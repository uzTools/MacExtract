/*
 * fmt_sit.c — StuffIt classic (1.5.1–4.x) container, methods 0/1/2/3
 * in M5; further methods land with M6.
 *
 * Sources. The CONTAINER is the format's own published description
 * since 2026-09-20 — docs/formats/stuffit-method-13.md and
 * reference/notes/sit_format_theunarchiver.md, which a reader written
 * from it alone walks 103 archives with, every entry matching the name
 * the oracle recorded (tools/derive_sit13.py). Method 3's tree is
 * docs/formats/serialized-huffman-tree.md, method 8's coder is
 * docs/formats/stuffit-method-8-mw.md, method 13's is the first note
 * above, and method 6's code book and framing are
 * docs/formats/stuffit-method-6.md. **Nothing in this file is
 * XADStuffItParser.m's, XADCompressHandle.m's or macunpack/sit.c's
 * any more**, since 2026-09-21: method 6's framing was the last of
 * it, and the RLE90 filter left the same day for the format's own
 * published description, reference/notes/rle90_theunarchiver.md,
 * which states every rule it implements.
 *
 * Archive header (22 bytes): u32 magic ('SIT!' or installer 'ST..'
 * variants), u16 numfiles, u32 totalsize, u32 magic2 'rLau', u8
 * version, 1 reserved byte, u32 headersize, u16 crc. The entry walk
 * simply runs while another 112-byte entry header fits below
 * totalsize.
 *
 * Entry header (112 bytes, u16 CRC-16/ARC of bytes 0..109 at 110):
 *   0 u8 rsrc method | 1 u8 data method | 2 u8 namelen | 3 name[31]
 *   34 u16 name crc | ... | 48 u16 numfiles (dirs) | 50..65 offsets |
 *   66 u32 type | 70 u32 creator | 74 u16 finderflags |
 *   76 u32 createdate | 80 u32 moddate | 84 u32 rsrclen |
 *   88 u32 datalen | 92 u32 rsrccomplen | 96 u32 datacomplen |
 *   100 u16 rsrc crc | 102 u16 data crc | 104.. pad/unknown |
 *   110 u16 header crc
 * Fork data follows the header: rsrc fork first, then data fork.
 *
 * Method byte: 0x80 = encrypted flag; masked value 0x20 = folder
 * start, 0x21 = folder end (0x10 = "folder contains encrypted").
 * Plain methods: 0 store, 1 RLE90, 2 compress LZW (14-bit, block
 * mode), 3 Huffman (bit-serialized tree), 5 LZAH, 6 fixed Huffman,
 * 8 MW, 13 LZSS+Huffman, 14 installer, 15 Arsenic.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define SIT_FILEHDRSIZE 112
#define SIT_ENCRYPTED   0x80
#define SIT_FOLDER_MASK 0x6F  /* ~(0x80|0x10) */
#define SIT_STARTFOLDER 0x20
#define SIT_ENDFOLDER   0x21
#define SIT_METHODMASK  0x7F  /* ~0x80 */

UncFormat unc_sit_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    /* Source: XADStuffItParser.m recognizeFileWithHandle. */
    if (len < 14) return UNC_FORMAT_UNKNOWN;
    if (unc_get_u32be(head + 10) != 0x724c6175u) return UNC_FORMAT_UNKNOWN;   /* 'rLau' */
    if (unc_get_u32be(head) == 0x53495421u) return UNC_FORMAT_SIT;        /* 'SIT!' */
    if (head[0] == 'S' && head[1] == 'T') {                  /* installers */
        if (head[2] == 'i' &&
            (head[3] == 'n' || (head[3] >= '0' && head[3] <= '9'))) return UNC_FORMAT_SIT;
        if (head[2] >= '0' && head[2] <= '9' &&
            head[3] >= '0' && head[3] <= '9') return UNC_FORMAT_SIT;
    }
    return UNC_FORMAT_UNKNOWN;
}

/* ------------------------------------------------------------------ */
/* Per-method fork decoders. Each writes exactly outlen decoded bytes */
/* (through obuf) to the sink and accumulates the CRC-16/ARC.         */
/* ------------------------------------------------------------------ */


/* Method 0: stored. */
static int sit_store(UncForkOut *f, UncBufIn *in, uint32_t outlen)
{
    uint32_t i;
    for (i = 0; i < outlen; i++) {
        int b = unc_bufin_next(in);
        if (b < 0) return in->err;
        if (unc_fork_put(f, (uint8_t)b) != UNC_OK) return UNC_ERR_SINK;
    }
    return UNC_OK;
}

/* Method 1: RLE90 — 0x90 0x00 is a literal 0x90; 0x90 n>=2 repeats
 * the previous byte n-1 more times; 0x90 0x01 is illegal.
 * Source: reference/notes/rle90_theunarchiver.md (unc_internal.h). */
static int sit_rle90(UncForkOut *f, UncBufIn *in, uint32_t outlen)
{
    UncRle90 r;
    uint32_t left = outlen;

    unc_rle90_init(&r, 1);
    while (left > 0) {
        int v = unc_rle90_take(&r);
        if (v < 0) {
            int b = unc_bufin_next(in);
            if (b < 0) return in->err;
            v = unc_rle90_feed(&r, b);
            if (v == UNC_RLE90_MORE) continue;
            if (v < 0) return v;                 /* UNC_ERR_CORRUPT */
        }
        if (unc_fork_put(f, (uint8_t)v) != UNC_OK) return UNC_ERR_SINK;
        left--;
    }
    return UNC_OK;
}

/* Method 2: compress LZW, 14-bit codes, block mode (flags 0x8e in
 * XADStuffItParser.m). */
static UNC_HOT int sit_lzw(UncForkOut *f, UncBufIn *in, uint32_t outlen, uint32_t complen,
                   UncAlloc *al)
{
    UncLzw z;
    uint32_t left = outlen;
    int err = unc_lzw_init(&z, al, in, 14, 1, complen);
    if (err != UNC_OK) return err;
    while (left > 0) {
        uint32_t space = f->cap - f->len;
        int32_t want = left < space ? (int32_t)left : (int32_t)space;
        int32_t got = unc_lzw_read(&z, f->buf + f->len, want);
        if (got < 0) { err = (int)got; goto out; }
        if (got == 0) { err = UNC_ERR_TRUNCATED; goto out; }
        f->len += (uint32_t)got;
        left -= (uint32_t)got;
        if (f->len == f->cap && (err = unc_fork_flush(f)) != UNC_OK) goto out;
    }
out:
    unc_lzw_free(&z, al);
    return err;
}

/* Method 3: Huffman with the bit-serialized tree, which PackIt and
 * DiskDoubler method 4 write too. Source:
 * docs/formats/serialized-huffman-tree.md, derived from this format's
 * own output — nine method-3 forks across eight archives read by the
 * rule it states, byte-exact against the oracle. */
static UNC_HOT int sit_huffman(UncForkOut *f, UncBufIn *in, uint32_t outlen,
                       UncAlloc *al)
{
    UncBitIn bi;
    UncHuff *h;
    uint32_t i;
    int err;

    h = (UncHuff *)unc_alloc(al, (uint32_t)sizeof *h);
    if (!h) return UNC_ERR_MEM;
    unc_bitin_init(&bi, in);
    err = unc_huff_read_tree(h, &bi);
    if (err == UNC_OK) {
        for (i = 0; i < outlen; i++) {
            int sym = unc_huff_decode(h, &bi);
            if (sym < 0) {
                err = bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT;
                break;
            }
            if (unc_fork_put(f, (uint8_t)sym) != UNC_OK) { err = UNC_ERR_SINK; break; }
        }
    }
    unc_free(al, h);
    return err;
}

/* ------------------------------------------------------------------ */
/* Method 13: LZSS (64 KB window) + Huffman, little-endian bit order. */
/* Two literal/length codes (321 symbols; the coder alternates:       */
/* after a literal the "first" code is used, after a match the        */
/* "second") and an offset code. A leading byte selects one of five   */
/* fixed code sets or a dynamic set serialized via a fixed meta code. */
/*                                                                    */
/* Source: docs/formats/stuffit-method-13.md — the format's own       */
/* published description plus the two corrections it needs (the       */
/* meta-code's "in addition" rule, and a match offset one further     */
/* back than it says). A reader written from that page alone          */
/* reproduces 897 method-13 forks across 103 archives, meeting all six */
/* code selectors (tools/derive_sit13.py). sit13_tables.h is the      */
/* page's too, and identical to what XADStuffIt13Handle.m carries —   */
/* compared array by array before the generator was pointed at it.    */
/* ------------------------------------------------------------------ */

#include "sit13_tables.h"

#define SIT13_WINDOW 65536u
#define SIT13_WINMIN 256u

/* The window is 64 KB by the format, but no stream can REACH further back
 * than it has produced: an offset is `pos - moff` and a well-formed encoder
 * never emits moff > pos, because those bytes do not exist yet. So a fork
 * whose whole output is 6 KB can only ever address 6 KB of window, and the
 * other 58 KB is allocated, zeroed and never read.
 *
 * Rounding up to a power of two keeps the existing `& (win - 1)` masking
 * exact: with win >= outlen, pos < outlen <= win so `pos & (win-1) == pos`
 * and `from & (win-1) == from` for every reachable offset — the same indices
 * the 64 KB window computes. Streams that DO reference beyond what they have
 * produced read a different zero-filled slot than before; that cannot happen
 * in a valid archive, and stays in bounds either way. */
static uint32_t sit13_winsize(uint32_t outlen)
{
    uint32_t w = SIT13_WINMIN;
    while (w < outlen && w < SIT13_WINDOW) w <<= 1;
    return w;
}

typedef struct Sit13 {
    UncCanon first, second, offset;
    uint8_t lengths[321];
} Sit13;

/* Decode one meta-code symbol (explicit LSB-first code table). */
static int sit13_metasym(UncBitIn *bi)
{
    uint32_t acc = 0;
    int len, i;
    for (len = 1; len <= 12; len++) {
        int bit = unc_bitin_bit(bi);
        if (bit < 0) return -1;
        acc |= (uint32_t)bit << (len - 1);
        for (i = 0; i < 37; i++)
            if (sit13_metacodelengths[i] == len && sit13_metacodes[i] == acc)
                return i;
    }
    return -1;
}

/* Parse one dynamic code's lengths via the meta code
 * (allocAndParseCodeOfSize: in the reference). */
static int sit13_parse_code(UncCanon *cn, UncBitIn *bi, uint8_t *lengths,
                            int32_t nsyms)
{
    int32_t i;
    int len = 0;

    for (i = 0; i < nsyms; i++) {
        int val = sit13_metasym(bi);
        if (val < 0) return bi->err != UNC_OK ? bi->err : UNC_ERR_CORRUPT;
        switch (val) {
        case 31: len = -1; break;
        case 32: len++; break;
        case 33: len--; break;
        case 34: {
            int bit = unc_bitin_bit(bi);
            if (bit < 0) return bi->err;
            if (bit) {
                if (i >= nsyms) return UNC_ERR_CORRUPT;
                lengths[i++] = len < 0 ? 0 : (uint8_t)len;
            }
            break;
        }
        case 35: case 36: {
            int32_t rep = unc_bitin_bits_le(bi, val == 35 ? 3 : 6);
            if (rep < 0) return bi->err;
            rep += val == 35 ? 2 : 10;
            while (rep-- > 0) {
                if (i >= nsyms) return UNC_ERR_CORRUPT;
                lengths[i++] = len < 0 ? 0 : (uint8_t)len;
            }
            break;
        }
        default: len = val + 1; break;
        }
        if (i >= nsyms) break;   /* repeats may land exactly on the end */
        lengths[i] = len < 0 ? 0 : (uint8_t)len;
    }
    return unc_canon_build(cn, lengths, nsyms);
}

/* Hand over what the window has taken since the last flush.
 *
 * The decoder writes every byte into its own window anyway, so the
 * window IS the staging buffer and a run costs no memory to keep. The
 * alternative is what this file did until 2026-09-20: one
 * `unc_fork_put` per output byte, which is a CALL — the function is
 * `static inline` but carries a call to the flush, so gcc leaves it
 * out of line at `-Os`, and a 68000 profile put the jsr, the ten
 * instructions and the rts at 13.6 % of a method-13 run.
 *
 * `to - from` is never more than the window: the loop head below
 * flushes at a quarter of it, and one iteration adds at most 32,832
 * bytes (the 0x13f escape's 15 bits plus 65). */
static int sit13_flush(UncForkOut *f, const uint8_t *window, uint32_t win,
                       uint32_t from, uint32_t to)
{
    uint32_t n = to - from, a = from & (win - 1);
    if (n == 0) return UNC_OK;
    if (a + n > win) {                      /* the run wraps the window */
        int err = unc_fork_write(f, window + a, win - a);
        if (err != UNC_OK) return err;
        n -= win - a;
        a = 0;
    }
    return unc_fork_write(f, window + a, n);
}

static int sit13_fork(UncForkOut *f, UncBufIn *in, uint32_t outlen,
                      UncAlloc *al)
{
    Sit13 *hz;
    uint8_t *window;
    UncBitIn bi;
    UncCanon *curr, *second;
    uint32_t pos = 0, flushed = 0;
    uint32_t win = sit13_winsize(outlen), thresh;
    int err = UNC_OK;
    int val, sel;

    hz = (Sit13 *)unc_alloc(al, (uint32_t)sizeof *hz);
    if (!hz) return UNC_ERR_MEM;
    window = (uint8_t *)unc_alloc(al, win);
    if (!window) { unc_free(al, hz); return UNC_ERR_MEM; }
    {
        uint32_t i;
        for (i = 0; i < win; i++) window[i] = 0;
    }

    val = unc_bufin_next(in);
    if (val < 0) { err = in->err; goto out; }
    sel = val >> 4;

    unc_bitin_init_le(&bi, in);

    if (sel == 0) {
        err = sit13_parse_code(&hz->first, &bi, hz->lengths, 321);
        if (err == UNC_OK) {
            if (val & 0x08) {
                second = &hz->first;
            } else {
                err = sit13_parse_code(&hz->second, &bi, hz->lengths, 321);
                second = &hz->second;
            }
        } else second = &hz->first;
        if (err == UNC_OK)
            err = sit13_parse_code(&hz->offset, &bi, hz->lengths,
                                   (val & 0x07) + 10);
    } else if (sel < 6) {
        err = unc_canon_build(&hz->first, sit13_firstlengths[sel - 1], 321);
        if (err == UNC_OK)
            err = unc_canon_build(&hz->second, sit13_secondlengths[sel - 1], 321);
        if (err == UNC_OK)
            err = unc_canon_build(&hz->offset, sit13_offsetlengths[sel - 1],
                                  sit13_offsetcodesize[sel - 1]);
        second = &hz->second;
    } else {
        err = UNC_ERR_CORRUPT;
        second = &hz->first;
    }
    if (err != UNC_OK) goto out;

    curr = &hz->first;
    thresh = win >> 2;
    while (pos < outlen) {
        int sym;
        if (pos - flushed >= thresh) {
            err = sit13_flush(f, window, win, flushed, pos);
            if (err != UNC_OK) goto out;
            flushed = pos;
        }
        sym = unc_canon_decode(curr, &bi);
        if (sym < 0) {
            err = bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT;
            goto out;
        }
        if (sym < 0x100) {
            curr = &hz->first;
            window[pos++ & (win - 1)] = (uint8_t)sym;
        } else {
            int32_t mlen, moff, bl;
            curr = second;
            if (sym < 0x13e) mlen = sym - 0x100 + 3;
            else if (sym == 0x13e) mlen = unc_bitin_bits_le(&bi, 10) + 65;
            else if (sym == 0x13f) mlen = unc_bitin_bits_le(&bi, 15) + 65;
            else { err = UNC_ERR_TRUNCATED; goto out; }  /* 0x140: early end */
            if (mlen < 0) { err = bi.err; goto out; }

            bl = unc_canon_decode(&hz->offset, &bi);
            if (bl < 0) { err = bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT; goto out; }
            if (bl == 0) moff = 1;
            else if (bl == 1) moff = 2;
            else {
                int32_t low = unc_bitin_bits_le(&bi, bl - 1);
                if (low < 0) { err = bi.err; goto out; }
                moff = (1 << (bl - 1)) + low + 1;
            }

            {
                uint32_t from = pos - (uint32_t)moff;
                while (mlen-- > 0 && pos < outlen) {
                    window[pos++ & (win - 1)] = window[from++ & (win - 1)];
                }
            }
        }
    }
    err = sit13_flush(f, window, win, flushed, pos);

out:
    unc_free(al, window);
    unc_free(al, hz);
    return err;
}

/* ------------------------------------------------------------------ */
/* Method 6: "fixed Huffman" — a fork is a sequence of independent    */
/* segments, each of which decodes to a PackBits stream that is then  */
/* expanded into the fork.                                            */
/*                                                                    */
/*   s32 size    counted from its own first byte.                     */
/*   size < 0    the segment is stored: |size| - 4 PackBits bytes.    */
/*   size > 0    u32 expanded length, u16 code count, then that many  */
/*               bytes naming what leaf ordinals 1..count stand for,  */
/*               then a bitstream ending at the terminator symbol.    */
/*                                                                    */
/* The Huffman tree's SHAPE is the same in every archive (sit6_tables */
/* .h); only the leaf bytes change per segment, which is what "fixed" */
/* means here.                                                        */
/*                                                                    */
/* Source: docs/formats/stuffit-method-6.md, which describes the code */
/* book, this framing and its three corrections, and which is written */
/* against reference/deark/modules/stuffit.c (MIT — deark credits     */
/* macunpack as documentation and uses none of its code). A reader    */
/* written from that note alone reads all 11 method-6 forks in the    */
/* corpus, byte for byte (tools/derive_sit6.py). XADMaster recognizes */
/* the method and refuses it (XADStuffItParser.m), which is where the */
/* name comes from; this file called macunpack "the ONLY reference    */
/* implementation the project has for method 6" until 2026-09-21, and */
/* that was false.                                                    */
/* ------------------------------------------------------------------ */

#include "sit6_tables.h"

/* Build the fixed tree from `sit6_runlen`/`sit6_runbits` into two
 * 257-entry arrays the decoder walks. 26 bytes and this function stand
 * in for the 1,028-byte table that used to be compiled in; the arrays
 * are allocated per FORK, so what was permanent code is transient heap
 * and only while a method-6 fork is being read.
 *
 * Source: reference/deark/modules/stuffit.c (MIT). A child <= 258 is a
 * leaf whose value is the ordinal of a byte the segment declares, and
 * 257/258 are the terminator; a larger value is the internal node at
 * `value - 258`. **The terminator gets macunpack's extra level on
 * purpose**: its code is 12 bits and the tree spends 13, accepting
 * either final bit, and a tree that stopped at 12 would consume one
 * bit fewer than every stream here was written for. Checked over all
 * 8,192 bit paths of depth 13 against the table this replaces
 * (sit6_tables.h). */
static void sit6_build(uint16_t *zero, uint16_t *one)
{
    uint32_t code = 0, prev = 0, sym = 0, nodes = 1;
    uint32_t run, k, i;
    int len = 0, prevlen = 0;

    for (i = 0; i < SIT6_INTERNAL; i++) {
        zero[i] = 0;
        one[i] = 0;
    }
    for (run = 0; run < SIT6_RUNS; run++) {
        for (k = 0; k < sit6_runlen[run]; k++, sym++) {
            uint32_t node = 0;
            int b;

            len = sit6_runbits[run];
            if (prevlen == 0)              code = 0;
            else if (len < prevlen)        code = (prev >> (prevlen - len)) + 1;
            else                           code = (prev + 1) << (len - prevlen);
            prev = code;
            prevlen = len;

            for (b = len - 1; b >= 0; b--) {
                uint32_t bit = (code >> b) & 1u;
                uint16_t child;

                if (b == 0) {
                    if (bit) one[node] = (uint16_t)(sym + 1);
                    else     zero[node] = (uint16_t)(sym + 1);
                    break;
                }
                child = bit ? one[node] : zero[node];
                if (child == 0) {
                    child = (uint16_t)(SIT6_LEAVES + nodes);
                    if (bit) one[node] = child;
                    else     zero[node] = child;
                    nodes++;
                }
                node = (uint32_t)(child - SIT6_LEAVES);
            }
        }
    }
    /* Symbol 256 is the terminator, and macunpack's tree spends a
     * thirteenth bit on it: its 12-bit code leads to an internal node
     * whose two children are BOTH terminators. There is exactly one
     * leaf 257 to replace, so this stops at the first — a scan that ran
     * on would find the terminator it had just written and split that
     * too, which is the whole of what went wrong the first time. */
    if (nodes < SIT6_INTERNAL) {
        for (i = 0; i < nodes; i++) {
            if (zero[i] == SIT6_CODES) {
                zero[i] = (uint16_t)(SIT6_LEAVES + nodes);
            } else if (one[i] == SIT6_CODES) {
                one[i] = (uint16_t)(SIT6_LEAVES + nodes);
            } else {
                continue;
            }
            zero[nodes] = SIT6_CODES;
            one[nodes] = SIT6_LEAVES;
            nodes++;
            break;
        }
    }
}

/* Largest segment buffer we will allocate. macunpack decodes into a
 * fixed char[32768], so the format does not exceed that; the cap is
 * doubled to leave a real archive room to disagree. Nothing is
 * allocated AT the cap — every buffer is the size the segment in hand
 * declares, which for the corpus's only method-6 fork is 31,806 B. */
#define SIT6_MAX_SEG 65536u

/* Grow the segment buffer to n bytes. The old contents are dead at a
 * segment boundary, so this frees and allocates rather than copying:
 * a copy-based growth would need old + new bytes live at once, which
 * is what made growth-on-demand lose to one-shot sizing for the LZW
 * table (DECISIONS.md, 2026-08-03). */
static int sit6_need(UncAlloc *al, uint8_t **seg, uint32_t *cap, uint32_t n)
{
    if (n <= *cap) return UNC_OK;
    if (n > SIT6_MAX_SEG) return UNC_ERR_CORRUPT;
    unc_free(al, *seg);
    *seg = NULL;
    *cap = 0;
    *seg = (uint8_t *)unc_alloc(al, n);
    if (!*seg) return UNC_ERR_MEM;
    *cap = n;
    return UNC_OK;
}

/* Big-endian scalars, byte-wise (no unaligned loads on a 68000). */
static int sit6_u32(UncBufIn *in, uint32_t *out)
{
    uint32_t v = 0;
    int i, b;
    for (i = 0; i < 4; i++) {
        if ((b = unc_bufin_next(in)) < 0) return in->err;
        v = (v << 8) | (uint32_t)b;
    }
    *out = v;
    return UNC_OK;
}

/* Expand one PackBits stream into the fork, stopping at *left bytes.
 * Standard Macintosh PackBits: a control byte below 0x80 introduces
 * n + 1 literals, 0x80 is a no-op, and above that it repeats the next
 * byte 0x101 - n times. The remaining fork length is a maximum and
 * not an expectation. Source: docs/formats/stuffit-method-6.md,
 * *PackBits, once per block*. */
static int sit6_packbits(UncForkOut *f, const uint8_t *seg, uint32_t seglen,
                         uint32_t *left)
{
    uint32_t p = 0;
    while (p < seglen && *left > 0) {
        uint32_t n = seg[p++];
        if (n < 0x80) {
            n++;
            if (seglen - p < n) return UNC_ERR_CORRUPT;
            while (n-- > 0 && *left > 0) {
                if (unc_fork_put(f, seg[p++]) != UNC_OK) return UNC_ERR_SINK;
                (*left)--;
            }
        } else if (n != 0x80) {
            uint8_t v;
            n = 0x101u - n;
            if (p >= seglen) return UNC_ERR_CORRUPT;
            v = seg[p++];
            while (n-- > 0 && *left > 0) {
                if (unc_fork_put(f, v) != UNC_OK) return UNC_ERR_SINK;
                (*left)--;
            }
        }
    }
    return UNC_OK;
}

/* Decode one Huffman-coded segment into seg[0..explen). */
static int sit6_huffseg(UncBufIn *in, uint8_t *seg, uint32_t explen,
                        const uint8_t *leaf, uint32_t codes,
                        uint32_t segbytes, uint32_t *used,
                        const uint16_t *sit6_zero, const uint16_t *sit6_one)
{
    UncBitIn bi;
    uint32_t start, got = 0;

    unc_bitin_init(&bi, in);
    start = unc_bitin_bytepos(&bi);
    for (;;) {
        uint16_t node = 0, child = 0;
        int depth = 0;
        do {
            int bit = unc_bitin_bit(&bi);
            if (bit < 0) return bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT;
            child = bit ? sit6_one[node] : sit6_zero[node];
            if (child <= SIT6_LEAVES) break;             /* a leaf ordinal */
            node = (uint16_t)(child - SIT6_LEAVES);
        } while (++depth <= SIT6_DEPTH);
        if (child > SIT6_LEAVES) return UNC_ERR_CORRUPT; /* not a tree */
        if (child >= SIT6_LEAVES - 1) break;             /* terminator */
        /* A code for a leaf the segment never named stands for nothing.
         * Both references index their translation array with it and
         * bound it against nothing, handing back a byte an earlier
         * segment left there — a wrong fork rather than a refused one.
         * No segment in the corpus does it (correction 2 of
         * docs/formats/stuffit-method-6.md). */
        if (child > codes) return UNC_ERR_CORRUPT;
        if (got == explen) return UNC_ERR_CORRUPT;
        seg[got++] = leaf[child - 1];
        /* Bounded by the segment's own byte count, so a bitstream that
         * never terminates cannot read on into the next fork. */
        if (unc_bitin_bytepos(&bi) - start > segbytes) return UNC_ERR_CORRUPT;
    }
    /* The terminator is REQUIRED, and it is where the declared length
     * says it is: across the corpus's 13 Huffman segments the symbol
     * after the declared length is the terminator in 13 of 13
     * (correction 1 of docs/formats/stuffit-method-6.md). deark stops
     * at the length without reading it and macunpack ignores the
     * length and reads until it; requiring both refuses a segment the
     * two would disagree about. */
    if (got != explen) return UNC_ERR_CORRUPT;
    *used = unc_bitin_bytepos(&bi) - start;
    return *used <= segbytes ? UNC_OK : UNC_ERR_CORRUPT;
}

static int sit6_fork(UncForkOut *f, UncBufIn *in, uint32_t outlen, UncAlloc *al)
{
    uint8_t *seg = NULL;
    uint32_t segcap = 0;
    uint32_t left = outlen;
    uint8_t leaf[256];
    uint16_t *tree;
    int err = UNC_OK;

    /* The fixed tree, built once per fork from 26 bytes (sit6_build).
     * Per-entry on failure, like every other allocation here. */
    tree = (uint16_t *)unc_alloc(al, 2u * SIT6_INTERNAL * sizeof(uint16_t));
    if (!tree) return UNC_ERR_MEM;
    sit6_build(tree, tree + SIT6_INTERNAL);

    /* Driven by the fork length rather than by the compressed length:
     * every iteration consumes at least the 4-byte segment header, and
     * the bufin is limited to this fork, so a stream that stops
     * producing output still terminates on truncation. */
    while (left > 0) {
        uint32_t size = 0, seglen, i;
        int stored;

        if ((err = sit6_u32(in, &size)) != UNC_OK) goto out;
        stored = (size & 0x80000000u) != 0;
        if (stored) size = 0u - size;        /* negate without signed UB */
        if (size < 4) { err = UNC_ERR_CORRUPT; goto out; }
        size -= 4;

        if (stored) {
            seglen = size;
            if ((err = sit6_need(al, &seg, &segcap, seglen)) != UNC_OK) goto out;
            for (i = 0; i < seglen; i++) {
                int b = unc_bufin_next(in);
                if (b < 0) { err = in->err; goto out; }
                seg[i] = (uint8_t)b;
            }
        } else {
            uint32_t explen = 0, codes, used = 0;
            int hi, lo;

            if (size < 6) { err = UNC_ERR_CORRUPT; goto out; }
            if ((err = sit6_u32(in, &explen)) != UNC_OK) goto out;
            if ((hi = unc_bufin_next(in)) < 0 ||
                (lo = unc_bufin_next(in)) < 0) {
                err = in->err;
                goto out;
            }
            codes = ((uint32_t)hi << 8) | (uint32_t)lo;
            size -= 6;
            /* Ordinals 257 and 258 are the terminator; a count that
             * reached them would redefine it. */
            if (codes > SIT6_LEAVES - 2 || codes > size || explen == 0) {
                err = UNC_ERR_CORRUPT;
                goto out;
            }
            for (i = 0; i < codes; i++) {
                int b = unc_bufin_next(in);
                if (b < 0) { err = in->err; goto out; }
                leaf[i] = (uint8_t)b;
            }
            size -= codes;
            if ((err = sit6_need(al, &seg, &segcap, explen)) != UNC_OK) goto out;
            if ((err = sit6_huffseg(in, seg, explen, leaf, codes, size,
                                    &used, tree, tree + SIT6_INTERNAL))
                    != UNC_OK) goto out;
            /* The bitstream may end before the segment does. */
            for (i = used; i < size; i++) {
                if (unc_bufin_next(in) < 0) { err = in->err; goto out; }
            }
            seglen = explen;
        }
        if ((err = sit6_packbits(f, seg, seglen, &left)) != UNC_OK) goto out;
    }

out:
    unc_free(al, seg);
    unc_free(al, tree);
    return err;
}

/* ------------------------------------------------------------------ */
/* Method 8: "MW" — Miller and Wegman's variation on Ziv-Lempel, in    */
/* which a dictionary entry is the concatenation of two earlier ones   */
/* rather than an entry plus a byte. LSB-first codes, 9 bits growing   */
/* as the dictionary fills.                                           */
/*                                                                    */
/* Source: docs/formats/stuffit-method-8-mw.md, derived from this     */
/* format's own output — all four method-8 forks the corpus has,       */
/* reproduced byte for byte against the oracle                        */
/* (tools/derive_stuffit8.py).                                        */
/*                                                                    */
/* TWO RULES BELOW ARE NOT IN THAT NOTE and remain                    */
/* reference/XADMaster/XADStuffItOldHandles.m's (SIT_mw, SITMW_out;   */
/* libxad heritage) — LGPL, see NOTICE: the table RESTART (a code      */
/* equal to the next free one) and the END of the stream (a code       */
/* greater than it), with the 14-bit ceiling that goes with them. No   */
/* specimen reaches any of the three — the largest fork in the corpus  */
/* stops at 7,347 entries and 13 bits — so they are the part of this   */
/* row a derivation could not take.                                   */
/* ------------------------------------------------------------------ */

#define MW_DICT  16385
#define MW_STACK 16384

typedef struct SitMw {
    uint16_t dict[MW_DICT];
    uint16_t stack[MW_STACK];
} SitMw;

/* Emit the chain for ptr (SITMW_out). */
static int mw_out(UncForkOut *f, SitMw *m, int32_t ptr, uint32_t *pos,
                  uint32_t outlen)
{
    uint32_t sp = 1;
    m->stack[0] = (uint16_t)ptr;
    while (sp > 0) {
        ptr = m->stack[--sp];
        while (ptr >= 256) {
            if (sp >= MW_STACK) return UNC_ERR_CORRUPT;
            m->stack[sp++] = m->dict[ptr];
            ptr = m->dict[ptr - 1];
        }
        if (*pos < outlen) {
            (*pos)++;
            if (unc_fork_put(f, (uint8_t)ptr) != UNC_OK) return UNC_ERR_SINK;
        }
    }
    return UNC_OK;
}

static int sit_mw_fork(UncForkOut *f, UncBufIn *in, uint32_t outlen,
                       UncAlloc *al)
{
    SitMw *m;
    UncBitIn bi;
    uint32_t pos = 0;
    int err = UNC_OK;

    m = (SitMw *)unc_alloc(al, (uint32_t)sizeof *m);
    if (!m) return UNC_ERR_MEM;
    unc_bitin_init_le(&bi, in);

    while (pos < outlen) {
        int32_t max = 256, max1 = 512, bits = 9;
        int32_t ptr = unc_bitin_bits_le(&bi, (int)bits);
        if (ptr < 0) { err = bi.err; goto out; }
        if (ptr < max) {
            m->dict[255] = (uint16_t)ptr;
            if ((err = mw_out(f, m, ptr, &pos, outlen)) != UNC_OK) goto out;
            for (;;) {
                if (pos >= outlen) goto out;
                ptr = unc_bitin_bits_le(&bi, (int)bits);
                if (ptr < 0) { err = bi.err; goto out; }
                if (ptr >= max) break;
                if (max >= MW_DICT) { err = UNC_ERR_CORRUPT; goto out; }
                m->dict[max++] = (uint16_t)ptr;
                if (max == max1) { max1 <<= 1; bits++; }
                if ((err = mw_out(f, m, ptr, &pos, outlen)) != UNC_OK) goto out;
            }
        }
        if (ptr > max) break;   /* ptr == max restarts the table */
    }
    if (pos < outlen) err = UNC_ERR_TRUNCATED;

out:
    unc_free(al, m);
    return err;
}

/* Output adapter for the -lh1- coder shared with LZH (unc_lzah.c),
 * which hands its output back in runs out of its own window. */
static int sit_put_run(void *ctx, const uint8_t *p, uint32_t n)
{
    return unc_fork_write((UncForkOut *)ctx, p, n);
}

/* Decode one fork (shared with the SIT5 container). Returns a
 * per-entry status. */
int unc_sit_decode_fork(UncCtx *c, UncFork fork, uint32_t at,
                        uint32_t complen, uint32_t outlen, int method,
                        uint16_t wantcrc, uint8_t *iobuf, uint32_t iocap,
                        uint8_t *obuf, uint32_t ocap, UncCrypt *cr)
{
    UncBufIn in;
    UncForkOut f;
    int err;

    if (outlen == 0) return UNC_OK;

    if (c->io->seek(c->io->ctx, at) < 0) return UNC_ERR_IO;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = complen;
    /* An encrypted fork is decrypted as it is read, so every method
     * below sees exactly what it would have seen unencrypted. */
    if (cr) in.crypt = cr;

    unc_fork_out(&f, c, fork, !c->opt.test_only, UNC_CK_CRC16_ARC,
                 obuf, ocap);

    switch (method & 0x0f) {
    case 0:  err = sit_store(&f, &in, outlen); break;
    case 1:  err = sit_rle90(&f, &in, outlen); break;
    case 2:  err = sit_lzw(&f, &in, outlen, complen, c->al); break;
    case 3:  err = sit_huffman(&f, &in, outlen, c->al); break;
    case 5:  {
        /* "LZAH" is LHarc's -lh1- coder, and the oracle runs one handle
         * for both; it lives in unc_lzah.c and fmt_lzh.c calls the same
         * function. */
        UncBitIn bi;
        unc_bitin_init(&bi, &in);
        err = unc_lzah_decode(c->al, &bi, outlen, UNC_LZAH_LH1, sit_put_run, &f);
        break;
    }
    case 6:  err = sit6_fork(&f, &in, outlen, c->al); break;
    case 8:  err = sit_mw_fork(&f, &in, outlen, c->al); break;
    case 13: err = sit13_fork(&f, &in, outlen, c->al); break;
    case 15: err = unc_arsenic_decode(&in, c->al, outlen, &f); break;
    default: return UNC_ERR_UNSUPPORTED;
    }
    if (err == UNC_OK) err = unc_fork_flush(&f);
    /* Method 15 carries its own CRC-32, checked inside the decoder;
     * the header CRC-16 field is not meaningful for it. */
    if (err == UNC_OK && (method & 0x0f) != 15 && f.crc16 != wantcrc)
        err = UNC_ERR_CRC;
    return err;
}

/* ------------------------------------------------------------------ */
/* Encryption                                                         */
/*                                                                    */
/* An encrypted fork carries sixteen bytes of key material at its END  */
/* (so its compressed length is sixteen more than the ciphertext), and */
/* the byte at header offset 104/105 says how many bytes the last      */
/* plaintext block was padded with — which nothing here reads, because */
/* every method stops when it has produced the fork's declared length  */
/* and so never consumes the padding. XADMaster shortens the stream by */
/* it instead; same result. The other half of the key is the           */
/* ARCHIVE's 'MKey' resource, which is in its resource fork and not in */
/* the stream at all: without it nothing can decrypt this, and the     */
/* entry fails UNC_ERR_ENCRYPTED rather than asking for a password it  */
/* could not use.                                                     */
/* Source: XADStuffItParser.m decryptHandleForEntryWithDictionary.     */
/* ------------------------------------------------------------------ */

static int sit_fork_crypt(UncCtx *c, UncCrypt *cr, uint32_t at,
                          uint32_t complen)
{
    uint8_t entrykey[16];
    int attempt = 0;

    if (!c->opt.mkey) return UNC_ERR_ENCRYPTED;
    if (complen < 16) return UNC_ERR_CORRUPT;
    if (unc_read_at(c->io, at + complen - 16, entrykey, 16) != UNC_OK)
        return UNC_ERR_TRUNCATED;
    for (;;) {
        int err = unc_password(c, attempt > 0);
        if (err != UNC_OK) return err;
        err = unc_crypt_sit(cr, c->al, c->pw, c->pwlen, entrykey, c->opt.mkey);
        if (err == UNC_OK) return UNC_OK;
        attempt++;              /* the archive rejected it; ask again */
    }
}

/* ------------------------------------------------------------------ */
/* Container walk                                                     */
/* ------------------------------------------------------------------ */

#define SIT_MAX_DEPTH 32

int unc_sit_extract(UncCtx *c)
{
    uint8_t hdr[SIT_FILEHDRSIZE];
    uint32_t totalsize, pos, fsize;
    uint8_t path[UNC_NAME_MAX + 1];
    uint16_t plen = 0;
    uint16_t pathlens[SIT_MAX_DEPTH];
    int depth = 0;
    uint8_t *iobuf, *obuf;
    UncCrypt *cr;
    uint32_t iocap = UNC_IOBUF, ocap = UNC_IOBUF;
    int err = UNC_OK, cut = 0;

    fsize = unc_io_size32(c->io);

    if (unc_read_at(c->io, 0, hdr, 22) != UNC_OK) return UNC_ERR_FORMAT;
    if (!unc_sit_probe(hdr, 22, NULL)) return UNC_ERR_FORMAT;
    /* The archive states its own length. A file SHORTER than that is
     * cut, and clamping the walk to what is there — which is what keeps
     * it inside the file — is exactly the step that used to erase the
     * evidence: the loop then ended tidily at the new end and the run
     * reported success with the entries beyond the cut missing. Clamp,
     * and remember (2026-08-29; BLOCKERS.md). */
    totalsize = unc_get_u32be(hdr + 6);
    if (fsize != UNC_SIZE_UNKNOWN && totalsize > fsize) {
        totalsize = fsize;
        cut = 1;
    }
    pos = 22;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap + (uint32_t)sizeof *cr);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;
    cr = (UncCrypt *)(void *)(obuf + ocap);
    unc_crypt_init(cr);

    while (pos + SIT_FILEHDRSIZE <= totalsize) {
        uint32_t namelen, rmeth, dmeth, rlen, dlen, rcomp, dcomp, start;
        UncEntryInfo e;
        int sret, est;

        if (unc_read_at(c->io, pos, hdr, SIT_FILEHDRSIZE) != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            break;
        }
        if (unc_crc16_arc(0, hdr, 110) != unc_get_u16be(hdr + 110)) {
            /* Without a valid header there is no way to find the next
             * entry (XADStuffItParser raises a checksum exception). */
            err = UNC_ERR_CORRUPT;
            break;
        }

        rmeth = hdr[0];
        dmeth = hdr[1];
        namelen = hdr[2];
        if (namelen > 31) namelen = 31;
        rlen  = unc_get_u32be(hdr + 84);
        dlen  = unc_get_u32be(hdr + 88);
        rcomp = unc_get_u32be(hdr + 92);
        dcomp = unc_get_u32be(hdr + 96);
        start = pos + SIT_FILEHDRSIZE;

        if ((rmeth & SIT_FOLDER_MASK) == SIT_STARTFOLDER ||
            (dmeth & SIT_FOLDER_MASK) == SIT_STARTFOLDER) {
            unc_entry_clear(&e);
            unc_entry_set_path(&e, path, plen);
            unc_entry_path_append(&e, hdr + 3, namelen);
            e.is_dir = 1;
            e.data_size = e.rsrc_size = 0;
            e.comp_data_size = e.comp_rsrc_size = 0;
            e.finder_flags = unc_get_u16be(hdr + 74);
            e.create_date  = unc_get_u32be(hdr + 76);
            e.mod_date     = unc_get_u32be(hdr + 80);
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; goto out; }
            if (sret == 0 && c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
            if (depth + 1 >= SIT_MAX_DEPTH) { err = UNC_ERR_CORRUPT; goto out; }
            pathlens[depth++] = plen;
            plen = e.name_len;
            {
                uint32_t i;
                for (i = 0; i < e.name_len; i++) path[i] = e.name[i];
            }
            pos = start;
            continue;
        }
        if ((rmeth & SIT_FOLDER_MASK) == SIT_ENDFOLDER ||
            (dmeth & SIT_FOLDER_MASK) == SIT_ENDFOLDER) {
            if (depth > 0) plen = pathlens[--depth];
            pos = start;
            continue;
        }

        unc_entry_clear(&e);
        unc_entry_set_path(&e, path, plen);
        unc_entry_path_append(&e, hdr + 3, namelen);
        e.type         = unc_get_u32be(hdr + 66);
        e.creator      = unc_get_u32be(hdr + 70);
        e.finder_flags = unc_get_u16be(hdr + 74);
        e.create_date  = unc_get_u32be(hdr + 76);
        e.mod_date     = unc_get_u32be(hdr + 80);
        e.rsrc_size = rlen;
        e.data_size = dlen;
        e.comp_rsrc_size = rcomp;
        e.comp_data_size = dcomp;
        e.method_rsrc = (uint8_t)(rmeth & SIT_METHODMASK);
        e.method_data = (uint8_t)(dmeth & SIT_METHODMASK);

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; goto out; }

        if (sret == 0) {
            est = UNC_OK;
            if (!c->opt.list_only) {
                if (start + rcomp < start || start + rcomp + dcomp < start ||
                    (fsize != UNC_SIZE_UNKNOWN && start + rcomp + dcomp > fsize)) {
                    est = UNC_ERR_TRUNCATED;   /* forks extend past EOF */
                } else {
                    /* Sixteen bytes of key sit at the end of an
                     * encrypted fork and are not part of its stream. */
                    uint32_t rc = rcomp, dc = dcomp;
                    int renc = (rmeth & SIT_ENCRYPTED) && rlen;
                    int denc = (dmeth & SIT_ENCRYPTED) && dlen;

                    est = UNC_OK;
                    if (renc) {
                        est = sit_fork_crypt(c, cr, start, rcomp);
                        if (est == UNC_OK) rc -= 16;
                    }
                    if (est == UNC_OK)
                        est = unc_sit_decode_fork(c, UNC_FORK_RSRC, start,
                                       rc, rlen,
                                       (int)rmeth, unc_get_u16be(hdr + 100),
                                       iobuf, iocap, obuf, ocap,
                                       renc ? cr : NULL);
                    if (est == UNC_OK && denc) {
                        est = sit_fork_crypt(c, cr, start + rcomp, dcomp);
                        if (est == UNC_OK) dc -= 16;
                    }
                    if (est == UNC_OK)
                        est = unc_sit_decode_fork(c, UNC_FORK_DATA,
                                       start + rcomp,
                                       dc, dlen, (int)dmeth,
                                       unc_get_u16be(hdr + 102),
                                       iobuf, iocap, obuf, ocap,
                                       denc ? cr : NULL);
                }
            }
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
            if (unc_fatal(est)) {
                err = est;
                goto out;
            }
        }

        if (start + rcomp + dcomp < start) { err = UNC_ERR_CORRUPT; break; }
        pos = start + rcomp + dcomp;
    }

out:
    unc_crypt_free(cr, c->al);
    unc_free(c->al, iobuf);
    /* A walk that finished tidily over a file shorter than the archive
     * says it is finished over half an archive. What was decoded stands
     * — it is on the disk and it is correct — but the run is not
     * complete, and until 2026-08-29 it said it was. */
    if (err == UNC_OK && cut) err = UNC_ERR_TRUNCATED;
    return err;
}

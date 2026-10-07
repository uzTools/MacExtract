/*
 * fmt_now.c — Now Compress archives.
 *
 *   Source: docs/formats/now-compress.md — this project's own
 *   description of the format, measured off Now Compress 5.0.1 driven
 *   under emulation (tools/vmac/nowcompress.py) and re-read by
 *   tools/derive_now.py, which decodes every block of both corpus
 *   archives from that note alone: the entry table and its per-record
 *   fields, the block table, all four block shapes, the three
 *   checksums and the header fields that bound a block's stream.
 *
 *   The coders below were REWRITTEN from that note on 2026-09-21, the
 *   M12 transcription of XADNowCompressParser.m and
 *   XADNowCompressHandle.m having stood until then. **Nothing in this
 *   file rests on the reference any more**: the last two things that
 *   did — the offset-delta search and the code-length escape past 15 —
 *   were measured against the format's own decoder that day, by
 *   changing the field and handing the file back to Now Compress
 *   (tools/mutate_now.py, tools/vmac/nowcompress.py).
 *
 * The archive is a flat entry table, nested by a per-directory entry
 * count, followed by one compressed stream per FILE, and **a compressed
 * file is one of those with a single entry** — there is no second
 * layout to read. The reference treats the whole archive as ONE solid
 * stream and cuts entries out of it by (offset, length); it does not
 * have to. Each file's stream holds exactly that file's resource fork
 * followed by its data fork, in that order, so this reader decodes file
 * by file and never needs the solid abstraction — which is also what
 * lets it run in fixed memory.
 *
 * A stream is a table of blocks, each up to 32 KB of output, decoded
 * against a 32 KB sliding history.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define NOW_HISTORY   0x8000u     /* sliding history kept between blocks */
#define NOW_OUTBLOCK  0x10000u    /* history + one block's output       */
#define NOW_INBLOCK   0x8000u     /* staging for a block's input        */
#define NOW_ENTRY     110u        /* bytes per entry in the table       */
#define NOW_MAXBLOCKS 0x2000u     /* a table walk's sanity bound: 8,192
                                   * records is 64 KB of block table  */
#define NOW_MAXSYMS   0x122u      /* the largest alphabet: shape 3's main */
/* Block slots after the history, tried first and halved on refusal. Four
 * is where the tick probe put the knee on a 7 MHz Mac Plus: the window
 * slide was 19 % of the largest Now Compress run on Linux, and with four
 * slots derived-Expand_Now_1.0.1.sea's engine time fell 945 -> 793 ticks,
 * -16.1 %, for +32 B of code and 96 KB more of this one per-archive
 * allocation when the budget has it (DECISIONS.md 2026-09-19). UNC_HOT on
 * the three hot functions was measured on the same run and bought 0.3 %
 * for 1,152 B, so they are not marked. */
#define NOW_SLOTS     4u

/* ------------------------------------------------------------------ */
/* Bit input over a memory block, via the shared readers               */
/* ------------------------------------------------------------------ */

typedef struct NowBits {
    UncBufIn in;
    UncBitIn bi;
    uint32_t nbytes;
} NowBits;

static void now_bits_start(NowBits *b, const uint8_t *mem, uint32_t len)
{
    unc_bufin_init_mem(&b->in, mem, len);
    unc_bitin_init(&b->bi, &b->in);
    b->nbytes = len;
}

/* Bits consumed so far: what the byte reader has handed over, less what
 * the bit reader is still holding. */
static uint32_t now_bit_offset(const NowBits *b)
{
    /* unc_bufin_tell() reduces to `pos` here and is not called: a
     * NowBits is always memory-backed (now_bits_start), so lenfed ==
     * len and `lenfed - (len - pos)` is `pos`. This sits in the
     * condition of the two decode loops below and so runs once per
     * SYMBOL — two million times on
     * derived-SyntheticReferences2.0.sea, where computing it the long
     * way was 4.5 % of the run (DECISIONS.md 2026-08-27). */
    return b->in.pos * 8u - (uint32_t)b->bi.nbits;
}

/* ------------------------------------------------------------------ */
/* A Huffman-coded region                                             */
/* ------------------------------------------------------------------ */

/* Three things in this format are one thing: a Huffman-only block, the
 * stream under a shape-2 block, and the header a shape-3 block writes
 * its two code tables in. Each is a REGION laid out the same way
 * (docs/formats/now-compress.md, *Shape 2*, *Huffman alone*, *The
 * header*):
 *
 *   +0        the end flush: `(16 - it) mod 16` bits follow the last
 *             symbol, which is how much of the encoder's 16-bit
 *             register was still free when it stopped
 *   +1        the code, as `nsyms` four-bit lengths, high nibble first
 *   then      a count of "extra length" entries and that many symbol
 *             indices, each gaining 16 — the escape past the 15 four
 *             bits can hold
 *   then      a pad to an EVEN offset from the region's own start
 *   then      the symbols
 *
 * so one function reads all three and the caller does what it likes
 * with the symbols. **The escape is measured**, late and the hard way:
 * Now Compress will not write a code deeper than 15, so a block it did
 * write was re-coded here to use one and handed back to its own
 * Decompress, which returned every byte (docs/formats/now-compress.md,
 * *A code length past 15*). */
static int32_t now_huffman(const uint8_t *src, uint32_t srclen,
                           uint8_t *dst, uint32_t dstcap, int32_t nsyms,
                           UncCanon *code, int *err)
{
    uint8_t lengths[NOW_MAXSYMS];
    NowBits b;
    uint32_t at = 1, numbits;
    int32_t i, n, out = 0;
    int flush, e;

    *err = UNC_OK;
    if (nsyms > (int32_t)NOW_MAXSYMS) { *err = UNC_ERR_CORRUPT; return -1; }
    if (srclen < 1) { *err = UNC_ERR_TRUNCATED; return -1; }
    flush = src[0];

    for (i = 0; i < nsyms / 2; i++) {
        if (at >= srclen) { *err = UNC_ERR_TRUNCATED; return -1; }
        lengths[2 * i]     = (uint8_t)(src[at] >> 4);
        lengths[2 * i + 1] = (uint8_t)(src[at] & 0x0F);
        at++;
    }
    if (nsyms & 1) lengths[nsyms - 1] = 0;
    if (at >= srclen) { *err = UNC_ERR_TRUNCATED; return -1; }
    for (n = src[at++]; n > 0; n--) {
        if (at >= srclen) { *err = UNC_ERR_TRUNCATED; return -1; }
        lengths[src[at]] = (uint8_t)(lengths[src[at]] + 16u);
        at++;
    }
    if (at & 1) at++;               /* even, from the region's start */
    if (at > srclen) { *err = UNC_ERR_TRUNCATED; return -1; }

    numbits = (srclen - at) * 8u;
    if (flush) {
        if (numbits < (uint32_t)(16 - flush)) { *err = UNC_ERR_CORRUPT; return -1; }
        numbits -= (uint32_t)(16 - flush);
    }
    if ((e = unc_canon_build(code, lengths, nsyms)) != UNC_OK) {
        *err = e; return -1;
    }

    /* The region says where it ends; nothing in it says how many
     * symbols that is. **Everything this loop touches is a local**, and
     * that is not a style choice: the same code with the opening above
     * split into its own function — which reads better — cost 21 of 790
     * engine ticks on derived-Expand_Now_1.0.1.sea at 7 MHz, while x86
     * instruction counts said it was FASTER. It runs 32,768 times for a
     * full block (DECISIONS.md 2026-09-21, asking the program that
     * wrote it). */
    now_bits_start(&b, src + at, srclen - at);
    while (now_bit_offset(&b) < numbits) {
        int sym;
        if ((uint32_t)out >= dstcap) { *err = UNC_ERR_CORRUPT; return -1; }
        sym = unc_canon_decode(code, &b.bi);
        if (sym < 0) { *err = b.bi.err ? b.bi.err : UNC_ERR_CORRUPT; return -1; }
        dst[out++] = (uint8_t)sym;
    }
    if (now_bit_offset(&b) != numbits) { *err = UNC_ERR_CORRUPT; return -1; }
    return out;
}

/* The code tables a block needs, on the heap rather than on the frame.
 * An UncCanon is ~1.3 KB and a shape-3 block wants three of them at
 * once: 4,960 B in one chain, under unc_now_extract's own 1.2 KB, for
 * 5,632 B against CLAUDE.md's 4 KB call-depth rule (measured, m68k -Os
 * -fstack-usage). They ride in the same allocation as the block
 * buffers, and since 2026-09-21 so does the staging below — the file's
 * deepest chain is 1,648 B. */
struct NowCodes {
    UncCanon one, main, off;
    /* where a shape-3 header's 290 + 56 code lengths land on their way
     * into the two builds above: 346 bytes that were a frame in the
     * deepest chain in this file until they moved here */
    uint8_t  tables[0x122 + 0x38];
};

/* ------------------------------------------------------------------ */
/* The two LZSS variants                                              */
/* ------------------------------------------------------------------ */

/* Flag byte, MSB first: 1 = literal, 0 = a match whose offset is 13
 * bits split across two bytes and whose length is 3 bits, or a whole
 * byte when those 3 are zero. Source: docs/formats/now-compress.md,
 * *Shape 1* — where that rule is now measured rather than borrowed,
 * against shape 2's 1,340 match tokens whose offsets pass 255. */
static int32_t now_lzss(const uint8_t *src, uint32_t srclen,
                        uint8_t *dst, uint32_t dstcap, int *err)
{
    uint32_t at = 2;                /* the first two bytes are skipped */
    int32_t out = 0;
    int bits = 0, numbits = 0;

    *err = UNC_OK;
    while (at < srclen) {
        if (!numbits) {
            bits = src[at++];
            numbits = 8;
            if (at >= srclen) { *err = UNC_ERR_TRUNCATED; return -1; }
        }
        if (bits & 0x80) {
            if ((uint32_t)out >= dstcap) { *err = UNC_ERR_CORRUPT; return -1; }
            dst[out++] = src[at++];
        } else {
            uint32_t offset, length, i;
            int b1, b2;
            b1 = src[at++];
            if (at >= srclen) { *err = UNC_ERR_TRUNCATED; return -1; }
            b2 = src[at++];
            offset = (uint32_t)(((b1 & 0xF8) << 5) | b2);
            length = (uint32_t)(b1 & 0x07);
            if (!length) {
                if (at >= srclen) { *err = UNC_ERR_TRUNCATED; return -1; }
                length = src[at++];
            }
            length += 2;
            if (offset == 0 || (uint32_t)out < offset) {
                *err = UNC_ERR_CORRUPT; return -1;
            }
            for (i = 0; i < length; i++) {
                if ((uint32_t)out >= dstcap) { *err = UNC_ERR_CORRUPT; return -1; }
                dst[out] = dst[out - (int32_t)offset];
                out++;
            }
        }
        bits <<= 1;
        numbits--;
    }
    return out;
}

/* Source: docs/formats/now-compress.md, *Shape 3* — the same 88
 * numbers, derived from matches planted at a chosen length and
 * distance and compared with these arrays afterwards, disagreeing on
 * none of them (DECISIONS.md 2026-09-21, *the pair that never
 * repeats*). The values are the format's own, re-derived that way and
 * matched entry for entry; docs/formats/now-compress.md records them. */
static const uint8_t now_len_extra[0x22] = {
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    1,1,2,2,2,2,2,3, 3,3,4,4,4,4,5,5, 5,5
};
static const uint16_t now_len_base[0x22] = {
    0x0000,0x0001,0x0002,0x0003,0x0004,0x0005,0x0006,0x0007,
    0x0008,0x0009,0x000a,0x000b,0x000c,0x000d,0x000e,0x000f,
    0x0010,0x0012,0x0014,0x0018,0x001c,0x0020,0x0024,0x0028,
    0x0030,0x0038,0x0040,0x0050,0x0060,0x0070,0x0080,0x00a0,
    0x00c0,0x00e0
};
static const uint8_t now_off_extra[0x38] = {
    0,0,0,0,0,0,0,0, 1,1,1,1,2,2,2,2,
    3,3,3,3,4,4,4,4, 5,5,5,5,8,8,8,8,
    8,8,8,8,9,9,9,9, 10,10,10,10,11,11,11,11,
    12,12,12,12,13,13,13,13
};
static const uint16_t now_off_base[0x38] = {
    0x0000,0x0001,0x0002,0x0003,0x0004,0x0005,0x0006,0x0007,
    0x0008,0x000a,0x000c,0x000e,0x0010,0x0014,0x0018,0x001c,
    0x0020,0x0028,0x0030,0x0038,0x0040,0x0050,0x0060,0x0070,
    0x0080,0x00a0,0x00c0,0x00e0,0x0100,0x0200,0x0300,0x0400,
    0x0500,0x0600,0x0700,0x0800,0x0900,0x0b00,0x0d00,0x0f00,
    0x1100,0x1500,0x1900,0x1d00,0x2100,0x2900,0x3100,0x3900,
    0x4100,0x5100,0x6100,0x7100,0x8100,0xa100,0xc100,0xe100
};

/* `base` is where matches may reach back to (the history), `dst` where
 * this block's output starts. Source: docs/formats/now-compress.md,
 * *Shape 3* — its tokens, both alphabets, and the window that spans
 * members. */
/* A shape-3 block's two code tables, out of the Huffman-coded region
 * that starts at byte 4: 290 code lengths for the main alphabet, then
 * 56 for the distance classes, each of those stored as its code length
 * PLUS TWO. Twenty symbols code them, because that plus-two runs the
 * values to 19. Source: docs/formats/now-compress.md, *The header*. */
static int now_tables(const uint8_t *src, uint32_t headersize,
                      struct NowCodes *cd)
{
    uint8_t *t = cd->tables;
    int32_t i, n;
    int e;

    n = now_huffman(src, headersize, t, (uint32_t)sizeof cd->tables, 20,
                    &cd->one, &e);
    if (n < 0) return e;
    /* 290 + 56 is the whole region: the two tables are all it carries */
    if (n != (int32_t)sizeof cd->tables) return UNC_ERR_CORRUPT;

    if ((e = unc_canon_build(&cd->main, t, 0x122)) != UNC_OK) return e;
    for (i = 0; i < 0x38; i++)
        t[i] = t[i + 0x122] ? (uint8_t)(t[i + 0x122] - 2) : 0;
    return unc_canon_build(&cd->off, t, 0x38);
}

static int32_t now_newlzss(const uint8_t *src, uint32_t srclen,
                           uint8_t *base, uint8_t *dst, uint32_t dstcap,
                           struct NowCodes *cd, int *err)
{
    NowBits b;
    uint32_t at, headersize, numbits;
    int32_t out = 0;
    int sym, e;

    *err = UNC_OK;
    /* The header, which is a size and three flush counts. Bytes 0..1
     * are 0x2F59 plus the length of the coded region that follows;
     * **byte 2 is read by nothing** — not here, not in the format's own
     * decoder (docs/formats/now-compress.md, *The header*); byte 3 is
     * this block's own end flush, and from byte 4 comes the region the
     * two code tables ride in. */
    if (srclen < 4) { *err = UNC_ERR_TRUNCATED; return -1; }
    headersize = (uint32_t)((unc_get_u16be(src) - 0x2F59u) & 0xFFFFu);
    at = 4;
    if (headersize > srclen - at) { *err = UNC_ERR_TRUNCATED; return -1; }
    if ((e = now_tables(src + at, headersize, cd)) != UNC_OK) {
        *err = e; return -1;
    }

    at += headersize;
    if (at & 1) at++;                       /* the stream starts even */
    if (at > srclen) { *err = UNC_ERR_TRUNCATED; return -1; }

    /* Then the stream, where the header says, running to the bit byte 3
     * names. A symbol below 256 is a literal; 257..289 is a match — its
     * length class, that class's extra bits, a distance symbol and that
     * class's extra bits. The window spans members, which is what
     * `base` bounds. */
    numbits = (srclen - at) * 8u;
    if (src[3]) {
        if (numbits < (uint32_t)(16 - src[3])) {
            *err = UNC_ERR_CORRUPT; return -1;
        }
        numbits -= (uint32_t)(16 - src[3]);
    }
    now_bits_start(&b, src + at, srclen - at);

    while (now_bit_offset(&b) < numbits) {
        uint32_t length, offset, k;
        int sel;
        sym = unc_canon_decode(&cd->main, &b.bi);
        if (sym < 0) { *err = b.bi.err ? b.bi.err : UNC_ERR_CORRUPT;
                       return -1; }
        if (sym < 0x100) {
            if ((uint32_t)out >= dstcap) { *err = UNC_ERR_CORRUPT; return -1; }
            dst[out++] = (uint8_t)sym;
            continue;
        }
        sel = sym - 0x100;
        if (sel >= 0x22) { *err = UNC_ERR_CORRUPT; return -1; }
        length = now_len_base[sel];
        if (now_len_extra[sel]) {
            int32_t extra = unc_bitin_bits(&b.bi, now_len_extra[sel]);
            if (extra < 0) { *err = b.bi.err; return -1; }
            length += (uint32_t)extra;
        }
        length += 2;

        sel = unc_canon_decode(&cd->off, &b.bi);
        if (sel < 0) { *err = b.bi.err ? b.bi.err : UNC_ERR_CORRUPT;
                       return -1; }
        if (sel >= 0x38) { *err = UNC_ERR_CORRUPT; return -1; }
        offset = now_off_base[sel];
        if (now_off_extra[sel]) {
            int32_t extra = unc_bitin_bits(&b.bi, now_off_extra[sel]);
            if (extra < 0) { *err = b.bi.err; return -1; }
            offset += (uint32_t)extra;
        }

        if ((uint32_t)out + length > dstcap) { *err = UNC_ERR_CORRUPT; return -1; }
        if (dst + out - offset < base) { *err = UNC_ERR_CORRUPT; return -1; }
        for (k = 0; k < length; k++) {
            dst[out] = dst[out - (int32_t)offset];
            out++;
        }
    }
    return out;
}

/* ------------------------------------------------------------------ */
/* One file's stream of blocks                                        */
/* ------------------------------------------------------------------ */

typedef struct NowStream {
    UncCtx  *c;
    struct NowCodes *cd;   /* code tables, off the stack — see below */
    uint8_t *inblock;      /* [incap]                                    */
    uint8_t *outblock;     /* [hist + outcap]                            */
    uint8_t *dict;         /* [hist]                                     */
    /* Blocks are decoded one after another at `outpos`, so that each
     * one's history is simply the bytes before it, and the window slides
     * only when the next block would not fit — once per `outcap / blkcap`
     * blocks rather than once per block. See now_next_block. */
    uint32_t outcap;       /* bytes after the history: slots * blkcap    */
    uint32_t outpos;       /* where the next block decodes, >= hist      */
    /* Sized from the archive's largest fork rather than from the
     * format's ceilings — see unc_now_extract. hist <= NOW_HISTORY and
     * blkcap <= st->blkcap, always. */
    uint32_t hist;
    uint32_t blkcap;
    uint32_t incap;
    /* Where the current block's output sits and how much is left of it,
     * so a fork can be served across block boundaries. */
    uint8_t *avail;
    uint32_t availlen;
    /* Block table walk. */
    uint32_t tableat;      /* file offset of the next table entry */
    uint32_t entriesleft;
    uint32_t lastoffset;
    int32_t  delta;
    int      nextisstart;
    int      done;
} NowStream;

static int now_read_u32(UncCtx *c, uint32_t at, uint32_t *out)
{
    uint8_t b[4];
    if (c->io->seek(c->io->ctx, at) < 0) return UNC_ERR_IO;
    if (unc_read_full(c->io, b, 4) != UNC_OK) return UNC_ERR_TRUNCATED;
    *out = unc_get_u32be(b);
    return UNC_OK;
}

/* A block table's offsets are sometimes all short by a constant. Walk
 * the table until a 4-byte field equals the running sum of everything
 * before it — which is where the table's checksum sits, so that
 * position is the table's true end — and the difference from the offset
 * the header states is the constant.
 *
 * Source: docs/formats/now-compress.md, *The archive layer*, where the
 * checksum is measured on 108 members and the correction on
 * 2026-09-21: an archive rebased by 100 here, with that checksum
 * recomputed, comes out of its OWN self-extractor byte for byte, and
 * out of this engine not at all when this function is made to return 0
 * (tools/mutate_now.py --delta). No file the encoder wrote needs it;
 * the archives that exercise it in ci.sh are written by
 * tools/synth_now.py for that purpose. */
/* The sum of `n` bytes: what every one of this format's four checksums
 * is made of (docs/formats/now-compress.md). */
static uint32_t now_sum(const uint8_t *p, int n)
{
    uint32_t sum = 0;
    while (n-- > 0) sum += *p++;
    return sum;
}

static int32_t now_find_delta(UncCtx *c, uint32_t start, uint32_t first)
{
    uint8_t buf[8];
    uint32_t sum = 0, n;
    int i;

    if (c->io->seek(c->io->ctx, start) < 0) return 0;
    /* the u32 and one record: the least a table can hold */
    for (i = 0; i < 4; i++) {
        if (unc_read_full(c->io, buf, 4) != UNC_OK) return 0;
        sum += now_sum(buf, 4);
    }
    for (n = 2; n < NOW_MAXBLOCKS; n++) {
        if (unc_read_full(c->io, buf, 4) != UNC_OK) return 0;
        if (unc_get_u32be(buf) == sum)          /* the table ends here */
            return (int32_t)(start + n * 8u + 4u) - (int32_t)first;
        sum += now_sum(buf, 4);
        if (unc_read_full(c->io, buf, 4) != UNC_OK) return 0;
        sum += now_sum(buf, 4);
    }
    return 0;
}

/* Count a member's block records and check the table against itself.
 *
 * Source: docs/formats/now-compress.md, *A member's blocks* — the data
 * area opens with a u32 saying where the first block begins, which is
 * also where the table ends, so `(first - start - 4) / 8 - 1` records
 * of eight bytes lie between; then four bytes, then a u32 equal to the
 * sum of every byte of the data area before it. That sum agrees on all
 * 108 members measured there, this project's own synthetic archives
 * included. */
static int now_check_table(UncCtx *c, uint32_t start, uint32_t first,
                           int32_t delta, uint32_t *nrecs_out)
{
    uint8_t buf[8];
    uint32_t sum;
    int32_t nrecs, i;

    nrecs = ((int32_t)(first + (uint32_t)delta - start) - 4) / 8 - 1;
    if (nrecs < 0 || (uint32_t)nrecs > NOW_MAXBLOCKS) return UNC_ERR_CORRUPT;

    /* the u32 is the first thing summed, and it is summed as it is
     * STORED — short by the delta, where there is one */
    unc_put_u32be(buf, first);
    sum = now_sum(buf, 4);
    if (c->io->seek(c->io->ctx, start + 4) < 0) return UNC_ERR_IO;

    for (i = 0; i < nrecs; i++) {
        if (unc_read_full(c->io, buf, 8) != UNC_OK) return UNC_ERR_TRUNCATED;
        sum += now_sum(buf, 8);
    }
    if (unc_read_full(c->io, buf, 8) != UNC_OK) return UNC_ERR_TRUNCATED;
    sum += now_sum(buf, 4);
    if (sum != unc_get_u32be(buf + 4)) return UNC_ERR_CORRUPT;

    *nrecs_out = (uint32_t)nrecs;
    return UNC_OK;
}

/* Position the walk at a file's block table. */
static int now_stream_open(NowStream *st, uint32_t headeroffset)
{
    uint32_t firstoffset, n;
    int32_t delta = 0;
    int err;

    if ((err = now_read_u32(st->c, headeroffset, &firstoffset)) != UNC_OK)
        return err;

    if (firstoffset < headeroffset + 20) {
        delta = now_find_delta(st->c, headeroffset, firstoffset);
        err = now_check_table(st->c, headeroffset, firstoffset, delta, &n);
    } else {
        err = now_check_table(st->c, headeroffset, firstoffset, 0, &n);
        if (err != UNC_OK) {
            delta = now_find_delta(st->c, headeroffset, firstoffset);
            err = now_check_table(st->c, headeroffset, firstoffset, delta, &n);
        }
    }
    if (err != UNC_OK) return err;

    st->tableat = headeroffset + 4;
    st->entriesleft = n;
    st->lastoffset = firstoffset;
    st->delta = delta;
    st->nextisstart = 1;
    st->availlen = 0;
    st->done = 0;
    return UNC_OK;
}

/* Decode the next block of the current stream into st->avail.
 * Source: docs/formats/now-compress.md — the block table's records
 * (offset, flags, padding), the repeated offset that starts a stream,
 * and the four shapes a block can be. There is exactly one such
 * repeated offset per member and it is the boundary between its two
 * forks, so it is first when the resource fork is empty and last when
 * the data fork is; a member's first block starts a stream either way. */
static int now_next_block(NowStream *st)
{
    UncCtx *c = st->c;
    uint8_t rec[8];
    uint8_t *outstart;
    uint32_t offset, length, i;
    int32_t out;
    int flags, first, err;

    /* The window slides by the block's length: what was written at
     * outstart ends up just below it, and the last 32 KB become the
     * history for the next block. Done HERE, before the next block, and
     * only when that block would not fit after the last one — the
     * previous block has been served in full by then (now_fork drains
     * `avail` before asking for another), so nothing live is moved.
     * With one slot this runs every block, as it always did; with more
     * it runs once per slot-full, and the copy was 19 % of the largest
     * run in the corpus (callgrind, 2026-09-18). */
    if (st->outpos + st->blkcap > st->hist + st->outcap) {
        uint8_t *from = st->outblock + st->outpos - st->hist;
        for (i = 0; i < st->hist; i++) st->outblock[i] = from[i];
        st->outpos = st->hist;
    }
    outstart = st->outblock + st->outpos;

    for (;;) {
        uint32_t nextoffset, padding;
        if (st->entriesleft == 0) { st->done = 1; return UNC_OK; }
        if (c->io->seek(c->io->ctx, st->tableat) < 0) return UNC_ERR_IO;
        if (unc_read_full(c->io, rec, 8) != UNC_OK) return UNC_ERR_TRUNCATED;
        st->tableat += 8;
        st->entriesleft--;
        flags = (int)unc_get_u16be(rec);
        padding = unc_get_u16be(rec + 2);
        nextoffset = unc_get_u32be(rec + 4);
        if (nextoffset == st->lastoffset) { st->nextisstart = 1; continue; }
        if (nextoffset < st->lastoffset + padding + 4) return UNC_ERR_CORRUPT;
        offset = (uint32_t)((int32_t)st->lastoffset + st->delta);
        length = nextoffset - st->lastoffset - padding - 4;
        first = st->nextisstart;
        st->lastoffset = nextoffset;
        st->nextisstart = 0;
        break;
    }

    if (length > st->incap) return UNC_ERR_CORRUPT;

    /* A block that starts a stream reaches back into the history the
     * PREVIOUS stream left behind. The reference calls this absurd and
     * does it anyway; so do we, because the bytes require it. */
    if (first) {
        uint8_t *hist = outstart - st->hist;
        for (i = 0; i < st->hist; i++) hist[i] = st->dict[i];
    }

    if (c->io->seek(c->io->ctx, offset) < 0) return UNC_ERR_IO;

    /* The stored path and the Huffman-then-LZSS path stage their raw
     * input in `outstart` itself, and the room there is `blkcap` — the
     * bound every decoder below writes to. `length` is a block's
     * COMPRESSED length, checked only against `incap` above, so a
     * crafted block can name a length far larger than the fork it
     * belongs to declared; without this a stored or shape-2 block of up
     * to `incap` bytes overruns `outstart`. The three paths that read
     * into `st->inblock` (incap) are already covered by that check. */
    if (flags & 0x20) {
        if (flags & 0x1F) {                       /* Huffman, then LZSS */
            int32_t mid;
            if (length > st->blkcap) return UNC_ERR_CORRUPT;
            if (unc_read_full(c->io, outstart, (int32_t)length) != UNC_OK)
                return UNC_ERR_TRUNCATED;
            mid = now_huffman(outstart, length, st->inblock, st->incap,
                              0x100, &st->cd->one, &err);
            if (mid < 0) return err;
            out = now_lzss(st->inblock, (uint32_t)mid, outstart,
                           st->blkcap, &err);
        } else {                                  /* Huffman only */
            if (unc_read_full(c->io, st->inblock, (int32_t)length) != UNC_OK)
                return UNC_ERR_TRUNCATED;
            out = now_huffman(st->inblock, length, outstart,
                              st->blkcap, 0x100,
                              &st->cd->one, &err);
        }
    } else if (flags & 0x40) {                    /* new LZSS */
        if (unc_read_full(c->io, st->inblock, (int32_t)length) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        out = now_newlzss(st->inblock, length, outstart - st->hist, outstart,
                          st->blkcap, st->cd, &err);
    } else if (flags & 0x1F) {                    /* LZSS only */
        if (unc_read_full(c->io, st->inblock, (int32_t)length) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        out = now_lzss(st->inblock, length, outstart,
                       st->blkcap, &err);
    } else {                                      /* stored */
        if (length > st->blkcap) return UNC_ERR_CORRUPT;
        if (unc_read_full(c->io, outstart, (int32_t)length) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        out = (int32_t)length;
        err = UNC_OK;
    }
    if (out < 0) return err;

    /* One tick per block. This reader seeks to each block and pulls it
     * whole with unc_read_full, which is the raw UncIO and not the
     * shared buffered reader — the only thing in the engine that drives
     * the progress pump. So until 2026-08-28 Now Compress never called
     * the progress callback AT ALL, against the contract in
     * include/macextract.h, and on the Mac that froze the progress
     * dialog at 0 % and put both Cancel routes out of reach for the
     * whole extraction: measured on Mac OS 9, where three Cmd-. in
     * twenty seconds did nothing to a 9.9 MB entry (DECISIONS.md
     * 2026-08-28). A block's input is at most NOW_INBLOCK. */
    err = unc_progress_add(&c->ps, length);
    if (err != UNC_OK) return err;

    /* The dictionary cache the NEXT stream starts from is the last
     * `hist` bytes ending where this block ends, history included when
     * the block is shorter than that. */
    if (first) {
        const uint8_t *tail = outstart + (uint32_t)out - st->hist;
        for (i = 0; i < st->hist; i++) st->dict[i] = tail[i];
    }

    st->avail = outstart;
    st->availlen = (uint32_t)out;
    st->outpos += (uint32_t)out;
    return UNC_OK;
}

/* Serve `want` bytes of the current stream into a fork. */
static int now_fork(NowStream *st, UncFork fork, uint32_t want)
{
    UncCtx *c = st->c;
    int err;

    while (want > 0) {
        uint32_t n;
        if (st->availlen == 0) {
            if ((err = now_next_block(st)) != UNC_OK) return err;
            if (st->done) return UNC_ERR_TRUNCATED;
            continue;
        }
        n = st->availlen < want ? st->availlen : want;
        if (!c->opt.test_only && !c->opt.list_only &&
            c->sink->write(c->sink->ctx, fork, st->avail, (int32_t)n) < 0)
            return UNC_ERR_SINK;
        st->avail += n;
        st->availlen -= n;
        want -= n;
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* The entry table                                                    */
/* ------------------------------------------------------------------ */

int unc_now_extract(UncCtx *c)
{
    uint8_t hdr[NOW_ENTRY];
    UncPath path;
    /* Entries still owed at each level, which is Now Compress's own
     * way of closing a folder and not part of the shared path. */
    uint32_t owed[UNC_PATH_MAXDEPTH];
    /* And still owed by all the levels past UNC_PATH_MAXDEPTH together,
     * which have no slot of their own; see the walk below. */
    uint32_t deepowed = 0;
    NowStream st;
    uint8_t *mem;
    uint32_t totalentries, seen = 0, at = 24;
    int err = UNC_OK;

    if (c->io->seek(c->io->ctx, 8) < 0) return UNC_ERR_IO;
    if (unc_read_full(c->io, hdr, 4) != UNC_OK) return UNC_ERR_FORMAT;
    totalentries = unc_get_u32be(hdr);
    if (totalentries == 0 || totalentries > 0xFFFFu) return UNC_ERR_FORMAT;

    /* Size the block buffers from the archive's LARGEST FORK, not from
     * the format's three ceilings.
     *
     * This allocation happens once per archive, before a single entry is
     * read, and at the ceilings it is 131,072 B. That is not headroom
     * anybody was spending: a Macintosh application's heap is its
     * MultiFinder partition, `macextract.r` declares a 400 KB minimum, and
     * 150 KB of that partition is the application's own code. Measured at
     * a 110,000 B budget — about what the minimum partition leaves — Now
     * Compress opened NONE of its three fixtures, refused at this line
     * with a high-water of zero. A per-archive allocation that fails is
     * also the one shape the engine's contract does not allow: allocation
     * failure is supposed to be per ENTRY.
     *
     * The entry table carries each fork's uncompressed size at +86 and
     * +90, and ONE STREAM CARRIES BOTH FORKS — resource first, then data
     * — so the bound is their SUM, not the larger of the two. (Learned
     * from a unit test: a stream of one 11-byte block holding a 5-byte
     * resource fork and a 6-byte data fork overran a capacity of 6.)
     * One pass over the table bounds all three:
     *
     *   hist   <= NOW_HISTORY, and a back-reference cannot reach further
     *            back than the ARCHIVE has produced, so <= the sum of
     *            every fork too. **Not the largest fork**: a stream's
     *            first block reaches into the history the PREVIOUS
     *            stream left behind (now_next_block, `first`), so a
     *            match in the third member can name an offset longer
     *            than any one fork in the file. Bounding this by
     *            `maxout` refused two members of a four-member archive
     *            Now Compress itself wrote, with offsets 6,228 and
     *            13,000 against a 6,000-byte window
     *            (BLOCKERS.md, *Withdrawn claims*)
     *   blkcap <= NOW_OUTBLOCK - NOW_HISTORY, and one block's output is
     *            part of a fork, so <= maxout
     *   incap  is left at NOW_INBLOCK: a block's COMPRESSED length is not
     *            bounded by its output, and `length > incap` is a
     *            corruption test, so shrinking it could refuse a valid
     *            archive. 32 KB of the 128 stays.
     *
     * The tables go FIRST so their alignment is the allocator's own, and
     * everything after them is bytes. */
    {
        uint32_t maxout = 0, totalout = 0, i, scanat = at, left = totalentries;
        while (left-- > 0) {
            uint32_t d, r;
            if (c->io->seek(c->io->ctx, scanat) < 0) return UNC_ERR_IO;
            if (unc_read_full(c->io, hdr, NOW_ENTRY) != UNC_OK) break;
            scanat += NOW_ENTRY;
            d = unc_get_u32be(hdr + 86);
            r = unc_get_u32be(hdr + 90);
            /* Saturate rather than wrap: a damaged header can declare
             * anything, and the two ceilings below clamp it anyway. */
            if (d > UNC_U32_MAX - r) d = UNC_U32_MAX - r;
            if (d + r > maxout) maxout = d + r;
            /* Clamp BEFORE adding: a damaged header can declare a
             * fork of 4 GB, and `totalout += d + r` wraps to a small
             * number that would size the window too SHORT. */
            if (totalout < NOW_HISTORY) {
                if (d + r > NOW_HISTORY - totalout) totalout = NOW_HISTORY;
                else totalout += d + r;
            }
        }
        st.hist   = totalout < NOW_HISTORY ? totalout : NOW_HISTORY;
        st.blkcap = maxout < (NOW_OUTBLOCK - NOW_HISTORY)
                    ? maxout : (NOW_OUTBLOCK - NOW_HISTORY);
        st.incap  = NOW_INBLOCK;
        /* A zero-length archive still needs somewhere to decode into. */
        if (st.blkcap == 0) st.blkcap = 1;

        /* Listing needs none of this, and a failure to get it is NOT the
         * archive's failure.
         *
         * This is the engine's only per-ARCHIVE allocation, and the
         * contract is that allocation failure is per entry, never per
         * archive (CLAUDE.md, 68000 discipline). Returning UNC_ERR_MEM
         * here refused the whole archive — no listing, no entry names,
         * nothing — and it made this one buffer the floor for whether
         * ANY Now archive opens at all: 137,264 B, against a 158,970 B
         * budget in the 400 KB minimum partition. Twenty-two kilobytes
         * of headroom, on an application that grew twenty-four in two
         * versions. Now the entries are still walked and named, and each
         * one that needs the buffer fails on its own. */
        /* Room for several blocks after the history, so the window slides
         * once per slot-full instead of once per block (now_next_block).
         * NOW_SLOTS first, then fewer, then one — the shape the archive
         * always had — so a small machine pays nothing it cannot afford:
         * every extra slot is blkcap more of this one per-archive
         * allocation, 32 KB at the ceiling. Bought for the largest run in
         * the corpus, where the slide was 19 % (DECISIONS.md 2026-09-19). */
        mem = NULL;
        st.outcap = st.blkcap;
        if (!c->opt.list_only) {
            uint32_t slots;
            for (slots = NOW_SLOTS; slots >= 1; slots >>= 1) {
                st.outcap = slots * st.blkcap;
                mem = (uint8_t *)unc_alloc(c->al, (uint32_t)sizeof *st.cd
                                           + st.incap + st.hist + st.outcap
                                           + st.hist);
                if (mem) break;
            }
        }
        st.c = c;
        st.outpos = st.hist;
        if (mem) {
            st.cd       = (struct NowCodes *)(void *)mem;
            st.inblock  = mem + sizeof *st.cd;
            st.outblock = st.inblock + st.incap;
            st.dict     = st.outblock + st.hist + st.outcap;
            for (i = 0; i < st.hist; i++) st.dict[i] = 0;
        } else {
            st.cd = NULL;
            st.inblock = st.outblock = st.dict = NULL;
        }
    }

    unc_path_init(&path, c);

    while (seen < totalentries) {
        UncEntryInfo e;
        uint32_t nlen, datasize, rsrcsize, datastart, numdir;
        int flags, sret, deep;

        if (c->io->seek(c->io->ctx, at) < 0) { err = UNC_ERR_IO; break; }
        if (unc_read_full(c->io, hdr, NOW_ENTRY) != UNC_OK) break;
        at += NOW_ENTRY;
        seen++;

        nlen = hdr[0];
        if (nlen > 31) nlen = 31;
        flags     = (int)unc_get_u16be(hdr + 36);
        datasize  = unc_get_u32be(hdr + 86);
        rsrcsize  = unc_get_u32be(hdr + 90);
        datastart = unc_get_u32be(hdr + 98);
        numdir    = unc_get_u16be(hdr + 82);

        unc_entry_clear(&e);
        unc_path_leaf(&path, &e, hdr + 1, nlen);
        deep = unc_path_toodeep(&path);
        e.type         = unc_get_u32be(hdr + 38);
        e.creator      = unc_get_u32be(hdr + 42);
        e.finder_flags = unc_get_u16be(hdr + 46);
        e.create_date  = unc_get_u32be(hdr + 54);
        e.mod_date     = unc_get_u32be(hdr + 58);

        if (flags & 0x10) {                       /* directory */
            e.is_dir = 1;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0 &&
                c->sink->end_entry(c->sink->ctx,
                                   deep ? UNC_ERR_TOODEEP : UNC_OK) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
        } else {
            e.data_size = datasize;
            e.rsrc_size = rsrcsize;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0) {
                int ferr = UNC_OK;
                if (deep) {
                    ferr = UNC_ERR_TOODEEP;   /* per entry, like the above */
                } else if (!c->opt.list_only && (datasize || rsrcsize) &&
                    st.inblock == NULL) {
                    ferr = UNC_ERR_MEM;       /* per entry, not per archive */
                } else if (!c->opt.list_only && (datasize || rsrcsize)) {
                    ferr = now_stream_open(&st, datastart);
                    /* The forks come out of the stream in the order the
                     * archive stores them: resource first, then data. */
                    if (ferr == UNC_OK && rsrcsize)
                        ferr = now_fork(&st, UNC_FORK_RSRC, rsrcsize);
                    if (ferr == UNC_OK && datasize)
                        ferr = now_fork(&st, UNC_FORK_DATA, datasize);
                }
                if (c->sink->end_entry(c->sink->ctx, ferr) < 0) {
                    err = UNC_ERR_SINK;
                    break;
                }
                if (unc_fatal(ferr)) {
                    err = ferr;
                    break;
                }
            }
        }

        /* This entry counts against the directory it is in; a directory
         * then opens one of its own. Levels close when their count runs
         * out, which is how an empty folder closes immediately.
         * Source: docs/formats/now-compress.md, *The archive layer* —
         * a directory is flagged by bit 0x10 at +36 and says at +82 how
         * many entries follow it; the reference does the same by
         * recursing (parseDirectoryWithParent).
         *
         * A level past UNC_PATH_MAXDEPTH has no slot of its own, so the
         * counts of all the refused ones are summed into `deepowed`. The
         * sum telescopes — every entry is owed by exactly one level, and a
         * refused folder adds its own count the same way a real one does —
         * so the chain is exhausted at the same entry a stack of counters
         * would have exhausted it at. What it cannot say is WHICH refused
         * level each entry belonged to, which is the thing this walk could
         * not represent in the first place. */
        if (unc_path_toodeep(&path)) {
            if (deepowed > 0) deepowed--;
        } else if (path.depth > 0 && owed[path.depth - 1] > 0) {
            owed[path.depth - 1]--;
        }

        if (flags & 0x10) {
            if (unc_path_push(&path, hdr + 1, nlen) == UNC_OK)
                owed[path.depth - 1] = numdir;
            else
                deepowed += numdir;
        }

        /* The refused chain closes first, and the real levels only once it
         * has: a level whose count ran out while the walk was still below
         * the limit must wait, or the pop lands on the refusal instead and
         * the walk comes back up one level short of where it went down. */
        while (unc_path_toodeep(&path) && deepowed == 0)
            unc_path_pop(&path);
        if (!unc_path_toodeep(&path))
            while (path.depth > 0 && owed[path.depth - 1] == 0)
                unc_path_pop(&path);
    }

    unc_free(c->al, mem);
    return err;
}

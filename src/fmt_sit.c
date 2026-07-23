/*
 * fmt_sit.c — StuffIt classic (1.5.1–4.x) container, methods 0/1/2/3
 * in M5; further methods land with M6.
 *
 * Sources: reference/XADMaster/XADStuffItParser.m (header layout,
 * SITFH_* offsets, folder markers), XADRLE90Handle.m,
 * XADCompressHandle.m, XADStuffItHuffmanHandle.m, and
 * reference/macutils/macunpack/sit.c — LGPL, see NOTICE.
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
 * mode), 3 Huffman (bit-serialized tree), 5 LZAH, 8 MW, 13
 * LZSS+Huffman, 14 installer, 15 Arsenic.
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

int unc_sit_probe(const uint8_t *head, int32_t len)
{
    /* Source: XADStuffItParser.m recognizeFileWithHandle. */
    if (len < 14) return 0;
    if (unc_get_u32be(head + 10) != 0x724c6175u) return 0;   /* 'rLau' */
    if (unc_get_u32be(head) == 0x53495421u) return 1;        /* 'SIT!' */
    if (head[0] == 'S' && head[1] == 'T') {                  /* installers */
        if (head[2] == 'i' &&
            (head[3] == 'n' || (head[3] >= '0' && head[3] <= '9'))) return 1;
        if (head[2] >= '0' && head[2] <= '9' &&
            head[3] >= '0' && head[3] <= '9') return 1;
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* Per-method fork decoders. Each writes exactly outlen decoded bytes */
/* (through obuf) to the sink and accumulates the CRC-16/ARC.         */
/* ------------------------------------------------------------------ */

typedef struct SitFork {
    UncCtx  *c;
    UncFork  fork;
    uint16_t crc;
    uint8_t *obuf;
    uint32_t ocap, olen;
} SitFork;

static int sit_flush(SitFork *f)
{
    if (f->olen == 0) return UNC_OK;
    f->crc = unc_crc16_arc(f->crc, f->obuf, (int32_t)f->olen);
    if (!f->c->opt.test_only &&
        f->c->sink->write(f->c->sink->ctx, f->fork, f->obuf,
                          (int32_t)f->olen) < 0)
        return UNC_ERR_SINK;
    f->olen = 0;
    return UNC_OK;
}

static int sit_put(SitFork *f, uint8_t b)
{
    f->obuf[f->olen++] = b;
    if (f->olen == f->ocap) return sit_flush(f);
    return UNC_OK;
}

/* Method 0: stored. */
static int sit_store(SitFork *f, UncBufIn *in, uint32_t outlen)
{
    uint32_t i;
    for (i = 0; i < outlen; i++) {
        int b = unc_bufin_next(in);
        if (b < 0) return in->err;
        if (sit_put(f, (uint8_t)b) != UNC_OK) return UNC_ERR_SINK;
    }
    return UNC_OK;
}

/* Method 1: RLE90 — 0x90 0x00 is a literal 0x90; 0x90 n>=2 repeats
 * the previous byte n-1 more times; 0x90 0x01 is illegal.
 * Source: XADRLE90Handle.m. */
static int sit_rle90(SitFork *f, UncBufIn *in, uint32_t outlen)
{
    uint32_t left = outlen;
    uint8_t repeated = 0;
    while (left > 0) {
        int b = unc_bufin_next(in);
        if (b < 0) return in->err;
        if (b != 0x90) {
            repeated = (uint8_t)b;
            if (sit_put(f, repeated) != UNC_OK) return UNC_ERR_SINK;
            left--;
        } else {
            int c = unc_bufin_next(in);
            if (c < 0) return in->err;
            if (c == 0) {
                repeated = 0x90;
                if (sit_put(f, repeated) != UNC_OK) return UNC_ERR_SINK;
                left--;
            } else if (c == 1) {
                return UNC_ERR_CORRUPT;
            } else {
                uint32_t n = (uint32_t)c - 1;
                while (n-- > 0 && left > 0) {
                    if (sit_put(f, repeated) != UNC_OK) return UNC_ERR_SINK;
                    left--;
                }
            }
        }
    }
    return UNC_OK;
}

/* Method 2: compress LZW, 14-bit codes, block mode (flags 0x8e in
 * XADStuffItParser.m). */
static int sit_lzw(SitFork *f, UncBufIn *in, uint32_t outlen, UncAlloc *al)
{
    UncLzw z;
    uint32_t left = outlen;
    int err = unc_lzw_init(&z, al, in, 14, 1);
    if (err != UNC_OK) return err;
    while (left > 0) {
        uint32_t space = f->ocap - f->olen;
        int32_t want = left < space ? (int32_t)left : (int32_t)space;
        int32_t got = unc_lzw_read(&z, f->obuf + f->olen, want);
        if (got < 0) { err = (int)got; goto out; }
        if (got == 0) { err = UNC_ERR_TRUNCATED; goto out; }
        f->olen += (uint32_t)got;
        left -= (uint32_t)got;
        if (f->olen == f->ocap && (err = sit_flush(f)) != UNC_OK) goto out;
    }
out:
    unc_lzw_free(&z, al);
    return err;
}

/* Method 3: Huffman with the bit-serialized tree (shared with
 * PackIt; source XADStuffItHuffmanHandle.m). */
static int sit_huffman(SitFork *f, UncBufIn *in, uint32_t outlen,
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
            if (sit_put(f, (uint8_t)sym) != UNC_OK) { err = UNC_ERR_SINK; break; }
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
/* Source: reference/XADMaster/XADStuffIt13Handle.m — LGPL, NOTICE.   */
/* ------------------------------------------------------------------ */

#include "sit13_tables.h"

#define SIT13_WINDOW 65536u

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

static int sit13_fork(SitFork *f, UncBufIn *in, uint32_t outlen,
                      UncAlloc *al)
{
    Sit13 *hz;
    uint8_t *window;
    UncBitIn bi;
    UncCanon *curr, *second;
    uint32_t pos = 0;
    int err = UNC_OK;
    int val, sel;

    hz = (Sit13 *)unc_alloc(al, (uint32_t)sizeof *hz);
    if (!hz) return UNC_ERR_MEM;
    window = (uint8_t *)unc_alloc(al, SIT13_WINDOW);
    if (!window) { unc_free(al, hz); return UNC_ERR_MEM; }
    {
        uint32_t i;
        for (i = 0; i < SIT13_WINDOW; i++) window[i] = 0;
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
    while (pos < outlen) {
        int sym = unc_canon_decode(curr, &bi);
        if (sym < 0) {
            err = bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT;
            goto out;
        }
        if (sym < 0x100) {
            curr = &hz->first;
            window[pos++ & (SIT13_WINDOW - 1)] = (uint8_t)sym;
            if (sit_put(f, (uint8_t)sym) != UNC_OK) { err = UNC_ERR_SINK; goto out; }
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
                    uint8_t b = window[from++ & (SIT13_WINDOW - 1)];
                    window[pos++ & (SIT13_WINDOW - 1)] = b;
                    if (sit_put(f, b) != UNC_OK) { err = UNC_ERR_SINK; goto out; }
                }
            }
        }
    }

out:
    unc_free(al, window);
    unc_free(al, hz);
    return err;
}

/* ------------------------------------------------------------------ */
/* Method 5: "LZAH" — LZSS (4 KB window) + adaptive Huffman with 314  */
/* leaves (the LHarc -lh1- scheme), MSB-first bits. Static distance   */
/* code (64 symbols) supplies the offset high bits.                   */
/* Source: reference/XADMaster/XADLZHDynamicHandle.m (the handle      */
/* XADStuffItParser actually uses for method 5) — LGPL, see NOTICE.   */
/* ------------------------------------------------------------------ */

#define LZAH_LEAVES 314
#define LZAH_NODES  (2 * LZAH_LEAVES - 1)   /* 627 */
#define LZAH_WINDOW 4096

typedef struct Lzah {
    /* Node storage, index-based transcription of XADLZHDynamicNode:
     * children/parent are storage indices, -1 = none. nodes[] maps
     * frequency rank -> storage index; st_index is its inverse. */
    int16_t  st_left[LZAH_NODES], st_right[LZAH_NODES], st_parent[LZAH_NODES];
    uint16_t st_freq[LZAH_NODES], st_value[LZAH_NODES], st_index[LZAH_NODES];
    int16_t  nodes[LZAH_NODES];
    int16_t  leafs[LZAH_LEAVES];             /* reconstructTree scratch */
    UncCanon distance;
    uint8_t  window[LZAH_WINDOW];
} Lzah;

/* Distance-code lengths, XADLZHDynamicHandle.m initWithHandle. */
static const uint8_t lzah_distlengths[64] = {
    3,4,4,4,5,5,5,5,5,5,5,5,6,6,6,6,
    6,6,6,6,6,6,6,6,7,7,7,7,7,7,7,7,
    7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
    8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,
};

static void lzah_reset(Lzah *h)
{
    int32_t i;
    for (i = 0; i < LZAH_NODES; i++) {
        h->st_left[i] = h->st_right[i] = h->st_parent[i] = -1;
        h->st_freq[i] = 0;
        h->st_value[i] = 0;
        h->nodes[i] = (int16_t)i;
        h->st_index[i] = (uint16_t)i;
    }
    for (i = 0; i < LZAH_LEAVES; i++) {
        int32_t idx = LZAH_NODES - 1 - i;
        h->st_freq[idx] = 1;
        h->st_value[idx] = (uint16_t)i;
    }
    for (i = LZAH_LEAVES - 2; i >= 0; i--) {
        h->st_left[i]  = (int16_t)(2 * i + 1);
        h->st_right[i] = (int16_t)(2 * i + 2);
        h->st_parent[2 * i + 1] = (int16_t)i;
        h->st_parent[2 * i + 2] = (int16_t)i;
        h->st_freq[i] = (uint16_t)(h->st_freq[2 * i + 1] +
                                   h->st_freq[2 * i + 2]);
    }

    /* Window preload (resetLZSSHandle): zeros, then the pattern.
     * "TODO: Figure out if the initialization of the window differs
     * between LHArc and StuffIt" — we follow what the oracle runs. */
    for (i = 0; i < LZAH_WINDOW; i++) h->window[i] = 0;
    for (i = 0; i < 256; i++) {
        int32_t j;
        for (j = 0; j < 13; j++) h->window[i * 13 + 18 + j] = (uint8_t)i;
    }
    for (i = 0; i < 256; i++) h->window[256 * 13 + 18 + i] = (uint8_t)i;
    for (i = 0; i < 256; i++) h->window[256 * 13 + 256 + 18 + i] = (uint8_t)(255 - i);
    for (i = 0; i < 128; i++) h->window[256 * 13 + 512 + 18 + i] = 0;
    for (i = 0; i < 128 - 18; i++) h->window[256 * 13 + 512 + 128 + 18 + i] = ' ';
}

static void lzah_rearrange(Lzah *h, int16_t p)
{
    uint16_t p_index = h->st_index[p];
    uint16_t q_index = p_index;
    while (q_index > 0 &&
           h->st_freq[h->nodes[q_index - 1]] < h->st_freq[p])
        q_index--;
    if (q_index < p_index) {
        int16_t q = h->nodes[q_index];
        int16_t new_q_parent = h->st_parent[p];
        int16_t new_p_parent = h->st_parent[q];
        int p_right, q_right;
        if (new_q_parent < 0 || new_p_parent < 0) return;  /* root: cannot happen */
        p_right = h->st_right[new_q_parent] == p;
        q_right = h->st_right[new_p_parent] == q;
        if (p_right) h->st_right[new_q_parent] = q;
        else         h->st_left[new_q_parent] = q;
        if (q_right) h->st_right[new_p_parent] = p;
        else         h->st_left[new_p_parent] = p;
        h->st_parent[p] = new_p_parent;
        h->st_parent[q] = new_q_parent;
        h->nodes[p_index] = q;
        h->st_index[q] = p_index;
        h->nodes[q_index] = p;
        h->st_index[p] = q_index;
    }
}

static void lzah_reconstruct(Lzah *h)
{
    int32_t n = 0, i;
    int32_t leaf_index, branch_index, node_index, pair_index;

    for (i = 0; i < LZAH_NODES; i++) {
        int16_t s = h->nodes[i];
        if (h->st_left[s] < 0 && h->st_right[s] < 0) {
            h->st_freq[s] = (uint16_t)((h->st_freq[s] + 1) / 2);
            h->leafs[n++] = s;
        }
    }

    leaf_index = LZAH_LEAVES - 1;
    branch_index = LZAH_LEAVES - 2;
    node_index = LZAH_NODES - 1;
    pair_index = LZAH_NODES - 2;

    while (node_index >= 0) {
        int16_t branch;
        while (node_index >= pair_index) {
            h->nodes[node_index] = h->leafs[leaf_index];
            h->st_index[h->nodes[node_index]] = (uint16_t)node_index;
            node_index--;
            leaf_index--;
        }
        branch = (int16_t)branch_index--;
        h->st_left[branch] = h->nodes[pair_index];
        h->st_right[branch] = h->nodes[pair_index + 1];
        h->st_parent[h->st_left[branch]] = branch;
        h->st_parent[h->st_right[branch]] = branch;
        h->st_freq[branch] = (uint16_t)(h->st_freq[h->st_left[branch]] +
                                        h->st_freq[h->st_right[branch]]);
        while (leaf_index >= 0 &&
               h->st_freq[h->leafs[leaf_index]] <= h->st_freq[branch]) {
            h->nodes[node_index] = h->leafs[leaf_index];
            h->st_index[h->nodes[node_index]] = (uint16_t)node_index;
            node_index--;
            leaf_index--;
        }
        h->nodes[node_index] = branch;
        h->st_index[branch] = (uint16_t)node_index;
        node_index--;
        pair_index -= 2;
    }
    h->st_parent[h->nodes[0]] = -1;
}

static void lzah_update(Lzah *h, int16_t node)
{
    if (h->st_freq[0] == 0x8000) lzah_reconstruct(h);
    for (;;) {
        h->st_freq[node]++;
        if (h->st_parent[node] < 0) break;
        lzah_rearrange(h, node);
        node = h->st_parent[node];
    }
}

static int sit_lzah_fork(SitFork *f, UncBufIn *in, uint32_t outlen,
                         UncAlloc *al)
{
    Lzah *h;
    UncBitIn bi;
    uint32_t pos = 0;
    int err = UNC_OK;

    h = (Lzah *)unc_alloc(al, (uint32_t)sizeof *h);
    if (!h) return UNC_ERR_MEM;
    lzah_reset(h);
    err = unc_canon_build(&h->distance, lzah_distlengths, 64);
    if (err != UNC_OK) goto out;

    unc_bitin_init(&bi, in);

    while (pos < outlen) {
        int16_t node = 0;   /* storage 0 is always the root */
        int lit;
        while (h->st_left[node] >= 0 || h->st_right[node] >= 0) {
            int bit = unc_bitin_bit(&bi);
            if (bit < 0) { err = bi.err; goto out; }
            node = bit ? h->st_left[node] : h->st_right[node];
            if (node < 0) { err = UNC_ERR_CORRUPT; goto out; }
        }
        lzah_update(h, node);
        lit = h->st_value[node];

        if (lit < 0x100) {
            h->window[pos++ & (LZAH_WINDOW - 1)] = (uint8_t)lit;
            if (sit_put(f, (uint8_t)lit) != UNC_OK) { err = UNC_ERR_SINK; goto out; }
        } else {
            int32_t mlen = lit - 0x100 + 3;
            int32_t high = unc_canon_decode(&h->distance, &bi);
            int32_t low, moff;
            uint32_t from;
            if (high < 0) { err = bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT; goto out; }
            low = unc_bitin_bits(&bi, 6);
            if (low < 0) { err = bi.err; goto out; }
            moff = (high << 6) + low + 1;
            from = pos - (uint32_t)moff;
            while (mlen-- > 0 && pos < outlen) {
                uint8_t b = h->window[from++ & (LZAH_WINDOW - 1)];
                h->window[pos++ & (LZAH_WINDOW - 1)] = b;
                if (sit_put(f, b) != UNC_OK) { err = UNC_ERR_SINK; goto out; }
            }
        }
    }

out:
    unc_free(al, h);
    return err;
}

/* ------------------------------------------------------------------ */
/* Method 8: "MW" — an LZW variant with parent-only dictionary and    */
/* explicit table restarts, LSB-first bits.                           */
/* Source: reference/XADMaster/XADStuffItOldHandles.m (SIT_mw,        */
/* SITMW_out; libxad heritage) — LGPL, see NOTICE.                    */
/* ------------------------------------------------------------------ */

#define MW_DICT  16385
#define MW_STACK 16384

typedef struct SitMw {
    uint16_t dict[MW_DICT];
    uint16_t stack[MW_STACK];
} SitMw;

/* Emit the chain for ptr (SITMW_out). */
static int mw_out(SitFork *f, SitMw *m, int32_t ptr, uint32_t *pos,
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
            if (sit_put(f, (uint8_t)ptr) != UNC_OK) return UNC_ERR_SINK;
        }
    }
    return UNC_OK;
}

static int sit_mw_fork(SitFork *f, UncBufIn *in, uint32_t outlen,
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

/* Method 15 put callback: byte into the SitFork staging buffer. */
static int sit_arsenic_put(void *ctx, uint8_t b)
{
    SitFork *f = (SitFork *)ctx;
    return sit_put(f, b);
}

/* Decode one fork (shared with the SIT5 container). Returns a
 * per-entry status. */
int unc_sit_decode_fork(UncCtx *c, UncFork fork, uint32_t at,
                        uint32_t complen, uint32_t outlen, int method,
                        uint16_t wantcrc, uint8_t *iobuf, uint32_t iocap,
                        uint8_t *obuf, uint32_t ocap)
{
    UncBufIn in;
    SitFork f;
    int err;

    if (method & SIT_ENCRYPTED) return UNC_ERR_ENCRYPTED;
    if (outlen == 0) return UNC_OK;

    if (c->io->seek(c->io->ctx, at) < 0) return UNC_ERR_IO;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = complen;

    f.c = c;
    f.fork = fork;
    f.crc = 0;
    f.obuf = obuf;
    f.ocap = ocap;
    f.olen = 0;

    switch (method & 0x0f) {
    case 0:  err = sit_store(&f, &in, outlen); break;
    case 1:  err = sit_rle90(&f, &in, outlen); break;
    case 2:  err = sit_lzw(&f, &in, outlen, c->al); break;
    case 3:  err = sit_huffman(&f, &in, outlen, c->al); break;
    case 5:  err = sit_lzah_fork(&f, &in, outlen, c->al); break;
    case 8:  err = sit_mw_fork(&f, &in, outlen, c->al); break;
    case 13: err = sit13_fork(&f, &in, outlen, c->al); break;
    case 15: err = unc_arsenic_decode(&in, c->al, outlen,
                                      sit_arsenic_put, &f); break;
    default: return UNC_ERR_UNSUPPORTED;
    }
    if (err == UNC_OK) err = sit_flush(&f);
    /* Method 15 carries its own CRC-32, checked inside the decoder;
     * the header CRC-16 field is not meaningful for it. */
    if (err == UNC_OK && (method & 0x0f) != 15 && f.crc != wantcrc)
        err = UNC_ERR_CRC;
    return err;
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
    uint32_t iocap = 4096, ocap = 4096;
    int err = UNC_OK;

    fsize = c->io->size(c->io->ctx);

    if (unc_read_at(c->io, 0, hdr, 22) != UNC_OK) return UNC_ERR_FORMAT;
    if (!unc_sit_probe(hdr, 22)) return UNC_ERR_FORMAT;
    totalsize = unc_get_u32be(hdr + 6);
    if (fsize != UNC_SIZE_UNKNOWN && totalsize > fsize) totalsize = fsize;
    pos = 22;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;

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
                    est = unc_sit_decode_fork(c, UNC_FORK_RSRC, start,
                                   rcomp, rlen,
                                   (int)rmeth, unc_get_u16be(hdr + 100),
                                   iobuf, iocap, obuf, ocap);
                    if (est == UNC_OK)
                        est = unc_sit_decode_fork(c, UNC_FORK_DATA,
                                       start + rcomp,
                                       dcomp, dlen, (int)dmeth,
                                       unc_get_u16be(hdr + 102),
                                       iobuf, iocap, obuf, ocap);
                }
            }
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
            if (est == UNC_ERR_SINK || est == UNC_ERR_ABORTED ||
                est == UNC_ERR_IO) {
                err = est;
                goto out;
            }
        }

        if (start + rcomp + dcomp < start) { err = UNC_ERR_CORRUPT; break; }
        pos = start + rcomp + dcomp;
    }

out:
    unc_free(c->al, iobuf);
    return err;
}

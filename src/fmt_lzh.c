/*
 * fmt_lzh.c — LZH / LHA archives (.lzh, .lha), the LHarc/LHa family.
 *
 * In scope since 2026-08-23. Until then this file's probe lived in
 * fmt_stubs.c and the format was detect-only, for want of anything to
 * grade a decoder against: the Macintosh corpus contains no `.lzh`
 * (DECISIONS.md 2026-08-14). What changed is the specimens, not the
 * effort — reference/lhasa ships 182 archives written by fourteen
 * different implementations, MacLHA 2.24 among them, and MacLHA 2.00
 * itself is a corpus fixture, so the Macintosh specimen with a resource
 * fork in it could be MADE (tools/vmac/maclha.py).
 *
 * Sources (transcribed, never guessed):
 *   reference/lhasa/lib/                      — Simon Howard's lhasa,
 *       under the ISC licence: lh_new_decoder.c and tree_decode.c for
 *       -lh4- .. -lh7-, lz5_decoder.c and lzs_decoder.c for LArc's
 *       -lz5- and -lzs-, lha_file_header.c for the header levels,
 *       lha_reader.c for LHArk's collision on "-lh7-". Its test
 *       archives are the specimens too.
 *   reference/lha/src/                        — LHa for UNIX 1.14i, the
 *       original: header.c, huf.c, dhuf.c, larc.c, slide.c. A second
 *       reading of every one of the above.
 *   the published LZHUF (src/unc_lzah.c, since 2026-09-19 no longer
 *       XADMaster's XADLZHDynamicHandle.m) — -lh1-, which is also
 *       StuffIt classic's method 5; the decoder is shared and lives in
 *       src/unc_lzah.c.
 *   reference/lha/header.doc.euc              — Masaru Oki's
 *       header.doc, LHa for UNIX, 2 March 1992: the base header at all
 *       three levels it covers, the extended-header types, the OS IDs
 *       and the method IDs. The header walk is written from it, and
 *       from lhasa for the four things it does not cover — level 3,
 *       OS-9/68k's short level 2 size, -lhd-, and LHArk. Read as a
 *       table, with the evidence: docs/formats/lzh-header.md.
 *       **Nothing in this file is XADMaster's since 2026-09-22**, bar
 *       one rule with no specimen, marked where it is.
 *
 * What is NOT here, and why:
 *   -lhx-, PMarc (-pm0-/-pm1-/-pm2-)  A different container family
 *       sharing this one's shape; out of scope (OPEN_ITEMS.md, part 1).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* Level 0/1 base header, before the name.
 * Source: reference/lha/header.doc.euc, section A, which states every
 * field of it — header size, header sum, method ID, packed and
 * original size, time, date, attribute, level, name length, the name,
 * the file CRC and level 1's OS ID and next-header size. It named
 * XADLZHParser.m as well until 2026-09-27; the document alone covers
 * this table. */
#define LZH_H_SIZE       0    /* level 0/1: header size - 2            */
#define LZH_H_SUM        1    /* level 0/1: sum of bytes 2..size-1     */
#define LZH_H_METHOD     2    /* 5 bytes, "-lh5-" and friends          */
#define LZH_H_COMPSIZE   7
#define LZH_H_ORIGSIZE  11
#define LZH_H_TIME      15
#define LZH_H_ATTR      19
#define LZH_H_LEVEL     20
#define LZH_H_NAMELEN   21    /* level 0/1 only                        */
#define LZH_H_L2_CRC    21    /* level 2/3: CRC sits where namelen does */
#define LZH_H_L2_OS     23
#define LZH_L2_BASE     24    /* level 2 base header, ext headers after */
#define LZH_L3_BASE     28    /* level 3: u32 header size at 24         */

#define LZH_MAX_BASE   257    /* level 0/1: size byte + 2               */
#define LZH_MAX_EXT     64    /* extended headers per entry, a bound    */
#define LZH_MAX_L3    (1u << 20)  /* lhasa's LEVEL_3_MAX_HEADER_LEN     */

typedef struct LzhEnt {
    uint8_t  method[5];
    uint32_t compsize;      /* bytes of compressed data                */
    uint32_t origsize;      /* bytes it decodes to                     */
    uint32_t dataoff;       /* absolute offset of the compressed data  */
    uint16_t crc;           /* CRC-16/ARC over the decoded bytes       */
    int      level;
    int      os;            /* level 1/2/3 OS byte; -1 when unstated   */
    int      is_dir;
} LzhEnt;

/* ------------------------------------------------------------------ */
/* Output side: CRC, the sink, and MacLHA's MacBinary payload          */
/*                                                                     */
/* MacLHA stores a Macintosh file as a MacBinary stream and compresses  */
/* THAT, so an entry's decoded bytes are a 128-byte header, the data    */
/* fork padded to 128, then the resource fork. The stored CRC covers    */
/* the whole stream, header and padding included, so the checksum is    */
/* taken over everything and only the routing to the sink cares where   */
/* the forks are.                                                       */
/*                                                                     */
/* The unwrap happens for OS byte 'm' and no other. 'm' is Mac in the   */
/* document's OS ID list (header.doc, section A.c); that a MacLHA entry */
/* is a MacBinary stream is in no document and is what the oracle does  */
/* too. A level 0 header has no OS byte at all, and unar reads          */
/* MacLHA's own level 0 archives as one 18,304-byte file rather than    */
/* an 18,092-byte one with a Mac header on it. Measured, not assumed.   */
/* ------------------------------------------------------------------ */

/* One decoded stream, routed to one fork or two. MacLHA compresses a
 * MacBinary payload, so the spans are set again once its header has
 * been read; until then everything is the data fork. */
static void lzh_out_start(UncForkOut *o, UncCtx *c, uint8_t *buf, int write)
{
    unc_fork_out(o, c, UNC_FORK_DATA, write, UNC_CK_CRC16_ARC,
                 buf, UNC_STAGE);
    unc_fork_split(o, 0, UNC_U32_MAX, 0, 0);
}

static int lzh_put(void *ctx, uint8_t b)
{
    return unc_fork_put((UncForkOut *)ctx, b);
}

/* The three coders in unc_lzah.c and unc_lzdyn.c hand back runs. */
static int lzh_put_run(void *ctx, const uint8_t *p, uint32_t n)
{
    return unc_fork_write((UncForkOut *)ctx, p, n);
}

/* ------------------------------------------------------------------ */
/* -lh0-, -lz4-, -pm0-: stored                                         */
/* ------------------------------------------------------------------ */

static int lzh_store(UncForkOut *o, UncBufIn *in, uint32_t outlen)
{
    uint32_t i;
    for (i = 0; i < outlen; i++) {
        int b = unc_bufin_next(in);
        int err;
        if (b < 0) return in->err;
        err = lzh_put(o, (uint8_t)b);
        if (err != UNC_OK) return err;
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* The sliding window, and how a match leaves it                      */
/*                                                                    */
/* Both coders below decode into a circular window. The window index   */
/* is the output position plus a fixed skew: zero for -lh4- .. -lh7-,  */
/* and LArc's START_OFFSET for -lz5- and -lzs-, whose first byte is    */
/* written 18 (or 17) bytes into a preloaded window                    */
/* (reference/lhasa/lib/lz5_decoder.c, lzs_decoder.c).                 */
/* ------------------------------------------------------------------ */

/* One match, out of the window and into the window AND the writer's
 * staging buffer in the same pass: the byte reaches both from one
 * register, and nothing is called per byte at all. A piece is as long
 * as the match, the two ends of the circular window, the output still
 * owed and the staging buffer allow, so none of those tests is left
 * inside the loop. The shape Compact Pro's match was fused into on
 * 2026-09-19 (DECISIONS.md, *the byte that went to two places at
 * once*), which is where the reasoning for it lives.
 *
 * The window is written before the next byte is read out of it, which
 * is what makes a match overlapping its own source — the format's
 * run-length idiom — come out right. */
static int lzh_copy(UncForkOut *o, uint8_t *w, uint32_t mask, uint32_t wskew,
                    uint32_t from, uint32_t mlen, uint32_t *posp,
                    uint32_t outlen)
{
    uint32_t pos = *posp;
    int err = UNC_OK;

    while (mlen > 0 && pos < outlen) {
        uint32_t at  = (pos + wskew) & mask;
        uint32_t sat = from & mask;
        uint32_t k = mlen;

        if (k > mask + 1u - at)   k = mask + 1u - at;
        if (k > mask + 1u - sat)  k = mask + 1u - sat;
        if (k > outlen - pos)     k = outlen - pos;
        if (k > o->cap - o->len)  k = o->cap - o->len;  /* >= 1: the put
                                                         * flushes at cap */
        /* Three cursors rather than three indices: a 68000 reads and
         * writes through (An)+ in 8 cycles where it indexes in 14. */
        {
            const uint8_t *s = w + sat;
            uint8_t *d = w + at;
            uint8_t *p = o->buf + o->len;
            uint32_t n = k;
            do { uint8_t b = *s++; *d++ = b; *p++ = b; } while (--n);
        }
        o->len += k;
        pos += k;
        from += k;
        mlen -= k;
        if (o->len == o->cap && (err = unc_fork_flush(o)) != UNC_OK) break;
    }
    *posp = pos;
    return err;
}

/* ------------------------------------------------------------------ */
/* LArc: -lzs- (2 KB window) and -lz5- (4 KB, preloaded)               */
/*                                                                    */
/* Source: reference/lhasa/lib/lz5_decoder.c and lzs_decoder.c (ISC),  */
/* cross-read against reference/lha/src/larc.c (decode_c_lzs and       */
/* decode_start_lz5). Both commands address a window POSITION rather   */
/* than a distance, which is why `from` below is an index and not an   */
/* offset.                                                            */
/* ------------------------------------------------------------------ */

/* The preload -lz5- starts from: 13 copies of each byte value, then
 * 0..255, then 255..0, then 128 zeros, then 110 spaces, then the 18
 * bytes the first output byte is written after. lz5_decoder.c's
 * fill_initial, which LHa's decode_start_lz5 agrees with byte for byte.
 *
 * Those last 18 bytes are the one place the references disagree, and
 * LArc 3.33's own `initial.lzs` — an archive whose contents ARE the
 * initial window — settles it: ZEROS. See DECISIONS.md, 2026-08-23. */
static void lzh_preload(uint8_t *w)
{
    int32_t i, j;
    uint8_t *p = w;
    for (i = 0; i < 256; i++)
        for (j = 0; j < 13; j++) *p++ = (uint8_t)i;
    for (i = 0; i < 256; i++) *p++ = (uint8_t)i;
    for (i = 0; i < 256; i++) *p++ = (uint8_t)(255 - i);
    for (i = 0; i < 128; i++) *p++ = 0;
    for (i = 0; i < 110; i++) *p++ = ' ';
    for (i = 0; i < 18;  i++) *p++ = 0;
}

static int lzh_larc(UncForkOut *o, UncBufIn *in, uint32_t outlen, UncAlloc *al,
                    int lz5)
{
    uint32_t wsize = lz5 ? 4096u : 2048u;
    uint32_t mask = wsize - 1;
    /* START_OFFSET: where the first output byte lands in the preloaded
     * window. lz5_decoder.c 18, lzs_decoder.c 17. */
    uint32_t wskew = wsize - (lz5 ? 18u : 17u);
    uint8_t *w = (uint8_t *)unc_alloc(al, wsize);
    uint32_t pos = 0;
    int flags = 0, flagbit = 7;
    UncBitIn bi;
    int err = UNC_OK;

    if (!w) return UNC_ERR_MEM;
    if (lz5) lzh_preload(w);
    /* -lzs- has no preload, and its window starts full of SPACES, not
     * zeros: lhasa and LHa 1.14i both say so, XADMaster's LZSS base
     * class zero-fills, and lhasa's `lzs.lzs` fails its stored CRC
     * either way but one. Measured, 2026-08-23 (DECISIONS.md). */
    else { uint32_t i; for (i = 0; i < wsize; i++) w[i] = ' '; }
    unc_bitin_init(&bi, in);

    while (pos < outlen) {
        uint32_t mlen, from;
        int32_t lit = -1;              /* >= 0: a literal byte value */

        if (lz5) {
            /* A run of eight commands under one bitmap byte, LSB first:
             * a set bit is a literal, a clear one a two-byte copy. */
            int byte, byte2;
            if (++flagbit > 7) {
                flagbit = 0;
                flags = unc_bufin_next(in);
                if (flags < 0) { err = in->err; break; }
            }
            byte = unc_bufin_next(in);
            if (byte < 0) { err = in->err; break; }
            if (flags & (1 << flagbit)) lit = byte;
            else {
                byte2 = unc_bufin_next(in);
                if (byte2 < 0) { err = in->err; break; }
                from = (uint32_t)byte | (((uint32_t)byte2 & 0xf0u) << 4);
                mlen = ((uint32_t)byte2 & 0x0fu) + 3u;   /* THRESHOLD 3 */
            }
        } else {
            int bit = unc_bitin_bit(&bi);
            if (bit < 0) { err = bi.err; break; }
            if (bit) {
                lit = unc_bitin_bits(&bi, 8);
                if (lit < 0) { err = bi.err; break; }
            } else {
                int32_t p = unc_bitin_bits(&bi, 11);
                int32_t l = unc_bitin_bits(&bi, 4);
                if (p < 0 || l < 0) { err = bi.err; break; }
                from = (uint32_t)p;
                mlen = (uint32_t)l + 2u;                 /* THRESHOLD 2 */
            }
        }

        if (lit >= 0) {
            w[(pos + wskew) & mask] = (uint8_t)lit;
            o->buf[o->len++] = (uint8_t)lit;
            pos++;
            if (o->len == o->cap && (err = unc_fork_flush(o)) != UNC_OK) break;
            continue;
        }
        err = lzh_copy(o, w, mask, wskew, from, mlen, &pos, outlen);
        if (err != UNC_OK) break;
    }

    unc_free(al, w);
    return err;
}

/* ------------------------------------------------------------------ */
/* -lh4- .. -lh7-: LHA v2's "new" algorithm — LZSS over a sliding      */
/* window, with three canonical Huffman codes rebuilt per block        */
/*                                                                    */
/* Source: reference/lhasa/lib/lh_new_decoder.c (ISC), the template    */
/* lhasa generates its -lh4-, -lh5-, -lh6- and -lh7- decoders from,    */
/* with tree_decode.c for the code tables and lh5_decoder.c /          */
/* lh7_decoder.c for the two alphabet widths. Cross-read against       */
/* reference/lha/src/huf.c (read_pt_len, read_c_len, decode_c_st1),    */
/* LHa for UNIX 1.14i, the original.                                   */
/*                                                                    */
/* lhasa decodes a symbol by walking a binary tree held in an array    */
/* (tree_decode.c, build_tree), which assigns codes in order of length */
/* and, within a length, in symbol order: a canonical code, which is   */
/* what UncCanon builds with a 10-bit lookup in front of it. That      */
/* table is ours and measured (DECISIONS.md 2026-08-24); what comes    */
/* from lhasa is everything that decides which lengths go into it.     */
/*                                                                    */
/* The window here is the format's dictionary — 4/8/32/64 KB — where   */
/* lhasa's ring is twice that, because in lhasa the ring is also the   */
/* output buffer. Ours stages output separately, so the smaller one is */
/* enough and a -lh7- entry costs 64 KB instead of 128 KB on a Mac.    */
/* ------------------------------------------------------------------ */

/* The command alphabet: 256 literal byte values and 254 copy lengths,
 * 3 (COPY_THRESHOLD) to 256. Source: lh_new_decoder.c NUM_CODES. */
#define LZH_NUM_CODES   510
/* Each of the other two tables is counted in a field of its own width,
 * and lhasa bounds the alphabet by what that field can say: five bits
 * for the temporary table, OFFSET_BITS (4 for -lh4-/-lh5-, 5 for
 * -lh6-/-lh7-) for the offset table. */
#define LZH_TEMP_BITS    5
#define LZH_MAX_TEMP    ((1 << LZH_TEMP_BITS) - 1)
#define LZH_MAX_OFFSET  31

typedef struct LzhCode {
    UncCanon c;
    int32_t  single;    /* >= 0: one symbol, and no bits are consumed  */
} LzhCode;

typedef struct LzhStatic {
    LzhCode  code, offset, temp;
    int16_t  codesyms[LZH_NUM_CODES];   /* 510 > UNC_CANON_MAX_SYMS    */
    uint8_t  lengths[LZH_NUM_CODES];
    uint32_t block_remaining;           /* commands left in this block */
} LzhStatic;

static int32_t lzh_code_decode(const LzhCode *k, UncBitIn *bi)
{
    if (k->single >= 0) return k->single;
    return unc_canon_decode(&k->c, bi);
}

/* A code length: three bits, and if that says 7 a unary tail extends it.
 * lh_new_decoder.c read_length_value. The ceiling is ours — the tail is
 * unbounded in the format, and a garbage stream must not be able to
 * spin in it. */
static int32_t lzh_read_length_value(UncBitIn *bi)
{
    int32_t len = unc_bitin_bits(bi, 3);

    if (len < 0) return -1;
    if (len == 7) {
        for (;;) {
            int bit = unc_bitin_bit(bi);
            if (bit < 0) return -1;
            if (!bit) break;
            if (++len > UNC_CANON_MAX_BITS) return -1;
        }
    }
    return len;
}

/* The temporary table and the offset table, which are read the same way
 * but for two things: their count field's width, and a 2-bit run of
 * skipped lengths after the third entry of the temporary one.
 * lh_new_decoder.c read_temp_table and read_offset_table, folded.
 *
 * A count of zero means one code of zero length, which every input
 * decodes to and which consumes no bits at all. */
static int lzh_read_table(LzhCode *k, UncBitIn *bi, uint8_t *lengths,
                          int bits, int32_t maxcodes, int skipafter,
                          int16_t *symbuf, int32_t symcap)
{
    int32_t n = unc_bitin_bits(bi, bits);
    int32_t i;

    if (n < 0) return bi->err;
    k->single = -1;
    if (n == 0) {
        int32_t code = unc_bitin_bits(bi, bits);
        if (code < 0) return bi->err;
        k->single = code;
        return UNC_OK;
    }
    if (n > maxcodes) n = maxcodes;       /* what the field can say is
                                           * more than the code has */

    for (i = 0; i < n; i++) lengths[i] = 0;
    for (i = 0; i < n; i++) {
        int32_t len = lzh_read_length_value(bi);
        if (len < 0) return bi->err != UNC_OK ? bi->err : UNC_ERR_CORRUPT;
        lengths[i] = (uint8_t)len;
        if (i == skipafter) {
            /* "After the first three lengths, there is a 2-bit field to
             * allow skipping over up to a further three lengths"
             * (lh_new_decoder.c). The skip may run past the count, and
             * lhasa lets it: the lengths beyond n are never read. */
            int32_t skip = unc_bitin_bits(bi, 2);
            if (skip < 0) return bi->err;
            while (skip-- > 0) lengths[++i] = 0;
        }
    }
    return unc_canon_build_ext(&k->c, lengths, n, symbuf, symcap);
}

/* How many codes a 0/1/2 from the temporary table skips over.
 * lh_new_decoder.c read_skip_count. */
static int32_t lzh_read_skip_count(UncBitIn *bi, int32_t skiprange)
{
    int32_t result;

    if (skiprange == 0) return 1;
    result = unc_bitin_bits(bi, skiprange == 1 ? 4 : 9);
    if (result < 0) return -1;
    return result + (skiprange == 1 ? 3 : 20);
}

/* The code table, whose lengths are themselves coded with the temporary
 * table: 0, 1 and 2 skip a run of unused codes, anything else is the
 * length plus two. lh_new_decoder.c read_code_table. */
static int lzh_read_code_table(LzhStatic *s, UncBitIn *bi)
{
    int32_t n, i = 0;
    int err;

    err = lzh_read_table(&s->temp, bi, s->lengths, LZH_TEMP_BITS,
                         LZH_MAX_TEMP, 2, s->temp.c.symstore,
                         UNC_CANON_MAX_SYMS);
    if (err != UNC_OK) return err;

    n = unc_bitin_bits(bi, 9);
    if (n < 0) return bi->err;
    s->code.single = -1;
    if (n == 0) {
        int32_t code = unc_bitin_bits(bi, 9);
        if (code < 0) return bi->err;
        s->code.single = code;
        return UNC_OK;
    }
    if (n > LZH_NUM_CODES) n = LZH_NUM_CODES;

    for (i = 0; i < n; i++) s->lengths[i] = 0;
    i = 0;
    while (i < n) {
        int32_t code = lzh_code_decode(&s->temp, bi);
        if (code < 0) return bi->err != UNC_OK ? bi->err : UNC_ERR_CORRUPT;
        if (code <= 2) {
            int32_t skip = lzh_read_skip_count(bi, code);
            if (skip < 0) return bi->err != UNC_OK ? bi->err : UNC_ERR_CORRUPT;
            while (skip-- > 0 && i < n) s->lengths[i++] = 0;
        } else {
            /* No ceiling test: the temporary table's alphabet is 31
             * symbols wide at most, so a length from it is at most 29
             * and UncCanon carries 31. */
            s->lengths[i++] = (uint8_t)(code - 2);
        }
    }
    return unc_canon_build_ext(&s->code.c, s->lengths, n, s->codesyms,
                               LZH_NUM_CODES);
}

/* A new block: its length in commands, then the three tables.
 * lh_new_decoder.c start_new_block. */
static int lzh_start_new_block(LzhStatic *s, UncBitIn *bi, int offbits)
{
    int32_t len = unc_bitin_bits(bi, 16);
    int err;

    if (len < 0) return bi->err;
    s->block_remaining = (uint32_t)len;
    err = lzh_read_code_table(s, bi);
    if (err != UNC_OK) return err;
    return lzh_read_table(&s->offset, bi, s->lengths, offbits,
                          LZH_MAX_OFFSET, -1, s->offset.c.symstore,
                          UNC_CANON_MAX_SYMS);
}

/* The distance back to a match. The offset table codes the LENGTH IN
 * BITS of the distance, whose top bit is then implicit:
 *   bits = 0 -> 0,  1 -> 1,  2 -> 1x,  3 -> 1xx, ...
 * lh_new_decoder.c read_offset_code. Returned one higher than lhasa's,
 * because lhasa counts back from the byte before the cursor. */
static int32_t lzh_read_offset(LzhStatic *s, UncBitIn *bi)
{
    int32_t bits = lzh_code_decode(&s->offset, bi);
    int32_t extra;

    if (bits < 0) return -1;
    if (bits == 0) return 1;
    if (bits == 1) return 2;
    if (bits > 24) return -1;       /* unc_bitin_bits reads at most 24 */
    extra = unc_bitin_bits(bi, bits - 1);
    if (extra < 0) return -1;
    return extra + (1 << (bits - 1)) + 1;
}

static int lzh_static(UncForkOut *o, UncBufIn *in, uint32_t outlen, int wbits,
                      UncAlloc *al)
{
    LzhStatic *s;
    UncBitIn bi;
    uint8_t *w;
    uint32_t wsize = 1u << wbits, mask, pos = 0;
    /* OFFSET_BITS: four for the 4 and 8 KB dictionaries, five for the
     * 32 and 64 KB ones (lh5_decoder.c, lh6_decoder.c). */
    int offbits = wbits < 15 ? 4 : 5;
    int err = UNC_OK;

    /* The window never has to be bigger than the output rounded up to a
     * power of two: a stream that reaches further back than it has
     * written is corrupt, and the format's encoders never emit one.
     * Same sizing StuffIt method 13 uses (fmt_sit.c). It is what keeps
     * a -lh7- entry of a few KB off a 64 KB allocation on a Mac Plus. */
    while (wsize > 4096u && wsize / 2u >= outlen) wsize /= 2u;
    mask = wsize - 1;

    s = (LzhStatic *)unc_alloc(al, (uint32_t)sizeof *s);
    if (!s) return UNC_ERR_MEM;
    w = (uint8_t *)unc_alloc(al, wsize);
    if (!w) { unc_free(al, s); return UNC_ERR_MEM; }
    /* lhasa fills the ring with SPACES and XADMaster with zeros; only a
     * stream that reads back further than it has written can tell, and
     * none in the corpus does (measured 2026-09-19, DECISIONS.md). The
     * two references that describe the format agree on spaces. */
    { uint32_t i; for (i = 0; i < wsize; i++) w[i] = ' '; }

    s->block_remaining = 0;
    s->code.single = s->offset.single = s->temp.single = -1;
    unc_bitin_init(&bi, in);

    while (pos < outlen) {
        int32_t code;

        if (s->block_remaining == 0) {
            err = lzh_start_new_block(s, &bi, offbits);
            if (err != UNC_OK) break;
            if (s->block_remaining == 0) continue;   /* an empty block */
        }
        s->block_remaining--;

        code = lzh_code_decode(&s->code, &bi);
        if (code < 0) { err = bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT; break; }

        if (code < 0x100) {
            w[pos & mask] = (uint8_t)code;
            o->buf[o->len++] = (uint8_t)code;
            pos++;
            if (o->len == o->cap && (err = unc_fork_flush(o)) != UNC_OK) break;
        } else {
            int32_t moff = lzh_read_offset(s, &bi);
            if (moff < 0) { err = bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT; break; }
            err = lzh_copy(o, w, mask, 0, pos - (uint32_t)moff,
                           (uint32_t)(code - 0x100 + 3), &pos, outlen);
            if (err != UNC_OK) break;
        }
    }

    unc_free(al, w);
    unc_free(al, s);
    return err;
}

/* ------------------------------------------------------------------ */
/* Method dispatch                                                     */
/* ------------------------------------------------------------------ */

static int lzh_is(const uint8_t *m, const char *want)
{
    int i;
    for (i = 0; i < 5; i++) if (m[i] != (uint8_t)want[i]) return 0;
    return 1;
}

/* Decode one entry's stream into `o`. Per-entry status. */
static int lzh_decode(UncCtx *c, const LzhEnt *e, UncForkOut *o, uint8_t *iobuf,
                      uint32_t iocap)
{
    UncBufIn in;
    int err;

    if (c->io->seek(c->io->ctx, e->dataoff) < 0) return UNC_ERR_IO;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = e->compsize;

    /* LHArk 0.4d writes "-lh7-" over a method of its own, and marks
     * itself with a space as the OS byte. It is a different algorithm
     * (lhasa calls it -lk7- and decodes it separately); nothing here
     * reads it, so it is refused rather than decoded into rubbish.
     * Source: reference/lhasa/lib/lha_reader.c, LHA_OS_TYPE_LHARK. */
    if (lzh_is(e->method, "-lh7-") && e->os == ' ')
        return UNC_ERR_UNSUPPORTED;

    if (lzh_is(e->method, "-lh0-") || lzh_is(e->method, "-lz4-"))
        err = lzh_store(o, &in, e->origsize);
    else if (lzh_is(e->method, "-lh2-")) {
        UncBitIn bi;
        unc_bitin_init(&bi, &in);
        err = unc_lzdyn_decode(c->al, &bi, e->origsize, lzh_put_run, o);
    }
    else if (lzh_is(e->method, "-lh3-")) {
        UncBitIn bi;
        unc_bitin_init(&bi, &in);
        err = unc_lzst0_decode(c->al, &bi, e->origsize, lzh_put_run, o);
    }
    else if (lzh_is(e->method, "-lh1-")) {
        UncBitIn bi;
        unc_bitin_init(&bi, &in);
        err = unc_lzah_decode(c->al, &bi, e->origsize, UNC_LZAH_LH1,
                              lzh_put_run, o);
    }
    else if (lzh_is(e->method, "-lh4-"))
        err = lzh_static(o, &in, e->origsize, 12, c->al);
    else if (lzh_is(e->method, "-lh5-"))
        err = lzh_static(o, &in, e->origsize, 13, c->al);
    else if (lzh_is(e->method, "-lh6-"))
        err = lzh_static(o, &in, e->origsize, 15, c->al);
    else if (lzh_is(e->method, "-lh7-"))
        err = lzh_static(o, &in, e->origsize, 16, c->al);
    else if (lzh_is(e->method, "-lz5-"))
        err = lzh_larc(o, &in, e->origsize, c->al, 1);
    else if (lzh_is(e->method, "-lzs-"))
        err = lzh_larc(o, &in, e->origsize, c->al, 0);
    else
        return UNC_ERR_UNSUPPORTED;

    if (err == UNC_OK) err = unc_fork_flush(o);
    if (err != UNC_OK) return err;
    if (unc_fork_pos(o) != e->origsize) return UNC_ERR_TRUNCATED;
    if (o->crc16 != e->crc) return UNC_ERR_CRC;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Headers                                                             */
/* ------------------------------------------------------------------ */

/* Append one path component, mapping the format's separators. LZH
 * names arrive with 0xff between directory components — the dirname
 * extended header, 0x02 in the document's section B, whose separator
 * is lhasa's (ext_header_path_decoder) — or, in an old header, with a
 * DOS backslash or a Unix slash. Splitting on all of them and dropping
 * the empty components also absorbs the two shapes lhasa needs a
 * special case for: a dirname with a trailing separator and one
 * without (Amiga LHA 1.22). */
static void lzh_add_path(UncEntryInfo *e, const uint8_t *p, uint32_t len,
                         int seps_all)
{
    uint32_t i, start = 0;
    for (i = 0; i <= len; i++) {
        int sep = i == len ? 1 :
                  (p[i] == 0xff || (seps_all && (p[i] == '\\' || p[i] == '/')));
        if (!sep) continue;
        if (i > start) unc_entry_path_append(e, p + start, i - start);
        start = i + 1;
    }
}

/* One extended header, of which this reader wants two: the long
 * filename (0x01) and the directory (0x02). Everything else is
 * stepped over — the dates in 0x41/0x54 are Unix or Windows time and
 * this engine does not convert either (see the entry loop). */
static int lzh_ext(UncCtx *c, uint32_t at, uint32_t size, uint8_t *name,
                   uint32_t *namelen, uint8_t *dir, uint32_t *dirlen,
                   UncEntryInfo *info)
{
    uint8_t type;
    uint32_t n;

    if (size < 1) return UNC_ERR_CORRUPT;
    if (unc_read_at(c->io, at, &type, 1) != UNC_OK) return UNC_ERR_TRUNCATED;
    n = size - 1;
    if (n > UNC_NAME_MAX) {
        if (type == 0x01 || type == 0x02) {
            info->name_truncated = 1;
            info->name_full_len = (uint16_t)(n > 65535u ? 65535u : n);
        }
        n = UNC_NAME_MAX;
    }
    if (type == 0x01 && n > 0) {
        if (unc_read_at(c->io, at + 1, name, (int32_t)n) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        *namelen = n;
    } else if (type == 0x02 && n > 0) {
        if (unc_read_at(c->io, at + 1, dir, (int32_t)n) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        *dirlen = n;
    }
    return UNC_OK;
}

/* Read the header at `pos`. Returns UNC_OK with *next set to the offset
 * of the following header, UNC_ERR_FORMAT at the end-of-archive marker,
 * or a hard error. */
static int lzh_header(UncCtx *c, uint32_t pos, LzhEnt *e, UncEntryInfo *info,
                      uint32_t *next)
{
    uint8_t h[LZH_MAX_BASE];
    uint8_t extname[UNC_NAME_MAX + 1], extdir[UNC_NAME_MAX + 1];
    uint32_t extnamelen = 0, extdirlen = 0;
    uint32_t hdrsize, at, headerend, k;
    int i, level, nexts_are_32 = 0;

    if (unc_read_at(c->io, pos, h, LZH_L2_BASE) != UNC_OK)
        return UNC_ERR_FORMAT;
    if (h[0] == 0) return UNC_ERR_FORMAT;      /* end-of-archive marker */

    level = h[LZH_H_LEVEL];
    for (i = 0; i < 5; i++) e->method[i] = h[LZH_H_METHOD + i];
    e->compsize = unc_get_u32le(h + LZH_H_COMPSIZE);
    e->origsize = unc_get_u32le(h + LZH_H_ORIGSIZE);
    e->level = level;
    e->os = -1;
    e->is_dir = lzh_is(e->method, "-lhd-");
    unc_entry_clear(info);

    if (level == 0 || level == 1) {
        uint32_t namelen, nameat;
        hdrsize = (uint32_t)h[LZH_H_SIZE] + 2u;
        if (hdrsize < 22) return UNC_ERR_CORRUPT;
        if (unc_read_at(c->io, pos, h, (int32_t)hdrsize) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        namelen = h[LZH_H_NAMELEN];
        nameat = 22;
        if (nameat + namelen + 2 > hdrsize) return UNC_ERR_CORRUPT;
        /* A NUL inside the name field ends it.
         *
         * BOTH references produce this name, which this comment denied
         * until 2026-09-27 by saying "lhasa takes the whole field".
         * XADMaster stops at the NUL explicitly and keeps the
         * remainder as XADCommentKey (XADLZHParser.m). lhasa reaches
         * the same filename implicitly: process_level0_path() copies
         * the whole field and NUL-terminates it, and every consumer
         * then touches it as a C string — strrchr in
         * split_header_filename, strdup, strlen and sprintf in
         * lha_file_header_full_path — so anything after an embedded
         * NUL is unreachable. Source: reference/lhasa/lib/
         * lha_file_header.c (ISC).
         *
         * What differs is only whether the trailing bytes surface as a
         * COMMENT, and this engine has nowhere to put one, so it drops
         * them and agrees with both. The document states no comment in
         * this field at all, and lhasa's level-0 comment support is in
         * the extended AREA (process_level0_extended_area, for PMarc).
         * No specimen either way: 0 of the 140 level 0/1 name fields in
         * the 156 archives here holds a NUL (tools/derive_lzh.py).
         * docs/formats/lzh-header.md. */
        for (k = 0; k < namelen; k++)
            if (h[nameat + k] == 0) { namelen = k; break; }
        if (namelen > UNC_NAME_MAX) {
            info->name_truncated = 1;
            info->name_full_len = (uint16_t)namelen;
            namelen = UNC_NAME_MAX;
        }
        for (k = 0; k < namelen; k++) extname[k] = h[nameat + k];
        extnamelen = namelen;
        e->crc = unc_get_u16le(h + 22 + h[LZH_H_NAMELEN]);
        headerend = pos + hdrsize;
        if (level == 1) {
            if (25u + h[LZH_H_NAMELEN] > hdrsize) return UNC_ERR_CORRUPT;
            e->os = h[22 + h[LZH_H_NAMELEN] + 2];
            /* The chain starts at the "next header size" word that ends
             * the base header — it is INSIDE hdrsize, not after it. */
            at = pos + 25u + h[LZH_H_NAMELEN];
            /* Level 1 counts its extended headers inside the COMPRESSED
             * size, so each one moves the data start along and shortens
             * the stream. The document names that field "skip size" for
             * exactly this reason (header.doc, section A, the level-1
             * column); lhasa makes the same subtraction, in
             * read_l1_extended_headers. */
            for (i = 0; i < LZH_MAX_EXT; i++) {
                uint8_t sz[2];
                uint32_t extsize;
                if (unc_read_at(c->io, at, sz, 2) != UNC_OK)
                    return UNC_ERR_TRUNCATED;
                extsize = unc_get_u16le(sz);
                if (extsize == 0) break;
                if (extsize < 3 || extsize > e->compsize) return UNC_ERR_CORRUPT;
                if (lzh_ext(c, at + 2, extsize - 2, extname, &extnamelen,
                            extdir, &extdirlen, info) != UNC_OK)
                    return UNC_ERR_TRUNCATED;
                e->compsize -= extsize;
                hdrsize += extsize;
                at += extsize;
            }
            headerend = pos + hdrsize;
        }
    } else if (level == 2 || level == 3) {
        if (level == 2) {
            hdrsize = unc_get_u16le(h);
            if (hdrsize < LZH_L2_BASE) return UNC_ERR_CORRUPT;
            /* LHA for OS-9/68k 2.01 writes the length of the REST of
             * the header rather than the whole of it, so its level 2
             * headers are two bytes short and every offset after them
             * is wrong. lhasa compensates by OS byte and this follows
             * it; XADMaster does not, which is why `unar` fails all
             * three of lhasa's lha_osk_201 level 2 archives.
             * Source: reference/lhasa/lib/lha_file_header.c,
             * decode_level2_header. */
            if (h[LZH_H_L2_OS] == 'K') hdrsize += 2u;
            at = pos + LZH_L2_BASE;
        } else {
            uint8_t l3[LZH_L3_BASE];
            if (unc_get_u16le(h) != 4) return UNC_ERR_UNSUPPORTED;
            if (unc_read_at(c->io, pos, l3, LZH_L3_BASE) != UNC_OK)
                return UNC_ERR_TRUNCATED;
            hdrsize = unc_get_u32le(l3 + 24);
            if (hdrsize < LZH_L3_BASE || hdrsize > LZH_MAX_L3)
                return UNC_ERR_CORRUPT;
            at = pos + LZH_L3_BASE;
            nexts_are_32 = 1;
        }
        e->crc = unc_get_u16le(h + LZH_H_L2_CRC);
        e->os = h[LZH_H_L2_OS];
        headerend = pos + hdrsize;
        /* Level 2 and 3 keep their extended headers INSIDE the header,
         * so they change neither the data offset nor the size. */
        for (i = 0; i < LZH_MAX_EXT; i++) {
            uint8_t sz[4];
            uint32_t extsize, w = nexts_are_32 ? 4u : 2u;
            if (at + w > headerend) break;
            if (unc_read_at(c->io, at, sz, (int32_t)w) != UNC_OK)
                return UNC_ERR_TRUNCATED;
            extsize = nexts_are_32 ? unc_get_u32le(sz) : unc_get_u16le(sz);
            if (extsize == 0) break;
            if (extsize < w + 1 || at + extsize > headerend)
                return UNC_ERR_CORRUPT;
            if (lzh_ext(c, at + w, extsize - w, extname, &extnamelen,
                        extdir, &extdirlen, info) != UNC_OK)
                return UNC_ERR_TRUNCATED;
            at += extsize;
        }
    } else {
        return UNC_ERR_CORRUPT;
    }

    e->dataoff = headerend;
    *next = headerend + e->compsize;

    /* Build the path into the caller's entry: directory components
     * (0xff-separated) then the name. Without a directory header the
     * name itself may carry separators — 0xff, a DOS backslash or a
     * Unix slash. Built here rather than into a local, because an
     * UncEntryInfo is 300 bytes on the 68000 target (measured
     * 2026-09-22 with the Retro68 compiler; the 280 that stood here was
     * never right, the 296 that replaced it was measured hours
     * before the struct's next field landed, and 298 held until
     * `name_utf8`) and this call chain has a
     * 4 KB budget (CLAUDE.md, 68000 discipline). */
    if (extdirlen) {
        lzh_add_path(info, extdir, extdirlen, 0);
        if (extnamelen) lzh_add_path(info, extname, extnamelen, 0);
    } else if (extnamelen) {
        lzh_add_path(info, extname, extnamelen, 1);
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Probe and walk                                                      */
/* ------------------------------------------------------------------ */

/* "-lh?-" (lzh) or "-lz?-" (larc) method id at offset 2.
 * Source: reference/lha/header.doc.euc, section A — the method ID is
 * the third field of every header level — and section A.b for the set
 * of IDs it can hold.
 *
 * With one addition, measured rather than copied: XADMaster's
 * recogniser accepts -lz0-, -lz4- and -lz5- but not -lzs-, while its
 * OWN parser has a decoder for -lzs- — so `unar` cannot open a file it
 * can decode (checked: "Couldn't recognize the archive format" on
 * lhasa's lzs specimens). This probe accepts it. */

/* Is this 128-byte block MacLHA's MacBinary header, when the ordinary
 * MacBinary probe has said no?
 *
 * MacLHA 2.00 writes a MacBinary I header whose CREATION AND
 * MODIFICATION DATES ARE ZERO, and every reader in reach refuses it for
 * that: XADMaster's MacBinary I heuristic requires both dates non-zero,
 * and lhasa requires the modification date to be both sane and equal to
 * the LZH header's. So `unar` and lhasa hand back the whole 2,304-byte
 * stream, header and padding included, and the file's resource fork
 * with it. Measured on an archive MacLHA 2.00 itself wrote under Mini
 * vMac (`tools/vmac/maclha.py`), which is the only specimen of that
 * writer anybody here has.
 *
 * What replaces the dates is arithmetic, and it is lhasa's own check
 * without the clock in it: the two fork lengths, each padded to 128 and
 * with the header, must come to exactly the entry's uncompressed size,
 * and the name in the Mac header must be the name in the LZH header.
 * A stream that satisfies both is a MacBinary stream; a data fork that
 * happens to satisfy both would have to agree with its own container
 * about its length to the byte and carry the entry's name at offset 2.
 * DECISIONS.md 2026-08-23 (LZH). */
static int lzh_maclha_header(const uint8_t *mb, uint32_t origsize,
                             const uint8_t *name, uint32_t namelen)
{
    uint32_t dlen, rlen, total, i;

    if (mb[0] != 0 || mb[74] != 0 || mb[82] != 0) return 0;
    for (i = 108; i <= 115; i++) if (mb[i] != 0) return 0;
    if (mb[1] == 0 || mb[1] > 63) return 0;
    /* The name, and nothing but the name, in the 63-byte field. */
    if (mb[1] != namelen) return 0;
    for (i = 0; i < namelen; i++) if (mb[2 + i] != name[i]) return 0;
    for (i = namelen; i < 63; i++) if (mb[2 + i] != 0) return 0;

    dlen = unc_get_u32be(mb + 83);
    rlen = unc_get_u32be(mb + 87);
    if (dlen > origsize || rlen > origsize) return 0;
    total = 128u + ((dlen + 127u) & ~127u) + ((rlen + 127u) & ~127u);
    return total == origsize;
}

int unc_lzh_extract(UncCtx *c)
{
    uint8_t *iobuf;
    uint32_t iocap = UNC_IOBUF;
    uint32_t pos = 0;
    int err = UNC_OK, any = 0;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap);
    if (!iobuf) return UNC_ERR_MEM;

    for (;;) {
        LzhEnt e;
        UncForkOut o;
        uint8_t    obuf[UNC_STAGE];
        UncEntryInfo info;
        uint8_t mb[128];
        uint32_t next = 0;
        int sret, est = UNC_OK, mac = 0, hret;

        hret = lzh_header(c, pos, &e, &info, &next);
        if (hret == UNC_ERR_FORMAT) break;       /* end-of-archive */
        if (hret != UNC_OK) { err = hret; break; }
        if (next <= pos) { err = UNC_ERR_CORRUPT; break; }

        /* A -lhd- entry with no path at all names the directory the
         * archive is being extracted INTO ("." to the oracle, which
         * creates nothing for it). Nothing to report and nothing to
         * make. */
        if (e.is_dir && info.name_len == 0) { any = 1; pos = next; continue; }

        /* A symbolic link is stored as one entry named "link|target",
         * usually with -lhd- as its method. Classic Mac OS has no
         * symbolic links, so it is reported and not created — the same
         * answer tar's reader gives a link (fmt_exo.c).
         * Source: reference/lhasa/lib/lha_file_header.c parse_symlink. */
        {
            uint32_t k2;
            for (k2 = 0; k2 < info.name_len; k2++)
                if (info.name[k2] == '|') break;
            if (k2 < info.name_len) {
                info.name_len = (uint16_t)k2;
                info.name[k2] = 0;
                info.data_size = 0;
                info.rsrc_size = 0;
                sret = c->sink->begin_entry(c->sink->ctx, &info);
                if (sret < 0) { err = UNC_ERR_SINK; break; }
                if (sret == 0 &&
                    c->sink->end_entry(c->sink->ctx, UNC_ERR_UNSUPPORTED) < 0) {
                    err = UNC_ERR_SINK;
                    break;
                }
                any = 1;
                pos = next;
                continue;
            }
        }

        info.data_size = e.origsize;
        info.rsrc_size = 0;
        info.comp_data_size = e.compsize;
        info.is_dir = (uint8_t)e.is_dir;
        /* No date: levels 0 and 1 store an MS-DOS timestamp and 2 and 3
         * a Unix one, and neither is a Mac date. Zip's reader says the
         * same nothing for the same reason. Where a MacBinary header
         * follows, its Mac dates are used instead — below. */

        lzh_out_start(&o, c, obuf, !c->opt.test_only);

        /* MacLHA's payload: peek the first 128 decoded bytes and let
         * the MacBinary probe decide. Decoding twice costs one header's
         * worth of output, because the peek stops there. */
        /* Listing does the peek too: what the entry IS — its name,
         * its type and creator, the size of each fork — is what the
         * Mac header says, and a listing that disagreed with the
         * extraction would be a bug a diff suite cannot see. */
        if (!e.is_dir && e.os == 'm' && e.origsize >= 128) {
            uint32_t want = e.origsize;
            /* The same entry and the same output struct, so the peek
             * costs no stack: 128 bytes of output, then reset. It must
             * write NOTHING — begin_entry has not been called yet — so
             * the sink is switched off for the duration. */
            lzh_out_start(&o, c, obuf, 0);
            e.origsize = 128;
            (void)lzh_decode(c, &e, &o, iobuf, iocap);
            e.origsize = want;
            if (unc_fork_pos(&o) == 128) {
                uint32_t k;
                for (k = 0; k < 128; k++) mb[k] = o.buf[k];
                mac = unc_macbinary_probe(mb, 128, 0) ||
                      lzh_maclha_header(mb, e.origsize, info.name,
                                        info.name_len);
            }
            lzh_out_start(&o, c, obuf, !c->opt.test_only);
        }
        if (mac) {
            uint32_t sec = unc_get_u16be(mb + 120);
            uint32_t dlen = unc_get_u32be(mb + 83);
            uint32_t rlen = unc_get_u32be(mb + 87);
            uint32_t ds = 128u + ((sec + 127u) & ~127u);
            uint32_t rs = ds + ((dlen + 127u) & ~127u);
            if (dlen > e.origsize || rlen > e.origsize ||
                rs + rlen > e.origsize) {
                mac = 0;
            } else {
                unc_fork_split(&o, ds, ds + dlen, rs, rs + rlen);
                info.data_size = dlen;
                info.rsrc_size = rlen;
                info.type = unc_get_u32be(mb + 65);
                info.creator = unc_get_u32be(mb + 69);
                info.finder_flags = (uint16_t)((mb[73] << 8) | mb[101]);
                info.create_date = unc_get_u32be(mb + 91);
                info.mod_date = unc_get_u32be(mb + 95);
            }
        }

        sret = c->sink->begin_entry(c->sink->ctx, &info);
        if (sret < 0) { err = UNC_ERR_SINK; break; }
        if (sret == 0) {
            if (!c->opt.list_only && !e.is_dir)
                est = lzh_decode(c, &e, &o, iobuf, iocap);
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
            /* A per-entry error does not stop the walk — but these
             * three are not the entry's: the host asked to stop, the
             * sink failed, or the archive is unreadable. Same rule the
             * tar reader applies (fmt_exo.c). */
            if (unc_fatal(est)) {
                err = est;
                break;
            }
        }
        any = 1;
        pos = next;
    }

    unc_free(c->al, iobuf);
    if (!any && err == UNC_OK) return UNC_ERR_FORMAT;
    return err;
}

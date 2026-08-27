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
 *   reference/XADMaster/XADLZHParser.m        — the header walk, all
 *       four header levels, the extended-header types, which method
 *       maps to which window size, and the CRC contract (CRC-16/ARC
 *       over the DECODED bytes, unconditioned).
 *   reference/XADMaster/XADLZHStaticHandle.m  — -lh4- .. -lh7-.
 *   reference/XADMaster/XADLZHDynamicHandle.m — -lh1-, which is also
 *       StuffIt classic's method 5; the decoder is shared and lives in
 *       src/unc_lzah.c.
 *   reference/XADMaster/XADLArcHandles.m      — LArc's -lzs- and -lz5-.
 *   reference/lha/src/                        — LHa for UNIX 1.14i, the
 *       original: header.c, huf.c, dhuf.c, larc.c, slide.c. A second
 *       reading of every one of the above.
 *   reference/lhasa/lib/                      — Simon Howard's lhasa,
 *       an independent implementation: lha_file_header.c for the
 *       header levels, and its test archives as specimens.
 *
 * What is NOT here, and why:
 *   -lh2-, -lh3-  Declined per entry. Both are implementable from
 *       XADLZHOldHandles.m, but no archive that uses either is
 *       reachable here — not in the corpus, not in lhasa's collection
 *       of fourteen writers, and nothing in reach writes one. Code no
 *       oracle can grade is the bargain this project declines
 *       everywhere else (OPEN_ITEMS.md).
 *   -lhx-, PMarc (-pm0-/-pm1-/-pm2-)  A different container family
 *       sharing this one's shape; out of scope (OPEN_ITEMS.md, part 1).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* Level 0/1 base header, before the name. Source: XADLZHParser.m and
 * reference/lha/header.doc.euc ("header level 0/1"). */
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

/* Static Huffman (-lh4- .. -lh7-). Alphabet sizes are LHa's own:
 * NC = UCHAR_MAX + MAXMATCH + 2 - THRESHOLD = 510 literals-and-lengths,
 * NT = 19 code-length symbols. Source: reference/lha/src/lha.h. */
#define LZH_NC   510
#define LZH_NT    19
#define LZH_NP    32          /* offset symbols: 4- or 5-bit count      */

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
/* The unwrap happens for OS byte 'm' and no other, which is what the   */
/* oracle does (XADLZHParser.m sets XADMightBeMacBinaryKey there, and    */
/* only there): a level 0 header has no OS byte at all, and unar reads  */
/* MacLHA's own level 0 archives as one 18,304-byte file rather than    */
/* an 18,092-byte one with a Mac header on it. Measured, not assumed.   */
/* ------------------------------------------------------------------ */

typedef struct LzhOut {
    UncCtx  *c;
    uint16_t crc;
    int      write;         /* nonzero: write to the sink              */
    uint32_t pos;           /* decoded bytes produced so far           */
    uint32_t base;          /* stream offset of buf[0]                 */
    /* Fork spans within the decoded stream. Without a Mac header the
     * data span is the whole of it and the resource span is empty. */
    uint32_t dstart, dend, rstart, rend;
    uint8_t  buf[512];
    uint32_t blen;
} LzhOut;

static void lzh_out_init(LzhOut *o, UncCtx *c, int write)
{
    o->c = c;
    o->crc = 0;
    o->write = write;
    o->pos = o->base = o->blen = 0;
    o->dstart = 0;
    o->dend = 0xFFFFFFFFu;
    o->rstart = o->rend = 0;
}

/* Write the part of [from, to) that falls inside [start, end) to `fork`. */
static int lzh_span(LzhOut *o, UncFork fork, uint32_t start, uint32_t end)
{
    uint32_t from = o->base, to = o->base + o->blen;
    if (from < start) from = start;
    if (to > end) to = end;
    if (from >= to) return UNC_OK;
    if (o->c->sink->write(o->c->sink->ctx, fork, o->buf + (from - o->base),
                          (int32_t)(to - from)) != 0)
        return UNC_ERR_SINK;
    return UNC_OK;
}

static int lzh_flush(LzhOut *o)
{
    int err = UNC_OK;
    if (o->blen == 0) return UNC_OK;
    o->crc = unc_crc16_arc(o->crc, o->buf, (int32_t)o->blen);
    if (o->write) {
        err = lzh_span(o, UNC_FORK_DATA, o->dstart, o->dend);
        if (err == UNC_OK)
            err = lzh_span(o, UNC_FORK_RSRC, o->rstart, o->rend);
    }
    o->base += o->blen;
    o->blen = 0;
    return err;
}

static int lzh_put(void *ctx, uint8_t b)
{
    LzhOut *o = (LzhOut *)ctx;
    o->buf[o->blen++] = b;
    o->pos++;
    if (o->blen == sizeof o->buf) return lzh_flush(o);
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* -lh0-, -lz4-, -pm0-: stored                                         */
/* ------------------------------------------------------------------ */

static int lzh_store(LzhOut *o, UncBufIn *in, uint32_t outlen)
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
/* LArc: -lzs- (2 KB window) and -lz5- (4 KB, preloaded)               */
/* Source: reference/XADMaster/XADLArcHandles.m, cross-read against    */
/* reference/lha/src/larc.c (decode_c_lzs / decode_c_lz5).             */
/* ------------------------------------------------------------------ */

/* The preload LArc and LHarc share: 13 copies of each byte value, then
 * 0..255, then 255..0, then zeros, then spaces. Source: larc.c
 * decode_start_lz5 and XADLArcLZ5Handle resetLZSSHandle, which agree
 * byte for byte.
 *
 * What is underneath it — the 18 bytes the pattern does not cover —
 * is the one place the three references disagree, and LArc 3.33's own
 * `initial.lzs` (an archive whose contents ARE the initial window)
 * settles it: ZEROS. See DECISIONS.md, 2026-08-23. */
static void lzh_preload(uint8_t *w)
{
    int32_t i, j;
    for (i = 0; i < 4096; i++) w[i] = 0;
    for (i = 0; i < 256; i++)
        for (j = 0; j < 13; j++) w[i * 13 + 18 + j] = (uint8_t)i;
    for (i = 0; i < 256; i++) w[256 * 13 + 18 + i] = (uint8_t)i;
    for (i = 0; i < 256; i++) w[256 * 13 + 256 + 18 + i] = (uint8_t)(255 - i);
    for (i = 0; i < 128; i++) w[256 * 13 + 512 + 18 + i] = 0;
    for (i = 0; i < 128 - 18; i++) w[256 * 13 + 512 + 128 + 18 + i] = ' ';
}

static int lzh_larc(LzhOut *o, UncBufIn *in, uint32_t outlen, UncAlloc *al,
                    int lz5)
{
    uint32_t wsize = lz5 ? 4096u : 2048u;
    uint32_t mask = wsize - 1;
    uint8_t *w = (uint8_t *)unc_alloc(al, wsize);
    uint32_t pos = 0;
    int flags = 0, flagbit = 7;
    UncBitIn bi;
    int err = UNC_OK;

    if (!w) return UNC_ERR_MEM;
    if (lz5) lzh_preload(w);
    /* -lzs- has no preload, and its window starts full of SPACES, not
     * zeros: LHa 1.14i and lhasa both say so, XADMaster's LZSS base
     * class zero-fills, and lhasa's `lzs.lzs` fails its stored CRC
     * either way but one. Measured, 2026-08-23 (DECISIONS.md). */
    else { uint32_t i; for (i = 0; i < wsize; i++) w[i] = ' '; }
    unc_bitin_init(&bi, in);

    while (pos < outlen) {
        int32_t mlen, moff;
        uint32_t from;

        if (lz5) {
            int byte, byte2;
            if (++flagbit > 7) {
                flagbit = 0;
                flags = unc_bufin_next(in);
                if (flags < 0) { err = in->err; break; }
            }
            byte = unc_bufin_next(in);
            if (byte < 0) { err = in->err; break; }
            if (flags & (1 << flagbit)) {
                w[pos++ & mask] = (uint8_t)byte;
                err = lzh_put(o, (uint8_t)byte);
                if (err != UNC_OK) break;
                continue;
            }
            byte2 = unc_bufin_next(in);
            if (byte2 < 0) { err = in->err; break; }
            /* The pair addresses a window POSITION, not a distance:
             * LHa computes `(loc - decode_p() - 1) & mask` around
             * `decode_p_lz5`, which comes to (matchpos + 18) & mask,
             * and XADLArcLZ5Handle's `pos - byte - ((byte2&0xf0)<<4)
             * - 18` reaches the same index through the base class's
             * `matchoffset = pos - offset`. */
            moff = byte + ((byte2 & 0xf0) << 4) + 18;
            mlen = (byte2 & 0x0f) + 3;
        } else {
            int bit = unc_bitin_bit(&bi);
            if (bit < 0) { err = bi.err; break; }
            if (bit) {
                int32_t lit = unc_bitin_bits(&bi, 8);
                if (lit < 0) { err = bi.err; break; }
                w[pos++ & mask] = (uint8_t)lit;
                err = lzh_put(o, (uint8_t)lit);
                if (err != UNC_OK) break;
                continue;
            }
            {
                int32_t p = unc_bitin_bits(&bi, 11);
                int32_t l = unc_bitin_bits(&bi, 4);
                if (p < 0 || l < 0) { err = bi.err; break; }
                /* As -lz5-, with LArc's other magic: (matchpos + 17). */
                moff = p + 17;
                mlen = l + 2;
            }
        }

        from = (uint32_t)moff;
        while (mlen-- > 0 && pos < outlen) {
            uint8_t b = w[from++ & mask];
            w[pos++ & mask] = b;
            err = lzh_put(o, b);
            if (err != UNC_OK) break;
        }
        if (err != UNC_OK) break;
    }

    unc_free(al, w);
    return err;
}

/* ------------------------------------------------------------------ */
/* -lh4- .. -lh7-: block-wise static Huffman over an LZSS              */
/* Source: reference/XADMaster/XADLZHStaticHandle.m; second reading    */
/* reference/lha/src/huf.c (read_pt_len / read_c_len / decode_c_st1).  */
/* ------------------------------------------------------------------ */

typedef struct LzhCode {
    UncCanon c;
    int32_t  single;    /* >= 0: one symbol, and no bits are consumed  */
} LzhCode;

typedef struct LzhStatic {
    LzhCode  lit, dist, meta;
    int16_t  litsyms[LZH_NC];   /* 510 > UNC_CANON_MAX_SYMS            */
    uint8_t  lengths[LZH_NC];
    int32_t  blocksize, blockpos;
} LzhStatic;

static int32_t lzh_code_decode(const LzhCode *k, UncBitIn *bi)
{
    if (k->single >= 0) return k->single;
    return unc_canon_decode(&k->c, bi);
}

/* One code-length table: `bits`-wide count, then 3-bit lengths with a
 * unary tail, and — for the meta code only — a 2-bit run of zeros
 * after the fourth entry. XADLZHStaticHandle allocAndParseCodeOfWidth. */
static int lzh_read_code(LzhCode *k, UncBitIn *bi, uint8_t *lengths,
                         int bits, int32_t maxsyms, int32_t specialindex,
                         int16_t *symbuf, int32_t symcap)
{
    int32_t num = unc_bitin_bits(bi, bits);
    int32_t n = 0, i;

    if (num < 0) return bi->err;
    k->single = -1;
    if (num == 0) {
        int32_t val = unc_bitin_bits(bi, bits);
        if (val < 0) return bi->err;
        k->single = val;
        return UNC_OK;
    }
    if (num > maxsyms) return UNC_ERR_CORRUPT;

    for (i = 0; i < num; i++) lengths[i] = 0;
    while (n < num) {
        int32_t len = unc_bitin_bits(bi, 3);
        if (len < 0) return bi->err;
        if (len == 7) {
            for (;;) {
                int bit = unc_bitin_bit(bi);
                if (bit < 0) return bi->err;
                if (!bit) break;
                if (++len > UNC_CANON_MAX_BITS) return UNC_ERR_CORRUPT;
            }
        }
        lengths[n++] = (uint8_t)len;
        if (n == specialindex) {
            int32_t zeros = unc_bitin_bits(bi, 2);
            if (zeros < 0) return bi->err;
            if (n + zeros > num) return UNC_ERR_CORRUPT;
            for (i = 0; i < zeros; i++) lengths[n++] = 0;
        }
    }
    return unc_canon_build_ext(&k->c, lengths, num, symbuf, symcap);
}

/* The literal code, whose lengths are themselves coded with the meta
 * code: 0/1/2 are runs of zero lengths, anything else is length - 2.
 * XADLZHStaticHandle allocAndParseLiteralCode. */
static int lzh_read_literal_code(LzhStatic *s, UncBitIn *bi)
{
    int32_t num, n = 0, i;
    int err;

    err = lzh_read_code(&s->meta, bi, s->lengths, 5, LZH_NT, 3,
                        s->meta.c.symstore, UNC_CANON_MAX_SYMS);
    if (err != UNC_OK) return err;

    num = unc_bitin_bits(bi, 9);
    if (num < 0) return bi->err;
    s->lit.single = -1;
    if (num == 0) {
        int32_t val = unc_bitin_bits(bi, 9);
        if (val < 0) return bi->err;
        s->lit.single = val;
        return UNC_OK;
    }
    if (num > LZH_NC) return UNC_ERR_CORRUPT;

    for (i = 0; i < num; i++) s->lengths[i] = 0;
    while (n < num) {
        int32_t c = lzh_code_decode(&s->meta, bi);
        if (c < 0) return bi->err != UNC_OK ? bi->err : UNC_ERR_CORRUPT;
        if (c <= 2) {
            int32_t zeros;
            if (c == 0) zeros = 1;
            else if (c == 1) {
                zeros = unc_bitin_bits(bi, 4);
                if (zeros < 0) return bi->err;
                zeros += 3;
            } else {
                zeros = unc_bitin_bits(bi, 9);
                if (zeros < 0) return bi->err;
                zeros += 20;
            }
            if (n + zeros > num) return UNC_ERR_CORRUPT;
            for (i = 0; i < zeros; i++) s->lengths[n++] = 0;
        } else {
            if (c - 2 > UNC_CANON_MAX_BITS) return UNC_ERR_CORRUPT;
            s->lengths[n++] = (uint8_t)(c - 2);
        }
    }
    return unc_canon_build_ext(&s->lit.c, s->lengths, num, s->litsyms,
                               LZH_NC);
}

static int lzh_static(LzhOut *o, UncBufIn *in, uint32_t outlen, int wbits,
                      UncAlloc *al)
{
    LzhStatic *s;
    UncBitIn bi;
    uint8_t *w;
    uint32_t wsize = 1u << wbits, mask, pos = 0;
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
    { uint32_t i; for (i = 0; i < wsize; i++) w[i] = 0; }

    s->blocksize = s->blockpos = 0;
    s->lit.single = s->dist.single = s->meta.single = -1;
    unc_bitin_init(&bi, in);

    while (pos < outlen) {
        int32_t lit;

        if (s->blockpos >= s->blocksize) {
            int32_t bs = unc_bitin_bits(&bi, 16);
            if (bs < 0) { err = bi.err; break; }
            s->blocksize = bs;
            s->blockpos = 0;
            err = lzh_read_literal_code(s, &bi);
            if (err != UNC_OK) break;
            err = lzh_read_code(&s->dist, &bi, s->lengths,
                                wbits < 15 ? 4 : 5, LZH_NP, -1,
                                s->dist.c.symstore, UNC_CANON_MAX_SYMS);
            if (err != UNC_OK) break;
        }
        s->blockpos++;

        lit = lzh_code_decode(&s->lit, &bi);
        if (lit < 0) { err = bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT; break; }

        if (lit < 0x100) {
            w[pos++ & mask] = (uint8_t)lit;
            err = lzh_put(o, (uint8_t)lit);
            if (err != UNC_OK) break;
        } else {
            int32_t mlen = lit - 0x100 + 3;
            int32_t bits = lzh_code_decode(&s->dist, &bi);
            int32_t moff;
            uint32_t from;

            if (bits < 0) { err = bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT; break; }
            if (bits > 24) { err = UNC_ERR_CORRUPT; break; }
            if (bits == 0) moff = 1;
            else if (bits == 1) moff = 2;
            else {
                int32_t extra = unc_bitin_bits(&bi, bits - 1);
                if (extra < 0) { err = bi.err; break; }
                moff = (1 << (bits - 1)) + extra + 1;
            }
            from = pos - (uint32_t)moff;
            while (mlen-- > 0 && pos < outlen) {
                uint8_t b = w[from++ & mask];
                w[pos++ & mask] = b;
                err = lzh_put(o, b);
                if (err != UNC_OK) break;
            }
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
static int lzh_decode(UncCtx *c, const LzhEnt *e, LzhOut *o, uint8_t *iobuf,
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
        err = unc_lzdyn_decode(c->al, &bi, e->origsize, lzh_put, o);
    }
    else if (lzh_is(e->method, "-lh3-")) {
        UncBitIn bi;
        unc_bitin_init(&bi, &in);
        err = unc_lzst0_decode(c->al, &bi, e->origsize, lzh_put, o);
    }
    else if (lzh_is(e->method, "-lh1-")) {
        UncBitIn bi;
        unc_bitin_init(&bi, &in);
        err = unc_lzah_decode(c->al, &bi, e->origsize, UNC_LZAH_LH1, lzh_put, o);
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

    if (err == UNC_OK) err = lzh_flush(o);
    if (err != UNC_OK) return err;
    if (o->pos != e->origsize) return UNC_ERR_TRUNCATED;
    if (o->crc != e->crc) return UNC_ERR_CRC;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Headers                                                             */
/* ------------------------------------------------------------------ */

/* Append one path component, mapping the format's separators. LZH
 * names arrive with 0xff between directory components (the extended
 * header) or, in an old header, with a DOS backslash or a Unix slash;
 * XADLZHParser splits on exactly those. */
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
        n = UNC_NAME_MAX;
        if (type == 0x01 || type == 0x02) info->name_truncated = 1;
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
        /* A NUL inside the name field ends it; what follows is this
         * entry's comment, which has no home in UncEntryInfo and is
         * dropped (XADLZHParser puts it in XADCommentKey). */
        for (k = 0; k < namelen; k++)
            if (h[nameat + k] == 0) { namelen = k; break; }
        if (namelen > UNC_NAME_MAX) {
            namelen = UNC_NAME_MAX;
            info->name_truncated = 1;
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
             * the stream. Source: XADLZHParser.m, level 1 branch. */
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
     * UncEntryInfo is 296 bytes on the 68000 target (measured
     * 2026-08-27; the 280 that stood here was never right) and this
     * call chain has a 4 KB budget (CLAUDE.md, 68000 discipline). */
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
 * Source: reference/XADMaster/XADLZHParser.m recognizeFileWithHandle.
 *
 * With one addition, measured rather than copied: XADMaster's
 * recogniser accepts -lz0-, -lz4- and -lz5- but not -lzs-, while its
 * OWN parser has a decoder for -lzs- — so `unar` cannot open a file it
 * can decode (checked: "Couldn't recognize the archive format" on
 * lhasa's lzs specimens). This probe accepts it. */
int unc_lzh_probe(const uint8_t *head, int32_t len)
{
    if (len < 7) return 0;
    if (head[2] != '-' || head[6] != '-') return 0;
    if (head[3] == 'l' && head[4] == 'h') {
        uint8_t m = head[5];
        return (m >= '0' && m <= '7') || m == 'd';
    }
    if (head[3] == 'l' && head[4] == 'z') {
        uint8_t m = head[5];
        return m == '0' || m == '4' || m == '5' || m == 's';
    }
    return 0;
}

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
    uint32_t iocap = 4096;
    uint32_t pos = 0;
    int err = UNC_OK, any = 0;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap);
    if (!iobuf) return UNC_ERR_MEM;

    for (;;) {
        LzhEnt e;
        LzhOut o;
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

        lzh_out_init(&o, c, !c->opt.test_only);

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
            lzh_out_init(&o, c, 0);
            e.origsize = 128;
            (void)lzh_decode(c, &e, &o, iobuf, iocap);
            e.origsize = want;
            if (o.pos == 128) {
                uint32_t k;
                for (k = 0; k < 128; k++) mb[k] = o.buf[k];
                mac = unc_macbinary_probe(mb, 128, 0) ||
                      lzh_maclha_header(mb, e.origsize, info.name,
                                        info.name_len);
            }
            lzh_out_init(&o, c, !c->opt.test_only);
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
                o.dstart = ds; o.dend = ds + dlen;
                o.rstart = rs; o.rend = rs + rlen;
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
            if (est == UNC_ERR_ABORTED || est == UNC_ERR_SINK ||
                est == UNC_ERR_IO) {
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

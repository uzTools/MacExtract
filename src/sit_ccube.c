/*
 * sit_ccube.c — the payload a StuffIt 2.0 `Photoshop/JPEG Lossy`
 * Optimizer stores: C-Cube's JPEG, inside a TIFF, behind an 80-byte
 * module header.
 *
 * Source: two halves, and only one of them is published.
 *
 *   * the ENTROPY layer is ITU-T T.81 (1992), in
 *     `reference/notes/itu-t81.pdf`: Annex F's BITS/HUFFVAL decoding
 *     tables (F.2.2.3, Figures F.15-F.16, built in `cc_huff_build`),
 *     the category-coded DC difference and AC run/size pairs, `FF 00`
 *     stuffing (F.1.2.3) and the zig-zag order of Figure A.6
 *     (`cc_zig`).
 *   * everything C-Cube added is the module's own `CCOD` resource,
 *     disassembled (`tools/ccube/m68ktrace.py`): the IDCT below, the
 *     3-MCU restart segments that do NOT reset the DC predictor, the
 *     padded tile rows, and the TIFF private tags. No spec states any
 *     of it — FORMATS.md, *What an Optimizer did to the fork*.
 *
 * The prototype this is transcribed from is `tools/ccube/decode.py`,
 * which reproduces StuffIt Deluxe 2.0.1's own restored file byte for
 * byte; nothing here is guessed, and `tools/run_sitopt.py` grades this
 * engine against the same specimen.
 *
 * WHAT THE FORMAT IS, in the order this file uses it. Measured on 36
 * payloads StuffIt Deluxe 2.0.1 wrote, every one decoded here to its own
 * restored file byte for byte (FORMATS.md, *What an Optimizer did to
 * the fork*; tools/run_sitcombo.py):
 *
 *   * 80 bytes of module header: the module's colour code at +0 (1
 *     RGB, 2 HSB, 3 HSL, 4 CMYK, 5 channels coded one by one), the
 *     channel count at +2, WIDTH at +4 and height at +6 — the other
 *     way round from what tools/ccube/decode.py said, which only ever
 *     saw a square — the quality at
 *     +8, the length after the header at +10, then the OFFSET OF EACH
 *     TIFF from +14 on, ending with the total. An RGB document is one
 *     three-channel TIFF; CMYK is a three-channel one for C, M and Y
 *     and a one-channel one for K; everything else is one one-channel
 *     TIFF per channel. Their planes, in order, are the document's.
 *   * each TIFF (`MM\0*`) has `Compression` **32865**, C-Cube's own
 *     code from before TIFF 6.0 gave old-style JPEG the number 6;
 *     `libtiff` will not read it. Its offsets are its own.
 *   * one quantisation table per channel at private tag **33606**, 64
 *     words, IN ZIGZAG ORDER; the DC Huffman tables at **33607** and
 *     the AC at **33608**, `BITS[16]` then `HUFFVAL`. One channel's
 *     tag holds the table's offset; three channels' holds the offset
 *     of three offsets.
 *   * `TileOffsets` (324) holds the offset of an ARRAY of segment
 *     offsets even when it declares one — which TIFF says should be
 *     the offset itself; 7x5 and 1x1 documents are what showed it.
 *   * a three-channel MCU is **2 luma blocks, one Cb, one Cr — 4:2:2**,
 *     16x8 pixels; a one-channel MCU is one 8x8 block.
 *   * the row layout is C3a+0x4366's arithmetic, read and then matched
 *     against every width from 1 to 512: **(w + 39) / 40 restart
 *     segments per MCU row**, each of **(segs * mcu + w - 1) / (segs *
 *     mcu)** MCUs, the encoder coding the padding past the image flat.
 *     So a 256-wide row is 7 segments of 3 MCUs = 336 pixels, which is
 *     the one width this file assumed until 2026-10-11.
 *   * each segment ends `FF Dn` and **one pad byte**; the restart
 *     index runs continuously mod 8 and **does not reset the DC
 *     predictors**.
 *   * chroma is upsampled by INTERPOLATION in the module's own 16-bit
 *     words — an odd column is the mean of its two neighbours' samples
 *     at full precision, the last one past the image's own half-width
 *     (rounded up) repeats — and converted at CCOD+0xd98, whose
 *     arithmetic reduces to `y + (k * c2) >> 15` with `c2` that
 *     doubled chroma. Measured: a grey document cannot tell this from
 *     replication, which is what this file did until 2026-10-11, and
 *     every coloured one can.
 *   * the output is PLANAR, which is why this decodes a TIFF's stream
 *     once per plane rather than buffering the image. Memory is one
 *     MCU row, not one image.
 *
 * 68000 discipline: byte-wise big-endian reads, no recursion, 32-bit
 * arithmetic in the transform, every allocation through the caller's
 * UncAlloc and a per-entry error if one fails.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* The module's cosine table, cos(k*pi/16) at 2^9, written as fifteen
 * immediates at CCOD+0x2f40. Nine bits is the whole precision of this
 * transform. */
#define CC_C1 502
#define CC_C2 473
#define CC_C3 426
#define CC_C4 362
#define CC_C5 284
#define CC_C6 196
#define CC_C7 100

#define CC_MCU_H    8
#define CC_HDR     80        /* the module's own header             */
#define CC_MAXTIFF 16        /* offsets that fit in it after +14    */

#define CC_COMPRESSION 32865u

/* Zigzag, as JPEG's and as the quantisation tables are stored. */
static const uint8_t cc_zig[64] = {
     0,  1,  8, 16,  9,  2,  3, 10, 17, 24, 32, 25, 18, 11,  4,  5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13,  6,  7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63
};

/* ------------------------------------------------------------------ */
/* Huffman                                                            */
/* ------------------------------------------------------------------ */

typedef struct CcHuff {
    int32_t  mincode[17];
    int32_t  maxcode[17];   /* -1 when no code of that length */
    int16_t  valptr[17];
    uint8_t  vals[256];
} CcHuff;

/* BITS[16] then HUFFVAL, the JPEG way (T.81 Annex C): codes of each
 * length run consecutively, in the order HUFFVAL gives them, which is
 * NOT the order a symbol-sorted canonical builder would use — so this
 * cannot borrow unc_canon_build. */
static int cc_huff(CcHuff *h, const uint8_t *p, uint32_t avail)
{
    int32_t code = 0;
    int32_t k = 0;
    int l;
    uint32_t total = 0;

    if (avail < 16) return UNC_ERR_TRUNCATED;
    for (l = 0; l < 16; l++) total += p[l];
    if (total == 0 || total > 256 || avail < 16 + total)
        return UNC_ERR_CORRUPT;
    for (l = 1; l <= 16; l++) {
        int n = p[l - 1];
        if (n == 0) {
            h->maxcode[l] = -1;
        } else {
            h->valptr[l] = (int16_t)k;
            h->mincode[l] = code;
            code += n;
            k += n;
            h->maxcode[l] = code - 1;
        }
        code <<= 1;
        if (code > (1L << 17)) return UNC_ERR_CORRUPT;
    }
    for (k = 0; k < (int32_t)total; k++) h->vals[k] = p[16 + k];
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* The entropy stream                                                 */
/* ------------------------------------------------------------------ */

typedef struct CcBits {
    const uint8_t *p;
    uint32_t       len, pos;
    uint32_t       bitbuf;
    int            nbits;
    int            err;
} CcBits;

static void cc_bits_at(CcBits *b, const uint8_t *p, uint32_t len, uint32_t pos)
{
    b->p = p; b->len = len; b->pos = pos;
    b->bitbuf = 0; b->nbits = 0; b->err = UNC_OK;
}

/* One byte of entropy data, undoing JPEG's FF 00 stuffing. A marker
 * ends the segment, and the caller is the one that knows when to
 * expect it, so this simply refuses to read past one. */
static int cc_byte(CcBits *b)
{
    int v;
    if (b->pos >= b->len) { b->err = UNC_ERR_TRUNCATED; return -1; }
    v = b->p[b->pos++];
    if (v == 0xFF) {
        if (b->pos >= b->len) { b->err = UNC_ERR_TRUNCATED; return -1; }
        if (b->p[b->pos] == 0x00) b->pos++;
        else { b->err = UNC_ERR_CORRUPT; return -1; }
    }
    return v;
}

static int32_t cc_get(CcBits *b, int n)
{
    int32_t v;
    while (b->nbits < n) {
        int c = cc_byte(b);
        if (c < 0) return 0;
        b->bitbuf = (b->bitbuf << 8) | (uint32_t)c;
        b->nbits += 8;
    }
    b->nbits -= n;
    v = (int32_t)((b->bitbuf >> b->nbits) & ((1UL << n) - 1UL));
    return v;
}

static int cc_decode(CcBits *b, const CcHuff *h)
{
    int32_t code = 0;
    int l;
    for (l = 1; l <= 16; l++) {
        code = (code << 1) | cc_get(b, 1);
        if (b->err != UNC_OK) return -1;
        if (h->maxcode[l] >= 0 && code <= h->maxcode[l])
            return h->vals[h->valptr[l] + (code - h->mincode[l])];
    }
    b->err = UNC_ERR_CORRUPT;
    return -1;
}

/* T.81's EXTEND. */
static int32_t cc_extend(int32_t v, int n)
{
    if (n == 0) return 0;
    return v < ((int32_t)1 << (n - 1))
           ? v - ((int32_t)1 << n) + 1 : v;
}

/* Byte-align, then step over `FF Dn` and the single pad byte that
 * follows it. The restart INDEX is not checked against a counter: it
 * runs continuously mod 8 across the whole image and nothing here
 * needs it. */
static int cc_restart(CcBits *b)
{
    b->nbits = 0;
    b->bitbuf = 0;
    if (b->pos + 2 > b->len) return UNC_ERR_TRUNCATED;
    if (b->p[b->pos] != 0xFF ||
        b->p[b->pos + 1] < 0xD0 || b->p[b->pos + 1] > 0xD7)
        return UNC_ERR_CORRUPT;
    b->pos += 2;
    if (b->pos < b->len) b->pos++;          /* the pad byte */
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* The transform, transcribed from CCOD+0x2f3c                        */
/* ------------------------------------------------------------------ */

/* asr.l #9, then addq.l #1 when the result is negative — which rounds
 * toward zero except on exact negative multiples of 512, where it
 * overshoots by one. That quirk is the module's and reproducing it is
 * the whole point. */
static UNC_HOT int32_t cc_sh(int32_t x)
{
    int32_t v = x >> 9;
    return v < 0 ? v + 1 : v;
}

static UNC_HOT void cc_idct1(const int32_t *x, int32_t *y)
{
    int32_t a2, a3, a4, a5, a6, a7, e0, e1;
    int32_t b0, b1, b2, b3, b4, b5, b6, b7, d5, d6;

    a4 = cc_sh(CC_C7 * x[1] - CC_C1 * x[7]);
    a7 = cc_sh(CC_C7 * x[7] + CC_C1 * x[1]);
    a5 = cc_sh(CC_C3 * x[5] - CC_C5 * x[3]);
    a6 = cc_sh(CC_C5 * x[5] + CC_C3 * x[3]);
    e0 = cc_sh(CC_C4 * (x[0] + x[4]));
    e1 = cc_sh(CC_C4 * (x[0] - x[4]));
    a2 = cc_sh(CC_C6 * x[2] - CC_C2 * x[6]);
    a3 = cc_sh(CC_C2 * x[2] + CC_C6 * x[6]);

    b4 = a4 + a5; b5 = a4 - a5;
    b6 = a7 - a6; b7 = a7 + a6;
    b0 = e0 + a3; b1 = e1 + a2;
    b2 = e1 - a2; b3 = e0 - a3;

    d5 = cc_sh(CC_C4 * (b6 - b5));
    d6 = cc_sh(CC_C4 * (b6 + b5));

    y[0] = b0 + b7; y[1] = b1 + d6; y[2] = b2 + d5; y[3] = b3 + b4;
    y[4] = b3 - b4; y[5] = b2 - d5; y[6] = b1 - d6; y[7] = b0 - b7;
}

/* Columns first and then rows, which is what the de-zigzag table's
 * stride says: it is gathered at 16 bytes with the loop index at 2,
 * which is a column of an 8x8 word array. The two passes are the same
 * code in the module and are the same here. */
static void cc_idct(int32_t *blk)
{
    int32_t col[8], out[8];
    int i, r;

    /* The pre-scale. Written as a multiply because a dequantised
     * coefficient is signed and `<< 3` on a negative value is undefined
     * — UBSan said so on the first full run. Every 68000 compiler turns
     * `* 8` into the same three shifts. */
    for (i = 0; i < 64; i++) blk[i] *= 8;
    for (i = 0; i < 8; i++) {
        for (r = 0; r < 8; r++) col[r] = blk[r * 8 + i];
        cc_idct1(col, out);
        for (r = 0; r < 8; r++) blk[r * 8 + i] = out[r];
    }
    for (r = 0; r < 8; r++) {
        cc_idct1(blk + r * 8, out);
        for (i = 0; i < 8; i++) blk[r * 8 + i] = out[i];
    }
}

/* (x + 16) >> 5, the level shift and the clamp.
 *
 * **No round-toward-zero correction here**, unlike every rotation in
 * the network above. This was recorded as unexplained until
 * 2026-10-02, because CCOD+0x3826 was read as applying one: a second
 * subject settles it. A dense drawing reaches `v < 0` 9,645 times
 * against the first subject's 709, and the correction is wrong on
 * every one of them while this is byte-exact on both — so the
 * attribution was a misreading of the disassembly, not a branch these
 * images miss (BLOCKERS.md, *Withdrawn claims*; FORMATS.md, *What an
 * Optimizer did to the fork*). Do not "fix" this to match the asm. */
static int cc_sample(int32_t x)
{
    int32_t v = ((x + 16) >> 5) + 128;
    return v < 0 ? 0 : (v > 255 ? 255 : (int)v);
}

/* ------------------------------------------------------------------ */
/* The TIFF the module wraps it in                                    */
/* ------------------------------------------------------------------ */

typedef struct CcImage {
    const uint8_t *t;        /* one TIFF, at its offset in the payload */
    uint32_t       len;
    uint32_t       w, h;
    unsigned       spp;      /* 1 or 3 */
    uint32_t       qoff[3], dcoff[3], acoff[3];
    uint32_t       data;     /* first segment's offset */
} CcImage;

static uint32_t cc_u16(const uint8_t *p) { return ((uint32_t)p[0] << 8) | p[1]; }
static uint32_t cc_u32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | p[3];
}

/* A table tag: one offset per channel. A one-channel TIFF's entry
 * holds the offset itself, as TIFF says; three channels' holds the
 * offset of three. */
static int cc_tables(const CcImage *im, const uint8_t *e, uint32_t *out)
{
    uint32_t cnt = cc_u32(e + 4), off = cc_u32(e + 8), i;
    if (cnt != im->spp) return UNC_ERR_CORRUPT;
    if (cnt == 1) { out[0] = off; return UNC_OK; }
    if (off > im->len || im->len - off < 4 * cnt) return UNC_ERR_CORRUPT;
    for (i = 0; i < cnt; i++) out[i] = cc_u32(im->t + off + i * 4);
    return UNC_OK;
}

static int cc_parse(CcImage *im)
{
    uint32_t ifd, n, i, seg_off = 0, seg_cnt = 0, q = 0, dc = 0, ac = 0;
    int seen = 0;

    if (im->len < 16 || im->t[0] != 'M' || im->t[1] != 'M' ||
        cc_u16(im->t + 2) != 42)
        return UNC_ERR_UNSUPPORTED;
    ifd = cc_u32(im->t + 4);
    if (ifd > im->len || im->len - ifd < 2) return UNC_ERR_CORRUPT;
    n = cc_u16(im->t + ifd);
    if (n > 64 || ifd + 2 + n * 12 > im->len) return UNC_ERR_CORRUPT;
    im->w = im->h = 0;
    im->spp = 0;
    /* Two passes: the table tags' shape depends on SamplesPerPixel,
     * and nothing says it comes first. */
    for (i = 0; i < n; i++) {
        const uint8_t *e = im->t + ifd + 2 + i * 12;
        switch (cc_u16(e)) {
        case 256: im->w = cc_u16(e + 8); break;
        case 257: im->h = cc_u16(e + 8); break;
        case 259:
            if (cc_u16(e + 8) != CC_COMPRESSION) return UNC_ERR_UNSUPPORTED;
            seen |= 1;
            break;
        case 277:
            im->spp = cc_u16(e + 8);
            if (im->spp != 1 && im->spp != 3) return UNC_ERR_UNSUPPORTED;
            break;
        case 324:
            seg_cnt = cc_u32(e + 4);
            seg_off = cc_u32(e + 8);
            seen |= 2;
            break;
        case 33606: q = i + 1; break;
        case 33607: dc = i + 1; break;
        case 33608: ac = i + 1; break;
        default: break;
        }
    }
    if (!im->spp || !q || !dc || !ac) return UNC_ERR_CORRUPT;
    {
        const uint8_t *base = im->t + ifd + 2;
        int err = cc_tables(im, base + (q - 1) * 12, im->qoff);
        if (err == UNC_OK) err = cc_tables(im, base + (dc - 1) * 12, im->dcoff);
        if (err == UNC_OK) err = cc_tables(im, base + (ac - 1) * 12, im->acoff);
        if (err != UNC_OK) return err;
    }
    if (seen != 3 || im->w == 0 || im->h == 0 || seg_cnt == 0)
        return UNC_ERR_CORRUPT;
    /* The offset of the segment offsets, whatever the count says: a
     * one-segment image declares 1 and still points at an array. */
    if (seg_off > im->len || im->len - seg_off < 4) return UNC_ERR_CORRUPT;
    im->data = cc_u32(im->t + seg_off);
    if (im->data >= im->len) return UNC_ERR_CORRUPT;
    /* The engine's own ceiling, on the WIDTH only: a row buffer is 16
     * bytes per padded pixel of width, so a silly width is refused here
     * rather than in the allocator, and with it capped, w * h * channels
     * fits a uint32 for any height a TIFF short can state. The height
     * was capped at 8,192 too until 2026-10-15, for no reason anything
     * recorded, and refused a 16 x 8,208 document StuffIt Deluxe 2.0.1
     * itself compresses and restores (DECISIONS.md 2026-10-15, *the
     * height nothing needed*). */
    if (im->w > 8192u) return UNC_ERR_TOOLARGE;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* One plane                                                          */
/* ------------------------------------------------------------------ */

typedef struct CcState {
    CcHuff   dc[3], ac[3];
    uint16_t q[3][64];
    uint8_t *yrow;           /* stride wide, 8 rows, samples 0..255   */
    uint8_t *cbrow, *crrow;  /* half the stride, 8 rows               */
    uint32_t segs, per_seg;  /* restart segments per row, MCUs in each */
    uint32_t mcu_w;          /* 16 for three channels, 8 for one      */
    uint32_t stride;         /* the coded row, in pixels              */
} CcState;

/* One 8x8 block: entropy, dequantise, de-zigzag, transform. */
static int cc_block(CcBits *b, CcState *s, int comp, int32_t *pred,
                    int32_t *blk)
{
    int32_t co[64];
    int i, k, sym, run, size;

    for (i = 0; i < 64; i++) co[i] = 0;
    sym = cc_decode(b, &s->dc[comp]);
    if (sym < 0) return b->err != UNC_OK ? b->err : UNC_ERR_CORRUPT;
    if (sym > 15) return UNC_ERR_CORRUPT;
    *pred += cc_extend(cc_get(b, sym), sym);
    co[0] = *pred;
    k = 1;
    while (k < 64) {
        sym = cc_decode(b, &s->ac[comp]);
        if (sym < 0) return b->err != UNC_OK ? b->err : UNC_ERR_CORRUPT;
        run = sym >> 4;
        size = sym & 15;
        if (size == 0) {
            if (run == 15) { k += 16; continue; }
            break;                                   /* EOB */
        }
        k += run;
        if (k > 63) break;
        co[k] = cc_extend(cc_get(b, size), size);
        k++;
    }
    if (b->err != UNC_OK) return b->err;
    for (i = 0; i < 64; i++) blk[i] = 0;
    for (i = 0; i < 64; i++)
        blk[cc_zig[i]] = co[i] * (int32_t)s->q[comp][i];
    cc_idct(blk);
    return UNC_OK;
}

/* Twice a chroma sample's distance from 128, at column x of an image w
 * wide: an even column is its own sample, an odd one the sum of the
 * two either side — the mean, kept at the module's full precision —
 * and the last odd column of the image repeats its left neighbour,
 * because the module stops at its own half-width, rounded up.
 * Measured: every width from 1 to 512 is byte-exact this way, and a
 * last column interpolated into the padding is not (C256, 642 bytes). */
static int32_t cc_chroma2(const uint8_t *row, uint32_t x, uint32_t w)
{
    uint32_t j = x >> 1;
    int32_t a = (int32_t)row[j] - 128;
    if (!(x & 1)) return a + a;
    if (j + 1 < (w + 1) / 2) return a + ((int32_t)row[j + 1] - 128);
    return a + a;
}

static uint8_t cc_clamp(int32_t v)
{
    return v < 0 ? 0 : (v > 255 ? 255 : (uint8_t)v);
}

/* Decode one TIFF's stream once, writing plane `plane` of it (0=R,
 * 1=G, 2=B for three channels; 0 for one) to the fork. Once per plane
 * rather than one buffered image: the output is planar and an MCU row
 * is all this needs to hold. */
static int cc_plane(const CcImage *im, CcState *s, UncForkOut *f, int plane)
{
    CcBits b;
    int32_t pred[3];
    int32_t blk[64];
    uint32_t mrows = (im->h + CC_MCU_H - 1) / CC_MCU_H;
    uint32_t mr, m, seg, x, y;
    int ncomp = im->spp == 3 ? 3 : 1;
    int err;

    cc_bits_at(&b, im->t, im->len, im->data);
    pred[0] = pred[1] = pred[2] = 0;

    for (mr = 0; mr < mrows; mr++) {
        for (seg = 0; seg < s->segs; seg++) {
            for (m = 0; m < s->per_seg; m++) {
                uint32_t mx = seg * s->per_seg + m;
                int comp, kb;
                for (comp = 0; comp < ncomp; comp++) {
                    int nb = (comp == 0 && ncomp == 3) ? 2 : 1;
                    for (kb = 0; kb < nb; kb++) {
                        uint8_t *d;
                        uint32_t ox, st;
                        err = cc_block(&b, s, comp, &pred[comp], blk);
                        if (err != UNC_OK) return err;
                        if (comp == 0) {
                            d = s->yrow;
                            st = s->stride;
                            ox = mx * s->mcu_w + (uint32_t)kb * 8;
                        } else {
                            d = comp == 1 ? s->cbrow : s->crrow;
                            st = s->stride / 2;
                            ox = mx * 8;
                        }
                        for (y = 0; y < 8; y++)
                            for (x = 0; x < 8; x++)
                                d[y * st + ox + x] =
                                    (uint8_t)cc_sample(blk[y * 8 + x]);
                    }
                }
            }
            err = cc_restart(&b);
            if (err != UNC_OK) return err;
        }
        /* The MCU row is complete: emit its rows of this plane. The
         * colour conversion is CCOD+0xd98's: its 16-bit words reduce
         * to `y + (k * c2) >> 15`, k being 1.402, 1.772 and the two
         * green terms at 2^14 and c2 the doubled chroma above. */
        for (y = 0; y < 8; y++) {
            uint32_t row = mr * 8 + y;
            const uint8_t *yr = s->yrow + y * s->stride;
            const uint8_t *cb = s->cbrow, *cr = s->crrow;
            if (row >= im->h) break;
            if (ncomp == 3) {
                cb += y * (s->stride / 2);
                cr += y * (s->stride / 2);
            }
            for (x = 0; x < im->w; x++) {
                int32_t v = yr[x];
                if (ncomp == 3) {
                    if (plane == 0)
                        v += ((int32_t)22965 * cc_chroma2(cr, x, im->w)) >> 15;
                    else if (plane == 1)
                        v += ((int32_t)-11703 * cc_chroma2(cr, x, im->w) -
                              (int32_t)5631 * cc_chroma2(cb, x, im->w)) >> 15;
                    else
                        v += ((int32_t)29036 * cc_chroma2(cb, x, im->w)) >> 15;
                }
                if (unc_fork_put(f, cc_clamp(v)) != UNC_OK)
                    return UNC_ERR_SINK;
            }
        }
    }
    return UNC_OK;
}

/* One TIFF: its tables, its row buffers, and its planes in order. */
static int cc_tiff(UncCtx *c, const CcImage *im, UncForkOut *f)
{
    CcState *s;
    uint32_t need, unit;
    int err = UNC_OK, i, j, planes = im->spp == 3 ? 3 : 1;

    s = (CcState *)unc_alloc(c->al, (uint32_t)sizeof *s);
    if (!s) return UNC_ERR_MEM;
    /* C3a+0x4366: the row is cut into (w + 39) / 40 restart segments
     * and each holds as many MCUs as it takes to cover the width. */
    s->mcu_w = im->spp == 3 ? 16 : 8;
    s->segs = (im->w + 39) / 40;
    unit = s->segs * s->mcu_w;
    s->per_seg = (unit + im->w - 1) / unit;
    s->stride = unit * s->per_seg;
    need = s->stride * 8u;
    if (im->spp == 3) need += s->stride * 8u;          /* both chroma */
    s->yrow = (uint8_t *)unc_alloc(c->al, need);
    if (!s->yrow) { unc_free(c->al, s); return UNC_ERR_MEM; }
    s->cbrow = s->crrow = NULL;
    if (im->spp == 3) {
        s->cbrow = s->yrow + s->stride * 8u;
        s->crrow = s->cbrow + (s->stride / 2) * 8u;
    }

    for (i = 0; i < (int)im->spp && err == UNC_OK; i++) {
        for (j = 0; j < 64; j++) {
            uint32_t o = im->qoff[i] + (uint32_t)j * 2;
            if (o > im->len || im->len - o < 2) { err = UNC_ERR_CORRUPT; break; }
            s->q[i][j] = (uint16_t)cc_u16(im->t + o);
        }
        if (err != UNC_OK) break;
        if (im->dcoff[i] >= im->len || im->acoff[i] >= im->len) {
            err = UNC_ERR_CORRUPT;
            break;
        }
        err = cc_huff(&s->dc[i], im->t + im->dcoff[i], im->len - im->dcoff[i]);
        if (err == UNC_OK)
            err = cc_huff(&s->ac[i], im->t + im->acoff[i],
                          im->len - im->acoff[i]);
    }
    for (i = 0; i < planes && err == UNC_OK; i++)
        err = cc_plane(im, s, f, i);

    unc_free(c->al, s->yrow);
    unc_free(c->al, s);
    return err;
}

/* ------------------------------------------------------------------ */
/* Entry point                                                        */
/* ------------------------------------------------------------------ */

int unc_ccube_decode(UncCtx *c, UncFork fork, const uint8_t *stored,
                     uint32_t storedlen, uint32_t outlen,
                     uint8_t *obuf, uint32_t ocap)
{
    UncForkOut f;
    uint32_t off[CC_MAXTIFF + 1];
    uint32_t chans, w, h, total, k, n = 0, got = 0;
    int err = UNC_OK;

    /* The module's header: which TIFFs, and where. */
    if (storedlen < CC_HDR + 16) return UNC_ERR_TRUNCATED;
    chans = cc_u16(stored + 2);
    w = cc_u16(stored + 4);
    h = cc_u16(stored + 6);
    total = cc_u32(stored + 10);
    if (total > storedlen - CC_HDR) return UNC_ERR_TRUNCATED;
    total += CC_HDR;
    for (k = 14; k + 4 <= CC_HDR; k += 4) {
        uint32_t v = cc_u32(stored + k);
        if (v >= total) break;
        if (v < CC_HDR || (n && v <= off[n - 1]) || n == CC_MAXTIFF)
            return UNC_ERR_CORRUPT;
        off[n++] = v;
    }
    if (n == 0 || chans == 0 || chans > 4) return UNC_ERR_CORRUPT;
    if (w > 8192u) return UNC_ERR_TOOLARGE;      /* see cc_parse */
    off[n] = total;
    if ((uint32_t)w * h * chans != outlen) return UNC_ERR_CORRUPT;

    unc_fork_out(&f, c, fork, !c->opt.test_only, UNC_CK_CRC16_ARC, obuf, ocap);
    for (k = 0; k < n && err == UNC_OK; k++) {
        CcImage im;
        im.t = stored + off[k];
        im.len = off[k + 1] - off[k];
        err = cc_parse(&im);
        if (err != UNC_OK) break;
        /* Every TIFF is the whole document's size, and between them
         * they hold exactly its channels. */
        got += im.spp;
        if (im.w != w || im.h != h || got > chans) { err = UNC_ERR_CORRUPT; break; }
        err = cc_tiff(c, &im, &f);
    }
    if (err == UNC_OK && got != chans) err = UNC_ERR_CORRUPT;
    if (err == UNC_OK) err = unc_fork_flush(&f);
    return err;
}

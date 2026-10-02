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
 * WHAT THE FORMAT IS, in the order this file uses it:
 *
 *   * 80 bytes of module header, then a TIFF (`MM\0*`). `Compression`
 *     is **32865**, C-Cube's own code from before TIFF 6.0 gave
 *     old-style JPEG the number 6; `libtiff` will not read it.
 *   * three quantisation tables at private tag **33606**, 64 words
 *     each, IN ZIGZAG ORDER; three DC Huffman tables at **33607** and
 *     three AC at **33608**, `BITS[16]` then `HUFFVAL`, 256 symbols
 *     apiece.
 *   * an MCU is **2 luma blocks, one Cb, one Cr — 4:2:2**, 16x8
 *     pixels, and a restart segment is **exactly 3 MCUs**.
 *   * a tile row is **7 segments = 21 MCUs = 336 pixels**: the encoder
 *     pads the width out and codes the padding flat, so a decoder
 *     decodes 21 MCUs of every row and keeps the ones inside the
 *     image.
 *   * each segment ends `FF Dn` and **one pad byte**; the restart
 *     index runs continuously mod 8 and **does not reset the DC
 *     predictors**.
 *   * the output is PLANAR — R, then G, then B, each a whole plane —
 *     which is why this decodes the stream once per plane rather than
 *     buffering the image. Memory is then one MCU row, not one image.
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

#define CC_MCU_W   16        /* 4:2:2 */
#define CC_MCU_H    8
#define CC_PER_SEG  3        /* MCUs between restart markers */
#define CC_SEG_ROW  7        /* segments per tile row */
#define CC_MCU_ROW  (CC_PER_SEG * CC_SEG_ROW)       /* 21 */
#define CC_PAD_W    (CC_MCU_ROW * CC_MCU_W)         /* 336 */

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
 * **CCOD+0x3826 applies the same round-toward-zero correction here
 * that every rotation applies, and the output is exact only WITHOUT
 * it**: with it, 709 of 65,536 luma samples miss by one. Measured, and
 * unexplained — FORMATS.md says so too rather than smoothing it over. */
static int cc_sample(int32_t x)
{
    int32_t v = ((x + 16) >> 5) + 128;
    return v < 0 ? 0 : (v > 255 ? 255 : (int)v);
}

/* ------------------------------------------------------------------ */
/* The TIFF the module wraps it in                                    */
/* ------------------------------------------------------------------ */

typedef struct CcImage {
    const uint8_t *t;        /* the TIFF, at the module header + 80 */
    uint32_t       len;
    uint32_t       w, h;
    uint32_t       qoff[3], dcoff[3], acoff[3];
    uint32_t       data;     /* first segment's offset */
} CcImage;

static uint32_t cc_u16(const uint8_t *p) { return ((uint32_t)p[0] << 8) | p[1]; }
static uint32_t cc_u32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | p[3];
}

static int cc_triple(const CcImage *im, const uint8_t *e, uint32_t *out)
{
    uint32_t cnt = cc_u32(e + 4), off, i;
    if (cnt != 3) return UNC_ERR_CORRUPT;
    off = cc_u32(e + 8);
    if (off > im->len || im->len - off < 12) return UNC_ERR_CORRUPT;
    for (i = 0; i < 3; i++) out[i] = cc_u32(im->t + off + i * 4);
    return UNC_OK;
}

static int cc_parse(CcImage *im)
{
    uint32_t ifd, n, i;
    int seen = 0;

    if (im->len < 16 || im->t[0] != 'M' || im->t[1] != 'M' ||
        cc_u16(im->t + 2) != 42)
        return UNC_ERR_UNSUPPORTED;
    ifd = cc_u32(im->t + 4);
    if (ifd + 2 > im->len) return UNC_ERR_CORRUPT;
    n = cc_u16(im->t + ifd);
    if (n > 64 || ifd + 2 + n * 12 > im->len) return UNC_ERR_CORRUPT;
    im->w = im->h = 0;
    for (i = 0; i < n; i++) {
        const uint8_t *e = im->t + ifd + 2 + i * 12;
        uint32_t tag = cc_u16(e);
        int err = UNC_OK;
        switch (tag) {
        case 256: im->w = cc_u16(e + 8); break;
        case 257: im->h = cc_u16(e + 8); break;
        case 259:
            if (cc_u16(e + 8) != CC_COMPRESSION) return UNC_ERR_UNSUPPORTED;
            seen |= 1;
            break;
        case 277:
            if (cc_u16(e + 8) != 3) return UNC_ERR_UNSUPPORTED;
            break;
        case 324: {                    /* the first segment's offset */
            uint32_t cnt = cc_u32(e + 4), off = cc_u32(e + 8);
            if (cnt == 0) return UNC_ERR_CORRUPT;
            if (cnt == 1) im->data = off;
            else {
                if (off > im->len || im->len - off < 4) return UNC_ERR_CORRUPT;
                im->data = cc_u32(im->t + off);
            }
            seen |= 2;
            break;
        }
        case 33606: err = cc_triple(im, e, im->qoff); seen |= 4; break;
        case 33607: err = cc_triple(im, e, im->dcoff); seen |= 8; break;
        case 33608: err = cc_triple(im, e, im->acoff); seen |= 16; break;
        default: break;
        }
        if (err != UNC_OK) return err;
    }
    if (seen != 31 || im->w == 0 || im->h == 0) return UNC_ERR_CORRUPT;
    if (im->data >= im->len) return UNC_ERR_CORRUPT;
    /* The engine's own ceiling: a fork is uint32 and a row buffer is
     * 16 bytes per padded pixel of width, so a silly width is refused
     * here rather than in the allocator. */
    if (im->w > 8192u || im->h > 8192u) return UNC_ERR_TOOLARGE;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* One plane                                                          */
/* ------------------------------------------------------------------ */

typedef struct CcState {
    CcHuff   dc[3], ac[3];
    uint16_t q[3][64];
    uint8_t *yrow;           /* CC_PAD-wide, 8 rows, samples 0..255   */
    int8_t  *cbrow, *crrow;  /* half width, 8 rows, centred           */
    uint32_t stride;         /* padded width in pixels                */
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

/* Decode the whole stream once, writing plane `plane` (0=R, 1=G, 2=B)
 * to the fork. Three passes rather than one buffered image: the output
 * is planar and an MCU row is all this needs to hold. */
static int cc_plane(UncCtx *c, const CcImage *im, CcState *s,
                    UncForkOut *f, int plane)
{
    CcBits b;
    int32_t pred[3];
    int32_t blk[64];
    uint32_t mrows = (im->h + CC_MCU_H - 1) / CC_MCU_H;
    uint32_t mr, m, seg, i, x, y;
    int err;

    cc_bits_at(&b, im->t, im->len, im->data);
    pred[0] = pred[1] = pred[2] = 0;

    for (mr = 0; mr < mrows; mr++) {
        for (seg = 0; seg < CC_SEG_ROW; seg++) {
            for (m = 0; m < CC_PER_SEG; m++) {
                uint32_t mx = seg * CC_PER_SEG + m;
                int comp, kb;
                for (comp = 0; comp < 3; comp++) {
                    int nb = comp == 0 ? 2 : 1;
                    for (kb = 0; kb < nb; kb++) {
                        err = cc_block(&b, s, comp, &pred[comp], blk);
                        if (err != UNC_OK) return err;
                        if (mx * CC_MCU_W >= s->stride) continue;
                        if (comp == 0) {
                            uint32_t ox = mx * CC_MCU_W + (uint32_t)kb * 8;
                            for (y = 0; y < 8; y++)
                                for (x = 0; x < 8; x++)
                                    s->yrow[y * s->stride + ox + x] =
                                        (uint8_t)cc_sample(blk[y * 8 + x]);
                        } else {
                            uint32_t ox = mx * 8;
                            int8_t *d = comp == 1 ? s->cbrow : s->crrow;
                            for (y = 0; y < 8; y++)
                                for (x = 0; x < 8; x++)
                                    d[y * (s->stride / 2) + ox + x] =
                                        (int8_t)(cc_sample(blk[y * 8 + x]) - 128);
                        }
                    }
                }
            }
            err = cc_restart(&b);
            if (err != UNC_OK) return err;
        }
        /* The MCU row is complete: emit its rows of this plane.
         * The module's own YCbCr to RGB, at CCOD+0xd98 — 1.402 and
         * 1.772 at 2^14, and the two green terms at the same scale. */
        for (y = 0; y < 8; y++) {
            uint32_t row = mr * 8 + y;
            if (row >= im->h) break;
            for (x = 0; x < im->w; x++) {
                int32_t yy = s->yrow[y * s->stride + x];
                int32_t cb = s->cbrow[y * (s->stride / 2) + x / 2];
                int32_t cr = s->crrow[y * (s->stride / 2) + x / 2];
                int32_t v;
                if (plane == 0)
                    v = yy + (int32_t)(((int32_t)22965 * cr) >> 14);
                else if (plane == 1)
                    v = yy - (int32_t)(((int32_t)11703 * cr +
                                        (int32_t)5631 * cb) >> 14);
                else
                    v = yy + (int32_t)(((int32_t)29036 * cb) >> 14);
                if (v < 0) v = 0; else if (v > 255) v = 255;
                if (unc_fork_put(f, (uint8_t)v) != UNC_OK) return UNC_ERR_SINK;
            }
        }
    }
    (void)c;
    (void)i;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Entry point                                                        */
/* ------------------------------------------------------------------ */

int unc_ccube_decode(UncCtx *c, UncFork fork, const uint8_t *stored,
                     uint32_t storedlen, uint32_t outlen,
                     uint8_t *obuf, uint32_t ocap)
{
    CcImage im;
    CcState *s;
    UncForkOut f;
    uint32_t stride, need;
    int err, i, j;

    /* 80 bytes of module header, then the TIFF. */
    if (storedlen < 96) return UNC_ERR_TRUNCATED;
    im.t = stored + 80;
    im.len = storedlen - 80;
    im.data = 0;
    err = cc_parse(&im);
    if (err != UNC_OK) return err;
    if ((uint32_t)im.w * im.h * 3u != outlen) return UNC_ERR_CORRUPT;

    stride = ((im.w + CC_PAD_W - 1) / CC_PAD_W) * CC_PAD_W;
    s = (CcState *)unc_alloc(c->al, (uint32_t)sizeof *s);
    if (!s) return UNC_ERR_MEM;
    s->stride = stride;
    need = stride * 8u + stride * 8u;          /* luma + both chroma */
    s->yrow = (uint8_t *)unc_alloc(c->al, need);
    if (!s->yrow) { unc_free(c->al, s); return UNC_ERR_MEM; }
    s->cbrow = (int8_t *)(s->yrow + stride * 8u);
    s->crrow = s->cbrow + (stride / 2) * 8;

    for (i = 0; i < 3; i++) {
        for (j = 0; j < 64; j++) {
            uint32_t o = im.qoff[i] + (uint32_t)j * 2;
            if (o + 2 > im.len) { err = UNC_ERR_CORRUPT; goto out; }
            s->q[i][j] = (uint16_t)cc_u16(im.t + o);
        }
        if (im.dcoff[i] >= im.len || im.acoff[i] >= im.len) {
            err = UNC_ERR_CORRUPT; goto out;
        }
        err = cc_huff(&s->dc[i], im.t + im.dcoff[i], im.len - im.dcoff[i]);
        if (err != UNC_OK) goto out;
        err = cc_huff(&s->ac[i], im.t + im.acoff[i], im.len - im.acoff[i]);
        if (err != UNC_OK) goto out;
    }

    unc_fork_out(&f, c, fork, !c->opt.test_only, UNC_CK_CRC16_ARC, obuf, ocap);
    for (i = 0; i < 3 && err == UNC_OK; i++)
        err = cc_plane(c, &im, s, &f, i);
    if (err == UNC_OK) err = unc_fork_flush(&f);

out:
    unc_free(c->al, s->yrow);
    unc_free(c->al, s);
    return err;
}

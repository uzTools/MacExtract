/*
 * sit_arsenic.c — StuffIt method 15 "Arsenic":
 * arithmetic coder over an MTF-coded, optionally randomized BWT block,
 * with a final RLE stage and an internal CRC-32.
 *
 * Sources: reference/XADMaster/XADStuffItArsenicHandle.m (arithmetic
 * decoder, models, block/RLE logic, randomization table) and
 * reference/XADMaster/BWT.c (DecodeMTF, CalculateInverseBWT) — LGPL,
 * see NOTICE. The format is documented publicly only by Matthew T.
 * Russotto's write-up (reference/notes/arsenic_russotto.md).
 *
 * Memory per fork: block + 4*block for the inverse-BWT transform
 * vector, block = 1 << (9..24) bits as encoded in the stream. Real
 * StuffIt 5 archives in the corpus use 16-bit blocks (64 KB -> ~320 KB
 * peak); the caller's allocator budget decides what is acceptable.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* ------------------------------------------------------------------ */
/* Arithmetic decoder (26-bit, MSB-first bits)                        */
/* ------------------------------------------------------------------ */

#define ARS_NUMBITS 26
#define ARS_ONE  (1 << (ARS_NUMBITS - 1))
#define ARS_HALF (1 << (ARS_NUMBITS - 2))

typedef struct ArsSym {
    int32_t symbol, frequency;
} ArsSym;

typedef struct ArsModel {
    int32_t increment, frequencylimit;
    int32_t numsymbols, totalfrequency;
    ArsSym  symbols[128];
} ArsModel;

typedef struct ArsDecoder {
    UncBitIn *bi;
    int32_t   range, code;
    int       err;
} ArsDecoder;

static void ars_model_reset(ArsModel *m)
{
    int32_t i;
    m->totalfrequency = m->increment * m->numsymbols;
    for (i = 0; i < m->numsymbols; i++) m->symbols[i].frequency = m->increment;
}

static void ars_model_init(ArsModel *m, int32_t first, int32_t last,
                           int32_t increment, int32_t limit)
{
    int32_t i;
    m->increment = increment;
    m->frequencylimit = limit;
    m->numsymbols = last - first + 1;
    for (i = 0; i < m->numsymbols; i++) m->symbols[i].symbol = i + first;
    ars_model_reset(m);
}

static void ars_model_bump(ArsModel *m, int32_t n)
{
    int32_t i;
    m->symbols[n].frequency += m->increment;
    m->totalfrequency += m->increment;
    if (m->totalfrequency > m->frequencylimit) {
        m->totalfrequency = 0;
        for (i = 0; i < m->numsymbols; i++) {
            m->symbols[i].frequency++;
            m->symbols[i].frequency >>= 1;
            m->totalfrequency += m->symbols[i].frequency;
        }
    }
}

static void ars_dec_init(ArsDecoder *d, UncBitIn *bi)
{
    int32_t hi, lo;
    d->bi = bi;
    d->range = ARS_ONE;
    d->err = UNC_OK;
    hi = unc_bitin_bits(bi, 13);
    lo = unc_bitin_bits(bi, 13);
    if (hi < 0 || lo < 0) { d->err = bi->err; d->code = 0; return; }
    d->code = (hi << 13) | lo;
}

static void ars_dec_advance(ArsDecoder *d, int32_t symlow, int32_t symsize,
                            int32_t symtot)
{
    int32_t renorm = d->range / symtot;
    int32_t lowincr = renorm * symlow;

    d->code -= lowincr;
    if (symlow + symsize == symtot) d->range -= lowincr;
    else d->range = symsize * renorm;

    while (d->range <= ARS_HALF) {
        int bit = unc_bitin_bit(d->bi);
        if (bit < 0) { d->err = d->bi->err; return; }
        d->range <<= 1;
        d->code = (d->code << 1) | bit;
    }
}

static int32_t ars_next_symbol(ArsDecoder *d, ArsModel *m)
{
    int32_t frequency, cumulative, n;
    if (d->err != UNC_OK) return -1;
    if (m->totalfrequency == 0 || d->range / m->totalfrequency == 0) {
        d->err = UNC_ERR_CORRUPT;
        return -1;
    }
    frequency = d->code / (d->range / m->totalfrequency);
    cumulative = 0;
    for (n = 0; n < m->numsymbols - 1; n++) {
        if (cumulative + m->symbols[n].frequency > frequency) break;
        cumulative += m->symbols[n].frequency;
    }
    ars_dec_advance(d, cumulative, m->symbols[n].frequency, m->totalfrequency);
    if (d->err != UNC_OK) return -1;
    ars_model_bump(m, n);
    return m->symbols[n].symbol;
}

/* n-bit string, first symbol = bit 0 (NextArithmeticBitString). */
static int32_t ars_next_bits(ArsDecoder *d, ArsModel *m, int32_t n)
{
    int32_t res = 0, i;
    for (i = 0; i < n; i++) {
        int32_t b = ars_next_symbol(d, m);
        if (b < 0) return -1;
        if (b) res |= 1 << i;
    }
    return res;
}

/* ------------------------------------------------------------------ */
/* MTF decoder (BWT.c)                                                */
/* ------------------------------------------------------------------ */

typedef struct ArsMtf {
    uint8_t table[256];
} ArsMtf;

static void ars_mtf_reset(ArsMtf *m)
{
    int32_t i;
    for (i = 0; i < 256; i++) m->table[i] = (uint8_t)i;
}

static uint8_t ars_mtf_decode(ArsMtf *m, int32_t symbol)
{
    uint8_t res = m->table[symbol];
    int32_t i;
    for (i = symbol; i > 0; i--) m->table[i] = m->table[i - 1];
    m->table[0] = res;
    return res;
}

/* ------------------------------------------------------------------ */
/* Randomization table (XADStuffItArsenicHandle.m)                    */
/* ------------------------------------------------------------------ */

static const uint16_t ars_randtable[256] = {
    0xee, 0x56, 0xf8, 0xc3, 0x9d, 0x9f, 0xae, 0x2c,
    0xad, 0xcd, 0x24, 0x9d, 0xa6, 0x101, 0x18, 0xb9,
    0xa1, 0x82, 0x75, 0xe9, 0x9f, 0x55, 0x66, 0x6a,
    0x86, 0x71, 0xdc, 0x84, 0x56, 0x96, 0x56, 0xa1,
    0x84, 0x78, 0xb7, 0x32, 0x6a, 0x3, 0xe3, 0x2,
    0x11, 0x101, 0x8, 0x44, 0x83, 0x100, 0x43, 0xe3,
    0x1c, 0xf0, 0x86, 0x6a, 0x6b, 0xf, 0x3, 0x2d,
    0x86, 0x17, 0x7b, 0x10, 0xf6, 0x80, 0x78, 0x7a,
    0xa1, 0xe1, 0xef, 0x8c, 0xf6, 0x87, 0x4b, 0xa7,
    0xe2, 0x77, 0xfa, 0xb8, 0x81, 0xee, 0x77, 0xc0,
    0x9d, 0x29, 0x20, 0x27, 0x71, 0x12, 0xe0, 0x6b,
    0xd1, 0x7c, 0xa, 0x89, 0x7d, 0x87, 0xc4, 0x101,
    0xc1, 0x31, 0xaf, 0x38, 0x3, 0x68, 0x1b, 0x76,
    0x79, 0x3f, 0xdb, 0xc7, 0x1b, 0x36, 0x7b, 0xe2,
    0x63, 0x81, 0xee, 0xc, 0x63, 0x8b, 0x78, 0x38,
    0x97, 0x9b, 0xd7, 0x8f, 0xdd, 0xf2, 0xa3, 0x77,
    0x8c, 0xc3, 0x39, 0x20, 0xb3, 0x12, 0x11, 0xe,
    0x17, 0x42, 0x80, 0x2c, 0xc4, 0x92, 0x59, 0xc8,
    0xdb, 0x40, 0x76, 0x64, 0xb4, 0x55, 0x1a, 0x9e,
    0xfe, 0x5f, 0x6, 0x3c, 0x41, 0xef, 0xd4, 0xaa,
    0x98, 0x29, 0xcd, 0x1f, 0x2, 0xa8, 0x87, 0xd2,
    0xa0, 0x93, 0x98, 0xef, 0xc, 0x43, 0xed, 0x9d,
    0xc2, 0xeb, 0x81, 0xe9, 0x64, 0x23, 0x68, 0x1e,
    0x25, 0x57, 0xde, 0x9a, 0xcf, 0x7f, 0xe5, 0xba,
    0x41, 0xea, 0xea, 0x36, 0x1a, 0x28, 0x79, 0x20,
    0x5e, 0x18, 0x4e, 0x7c, 0x8e, 0x58, 0x7a, 0xef,
    0x91, 0x2, 0x93, 0xbb, 0x56, 0xa1, 0x49, 0x1b,
    0x79, 0x92, 0xf3, 0x58, 0x4f, 0x52, 0x9c, 0x2,
    0x77, 0xaf, 0x2a, 0x8f, 0x49, 0xd0, 0x99, 0x4d,
    0x98, 0x101, 0x60, 0x93, 0x100, 0x75, 0x31, 0xce,
    0x49, 0x20, 0x56, 0x57, 0xe2, 0xf5, 0x26, 0x2b,
    0x8a, 0xbf, 0xde, 0xd0, 0x83, 0x34, 0xf4, 0x17,
};

/* ------------------------------------------------------------------ */
/* Decoder state                                                      */
/* ------------------------------------------------------------------ */

typedef struct Arsenic {
    ArsDecoder dec;
    ArsModel   initialmodel, selectormodel;
    ArsModel   mtfmodel[7];
    ArsMtf     mtf;
    UncBitIn   bi;

    uint8_t   *block;       /* [blocksize] */
    uint32_t  *transform;   /* [transform_cap] inverse-BWT vector */
    uint32_t   blocksize;
    uint32_t   transform_cap;
    int32_t    blockbits;

    uint32_t   numbytes, bytecount, transformindex;
    int        randomized, endofblocks;
    int32_t    randindex, randcount;
    int32_t    count, repeat;
    uint8_t    last;
    uint32_t   crc, compcrc;
    int        has_compcrc;
} Arsenic;

/* CalculateInverseBWT (BWT.c): transform[] such that repeatedly
 * following transformindex=transform[transformindex] walks the
 * original byte order. Iterative, no recursion. */
static void ars_inverse_bwt(uint32_t *transform, const uint8_t *block,
                            uint32_t blocklen)
{
    uint32_t counts[256], cumulative[256];
    uint32_t i, total = 0;
    for (i = 0; i < 256; i++) counts[i] = 0;
    for (i = 0; i < blocklen; i++) counts[block[i]]++;
    for (i = 0; i < 256; i++) {
        cumulative[i] = total;
        total += counts[i];
        counts[i] = 0;
    }
    for (i = 0; i < blocklen; i++) {
        transform[cumulative[block[i]] + counts[block[i]]] = i;
        counts[block[i]]++;
    }
}

static int ars_read_block(Arsenic *a, UncAlloc *al)
{
    int32_t sel, symbol;

    ars_mtf_reset(&a->mtf);

    a->randomized = (int)ars_next_symbol(&a->dec, &a->initialmodel);
    a->transformindex =
        (uint32_t)ars_next_bits(&a->dec, &a->initialmodel, a->blockbits);
    if (a->dec.err != UNC_OK) return a->dec.err;
    a->numbytes = 0;

    for (;;) {
        sel = ars_next_symbol(&a->dec, &a->selectormodel);
        if (sel < 0) return a->dec.err != UNC_OK ? a->dec.err : UNC_ERR_CORRUPT;

        if (sel == 0 || sel == 1) {
            /* Zero-run counting (bzip2-style RUNA/RUNB). */
            uint32_t zerostate = 1, zerocount = 0;
            while (sel < 2) {
                if (sel == 0) zerocount += zerostate;
                else zerocount += 2 * zerostate;
                zerostate *= 2;
                sel = ars_next_symbol(&a->dec, &a->selectormodel);
                if (sel < 0)
                    return a->dec.err != UNC_OK ? a->dec.err : UNC_ERR_CORRUPT;
                if (zerocount > a->blocksize) return UNC_ERR_CORRUPT;
            }
            if (a->numbytes + zerocount > a->blocksize) return UNC_ERR_CORRUPT;
            {
                uint8_t z = ars_mtf_decode(&a->mtf, 0);
                uint32_t i;
                for (i = 0; i < zerocount; i++) a->block[a->numbytes + i] = z;
            }
            a->numbytes += zerocount;
        }

        if (sel == 10) break;
        else if (sel == 2) symbol = 1;
        else {
            symbol = ars_next_symbol(&a->dec, &a->mtfmodel[sel - 3]);
            if (symbol < 0)
                return a->dec.err != UNC_OK ? a->dec.err : UNC_ERR_CORRUPT;
        }

        if (a->numbytes >= a->blocksize) return UNC_ERR_CORRUPT;
        a->block[a->numbytes++] = ars_mtf_decode(&a->mtf, symbol);
    }

    if (a->transformindex >= a->numbytes) return UNC_ERR_CORRUPT;

    ars_model_reset(&a->selectormodel);
    {
        int32_t i;
        for (i = 0; i < 7; i++) ars_model_reset(&a->mtfmodel[i]);
    }

    {
        int32_t end = ars_next_symbol(&a->dec, &a->initialmodel);
        if (end < 0) return a->dec.err != UNC_OK ? a->dec.err : UNC_ERR_CORRUPT;
        if (end) {
            int32_t lo = ars_next_bits(&a->dec, &a->initialmodel, 16);
            int32_t hi = ars_next_bits(&a->dec, &a->initialmodel, 16);
            if (lo < 0 || hi < 0)
                return a->dec.err != UNC_OK ? a->dec.err : UNC_ERR_CORRUPT;
            a->compcrc = (uint32_t)lo | ((uint32_t)hi << 16);
            a->has_compcrc = 1;
            a->endofblocks = 1;
        }
    }

    /* Size the transform vector to the actual block fill, not the
     * declared block size: real archives use 512 KB blocks even for
     * tiny files, and the 4x transform is the dominant allocation
     * (XADStuffItArsenicHandle reallocs per block the same way).
     * This is what lets small Arsenic files fit a small budget. */
    if (a->numbytes > a->transform_cap) {
        unc_free(al, a->transform);
        a->transform = (uint32_t *)unc_alloc(al, a->numbytes * 4);
        if (!a->transform) { a->transform_cap = 0; return UNC_ERR_MEM; }
        a->transform_cap = a->numbytes;
    }

    ars_inverse_bwt(a->transform, a->block, a->numbytes);
    return UNC_OK;
}

int unc_arsenic_decode(UncBufIn *in, UncAlloc *al, uint32_t outlen,
                       int (*put)(void *ctx, uint8_t b), void *pctx)
{
    Arsenic *a;
    uint32_t produced = 0;
    int err = UNC_OK;
    int32_t v;

    a = (Arsenic *)unc_alloc(al, (uint32_t)sizeof *a);
    if (!a) return UNC_ERR_MEM;
    a->block = NULL;
    a->transform = NULL;

    unc_bitin_init(&a->bi, in);
    ars_dec_init(&a->dec, &a->bi);

    ars_model_init(&a->initialmodel, 0, 1, 1, 256);
    ars_model_init(&a->selectormodel, 0, 10, 8, 1024);
    ars_model_init(&a->mtfmodel[0], 2, 3, 8, 1024);
    ars_model_init(&a->mtfmodel[1], 4, 7, 4, 1024);
    ars_model_init(&a->mtfmodel[2], 8, 15, 4, 1024);
    ars_model_init(&a->mtfmodel[3], 16, 31, 4, 1024);
    ars_model_init(&a->mtfmodel[4], 32, 63, 2, 1024);
    ars_model_init(&a->mtfmodel[5], 64, 127, 2, 1024);
    ars_model_init(&a->mtfmodel[6], 128, 255, 1, 1024);

    v = ars_next_bits(&a->dec, &a->initialmodel, 8);
    if (v != 'A') { err = v < 0 ? a->dec.err : UNC_ERR_CORRUPT; goto out; }
    v = ars_next_bits(&a->dec, &a->initialmodel, 8);
    if (v != 's') { err = v < 0 ? a->dec.err : UNC_ERR_CORRUPT; goto out; }

    v = ars_next_bits(&a->dec, &a->initialmodel, 4);
    if (v < 0) { err = a->dec.err; goto out; }
    a->blockbits = v + 9;
    a->blocksize = 1u << a->blockbits;

    a->block = (uint8_t *)unc_alloc(al, a->blocksize);
    if (!a->block) { err = UNC_ERR_MEM; goto out; }
    a->transform = NULL;
    a->transform_cap = 0;

    a->numbytes = a->bytecount = 0;
    a->repeat = 0;
    a->count = 0;
    a->last = 0;
    a->crc = 0xFFFFFFFFu;
    a->compcrc = 0;
    a->has_compcrc = 0;
    a->randomized = 0;
    a->transformindex = 0;

    v = ars_next_symbol(&a->dec, &a->initialmodel);   /* first end marker */
    if (v < 0) { err = a->dec.err; goto out; }
    a->endofblocks = v;

    while (produced < outlen) {
        uint8_t outbyte;

        if (a->repeat) {
            a->repeat--;
            outbyte = a->last;
        } else {
            int32_t byte;
retry:
            if (a->bytecount >= a->numbytes) {
                if (a->endofblocks) { err = UNC_ERR_TRUNCATED; goto out; }
                if ((err = ars_read_block(a, al)) != UNC_OK) goto out;
                a->bytecount = 0;
                a->count = 0;
                a->last = 0;
                a->randindex = 0;
                a->randcount = (int32_t)ars_randtable[0];
            }

            a->transformindex = a->transform[a->transformindex];
            byte = a->block[a->transformindex];

            if (a->randomized && (uint32_t)a->randcount == a->bytecount) {
                byte ^= 1;
                a->randindex = (a->randindex + 1) & 255;
                a->randcount += (int32_t)ars_randtable[a->randindex];
            }

            a->bytecount++;

            if (a->count == 4) {
                a->count = 0;
                if (byte == 0) goto retry;
                a->repeat = byte - 1;
                outbyte = a->last;
            } else {
                if (byte == a->last) a->count++;
                else { a->count = 1; a->last = (uint8_t)byte; }
                outbyte = (uint8_t)byte;
            }
        }

        a->crc = unc_crc32(a->crc, &outbyte, 1);
        if (put(pctx, outbyte) != UNC_OK) { err = UNC_ERR_SINK; goto out; }
        produced++;
    }

    if (a->has_compcrc && a->compcrc != ~a->crc) err = UNC_ERR_CRC;

out:
    unc_free(al, a->transform);
    unc_free(al, a->block);
    unc_free(al, a);
    return err;
}

/*
 * sit_arsenic.c — StuffIt method 15, "Arsenic": a Burrows-Wheeler block
 * sort, move-to-front coded with zero-run suppression, arithmetic-coded
 * under nine adaptive models, then randomisation, a byte-stuffing RLE and
 * a CRC-32 over the whole output.
 *
 * WRITTEN FROM THE DESCRIPTION, 2026-09-19: Matthew T. Russotto's
 * write-up of the format, reference/notes/arsenic_russotto.md — the
 * coder's pseudocode, the nine models' parameters, the block header, the
 * selector alphabet and its zero counting, the randomisation table and
 * schedule, the final RLE and the CRC. Until this date the file
 * transcribed reference/XADMaster/XADStuffItArsenicHandle.m and BWT.c;
 * what remains from that version is what was never XADMaster's — the
 * sampled inverse-BWT index and its target dial (2026-08-07), the block
 * buffer's growth policy (2026-08-06), the three-byte transform vector
 * (2026-09-19) and progress by output. The author of this version had
 * read the transcription; the structures below are not its.
 *
 * WHAT THE FORMAT FIXES AND WHAT IT LEAVES FREE. The arithmetic is
 * bit-exact and is the write-up's, rounding included:
 *
 *     renorm    = range / total                 (integer division)
 *     frequency = code / renorm
 *     code     -= renorm * low
 *     range     = (high == total) ? range - renorm * low
 *                                 : renorm * (high - low)
 *     while (range <= HALF) { range <<= 1; code = (code << 1) | bit; }
 *
 * The models' increments and limits, the MTF, the selector's meaning,
 * the randomisation schedule and the RLE-of-four are all fixed too. What
 * a decoder may choose is how it STORES things, and two of those choices
 * are where a 68000 spends this format's time (measured 2026-09-19 with
 * qemu-m68k on the shipped flags, derived-a2basic.dmg.sit):
 *
 *   - the MTF. A byte-at-a-time shift of a 256-entry table costs the
 *     symbol's rank in moves, and on data that barely compresses the
 *     ranks are large: 34.5 % of every instruction the Plus executed.
 *     The table here is bzip2's two-level shape — sixteen lists of
 *     sixteen inside a 4 KB array that is re-spaced when it runs out —
 *     which bounds a move at about thirty steps and is byte for byte the
 *     same permutation, because a move-to-front is a move-to-front
 *     however the front is kept.
 *   - the symbol search. Finding which symbol's cumulative range holds
 *     `frequency` was a linear walk, 27 % of the instructions. The
 *     models keep a sum per group of sixteen symbols beside the
 *     frequencies, so the walk is over groups and then inside one.
 *
 * Both are invisible to a Linux profile, which inlines the byte shift
 * into a `rep movs` and runs the walk at a fraction of the cost per step.
 *
 * MEMORY PER FORK: ~28 KB of state (the MTF table is 2 KB of it), the
 * block at its fill, and either the 3-bytes-per-byte transform vector or
 * the sampled index — see "Inverse BWT" below, which is unchanged.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* ------------------------------------------------------------------ */
/* The arithmetic decoder                                             */
/* ------------------------------------------------------------------ */

#define ARS_NUMBITS 26
#define ARS_ONE  (1 << (ARS_NUMBITS - 1))
#define ARS_HALF (1 << (ARS_NUMBITS - 2))

typedef struct ArsDecoder {
    UncBitIn *bi;
    int32_t   range, code;
    int       err;
} ArsDecoder;

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

/* ------------------------------------------------------------------ */
/* The models                                                         */
/*                                                                    */
/* A model is `nsyms` consecutive symbol values from `first`, each with */
/* a frequency that starts at `increment`, grows by it when the symbol */
/* is decoded, and is halved (rounding up) across the model when the   */
/* total passes `limit`. The frequencies are kept per symbol, and the  */
/* SUM of each group of sixteen beside them, so the search below walks */
/* at most eight groups and sixteen symbols instead of 128.            */
/* ------------------------------------------------------------------ */

#define ARS_GROUP     16
#define ARS_GROUPS    8                 /* 128 symbols at most */
/* Symbols across the nine models: 2 + 11 + 2 + 4 + 8 + 16 + 32 + 64 + 128.
 * The frequencies live in one pool of exactly that many, carved up at
 * init, rather than 128 per model: 1,068 B instead of 4,608. */
#define ARS_POOL      267

typedef struct ArsModel {
    int32_t  increment, limit;
    int32_t  nsyms, total;
    int32_t  first;
    int32_t *freq;                  /* [nsyms], into the decoder's pool */
    int32_t  gsum[ARS_GROUPS];
} ArsModel;

static void ars_model_reset(ArsModel *m)
{
    int32_t i;
    for (i = 0; i < m->nsyms; i++) m->freq[i] = m->increment;
    for (i = 0; i < ARS_GROUPS; i++) m->gsum[i] = 0;
    for (i = 0; i < m->nsyms; i++) m->gsum[i / ARS_GROUP] += m->increment;
    m->total = m->increment * m->nsyms;
}

static void ars_model_init(ArsModel *m, int32_t *freq, int32_t first,
                           int32_t last, int32_t increment, int32_t limit)
{
    m->increment = increment;
    m->limit = limit;
    m->nsyms = last - first + 1;
    m->first = first;
    m->freq = freq;
    ars_model_reset(m);
}

/* Symbol n was decoded: count it, and halve the model when the total
 * passes its limit — "dividing all the frequencies by 2 (with
 * rounding) and recalculating symtot". */
static void ars_model_bump(ArsModel *m, int32_t n)
{
    m->freq[n] += m->increment;
    m->gsum[n / ARS_GROUP] += m->increment;
    m->total += m->increment;
    if (m->total > m->limit) {
        int32_t i, t = 0;
        for (i = 0; i < ARS_GROUPS; i++) m->gsum[i] = 0;
        for (i = 0; i < m->nsyms; i++) {
            int32_t f = (m->freq[i] + 1) >> 1;
            m->freq[i] = f;
            m->gsum[i / ARS_GROUP] += f;
            t += f;
        }
        m->total = t;
    }
}

/* Decode one symbol under `m`: the write-up's "decode a frequency" and
 * "remove symbol", with the search over the group sums first.
 *
 * Every operand is provably non-negative in a valid stream — `range` is
 * renormalised into (HALF, ONE], `code` lies in [0, range), totals are
 * positive — so the two divisions are UNSIGNED: on a 68000 __divsi3 is a
 * sign wrapper around the unsigned helper. The guard replaces the
 * narrower `total == 0` test and cannot fire on a valid stream; on a
 * corrupt one it is the same UNC_ERR_CORRUPT, sooner. */
static int32_t ars_decode(ArsDecoder *d, ArsModel *m)
{
    int32_t renorm, frequency, low, n, g, hi;
    const int32_t *freq = m->freq;

    if (d->err != UNC_OK) return -1;
    if (d->range <= 0 || m->total <= 0 || d->code < 0) {
        d->err = UNC_ERR_CORRUPT;
        return -1;
    }
    renorm = (int32_t)((uint32_t)d->range / (uint32_t)m->total);
    if (renorm == 0) { d->err = UNC_ERR_CORRUPT; return -1; }
    frequency = (int32_t)((uint32_t)d->code / (uint32_t)renorm);

    /* Which group, then which symbol in it. `frequency` can be equal to
     * or a little above the total — renorm is rounded down, so code can
     * sit in [renorm * total, range) — and the format's answer is the
     * LAST symbol: both walks stop at the last group and the last symbol
     * rather than running off the end. */
    low = 0;
    g = 0;
    hi = (m->nsyms - 1) / ARS_GROUP;                /* last non-empty group */
    while (g < hi && low + m->gsum[g] <= frequency) {
        low += m->gsum[g];
        g++;
    }
    n = g * ARS_GROUP;
    hi = n + ARS_GROUP < m->nsyms ? n + ARS_GROUP : m->nsyms;
    while (n < hi - 1 && low + freq[n] <= frequency) {
        low += freq[n];
        n++;
    }

    /* Remove the symbol and renormalise. */
    {
        int32_t lowincr = renorm * low;
        d->code -= lowincr;
        if (low + freq[n] == m->total) d->range -= lowincr;
        else d->range = renorm * freq[n];
        while (d->range <= ARS_HALF) {
            int bit = unc_bitin_bit(d->bi);
            if (bit < 0) { d->err = d->bi->err; return -1; }
            d->range <<= 1;
            d->code = (d->code << 1) | bit;
        }
    }
    ars_model_bump(m, n);
    return m->first + n;
}

/* n bits as a number, least significant first, each under `m`. */
static int32_t ars_bits(ArsDecoder *d, ArsModel *m, int32_t n)
{
    int32_t v = 0, i;
    for (i = 0; i < n; i++) {
        int32_t b = ars_decode(d, m);
        if (b < 0) return -1;
        if (b) v |= 1 << i;
    }
    return v;
}

/* ------------------------------------------------------------------ */
/* Move-to-front, two levels                                          */
/*                                                                    */
/* The 256 byte values in rank order, kept as sixteen lists of sixteen */
/* inside a 4 KB array that grows DOWNWARD: list `l` starts at         */
/* base[l]. Fetching rank r takes the byte at base[r/16] + r%16,       */
/* shifts the entries before it in that list down by one, then rotates */
/* the last entry of each earlier list into the first slot of the next */
/* — sixteen moves at most plus one per list — and puts the byte at    */
/* the new front, one slot below where list 0 began. When list 0       */
/* reaches the bottom of the array, everything is re-spaced to the top */
/* — once per ~3,800 symbols. This is bzip2's arrangement (Julian       */
/* Seward's decompress.c, BSD-style licence), written here from the    */
/* idea; it computes the same permutation a flat table does.           */
/* ------------------------------------------------------------------ */

#define ARS_MTFA 2048                   /* re-spaced every ~1,800 symbols;
                                         * 4 KB was one fixture off the 400 KB
                                         * budget (measured 2026-09-19) */
#define ARS_MTFL 16

typedef struct ArsMtf {
    int32_t base[256 / ARS_MTFL];
    uint8_t a[ARS_MTFA];
} ArsMtf;

static void ars_mtf_reset(ArsMtf *m)
{
    int32_t k = ARS_MTFA - 1, i, j;
    for (i = 256 / ARS_MTFL - 1; i >= 0; i--) {
        for (j = ARS_MTFL - 1; j >= 0; j--) {
            m->a[k] = (uint8_t)(i * ARS_MTFL + j);
            k--;
        }
        m->base[i] = k + 1;
    }
}

static uint8_t ars_mtf_decode(ArsMtf *m, int32_t rank)
{
    uint8_t *a = m->a;
    int32_t l, p, at;
    uint8_t v;

    if (rank == 0) return a[m->base[0]];

    if (rank < ARS_MTFL) {
        p = m->base[0];
        v = a[p + rank];
        while (rank > 0) { a[p + rank] = a[p + rank - 1]; rank--; }
        a[p] = v;
        return v;
    }

    l = rank / ARS_MTFL;
    at = m->base[l] + (rank & (ARS_MTFL - 1));
    v = a[at];
    while (at > m->base[l]) { a[at] = a[at - 1]; at--; }
    m->base[l]++;
    while (l > 0) {
        m->base[l]--;
        a[m->base[l]] = a[m->base[l - 1] + ARS_MTFL - 1];
        l--;
    }
    m->base[0]--;
    a[m->base[0]] = v;

    if (m->base[0] == 0) {
        /* Re-space: copy every list back to the top of the array. */
        int32_t k = ARS_MTFA - 1, i, j;
        for (i = 256 / ARS_MTFL - 1; i >= 0; i--) {
            for (j = ARS_MTFL - 1; j >= 0; j--) {
                a[k] = a[m->base[i] + j];
                k--;
            }
            m->base[i] = k + 1;
        }
    }
    return v;
}

/* ------------------------------------------------------------------ */
/* Randomisation table (the write-up's Appendix A)                     */
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

/* Sampled occurrence index — the low-memory inverse BWT (see below). */
/* Entries in the coarse value table below. 512 slots against at most 256
 * boundaries means half a boundary per slot, so the walk after the lookup
 * is normally none and never more than the boundaries that fall in one
 * slot. 512 bytes, against an index that is hundreds of kilobytes. */
#define ARS_VTAB_BITS 9
#define ARS_VTAB_SIZE (1u << ARS_VTAB_BITS)

typedef struct ArsIndex {
    uint32_t cum[256];     /* first sorted index of byte value c */
    uint32_t base[256];    /* which SAMPLE c's samples start at */
    uint32_t nsamples;
    uint8_t  shift[256];   /* one sample per 1 << shift[c] occurrences */
    /* Which byte value owns sorted index k, to within a short forward
     * walk: vtab[k >> vshift] is the largest c whose range starts at or
     * before k rounded down to a slot. It replaces a binary search over
     * cum[] that ran ONCE PER OUTPUT BYTE — eight iterations, each a
     * 32-bit load from a 1 KB array, on a processor with no cache. */
    uint8_t  vtab[ARS_VTAB_SIZE];
    uint32_t vshift;
    /* [nsamples * 3]; over-allocated by the caller. THREE bytes per
     * sample, not four: a sample is a position inside the block, and
     * blockbits is 4 stream bits plus 9, so a block is at most 1 << 24
     * bytes and a position at most (1 << 24) - 1. That is exactly what
     * three bytes hold, and it is 25 % of the index given back.
     *
     * The index is a pure time-for-memory dial — `target` halves until
     * the allocator accepts, and each halving doubles the scan distance
     * — so a quarter off its size is a quarter more density at the same
     * budget, and on derived-Library_ISBN_Barcoder.sit at the 1 MB
     * budget it is the difference between target 512 and target 1024
     * (measured: 260,705 B against 346,836 B for the same 86,131
     * samples, in 290,391 B of room). Reading a position costs two
     * shifts and two ors more than a word load, once per query, against
     * a scan of blocklen/target bytes.
     *
     * Byte-wise big-endian, which the 68000 discipline wants anyway:
     * pos[] needs no alignment and there is no unaligned dereference. */
    uint8_t  pos[3];
} ArsIndex;

typedef struct Arsenic {
    ArsDecoder dec;
    ArsModel   initial, selector;
    ArsModel   mtfmodel[7];
    int32_t    pool[ARS_POOL];
    ArsMtf     mtf;
    UncBitIn   bi;

    uint8_t   *block;       /* [blockcap + 1], grown on demand up to blocksize */
    uint8_t   *transform;   /* [transform_cap * 3] inverse-BWT vector, or NULL */
    ArsIndex  *index;       /* set instead of transform when memory is tight */
    uint32_t   blocksize;   /* the DECLARED block size, 1 << blockbits */
    uint32_t   blockcap;    /* what is actually allocated right now */
    uint32_t   outlen;      /* the entry's whole output — bounds the block */
    uint32_t   transform_cap;
    int32_t    blockbits;

    uint32_t   numbytes, bytecount, transformindex;
    int        randomized, endofblocks;
    int32_t    randindex, randcount;
    int32_t    count, repeat;
    uint8_t    last;
    uint32_t   compcrc;     /* the CRC-32 the stream ends with; the
                             * running one is the fork writer's */
    int        has_compcrc;
} Arsenic;

/* ------------------------------------------------------------------ */
/* Inverse BWT                                                        */
/*                                                                    */
/* Two implementations of one operation. The walk needs, for a sorted */
/* index k, the block position transform[k] = the position of the     */
/* (r+1)-th occurrence of the byte value c that owns k, where         */
/* c is the value whose sorted range contains k and r = k - cum[c].   */
/*                                                                    */
/* ars_inverse_bwt() answers it in O(1) from a table costing 3 bytes  */
/* per block byte. That table is the largest allocation the decoder   */
/* makes and on a 1 MB Mac it is what puts large blocks out of reach: */
/* a 323,384-byte block wants 970,152 bytes for it, against a         */
/* ~648 KB heap budget.                                               */
/*                                                                    */
/* ars_index_build() answers the same question from SAMPLES: the      */
/* position of every (1 << shift[c])-th occurrence of each value,     */
/* shift[c] chosen so every value gets at most `target` samples.      */
/* A query then scans the block forward from the nearest sample,      */
/* counting occurrences of c. Cost:                                   */
/*                                                                    */
/*   memory  ~ 3 * sum over c of min(counts[c], target)               */
/*   time    ~ blocklen/target positions scanned per output byte      */
/*                                                                    */
/* so `target` is a pure time-for-memory dial, and it is chosen by    */
/* halving until the allocator accepts — nothing else knows what the  */
/* caller's budget is. Samples are per VALUE rather than per sorted   */
/* index on purpose: it makes the scan distance ~blocklen/target for  */
/* every value, common or rare, instead of ~target occurrences of c,  */
/* which for a rare c is most of the block.                           */
/*                                                                    */
/* The fast path is tried first at every block, so a machine that can */
/* afford the table pays nothing for any of this.                     */
/* ------------------------------------------------------------------ */

/* THREE bytes per entry, not four. An entry is a position inside the
 * block, and blockbits is four stream bits plus nine, so a position is
 * at most (1 << 24) - 1 and three bytes hold it exactly — the argument
 * the sampled index's pos[] makes above. Written and read through
 * these two so the width lives in one place. */
static inline uint32_t ars_transform_get(const uint8_t *t, uint32_t k)
{
    const uint8_t *p = t + k * 3u;
    return ((uint32_t)p[0] << 16) | ((uint32_t)p[1] << 8) | (uint32_t)p[2];
}

static inline void ars_transform_put(uint8_t *t, uint32_t k, uint32_t v)
{
    uint8_t *p = t + k * 3u;
    p[0] = (uint8_t)(v >> 16);
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)v;
}

#ifndef UNC_ARS_FORCE_SAMPLED
/* The standard inverse: count each value, turn the counts into the
 * first sorted index of each value, then a second pass places every
 * block position at its sorted index. Following transform[] from the
 * header's index walks the original byte order. */
static void ars_inverse_bwt(uint8_t *transform, const uint8_t *block,
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
        ars_transform_put(transform, cumulative[block[i]] + counts[block[i]], i);
        counts[block[i]]++;
    }
}
#endif

/* Output bytes between progress reports. Much finer than the engine's
 * input-side UNC_PROGRESS_STEP (8192) because this decoder's bytes are
 * expensive: under the sampled index a2basic emits 205,019 bytes in 927 s
 * on a Mac Plus, so an 8 KB interval would tick once every 37 seconds —
 * a bar that jumps in 4% steps and a Cancel button that takes half a
 * minute to answer. At 256 the same run reports ~800 times, about 1.2 s
 * apart. The cost is a compare per output byte and a callback that the
 * Mac shell rate-limits to 10 Hz anyway. */
#define ARS_PROGRESS_STEP 256u

/* Samples per byte value at the first attempt. Halved until the index fits;
 * one sample per value (target 1) is the floor and costs at most 2 KB.
 * Overridable at compile time so a test build can force the deep end of
 * the dial: a budget large enough to hold the block is also large enough
 * to keep `target` high, so nothing a real run does exercises a query
 * whose scan spans most of the block. ci.sh builds with 1. */
#ifndef ARS_INDEX_TARGET
#define ARS_INDEX_TARGET 1024u
#endif

/* Pick shift[c] so no value has more than `target` samples, and return how
 * many samples that is in total. Pure function of the histogram: cheap
 * enough (256 values, <=24 shifts) to re-run for every candidate target. */
static uint32_t ars_index_plan(const uint32_t *counts, uint32_t target,
                               uint8_t *shift)
{
    uint32_t c, total = 0;
    for (c = 0; c < 256; c++) {
        uint32_t sh = 0;
        while ((counts[c] >> sh) > target) sh++;
        shift[c] = (uint8_t)sh;
        if (counts[c]) total += ((counts[c] - 1) >> sh) + 1;
    }
    return total;
}

/* Build the sampled index for the block currently in a->block. */
static int ars_index_build(Arsenic *a, UncAlloc *al)
{
    uint32_t counts[256], occ[256];
    uint8_t  shift[256];
    uint32_t i, c, total = 0, target, running, n = a->numbytes;
    ArsIndex *ix = NULL;

    for (i = 0; i < 256; i++) counts[i] = 0;
    for (i = 0; i < n; i++) counts[a->block[i]]++;

    for (target = ARS_INDEX_TARGET; ; target >>= 1) {
        total = ars_index_plan(counts, target, shift);
        /* Never ask for more than the table we already could not get. */
        if (total <= n) {
            ix = (ArsIndex *)unc_alloc(al, (uint32_t)sizeof *ix + total * 3u);
            if (ix) break;
        }
        if (target == 1) return UNC_ERR_MEM;   /* per-entry, not fatal */
    }

    ix->nsamples = total;
    running = 0;
    for (c = 0; c < 256; c++) {
        ix->cum[c] = running;
        ix->shift[c] = shift[c];
        running += counts[c];
    }

    /* The coarse value table. vshift is chosen so the whole block maps
     * into ARS_VTAB_SIZE slots; slot j answers for k = j << vshift, and
     * ars_index_next walks forward from there. Built by sweeping the
     * values in order rather than searching per slot. */
    {
        uint32_t vs = 0, j = 0, cc = 0;
        while ((n >> vs) >= ARS_VTAB_SIZE) vs++;
        ix->vshift = vs;
        for (j = 0; j < ARS_VTAB_SIZE; j++) {
            uint32_t at = j << vs;
            while (cc < 255u && ix->cum[cc + 1u] <= at) cc++;
            ix->vtab[j] = (uint8_t)cc;
        }
    }
    running = 0;
    for (c = 0; c < 256; c++) {
        ix->base[c] = running;
        if (counts[c]) running += ((counts[c] - 1) >> shift[c]) + 1;
    }
    for (i = 0; i < 256; i++) occ[i] = 0;
    for (i = 0; i < n; i++) {
        c = a->block[i];
        if ((occ[c] & ((1u << shift[c]) - 1u)) == 0) {
            uint8_t *p = &ix->pos[(ix->base[c] + (occ[c] >> shift[c])) * 3u];
            p[0] = (uint8_t)(i >> 16);
            p[1] = (uint8_t)(i >> 8);
            p[2] = (uint8_t)i;
        }
        occ[c]++;
    }

    a->index = ix;
    return UNC_OK;
}

/* One step of the walk, from the sampled index. Equivalent to
 * transform[k], and provably in range: the lookup lands on the value c
 * whose sorted range holds k, so r < counts[c] and the r-th occurrence
 * of c exists at or after the sample it starts from.
 *
 * The scan below is the hottest line under the sampled index: it used
 * to test two things per byte, `i < n` and the byte itself. A SENTINEL
 * removes the first: block[n] holds a copy of the value being searched
 * for, so every scan stops at n at the latest and the bound is checked
 * once per scan instead of once per byte. ars_block_reserve allocates
 * blockcap + 1 for exactly this, and the corrupt case still cannot walk
 * out of the buffer — a scan that reaches the sentinel ends the walk
 * and returns 0, as it did before. */
static uint32_t ars_index_next(const Arsenic *a, uint32_t k)
{
    const ArsIndex *ix = a->index;
    uint8_t *block = a->block;
    uint32_t c, r, sh, i, rem, n = a->numbytes;

    c = ix->vtab[k >> ix->vshift];
    while (c < 255u && ix->cum[c + 1u] <= k) c++;
    sh = ix->shift[c];
    r = k - ix->cum[c];
    {
        const uint8_t *p = &ix->pos[(ix->base[c] + (r >> sh)) * 3u];
        i = ((uint32_t)p[0] << 16) | ((uint32_t)p[1] << 8) | (uint32_t)p[2];
    }

    rem = r & ((1u << sh) - 1u);
    if (rem) {
        block[n] = (uint8_t)c;
        do {
            do { i++; } while (block[i] != (uint8_t)c);
        } while (i < n && --rem);
    }
    return i < n ? i : 0;
}

/* Choose how this block's BWT will be inverted: the 3-bytes-per-byte table
 * when the allocator affords it, the sampled index when it does not.
 *
 * The choice is made per block, and the table is kept across blocks while it
 * is big enough, so a stream that starts affordable stays on the fast path
 * without reallocating. UNC_ARS_FORCE_SAMPLED drops the fast path entirely;
 * it exists so ci.sh can run the whole corpus through the fallback. */
static int ars_bwt_prepare(Arsenic *a, UncAlloc *al)
{
#ifndef UNC_ARS_FORCE_SAMPLED
    if (a->numbytes > a->transform_cap) {
        uint8_t *nt;
        unc_free(al, a->transform);
        a->transform = NULL;
        a->transform_cap = 0;
        nt = (uint8_t *)unc_alloc(al, a->numbytes * 3u);
        if (nt) { a->transform = nt; a->transform_cap = a->numbytes; }
    }
    if (a->transform) {
        unc_free(al, a->index);
        a->index = NULL;
        ars_inverse_bwt(a->transform, a->block, a->numbytes);
        return UNC_OK;
    }
#endif
    /* Sized from this block's histogram, so it is rebuilt per block rather
     * than grown; freeing first keeps the two from coexisting. */
    unc_free(al, a->index);
    a->index = NULL;
    return ars_index_build(a, al);
}

/* Starting capacity for a block. Small enough that a tiny entry costs almost
 * nothing, large enough that ordinary entries need only a few doublings. */
#define ARS_BLOCK_INITIAL 8192u

/* Grow a->block so it can hold `need` bytes, doubling, never past the
 * declared block size.
 *
 * Every real Arsenic block declares 512 KB (measured: all 484 streams in the
 * corpus), but most hold far less — a fixture peaking at 643 KB on a 1 MB Mac
 * was a 512 KB allocation holding 24 KB. Allocating the declared size up front
 * therefore spent half a megabyte to store nothing, and on the floor target
 * that was the difference between an entry being affordable and being refused:
 * the budget saw 35 KB parser + 512 KB block + 4 bytes per byte actually
 * decoded (3 since 2026-09-19), so only ~37 KB of real data fit in a
 * ~700 KB heap.
 *
 * Growing instead makes the cost proportional to the data: ~30 KB + capacity +
 * 3x fill. The transform vector has been sized to the fill since M9 for the
 * same reason; this is the other half of it.
 *
 * The transient during a growth is old + new = 1.5x the new capacity, which is
 * below the later peak of capacity + 3x fill, so growing never sets the high
 * water mark. There is no realloc in the allocator API by design (see
 * DECISIONS.md), hence alloc-copy-free.
 *
 * One byte more than blockcap is always allocated: block[numbytes] is the
 * sentinel ars_index_next writes, which is what lets its scan drop its bound
 * test. blockcap itself is unchanged, so nothing else sees the spare byte. */
static int ars_block_reserve(Arsenic *a, UncAlloc *al, uint32_t need)
{
    uint8_t *nb;
    uint32_t cap, i;

    if (need <= a->blockcap) return UNC_OK;
    if (need > a->blocksize) return UNC_ERR_CORRUPT;   /* caller checks too */

    if (a->blockcap == 0) {
        /* Size the FIRST allocation from the entry, so there is normally no
         * second one. min(outlen, blocksize) is exact both ways: if the
         * entry's whole output is smaller than a block there is exactly one
         * block holding outlen, and otherwise at least one block fills.
         *
         * This is not just tidier than doubling from 8 KB — the doubling left
         * a TRAIL. Each freed step is smaller than the next request, and a
         * geometric trail can never satisfy the step that follows it, so
         * 8+16+32+64 KB of holes sat under the final 128 KB block. Measured
         * on the 1 MB floor target that trail was 125,614 B of stranded heap,
         * and it is what made the transform vector's 498,548 B request fail
         * against a 468,126 B largest run while the budget still had 678 KB.
         * See OPEN_ITEMS.md section 5 and BLOCKERS.md. */
        cap = a->outlen < a->blocksize ? a->outlen : a->blocksize;
        if (cap < ARS_BLOCK_INITIAL) cap = ARS_BLOCK_INITIAL;
    } else {
        cap = a->blockcap;
    }
    while (cap < need) {
        if (cap > a->blocksize / 2) { cap = a->blocksize; break; }
        cap *= 2;
    }
    /* blockbits is 4 bits from the stream, so a declared block can be as
     * small as 512 bytes — smaller than the starting capacity. Never allocate
     * more than the format says the block can hold. */
    if (cap > a->blocksize) cap = a->blocksize;

    nb = (uint8_t *)unc_alloc(al, cap + 1u);           /* +1: the sentinel */
    if (!nb) return UNC_ERR_MEM;                       /* per-entry, not fatal */
    for (i = 0; i < a->numbytes; i++) nb[i] = a->block[i];
    unc_free(al, a->block);
    a->block = nb;
    a->blockcap = cap;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* One block                                                          */
/*                                                                    */
/* Header under the initial model: the randomisation bit, then         */
/* blockbits bits of the index the walk starts from. (The end-of-file  */
/* bit that precedes each header is read by the caller, because it is  */
/* what decides whether there IS a block.) Then, under the selector    */
/* model: 0 and 1 count zeros (the write-up's zero_state/zero_count),  */
/* 2 is the MTF rank 1, 3..9 name the model the rank is read under,    */
/* and 10 ends the block. After the block: the models the block used   */
/* are re-initialised, and the next end-of-file bit is read — set, it  */
/* is followed by the 32-bit CRC, sixteen bits at a time.              */
/* ------------------------------------------------------------------ */

static int ars_read_block(Arsenic *a, UncAlloc *al)
{
    int32_t sel, rank;

    ars_mtf_reset(&a->mtf);

    a->randomized = (int)ars_decode(&a->dec, &a->initial);
    a->transformindex = (uint32_t)ars_bits(&a->dec, &a->initial, a->blockbits);
    if (a->dec.err != UNC_OK) return a->dec.err;
    a->numbytes = 0;

    for (;;) {
        sel = ars_decode(&a->dec, &a->selector);
        if (sel < 0) return a->dec.err != UNC_OK ? a->dec.err : UNC_ERR_CORRUPT;

        if (sel == 0 || sel == 1) {
            /* Zero counting: each 0 adds the state, each 1 twice the
             * state, and the state doubles every time. */
            uint32_t zerostate = 1, zerocount = 0;
            while (sel < 2) {
                if (sel == 0) zerocount += zerostate;
                else zerocount += 2 * zerostate;
                zerostate *= 2;
                sel = ars_decode(&a->dec, &a->selector);
                if (sel < 0)
                    return a->dec.err != UNC_OK ? a->dec.err : UNC_ERR_CORRUPT;
                if (zerocount > a->blocksize) return UNC_ERR_CORRUPT;
            }
            if (a->numbytes + zerocount > a->blocksize) return UNC_ERR_CORRUPT;
            {
                int rerr = ars_block_reserve(a, al, a->numbytes + zerocount);
                if (rerr != UNC_OK) return rerr;
            }
            {
                uint8_t z = ars_mtf_decode(&a->mtf, 0);
                uint32_t i;
                for (i = 0; i < zerocount; i++) a->block[a->numbytes + i] = z;
            }
            a->numbytes += zerocount;
        }

        if (sel == 10) break;
        else if (sel == 2) rank = 1;
        else {
            rank = ars_decode(&a->dec, &a->mtfmodel[sel - 3]);
            if (rank < 0)
                return a->dec.err != UNC_OK ? a->dec.err : UNC_ERR_CORRUPT;
        }

        if (a->numbytes >= a->blocksize) return UNC_ERR_CORRUPT;
        {
            int rerr = ars_block_reserve(a, al, a->numbytes + 1);
            if (rerr != UNC_OK) return rerr;
        }
        a->block[a->numbytes++] = ars_mtf_decode(&a->mtf, rank);
    }

    if (a->transformindex >= a->numbytes) return UNC_ERR_CORRUPT;

    ars_model_reset(&a->selector);
    {
        int32_t i;
        for (i = 0; i < 7; i++) ars_model_reset(&a->mtfmodel[i]);
    }

    {
        int32_t end = ars_decode(&a->dec, &a->initial);
        if (end < 0) return a->dec.err != UNC_OK ? a->dec.err : UNC_ERR_CORRUPT;
        if (end) {
            int32_t lo = ars_bits(&a->dec, &a->initial, 16);
            int32_t hi = ars_bits(&a->dec, &a->initial, 16);
            if (lo < 0 || hi < 0)
                return a->dec.err != UNC_OK ? a->dec.err : UNC_ERR_CORRUPT;
            a->compcrc = (uint32_t)lo | ((uint32_t)hi << 16);
            a->has_compcrc = 1;
            a->endofblocks = 1;
        }
    }

    /* Size the inverse-BWT structure to the actual block fill, not the
     * declared block size: real archives use 512 KB blocks even for
     * tiny files, and the transform is the dominant allocation. This is
     * what lets small Arsenic files fit a small budget. */
    return ars_bwt_prepare(a, al);
}

/* span * num / den in 32-bit arithmetic (68000 discipline: no 64-bit in
 * hot paths). Shifts num and den down together until the product cannot
 * overflow, which costs at most one part in 2^16 of precision — far finer
 * than a progress bar can show. */
static uint32_t ars_scale(uint32_t span, uint32_t num, uint32_t den)
{
    if (den == 0 || span == 0) return 0;
    if (num > den) num = den;
    while (num != 0 && num > 0xFFFFFFFFu / span) { num >>= 1; den >>= 1; }
    if (den == 0) return span;
    return span * num / den;
}

/* ------------------------------------------------------------------ */
/* The fork                                                           */
/* ------------------------------------------------------------------ */

int unc_arsenic_decode(UncBufIn *in, UncAlloc *al, uint32_t outlen,
                       UncForkOut *f)
{
    Arsenic *a;
    uint32_t produced = 0;
    uint32_t nexttick = 0;
    int err = UNC_OK;
    int32_t v;
    /* This fork's input span, for reporting progress by OUTPUT. Arsenic
     * decodes a whole block before emitting any of it, so the input
     * position races to the end of the fork and then stops moving while
     * the walk runs — which under the sampled index is most of the time.
     * Hold the input pump and interpolate across the span instead. */
    uint32_t pbase = in->ps ? in->ps->done : 0;
    uint32_t pspan = in->limit;
    uint32_t phold = in->ps ? in->ps->hold : 0;

    if (in->ps) in->ps->hold = 1;

    /* The stream's own check is a CRC-32 over the output, and the fork
     * writer keeps one over what it stages: seeded here, read back
     * after the final flush. The container's CRC-16 means nothing for
     * this method and the caller does not ask for it. */
    f->ck = UNC_CK_CRC32;
    f->crc32 = UNC_CRC32_INIT;

    a = (Arsenic *)unc_alloc(al, (uint32_t)sizeof *a);
    if (!a) { if (in->ps) in->ps->hold = phold; return UNC_ERR_MEM; }
    a->block = NULL;
    a->transform = NULL;
    a->index = NULL;

    unc_bitin_init(&a->bi, in);
    ars_dec_init(&a->dec, &a->bi);

    /* The nine models, as the write-up tabulates them: symbols, increment,
     * limit. The selector's 88 = 11 * 8 and the rest follow. */
    {
        int32_t *pool = a->pool;
        ars_model_init(&a->initial,     pool,        0,   1,   1,  256);
        ars_model_init(&a->selector,    pool + 2,    0,  10,   8, 1024);
        ars_model_init(&a->mtfmodel[0], pool + 13,   2,   3,   8, 1024);
        ars_model_init(&a->mtfmodel[1], pool + 15,   4,   7,   4, 1024);
        ars_model_init(&a->mtfmodel[2], pool + 19,   8,  15,   4, 1024);
        ars_model_init(&a->mtfmodel[3], pool + 27,  16,  31,   4, 1024);
        ars_model_init(&a->mtfmodel[4], pool + 43,  32,  63,   2, 1024);
        ars_model_init(&a->mtfmodel[5], pool + 75,  64, 127,   2, 1024);
        ars_model_init(&a->mtfmodel[6], pool + 139, 128, 255,  1, 1024);
    }

    /* "As", then the block size code. */
    v = ars_bits(&a->dec, &a->initial, 8);
    if (v != 'A') { err = v < 0 ? a->dec.err : UNC_ERR_CORRUPT; goto out; }
    v = ars_bits(&a->dec, &a->initial, 8);
    if (v != 's') { err = v < 0 ? a->dec.err : UNC_ERR_CORRUPT; goto out; }
    v = ars_bits(&a->dec, &a->initial, 4);
    if (v < 0) { err = a->dec.err; goto out; }
    a->blockbits = v + 9;
    a->blocksize = 1u << a->blockbits;

    /* Deliberately NOT allocated at a->blocksize; ars_block_reserve() grows it
     * to whatever the blocks actually hold. */
    a->block = NULL;
    a->blockcap = 0;
    a->outlen = outlen;
    a->transform = NULL;
    a->transform_cap = 0;
    a->index = NULL;

    a->numbytes = a->bytecount = 0;
    a->repeat = 0;
    a->count = 0;
    a->last = 0;
    a->compcrc = 0;
    a->has_compcrc = 0;
    a->randomized = 0;
    a->transformindex = 0;

    v = ars_decode(&a->dec, &a->initial);            /* first end-of-file bit */
    if (v < 0) { err = a->dec.err; goto out; }
    a->endofblocks = v;

    while (produced < outlen) {
        uint8_t outbyte;

        /* The only progress this decoder reports: the input pump is held
         * for the whole fork (see pbase/pspan above), so this is what
         * keeps the dialog alive, moves the bar and notices a Cancel.
         * Driven by OUTPUT, on both paths — the walk is where the time
         * goes under the sampled index, and it reads no input at all.
         * Thresholded rather than tested with a mask because `retry`
         * below re-enters the loop body without advancing `produced`. */
        if (produced >= nexttick) {
            nexttick = produced + ARS_PROGRESS_STEP;
            err = unc_progress_at(in->ps,
                                  pbase + ars_scale(pspan, produced, outlen));
            if (err != UNC_OK) goto out;
        }

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

            a->transformindex = a->index
                ? ars_index_next(a, a->transformindex)
                : ars_transform_get(a->transform, a->transformindex);
            byte = a->block[a->transformindex];

            /* Randomisation: flip bit 0 of the byte at each position the
             * table names, cumulatively. */
            if (a->randomized && (uint32_t)a->randcount == a->bytecount) {
                byte ^= 1;
                a->randindex = (a->randindex + 1) & 255;
                a->randcount += (int32_t)ars_randtable[a->randindex];
            }

            a->bytecount++;

            /* The byte-stuffing RLE: after four equal bytes, the next
             * byte is how many more of them there are. */
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

        if ((err = unc_fork_put(f, outbyte)) != UNC_OK) goto out;
        produced++;
    }

    err = unc_fork_flush(f);
    if (err == UNC_OK && a->has_compcrc && a->compcrc != ~f->crc32)
        err = UNC_ERR_CRC;

out:
    unc_free(al, a->index);
    unc_free(al, a->transform);
    unc_free(al, a->block);
    unc_free(al, a);
    if (in->ps) in->ps->hold = phold;
    return err;
}

/*
 * unc_lzw.c — Unix compress(1)-compatible LZW decoder.
 *
 * Used by StuffIt classic method 2 (14-bit codes, block mode), by .Z
 * files (parameters from the .Z header), by ARC's methods 8 and 9 and
 * by DiskDoubler method 1. Codes are LSB-first bit strings of
 * 9..maxbits bits — the one little-endian bit stream in the classic
 * Mac world.
 *
 * Source: reference/deark/src/fmtutil-lzw.c (Jason Summers, MIT) for
 * the compress(1) stream — the clear code, the point at which the code
 * width grows, and the padding rule below. The algorithm itself is
 * Welch's (T. A. Welch, "A Technique for High-Performance Data
 * Compression", IEEE Computer 17(6), 1984): a code stands for a string,
 * every code read defines one new string — the previous code's string
 * followed by the first byte of this one's — and a code may name the
 * string it is itself about to define.
 *
 * The one quirk that is not in the algorithm: compress(1) writes its
 * codes in groups of eight of the same width, so when the width
 * changes mid-group the rest of the group is padding and is discarded.
 * A clear code is where that bites, because it drops the width back to
 * 9 at an arbitrary point; at the width INCREASES the group happens to
 * be full already, so nothing is skipped there (fmtutil-lzw.c,
 * delzw_unixcompress_end_bitgroup).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* The value len[] saturates at. 255 in every shipped build; ci.sh
 * builds one variant at 4 so that lzw_strlen's resolving walk — which
 * no archive in the corpus is long enough to reach — runs on nearly
 * every string, and the output has to stay byte-exact. See TESTING.md,
 * *The LZW string length*. */
#ifndef UNC_LZW_LEN_MAX
#define UNC_LZW_LEN_MAX 255
#endif

/* Layout of the single allocation:
 *   parent[capsymbols] u16, chr[capsymbols] u8, len[capsymbols] u8
 *
 * `len` is what makes the decode loop cheap, and it is the reason this
 * file has no staging buffer. A symbol's string is stored backwards —
 * chr[s] is its LAST byte and parent[s] names the rest — so walking it
 * produces the bytes in reverse. Knowing the LENGTH first means the
 * walk can store straight into the caller's buffer from the far end
 * backwards, and the string lands the right way round with no second
 * pass over it. Before 2026-09-19 the walk filled a capsymbols-byte
 * staging array and a reverse copy moved it out, which was 17.8 % of a
 * `.Z` run on its own (DECISIONS.md 2026-09-19).
 *
 * It costs nothing: `len` is one byte per symbol, exactly what the
 * staging array was, so the allocation is the same cap * 4. A string
 * of UNC_LZW_LEN_MAX bytes or more stores that value, and lzw_strlen
 * walks up the parents to recover the exact figure — which no archive
 * in the corpus ever needs, the longest string measured anywhere being
 * 223 bytes, so ci.sh moves the saturation point instead (above).
 *
 * capsymbols is sized from the INPUT, not from maxbits. compress(1)
 * writes maxbits=16 by default whatever it compressed, so a 488-byte .Z
 * declares a 65536-entry table it fills a few hundred entries of. Every
 * input code defines at most one new symbol, so the input bounds the
 * table however large maxbits claims.
 *
 * The bound walks the CODE-WIDTH SCHEDULE rather than assuming every
 * code is the minimum 9 bits. A code is 9 bits only while numsymbols is
 * under 512, 10 bits under 1024, and so on — the same rule the decode
 * loop applies below — so a byte buys progressively fewer symbols the
 * further in the stream it sits, and `insize * 8 / 9` overpays badly on
 * inputs big enough to widen. On popper-1.7.tar.Z, 59,323 B in, it is
 * 52,988 entries against 33,870: 211,952 B of table against 135,480 B,
 * which is the difference between refusing that file on a 512 KB
 * Macintosh and extracting it (FORMATS.md, *512 KB machines*).
 *
 * Still strict, for three reasons that all cut the same way. Creating
 * the symbol that takes numsymbols to k costs a code at the width in
 * force at the time, which is what lzw_cap_from_input sums. The first
 * code of a stream creates nothing. And in block mode a clear resets
 * numsymbols AND the width to 9, so the bits are split between
 * generations — the reachable maximum is per generation, and one
 * generation holding every bit dominates any split, because the
 * schedule is increasing in the bits it is given.
 *
 * Sized once, up front: growth by copy has an unavoidable old+new
 * transient, and where the table IS the allocation that transient
 * becomes the peak (measured: popper-1.7.tar.Z 274,432 -> 405,504 B
 * under doubling). lzw_grow below is a safety net for an under-estimate,
 * not a strategy; with a correct bound it never runs. */

/* How many symbols `insize` bytes can define, walking the width schedule.
 * Returns the count including the initial 256 + reserved. */
static uint32_t lzw_cap_from_input(uint32_t insize, uint32_t start,
                                   int maxbits)
{
    uint32_t bits, sym;
    int width;

    /* insize * 8 must not wrap. Anything this large bounds nothing
     * anyway: 2^29 bytes buys every symbol at any maxbits <= 16. */
    if (insize > 0x1FFFFFFFu) insize = 0x1FFFFFFFu;
    bits = insize * 8u;
    sym = start;
    for (width = 9; width <= maxbits; width++) {
        /* Creations still to come at this width, and what they cost.
         * room <= 1 << 16 and width <= 16, so the product is small. */
        uint32_t room = (1u << width) - sym;
        uint32_t cost = room * (uint32_t)width;
        if (cost > bits) return sym + bits / (uint32_t)width;
        bits -= cost;
        sym += room;
    }
    return sym;
}

/* Point the three arrays into a capsymbols-entry block. */
static void lzw_layout(UncLzw *z, uint8_t *mem, uint32_t cap)
{
    z->mem    = mem;
    z->parent = (uint16_t *)(void *)mem;              /* 2-aligned: alloc */
    z->chr    = mem + cap * 2;
    z->len    = mem + cap * 3;
}

int unc_lzw_init(UncLzw *z, UncAlloc *al, UncBufIn *in,
                 int maxbits, int blockmode, uint32_t insize)
{
    int32_t i;
    uint32_t maxsym, cap;
    uint8_t *mem;

    if (maxbits < 9 || maxbits > 16) return UNC_ERR_CORRUPT;
    maxsym = 1u << maxbits;

    cap = maxsym;
    if (insize > 0) {
        /* +1 keeps the slack the old bound carried: the sizing is an
         * upper bound on symbols DEFINED, and lzw_grow is the net if it
         * were ever short. */
        uint32_t want = lzw_cap_from_input(
            insize, 256u + (blockmode ? 1u : 0u), maxbits) + 1u;
        if (want < cap) cap = want;
    }
#ifdef UNC_LZW_TINY_TABLE
    /* Deliberately under-estimate so lzw_grow runs on every stream that
     * defines a symbol. The output must stay byte-exact; that is the
     * only way the safety net is ever exercised. See TESTING.md. */
    cap = 258;
#endif

    mem = (uint8_t *)unc_alloc(al, cap * 4);
    if (!mem) return UNC_ERR_MEM;
    lzw_layout(z, mem, cap);

    z->in = in;
    z->al = al;
    z->capsymbols = (int32_t)cap;
    z->maxsymbols = (int32_t)maxsym;
    z->reserved = blockmode ? 1 : 0;
    z->blockmode = blockmode;
    z->bitbuf = 0;
    z->nbits = 0;

    /* The 256 single-byte strings. Their parent is never read — a walk
     * is bounded by the length it was given, and a root is where that
     * length runs out — so only chr and len are laid down here. */
    for (i = 0; i < 256; i++) {
        z->chr[i] = (uint8_t)i;
        z->len[i] = 1;
    }
    z->numsymbols = 256 + z->reserved;
    z->prevsymbol = -1;
    z->symbolsize = 9;
    z->symbolcounter = 0;
    z->pendsym = 0;
    z->pendn = z->pende = 0;
    z->pendtop = 0;
    z->topbyte = z->lastfirst = 0;
    return UNC_OK;
}

void unc_lzw_free(UncLzw *z, UncAlloc *al)
{
    unc_free(al, z->mem);
    z->mem = NULL;
}

/* Safety net for an under-estimated bound: widen to the declared
 * ceiling so a wrong estimate stays CORRECT rather than overflowing the
 * table. Not a growth strategy — see the layout note above. */
static int lzw_grow(UncLzw *z)
{
    uint32_t cap = (uint32_t)z->maxsymbols;
    int32_t used = z->numsymbols;
    uint16_t *oldparent = z->parent;
    uint8_t *oldmem = z->mem, *oldchr = z->chr, *oldlen = z->len, *mem;
    int32_t i;

    if (z->capsymbols >= (int32_t)cap) return UNC_ERR_CORRUPT;

    mem = (uint8_t *)unc_alloc(z->al, cap * 4);
    if (!mem) return UNC_ERR_MEM;
    lzw_layout(z, mem, cap);                      /* 2-aligned: alloc */
    /* All three carry across. `len` did not exist when this copied two
     * arrays, and the staging buffer it replaced carried nothing. */
    for (i = 0; i < used; i++) {
        z->parent[i] = oldparent[i];
        z->chr[i] = oldchr[i];
        z->len[i] = oldlen[i];
    }
    unc_free(z->al, oldmem);
    z->capsymbols = (int32_t)cap;
    return UNC_OK;
}

/* Next LSB-first n-bit code, or -1 on input end/error. */
static UNC_HOT int32_t lzw_code(UncLzw *z, int n)
{
    while (z->nbits < n) {
        int b = unc_bufin_next(z->in);
        if (b < 0) return -1;
        z->bitbuf |= (uint32_t)b << z->nbits;
        z->nbits += 8;
    }
    {
        int32_t v = (int32_t)(z->bitbuf & ((1u << n) - 1));
        z->bitbuf >>= n;
        z->nbits -= n;
        return v;
    }
}

/* The exact length of symbol's string.
 *
 * len[] saturates at 255, so that is the only value that has to be
 * resolved: walk up the parents, each step one byte shorter, until one
 * of them carries a length that did not saturate. A root never does
 * (its length is 1), so this terminates, and it costs length-254 steps
 * rather than a walk of the whole string. */
static int32_t lzw_strlen(const UncLzw *z, int32_t symbol)
{
    int32_t n = z->len[symbol];

    if (n == UNC_LZW_LEN_MAX) {
        const uint16_t *parent = z->parent;
        const uint8_t *len = z->len;
        int32_t s = symbol;
        n = 0;
        while (len[s] == UNC_LZW_LEN_MAX) { n++; s = parent[s]; }
        n += len[s];
    }
    return n;
}

/* Write k bytes of the pending string into dst, resuming at pende.
 *
 * The walk hands the bytes over backwards, so they are stored from
 * dst[k-1] down to dst[0] and come out in order. Bytes above the ones
 * wanted are passed over by following parents without storing, which is
 * what lets a string longer than the caller's buffer be handed over in
 * pieces across several calls without any buffer of its own.
 *
 * Returns dst[0], the first byte written. When pende is 0 that is the
 * first byte of the whole string, which is the byte the next table
 * entry is built with. */
static UNC_HOT uint8_t lzw_emit(UncLzw *z, uint8_t *dst, int32_t k)
{
    /* Locals: a 68000 reloads a struct field from memory on every use,
     * and this is the loop that moves every byte of an LZW stream. */
    const uint16_t *parent = z->parent;
    const uint8_t *chr = z->chr;
    int32_t s = z->pendsym;
    int32_t skip = z->pendn - z->pende - k;
    uint8_t *q = dst + k;

    /* A code that named the string it was about to define expands to
     * the previous string plus that string's own first byte. That extra
     * byte is the LAST one out, so it heads the walk. */
    if (z->pendtop) {
        if (skip > 0) skip--;
        else *--q = z->topbyte;
    }
    while (skip-- > 0) s = parent[s];
    while (q > dst) {
        *--q = chr[s];
        if (q == dst) break;
        s = parent[s];
    }
    return *dst;
}

/* Decode into out, up to want bytes. Returns bytes produced (0 only at
 * clean end of stream), or a negative UNC_ERR_*. */
UNC_HOT int32_t unc_lzw_read(UncLzw *z, uint8_t *out, int32_t want)
{
    int32_t produced = 0;

    /* What the previous call could not fit. One piece at most: k is the
     * smaller of what is left and what fits, so this either finishes the
     * string or fills the buffer. */
    if (z->pende < z->pendn) {
        int32_t k = z->pendn - z->pende;
        if (k > want) k = want;
        if (k > 0) {
            (void)lzw_emit(z, out, k);
            z->pende += k;
            produced = k;
        }
    }

    while (produced < want) {
        int32_t symbol, n, k;

        for (;;) {
            symbol = lzw_code(z, z->symbolsize);
            if (symbol < 0) {
                /* Input end: clean if it falls between codes. */
                if (z->in->err == UNC_ERR_TRUNCATED && z->nbits < z->symbolsize)
                    return produced;
                return z->in->err;
            }
            z->symbolcounter++;
            if (symbol == 256 && z->blockmode) {
                /* Clear code: discard the rest of the eight-code group,
                 * then start the table and the width again. */
                if (z->symbolcounter % 8) {
                    int32_t skip =
                        z->symbolsize * (8 - (int32_t)(z->symbolcounter % 8));
                    while (skip > 0) {
                        int32_t chunk = skip > 16 ? 16 : skip;
                        if (lzw_code(z, (int)chunk) < 0)
                            return z->in->err == UNC_ERR_TRUNCATED
                                 ? produced : z->in->err;
                        skip -= chunk;
                    }
                }
                z->numsymbols = 256 + z->reserved;
                z->prevsymbol = -1;
                z->symbolsize = 9;
                z->symbolcounter = 0;
            } else break;
        }

        if (symbol < z->numsymbols) {
            z->pendsym = symbol;
            z->pendtop = 0;
        } else if (symbol == z->numsymbols && z->prevsymbol >= 0) {
            /* The code names the entry it is itself about to define, so
             * its string is the previous one plus the previous one's
             * first byte — which is the byte the last string started
             * with, and is already in hand. */
            z->pendsym = z->prevsymbol;
            z->pendtop = 1;
            z->topbyte = z->lastfirst;
        } else {
            return UNC_ERR_CORRUPT;
        }
        n = lzw_strlen(z, z->pendsym) + z->pendtop;

        z->pendn = n;
        z->pende = 0;
        k = n > want - produced ? want - produced : n;
        z->lastfirst = lzw_emit(z, out + produced, k);
        z->pende = k;
        produced += k;

        /* The new entry: the previous string followed by the first byte
         * of this one. Nothing is added for the first code of a
         * generation, which has no previous string; and once the table
         * has reached the declared ceiling, codes keep decoding and
         * nothing more is added. */
        if (z->prevsymbol >= 0 && z->numsymbols < z->maxsymbols) {
            int32_t plen;
            if (z->numsymbols >= z->capsymbols) {
                int gerr = lzw_grow(z);
                if (gerr != UNC_OK) return gerr;
            }
            plen = z->len[z->prevsymbol];
            z->parent[z->numsymbols] = (uint16_t)z->prevsymbol;
            z->chr[z->numsymbols] = z->lastfirst;
            z->len[z->numsymbols] =
                (uint8_t)(plen < UNC_LZW_LEN_MAX ? plen + 1 : UNC_LZW_LEN_MAX);
            z->numsymbols++;
            if (z->numsymbols < z->maxsymbols &&
                (z->numsymbols & (z->numsymbols - 1)) == 0)
                z->symbolsize++;
        }
        z->prevsymbol = symbol;
    }
    return produced;
}

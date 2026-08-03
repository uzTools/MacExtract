/*
 * unc_lzw.c — Unix compress(1)-compatible LZW decoder.
 *
 * Used by StuffIt classic method 2 (14-bit, block mode — XADMaster
 * passes flags 0x8e) and by .Z files in M8 (parameters from the .Z
 * header). Codes are LSB-first bit strings of 9..maxbits bits — the
 * one little-endian bit stream in the classic Mac world.
 *
 * Transcribed from reference/XADMaster/LZW.c and
 * reference/XADMaster/XADCompressHandle.m — LGPL, see NOTICE.
 * Compress quirks preserved:
 *   - the code width grows when the table size reaches a power of two;
 *   - in block mode, code 256 clears the table AND the reader skips
 *     to the end of the current 8-code group ("Skip garbage data
 *     after a clear. God damn, this is dumb." — XADCompressHandle.m).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define UNC_LZW_NOPARENT 0xFFFFu   /* parent sentinel: the last symbol
                                    * (maxsymbols-1) can never be a
                                    * parent, so 0xFFFF is safe even
                                    * at 16-bit maxbits */

/* Layout of the single allocation:
 *   parent[capsymbols] u16, chr[capsymbols] u8, chain[capsymbols] u8
 *
 * capsymbols is sized from the INPUT, not from maxbits. compress(1)
 * writes maxbits=16 by default whatever it compressed, so a 488-byte .Z
 * declares a 65536-entry table it fills a few hundred entries of. Every
 * input code defines at most one new symbol and codes are at least 9
 * bits wide, so
 *
 *     symbols <= 256 + reserved + insize * 8 / 9
 *
 * however large maxbits claims. The bound is strict: reaching entry
 * 256+reserved+k needs k+1 codes, so the table cannot fill even when
 * every code is the minimum width — which is what lets maxsymbols keep
 * its declared value and the decode stay bit-identical.
 *
 * Sized once, up front: growth by copy has an unavoidable old+new
 * transient, and where the table IS the allocation that transient
 * becomes the peak (measured: popper-1.7.tar.Z 274,432 -> 405,504 B
 * under doubling). lzw_grow below is a safety net for an under-estimate,
 * not a strategy; with a correct bound it never runs. */

/* Point the three arrays into a capsymbols-entry block. */
static void lzw_layout(UncLzw *z, uint8_t *mem, uint32_t cap)
{
    z->mem    = mem;
    z->parent = (uint16_t *)(void *)mem;              /* 2-aligned: alloc */
    z->chr    = mem + cap * 2;
    z->chain  = mem + cap * 3;
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
        /* floor(insize * 8 / 9) without overflowing 32 bits. */
        uint32_t codes = insize / 9 * 8 + insize % 9 * 8 / 9;
        if (codes < maxsym) {
            uint32_t want = 257 + (blockmode ? 1u : 0u) + codes;
            if (want < cap) cap = want;
        }
    }
#ifdef UNC_LZW_TINY_TABLE
    /* Deliberately under-estimate so lzw_grow runs on every stream that
     * defines a symbol. The output must stay byte-exact; that is the
     * only way the safety net is ever exercised. See MANUAL_TESTS.md. */
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
    z->chainlen = z->chainpos = 0;

    for (i = 0; i < 256; i++) {
        z->chr[i] = (uint8_t)i;
        z->parent[i] = UNC_LZW_NOPARENT;
    }
    z->numsymbols = 256 + z->reserved;
    z->prevsymbol = -1;
    z->symbolsize = 9;
    z->symbolcounter = 0;
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
    uint8_t *oldmem = z->mem, *oldchr = z->chr, *mem;
    int32_t i;

    if (z->capsymbols >= (int32_t)cap) return UNC_ERR_CORRUPT;

    mem = (uint8_t *)unc_alloc(z->al, cap * 4);
    if (!mem) return UNC_ERR_MEM;
    lzw_layout(z, mem, cap);                      /* 2-aligned: alloc */
    for (i = 0; i < used; i++) {
        z->parent[i] = oldparent[i];
        z->chr[i] = oldchr[i];
    }
    unc_free(z->al, oldmem);
    z->capsymbols = (int32_t)cap;
    /* chain carries nothing across: it is fully drained before any
     * symbol is added (see unc_lzw_read). */
    z->chainlen = z->chainpos = 0;
    return UNC_OK;
}

/* Next LSB-first n-bit code, or -1 on input end/error. */
static int32_t lzw_code(UncLzw *z, int n)
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

static uint8_t lzw_firstbyte(const UncLzw *z, int32_t symbol)
{
    while (z->parent[symbol] != UNC_LZW_NOPARENT)
        symbol = z->parent[symbol];
    return z->chr[symbol];
}

/* Decode into out, up to want bytes. Returns bytes produced (0 only at
 * clean end of stream), or a negative UNC_ERR_*. */
int32_t unc_lzw_read(UncLzw *z, uint8_t *out, int32_t want)
{
    int32_t produced = 0;

    while (produced < want) {
        /* Drain the pending chain first. */
        while (z->chainpos > 0 && produced < want)
            out[produced++] = z->chain[--z->chainpos];
        if (produced == want) break;

        {
            int32_t symbol, postfix, parent;
            int32_t n;

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
                    /* Clear code: skip the rest of the 8-code group
                     * (compress pads its output in groups of 8 codes),
                     * then reset the table. */
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

            /* Transcription of LZW.c NextLZWSymbol. */
            if (z->prevsymbol < 0) {
                if (symbol >= z->numsymbols) return UNC_ERR_CORRUPT;
                z->prevsymbol = symbol;
            } else {
                if (symbol < z->numsymbols)
                    postfix = lzw_firstbyte(z, symbol);
                else if (symbol == z->numsymbols)
                    postfix = lzw_firstbyte(z, z->prevsymbol);
                else
                    return UNC_ERR_CORRUPT;

                parent = z->prevsymbol;
                z->prevsymbol = symbol;

                if (z->numsymbols < z->maxsymbols) {
                    if (z->numsymbols >= z->capsymbols) {
                        int gerr = lzw_grow(z);
                        if (gerr != UNC_OK) return gerr;
                    }
                    z->parent[z->numsymbols] = (uint16_t)parent;
                    z->chr[z->numsymbols] = (uint8_t)postfix;
                    z->numsymbols++;
                    if (z->numsymbols < z->maxsymbols &&
                        (z->numsymbols & (z->numsymbols - 1)) == 0)
                        z->symbolsize++;
                }
                /* Table full: symbols keep decoding, nothing is added
                 * (LZW.c returns LZWTooManyCodesError but
                 * XADCompressHandle only checks for InvalidCode). */
            }

            /* Emit prevsymbol's chain, reversed into z->chain. */
            n = 0;
            {
                int32_t s = z->prevsymbol;
                while (s >= 0 && n < z->capsymbols) {
                    z->chain[n++] = z->chr[s];
                    s = z->parent[s] == UNC_LZW_NOPARENT ? -1
                                                         : (int32_t)z->parent[s];
                }
                /* Bounded by the chain buffer, which is capsymbols long.
                 * A well-formed chain is strictly decreasing and ends in
                 * the 0..255 roots, so it cannot reach that. */
                if (n >= z->capsymbols) return UNC_ERR_CORRUPT;
            }
            z->chainpos = z->chainlen = n;
        }
    }
    return produced;
}

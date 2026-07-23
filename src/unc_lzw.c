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
 *   parent[maxsymbols] u16, chr[maxsymbols] u8, chain[maxsymbols] u8 */

int unc_lzw_init(UncLzw *z, UncAlloc *al, UncBufIn *in,
                 int maxbits, int blockmode)
{
    int32_t i;
    uint32_t maxsym;

    if (maxbits < 9 || maxbits > 16) return UNC_ERR_CORRUPT;
    maxsym = 1u << maxbits;

    z->mem = (uint8_t *)unc_alloc(al, maxsym * 4);
    if (!z->mem) return UNC_ERR_MEM;
    z->parent = (uint16_t *)(void *)z->mem;           /* 2-aligned: alloc */
    z->chr    = z->mem + maxsym * 2;
    z->chain  = z->mem + maxsym * 3;

    z->in = in;
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
                while (s >= 0 && n < z->maxsymbols) {
                    z->chain[n++] = z->chr[s];
                    s = z->parent[s] == UNC_LZW_NOPARENT ? -1
                                                         : (int32_t)z->parent[s];
                }
                if (n >= z->maxsymbols) return UNC_ERR_CORRUPT;
            }
            z->chainpos = z->chainlen = n;
        }
    }
    return produced;
}

/*
 * unc_huffman.c — MSB-first bit reader + bit-serialized Huffman trees.
 *
 * Sources:
 *   reference/XADMaster/XADStuffItHuffmanHandle.m (parseTree),
 *   reference/macutils/macunpack/de_huffman.c (read_sub_tree,
 *   getbit_be) — LGPL, see NOTICE.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* ------------------------------------------------------------------ */
/* Bit reader                                                         */
/* ------------------------------------------------------------------ */

void unc_bitin_init(UncBitIn *b, UncBufIn *in)
{
    b->in = in;
    b->bitbuf = 0;
    b->nbits = 0;
    b->le = 0;
    b->err = UNC_OK;
}

void unc_bitin_init_le(UncBitIn *b, UncBufIn *in)
{
    unc_bitin_init(b, in);
    b->le = 1;
}

int unc_bitin_bit(UncBitIn *b)
{
    if (b->nbits == 0) {
        int byte = unc_bufin_next(b->in);
        if (byte < 0) { b->err = b->in->err; return -1; }
        b->bitbuf = (uint32_t)byte;
        b->nbits = 8;
    }
    b->nbits--;
    if (b->le) {
        int bit = (int)(b->bitbuf & 1u);
        b->bitbuf >>= 1;
        return bit;
    }
    return (int)((b->bitbuf >> b->nbits) & 1u);
}

int32_t unc_bitin_bits(UncBitIn *b, int n)
{
    int32_t v = 0;
    while (n-- > 0) {
        int bit = unc_bitin_bit(b);
        if (bit < 0) return -1;
        v = (v << 1) | bit;
    }
    return v;
}

int32_t unc_bitin_bits_le(UncBitIn *b, int n)
{
    int32_t v = 0;
    int i;
    for (i = 0; i < n; i++) {
        int bit = unc_bitin_bit(b);
        if (bit < 0) return -1;
        v |= (int32_t)bit << i;
    }
    return v;
}

void unc_bitin_align(UncBitIn *b)
{
    b->nbits = 0;
    b->bitbuf = 0;
}

uint32_t unc_bitin_bytepos(const UncBitIn *b)
{
    /* Bytes handed out by the bufin, minus whole bytes still buffered
     * in bitbuf. (Bytes handed out = fed from io - unread in window.) */
    uint32_t consumed = b->in->lenfed - (b->in->len - b->in->pos);
    return consumed - ((uint32_t)b->nbits >> 3);
}

/* ------------------------------------------------------------------ */
/* Tree building (iterative — engine forbids recursion)               */
/* ------------------------------------------------------------------ */

int unc_huff_read_tree(UncHuff *h, UncBitIn *bi)
{
    /* Stack of pending child slots: (node << 1) | side, filled in the
     * serialized order: zero branch fully, then one branch. */
    int16_t stack[UNC_HUFF_MAX_INTERNAL + 4];
    int32_t sp = 0;
    int have_root = 0;

    h->nnodes = 0;

    for (;;) {
        int bit = unc_bitin_bit(bi);
        int16_t val;
        if (bit < 0) return bi->err != UNC_OK ? bi->err : UNC_ERR_CORRUPT;

        if (bit == 1) {
            int32_t sym = unc_bitin_bits(bi, 8);
            if (sym < 0) return bi->err != UNC_OK ? bi->err : UNC_ERR_CORRUPT;
            val = (int16_t)(-(sym + 1));
        } else {
            if (h->nnodes >= UNC_HUFF_MAX_INTERNAL) return UNC_ERR_CORRUPT;
            val = h->nnodes++;
        }

        if (!have_root) {
            h->root = val;
            have_root = 1;
        } else {
            int16_t slot = stack[--sp];
            h->child[slot & 1][slot >> 1] = val;
        }

        if (val >= 0) {
            /* Internal node: its zero branch comes next in the stream,
             * so push the one-side first (LIFO). */
            if (sp + 2 > (int32_t)(sizeof stack / sizeof stack[0]))
                return UNC_ERR_CORRUPT;
            stack[sp++] = (int16_t)((val << 1) | 1);
            stack[sp++] = (int16_t)((val << 1) | 0);
        }

        if (sp == 0) return UNC_OK;   /* every slot filled: done */
    }
}

int unc_huff_decode(const UncHuff *h, UncBitIn *bi)
{
    int16_t cur = h->root;
    int32_t guard = 0;
    while (cur >= 0) {
        int bit = unc_bitin_bit(bi);
        if (bit < 0) return -1;
        cur = h->child[bit][cur];
        /* A malformed tree cannot loop (children always point to
         * later-allocated nodes or leaves), but guard anyway. */
        if (++guard > 300) return -1;
    }
    return -(cur + 1);
}

/* ------------------------------------------------------------------ */
/* Canonical (code-length) Huffman codes                              */
/* Codes assigned in (length, symbol) order, shortest code all-zeros, */
/* decoded MSB-first. Sources:                                        */
/*   reference/XADMaster/XADPrefixCode.m (initWithLengths:...         */
/*   shortestCodeIsZeros:YES) and                                     */
/*   reference/macutils/macunpack/cpt.c (cpt_readHuff: sort by        */
/*   (BitLength, Value) then assign codes; "Compactor allows unused   */
/*   trailing codes in its Huffman tree", i.e. incomplete codes are   */
/*   legal and pad out the deep end) — LGPL, see NOTICE.              */
/* ------------------------------------------------------------------ */

int unc_canon_build(UncCanon *c, const uint8_t *lengths, int32_t nsyms)
{
    return unc_canon_build_ext(c, lengths, nsyms, c->symstore,
                               UNC_CANON_MAX_SYMS);
}

/* The same build, over symbol storage the caller supplies. LZH's
 * literal alphabet is 510 symbols, which does not fit the inline
 * store, and growing that store would widen every UncCanon on every
 * decoder's stack — dd_ddn holds three of them. */
int unc_canon_build_ext(UncCanon *c, const uint8_t *lengths, int32_t nsyms,
                        int16_t *symbuf, int32_t symcap)
{
    int32_t i, l;
    uint32_t code, space;
    uint16_t idx[UNC_CANON_MAX_BITS + 1];

    if (nsyms > symcap) return UNC_ERR_CORRUPT;
    c->sym = symbuf;

    for (l = 0; l <= UNC_CANON_MAX_BITS; l++) c->count[l] = 0;
    c->maxlen = 0;
    for (i = 0; i < nsyms; i++) {
        int len = lengths[i];
        if (len == 0) continue;
        if (len > UNC_CANON_MAX_BITS) return UNC_ERR_CORRUPT;
        c->count[len]++;
        if (len > c->maxlen) c->maxlen = (int16_t)len;
    }

    /* First code value at each length (canonical, all-zeros start),
     * and over-subscription check. Incomplete codes are allowed:
     * leftover code space simply decodes as invalid. */
    code = 0;
    space = 0;
    for (l = 1; l <= c->maxlen; l++) {
        c->first[l] = code;
        code = (code + c->count[l]) << 1;
        space = (space << 1) + c->count[l];
        if (space > (1u << l)) return UNC_ERR_CORRUPT;
    }

    /* Symbol table in (length, symbol) order. */
    idx[1] = 0;
    for (l = 1; l < c->maxlen; l++)
        idx[l + 1] = (uint16_t)(idx[l] + c->count[l]);
    for (i = 0; i < nsyms; i++) {
        int len = lengths[i];
        if (len) c->sym[idx[len]++] = (int16_t)i;
    }
    return UNC_OK;
}

int unc_canon_decode(const UncCanon *c, UncBitIn *bi)
{
    uint32_t code = 0, base = 0;
    int l;
    for (l = 1; l <= c->maxlen; l++) {
        int bit = unc_bitin_bit(bi);
        if (bit < 0) return -1;
        code = (code << 1) | (uint32_t)bit;
        if (code - c->first[l] < c->count[l])
            return c->sym[base + (code - c->first[l])];
        base += c->count[l];
    }
    return -1;   /* invalid (possibly "unused trailing") code */
}

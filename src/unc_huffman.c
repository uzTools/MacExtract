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

/* Take n bits in one go when the window already holds them, which is the
 * common case: unc_bitin_fill only moves bytes that are in the UncBufIn's
 * buffer already, so this cannot read ahead across a substream boundary or
 * set the sticky error early (see the header). Callgrind put this function
 * at 9-13 % of a DiskDoubler or Now Compress run doing it one bit at a
 * time, through a call each. The per-bit loop stays as the fallback and is
 * what runs at a window boundary and in LSB-first mode. */
int32_t unc_bitin_bits(UncBitIn *b, int n)
{
    int32_t v = 0;
    if (n <= 0) return 0;
    if (!b->le && n <= 24 && unc_bitin_fill(b, n)) {
        b->nbits -= n;
        return (int32_t)((b->bitbuf >> b->nbits) & ((1u << n) - 1u));
    }
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
    if (n <= 0) return 0;
    if (b->le && n <= 24 && unc_bitin_fill(b, n)) {
        v = (int32_t)(b->bitbuf & ((1u << n) - 1u));
        b->bitbuf >>= n;
        b->nbits -= n;
        return v;
    }
    for (i = 0; i < n; i++) {
        int bit = unc_bitin_bit(b);
        if (bit < 0) return -1;
        v |= (int32_t)bit << i;
    }
    return v;
}

/* Drop the rest of the byte the reader is inside, and hand any WHOLE
 * bytes unc_bitin_fill moved into bitbuf ahead of it back to the window
 * they came from. Zeroing both fields was right only while nbits could
 * never exceed 8; a caller that byte-aligns may go on reading the
 * UncBufIn directly — fmt_cpt.c does, between Huffman blocks — and
 * would otherwise skip whatever had been read ahead.
 *
 * Giving them back is exact: unc_bitin_fill only ever takes bytes that
 * are already in the window, and it cannot run while nbits >= 8, so the
 * window cannot have been refilled underneath them. */
void unc_bitin_align(UncBitIn *b)
{
    b->in->pos -= (uint32_t)((b->nbits & ~7) >> 3);
    b->nbits = 0;
    b->bitbuf = 0;
}

uint32_t unc_bitin_bytepos(const UncBitIn *b)
{
    /* Bytes handed out by the bufin, minus whole bytes still buffered
     * in bitbuf. (Bytes handed out = fed from io - unread in window.)
     *
     * This is the byte position ROUNDED UP, which is what both callers
     * want — a bit reader half-way through a byte has consumed that
     * byte — and it stays the ceiling however many whole bytes
     * unc_bitin_fill has moved ahead, so read-ahead does not shift it. */
    uint32_t consumed = b->in->lenfed - (b->in->len - b->in->pos);
    return consumed - ((uint32_t)b->nbits >> 3);
}

/* ------------------------------------------------------------------ */
/* Tree building (iterative — engine forbids recursion)               */
/* ------------------------------------------------------------------ */

/* Map every UNC_HUFF_FAST_BITS-bit prefix to the code that starts there,
 * by walking the tree once per prefix — 256 walks of at most eight steps,
 * paid once per tree against a decode that walks it per symbol.
 *
 * A tree whose root is already a leaf gets no table: that code consumes
 * NO bits, and every entry here consumes at least one. `fastok` says so
 * and unc_huff_decode falls back to the walk, which handles it. */
static void huff_build_fast(UncHuff *h)
{
    uint32_t p;

    h->fastok = 0;
    if (h->root < 0) return;
    for (p = 0; p < (1u << UNC_HUFF_FAST_BITS); p++) {
        int16_t cur = h->root;
        int l;
        h->fast[p] = 0;
        for (l = 1; l <= UNC_HUFF_FAST_BITS; l++) {
            int bit = (int)((p >> (UNC_HUFF_FAST_BITS - l)) & 1u);
            cur = h->child[bit][cur];
            if (cur < 0) {
                h->fast[p] = (uint16_t)(((-(cur + 1)) << 4) | l);
                break;
            }
        }
    }
    h->fastok = 1;
}

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

        if (sp == 0) { huff_build_fast(h); return UNC_OK; }
    }
}

int unc_huff_decode(const UncHuff *h, UncBitIn *bi)
{
    int16_t cur = h->root;
    int32_t guard = 0;

    /* One peek and one lookup for any code of eight bits or fewer, which
     * is most of the symbols decoded. This walk was 48 % of a StuffIt
     * method-3 run (`derived-EmpireBuilderDemo.sit`) doing it a bit at a
     * time. MSB mode only, and the walk below is the fallback whenever
     * the window holds fewer than eight bits, so nothing depends on the
     * peek succeeding. */
    if (h->fastok && !bi->le && unc_bitin_fill(bi, UNC_HUFF_FAST_BITS)) {
        uint32_t peek = (bi->bitbuf >> (bi->nbits - UNC_HUFF_FAST_BITS))
                        & ((1u << UNC_HUFF_FAST_BITS) - 1u);
        uint16_t e = h->fast[peek];
        if (e) {
            bi->nbits -= (int32_t)(e & 15u);
            return (int)(e >> 4);
        }
    }

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
    for (l = 1; l <= c->maxlen; l++) c->cbase[l] = idx[l];
    for (i = 0; i < nsyms; i++) {
        int len = lengths[i];
        if (len) c->sym[idx[len]++] = (int16_t)i;
    }

    /* The fast table. Codes of one length are consecutive from
     * first[l], so their UNC_CANON_FAST_BITS-bit prefixes are the
     * consecutive run [first[l] << (K-l), (first[l]+count[l]) << (K-l)),
     * which the over-subscription check above has already bounded by
     * 1 << K. */
    for (i = 0; i < (int32_t)(1u << UNC_CANON_FAST_BITS); i++)
        c->fastlen[i] = 0;
    for (l = 1; l <= c->maxlen && l <= UNC_CANON_FAST_BITS; l++) {
        uint32_t shift = (uint32_t)(UNC_CANON_FAST_BITS - l);
        uint32_t at = c->first[l] << shift;
        uint32_t n  = (uint32_t)c->count[l] << shift;
        while (n-- > 0) c->fastlen[at++] = (uint8_t)l;
    }
    return UNC_OK;
}

int unc_canon_decode(const UncCanon *c, UncBitIn *bi)
{
    uint32_t code = 0, base = 0;
    int l;

    /* One peek, one table lookup, one consume — instead of a call into
     * the bit reader and two array compares PER BIT. This function was
     * 28-32 % of a DiskDoubler or Now Compress run and 20 % of a
     * Compact Pro one, plus the bit reads inlined into it again.
     *
     * MSB mode only: StuffIt method 13 reads LSB-first and takes the
     * walk below, which is what it always did. The walk is also the
     * fallback whenever the window has fewer than eight bits left, so
     * nothing here depends on the fill succeeding. */
    if (!bi->le && unc_bitin_fill(bi, UNC_CANON_FAST_BITS)) {
        uint32_t peek = (bi->bitbuf >> (bi->nbits - UNC_CANON_FAST_BITS))
                        & ((1u << UNC_CANON_FAST_BITS) - 1u);
        int fl = c->fastlen[peek];
        if (fl) {
            bi->nbits -= fl;
            return c->sym[c->cbase[fl]
                          + ((peek >> (UNC_CANON_FAST_BITS - fl))
                             - c->first[fl])];
        }
    }

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

/*
 * unc_huffman.c — MSB-first bit reader, bit-serialized Huffman trees,
 * and canonical (code-length) Huffman codes.
 *
 * Two unrelated things share this file because they share the bit
 * reader, and they have different sources.
 *
 * The bit-serialized TREE owes neither, since 2026-09-20. Source:
 * docs/formats/serialized-huffman-tree.md — this project's own
 * description of the serialisation, derived from the output of the
 * three formats that write it (StuffIt method 3, DiskDoubler method 4,
 * PackIt) and from nothing else: a grid of plausible serialisations
 * tried at every offset of a real archive, keeping the one whose
 * decode reproduces an independent oracle's sha256 for a whole fork.
 * Thirteen forks, re-runnable with tools/derive_huffman_tree.py.
 * XADStuffItHuffmanHandle.m and macutils' de_huffman.c were the source
 * of these FACTS until that note existed; what they are not a source
 * of is the code below, which the engine's own rules shape — no
 * recursion, so an explicit stack, and a lookup table the formats know
 * nothing about (NOTICE).
 *
 * The CANONICAL codes owe neither, since 2026-09-19. Sources:
 *   reference/notes/rfc1951.txt section 3.2.2 — the definition: codes
 *     of one length are consecutive in symbol order, shorter codes come
 *     first, and the shortest is all zeros, so the code lengths alone
 *     determine every code;
 *   reference/notes/puff.c (Mark Adler, zlib licence) — construct() and
 *     decode(), the counts-and-offsets build and the walk that carries
 *     `first` and `index` along with the code.
 *
 * The canonical DECODER is unc_canon_dec.c's since 2026-11-10, so that
 * each image calling it carries a copy; the build stays here.
 *
 * SPDX-License-Identifier: 0BSD
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

UNC_HOT int unc_huff_decode(const UncHuff *h, UncBitIn *bi)
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
/*                                                                    */
/* RFC 1951 section 3.2.2 defines them and gives the assignment: count */
/* the codes of each length, take the first code of each length as     */
/* (previous first + previous count) << 1 starting from zero, and hand */
/* them out in symbol order within a length. puff.c's construct() is   */
/* the same thing with the symbol table sorted by (length, symbol) and */
/* an over-subscription check carried as the code space left, and its  */
/* decode() is the walk at the bottom of this file. See the file head. */
/*                                                                    */
/* An INCOMPLETE set — code space left over — is legal here and is not */
/* rejected: puff.c returns it as a positive result rather than an     */
/* error, and Compact Pro relies on it, writing trailing codes it      */
/* never uses. What is left over simply decodes as invalid.            */
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
    uint32_t code, left;
    uint16_t offs[UNC_CANON_MAX_BITS + 1];

    if (nsyms > symcap) return UNC_ERR_CORRUPT;
    c->sym = symbuf;

    /* Count the codes of each length. A length of zero is a symbol that
     * does not appear and gets no code (RFC 1951 step 3). */
    for (l = 0; l <= UNC_CANON_MAX_BITS; l++) c->count[l] = 0;
    c->maxlen = 0;
    for (i = 0; i < nsyms; i++) {
        int len = lengths[i];
        if (len == 0) continue;
        if (len > UNC_CANON_MAX_BITS) return UNC_ERR_CORRUPT;
        c->count[len]++;
        if (len > c->maxlen) c->maxlen = (int16_t)len;
    }

    /* The first code of each length, and the code space. One bit doubles
     * the codes available and the codes of this length spend that many
     * of them; spending more than there are is over-subscription and the
     * lengths cannot be a prefix code. Having some left is incomplete,
     * which is allowed — see the note above.
     *
     * puff.c carries `left` signed and tests it below zero. Here it is
     * UNSIGNED and the test is made before the subtraction, because
     * UNC_CANON_MAX_BITS is 31, not puff's 15: a stream declaring a
     * length of 31 takes `left` to 1 << 31, which is not an int32_t.
     * The rejections are the same ones. */
    code = 0;
    left = 1;
    for (l = 1; l <= c->maxlen; l++) {
        c->first[l] = code;
        code = (code + c->count[l]) << 1;
        left <<= 1;
        if (c->count[l] > left) return UNC_ERR_CORRUPT;
        left -= c->count[l];
    }

    /* Where each length's codes start in the symbol table, then the
     * symbols themselves in (length, symbol) order. cdelta keeps those
     * starts less each length's first code, which is what the decoder
     * (unc_canon_dec.c) adds a code to. */
    offs[1] = 0;
    for (l = 1; l < c->maxlen; l++)
        offs[l + 1] = (uint16_t)(offs[l] + c->count[l]);
    for (l = 1; l <= c->maxlen; l++)
        c->cdelta[l] = (uint16_t)(offs[l] - c->first[l]);
    for (i = 0; i < nsyms; i++) {
        int len = lengths[i];
        if (len) c->sym[offs[len]++] = (int16_t)i;
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

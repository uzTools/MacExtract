/*
 * unc_implode.c — zip method 6, Implode.
 *
 * Moved out of fmt_exo.c on 2026-10-17, unchanged but for its signature,
 * so that it sits beside Shrink and Reduce in the one image only zip keeps
 * (`ovl_zipold`): `ovl_exo` had reached the 32 KB a 68000's 16-bit
 * PC-relative references span (DECISIONS.md 2026-10-17, *dates in the
 * Macintosh's own zone*; FORMATS.md, *Implode*).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* ------------------------------------------------------------------ */
/* Implode — zip method 6, PKZIP 1.x                                  */
/* ------------------------------------------------------------------ */

/* A sliding dictionary whose output tokens are Shannon-Fano coded, with
 * one tree per alphabet stored byte-aligned at the head of the entry.
 * THREE parameters shape it and every one is read off the entry's own
 * general-purpose flag word rather than assumed:
 *
 *   bit 1 (0x0002)  0 = a 4 K dictionary, 1 = 8 K
 *   bit 2 (0x0004)  0 = two trees stored (length, then distance),
 *                   1 = three (a literal tree first)
 *
 * and the literal tree's PRESENCE is what sets the minimum match
 * length: 3 when it is there, 2 when it is not.
 *
 * Source: reference/notes/zip_appnote.txt 5.3.2 (the dictionary size and
 * the flag bit that states it), 5.3.3 (the tree count, its flag bit, and
 * the order the trees are stored in), 5.3.4 (the literal tree's 256
 * values and the minimum match length that follows from its presence),
 * 5.3.5 and 5.3.6 (the 64-value length and distance trees), 5.3.7 (how a
 * tree is stored), 5.3.8 (how the codes come out of the bit lengths) and
 * 5.3.9 (the token stream). reference/deark/src/fmtutil-lzh.c (MIT) is
 * the reference implementation each of those was read beside —
 * `implode_read_a_tree`, `implode_read_trees` and
 * `decompress_implode_internal`.
 *
 * A FOURTH parameter is not in the flag word and not in the stream: it
 * is the WRITER. PKZIP 1.01 and 1.02 took the minimum match length from
 * the DICTIONARY SIZE instead of from the literal tree's presence — 3
 * at 8 K and 2 at 4 K — which disagrees with 5.3.4 in exactly the two
 * combinations where the two readings differ (bit 1 set alone, and bit
 * 2 set alone). `mmlbug` selects it, and which of the two an archive
 * wants is settled by decoding one entry with no output and comparing
 * the stored CRC-32 (zip_imp_dry, src/fmt_exo.c).
 *
 * Source: reference/deark/src/fmtutil-lzh.c (MIT),
 * `fmtutil_decompress_zip_implode` — `cctx->implode_min_match_len =
 * cctx->implode_8k_buffer ? 3 : 2` under `params->mml_bug`, against
 * `cctx->implode_3_trees ? 3 : 2` without it. No specification states
 * the buggy rule: it is a reading of two programs' behaviour, and
 * PKZIP 1.01's own distribution is what grades it here (the fixture
 * `pkz101.exe`; FORMATS.md, *Implode*). */

/* The RLE nibble carries a bit length MINUS ONE, so 16 is the longest
 * code the format can state. Source: zip_appnote.txt 5.3.7. */
#define IMP_MAXBITS 16

/* 4 K or 8 K, and the low bits of a distance that are read raw: six for
 * a 4 K dictionary and seven for an 8 K one, the distance tree supplying
 * the upper six either way. Source: zip_appnote.txt 5.3.2, 5.3.6, 5.3.9. */
#define IMP_DICT_4K  4096u
#define IMP_DICT_8K  8192u

/* One decode table. `sym` is the symbol each code slot names, laid out
 * in the order 5.3.8 assigns codes — so the codes of one bit length are
 * a consecutive run, and `first`/`cbase` turn a code of that length into
 * an index. Symbols are 0..255, which is why a byte holds one. */
typedef struct ImpTree {
    uint16_t count[IMP_MAXBITS + 1];  /* codes of each bit length      */
    uint16_t first[IMP_MAXBITS + 1];  /* lowest code value of a length */
    uint16_t cbase[IMP_MAXBITS + 1];  /* where that run starts in sym  */
    uint8_t *sym;                     /* nsyms entries                 */
    uint8_t  maxlen;
} ImpTree;

/* Per-entry state. One allocation, so a refusal is one failure: the
 * window is the second and is sized to the dictionary the flags name. */
typedef struct ImpState {
    ImpTree  lit, len, dist;
    uint8_t  litsym[256], lensym[64], distsym[64];
    /* The bit lengths of the tree being built, by symbol. 256 covers the
     * literal tree and both 64-value ones. */
    uint8_t  lengths[256];
} ImpState;

/* 5.3.7: a count byte holding (number of RLE bytes - 1), then that many
 * bytes of "high nibble = number of values at this bit length - 1, low
 * nibble = bit length - 1".
 *
 * The tree data is read as whole BYTES and not through the bit reader,
 * which is what the reference does (`dbuf_getbyte_p` against
 * `bitrd.curpos`): the trees sit at the head of the entry and the token
 * stream's bit numbering starts after them.
 *
 * The count must come to EXACTLY the alphabet's size. 5.3.4/5.3.5/5.3.6
 * fix those at 256, 64 and 64, and the reference says the same in
 * prose — "the Implode specification apparently requires the trees to
 * always be fully populated". A stream that says otherwise is corrupt,
 * and this is where a bent one is turned away. */
static int imp_read_lengths(UncBufIn *in, uint8_t *lengths, uint32_t nsyms)
{
    int b = unc_bufin_next(in);
    uint32_t nrle, i, next = 0;

    if (b < 0) return in->err;
    nrle = (uint32_t)b + 1u;
    for (i = 0; i < nrle; i++) {
        uint32_t n, l, k;

        b = unc_bufin_next(in);
        if (b < 0) return in->err;
        n = ((uint32_t)b >> 4) + 1u;        /* values at this length   */
        l = ((uint32_t)b & 0x0Fu) + 1u;     /* the length itself       */
        if (next + n > nsyms) return UNC_ERR_CORRUPT;
        for (k = 0; k < n; k++) lengths[next++] = (uint8_t)l;
    }
    if (next != nsyms) return UNC_ERR_CORRUPT;
    return UNC_OK;
}

/* 5.3.8, steps 1, 2 and 4, without step 3.
 *
 * Step 3 reverses every code so that its most significant bit becomes
 * its least significant, and step 3 is NOT performed: the token stream
 * hands its bits over least-significant-first within each byte
 * (5.3.9 through `unc_bitin_init_le`), so accumulating a code
 * most-significant-bit-first out of that stream — which is what
 * `imp_decode` below does, and what the reference's bit-serial tree walk
 * does — IS the reversal. The two readings were checked against each
 * other on every tree in reach (DECISIONS.md 2026-10-07).
 *
 * Steps 1 and 2 together are: visit the symbols longest code first, and
 * within one length in DECREASING symbol order; give the first a code of
 * zero; and for each one after it take the previous code, shift it right
 * by the drop in length, and add one. That is the reference's
 * `fmtutil_huffman_make_canonical_tree2` driven over the length array
 * reversed, which is what its two flags
 * (LEFT_ALIGN_BRANCHES | LAST_CODE_FIRST) ask for.
 *
 * It is NOT this engine's canonical coder (`unc_canon_build`), whose
 * codes run the other way: shortest first, all-zeros at the shortest
 * length, ascending by symbol. */
static int imp_build(ImpTree *t, const uint8_t *lengths, uint32_t nsyms)
{
    uint32_t code = 0, prevlen = 0;
    uint32_t l, i, slot = 0;
    int first = 1;

    for (l = 0; l <= IMP_MAXBITS; l++)
        t->count[l] = t->first[l] = t->cbase[l] = 0;
    t->maxlen = 0;

    for (l = IMP_MAXBITS; l >= 1; l--) {
        uint32_t runstart = slot;
        /* Decreasing symbol order: step 1's sort is stable, so reading
         * it back from the end visits each length's symbols that way. */
        i = nsyms;
        while (i-- > 0) {
            if (lengths[i] != l) continue;
            if (first) { code = 0; first = 0; }
            else code = (code >> (prevlen - l)) + 1u;
            prevlen = l;
            if (code >= (1u << l)) return UNC_ERR_CORRUPT;
            if (t->count[l] == 0) t->first[l] = (uint16_t)code;
            t->count[l]++;
            t->sym[slot++] = (uint8_t)i;
        }
        if (t->count[l]) {
            t->cbase[l] = (uint16_t)runstart;
            if (t->maxlen == 0) t->maxlen = (uint8_t)l;
        }
    }
    /* A tree with no codes at all decodes nothing, and the alphabet
     * sizes above make it unreachable; refuse it rather than loop. */
    return t->maxlen ? UNC_OK : UNC_ERR_CORRUPT;
}

/* One code, bit-serially: take a bit, make it the next
 * least-significant bit of the code, and ask whether a code of the
 * length so far starts where this one does. The same walk
 * `unc_canon_decode` falls back to, over this format's own run table. */
static int imp_decode(const ImpTree *t, UncBitIn *bi)
{
    uint32_t code = 0;
    uint32_t l;

    for (l = 1; l <= (uint32_t)t->maxlen; l++) {
        int bit = unc_bitin_bit(bi);
        if (bit < 0) return -1;
        code = (code << 1) | (uint32_t)bit;
        if (t->count[l] && code - t->first[l] < t->count[l])
            return t->sym[t->cbase[l] + (code - t->first[l])];
    }
    return -2;                  /* no code of any length: corrupt */
}

/* Hand over what the window has taken since the last flush, and take the
 * CRC-32 of the same span. The window wraps, so a span crossing its end
 * is two writes — the shape is sit14_flush's (src/sit14.c). */
static int imp_flush(const uint8_t *win, uint32_t dict, uint32_t from,
                     uint32_t to, uint32_t *crc, UncPutRun emit, void *ectx)
{
    uint32_t n = to - from, a = from & (dict - 1u);

    if (n == 0) return UNC_OK;
    if (a + n > dict) {
        int err;
        *crc = unc_crc32(*crc, win + a, (int32_t)(dict - a));
        err = emit(ectx, win + a, dict - a);
        if (err != UNC_OK) return err;
        n -= dict - a;
        a = 0;
    }
    *crc = unc_crc32(*crc, win + a, (int32_t)n);
    return emit(ectx, win + a, n);
}

int unc_implode_decode(UncAlloc *al, UncBufIn *in, uint32_t flags,
                       uint32_t usize, uint32_t *crc, uint32_t mmlbug,
                       UncPutRun emit, void *ectx)
{
    ImpState *s;
    uint8_t *win;
    UncBitIn bi;
    uint32_t dict = (flags & 0x0002u) ? IMP_DICT_8K : IMP_DICT_4K;
    uint32_t lowbits = (flags & 0x0002u) ? 7u : 6u;
    int three = (flags & 0x0004u) != 0;
    /* 5.3.4's rule, or PKZIP 1.01/1.02's — see the fourth parameter in
     * the comment above this file's Implode section. */
    uint32_t mml = mmlbug ? (dict == IMP_DICT_8K ? 3u : 2u)
                          : (three ? 3u : 2u);
    uint32_t mask, thresh, pos = 0, flushed = 0;
    int err;

    if (usize == 0) return UNC_OK;

    s = (ImpState *)unc_alloc(al, (uint32_t)sizeof *s);
    if (!s) return UNC_ERR_MEM;
    win = (uint8_t *)unc_alloc(al, dict);
    if (!win) { unc_free(al, s); return UNC_ERR_MEM; }
    /* 5.3.9: "if this position is before the start of the output stream,
     * then assume that all the data before the start of the output
     * stream is filled with zeros" — so the dictionary starts zeroed,
     * and a match that reaches back past the first byte reads those
     * zeros. 30 of the 20,247 matches in reach do (FORMATS.md). */
    {
        uint32_t i;
        for (i = 0; i < dict; i++) win[i] = 0;
    }
    mask = dict - 1u;
    thresh = dict >> 2;

    s->lit.sym = s->litsym;
    s->len.sym = s->lensym;
    s->dist.sym = s->distsym;

    /* 5.3.3: with three trees the literal tree comes first; with two the
     * length tree does, and the distance tree is last either way. */
    if (three) {
        if ((err = imp_read_lengths(in, s->lengths, 256)) != UNC_OK) goto out;
        if ((err = imp_build(&s->lit, s->lengths, 256)) != UNC_OK) goto out;
    }
    if ((err = imp_read_lengths(in, s->lengths, 64)) != UNC_OK) goto out;
    if ((err = imp_build(&s->len, s->lengths, 64)) != UNC_OK) goto out;
    if ((err = imp_read_lengths(in, s->lengths, 64)) != UNC_OK) goto out;
    if ((err = imp_build(&s->dist, s->lengths, 64)) != UNC_OK) goto out;

    unc_bitin_init_le(&bi, in);

    while (pos < usize) {
        int bit;

        if (pos - flushed >= thresh) {
            if ((err = imp_flush(win, dict, flushed, pos, crc, emit, ectx))
                    != UNC_OK)
                goto out;
            flushed = pos;
        }

        bit = unc_bitin_bit(&bi);
        if (bit < 0) { err = bi.err; goto out; }
        if (bit) {
            /* 5.3.9: a set bit is a literal — through the literal tree
             * where there is one, eight raw bits where there is not. */
            int b;
            if (three) {
                b = imp_decode(&s->lit, &bi);
                if (b < 0) { err = b == -1 ? bi.err : UNC_ERR_CORRUPT;
                             goto out; }
            } else {
                int32_t v = unc_bitin_bits_le(&bi, 8);
                if (v < 0) { err = bi.err; goto out; }
                b = (int)v;
            }
            win[pos++ & mask] = (uint8_t)b;
        } else {
            int32_t lo;
            int hi, lc;
            uint32_t distance, mlen, from;

            lo = unc_bitin_bits_le(&bi, (int)lowbits);
            if (lo < 0) { err = bi.err; goto out; }
            hi = imp_decode(&s->dist, &bi);
            if (hi < 0) { err = hi == -1 ? bi.err : UNC_ERR_CORRUPT;
                          goto out; }
            distance = ((uint32_t)hi << lowbits) | (uint32_t)lo;

            lc = imp_decode(&s->len, &bi);
            if (lc < 0) { err = lc == -1 ? bi.err : UNC_ERR_CORRUPT;
                          goto out; }
            if (lc == 63) {
                /* 5.3.9: the top length code is an escape and eight more
                 * bits follow. 249 of the matches in reach take it. */
                int32_t v = unc_bitin_bits_le(&bi, 8);
                if (v < 0) { err = bi.err; goto out; }
                mlen = mml + 63u + (uint32_t)v;
            } else {
                mlen = mml + (uint32_t)lc;
            }

            /* "move backwards Distance+1 bytes in the output stream":
             * masked, which is the same slot for every distance the
             * dictionary can hold, and the zeros above for the rest. A
             * match may overlap its own output (347 in reach do), so it
             * is copied one byte at a time. */
            from = pos - 1u - distance;
            while (mlen-- > 0 && pos < usize) {
                win[pos & mask] = win[from++ & mask];
                pos++;
            }
            /* No flush inside that loop, and it is not an omission: the
             * test at the head of the while reserves a quarter of the
             * window, and the longest match the format can state is
             * mml + 63 + 255 = 321 bytes, so `pos - flushed` cannot pass
             * (dict/4 - 1) + 321 — 1,344 against the 4,096 of the
             * smaller dictionary. Unflushed bytes therefore cannot be
             * overwritten, and a check here could not fire. */
        }
    }

    err = imp_flush(win, dict, flushed, pos, crc, emit, ectx);
    /* No "short of `usize`" test here, and sit14's shape is the wrong
     * one to copy: this loop's only exit is `pos >= usize`, so such a
     * test could not fire. A stream that ends early is reported by the
     * bit reader instead — `unc_bufin_next` hits the substream's limit
     * and `bi.err` is UNC_ERR_TRUNCATED, which every read above
     * propagates. */

out:
    unc_free(al, win);
    unc_free(al, s);
    return err;
}


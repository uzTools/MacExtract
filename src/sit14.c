/*
 * sit14.c — StuffIt method 14: LZSS over a 256 KB window, with both of
 * its alphabets canonically Huffman-coded and a fresh pair of trees in
 * every block.
 *
 * Source: reference/XADMaster/XADStuffItOldHandles.m — SIT_14,
 * SIT14_ReadTree and SIT14_Update (libxad's decoder, reached through
 * XADStuffIt14Handle). Everything numeric below is that file's: the
 * 16-bit block count, each block's skipped 32-bit crunched size and
 * 32-bit uncrunched length read as two LSB-first halves, the 308- and
 * 75-symbol alphabets, the length base/extra ladder built from
 * `(i-4)>>2` with a +4 bias, the distance ladder from `(i-3)>>2` based
 * at 1, the `1<<j` nested code-length alphabet with its `o` bias and
 * its `m`/`k` repeat and zero escapes, the bit-reversed canonical code
 * assignment, and the byte boundary at the end of every tree and every
 * block. Bit order is libxad's `xadIOGetBitsLow`, which is LSB-first
 * within each byte — the engine's LE mode (`unc_bitin_init_le`), the
 * same one StuffIt method 13 reads in.
 *
 * WHAT THIS DOES NOT TRANSCRIBE, and why each one is not a guess:
 *
 *   - `SIT14_ReadTree` recurses to read the alphabet its code lengths
 *     are coded in, and `SIT14_Update` is a quicksort that recurses on
 *     the smaller half. Neither may here (CLAUDE.md, 68000 discipline):
 *     the sort is the same partition driven from an explicit range
 *     stack — which yields the identical permutation, because each
 *     subrange is sorted independently and the order ranges are taken
 *     in cannot change the result — and the nested tree is read by the
 *     `nest` branch below rather than by a self-call.
 *   - a nested tree that itself asks for a nested one is REFUSED. The
 *     reference passes `dat->freq` as both the nested call's result
 *     array and its own scratch, so a second level would overwrite the
 *     first level's trie while decoding through it; what libxad would
 *     produce there is not a format, it is an aliasing accident. No
 *     fork reaches it (FORMATS.md, *Method 14*).
 *   - two of libxad's tables, `var6[1024]` and `var8[0x4000]`, are
 *     built by `SIT_14` and never read by it — 17 KB of a compressor's
 *     inverse mapping left in a decoder. They are not here.
 *   - the reference's `n -= k` lets a match longer than the block's
 *     remaining length wrap `n` through zero and leans on the output
 *     limit to stop the loop. This clamps instead: identical output for
 *     any stream whose blocks sum to the fork's declared length, and in
 *     bounds for one whose do not.
 *   - `xadIOByteBoundary` clears the bit COUNT and leaves the unread
 *     bits in the buffer, so libxad's next refill ORs a fresh byte over
 *     them; that is only harmless because the encoder pads with zeros.
 *     `unc_bitin_align` discards them properly. Measured identical over
 *     every fork in FORMATS.md, *Method 14* — the padding is zero in
 *     all of them.
 *   - the window is sized to the fork rather than always 256 KB, for
 *     the reason and with the masking argument fmt_sit.c's
 *     `sit13_winsize` states.
 *
 * MEMORY PER FORK: the window — min(0x40000, the fork rounded up to a
 * power of two) — plus 4.7 KB of trees and ladders.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define SIT14_WINDOW   0x40000u      /* the format's window           */
#define SIT14_WINMIN   256u
#define SIT14_LITSYMS  308           /* 256 literals + 52 length codes */
#define SIT14_OFFSYMS  75
#define SIT14_LENCODES 52
#define SIT14_LENBIAS  4             /* the shortest match             */
/* A code the canonical assignment can represent: it reverses the code
 * into a 32-bit word, so a longer one is not a code the reference could
 * have written. It also bounds the walk down a trie. */
#define SIT14_MAXBITS  32
/* The nested alphabet is `1 << (GetBits(2)+2)`, so 4, 8, 16 or 32. */
#define SIT14_SUBMAX   32

typedef struct Sit14 {
    UncBitIn *bi;
    uint8_t  len[SIT14_LITSYMS];       /* code lengths, symbol order   */
    uint8_t  lensort[SIT14_LITSYMS];   /* the same, sorted             */
    uint16_t order[SIT14_LITSYMS];     /* which symbol each sorted slot was */
    uint32_t code[SIT14_LITSYMS];      /* the assigned code, reversed  */
    uint16_t littree[SIT14_LITSYMS * 2];
    uint16_t offtree[SIT14_OFFSYMS * 2];
    uint16_t subtree[SIT14_SUBMAX * 2];
    uint32_t lenbase[SIT14_LENCODES];
    uint8_t  lenextra[SIT14_LENCODES];
    uint32_t offbase[SIT14_OFFSYMS];
    uint8_t  offextra[SIT14_OFFSYMS];
} Sit14;

/* ------------------------------------------------------------------ */
/* The two ladders, built once per fork                               */
/* ------------------------------------------------------------------ */

static void sit14_ladders(Sit14 *s)
{
    uint32_t i, k;

    for (i = 0, k = 0; i < SIT14_LENCODES; i++) {
        s->lenextra[i] = (uint8_t)(i >= 4 ? (i - 4) >> 2 : 0);
        s->lenbase[i] = k;
        k += 1u << s->lenextra[i];
    }
    for (i = 0, k = 1; i < SIT14_OFFSYMS; i++) {
        s->offextra[i] = (uint8_t)(i >= 3 ? (i - 3) >> 2 : 0);
        s->offbase[i] = k;
        k += 1u << s->offextra[i];
    }
}

/* ------------------------------------------------------------------ */
/* Canonical codes                                                    */
/* ------------------------------------------------------------------ */

/* SIT14_Update, from an explicit stack. Sorts `lensort` ascending and
 * carries `order` along with it; equal lengths end up in whatever order
 * this exact partition leaves them, which is what decides the code
 * assignment, so the partition is transcribed and not replaced. */
static void sit14_sort(uint8_t *key, uint16_t *val, int32_t nsyms)
{
    /* Each pushed range is the smaller half, so the depth cannot pass
     * log2(nsyms); 16 covers 65,536 symbols against this file's 308. */
    int32_t stack[16][2];
    int32_t top = 0;
    int32_t first = 0, last = nsyms;

    for (;;) {
        while (last - first > 1) {
            int32_t i = first, j = last;
            do {
                while (++i < last && key[first] > key[i])
                    ;
                while (--j > first && key[first] < key[j])
                    ;
                if (j > i) {
                    uint8_t t = key[i]; key[i] = key[j]; key[j] = t;
                    { uint16_t u = val[i]; val[i] = val[j]; val[j] = u; }
                }
            } while (j > i);

            if (first != j) {
                uint8_t t = key[first]; key[first] = key[j]; key[j] = t;
                { uint16_t u = val[first]; val[first] = val[j]; val[j] = u; }

                i = j + 1;
                if (last - i <= j - first) {
                    if (top < 16) {
                        stack[top][0] = i; stack[top][1] = last; top++;
                    }
                    last = j;
                } else {
                    if (top < 16) {
                        stack[top][0] = first; stack[top][1] = j; top++;
                    }
                    first = i;
                }
            } else {
                ++first;
            }
        }
        if (top == 0) return;
        top--;
        first = stack[top][0];
        last = stack[top][1];
    }
}

/* Turn `nsyms` code lengths into the trie the decoder walks.
 *
 * `tree` holds 2*nsyms entries: an internal node is an even index whose
 * two children are at that index and the one after it, and a leaf is
 * 2*nsyms + the symbol. Node 0 is the root. */
static int sit14_build(Sit14 *s, int32_t nsyms, uint16_t *tree)
{
    int32_t i, j, leaf = nsyms * 2;
    uint32_t ctr;

    for (i = 0; i < nsyms; i++) {
        if (s->len[i] > SIT14_MAXBITS) return UNC_ERR_CORRUPT;
        s->lensort[i] = s->len[i];
        s->order[i] = (uint16_t)i;
    }
    sit14_sort(s->lensort, s->order, nsyms);

    for (i = 0; i < nsyms; i++) s->code[i] = 0;

    for (i = 0; i < nsyms && !s->lensort[i]; i++)
        ;                                    /* skip the unused symbols */
    /* The counter is UNSIGNED, as the reference's is: a corrupt tree can
     * run it past 32 bits, and a signed overflow there is undefined
     * rather than merely wrong (caught by UBSan, 2026-10-03, on mutant
     * 213 of the 400 in TESTING.md). Where it wraps, the codes collide
     * and the trie build below refuses the tree. */
    for (ctr = 0; i < nsyms; i++, ctr++) {
        /* The code is the counter read backwards, so that the trie
         * below and the decoder both take its bits off the bottom in
         * stream order. */
        uint32_t l, rev = 0;
        int32_t bits = s->lensort[i];
        /* `ctr` is zero only on the first symbol with a length, where
         * the shift is a no-op — and skipping it is what keeps a jump
         * from length 0 to length 32 from shifting by the whole width. */
        if (i && ctr) ctr <<= (s->lensort[i] - s->lensort[i - 1]);
        l = ctr;
        while (bits-- > 0) { rev = (rev << 1) | (l & 1u); l >>= 1; }
        s->code[s->order[i]] = rev;
    }

    for (i = 0; i < leaf; i++) tree[i] = 0;

    j = 2;
    for (i = 0; i < nsyms; i++) {
        int32_t at = 0, bit;
        uint32_t m = s->code[i];
        for (bit = 0; bit < s->len[i]; bit++) {
            at += (int32_t)(m & 1u);
            if (at >= leaf) return UNC_ERR_CORRUPT;
            if (s->len[i] - 1 <= bit) {
                tree[at] = (uint16_t)(leaf + i);
            } else {
                if (!tree[at]) {
                    if (j + 1 >= leaf) return UNC_ERR_CORRUPT;
                    tree[at] = (uint16_t)j;
                    j += 2;
                }
                at = tree[at];
                if (at >= leaf) return UNC_ERR_CORRUPT;   /* leaf midway */
            }
            m >>= 1;
        }
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Reading one symbol, and one tree                                   */
/* ------------------------------------------------------------------ */

/* The symbol, or -1 on a read error, or -2 for a trie that never
 * reaches a leaf (which a well-formed one does within its longest
 * code). */
static int32_t sit14_sym(Sit14 *s, const uint16_t *tree, int32_t nsyms)
{
    int32_t leaf = nsyms * 2;
    int32_t at = 0, steps;

    for (steps = 0; steps <= SIT14_MAXBITS; steps++) {
        int bit = unc_bitin_bit(s->bi);
        if (bit < 0) return -1;
        at = tree[at + bit];
        if (at >= leaf) return at - leaf;
    }
    return -2;
}

/* The header every tree carries, and the two escapes its code lengths
 * are written with: `zero` ends a symbol at length 0, `rep` repeats the
 * previous length. */
typedef struct Sit14Head {
    int32_t width;    /* j: bits per raw length, and 1<<j the alphabet  */
    int32_t bias;     /* o: added to every raw length                   */
    int32_t zero;     /* k: the value that means "unused"              */
    int32_t rep;      /* m: the value that introduces a repeat         */
    int      nest;    /* whether the lengths are themselves coded      */
} Sit14Head;

static int sit14_head(Sit14 *s, Sit14Head *h)
{
    int32_t flag = unc_bitin_bits_le(s->bi, 1);
    int32_t width = unc_bitin_bits_le(s->bi, 2);
    int32_t bias = unc_bitin_bits_le(s->bi, 3);
    int32_t nest = unc_bitin_bits_le(s->bi, 2);   /* one bit is skipped */

    if (flag < 0 || width < 0 || bias < 0 || nest < 0) return s->bi->err;

    h->width = width + 2;
    h->bias = bias + 1;
    h->rep = (1 << h->width) - 1;
    /* Without the flag there is no "unused" value at all: the reference
     * sets k to -1 in a 32-bit unsigned, which no length can equal. */
    h->zero = flag ? h->rep - 1 : -1;
    h->nest = nest & 1;
    return UNC_OK;
}

/* Read `nsyms` code lengths into s->len, the raw way: each one a
 * `width`-bit field. */
static int sit14_lengths_raw(Sit14 *s, const Sit14Head *h, int32_t nsyms)
{
    int32_t i = 0;

    while (i < nsyms) {
        int32_t v = unc_bitin_bits_le(s->bi, h->width);
        if (v < 0) return s->bi->err;
        if (v == h->zero) {
            s->len[i++] = 0;
        } else if (v == h->rep) {
            int32_t rep = unc_bitin_bits_le(s->bi, h->width);
            if (rep < 0) return s->bi->err;
            rep += 3;
            if (i == 0) return UNC_ERR_CORRUPT;   /* nothing to repeat */
            while (rep-- > 0) {
                if (i >= nsyms) return UNC_ERR_CORRUPT;
                s->len[i] = s->len[i - 1];
                i++;
            }
        } else {
            s->len[i++] = (uint8_t)(v + h->bias);
        }
    }
    return UNC_OK;
}

/* The same, with every length taken through the nested tree instead. */
static int sit14_lengths_coded(Sit14 *s, const Sit14Head *h, int32_t nsyms,
                               int32_t subsyms)
{
    int32_t i = 0;

    while (i < nsyms) {
        int32_t v = sit14_sym(s, s->subtree, subsyms);
        if (v < 0) return v == -1 ? s->bi->err : UNC_ERR_CORRUPT;
        if (v == h->zero) {
            s->len[i++] = 0;
        } else if (v == h->rep) {
            int32_t rep = sit14_sym(s, s->subtree, subsyms);
            if (rep < 0) return rep == -1 ? s->bi->err : UNC_ERR_CORRUPT;
            rep += 3;
            if (i == 0) return UNC_ERR_CORRUPT;
            while (rep-- > 0) {
                if (i >= nsyms) return UNC_ERR_CORRUPT;
                s->len[i] = s->len[i - 1];
                i++;
            }
        } else {
            s->len[i++] = (uint8_t)(v + h->bias);
        }
    }
    return UNC_OK;
}

/* One of a block's two trees. */
static int sit14_tree(Sit14 *s, int32_t nsyms, uint16_t *tree)
{
    Sit14Head h;
    int err = sit14_head(s, &h);
    if (err != UNC_OK) return err;

    if (h.nest) {
        Sit14Head sub;
        /* The nested tree's alphabet is the OUTER header's raw-value
         * alphabet — the reference calls itself with `size`, its own
         * `1<<j`, and the sub-header's width only says how wide the
         * fields that spell out ITS lengths are. */
        int32_t subsyms = 1 << h.width;
        if ((err = sit14_head(s, &sub)) != UNC_OK) return err;
        /* See the file header: libxad's second level aliases the first
         * level's trie, so there is nothing here to transcribe. */
        if (sub.nest) return UNC_ERR_UNSUPPORTED;
        if ((err = sit14_lengths_raw(s, &sub, subsyms)) != UNC_OK)
            return err;
        if ((err = sit14_build(s, subsyms, s->subtree)) != UNC_OK)
            return err;
        unc_bitin_align(s->bi);        /* the nested read ends on one   */
        err = sit14_lengths_coded(s, &h, nsyms, subsyms);
    } else {
        err = sit14_lengths_raw(s, &h, nsyms);
    }
    if (err != UNC_OK) return err;

    err = sit14_build(s, nsyms, tree);
    unc_bitin_align(s->bi);
    return err;
}

/* ------------------------------------------------------------------ */
/* The fork                                                           */
/* ------------------------------------------------------------------ */

static uint32_t sit14_winsize(uint32_t outlen)
{
    uint32_t w = SIT14_WINMIN;
    while (w < outlen && w < SIT14_WINDOW) w <<= 1;
    return w;
}

/* Hand over what the window has taken since the last flush — the shape
 * and the reasoning are fmt_sit.c's sit13_flush. */
static int sit14_flush(UncForkOut *f, const uint8_t *window, uint32_t win,
                       uint32_t from, uint32_t to)
{
    uint32_t n = to - from, a = from & (win - 1);
    if (n == 0) return UNC_OK;
    if (a + n > win) {
        int err = unc_fork_write(f, window + a, win - a);
        if (err != UNC_OK) return err;
        n -= win - a;
        a = 0;
    }
    return unc_fork_write(f, window + a, n);
}

int unc_sit14_decode(UncBufIn *in, UncAlloc *al, uint32_t outlen,
                     UncForkOut *f)
{
    Sit14 *s;
    uint8_t *window;
    UncBitIn bi;
    uint32_t win = sit14_winsize(outlen), mask, thresh;
    uint32_t pos = 0, flushed = 0;
    int32_t blocks;
    int err = UNC_OK;

    if (outlen == 0) return UNC_OK;

    s = (Sit14 *)unc_alloc(al, (uint32_t)sizeof *s);
    if (!s) return UNC_ERR_MEM;
    window = (uint8_t *)unc_alloc(al, win);
    if (!window) { unc_free(al, s); return UNC_ERR_MEM; }
    {
        uint32_t i;
        for (i = 0; i < win; i++) window[i] = 0;
    }
    mask = win - 1;
    thresh = win >> 2;

    unc_bitin_init_le(&bi, in);
    s->bi = &bi;
    sit14_ladders(s);

    blocks = unc_bitin_bits_le(&bi, 16);
    if (blocks < 0) { err = bi.err; goto out; }

    while (blocks-- > 0 && pos < outlen) {
        int32_t lo, hi;
        uint32_t left;

        /* The crunched size of the block, which nothing needs: the
         * trees say where the symbols end and `left` says when the
         * block does. */
        if (unc_bitin_bits_le(&bi, 16) < 0 ||
            unc_bitin_bits_le(&bi, 16) < 0) { err = bi.err; goto out; }
        lo = unc_bitin_bits_le(&bi, 16);
        hi = unc_bitin_bits_le(&bi, 16);
        if (lo < 0 || hi < 0) { err = bi.err; goto out; }
        left = (uint32_t)lo | ((uint32_t)hi << 16);

        if ((err = sit14_tree(s, SIT14_LITSYMS, s->littree)) != UNC_OK)
            goto out;
        if ((err = sit14_tree(s, SIT14_OFFSYMS, s->offtree)) != UNC_OK)
            goto out;

        while (left > 0 && pos < outlen) {
            int32_t sym;

            if (pos - flushed >= thresh) {
                if ((err = sit14_flush(f, window, win, flushed, pos)) != UNC_OK)
                    goto out;
                flushed = pos;
            }

            sym = sit14_sym(s, s->littree, SIT14_LITSYMS);
            if (sym < 0) {
                err = sym == -1 ? bi.err : UNC_ERR_CORRUPT;
                goto out;
            }
            if (sym < 0x100) {
                window[pos++ & mask] = (uint8_t)sym;
                left--;
            } else {
                int32_t li = sym - 0x100, oi;
                uint32_t mlen, dist, from;

                if (li >= SIT14_LENCODES) { err = UNC_ERR_CORRUPT; goto out; }
                mlen = s->lenbase[li] + SIT14_LENBIAS;
                if (s->lenextra[li]) {
                    int32_t v = unc_bitin_bits_le(&bi, s->lenextra[li]);
                    if (v < 0) { err = bi.err; goto out; }
                    mlen += (uint32_t)v;
                }

                oi = sit14_sym(s, s->offtree, SIT14_OFFSYMS);
                if (oi < 0) {
                    err = oi == -1 ? bi.err : UNC_ERR_CORRUPT;
                    goto out;
                }
                dist = s->offbase[oi];
                if (s->offextra[oi]) {
                    int32_t v = unc_bitin_bits_le(&bi, s->offextra[oi]);
                    if (v < 0) { err = bi.err; goto out; }
                    dist += (uint32_t)v;
                }

                /* The reference's `j + 0x40000 - l`, masked: the same
                 * slot for every distance a valid stream can code. */
                from = pos - dist;
                left = mlen >= left ? 0 : left - mlen;
                while (mlen-- > 0 && pos < outlen)
                    window[pos++ & mask] = window[from++ & mask];
            }
        }
        unc_bitin_align(&bi);
    }

    if ((err = sit14_flush(f, window, win, flushed, pos)) != UNC_OK) goto out;
    /* Short of the declared length the fork is not there, whatever the
     * block count said. */
    if (pos < outlen) err = UNC_ERR_TRUNCATED;

out:
    unc_free(al, window);
    unc_free(al, s);
    return err;
}

/*
 * unc_lzdyn.c — LHarc's two old coders, -lh2- and -lh3-.
 *
 * -lh2-: an 8 KB-window LZSS in which BOTH
 * codes are adaptive. The literal/length code is the dynamic Huffman
 * tree -lh1- also uses; the position code is a second dynamic tree that
 * GROWS as output is produced — a new leaf every 64 bytes, so an offset
 * can only be expressed once the output is long enough to hold it.
 *
 * Source: reference/XADMaster/XADLZHOldHandles.m — `LHAdecode_start_dyn`,
 * `LHAdecode_c_dyn`, `LHAdecode_p_dyn` and the tree machinery they share
 * (`LHAreconst`, `LHAswap_inc`, `LHAupdate_c`, `LHAupdate_p`,
 * `LHAmake_new_node`), with the main loop from `LhA_Decrunch`. LGPL, see
 * NOTICE. Cross-read against LHa for UNIX's own `dhuf.c`, which is the
 * original this descends from.
 *
 * The two trees are one array pair: symbols live at ROOT_C..TREESIZE_C-1
 * and positions from ROOT_P up, which is why `reconst` and `swap_inc`
 * take a range rather than a tree.
 *
 * Nothing in the corpus uses -lh2- and no reachable tool writes one, so
 * this is graded against LHa for UNIX itself: tools/run_lzh.py builds
 * archives with a locally patched copy of that program (which can encode
 * -lh2- where the stock one cannot) and requires this decoder and LHa's
 * to return the same bytes. TESTING.md, "LZH's old methods".
 *
 * -lh3- is the other half of this file and shares only the outer loop:
 * a STATIC code, rebuilt per block, where -lh2- adapts continuously. Its
 * block head is a 16-bit symbol count, then a literal/length tree sent as
 * one 4-bit length per symbol, then either a position tree in the same
 * shape or a fixed one the format keeps for the purpose. Source: the same
 * XADMaster file (`LHAdecode_start_st0`, `_c_st0`, `_p_st0`,
 * `LHAread_tree_c`, `LHAread_tree_p`, `LHAready_made`), cross-read against
 * LHa's `shuf.c`.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define LZD_THRESHOLD  3
#define LZD_N_CHAR     (256 + 60 - LZD_THRESHOLD + 1)   /* 314 */
#define LZD_TREESIZE_C (LZD_N_CHAR * 2)                 /* 628 */
#define LZD_TREESIZE_P (128 * 2)                        /* 256 */
#define LZD_TREESIZE   (LZD_TREESIZE_C + LZD_TREESIZE_P)
#define LZD_ROOT_C     0
#define LZD_ROOT_P     LZD_TREESIZE_C
#define LZD_NMAX       286              /* -lh2-'s alphabet             */
#define LZD_DICBIT     13
#define LZD_DICSIZ     (1u << LZD_DICBIT)
#define LZD_MAXMATCH   256

typedef struct Lzdyn {
    uint16_t freq[LZD_TREESIZE];
    int16_t  child[LZD_TREESIZE];
    int16_t  stock[LZD_TREESIZE];
    int16_t  block[LZD_TREESIZE];
    int16_t  parent[LZD_TREESIZE];
    int16_t  edge[LZD_TREESIZE];
    int16_t  s_node[LZD_TREESIZE / 2];
    int32_t  avail, most_p, n1, nn;
    uint16_t total_p;
    uint32_t count, nextcount;
    uint8_t  window[LZD_DICSIZ];
} Lzdyn;

/* Rebuild a range of the tree, halving every frequency. @LHAreconst. */
static void lzd_reconst(Lzdyn *h, int32_t start, int32_t end)
{
    int32_t i, j, k, l, b = 0;
    uint32_t f, g;

    for (i = j = start; i < end; i++) {
        if ((k = h->child[i]) < 0) {
            h->freq[j] = (uint16_t)((h->freq[i] + 1) / 2);
            h->child[j] = (int16_t)k;
            j++;
        }
        if (h->edge[b = h->block[i]] == i) h->stock[--h->avail] = (int16_t)b;
    }
    j--;
    i = end - 1;
    l = end - 2;
    while (i >= start) {
        while (i >= l) {
            h->freq[i] = h->freq[j];
            h->child[i] = h->child[j];
            i--; j--;
        }
        f = (uint32_t)h->freq[l] + h->freq[l + 1];
        for (k = start; f < h->freq[k]; k++)
            ;
        while (j >= k) {
            h->freq[i] = h->freq[j];
            h->child[i] = h->child[j];
            i--; j--;
        }
        h->freq[i] = (uint16_t)f;
        h->child[i] = (int16_t)(l + 1);
        i--;
        l -= 2;
    }
    f = 0;
    for (i = start; i < end; i++) {
        if ((j = h->child[i]) < 0) h->s_node[~j] = (int16_t)i;
        else h->parent[j] = h->parent[j - 1] = (int16_t)i;
        if ((g = h->freq[i]) == f) {
            h->block[i] = (int16_t)b;
        } else {
            h->edge[b = h->block[i] = h->stock[h->avail++]] = (int16_t)i;
            f = g;
        }
    }
}

/* Increment a node's frequency, keeping the ordering. @LHAswap_inc. */
static int32_t lzd_swap_inc(Lzdyn *h, int32_t p)
{
    int32_t b, q, r, s;

    b = h->block[p];
    if ((q = h->edge[b]) != p) {                  /* swap for leader */
        r = h->child[p];
        s = h->child[q];
        h->child[p] = (int16_t)s;
        h->child[q] = (int16_t)r;
        if (r >= 0) h->parent[r] = h->parent[r - 1] = (int16_t)q;
        else        h->s_node[~r] = (int16_t)q;
        if (s >= 0) h->parent[s] = h->parent[s - 1] = (int16_t)p;
        else        h->s_node[~s] = (int16_t)p;
        p = q;
        h->edge[b]++;
        if (++h->freq[p] == h->freq[p - 1]) h->block[p] = h->block[p - 1];
        else h->edge[h->block[p] = h->stock[h->avail++]] = (int16_t)p;
    } else if (b == h->block[p + 1]) {
        h->edge[b]++;
        if (++h->freq[p] == h->freq[p - 1]) h->block[p] = h->block[p - 1];
        else h->edge[h->block[p] = h->stock[h->avail++]] = (int16_t)p;
    } else if (++h->freq[p] == h->freq[p - 1]) {
        h->stock[--h->avail] = (int16_t)b;        /* delete block */
        h->block[p] = h->block[p - 1];
    }
    return h->parent[p];
}

static void lzd_update_p(Lzdyn *h, int32_t p)
{
    int32_t q;

    if (h->total_p == 0x8000) {
        lzd_reconst(h, LZD_ROOT_P, h->most_p + 1);
        h->total_p = h->freq[LZD_ROOT_P];
        h->freq[LZD_ROOT_P] = 0xffff;
    }
    q = h->s_node[p + LZD_N_CHAR];
    while (q != LZD_ROOT_P) q = lzd_swap_inc(h, q);
    h->total_p++;
}

/* One more position symbol becomes expressible. @LHAmake_new_node. */
static void lzd_make_new_node(Lzdyn *h, int32_t p)
{
    int32_t q, r;

    r = h->most_p + 1;
    q = r + 1;
    h->s_node[~(h->child[r] = h->child[h->most_p])] = (int16_t)r;
    h->child[q] = (int16_t)(~(p + LZD_N_CHAR));
    h->child[h->most_p] = (int16_t)q;
    h->freq[r] = h->freq[h->most_p];
    h->freq[q] = 0;
    h->block[r] = h->block[h->most_p];
    if (h->most_p == LZD_ROOT_P) {
        h->freq[LZD_ROOT_P] = 0xffff;
        h->edge[h->block[LZD_ROOT_P]]++;
    }
    h->parent[r] = h->parent[q] = (int16_t)h->most_p;
    h->edge[h->block[q] = h->stock[h->avail++]] =
        h->s_node[p + LZD_N_CHAR] = (int16_t)(h->most_p = q);
    lzd_update_p(h, p);
}

static void lzd_update_c(Lzdyn *h, int32_t p)
{
    int32_t q;

    if (h->freq[LZD_ROOT_C] == 0x8000)
        lzd_reconst(h, 0, LZD_NMAX * 2 - 1);
    h->freq[LZD_ROOT_C]++;
    q = h->s_node[p];
    do { q = lzd_swap_inc(h, q); } while (q != LZD_ROOT_C);
}

static void lzd_start(Lzdyn *h)
{
    int32_t i, j;
    uint32_t f;

    /* start_c_dyn */
    h->n1 = (LZD_NMAX >= 256 + LZD_MAXMATCH - LZD_THRESHOLD + 1)
                ? 512 : LZD_NMAX - 1;
    for (i = 0; i < LZD_TREESIZE_C; i++) { h->stock[i] = (int16_t)i; h->block[i] = 0; }
    for (i = 0, j = LZD_NMAX * 2 - 2; i < LZD_NMAX; i++, j--) {
        h->freq[j] = 1;
        h->child[j] = (int16_t)~i;
        h->s_node[i] = (int16_t)j;
        h->block[j] = 1;
    }
    h->avail = 2;
    h->edge[1] = (int16_t)(LZD_NMAX - 1);
    i = LZD_NMAX * 2 - 2;
    while (j >= 0) {
        f = h->freq[j] = (uint16_t)(h->freq[i] + h->freq[i - 1]);
        h->child[j] = (int16_t)i;
        h->parent[i] = h->parent[i - 1] = (int16_t)j;
        if (f == h->freq[j + 1]) h->edge[h->block[j] = h->block[j + 1]] = (int16_t)j;
        else h->edge[h->block[j] = h->stock[h->avail++]] = (int16_t)j;
        i -= 2;
        j--;
    }

    /* start_p_dyn */
    h->freq[LZD_ROOT_P] = 1;
    h->child[LZD_ROOT_P] = (int16_t)~LZD_N_CHAR;
    h->s_node[LZD_N_CHAR] = LZD_ROOT_P;
    h->edge[h->block[LZD_ROOT_P] = h->stock[h->avail++]] = LZD_ROOT_P;
    h->most_p = LZD_ROOT_P;
    h->total_p = 0;
    h->nn = 1 << LZD_DICBIT;
    h->nextcount = 64;
    h->count = 0;
}

/* Output leaves through the window, a run at a time, for both coders
 * in this file: `done` counts every byte written and `loc` is that
 * count masked, so [flushed, done) is what has not been handed over
 * yet. Flushing every LZD_FLUSH bytes keeps that span, plus the longest
 * match that can land on top of it (LZD_MAXMATCH), inside the 8 KB
 * window. Same arrangement, and the same one-call-site shape, as
 * unc_lzah.c. */
#define LZD_FLUSH 4096u

static int lzd_flush(const uint8_t *window, uint32_t *flushed, uint32_t done,
                     UncPutRun put, void *pctx)
{
    while (*flushed < done) {
        uint32_t at = *flushed & (LZD_DICSIZ - 1);
        uint32_t n = done - *flushed;
        int err;
        if (n > LZD_DICSIZ - at) n = LZD_DICSIZ - at;
        *flushed += n;
        err = put(pctx, window + at, n);
        if (err != UNC_OK) return err;
    }
    return UNC_OK;
}

static int lzd_walk(Lzdyn *h, UncBitIn *bi, int32_t root, int32_t *out)
{
    int32_t c = h->child[root];
    int steps = 0;

    while (c > 0) {
        int bit = unc_bitin_bit(bi);
        if (bit < 0) return bi->err;
        c = h->child[c - bit];
        if (++steps > LZD_TREESIZE) return UNC_ERR_CORRUPT;
    }
    *out = ~c;
    return UNC_OK;
}

static int lzd_decode_c(Lzdyn *h, UncBitIn *bi, int32_t *out)
{
    int32_t c = 0;
    int e = lzd_walk(h, bi, LZD_ROOT_C, &c);
    if (e != UNC_OK) return e;
    if (c < 0 || c >= LZD_TREESIZE) return UNC_ERR_CORRUPT;
    lzd_update_c(h, c);
    if (c == h->n1) {
        int32_t extra = unc_bitin_bits(bi, 8);
        if (extra < 0) return bi->err;
        c += extra;
    }
    *out = c;
    return UNC_OK;
}

static int lzd_decode_p(Lzdyn *h, UncBitIn *bi, int32_t *out)
{
    int32_t c = 0, low;
    int e;

    /* The tree grows on the OUTPUT's schedule, not the input's. */
    while (h->count > h->nextcount) {
        lzd_make_new_node(h, (int32_t)(h->nextcount / 64));
        if ((h->nextcount += 64) >= (uint32_t)h->nn) h->nextcount = 0xffffffffu;
    }
    if ((e = lzd_walk(h, bi, LZD_ROOT_P, &c)) != UNC_OK) return e;
    c -= LZD_N_CHAR;
    if (c < 0 || c >= LZD_TREESIZE / 2) return UNC_ERR_CORRUPT;
    lzd_update_p(h, c);
    low = unc_bitin_bits(bi, 6);
    if (low < 0) return bi->err;
    *out = (c << 6) + low;
    return UNC_OK;
}

int unc_lzdyn_decode(UncAlloc *al, UncBitIn *bi, uint32_t outlen,
                     UncPutRun put, void *pctx)
{
    Lzdyn *h;
    uint32_t loc = 0, done = 0, flushed = 0;
    int err = UNC_OK;

    h = (Lzdyn *)unc_alloc(al, (uint32_t)sizeof *h);
    if (!h) return UNC_ERR_MEM;
    {   /* no libc in the engine: clear by hand, as unc_lzah.c does */
        uint32_t i;
        for (i = 0; i < LZD_TREESIZE; i++) {
            h->freq[i] = 0;
            h->child[i] = h->stock[i] = h->block[i] = 0;
            h->parent[i] = h->edge[i] = 0;
        }
        for (i = 0; i < LZD_TREESIZE / 2; i++) h->s_node[i] = 0;
        /* The window starts full of spaces, as every reference does, so
         * that a match reaching back past the start of the output finds
         * something defined. **Unexercised**: zero-filling it instead
         * changes nothing that `tools/run_lzh.py` can see, because LHa's
         * encoder never emits such a match — its match search only knows
         * positions it has actually inserted. Kept because it is what
         * the reference does, not because a test would catch its loss. */
        for (i = 0; i < LZD_DICSIZ; i++) h->window[i] = ' ';
    }
    h->avail = h->most_p = h->n1 = h->nn = 0;
    h->total_p = 0;
    lzd_start(h);

    for (;;) {
        int32_t c = 0;
        if (done >= outlen || done - flushed >= LZD_FLUSH) {
            err = lzd_flush(h->window, &flushed, done, put, pctx);
            if (err != UNC_OK || done >= outlen) goto out;
        }
        if ((err = lzd_decode_c(h, bi, &c)) != UNC_OK) goto out;
        if (c <= 255) {
            h->window[loc++ & (LZD_DICSIZ - 1)] = (uint8_t)c;
            loc &= LZD_DICSIZ - 1;
            h->count++;
            done++;
        } else {
            int32_t len = c - (0x100 - LZD_THRESHOLD);
            int32_t pos = 0;
            uint32_t from;
            if (len <= 0) { err = UNC_ERR_CORRUPT; goto out; }
            if ((err = lzd_decode_p(h, bi, &pos)) != UNC_OK) goto out;
            from = (loc - (uint32_t)pos - 1) & (LZD_DICSIZ - 1);
            h->count += (uint32_t)len;
            while (len-- > 0 && done < outlen) {
                uint8_t b = h->window[from++ & (LZD_DICSIZ - 1)];
                h->window[loc++ & (LZD_DICSIZ - 1)] = b;
                loc &= LZD_DICSIZ - 1;
                done++;
            }
        }
    }

out:
    unc_free(al, h);
    return err;
}

/* ------------------------------------------------------------------ */
/* -lh3-: a static code, rebuilt per block                            */
/* ------------------------------------------------------------------ */

#define LZS_N1        286      /* the literal/length alphabet          */
#define LZS_NP        128      /* 8 KB window / 64                     */
#define LZS_CBIT      9        /* the "one symbol only" escape's width */
#define LZS_LENFIELD  4        /* a code length, as sent               */
#define LZS_EXTRABITS 8        /* the long-match escape                */
#define LZS_BUFBITS   16       /* the block's symbol count             */

typedef struct Lzst0 {
    uint8_t  c_len[LZS_N1];
    uint8_t  pt_len[LZS_NP];
    UncCanon c_canon, p_canon;
    int32_t  c_single, p_single;   /* -1, or the block's ONLY symbol */
    int32_t  blocksize;            /* symbols left in this block     */
    uint8_t  window[LZD_DICSIZ];
} Lzst0;

/* The position code the format keeps for blocks that send none.
 * @LHAready_made, table 1 ("8K buf"). */
static void lzs_ready_made(Lzst0 *h)
{
    static const int tbl[] = { 0x01, 0x01, 0x03, 0x06, 0x0D, 0x1F, 0x4E, -1 };
    int32_t i, j = 2, k = 0;

    for (i = 0; i < LZS_NP; i++) {
        while (tbl[k] >= 0 && tbl[k] == i) { j++; k++; }
        h->pt_len[i] = (uint8_t)j;
    }
}

/* One 4-bit length per symbol, with a bit ahead of each saying whether
 * the symbol occurs at all. Three lengths of 1 in a row is not a code:
 * it means the block holds ONE symbol, named next. @LHAread_tree_c. */
static int lzs_read_tree_c(Lzst0 *h, UncBitIn *bi)
{
    int32_t i = 0, v;

    h->c_single = -1;
    while (i < LZS_N1) {
        int bit = unc_bitin_bit(bi);
        if (bit < 0) return bi->err;
        if (bit) {
            v = unc_bitin_bits(bi, LZS_LENFIELD);
            if (v < 0) return bi->err;
            h->c_len[i] = (uint8_t)(v + 1);
        } else {
            h->c_len[i] = 0;
        }
        if (++i == 3 && h->c_len[0] == 1 && h->c_len[1] == 1
                     && h->c_len[2] == 1) {
            v = unc_bitin_bits(bi, LZS_CBIT);
            if (v < 0) return bi->err;
            h->c_single = v;
            return UNC_OK;
        }
    }
    return unc_canon_build(&h->c_canon, h->c_len, LZS_N1);
}

/* The same shape for positions, minus the presence bit and the +1.
 * @LHAread_tree_p. */
static int lzs_read_tree_p(Lzst0 *h, UncBitIn *bi)
{
    int32_t i = 0, v;

    h->p_single = -1;
    while (i < LZS_NP) {
        v = unc_bitin_bits(bi, LZS_LENFIELD);
        if (v < 0) return bi->err;
        h->pt_len[i] = (uint8_t)v;
        if (++i == 3 && h->pt_len[0] == 1 && h->pt_len[1] == 1
                     && h->pt_len[2] == 1) {
            v = unc_bitin_bits(bi, LZD_DICBIT - 6);
            if (v < 0) return bi->err;
            h->p_single = v;
            return UNC_OK;
        }
    }
    return UNC_OK;
}

static int lzs_block_head(Lzst0 *h, UncBitIn *bi)
{
    int32_t n = unc_bitin_bits(bi, LZS_BUFBITS);
    int bit, e;

    if (n < 0) return bi->err;
    h->blocksize = n;
    if ((e = lzs_read_tree_c(h, bi)) != UNC_OK) return e;
    if ((bit = unc_bitin_bit(bi)) < 0) return bi->err;
    if (bit) {
        if ((e = lzs_read_tree_p(h, bi)) != UNC_OK) return e;
    } else {
        h->p_single = -1;
        lzs_ready_made(h);
    }
    if (h->p_single < 0)
        return unc_canon_build(&h->p_canon, h->pt_len, LZS_NP);
    return UNC_OK;
}

static int lzs_decode_c(Lzst0 *h, UncBitIn *bi, int32_t *out)
{
    int32_t j;
    int e;

    if (h->blocksize == 0) {
        if ((e = lzs_block_head(h, bi)) != UNC_OK) return e;
        /* A block of zero symbols would spin forever rather than end. */
        if (h->blocksize == 0) return UNC_ERR_CORRUPT;
    }
    h->blocksize--;
    if (h->c_single >= 0) {
        j = h->c_single;               /* no bits: the block is one symbol */
    } else {
        j = unc_canon_decode(&h->c_canon, bi);
        if (j < 0) return bi->err != UNC_OK ? bi->err : UNC_ERR_CORRUPT;
    }
    if (j == LZS_N1 - 1) {
        int32_t extra = unc_bitin_bits(bi, LZS_EXTRABITS);
        if (extra < 0) return bi->err;
        j += extra;
    }
    *out = j;
    return UNC_OK;
}

static int lzs_decode_p(Lzst0 *h, UncBitIn *bi, int32_t *out)
{
    int32_t j, low;

    if (h->p_single >= 0) {
        j = h->p_single;
    } else {
        j = unc_canon_decode(&h->p_canon, bi);
        if (j < 0) return bi->err != UNC_OK ? bi->err : UNC_ERR_CORRUPT;
    }
    low = unc_bitin_bits(bi, 6);
    if (low < 0) return bi->err;
    *out = (j << 6) + low;
    return UNC_OK;
}

int unc_lzst0_decode(UncAlloc *al, UncBitIn *bi, uint32_t outlen,
                     UncPutRun put, void *pctx)
{
    Lzst0 *h;
    uint32_t loc = 0, done = 0, flushed = 0;
    uint32_t i;
    int err = UNC_OK;

    h = (Lzst0 *)unc_alloc(al, (uint32_t)sizeof *h);
    if (!h) return UNC_ERR_MEM;
    for (i = 0; i < LZS_N1; i++) h->c_len[i] = 0;
    for (i = 0; i < LZS_NP; i++) h->pt_len[i] = 0;
    for (i = 0; i < LZD_DICSIZ; i++) h->window[i] = ' ';
    h->c_single = h->p_single = -1;
    h->blocksize = 0;

    for (;;) {
        int32_t c = 0;
        if (done >= outlen || done - flushed >= LZD_FLUSH) {
            err = lzd_flush(h->window, &flushed, done, put, pctx);
            if (err != UNC_OK || done >= outlen) goto out;
        }
        if ((err = lzs_decode_c(h, bi, &c)) != UNC_OK) goto out;
        if (c <= 255) {
            h->window[loc++ & (LZD_DICSIZ - 1)] = (uint8_t)c;
            loc &= LZD_DICSIZ - 1;
            done++;
        } else {
            int32_t len = c - (0x100 - LZD_THRESHOLD);
            int32_t pos = 0;
            uint32_t from;
            if (len <= 0) { err = UNC_ERR_CORRUPT; goto out; }
            if ((err = lzs_decode_p(h, bi, &pos)) != UNC_OK) goto out;
            from = (loc - (uint32_t)pos - 1) & (LZD_DICSIZ - 1);
            while (len-- > 0 && done < outlen) {
                uint8_t b = h->window[from++ & (LZD_DICSIZ - 1)];
                h->window[loc++ & (LZD_DICSIZ - 1)] = b;
                loc &= LZD_DICSIZ - 1;
                done++;
            }
        }
    }

out:
    unc_free(al, h);
    return err;
}

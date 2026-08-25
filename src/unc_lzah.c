/*
 * unc_lzah.c — LHarc's -lh1- coder: a 4 KB-window LZSS whose literals
 * and match lengths come from an ADAPTIVE Huffman tree of 314 leaves,
 * with a static 64-symbol code for the offset's high bits.
 *
 * Two formats here use it and they use the same one: StuffIt classic's
 * method 5 ("LZAH") and LZH's -lh1-. XADMaster runs a single handle for
 * both, which is why this is one file rather than two — the same
 * arrangement DiskDoubler method 8 has with Compact Pro's stages.
 *
 * Source: reference/XADMaster/XADLZHDynamicHandle.m (the handle
 * XADStuffItParser and XADLZHParser both instantiate) — LGPL, see
 * NOTICE. Cross-read against reference/lha/src/dhuf.c, LHa for UNIX
 * 1.14i, which is the original: see DECISIONS.md for the one place the
 * two readings differ (the window preload) and which the archives
 * chose.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define LZAH_LEAVES 314
#define LZAH_NODES  (2 * LZAH_LEAVES - 1)   /* 627 */
#define LZAH_WINDOW 4096

typedef struct Lzah {
    /* Node storage, index-based transcription of XADLZHDynamicNode:
     * children/parent are storage indices, -1 = none. nodes[] maps
     * frequency rank -> storage index; st_index is its inverse. */
    int16_t  st_left[LZAH_NODES], st_right[LZAH_NODES], st_parent[LZAH_NODES];
    uint16_t st_freq[LZAH_NODES], st_value[LZAH_NODES], st_index[LZAH_NODES];
    int16_t  nodes[LZAH_NODES];
    int16_t  leafs[LZAH_LEAVES];             /* reconstructTree scratch */
    UncCanon distance;
    uint8_t  window[LZAH_WINDOW];
} Lzah;

/* Distance-code lengths, XADLZHDynamicHandle.m initWithHandle. */
static const uint8_t lzah_distlengths[64] = {
    3,4,4,4,5,5,5,5,5,5,5,5,6,6,6,6,
    6,6,6,6,6,6,6,6,7,7,7,7,7,7,7,7,
    7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
    8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,
};

static void lzah_reset(Lzah *h, int mode)
{
    int32_t i;
    for (i = 0; i < LZAH_NODES; i++) {
        h->st_left[i] = h->st_right[i] = h->st_parent[i] = -1;
        h->st_freq[i] = 0;
        h->st_value[i] = 0;
        h->nodes[i] = (int16_t)i;
        h->st_index[i] = (uint16_t)i;
    }
    for (i = 0; i < LZAH_LEAVES; i++) {
        int32_t idx = LZAH_NODES - 1 - i;
        h->st_freq[idx] = 1;
        h->st_value[idx] = (uint16_t)i;
    }
    for (i = LZAH_LEAVES - 2; i >= 0; i--) {
        h->st_left[i]  = (int16_t)(2 * i + 1);
        h->st_right[i] = (int16_t)(2 * i + 2);
        h->st_parent[2 * i + 1] = (int16_t)i;
        h->st_parent[2 * i + 2] = (int16_t)i;
        h->st_freq[i] = (uint16_t)(h->st_freq[2 * i + 1] +
                                   h->st_freq[2 * i + 2]);
    }

    /* Window preload (resetLZSSHandle): zeros, then the pattern.
     * "TODO: Figure out if the initialization of the window differs
     * between LHArc and StuffIt" — we follow what the oracle runs.
     *
     * ARC's Trimmed takes the zeros and NOT the pattern: deark passes
     * history_fill_val = 0 and its ring buffer starts zeroed
     * (reference/deark/foreign/lzhuf.h, lzhuf_Decode_init). A Trimmed
     * member whose first match reaches back past the start of the data
     * is what tells the two apart, and the entry's CRC is what says
     * so. */
    for (i = 0; i < LZAH_WINDOW; i++) h->window[i] = 0;
    if (mode == UNC_LZAH_TRIMMED) return;
    for (i = 0; i < 256; i++) {
        int32_t j;
        for (j = 0; j < 13; j++) h->window[i * 13 + 18 + j] = (uint8_t)i;
    }
    for (i = 0; i < 256; i++) h->window[256 * 13 + 18 + i] = (uint8_t)i;
    for (i = 0; i < 256; i++) h->window[256 * 13 + 256 + 18 + i] = (uint8_t)(255 - i);
    for (i = 0; i < 128; i++) h->window[256 * 13 + 512 + 18 + i] = 0;
    for (i = 0; i < 128 - 18; i++) h->window[256 * 13 + 512 + 128 + 18 + i] = ' ';
}

static void lzah_rearrange(Lzah *h, int16_t p)
{
    uint16_t p_index = h->st_index[p];
    uint16_t q_index = p_index;
    while (q_index > 0 &&
           h->st_freq[h->nodes[q_index - 1]] < h->st_freq[p])
        q_index--;
    if (q_index < p_index) {
        int16_t q = h->nodes[q_index];
        int16_t new_q_parent = h->st_parent[p];
        int16_t new_p_parent = h->st_parent[q];
        int p_right, q_right;
        if (new_q_parent < 0 || new_p_parent < 0) return;  /* root: cannot happen */
        p_right = h->st_right[new_q_parent] == p;
        q_right = h->st_right[new_p_parent] == q;
        if (p_right) h->st_right[new_q_parent] = q;
        else         h->st_left[new_q_parent] = q;
        if (q_right) h->st_right[new_p_parent] = p;
        else         h->st_left[new_p_parent] = p;
        h->st_parent[p] = new_p_parent;
        h->st_parent[q] = new_q_parent;
        h->nodes[p_index] = q;
        h->st_index[q] = p_index;
        h->nodes[q_index] = p;
        h->st_index[p] = q_index;
    }
}

static void lzah_reconstruct(Lzah *h)
{
    int32_t n = 0, i;
    int32_t leaf_index, branch_index, node_index, pair_index;

    for (i = 0; i < LZAH_NODES; i++) {
        int16_t s = h->nodes[i];
        if (h->st_left[s] < 0 && h->st_right[s] < 0) {
            h->st_freq[s] = (uint16_t)((h->st_freq[s] + 1) / 2);
            h->leafs[n++] = s;
        }
    }

    leaf_index = LZAH_LEAVES - 1;
    branch_index = LZAH_LEAVES - 2;
    node_index = LZAH_NODES - 1;
    pair_index = LZAH_NODES - 2;

    while (node_index >= 0) {
        int16_t branch;
        while (node_index >= pair_index) {
            h->nodes[node_index] = h->leafs[leaf_index];
            h->st_index[h->nodes[node_index]] = (uint16_t)node_index;
            node_index--;
            leaf_index--;
        }
        branch = (int16_t)branch_index--;
        h->st_left[branch] = h->nodes[pair_index];
        h->st_right[branch] = h->nodes[pair_index + 1];
        h->st_parent[h->st_left[branch]] = branch;
        h->st_parent[h->st_right[branch]] = branch;
        h->st_freq[branch] = (uint16_t)(h->st_freq[h->st_left[branch]] +
                                        h->st_freq[h->st_right[branch]]);
        while (leaf_index >= 0 &&
               h->st_freq[h->leafs[leaf_index]] <= h->st_freq[branch]) {
            h->nodes[node_index] = h->leafs[leaf_index];
            h->st_index[h->nodes[node_index]] = (uint16_t)node_index;
            node_index--;
            leaf_index--;
        }
        h->nodes[node_index] = branch;
        h->st_index[branch] = (uint16_t)node_index;
        node_index--;
        pair_index -= 2;
    }
    h->st_parent[h->nodes[0]] = -1;
}

static void lzah_update(Lzah *h, int16_t node)
{
    if (h->st_freq[0] == 0x8000) lzah_reconstruct(h);
    for (;;) {
        h->st_freq[node]++;
        if (h->st_parent[node] < 0) break;
        lzah_rearrange(h, node);
        node = h->st_parent[node];
    }
}

int unc_lzah_decode(UncAlloc *al, UncBitIn *bi, uint32_t outlen, int mode,
                    int (*put)(void *ctx, uint8_t b), void *pctx)
{
    Lzah *h;
    uint32_t pos = 0;
    int err = UNC_OK;

    h = (Lzah *)unc_alloc(al, (uint32_t)sizeof *h);
    if (!h) return UNC_ERR_MEM;
    lzah_reset(h, mode);
    err = unc_canon_build(&h->distance, lzah_distlengths, 64);
    if (err != UNC_OK) goto out;

    while (pos < outlen) {
        int16_t node = 0;   /* storage 0 is always the root */
        int lit;
        while (h->st_left[node] >= 0 || h->st_right[node] >= 0) {
            int bit = unc_bitin_bit(bi);
            if (bit < 0) { err = bi->err; goto out; }
            node = bit ? h->st_left[node] : h->st_right[node];
            if (node < 0) { err = UNC_ERR_CORRUPT; goto out; }
        }
        lzah_update(h, node);
        lit = h->st_value[node];

        if (lit < 0x100) {
            h->window[pos++ & (LZAH_WINDOW - 1)] = (uint8_t)lit;
            err = put(pctx, (uint8_t)lit);
            if (err != UNC_OK) goto out;
        } else if (mode == UNC_LZAH_TRIMMED && lit == 0x100) {
            goto out;                     /* Trimmed's stop code */
        } else {
            int32_t mlen = lit - 0x100 + 3;
            if (mode == UNC_LZAH_TRIMMED) mlen--;   /* 0x101 is 3 */
            int32_t high = unc_canon_decode(&h->distance, bi);
            int32_t low, moff;
            uint32_t from;
            if (high < 0) { err = bi->err != UNC_OK ? bi->err : UNC_ERR_CORRUPT; goto out; }
            low = unc_bitin_bits(bi, 6);
            if (low < 0) { err = bi->err; goto out; }
            moff = (high << 6) + low + 1;
            from = pos - (uint32_t)moff;
            while (mlen-- > 0 && pos < outlen) {
                uint8_t b = h->window[from++ & (LZAH_WINDOW - 1)];
                h->window[pos++ & (LZAH_WINDOW - 1)] = b;
                err = put(pctx, b);
                if (err != UNC_OK) goto out;
            }
        }
    }

out:
    unc_free(al, h);
    return err;
}

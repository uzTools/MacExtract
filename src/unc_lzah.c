/*
 * unc_lzah.c — LHarc's -lh1- coder: a 4 KB-window LZSS whose literals
 * and match lengths come from an ADAPTIVE Huffman tree of 314 leaves,
 * with a static 64-symbol code for the offset's high bits.
 *
 * Two formats here use it and they use the same one: StuffIt classic's
 * method 5 ("LZAH") and LZH's -lh1-. XADMaster runs a single handle for
 * both, which is why this is one file rather than two — the same
 * arrangement DiskDoubler method 8 has with Compact Pro's stages. ARC
 * 7.x's "Trimmed" is the same coder again, differing in one constant:
 * see the modes in unc_internal.h.
 *
 * THE TREE IS YOSHIZAKI'S, NOT XADMASTER'S, since 2026-09-19. Until then
 * this file transcribed reference/XADMaster/XADLZHDynamicHandle.m, which
 * keeps the tree as six parallel node arrays plus a rank list and its
 * inverse, and decodes the offset's high bits through a UncCanon. The
 * published LZHUF (Haruyasu Yoshizaki, 1988, comments by Haruhiko
 * Okumura, 1989 — http://cd.textfiles.com/rbbsv3n1/pac4/okumura.zip; no
 * copyright notice, terms reconstructed as "use, distribute and modify
 * freely", see reference/deark's readme-lzhuf.txt) keeps it as three
 * arrays — freq, son, prnt — with the leaves' order carried in the
 * array itself, and reads the offset's high bits through a 256-entry
 * byte lookup. MacMount's src/mm_lzhuf.c, written from the published
 * program, measured against this file's XADMaster form
 * on Linux: 22–24 % fewer instructions, 9,024 B of state against
 * 15,568, 1,276 B of 68000 code against 1,592, and byte for byte the
 * same output on four real archives and 192 blocks (DECISIONS.md
 * 2026-09-19, *the tree that was Yoshizaki's*). So the tree machinery
 * below follows the published program's shape; what is OURS and kept
 * from the previous version is everything around it — the two modes,
 * the window preload each one wants, the run-based output and the
 * engine's own bit reader.
 *
 * The distance-code lengths are a fact about the format (every reader of
 * these bytes uses the same 64 numbers) and are checked, not trusted:
 * they must tile exactly 256 slots of the lookup, which a mistyped entry
 * cannot do, and the two lookup tables are derived from them by
 * canonical construction rather than copied out of any program.
 *
 * Cross-read against reference/lha/src/dhuf.c, LHa for UNIX 1.14i, which
 * descends from the same program: see DECISIONS.md for the one place the
 * readings differ (the window preload) and which the archives chose.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define LZAH_N_CHAR   314u                  /* 256 literals + 58 lengths */
#define LZAH_T        (LZAH_N_CHAR * 2u - 1u) /* 627 nodes               */
#define LZAH_R        (LZAH_T - 1u)          /* the root                 */
#define LZAH_MAX_FREQ 0x8000u                /* rebuild when the root hits it */
#define LZAH_WINDOW   4096u

typedef struct Lzah {
    /* freq[i] is node i's count and the array is kept SORTED by it,
     * which is what makes the tree adaptive without a rank list: a node
     * whose count overtakes the one after it swaps places. son[i] is
     * node i's first child (the second is son[i] + 1), or T + symbol
     * for a leaf. prnt[i] is node i's parent, and prnt[T + symbol] is
     * where the leaf for `symbol` currently sits. */
    uint16_t freq[LZAH_T + 1];
    uint16_t son[LZAH_T];
    uint16_t prnt[LZAH_T + LZAH_N_CHAR];
    /* The offset's high six bits, from the next eight bits of the
     * stream: which symbol, and how many of the eight it really used. */
    uint8_t  dist_high[256];
    uint8_t  dist_bits[256];
    uint8_t  window[LZAH_WINDOW];
} Lzah;

/* Distance-code lengths, one per high value. The published program
 * prints the 256-entry tables these expand to; this is what they are
 * made of. */
static const uint8_t lzah_distlengths[64] = {
    3,4,4,4,5,5,5,5,5,5,5,5,6,6,6,6,
    6,6,6,6,6,6,6,6,7,7,7,7,7,7,7,7,
    7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
    8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,
};

/* Canonical construction over lzah_distlengths: each symbol takes the
 * next code of its length, and every eight-bit window whose top bits
 * are that code maps back to it. The lengths must tile the 256 slots
 * exactly — filling the last one IS the check. */
static int lzah_build_dist(Lzah *h)
{
    uint32_t sym, code = 0, prev = lzah_distlengths[0], filled = 0;

    for (sym = 0; sym < 64; sym++) {
        uint32_t len = lzah_distlengths[sym], start, count, i;
        if (len < 3 || len > 8) return UNC_ERR_CORRUPT;
        if (sym > 0) code = (code + 1u) << (len - prev);
        prev = len;
        start = code << (8u - len);
        count = 1u << (8u - len);
        if (start + count > 256u) return UNC_ERR_CORRUPT;
        for (i = 0; i < count; i++) {
            h->dist_high[start + i] = (uint8_t)sym;
            h->dist_bits[start + i] = (uint8_t)len;
        }
        filled += count;
    }
    return filled == 256u ? UNC_OK : UNC_ERR_CORRUPT;
}

/* Every leaf at count 1, then the internal nodes summed upwards, in the
 * order that keeps freq[] sorted. */
static void lzah_start(Lzah *h)
{
    uint32_t i, j;

    for (i = 0; i < LZAH_N_CHAR; i++) {
        h->freq[i] = 1;
        h->son[i] = (uint16_t)(i + LZAH_T);
        h->prnt[i + LZAH_T] = (uint16_t)i;
    }
    i = 0;
    j = LZAH_N_CHAR;
    while (j <= LZAH_R) {
        h->freq[j] = (uint16_t)(h->freq[i] + h->freq[i + 1]);
        h->son[j] = (uint16_t)i;
        h->prnt[i] = h->prnt[i + 1] = (uint16_t)j;
        i += 2;
        j++;
    }
    h->freq[LZAH_T] = 0xFFFF;
    h->prnt[LZAH_R] = 0;
}

/* Halve every leaf's count and rebuild the tree over them. The leaves
 * keep their order, so the tree that comes out codes what the encoder's
 * does. */
static void lzah_reconst(Lzah *h)
{
    uint32_t i, j, k, f, l;

    j = 0;
    for (i = 0; i < LZAH_T; i++) {
        if (h->son[i] >= LZAH_T) {
            h->freq[j] = (uint16_t)((h->freq[i] + 1u) / 2u);
            h->son[j] = h->son[i];
            j++;
        }
    }
    for (i = 0, j = LZAH_N_CHAR; j < LZAH_T; i += 2, j++) {
        k = i + 1;
        f = (uint32_t)h->freq[i] + h->freq[k];
        h->freq[j] = (uint16_t)f;
        k = j;
        while (k > 0 && f < h->freq[k - 1]) k--;
        for (l = j; l > k; l--) {
            h->freq[l] = h->freq[l - 1];
            h->son[l] = h->son[l - 1];
        }
        h->freq[k] = (uint16_t)f;
        h->son[k] = (uint16_t)i;
    }
    for (i = 0; i < LZAH_T; i++) {
        k = h->son[i];
        if (k >= LZAH_T) h->prnt[k] = (uint16_t)i;
        else h->prnt[k] = h->prnt[k + 1] = (uint16_t)i;
    }
}

/* One more occurrence of `c`: count it up the tree, swapping a node
 * with the last of the nodes it has just overtaken so freq[] stays
 * sorted. */
static void lzah_update(Lzah *h, uint32_t c)
{
    uint32_t i, j, k, l;

    if (h->freq[LZAH_R] == LZAH_MAX_FREQ) lzah_reconst(h);
    c = h->prnt[c + LZAH_T];
    do {
        k = ++h->freq[c];
        l = c + 1;
        if (k > h->freq[l]) {
            while (l + 1 <= LZAH_T && k > h->freq[l + 1]) l++;
            h->freq[c] = h->freq[l];
            h->freq[l] = (uint16_t)k;

            i = h->son[c];
            h->prnt[i] = (uint16_t)l;
            if (i < LZAH_T) h->prnt[i + 1] = (uint16_t)l;

            j = h->son[l];
            h->son[l] = (uint16_t)i;

            h->prnt[j] = (uint16_t)c;
            if (j < LZAH_T) h->prnt[j + 1] = (uint16_t)c;
            h->son[c] = (uint16_t)j;

            c = l;
        }
        c = h->prnt[c];
    } while (c != 0);
}

/* Window preload, per mode. Zeros for everyone; then, for -lh1- and
 * StuffIt method 5 only, XADMaster's pattern
 * (reference/XADMaster/XADLZHDynamicHandle.m, resetLZSSHandle; the
 * doubt is XADStuffItParser.m's, at case 5: "TODO: Figure out if the
 * initialization of the window differs between LHArc and StuffIt" —
 * we follow what the oracle runs and the archives agree with). LHa
 * for UNIX writes the same five steps for LArc's -lz5- and not for
 * -lh1- (reference/lha/src/larc.c, decode_start_lz5) and lhasa fills
 * the -lh1- buffer with spaces (lh1_decoder.c), so this pattern here
 * is XADMaster's alone and is in NOTICE's inventory.
 * Source: reference/XADMaster/XADLZHDynamicHandle.m (resetLZSSHandle). ARC's Trimmed takes the zeros and NOT the pattern: deark
 * passes history_fill_val = 0 and its ring buffer starts zeroed
 * (reference/deark/foreign/lzhuf.h, lzhuf_Decode_init); a Trimmed
 * member whose first match reaches back past the start of the data is
 * what tells the two apart, and the entry's CRC is what says so. */
static void lzah_preload(Lzah *h, int mode)
{
    uint32_t i;
    for (i = 0; i < LZAH_WINDOW; i++) h->window[i] = 0;
    if (mode == UNC_LZAH_TRIMMED) return;
    for (i = 0; i < 256; i++) {
        uint32_t j;
        for (j = 0; j < 13; j++) h->window[i * 13 + 18 + j] = (uint8_t)i;
    }
    for (i = 0; i < 256; i++) h->window[256 * 13 + 18 + i] = (uint8_t)i;
    for (i = 0; i < 256; i++) h->window[256 * 13 + 256 + 18 + i] = (uint8_t)(255 - i);
    for (i = 0; i < 128; i++) h->window[256 * 13 + 512 + 18 + i] = 0;
    for (i = 0; i < 128 - 18; i++) h->window[256 * 13 + 512 + 128 + 18 + i] = ' ';
}

/* Output leaves through the window itself, a run at a time. Bytes
 * between `flushed` and `pos` have been written and not yet handed
 * over; a run is at most two pieces, because the window wraps. Flushing
 * every LZAH_FLUSH bytes keeps that span, plus the longest match that
 * can land on top of it (60), well inside the 4 KB window, so nothing
 * is overwritten before it is read.
 *
 * ONE call site, at the head of the loop, which also serves the end of
 * the stream: a second one at the exit cost 60-190 B of 68000 code in
 * each of the three coders that do this (measured 2026-09-18). On an
 * error nothing more is flushed; a failed entry's partial output was
 * never graded by anything and the hosts discard it. */
#define LZAH_FLUSH 2048u

static int lzah_flush(const Lzah *h, uint32_t *flushed, uint32_t pos,
                      UncPutRun put, void *pctx)
{
    while (*flushed < pos) {
        uint32_t at = *flushed & (LZAH_WINDOW - 1);
        uint32_t n = pos - *flushed;
        int err;
        if (n > LZAH_WINDOW - at) n = LZAH_WINDOW - at;
        *flushed += n;
        err = put(pctx, h->window + at, n);
        if (err != UNC_OK) return err;
    }
    return UNC_OK;
}

int unc_lzah_decode(UncAlloc *al, UncBitIn *bi, uint32_t outlen, int mode,
                    UncPutRun put, void *pctx)
{
    Lzah *h;
    uint32_t pos = 0, flushed = 0;
    int err;

    h = (Lzah *)unc_alloc(al, (uint32_t)sizeof *h);
    if (!h) return UNC_ERR_MEM;
    err = lzah_build_dist(h);
    if (err != UNC_OK) goto out;
    lzah_start(h);
    lzah_preload(h, mode);

    for (;;) {
        uint32_t c;
        if (pos >= outlen || pos - flushed >= LZAH_FLUSH) {
            err = lzah_flush(h, &flushed, pos, put, pctx);
            if (err != UNC_OK || pos >= outlen) goto out;
        }

        /* Down from the root, one bit per level, to a leaf. */
        c = h->son[LZAH_R];
        while (c < LZAH_T) {
            int bit = unc_bitin_bit(bi);
            if (bit < 0) { err = bi->err; goto out; }
            c = h->son[c + (uint32_t)bit];
        }
        c -= LZAH_T;
        lzah_update(h, c);

        if (c < 0x100) {
            h->window[pos++ & (LZAH_WINDOW - 1)] = (uint8_t)c;
        } else if (mode == UNC_LZAH_TRIMMED && c == 0x100) {
            outlen = pos;                 /* Trimmed's stop code: flush
                                           * what there is, and leave */
            continue;
        } else {
            uint32_t mlen = c - 0x100 + 3;
            uint32_t i, j, high, moff, from;
            int32_t v;
            if (mode == UNC_LZAH_TRIMMED) mlen--;   /* 0x101 is 3 */

            /* The offset: eight bits looked up, of which the code was
             * dist_bits of them, then the rest of the low six bits. */
            v = unc_bitin_bits(bi, 8);
            if (v < 0) { err = bi->err; goto out; }
            i = (uint32_t)v;
            high = h->dist_high[i];
            j = h->dist_bits[i] - 2u;
            while (j-- > 0) {
                int bit = unc_bitin_bit(bi);
                if (bit < 0) { err = bi->err; goto out; }
                i = ((i << 1) & 0xFFu) | (uint32_t)bit;
            }
            moff = (high << 6) + (i & 0x3Fu) + 1u;
            from = pos - moff;
            while (mlen-- > 0 && pos < outlen) {
                uint8_t b = h->window[from++ & (LZAH_WINDOW - 1)];
                h->window[pos++ & (LZAH_WINDOW - 1)] = b;
            }
        }
    }

out:
    unc_free(al, h);
    return err;
}

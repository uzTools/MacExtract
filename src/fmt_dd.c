/*
 * fmt_dd.c — DiskDoubler: single compressed files (0xABCD0054) and the
 * two archive containers, 'DDAR' and 'DDA2'.
 *
 * The CONTAINERS are this project's own description, measured here,
 * since 2026-09-22 — the wiki names three pages for them and none of
 * the three exists:
 *   Source: docs/formats/diskdoubler-container.md
 * `tools/derive_ddc.py` is a reader written from that document alone
 * and makes 643 assertions against the oracle over all 91 DiskDoubler
 * fixtures, 0 disagreements. What it does NOT cover is the 'DDAR'
 * folder records and the 0x20 raw-fork shape, which no fixture here
 * has; those rows are still
 *   Source: reference/XADMaster/XADDiskDoublerParser.m
 * and the note says what would settle them.
 *
 * Method 7 is transcribed:
 *   Source: reference/XADMaster/XADStacLZSHandle.m           (method 7)
 * — LGPL, see NOTICE.
 *
 * The AD and DD coders are NOT, since 2026-09-21. They are written
 * from the format's own published description, with the corrections
 * it needs measured here:
 *   Source: reference/notes/dd_ad_theunarchiver.md
 *           + docs/formats/diskdoubler-dd.md                 (methods 6, 9)
 *   Source: reference/notes/dd_dd_theunarchiver.md
 *           + docs/formats/diskdoubler-dd.md                 (method 10)
 *
 * A file header describes BOTH forks, each with its own method, so one
 * DiskDoubler entry is one entry here (XADMaster splits the forks into
 * two entries; ours is the engine's usual shape).
 *
 * Methods 2, 3, 4 and 5 are recognized and declined per entry: no
 * specimen of any of them has been found, so an implementation could not
 * be graded — the same reason LZH extraction stays out of scope.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define DD_MAGIC   0xABCD0054u
#define DD_DDAR    0x44444152u    /* 'DDAR' */
#define DD_DDA2    0x44444132u    /* 'DDA2' */

#define DD_FILEHDR 80             /* after the 4-byte magic */
#define CPT_DD_WINDOW 8192u       /* Compact Pro's LZH window */

/* ------------------------------------------------------------------ */
/* Per-fork decoding                                                  */
/* ------------------------------------------------------------------ */

typedef struct DdFork {
    UncForkOut out;
    uint32_t left;        /* output bytes still owed */
    uint32_t sum;         /* running byte sum, masked to 16 bits */
    /* Delta preprocessing (type 1, distance 1): each decompressed byte
     * is an increment on the byte `dist` back. It sits OUTSIDE the
     * checksum, which is why the sum is taken before the transform.
     * The transform: docs/formats/diskdoubler-dd.md, "The second form",
     * measured here. WHICH forks use it is the container's to say, and
     * the two fields that say it are measured from both sides:
     * Source: docs/formats/diskdoubler-container.md, "Which forks use
     * method 10's second form" — the container names two forks, and the
     * coder, which never reads a container, finds the same two. */
    uint32_t dist;
    uint32_t dpos;
    uint8_t  dbuf[256];
    uint8_t  xsum;        /* running XOR of the same bytes; method 7 */
    uint16_t sumadj;      /* subtracted from the stored sum; method 1 */
} DdFork;

static void dd_out_start(DdFork *o, UncCtx *c, UncFork fork, uint32_t len,
                         uint8_t *obuf, uint32_t ocap, uint32_t dist)
{
    uint32_t i;
    unc_fork_out(&o->out, c, fork,
                 !c->opt.test_only && !c->opt.list_only,
                 UNC_CK_NONE, obuf, ocap);
    o->left = len; o->sum = 0; o->xsum = 0;
    o->sumadj = 0;
    o->dist = dist; o->dpos = 0;
    for (i = 0; i < sizeof o->dbuf; i++) o->dbuf[i] = 0;
}

/* One decoded byte. The sum and the XOR are taken over what the codec
 * produced, BEFORE the delta transform, which is why they cannot move
 * into the shared writer's flush the way a CRC does. */
static int dd_out_byte(DdFork *o, uint8_t b)
{
    if (o->left == 0) return UNC_OK;      /* trailing filler is dropped */
    o->sum = (o->sum + b) & 0xFFFFu;
    o->xsum ^= b;
    if (o->dist) {
        b = (uint8_t)(b + o->dbuf[(o->dpos - o->dist) & 0xFFu]);
        o->dbuf[o->dpos & 0xFFu] = b;
        o->dpos++;
    }
    {
        int e = unc_fork_put(&o->out, b);
        o->left--;
        return e;
    }
}

/* ---- method 0: stored -------------------------------------------- */

static int dd_store(DdFork *o, UncBufIn *in, uint32_t complen)
{
    uint32_t i;
    int err;
    for (i = 0; i < complen && o->left > 0; i++) {
        int b = unc_bufin_next(in);
        if (b < 0) return in->err;
        if ((err = dd_out_byte(o, (uint8_t)b)) != UNC_OK) return err;
    }
    return UNC_OK;
}

/* ---- methods 6 and 9: ADn ----------------------------------------- */
/*
 * Blocks of at most 0x2000 output bytes. Each carries a 10-byte header
 * whose bytes XOR to zero, then either stored bytes or an LZSS bit
 * stream: 0 = 8-bit literal, 1 = match with an 8- or 12-bit offset and
 * a length of 2, 3, 4, or 5..20. Matches may overlap.
 *
 * Source: reference/notes/dd_ad_theunarchiver.md — the format's own
 * published description, which needs one correction (which way round
 * the flags' bit 0 runs): docs/formats/diskdoubler-dd.md, "AD, methods
 * 6 and 9". All five AD forks in the corpus read from it.
 */
#define DD_AD_BLOCK 0x2000u

static int dd_adn(DdFork *o, UncBufIn *in, uint8_t *win)
{
    UncBitIn bi;
    int err;

    while (o->left > 0) {
        uint32_t compsize, uncompsize, i, pos = 0, blockstart;
        uint8_t hx = 0;
        int flags, b;

        blockstart = unc_bufin_tell(in);

        b = unc_bufin_next(in); if (b < 0) return in->err;
        compsize = (uint32_t)b << 8; hx ^= (uint8_t)b;
        b = unc_bufin_next(in); if (b < 0) return in->err;
        compsize |= (uint32_t)b; hx ^= (uint8_t)b;

        b = unc_bufin_next(in); if (b < 0) return in->err;
        uncompsize = (uint32_t)b << 8; hx ^= (uint8_t)b;
        b = unc_bufin_next(in); if (b < 0) return in->err;
        uncompsize |= (uint32_t)b; hx ^= (uint8_t)b;
        if (uncompsize > DD_AD_BLOCK) return UNC_ERR_CORRUPT;

        for (i = 0; i < 4; i++) {
            b = unc_bufin_next(in); if (b < 0) return in->err;
            hx ^= (uint8_t)b;
        }
        b = unc_bufin_next(in); if (b < 0) return in->err;   /* data xor */
        hx ^= (uint8_t)b;
        flags = unc_bufin_next(in); if (flags < 0) return in->err;
        hx ^= (uint8_t)flags;
        b = unc_bufin_next(in); if (b < 0) return in->err;
        hx ^= (uint8_t)b;
        b = unc_bufin_next(in); if (b < 0) return in->err;   /* head xor */
        if (hx != (uint8_t)b) return UNC_ERR_CORRUPT;

        if (flags & 1) {
            for (i = 0; i < uncompsize; i++) {
                b = unc_bufin_next(in); if (b < 0) return in->err;
                win[i] = (uint8_t)b;
            }
            pos = uncompsize;
        } else {
            unc_bitin_init(&bi, in);
            while (pos < uncompsize) {
                int bit = unc_bitin_bit(&bi);
                if (bit < 0) return bi.err;
                if (!bit) {
                    int32_t lit = unc_bitin_bits(&bi, 8);
                    if (lit < 0) return bi.err;
                    win[pos++] = (uint8_t)lit;
                } else {
                    int32_t offset;
                    uint32_t length;
                    int isfar = unc_bitin_bit(&bi);
                    if (isfar < 0) return bi.err;
                    offset = unc_bitin_bits(&bi, isfar ? 12 : 8);
                    if (offset < 0) return bi.err;
                    if ((uint32_t)offset > pos) return UNC_ERR_CORRUPT;
                    if ((bit = unc_bitin_bit(&bi)) < 0) return bi.err;
                    if (bit == 0) length = 2;
                    else {
                        if ((bit = unc_bitin_bit(&bi)) < 0) return bi.err;
                        if (bit == 0) {
                            if ((bit = unc_bitin_bit(&bi)) < 0) return bi.err;
                            length = bit ? 4u : 3u;
                        } else {
                            int32_t e = unc_bitin_bits(&bi, 4);
                            if (e < 0) return bi.err;
                            length = (uint32_t)e + 5u;
                        }
                    }
                    if (pos + length > uncompsize) length = uncompsize - pos;
                    if (length > (uint32_t)offset) return UNC_ERR_CORRUPT;
                    for (i = 0; i < length; i++)
                        win[pos + i] = win[pos - (uint32_t)offset + i];
                    pos += length;
                }
            }
        }

        for (i = 0; i < pos && o->left > 0; i++)
            if ((err = dd_out_byte(o, win[i])) != UNC_OK) return err;

        /* The block's own size decides where the next one starts, from
         * the end of its 12-byte header; the bit stream is allowed to
         * stop short of it. */
        if ((err = unc_bufin_skip_to(in, blockstart + 12 + compsize)) != UNC_OK)
            return err;
    }
    return UNC_OK;
}

/* ---- method 1: Unix compress -------------------------------------- */
/*
 * compress(1)'s LZW, behind three bytes of its own: the two magic bytes
 * and the flags byte that names the code width and block mode. Three
 * things about it are DiskDoubler's rather than compress's, and all
 * three are what a plain .Z reader would get wrong:
 *
 *  - those three bytes are stored XORed with 0x5a whenever the header
 *    asks for it (`info1 >= 0x2a` and info2's high bit clear), and so
 *    are the DECOMPRESSED bytes — but NOT the code stream between them;
 *  - the fork's stored sum has the three header bytes added into it, so
 *    the sum to compare against is `crc - m1 - m2 - flags`;
 *  - the fork's length is what ends the stream, not the stream itself.
 *
 * Source: XADDiskDoublerParser.m handleForEntryWithDictionary, case 1.
 */
static int dd_lzc(DdFork *o, UncCtx *c, UncBufIn *in, uint32_t complen,
                  int xorval, uint8_t *obuf, uint32_t ocap)
{
    UncLzw z;
    int m1, m2, flags, err;

    if (complen < 3) return UNC_ERR_TRUNCATED;
    if ((m1 = unc_bufin_next(in)) < 0) return in->err;
    if ((m2 = unc_bufin_next(in)) < 0) return in->err;
    if ((flags = unc_bufin_next(in)) < 0) return in->err;
    m1 ^= xorval; m2 ^= xorval; flags ^= xorval;
    o->sumadj = (uint16_t)(m1 + m2 + flags);

    err = unc_lzw_init(&z, c->al, in, flags & 0x1F, (flags & 0x80) != 0,
                       complen - 3u);
    if (err != UNC_OK) return err;
    while (o->left > 0) {
        /* Ask for exactly what the fork still owes. The forks are laid
         * out back to back and nothing marks the end of this one's code
         * stream, so a decoder asked for more than it owes reads the
         * NEXT fork's first code and rejects it as out of range — which
         * is what "corrupt" meant here for one build. */
        int32_t want = (int32_t)(o->left < ocap ? o->left : ocap);
        int32_t got = unc_lzw_read(&z, obuf, want), i;
        if (got < 0) { err = (int)got; break; }
        if (got == 0) break;                     /* end of stream */
        for (i = 0; i < got && o->left > 0; i++)
            if ((err = dd_out_byte(o, (uint8_t)(obuf[i] ^ xorval))) != UNC_OK)
                break;
        if (err != UNC_OK) break;
    }
    unc_lzw_free(&z, c->al);
    return err;
}

/* ---- method 2: splay-tree Huffman, one tree per preceding byte ----- */
/*
 * An order-1 adaptive code: 256 splay trees, the one in use chosen by
 * the byte just produced. Each tree starts as the complete binary tree
 * over 256 leaves — internal node j has children 2j and 2j+1, the root
 * is node 1 and node 256+b is the leaf for byte b — so the first byte
 * of a fork costs eight bits and the tree self-adjusts from there:
 * after each byte its leaf is rotated toward the root, which is what
 * makes the code adaptive without transmitting any table.
 *
 * The decompressed bytes are XORed with 0x5a under the same condition
 * as method 1 (`info1 >= 0x2a` and info2's high bit clear); the fork's
 * 16-bit sum is taken over the result, and unlike method 1 there is no
 * header adjustment because the stream carries no header.
 *
 * Method 5 is this codec with a leading byte giving the tree count
 * (0 meaning 256); it stays declined for want of a specimen.
 *
 * Source: reference/XADMaster/XADDiskDoublerMethod2Handle.m (the tree
 * and the splay step) and XADDiskDoublerParser.m, case 2 (the tree
 * count, the XOR condition and the checksum).
 */
typedef struct DdM2Tree {
    uint16_t left[256];      /* by internal node; a value >= 256 is a leaf */
    uint16_t right[256];
    uint8_t  parent[512];    /* by node, internal and leaf alike */
} DdM2Tree;

typedef struct DdM2 {
    DdM2Tree *tree[256];     /* NULL until a context is first used */
} DdM2;

/* The trees are identical until used, so one is built only when its
 * context byte actually occurs. A fork that never mentions a byte never
 * pays its 1,536 bytes — which is what keeps a small fork small; a fork
 * that uses every context costs 384 KB and is a per-entry allocation
 * failure on a small machine, like any other data-driven allocation
 * here. */
static DdM2Tree *dd_m2_tree(DdM2 *m, UncCtx *c, int i)
{
    DdM2Tree *t = m->tree[i];
    int j;

    if (t) return t;
    t = (DdM2Tree *)unc_alloc(c->al, (uint32_t)sizeof *t);
    if (!t) return NULL;
    for (j = 0; j < 256; j++) {
        t->left[j]  = (uint16_t)(j * 2);
        t->right[j] = (uint16_t)(j * 2 + 1);
        t->parent[j * 2]     = (uint8_t)j;
        t->parent[j * 2 + 1] = (uint8_t)j;
    }
    m->tree[i] = t;
    return t;
}

/* Rotate the leaf just decoded one level toward the root, repeatedly:
 * the node changes places with its uncle, which halves its depth. */
static void dd_m2_splay(DdM2Tree *t, int byte)
{
    int node = byte + 0x100;

    for (;;) {
        int parent = t->parent[node], grand, uncle;

        if (parent == 1) break;
        grand = t->parent[parent];
        uncle = t->left[grand];
        if (uncle == parent) {
            uncle = t->right[grand];
            t->right[grand] = (uint16_t)node;
        } else {
            t->left[grand] = (uint16_t)node;
        }
        if (t->left[parent] != node) t->right[parent] = (uint16_t)uncle;
        else                         t->left[parent]  = (uint16_t)uncle;
        t->parent[node]  = (uint8_t)grand;
        t->parent[uncle] = (uint8_t)parent;

        node = grand;
        if (node == 1) break;
    }
}

static int dd_m2(DdFork *o, UncCtx *c, UncBufIn *in, int xorval, int ntrees)
{
    UncBitIn bi;
    DdM2 m;
    uint8_t ctxof[256];
    int err = UNC_OK, i, ctx = 0;

    /* Method 2 fixes this at 256; method 5 reads it from the stream, and
     * 0 there means 256. Guarded because byte % ntrees is what selects
     * the tree: a zero reaching that would be a crash on a malformed
     * file, which is the one failure the fork's checksum cannot turn
     * into an error. */
    if (ntrees <= 0 || ntrees > 256) ntrees = 256;

    /* ...and the modulo itself runs ONCE PER OUTPUT BYTE. The 256 = 256
     * case is already a special case in the source; the other branch
     * still called __modsi3 per byte on a 68000, which has no divide.
     * A 256-entry table built once answers both. */
    for (i = 0; i < 256; i++)
        ctxof[i] = (uint8_t)(ntrees == 256 ? i : i % ntrees);

    for (i = 0; i < 256; i++) m.tree[i] = NULL;
    unc_bitin_init(&bi, in);

    while (o->left > 0) {
        DdM2Tree *t = dd_m2_tree(&m, c, ctx);
        int node = 1, byte;

        if (!t) { err = UNC_ERR_MEM; break; }
        for (;;) {
            int bit = unc_bitin_bit(&bi);
            if (bit < 0) { err = bi.err; break; }
            node = bit ? t->right[node] : t->left[node];
            if (node >= 0x100) break;
        }
        if (err != UNC_OK) break;
        byte = node - 0x100;
        dd_m2_splay(t, byte);
        ctx = ctxof[byte];
        if ((err = dd_out_byte(o, (uint8_t)(byte ^ xorval))) != UNC_OK) break;
    }

    for (i = 0; i < 256; i++) unc_free(c->al, m.tree[i]);
    return err;
}

/* ---- method 3: RLE90 ----------------------------------------------- */
/*
 * A run filter on an escape byte: ESC 0 is a literal ESC, and ESC n is
 * a run of n copies of the byte before it. Identical in shape to the
 * RLE90 this engine already runs for ARC (`arc_byte`), whose reference
 * is the format's own published description
 * (reference/notes/rle90_theunarchiver.md), and to macutils' `dd_rle`.
 *
 * **The escape byte is derived, not transcribed, and it is the one
 * thing here a specimen has never confirmed.** macutils declares it
 * `#define ESC 0x144` — 324, which no byte can equal, so its own escape
 * branch is unreachable and its method 3 copies input to output. Read as
 * decimal 144 the algorithm becomes RLE90 exactly, escape byte 0x90,
 * which is what the surrounding code computes (`n = *data++ - 1`, then
 * n copies; a count of 0 emits the escape itself). Labelled a
 * HYPOTHESIS until an expander that was there agrees — DECISIONS.md
 * 2026-08-21 (methods 3, 4 and 5).
 *
 * **No 0x5a XOR**, unlike methods 1, 2 and 5, and this is measured
 * rather than transcribed: Salient's own 1991 expander turned a
 * synthetic method 3 fork into exactly the codec's output with no XOR
 * applied, on a header carrying info1 = 0x2a — the value every real
 * file of that era carries. macutils agrees by construction, since
 * `dd_rle` never touches its `dd_xor`. DECISIONS.md 2026-08-21
 * (methods 3, 4 and 5).
 *
 * Source: reference/macutils/macunpack/dd.c dd_rle (the algorithm),
 * reference/notes/rle90_theunarchiver.md (the same filter, and the
 * escape byte — re-cited from XADRLE90Handle.m on 2026-09-21, the
 * page having been in reference/notes/ all along).
 */
static int dd_rle(DdFork *o, UncBufIn *in, uint32_t complen, int xorval)
{
    UncRle90 r;
    uint32_t left = complen;
    int err;

    /* STRICT on ESC 1, like the other five RLE90 call sites. This one
     * was lenient after macutils' dd_rle, which emits nothing for that
     * token; XADRLE90Handle calls it an error, and the tie is broken by
     * the vendor. Salient's own 1991 expander refuses a fork containing
     * one, at offset 0 and 1,800 bytes in, on forks that SHRINK — so not
     * its refusal of a fork that grew (tools/vmac/ddencode.py, RleEsc1 /
     * RleEsc1Mid / RleGrow, 2026-08-29). All 91 DiskDoubler fixtures are
     * byte-exact either way, which is what a token no valid file carries
     * looks like. BLOCKERS.md has what the leniency cost. */
    unc_rle90_init(&r, 1);

    while (o->left > 0) {
        int v = unc_rle90_take(&r);
        if (v < 0) {
            int b;
            /* The compressed side is bounded by complen, not by the
             * stream. An escape still waiting for its count when it
             * runs out is a truncated stream; anything else is the end
             * of one. */
            if (left == 0) return r.esc ? UNC_ERR_TRUNCATED : UNC_OK;
            left--;
            b = unc_bufin_next(in);
            if (b < 0) return in->err;
            v = unc_rle90_feed(&r, b);
            if (v == UNC_RLE90_MORE) continue;
            if (v < 0) return v;
        }
        if ((err = dd_out_byte(o, (uint8_t)(v ^ xorval))) != UNC_OK)
            return err;
    }
    return UNC_OK;
}

/* ---- method 4: StuffIt's Huffman ----------------------------------- */
/*
 * The bit-serialized Huffman tree this engine already reads for StuffIt
 * method 3 and for PackIt, in a DiskDoubler container — the same
 * borrowing method 8 makes of Compact Pro. The 0x5a XOR over decoded
 * bytes and the 16-bit sum are DiskDoubler's.
 *
 * **No 0x5a XOR**, and here this project DISAGREES with its reference:
 * XADMaster's case 4 applies one, and its own author marks the branch
 * untested. Salient's 1991 expander does not — it turned a synthetic
 * method 4 fork into exactly the Huffman output, on a header carrying
 * info1 = 0x2a. A real implementation of the era beats an untested
 * transcription; no specimen exists to break the tie outright.
 * DECISIONS.md 2026-08-21 (methods 3, 4 and 5).
 *
 * Source: docs/formats/serialized-huffman-tree.md. That method 4 is
 * the same serialized tree StuffIt method 3 writes is measured here
 * rather than taken from XADDiskDoublerParser.m: `synth-dd-m4.dd` — a
 * container Salient's own 1991 expander reads back — decodes under the
 * note's rule, 256 leaves and depth 11
 * (tools/derive_huffman_tree.py).
 */
static int dd_huffman(DdFork *o, UncCtx *c, UncBufIn *in, int xorval)
{
    UncBitIn bi;
    UncHuff *h;
    int err;

    h = (UncHuff *)unc_alloc(c->al, (uint32_t)sizeof *h);
    if (!h) return UNC_ERR_MEM;
    unc_bitin_init(&bi, in);
    err = unc_huff_read_tree(h, &bi);
    while (err == UNC_OK && o->left > 0) {
        int sym = unc_huff_decode(h, &bi);
        if (sym < 0) { err = bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT; break; }
        err = dd_out_byte(o, (uint8_t)(sym ^ xorval));
    }
    unc_free(c->al, h);
    return err;
}

/* ---- method 7: Stac LZS -------------------------------------------- */
/*
 * Stac's LZS, which DiskDoubler 3.x wrote when a Sigma Designs
 * compression card was fitted. A 2 KB-window LZSS, with two twists: the
 * bit stream is stored COMPLEMENTED, and so are the bytes it produces;
 * and a match length is not bounded by the window, so it may exceed 2048
 * and repeat.
 *
 * Source: reference/XADMaster/XADStacLZSHandle.m (the codec) and
 * XADDiskDoublerParser.m, case 7 (the chunk table, the two complements
 * and the checksum's parity rule). Cross-checked against
 * reference/macutils/macunpack/dd.c, dd_lzss, which agrees on the codec
 * and on complementing the input, and omits the output's complement.
 */
#define DD_STAC_WINDOW 2048u

/* n bits of a complemented stream. Bits are read MSB-first and each
 * field is contiguous, so complementing the field is complementing the
 * bytes it came from. */
static int32_t dd_stac_bits(UncBitIn *bi, int n)
{
    int32_t v = unc_bitin_bits(bi, n);
    if (v < 0) return v;
    return v ^ (int32_t)((1u << n) - 1u);
}

static int dd_stac(DdFork *o, UncBufIn *in, uint8_t *win, uint32_t complen)
{
    UncBitIn bi;
    uint32_t ne = 0, pos = 0, i;
    int32_t v;
    int err, b;

    /* Six bytes, a 32-bit count of compressed chunks, eight more, then
     * one 16-bit length per chunk. The codec reads none of it: the
     * chunks are one continuous bit stream. */
    if (complen < 18) return UNC_ERR_TRUNCATED;
    for (i = 0; i < 6; i++)
        if (unc_bufin_next(in) < 0) return in->err;
    for (i = 0; i < 4; i++) {
        b = unc_bufin_next(in);
        if (b < 0) return in->err;
        ne = (ne << 8) | (uint32_t)b;
    }
    if (ne > (complen - 18u) / 2u) return UNC_ERR_CORRUPT;
    if ((err = unc_bufin_skip_to(in, 18u + 2u * ne)) != UNC_OK) return err;

    unc_bitin_init(&bi, in);
    while (o->left > 0) {
        if ((v = dd_stac_bits(&bi, 1)) < 0) return bi.err;
        if (v == 0) {
            if ((v = dd_stac_bits(&bi, 8)) < 0) return bi.err;
            win[pos & (DD_STAC_WINDOW - 1u)] = (uint8_t)v;
            pos++;
            if ((err = dd_out_byte(o, (uint8_t)(v ^ 0xFF))) != UNC_OK)
                return err;
        } else {
            uint32_t offset, length;
            if ((v = dd_stac_bits(&bi, 1)) < 0) return bi.err;
            if (v == 1) {
                if ((v = dd_stac_bits(&bi, 7)) < 0) return bi.err;
                offset = (uint32_t)v;
            } else {
                if ((v = dd_stac_bits(&bi, 7)) < 0) return bi.err;
                if (v == 0) break;                  /* end of stream */
                offset = (uint32_t)v << 4;
                if ((v = dd_stac_bits(&bi, 4)) < 0) return bi.err;
                offset |= (uint32_t)v;
            }
            if ((v = dd_stac_bits(&bi, 2)) < 0) return bi.err;
            length = (uint32_t)v;
            if (length == 3) {
                if ((v = dd_stac_bits(&bi, 2)) < 0) return bi.err;
                length += (uint32_t)v;
                if (length == 6) {
                    do {
                        if ((v = dd_stac_bits(&bi, 4)) < 0) return bi.err;
                        length += (uint32_t)v;
                    } while (v == 15);
                }
            }
            length += 2;
            /* A zero distance names no byte. XADStacLZSHandle rejects it
             * only through `offset>pos`, macunpack ends the stream on it;
             * no specimen reaches either. */
            if (offset == 0 || offset > pos) return UNC_ERR_CORRUPT;
            for (i = 0; i < length && o->left > 0; i++) {
                uint8_t m = win[(pos - offset) & (DD_STAC_WINDOW - 1u)];
                win[pos & (DD_STAC_WINDOW - 1u)] = m;
                pos++;
                if ((err = dd_out_byte(o, (uint8_t)(m ^ 0xFF))) != UNC_OK)
                    return err;
            }
        }
    }
    return UNC_OK;
}

/* ---- method 10: DDn ----------------------------------------------- */
/*
 * LZSS over a 64 KB window, block by block. A block header names three
 * separately Huffman-coded streams laid out back to back — offsets,
 * literals, lengths — and the lengths stream drives the walk: symbol 0
 * is "take the next literal", 1..127 is a match of code+2 bytes using
 * the next offset, and 128+ is a run of 1<<(code-128) literals.
 *
 * Source: reference/notes/dd_dd_theunarchiver.md — the format's own
 * published description — with the six corrections it needs in
 * docs/formats/diskdoubler-dd.md, where a reader written from that page
 * alone reads all 39 DD and AD forks in the corpus.
 */
typedef struct DdnState {
    uint8_t  *win;          /* LZSS window */
    uint32_t  wsize, wmask;
    uint8_t  *lit;          /* offsets, then literals, per block */
    uint32_t  litcap;
    uint32_t  base;         /* absolute offset of the entry's data */
    uint32_t  origin;       /* absolute offset the buffer was re-based at:
                             * unc_bufin_tell() counts from the last init,
                             * and this decoder addresses the file. */
} DdnState;

/* Absolute file position of the read cursor. */
static uint32_t ddn_at(const DdnState *st, const UncBufIn *in)
{
    return st->origin + unc_bufin_tell(in);
}

typedef struct DdnCode { UncCanon canon; } DdnCode;

/* One prefix code: a 4-byte head, then per-symbol code lengths, either
 * plain or with a present/absent bit each ("zero coding").
 * Source: reference/notes/dd_dd_theunarchiver.md, "Huffman coding";
 * the canonical-code convention it omits is docs/formats/diskdoubler-dd.md
 * correction 5. */
static int ddn_read_code(const DdnState *st, UncCanon *out, UncBufIn *in,
                         uint8_t *lenbuf, uint32_t *endout)
{
    UncBitIn bi;
    uint32_t head = 0, end;
    int numcodes, numbytes, maxlength, numbits, i;

    for (i = 0; i < 4; i++) {
        int b = unc_bufin_next(in);
        if (b < 0) return in->err;
        head = (head << 8) | (uint32_t)b;
    }
    numcodes  = (int)((head >> 24) & 0xFF) + 1;
    numbytes  = (int)((head >> 13) & 0x7FF);
    maxlength = (int)((head >> 8) & 0x1F);
    numbits   = (int)((head >> 3) & 0x1F);
    if (numbits > 24 || maxlength > UNC_CANON_MAX_BITS) return UNC_ERR_CORRUPT;

    end = ddn_at(st, in) + (uint32_t)numbytes;
    *endout = end;

    unc_bitin_init(&bi, in);
    for (i = 0; i < numcodes; i++) {
        int32_t v;
        if (head & 0x04) {
            int present = unc_bitin_bit(&bi);
            if (present < 0) return bi.err;
            if (!present) { lenbuf[i] = 0; continue; }
        }
        v = unc_bitin_bits(&bi, numbits);
        if (v < 0) return bi.err;
        if (v > maxlength) return UNC_ERR_CORRUPT;
        lenbuf[i] = (uint8_t)v;
    }
    return unc_canon_build(out, lenbuf, numcodes);
}

static int ddn_seek(DdnState *st, UncCtx *c, UncBufIn *in, uint8_t *iobuf,
                    uint32_t iocap, uint32_t abs)
{
    if (c->io->seek(c->io->ctx, abs) < 0) return UNC_ERR_IO;
    unc_bufin_init(in, c->io, &c->ps, iobuf, iocap);
    st->origin = abs;
    return UNC_OK;
}

/* The three code tables of a DDn block. On the heap, not the stack: an
 * UncCanon is ~1.3 KB and this function holds three at once, which put
 * the unc_dd_extract -> dd_fork -> dd_ddn chain at 6,664 B (measured,
 * m68k -Os -fstack-usage) against CLAUDE.md's 4 KB call-depth rule.
 * Not against the machine — the shell asks for 32 KB of stack, so this
 * was over the RULE and nowhere near the limit — but the rule is what
 * keeps the engine portable to a host that did not ask. */
typedef struct DdnCodes { UncCanon len, off, lit; } DdnCodes;

static int dd_ddn_run(DdFork *o, UncCtx *c, DdnState *st, UncBufIn *in,
                      uint8_t *iobuf, uint32_t iocap, DdnCodes *cd)
{
    UncBitIn bi;
    uint8_t lenbuf[257];
    uint32_t nextblock = st->base, wpos = 0;
    int err;

    while (o->left > 0) {
        uint32_t uncompsize, numliterals, numoffsets;
        uint32_t lengthcompsize, literalcompsize, offsetcompsize;
        uint32_t literalstart, lengthstart, need, produced = 0, codeend;
        uint32_t litpos = 0, offpos = 0;
        uint8_t hx = 0;
        int flags, i, b;
        uint16_t *offs;
        uint8_t *lits;

        if ((err = ddn_seek(st, c, in, iobuf, iocap, nextblock)) != UNC_OK)
            return err;

        uncompsize = 0;
        for (i = 0; i < 4; i++) {
            b = unc_bufin_next(in); if (b < 0) return in->err;
            uncompsize = (uncompsize << 8) | (uint32_t)b;
            hx ^= (uint8_t)b;
        }
        numliterals = 0;
        for (i = 0; i < 2; i++) {
            b = unc_bufin_next(in); if (b < 0) return in->err;
            numliterals = (numliterals << 8) | (uint32_t)b; hx ^= (uint8_t)b;
        }
        numoffsets = 0;
        for (i = 0; i < 2; i++) {
            b = unc_bufin_next(in); if (b < 0) return in->err;
            numoffsets = (numoffsets << 8) | (uint32_t)b; hx ^= (uint8_t)b;
        }
        lengthcompsize = 0;
        for (i = 0; i < 2; i++) {
            b = unc_bufin_next(in); if (b < 0) return in->err;
            lengthcompsize = (lengthcompsize << 8) | (uint32_t)b; hx ^= (uint8_t)b;
        }
        literalcompsize = 0;
        for (i = 0; i < 2; i++) {
            b = unc_bufin_next(in); if (b < 0) return in->err;
            literalcompsize = (literalcompsize << 8) | (uint32_t)b; hx ^= (uint8_t)b;
        }
        offsetcompsize = 0;
        for (i = 0; i < 2; i++) {
            b = unc_bufin_next(in); if (b < 0) return in->err;
            offsetcompsize = (offsetcompsize << 8) | (uint32_t)b; hx ^= (uint8_t)b;
        }
        flags = unc_bufin_next(in); if (flags < 0) return in->err;
        hx ^= (uint8_t)flags;
        for (i = 0; i < 6; i++) {         /* pad, three data xors, uncomp
                                           * xor, pad — all folded in */
            b = unc_bufin_next(in); if (b < 0) return in->err;
            hx ^= (uint8_t)b;
        }
        b = unc_bufin_next(in); if (b < 0) return in->err;
        if (hx != (uint8_t)b) return UNC_ERR_CORRUPT;

        if (flags & 0x40) {               /* stored block */
            uint32_t n;
            for (n = 0; n < uncompsize; n++) {
                b = unc_bufin_next(in); if (b < 0) return in->err;
                st->win[wpos & st->wmask] = (uint8_t)b;
                wpos++;
                if (o->left && (err = dd_out_byte(o, (uint8_t)b)) != UNC_OK)
                    return err;
            }
            nextblock = ddn_at(st, in);
            continue;
        }

        literalstart = ddn_at(st, in) + offsetcompsize;
        lengthstart  = literalstart + literalcompsize;
        nextblock    = lengthstart + lengthcompsize;

        need = numliterals + numoffsets * 2u;
        if (need > 0x10000u) return UNC_ERR_CORRUPT;
        if (need > st->litcap) {
            uint32_t want = (need + 0xFFFu) & ~0xFFFu;
            uint8_t *nb;
            unc_free(c->al, st->lit);
            st->lit = NULL; st->litcap = 0;
            nb = (uint8_t *)unc_alloc(c->al, want);
            if (!nb) return UNC_ERR_MEM;
            st->lit = nb; st->litcap = want;
        }
        offs = (uint16_t *)(void *)st->lit;
        lits = st->lit + numoffsets * 2u;

        /* offsets */
        if ((err = ddn_read_code(st, &cd->off, in, lenbuf, &codeend)) != UNC_OK)
            return err;
        if ((err = ddn_seek(st, c, in, iobuf, iocap, codeend)) != UNC_OK) return err;
        unc_bitin_init(&bi, in);
        for (i = 0; (uint32_t)i < numoffsets; i++) {
            int slot = unc_canon_decode(&cd->off, &bi);
            if (slot < 0) return bi.err ? bi.err : UNC_ERR_CORRUPT;
            if (slot < 4) offs[i] = (uint16_t)(slot + 1);
            else {
                int bits = slot / 2 - 1;
                int32_t start = ((2 + (slot & 1)) << bits) + 1;
                int32_t extra = unc_bitin_bits(&bi, bits);
                if (extra < 0) return bi.err;
                offs[i] = (uint16_t)(start + extra);
            }
        }

        /* literals */
        if ((err = ddn_seek(st, c, in, iobuf, iocap, literalstart)) != UNC_OK)
            return err;
        if (flags & 0x80) {
            if ((err = ddn_read_code(st, &cd->lit, in, lenbuf, &codeend)) != UNC_OK)
                return err;
            if ((err = ddn_seek(st, c, in, iobuf, iocap, codeend)) != UNC_OK) return err;
            unc_bitin_init(&bi, in);
            for (i = 0; (uint32_t)i < numliterals; i++) {
                int sym = unc_canon_decode(&cd->lit, &bi);
                if (sym < 0) return bi.err ? bi.err : UNC_ERR_CORRUPT;
                lits[i] = (uint8_t)sym;
            }
        } else {
            for (i = 0; (uint32_t)i < numliterals; i++) {
                b = unc_bufin_next(in); if (b < 0) return in->err;
                lits[i] = (uint8_t)b;
            }
        }

        /* lengths, and the walk they drive */
        if ((err = ddn_seek(st, c, in, iobuf, iocap, lengthstart)) != UNC_OK)
            return err;
        if ((err = ddn_read_code(st, &cd->len, in, lenbuf, &codeend)) != UNC_OK)
            return err;
        if ((err = ddn_seek(st, c, in, iobuf, iocap, codeend)) != UNC_OK) return err;
        unc_bitin_init(&bi, in);

        while (produced < uncompsize) {
            int code = unc_canon_decode(&cd->len, &bi);

            uint32_t length, k;
            if (code < 0) return bi.err ? bi.err : UNC_ERR_CORRUPT;
            if (code == 0) {
                if (litpos >= numliterals) return UNC_ERR_CORRUPT;
                st->win[wpos & st->wmask] = lits[litpos];
                if ((err = dd_out_byte(o, lits[litpos])) != UNC_OK) return err;
                litpos++; wpos++; produced++;
                continue;
            }
            if (code < 128) {
                uint32_t offset;
                length = (uint32_t)code + 2u;
                if (offpos >= numoffsets) return UNC_ERR_CORRUPT;
                offset = offs[offpos++];
                if (offset > wpos) return UNC_ERR_CORRUPT;
                if (produced + length > uncompsize) length = uncompsize - produced;
                for (k = 0; k < length; k++) {
                    uint8_t v = st->win[(wpos - offset) & st->wmask];
                    st->win[wpos & st->wmask] = v;
                    if ((err = dd_out_byte(o, v)) != UNC_OK) return err;
                    wpos++;
                }
                produced += length;
                continue;
            }
            length = 1u << (code - 128);
            if (produced + length > uncompsize) length = uncompsize - produced;
            for (k = 0; k < length; k++) {
                if (litpos >= numliterals) return UNC_ERR_CORRUPT;
                st->win[wpos & st->wmask] = lits[litpos];
                if ((err = dd_out_byte(o, lits[litpos])) != UNC_OK) return err;
                litpos++; wpos++;
            }
            produced += length;
        }
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* One fork                                                           */
/* ------------------------------------------------------------------ */

/* Window size for DDn: the format's 64 KB, or the entry if smaller —
 * the same reasoning as StuffIt method 13 (DECISIONS.md 2026-08-06). */
/* Thin wrapper so the ~3.8 KB of code tables is allocated and freed in
 * one place rather than at each of dd_ddn_run's two dozen early exits. */
static int dd_ddn(DdFork *o, UncCtx *c, DdnState *st, UncBufIn *in,
                  uint8_t *iobuf, uint32_t iocap)
{
    DdnCodes *cd = (DdnCodes *)unc_alloc(c->al, (uint32_t)sizeof *cd);
    int err;
    if (!cd) return UNC_ERR_MEM;             /* per-entry, not fatal */
    err = dd_ddn_run(o, c, st, in, iobuf, iocap, cd);
    unc_free(c->al, cd);
    return err;
}

static uint32_t dd_window_for(uint32_t size)
{
    uint32_t w = 1024;
    while (w < size && w < 65536u) w <<= 1;
    return w;
}

/* Compact Pro compression in a DiskDoubler container: sixteen bytes
 * whose sum decides whether the LZH stage is present, then Compact
 * Pro's RLE either way, and the fork's checksum is a CRC-16/ARC over
 * the result. It is the one method that does not decode through
 * DdFork — Compact Pro's stage carries its own writer and its own
 * checksum — which is why it sits outside dd_fork's dispatch instead
 * of inside it.
 * Source: XADDiskDoublerParser.m handleForEntryWithDictionary, case 8. */
static int dd_fork_cpt(UncCtx *c, UncFork fork, uint32_t complen,
                       uint32_t uncomplen, uint16_t crc)
{
    uint32_t iocap = UNC_IOBUF, ocap = UNC_IOBUF;
    CptRle rle;
    CptLzh *hz = NULL;
    uint8_t *window = NULL, *mem;
    uint32_t sub = 0;
    int i, err;

    mem = (uint8_t *)unc_alloc(c->al, iocap + ocap);
    if (!mem) return UNC_ERR_MEM;
    {
        UncBufIn in;
        unc_bufin_init(&in, c->io, &c->ps, mem, iocap);
        for (i = 0; i < 16; i++) {
            int b = unc_bufin_next(&in);
            if (b < 0) { unc_free(c->al, mem); return in.err; }
            sub += (uint32_t)b;
        }
        unc_cpt_rle_start(&rle, c, fork, uncomplen, 0, mem + iocap, ocap);
        /* This container checks a CRC-16/ARC that Compact Pro itself
         * does not keep. */
        rle.out.ck = UNC_CK_CRC32_16;
        if (sub == 0) {
            hz = (CptLzh *)unc_alloc(c->al, (uint32_t)sizeof *hz);
            window = (uint8_t *)unc_alloc(c->al, CPT_DD_WINDOW);
            if (!hz || !window) {
                unc_free(c->al, hz); unc_free(c->al, window);
                unc_free(c->al, mem);
                return UNC_ERR_MEM;
            }
            err = unc_cpt_lzh_fork(&rle, &in, hz, window, 0xFFF0u);
        } else {
            err = unc_cpt_rle_fork(&rle, &in, complen - 16u);
        }
    }
    unc_free(c->al, hz);
    unc_free(c->al, window);
    if (err == UNC_OK) err = unc_cpt_rle_flush(&rle);
    if (err == UNC_OK && rle.remaining != 0) err = UNC_ERR_TRUNCATED;
    if (err == UNC_OK && crc != 0 && rle.out.crc16 != crc) err = UNC_ERR_CRC;
    unc_free(c->al, mem);
    return err;
}

/* Working memory each method wants BEHIND the input and output staging,
 * so that the one allocation and the one UncBufIn are set up once
 * rather than in every branch of the dispatch. */
#define DD_LZC_STAGE 2048u          /* LZW hands back runs, not bytes  */

static uint32_t dd_extra(int m, uint32_t uncomplen)
{
    switch (m) {
    case 1:            return DD_LZC_STAGE;
    case 6: case 9:    return DD_AD_BLOCK;
    case 7:            return DD_STAC_WINDOW;
    case 10:           return dd_window_for(uncomplen);
    default:           return 0;
    }
}

static int dd_fork(UncCtx *c, UncFork fork, uint32_t at, uint32_t complen,
                   uint32_t uncomplen, int method, int delta, uint16_t crc,
                   int xorval, int xorsum)
{
    uint8_t *mem, *work;
    UncBufIn in;
    DdFork o;
    uint32_t iocap = UNC_IOBUF, ocap = UNC_IOBUF;
    int err, m = method & 0x7F;

    if (uncomplen == 0) return UNC_OK;
    if (delta != 0 && delta != 1) return UNC_ERR_UNSUPPORTED;

    switch (m) {
    case 0: case 1: case 2: case 3: case 4: case 5:
    case 6: case 7: case 8: case 9: case 10: break;
    default: return UNC_ERR_UNSUPPORTED;
    }
    /* Method 8's RLE stage writes to the sink itself, so the delta
     * transform has nowhere to sit; no corpus fixture pairs them. */
    if (m == 8 && delta != 0) return UNC_ERR_UNSUPPORTED;

    if (c->io->seek(c->io->ctx, at) < 0) return UNC_ERR_IO;

    if (m == 8) return dd_fork_cpt(c, fork, complen, uncomplen, crc);

    mem = (uint8_t *)unc_alloc(c->al, iocap + ocap + dd_extra(m, uncomplen));
    if (!mem) return UNC_ERR_MEM;
    unc_bufin_init(&in, c->io, &c->ps, mem, iocap);
    dd_out_start(&o, c, fork, uncomplen, mem + iocap, ocap,
                 delta == 1 ? 1u : 0u);
    work = mem + iocap + ocap;

    switch (m) {
    case 0:
        err = dd_store(&o, &in, complen);
        break;
    case 1:
        err = dd_lzc(&o, c, &in, complen, xorval, work, DD_LZC_STAGE);
        break;
    case 2:
    case 5: {
        int ntrees = 256;
        if (m == 5) {
            /* Method 5 is method 2 with the tree count in front of the
             * bit stream, 0 meaning 256.
             * Source: XADDiskDoublerParser.m case 5. */
            int nb = unc_bufin_next(&in);
            if (nb < 0) { err = in.err; break; }
            ntrees = nb == 0 ? 256 : nb;
        }
        err = dd_m2(&o, c, &in, xorval, ntrees);
        break;
    }
    case 3:
        err = dd_rle(&o, &in, complen, 0);
        break;
    case 4:
        err = dd_huffman(&o, c, &in, 0);
        break;
    case 6:
    case 9:
        err = dd_adn(&o, &in, work);
        break;
    case 7:
        err = dd_stac(&o, &in, work, complen);
        break;
    default: {                                       /* method 10, DDn */
        DdnState st;
        uint32_t wsize = dd_extra(10, uncomplen);
        st.win = work;
        st.wsize = wsize;
        st.wmask = wsize - 1;
        st.lit = NULL;
        st.litcap = 0;
        st.base = at;
        err = dd_ddn(&o, c, &st, &in, mem, iocap);
        unc_free(c->al, st.lit);
        break;
    }
    }

    if (err == UNC_OK) err = unc_fork_flush(&o.out);
    if (err == UNC_OK && o.left != 0) err = UNC_ERR_TRUNCATED;
    /* Methods 0..5 carry a 16-bit sum of the decompressed bytes; the
     * AD and DD methods carry per-block XORs instead and store 0 here.
     * Source: XADDiskDoublerParser.m handleForEntryWithDictionary. */
    if (err == UNC_OK && !xorsum && m <= 5 && crc != 0 &&
        o.sum != (uint16_t)(crc - o.sumadj))
        err = UNC_ERR_CRC;
    /* A DDA2 entry stored in the archive with no file header of its own
     * carries a one-byte XOR of each fork where the header would carry
     * that sum, and carries it whatever its value: 0 means an empty
     * fork, which never reaches here. Measured on both stored forks of
     * all five DiskDoubler Pro 4.1.1 archives (DECISIONS.md 2026-08-21). */
    if (err == UNC_OK && xorsum && o.xsum != (uint8_t)crc)
        err = UNC_ERR_CRC;
    /* Method 7 carries a one-byte XOR of the fork instead, complemented
     * when the fork's length is even.
     * Source: XADDiskDoublerParser.m handleForEntryWithDictionary, case 7. */
    if (err == UNC_OK && m == 7 && crc != 0) {
        uint8_t want = (uint8_t)crc;
        if ((uncomplen & 1u) == 0) want ^= 0xFF;
        if (o.xsum != want) err = UNC_ERR_CRC;
    }
    unc_free(c->al, mem);
    return err;
}

/* ------------------------------------------------------------------ */
/* File headers and the two archive walks                             */
/* ------------------------------------------------------------------ */

typedef struct DdFile {
    uint32_t datasize, datacomp, rsrcsize, rsrccomp;
    int      datamethod, rsrcmethod;
    uint32_t modification, creation, type, creator;
    int      finderflags, datadelta, rsrcdelta;
    uint16_t datacrc, rsrccrc;
    int      info1, info2;   /* method 1's obfuscation, below */
    int      xorsum;         /* datacrc/rsrccrc are one-byte XORs */
} DdFile;

/* The 80 bytes after 0xABCD0054.
 * Source: docs/formats/diskdoubler-container.md, "A compressed file".
 * The same 84 bytes appear three times — as a file, and inside both
 * archive containers — which is itself measured: the fork lengths pin
 * at one offset across all 195 of them. */
static void dd_parse_filehdr(const uint8_t *h, DdFile *f)
{
    f->datasize     = unc_get_u32be(h + 0);
    f->datacomp     = unc_get_u32be(h + 4);
    f->rsrcsize     = unc_get_u32be(h + 8);
    f->rsrccomp     = unc_get_u32be(h + 12);
    f->datamethod   = h[16];
    f->rsrcmethod   = h[17];
    f->info1        = h[18];
    f->info2        = h[48];
    f->modification = unc_get_u32be(h + 20);
    f->creation     = unc_get_u32be(h + 24);
    f->type         = unc_get_u32be(h + 28);
    f->creator      = unc_get_u32be(h + 32);
    f->finderflags  = (int)unc_get_u16be(h + 36);
    f->datacrc      = unc_get_u16be(h + 44);
    f->rsrccrc      = unc_get_u16be(h + 46);
    f->datadelta    = (int)unc_get_u16be(h + 50);
    f->rsrcdelta    = (int)unc_get_u16be(h + 52);
    f->xorsum       = 0;
}

static void dd_entry_from(UncEntryInfo *e, const DdFile *f)
{
    e->type         = f->type;
    e->creator      = f->creator;
    e->finder_flags = (uint16_t)f->finderflags;
    e->create_date  = f->creation;
    e->mod_date     = f->modification;
    e->data_size    = f->datasize;
    e->rsrc_size    = f->rsrcsize;
    e->comp_data_size = f->datacomp;
    e->comp_rsrc_size = f->rsrccomp;
    e->method_data  = (uint8_t)(f->datamethod & 0x7F);
    e->method_rsrc  = (uint8_t)(f->rsrcmethod & 0x7F);
}

/* The obfuscation methods 1..5 apply to their three header bytes and to
 * the bytes they decode. It is on when info1 has reached 0x2a and info2's
 * high bit is clear; every specimen seen has info1 == 0x2a exactly, so
 * no fixture here tells the >= from an ==.
 * Source: docs/formats/diskdoubler-container.md, "The XOR garbling". */
static int dd_xorval(const DdFile *f)
{
    return (f->info1 >= 0x2a && (f->info2 & 0x80) == 0) ? 0x5a : 0;
}

/* Emit one file: begin, both forks, end. `at` is where the data fork's
 * compressed bytes start. */
static int dd_emit(UncCtx *c, UncEntryInfo *e, const DdFile *f, uint32_t at)
{
    int sret, err = UNC_OK, ferr;

    sret = c->sink->begin_entry(c->sink->ctx, e);
    if (sret < 0) return UNC_ERR_SINK;
    if (sret > 0) return UNC_OK;

    if (!c->opt.list_only) {
        err = dd_fork(c, UNC_FORK_DATA, at, f->datacomp, f->datasize,
                      f->datamethod, f->datadelta, f->datacrc, dd_xorval(f),
                      f->xorsum);
        ferr = dd_fork(c, UNC_FORK_RSRC, at + f->datacomp, f->rsrccomp,
                       f->rsrcsize, f->rsrcmethod, f->rsrcdelta, f->rsrccrc,
                       dd_xorval(f), f->xorsum);
        if (err == UNC_OK) err = ferr;
    }

    if (c->sink->end_entry(c->sink->ctx, err) < 0) return UNC_ERR_SINK;
    if (unc_fatal(err))
        return err;
    return UNC_OK;
}

/* ---- 'DDAR' ------------------------------------------------------- */

static int dd_archive(UncCtx *c)
{
    UncPath path;
    uint8_t hdr[124];
    uint32_t at = 78;      /* 'DDAR' + 74 header bytes */
    int err;

    unc_path_init(&path, c);

    for (;;) {
        uint32_t magic, datasize, rsrcsize, start;
        uint32_t nlen;
        UncEntryInfo e;
        int isdir, enddir, sret;

        if (c->io->seek(c->io->ctx, at) < 0) return UNC_ERR_IO;
        err = unc_read_full(c->io, hdr, 4);
        if (err != UNC_OK) {
            /* A DDAR archive ends where the FILE ends — there is no end
             * marker to look for — so running out of bytes here is the
             * end of the archive only when the walk arrived exactly at
             * the end of the file. Bytes still ahead mean a header that
             * stops part way; a position PAST the end means an entry
             * whose data was cut off and stepped over. Neither is an
             * end:
             * until 2026-08-29 both came out as a clean walk, so an
             * archive cut in half extracted the entries before the cut
             * and reported success (unar calls the same file broken;
             * BLOCKERS.md). */
            if ((unc_off_t)at != c->io->size(c->io->ctx))
                return UNC_ERR_TRUNCATED;
            break;                                /* end of archive */
        }
        magic = unc_get_u32be(hdr);
        /* Four bytes read from inside the file that are not a record:
         * every entry position in a DDAR archive is one, so this is a
         * cut or a corrupted archive rather than its end — the end is
         * where the FILE ends, and is taken above.
         *
         * There is no skip for a compressed-file header here any more.
         * What used to look like a stray one is the PREVIOUS entry's
         * header trailer, which lives inside that entry's stated span:
         * a compressed file ends with a byte-identical copy of its own
         * 84-byte header, in 63 of the corpus's 66 (the three without
         * it are this tree's own synthetic specimens).
         * Source: docs/formats/diskdoubler-container.md, "The header is
         * written twice". */
        if (magic != DD_DDAR) return UNC_ERR_TRUNCATED;

        /* 120 bytes: the entry header is 124 including its magic, and
         * the last field in it (rsrccrc) sits at byte 120. A header
         * whose magic is there and whose body is not is truncation, and
         * nothing else: there is no reading of this file in which those
         * four bytes are the last thing in it. */
        if (unc_read_full(c->io, hdr, 120) != UNC_OK) return UNC_ERR_TRUNCATED;
        nlen = hdr[4];
        if (nlen > 63) nlen = 63;
        isdir  = hdr[68];
        enddir = hdr[69];
        datasize = unc_get_u32be(hdr + 70);
        rsrcsize = unc_get_u32be(hdr + 74);
        start = at + 124;

        if (enddir) {
            unc_path_pop(&path);
            at = start;
            continue;
        }

        unc_entry_clear(&e);
        if (isdir) {
            /* NO SPECIMEN. All 36 entries in the corpus's 7 DDAR
             * archives are files with a full file header, so neither
             * this branch nor the 0x20 one below is read by anything
             * here. Both rows are still
             * Source: XADDiskDoublerParser.m parseArchive (macutils'
             * macunpack/dd.h states the same offsets under its own
             * names, which is agreement between two readers and not a
             * specimen). docs/formats/diskdoubler-container.md, "What
             * no DDAR fixture here reaches", says what would settle it.
             *
             * The folder's own path is the leaf of the path it is being
             * pushed onto, which is where the whole name is reported
             * from; taking it out of path.buf afterwards would report a
             * name already cut to UNC_NAME_MAX. */
            unc_path_leaf(&path, &e, hdr + 5, nlen);
            if ((err = unc_path_push(&path, hdr + 5, nlen)) != UNC_OK) return err;
            e.is_dir = 1;
            e.create_date = unc_get_u32be(hdr + 78);
            e.mod_date    = unc_get_u32be(hdr + 82);
            /* A skipped entry gets no end_entry — the contract in
             * macextract.h, which this said nothing about until a host
             * skipped a FOLDER rather than a file (2026-08-28). */
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) return UNC_ERR_SINK;
            if (sret == 0 && c->sink->end_entry(c->sink->ctx, UNC_OK) < 0)
                return UNC_ERR_SINK;
            at = start;
            continue;
        }

        unc_path_leaf(&path, &e, hdr + 5, nlen);

        if (unc_get_u16be(hdr + 94) & 0x20) {
            /* Stored in the archive with no file header of its own.
             * NO SPECIMEN either — see the folder branch above. */
            DdFile f;
            uint8_t *fp = (uint8_t *)&f;
            uint32_t fi;
            for (fi = 0; fi < sizeof f; fi++) fp[fi] = 0;
            f.datasize = f.datacomp = datasize;
            f.rsrcsize = f.rsrccomp = rsrcsize;
            f.creation     = unc_get_u32be(hdr + 78);
            f.modification = unc_get_u32be(hdr + 82);
            f.type         = unc_get_u32be(hdr + 86);
            f.creator      = unc_get_u32be(hdr + 90);
            f.finderflags  = (int)unc_get_u16be(hdr + 94);
            f.datacrc      = unc_get_u16be(hdr + 114);
            f.rsrccrc      = unc_get_u16be(hdr + 116);
            dd_entry_from(&e, &f);
            if ((err = dd_emit(c, &e, &f, start)) != UNC_OK) return err;
            at = start + datasize + rsrcsize;
            continue;
        }

        /* Otherwise a full file header follows. The entry's own record
         * has already said this file is here, so a header that runs out
         * mid-way is a cut archive rather than the end of one — it
         * broke out of the walk and returned success until 2026-08-29,
         * which is how a file cut to a fifth of itself extracted two
         * entries of five and called the run complete. */
        if (c->io->seek(c->io->ctx, start) < 0) return UNC_ERR_IO;
        if (unc_read_full(c->io, hdr, 4) != UNC_OK) return UNC_ERR_TRUNCATED;
        if (unc_get_u32be(hdr) != DD_MAGIC) return UNC_ERR_CORRUPT;
        if (unc_read_full(c->io, hdr, DD_FILEHDR) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        {
            DdFile f;
            uint32_t inner;
            dd_parse_filehdr(hdr, &f);
            /* The record's own +74 is the whole ENTRY's span, and it is
             * what walks the archive: `record + 124 + span` lands on
             * the next record, or on the last byte, in all nine DDAR
             * archives reachable here. What it spans is a compressed
             * FILE, so it is that file's length — with or without the
             * header trailer, and nothing else.
             * Source: docs/formats/diskdoubler-container.md, "DDAR". */
            inner = 84 + f.datacomp + f.rsrccomp;
            if (datasize != inner && datasize != inner + 84)
                return UNC_ERR_CORRUPT;
            dd_entry_from(&e, &f);
            if ((err = dd_emit(c, &e, &f, start + 84)) != UNC_OK) return err;
            at = start + datasize;
        }
    }
    return UNC_OK;
}

/* ---- 'DDA2' ------------------------------------------------------- */

static int dd_archive2(UncCtx *c)
{
    UncPath path;
    uint8_t hdr[96];
    int sawend = 0;        /* the 0xBBBB record: this archive's own end */
    uint32_t at = 62;      /* 'DDA2' + 58 header bytes */
    int lastlevel = 0, err;

    unc_path_init(&path, c);

    for (;;) {
        uint32_t start = at, totalsize, nlen;
        int entrytype, dirlevel, sret;
        UncEntryInfo e;
        unc_off_t fsize = c->io->size(c->io->ctx);

        if (c->io->seek(c->io->ctx, at) < 0) return UNC_ERR_IO;
        if (unc_read_full(c->io, hdr, 46) != UNC_OK) {
            /* A record that will not read is the end of the archive only
             * in one shape: the walk arrived INSIDE the file with less
             * than a record left over. `derived-DD_Expand.sea` ends
             * exactly so — 38 bytes after its last entry, no end marker
             * — and `unar` reads it, so this is a real archive's ending
             * and not a cut one. Being sent PAST the end is different:
             * a record said the next one begins where the file no
             * longer goes, which is a download that stopped
             * (2026-08-29). */
            if ((unc_off_t)at <= fsize && fsize - (unc_off_t)at < 46)
                sawend = 1;
            break;
        }
        if (unc_get_u32be(hdr) != DD_DDA2) break;

        entrytype = (int)unc_get_u16be(hdr + 4);
        if (entrytype == 0xBBBB) { sawend = 1; break; }   /* end marker */
        nlen = hdr[6];
        if (nlen > 31) nlen = 31;
        dirlevel  = (int)unc_get_u32be(hdr + 38) - 2;
        totalsize = unc_get_u32be(hdr + 42);
        if (totalsize == 0) break;

        if (dirlevel < 0) { at = start + totalsize; continue; }

        while (lastlevel > dirlevel) { unc_path_pop(&path); lastlevel--; }
        lastlevel = dirlevel;

        unc_entry_clear(&e);

        if (entrytype & 0x8000) {
            /* A folder: it deepens the path but does NOT deepen the
             * level counter, which is what the level arithmetic above
             * is written against — read the other way the tree inverts
             * on the first nested folder, and the 19 folders here are
             * what says which.
             * Source: docs/formats/diskdoubler-container.md, "DDA2". */
            if (unc_read_full(c->io, hdr + 46, 16) != UNC_OK) break;
            unc_path_leaf(&path, &e, hdr + 7, nlen);   /* before the push */
            if ((err = unc_path_push(&path, hdr + 7, nlen)) != UNC_OK) return err;
            e.is_dir = 1;
            e.create_date = unc_get_u32be(hdr + 54);
            e.mod_date    = unc_get_u32be(hdr + 58);
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) return UNC_ERR_SINK;
            if (sret == 0 && c->sink->end_entry(c->sink->ctx, UNC_OK) < 0)
                return UNC_ERR_SINK;
            at = start + totalsize;
            continue;
        }

        unc_path_leaf(&path, &e, hdr + 7, nlen);

        if ((entrytype & 0xF000) == 0x1000) {
            /* Stored in the archive with no file header of its own.
             * DiskDoubler Pro writes it when the data fork is stored
             * AND the file has no resource fork — both halves measured
             * on the application, 2026-08-21 (DECISIONS.md, the
             * Symantec release); a file with a resource fork gets a
             * full header even when its data fork is stored. The
             * record carries the file's own metadata instead, and the
             * 90-byte header is followed by the two raw forks. The
             * reference has no branch for this and raises on the
             * missing 0xABCD0054, which is why `unar` calls every
             * DiskDoubler Pro archive holding an incompressible
             * fork-less file corrupt. Derived from the nine archives of
             * ssokolow/diskdoubler-test-files (DECISIONS.md 2026-08-21). */
            DdFile f;
            uint8_t *fp = (uint8_t *)&f;
            uint32_t fi;
            if (unc_read_full(c->io, hdr + 46, 44) != UNC_OK) break;
            for (fi = 0; fi < sizeof f; fi++) fp[fi] = 0;
            /* MEASURED 2026-08-21: two subjects stamped with a 1990
             * creation and a 1995 modification came back with 1990 at
             * +54 in both records (`tools/vmac/ndd.py --dates`). Until
             * then every specimen carried the same value twice and this
             * was the reference's order in the folder branch of the
             * same walk, taken on faith. */
            f.creation     = unc_get_u32be(hdr + 54);
            f.modification = unc_get_u32be(hdr + 58);
            f.type         = unc_get_u32be(hdr + 62);
            f.creator      = unc_get_u32be(hdr + 66);
            f.finderflags  = (int)unc_get_u16be(hdr + 70);
            f.datasize = f.datacomp = unc_get_u32be(hdr + 78);
            f.rsrcsize = f.rsrccomp = unc_get_u32be(hdr + 82);
            f.datacrc  = hdr[86];
            /* +87 sits where the resource fork's checksum would go and
             * is 0 in all 33 records seen. It has never described
             * anything: this record type is only written for a file
             * with no resource fork, so rsrcsize above is always 0 and
             * this value is never compared. */
            f.rsrccrc  = hdr[87];
            f.xorsum   = 1;
            dd_entry_from(&e, &f);
            if ((err = dd_emit(c, &e, &f, start + 90)) != UNC_OK) return err;
            at = start + totalsize;
            continue;
        }

        if (c->io->seek(c->io->ctx, start + 56) < 0) return UNC_ERR_IO;
        if (unc_read_full(c->io, hdr, 4) != UNC_OK) break;
        if (unc_get_u32be(hdr) != DD_MAGIC) return UNC_ERR_CORRUPT;
        if (unc_read_full(c->io, hdr, DD_FILEHDR) != UNC_OK) break;
        {
            DdFile f;
            dd_parse_filehdr(hdr, &f);
            dd_entry_from(&e, &f);
            if ((err = dd_emit(c, &e, &f, start + 56 + 84)) != UNC_OK) return err;
        }
        at = start + totalsize;
    }
    /* A DDA2 archive normally says where it ends. A walk that fell out
     * of the loop without that marker AND without running out of file
     * ran off something that stops early — a record whose magic is not
     * there, a length of zero, a header that reads short in the middle
     * of the file. Every one of those returned success until
     * 2026-08-29 and took the entries beyond the cut with it, silently
     * (BLOCKERS.md).
     *
     * WHAT THIS STILL CANNOT SEE: an archive cut so that the last whole
     * record lands within 46 bytes of the new end. That is
     * byte-for-byte the shape of the marker-less ending above, and
     * nothing in the format tells them apart — measured on
     * `ddtf-ddpro411dd3.dd` cut to a fifth (TESTING.md). */
    return sawend ? UNC_OK : UNC_ERR_TRUNCATED;
}

/* ------------------------------------------------------------------ */

int unc_dd_extract(UncCtx *c)
{
    uint8_t hdr[DD_FILEHDR];
    uint32_t magic;

    if (c->io->seek(c->io->ctx, 0) < 0) return UNC_ERR_IO;
    if (unc_read_full(c->io, hdr, 4) != UNC_OK) return UNC_ERR_FORMAT;
    magic = unc_get_u32be(hdr);

    if (magic == DD_DDAR) return dd_archive(c);
    if (magic == DD_DDA2) return dd_archive2(c);
    if (magic != DD_MAGIC) return UNC_ERR_FORMAT;

    /* A single compressed file carries no name of its own: DiskDoubler
     * appended ".dd" to the original, so the host's name (minus that
     * suffix) is the name. The container says nothing about it
     * (docs/formats/diskdoubler-container.md, "A compressed file") and
     * the oracle agrees on all 66 of them, which is what grades this. */
    if (unc_read_full(c->io, hdr, DD_FILEHDR) != UNC_OK) return UNC_ERR_TRUNCATED;
    {
        DdFile f;
        UncEntryInfo e;
        dd_parse_filehdr(hdr, &f);
        unc_entry_clear(&e);
        if (c->opt.name_hint && c->opt.name_hint_len) {
            uint16_t n = c->opt.name_hint_len;
            if (n > 3 && c->opt.name_hint[n - 3] == '.' &&
                (c->opt.name_hint[n - 2] | 0x20) == 'd' &&
                (c->opt.name_hint[n - 1] | 0x20) == 'd')
                n = (uint16_t)(n - 3);
            unc_entry_set_path(&e, c->opt.name_hint, n);
        } else {
            unc_entry_set_name(&e, (const uint8_t *)"diskdoubler", 11);
        }
        dd_entry_from(&e, &f);
        return dd_emit(c, &e, &f, 84);
    }
}

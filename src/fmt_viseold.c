/*
 * fmt_viseold.c — MindVision's VISE before Installer VISE 3.5: the 'VISE'
 * archive, an installer's data fork or a `.vct` file beside an Apple
 * Installer script, 1992 to 1996.
 *
 * The whole file:
 *
 *   +0   'VISE'
 *   +4   u32  a Macintosh date
 *   +8   u32  0x04000004
 *   +12  u32  the stream's length
 *   +20  u32  where the catalogue is: always +12 plus 24
 *   +24  ONE stream: every fork of every file, back to back
 *   then the catalogue: u16 the record count, u16 0, 80-byte records
 *
 * A record: +0 its kind, 0x80 a folder opening, 0xC0 the folder last
 * opened closing (the rest of that record is whatever the one before it
 * held), 0x33 a file; +1 0x10 in a folder's, 0x00 or 0x02 in a file's;
 * +2 a file's type and +6 its creator (a folder's window rectangle); +10
 * the Finder flags; +18 created, +22 modified (Macintosh dates); +26 the
 * resource fork's length and +34 the data fork's, the resource fork first
 * in the stream; +48 the name, a Str31.
 *
 * The stream: u32 big-endian, the bytes it expands to, which is the sum of
 * every file's two lengths; a byte whose bits 2-3 plus 13 are the window's
 * bits (its bits 0-1 are read and not used); three trees, the literals',
 * the match lengths' and a distance's high byte, each stored as a count
 * byte and that many bytes of which each gives (b >> 5) + 1 symbols in a
 * row the bit length b & 31; then the tokens, bits from the low end of each
 * byte. A 1 bit is a literal; a 0 bit is a match: (window bits - 8) raw
 * bits of distance, the distance tree's symbol above them, the length
 * tree's; the copy starts (raw + (symbol << (bits - 8)) + 3) bytes back and
 * is (length + 3) bytes long. The codes are Shannon-Fano codes like
 * Implode's, but in the order an unstable quicksort leaves the 256 lengths:
 * the last symbol of the sorted list, the longest, gets the code of all
 * zeros, and each one before it the code after its successor's, counted at
 * its own length; the first bit read is the one nearest the root.
 *
 * Sources. Nothing published describes this format. The stream is read
 * out of the decompressor itself, the 'Dcmp' 2002 resource of CompuServe
 * Mail Installer (1995): 0x2b6c decodes, 0xc3e reads a tree's lengths,
 * 0x924 and 0x8cc assign the codes, 0x7cc is the quicksort (copied below
 * step for step, because the order it leaves equal lengths in is what the
 * codes are: a stable sort decodes none of the specimens), 0x9f0 builds
 * the tree. The header and the catalogue are MEASURED on eight archives of
 * 1992-1995 (DECISIONS.md 2026-11-12, *the VISE before VISE*): each stream
 * ends at its catalogue to the byte, and expands to the sum of its
 * records' lengths. There is no checksum, so that end is the one check the
 * format allows, and it is the last file's.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_vise_priv.h"

#define VO_EMPTY  0xFFFFu
#define VO_LEAF   0x8000u
#define VO_DEPTH  32u

/* One tree: node n's children, for a 0 and a 1 bit; a child is another
 * node, VO_LEAF | a symbol, or VO_EMPTY. Node 0 is the root. */
typedef struct VoTree {
    uint16_t kid[2][256];
} VoTree;

typedef struct VoDec {
    UncBufIn in;
    UncBitIn bi;
    VoTree   t[3];               /* literals, lengths, distances       */
    uint8_t *win;
    uint32_t mask;
    uint32_t pos;                /* bytes produced so far              */
    uint32_t mlen, mdist;        /* what is left of a match            */
    int      lowb;
    int      err;                /* sticky                             */
    uint32_t code[256];
    uint8_t  len[256];
    uint8_t  idx[256];
    uint8_t  ibuf[UNC_IOBUF];
} VoDec;

/* 0x7cc: sort(lo, hi) over idx[lo..hi-1] by length, as the 68k does it,
 * the recursion kept on a stack of the ranges still to sort. */
static void vo_qsort(VoDec *d)
{
    int16_t st[2 * 16];
    int sp = 0;
    st[sp++] = 0;
    st[sp++] = 256;
    while (sp) {
        int16_t hi = st[--sp], lo = st[--sp];
        int16_t i = lo, j = (int16_t)(hi - 1);
        uint8_t piv = d->len[d->idx[(hi + lo - 1) / 2]];
        do {
            while (d->len[d->idx[i]] < piv) i++;
            while (d->len[d->idx[j]] > piv) j--;
            if (j >= i) {
                uint8_t t = d->idx[i];
                d->idx[i] = d->idx[j];
                d->idx[j] = t;
                i++;
                j--;
            }
        } while (j >= i);
        /* The two ranges are disjoint, so their order is free: the
         * smaller is pushed last and sorted first, which keeps the stack
         * within log2(256) + 1 ranges. */
        if (j - lo > hi - i) {
            if (j > lo) { st[sp++] = lo; st[sp++] = (int16_t)(j + 1); }
            if (hi > i) { st[sp++] = i;  st[sp++] = hi; }
        } else {
            if (hi > i) { st[sp++] = i;  st[sp++] = hi; }
            if (j > lo) { st[sp++] = lo; st[sp++] = (int16_t)(j + 1); }
        }
    }
}

/* 0xc3e, 0x924, 0x8cc and 0x9f0: one tree's lengths, then its codes, then
 * the tree. A code's bit k - 1 is the branch taken at depth k. */
static int vo_tree(VoDec *d, VoTree *t)
{
    uint32_t *code = d->code;
    uint32_t cur = 0, n, s, k, nnodes = 1;
    int i, b = unc_bufin_next(&d->in), depth = 32;

    if (b < 0) return d->in.err;
    for (n = (uint32_t)b, s = 0; n; n--) {
        int v = unc_bufin_next(&d->in);
        uint32_t run;
        if (v < 0) return d->in.err;
        for (run = ((uint32_t)v >> 5) + 1u; run; run--) {
            if (s == 256) return UNC_ERR_CORRUPT;
            d->len[s++] = (uint8_t)(v & 31);
        }
    }
    while (s < 256) d->len[s++] = 0;

    for (s = 0; s < 256; s++) d->idx[s] = (uint8_t)s;
    vo_qsort(d);
    for (i = 255; i >= 0 && d->len[d->idx[i]]; i--) {
        uint32_t l = d->len[d->idx[i]];
        if ((int)l < depth) depth = (int)l;
        code[d->idx[i]] = cur;
        for (k = (uint32_t)depth; k && (cur >> (k - 1)) & 1u; k--)
            cur &= ~((uint32_t)1 << (k - 1));
        if (k) cur |= (uint32_t)1 << (k - 1);
    }

    for (s = 0; s < 256; s++) t->kid[0][s] = t->kid[1][s] = VO_EMPTY;
    for (s = 0; s < 256; s++) {
        uint32_t l = d->len[s], node = 0;
        if (!l) continue;
        for (k = 1; k < l; k++) {
            uint16_t *c = &t->kid[(code[s] >> (k - 1)) & 1u][node];
            if (*c == VO_EMPTY) {
                if (nnodes == 256) return UNC_ERR_CORRUPT;
                *c = (uint16_t)nnodes++;
            } else if (*c & VO_LEAF) {
                return UNC_ERR_CORRUPT;
            }
            node = *c;
        }
        {
            uint16_t *c = &t->kid[(code[s] >> (l - 1)) & 1u][node];
            if (*c != VO_EMPTY) return UNC_ERR_CORRUPT;
            *c = (uint16_t)(VO_LEAF | s);
        }
    }
    return UNC_OK;
}

static int vo_sym(VoDec *d, const VoTree *t)
{
    uint32_t node = 0;
    for (;;) {
        int b = unc_bitin_bit(&d->bi);
        uint16_t c;
        if (b < 0) return -1;
        c = t->kid[b][node];
        if (c == VO_EMPTY) { d->bi.err = UNC_ERR_CORRUPT; return -1; }
        if (c & VO_LEAF) return (int)(c & 0xFFu);
        node = c;
    }
}

/* The stream's head: its expanded length, which must be `total`, the
 * window, and the trees. */
static int vo_open(VoDec *d, UncCtx *c, uint32_t clen, uint32_t total)
{
    uint8_t h[5];
    uint32_t need = 512u, win;
    int i, err;

    unc_bufin_init(&d->in, c->io, &c->ps, d->ibuf, UNC_IOBUF);
    d->in.limit = clen;
    for (i = 0; i < 5; i++) {
        int v = unc_bufin_next(&d->in);
        if (v < 0) return d->in.err;
        h[i] = (uint8_t)v;
    }
    if (unc_get_u32be(h) != total) return UNC_ERR_CORRUPT;
    d->lowb = (int)((h[4] >> 2) & 3u) + 5;
    win = (uint32_t)1 << (d->lowb + 8);
    /* No match reaches past the start, so a window larger than all there
     * is to produce is never read. */
    while (need < total && need < win) need <<= 1;
    d->win = (uint8_t *)unc_alloc(c->al, need);
    if (!d->win) return UNC_ERR_MEM;
    d->mask = need - 1u;
    for (i = 0; i < 3; i++)
        if ((err = vo_tree(d, &d->t[i])) != UNC_OK) return err;
    unc_bitin_init_le(&d->bi, &d->in);
    d->pos = d->mlen = 0;
    return UNC_OK;
}

/* What is in the window since `*mark`, out to `fork`. Called at every
 * turn of the window, so what is pending never wraps and is never
 * overwritten before it is out. */
static int vo_flush(VoDec *d, UncCtx *c, UncFork fork, int out,
                    uint32_t *mark)
{
    uint32_t k = d->pos - *mark;
    if (out && k && !c->opt.test_only &&
        c->sink->write(c->sink->ctx, fork, d->win + (*mark & d->mask),
                       (int32_t)k) < 0)
        return UNC_ERR_SINK;
    *mark = d->pos;
    return UNC_OK;
}

/* `n` more bytes to `fork`, or nowhere when `out` is 0. A match may run
 * on into the next fork or the next file: the stream is one. */
static int vo_produce(VoDec *d, UncCtx *c, UncFork fork, int out, uint32_t n)
{
    uint32_t mark = d->pos;
    int err = UNC_OK;

    while (n) {
        uint8_t v;
        if (d->mlen) {
            v = d->win[(d->pos - d->mdist) & d->mask];
            d->mlen--;
        } else {
            int b = unc_bitin_bit(&d->bi), s;
            if (b < 0) { err = d->bi.err; break; }
            if (b) {
                if ((s = vo_sym(d, &d->t[0])) < 0) { err = d->bi.err; break; }
                v = (uint8_t)s;
            } else {
                int32_t low = unc_bitin_bits_le(&d->bi, d->lowb);
                int hi, l;
                if (low < 0 || (hi = vo_sym(d, &d->t[2])) < 0 ||
                    (l = vo_sym(d, &d->t[1])) < 0) {
                    err = d->bi.err;
                    break;
                }
                d->mdist = (uint32_t)low + ((uint32_t)hi << d->lowb) + 3u;
                if (d->mdist > d->pos || d->mdist > d->mask + 1u) {
                    err = UNC_ERR_CORRUPT;
                    break;
                }
                d->mlen = (uint32_t)l + 3u;
                continue;
            }
        }
        d->win[d->pos++ & d->mask] = v;
        n--;
        if (!(d->pos & d->mask) &&
            (err = vo_flush(d, c, fork, out, &mark)) != UNC_OK)
            return err;
    }
    if (err == UNC_OK) err = vo_flush(d, c, fork, out, &mark);
    else if (err != UNC_ERR_SINK) d->err = err;
    return err;
}

static int vo_seek(UncCtx *c, uint32_t off)
{
    if (c->segmap) return c->segmap->seek_part(c->segmap->ctx, 1, off) < 0
                          ? UNC_ERR_IO : UNC_OK;
    return c->io->seek(c->io->ctx, off) < 0 ? UNC_ERR_IO : UNC_OK;
}

int unc_viseold_extract(UncCtx *c, const uint8_t *h)
{
    uint32_t clen = unc_get_u32be(h + VISEO_H_LEN),
             cat = unc_get_u32be(h + VISEO_H_CAT);
    uint8_t ch[4], *rec = NULL;
    uint16_t up[VO_DEPTH];
    uint32_t n, k, total = 0, last = 0, depth, owed, before = c->ps.done;
    VoDec *d = NULL;
    int err, derr = UNC_OK;

    if ((err = vo_seek(c, cat)) != UNC_OK) return err;
    if (unc_read_full(c->io, ch, 4) != UNC_OK) return UNC_ERR_TRUNCATED;
    n = unc_get_u16be(ch);
    if (!n || unc_get_u16be(ch + 2)) return UNC_ERR_FORMAT;
    rec = (uint8_t *)unc_alloc(c->al, n * VISEO_REC);
    if (!rec) return UNC_ERR_MEM;
    if (unc_read_full(c->io, rec, (int32_t)(n * VISEO_REC)) != UNC_OK) {
        err = UNC_ERR_TRUNCATED;
        goto out;
    }

    /* The records are the archive: they must nest, and their forks must
     * add up to what the stream says it holds. */
    for (k = 0, depth = 0; k < n; k++) {
        const uint8_t *r = rec + k * VISEO_REC;
        if (r[0] == VISEO_DIR) {
            if (++depth > VO_DEPTH) { err = UNC_ERR_CORRUPT; goto out; }
        } else if (r[0] == VISEO_END) {
            if (!depth--) { err = UNC_ERR_CORRUPT; goto out; }
        } else if (r[0] == VISEO_FILE) {
            uint32_t rl = unc_get_u32be(r + 26), dl = unc_get_u32be(r + 34);
            if (rl > UNC_MAC_MAX || dl > UNC_MAC_MAX ||
                total > UNC_MAC_MAX - rl || total + rl > UNC_MAC_MAX - dl) {
                err = UNC_ERR_TOOLARGE;
                goto out;
            }
            total += rl + dl;
            if (rl + dl) last = k;
        } else {
            err = UNC_ERR_CORRUPT;
            goto out;
        }
        if (r[48] > 31) { err = UNC_ERR_CORRUPT; goto out; }
    }
    if ((err = unc_progress_add(&c->ps, VISEO_HDR + 4u + n * VISEO_REC))
        != UNC_OK)
        goto out;

    /* One stream, opened once; a file that cannot be had makes every one
     * after it unreachable too, and each is told so. */
    if (!c->opt.list_only && total) {
        d = (VoDec *)unc_alloc(c->al, (uint32_t)sizeof(VoDec));
        if (!d) derr = UNC_ERR_MEM;
        else {
            d->win = NULL;
            d->err = UNC_OK;
            if ((derr = vo_seek(c, VISEO_HDR)) == UNC_OK)
                derr = vo_open(d, c, clen, total);
            if (derr == UNC_ERR_ABORTED) goto fatal;
        }
    }

    for (k = 0, depth = 0; k < n; k++) {
        const uint8_t *r = rec + k * VISEO_REC;
        UncEntryInfo e;
        uint32_t q, rl = 0, dl = 0;
        int sret, est = UNC_OK;

        if (r[0] == VISEO_END) { depth--; continue; }
        unc_entry_clear(&e);
        for (q = 0; q < depth; q++) {
            const uint8_t *f = rec + up[q] * VISEO_REC;
            unc_entry_path_append(&e, f + 49, f[48]);
        }
        unc_entry_path_append(&e, r + 49, r[48]);
        e.finder_flags = unc_get_u16be(r + 10);
        e.create_date = unc_get_u32be(r + 18);
        e.mod_date = unc_get_u32be(r + 22);
        if (r[0] == VISEO_DIR) {
            up[depth++] = (uint16_t)k;
            e.is_dir = 1;
            e.data_size = e.rsrc_size = 0;
        } else {
            rl = unc_get_u32be(r + 26);
            dl = unc_get_u32be(r + 34);
            e.type = unc_get_u32be(r + 2);
            e.creator = unc_get_u32be(r + 6);
            e.rsrc_size = rl;
            e.data_size = dl;
            e.comp_data_size = e.comp_rsrc_size = UNC_SIZE_UNKNOWN;
        }
        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; goto out; }
        if (r[0] == VISEO_DIR || c->opt.list_only) {
            if (sret == 0 &&
                c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
            continue;
        }
        /* Solid: a file passed over is still decoded, to nowhere. An
         * archive of empty files has no stream to open. */
        if (!total) est = UNC_OK;
        else if (!d || derr != UNC_OK) est = derr ? derr : UNC_ERR_MEM;
        else if (d->err != UNC_OK) est = d->err;
        else {
            est = vo_produce(d, c, UNC_FORK_RSRC, sret == 0, rl);
            if (est == UNC_OK)
                est = vo_produce(d, c, UNC_FORK_DATA, sret == 0, dl);
            /* The last file's stream ends at the catalogue, to the byte:
             * the one check the format allows. */
            if (est == UNC_OK && k == last) {
                unc_bitin_align(&d->bi);
                if (unc_bitin_bytepos(&d->bi) != clen) est = UNC_ERR_CORRUPT;
            }
            if (est == UNC_ERR_SINK || est == UNC_ERR_ABORTED) {
                err = est;
                goto out;
            }
        }
        if (sret == 0 && c->sink->end_entry(c->sink->ctx, est) < 0) {
            err = UNC_ERR_SINK;
            goto out;
        }
    }
    /* What was not read (a listing, a stream given up) is still done. */
    owed = VISEO_HDR + 4u + n * VISEO_REC + clen;
    if (c->ps.done - before < owed)
        err = unc_progress_add(&c->ps, owed - (c->ps.done - before));
    goto out;
fatal:
    err = derr;
out:
    if (d) {
        if (d->win) unc_free(c->al, d->win);
        unc_free(c->al, d);
    }
    unc_free(c->al, rec);
    return err;
}

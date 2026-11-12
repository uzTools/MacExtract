/*
 * fmt_vise.c — Installer VISE 3.x, MindVision's installer, as an archive.
 *
 * An installer built by Installer VISE 3.5 and later keeps everything it
 * installs in its DATA fork (the resource fork is the installer program,
 * which nothing here reads), as a set of one or more SEGMENTS: the first
 * is the installer itself, the rest files called "Segment.N" on further
 * disks. Every segment opens with a 44-byte header:
 *
 *   +0   'SVCT'
 *   +4   u32  this segment's number, 1-based
 *   +12  u32  the same in every segment of one set
 *   +16  u32  the archive version (below)
 *   +20  u32  segment 1: how many segments the set has; 0 in the others
 *   +36  u32  segment 1: where the catalogue is; 0 in the others
 *
 * and its PAYLOAD runs from +44 to the catalogue (segment 1) or to the end
 * of the file (every other). A file's stream may start in one segment and
 * go on at +44 of the next.
 *
 * The catalogue: 'CVCT', u32 at +4, u32 at +8 non-zero when what follows is
 * compressed, u16 at +16 the record count, then the records. In the later
 * versions the records are behind an 80-byte prefix that opens 'PACK', and
 * +4 is the length of what follows the prefix (compressed or not); in the
 * earlier ones +4 is the length of the records themselves.
 *
 * Each record is 'DVCT' (a folder) or 'FVCT' (a file) and a body: 78 fixed
 * bytes for a folder, 120 for a file, a suffix whose length the version
 * sets (fmt_vise_priv.h), and the name, whose length is the byte at +76 of
 * a folder and +118 of a file. Some records carry more after the name (the
 * text of an installer's search-and-alert actions, an alias), so a record
 * ends where the next one's signature begins. Of the body:
 *
 *   folder  +16 created, +20 modified (Macintosh dates); +68 u16 its
 *           parent, as a DEPTH: 0 the root, d the last folder opened at
 *           depth d - 1
 *   file    +8 bit 0x10: the forks are slices of a SHARED block;
 *           +40 type, +44 creator, +48 u16 Finder flags, +56 created,
 *           +60 modified; +64 u32 the data fork's stream length, or the
 *           shared block's; +68 the data fork's length; +72 the resource
 *           fork's stream length, or the block's expanded length; +76 the
 *           resource fork's length; +80 the CRC-32 of the data fork
 *           followed by the resource fork; +92 u16 its parent (a depth);
 *           +94 u16 the segment its stream starts in, 0 for a record that
 *           is not stored in the archive at all; +96 u32 where, in that
 *           segment; +100 and +104 a shared file's data and resource
 *           slices in the block's expanded bytes
 *
 * A fork that is not shared is its own stream: the data fork's at +96, the
 * resource fork's straight after it.
 *
 * Every stream is a raw DEFLATE stream (RFC 1951) as Installer VISE's own
 * 'Dcmp' reads it: in 16-bit big-endian words, bits from the low end of
 * each, which is DEFLATE with every pair of bytes swapped; a stored block
 * aligned to 16 bits rather than to a byte, and an odd stored length padded
 * to the next word; no fixed-Huffman block. A file's streams, and not the
 * catalogue's, are also passed through a fixed 256-byte substitution before
 * the swap is undone.
 *
 * Sources. The header's +16 and +36, the catalogue's count, the fixed
 * offsets of the records' fields but the folder dates and +8, the
 * substitution table and the pair swap are ScummVM's
 * common/compression/vise.cpp (GPL-3.0-or-later, read for these facts
 * only; nothing here is transcribed from it). The word-oriented reading of
 * the stream, the stored block's alignment and padding, the shared blocks
 * and their slices, the CRC-32 at +80 and the 'PACK' prefix's length are
 * mrmidi/installer-vise's docs (MIT). The record suffixes, the parent as a
 * depth, and +94 as the segment, are systemless's vise.rs (licence not
 * stated, read for facts only). EVERYTHING ELSE IS MEASURED on 29
 * installers of every version here, the three segments of one set and the
 * Myth demo's installer (DECISIONS.md 2026-11-11, *the installer that was
 * an archive*): the count at +20 and the stamp at +12; +8 of the
 * catalogue as the compression flag; +4 as the length past the prefix;
 * the suffixes of 0x80010301, 0x80010302, 0x80010303 and 0x8001030C, which
 * no outside reader has; the depth in every version, 3.5 included, where
 * ScummVM reads an index and files land in a sibling folder; and the
 * segment payload's end at the catalogue, which puts the two streams that
 * cross a disk in the set back together. Every one of 456 stored files
 * matches its own CRC-32.
 *
 * A record in segment 0 is not in the archive (an action, a file the
 * installer fetches or finds elsewhere) and is passed over; a folder that
 * holds nothing that is comes out of nothing either.
 *
 * Read through the set's map (unc_segment.c, ADDRESSED), an installer of
 * one segment as a set of one; or, given no map, as that installer alone. The catalogue is read into memory, then
 * the files come out in the order of their bytes, so that a shared block
 * is decoded once and a set's disks are wanted in order.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_vise_priv.h"

#define VISE_WINMAX   32768u
#define VISE_DEPTHMAX 128u
#define VISE_ROOT     0xFFFFu
#define VISE_CATMAX   (8ul << 20)    /* a catalogue past this is not one */

/* Source: ScummVM, common/compression/vise.cpp, vl3DeobfuscationTable. */
static const uint8_t vise_subst[256] = {
    0x6a, 0xb7, 0x36, 0xec, 0x15, 0xd9, 0xc8, 0x73, 0xe8, 0x38, 0x9a, 0xdf, 0x21, 0x25, 0xd0, 0xcc,
    0xfd, 0xdc, 0x16, 0xd7, 0xe3, 0x43, 0x05, 0xc5, 0x8f, 0x48, 0xda, 0xf2, 0x3f, 0x10, 0x23, 0x6c,
    0x77, 0x7c, 0xf9, 0xa0, 0xa3, 0xe9, 0xed, 0x46, 0x8b, 0xd8, 0xac, 0x54, 0xce, 0x2d, 0x19, 0x5e,
    0x6d, 0x7d, 0x87, 0x5d, 0xfa, 0x5b, 0x9b, 0xe0, 0xc7, 0xee, 0x9f, 0x52, 0xa9, 0xb9, 0x0a, 0xd1,
    0xfe, 0x78, 0x76, 0x4a, 0x3d, 0x44, 0x5a, 0x96, 0x90, 0x1f, 0x26, 0x9d, 0x58, 0x1b, 0x8e, 0x57,
    0x59, 0xc3, 0x0b, 0x6b, 0xfc, 0x1d, 0xe6, 0xa2, 0x7f, 0x92, 0x4f, 0x40, 0xb4, 0x06, 0x72, 0x4d,
    0xf4, 0x34, 0xaa, 0xd2, 0x49, 0xad, 0xef, 0x22, 0x1a, 0xb5, 0xba, 0xbf, 0x29, 0x68, 0x89, 0x93,
    0x3e, 0x32, 0x04, 0xf5, 0xde, 0xe1, 0x6f, 0xfb, 0x67, 0xe4, 0x7e, 0x08, 0xaf, 0xf0, 0xab, 0x41,
    0x82, 0xea, 0x50, 0x0f, 0x2a, 0xc6, 0x35, 0xb3, 0xa8, 0xca, 0xe5, 0x4c, 0x45, 0x8a, 0x97, 0xae,
    0xd6, 0x66, 0x27, 0x53, 0xc9, 0x1c, 0x3c, 0x03, 0x99, 0xc1, 0x09, 0x2e, 0x69, 0x37, 0x8d, 0x2f,
    0x60, 0xc2, 0xa6, 0x18, 0x4e, 0x7a, 0xb8, 0xcf, 0xa7, 0x3a, 0x17, 0xd5, 0x9e, 0xf1, 0x84, 0x51,
    0x0d, 0xa4, 0x64, 0xc4, 0x1e, 0xb1, 0x30, 0x98, 0xbb, 0x79, 0x01, 0xf6, 0x62, 0x0e, 0xb2, 0x63,
    0x91, 0xcb, 0xff, 0x80, 0x71, 0xe7, 0xd4, 0x00, 0xdb, 0x75, 0x2c, 0xbd, 0x39, 0x33, 0x94, 0xbc,
    0x8c, 0x3b, 0xb6, 0x20, 0x85, 0x24, 0x88, 0x2b, 0x70, 0x83, 0x6e, 0x7b, 0x9c, 0xbe, 0x14, 0x47,
    0x65, 0x4b, 0x56, 0x81, 0xf8, 0x12, 0x11, 0x28, 0xeb, 0x55, 0x74, 0xa1, 0x31, 0xf7, 0xb0, 0x13,
    0x86, 0xdd, 0x5f, 0x42, 0xd3, 0x02, 0x61, 0x95, 0x0c, 0x5c, 0xa5, 0xcd, 0xc0, 0x07, 0xe2, 0xf3,
};

/* Source: RFC 1951 section 3.2.5 (reference/notes/rfc1951.txt). */
static const uint16_t vise_lbase[29] = {
    3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31,
    35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258 };
static const uint8_t vise_lext[29] = {
    0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2,
    3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0 };
static const uint16_t vise_dbase[30] = {
    1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193,
    257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289,
    16385, 24577 };
static const uint8_t vise_dext[30] = {
    0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6,
    7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13 };
/* Source: RFC 1951 section 3.2.7, the code length code's order. */
static const uint8_t vise_clord[19] = {
    16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15 };

/* ------------------------------------------------------------------ */
/* A stream's bytes: an UncIO over (segment, offset)                  */
/* ------------------------------------------------------------------ */

typedef struct ViseSrc {
    UncCtx  *c;
    uint32_t cat;               /* segment 1's payload end            */
    uint32_t part, off, end;    /* where the next byte is, and where  *
                                 * this segment's payload ends        */
    uint32_t left;              /* bytes of the stream still to give  */
    int      subst;
    int      err;               /* why the bytes stopped, when a next  *
                                 * segment could not be had            */
    /* Where the bytes read are credited: the progress state the first
     * time a stream is read, NULL when it is read again. */
    UncProgressState *ps;
    uint32_t credited;
} ViseSrc;

static int vise_seek(ViseSrc *s, uint32_t part, uint32_t off)
{
    const UncSegMap *m = s->c->segmap;
    uint32_t end;

    if (part == 1) {
        end = s->cat;
    } else {
        if (!m || part > m->nparts) return UNC_ERR_SEGMENTED;
        end = m->part_size(m->ctx, (int)part);
        if (end == UNC_SIZE_UNKNOWN) return UNC_ERR_SEGMENTED;
    }
    if (off < VISE_HDR || off > end) return UNC_ERR_CORRUPT;
    if (m) {
        if (m->seek_part(m->ctx, (int)part, off) < 0) return UNC_ERR_SEGMENTED;
    } else if (s->c->io->seek(s->c->io->ctx, off) < 0) {
        return UNC_ERR_IO;
    }
    s->part = part;
    s->off = off;
    s->end = end;
    return UNC_OK;
}

/* Step `n` bytes on from (*part, *off) through the payload, across the
 * segments it runs into: where a stream that follows one `n` long begins. */
static int vise_advance(ViseSrc *s, uint32_t *part, uint32_t *off,
                        uint32_t n)
{
    const UncSegMap *m = s->c->segmap;
    for (;;) {
        uint32_t end;
        if (*part == 1) {
            end = s->cat;
        } else {
            if (!m || *part > m->nparts) return UNC_ERR_SEGMENTED;
            end = m->part_size(m->ctx, (int)*part);
            if (end == UNC_SIZE_UNKNOWN) return UNC_ERR_SEGMENTED;
        }
        if (*off > end) return UNC_ERR_CORRUPT;
        if (n < end - *off || (n == end - *off && n == 0)) {
            *off += n;
            return UNC_OK;
        }
        n -= end - *off;
        if (n == 0 && (!m || *part >= m->nparts)) {
            *off = end;
            return UNC_OK;
        }
        (*part)++;
        *off = VISE_HDR;
    }
}

/* UncIO.read: up to `len` bytes of the stream, an even count except at its
 * end, so that every pair the writer swapped is turned back whole. */
static int32_t vise_src_read(void *ctx, void *buf, int32_t len)
{
    ViseSrc *s = (ViseSrc *)ctx;
    uint8_t *p = (uint8_t *)buf;
    uint32_t got = 0, want = (uint32_t)len & ~1u, i;

    if (want == 0) return 0;
    while (got < want && s->left) {
        uint32_t k;
        int32_t r;
        if (s->off >= s->end) {
            int err = vise_seek(s, s->part + 1, VISE_HDR);
            if (err != UNC_OK) {
                s->err = err;
                return err == UNC_ERR_IO ? -1 : 0;
            }
            continue;
        }
        k = want - got;
        if (k > s->left) k = s->left;
        if (k > s->end - s->off) k = s->end - s->off;
        r = s->c->io->read(s->c->io->ctx, p + got, (int32_t)k);
        if (r < 0) return -1;
        if (r == 0) break;
        got += (uint32_t)r;
        s->off += (uint32_t)r;
        s->left -= (uint32_t)r;
        if (s->ps) {
            int err = unc_progress_add(s->ps, (uint32_t)r);
            s->credited += (uint32_t)r;
            if (err != UNC_OK) { s->err = err; return -1; }
        }
    }
    for (i = 0; i + 1 < got; i += 2) {
        uint8_t t = p[i];
        p[i] = p[i + 1];
        p[i + 1] = t;
    }
    if (s->subst)
        for (i = 0; i < got; i++) p[i] = vise_subst[p[i]];
    return (int32_t)got;
}

static int vise_src_seek(void *ctx, unc_off_t pos)
{
    (void)ctx; (void)pos;
    return -1;                  /* a stream is read once, forwards    */
}

static unc_off_t vise_src_tell(void *ctx)
{
    (void)ctx;
    return UNC_OFF_UNKNOWN;
}

static unc_off_t vise_src_size(void *ctx)
{
    (void)ctx;
    return UNC_OFF_UNKNOWN;
}

/* ------------------------------------------------------------------ */
/* The inflater, resumable at any output byte                         */
/* ------------------------------------------------------------------ */

enum { VI_HEAD, VI_STORED, VI_HUFF, VI_DONE };

typedef int (*ViseEmit)(void *ctx, const uint8_t *p, uint32_t n);

typedef struct ViseInf {
    ViseSrc  src;
    UncIO    io;
    UncBufIn in;
    UncBitIn bi;
    UncCanon lit, dst;          /* `lit` is the code length code too  */
    uint8_t *win, *ibuf;
    uint32_t mask, wpos, total; /* `total` bytes out of this stream   */
    uint32_t copy, dist;        /* a match still to copy              */
    uint32_t stored;            /* a stored block's bytes still to copy */
    uint8_t  pad;               /* and a pad byte after them          */
    uint8_t  state, final;
    uint8_t  lens[288 + 32];
} ViseInf;

static int vise_open(ViseInf *v, uint32_t part, uint32_t off, uint32_t clen,
                     int subst, UncProgressState *ps)
{
    int err;
    v->src.left = clen;
    v->src.subst = subst;
    v->src.err = UNC_OK;
    v->src.ps = ps;
    v->src.credited = 0;
    if ((err = vise_seek(&v->src, part, off)) != UNC_OK) return err;
    v->io.ctx = &v->src;
    v->io.read = vise_src_read;
    v->io.seek = vise_src_seek;
    v->io.tell = vise_src_tell;
    v->io.size = vise_src_size;
    unc_bufin_init(&v->in, &v->io, NULL, v->ibuf, UNC_IOBUF);
    unc_bitin_init_le(&v->bi, &v->in);
    v->wpos = v->total = 0;
    v->copy = v->stored = 0;
    v->pad = 0;
    v->state = VI_HEAD;
    v->final = 0;
    return UNC_OK;
}

static int vise_bits(ViseInf *v, int n, uint32_t *out)
{
    int32_t b = unc_bitin_bits_le(&v->bi, n);
    if (b < 0) return v->bi.err ? v->bi.err : UNC_ERR_TRUNCATED;
    *out = (uint32_t)b;
    return UNC_OK;
}

static int vise_byte(ViseInf *v)
{
    int b = unc_bufin_next(&v->in);
    return b < 0 ? (v->in.err ? v->in.err : UNC_ERR_TRUNCATED) : b;
}

/* The tables of a dynamic block (RFC 1951 section 3.2.7). */
static int vise_tables(ViseInf *v)
{
    uint32_t hl, hd, hc, x;
    int32_t i, n, err;

    if ((err = vise_bits(v, 5, &hl)) != UNC_OK ||
        (err = vise_bits(v, 5, &hd)) != UNC_OK ||
        (err = vise_bits(v, 4, &hc)) != UNC_OK)
        return err;
    hl += 257; hd += 1; hc += 4;
    if (hl > 286 || hd > 30) return UNC_ERR_CORRUPT;
    for (i = 0; i < 19; i++) v->lens[i] = 0;
    for (i = 0; i < (int32_t)hc; i++) {
        if ((err = vise_bits(v, 3, &x)) != UNC_OK) return err;
        v->lens[vise_clord[i]] = (uint8_t)x;
    }
    if (unc_canon_build_le(&v->lit, v->lens, 19) != UNC_OK)
        return UNC_ERR_CORRUPT;
    for (n = 0; n < (int32_t)(hl + hd);) {
        int32_t sym = unc_canon_decode(&v->lit, &v->bi), rep;
        uint8_t fill = 0;
        if (sym < 0) return v->bi.err ? v->bi.err : UNC_ERR_CORRUPT;
        if (sym < 16) { v->lens[n++] = (uint8_t)sym; continue; }
        if (sym == 16) {
            if (n == 0) return UNC_ERR_CORRUPT;
            fill = v->lens[n - 1];
            if ((err = vise_bits(v, 2, &x)) != UNC_OK) return err;
            rep = 3 + (int32_t)x;
        } else if (sym == 17) {
            if ((err = vise_bits(v, 3, &x)) != UNC_OK) return err;
            rep = 3 + (int32_t)x;
        } else {
            if ((err = vise_bits(v, 7, &x)) != UNC_OK) return err;
            rep = 11 + (int32_t)x;
        }
        if (n + rep > (int32_t)(hl + hd)) return UNC_ERR_CORRUPT;
        while (rep--) v->lens[n++] = fill;
    }
    if (v->lens[256] == 0) return UNC_ERR_CORRUPT;   /* no end of block */
    if (unc_canon_build_le(&v->lit, v->lens, (int32_t)hl) != UNC_OK ||
        unc_canon_build_le(&v->dst, v->lens + hl, (int32_t)hd) != UNC_OK)
        return UNC_ERR_CORRUPT;
    return UNC_OK;
}

/* A block's three header bits, and what a stored block needs before its
 * bytes: the next 16-bit boundary of the stream, LEN and NLEN. */
static int vise_head(ViseInf *v)
{
    uint32_t h, len, nlen;
    int err;

    if (v->final) { v->state = VI_DONE; return UNC_OK; }
    if ((err = vise_bits(v, 3, &h)) != UNC_OK) return err;
    v->final = (uint8_t)(h & 1u);
    h >>= 1;
    if (h == 2) {
        if ((err = vise_tables(v)) != UNC_OK) return err;
        v->state = VI_HUFF;
        return UNC_OK;
    }
    if (h != 0) return UNC_ERR_CORRUPT;   /* fixed codes: VISE has none */
    unc_bitin_align(&v->bi);
    if ((unc_bitin_bytepos(&v->bi) & 1u) && (err = vise_byte(v)) < 0)
        return err;
    if ((err = vise_bits(v, 16, &len)) != UNC_OK ||
        (err = vise_bits(v, 16, &nlen)) != UNC_OK)
        return err;
    if ((len ^ nlen) != 0xFFFFu) return UNC_ERR_CORRUPT;
    v->stored = len;
    v->pad = (uint8_t)(len & 1u);
    v->state = VI_STORED;
    return UNC_OK;
}

/* Hand what the window holds past `*mark` to `emit`. */
static int vise_flush(ViseInf *v, uint32_t *mark, ViseEmit emit, void *ectx)
{
    int err = UNC_OK;
    if (emit && v->wpos > *mark)
        err = emit(ectx, v->win + *mark, v->wpos - *mark);
    *mark = v->wpos;
    return err;
}

/* Up to `want` more bytes of the stream, handed to `emit` as they leave
 * the window (`emit` NULL: passed over). UNC_OK once `want` are out or
 * the stream has ended; *got says how many. */
static int vise_produce(ViseInf *v, uint32_t want, ViseEmit emit, void *ectx,
                        uint32_t *got)
{
    uint32_t done = 0, mark = v->wpos, mask = v->mask;
    uint8_t *w = v->win;
    int err = UNC_OK;

#define VISE_PUT(b)                                                        \
    do {                                                                   \
        w[v->wpos++] = (b);                                                \
        done++;                                                            \
        if (v->wpos > mask) {                                              \
            if ((err = vise_flush(v, &mark, emit, ectx)) != UNC_OK)        \
                goto out;                                                  \
            v->wpos = mark = 0;                                            \
        }                                                                  \
    } while (0)

    while (done < want) {
        if (v->copy) {
            uint32_t from = (v->wpos - v->dist) & mask;
            while (v->copy && done < want) {
                uint8_t b = w[from];
                from = (from + 1) & mask;
                v->copy--;
                VISE_PUT(b);
            }
            continue;
        }
        if (v->state == VI_HUFF) {
            int32_t sym = unc_canon_decode(&v->lit, &v->bi);
            if (sym < 0) { err = v->bi.err ? v->bi.err : UNC_ERR_CORRUPT; goto out; }
            if (sym < 256) { VISE_PUT((uint8_t)sym); continue; }
            if (sym == 256) { v->state = VI_HEAD; continue; }
            sym -= 257;
            if (sym >= 29) { err = UNC_ERR_CORRUPT; goto out; }
            {
                uint32_t x, len, dist;
                int32_t ds;
                if ((err = vise_bits(v, vise_lext[sym], &x)) != UNC_OK) goto out;
                len = vise_lbase[sym] + x;
                ds = unc_canon_decode(&v->dst, &v->bi);
                if (ds < 0 || ds >= 30) {
                    err = ds < 0 && v->bi.err ? v->bi.err : UNC_ERR_CORRUPT;
                    goto out;
                }
                if ((err = vise_bits(v, vise_dext[ds], &x)) != UNC_OK) goto out;
                dist = vise_dbase[ds] + x;
                if (dist > v->total + done || dist > mask + 1u) {
                    err = UNC_ERR_CORRUPT;
                    goto out;
                }
                v->copy = len;
                v->dist = dist;
            }
            continue;
        }
        if (v->state == VI_STORED) {
            if (v->stored) {
                int b = vise_byte(v);
                if (b < 0) { err = b; goto out; }
                v->stored--;
                VISE_PUT((uint8_t)b);
                continue;
            }
            if (v->pad) {
                int b = vise_byte(v);
                if (b < 0) { err = b; goto out; }
                v->pad = 0;
            }
            v->state = VI_HEAD;
            continue;
        }
        if (v->state == VI_DONE) break;
        if ((err = vise_head(v)) != UNC_OK) goto out;
    }
    err = vise_flush(v, &mark, emit, ectx);
out:
    v->total += done;
    *got = done;
    /* A stream cut short by a segment that is not there says so. */
    if (err != UNC_OK && v->src.err != UNC_OK) err = v->src.err;
    return err;
#undef VISE_PUT
}

/* ------------------------------------------------------------------ */
/* The catalogue                                                      */
/* ------------------------------------------------------------------ */

typedef struct Vise {
    UncCtx   *c;
    ViseInf  *v;
    uint8_t  *cat;              /* the records                       */
    uint32_t  catlen;
    uint32_t  n, suf;
    uint32_t *rec;              /* each record's offset in `cat`     */
    uint16_t *par;              /* its parent folder's record, or ROOT */
    uint16_t *ord;              /* the files, in the order of their bytes */
    uint8_t  *keep;             /* a folder that holds a stored file */
    uint32_t  nfiles;
    /* The shared block being read, and how far into it. */
    uint32_t  bpart, boff, bclen;
    uint32_t  bpos;
    int       bopen;
    /* The shared block whose input is owed to the progress state: its
     * stream's length, what readings of it that are over credited, and
     * whether one that credits has begun. Settled once, as the walk
     * leaves the block, whatever was read of it. */
    uint32_t  cpart, coff, cclen, ccred;
    int       cstarted;
} Vise;

static int vise_cat_count(void *ctx, const uint8_t *p, uint32_t n)
{
    (void)p;
    *(uint32_t *)ctx += n;
    return UNC_OK;
}

typedef struct { uint8_t *at; uint32_t room; } ViseFill;

static int vise_cat_fill(void *ctx, const uint8_t *p, uint32_t n)
{
    ViseFill *f = (ViseFill *)ctx;
    uint32_t i;
    if (n > f->room) return UNC_ERR_CORRUPT;
    for (i = 0; i < n; i++) f->at[i] = p[i];
    f->at += n;
    f->room -= n;
    return UNC_OK;
}

/* Read the records into memory: as they are, or inflated, which takes two
 * passes because the catalogue does not say how long it is expanded. */
static int vise_cat_read(Vise *V, const uint8_t *h)
{
    UncCtx *c = V->c;
    uint8_t cv[VISE_CAT_HDR + 4];
    uint32_t at = unc_get_u32be(h + VISE_H_CAT), blen, comp, body, len;
    int err;

    if (V->v->src.cat == 0) return UNC_ERR_FORMAT;
    if ((err = vise_seek(&V->v->src, 1, at)) != UNC_OK) return err;
    if (unc_read_full(c->io, cv, (int32_t)sizeof cv) != UNC_OK)
        return UNC_ERR_TRUNCATED;
    if (unc_get_u32be(cv) != VISE_CAT_MAGIC) return UNC_ERR_FORMAT;
    blen = unc_get_u32be(cv + 4);
    comp = unc_get_u32be(cv + 8);
    V->n = unc_get_u16be(cv + 16);
    body = at + VISE_CAT_HDR;
    if (unc_get_u32be(cv + VISE_CAT_HDR) == VISE_PACK) body += VISE_PACK_LEN;
    else if (comp) return UNC_ERR_CORRUPT;
    /* +4 is the records' length, or past a prefix what follows it. */
    len = blen;
    if (len > VISE_CATMAX) return UNC_ERR_CORRUPT;
    if ((err = unc_progress_add(&c->ps, body - at)) != UNC_OK) return err;

    if (!comp) {
        V->cat = (uint8_t *)unc_alloc(c->al, len ? len : 1u);
        if (!V->cat) return UNC_ERR_MEM;
        if ((err = vise_seek(&V->v->src, 1, body)) != UNC_OK) return err;
        if (unc_read_full(c->io, V->cat, (int32_t)len) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        V->catlen = len;
        return unc_progress_add(&c->ps, len);
    }

    /* Inflated: the stream's own end says where the records end. */
    {
        uint32_t size = 0, got;
        ViseFill f;
        V->v->win = (uint8_t *)unc_alloc(c->al, VISE_WINMAX);
        if (!V->v->win) return UNC_ERR_MEM;
        V->v->mask = VISE_WINMAX - 1u;
        if ((err = vise_open(V->v, 1, body, blen, 0, &c->ps)) != UNC_OK)
            return err;
        err = vise_produce(V->v, VISE_CATMAX, vise_cat_count, &size, &got);
        if (err != UNC_OK) return err;
        if (V->v->state != VI_DONE || size == 0) return UNC_ERR_CORRUPT;
        V->cat = (uint8_t *)unc_alloc(c->al, size);
        if (!V->cat) return UNC_ERR_MEM;
        f.at = V->cat;
        f.room = size;
        if ((err = vise_open(V->v, 1, body, blen, 0, NULL)) != UNC_OK)
            return err;
        err = vise_produce(V->v, size, vise_cat_fill, &f, &got);
        if (err != UNC_OK) return err;
        if (got != size) return UNC_ERR_CORRUPT;
        V->catlen = size;
    }
    return UNC_OK;
}

/* The catalogue is past segment 1's payload, which ends where it starts:
 * while it is read, segment 1 is the whole file. */
static int vise_cat_load(Vise *V, const uint8_t *h)
{
    uint32_t pay = V->v->src.cat;
    int err;
    V->v->src.cat = UNC_U32_MAX;
    err = vise_cat_read(V, h);
    V->v->src.cat = pay;
    return err;
}

static uint32_t vise_find(const uint8_t *p, uint32_t from, uint32_t len)
{
    uint32_t i;
    for (i = from; i + 4 <= len; i++)
        if ((p[i] == 'F' || p[i] == 'D') && p[i + 1] == 'V' &&
            p[i + 2] == 'C' && p[i + 3] == 'T')
            return i;
    return UNC_SIZE_UNKNOWN;
}

#define VR(V, k)      ((V)->cat + (V)->rec[k] + 4)  /* a record's body */
#define VISDIR(V, k)  ((V)->cat[(V)->rec[k]] == 'D')
#define VSEG(V, k)    unc_get_u16be(VR(V, k) + 94)

/* Where every record is, whose its parent is, and which folders hold a
 * file that is in the archive. */
static int vise_walk(Vise *V)
{
    UncCtx *c = V->c;
    uint16_t stack[VISE_DEPTHMAX];
    uint32_t k, at = 0, sp = 0, dsuf = VISE_DSUF(V->suf),
             fsuf = VISE_FSUF(V->suf);

    if (V->n == 0) return UNC_ERR_CORRUPT;
    V->rec = (uint32_t *)unc_alloc(c->al, V->n * 9u);
    if (!V->rec) return UNC_ERR_MEM;
    V->par = (uint16_t *)(V->rec + V->n);
    V->ord = V->par + V->n;
    V->keep = (uint8_t *)(V->ord + V->n);
    for (k = 0; k < V->n; k++) V->keep[k] = 0;

    for (k = 0; k < V->n; k++) {
        const uint8_t *r;
        uint32_t fixed, depth, need, nlen;
        int isdir;
        if (at + 4 > V->catlen || V->cat[at + 1] != 'V' ||
            V->cat[at + 2] != 'C' || V->cat[at + 3] != 'T')
            return UNC_ERR_CORRUPT;
        isdir = V->cat[at] == 'D';
        if (!isdir && V->cat[at] != 'F') return UNC_ERR_CORRUPT;
        fixed = isdir ? 78u : 120u;
        if (V->catlen - at - 4 < fixed + 1u) return UNC_ERR_CORRUPT;
        V->rec[k] = at;
        r = V->cat + at + 4;
        nlen = r[isdir ? VISE_DLEN(V->suf) : VISE_FLEN(V->suf)];
        need = 4 + fixed + (isdir ? dsuf : fsuf) + nlen;
        depth = unc_get_u16be(r + (isdir ? 68 : 92));
        if (depth > sp) return UNC_ERR_CORRUPT;
        V->par[k] = depth ? stack[depth - 1] : VISE_ROOT;
        if (isdir) {
            if (depth >= VISE_DEPTHMAX) return UNC_ERR_CORRUPT;
            stack[depth] = (uint16_t)k;
            sp = depth + 1;
        } else if (unc_get_u16be(r + 94) != 0) {
            uint32_t p = V->par[k];
            /* Its name must fit before whatever comes next. */
            if (V->catlen - at < need) return UNC_ERR_CORRUPT;
            V->ord[V->nfiles++] = (uint16_t)k;
            while (p != VISE_ROOT && !V->keep[p]) {
                V->keep[p] = 1;
                p = V->par[p];
            }
        }
        if (k + 1 < V->n) {
            at = vise_find(V->cat, at + 4 + fixed, V->catlen);
            if (at == UNC_SIZE_UNKNOWN) return UNC_ERR_CORRUPT;
        }
        if (isdir && V->catlen - V->rec[k] < need) return UNC_ERR_CORRUPT;
    }
    return UNC_OK;
}

/* Where a file's bytes start, as one number that orders them: segment,
 * offset, then the first of its slices in a shared block. */
static void vise_key(const Vise *V, uint32_t k, uint32_t key[3])
{
    const uint8_t *r = VR(V, k);
    key[0] = unc_get_u16be(r + 94);
    key[1] = unc_get_u32be(r + 96);
    key[2] = 0;
    if (r[8] & 0x10)
        key[2] = unc_get_u32be(r + 68) ? unc_get_u32be(r + 100)
                                        : unc_get_u32be(r + 104);
}

static int vise_before(const Vise *V, uint32_t a, uint32_t b)
{
    uint32_t ka[3], kb[3];
    int i;
    vise_key(V, a, ka);
    vise_key(V, b, kb);
    for (i = 0; i < 3; i++)
        if (ka[i] != kb[i]) return ka[i] < kb[i];
    return a < b;
}

/* Shell sort: no recursion, and catalogue order kept among equal keys
 * by the tie on the record's index. */
static void vise_sort(Vise *V)
{
    uint32_t gap, i, j, n = V->nfiles;
    for (gap = 1; gap < n / 3; gap = gap * 3 + 1) {}
    for (; gap > 0; gap /= 3)
        for (i = gap; i < n; i++) {
            uint16_t t = V->ord[i];
            for (j = i; j >= gap && vise_before(V, t, V->ord[j - gap]);
                 j -= gap)
                V->ord[j] = V->ord[j - gap];
            V->ord[j] = t;
        }
}

/* A record's path: its folders from the root down, then its own name. */
static void vise_path(const Vise *V, uint32_t k, UncEntryInfo *e)
{
    uint16_t up[VISE_DEPTHMAX];
    uint32_t d = 0, p = k;
    while (p != VISE_ROOT && d < VISE_DEPTHMAX) {
        up[d++] = (uint16_t)p;
        p = V->par[p];
    }
    while (d--) {
        uint32_t q = up[d];
        const uint8_t *r = VR(V, q);
        int isdir = VISDIR(V, q);
        uint32_t nl = r[isdir ? VISE_DLEN(V->suf) : VISE_FLEN(V->suf)];
        uint32_t off = isdir ? 78u + VISE_DSUF(V->suf)
                             : 120u + VISE_FSUF(V->suf);
        unc_entry_path_append(e, r + off, nl);
    }
}

/* ------------------------------------------------------------------ */
/* The files                                                          */
/* ------------------------------------------------------------------ */

typedef struct ViseOut {
    UncCtx  *c;
    UncFork  fork;
    uint32_t crc;
} ViseOut;

static int vise_out(void *ctx, const uint8_t *p, uint32_t n)
{
    ViseOut *o = (ViseOut *)ctx;
    o->crc = unc_crc32(o->crc, p, (int32_t)n);
    if (o->c->opt.test_only) return UNC_OK;
    return o->c->sink->write(o->c->sink->ctx, o->fork, p, (int32_t)n) < 0
           ? UNC_ERR_SINK : UNC_OK;
}

/* One fork that is its own stream. */
static int vise_fork(Vise *V, ViseOut *o, UncFork fork, uint32_t part,
                     uint32_t off, uint32_t clen, uint32_t len)
{
    uint32_t got;
    int err;
    if (len == 0) return UNC_OK;
    V->bopen = 0;
    if ((err = vise_open(V->v, part, off, clen, 1, &V->c->ps)) != UNC_OK)
        return err;
    o->fork = fork;
    err = vise_produce(V->v, len, vise_out, o, &got);
    if (err != UNC_OK) return err;
    return got == len ? UNC_OK : UNC_ERR_CORRUPT;
}

static int vise_settle(Vise *V)
{
    uint32_t got = V->ccred;
    int err = UNC_OK;
    if (!V->cclen) return UNC_OK;
    if (V->bopen && V->bpart == V->cpart && V->boff == V->coff &&
        V->v->src.ps)
        got += V->v->src.credited;
    if (got < V->cclen) err = unc_progress_add(&V->c->ps, V->cclen - got);
    V->cclen = 0;
    return err;
}

/* One slice of a shared block: decoded on from where the block was left,
 * or from its start when this slice is behind that. */
static int vise_slice(Vise *V, ViseOut *o, UncFork fork, uint32_t part,
                      uint32_t off, uint32_t clen, uint32_t at, uint32_t len)
{
    uint32_t got;
    int err;
    if (len == 0) return UNC_OK;
    if (!V->bopen || V->bpart != part || V->boff != off ||
        V->bclen != clen || at < V->bpos) {
        /* Credited once: a block read again is not more of the file. */
        UncProgressState *ps = NULL;
        if (V->bopen && V->bpart == part && V->boff == off && V->v->src.ps)
            V->ccred += V->v->src.credited;
        if (V->cclen && V->cpart == part && V->coff == off &&
            !V->cstarted) {
            ps = &V->c->ps;
            V->cstarted = 1;
        }
        V->bopen = 0;
        err = vise_open(V->v, part, off, clen, 1, ps);
        if (err != UNC_OK) return err;
        V->bopen = 1;
        V->bpart = part;
        V->boff = off;
        V->bclen = clen;
        V->bpos = 0;
    }
    if (at > V->bpos) {
        err = vise_produce(V->v, at - V->bpos, NULL, NULL, &got);
        V->bpos += got;
        if (err != UNC_OK) { V->bopen = 0; return err; }
        if (V->bpos != at) { V->bopen = 0; return UNC_ERR_CORRUPT; }
    }
    o->fork = fork;
    err = vise_produce(V->v, len, vise_out, o, &got);
    V->bpos += got;
    if (err != UNC_OK) { V->bopen = 0; return err; }
    if (got != len) { V->bopen = 0; return UNC_ERR_CORRUPT; }
    return UNC_OK;
}

static int vise_file(Vise *V, uint32_t k)
{
    UncCtx *c = V->c;
    const uint8_t *r = VR(V, k);
    /* The set's file a record's segment is in: VISE X's first is the
     * catalogue's, and its segment 1 is the second. */
    uint32_t part = unc_get_u16be(r + 94) + ((V->suf & VISE_X) ? 1u : 0u),
             off = unc_get_u32be(r + 96);
    uint32_t dc = unc_get_u32be(r + 64), dl = unc_get_u32be(r + 68),
             rc = unc_get_u32be(r + 72), rl = unc_get_u32be(r + 76),
             crc = unc_get_u32be(r + 80);
    uint32_t nparts = c->segmap ? c->segmap->nparts : 1u;
    int shared = (r[8] & 0x10) != 0;
    uint32_t owed = 0, before;
    UncEntryInfo e;
    ViseOut o;
    int sret, est = UNC_OK;

    unc_entry_clear(&e);
    vise_path(V, k, &e);
    e.type = unc_get_u32be(r + 40);
    e.creator = unc_get_u32be(r + 44);
    e.finder_flags = unc_get_u16be(r + 48);
    e.create_date = unc_get_u32be(r + 56);
    e.mod_date = unc_get_u32be(r + 60);
    e.data_size = dl;
    e.rsrc_size = rl;
    e.comp_data_size = shared ? 0 : dc;
    e.comp_rsrc_size = shared ? 0 : rc;

    if (dl > UNC_MAC_MAX || rl > UNC_MAC_MAX)
        est = UNC_ERR_TOOLARGE;
    else if (part > nparts)
        est = UNC_ERR_SEGMENTED;
    else if (shared) {
        uint32_t s0 = unc_get_u32be(r + 100), s1 = unc_get_u32be(r + 104);
        /* A slice must lie in the block's expanded bytes. */
        if ((dl && (s0 > rc || dl > rc - s0)) ||
            (rl && (s1 > rc || rl > rc - s1)))
            est = UNC_ERR_CORRUPT;
    } else {
        if (dc > UNC_MAC_MAX - rc) est = UNC_ERR_CORRUPT;
        owed = dc + rc;
    }
    /* A shared block is owed once, by the walk, as it leaves the block. */
    if (!shared || !V->cclen || V->cpart != part || V->coff != off) {
        int perr = vise_settle(V);
        if (perr != UNC_OK) return perr;
        if (shared && part <= nparts) {
            V->cpart = part;
            V->coff = off;
            V->cclen = dc;
            V->ccred = 0;
            V->cstarted = 0;
        }
    }
    if (est == UNC_ERR_TOOLARGE || est == UNC_ERR_SEGMENTED) owed = 0;
    before = c->ps.done;

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) return UNC_ERR_SINK;
    if (sret == 0) {
        if (!c->opt.list_only && est == UNC_OK) {
            o.c = c;
            o.crc = UNC_CRC32_INIT;
            if (shared) {
                est = vise_slice(V, &o, UNC_FORK_DATA, part, off, dc,
                                 unc_get_u32be(r + 100), dl);
                if (est == UNC_OK)
                    est = vise_slice(V, &o, UNC_FORK_RSRC, part, off, dc,
                                     unc_get_u32be(r + 104), rl);
            } else {
                est = vise_fork(V, &o, UNC_FORK_DATA, part, off, dc, dl);
                if (est == UNC_OK && rl) {
                    /* The resource fork's stream follows the data fork's,
                     * in whatever segment that one ran on into. */
                    uint32_t p2 = part, o2 = off;
                    est = vise_advance(&V->v->src, &p2, &o2, dc);
                    if (est == UNC_OK)
                        est = vise_fork(V, &o, UNC_FORK_RSRC, p2, o2, rc, rl);
                }
            }
            if (est == UNC_OK && ~o.crc != crc) est = UNC_ERR_CRC;
        }
        if (c->sink->end_entry(c->sink->ctx, est) < 0) return UNC_ERR_SINK;
        if (unc_fatal(est)) return est;
    }
    /* What ran on into a segment that is not here is not this file's. */
    if (est == UNC_ERR_SEGMENTED) owed = 0;
    if (c->ps.done - before < owed)
        return unc_progress_add(&c->ps, owed - (c->ps.done - before));
    return UNC_OK;
}

int unc_vise_extract(UncCtx *c)
{
    uint8_t h[VISE_HDR];
    Vise V;
    uint32_t k;
    int err;

    /* Through a set's map, or the installer alone: a set of one without
     * the joiner, whose records of a later segment then fail one by one. */
    if (c->segmap ? c->segmap->seek_part(c->segmap->ctx, 1, 0) < 0
                  : c->io->seek(c->io->ctx, 0) < 0)
        return UNC_ERR_FORMAT;
    if (unc_read_full(c->io, h, (int32_t)VISE_HDR) != UNC_OK ||
        !vise_first_ok(h))
        return UNC_ERR_FORMAT;

    V.c = c;
    V.cat = NULL;
    V.rec = NULL;
    V.nfiles = 0;
    V.bopen = 0;
    V.cclen = 0;
    V.suf = vise_suffixes(unc_get_u32be(h + VISE_H_VER));
    V.v = (ViseInf *)unc_alloc(c->al, (uint32_t)sizeof(ViseInf) + UNC_IOBUF);
    if (!V.v) return UNC_ERR_MEM;
    V.v->src.c = c;
    V.v->src.cat = unc_get_u32be(h + VISE_H_CAT);
    V.v->ibuf = (uint8_t *)(V.v + 1);
    V.v->win = NULL;
    if ((err = unc_progress_add(&c->ps, VISE_HDR)) != UNC_OK) goto out;

    /* A compressed catalogue inflates through a whole window, allocated
     * when it is met; the files through one no larger than the largest
     * stream's output needs, below. */
    if ((err = vise_cat_load(&V, h)) != UNC_OK) goto out;
    if ((err = vise_walk(&V)) != UNC_OK) goto out;

    /* The folders that hold a stored file, in catalogue order. */
    for (k = 0; k < V.n; k++) {
        UncEntryInfo e;
        const uint8_t *r;
        int sret;
        if (!VISDIR(&V, k) || !V.keep[k]) continue;
        r = VR(&V, k);
        unc_entry_clear(&e);
        vise_path(&V, k, &e);
        e.is_dir = 1;
        e.create_date = unc_get_u32be(r + 16);
        e.mod_date = unc_get_u32be(r + 20);
        e.data_size = e.rsrc_size = 0;
        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; goto out; }
        if (sret == 0 && c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) {
            err = UNC_ERR_SINK;
            goto out;
        }
    }

    /* No stream's match reaches further back than its own output, so the
     * window need be no larger than the longest output a stream has: the
     * catalogue's, read above, needed a whole one, and a small installer's
     * files need far less. */
    {
        uint32_t need = 512u, f;
        for (f = 0; f < V.nfiles; f++) {
            const uint8_t *r = VR(&V, V.ord[f]);
            uint32_t o = (r[8] & 0x10) ? unc_get_u32be(r + 72)
                                       : unc_get_u32be(r + 68);
            if (!(r[8] & 0x10) && unc_get_u32be(r + 76) > o)
                o = unc_get_u32be(r + 76);
            while (need < o && need < VISE_WINMAX) need <<= 1;
        }
        if (!V.v->win || V.v->mask + 1u != need) {
            if (V.v->win) unc_free(c->al, V.v->win);
            V.v->win = (uint8_t *)unc_alloc(c->al, need);
            if (!V.v->win) { err = UNC_ERR_MEM; goto out; }
            V.v->mask = need - 1u;
        }
    }

    vise_sort(&V);
    for (k = 0; k < V.nfiles; k++)
        if ((err = vise_file(&V, V.ord[k])) != UNC_OK) goto out;
    if ((err = vise_settle(&V)) != UNC_OK) goto out;
    /* An installer that stores none of what it installs — a downloader,
     * an updater that finds its files on the disk — has nothing to give. */
    if (V.nfiles == 0) err = UNC_ERR_UNSUPPORTED;
out:
    if (V.rec) unc_free(c->al, V.rec);
    if (V.cat) unc_free(c->al, V.cat);
    if (V.v->win) unc_free(c->al, V.v->win);
    unc_free(c->al, V.v);
    return err;
}

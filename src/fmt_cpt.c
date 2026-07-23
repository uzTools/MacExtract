/*
 * fmt_cpt.c — Compact Pro (.cpt) decoder.
 *
 * Layout (sources: reference/XADMaster/XADCompactProParser.m and
 * reference/macutils/macunpack/cpt.c — LGPL, see NOTICE):
 *
 *   File header (8 bytes): u8 signature (= 1), u8 volume, u16 xmagic,
 *   u32 offset of the index.
 *
 *   Index, at `offset`: u32 index CRC, then the CRC'd region:
 *   u16 nentries, u8 commentlen, comment, then `nentries` entry
 *   headers. nentries counts every header, including those inside
 *   folders. Entry header: u8 namelen (bit 7 = folder), name
 *   (namelen & 0x7f bytes), then for a folder u16 subtree entry count
 *   (again counting nested contents), or for a file 45 bytes:
 *     u8 volume, u32 fileoffs, u32 type, u32 creator, u32 createdate,
 *     u32 moddate, u16 finderflags, u32 fileCRC, u16 flags,
 *     u32 rsrclen, u32 datalen, u32 rsrccomplen, u32 datacomplen
 *   flags: bit0 = encrypted, bit1 = rsrc fork LZH, bit2 = data fork
 *   LZH (else the fork is RLE only).
 *
 *   File data, at absolute `fileoffs`: compressed rsrc fork
 *   (rsrccomplen bytes) immediately followed by the compressed data
 *   fork (datacomplen bytes).
 *
 *   Both CRCs are CRC-32 (reflected 0xEDB88320), init 0xFFFFFFFF,
 *   compared WITHOUT the final xor (macutils compares against
 *   INIT_CRC-seeded zip_updcrc directly; XADMaster passes
 *   correctCRC:~crc to a conditioned handle — same thing). fileCRC
 *   covers the decoded rsrc fork bytes, then the decoded data fork.
 *
 * Compression is RLE, optionally preceded by an LZSS+Huffman stage
 * ("LZH"); see cpt_rle_* and cpt_lzh_* below.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define CPT_WINDOW   8192u      /* macutils CIRCSIZE */
#define CPT_BLOCK    0x1fff0u   /* cost units per Huffman-tree block */
#define CPT_ESC1     0x81
#define CPT_ESC2     0x82

/* ------------------------------------------------------------------ */
/* Probe: signature byte + full index CRC walk, as XADMaster's        */
/* recognizeFileWithHandle does. A 1-byte magic is far too weak on    */
/* its own.                                                           */
/* ------------------------------------------------------------------ */

int unc_cpt_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint8_t buf[256];   /* max chunk: 255-byte archive comment; entries
                         * are smaller (127-byte name + 45 meta) */
    uint32_t offset, crc, storedcrc, fsize;
    uint32_t nentries, commentlen, i;

    if (len < 8 || head[0] != 1) return 0;
    offset = unc_get_u32be(head + 4);
    fsize = io->size(io->ctx);
    if (fsize != UNC_SIZE_UNKNOWN && (offset + 7 < offset || offset + 7 > fsize))
        return 0;

    if (unc_read_at(io, offset, buf, 7) != UNC_OK) return 0;
    storedcrc = unc_get_u32be(buf);
    crc = unc_crc32(0xFFFFFFFFu, buf + 4, 3);
    nentries = unc_get_u16be(buf + 4);
    commentlen = buf[6];

    if (commentlen) {
        if (unc_read_full(io, buf, (int32_t)commentlen) != UNC_OK) return 0;
        crc = unc_crc32(crc, buf, (int32_t)commentlen);
    }

    for (i = 0; i < nentries; i++) {
        uint32_t namelen, metalen, left;
        if (unc_read_full(io, buf, 1) != UNC_OK) return 0;
        crc = unc_crc32(crc, buf, 1);
        namelen = buf[0] & 0x7f;
        metalen = (buf[0] & 0x80) ? 2 : 45;
        left = namelen + metalen;
        if (unc_read_full(io, buf, (int32_t)left) != UNC_OK) return 0;
        crc = unc_crc32(crc, buf, (int32_t)left);
    }
    return crc == storedcrc;
}

/* ------------------------------------------------------------------ */
/* RLE stage (the final stage of both methods).                       */
/* Transcribed from macutils cpt.c cpt_outch: escape byte 0x81;       */
/*   0x81 0x82 n>0  -> n-1 more copies of the previous byte           */
/*   0x81 0x82 0    -> literal 0x81 0x82                              */
/*   0x81 0x81      -> literal 0x81, and the second 0x81 starts a new */
/*                     escape ("halfescaped" in XADCompactProRLE)     */
/*   0x81 X         -> literal 0x81 X                                 */
/* Quirk: an 0x81 that would be the LAST output byte is emitted as a  */
/* literal (the `cpt_outlength != 1` tests below).                    */
/* ------------------------------------------------------------------ */

enum { CPT_RLE_NONE, CPT_RLE_ESC1, CPT_RLE_ESC2 };

typedef struct CptRle {
    UncCtx  *c;
    UncFork  fork;
    uint32_t remaining;   /* output bytes still owed */
    uint32_t crc;         /* running fork CRC (shared across forks) */
    int      state;
    uint8_t  saved;       /* last emitted byte (repeat source) */
    uint8_t *obuf;        /* staging buffer */
    uint32_t ocap, olen;
    int      err;         /* sticky */
} CptRle;

static void cpt_rle_start(CptRle *r, UncCtx *c, UncFork fork,
                          uint32_t outlen, uint32_t crc,
                          uint8_t *obuf, uint32_t ocap)
{
    r->c = c;
    r->fork = fork;
    r->remaining = outlen;
    r->crc = crc;
    r->state = CPT_RLE_NONE;
    r->saved = 0;
    r->obuf = obuf;
    r->ocap = ocap;
    r->olen = 0;
    r->err = UNC_OK;
}

static int cpt_rle_flush(CptRle *r)
{
    if (r->olen == 0) return UNC_OK;
    r->crc = unc_crc32(r->crc, r->obuf, (int32_t)r->olen);
    if (!r->c->opt.test_only &&
        r->c->sink->write(r->c->sink->ctx, r->fork, r->obuf,
                          (int32_t)r->olen) < 0) {
        r->err = UNC_ERR_SINK;
        return r->err;
    }
    r->olen = 0;
    return UNC_OK;
}

static int cpt_rle_emit(CptRle *r, uint8_t b)
{
    r->obuf[r->olen++] = b;
    r->remaining--;
    if (r->olen == r->ocap) return cpt_rle_flush(r);
    return UNC_OK;
}

/* Feed one post-LZ byte through the RLE state machine. */
static int cpt_rle_push(CptRle *r, uint8_t ch)
{
    if (r->err != UNC_OK) return r->err;
    switch (r->state) {
    case CPT_RLE_NONE:
        if (ch == CPT_ESC1 && r->remaining != 1) {
            r->state = CPT_RLE_ESC1;
        } else {
            r->saved = ch;
            return cpt_rle_emit(r, ch);
        }
        break;
    case CPT_RLE_ESC1:
        if (ch == CPT_ESC2) {
            r->state = CPT_RLE_ESC2;
        } else {
            r->saved = CPT_ESC1;
            if (cpt_rle_emit(r, CPT_ESC1) != UNC_OK) return r->err;
            if (r->remaining == 0) return UNC_OK;
            if (ch == CPT_ESC1 && r->remaining != 1)
                return UNC_OK;             /* stay in ESC1 ("halfescaped") */
            r->state = CPT_RLE_NONE;
            r->saved = ch;
            return cpt_rle_emit(r, ch);
        }
        break;
    default: /* CPT_RLE_ESC2 */
        r->state = CPT_RLE_NONE;
        if (ch != 0) {
            /* ch-1 further copies of the previous byte, clamped to the
             * output budget (macutils stops when outlength hits 0). */
            uint32_t n = (uint32_t)ch - 1;
            while (n-- > 0 && r->remaining > 0)
                if (cpt_rle_emit(r, r->saved) != UNC_OK) return r->err;
        } else {
            if (cpt_rle_emit(r, CPT_ESC1) != UNC_OK) return r->err;
            if (r->remaining == 0) return UNC_OK;
            r->saved = CPT_ESC2;
            return cpt_rle_emit(r, CPT_ESC2);
        }
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* LZH stage: LZSS over an 8 KB window + three canonical Huffman      */
/* codes (literals 256, match lengths 64, match offsets 128), with a  */
/* fresh set of codes every CPT_BLOCK cost units (2 per literal, 3    */
/* per match). Sources: XADCompactProLZHHandle.m and macutils cpt.c   */
/* cpt_rle_lzh.                                                       */
/* ------------------------------------------------------------------ */

typedef struct CptLzh {
    UncCanon lit, len, off;
} CptLzh;

/* One code: u8 n, then n bytes of two 4-bit code lengths each
 * (high nibble first). n*2 must not exceed nsyms; missing trailing
 * lengths are zero. (XADCompactProLZHHandle allocAndParseCodeOfSize.) */
static int cpt_read_code(UncCanon *c, UncBufIn *in, int32_t nsyms)
{
    uint8_t lengths[256];
    int32_t n, i;
    int b = unc_bufin_next(in);
    if (b < 0) return in->err;
    n = b;
    if (n * 2 > nsyms) return UNC_ERR_CORRUPT;
    for (i = 0; i < n; i++) {
        b = unc_bufin_next(in);
        if (b < 0) return in->err;
        lengths[2 * i]     = (uint8_t)(b >> 4);
        lengths[2 * i + 1] = (uint8_t)(b & 0x0f);
    }
    for (i = n * 2; i < nsyms; i++) lengths[i] = 0;
    return unc_canon_build(c, lengths, nsyms);
}

/* Decode one LZH-compressed fork, feeding bytes through `rle`. */
static int cpt_lzh_fork(CptRle *rle, UncBufIn *in, CptLzh *hz,
                        uint8_t *window)
{
    UncBitIn bi;
    uint32_t wpos = 0;
    uint32_t blockcost = CPT_BLOCK;   /* force tree read on first pass */
    uint32_t blockstart = 0;
    int first = 1, err;
    uint32_t i;

    for (i = 0; i < CPT_WINDOW; i++) window[i] = 0;
    unc_bitin_init(&bi, in);

    while (rle->remaining > 0) {
        if (blockcost >= CPT_BLOCK) {
            /* New block: re-read the three codes, byte-aligned.
             * After the first block, the encoder pads to a 16-bit unit
             * boundary relative to the previous trees' end; XADMaster
             * expresses this as: align to byte, then skip 3 bytes if
             * an odd number of bytes was consumed since the previous
             * block's trees, else 2. ("Don't let your bad
             * implementations leak into your file formats, people!"
             * — XADCompactProLZHHandle.m) */
            if (!first) {
                uint32_t consumed;
                unc_bitin_align(&bi);
                consumed = unc_bitin_bytepos(&bi) - blockstart;
                if (unc_bufin_next(in) < 0 || unc_bufin_next(in) < 0 ||
                    ((consumed & 1) && unc_bufin_next(in) < 0))
                    return in->err;
            }
            first = 0;
            if ((err = cpt_read_code(&hz->lit, in, 256)) != UNC_OK) return err;
            if ((err = cpt_read_code(&hz->len, in, 64))  != UNC_OK) return err;
            if ((err = cpt_read_code(&hz->off, in, 128)) != UNC_OK) return err;
            blockcost = 0;
            unc_bitin_init(&bi, in);
            blockstart = unc_bitin_bytepos(&bi);
        }

        {
            int bit = unc_bitin_bit(&bi);
            if (bit < 0) return bi.err;
            if (bit) {
                int sym = unc_canon_decode(&hz->lit, &bi);
                if (sym < 0)
                    return bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT;
                window[wpos++ & (CPT_WINDOW - 1)] = (uint8_t)sym;
                if ((err = cpt_rle_push(rle, (uint8_t)sym)) != UNC_OK)
                    return err;
                blockcost += 2;
            } else {
                int32_t mlen, moff, low;
                uint32_t from;
                mlen = unc_canon_decode(&hz->len, &bi);
                if (mlen < 0)
                    return bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT;
                moff = unc_canon_decode(&hz->off, &bi);
                if (moff < 0)
                    return bi.err != UNC_OK ? bi.err : UNC_ERR_CORRUPT;
                low = unc_bitin_bits(&bi, 6);
                if (low < 0) return bi.err;
                moff = (moff << 6) | low;
                /* Copy from the window; overlap (and even offset 0,
                 * reading bytes as they are written) is legal. The
                 * copy may overshoot rle->remaining; macutils stops
                 * writing when the output budget is exhausted. */
                from = wpos - (uint32_t)moff;
                while (mlen-- > 0 && rle->remaining > 0) {
                    uint8_t b = window[from++ & (CPT_WINDOW - 1)];
                    window[wpos++ & (CPT_WINDOW - 1)] = b;
                    if ((err = cpt_rle_push(rle, b)) != UNC_OK) return err;
                }
                blockcost += 3;
            }
        }
    }
    return UNC_OK;
}

/* Plain-RLE fork: complen input bytes through the RLE stage. */
static int cpt_rle_fork(CptRle *rle, UncBufIn *in, uint32_t complen)
{
    uint32_t i;
    int err;
    for (i = 0; i < complen && rle->remaining > 0; i++) {
        int b = unc_bufin_next(in);
        if (b < 0) return in->err;
        if ((err = cpt_rle_push(rle, (uint8_t)b)) != UNC_OK) return err;
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* One fork: position io, bound the substream, pick the method.       */
/* Returns UNC_OK and the updated running CRC via *crc.               */
/* ------------------------------------------------------------------ */

static int cpt_fork(UncCtx *c, UncFork fork, uint32_t at, uint32_t complen,
                    uint32_t outlen, int lzh, uint32_t *crc,
                    uint8_t *iobuf, uint32_t iocap,
                    uint8_t *obuf, uint32_t ocap,
                    CptLzh *hz, uint8_t *window)
{
    UncBufIn in;
    CptRle rle;
    int err;

    if (complen == 0 || outlen == 0) {
        /* macutils cpt_wrfile returns before writing anything when the
         * compressed fork is empty, whatever the claimed output size. */
        return UNC_OK;
    }
    if (c->io->seek(c->io->ctx, at) < 0) return UNC_ERR_IO;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = complen;   /* corrupt streams must not read past the fork */

    cpt_rle_start(&rle, c, fork, outlen, *crc, obuf, ocap);
    if (lzh) err = cpt_lzh_fork(&rle, &in, hz, window);
    else     err = cpt_rle_fork(&rle, &in, complen);
    if (err == UNC_OK && rle.remaining > 0) err = UNC_ERR_TRUNCATED;
    if (err == UNC_OK || err == UNC_ERR_TRUNCATED || err == UNC_ERR_CORRUPT)
        if (cpt_rle_flush(&rle) != UNC_OK) err = rle.err;
    *crc = rle.crc;
    return err;
}

/* ------------------------------------------------------------------ */
/* Container walk                                                     */
/* ------------------------------------------------------------------ */

#define CPT_MAX_DEPTH 32

int unc_cpt_extract(UncCtx *c)
{
    uint8_t head[8], meta[45], name[128];
    uint32_t offset, fsize, ipos;
    uint32_t nentries, commentlen, done;
    uint32_t remaining[CPT_MAX_DEPTH]; /* entries left per folder level */
    uint16_t pathlen[CPT_MAX_DEPTH];   /* path length before each level */
    int depth = 0;
    UncEntryInfo e;
    uint8_t *iobuf, *obuf, *window;
    CptLzh *hz;
    uint32_t iocap = 4096, ocap = 4096;
    uint8_t path[UNC_NAME_MAX + 1];
    uint16_t plen = 0;
    int err = UNC_OK;

    fsize = c->io->size(c->io->ctx);

    if (unc_read_at(c->io, 0, head, 8) != UNC_OK) return UNC_ERR_FORMAT;
    if (head[0] != 1) return UNC_ERR_FORMAT;
    offset = unc_get_u32be(head + 4);

    if (unc_read_at(c->io, offset, meta, 7) != UNC_OK) return UNC_ERR_FORMAT;
    /* Index CRC was verified by the probe; re-deriving it here would
     * mean a second full pass, so trust the per-file CRCs instead. */
    nentries = unc_get_u16be(meta + 4);
    commentlen = meta[6];
    ipos = offset + 7 + commentlen;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap + CPT_WINDOW);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;
    window = obuf + ocap;
    hz = (CptLzh *)unc_alloc(c->al, (uint32_t)sizeof *hz);
    if (!hz) { unc_free(c->al, iobuf); return UNC_ERR_MEM; }

    remaining[0] = nentries;
    pathlen[0] = 0;

    for (done = 0; done < nentries; done++) {
        uint32_t namelen, isdir;
        int sret;

        while (depth > 0 && remaining[depth] == 0) {
            plen = pathlen[depth];
            depth--;
        }
        if (remaining[depth] == 0) break;   /* top level exhausted */

        if (unc_read_at(c->io, ipos, name, 1) != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            goto out;
        }
        ipos++;
        namelen = name[0] & 0x7f;
        isdir = name[0] & 0x80;
        if (namelen &&
            unc_read_at(c->io, ipos, name, (int32_t)namelen) != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            goto out;
        }
        ipos += namelen;

        {
            uint32_t lvl;
            for (lvl = 0; lvl <= (uint32_t)depth; lvl++) remaining[lvl]--;
        }

        unc_entry_clear(&e);
        unc_entry_set_path(&e, path, plen);   /* already-swapped prefix */
        unc_entry_path_append(&e, name, namelen);

        if (isdir) {
            uint32_t count;
            if (unc_read_at(c->io, ipos, meta, 2) != UNC_OK) {
                err = UNC_ERR_TRUNCATED;
                goto out;
            }
            ipos += 2;
            count = unc_get_u16be(meta);
            if (count > remaining[depth]) {   /* subtree bigger than parent */
                err = UNC_ERR_CORRUPT;
                goto out;
            }
            e.is_dir = 1;
            e.data_size = e.rsrc_size = 0;
            e.comp_data_size = e.comp_rsrc_size = 0;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; goto out; }
            if (sret == 0 && c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
            if (depth + 1 >= CPT_MAX_DEPTH) { err = UNC_ERR_CORRUPT; goto out; }
            depth++;
            remaining[depth] = count;
            pathlen[depth] = plen;
            plen = e.name_len;
            {
                uint32_t i;
                for (i = 0; i < e.name_len; i++) path[i] = e.name[i];
            }
        } else {
            uint32_t fileoffs, filecrc, flags;
            uint32_t rsrclen, datalen, rcomp, dcomp;
            uint32_t crc;
            int est;

            if (unc_read_at(c->io, ipos, meta, 45) != UNC_OK) {
                err = UNC_ERR_TRUNCATED;
                goto out;
            }
            ipos += 45;

            fileoffs      = unc_get_u32be(meta + 1);
            e.type        = unc_get_u32be(meta + 5);
            e.creator     = unc_get_u32be(meta + 9);
            e.create_date = unc_get_u32be(meta + 13);
            e.mod_date    = unc_get_u32be(meta + 17);
            e.finder_flags = unc_get_u16be(meta + 21);
            filecrc       = unc_get_u32be(meta + 23);
            flags         = unc_get_u16be(meta + 27);
            rsrclen       = unc_get_u32be(meta + 29);
            datalen       = unc_get_u32be(meta + 33);
            rcomp         = unc_get_u32be(meta + 37);
            dcomp         = unc_get_u32be(meta + 41);

            e.rsrc_size = rsrclen;
            e.data_size = datalen;
            e.comp_rsrc_size = rcomp;
            e.comp_data_size = dcomp;
            e.method_rsrc = (flags & 2) ? 1 : 0;   /* 1 = LZH+RLE, 0 = RLE */
            e.method_data = (flags & 4) ? 1 : 0;

            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; goto out; }
            if (sret > 0) continue;               /* skipped: no decode */

            est = UNC_OK;
            if (flags & 1) {
                est = UNC_ERR_ENCRYPTED;
            } else if (c->opt.list_only) {
                est = UNC_OK;                     /* metadata only */
            } else if (fileoffs + rcomp < fileoffs ||
                       fileoffs + rcomp + dcomp < fileoffs ||
                       (fsize != UNC_SIZE_UNKNOWN &&
                        fileoffs + rcomp + dcomp > fsize)) {
                est = UNC_ERR_CORRUPT;            /* forks outside file */
            } else {
                crc = 0xFFFFFFFFu;
                est = cpt_fork(c, UNC_FORK_RSRC, fileoffs, rcomp, rsrclen,
                               flags & 2, &crc, iobuf, iocap, obuf, ocap,
                               hz, window);
                if (est == UNC_OK)
                    est = cpt_fork(c, UNC_FORK_DATA, fileoffs + rcomp,
                                   dcomp, datalen, flags & 4, &crc,
                                   iobuf, iocap, obuf, ocap, hz, window);
                if (est == UNC_OK && crc != filecrc) est = UNC_ERR_CRC;
            }
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
            if (est == UNC_ERR_SINK || est == UNC_ERR_ABORTED ||
                est == UNC_ERR_IO) {
                err = est;                        /* fatal, stop the walk */
                goto out;
            }
        }
    }

out:
    unc_free(c->al, hz);
    unc_free(c->al, iobuf);
    return err;
}

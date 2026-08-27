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
/* Eight bytes in front of an encrypted entry's stream: decrypted, then
 * discarded. See cpt_entry_forks. */
#define CPT_CRYPT_PREAMBLE 8u
/* An index bigger than this is not worth an allocation attempt;
 * the record-at-a-time walk reads it either way. */
#define CPT_INDEX_MAX 262144u
#define CPT_BLOCK    0x1fff0u   /* cost units per Huffman-tree block */
#define CPT_ESC1     0x81
#define CPT_ESC2     0x82

/* ------------------------------------------------------------------ */
/* Probe: signature byte + full index CRC walk, as XADMaster's        */
/* recognizeFileWithHandle does. A 1-byte magic is far too weak on    */
/* its own.                                                           */
/* ------------------------------------------------------------------ */

UncFormat unc_cpt_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint8_t buf[256];   /* max chunk: 255-byte archive comment; entries
                         * are smaller (127-byte name + 45 meta) */
    uint32_t offset, crc, storedcrc, fsize;
    uint32_t nentries, commentlen, i;

    if (len < 8 || head[0] != 1) return UNC_FORMAT_UNKNOWN;
    offset = unc_get_u32be(head + 4);
    fsize = io->size(io->ctx);
    if (fsize != UNC_SIZE_UNKNOWN && (offset + 7 < offset || offset + 7 > fsize))
        return UNC_FORMAT_UNKNOWN;

    if (unc_read_at(io, offset, buf, 7) != UNC_OK) return UNC_FORMAT_UNKNOWN;
    storedcrc = unc_get_u32be(buf);
    crc = unc_crc32(0xFFFFFFFFu, buf + 4, 3);
    nentries = unc_get_u16be(buf + 4);
    commentlen = buf[6];

    if (commentlen) {
        if (unc_read_full(io, buf, (int32_t)commentlen) != UNC_OK) return UNC_FORMAT_UNKNOWN;
        crc = unc_crc32(crc, buf, (int32_t)commentlen);
    }

    for (i = 0; i < nentries; i++) {
        uint32_t namelen, metalen, left;
        if (unc_read_full(io, buf, 1) != UNC_OK) return UNC_FORMAT_UNKNOWN;
        crc = unc_crc32(crc, buf, 1);
        namelen = buf[0] & 0x7f;
        metalen = (buf[0] & 0x80) ? 2 : 45;
        left = namelen + metalen;
        if (unc_read_full(io, buf, (int32_t)left) != UNC_OK) return UNC_FORMAT_UNKNOWN;
        crc = unc_crc32(crc, buf, (int32_t)left);
    }
    return (crc == storedcrc)
           ? UNC_FORMAT_COMPACTPRO : UNC_FORMAT_UNKNOWN;
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


void unc_cpt_rle_start(CptRle *r, UncCtx *c, UncFork fork,
                          uint32_t outlen, uint32_t crc,
                          uint8_t *obuf, uint32_t ocap)
{
    unc_fork_out(&r->out, c, fork, !c->opt.test_only, UNC_CK_CRC32,
                 obuf, ocap);
    r->out.crc32 = crc;
    r->remaining = outlen;
    r->state = CPT_RLE_NONE;
    r->saved = 0;
    r->err = UNC_OK;
}

int unc_cpt_rle_flush(CptRle *r)
{
    int e = unc_fork_flush(&r->out);
    if (e != UNC_OK) r->err = e;
    return e;
}

static int cpt_rle_emit(CptRle *r, uint8_t b)
{
    int e = unc_fork_put(&r->out, b);
    r->remaining--;
    return e;
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
int unc_cpt_lzh_fork(CptRle *rle, UncBufIn *in, CptLzh *hz,
                     uint8_t *window, uint32_t blocksize)
{
    UncBitIn bi;
    uint32_t wpos = 0;
    uint32_t blockcost = blocksize;   /* force tree read on first pass */
    uint32_t blockstart = 0;
    int first = 1, err;
    uint32_t i;

    for (i = 0; i < CPT_WINDOW; i++) window[i] = 0;
    unc_bitin_init(&bi, in);

    while (rle->remaining > 0) {
        if (blockcost >= blocksize) {
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
int unc_cpt_rle_fork(CptRle *rle, UncBufIn *in, uint32_t complen)
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

/* Compact Pro writes every address as (volume, offset within that
 * volume's file) — the volume byte sits in front of the offset in each
 * file entry, and in an unsegmented archive it is 1 and the offset is
 * absolute. So these two make the reader indifferent to which it has,
 * exactly as zip_seek/zip_skip do in fmt_exo.c: position, then read
 * forward, and a segmented set rolls into its next segment on its own.
 *
 * DERIVED, not transcribed — the mapping was measured on sets cut by
 * Compact Pro itself; see fmt_cptseg.c and DECISIONS.md 2026-08-14. */
static int cpt_seek(UncCtx *c, uint32_t vol, uint32_t off)
{
    if (!c->segmap) {
        /* One file, and an entry that says it lives in another volume:
         * the caller was handed one segment of a set and nothing else.
         * Not corrupt — incomplete. */
        if (vol > 1) return UNC_ERR_SEGMENTED;
        return c->io->seek(c->io->ctx, off) < 0 ? UNC_ERR_IO : UNC_OK;
    }
    if (vol < 1 || vol > c->segmap->nparts) return UNC_ERR_SEGMENTED;
    return c->segmap->seek_part(c->segmap->ctx, (int)vol, off);
}

static int cpt_read_at(UncCtx *c, uint32_t vol, uint32_t off,
                       void *buf, int32_t len)
{
    int err = cpt_seek(c, vol, off);
    if (err != UNC_OK) return err;
    return unc_read_full(c->io, buf, len);
}

/* The index, held in memory while the entries are walked.
 *
 * Every entry's record has to be read from the index and its forks from
 * wherever the entry lives, and in a segmented set those are different
 * SEGMENTS — so alternating between them costs a part open each way. On
 * a floppy that is a disk swap each way. Measured before this existed:
 * 19 opens and 8 backward crossings on a 4-segment set whose floor is 5
 * and 1. The zip reader met the same problem and answered it the same
 * way (DECISIONS.md 2026-08-09).
 *
 * It is an allocation that may be refused, so the record-at-a-time walk
 * stays as the fallback: same bytes out, more crossings. */
typedef struct {
    uint8_t *buf;        /* NULL: read records through cpt_read_at    */
    uint32_t base;       /* offset the buffer starts at, within `vol` */
    uint32_t len;
    uint32_t vol;
} CptIndex;

static int cpt_index_read(UncCtx *c, const CptIndex *ix, uint32_t off,
                          void *buf, int32_t len)
{
    if (ix->buf && off >= ix->base && len >= 0 &&
        (uint32_t)len <= ix->len - (off - ix->base)) {
        uint8_t *d = (uint8_t *)buf;
        const uint8_t *sp = ix->buf + (off - ix->base);
        int32_t i;
        for (i = 0; i < len; i++) d[i] = sp[i];
        return UNC_OK;
    }
    return cpt_read_at(c, ix->vol, off, buf, len);
}

static int cpt_fork(UncCtx *c, UncFork fork, uint32_t vol, uint32_t at,
                    uint32_t complen,
                    uint32_t outlen, int lzh, uint32_t *crc,
                    uint8_t *iobuf, uint32_t iocap,
                    uint8_t *obuf, uint32_t ocap,
                    CptLzh *hz, uint8_t *window, UncCrypt *cr, int quiet,
                    uint32_t skip)
{
    UncBufIn in;
    CptRle rle;
    int err;

    if (complen == 0 || outlen == 0) {
        /* macutils cpt_wrfile returns before writing anything when the
         * compressed fork is empty, whatever the claimed output size. */
        return UNC_OK;
    }
    if (complen < skip) return UNC_ERR_CORRUPT;
    {
        int serr = cpt_seek(c, vol, at);
        if (serr != UNC_OK) return serr;
    }
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = complen;   /* corrupt streams must not read past the fork */
    /* The cipher runs across BOTH forks of an entry without resetting,
     * so `cr` arrives already keyed and already advanced by whatever
     * the resource fork consumed. */
    if (cr) in.crypt = cr;
    /* An encrypted entry's stream opens with eight bytes that are
     * decrypted and thrown away — Compact Pro moves its read cursor
     * past them (`CODE` 3 @0x1f5e) — and their length is counted in the
     * first non-empty fork's compressed size. Reading them is not
     * optional: they are what the cipher's state has consumed by the
     * time the real data starts. */
    while (skip-- > 0) {
        if (unc_bufin_next(&in) < 0) return in.err;
    }

    unc_cpt_rle_start(&rle, c, fork, outlen, *crc, obuf, ocap);
    /* A password candidate is graded by the CRC alone; it must not
     * reach the sink. */
    if (quiet) rle.out.write = 0;
    if (lzh) err = unc_cpt_lzh_fork(&rle, &in, hz, window, CPT_BLOCK);
    else     err = unc_cpt_rle_fork(&rle, &in, complen);
    if (err == UNC_OK && rle.remaining > 0) err = UNC_ERR_TRUNCATED;
    if (err == UNC_OK || err == UNC_ERR_TRUNCATED || err == UNC_ERR_CORRUPT)
        if (unc_cpt_rle_flush(&rle) != UNC_OK) err = rle.err;
    *crc = rle.out.crc32;
    return err;
}

/* Both forks of one entry, in the order they are stored: resource
 * first, then data, with one CRC-32 across the pair. */
static int cpt_entry_forks(UncCtx *c, uint32_t vol, uint32_t at,
                           uint32_t rcomp, uint32_t dcomp,
                           uint32_t rsrclen, uint32_t datalen, uint32_t flags,
                           uint32_t *crc, uint8_t *iobuf, uint32_t iocap,
                           uint8_t *obuf, uint32_t ocap, CptLzh *hz,
                           uint8_t *window, UncCrypt *cr, int quiet)
{
    /* The eight-byte preamble of an encrypted entry belongs to the FIRST
     * fork that has any bytes at all, and is counted in its compressed
     * length: a 400-byte resource fork is stored as 408, and a file with
     * no resource fork puts the eight in front of the data fork
     * (measured on three archives Compact Pro itself wrote). */
    uint32_t rskip = 0, dskip = 0;
    int est;

    if (cr) {
        if (rcomp) rskip = CPT_CRYPT_PREAMBLE;
        else       dskip = CPT_CRYPT_PREAMBLE;
    }
    est = cpt_fork(c, UNC_FORK_RSRC, vol, at, rcomp, rsrclen,
                   (int)(flags & 2), crc, iobuf, iocap, obuf, ocap,
                   hz, window, cr, quiet, rskip);
    if (est == UNC_OK)
        est = cpt_fork(c, UNC_FORK_DATA, vol, at + rcomp, dcomp, datalen,
                       (int)(flags & 4), crc, iobuf, iocap, obuf, ocap,
                       hz, window, cr, quiet, dskip);
    return est;
}

/* ------------------------------------------------------------------ */
/* Encrypted entries                                                  */
/*                                                                    */
/* Compact Pro stores NOTHING that verifies a password — its own       */
/* message says so ("The password supplied is incorrect or the archive */
/* is damaged"), and the entry's CRC-32 is the only evidence there is. */
/* So a candidate key can only be graded by decoding the whole entry,  */
/* and an encrypted entry is therefore decoded TWICE: once writing     */
/* nothing, to find the key, and once to write it.                     */
/*                                                                    */
/* Every encrypted entry pays that, not just the first. Grading the    */
/* first one and then trusting the password would save a pass, and     */
/* would be wrong for an archive whose files were added in two         */
/* sittings under two passwords: the second entry's CRC would fail     */
/* with its output already half written. Twice through a floppy-sized  */
/* entry is the cheaper mistake.                                       */
/* ------------------------------------------------------------------ */

static int cpt_encrypted_entry(UncCtx *c, uint32_t vol,
                               uint32_t at, uint32_t rcomp, uint32_t dcomp,
                               uint32_t rsrclen, uint32_t datalen,
                               uint32_t flags, uint32_t filecrc,
                               uint8_t *iobuf, uint32_t iocap,
                               uint8_t *obuf, uint32_t ocap, CptLzh *hz,
                               uint8_t *window, UncCrypt *cr)
{
    uint32_t crc;
    int est, attempt = 0;

    for (;;) {
        est = unc_password(c, attempt > 0);
        if (est != UNC_OK) return est;      /* nothing (more) to try */
        crc = 0xFFFFFFFFu;
        unc_crypt_cpt(cr, c->pw, c->pwlen);
        est = cpt_entry_forks(c, vol, at, rcomp, dcomp, rsrclen, datalen,
                              flags, &crc, iobuf, iocap, obuf, ocap,
                              hz, window, cr, 1);
        if (est == UNC_ERR_ABORTED || est == UNC_ERR_IO) return est;
        if (est == UNC_OK && crc == filecrc) break;
        /* Wrong key, or a damaged entry: indistinguishable here, and
         * the caller was the one who offered a password. */
        attempt++;
    }
    if (c->opt.test_only) return UNC_OK;    /* that pass WAS the test */

    crc = 0xFFFFFFFFu;
    unc_crypt_cpt(cr, c->pw, c->pwlen);
    est = cpt_entry_forks(c, vol, at, rcomp, dcomp, rsrclen, datalen,
                          flags, &crc, iobuf, iocap, obuf, ocap,
                          hz, window, cr, 0);
    if (est == UNC_OK && crc != filecrc) est = UNC_ERR_CRC;
    return est;
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
    uint32_t iocap = UNC_IOBUF, ocap = UNC_IOBUF;
    uint8_t path[UNC_NAME_MAX + 1];
    uint16_t plen = 0;
    uint32_t idxvol;
    CptIndex ix;
    UncCrypt *cr;
    int err = UNC_OK;

    fsize = c->io->size(c->io->ctx);

    /* The index is in the LAST segment of a set — "you must open the
     * FINAL segment", the manual, and the byte that says so is the only
     * non-zero index offset in the set. For one file that is volume 1
     * and this is all a no-op. */
    idxvol = c->segmap ? (uint32_t)c->segmap->nparts : 1u;

    if (cpt_read_at(c, idxvol, 0, head, 8) != UNC_OK) return UNC_ERR_FORMAT;
    if (head[0] != 1) return UNC_ERR_FORMAT;
    offset = unc_get_u32be(head + 4);
    if (c->segmap && offset == 0) return UNC_ERR_SEGMENTED;  /* not the last */

    if (cpt_read_at(c, idxvol, offset, meta, 7) != UNC_OK) return UNC_ERR_FORMAT;
    /* Index CRC was verified by the probe; re-deriving it here would
     * mean a second full pass, so trust the per-file CRCs instead. */
    nentries = unc_get_u16be(meta + 4);
    commentlen = meta[6];
    ipos = offset + 7 + commentlen;

    iobuf = (uint8_t *)unc_alloc(c->al,
                                 iocap + ocap + CPT_WINDOW +
                                 (uint32_t)sizeof *cr);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;
    window = obuf + ocap;
    cr = (UncCrypt *)(void *)(window + CPT_WINDOW);
    hz = (CptLzh *)unc_alloc(c->al, (uint32_t)sizeof *hz);
    if (!hz) { unc_free(c->al, iobuf); return UNC_ERR_MEM; }

    /* LAST, and deliberately: this one is an optimisation and the two
     * above are not, so it gets what is left rather than competing for
     * what they need. Refused, the walk simply reads each record where
     * it lies — which for a segmented set is more part opens (and on a
     * floppy, more disk swaps) for exactly the same bytes. */
    ix.buf = NULL;
    ix.base = offset;
    ix.len = 0;
    ix.vol = idxvol;
    {
        /* Everything from the index CRC to the end of the file — or of
         * the final segment — is the index. */
        uint32_t end = c->segmap
            ? c->segmap->part_size(c->segmap->ctx, (int)idxvol) : fsize;
        if (end != UNC_SIZE_UNKNOWN && end > offset &&
            end - offset <= CPT_INDEX_MAX) {
            uint32_t want = end - offset;
            uint8_t *b = (uint8_t *)unc_alloc(c->al, want);
            if (b) {
                if (cpt_read_at(c, idxvol, offset, b, (int32_t)want) == UNC_OK) {
                    ix.buf = b;
                    ix.len = want;
                } else {
                    unc_free(c->al, b);
                }
            }
        }
    }



    /* The archive comment, which belongs to no entry and so has no
     * place in the stream of forks: it goes to the sink's own comment
     * callback, once, before the first entry. A host that has none set
     * gets what every host got before — the bytes are part of the index
     * the probe already CRC'd, and nothing more happens to them.
     * iobuf is the scratch: 4 KB against a length that is one byte. */
    if (commentlen && c->sink->comment) {
        if (cpt_index_read(c, &ix, offset + 7, iobuf,
                           (int32_t)commentlen) != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            goto out;
        }
        if (c->sink->comment(c->sink->ctx, iobuf,
                             (uint16_t)commentlen) < 0) {
            err = UNC_ERR_SINK;
            goto out;
        }
    }

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

        if (cpt_index_read(c, &ix, ipos, name, 1) != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            goto out;
        }
        ipos++;
        namelen = name[0] & 0x7f;
        isdir = name[0] & 0x80;
        if (namelen &&
            cpt_index_read(c, &ix, ipos, name, (int32_t)namelen) != UNC_OK) {
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
            if (cpt_index_read(c, &ix, ipos, meta, 2) != UNC_OK) {
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
            uint32_t fileoffs, filecrc, flags, filevol;
            uint32_t rsrclen, datalen, rcomp, dcomp;
            uint32_t crc;
            int est;

            if (cpt_index_read(c, &ix, ipos, meta, 45) != UNC_OK) {
                err = UNC_ERR_TRUNCATED;
                goto out;
            }
            ipos += 45;

            filevol       = meta[0];
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
            if (c->opt.list_only && (flags & 1)) {
                est = UNC_OK;                     /* metadata only */
            } else if (flags & 1) {
                est = cpt_encrypted_entry(c, filevol, fileoffs,
                                          rcomp, dcomp, rsrclen, datalen,
                                          flags, filecrc, iobuf, iocap,
                                          obuf, ocap, hz, window, cr);
            } else if (c->opt.list_only) {
                est = UNC_OK;                     /* metadata only */
            } else if (fileoffs + rcomp < fileoffs ||
                       fileoffs + rcomp + dcomp < fileoffs ||
                       (!c->segmap && fsize != UNC_SIZE_UNKNOWN &&
                        fileoffs + rcomp + dcomp > fsize)) {
                /* Only within one file does "past the end" mean
                 * anything: across a set the forks legitimately run off
                 * the end of the segment they start in, and the reader
                 * rolls into the next one. A short set is caught by the
                 * read, which cannot roll past the last part. */
                est = UNC_ERR_CORRUPT;            /* forks outside file */
            } else {
                crc = 0xFFFFFFFFu;
                est = cpt_entry_forks(c, filevol, fileoffs, rcomp, dcomp,
                                      rsrclen, datalen, flags, &crc,
                                      iobuf, iocap, obuf, ocap, hz, window,
                                      NULL, 0);
                if (est == UNC_OK && crc != filecrc) est = UNC_ERR_CRC;
            }
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
            if (unc_fatal(est)) {
                err = est;                        /* fatal, stop the walk */
                goto out;
            }
        }
    }

out:
    if (ix.buf) unc_free(c->al, ix.buf);
    unc_free(c->al, hz);
    unc_free(c->al, iobuf);
    return err;
}

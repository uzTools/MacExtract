/*
 * fmt_zipseg.c — one part of a spanned ("split") zip set.
 *
 * A spanned zip is the plainest segmentation there is: the parts
 * concatenate, in order, with nothing added and nothing to strip. What
 * makes it work is that the archive's own offsets are already written
 * as (part, offset within that part) pairs, so the reader never needs
 * to know where the cuts fell — it only needs the SIZE of every part
 * before it.
 *
 *   Source: reference/XADMaster/XADZipParser.m, -offsetForVolume:offset:
 *   ("for(i=0;i<count && i<disk;i++) offset+=sizes[i]") — LGPL, see
 *   NOTICE. The pairs live in the central directory ("disk number
 *   start", offset 34) and in the end-of-central-directory record
 *   ("number of this disk" at 4, "disk where the central directory
 *   starts" at 6). unc_zip_extract does the translation; this file
 *   only works out how many parts there are.
 *
 * Which is the whole difficulty. A spanned zip records the part count
 * in exactly one place, the end-of-central-directory record, which is
 * in the LAST part. It records nothing at all in the parts between the
 * first and the last: those are undistinguished archive data, and no
 * amount of looking at one will say which set it belongs to or where
 * it goes. So:
 *
 *   - the last part is recognized by its EOCD, and it is the only part
 *     this file can describe;
 *   - the first part is recognized because a local file header sits at
 *     offset 4 rather than 0 (source: XADZipParser.m
 *     +recognizeFileWithHandle:, `bytes[4..7] == PK\3\4`). The four
 *     bytes it is displaced by measure 50 4B 07 08 in Info-ZIP 3.0's
 *     `zip -s` output (MEASURED here, 2026-08-09; no reference in this
 *     repository documents them, so the probe does not require them);
 *   - everything in between is invisible, and `unar` refuses such a
 *     part too (MEASURED: `unar split.z03` exits 1 while `unar
 *     split.z01` and `unar split.zip` both read the whole set).
 *
 * A trap worth naming, because it is what a leading `PK\7\8` really
 * means: `zip -s` writes that marker whenever it is splitting, INCLUDING
 * when the result fits in one file. Such an archive is a normal zip with
 * a four-byte hat and an EOCD that says "disk 0" — nothing is missing
 * and nothing needs joining. Reading the marker as "this is a segment"
 * would refuse a file that extracts perfectly well. The EOCD is the
 * authority; the marker is not (MEASURED, 2026-08-09).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* EOCD: 22 fixed bytes plus a comment of up to 65,535. */
#define ZS_EOCD_FIXED   22
#define ZS_EOCD_MAXBACK (ZS_EOCD_FIXED + 65535u)

/* Scan backwards for the end-of-central-directory signature.
 *
 * Deliberately allocation-free. It used to be a 66,000-byte buffer in
 * unc_zip_extract holding the whole possible tail, which on a 1 MB Mac
 * is a large fraction of the heap and, for a segmented set, spans two
 * parts and so costs a disk swap to read. A window on the stack keeps
 * this within the 68000 discipline (call depth <= 4 KB) at the cost of
 * re-reading 3 bytes per step, and is now the only such scan in the
 * engine — the describe path, whole-file extraction and segmented
 * extraction all come here.
 *
 * `end` is one past the last byte that may be scanned: the file size
 * for a whole archive, the LAST PART's size for a segmented one, since
 * that is where a zip writes the record.
 *
 * Returns UNC_OK with *at set, or UNC_ERR_FORMAT if there is none. */
int unc_zip_scan_eocd(void *ctx, UncZipReadAt rd, uint32_t end, uint32_t *at)
{
    uint8_t win[512 + 3];
    uint32_t back = end < ZS_EOCD_MAXBACK ? end : ZS_EOCD_MAXBACK;
    uint32_t floor_ = end - back;     /* earliest offset worth reading */
    uint32_t hiend = end;             /* exclusive end of this window */

    if (end < ZS_EOCD_FIXED) return UNC_ERR_FORMAT;

    while (hiend > floor_) {
        uint32_t span = hiend - floor_ < 512u ? hiend - floor_ : 512u;
        uint32_t start = hiend - span;
        /* Carry 3 bytes of the NEXT window down so a signature
         * straddling the boundary is still seen whole. */
        uint32_t take = span + (end - hiend < 3u ? end - hiend : 3u);
        /* Highest start position whose four signature bytes were read.
         * In the topmost window there is nothing past `hiend`, so the
         * last three positions cannot hold a signature at all. */
        uint32_t hi = take >= 3u ? take - 3u : 0u;
        uint32_t i;

        if (hi > span) hi = span;
        if (rd(ctx, start, win, (int32_t)take) != UNC_OK)
            return UNC_ERR_FORMAT;
        for (i = hi; i-- > 0; ) {
            if (win[i] == 'P' && win[i + 1] == 'K' &&
                win[i + 2] == 5 && win[i + 3] == 6) {
                /* The record must fit in what is being scanned. */
                if (start + i + ZS_EOCD_FIXED > end) continue;
                *at = start + i;
                return UNC_OK;
            }
        }
        hiend = start;
    }
    return UNC_ERR_FORMAT;
}

/* The scanner's reader, for a caller that has a plain stream. */
static int zs_io_read_at(void *ctx, uint32_t off, void *buf, int32_t len)
{
    return unc_read_at((UncIO *)ctx, off, buf, len);
}

static int zs_find_eocd(UncIO *io, uint32_t fsize, uint32_t *at)
{
    return unc_zip_scan_eocd(io, zs_io_read_at, fsize, at);
}

/* Read the two disk numbers out of the EOCD at `at`. */
static int zs_read_eocd(UncIO *io, uint32_t at, uint32_t *disknum,
                        uint32_t *cddisk)
{
    uint8_t e[ZS_EOCD_FIXED];
    if (unc_read_at(io, at, e, ZS_EOCD_FIXED) != UNC_OK) return UNC_ERR_FORMAT;
    *disknum = unc_get_u16le(e + 4);
    *cddisk  = unc_get_u16le(e + 6);
    return UNC_OK;
}

/* Nonzero if a local file header sits at offset 4 — the shape `zip -s`
 * gives the first part of a set. Source: XADZipParser.m
 * +recognizeFileWithHandle:. */
static int zs_head_is_first_part(const uint8_t *head, int32_t len)
{
    return len >= 8 && head[4] == 'P' && head[5] == 'K' &&
           head[6] == 3 && head[7] == 4;
}

int unc_zipseg_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t fsize, at, disknum, cddisk;

    if (!io) return 0;
    fsize = io->size(io->ctx);
    if (fsize == UNC_SIZE_UNKNOWN) return 0;

    if (zs_find_eocd(io, fsize, &at) == UNC_OK) {
        if (zs_read_eocd(io, at, &disknum, &cddisk) != UNC_OK) return 0;
        /* An EOCD that says "disk 0" describes a set of one, i.e. an
         * ordinary zip — including the one `zip -s` writes when the
         * archive did not need splitting after all. */
        return disknum != 0;
    }

    /* No EOCD anywhere: this cannot be a whole archive. If it has the
     * first part's shape, say so; unc_zip_probe would otherwise claim
     * it and the failure would read as "not a zip". */
    return zs_head_is_first_part(head, len);
}

int unc_zipseg_describe(UncIO *io, UncSegmentDesc *desc)
{
    uint32_t fsize, at, disknum, cddisk;
    int32_t i;

    if (!io || !desc) return UNC_ERR_FORMAT;
    fsize = io->size(io->ctx);
    if (fsize == UNC_SIZE_UNKNOWN) return UNC_ERR_FORMAT;
    if (zs_find_eocd(io, fsize, &at) != UNC_OK) return UNC_ERR_FORMAT;
    if (zs_read_eocd(io, at, &disknum, &cddisk) != UNC_OK) return UNC_ERR_FORMAT;

    if (disknum == 0) return UNC_ERR_FORMAT;      /* an ordinary zip */
    if (disknum == 0xFFFFu) return UNC_ERR_UNSUPPORTED;  /* zip64 */
    if (disknum + 1 > UNC_SEG_MAX_PARTS) return UNC_ERR_UNSUPPORTED;
    if (cddisk > disknum) return UNC_ERR_CORRUPT;

    desc->scheme   = UNC_FORMAT_ZIPSEG;
    desc->head_len = 0;                 /* the parts simply concatenate */
    desc->nparts   = (uint16_t)(disknum + 1);
    desc->part     = desc->nparts;      /* the EOCD is in the last part */
    desc->total    = UNC_SIZE_UNKNOWN;  /* measured by opening them all */

    /* Nothing else is known: a zip stores no original filename, no
     * fingerprint and no fork sizes. Left zeroed rather than guessed. */
    desc->name[0]  = 0;
    desc->name_len = 0;
    for (i = 0; i < UNC_SEG_FP_LEN; i++) desc->fp[i] = 0;
    desc->data_size = desc->rsrc_size = 0;
    desc->type = desc->creator = 0;
    desc->finder_flags = 0;
    desc->create_date = desc->mod_date = 0;
    return UNC_OK;
}

int unc_zipseg_extract(UncCtx *c)
{
    /* A part on its own. Unlike a StuffIt set, a spanned zip of one
     * part does not exist — such an archive records "disk 0" and is
     * read as an ordinary zip — so there is nothing this can do but
     * name the problem. */
    (void)c;
    return UNC_ERR_SEGMENTED;
}

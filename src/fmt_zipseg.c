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
 *   Source: reference/notes/zip_appnote.txt (PKWARE APPNOTE.TXT 6.3.10),
 *   sections 4.3.12 and 4.3.16. The pairs live in the central directory
 *   ("disk number start", offset 34) and in the end-of-central-directory
 *   record ("number of this disk" at 4, "number of the disk with the
 *   start of the central directory" at 6). unc_zip_extract does the
 *   translation; this file only works out how many parts there are.
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
 *     offset 4 rather than 0. The four bytes it is displaced by measure
 *     50 4B 07 08 in Info-ZIP 3.0's `zip -s` output (MEASURED here,
 *     2026-08-09), which is the 0x08074b50 of APPNOTE.TXT 8.5.3: "a
 *     special spanning signature as the first 4 bytes of the first
 *     segment of the archive ... followed immediately by the local
 *     header signature for the first file". The probe still does not
 *     require it, for the reason below;
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
 * APPNOTE.TXT 8.5.4 says that case is written with a DIFFERENT marker,
 * 0x30304b50, "if the spanning or splitting process starts but only
 * requires one segment" — and the measurement above is Info-ZIP not
 * doing that. Which is the argument for ignoring the marker rather
 * than against it: two implementations already disagree about what the
 * four bytes mean, and 8.5.5 adds that 0x08074b50 "is also used by some
 * ZIP implementations as a marker for the Data Descriptor record". A
 * signature that three things can mean is not evidence. Nothing here
 * reads either value; the displacement is all that is tested, so both
 * markers and any third one behave identically.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_zipseg_priv.h"

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
 * The window is 1 KB rather than the 512 B it was, because the cost that
 * matters is not the instructions. A whole zip finds its record in the
 * first window and pays one read; a file that is NOT a zip walks the
 * whole 65,557 bytes, which at 512 B was up to 129 SetFPos + FSRead
 * pairs — on a floppy, a head move and 64 KB read per archive opened.
 * At 1 KB it is 65. Widening does not change how many BYTES are scanned
 * and so buys only ~6 % of the instructions (measured); the reads are
 * the point, and no Linux measurement here can show them.
 *
 * It stops at 1 KB rather than the 4 KB that would make the reads 17,
 * because this window IS the frame: at 4 KB it would be the deepest
 * stack chain in the engine on its own (FORMATS.md, `Stack`).
 *
 * `end` is one past the last byte that may be scanned: the file size
 * for a whole archive, the LAST PART's size for a segmented one, since
 * that is where a zip writes the record.
 *
 * Returns UNC_OK with *at set, or UNC_ERR_FORMAT if there is none. */
#define ZS_WINDOW 1024u

int unc_zip_scan_eocd(void *ctx, UncZipReadAt rd, uint32_t end, uint32_t *at)
{
    uint8_t win[ZS_WINDOW + 3];
    uint32_t back = end < ZS_EOCD_MAXBACK ? end : ZS_EOCD_MAXBACK;
    uint32_t floor_ = end - back;     /* earliest offset worth reading */
    uint32_t hiend = end;             /* exclusive end of this window */

    if (end < ZS_EOCD_FIXED) return UNC_ERR_FORMAT;

    while (hiend > floor_) {
        uint32_t span = hiend - floor_ < ZS_WINDOW ? hiend - floor_ : ZS_WINDOW;
        uint32_t start = hiend - span;
        /* Carry 3 bytes of the NEXT window down so a signature
         * straddling the boundary is still seen whole. */
        uint32_t take = span + (end - hiend < 3u ? end - hiend : 3u);
        /* Highest start position whose four signature bytes were read.
         * In the topmost window there is nothing past `hiend`, so the
         * last three positions cannot hold a signature at all. */
        uint32_t hi = take >= 3u ? take - 3u : 0u;
        const uint8_t *p;
        uint32_t i;

        if (hi > span) hi = span;
        if (rd(ctx, start, win, (int32_t)take) != UNC_OK)
            return UNC_ERR_FORMAT;
        /* Walked with a pointer rather than indexed: this is 64 KB of
         * byte compares for every archive that is not a zip, and the
         * indexed form recomputed win + i four times a byte. */
        p = win + hi;
        while (p-- > win) {
            if (p[0] == 'P' && p[1] == 'K' && p[2] == 5 && p[3] == 6) {
                i = (uint32_t)(p - win);
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

int unc_zipseg_describe(UncIO *io, UncSegmentDesc *desc)
{
    uint32_t fsize, at;
    ZsEocd e;
    int32_t i;

    if (!io || !desc) return UNC_ERR_FORMAT;
    fsize = unc_io_size32(io);
    if (fsize == UNC_SIZE_UNKNOWN) return UNC_ERR_FORMAT;
    if (zs_find_eocd(io, fsize, &at) != UNC_OK) return UNC_ERR_FORMAT;
    if (zs_read_eocd(io, at, &e) != UNC_OK) return UNC_ERR_FORMAT;

    if (e.disknum == 0) return UNC_ERR_FORMAT;      /* an ordinary zip */
    if (e.disknum == 0xFFFFu) return UNC_ERR_UNSUPPORTED;  /* zip64 */
    if (e.disknum + 1 > UNC_SEG_MAX_PARTS) return UNC_ERR_UNSUPPORTED;
    if (e.cddisk > e.disknum) return UNC_ERR_CORRUPT;

    desc->scheme   = UNC_FORMAT_ZIPSEG;
    desc->head_len = 0;                 /* the parts simply concatenate */
    desc->nparts   = (uint16_t)(e.disknum + 1);
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

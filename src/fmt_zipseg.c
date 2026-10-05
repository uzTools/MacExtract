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

/* The scanner's reader, for a caller that has a plain stream. */
static int zs_io_read_at(void *ctx, uint32_t off, void *buf, int32_t len)
{
    return unc_read_at((UncIO *)ctx, off, buf, len);
}

static int zs_find_eocd(UncIO *io, uint32_t fsize, uint32_t *at)
{
    return unc_zip_scan_eocd(io, zs_io_read_at, fsize, at);
}

/* The six fields of the record both zip probes judge a file by.
 *
 * Source: reference/notes/zip_appnote.txt 4.3.16, the End of central
 * directory record, read in order from its signature: "number of this
 * disk" at 4, "number of the disk with the start of the central
 * directory" at 6, "total number of entries in the central directory on
 * this disk" at 8, "total number of entries in the central directory"
 * at 10, "size of the central directory" at 12, "offset of start of
 * central directory with respect to the starting disk number" at 16.
 * Every one is Intel byte order (4.4.1.1) and read a byte at a time. */
typedef struct {
    uint32_t disknum;    /* 4.4.19 */
    uint32_t cddisk;     /* 4.4.20 */
    uint32_t here;       /* 4.4.21 — entries in the directory on this disk */
    uint32_t total;      /* 4.4.22 */
    uint32_t cdsize;     /* 4.4.23 */
    uint32_t cdoff;      /* 4.4.24 */
} ZsEocd;

static int zs_read_eocd(UncIO *io, uint32_t at, ZsEocd *e)
{
    uint8_t r[ZS_EOCD_FIXED];
    if (unc_read_at(io, at, r, ZS_EOCD_FIXED) != UNC_OK) return UNC_ERR_FORMAT;
    e->disknum = unc_get_u16le(r + 4);
    e->cddisk  = unc_get_u16le(r + 6);
    e->here    = unc_get_u16le(r + 8);
    e->total   = unc_get_u16le(r + 10);
    e->cdsize  = unc_get_u32le(r + 12);
    e->cdoff   = unc_get_u32le(r + 16);
    return UNC_OK;
}

/* Does the record at `at` describe a central directory that is actually
 * there? Four bytes of signature are not evidence — measured, and this
 * function is what that measurement bought: five files of 8,364 that are
 * not archives at all carry `PK\5\6` by chance, and all five were claimed
 * as a spanned zip part by the disk number alone (FORMATS.md, *What the
 * zip pair claims, and what it costs*).
 *
 * Five of the six tests are arithmetic on fields already read, so they
 * cost nothing; the sixth is one four-byte read, and only on a file that
 * passed all five.
 *
 *   - an archive with no entries has nothing to extract, and `total` is
 *     what every count in the walk is bounded by;
 *   - the directory on ONE disk cannot hold more entries than the whole
 *     of it (4.4.21 against 4.4.22);
 *   - a set whose directory starts on a LATER part than its last is
 *     incoherent — unc_zipseg_describe already calls that UNC_ERR_CORRUPT;
 *   - a central file header is 46 bytes before its name (4.3.12), so a
 *     directory of `total` entries cannot be smaller than 46 × total. A
 *     LOWER bound and not an equality, because 4.3.13 lets a digital
 *     signature record follow the headers inside the same directory;
 *   - the record comes after the directory (4.3.6), so the `here`
 *     entries that are in THIS part lie in front of it and need 46
 *     bytes each there as well. This is the only test with any force
 *     left when the directory began on an earlier part, which is why it
 *     is not behind the condition below;
 *   - and where the directory is on THIS part — which is every
 *     single-file archive, `cddisk == disknum == 0` — it must fit in
 *     front of the record that points at it, and its first four bytes
 *     are the central file header signature of 4.3.12.
 *
 * The last bullet's two tests are the ones behind that condition, and
 * the condition is not caution: `zip -s` SPLITS the central directory
 * when it outgrows a part. Measured 2026-10-05 on a 1,201-entry set at
 * 64 KB per part — `disknum` 7 and `cddisk` 5, so eight parts with the
 * directory beginning in the sixth; `here` 238 of 1,201; `cdsize`
 * 132,048 in a file of 26,312 bytes, and `cdoff` an offset on that
 * sixth part where this one holds somebody's filename. Applying either
 * test to such a part refuses a set Info-ZIP writes, which is what the
 * first draft of this function did
 * (`tools/synth_zipsplit.py`, the `zspancd` case). */
static int zs_cd_is_there(UncIO *io, const ZsEocd *e, uint32_t at)
{
    uint8_t sig[4];

    if (e->total == 0 || e->here > e->total) return 0;
    if (e->cddisk > e->disknum) return 0;
    if (e->cdsize < e->total * 46u) return 0;
    if (at < e->here * 46u) return 0;
    if (e->cddisk != e->disknum) return 1;   /* not in this file to read */
    /* Written as a subtraction so a 0xFFFFFFFF field (Zip64's escape,
     * 4.4.23) cannot wrap the sum. */
    if (e->cdoff > at || e->cdsize > at - e->cdoff) return 0;
    if (unc_read_at(io, e->cdoff, sig, 4) != UNC_OK) return 0;
    return sig[0] == 'P' && sig[1] == 'K' && sig[2] == 1 && sig[3] == 2;
}

/* Nonzero if a local file header sits at offset 4 — the shape `zip -s`
 * gives the first part of a set (APPNOTE.TXT 8.5.3; see file comment
 * for why the four bytes in front of it are not examined). */
static int zs_head_is_first_part(const uint8_t *head, int32_t len)
{
    return len >= 8 && head[4] == 'P' && head[5] == 'K' &&
           head[6] == 3 && head[7] == 4;
}

/* Both halves of the zip pair's answer, off one backwards scan.
 *
 * This probe is the only place the scan happens during a sniff, and it
 * runs for every file the probes above it did not claim — 50 % of all the
 * reads a sniff of the corpus makes, measured (FORMATS.md, *What the zip
 * pair claims, and what it costs*). So the record it finds answers BOTH
 * questions while it is in hand, rather than being thrown away for one of
 * them and scanned for again: an EOCD that says "disk 0" describes an
 * ordinary zip, wherever in the file its archive starts, and that is what
 * makes a self-extracting zip recognisable for one four-byte read. The
 * decoder needs nothing either way — it addresses the central directory
 * absolutely, from the same record.
 *
 * unc_zip_probe still does the head test, and is still reached: a zip
 * whose EOCD is cut off, an empty archive, and a stub glued in front of
 * one whose offsets were never adjusted all fail the corroboration here
 * and are claimed there, on the local file header at offset 0. */
UncFormat unc_zipseg_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t fsize, at;
    ZsEocd e;

    if (!io) return UNC_FORMAT_UNKNOWN;
    fsize = unc_io_size32(io);
    if (fsize == UNC_SIZE_UNKNOWN) return UNC_FORMAT_UNKNOWN;

    if (zs_find_eocd(io, fsize, &at) == UNC_OK) {
        if (zs_read_eocd(io, at, &e) != UNC_OK) return UNC_FORMAT_UNKNOWN;
        if (!zs_cd_is_there(io, &e, at)) return UNC_FORMAT_UNKNOWN;
        /* An EOCD that says "disk 0" describes a set of one, i.e. an
         * ordinary zip — including the one `zip -s` writes when the
         * archive did not need splitting after all. */
        return (e.disknum != 0) ? UNC_FORMAT_ZIPSEG : UNC_FORMAT_ZIP;
    }

    /* No EOCD anywhere: this cannot be a whole archive. If it has the
     * first part's shape, say so; unc_zip_probe would otherwise claim
     * it and the failure would read as "not a zip". */
    return (zs_head_is_first_part(head, len))
           ? UNC_FORMAT_ZIPSEG : UNC_FORMAT_UNKNOWN;
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

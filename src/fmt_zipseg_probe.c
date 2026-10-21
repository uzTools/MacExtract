/* fmt_zipseg_probe.c — the probe for one part of a spanned zip set, and
 * the end-of-central-directory reads it shares with the reader. Why the
 * scan is where it is, and what it costs, is fmt_zipseg.c's file comment.
 *
 * Every probe is in its reader's `_probe.c`, resident, so the reader can
 * be an overlay: unc_sniff calls every probe for every file it is handed,
 * before any image is chosen (DECISIONS.md 2026-10-20, *one place for
 * every probe*). What a probe and its reader share is defined once, here.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_zipseg_priv.h"

int zs_io_read_at(void *ctx, uint32_t off, void *buf, int32_t len)
{
    return unc_read_at((UncIO *)ctx, off, buf, len);
}

int zs_read_eocd(UncIO *io, uint32_t at, ZsEocd *e)
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

/*
 * unc_encinfo.c — does this archive contain an encrypted entry?
 *
 * Answered from the archive's own directory, before anything is decoded, for
 * the two formats that can answer without guessing: Compact Pro and zip. Both
 * keep a per-entry flag in a structure that is read in one place, so the
 * question costs a walk of that structure and nothing else.
 *
 * Why the engine and not the Macintosh shell: the offsets below belong to the
 * readers beside this file, and a second copy of a format's layout is what
 * rule #1 forbids. Every field here is cited to the reader it comes from.
 *
 * The answer is deliberately three-valued. UNKNOWN is not a failure: it is
 * what a format that does not advertise encryption (ARC says so in as many
 * words) and a structure that could not be read both deserve, and the caller
 * is expected to treat it exactly as "yes".
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* Compact Pro. Source: the layout comment in src/fmt_cpt.c, which has
 * been docs/formats/compact-pro.md's and the three wiki pages it
 * corrects since 2026-09-20 — this comment still named
 * XADCompactProParser.m and macutils' cpt.c until 2026-09-26 —
 *
 *   header: u8 signature, u8 volume, u16 xmagic, u32 index offset
 *   index:  u32 CRC, u16 nentries, u8 commentlen, comment,
 *           then nentries headers, each: u8 namelen (bit 7 = folder),
 *           name, then a folder's u16 subtree count or a file's 45 bytes.
 *
 * The 45 are u8 volume, u32 fileoffs, u32 type, u32 creator, u32 created,
 * u32 modified, u16 finderflags, u32 fileCRC, u16 flags, u32 rsrclen,
 * u32 datalen, u32 rsrccomplen, u32 datacomplen — so `flags`, whose bit 0
 * means encrypted, begins at offset 27. */
#define CPT_FILEREC     45
#define CPT_FLAGS_OFF   27

static int cpt_has_encrypted(UncIO *io)
{
    uint8_t buf[64];
    uint32_t idx, n, i;
    uint32_t pos;
    unc_off_t size = io->size ? io->size(io->ctx) : 0;

    if (size <= 0 || size > 0x7fffffffL) return UNC_ENC_UNKNOWN;
    if (unc_read_at(io, 0, buf, 8) != UNC_OK) return UNC_ENC_UNKNOWN;
    if (buf[0] != 1) return UNC_ENC_UNKNOWN;
    /* MULTI-PART SETS, which is what this pair of tests is for. Compact Pro
     * puts its index in the LAST segment — "you must open the FINAL segment",
     * per the manual quoted in src/fmt_cpt.c — so a first part has no index
     * to read, and a user opening a set opens the first part.
     *
     * The reader's own rule for the header's volume byte is `vol > 1` means
     * "one segment of a set" (cpt_seek_at), so 0 and 1 are a whole archive;
     * and the index offset "is the only non-zero one in the set", so a zero
     * there is a part rather than an archive with an empty index. The segment
     * probe claims such a file first, so both tests should be unreachable —
     * "should be" is not a guarantee, and what a wrong answer costs here is a
     * capability released on a maybe. */
    if (buf[1] > 1) return UNC_ENC_UNKNOWN;
    idx = unc_get_u32be(buf + 4);
    if (idx == 0 || idx + 7 > (uint32_t)size) return UNC_ENC_UNKNOWN;
    if (unc_read_at(io, idx, buf, 7) != UNC_OK) return UNC_ENC_UNKNOWN;
    n = unc_get_u16be(buf + 4);
    pos = idx + 7 + buf[6];                    /* past CRC, count, comment */

    for (i = 0; i < n; i++) {
        uint32_t namelen;
        if (pos >= (uint32_t)size) return UNC_ENC_UNKNOWN;
        if (unc_read_at(io, pos, buf, 1) != UNC_OK) return UNC_ENC_UNKNOWN;
        namelen = (uint32_t)(buf[0] & 0x7f);
        if (buf[0] & 0x80) {                   /* a folder: u16 subtree count */
            pos += 1 + namelen + 2;
            continue;
        }
        pos += 1 + namelen;
        if (unc_read_at(io, pos, buf, CPT_FILEREC) != UNC_OK)
            return UNC_ENC_UNKNOWN;
        if (unc_get_u16be(buf + CPT_FLAGS_OFF) & 1) return UNC_ENC_YES;
        pos += CPT_FILEREC;
    }
    return UNC_ENC_NO;
}

/* Zip. Source: the central-directory walk in src/fmt_exo.c — a 46-byte fixed
 * record, general-purpose flags at +8 (bit 0 = encrypted, which WinZip AES
 * entries also set), name/extra/comment lengths at +28/+30/+32. The EOCD is
 * found by the same backwards scan the reader uses. */
#define ZIP_CD_FIXED    46

static int zip_read_at(void *ctx, uint32_t pos, void *buf, int32_t len)
{
    return unc_read_at((UncIO *)ctx, pos, buf, len);
}

static int zip_has_encrypted(UncIO *io)
{
    uint8_t rec[ZIP_CD_FIXED];
    uint32_t eocd = 0, n, i, cdoffs, cdsize, pos;
    unc_off_t size = io->size ? io->size(io->ctx) : 0;

    if (size <= 0 || size > 0x7fffffffL) return UNC_ENC_UNKNOWN;
    if (unc_zip_scan_eocd(io, zip_read_at, (uint32_t)size, &eocd) != UNC_OK)
        return UNC_ENC_UNKNOWN;
    if (unc_read_at(io, eocd, rec, 22) != UNC_OK) return UNC_ENC_UNKNOWN;
    /* SPANNED SETS ARE THE POINT OF THIS BLOCK. A zip keeps its directory at
     * the END, so the first part of a multi-part set — the part a user is
     * told to open, and the only one they can be expected to open — has no
     * directory at all. Nothing here may answer NO for such a file.
     *
     * EOCD fields, PKWARE APPNOTE 4.3.16 and the reader's own checks in
     * src/fmt_exo.c: +4 this disk's number, +6 the disk the central
     * directory starts on, +8 entries on this disk, +10 entries in total,
     * +12 its size, +16 its offset. A single-volume archive has both disk
     * numbers 0 and both counts equal, and its directory lies inside the
     * file. Anything else is a part, a Zip64 archive whose real values are
     * in a locator this does not read, or damage — and all three deserve
     * the same answer. */
    if (unc_get_u16le(rec + 4) != 0 || unc_get_u16le(rec + 6) != 0)
        return UNC_ENC_UNKNOWN;
    if (unc_get_u16le(rec + 8) != unc_get_u16le(rec + 10))
        return UNC_ENC_UNKNOWN;
    n      = unc_get_u16le(rec + 10);
    cdsize = unc_get_u32le(rec + 12);
    cdoffs = unc_get_u32le(rec + 16);
    if (n == 0xffff || cdsize == 0xffffffffUL || cdoffs == 0xffffffffUL)
        return UNC_ENC_UNKNOWN;               /* Zip64: the truth is elsewhere */
    if (cdoffs > (uint32_t)size || cdsize > (uint32_t)size - cdoffs)
        return UNC_ENC_UNKNOWN;

    pos = cdoffs;
    for (i = 0; i < n; i++) {
        uint32_t namelen, extralen, commentlen;
        if (pos + ZIP_CD_FIXED > cdoffs + cdsize) return UNC_ENC_UNKNOWN;
        if (unc_read_at(io, pos, rec, ZIP_CD_FIXED) != UNC_OK)
            return UNC_ENC_UNKNOWN;
        if (unc_get_u32le(rec) != 0x02014b50UL) return UNC_ENC_UNKNOWN;
        if (unc_get_u16le(rec + 8) & 1) return UNC_ENC_YES;
        namelen    = unc_get_u16le(rec + 28);
        extralen   = unc_get_u16le(rec + 30);
        commentlen = unc_get_u16le(rec + 32);
        pos += ZIP_CD_FIXED + namelen + extralen + commentlen;
    }
    return UNC_ENC_NO;
}

int unc_archive_encrypted(UncFormat fmt, UncIO *io)
{
    if (io == NULL) return UNC_ENC_UNKNOWN;
    switch (fmt) {
    case UNC_FORMAT_COMPACTPRO: return cpt_has_encrypted(io);
    case UNC_FORMAT_ZIP:        return zip_has_encrypted(io);
    default:                    return UNC_ENC_UNKNOWN;
    }
}

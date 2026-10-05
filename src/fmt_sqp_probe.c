/* fmt_sqp_probe.c — the AppleLink package probe, kept resident.
 *
 * Split out so the decoder can live in an overlay: `unc_sniff` calls a probe
 * for every file it is handed, and a probe inside a blob would mean loading
 * the decoder to decide the file is not one (FORMATS.md, *Overlays*).
 *
 * A package has NO MAGIC NUMBER, and the probe this format had between
 * 2026-08-23 and 2026-09-27 was not a file test at all — it tokenized a
 * sentence in the StuffIt translator API's command language and so named
 * neither real package anything, for 35 days (BLOCKERS.md, *Withdrawn
 * claims*). What is tested here is the container's own arithmetic:
 *
 *   - a version byte of 0 or 1 (ReadFileAndBuildLinkedList @0x3074 takes
 *     those two and prints an error for anything else), and the eight
 *     bytes after it zero, as they are in both real packages;
 *   - at least one item, and a directory that FITS;
 *   - every record's name no longer than the Str31 field holds, and every
 *     level between 1 and one deeper than the item before it, which is
 *     all a folder tree can do (DoItemsForward @0x1ca2 descends one at a
 *     time);
 *   - and the members TILE: every fork's (offset, compressed length) lies
 *     inside the file, the first starts where the directory ends, the last
 *     ends at the last byte, and their lengths sum to exactly the space
 *     between. Both real packages tile to the byte, and nothing else here
 *     would reject a file whose directory looks plausible and whose bytes
 *     are somebody else's.
 *
 * What it costs a file that is NOT one: ten bytes already in `head`, and a
 * size the host has. The directory walk is reached only by a file that
 * passes the version test and the eight zero bytes, and it stops at the
 * first record that disagrees — so the worst case is a package, which pays
 * one pass over its own directory.
 *
 * THE TOLERANCE TO QUESTION FIRST, if a real package is ever reported
 * unrecognised, is the exact tiling: this requires the forks to cover
 * [directory end, EOF) with no gap and no byte to spare, which is what
 * Aladdin's writer produces — it appends each fork to the file as it
 * compresses it, and both real packages tile to the byte — but it is a
 * property of that writer rather than of the format, and an aligned or
 * padded package from some other version would fail it.
 *
 * And what it costs the MACHINE: 666 B of 68000 text, resident, which is
 * 666 B off every extraction's budget on a 1 MB Mac Plus. Two cheaper
 * shapes were measured and both were 6 B WORSE — a table of the two forks'
 * field offsets instead of the ternaries, and one helper for the two runs
 * of zero bytes instead of two loops (DECISIONS.md 2026-10-05).
 *
 * Source: at the fields; the rest of the format's provenance is
 * fmt_sqp.c's.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

UncFormat unc_sqp_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint8_t rec[90];
    uint32_t base, stride, pre, n, i, fsize, start;
    /* The deepest level the NEXT record may claim: one more than a
     * folder's, and no more than a file's, since only a folder can be
     * descended into. The first record must therefore be level 1. */
    uint32_t sum = 0, lo, hi, allowed = 1;
    int version;

    if (len < 10) return UNC_FORMAT_UNKNOWN;
    version = head[1];
    if (version > 1) return UNC_FORMAT_UNKNOWN;
    for (i = 2; i < 10; i++)
        if (head[i] != 0) return UNC_FORMAT_UNKNOWN;

    fsize = unc_io_size32(io);
    if (fsize == UNC_SIZE_UNKNOWN || fsize < 10) return UNC_FORMAT_UNKNOWN;

    if (version == 0) {
        n = head[0];
        base = 10;
        stride = 86;
        pre = 0;
    } else {
        base = 86u * head[0] + 10u;
        if (base + 12u > fsize) return UNC_FORMAT_UNKNOWN;
        if (unc_read_at(io, base, rec, 12) != UNC_OK)
            return UNC_FORMAT_UNKNOWN;
        /* The item count, then eight more bytes that are zero in both
         * real packages. The reader takes the count as a word. */
        if (unc_get_u16be(rec) != 0) return UNC_FORMAT_UNKNOWN;
        n = unc_get_u16be(rec + 2);
        for (i = 4; i < 12; i++)
            if (rec[i] != 0) return UNC_FORMAT_UNKNOWN;
        base += 12;
        stride = 90;
        pre = 4;
    }
    /* An empty package names nothing and is indistinguishable from a
     * file of zeros, which is why this is a test and not a tolerance. */
    if (n < 1) return UNC_FORMAT_UNKNOWN;
    if (base > fsize || n > (fsize - base) / stride)
        return UNC_FORMAT_UNKNOWN;
    start = base + stride * n;
    lo = fsize;
    hi = start;

    for (i = 0; i < n; i++, base += stride) {
        const uint8_t *r = rec + pre;
        uint32_t f;
        int folder = 0;

        if (unc_read_at(io, base, rec, (int32_t)stride) != UNC_OK)
            return UNC_FORMAT_UNKNOWN;
        if (pre) {
            uint32_t lv = unc_get_u16be(rec);
            folder = unc_get_u16be(rec + 2) != 0;
            if (lv < 1 || lv > allowed) return UNC_FORMAT_UNKNOWN;
            allowed = folder ? lv + 1 : lv;
        }
        if (r[36] > 31) return UNC_FORMAT_UNKNOWN;
        if (folder) continue;

        /* Each fork in turn, by its COMPRESSED length, which is what the
         * tiling is made of: zero means the fork is not there, and both
         * real packages then carry a zero offset with it. */
        for (f = 0; f < 2; f++) {
            uint32_t clen = unc_get_u32be(r + (f ? 4 : 8));
            uint32_t off  = unc_get_u32be(r + (f ? 16 : 12));
            if (clen == 0) continue;
            if (off < start || off > fsize || clen > fsize - off)
                return UNC_FORMAT_UNKNOWN;
            if (off < lo) lo = off;
            if (off + clen > hi) hi = off + clen;
            if (clen > fsize - sum) return UNC_FORMAT_UNKNOWN;
            sum += clen;
        }
    }
    if (hi != fsize || lo != start || sum != fsize - start)
        return UNC_FORMAT_UNKNOWN;
    return UNC_FORMAT_SQP;
}

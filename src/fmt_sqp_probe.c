/* fmt_sqp_probe.c — the AppleLink package probe, in the sniffer's image.
 *
 * Split out so the decoder can live in an overlay, and since 2026-10-21 in
 * the sniffer's own image with every other probe, run before the release
 * and given back with it (DECISIONS.md 2026-10-21, *the probes that left
 * with the bundle*).
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
 *   - every record's name between 1 and the 31 bytes a Str31 holds — the
 *     LOWER bound is what keeps a FILE OF ZEROS out, and it is the only
 *     test here such a file cannot satisfy: 96 zero bytes with two of
 *     them set pass all the rest, and 198 with four do on the version-1
 *     path (below, and BLOCKERS.md, *Withdrawn claims*) — and every level
 *     between 1 and one deeper than the item before it, which is all a
 *     folder tree can do (DoItemsForward @0x1ca2 descends one at a time);
 *   - and the members TILE: every fork's (offset, compressed length) lies
 *     inside the file, the first starts where the directory ends, the last
 *     ends at the last byte, and their lengths sum to exactly the space
 *     between. Both real packages tile to the byte, and nothing else here
 *     would reject a file whose directory looks plausible and whose bytes
 *     are somebody else's. It is VACUOUS when every compressed length is
 *     zero — `lo` stays at `fsize`, `hi` at `start` and the sum at
 *     0 == fsize - start — so a directory that declares no fork at all
 *     passes it, which is correct for a package of empty files and is
 *     why the name test has to carry the file of zeros.
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
 * And what it costs the MACHINE: 670 B of 68000 text, resident, which is
 * 670 B off every extraction's budget on a 1 MB Mac Plus. Two cheaper
 * shapes were measured and both were 6 B WORSE — a table of the two forks'
 * field offsets instead of the ternaries, and one helper for the two runs
 * of zero bytes instead of two loops (DECISIONS.md 2026-10-05). It was 666
 * until the name's lower bound arrived, and that bound is 4 B however it
 * is written: seven shapes were measured and five land on 670, because
 * the compiler emits the same `subq.b #1` + `cmpi.b #30` + `bhi` for
 * every way of spelling the range — while writing that wrap by hand in
 * 32-bit arithmetic costs 2 B MORE (DECISIONS.md 2026-10-06).
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
    /* A count of zero locates no record at all, so nothing below could
     * run. It does NOT keep a file of zeros out — the name test in the
     * walk is what does that (see the head of this file). */
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
        /* The name, 1..31 bytes. A record's name is the one the File
         * Manager returned for a file the writer had just enumerated, so
         * it is neither longer than the Str31 it was copied into nor
         * empty.
         *
         * Source: `AddItems` @0x22ac points the `ioNamePtr` of its
         * `CInfoPBRec` (+18, `a5@(-438)`) at a 32-byte buffer it has
         * just cleared, calls `PBGetCatInfo` @0x22be — `_HFSDispatch`
         * selector 9, the glue at 0x6500 — and bails on any error but
         * `fnfErr`; @0x2354 copies that buffer into the node's name
         * field with `pStrCpy`, which is the field `WrHFSDirectory`
         * @0x5f2e writes at record+36. */
        if (r[36] < 1 || r[36] > 31) return UNC_FORMAT_UNKNOWN;
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

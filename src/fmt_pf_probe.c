/* fmt_pf_probe.c — Private File's probe, in the sniffer's image.
 *
 * Split from fmt_pf.c so the reader can live in the StuffIt image, and since 2026-10-21 in
 * the sniffer's own image with every other probe, run before the release
 * and given back with it (DECISIONS.md 2026-10-21, *the probes that left
 * with the bundle*).
 * The format, and where every rule here comes from, is in fmt_pf.c's
 * header comment.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"
#include "fmt_pf_priv.h"

UncFormat unc_pf_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t size;
    uint8_t tail[4];

    if (len < (int32_t)PF_HDR) return UNC_FORMAT_UNKNOWN;
    /* PFEngine's own acceptance test, nothing looser and nothing tighter:
     * 'CSIT', u16 version == 2, u16 derivation and u16 cipher each <= 1,
     * s16 at 12 <= 0. A header it would refuse as an unknown METHOD is
     * still a Private File, and is named here so the entry can say so.
     * Written as byte compares rather than through unc_get_u16be: the
     * 68000 rebuilds every big-endian field with shifts before comparing
     * it, which made this probe 222 B (DECISIONS.md 2026-10-09, *the
     * specimen was one search away*). */
    if (head[0] != 'C' || head[1] != 'S' || head[2] != 'I' || head[3] != 'T')
        return UNC_FORMAT_UNKNOWN;
    if ((head[4] | head[6] | head[8]) != 0 || head[5] != 2 ||
        head[7] > 1 || head[9] > 1)
        return UNC_FORMAT_UNKNOWN;
    if (head[12] < 0x80 && (head[12] | head[13]) != 0)
        return UNC_FORMAT_UNKNOWN;
    /* And the footer's magic, which six header bytes alone cannot vouch
     * for: 'CSIT' is a creator code, and creator codes are everywhere. */
    if (!io) return UNC_FORMAT_UNKNOWN;
    size = unc_io_size32(io);
    if (size == UNC_SIZE_UNKNOWN || size < PF_FIXED) return UNC_FORMAT_UNKNOWN;
    if (unc_read_at(io, size - PF_FOOT, tail, 4) != UNC_OK)
        return UNC_FORMAT_UNKNOWN;
    return unc_get_u32be(tail) == PF_MAGIC ? UNC_FORMAT_PRIVATEFILE
                                           : UNC_FORMAT_UNKNOWN;
}

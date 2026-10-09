/* fmt_pf_probe.c — Private File's probe, kept resident.
 *
 * Split from fmt_pf.c so the reader can live in the StuffIt 'OVLY' image:
 * `unc_sniff` calls a probe for every file it is handed, and one inside a
 * blob would load the reader to decide a file is not one (FORMATS.md,
 * *Overlays*). The format, and where every rule here comes from, is in
 * fmt_pf.c's header comment.
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
    if (unc_get_u32be(head) != PF_MAGIC) return UNC_FORMAT_UNKNOWN;
    /* PFEngine's own acceptance test, nothing looser and nothing tighter:
     * a header it would refuse as an unknown METHOD is still a Private
     * File, and is named here so the entry can say so. */
    if (unc_get_u16be(head + 4) != 2) return UNC_FORMAT_UNKNOWN;
    if (unc_get_u16be(head + 6) > 1 || unc_get_u16be(head + 8) > 1)
        return UNC_FORMAT_UNKNOWN;
    if ((int16_t)unc_get_u16be(head + 12) > 0) return UNC_FORMAT_UNKNOWN;
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

/* fmt_arc_probe.c — ARC's probe, in the sniffer's image.
 *
 * Split out so the decoder can live in an overlay, and since 2026-10-21 in
 * the sniffer's own image with every other probe, run before the release
 * and given back with it (DECISIONS.md 2026-10-21, *the probes that left
 * with the bundle*).
 *
 * Source: unchanged from fmt_arc.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_arc_priv.h"

/* arc_name_ok is used by the decoder too, so it is declared in
 * fmt_arc_priv.h and this file is compiled into the ARC overlay as well —
 * one definition, two places, rather than a copy in each. */
int arc_name_ok(const uint8_t *p)
{
    int i;
    if (p[0] == 0) return 0;
    for (i = 0; i < ARC_NAME_LEN && p[i] != 0; i++)
        if (p[i] < 32) return 0;
    return 1;
}

UncFormat unc_arc_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t compsize, uncompsize, nextoff;
    int method;
    uint8_t nb[1];

    if (len < ARC_HDR_MIN) return UNC_FORMAT_UNKNOWN;

    /* ArcMac: the Mac header, then the PC one 59 bytes in. */
    if (head[AM_MAGIC1] == 0x1b && len >= AM_HDRBYTES &&
        head[AM_MAGIC2] == 0x1a && head[AM_KIND] != 0 &&
        head[AM_KIND] == head[AM_MAGIC2 + 1])
        return UNC_FORMAT_ARC;

    if (head[0] != 0x1a) return UNC_FORMAT_UNKNOWN;
    method = head[1];
    if (method == 0) return UNC_FORMAT_UNKNOWN;
    if (method != ARC_M_DIR && method != ARC_M_DIREND && !arc_is_item(method) &&
        (method & 0x7f) > ARC_M_DISTILLED && (method & 0x7f) != ARC_M_COMPRESSED)
        return UNC_FORMAT_UNKNOWN;
    /* An informational item's name field is empty and its uncompressed
     * length is 0 while its payload is not, so neither the name check
     * nor the size relation below applies to one. */
    if (!arc_is_item(method) && !arc_name_ok(head + 2)) return UNC_FORMAT_UNKNOWN;

    compsize = unc_get_u32le(head + 0x0f);
    if (method == ARC_M_STORED_OLD) {
        if (compsize > 0x1000000u) return UNC_FORMAT_UNKNOWN;
        nextoff = 0x19u + compsize;
    } else {
        if (len < 0x1d) return UNC_FORMAT_UNKNOWN;
        uncompsize = unc_get_u32le(head + 0x19);
        if (compsize > 0x1000000u) return UNC_FORMAT_UNKNOWN;
        if (uncompsize > 0x1000000u) return UNC_FORMAT_UNKNOWN;
        if (!arc_is_item(method) && compsize > uncompsize) return UNC_FORMAT_UNKNOWN;
        nextoff = 0x1du + compsize;
        if (method & 0x80) nextoff += 12u;
    }

    /* The strongest thing an ARC file says about itself: the next
     * header, or the end marker, sits exactly where the size puts it. */
    if ((int32_t)nextoff < len) return (head[nextoff] == 0x1a)
           ? UNC_FORMAT_ARC : UNC_FORMAT_UNKNOWN;
    if (!io) return UNC_FORMAT_UNKNOWN;
    if (unc_read_at(io, nextoff, nb, 1) != UNC_OK) return UNC_FORMAT_UNKNOWN;
    return (nb[0] == 0x1a)
           ? UNC_FORMAT_ARC : UNC_FORMAT_UNKNOWN;
}

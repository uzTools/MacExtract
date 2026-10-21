/* fmt_packit_probe.c — PackIt's probe(s), in the sniffer's image.
 *
 * Split out so the decoder can live in an overlay, and since 2026-10-21 in
 * the sniffer's own image with every other probe, run before the release
 * and given back with it (DECISIONS.md 2026-10-21, *the probes that left
 * with the bundle*).
 *
 * Source: at the probe itself. The rest of the format's provenance is
 * fmt_packit.c's.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

UncFormat unc_packit_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    /* Source: reference/deark/modules/packit.c (MIT),
     * de_identify_packit — "PMa" and the fourth byte, 'g' and '4' at
     * full confidence and '1'..'7' at low, a superset of the four
     * words this accepts. Appendix B of reference/notes/
     * packit_unpackit.txt names 'PMag', 'PMa4' and 'PMa5' (twice),
     * so deark is where 'PMa6' comes from. */
    if (len < 4) return UNC_FORMAT_UNKNOWN;
    if (head[0] == 'P' && head[1] == 'M' && head[2] == 'a' &&
        (head[3] == 'g' || head[3] == '4' || head[3] == '5' || head[3] == '6'))
        return UNC_FORMAT_PACKIT;
    return UNC_FORMAT_UNKNOWN;
}

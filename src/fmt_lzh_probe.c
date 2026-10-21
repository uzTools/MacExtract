/* fmt_lzh_probe.c — LZH's probe, in the sniffer's image.
 *
 * Split out so the decoder can live in an overlay, and since 2026-10-21 in
 * the sniffer's own image with every other probe, run before the release
 * and given back with it (DECISIONS.md 2026-10-21, *the probes that left
 * with the bundle*).
 *
 * Source: unchanged from fmt_lzh.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

UncFormat unc_lzh_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    if (len < 7) return UNC_FORMAT_UNKNOWN;
    if (head[2] != '-' || head[6] != '-') return UNC_FORMAT_UNKNOWN;
    if (head[3] == 'l' && head[4] == 'h') {
        uint8_t m = head[5];
        return ((m >= '0' && m <= '7') || m == 'd')
           ? UNC_FORMAT_LZH : UNC_FORMAT_UNKNOWN;
    }
    if (head[3] == 'l' && head[4] == 'z') {
        uint8_t m = head[5];
        return (m == '0' || m == '4' || m == '5' || m == 's')
           ? UNC_FORMAT_LZH : UNC_FORMAT_UNKNOWN;
    }
    return UNC_FORMAT_UNKNOWN;
}

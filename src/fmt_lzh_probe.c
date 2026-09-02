/* fmt_lzh_probe.c — LZH's probe, kept resident.
 *
 * Split out on 2026-09-02 so the decoder can live in an overlay. `unc_sniff`
 * calls this for every file it is handed: a probe inside a blob would mean
 * loading the whole decoder in order to decide the file is not one of these.
 * Separating what DECIDES from what DECODES is what makes on-demand loading
 * pay at all (BRANCH_NOTES.md).
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

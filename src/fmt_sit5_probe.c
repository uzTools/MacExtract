/* fmt_sit5_probe.c — StuffIt 5's probe(s), in the sniffer's image.
 *
 * Split out so the decoder can live in an overlay, and since 2026-10-21 in
 * the sniffer's own image with every other probe, run before the release
 * and given back with it (DECISIONS.md 2026-10-21, *the probes that left
 * with the bundle*).
 *
 * Source: unchanged from fmt_sit5.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_sit5_priv.h"

/* The banner match string; \xFF bytes match anything (the four
 * digits of the second year vary), which is how the published table
 * states it too: "characters marked ? can vary". */
const char sit5_banner[] =
    "StuffIt (c)1997-\xFF\xFF\xFF\xFF"
    " Aladdin Systems, Inc., http://www.aladdinsys.com/StuffIt/\x0d\x0a";

UncFormat unc_sit5_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    const char *m = sit5_banner;
    if (len < 100) return UNC_FORMAT_UNKNOWN;
    while (*m && (*head == (uint8_t)*m || (uint8_t)*m == 0xFF)) { m++; head++; }
    return (*m == 0)
           ? UNC_FORMAT_SIT5 : UNC_FORMAT_UNKNOWN;
}

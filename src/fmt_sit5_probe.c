/* fmt_sit5_probe.c — StuffIt 5's probe(s), kept resident.
 *
 * Split out so the decoder can live in an overlay: `unc_sniff` calls a probe
 * for every file it is handed, and a probe inside a blob would mean loading
 * the decoder to decide the file is not one (BRANCH_NOTES.md).
 *
 * Source: unchanged from fmt_sit5.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_sit5_priv.h"

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

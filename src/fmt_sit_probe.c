/* fmt_sit_probe.c — StuffIt classic's probe(s), kept resident.
 *
 * Split out so the decoder can live in an overlay: `unc_sniff` calls a probe
 * for every file it is handed, and a probe inside a blob would mean loading
 * the decoder to decide the file is not one (BRANCH_NOTES.md).
 *
 * Source: unchanged from fmt_sit.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

UncFormat unc_sit_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    /* Source: XADStuffItParser.m recognizeFileWithHandle. */
    if (len < 14) return UNC_FORMAT_UNKNOWN;
    if (unc_get_u32be(head + 10) != 0x724c6175u) return UNC_FORMAT_UNKNOWN;   /* 'rLau' */
    if (unc_get_u32be(head) == 0x53495421u) return UNC_FORMAT_SIT;        /* 'SIT!' */
    if (head[0] == 'S' && head[1] == 'T') {                  /* installers */
        if (head[2] == 'i' &&
            (head[3] == 'n' || (head[3] >= '0' && head[3] <= '9'))) return UNC_FORMAT_SIT;
        if (head[2] >= '0' && head[2] <= '9' &&
            head[3] >= '0' && head[3] <= '9') return UNC_FORMAT_SIT;
    }
    return UNC_FORMAT_UNKNOWN;
}

/* fmt_packit_probe.c — PackIt's probe(s), kept resident.
 *
 * Split out so the decoder can live in an overlay: `unc_sniff` calls a probe
 * for every file it is handed, and a probe inside a blob would mean loading
 * the decoder to decide the file is not one (BRANCH_NOTES.md).
 *
 * Source: unchanged from fmt_packit.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

UncFormat unc_packit_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    /* Source: XADPackItParser.m recognizeFileWithHandle. */
    if (len < 4) return UNC_FORMAT_UNKNOWN;
    if (head[0] == 'P' && head[1] == 'M' && head[2] == 'a' &&
        (head[3] == 'g' || head[3] == '4' || head[3] == '5' || head[3] == '6'))
        return UNC_FORMAT_PACKIT;
    return UNC_FORMAT_UNKNOWN;
}

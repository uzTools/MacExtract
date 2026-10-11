/* fmt_btoa_probe.c — btoa's probe(s), kept resident.
 *
 * Split out so the decoder can live in an overlay: `unc_sniff` calls a probe
 * for every file it is handed, and a probe inside a blob would mean loading
 * the decoder to decide the file is not one (BRANCH_NOTES.md).
 *
 * Source: unchanged from fmt_btoa.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

UncFormat unc_btoa_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    /* "xbtoa Begin" or "xbtoa5 ", at the start of some line within the
     * bytes we were handed — a btoa file may arrive with mail headers
     * in front of it, exactly as a BinHex or uuencoded one does. */
    int32_t i = 0;
    while (i < len) {
        int32_t j = i;
        while (j < len && head[j] != '\n' && head[j] != '\r') j++;
        if (j - i >= 11 &&
            head[i] == 'x' && head[i + 1] == 'b' && head[i + 2] == 't' &&
            head[i + 3] == 'o' && head[i + 4] == 'a') {
            if (head[i + 5] == ' ' &&
                head[i + 6] == 'B' && head[i + 7] == 'e' &&
                head[i + 8] == 'g' && head[i + 9] == 'i' &&
                head[i + 10] == 'n')
                return UNC_FORMAT_BTOA;
            if (head[i + 5] == '5' && head[i + 6] == ' ') return UNC_FORMAT_BTOA;
        }
        while (j < len && (head[j] == '\n' || head[j] == '\r')) j++;
        if (j == i) break;
        i = j;
    }
    return UNC_FORMAT_UNKNOWN;
}

/* fmt_uu_probe.c — uuencode's probe(s), kept resident.
 *
 * Split out so the decoder can live in an overlay: `unc_sniff` calls a probe
 * for every file it is handed, and a probe inside a blob would mean loading
 * the decoder to decide the file is not one (BRANCH_NOTES.md).
 *
 * The helpers below come with it and are used by the decoder as well, so this
 * file is compiled into that overlay TOO — one definition, two places.
 *
 * Source: unchanged from fmt_uu.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_uu_priv.h"
/* Used by the probe AND by the decoder, so it lives with the probe —
 * which the uu overlay compiles as well. */
int unc_uu_line_is_data(const uint8_t *p, int32_t len)
{
    int32_t outcount, incount, i;

    if (len < 1) return 0;
    if (p[0] < 0x20 || p[0] > 0x60) return 0;
    outcount = UU_SIXB(p[0]);
    if (outcount == 0 || outcount > 45) return 0;
    incount = ((outcount / 3) + 1) * 4;
    /* Trailing spaces may have been stripped; the line may be short,
     * never long. Every character must be in the uu alphabet. */
    if (len > incount + 1) return 0;
    for (i = 1; i < len; i++)
        if (p[i] < 0x20 || p[i] > 0x60) return 0;
    return 1;
}

UncFormat unc_uu_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    int32_t i = 0;

    while (i < len) {
        int32_t ls = i, le;
        while (i < len && head[i] != '\n' && head[i] != '\r') i++;
        le = i;
        while (i < len && (head[i] == '\n' || head[i] == '\r')) i++;

        if (le - ls >= 6 && head[ls] == 'b' && head[ls + 1] == 'e' &&
            head[ls + 2] == 'g' && head[ls + 3] == 'i' &&
            head[ls + 4] == 'n' && head[ls + 5] == ' ') {
            /* Next non-empty line must be a uu data line. */
            while (i < len) {
                int32_t ns = i, ne;
                while (i < len && head[i] != '\n' && head[i] != '\r') i++;
                ne = i;
                while (i < len && (head[i] == '\n' || head[i] == '\r')) i++;
                if (ne == ns) continue;                 /* blank */
                return (unc_uu_line_is_data(head + ns, ne - ns))
           ? UNC_FORMAT_UU : UNC_FORMAT_UNKNOWN;
            }
            return UNC_FORMAT_UNKNOWN;   /* begin line, but the file ends there */
        }
    }
    return UNC_FORMAT_UNKNOWN;
}

/* fmt_sit_probe.c — StuffIt classic's probe(s), kept resident.
 *
 * Split out so the decoder can live in an overlay: `unc_sniff` calls a probe
 * for every file it is handed, and a probe inside a blob would mean loading
 * the decoder to decide the file is not one (BRANCH_NOTES.md).
 *
 * Source: at the probe itself. The rest of the format's provenance is
 * fmt_sit.c's.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

UncFormat unc_sit_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    /* Source: reference/notes/sit_format_theunarchiver.md, the
     * archive-header table — "Magic number 2 (0x724c6175)" at offset
     * 10, and the "Known values for Magic number 1" list: SIT!, ST46,
     * ST50, ST60, ST65, STin. It is the same page fmt_sit.c walks the
     * container with.
     * THE WIDENING BELOW IS THIS PROJECT'S, not the page's: ST + two
     * digits and STi + a digit generalise that list to the pattern it
     * shows, so an installer version nobody has listed still opens.
     * It cannot cost a false positive, because 'rLau' has to match as
     * well — and it reaches nothing here: all 336 archives in the
     * corpus with 'rLau' at 10 carry 'SIT!' at 0, at either offset a
     * MacBinary header can put them (measured 2026-09-27). */
    if (len < 14) return UNC_FORMAT_UNKNOWN;
    if (head[10] != 'r' || head[11] != 'L' || head[12] != 'a' || head[13] != 'u')
        return UNC_FORMAT_UNKNOWN;                           /* 'rLau' */
    if (head[0] == 'S' && head[1] == 'I' && head[2] == 'T' && head[3] == '!')
        return UNC_FORMAT_SIT;                               /* 'SIT!' */
    if (head[0] == 'S' && head[1] == 'T') {                  /* installers */
        if (head[2] == 'i' &&
            (head[3] == 'n' || (head[3] >= '0' && head[3] <= '9'))) return UNC_FORMAT_SIT;
        if (head[2] >= '0' && head[2] <= '9' &&
            head[3] >= '0' && head[3] <= '9') return UNC_FORMAT_SIT;
    }
    return UNC_FORMAT_UNKNOWN;
}

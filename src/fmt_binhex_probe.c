/* fmt_binhex_probe.c — BinHex's probe(s), kept resident.
 *
 * Split out so the decoder can live in an overlay: `unc_sniff` calls a probe
 * for every file it is handed, and a probe inside a blob would mean loading
 * the decoder to decide the file is not one (BRANCH_NOTES.md).
 *
 * Source: unchanged from fmt_binhex.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_binhex_priv.h"

const char bh_banner[40] = "(This file must be converted with BinHex";

UncFormat unc_binhex_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    /* The banner can sit deep inside mail headers/digests, so scan up
     * to BH_SNIFF_LIMIT bytes: first the sniff head we were given, then
     * onward from the io handle with a rolling 40-byte window. */
    uint8_t window[40];
    uint8_t chunk[256];
    int32_t have = 0, w = 0, scanned = 0, pos = 0, clen = 0, cpos = 0;
    int found = 0;

    /* Earlier probes may have moved the position; continue after head. */
    if (io->seek(io->ctx, (uint32_t)len) < 0) return UNC_FORMAT_UNKNOWN;

    while (!found && scanned < BH_SNIFF_LIMIT) {
        int ch;
        int32_t i;
        if (pos < len) {
            ch = head[pos++];
        } else {
            if (cpos >= clen) {
                clen = io->read(io->ctx, chunk, (int32_t)sizeof chunk);
                if (clen <= 0) break;
                cpos = 0;
            }
            ch = chunk[cpos++];
        }
        scanned++;
        window[w] = (uint8_t)ch;
        if (++w == 40) w = 0;
        if (have < 40) have++;
        if (have == 40) {
            int32_t j = w;
            for (i = 0; i < 40; i++) {
                if (window[j] != (uint8_t)bh_banner[i]) break;
                if (++j == 40) j = 0;
            }
            if (i == 40) found = 1;
        }
    }
    return (found)
           ? UNC_FORMAT_BINHEX : UNC_FORMAT_UNKNOWN;
}

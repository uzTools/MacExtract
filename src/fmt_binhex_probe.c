/* fmt_binhex_probe.c — BinHex's probe(s), in the sniffer's image.
 *
 * Split out so the decoder can live in an overlay, and since 2026-10-21 in
 * the sniffer's own image with every other probe, run before the release
 * and given back with it (DECISIONS.md 2026-10-21, *the probes that left
 * with the bundle*).
 *
 * Source: unchanged from fmt_binhex.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_binhex_priv.h"

const char bh_banner[40] = "(This file must be converted with BinHex";

/* The "#TYPECREA$FFFF" line that opens a `.hex` or `.hcx` document.
 * Source: reference/macutils/hexbin/hecx.c, which takes the type when the
 * line is at least 10 long and the creator at 14, and wants '$' five from
 * the end. The four flag digits are required here and not there: BinHex
 * 2.0 writes all four (tools/vmac/binhex2.py), and they are what lets a
 * probe trust one line. Shared with fmt_hecx.c, which is compiled into
 * the overlay beside a copy of this file. */
int unc_hecx_is_header(const uint8_t *l, int32_t n)
{
    int32_t i;
    if (n < 6 || l[0] != '#' || l[n - 5] != '$') return 0;
    for (i = n - 4; i < n; i++) {
        uint8_t d = l[i];
        if (!((d >= '0' && d <= '9') || (d >= 'A' && d <= 'F') ||
              (d >= 'a' && d <= 'f')))
            return 0;
    }
    return 1;
}

#define HX_PROBE_LINE 32

UncFormat unc_binhex_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    /* The banner can sit deep inside mail headers/digests, so scan up
     * to BH_SNIFF_LIMIT bytes: first the sniff head we were given, then
     * onward from the io handle with a rolling 40-byte window.
     *
     * The same scan finds the two encodings before 4.0. Their banner,
     * "(This file must be converted with BinHex.Hex)", matches the 40
     * characters above, and two of the three 1985 `.hcx` files here have
     * none at all, so what tells them apart is the document: a header
     * line (unc_hecx_is_header) whose next non-empty line is a "***"
     * marker. After a banner, the first line that is not such a header
     * settles it as BinHex 4.
     *
     * And SUMacC's `.dl`, which has no marker at all: before any banner,
     * a line of 41 to 1,022 characters, even in length, every one of them
     * '@'..'O' or '|', is one, as hexbin.c's find_header has it (its line
     * buffer cuts at 1,023, which is odd) — and, which hexbin does not
     * ask, opening "@@", the zero high byte of the resource fork's data
     * offset (fmt_hecx.c). Without that, base64 of a run of zeros is a
     * line of 'A' and was claimed. Only the FIRST such line is looked at,
     * since hexbin decodes from there: one that does not open "@@" ends
     * the question rather than passing it to a later line. */
    uint8_t window[40];
    uint8_t chunk[256];
    uint8_t ln[HX_PROBE_LINE];
    int32_t have = 0, w = 0, scanned = 0, pos = 0, clen = 0, cpos = 0;
    int32_t ll = 0;
    int banner = 0, in_banner = 0, hdr = 0, dl = 1, dlseen = 0;

    /* Earlier probes may have moved the position; continue after head. */
    if (io->seek(io->ctx, (uint32_t)len) < 0) return UNC_FORMAT_UNKNOWN;

    while (scanned < BH_SNIFF_LIMIT) {
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
        if (ch == '\r' || ch == '\n') {
            if (!banner && !dlseen && dl && ll > 40 && ll < 1023 &&
                !(ll & 1)) {
                if (ln[0] == '@' && ln[1] == '@') return UNC_FORMAT_DL;
                dlseen = 1;
            }
            if (ll > 0 && !in_banner) {
                int is = ll <= HX_PROBE_LINE && unc_hecx_is_header(ln, ll);
                if (hdr && ll >= 3 && ln[0] == '*' && ln[1] == '*' &&
                    ln[2] == '*')
                    return UNC_FORMAT_BINHEX_OLD;
                if (banner && !is) return UNC_FORMAT_BINHEX;
                hdr = is;
            }
            if (ll > 0) in_banner = 0;
            ll = 0;
            dl = 1;
        } else {
            if ((ch < '@' || ch > 'O') && ch != '|') dl = 0;
            if (ll < HX_PROBE_LINE) ln[ll] = (uint8_t)ch;
            if (ll < 0x7FFF) ll++;
        }
        window[w] = (uint8_t)ch;
        if (++w == 40) w = 0;
        if (have < 40) have++;
        if (have == 40 && !banner) {
            int32_t j = w;
            for (i = 0; i < 40; i++) {
                if (window[j] != (uint8_t)bh_banner[i]) break;
                if (++j == 40) j = 0;
            }
            if (i == 40) { banner = 1; in_banner = 1; hdr = 0; }
        }
    }
    return banner ? UNC_FORMAT_BINHEX : UNC_FORMAT_UNKNOWN;
}

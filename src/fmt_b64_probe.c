/* fmt_b64_probe.c — base64's probe(s), in the sniffer's image.
 *
 * Split out so the decoder can live in an overlay, and since 2026-10-21 in
 * the sniffer's own image with every other probe, run before the release
 * and given back with it (DECISIONS.md 2026-10-21, *the probes that left
 * with the bundle*).
 *
 * The helpers below come with it and are used by the decoder as well, so this
 * file is compiled into that overlay TOO — one definition, two places.
 *
 * Source: unchanged from fmt_b64.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_b64_priv.h"
int b64_val(int c)
{
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

static int b64_bare_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    int32_t i = 0, width = -1, lines = 0;
    uint8_t tail[512];
    uint32_t size;
    int32_t got, ls, le, lastlen;

    while (i < len && lines < B64_MIN_LINES) {
        int32_t s = i, e;
        while (i < len && head[i] != '\n' && head[i] != '\r') i++;
        e = i;
        while (i < len && (head[i] == '\n' || head[i] == '\r')) i++;
        if (e == s) return 0;               /* a blank line: not a body */
        if (i >= len && e - s < width) break;   /* cut by the window */
        if (!b64_line_ok(head + s, e - s)) return 0;
        if (width < 0) {
            width = e - s;
            if (width < B64_MIN_WIDTH || width > B64_MAX_WIDTH) return 0;
        } else if (e - s != width) {
            return 0;                       /* only the LAST line is short */
        }
        lines++;
    }
    if (lines < B64_MIN_LINES) return 0;

    /* The tail. A stream that ends mid-group, or on a line that is not
     * base64 at all, is not a bare base64 file. */
    if (!io) return 0;
    size = unc_io_size32(io);
    if (size == UNC_SIZE_UNKNOWN || size == 0) return 0;
    got = (int32_t)(size < sizeof tail ? size : sizeof tail);
    if (unc_read_at(io, size - (uint32_t)got, tail, got) != UNC_OK) return 0;

    /* Walk to the last non-empty line of the buffer. */
    ls = le = -1;
    for (i = 0; i < got; ) {
        int32_t s = i, e;
        while (i < got && tail[i] != '\n' && tail[i] != '\r') i++;
        e = i;
        while (i < got && (tail[i] == '\n' || tail[i] == '\r')) i++;
        if (e > s) { ls = s; le = e; }
    }
    if (ls < 0) return 0;
    lastlen = le - ls;
    if (lastlen > width) return 0;
    if (!b64_line_ok(tail + ls, lastlen)) return 0;
    return 1;
}

int b64_is_begin(const uint8_t *p, int32_t len)
{
    static const char tag[] = "begin-base64 ";
    int32_t i;
    if (len < 16) return 0;                 /* deark's bound: the tag,
                                             * a mode and a name */
    for (i = 0; tag[i]; i++) if (p[i] != (uint8_t)tag[i]) return 0;
    return 1;
}

int b64_line_ok(const uint8_t *p, int32_t len)
{
    int32_t i, np = 0;

    if (len < 4) return 0;
    for (i = 0; i < len; i++) {
        if (p[i] == '=') { np++; continue; }
        if (np) return 0;                   /* padding is only ever last */
        if (b64_val(p[i]) < 0) return 0;
    }
    if (np > 2) return 0;
    return (len % 4) == 0;
}

UncFormat unc_b64_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    int32_t i = 0;

    /* The named shape: a "begin-base64 " line, and behind it a line
     * that really is base64 — the same two-step BinHex and uuencode
     * use, because a marker alone occurs in prose. */
    while (i < len) {
        int32_t s = i, e;
        while (i < len && head[i] != '\n' && head[i] != '\r') i++;
        e = i;
        while (i < len && (head[i] == '\n' || head[i] == '\r')) i++;
        if (b64_is_begin(head + s, e - s)) {
            while (i < len) {
                int32_t ns = i, ne;
                while (i < len && head[i] != '\n' && head[i] != '\r') i++;
                ne = i;
                while (i < len && (head[i] == '\n' || head[i] == '\r')) i++;
                if (ne == ns) continue;
                return (b64_line_ok(head + ns, ne - ns))
           ? UNC_FORMAT_BASE64 : UNC_FORMAT_UNKNOWN;
            }
            return UNC_FORMAT_UNKNOWN;
        }
    }

    return (b64_bare_probe(head, len, io))
           ? UNC_FORMAT_BASE64 : UNC_FORMAT_UNKNOWN;
}

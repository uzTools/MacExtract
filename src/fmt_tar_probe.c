/* fmt_tar_probe.c — tar's probe, and the three header-field checks it
 * shares with the reader. The provenance of each is at the function.
 *
 * Every probe is in its reader's `_probe.c` (DECISIONS.md 2026-10-20, *one
 * place for every probe*), and the Macintosh application carries them all,
 * with the sniffer, in one `'OVLY'` image run before the release and given
 * back with it (DECISIONS.md 2026-10-21, *the probes that left with the
 * bundle*). What a probe and its reader share is defined once, here, and
 * stays resident for the reader.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_tar_priv.h"

/* Parse an octal field (space/NUL padded). Returns value or -1.
 * Source: posix_ustar.txt, "ustar Interchange Format" — every numeric
 * field in the header block is an octal representation in ISO/IEC
 * 646:1991, terminated by one or more <space> or NUL characters. */
int64_t tar_octal(const uint8_t *p, int32_t n)
{
    int64_t v = 0;
    int32_t i = 0;
    while (i < n && (p[i] == ' ' || p[i] == 0)) i++;
    if (i == n) return 0;
    for (; i < n && p[i] >= '0' && p[i] <= '7'; i++)
        v = v * 8 + (p[i] - '0');
    return v;
}

int tar_field_ok(const uint8_t *p, int32_t n)
{
    int32_t i = 0;
    while (i < n && p[i] == ' ') i++;
    while (i < n && p[i] >= '0' && p[i] <= '7') i++;
    while (i < n && (p[i] == 0 || p[i] == ' ')) i++;
    return i == n;
}

/* Source: posix_ustar.txt — "the simple sum of all octets in the header
 * logical record ... each octet ... treated as an unsigned value ...
 * the chksum field is treated as if it were all <space> characters". */
int tar_checksum_ok(const uint8_t *h)
{
    int64_t stored = tar_octal(h + 148, 8);
    int32_t i;
    int64_t uns = 0, sig = 0;
    for (i = 0; i < 512; i++) {
        uint8_t b = (i >= 148 && i < 156) ? (uint8_t)' ' : h[i];
        uns += b;
        sig += (int8_t)((i >= 148 && i < 156) ? ' ' : (int8_t)h[i]);
    }
    return stored == uns || stored == sig;   /* GNU tolerates signed sums */
}

UncFormat unc_tar_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    int32_t i;
    if (len < 512) return UNC_FORMAT_UNKNOWN;
    if (!tar_checksum_ok(head)) return UNC_FORMAT_UNKNOWN;

    /* POSIX/old-GNU: "ustar" magic at 257 plus the checksum. This
     * offset and every other one below is the ustar Header Block table
     * in posix_ustar.txt, where the magic field is "the five characters
     * ... shown followed by NUL". Only the five are compared, and that
     * is what lets the older GNU spelling of the field through. */
    if (head[257] == 'u' && head[258] == 's' && head[259] == 't' &&
        head[260] == 'a' && head[261] == 'r')
        return UNC_FORMAT_TAR;

    /* Pre-POSIX v7 tar has NO magic, and no specification either — it
     * predates the one above. XADTarParser falls back to the
     * *filename* for these, which our content-only rule forbids, so
     * we demand structure instead: a valid checksum plus well-formed
     * v7 fields (see DECISIONS.md M9/M10 follow-up).
     *   - name: NUL-terminated printable, non-empty
     *   - mode/uid/gid/size/mtime: octal fields
     *   - typeflag: NUL or '0'..'7' — POSIX defines both, saying a
     *     binary zero "should be recognized as meaning a regular
     *     file" for backwards-compatibility with exactly this. */
    if (head[0] == 0) return UNC_FORMAT_UNKNOWN;
    for (i = 0; i < 100 && head[i]; i++)
        if (head[i] < 0x20 || head[i] == 0x7F) return UNC_FORMAT_UNKNOWN;
    if (i == 100) return UNC_FORMAT_UNKNOWN;                    /* name not terminated */
    if (!tar_field_ok(head + 100, 8)) return UNC_FORMAT_UNKNOWN;   /* mode  */
    if (!tar_field_ok(head + 108, 8)) return UNC_FORMAT_UNKNOWN;   /* uid   */
    if (!tar_field_ok(head + 116, 8)) return UNC_FORMAT_UNKNOWN;   /* gid   */
    if (!tar_field_ok(head + 124, 12)) return UNC_FORMAT_UNKNOWN;  /* size  */
    if (!tar_field_ok(head + 136, 12)) return UNC_FORMAT_UNKNOWN;  /* mtime */
    if (head[156] != 0 && (head[156] < '0' || head[156] > '7')) return UNC_FORMAT_UNKNOWN;
    return UNC_FORMAT_TAR;
}

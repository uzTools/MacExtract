/* fmt_exo_probe.c — the four probes of the non-Macintosh formats.
 *
 * gzip, Unix compress, tar and zip share one decoder file; their probes are
 * here so that file can be an overlay. unc_sniff calls all four for every
 * file it is handed, and a probe inside a blob would mean loading zip,
 * gzip, compress, tar AND zlib to decide a file is none of them
 * (BRANCH_NOTES.md).
 *
 * tar's two field checks come along because the decoder uses them too, so
 * this file is compiled into that overlay as well.
 *
 * Source: unchanged from fmt_exo.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_exo_priv.h"

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

UncFormat unc_gzip_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return (len >= 3 && head[0] == 0x1F && head[1] == 0x8B && head[2] == 8)
           ? UNC_FORMAT_GZIP : UNC_FORMAT_UNKNOWN;
}

UncFormat unc_compressz_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return (len >= 3 && head[0] == 0x1F && head[1] == 0x9D)
           ? UNC_FORMAT_COMPRESS_Z : UNC_FORMAT_UNKNOWN;
}

UncFormat unc_tar_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    int32_t i;
    if (len < 512) return UNC_FORMAT_UNKNOWN;
    if (!tar_checksum_ok(head)) return UNC_FORMAT_UNKNOWN;

    /* POSIX/old-GNU: "ustar" magic at 257 plus the checksum. */
    if (head[257] == 'u' && head[258] == 's' && head[259] == 't' &&
        head[260] == 'a' && head[261] == 'r')
        return UNC_FORMAT_TAR;

    /* Pre-POSIX v7 tar has NO magic. XADTarParser falls back to the
     * *filename* for these, which our content-only rule forbids, so
     * we demand structure instead: a valid checksum plus well-formed
     * v7 fields (see DECISIONS.md M9/M10 follow-up).
     *   - name: NUL-terminated printable, non-empty
     *   - mode/uid/gid/size/mtime: octal fields
     *   - typeflag: NUL or '0'..'7' */
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

UncFormat unc_zip_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    if (len < 4) return UNC_FORMAT_UNKNOWN;
    /* Local file header or (rarely first) central dir / EOCD magic. */
    if (head[0] == 'P' && head[1] == 'K' &&
        ((head[2] == 3 && head[3] == 4) ||
         (head[2] == 5 && head[3] == 6)))    /* empty archive */
        return UNC_FORMAT_ZIP;
    /* A local header displaced to offset 4: what a splitting zip writes
     * when it puts a marker in front. That archive may be a set of one,
     * in which case it is an ordinary zip and reads as one — the four
     * bytes are simply part of every offset it records.
     * Source: reference/XADMaster/XADZipParser.m
     * +recognizeFileWithHandle:, `bytes[4..7] == PK\3\4`. Segmented
     * sets are caught before this by unc_zipseg_probe. */
    return (len >= 8 && head[4] == 'P' && head[5] == 'K' &&
           head[6] == 3 && head[7] == 4)
           ? UNC_FORMAT_ZIP : UNC_FORMAT_UNKNOWN;
}

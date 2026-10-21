/* fmt_exo_probe.c — the probes of zip, gzip and Unix compress, whose
 * readers share fmt_exo.c. Source: unchanged from fmt_exo.c, whose
 * provenance comments stand.
 *
 * Every probe is in its reader's `_probe.c`, resident, so the reader can
 * be an overlay: unc_sniff calls every probe for every file it is handed,
 * before any image is chosen (DECISIONS.md 2026-10-20, *one place for
 * every probe*). What a probe and its reader share is defined once, here.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

UncFormat unc_gzip_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return (len >= 3 && head[0] == 0x1F && head[1] == 0x8B && head[2] == 8)
           ? UNC_FORMAT_GZIP : UNC_FORMAT_UNKNOWN;
}

/* The three-byte header: 1F 9D, then a mode byte whose low five bits
 * are the maximum code width and whose bit 7 says the stream has a
 * clear code in it. Source: deark's `delzw_process_unixcompress_-
 * 3byteheader` (MIT, see NOTICE) — the same file `src/unc_lzw.c` is
 * written from, and the forward reference the LZW row left for this
 * one (DECISIONS.md 2026-09-19, *the buffer that became a length*). */
UncFormat unc_compressz_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return (len >= 3 && head[0] == 0x1F && head[1] == 0x9D)
           ? UNC_FORMAT_COMPRESS_Z : UNC_FORMAT_UNKNOWN;
}

/* The HEAD test, and only that. Where a zip's archive begins is found
 * from its end-of-central-directory record, and the probe that scans for
 * that one runs just before this (unc_zipseg_probe, which claims a
 * corroborated record for either of the two zip formats). What is left
 * here is every
 * zip whose record is missing or unconfirmable and which says what it is
 * at offset 0 anyway: a truncated archive, an empty one, and a file whose
 * directory is not where it claims. */
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
     * when it puts a marker in front (APPNOTE.TXT 8.5.3 — "a special
     * spanning signature as the first 4 bytes of the first segment ...
     * followed immediately by the local header signature for the first
     * file"). That archive may be a set of one, in which case it is an
     * ordinary zip and reads as one — the four bytes are simply part of
     * every offset it records. What is tested is the displacement and
     * not the marker, for the reason fmt_zipseg.c gives. Segmented sets
     * are caught before this by unc_zipseg_probe. */
    return (len >= 8 && head[4] == 'P' && head[5] == 'K' &&
           head[6] == 3 && head[7] == 4)
           ? UNC_FORMAT_ZIP : UNC_FORMAT_UNKNOWN;
}

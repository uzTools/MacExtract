/* fmt_now_probe.c — Now Compress's probe.
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
#include "unc_internal.h"

/* Now Compress: 00 02 magic, plausible file count, Pascal name, and a
 * byte-sum checksum over bytes 24..129 stored at 130 — which is the
 * first ENTRY RECORD's own checksum, the record being 110 bytes from
 * 24 with a u32 at +106 summing the 106 before it.
 *
 * Source: docs/formats/now-compress.md, *The archive layer* — this
 * project's own description, where every field this tests is measured:
 * the 24-byte file header (0x0002, a version word, the entry count as
 * a u32 at +8), the record layout, and that checksum, which nine
 * archives here agree on. Until 2026-09-21 this cited
 * XADNowCompressParser.m, the only account of the format that existed;
 * `src/fmt_now.c` still does, for the code. */
UncFormat unc_nowcompress_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    uint32_t sum;
    int32_t i;
    if (len < 134) return UNC_FORMAT_UNKNOWN;
    if (head[0] != 0x00 || head[1] != 0x02) return UNC_FORMAT_UNKNOWN;
    /* The u32 count at +8 is 1..0xFFFF: its high word zero, its low
     * word not. Bytes, not a long (DECISIONS.md 2026-10-09, *the probe
     * was the outlier*). */
    if (head[8] != 0 || head[9] != 0 || (head[10] == 0 && head[11] == 0))
        return UNC_FORMAT_UNKNOWN;
    if (head[24] == 0 || head[24] > 31) return UNC_FORMAT_UNKNOWN;
    for (i = 0; i < head[24]; i++)
        if (head[25 + i] < 32) return UNC_FORMAT_UNKNOWN;
    sum = 0;
    for (i = 24; i < 130; i++) sum += head[i];
    /* 106 bytes sum to at most 27,030, so the stored u32 equals it only
     * with its high word zero and its low word the sum. */
    return (head[130] == 0 && head[131] == 0 && unc_get_u16be(head + 132) == sum)
           ? UNC_FORMAT_NOWCOMPRESS : UNC_FORMAT_UNKNOWN;
}

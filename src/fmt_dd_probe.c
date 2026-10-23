/* fmt_dd_probe.c — DiskDoubler's probe.
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

/* DiskDoubler: 0xABCD0054 and a CRC-16/XMODEM of the 82-byte header
 * at +82, 0xABCD0030 for the 1990 header, which has no CRC, or the
 * 'DDAR' and 'DDA2' archives, each with a CRC of its own header.
 *
 * Source: docs/formats/diskdoubler-container.md, where every one of
 * those facts is measured rather than read: the magic word and the
 * header's own size at +2 (84 in every corpus header, 48 in the 1990
 * one, *The header size, and the 1990 header*); the CRC at +82, which
 * holds on all 91 84-byte headers in the fixtures and the specimens
 * (2026-10-23) and which DiskDoubler 3.7 itself refuses a header for
 * failing; the `DDAR` archive header's 78 bytes and its CRC at +76,
 * which hold on all 7 `DDAR` archives here (2026-10-23); and `DDA2`'s
 * CRC at +60, read off the CC0 specimens NOTICE credits. The 1990
 * header is matched as a whole 32-bit constant like the first: it ends
 * before any CRC, and its +42 fill is zero where the forks' own sums are
 * not, so the size makes the magic MORE specific. Two programs write it,
 * DiskDoubler ß05 and MacCompress 3.2 (`tools/vmac/maccompress.py`).
 * Only two sizes have a specimen; ß05's validator accepts any from 48
 * up, but nothing here guesses what a third would put where.
 * macutils' `dd.h` and XADMaster's XADDiskDoublerParser.m state the
 * 84- and 78-byte shapes too and agree with all of this.
 *
 * One rule is NOT measured, and is XADMaster's alone: a stored CRC of
 * zero on the 84-byte header is accepted ("Really old files have 0000
 * instead of a CRC"). None of the 91 headers here has one; kept, the
 * maintainer's decision 2026-10-23 (DECISIONS.md, *the probes next
 * door*).
 * Source: reference/XADMaster/XADDiskDoublerParser.m, recognizeFile
 * (LGPL, see NOTICE). */
UncFormat unc_diskdoubler_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    /* The four magics as bytes, not longs (DECISIONS.md 2026-10-09,
     * *the probe was the outlier*): AB CD 00 54, AB CD 00 30, 'DDAR',
     * 'DDA2'. */
    if (len >= 48 && head[0] == 0xAB && head[1] == 0xCD && head[2] == 0x00) {
        if (head[3] == 0x54 && len >= 84) {
            uint16_t crc = unc_get_u16be(head + 82);
            if (crc == 0 || crc == unc_crc16_xmodem(0, head, 82)) return UNC_FORMAT_DISKDOUBLER;
        }
        if (head[3] == 0x30)
            return UNC_FORMAT_DISKDOUBLER;
    }
    if (len >= 62 && head[0] == 'D' && head[1] == 'D' && head[2] == 'A') {
        if (head[3] == 'R' && len >= 78 &&
            unc_get_u16be(head + 76) == unc_crc16_xmodem(0, head, 76)) return UNC_FORMAT_DISKDOUBLER;
        if (head[3] == '2' &&
            unc_get_u16be(head + 60) == unc_crc16_xmodem(0, head, 60)) return UNC_FORMAT_DISKDOUBLER;
    }
    return UNC_FORMAT_UNKNOWN;
}


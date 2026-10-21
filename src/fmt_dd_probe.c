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

/* DiskDoubler: 0xABCD0054 magic + XMODEM CRC of the 82-byte header
 * (or 0 in very old files), 0xABCD0030 for the 1990 shape, or the
 * 'DDAR' archive variant.
 *
 * **That long is a word and a length**, measured 2026-09-22 by running
 * DiskDoubler ß05 (1990), which writes 48 where every one of the 195
 * headers in the corpus writes 84 (docs/formats/diskdoubler-container.md,
 * "The header size, and the 1990 header"). A short header ends before
 * `C_HDRCRC 82`, so there is no header CRC to check — and none of its
 * fill is one either: 0x00 through all six bytes at +42, where the two
 * forks' own sums are 0xd766 and 0x116a. So the second shape is matched
 * as a whole 32-bit constant exactly as the first is, and the size makes
 * the magic MORE specific rather than less. Only two values have a
 * specimen; that version's validator accepts any size from 48 up, which
 * is why the field is read as a size at all, but nothing here guesses
 * what a third would put where. Both references know only the 84-byte
 * shape — macutils states `MAGIC2 "\253\315\000\124"` as four bytes
 * and XADMaster compares `0xabcd0054` as a long — so the first path
 * below is byte-for-byte what it was and no corpus file reaches the new
 * one.
 *
 * Source: reference/macutils/macunpack/dd.h, for the first two, which
 * states both magics and both header shapes — MAGIC2 "\253\315\000\124"
 * is the same four bytes, C_HDRCRC 82 in an 84-byte compressed-file
 * header, ARCHHDRCRC 76 in a 78-byte archive header. XADMaster's
 * XADDiskDoublerParser.m agrees and is where the CRC came from; its
 * reversed-table formulation equals plain CRC-16/XMODEM, see
 * DECISIONS.md M0.
 *
 * 'DDA2' is in neither: it is DiskDoubler Pro's, read off the CC0
 * specimens NOTICE credits, as the SPLT container in fmt_ddseg.c was. */
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


/* fmt_macbinary_probe.c — MacBinary's probe, and the header test it
 * shares with the reader (mb_version). The layout is fmt_macbinary.c's
 * file comment.
 *
 * Every probe is in its reader's `_probe.c` (DECISIONS.md 2026-10-20, *one
 * place for every probe*), and the Macintosh application carries them all,
 * with the sniffer, in one `'OVLY'` image run before the release and given
 * back with it (DECISIONS.md 2026-10-21, *the probes that left with the
 * bundle*). What a probe and its reader share is defined once, here, and
 * stays resident for the reader.
 *
 * MacBinary I has no CRC, so it is accepted only under the stricter
 * tests the II standard sets out for exactly that case: "Offsets
 * 101-125 ... should all be 0", the name length in 1..63, and the two
 * fork lengths bounded. Two of those are read here more strictly than
 * written and one less, and each difference is deliberate:
 *
 *   - zero is required from offset 99 rather than 101. 99 is the Get
 *     Info comment length, which the II standard adds and then reports
 *     that "to the best of our knowledge, no program has implemented
 *     this feature"; a MacBinary I header has nothing there at all.
 *   - the fork lengths are bounded by UNC_MAC_MAX (2 GB) rather than by
 *     the standard's 0x007FFFFF. The smaller figure is a 1987 statement
 *     about how large a Macintosh file could be, not about the format,
 *     and this engine already refuses what it cannot address.
 *   - nonzero creation and modification dates are required, which no
 *     standard asks for. It is XADMaster's test and it is kept: a
 *     MacBinary I header has no checksum, so without it the whole of
 *     the evidence is a handful of zero bytes.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_macbinary_priv.h"

/* CRC-16 with reflected polynomial 0xA001 (CRC-16/USB when init and
 * final xor are 0xFFFF). The standard specifies one checksum and this
 * is not it: XADMaster is the sole source, accepting this as a fallback
 * for files made by encoders that reached for the wrong table.
 * Source: reference/XADMaster/XADMacArchiveParser.m (XADCRCTable_a001
 * use, and the nonzero-date test above) — LGPL, see NOTICE. Bitwise form; runs over 124 bytes only, speed is
 * irrelevant. */
static uint16_t mb_crc16_a001(uint16_t crc, const uint8_t *buf, int32_t len)
{
    int32_t i;
    int b;
    for (i = 0; i < len; i++) {
        crc ^= buf[i];
        for (b = 0; b < 8; b++)
            crc = (crc & 1) ? (uint16_t)((crc >> 1) ^ 0xA001) : (uint16_t)(crc >> 1);
    }
    return crc;
}

/* Returns MacBinary version 1..3, or 0 if the header is not MacBinary.
 *
 * The III standard says to look at the 'mBIN' signature FIRST and fall
 * back to the II procedure if it is absent. The order here is the other
 * way round — the zero fills and the name, then the CRC, and only then
 * 'mBIN' to tell III from II — and the two agree, because a MacBinary
 * III header carries the II checksum as well. Reading the CRC first
 * costs a III file nothing and buys the signature test a header that
 * has already been checked. */
int mb_version(const uint8_t *b, int32_t len)
{
    int i;
    uint16_t stored;
    if (len < MB_HDR) return 0;

    /* Zero fill bytes. */
    if (b[0] != 0) return 0;
    if (b[74] != 0) return 0;
    if (b[82] != 0) return 0;
    for (i = 108; i <= 115; i++) if (b[i] != 0) return 0;

    /* Valid name. */
    if (b[1] == 0 || b[1] > 63) return 0;
    for (i = 0; i < b[1]; i++) if (b[i + 2] == 0) return 0;

    /* MacBinary II/III: header CRC at 124 (CRC-16/XMODEM over 0..123). */
    stored = unc_get_u16be(b + 124);
    if (unc_crc16_xmodem(0, b, 124) == stored ||
        (mb_crc16_a001(0xFFFF, b, 124) ^ 0xFFFF) == stored) {
        if (b[102] == 'm' && b[103] == 'B' && b[104] == 'I' && b[105] == 'N')
            return 3;
        return 2;
    }

    /* MacBinary I: no checksum, so the structural tests are all the
     * evidence there is (see file comment). */
    for (i = 99; i <= 125; i++) if (b[i] != 0) return 0;
    /* Bytes, not longs (DECISIONS.md 2026-10-09, *the probe was the
     * outlier*): a fork size over UNC_MAC_MAX is one with its top bit
     * set, and a date is zero when its four bytes are. */
    if (b[83] & 0x80) return 0;                        /* data fork size */
    if (b[87] & 0x80) return 0;                        /* rsrc fork size */
    if ((b[91] | b[92] | b[93] | b[94]) == 0) return 0; /* creation date */
    if ((b[95] | b[96] | b[97] | b[98]) == 0) return 0; /* mod date      */
    return 1;
}

UncFormat unc_macbinary_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return (mb_version(head, len) > 0)
           ? UNC_FORMAT_MACBINARY : UNC_FORMAT_UNKNOWN;
}

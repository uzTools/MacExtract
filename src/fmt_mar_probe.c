/* fmt_mar_probe.c — MAR's probe and its CRC, in the sniffer's image and,
 * for the reader, in ovl_zipold beside it.
 *
 * The format, and where every rule here comes from, is in fmt_mar.c's
 * header comment.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_mar_priv.h"

/* Four bits at a time: 64 B of table where a byte-wide one is 1 KB.
 * Entry i is i << 28 shifted out through the polynomial four times. */
static const uint32_t mar_crc_nib[16] = {
    0x00000000u, 0x1EDC6F41u, 0x3DB8DE82u, 0x2364B1C3u,
    0x7B71BD04u, 0x65ADD245u, 0x46C96386u, 0x58150CC7u,
    0xF6E37A08u, 0xE83F1549u, 0xCB5BA48Au, 0xD587CBCBu,
    0x8D92C70Cu, 0x934EA84Du, 0xB02A198Eu, 0xAEF676CFu
};

uint32_t unc_mar_crc(uint32_t crc, const uint8_t *p, uint32_t n)
{
    while (n--) {
        uint32_t b = *p++;
        crc = (crc << 4) ^ mar_crc_nib[(crc >> 28) ^ (b >> 4)];
        crc = (crc << 4) ^ mar_crc_nib[(crc >> 28) ^ (b & 15u)];
    }
    return crc;
}

int unc_mar_hdr_ok(const uint8_t *h)
{
    return h[0] == 'M' && h[1] == 'A' && h[2] == 'R' && h[3] == 0x80 &&
           unc_mar_crc(0, h, 124) == unc_get_u32be(h + 124);
}

/* What both of hampa's readers accept as an archive: the magic, the
 * header CRC, and a first record that is a file or a folder.
 * Source: reference/mar/mac-utils/src/mar/mar_extract.c (mar_extract_fp)
 * and reference/mar/mar-0.2.0-src/src/mar_dec.c (mar_decode_fd). */
UncFormat unc_mar_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t id;
    (void)io;
    if (len < (int32_t)MAR_HDR || !unc_mar_hdr_ok(head))
        return UNC_FORMAT_UNKNOWN;
    id = unc_get_u32be(head + 4);
    return id == MAR_FILE || id == MAR_FOLDER ? UNC_FORMAT_MAR
                                              : UNC_FORMAT_UNKNOWN;
}

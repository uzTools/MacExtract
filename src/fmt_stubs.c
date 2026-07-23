/*
 * fmt_stubs.c — detect-only probes: formats v1 names in unc_sniff but
 * does not extract, so a UI can tell the user what the file is.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* StuffIt X: 8-byte magic "StuffIt!" or "StuffIt?".
 * Source: reference/XADMaster/XADStuffItXParser.m. */
int unc_sitx_probe(const uint8_t *head, int32_t len)
{
    if (len < 8) return 0;
    return head[0] == 'S' && head[1] == 't' && head[2] == 'u' &&
           head[3] == 'f' && head[4] == 'f' && head[5] == 'I' &&
           head[6] == 't' && (head[7] == '!' || head[7] == '?');
}

/* Now Compress: 00 02 magic, plausible file count, Pascal name, and a
 * byte-sum checksum over bytes 24..129 stored at 130.
 * Source: reference/XADMaster/XADNowCompressParser.m. */
int unc_nowcompress_probe(const uint8_t *head, int32_t len)
{
    uint32_t nfiles, sum;
    int32_t i;
    if (len < 134) return 0;
    if (head[0] != 0x00 || head[1] != 0x02) return 0;
    nfiles = unc_get_u32be(head + 8);
    if (nfiles == 0 || nfiles > 0xFFFF) return 0;
    if (head[24] == 0 || head[24] > 31) return 0;
    for (i = 0; i < head[24]; i++)
        if (head[25 + i] < 32) return 0;
    sum = 0;
    for (i = 24; i < 130; i++) sum += head[i];
    return sum == unc_get_u32be(head + 130);
}

/* DiskDoubler: 0xABCD0054 magic + XMODEM CRC of the 82-byte header
 * (or 0 in very old files), or the 'DDAR' archive variant.
 * Source: reference/XADMaster/XADDiskDoublerParser.m — its
 * reversed-table CRC formulation equals plain CRC-16/XMODEM, see
 * DECISIONS.md M0. */
int unc_diskdoubler_probe(const uint8_t *head, int32_t len)
{
    if (len >= 84 && unc_get_u32be(head) == 0xABCD0054u) {
        uint16_t crc = unc_get_u16be(head + 82);
        if (crc == 0 || crc == unc_crc16_xmodem(0, head, 82)) return 1;
    }
    if (len >= 78 && unc_get_u32be(head) == 0x44444152u &&    /* 'DDAR' */
        unc_get_u16be(head + 76) == unc_crc16_xmodem(0, head, 76)) return 1;
    if (len >= 62 && unc_get_u32be(head) == 0x44444132u &&    /* 'DDA2' */
        unc_get_u16be(head + 60) == unc_crc16_xmodem(0, head, 60)) return 1;
    return 0;
}

/* DiskCopy 4.2: no implementation exists in the available references
 * (XADMaster's DiskCopy support lives outside the cloned sources), so
 * per the no-invented-format-details rule this probe never matches. */
int unc_diskcopy_probe(const uint8_t *h, int32_t l, UncIO *io)
{
    (void)h; (void)l; (void)io;
    return 0;
}

/* LZH/LHA: "-lh?-" (lzh) or "-lz?-" (larc) method id at offset 2.
 * Source: reference/XADMaster/XADLZHParser.m. */
int unc_lzh_probe(const uint8_t *head, int32_t len)
{
    if (len < 7) return 0;
    if (head[2] != '-' || head[6] != '-') return 0;
    if (head[3] == 'l' && head[4] == 'h') {
        uint8_t m = head[5];
        return (m >= '0' && m <= '7') || m == 'd';
    }
    if (head[3] == 'l' && head[4] == 'z') {
        uint8_t m = head[5];
        return m == '0' || m == '4' || m == '5';
    }
    return 0;
}

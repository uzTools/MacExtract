/*
 * fmt_macbinary.c — MacBinary I/II/III decoder.
 *
 * MacBinary is a flat 128-byte header + data fork + resource fork,
 * each fork zero-padded to a 128-byte boundary. All header layout and
 * validation logic transcribed from:
 *   Source: reference/XADMaster/XADMacArchiveParser.m
 *           (+macBinaryVersionForHeader:, -parseMacBinaryWithDictionary:)
 *   — LGPL, see NOTICE.
 *
 * Header fields used (offsets in bytes):
 *     0  zero
 *     1  name length (1..63)
 *     2  name bytes (MacRoman)
 *    65  type (4)        69  creator (4)
 *    73  Finder flags, high byte
 *    74  zero
 *    82  zero
 *    83  data fork size (4)      87  resource fork size (4)
 *    91  creation date (4, Mac 1904 epoch)
 *    95  modification date (4)
 *   101  Finder flags, low byte (MacBinary II)
 *   102  'mBIN' signature (MacBinary III)
 *   108..115 zero
 *   120  secondary header length (2) — data starts at 128 + pad128(it)
 *   124  CRC-16/XMODEM of bytes 0..123 (MacBinary II/III)
 *
 * MacBinary I has no CRC; it is accepted only under the stricter
 * heuristics used by XADMaster (bytes 99..125 zero, plausible sizes,
 * nonzero dates).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define MB_HDR 128
#define MB_PAD(n) (((n) + 127u) & ~127u)

/* CRC-16 with reflected polynomial 0xA001 (CRC-16/USB when init and
 * final xor are 0xFFFF). XADMaster accepts this as a fallback header
 * checksum for files made by buggy encoders — see
 * reference/XADMaster/XADMacArchiveParser.m (XADCRCTable_a001 use).
 * Bitwise form; runs over 124 bytes only, speed is irrelevant. */
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
 * Transcribed from +macBinaryVersionForHeader: (see file comment). */
static int mb_version(const uint8_t *b, int32_t len)
{
    int i;
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
    if (unc_crc16_xmodem(0, b, 124) == unc_get_u16be(b + 124) ||
        (mb_crc16_a001(0xFFFF, b, 124) ^ 0xFFFF) == unc_get_u16be(b + 124)) {
        if (unc_get_u32be(b + 102) == 0x6D42494Eu) return 3; /* 'mBIN' */
        return 2;
    }

    /* MacBinary I heuristics. */
    for (i = 99; i <= 125; i++) if (b[i] != 0) return 0;
    if (unc_get_u32be(b + 83) > 0x7FFFFFFFu) return 0; /* data fork size */
    if (unc_get_u32be(b + 87) > 0x7FFFFFFFu) return 0; /* rsrc fork size */
    if (unc_get_u32be(b + 91) == 0) return 0;          /* creation date  */
    if (unc_get_u32be(b + 95) == 0) return 0;          /* mod date       */
    return 1;
}

int unc_macbinary_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return mb_version(head, len) > 0;
}

/* Stream `size` fork bytes from the current position to the sink,
 * then skip the padding up to a 128-byte boundary.
 * Returns UNC_OK or an error; short input yields UNC_ERR_TRUNCATED
 * after delivering what was available. */
static int mb_stream_fork(UncCtx *c, UncFork fork, uint32_t size,
                          uint8_t *buf, uint32_t bufsz)
{
    uint32_t left = size;
    while (left > 0) {
        int32_t want = (int32_t)(left < bufsz ? left : bufsz);
        int32_t r = c->io->read(c->io->ctx, buf, want);
        if (r < 0) return UNC_ERR_IO;
        if (r == 0) return UNC_ERR_TRUNCATED;
        if (!c->opt.test_only &&
            c->sink->write(c->sink->ctx, fork, buf, r) < 0)
            return UNC_ERR_SINK;
        left -= (uint32_t)r;
        {
            int e = unc_progress_add(&c->ps, (uint32_t)r);
            if (e != UNC_OK) return e;
        }
    }
    /* Skip zero padding to the next 128-byte boundary. */
    return unc_skip(c->io, MB_PAD(size) - size);
}

int unc_macbinary_extract(UncCtx *c)
{
    uint8_t hdr[MB_HDR];
    UncEntryInfo e;
    uint32_t datasize, rsrcsize, extsize;
    int err, sret;

    err = unc_read_at(c->io, 0, hdr, MB_HDR);
    if (err != UNC_OK) return err;
    if (mb_version(hdr, MB_HDR) == 0) return UNC_ERR_FORMAT;

    datasize = unc_get_u32be(hdr + 83);
    rsrcsize = unc_get_u32be(hdr + 87);
    extsize  = unc_get_u16be(hdr + 120);

    unc_entry_clear(&e);
    unc_entry_set_name(&e, hdr + 2, hdr[1]);
    e.type         = unc_get_u32be(hdr + 65);
    e.creator      = unc_get_u32be(hdr + 69);
    e.finder_flags = (uint16_t)((hdr[73] << 8) | hdr[101]);
    e.create_date  = unc_get_u32be(hdr + 91);
    e.mod_date     = unc_get_u32be(hdr + 95);
    e.data_size    = datasize;
    e.rsrc_size    = rsrcsize;
    e.comp_data_size = datasize;
    e.comp_rsrc_size = rsrcsize;

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) return UNC_ERR_SINK;
    if (sret > 0) return UNC_OK;    /* sink skipped the only entry */

    err = UNC_OK;
    if (!c->opt.list_only) {
        uint8_t *buf;
        uint32_t bufsz = UNC_PROGRESS_STEP;
        buf = (uint8_t *)unc_alloc(c->al, bufsz);
        if (!buf) err = UNC_ERR_MEM;
        if (err == UNC_OK) {
            /* Data fork begins after the (padded) secondary header. */
            if (c->io->seek(c->io->ctx, MB_HDR + MB_PAD(extsize)) < 0)
                err = UNC_ERR_IO;
            if (err == UNC_OK)
                err = mb_stream_fork(c, UNC_FORK_DATA, datasize, buf, bufsz);
            if (err == UNC_OK)
                err = mb_stream_fork(c, UNC_FORK_RSRC, rsrcsize, buf, bufsz);
            unc_free(c->al, buf);
        }
    }

    if (c->sink->end_entry(c->sink->ctx, err) < 0) return UNC_ERR_SINK;
    /* Per-entry errors were reported via end_entry; fatal ones stop us. */
    if (err == UNC_ERR_SINK || err == UNC_ERR_ABORTED || err == UNC_ERR_IO)
        return err;
    return UNC_OK;
}

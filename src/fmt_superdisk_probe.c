/* fmt_superdisk_probe.c — Alysis SuperDisk!'s probe(s), in the sniffer's image.
 *
 * Split out so the decoder can live in an overlay, and since 2026-10-21 in
 * the sniffer's own image with every other probe, run before the release
 * and given back with it (DECISIONS.md 2026-10-21, *the probes that left
 * with the bundle*).
 *
 * The helpers below come with it and are used by the decoder as well, so this
 * file is compiled into that overlay TOO — one definition, two places.
 *
 * Source: unchanged from fmt_superdisk.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_superdisk_priv.h"

const char sd_modsig[] = "SuperDisk! Add-In Module";
static int sd_end_marker_ok(UncIO *io)
{
    uint8_t tail[8];
    uint32_t size = unc_io_size32(io);
    int i;
    if (size == UNC_SIZE_UNKNOWN || size < 24) return 0;
    if (unc_read_at(io, size - 8, tail, 8) != UNC_OK) return 0;
    if (tail[0] != SD_TAG_END) return 0;
    for (i = 1; i < 8; i++)
        if (tail[i] != 0) return 0;
    return 1;
}

int sd_records_start(UncIO *io, uint32_t *out, int *has_module)
{
    uint8_t buf[32];
    uint32_t at, len;
    unsigned n;

    *has_module = 0;
    if (unc_read_at(io, 8, buf, 8) != UNC_OK) return UNC_ERR_FORMAT;
    if (buf[0] == SD_TAG_FILE || buf[0] == SD_TAG_DIR) {
        for (n = 1; n < 8; n++)
            if (buf[n] != 0) break;
        if (n == 8) { *out = 8u; return UNC_OK; }   /* the 1991 shape */
    }
    len = unc_get_u32be(buf);
    at = 12;
    for (n = 0; len != 0; n++) {
        unsigned i;
        if (n >= SD_MODULEMAX) return UNC_ERR_CORRUPT;
        if (len < 32 || len > 0x100000u) return UNC_ERR_FORMAT;
        if (unc_read_at(io, at + 4, buf, 24) != UNC_OK) return UNC_ERR_FORMAT;
        for (i = 0; i < 24; i++)
            if (buf[i] != (uint8_t)sd_modsig[i]) return UNC_ERR_FORMAT;
        *has_module = 1;
        at += len;
        if (unc_read_at(io, at, buf, 4) != UNC_OK) return UNC_ERR_FORMAT;
        len = unc_get_u32be(buf);
        at += 4;
    }
    *out = *has_module ? at : 8u;
    return UNC_OK;
}

uint32_t unc_superdisk_single_body(const uint8_t *head, int32_t len)
{
    uint32_t total, dlen, rlen, body, clen, ulen;
    uint32_t nlen;

    if (len < 40) return 0;
    total = unc_get_u32be(head);
    dlen  = unc_get_u32be(head + 4);
    rlen  = unc_get_u32be(head + 8);
    if (total == 0 || total > UNC_MAC_MAX) return 0;
    if (dlen > UNC_MAC_MAX || rlen > UNC_MAC_MAX) return 0;
    if (total != dlen + rlen) return 0;
    nlen = head[30];
    if (nlen == 0 || nlen > 31) return 0;
    body = 31u + nlen;
    if (body & 1u) body++;
    if ((int32_t)(body + 6u) > len) return 0;
    /* and the first block header has to be one */
    clen = unc_get_u16be(head + body);
    if (clen & 0x8000u) {
        if ((clen & 0x7FFFu) < 2 && clen != 0x8002u) return 0;
        return body;
    }
    if (clen < 8) return 0;
    ulen = unc_get_u16be(head + body + 2);
    if (ulen == 0 || ulen > SD_BLOCKMAX) return 0;
    return body;
}

UncFormat unc_superdisk_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t start;
    int has_module, i;

    if (len < 40) return UNC_FORMAT_UNKNOWN;
    if (unc_superdisk_single_body(head, len)) return UNC_FORMAT_SUPERDISK;
    /* Cheap rejection first: either a module signature sits where the
     * module chain would put it, or the ninth byte opens a record. */
    if (head[8] == SD_TAG_FILE || head[8] == SD_TAG_DIR) {
        for (i = 9; i < 16; i++)
            if (head[i] != 0) break;
        if (i == 16 && head[16] >= 1 && head[16] <= 31)
            return (sd_end_marker_ok(io))
           ? UNC_FORMAT_SUPERDISK : UNC_FORMAT_UNKNOWN;
        return UNC_FORMAT_UNKNOWN;
    }
    for (i = 0; i < 24; i++)
        if (head[16 + i] != (uint8_t)sd_modsig[i]) return UNC_FORMAT_UNKNOWN;
    if (sd_records_start(io, &start, &has_module) != UNC_OK) return UNC_FORMAT_UNKNOWN;
    return (sd_end_marker_ok(io))
           ? UNC_FORMAT_SUPERDISK : UNC_FORMAT_UNKNOWN;
}

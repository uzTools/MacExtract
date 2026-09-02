/* fmt_cpt_probe.c — Compact Pro's probe, kept resident.
 *
 * Split out on 2026-09-02 so the decoder can live in an overlay. `unc_sniff`
 * calls this for every file it is handed: a probe inside a blob would mean
 * loading the whole decoder in order to decide the file is not one of these.
 * Separating what DECIDES from what DECODES is what makes on-demand loading
 * pay at all (BRANCH_NOTES.md).
 *
 * Source: unchanged from fmt_cpt.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

UncFormat unc_cpt_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint8_t buf[256];   /* max chunk: 255-byte archive comment; entries
                         * are smaller (127-byte name + 45 meta) */
    uint32_t offset, crc, storedcrc, fsize;
    uint32_t nentries, commentlen, i;

    if (len < 8 || head[0] != 1) return UNC_FORMAT_UNKNOWN;
    offset = unc_get_u32be(head + 4);
    fsize = unc_io_size32(io);
    if (fsize != UNC_SIZE_UNKNOWN && (offset + 7 < offset || offset + 7 > fsize))
        return UNC_FORMAT_UNKNOWN;

    if (unc_read_at(io, offset, buf, 7) != UNC_OK) return UNC_FORMAT_UNKNOWN;
    storedcrc = unc_get_u32be(buf);
    crc = unc_crc32(UNC_CRC32_INIT, buf + 4, 3);
    nentries = unc_get_u16be(buf + 4);
    commentlen = buf[6];

    if (commentlen) {
        if (unc_read_full(io, buf, (int32_t)commentlen) != UNC_OK) return UNC_FORMAT_UNKNOWN;
        crc = unc_crc32(crc, buf, (int32_t)commentlen);
    }

    for (i = 0; i < nentries; i++) {
        uint32_t namelen, metalen, left;
        if (unc_read_full(io, buf, 1) != UNC_OK) return UNC_FORMAT_UNKNOWN;
        crc = unc_crc32(crc, buf, 1);
        namelen = buf[0] & 0x7f;
        metalen = (buf[0] & 0x80) ? 2 : 45;
        left = namelen + metalen;
        if (unc_read_full(io, buf, (int32_t)left) != UNC_OK) return UNC_FORMAT_UNKNOWN;
        crc = unc_crc32(crc, buf, (int32_t)left);
    }
    return (crc == storedcrc)
           ? UNC_FORMAT_COMPACTPRO : UNC_FORMAT_UNKNOWN;
}

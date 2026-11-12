/* fmt_vise_probe.c — Installer VISE's probe, in the sniffer's image.
 *
 * The layout, and where each fact comes from, is fmt_vise.c's file
 * comment, and the archive before 3.5, fmt_viseold.c's. Only a FIRST
 * segment is claimed: it is the one that holds the
 * catalogue, and a later one opened alone has nothing to show but bytes
 * that continue somebody else's.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_vise_priv.h"

/* 'SVCT', a version this engine reads, segment 1 of a count, and 'CVCT'
 * where the header says the catalogue is. Eight bytes 'SVCT'..'CVCT' apart
 * at an offset the file states, so a non-archive that opens with the four
 * letters is not enough. */
UncFormat unc_vise_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint8_t cv[4];
    unc_off_t size;
    uint32_t cat;

    size = io->size(io->ctx);
    /* Before 3.5: 'VISE', and at the catalogue a count, a zero word and
     * that many records, all inside the file. */
    if (len >= (int32_t)VISEO_HDR && vise_old_ok(head)) {
        cat = unc_get_u32be(head + VISEO_H_CAT);
        if (unc_read_at(io, cat, cv, 4) != UNC_OK || !unc_get_u16be(cv) ||
            unc_get_u16be(cv + 2) ||
            (size != UNC_OFF_UNKNOWN &&
             (unc_off_t)cat + 4 + (unc_off_t)unc_get_u16be(cv) * VISEO_REC
                 > size))
            return UNC_FORMAT_UNKNOWN;
        return UNC_FORMAT_VISE;
    }
    if (len < (int32_t)VISE_HDR || !vise_first_ok(head))
        return UNC_FORMAT_UNKNOWN;
    cat = unc_get_u32be(head + VISE_H_CAT);
    if (size != UNC_OFF_UNKNOWN && (unc_off_t)cat + VISE_CAT_HDR > size)
        return UNC_FORMAT_UNKNOWN;
    if (unc_read_at(io, cat, cv, 4) != UNC_OK ||
        unc_get_u32be(cv) != VISE_CAT_MAGIC)
        return UNC_FORMAT_UNKNOWN;
    return UNC_FORMAT_VISE;
}

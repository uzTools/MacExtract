/* fmt_viseset.c — which Installer VISE set a segment belongs to, and which
 * segment of it it is. An archive of the VISE before 3.5 (fmt_viseold.c)
 * is a set of one.
 *
 * In a file of its own for the reason fmt_abkset.c is: the Macintosh build
 * carries it in two images, the sniffer's and the reader's, which is the
 * one an installer keeps while its part search runs after the release.
 *
 * Segment 1 states the count (+20); no later segment does, so only the
 * first describes the set. VISE X's payload, Installer.data, is segment 1
 * with no count and the installer's stamp: the set's second file. Every segment repeats the version and the long
 * at +12, which is what ties them together: three segments of one set
 * agree on it and two installers here do not (fmt_vise.c).
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_vise_priv.h"

int unc_vise_describe(UncIO *io, UncSegmentDesc *desc)
{
    uint8_t h[VISE_HDR];
    unsigned i;

    if (unc_read_at(io, 0, h, (int32_t)VISEO_HDR) != UNC_OK)
        return UNC_ERR_FORMAT;
    for (i = 0; i < UNC_SEG_FP_LEN; i++) desc->fp[i] = 0;
    /* Before 3.5 there are no segments: a set of one, whose fingerprint
     * no 'SVCT' segment can match. */
    if (vise_old_ok(h)) {
        for (i = 0; i < 4; i++) {
            desc->fp[i] = h[4 + i];
            desc->fp[4 + i] = h[i];
        }
        desc->nparts = 1;
        goto common;
    }
    if (unc_read_at(io, 0, h, (int32_t)VISE_HDR) != UNC_OK ||
        !vise_first_ok(h))
        return UNC_ERR_FORMAT;
    for (i = 0; i < 4; i++) {
        desc->fp[i] = h[VISE_H_STAMP + i];
        desc->fp[4 + i] = h[VISE_H_VER + i];
    }
    desc->nparts    = (uint16_t)unc_get_u32be(h + VISE_H_COUNT);
    /* VISE X: the installer holds the catalogue alone, and what the
     * records call segment 1 is the second file of the set. */
    if (vise_suffixes(unc_get_u32be(h + VISE_H_VER)) & VISE_X)
        desc->nparts++;
common:
    desc->name[0] = 0;          /* the installer's name is the host's */
    desc->name_len = 0;
    desc->scheme    = UNC_FORMAT_VISE;
    desc->part      = 1;
    desc->head_len  = VISE_HDR;
    desc->total     = UNC_SIZE_UNKNOWN;   /* addressed: not the host's */
    desc->data_size = desc->rsrc_size = 0;
    desc->type = desc->creator = 0;
    desc->finder_flags = 0;
    desc->create_date = desc->mod_date = 0;
    return UNC_OK;
}

int unc_vise_match(const UncSegmentDesc *desc, const uint8_t *head,
                   int32_t len)
{
    uint32_t part;
    unsigned i;

    if (len < (int32_t)VISE_HDR || unc_get_u32be(head) != VISE_MAGIC)
        return 0;
    for (i = 0; i < 4; i++)
        if (head[VISE_H_STAMP + i] != desc->fp[i] ||
            head[VISE_H_VER + i] != desc->fp[4 + i])
            return 0;
    part = unc_get_u32be(head + VISE_H_PART);
    /* VISE X's Installer.data: segment 1 with no count, the set's second
     * file. Its later segments are not known here. */
    if (vise_suffixes(unc_get_u32be(head + VISE_H_VER)) & VISE_X)
        return part == 1 && unc_get_u32be(head + VISE_H_COUNT) == 0 ? 2 : 0;
    if (part < 1 || part > desc->nparts) return 0;
    return (int)part;
}

/* fmt_abkset.c — which Apple Backup set a disk belongs to, and which disk
 * of it it is.
 *
 * In a file of its own, apart from the reader, because the Macintosh
 * build carries it in two images: the sniffer's, which answers every
 * scheme's describe and match while the bundle is whole, and ovl_zipold,
 * the reader's, which is the one image an Apple Backup set keeps while
 * its part search runs after the release (mac/ovl_shim.c; DECISIONS.md
 * 2026-11-09, *the set's identity that left*).
 *
 * Every disk states its own number and the set's count, so any disk
 * describes the whole set (fmt_abk.c). The set's identity is the backup's
 * start time, which every disk header and every item header repeats; two
 * backups of one drive differ in it, and every file on every disk is
 * called "Apple Backup Data", so a name says nothing.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_abk_priv.h"

int unc_abk_describe(UncIO *io, UncSegmentDesc *desc)
{
    uint8_t h[ABK_DISK_HDR];
    int i, n;

    if (unc_read_at(io, 0, h, (int32_t)ABK_DISK_HDR) != UNC_OK ||
        !abk_disk_ok(h))
        return UNC_ERR_FORMAT;
    for (i = 0; i < UNC_SEG_FP_LEN; i++) desc->fp[i] = 0;
    for (i = 0; i < 4; i++) desc->fp[i] = h[0x0A + i];
    /* The drive the backup was made of: what the user knows the set as,
     * and the folder name a host may give what it restores. A Str31. */
    n = h[0x12] > 31 ? 31 : h[0x12];
    for (i = 0; i < n; i++) desc->name[i] = h[0x13 + i];
    desc->name[n] = 0;
    desc->name_len = (uint16_t)n;
    desc->scheme    = UNC_FORMAT_ABK;
    desc->part      = unc_get_u16be(h + 6);
    desc->nparts    = unc_get_u16be(h + 8);
    desc->head_len  = ABK_FIRST;
    desc->total     = UNC_SIZE_UNKNOWN;   /* addressed: not the host's */
    desc->data_size = desc->rsrc_size = 0;
    desc->type = desc->creator = 0;
    desc->finder_flags = 0;
    desc->create_date = desc->mod_date = 0;
    return UNC_OK;
}

int unc_abk_match(const UncSegmentDesc *desc, const uint8_t *head,
                  int32_t len)
{
    int i;

    if (len < (int32_t)ABK_DISK_HDR || !abk_disk_ok(head)) return 0;
    for (i = 0; i < 4; i++)
        if (head[0x0A + i] != desc->fp[i]) return 0;
    if (unc_get_u16be(head + 8) != desc->nparts) return 0;
    return (int)unc_get_u16be(head + 6);
}

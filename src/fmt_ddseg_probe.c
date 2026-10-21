/* fmt_ddseg_probe.c — the probe for one part of a DiskDoubler `SPLT` set,
 * and the header parse it shares with the reader (ddseg_parse). The
 * layout, read off specimens, is fmt_ddseg.c's file comment.
 *
 * Every probe is in its reader's `_probe.c`, resident, so the reader can
 * be an overlay: unc_sniff calls every probe for every file it is handed,
 * before any image is chosen (DECISIONS.md 2026-10-20, *one place for
 * every probe*). What a probe and its reader share is defined once, here.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_ddseg_priv.h"

static int ddseg_magic(const uint8_t *h)
{
    return h[0] == 'S' && h[1] == 'P' && h[2] == 'L' && h[3] == 'T';
}

/* Parse and validate a header. `desc` may be NULL to validate only. */
int ddseg_parse(const uint8_t *h, int32_t len, UncSegmentDesc *desc,
                uint32_t *paylen_out)
{
    uint32_t data, rsrc, paylen;
    uint32_t nparts, index;
    int32_t i;

    if (len < UNC_DDSEG_HEAD) return UNC_ERR_FORMAT;
    /* Both marks, because 'SPLT' alone at offset 0 is four bytes that
     * any file could open with; the second one sits where this header
     * ends and is what makes the pair a shape rather than a word. */
    if (!ddseg_magic(h) || !ddseg_magic(h + DS_MAGIC2)) return UNC_ERR_FORMAT;

    nparts = unc_get_u16be(h + DS_NPARTS);
    index  = unc_get_u16be(h + DS_INDEX);
    if (nparts < 1 || nparts > UNC_SEG_MAX_PARTS) return UNC_ERR_FORMAT;
    if (index >= nparts) return UNC_ERR_FORMAT;

    data   = unc_get_u32be(h + DS_DATALEN);
    rsrc   = unc_get_u32be(h + DS_RSRCLEN);
    paylen = unc_get_u32be(h + DS_PAYLEN);
    /* HFS caps a fork at 2 GB and the engine is 32-bit throughout. */
    if (data > UNC_MAC_MAX || rsrc > UNC_MAC_MAX) return UNC_ERR_FORMAT;
    /* One part cannot hold more than the whole file. */
    if (paylen > data + rsrc) return UNC_ERR_FORMAT;
    if (paylen_out) *paylen_out = paylen;

    if (desc) {
        desc->scheme   = UNC_FORMAT_DDSEG;
        desc->part     = (uint16_t)(index + 1u);
        desc->head_len = UNC_DDSEG_HEAD;
        desc->nparts   = (uint16_t)nparts;
        desc->name[0]  = 0;
        desc->name_len = 0;
        for (i = 0; i < UNC_SEG_FP_LEN; i++) desc->fp[i] = h[DS_ID + i];

        desc->data_size    = data;
        desc->rsrc_size    = rsrc;
        desc->total        = data + rsrc;
        desc->type         = unc_get_u32be(h + DS_TYPE);
        desc->creator      = unc_get_u32be(h + DS_CREATOR);
        desc->finder_flags = unc_get_u16be(h + DS_FFLAGS);
        desc->mod_date     = unc_get_u32be(h + DS_MTIME);
        desc->create_date  = unc_get_u32be(h + DS_CTIME);
    }
    return UNC_OK;
}

UncFormat unc_ddseg_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return (ddseg_parse(head, len, NULL, NULL) == UNC_OK)
           ? UNC_FORMAT_DDSEG : UNC_FORMAT_UNKNOWN;
}

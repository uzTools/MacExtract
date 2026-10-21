/* fmt_sitseg_probe.c — the probe for one part of a StuffIt segmented set,
 * and the header parse it shares with the reader (sitseg_parse).
 *
 * Every probe is in its reader's `_probe.c`, resident, so the reader can
 * be an overlay: unc_sniff calls every probe for every file it is handed,
 * before any image is chosen (DECISIONS.md 2026-10-20, *one place for
 * every probe*). What a probe and its reader share is defined once, here.
 *
 * Source: reference/XADMaster/XADStuffItSplitParser.m — every offset
 * below; fmt_sitseg.c's file comment states the layout, and what it
 * costs that nothing else describes it.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_sitseg_priv.h"

/* Header field offsets. */
#define SS_PART      3
#define SS_NAMELEN   4
#define SS_NAME      5
#define SS_FP       68          /* start of the 26 fingerprint bytes */
#define SS_TYPE     68
#define SS_CREATOR  72
#define SS_FFLAGS   76
#define SS_CTIME    78
#define SS_MTIME    82
#define SS_RSRCLEN  86
#define SS_DATALEN  90

/* Parse and validate a header. Returns UNC_OK or UNC_ERR_FORMAT.
 * `desc` may be NULL to validate only. */
int sitseg_parse(const uint8_t *h, int32_t len, UncSegmentDesc *desc)
{
    int32_t i;
    uint32_t nl;

    if (len < UNC_SEG_HEAD) return UNC_ERR_FORMAT;
    if (h[0] != 0xB0 || h[1] != 0x56 || h[2] != 0x00) return UNC_ERR_FORMAT;
    if (h[SS_PART] == 0) return UNC_ERR_FORMAT;
    nl = h[SS_NAMELEN];
    if (nl == 0 || nl > 63) return UNC_ERR_FORMAT;
    for (i = 0; i < (int32_t)nl; i++)
        if (h[SS_NAME + i] == 0) return UNC_ERR_FORMAT;

    if (desc) {
        uint32_t rsrc = unc_get_u32be(h + SS_RSRCLEN);
        uint32_t data = unc_get_u32be(h + SS_DATALEN);

        /* HFS caps a fork at 2 GB and the engine is 32-bit throughout;
         * a sum that wraps would make `total` describe less than the
         * forks it is the total of. */
        if (rsrc > UNC_MAC_MAX || data > UNC_MAC_MAX) return UNC_ERR_FORMAT;

        desc->scheme   = UNC_FORMAT_SITSEG;
        desc->part     = h[SS_PART];
        desc->head_len = UNC_SEG_HEAD;
        desc->name_len = (uint16_t)nl;
        for (i = 0; i < (int32_t)nl; i++) desc->name[i] = h[SS_NAME + i];
        desc->name[nl] = 0;
        for (i = 0; i < UNC_SEG_FP_LEN; i++) desc->fp[i] = h[SS_FP + i];

        desc->rsrc_size    = rsrc;
        desc->data_size    = data;
        desc->total        = rsrc + data;
        desc->type         = unc_get_u32be(h + SS_TYPE);
        desc->creator      = unc_get_u32be(h + SS_CREATOR);
        desc->finder_flags = unc_get_u16be(h + SS_FFLAGS);
        desc->create_date  = unc_get_u32be(h + SS_CTIME);
        desc->mod_date     = unc_get_u32be(h + SS_MTIME);
    }
    return UNC_OK;
}

UncFormat unc_sitseg_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return (sitseg_parse(head, len, NULL) == UNC_OK)
           ? UNC_FORMAT_SITSEG : UNC_FORMAT_UNKNOWN;
}

/* ovlbox_seghooks.c - the joiner's three hooks, for the host lanes.
 *
 * On a Macintosh src/unc_segment.c is built into the set code's image
 * (tools/overlay/ovl_segrun.c), which defines unc_sitseg_emit,
 * unc_ddseg_payload and unc_mimeseg_head over mac/ovl_shim.c's
 * ovl_seg_hook. The host lanes link src/unc_segment.c resident, so they
 * get the same three here.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "overlay.h"
#include "macextract.h"
#include "unc_internal.h"

int32_t ovl_seg_hook(int32_t which, OvlArgs *g);

int unc_sitseg_emit(UncCtx *c, const UncSegmentDesc *desc, uint32_t base,
                    int data_first, const int *ioerr)
{
    OvlArgs g;
    g.obj = c; g.in = desc; g.len = base; g.pos = (uint32_t)data_first;
    g.out = (void *)ioerr;
    return (int)ovl_seg_hook(OVL_SITSEG_EMIT, &g);
}

int unc_ddseg_payload(const UncSegmentDesc *desc, const uint8_t *head,
                      int32_t len, int part, uint32_t size, uint32_t *payload)
{
    OvlArgs g;
    g.obj = (void *)desc; g.in = head; g.len = (uint32_t)len;
    g.pos = (uint32_t)part; g.extra = size; g.off_out = payload;
    return (int)ovl_seg_hook(OVL_DDSEG_PAYLOAD, &g);
}

int unc_mimeseg_head(const UncSegmentDesc *d, UncIO *io, int part,
                     uint32_t size, uint32_t *out)
{
    OvlArgs g;
    g.obj = (void *)d; g.in = io; g.pos = (uint32_t)part; g.extra = size;
    g.off_out = out;
    return (int)ovl_seg_hook(OVL_MIMESEG_HEAD, &g);
}

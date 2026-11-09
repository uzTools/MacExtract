/* ovl_cptdd.c — Compact Pro and DiskDoubler as an overlay.
 *
 * The decoder source is compiled in UNMODIFIED; every engine helper it calls
 * is defined by ovl_forwards_gen.c as a forward through the host vector
 * (tools/overlay/mkforwards.py). The PROBE is not here: it stays resident, or
 * sniffing a file would load the decoder in order to decide it is not one.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "overlay.h"
#include "ovl_host_gen.h"

/* Initialised non-zero: a zero initialiser lands in .bss, which objcopy
 * leaves out of the image and mkoverlay.sh refuses. */
const OverlayHostFns *g_ovl_fns = (const OverlayHostFns *)-1;

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b);
int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)b;
    g_ovl_fns = (const OverlayHostFns *)host->fns;
    switch (which) {
    case OVL_SELFTEST:
        return 0x4F4B;
    case OVL_CPT_EXTRACT:
        return (int32_t)unc_cpt_extract((UncCtx *)a);
    case OVL_DD_EXTRACT:
        return (int32_t)unc_dd_extract((UncCtx *)a);
    /* A Compact Pro set keeps this image and not the sniffer's, and its
     * parts are still being matched while it is read: the part search a
     * disk swap starts (mac/ovl_shim.c, unc_segment_match). */
    case OVL_SEG_MATCH: {
        const OvlArgs *g = (const OvlArgs *)a;
        return (int32_t)unc_cptseg_match((const UncSegmentDesc *)g->obj,
                                         (const uint8_t *)g->in,
                                         (int32_t)g->len);
    }
    default:
        return -1;
    }
}

/* ovl_vise.c — the Installer VISE reader as an overlay.
 *
 * The decoder source is compiled in UNMODIFIED; every engine helper it calls
 * is defined by ovl_forwards_gen.c as a forward through the host vector
 * (tools/overlay/mkforwards.py), the bit reader and the canonical decoder
 * among them, which live in the shared codecs image. The PROBE is not here:
 * it is in the sniffer's image.
 *
 * Its own image, for the reason every format family has one: what an
 * installer costs the engine is this image and nothing else, and nothing
 * else pays for it (DECISIONS.md 2026-11-11, *the installer that was an
 * archive*).
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
    case OVL_VISE_EXTRACT:
        return (int32_t)unc_vise_extract((UncCtx *)a);
    /* A set keeps this image and not the sniffer's, and its segments are
     * still being matched while it is read: the part search a disk swap
     * starts (mac/ovl_shim.c, unc_segment_match). */
    case OVL_SEG_MATCH: {
        const OvlArgs *g = (const OvlArgs *)a;
        return (int32_t)unc_vise_match((const UncSegmentDesc *)g->obj,
                                       (const uint8_t *)g->in,
                                       (int32_t)g->len);
    }
    default:
        return -1;
    }
}

/* ovl_sqp.c — the AppleLink package decoder as an overlay.
 *
 * The decoder source is compiled in UNMODIFIED; every engine helper it calls
 * is defined by ovl_forwards_gen.c as a forward through the host vector
 * (tools/overlay/mkforwards.py), including unc_lzw_*, which lives in the
 * shared codecs image. The PROBE is not here: it stays resident, or sniffing
 * a file would load the decoder in order to decide it is not one.
 *
 * Its own image rather than a lodger in another, for the reason the build
 * gives for one image per format family: what a .pkg costs the engine is
 * then the 1,038 B of this image and nothing else (FORMATS.md, *Overlays*;
 * DECISIONS.md 2026-10-05).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
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
    case OVL_SQP_EXTRACT:
        return (int32_t)unc_sqp_extract((UncCtx *)a);
    default:
        return -1;
    }
}

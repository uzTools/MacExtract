/* ovl_stuffit.c — StuffIt classic and StuffIt 5 as an overlay.
 *
 * The decoder source is compiled in UNMODIFIED; every engine helper it calls
 * is defined by ovl_forwards_gen.c as a forward through the host vector
 * (tools/overlay/mkforwards.py). Private File's reader is here too. The PROBE is not here: it stays resident, or
 * sniffing a file would load the decoder in order to decide it is not one.
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
    case OVL_SIT_EXTRACT:
        return (int32_t)unc_sit_extract((UncCtx *)a);
    case OVL_SIT5_EXTRACT:
        return (int32_t)unc_sit5_extract((UncCtx *)a);
    /* Private File lodges here: what it decrypts is always a StuffIt
     * archive (src/fmt_pf.c), so the two are never wanted apart. */
    case OVL_PF_EXTRACT:
        return (int32_t)unc_pf_extract((UncCtx *)a);
    default:
        return -1;
    }
}

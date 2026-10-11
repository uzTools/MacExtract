/* ovl_zipold.c — zip's Shrink and Reduce, in an overlay only zip keeps.
 *
 * They are called from the zip reader in `ovl_exo`, which is too close to
 * the 32 KB a 68000's 16-bit PC-relative references reach to hold them
 * (FORMATS.md, *Shrink*). They were in the codecs image until 2026-10-11,
 * which every format keeps, so every format paid 2,275 B of heap for two
 * methods only zip has (FORMATS.md, *Reduce*). This image patches itself
 * into the host vector exactly as ovl_codecs.c does, and the eager release
 * keeps it for zip alone.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "overlay.h"
#include "ovl_host_gen.h"
#include "ovl_zipold_exports_gen.h"

const OverlayHostFns *g_ovl_fns = (const OverlayHostFns *)-1;

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b);
int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)b;
    g_ovl_fns = (const OverlayHostFns *)host->fns;
    switch (which) {
    case OVL_SELFTEST:
        return 0x4F4B;
    case OVL_CODEC_EXPORTS:
        OVL_ZIPOLD_EXPORTS_FILL((OverlayHostFns *)a);
        return 0;
    default:
        return -1;
    }
}

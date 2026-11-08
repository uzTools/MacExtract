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
 * Tar's reader too, since 2026-10-17 (src/fmt_tar.c says why): the eager
 * release keeps this image, and only this one, for a tar. And MAR's, since
 * 2026-11-03, on the same terms: a reader that calls no codec; and the
 * LZ4 frame's, the same day, the form mar 0.2.0 reads a MAR compressed in.
 *
 * Implode too (src/unc_implode.c), since 2026-10-17, when `ovl_exo` reached
 * the 32 KB it can span (DECISIONS.md 2026-10-17, *dates in the Macintosh's
 * own zone*).
 *
 * The Mac OS X sidecars too (src/unc_sidecar.c), since 2026-10-17: zip
 * calls them from `ovl_exo` through the vector this image patches, and tar
 * from inside it (DECISIONS.md 2026-10-17, *the sidecars Mac OS X left
 * beside the file*).
 *
 * SPDX-License-Identifier: 0BSD
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
    case OVL_TAR_EXTRACT:
        return (int32_t)unc_tar_extract((UncCtx *)a);
    case OVL_MAR_EXTRACT:
        return (int32_t)unc_mar_extract((UncCtx *)a);
    case OVL_LZ4_EXTRACT:
        return (int32_t)unc_lz4_extract((UncCtx *)a);
    default:
        return -1;
    }
}

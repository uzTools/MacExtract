/* ovl_dart.c — DART's decoder as an overlay.
 *
 * The decoder source is compiled in UNMODIFIED; every engine helper it calls
 * is defined by ovl_forwards_gen.c as a forward through the host vector
 * (tools/overlay/mkforwards.py). `unc_lzah_decode` — DART's "best" method is
 * LZHUF — comes from the codecs overlay, which the shim makes ready before
 * it loads this one, exactly as ovl_lzh.c gets it.
 *
 * fmt_dart_probe.c is compiled in TOO, and is resident as well. That is not
 * an oversight: DART has no signature, so its probe is the whole header
 * reader, and the decoder needs the same reader. Duplicating ~400 B beats
 * either making the decoder call back into the host for it or making the
 * probe load the overlay to sniff a file that turns out not to be a DART.
 * ovl_spacesaver.c does the same thing for the same reason.
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
    case OVL_DART_EXTRACT:
        return (int32_t)unc_dart_extract((UncCtx *)a);
    default:
        return -1;
    }
}

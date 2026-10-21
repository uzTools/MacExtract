/* ovl_sniff.c — the entry of the sniffer's image: unc_sniff and the
 * twenty-six probes it walks, compiled unmodified. The EAGER lifetime runs
 * it from the bundle before the release and gives it back with the rest;
 * the LAZY one reads it once and keeps it like any other image
 * (DECISIONS.md 2026-10-21, *the probes that left with the bundle*).
 *
 * Its forwards file leaves out unc_macbinary_probe, which this image
 * defines itself (tools/overlay/mkforwards.py, SNIFF).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "overlay.h"
#include "ovl_host_gen.h"

const OverlayHostFns *g_ovl_fns = (const OverlayHostFns *)-1;

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b);
int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)b;
    g_ovl_fns = (const OverlayHostFns *)host->fns;
    switch (which) {
    case OVL_SELFTEST:
        return 0x4F4B;
    case OVL_SNIFF:
        return (int32_t)unc_sniff((UncIO *)a);
    default:
        return -1;
    }
}

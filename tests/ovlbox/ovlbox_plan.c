/* ovlbox_plan.c — the eager release's plan, compiled into the host lane.
 *
 * On the Macintosh the plan runs in the set's setup image
 * (tools/overlay/ovl_segsetup.c), which is Toolbox code that only the
 * Retro68 build makes, so this lane has no such image to call. The loader
 * reaches the plan through OVL_PLAN, which this lane defines as
 * ovlbox_plan: the same source, mac/release_plan.inc.c, compiled here and
 * handed the sniffer's image exactly as the shell's ovl_plan hands it.
 * Natively the sniffer cannot be called, and the loader test's releases
 * (StuffIt, LZH) never ask it; under qemu-m68k the sink lane's envelopes
 * do, through the real image.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "ovl_load.h"

static void *peek_alloc(void *ctx, uint32_t size)
{
    (void)ctx;
    return NewPtr((Size)size);
}

static void peek_free(void *ctx, void *ptr)
{
    (void)ctx;
    if (ptr) DisposePtr((Ptr)ptr);
}

#include "release_plan.inc.c"

int ovlbox_plan(UncFormat fmt, UncIO *io, unsigned char *out);
int ovlbox_plan(UncFormat fmt, UncIO *io, unsigned char *out)
{
    return release_plan(&gOvlHost, ovl_image(OVL_ID_SNIFF), fmt, io, out);
}

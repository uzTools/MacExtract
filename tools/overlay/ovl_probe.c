/* ovl_probe.c — the smallest overlay that can prove the mechanism works:
 * one blob, loaded from a resource, called through a locked handle, with one
 * entry that answers from its own PC-relative data and one that calls back
 * into the application through the host vector. If this runs on a 68000, the
 * hard parts (position independence, the handle call, the vector table) are
 * done and the rest is porting decoders in behind it. */
#include "overlay.h"

/* Deliberately a TABLE, not a constant: a table forces the PC-relative data
 * reference that is the whole question. */
static const uint8_t ovl_marker[8] = { 0x4F, 0x4B, 0, 0, 0, 0, 0, 0 };

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b);
int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)b;
    switch (which) {
    case OVL_SELFTEST:
        return ((int32_t)ovl_marker[0] << 8) | (int32_t)ovl_marker[1];
    case OVL_CRC_VIA_HOST:
        return (int32_t)host->crc32(0, (const uint8_t *)a, 4);
    default:
        return -1;
    }
}

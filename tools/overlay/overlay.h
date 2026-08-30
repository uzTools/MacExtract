/* overlay.h — the contract between the application and a loadable overlay.
 *
 * An overlay is a flat, position-independent blob stored as a resource and
 * loaded only when the archive needs it. Its whole point is that its CODE is
 * not resident: code is the only thing that costs the engine budget on a
 * Macintosh (FORMATS.md, *What the application costs the engine*).
 *
 * Position independence comes from -mpcrel, which turns internal references
 * into PC-relative ones the LINKER resolves, so a linked blob carries no
 * runtime relocations. That costs a +-32 KB range, which bounds an overlay's
 * size and is checked by the build.
 *
 * Everything an overlay needs from outside itself arrives in OverlayHost. It
 * may not call the application directly: there is no relocation left to patch
 * such a call with.
 */
#ifndef UNC_OVERLAY_H
#define UNC_OVERLAY_H

#include <stdint.h>

typedef struct OverlayHost {
    uint32_t (*crc32)(uint32_t crc, const uint8_t *p, uint32_t n);
    void    *(*alloc)(void *ctx, uint32_t n);
    void     (*free)(void *ctx, void *p);
    void     *alloc_ctx;
} OverlayHost;

/* Every overlay begins with this, at offset 0 of the blob: the application
 * jumps straight to the start of the locked handle. `which` selects the
 * entry point, so one overlay can carry several. */
typedef int32_t (*OverlayEntry)(const OverlayHost *host, int32_t which,
                                void *a, void *b);

#define OVL_SELFTEST 0      /* returns 0x4F4B ('OK') — proves the mechanism */
#define OVL_CRC_VIA_HOST 1  /* calls back through the host vector           */

#endif

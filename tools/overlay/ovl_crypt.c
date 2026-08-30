/* ovl_crypt.c — the first REAL overlay: the cipher module, out of resident
 * code and into a resource loaded only when an archive turns out to be
 * encrypted.
 *
 * unc_crypt.c is compiled in unmodified. It has five external references and
 * they are why this module was chosen first: __divsi3, __modsi3, __mulsi3 and
 * __umodsi3 are libgcc and link INTO the blob, and unc_crc32 is the only call
 * back into the application, which the glue below routes through the host
 * vector. Nothing in the engine calls into unc_crypt except through the
 * entry points dispatched here, so the seam is clean.
 */
#include "overlay.h"
#include <stdint.h>

/* Set once per call from the entry point, so unc_crypt.c can be compiled
 * unmodified: its call to unc_crc32 binds to the definition below.
 *
 * INITIALISED, deliberately. An uninitialised static lands in .bss, which
 * objcopy leaves OUT of the image — the blob would write past its own end and
 * into the heap. An initialised one lands in .data, inside the image, which
 * is a locked Handle and therefore writable. mkoverlay.sh refuses .bss for
 * exactly this reason and allows .data. */
static const OverlayHost *g_host = (const OverlayHost *)-1;

uint32_t unc_crc32(uint32_t crc, const uint8_t *buf, int32_t len);
uint32_t unc_crc32(uint32_t crc, const uint8_t *buf, int32_t len)
{
    return g_host->crc32(crc, buf, (uint32_t)len);
}

/* The cipher entry points the application needs. Kept as a dispatch rather
 * than one entry per function because a resource has one start address. */
struct UncCrypt;
void unc_crypt_apply(struct UncCrypt *cr, uint8_t *buf, int32_t len);

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b);
int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    g_host = host;
    switch (which) {
    case OVL_SELFTEST:
        return 0x4F4B;
    case OVL_CRYPT_APPLY: {
        OvlCryptArgs *g = (OvlCryptArgs *)a;
        (void)b;
        unc_crypt_apply((struct UncCrypt *)g->cr, g->buf, g->len);
        return 0;
    }
    default:
        return -1;
    }
}

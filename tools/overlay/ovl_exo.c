/* ovl_exo.c — zip, gzip, Unix compress and tar as an overlay.
 *
 * The decoder source is compiled in UNMODIFIED; every engine helper it calls
 * is defined by ovl_forwards_gen.c as a forward through the host vector
 * (tools/overlay/mkforwards.py). The PROBE is not here: it stays resident, or
 * sniffing a file would load the decoder in order to decide it is not one.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "overlay.h"
#include "ovl_host_gen.h"

/* Initialised non-zero: a zero initialiser lands in .bss, which objcopy
 * leaves out of the image and mkoverlay.sh refuses. */
const OverlayHostFns *g_ovl_fns = (const OverlayHostFns *)-1;

/* An overlay links no libc, and zlib wants three primitives from it.
 *
 * memcpy is real: inflate copies its window with it on every block, so this
 * is a working implementation and not a stub. malloc and free are the other
 * kind and say so — src/unc_inflate.c installs the engine's own allocator
 * into the z_stream (unc_zalloc/unc_zfree), so zlib's zcalloc/zcfree are
 * never called. They exist because inflateInit2_ REFERENCES them whether or
 * not the path runs, and a NULL from malloc is the answer zlib is written to
 * handle: it returns Z_MEM_ERROR, which surfaces as a per-entry memory error
 * rather than as anything silent. */
void *memcpy(void *dst, const void *src, unsigned long n);
void *memcpy(void *dst, const void *src, unsigned long n)
{
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    while (n--) *d++ = *s++;
    return dst;
}

void *malloc(unsigned long n);
void *malloc(unsigned long n) { (void)n; return (void *)0; }

void free(void *p);
void free(void *p) { (void)p; }

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b);
int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)b;
    g_ovl_fns = (const OverlayHostFns *)host->fns;
    switch (which) {
    case OVL_SELFTEST:
        return 0x4F4B;
    case OVL_ZIP_EXTRACT:
        return (int32_t)unc_zip_extract((UncCtx *)a);
    case OVL_GZIP_EXTRACT:
        return (int32_t)unc_gzip_extract((UncCtx *)a);
    case OVL_COMPRESSZ_EXTRACT:
        return (int32_t)unc_compressz_extract((UncCtx *)a);
    case OVL_TAR_EXTRACT:
        return (int32_t)unc_tar_extract((UncCtx *)a);
    default:
        return -1;
    }
}

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
 * memcpy used to be defined here — inflate copies its window with it on every
 * block — and is now tools/overlay/ovl_rt.c's, which every image links and
 * --gc-sections drops where nothing calls it. One definition rather than one
 * per image that needs one: a second image reaching for memcpy was a link
 * failure to be solved by hand, and the compiler can emit that call from
 * source that never mentions it.
 *
 * malloc and free stay HERE, and are the other kind of primitive: stubs.
 * src/unc_inflate.c installs the engine's own allocator into the z_stream
 * (unc_zalloc/unc_zfree), so zlib's zcalloc/zcfree are never called. They
 * exist because inflateInit2_ REFERENCES them whether or not the path runs,
 * and a NULL from malloc is the answer zlib is written to handle: it returns
 * Z_MEM_ERROR, which surfaces as a per-entry memory error rather than as
 * anything silent. They are not in the runtime net deliberately — a stub that
 * answers NULL is right for zlib and wrong as a default for whatever reaches
 * for malloc next, and a link failure is how that gets noticed. */
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

/* ovl_load.h — what the dispatch shims ask of a loader, and nothing more.
 *
 * `mac/ovl_shim.c` holds one shim per engine entry point and knows only these
 * calls; the LIFETIME of an image — read at launch as one bundle and released
 * once the format is known, or read per format when a format turns out to
 * want it — is a whole file behind them, chosen at build time:
 *
 *   mac/ovl_load_eager.c   the default
 *   mac/ovl_load_lazy.c    UNC_OVL_LAZY=1 in the environment at configure
 *                          time, which every harness here can pass as
 *                          `-D UNC_OVL_LAZY`
 *
 * The two were separate branches for a month (`overlay-eager`,
 * `selective-loading`) and 21 of the 24 files under tools/overlay/ were
 * byte-identical between them, which is how the same build-staleness fix came
 * to be written twice, days apart. They share everything here instead.
 *
 * Shared by both, in mac/ovl_reloc.c: the relocation trailer and the
 * instruction-cache flush. BOTH lifetimes write executable bytes as data and
 * then execute them — the eager one twice, once in the bundle and once in the
 * copy it keeps — so both need the flush Inside Macintosh: Memory requires
 * (*Stale Instructions*; DECISIONS.md 2026-09-25, *the flush nobody wrote*).
 */
#ifndef OVL_LOAD_H
#define OVL_LOAD_H

#include "overlay.h"
#include "unc_internal.h"
#include <Memory.h>

/* mac/ovl_reloc.c — shared. */
unsigned long ovl_be32(const unsigned char *p);
unsigned short ovl_be16(const unsigned char *p);
void ovl_fixup(unsigned char *base, unsigned long size, long delta);
void ovl_flush_code(void);

#ifdef UNC_AT_BUDGET
/* The probe fields both lifetimes report on the completion alert. `wa` and
 * `kf` and `rf` belong to the eager release and stay 0 under `lazy`, which
 * has no release to get wrong; `fc`/`fn` are the flush route and its count,
 * and both lifetimes fill them. */
extern short gWantedAfterRelease, gKeepFail, gRelFmt;
extern short gFlushHas, gFlushCalls;
#define OVL_DIAG(stmt) do { stmt; } while (0)
#else
#define OVL_DIAG(stmt) ((void)0)
#endif

/* The loader, both lifetimes.
 *
 * ovl_image(id)            the image, loaded if it is not in memory yet, or
 *                          NULL — which every caller reports as a per-entry
 *                          UNC_ERR_MEM, like any other allocation failure.
 * ovl_image_q(id, 1)       the same, for the ONE caller allowed to find an
 *                          image gone: unc_crypt_free, which three format
 *                          readers call unconditionally at cleanup. Recording
 *                          that as `wa` made the alarm fire on every
 *                          unencrypted Compact Pro.
 * ovl_preload()            eager: read the bundle while the boot disk is
 *                          certainly in. lazy: nothing, by design — it reads
 *                          per format, later, and that IS the trade.
 * ovl_release_if_unwanted  eager: keep what the sniffed format can want and
 *                          give the rest back before the engine takes its
 *                          budget. lazy: nothing; it never took the memory.
 *
 * Both no-ops are real functions rather than #ifdefs at the call sites, so
 * mac/macextract_mac.c reads the same either way. */
OverlayEntry ovl_image(short id);
OverlayEntry ovl_image_q(short id, int expected);
void ovl_preload(void);
void ovl_release_if_unwanted(UncFormat fmt, UncIO *io);

/* The codec vector lives in the shim, which plants it; the eager release
 * invalidates it because the copy it keeps is at a different address. */
void ovl_codecs_invalidate(void);

#endif /* OVL_LOAD_H */

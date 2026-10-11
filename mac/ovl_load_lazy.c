/* ovl_load_lazy.c — one image per format, read when a format turns out to
 * want it, and kept for the rest of the run.
 *
 * The other lifetime is mac/ovl_load_eager.c, which is the shipped one; both
 * answer mac/ovl_load.h and the dispatch shims cannot tell which is linked.
 * This was the branch `selective-loading` until 2026-09-25.
 *
 * What it buys and what it costs, measured at 1 MB on System 6.0.8
 * (FORMATS.md, *Overlays*): 894 B-10.7 KB MORE budget than eager for a format
 * that must keep the ciphers, because nothing is ever copied and nothing is
 * held that this archive cannot want — against **one disk access per format,
 * after the archive has been chosen**. On a Mac Plus with one drive that is
 * the moment the application's own floppy may have been swapped out for the
 * archive's, which is the whole reason eager is the default.
 *
 * Each image is its own 'OVLY' resource here, numbered by the OVL_ID_* the
 * build passes (tools/overlay/ovlid.py); the eager build bundles the same
 * images into one resource instead. Nothing else about them differs — 21 of
 * the 24 files under tools/overlay/ were byte-identical between the two
 * branches this file and its sibling came from.
 */
#include "ovl_load.h"
#include <Resources.h>

/* Loaded images, by id. Sized from OVL_IMAGE_MAX so adding an image cannot
 * silently overflow it; the branch this came from kept a Handle and a `tried`
 * flag beside every CALL SITE instead, which meant two shims wanting the same
 * image each carried their own pair. */
static Handle gImage[OVL_IMAGE_MAX];
static short  gImageId[OVL_IMAGE_MAX];
static int    gImages;

/* Read at launch: nothing. That is this lifetime, not an omission — it reads
 * per format, later, and mac/macextract_mac.c calls this either way so the
 * shell reads the same in both builds. */
void ovl_preload(void)
{
}

/* Release after the sniff: nothing to release. The eager loader gives back
 * the images this archive cannot want; here they were never taken. */
void ovl_release_if_unwanted(UncFormat fmt, UncIO *io)
{
    (void)fmt; (void)io;
}

OverlayEntry ovl_image_q(short id, int expected)
{
    Handle h;
    int i;
    (void)expected;      /* nothing here is ever released, so no caller can
                          * find an image gone — `wa` cannot fire under this
                          * lifetime and the quiet form costs nothing. */
    for (i = 0; i < gImages; i++)
        if (gImageId[i] == id)
            return gImage[i] ? (OverlayEntry)(void *)*gImage[i] : NULL;
    if (gImages >= OVL_IMAGE_MAX) return NULL;   /* cannot happen; see above */

    h = GetResource('OVLY', id);
    if (h != NULL && *h != NULL) {
        HLock(h);
        /* AFTER HLock: the fixup writes the address the image will run at, so
         * the image must not move afterwards. Relocating by its own address,
         * which is what the eager loader's delta form reduces to when an
         * image runs where it was read. */
        ovl_fixup((unsigned char *)*h, (unsigned long)GetHandleSize(h),
                  (long)*h);
        /* Executable bytes were just written as data. Inside Macintosh:
         * Memory requires the flush here exactly as it does for the bundle
         * (*Stale Instructions*), and this lifetime went without one for as
         * long as it was a branch of its own — nothing on a 68000 could show
         * it, and no tier with a cache has ever run either lifetime. */
        ovl_flush_code();
    } else {
        h = NULL;
    }
    gImageId[gImages] = id;
    gImage[gImages++] = h;
    return h ? (OverlayEntry)(void *)*h : NULL;
}

OverlayEntry ovl_image(short id) { return ovl_image_q(id, 0); }

/* Nothing is ever given back, so any format can still be opened. */
int ovl_spent(void)
{
    return 0;
}

/* ovl_load_eager.c — all seventeen images as ONE resource, read at launch, and
 * most of it thrown away as soon as the archive says what it is.
 *
 * The lifetime this file implements is the shipped one. `mac/ovl_load_lazy.c`
 * is the other: one image per format, read when a format turns out to want
 * it. Both answer mac/ovl_load.h and nothing else; the dispatch shims in
 * mac/ovl_shim.c cannot tell which is linked.
 *
 * The trade, measured (FORMATS.md, *Overlays*): this one grants the engine
 * 84-103 KB more than a resident build and needs NO disk access after the
 * archive has been chosen, which on a Mac Plus with one drive is the moment
 * the application's floppy may be out. That is the images'; the dialogs'
 * layouts, which no image carries, are the resource file's preloads, which
 * stay in memory because the launch grows the heap without purging
 * (mac/macextract_mac.c, GrowApplZone). The lazy one grants 894 B-10.7 KB
 * more still, for a format that must keep the ciphers, and pays a disk
 * access per format instead.
 *
 * Bundle layout: tools/overlay/mkbundle.py. Two byte-wise big-endian reads
 * per field, no unaligned dereference, per the 68000 rules in CLAUDE.md.
 */
#include "ovl_load.h"
#include <Resources.h>
#include <Dialogs.h>

/* The whole thing until the release; after it, the same block detached
 * from the resource map and cut down to what was kept (ovl_pack). */
static Handle gBundle;
static int    gBundleTried;
static int    gPacked;          /* gBundle holds only what the release kept */
short         gDrop;            /* the envelope's own reader, for the layer
                                 * under it to give back */
int           gPeeked;          /* the format the peek named. These two are
                                 * not static: tests/ovlbox sets them, having
                                 * no peek */

/* An image's directory entry in the bundle: id, keep count, offset, length,
 * twelve bytes (tools/overlay/mkbundle.py, which writes the count as 0).
 * NULL if this bundle has no such id — before the release a build mismatch,
 * after it an image that was not kept. */
static unsigned char *ovl_entry(short id)
{
    unsigned char *e;
    unsigned short n;
    if (gBundle == NULL || *gBundle == NULL) return NULL;
    e = (unsigned char *)*gBundle;
    for (n = ovl_be16(e), e += 4; n != 0; n--, e += 12)
        if (ovl_be16(e) == (unsigned short)id) return e;
    return NULL;
}

static void ovl_put32(unsigned char *p, unsigned long v)
{
    p[0] = (unsigned char)(v >> 24);
    p[1] = (unsigned char)(v >> 16);
    p[2] = (unsigned char)(v >> 8);
    p[3] = (unsigned char)v;
}

/* Relocate every image where it sits IN THE BUNDLE, once, at load.
 *
 * Every image is executed where it sits in the bundle, so its relocations
 * have to be applied at its bundle address; ovl_pack applies them again,
 * by the difference, to an image it moves. Doing it here rather than per
 * image keeps the "exactly once" property that makes a fixup safe. */
static void ovl_bundle_fixup(void)
{
    const unsigned char *p;
    unsigned short n, i;
    if (gBundle == NULL || *gBundle == NULL) return;
    p = (const unsigned char *)*gBundle;
    n = ovl_be16(p);
    for (i = 0; i < n; i++) {
        const unsigned char *e = p + 4 + (unsigned long)i * 12;
        unsigned long off = ovl_be32(e + 4), len = ovl_be32(e + 8);
        ovl_fixup((unsigned char *)p + off, len, (long)(p + off));
    }
    ovl_flush_code();
}

/* Called from main() while the boot disk is certainly in. */
void ovl_preload(void)
{
    if (gBundleTried) return;
    gBundleTried = 1;
    gBundle = GetResource('OVLY', OVL_ID_BUNDLE);
    if (gBundle != NULL && *gBundle != NULL) {
        HLock(gBundle);
        ovl_bundle_fixup();
    } else {
        gBundle = NULL;
    }
}

/* Never reloads by itself. One disk read at launch is the whole of this
 * lifetime's argument, and a loader that quietly re-read the application's
 * resource fork mid-extraction would spend exactly what it exists to save —
 * on a Mac Plus with one drive, at the moment the archive's floppy is in.
 * The only re-reads are ovl_reload, BETWEEN archives, and only when the Finder
 * handed over more than one; and between two LAYERS, only when an envelope's
 * peek named a format the layer under it turned out not to be.
 *
 * That makes the release decision load-bearing rather than an optimisation:
 * an image released is gone for this archive. It is safe because nothing is
 * released without the archive's own directory saying so — see
 * mac/release_plan.inc.c, where anything short of a definite NO keeps the
 * ciphers. */
OverlayEntry ovl_image_q(short id, int expected)
{
    const unsigned char *e = ovl_entry(id);
    if (e == NULL) {
        OVL_DIAG(if (!expected && (gPacked || gBundle == NULL))
                     gWantedAfterRelease = id);
        (void)expected;
        return NULL;
    }
    return (OverlayEntry)(void *)(*gBundle + ovl_be32(e + 4));
}

OverlayEntry ovl_image(short id) { return ovl_image_q(id, 0); }

/* Keep what this format can want; release the rest. Called after the sniff.
 *
 * The keep set is the decoder for the format — for zip, two images, the
 * reader and Shrink/Reduce — the ciphers where an entry might be encrypted,
 * and always the codecs; the plan below lists it (mac/release_plan.inc.c).
 *
 * A keep is a count in the image's directory entry: one image can be kept
 * twice, an LZ4 frame's and the MAR's in it, and given back once. */
static void ovl_keep(short id)
{
    unsigned char *e = ovl_entry(id);
    if (e == NULL) { OVL_DIAG(gKeepFail = 1); return; }
    e[3]++;
}

static void ovl_drop(short id)
{
    unsigned char *e = ovl_entry(id);
    if (e != NULL && e[3] != 0) e[3]--;
}

/* What was kept goes to the start of the bundle's own block, the directory
 * first and then the images, and the rest of the block is given back. In
 * place, so it needs no room and cannot fail: until 2026-11-11 each kept
 * image was COPIED to a block of its own high in the heap while the bundle
 * was still locked below them, and on a 512Ke under System 6.0.8 a tar
 * envelope's four copies needed 79,814 B where 70,006 B were free
 * (DECISIONS.md 2026-11-11, *the copies that moved down*). The bundle is the
 * lowest block the application allocates (ovl_preload at launch; ovl_reload
 * reserves its place), so what stays is at the bottom of the heap and what
 * is cut off joins the free space above it in one piece.
 *
 * Run again for the layer under an envelope, once it has given back the
 * envelope's reader and the sniffer. The directory is in offset order
 * (mkbundle.py) and stays so; each entry and each image is moved to the end
 * of the last, so a destination is never above its source nor over anything
 * not yet moved, and BlockMove copies an overlapping range correctly
 * (Inside Macintosh II, The Memory Manager). An image that moves is
 * relocated AGAIN, by the difference: the fixup is relative to wherever it
 * sat. */
static void ovl_pack(void)
{
    unsigned char *b = (unsigned char *)*gBundle, *e, *w, *src, *dst;
    unsigned short n = ovl_be16(b), k = 0;
    unsigned long len;
    for (e = w = b + 4; n != 0; n--, e += 12)
        if (e[3] != 0) {
            BlockMoveData(e, w, 12);
            w += 12;
            k++;
        }
    b[0] = (unsigned char)(k >> 8);
    b[1] = (unsigned char)k;
    for (e = b + 4, dst = w; e < w; e += 12) {
        src = b + ovl_be32(e + 4);
        len = ovl_be32(e + 8);
        BlockMoveData(src, dst, (Size)len);
        ovl_fixup(dst, len, (long)dst - (long)src);
        ovl_put32(e + 4, (unsigned long)(dst - b));
        dst += (len + 3) & ~3UL;          /* aligned as mkbundle.py aligns */
    }
    ovl_flush_code();
    SetHandleSize(gBundle, (Size)(dst - b));
    /* The codecs may have moved: the vector is re-patched to wherever they
     * are now by its next caller. */
    ovl_codecs_invalidate();
}

/* What to keep is decided in the bundle, by the set's setup image, while
 * the bundle is whole (mac/release_plan.inc.c, which says what each format
 * keeps and why): this file keeps what the plan lists. The host lane has no
 * such image and compiles the plan natively instead (tests/ovlbox), so it is
 * reached through OVL_PLAN, as the ROM test once was through a
 * macro of its own. No image is no plan, and no plan keeps the whole
 * bundle, which costs memory and loses nothing. */
#ifndef OVL_PLAN
static int ovl_plan(UncFormat fmt, UncIO *io, unsigned char *out)
{
    OverlayEntry e = ovl_image(OVL_ID_SEGSETUP);
    OvlArgs g;
    if (!e) return 0;
    g.obj = (void *)ovl_image(OVL_ID_SNIFF);
    g.in = io;
    g.len = (uint32_t)fmt;
    return (int)e(&gOvlHost, OVL_RELEASE_PLAN, &g, out);
}
#define OVL_PLAN ovl_plan
#else
int OVL_PLAN(UncFormat fmt, UncIO *io, unsigned char *out);
#endif

/* Runs immediately after the sniff and therefore BEFORE the engine's first
 * allocation, which is where the budget is taken. So what it frees is heap
 * the engine is simply measured against a moment later — there is nothing to
 * credit back, and no ordering to get wrong. */
void ovl_release_if_unwanted(UncFormat fmt, UncIO *io)
{
    unsigned char plan[8];
    int n;

    if (gBundle == NULL || gPacked) {
        /* The layer under an envelope that was peeked into: its own sniff
         * has run, so the envelope's reader and the sniffer go back, and it
         * keeps what it would have kept had it been opened on its own. */
        if (!gPeeked) return;
        ovl_drop(gDrop);
        ovl_drop(OVL_ID_SNIFF);
        /* Unless the whole file is not what its head said: a probe ahead
         * of the peek's answer that reads past 512 bytes — a zip found by
         * its end record behind a tar header — claims it, and its decoder
         * went with the bundle. Read the bundle again, as between two
         * archives, and release for what this layer is (DECISIONS.md
         * 2026-11-05, *the head that was not the file*). */
        if (gPeeked == (int)fmt) { gPeeked = 0; ovl_pack(); return; }
        /* A head that named nothing kept the readers of the two formats
         * only an end can name, and the ciphers (mac/release_plan.inc.c,
         * gUnnamed); any other layer is read as a wrong peek is. */
        if (gPeeked == OVL_PEEK_UNNAMED &&
            (fmt == UNC_FORMAT_COMPACTPRO || fmt == UNC_FORMAT_CPTSEG ||
             fmt == UNC_FORMAT_DISKDOUBLER || fmt == UNC_FORMAT_SUPERDISK)) {
            gPeeked = 0;
            ovl_pack();
            return;
        }
        if (!ovl_reload()) { StopAlert(135, NULL); return; }  /* kNoReloadALRT */
    }

    n = OVL_PLAN(fmt, io, plan);
    if (n <= 0) return;
    OVL_DIAG(gRelFmt = (short)fmt);
    gPeeked = plan[0];
    gDrop = (short)(OVL_ID_CRYPT + plan[1]);
    do ovl_keep((short)(OVL_ID_CRYPT + plan[1 + n])); while (--n);

    /* Out of the resource map, so that a later GetResource reads the bundle
     * afresh rather than handing back this block. Still locked. */
    DetachResource(gBundle);
    gPacked = 1;
    ovl_pack();
}

/* The one disk read after launch this lifetime makes, and only when the
 * Finder handed over several archives at once: the release gave back what
 * the next one may need (DECISIONS.md 2026-10-12, *the reload that the
 * list needs*). The copies kept for the last archive go first, so that the
 * bundle is read into as much of the heap as there is. */
int ovl_reload(void)
{
    if (gBundle != NULL) DisposeHandle(gBundle);  /* what the release kept */
    gBundle = NULL;
    gPacked = 0;
    gPeeked = 0;
    ovl_codecs_invalidate();
    /* Only called once ovl_spent() says the bundle was released. */
    {
        /* LOW in the heap, as at launch. Left to itself the Memory Manager
         * put the bundle in the MIDDLE — at 239,626 of a 512Ke's heap,
         * above what the last archive left — the copies the release keeps
         * were moved high only as far as just under it, and its release
         * then left them an island: the largest free block fell from
         * 317,692 B to 175,478 B (DECISIONS.md 2026-10-12). ResrvMem makes
         * room for a block at the lowest place it can (ReserveMem, trap A040,
         * the classic ResrvMem; the size by A9A5, SizeRsrc), which is what a
         * block about to be locked wants. The size needs the handle and
         * not its data, so the handle is fetched empty first. */
        Handle h;
        SetResLoad(false);
        h = GetResource('OVLY', OVL_ID_BUNDLE);
        SetResLoad(true);
        if (h != NULL) ReserveMem(GetResourceSizeOnDisk(h));
        gBundleTried = 0;
        ovl_preload();
    }
    return gBundle != NULL;
}

/* Released is packed. A bundle that never loaded reads as spent too, and
 * that is right — with no images, no format can be opened a second time
 * either. */
int ovl_spent(void)
{
    return gPacked || (gBundleTried && gBundle == NULL);
}

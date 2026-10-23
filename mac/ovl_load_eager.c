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
 * the application's floppy may be out. The lazy one grants 894 B-10.7 KB
 * more still, for a format that must keep the ciphers, and pays a disk
 * access per format instead.
 *
 * Bundle layout: tools/overlay/mkbundle.py. Two byte-wise big-endian reads
 * per field, no unaligned dereference, per the 68000 rules in CLAUDE.md.
 */
#include "ovl_load.h"
#include <Resources.h>

static Handle gBundle;          /* the whole thing, until the release */
static int    gBundleTried;
static Handle gKept[4];         /* the images we copied out, locked */
static short  gKeptId[4];

/* Find an image inside the bundle. Returns NULL if this bundle has no such
 * id, which is a build mismatch rather than a run-time condition. */
static const unsigned char *ovl_find(Handle h, short id, unsigned long *len)
{
    const unsigned char *p;
    unsigned short n, i;
    if (h == NULL || *h == NULL) return NULL;
    p = (const unsigned char *)*h;
    n = ovl_be16(p);
    for (i = 0; i < n; i++) {
        const unsigned char *e = p + 4 + (unsigned long)i * 12;
        if (ovl_be16(e) == (unsigned short)id) {
            *len = ovl_be32(e + 8);
            return p + ovl_be32(e + 4);
        }
    }
    return NULL;
}

/* Relocate every image where it sits IN THE BUNDLE, once, at load.
 *
 * An image is executed in place unless it is copied out, so its relocations
 * have to be applied at its bundle address; ovl_keep applies them again to
 * the copy, at the copy's address. Doing it here rather than per image keeps
 * the "exactly once" property that makes a fixup safe. */
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
 * The only re-read is ovl_reload, BETWEEN archives, and only when the Finder
 * handed over more than one.
 *
 * That makes the release decision load-bearing rather than an optimisation:
 * an image released is gone for this archive. It is safe because nothing is
 * released without the archive's own directory saying so — see
 * ovl_release_if_unwanted, where anything short of a definite NO keeps the
 * ciphers. */
OverlayEntry ovl_image_q(short id, int expected)
{
    const unsigned char *p;
    unsigned long len;
    int i;
    for (i = 0; i < 4; i++)
        if (gKept[i] != NULL && gKeptId[i] == id)
            return (OverlayEntry)(void *)*gKept[i];
    if (gBundle == NULL) {
        if (!expected) OVL_DIAG(gWantedAfterRelease = id);
        return NULL;
    }
    p = ovl_find(gBundle, id, &len);
    return p ? (OverlayEntry)(void *)p : NULL;
}

OverlayEntry ovl_image(short id) { return ovl_image_q(id, 0); }

/* Keep what this format can want; release the rest. Called after the sniff.
 *
 * The keep set is the decoder for the format — for zip, two images, the
 * reader and Shrink/Reduce — the ciphers where an entry might be encrypted,
 * and always the codecs, below. Encryption is discovered per ENTRY, as
 * the entry is read, so a format that can carry one has to keep the ciphers
 * whatever this archive turns out to hold — the eligibility rule the mechanism
 * has always had, applied to a bundle rather than to one blob. */
static void ovl_keep(short id, int slot)
{
    unsigned long len;
    const unsigned char *p = ovl_find(gBundle, id, &len);
    Handle h;
    if (p == NULL || len == 0) { OVL_DIAG(gKeepFail = 1); return; }
    h = NewHandle((Size)len);
    if (h == NULL || *h == NULL) { OVL_DIAG(gKeepFail = 2); return; }
    /* MoveHHi before the lock. These copies are locked for the rest of the
     * run, and a locked block in the middle of the heap splits it. Measured
     * on a Macintosh 512Ke: with the copies left where NewHandle put them,
     * `derived-a2basic.dmg.sit` was granted 317,838 B and still failed —
     * `gRefusedWhy` = 2, NewPtr returning NULL for a 205 KB block against a
     * largest free block of 169,298 B. The memory was there, in two pieces. */
    MoveHHi(h);
    HLock(h);
    BlockMoveData(p, *h, (Size)len);
    /* Relocated AGAIN, for the address the copy runs at: the fixup is
     * relative to wherever the image sits, and this one has moved. */
    ovl_fixup((unsigned char *)*h, (unsigned long)len,
              (long)*h - (long)p);   /* by the DIFFERENCE: p was relocated
                                      * for its place in the bundle */
    ovl_flush_code();
    gKept[slot] = h;
    gKeptId[slot] = id;
}

/* What each format keeps (DECISIONS.md 2026-10-23, *the shims that were
 * one function*): the format, then its decoder's image as an offset from 128
 * with KEEP_CRYPT set if an entry might be encrypted. That second column is
 * the eligibility rule the mechanism has always had: a format that MAY carry
 * an encrypted entry keeps the ciphers, because encryption is discovered per
 * entry and the release must decide before it knows. Two bytes a format, in
 * place of a `switch` that was 354 B of code with the rest of this function.
 *
 * A format that is NOT here keeps the whole bundle, which costs memory and
 * loses nothing. That is every ENVELOPE — BinHex, MacBinary, AppleSingle and
 * AppleDouble, gzip, .Z, MIME, uu, btoa, base64 — because what is under one
 * is unknown until it has been unwrapped; the segment schemes that join to a
 * FILE (StuffIt's, DiskDoubler's, plain NAME.001, MIME's partial) for the
 * same reason; Private File, whose reader is in the StuffIt image and its key
 * setup in the ciphers', and which always decrypts to a StuffIt archive
 * unwrapped next; and any format nobody has added here yet, which is the
 * answer that cannot be wrong. */
#define KEEP_CRYPT 0x80
#define KEEP(id, crypt) ((unsigned char)(((id) - OVL_ID_CRYPT) | (crypt)))
static const unsigned char gKeepSet[][2] = {
    { UNC_FORMAT_SPACESAVER,  KEEP(OVL_ID_SPACESAVER, 0) },
    { UNC_FORMAT_COMPACTPRO,  KEEP(OVL_ID_CPTDD,      KEEP_CRYPT) },
    { UNC_FORMAT_DISKDOUBLER, KEEP(OVL_ID_CPTDD,      0) },
    { UNC_FORMAT_LZH,         KEEP(OVL_ID_LZH,        0) },
    { UNC_FORMAT_ARC,         KEEP(OVL_ID_ARC,        KEEP_CRYPT) },
    { UNC_FORMAT_NOWCOMPRESS, KEEP(OVL_ID_NOW,        0) },
    { UNC_FORMAT_SUPERDISK,   KEEP(OVL_ID_SUPERDISK,  0) },
    { UNC_FORMAT_PACKIT,      KEEP(OVL_ID_PACKIT,     KEEP_CRYPT) },
    /* An AppleLink package cannot be encrypted: the format has no password
     * anywhere in it, and its own expander never asks for one. */
    { UNC_FORMAT_SQP,         KEEP(OVL_ID_SQP,        0) },
    { UNC_FORMAT_SIT,         KEEP(OVL_ID_STUFFIT,    KEEP_CRYPT) },
    { UNC_FORMAT_SIT5,        KEEP(OVL_ID_STUFFIT,    KEEP_CRYPT) },
    { UNC_FORMAT_ZIP,         KEEP(OVL_ID_EXO,        KEEP_CRYPT) },
    { UNC_FORMAT_TAR,         KEEP(OVL_ID_ZIPOLD,     0) },
    /* Segment SCHEMES, from the other release site: a Compact Pro or spanned
     * zip set is read by that format's own reader over the joined parts. */
    { UNC_FORMAT_CPTSEG,      KEEP(OVL_ID_CPTDD,      KEEP_CRYPT) },
    { UNC_FORMAT_ZIPSEG,      KEEP(OVL_ID_EXO,        KEEP_CRYPT) },
};

/* Runs immediately after the sniff and therefore BEFORE the engine's first
 * allocation, which is where the budget is taken. So what it frees is heap
 * the engine is simply measured against a moment later — there is nothing to
 * credit back, and no ordering to get wrong. */
void ovl_release_if_unwanted(UncFormat fmt, UncIO *io)
{
    short want;
    int crypt;
    unsigned i;

    if (gBundle == NULL) return;

    /* The sniffer's image (OVL_ID_SNIFF) is in no keep set, on purpose: it
     * has answered by the time this runs, and every later sniff — a layer
     * under an envelope, the next archive after the reload — finds the
     * bundle whole (DECISIONS.md 2026-10-21, *the probes that left with the
     * bundle*). */
    for (i = 0; i < sizeof gKeepSet / sizeof gKeepSet[0]; i++)
        if (gKeepSet[i][0] == (unsigned char)fmt) break;
    if (i == sizeof gKeepSet / sizeof gKeepSet[0]) return;
    want = (short)(OVL_ID_CRYPT + (gKeepSet[i][1] & 0x1f));
    crypt = gKeepSet[i][1] & KEEP_CRYPT;

    /* Compact Pro and zip keep a per-entry encryption flag in a directory
     * that can be walked before anything is decoded, so for those two the
     * ciphers are kept only when an entry actually needs them
     * (unc_archive_encrypted). Anything else — a format that flags encryption
     * per entry with no directory (StuffIt, StuffIt 5, PackIt), one that does
     * not flag it at all (ARC), or a directory that would not read — answers
     * UNKNOWN, and UNKNOWN is treated as YES.
     *
     * This is the only place the answer may be acted on: there is no reload,
     * so releasing the ciphers on a maybe would lose an entry rather than
     * cost a disk access. */
    if (crypt && (fmt == UNC_FORMAT_COMPACTPRO || fmt == UNC_FORMAT_ZIP) &&
        unc_archive_encrypted(fmt, io) == UNC_ENC_NO)
        crypt = 0;

    OVL_DIAG(gRelFmt = (short)fmt);
    ovl_keep(want, 0);
    /* Zip, and a spanned zip, also keep Shrink and Reduce, which nothing
     * else calls. */
    if (fmt == UNC_FORMAT_ZIP || fmt == UNC_FORMAT_ZIPSEG)
        ovl_keep(OVL_ID_ZIPOLD, 3);
    if (crypt) ovl_keep(OVL_ID_CRYPT, 1);
    /* And ALWAYS the codecs, because every decoder calls into them: the bit
     * reader, the Huffman and canonical coders, LZW and LZAH live there and
     * are reached through pointers in the host vector. Releasing the bundle
     * without keeping this image left those pointers aimed at memory that had
     * been given back — which is not a wrong answer but no answer at all:
     * every decoder stub failed at ovl_codecs_ready() and the archive
     * produced nothing. */
    ovl_keep(OVL_ID_CODECS, 2);
    /* The vector must be re-patched to the COPY's address, so make the next
     * caller do it. */
    ovl_codecs_invalidate();

    HUnlock(gBundle);
    ReleaseResource(gBundle);
    gBundle = NULL;

}

/* The one disk read after launch this lifetime makes, and only when the
 * Finder handed over several archives at once: the release gave back what
 * the next one may need (DECISIONS.md 2026-10-12, *the reload that the
 * list needs*). The copies kept for the last archive go first, so that the
 * bundle is read into as much of the heap as there is. */
int ovl_reload(void)
{
    int i;
    for (i = 0; i < 4; i++) {
        if (gKept[i] != NULL) {
            DisposeHandle(gKept[i]);       /* locked is fine to dispose */
            gKept[i] = NULL;
        }
    }
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

/* Tried and gone is released: nothing else sets gBundle back to NULL.
 * A bundle that never loaded reads as spent too, and that is right — with
 * no images, no format can be opened a second time either. */
int ovl_spent(void)
{
    return gBundleTried && gBundle == NULL;
}

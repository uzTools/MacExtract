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
 * ovl_release_if_unwanted, where anything short of a definite NO keeps the
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
 * and always the codecs, below. Encryption is discovered per ENTRY, as
 * the entry is read, so a format that can carry one has to keep the ciphers
 * whatever this archive turns out to hold — the eligibility rule the mechanism
 * has always had, applied to a bundle rather than to one blob.
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

/* What each format keeps (DECISIONS.md 2026-10-23, *the shims that were
 * one function*): the format, then its decoder's image as an offset from 128
 * with KEEP_CRYPT set if an entry might be encrypted. That second column is
 * the eligibility rule the mechanism has always had: a format that MAY carry
 * an encrypted entry keeps the ciphers, because encryption is discovered per
 * entry and the release must decide before it knows. Two bytes a format, in
 * place of a `switch` that was 354 B of code with the rest of this function.
 *
 * An ENVELOPE, KEEP_PEEK, keeps its own reader and what the format under it
 * keeps, when the first bytes of its payload say what that is
 * (unc_envelope_peek; DECISIONS.md 2026-11-03, *the envelope that said what
 * it held*); when they do not, or say another envelope, it keeps the whole
 * bundle, as every envelope did before.
 *
 * A format that is NOT here keeps the whole bundle, which costs memory and
 * loses nothing: MIME, whose parts can be anything; the segment schemes
 * that join to a FILE (StuffIt's, DiskDoubler's, plain NAME.001, MIME's
 * partial), because what they join is unknown until it is joined; Private
 * File, whose reader is in the StuffIt image and its key setup in the
 * ciphers', and which always decrypts to a StuffIt archive unwrapped next;
 * and any format nobody has added here yet, which is the answer that cannot
 * be wrong. */
#define KEEP_CRYPT 0x80
#define KEEP_PEEK  0x40
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
    /* No password anywhere in the format. */
    { UNC_FORMAT_MAR,         KEEP(OVL_ID_ZIPOLD,     0) },
    { UNC_FORMAT_TOME,        KEEP(OVL_ID_ZIPOLD,     0) },
    /* Segment SCHEMES, from the other release site: a Compact Pro or spanned
     * zip set is read by that format's own reader over the joined parts. */
    { UNC_FORMAT_CPTSEG,      KEEP(OVL_ID_CPTDD,      KEEP_CRYPT) },
    { UNC_FORMAT_ZIPSEG,      KEEP(OVL_ID_EXO,        KEEP_CRYPT) },
    /* An Apple Backup set: its reader and its match, no password. */
    { UNC_FORMAT_ABK,         KEEP(OVL_ID_ZIPOLD,     0) },
    /* Envelopes, by the image their reader is in. */
    { UNC_FORMAT_BINHEX,      KEEP(OVL_ID_BINHEX,     KEEP_PEEK) },
    { UNC_FORMAT_BINHEX_OLD,  KEEP(OVL_ID_BINHEX,     KEEP_PEEK) },
    { UNC_FORMAT_DL,          KEEP(OVL_ID_BINHEX,     KEEP_PEEK) },
    { UNC_FORMAT_MACBINARY,   KEEP(OVL_ID_BINHEX,     KEEP_PEEK) },
    { UNC_FORMAT_APPLESINGLE, KEEP(OVL_ID_BINHEX,     KEEP_PEEK) },
    { UNC_FORMAT_APPLEDOUBLE, KEEP(OVL_ID_BINHEX,     KEEP_PEEK) },
    { UNC_FORMAT_GZIP,        KEEP(OVL_ID_EXO,        KEEP_PEEK) },
    { UNC_FORMAT_COMPRESS_Z,  KEEP(OVL_ID_EXO,        KEEP_PEEK) },
    { UNC_FORMAT_LZ4,         KEEP(OVL_ID_ZIPOLD,     KEEP_PEEK) },
    { UNC_FORMAT_UU,          KEEP(OVL_ID_TEXT,       KEEP_PEEK) },
    { UNC_FORMAT_BASE64,      KEEP(OVL_ID_TEXT,       KEEP_PEEK) },
    { UNC_FORMAT_BTOA,        KEEP(OVL_ID_BTOA,       KEEP_PEEK) },
};

/* The peek's own allocator: plain NewPtr and DisposePtr, outside the
 * engine's budget, which is not taken until after the release. */
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

static int keep_row(UncFormat fmt)
{
    unsigned i;
    for (i = 0; i < sizeof gKeepSet / sizeof gKeepSet[0]; i++)
        if (gKeepSet[i][0] == (unsigned char)fmt) return (int)i;
    return -1;
}

/* Runs immediately after the sniff and therefore BEFORE the engine's first
 * allocation, which is where the budget is taken. So what it frees is heap
 * the engine is simply measured against a moment later — there is nothing to
 * credit back, and no ordering to get wrong. */
void ovl_release_if_unwanted(UncFormat fmt, UncIO *io)
{
    short want, inner = 0;
    int crypt, row, enc = UNC_ENC_UNKNOWN;
    UncFormat as = fmt;     /* whose rules the ciphers and zipold follow */

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
        if (!ovl_reload()) { StopAlert(135, NULL); return; }  /* kNoReloadALRT */
    }

    /* The sniffer's image (OVL_ID_SNIFF) is in no keep set, on purpose: it
     * has answered by the time this runs, and every later sniff — the next
     * archive after the reload — finds the bundle whole (DECISIONS.md
     * 2026-10-21, *the probes that left with the bundle*). An envelope that
     * was peeked into keeps it for the layer under it, which is sniffed
     * after this. */
    row = keep_row(fmt);
    if (row < 0) return;
    want = (short)(OVL_ID_CRYPT + (gKeepSet[row][1] & 0x1f));
    if (gKeepSet[row][1] & KEEP_PEEK) {
        UncAlloc pal;
        pal.ctx = NULL;
        pal.alloc = peek_alloc;
        pal.free = peek_free;
        as = unc_envelope_peek(io, &pal, &enc);
        row = keep_row(as);
        if (row < 0 || (gKeepSet[row][1] & KEEP_PEEK)) return;
        inner = (short)(OVL_ID_CRYPT + (gKeepSet[row][1] & 0x1f));
        /* One image can serve both: an LZ4 frame and the MAR in it are
         * both `ovl_zipold`'s, kept twice and given back once. Kept once
         * and given back with the frame, the MAR layer ran with its image
         * gone, "Archive damaged." (measured 2026-11-03; DECISIONS.md, *the
         * frame mar 0.2.0 reads*). */
    }
    crypt = gKeepSet[row][1] & KEEP_CRYPT;

    /* Compact Pro and zip keep a per-entry encryption flag in a directory
     * that can be walked before anything is decoded, and StuffIt 5's header
     * says whether its reader can decrypt anything at all, so for those
     * three the ciphers are kept only when an entry can need them
     * (unc_archive_encrypted; under an envelope, the peek's answer over the
     * first bytes, which only StuffIt 5's header can give). Anything else —
     * a format that flags encryption per entry with no directory (StuffIt,
     * PackIt), one that does not flag it at all (ARC), or a header or
     * directory that would not read — answers UNKNOWN, and UNKNOWN is
     * treated as YES.
     *
     * This is the only place the answer may be acted on: there is no reload,
     * so releasing the ciphers on a maybe would lose an entry rather than
     * cost a disk access. */
    if (crypt && (as == UNC_FORMAT_COMPACTPRO || as == UNC_FORMAT_ZIP ||
                  as == UNC_FORMAT_SIT5) &&
        (as != fmt ? enc : unc_archive_encrypted(as, io)) == UNC_ENC_NO)
        crypt = 0;

    OVL_DIAG(gRelFmt = (short)fmt);
    ovl_keep(want);
    if (as != fmt) {
        gDrop = want;
        ovl_keep(inner);
        ovl_keep(OVL_ID_SNIFF);
        gPeeked = (int)as;
    }
    /* Zip, and a spanned zip, also keep Shrink and Reduce, which nothing
     * else calls. */
    if (as == UNC_FORMAT_ZIP || as == UNC_FORMAT_ZIPSEG)
        ovl_keep(OVL_ID_ZIPOLD);
    if (crypt) ovl_keep(OVL_ID_CRYPT);
    /* And ALWAYS the codecs, because every decoder calls into them: the bit
     * reader, the Huffman and canonical coders, LZW and LZAH live there and
     * are reached through pointers in the host vector. Releasing the bundle
     * without keeping this image left those pointers aimed at memory that had
     * been given back — which is not a wrong answer but no answer at all:
     * every decoder stub failed at ovl_codecs_ready() and the archive
     * produced nothing. */
    ovl_keep(OVL_ID_CODECS);

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

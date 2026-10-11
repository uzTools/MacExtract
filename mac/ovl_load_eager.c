/* ovl_load_eager.c — all sixteen images as ONE resource, read at launch, and
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

/* NEVER reloads. One disk read at launch is the whole of this lifetime's
 * argument, and a loader that quietly re-read the application's resource fork
 * mid-extraction would spend exactly what it exists to save — on a Mac Plus
 * with one drive, at the moment the archive's floppy is in.
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

/* Runs immediately after the sniff and therefore BEFORE the engine's first
 * allocation, which is where the budget is taken. So what it frees is heap
 * the engine is simply measured against a moment later — there is nothing to
 * credit back, and no ordering to get wrong. */
void ovl_release_if_unwanted(UncFormat fmt, UncIO *io)
{
    short want = 0;
    int crypt = 1;

    if (gBundle == NULL) return;

    switch (fmt) {
    /* Decoder, and whether an entry might be encrypted. The second column is
     * the eligibility rule the mechanism has always had: a format that MAY
     * carry an encrypted entry keeps the ciphers, because encryption is
     * discovered per entry and the release must decide before it knows. */
    case UNC_FORMAT_SPACESAVER:  want = OVL_ID_SPACESAVER; crypt = 0; break;
    case UNC_FORMAT_COMPACTPRO:  want = OVL_ID_CPTDD;      break;
    case UNC_FORMAT_DISKDOUBLER: want = OVL_ID_CPTDD;      crypt = 0; break;
    case UNC_FORMAT_LZH:         want = OVL_ID_LZH;        crypt = 0; break;
    case UNC_FORMAT_ARC:         want = OVL_ID_ARC;        break;
    case UNC_FORMAT_NOWCOMPRESS: want = OVL_ID_NOW;        crypt = 0; break;
    case UNC_FORMAT_SUPERDISK:   want = OVL_ID_SUPERDISK;  crypt = 0; break;
    case UNC_FORMAT_PACKIT:      want = OVL_ID_PACKIT;     break;
    /* An AppleLink package cannot be encrypted: the format has no password
     * anywhere in it, and its own expander never asks for one. */
    case UNC_FORMAT_SQP:         want = OVL_ID_SQP;        crypt = 0; break;
    case UNC_FORMAT_SIT:         case UNC_FORMAT_SIT5:
        want = OVL_ID_STUFFIT;   break;
    case UNC_FORMAT_ZIP:         want = OVL_ID_EXO;        break;
    case UNC_FORMAT_TAR:         want = OVL_ID_EXO;        crypt = 0; break;
    /* Segment SCHEMES, from the other release site: a Compact Pro or spanned
     * zip set is read by that format's own reader over the joined parts. */
    case UNC_FORMAT_CPTSEG:      want = OVL_ID_CPTDD;      break;
    case UNC_FORMAT_ZIPSEG:      want = OVL_ID_EXO;        break;
    /* An ENVELOPE does not yet know what is under it, and the schemes that
     * join to a FILE do not either. Both keep the whole bundle, which costs
     * memory and loses nothing. */
    /* BinHex has its own image now, but it is still an ENVELOPE: what is
     * under a .hqx is unknown until it has been unwrapped, so this lifetime
     * keeps the whole bundle for it exactly as before. The split buys the
     * LAZY lifetime a smaller load; here it buys nothing, and pretending
     * otherwise would strand the archive inside. */
    case UNC_FORMAT_BINHEX:      case UNC_FORMAT_MACBINARY:
    case UNC_FORMAT_APPLESINGLE: case UNC_FORMAT_APPLEDOUBLE:
    case UNC_FORMAT_GZIP:        case UNC_FORMAT_COMPRESS_Z:
    case UNC_FORMAT_MIME:        case UNC_FORMAT_UU:
    case UNC_FORMAT_BTOA:        case UNC_FORMAT_BASE64:
    case UNC_FORMAT_SITSEG:      case UNC_FORMAT_DDSEG:
    case UNC_FORMAT_SPLIT:       case UNC_FORMAT_MIMESEG:
    /* Private File too: its reader is in the StuffIt image and its key
     * setup in the ciphers', and what it decrypts is a StuffIt archive,
     * unwrapped next — so nothing in the bundle can be released yet. */
    case UNC_FORMAT_PRIVATEFILE:
        return;
    default:
        /* A format with no overlay of its own — or one this table has not
         * been taught. Keeping the whole bundle is the answer that cannot be
         * wrong, and it is what a new format gets until someone adds it. */
        return;
    }

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
    if (want) ovl_keep(want, 0);
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

/* Tried and gone is released: nothing else sets gBundle back to NULL.
 * A bundle that never loaded reads as spent too, and that is right — with
 * no images, no format can be opened a second time either. */
int ovl_spent(void)
{
    return gBundleTried && gBundle == NULL;
}

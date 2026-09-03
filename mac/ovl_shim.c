/* ovl_shim.c — what the engine links against when the ciphers are an overlay.
 *
 * Each function here has the signature `src/unc_crypt.c` would have provided,
 * loads the 'OVLY' resource on first use, and dispatches into it. The engine
 * is unchanged and does not know the difference; the point is that 15 KB of
 * cipher code and tables is not resident until an archive turns out to be
 * encrypted, and code is the only thing that costs the engine budget on a
 * Macintosh (FORMATS.md, *What the application costs the engine*).
 *
 * The handle is locked once and kept: unc_crypt_apply is called once per
 * buffer refill, and reloading a resource per call would be absurd. It is
 * never released — an application that has decrypted once will decrypt again,
 * and 15 KB is not worth the risk of a dangling entry pointer.
 *
 * FAILURE TO LOAD is handled, not ignored. Where the signature allows it the
 * shim returns UNC_ERR_MEM; where it does not, it clears the cipher kind so
 * the entry decodes undecrypted and fails its CRC — a per-entry error, which
 * is what this engine does with every other allocation failure. What it must
 * never do is silently return with the cipher half-initialised.
 */
#include "overlay.h"
#include "ovl_host_gen.h"
#include "ovl_host_init_gen.h"
#include "unc_internal.h"
#include <Resources.h>
#include <Memory.h>

static uint32_t ovl_host_crc32(uint32_t crc, const uint8_t *p, uint32_t n)
{
    return unc_crc32(crc, p, (int32_t)n);
}

static OverlayHostFns gOvlFns = OVL_HOST_FNS_INIT;

static const OverlayHost gOvlHost = { ovl_host_crc32, NULL, NULL, NULL,
                                      (const struct OverlayHostFns *)&gOvlFns };

/* ONE resource, read ONCE, at launch — and then most of it thrown away.
 *
 * `selective-loading` keeps one 'OVLY' per format and reads whichever the
 * archive turns out to need, which is a disk access after the archive has
 * been chosen; on a Mac Plus with one drive the application's floppy may have
 * been swapped by then. This branch reads a single bundle of all six images
 * while the boot disk is certainly in (ovl_preload, from main), and then
 * ovl_keep_for() copies out the one or two images the sniffed format can
 * actually want and releases the bundle. What the archive cannot want is gone
 * before the engine takes its budget — which is the whole trade: 74 KB
 * resident for a moment at launch, so that the decoder has room later.
 *
 * Bundle layout: tools/overlay/mkbundle.py. Two byte-wise big-endian reads
 * per field, no unaligned dereference, per the 68000 rules in CLAUDE.md. */
static Handle gBundle;          /* the whole thing, until ovl_keep_for */
static int    gBundleTried;
#ifdef UNC_AT_BUDGET
/* Diagnostics, in the probe build only, and worth keeping: they are what
 * found the preload that was called from one main() and not the other. `wa`
 * is an image wanted AFTER the release — which must never happen, since
 * there is no reload — `kf` says why a keep failed, and `rf` is the format
 * the release decided on. Printed on the completion alert. */
short gWantedAfterRelease, gKeepFail, gRelFmt;
#define OVL_DIAG(stmt) do { stmt; } while (0)
#else
#define OVL_DIAG(stmt) ((void)0)
#endif
static Handle gKept[3];         /* the images we copied out, locked */
static short  gKeptId[3];

static unsigned long ovl_be32(const unsigned char *p)
{
    return ((unsigned long)p[0] << 24) | ((unsigned long)p[1] << 16) |
           ((unsigned long)p[2] << 8) | (unsigned long)p[3];
}

static unsigned short ovl_be16(const unsigned char *p)
{
    return (unsigned short)(((unsigned short)p[0] << 8) | p[1]);
}

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


static void ovl_fixup(unsigned char *base, unsigned long size, long delta)
{
    unsigned long n, i, table;
    if (size < 4) return;
    n = ovl_be32(base + size - 4);
    if (n == 0) return;
    if (n > (size - 4) / 4) return;          /* not ours; leave it alone */
    table = size - 4 - n * 4;
    for (i = 0; i < n; i++) {
        unsigned long off = ovl_be32(base + table + i * 4);
        unsigned long v;
        if (off + 4 > table) continue;       /* outside the image proper */
        v = ovl_be32(base + off) + (unsigned long)delta;
        base[off]     = (unsigned char)(v >> 24);
        base[off + 1] = (unsigned char)(v >> 16);
        base[off + 2] = (unsigned char)(v >> 8);
        base[off + 3] = (unsigned char)v;
    }
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

/* NEVER reloads. One disk read at launch is the whole of this branch's
 * argument, and a shim that quietly re-read the application's resource fork
 * mid-extraction would spend exactly what the branch exists to save — on a
 * Mac Plus with one drive, at the moment the archive's floppy is in.
 *
 * That makes the release decision load-bearing rather than an optimisation:
 * an image released is gone for this archive. It is safe because nothing is
 * released without the archive's own directory saying so — see
 * ovl_release_if_unwanted, where anything short of a definite NO keeps the
 * ciphers. */
static OverlayEntry ovl_image(short id)
{
    const unsigned char *p;
    unsigned long len;
    int i;
    for (i = 0; i < 3; i++)
        if (gKept[i] != NULL && gKeptId[i] == id)
            return (OverlayEntry)(void *)*gKept[i];
    if (gBundle == NULL) { OVL_DIAG(gWantedAfterRelease = id); return NULL; }
    p = ovl_find(gBundle, id, &len);
    return p ? (OverlayEntry)(void *)p : NULL;
}

/* The ciphers, by their id in the bundle. Kept as a named function because
 * every cipher shim calls it and the name says which overlay is meant. */
/* Load the codec machinery and let it plant itself in the vector. Every
 * decoder shim calls this BEFORE dispatching, because a decoder that ran with
 * NULL codec pointers would not fail — it would jump to zero.
 *
 * Returns 0 if the overlay could not be had, and the caller then reports a
 * per-entry memory error, which is what this shell does with every other
 * allocation failure. */
static int gCodecsIn;   /* cleared when the bundle goes: the vector then
                         * points into memory that has been released */

static int ovl_codecs_ready(void)
{
    OverlayEntry e;
    if (gCodecsIn) return 1;
    /* From the bundle, like every other image on this branch — no separate
     * resource and no second disk read. */
    e = ovl_image(OVL_ID_CODECS);
    if (!e) return 0;
    e(&gOvlHost, OVL_CODEC_EXPORTS, &gOvlFns, NULL);
    gCodecsIn = 1;
    return 1;
}

static OverlayEntry ovl_entry(void)
{
    return ovl_image(OVL_ID_CRYPT);
}

/* Keep what this format can want; release the rest. Called after the sniff.
 *
 * The keep set is at most two: the decoder for the format, and the ciphers
 * where an entry might be encrypted. Encryption is discovered per ENTRY, as
 * the entry is read, so a format that can carry one has to keep the ciphers
 * whatever this archive turns out to hold — that is the eligibility rule this
 * branch has always had, now applied to a bundle rather than to one blob. */
static void ovl_keep(short id, int slot)
{
    unsigned long len;
    const unsigned char *p = ovl_find(gBundle, id, &len);
    Handle h;
    if (p == NULL || len == 0) { OVL_DIAG(gKeepFail = 1); return; }
    h = NewHandle((Size)len);
    if (h == NULL || *h == NULL) { OVL_DIAG(gKeepFail = 2); return; }
<<<<<<< Updated upstream
    /* MoveHHi before the lock. These copies are locked for the rest of the
     * run, and a locked block in the middle of the heap splits it. Measured
     * on a Macintosh 512Ke: with the copies left where NewHandle put them,
     * `derived-a2basic.dmg.sit` was granted 317,838 B and still failed —
     * `gRefusedWhy` = 2, NewPtr returning NULL for a 205 KB block against a
     * largest free block of 169,298 B. The memory was there, in two pieces. */
    MoveHHi(h);
=======
    /* MoveHHi before the lock, which is the whole reason this is not just
     * NewHandle + HLock.
     *
     * These copies are locked for the rest of the run, and a locked block in
     * the middle of the heap splits it. Measured on a Macintosh 512Ke: with
     * the copies left where NewHandle put them, `derived-a2basic.dmg.sit` was
     * granted 317,838 B and still failed — `gRefusedWhy` = 2, NewPtr
     * returning NULL for a 205 KB block against a largest free block of
     * 169,298 B. The memory was there; it was in two pieces. */
    /* MoveHHi(h); TEMPORARILY OUT — isolating a hang */
>>>>>>> Stashed changes
    HLock(h);
    BlockMoveData(p, *h, (Size)len);
    /* Relocated AGAIN, for the address the copy runs at: the fixup is
     * relative to wherever the image sits, and this one has moved. */
    ovl_fixup((unsigned char *)*h, (unsigned long)len,
              (long)*h - (long)p);   /* by the DIFFERENCE: p was relocated
                                      * for its place in the bundle */
    gKept[slot] = h;
    gKeptId[slot] = id;
}

/* Runs immediately after the sniff and therefore BEFORE the engine's first
 * allocation, which is where the budget is taken. So what it frees is heap
 * the engine is simply measured against a moment later — there is nothing to
 * credit back, and no ordering to get wrong. */
void ovl_release_if_unwanted(UncFormat fmt, UncIO *io, UncAlloc *al)
{
    short want = 0;
    int crypt = 1;

    if (gBundle == NULL) return;

    switch (fmt) {
    /* Decoder, and whether an entry might be encrypted. The second column is
     * the eligibility rule this branch has always had: a format that MAY
     * carry an encrypted entry keeps the ciphers, because encryption is
     * discovered per entry and this branch must decide before it knows. */
    case UNC_FORMAT_SPACESAVER:  want = OVL_ID_SPACESAVER; crypt = 0; break;
    case UNC_FORMAT_COMPACTPRO:  want = OVL_ID_CPTDD;      break;
    case UNC_FORMAT_DISKDOUBLER: want = OVL_ID_CPTDD;      crypt = 0; break;
    case UNC_FORMAT_LZH:         want = OVL_ID_LZH;        crypt = 0; break;
    case UNC_FORMAT_ARC:         want = OVL_ID_ARC;        break;
    case UNC_FORMAT_NOWCOMPRESS: want = OVL_ID_NOW;        crypt = 0; break;
    case UNC_FORMAT_SUPERDISK:   want = OVL_ID_SUPERDISK;  crypt = 0; break;
    case UNC_FORMAT_PACKIT:      want = OVL_ID_PACKIT;     break;
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
    case UNC_FORMAT_BINHEX:      case UNC_FORMAT_MACBINARY:
    case UNC_FORMAT_APPLESINGLE: case UNC_FORMAT_APPLEDOUBLE:
    case UNC_FORMAT_GZIP:        case UNC_FORMAT_COMPRESS_Z:
    case UNC_FORMAT_MIME:        case UNC_FORMAT_UU:
    case UNC_FORMAT_BTOA:        case UNC_FORMAT_BASE64:
    case UNC_FORMAT_SITSEG:      case UNC_FORMAT_DDSEG:
    case UNC_FORMAT_SPLIT:       case UNC_FORMAT_MIMESEG:
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
    /* Ask the archive. unc_archive_encrypted runs a LIST pass, so the answer
     * comes from the format's own reader rather than from a copy of its
     * layout, and it covers every format that can know — StuffIt and
     * StuffIt 5 among them, which is what lets a plain .sit release the
     * ciphers. ARC cannot know and answers UNKNOWN; so does a part of a
     * multi-part set, whose directory is in the LAST part.
     *
     * Only a definite NO releases them. There is no reload, so a wrong
     * release costs an entry rather than a disk access. */
    if (crypt && unc_archive_encrypted(fmt, io, al) == UNC_ENC_NO)
        crypt = 0;

    OVL_DIAG(gRelFmt = (short)fmt);
    if (want) ovl_keep(want, 0);
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
    gCodecsIn = 0;

    HUnlock(gBundle);
    ReleaseResource(gBundle);
    gBundle = NULL;
}

/* The SpaceSaver decoder, 'OVLY' 129. Its resident half is the PROBE, which
 * lives in src/fmt_spacesaver_probe.c and is never in the blob: the sniffer
 * calls it for every file, and an overlay loaded by sniffing would be an
 * overlay always loaded.
 *
 * Failure to load is a per-entry error like any other allocation failure —
 * UNC_ERR_MEM, and the rest of the archive still comes out. */
int unc_spacesaver_extract(UncCtx *c)
{
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    OverlayEntry e = ovl_image(OVL_ID_SPACESAVER);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_SPACESAVER_EXTRACT, c, NULL);
}

#define OVL_CALL(which, gp) (e(&gOvlHost, (which), (gp), NULL))

void unc_crypt_apply(UncCrypt *cr, uint8_t *buf, uint32_t len, uint32_t pos)
{
    OverlayEntry e = ovl_entry(); OvlArgs g;
    if (!e) { cr->kind = UNC_CRYPT_NONE; return; }
    g.obj = cr; g.out = buf; g.len = len; g.pos = pos;
    OVL_CALL(OVL_CRYPT_APPLY, &g);
}

#define VOID_KEYED(fn, code)                                              \
void fn(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen)                  \
{                                                                         \
    OverlayEntry e = ovl_entry(); OvlArgs g;                              \
    if (!e) { cr->kind = UNC_CRYPT_NONE; return; }                        \
    g.obj = cr; g.in = pw; g.len = pwlen;                                 \
    OVL_CALL(code, &g);                                                   \
}
VOID_KEYED(unc_crypt_cpt,        OVL_CRYPT_CPT)
VOID_KEYED(unc_crypt_packit_des, OVL_CRYPT_PACKIT_DES)
VOID_KEYED(unc_crypt_packit_xor, OVL_CRYPT_PACKIT_XOR)
VOID_KEYED(unc_crypt_rc4,        OVL_CRYPT_RC4)
VOID_KEYED(unc_crypt_xor,        OVL_CRYPT_XOR)

int unc_crypt_zip(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen)
{
    OverlayEntry e = ovl_entry(); OvlArgs g;
    if (!e) return UNC_ERR_MEM;
    g.obj = cr; g.in = pw; g.len = pwlen;
    return (int)OVL_CALL(OVL_CRYPT_ZIP, &g);
}

int unc_crypt_sit(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen,
                  const uint8_t entrykey[16], const uint8_t mkey[8])
{
    OverlayEntry e = ovl_entry(); OvlArgs g; const uint8_t *pair[2];
    if (!e) return UNC_ERR_MEM;
    pair[0] = entrykey; pair[1] = mkey;
    g.obj = cr; g.in = pw; g.len = pwlen; g.out = (void *)pair;
    return (int)OVL_CALL(OVL_CRYPT_SIT, &g);
}

int unc_crypt_sit5_key(const uint8_t *pw, uint16_t pwlen,
                       const uint8_t hash[UNC_SIT5_KEYLEN],
                       uint8_t out[UNC_SIT5_KEYLEN])
{
    OverlayEntry e = ovl_entry(); OvlArgs g;
    if (!e) return UNC_ERR_MEM;
    g.obj = (void *)hash; g.in = pw; g.len = pwlen; g.out = out;
    return (int)OVL_CALL(OVL_CRYPT_SIT5_KEY, &g);
}

int unc_crypt_winzip_aes(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen,
                         const uint8_t *salt, int keybytes,
                         const uint8_t verifier[2])
{
    OverlayEntry e = ovl_entry(); OvlArgs g; const uint8_t *pair[2];
    if (!e) return UNC_ERR_MEM;
    pair[0] = salt; pair[1] = verifier;
    g.obj = cr; g.in = pw; g.len = pwlen; g.out = (void *)pair;
    g.extra = (uint32_t)keybytes;
    return (int)OVL_CALL(OVL_CRYPT_WINZIP_AES, &g);
}

void unc_hmac_final(UncHmac *m, uint8_t out[20])
{
    OverlayEntry e = ovl_entry(); OvlArgs g;
    if (!e) return;
    g.obj = m; g.out = out;
    OVL_CALL(OVL_HMAC_FINAL, &g);
}

int unc_password(UncCtx *c, int again)
{
    OverlayEntry e = ovl_entry(); OvlArgs g;
    if (!e) return UNC_ERR_MEM;
    g.obj = c; g.len = (uint32_t)again;
    return (int)OVL_CALL(OVL_PASSWORD, &g);
}

int unc_resfork_find(const uint8_t *fork, uint32_t forklen, uint32_t type,
                     int16_t id, uint32_t *off, uint32_t *len)
{
    OverlayEntry e = ovl_entry(); OvlArgs g;
    if (!e) return UNC_ERR_MEM;
    g.in = fork; g.len = forklen; g.pos = type; g.extra = id;
    g.off_out = off; g.len_out = len;
    return (int)OVL_CALL(OVL_RESFORK_FIND, &g);
}

/* Compact Pro. The probe stays resident (src/fmt_cpt_probe.c); this is the decoder,
 * loaded when an archive actually turns out to be one. A load failure is a
 * per-entry error like any other allocation failure. */
int unc_cpt_extract(UncCtx *c)
{
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    OverlayEntry e = ovl_image(OVL_ID_CPTDD);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_CPT_EXTRACT, c, NULL);
}

/* DiskDoubler. The probe stays resident (src/fmt_stubs.c); this is the decoder,
 * loaded when an archive actually turns out to be one. A load failure is a
 * per-entry error like any other allocation failure. */
int unc_dd_extract(UncCtx *c)
{
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    OverlayEntry e = ovl_image(OVL_ID_CPTDD);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_DD_EXTRACT, c, NULL);
}

/* LZH. The probe stays resident (src/fmt_lzh_probe.c); this is the decoder,
 * loaded when an archive actually turns out to be one. A load failure is a
 * per-entry error like any other allocation failure. */
int unc_lzh_extract(UncCtx *c)
{
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    OverlayEntry e = ovl_image(OVL_ID_LZH);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_LZH_EXTRACT, c, NULL);
}

/* ARC. The probe stays resident (src/fmt_arc_probe.c); this is the decoder,
 * loaded when an archive actually turns out to be one. A load failure is a
 * per-entry error like any other allocation failure. */
int unc_arc_extract(UncCtx *c)
{
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    OverlayEntry e = ovl_image(OVL_ID_ARC);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_ARC_EXTRACT, c, NULL);
}

/* Now Compress. The probe stays resident (src/fmt_stubs.c); this is the decoder,
 * loaded when an archive actually turns out to be one. A load failure is a
 * per-entry error like any other allocation failure. */
int unc_now_extract(UncCtx *c)
{
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    OverlayEntry e = ovl_image(OVL_ID_NOW);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_NOW_EXTRACT, c, NULL);
}

/* SuperDisk!. Probe resident; decoder from the bundle. */
int unc_superdisk_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_SUPERDISK);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_SUPERDISK_EXTRACT, c, NULL);
}

/* PackIt. Probe resident; decoder from the bundle. */
int unc_packit_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_PACKIT);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_PACKIT_EXTRACT, c, NULL);
}

/* MIME. Probe resident; decoder from the bundle. */
int unc_mime_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_TEXT);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_MIME_EXTRACT, c, NULL);
}

/* uuencode. Probe resident; decoder from the bundle. */
int unc_uu_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_TEXT);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_UU_EXTRACT, c, NULL);
}

/* btoa. Probe resident; decoder from the bundle. */
int unc_btoa_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_TEXT);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_BTOA_EXTRACT, c, NULL);
}

/* base64. Probe resident; decoder from the bundle. */
int unc_b64_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_TEXT);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_B64_EXTRACT, c, NULL);
}

/* BinHex. Probe resident; decoder from the bundle. */
int unc_binhex_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_TEXT);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_BINHEX_EXTRACT, c, NULL);
}

/* StuffIt classic. Probe resident; decoder from the bundle. */
int unc_sit_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_STUFFIT);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_SIT_EXTRACT, c, NULL);
}

/* StuffIt 5. Probe resident; decoder from the bundle. */
int unc_sit5_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_STUFFIT);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_SIT5_EXTRACT, c, NULL);
}

/* Zip. Probe resident; decoder from the bundle. */
int unc_zip_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_EXO);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_ZIP_EXTRACT, c, NULL);
}

/* Gzip. Probe resident; decoder from the bundle. */
int unc_gzip_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_EXO);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_GZIP_EXTRACT, c, NULL);
}

/* Unix compress. Probe resident; decoder from the bundle. */
int unc_compressz_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_EXO);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_COMPRESSZ_EXTRACT, c, NULL);
}

/* Tar. Probe resident; decoder from the bundle. */
int unc_tar_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_EXO);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_TAR_EXTRACT, c, NULL);
}

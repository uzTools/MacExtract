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
/* `fc` is which flush route this machine offers — 0 none, 1 _HWPriv, 2
 * FlushCodeCache — and `fn` how many times one was called. Without them the
 * flush is a line nobody can watch fail: every tier here is either cacheless
 * or documented to ignore the request, so a green sweep says nothing about
 * whether the call was even reached. These two say which. */
short gFlushHas, gFlushCalls;
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

/* Newly written instruction bytes have to reach the instruction stream, and
 * this is a documented requirement rather than a precaution.
 *
 * Both fixup sites write code AS DATA and then execute it: ovl_bundle_fixup
 * rewrites longs inside the bundle at load, and ovl_keep copies an image with
 * BlockMoveData and fixes it up again at the copy's address.
 *
 * Source: Inside Macintosh: Memory, chapter 4, *Stale Instructions* — "you
 * must flush the instruction cache every time you modify executable
 * instructions in memory", and it names modifying jump-table entries and
 * installing patches by copying code as the cases. _BlockMove, _Read, _LoadSeg
 * and _UnloadSeg flush on the application's behalf; BlockMoveData is the
 * variant trap (0xA22E against _BlockMove's 0xA02E) and is not among them, so
 * ovl_keep's copy is exactly the case the chapter is about. Retro68's own
 * relocator flushes at the same two moments — after Retro68ApplyRelocations
 * and after patching each jump-table entry (libretro/relocate.c,
 * libretro/MultiSegApp.c) — which is where the trap-availability probe below
 * comes from.
 *
 * TWO traps, because the one the toolchain uses is not the documented one.
 * Retro68 calls FlushCodeCache (0xA0BD). Inside Macintosh: Memory documents
 * FlushInstructionCache as _HWPriv (0xA198) selector 1, and says that on a
 * processor with a copy-back data cache it flushes the DATA cache first, "to
 * ensure that any instructions subsequently copied to the instruction cache
 * are not copied from stale RAM" — which is the 68040 case, and the case a
 * BlockMoveData copy creates. So _HWPriv is preferred where it exists and
 * 0xA0BD is the fallback for the older ROMs that have only that.
 *
 * WHAT NO TIER HERE CAN SHOW. Mini vMac emulates a 68000, which has no cache,
 * and Apple documents that the 68LC040 Emulator — how the Mac OS 9 tier runs
 * this application — IGNORES requests to invalidate the 68040 instruction
 * cache, while telling developers to keep issuing them for 680x0 machines
 * (Inside Macintosh: PowerPC System Software, *The 68LC040 Emulator*). So a
 * green sweep on any tier this project can run is not evidence that the call
 * works, and the gFlushHas/gFlushCalls diagnostics below are what a run can
 * actually report: which route was taken, and how many times. Real 68020-and-up
 * silicon is MANUAL_TESTS.md's. */
static int gFlushProbed;
static int gFlushRoute;         /* 0 none, 1 _HWPriv, 2 FlushCodeCache */

static int ovl_trap_live(unsigned short trap)
{
    return GetOSTrapAddress(trap) != GetOSTrapAddress(_Unimplemented);
}

static void ovl_flush_code(void)
{
    if (!gFlushProbed) {
        const short *rom85 = (const short *)0x028EL;   /* >0 on a 128K ROM */
        gFlushProbed = 1;
        if (*rom85 > 0) {                    /* a 64K ROM has neither trap */
            if (ovl_trap_live(_HWPriv)) gFlushRoute = 1;
            else if (ovl_trap_live(0xA0BD)) gFlushRoute = 2;
        }
        OVL_DIAG(gFlushHas = (short)gFlushRoute);
    }
    if (gFlushRoute == 1) HWPriv(1, 0);      /* FlushInstructionCache */
    else if (gFlushRoute == 2) FlushCodeCache();
    else return;
    OVL_DIAG(gFlushCalls++);
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
static OverlayEntry ovl_image_q(short id, int expected)
{
    const unsigned char *p;
    unsigned long len;
    int i;
    for (i = 0; i < 3; i++)
        if (gKept[i] != NULL && gKeptId[i] == id)
            return (OverlayEntry)(void *)*gKept[i];
    if (gBundle == NULL) {
        if (!expected) OVL_DIAG(gWantedAfterRelease = id);
        return NULL;
    }
    p = ovl_find(gBundle, id, &len);
    return p ? (OverlayEntry)(void *)p : NULL;
}

static OverlayEntry ovl_image(short id) { return ovl_image_q(id, 0); }

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
    /* DART carries no encryption of any kind — the format has no flag for
     * it and no reference describes one — so the ciphers go. It is also the
     * one format here whose output is a file of its own format, which
     * changes nothing for this table: what comes out is written by the sink
     * like anything else. Before this line it fell to `default` and kept the
     * whole bundle, which was safe and bought nothing. */
    case UNC_FORMAT_DART:        want = OVL_ID_DART;       crypt = 0; break;
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
    /* BinHex has its own image now, but it is still an ENVELOPE: what is
     * under a .hqx is unknown until it has been unwrapped, so this branch
     * keeps the whole bundle for it exactly as before. The split buys the
     * lazy branch a smaller load; here it buys nothing, and pretending
     * otherwise would strand the archive inside. */
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
    if (crypt && (fmt == UNC_FORMAT_COMPACTPRO || fmt == UNC_FORMAT_ZIP) &&
        unc_archive_encrypted(fmt, io) == UNC_ENC_NO)
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
VOID_KEYED(unc_crypt_packit_xor, OVL_CRYPT_PACKIT_XOR)
VOID_KEYED(unc_crypt_rc4,        OVL_CRYPT_RC4)
VOID_KEYED(unc_crypt_xor,        OVL_CRYPT_XOR)

/* The two key setups that build their table on the heap. They take the
 * allocator and return UNC_ERR_MEM when it says no, so — unlike the
 * keyed shims above — a missing overlay is reported rather than absorbed
 * into UNC_CRYPT_NONE (DECISIONS.md 2026-09-19, the transient tables). */
#define INT_KEYED_AL(fn, code)                                            \
int fn(UncCrypt *cr, UncAlloc *al, const uint8_t *pw, uint16_t pwlen)     \
{                                                                         \
    OverlayEntry e = ovl_entry(); OvlArgs g;                              \
    if (!e) return UNC_ERR_MEM;                                           \
    g.obj = cr; g.al = al; g.in = pw; g.len = pwlen;                      \
    return (int)OVL_CALL(code, &g);                                       \
}
INT_KEYED_AL(unc_crypt_cpt,        OVL_CRYPT_CPT)
INT_KEYED_AL(unc_crypt_packit_des, OVL_CRYPT_PACKIT_DES)

/* Giving the table back goes through the overlay too, because the block
 * belongs to unc_crypt.c's own accounting. It is reachable whenever there
 * is anything to free: cr->tab is non-NULL only if a key setup ran, which
 * needed this image, and ovl_release_if_unwanted runs once after the sniff
 * and never during an extraction.
 *
 * And this is the ONE path allowed to find the image gone, which is why it
 * asks quietly. fmt_cpt.c, fmt_sit.c and fmt_packit.c free unconditionally at
 * cleanup, encrypted or not, and the resident unc_crypt_free is a no-op on a
 * NULL table — so an unencrypted Compact Pro, whose directory let the release
 * drop the ciphers, arrives here with nothing to free and no image to do it
 * with. Recording that as `wa` made the alarm fire on every such archive
 * (measured 2026-09-25: `wa=128` on derived-BootTime.cpt, extraction
 * complete, e1=0), and an alarm that fires when nothing is wrong cannot be
 * read when something is: `wa` is how the preload bug was found. */
void unc_crypt_free(UncCrypt *cr, UncAlloc *al)
{
    OverlayEntry e = ovl_image_q(OVL_ID_CRYPT, 1); OvlArgs g;
    if (!e) return;
    g.obj = cr; g.al = al;
    OVL_CALL(OVL_CRYPT_FREE, &g);
}

int unc_crypt_zip(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen)
{
    OverlayEntry e = ovl_entry(); OvlArgs g;
    if (!e) return UNC_ERR_MEM;
    g.obj = cr; g.in = pw; g.len = pwlen;
    return (int)OVL_CALL(OVL_CRYPT_ZIP, &g);
}

int unc_crypt_sit(UncCrypt *cr, UncAlloc *al, const uint8_t *pw,
                  uint16_t pwlen,
                  const uint8_t entrykey[16], const uint8_t mkey[8])
{
    OverlayEntry e = ovl_entry(); OvlArgs g; const uint8_t *pair[2];
    if (!e) return UNC_ERR_MEM;
    pair[0] = entrykey; pair[1] = mkey;
    g.obj = cr; g.al = al; g.in = pw; g.len = pwlen; g.out = (void *)pair;
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
    e = ovl_image(OVL_ID_BTOA);
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
    e = ovl_image(OVL_ID_BINHEX);
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

/* DART. Probe resident; decoder from the bundle. Needs the codecs image,
 * which is kept unconditionally — its "best" method is LZHUF. */
int unc_dart_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_DART);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_DART_EXTRACT, c, NULL);
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

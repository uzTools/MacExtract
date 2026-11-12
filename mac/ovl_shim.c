/* ovl_shim.c — what the engine links against when its decoders are overlays.
 *
 * One shim per entry point `src/*.c` would otherwise have provided: it asks
 * the loader for the image, dispatches into it, and returns what the engine
 * expects. The engine is unchanged and does not know the difference; the
 * point is that a decoder's code is not resident until an archive turns out
 * to want it, and code is the only thing that costs the engine budget on a
 * Macintosh (FORMATS.md, *What the application costs the engine*).
 *
 * NOTHING HERE KNOWS WHEN AN IMAGE IS READ. `ovl_image()` answers with one
 * whether the bundle was read at launch and this one kept, or the resource is
 * being fetched now because this shim asked — mac/ovl_load_eager.c and
 * mac/ovl_load_lazy.c, selected by UNC_OVL_LAZY at build time and
 * described in mac/ovl_load.h. The two were separate branches until
 * 2026-09-25 and this file was ~340 lines of the difference between them,
 * identical on both sides.
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
#include "ovl_load.h"
#include "unc_internal.h"
#include <Memory.h>

static uint32_t ovl_host_crc32(uint32_t crc, const uint8_t *p, uint32_t n)
{
    return unc_crc32(crc, p, (int32_t)n);
}

static OverlayHostFns gOvlFns = OVL_HOST_FNS_INIT;

/* Not static: the eager release hands it to the image that plans it
 * (mac/ovl_load_eager.c, ovl_plan), which asks the sniffer's. */
const OverlayHost gOvlHost = { ovl_host_crc32, NULL, NULL, NULL,
                                      (const struct OverlayHostFns *)&gOvlFns };

/* Load the codec machinery and let it plant itself in the vector. Every
 * decoder shim calls this BEFORE dispatching, because a decoder that ran with
 * NULL codec pointers would not fail — it would jump to zero.
 *
 * Returns 0 if the overlay could not be had, and the caller then reports a
 * per-entry memory error, which is what this shell does with every other
 * allocation failure. */
static int gCodecsIn;   /* the vector is patched to an ADDRESS, so it is only
                         * valid while the image it points into stays put.
                         * One bit per image that patches it: 1 the codecs,
                         * 2 zip's Shrink, Reduce and Implode (ovl_zipold.c). */

static int ovl_patched(short id, int bit)
{
    OverlayEntry e;
    if (gCodecsIn & bit) return 1;
    e = ovl_image(id);
    if (!e) return 0;
    e(&gOvlHost, OVL_CODEC_EXPORTS, &gOvlFns, NULL);
    gCodecsIn |= bit;
    return 1;
}

static int ovl_codecs_ready(void)
{
    return ovl_patched(OVL_ID_CODECS, 1);
}

/* The eager release copies the codecs image out of the bundle, so the vector
 * has to be re-patched to the copy's address; it calls this and the next
 * decoder plants the vector again. The lazy lifetime never moves an image and
 * never calls it. */
void ovl_codecs_invalidate(void)
{
    gCodecsIn = 0;
}

static OverlayEntry ovl_entry(void)
{
    return ovl_image(OVL_ID_CRYPT);
}

/* The sniffer and every probe, 'OVLY' 144, since 2026-10-21. Run from the
 * bundle BEFORE the release, which is what its answer decides, and given
 * back with everything else: a later layer under an envelope is sniffed
 * with the bundle still whole, and the next archive in the Finder's list
 * after the reload. No image means no answer, and UNKNOWN is the honest
 * one — with the bundle missing, nothing could be extracted anyway. The
 * codecs are not needed: a probe reads bytes, CRCs and the file's size
 * through resident slots of the vector (DECISIONS.md 2026-10-21, *the
 * probes that left with the bundle*). */
UncFormat unc_sniff(UncIO *io)
{
    OverlayEntry e = ovl_image(OVL_ID_SNIFF);
    if (!e) return UNC_FORMAT_UNKNOWN;
    return (UncFormat)e(&gOvlHost, OVL_SNIFF, io, NULL);
}

/* In the same image: the envelope a file would be unwrapped as, for the
 * scan of a folder for a set's parts inside envelopes. */
UncFormat unc_sniff_envelope(UncIO *io)
{
    OverlayEntry e = ovl_image(OVL_ID_SNIFF);
    if (!e) return UNC_FORMAT_UNKNOWN;
    return (UncFormat)e(&gOvlHost, OVL_SNIFF_ENVELOPE, io, NULL);
}

/* In the same image: where a fat installer's part 1 ends. A StuffIt set
 * keeps the bundle whole while it joins (ovl_release_if_unwanted), so the
 * image is there when part 1 is opened; without it the answer is the
 * fork's own length, which is what a part with no 'endD' gets anyway. */
uint32_t unc_segment_first_end(const UncSegmentDesc *desc, UncIO *rsrc,
                               uint32_t datalen)
{
    OverlayEntry e = ovl_image(OVL_ID_SNIFF);
    OvlArgs g;
    if (!e) return datalen;
    g.obj = (void *)desc; g.in = rsrc; g.len = datalen;
    return (uint32_t)e(&gOvlHost, OVL_SEG_FIRST_END, &g, NULL);
}


/* In the same image: which set a file belongs to (src/unc_segid.c). Asked
 * with the bundle whole, before the release, and again while a set is
 * read, by the part search a disk swap starts (mac/macextract_mac.c,
 * SegPartOf). The bundle is whole then for every scheme but three: a spanned
 * zip's parts are placed by name and never asked, and Compact Pro's and
 * Apple Backup's are matched in their reader's image, which the set keeps.
 * No image is no set:
 * UNC_ERR_FORMAT, which a match reads as 0. */
static int32_t seg_id(short id, int32_t which, const void *obj,
                      const void *in, uint32_t len)
{
    OverlayEntry e = ovl_image(id);
    OvlArgs g;
    if (!e) return UNC_ERR_FORMAT;
    g.obj = (void *)obj; g.in = in; g.len = len;
    return e(&gOvlHost, which, &g, NULL);
}

int unc_segment_describe_as(UncIO *io, UncFormat scheme,
                            UncSegmentDesc *desc)
{
    return (int)seg_id(OVL_ID_SNIFF, OVL_SEG_DESCRIBE, desc, io,
                       (uint32_t)scheme);
}

int unc_segment_describe(UncIO *io, UncSegmentDesc *desc)
{
    return (int)seg_id(OVL_ID_SNIFF, OVL_SEG_DESCRIBE, desc, io,
                       OVL_SEG_EVERY);
}

/* Every decoder, by one table and one function (DECISIONS.md 2026-10-23,
 * *the shims that were one function*, and 2026-11-11, *the release
 * decided in the bundle*).
 *
 * The engine calls each format's entry point by name, as it does on Linux,
 * and on this build every one of those names did the same four things with
 * two different constants: plant the codec vector, find the image, return
 * UNC_ERR_MEM if either failed, and call the image at its entry point. Since
 * 2026-10-23 the four things are ovl_run, once; since 2026-11-11 every name
 * IS ovl_run, an alias, and the constants are a row of gRun, found by the
 * format the engine is reading — UncCtx.fmt, which unc_extract_as sets, and
 * which the segment joiner sets to the set's scheme (src/unc_segment.c). A
 * row is the image (as an offset from 128, five bits), the entry point
 * (eight) and what has to be planted first; two bytes a format, where a
 * name of its own was an 18-byte call.
 *
 * A format with no row reaches the ciphers' self-test and returns its
 * 0x4F4B, which the shell reports as an error of no name: every format the
 * engine table or a segment scheme sends here needs one, and
 * tools/check_ovl_rows.py (ci.sh) fails on one that has none.
 *
 * Failure to load is a per-entry error like any other allocation failure —
 * UNC_ERR_MEM, and the rest of the archive still comes out. */
#define RUN_CODECS 0x2000   /* the shared codecs, which every decoder calls
                             * into through the vector — all but the readers
                             * that copy stored forks */
#define RUN_ZIPOLD 0x4000   /* zip's Shrink, Reduce and Implode, which only
                             * zip calls */
#define RUN_MATCH  0x8000   /* a set whose release keeps this image and not
                             * the sniffer's: its parts are matched here
                             * (unc_segment_match), by OVL_SEG_MATCH */
#define RUN(id, which, flags) \
    ((unsigned short)((((id) - OVL_ID_CRYPT) << 8) | (which) | (flags)))

static const unsigned short gRun[UNC_FORMAT__COUNT] = {
    [UNC_FORMAT_SPACESAVER]  = RUN(OVL_ID_SPACESAVER, OVL_SPACESAVER_EXTRACT, RUN_CODECS),
    [UNC_FORMAT_COMPACTPRO]  = RUN(OVL_ID_CPTDD,      OVL_CPT_EXTRACT,        RUN_CODECS),
    /* A Compact Pro set, read by the same reader over the joined parts. */
    [UNC_FORMAT_CPTSEG]      = RUN(OVL_ID_CPTDD,      OVL_CPT_EXTRACT,        RUN_CODECS | RUN_MATCH),
    [UNC_FORMAT_DISKDOUBLER] = RUN(OVL_ID_CPTDD,      OVL_DD_EXTRACT,         RUN_CODECS),
    [UNC_FORMAT_LZH]         = RUN(OVL_ID_LZH,        OVL_LZH_EXTRACT,        RUN_CODECS),
    [UNC_FORMAT_ARC]         = RUN(OVL_ID_ARC,        OVL_ARC_EXTRACT,        RUN_CODECS),
    [UNC_FORMAT_NOWCOMPRESS] = RUN(OVL_ID_NOW,        OVL_NOW_EXTRACT,        RUN_CODECS),
    [UNC_FORMAT_SUPERDISK]   = RUN(OVL_ID_SUPERDISK,  OVL_SUPERDISK_EXTRACT,  RUN_CODECS),
    [UNC_FORMAT_PACKIT]      = RUN(OVL_ID_PACKIT,     OVL_PACKIT_EXTRACT,     RUN_CODECS),
    [UNC_FORMAT_SQP]         = RUN(OVL_ID_SQP,        OVL_SQP_EXTRACT,        RUN_CODECS),
    [UNC_FORMAT_MIME]        = RUN(OVL_ID_TEXT,       OVL_MIME_EXTRACT,       RUN_CODECS),
    /* A message/partial set joins into a message, read by the MIME walk. */
    [UNC_FORMAT_MIMESEG]     = RUN(OVL_ID_TEXT,       OVL_MIME_EXTRACT,       RUN_CODECS),
    [UNC_FORMAT_UU]          = RUN(OVL_ID_TEXT,       OVL_UU_EXTRACT,         RUN_CODECS),
    [UNC_FORMAT_BTOA]        = RUN(OVL_ID_BTOA,       OVL_BTOA_EXTRACT,       RUN_CODECS),
    [UNC_FORMAT_BASE64]      = RUN(OVL_ID_TEXT,       OVL_B64_EXTRACT,        RUN_CODECS),
    /* BinHex 4, and before it .hex/.hcx and .dl: one entry point, which
     * reads UncCtx.fmt itself (src/fmt_binhex.c). */
    [UNC_FORMAT_BINHEX]      = RUN(OVL_ID_BINHEX,     OVL_BINHEX_EXTRACT,     RUN_CODECS),
    [UNC_FORMAT_BINHEX_OLD]  = RUN(OVL_ID_BINHEX,     OVL_BINHEX_EXTRACT,     RUN_CODECS),
    [UNC_FORMAT_DL]          = RUN(OVL_ID_BINHEX,     OVL_BINHEX_EXTRACT,     RUN_CODECS),
    /* MacBinary and AppleSingle/AppleDouble, beside BinHex: readers with no
     * codecs, which copy forks through the resident helpers. */
    [UNC_FORMAT_MACBINARY]   = RUN(OVL_ID_BINHEX,     OVL_MACBINARY_EXTRACT,  0),
    [UNC_FORMAT_APPLESINGLE] = RUN(OVL_ID_BINHEX,     OVL_APPLEDOUBLE_EXTRACT, 0),
    [UNC_FORMAT_APPLEDOUBLE] = RUN(OVL_ID_BINHEX,     OVL_APPLEDOUBLE_EXTRACT, 0),
    [UNC_FORMAT_SIT]         = RUN(OVL_ID_STUFFIT,    OVL_SIT_EXTRACT,        RUN_CODECS),
    [UNC_FORMAT_SIT5]        = RUN(OVL_ID_STUFFIT,    OVL_SIT5_EXTRACT,       RUN_CODECS),
    /* Private File: a reader with no codecs, in the StuffIt image beside the
     * archive it always decrypts to. Its cipher calls cross to the crypt
     * image through the resident shims above, as StuffIt 5's do. */
    [UNC_FORMAT_PRIVATEFILE] = RUN(OVL_ID_STUFFIT,    OVL_PF_EXTRACT,         0),
    [UNC_FORMAT_ZIP]         = RUN(OVL_ID_EXO,        OVL_ZIP_EXTRACT,        RUN_CODECS | RUN_ZIPOLD),
    /* A spanned zip, read by zip's reader over the joined parts. */
    [UNC_FORMAT_ZIPSEG]      = RUN(OVL_ID_EXO,        OVL_ZIP_EXTRACT,        RUN_CODECS | RUN_ZIPOLD),
    [UNC_FORMAT_GZIP]        = RUN(OVL_ID_EXO,        OVL_GZIP_EXTRACT,       RUN_CODECS),
    [UNC_FORMAT_COMPRESS_Z]  = RUN(OVL_ID_EXO,        OVL_COMPRESSZ_EXTRACT,  RUN_CODECS),
    /* Tar is in zip's old-methods image; src/fmt_tar.c says why. */
    [UNC_FORMAT_TAR]         = RUN(OVL_ID_ZIPOLD,     OVL_TAR_EXTRACT,        RUN_CODECS),
    /* MAR beside it: stored forks, no codec (src/fmt_mar.c). */
    [UNC_FORMAT_MAR]         = RUN(OVL_ID_ZIPOLD,     OVL_MAR_EXTRACT,        0),
    /* An LZ4 frame beside it: its own window, no codec (src/fmt_lz4.c). */
    [UNC_FORMAT_LZ4]         = RUN(OVL_ID_ZIPOLD,     OVL_LZ4_EXTRACT,        0),
    /* Apple Backup beside it: stored forks across disks, no codec
     * (src/fmt_abk.c); read only as a set. */
    [UNC_FORMAT_ABK]         = RUN(OVL_ID_ZIPOLD,     OVL_ABK_EXTRACT,        RUN_MATCH),
    /* And the Installer Tome: its own window, no codec (src/fmt_tome.c). */
    [UNC_FORMAT_TOME]        = RUN(OVL_ID_ZIPOLD,     OVL_TOME_EXTRACT,       0),
};

int unc_segment_match(const UncSegmentDesc *desc, const uint8_t *head,
                      int32_t len)
{
    short id = OVL_ID_SNIFF;
    int32_t r;
    /* A scheme whose set keeps its reader's image and not the sniffer's
     * is matched in that image, which gRun names (RUN_MATCH above). */
    if (desc) {
        unsigned short how = gRun[desc->scheme];
        if (how & RUN_MATCH)
            id = (short)(OVL_ID_CRYPT + ((how >> 8) & 0x1f));
    }
    r = seg_id(id, OVL_SEG_MATCH, desc, head, (uint32_t)len);
    return r > 0 ? (int)r : 0;
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
                  const uint8_t entrykey[16], const uint8_t mkey[8],
                  int scheme)
{
    OverlayEntry e = ovl_entry(); OvlArgs g; const uint8_t *pair[2];
    if (!e) return UNC_ERR_MEM;
    pair[0] = entrykey; pair[1] = mkey;
    g.obj = cr; g.al = al; g.in = pw; g.len = pwlen; g.out = (void *)pair;
    g.pos = (uint32_t)scheme;
    return (int)OVL_CALL(OVL_CRYPT_SIT, &g);
}

void unc_crypt_pf(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen,
                  uint16_t keylen)
{
    OverlayEntry e = ovl_entry(); OvlArgs g;
    if (!e) { cr->kind = UNC_CRYPT_NONE; return; }
    g.obj = cr; g.in = pw; g.len = pwlen; g.extra = keylen;
    OVL_CALL(OVL_CRYPT_PF, &g);
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

static int ovl_run(UncCtx *c)
{
    unsigned short how = gRun[c->fmt];
    OverlayEntry e;
    if ((how & RUN_CODECS) && !ovl_codecs_ready()) return UNC_ERR_MEM;
    if ((how & RUN_ZIPOLD) && !ovl_patched(OVL_ID_ZIPOLD, 2))
        return UNC_ERR_MEM;
    e = ovl_image((short)(OVL_ID_CRYPT + ((how >> 8) & 0x1f)));
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, how & 0xff, c, NULL);
}

/* The engine's two dispatches (src/unc_internal.h). A set's reader is
 * gRun's row for the scheme; a format read as a file is gRun's row for the
 * format, but for the three readers of one part of a set that are
 * resident, beside the joiner that shares their code: a zip part's row is
 * the set's, zip's reader, and one part on its own is what
 * unc_zipseg_extract refuses. tools/check_ovl_rows.py reads these three
 * comparisons as rows. */
int unc_run(UncCtx *c) __attribute__((alias("ovl_run")));

int unc_run_file(UncCtx *c)
{
    if (c->fmt == UNC_FORMAT_SITSEG) return unc_sitseg_extract(c);
    if (c->fmt == UNC_FORMAT_DDSEG)  return unc_ddseg_extract(c);
    if (c->fmt == UNC_FORMAT_ZIPSEG) return unc_zipseg_extract(c);
    return ovl_run(c);
}

#define DECODER(fn) int fn(UncCtx *c) __attribute__((alias("ovl_run")));
DECODER(unc_spacesaver_extract)
DECODER(unc_cpt_extract)
DECODER(unc_dd_extract)
DECODER(unc_lzh_extract)
DECODER(unc_arc_extract)
DECODER(unc_now_extract)
DECODER(unc_superdisk_extract)
DECODER(unc_packit_extract)
DECODER(unc_sqp_extract)
DECODER(unc_mime_extract)
DECODER(unc_uu_extract)
DECODER(unc_btoa_extract)
DECODER(unc_b64_extract)
DECODER(unc_binhex_extract)
DECODER(unc_macbinary_extract)
DECODER(unc_appledouble_extract)
DECODER(unc_sit_extract)
DECODER(unc_sit5_extract)
DECODER(unc_pf_extract)
DECODER(unc_zip_extract)
DECODER(unc_gzip_extract)
DECODER(unc_compressz_extract)
DECODER(unc_tar_extract)
DECODER(unc_mar_extract)
DECODER(unc_lz4_extract)
DECODER(unc_abk_extract)
DECODER(unc_tome_extract)

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

static const OverlayHost gOvlHost = { ovl_host_crc32, NULL, NULL, NULL,
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
                         * 2 zip's Shrink and Reduce (ovl_zipold.c). */

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

/* AppleLink packages. Probe resident; decoder from the bundle. */
int unc_sqp_extract(UncCtx *c)
{
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_image(OVL_ID_SQP);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_SQP_EXTRACT, c, NULL);
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

/* Private File: a reader with no codecs, in the StuffIt image beside the
 * archive it always decrypts to. Its cipher calls cross to the crypt image
 * through the resident shims above, as StuffIt 5's do. */
int unc_pf_extract(UncCtx *c)
{
    OverlayEntry e = ovl_image(OVL_ID_STUFFIT);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_PF_EXTRACT, c, NULL);
}

/* Zip. Probe resident; decoder from the bundle. */
int unc_zip_extract(UncCtx *c)
{
    OverlayEntry e;
    /* Zip's Shrink and Reduce too, which only zip keeps. */
    if (!ovl_codecs_ready() || !ovl_patched(OVL_ID_ZIPOLD, 2))
        return UNC_ERR_MEM;
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

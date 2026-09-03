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

/* NOT const: the codecs overlay writes its own addresses into these fields
 * when it loads (OVL_CODEC_EXPORTS). Fifteen of them start NULL, because
 * their implementations are not in the application at all. */
static OverlayHostFns gOvlFns = OVL_HOST_FNS_INIT;


static const OverlayHost gOvlHost = { ovl_host_crc32, NULL, NULL, NULL,
                                      (const struct OverlayHostFns *)&gOvlFns };

/* Big-endian, byte-wise: the image is a Handle, and nothing guarantees a
 * relocation lands on an even address. */
static unsigned long ovl_be32(const unsigned char *p)
{
    return ((unsigned long)p[0] << 24) | ((unsigned long)p[1] << 16) |
           ((unsigned long)p[2] << 8) | (unsigned long)p[3];
}

/* Apply the relocation trailer, once, to an image at the address it will run
 * at.
 *
 * -mpcrel makes the CODE position-independent and for a year that was taken
 * to mean the image was. It is not: an array of POINTERS in constant data —
 * `sit13_firstlengths`, zlib's `z_errmsg`, MIME's keyword tables — holds
 * LINK-TIME addresses, and a blob loaded wherever the Memory Manager put it
 * dereferences them into nowhere. What that looked like was StuffIt's
 * method 13 returning UNC_ERR_CORRUPT for exactly the entries small enough to
 * use its preset tables: one fixture in 69, found by the tier and by nothing
 * before it.
 *
 * Layout (tools/overlay/mkreloctrailer.py): the image, then one u32 image
 * offset per relocation, then the count. Every image carries the trailer, a
 * clean one with a count of 0. */
static void ovl_fixup(unsigned char *base, unsigned long size)
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
        v = ovl_be32(base + off) + (unsigned long)base;
        base[off]     = (unsigned char)(v >> 24);
        base[off + 1] = (unsigned char)(v >> 16);
        base[off + 2] = (unsigned char)(v >> 8);
        base[off + 3] = (unsigned char)v;
    }
}

static OverlayEntry ovl_load(short id, Handle *slot, int *tried)
{
    if (!*tried) {
        *tried = 1;
        *slot = GetResource('OVLY', id);
        if (*slot != NULL && **slot != NULL) {
            HLock(*slot);
            /* AFTER HLock: the fixup writes the address the image will run
             * at, so the image must not move afterwards. */
            ovl_fixup((unsigned char *)**slot,
                      (unsigned long)GetHandleSize(*slot));
        } else {
            *slot = NULL;
        }
    }
    return *slot ? (OverlayEntry)(void *)**slot : NULL;
}

/* Load the codec machinery and let it plant itself in the vector. Every
 * decoder shim calls this BEFORE dispatching, because a decoder that ran with
 * NULL codec pointers would not fail — it would jump to zero.
 *
 * Returns 0 if the overlay could not be had, and the caller then reports a
 * per-entry memory error, which is what this shell does with every other
 * allocation failure. */
static int ovl_codecs_ready(void)
{
    static Handle h;
    static int tried, in;
    OverlayEntry e;
    if (in) return 1;
    e = ovl_load(OVL_ID_CODECS, &h, &tried);
    if (!e) return 0;
    e(&gOvlHost, OVL_CODEC_EXPORTS, &gOvlFns, NULL);
    in = 1;
    return 1;
}

static OverlayEntry ovl_entry(void)
{
    static Handle h;
    static int tried;
    return ovl_load(OVL_ID_CRYPT, &h, &tried);
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
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_SPACESAVER, &h, &tried);
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
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_CPTDD, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_CPT_EXTRACT, c, NULL);
}

/* DiskDoubler. The probe stays resident (src/fmt_stubs.c); this is the decoder,
 * loaded when an archive actually turns out to be one. A load failure is a
 * per-entry error like any other allocation failure. */
int unc_dd_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_CPTDD, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_DD_EXTRACT, c, NULL);
}

/* LZH. The probe stays resident (src/fmt_lzh_probe.c); this is the decoder,
 * loaded when an archive actually turns out to be one. A load failure is a
 * per-entry error like any other allocation failure. */
int unc_lzh_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_LZH, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_LZH_EXTRACT, c, NULL);
}

/* ARC. The probe stays resident (src/fmt_arc_probe.c); this is the decoder,
 * loaded when an archive actually turns out to be one. A load failure is a
 * per-entry error like any other allocation failure. */
int unc_arc_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_ARC, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_ARC_EXTRACT, c, NULL);
}

/* Now Compress. The probe stays resident (src/fmt_stubs.c); this is the decoder,
 * loaded when an archive actually turns out to be one. A load failure is a
 * per-entry error like any other allocation failure. */
int unc_now_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_NOW, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_NOW_EXTRACT, c, NULL);
}

/* SuperDisk!. Probe resident (src/fmt_superdisk_probe.c), decoder on demand. */
int unc_superdisk_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_SUPERDISK, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_SUPERDISK_EXTRACT, c, NULL);
}

/* PackIt. Probe resident (src/fmt_packit_probe.c), decoder on demand. */
int unc_packit_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_PACKIT, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_PACKIT_EXTRACT, c, NULL);
}

/* MIME. Probe resident (src/fmt_mime_probe.c), decoder on demand. */
int unc_mime_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_TEXT, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_MIME_EXTRACT, c, NULL);
}

/* uuencode. Probe resident (src/fmt_uu_probe.c), decoder on demand. */
int unc_uu_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_TEXT, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_UU_EXTRACT, c, NULL);
}

/* btoa. Probe resident (src/fmt_btoa_probe.c), decoder on demand. */
int unc_btoa_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_BTOA, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_BTOA_EXTRACT, c, NULL);
}

/* base64. Probe resident (src/fmt_b64_probe.c), decoder on demand. */
int unc_b64_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_TEXT, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_B64_EXTRACT, c, NULL);
}

/* BinHex. Probe resident (src/fmt_binhex_probe.c), decoder on demand. */
int unc_binhex_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_BINHEX, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_BINHEX_EXTRACT, c, NULL);
}

/* StuffIt classic. Probe resident (src/fmt_sit_probe.c), decoder on demand. */
int unc_sit_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_STUFFIT, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_SIT_EXTRACT, c, NULL);
}

/* StuffIt 5. Probe resident (src/fmt_sit5_probe.c), decoder on demand. */
int unc_sit5_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_STUFFIT, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_SIT5_EXTRACT, c, NULL);
}

/* Zip. */
int unc_zip_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_EXO, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_ZIP_EXTRACT, c, NULL);
}

/* Gzip. */
int unc_gzip_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_EXO, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_GZIP_EXTRACT, c, NULL);
}

/* Unix compress. */
int unc_compressz_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_EXO, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_COMPRESSZ_EXTRACT, c, NULL);
}

/* Tar. */
int unc_tar_extract(UncCtx *c)
{
    static Handle h;
    static int tried;
    OverlayEntry e;
    if (!ovl_codecs_ready()) return UNC_ERR_MEM;
    e = ovl_load(OVL_ID_EXO, &h, &tried);
    if (!e) return UNC_ERR_MEM;
    return (int)e(&gOvlHost, OVL_TAR_EXTRACT, c, NULL);
}

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
#include "unc_internal.h"
#include <Resources.h>
#include <Memory.h>

static uint32_t ovl_host_crc32(uint32_t crc, const uint8_t *p, uint32_t n)
{
    return unc_crc32(crc, p, (int32_t)n);
}

static const OverlayHost gOvlHost = { ovl_host_crc32, NULL, NULL, NULL };

static Handle gOvl;
static int gOvlTried, gOvlReleased;

/* EAGER, and that is the whole point of this branch. A lazy GetResource has
 * to touch the application's own disk AFTER the archive has been chosen, and
 * on the machine this project is designed around — a Mac Plus with one floppy
 * drive, which "cannot mount two" (DECISIONS.md 2026-08-24) — that disk may
 * have been swapped for the archive's by then. Loading at launch means the
 * only disk access happens while the boot disk is certainly in.
 *
 * Called from main() before anything is opened. */
void ovl_preload(void)
{
    if (gOvlTried) return;
    gOvlTried = 1;
    gOvl = GetResource('OVLY', 128);
    if (gOvl != NULL && *gOvl != NULL) HLock(gOvl);
    else gOvl = NULL;
}

/* Give the 15 KB back once the format says the ciphers cannot be wanted.
 *
 * The list is short because two things disqualify a format: it may carry an
 * encrypted entry, or it is an ENVELOPE whose contents are not yet known — a
 * .sit.hqx sniffs as BinHex, and releasing on that would strand the StuffIt
 * inside it. So this pays for LZH, DiskDoubler, Now Compress, SpaceSaver,
 * SuperDisk! and tar, and NOT for StuffIt, which is the common case.
 * BRANCH_NOTES.md says why that limit is inherent rather than an oversight. */
void ovl_release_if_unwanted(UncFormat fmt)
{
    switch (fmt) {
    case UNC_FORMAT_LZH:         case UNC_FORMAT_DISKDOUBLER:
    case UNC_FORMAT_NOWCOMPRESS: case UNC_FORMAT_SPACESAVER:
    case UNC_FORMAT_SUPERDISK:   case UNC_FORMAT_TAR:
        break;
    default:
        return;                      /* may encrypt, or may wrap something */
    }
    if (gOvl != NULL) {
        HUnlock(gOvl);
        ReleaseResource(gOvl);
        gOvl = NULL;
        gOvlReleased = 1;
    }
}

static OverlayEntry ovl_entry(void)
{
    /* RELOADS if it was released, and that is not a detail. The release is
     * per ARCHIVE; this application loops back to Standard File and opens
     * another. Extract an LZH, then an encrypted .sit in the same session,
     * and a shim that refused to reload would find the ciphers gone — the
     * cipher kind cleared, the entry failing, a capability disappearing
     * because of what was opened BEFORE it. Not a prompt, not a delay: a
     * silent loss.
     *
     * So a reload is allowed, and it costs what this branch was trying to
     * avoid — a disk access after an archive has been chosen. That is the
     * honest price of releasing at all, and it is why neither overlay branch
     * is obviously worth merging for 6 KB (BRANCH_NOTES.md). */
    if (!gOvlTried || (gOvlReleased && gOvl == NULL)) {
        gOvlTried = 0;
        gOvlReleased = 0;
        ovl_preload();
    }
    return gOvl ? (OverlayEntry)(void *)*gOvl : NULL;
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

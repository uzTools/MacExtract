/* ovl_crypt.c — the cipher overlay: src/unc_crypt.c, out of resident code.
 *
 * unc_crypt.c is compiled in UNMODIFIED. It was chosen as the first real
 * overlay because its seam is clean: four of its five external references are
 * libgcc arithmetic helpers, which link into the image, and the fifth is
 * unc_crc32, routed through the host vector below. Nothing in the engine
 * reaches into it except through the entry points dispatched here.
 *
 * Everything it holds is only wanted when an archive turns out to be
 * encrypted — the ciphers, their tables, the password state machine and the
 * resource-fork walk that finds StuffIt's 'MKey'. An ordinary extraction
 * never loads it and never pays for it.
 */
#include "overlay.h"
#include "unc_internal.h"

/* INITIALISED, deliberately: an uninitialised static lands in .bss, which
 * objcopy leaves out of the image, so the blob would write past its own end
 * into the heap. .data is inside the image, which is a locked Handle and
 * writable. mkoverlay.sh refuses .bss for exactly this reason. */
static const OverlayHost *g_host = (const OverlayHost *)-1;

uint32_t unc_crc32(uint32_t crc, const uint8_t *buf, int32_t len)
{
    return g_host->crc32(crc, buf, (uint32_t)len);
}

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b);
int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    OvlArgs *g = (OvlArgs *)a;
    (void)b;
    g_host = host;
    switch (which) {
    case OVL_SELFTEST:
        return 0x4F4B;
    case OVL_CRYPT_APPLY:
        unc_crypt_apply((UncCrypt *)g->obj, (uint8_t *)g->out, g->len, g->pos);
        return 0;
    /* The three key setups that build their table on the heap take the
     * allocator and can fail with UNC_ERR_MEM, which is why these two
     * return what they used to discard (DECISIONS.md 2026-09-19, the
     * transient tables). */
    case OVL_CRYPT_CPT:
        return (int32_t)unc_crypt_cpt((UncCrypt *)g->obj, (UncAlloc *)g->al,
                                      (const uint8_t *)g->in,
                                      (uint16_t)g->len);
    case OVL_CRYPT_PACKIT_DES:
        return (int32_t)unc_crypt_packit_des((UncCrypt *)g->obj,
                                             (UncAlloc *)g->al,
                                             (const uint8_t *)g->in,
                                             (uint16_t)g->len);
    case OVL_CRYPT_FREE:
        unc_crypt_free((UncCrypt *)g->obj, (UncAlloc *)g->al);
        return 0;
    case OVL_CRYPT_PACKIT_XOR:
        unc_crypt_packit_xor((UncCrypt *)g->obj, (const uint8_t *)g->in,
                             (uint16_t)g->len);
        return 0;
    case OVL_CRYPT_RC4:
        unc_crypt_rc4((UncCrypt *)g->obj, (const uint8_t *)g->in,
                      (uint16_t)g->len);
        return 0;
    case OVL_CRYPT_XOR:
        unc_crypt_xor((UncCrypt *)g->obj, (const uint8_t *)g->in,
                      (uint16_t)g->len);
        return 0;
    case OVL_CRYPT_ZIP:
        return (int32_t)unc_crypt_zip((UncCrypt *)g->obj,
                                      (const uint8_t *)g->in, (uint16_t)g->len);
    case OVL_CRYPT_SIT:
        /* entrykey[16] and mkey[8] both arrive: `in` is the password,
         * `out` points at a two-pointer array so one struct carries both. */
        return (int32_t)unc_crypt_sit((UncCrypt *)g->obj, (UncAlloc *)g->al,
                                      (const uint8_t *)g->in, (uint16_t)g->len,
                                      ((const uint8_t **)g->out)[0],
                                      ((const uint8_t **)g->out)[1]);
    case OVL_CRYPT_SIT5_KEY:
        return (int32_t)unc_crypt_sit5_key((const uint8_t *)g->in,
                                           (uint16_t)g->len,
                                           (const uint8_t *)g->obj,
                                           (uint8_t *)g->out);
    case OVL_CRYPT_WINZIP_AES:
        return (int32_t)unc_crypt_winzip_aes((UncCrypt *)g->obj,
                                             (const uint8_t *)g->in,
                                             (uint16_t)g->len,
                                             ((const uint8_t **)g->out)[0],
                                             (int)g->extra,
                                             ((const uint8_t **)g->out)[1]);
    case OVL_HMAC_FINAL:
        unc_hmac_final((UncHmac *)g->obj, (uint8_t *)g->out);
        return 0;
    case OVL_PASSWORD:
        return (int32_t)unc_password((UncCtx *)g->obj, (int)g->len);
    case OVL_RESFORK_FIND:
        return (int32_t)unc_resfork_find((const uint8_t *)g->in, g->len,
                                         g->pos, (int16_t)g->extra,
                                         g->off_out, g->len_out);
    default:
        return -1;
    }
}

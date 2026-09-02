/* overlay.h — the contract between the application and a loadable overlay.
 *
 * An overlay is a flat, position-independent blob stored as a resource and
 * loaded only when the archive needs it. Its whole point is that its CODE is
 * not resident: code is the only thing that costs the engine budget on a
 * Macintosh (FORMATS.md, *What the application costs the engine*).
 *
 * Position independence comes from -mpcrel, which turns internal references
 * into PC-relative ones the LINKER resolves, so a linked blob carries no
 * runtime relocations. That costs a +-32 KB range, which bounds an overlay's
 * size and is checked by the build.
 *
 * Everything an overlay needs from outside itself arrives in OverlayHost. It
 * may not call the application directly: there is no relocation left to patch
 * such a call with.
 */
#ifndef UNC_OVERLAY_H
#define UNC_OVERLAY_H

#include <stdint.h>

struct UncBitIn; struct UncBufIn; struct UncIO; struct UncProgressState;
struct UncEntryInfo; struct UncForkOut; struct UncCtx;

typedef struct OverlayHost {
    uint32_t (*crc32)(uint32_t crc, const uint8_t *p, uint32_t n);
    void    *(*alloc)(void *ctx, uint32_t n);
    void     (*free)(void *ctx, void *p);
    void     *alloc_ctx;

    /* The engine helpers a DECODER overlay needs. The ciphers wanted one
     * callback; a decoder wants twelve, because a decoder is not a leaf — it
     * reads through the buffered input, writes through the fork writer and
     * names entries. They are listed rather than pulled in because pulling
     * them in would duplicate code that is resident anyway for other formats.
     *
     * The overlay does not call these directly either: `ovl_spacesaver.c`
     * DEFINES each engine symbol as a one-line forward through this table, so
     * the decoder source is compiled unmodified on both sides. */
    void     (*bitin_align)(struct UncBitIn *b);
    int32_t  (*bitin_bits_le)(struct UncBitIn *b, int n);
    void     (*bitin_init_le)(struct UncBitIn *b, struct UncBufIn *in);
    void     (*bufin_init)(struct UncBufIn *b, struct UncIO *io,
                           struct UncProgressState *ps, uint8_t *storage,
                           uint32_t cap);
    int      (*bufin_next_slow)(struct UncBufIn *b);
    void     (*entry_clear)(struct UncEntryInfo *e);
    int      (*entry_set_name)(struct UncEntryInfo *e, const uint8_t *name,
                               uint32_t len);
    void     (*entry_set_path)(struct UncEntryInfo *e, const uint8_t *path,
                               uint32_t len);
    int      (*fork_flush)(struct UncForkOut *o);
    void     (*fork_out)(struct UncForkOut *o, struct UncCtx *c, int fork,
                         int write, int ck, uint8_t *buf, uint32_t cap);
    int      (*progress_add)(struct UncProgressState *ps, uint32_t n);
    int      (*read_at)(struct UncIO *io, uint32_t pos, void *buf,
                        int32_t len);
} OverlayHost;

/* Every overlay begins with this, at offset 0 of the blob: the application
 * jumps straight to the start of the locked handle. `which` selects the
 * entry point, so one overlay can carry several. */
typedef int32_t (*OverlayEntry)(const OverlayHost *host, int32_t which,
                                void *a, void *b);

#define OVL_SELFTEST     0  /* returns 0x4F4B ('OK') — proves the mechanism */
#define OVL_CRC_VIA_HOST 1  /* calls back through the host vector           */

/* The cipher overlay's entry points. One resource has one start address, so
 * every one of these arrives through ovl_main with a `which` and a struct;
 * the shims in mac/ovl_shim.c are what the engine actually links against. */
#define OVL_CRYPT_APPLY       10
#define OVL_CRYPT_CPT         11
#define OVL_CRYPT_PACKIT_DES  12
#define OVL_CRYPT_PACKIT_XOR  13
#define OVL_CRYPT_RC4         14
#define OVL_CRYPT_SIT         15
#define OVL_CRYPT_SIT5_KEY    16
#define OVL_CRYPT_WINZIP_AES  17
#define OVL_CRYPT_XOR         18
#define OVL_CRYPT_ZIP         19
#define OVL_HMAC_FINAL        20
#define OVL_PASSWORD          21
#define OVL_RESFORK_FIND      22

/* The SpaceSaver overlay — a DECODER rather than a cipher, and the first
 * proof that a decoder can be one at all. It is 'OVLY' 129: a separate
 * resource from the ciphers, because an encrypted zip has no reason to load
 * a SpaceSaver decoder or the other way round. */
#define OVL_ID_CRYPT         128
#define OVL_ID_SPACESAVER    129
#define OVL_SPACESAVER_EXTRACT 30

/* One struct for every entry, because the entry signature is fixed. Fields
 * are named for their role rather than their type so a reader can follow a
 * call across the boundary without holding both sides in mind. */
typedef struct OvlArgs {
    void       *obj;      /* UncCrypt*, UncHmac* or UncCtx* */
    const void *in;       /* password, key or fork bytes    */
    void       *out;      /* result buffer, where there is one */
    uint32_t    len;      /* bytes in `in`, or buffer length   */
    uint32_t    pos;      /* stream position, or a second length */
    uint32_t    extra;    /* whatever one entry needs and the rest do not */
    uint32_t   *off_out;  /* unc_resfork_find's two outputs */
    uint32_t   *len_out;
} OvlArgs;

#endif

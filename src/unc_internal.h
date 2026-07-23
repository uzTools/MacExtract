/*
 * unc_internal.h — shared internals of libunclassic.
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_INTERNAL_H
#define UNC_INTERNAL_H

#include "unclassic.h"

/* ------------------------------------------------------------------ */
/* Byte-wise big-endian readers.                                      */
/* Every multi-byte field in every classic Mac format is big-endian.  */
/* These are the ONLY sanctioned way to read them: zero unaligned     */
/* dereferences (the 68000 hard-crashes on those).                    */
/* ------------------------------------------------------------------ */

static inline uint16_t unc_get_u16be(const uint8_t *p)
{
    return (uint16_t)((p[0] << 8) | p[1]);
}

static inline uint32_t unc_get_u32be(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8)  |  (uint32_t)p[3];
}

/* Little-endian variants (zip/gzip live in that world). */
static inline uint16_t unc_get_u16le(const uint8_t *p)
{
    return (uint16_t)((p[1] << 8) | p[0]);
}

static inline uint32_t unc_get_u32le(const uint8_t *p)
{
    return ((uint32_t)p[3] << 24) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[1] << 8)  |  (uint32_t)p[0];
}

/* ------------------------------------------------------------------ */
/* I/O helpers                                                        */
/* ------------------------------------------------------------------ */

/* Read exactly len bytes or fail. Returns UNC_OK, UNC_ERR_TRUNCATED
 * (clean EOF hit first) or UNC_ERR_IO. */
int unc_read_full(UncIO *io, void *buf, int32_t len);

/* Read exactly len bytes at absolute offset pos. */
int unc_read_at(UncIO *io, uint32_t pos, void *buf, int32_t len);

/* Skip len bytes forward from the current position (via seek). */
int unc_skip(UncIO *io, uint32_t len);

/* ------------------------------------------------------------------ */
/* Allocation helpers                                                 */
/* ------------------------------------------------------------------ */

static inline void *unc_alloc(UncAlloc *al, uint32_t size)
{
    return al->alloc(al->ctx, size);
}

static inline void unc_free(UncAlloc *al, void *p)
{
    if (p) al->free(al->ctx, p);
}

/* ------------------------------------------------------------------ */
/* Progress pump                                                      */
/* ------------------------------------------------------------------ */

/* Decoders call this every UNC_PROGRESS_STEP input bytes.            */
#define UNC_PROGRESS_STEP 8192u

typedef struct UncProgressState {
    UncProgress *prog;       /* may be NULL */
    uint32_t     total;      /* archive size or UNC_SIZE_UNKNOWN */
    uint32_t     done;       /* bytes consumed so far */
    uint32_t     since_tick; /* bytes since last tick */
} UncProgressState;

/* Account for n consumed input bytes; fires prog->tick at bounded
 * intervals. Returns UNC_OK or UNC_ERR_ABORTED. */
int unc_progress_add(UncProgressState *ps, uint32_t n);

/* ------------------------------------------------------------------ */
/* Buffered byte-wise input reader                                    */
/* Many decoders consume input a byte at a time; UncBufIn batches the */
/* io->read calls and drives the progress pump on each refill.        */
/* ------------------------------------------------------------------ */

typedef struct UncBufIn {
    UncIO            *io;
    UncProgressState *ps;    /* may be NULL */
    uint8_t          *buf;   /* caller-provided storage */
    uint32_t          cap;
    uint32_t          len;   /* valid bytes in buf */
    uint32_t          pos;   /* read cursor */
    int               err;   /* sticky: UNC_OK until EOF/error */
} UncBufIn;

void unc_bufin_init(UncBufIn *b, UncIO *io, UncProgressState *ps,
                    uint8_t *storage, uint32_t cap);

/* Returns next byte (0..255), or -1 with b->err set to
 * UNC_ERR_TRUNCATED (EOF), UNC_ERR_IO, or UNC_ERR_ABORTED. */
int unc_bufin_next_slow(UncBufIn *b);

static inline int unc_bufin_next(UncBufIn *b)
{
    if (b->pos < b->len) return b->buf[b->pos++];
    return unc_bufin_next_slow(b);
}

/* ------------------------------------------------------------------ */
/* CRC primitives (per-format tables live with their decoders)        */
/* ------------------------------------------------------------------ */

/* CRC-16/XMODEM: poly 0x1021, init 0, no reflection, no final xor.
 * Used by MacBinary II and BinHex 4.
 * Source: reference/XADMaster/CRC.m (XADCalculateCRC/XADCRCTable) and
 * reference/macutils/crc/ — LGPL, see NOTICE. */
uint16_t unc_crc16_xmodem(uint16_t crc, const uint8_t *buf, int32_t len);

/* CRC-32 (IEEE, reflected, poly 0x04C11DB7 => table 0xEDB88320,
 * init 0xFFFFFFFF, final xor 0xFFFFFFFF handled by caller).
 * Used by Arsenic, gzip, zip.
 * Source: reference/XADMaster/CRC.m (XADCRCReverseTable usage). */
uint32_t unc_crc32(uint32_t crc, const uint8_t *buf, int32_t len);

/* ------------------------------------------------------------------ */
/* Sink helpers                                                       */
/* ------------------------------------------------------------------ */

void unc_entry_clear(UncEntryInfo *e);
int  unc_entry_set_name(UncEntryInfo *e, const uint8_t *name, uint32_t len);

/* ------------------------------------------------------------------ */
/* Per-format sniffers and extractors                                 */
/* Each fmt_*.c exposes: a cheap content probe (bounded reads from    */
/* offset 0) and an extractor.                                        */
/* ------------------------------------------------------------------ */

typedef struct UncCtx {
    UncIO            *io;
    UncSink          *sink;
    UncAlloc         *al;
    UncProgressState  ps;
    UncOptions        opt;
} UncCtx;

int unc_macbinary_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_macbinary_extract(UncCtx *c);
int unc_applesingle_probe(const uint8_t *head, int32_t len, UncFormat *out);
int unc_appledouble_extract(UncCtx *c, UncFormat which);
int unc_binhex_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_binhex_extract(UncCtx *c);
int unc_packit_probe(const uint8_t *head, int32_t len);
int unc_packit_extract(UncCtx *c);
int unc_cpt_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_cpt_extract(UncCtx *c);
int unc_sit_probe(const uint8_t *head, int32_t len);       /* classic */
int unc_sit_extract(UncCtx *c);
int unc_sit5_probe(const uint8_t *head, int32_t len);
int unc_sit5_extract(UncCtx *c);
int unc_zip_probe(const uint8_t *head, int32_t len);
int unc_zip_extract(UncCtx *c);
int unc_gzip_probe(const uint8_t *head, int32_t len);
int unc_gzip_extract(UncCtx *c);
int unc_compressz_probe(const uint8_t *head, int32_t len);
int unc_compressz_extract(UncCtx *c);
int unc_tar_probe(const uint8_t *head, int32_t len);
int unc_tar_extract(UncCtx *c);

/* Detect-only probes */
int unc_sitx_probe(const uint8_t *head, int32_t len);
int unc_diskcopy_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_nowcompress_probe(const uint8_t *head, int32_t len);
int unc_lzh_probe(const uint8_t *head, int32_t len);

#endif /* UNC_INTERNAL_H */

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

/* The one writer: the fork ciphers work on whole 32-bit halves, and a
 * byte-wise store is the only way to put one back without an unaligned
 * dereference. */
static inline void unc_put_u32be(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24);
    p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);
    p[3] = (uint8_t)v;
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
    uint32_t     hold;       /* nonzero: accumulate, but do not tick */
} UncProgressState;

/* Account for n consumed input bytes; fires prog->tick at bounded
 * intervals, unless ps->hold is set. Returns UNC_OK or UNC_ERR_ABORTED. */
int unc_progress_add(UncProgressState *ps, uint32_t n);

/* Fire prog->tick at an explicit position, ignoring both the interval
 * check and ps->hold. Returns UNC_OK or UNC_ERR_ABORTED; tolerates a
 * NULL ps.
 *
 * This exists for decoders whose input position is a bad description of
 * their progress. Arsenic decodes a whole block from the input and only
 * then walks it into output, so the input pump runs to the end of the
 * fork and then goes silent for as long as the walk takes — minutes,
 * under the sampled index. Such a decoder sets ps->hold, keeps the
 * input pump quiet, and reports its own position interpolated across
 * the fork's input span instead. The number the UI sees stays in one
 * unit (bytes of archive consumed) and stays monotonic. */
int unc_progress_at(UncProgressState *ps, uint32_t done);

/* ------------------------------------------------------------------ */
/* Ciphers (src/unc_crypt.c)                                          */
/*                                                                    */
/* One state struct for all six, because a decoder does not care       */
/* which it is reading through: it attaches a UncCrypt to its UncBufIn */
/* and every refill is decrypted before the decoder sees a byte.       */
/* ------------------------------------------------------------------ */

enum {
    UNC_CRYPT_NONE = 0,
    UNC_CRYPT_XOR,        /* ARC: password repeated over the stream    */
    UNC_CRYPT_PIT_XOR,    /* PackIt PMa5                               */
    UNC_CRYPT_PIT_DES,    /* PackIt PMa6                               */
    UNC_CRYPT_SIT_DES,    /* StuffIt classic fork cipher               */
    UNC_CRYPT_RC4,        /* StuffIt 5                                 */
    UNC_CRYPT_ZIP,        /* PKWARE's zip stream cipher                */
    UNC_CRYPT_CPT         /* Compact Pro's 64-bit CRC keystream        */
};

#define UNC_SIT5_KEYLEN 5      /* 40 bits, all StuffIt 5 uses          */

typedef struct UncCrypt {
    int      kind;
    uint32_t blocksize;    /* 1, or 8 for the two block ciphers: what
                            * a refill must be a whole number of      */
    uint8_t  key[UNC_PASSWORD_MAX];  /* XOR / PackIt key material.
                            * A whole password long, not eight: ARC
                            * repeats the password itself, and a key cut
                            * to eight decodes a longer one to rubbish. */
    uint16_t keylen;
    uint8_t  ks[16][8];    /* DES subkeys, eight six-bit groups a round */
    uint32_t a, b, c, d;   /* StuffIt classic fork cipher state         */
    uint8_t  s[256];       /* RC4                                       */
    uint8_t  si, sj;
    uint32_t k0, k1, k2;   /* zip                                       */
    uint32_t hi, lo;       /* Compact Pro's 64-bit register             */
} UncCrypt;

void unc_crypt_xor(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen);
void unc_crypt_packit_xor(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen);
void unc_crypt_packit_des(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen);
int  unc_crypt_zip(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen);
void unc_crypt_cpt(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen);
void unc_crypt_zip_update(UncCrypt *cr, uint8_t plain);
void unc_crypt_rc4(UncCrypt *cr, const uint8_t *key, uint16_t keylen);
int  unc_crypt_sit5_key(const uint8_t *pw, uint16_t pwlen,
                        const uint8_t hash[UNC_SIT5_KEYLEN],
                        uint8_t out[UNC_SIT5_KEYLEN]);
int  unc_crypt_sit(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen,
                   const uint8_t entrykey[16], const uint8_t mkey[8]);

/* Decrypt `len` bytes in place; `pos` is buf[0]'s offset within the
 * encrypted stream (used by the two position-keyed ciphers, ignored by
 * the stateful ones, which require sequential calls). */
void unc_crypt_apply(UncCrypt *cr, uint8_t *buf, uint32_t len, uint32_t pos);

/* MD5 of a short message. Exposed for the unit tests, which grade it
 * against published digests. */
void unc_md5(const uint8_t *msg, uint32_t len, uint8_t out[16]);

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
    uint32_t          lenfed; /* total bytes pulled from io so far */
    uint32_t          limit; /* max bytes to pull from io (default ~0u):
                              * bounds a substream (e.g. one compressed
                              * fork) so corrupt data cannot read past
                              * its end into unrelated bytes */
    UncCrypt         *crypt; /* NULL: the stream is plaintext. Set AFTER
                              * unc_bufin_init and BEFORE the first read:
                              * a refill already in the buffer is not
                              * revisited. Every refill is decrypted as
                              * it arrives, so no decoder above this
                              * knows the difference. */
    int               err;   /* sticky: UNC_OK until EOF/error */
} UncBufIn;

void unc_bufin_init(UncBufIn *b, UncIO *io, UncProgressState *ps,
                    uint8_t *storage, uint32_t cap);

/* Returns next byte (0..255), or -1 with b->err set to
 * UNC_ERR_TRUNCATED (EOF), UNC_ERR_IO, or UNC_ERR_ABORTED. */
int unc_bufin_next_slow(UncBufIn *b);

/* Absolute position in the stream, and forward-only seeking to one. */
void unc_bufin_init_mem(UncBufIn *b, const uint8_t *mem, uint32_t len);
uint32_t unc_bufin_tell(const UncBufIn *b);
int unc_bufin_skip_to(UncBufIn *b, uint32_t abs);

static inline int unc_bufin_next(UncBufIn *b)
{
    if (b->pos < b->len) return b->buf[b->pos++];
    return unc_bufin_next_slow(b);
}

/* ------------------------------------------------------------------ */
/* MSB-first bit reader over UncBufIn                                 */
/* (Classic Mac compressors emit bits high-to-low within each byte;   */
/* source: reference/macutils/macunpack/de_huffman.c getbit_be and    */
/* reference/XADMaster/CSInputBuffer.h.)                              */
/* ------------------------------------------------------------------ */

typedef struct UncBitIn {
    UncBufIn *in;
    uint32_t  bitbuf;   /* up to 24 buffered bits, right-aligned */
    int32_t   nbits;
    int       le;       /* LSB-first bit order within each byte
                         * (StuffIt method 13; everything else is MSB) */
    int       err;      /* sticky */
} UncBitIn;

void unc_bitin_init(UncBitIn *b, UncBufIn *in);
void unc_bitin_init_le(UncBitIn *b, UncBufIn *in);
/* Next single bit (0/1), or -1 with err set. */
int unc_bitin_bit(UncBitIn *b);
/* Next n bits (n <= 24) as an MSB-first integer, or -1 with err set.
 * (MSB mode only.) */
int32_t unc_bitin_bits(UncBitIn *b, int n);
/* Next n bits assembled LSB-first (first bit read = bit 0), n <= 24.
 * (LE mode only; CSInputNextBitStringLE semantics.) */
int32_t unc_bitin_bits_le(UncBitIn *b, int n);
/* Discard buffered bits up to the next byte boundary. */
void unc_bitin_align(UncBitIn *b);
/* Bytes consumed from the underlying io up to the current bit
 * position (byte-aligned reads only; call unc_bitin_align first). */
uint32_t unc_bitin_bytepos(const UncBitIn *b);

/* ------------------------------------------------------------------ */
/* Bit-serialized Huffman (prefix) trees                              */
/* Used by PackIt and StuffIt method 3: serialized depth-first, one   */
/* bit per node — 1 = leaf followed by 8 value bits, 0 = internal     */
/* node (zero branch first, then one branch).                         */
/* Source: reference/XADMaster/XADStuffItHuffmanHandle.m (parseTree)  */
/* and reference/macutils/macunpack/de_huffman.c (read_sub_tree).     */
/* ------------------------------------------------------------------ */

/* macutils sizes its node pool at 515 "because StuffIt Classic needs
 * more than the needed 511"; internal nodes only need child slots. */
#define UNC_HUFF_MAX_INTERNAL 320

typedef struct UncHuff {
    /* child[side][node]: value >= 0 is a node index, < 0 is a leaf
     * holding symbol -(value+1). */
    int16_t child[2][UNC_HUFF_MAX_INTERNAL];
    int16_t nnodes;
    int16_t root;       /* node index, or negative leaf code */
} UncHuff;

/* Build from the serialized form. Iterative (explicit stack), caps
 * the node count; returns UNC_OK or UNC_ERR_CORRUPT/bit error. */
int unc_huff_read_tree(UncHuff *h, UncBitIn *bi);

/* Decode one symbol (0..255), or -1 with bi->err/corrupt. */
int unc_huff_decode(const UncHuff *h, UncBitIn *bi);

/* ------------------------------------------------------------------ */
/* Canonical (code-length) Huffman codes                              */
/* Codes assigned in (length, symbol) order, shortest code all-zeros; */
/* MSB-first. Compact Pro serializes 4-bit lengths and permits        */
/* incomplete trees ("Compactor allows unused trailing codes").       */
/* Source: reference/XADMaster/XADPrefixCode.m                        */
/* (initWithLengths:shortestCodeIsZeros:YES) and                      */
/* reference/macutils/macunpack/cpt.c (cpt_readHuff) — LGPL, NOTICE.  */
/* ------------------------------------------------------------------ */

#define UNC_CANON_MAX_SYMS 384
#define UNC_CANON_MAX_BITS 31   /* method-13 tables reach 18; the
                                 * serialized form could go higher */

typedef struct UncCanon {
    uint16_t count[UNC_CANON_MAX_BITS + 1]; /* codes per bit length */
    uint32_t first[UNC_CANON_MAX_BITS + 1]; /* first code value per length */
    int16_t  sym[UNC_CANON_MAX_SYMS];       /* symbols in (len,sym) order */
    int16_t  maxlen;
} UncCanon;

/* Build from per-symbol code lengths (0 = unused). Incomplete codes
 * are allowed; over-subscribed ones return UNC_ERR_CORRUPT. */
int unc_canon_build(UncCanon *c, const uint8_t *lengths, int32_t nsyms);

/* Decode one symbol, or -1 with bi->err set / on an invalid code. */
int unc_canon_decode(const UncCanon *c, UncBitIn *bi);

/* ------------------------------------------------------------------ */
/* Unix compress(1)-compatible LZW (see unc_lzw.c)                    */
/* StuffIt method 2 (14-bit, block mode) and .Z (params from header). */
/* ------------------------------------------------------------------ */

typedef struct UncLzw {
    UncBufIn *in;
    UncAlloc *al;           /* kept for the growth safety net */
    uint8_t  *mem;          /* single allocation, see unc_lzw_init */
    uint16_t *parent;       /* [capsymbols] */
    uint8_t  *chr;          /* [capsymbols] */
    uint8_t  *chain;        /* [capsymbols] reversed-chain staging */
    uint32_t  bitbuf;       /* LSB-first bit accumulator */
    int32_t   nbits;
    /* maxsymbols is the DECLARED ceiling (1 << maxbits) and governs
     * decode semantics — code-width growth and the table-full point —
     * so it must not be lowered. capsymbols is what is allocated. */
    int32_t   capsymbols;
    int32_t   maxsymbols, numsymbols, reserved;
    int32_t   prevsymbol;
    int32_t   symbolsize;   /* current code width in bits */
    uint32_t  symbolcounter;
    int32_t   chainlen, chainpos;
    int       blockmode;
} UncLzw;

/* insize is the compressed size of the stream in bytes, or 0 when it is
 * not known; it only sizes the initial allocation and never changes the
 * decoded output. See unc_lzw.c. */
int  unc_lzw_init(UncLzw *z, UncAlloc *al, UncBufIn *in,
                  int maxbits, int blockmode, uint32_t insize);
void unc_lzw_free(UncLzw *z, UncAlloc *al);
int32_t unc_lzw_read(UncLzw *z, uint8_t *out, int32_t want);

/* ------------------------------------------------------------------ */
/* CRC primitives (per-format tables live with their decoders)        */
/* ------------------------------------------------------------------ */

/* CRC-16/XMODEM: poly 0x1021, init 0, no reflection, no final xor.
 * Used by MacBinary II and BinHex 4.
 * Source: reference/XADMaster/CRC.m (XADCalculateCRC/XADCRCTable) and
 * reference/macutils/crc/ — LGPL, see NOTICE. */
uint16_t unc_crc16_xmodem(uint16_t crc, const uint8_t *buf, int32_t len);

/* CRC-16/ARC: poly 0xA001 (reflected), init 0, no final xor.
 * Used by StuffIt classic (header + fork CRCs).
 * Source: reference/XADMaster/CRC.m (XADCRCTable_a001).
 * Check value: 0xBB3D over "123456789". */
uint16_t unc_crc16_arc(uint16_t crc, const uint8_t *buf, int32_t len);

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

/* Set e->name to an already-formed '/'-separated path verbatim (no
 * component swap: the bytes were produced by unc_entry_path_append or
 * come from a format whose names natively use '/', like zip/tar). */
void unc_entry_set_path(UncEntryInfo *e, const uint8_t *path, uint32_t len);

/* Append one Mac path component to e->name ('/'-separated path),
 * applying the classic reversible '/'->':' swap to the component
 * (':' cannot occur in an HFS name, '/' can — see DECISIONS.md M4).
 * Truncates at UNC_NAME_MAX. */
void unc_entry_path_append(UncEntryInfo *e, const uint8_t *comp, uint32_t len);

/* ------------------------------------------------------------------ */
/* Per-format sniffers and extractors                                 */
/* Each fmt_*.c exposes: a cheap content probe (bounded reads from    */
/* offset 0) and an extractor.                                        */
/* ------------------------------------------------------------------ */

/* Reading a segmented archive by the addresses it actually stores.
 *
 * Only formats that address themselves as (part, offset within that
 * part) need this — in practice zip, whose central directory stores
 * both numbers per entry. NULL for an archive read out of one file,
 * which is every other case; a decoder that finds a non-zero part
 * number with no map in hand is looking at a set it was handed one
 * member of, and should say UNC_ERR_SEGMENTED rather than guess.
 *
 * The pairs are kept as pairs. An earlier version flattened the set
 * into one address space and translated, which is the obvious thing to
 * do and costs a pass over every part to learn the sizes that make the
 * translation possible — on a one-drive Mac, a disk swap each, before
 * a byte is extracted. Keeping the pairs needs no sizes at all:
 * position, read, and roll into the next part at EOF (DECISIONS.md
 * 2026-08-09). */
typedef struct UncSegMap {
    void     *ctx;
    /* Position the stream at `off` within part `part` (1-based). An
     * `off` past that part's end rolls into the following ones, so a
     * caller may skip forward without knowing where the cuts fell.
     * Reads afterwards cross part boundaries invisibly. */
    int      (*seek_part)(void *ctx, int part, uint32_t off);
    /* Skip `n` bytes forward from wherever the stream is now. */
    int      (*skip)(void *ctx, uint32_t n);
    /* Length of part `part`, opening it if that is the only way to
     * tell. UNC_SIZE_UNKNOWN if it cannot be had. */
    uint32_t (*part_size)(void *ctx, int part);
    uint16_t  nparts;
} UncSegMap;

/* Where the password in hand came from. A rejected one moves the state
 * along rather than being asked for twice. */
enum {
    UNC_PW_UNSET = 0,   /* nothing tried yet                          */
    UNC_PW_STATIC,      /* opt.password is in c->pw                    */
    UNC_PW_TRIED,       /* opt.password was tried and rejected         */
    UNC_PW_ASKED,       /* opt.ask supplied what is in c->pw           */
    UNC_PW_NONE         /* the host has nothing (more) to offer        */
};

typedef struct UncCtx {
    UncIO            *io;
    UncSink          *sink;
    UncAlloc         *al;
    const UncSegMap  *segmap;   /* NULL unless the archive is joined */
    UncProgressState  ps;
    UncOptions        opt;
    /* The password for this archive, fetched the first time an entry
     * needs one and kept for the rest of the walk: every format here
     * keys every entry from the same password. */
    uint8_t           pw[UNC_PASSWORD_MAX];
    uint16_t          pwlen;
    uint8_t           pwstate;
    int               pwattempt;
} UncCtx;

/* Get a password to try. `again` = the last one was rejected. Returns
 * UNC_OK with c->pw/c->pwlen valid, or UNC_ERR_PASSWORD when the host
 * has none left. */
int unc_password(UncCtx *c, int again);

/* ------------------------------------------------------------------ */
/* Compact Pro's two decode stages, shared with DiskDoubler method 8,   */
/* which is Compact Pro compression inside a DiskDoubler container      */
/* (Source: XADDiskDoublerParser.m case 8). The only difference is the  */
/* Huffman block size: 0x1fff0 there, 0xfff0 here.                      */
/* ------------------------------------------------------------------ */

typedef struct CptRle {
    /* DiskDoubler method 8 reuses this stage and needs the archive's own
     * CRC-16/ARC over the decompressed bytes; Compact Pro itself does not
     * ask for it. See fmt_dd.c. */
    uint16_t crc16;
    int      want_crc16;
    UncCtx  *c;
    UncFork  fork;
    uint32_t remaining;   /* output bytes still owed */
    uint32_t crc;         /* running fork CRC (shared across forks) */
    int      state;
    uint8_t  saved;       /* last emitted byte (repeat source) */
    uint8_t *obuf;        /* staging buffer */
    uint32_t ocap, olen;
    int      quiet;       /* decode but write nothing: what a password
                           * candidate is graded by, since Compact Pro
                           * stores no verifier and the entry CRC is the
                           * only evidence a key was right */
    int      err;         /* sticky */
} CptRle;

typedef struct CptLzh {
    UncCanon lit, len, off;
} CptLzh;

void unc_cpt_rle_start(CptRle *r, UncCtx *c, UncFork fork, uint32_t outlen,
                       uint32_t crc, uint8_t *obuf, uint32_t ocap);
int unc_cpt_lzh_fork(CptRle *rle, UncBufIn *in, CptLzh *hz,
                     uint8_t *window, uint32_t blocksize);
int unc_cpt_rle_fork(CptRle *rle, UncBufIn *in, uint32_t complen);
int unc_cpt_rle_flush(CptRle *r);


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
int unc_cptseg_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_cptseg_describe(UncIO *io, UncSegmentDesc *desc);
int unc_cptseg_match(const UncSegmentDesc *desc, const uint8_t *head,
                     int32_t len);
int unc_sit_probe(const uint8_t *head, int32_t len);       /* classic */
int unc_sit_extract(UncCtx *c);

/* One part of a StuffIt segmented set (fmt_sitseg.c). unc_sitseg_emit
 * writes the single joined entry, reading its forks from `base`:
 * UNC_SEG_HEAD for a lone part, 0 for the stream unc_segment.c joins.
 * `data_first` says which fork the stream begins with — StuffIt puts
 * the resource fork first, DiskDoubler's `SPLT` the data fork. */
int unc_sitseg_probe(const uint8_t *head, int32_t len);
int unc_sitseg_extract(UncCtx *c);
int unc_sitseg_emit(UncCtx *c, const UncSegmentDesc *desc, uint32_t base,
                    int data_first);
int unc_sitseg_describe(UncIO *io, UncSegmentDesc *desc);

/* One part of a DiskDoubler `SPLT` set (fmt_ddseg.c). unc_ddseg_payload
 * is what the joiner asks a freshly opened part: how many of its bytes
 * are payload, given that the part declares it and also re-proves that
 * it belongs to this set and is this part. */
int unc_ddseg_probe(const uint8_t *head, int32_t len);
int unc_ddseg_extract(UncCtx *c);
int unc_ddseg_describe(UncIO *io, UncSegmentDesc *desc);
int unc_ddseg_match(const UncSegmentDesc *desc, const uint8_t *head,
                    int32_t len);
int unc_ddseg_payload(const UncSegmentDesc *desc, const uint8_t *head,
                      int32_t len, int part, uint32_t size,
                      uint32_t *payload);
/* The CRC-16/XMODEM the part stores over its own payload. The joiner
 * checks it against a running CRC when a part happens to be read
 * straight through, which is the common case and not a guarantee
 * (unc_segment.c). */
uint16_t unc_ddseg_stored_crc(const uint8_t *head);

/* One part of a spanned ("split") zip set (fmt_zipseg.c). The probe
 * needs the io handle because the only part that identifies itself
 * unambiguously does so at the END of the file. */
int unc_zipseg_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_zipseg_extract(UncCtx *c);
int unc_zipseg_describe(UncIO *io, UncSegmentDesc *desc);

/* The one backwards scan for a zip's end-of-central-directory record,
 * shared by the describe path and both extraction paths. Reads through
 * `rd` so the caller decides what "offset" means — a position in a file
 * for a whole archive, a position in the LAST PART for a segmented one.
 * `end` is one past the last byte that may be scanned. */
typedef int (*UncZipReadAt)(void *ctx, uint32_t off, void *buf, int32_t len);
int unc_zip_scan_eocd(void *ctx, UncZipReadAt rd, uint32_t end, uint32_t *at);

/* One StuffIt fork: seek to `at`, decode `complen` -> `outlen` bytes
 * with the given method, verify the CRC-16/ARC (`wantcrc`; method 15
 * verifies its own internal CRC-32 instead). Shared by the classic
 * and SIT5 containers. Returns a per-entry status. */
int unc_sit_decode_fork(UncCtx *c, UncFork fork, uint32_t at,
                        uint32_t complen, uint32_t outlen, int method,
                        uint16_t wantcrc, uint8_t *iobuf, uint32_t iocap,
                        uint8_t *obuf, uint32_t ocap, UncCrypt *cr);

/* Arsenic (method 15) core, in sit_arsenic.c. */
int unc_arsenic_decode(UncBufIn *in, UncAlloc *al, uint32_t outlen,
                       int (*put)(void *ctx, uint8_t b), void *pctx);

/* Raw-deflate decode via vendored zlib (unc_inflate.c). Decodes one
 * complete deflate stream from `in`, leaving the reader positioned on
 * the first byte after it. maxout: expected output size cap, or
 * UNC_SIZE_UNKNOWN. *crc (if non-NULL) is updated as CRC-32 over the
 * output. Output chunks go to emit(). */
int unc_inflate_raw(UncBufIn *in, UncAlloc *al,
                    uint8_t *obuf, uint32_t ocap,
                    uint32_t maxout, uint32_t *produced, uint32_t *crc,
                    int (*emit)(void *ctx, const uint8_t *p, int32_t n),
                    void *ectx);
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
int unc_dd_extract(UncCtx *c);
int unc_now_extract(UncCtx *c);
int unc_superdisk_extract(UncCtx *c);
int unc_spacesaver_extract(UncCtx *c);

/* uuencode, including UUTool's two-fork shape (fmt_uu.c). The probe
 * needs no io: a uu file identifies itself in its first lines. */
int unc_uu_probe(const uint8_t *head, int32_t len);
int unc_uu_extract(UncCtx *c);

/* ARC / ArcMac (fmt_arc.c). The probe reads the next header to place
 * this one, so it takes io. */
int unc_arc_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_arc_extract(UncCtx *c);

/* Detect-only probes */
int unc_sitx_probe(const uint8_t *head, int32_t len);
int unc_diskcopy_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_nowcompress_probe(const uint8_t *head, int32_t len);
int unc_superdisk_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_spacesaver_probe(const uint8_t *head, int32_t len);
int unc_applelink_probe(const uint8_t *head, int32_t len);
uint32_t unc_superdisk_single_body(const uint8_t *head, int32_t len);
int unc_diskdoubler_probe(const uint8_t *head, int32_t len);
int unc_lzh_probe(const uint8_t *head, int32_t len);

#endif /* UNC_INTERNAL_H */

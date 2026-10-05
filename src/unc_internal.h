/*
 * unc_internal.h — shared internals of libmacextract.
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_INTERNAL_H
#define UNC_INTERNAL_H

#include "macextract.h"

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

/* The largest single read the engine expresses. UncIO.read takes an
 * int32_t length, so a buffer to be filled in one call is bounded here
 * — the same number as UNC_MAC_MAX and a different idea from it. */
#define UNC_READ_MAX 0x7FFFFFFFu

/* Read exactly len bytes or fail. Returns UNC_OK, UNC_ERR_TRUNCATED
 * (clean EOF hit first) or UNC_ERR_IO. */
int unc_read_full(UncIO *io, void *buf, int32_t len);

/* Read exactly len bytes at absolute offset pos. */
int unc_read_at(UncIO *io, unc_off_t pos, void *buf, int32_t len);

/* The container's size as a format that addresses 32 bits sees it.
 * Clamped to UNC_U32_MAX, which is exactly as tight a bound as the
 * true size for every offset such a format can form — and which is
 * UNC_SIZE_UNKNOWN, so a container past 4 GiB reads to these parsers
 * as one whose length the host did not state. That is the same
 * leniency a streamed container gets, and none of them can address
 * far enough to be misled by it. A format that CAN address further
 * (zip, tar) calls io->size directly and carries unc_off_t. */
uint32_t unc_io_size32(UncIO *io);

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
/* One state struct for all seven, because a decoder does not care     */
/* which it is reading through: it attaches a UncCrypt to its UncBufIn */
/* and every refill is decrypted before the decoder sees a byte.       */
/* ------------------------------------------------------------------ */

enum {
    UNC_CRYPT_NONE = 0,
    UNC_CRYPT_XOR,        /* ARC: password repeated over the stream    */
    UNC_CRYPT_PIT_XOR,    /* PackIt PMa5                               */
    UNC_CRYPT_PIT_DES,    /* PackIt PMa6                               */
    UNC_CRYPT_SIT_DES,    /* StuffIt classic fork cipher               */
    UNC_CRYPT_SIT_CBC,    /* StuffIt 2.x `DES`: standard DES in CBC     */
    UNC_CRYPT_SIT_NEWDE,  /* StuffIt 2.x `NewDE`: StuffItDES in CBC     */
    UNC_CRYPT_RC4,        /* StuffIt 5                                 */
    UNC_CRYPT_ZIP,        /* PKWARE's zip stream cipher                */
    UNC_CRYPT_CPT,        /* Compact Pro's 64-bit CRC keystream        */
    UNC_CRYPT_AES         /* WinZip's AES, in counter mode             */
};

/* HMAC-SHA1: two saved SHA-1 states, so the outer hash never re-keys.
 * Only WinZip's AES uses it — for the key derivation and for the ten
 * bytes of authentication code an AES entry ends with. */
typedef struct UncSha1 {
    uint32_t h[5];
    uint32_t len;          /* bytes hashed so far */
    uint8_t  buf[64];
    uint32_t have;
} UncSha1;

typedef struct UncHmac {
    UncSha1 in, out;
} UncHmac;

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
    /* WinZip AES: the expanded key (15 rounds at most), the counter and
     * its keystream block, and the authentication state. */
    uint8_t  rk[16 * 15];
    int      aesrounds;
    uint8_t  ctr[16], ctrbuf[16], ctrpos;
    UncHmac  hmac;
    /* The one 2 KB table the two DES variants and Compact Pro's CRC-64
     * read a round or a byte through — built at key setup into a heap
     * block the caller frees with unc_crypt_free, from 544 B of S boxes
     * and P. Resident as three const tables it was 6 KB of A5 world on
     * every extraction, for entries nothing in the corpus has
     * (DECISIONS.md 2026-09-19). Preserved across crypt_clear; the
     * ciphers that need none leave it NULL. */
    uint32_t *tab;
    int      tabkind;
} UncCrypt;

/* Before the first key: no cipher, no table. Every host of a UncCrypt
 * calls this once, because the struct usually sits inside a buffer that
 * was never zeroed. */
static inline void unc_crypt_init(UncCrypt *cr)
{
    cr->kind = UNC_CRYPT_NONE;
    cr->tab = NULL;
    cr->tabkind = 0;
}

/* Give the table back. Safe on a UncCrypt that never needed one. */
void unc_crypt_free(UncCrypt *cr, UncAlloc *al);

void unc_crypt_xor(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen);
void unc_crypt_packit_xor(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen);
/* The three that build a table take the allocator and can fail with
 * UNC_ERR_MEM — per entry, like any other allocation. */
int  unc_crypt_packit_des(UncCrypt *cr, UncAlloc *al, const uint8_t *pw,
                          uint16_t pwlen);
int  unc_crypt_zip(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen);
int  unc_crypt_cpt(UncCrypt *cr, UncAlloc *al, const uint8_t *pw,
                   uint16_t pwlen);
void unc_crypt_zip_update(UncCrypt *cr, uint8_t plain);
void unc_crypt_rc4(UncCrypt *cr, const uint8_t *key, uint16_t keylen);
int  unc_crypt_sit5_key(const uint8_t *pw, uint16_t pwlen,
                        const uint8_t hash[UNC_SIT5_KEYLEN],
                        uint8_t out[UNC_SIT5_KEYLEN]);
/* `scheme` picks what the FORK is encrypted with — the key derivation
 * above it is the same for all three, measured 2026-10-02 on archives
 * StuffIt Deluxe 2.0.1 and 3.5.1 wrote (FORMATS.md, *The three ways
 * 2.0.1 encrypts*). */
#define UNC_SIT_SCHEME_FEEDBACK 0   /* 3.5's built-in: the 8-byte XOR  */
#define UNC_SIT_SCHEME_DES      1   /* 2.x `DES`: standard DES, CBC    */
#define UNC_SIT_SCHEME_NEWDE    2   /* 2.x `NewDE`: StuffItDES, CBC    */
int  unc_crypt_sit(UncCrypt *cr, UncAlloc *al, const uint8_t *pw,
                   uint16_t pwlen, const uint8_t entrykey[16],
                   const uint8_t mkey[8], int scheme);
int  unc_crypt_winzip_aes(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen,
                          const uint8_t *salt, int keybytes,
                          const uint8_t verifier[2]);
void unc_hmac_update(UncHmac *m, const uint8_t *p, uint32_t n);
/* Test hooks; nothing in the engine calls these. */
void unc_hmac_init_test(UncHmac *m, const uint8_t *key, uint32_t keylen);
void unc_pbkdf2_test(const uint8_t *pw, uint32_t pwlen,
                     const uint8_t *salt, uint32_t saltlen,
                     uint32_t iterations, uint8_t *out, uint32_t outlen);
void unc_aes_encrypt_test(UncCrypt *cr, const uint8_t *key, int keybytes,
                          uint8_t block[16]);
void unc_hmac_final(UncHmac *m, uint8_t out[20]);

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

/* The bytes that are already in the buffer: *p is set to the first of
 * them and their count returned, which is 0 when the buffer is spent —
 * the caller's cue to go through unc_bufin_next, refill and ask again.
 * unc_bufin_drop consumes n of them. Only fmt_binhex.c uses this, to
 * take a whole 64-character line in one pass rather than pay the bounds
 * test and the cursor store once per character. */
static inline uint32_t unc_bufin_span(const UncBufIn *b, const uint8_t **p)
{
    *p = b->buf + b->pos;
    return b->len - b->pos;
}

static inline void unc_bufin_drop(UncBufIn *b, uint32_t n)
{
    b->pos += n;
}

/* The next byte WITHOUT consuming it, or -1 at EOF (which sets the
 * sticky error, as reading it would have). One byte of lookahead is
 * enough for the only caller: unc_readline, which has to take CRLF as a
 * single terminator. */
static inline int unc_bufin_peek(UncBufIn *b)
{
    int c;
    if (b->pos < b->len) return b->buf[b->pos];
    c = unc_bufin_next_slow(b);
    if (c < 0) return -1;
    b->pos--;                       /* next_slow refilled, then consumed */
    return c;
}

/* ------------------------------------------------------------------ */
/* Text line reader (unc_util.c)                                      */
/*                                                                    */
/* CR, LF and CRLF all end a line, and a last line need not be        */
/* terminated at all — and the one a btoa file saved on a Mac needed  */
/* (FORMATS.md, "btoa").                                              */
/* Source: reference/macutils/hexbin/readline.c, which states that    */
/* rule. Marked 2026-10-06: it was a live citation without the marker */
/* the inventory check reads, which is the shape of defect            */
/* DECISIONS.md 2026-09-27 (*the check that tested the wrong thing*)  */
/* normalised in six other files.                                     */
/* Unlike the readers inside fmt_uu.c and fmt_btoa.c, this            */
/* one consumes CRLF as ONE terminator instead of letting the LF come  */
/* back as an empty line: those two formats may ignore a blank line    */
/* anywhere, and MIME may not — a blank line is where a part's headers */
/* stop and its body starts.                                          */
/*                                                                    */
/* Fills buf (cap bytes, NUL-terminated) and *len with the line, minus */
/* the terminator; a longer line is truncated and the rest skipped.    */
/* *eof is set once the stream ends. Returns UNC_ERR_TRUNCATED when    */
/* there was nothing left to read at all.                             */
/* ------------------------------------------------------------------ */
int unc_readline(UncBufIn *in, uint8_t *buf, int32_t cap, int32_t *len,
                 int *eof);

/* ------------------------------------------------------------------ */
/* MSB-first bit reader over UncBufIn                                 */
/* (Classic Mac compressors emit bits high-to-low within each byte.)  */
/* Source: reference/deark/src/deark-dbuf.c (MIT) — de_bitreader and  */
/* de_bitbuf_lowlevel, the same design in the same two modes: a right- */
/* aligned buffer refilled a byte at a time, the next bits taken with  */
/* >> nbits_in_bitbuf & mask in MSB mode and off the bottom in LSB     */
/* mode, and de_bitreader_skip_to_byte_boundary where this has         */
/* unc_bitin_align. It was macutils' de_huffman.c (getbit_be) and     */
/* XADMaster's CSInputBuffer.h until 2026-09-27.                       */
/* ------------------------------------------------------------------ */

typedef struct UncBitIn {
    UncBufIn *in;
    uint32_t  bitbuf;   /* up to 32 buffered bits. MSB mode: the next bit
                         * is at position nbits-1, so bits are right-
                         * aligned and a refill shifts in at the bottom.
                         * LE mode: the next bit is at position 0 and a
                         * refill ors in above.                          */
    int32_t   nbits;
    int       le;       /* LSB-first bit order within each byte
                         * (StuffIt method 13; everything else is MSB) */
    int       err;      /* sticky */
} UncBitIn;

void unc_bitin_init(UncBitIn *b, UncBufIn *in);
void unc_bitin_init_le(UncBitIn *b, UncBufIn *in);
/* Next single bit (0/1), or -1 with err set.
 *
 * Inline for the same reason unc_bufin_next is: this is called once per
 * BIT by every canonical-Huffman format (Compact Pro, DiskDoubler, Now
 * Compress, StuffIt methods 3/13, LZH) and several times per symbol by
 * Arsenic's renormalisation, and seven calls in eight need nothing but
 * the buffered byte. Callgrind put 2.1-13.7 % of various runs in the
 * call itself.
 *
 * The REFILL is inline too, and that is not incidental: a version whose
 * refill was an out-of-line unc_bitin_bit_slow() measured 3.1-6.6 %
 * WORSE than the plain function on Compact Pro, DiskDoubler and Now
 * Compress, because the opaque call forced bitbuf/nbits/le to be
 * reloaded around every eighth bit — and unc_canon_decode compiles in
 * the same translation unit unc_bitin_bit used to live in, where gcc
 * was already inlining the whole of it with that state in registers. */
static inline int unc_bitin_bit(UncBitIn *b)
{
    if (b->nbits == 0) {
        int byte = unc_bufin_next(b->in);
        if (byte < 0) { b->err = b->in->err; return -1; }
        b->bitbuf = (uint32_t)byte;
        b->nbits = 8;
    }
    b->nbits--;
    if (b->le) {
        int bit = (int)(b->bitbuf & 1u);
        b->bitbuf >>= 1;
        return bit;
    }
    return (int)((b->bitbuf >> b->nbits) & 1u);
}

/* Top up bitbuf to at least `n` bits (n <= 24) from bytes ALREADY in the
 * UncBufIn's window, and say whether it got there.
 *
 * "Already in the window" is the whole design. It never calls into io, so
 * it cannot pull a byte across a substream's `limit`, cannot set the
 * sticky error early, and cannot turn a stream that ends exactly on a
 * symbol boundary into a truncation. At a window boundary it simply
 * fails and the caller takes its bit-at-a-time path, which is correct
 * whatever is buffered. The two functions that convert a bit position
 * back into a byte position — unc_bitin_align and unc_bitin_bytepos —
 * count whole buffered bytes rather than discarding them, so a caller
 * that byte-aligns and asks where it is gets the same answer it did when
 * nothing was ever buffered ahead. */
static inline int unc_bitin_fill(UncBitIn *b, int n)
{
    UncBufIn *in = b->in;
    while (b->nbits < n) {
        uint32_t byte;
        if (in->pos >= in->len) return 0;
        byte = in->buf[in->pos++];
        if (b->le) b->bitbuf |= byte << b->nbits;
        else       b->bitbuf = (b->bitbuf << 8) | byte;
        b->nbits += 8;
    }
    return 1;
}
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
/* Used by PackIt, StuffIt method 3 and DiskDoubler method 4:         */
/* serialized depth-first, one bit per node — 1 = leaf followed by 8  */
/* value bits, 0 = internal node (zero branch first, then one).       */
/* Source since 2026-09-20: docs/formats/serialized-huffman-tree.md,  */
/* this project's own description, derived from the three formats'    */
/* output by experiment (tools/derive_huffman_tree.py). NOTICE has    */
/* said so since that day; this comment still named parseTree and     */
/* read_sub_tree until 2026-09-26.                                    */
/* ------------------------------------------------------------------ */

/* macutils sizes its node pool at 515 "because StuffIt Classic needs
 * more than the needed 511"; internal nodes only need child slots. */
#define UNC_HUFF_MAX_INTERNAL 320

/* The same trade on the other Huffman decoder, and the same answer:
 * 8 -> 10 is 8.7 % of derived-EmpireBuilderDemo.sit and 11 only 1.2 %
 * more. Entries are uint16_t here (the symbol is stored), so the table
 * is 2 KB. The length is packed into the low four bits, which holds any
 * K up to 15. */
#define UNC_HUFF_FAST_BITS 10

typedef struct UncHuff {
    /* child[side][node]: value >= 0 is a node index, < 0 is a leaf
     * holding symbol -(value+1). */
    int16_t child[2][UNC_HUFF_MAX_INTERNAL];
    int16_t nnodes;
    int16_t root;       /* node index, or negative leaf code */
    /* Next UNC_HUFF_FAST_BITS bits -> (symbol << 4) | length, or 0 when
     * the code is longer than that and the walk below has to run. The
     * symbol IS stored here, unlike the canonical decoder's table: this
     * tree is arbitrary, so there is no arithmetic that recovers it.
     * Eight bits and 255 symbols fit a uint16_t with room for the
     * length. Zero throughout when the root is a bare leaf, because
     * that case must consume NO bits and a table entry cannot say so. */
    uint16_t fast[1u << UNC_HUFF_FAST_BITS];
    int16_t  fastok;
} UncHuff;

/* Build from the serialized form. Iterative (explicit stack), caps
 * the node count; returns UNC_OK or UNC_ERR_CORRUPT/bit error. */
int unc_huff_read_tree(UncHuff *h, UncBitIn *bi);

/* Decode one symbol (0..255), or -1 with bi->err/corrupt. */
int unc_huff_decode(const UncHuff *h, UncBitIn *bi);

/* ------------------------------------------------------------------ */
/* Canonical (code-length) Huffman codes                              */
/* Codes assigned in (length, symbol) order, shortest code all-zeros; */
/* MSB-first. Compact Pro serializes 4-bit lengths, two to a byte     */
/* behind a count byte (docs/formats/compact-pro.md, correction 1),   */
/* and writes trailing codes it never uses, so an incomplete set is   */
/* legal — see unc_huffman.c, which says where that comes from.       */
/* Source since 2026-09-19: reference/notes/rfc1951.txt section       */
/* 3.2.2 and reference/notes/puff.c. NOTICE has said so since that    */
/* day; this comment still named XADPrefixCode.m and cpt_readHuff     */
/* until 2026-09-26.                                                  */
/* ------------------------------------------------------------------ */

#define UNC_CANON_MAX_SYMS 384
#define UNC_CANON_MAX_BITS 31   /* method-13 tables reach 18; the
                                 * serialized form could go higher */

/* Bits looked up at once by unc_canon_decode's fast path, and the size of
 * the table that answers them: 1 byte per entry, so 1 KB.
 *
 * TEN rather than eight, measured. Eight covers every code of eight bits
 * or fewer, which for a 256-symbol alphabet is most of the symbols
 * decoded — but Now Compress codes 0x122 of them and DiskDoubler DDn 257,
 * and there the tail past eight bits is where the time was. Going 8 -> 10
 * is another 17.0 % of a Now Compress run, 8.0 % of DiskDoubler and 7.8 %
 * of Compact Pro; 11 adds 2.7 % more and 12 a further 0.7 %, for two and
 * four times the table. The build cost is 1 << K writes per code table,
 * and archives of many small entries were checked for it: keyAhead.cpt
 * got FASTER at 10, so the fill is not what those pay. */
#define UNC_CANON_FAST_BITS 10
#define UNC_CANON_FAST_MASK ((1u << UNC_CANON_FAST_BITS) - 1u)

typedef struct UncCanon {
    uint16_t count[UNC_CANON_MAX_BITS + 1]; /* codes per bit length */
    uint32_t first[UNC_CANON_MAX_BITS + 1]; /* first code value per length */
    uint16_t cbase[UNC_CANON_MAX_BITS + 1]; /* sym[] index length l starts at */
    int16_t *sym;                           /* symbols in (len,sym) order */
    int16_t  maxlen;
    /* Next UNC_CANON_FAST_BITS bits -> the length of the code that
     * starts there, or 0 when it is longer than that and the
     * bit-at-a-time walk has to run. The symbol itself is not stored:
     * codes of one length are consecutive from first[l], so it is
     * sym[cbase[l] + (code - first[l])], which is two shifts and a
     * subtract against the 256 extra bytes a symbol table would cost. */
    uint8_t  fastlen[1u << UNC_CANON_FAST_BITS];
    int16_t  symstore[UNC_CANON_MAX_SYMS];  /* what `sym` points at unless
                                             * the caller supplied storage */
} UncCanon;

/* Build from per-symbol code lengths (0 = unused). Incomplete codes
 * are allowed; over-subscribed ones return UNC_ERR_CORRUPT. */
int unc_canon_build(UncCanon *c, const uint8_t *lengths, int32_t nsyms);

/* The same, over symbol storage the caller owns: for an alphabet
 * larger than UNC_CANON_MAX_SYMS (LZH's 510 literals). */
int unc_canon_build_ext(UncCanon *c, const uint8_t *lengths, int32_t nsyms,
                        int16_t *symbuf, int32_t symcap);

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
    uint8_t  *len;          /* [capsymbols] string length, 255 = "or more" */
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
    /* A string longer than the caller's buffer is handed over in
     * pieces: pendsym/pendn/pende say which one and how far in. */
    int32_t   pendsym, pendn, pende;
    int32_t   pendtop;      /* the string ends with topbyte (see unc_lzw.c) */
    uint8_t   topbyte;
    uint8_t   lastfirst;    /* first byte of the string last handed over */
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
 * Source: reference/notes/binhex40_lewis.txt, section "CRCs". The
 * table is checked against that polynomial by
 * tools/check_crc_tables.py; see src/unc_util.c. */
uint16_t unc_crc16_xmodem(uint16_t crc, const uint8_t *buf, int32_t len);

/* CRC-16/ARC: poly 0xA001 (reflected), init 0, no final xor.
 * Used by StuffIt classic (header + fork CRCs).
 * Source: the polynomial itself — deark and lhasa each build this
 * table from 0xA001, as tools/check_crc_tables.py does here.
 * Check value: 0xBB3D over "123456789". */
uint16_t unc_crc16_arc(uint16_t crc, const uint8_t *buf, int32_t len);

/* CRC-32 (IEEE, reflected, poly 0x04C11DB7 => table 0xEDB88320,
 * init 0xFFFFFFFF, final xor 0xFFFFFFFF handled by caller).
 * Used by Arsenic, gzip, zip.
 * Source: reference/notes/zip_appnote.txt, which states the
 * polynomial and the 0xdebb20e3 residue. */
uint32_t unc_crc32(uint32_t crc, const uint8_t *buf, int32_t len);

/* The initial value that definition calls for. The final xor is the
 * same number and is written `~crc` at the call sites; neither is a
 * ceiling, and naming this one keeps it out of a search for one. */
#define UNC_CRC32_INIT 0xFFFFFFFFu

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
 * Truncates at UNC_NAME_MAX, setting e->name_truncated. */
void unc_entry_path_append(UncEntryInfo *e, const uint8_t *comp, uint32_t len);

/* Is this per-entry status one that ends the whole walk? A decoder
 * failure belongs to its entry and the next one is still worth trying;
 * a dead sink, a user who cancelled and an unreadable file do not get
 * better by reading on. Every archive walk asks this, and it was
 * written out at nineteen sites before it was a function. */
static inline int unc_fatal(int err)
{
    return err == UNC_ERR_SINK || err == UNC_ERR_ABORTED ||
           err == UNC_ERR_IO;
}

/* ------------------------------------------------------------------ */
/* A folder path being walked                                         */
/*                                                                    */
/* What an entry table needs while it descends: components joined      */
/* with '/', the classic '/'->':' swap applied per component, and a    */
/* note of the depth at which a FOLDER name was first cut to fit.      */
/* DiskDoubler, Now Compress and SuperDisk! each wrote this out        */
/* (DECISIONS.md 2026-08-27, the scaffolding audit); StuffIt and       */
/* Compact Pro do the same job through unc_entry_path_append, which is */
/* the other half of it and is what unc_path_leaf ends in.             */
/*                                                                    */
/* Components are pushed and popped by LENGTH, never by re-scanning    */
/* for a separator, and there is no recursion anywhere in it.          */
/* ------------------------------------------------------------------ */

/* All three formats that use this chose 24 independently. */
#define UNC_PATH_MAXDEPTH 24

struct UncCtx;

typedef struct UncPath {
    uint8_t  buf[UNC_NAME_MAX + 1];
    uint16_t len;
    uint16_t stack[UNC_PATH_MAXDEPTH];
    int      depth;
    /* Depth at which a FOLDER name was first cut to fit, 0 for none.
     * A leaf under it carries a path that is not the archive's even
     * when the leaf itself fitted. */
    int      truncdepth;
    /* The same path UNCUT: its length, saturating at 65,535, and — when
     * the host offered UncOptions.long_name — its bytes, written there
     * as the walk descends. `full` is both the length and the write
     * offset, so a pop restores the buffer as well as the count. The
     * context is held for that buffer alone and may be NULL. */
    struct UncCtx *c;
    uint16_t full;
    uint16_t fullstack[UNC_PATH_MAXDEPTH];
} UncPath;

void unc_path_init(UncPath *p, struct UncCtx *c);

/* Descend into `name`. UNC_ERR_CORRUPT at UNC_PATH_MAXDEPTH with
 * NOTHING changed, so a caller that would rather carry on than fail
 * may ignore the result — which is what two of the three formats do,
 * landing the entries under the parent instead of refusing the
 * archive. */
int  unc_path_push(UncPath *p, const uint8_t *name, uint32_t nlen);

void unc_path_pop(UncPath *p);

/* The full path of a leaf, without disturbing the stack. Where the path
 * does not fit UNC_NAME_MAX it reports the WHOLE length in
 * e->name_full_len, and hands the whole name to the host through
 * UncOptions.long_name when there is room for it (name_truncated 2). */
void unc_path_leaf(const UncPath *p, UncEntryInfo *e,
                   const uint8_t *name, uint32_t nlen);

/* ------------------------------------------------------------------ */
/* Per-format sniffers and extractors                                 */
/*                                                                    */
/* Each fmt_*.c exposes a cheap content probe and an extractor, and   */
/* both have ONE shape:                                               */
/*                                                                    */
/*   UncFormat probe(const uint8_t *head, int32_t len, UncIO *io);    */
/*   int       extract(UncCtx *c);                                    */
/*                                                                    */
/* The probe reads `head` — the first UNC_SNIFF_HEAD bytes, already   */
/* read — and answers with the format it claims or UNC_FORMAT_UNKNOWN.*/
/* `io` is there for the probes that need more than the head (a       */
/* MacBinary CRC, tar at 257, a Compact Pro trailer, a zip's EOCD);   */
/* the rest take it and ignore it, which is the price of unc_sniff    */
/* being an ORDERED TABLE rather than a chain of twenty-eight `if`s.  */
/* Returning the format rather than a flag is what lets one probe     */
/* answer for several: AppleSingle and AppleDouble share a magic, and */
/* fmt_foreign.c answers for ten PC formats at once.                  */
/* ------------------------------------------------------------------ */

struct UncCtx;
typedef UncFormat (*UncProbe)(const uint8_t *head, int32_t len, UncIO *io);
typedef int (*UncExtract)(struct UncCtx *c);

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

/* Hand the host the WHOLE name of an entry whose name had to be cut,
 * where the format still has it (UncOptions.long_name). Does nothing
 * without a buffer; sets e->name_truncated to 2 when it filled one. */
void unc_entry_long_name(UncCtx *c, UncEntryInfo *e, const uint8_t *name,
                         uint32_t len);

/* Get a password to try. `again` = the last one was rejected. Returns
 * UNC_OK with c->pw/c->pwlen valid, or UNC_ERR_PASSWORD when the host
 * has none left. */
int unc_password(UncCtx *c, int again);

/* Copy `size` bytes from the CURRENT io position straight to the sink,
 * in `bufsz` chunks, pumping progress. For a fork that is stored rather
 * than compressed, which is every fork of MacBinary, AppleSingle and a
 * StuffIt segment. Positioning before and padding after are the
 * caller's. */
int unc_copy_fork(UncCtx *c, UncFork fork, uint32_t size,
                  uint8_t *buf, uint32_t bufsz);

/* ------------------------------------------------------------------ */
/* RLE90                                                              */
/*                                                                    */
/* An escape byte followed by a count: ESC 0 is a literal escape, and  */
/* ESC n means the byte before it stands n times in total, so n-1      */
/* more follow the one already out. Five formats here run it —         */
/* StuffIt method 1, BinHex, DiskDoubler method 3, and ARC both        */
/* before and after its LZH layer — and each had written it out.       */
/*                                                                    */
/* They agreed on everything except ESC 1, a run of one that no        */
/* encoder emits: four call it corrupt, and DiskDoubler's reference    */
/* (macutils' dd_rle, whose `while (--b > 0)` simply emits nothing)    */
/* lets it pass. That is the `strict` flag, and it is the whole of the */
/* difference — which is worth knowing, because five copies could not  */
/* say whether it was a decision or a slip (DECISIONS.md 2026-08-27,   */
/* the fork writer and the filter).                                   */
/*                                                                    */
/* Source: reference/notes/rle90_theunarchiver.md — the format's own   */
/* published description, which states all four rules this implements: */
/* `0x90 N` for N nonzero is N-1 repeats of the last byte, `0x90 0x00` */
/* is a literal 0x90, anything else is a literal, and `0x90 0x01`      */
/* "seems to either be a no-op or illegal" — which is the `strict`     */
/* flag above, named as an open question by the description and        */
/* settled here by measuring five implementations. Re-cited from       */
/* XADRLE90Handle.m on 2026-09-21: the page was in reference/notes/    */
/* the whole time (OPEN_ITEMS.md, *What is still XADMaster's*).        */
/* ------------------------------------------------------------------ */

#define UNC_RLE90_ESC  0x90
#define UNC_RLE90_MORE (-256)   /* nothing to emit; feed another raw byte */

typedef struct UncRle90 {
    uint8_t  last;      /* the byte a run repeats                      */
    uint8_t  esc;       /* an escape is waiting for its count byte     */
    uint8_t  strict;    /* nonzero: ESC 1 is UNC_ERR_CORRUPT           */
    uint16_t run;       /* bytes still owed by the run in progress     */
} UncRle90;

static inline void unc_rle90_init(UncRle90 *r, int strict)
{
    r->last = 0;
    r->esc = 0;
    r->strict = (uint8_t)(strict != 0);
    r->run = 0;
}

/* The two halves are inline and take no callback, which is the whole
 * shape of this: the caller reads its own source and writes its own
 * output, so nothing here is reached through a pointer. Measured —
 * a callback version of the same filter cost a .hqx run 15 %, because
 * BinHex puts every byte it decodes through it (DECISIONS.md
 * 2026-08-27, the fork writer and the filter). */

/* The next byte of a run in progress, or UNC_RLE90_MORE if none is. */
static inline int unc_rle90_take(UncRle90 *r)
{
    if (!r->run) return UNC_RLE90_MORE;
    r->run--;
    return r->last;
}

/* Feed one RAW byte. Returns the byte to emit, UNC_RLE90_MORE when
 * there is nothing yet (the escape was consumed, or a lenient run of
 * one produced nothing), or UNC_ERR_CORRUPT. A run that starts here
 * yields its first byte; unc_rle90_take drains the rest.
 *
 * After a raw byte that was the escape, r->esc stays set until the
 * count arrives — which is how a caller tells a stream that ended
 * cleanly from one that ended holding an escape. DiskDoubler is the
 * only reader that has to make that distinction. */
static inline int unc_rle90_feed(UncRle90 *r, int b)
{
    if (r->esc) {
        r->esc = 0;
        if (b == 0) { r->last = UNC_RLE90_ESC; return UNC_RLE90_ESC; }
        if (b == 1) return r->strict ? UNC_ERR_CORRUPT : UNC_RLE90_MORE;
        r->run = (uint16_t)(b - 2);
        return r->last;
    }
    if (b == UNC_RLE90_ESC) { r->esc = 1; return UNC_RLE90_MORE; }
    r->last = (uint8_t)b;
    return b;
}

/* ------------------------------------------------------------------ */
/* Fork output                                                        */
/*                                                                    */
/* Every decoder here ends the same way: stage the bytes it produces  */
/* so the sink sees runs rather than bytes, keep a checksum over      */
/* them, and write them where the entry says. Eight formats wrote     */
/* that out separately (DECISIONS.md 2026-08-27, the fork writer      */
/* and the filter).                                                   */
/*                                                                    */
/* What is deliberately NOT here is per-byte work only one format     */
/* knows about: DiskDoubler's delta transform and running sum, btoa's */
/* three whole-stream checksums, and — the one worth stating — the    */
/* CAP at the entry's declared length. Four formats have one and in   */
/* every one of them the same counter is also the decode loop's own   */
/* condition, so hoisting it here would have bought nothing and cost  */
/* every other format a compare per byte in its hottest loop. Those   */
/* formats keep their own put(), which ends in unc_fork_put.          */
/* ------------------------------------------------------------------ */

/* Which checksum the writer keeps over what it produces. A format    */
/* whose checksum is per-byte, or is taken over something other than  */
/* the output, keeps its own and asks for NONE.                       */
enum {
    UNC_CK_NONE = 0,
    UNC_CK_CRC16_ARC,   /* StuffIt classic, LZH, ARC                  */
    UNC_CK_CRC32,       /* Compact Pro                                */
    UNC_CK_CRC32_16     /* Compact Pro inside a DiskDoubler container:
                         * the CRC-32 it always keeps, and the
                         * CRC-16/ARC that container checks against   */
};

/* Staging size for a writer whose buffer is not the caller's own. */
#define UNC_STAGE 512u

/* The staging a format allocates for itself: UncBufIn's input side,
 * and the output side of a decoder that hands back runs. It was a
 * bare 4096 in eleven files and named in one, which is how a size
 * nobody chose becomes a size nobody can change. A format that wants
 * a different one says so with a constant of its own. */
#define UNC_IOBUF 4096u

/* UNC_HOT — compile this ONE function for speed, whatever the rest of the
 * translation unit is built at. Carried by StuffIt's two hot method
 * decoders, the LZW and Huffman primitives, unc_crc16_arc, and since
 * 2026-09-19 Compact Pro's unc_cpt_lzh_fork, cpt_rle_push and the two
 * functions its stages were fused into (-14.8 % of that format's engine
 * time for +1,028 B when the marks went on, tick probe).
 *
 * The Macintosh application builds at -Os because the application is
 * resident and the floor target is a 1 MB machine. That is right for the
 * ~40 functions in a file and wrong for the two or three an extraction
 * actually spends its time in: on a 7 MHz 68000, -O3 on four whole files
 * took derived-EmpireBuilderDemo.sit from 70.4 s to 52.5 s and cost
 * 8,850 B of text, of which the largest single item was
 * unc_huff_read_tree — a function that is 0.44 % of that run
 * (mac/CMakeLists.txt has the table; DECISIONS.md 2026-08-30).
 *
 * Marking the functions instead of the files also puts them under the
 * differential suite: every one of the 932 fixtures on Linux then decodes
 * through the same aggressively optimised code the Mac runs, which a flag
 * that lives in mac/CMakeLists.txt cannot arrange.
 *
 * GCC only. Clang parses `optimize` and ignores it with a warning, and no
 * other compiler this builds under has an equivalent worth guessing at. */
#if defined(__GNUC__) && !defined(__clang__)
#define UNC_HOT __attribute__((optimize("O3")))
#else
#define UNC_HOT
#endif

/* UNC_NOINLINE — keep this function out of its caller. Used where a cold
 * branch's body would otherwise make its CALLER too big to inline into a
 * hot loop, which measured worse than the branch itself ever cost
 * (fmt_cpt.c, cpt_rle_fill). */
#if defined(__GNUC__)
#define UNC_NOINLINE __attribute__((noinline))
#else
#define UNC_NOINLINE
#endif

typedef struct UncForkOut {
    UncCtx  *c;
    UncFork  fork;       /* destination, unless `split` is set        */
    uint8_t *buf;        /* staging, owned by the caller              */
    uint32_t cap, len;
    uint32_t written;    /* bytes already handed to the sink          */
    uint8_t  ck;
    /* 0: decode and checksum, write nothing. WHAT that means is the
     * caller's: `test_only` alone for some formats, that and
     * `list_only` for others, and Compact Pro's password grading needs
     * a third answer. Four spellings, and they are now four visible
     * arguments rather than four flush functions that looked alike. */
    uint8_t  write;
    uint8_t  split;      /* nonzero: route by the four spans below    */
    uint16_t crc16;
    uint32_t crc32;
    /* Two forks inside ONE decoded stream, as absolute positions in
     * it: MacLHA compresses a MacBinary payload and ArcMac splits at
     * one offset. Only meaningful while `split` is set. */
    uint32_t dstart, dend, rstart, rend;
    /* What a StuffIt 2.0 Optimizer did to the fork before it was
     * compressed, undone here at flush time and BEFORE the checksum —
     * because the entry's CRC is over the ORIGINAL bytes wherever the
     * module is exactly reversible (FORMATS.md, *What an Optimizer did
     * to the fork*). Both are off for every other format and cost one
     * test per flush.
     *
     * `delta`: the fork is a byte-wise difference; undo it with a
     * running sum carried across flushes in `dacc`. That is the whole
     * of what `Sound 1` and `Photoshop 1` do, and their two 'DCMP'
     * resources are byte-identical apart from the name and the id.
     *
     * `skip`: drop this many bytes from the FRONT of the stream,
     * accumulating them big-endian into `skipval` so the format can
     * check them — `MacPaint 1` puts its remnant's own length there,
     * and four bytes shifted into a long is both the smallest code and
     * the value the caller wants. */
    uint8_t  delta, dacc, skip;
    uint32_t skipval;
} UncForkOut;

/* `write` and `ck` as above; `buf`/`cap` are the caller's staging.
 * A format that seeds its checksum (Compact Pro carries one CRC-32
 * across both forks) assigns o->crc32 afterwards. */
void unc_fork_out(UncForkOut *o, UncCtx *c, UncFork fork, int write,
                  int ck, uint8_t *buf, uint32_t cap);

/* Route what follows to two forks by position in the decoded stream. */
void unc_fork_split(UncForkOut *o, uint32_t dstart, uint32_t dend,
                    uint32_t rstart, uint32_t rend);

int unc_fork_flush(UncForkOut *o);

/* Bytes produced so far, staged and written together. */
static inline uint32_t unc_fork_pos(const UncForkOut *o)
{
    return o->written + o->len;
}

/* One decoded byte. Stays inline: this is a per-byte call in the
 * hottest loop every format has, and the 68000 pays for a real one
 * (DECISIONS.md 2026-08-24, the performance pass). */
static inline int unc_fork_put(UncForkOut *o, uint8_t b)
{
    o->buf[o->len++] = b;
    if (o->len == o->cap) return unc_fork_flush(o);
    return UNC_OK;
}

/* A run of decoded bytes: staged in pieces the buffer can hold, and
 * flushed as each fills. The shape the run-callback decoders below
 * hand their output over in. */
int unc_fork_write(UncForkOut *o, const uint8_t *p, uint32_t n);

/* How the LZ decoders below hand their output back: a RUN at a time,
 * straight out of the decoder's own window, rather than one byte at a
 * time through a pointer. A per-byte callback was 6 % of an LZH or
 * -lh1- run on Linux (callgrind, 2026-09-18) and an indirect call is
 * dearer still on a 68000; the window is already the staging, so a run
 * costs no memory. Returns UNC_OK or a per-entry error, which stops
 * the decoder. */
typedef int (*UncPutRun)(void *ctx, const uint8_t *p, uint32_t n);

/* ------------------------------------------------------------------ */
/* Compact Pro's two decode stages, shared with DiskDoubler method 8,   */
/* which is Compact Pro compression inside a DiskDoubler container      */
/* THAT METHOD 8 IS COMPACT PRO'S STAGES IS MEASURED, since            */
/* 2026-09-27: all 7 method-8 forks in reach decode byte for byte      */
/* against the oracle's sha256 with a reader written from Compact      */
/* Pro's three published wiki pages alone (tools/derive_dd8.py).       */
/* AND SO IS THE BLOCK SIZE, since 2026-10-06, by the archives          */
/* themselves: a wrong size yields the right NUMBER of bytes and the    */
/* wrong ones, and a method-8 fork's header states a CRC-16/ARC over    */
/* the decoded result. Over the 9 forks in reach, 0xfff0 is the only    */
/* size of eleven swept whose output satisfies that stored CRC — no     */
/* oracle and no reference implementation in the loop, only the file    */
/* (tools/derive_dd8.py; DECISIONS.md 2026-10-06, *the other half of    */
/* that citation*). It took two wild forks, 210,944 and 242,237 B,      */
/* to reach a flush at all: until they were found no stream here        */
/* crossed even 0x400 cost units and every size above that read every   */
/* fork identically.                                                    */
/* The only difference from Compact Pro is the                          */
/* Huffman block size: 0x1fff0 for Compact Pro (fmt_cpt.c, CPT_BLOCK,   */
/* and the published description agrees) and 0xfff0 for DiskDoubler     */
/* (fmt_dd.c, at the call). This comment had the two the WRONG WAY      */
/* ROUND until 2026-09-20, when a fetched specification disagreed with  */
/* it and the code turned out to be right.                              */
/* ------------------------------------------------------------------ */

typedef struct CptRle {
    /* The CRC-32 is Compact Pro's and runs across BOTH forks, so the
     * caller seeds out.crc32; the CRC-16/ARC is only asked for by the
     * DiskDoubler container that borrows this stage, which says so by
     * setting out.ck to UNC_CK_CRC32_16. See fmt_dd.c. */
    UncForkOut out;
    uint32_t remaining;   /* output bytes still owed */
    int      state;
    uint8_t  saved;       /* last emitted byte (repeat source) */
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


UncFormat unc_macbinary_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_macbinary_extract(UncCtx *c);
UncFormat unc_applesingle_probe(const uint8_t *head, int32_t len,
                                UncIO *io);
int unc_appledouble_extract(UncCtx *c);
UncFormat unc_binhex_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_binhex_extract(UncCtx *c);
UncFormat unc_packit_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_packit_extract(UncCtx *c);

UncFormat unc_sqp_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_sqp_extract(UncCtx *c);
UncFormat unc_cpt_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_cpt_extract(UncCtx *c);
UncFormat unc_cptseg_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_cptseg_describe(UncIO *io, UncSegmentDesc *desc);
int unc_cptseg_match(const UncSegmentDesc *desc, const uint8_t *head,
                     int32_t len);
UncFormat unc_sit_probe(const uint8_t *head, int32_t len, UncIO *io);       /* classic */
int unc_sit_extract(UncCtx *c);

/* One part of a StuffIt segmented set (fmt_sitseg.c). unc_sitseg_emit
 * writes the single joined entry, reading its forks from `base`:
 * UNC_SEG_HEAD for a lone part, 0 for the stream unc_segment.c joins.
 * `data_first` says which fork the stream begins with — StuffIt puts
 * the resource fork first, DiskDoubler's `SPLT` the data fork. */
UncFormat unc_sitseg_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_sitseg_extract(UncCtx *c);
int unc_sitseg_emit(UncCtx *c, const UncSegmentDesc *desc, uint32_t base,
                    int data_first);
int unc_sitseg_describe(UncIO *io, UncSegmentDesc *desc);
int unc_sitseg_match(const UncSegmentDesc *desc,
                     const uint8_t *head, int32_t len);

/* One part of a DiskDoubler `SPLT` set (fmt_ddseg.c). unc_ddseg_payload
 * is what the joiner asks a freshly opened part: how many of its bytes
 * are payload, given that the part declares it and also re-proves that
 * it belongs to this set and is this part. */
UncFormat unc_ddseg_probe(const uint8_t *head, int32_t len, UncIO *io);
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
UncFormat unc_zipseg_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_zipseg_extract(UncCtx *c);
int unc_zipseg_describe(UncIO *io, UncSegmentDesc *desc);

/* The one backwards scan for a zip's end-of-central-directory record,
 * shared by the describe path and both extraction paths. Reads through
 * `rd` so the caller decides what "offset" means — a position in a file
 * for a whole archive, a position in the LAST PART for a segmented one.
 * `end` is one past the last byte that may be scanned. */
typedef int (*UncZipReadAt)(void *ctx, uint32_t off, void *buf, int32_t len);
int unc_zip_scan_eocd(void *ctx, UncZipReadAt rd, uint32_t end, uint32_t *at);

/* Does this archive hold an encrypted entry? Answered from its own directory
 * before anything is decoded, and only for the formats that keep a per-entry
 * flag somewhere a reader can walk: Compact Pro and zip. src/unc_encinfo.c.
 *
 * UNKNOWN is the answer for every other format and for a directory that could
 * not be read, and a caller must treat it as YES. StuffIt and StuffIt 5 flag
 * encryption per entry with no directory to consult, PackIt in each block's
 * magic, and ARC not at all. */
#define UNC_ENC_NO       0
#define UNC_ENC_YES      1
#define UNC_ENC_UNKNOWN (-1)
int unc_archive_encrypted(UncFormat fmt, UncIO *io);

/* One StuffIt fork: seek to `at`, decode `complen` -> `outlen` bytes
 * with the given method, verify the CRC-16/ARC (`wantcrc`; method 15
 * verifies its own internal CRC-32 instead). Shared by the classic
 * and SIT5 containers. Returns a per-entry status.
 *
 * `optdec` says what a StuffIt 2.0 Optimizer left behind and how to put
 * it back — one of fmt_sit.c's SIT_OPTDEC_* values, and 0 for every
 * caller that has no such thing. It can change what is STORED as well
 * as what comes out: `MacPaint 1` declares the original length and
 * stores a shorter remnant. */
int unc_sit_decode_fork(UncCtx *c, UncFork fork, uint32_t at,
                        uint32_t complen, uint32_t outlen, int method,
                        int optdec, uint16_t wantcrc,
                        uint8_t *iobuf, uint32_t iocap,
                        uint8_t *obuf, uint32_t ocap, UncCrypt *cr);

/* The payload a StuffIt 2.0 `JPEG Lossy` Optimizer stores: C-Cube's
 * JPEG inside a TIFF behind an 80-byte module header (sit_ccube.c).
 * `stored` is the entry's STORED fork, whole — that Optimizer's output
 * is already compressed and StuffIt keeps it at method 0, which is the
 * only shape this handles. Writes `outlen` bytes of planar RGB to
 * `fork` and returns a per-entry status. */
int unc_ccube_decode(UncCtx *c, UncFork fork, const uint8_t *stored,
                     uint32_t storedlen, uint32_t outlen,
                     uint8_t *obuf, uint32_t ocap);

/* LHarc's -lh1- coder (unc_lzah.c): a 4 KB-window LZSS whose literals
 * and lengths come from an adaptive Huffman tree of 314 leaves. Shared
 * by StuffIt classic's method 5 and LZH's -lh1-, which are the same
 * scheme — XADMaster instantiates one handle for both. `bi` is an
 * MSB-first reader the caller has already positioned; `put` receives
 * the decoded bytes in runs (UncPutRun) and returns UNC_OK or a
 * per-entry error. */
/* LHarc's -lh2-: both codes adaptive, and the position tree grows with
 * the output. src/unc_lzdyn.c. */
int unc_lzdyn_decode(UncAlloc *al, UncBitIn *bi, uint32_t outlen,
                     UncPutRun put, void *pctx);

/* LHarc's -lh3-: a static code rebuilt per block. src/unc_lzdyn.c. */
int unc_lzst0_decode(UncAlloc *al, UncBitIn *bi, uint32_t outlen,
                     UncPutRun put, void *pctx);

/* Adaptive-Huffman LZSS, in three dialects that share a tree of 314
 * leaves and differ only in what the codes above 0xff mean and in what
 * the window starts as:
 *
 *   UNC_LZAH_LH1      LHarc's -lh1- and StuffIt method 5: 0x100 is a
 *                     match of 3, and the window carries XADMaster's
 *                     preload (value runs, ramps, zeros, spaces).
 *                     Source: reference/XADMaster/
 *                     XADLZHDynamicHandle.m, resetLZSSHandle, which
 *                     is where the preload is written — the same citation
 *                     src/unc_lzah.c carries, marked here too on
 *                     2026-10-06.
 *   UNC_LZAH_TRIMMED  ARC 7.x's "Trimmed": 0x100 is a STOP code, 0x101
 *                     is a match of 3 (so 3..59, one shorter than
 *                     -lh1-), and the window starts as zeros.
 *                     Source: reference/deark/foreign/lzhuf.h,
 *                     lzhuf_Decode_init's is_arc_trimmed branch, and
 *                     modules/arc.c's decompressor_trimmed, which
 *                     chains RLE90 after it.
 *
 * The window fill is uniform in both, so LZHUF's ring-buffer start of
 * N-F does not appear here: a match reaching back before the first byte
 * reads the fill byte wherever the cursor started.
 *
 * A third mode, UNC_LZAH_DART, was Apple's LZHUF over a window of
 * zeros; it left with DART on 2026-09-25 (DECISIONS.md, *the disk
 * images that found another home*). */
#define UNC_LZAH_LH1      0
#define UNC_LZAH_TRIMMED  1

int unc_lzah_decode(UncAlloc *al, UncBitIn *bi, uint32_t outlen, int mode,
                    UncPutRun put, void *pctx);

/* Arsenic (method 15) core, in sit_arsenic.c. Writes into the fork
 * writer directly, and has it keep the CRC-32 the stream ends with:
 * `f` comes back set to UNC_CK_CRC32, flushed, and checked. It used to
 * take a per-byte callback and CRC each byte through unc_crc32, and the
 * two calls were 10 % of a fast-path run (callgrind, 2026-09-18). */
int unc_arsenic_decode(UncBufIn *in, UncAlloc *al, uint32_t outlen,
                       UncForkOut *f);

/* Method 14 (sit14.c): LZSS over a window of up to 256 KB, both
 * alphabets Huffman-coded per block. Writes into the fork writer, which
 * keeps the container's CRC-16 — unlike Arsenic, this method carries no
 * check of its own. */
int unc_sit14_decode(UncBufIn *in, UncAlloc *al, uint32_t outlen,
                     UncForkOut *f);

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
UncFormat unc_sit5_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_sit5_extract(UncCtx *c);
UncFormat unc_zip_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_zip_extract(UncCtx *c);
UncFormat unc_gzip_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_gzip_extract(UncCtx *c);
UncFormat unc_compressz_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_compressz_extract(UncCtx *c);
UncFormat unc_tar_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_tar_extract(UncCtx *c);
int unc_dd_extract(UncCtx *c);
int unc_now_extract(UncCtx *c);
int unc_superdisk_extract(UncCtx *c);
int unc_spacesaver_extract(UncCtx *c);

/* uuencode, including UUTool's two-fork shape (fmt_uu.c). The probe
 * needs no io: a uu file identifies itself in its first lines. */
UncFormat unc_btoa_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_btoa_extract(UncCtx *c);
UncFormat unc_uu_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_uu_extract(UncCtx *c);

/* The line-level half of uuencode, shared with fmt_mime.c: a uuencoded
 * body inside a multipart is decoded by the MIME walk, and decoding it
 * a second time there is how two transcriptions of one format come to
 * disagree. UNC_UU_LINE_MAX is a full line (45 payload bytes = 60
 * characters, plus the length character and slack); a decoded line
 * needs UNC_UU_DEC_MAX. */
#define UNC_UU_LINE_MAX   96
#define UNC_UU_DEC_MAX    48    /* ((45/3)+1)*3, mu_convert's obuf bound */

/* Decoded bytes (0..45), or -1 for a line that cannot be one. */
int32_t unc_uu_decode_line(const uint8_t *buf, int32_t len, uint8_t *out);
/* Can this line be uu data at all? Its first character declares how
 * many bytes it encodes, so the length has to agree. */
int unc_uu_line_is_data(const uint8_t *p, int32_t len);
/* Where the name sits inside a "begin" line. */
void unc_uu_name_span(const uint8_t *buf, int32_t len, int32_t *soff,
                      int32_t *eoff);

/* base64 (fmt_b64.c), and the streaming decoder MIME shares with it.
 *
 * Source: reference/mpack/decode.c from64() and
 * reference/deark/modules/xfer.c do_base64_internal(), which agree on
 * every byte that matters: characters outside the alphabet are skipped
 * rather than refused (mailers wrap, indent and re-flow these streams),
 * '=' ends the data, and a group left part-decoded yields the bytes it
 * implies — two characters one byte, three characters two. */
typedef struct UncB64 {
    uint8_t q[4];        /* six-bit values of the group so far */
    int     n;
    int     done;        /* '=' seen: the data ended there */
} UncB64;

void unc_b64_reset(UncB64 *b);
/* Bytes written to out (0..3). Skips what is not in the alphabet. */
int  unc_b64_feed(UncB64 *b, int ch, uint8_t out[3]);
/* The tail of a group left over at end of stream (0..2 bytes). */
int  unc_b64_flush(UncB64 *b, uint8_t out[3]);

UncFormat unc_b64_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_b64_extract(UncCtx *c);

/* MIME messages (fmt_mime.c). The probe scans past the mail headers,
 * which are longer than the sniff window, so it takes io. */
/* Shared with fmt_mimeseg.c: the header and parameter rules, once. */
int32_t unc_mime_ci_prefix(const uint8_t *s, int32_t len, const char *pfx);
uint32_t unc_mime_param(const uint8_t *h, int32_t hlen, const char *key,
                        uint8_t *out, uint32_t cap, int *trunc);
void unc_mime_ctype_of(const uint8_t *h, int32_t hlen, uint8_t *out,
                       uint32_t cap);
int unc_mime_is_header(const uint8_t *s, int32_t len);

UncFormat unc_mime_probe(const uint8_t *head, int32_t len, UncIO *io);
/* The same probe, restricted to a message that declares a multipart
 * with a boundary — parts the walk can ENUMERATE. unc_sniff runs this
 * one before uuencode, btoa and BinHex, whose scans would otherwise
 * claim a whole message on the strength of one part of it and drop the
 * rest (DECISIONS.md 2026-08-29, a part that hid its message). */
UncFormat unc_mime_probe_multipart(const uint8_t *head, int32_t len,
                                   UncIO *io);
int unc_mime_extract(UncCtx *c);

/* ARC / ArcMac (fmt_arc.c). The probe reads the next header to place
 * this one, so it takes io. */
/* message/partial: a message split across several FILES (fmt_mimeseg.c).
 * The parts are mail messages, so the probe reads on through io past
 * the sniff window, as the MIME probe does. */
UncFormat unc_mimeseg_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_mimeseg_describe(UncIO *io, UncSegmentDesc *desc);
/* This part's OWN header length — they differ from part to part, which
 * no other scheme's do — and the check that it is the part the joiner
 * asked for. */
int unc_mimeseg_head(const UncSegmentDesc *d, UncIO *io, int part,
                     uint32_t size, uint32_t *out);

UncFormat unc_arc_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_arc_extract(UncCtx *c);

/* LZH / LHA (fmt_lzh.c). */
UncFormat unc_lzh_probe(const uint8_t *head, int32_t len, UncIO *io);
int unc_lzh_extract(UncCtx *c);

/* Foreign archives (fmt_foreign.c): PC-side formats named but never
 * extracted. One probe for all of them; returns the format or
 * UNC_FORMAT_UNKNOWN. Head buffer only, no io. */
UncFormat unc_foreign_probe(const uint8_t *head, int32_t len,
                            UncIO *io);

/* Detect-only probes */
UncFormat unc_sitx_probe(const uint8_t *head, int32_t len, UncIO *io);
UncFormat unc_nowcompress_probe(const uint8_t *head, int32_t len, UncIO *io);
UncFormat unc_superdisk_probe(const uint8_t *head, int32_t len, UncIO *io);
UncFormat unc_spacesaver_probe(const uint8_t *head, int32_t len, UncIO *io);
uint32_t unc_superdisk_single_body(const uint8_t *head, int32_t len);
UncFormat unc_diskdoubler_probe(const uint8_t *head, int32_t len, UncIO *io);

#endif /* UNC_INTERNAL_H */

/*
 * fmt_superdisk.c — Alysis SuperDisk! auto-expanding files (`.X`, `.x`).
 *
 *   Source: the format's own decoders, disassembled. There is no
 *   published layout and no other implementation — XADMaster does not
 *   know the format and `unar` stops at the envelope.
 *
 *     - the container walk, the block chain and the built-in methods
 *       1..9: `CODE 2` of the self-extracting application in the corpus
 *       (`super-disk-utility.hqx`), routines at 0x2e4 (records), 0x5f4
 *       (blocks), 0x6b4 (method dispatch), 0x72e (the context
 *       predictor) and 0x884 (Huffman);
 *     - the module chain: `CODE 2` of `alysis-disk-expander-12.hqx`
 *       at 0x476;
 *     - method 11 "SlowFastB": the "SuperDisk! Add-In Module" the
 *       second archive carries in its own data fork, which is also
 *       `Cmpr` 23 of the Disk Expander extension inside it.
 *
 *   How each was read, and what was measured on an emulated Mac rather
 *   than deduced, is DECISIONS.md, "SuperDisk!, read out of SuperDisk!".
 *
 * An archive is 8 bytes nobody reads, an optional chain of 68k
 * decompressor modules, then a stream of 8-byte-tagged records: 0x29
 * opens a folder, 0x2a closes one, 0x28 is a file and 0x27 ends the
 * archive. A file's forks follow its record inline, DATA FIRST, each a
 * chain of blocks of at most 32 KB of output.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define SD_TAG_END    0x27u
#define SD_TAG_FILE   0x28u
#define SD_TAG_DIR    0x29u
#define SD_TAG_UPDIR  0x2Au

#define SD_MAXDEPTH   24u
#define SD_BLOCKMAX   0x8000u      /* the largest ulen a block may claim */
#define SD_WINDOW     0x10000u     /* SlowFastB reaches back 49120 bytes */
#define SD_STAGE      512u         /* output staging, so the sink sees runs */
#define SD_MODULEMAX  64u          /* modules before we call it a loop      */

/* The signature every Add-In Module carries at its own offset 4. */
static const char sd_modsig[] = "SuperDisk! Add-In Module";

/* ------------------------------------------------------------------ */
/* Where the record stream starts                                     */
/* ------------------------------------------------------------------ */

/* Two shapes exist. The 1991 self-extractor (`CODE 2` @0x110) sets its
 * file position to 0, reads 80 bytes and then throws the first EIGHT
 * away — so the records begin at 8 and nothing ever looks at what was
 * skipped. The 1992 Disk Expander (`CODE 2` @0x476) starts its walk at
 * 12 instead and treats the long at 8 as the length of a decompressor
 * module, each module being followed by the length of the next and a
 * zero ending the chain.
 *
 * Which one a file is, is decided by the module signature rather than
 * by a version byte: a module is there or it is not. */
static int sd_records_start(UncIO *io, uint32_t *out, int *has_module)
{
    uint8_t buf[32];
    uint32_t at, len;
    unsigned n;

    *has_module = 0;
    if (unc_read_at(io, 8, buf, 8) != UNC_OK) return UNC_ERR_FORMAT;
    if (buf[0] == SD_TAG_FILE || buf[0] == SD_TAG_DIR) {
        for (n = 1; n < 8; n++)
            if (buf[n] != 0) break;
        if (n == 8) { *out = 8u; return UNC_OK; }   /* the 1991 shape */
    }
    len = unc_get_u32be(buf);
    at = 12;
    for (n = 0; len != 0; n++) {
        unsigned i;
        if (n >= SD_MODULEMAX) return UNC_ERR_CORRUPT;
        if (len < 32 || len > 0x100000u) return UNC_ERR_FORMAT;
        if (unc_read_at(io, at + 4, buf, 24) != UNC_OK) return UNC_ERR_FORMAT;
        for (i = 0; i < 24; i++)
            if (buf[i] != (uint8_t)sd_modsig[i]) return UNC_ERR_FORMAT;
        *has_module = 1;
        at += len;
        if (unc_read_at(io, at, buf, 4) != UNC_OK) return UNC_ERR_FORMAT;
        len = unc_get_u32be(buf);
        at += 4;
    }
    *out = *has_module ? at : 8u;
    return UNC_OK;
}

/* An archive ends with a lone 0x27 record, so the last eight bytes are
 * a tag and seven zeros. That is what separates this from any other
 * file whose ninth byte happens to be 0x28. */
static int sd_end_marker_ok(UncIO *io)
{
    uint8_t tail[8];
    uint32_t size = io->size(io->ctx);
    int i;
    if (size == UNC_SIZE_UNKNOWN || size < 24) return 0;
    if (unc_read_at(io, size - 8, tail, 8) != UNC_OK) return 0;
    if (tail[0] != SD_TAG_END) return 0;
    for (i = 1; i < 8; i++)
        if (tail[i] != 0) return 0;
    return 1;
}

int unc_superdisk_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t start;
    int has_module, i;

    if (len < 40) return 0;
    /* Cheap rejection first: either a module signature sits where the
     * module chain would put it, or the ninth byte opens a record. */
    if (head[8] == SD_TAG_FILE || head[8] == SD_TAG_DIR) {
        for (i = 9; i < 16; i++)
            if (head[i] != 0) break;
        if (i == 16 && head[16] >= 1 && head[16] <= 31)
            return sd_end_marker_ok(io);
        return 0;
    }
    for (i = 0; i < 24; i++)
        if (head[16 + i] != (uint8_t)sd_modsig[i]) return 0;
    if (sd_records_start(io, &start, &has_module) != UNC_OK) return 0;
    return sd_end_marker_ok(io);
}

/* ------------------------------------------------------------------ */
/* Working storage, grown from the data rather than from a ceiling     */
/* ------------------------------------------------------------------ */

typedef struct SdBuf {
    uint8_t *p;
    uint32_t cap;
} SdBuf;

static int sd_need(UncCtx *c, SdBuf *b, uint32_t want)
{
    uint8_t *n;
    if (b->cap >= want) return UNC_OK;
    n = (uint8_t *)unc_alloc(c->al, want);
    if (!n) return UNC_ERR_MEM;
    unc_free(c->al, b->p);
    b->p = n;
    b->cap = want;
    return UNC_OK;
}

typedef struct SdState {
    UncCtx  *c;
    SdBuf    in;         /* one block, exactly as the reference reads it */
    SdBuf    flags;      /* the predictor's flag bitmap, when Huffman-coded */
    SdBuf    table;      /* the predictor's context table                 */
    SdBuf    win;        /* SlowFastB's history + the current block       */
    uint32_t winlen;     /* bytes of history live in win                  */
    uint8_t  stage[SD_STAGE];
    uint32_t staged;
    UncFork  fork;
} SdState;

static int sd_flush(SdState *s)
{
    UncCtx *c = s->c;
    if (s->staged == 0) return UNC_OK;
    if (!c->opt.test_only && !c->opt.list_only &&
        c->sink->write(c->sink->ctx, s->fork, s->stage,
                       (int32_t)s->staged) < 0)
        return UNC_ERR_SINK;
    s->staged = 0;
    return UNC_OK;
}

static int sd_emit(SdState *s, uint8_t b)
{
    if (s->staged == SD_STAGE) {
        int e = sd_flush(s);
        if (e != UNC_OK) return e;
    }
    s->stage[s->staged++] = b;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Huffman — CODE 2 @0x884                                            */
/* ------------------------------------------------------------------ */

/* The table is a byte-permutation in code order, plus one cumulative
 * count per code length starting at `startbits`, terminated by a
 * negative word. The reference turns those into one limit per length
 * and walks lengths until the accumulated code is below the limit. It
 * writes a WORD sentinel into a table of LONGS after the last limit,
 * which is how the LAST length gets no limit at all and always
 * matches: that is transcribed here as an explicit infinity rather
 * than as the reference's stale scratch memory. */
#define SD_MAXLEN 24

typedef struct SdHuff {
    const uint8_t *src;
    uint32_t       len;
    uint32_t       sym;          /* offset of the symbol permutation */
    uint32_t       pos;          /* next long of the code stream     */
    uint32_t       lim[SD_MAXLEN + 1];
    unsigned       nlim;
    unsigned       startbits;
    uint32_t       bits;
    unsigned       nbits;
    uint32_t       left;         /* symbols still to come            */
    uint8_t        run;          /* nonzero: a single repeated value */
    uint8_t        runval;
} SdHuff;

static int sd_huff_start(SdHuff *h, const uint8_t *src, uint32_t len,
                         uint32_t at)
{
    uint32_t d0, ct, i;

    if (at + 8 > len) return UNC_ERR_TRUNCATED;
    h->src = src;
    h->len = len;
    if (unc_get_u16be(src + at) == 0xFFFFu) {
        if (at + 6 > len) return UNC_ERR_TRUNCATED;
        h->run    = 1;
        h->runval = (uint8_t)unc_get_u16be(src + at + 2);
        h->left   = unc_get_u16be(src + at + 4);
        h->pos    = at + 8;                 /* @0x84a: a3 + 2 */
        return UNC_OK;
    }
    h->run       = 0;
    h->left      = unc_get_u16be(src + at);
    h->startbits = src[at + 2];
    h->sym       = at + 8;
    h->pos       = at + unc_get_u16be(src + at + 4);
    ct           = at + 10 + unc_get_u16be(src + at + 6);
    if (h->startbits == 0 || h->startbits > SD_MAXLEN) return UNC_ERR_CORRUPT;
    if (ct + 2 > len || h->pos > len || h->sym > len) return UNC_ERR_TRUNCATED;

    h->nlim = 0;
    d0 = unc_get_u16be(src + ct);
    for (i = 0;; i++) {
        uint32_t prev;
        int32_t  next;
        if (h->nlim >= SD_MAXLEN) return UNC_ERR_CORRUPT;
        h->lim[h->nlim++] = d0;
        d0 = (d0 * 2u) & 0xFFFFFFFFu;
        if (ct + (i + 2) * 2 > len) return UNC_ERR_TRUNCATED;
        prev = unc_get_u16be(src + ct + i * 2);
        next = (int16_t)unc_get_u16be(src + ct + (i + 1) * 2);
        if (next < 0) break;
        d0 = (d0 + (uint32_t)((int32_t)next - (int32_t)prev)) & 0xFFFFFFFFu;
    }
    h->lim[h->nlim++] = 0xFFFF0000u;        /* the sentinel, see above */
    h->bits = 0;
    h->nbits = 0;
    return UNC_OK;
}

static int sd_huff_bit(SdHuff *h, uint32_t *bit)
{
    if (h->nbits == 0) {
        if (h->pos + 4 > h->len) return UNC_ERR_TRUNCATED;
        h->bits = unc_get_u32be(h->src + h->pos);
        h->pos += 4;
        h->nbits = 32;
    }
    *bit = h->bits >> 31;
    h->bits = (h->bits << 1) & 0xFFFFFFFFu;
    h->nbits--;
    return UNC_OK;
}

static int sd_huff_next(SdHuff *h, uint8_t *out)
{
    uint32_t code = 0, base = 0, limit, bit;
    unsigned i;
    int e;

    if (h->left == 0) return UNC_ERR_TRUNCATED;
    h->left--;
    if (h->run) { *out = h->runval; return UNC_OK; }

    limit = h->lim[0];
    for (i = 0; i < h->startbits; i++) {
        if ((e = sd_huff_bit(h, &bit)) != UNC_OK) return e;
        code = (code << 1) | bit;
    }
    for (i = 1; code >= limit; i++) {
        if (i >= h->nlim) return UNC_ERR_CORRUPT;
        if ((e = sd_huff_bit(h, &bit)) != UNC_OK) return e;
        code = (code << 1) | bit;
        base += limit;
        limit = h->lim[i];
    }
    if (code < base) return UNC_ERR_CORRUPT;
    if (h->sym + (code - base) >= h->len) return UNC_ERR_CORRUPT;
    *out = h->src[h->sym + (code - base)];
    return UNC_OK;
}

/* Where the region after a Huffman-coded one begins: the reference
 * takes the cursor the bit reader left and adds 2 (@0x84a). */
static uint32_t sd_huff_end(const SdHuff *h)
{
    return h->run ? h->pos : h->pos + 2u;
}

/* ------------------------------------------------------------------ */
/* The finite-context predictor — CODE 2 @0x72e                        */
/* ------------------------------------------------------------------ */

/* One flag bit per output byte: set means "the byte this context
 * predicted", clear means "the next literal", which also becomes the
 * prediction for that context. The context is a lossy hash of the last
 * two bytes — the reference ORs the new byte into the low eight bits
 * of the shifted context instead of replacing them, so the top bits of
 * a byte can collide with the bottom bits of the one before it. That
 * is not a transcription slip; a plain concatenation decodes garbage.
 *
 * The first two output bytes are the first two literals, taken raw and
 * with the context left at zero. `ulen` counts only the bytes after
 * them, so the decoder produces ulen + 2 and the reference's caller
 * writes ulen — the last two are dropped, and the two literals they
 * would have consumed are read past the end of the literal stream.
 * Stopping at ulen, as here, avoids the over-read and yields the same
 * bytes. */
typedef struct SdLits {
    const uint8_t *raw;      /* when the literals are stored           */
    uint32_t       at, end;
    SdHuff        *huff;     /* when they are Huffman-coded            */
} SdLits;

static int sd_lit(SdLits *l, uint8_t *out)
{
    if (l->huff) return sd_huff_next(l->huff, out);
    if (l->at >= l->end) return UNC_ERR_TRUNCATED;
    *out = l->raw[l->at++];
    return UNC_OK;
}

static int sd_context(SdState *s, uint32_t ulen, const uint8_t *flags,
                      uint32_t flaglen, SdLits *lits, int wide)
{
    uint8_t *tbl = s->table.p;
    uint32_t mask = wide ? 0xFFFFu : 0x1FFFu;
    unsigned shift = wide ? 6u : 5u;
    uint32_t ctx = 0, done = 0, word = 0, at = 0;
    int      nbit = -1;
    uint8_t  b = 0;
    int      e;
    uint32_t i;

    for (i = 0; i < (wide ? 0x10000u : 0x2000u); i++) tbl[i] = 0;

    /* The two raw bytes that seed the output but not the context. */
    for (i = 0; i < 2 && done < ulen; i++) {
        if ((e = sd_lit(lits, &b)) != UNC_OK) return e;
        if ((e = sd_emit(s, b)) != UNC_OK) return e;
        done++;
    }

    while (done < ulen) {
        if (nbit < 0) {
            if (at + 4 > flaglen) return UNC_ERR_TRUNCATED;
            word = unc_get_u32be(flags + at);
            at += 4;
            nbit = 31;
        }
        if ((word >> (unsigned)nbit) & 1u) {
            b = tbl[ctx];
        } else {
            if ((e = sd_lit(lits, &b)) != UNC_OK) return e;
            tbl[ctx] = b;
        }
        if ((e = sd_emit(s, b)) != UNC_OK) return e;
        done++;
        nbit--;
        ctx = (ctx << shift) & 0xFFFFu;
        ctx = (ctx & 0xFF00u) | ((ctx | b) & 0x00FFu);
        ctx &= mask;
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* SlowFastB, method 11 — the Add-In Module @0xfc                     */
/* ------------------------------------------------------------------ */

/* An LZSS with two prefix codes and no explicit end of data: a length
 * escape of 255 terminates. Bits come out of 16-bit big-endian words,
 * LOW bit of each word first, which is what the module's
 * ror/move.w/rol refill amounts to. */
typedef struct SdLz {
    const uint8_t *src;
    uint32_t       len, pos;
    uint32_t       buf;
    unsigned       nbits;
    int            eof;
} SdLz;

static void sd_lz_fill(SdLz *z)
{
    uint32_t w;
    if (z->pos + 2 > z->len) { z->eof = 1; w = 0; }
    else { w = unc_get_u16be(z->src + z->pos); z->pos += 2; }
    z->buf = (z->buf & ((1u << z->nbits) - 1u)) | (w << z->nbits);
    z->nbits += 16;
}

static uint32_t sd_lz_take(SdLz *z, unsigned n)
{
    uint32_t v = z->buf & ((1u << n) - 1u);
    z->buf >>= n;
    z->nbits -= n;
    return v;
}

static int sd_slowfastb(SdState *s, const uint8_t *src, uint32_t len,
                        uint32_t ulen)
{
    SdLz z;
    uint8_t *win = s->win.p;
    uint32_t have = s->winlen;          /* history carried from earlier blocks */
    uint32_t out = 0;
    int e;

    z.src = src; z.len = len; z.pos = 0; z.buf = 0; z.nbits = 0; z.eof = 0;

    for (;;) {
        uint32_t n, off, idx;
        if (z.nbits < 10) sd_lz_fill(&z);
        if (sd_lz_take(&z, 1) == 0) {
            if (sd_lz_take(&z, 1) == 0) {
                uint8_t lit = (uint8_t)sd_lz_take(&z, 8);
                if (out >= ulen) return UNC_ERR_CORRUPT;
                win[have + out] = lit;
                out++;
                continue;
            }
            n = 1;
        } else if (sd_lz_take(&z, 1) == 0) {
            n = sd_lz_take(&z, 1) == 0 ? 2u : 3u;
        } else if (sd_lz_take(&z, 1) == 0) {
            n = 4;
        } else {
            uint32_t v = sd_lz_take(&z, 3);
            if (v != 7) n = v + 5;
            else {
                v = sd_lz_take(&z, 4);
                if (v != 15) n = v + 12;
                else {
                    if (z.nbits < 8) sd_lz_fill(&z);
                    v = sd_lz_take(&z, 8);
                    if (v == 255) break;          /* end of the block */
                    n = v + 27;
                }
            }
        }
        if (z.eof) return UNC_ERR_TRUNCATED;

        if (z.nbits < 15) sd_lz_fill(&z);
        idx = z.buf & 31u;
        (void)sd_lz_take(&z, 3);
        switch (idx & 7u) {
        case 0: off = sd_lz_take(&z, 5) + 1;     break;
        case 4: off = sd_lz_take(&z, 6) + 33;    break;
        case 2: off = sd_lz_take(&z, 7) + 97;    break;
        case 6: off = sd_lz_take(&z, 8) + 225;   break;
        case 1: off = sd_lz_take(&z, 9) + 481;   break;
        case 5: off = sd_lz_take(&z, 10) + 993;  break;
        case 3:
            (void)sd_lz_take(&z, 1);
            if (((idx >> 3) & 1u) == 0) {
                if (z.nbits < 11) sd_lz_fill(&z);
                off = sd_lz_take(&z, 11) + 2017;
            } else {
                if (z.nbits < 12) sd_lz_fill(&z);
                off = sd_lz_take(&z, 12) + 4065;
            }
            break;
        default:                                  /* case 7 */
            if (((idx >> 3) & 1u) == 0) {
                (void)sd_lz_take(&z, 1);
                if (z.nbits < 13) sd_lz_fill(&z);
                off = sd_lz_take(&z, 13) + 8161;
            } else {
                (void)sd_lz_take(&z, 2);
                if (z.nbits < 14) sd_lz_fill(&z);
                off = sd_lz_take(&z, 14) +
                      (((idx >> 4) & 1u) == 0 ? 16353u : 32737u);
            }
            break;
        }
        if (z.eof) return UNC_ERR_TRUNCATED;

        n++;                                       /* dbf runs n+1 times */
        if (off == 0 || off > have + out) return UNC_ERR_CORRUPT;
        if (out + n > ulen) return UNC_ERR_CORRUPT;
        while (n--) {
            win[have + out] = win[have + out - off];
            out++;
        }
    }
    if (out != ulen) return UNC_ERR_CORRUPT;

    for (out = 0; out < ulen; out++)
        if ((e = sd_emit(s, win[have + out])) != UNC_OK) return e;

    /* Slide the history: the last SD_WINDOW bytes of the fork so far. */
    if (have + ulen > SD_WINDOW) {
        uint32_t drop = have + ulen - SD_WINDOW;
        uint32_t i;
        for (i = 0; i < SD_WINDOW; i++) win[i] = win[drop + i];
        s->winlen = SD_WINDOW;
    } else {
        s->winlen = have + ulen;
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* One block                                                          */
/* ------------------------------------------------------------------ */

/* CODE 2 @0x6b4. Methods 5..8 are 1..4 over a 16-bit context instead of
 * a 13-bit one; 9 is Huffman alone; within 1..4, bit 1 says the flag
 * bitmap is Huffman-coded and bit 2 says the literals are. */
static int sd_block_body(SdState *s, uint32_t ulen, unsigned method,
                         uint8_t *body, uint32_t bodylen)
{
    SdHuff  fh, lh;
    SdLits  lits;
    uint32_t at = 0, fsize;
    const uint8_t *flags;
    int wide = 0, e;

    if (method == 11)
        return sd_slowfastb(s, body, bodylen, ulen);
    if (method == 9) {
        uint32_t i;
        if ((e = sd_huff_start(&lh, body, bodylen, 0)) != UNC_OK) return e;
        for (i = 0; i < ulen; i++) {
            uint8_t b;
            if ((e = sd_huff_next(&lh, &b)) != UNC_OK) return e;
            if ((e = sd_emit(s, b)) != UNC_OK) return e;
        }
        return UNC_OK;
    }
    if (method >= 5 && method <= 8) { wide = 1; method -= 4; }
    if (method < 1 || method > 4) return UNC_ERR_UNSUPPORTED;

    if ((e = sd_need(s->c, &s->table, wide ? 0x10000u : 0x2000u)) != UNC_OK)
        return e;

    fsize = (((ulen >> 3) + 4u) & ~1u);

    if (method == 1 || method == 3) {              /* the bitmap is stored */
        if (fsize > bodylen) return UNC_ERR_TRUNCATED;
        flags = body;
        at = fsize;
    } else {                                       /* @0x842 */
        uint32_t i;
        if ((e = sd_huff_start(&fh, body, bodylen, 0)) != UNC_OK) return e;
        if ((e = sd_need(s->c, &s->flags, fsize)) != UNC_OK) return e;
        for (i = 0; i < fsize; i++)
            if ((e = sd_huff_next(&fh, &s->flags.p[i])) != UNC_OK) return e;
        flags = s->flags.p;
        at = sd_huff_end(&fh);
    }

    lits.huff = 0;
    lits.raw = body;
    lits.at  = at;
    lits.end = bodylen;
    if (method == 3 || method == 4) {              /* @0x866 */
        if ((e = sd_huff_start(&lh, body, bodylen, at)) != UNC_OK) return e;
        lits.huff = &lh;
    }
    return sd_context(s, ulen, flags, fsize, &lits, wide);
}

/* ------------------------------------------------------------------ */
/* One fork: a chain of blocks                                        */
/* ------------------------------------------------------------------ */

/* CODE 2 @0x5f4. Each block starts with its own total length, and a
 * length with bit 15 set means the bytes are stored rather than coded
 * — except for exactly 0x8002, which the reference singles out
 * (@0x614) because a full 32 KB stored block cannot be said any other
 * way. The chain runs until the fork's declared length is met; there
 * is no block count.
 *
 * Walking is separated from decoding because a fork's length is the
 * only way to find the record after it: a listing, a skipped entry and
 * an entry whose method no reference here could be read from all have
 * to step over the chain, and only the first six bytes of each block
 * are needed to do that. */
static int sd_block_head(UncCtx *c, uint32_t at, uint32_t *clen,
                         uint32_t *ulen, unsigned *method, int *stored)
{
    uint8_t hdr[6];
    uint32_t n;

    if (unc_read_at(c->io, at, hdr, 2) != UNC_OK) return UNC_ERR_TRUNCATED;
    n = unc_get_u16be(hdr);
    if (n & 0x8000u) {
        *stored = 1;
        if (n == 0x8002u) { *clen = 0x8002u; *ulen = 0x8000u; }
        else {
            n &= 0x7FFFu;
            if (n < 2) return UNC_ERR_CORRUPT;
            *clen = n;
            *ulen = n - 2u;
        }
        *method = 0;
        return UNC_OK;
    }
    *stored = 0;
    if (n < 8) return UNC_ERR_CORRUPT;
    if (unc_read_at(c->io, at, hdr, 6) != UNC_OK) return UNC_ERR_TRUNCATED;
    *clen   = n;
    *ulen   = unc_get_u16be(hdr + 2);
    *method = unc_get_u16be(hdr + 4);
    if (*ulen == 0 || *ulen > SD_BLOCKMAX) return UNC_ERR_CORRUPT;
    return UNC_OK;
}

/* Where the fork ends, without decoding a byte of it. */
static int sd_fork_span(UncCtx *c, uint32_t at, uint32_t want, uint32_t *end)
{
    uint32_t done = 0;
    while (done < want) {
        uint32_t clen, ulen;
        unsigned method;
        int stored, e;
        if ((e = sd_block_head(c, at, &clen, &ulen, &method, &stored)) != UNC_OK)
            return e;
        if (ulen > want - done) {
            if (!stored) return UNC_ERR_CORRUPT;
            ulen = want - done;               /* a stored tail may overhang */
        }
        done += ulen;
        at += clen;
    }
    *end = at;
    return UNC_OK;
}

static int sd_fork(SdState *s, uint32_t at, uint32_t want)
{
    UncCtx *c = s->c;
    uint32_t done = 0;
    int e;

    s->winlen = 0;
    while (done < want) {
        uint32_t clen, ulen, body;
        unsigned method;
        int stored;

        if ((e = sd_block_head(c, at, &clen, &ulen, &method, &stored)) != UNC_OK)
            return e;

        if (stored) {
            uint32_t n = ulen, off = at + 2;
            if (n > want - done) n = want - done;
            if ((e = sd_flush(s)) != UNC_OK) return e;
            while (n > 0) {
                uint32_t take = n < SD_STAGE ? n : SD_STAGE;
                if (unc_read_at(c->io, off, s->stage, (int32_t)take) != UNC_OK)
                    return UNC_ERR_TRUNCATED;
                s->staged = take;
                if ((e = sd_flush(s)) != UNC_OK) return e;
                if ((e = unc_progress_add(&c->ps, take)) != UNC_OK) return e;
                off += take; done += take; n -= take;
            }
            at += clen;
            continue;
        }
        if (ulen > want - done) return UNC_ERR_CORRUPT;

        body = clen - 6u;
        /* The reference hands the decoder the two bytes that follow the
         * block as well — they are the next block's length — so keep
         * them, plus slack for a bit reader that peeks past the end. */
        if ((e = sd_need(c, &s->in, body + 8u)) != UNC_OK) return e;
        s->in.p[body] = s->in.p[body + 1] = 0;
        if (unc_read_at(c->io, at + 6, s->in.p, (int32_t)(body + 2u)) != UNC_OK &&
            unc_read_at(c->io, at + 6, s->in.p, (int32_t)body) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        s->in.p[body + 2] = s->in.p[body + 3] = 0;
        s->in.p[body + 4] = s->in.p[body + 5] = 0;
        s->in.p[body + 6] = s->in.p[body + 7] = 0;

        if (method == 11 &&
            (e = sd_need(c, &s->win, SD_WINDOW + SD_BLOCKMAX)) != UNC_OK)
            return e;
        if ((e = sd_block_body(s, ulen, method, s->in.p, body + 2u)) != UNC_OK)
            return e;
        if ((e = unc_progress_add(&c->ps, clen)) != UNC_OK) return e;
        done += ulen;
        at += clen;
    }
    return sd_flush(s);
}

/* ------------------------------------------------------------------ */
/* The record stream                                                  */
/* ------------------------------------------------------------------ */

typedef struct SdPath {
    uint8_t  buf[UNC_NAME_MAX + 1];
    uint16_t len;
    uint16_t stack[SD_MAXDEPTH];
    int      depth;
} SdPath;

static void sd_path_leaf(const SdPath *p, UncEntryInfo *e,
                         const uint8_t *name, uint32_t nlen)
{
    uint8_t full[UNC_NAME_MAX + 1];
    uint32_t n = p->len, i;
    if (n > UNC_NAME_MAX) n = UNC_NAME_MAX;
    for (i = 0; i < n; i++) full[i] = p->buf[i];
    if (n && n < UNC_NAME_MAX) full[n++] = '/';
    for (i = 0; i < nlen && n < UNC_NAME_MAX; i++) {
        uint8_t ch = name[i];
        full[n++] = (uint8_t)(ch == '/' ? ':' : ch);
    }
    unc_entry_set_path(e, full, n);
}

int unc_superdisk_extract(UncCtx *c)
{
    SdState s;
    SdPath  path;
    uint8_t rec[40];
    uint32_t at;
    int has_module, err = UNC_OK;

    if ((err = sd_records_start(c->io, &at, &has_module)) != UNC_OK) return err;

    s.c = c;
    s.in.p = s.flags.p = s.table.p = s.win.p = 0;
    s.in.cap = s.flags.cap = s.table.cap = s.win.cap = 0;
    s.winlen = 0;
    s.staged = 0;
    s.fork = UNC_FORK_DATA;
    path.len = 0;
    path.depth = 0;

    for (;;) {
        uint32_t nlen, dlen, rlen, p;
        UncEntryInfo e;
        unsigned tag;
        int sret;

        if (unc_read_at(c->io, at, rec, 8) != UNC_OK) { err = UNC_ERR_TRUNCATED; break; }
        tag = rec[0];
        if (tag == SD_TAG_END) break;
        if (tag == SD_TAG_UPDIR) {
            at += 8;
            if (path.depth > 0) {
                path.depth--;
                path.len = path.stack[path.depth];
                path.buf[path.len] = 0;
            }
            continue;
        }
        if (tag != SD_TAG_FILE && tag != SD_TAG_DIR) { err = UNC_ERR_CORRUPT; break; }

        if (unc_read_at(c->io, at + 8, rec, 1) != UNC_OK) { err = UNC_ERR_TRUNCATED; break; }
        nlen = rec[0];
        if (nlen == 0 || nlen > 31) { err = UNC_ERR_CORRUPT; break; }
        if (unc_read_at(c->io, at + 9, rec, (int32_t)nlen) != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            break;
        }
        p = at + 9 + nlen;
        if (p & 1u) p++;                          /* @0x336: pad to even */

        unc_entry_clear(&e);
        sd_path_leaf(&path, &e, rec, nlen);

        if (tag == SD_TAG_DIR) {
            uint8_t info[20];
            if (unc_read_at(c->io, p, info, 20) != UNC_OK) { err = UNC_ERR_TRUNCATED; break; }
            e.is_dir = 1;
            if (c->sink->begin_entry(c->sink->ctx, &e) < 0) { err = UNC_ERR_SINK; break; }
            if (c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) { err = UNC_ERR_SINK; break; }
            if (path.depth < (int)SD_MAXDEPTH) {
                uint32_t i;
                path.stack[path.depth++] = path.len;
                if (path.len && path.len < UNC_NAME_MAX) path.buf[path.len++] = '/';
                for (i = 0; i < nlen && path.len < UNC_NAME_MAX; i++)
                    path.buf[path.len++] = (uint8_t)(rec[i] == '/' ? ':' : rec[i]);
                path.buf[path.len] = 0;
            }
            at = p + 20;
            continue;
        }

        /* A file: 30 bytes of it, then its forks. @0x39c. */
        if (unc_read_at(c->io, p, rec, 30) != UNC_OK) { err = UNC_ERR_TRUNCATED; break; }
        dlen = unc_get_u32be(rec);
        rlen = unc_get_u32be(rec + 4);
        e.data_size    = dlen;
        e.rsrc_size    = rlen;
        e.type         = unc_get_u32be(rec + 8);
        e.creator      = unc_get_u32be(rec + 12);
        e.finder_flags = unc_get_u16be(rec + 16);
        e.create_date  = unc_get_u32be(rec + 22);
        e.mod_date     = unc_get_u32be(rec + 26);
        at = p + 30;

        /* Both forks are spanned before anything is decoded: their
         * lengths are the only route to the next record, so a fork we
         * cannot decode must still be stepped over. */
        {
            uint32_t end = at;
            if (dlen && (err = sd_fork_span(c, end, dlen, &end)) != UNC_OK) break;
            if (rlen && (err = sd_fork_span(c, end, rlen, &end)) != UNC_OK) break;

            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0) {
                int ferr = UNC_OK;
                s.staged = 0;
                if (!c->opt.list_only) {
                    if (dlen) { s.fork = UNC_FORK_DATA; ferr = sd_fork(&s, at, dlen); }
                    if (ferr == UNC_OK && rlen) {
                        uint32_t rat = at;
                        if (dlen) (void)sd_fork_span(c, at, dlen, &rat);
                        s.fork = UNC_FORK_RSRC;
                        ferr = sd_fork(&s, rat, rlen);
                    }
                }
                if (c->sink->end_entry(c->sink->ctx, ferr) < 0) { err = UNC_ERR_SINK; break; }
                /* Not UNC_ERR_MEM: an entry that will not fit is that
                 * entry's error, and the next one may be smaller. */
                if (ferr == UNC_ERR_SINK || ferr == UNC_ERR_ABORTED ||
                    ferr == UNC_ERR_IO) { err = ferr; break; }
            }
            at = end;
        }
    }

    unc_free(c->al, s.in.p);
    unc_free(c->al, s.flags.p);
    unc_free(c->al, s.table.p);
    unc_free(c->al, s.win.p);
    return err;
}

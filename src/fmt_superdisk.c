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
 * SuperDisk! also writes a SINGLE-FILE container — what its control
 * panel's "Make File" produces, and what the format's own help calls an
 * auto-expanding file. It stands to the archive as DiskDoubler's
 * 0xABCD0054 does to `DDAR`: no record stream at all, a fixed header and
 * then the same block chains, data fork first.
 *
 *   +0  (4) total uncompressed size, and it EQUALS +4 plus +8
 *   +4  (4) data fork size          +8  (4) resource fork size
 *   +12 (4) type                    +16 (4) creator
 *   +20 (2) Finder flags
 *   +22 (4) creation date           +26 (4) modification date
 *   +30     the name as a Pascal string, padded to an even total
 *           length, then the data fork's blocks, then the resource
 *           fork's
 *
 * Derived 2026-08-22 by compressing five subjects chosen to separate the
 * fields — one with a resource fork, one with distinct dates, one with a
 * 20-character name, one over 32 KB — with Alysis's own 1991 control
 * panel under Mini vMac (`tools/vmac/sdcompress.py --specimens`), and
 * graded against the bytes that went in. DECISIONS.md 2026-08-22.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define SD_TAG_END    0x27u
#define SD_TAG_FILE   0x28u
#define SD_TAG_DIR    0x29u
#define SD_TAG_UPDIR  0x2Au

#define SD_BLOCKMAX   0x8000u      /* the largest ulen a block may claim */
#define SD_WINDOW     0x10000u     /* SlowFastB reaches back 49120 bytes */
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
    uint32_t size = unc_io_size32(io);
    int i;
    if (size == UNC_SIZE_UNKNOWN || size < 24) return 0;
    if (unc_read_at(io, size - 8, tail, 8) != UNC_OK) return 0;
    if (tail[0] != SD_TAG_END) return 0;
    for (i = 1; i < 8; i++)
        if (tail[i] != 0) return 0;
    return 1;
}

/* The single-file container's body offset, or 0 if the head does not
 * look like one. `total == data + rsrc` is the load-bearing test: it is
 * a 32-bit identity that random data fails, and it is what tells this
 * container apart from an archive whose first eight bytes nobody
 * reads. */
uint32_t unc_superdisk_single_body(const uint8_t *head, int32_t len)
{
    uint32_t total, dlen, rlen, body, clen, ulen;
    uint32_t nlen;

    if (len < 40) return 0;
    total = unc_get_u32be(head);
    dlen  = unc_get_u32be(head + 4);
    rlen  = unc_get_u32be(head + 8);
    if (total == 0 || total > UNC_MAC_MAX) return 0;
    if (dlen > UNC_MAC_MAX || rlen > UNC_MAC_MAX) return 0;
    if (total != dlen + rlen) return 0;
    nlen = head[30];
    if (nlen == 0 || nlen > 31) return 0;
    body = 31u + nlen;
    if (body & 1u) body++;
    if ((int32_t)(body + 6u) > len) return 0;
    /* and the first block header has to be one */
    clen = unc_get_u16be(head + body);
    if (clen & 0x8000u) {
        if ((clen & 0x7FFFu) < 2 && clen != 0x8002u) return 0;
        return body;
    }
    if (clen < 8) return 0;
    ulen = unc_get_u16be(head + body + 2);
    if (ulen == 0 || ulen > SD_BLOCKMAX) return 0;
    return body;
}

UncFormat unc_superdisk_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t start;
    int has_module, i;

    if (len < 40) return UNC_FORMAT_UNKNOWN;
    if (unc_superdisk_single_body(head, len)) return UNC_FORMAT_SUPERDISK;
    /* Cheap rejection first: either a module signature sits where the
     * module chain would put it, or the ninth byte opens a record. */
    if (head[8] == SD_TAG_FILE || head[8] == SD_TAG_DIR) {
        for (i = 9; i < 16; i++)
            if (head[i] != 0) break;
        if (i == 16 && head[16] >= 1 && head[16] <= 31)
            return (sd_end_marker_ok(io))
           ? UNC_FORMAT_SUPERDISK : UNC_FORMAT_UNKNOWN;
        return UNC_FORMAT_UNKNOWN;
    }
    for (i = 0; i < 24; i++)
        if (head[16 + i] != (uint8_t)sd_modsig[i]) return UNC_FORMAT_UNKNOWN;
    if (sd_records_start(io, &start, &has_module) != UNC_OK) return UNC_FORMAT_UNKNOWN;
    return (sd_end_marker_ok(io))
           ? UNC_FORMAT_SUPERDISK : UNC_FORMAT_UNKNOWN;
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
    UncForkOut out;      /* the sink, the fork, and the staging buffer   */
    uint8_t  sbuf[UNC_STAGE];
    SdBuf    in;         /* one block, exactly as the reference reads it */
    SdBuf    flags;      /* the predictor's flag bitmap, when Huffman-coded */
    SdBuf    table;      /* the predictor's context table                 */
    SdBuf    win;        /* SlowFastB's history + the current block       */
    uint32_t winlen;     /* bytes of history live in win                  */
} SdState;

/* Start one fork's output. The guard is this format's: a list-only or
 * test-only run decodes and checksums but writes nothing. */
static void sd_out_start(SdState *s, UncCtx *c, UncFork fork)
{
    unc_fork_out(&s->out, c, fork,
                 !c->opt.test_only && !c->opt.list_only,
                 UNC_CK_NONE, s->sbuf, UNC_STAGE);
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
 * takes the cursor the bit reader left and adds 2 (@0x84a).
 *
 * The cursor is not this reader's cursor when the last symbol ended
 * exactly on a 32-bit refill. `sd_huff_bit` fetches a long only when a
 * bit is asked for; the compressor's reader has already fetched it, so
 * its cursor is four bytes further on and everything after the region
 * starts there. MEASURED 2026-08-28 on blocks Alysis's own 1991 panel
 * wrote for the purpose: at 160 and 256 flag bits every literal came
 * back wrong under `+2` alone and byte-exact under this, while 161 and
 * 257 bits are unaffected either way (DECISIONS.md, the refill
 * boundary). The 1992 Add-In Module reads them the same way, which is
 * the disagreement this closes. */
static uint32_t sd_huff_end(const SdHuff *h)
{
    if (h->run) return h->pos;
    return h->pos + (h->nbits == 0 ? 4u : 0u) + 2u;
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
        if ((e = unc_fork_put(&s->out, b)) != UNC_OK) return e;
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
        if ((e = unc_fork_put(&s->out, b)) != UNC_OK) return e;
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
        if ((e = unc_fork_put(&s->out, win[have + out])) != UNC_OK) return e;

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
/* SlowFastA, method 10 — `Cmpr` 21 @0x8a                             */
/* ------------------------------------------------------------------ */

/* An LZSS with a control word ahead of every 32 items, MSB first: a set
 * bit is one literal byte, a clear one a match. A match is two bytes —
 * the high nibble of the first is the length, the remaining twelve bits
 * are the offset — and it copies `nibble + 2` bytes from `out - offset
 * + 1`. Twelve bits of 0xF00 or more is an escape: the field's low byte
 * and one further byte make a sixteen-bit offset. An offset of zero ends
 * the block.
 *
 * **The length is nibble + 2 and not 2*(nibble+1)**, which is the whole
 * reason this decoder was graded before it was believed: the copy is one
 * unconditional MOVEB followed by a DBF whose target is the SECOND move
 * (@0xfc, @0xfe, @0x100), so the loop body is one byte, not two. Read
 * as a pair it decodes a stream this engine's own test encoder wrote and
 * disagrees with the module on every match — measured 2026-08-25.
 *
 *   Source: the module itself — `Cmpr` 21 of the Disk Expander 1.2
 *   extension, which `fixtures/alysis-disk-expander-12.hqx` carries and
 *   this engine extracts. Code at 0x8a: the control word is built at
 *   0xc4, literals copied at 0xd8, the two-byte match read at 0xe0, the
 *   twenty-bit escape taken at 0x10a, and the block ends at 0xee where
 *   the offset field is zero. The parameter block it arrives on is
 *   Alysis's own published one (tools/sdmodule/sdmod_run.c).
 *
 * **No corpus archive uses method 10 and nothing reachable writes one**,
 * so the module IS the oracle: `tools/sdmodule/run_sdmodule.py` runs it
 * under qemu-m68k over the same streams this decoder is given and
 * requires the same bytes out.
 *
 * One case is refused rather than copied: an offset of 1 addresses the
 * byte being written, so the reference copies whatever its destination
 * buffer happened to hold. That is not a decodable stream, and a
 * compressor cannot mean it. */
static int sd_slowfasta(SdState *s, const uint8_t *src, uint32_t len,
                        uint32_t ulen)
{
    uint8_t *win = s->win.p;
    uint32_t have = s->winlen;          /* history carried across blocks */
    uint32_t out = 0, at = 0, ctrl = 0;
    unsigned nbit = 0;
    int e;

    for (;;) {
        uint32_t off, n, from;

        if (nbit == 0) {
            if (at + 4 > len) return UNC_ERR_TRUNCATED;
            ctrl = unc_get_u32be(src + at);
            at += 4;
            nbit = 32;
        }
        if (ctrl & 0x80000000u) {                 /* @0xd8: a literal */
            if (at >= len) return UNC_ERR_TRUNCATED;
            if (out >= ulen) return UNC_ERR_CORRUPT;
            win[have + out] = src[at++];
            out++;
            ctrl <<= 1;
            nbit--;
            continue;
        }
        ctrl <<= 1;
        nbit--;

        if (at + 2 > len) return UNC_ERR_TRUNCATED;
        n   = (uint32_t)(src[at] >> 4);
        off = (((uint32_t)src[at] << 8) | src[at + 1]) & 0xFFFu;
        at += 2;
        if (off == 0) break;                      /* @0xee */
        if (off >= 0xF00u) {                      /* @0x10a: sixteen bits */
            /* ASL.W #8 shifts the marker nibble out of the word, so the
             * wide offset is the field's LOW byte joined with the next
             * one — 0..65535, which is the window — and not the marker
             * carried along into a twenty-bit number. */
            if (at >= len) return UNC_ERR_TRUNCATED;
            off = ((off & 0xFFu) << 8) | src[at++];
            if (off == 0) return UNC_ERR_CORRUPT;
        }
        n += 2u;                                  /* @0xfc + @0xfe..@0x100 */
        if (off < 2u || off - 1u > have + out) return UNC_ERR_CORRUPT;
        from = have + out - (off - 1u);
        if (out + n > ulen) return UNC_ERR_CORRUPT;
        while (n--) {
            win[have + out] = win[from];
            out++;
            from++;
        }
    }
    if (out != ulen) return UNC_ERR_CORRUPT;

    for (out = 0; out < ulen; out++)
        if ((e = unc_fork_put(&s->out, win[have + out])) != UNC_OK) return e;

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
    if (method == 10)
        return sd_slowfasta(s, body, bodylen, ulen);
    if (method == 9) {
        uint32_t i;
        if ((e = sd_huff_start(&lh, body, bodylen, 0)) != UNC_OK) return e;
        for (i = 0; i < ulen; i++) {
            uint8_t b;
            if ((e = sd_huff_next(&lh, &b)) != UNC_OK) return e;
            if ((e = unc_fork_put(&s->out, b)) != UNC_OK) return e;
        }
        return UNC_OK;
    }
    if (method >= 5 && method <= 8) { wide = 1; method -= 4; }
    if (method < 1 || method > 4) return UNC_ERR_UNSUPPORTED;

    if ((e = sd_need(s->out.c, &s->table, wide ? 0x10000u : 0x2000u)) != UNC_OK)
        return e;

    fsize = (((ulen >> 3) + 4u) & ~1u);

    if (method == 1 || method == 3) {              /* the bitmap is stored */
        if (fsize > bodylen) return UNC_ERR_TRUNCATED;
        flags = body;
        at = fsize;
    } else {                                       /* @0x842 */
        /* Only the bytes the bitmap actually needs are coded — one bit
         * per output byte, so ceil(ulen/8) — where the STORED form at
         * `fsize` carries four bytes of slack and a round-up beyond
         * them. Asking the Huffman decoder for `fsize` bytes runs it off
         * the end of the stream: measured on the first method 6 block
         * ever decoded here, which wanted 1,300 and had 1,297
         * (DECISIONS.md 2026-08-22, the settings sweep). The tail is
         * zeroed so nothing downstream reads what was never coded. */
        uint32_t i, nflags = (ulen + 7u) >> 3;
        if (nflags > fsize) nflags = fsize;
        if ((e = sd_huff_start(&fh, body, bodylen, 0)) != UNC_OK) return e;
        if ((e = sd_need(s->out.c, &s->flags, fsize)) != UNC_OK) return e;
        for (i = 0; i < nflags; i++)
            if ((e = sd_huff_next(&fh, &s->flags.p[i])) != UNC_OK) return e;
        for (i = nflags; i < fsize; i++) s->flags.p[i] = 0;
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
    /* The method is the LOW byte of that word, not the word: the
     * reference dispatches on `a2@(3)` with a2 at the length word
     * (CODE 2 @0x6ba, and the Add-In Modules' own dispatch), and the
     * high byte carries something else — method 9 keeps its Huffman
     * `startbits` there. Read as a word it was 0x0809 for a method 9
     * block, which this engine then refused as unsupported (2026-08-25,
     * BLOCKERS.md). */
    *method = hdr[5];
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
    UncCtx *c = s->out.c;
    uint32_t done = 0;
    int e;

    s->winlen = 0;
    while (done < want) {
        uint32_t clen, ulen, body, head;
        unsigned method;
        int stored;

        if ((e = sd_block_head(c, at, &clen, &ulen, &method, &stored)) != UNC_OK)
            return e;

        if (stored) {
            uint32_t n = ulen, off = at + 2;
            if (n > want - done) n = want - done;
            if ((e = unc_fork_flush(&s->out)) != UNC_OK) return e;
            while (n > 0) {
                uint32_t take = n < UNC_STAGE ? n : UNC_STAGE;
                if (unc_read_at(c->io, off, s->out.buf, (int32_t)take) != UNC_OK)
                    return UNC_ERR_TRUNCATED;
                s->out.len = take;
                if ((e = unc_fork_flush(&s->out)) != UNC_OK) return e;
                if ((e = unc_progress_add(&c->ps, take)) != UNC_OK) return e;
                off += take; done += take; n -= take;
            }
            at += clen;
            continue;
        }
        if (ulen > want - done) return UNC_ERR_CORRUPT;

        /* Where the decoder is handed the block. Method 9 gets it at the
         * LENGTH word — its Huffman header starts there, so `left` is
         * the same word as `ulen` and `startbits` is the byte the method
         * word shares with the method itself. CODE 2 calls the Huffman
         * routine with a2 unchanged for method 9 (@0x712) where the
         * 1..4 family advances it past four bytes first (@0x812). */
        head = (method == 9) ? 2u : 6u;
        body = clen - head;
        /* The reference hands the decoder the two bytes that follow the
         * block as well — they are the next block's length — so keep
         * them, plus slack for a bit reader that peeks past the end. */
        if ((e = sd_need(c, &s->in, body + 8u)) != UNC_OK) return e;
        s->in.p[body] = s->in.p[body + 1] = 0;
        if (unc_read_at(c->io, at + head, s->in.p, (int32_t)(body + 2u)) != UNC_OK &&
            unc_read_at(c->io, at + head, s->in.p, (int32_t)body) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        s->in.p[body + 2] = s->in.p[body + 3] = 0;
        s->in.p[body + 4] = s->in.p[body + 5] = 0;
        s->in.p[body + 6] = s->in.p[body + 7] = 0;

        if (method == 11 || method == 10) {
            /* SlowFastB's window is history CARRIED ACROSS blocks plus the
             * block being decoded, so it is not bounded by one block's
             * ulen — but it is bounded by the FORK: `have` is the bytes
             * produced so far, capped at SD_WINDOW, and `have + ulen`
             * therefore never exceeds `want`, the fork's whole output.
             * A fork smaller than 96 KB gets a window its own size. */
            uint32_t need = SD_WINDOW + SD_BLOCKMAX;
            if (want < need) need = want;
            if ((e = sd_need(c, &s->win, need)) != UNC_OK) return e;
        }
        if ((e = sd_block_body(s, ulen, method, s->in.p, body + 2u)) != UNC_OK)
            return e;
        if ((e = unc_progress_add(&c->ps, clen)) != UNC_OK) return e;
        done += ulen;
        at += clen;
    }
    return unc_fork_flush(&s->out);
}

/* ------------------------------------------------------------------ */
/* The record stream                                                  */
/* ------------------------------------------------------------------ */

/* The single-file container: one entry, two fork chains, no records. */
static int sd_single(UncCtx *c, const uint8_t *head, uint32_t body)
{
    SdState s;
    UncEntryInfo e;
    uint32_t dlen, rlen, nlen, end;
    int sret, err = UNC_OK, ferr = UNC_OK;

    dlen = unc_get_u32be(head + 4);
    rlen = unc_get_u32be(head + 8);
    nlen = head[30];

    s.in.p = s.flags.p = s.table.p = s.win.p = 0;
    s.in.cap = s.flags.cap = s.table.cap = s.win.cap = 0;
    s.winlen = 0;
    sd_out_start(&s, c, UNC_FORK_DATA);

    unc_entry_clear(&e);
    unc_entry_set_path(&e, head + 31, nlen);
    e.data_size    = dlen;
    e.rsrc_size    = rlen;
    e.type         = unc_get_u32be(head + 12);
    e.creator      = unc_get_u32be(head + 16);
    e.finder_flags = unc_get_u16be(head + 20);
    e.create_date  = unc_get_u32be(head + 22);
    e.mod_date     = unc_get_u32be(head + 26);

    /* Span both forks first, exactly as the archive walk does: a fork
     * that cannot be stepped over is a corrupt file, not a short one. */
    end = body;
    if (dlen && (err = sd_fork_span(c, end, dlen, &end)) != UNC_OK) goto done;
    {   /* the method each fork opens with, for the host to name */
        uint32_t bclen, bulen;
        unsigned bmeth;
        int bstored;
        if (dlen && sd_block_head(c, body, &bclen, &bulen, &bmeth,
                                  &bstored) == UNC_OK)
            e.method_data = (uint8_t)(bstored ? 0 : bmeth);
        if (rlen && sd_block_head(c, end, &bclen, &bulen, &bmeth,
                                  &bstored) == UNC_OK)
            e.method_rsrc = (uint8_t)(bstored ? 0 : bmeth);
    }
    if (rlen && (err = sd_fork_span(c, end, rlen, &end)) != UNC_OK) goto done;

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) { err = UNC_ERR_SINK; goto done; }
    if (sret == 0) {
        if (!c->opt.list_only) {
            if (dlen) { sd_out_start(&s, c, UNC_FORK_DATA);
                        ferr = sd_fork(&s, body, dlen); }
            if (ferr == UNC_OK && rlen) {
                uint32_t rat = body;
                if (dlen) (void)sd_fork_span(c, body, dlen, &rat);
                sd_out_start(&s, c, UNC_FORK_RSRC);
                ferr = sd_fork(&s, rat, rlen);
            }
        }
        if (c->sink->end_entry(c->sink->ctx, ferr) < 0) err = UNC_ERR_SINK;
        else if (unc_fatal(ferr)) err = ferr;
    }
done:
    unc_free(c->al, s.in.p);
    unc_free(c->al, s.flags.p);
    unc_free(c->al, s.table.p);
    unc_free(c->al, s.win.p);
    return err;
}

int unc_superdisk_extract(UncCtx *c)
{
    SdState s;
    UncPath path;
    uint8_t rec[40];
    uint32_t at;
    int has_module, err = UNC_OK;

    {   /* the single-file container first: it has no record stream, so
         * the archive walk below would read its header as one.
         *
         * Only as much head as there IS: the smallest container this
         * format can write is 40 bytes — 30 of header, a one-character
         * name, and an eight-byte block — and asking for 64 turned every
         * one under that into "archive structure is corrupt". Found
         * 2026-08-25 with a synthetic 60-byte container
         * (tools/sdmodule/). */
        uint8_t head[64];
        uint32_t body, size = unc_io_size32(c->io);
        int32_t n = (int32_t)sizeof head;
        if (size != UNC_SIZE_UNKNOWN && size < sizeof head) n = (int32_t)size;
        if (n >= 40 && unc_read_at(c->io, 0, head, n) == UNC_OK) {
            body = unc_superdisk_single_body(head, n);
            if (body) return sd_single(c, head, body);
        }
    }

    if ((err = sd_records_start(c->io, &at, &has_module)) != UNC_OK) return err;

    s.in.p = s.flags.p = s.table.p = s.win.p = 0;
    s.in.cap = s.flags.cap = s.table.cap = s.win.cap = 0;
    s.winlen = 0;
    sd_out_start(&s, c, UNC_FORK_DATA);
    unc_path_init(&path, c);

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
            unc_path_pop(&path);
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
        unc_path_leaf(&path, &e, rec, nlen);

        if (tag == SD_TAG_DIR) {
            uint8_t info[20];
            if (unc_read_at(c->io, p, info, 20) != UNC_OK) { err = UNC_ERR_TRUNCATED; break; }
            e.is_dir = 1;
            if (c->sink->begin_entry(c->sink->ctx, &e) < 0) { err = UNC_ERR_SINK; break; }
            if (c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) { err = UNC_ERR_SINK; break; }
            /* Too deep to descend leaves the entries under the parent,
             * which is what this walk did before the push was shared. */
            (void)unc_path_push(&path, rec, nlen);
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
            uint32_t end = at, dend = at;
            if (dlen && (err = sd_fork_span(c, end, dlen, &end)) != UNC_OK) break;
            dend = end;
            if (rlen && (err = sd_fork_span(c, end, rlen, &end)) != UNC_OK) break;

            /* The method each fork opens with, for the host to name in a
             * message. Informational only — a fork's chain may in
             * principle change method between blocks — but it is what a
             * user needs when an entry comes back unsupported, and what
             * makes a bug report about it actionable. */
            {
                uint32_t bclen, bulen;
                unsigned bmeth;
                int bstored;
                if (dlen && sd_block_head(c, at, &bclen, &bulen, &bmeth,
                                          &bstored) == UNC_OK)
                    e.method_data = (uint8_t)(bstored ? 0 : bmeth);
                if (rlen && sd_block_head(c, dend, &bclen, &bulen, &bmeth,
                                          &bstored) == UNC_OK)
                    e.method_rsrc = (uint8_t)(bstored ? 0 : bmeth);
            }

            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0) {
                int ferr = UNC_OK;
                if (!c->opt.list_only) {
                    if (dlen) { sd_out_start(&s, c, UNC_FORK_DATA);
                                ferr = sd_fork(&s, at, dlen); }
                    if (ferr == UNC_OK && rlen) {
                        uint32_t rat = at;
                        if (dlen) (void)sd_fork_span(c, at, dlen, &rat);
                        sd_out_start(&s, c, UNC_FORK_RSRC);
                        ferr = sd_fork(&s, rat, rlen);
                    }
                }
                if (c->sink->end_entry(c->sink->ctx, ferr) < 0) { err = UNC_ERR_SINK; break; }
                /* Not UNC_ERR_MEM: an entry that will not fit is that
                 * entry's error, and the next one may be smaller. */
                if (unc_fatal(ferr)) { err = ferr; break; }
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

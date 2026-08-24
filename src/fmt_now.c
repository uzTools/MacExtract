/*
 * fmt_now.c — Now Compress archives.
 *
 *   Source: reference/XADMaster/XADNowCompressParser.m  (entry table)
 *   Source: reference/XADMaster/XADNowCompressHandle.m  (block table,
 *           and the four ways a block can be compressed)
 * — LGPL, see NOTICE.
 *
 * The archive is a flat entry table, nested by a per-directory entry
 * count, followed by one compressed stream per FILE. The reference
 * treats the whole archive as ONE solid stream and cuts entries out of
 * it by (offset, length); it does not have to. Each file's stream holds
 * exactly that file's resource fork followed by its data fork, in that
 * order, so this reader decodes file by file and never needs the solid
 * abstraction — which is also what lets it run in fixed memory.
 *
 * A stream is a table of blocks, each up to 32 KB of output, decoded
 * against a 32 KB sliding history. The block table's offsets are
 * sometimes wrong by a constant, which the reference finds by searching
 * for the header's own checksum; that search is transcribed here.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define NOW_HISTORY   0x8000u     /* sliding history kept between blocks */
#define NOW_OUTBLOCK  0x10000u    /* history + one block's output       */
#define NOW_INBLOCK   0x8000u     /* staging for a block's input        */
#define NOW_ENTRY     110u        /* bytes per entry in the table       */
#define NOW_MAXDEPTH  24
#define NOW_MAXBLOCKS 0x2000u     /* the reference's own search bound   */

/* ------------------------------------------------------------------ */
/* Bit input over a memory block, via the shared readers               */
/* ------------------------------------------------------------------ */

typedef struct NowBits {
    UncBufIn in;
    UncBitIn bi;
    uint32_t nbytes;
} NowBits;

static void now_bits_start(NowBits *b, const uint8_t *mem, uint32_t len)
{
    unc_bufin_init_mem(&b->in, mem, len);
    unc_bitin_init(&b->bi, &b->in);
    b->nbytes = len;
}

/* Bits consumed so far: what the byte reader has handed over, less what
 * the bit reader is still holding. */
static uint32_t now_bit_offset(const NowBits *b)
{
    return unc_bufin_tell(&b->in) * 8u - (uint32_t)b->bi.nbits;
}

/* ------------------------------------------------------------------ */
/* Huffman                                                            */
/* ------------------------------------------------------------------ */

/* numvalues/2 bytes of two 4-bit lengths each, then a count of
 * "extra length" entries, then that many symbol indices whose length
 * gains 16. Source: AllocAndReadCode. */
static int now_read_code(UncCanon *c, const uint8_t *src, uint32_t len,
                         int32_t numvalues, uint32_t *used)
{
    uint8_t lengths[0x122];
    int32_t i, n;
    uint32_t at = 0;

    if (numvalues > (int32_t)sizeof lengths) return UNC_ERR_CORRUPT;
    for (i = 0; i < numvalues / 2; i++) {
        if (at >= len) return UNC_ERR_TRUNCATED;
        lengths[2 * i]     = (uint8_t)(src[at] >> 4);
        lengths[2 * i + 1] = (uint8_t)(src[at] & 0x0F);
        at++;
    }
    if (numvalues & 1) lengths[numvalues - 1] = 0;
    if (at >= len) return UNC_ERR_TRUNCATED;
    n = src[at++];
    for (i = 0; i < n; i++) {
        if (at >= len) return UNC_ERR_TRUNCATED;
        lengths[src[at]] = (uint8_t)(lengths[src[at]] + 16u);
        at++;
    }
    *used = at;
    return unc_canon_build(c, lengths, numvalues);
}

/* The code tables a block needs, on the heap rather than on the frame.
 * An UncCanon is ~1.3 KB and now_newlzss holds two while calling
 * now_huffman, which held a third: 4,960 B in one chain, under
 * unc_now_extract's own 1.2 KB, for 5,632 B against CLAUDE.md's 4 KB
 * call-depth rule (measured, m68k -Os -fstack-usage). They ride in the
 * same allocation as the block buffers. */
struct NowCodes { UncCanon one, main, off; };

/* Decode one Huffman-coded region. Returns the output length, or a
 * negative error. Source: UnpackHuffman. */
static int32_t now_huffman(const uint8_t *src, uint32_t srclen,
                           uint8_t *dst, uint32_t dstcap, int32_t numvalues,
                           UncCanon *code, int *err)
{
    NowBits b;
    uint32_t used = 0, at, numbits;
    int32_t out = 0;
    int endbits, e;

    *err = UNC_OK;
    if (srclen < 1) { *err = UNC_ERR_TRUNCATED; return -1; }
    endbits = src[0];

    e = now_read_code(code, src + 1, srclen - 1, numvalues, &used);
    if (e != UNC_OK) { *err = e; return -1; }

    at = 1 + used;
    if (at & 1) at++;               /* WordAlign, from the buffer start */
    if (at > srclen) { *err = UNC_ERR_TRUNCATED; return -1; }

    numbits = (srclen - at) * 8u;
    if (endbits) {
        if (numbits < (uint32_t)(16 - endbits)) { *err = UNC_ERR_CORRUPT; return -1; }
        numbits -= (uint32_t)(16 - endbits);
    }

    now_bits_start(&b, src + at, srclen - at);
    while (now_bit_offset(&b) < numbits) {
        int sym;
        if ((uint32_t)out >= dstcap) { *err = UNC_ERR_CORRUPT; return -1; }
        sym = unc_canon_decode(code, &b.bi);
        if (sym < 0) { *err = b.bi.err ? b.bi.err : UNC_ERR_CORRUPT; return -1; }
        dst[out++] = (uint8_t)sym;
    }
    if (now_bit_offset(&b) != numbits) { *err = UNC_ERR_CORRUPT; return -1; }
    return out;
}

/* ------------------------------------------------------------------ */
/* The two LZSS variants                                              */
/* ------------------------------------------------------------------ */

/* Flag byte, MSB first: 1 = literal, 0 = a match whose offset is 13
 * bits split across two bytes and whose length is 3 bits, or a whole
 * byte when those 3 are zero. Source: UnpackLZSS. */
static int32_t now_lzss(const uint8_t *src, uint32_t srclen,
                        uint8_t *dst, uint32_t dstcap, int *err)
{
    uint32_t at = 2;                /* the first two bytes are skipped */
    int32_t out = 0;
    int bits = 0, numbits = 0;

    *err = UNC_OK;
    while (at < srclen) {
        if (!numbits) {
            bits = src[at++];
            numbits = 8;
            if (at >= srclen) { *err = UNC_ERR_TRUNCATED; return -1; }
        }
        if (bits & 0x80) {
            if ((uint32_t)out >= dstcap) { *err = UNC_ERR_CORRUPT; return -1; }
            dst[out++] = src[at++];
        } else {
            uint32_t offset, length, i;
            int b1, b2;
            b1 = src[at++];
            if (at >= srclen) { *err = UNC_ERR_TRUNCATED; return -1; }
            b2 = src[at++];
            offset = (uint32_t)(((b1 & 0xF8) << 5) | b2);
            length = (uint32_t)(b1 & 0x07);
            if (!length) {
                if (at >= srclen) { *err = UNC_ERR_TRUNCATED; return -1; }
                length = src[at++];
            }
            length += 2;
            if (offset == 0 || (uint32_t)out < offset) {
                *err = UNC_ERR_CORRUPT; return -1;
            }
            for (i = 0; i < length; i++) {
                if ((uint32_t)out >= dstcap) { *err = UNC_ERR_CORRUPT; return -1; }
                dst[out] = dst[out - (int32_t)offset];
                out++;
            }
        }
        bits <<= 1;
        numbits--;
    }
    return out;
}

/* Source: UnpackNewLZSS — the tables are the format's, transcribed. */
static const uint8_t now_len_extra[0x22] = {
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    1,1,2,2,2,2,2,3, 3,3,4,4,4,4,5,5, 5,5
};
static const uint16_t now_len_base[0x22] = {
    0x0000,0x0001,0x0002,0x0003,0x0004,0x0005,0x0006,0x0007,
    0x0008,0x0009,0x000a,0x000b,0x000c,0x000d,0x000e,0x000f,
    0x0010,0x0012,0x0014,0x0018,0x001c,0x0020,0x0024,0x0028,
    0x0030,0x0038,0x0040,0x0050,0x0060,0x0070,0x0080,0x00a0,
    0x00c0,0x00e0
};
static const uint8_t now_off_extra[0x38] = {
    0,0,0,0,0,0,0,0, 1,1,1,1,2,2,2,2,
    3,3,3,3,4,4,4,4, 5,5,5,5,8,8,8,8,
    8,8,8,8,9,9,9,9, 10,10,10,10,11,11,11,11,
    12,12,12,12,13,13,13,13
};
static const uint16_t now_off_base[0x38] = {
    0x0000,0x0001,0x0002,0x0003,0x0004,0x0005,0x0006,0x0007,
    0x0008,0x000a,0x000c,0x000e,0x0010,0x0014,0x0018,0x001c,
    0x0020,0x0028,0x0030,0x0038,0x0040,0x0050,0x0060,0x0070,
    0x0080,0x00a0,0x00c0,0x00e0,0x0100,0x0200,0x0300,0x0400,
    0x0500,0x0600,0x0700,0x0800,0x0900,0x0b00,0x0d00,0x0f00,
    0x1100,0x1500,0x1900,0x1d00,0x2100,0x2900,0x3100,0x3900,
    0x4100,0x5100,0x6100,0x7100,0x8100,0xa100,0xc100,0xe100
};

/* `base` is where matches may reach back to (the history), `dst` where
 * this block's output starts. Source: UnpackNewLZSS. */
static int32_t now_newlzss(const uint8_t *src, uint32_t srclen,
                           uint8_t *base, uint8_t *dst, uint32_t dstcap,
                           struct NowCodes *cd, int *err)
{
    uint8_t header[0x15a];
    uint8_t lengths[0x122];
    NowBits b;
    uint32_t at, headersize, numbits;
    int32_t out = 0, i, n;
    int endbits, e;

    *err = UNC_OK;
    if (srclen < 4) { *err = UNC_ERR_TRUNCATED; return -1; }
    headersize = (uint32_t)((unc_get_u16be(src) - 0x2F59u) & 0xFFFFu);
    endbits = src[3];
    at = 4;
    if (headersize > srclen - at) { *err = UNC_ERR_TRUNCATED; return -1; }

    n = now_huffman(src + at, headersize, header, (uint32_t)sizeof header,
                    20, &cd->one, &e);
    if (n < 0) { *err = e; return -1; }
    if (n != (int32_t)sizeof header) { *err = UNC_ERR_CORRUPT; return -1; }

    at += headersize;
    if (at & 1) at++;                       /* WordAlign */
    if (at > srclen) { *err = UNC_ERR_TRUNCATED; return -1; }

    for (i = 0; i < 0x122; i++) lengths[i] = header[i];
    if ((e = unc_canon_build(&cd->main, lengths, 0x122)) != UNC_OK) {
        *err = e; return -1;
    }
    for (i = 0; i < 0x38; i++)
        lengths[i] = header[i + 0x122] ? (uint8_t)(header[i + 0x122] - 2) : 0;
    if ((e = unc_canon_build(&cd->off, lengths, 0x38)) != UNC_OK) {
        *err = e; return -1;
    }

    numbits = (srclen - at) * 8u;
    if (endbits) {
        if (numbits < (uint32_t)(16 - endbits)) { *err = UNC_ERR_CORRUPT; return -1; }
        numbits -= (uint32_t)(16 - endbits);
    }

    now_bits_start(&b, src + at, srclen - at);
    while (now_bit_offset(&b) < numbits) {
        int sym = unc_canon_decode(&cd->main, &b.bi);
        uint32_t length, offset, k;
        int sel;
        if (sym < 0) { *err = b.bi.err ? b.bi.err : UNC_ERR_CORRUPT; return -1; }
        if (sym < 0x100) {
            if ((uint32_t)out >= dstcap) { *err = UNC_ERR_CORRUPT; return -1; }
            dst[out++] = (uint8_t)sym;
            continue;
        }
        sel = sym - 0x100;
        if (sel >= 0x22) { *err = UNC_ERR_CORRUPT; return -1; }
        length = now_len_base[sel];
        if (now_len_extra[sel]) {
            int32_t extra = unc_bitin_bits(&b.bi, now_len_extra[sel]);
            if (extra < 0) { *err = b.bi.err; return -1; }
            length += (uint32_t)extra;
        }
        length += 2;

        sel = unc_canon_decode(&cd->off, &b.bi);
        if (sel < 0) { *err = b.bi.err ? b.bi.err : UNC_ERR_CORRUPT; return -1; }
        if (sel >= 0x38) { *err = UNC_ERR_CORRUPT; return -1; }
        offset = now_off_base[sel];
        if (now_off_extra[sel]) {
            int32_t extra = unc_bitin_bits(&b.bi, now_off_extra[sel]);
            if (extra < 0) { *err = b.bi.err; return -1; }
            offset += (uint32_t)extra;
        }

        if ((uint32_t)out + length > dstcap) { *err = UNC_ERR_CORRUPT; return -1; }
        if (dst + out - offset < base) { *err = UNC_ERR_CORRUPT; return -1; }
        for (k = 0; k < length; k++) {
            dst[out] = dst[out - (int32_t)offset];
            out++;
        }
    }
    return out;
}

/* ------------------------------------------------------------------ */
/* One file's stream of blocks                                        */
/* ------------------------------------------------------------------ */

typedef struct NowStream {
    UncCtx  *c;
    struct NowCodes *cd;   /* code tables, off the stack — see below */
    uint8_t *inblock;      /* [incap]                                    */
    uint8_t *outblock;     /* [hist + blkcap]                            */
    uint8_t *dict;         /* [hist]                                     */
    /* Sized from the archive's largest fork rather than from the
     * format's ceilings — see unc_now_extract. hist <= NOW_HISTORY and
     * blkcap <= st->blkcap, always. */
    uint32_t hist;
    uint32_t blkcap;
    uint32_t incap;
    /* Where the current block's output sits and how much is left of it,
     * so a fork can be served across block boundaries. */
    uint8_t *avail;
    uint32_t availlen;
    /* Block table walk. */
    uint32_t tableat;      /* file offset of the next table entry */
    uint32_t entriesleft;
    uint32_t lastoffset;
    int32_t  delta;
    int      nextisstart;
    int      done;
} NowStream;

static int now_read_u32(UncCtx *c, uint32_t at, uint32_t *out)
{
    uint8_t b[4];
    if (c->io->seek(c->io->ctx, at) < 0) return UNC_ERR_IO;
    if (unc_read_full(c->io, b, 4) != UNC_OK) return UNC_ERR_TRUNCATED;
    *out = unc_get_u32be(b);
    return UNC_OK;
}

/* The header's offsets are sometimes off by a constant. The reference
 * finds it by walking the table until a 4-byte field equals the running
 * sum of everything before it, which is where the table's checksum sits.
 * Source: findFileHeaderDeltaWithHeaderOffset. */
static int32_t now_find_delta(UncCtx *c, uint32_t headeroffset,
                              uint32_t firstoffset)
{
    uint8_t buf[8];
    uint32_t checksum = 0;
    uint32_t n, i;

    if (c->io->seek(c->io->ctx, headeroffset) < 0) return 0;
    for (i = 0; i < 4; i++) {
        if (unc_read_full(c->io, buf, 4) != UNC_OK) return 0;
        checksum += (uint32_t)buf[0] + buf[1] + buf[2] + buf[3];
    }
    for (n = 2; n < NOW_MAXBLOCKS; n++) {
        if (unc_read_full(c->io, buf, 4) != UNC_OK) return 0;
        if (unc_get_u32be(buf) == checksum)
            return (int32_t)(headeroffset + n * 8u + 4u) - (int32_t)firstoffset;
        checksum += (uint32_t)buf[0] + buf[1] + buf[2] + buf[3];
        if (unc_read_full(c->io, buf, 4) != UNC_OK) return 0;
        checksum += (uint32_t)buf[0] + buf[1] + buf[2] + buf[3];
    }
    return 0;
}

static uint32_t now_sum32(uint32_t v)
{
    return (v >> 24) + ((v >> 16) & 0xFF) + ((v >> 8) & 0xFF) + (v & 0xFF);
}

/* Walk the table once to verify its checksum. Source:
 * parseAndCheckFileHeaderWithHeaderOffset. */
static int now_check_table(UncCtx *c, uint32_t headeroffset,
                           uint32_t firstoffset, int32_t delta,
                           uint32_t *nentries_out)
{
    uint8_t rec[8];
    uint32_t checksum, lastoffset = firstoffset;
    int32_t numentries;
    int32_t i;

    numentries = ((int32_t)(firstoffset + (uint32_t)delta - headeroffset) - 4) / 8 - 1;
    if (numentries < 0 || (uint32_t)numentries > NOW_MAXBLOCKS)
        return UNC_ERR_CORRUPT;

    if (c->io->seek(c->io->ctx, headeroffset + 4) < 0) return UNC_ERR_IO;
    checksum = now_sum32(firstoffset);

    for (i = 0; i < numentries; i++) {
        uint32_t nextoffset;
        if (unc_read_full(c->io, rec, 8) != UNC_OK) return UNC_ERR_TRUNCATED;
        nextoffset = unc_get_u32be(rec + 4);
        checksum += (uint32_t)rec[0] + rec[1];       /* flags   */
        checksum += (uint32_t)rec[2] + rec[3];       /* padding */
        checksum += now_sum32(nextoffset);
        lastoffset = nextoffset;
    }
    if (unc_read_full(c->io, rec, 4) != UNC_OK) return UNC_ERR_TRUNCATED;
    checksum += (uint32_t)rec[0] + rec[1] + rec[2] + rec[3];
    if (unc_read_full(c->io, rec, 4) != UNC_OK) return UNC_ERR_TRUNCATED;
    if (checksum != unc_get_u32be(rec)) return UNC_ERR_CORRUPT;

    (void)lastoffset;
    *nentries_out = (uint32_t)numentries;
    return UNC_OK;
}

/* Position the walk at a file's block table. */
static int now_stream_open(NowStream *st, uint32_t headeroffset)
{
    uint32_t firstoffset, n;
    int32_t delta = 0;
    int err;

    if ((err = now_read_u32(st->c, headeroffset, &firstoffset)) != UNC_OK)
        return err;

    if (firstoffset < headeroffset + 20) {
        delta = now_find_delta(st->c, headeroffset, firstoffset);
        err = now_check_table(st->c, headeroffset, firstoffset, delta, &n);
    } else {
        err = now_check_table(st->c, headeroffset, firstoffset, 0, &n);
        if (err != UNC_OK) {
            delta = now_find_delta(st->c, headeroffset, firstoffset);
            err = now_check_table(st->c, headeroffset, firstoffset, delta, &n);
        }
    }
    if (err != UNC_OK) return err;

    st->tableat = headeroffset + 4;
    st->entriesleft = n;
    st->lastoffset = firstoffset;
    st->delta = delta;
    st->nextisstart = 1;
    st->availlen = 0;
    st->done = 0;
    return UNC_OK;
}

/* Decode the next block of the current stream into st->avail.
 * Source: produceBlockAtOffset. */
static int now_next_block(NowStream *st)
{
    UncCtx *c = st->c;
    uint8_t rec[8];
    uint8_t *outstart = st->outblock + st->hist;
    uint32_t offset, length, i;
    int32_t out;
    int flags, first, err;

    for (;;) {
        uint32_t nextoffset, padding;
        if (st->entriesleft == 0) { st->done = 1; return UNC_OK; }
        if (c->io->seek(c->io->ctx, st->tableat) < 0) return UNC_ERR_IO;
        if (unc_read_full(c->io, rec, 8) != UNC_OK) return UNC_ERR_TRUNCATED;
        st->tableat += 8;
        st->entriesleft--;
        flags = (int)unc_get_u16be(rec);
        padding = unc_get_u16be(rec + 2);
        nextoffset = unc_get_u32be(rec + 4);
        if (nextoffset == st->lastoffset) { st->nextisstart = 1; continue; }
        if (nextoffset < st->lastoffset + padding + 4) return UNC_ERR_CORRUPT;
        offset = (uint32_t)((int32_t)st->lastoffset + st->delta);
        length = nextoffset - st->lastoffset - padding - 4;
        first = st->nextisstart;
        st->lastoffset = nextoffset;
        st->nextisstart = 0;
        break;
    }

    if (length > st->incap) return UNC_ERR_CORRUPT;

    /* A block that starts a stream reaches back into the history the
     * PREVIOUS stream left behind. The reference calls this absurd and
     * does it anyway; so do we, because the bytes require it. */
    if (first)
        for (i = 0; i < st->hist; i++) st->outblock[i] = st->dict[i];

    if (c->io->seek(c->io->ctx, offset) < 0) return UNC_ERR_IO;

    if (flags & 0x20) {
        if (flags & 0x1F) {                       /* Huffman, then LZSS */
            int32_t mid;
            if (unc_read_full(c->io, outstart, (int32_t)length) != UNC_OK)
                return UNC_ERR_TRUNCATED;
            mid = now_huffman(outstart, length, st->inblock, st->incap,
                              0x100, &st->cd->one, &err);
            if (mid < 0) return err;
            out = now_lzss(st->inblock, (uint32_t)mid, outstart,
                           st->blkcap, &err);
        } else {                                  /* Huffman only */
            if (unc_read_full(c->io, st->inblock, (int32_t)length) != UNC_OK)
                return UNC_ERR_TRUNCATED;
            out = now_huffman(st->inblock, length, outstart,
                              st->blkcap, 0x100,
                              &st->cd->one, &err);
        }
    } else if (flags & 0x40) {                    /* new LZSS */
        if (unc_read_full(c->io, st->inblock, (int32_t)length) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        out = now_newlzss(st->inblock, length, st->outblock, outstart,
                          st->blkcap, st->cd, &err);
    } else if (flags & 0x1F) {                    /* LZSS only */
        if (unc_read_full(c->io, st->inblock, (int32_t)length) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        out = now_lzss(st->inblock, length, outstart,
                       st->blkcap, &err);
    } else {                                      /* stored */
        if (unc_read_full(c->io, outstart, (int32_t)length) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        out = (int32_t)length;
        err = UNC_OK;
    }
    if (out < 0) return err;

    /* The window slides by the block's length: what was written at
     * outstart ends up just below it, and the last 32 KB become the
     * history for the next block. */
    for (i = 0; i < st->hist; i++)
        st->outblock[i] = st->outblock[i + (uint32_t)out];
    if (first)
        for (i = 0; i < st->hist; i++) st->dict[i] = st->outblock[i];

    st->avail = outstart - out;
    st->availlen = (uint32_t)out;
    return UNC_OK;
}

/* Serve `want` bytes of the current stream into a fork. */
static int now_fork(NowStream *st, UncFork fork, uint32_t want)
{
    UncCtx *c = st->c;
    int err;

    while (want > 0) {
        uint32_t n;
        if (st->availlen == 0) {
            if ((err = now_next_block(st)) != UNC_OK) return err;
            if (st->done) return UNC_ERR_TRUNCATED;
            continue;
        }
        n = st->availlen < want ? st->availlen : want;
        if (!c->opt.test_only && !c->opt.list_only &&
            c->sink->write(c->sink->ctx, fork, st->avail, (int32_t)n) < 0)
            return UNC_ERR_SINK;
        st->avail += n;
        st->availlen -= n;
        want -= n;
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* The entry table                                                    */
/* ------------------------------------------------------------------ */

typedef struct NowPath {
    uint8_t  buf[UNC_NAME_MAX + 1];
    uint16_t len;
    uint16_t stack[NOW_MAXDEPTH];
    uint32_t left[NOW_MAXDEPTH];   /* entries still owed at this level */
    int      depth;
} NowPath;

static void now_path_leaf(const NowPath *p, UncEntryInfo *e,
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

int unc_now_extract(UncCtx *c)
{
    uint8_t hdr[NOW_ENTRY];
    NowPath path;
    NowStream st;
    uint8_t *mem;
    uint32_t totalentries, seen = 0, at = 24;
    int err = UNC_OK;

    if (c->io->seek(c->io->ctx, 8) < 0) return UNC_ERR_IO;
    if (unc_read_full(c->io, hdr, 4) != UNC_OK) return UNC_ERR_FORMAT;
    totalentries = unc_get_u32be(hdr);
    if (totalentries == 0 || totalentries > 0xFFFFu) return UNC_ERR_FORMAT;

    /* Size the block buffers from the archive's LARGEST FORK, not from
     * the format's three ceilings.
     *
     * This allocation happens once per archive, before a single entry is
     * read, and at the ceilings it is 131,072 B. That is not headroom
     * anybody was spending: a Macintosh application's heap is its
     * MultiFinder partition, `unclassic.r` declares a 400 KB minimum, and
     * 150 KB of that partition is the application's own code. Measured at
     * a 110,000 B budget — about what the minimum partition leaves — Now
     * Compress opened NONE of its three fixtures, refused at this line
     * with a high-water of zero. A per-archive allocation that fails is
     * also the one shape the engine's contract does not allow: allocation
     * failure is supposed to be per ENTRY.
     *
     * The entry table carries each fork's uncompressed size at +86 and
     * +90, and ONE STREAM CARRIES BOTH FORKS — resource first, then data
     * — so the bound is their SUM, not the larger of the two. (Learned
     * from a unit test: a stream of one 11-byte block holding a 5-byte
     * resource fork and a 6-byte data fork overran a capacity of 6.)
     * One pass over the table bounds all three:
     *
     *   hist   <= NOW_HISTORY, and a back-reference cannot reach further
     *            back than the fork has produced, so <= maxout too
     *   blkcap <= NOW_OUTBLOCK - NOW_HISTORY, and one block's output is
     *            part of a fork, so <= maxout
     *   incap  is left at NOW_INBLOCK: a block's COMPRESSED length is not
     *            bounded by its output, and `length > incap` is a
     *            corruption test, so shrinking it could refuse a valid
     *            archive. 32 KB of the 128 stays.
     *
     * The tables go FIRST so their alignment is the allocator's own, and
     * everything after them is bytes. */
    {
        uint32_t maxout = 0, i, scanat = at, left = totalentries;
        while (left-- > 0) {
            uint32_t d, r;
            if (c->io->seek(c->io->ctx, scanat) < 0) return UNC_ERR_IO;
            if (unc_read_full(c->io, hdr, NOW_ENTRY) != UNC_OK) break;
            scanat += NOW_ENTRY;
            d = unc_get_u32be(hdr + 86);
            r = unc_get_u32be(hdr + 90);
            /* Saturate rather than wrap: a damaged header can declare
             * anything, and the two ceilings below clamp it anyway. */
            if (d > 0xFFFFFFFFu - r) d = 0xFFFFFFFFu - r;
            if (d + r > maxout) maxout = d + r;
        }
        st.hist   = maxout < NOW_HISTORY ? maxout : NOW_HISTORY;
        st.blkcap = maxout < (NOW_OUTBLOCK - NOW_HISTORY)
                    ? maxout : (NOW_OUTBLOCK - NOW_HISTORY);
        st.incap  = NOW_INBLOCK;
        /* A zero-length archive still needs somewhere to decode into. */
        if (st.blkcap == 0) st.blkcap = 1;

        /* Listing needs none of this, and a failure to get it is NOT the
         * archive's failure.
         *
         * This is the engine's only per-ARCHIVE allocation, and the
         * contract is that allocation failure is per entry, never per
         * archive (CLAUDE.md, 68000 discipline). Returning UNC_ERR_MEM
         * here refused the whole archive — no listing, no entry names,
         * nothing — and it made this one buffer the floor for whether
         * ANY Now archive opens at all: 137,264 B, against a 158,970 B
         * budget in the 400 KB minimum partition. Twenty-two kilobytes
         * of headroom, on an application that grew twenty-four in two
         * versions. Now the entries are still walked and named, and each
         * one that needs the buffer fails on its own. */
        mem = NULL;
        if (!c->opt.list_only) {
            mem = (uint8_t *)unc_alloc(c->al, (uint32_t)sizeof *st.cd
                                       + st.incap + st.hist + st.blkcap
                                       + st.hist);
        }
        st.c = c;
        if (mem) {
            st.cd       = (struct NowCodes *)(void *)mem;
            st.inblock  = mem + sizeof *st.cd;
            st.outblock = st.inblock + st.incap;
            st.dict     = st.outblock + st.hist + st.blkcap;
            for (i = 0; i < st.hist; i++) st.dict[i] = 0;
        } else {
            st.cd = NULL;
            st.inblock = st.outblock = st.dict = NULL;
        }
    }

    path.len = 0;
    path.depth = 0;

    while (seen < totalentries) {
        UncEntryInfo e;
        uint32_t nlen, datasize, rsrcsize, datastart, numdir;
        int flags, sret;

        if (c->io->seek(c->io->ctx, at) < 0) { err = UNC_ERR_IO; break; }
        if (unc_read_full(c->io, hdr, NOW_ENTRY) != UNC_OK) break;
        at += NOW_ENTRY;
        seen++;

        nlen = hdr[0];
        if (nlen > 31) nlen = 31;
        flags     = (int)unc_get_u16be(hdr + 36);
        datasize  = unc_get_u32be(hdr + 86);
        rsrcsize  = unc_get_u32be(hdr + 90);
        datastart = unc_get_u32be(hdr + 98);
        numdir    = unc_get_u16be(hdr + 82);

        unc_entry_clear(&e);
        now_path_leaf(&path, &e, hdr + 1, nlen);
        e.type         = unc_get_u32be(hdr + 38);
        e.creator      = unc_get_u32be(hdr + 42);
        e.finder_flags = unc_get_u16be(hdr + 46);
        e.create_date  = unc_get_u32be(hdr + 54);
        e.mod_date     = unc_get_u32be(hdr + 58);

        if (flags & 0x10) {                       /* directory */
            e.is_dir = 1;
            if (c->sink->begin_entry(c->sink->ctx, &e) < 0) { err = UNC_ERR_SINK; break; }
            if (c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) { err = UNC_ERR_SINK; break; }
        } else {
            e.data_size = datasize;
            e.rsrc_size = rsrcsize;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0) {
                int ferr = UNC_OK;
                if (!c->opt.list_only && (datasize || rsrcsize) &&
                    st.inblock == NULL) {
                    ferr = UNC_ERR_MEM;       /* per entry, not per archive */
                } else if (!c->opt.list_only && (datasize || rsrcsize)) {
                    ferr = now_stream_open(&st, datastart);
                    /* The forks come out of the stream in the order the
                     * archive stores them: resource first, then data. */
                    if (ferr == UNC_OK && rsrcsize)
                        ferr = now_fork(&st, UNC_FORK_RSRC, rsrcsize);
                    if (ferr == UNC_OK && datasize)
                        ferr = now_fork(&st, UNC_FORK_DATA, datasize);
                }
                if (c->sink->end_entry(c->sink->ctx, ferr) < 0) {
                    err = UNC_ERR_SINK;
                    break;
                }
                if (ferr == UNC_ERR_SINK || ferr == UNC_ERR_ABORTED ||
                    ferr == UNC_ERR_IO) {
                    err = ferr;
                    break;
                }
            }
        }

        /* This entry counts against the directory it is in; a directory
         * then opens one of its own. Levels close when their count runs
         * out, which is how an empty folder closes immediately.
         * Source: parseDirectoryWithParent, which does it by recursing. */
        if (path.depth > 0 && path.left[path.depth - 1] > 0)
            path.left[path.depth - 1]--;

        if ((flags & 0x10) && path.depth < NOW_MAXDEPTH) {
            path.stack[path.depth] = path.len;
            path.left[path.depth] = numdir;
            path.depth++;
            if (path.len && path.len < UNC_NAME_MAX) path.buf[path.len++] = '/';
            {
                uint32_t i;
                for (i = 0; i < nlen && path.len < UNC_NAME_MAX; i++) {
                    uint8_t ch = hdr[1 + i];
                    path.buf[path.len++] = (uint8_t)(ch == '/' ? ':' : ch);
                }
            }
            path.buf[path.len] = 0;
        }

        while (path.depth > 0 && path.left[path.depth - 1] == 0) {
            path.depth--;
            path.len = path.stack[path.depth];
            path.buf[path.len] = 0;
        }
    }

    unc_free(c->al, mem);
    return err;
}

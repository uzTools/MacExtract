/*
 * fmt_arc.c — ARC archives (.arc), the SEA/PKARC family, plus the
 * ArcMac container that wraps each entry in Macintosh metadata.
 *
 * Sources (transcribed, never guessed):
 *   reference/XADMaster/XADARCParser.m       — header walk, the method
 *       numbers, which methods chain RLE90, and the CRC-16 contract
 *       (IBM CRC-16 over the DECODED bytes, unconditioned).
 *   reference/XADMaster/XADRLE90Handle.m     — the 0x90 run filter.
 *   reference/XADMaster/XADSqueezeHandle.m   — method 4's Huffman tree.
 *   reference/XADMaster/XADARCCrunchHandle.m — methods 5/6/7, an LZW
 *       whose table is addressed by hash rather than by sequence.
 *   reference/macutils/macunpack/arc.h       — the ArcMac header, and
 *       the note that its second size field is a copy of the first
 *       ("this is wrong for Arc!"), which is why the uncompressed
 *       length of an ArcMac entry comes from the fork lengths.
 *   reference/macutils/README                — "ArcMac: nearly PC-Arc
 *       compatible", and the method list this file implements.
 *   reference/notes/ArcMac.DOC               — ArcMac's own specification,
 *       section "ArcMac File Structure": the header as a Pascal record,
 *       and the only statement anywhere of the fork lengths' byte order
 *       ("stored in archive using Intel 80xxx byte sex").
 *
 * What no document states is which fork an ArcMac payload starts with.
 * That was MEASURED — ArcMac 1.3c archiving a two-fork file under an
 * emulated Mac Plus, tools/vmac/arcmac.py — and it is the data fork.
 *
 * Methods 8, 9 and 0x7f are Unix compress with the parameters the
 * method fixes, so they run through unc_lzw.c unchanged.
 *
 * Methods 0x0a (Crushed) and 0x0b (Distilled) are PKARC's and are
 * DECLINED per entry: nothing in reach writes them, so an
 * implementation could not be graded (the DiskDoubler precedent,
 * DECISIONS.md 2026-08-15).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* Methods. Source: XADARCParser.m and macutils' arc.h, which agree. */
#define ARC_M_STORED_OLD  0x01
#define ARC_M_STORED      0x02
#define ARC_M_PACKED      0x03
#define ARC_M_SQUEEZED    0x04
#define ARC_M_CRUNCH5     0x05
#define ARC_M_CRUNCH6     0x06
#define ARC_M_CRUNCH7     0x07
#define ARC_M_CRUNCH8     0x08
#define ARC_M_SQUASHED    0x09
#define ARC_M_CRUSHED     0x0a
#define ARC_M_DISTILLED   0x0b
#define ARC_M_DIR         0x1e
#define ARC_M_DIREND      0x1f
#define ARC_M_COMPRESSED  0x7f

#define ARC_HDR_MIN       0x1d   /* 0x1a, method, 13 name, 4+2+2+2, 4 */
#define ARC_NAME_LEN      13

/* ArcMac field offsets. Source: reference/macutils/macunpack/arc.h. */
#define AM_MAGIC1      0
#define AM_KIND        1
#define AM_FNAME       2      /* 31 bytes, NUL-padded */
#define AM_FTYPE      34
#define AM_FAUTH      38
#define AM_FINFO      42
#define AM_FDATA      50      /* data fork length   */
#define AM_FRSRC      54      /* rsrc fork length   */
#define AM_MAGIC2     59      /* the PC ARC header starts here */
#define AM_HDRBYTES   88

/* Crunch: a 4096-entry table, addressed by hash. */
#define ARC_CRUNCH_SIZE  4096
#define ARC_STACK_SIZE   4096

/* Squeeze: at most 257 leaves, so 257 node pairs. */
#define ARC_SQ_MAXNODES  (257 * 2)

/* ------------------------------------------------------------------ */
/* Decoder state                                                      */
/* ------------------------------------------------------------------ */

typedef struct ArcDec {
    int        method;       /* method & 0x7f */
    UncBufIn  *in;
    UncAlloc  *al;
    uint8_t   *mem;          /* single allocation for the tables */

    uint32_t   left;         /* stored: input bytes still to copy    */

    /* RLE90 filter state (XADRLE90Handle). */
    int        rle;          /* filter enabled                        */
    int        rle_last;
    int32_t    rle_count;

    /* Squeeze (XADSqueezeHandle). */
    UncBitIn   bit;
    int16_t   *nodes;
    int32_t    numnodes;
    int        sq_eof;

    /* Crunch (XADARCCrunchHandle). */
    int16_t   *parent;       /* [4096], -1 = root                     */
    uint8_t   *cbyte;        /* [4096]                                */
    uint16_t  *next;         /* [4096]                                */
    uint8_t   *used;         /* [4096]                                */
    uint8_t   *stack;        /* [4096]                                */
    int32_t    sp;
    int32_t    numfree;
    int32_t    lastcode;
    int        lastbyte;
    int        fast;         /* method 7's hash                       */
    int        started;

    /* Unix compress (methods 8, 9, 0x7f). */
    UncLzw     lzw;
    int        lzw_open;
    uint8_t    lzwbuf[64];
    int32_t    lzwlen, lzwpos;
} ArcDec;

/* ------------------------------------------------------------------ */
/* Squeeze                                                            */
/* ------------------------------------------------------------------ */

static int arc_squeeze_init(ArcDec *d)
{
    int32_t i;
    int lo, hi, pairs;

    lo = unc_bufin_next(d->in);
    hi = unc_bufin_next(d->in);
    if (lo < 0 || hi < 0) return UNC_ERR_TRUNCATED;
    pairs = lo | (hi << 8);
    d->numnodes = (int32_t)pairs * 2;
    if (d->numnodes >= ARC_SQ_MAXNODES || d->numnodes < 2) return UNC_ERR_CORRUPT;

    for (i = 0; i < d->numnodes; i++) {
        int a = unc_bufin_next(d->in), b = unc_bufin_next(d->in);
        if (a < 0 || b < 0) return UNC_ERR_TRUNCATED;
        d->nodes[i] = (int16_t)(uint16_t)(a | (b << 8));
    }
    unc_bitin_init_le(&d->bit, d->in);
    d->sq_eof = 0;
    return UNC_OK;
}

/* -1 = end of stream, -2 = corrupt/short. */
static int arc_squeeze_byte(ArcDec *d)
{
    int32_t node = 0;
    int depth = 0;

    if (d->sq_eof) return -1;
    for (;;) {
        int bit = unc_bitin_bit(&d->bit);
        int32_t v;
        if (bit < 0) return -1;                 /* input ran out */
        if (2 * node + bit >= d->numnodes) return -2;
        v = d->nodes[2 * node + bit];
        if (v < 0) {
            int sym = (int)(-(v + 1));
            if (sym == 256) { d->sq_eof = 1; return -1; }
            if (sym < 0 || sym > 255) return -2;
            return sym;
        }
        node = v;
        if (++depth > 64) return -2;            /* cyclic tree */
    }
}

/* ------------------------------------------------------------------ */
/* Crunch (methods 5, 6, 7)                                           */
/* ------------------------------------------------------------------ */

static void arc_crunch_update(ArcDec *d, int32_t parentcode, int byte)
{
    uint32_t index;

    if (d->fast) {
        index = (((uint32_t)(parentcode + byte) & 0xffffu) * 15073u) & 0xfffu;
    } else {
        index = ((uint32_t)(parentcode + byte) | 0x0800u) & 0xffffu;
        index = ((index * index) >> 6) & 0xfffu;
    }

    if (d->used[index]) {
        uint32_t nx;
        while (d->next[index]) index = d->next[index];
        nx = (index + 101u) & 0xfffu;
        while (d->used[nx]) nx = (nx + 1u) & 0xfffu;
        d->next[index] = (uint16_t)nx;
        index = nx;
    }

    d->used[index]   = 1;
    d->next[index]   = 0;
    d->parent[index] = (int16_t)parentcode;
    d->cbyte[index]  = (uint8_t)byte;
}

static int arc_crunch_start(ArcDec *d)
{
    int32_t i, code;

    for (i = 0; i < ARC_CRUNCH_SIZE; i++) {
        d->used[i] = 0;
        d->next[i] = 0;
        d->parent[i] = -1;
        d->cbyte[i] = 0;
    }
    d->sp = 0;
    d->numfree = ARC_CRUNCH_SIZE - 256;
    for (i = 0; i < 256; i++) arc_crunch_update(d, -1, (int)i);

    /* MSB-first: XADARCCrunchHandle reads CSInputNextBitString, and it
     * is the LE-suffixed variant that means LSB-first (CSInputBuffer.h).
     * Reading these 12-bit codes the other way round decodes to
     * plausible-looking garbage that still satisfies our own CRC, so
     * the mistake only surfaced against `unar`. */
    unc_bitin_init(&d->bit, d->in);
    code = unc_bitin_bits(&d->bit, 12);
    if (code < 0) return UNC_ERR_TRUNCATED;
    d->lastcode = code;
    d->lastbyte = d->cbyte[code];
    d->stack[d->sp++] = (uint8_t)d->lastbyte;
    d->started = 1;
    return UNC_OK;
}

static int arc_crunch_byte(ArcDec *d)
{
    if (!d->started) {
        if (arc_crunch_start(d) != UNC_OK) return -1;
    }
    if (!d->sp) {
        int32_t code = unc_bitin_bits(&d->bit, 12);
        int32_t entry;
        int byte;

        if (code < 0) return -1;                 /* end of input */
        entry = code;
        if (!d->used[entry]) {
            entry = d->lastcode;
            if (d->sp >= ARC_STACK_SIZE) return -2;
            d->stack[d->sp++] = (uint8_t)d->lastbyte;
        }
        while (d->parent[entry] != -1) {
            if (d->sp >= ARC_STACK_SIZE - 1) return -2;
            d->stack[d->sp++] = d->cbyte[entry];
            entry = d->parent[entry];
        }
        byte = d->cbyte[entry];
        d->stack[d->sp++] = (uint8_t)byte;

        if (d->numfree != 0) {
            arc_crunch_update(d, d->lastcode, byte);
            d->numfree--;
        }
        d->lastcode = code;
        d->lastbyte = byte;
    }
    return d->stack[--d->sp];
}

/* ------------------------------------------------------------------ */
/* Producer: one pre-RLE byte                                         */
/* ------------------------------------------------------------------ */

static int arc_raw_byte(ArcDec *d)
{
    switch (d->method) {
    case ARC_M_STORED_OLD:
    case ARC_M_STORED:
    case ARC_M_PACKED:
        if (d->left == 0) return -1;
        {
            int b = unc_bufin_next(d->in);
            if (b < 0) return -1;
            d->left--;
            return b;
        }
    case ARC_M_SQUEEZED:
        return arc_squeeze_byte(d);
    case ARC_M_CRUNCH5:
    case ARC_M_CRUNCH6:
    case ARC_M_CRUNCH7:
        return arc_crunch_byte(d);
    default:                                     /* LZW family */
        if (d->lzwpos >= d->lzwlen) {
            int32_t n = unc_lzw_read(&d->lzw, d->lzwbuf, (int32_t)sizeof d->lzwbuf);
            if (n <= 0) return n == 0 ? -1 : -2;
            d->lzwlen = n;
            d->lzwpos = 0;
        }
        return d->lzwbuf[d->lzwpos++];
    }
}

/* One output byte, through the RLE90 filter where the method uses it.
 * Source: XADRLE90Handle.m. */
static int arc_byte(ArcDec *d)
{
    int b, c;

    if (!d->rle) return arc_raw_byte(d);

    if (d->rle_count) { d->rle_count--; return d->rle_last; }

    b = arc_raw_byte(d);
    if (b < 0) return b;
    if (b != 0x90) { d->rle_last = b; return b; }

    c = arc_raw_byte(d);
    if (c < 0) return c;
    if (c == 0) { d->rle_last = 0x90; return 0x90; }
    if (c == 1) return -2;
    d->rle_count = c - 2;
    return d->rle_last;
}

/* ------------------------------------------------------------------ */
/* Per-entry setup                                                    */
/* ------------------------------------------------------------------ */

static int arc_dec_init(ArcDec *d, UncCtx *c, UncBufIn *in, int method,
                        uint32_t compsize)
{
    int err = UNC_OK;

    d->in = in;
    d->al = c->al;
    d->mem = 0;
    d->method = method & 0x7f;
    d->left = compsize;
    d->rle = 0;
    d->rle_last = 0;
    d->rle_count = 0;
    d->sq_eof = 0;
    d->started = 0;
    d->lzw_open = 0;
    d->lzwlen = d->lzwpos = 0;
    d->fast = (d->method == ARC_M_CRUNCH7);

    switch (d->method) {
    case ARC_M_STORED_OLD:
    case ARC_M_STORED:
        break;
    case ARC_M_PACKED:
        d->rle = 1;
        break;
    case ARC_M_SQUEEZED:
        d->mem = (uint8_t *)unc_alloc(c->al, ARC_SQ_MAXNODES * 2u);
        if (!d->mem) return UNC_ERR_MEM;
        d->nodes = (int16_t *)(void *)d->mem;
        d->rle = 1;
        err = arc_squeeze_init(d);
        break;
    case ARC_M_CRUNCH5:
    case ARC_M_CRUNCH6:
    case ARC_M_CRUNCH7:
        /* parent[4096] u16 | next[4096] u16 | cbyte[4096] | used[4096]
         * | stack[4096] — one block, 2-aligned first for the u16s. */
        d->mem = (uint8_t *)unc_alloc(c->al, ARC_CRUNCH_SIZE * 6u + ARC_STACK_SIZE);
        if (!d->mem) return UNC_ERR_MEM;
        d->parent = (int16_t *)(void *)d->mem;
        d->next   = (uint16_t *)(void *)(d->mem + ARC_CRUNCH_SIZE * 2u);
        d->cbyte  = d->mem + ARC_CRUNCH_SIZE * 4u;
        d->used   = d->mem + ARC_CRUNCH_SIZE * 5u;
        d->stack  = d->mem + ARC_CRUNCH_SIZE * 6u;
        d->rle = (d->method != ARC_M_CRUNCH5);
        break;
    case ARC_M_CRUNCH8:
        /* A leading maxbits byte, which the format fixes at 12. */
        {
            int b = unc_bufin_next(in);
            if (b < 0) return UNC_ERR_TRUNCATED;
            if (b != 0x0c) return UNC_ERR_CORRUPT;
        }
        err = unc_lzw_init(&d->lzw, c->al, in, 12, 1, compsize);
        if (err == UNC_OK) d->lzw_open = 1;
        d->rle = 1;
        break;
    case ARC_M_SQUASHED:
        err = unc_lzw_init(&d->lzw, c->al, in, 13, 1, compsize);
        if (err == UNC_OK) d->lzw_open = 1;
        break;
    case ARC_M_COMPRESSED:
        {
            int b = unc_bufin_next(in);
            if (b < 0) return UNC_ERR_TRUNCATED;
            err = unc_lzw_init(&d->lzw, c->al, in, b & 0x1f, 1, compsize);
            if (err == UNC_OK) d->lzw_open = 1;
        }
        break;
    default:
        return UNC_ERR_UNSUPPORTED;
    }
    return err;
}

static void arc_dec_free(ArcDec *d)
{
    if (d->lzw_open) unc_lzw_free(&d->lzw, d->al);
    if (d->mem) unc_free(d->al, d->mem);
    d->mem = 0;
    d->lzw_open = 0;
}

/* ------------------------------------------------------------------ */
/* Header walk                                                        */
/* ------------------------------------------------------------------ */

static int arc_name_ok(const uint8_t *p)
{
    int i;
    if (p[0] == 0) return 0;
    for (i = 0; i < ARC_NAME_LEN && p[i] != 0; i++)
        if (p[i] < 32) return 0;
    return 1;
}

/* Trim as XADARCParser does: to the NUL, then one trailing space, then
 * one trailing dot. */
static uint32_t arc_name_len(const uint8_t *p)
{
    uint32_t n = 0;
    while (n < ARC_NAME_LEN - 1 && p[n] != 0) n++;
    if (n > 1 && p[n - 1] == ' ') n--;
    if (n > 1 && p[n - 1] == '.') n--;
    return n;
}

int unc_arc_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t compsize, uncompsize, nextoff;
    int method;
    uint8_t nb[1];

    if (len < ARC_HDR_MIN) return 0;

    /* ArcMac: the Mac header, then the PC one 59 bytes in. */
    if (head[AM_MAGIC1] == 0x1b && len >= AM_HDRBYTES &&
        head[AM_MAGIC2] == 0x1a && head[AM_KIND] != 0 &&
        head[AM_KIND] == head[AM_MAGIC2 + 1])
        return 1;

    if (head[0] != 0x1a) return 0;
    method = head[1];
    if (method == 0) return 0;
    if (method != ARC_M_DIR && method != ARC_M_DIREND &&
        (method & 0x7f) > ARC_M_DISTILLED && (method & 0x7f) != ARC_M_COMPRESSED)
        return 0;
    if (!arc_name_ok(head + 2)) return 0;

    compsize = unc_get_u32le(head + 0x0f);
    if (method == ARC_M_STORED_OLD) {
        if (compsize > 0x1000000u) return 0;
        nextoff = 0x19u + compsize;
    } else {
        if (len < 0x1d) return 0;
        uncompsize = unc_get_u32le(head + 0x19);
        if (uncompsize > 0x1000000u) return 0;
        if (compsize > uncompsize) return 0;
        nextoff = 0x1du + compsize;
        if (method & 0x80) nextoff += 12u;
    }

    /* The strongest thing an ARC file says about itself: the next
     * header, or the end marker, sits exactly where the size puts it. */
    if ((int32_t)nextoff < len) return head[nextoff] == 0x1a;
    if (!io) return 0;
    if (unc_read_at(io, nextoff, nb, 1) != UNC_OK) return 0;
    return nb[0] == 0x1a;
}

/* Write one run of decoded bytes, splitting it across the two forks.
 *
 * `at` is the offset of buf[0] within the entry's single stream and
 * `dsplit` how much of that stream is the data fork — the whole of it for
 * plain ARC, the header's data-fork length for ArcMac. A run can straddle
 * the boundary, so it is written in at most two pieces.
 * Source: the fork order is measured, tools/vmac/arcmac.py. */
static int arc_emit(UncCtx *c, uint32_t at, const uint8_t *buf, int32_t n,
                    uint32_t dsplit)
{
    if (at < dsplit) {
        int32_t k = (int32_t)(dsplit - at);
        if (k > n) k = n;
        if (c->sink->write(c->sink->ctx, UNC_FORK_DATA, buf, k) != 0)
            return UNC_ERR_SINK;
        buf += k;
        n -= k;
    }
    if (n > 0 && c->sink->write(c->sink->ctx, UNC_FORK_RSRC, buf, n) != 0)
        return UNC_ERR_SINK;
    return UNC_OK;
}

/* Decode one entry's stream into the sink, checking the CRC.         */
static int arc_entry_data(UncCtx *c, UncBufIn *in, int method,
                          uint32_t compsize, uint32_t outsize, uint16_t crc16,
                          int write, uint32_t dsplit)
{
    ArcDec d;
    uint8_t out[512];
    int32_t n = 0;
    uint32_t produced = 0;
    uint16_t crc = 0;
    int err;

    err = arc_dec_init(&d, c, in, method, compsize);
    if (err != UNC_OK) { arc_dec_free(&d); return err; }

    for (;;) {
        int b;
        if (outsize != UNC_SIZE_UNKNOWN && produced >= outsize) break;
        b = arc_byte(&d);
        if (b == -1) break;
        if (b < -1) { err = UNC_ERR_CORRUPT; break; }
        out[n++] = (uint8_t)b;
        produced++;
        if (n == (int32_t)sizeof out) {
            crc = unc_crc16_arc(crc, out, n);
            if (write) {
                err = arc_emit(c, produced - (uint32_t)n, out, n, dsplit);
                if (err != UNC_OK) break;
            }
            n = 0;
        }
    }
    if (err == UNC_OK && n > 0) {
        crc = unc_crc16_arc(crc, out, n);
        if (write)
            err = arc_emit(c, produced - (uint32_t)n, out, n, dsplit);
    }
    arc_dec_free(&d);

    if (err != UNC_OK) return err;
    if (outsize != UNC_SIZE_UNKNOWN && produced != outsize) return UNC_ERR_TRUNCATED;
    if (crc != crc16) return UNC_ERR_CRC;
    return UNC_OK;
}

int unc_arc_extract(UncCtx *c)
{
    uint8_t hdr[ARC_HDR_MIN + 12];
    uint8_t *iobuf;
    uint32_t iocap = 4096;
    uint32_t pos = 0;
    uint8_t  path[UNC_NAME_MAX + 1];
    uint32_t plen = 0;
    int err = UNC_OK, any = 0, arcmac = 0;
    UncBufIn in;

    /* ArcMac? Its Mac header precedes the PC one; the whole file is
     * either one shape or the other. */
    {
        uint8_t probe[AM_HDRBYTES];
        if (unc_read_at(c->io, 0, probe, AM_HDRBYTES) == UNC_OK &&
            probe[AM_MAGIC1] == 0x1b && probe[AM_MAGIC2] == 0x1a)
            arcmac = 1;
    }

    iobuf = (uint8_t *)unc_alloc(c->al, iocap);
    if (!iobuf) return UNC_ERR_MEM;

    for (;;) {
        UncEntryInfo e;
        uint8_t macname[32];
        uint32_t compsize, uncompsize, dlen = 0, rlen = 0;
        uint32_t mactype = 0, maccreator = 0;
        uint16_t crc16;
        int method, sret, est;

        if (arcmac) {
            uint8_t mh[AM_HDRBYTES];
            uint32_t i;
            if (unc_read_at(c->io, pos, mh, AM_HDRBYTES) != UNC_OK) break;
            if (mh[AM_MAGIC1] != 0x1b || mh[AM_MAGIC2] != 0x1a) break;
            method = mh[AM_KIND];
            if (method == 0) break;
            for (i = 0; i < 31 && mh[AM_FNAME + i]; i++) macname[i] = mh[AM_FNAME + i];
            macname[i] = 0;
            mactype    = unc_get_u32be(mh + AM_FTYPE);
            maccreator = unc_get_u32be(mh + AM_FAUTH);
            /* Little-endian, like every other sized field in an ARC
             * header. ARCMAC.DOC marks the fork lengths, with size, date,
             * time and crc, as "stored in archive using Intel 80xxx byte
             * sex"; arc.h gives the offsets but not the order, and this
             * read was big-endian until 2026-08-16. Both archives in the
             * wild confirm it: little-endian, the pair sums to the
             * header's own uncompressed size on every entry.
             * Source: reference/notes/ArcMac.DOC, "ArcMac File Structure". */
            dlen = unc_get_u32le(mh + AM_FDATA);
            rlen = unc_get_u32le(mh + AM_FRSRC);
            compsize = unc_get_u32le(mh + AM_MAGIC2 + 0x0f);
            crc16 = unc_get_u16le(mh + AM_MAGIC2 + 0x17);
            uncompsize = dlen + rlen;
            pos += AM_HDRBYTES;

            unc_entry_clear(&e);
            unc_entry_set_name(&e, macname, i);
            e.type = mactype;
            e.creator = maccreator;
            e.data_size = dlen;
            e.rsrc_size = rlen;
            e.comp_data_size = compsize;
            e.method_data = (uint8_t)(method & 0x7f);

            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0) {
                /* One compressed stream holds both forks, data fork
                 * first. Nothing states the order — macunpack's arc.c,
                 * the only implementation that ever read the payload, is
                 * absent from the distribution — so it was MEASURED, by
                 * having ArcMac 1.3c itself archive a two-fork file under
                 * the emulator: tools/vmac/arcmac.py, and DECISIONS.md.
                 * The CRC covers the concatenation, so it grades the
                 * split as well as the decode. */
                est = UNC_OK;
                if (!c->opt.list_only) {
                    if (c->io->seek(c->io->ctx, pos) < 0) {
                        est = UNC_ERR_IO;
                    } else {
                        unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
                        in.limit = compsize;
                        est = arc_entry_data(c, &in, method & 0x7f, compsize,
                                             uncompsize, crc16,
                                             !c->opt.test_only, dlen);
                    }
                }
                if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                    err = UNC_ERR_SINK;
                    break;
                }
            }
            any = 1;
            pos += compsize;
            continue;
        }

        if (unc_read_at(c->io, pos, hdr, ARC_HDR_MIN) != UNC_OK) break;
        if (hdr[0] != 0x1a) break;
        method = hdr[1];
        if (method == 0) break;                       /* end of archive */

        if (method == ARC_M_DIREND || method == 0x80) {
            /* Leave the current directory. */
            while (plen > 0 && path[plen - 1] != '/') plen--;
            if (plen > 0) plen--;
            pos += 2;
            continue;
        }

        compsize = unc_get_u32le(hdr + 0x0f);
        crc16    = unc_get_u16le(hdr + 0x17);
        if (method == ARC_M_STORED_OLD) {
            uncompsize = compsize;
            pos += 0x19u;
        } else {
            uncompsize = unc_get_u32le(hdr + 0x19);
            pos += 0x1du;
            if (method & 0x80) pos += 12u;            /* Archimedes fields */
        }

        if (!arc_name_ok(hdr + 2)) { err = UNC_ERR_CORRUPT; break; }

        if (method == ARC_M_DIR) {
            uint32_t nl = arc_name_len(hdr + 2), i;
            if (plen > 0 && plen < UNC_NAME_MAX) path[plen++] = '/';
            for (i = 0; i < nl && plen < UNC_NAME_MAX; i++)
                path[plen++] = hdr[2 + i] == '/' ? (uint8_t)':' : hdr[2 + i];
            any = 1;
            pos += compsize;
            continue;
        }

        unc_entry_clear(&e);
        if (plen) {
            unc_entry_set_path(&e, path, plen);
            unc_entry_path_append(&e, hdr + 2, arc_name_len(hdr + 2));
        } else {
            unc_entry_set_name(&e, hdr + 2, arc_name_len(hdr + 2));
        }
        e.data_size = uncompsize;
        e.rsrc_size = 0;
        e.comp_data_size = compsize;
        e.method_data = (uint8_t)(method & 0x7f);

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; break; }
        if (sret == 0) {
            est = UNC_OK;
            if (!c->opt.list_only) {
                if (c->io->seek(c->io->ctx, pos) < 0) {
                    est = UNC_ERR_IO;
                } else {
                    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
                    in.limit = compsize;
                    est = arc_entry_data(c, &in, method, compsize, uncompsize,
                                         crc16, !c->opt.test_only, uncompsize);
                }
            }
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
        }
        any = 1;
        pos += compsize;
    }

    unc_free(c->al, iobuf);
    if (!any && err == UNC_OK) return UNC_ERR_FORMAT;
    return err;
}

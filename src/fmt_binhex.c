/*
 * fmt_binhex.c — BinHex 4.0 (.hqx) decoder.
 *
 * A BinHex file is 7-bit mail-safe text: a banner line
 * "(This file must be converted with BinHex ...)", then a ':',
 * a 6-bit-encoded stream (64-char alphabet, ':' terminates), with a
 * 0x90-marker RLE applied *inside* the decoded byte stream.
 *
 * Decoded layout:
 *   u8  namelen (1..63)     name bytes (MacRoman)
 *   u8  version
 *   u32 type, u32 creator, u16 finderflags
 *   u32 datalen, u32 rsrclen
 *   u16 header CRC          (CRC-16/XMODEM over everything above)
 *   datalen bytes of data fork, u16 CRC
 *   rsrclen bytes of rsrc fork, u16 CRC
 *
 * Everything transcribed from:
 *   Source: reference/XADMaster/XADBinHexParser.m — LGPL, see NOTICE.
 * (Alphabet string, RLE semantics incl. "count==1 is illegal",
 * banner scanning, ':'-after-whitespace start condition, fork CRCs
 * computed over the fully decoded stream.)
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* The 64-character BinHex alphabet, index = 6-bit value.
 * Source: reference/XADMaster/XADBinHexParser.m (GetBits). */
static const char bh_alphabet[65] =
    "!\"#$%&'()*+,-012345689@ABCDEFGHIJKLMNPQRSTUVXYZ[`abcdefhijklmpqr";

static const char bh_banner[40] = "(This file must be converted with BinHex";

/* How far into the file we are willing to look for the banner when
 * sniffing (XADMaster inspects the first 8 KB). */
#define BH_SNIFF_LIMIT 8192

/* ------------------------------------------------------------------ */
/* Probe: banner within the head buffer, then EOL, whitespace, ':'.   */
/* ------------------------------------------------------------------ */

int unc_binhex_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    /* The banner can sit deep inside mail headers/digests, so scan up
     * to BH_SNIFF_LIMIT bytes (XADMaster inspects 8 KB too): first the
     * sniff head we were given, then onward from the io handle with a
     * rolling 40-byte window. */
    uint8_t window[40];
    uint8_t chunk[256];
    int32_t have = 0, w = 0, scanned = 0, pos = 0, clen = 0, cpos = 0;
    int found = 0;

    /* Earlier probes may have moved the position; continue after head. */
    if (io->seek(io->ctx, (uint32_t)len) < 0) return 0;

    while (!found && scanned < BH_SNIFF_LIMIT) {
        int ch;
        int32_t i;
        if (pos < len) {
            ch = head[pos++];
        } else {
            if (cpos >= clen) {
                clen = io->read(io->ctx, chunk, (int32_t)sizeof chunk);
                if (clen <= 0) break;
                cpos = 0;
            }
            ch = chunk[cpos++];
        }
        scanned++;
        window[w] = (uint8_t)ch;
        if (++w == 40) w = 0;
        if (have < 40) have++;
        if (have == 40) {
            int32_t j = w;
            for (i = 0; i < 40; i++) {
                if (window[j] != (uint8_t)bh_banner[i]) break;
                if (++j == 40) j = 0;
            }
            if (i == 40) found = 1;
        }
    }
    return found;
}

/* ------------------------------------------------------------------ */
/* Decoder state                                                      */
/* ------------------------------------------------------------------ */

/* A BinHex line is 64 characters; the buffer is larger so that a file
 * written with longer lines still reads. A line that overflows it is
 * handed over in pieces, which is harmless: every piece is judged by
 * the same rule and the character order is unchanged. */
#define BH_LINE_MAX 256

typedef struct BhDec {
    UncBufIn in;
    /* One line at a time, because a document can have MAIL between its
     * lines — the shape a file posted in several parts arrives in. See
     * bh_refill_line. */
    uint8_t  line[BH_LINE_MAX];
    int32_t  llen, lpos;
    uint8_t  lut[256];    /* char -> 6-bit value, 0xFF = invalid, 0xFE = ':' */
    uint32_t phase;       /* decoded-byte counter mod 3 */
    uint8_t  prev_bits;
    int      eof;         /* saw terminating ':' */
    /* RLE layer */
    uint8_t  rle_byte;
    uint32_t rle_num;
    int      err;         /* sticky decoder error */
} BhDec;

static void bh_init(BhDec *d, UncCtx *c, uint8_t *storage, uint32_t cap)
{
    uint32_t i;
    unc_bufin_init(&d->in, c->io, &c->ps, storage, cap);
    for (i = 0; i < 256; i++) d->lut[i] = 0xFF;
    for (i = 0; i < 64; i++) d->lut[(uint8_t)bh_alphabet[i]] = (uint8_t)i;
    d->lut[':'] = 0xFE;
    d->phase = 0;
    d->prev_bits = 0;
    d->eof = 0;
    d->rle_byte = 0;
    d->rle_num = 0;
    d->llen = d->lpos = 0;
    d->err = UNC_OK;
}

/* Read the next line and decide whether it belongs to the document.
 *
 * Source: reference/macutils/hexbin/hqx.c, which checks each line "for
 * intermediate garbage" and skips the whole line when it finds any —
 * that is what lets it read a file posted in several parts, each part
 * carrying its own mail header, and it is why the BinHex alphabet
 * omitting n, o, s, t, u and the space is load-bearing: ordinary prose
 * fails within a few characters.
 *
 * ONE HALF of hexbin's rule is deliberately not transcribed: it also
 * skips any line whose length differs from the first line's, with a
 * look-ahead exception for the last one. That test can discard a
 * legitimate short final line (hexbin ships `-c` to turn it off), and
 * the alphabet half already rejects every header shape measured here.
 * What it would have caught — a junk line built only of alphabet
 * characters — is caught by BinHex's own per-fork CRC instead, as a
 * per-entry error rather than as silence. */
static int bh_refill_line(BhDec *d)
{
    for (;;) {
        int ch;
        int32_t i;
        int ok = 1;

        d->llen = d->lpos = 0;
        for (;;) {
            ch = unc_bufin_next(&d->in);
            if (ch < 0) {
                if (d->llen == 0) { d->err = d->in.err; return -1; }
                break;
            }
            if (ch == '\n' || ch == '\r') break;
            if (d->llen >= BH_LINE_MAX) break;      /* hand over in pieces */
            d->line[d->llen++] = (uint8_t)ch;
        }
        /* Mailers eat trailing whitespace; hexbin trims it before
         * judging the line, so a trimmed line is not "garbage". */
        while (d->llen > 0 && (d->line[d->llen - 1] == ' ' ||
                               d->line[d->llen - 1] == '\t'))
            d->llen--;
        if (d->llen == 0) continue;                 /* blank line */

        for (i = 0; i < d->llen; i++)
            if (d->lut[d->line[i]] == 0xFF) { ok = 0; break; }
        if (ok) return UNC_OK;
    }
}

/* Next 6-bit group, from a line that belongs to the document; ':' ends
 * the stream. Returns -1 on end/error with d->err set. */
static int bh_get_bits(BhDec *d)
{
    for (;;) {
        uint8_t v;
        if (d->lpos >= d->llen) {
            if (bh_refill_line(d) != UNC_OK) return -1;
            continue;
        }
        v = d->lut[d->line[d->lpos++]];
        if (v == 0xFF) continue;                    /* cannot happen */
        if (v == 0xFE) { d->eof = 1; d->err = UNC_ERR_TRUNCATED; return -1; }
        return v;
    }
}

/* Next byte of the 6-bit layer (pre-RLE). */
static int bh_decode_byte(BhDec *d)
{
    int bits1, bits2;
    switch (d->phase++ % 3) {
    case 0:
        bits1 = bh_get_bits(d);
        if (bits1 < 0) return -1;
        bits2 = bh_get_bits(d);
        if (bits2 < 0) return -1;
        d->prev_bits = (uint8_t)bits2;
        return ((bits1 << 2) | (bits2 >> 4)) & 0xFF;
    case 1:
        bits1 = d->prev_bits;
        bits2 = bh_get_bits(d);
        if (bits2 < 0) return -1;
        d->prev_bits = (uint8_t)bits2;
        return ((bits1 << 4) | (bits2 >> 2)) & 0xFF;
    default:
        bits1 = d->prev_bits;
        bits2 = bh_get_bits(d);
        if (bits2 < 0) return -1;
        return ((bits1 << 6) | bits2) & 0xFF;
    }
}

/* Next fully decoded byte (post-RLE). 0x90 <count>: count==0 emits a
 * literal 0x90; count==1 is illegal; else the previous byte repeats
 * count-1 more times. */
static int bh_next(BhDec *d)
{
    int byte, count;
    if (d->err != UNC_OK) return -1;
    if (d->rle_num) {
        d->rle_num--;
        return d->rle_byte;
    }
    byte = bh_decode_byte(d);
    if (byte < 0) return -1;
    if (byte != 0x90) {
        d->rle_byte = (uint8_t)byte;
        return byte;
    }
    count = bh_decode_byte(d);
    if (count < 0) return -1;
    if (count == 0) {
        d->rle_byte = 0x90;
        return 0x90;
    }
    if (count == 1) { d->err = UNC_ERR_CORRUPT; return -1; }
    d->rle_num = (uint32_t)count - 2;
    return d->rle_byte;
}

/* ------------------------------------------------------------------ */
/* Extraction                                                         */
/* ------------------------------------------------------------------ */

/* Scan the raw input for the banner; position after end of that line.
 *
 * `limited` bounds the scan, which is right for the FIRST document — a
 * mail preamble is short, and a file that is not BinHex at all should be
 * given up on rather than read whole. It is wrong for every document
 * after it: the text between two postings is a whole posting, and in
 * list mode the previous document's own encoded stream has not been
 * consumed, so the distance to the next banner is the size of the file.
 * Source: reference/macutils/hexbin/hexbin.c, which decodes a document
 * and then does `again = 1; goto nexttry` to look for the next header in
 * the same input, its find_header() scanning to EOF.
 *
 * Returns UNC_OK or UNC_ERR_FORMAT. */
static int bh_find_banner(UncBufIn *in, int limited)
{
    uint8_t window[40];
    uint32_t have = 0, w = 0, scanned = 0;
    int ch;

    /* Rolling comparison without shifting: circular buffer holding the
     * last 40 bytes; oldest byte lives at index w.
     *
     * The wrap is a conditional subtract, not a `%`. Both indices are
     * already below 40 so it is exact — and the divisor being a constant
     * does not save a 68000, which has no 32-bit multiply for gcc to
     * build a magic-number reciprocal out of, so `% 40` inside a
     * 40-iteration inner loop was 40 calls to __umodsi3 per byte of mail
     * header scanned. */
    for (;;) {
        uint32_t i = 0;
        ch = unc_bufin_next(in);
        if (ch < 0) return UNC_ERR_FORMAT;
        window[w] = (uint8_t)ch;
        if (++w == 40) w = 0;
        if (have < 40) have++;
        if (have == 40) {
            uint32_t j = w;
            for (i = 0; i < 40; i++) {
                if (window[j] != (uint8_t)bh_banner[i]) break;
                if (++j == 40) j = 0;
            }
            if (i == 40) break;
        }
        if (limited && ++scanned > 4 * BH_SNIFF_LIMIT) return UNC_ERR_FORMAT;
    }
    do {
        ch = unc_bufin_next(in);
        if (ch < 0) return UNC_ERR_FORMAT;
    } while (ch != '\n' && ch != '\r');
    return UNC_OK;
}

/* Position the 6-bit decoder start: ':' preceded by line break or
 * whitespace (source: resetByteStream in the reference). */
static int bh_find_colon(UncBufIn *in)
{
    int prev = '\n', curr;
    for (;;) {
        curr = unc_bufin_next(in);
        if (curr < 0) return UNC_ERR_FORMAT;
        if (curr == ':' && (prev == '\n' || prev == '\r' ||
                            prev == '\t' || prev == ' '))
            return UNC_OK;
        prev = curr;
    }
}

/* Decode `size` bytes to the sink fork, then verify the trailing CRC.
 * Returns UNC_OK / UNC_ERR_CRC / decoder error. */
static int bh_fork(UncCtx *c, BhDec *d, UncFork fork, uint32_t size,
                   uint8_t *obuf, uint32_t ocap)
{
    uint32_t left = size;
    uint16_t crc = 0;
    int b1, b2;

    while (left > 0) {
        uint32_t n = 0;
        while (n < ocap && n < left) {
            int b = bh_next(d);
            if (b < 0) return d->err != UNC_OK ? d->err : UNC_ERR_TRUNCATED;
            obuf[n++] = (uint8_t)b;
        }
        crc = unc_crc16_xmodem(crc, obuf, (int32_t)n);
        if (!c->opt.test_only && !c->opt.list_only &&
            c->sink->write(c->sink->ctx, fork, obuf, (int32_t)n) < 0)
            return UNC_ERR_SINK;
        left -= n;
    }
    b1 = bh_next(d);
    b2 = bh_next(d);
    if (b1 < 0 || b2 < 0) return UNC_ERR_TRUNCATED;
    if ((uint16_t)((b1 << 8) | b2) != crc) return UNC_ERR_CRC;
    return UNC_OK;
}

/* Decoder state for the next document. The input cursor and its buffer
 * carry on; everything the 6-bit and RLE layers hold does not, including
 * the sticky error the terminating ':' of the previous document set. */
static void bh_reset(BhDec *d)
{
    d->llen = d->lpos = 0;
    d->phase = 0;
    d->prev_bits = 0;
    d->eof = 0;
    d->rle_byte = 0;
    d->rle_num = 0;
    d->err = UNC_OK;
}

/* One BinHex document, from just after its ':' to the end of its forks. */
static int bh_document(UncCtx *c, BhDec *d, uint8_t *obuf, uint32_t ocap)
{
    UncEntryInfo e;
    uint8_t hdr[64 + 20];
    uint32_t namelen, datalen, rsrclen, i;
    uint16_t hcrc;
    int err, sret, b;

    /* Header: namelen, name, version, type, creator, flags, lens, CRC. */
    b = bh_next(d);
    if (b < 0) return UNC_ERR_FORMAT;
    namelen = (uint32_t)b;
    if (namelen < 1 || namelen > 63) return UNC_ERR_FORMAT;
    hdr[0] = (uint8_t)namelen;
    for (i = 0; i < namelen + 19; i++) {
        b = bh_next(d);
        if (b < 0) return UNC_ERR_TRUNCATED;
        hdr[1 + i] = (uint8_t)b;
    }
    b = bh_next(d);
    if (b < 0) return UNC_ERR_TRUNCATED;
    hcrc = (uint16_t)(b << 8);
    b = bh_next(d);
    if (b < 0) return UNC_ERR_TRUNCATED;
    hcrc |= (uint16_t)b;
    if (unc_crc16_xmodem(0, hdr, (int32_t)(namelen + 20)) != hcrc)
        return UNC_ERR_CRC;

    unc_entry_clear(&e);
    unc_entry_set_name(&e, hdr + 1, namelen);
    /* hdr[1+namelen] is the version byte (ignored, per reference). */
    e.type         = unc_get_u32be(hdr + 1 + namelen + 1);
    e.creator      = unc_get_u32be(hdr + 1 + namelen + 5);
    e.finder_flags = unc_get_u16be(hdr + 1 + namelen + 9);
    datalen = unc_get_u32be(hdr + 1 + namelen + 11);
    rsrclen = unc_get_u32be(hdr + 1 + namelen + 15);
    e.data_size = datalen;
    e.rsrc_size = rsrclen;

    /* Sanity: 6-bit coding expands 3 bytes to 4 chars; decoded output
     * can never exceed input*3/4 unless RLE is present, but RLE caps
     * expansion at 255x. Just cap against something sane. */
    if (c->ps.total != UNC_SIZE_UNKNOWN) {
        uint32_t cap255 = c->ps.total > 0x00FFFFFFu ? 0xFFFFFFFEu
                                                    : c->ps.total * 255u;
        if (datalen > cap255 || rsrclen > cap255) return UNC_ERR_CORRUPT;
    }

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) return UNC_ERR_SINK;
    if (sret > 0) return UNC_OK;

    err = UNC_OK;
    if (!c->opt.list_only) {
        err = bh_fork(c, d, UNC_FORK_DATA, datalen, obuf, ocap);
        if (err == UNC_OK)
            err = bh_fork(c, d, UNC_FORK_RSRC, rsrclen, obuf, ocap);
    }

    if (c->sink->end_entry(c->sink->ctx, err) < 0) return UNC_ERR_SINK;
    if (err != UNC_ERR_SINK && err != UNC_ERR_ABORTED && err != UNC_ERR_IO)
        err = UNC_OK;
    return err;
}

/* A .hqx file can hold MORE THAN ONE document — several files posted in
 * one message, which is what comp.binaries.mac produced and what this
 * decoder took the first of, exit 0, until 2026-08-15. Each document is
 * banner, ':', stream, ':'; after one ends we look for the next banner,
 * exactly as the reference does (see bh_find_banner).
 *
 * A banner with no usable document after it is an ERROR, not a quiet
 * stop: swallowing it is how the single-document version hid the rest of
 * a posting for as long as it did. */
int unc_binhex_extract(UncCtx *c)
{
    BhDec d;
    uint8_t *iobuf, *obuf;
    uint32_t iocap = 4096, ocap = 4096;
    uint32_t docs;
    int err;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;

    bh_init(&d, c, iobuf, iocap);

    for (docs = 0; ; docs++) {
        err = bh_find_banner(&d.in, docs == 0);
        if (err != UNC_OK) {
            /* No further banner. For the first document that means the
             * file is not BinHex; after one, it means the file is over —
             * unless the reader itself failed, which is not an end. */
            if (docs > 0)
                err = (d.in.err == UNC_ERR_IO || d.in.err == UNC_ERR_ABORTED)
                      ? d.in.err : UNC_OK;
            break;
        }
        err = bh_find_colon(&d.in);
        if (err != UNC_OK) break;
        bh_reset(&d);
        err = bh_document(c, &d, obuf, ocap);
        if (err != UNC_OK) break;
    }

    unc_free(c->al, iobuf);
    return err;
}

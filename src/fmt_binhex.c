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
 * Source: reference/notes/binhex40_lewis.txt — Peter N Lewis, "BinHex
 * 4.0 Definition", August 1991, which is the only full statement of the
 * format there is; and reference/notes/rfc1741.txt Appendix A, which
 * repeats the layout, the banner and the 0x90 run encoding.
 *
 * The RFC is the weaker of the two and in one place it is wrong: its
 * rendering of the alphabet carries a stray space and is 65 characters
 * long, so a reader holding only the RFC cannot say what the 64
 * characters are. Lewis's document also has what the RFC has not — the
 * CRC (polynomial 0x1021, initial register zero, restarted for each of
 * the three sections and taken over the decoded bytes) and the rule
 * that a run count of zero means a literal 0x90.
 *
 * One behaviour here is in neither document and is this project's: a
 * run count of ONE is rejected (unc_rle90's strict mode). Lewis defines
 * counts of zero and of two-and-up and says nothing about one;
 * macutils' hexbin emits the byte once and says nothing either.
 * Refusing it costs nothing a real encoder writes, and turns a
 * malformed stream into a per-entry error instead of into plausible
 * output.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"
#include "fmt_binhex_priv.h"

/* The 64-character BinHex alphabet, index = 6-bit value. Source:
 * binhex40_lewis.txt, "This string defines the valid characters, in
 * order" — not RFC 1741's copy of it, which has 65 characters in it. */
static const char bh_alphabet[65] =
    "!\"#$%&'()*+,-012345689@ABCDEFGHIJKLMNPQRSTUVXYZ[`abcdefhijklmpqr";

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
    uint32_t phase;       /* 0, 1 or 2: which third of the 4-group ->
                           * 3-byte cycle the next byte comes from. Kept
                           * ALREADY REDUCED rather than counted and taken
                           * mod 3, because that modulo ran once per output
                           * byte and a 68000 has no divide instruction.
                           */
    uint8_t  batch[2];    /* bytes 2 and 3 of a group decoded at once */
    uint8_t *bp, *bend;   /* what is left of them; equal when none is */
    uint8_t  prev_bits;
    int      eof;         /* saw terminating ':' */
    int      in_gap;      /* between "--- end of part" and "---" */
    /* RLE layer */
    UncRle90 rle;
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
    d->bp = d->bend = d->batch;
    d->prev_bits = 0;
    d->eof = 0;
    d->in_gap = 0;
    unc_rle90_init(&d->rle, 1);
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
        const uint8_t *q;
        uint32_t avail;
        int32_t n = 0, i;
        int ok = 1;

        d->llen = d->lpos = 0;

        /* The line is normally in the reader's buffer already, all 64
         * characters and the terminator with them, so it is taken in
         * one scan for that terminator rather than one call, one bounds
         * test and one cursor store per character. */
        avail = unc_bufin_span(&d->in, &q);
        if (avail > (uint32_t)BH_LINE_MAX) avail = (uint32_t)BH_LINE_MAX;
        while ((uint32_t)n < avail && q[n] != '\n' && q[n] != '\r') n++;
        if ((uint32_t)n < avail) {
            unc_bufin_drop(&d->in, (uint32_t)n + 1u);   /* and the terminator */
        } else {
            /* Not in hand: the line straddles a refill, or ends with
             * the file, or is longer than the buffer. One character at
             * a time, and a line that overflows is handed over in
             * pieces — harmless, because every piece is judged by the
             * same rule and the character order is unchanged. */
            int ch;
            n = 0;                      /* the scan above found nothing */
            for (;;) {
                ch = unc_bufin_next(&d->in);
                if (ch < 0) {
                    if (n == 0) { d->err = d->in.err; return -1; }
                    break;
                }
                if (ch == '\n' || ch == '\r') break;
                if (n >= BH_LINE_MAX) break;
                d->line[n++] = (uint8_t)ch;
            }
            q = d->line;
        }

        /* Mailers eat trailing whitespace; hexbin trims it before
         * judging the line, so a trimmed line is not "garbage".
         *
         * THE TAB IS OURS. `hqx.c` tests `line[n - 1] == ' '` and
         * nothing else, and a tab is FAIL in its lookup, so a line
         * ending in one is skipped there and read here. Corrected
         * 2026-10-07: the sentence above attributed both characters to
         * a source that states one. What the second one does have is a
         * second implementation — HQXer 1.1's inverse table marks TAB
         * skippable ANYWHERE in a line, with BS, LF, CR and the space
         * (tools/derive_hqxgarbage.py --tables). */
        while (n > 0 && (q[n - 1] == ' ' || q[n - 1] == '\t')) n--;
        if (n == 0) continue;                       /* blank line */

        /* The part separator a posting is CUT at, which the alphabet
         * rule below cannot see: the resume line is "---" and every one
         * of those three characters is in the BinHex alphabet, so it
         * reads as two bytes of data and the fork's CRC fails.
         *
         * Source: DeHQX 2.0.1's own documentation, *How It Works*, by
         * Peter N Lewis — who wrote the BinHex 4.0 Definition this file
         * is transcribed from: "If it encounters a line beginning with
         * '--- end of part', it ignores the file until it encounters a
         * line consisting only of '---', at which time it resumes
         * dehqxing." tools/derive_dehqx.py checks that sentence and
         * grades a posting cut this way, which this reader failed until
         * 2026-10-06 and macutils' hexbin reads (by the length rule
         * below, which is still not transcribed).
         *
         * THE RESUME LINE IS A PREFIX, not the whole line, and that is
         * a second implementation's reading rather than the prose's.
         * Source: HQXer 1.1 (John Stiles, 1994), `CODE` 2 +0x1baa — its
         * gap loop reads three characters, compares each with '-', and
         * on three hits discards the REST of the line and resumes with
         * the next character. Taking "consisting only of '---'"
         * literally cost a regression this suite could not see: between
         * 2026-10-06 and 2026-10-07 a posting whose resume line read
         * `--- part 2 ---` or `-----` lost everything after the cut —
         * and the FIRST of those had read correctly before the gap
         * existed at all, because it holds spaces and the garbage rule
         * below skips it, so the gap cost a file it had been given
         * (measured on a build with this test compiled out;
         * DECISIONS.md 2026-10-07; graded by tools/run_multihqx.py's
         * three cuts). HQXer is more permissive
         * still — it scans for three consecutive '-' anywhere, not at a
         * line start — and the line anchor is kept because nothing here
         * needs the rest. */
        if (d->in_gap) {
            if (n >= 3 && q[0] == '-' && q[1] == '-' && q[2] == '-')
                d->in_gap = 0;
            continue;
        }
        if (n >= 15 && q[0] == '-' && q[1] == '-' && q[2] == '-' &&
            q[3] == ' ' && q[4] == 'e' && q[5] == 'n' && q[6] == 'd' &&
            q[7] == ' ' && q[8] == 'o' && q[9] == 'f' && q[10] == ' ' &&
            q[11] == 'p' && q[12] == 'a' && q[13] == 'r' && q[14] == 't') {
            /* Compared byte by byte rather than against a literal: a
             * string constant here would be thirteen bytes of A5 world,
             * which is resident for the life of the application and is
             * at its ceiling (tools/check_app_size.py). */
            d->in_gap = 1;
            continue;
        }

        /* The one pass that judges the line also converts it: what
         * line[] holds from here on is 6-bit values and 0xFE for the
         * ':', not characters, so neither bh_get_bits nor the 4->3
         * group in bh_decode_byte looks a character up again. In the
         * straddling case q IS d->line and the conversion is in place,
         * one element at a time. */
        for (i = 0; i < n; i++) {
            uint8_t v = d->lut[q[i]];
            if (v == 0xFF) { ok = 0; break; }
            d->line[i] = v;
        }
        if (ok) { d->llen = n; return UNC_OK; }
    }
}

/* Next 6-bit group, from a line that belongs to the document; ':' ends
 * the stream. Returns -1 on end/error with d->err set. */
static int bh_get_bits(BhDec *d)
{
    /* Written so the byte-in-hand case is straight-line and costs one
     * compare: this runs four times per three output bytes and callgrind
     * put it at 37 % of a large .hqx, which is 204 of the 929 fixtures. */
    for (;;) {
        uint8_t v;
        if (d->lpos < d->llen) {
            v = d->line[d->lpos++];
            if (v < 0xFE) return v;
            if (v == 0xFE) { d->eof = 1; d->err = UNC_ERR_TRUNCATED; return -1; }
            continue;                               /* 0xFF: cannot happen */
        }
        if (bh_refill_line(d) != UNC_OK) return -1;
    }
}

/* Next byte of the 6-bit layer (pre-RLE).
 *
 * Four characters make three bytes, and when all four are on the line in
 * hand the group is decoded in one go: the caller gets the first byte
 * and the other two are served from d->batch without the line, the
 * bounds test or the LUT being touched again. A BinHex line is 64
 * characters, a multiple of four, so a real file takes this path for
 * every group except at a line break. Everything else — a short line, a
 * group straddling two lines, the terminating ':' — falls through to
 * the one-character-at-a-time path below, which is unchanged. */
static int bh_decode_byte(BhDec *d)
{
    int bits1, bits2;
    uint32_t ph = d->phase;

    if (d->bp != d->bend) return *d->bp++;   /* rest of a decoded group */
    if (ph == 0u && d->llen - d->lpos >= 4) {
        const uint8_t *p = d->line + d->lpos;
        uint32_t a = p[0], b = p[1], c = p[2], e = p[3];
        /* Every value on the line is a 6-bit code or 0xFE (':'); one
         * test on the OR of the four says all of them are codes. */
        if (((a | b | c | e) & 0xC0u) == 0u) {
            d->lpos += 4;
            d->batch[0] = (uint8_t)((b << 4) | (c >> 2));
            d->batch[1] = (uint8_t)((c << 6) | e);
            d->bp = d->batch; d->bend = d->batch + 2;
            return (int)(((a << 2) | (b >> 4)) & 0xFFu);
        }
    }
    d->phase = (ph == 2u) ? 0u : ph + 1u;
    switch (ph) {
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
/* Next fully decoded byte (post-RLE), or -1 with d->err set.
 *
 * The loop is the cheapest of three shapes measured here: straight-line
 * (two inlined unc_rle90_feed bodies) and a fast/slow split both grew
 * this past the point where gcc inlines it into bh_fork, and cost 10 %
 * and 4 % of a .hqx run against this one's 2-3 %. DECISIONS.md
 * 2026-08-27, the fork writer and the filter. */
static int bh_next(BhDec *d)
{
    if (d->err != UNC_OK) return -1;
    for (;;) {
        int b, v = unc_rle90_take(&d->rle);
        if (v >= 0) return v;
        b = bh_decode_byte(d);
        if (b < 0) return -1;                    /* d->err is set */
        v = unc_rle90_feed(&d->rle, b);
        if (v >= 0) return v;
        if (v != UNC_RLE90_MORE) { d->err = UNC_ERR_CORRUPT; return -1; }
    }
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
 *
 * Source: DeHQX 2.0.1's own documentation, *How It Works*, by Peter N
 * Lewis — the author of the BinHex 4.0 Definition above: "When it comes
 * to the end of the HQX source, if [sic] checks for the terminating
 * colon, and then continues scanning the file for the next '(This
 * file...'", and its glossary defines a source file as "a file
 * containing (parts of) one or more HQX sources". macutils' hexbin.c,
 * which decodes a document and then does `again = 1; goto nexttry`,
 * until 2026-10-06 (tools/derive_dehqx.py).
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
 * whitespace. Source: binhex40_lewis.txt, which defines <return> to a
 * DECODER as "any sequence of <cr>, <lf>, <tab>, <spc>" — the tab and
 * the space "because some old programs produced these characters" —
 * and then says to skip <return> characters and check for the colon. */
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
    d->bp = d->bend = d->batch;
    d->prev_bits = 0;
    d->eof = 0;
    d->in_gap = 0;
    unc_rle90_init(&d->rle, 1);
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
    uint32_t iocap = UNC_IOBUF, ocap = UNC_IOBUF;
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

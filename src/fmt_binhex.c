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
 * SPDX-License-Identifier: 0BSD
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
     * bh_refill_line. Once a line is accepted this holds its DECODED
     * bytes, three for every four characters (written over the
     * characters when a line had to be copied here to be read); rp..rend
     * is what is left of them. */
    uint8_t  line[BH_LINE_MAX];
    uint8_t *rp, *rend;
    uint8_t  lut[256];    /* char -> 6-bit value, 0xFF = invalid, 0xFE = ':' */
    uint8_t  phase;       /* characters of the current four-character group
                           * already taken, 0..3: a group can straddle a
                           * line break, so it carries from line to line */
    uint8_t  prev_bits;   /* the last of them, whose low bits are owed */
    uint8_t  colon;       /* the terminating ':' is on the line in hand */
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
    d->prev_bits = 0;
    d->colon = 0;
    d->in_gap = 0;
    unc_rle90_init(&d->rle, 1);
    d->rp = d->rend = d->line;
    d->err = UNC_OK;
}

/* Read the next line and decide whether it belongs to the document.
 *
 * A line that cannot be data is skipped WHOLE, which is what lets this
 * read a file posted in several parts, each part carrying its own mail
 * header. It is why the BinHex alphabet omitting n, o, s, t, u and the
 * space is load-bearing: ordinary prose fails within a few characters.
 *
 * Source: StuffIt's own `HQXEngine`, Aladdin's StuffIt Engine SDK 5.1.2
 * (April 1999), resource `Eng ` 10000 — the decoder behind StuffIt
 * Expander 5.x. Its 6-bit fetcher calls a LINE reader (+0x0d7e), which
 * fills an 80-byte buffer to the first CR or LF (+0x4acc), hands it to a
 * predicate (+0x4b0e), and on a refusal REWINDS THE BUFFER AND READS THE
 * NEXT LINE (+0x4b1c). The predicate (+0x4a30) wants a line of 63 or 64
 * characters, or one ending at the ':', with every character in a
 * 71-value set that holds all 64 of the alphabet and rejects SPACE and
 * TAB. Not published as source: it is four layers inside `sdk512.hqx`,
 * and tools/derive_hqxgarbage.py --engine opens every layer with this
 * project's own CLI and checks 29 witnesses at the offsets they are
 * claimed to sit at.
 *
 * macutils' hexbin states the same rule (hqx.c, "Check line for
 * intermediate garbage") and is where this was first transcribed from.
 * It is no longer cited: thirteen readers were asked for a second
 * statement of it and none gave one, the fourteenth did, and nothing
 * here is hexbin's alone any more (NOTICE; DECISIONS.md 2026-10-07,
 * *the engine four layers down*).
 *
 * THE RULE IS A DEPARTURE FROM THE FORMAT, not an implementation of it,
 * and the Definition says so in as many words: "any character other than
 * those 64 and the <return> characters indicates an error and the user
 * should be notified of such" (binhex40_lewis.txt). deark and DeHQX
 * 2.0.1 — Lewis's own decoder — both do exactly that. Two readers depart
 * for mailed text in the same direction, which is what this rests on.
 *
 * ONE HALF of hexbin's rule is deliberately not transcribed: it also
 * skips any line whose length differs from the first line's, with a
 * look-ahead exception for the last one, and HQXEngine's 63-or-64 is the
 * same test. The Definition refuses it first-party — "When decoding,
 * lines of any length should be accepted" — and the corpus agrees: NO
 * line in any of the 204 `.hqx` fixtures would be skipped by the length
 * half and kept by the alphabet half (measured 2026-10-06,
 * tools/derive_hqxgarbage.py --length, whose scan is shown to fire by
 * injecting one). What the half would have caught — a junk line built
 * only of alphabet characters, a bare rule of hyphens being the
 * realistic shape — is taken as data and caught by BinHex's own per-fork
 * CRC, as a per-entry error rather than as silence. */
static UNC_NOINLINE int bh_refill_line(BhDec *d)
{
    const uint8_t *const lut = d->lut;

    for (;;) {
        const uint8_t *q, *s, *se;
        uint8_t *o = d->line;
        uint32_t avail, ph = d->phase, prev = d->prev_bits;
        int32_t n = 0;
        int keep = 0, colon = 0, found = 0;

        /* The line is normally in the reader's buffer already, all 64
         * characters and the terminator with them, so it is taken in
         * one scan for that terminator rather than one call, one bounds
         * test and one cursor store per character — and that scan is
         * the DECODE, for as long as it lasts (`found` is 0 while it
         * is): four characters at a time through the table, which
         * marks the line break, the ':' and every character outside
         * the alphabet alike, so the group holding the terminator is
         * the one that stops it. A group carried from the line before
         * is finished first, a character at a time, which is every line
         * of a real file: the first holds 63 characters after the ':',
         * so every line break after it falls one character into a
         * group. Not in a gap, whose lines are only scanned. */
        avail = unc_bufin_span(&d->in, &q);
        if (avail > (uint32_t)BH_LINE_MAX) avail = (uint32_t)BH_LINE_MAX;
        s = q;
        se = d->in_gap ? q : q + avail;
        for (;;) {
            uint32_t v;
            /* The bytes are written over the characters when the line
             * is d->line, which is safe: a character yields at most one
             * byte and the first of each group none, so the write never
             * passes the read. A line that is refused leaves line[]
             * spent and the carried group untouched, so it is as if
             * never read. */
            if (ph == 0u) {
                while (se - s >= 4) {
                    uint32_t a = lut[s[0]], b = lut[s[1]];
                    uint32_t c = lut[s[2]], e = lut[s[3]];
                    /* One test on the OR of the four: none is outside
                     * the alphabet (0xFF, the line break included) or
                     * the ':' (0xFE). */
                    if (((a | b | c | e) & 0xC0u) != 0u) break;
                    o[0] = (uint8_t)((a << 2) | (b >> 4));
                    o[1] = (uint8_t)((b << 4) | (c >> 2));
                    o[2] = (uint8_t)((c << 6) | e);
                    o += 3;
                    s += 4;
                }
            }
            if (!found) {
                if (s != se && lut[*s] < 0xFEu) goto one;
                found = 1;
                /* Fewer than four characters taken might be the start
                 * of a part separator, "---" being in the alphabet: the
                 * line is judged from its first character instead. */
                if (s - q < 4) {
                    s = q;
                    o = d->line;
                    ph = d->phase;
                    prev = d->prev_bits;
                }
                n = (int32_t)(s - q);
                while ((uint32_t)n < avail && q[n] != '\n' && q[n] != '\r') n++;
                if ((uint32_t)n < avail) {
                    unc_bufin_drop(&d->in, (uint32_t)n + 1u);   /* and the terminator */
                } else {
                    /* Not in hand: the line straddles a refill, or ends
                     * with the file, or is longer than the buffer. One
                     * character at a time, and a line that overflows is
                     * handed over in pieces — harmless, because every
                     * piece is judged by the same rule and the character
                     * order is unchanged. The test for a full buffer
                     * comes BEFORE the read: after it, the character that
                     * did not fit was read and lost, and a line of 257
                     * characters or more failed its fork's CRC
                     * (DECISIONS.md 2026-11-09, *the character past the
                     * buffer*). */
                    int ch;
                    n = 0;              /* the scan above found nothing */
                    while (n < BH_LINE_MAX) {
                        ch = unc_bufin_next(&d->in);
                        if (ch < 0) {
                            if (n == 0) { d->err = d->in.err; return -1; }
                            break;
                        }
                        if (ch == '\n' || ch == '\r') break;
                        d->line[n++] = (uint8_t)ch;
                    }
                    q = s = d->line;    /* and nothing decoded is kept */
                    o = d->line;
                    ph = d->phase;
                    prev = d->prev_bits;
                }

                /* Mailers put whitespace on the end of a line, so it is
                 * trimmed before the line is judged and a trimmed line is not
                 * "garbage".
                 *
                 * Source: binhex40_lewis.txt — "<return> means to the decoder:
                 * Any sequence of <cr>, <lf>, <tab>, <spc>. (The <tab> and <spc>
                 * are required because some old programs produced these
                 * characters)". Both characters are named by the format's own
                 * Definition, so trailing ones are a line ending and not data.
                 *
                 * THE TAB IS NOT OURS, corrected 2026-10-07: this comment said
                 * it was from 2026-10-06, having looked for it in hexbin (which
                 * tests `line[n - 1] == ' '` and nothing else) rather than in
                 * the document this file is transcribed from. HQXer 1.1 is a
                 * second implementation — its inverse table marks TAB skippable
                 * ANYWHERE in a line, with BS, LF, CR and the space
                 * (tools/derive_hqxgarbage.py --tables).
                 *
                 * The trim is load-bearing, and on a real file:
                 * country-song-generator-101.hqx carries a trailing space on all
                 * 2,600 of its data lines. StuffIt's HQXEngine does not trim, so
                 * every one of those lines is 65 characters long and holds a
                 * SPACE — it fails both halves of that engine's predicate and
                 * the whole file is discarded, line by line. A rule and its
                 * second implementation are not the same reader
                 * (tools/derive_hqxgarbage.py --length). */
                while (n > 0 && (q[n - 1] == ' ' || q[n - 1] == '\t')) n--;
                se = q + n;
                /* Four characters already taken are data: the line is
                 * neither blank nor a part separator. */
                if (s != q) continue;
                if (n == 0) break;                      /* blank line */

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
                 * literally cost a regression this suite could not see, written
                 * and withdrawn the same day, 2026-10-06: a posting whose resume
                 * line read `--- part 2 ---` or `-----` lost everything after
                 * the cut —
                 * and the FIRST of those had read correctly before the gap
                 * existed at all, because it holds spaces and the garbage rule
                 * below skips it, so the gap cost a file it had been given
                 * (measured on a build with this test compiled out;
                 * DECISIONS.md 2026-10-06; graded by tools/run_multihqx.py's
                 * three cuts). HQXer is more permissive
                 * still — it scans for three consecutive '-' anywhere, not at a
                 * line start — and the line anchor is kept because nothing here
                 * needs the rest. */
                if (d->in_gap) {
                    if (n >= 3 && q[0] == '-' && q[1] == '-' && q[2] == '-')
                        d->in_gap = 0;
                    break;
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
                    break;
                }
                continue;
            }

            /* Past the groups: one character at a time, which is a
             * group cut by the line break, a short line and the ':'.
             * Every character is judged, those after the ':' too: a
             * line holding one that is not BinHex is refused whole. */
            if (s == se) { keep = 1; break; }
        one:
            v = lut[*s++];
            if (v == 0xFFu) break;                      /* refused */
            if (v == 0xFEu) {
                colon = keep = 1;
                while (s != se)
                    if (lut[*s++] == 0xFFu) keep = 0;
                break;
            }
            switch (ph) {
            case 0:  ph = 1; break;
            case 1:  *o++ = (uint8_t)((prev << 2) | (v >> 4)); ph = 2; break;
            case 2:  *o++ = (uint8_t)((prev << 4) | (v >> 2)); ph = 3; break;
            default: *o++ = (uint8_t)((prev << 6) | v);        ph = 0; break;
            }
            prev = v;
        }
        if (keep) {
            d->colon = (uint8_t)colon;
            d->phase = (uint8_t)ph;
            d->prev_bits = (uint8_t)prev;
            d->rp = d->line;
            d->rend = o;
            return UNC_OK;
        }
        /* blank, in a gap, a separator, or refused: the next line */
    }
}

/* Up to `n` fully decoded bytes (after RLE90) into `out`; the count is
 * returned, and fewer than `n` means the stream ended or failed, with
 * d->err set as bh_next's caller has always read it: UNC_ERR_TRUNCATED
 * at the ':', the reader's own error at the end of the input, and
 * UNC_ERR_CORRUPT for a run count of one.
 *
 * The whole document goes through here, a fork's bytes a buffer at a
 * time, so the per-byte path is the literal loop in the middle: a byte
 * that is not 0x90 and not owed to an escape is copied and is the new
 * run byte, which is unc_rle90_feed's last branch, and the 0x90 that
 * stops it only marks the escape, which is its first. The count byte
 * goes through unc_rle90_feed itself, so the rules for a count have one
 * statement. A line is read only when one of its bytes is needed, as
 * the byte-at-a-time reader before this did: a document ends with the
 * input where it ended then, and the next banner is searched for from
 * there. */
static uint32_t bh_fill(BhDec *d, uint8_t *out, uint32_t n)
{
    uint8_t *p = out, *const end = out + n;

    if (d->err != UNC_OK) return 0;
    while (p != end) {
        uint8_t *r = d->rp;
        uint32_t k;
        int v;

        if (d->rle.run) {                       /* a run still owed */
            uint8_t last = d->rle.last;
            k = d->rle.run;
            if (k > (uint32_t)(end - p)) k = (uint32_t)(end - p);
            d->rle.run = (uint16_t)(d->rle.run - k);
            do *p++ = last; while (--k);
            continue;
        }
        if (r == d->rend) {
            if (d->colon) { d->err = UNC_ERR_TRUNCATED; break; }
            if (bh_refill_line(d) != UNC_OK) break;     /* d->err set */
            continue;
        }
        if (!d->rle.esc) {
            uint8_t *start = p;
            uint8_t b;
            k = (uint32_t)(d->rend - r);
            if (k > (uint32_t)(end - p)) k = (uint32_t)(end - p);
            do {
                b = *r++;
                if (b == UNC_RLE90_ESC) break;
                *p++ = b;
            } while (--k);
            if (p != start) d->rle.last = p[-1];
            d->rp = r;
            /* An escape outside a run only waits for its count, which
             * is all unc_rle90_feed would do with it. */
            if (b == UNC_RLE90_ESC) d->rle.esc = 1;
            continue;
        }
        d->rp = r + 1;
        v = unc_rle90_feed(&d->rle, *r);
        if (v >= 0) *p++ = (uint8_t)v;
        else if (v != UNC_RLE90_MORE) { d->err = UNC_ERR_CORRUPT; break; }
    }
    return (uint32_t)(p - out);
}

/* Next fully decoded byte, or -1 with d->err set: the header's reader. */
static int bh_next(BhDec *d)
{
    uint8_t b;
    return bh_fill(d, &b, 1) == 1 ? (int)b : -1;
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
 * and then says to skip <return> characters and check for the colon.
 *
 * Lempereur's own BinHex 5.0 is STRICTER than its Definition here: its
 * start scan skips characters below 32 and requires the ':' to be the
 * first one at or above it, so a space or a tab in front of the colon
 * loses the document there and is read here (`CODE` 1 +0x0522,
 * tools/derive_hqxgarbage.py --author). The Definition names both
 * characters, so the Definition is what this follows. */
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
        uint32_t n = left < ocap ? left : ocap;
        if (bh_fill(d, obuf, n) != n)
            return d->err != UNC_OK ? d->err : UNC_ERR_TRUNCATED;
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
    d->rp = d->rend = d->line;
    d->phase = 0;
    d->prev_bits = 0;
    d->colon = 0;
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

    /* BinHex before 4.0, and SUMacC's `.dl` before that, are another
     * decoder in the same overlay; one entry point means one Macintosh
     * shim (src/fmt_hecx.c). */
    if (c->fmt != UNC_FORMAT_BINHEX) return unc_hecx_extract(c);

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

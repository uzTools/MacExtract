/*
 * fmt_uu.c — uuencoded files (.uu), including the UUTool "MU" shape
 * that carries both forks and the Finder info.
 *
 * Sources (transcribed, never guessed):
 *   reference/mpack/uudecode.c          — dispatch, since 2026-09-27
 *       (macutils' hexbin.c until then): any amount of preamble is
 *       skipped looking for a line that begins "begin ", and the
 *       terminator is "end" followed by whitespace. mpack's state
 *       machine spells both out — st_start for the first and st_last
 *       for the second — and mpack is permissive (CMU), where hexbin
 *       is not. What mpack does NOT state is the CR/LF rule, because
 *       it is LF-only throughout (part_gets breaks on '\n' alone) —
 *       and that was taken for "nobody else states it" until
 *       2026-10-05, when deark was asked (below).
 *   reference/deark/src/deark-dbuf.c (MIT) and modules/xfer.c
 *       — the line rule, since 2026-10-05 (macutils' readline.c until
 *       then): dbuf_find_line ends a line at CR, at LF or at CR+LF and
 *       treats a last line with no terminator as a line, and deark's
 *       own uudecode skips the blank line a CRLF leaves behind.
 *   UUTool, by Bernie Wieser (Octavian Micro Development) — the MU
 *       layout and both of its alphabets, since 2026-10-06 (macutils'
 *       hexbin/mu.c until then). The program that WRITES the layout
 *       states it three ways, and tools/derive_mu.py checks all three
 *       against three versions of it: its own manual has the order
 *       ("The data fork of a file is the first part in the encoded
 *       text file, bounded by a 'begin' and 'end' statement.  This is
 *       followed by the resource fork, and finally finder
 *       information"), its DATA 0 holds the section headers it writes
 *       as whole literals — "begin 0700 .rsrc\r", "begin 0700
 *       .finfo\r", "end\r" — and its HEXA 128 "PC" and HEXA 129
 *       "UNIX" resources are the two encode tables. UUParser 1.72, a
 *       different author, carries both tables too.
 *   reference/mpack/uudecode.c, uudecodeline() — the 4-for-3 transform
 *       and the count character that leads each line, which is
 *       DEC(c) = ((c) - ' ') & 077 there and UU_SIXB() here.
 *
 * Two shapes are read:
 *
 *   plain uuencode   begin <mode> <name> / data / end
 *                    One data fork, no Mac metadata. The name is the
 *                    rest of the begin line.
 *
 *   UUTool ("MU")    begin <mode> "<mac name>" / data / end
 *                    begin <mode>  .rsrc      / data / end   (optional)
 *                    begin <mode>  .finfo     / 16 bytes / end
 *                    Both forks and type/creator/Finder flags.
 *
 * Several documents in one file are extracted, not just the first —
 * the same shape BinHex has in a newsgroup posting, and for the same
 * reason (DECISIONS.md 2026-08-15).
 *
 * Each document is read TWICE: once to measure the forks and pick up
 * the Finder info, which lives at the END of the document, and once to
 * decode. The sink is told an entry's type and creator before any of
 * its bytes, so the alternative would be emitting Mac files with no
 * type — an extracted application that does not launch.
 *
 * Harness: tests/harness/run_uu.py
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "unc_internal.h"
#include "fmt_uu_priv.h"

/* A uu line holds at most 45 payload bytes = 60 encoded characters,
 * plus the length character. Mailers wrap nothing shorter, but a line
 * longer than this is not a uu line at all. */
/* Both are unc_internal.h's, because fmt_mime.c decodes uu lines too. */

/* How far into a file the "begin " line may sit. hexbin skips lines
 * until it finds one; the probe needs a bound, and BinHex's own banner
 * scan uses the same 512-byte sniff window. */

typedef struct UuLine {
    uint8_t  buf[UU_LINE_MAX + 1];
    /* The line: `buf`, or where it already lies whole in the input
     * buffer, valid until the next uu_readline. A line padded to its
     * count is never one in the input buffer (uu_readline). */
    uint8_t *p;
    uint8_t  lo, hi;   /* the line's lowest and highest byte (uu_mask) */
    uint8_t  cut;            /* the line was longer than the buffer */
    uint32_t dropped;        /* by this many bytes, all off the end */
    /* Where a line too long for `buf` is kept whole: the host's
     * UncOptions.long_name, or NULL. Only the "begin" line is ever
     * worth keeping, so once its name has been lifted out `locked`
     * stops a later line from writing over it. */
    uint8_t *over;
    uint32_t over_cap;
    uint32_t over_len;
    uint8_t  locked;
    int32_t  len;
    int      eof;      /* set once the stream ended */
    uint32_t start;    /* absolute offset the line began at */
} UuLine;

/* unc_bufin_tell() counts from wherever the buffer was initialised, so
 * every offset here is taken through this: a document after the first
 * is read from a buffer that started part-way into the file, and a
 * relative offset seeks to the wrong place (measured — the second
 * document of a multi-document file decoded as corrupt). */
static uint32_t uu_abs(uint32_t base, const UncBufIn *in)
{
    return base + unc_bufin_tell(in);
}

/* ------------------------------------------------------------------ */
/* Line reader                                                        */
/* Source: reference/deark/src/deark-dbuf.c (MIT), dbuf_find_line —    */
/* CR, LF or CRLF, and a final line without a terminator is still a    */
/* line; and reference/deark/modules/xfer.c's own uudecode, which      */
/* takes CR or LF as the end of a line and skips the blank line a CRLF */
/* leaves behind, which is the choice made below. macutils' readline.c */
/* until 2026-10-05. A line longer than the buffer is truncated at the */
/* buffer and the rest skipped, which cannot lose a uu line (they are  */
/* 61 characters).                                                     */
/* ------------------------------------------------------------------ */
static int uu_readline(UncBufIn *in, uint32_t base, UuLine *l)
{
    int c;

    l->len = 0;
    l->cut = 0;
    l->dropped = 0;
    if (!l->locked) l->over_len = 0;
    l->start = uu_abs(base, in);
    l->p = l->buf;
    /* Where it lies whole in the input buffer, it is read there: no copy
     * (tools/m68kprof.py, 2026-11-20). */
    {
        const uint8_t *q;
        uint32_t n = unc_bufin_span(in, &q), k;
        uint8_t lo = 0xFF, hi = 0;
        if (n > UU_LINE_MAX) n = UU_LINE_MAX;
        /* Where the count says the line ends, first: a full line is
         * ((count + 2) / 3) * 4 + 1 characters, and if the byte there
         * ends a line the scan needs no test for the end, only the
         * lowest and highest byte. A CR or LF inside would be the
         * lowest, below UU_CH_MIN, and goes to the scan below, which
         * finds where the line really ends; so does any line whose end
         * is not where its count puts it. Two compares a character were
         * a third of a uuencoded file's instructions (tools/m68kprof.py,
         * 2026-11-22). */
        if (n > 0) {
            uint32_t want = (uint32_t)UU_DIV3(UU_SIXB(q[0]) + 2) * 4u + 1u;
            if (want < n && (q[want] == '\n' || q[want] == '\r')) {
                const uint8_t *r = q, *re = q + want;
                do {
                    uint8_t ch = *r++;
                    if (ch < lo) lo = ch;
                    if (ch > hi) hi = ch;
                } while (r != re);
                if (lo >= UU_CH_MIN) {
                    l->p = (uint8_t *)q;
                    l->len = (int32_t)want;
                    l->lo = lo;
                    l->hi = hi;
                    unc_bufin_drop(in, want + 1);
                    return UNC_OK;
                }
                lo = 0xFF;
                hi = 0;
            }
        }
        for (k = 0; k < n; k++) {
            uint8_t ch = q[k];
            if (ch == '\n' || ch == '\r') {
                /* A line shorter than its count says is padded where it
                 * lies (uu_decode), which in the input buffer would be
                 * over the next line: such a line is copied, below. */
                int32_t oc = UU_SIXB(q[0]);
                if (k < (uint32_t)UU_DIV3(oc + 2) * 4 + 1) break;
                l->p = (uint8_t *)q;
                l->len = (int32_t)k;
                l->lo = lo;
                l->hi = hi;
                unc_bufin_drop(in, k + 1);
                return UNC_OK;
            }
            if (ch < lo) lo = ch;
            if (ch > hi) hi = ch;
        }
    }
    for (;;) {
        c = unc_bufin_next(in);
        if (c < 0) {
            if (in->err != UNC_ERR_TRUNCATED) return in->err;
            l->eof = 1;
            break;
        }
        /* CR, LF, or both. A CRLF pair leaves an empty line behind,
         * which every loop here skips — which is what deark's own
         * uudecode does with it (xfer.c, do_uudecode_internal: a CR or
         * LF at the start of a line is "a multi-byte EOL sequence, or
         * blank line" and is skipped). Peeking instead would need a
         * byte of push-back, and UncBufIn only seeks forward. */
        if (c == '\n' || c == '\r') break;
        if (l->len < UU_LINE_MAX) l->buf[l->len++] = (uint8_t)c;
        else {
            /* Past the line buffer. The bytes are only lost if nobody
             * asked for them: with a host buffer the whole line is kept
             * there, starting with the part already in `buf`. */
            l->cut = 1;
            l->dropped++;
            if (l->over && !l->locked && l->over_cap > 1) {
                if (l->over_len == 0) {
                    int32_t k;
                    for (k = 0; k < l->len; k++) l->over[k] = l->buf[k];
                    l->over_len = (uint32_t)l->len;
                }
                if (l->over_len < l->over_cap - 1u)
                    l->over[l->over_len++] = (uint8_t)c;
            }
        }
    }

    l->buf[l->len] = 0;
    {
        int32_t k;
        l->lo = 0xFF;
        l->hi = 0;
        for (k = 0; k < l->len; k++) {
            if (l->buf[k] < l->lo) l->lo = l->buf[k];
            if (l->buf[k] > l->hi) l->hi = l->buf[k];
        }
    }
    if (l->eof && l->len == 0) return UNC_ERR_TRUNCATED;   /* nothing left */
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Line decoding                                                      */
/* Source: uudecodeline() in reference/mpack/uudecode.c (CMU,         */
/* permissive) for the transform, and UUTool's own HEXA 128 "PC"      */
/* table for the padding below (tools/derive_mu.py --tables).         */
/* ------------------------------------------------------------------ */


/* The `outcount` bytes a line declares, into `out`: the groups that hold
 * them, ceil(outcount / 3), and no more — reading the one after them made
 * every full line "short", so padded, so copied (2026-11-20).
 * Mailers strip trailing whitespace, so a short line is padded
 * back out to the length its count implies. A space is what the
 * padding has to be because the "PC" table spells the value ZERO
 * as one, which is also why UUTool's other table exists at all:
 * "I suggest not using original coding when using UNIX machines,
 * since some electronic mailors reformat white space" (its manual,
 * *UUcode preferences*). Under either of the UNIX tables the value
 * zero is 0x60 instead, and UU_SIXB reads a space as zero there
 * too, so one pad character serves all three. */
static void uu_decode(uint8_t *buf, int32_t len, uint8_t *out, int32_t outcount)
{
    int32_t i, n, last = UU_DIV3(outcount + 2) * 4;   /* the last char read */

    for (i = len; i <= last; i++) buf[i] = ' ';
    for (n = 0, i = 1; n < outcount; n += 3, i += 4) {
        uint8_t a = (uint8_t)UU_SIXB(buf[i]),     b = (uint8_t)UU_SIXB(buf[i + 1]);
        uint8_t c = (uint8_t)UU_SIXB(buf[i + 2]), d = (uint8_t)UU_SIXB(buf[i + 3]);
        out[n]     = (uint8_t)(a << 2 | b >> 4);
        out[n + 1] = (uint8_t)(b << 4 | c >> 2);
        out[n + 2] = (uint8_t)(c << 6 | d);
    }
}

/* What unc_uu_line_is_data says of a line, from the lowest and highest
 * byte uu_readline kept while it looked for the line's end: one loop
 * over the characters instead of two. Same answer, every case. */
static int uu_mask(const UuLine *l, int32_t outcount)
{
    int mask = UU_TBL_ANY;
    if (outcount == 0 || outcount > 45) return 0;
    if (l->len > (UU_DIV3(outcount) + 1) * 4 + 1) return 0;
    if (l->lo < UU_CH_MIN || l->hi > UU_CH_MAX) return 0;
    if (l->hi > UU_PC_MAX) mask &= ~UU_TBL_PC;
    if (l->lo < UU_UNIX_MIN) mask &= ~UU_TBL_UNIX;
    return mask;
}

/* One line: its payload into `out` (>= UU_DEC_MAX bytes) and, in `*mask`,
 * what unc_uu_line_is_data says of it — which alphabets it could be from,
 * 0 if it cannot be a data line. Returns the count (0..45), 0 for the
 * terminator, -1 for a line whose count cannot be one. With `out` NULL
 * only the count and the mask: uuencode's measuring pass. The line is
 * decoded whatever the mask (the .finfo section reads it so); it is
 * padded in place, in `buf` itself, which must hold UU_LINE_MAX + 1.
 * One pass where a copy into a padded buffer, a decode and a separate
 * check were 58 % of a 200 KB file's instructions (tools/m68kprof.py,
 * 2026-11-20). */
int32_t unc_uu_data_line(uint8_t *buf, int32_t len, uint8_t *out, int *mask)
{
    int32_t outcount;

    *mask = 0;
    if (len < 1) return -1;
    outcount = UU_SIXB(buf[0]);
    if (outcount > 45) return -1;
    if (outcount == 0) return 0;
    *mask = unc_uu_line_is_data(buf, len);
    if (out != NULL) uu_decode(buf, len, out, outcount);
    return outcount;
}


static int uu_is_begin(const UuLine *l)
{
    return l->len >= 6 && l->p[0] == 'b' && l->p[1] == 'e' &&
           l->p[2] == 'g' && l->p[3] == 'i' && l->p[4] == 'n' &&
           l->p[5] == ' ';
}

static int uu_is_end(const UuLine *l)
{
    return l->len >= 3 && l->p[0] == 'e' && l->p[1] == 'n' &&
           l->p[2] == 'd';
}

/* The section tag of a UUTool continuation line, at the offset the
 * literal puts it: UUTool's DATA 0 holds "begin 0700 .rsrc\r" and
 * "begin 0700 .finfo\r" whole, so the tag starts at 10 and begins
 * with a space. The mode in a continuation line is that literal's and
 * not the preference's — `uu-wild-dictcol.uu` says 0755 in its first
 * line and 0700 in both sections — and a Macintosh ignores it either
 * way ("This is ignored on the Mac side", the manual's *UNIX
 * Preferences*). */
static int uu_tag_is(const UuLine *l, const char *tag)
{
    int32_t i;
    if (l->len < 10) return 0;
    for (i = 0; tag[i]; i++)
        if (10 + i >= l->len || l->p[10 + i] != (uint8_t)tag[i]) return 0;
    return 1;
}

/* Name out of a begin line. UUTool quotes a Mac name when its naming
 * preference is "Macintosh", where "anything goes" and a space in a
 * name would otherwise end it; with the PC or UNIX preference it
 * writes a bare name with the characters it calls dangerous replaced
 * (its manual, *UUcode preferences*), and so does plain uuencode. Both
 * wild specimens are here: one of each. So the name is what follows
 * the first '"' with the closing one dropped, or the rest of the line
 * past the mode. */
/* Where the name sits inside a "begin" line. Takes the bytes rather
 * than the UuLine, so it can run over the whole line kept in the host's
 * buffer as well as over the first UU_LINE_MAX of it. */
void unc_uu_name_span(const uint8_t *buf, int32_t len, int32_t *soff,
                      int32_t *eoff)
{
    int32_t i, s, e;

    for (i = 6; i < len; i++) if (buf[i] == '"') break;
    if (i < len) {                        /* quoted: UUTool */
        s = i + 1;
        e = len;
        if (e > s && buf[e - 1] == '"') e--;
    } else {                              /* bare: skip "begin <mode> " */
        s = 6;
        while (s < len && buf[s] != ' ') s++;   /* the mode */
        while (s < len && buf[s] == ' ') s++;
        e = len;
        while (e > s && (buf[e - 1] == ' ' || buf[e - 1] == '\t')) e--;
    }
    if (e < s) e = s;
    *soff = s;
    *eoff = e;
}

/* The lock a "begin <mode> <name>" line states, from its octal mode:
 * locked where the mode has no owner write, 0200. `at` is where the mode
 * may start, after "begin " or "begin-base64 ", so that base64 and MIME
 * read it the same way.
 *
 * Source: reference/deark/modules/xfer.c, parse_begin_line() — the field
 * after "begin" (or "begin-base64") and one space is an octal number,
 * de_strtoll(..., 8), which deark reads as a POSIX mode (it tests 0111 for
 * execute); reference/notes/posix_ustar.txt, the mode table — 00200 is
 * S_IWUSR, write permission for the file owner. A file its owner could
 * not write is the one HFS calls locked (DECISIONS.md 2026-10-17, the
 * maintainer's brief). A mode that is not all octal digits, or has none,
 * states nothing. */
int unc_uu_mode_lock(const uint8_t *buf, int32_t len, int32_t at)
{
    uint32_t mode = 0;
    int32_t i;
    while (at < len && buf[at] == ' ') at++;
    /* Only the last three digits reach 0200, so a long mode cannot wrap
     * into a wrong answer and needs no cap. */
    for (i = at; i < len && buf[i] != ' '; i++) {
        if (buf[i] < '0' || buf[i] > '7') return UNC_LOCK_UNKNOWN;
        mode = mode * 8u + (uint32_t)(buf[i] - '0');
    }
    if (i == at) return UNC_LOCK_UNKNOWN;
    return (mode & 0200u) ? UNC_LOCK_NO : UNC_LOCK_YES;
}

static void uu_name_from_begin(const UuLine *l, const uint8_t **name,
                               uint32_t *len)
{
    int32_t s, e;
    unc_uu_name_span(l->p, l->len, &s, &e);
    *name = l->p + s;
    *len  = (uint32_t)(e - s);
}

/* ------------------------------------------------------------------ */
/* Probe                                                              */
/* ------------------------------------------------------------------ */

/* A "begin " line alone is far too weak — it occurs in English prose
 * and in shell scripts. What makes it a uu file is the line AFTER it:
 * a length character that agrees with the encoded length. */

/* Shared with uu_section: a line belongs to the stream only if it can
 * be one. See the comment there for what that buys and what it costs. */

/* ------------------------------------------------------------------ */
/* Section walk                                                       */
/* ------------------------------------------------------------------ */

typedef struct UuSection {
    uint32_t bytes;      /* payload length */
    int      present;
} UuSection;

typedef struct UuDoc {
    uint32_t  start;                 /* offset of the begin line       */
    uint32_t  end;                   /* offset just past the document  */
    UuSection data, rsrc, finfo;
    uint8_t   name[UNC_NAME_MAX + 1];
    uint32_t  name_len;
    uint8_t   name_trunc;   /* the "begin" line named more than fits */
    uint32_t  name_full;    /* what the name's length was, 0 if unknown */
    uint8_t   name_have_full; /* and the whole of it is in the host's
                               * buffer (UncOptions.long_name) */
    uint8_t   info[16];              /* type, creator, flags, ...      */
    uint8_t   lock;     /* what the first begin line's mode says */
} UuDoc;

/* Read one section's lines. If sink is non-NULL the payload is written
 * to it as `fork`; otherwise only its length is measured. Stops after
 * the zero-length line and the "end" that follows it — or after a bare
 * "end", which is what encoders other than UUTool write.
 *
 * `*table` is the DOCUMENT's alphabet, narrowed as its lines are read
 * and carried from one section to the next because UUTool writes every
 * section of a document with one table (fmt_uu_priv.h). */
/* Written through UncForkOut's `obuf` (UNC_IOBUF bytes), not a line at a
 * time: a sink write per 45-byte line was 4,400 FSWrites for a 200 KB
 * file, and on a Mac Plus 66 s against UUTool's 9 (FORMATS.md, *Each
 * format's own program*). `obuf` may be NULL when `write` is 0. */
static int uu_section(UncCtx *c, UncBufIn *in, uint32_t base, UuLine *l,
                      UncFork fork, int write, uint32_t *bytes, int *table,
                      uint8_t *obuf)
{
    UncForkOut o;
    int err;

    if (write) unc_fork_out(&o, c, fork, 1, UNC_CK_NONE, obuf, UNC_IOBUF);
    *bytes = 0;
    for (;;) {
        err = uu_readline(in, base, l);
        if (err != UNC_OK) return err;
        if (l->len == 0) {
            if (l->eof) return UNC_ERR_TRUNCATED;
            continue;                     /* mailers leave blank lines */
        }
        if (uu_is_end(l)) return write ? unc_fork_flush(&o) : UNC_OK;
        {
            int m;
            int32_t n;
            uint8_t *dst = NULL;           /* measuring: the count is enough */
            /* Straight into the fork's buffer when writing: a copy a byte
             * at a time through unc_fork_write was 13 % of the decode. */
            if (write) {
                if (o.cap - o.len < UU_DEC_MAX &&
                    (err = unc_fork_flush(&o)) != UNC_OK)
                    return err;
                dst = o.buf + o.len;
            }
            n = l->len < 1 ? -1 : UU_SIXB(l->p[0]);
            if (n > 45) n = -1;
            m = n > 0 ? uu_mask(l, n) : 0;
            if (n > 0 && dst != NULL && (m & *table))
                uu_decode(l->p, l->len, dst, n);
            if (n == 0) {
                /* Terminator; the "end" line follows it. */
                err = uu_readline(in, base, l);
                if (err != UNC_OK) return err;
                while (l->len == 0 && !l->eof) {
                    err = uu_readline(in, base, l);
                    if (err != UNC_OK) return err;
                }
                if (!uu_is_end(l)) return UNC_ERR_CORRUPT;
                return write ? unc_fork_flush(&o) : UNC_OK;
            }
            /* A line that cannot be a data line is MAIL, not data: a
             * file posted in several parts arrives as several messages,
             * each with its own header, and joining them puts that
             * header in the middle of the stream. The same thing
             * macutils' hexbin does for BinHex (hqx.c, "check line for
             * intermediate garbage") and StuffIt's own HQXEngine after
             * it, which is what fmt_binhex.c cites since 2026-10-07;
             * here the test is stronger, because a uu line's first
             * character DECLARES how many bytes it encodes, so the
             * length has to agree AND the characters have to be in the
             * alphabet this document has used so far. Both halves are
             * load-bearing: with the character test widened to the
             * union of UUTool's two alphabets and no per-document
             * narrowing, three cases of mail in mid-stream were read as
             * data (tests/harness/run_uu.py, the intruder pair).
             *
             * What this cannot do is notice a part that never arrived.
             * uuencode carries no length and no checksum anywhere, so a
             * set missing its MIDDLE part decodes to a short file with
             * nothing to object to. A missing LAST part is still caught:
             * the terminator and "end" live there. OPEN_ITEMS.md. */
            if (n < 0 || !(m & *table)) continue;
            *table &= m;
            *bytes += (uint32_t)n;
            if (write) o.len += (uint32_t)n;
        }
        if (l->eof) return UNC_ERR_TRUNCATED;
    }
}

/* Measure one document: sizes, name and Finder info. `in` must be
 * positioned at its begin line. */
/* A document's begin line: its name, and the mode's lock. */
static void uu_doc_head(UuLine *l, UuDoc *d)
{
    const uint8_t *nm;
    uint32_t nlen;

    d->data.present = d->rsrc.present = d->finfo.present = 0;
    d->data.bytes = d->rsrc.bytes = d->finfo.bytes = 0;
    d->name_len = 0;
    d->name_trunc = 0;
    d->name_full = 0;
    d->name_have_full = 0;
    l->locked = 0;          /* this document may keep its own name */
    {
        int i;
        for (i = 0; i < 16; i++) d->info[i] = 0;
    }

    d->start = l->start;
    d->lock = (uint8_t)unc_uu_mode_lock(l->p, l->len, 6);
    uu_name_from_begin(l, &nm, &nlen);
    if (nlen > UNC_NAME_MAX) {
        nlen = UNC_NAME_MAX;
        d->name_trunc = 1;
    }
    if (l->cut) {
        /* The name is the last thing on a "begin" line, so the bytes
         * the buffer dropped are exactly the ones missing from it. */
        d->name_trunc = 1;
        d->name_full = nlen + l->dropped;
        if (l->over && l->over_len > 6) {
            /* The whole line was kept: move the name to the front of
             * the host's buffer and hold it there, so the data lines
             * behind it do not write over it. */
            int32_t s2, e2;
            unc_uu_name_span(l->over, (int32_t)l->over_len, &s2, &e2);
            if (e2 > s2) {
                uint32_t k, n2 = (uint32_t)(e2 - s2);
                for (k = 0; k < n2; k++) l->over[k] = l->over[(uint32_t)s2 + k];
                l->over[n2] = 0;
                l->over_len = n2;
                l->locked = 1;
                d->name_have_full = 1;
            }
        }
    }
    {
        uint32_t i;
        for (i = 0; i < nlen; i++) d->name[i] = nm[i];
        d->name[nlen] = 0;
        d->name_len = nlen;
    }
}

static int uu_finfo(UncBufIn *in, uint32_t base, UuLine *l, UuDoc *d);

/* One document's sections, from its begin line (in `l`, its head already
 * read) to the line after its last: each fork counted, and written when
 * `write` is set, and the .finfo section read. Every pass over a document
 * is this walk: the measuring one before begin_entry, the writing one
 * after, or — for a host that takes the Finder info late — the only one
 * (UncSink.set_info). */
static int uu_walk(UncCtx *c, UncBufIn *in, uint32_t base, UuLine *l,
                   UuDoc *d, int write, uint8_t *obuf)
{
    int err;
    int table = UU_TBL_ANY;      /* which alphabet this document uses */

    err = uu_section(c, in, base, l, UNC_FORK_DATA, write, &d->data.bytes,
                     &table, obuf);
    if (err != UNC_OK) return err;
    d->data.present = 1;
    d->end = uu_abs(base, in);

    /* Optional continuation sections. Anything else — EOF, or a begin
     * line that names neither — ends the document. */
    for (;;) {
        uint32_t mark = uu_abs(base, in);
        err = uu_readline(in, base, l);
        if (err != UNC_OK) { d->end = mark; return UNC_OK; }
        if (l->len == 0) { if (l->eof) { d->end = mark; return UNC_OK; } continue; }
        if (!uu_is_begin(l)) { d->end = mark; return UNC_OK; }

        if (uu_tag_is(l, " .rsrc")) {
            err = uu_section(c, in, base, l, UNC_FORK_RSRC, write,
                             &d->rsrc.bytes, &table, obuf);
            if (err != UNC_OK) return err;
            d->rsrc.present = 1;
            d->end = uu_abs(base, in);
        } else if (uu_tag_is(l, " .finfo")) {
            err = uu_finfo(in, base, l, d);
            if (err != UNC_OK) return err;
        } else {
            d->end = mark;      /* the next document's begin line */
            return UNC_OK;
        }
    }
}

/* A .finfo section, its begin line read: 16 bytes, type(4), creator(4),
 * flags(2), then the position and folder the Finder remembered. */
static int uu_finfo(UncBufIn *in, uint32_t base, UuLine *l, UuDoc *d)
{
    uint8_t dec[UU_DEC_MAX];
    uint32_t got = 0;
    int err;

    for (;;) {
        err = uu_readline(in, base, l);
        if (err != UNC_OK) return err;
        if (l->len == 0) { if (l->eof) return UNC_ERR_TRUNCATED; continue; }
        if (uu_is_end(l)) break;
        {
            int m;
            int32_t n = unc_uu_data_line(l->p, l->len, dec, &m);
            int32_t k;
            if (n < 0) return UNC_ERR_CORRUPT;
            if (n == 0) continue;
            for (k = 0; k < n && got < 16; k++) d->info[got++] = dec[k];
        }
    }
    d->finfo.present = 1;
    d->finfo.bytes = got;
    d->end = uu_abs(base, in);
    return UNC_OK;
}

/* A document's entry, from what is known of it: the name always, and
 * the Finder info once its .finfo section has been read. */
static void uu_doc_entry(UncCtx *c, const UuDoc *d, UncEntryInfo *e)
{
    unc_entry_clear(e);
    if (d->name_len == 0) {
        if (c->opt.name_hint && c->opt.name_hint_len)
            unc_entry_set_name(e, c->opt.name_hint, c->opt.name_hint_len);
    } else {
        unc_entry_set_name(e, d->name, d->name_len);
        if (d->name_trunc) {
            e->name_truncated = d->name_have_full ? 2 : 1;
            e->name_full_len = (uint16_t)(d->name_full > 65535u ? 65535u
                                                                : d->name_full);
        }
    }
    /* Measured only for a listing: an extraction writes as it reads. */
    e->data_size = e->rsrc_size = UNC_SIZE_UNKNOWN;
    if (c->opt.list_only) {
        e->data_size = d->data.bytes;
        e->rsrc_size = d->rsrc.bytes;
    }
    if (d->finfo.present && d->finfo.bytes >= 8) {
        e->type    = unc_get_u32be(d->info);
        e->creator = unc_get_u32be(d->info + 4);
        if (d->finfo.bytes >= 10) e->finder_flags = unc_get_u16be(d->info + 8);
        /* All of it: UUTool's .finfo is the FInfo record whole —
         * type, creator, flags, then fdLocation and fdFldr (the
         * layout tools/derive_mu.py reads out of UUTool itself). */
        if (d->finfo.bytes >= 16) {
            uint32_t k;
            for (k = 0; k < 16; k++) e->finder_info[k] = d->info[k];
            e->meta |= UNC_META_FINFO;
        }
    } else if (!d->finfo.present) {
        /* A plain uuencode's mode is the file's own permission. Not
         * a UUTool document's: there it is UUTool's preference, the
         * same 0700 in every section, and "ignored on the Mac side"
         * (its manual, *UNIX Preferences*; see uu_tag_is). */
        e->locked = d->lock;
    }
}

/* ------------------------------------------------------------------ */
/* Extract                                                            */
/* ------------------------------------------------------------------ */

int unc_uu_extract(UncCtx *c)
{
    uint8_t *iobuf;
    uint32_t iocap = UNC_IOBUF;
    UncBufIn in;
    UuLine l;
    UuDoc d;
    int err = UNC_OK, any = 0;
    uint32_t pos = 0;
    uint32_t base = c->ps.done;

    l.over = c->opt.long_name;
    l.over_cap = c->opt.long_name_cap;
    l.over_len = 0;
    l.locked = 0;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + UNC_IOBUF);  /* + output */
    if (!iobuf) return UNC_ERR_MEM;

    for (;;) {
        UncEntryInfo e;
        int sret, est = UNC_OK;
        int found = 0;

        /* Find the next begin line. Every pass here re-reads input an
         * earlier one buffered, so progress is pinned to the position
         * each starts from: the scan below ticks, so Cancel answers,
         * and only the writing pass counts. */
        c->ps.done = base + pos;
        if (c->io->seek(c->io->ctx, pos) < 0) { err = UNC_ERR_IO; break; }
        unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
        l.eof = 0;
        for (;;) {
            uint32_t before = unc_bufin_tell(&in);
            int rerr = uu_readline(&in, pos, &l);
            if (rerr != UNC_OK) break;
            if (uu_is_begin(&l)) { found = 1; break; }
            if (l.eof) break;
            if (before > UU_SCAN_MAX && !any) break;   /* not a uu file */
        }
        if (!found) break;

        /* One pass: the entry begins at the begin line with its sizes
         * unknown, the forks are written as their sections come, and the
         * .finfo section, which UUTool writes last, goes to the host
         * through set_info (DECISIONS.md 2026-11-20, *the character
         * uuencode touched five times*). A listing has nothing to fix up
         * afterwards, so it measures the document first. */
        uu_doc_head(&l, &d);
        if (c->opt.list_only) {
            err = uu_walk(c, &in, pos, &l, &d, 0, NULL);
            if (err != UNC_OK) {
                if (any) err = UNC_OK;  /* trailing junk after a good doc */
                break;
            }
        }
        uu_doc_entry(c, &d, &e);

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; break; }
        if (!c->opt.list_only)
            est = uu_walk(c, &in, pos, &l, &d,
                          sret == 0 && !c->opt.test_only, iobuf + iocap);
        if (sret == 0) {
            if (est == UNC_OK && d.finfo.present && c->sink->set_info) {
                uu_doc_entry(c, &d, &e);
                if (c->sink->set_info(c->sink->ctx, &e) < 0) {
                    err = UNC_ERR_SINK;
                    break;
                }
            }
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
        }
        if (est != UNC_OK) { any = 1; break; }  /* a damaged document ends it */
        any = 1;
        pos = d.end;
        if (d.end <= d.start) break;      /* no forward progress */
    }

    unc_free(c->al, iobuf);
    if (!any && err == UNC_OK) return UNC_ERR_FORMAT;
    return err;
}

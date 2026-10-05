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
 *   reference/macutils/hexbin/mu.c      — the UUTool layout: the data
 *       fork's section, then an OPTIONAL " .rsrc" section, then a
 *       " .finfo" section holding the Finder info, each terminated by
 *       a zero-length line and the word "end". SIXB()/mu_convert(),
 *       including the restoration of trailing spaces that mailers eat.
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
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
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
    if (l->eof && l->len == 0) return UNC_ERR_TRUNCATED;   /* nothing left */
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Line decoding                                                      */
/* Source: mu_convert() in reference/macutils/hexbin/mu.c.            */
/* ------------------------------------------------------------------ */


/* Decode one data line into out (>= UU_DEC_MAX bytes). Returns the
 * payload length (0..45), or -1 if the line cannot be one. */
int32_t unc_uu_decode_line(const uint8_t *buf, int32_t len, uint8_t *out)
{
    uint8_t ib[UU_LINE_MAX + 4];
    int32_t outcount, incount, n, i;

    if (len < 1) return -1;
    outcount = UU_SIXB(buf[0]);
    if (outcount > 45) return -1;
    incount = ((outcount / 3) + 1) * 4;
    if (incount > UU_LINE_MAX) return -1;

    /* "restore lost spaces" — mailers strip trailing whitespace, so a
     * short line is padded back out to the length its count implies. */
    for (i = 0; i < len && i <= incount; i++) ib[i] = buf[i];
    for (; i <= incount; i++) ib[i] = ' ';

    n = 0;
    i = 1;
    while (n <= outcount) {
        out[n]     = (uint8_t)(UU_SIXB(ib[i])     << 2 | UU_SIXB(ib[i + 1]) >> 4);
        out[n + 1] = (uint8_t)(UU_SIXB(ib[i + 1]) << 4 | UU_SIXB(ib[i + 2]) >> 2);
        out[n + 2] = (uint8_t)(UU_SIXB(ib[i + 2]) << 6 | UU_SIXB(ib[i + 3]));
        i += 4;
        n += 3;
    }
    return outcount;
}

static int32_t uu_decode_line(const UuLine *l, uint8_t *out)
{
    return unc_uu_decode_line(l->buf, l->len, out);
}

/* Does this line open a section? */
static int uu_is_begin(const UuLine *l)
{
    return l->len >= 6 && l->buf[0] == 'b' && l->buf[1] == 'e' &&
           l->buf[2] == 'g' && l->buf[3] == 'i' && l->buf[4] == 'n' &&
           l->buf[5] == ' ';
}

static int uu_is_end(const UuLine *l)
{
    return l->len >= 3 && l->buf[0] == 'e' && l->buf[1] == 'n' &&
           l->buf[2] == 'd';
}

/* The section tag of a UUTool continuation line, compared where the
 * reference compares it: mu.c tests line+10 against " .rsrc" and
 * " .finfo" — a fixed offset, because UUTool writes a fixed
 * "begin ### " prefix. */
static int uu_tag_is(const UuLine *l, const char *tag)
{
    int32_t i;
    if (l->len < 10) return 0;
    for (i = 0; tag[i]; i++)
        if (l->buf[10 + i] != (uint8_t)tag[i] || 10 + i >= l->len) return 0;
    return 1;
}

/* Name out of a begin line. UUTool quotes a Mac name; plain uuencode
 * writes a bare filename. mu.c takes everything after the first '"'
 * and drops the last character. */
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

static void uu_name_from_begin(const UuLine *l, const uint8_t **name,
                               uint32_t *len)
{
    int32_t s, e;
    unc_uu_name_span(l->buf, l->len, &s, &e);
    *name = l->buf + s;
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
} UuDoc;

/* Read one section's lines. If sink is non-NULL the payload is written
 * to it as `fork`; otherwise only its length is measured. Stops after
 * the zero-length line and the "end" that follows it — or after a bare
 * "end", which is what encoders other than UUTool write. */
static int uu_section(UncCtx *c, UncBufIn *in, uint32_t base, UuLine *l,
                      UncFork fork, int write, uint32_t *bytes)
{
    uint8_t dec[UU_DEC_MAX];
    int err;

    *bytes = 0;
    for (;;) {
        err = uu_readline(in, base, l);
        if (err != UNC_OK) return err;
        if (l->len == 0) {
            if (l->eof) return UNC_ERR_TRUNCATED;
            continue;                     /* mailers leave blank lines */
        }
        if (uu_is_end(l)) return UNC_OK;
        {
            int32_t n = uu_decode_line(l, dec);
            if (n == 0) {
                /* Terminator; the "end" line follows it. */
                err = uu_readline(in, base, l);
                if (err != UNC_OK) return err;
                while (l->len == 0 && !l->eof) {
                    err = uu_readline(in, base, l);
                    if (err != UNC_OK) return err;
                }
                if (!uu_is_end(l)) return UNC_ERR_CORRUPT;
                return UNC_OK;
            }
            /* A line that cannot be a data line is MAIL, not data: a
             * file posted in several parts arrives as several messages,
             * each with its own header, and joining them puts that
             * header in the middle of the stream. Skipping it is what
             * hexbin does for BinHex (hqx.c, "check line for
             * intermediate garbage"); here the test is stronger than an
             * alphabet, because a uu line's first character DECLARES how
             * many bytes it encodes, so the length has to agree.
             *
             * What this cannot do is notice a part that never arrived.
             * uuencode carries no length and no checksum anywhere, so a
             * set missing its MIDDLE part decodes to a short file with
             * nothing to object to. A missing LAST part is still caught:
             * the terminator and "end" live there. OPEN_ITEMS.md. */
            if (n < 0 || !unc_uu_line_is_data(l->buf, l->len)) continue;
            *bytes += (uint32_t)n;
            if (write) {
                if (c->sink->write(c->sink->ctx, fork, dec, n) != 0)
                    return UNC_ERR_SINK;
            }
        }
        if (l->eof) return UNC_ERR_TRUNCATED;
    }
}

/* Measure one document: sizes, name and Finder info. `in` must be
 * positioned at its begin line. */
static int uu_scan_doc(UncCtx *c, UncBufIn *in, uint32_t base, UuLine *l,
                       UuDoc *d)
{
    const uint8_t *nm;
    uint32_t nlen;
    int err;

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

    err = uu_section(c, in, base, l, UNC_FORK_DATA, 0, &d->data.bytes);
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
            err = uu_section(c, in, base, l, UNC_FORK_RSRC, 0, &d->rsrc.bytes);
            if (err != UNC_OK) return err;
            d->rsrc.present = 1;
            d->end = uu_abs(base, in);
        } else if (uu_tag_is(l, " .finfo")) {
            /* 16 bytes: type(4), creator(4), flags(2), then the
             * position and folder the Finder remembered. */
            uint8_t dec[UU_DEC_MAX];
            uint32_t got = 0;
            for (;;) {
                err = uu_readline(in, base, l);
                if (err != UNC_OK) return err;
                if (l->len == 0) { if (l->eof) return UNC_ERR_TRUNCATED; continue; }
                if (uu_is_end(l)) break;
                {
                    int32_t n = uu_decode_line(l, dec);
                    int32_t k;
                    if (n < 0) return UNC_ERR_CORRUPT;
                    if (n == 0) continue;
                    for (k = 0; k < n && got < 16; k++) d->info[got++] = dec[k];
                }
            }
            d->finfo.present = 1;
            d->finfo.bytes = got;
            d->end = uu_abs(base, in);
        } else {
            d->end = mark;      /* the next document's begin line */
            return UNC_OK;
        }
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

    l.over = c->opt.long_name;
    l.over_cap = c->opt.long_name_cap;
    l.over_len = 0;
    l.locked = 0;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap);
    if (!iobuf) return UNC_ERR_MEM;

    for (;;) {
        UncEntryInfo e;
        int sret, est = UNC_OK;
        int found = 0;

        /* Find the next begin line. */
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

        err = uu_scan_doc(c, &in, pos, &l, &d);
        if (err != UNC_OK) {
            if (any) err = UNC_OK;     /* trailing junk after a good doc */
            break;
        }

        unc_entry_clear(&e);
        if (d.name_len == 0) {
            if (c->opt.name_hint && c->opt.name_hint_len)
                unc_entry_set_name(&e, c->opt.name_hint, c->opt.name_hint_len);
        } else {
            unc_entry_set_name(&e, d.name, d.name_len);
            if (d.name_trunc) {
                e.name_truncated = d.name_have_full ? 2 : 1;
                e.name_full_len = (uint16_t)(d.name_full > 65535u ? 65535u
                                                                  : d.name_full);
            }
        }
        e.data_size = d.data.bytes;
        e.rsrc_size = d.rsrc.bytes;
        if (d.finfo.present && d.finfo.bytes >= 8) {
            e.type    = unc_get_u32be(d.info);
            e.creator = unc_get_u32be(d.info + 4);
            if (d.finfo.bytes >= 10) e.finder_flags = unc_get_u16be(d.info + 8);
        }

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; break; }
        if (sret == 0) {
            if (!c->opt.list_only) {
                /* Second pass over the same document, this time writing. */
                uint32_t n;
                if (c->io->seek(c->io->ctx, d.start) < 0) {
                    est = UNC_ERR_IO;
                } else {
                    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
                    l.eof = 0;
                    est = uu_readline(&in, d.start, &l);
                    if (est == UNC_OK && !uu_is_begin(&l)) est = UNC_ERR_CORRUPT;
                    if (est == UNC_OK)
                        est = uu_section(c, &in, d.start, &l, UNC_FORK_DATA,
                                         !c->opt.test_only, &n);
                    if (est == UNC_OK && d.rsrc.present) {
                        /* Skip to the .rsrc section's own begin line. */
                        for (;;) {
                            est = uu_readline(&in, d.start, &l);
                            if (est != UNC_OK) break;
                            if (l.len == 0) { if (l.eof) { est = UNC_ERR_TRUNCATED; break; } continue; }
                            if (uu_is_begin(&l) && uu_tag_is(&l, " .rsrc")) {
                                est = uu_section(c, &in, d.start, &l, UNC_FORK_RSRC,
                                                 !c->opt.test_only, &n);
                                break;
                            }
                            if (uu_is_begin(&l)) { est = UNC_ERR_CORRUPT; break; }
                        }
                    }
                }
            }
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
        }
        any = 1;
        pos = d.end;
        if (d.end <= d.start) break;      /* no forward progress */
    }

    unc_free(c->al, iobuf);
    if (!any && err == UNC_OK) return UNC_ERR_FORMAT;
    return err;
}

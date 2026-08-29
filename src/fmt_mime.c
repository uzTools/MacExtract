/*
 * fmt_mime.c — MIME messages (RFC 2045/2046), which is how a Macintosh
 * file crossed the Internet once mail had stopped being seven-bit: a
 * base64 or quoted-printable part per attachment, and — for a file that
 * still had to arrive with both forks and its Finder info —
 * multipart/appledouble (RFC 1740), an application/applefile header
 * part in front of the data fork.
 *
 * Sources (transcribed, never guessed):
 *   reference/mpack/decode.c  — ParseHeaders(): a header line is a name
 *       with no space or control character before its colon, and a line
 *       starting with space or tab continues the one before; the first
 *       line that is neither ends the headers and belongs to the body.
 *       ParseContent()/getParam(): parameters are ';'-separated, a
 *       value may be a quoted string with '\' escapes. parseEncoding().
 *       from64()/fromqp(). saveToFile(): the filename is the
 *       Content-Disposition's `filename` first and the Content-Type's
 *       `name` second. handleMessage(): a `text/...` part with no filename
 *       is the message BODY, not an attachment.
 *   reference/mpack/part.c    — pendingboundary()/part_readboundary():
 *       a boundary is "--" and the boundary string at the start of a
 *       line, the newline in front of it belongs to the boundary and
 *       not to the part, a trailing "--" closes that multipart, and a
 *       boundary belonging to an ENCLOSING multipart closes every part
 *       inside it.
 *   reference/mpack/encode.c  — the shape mpack writes for a Macintosh
 *       file: multipart/appledouble, application/applefile first, the
 *       data fork second.
 *   reference/mpack/macfile.c — encode_applefile(): the entry ids in
 *       that header part (2 resource fork, 3 real name, 9 Finder info),
 *       the same layout src/fmt_applesingle.c already reads for a file
 *       that arrived on its own.
 *   reference/mpack/unixos.c  — os_newtypedfile(): a part with no
 *       filename is called "part1", "part2", ...
 *   reference/mpack/decode.c  — handleUuencode(): a text part with no
 *       encoding and no filename may still BE a file, pasted into the
 *       message; mpack tests for that at the top level only, and this
 *       walk runs the same test at every depth (see mime_body_nested).
 *   reference/mpack/uudecode.c — uudecodeline(), the 4-into-3 loop
 *       src/fmt_uu.c transcribes and this file calls rather than
 *       transcribing a second time.
 *
 * mpack recurses through nested multiparts. This walks them with an
 * explicit stack of at most MIME_MAX_DEPTH boundaries, because nothing
 * in this engine may recurse (CLAUDE.md, 68000 discipline). The walk is
 * linear in the file either way: a part's end is the next boundary line.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define MIME_MAX_DEPTH   4
#define MIME_BND_MAX     70      /* RFC 2046; reference/mpack/part.h    */
#define MIME_LINE_MAX    1000    /* RFC 5322 caps a line at 998         */
#define MIME_HDR_MAX     512     /* one header, continuation lines and all */
#define MIME_CTYPE_MAX   63
#define MIME_IOBUF       4096
#define MIME_AF_PREFIX   512     /* of an applefile part, decoded       */
#define MIME_AF_ENTRIES  16
#define MIME_SCAN_MAX    16384u  /* how far the probe looks for a header */
#define MIME_NEST_SCAN   4096u   /* how far into a body part the test for a
                                  * pasted document looks */

/* MIME_CTE_UU is not a Content-Transfer-Encoding: no header names it
 * here. mpack has no such value either — an encoding it does not know
 * warns and falls through as `enc_none` (parseEncoding) — so a part
 * that says "x-uuencode" arrives here as NONE like any other, and it
 * is the BODY that decides. */
enum { MIME_CTE_NONE = 0, MIME_CTE_QP, MIME_CTE_B64, MIME_CTE_UU };

/* What a body part the walk would otherwise drop turns out to hold. */
enum { MIME_NEST_NONE = 0, MIME_NEST_UU, MIME_NEST_DOC };

/* Entry ids inside an application/applefile part.
 * Source: reference/mpack/macfile.c, and src/fmt_applesingle.c. */
#define AF_MAGIC_DOUBLE  0x00051607u
#define AF_MAGIC_SINGLE  0x00051600u
#define AF_ID_DATA       1u
#define AF_ID_RSRC       2u
#define AF_ID_NAME       3u
#define AF_ID_FINFO      9u

typedef struct MimePart {
    uint32_t start, end;         /* raw byte range of the body */
    int      cte;
} MimePart;

typedef struct MimeHdrs {
    uint8_t  ctype[MIME_CTYPE_MAX + 1];   /* "multipart/mixed", lowercased */
    uint8_t  bnd[MIME_BND_MAX + 1];
    int32_t  bndlen;
    uint8_t  name[UNC_NAME_MAX + 1];
    uint32_t namelen;
    uint8_t  name_trunc;         /* the header named more than fits */
    int      cte;
    uint32_t body;               /* absolute offset of the first body byte */
} MimeHdrs;

/* What a scan for the next boundary found. */
typedef struct MimeStop {
    int      level;              /* boundary stack index, -1 at EOF */
    int      final;              /* it carried the closing "--"     */
    uint32_t body_end;           /* end of the part being scanned   */
    uint32_t next;               /* first byte after the boundary line */
} MimeStop;

/* What an application/applefile part says about the file it belongs to.
 * Only the prefix of the part is decoded here — the header, the entry
 * table and the small entries in front of the forks, which is where
 * every writer puts the name and the Finder info
 * (reference/mpack/macfile.c encode_applefile). An entry that sits
 * further in is left alone rather than guessed at; the name then comes
 * from the Content-Type, as it does for a part with no applefile. */
typedef struct MimeApple {
    uint32_t rsrc_off, rsrc_len;
    int      have_rsrc;
    uint8_t  name[UNC_NAME_MAX + 1];
    uint32_t namelen;
    uint8_t  name_trunc;         /* the part named more than fits */
    uint32_t name_full;          /* by how much, where the part says */
    uint32_t type, creator;
    uint16_t flags;
    int      have_finfo;
} MimeApple;

typedef struct MimeCtx {
    UncCtx  *c;
    UncBufIn in;
    uint32_t base;               /* where `in` was last initialised */
    uint8_t *iobuf;              /* MIME_IOBUF                      */
    uint8_t *line;               /* MIME_LINE_MAX + 1               */
    uint8_t *hdr;                /* MIME_HDR_MAX + 1                */
    uint8_t *afbuf;              /* MIME_AF_PREFIX                  */
    uint8_t *uub;                /* UNC_UU_DEC_MAX: one decoded uu line */
    uint8_t  nname[UNC_NAME_MAX + 1];  /* a "begin" line's name */
    uint32_t nnamelen;
    uint8_t  bnd[MIME_MAX_DEPTH][MIME_BND_MAX + 1];
    int32_t  bndlen[MIME_MAX_DEPTH];
    int      appledouble[MIME_MAX_DEPTH];
    uint8_t  mname[MIME_MAX_DEPTH][UNC_NAME_MAX + 1];
    uint32_t mnamelen[MIME_MAX_DEPTH];
    uint8_t  mnametrunc[MIME_MAX_DEPTH];
    uint8_t  hdrcut;             /* the header being read did not fit */
    int      depth;
    int      partno;             /* for the "part1", "part2" names  */
    /* The walk's working state lives here rather than on the stack:
     * one MimeCtx is ~1.9 KB and the engine's call-depth budget is
     * 4 KB for the WHOLE chain (CLAUDE.md; FORMATS.md, "Stack"). */
    MimeHdrs h;
    MimeStop s;
    MimePart af;
    MimeApple apple;
} MimeCtx;

/* ------------------------------------------------------------------ */
/* Small text helpers                                                 */
/* ------------------------------------------------------------------ */

static int mime_lower(int c)
{
    return (c >= 'A' && c <= 'Z') ? c + ('a' - 'A') : c;
}

/* Length of `pfx` if it matches the start of s case-insensitively. */
static int32_t mime_ci_prefix(const uint8_t *s, int32_t len, const char *pfx)
{
    int32_t i;
    for (i = 0; pfx[i]; i++) {
        if (i >= len) return 0;
        if (mime_lower(s[i]) != mime_lower((unsigned char)pfx[i])) return 0;
    }
    return i;
}

static int mime_is_space(int c)
{
    return c == ' ' || c == '\t';
}

static int32_t mime_strlen(const char *s)
{
    int32_t n = 0;
    while (s[n]) n++;
    return n;
}

/* Length of a NUL-terminated field this file filled in itself. */
static int32_t mime_len(const uint8_t *s)
{
    int32_t n = 0;
    while (s[n]) n++;
    return n;
}

/* mpack's test for a header line: a run of printable, non-space
 * characters, then a colon. Source: ParseHeaders(). */
static int mime_is_header(const uint8_t *s, int32_t len)
{
    int32_t i;
    for (i = 0; i < len; i++) {
        if (s[i] == ':') return i > 0;
        if (s[i] <= ' ' || s[i] >= 0177) return 0;
    }
    return 0;
}

/* The value of parameter `key` out of a header value: `; key=value` or
 * `; key="value"`, the quoted form honouring '\' escapes.
 * Source: reference/mpack/decode.c ParseContent()/getParam(). */
static uint32_t mime_param(const uint8_t *h, int32_t hlen, const char *key,
                           uint8_t *out, uint32_t cap, int *trunc)
{
    int32_t i = 0;
    int32_t klen = mime_strlen(key);

    while (i < hlen) {
        int32_t start;
        /* Step to the next ';' that is not inside a quoted string. */
        while (i < hlen && h[i] != ';') {
            if (h[i] == '"') {
                i++;
                while (i < hlen && h[i] != '"') {
                    if (h[i] == '\\' && i + 1 < hlen) i++;
                    i++;
                }
            }
            i++;
        }
        if (i >= hlen) break;
        i++;                                        /* past the ';' */
        while (i < hlen && mime_is_space(h[i])) i++;
        start = i;
        if (mime_ci_prefix(h + start, hlen - start, key) != klen) continue;
        i = start + klen;
        while (i < hlen && mime_is_space(h[i])) i++;
        if (i >= hlen || h[i] != '=') continue;
        i++;
        while (i < hlen && mime_is_space(h[i])) i++;
        {
            uint32_t n = 0, seen = 0;
            if (i < hlen && h[i] == '"') {
                i++;
                while (i < hlen && h[i] != '"') {
                    if (h[i] == '\\' && i + 1 < hlen) i++;
                    seen++;
                    if (n < cap) out[n++] = h[i];
                    i++;
                }
            } else {
                while (i < hlen && h[i] != ';' && !mime_is_space(h[i])) {
                    seen++;
                    if (n < cap) out[n++] = h[i];
                    i++;
                }
            }
            if (trunc) *trunc = seen > n;
            return n;
        }
    }
    return 0;
}

/* The bare content type, lowercased: everything up to a ';', a space or
 * a comment. Source: ParseContent()'s "strip whitespace" loop. */
static void mime_ctype_of(const uint8_t *h, int32_t hlen, uint8_t *out)
{
    int32_t i = 0, n = 0;
    while (i < hlen && mime_is_space(h[i])) i++;
    while (i < hlen && h[i] != ';' && !mime_is_space(h[i]) && h[i] != '(') {
        if (n < MIME_CTYPE_MAX) out[n++] = (uint8_t)mime_lower(h[i]);
        i++;
    }
    out[n] = 0;
}

/* Source: reference/mpack/decode.c parseEncoding(). Anything this does
 * not name — 7bit, 8bit, binary, x-uuencode — leaves the bytes alone;
 * a uuencoded body posted to mail is claimed by the uuencode probe
 * before this format is reached (unc_sniff). */
static int mime_cte_of(const uint8_t *h, int32_t hlen)
{
    while (hlen > 0 && mime_is_space(*h)) { h++; hlen--; }
    if (mime_ci_prefix(h, hlen, "base64")) return MIME_CTE_B64;
    if (mime_ci_prefix(h, hlen, "quoted-printable")) return MIME_CTE_QP;
    return MIME_CTE_NONE;
}

/* ------------------------------------------------------------------ */
/* Positioning                                                        */
/* ------------------------------------------------------------------ */

static int mime_seek(MimeCtx *m, uint32_t pos)
{
    if (m->c->io->seek(m->c->io->ctx, pos) < 0) return UNC_ERR_IO;
    unc_bufin_init(&m->in, m->c->io, &m->c->ps, m->iobuf, MIME_IOBUF);
    m->base = pos;
    return UNC_OK;
}

static uint32_t mime_tell(MimeCtx *m)
{
    return m->base + unc_bufin_tell(&m->in);
}

/* ------------------------------------------------------------------ */
/* Headers                                                            */
/* ------------------------------------------------------------------ */

enum { MIME_H_NONE = 0, MIME_H_TYPE, MIME_H_CTE, MIME_H_DISP };

static void mime_hdr_apply(MimeCtx *m, MimeHdrs *h, int which, int32_t hlen)
{
    switch (which) {
    case MIME_H_TYPE:
        mime_ctype_of(m->hdr, hlen, h->ctype);
        h->bndlen = (int32_t)mime_param(m->hdr, hlen, "boundary",
                                        h->bnd, MIME_BND_MAX, NULL);
        h->bnd[h->bndlen] = 0;
        if (h->namelen == 0) {
            int t = 0;
            h->namelen = mime_param(m->hdr, hlen, "name",
                                    h->name, UNC_NAME_MAX, &t);
            h->name_trunc = (uint8_t)(t || m->hdrcut);
        }
        break;
    case MIME_H_CTE:
        h->cte = mime_cte_of(m->hdr, hlen);
        break;
    case MIME_H_DISP:
        /* The disposition's filename wins over the type's name. */
        {
            int t = 0;
            uint32_t n = mime_param(m->hdr, hlen, "filename",
                                    h->name, UNC_NAME_MAX, &t);
            if (n) { h->namelen = n; h->name_trunc = (uint8_t)(t || m->hdrcut); }
        }
        break;
    default:
        break;
    }
}

/* Read one part's headers, starting at `pos`. On return h->body is the
 * first byte of the body and `m->in` is positioned there. */
static int mime_headers(MimeCtx *m, uint32_t pos, MimeHdrs *h)
{
    int which = MIME_H_NONE;
    int32_t hlen = 0;
    int err;
    /* Whether a header — ANY header — is open, which is not the same as
     * `which`: a folded `Received:` continues over three lines and is of
     * no interest, and taking its continuation for the start of the body
     * would end the headers half way through them. Real mail folds. */
    int inhdr = 0;

    h->ctype[0] = 0;
    h->bndlen = 0;
    h->bnd[0] = 0;
    h->name[0] = 0;
    h->namelen = 0;
    h->name_trunc = 0;
    h->cte = MIME_CTE_NONE;

    err = mime_seek(m, pos);
    if (err != UNC_OK) return err;

    for (;;) {
        uint32_t start = mime_tell(m);
        int32_t llen = 0;
        int eof = 0;

        err = unc_readline(&m->in, m->line, MIME_LINE_MAX + 1, &llen, &eof);
        if (err != UNC_OK) {                    /* nothing left at all */
            mime_hdr_apply(m, h, which, hlen);
            h->body = mime_tell(m);
            return UNC_OK;
        }
        if (llen == 0) {                        /* the blank line: done */
            mime_hdr_apply(m, h, which, hlen);
            h->body = mime_tell(m);
            return UNC_OK;
        }
        if (inhdr && mime_is_space(m->line[0])) {
            int32_t i = 0;                      /* a continuation line */
            if (which != MIME_H_NONE) {
                while (i < llen && hlen < MIME_HDR_MAX)
                    m->hdr[hlen++] = m->line[i++];
                if (i < llen) m->hdrcut = 1;
                m->hdr[hlen] = 0;
            }
            continue;
        }
        if (!mime_is_header(m->line, llen)) {
            /* Not a header and not a continuation: the headers ended
             * here and this line is body (mpack pushes it back). */
            mime_hdr_apply(m, h, which, hlen);
            h->body = start;
            return UNC_OK;
        }
        mime_hdr_apply(m, h, which, hlen);
        which = MIME_H_NONE;
        hlen = 0;
        m->hdrcut = 0;
        inhdr = 1;
        {
            int32_t k;
            if ((k = mime_ci_prefix(m->line, llen, "content-type:")))
                which = MIME_H_TYPE;
            else if ((k = mime_ci_prefix(m->line, llen,
                                         "content-transfer-encoding:")))
                which = MIME_H_CTE;
            else if ((k = mime_ci_prefix(m->line, llen, "content-disposition:")))
                which = MIME_H_DISP;
            if (which != MIME_H_NONE) {
                int32_t i = k;
                while (i < llen && hlen < MIME_HDR_MAX) m->hdr[hlen++] = m->line[i++];
                if (i < llen) m->hdrcut = 1;
                m->hdr[hlen] = 0;
            }
        }
    }
}

/* ------------------------------------------------------------------ */
/* Boundaries                                                         */
/* ------------------------------------------------------------------ */

/* Which stack level this line closes, or -1. Source: pendingboundary()
 * — "--", then a boundary; the outermost match wins, because a boundary
 * from an enclosing multipart ends everything inside it. */
static int mime_boundary_at(MimeCtx *m, const uint8_t *line, int32_t llen,
                            int *final)
{
    int i;

    *final = 0;
    if (llen < 2 || line[0] != '-' || line[1] != '-') return -1;
    for (i = 0; i < m->depth; i++) {
        int32_t bl = m->bndlen[i];
        int32_t k;
        if (bl == 0 || llen - 2 < bl) continue;
        for (k = 0; k < bl; k++)
            if (line[2 + k] != m->bnd[i][k]) break;
        if (k != bl) continue;
        if (llen - 2 - bl >= 2 && line[2 + bl] == '-' && line[3 + bl] == '-')
            *final = 1;
        return i;
    }
    return -1;
}

/* How many bytes of line terminator sit immediately before `pos`. The
 * CRLF in front of a boundary belongs to the boundary and not to the
 * part (RFC 2046; mpack ends the part at that newline). */
static uint32_t mime_term_before(MimeCtx *m, uint32_t pos)
{
    uint8_t t[2];

    if (pos == 0) return 0;
    if (pos >= 2) {
        if (unc_read_at(m->c->io, pos - 2, t, 2) != UNC_OK) return 0;
        if (t[0] == '\r' && t[1] == '\n') return 2;
        if (t[1] == '\n' || t[1] == '\r') return 1;
        return 0;
    }
    if (unc_read_at(m->c->io, pos - 1, t, 1) != UNC_OK) return 0;
    return (t[0] == '\n' || t[0] == '\r') ? 1u : 0u;
}

/* Read forward from `from` to the next boundary line or to EOF. */
static int mime_scan(MimeCtx *m, uint32_t from, MimeStop *s)
{
    int err = mime_seek(m, from);
    if (err != UNC_OK) return err;

    for (;;) {
        uint32_t start = mime_tell(m);
        int32_t llen = 0;
        int eof = 0, final = 0, lvl;

        err = unc_readline(&m->in, m->line, MIME_LINE_MAX + 1, &llen, &eof);
        if (err != UNC_OK) {
            s->level = -1;
            s->final = 0;
            s->body_end = mime_tell(m);
            s->next = s->body_end;
            return UNC_OK;
        }
        lvl = mime_boundary_at(m, m->line, llen, &final);
        if (lvl >= 0) {
            s->level = lvl;
            s->final = final;
            s->body_end = start - mime_term_before(m, start);
            s->next = mime_tell(m);
            return UNC_OK;
        }
        if (eof) {
            s->level = -1;
            s->final = 0;
            s->body_end = mime_tell(m);
            s->next = s->body_end;
            return UNC_OK;
        }
    }
}

/* ------------------------------------------------------------------ */
/* Decoding one part                                                  */
/* ------------------------------------------------------------------ */

typedef struct MimeDec {
    MimeCtx *m;
    UncBufIn in;
    int      cte;
    UncB64   b64;
    uint8_t  out[3];
    int      nout, iout;
    int      flushed;
    /* uuencode: one decoded line at a time, in the walker's buffer
     * rather than this frame's — 45 bytes on a 4 KB stack budget. */
    uint8_t *ub;
    int      unout, uiout;
    int      udone;
} MimeDec;

static int mime_dec_open(MimeDec *d, MimeCtx *m, const MimePart *p,
                         uint8_t *iobuf)
{
    d->m = m;
    d->cte = p->cte;
    d->nout = d->iout = 0;
    d->flushed = 0;
    d->ub = m->uub;
    d->unout = d->uiout = 0;
    d->udone = 0;
    unc_b64_reset(&d->b64);
    if (m->c->io->seek(m->c->io->ctx, p->start) < 0) return UNC_ERR_IO;
    unc_bufin_init(&d->in, m->c->io, &m->c->ps, iobuf, MIME_IOBUF);
    d->in.limit = p->end > p->start ? p->end - p->start : 0;
    return UNC_OK;
}

/* One hex digit. Source: reference/mpack/decode.c index_hex. */
static int mime_hex(int c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

/* Does this line end a uu document? Source: reference/macutils/hexbin,
 * as src/fmt_uu.c reads it — the word "end" on a line of its own. */
static int mime_uu_is_end(const uint8_t *l, int32_t len)
{
    return len >= 3 && l[0] == 'e' && l[1] == 'n' && l[2] == 'd';
}

/* One uuencoded line at a time, through the same two helpers fmt_uu.c
 * decodes a file with. A line that cannot be uu data is skipped rather
 * than refused: what sits between the lines of a posted document is
 * mail, not data (the reasoning is fmt_uu.c's uu_section). */
static int mime_uu_next(MimeDec *d)
{
    if (d->uiout < d->unout) return d->ub[d->uiout++];

    while (!d->udone) {
        int32_t llen = 0, n;
        int eof = 0;

        if (unc_readline(&d->in, d->m->line, UNC_UU_LINE_MAX + 1,
                         &llen, &eof) != UNC_OK) break;
        if (mime_uu_is_end(d->m->line, llen)) break;
        n = unc_uu_decode_line(d->m->line, llen, d->ub);
        if (n > 0 && unc_uu_line_is_data(d->m->line, llen)) {
            d->unout = (int)n;
            d->uiout = 1;
            return d->ub[0];
        }
        if (eof) break;
    }
    d->udone = 1;
    return -1;
}

/* The next decoded byte, or -1 when the part ends (or on error, which
 * `d->in.err` then holds). */
static int mime_dec_next(MimeDec *d)
{
    if (d->cte == MIME_CTE_UU) return mime_uu_next(d);
    if (d->iout < d->nout) return d->out[d->iout++];

    for (;;) {
        int ch = unc_bufin_next(&d->in);

        if (ch < 0) {
            if (d->cte == MIME_CTE_B64 && !d->flushed) {
                d->flushed = 1;
                d->nout = unc_b64_flush(&d->b64, d->out);
                d->iout = 0;
                if (d->nout > 0) return d->out[d->iout++];
            }
            return -1;
        }

        if (d->cte == MIME_CTE_B64) {
            int n;
            if (d->b64.done) return -1;
            n = unc_b64_feed(&d->b64, ch, d->out);
            if (n > 0) { d->nout = n; d->iout = 1; return d->out[0]; }
            continue;
        }

        if (d->cte == MIME_CTE_QP) {
            int c1, c2, h1, h2;
            if (ch != '=') return ch;
            c1 = unc_bufin_next(&d->in);
            if (c1 < 0) return -1;
            if (c1 == '\n') continue;                  /* soft line break */
            if (c1 == '\r') {
                if (unc_bufin_peek(&d->in) == '\n') (void)unc_bufin_next(&d->in);
                continue;
            }
            c2 = unc_bufin_next(&d->in);
            if (c2 < 0) return -1;
            h1 = mime_hex(c1);
            h2 = mime_hex(c2);
            if (h1 < 0 || h2 < 0) return '=';          /* not an escape */
            return (h1 << 4) | h2;
        }

        return ch;                                      /* 7bit/8bit/binary */
    }
}

/* Run a part through the decoder: counts always, writes when `write`.
 * `skip` bytes are decoded and discarded first, and at most `limit`
 * bytes are produced (UNC_SIZE_UNKNOWN for all of them). */
static int mime_dec_run(MimeCtx *m, const MimePart *p, UncFork fork,
                        int write, uint32_t skip, uint32_t limit,
                        uint32_t *bytes)
{
    MimeDec d;
    uint8_t buf[256];
    uint32_t n = 0;
    int err;

    *bytes = 0;
    err = mime_dec_open(&d, m, p, m->iobuf);
    if (err != UNC_OK) return err;

    while (skip > 0) {
        int ch = mime_dec_next(&d);
        if (ch < 0) break;
        skip--;
    }

    for (;;) {
        int ch;
        if (limit != UNC_SIZE_UNKNOWN && *bytes >= limit) break;
        ch = mime_dec_next(&d);
        if (ch < 0) break;
        buf[n++] = (uint8_t)ch;
        (*bytes)++;
        if (n == sizeof buf) {
            if (write && m->c->sink->write(m->c->sink->ctx, fork, buf,
                                           (int32_t)n) != 0)
                return UNC_ERR_SINK;
            n = 0;
        }
    }
    if (n > 0 && write &&
        m->c->sink->write(m->c->sink->ctx, fork, buf, (int32_t)n) != 0)
        return UNC_ERR_SINK;

    if (d.in.err != UNC_OK && d.in.err != UNC_ERR_TRUNCATED) return d.in.err;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Entries                                                            */
/* ------------------------------------------------------------------ */


static int mime_read_applefile(MimeCtx *m, const MimePart *p, MimeApple *a)
{
    uint32_t got = 0, magic;
    MimeDec d;
    int n, i, err;

    a->rsrc_off = a->rsrc_len = 0;
    a->have_rsrc = a->have_finfo = 0;
    a->namelen = 0;
    a->name_trunc = 0;
    a->name_full = 0;
    a->type = a->creator = 0;
    a->flags = 0;

    err = mime_dec_open(&d, m, p, m->iobuf);
    if (err != UNC_OK) return err;
    while (got < MIME_AF_PREFIX) {
        int ch = mime_dec_next(&d);
        if (ch < 0) break;
        m->afbuf[got++] = (uint8_t)ch;
    }

    if (got < 26) return UNC_ERR_TRUNCATED;
    magic = unc_get_u32be(m->afbuf);
    if (magic != AF_MAGIC_DOUBLE && magic != AF_MAGIC_SINGLE)
        return UNC_ERR_FORMAT;

    n = (int)unc_get_u16be(m->afbuf + 24);
    if (n > MIME_AF_ENTRIES) n = MIME_AF_ENTRIES;
    for (i = 0; i < n; i++) {
        uint32_t at = 26u + (uint32_t)i * 12u;
        uint32_t id, off, elen;
        if (at + 12u > got) break;
        id   = unc_get_u32be(m->afbuf + at);
        off  = unc_get_u32be(m->afbuf + at + 4);
        elen = unc_get_u32be(m->afbuf + at + 8);
        switch (id) {
        case AF_ID_RSRC:
            a->rsrc_off = off; a->rsrc_len = elen; a->have_rsrc = 1;
            break;
        case AF_ID_NAME:
            if (elen > 0 && off + elen <= got) {
                uint32_t k, nl = elen > UNC_NAME_MAX ? UNC_NAME_MAX : elen;
                for (k = 0; k < nl; k++) a->name[k] = m->afbuf[off + k];
                a->namelen = nl;
                a->name_trunc = (uint8_t)(elen > nl);
                a->name_full = elen;
            }
            break;
        case AF_ID_FINFO:
            if (elen >= 10 && off + 10 <= got) {
                a->type    = unc_get_u32be(m->afbuf + off);
                a->creator = unc_get_u32be(m->afbuf + off + 4);
                a->flags   = unc_get_u16be(m->afbuf + off + 8);
                a->have_finfo = 1;
            }
            break;
        default:
            break;
        }
    }
    return UNC_OK;
}

/* Emit one entry: a body part, optionally with the applefile part that
 * came in front of it inside a multipart/appledouble. */
static int mime_emit(MimeCtx *m, const MimeHdrs *h, const MimePart *data,
                     const MimePart *af, int *any)
{
    UncEntryInfo e;
    MimeApple *a = &m->apple;
    uint8_t nbuf[16];
    uint32_t dsize = 0;
    int have_af = 0, sret, err = UNC_OK, est = UNC_OK;

    if (af) {
        if (mime_read_applefile(m, af, a) == UNC_OK) have_af = 1;
    }

    if (data) {
        err = mime_dec_run(m, data, UNC_FORK_DATA, 0, 0, UNC_SIZE_UNKNOWN,
                           &dsize);
        if (err != UNC_OK && err != UNC_ERR_TRUNCATED) return err;
    }

    unc_entry_clear(&e);
    m->partno++;

    /* The name, best first: the applefile's own, then this part's
     * filename, then the name on the multipart that holds them both,
     * then mpack's "partN". */
    if (have_af && a->namelen) {
        unc_entry_set_name(&e, a->name, a->namelen);
        if (a->name_trunc) {
            e.name_truncated = 1;
            e.name_full_len = (uint16_t)(a->name_full > 65535u ? 65535u
                                                               : a->name_full);
        }
    }
    else if (h && h->namelen) {
        unc_entry_set_name(&e, h->name, h->namelen);
        if (h->name_trunc) e.name_truncated = 1;
    }
    else if (data && data->cte == MIME_CTE_UU && m->nnamelen) {
        unc_entry_set_name(&e, m->nname, m->nnamelen);   /* "begin" line */
    }
    else if (m->depth > 0 && m->mnamelen[m->depth - 1]) {
        unc_entry_set_name(&e, m->mname[m->depth - 1],
                           m->mnamelen[m->depth - 1]);
        if (m->mnametrunc[m->depth - 1]) e.name_truncated = 1;
    }
    else {
        int k = 0, v = m->partno, digits = 0, j;
        char tmp[8];
        nbuf[k++] = 'p'; nbuf[k++] = 'a'; nbuf[k++] = 'r'; nbuf[k++] = 't';
        do { tmp[digits++] = (char)('0' + v % 10); v /= 10; } while (v && digits < 7);
        for (j = digits - 1; j >= 0; j--) nbuf[k++] = (uint8_t)tmp[j];
        unc_entry_set_name(&e, nbuf, (uint32_t)k);
    }

    e.data_size = dsize;
    e.comp_data_size = data ? data->end - data->start : 0;
    if (have_af) {
        e.rsrc_size = a->have_rsrc ? a->rsrc_len : 0;
        e.comp_rsrc_size = e.rsrc_size;
        if (a->have_finfo) {
            e.type = a->type;
            e.creator = a->creator;
            e.finder_flags = a->flags;
        }
    }

    sret = m->c->sink->begin_entry(m->c->sink->ctx, &e);
    if (sret < 0) return UNC_ERR_SINK;
    if (sret > 0) { *any = 1; return UNC_OK; }

    if (!m->c->opt.list_only) {
        uint32_t n;
        int write = !m->c->opt.test_only;
        if (data && est == UNC_OK)
            est = mime_dec_run(m, data, UNC_FORK_DATA, write, 0,
                               UNC_SIZE_UNKNOWN, &n);
        if (have_af && a->have_rsrc && a->rsrc_len > 0 && est == UNC_OK) {
            est = mime_dec_run(m, af, UNC_FORK_RSRC, write, a->rsrc_off,
                               a->rsrc_len, &n);
            if (est == UNC_OK && n != a->rsrc_len) est = UNC_ERR_TRUNCATED;
        }
        if (est == UNC_ERR_TRUNCATED && data == NULL && !have_af)
            est = UNC_OK;
    }

    if (m->c->sink->end_entry(m->c->sink->ctx, est) < 0) return UNC_ERR_SINK;
    *any = 1;
    if (unc_fatal(est))
        return est;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* The walk                                                           */
/* ------------------------------------------------------------------ */

/* Is this part TEXT, in mpack's sense: a `text/...` type, or none at
 * all — decode.c's defaultContentType is "text/plain". */
static int mime_is_text(const MimeHdrs *h)
{
    int32_t n = mime_len(h->ctype);
    if (n == 0) return 1;
    return mime_ci_prefix(h->ctype, n, "text/") ? 1 : 0;
}

/* A text part with no filename is the note the sender typed — except
 * when it is a file somebody pasted into the message, which is a shape
 * mail carried for as long as it carried attachments. mpack tests for
 * exactly one such document and only at the top level: handleUuencode()
 * runs for a depth-0 text part with no encoding, no `filename` and no
 * `name` (reference/mpack/decode.c). This walk runs that test at EVERY
 * depth, because since 2026-08-29 a multipart holding a uuencoded part
 * is claimed here rather than by the uuencode walk, and dropping the
 * part as a note would lose the file that walk used to write.
 *
 * A BinHex or btoa document in the same position is emitted as it
 * lies, undecoded: its own extractor reads the file this writes, and
 * saving the bytes is what keeps the change from costing a capability.
 * The two markers are the ones src/fmt_binhex.c and src/fmt_btoa.c
 * identify their formats by.
 *
 * Returns MIME_NEST_*, and for a uu document the offset its data
 * starts at; the name off the "begin" line is left in m->nname. */
static int mime_body_nested(MimeCtx *m, uint32_t start, uint32_t end,
                            uint32_t *data_at)
{
    static const char bh_banner[] =
        "(This file must be converted with BinHex";
    uint32_t stop = start + MIME_NEST_SCAN;

    m->nnamelen = 0;
    if (end <= start) return MIME_NEST_NONE;
    if (stop > end) stop = end;
    if (mime_seek(m, start) != UNC_OK) return MIME_NEST_NONE;
    m->in.limit = end - start;

    for (;;) {
        int32_t llen = 0;
        int eof = 0;

        if (mime_tell(m) >= stop) break;
        if (unc_readline(&m->in, m->line, MIME_LINE_MAX + 1,
                         &llen, &eof) != UNC_OK) break;

        if (mime_ci_prefix(m->line, llen, bh_banner) ||
            mime_ci_prefix(m->line, llen, "xbtoa Begin") ||
            mime_ci_prefix(m->line, llen, "xbtoa5 "))
            return MIME_NEST_DOC;

        if (llen >= 6 && mime_ci_prefix(m->line, llen, "begin ")) {
            int32_t so, eo, k;
            uint32_t at;

            /* The name first: the next readline writes over it. */
            unc_uu_name_span(m->line, llen, &so, &eo);
            for (k = 0; k < eo - so && k < (int32_t)UNC_NAME_MAX; k++)
                m->nname[k] = m->line[so + k];
            m->nnamelen = (uint32_t)k;
            at = mime_tell(m);

            /* A "begin" line alone occurs in prose. What makes it a uu
             * document is the line after it (unc_uu_line_is_data). */
            for (;;) {
                if (unc_readline(&m->in, m->line, UNC_UU_LINE_MAX + 1,
                                 &llen, &eof) != UNC_OK) break;
                if (llen == 0) {
                    if (eof) break;
                    continue;                      /* mailers wrap */
                }
                if (unc_uu_line_is_data(m->line, llen)) {
                    *data_at = at;
                    return MIME_NEST_UU;
                }
                break;
            }
            m->nnamelen = 0;
            return MIME_NEST_NONE;
        }
        if (eof) break;
    }
    return MIME_NEST_NONE;
}

/* Is this part an attachment, or the message body? Source: mpack's
 * handleMessage — a `text/...` part with no filename of its own is the
 * note the sender typed, and munpack does not write it out. */
static int mime_is_attachment(const MimeHdrs *h)
{
    int32_t n = mime_len(h->ctype);
    if (h->namelen) return 1;
    if (n == 0) return 0;                           /* no type: body */
    if (mime_ci_prefix(h->ctype, n, "text/")) return 0;
    if (mime_ci_prefix(h->ctype, n, "multipart/")) return 0;
    if (mime_ci_prefix(h->ctype, n, "message/")) return 0;
    return 1;
}

int unc_mime_extract(UncCtx *c)
{
    /* One allocation: the walker, then the four buffers behind it. The
     * struct goes first because the allocator returns memory aligned
     * for anything, and the buffers after it are bytes. */
    MimeCtx *m;
    uint8_t *blk, *buf;
    uint32_t pos = 0;
    int have_af = 0, af_level = -1, any = 0, err = UNC_OK;
    int guard = 0;

    blk = (uint8_t *)unc_alloc(c->al, (uint32_t)sizeof(MimeCtx) +
                                      MIME_IOBUF + MIME_LINE_MAX + 1 +
                                      MIME_HDR_MAX + 1 + MIME_AF_PREFIX +
                                      UNC_UU_DEC_MAX);
    if (!blk) return UNC_ERR_MEM;
    m = (MimeCtx *)(void *)blk;
    buf = blk + sizeof(MimeCtx);

    m->c = c;
    m->iobuf = buf;
    m->line  = buf + MIME_IOBUF;
    m->hdr   = m->line + MIME_LINE_MAX + 1;
    m->afbuf = m->hdr + MIME_HDR_MAX + 1;
    m->uub   = m->afbuf + MIME_AF_PREFIX;
    m->nnamelen = 0;
    m->depth = 0;
    m->partno = 0;
    m->base = 0;
    m->hdrcut = 0;

    /* Every part costs at least a header line, so a message cannot have
     * more parts than it has bytes; the guard is against a walk that
     * fails to move forward, not against a large message. */
    while (guard++ < 100000) {
        int lvl;

        err = mime_headers(m, pos, &m->h);
        if (err != UNC_OK) break;

        /* A multipart: push its boundary and go on to its first part. */
        if (mime_ci_prefix(m->h.ctype, MIME_CTYPE_MAX, "multipart/") &&
            m->h.bndlen > 0 && m->depth < MIME_MAX_DEPTH) {
            int d = m->depth;
            int32_t i;
            for (i = 0; i < m->h.bndlen; i++) m->bnd[d][i] = m->h.bnd[i];
            m->bndlen[d] = m->h.bndlen;
            m->appledouble[d] =
                mime_ci_prefix(m->h.ctype, MIME_CTYPE_MAX,
                               "multipart/appledouble") ? 1 : 0;
            m->mnamelen[d] = m->h.namelen;
            m->mnametrunc[d] = m->h.name_trunc;
            if (m->h.namelen) {
                uint32_t k;
                for (k = 0; k < m->h.namelen; k++) m->mname[d][k] = m->h.name[k];
            }
            m->depth = d + 1;

            err = mime_scan(m, m->h.body, &m->s);      /* skip the preamble */
            if (err != UNC_OK) break;
            if (m->s.level < 0) break;
            m->depth = m->s.level + 1;
            if (m->s.final) m->depth = m->s.level;
            pos = m->s.next;
            continue;
        }

        /* An embedded message: its headers are the next thing in the
         * stream. mpack recurses here; there is nothing to push. */
        if (mime_ci_prefix(m->h.ctype, MIME_CTYPE_MAX, "message/rfc822")) {
            pos = m->h.body;
            continue;
        }

        err = mime_scan(m, m->h.body, &m->s);
        if (err != UNC_OK) break;

        lvl = m->depth - 1;
        {
            MimePart part;
            part.start = m->h.body;
            part.end = m->s.body_end > m->h.body ? m->s.body_end : m->h.body;
            part.cte = m->h.cte;

            if (lvl >= 0 && m->appledouble[lvl] &&
                mime_ci_prefix(m->h.ctype, MIME_CTYPE_MAX,
                               "application/applefile")) {
                m->af = part;                       /* the header part */
                have_af = 1;
                af_level = lvl;
            } else if (have_af && lvl == af_level) {
                err = mime_emit(m, &m->h, &part, &m->af, &any);
                have_af = 0;
                af_level = -1;
                if (err != UNC_OK) break;
            } else if (mime_is_attachment(&m->h)) {
                m->nnamelen = 0;
                err = mime_emit(m, &m->h, &part, NULL, &any);
                if (err != UNC_OK) break;
            } else if (m->h.cte == MIME_CTE_NONE && m->h.namelen == 0 &&
                       mime_is_text(&m->h)) {
                uint32_t at = part.start;
                int nest = mime_body_nested(m, part.start, part.end, &at);
                if (nest == MIME_NEST_UU) {
                    part.cte = MIME_CTE_UU;
                    part.start = at;
                }
                if (nest != MIME_NEST_NONE) {
                    err = mime_emit(m, &m->h, &part, NULL, &any);
                    if (err != UNC_OK) break;
                }
            }
        }

        /* Close what this boundary closed. An appledouble that ends
         * with no data part still describes a file — a resource-only
         * one, which on a Macintosh is most of them. */
        if (m->s.level >= 0) {
            m->depth = m->s.level + 1;
            if (m->s.final) m->depth = m->s.level;
        }
        if (have_af && m->depth <= af_level) {
            err = mime_emit(m, NULL, NULL, &m->af, &any);
            have_af = 0;
            af_level = -1;
            if (err != UNC_OK) break;
        }
        if (m->s.level < 0) break;                  /* end of the message */
        if (m->s.next <= pos) break;                /* no forward progress */
        pos = m->s.next;
    }

    if (have_af && err == UNC_OK)
        err = mime_emit(m, NULL, NULL, &m->af, &any);

    unc_free(c->al, blk);
    if (err == UNC_ERR_TRUNCATED && any) err = UNC_OK;
    if (!any && err == UNC_OK) return UNC_ERR_FORMAT;
    return err;
}

/* ------------------------------------------------------------------ */
/* What fmt_mimeseg.c reads through                                   */
/*                                                                    */
/* A part of a message/partial set is a mail message like any other,  */
/* and its Content-Type parameters are parsed by the same getParam()  */
/* transcription as everything here. Wrappers rather than a second    */
/* copy: two transcriptions of one rule disagree eventually.          */
/* ------------------------------------------------------------------ */

int32_t unc_mime_ci_prefix(const uint8_t *s, int32_t len, const char *pfx)
{
    return mime_ci_prefix(s, len, pfx);
}

uint32_t unc_mime_param(const uint8_t *h, int32_t hlen, const char *key,
                        uint8_t *out, uint32_t cap, int *trunc)
{
    return mime_param(h, hlen, key, out, cap, trunc);
}

/* `cap` is the caller's buffer, which must hold MIME_CTYPE_MAX + 1;
 * the argument is there so a caller declaring less fails to compile
 * rather than at run time. */
void unc_mime_ctype_of(const uint8_t *h, int32_t hlen, uint8_t *out,
                       uint32_t cap)
{
    if (cap < MIME_CTYPE_MAX) { out[0] = 0; return; }
    mime_ctype_of(h, hlen, out);
}

int unc_mime_is_header(const uint8_t *s, int32_t len)
{
    return mime_is_header(s, len);
}

/* ------------------------------------------------------------------ */
/* Probe                                                              */
/* ------------------------------------------------------------------ */

/* A message claims this format only if it carries something to EXTRACT:
 * a multipart with a boundary, or a part encoded in base64 or
 * quoted-printable. Mail headers alone are not enough — a BinHex or
 * uuencoded posting has those too, and both are claimed by their own
 * probes, which unc_sniff runs first.
 *
 * The interesting header can sit well past the 512-byte sniff window
 * (Received: and DKIM lines are long), so this reads on through io. */
/* What the headers scanned so far have shown. */
typedef struct MimeSigns {
    int ctype;                   /* a Content-Type at all      */
    int signal;                  /* something to extract       */
    int bnd;                     /* a multipart WITH a boundary */
} MimeSigns;

/* One unfolded header. Sets the flags; returns nonzero once the file is
 * a MIME message worth opening — which in `strict` mode means a
 * multipart whose parts this walk can enumerate, and otherwise any
 * message carrying something to extract. */
static int mime_probe_header(const uint8_t *h, int32_t hlen, uint8_t *pb,
                             MimeSigns *f, int strict)
{
    int32_t k;

    if ((k = mime_ci_prefix(h, hlen, "content-type:"))) {
        int have_bnd = mime_param(h, hlen, "boundary", pb,
                                  MIME_BND_MAX, NULL) > 0;
        f->ctype = 1;
        /* A boundary, or a part that names a file: either is something
         * to extract. A Content-Type alone is not — every mail message
         * has one. */
        if (have_bnd || mime_param(h, hlen, "name", pb, MIME_BND_MAX, NULL) > 0)
            f->signal = 1;
        if (have_bnd) {
            int32_t j = k;
            while (j < hlen && mime_is_space(h[j])) j++;
            if (mime_ci_prefix(h + j, hlen - j, "multipart/")) f->bnd = 1;
        }
    } else if (mime_ci_prefix(h, hlen, "content-disposition:")) {
        if (mime_param(h, hlen, "filename", pb, MIME_BND_MAX, NULL) > 0)
            f->signal = 1;
    } else if ((k = mime_ci_prefix(h, hlen, "content-transfer-encoding:"))) {
        if (mime_cte_of(h + k, hlen - k) != MIME_CTE_NONE)
            f->signal = 1;
    }
    return strict ? f->bnd : (f->ctype && f->signal);
}

static UncFormat mime_probe(const uint8_t *head, int32_t len, UncIO *io,
                            int strict)
{
    /* Deliberately small: this frame is on the sniff path, which every
     * file that reaches the end of unc_sniff pays for. 512 bytes of
     * lines and 256 of unfolded header are enough to FIND the signal —
     * a boundary, a filename or an encoding — and a line too long for
     * the window is skipped rather than ending the scan. */
    uint8_t buf[512], pb[MIME_BND_MAX + 1];
    uint8_t hb[256];
    int32_t hn = 0;
    uint32_t pos = 0, size;
    int32_t n = 0, i = 0;
    MimeSigns f;

    f.ctype = f.signal = f.bnd = 0;

    if (len < 16 || !io) return UNC_FORMAT_UNKNOWN;

    /* The file has to START like a message: a header line, or the "From "
     * line an mbox begins with. */
    {
        int32_t e = 0;
        while (e < len && head[e] != '\n' && head[e] != '\r') e++;
        if (!mime_is_header(head, e) &&
            !mime_ci_prefix(head, e, "from ")) return UNC_FORMAT_UNKNOWN;
    }

    size = unc_io_size32(io);
    if (size == UNC_SIZE_UNKNOWN) size = MIME_SCAN_MAX;
    if (size > MIME_SCAN_MAX) size = MIME_SCAN_MAX;

    while (pos < size) {
        int32_t want = (int32_t)(size - pos);
        if (want > (int32_t)sizeof buf) want = (int32_t)sizeof buf;
        if (unc_read_at(io, pos, buf, want) != UNC_OK) break;
        n = want;

        /* Whole lines only: stop at the last terminator in the buffer,
         * unless this is the end of the scan. */
        if (pos + (uint32_t)n < size) {
            while (n > 0 && buf[n - 1] != '\n' && buf[n - 1] != '\r') n--;
            if (n == 0) {                       /* a line longer than buf */
                pos += (uint32_t)want;
                hn = 0;
                continue;
            }
        }

        i = 0;
        while (i < n) {
            int32_t s = i, e;
            while (i < n && buf[i] != '\n' && buf[i] != '\r') i++;
            e = i;
            while (i < n && (buf[i] == '\n' || buf[i] == '\r')) i++;

            /* Unfold, exactly as the extractor does: a
             * "Content-Type: application/octet-stream;" whose `name`
             * is on the next line is one header, and reading the two
             * lines separately finds neither the name nor, for a
             * folded Content-Transfer-Encoding, the encoding. The
             * pending header survives across read chunks. */
            if (hn > 0 && e > s && mime_is_space(buf[s])) {
                int32_t k = s;
                while (k < e && hn < (int32_t)sizeof hb - 1) hb[hn++] = buf[k++];
                continue;
            }
            if (hn > 0) {
                if (mime_probe_header(hb, hn, pb, &f, strict))
                    return UNC_FORMAT_MIME;
                hn = 0;
            }
            if (e == s) continue;               /* the end of the headers */
            {
                int32_t k = s;
                while (k < e && hn < (int32_t)sizeof hb - 1) hb[hn++] = buf[k++];
            }
        }
        pos += (uint32_t)n;
    }
    if (hn > 0 && mime_probe_header(hb, hn, pb, &f, strict))
        return UNC_FORMAT_MIME;

    return UNC_FORMAT_UNKNOWN;
}

UncFormat unc_mime_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    return mime_probe(head, len, io, 0);
}

/* The strict half, which unc_sniff runs BEFORE uuencode, btoa and
 * BinHex: a message that declares a multipart with a boundary has parts
 * this walk can enumerate, and one of them being a document those three
 * scans recognise is no reason to hand them the whole message and drop
 * the others (DECISIONS.md 2026-08-29). */
UncFormat unc_mime_probe_multipart(const uint8_t *head, int32_t len,
                                   UncIO *io)
{
    return mime_probe(head, len, io, 1);
}

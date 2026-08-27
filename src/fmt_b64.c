/*
 * fmt_b64.c — base64 (RFC 2045 §6.8), in the two shapes a file arrives
 * in when it is not inside a MIME message (those are fmt_mime.c).
 *
 * Sources (transcribed, never guessed):
 *   reference/deark/modules/xfer.c — do_base64_internal(): the
 *       alphabet, '=' ending the data, whitespace and anything else
 *       skipped, and a part-decoded group yielding the bytes it
 *       implies. uuencode_read_header(): the "begin-base64 " line,
 *       compared as thirteen characters at the start of a line.
 *   reference/mpack/decode.c — from64(), which decodes the same way
 *       character by character. The two agree except at a stream that
 *       stops mid-group: deark writes the implied bytes, mpack drops
 *       them with a warning. deark's reading is followed here
 *       (DECISIONS.md 2026-08-26).
 *
 * Two shapes:
 *
 *   begin-base64 <mode> <name>     what sharutils' `base64` and
 *   <data lines>                   `uuencode -m` write, and the shape
 *   ====                           that carries a NAME. Several
 *                                  documents in one file are read, as
 *                                  uuencode and BinHex are.
 *
 *   <data lines>                   a bare body, the whole file. It has
 *                                  no name — the host's filename is
 *                                  the only one there is, which is the
 *                                  rule gzip, .Z and AppleDouble
 *                                  sidecars already follow here.
 *
 * The payload is almost always another archive (a MacBinary file, a
 * .sit), so the CLI's envelope unwrapping takes the next layer off.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define B64_LINE_MAX   1000       /* a mailer wraps at 76; this is slack */
#define B64_IOBUF      4096
#define B64_SCAN_MAX   8192u      /* how far in a "begin-base64" may sit */

/* The alphabet, in the range form deark uses (b-65, b-71, b+4, 62, 63).
 * Source: reference/deark/modules/xfer.c do_base64_internal. */
static int b64_val(int c)
{
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

void unc_b64_reset(UncB64 *b)
{
    b->n = 0;
    b->done = 0;
}

int unc_b64_flush(UncB64 *b, uint8_t out[3])
{
    int n = b->n;
    b->n = 0;
    if (n < 2) return 0;                    /* one character implies none */
    out[0] = (uint8_t)((b->q[0] << 2) | (b->q[1] >> 4));
    if (n < 3) return 1;
    out[1] = (uint8_t)((b->q[1] << 4) | (b->q[2] >> 2));
    return 2;
}

int unc_b64_feed(UncB64 *b, int ch, uint8_t out[3])
{
    int v;

    if (b->done) return 0;
    if (ch == '=') {                        /* padding: the data ends here */
        b->done = 1;
        return unc_b64_flush(b, out);
    }
    v = b64_val(ch);
    if (v < 0) return 0;                    /* newline, space, mail garbage */
    b->q[b->n++] = (uint8_t)v;
    if (b->n < 4) return 0;
    b->n = 0;
    out[0] = (uint8_t)((b->q[0] << 2) | (b->q[1] >> 4));
    out[1] = (uint8_t)((b->q[1] << 4) | (b->q[2] >> 2));
    out[2] = (uint8_t)((b->q[2] << 6) |  b->q[3]);
    return 3;
}

/* ------------------------------------------------------------------ */
/* Probe                                                              */
/* ------------------------------------------------------------------ */

static int b64_is_begin(const uint8_t *p, int32_t len)
{
    static const char tag[] = "begin-base64 ";
    int32_t i;
    if (len < 16) return 0;                 /* deark's bound: the tag,
                                             * a mode and a name */
    for (i = 0; tag[i]; i++) if (p[i] != (uint8_t)tag[i]) return 0;
    return 1;
}

/* Is this line nothing but base64? */
static int b64_line_ok(const uint8_t *p, int32_t len)
{
    int32_t i, np = 0;

    if (len < 4) return 0;
    for (i = 0; i < len; i++) {
        if (p[i] == '=') { np++; continue; }
        if (np) return 0;                   /* padding is only ever last */
        if (b64_val(p[i]) < 0) return 0;
    }
    if (np > 2) return 0;
    return (len % 4) == 0;
}

/* A bare base64 body has no marker of any kind, so the whole shape of
 * the file has to carry the claim: several full lines of one length,
 * every character in the alphabet, and a last line that closes the
 * stream properly. That is why this probe also reads the TAIL — a file
 * whose head is base64-shaped and whose end is not is something else
 * with a base64 attachment in it, and that is fmt_mime.c's business.
 *
 * The probe is the last one unc_sniff runs, so nothing with a magic
 * number, a banner or a header can be taken from it by this. */
#define B64_MIN_LINES  4
#define B64_MIN_WIDTH  40
#define B64_MAX_WIDTH  76

static int b64_bare_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    int32_t i = 0, width = -1, lines = 0;
    uint8_t tail[512];
    uint32_t size;
    int32_t got, ls, le, lastlen;

    while (i < len && lines < B64_MIN_LINES) {
        int32_t s = i, e;
        while (i < len && head[i] != '\n' && head[i] != '\r') i++;
        e = i;
        while (i < len && (head[i] == '\n' || head[i] == '\r')) i++;
        if (e == s) return 0;               /* a blank line: not a body */
        if (i >= len && e - s < width) break;   /* cut by the window */
        if (!b64_line_ok(head + s, e - s)) return 0;
        if (width < 0) {
            width = e - s;
            if (width < B64_MIN_WIDTH || width > B64_MAX_WIDTH) return 0;
        } else if (e - s != width) {
            return 0;                       /* only the LAST line is short */
        }
        lines++;
    }
    if (lines < B64_MIN_LINES) return 0;

    /* The tail. A stream that ends mid-group, or on a line that is not
     * base64 at all, is not a bare base64 file. */
    if (!io) return 0;
    size = io->size(io->ctx);
    if (size == UNC_SIZE_UNKNOWN || size == 0) return 0;
    got = (int32_t)(size < sizeof tail ? size : sizeof tail);
    if (unc_read_at(io, size - (uint32_t)got, tail, got) != UNC_OK) return 0;

    /* Walk to the last non-empty line of the buffer. */
    ls = le = -1;
    for (i = 0; i < got; ) {
        int32_t s = i, e;
        while (i < got && tail[i] != '\n' && tail[i] != '\r') i++;
        e = i;
        while (i < got && (tail[i] == '\n' || tail[i] == '\r')) i++;
        if (e > s) { ls = s; le = e; }
    }
    if (ls < 0) return 0;
    lastlen = le - ls;
    if (lastlen > width) return 0;
    if (!b64_line_ok(tail + ls, lastlen)) return 0;
    return 1;
}

UncFormat unc_b64_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    int32_t i = 0;

    /* The named shape: a "begin-base64 " line, and behind it a line
     * that really is base64 — the same two-step BinHex and uuencode
     * use, because a marker alone occurs in prose. */
    while (i < len) {
        int32_t s = i, e;
        while (i < len && head[i] != '\n' && head[i] != '\r') i++;
        e = i;
        while (i < len && (head[i] == '\n' || head[i] == '\r')) i++;
        if (b64_is_begin(head + s, e - s)) {
            while (i < len) {
                int32_t ns = i, ne;
                while (i < len && head[i] != '\n' && head[i] != '\r') i++;
                ne = i;
                while (i < len && (head[i] == '\n' || head[i] == '\r')) i++;
                if (ne == ns) continue;
                return (b64_line_ok(head + ns, ne - ns))
           ? UNC_FORMAT_BASE64 : UNC_FORMAT_UNKNOWN;
            }
            return UNC_FORMAT_UNKNOWN;
        }
    }

    return (b64_bare_probe(head, len, io))
           ? UNC_FORMAT_BASE64 : UNC_FORMAT_UNKNOWN;
}

/* ------------------------------------------------------------------ */
/* Decode                                                             */
/* ------------------------------------------------------------------ */

/* Decode from `start` to the end of the document. Counts always, writes
 * when `write`. `*endpos` is where the document stopped: at the '=' of
 * a "====" line, or at EOF. */
static int b64_run(UncCtx *c, uint32_t start, int write,
                   uint8_t *iobuf, uint32_t *bytes, uint32_t *endpos)
{
    UncBufIn in;
    UncB64 st;
    uint8_t out[3];
    int err = UNC_OK;

    *bytes = 0;
    if (c->io->seek(c->io->ctx, start) < 0) return UNC_ERR_IO;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, B64_IOBUF);
    unc_b64_reset(&st);

    for (;;) {
        int ch = unc_bufin_next(&in);
        int n;
        if (ch < 0) {
            if (in.err != UNC_ERR_TRUNCATED) err = in.err;
            n = unc_b64_flush(&st, out);
            if (n > 0) {
                *bytes += (uint32_t)n;
                if (write && c->sink->write(c->sink->ctx, UNC_FORK_DATA,
                                            out, n) != 0)
                    err = UNC_ERR_SINK;
            }
            break;
        }
        n = unc_b64_feed(&st, ch, out);
        if (n > 0) {
            *bytes += (uint32_t)n;
            if (write && c->sink->write(c->sink->ctx, UNC_FORK_DATA,
                                        out, n) != 0) {
                err = UNC_ERR_SINK;
                break;
            }
        }
        if (st.done) break;
    }

    *endpos = start + unc_bufin_tell(&in);
    return err;
}

/* The name out of a "begin-base64 <mode> <name>" line: the mode, then
 * the rest of the line, which is where fmt_uu.c takes a bare uuencode
 * name from as well. */
static void b64_name_from_begin(const uint8_t *line, int32_t len,
                                const uint8_t **name, uint32_t *nlen)
{
    int32_t s = 13, e = len;                /* past "begin-base64 " */

    while (s < len && line[s] == ' ') s++;
    while (s < len && line[s] != ' ') s++;  /* the mode */
    while (s < len && line[s] == ' ') s++;
    while (e > s && (line[e - 1] == ' ' || line[e - 1] == '\t')) e--;
    if (e < s) e = s;
    *name = line + s;
    *nlen = (uint32_t)(e - s);
}

int unc_b64_extract(UncCtx *c)
{
    uint8_t *buf;
    uint8_t *iobuf, *line;
    UncBufIn scan;
    int err = UNC_OK, any = 0;
    uint32_t pos = 0;

    buf = (uint8_t *)unc_alloc(c->al, B64_IOBUF + B64_LINE_MAX + 1);
    if (!buf) return UNC_ERR_MEM;
    iobuf = buf;
    line  = buf + B64_IOBUF;

    for (;;) {
        UncEntryInfo e;
        uint32_t start = 0, end = 0, bytes = 0;
        const uint8_t *nm = NULL;
        uint32_t nlen = 0;
        int found = 0, eof = 0, sret, est = UNC_OK;
        int32_t llen = 0;

        /* Look for a "begin-base64" line. Without one the whole file is
         * the body — but only from the very beginning, so a second pass
         * cannot claim the tail of a document it has already read. */
        if (c->io->seek(c->io->ctx, pos) < 0) { err = UNC_ERR_IO; break; }
        unc_bufin_init(&scan, c->io, &c->ps, iobuf, B64_IOBUF);
        for (;;) {
            uint32_t before = unc_bufin_tell(&scan);
            if (unc_readline(&scan, line, B64_LINE_MAX + 1, &llen, &eof)
                != UNC_OK) break;
            if (b64_is_begin(line, llen)) {
                found = 1;
                start = pos + unc_bufin_tell(&scan);
                break;
            }
            if (eof) break;
            if (before > B64_SCAN_MAX) break;
        }

        if (!found) {
            if (any || pos != 0) break;      /* nothing more in the file */
            start = 0;                       /* the bare shape */
        } else {
            b64_name_from_begin(line, llen, &nm, &nlen);
        }

        err = b64_run(c, start, 0, iobuf, &bytes, &end);
        if (err != UNC_OK && err != UNC_ERR_TRUNCATED) break;
        err = UNC_OK;
        if (bytes == 0 && !found) { err = UNC_ERR_FORMAT; break; }

        unc_entry_clear(&e);
        if (nlen)
            unc_entry_set_name(&e, nm, nlen);
        else if (c->opt.name_hint && c->opt.name_hint_len)
            unc_entry_set_name(&e, c->opt.name_hint, c->opt.name_hint_len);
        e.data_size = bytes;
        e.comp_data_size = end - start;

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; break; }
        if (sret == 0) {
            uint32_t n, stop;
            if (!c->opt.list_only)
                est = b64_run(c, start, !c->opt.test_only, iobuf, &n, &stop);
            if (est == UNC_ERR_TRUNCATED) est = UNC_OK;
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
        }
        any = 1;
        if (!found) break;                   /* the bare shape is one file */
        if (end <= start) break;             /* no forward progress */
        pos = end;
    }

    unc_free(c->al, buf);
    if (!any && err == UNC_OK) return UNC_ERR_FORMAT;
    return err;
}

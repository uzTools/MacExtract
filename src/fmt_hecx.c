/*
 * fmt_hecx.c — the two BinHex encodings before 4.0, `.hex` and `.hcx`, and
 * SUMacC's `.dl` before them.
 *
 * The BinHex ones are line-oriented text with no file name in them:
 *
 *   (This file must be converted with BinHex.Hex)    optional banner
 *   #TYPECREA$FFFF                                   type, creator, flags
 *   ***COMPRESSED                                    .hcx only
 *   ***RESOURCE FORK                                 either fork, any order
 *   <lines>
 *   ***END OF DATA
 *   ***DATA FORK
 *   <lines>
 *   ***END OF DATA
 *   ***CHECKSUM:hh            .hex: an 8-bit sum of every byte of both forks
 *   ***CRC:hhhh               .hcx: a 16-bit add-and-rotate over the same
 *
 * A `.hex` line is pairs of upper-case hex digits. A `.hcx` line is six bits
 * a character, value = (ch - 0x20) & 0x3F, decoded four characters to three
 * bytes; the first decoded byte is the count of bytes the line holds, and a
 * line shorter than its count implies was cut by a mailer stripping
 * trailing spaces, which are value 0 and are put back.
 *
 * Source: reference/macutils/hexbin/hecx.c (do_o_forks, make_file,
 * comp_to_bin, hex_to_bin, hexit, comp_c_crc, comp_e_crc) and crc.c
 * (verify_crc), the only implementation there is. Its author did not know
 * which BinHex wrote which ("Is it BinHex 2.0?", macutils/README), and the
 * version numbers disagree between sources (reference/notes/BinHex.md has
 * .hcx as 2.0). Measured instead: BinHex 2.0 itself (Yves Lempereur, 1984)
 * writes BOTH, `.hcx` with File ▸ Compressed checked and `.hex` without,
 * and every marker above is a string in its code (tools/vmac/binhex2.py).
 *
 * The CRC adds each byte UNSIGNED. hecx.c passes a plain `char` and so
 * leaves the sign to the compiler; BinHex 2.0's own output and the three
 * 1985 files this was graded on all hold bytes above 0x7F, and every one
 * of their CRCs agrees with the unsigned sum and none with the signed one
 * (DECISIONS.md 2026-10-14, *the BinHex before 4.0*).
 *
 * Two departures from hecx.c, each a file it refuses and this reads or the
 * reverse:
 *  - The banner is NOT required. hexbin will not look for a '#' line until
 *    it has seen "(This file", so it cannot read two of the three `.hcx`
 *    files in the 1985 mactosh archive, which have none; their CRCs verify.
 *  - A `.hcx` line cut to ONE character is restored from its second, which
 *    holds half the count: hexbin reads the count before it puts the
 *    spaces back, takes the NUL after that character as data, and gets a
 *    count 2 too high — so a mailer stripping trailing spaces from a line
 *    of zeros costs it the file (tools/run_hecx.py, "trailing spaces").
 *  - A line of 1,023 characters or more is refused as corrupt; hexbin
 *    carries the rest over as a line of its own. No writer here produces
 *    one (64 characters for `.hex`, 44 for `.hcx`).
 *
 * The fork sizes are not in the header, so the document is read twice:
 * once to count, and once to write — the shape fmt_uu.c already has.
 *
 * `.dl` is older and smaller: a resource fork alone, no name, type or
 * creator, four bits a character — '@'..'O' are 0..15, high nibble first,
 * and every other character is skipped — ended by '|' and eight more
 * characters whose low four bits are a sum, high nibble first: the byte
 * count plus every byte. Its first line is the first one longer than 40,
 * of even length, made of nothing but '@'..'O' and '|'; and here, not in
 * hexbin, one that opens "@@". That is the high byte of the first long of
 * a resource fork, the offset of its data, which is under 16 MB in any
 * fork (Inside Macintosh: More Macintosh Toolbox, "Resource File Format",
 * as unc_crypt.c reads it); without it base64 of a run of zeros, a line of
 * 'A', is a `.dl` (DECISIONS.md 2026-10-24, *the format before BinHex*).
 * Source: reference/macutils/hexbin/dl.c (dl, dl_fork) and hexbin.c
 * (find_header); macutils/README has the format as SUMacC's, the first
 * hexified one, and dl.c as based on its original distribution. The type
 * and creator are dl.c's, APPL and ????. The sum is compared on its low 16
 * bits, as dl.c's verify_crc does, though eight characters hold 32: the
 * one file found (mactosh/lang/xlispold.dl) agrees on all 32, and a sum of
 * bytes mod 65,536 already catches any change of fewer than 257 bytes
 * (DECISIONS.md 2026-10-24, *the format before BinHex*). It goes through
 * the same driver below: one document, counted, then written.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"
#include "fmt_binhex_priv.h"

#define HX_LINE 1024

typedef struct HxDoc {
    uint32_t type, creator;
    uint16_t flags;
    uint32_t start;          /* just after the '#' line */
    uint32_t size[2];        /* data, rsrc */
} HxDoc;

/* 'line' starts with "***" and then `tag`, compared byte by byte: a string
 * constant would be A5 world, resident for the life of the application
 * (the same reason fmt_binhex.c spells out "--- end of part"). */
static int hx_is(const uint8_t *l, int32_t n, const char *tag, int32_t tn)
{
    int32_t i;
    if (n < 3 + tn || l[0] != '*' || l[1] != '*' || l[2] != '*') return 0;
    for (i = 0; i < tn; i++) if (l[3 + i] != (uint8_t)tag[i]) return 0;
    return 1;
}

static int hx_hexit(int ch)
{
    if (ch >= '0' && ch <= '9') return ch - '0';
    if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
    return -1;                     /* hexit() takes upper case only */
}

/* A value after a marker, as sscanf("%lx") reads it: leading blanks, then
 * hex digits of either case. -1 if there are none. */
static int32_t hx_value(const uint8_t *p, int32_t n)
{
    int32_t i = 0, any = 0;
    uint32_t v = 0;
    while (i < n && (p[i] == ' ' || p[i] == '\t')) i++;
    for (; i < n; i++) {
        int d = p[i];
        if (d >= 'a' && d <= 'f') d -= 'a' - 'A';
        d = hx_hexit(d);
        if (d < 0) break;
        v = (v << 4) | (uint32_t)d;
        any = 1;
    }
    return any ? (int32_t)(v & 0xFFFFu) : -1;
}

/* One body line decoded in place; returns its byte count, or -1. */
static int32_t hx_decode(uint8_t *l, int32_t n, int compressed)
{
    int32_t i, k, cnt, need;
    if (!compressed) {
        cnt = n >> 1;              /* an odd last character is dropped */
        for (i = 0; i < cnt; i++) {
            int hi = hx_hexit(l[2 * i]), lo = hx_hexit(l[2 * i + 1]);
            if (hi < 0 || lo < 0) return -1;
            l[i] = (uint8_t)((hi << 4) | lo);
        }
        return cnt;
    }
#define SIXB(ch) ((uint32_t)((ch) - 0x20) & 0x3Fu)
    if (n < 1) return -1;
    if (n < 2) l[1] = ' ';         /* the count's own second character */
    cnt = (int32_t)((SIXB(l[0]) << 2) | (SIXB(l[1]) >> 4));
    need = (cnt / 3 + 1) * 4;
    for (i = n; i < need; i++) l[i] = ' ';        /* restore lost spaces */
    /* Four characters to three bytes, written behind where they are read;
     * the first byte is the count itself and is dropped below. */
    for (i = 0, k = 0; k <= cnt; i += 4, k += 3) {
        uint32_t a = SIXB(l[i]), b = SIXB(l[i + 1]);
        uint32_t c = SIXB(l[i + 2]), d = SIXB(l[i + 3]);
        l[k]     = (uint8_t)((a << 2) | (b >> 4));
        l[k + 1] = (uint8_t)((b << 4) | (c >> 2));
        l[k + 2] = (uint8_t)((c << 6) | d);
    }
#undef SIXB
    for (i = 0; i < cnt; i++) l[i] = l[i + 1];
    return cnt;
}

/* The next non-empty line: its length, or an error. A line that cannot
 * be followed by another is UNC_ERR_TRUNCATED unless the caller says the
 * document may end there, which only its last line may. */
static int32_t hx_line(UncBufIn *in, uint8_t *line, int *eof)
{
    int32_t n;
    for (;;) {
        if (*eof) return UNC_ERR_TRUNCATED;
        if (unc_readline(in, line, HX_LINE, &n, eof) != UNC_OK)
            return in->err == UNC_ERR_TRUNCATED ? UNC_ERR_TRUNCATED : in->err;
        if (n >= HX_LINE - 1) return UNC_ERR_CORRUPT;
        if (n > 0) return n;
    }
}

/* Walk the document from just after its '#' line: count each fork, check
 * the sum, and when `write` is set hand the bytes to the sink. */
static int hx_walk(UncCtx *c, UncBufIn *in, uint8_t *line, uint8_t *obuf,
                   uint32_t ocap, HxDoc *doc, int write)
{
    int compressed = 0, seen = 0, eof = 0;
    uint32_t sum = 0;
    int32_t n, want;

    for (;;) {
        UncFork fork;
        uint32_t got = 0, have = 0;

        n = hx_line(in, line, &eof);
        if (n < 0) return (int)n;
        if (seen == 0 && hx_is(line, n, "COMPRESSED", 10)) {
            compressed = 1;
            continue;
        }
        if (hx_is(line, n, "DATA", 4)) {
            fork = UNC_FORK_DATA;
        } else if (hx_is(line, n, "RESOURCE", 8)) {
            fork = UNC_FORK_RSRC;
        } else if (compressed ? hx_is(line, n, "CRC:", 4)
                              : hx_is(line, n, "CHECKSUM:", 9)) {
            int32_t at = compressed ? 7 : 12;
            want = hx_value(line + at, n - at);
            if (want < 0) return UNC_ERR_CORRUPT;
            if (!compressed) { want &= 0xFF; sum &= 0xFFu; }
            return (uint32_t)want == sum ? UNC_OK : UNC_ERR_CRC;
        } else {
            continue;                       /* hecx.c ignores the rest */
        }
        /* The same fork twice: hecx.c appends the second to the first and
         * its sum then fails. Refused here before anything is written. */
        if (seen & (1 << fork)) return UNC_ERR_CORRUPT;
        seen |= 1 << fork;

        for (;;) {
            int32_t k, cnt;
            n = hx_line(in, line, &eof);
            if (n < 0) return (int)n;
            if (hx_is(line, n, "END", 3)) break;
            cnt = hx_decode(line, n, compressed);
            if (cnt < 0) return UNC_ERR_CORRUPT;
            for (k = 0; k < cnt; k++) {
                if (compressed) {
                    sum = (sum + line[k]) & 0xFFFFu;
                    sum = ((sum << 3) & 0xFFFFu) | (sum >> 13);
                } else {
                    sum += line[k];
                }
                /* Gathered, not handed over a line at a time: a .hcx line
                 * is 33 bytes, and the Mac sink is an FSWrite per call.
                 * By hand rather than through UncForkOut, which does the
                 * same and costs this overlay 54 B more: its two calls go
                 * through the host vector (measured 2026-10-14). */
                if (write) {
                    obuf[have++] = line[k];
                    if (have == ocap) {
                        if (c->sink->write(c->sink->ctx, fork, obuf,
                                           (int32_t)have) < 0)
                            return UNC_ERR_SINK;
                        have = 0;
                    }
                }
            }
            got += (uint32_t)cnt;
        }
        if (have > 0 &&
            c->sink->write(c->sink->ctx, fork, obuf, (int32_t)have) < 0)
            return UNC_ERR_SINK;
        doc->size[fork == UNC_FORK_RSRC] = got;
    }
}

/* `.dl` from its first line: count the fork and check the sum, and when
 * `write` is set hand the bytes to the sink. hexbin reads line by line and
 * so never sees a line end; here they are skipped like any other character
 * in the body, and in the sum, where a mailer may have broken the line.
 * The seven-bit mask is dl.c's (nchar). */
static int dl_walk(UncCtx *c, UncBufIn *in, uint8_t *obuf, uint32_t ocap,
                   HxDoc *doc, int write)
{
    uint32_t v = 0, n = 0, sum = 0, want = 0, have = 0;
    int ch, k = -1;

    while (k < 8) {
        ch = unc_bufin_next(in);
        if (ch < 0) return in->err;
        ch &= 0x7F;
        if (k >= 0) {
            if (ch == '\r' || ch == '\n' || ch == 0) continue;
            want = (want << 4) | (uint32_t)(ch & 0xF);
            k++;
            continue;
        }
        if (ch == '|') { k = 0; continue; }
        if (ch < '@' || ch > 'O') continue;
        v = (v << 4) | (uint32_t)(ch & 0xF);
        if (++n & 1) continue;
        sum += v;
        if (write) {
            obuf[have++] = (uint8_t)v;
            if (have == ocap) {
                if (c->sink->write(c->sink->ctx, UNC_FORK_RSRC, obuf,
                                   (int32_t)have) < 0)
                    return UNC_ERR_SINK;
                have = 0;
            }
        }
        v = 0;
    }
    if (have > 0 &&
        c->sink->write(c->sink->ctx, UNC_FORK_RSRC, obuf, (int32_t)have) < 0)
        return UNC_ERR_SINK;
    doc->size[1] = n >> 1;
    return ((want ^ (doc->size[1] + sum)) & 0xFFFFu) ? UNC_ERR_CRC : UNC_OK;
}

/* hexbin.c's find_header test for a `.dl` document's first line: 1 if
 * the line passes it. A line of 1,023 or more is cut there and here, and
 * is odd once cut. The "@@" it does not ask for is the caller's. */
static int dl_is_start(const uint8_t *l, int32_t n)
{
    int32_t i;
    if (n <= 40 || (n & 1)) return 0;
    for (i = 0; i < n; i++)
        if ((l[i] < '@' || l[i] > 'O') && l[i] != '|') return 0;
    return 1;
}

int unc_hecx_extract(UncCtx *c)
{
    UncBufIn in;
    UncEntryInfo e;
    HxDoc doc;
    uint8_t *iobuf, *line, *obuf;
    uint32_t base = c->ps.done;
    uint32_t at;
    int32_t n;
    int eof = 0, err, sret, pass;
    int dl = c->fmt == UNC_FORMAT_DL;

    iobuf = (uint8_t *)unc_alloc(c->al, UNC_IOBUF + HX_LINE + UNC_IOBUF);
    if (!iobuf) return UNC_ERR_MEM;
    line = iobuf + UNC_IOBUF;
    obuf = line + HX_LINE;

    unc_bufin_init(&in, c->io, &c->ps, iobuf, UNC_IOBUF);
    for (;;) {
        at = unc_bufin_tell(&in);
        if (unc_readline(&in, line, HX_LINE, &n, &eof) != UNC_OK || eof) {
            err = (in.err == UNC_ERR_IO || in.err == UNC_ERR_ABORTED)
                  ? in.err : UNC_ERR_FORMAT;
            goto out;
        }
        if (dl ? dl_is_start(line, n) : unc_hecx_is_header(line, n)) break;
    }
    /* The first line hexbin would decode from, and it must open "@@". */
    if (dl && (line[0] != '@' || line[1] != '@')) {
        err = UNC_ERR_FORMAT;
        goto out;
    }
    doc.size[0] = doc.size[1] = 0;
    if (dl) {
        doc.type = 0x4150504CUL;        /* 'APPL' and '????', dl.c's */
        doc.creator = 0x3F3F3F3FUL;
        doc.flags = 0;
        doc.start = at;                 /* the first line is data */
    } else {
        doc.type = doc.creator = 0;
        if (n >= 10) doc.type = unc_get_u32be(line + 1);
        if (n >= 14) doc.creator = unc_get_u32be(line + 5);
        doc.flags = (uint16_t)hx_value(line + n - 4, 4);
        doc.start = unc_bufin_tell(&in);
    }

    /* Counting pass, then the writing one. The first one's status is the
     * entry's when nothing is written. */
    for (pass = 0; pass < 2; pass++) {
        if (pass) {
            if (err == UNC_ERR_SINK || err == UNC_ERR_IO ||
                err == UNC_ERR_ABORTED)
                goto out;
            unc_entry_clear(&e);
            if (c->opt.name_hint && c->opt.name_hint_len)
                unc_entry_set_name(&e, c->opt.name_hint, c->opt.name_hint_len);
            e.type = doc.type;
            e.creator = doc.creator;
            e.finder_flags = doc.flags;
            e.data_size = doc.size[0];
            e.rsrc_size = doc.size[1];

            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; goto out; }
            if (sret > 0) { err = UNC_OK; goto out; }
            if (c->opt.list_only || c->opt.test_only) break;
        }
        c->ps.done = base + doc.start;
        if (c->io->seek(c->io->ctx, doc.start) < 0) {
            err = UNC_ERR_IO;
            if (pass) break;
            goto out;
        }
        unc_bufin_init(&in, c->io, &c->ps, iobuf, UNC_IOBUF);
        err = dl ? dl_walk(c, &in, obuf, UNC_IOBUF, &doc, pass)
                 : hx_walk(c, &in, line, obuf, UNC_IOBUF, &doc, pass);
    }
    if (c->sink->end_entry(c->sink->ctx, err) < 0) { err = UNC_ERR_SINK; goto out; }
    if (err != UNC_ERR_SINK && err != UNC_ERR_ABORTED && err != UNC_ERR_IO)
        err = UNC_OK;
out:
    unc_free(c->al, iobuf);
    return err;
}

/*
 * fmt_btoa.c — btoa/atob, the other ASCII armour a Mac met.
 *
 * Paul Rutter's btoa is uuencode's rival from the Unix side: four bytes
 * become five printable characters in base 85, which is 25% overhead
 * against uuencode's 33%. StuffIt Deluxe shipped a `btoa/atob
 * Translator` beside its BinHex and UUCode ones, so a Mac user met
 * these the same way and by the same route (FORMATS.md, *btoa*).
 *
 * Source: the FORMAT as described by reference/btoa/btoa.1 and read out
 * of reference/btoa/atob.c, btoa.h and chksum.h (btoa 5.2.1, Paul
 * Rutter, Joe Orost & Stefan Parmark, 1996), fetched by
 * tools/fetch_references.sh. There is no other implementation and no
 * spec beyond those.
 *
 * NOT a transcription, and that is a licence matter rather than a
 * stylistic one: btoa's README allows use "as long as ... you don't use
 * it to earn money", which is why Debian shipped it in non-free and why
 * its code cannot be carried into an LGPL engine. What is taken here is
 * what a format IS — the two headers, the alphabet, the escapes, the
 * checksum recurrences, the padding rule — and every one of those is
 * cited below to the routine it was read from. No function, buffer or
 * control structure of atob.c survives into this file. NOTICE, and
 * DECISIONS.md 2026-08-23 (btoa's licence).
 *
 * Layout:
 *
 *   xbtoa Begin                         version 4, no per-line check
 *   xbtoa5 <perline> <name> Begin       version 5
 *   <body lines>
 *   xbtoa End N <len> <lenhex> E <eor> S <sum> R <rot>
 *
 * A body character is a base-85 digit offset by '!'; `z` stands for
 * four zero bytes, and in version 5 `y` stands for four spaces. Version
 * 5 lines carry ONE extra character at the end: the running sum modulo
 * 85, encoded the same way — so the data on a line is everything but
 * its last character.
 *
 * Three checksums cover the whole stream and are compared against the
 * End line: eor (xor), sum (+= ch + 1) and rot (rotate left one, then
 * += ch). What they are computed over differs between versions, and
 * that difference is the format's one real trap: version 5 checksums
 * the ENCODED characters as they are read, version 4 the DECODED bytes
 * as they are produced (atob.c, decode_line: `if (new_version)
 * calcchecksum(ch)` before decoding, and four calls after it if not).
 *
 * The declared length is what ends the file: the encoder always writes
 * whole five-character groups, so the last group holds up to three
 * bytes of padding, and `(len - 1) & 3` says how many of its four bytes
 * are real.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define BTOA_LINE_MAX 256      /* btoa.h caps a line at 78 + slack     */

int unc_btoa_probe(const uint8_t *head, int32_t len)
{
    /* "xbtoa Begin" or "xbtoa5 ", at the start of some line within the
     * bytes we were handed — a btoa file may arrive with mail headers
     * in front of it, exactly as a BinHex or uuencoded one does. */
    int32_t i = 0;
    while (i < len) {
        int32_t j = i;
        while (j < len && head[j] != '\n' && head[j] != '\r') j++;
        if (j - i >= 11 &&
            head[i] == 'x' && head[i + 1] == 'b' && head[i + 2] == 't' &&
            head[i + 3] == 'o' && head[i + 4] == 'a') {
            if (head[i + 5] == ' ' &&
                head[i + 6] == 'B' && head[i + 7] == 'e' &&
                head[i + 8] == 'g' && head[i + 9] == 'i' &&
                head[i + 10] == 'n')
                return 1;
            if (head[i + 5] == '5' && head[i + 6] == ' ') return 1;
        }
        while (j < len && (head[j] == '\n' || head[j] == '\r')) j++;
        if (j == i) break;
        i = j;
    }
    return 0;
}

/* ------------------------------------------------------------------ */

typedef struct BtoaState {
    UncCtx  *c;
    UncForkOut out;
    uint32_t want;           /* declared length, or UNC_SIZE_UNKNOWN   */
    /* the three whole-stream checksums (atob.c chksum.h) */
    uint32_t eor, sum, rot;
    /* the 4-to-5 group in progress */
    uint32_t code;
    int      count;
    uint8_t  group[4];
    int      have;           /* group holds a decoded quad             */
    int      err;
} BtoaState;

/* One decoded byte, dropped once the declared length is reached: the
 * final quad carries up to three bytes the file does not have. */
static int btoa_put(BtoaState *s, uint8_t b)
{
    if (s->want != UNC_SIZE_UNKNOWN && unc_fork_pos(&s->out) >= s->want)
        return UNC_OK;
    return unc_fork_put(&s->out, b);
}

/* chksum.h, verbatim: xor, sum of (ch + 1), and a rotate-left-1 that
 * carries its top bit back in before adding. */
static void btoa_chk(BtoaState *s, uint8_t ch)
{
    s->eor ^= ch;
    s->sum += (uint32_t)ch + 1u;
    if (s->rot & 0x80000000u) s->rot = (s->rot << 1) + 1u;
    else                      s->rot <<= 1;
    s->rot += ch;
}

/* Emit the quad the group register holds. */
static int btoa_emit_group(BtoaState *s, int newver)
{
    int i, err;
    s->group[3] = (uint8_t)(s->code & 0xFF);
    s->group[2] = (uint8_t)((s->code >> 8) & 0xFF);
    s->group[1] = (uint8_t)((s->code >> 16) & 0xFF);
    s->group[0] = (uint8_t)((s->code >> 24) & 0xFF);
    if (!newver)
        for (i = 0; i < 4; i++) btoa_chk(s, s->group[i]);
    /* Held back, not written: the last group of a file whose length is
     * not a multiple of four carries padding, and how much is only
     * known from the End line. */
    s->have = 1;
    err = UNC_OK;
    return err;
}

static int btoa_release_group(BtoaState *s, int n)
{
    int i;
    if (!s->have) return UNC_OK;
    for (i = 0; i < n; i++)
        if (btoa_put(s, s->group[i]) != UNC_OK) return UNC_ERR_SINK;
    s->have = 0;
    return UNC_OK;
}

/* One body line, without its terminator. `datalen` excludes the
 * version-5 per-line checksum character. */
static int btoa_line(BtoaState *s, const uint8_t *line, int32_t datalen,
                     int newver)
{
    int32_t i;
    for (i = 0; i < datalen; i++) {
        uint8_t ch = line[i];
        if (newver) btoa_chk(s, ch);
        if (ch >= '!' && ch < (uint8_t)('!' + 85)) {
            if (s->count == 0) {
                if (btoa_release_group(s, 4) != UNC_OK) return UNC_ERR_SINK;
                s->code = (uint32_t)(ch - '!');
            } else {
                s->code = s->code * 85u + (uint32_t)(ch - '!');
            }
            if (++s->count == 5) {
                if (btoa_emit_group(s, newver) != UNC_OK) return UNC_ERR_SINK;
                s->count = 0;
            }
        } else if (ch == 'z' || (newver && ch == 'y')) {
            if (s->count != 0) return UNC_ERR_CORRUPT;
            if (btoa_release_group(s, 4) != UNC_OK) return UNC_ERR_SINK;
            s->group[0] = s->group[1] = s->group[2] = s->group[3] =
                ch == 'z' ? 0x00 : 0x20;
            if (!newver) {
                int k;
                for (k = 0; k < 4; k++) btoa_chk(s, s->group[0]);
            }
            s->have = 1;
        } else {
            return UNC_ERR_CORRUPT;
        }
    }
    return UNC_OK;
}

/* Read one line into buf (without its terminator). Returns the length,
 * or -1 at end of input. */
static int32_t btoa_read_line(UncBufIn *in, uint8_t *buf, int32_t cap)
{
    int32_t n = 0;
    int b;
    for (;;) {
        b = unc_bufin_next(in);
        if (b < 0) return n > 0 ? n : -1;
        if (b == '\n') return n;
        if (b == '\r') {
            /* CR ends a line as surely as LF does. A Macintosh text file
             * has ONLY CRs, and a Mac is where these are being read; the
             * first version of this skipped CR instead, which quietly
             * turned such a file into one enormous line. For CRLF the LF
             * arrives next and reads as an empty line, which both callers
             * already skip. */
            return n;
        }
        if (n < cap) buf[n++] = (uint8_t)b;
        else return n;                 /* over-long: the caller decides */
    }
}

static uint32_t btoa_hex(const uint8_t *p, int32_t n)
{
    uint32_t v = 0;
    int32_t i;
    for (i = 0; i < n; i++) {
        uint8_t c = p[i];
        if (c >= '0' && c <= '9') v = v * 16u + (uint32_t)(c - '0');
        else if (c >= 'a' && c <= 'f') v = v * 16u + (uint32_t)(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') v = v * 16u + (uint32_t)(c - 'A' + 10);
        else break;
    }
    return v;
}

static uint32_t btoa_dec(const uint8_t *p, int32_t n)
{
    uint32_t v = 0;
    int32_t i;
    for (i = 0; i < n && p[i] >= '0' && p[i] <= '9'; i++)
        v = v * 10u + (uint32_t)(p[i] - '0');
    return v;
}

/* Split a line on spaces; returns the number of fields found and fills
 * `off`/`len` for each. */
static int btoa_fields(const uint8_t *line, int32_t n, int32_t *off,
                       int32_t *flen, int max)
{
    int32_t i = 0;
    int f = 0;
    while (i < n && f < max) {
        while (i < n && line[i] == ' ') i++;
        if (i >= n) break;
        off[f] = i;
        while (i < n && line[i] != ' ') i++;
        flen[f] = i - off[f];
        f++;
    }
    return f;
}

int unc_btoa_extract(UncCtx *c)
{
    UncBufIn in;
    BtoaState s;
    uint8_t *iobuf, *obuf, *line;
    uint32_t iocap = 4096, ocap = 4096;
    int32_t n;
    int newver = 0, perline = 0, started = 0;
    uint8_t name[UNC_NAME_MAX + 1];
    uint16_t namelen = 0;
    int      nametrunc = 0;
    int32_t  namefull = 0;
    UncEntryInfo e;
    int sret, err = UNC_OK, est = UNC_OK;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap + BTOA_LINE_MAX);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;
    line = obuf + ocap;

    if (c->io->seek(c->io->ctx, 0) < 0) {
        unc_free(c->al, iobuf);
        return UNC_ERR_IO;
    }
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);

    s.c = c;
    unc_fork_out(&s.out, c, UNC_FORK_DATA, !c->opt.test_only,
                 UNC_CK_NONE, obuf, ocap);
    s.want = UNC_SIZE_UNKNOWN;
    s.eor = s.sum = s.rot = 0;
    s.code = 0;
    s.count = 0;
    s.have = 0;
    s.err = UNC_OK;

    /* --- the header, which may be anywhere in the mail around it --- */
    while ((n = btoa_read_line(&in, line, BTOA_LINE_MAX)) >= 0) {
        if (n >= 11 && line[0] == 'x' && line[1] == 'b' && line[2] == 't' &&
            line[3] == 'o' && line[4] == 'a') {
            if (line[5] == ' ') {                     /* xbtoa Begin */
                newver = 0;
                started = 1;
                break;
            }
            if (line[5] == '5' && line[6] == ' ') {   /* xbtoa5 N name Begin */
                int32_t off[4], flen[4];
                int f = btoa_fields(line, n, off, flen, 4);
                if (f >= 3) {
                    perline = (int)btoa_dec(line + off[1], flen[1]);
                    if (!(flen[2] == 1 && line[off[2]] == '-')) {
                        int32_t k;
                        /* The line itself may have been cut at
                         * BTOA_LINE_MAX, which cuts the name in it. */
                        namefull = flen[2];
                        nametrunc = flen[2] > UNC_NAME_MAX ||
                                    n >= BTOA_LINE_MAX;
                        namelen = (uint16_t)(flen[2] > UNC_NAME_MAX
                                             ? UNC_NAME_MAX : flen[2]);
                        for (k = 0; k < namelen; k++)
                            name[k] = line[off[2] + k];
                    }
                }
                if (perline <= 0 || perline >= BTOA_LINE_MAX) perline = 0;
                newver = 1;
                started = 1;
                break;
            }
        }
    }
    if (!started) {
        unc_free(c->al, iobuf);
        return UNC_ERR_FORMAT;
    }

    /* --- the entry. btoa carries no fork, no type and no dates: one
     *     data fork, named by the header where version 5 gives one and
     *     by the host's hint (the archive's own name) where it does
     *     not, exactly as gzip and .Z are named. --- */
    unc_entry_clear(&e);
    if (namelen) unc_entry_set_name(&e, name, namelen);
    else if (c->opt.name_hint && c->opt.name_hint_len)
        unc_entry_set_name(&e, c->opt.name_hint, c->opt.name_hint_len);
    if (namelen && nametrunc) {
        e.name_truncated = 1;
        /* Known when the NAME was too long; not when the line it sat on
         * was cut, since the name is not the last field on it. */
        if (namefull > UNC_NAME_MAX)
            e.name_full_len = (uint16_t)(namefull > 65535 ? 65535 : namefull);
    }
    e.data_size = UNC_SIZE_UNKNOWN;
    e.rsrc_size = 0;

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) { unc_free(c->al, iobuf); return UNC_ERR_SINK; }
    if (sret > 0) { unc_free(c->al, iobuf); return UNC_OK; }

    if (c->opt.list_only) {
        if (c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) err = UNC_ERR_SINK;
        unc_free(c->al, iobuf);
        return err;
    }

    /* --- body --- */
    for (;;) {
        n = btoa_read_line(&in, line, BTOA_LINE_MAX);
        if (n < 0) { est = UNC_ERR_TRUNCATED; break; }
        if (n > 0 && line[0] == 'x') {                /* the End line */
            int32_t off[12], flen[12];
            int f = btoa_fields(line, n, off, flen, 12);
            uint32_t n1, n2, oeor, osum, orot;
            /* xbtoa End N <dec> <hex> E <hex> S <hex> R <hex> */
            if (f < 10) { est = UNC_ERR_CORRUPT; break; }
            n1   = btoa_dec(line + off[3], flen[3]);
            n2   = btoa_hex(line + off[4], flen[4]);
            oeor = btoa_hex(line + off[6], flen[6]);
            osum = btoa_hex(line + off[8], flen[8]);
            orot = btoa_hex(line + off[10], flen[10]);
            if (n1 != n2) { est = UNC_ERR_CORRUPT; break; }
            s.want = n1;
            /* Whatever is still held back: (len - 1) & 3 says how many
             * of the final quad's four bytes are real. */
            if (btoa_release_group(&s, n1 == 0 ? 0
                                  : (int)(((n1 - 1u) & 3u) + 1u)) != UNC_OK) {
                est = UNC_ERR_SINK;
                break;
            }
            if (unc_fork_flush(&s.out) != UNC_OK) { est = UNC_ERR_SINK; break; }
            if (unc_fork_pos(&s.out) != n1) est = UNC_ERR_TRUNCATED;
            else if (oeor != s.eor || osum != s.sum || orot != s.rot)
                est = UNC_ERR_CRC;
            break;
        }
        if (n == 0) continue;                          /* blank line */
        {
            int32_t datalen = n;
            if (newver) {
                /* The last character is the line's own checksum. */
                uint8_t want = line[n - 1];
                datalen = n - 1;
                if (btoa_line(&s, line, datalen, newver) != UNC_OK) {
                    est = UNC_ERR_CORRUPT;
                    break;
                }
                if (want != (uint8_t)('!' + (s.sum % 85u))) {
                    est = UNC_ERR_CRC;
                    break;
                }
                continue;
            }
            if (btoa_line(&s, line, datalen, newver) != UNC_OK) {
                est = UNC_ERR_CORRUPT;
                break;
            }
        }
    }
    if (est != UNC_OK) (void)unc_fork_flush(&s.out);

    if (c->sink->end_entry(c->sink->ctx, est) < 0) err = UNC_ERR_SINK;
    unc_free(c->al, iobuf);
    return err;
}

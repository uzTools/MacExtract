/*
 * fmt_mimeseg.c — a message split across several FILES: `message/partial`
 * (RFC 2046 section 5.2.2), which is how a file too big for a mail
 * gateway crossed one. The sixth join scheme, and the only one whose
 * parts are text.
 *
 * Sources (transcribed, never guessed):
 *   reference/mpack/decode.c handlePartial() — the three parameters
 *       that matter (`id`, `number`, `total`), the sanity checks it
 *       applies to them (an id is required, a number is 1-based and
 *       may not exceed the total), and the reassembly itself: the
 *       BODIES of the parts, in number order, concatenated.
 *   reference/mpack/encode.c — what `mpack -m` writes, which is what
 *       tools/run_mime.py grades this against.
 *   reference/mpack/decode.c ParseHeaders() — a header line, and a
 *       continuation line that begins with space or tab; the blank
 *       line that ends the header block. The PARAMETER parsing is
 *       shared with src/fmt_mime.c rather than transcribed twice.
 *
 * What is joined is each part's body and nothing else. mpack composes
 * a standalone message out of the enclosing headers as well, because
 * its result is a file somebody may read; here the joined stream is
 * handed straight to the MIME walk, and part 1's body already begins
 * with the enclosed message's own headers. DECISIONS.md 2026-08-29.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define MSEG_SCAN_MAX  16384u  /* how far into a part its headers may run */
#define MSEG_LINE      512     /* the scan window                         */
#define MSEG_HDR       512     /* one unfolded header                     */
#define MSEG_CTYPE     64      /* "message/partial", lowercased           */
#define MSEG_PARAM     64      /* one parameter value                     */

typedef struct MsegInfo {
    uint32_t body;               /* offset of the first body byte      */
    int      part;               /* the `number` parameter             */
    int      nparts;             /* the `total` parameter, or 0        */
    uint8_t  id[UNC_SEG_FP_LEN]; /* the `id` parameter, first 26 bytes */
    uint32_t idlen;
    int      partial;            /* the Content-Type was message/partial */
} MsegInfo;

/* A decimal parameter value. Anything that is not a run of digits is
 * not a number: mpack reaches atoi() with the same string and gets 0,
 * which its own sanity check then rejects. */
static int mseg_num(const uint8_t *p, uint32_t len)
{
    uint32_t i;
    long v = 0;

    if (len == 0) return 0;
    for (i = 0; i < len; i++) {
        if (p[i] < '0' || p[i] > '9') return 0;
        v = v * 10 + (p[i] - '0');
        if (v > 65535) return 0;
    }
    return (int)v;
}

static int32_t mseg_len(const uint8_t *s)
{
    int32_t n = 0;
    while (s[n]) n++;
    return n;
}

/* One unfolded header of a part. Only Content-Type says anything. */
static void mseg_header(const uint8_t *h, int32_t hlen, MsegInfo *mi)
{
    uint8_t ct[MSEG_CTYPE + 1], pb[MSEG_PARAM + 1];
    int32_t k = unc_mime_ci_prefix(h, hlen, "content-type:");
    uint32_t n;

    if (k == 0) return;
    unc_mime_ctype_of(h + k, hlen - k, ct, MSEG_CTYPE);
    if (unc_mime_ci_prefix(ct, mseg_len(ct), "message/partial") == 0) return;
    mi->partial = 1;

    n = unc_mime_param(h, hlen, "number", pb, MSEG_PARAM, NULL);
    mi->part = mseg_num(pb, n);
    n = unc_mime_param(h, hlen, "total", pb, MSEG_PARAM, NULL);
    mi->nparts = mseg_num(pb, n);
    mi->idlen = unc_mime_param(h, hlen, "id", mi->id, UNC_SEG_FP_LEN, NULL);
}

/* Read a part's header block: what it says about the set, and where
 * its body starts. UNC_ERR_FORMAT for anything that does not end its
 * headers with a blank line inside MSEG_SCAN_MAX bytes.
 *
 * The window is walked in whole lines, exactly as unc_mime_probe walks
 * one — with the difference that a blank line has to be SEEN here
 * rather than stepped over, because it is what the body starts after. */
static int mseg_scan(UncIO *io, MsegInfo *mi)
{
    uint8_t buf[MSEG_LINE], hb[MSEG_HDR];
    int32_t hn = 0, n, i;
    uint32_t pos = 0, size;
    int done = 0, first = 1;

    mi->body = 0;
    mi->part = mi->nparts = 0;
    mi->idlen = 0;
    mi->partial = 0;
    for (i = 0; i < UNC_SEG_FP_LEN; i++) mi->id[i] = 0;

    size = unc_io_size32(io);
    if (size == UNC_SIZE_UNKNOWN || size > MSEG_SCAN_MAX) size = MSEG_SCAN_MAX;

    while (pos < size && !done) {
        int32_t want = (int32_t)(size - pos);
        if (want > (int32_t)sizeof buf) want = (int32_t)sizeof buf;
        if (unc_read_at(io, pos, buf, want) != UNC_OK) break;
        n = want;

        /* Whole lines only, and never a CR whose LF is in the next
         * window: taking those two for two terminators would invent a
         * blank line, which here means the headers ended. */
        if (pos + (uint32_t)n < size) {
            while (n > 0 && buf[n - 1] != '\n' && buf[n - 1] != '\r') n--;
            if (n > 0 && buf[n - 1] == '\r') n--;
            if (n == 0) {                      /* a line longer than buf */
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
            if (i < n && buf[i] == '\r') {
                i++;
                if (i < n && buf[i] == '\n') i++;
            } else if (i < n && buf[i] == '\n') {
                i++;
            }

            /* The file has to START like a message. Said here rather
             * than left to the scan, because unc_segment_describe asks
             * every scheme about every archive a host opens: without
             * this a .sit would be read 16 KB at a time looking for a
             * blank line, once per open, on a 7 MHz machine. */
            if (first) {
                first = 0;
                if (!unc_mime_is_header(buf + s, e - s) &&
                    unc_mime_ci_prefix(buf + s, e - s, "from ") == 0)
                    return UNC_ERR_FORMAT;
            }

            if (hn > 0 && e > s && (buf[s] == ' ' || buf[s] == '\t')) {
                int32_t k = s;                          /* a continuation */
                while (k < e && hn < (int32_t)sizeof hb - 1) hb[hn++] = buf[k++];
                continue;
            }
            if (hn > 0) { mseg_header(hb, hn, mi); hn = 0; }
            if (e == s) {                     /* the blank line: body next */
                mi->body = pos + (uint32_t)i;
                done = 1;
                break;
            }
            {
                int32_t k = s;
                while (k < e && hn < (int32_t)sizeof hb - 1) hb[hn++] = buf[k++];
            }
        }
        pos += (uint32_t)n;
    }

    return done ? UNC_OK : UNC_ERR_FORMAT;
}

/* Everything mpack refuses a part for, in its own order. */
static int mseg_ok(const MsegInfo *mi)
{
    if (!mi->partial) return 0;
    if (mi->idlen == 0) return 0;               /* "has no id parameter" */
    if (mi->part < 1 || mi->part > UNC_SEG_MAX_PARTS) return 0;
    if (mi->nparts > UNC_SEG_MAX_PARTS) return 0;
    if (mi->nparts && mi->part > mi->nparts) return 0;   /* "invalid number" */
    return 1;
}

/* The probe. A part of a set goes before the whole it resembles, so
 * unc_sniff runs this in front of the MIME probes — without it, part 1
 * of a set reads as the message it is a slice of, and parts 2..n as
 * nothing at all (which is what they did until 2026-08-29). */
UncFormat unc_mimeseg_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    MsegInfo mi;
    int32_t e = 0;

    if (len < 16 || !io) return UNC_FORMAT_UNKNOWN;
    /* The file has to start like a message. Same gate as the MIME
     * probe's, and it is what keeps this off every binary archive. */
    while (e < len && head[e] != '\n' && head[e] != '\r') e++;
    if (!unc_mime_is_header(head, e) &&
        unc_mime_ci_prefix(head, e, "from ") == 0) return UNC_FORMAT_UNKNOWN;

    if (mseg_scan(io, &mi) != UNC_OK) return UNC_FORMAT_UNKNOWN;
    return mseg_ok(&mi) ? UNC_FORMAT_MIMESEG : UNC_FORMAT_UNKNOWN;
}

int unc_mimeseg_describe(UncIO *io, UncSegmentDesc *desc)
{
    MsegInfo mi;
    uint32_t i;

    if (mseg_scan(io, &mi) != UNC_OK) return UNC_ERR_FORMAT;
    if (!mseg_ok(&mi)) return UNC_ERR_FORMAT;

    for (i = 0; i < sizeof *desc; i++) ((uint8_t *)desc)[i] = 0;
    desc->scheme = UNC_FORMAT_MIMESEG;
    desc->part = (uint16_t)mi.part;
    desc->nparts = (uint16_t)mi.nparts;
    /* The identity is the `id` parameter, which every part of a set
     * repeats — the first 26 bytes of it, which is what a fingerprint
     * holds. Two sets that agree that far would be read as one; the
     * scheme that has been in this engine longest identifies itself
     * with two bytes. */
    for (i = 0; i < mi.idlen && i < UNC_SEG_FP_LEN; i++) desc->fp[i] = mi.id[i];
    /* A part's own headers are its header, and they are not all the
     * same length — so this is the length of THIS part's, and the
     * joiner asks again for every part it opens (unc_mimeseg_head). */
    desc->head_len = mi.body;
    /* Nothing in the format states how many bytes the message weighs:
     * `total` counts PARTS. The joiner learns the length when it opens
     * the last one. */
    desc->total = UNC_SIZE_UNKNOWN;
    desc->name_len = 0;
    desc->name[0] = 0;
    return UNC_OK;
}

/* This part's own header length, and the check that it is the part the
 * joiner asked for: the number and the id are in every part, so a set
 * assembled out of the wrong files is caught here rather than in the
 * joined stream. */
int unc_mimeseg_head(const UncSegmentDesc *d, UncIO *io, int part,
                     uint32_t size, uint32_t *out)
{
    MsegInfo mi;
    uint32_t i;

    (void)size;
    if (mseg_scan(io, &mi) != UNC_OK) return UNC_ERR_CORRUPT;
    if (!mseg_ok(&mi)) return UNC_ERR_CORRUPT;
    if (mi.part != part) return UNC_ERR_CORRUPT;
    for (i = 0; i < UNC_SEG_FP_LEN; i++)
        if (mi.id[i] != d->fp[i]) return UNC_ERR_CORRUPT;
    *out = mi.body;
    return UNC_OK;
}

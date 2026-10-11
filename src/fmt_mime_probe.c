/* fmt_mime_probe.c — MIME's two probes and the header parse behind them.
 *
 * Split out so the decoder can live in an overlay: unc_sniff calls a probe
 * for every file it is handed. The header parse comes along because the
 * decoder uses it too, so this file is compiled into the MIME overlay as
 * well — one definition, two places.
 *
 * Source: unchanged from fmt_mime.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_mime_priv.h"

void mime_ctype_of(const uint8_t *h, int32_t hlen, uint8_t *out)
{
    int32_t i = 0, n = 0;
    while (i < hlen && mime_is_space(h[i])) i++;
    while (i < hlen && h[i] != ';' && !mime_is_space(h[i]) && h[i] != '(') {
        if (n < MIME_CTYPE_MAX) out[n++] = (uint8_t)mime_lower(h[i]);
        i++;
    }
    out[n] = 0;
}

/* The four exported helpers. They are here rather than in the decoder
 * because src/fmt_mimeseg.c calls them and STAYS RESIDENT: a
 * message/partial set is recognised and joined before anything knows
 * there is a MIME message under it. This file is compiled into the
 * text overlay too, so the decoder has them as well.
 */
int32_t unc_mime_ci_prefix(const uint8_t *s, int32_t len, const char *pfx)
{
    return mime_ci_prefix(s, len, pfx);
}

uint32_t unc_mime_param(const uint8_t *h, int32_t hlen, const char *key,
                        uint8_t *out, uint32_t cap, int *trunc)
{
    return mime_param(h, hlen, key, out, cap, trunc);
}

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

int mime_lower(int c)
{
    return (c >= 'A' && c <= 'Z') ? c + ('a' - 'A') : c;
}

int32_t mime_strlen(const char *s)
{
    int32_t n = 0;
    while (s[n]) n++;
    return n;
}

int mime_is_space(int c)
{
    return c == ' ' || c == '\t';
}

int mime_is_header(const uint8_t *s, int32_t len)
{
    int32_t i;
    for (i = 0; i < len; i++) {
        if (s[i] == ':') return i > 0;
        if (s[i] <= ' ' || s[i] >= 0177) return 0;
    }
    return 0;
}

int32_t mime_ci_prefix(const uint8_t *s, int32_t len, const char *pfx)
{
    int32_t i;
    for (i = 0; pfx[i]; i++) {
        if (i >= len) return 0;
        if (mime_lower(s[i]) != mime_lower((unsigned char)pfx[i])) return 0;
    }
    return i;
}

uint32_t mime_param(const uint8_t *h, int32_t hlen, const char *key,
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

int mime_cte_of(const uint8_t *h, int32_t hlen)
{
    while (hlen > 0 && mime_is_space(*h)) { h++; hlen--; }
    if (mime_ci_prefix(h, hlen, "base64")) return MIME_CTE_B64;
    if (mime_ci_prefix(h, hlen, "quoted-printable")) return MIME_CTE_QP;
    return MIME_CTE_NONE;
}

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

UncFormat unc_mime_probe_multipart(const uint8_t *head, int32_t len,
                                   UncIO *io)
{
    return mime_probe(head, len, io, 1);
}

UncFormat unc_mime_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    return mime_probe(head, len, io, 0);
}

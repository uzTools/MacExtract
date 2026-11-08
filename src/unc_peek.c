/*
 * unc_peek.c — what an envelope holds, from its first bytes.
 *
 * The Macintosh shell gives back the overlay bundle after the sniff, keeping
 * only the images the sniffed format can want; an ENVELOPE kept all of them,
 * because what is under one is unknown until it has been unwrapped. This
 * decodes just enough of the envelope to sniff what is under it, so the shell
 * can keep the envelope's reader and the inner format's instead
 * (DECISIONS.md 2026-11-03, *the envelope that said what it held*).
 *
 * Two bounds make it cheap enough to run before the release, with the whole
 * bundle still in memory. The envelope's reader sees the first PEEK_WINDOW
 * bytes of the file as the whole file, so a reader that sizes its tables
 * from its input — LZW's, for .Z — sizes them for that; and the sink stops
 * the decode at PEEK_HEAD bytes of the first file's data fork. What comes
 * back is UNC_FORMAT_UNKNOWN whenever those bytes do not say: an inner
 * format that needs the end of the file (Compact Pro's index) or more than
 * the head, or a reader whose payload starts past the window.
 *
 * The head can also name what the whole file is not: a probe ahead of the
 * answer that reads past 512 bytes cannot claim it here — a zip found by
 * its end record behind a tar header sniffs as tar. The corpus holds no
 * such payload; the shell reads its bundle again when the layer under
 * disagrees (mac/ovl_load_eager.c; DECISIONS.md 2026-11-05, *the head that
 * was not the file*).
 *
 * The head is sniffed as a file of PEEK_HEAD bytes. Measured 2026-11-04 over
 * every envelope fixture, 466: 301 named, none other than the format the
 * whole payload sniffs as (tools/run_peek.py, in ci.sh); the rest name
 * nothing — Compact Pro and SuperDisk! say what they are only at the end.
 * A 2 KB window named no BinHex at all: bh_fork writes 4 KB at a time.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "unc_internal.h"

#define PEEK_WINDOW 8192u    /* bytes of the envelope its reader may see */
#define PEEK_HEAD   512      /* bytes of payload sniffed: a tar header */

/* The envelope, cut to its first `size` bytes. */
typedef struct { UncIO *io; uint32_t size; } PeekWin;

static int32_t pw_read(void *ctx, void *buf, int32_t len)
{
    PeekWin *w = (PeekWin *)ctx;
    unc_off_t at = w->io->tell(w->io->ctx);
    if (at >= (unc_off_t)w->size) return 0;
    if ((uint32_t)len > w->size - (uint32_t)at)
        len = (int32_t)(w->size - (uint32_t)at);
    return w->io->read(w->io->ctx, buf, len);
}
static int pw_seek(void *ctx, unc_off_t pos)
{
    PeekWin *w = (PeekWin *)ctx;
    return w->io->seek(w->io->ctx, pos);
}
static unc_off_t pw_tell(void *ctx)
{
    PeekWin *w = (PeekWin *)ctx;
    return w->io->tell(w->io->ctx);
}
static unc_off_t pw_size(void *ctx)
{
    return (unc_off_t)((PeekWin *)ctx)->size;
}

/* The first file's data fork, up to PEEK_HEAD bytes, then stop. */
typedef struct {
    uint8_t head[PEEK_HEAD];
    uint32_t len, pos;
    int      entries;
} PeekHead;

static int ph_begin(void *ctx, const UncEntryInfo *info)
{
    PeekHead *h = (PeekHead *)ctx;
    if (info->is_dir) return 1;
    return h->entries++ ? 1 : 0;
}
static int ph_write(void *ctx, UncFork fork, const void *buf, int32_t len)
{
    PeekHead *h = (PeekHead *)ctx;
    const uint8_t *p = (const uint8_t *)buf;
    if (fork != UNC_FORK_DATA) return 0;
    while (len-- > 0 && h->len < (uint32_t)PEEK_HEAD) h->head[h->len++] = *p++;
    return h->len < (uint32_t)PEEK_HEAD ? 0 : -1;  /* enough: stop it */
}
static int ph_end(void *ctx, int status)
{
    (void)ctx; (void)status;
    return 0;
}

/* And that head, read back as a file of its own. */
static int32_t ph_read(void *ctx, void *buf, int32_t len)
{
    PeekHead *h = (PeekHead *)ctx;
    uint8_t *d = (uint8_t *)buf;
    int32_t n = 0;
    while (n < len && h->pos < h->len) d[n++] = h->head[h->pos++];
    return n;
}
static int ph_seek(void *ctx, unc_off_t pos)
{
    PeekHead *h = (PeekHead *)ctx;
    if (pos > (unc_off_t)h->len) return -1;
    h->pos = (uint32_t)pos;
    return 0;
}
static unc_off_t ph_tell(void *ctx) { return ((PeekHead *)ctx)->pos; }
static unc_off_t ph_size(void *ctx) { return ((PeekHead *)ctx)->len; }

UncFormat unc_envelope_peek(UncIO *io, UncAlloc *al, int *enc)
{
    PeekWin w;
    PeekHead h;
    UncIO wio, hio;
    UncSink sk;
    UncFormat env, inner;
    uint32_t size;

    *enc = UNC_ENC_UNKNOWN;
    env = unc_sniff_envelope(io);
    if (env == UNC_FORMAT_UNKNOWN) return UNC_FORMAT_UNKNOWN;
    size = io->size ? unc_io_size32(io) : UNC_U32_MAX;
    if (size == UNC_U32_MAX) return UNC_FORMAT_UNKNOWN;

    w.io = io;
    w.size = size < PEEK_WINDOW ? size : PEEK_WINDOW;
    wio.ctx = &w;
    wio.read = pw_read;
    wio.seek = pw_seek;
    wio.tell = pw_tell;
    wio.size = pw_size;

    h.len = h.pos = 0;
    h.entries = 0;
    sk.ctx = &h;
    sk.begin_entry = ph_begin;
    sk.write = ph_write;
    sk.end_entry = ph_end;
    sk.comment = NULL;

    /* Its status is not the answer: a decode cut off by the window or by
     * the sink fails, and what it delivered first is what is judged. */
    (void)unc_extract_as(env, &wio, &sk, al, NULL, NULL);
    (void)io->seek(io->ctx, 0);
    if (h.len < (uint32_t)PEEK_HEAD) return UNC_FORMAT_UNKNOWN;

    hio.ctx = &h;
    hio.read = ph_read;
    hio.seek = ph_seek;
    hio.tell = ph_tell;
    hio.size = ph_size;
    inner = unc_sniff(&hio);
    if (inner != UNC_FORMAT_UNKNOWN) {
        (void)hio.seek(hio.ctx, 0);
        *enc = unc_archive_encrypted(inner, &hio);
    }
    return inner;
}

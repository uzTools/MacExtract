/* fz_common.h — what every decoder harness in tools/fuzz/ shares.
 *
 * A harness feeds ONE decoder its raw stream, with no container around
 * it: the container's checks (magic, header CRCs, sizes that must agree)
 * are what kept tools/fuzz.py's mutants away from the decoders' code
 * tables. Every input is
 *
 *     [outlen: 4 bytes, big-endian] [param: 1 byte] [budget: 1 byte] [stream]
 *
 * `outlen` is what the container would have declared (capped at
 * FZ_OUTMAX so one input cannot run for seconds), `param` is the
 * harness's own (a method, a window size, a shape), and `budget` picks
 * the allocator's cap, so allocation failure is reached as on a small
 * Macintosh: 0 is FZ_BUDGET_BIG, anything else is budget * 4 KB.
 * tools/fuzz/make_seeds.py writes seeds in this shape from the corpus.
 *
 * The sink discards what it is given: a harness is graded by ASan and
 * UBSan, not by its output (the differential suite grades output).
 *
 * SPDX-License-Identifier: 0BSD
 */
#ifndef FZ_COMMON_H
#define FZ_COMMON_H

#include "unc_internal.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define FZ_HDR       6u
#define FZ_OUTMAX    (1u << 20)
#define FZ_BUDGET_BIG (16u << 20)

typedef struct FzMem {
    const uint8_t *d;
    uint32_t n, pos;
} FzMem;

static int32_t fz_read(void *ctx, void *buf, int32_t len)
{
    FzMem *m = (FzMem *)ctx;
    uint32_t left = m->n - m->pos;
    if (len < 0) return -1;
    if ((uint32_t)len > left) len = (int32_t)left;
    memcpy(buf, m->d + m->pos, (size_t)len);
    m->pos += (uint32_t)len;
    return len;
}

static int fz_seek(void *ctx, unc_off_t pos)
{
    FzMem *m = (FzMem *)ctx;
    if (pos > m->n) return -1;
    m->pos = (uint32_t)pos;
    return 0;
}

static unc_off_t fz_tell(void *ctx) { return ((FzMem *)ctx)->pos; }
static unc_off_t fz_size(void *ctx) { return ((FzMem *)ctx)->n; }

/* A running total against a cap, as the Mac shell's allocator keeps one.
 * Each block carries its size in front so free can give it back. */
typedef struct FzAlloc { uint32_t cap, live; } FzAlloc;

static void *fz_alloc(void *ctx, uint32_t size)
{
    FzAlloc *a = (FzAlloc *)ctx;
    uint32_t *p;
    if (size > a->cap - a->live) return NULL;
    p = (uint32_t *)malloc((size_t)size + 8u);
    if (!p) return NULL;
    p[0] = size;
    a->live += size;
    return p + 2;
}

static void fz_free(void *ctx, void *ptr)
{
    FzAlloc *a = (FzAlloc *)ctx;
    uint32_t *p;
    if (!ptr) return;
    p = (uint32_t *)ptr - 2;
    a->live -= p[0];
    free(p);
}

static int fz_begin(void *ctx, const UncEntryInfo *i) { (void)ctx; (void)i; return 0; }
static int fz_write(void *ctx, UncFork f, const void *b, int32_t n)
{
    (void)ctx; (void)f; (void)b; (void)n;
    return UNC_OK;
}
static int fz_end(void *ctx, int s) { (void)ctx; (void)s; return 0; }

/* Everything a decoder can reach through its context, over `stream`. */
typedef struct Fz {
    uint32_t outlen;
    uint8_t  param;
    const uint8_t *stream;
    uint32_t n;
    FzMem    mem;
    UncIO    io;
    FzAlloc  fa;
    UncAlloc al;
    UncSink  sink;
    UncCtx   c;
} Fz;

/* 0: the input is too short to carry a header. */
static int fz_init(Fz *z, const uint8_t *data, size_t size)
{
    if (size < FZ_HDR || size > 0x7FFFFFFFu) return 0;
    memset(z, 0, sizeof *z);
    z->outlen = ((uint32_t)data[0] << 24) | ((uint32_t)data[1] << 16)
              | ((uint32_t)data[2] << 8) | data[3];
    if (z->outlen > FZ_OUTMAX) z->outlen %= FZ_OUTMAX + 1u;
    z->param = data[4];
    z->fa.cap = data[5] ? (uint32_t)data[5] << 12 : FZ_BUDGET_BIG;
    z->stream = data + FZ_HDR;
    z->n = (uint32_t)(size - FZ_HDR);

    z->mem.d = z->stream;
    z->mem.n = z->n;
    z->io.ctx = &z->mem;
    z->io.read = fz_read;
    z->io.seek = fz_seek;
    z->io.tell = fz_tell;
    z->io.size = fz_size;
    z->al.ctx = &z->fa;
    z->al.alloc = fz_alloc;
    z->al.free = fz_free;
    z->sink.begin_entry = fz_begin;
    z->sink.write = fz_write;
    z->sink.end_entry = fz_end;

    z->c.io = &z->io;
    z->c.sink = &z->sink;
    z->c.al = &z->al;
    z->c.ps.total = z->n;
    z->c.pwstate = UNC_PW_UNSET;
    return 1;
}

/* An allocation the decoder failed to give back is a leak ASan would
 * miss: everything here goes through fz_alloc. */
static void fz_done(Fz *z)
{
    if (z->fa.live != 0) abort();
}

#endif

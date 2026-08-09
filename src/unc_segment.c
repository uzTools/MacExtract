/*
 * unc_segment.c — presents the parts of a segmented archive as one
 * stream.
 *
 * The engine sequences; the host opens. Everything here works through
 * UncVolumeSource callbacks, so no file is touched from the engine and
 * the whole joiner is a caller-provided struct — no allocation, no
 * global state, one part open at a time (a Mac Plus with one floppy
 * drive cannot mount two, and System 6 counts its FCBs).
 *
 * Part sizes are not stored anywhere in the formats, so the map from a
 * logical offset to a part is discovered by opening parts in order:
 * start[i] is known only once parts 1..i-1 have been seen. That is why
 * a backward seek can cost a re-open, and why the joiner counts those
 * crossings — see unc_segment_stats() and DECISIONS.md.
 *
 * The two schemes end the walk differently, and that is the only place
 * they differ here. A StuffIt set declares its payload TOTAL in part 1,
 * so the walk stops when that many bytes have been seen and the parts
 * are opened lazily, strictly forward. A spanned zip declares a part
 * COUNT instead, and its reader wants the end of the stream first, so
 * every part is opened once up front purely to be measured. Which is
 * not an inefficiency to remove: the sizes ARE the address map, and
 * without them a (part, offset) pair cannot be resolved at all.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

typedef struct SegJoin {
    UncIO                 io;      /* what the engine reads through */
    const UncSegmentDesc *desc;
    UncVolumeSource      *vs;

    UncIO    cur;                  /* stream of the open part, if any */
    int      curpart;              /* 0 = none open */

    /* start[i] = logical offset of part i's payload, 1-based.
     * Valid for i <= known; start[known] is the total payload seen so
     * far, i.e. where the next unopened part would begin. */
    uint32_t start[UNC_SEG_MAX_PARTS + 2];
    int      known;

    /* Where the walk stops. Exactly one of these is authoritative:
     * `total` for a scheme that declares its payload size, `last` for
     * one that declares a part count (and then `total` is measured). */
    uint32_t total;
    int      last;                 /* highest part that may exist */

    uint32_t pos;                  /* logical read cursor */
    uint32_t switches;             /* parts opened */
    uint32_t backward;             /* opens forced by a backward seek */
    int      err;                  /* sticky: UNC_ERR_SEGMENTED etc. */
} SegJoin;

uint32_t unc_segment_scratch_size(void)
{
    return (uint32_t)sizeof(SegJoin);
}

int unc_segment_describe(UncIO *io, UncSegmentDesc *desc)
{
    int err;

    if (!io || !desc) return UNC_ERR_FORMAT;
    /* StuffIt first: it decides on 100 bytes at offset 0, where the zip
     * scheme has to hunt backwards from the end of the file. */
    err = unc_sitseg_describe(io, desc);
    if (err == UNC_OK) return UNC_OK;
    return unc_zipseg_describe(io, desc);
}

void unc_segment_stats(const void *scratch, uint32_t *part_switches,
                       uint32_t *backward_crossings)
{
    const SegJoin *j = (const SegJoin *)scratch;
    if (!j) return;
    if (part_switches) *part_switches = j->switches;
    if (backward_crossings) *backward_crossings = j->backward;
}

static void seg_release(SegJoin *j)
{
    if (j->curpart && j->vs->release) j->vs->release(j->vs->ctx, &j->cur);
    j->curpart = 0;
}

/* Make `part` the open one. Returns UNC_OK, UNC_ERR_SEGMENTED (the
 * host cannot produce it), or another negative error. */
static int seg_open(SegJoin *j, int part)
{
    uint32_t size;
    int err;

    if (j->curpart == part) return UNC_OK;
    if (part < 1 || part > j->last) return UNC_ERR_SEGMENTED;
    if (part > j->known) return UNC_ERR_CORRUPT;   /* start[] not derived yet */

    if (j->curpart && part < j->curpart) j->backward++;
    seg_release(j);

    err = j->vs->need(j->vs->ctx, j->desc, part, &j->cur);
    if (err != UNC_OK) return err;
    j->curpart = part;
    j->switches++;

    /* A part shorter than its own header carries no payload and would
     * make start[] non-monotonic. */
    size = j->cur.size(j->cur.ctx);
    if (size == UNC_SIZE_UNKNOWN || size < j->desc->head_len) {
        seg_release(j);
        return UNC_ERR_CORRUPT;
    }
    if (part == j->known) {
        uint32_t end = j->start[part] + (size - j->desc->head_len);
        if (end < j->start[part]) { seg_release(j); return UNC_ERR_CORRUPT; }
        j->start[part + 1] = end;
        j->known = part + 1;
    }
    return UNC_OK;
}

/* Open whichever part holds logical offset `at`, extending the map by
 * opening parts in order when `at` lies past everything seen. */
static int seg_locate(SegJoin *j, uint32_t at)
{
    int i;

    /* Already mapped: binary search would be overkill for <= 256. */
    for (i = 1; i < j->known; i++)
        if (at >= j->start[i] && at < j->start[i + 1])
            return seg_open(j, i);

    /* Past the end of the map: walk forward, opening as we go. */
    while (j->known <= j->last) {
        int next = j->known;
        int err;
        if (j->start[next] > at) break;      /* map overshot: gap, give up */
        err = seg_open(j, next);
        if (err != UNC_OK) return err;
        if (at < j->start[j->known]) return UNC_OK;
        if (j->start[j->known] >= j->total) break;        /* set complete */
    }
    return UNC_ERR_SEGMENTED;
}

/* Open every part once, in order, so that start[] spans the whole set
 * and the total is known. Only for a scheme that declares a part count
 * instead of a payload size; a declared total needs no such pass and
 * must not pay for one. */
static int seg_measure(SegJoin *j)
{
    while (j->known <= j->last) {
        int err = seg_open(j, j->known);
        if (err != UNC_OK) return err;
    }
    j->total = j->start[j->last + 1];
    return UNC_OK;
}

/* Logical offset where part `part` begins, for a reader that addresses
 * the stream as (part, offset within it). UNC_SIZE_UNKNOWN if the part
 * is not in the set — which for a set assembled by filename is a real
 * possibility and must not read as offset 0. */
static uint32_t seg_base(void *ctx, int part)
{
    const SegJoin *j = (const SegJoin *)ctx;
    if (part < 1 || part > j->last || part >= j->known)
        return UNC_SIZE_UNKNOWN;
    return j->start[part];
}

static int32_t seg_read(void *ctx, void *buf, int32_t len)
{
    SegJoin *j = (SegJoin *)ctx;
    uint32_t avail;
    int32_t r;
    int err;

    if (len <= 0) return 0;
    if (j->pos >= j->total) return 0;                /* logical EOF */

    err = seg_locate(j, j->pos);
    if (err == UNC_ERR_SEGMENTED) {
        /* A part the host could not produce. Reported as EOF so the
         * entry fails as truncated (partial output is kept and the
         * sink is told), while unc_extract_segments turns the sticky
         * error into UNC_ERR_SEGMENTED for the caller. */
        j->err = UNC_ERR_SEGMENTED;
        return 0;
    }
    if (err != UNC_OK) { j->err = err; return -1; }

    /* Do not read past this part, nor past the declared payload. */
    avail = j->start[j->curpart + 1] - j->pos;
    if (j->total - j->pos < avail) avail = j->total - j->pos;
    if ((uint32_t)len > avail) len = (int32_t)avail;
    if (len <= 0) return 0;

    if (j->cur.seek(j->cur.ctx,
                    j->desc->head_len + (j->pos - j->start[j->curpart])) < 0) {
        j->err = UNC_ERR_IO;
        return -1;
    }
    r = j->cur.read(j->cur.ctx, buf, len);
    if (r < 0) { j->err = UNC_ERR_IO; return -1; }
    j->pos += (uint32_t)r;
    return r;
}

static int seg_seek(void *ctx, uint32_t pos)
{
    SegJoin *j = (SegJoin *)ctx;
    j->pos = pos;               /* lazy: the next read locates the part */
    return 0;
}

static uint32_t seg_tell(void *ctx)  { return ((SegJoin *)ctx)->pos; }
static uint32_t seg_size(void *ctx)  { return ((SegJoin *)ctx)->total; }

int unc_extract_segments(const UncSegmentDesc *desc, UncVolumeSource *vs,
                         void *scratch, UncSink *sink, UncAlloc *al,
                         UncProgress *prog, const UncOptions *opt)
{
    SegJoin *j = (SegJoin *)scratch;
    UncSegMap map;
    UncCtx c;
    int ret;

    if (!desc || !vs || !vs->need || !scratch || !sink || !al)
        return UNC_ERR_IO;
    if (desc->scheme != UNC_FORMAT_SITSEG && desc->scheme != UNC_FORMAT_ZIPSEG)
        return UNC_ERR_UNSUPPORTED;
    if (desc->nparts > UNC_SEG_MAX_PARTS) return UNC_ERR_UNSUPPORTED;
    /* Neither a size nor a count is a set nobody can tell the end of. */
    if (desc->nparts == 0 && desc->total == UNC_SIZE_UNKNOWN)
        return UNC_ERR_CORRUPT;

    j->desc = desc;
    j->vs = vs;
    j->curpart = 0;
    j->start[1] = 0;
    j->known = 1;
    j->total = desc->total;
    j->last = desc->nparts ? (int)desc->nparts : UNC_SEG_MAX_PARTS;
    j->pos = 0;
    j->switches = 0;
    j->backward = 0;
    j->err = UNC_OK;
    j->io.ctx = j;
    j->io.read = seg_read;
    j->io.seek = seg_seek;
    j->io.tell = seg_tell;
    j->io.size = seg_size;

    if (j->total == UNC_SIZE_UNKNOWN) {
        ret = seg_measure(j);
        if (ret != UNC_OK) { seg_release(j); return ret; }
    }

    map.ctx = j;
    map.base = seg_base;
    map.nparts = (uint16_t)j->last;

    c.io = &j->io;
    c.sink = sink;
    c.al = al;
    /* Only for a scheme that declares a part count, because only then
     * is `nparts` a fact rather than the ceiling the walk happens to
     * have been given. A StuffIt payload is a plain byte stream and
     * nothing reading it asks which part a byte came from. */
    c.segmap = desc->nparts ? &map : NULL;
    c.ps.prog = prog;
    c.ps.total = j->total;
    c.ps.done = 0;
    c.ps.since_tick = 0;
    c.ps.hold = 0;
    if (opt) c.opt = *opt;
    else { c.opt.list_only = 0; c.opt.test_only = 0;
           c.opt.name_hint = 0; c.opt.name_hint_len = 0; }

    if (desc->scheme == UNC_FORMAT_ZIPSEG)
        ret = unc_zip_extract(&c);
    else
        ret = unc_sitseg_emit(&c, desc, 0);
    seg_release(j);

    /* A missing part is the archive's verdict, not the entry's: the
     * entry has already been reported truncated through end_entry.
     * UNC_ERR_IO is overridden too — the joiner turning a refusal into
     * a failed read is how the host's answer reaches the engine, and
     * "I/O error" would describe the mechanism instead of the cause
     * (a user who pressed Cancel, say). */
    if (j->err != UNC_OK && (ret == UNC_OK || ret == UNC_ERR_IO))
        ret = j->err;
    return ret;
}

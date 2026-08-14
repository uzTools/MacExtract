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
 * There are two modes, and which one a scheme wants follows from how
 * it addresses itself.
 *
 *   FLAT (StuffIt, and a plain NAME.001 split). The payload is one byte
 *   stream that happens to be cut up, and nothing inside it refers to a
 *   part. So the parts are presented as one address space, `start[]`
 *   maps an offset to a part, and it is discovered by opening parts in
 *   order — start[i] is known only once 1..i-1 have been seen. StuffIt
 *   declares its payload TOTAL in part 1, so the walk knows when to
 *   stop; a split declares nothing anywhere, and the host's part sizes
 *   are what end it.
 *
 *   ADDRESSED (spanned zip). The archive already stores (part, offset)
 *   pairs, so they are kept as pairs: position at one, read, and roll
 *   into the next part at EOF. No `start[]`, no sizes, no pass over the
 *   set to learn them. The set declares a part COUNT instead of a size,
 *   which is all this mode needs.
 *
 * Flattening the addressed case was the first implementation and it
 * cost a pass over every part before extraction began, to build a table
 * that only existed to undo the pairs the format had already given us
 * — on a one-drive Mac, a disk swap each (DECISIONS.md 2026-08-09).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

typedef struct SegJoin {
    UncIO                 io;      /* what the engine reads through */
    const UncSegmentDesc *desc;
    UncVolumeSource      *vs;

    /* SPLIT only: the caller's descriptor with the sizes filled in.
     * The joined length is learned here — from the volume source —
     * rather than by the host, and the emitter needs it in a desc.
     * In the scratch block because a 1 MB Mac has 8 KB of stack. */
    UncSegmentDesc        split;

    UncIO    cur;                  /* stream of the open part, if any */
    int      curpart;              /* 0 = none open */
    uint32_t cursize;              /* length of that part */

    int      addressed;            /* mode: see the header comment */

    /* FLAT mode only. start[i] = logical offset of part i's payload,
     * 1-based. Valid for i <= known; start[known] is the total payload
     * seen so far, i.e. where the next unopened part would begin. */
    uint32_t start[UNC_SEG_MAX_PARTS + 2];
    int      known;

    /* Where the walk stops: `total` in flat mode, `last` in addressed
     * mode (where the total is nobody's business and often unknowable
     * — it would take seeing every part). */
    uint32_t total;
    int      last;                 /* highest part that may exist */

    uint32_t off;                  /* ADDRESSED: cursor within curpart */
    uint32_t pos;                  /* FLAT: logical read cursor */
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
    /* Compact Pro next: like StuffIt it decides on a header at offset 0,
     * where the zip scheme has to hunt backwards from the end. Unlike
     * StuffIt, a part that is not the LAST one answers with nparts == 0
     * — it knows the set it belongs to but not how big the set is, and
     * the host is expected to go and find the final segment. */
    err = unc_cptseg_describe(io, desc);
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
    /* Flat mode can only reach a part whose predecessors have been
     * measured; addressed mode may open any part in the set, which is
     * the whole reason it exists. */
    if (!j->addressed && part > j->known) return UNC_ERR_CORRUPT;

    if (j->curpart && part < j->curpart) j->backward++;
    seg_release(j);

    err = j->vs->need(j->vs->ctx, j->desc, part, &j->cur);
    if (err != UNC_OK) {
        /* A part the host could not produce is the ARCHIVE's verdict,
         * not the entry's, however the caller happened to ask for it.
         * Recorded here rather than at each call site: addressed mode
         * reaches this through three of them, and the flat reader's
         * conversion to EOF would otherwise be the only path that
         * remembered. */
        if (err == UNC_ERR_SEGMENTED) j->err = err;
        return err;
    }
    j->curpart = part;
    j->switches++;

    /* A part shorter than its own header carries no payload and would
     * make start[] non-monotonic. */
    size = j->cur.size(j->cur.ctx);
    if (size == UNC_SIZE_UNKNOWN || size < j->desc->head_len) {
        seg_release(j);
        return UNC_ERR_CORRUPT;
    }
    j->cursize = size;
    if (j->addressed) return UNC_OK;
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

/* ------------------------------------------------------------------ */
/* ADDRESSED mode: the (part, offset) pairs the archive itself stores  */
/* ------------------------------------------------------------------ */

/* Position at `off` within `part`, rolling into later parts when `off`
 * runs past the end of one. Rolling is what lets a caller skip a
 * variable-length field — a local header's name and extra — without
 * knowing whether the skip crosses a cut.
 *
 * `head_len` is what a part costs before its payload starts: 0 for a
 * spanned zip, whose parts simply concatenate, and 8 for Compact Pro,
 * where every segment repeats the archive header. Rolling into a part
 * therefore lands on head_len, not on 0 — and getting that wrong is
 * invisible until an entry happens to straddle a cut, which is why the
 * first version passed 9 of 11 entries and failed exactly the two that
 * do (2026-08-14). */
static int seg_seek_part(void *ctx, int part, uint32_t off)
{
    SegJoin *j = (SegJoin *)ctx;
    int err;

    for (;;) {
        err = seg_open(j, part);
        if (err != UNC_OK) return err;
        if (off < j->cursize) break;
        if (part >= j->last) { j->off = j->cursize; return UNC_OK; }  /* EOF */
        off -= j->cursize;
        off += j->desc->head_len;
        part++;
    }
    j->off = off;
    return UNC_OK;
}

static int seg_skip_fwd(void *ctx, uint32_t n)
{
    SegJoin *j = (SegJoin *)ctx;
    if (!j->curpart) return UNC_ERR_IO;
    if (j->off + n < j->off) return UNC_ERR_CORRUPT;   /* 32-bit wrap */
    return seg_seek_part(j, j->curpart, j->off + n);
}

static uint32_t seg_part_size(void *ctx, int part)
{
    SegJoin *j = (SegJoin *)ctx;
    if (seg_open(j, part) != UNC_OK) return UNC_SIZE_UNKNOWN;
    return j->cursize;
}

static int32_t seg_read_addressed(SegJoin *j, void *buf, int32_t len)
{
    uint32_t avail;
    int32_t r;

    if (!j->curpart) { j->err = UNC_ERR_IO; return -1; }

    /* At the end of this part: step into the next one. A short read is
     * allowed by the UncIO contract, so this never has to stitch two
     * parts together within one call. */
    while (j->off >= j->cursize) {
        int err;
        if (j->curpart >= j->last) return 0;           /* end of the set */
        err = seg_open(j, j->curpart + 1);
        if (err == UNC_ERR_SEGMENTED) { j->err = err; return 0; }
        if (err != UNC_OK) { j->err = err; return -1; }
        j->off = j->desc->head_len;      /* past that part's own header */
    }

    avail = j->cursize - j->off;
    if ((uint32_t)len > avail) len = (int32_t)avail;
    if (j->cur.seek(j->cur.ctx, j->off) < 0) { j->err = UNC_ERR_IO; return -1; }
    r = j->cur.read(j->cur.ctx, buf, len);
    if (r < 0) { j->err = UNC_ERR_IO; return -1; }
    j->off += (uint32_t)r;
    return r;
}

static int32_t seg_read(void *ctx, void *buf, int32_t len)
{
    SegJoin *j = (SegJoin *)ctx;
    uint32_t avail;
    int32_t r;
    int err;

    if (len <= 0) return 0;
    if (j->addressed) return seg_read_addressed(j, buf, len);
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
    /* Addressed mode has no flat address space to seek within, and a
     * caller that thinks it does would read the wrong bytes silently.
     * Refuse instead: the reader for this mode positions itself through
     * UncSegMap and never comes here. */
    if (j->addressed) return -1;
    j->pos = pos;               /* lazy: the next read locates the part */
    return 0;
}

static uint32_t seg_tell(void *ctx)
{
    const SegJoin *j = (const SegJoin *)ctx;
    return j->addressed ? j->off : j->pos;
}

static uint32_t seg_size(void *ctx)  { return ((SegJoin *)ctx)->total; }

/* Total bytes across the set, if the host can say so for nothing.
 * Used only to give the progress callback a denominator: on a machine
 * with one drive the answer is genuinely unknowable until every disk
 * has been seen, and finding out is exactly the pass this mode exists
 * to avoid. UNC_SIZE_UNKNOWN is therefore a normal answer, not a
 * failure. */
static uint32_t seg_total_if_free(SegJoin *j)
{
    uint32_t sum = 0;
    int p;

    if (!j->vs->size) return UNC_SIZE_UNKNOWN;
    for (p = 1; p <= j->last; p++) {
        uint32_t s = j->vs->size(j->vs->ctx, j->desc, p);
        if (s == UNC_SIZE_UNKNOWN || sum + s < sum) return UNC_SIZE_UNKNOWN;
        sum += s;
    }
    return sum;
}

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
    if (desc->scheme != UNC_FORMAT_SITSEG && desc->scheme != UNC_FORMAT_ZIPSEG
        && desc->scheme != UNC_FORMAT_SPLIT
        && desc->scheme != UNC_FORMAT_CPTSEG)
        return UNC_ERR_UNSUPPORTED;
    if (desc->nparts > UNC_SEG_MAX_PARTS) return UNC_ERR_UNSUPPORTED;
    /* Neither a size nor a count is a set nobody can tell the end of. */
    if (desc->nparts == 0 && desc->total == UNC_SIZE_UNKNOWN)
        return UNC_ERR_CORRUPT;

    j->desc = desc;
    j->vs = vs;
    j->curpart = 0;
    j->cursize = 0;
    j->addressed = (desc->scheme == UNC_FORMAT_ZIPSEG ||
                    desc->scheme == UNC_FORMAT_CPTSEG);
    j->start[1] = 0;
    j->known = 1;
    j->total = desc->total;
    j->last = desc->nparts ? (int)desc->nparts : UNC_SEG_MAX_PARTS;
    j->off = 0;
    j->pos = 0;
    j->switches = 0;
    j->backward = 0;
    j->err = UNC_OK;
    j->io.ctx = j;
    j->io.read = seg_read;
    j->io.seek = seg_seek;
    j->io.tell = seg_tell;
    j->io.size = seg_size;

    if (j->addressed && j->total == UNC_SIZE_UNKNOWN)
        j->total = seg_total_if_free(j);

    /* A split declares no length anywhere, so the flat walk has nothing
     * to stop at and the emitted entry has no size to announce. The
     * host's part sizes are the only source, and they are free to ask
     * for (a directory lookup). Measuring instead — opening every part
     * before extracting — is the prepass the addressed mode exists to
     * avoid, and on removable media it is a disk swap each. */
    if (desc->scheme == UNC_FORMAT_SPLIT) {
        if (desc->nparts == 0) return UNC_ERR_CORRUPT;
        if (j->total == UNC_SIZE_UNKNOWN) j->total = seg_total_if_free(j);
        if (j->total == UNC_SIZE_UNKNOWN) return UNC_ERR_CORRUPT;
        j->split = *desc;
        j->split.head_len  = 0;      /* a part is payload, all of it */
        j->split.total     = j->total;
        j->split.data_size = j->total;
        j->split.rsrc_size = 0;      /* a split file has one fork */
        j->desc = &j->split;
    }

    map.ctx = j;
    map.seek_part = seg_seek_part;
    map.skip = seg_skip_fwd;
    map.part_size = seg_part_size;
    map.nparts = (uint16_t)j->last;

    c.io = &j->io;
    c.sink = sink;
    c.al = al;
    /* Only in addressed mode, because only there is `nparts` a fact
     * rather than the ceiling the walk happens to have been given. A
     * StuffIt payload is a plain byte stream and nothing reading it
     * asks which part a byte came from. */
    c.segmap = j->addressed ? &map : NULL;
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
    else if (desc->scheme == UNC_FORMAT_CPTSEG)
        ret = unc_cpt_extract(&c);
    else
        ret = unc_sitseg_emit(&c, j->desc, 0);   /* SPLIT: the copy above */
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

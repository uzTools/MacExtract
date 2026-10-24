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

/* ------------------------------------------------------------------ */
/* The join schemes                                                   */
/*                                                                    */
/* One row each, and the ORDER is the order unc_segment_describe tries */
/* them in. Everything that used to be a scheme test in the middle of  */
/* the joiner is a named property here, so adding a sixth scheme is a  */
/* row rather than a search (DECISIONS.md 2026-08-27, the shapes    */
/* that were left).                                                 */
/* ------------------------------------------------------------------ */

#define SEG_HEAD_MAX UNC_SEG_HEAD     /* the longest header a hook reads */

typedef struct SegScheme {
    UncFormat scheme;
    /* The archive stores (part, offset) pairs, so the joiner keeps them
     * as pairs instead of flattening the set. See the file header. */
    uint8_t   addressed;
    /* The joined stream starts with the DATA fork. StuffIt's split puts
     * the resource fork first; DiskDoubler's puts the data fork. */
    uint8_t   data_first;
    /* A part carries no header at all - no identity, no length, not
     * even a magic. The host's names and sizes are the whole map, and
     * the descriptor is the host's to build. */
    uint8_t   anonymous;
    /* Describe the set a file belongs to, or UNC_ERR_FORMAT. NULL for
     * a scheme whose parts carry nothing to read. */
    int      (*describe)(UncIO *io, UncSegmentDesc *desc);
    /* Which part of a set this file is, or 0. NULL where the parts
     * carry no identity - which is not the same as "no", and
     * macextract.h says why. */
    int      (*match)(const UncSegmentDesc *d, const uint8_t *head,
                      int32_t len);
    /* This part's payload length out of its OWN header. NULL means the
     * host's part size is all there is to go on. */
    int      (*payload)(const UncSegmentDesc *d, const uint8_t *head,
                        int32_t len, int part, uint32_t size,
                        uint32_t *out);
    /* The CRC a part stores, checked for free when the stream is read
     * straight through. NULL for none. `crc_fold` is which CRC it is -
     * the two schemes that store one differ - and `crc_runs` is what it
     * covers: 0, the part's own payload (`SPLT`); 1, the payloads of
     * parts 1..this one (StuffIt), so the sum is carried from part to
     * part and the last part's is the whole file's. */
    uint16_t (*stored_crc)(const uint8_t *head);
    uint16_t (*crc_fold)(uint16_t crc, const uint8_t *buf, int32_t len);
    uint8_t   crc_runs;
    /* How many bytes this part spends on its header, when that is not
     * the same for every part of the set. NULL means desc->head_len,
     * which is every scheme but message/partial: mail headers differ
     * in length from part to part, and the hook re-proves the part's
     * identity while it is in there. */
    int      (*hdr)(const UncSegmentDesc *d, UncIO *io, int part,
                    uint32_t size, uint32_t *out);
    uint32_t  head_len;      /* bytes the two hooks above want read */
    /* The reader for a scheme whose parts hold an ARCHIVE. NULL when
     * they join into one FILE, which unc_sitseg_emit writes. */
    int      (*extract)(UncCtx *c);
} SegScheme;

static const SegScheme seg_schemes[] = {
    /* StuffIt first: it decides on 100 bytes at offset 0, where the zip
     * scheme has to hunt backwards from the end of the file. */
    { UNC_FORMAT_SITSEG, 0, 0, 0, unc_sitseg_describe, unc_sitseg_match,
      NULL, unc_sitseg_stored_crc, unc_crc16_arc, 1, NULL, UNC_SEG_HEAD,
      NULL },
    /* Compact Pro next: like StuffIt it decides on a header at offset 0,
     * where the zip scheme has to hunt backwards from the end. Unlike
     * StuffIt, a part that is not the LAST one answers with nparts == 0
     * - it knows the set it belongs to but not how big the set is, and
     * the host is expected to go and find the final segment. */
    { UNC_FORMAT_CPTSEG, 1, 0, 0, unc_cptseg_describe, unc_cptseg_match,
      NULL, NULL, NULL, 0, NULL, 0, unc_cpt_extract },
    /* DiskDoubler's `SPLT`, also decided on a header at offset 0 - and
     * on a second copy of its magic at offset 90, so it is the cheapest
     * of the four to refuse. It is also the only scheme whose parts
     * state their own payload length; its CRC is each part's own, where
     * StuffIt's runs across the set. */
    { UNC_FORMAT_DDSEG, 0, 1, 0, unc_ddseg_describe, unc_ddseg_match,
      unc_ddseg_payload, unc_ddseg_stored_crc, unc_crc16_xmodem, 0, NULL,
      UNC_DDSEG_HEAD, NULL },
    { UNC_FORMAT_ZIPSEG, 1, 0, 0, unc_zipseg_describe, NULL,
      NULL, NULL, NULL, 0, NULL, 0, unc_zip_extract },
    /* message/partial, whose describe() reads a mail header block and
     * is therefore the dearest of them: it goes after every scheme
     * that decides on a magic at offset 0. The parts join into a
     * MESSAGE, so the reader for the joined stream is the MIME walk
     * — no file is emitted in between. */
    { UNC_FORMAT_MIMESEG, 0, 0, 0, unc_mimeseg_describe, NULL,
      NULL, NULL, NULL, 0, unc_mimeseg_head, 0, unc_mime_extract },
    /* SPLIT last and describe-less: a part of a plain NAME.001 split is
     * an anonymous slice of bytes, so nothing here can recognise one.
     * A host that has decided by name builds the descriptor itself. */
    { UNC_FORMAT_SPLIT, 0, 0, 1, NULL, NULL, NULL, NULL, NULL, 0, NULL, 0,
      NULL }
};

static const SegScheme *seg_scheme(UncFormat f)
{
    unsigned i;
    for (i = 0; i < sizeof seg_schemes / sizeof seg_schemes[0]; i++)
        if (seg_schemes[i].scheme == f) return &seg_schemes[i];
    return NULL;
}

typedef struct SegJoin {
    UncIO                 io;      /* what the engine reads through */
    const UncSegmentDesc *desc;
    const SegScheme      *sc;
    UncVolumeSource      *vs;

    /* SPLIT only: the caller's descriptor with the sizes filled in.
     * The joined length is learned here — from the volume source —
     * rather than by the host, and the emitter needs it in a desc.
     * In the scratch block because a 1 MB Mac has 8 KB of stack. */
    UncSegmentDesc        split;

    UncIO    cur;                  /* stream of the open part, if any */
    int      curpart;              /* 0 = none open */
    uint32_t cursize;              /* length of that part */
    uint32_t curhdr;               /* and what its header costs, which is
                                    * desc->head_len for every scheme
                                    * whose parts agree on that */

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

    /* Schemes with a stored CRC: the sum of the payload bytes that have
     * gone past, over the open part (`SPLT`) or over the set so far
     * (StuffIt, crc_runs). Valid only while the stream has been read
     * from where the sum starts with no gap — crc_ok goes to 0 the
     * moment a read starts anywhere else, because the sum can no longer
     * be completed without re-reading, which on a one-drive Mac is a
     * disk swap. See the check in seg_read. */
    uint16_t crc;
    uint32_t crc_pos;
    int      crc_ok;
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
    unsigned i;

    if (!io || !desc) return UNC_ERR_FORMAT;
    for (i = 0; i < sizeof seg_schemes / sizeof seg_schemes[0]; i++)
        if (seg_schemes[i].describe &&
            seg_schemes[i].describe(io, desc) == UNC_OK)
            return UNC_OK;
    return UNC_ERR_FORMAT;
}

int unc_segment_match(const UncSegmentDesc *d,
                      const uint8_t *head, int32_t len)
{
    const SegScheme *sc;

    if (!d || !head) return 0;
    sc = seg_scheme(d->scheme);
    /* A scheme whose parts carry no identity cannot answer this. Said
     * explicitly rather than left to fall out of a failed header parse,
     * because the two outcomes mean opposite things (see macextract.h). */
    if (!sc || !sc->match) return 0;
    return sc->match(d, head, len);
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
    size = unc_io_size32(&j->cur);
    j->curhdr = j->desc->head_len;
    if (j->sc->hdr && size != UNC_SIZE_UNKNOWN) {
        uint32_t h = j->curhdr;
        int e = j->sc->hdr(j->desc, &j->cur, part, size, &h);
        if (e != UNC_OK) { seg_release(j); return e; }
        j->curhdr = h;
    }
    if (size == UNC_SIZE_UNKNOWN || size < j->curhdr) {
        seg_release(j);
        return UNC_ERR_CORRUPT;
    }
    j->cursize = size;
    if (j->addressed) return UNC_OK;
    if (part == j->known) {
        uint32_t payload = size - j->curhdr;
        uint32_t end;
        /* A `SPLT` part declares its own payload length, so the file's
         * size is a bound on it and not a measurement of it — and the
         * same header re-proves that this file belongs to this set and
         * is this part. Every other scheme here has to take what the
         * host handed it. */
        if (j->sc->payload) {
            uint8_t h[SEG_HEAD_MAX];
            int e = unc_read_at(&j->cur, 0, h, (int32_t)j->sc->head_len);
            if (e == UNC_OK)
                e = j->sc->payload(j->desc, h, (int32_t)j->sc->head_len,
                                   part, size, &payload);
            if (e != UNC_OK) { seg_release(j); return e; }
        }
        end = j->start[part] + payload;
        if (end < j->start[part]) { seg_release(j); return UNC_ERR_CORRUPT; }
        j->start[part + 1] = end;
        j->known = part + 1;
        /* A scheme that declares a part COUNT and no byte total knows
         * its length here and nowhere earlier: the last part has just
         * been measured. Without this the flat walk would run off the
         * end of the map and report the set as missing a part, which
         * is what it says when the host cannot produce one. */
        if (j->total == UNC_SIZE_UNKNOWN && part == j->last)
            j->total = end;
    }
    /* A per-part CRC starts afresh with the part, whether it was opened
     * for the first time or re-opened after a backward seek. One that
     * runs across the set is carried over: a re-open leaves it where it
     * was, and the first read at any other offset drops it. */
    if (j->sc->stored_crc && !j->sc->crc_runs) {
        j->crc = 0;
        j->crc_pos = j->start[part];
        j->crc_ok = 1;
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
                    j->curhdr + (j->pos - j->start[j->curpart])) < 0) {
        j->err = UNC_ERR_IO;
        return -1;
    }
    r = j->cur.read(j->cur.ctx, buf, len);
    if (r < 0) { j->err = UNC_ERR_IO; return -1; }

    /* The stored CRC, checked for free when the stream is read straight
     * through — which is what joining a set does, and the ONLY case
     * this can see. A read that starts anywhere but where the running
     * sum stopped abandons it: what follows is then joined unchecked,
     * exactly as the schemes without one are. Each part is judged as
     * its last payload byte goes past, so a bad part is refused before
     * the next disk is asked for; a part with no payload is never read,
     * so never judged, and loses nothing. The last part's payload ends
     * at `total`, whatever its file holds after that. */
    if (j->sc->stored_crc && r > 0) {
        if (j->crc_ok && j->pos == j->crc_pos) {
            uint32_t end = j->start[j->curpart + 1];
            if (end > j->total) end = j->total;
            j->crc = j->sc->crc_fold(j->crc, buf, r);
            j->crc_pos += (uint32_t)r;
            if (j->crc_pos == end) {
                uint8_t h[SEG_HEAD_MAX];
                if (unc_read_at(&j->cur, 0, h,
                                (int32_t)j->sc->head_len) != UNC_OK ||
                    j->sc->stored_crc(h) != j->crc) {
                    j->err = UNC_ERR_CRC;
                    return -1;
                }
            }
        } else {
            j->crc_ok = 0;
        }
    }

    j->pos += (uint32_t)r;
    return r;
}

static int seg_seek(void *ctx, unc_off_t pos)
{
    SegJoin *j = (SegJoin *)ctx;
    /* Addressed mode has no flat address space to seek within, and a
     * caller that thinks it does would read the wrong bytes silently.
     * Refuse instead: the reader for this mode positions itself through
     * UncSegMap and never comes here. */
    if (j->addressed) return -1;
    /* A joined set is addressed in 32 bits: its parts are files a
     * Macintosh could hold, and their sum has never approached the
     * ceiling. A seek past it is a caller error, not a wider set. */
    if (pos > (unc_off_t)UNC_U32_MAX) return -1;
    j->pos = (uint32_t)pos;     /* lazy: the next read locates the part */
    return 0;
}

static unc_off_t seg_tell(void *ctx)
{
    const SegJoin *j = (const SegJoin *)ctx;
    return j->addressed ? j->off : j->pos;
}

/* total is UNC_SIZE_UNKNOWN when the set does not state one; that
 * value survives the widening as UNC_U32_MAX, which unc_io_size32
 * hands back unchanged. */
static unc_off_t seg_size(void *ctx)  { return ((SegJoin *)ctx)->total; }

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
    j->sc = seg_scheme(desc->scheme);
    if (!j->sc) return UNC_ERR_UNSUPPORTED;
    if (desc->nparts > UNC_SEG_MAX_PARTS) return UNC_ERR_UNSUPPORTED;
    /* Neither a size nor a count is a set nobody can tell the end of. */
    if (desc->nparts == 0 && desc->total == UNC_SIZE_UNKNOWN)
        return UNC_ERR_CORRUPT;

    j->desc = desc;
    j->vs = vs;
    j->curpart = 0;
    j->cursize = 0;
    j->curhdr = desc->head_len;
    j->addressed = j->sc->addressed;
    j->start[1] = 0;
    j->known = 1;
    j->total = desc->total;
    j->last = desc->nparts ? (int)desc->nparts : UNC_SEG_MAX_PARTS;
    j->off = 0;
    j->pos = 0;
    j->switches = 0;
    j->backward = 0;
    j->crc = 0;
    j->crc_pos = 0;
    j->crc_ok = 1;                 /* nothing read yet: the sum is whole */
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
    if (j->sc->anonymous) {
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
    c.fmt = UNC_FORMAT_UNKNOWN;     /* no scheme here serves two formats */
    if (opt) c.opt = *opt;
    else { c.opt.list_only = 0; c.opt.test_only = 0;
           c.opt.name_hint = 0; c.opt.name_hint_len = 0; }

    if (j->sc->extract)
        ret = j->sc->extract(&c);
    else
        /* SITSEG, SPLIT (the copy above) and DDSEG all join into one
         * file; only the fork order differs. The joiner's own verdict -
         * a CRC that did not match - reaches the entry through the last
         * argument, since a failed read says only that it failed. */
        ret = unc_sitseg_emit(&c, j->desc, 0, j->sc->data_first, &j->err);
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

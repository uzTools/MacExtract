/*
 * fmt_dart.c — Apple's Disk Archive/Retrieval Tool.
 *
 * DART cuts a floppy into chunks of forty sectors, compresses each one
 * on its own, and puts a table of their lengths in front. It has three
 * methods: "fast" is a word-oriented RLE, "best" is LZHUF, and "not" is
 * no compression at all.
 *
 * WHAT COMES OUT IS ANOTHER DART, and that is the whole shape of this
 * file. Everything else here yields the files somebody put in; a disk
 * image holds a VOLUME, and reading a volume is a file system rather
 * than a codec — which is why disk images are out of scope
 * (OPEN_ITEMS.md, part 1) and why this one is not an exception to that.
 * What a user of these machines does with a DART is mount it, and an
 * UNCOMPRESSED DART mounts: it is forty 512-byte sectors followed by
 * their forty 12-byte tags, chunk after chunk, which a mounter reads as
 * a raw image with a gap. So expanding one is a codec after all, and the
 * output is the same format with method 2 in its header. Fed a file that
 * is ALREADY method 2 there is nothing to do, and saying so is not an
 * error about the file but a statement about it: UNC_ERR_NOTCOMPRESSED,
 * which no other format returns.
 *
 * Sources, and there is no magic number so all of them are needed:
 *
 *   reference/notes/DartIntf.h  Apple's own header, Ken McLeod, 1994,
 *       "provided here for READ-ONLY use": the two record layouts, the
 *       disk and compression identifiers, the file types, and the rule
 *       that a block length is in BYTES except under kRLECompress,
 *       where it is in words, and except -1, which means stored.
 *   reference/ciderpress2/DART-notes.md and DART.cs  the second reading,
 *       and the one that states the RLE word-orientation, the 0xFFFF
 *       per-chunk fallback and which type/size pairs are valid.
 *   reference/ciderpress2/LZHufStream.cs  the LZHUF the "best" method
 *       is: unc_lzah.c's coder with a window of zeros (UNC_LZAH_DART).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* One chunk: forty sectors of 512 (20,480 bytes), then their forty tags
 * of 12 (480 more). Source: DartIntf.h, DDBLOCKSIZE, and the "How DART
 * creates a disk image" note above it. Only the total appears below —
 * nothing here separates a chunk's data from its tags, because what is
 * being written is a DART and not a volume. */
#define DART_CHUNK_BYTES  20960u
/* A length entry of -1: the chunk is stored whole. DartIntf.h, "If the
 * block length is -1, then the block isn't compressed". */
#define DART_STORED       0xFFFFu

/* Header: srcCmp, srcType, srcSize, then the table. Forty entries for a
 * disk up to 800K and seventy-two above it, so 84 bytes or 148.
 * Source: DartIntf.h, SrcInfoRec and HDSrcInfoRec. */
#define DART_SLOTS_SMALL  40u
#define DART_SLOTS_LARGE  72u
#define DART_HDR_MAX      (4u + 2u * DART_SLOTS_LARGE)

/* Compression identifiers, DartIntf.h. */
#define DART_CMP_RLE      0
#define DART_CMP_LZH      1
#define DART_CMP_NONE     2

typedef struct DartHead {
    uint8_t  cmp;
    uint8_t  type;
    uint16_t kb;
    uint16_t slots;        /* 40 or 72 */
    uint16_t hdrlen;       /* 4 + 2 * slots */
    uint16_t blocks;       /* chunks the disk actually occupies */
    uint16_t blen[DART_SLOTS_LARGE];
    uint32_t payload;      /* bytes of chunk data the table accounts for */
    uint32_t maxchunk;     /* the longest of them, which is the buffer   */
} DartHead;

/* ------------------------------------------------------------------ */
/* Header                                                             */
/* ------------------------------------------------------------------ */

/* The type/size pairs a DART may state. There is no signature anywhere
 * in the format, so this table is a third of the identification: the
 * disk identifiers come from DartIntf.h and the sizes each may carry
 * from DART.cs's FormatToKind, which is the only reading that pairs
 * them. `digit` completes the file type DartIntf.h names for that pair.
 *
 * The four pairs FormatToKind accepts and DartIntf.h names no type for
 * — a Lisa 800K, an Apple II 400K, a 720K Macintosh, a 1440K MS-DOS low
 * -density — are not in this table and are not recognized. A DART of a
 * shape Apple's own header has no file type for is a shape DART could
 * not have written, and admitting one would mean inventing the constant
 * it should carry (CLAUDE.md, rule 1). */
static const struct DartKind {
    uint8_t  type;
    uint16_t kb;
    uint8_t  digit;      /* the last character of the file type */
} dart_kinds[] = {
    { 1,   400u, '1' },           /* kMacDisk      'DMd1' Macintosh 400K */
    { 2,   400u, '2' },           /* kLisaDisk     'DMd2' Lisa 400K      */
    { 1,   800u, '3' },           /* kMacDisk      'DMd3' Macintosh 800K */
    { 3,   800u, '4' },           /* kAppleIIDisk  'DMd4' Apple II 800K  */
    { 17,  720u, '5' },           /* kMSDOSLowDD   'DMd5' MS-DOS 720K    */
    { 16, 1440u, '6' },           /* kMacHiDDisk   'DMd6' Macintosh 1.4M */
    { 18, 1440u, '7' }            /* kMSDOSHiDDisk 'DMd7' MS-DOS 1.4M    */
};

/* Every one of those seven is 'DMd' and a digit, so the digit is what
 * the table holds: 28 bytes of the A5 world instead of 56, on a target
 * where data costs the engine's budget one for one (FORMATS.md, *What
 * the application costs the engine*). Each constant is still spelled
 * out beside its row, which is what a reader needs. */
#define DART_TYPE_STEM 0x444D6400u    /* 'DMd\0' */
/* 'DART', the creator every one of them carries. DartIntf.h,
 * kDartCreator. */
#define DART_CREATOR   0x44415254u

static const struct DartKind *dart_kind(uint8_t type, uint16_t kb)
{
    unsigned i;
    for (i = 0; i < sizeof dart_kinds / sizeof dart_kinds[0]; i++)
        if (dart_kinds[i].type == type && dart_kinds[i].kb == kb)
            return &dart_kinds[i];
    return NULL;
}

/* How many bytes chunk `i` occupies in the file, or 0 for a length that
 * cannot be one. Source: DART-notes.md, "The meaning of each block
 * length can depend on the compression type used".
 *
 * The cap is the format's own: DART falls back to storing a chunk whole
 * — marking it 0xFFFF — when compressing it does not pay, so compressed
 * data longer than the chunk it expands to is not something DART wrote.
 * That is enforced HERE rather than in the walk so that identification
 * and extraction agree about what a well-formed table is. */
static uint32_t dart_chunk_bytes(uint8_t cmp, uint16_t blen)
{
    uint32_t n;

    if (cmp == DART_CMP_NONE || blen == DART_STORED) return DART_CHUNK_BYTES;
    n = (cmp == DART_CMP_RLE) ? (uint32_t)blen * 2u : (uint32_t)blen;
    if (n == 0 || n > DART_CHUNK_BYTES) return 0;
    return n;
}

/* Read and check the header out of `head`. Returns UNC_OK, or
 * UNC_ERR_FORMAT for anything that is not a DART header. */
static int dart_parse(const uint8_t *head, int32_t len, DartHead *h)
{
    uint32_t i;

    if (len < 4) return UNC_ERR_FORMAT;
    h->cmp  = head[0];
    h->type = head[1];
    h->kb   = unc_get_u16be(head + 2);
    if (h->cmp > DART_CMP_NONE) return UNC_ERR_FORMAT;
    if (!dart_kind(h->type, h->kb)) return UNC_ERR_FORMAT;

    /* The size decides the table's length and not the other way round.
     * Getting it wrong moves the payload by 64 bytes and yields a
     * volume that reads as noise. DartIntf.h: "you can decide whether
     * to interpret the file header as HDSrcInfoRec or SrcInfoRec". */
    h->slots  = (uint16_t)(h->kb <= 800u ? DART_SLOTS_SMALL : DART_SLOTS_LARGE);
    h->hdrlen = (uint16_t)(4u + 2u * h->slots);
    /* kb/20: a chunk is 20480 bytes, which is 20 KB of the disk. */
    h->blocks = (uint16_t)(h->kb / 20u);
    if (h->blocks == 0 || h->blocks > h->slots) return UNC_ERR_FORMAT;
    if (len < (int32_t)h->hdrlen) return UNC_ERR_FORMAT;

    h->payload = 0;
    h->maxchunk = 0;
    for (i = 0; i < h->slots; i++) {
        uint16_t e = unc_get_u16be(head + 4 + 2 * i);
        h->blen[i] = e;
        /* Entries past the end of the disk are zero, and entries inside
         * it are not: DART-notes.md, and the check DART.cs makes.
         * Neither half is decoration — a table whose unused slots are
         * not zero is something else that got this far. */
        if (i >= h->blocks) {
            if (e != 0) return UNC_ERR_FORMAT;
            continue;
        }
        if (e == 0) return UNC_ERR_FORMAT;
        {
            uint32_t n = dart_chunk_bytes(h->cmp, e);
            if (n == 0) return UNC_ERR_FORMAT;
            h->payload += n;
            if (n > h->maxchunk) h->maxchunk = n;
        }
    }
    return UNC_OK;
}

/* Four bytes and a table of lengths is a weak signature, and the
 * arithmetic is what makes it strong: the chunk sizes the table states
 * have to add up to the rest of the FILE, to the byte. That is the test
 * that settled the format in the first place (a byte-length reading of
 * a real archive came out 300,951 short) and it is what keeps this
 * probe from claiming anything that merely starts with three plausible
 * bytes. All five specimens in reference/ciderpress2/ and the real 1990
 * archive beside them consume to their last byte (TESTING.md, *DART*). */
UncFormat unc_dart_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    DartHead h;
    uint32_t size;

    if (!io) return UNC_FORMAT_UNKNOWN;
    if (dart_parse(head, len, &h) != UNC_OK) return UNC_FORMAT_UNKNOWN;
    size = unc_io_size32(io);
    if (size == UNC_SIZE_UNKNOWN) return UNC_FORMAT_UNKNOWN;
    if (size != (uint32_t)h.hdrlen + h.payload) return UNC_FORMAT_UNKNOWN;
    return UNC_FORMAT_DART;
}

/* ------------------------------------------------------------------ */
/* Output                                                             */
/* ------------------------------------------------------------------ */

/* Staged so the sink sees runs rather than bytes, and so the progress
 * pump has somewhere to fire from: a chunk's DECODE is what takes the
 * time on a 68000, and its input position says nothing about how far
 * through that decode it is. So a chunk's input is charged to the pump
 * only once the chunk is DONE, and the ticks in between come from here,
 * interpolated across that chunk's own input span. `unc_progress_at`
 * exists for exactly this — Arsenic has the same problem for the same
 * reason — and the number the UI sees stays in one unit and stays
 * monotonic. */
typedef struct DartOut {
    UncCtx  *c;
    uint8_t *buf;
    uint32_t cap, n;
    uint32_t base;       /* ps.done at the start of this chunk        */
    uint32_t inlen;      /* the chunk's compressed length             */
    uint32_t produced;   /* output bytes this chunk has made          */
    int      write;      /* 0 under test_only: decode, discard        */
} DartOut;

static int dart_flush(DartOut *o)
{
    if (o->n == 0) return UNC_OK;
    if (o->write &&
        o->c->sink->write(o->c->sink->ctx, UNC_FORK_DATA, o->buf,
                          (int32_t)o->n) < 0)
        return UNC_ERR_SINK;
    o->n = 0;
    /* base + inlen * produced / 20960: monotonic, in the same unit the
     * rest of the archive is counted in, and landing exactly on
     * base + inlen when the chunk ends. Both factors are at most 20960,
     * so the product is under 440 million and stays in 32 bits. */
    return unc_progress_at(&o->c->ps,
                           o->base + o->inlen * o->produced / DART_CHUNK_BYTES);
}

static int dart_put(void *ctx, uint8_t b)
{
    DartOut *o = (DartOut *)ctx;
    o->buf[o->n++] = b;
    o->produced++;
    if (o->n == o->cap) return dart_flush(o);
    return UNC_OK;
}

/* The same, for a run: RLE and a stored chunk both hand over spans. */
static int dart_put_run(DartOut *o, const uint8_t *p, uint32_t n)
{
    while (n) {
        uint32_t take = o->cap - o->n;
        uint32_t i;
        if (take > n) take = n;
        for (i = 0; i < take; i++) o->buf[o->n + i] = p[i];
        o->n += take;
        o->produced += take;
        p += take;
        n -= take;
        if (o->n == o->cap) {
            int err = dart_flush(o);
            if (err != UNC_OK) return err;
        }
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* The two codecs                                                     */
/* ------------------------------------------------------------------ */

/* "Fast": the chunk is a series of big-endian 16-bit words. The first
 * is a signed count of words — positive means that many literal words
 * follow, negative means the next word repeated -count times, and zero
 * cannot occur. Source: DART-notes.md, *Compression*, cross-read
 * against DART.cs's UnpackRLE. */
static int dart_rle(DartOut *o, const uint8_t *in, uint32_t inlen)
{
    uint32_t at = 0;

    while (at < inlen) {
        int32_t count;
        int err = UNC_OK;
        if (inlen - at < 2) return UNC_ERR_CORRUPT;
        count = (int32_t)(int16_t)unc_get_u16be(in + at);
        at += 2;
        if (count > 0) {
            uint32_t n = (uint32_t)count * 2u;
            if (inlen - at < n) return UNC_ERR_CORRUPT;
            if (o->produced + n > DART_CHUNK_BYTES) return UNC_ERR_CORRUPT;
            err = dart_put_run(o, in + at, n);
            at += n;
        } else if (count < 0) {
            uint32_t reps = (uint32_t)(-count), i;
            if (inlen - at < 2) return UNC_ERR_CORRUPT;
            if (o->produced + reps * 2u > DART_CHUNK_BYTES) return UNC_ERR_CORRUPT;
            err = UNC_OK;
            for (i = 0; i < reps && err == UNC_OK; i++)
                err = dart_put_run(o, in + at, 2);
            at += 2;
        } else {
            return UNC_ERR_CORRUPT;         /* "should never be zero" */
        }
        if (err != UNC_OK) return err;
    }
    return UNC_OK;
}

/* "Best": LZHUF with no leading length word and a window of zeros. The
 * length the decoder stops at is the chunk's, which the format states
 * rather than the stream. */
static int dart_lzh(DartOut *o, const uint8_t *in, uint32_t inlen)
{
    UncBufIn bin;
    UncBitIn bi;

    unc_bufin_init_mem(&bin, in, inlen);
    unc_bitin_init(&bi, &bin);
    return unc_lzah_decode(o->c->al, &bi, DART_CHUNK_BYTES, UNC_LZAH_DART,
                           dart_put, o);
}

/* ------------------------------------------------------------------ */
/* Extraction                                                         */
/* ------------------------------------------------------------------ */

/* Read n bytes from the current position, charging the progress pump
 * nothing: a chunk's input is accounted for once the chunk is done, so
 * that the tick this file fires from the DECODE stays monotonic. */
static int dart_read(UncCtx *c, uint8_t *buf, uint32_t n)
{
    while (n) {
        int32_t want = n > UNC_IOBUF ? (int32_t)UNC_IOBUF : (int32_t)n;
        int32_t got = c->io->read(c->io->ctx, buf, want);
        if (got < 0) return UNC_ERR_IO;
        if (got == 0) return UNC_ERR_TRUNCATED;
        buf += got;
        n -= (uint32_t)got;
    }
    return UNC_OK;
}

/* The header of the file being WRITTEN: the same disk, the same table
 * length, method 2, and every used slot marked stored.
 *
 * 0xFFFF rather than 20960, though DART-notes.md says a stored chunk
 * may be marked either way: -1 is what DartIntf.h calls the marker
 * ("If the block length is -1, then the block isn't compressed"), and
 * 20960 is what a reader may also accept. Writing the marker rather
 * than the length says stored in the format's own words. */
static void dart_out_header(const DartHead *h, uint8_t *out)
{
    uint32_t i;

    out[0] = DART_CMP_NONE;
    out[1] = h->type;
    out[2] = (uint8_t)(h->kb >> 8);
    out[3] = (uint8_t)h->kb;
    for (i = 0; i < h->slots; i++) {
        uint16_t v = (uint16_t)(i < h->blocks ? DART_STORED : 0u);
        out[4 + 2 * i]     = (uint8_t)(v >> 8);
        out[4 + 2 * i + 1] = (uint8_t)v;
    }
}

/* `<hint>.dart`, and the extension is the point: both hosts hand over
 * the archive's name minus its LAST one, and what comes out here is a
 * DART again. */
static void dart_name(UncEntryInfo *e, const uint8_t *hint, uint32_t len)
{
    static const uint8_t ext[5] = { '.', 'd', 'a', 'r', 't' };
    uint32_t i, full = len;

    if (len > UNC_NAME_MAX - 5u) len = UNC_NAME_MAX - 5u;
    unc_entry_set_path(e, hint, len);
    for (i = 0; i < 5; i++) e->name[e->name_len + i] = ext[i];
    e->name_len = (uint16_t)(e->name_len + 5u);
    e->name[e->name_len] = 0;
    if (full != len) {
        e->name_truncated = 1;
        e->name_full_len = (uint16_t)(full + 5u > 65535u ? 65535u : full + 5u);
    }
}

int unc_dart_extract(UncCtx *c)
{
    uint8_t hdr[DART_HDR_MAX];
    DartHead h;
    const struct DartKind *k;
    UncEntryInfo e;
    DartOut o;
    uint8_t *chunk = NULL;
    uint32_t chunkcap = 0, i;
    int sret, est = UNC_OK, err = UNC_OK;

    /* The size field decides how long the header is, so it is read
     * first and the header read twice. DartIntf.h: "you can decide
     * whether to interpret the file header as HDSrcInfoRec or
     * SrcInfoRec" from the first two words. */
    if (unc_read_at(c->io, 0, hdr, 4) != UNC_OK) return UNC_ERR_TRUNCATED;
    {
        uint32_t kb = unc_get_u16be(hdr + 2);
        uint32_t want = 4u + 2u * (kb <= 800u ? DART_SLOTS_SMALL
                                              : DART_SLOTS_LARGE);
        if (unc_read_at(c->io, 0, hdr, (int32_t)want) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        if (dart_parse(hdr, (int32_t)want, &h) != UNC_OK)
            return UNC_ERR_FORMAT;
    }

    /* Nothing to do, and that is not a failure of the file. Ahead of
     * every allocation and before the entry exists, so a host sees one
     * verdict about the archive rather than an entry that failed. */
    if (h.cmp == DART_CMP_NONE) return UNC_ERR_NOTCOMPRESSED;

    k = dart_kind(h.type, h.kb);

    unc_entry_clear(&e);
    /* `foo.image` and a name with no extension at all both become
     * `foo.dart`; `foo.dart` becomes `foo.dart`, which collides with the
     * archive in its own directory and is renamed by the host that
     * renames (the Macintosh shell, which reports it) or refused by the
     * one that refuses to overwrite (the CLI). */
    if (c->opt.name_hint && c->opt.name_hint_len)
        dart_name(&e, c->opt.name_hint, c->opt.name_hint_len);
    else
        unc_entry_set_name(&e, (const uint8_t *)"disk.dart", 9);
    e.type      = DART_TYPE_STEM | k->digit;
    e.creator   = DART_CREATOR;
    e.data_size = (uint32_t)h.hdrlen + (uint32_t)h.blocks * DART_CHUNK_BYTES;
    e.rsrc_size = 0;
    e.comp_data_size = (uint32_t)h.hdrlen + h.payload;
    e.method_data    = h.cmp;

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) return UNC_ERR_SINK;
    if (sret > 0) return UNC_OK;            /* not chosen: skipped whole */

    if (c->opt.list_only) {
        if (c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) return UNC_ERR_SINK;
        return UNC_OK;
    }

    /* One chunk in, one staging buffer out. The input side is the
     * LONGEST chunk the table states rather than the 20,960 a chunk may
     * be: the format's cap would make this a constant, and a peak that
     * does not vary with its input is a declared ceiling nobody
     * questioned (CLAUDE.md). On the five archives measured it saves
     * between 0 and 474 B, because every real 800K disk has one chunk
     * that barely compresses — but a disk that is mostly empty has no
     * such chunk, and it is the small machines that would meet one
     * (FORMATS.md, *DART*).
     *
     * The header goes out through the same buffer, so it may not be
     * smaller than that either. */
    chunkcap = h.maxchunk > h.hdrlen ? h.maxchunk : h.hdrlen;
    chunk = (uint8_t *)unc_alloc(c->al, chunkcap + UNC_IOBUF);
    if (!chunk) {
        est = UNC_ERR_MEM;
        goto done;
    }
    o.c = c;
    o.buf = chunk + chunkcap;
    o.cap = UNC_IOBUF;
    o.n = 0;
    o.write = !c->opt.test_only;

    if (c->io->seek(c->io->ctx, h.hdrlen) < 0) {
        est = UNC_ERR_IO;
        goto done;
    }

    /* The output's own header first: same disk, method 2, every slot
     * stored. The input header is charged to the pump here so that
     * `done` ends on the archive's own size rather than 84 bytes short
     * of it. */
    est = unc_progress_add(&c->ps, h.hdrlen);
    if (est != UNC_OK) goto done;
    o.base = c->ps.done;
    o.inlen = 0;
    o.produced = 0;
    dart_out_header(&h, chunk);
    est = dart_put_run(&o, chunk, h.hdrlen);
    o.produced = 0;

    for (i = 0; i < h.blocks && est == UNC_OK; i++) {
        uint32_t n = dart_chunk_bytes(h.cmp, h.blen[i]);

        o.base = c->ps.done;
        o.inlen = n;
        o.produced = 0;
        est = dart_read(c, chunk, n);
        if (est != UNC_OK) break;

        if (h.blen[i] == DART_STORED)
            est = dart_put_run(&o, chunk, DART_CHUNK_BYTES);
        else if (h.cmp == DART_CMP_RLE)
            est = dart_rle(&o, chunk, n);
        else
            est = dart_lzh(&o, chunk, n);

        /* A chunk expands to exactly one chunk. Anything else is a
         * disagreement between the table and the data, which is what
         * corrupt means here — DART.cs throws on the same condition. */
        if (est == UNC_OK && o.produced != DART_CHUNK_BYTES)
            est = UNC_ERR_CORRUPT;
        if (est == UNC_OK) est = dart_flush(&o);
        if (est == UNC_OK) est = unc_progress_add(&c->ps, n);
    }
    if (est == UNC_OK) est = dart_flush(&o);

done:
    unc_free(c->al, chunk);
    if (c->sink->end_entry(c->sink->ctx, est) < 0) err = UNC_ERR_SINK;
    if (unc_fatal(est)) err = est;
    return err;
}

/*
 * fmt_tome.c — the Apple Installer Tome (type 'idcp', creator 'kakc'),
 * the archive Apple's Installer reads its files from, System 7.5 to Mac
 * OS 9.
 *
 * A Tome is a flat list of files: a 0x24-byte header, then one 0x80-byte
 * record per file, then the forks' streams wherever the records say.
 *
 *   header +0x00  u32  magic, "kc" 00 01
 *          +0x1a  u16  the number of records
 *   record +0x06  Str31 the name, MacRoman; the bytes after it are
 *                       whatever was in memory
 *          +0x26  u32  type, +0x2a u32 creator
 *          +0x2e  u32  created, +0x32 u32 modified (1904 seconds)
 *          +0x36  u16  Finder flags
 *          +0x3c  the data fork, +0x4c the resource fork, each four u32:
 *                 its length, its stream's offset in the Tome, the
 *                 stream's length, and a checksum nobody has identified
 *
 * A fork with a stream of length 0 is absent. A fork's stream is one
 * block per 64 KB of output, each opening with 4 bytes: byte 0 = 1 is a
 * stored block, its bytes following; otherwise byte 1 names the codec,
 * 1 InstaCompOne, 0 a second codec for text. A compressed block runs
 * until the output reaches the block's end — its last copy may run past
 * it, and the next block still ends at the next multiple of 64 KB — and
 * the next block starts on the byte after. The window spans the fork; the
 * `mode` below starts at 1 in every block.
 *
 * Both codecs are one grammar of MSB-first tokens: a copy-length code c;
 * if c > 0, or the token before was a literal run shorter than 63, a copy
 * of c + 2 bytes, one more after such a run, from a distance read below;
 * otherwise a literal-count code n and n literals, of 8 bits in
 * InstaCompOne and 7 in the text codec. A distance is one of three forms
 * at a level s, the number of the codec's 11 limits below the output
 * position: '0' + s bits (1 .. 2^s), '10' + s + 2 bits (from 2^s + 1),
 * '11' + L bits (from 5 * 2^s + 1), L the bits of the position less
 * 5 * 2^s rounded up, at least 1 and at most 15 — and in InstaCompOne 11
 * where that difference is 1005 .. 1024. A stream ends where its stated
 * length does: a token that would read past it is padding and is dropped,
 * and output short of the fork's length is zeros.
 *
 * The forks carry no checksum this engine can verify, so a stream that
 * does not end EXACTLY at its stated length — the one test of a wrong
 * table or a damaged stream the format leaves — fails its entry as
 * UNC_ERR_CORRUPT.
 *
 * Source: reference/notes/installer_tome.md, the format as
 * danifunker/rusty-backup issue 109 documents it (`tome-support.zip` v2,
 * fetched by tools/fetch_references.sh), for every fact here — the
 * container, the record, the blocks, the end of a stream, both codecs'
 * tables and level limits, the long field and its exception. The zip's
 * own decoders were neither copied nor run (NOTICE). Its InstaCompOne
 * length and literal-count codes began as maximumspatium's ResDecompress
 * (`InstaCompOne.py`), with the last length code corrected. The
 * exception's lower bound is the document's, not deark's, which widens one
 * position earlier: with deark's, 19 entries of 39 Tomes miss their end
 * (DECISIONS.md 2026-11-10, *the archive the Installer reads*). Graded
 * against deark's Tome module for the stored and InstaCompOne forks and
 * against what Apple's Installer installed for the rest (FORMATS.md,
 * *Apple Installer Tomes*).
 *
 * A RESOURCE FORK holding 'part' resources — each one a Tome of its own,
 * version 2 — is read here too: *Parts*, below.
 *
 * Memory: a ring that is the window and the output's staging at once, as
 * fmt_lz4.c's, sized for each fork before it starts: the window starts
 * afresh with every fork and the record states the fork's length, so the
 * ring is the fork's length rounded up to a power of two, 4 KB at least
 * and 64 KB — what a 43,008-byte reach needs — at most, allocated again
 * only when a fork wants more than the last, and never copied. LZ4's ring
 * doubles as it goes because a frame need not say how long it is; here
 * that cost a 32 KB copy live beside the 64 KB one, 104,480 B where
 * 71,712 B do (DECISIONS.md 2026-11-10, *the archive the Installer
 * reads*). Then one input buffer, and two decoding tables of 1 KB, one
 * per codec, and one of 32 B.
 *
 * Harness: tests/harness/run_tome.py
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_tome_priv.h"

#define TOME_RING  65536u   /* the most the window needs: 43,008 B of reach */
#define TOME_MIN   4096u    /* the least a ring is; a power of two, >= TOME_FLUSH */
#define TOME_REACH 43008u   /* 5 * 2^11 + 2^15: the farthest a copy reaches */
#define TOME_FLUSH 4096u    /* output goes to the sink this often */
#define TOME_BLOCK 65536u   /* a block's share of the output */
#define TOME_LUTW  10       /* the longest copy-length code, in bits */
#define TOME_LITW  5        /* the longest literal-count code */

/* One prefix code: `width` bits equal to `code`, then `extra` bits added
 * to `base`. */
typedef struct {
    uint16_t code;
    uint8_t  width, extra;
    uint16_t base;
} TomeCode;

/* InstaCompOne's copy-length codes (c; the copy is c + 2). */
static const TomeCode tome_len_ic1[] = {
    { 0x000, 2, 0, 0 },    { 0x001, 2, 0, 1 },    { 0x004, 3, 0, 2 },
    { 0x00A, 4, 0, 3 },    { 0x00B, 4, 0, 4 },    { 0x018, 5, 0, 5 },
    { 0x019, 5, 0, 6 },    { 0x034, 6, 0, 7 },    { 0x035, 6, 0, 8 },
    { 0x036, 6, 0, 9 },    { 0x037, 6, 0, 10 },   { 0x00E, 4, 3, 11 },
    { 0x01E, 5, 3, 19 },   { 0x03E, 6, 5, 27 },   { 0x07E, 7, 6, 59 },
    { 0x0FE, 8, 7, 123 },  { 0x1FE, 9, 8, 251 },  { 0x3FE, 10, 9, 507 },
    { 0x3FF, 10, 10, 1019 }
};

/* The text codec's. The two longest are extrapolated in the source and
 * never seen in a stream; they complete the code. */
static const TomeCode tome_len_txt[] = {
    { 0x000, 3, 0, 0 },    { 0x001, 3, 0, 1 },    { 0x002, 3, 0, 2 },
    { 0x003, 3, 0, 3 },    { 0x008, 4, 0, 4 },    { 0x009, 4, 0, 5 },
    { 0x00A, 4, 0, 6 },    { 0x00B, 4, 0, 7 },    { 0x006, 3, 2, 8 },
    { 0x00E, 4, 3, 12 },   { 0x01E, 5, 4, 20 },   { 0x03E, 6, 5, 36 },
    { 0x07E, 7, 6, 68 },   { 0x0FE, 8, 7, 132 },  { 0x1FE, 9, 8, 260 },
    { 0x3FE, 10, 9, 516 }, { 0x3FF, 10, 10, 1028 }
};

/* Literal counts, both codecs. */
static const TomeCode tome_lit[] = {
    { 0x00, 1, 0, 1 },     { 0x04, 3, 0, 2 },     { 0x05, 3, 0, 3 },
    { 0x06, 3, 2, 4 },     { 0x0E, 4, 3, 8 },     { 0x1E, 5, 4, 16 },
    { 0x1F, 5, 5, 32 }
};

#define N_IC1 (sizeof tome_len_ic1 / sizeof tome_len_ic1[0])
#define N_TXT (sizeof tome_len_txt / sizeof tome_len_txt[0])
#define N_LIT (sizeof tome_lit / sizeof tome_lit[0])

/* The level limits: s is how many of these lie below the position. */
static const uint16_t tome_lim_ic1[11] = {
    10, 20, 40, 80, 160, 672, 1000, 2688, 5376, 10752, 21504
};
static const uint16_t tome_lim_txt[11] = {
    10, 20, 40, 80, 160, 320, 832, 1280, 2560, 5120, 10240
};

typedef struct {
    UncCtx   *c;
    UncBufIn  in;
    UncFork   fork;
    uint8_t  *ring;
    uint32_t  cap, mask;
    uint32_t  pos;       /* bytes out of this fork, the overshoot included */
    uint32_t  flushed;   /* how many of them the sink has */
    uint32_t  len;       /* the fork's length */
    /* The bit reader. `taken` counts bytes shifted into `bitbuf`, real
     * and the zeros read past the stream's end; the position in bits is
     * taken * 8 - nbits. */
    uint32_t  bitbuf;
    int32_t   nbits;
    uint32_t  taken, fed, clen;
    uint8_t  *lut_ic1, *lut_txt, *lut_lit;   /* code index per peek */
} Tome;

/* Expand one table into `lut`: for every `w`-bit peek, the row whose
 * code it begins with. 0xFF where none does — none, as the codes are
 * complete, and decode treats one as damage. */
static void tome_lut(uint8_t *lut, int w, const TomeCode *t, uint32_t n)
{
    uint32_t i, k;
    for (i = 0; i < (1u << w); i++) lut[i] = 0xFF;
    for (i = 0; i < n; i++) {
        uint32_t lo = (uint32_t)t[i].code << (w - t[i].width);
        uint32_t span = 1u << (w - t[i].width);
        for (k = 0; k < span; k++) lut[lo + k] = (uint8_t)i;
    }
}

/* Make sure `n` bits are buffered; past the stream's end they are zeros.
 * UNC_OK, or the input's error. */
static int tome_need(Tome *t, int32_t n)
{
    while (t->nbits < n) {
        uint32_t b = 0;
        if (t->fed < t->clen) {
            int v = unc_bufin_next(&t->in);
            if (v < 0) return t->in.err;
            b = (uint32_t)v;
            t->fed++;
        }
        t->bitbuf = (t->bitbuf << 8) | b;
        t->nbits += 8;
        t->taken++;
    }
    return UNC_OK;
}

static uint32_t tome_peek(const Tome *t, int32_t n)
{
    return (t->bitbuf >> (t->nbits - n)) & ((1u << n) - 1u);
}

/* The next `n` bits (n <= 15), or -1 with *err set. */
static int32_t tome_bits(Tome *t, int32_t n, int *err)
{
    uint32_t v;
    if (n == 0) return 0;
    if ((*err = tome_need(t, n)) != UNC_OK) return -1;
    v = tome_peek(t, n);
    t->nbits -= n;
    return (int32_t)v;
}

static uint32_t tome_bitpos(const Tome *t)
{
    return t->taken * 8u - (uint32_t)t->nbits;
}

/* One prefix code through its table, extra bits added. -1 with *err set. */
static int32_t tome_code(Tome *t, const uint8_t *lut, int32_t w,
                         const TomeCode *tab, int *err)
{
    const TomeCode *r;
    int32_t x;
    uint8_t i;
    if ((*err = tome_need(t, w)) != UNC_OK) return -1;
    i = lut[tome_peek(t, w)];
    if (i == 0xFF) { *err = UNC_ERR_CORRUPT; return -1; }
    r = &tab[i];
    t->nbits -= r->width;
    x = tome_bits(t, r->extra, err);
    return x < 0 ? -1 : (int32_t)r->base + x;
}

/* Hand the sink what it has not had, up to the fork's length: the
 * overshoot past it is window only. Every TOME_FLUSH bytes and at the end;
 * ring sizes are multiples of it, so a chunk never straddles the wrap.
 * The ring is at least the fork's length or at least 64 KB, so nothing
 * up to the fork's length is overwritten before it is flushed or out of
 * reach. */
static int tome_flush(Tome *t)
{
    uint32_t end = t->pos < t->len ? t->pos : t->len;
    if (end > t->flushed) {
        if (!t->c->opt.test_only &&
            t->c->sink->write(t->c->sink->ctx, t->fork,
                              t->ring + (t->flushed & t->mask),
                              (int32_t)(end - t->flushed)) < 0)
            return UNC_ERR_SINK;
        t->flushed = end;
    }
    return UNC_OK;
}

/* A ring for a fork of `len`: the fork's length rounded up to a power of
 * two, TOME_MIN at least; past the reach of a copy, all of TOME_RING. The
 * old one goes first — the window does not cross forks — so the most ever
 * held is one ring. */
static int tome_ring(Tome *t, uint32_t len)
{
    uint32_t need = TOME_MIN;
    if (len > TOME_REACH) need = TOME_RING;
    else while (need < len) need <<= 1;
    if (need <= t->cap) return UNC_OK;
    if (t->ring) unc_free(t->c->al, t->ring);
    t->ring = (uint8_t *)unc_alloc(t->c->al, need);
    t->cap = t->ring ? need : 0;
    t->mask = need - 1u;
    return t->ring ? UNC_OK : UNC_ERR_MEM;
}

static int tome_put(Tome *t, uint8_t b)
{
    t->ring[t->pos & t->mask] = b;
    t->pos++;
    if ((t->pos & (TOME_FLUSH - 1u)) == 0) return tome_flush(t);
    return UNC_OK;
}

/* One compressed block, until the output reaches `target`. Sets *ended
 * where a token ran past the stream's end and was dropped. */
static int tome_block(Tome *t, int ic1, uint32_t target, int *ended)
{
    const uint8_t *lut = ic1 ? t->lut_ic1 : t->lut_txt;
    const TomeCode *tab = ic1 ? tome_len_ic1 : tome_len_txt;
    const uint16_t *lim = ic1 ? tome_lim_ic1 : tome_lim_txt;
    uint32_t limit = t->clen * 8u;
    int32_t lb = ic1 ? 8 : 7, s = 0;
    int mode = 1, err = UNC_OK;

    while (t->pos < target && tome_bitpos(t) < limit) {
        int32_t c = tome_code(t, lut, TOME_LUTW, tab, &err);
        if (c < 0) return err;
        if (c > 0 || mode == 0) {
            uint32_t n = (uint32_t)c + 2u + (mode == 0 ? 1u : 0u);
            uint32_t d, near;
            int32_t v;
            while (s < 11 && lim[s] < t->pos) s++;
            v = tome_bits(t, 1, &err);
            if (v < 0) return err;
            if (v == 0) {
                v = tome_bits(t, s, &err);
                d = (uint32_t)v + 1u;
            } else {
                v = tome_bits(t, 1, &err);
                if (v < 0) return err;
                if (v == 0) {
                    v = tome_bits(t, s + 2, &err);
                    d = (uint32_t)v + (1u << s) + 1u;
                } else {
                    int32_t x, w = 1;
                    near = 5u << s;
                    x = (int32_t)(t->pos - near);
                    if (x >= 2)
                        while (w < 15 && (1L << w) < (long)x) w++;
                    if (ic1 && x > 1004 && x <= 1024) w = 11;
                    v = tome_bits(t, w, &err);
                    d = (uint32_t)v + near + 1u;
                }
            }
            if (v < 0) return err;
            if (tome_bitpos(t) > limit) { *ended = 1; return UNC_OK; }
            if (d > t->pos) return UNC_ERR_CORRUPT;
            while (n--) {
                err = tome_put(t, t->ring[(t->pos - d) & t->mask]);
                if (err != UNC_OK) return err;
            }
            mode = 1;
        } else {
            int32_t n = tome_code(t, t->lut_lit, TOME_LITW, tome_lit, &err);
            if (n < 0) return err;
            if (tome_bitpos(t) + (uint32_t)n * (uint32_t)lb > limit) {
                *ended = 1;
                return UNC_OK;
            }
            mode = n < 63 ? 0 : 1;
            while (n--) {
                int32_t b = tome_bits(t, lb, &err);
                if (b < 0) return err;
                err = tome_put(t, (uint8_t)b);
                if (err != UNC_OK) return err;
            }
        }
    }
    return UNC_OK;
}

/* One fork: `clen` stream bytes at `at`, `len` bytes out. */
static int tome_fork(Tome *t, UncFork fork, uint32_t at, uint32_t clen,
                     uint32_t len, uint8_t *ibuf)
{
    uint32_t block_end = 0, consumed;
    int ended = 0, err = UNC_OK;

    if ((err = tome_ring(t, len)) != UNC_OK) return err;
    if (t->c->io->seek(t->c->io->ctx, at) < 0) return UNC_ERR_IO;
    unc_bufin_init(&t->in, t->c->io, &t->c->ps, ibuf, UNC_IOBUF);
    t->in.limit = clen;
    t->fork = fork;
    t->pos = t->flushed = 0;
    t->len = len;
    t->bitbuf = 0;
    t->nbits = 0;
    t->taken = t->fed = 0;
    t->clen = clen;

    while (t->pos < len && tome_bitpos(t) < clen * 8u) {
        uint8_t h[4];
        uint32_t target;
        int k;
        block_end += TOME_BLOCK;
        target = block_end < len ? block_end : len;
        if (tome_bitpos(t) + 32u > clen * 8u) return UNC_ERR_CORRUPT;
        for (k = 0; k < 4; k++) {
            int32_t b = tome_bits(t, 8, &err);
            if (b < 0) return err;
            h[k] = (uint8_t)b;
        }
        if (h[0] == 1) {
            if (t->pos < target) {
                uint32_t n = target - t->pos;
                if (tome_bitpos(t) + n * 8u > clen * 8u)
                    return UNC_ERR_CORRUPT;
                while (n--) {
                    int32_t b = tome_bits(t, 8, &err);
                    if (b < 0) return err;
                    if ((err = tome_put(t, (uint8_t)b)) != UNC_OK) return err;
                }
            }
            continue;
        }
        if (h[1] > 1) return UNC_ERR_UNSUPPORTED;
        err = tome_block(t, h[1], target, &ended);
        if (err != UNC_OK) return err;
        if (ended) break;
        /* The next block starts on a byte: drop the partial one. */
        t->nbits &= ~7;
    }
    consumed = ended ? clen : tome_bitpos(t) / 8u;
    while (t->pos < len)
        if ((err = tome_put(t, 0)) != UNC_OK) return err;
    if ((err = tome_flush(t)) != UNC_OK) return err;
    return consumed == clen ? UNC_OK : UNC_ERR_CORRUPT;
}

/* ------------------------------------------------------------------ */
/* Parts                                                              */
/*                                                                    */
/* A 'part' resource is a Tome of version 2 (the word at 0x10), each  */
/* of whose records is one RESOURCE: +0x06 the id it is meant to have, */
/* +0x08 its type, +0x0c its name (a Pascal string, 65 bytes at most  */
/* before +0x4e), +0x4e one stream as a fork's (its length, offset    */
/* from the part's first byte, the stream's length, a checksum). The  */
/* Installer keeps them in an 'ircp' file's resource fork (QuickDraw   */
/* GX's fonts, AppleTalk's drivers) and in a Tome's own (System 7.5.5's */
/* fonts). What it writes from one is MEASURED: every one of 37 font   */
/* resources and 22 of 32 driver records is this engine's decoding at  */
/* the id the record states, a font given a new id when installed     */
/* (DECISIONS.md 2026-11-11, *what the Installer wrote*).              */
/*                                                                    */
/* So such a fork is read as a set of resource files, rebuilt and      */
/* streamed: every resource kept as it is, every part's records       */
/* expanded under the ids they state — no renumbering, and `STR `      */
/* -16397 and `vers` 2 dropped, the package's and not the font's (the  */
/* maintainer, 2026-11-11). An `iFND` is a FOND whose association      */
/* table names placeholder ids (measured: System 7.5.5's nine are the   */
/* FONDs the Installer writes but for those ids), so each comes out as */
/* a suitcase of its own, FFIL/DMOV, named by the resource: the iFND   */
/* retyped FOND and, for each association entry, the one part record  */
/* of its type (size 0 an 'sfnt', else an 'NFNT') and id whose part's  */
/* own id is of the family — that id mod 32 for an outline, mod 64 for */
/* a bitmap, MEASURED on all 64 parts of System 7.5.5's fonts, each    */
/* matched exactly once (DECISIONS.md 2026-11-11, *the parts the       */
/* Installer expands*). Placeholder ids repeat across families, which  */
/* is why each family is its own file. Everything else is one more     */
/* file, named after the archive (the host's name hint, as the         */
/* Installer names the font it installs), FFIL/DMOV if it holds a FOND  */
/* and rsrc/RSED otherwise — written only when it holds a part's       */
/* record, so a Tome's icons and version alone make nothing. A record  */
/* states no attributes, so its resource has none; its name is the    */
/* record's.                                                          */
/*                                                                    */
/* Source: the resource fork's header, map, type list and reference    */
/* list are Inside Macintosh: More Macintosh Toolbox, "Resource File   */
/* Format" (as src/unc_crypt.c transcribes them); the FOND's 52-byte   */
/* header is FamRec (multiversal's Multiverse.h) and the association   */
/* table after it — a count less one, then size, style and id —        */
/* Inside Macintosh: Text, "The Font Association Table"                */
/* (reference/notes/im_text_fond.txt, fetched by                       */
/* tools/fetch_references.sh). The 'part' layout is DERIVED from the   */
/* specimens, not transcribed: no document of it is known.             */
/*                                                                    */
/* Memory: the map, at most 64 KB; one TomeRes per resource out, at    */
/* most TOME_MAXRES; the names they carry; and the Tome reader's own   */
/* buffers, once.                                                     */
/* ------------------------------------------------------------------ */

#define TOME_MAXRES 1024u
#define TOME_MAPMAX 65536u
#define TOME_IFND 0x69464E44u   /* 'iFND' */
#define TOME_FOND 0x464F4E44u   /* 'FOND' */
#define TOME_SFNT 0x73666E74u   /* 'sfnt' */
#define TOME_NFNT 0x4E464E54u   /* 'NFNT' */
#define TOME_GREST 0xFFFFu      /* the archive's own file */
#define TOME_GDROP 0xFFFEu      /* the package's, not written */
#define TOME_NONAME 0xFFFFu

typedef struct {
    uint32_t type;
    uint32_t at;       /* a plain resource's data, or a record's stream */
    uint32_t len;      /* its bytes out */
    uint32_t clen;     /* a record's stream length; 0 for plain */
    int16_t  id;
    int16_t  pid;      /* a record's part's id */
    uint16_t name;     /* into the names, or TOME_NONAME */
    uint16_t group;    /* the iFND's suitcase, TOME_GREST or TOME_GDROP */
    uint16_t key;      /* the index of its type's first resource */
    uint8_t  attr;
    uint8_t  part;     /* 1: a record */
} TomeRes;

typedef struct {
    UncCtx  *c;
    TomeRes *r;
    uint32_t n;
    uint8_t *names;
    uint32_t nlen, ncap;
} TomeParts;

/* Out of line: the map is a dozen of these, and each inlined is longer
 * than the call. */
static UNC_NOINLINE void tome_put16(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 8);
    p[1] = (uint8_t)v;
}

static UNC_NOINLINE void tome_put32(uint8_t *p, uint32_t v)
{
    tome_put16(p, v >> 16);
    tome_put16(p + 2, v);
}

static int tome_out(UncCtx *c, const uint8_t *p, uint32_t n)
{
    if (c->opt.test_only) return UNC_OK;
    return c->sink->write(c->sink->ctx, UNC_FORK_RSRC, p, (int32_t)n) < 0
           ? UNC_ERR_SINK : UNC_OK;
}

static uint16_t tome_name(TomeParts *P, const uint8_t *s, uint32_t len)
{
    uint32_t at = P->nlen, i;
    if (len == 0) return TOME_NONAME;
    if (len > 255u || at + 1u + len > P->ncap || at + 1u + len > 0xFFFEu)
        return TOME_NONAME;
    P->names[at] = (uint8_t)len;
    for (i = 0; i < len; i++) P->names[at + 1u + i] = s[i];
    P->nlen = at + 1u + len;
    return (uint16_t)at;
}

/* The resources of the map, records expanded; `fill` 0 only counts them
 * (into *n, and the records into *nrec). */
static int tome_parts_scan(TomeParts *P, const uint8_t *map, uint32_t mlen,
                           uint32_t doff, int fill, uint32_t *n,
                           uint32_t *nrec)
{
    UncCtx *c = P->c;
    uint32_t tl = unc_get_u16be(map + 24), nl = unc_get_u16be(map + 26);
    uint32_t nt, i, k, out = 0, recs = 0;

    if (tl + 2u > mlen) return UNC_ERR_CORRUPT;
    nt = (unc_get_u16be(map + tl) + 1u) & 0xFFFFu;
    if (tl + 2u + 8u * nt > mlen) return UNC_ERR_CORRUPT;
    for (i = 0; i < nt; i++) {
        const uint8_t *te = map + tl + 2 + 8 * i;
        uint32_t ty = unc_get_u32be(te), cnt = unc_get_u16be(te + 4) + 1u;
        uint32_t ro = tl + unc_get_u16be(te + 6);
        if (ro + 12u * cnt > mlen) return UNC_ERR_CORRUPT;
        for (k = 0; k < cnt; k++) {
            const uint8_t *ref = map + ro + 12 * k;
            uint32_t at = doff + ((uint32_t)ref[5] << 16 |
                                  unc_get_u16be(ref + 6));
            uint8_t b[TOME_HDR];
            uint32_t len, nr = 1, j;
            if (unc_read_at(c->io, at, b, 4) != UNC_OK)
                return UNC_ERR_TRUNCATED;
            len = unc_get_u32be(b);
            if (ty == TOME_PART) {
                if (len < TOME_HDR ||
                    unc_read_at(c->io, at + 4u, b, (int32_t)TOME_HDR) != UNC_OK)
                    return UNC_ERR_TRUNCATED;
                if (unc_get_u32be(b) != TOME_MAGIC ||
                    unc_get_u16be(b + 0x10) != TOME_PARTVER)
                    return UNC_ERR_UNSUPPORTED;
                nr = unc_get_u16be(b + 0x1a);
                if (nr == 0 || TOME_HDR + nr * TOME_REC > len)
                    return UNC_ERR_CORRUPT;
            }
            if (out + nr > TOME_MAXRES) return UNC_ERR_TOOLARGE;
            if (!fill) {
                out += nr;
                if (ty == TOME_PART) recs += nr;
                continue;
            }
            for (j = 0; j < nr; j++) {
                TomeRes *r;
                if (out >= P->n) return UNC_ERR_CORRUPT;
                r = &P->r[out++];
                r->type = ty;
                r->id = (int16_t)unc_get_u16be(ref);
                r->attr = ref[4];
                r->at = at + 4u;
                r->len = len;
                r->clen = 0;
                r->part = 0;
                r->pid = r->id;
                r->name = TOME_NONAME;
                r->group = TOME_GREST;
                if (ty == TOME_PART) {
                    uint8_t rec[TOME_REC];
                    uint32_t so, sl;
                    if (unc_read_at(c->io, at + 4u + TOME_HDR + j * TOME_REC,
                                    rec, (int32_t)TOME_REC) != UNC_OK)
                        return UNC_ERR_TRUNCATED;
                    r->part = 1;
                    r->attr = 0;
                    r->id = (int16_t)unc_get_u16be(rec + 6);
                    r->type = unc_get_u32be(rec + 8);
                    r->name = tome_name(P, rec + 13,
                                        rec[12] > 65u ? 65u : rec[12]);
                    r->len = unc_get_u32be(rec + 0x4e);
                    so = unc_get_u32be(rec + 0x52);
                    sl = unc_get_u32be(rec + 0x56);
                    if (r->len > UNC_MAC_MAX || so > len || sl > len - so)
                        return UNC_ERR_CORRUPT;
                    r->at = at + 4u + so;
                    r->clen = sl;
                    /* An empty stream is an empty resource. */
                    if (sl == 0) r->len = 0;
                } else {
                    uint32_t no = unc_get_u16be(ref + 2);
                    if (no != 0xFFFFu && nl + no < mlen) {
                        uint32_t sl = map[nl + no];
                        if (nl + no + 1u + sl <= mlen)
                            r->name = tome_name(P, map + nl + no + 1, sl);
                    }
                    /* The package's, not the font's (the maintainer,
                     * 2026-11-11): the Finder's "use the Installer"
                     * message and the package's version. */
                    if ((ty == 0x53545220u && r->id == -16397) ||
                        (ty == 0x76657273u && r->id == 2))
                        r->group = TOME_GDROP;
                }
            }
        }
    }
    *n = out;
    if (nrec) *nrec = recs;
    return UNC_OK;
}

/* Each iFND's family: its own suitcase, number `g`, of the records its
 * association table names. An entry no record answers, or two do, takes
 * none, and those records stay in the archive's own file. */
static int tome_parts_family(TomeParts *P, uint32_t fi, uint16_t g)
{
    UncCtx *c = P->c;
    TomeRes *f = &P->r[fi];
    uint8_t b[6];
    uint32_t na, i, k;

    f->type = TOME_FOND;
    f->group = g;
    if (f->len < 54u) return UNC_OK;
    if (unc_read_at(c->io, f->at + 52u, b, 2) != UNC_OK)
        return UNC_ERR_TRUNCATED;
    na = unc_get_u16be(b) + 1u;
    if (na > TOME_MAXRES || 54u + 6u * na > f->len) return UNC_OK;
    for (i = 0; i < na; i++) {
        uint32_t want, hit = 0, fam;
        int16_t id;
        if (unc_read_at(c->io, f->at + 54u + 6u * i, b, 6) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        want = unc_get_u16be(b) == 0 ? TOME_SFNT : TOME_NFNT;
        id = (int16_t)unc_get_u16be(b + 4);
        for (k = 0; k < P->n; k++) {
            const TomeRes *r = &P->r[k];
            fam = (uint16_t)r->pid & (want == TOME_SFNT ? 31u : 63u);
            if (r->part && r->group == TOME_GREST && r->type == want &&
                r->id == id && fam == ((uint16_t)f->id & 0xFFFFu)) {
                if (hit) { hit = 0; break; }
                hit = k + 1u;
            }
        }
        if (hit) P->r[hit - 1u].group = g;
    }
    return UNC_OK;
}

/* Same types together, each where its first resource was: a stable
 * insertion sort on the index of a type's first resource, so that any
 * one file's resources, read in order, are its map's order. */
static void tome_parts_sort(TomeParts *P)
{
    uint32_t i, k;
    for (i = 0; i < P->n; i++) {
        for (k = 0; k < i && P->r[k].type != P->r[i].type; k++) ;
        P->r[i].key = (uint16_t)k;
    }
    for (i = 1; i < P->n; i++) {
        TomeRes x = P->r[i];
        for (k = i; k > 0 && P->r[k - 1u].key > x.key; k--)
            P->r[k] = P->r[k - 1u];
        P->r[k] = x;
    }
}

/* One resource file: the resources of group `g`, header, data and map,
 * streamed. Same types are together (tome_parts_sort), so the data is in
 * the map's order and every offset is a running sum. */
static int tome_parts_write(TomeParts *P, Tome *t, uint8_t *ibuf,
                            uint16_t g, const uint8_t *name,
                            uint32_t namelen)
{
    UncCtx *c = P->c;
    UncEntryInfo e;
    uint8_t h[16], b[16];
    uint32_t i, k, nr = 0, nt = 0, dlen = 0, nlen = 0, clen = 0, mlen;
    uint32_t refat, at, last = 0, run;
    int fond = 0, est = UNC_OK, sret, pass;

    for (i = 0; i < P->n; i++) {
        const TomeRes *r = &P->r[i];
        if (r->group != g) continue;
        if (nr == 0 || r->type != last) nt++;
        last = r->type;
        nr++;
        for (k = 0; k < i; k++)
            if (P->r[k].group == g && P->r[k].type == r->type &&
                P->r[k].id == r->id)
                est = UNC_ERR_UNSUPPORTED;   /* two of one id: no file */
        /* A resource fork's data offsets are 24 bits. */
        if (r->len > 0xFFFFFBu || dlen > 0xFFFFFBu - r->len)
            est = UNC_ERR_TOOLARGE;
        else
            dlen += 4u + r->len;
        clen += r->part ? r->clen : r->len;
        if (r->name != TOME_NONAME) nlen += 1u + P->names[r->name];
        if (r->type == TOME_FOND) fond = 1;
    }
    mlen = 30u + 8u * nt + 12u * nr + nlen;
    if (mlen - nlen > 0xFFFFu) est = UNC_ERR_TOOLARGE;

    unc_entry_clear(&e);
    if (namelen) unc_entry_set_name(&e, name, namelen);
    e.type = fond ? 0x4646494Cu : 0x72737263u;      /* FFIL, rsrc */
    e.creator = fond ? 0x444D4F56u : 0x52534544u;   /* DMOV, RSED */
    e.data_size = 0;
    e.comp_data_size = 0;
    e.rsrc_size = 256u + dlen + mlen;
    e.comp_rsrc_size = clen;

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) return UNC_ERR_SINK;
    if (sret > 0) return UNC_OK;
    if (c->opt.list_only || est != UNC_OK) goto end;

    /* The header, and the rest of its 256 bytes zeros. */
    tome_put32(h, 256u);
    tome_put32(h + 4, 256u + dlen);
    tome_put32(h + 8, dlen);
    tome_put32(h + 12, mlen);
    if ((est = tome_out(c, h, 16)) != UNC_OK) goto end;
    for (i = 0; i < sizeof b; i++) b[i] = 0;
    for (i = 16; i < 256 && est == UNC_OK; i += 16) est = tome_out(c, b, 16);

    /* The data. */
    for (i = 0; i < P->n && est == UNC_OK; i++) {
        const TomeRes *r = &P->r[i];
        if (r->group != g) continue;
        tome_put32(b, r->len);
        if ((est = tome_out(c, b, 4)) != UNC_OK) break;
        if (r->part) {
            if (r->len)
                est = tome_fork(t, UNC_FORK_RSRC, r->at, r->clen, r->len,
                                ibuf);
        } else if (c->io->seek(c->io->ctx, r->at) < 0) {
            est = UNC_ERR_IO;
        } else {
            est = unc_copy_fork(c, UNC_FORK_RSRC, r->len, ibuf, UNC_IOBUF);
        }
    }

    /* The map: the header again; no handle, file or attributes; the
     * type list's and name list's offsets; the type count less one. */
    if (est == UNC_OK) est = tome_out(c, h, 16);
    if (est == UNC_OK) {
        for (i = 0; i < 8; i++) b[i] = 0;
        b[9] = 28;
        b[8] = 0;
        tome_put16(b + 10, mlen - nlen);
        tome_put16(b + 12, nt - 1u);
        est = tome_out(c, b, 14);
    }
    /* Then pass 0, the type list; pass 1, the references; pass 2, the
     * names. */
    for (pass = 0; pass < 3 && est == UNC_OK; pass++) {
        refat = 2u + 8u * nt;
        at = 0;
        nlen = 0;
        for (i = 0; i < P->n && est == UNC_OK; i++) {
            const TomeRes *r = &P->r[i];
            if (r->group != g) continue;
            if (pass == 0) {
                if (i > 0 && at && r->type == last) continue;
                for (k = i, run = 0; k < P->n; k++)
                    if (P->r[k].group == g) {
                        if (P->r[k].type != r->type) break;
                        run++;
                    }
                tome_put32(b, r->type);
                tome_put16(b + 4, run - 1u);
                tome_put16(b + 6, refat);
                refat += 12u * run;
                last = r->type;
                at = 1;
                est = tome_out(c, b, 8);
            } else if (pass == 1) {
                tome_put16(b, (uint16_t)r->id);
                tome_put16(b + 2, r->name == TOME_NONAME ? 0xFFFFu : nlen);
                tome_put32(b + 4, (uint32_t)r->attr << 24 | at);
                tome_put32(b + 8, 0);
                if (r->name != TOME_NONAME) nlen += 1u + P->names[r->name];
                at += 4u + r->len;
                est = tome_out(c, b, 12);
            } else if (r->name != TOME_NONAME) {
                est = tome_out(c, P->names + r->name, 1u + P->names[r->name]);
            }
        }
    }
end:
    if (c->sink->end_entry(c->sink->ctx, est) < 0) return UNC_ERR_SINK;
    return unc_fatal(est) ? est : UNC_OK;
}

/* A resource fork holding parts, its 16-byte header in `h`. */
static int tome_parts(UncCtx *c, Tome *t, uint8_t *ibuf, const uint8_t *h)
{
    TomeParts P;
    uint8_t *map;
    uint32_t doff = unc_get_u32be(h), moff = unc_get_u32be(h + 4);
    uint32_t mlen = unc_get_u32be(h + 12), n = 0, nrec = 0, i;
    uint16_t g = 0;
    int err, rest = 0;

    if (mlen < TOME_RMAP || mlen > TOME_MAPMAX) return UNC_ERR_FORMAT;
    map = (uint8_t *)unc_alloc(c->al, mlen);
    if (!map) return UNC_ERR_MEM;
    P.c = c;
    P.r = NULL;
    P.names = NULL;
    if (unc_read_at(c->io, moff, map, (int32_t)mlen) != UNC_OK) {
        err = UNC_ERR_TRUNCATED;
        goto out;
    }
    if ((err = unc_progress_add(&c->ps, mlen)) != UNC_OK) goto out;
    if ((err = tome_parts_scan(&P, map, mlen, doff, 0, &n, &nrec)) != UNC_OK)
        goto out;
    if (nrec == 0) { err = UNC_ERR_FORMAT; goto out; }
    P.ncap = mlen + 66u * nrec;
    P.r = (TomeRes *)unc_alloc(c->al, n * (uint32_t)sizeof(TomeRes) + P.ncap);
    if (!P.r) { err = UNC_ERR_MEM; goto out; }
    P.names = (uint8_t *)(P.r + n);
    P.nlen = 0;
    P.n = n;
    if ((err = tome_parts_scan(&P, map, mlen, doff, 1, &n, NULL)) != UNC_OK)
        goto out;
    unc_free(c->al, map);
    map = NULL;

    for (i = 0; i < P.n; i++)
        if (P.r[i].type == TOME_IFND && !P.r[i].part &&
            (err = tome_parts_family(&P, i, g++)) != UNC_OK)
            goto out;
    for (i = 0; i < P.n; i++)
        if (P.r[i].group == TOME_GREST && P.r[i].part) rest = 1;
    tome_parts_sort(&P);

    for (i = 0; i < P.n && err == UNC_OK; i++) {
        const TomeRes *f = &P.r[i];
        if (f->type != TOME_FOND || f->group == TOME_GREST || f->part)
            continue;
        err = tome_parts_write(&P, t, ibuf, f->group,
                               f->name == TOME_NONAME ? NULL
                                   : P.names + f->name + 1,
                               f->name == TOME_NONAME ? 0
                                   : P.names[f->name]);
    }
    if (err == UNC_OK && rest)
        err = tome_parts_write(&P, t, ibuf, TOME_GREST, c->opt.name_hint,
                               c->opt.name_hint ? c->opt.name_hint_len : 0);
out:
    if (map) unc_free(c->al, map);
    if (P.r) unc_free(c->al, P.r);
    return err;
}

int unc_tome_extract(UncCtx *c)
{
    uint8_t r[TOME_REC];
    uint8_t *mem;
    Tome t;
    uint32_t i, n;
    unc_off_t fsize = c->io->size(c->io->ctx);
    int err = UNC_OK;

    if (unc_read_at(c->io, 0, r, 16) != UNC_OK) return UNC_ERR_FORMAT;
    if (unc_get_u32be(r) == TOME_MAGIC) {
        if (unc_read_at(c->io, 0, r, (int32_t)TOME_HDR) != UNC_OK)
            return UNC_ERR_FORMAT;
        n = unc_get_u16be(r + 0x1a);
        if (n == 0) return UNC_ERR_FORMAT;
    } else {
        n = 0;   /* a resource fork: its parts, below */
    }

    /* One block for what never grows: the input buffer and the three
     * tables. The ring is its own, since it does. */
    mem = (uint8_t *)unc_alloc(c->al, UNC_IOBUF + 2u * (1u << TOME_LUTW) +
                                      (1u << TOME_LITW));
    if (!mem) return UNC_ERR_MEM;
    t.c = c;
    t.lut_ic1 = mem + UNC_IOBUF;
    t.lut_txt = t.lut_ic1 + (1u << TOME_LUTW);
    t.lut_lit = t.lut_txt + (1u << TOME_LUTW);
    tome_lut(t.lut_ic1, TOME_LUTW, tome_len_ic1, N_IC1);
    tome_lut(t.lut_txt, TOME_LUTW, tome_len_txt, N_TXT);
    tome_lut(t.lut_lit, TOME_LITW, tome_lit, N_LIT);
    t.ring = NULL;
    t.cap = 0;
    if (n == 0) err = tome_parts(c, &t, mem, r);

    for (i = 0; i < n; i++) {
        UncEntryInfo e;
        uint32_t dlen, doff, dclen, rlen, roff, rclen, owed, before;
        int sret, est = UNC_OK;
        unc_off_t at = TOME_HDR + (unc_off_t)i * TOME_REC;

        if (unc_read_at(c->io, at, r, (int32_t)TOME_REC) != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            break;
        }
        if ((err = unc_progress_add(&c->ps, TOME_REC)) != UNC_OK) break;

        unc_entry_clear(&e);
        unc_entry_path_append(&e, r + 7, r[6] > 31 ? 31u : r[6]);
        e.type = unc_get_u32be(r + 0x26);
        e.creator = unc_get_u32be(r + 0x2a);
        e.create_date = unc_get_u32be(r + 0x2e);
        e.mod_date = unc_get_u32be(r + 0x32);
        e.finder_flags = unc_get_u16be(r + 0x36);
        dlen = unc_get_u32be(r + 0x3c);
        doff = unc_get_u32be(r + 0x40);
        dclen = unc_get_u32be(r + 0x44);
        rlen = unc_get_u32be(r + 0x4c);
        roff = unc_get_u32be(r + 0x50);
        rclen = unc_get_u32be(r + 0x54);
        /* A fork with no stream is absent, whatever its length says. */
        if (dclen == 0) dlen = 0;
        if (rclen == 0) rlen = 0;
        e.data_size = dlen;
        e.comp_data_size = dclen;
        e.rsrc_size = rlen;
        e.comp_rsrc_size = rclen;

        if (dlen > UNC_MAC_MAX || rlen > UNC_MAC_MAX ||
            doff > UNC_U32_MAX - dclen || roff > UNC_U32_MAX - rclen)
            est = UNC_ERR_TOOLARGE;
        else if (fsize != UNC_OFF_UNKNOWN &&
                 ((dclen && doff + dclen > fsize) ||
                  (rclen && roff + rclen > fsize)))
            est = UNC_ERR_TRUNCATED;
        /* The progress the entry owes: its streams, each counted once —
         * by the input buffer as it is read, and the rest after the entry.
         * Setting `done` to where the entry ends, as MAR does, counted the
         * record table a second time: the records are counted as they are
         * read, and that position already holds all of them (measured,
         * `tools/run_ticks.py`: up to 8,049 B past a Tome's end). */
        owed = est == UNC_ERR_TOOLARGE ? 0 : dclen + rclen;
        before = c->ps.done;

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; break; }
        if (sret == 0) {
            if (!c->opt.list_only && est == UNC_OK) {
                if (dclen)
                    est = tome_fork(&t, UNC_FORK_DATA, doff, dclen, dlen, mem);
                if (est == UNC_OK && rclen)
                    est = tome_fork(&t, UNC_FORK_RSRC, roff, rclen, rlen, mem);
            }
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
            if (unc_fatal(est)) { err = est; break; }
        }
        /* What the entry's streams hold and was not read counts too: a
         * fork skipped, listed, or refused (fmt_mar.c says why). */
        if (c->ps.done - before < owed) {
            err = unc_progress_add(&c->ps, owed - (c->ps.done - before));
            if (err != UNC_OK) break;
        }
    }

    if (t.ring) unc_free(c->al, t.ring);
    unc_free(c->al, mem);
    return err;
}

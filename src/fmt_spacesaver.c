/*
 * fmt_spacesaver.c — Aladdin StuffIt SpaceSaver compressed files.
 *
 *   Source: SpaceSaver's own engine, disassembled. Nothing published
 *   describes this format and no other implementation exists — `unar`
 *   and `macunpack` do not know it.
 *
 *     - the container: `SSEn 1` of `StuffIt Engine™`, which ships its
 *       MacsBug symbols. ReadSSHeader @0x644c (84 bytes at offset 0,
 *       the two magics), DefaultSSHeader @0x65c2 (version 3, the field
 *       defaults), UpdateSSHeader @0x6520 (what versions 1 and 2 put
 *       where), mCompressFile @0x549c (which fork's stream is written
 *       first, and the rounding of the file's length), MakeDFile
 *       @0x5b30 and UnDFile @0x5b7e (type, creator, Finder flags),
 *       IsFileCmpressed @0x5262 (how a compressed file is recognised);
 *     - the module interface: ExpandFork @0x5ee6, and the callback
 *       wrappers at the head of every `CMod` resource;
 *     - method 0: `CMod 1` "Default Compressor", XferData @0xee;
 *     - method 4: `CMod 21` "Alg 4 (decompress only)", @0x15a.
 *
 *   DECISIONS.md 2026-08-22 (the layout) and (the codecs) record how
 *   each was read; FORMATS.md tabulates the container.
 *
 * A compressed file keeps its name and its place — SpaceSaver replaces
 * the file in situ — so there is no name in the file and the host's
 * name is the entry's. The data fork holds an 84-byte header, then one
 * compressed stream per fork; the resource fork is emptied.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"
#include "ss_dict.h"

#define SS_HDRLEN   84u
#define SS_MAGIC1   0x53495421u        /* 'SIT!' */
#define SS_MAGIC2   0x44464433u        /* 'DFD3' */
#define SS_STAGE    512u               /* output staging, as elsewhere  */
#define SS_IOBUF    4096u
#define SS_MAXWBITS 16                 /* 64 KB, the largest window the
                                        * module's own arithmetic allows */

/* One fork's record. Two of them sit in the header, data fork first;
 * their OFFSETS decide which stream comes first in the file. */
typedef struct SsFork {
    uint32_t clen;      /* compressed bytes                            */
    uint32_t ulen;      /* original bytes; 0 = the fork is not there   */
    uint32_t off;       /* where its stream starts, from byte 0        */
    uint8_t  pset;      /* which preset dictionary ('PrAm' index)      */
    uint8_t  method;    /* compressor index; bit 7 = the PowerPC build */
} SsFork;

typedef struct SsHead {
    uint32_t version;
    uint32_t flags;
    SsFork   fork[2];   /* [0] data, [1] resource                      */
    uint32_t type, creator;
    uint16_t finder_flags;
} SsHead;

/* Decoder state for one fork. */
typedef struct SsState {
    UncCtx  *c;
    UncFork  fork;
    uint8_t *win;       /* sliding window, circular                    */
    uint32_t wsize;
    uint32_t wpos;      /* where the next produced byte goes           */
    uint32_t history;   /* bytes reachable behind wpos (preset + out)  */
    uint8_t  stage[SS_STAGE];
    uint32_t staged;
} SsState;

/* ------------------------------------------------------------------ */
/* The header                                                          */
/* ------------------------------------------------------------------ */

/* Versions 1 and 2 are read the way the engine reads them: it does not
 * decode them in place but converts them first (UpdateSSHeader @0x6520,
 * which runs for version 1 and 2 only), so that routine IS the old
 * layout. Everything it does not carry over — the offset of the second
 * stream, the parameter-set byte — it computes, so the old shape put
 * the data fork's stream first, always. */
static void ss_parse(const uint8_t *h, SsHead *o)
{
    o->version = unc_get_u32be(h + 8);
    o->flags   = unc_get_u32be(h + 16);
    if (o->version >= 3) {
        int i;
        for (i = 0; i < 2; i++) {
            const uint8_t *r = h + (i ? 36 : 20);
            o->fork[i].clen   = unc_get_u32be(r);
            o->fork[i].ulen   = unc_get_u32be(r + 4);
            o->fork[i].off    = unc_get_u32be(r + 8);
            o->fork[i].pset   = r[12];
            o->fork[i].method = r[13];
        }
        o->type         = unc_get_u32be(h + 52);
        o->creator      = unc_get_u32be(h + 56);
        o->finder_flags = unc_get_u16be(h + 60);
        return;
    }
    o->fork[0].clen   = unc_get_u32be(h + 24);
    o->fork[0].ulen   = unc_get_u32be(h + 32);
    o->fork[0].off    = SS_HDRLEN;
    o->fork[0].pset   = 0;
    o->fork[0].method = h[21];
    o->fork[1].clen   = unc_get_u32be(h + 28);
    o->fork[1].ulen   = unc_get_u32be(h + 36);
    o->fork[1].off    = SS_HDRLEN + o->fork[0].clen;
    o->fork[1].pset   = 0;
    o->fork[1].method = h[21];
    o->type         = unc_get_u32be(h + 40);
    o->creator      = unc_get_u32be(h + 44);
    o->finder_flags = unc_get_u16be(h + 48);
}

static int ss_head_ok(const SsHead *o)
{
    int i;
    if (o->version == 0 || o->version > 3) return 0;
    for (i = 0; i < 2; i++) {
        const SsFork *f = &o->fork[i];
        if (f->clen > 0x7FFFFFFFu || f->ulen > 0x7FFFFFFFu) return 0;
        if (f->ulen == 0) {
            /* SetupAFork @0x53d4 clears the method and the parameter
             * set with the length; a fork that claims neither bytes nor
             * a method is simply absent. */
            if (f->clen != 0) return 0;
            continue;
        }
        if (f->clen == 0) return 0;
        if (f->off < SS_HDRLEN || f->off > 0x7FFFFFFFu) return 0;
        if (f->off + f->clen < f->off) return 0;
        /* The compressor byte is deliberately NOT checked. A file whose
         * method this engine does not know is still a SpaceSaver file
         * and is worth NAMING — the user gets the format instead of
         * *unknown*, and the entry fails on its own (CLAUDE.md; the
         * same bargain LZH gets). The two magics are eight bytes. */
    }
    return 1;
}

int unc_spacesaver_probe(const uint8_t *head, int32_t len)
{
    SsHead o;
    if (len < (int32_t)SS_HDRLEN) return 0;
    if (unc_get_u32be(head) != SS_MAGIC1) return 0;
    if (unc_get_u32be(head + 4) != SS_MAGIC2) return 0;
    /* Version 3 states its own header length and it is always 84;
     * ReadSSHeader reads exactly that many bytes before looking. */
    if (unc_get_u32be(head + 8) >= 3 && unc_get_u32be(head + 12) != SS_HDRLEN)
        return 0;
    ss_parse(head, &o);
    return ss_head_ok(&o);
}

/* ------------------------------------------------------------------ */
/* Output staging and the sliding window                               */
/* ------------------------------------------------------------------ */

static int ss_flush(SsState *s)
{
    UncCtx *c = s->c;
    if (s->staged == 0) return UNC_OK;
    if (!c->opt.test_only && !c->opt.list_only &&
        c->sink->write(c->sink->ctx, s->fork, s->stage,
                       (int32_t)s->staged) < 0)
        return UNC_ERR_SINK;
    s->staged = 0;
    return UNC_OK;
}

static int ss_emit(SsState *s, uint8_t b)
{
    if (s->staged == SS_STAGE) {
        int e = ss_flush(s);
        if (e != UNC_OK) return e;
    }
    s->stage[s->staged++] = b;
    s->win[s->wpos] = b;
    if (++s->wpos == s->wsize) s->wpos = 0;
    if (s->history < s->wsize) s->history++;
    return UNC_OK;
}

/* The window starts loaded with a preset dictionary, and that is not
 * optional: @0x280 copies the engine's 'PrAm' resource into the bytes
 * immediately BEFORE the first output byte, so a match at a short
 * distance reads Aladdin's table rather than anything in the file. The
 * encoder places it identically (`CMod 20` @0x93e), which is where that
 * reading was confirmed.
 *
 * Both tables are carried in ss_dict.h — they are Aladdin's, and NOTICE
 * says so — because without the exact bytes a file decodes to something
 * wrong rather than to nothing. The record's byte at +12 chooses; a
 * caller may override the choice with UncOptions.preset, which is how a
 * table this build does not have could still be used. */
static void ss_preset(SsState *s, const uint8_t *p, uint32_t len)
{
    uint32_t k;
    if (len > s->wsize) {
        p += len - s->wsize;
        len = s->wsize;
    }
    for (k = 0; k < len; k++)
        s->win[(s->wsize - len + k) % s->wsize] = p[k];
    s->wpos = 0;
    s->history = len;
}

/* ------------------------------------------------------------------ */
/* Method 4 — "Alg 4", `CMod 21` @0x15a                                */
/*                                                                     */
/* Three bytes of stream header, then that many blocks; each block is a */
/* 6-byte header and a bit stream, LSB first within each byte:          */
/*                                                                      */
/*   1        a literal follows in the next 8 bits              @0x47a  */
/*   0        a 5-bit length and a wbits-bit distance follow;   @0x48e  */
/*            the copy is 4 + length bytes long                 @0x4ae  */
/*                                                                      */
/* The window slides across the whole fork rather than resetting per    */
/* block: the reference compacts it at @0x438 and keeps decoding.       */
/* ------------------------------------------------------------------ */

static int ss_alg4(SsState *s, const SsFork *f, uint8_t *iobuf,
                   uint32_t iocap)
{
    UncCtx *c = s->c;
    UncBufIn in;
    uint32_t nblocks, produced = 0, consumed = 3;
    int wbits, b, i;

    if (c->io->seek(c->io->ctx, f->off) < 0) return UNC_ERR_IO;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = f->clen;

    if (f->clen < 3) return UNC_ERR_TRUNCATED;
    nblocks = 0;
    for (i = 0; i < 2; i++) {                     /* u16, low byte first */
        if ((b = unc_bufin_next(&in)) < 0) return in.err;
        nblocks |= (uint32_t)b << (8 * i);
    }
    if ((b = unc_bufin_next(&in)) < 0) return in.err;
    wbits = b;
    if (wbits < 1 || wbits > SS_MAXWBITS) return UNC_ERR_UNSUPPORTED;

    s->wsize = 1u << wbits;
    s->win = (uint8_t *)unc_alloc(c->al, s->wsize);
    if (!s->win) return UNC_ERR_MEM;
    s->wpos = 0;
    s->history = 0;
    if (c->opt.preset && c->opt.preset_len)
        ss_preset(s, c->opt.preset, c->opt.preset_len);
    else if (f->pset == 0)
        ss_preset(s, ss_dict0, SS_DICT0_LEN);
    else if (f->pset == 1)
        ss_preset(s, ss_dict1, SS_DICT1_LEN);
    else
        /* A table this build does not have. Refusing is the only honest
         * answer: decoding with the wrong dictionary produces bytes
         * that look like a file and are not one. */
        return UNC_ERR_UNSUPPORTED;

    while (nblocks-- > 0) {
        uint32_t clen = 0, ulen = 0, endpos;
        UncBitIn bi;

        for (i = 0; i < 3; i++) {
            if ((b = unc_bufin_next(&in)) < 0) goto ioerr;
            clen |= (uint32_t)b << (8 * i);
        }
        for (i = 0; i < 3; i++) {
            if ((b = unc_bufin_next(&in)) < 0) goto ioerr;
            ulen |= (uint32_t)b << (8 * i);
        }
        consumed += 6;
        /* @0x4e8 subtracts clen from the byte count it holds STARTING
         * at the block header, so the six bytes above are part of it. */
        if (clen < 6u) return UNC_ERR_CORRUPT;
        if (clen - 6u > f->clen - consumed) return UNC_ERR_CORRUPT;
        if (ulen > f->ulen - produced) return UNC_ERR_CORRUPT;
        endpos = produced + ulen;

        unc_bitin_init_le(&bi, &in);
        while (produced < endpos) {
            int32_t v;
            uint32_t dist, n;

            if ((v = unc_bitin_bit(&bi)) < 0) { in.err = bi.err; goto ioerr; }
            if (v) {
                if ((v = unc_bitin_bits_le(&bi, 8)) < 0) { in.err = bi.err; goto ioerr; }
                if ((v = ss_emit(s, (uint8_t)v)) != UNC_OK) return v;
                produced++;
                continue;
            }
            if ((v = unc_bitin_bits_le(&bi, 5)) < 0) { in.err = bi.err; goto ioerr; }
            n = (uint32_t)v + 4u;                 /* @0x4ae: four, then L */
            if ((v = unc_bitin_bits_le(&bi, wbits)) < 0) { in.err = bi.err; goto ioerr; }
            dist = (uint32_t)v;
            if (dist == 0 || dist > s->history) return UNC_ERR_CORRUPT;
            if (n > endpos - produced) return UNC_ERR_CORRUPT;
            while (n-- > 0) {
                uint8_t byte = s->win[(s->wpos + s->wsize - dist) % s->wsize];
                int e = ss_emit(s, byte);
                if (e != UNC_OK) return e;
                produced++;
            }
        }
        /* Whatever bits are left over belong to the block's padding;
         * the next block starts at a byte boundary clen bytes on. */
        consumed += clen - 6u;
        if (c->io->seek(c->io->ctx, f->off + consumed) < 0) return UNC_ERR_IO;
        unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
        in.limit = f->clen - consumed;
    }
    if (produced != f->ulen) return UNC_ERR_CORRUPT;
    return ss_flush(s);

ioerr:
    return in.err != UNC_OK ? in.err : UNC_ERR_TRUNCATED;
}

/* ------------------------------------------------------------------ */
/* Method 0 — stored, `CMod 1` XferData @0xee: read, write, repeat.    */
/* ------------------------------------------------------------------ */

static int ss_stored(SsState *s, const SsFork *f)
{
    UncCtx *c = s->c;
    uint32_t left = f->ulen, at = f->off;

    if (f->clen != f->ulen) return UNC_ERR_CORRUPT;
    while (left > 0) {
        uint32_t take = left < SS_STAGE ? left : SS_STAGE;
        if (unc_read_at(c->io, at, s->stage, (int32_t)take) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        s->staged = take;
        if (ss_flush(s) != UNC_OK) return UNC_ERR_SINK;
        if (unc_progress_add(&c->ps, take) != UNC_OK) return UNC_ERR_ABORTED;
        at += take;
        left -= take;
    }
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* One fork, and the file                                              */
/* ------------------------------------------------------------------ */

static int ss_one_fork(SsState *s, const SsFork *f, uint8_t *iobuf,
                       uint32_t iocap)
{
    int err;
    unsigned m = f->method & 0x7Fu;   /* bit 7 only says which build of
                                       * the module wrote it (@0x578e) */
    s->win = 0;
    s->staged = 0;
    switch (m) {
    case 0:  err = ss_stored(s, f); break;
    case 4:  err = ss_alg4(s, f, iobuf, iocap); break;
    /* 1 "Original Fast", 2 "Original Slow" and 3 "Alg 3" are declined
     * per entry: their modules are in the software this was read out
     * of, but nothing reachable here writes them, so an implementation
     * could not be graded. The bargain LZH and DiskDoubler's declined
     * methods already make (OPEN_ITEMS.md). */
    default: err = UNC_ERR_UNSUPPORTED; break;
    }
    if (s->win) {
        unc_free(s->c->al, s->win);
        s->win = 0;
    }
    return err;
}

int unc_spacesaver_extract(UncCtx *c)
{
    uint8_t hdr[SS_HDRLEN];
    SsHead h;
    SsState s;
    UncEntryInfo e;
    uint8_t *iobuf;
    int sret, err = UNC_OK, ferr = UNC_OK;

    if (unc_read_at(c->io, 0, hdr, (int32_t)SS_HDRLEN) != UNC_OK)
        return UNC_ERR_TRUNCATED;
    if (!unc_spacesaver_probe(hdr, (int32_t)SS_HDRLEN)) return UNC_ERR_FORMAT;
    ss_parse(hdr, &h);

    unc_entry_clear(&e);
    if (c->opt.name_hint && c->opt.name_hint_len)
        unc_entry_set_path(&e, c->opt.name_hint, c->opt.name_hint_len);
    else
        unc_entry_set_name(&e, (const uint8_t *)"spacesaver", 10);
    e.data_size    = h.fork[0].ulen;
    e.rsrc_size    = h.fork[1].ulen;
    e.type         = h.type;
    e.creator      = h.creator;
    e.finder_flags = h.finder_flags;

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) return UNC_ERR_SINK;
    if (sret == 0) {
        if (!c->opt.list_only) {
            iobuf = (uint8_t *)unc_alloc(c->al, SS_IOBUF);
            if (!iobuf) {
                ferr = UNC_ERR_MEM;
            } else {
                int i;
                s.c = c;
                for (i = 0; i < 2 && ferr == UNC_OK; i++) {
                    if (h.fork[i].ulen == 0) continue;
                    s.fork = i ? UNC_FORK_RSRC : UNC_FORK_DATA;
                    ferr = ss_one_fork(&s, &h.fork[i], iobuf, SS_IOBUF);
                }
                unc_free(c->al, iobuf);
            }
        }
        if (c->sink->end_entry(c->sink->ctx, ferr) < 0) err = UNC_ERR_SINK;
        else if (ferr == UNC_ERR_SINK || ferr == UNC_ERR_ABORTED ||
                 ferr == UNC_ERR_IO) err = ferr;
    }
    return err;
}

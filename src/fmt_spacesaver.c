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
 *     - method 1: `CMod 3` "Original Fast Compressor", @0x156 for the
 *       block framing and @0x634 for the codec;
 *     - method 2: `CMod 4` "Original Slow Compressor", @0x136 and
 *       @0x6e8 — the same framing, a different codec;
 *     - method 3: `CMod 11` "Alg 3 (decompress only)", @0x1134 for the
 *       blocks, @0xe26 for the code lengths, @0x15a and @0x27c for the
 *       code assignment, @0x1a04 for the base tables;
 *     - method 4: `CMod 21` "Alg 4 (decompress only)", @0x15a.
 *
 *   Methods 1, 2 and 3 were declined per entry until 2026-08-25 for
 *   want of anything that writes them; `tools/ssmodule/` runs the
 *   modules' own compressors under qemu-m68k, which is what grades
 *   them now (TESTING.md).
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
#define SS_IOBUF    4096u
#define SS_MAXWBITS 16                 /* 64 KB, the largest window the
                                        * module's own arithmetic allows */

struct SsA3;

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
    UncForkOut out;     /* the sink, the fork, and the staging buffer  */
    uint8_t  sbuf[UNC_STAGE];
    uint8_t *win;       /* sliding window, circular                    */
    uint32_t wsize;
    uint32_t wmask;     /* wsize - 1: wsize is 1 << wbits, but it is a
                         * RUNTIME value, so gcc cannot turn the two
                         * circular `%` below into a mask and emits a
                         * call to __umodsi3 — once per copied byte on a
                         * machine with no divide instruction at all   */
    uint32_t wpos;      /* where the next produced byte goes           */
    uint32_t history;   /* bytes reachable behind wpos (preset + out)  */
    uint32_t produced;  /* method 2 only: the cursor its table indexes */
    struct SsA3 *a3;    /* method 3 only: its tables, all one allocation */
    uint32_t *m2tab;    /* method 2 only: 4,096 positions, or UNSET    */
    uint32_t m2slot;    /* method 2 only: the rotating slot, 0..7      */
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
         * same bargain StuffIt X gets). The two magics are eight
         * bytes. */
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

/* One decoded byte: staged for the sink, and into the sliding window.
 * The staging half is shared (unc_fork_put); the window is SpaceSaver's
 * own and is why this is not just a call to it. */
static int ss_emit(SsState *s, uint8_t b)
{
    int e = unc_fork_put(&s->out, b);
    if (e != UNC_OK) return e;
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
        s->win[(s->wsize - len + k) & s->wmask] = p[k];
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
    UncCtx *c = s->out.c;
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
    s->wmask = s->wsize - 1u;
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
                uint8_t byte = s->win[(s->wpos + s->wsize - dist) & s->wmask];
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
    return unc_fork_flush(&s->out);

ioerr:
    return in.err != UNC_OK ? in.err : UNC_ERR_TRUNCATED;
}

/* ------------------------------------------------------------------ */
/* Methods 1 and 2 — the "Original" compressors' block framing         */
/*                                                                     */
/* `CMod 3` @0x156 and `CMod 4` @0x136 are the same loop: read an       */
/* 8-byte block header, read the payload it declares, decode it, write  */
/* it out, and go round until the fork's declared length has been       */
/* produced. The header is four bytes whose FIRST says "this block is   */
/* stored" (@0x1b6 compares it with 1 and skips the decoder), then the  */
/* payload's length as a 32-bit big-endian value (@0x19a reads it and   */
/* asks for exactly that many bytes).                                   */
/*                                                                      */
/* The block's own output buffer is reused block after block (@0x202    */
/* writes it out and the next call starts at the same address), so a    */
/* match reaches back at most as far as this decoder's window does.     */
/* ------------------------------------------------------------------ */

#define SS_ORIG_HDR   8u
#define SS_ORIG_WBITS 12               /* the distance field's width */

/* Method 1 — "Original Fast", `CMod 3` @0x634.
 *
 * Sixteen flags in a little-endian 16-bit word, used LSB first
 * (@0x8c8 `lsrw #1` then `bcc` to the literal). A clear bit is a
 * literal byte; a set bit is two more bytes B1 B2, and @0x672 splits
 * them as
 *
 *     length   = (B1 & 0x0F) + 3        two copies then a dbf loop
 *     distance = ((B1 & 0xF0) << 4) | B2
 *
 * — the high nibble of B1 carries the distance's top four bits, which
 * is why the second `moveb` at @0x67e lands INSIDE the shifted value
 * rather than beside it. The copy is byte at a time and may overlap.
 * The block ends when the payload is exactly consumed (@0x8b4 compares
 * the two pointers for equality before every item). */
static int ss_orig1(SsState *s, UncBufIn *in, uint32_t plen,
                    uint32_t *produced, uint32_t room)
{
    uint32_t flags = 0, nflags = 0, left = plen;
    int b1, b2, e;

    while (left > 0) {
        if (nflags == 0) {
            if (left < 2) return UNC_ERR_CORRUPT;
            if ((b1 = unc_bufin_next(in)) < 0) return in->err;
            if ((b2 = unc_bufin_next(in)) < 0) return in->err;
            flags = (uint32_t)b1 | ((uint32_t)b2 << 8);
            nflags = 16;
            left -= 2;
            continue;
        }
        nflags--;
        if ((flags & 1u) == 0) {                  /* a literal */
            flags >>= 1;
            if ((b1 = unc_bufin_next(in)) < 0) return in->err;
            left--;
            if (*produced == room) return UNC_ERR_CORRUPT;
            if ((e = ss_emit(s, (uint8_t)b1)) != UNC_OK) return e;
            (*produced)++;
            continue;
        }
        flags >>= 1;
        if (left < 2) return UNC_ERR_CORRUPT;
        if ((b1 = unc_bufin_next(in)) < 0) return in->err;
        if ((b2 = unc_bufin_next(in)) < 0) return in->err;
        left -= 2;
        {
            uint32_t n = (uint32_t)(b1 & 0x0F) + 3u;
            uint32_t dist = ((uint32_t)(b1 & 0xF0) << 4) | (uint32_t)b2;
            /* The reference would happily subtract a distance that
             * reaches behind everything it has produced and copy the
             * previous block's leftovers, or in the first block the
             * work buffer's uninitialised bytes. That is not a
             * decodable file, so it is a per-entry error here. */
            if (dist == 0 || dist > s->history) return UNC_ERR_CORRUPT;
            if (n > room - *produced) return UNC_ERR_CORRUPT;
            while (n-- > 0) {
                uint8_t byte =
                    s->win[(s->wpos + s->wsize - dist) & s->wmask];
                if ((e = ss_emit(s, byte)) != UNC_OK) return e;
                (*produced)++;
            }
        }
    }
    return UNC_OK;
}

/* Method 2 — "Original Slow", `CMod 4` @0x6e8.
 *
 * The same flag bits and the same two bytes per match, and then it
 * diverges: those twelve bits are not a distance but an INDEX into a
 * table of 4,096 positions the decoder maintains alongside the encoder
 * (@0x81a scales the code by four and loads a pointer out of the work
 * buffer). The table is 512 buckets of 8, and both sides fill it with
 * the same three-byte hash of the output they have just produced:
 *
 *     h = (((p[1] + p[2]) & 0xFF) + 2 * ((p[0] + p[2]) & 0xFF)) & 511
 *
 * — the two additions are 8-bit and the doubling is not (@0x83c..0x848,
 * `addb`, `addb`, `addw`). An entry goes at `h * 8 + slot`, where slot
 * is one rotating counter shared by the whole table (@0x85a, `andl` with
 * 7). Three insertions exist, and getting any of them out of step
 * desynchronises every later code:
 *
 *   - after every THIRD consecutive literal, the three bytes that end
 *     at the output cursor (@0x8b6), leaving the counter at 2 so the
 *     next literal inserts again one byte along;
 *   - before a match, whatever literals are pending: one at
 *     `out - pending`, and a second one byte later when exactly two
 *     were pending (@0x85e subtracts 2 and tests, so 1 and 3 do not);
 *   - after a match, the position the copy STARTED at, into the same
 *     bucket the code named — `code & ~7` plus the rotating slot
 *     (@0x88e).
 *
 * A code whose entry was never filled points at the module's own last
 * eighteen bytes, `"     \xa91991 Aladdin"` (@0x6fc fills all 4,096
 * entries with that address), and **the compressor does emit such
 * codes** — five of the eight subjects in `tools/ssmodule/`'s sweep
 * reach one, so this is not a theoretical branch. They are carried in
 * `ss_dict.h` beside the preset dictionary, on the same terms and for
 * the same reason: without them the file decodes to something wrong
 * rather than to nothing. The longest match the format can ask for is
 * eighteen bytes, which is why the string is that long.
 */
#define SS_M2_ENTRIES 4096u
#define SS_M2_UNSET   0xFFFFFFFFu
#define SS_M2_WBITS   16               /* the block's own output, ring-buffered */

static uint32_t ss_m2_hash(SsState *s, uint32_t pos)
{
    /* The three bytes at `pos`, which are always within reach: every
     * insertion names a position at most two bytes behind the cursor. */
    uint32_t d = s->produced - pos;
    uint32_t i = (s->wpos + s->wsize - d) & s->wmask;
    uint32_t b0 = s->win[i];
    uint32_t b1 = s->win[(i + 1) & s->wmask];
    uint32_t b2 = s->win[(i + 2) & s->wmask];
    return (((b1 + b2) & 0xFFu) + 2u * ((b0 + b2) & 0xFFu)) & 511u;
}

static void ss_m2_insert(SsState *s, uint32_t index, uint32_t pos)
{
    s->m2tab[index & (SS_M2_ENTRIES - 1u)] = pos;
    s->m2slot = (s->m2slot + 1u) & 7u;
}

static int ss_orig2(SsState *s, UncBufIn *in, uint32_t plen,
                    uint32_t *produced, uint32_t room)
{
    uint32_t flags = 1, left = plen, pending = 0;
    int b1, b2, e;

    for (b1 = 0; b1 < (int)SS_M2_ENTRIES; b1++) s->m2tab[b1] = SS_M2_UNSET;
    s->m2slot = 0;

    while (left > 0) {
        /* The sentinel is tested ONCE per item, at the loop head
         * (@0x7de), and the item that follows a reload is decoded
         * without testing it again — which matters, because a flag
         * word of exactly 0x0001 looks like an exhausted one. Testing
         * again there costs 16 items every time such a word appears,
         * and the output stays right until the first of them is a
         * match. */
        if ((flags & 0xFFFFu) == 1u) {
            if (left < 2) return UNC_ERR_CORRUPT;
            if ((b1 = unc_bufin_next(in)) < 0) return in->err;
            if ((b2 = unc_bufin_next(in)) < 0) return in->err;
            flags = (uint32_t)b1 | ((uint32_t)b2 << 8) | 0x10000u;
            left -= 2;
            if (left == 0) break;                 /* @0x7d8 checks first */
        }
        if ((flags & 1u) == 0) {                  /* a literal */
            flags >>= 1;
            if ((b1 = unc_bufin_next(in)) < 0) return in->err;
            left--;
            if (*produced == room) return UNC_ERR_CORRUPT;
            if ((e = ss_emit(s, (uint8_t)b1)) != UNC_OK) return e;
            (*produced)++;
            s->produced = *produced;
            if (++pending == 3u) {
                uint32_t at = *produced - 3u;
                ss_m2_insert(s, ss_m2_hash(s, at) * 8u + s->m2slot, at);
                pending = 2u;
            }
            continue;
        }
        flags >>= 1;
        if (left < 2) return UNC_ERR_CORRUPT;
        if ((b1 = unc_bufin_next(in)) < 0) return in->err;
        if ((b2 = unc_bufin_next(in)) < 0) return in->err;
        left -= 2;
        {
            uint32_t start = *produced;
            uint32_t n = (uint32_t)(b1 & 0x0F) + 3u;
            uint32_t code = ((uint32_t)(b1 & 0xF0) << 4) | (uint32_t)b2;
            uint32_t src = s->m2tab[code], dist;

            if (src == SS_M2_UNSET) {
                /* Out of the module's own tail, byte by byte, exactly
                 * as the reference's pointer walks it. */
                uint32_t k;
                if (n > room - start) return UNC_ERR_CORRUPT;
                if (n > SS_M2_DEFAULT_LEN) return UNC_ERR_CORRUPT;
                for (k = 0; k < n; k++) {
                    if ((e = ss_emit(s, ss_m2_default[k])) != UNC_OK) return e;
                    (*produced)++;
                }
                s->produced = *produced;
                if (pending > 0) {
                    uint32_t at = start - pending;
                    ss_m2_insert(s, ss_m2_hash(s, at) * 8u + s->m2slot, at);
                    if (pending == 2u)
                        ss_m2_insert(s,
                                     ss_m2_hash(s, at + 1u) * 8u + s->m2slot,
                                     at + 1u);
                    pending = 0;
                }
                ss_m2_insert(s, (code & ~7u) + s->m2slot, start);
                continue;
            }
            if (src > start) return UNC_ERR_CORRUPT;
            dist = start - src;
            if (dist == 0 || dist > s->history) return UNC_ERR_CORRUPT;
            if (n > room - start) return UNC_ERR_CORRUPT;
            while (n-- > 0) {
                uint8_t byte =
                    s->win[(s->wpos + s->wsize - dist) & s->wmask];
                if ((e = ss_emit(s, byte)) != UNC_OK) return e;
                (*produced)++;
            }
            s->produced = *produced;
            if (pending > 0) {
                uint32_t at = start - pending;
                ss_m2_insert(s, ss_m2_hash(s, at) * 8u + s->m2slot, at);
                if (pending == 2u)
                    ss_m2_insert(s, ss_m2_hash(s, at + 1u) * 8u + s->m2slot,
                                 at + 1u);
                pending = 0;
            }
            ss_m2_insert(s, (code & ~7u) + s->m2slot, start);
        }
    }
    return UNC_OK;
}

static int ss_orig(SsState *s, const SsFork *f, uint8_t *iobuf,
                   uint32_t iocap, unsigned method)
{
    UncCtx *c = s->out.c;
    UncBufIn in;
    uint32_t produced = 0, consumed = 0;
    int e;

    if (c->io->seek(c->io->ctx, f->off) < 0) return UNC_ERR_IO;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = f->clen;

    /* Method 1 never reaches further back than its 12-bit distance;
     * method 2's table holds positions anywhere in the block it is
     * decoding, and a block is what the compressor read in one go. */
    s->wsize = 1u << (method == 1 ? SS_ORIG_WBITS : SS_M2_WBITS);
    s->wmask = s->wsize - 1u;
    s->win = (uint8_t *)unc_alloc(c->al, s->wsize);
    if (!s->win) return UNC_ERR_MEM;
    s->wpos = 0;
    s->history = 0;
    s->produced = 0;
    if (method == 2) {
        s->m2tab = (uint32_t *)unc_alloc(c->al,
                                         SS_M2_ENTRIES * sizeof(uint32_t));
        if (!s->m2tab) return UNC_ERR_MEM;
    }

    while (produced < f->ulen) {
        uint8_t hdr[SS_ORIG_HDR];
        uint32_t plen;
        int i, b;

        if (SS_ORIG_HDR > f->clen - consumed) return UNC_ERR_CORRUPT;
        for (i = 0; i < (int)SS_ORIG_HDR; i++) {
            if ((b = unc_bufin_next(&in)) < 0) return in.err;
            hdr[i] = (uint8_t)b;
        }
        consumed += SS_ORIG_HDR;
        plen = unc_get_u32be(hdr + 4);
        if (plen > f->clen - consumed) return UNC_ERR_CORRUPT;

        if (hdr[0] == 1) {                        /* stored, @0x1b6 */
            if (plen > f->ulen - produced) return UNC_ERR_CORRUPT;
            while (plen-- > 0) {
                if ((b = unc_bufin_next(&in)) < 0) return in.err;
                if ((e = ss_emit(s, (uint8_t)b)) != UNC_OK) return e;
                produced++;
                consumed++;
            }
            s->produced = produced;
            continue;
        }
        s->produced = produced;
        e = method == 1 ? ss_orig1(s, &in, plen, &produced, f->ulen)
                        : ss_orig2(s, &in, plen, &produced, f->ulen);
        if (e != UNC_OK) return e;
        consumed += plen;
    }
    if (produced != f->ulen) return UNC_ERR_CORRUPT;
    return unc_fork_flush(&s->out);
}

/* ------------------------------------------------------------------ */
/* Method 3 — "Alg 3", `CMod 11` @0x1134                               */
/*                                                                     */
/* The framing is method 4's: a 16-bit block count and a width byte,   */
/* then blocks of a 6-byte header (compressed and uncompressed length, */
/* both 24-bit little-endian). The codec is not: it is an LZ77 whose   */
/* literals and lengths share a 308-symbol Huffman alphabet and whose  */
/* distances use a second of `4 * wbits + 3`, both read LSB-first. A   */
/* symbol below 256 is a literal; above it selects a length from a base*/
/* table plus extra bits (@0x15d4), a distance symbol follows the same */
/* way, and the copy is `4 + length` bytes (@0x16fc copies four before */
/* it counts).                                                         */
/*                                                                     */
/* Both base tables are rules rather than data, built by the module's  */
/* own init (@0x1a04 and @0x1aa0):                                     */
/*                                                                     */
/*     length   extra[i] = i < 4 ? 0 : (i - 4) >> 2, base from 0       */
/*     distance extra[i] = i < 3 ? 0 : (i - 3) >> 2, base from 1       */
/* ------------------------------------------------------------------ */

#define SS_A3_LITS   308u
#define SS_A3_LENS   52u               /* 308 - 256                    */
#define SS_A3_MAXD   67u               /* 4 * 16 + 3, the widest       */
#define SS_A3_MAXLEN 24                /* code lengths past this: refused */
#define SS_A3_META   32u               /* the biggest meta alphabet    */
#define SS_A3_DEPTH  4                 /* meta levels this will follow */
#define SS_A3_QSTACK 32

typedef struct SsHuff {
    uint16_t *sym;                     /* symbols in assignment order  */
    uint16_t  count[SS_A3_MAXLEN + 2];
    uint32_t  first[SS_A3_MAXLEN + 2];
    uint16_t  index[SS_A3_MAXLEN + 2];
    int       maxlen;
} SsHuff;

/* The sort that decides the code assignment, and it has to be THIS
 * sort: @0x15a is a Hoare partition on the code lengths, pivoting on
 * the first element and recursing into the smaller half, and it is not
 * stable — so which symbol gets which code among equal lengths is
 * whatever this partitioning leaves behind. Both sides of the format
 * run the same routine, so it is self-consistent; a decoder that sorts
 * differently decodes a different file. Recursion is not allowed here
 * (CLAUDE.md), so the smaller half goes on an explicit stack. */
static int ss_a3_sort(uint8_t *len, uint16_t *idx, uint32_t n)
{
    uint32_t stack[SS_A3_QSTACK][2];
    int sp = 0;
    uint32_t lo = 0, hi = n;
    for (;;) {
        while (hi - lo - 1u > 0u && hi > lo) {
            uint32_t i = lo, j = hi, k;
            for (;;) {
                uint8_t pivot = len[lo];
                do { i++; } while (i < hi && pivot > len[i]);
                do { j--; } while (j > lo && len[j] > len[lo]);
                if (j <= i) break;
                { uint8_t t = len[i]; len[i] = len[j]; len[j] = t; }
                { uint16_t t = idx[i]; idx[i] = idx[j]; idx[j] = t; }
            }
            if (lo == j) { lo++; continue; }
            { uint8_t t = len[lo]; len[lo] = len[j]; len[j] = t; }
            { uint16_t t = idx[lo]; idx[lo] = idx[j]; idx[j] = t; }
            k = j + 1u;
            if (sp >= SS_A3_QSTACK) return UNC_ERR_UNSUPPORTED;
            if ((hi - k) < (j - lo)) {          /* @0x236 */
                stack[sp][0] = lo; stack[sp][1] = j; sp++;
                lo = k;
            } else {
                stack[sp][0] = k; stack[sp][1] = hi; sp++;
                hi = j;
            }
        }
        if (sp == 0) return UNC_OK;
        sp--;
        lo = stack[sp][0];
        hi = stack[sp][1];
    }
}

/* Lengths -> a canonical decoder. @0x27c assigns codes in the sorted
 * order above, skipping zero lengths, and bit-REVERSES each one
 * (@0x324) because the stream is read LSB first; reading a bit at a
 * time into the low end of an accumulator undoes exactly that, so what
 * is kept here is the ordinary count/first-code pair per length. */
static int ss_a3_build(SsHuff *h, uint8_t *len, uint16_t *idx,
                       const uint8_t *lengths, uint32_t n)
{
    uint32_t i, code, at;
    int L, e;
    for (i = 0; i < n; i++) { len[i] = lengths[i]; idx[i] = (uint16_t)i; }
    if ((e = ss_a3_sort(len, idx, n)) != UNC_OK) return e;
    for (L = 0; L <= SS_A3_MAXLEN + 1; L++) h->count[L] = 0;
    h->maxlen = 0;
    for (i = 0; i < n; i++) {
        if (len[i] == 0) continue;
        if (len[i] > SS_A3_MAXLEN) return UNC_ERR_UNSUPPORTED;
        h->count[len[i]]++;
        if (len[i] > h->maxlen) h->maxlen = len[i];
    }
    at = 0;
    for (i = 0; i < n; i++)
        if (len[i] != 0) h->sym[at++] = idx[i];
    code = 0; at = 0;
    for (L = 1; L <= h->maxlen; L++) {
        h->first[L] = code;
        h->index[L] = (uint16_t)at;
        at += h->count[L];
        code = (code + h->count[L]) << 1;
        /* A code that would not fit its own length is a corrupt table,
         * not something to keep decoding with. */
        if (code > (1u << (L + 1))) return UNC_ERR_CORRUPT;
    }
    return UNC_OK;
}

static int32_t ss_a3_sym(UncBitIn *bi, const SsHuff *h)
{
    uint32_t code = 0;
    int L;
    for (L = 1; L <= h->maxlen; L++) {
        int bit = unc_bitin_bit(bi);
        if (bit < 0) return -1;
        code = (code << 1) | (uint32_t)bit;
        if (h->count[L] != 0 && code >= h->first[L] &&
            code - h->first[L] < h->count[L])
            return (int32_t)h->sym[h->index[L] + (code - h->first[L])];
    }
    return -2;
}

/* The code lengths themselves, @0xe26 — a control byte, then symbols.
 *
 *   bit 6      the symbols are Huffman-coded, by this same routine
 *              called on an alphabet of its own
 *   bits 1..2  the raw symbol's width, 2..5 bits
 *   bits 3..5  what to add to a plain symbol, 1..8
 *   bit 0      the top-but-one symbol means "length 0"
 *
 * and the top symbol means "repeat the previous length, 3 + the next
 * symbol times". Each level ends on a byte boundary, and a level's
 * child sits between its control byte and its symbols — so the whole
 * thing reads forwards, which is what lets the recursion the module
 * uses become a descent and an unwind here. */
typedef struct SsA3Meta {
    uint8_t  lengths[SS_A3_META];
    uint16_t symbuf[SS_A3_META];
    uint8_t  sortlen[SS_A3_META];
    uint16_t sortidx[SS_A3_META];
    SsHuff   huff;
    uint32_t nsyms;
    unsigned width, add, mask;
    int      escape, meta;
} SsA3Meta;

typedef struct SsA3 {
    SsA3Meta meta[SS_A3_DEPTH + 1];
    SsHuff   lit, dist;
    uint16_t symbuf[SS_A3_LITS], sortidx[SS_A3_LITS];
    uint16_t dsym[SS_A3_MAXD], dsortidx[SS_A3_MAXD];
    uint16_t lbase[SS_A3_LENS], dbase[SS_A3_MAXD];
    uint8_t  litlen[SS_A3_LITS], sortlen[SS_A3_LITS];
    uint8_t  distlen[SS_A3_MAXD], dsortlen[SS_A3_MAXD];
    uint8_t  lext[SS_A3_LENS], dext[SS_A3_MAXD];
} SsA3;

static int ss_a3_lengths(SsState *s, UncBitIn *bi, uint8_t *out, uint32_t n)
{
    SsA3Meta *lv = s->a3->meta;
    int d = 0, e;
    uint32_t k;

    for (;;) {                                    /* the descent */
        int32_t c = unc_bitin_bits_le(bi, 8);
        if (c < 0) return bi->err ? bi->err : UNC_ERR_TRUNCATED;
        lv[d].add    = (unsigned)(((c >> 3) & 7) + 1);
        lv[d].width  = (unsigned)(((c >> 1) & 3) + 2);
        lv[d].mask   = (1u << lv[d].width) - 1u;
        lv[d].meta   = (c & 0x40) != 0;
        lv[d].escape = (c & 1) ? (int)lv[d].mask - 1 : -1;
        lv[d].nsyms  = d == 0 ? n : lv[d - 1].mask + 1u;
        if (!lv[d].meta) break;
        if (++d >= SS_A3_DEPTH) return UNC_ERR_UNSUPPORTED;
    }

    for (; d >= 0; d--) {                         /* and the unwind */
        uint8_t *dst = d == 0 ? out : lv[d].lengths;
        uint32_t want = lv[d].nsyms, at = 0;
        if (d != 0 && want > SS_A3_META) return UNC_ERR_CORRUPT;
        while (at < want) {
            int32_t sym;
            if (lv[d].meta) {
                sym = ss_a3_sym(bi, &lv[d + 1].huff);
                if (sym == -1) return bi->err ? bi->err : UNC_ERR_TRUNCATED;
                if (sym < 0) return UNC_ERR_CORRUPT;
            } else {
                sym = unc_bitin_bits_le(bi, (int)lv[d].width);
                if (sym < 0) return bi->err ? bi->err : UNC_ERR_TRUNCATED;
            }
            if (sym == lv[d].escape) {
                dst[at++] = 0;
            } else if ((unsigned)sym == lv[d].mask) {
                int32_t rep;
                if (lv[d].meta) {
                    rep = ss_a3_sym(bi, &lv[d + 1].huff);
                    if (rep == -1) return bi->err ? bi->err : UNC_ERR_TRUNCATED;
                    if (rep < 0) return UNC_ERR_CORRUPT;
                } else {
                    rep = unc_bitin_bits_le(bi, (int)lv[d].width);
                    if (rep < 0) return bi->err ? bi->err : UNC_ERR_TRUNCATED;
                }
                if (at == 0) return UNC_ERR_CORRUPT;
                for (k = 0; k < (uint32_t)rep + 3u; k++) {
                    if (at >= want) return UNC_ERR_CORRUPT;
                    dst[at] = dst[at - 1];
                    at++;
                }
            } else {
                dst[at++] = (uint8_t)((unsigned)sym + lv[d].add);
            }
        }
        unc_bitin_align(bi);                      /* @0x1126 rounds up */
        if (d != 0) {
            lv[d].huff.sym = lv[d].symbuf;
            if ((e = ss_a3_build(&lv[d].huff, lv[d].sortlen, lv[d].sortidx,
                                 lv[d].lengths, want)) != UNC_OK)
                return e;
        }
    }
    return UNC_OK;
}

static int ss_alg3(SsState *s, const SsFork *f, uint8_t *iobuf,
                   uint32_t iocap)
{
    UncCtx *c = s->out.c;
    UncBufIn in;
    UncBitIn bi;
    uint32_t nblocks, produced = 0, consumed = 3;
    SsA3 *w;
    uint32_t ndist, i, v;
    int wbits, b, e;

    if (c->io->seek(c->io->ctx, f->off) < 0) return UNC_ERR_IO;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = f->clen;

    if (f->clen < 3) return UNC_ERR_TRUNCATED;
    nblocks = 0;
    for (i = 0; i < 2; i++) {
        if ((b = unc_bufin_next(&in)) < 0) return in.err;
        nblocks |= (uint32_t)b << (8 * i);
    }
    if ((b = unc_bufin_next(&in)) < 0) return in.err;
    wbits = b;
    if (wbits < 1 || wbits > SS_MAXWBITS) return UNC_ERR_UNSUPPORTED;
    ndist = 4u * (uint32_t)wbits + 3u;
    if (ndist > SS_A3_MAXD) return UNC_ERR_UNSUPPORTED;

    /* Everything this codec needs is one allocation: a 68000 has 4 KB of
     * call depth to spend for the whole engine (CLAUDE.md), and the
     * tables here would eat a quarter of it on the stack. */
    s->a3 = (SsA3 *)unc_alloc(c->al, (uint32_t)sizeof(SsA3));
    if (!s->a3) return UNC_ERR_MEM;
    w = s->a3;

    /* The two base tables, as the module's init computes them. */
    v = 0;
    for (i = 0; i < SS_A3_LENS; i++) {
        w->lext[i] = (uint8_t)(i < 4 ? 0 : (i - 4) >> 2);
        w->lbase[i] = (uint16_t)v;
        v += 1u << w->lext[i];
    }
    v = 1;
    for (i = 0; i < ndist; i++) {
        w->dext[i] = (uint8_t)(i < 3 ? 0 : (i - 3) >> 2);
        w->dbase[i] = (uint16_t)(v > 0xFFFFu ? 0xFFFFu : v);
        v += 1u << w->dext[i];
    }

    s->wsize = 1u << wbits;
    s->wmask = s->wsize - 1u;
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
        return UNC_ERR_UNSUPPORTED;

    while (nblocks-- > 0) {
        uint32_t clen = 0, ulen = 0, endpos;

        for (i = 0; i < 3; i++) {
            if ((b = unc_bufin_next(&in)) < 0) goto ioerr;
            clen |= (uint32_t)b << (8 * i);
        }
        for (i = 0; i < 3; i++) {
            if ((b = unc_bufin_next(&in)) < 0) goto ioerr;
            ulen |= (uint32_t)b << (8 * i);
        }
        consumed += 6;
        if (clen < 6u) return UNC_ERR_CORRUPT;
        if (clen - 6u > f->clen - consumed) return UNC_ERR_CORRUPT;
        if (ulen > f->ulen - produced) return UNC_ERR_CORRUPT;
        endpos = produced + ulen;

        unc_bitin_init_le(&bi, &in);
        if ((e = ss_a3_lengths(s, &bi, w->litlen, SS_A3_LITS)) != UNC_OK)
            return e;
        w->lit.sym = w->symbuf;
        if ((e = ss_a3_build(&w->lit, w->sortlen, w->sortidx, w->litlen,
                             SS_A3_LITS)) != UNC_OK)
            return e;
        if ((e = ss_a3_lengths(s, &bi, w->distlen, ndist)) != UNC_OK)
            return e;
        w->dist.sym = w->dsym;
        if ((e = ss_a3_build(&w->dist, w->dsortlen, w->dsortidx, w->distlen,
                             ndist)) != UNC_OK)
            return e;

        while (produced < endpos) {
            int32_t sym = ss_a3_sym(&bi, &w->lit);
            uint32_t n, d;
            int32_t k;

            if (sym == -1) { in.err = bi.err; goto ioerr; }
            if (sym < 0) return UNC_ERR_CORRUPT;
            if (sym < 256) {
                if ((e = ss_emit(s, (uint8_t)sym)) != UNC_OK) return e;
                produced++;
                continue;
            }
            sym -= 256;
            n = w->lbase[sym];
            if (w->lext[sym]) {
                if ((k = unc_bitin_bits_le(&bi, w->lext[sym])) < 0)
                    { in.err = bi.err; goto ioerr; }
                n += (uint32_t)k;
            }
            n += 4u;                                  /* @0x16fc */
            if ((sym = ss_a3_sym(&bi, &w->dist)) == -1) { in.err = bi.err; goto ioerr; }
            if (sym < 0 || (uint32_t)sym >= ndist) return UNC_ERR_CORRUPT;
            d = w->dbase[sym];
            if (w->dext[sym]) {
                if ((k = unc_bitin_bits_le(&bi, w->dext[sym])) < 0)
                    { in.err = bi.err; goto ioerr; }
                d += (uint32_t)k;
            }
            if (d == 0 || d > s->history) return UNC_ERR_CORRUPT;
            if (n > endpos - produced) return UNC_ERR_CORRUPT;
            while (n-- > 0) {
                uint8_t byte = s->win[(s->wpos + s->wsize - d) & s->wmask];
                if ((e = ss_emit(s, byte)) != UNC_OK) return e;
                produced++;
            }
        }
        consumed += clen - 6u;
        if (c->io->seek(c->io->ctx, f->off + consumed) < 0) return UNC_ERR_IO;
        unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
        in.limit = f->clen - consumed;
    }
    if (produced != f->ulen) return UNC_ERR_CORRUPT;
    return unc_fork_flush(&s->out);

ioerr:
    return in.err != UNC_OK ? in.err : UNC_ERR_TRUNCATED;
}

/* ------------------------------------------------------------------ */
/* Method 0 — stored, `CMod 1` XferData @0xee: read, write, repeat.    */
/* ------------------------------------------------------------------ */

static int ss_stored(SsState *s, const SsFork *f)
{
    UncCtx *c = s->out.c;
    uint32_t left = f->ulen, at = f->off;

    if (f->clen != f->ulen) return UNC_ERR_CORRUPT;
    while (left > 0) {
        uint32_t take = left < UNC_STAGE ? left : UNC_STAGE;
        if (unc_read_at(c->io, at, s->out.buf, (int32_t)take) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        s->out.len = take;
        if (unc_fork_flush(&s->out) != UNC_OK) return UNC_ERR_SINK;
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
    s->m2tab = 0;
    s->a3 = 0;
    switch (m) {
    case 0:  err = ss_stored(s, f); break;
    case 1:
    case 2:  err = ss_orig(s, f, iobuf, iocap, m); break;
    case 3:  err = ss_alg3(s, f, iobuf, iocap); break;
    case 4:  err = ss_alg4(s, f, iobuf, iocap); break;
    /* Everything else is refused per entry: the file is still named,
     * and a method this build does not know costs the ENTRY. */
    default: err = UNC_ERR_UNSUPPORTED; break;
    }
    if (s->win) {
        unc_free(s->out.c->al, s->win);
        s->win = 0;
    }
    if (s->m2tab) {
        unc_free(s->out.c->al, s->m2tab);
        s->m2tab = 0;
    }
    if (s->a3) {
        unc_free(s->out.c->al, s->a3);
        s->a3 = 0;
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
                for (i = 0; i < 2 && ferr == UNC_OK; i++) {
                    if (h.fork[i].ulen == 0) continue;
                    /* The guard is this format's: a test-only run
                     * decodes and checksums but writes nothing. */
                    unc_fork_out(&s.out, c,
                                 i ? UNC_FORK_RSRC : UNC_FORK_DATA,
                                 !c->opt.test_only && !c->opt.list_only,
                                 UNC_CK_NONE, s.sbuf, UNC_STAGE);
                    ferr = ss_one_fork(&s, &h.fork[i], iobuf, SS_IOBUF);
                }
                unc_free(c->al, iobuf);
            }
        }
        if (c->sink->end_entry(c->sink->ctx, ferr) < 0) err = UNC_ERR_SINK;
        else if (unc_fatal(ferr)) err = ferr;
    }
    return err;
}

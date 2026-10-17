/*
 * fmt_exo.c — the exogenous formats: gzip (.gz), Unix compress (.Z)
 * and zip (store, Shrink, Reduce, Implode and deflate). Tar's reader is
 * src/fmt_tar.c since 2026-10-17 (that file says why).
 *
 * These are byte-oriented Unix/PC formats, and every one of them has a
 * specification of its own. Those are what is cited, here and at each
 * field below:
 *   gzip  reference/notes/rfc1952.txt
 *   zip   reference/notes/zip_appnote.txt (PKWARE APPNOTE.TXT 6.3.10),
 *         with reference/notes/winzip_aes.txt for the one extra field
 *         APPNOTE names but does not lay out; section 5.3 is the whole
 *         of Imploding and is cited field by field at the decoder,
 *         beside reference/deark/src/fmtutil-lzh.c, which is the
 *         reference implementation each reading was checked against
 *   tar   reference/notes/posix_ustar.txt (POSIX.1-2017, the pax page,
 *         "ustar Interchange Format")
 *   .Z    reference/deark/src/fmtutil-lzw.c for the three-byte header
 *         (the codec itself is unc_lzw.c, which cites the same file)
 *
 * One thing is in none of them: pre-POSIX v7 tar predates the standard
 * above and has no magic at all, so recognising one is this project's
 * own problem and its answer says so at the line that makes it.
 * Deflate decoding uses vendored zlib (third_party/zlib).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"
#include "fmt_exo_priv.h"
#include "unc_date.h"

/* Twice UNC_IOBUF. These readers move whole runs rather than bytes:
 * inflate hands back a block at a time, LZW a phrase, and tar copies
 * member data straight through. */
#define EXO_BUF (2u * UNC_IOBUF)

/* Shared emit callback: write to sink data fork. */
typedef struct ExoSink {
    UncCtx  *c;
    int      failed;
    /* ZipIt stores a Macintosh file as a MacBinary stream and zips
     * THAT, so one decoded stream is a 128-byte header, the data fork
     * padded to 128, then the resource fork. `split` routes the stream
     * to two forks by position; the entry's CRC-32 is still taken over
     * all of it, header and padding included, which is what the
     * directory records. Same arrangement as MacLHA's (fmt_lzh.c). */
    uint8_t  split;
    uint32_t pos, ds, de, rs, re;
    /* The first 128 bytes, captured for the header peek. */
    uint8_t *head;
    uint32_t headgot;
    /* Decode and CRC but write NOTHING, for the Implode
     * minimum-match-length probe (zip_imp_dry, below). Distinct from
     * `UncOptions.test_only`, which is the user asking for the same
     * thing over a whole archive: this one is the engine's own and
     * lasts one pass. */
    uint8_t  dry;
    /* A Mac OS X sidecar's header, captured before its file's entry is
     * offered (zip_side): fed, written nowhere, and the decode
     * stopped once the capture has all it wants. */
    UncAdCap *side;
} ExoSink;

static int exo_emit(void *ctx, const uint8_t *p, int32_t n)
{
    ExoSink *s = (ExoSink *)ctx;

    if (s->side)
        return unc_ad_feed(s->side, p, (uint32_t)n) ? UNC_ERR_SINK : UNC_OK;
    /* Peek mode: capture the first 128 bytes and write NOTHING —
     * begin_entry has not been called yet. Once they are in hand the
     * decode is stopped by failing the callback, which is the only
     * brake a chunk emitter has: zlib hands over a whole bufferful at
     * a time, so asking unc_inflate_raw for 128 bytes instead would
     * trip its "more output than declared" check before emitting any
     * of them. The status is discarded by the caller. */
    if (s->head) {
        while (n > 0 && s->headgot < 128) {
            s->head[s->headgot++] = *p++;
            n--;
        }
        return s->headgot < 128 ? UNC_OK : UNC_ERR_SINK;
    }
    /* A probe pass: the CRC-32 is accumulated by the decoder itself, so
     * there is nothing for this to do but count. One test, ahead of the
     * split walk, because a probe never splits. */
    if (s->dry) {
        s->pos += (uint32_t)n;
        return UNC_OK;
    }
    if (!s->split) {
        s->pos += (uint32_t)n;
        if (s->c->opt.test_only) return UNC_OK;
        if (s->c->sink->write(s->c->sink->ctx, UNC_FORK_DATA, p, n) < 0)
            return UNC_ERR_SINK;
        return UNC_OK;
    }
    /* Split: walk the chunk, handing each fork the part that falls in
     * its span and dropping the header and the padding between them. */
    while (n > 0) {
        uint32_t end = s->pos + (uint32_t)n;
        uint32_t lo, hi;
        UncFork fk;

        if (s->pos < s->de && end > s->ds) { lo = s->ds; hi = s->de;
                                             fk = UNC_FORK_DATA; }
        else if (s->pos < s->re && end > s->rs) { lo = s->rs; hi = s->re;
                                                  fk = UNC_FORK_RSRC; }
        else { s->pos = end; return UNC_OK; }   /* header or padding */

        if (s->pos < lo) {          /* skip up to the span */
            uint32_t skip = lo - s->pos;
            if (skip > (uint32_t)n) skip = (uint32_t)n;
            p += skip; n -= (int32_t)skip; s->pos += skip;
            continue;
        }
        {
            uint32_t take = hi - s->pos;
            if (take > (uint32_t)n) take = (uint32_t)n;
            if (!s->c->opt.test_only &&
                s->c->sink->write(s->c->sink->ctx, fk, p, (int32_t)take) < 0)
                return UNC_ERR_SINK;
            p += take; n -= (int32_t)take; s->pos += take;
        }
    }
    return UNC_OK;
}

static void exo_sink_init(ExoSink *s, UncCtx *c)
{
    s->c = c; s->failed = 0; s->split = 0; s->pos = 0;
    s->ds = s->de = s->rs = s->re = 0;
    s->head = NULL; s->headgot = 0; s->dry = 0; s->side = NULL;
}

static void exo_hint_name(UncCtx *c, UncEntryInfo *e)
{
    if (c->opt.name_hint && c->opt.name_hint_len)
        unc_entry_set_path(e, c->opt.name_hint, c->opt.name_hint_len);
}

/* ------------------------------------------------------------------ */
/* gzip (RFC 1952)                                                    */
/* ------------------------------------------------------------------ */


int unc_gzip_extract(UncCtx *c)
{
    uint8_t hdr[10], *iobuf, *obuf;
    uint32_t iocap = UNC_IOBUF, ocap = EXO_BUF;
    UncBufIn in;
    UncEntryInfo e;
    ExoSink es;
    int flg, sret, est = UNC_OK;
    int err = UNC_OK;
    uint8_t *cmt = NULL;
    uint32_t clen = 0;

    if (unc_read_at(c->io, 0, hdr, 10) != UNC_OK) return UNC_ERR_FORMAT;
    if (hdr[0] != 0x1F || hdr[1] != 0x8B) return UNC_ERR_FORMAT;
    if (hdr[2] != 8) return UNC_ERR_UNSUPPORTED;   /* only deflate exists */
    flg = hdr[3];

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;

    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    if (c->io->seek(c->io->ctx, 10) < 0) { err = UNC_ERR_IO; goto out; }

    /* Optional header fields, in the order RFC 1952 section 2.3's
     * member-format diagram puts them: FEXTRA, FNAME, FCOMMENT, FHCRC
     * — the last "immediately before the compressed data". */
    if (flg & 0x04) {   /* FEXTRA */
        int lo = unc_bufin_next(&in), hi = unc_bufin_next(&in);
        int32_t n;
        if (lo < 0 || hi < 0) { err = UNC_ERR_TRUNCATED; goto out; }
        n = lo | (hi << 8);
        while (n-- > 0)
            if (unc_bufin_next(&in) < 0) { err = UNC_ERR_TRUNCATED; goto out; }
    }
    if (flg & 0x08) {   /* FNAME: NUL-terminated (unar ignores it too) */
        int b;
        do {
            b = unc_bufin_next(&in);
            if (b < 0) { err = UNC_ERR_TRUNCATED; goto out; }
        } while (b != 0);
    }
    if (flg & 0x10) {   /* FCOMMENT: kept, up to what an entry carries */
        int b;
        cmt = (uint8_t *)unc_alloc(c->al, UNC_ENTRY_COMMENT_MAX);
        do {
            b = unc_bufin_next(&in);
            if (b < 0) { err = UNC_ERR_TRUNCATED; goto out; }
            if (b && cmt && clen < UNC_ENTRY_COMMENT_MAX)
                cmt[clen++] = (uint8_t)b;
        } while (b != 0);
    }
    if (flg & 0x02) {   /* FHCRC */
        if (unc_bufin_next(&in) < 0 || unc_bufin_next(&in) < 0) {
            err = UNC_ERR_TRUNCATED;
            goto out;
        }
    }

    unc_entry_clear(&e);
    exo_hint_name(c, &e);
    e.data_size = UNC_SIZE_UNKNOWN;   /* ISIZE is only mod 2^32; trailer */
    e.rsrc_size = 0;
    /* MTIME, a Unix time with 0 for "no time stamp", and FCOMMENT, the
     * member's comment — ISO 8859-1, handed on as the bytes it is, as
     * every name is. Source: reference/notes/rfc1952.txt, 2.3.1. */
    e.mod_date = unc_get_u32le(hdr + 4) ? unc_unix_to_mac(unc_get_u32le(hdr + 4))
                                        : 0;
    if (clen) {
        e.comment = cmt;
        e.comment_len = (uint16_t)clen;
    }

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) { err = UNC_ERR_SINK; goto out; }
    if (sret > 0) goto out;

    if (!c->opt.list_only) {
        uint32_t produced = 0, crc = UNC_CRC32_INIT;
        exo_sink_init(&es, c);
        est = unc_inflate_raw(&in, c->al, obuf, ocap, UNC_SIZE_UNKNOWN,
                              &produced, &crc, exo_emit, &es);
        if (est == UNC_OK) {
            /* Trailer: u32le CRC-32, u32le ISIZE. */
            uint8_t tr[8];
            int i, b;
            for (i = 0; i < 8; i++) {
                b = unc_bufin_next(&in);
                if (b < 0) { est = UNC_ERR_TRUNCATED; break; }
                tr[i] = (uint8_t)b;
            }
            if (est == UNC_OK) {
                if (unc_get_u32le(tr) != ~crc) est = UNC_ERR_CRC;
                else if (unc_get_u32le(tr + 4) != produced) est = UNC_ERR_CRC;
            }
        }
    }
    if (c->sink->end_entry(c->sink->ctx, est) < 0) err = UNC_ERR_SINK;
    if (unc_fatal(est)) err = est;

out:
    unc_free(c->al, cmt);
    unc_free(c->al, iobuf);
    return err;
}

/* ------------------------------------------------------------------ */
/* Unix compress .Z                                                   */
/* ------------------------------------------------------------------ */


int unc_compressz_extract(UncCtx *c)
{
    uint8_t hdr[3], *iobuf, *obuf;
    uint32_t iocap = UNC_IOBUF, ocap = EXO_BUF;
    UncBufIn in;
    UncLzw z;
    UncEntryInfo e;
    int maxbits, blockmode, sret, est = UNC_OK;
    int err = UNC_OK;

    if (unc_read_at(c->io, 0, hdr, 3) != UNC_OK) return UNC_ERR_FORMAT;
    if (hdr[0] != 0x1F || hdr[1] != 0x9D) return UNC_ERR_FORMAT;
    maxbits = hdr[2] & 0x1F;
    blockmode = hdr[2] & 0x80;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;

    unc_entry_clear(&e);
    exo_hint_name(c, &e);
    e.data_size = UNC_SIZE_UNKNOWN;   /* no size stored in the format */
    e.rsrc_size = 0;

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) { err = UNC_ERR_SINK; goto out; }
    if (sret > 0) goto out;

    if (!c->opt.list_only) {
        unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
        if (c->io->seek(c->io->ctx, 3) < 0) { err = UNC_ERR_IO; goto out; }
        {   /* Size the table from the stream, less the 3-byte header. */
            uint32_t insize = unc_io_size32(c->io);
            insize = (insize == UNC_SIZE_UNKNOWN || insize < 3)
                   ? 0 : insize - 3;
            est = unc_lzw_init(&z, c->al, &in, maxbits, blockmode, insize);
        }
        if (est == UNC_OK) {
            for (;;) {
                int32_t got = unc_lzw_read(&z, obuf, (int32_t)ocap);
                if (got < 0) { est = (int)got; break; }
                if (got == 0) break;   /* clean end of stream */
                if (!c->opt.test_only &&
                    c->sink->write(c->sink->ctx, UNC_FORK_DATA, obuf, got) < 0) {
                    est = UNC_ERR_SINK;
                    break;
                }
            }
            unc_lzw_free(&z, c->al);
        }
    }
    if (c->sink->end_entry(c->sink->ctx, est) < 0) err = UNC_ERR_SINK;
    if (unc_fatal(est)) err = est;

out:
    unc_free(c->al, iobuf);
    return err;
}

/* ------------------------------------------------------------------ */
/* zip (EOCD + central directory; store and deflate)                  */
/* ------------------------------------------------------------------ */


/* A zip stores every address as (part, offset within that part). For an
 * archive in one file the part is always 0 and the offset is absolute,
 * so these two make the whole reader indifferent to which it has: it
 * positions, then reads forward, and a segmented set rolls into its
 * next part on its own.
 *
 * Which is why nothing here ever needs a part's SIZE, or a table of
 * them. That was not true of the first version, and the table cost a
 * pass over the whole set to build (DECISIONS.md 2026-08-09). */
static int zip_seek(UncCtx *c, uint32_t part0, uint32_t off)
{
    if (!c->segmap) {
        /* A part number with no set behind it: the caller was handed
         * one member and nothing else. Not corrupt — incomplete. */
        if (part0 != 0) return UNC_ERR_SEGMENTED;
        return c->io->seek(c->io->ctx, off) < 0 ? UNC_ERR_IO : UNC_OK;
    }
    if (part0 >= 0xFFFFu) return UNC_ERR_UNSUPPORTED;   /* zip64 */
    return c->segmap->seek_part(c->segmap->ctx, (int)part0 + 1, off);
}

static int zip_skip(UncCtx *c, uint32_t n)
{
    if (!c->segmap) return unc_skip(c->io, n);
    return c->segmap->skip(c->segmap->ctx, n);
}

/* The EOCD scanner's reader. For a segmented set the record is in the
 * LAST part, so offsets here are within that part. */
typedef struct { UncCtx *c; uint32_t part0; } ZipScan;

static int zip_scan_read(void *ctx, uint32_t off, void *buf, int32_t len)
{
    ZipScan *s = (ZipScan *)ctx;
    int err = zip_seek(s->c, s->part0, off);
    if (err != UNC_OK) return err;
    return unc_read_full(s->c->io, buf, len);
}

static int zip_emit(void *ctx, const uint8_t *p, int32_t n)
{
    return exo_emit(ctx, p, n);
}

/* ------------------------------------------------------------------ */
/* Implode — zip method 6, PKZIP 1.x                                  */
/* ------------------------------------------------------------------ */

/* A sliding dictionary whose output tokens are Shannon-Fano coded, with
 * one tree per alphabet stored byte-aligned at the head of the entry.
 * THREE parameters shape it and every one is read off the entry's own
 * general-purpose flag word rather than assumed:
 *
 *   bit 1 (0x0002)  0 = a 4 K dictionary, 1 = 8 K
 *   bit 2 (0x0004)  0 = two trees stored (length, then distance),
 *                   1 = three (a literal tree first)
 *
 * and the literal tree's PRESENCE is what sets the minimum match
 * length: 3 when it is there, 2 when it is not.
 *
 * Source: reference/notes/zip_appnote.txt 5.3.2 (the dictionary size and
 * the flag bit that states it), 5.3.3 (the tree count, its flag bit, and
 * the order the trees are stored in), 5.3.4 (the literal tree's 256
 * values and the minimum match length that follows from its presence),
 * 5.3.5 and 5.3.6 (the 64-value length and distance trees), 5.3.7 (how a
 * tree is stored), 5.3.8 (how the codes come out of the bit lengths) and
 * 5.3.9 (the token stream). reference/deark/src/fmtutil-lzh.c (MIT) is
 * the reference implementation each of those was read beside —
 * `implode_read_a_tree`, `implode_read_trees` and
 * `decompress_implode_internal`.
 *
 * A FOURTH parameter is not in the flag word and not in the stream: it
 * is the WRITER. PKZIP 1.01 and 1.02 took the minimum match length from
 * the DICTIONARY SIZE instead of from the literal tree's presence — 3
 * at 8 K and 2 at 4 K — which disagrees with 5.3.4 in exactly the two
 * combinations where the two readings differ (bit 1 set alone, and bit
 * 2 set alone). `mmlbug` selects it, and which of the two an archive
 * wants is settled by decoding one entry with no output and comparing
 * the stored CRC-32 (zip_imp_dry, below).
 *
 * Source: reference/deark/src/fmtutil-lzh.c (MIT),
 * `fmtutil_decompress_zip_implode` — `cctx->implode_min_match_len =
 * cctx->implode_8k_buffer ? 3 : 2` under `params->mml_bug`, against
 * `cctx->implode_3_trees ? 3 : 2` without it. No specification states
 * the buggy rule: it is a reading of two programs' behaviour, and
 * PKZIP 1.01's own distribution is what grades it here (the fixture
 * `pkz101.exe`; FORMATS.md, *Implode*). */

/* The RLE nibble carries a bit length MINUS ONE, so 16 is the longest
 * code the format can state. Source: zip_appnote.txt 5.3.7. */
#define IMP_MAXBITS 16

/* 4 K or 8 K, and the low bits of a distance that are read raw: six for
 * a 4 K dictionary and seven for an 8 K one, the distance tree supplying
 * the upper six either way. Source: zip_appnote.txt 5.3.2, 5.3.6, 5.3.9. */
#define IMP_DICT_4K  4096u
#define IMP_DICT_8K  8192u

/* One decode table. `sym` is the symbol each code slot names, laid out
 * in the order 5.3.8 assigns codes — so the codes of one bit length are
 * a consecutive run, and `first`/`cbase` turn a code of that length into
 * an index. Symbols are 0..255, which is why a byte holds one. */
typedef struct ImpTree {
    uint16_t count[IMP_MAXBITS + 1];  /* codes of each bit length      */
    uint16_t first[IMP_MAXBITS + 1];  /* lowest code value of a length */
    uint16_t cbase[IMP_MAXBITS + 1];  /* where that run starts in sym  */
    uint8_t *sym;                     /* nsyms entries                 */
    uint8_t  maxlen;
} ImpTree;

/* Per-entry state. One allocation, so a refusal is one failure: the
 * window is the second and is sized to the dictionary the flags name. */
typedef struct ImpState {
    ImpTree  lit, len, dist;
    uint8_t  litsym[256], lensym[64], distsym[64];
    /* The bit lengths of the tree being built, by symbol. 256 covers the
     * literal tree and both 64-value ones. */
    uint8_t  lengths[256];
} ImpState;

/* 5.3.7: a count byte holding (number of RLE bytes - 1), then that many
 * bytes of "high nibble = number of values at this bit length - 1, low
 * nibble = bit length - 1".
 *
 * The tree data is read as whole BYTES and not through the bit reader,
 * which is what the reference does (`dbuf_getbyte_p` against
 * `bitrd.curpos`): the trees sit at the head of the entry and the token
 * stream's bit numbering starts after them.
 *
 * The count must come to EXACTLY the alphabet's size. 5.3.4/5.3.5/5.3.6
 * fix those at 256, 64 and 64, and the reference says the same in
 * prose — "the Implode specification apparently requires the trees to
 * always be fully populated". A stream that says otherwise is corrupt,
 * and this is where a bent one is turned away. */
static int imp_read_lengths(UncBufIn *in, uint8_t *lengths, uint32_t nsyms)
{
    int b = unc_bufin_next(in);
    uint32_t nrle, i, next = 0;

    if (b < 0) return in->err;
    nrle = (uint32_t)b + 1u;
    for (i = 0; i < nrle; i++) {
        uint32_t n, l, k;

        b = unc_bufin_next(in);
        if (b < 0) return in->err;
        n = ((uint32_t)b >> 4) + 1u;        /* values at this length   */
        l = ((uint32_t)b & 0x0Fu) + 1u;     /* the length itself       */
        if (next + n > nsyms) return UNC_ERR_CORRUPT;
        for (k = 0; k < n; k++) lengths[next++] = (uint8_t)l;
    }
    if (next != nsyms) return UNC_ERR_CORRUPT;
    return UNC_OK;
}

/* 5.3.8, steps 1, 2 and 4, without step 3.
 *
 * Step 3 reverses every code so that its most significant bit becomes
 * its least significant, and step 3 is NOT performed: the token stream
 * hands its bits over least-significant-first within each byte
 * (5.3.9 through `unc_bitin_init_le`), so accumulating a code
 * most-significant-bit-first out of that stream — which is what
 * `imp_decode` below does, and what the reference's bit-serial tree walk
 * does — IS the reversal. The two readings were checked against each
 * other on every tree in reach (DECISIONS.md 2026-10-07).
 *
 * Steps 1 and 2 together are: visit the symbols longest code first, and
 * within one length in DECREASING symbol order; give the first a code of
 * zero; and for each one after it take the previous code, shift it right
 * by the drop in length, and add one. That is the reference's
 * `fmtutil_huffman_make_canonical_tree2` driven over the length array
 * reversed, which is what its two flags
 * (LEFT_ALIGN_BRANCHES | LAST_CODE_FIRST) ask for.
 *
 * It is NOT this engine's canonical coder (`unc_canon_build`), whose
 * codes run the other way: shortest first, all-zeros at the shortest
 * length, ascending by symbol. */
static int imp_build(ImpTree *t, const uint8_t *lengths, uint32_t nsyms)
{
    uint32_t code = 0, prevlen = 0;
    uint32_t l, i, slot = 0;
    int first = 1;

    for (l = 0; l <= IMP_MAXBITS; l++)
        t->count[l] = t->first[l] = t->cbase[l] = 0;
    t->maxlen = 0;

    for (l = IMP_MAXBITS; l >= 1; l--) {
        uint32_t runstart = slot;
        /* Decreasing symbol order: step 1's sort is stable, so reading
         * it back from the end visits each length's symbols that way. */
        i = nsyms;
        while (i-- > 0) {
            if (lengths[i] != l) continue;
            if (first) { code = 0; first = 0; }
            else code = (code >> (prevlen - l)) + 1u;
            prevlen = l;
            if (code >= (1u << l)) return UNC_ERR_CORRUPT;
            if (t->count[l] == 0) t->first[l] = (uint16_t)code;
            t->count[l]++;
            t->sym[slot++] = (uint8_t)i;
        }
        if (t->count[l]) {
            t->cbase[l] = (uint16_t)runstart;
            if (t->maxlen == 0) t->maxlen = (uint8_t)l;
        }
    }
    /* A tree with no codes at all decodes nothing, and the alphabet
     * sizes above make it unreachable; refuse it rather than loop. */
    return t->maxlen ? UNC_OK : UNC_ERR_CORRUPT;
}

/* One code, bit-serially: take a bit, make it the next
 * least-significant bit of the code, and ask whether a code of the
 * length so far starts where this one does. The same walk
 * `unc_canon_decode` falls back to, over this format's own run table. */
static int imp_decode(const ImpTree *t, UncBitIn *bi)
{
    uint32_t code = 0;
    uint32_t l;

    for (l = 1; l <= (uint32_t)t->maxlen; l++) {
        int bit = unc_bitin_bit(bi);
        if (bit < 0) return -1;
        code = (code << 1) | (uint32_t)bit;
        if (t->count[l] && code - t->first[l] < t->count[l])
            return t->sym[t->cbase[l] + (code - t->first[l])];
    }
    return -2;                  /* no code of any length: corrupt */
}

/* Hand over what the window has taken since the last flush, and take the
 * CRC-32 of the same span. The window wraps, so a span crossing its end
 * is two writes — the shape is sit14_flush's (src/sit14.c). */
static int imp_flush(const uint8_t *win, uint32_t dict, uint32_t from,
                     uint32_t to, uint32_t *crc,
                     int (*emit)(void *, const uint8_t *, int32_t),
                     void *ectx)
{
    uint32_t n = to - from, a = from & (dict - 1u);

    if (n == 0) return UNC_OK;
    if (a + n > dict) {
        int err;
        *crc = unc_crc32(*crc, win + a, (int32_t)(dict - a));
        err = emit(ectx, win + a, (int32_t)(dict - a));
        if (err != UNC_OK) return err;
        n -= dict - a;
        a = 0;
    }
    *crc = unc_crc32(*crc, win + a, (int32_t)n);
    return emit(ectx, win + a, (int32_t)n);
}

static int zip_implode(UncCtx *c, UncBufIn *in, uint32_t flags, uint32_t usize,
                       uint32_t *crc, uint32_t mmlbug,
                       int (*emit)(void *, const uint8_t *, int32_t),
                       void *ectx)
{
    ImpState *s;
    uint8_t *win;
    UncBitIn bi;
    uint32_t dict = (flags & 0x0002u) ? IMP_DICT_8K : IMP_DICT_4K;
    uint32_t lowbits = (flags & 0x0002u) ? 7u : 6u;
    int three = (flags & 0x0004u) != 0;
    /* 5.3.4's rule, or PKZIP 1.01/1.02's — see the fourth parameter in
     * the comment above this file's Implode section. */
    uint32_t mml = mmlbug ? (dict == IMP_DICT_8K ? 3u : 2u)
                          : (three ? 3u : 2u);
    uint32_t mask, thresh, pos = 0, flushed = 0;
    int err;

    if (usize == 0) return UNC_OK;

    s = (ImpState *)unc_alloc(c->al, (uint32_t)sizeof *s);
    if (!s) return UNC_ERR_MEM;
    win = (uint8_t *)unc_alloc(c->al, dict);
    if (!win) { unc_free(c->al, s); return UNC_ERR_MEM; }
    /* 5.3.9: "if this position is before the start of the output stream,
     * then assume that all the data before the start of the output
     * stream is filled with zeros" — so the dictionary starts zeroed,
     * and a match that reaches back past the first byte reads those
     * zeros. 30 of the 20,247 matches in reach do (FORMATS.md). */
    {
        uint32_t i;
        for (i = 0; i < dict; i++) win[i] = 0;
    }
    mask = dict - 1u;
    thresh = dict >> 2;

    s->lit.sym = s->litsym;
    s->len.sym = s->lensym;
    s->dist.sym = s->distsym;

    /* 5.3.3: with three trees the literal tree comes first; with two the
     * length tree does, and the distance tree is last either way. */
    if (three) {
        if ((err = imp_read_lengths(in, s->lengths, 256)) != UNC_OK) goto out;
        if ((err = imp_build(&s->lit, s->lengths, 256)) != UNC_OK) goto out;
    }
    if ((err = imp_read_lengths(in, s->lengths, 64)) != UNC_OK) goto out;
    if ((err = imp_build(&s->len, s->lengths, 64)) != UNC_OK) goto out;
    if ((err = imp_read_lengths(in, s->lengths, 64)) != UNC_OK) goto out;
    if ((err = imp_build(&s->dist, s->lengths, 64)) != UNC_OK) goto out;

    unc_bitin_init_le(&bi, in);

    while (pos < usize) {
        int bit;

        if (pos - flushed >= thresh) {
            if ((err = imp_flush(win, dict, flushed, pos, crc, emit, ectx))
                    != UNC_OK)
                goto out;
            flushed = pos;
        }

        bit = unc_bitin_bit(&bi);
        if (bit < 0) { err = bi.err; goto out; }
        if (bit) {
            /* 5.3.9: a set bit is a literal — through the literal tree
             * where there is one, eight raw bits where there is not. */
            int b;
            if (three) {
                b = imp_decode(&s->lit, &bi);
                if (b < 0) { err = b == -1 ? bi.err : UNC_ERR_CORRUPT;
                             goto out; }
            } else {
                int32_t v = unc_bitin_bits_le(&bi, 8);
                if (v < 0) { err = bi.err; goto out; }
                b = (int)v;
            }
            win[pos++ & mask] = (uint8_t)b;
        } else {
            int32_t lo;
            int hi, lc;
            uint32_t distance, mlen, from;

            lo = unc_bitin_bits_le(&bi, (int)lowbits);
            if (lo < 0) { err = bi.err; goto out; }
            hi = imp_decode(&s->dist, &bi);
            if (hi < 0) { err = hi == -1 ? bi.err : UNC_ERR_CORRUPT;
                          goto out; }
            distance = ((uint32_t)hi << lowbits) | (uint32_t)lo;

            lc = imp_decode(&s->len, &bi);
            if (lc < 0) { err = lc == -1 ? bi.err : UNC_ERR_CORRUPT;
                          goto out; }
            if (lc == 63) {
                /* 5.3.9: the top length code is an escape and eight more
                 * bits follow. 249 of the matches in reach take it. */
                int32_t v = unc_bitin_bits_le(&bi, 8);
                if (v < 0) { err = bi.err; goto out; }
                mlen = mml + 63u + (uint32_t)v;
            } else {
                mlen = mml + (uint32_t)lc;
            }

            /* "move backwards Distance+1 bytes in the output stream":
             * masked, which is the same slot for every distance the
             * dictionary can hold, and the zeros above for the rest. A
             * match may overlap its own output (347 in reach do), so it
             * is copied one byte at a time. */
            from = pos - 1u - distance;
            while (mlen-- > 0 && pos < usize) {
                win[pos & mask] = win[from++ & mask];
                pos++;
            }
            /* No flush inside that loop, and it is not an omission: the
             * test at the head of the while reserves a quarter of the
             * window, and the longest match the format can state is
             * mml + 63 + 255 = 321 bytes, so `pos - flushed` cannot pass
             * (dict/4 - 1) + 321 — 1,344 against the 4,096 of the
             * smaller dictionary. Unflushed bytes therefore cannot be
             * overwritten, and a check here could not fire. */
        }
    }

    err = imp_flush(win, dict, flushed, pos, crc, emit, ectx);
    /* No "short of `usize`" test here, and sit14's shape is the wrong
     * one to copy: this loop's only exit is `pos >= usize`, so such a
     * test could not fire. A stream that ends early is reported by the
     * bit reader instead — `unc_bufin_next` hits the substream's limit
     * and `bi.err` is UNC_ERR_TRUNCATED, which every read above
     * propagates. */

out:
    unc_free(c->al, win);
    unc_free(c->al, s);
    return err;
}

/* Zip method 1, Shrink, is LZW and lives with the other LZW in
 * unc_lzw.c — in the codecs image on a Macintosh, because this image is
 * at the 32 KB a 68000's 16-bit PC-relative references reach
 * (FORMATS.md, *Shrink*). This only adapts the emit. */
static int zip_put(void *ctx, const uint8_t *p, uint32_t n)
{
    return exo_emit(ctx, p, (int32_t)n);
}

/* Decode one entry's data from a reader already positioned at it (and,
 * for an encrypted entry, already past the twelve-byte encryption
 * header and reading through a cipher). Accumulates the CRC-32 the
 * caller compares against the directory's. */
static int zip_decode(UncCtx *c, UncBufIn *in, ExoSink *es, uint32_t method,
                      uint32_t flags, uint32_t usize, uint32_t *crc,
                      uint32_t mmlbug, uint8_t *obuf, uint32_t ocap)
{
    uint32_t produced = 0;
    int est;

    if (method == 6) {
        /* Implode's three parameters are in the flag word, not in the
         * stream, which is why this is the one method that needs it
         * (zip_implode, above). */
        return zip_implode(c, in, flags, usize, crc, mmlbug, zip_emit, es);
    }
    if (method == 1)
        return unc_shrink_decode(c->al, in, usize, crc, obuf, ocap,
                                 zip_put, es);
    if (method >= 2 && method <= 5)
        return unc_reduce_decode(c->al, in, method - 1u, usize, crc, obuf,
                                 ocap, zip_put, es);

    if (method == 0) {
        uint32_t left = usize;
        est = UNC_OK;
        while (left > 0) {
            int b = unc_bufin_next(in);
            if (b < 0) { est = in->err; break; }
            obuf[produced % ocap] = (uint8_t)b;
            if (++produced % ocap == 0) {
                *crc = unc_crc32(*crc, obuf, (int32_t)ocap);
                est = exo_emit(es, obuf, (int32_t)ocap);
                if (est != UNC_OK) break;
            }
            left--;
        }
        if (est == UNC_OK && produced % ocap) {
            *crc = unc_crc32(*crc, obuf, (int32_t)(produced % ocap));
            est = exo_emit(es, obuf, (int32_t)(produced % ocap));
        }
        return est;
    }

    est = unc_inflate_raw(in, c->al, obuf, ocap, usize, &produced, crc,
                          zip_emit, es);
    if (est == UNC_OK && produced != usize) est = UNC_ERR_TRUNCATED;
    return est;
}

/* Position the reader at an entry's data, past its local header's name
 * and extra field: 1 if it is there. Source: APPNOTE.TXT 4.3.7, the
 * 30-byte local header whose name and extra lengths are at +26 and +28. */
static int zip_at_data(UncCtx *c, uint32_t part, uint32_t lhoffs)
{
    uint8_t lh[30];
    return zip_seek(c, part, lhoffs) == UNC_OK &&
           unc_read_full(c->io, lh, 30) == UNC_OK &&
           lh[0] == 'P' && lh[1] == 'K' && lh[2] == 3 && lh[3] == 4 &&
           zip_skip(c, (uint32_t)unc_get_u16le(lh + 26) +
                       unc_get_u16le(lh + 28)) == UNC_OK;
}

/* ZipIt's MacBinary payload: the first 128 decoded bytes of an entry,
 * so the header can be read before begin_entry is called.
 *
 * It has to be before, not during: a MacBinary stream's two fork sizes
 * are what the entry IS, and an entry is offered to the sink with both
 * of them set. MacLHA pays the same price for the same reason and in
 * the same way — decode the entry, stop at 128 bytes, then decode it
 * again properly (fmt_lzh.c, *MacLHA's payload*). Not one header's
 * worth of decoding but one EMIT's: the decode stops at the first call
 * that completes the 128 bytes, and Shrink and stored entries call it
 * once per 8 KB of output. A stream that emits nothing decodes whole,
 * so the peek ticks through `c->ps` like zip_imp_dry, and a Cancel
 * there is returned (FORMATS.md, *Shrink*).
 *
 * Returns 1 and fills `mb` when the 128 bytes are a MacBinary header
 * whose fork spans fit inside the entry, UNC_ERR_ABORTED when the user
 * cancelled, and 0 otherwise. An ENCRYPTED entry is left
 * alone: the peek would have to derive the key and burn a password
 * attempt before the entry proper, and no ZipIt archive is in reach to
 * say whether one exists. It comes out as a single data fork, which is
 * what every version of this engine has done. */
static int zip_mb_peek(UncCtx *c, uint32_t part, uint32_t lhoffs,
                       uint32_t method, uint32_t flags,
                       uint32_t csize, uint32_t usize,
                       uint8_t *mb, uint8_t *iobuf, uint32_t iocap,
                       uint8_t *obuf, uint32_t ocap)
{
    UncBufIn in;
    ExoSink es;
    uint32_t crc = UNC_CRC32_INIT, done0;
    int err;

    if (usize < 128 || usize == UNC_SIZE_UNKNOWN) return 0;
    if (!zip_at_data(c, part, lhoffs)) return 0;

    exo_sink_init(&es, c);
    es.head = mb;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = csize;
    /* 128 is asked for and the error that the stream holds more is
     * discarded: what is being tested is whether 128 bytes came out.
     * A Cancel is not discarded: it is the user's, not the stream's.
     *
     * The `mmlbug` argument is 0 — 5.3.4's minimum match length — and
     * the probe that would say otherwise has not run yet: it is inside
     * the extract branch, after begin_entry, and this call is what
     * decides what begin_entry is TOLD. So a PKZIP 1.01-written entry
     * carrying a ZipIt `0x2605` field would have its first 128 bytes
     * read under the wrong rule and simply not look like a MacBinary
     * header. ZipIt is a Macintosh program and PKZIP 1.01 a DOS one,
     * so nothing can carry both; UNEXERCISED, and said here rather
     * than measured. */
    done0 = c->ps.done;
    err = zip_decode(c, &in, &es, method, flags, usize, &crc, 0, obuf, ocap);
    /* The entry is read again by the decode proper, which counts it; this
     * pass ticks so Cancel answers, but must not count, or the bar passes
     * 100 % on every ZipIt entry. */
    c->ps.done = done0;
    if (err == UNC_ERR_ABORTED) return UNC_ERR_ABORTED;
    if (es.headgot != 128) return 0;
    if (!unc_macbinary_probe(mb, 128, 0)) return 0;
    {
        uint32_t sec  = unc_get_u16be(mb + 120);
        uint32_t dlen = unc_get_u32be(mb + 83);
        uint32_t rlen = unc_get_u32be(mb + 87);
        uint32_t ds = 128u + ((sec + 127u) & ~127u);
        uint32_t rs = ds + ((dlen + 127u) & ~127u);
        if (dlen > usize || rlen > usize || rs + rlen > usize) return 0;
    }
    return 1;
}

/* ------------------------------------------------------------------ */
/* Which minimum match length an archive's writer used                */
/* ------------------------------------------------------------------ */

/* The two combinations where 5.3.4's rule and PKZIP 1.01/1.02's
 * disagree: bit 1 set alone (8 K, two trees — 2 by the specification,
 * 3 by the bug) and bit 2 set alone (4 K, three trees — 3 against 2).
 * With both set or neither, the two rules name the same length and
 * nothing here runs.
 *
 * Source: reference/deark/src/fmtutil-lzh.c's caller,
 * reference/deark/modules/zip.c `could_have_mml_bug` —
 * `(bit_flags & 0x6)==2 || (bit_flags & 0x6)==4`. */
static int zip_imp_ambig(uint32_t flags)
{
    return (flags & 0x0006u) == 0x0002u || (flags & 0x0006u) == 0x0004u;
}

/* Decode one Implode entry under `mmlbug` with NO output and compare
 * the CRC-32 the central directory stored.
 *
 *   1  the entry reproduces that CRC-32 under this reading
 *   0  it does not — a wrong reading, or a corrupt entry
 *  <0  the engine error that ends the walk: the user cancelled, the
 *      sink died, or the file is unreadable. Returned as itself rather
 *      than as one sentinel, so a cancellation does not come out as an
 *      I/O failure.
 *
 * A local header this cannot read is 0 and not an error: the ordinary
 * decode below seeks to the same place a moment later and reports it
 * per entry, which is what it did before this probe existed.
 *
 * Same shape as zip_mb_peek above, and for the same reason: this engine
 * streams each fork to the sink as it decodes, so by the time a CRC-32
 * mismatch is known the host has the bytes. The only place a second
 * reading can be tried is BEFORE the first byte is emitted, which makes
 * a probe pass the price of the rule (DECISIONS.md 2026-10-08, *the
 * second attempt that had nowhere to go*).
 *
 * Progress goes through `c->ps` rather than NULL, unlike zip_mb_peek's
 * 128 bytes: a probe decodes a whole entry, and on a Macintosh a decode
 * that does not tick freezes the dialog and puts Cancel out of reach. */
static int zip_imp_dry(UncCtx *c, uint32_t part, uint32_t lhoffs,
                       uint32_t flags, uint32_t csize, uint32_t usize,
                       uint32_t wantcrc, uint32_t mmlbug,
                       uint8_t *iobuf, uint32_t iocap,
                       uint8_t *obuf, uint32_t ocap)
{
    UncBufIn in;
    ExoSink es;
    uint32_t crc = UNC_CRC32_INIT;
    uint32_t done0;
    int err;

    if (!zip_at_data(c, part, lhoffs)) return 0;

    exo_sink_init(&es, c);
    es.dry = 1;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = csize;
    done0 = c->ps.done;
    err = zip_decode(c, &in, &es, 6, flags, usize, &crc, mmlbug,
                     obuf, ocap);
    c->ps.done = done0;          /* counted once, by the decode proper */
    if (unc_fatal(err)) return err;
    return err == UNC_OK && ~crc == wantcrc;
}

/* The value a central-directory field carries when the real one is in
 * the Zip64 extra field instead. Not a ceiling: the format's own
 * escape, which happens to be all-ones. */
#define ZIP64_ESC32 0xFFFFFFFFu

/* A Mac OS X sidecar, the record at `srel` of the directory in memory,
 * decoded whole. With `rsrc` 0 it is read only far enough to capture its
 * AppleDouble head, once — the file and the sidecar each ask, and the
 * capture of the last one asked is kept — and the answer is 1 if it is a
 * sidecar, 0 if it is to come out as a file, <0 a Cancel. With `rsrc` 1,
 * after its file's data fork, entry 2's span goes to the sink and the
 * sidecar's own CRC-32 is checked: one that fails it fails its file.
 *
 * The first pass is zip_mb_peek's, and for the same reason: the fork's
 * size and the Finder info are what the FILE's entry is offered with, and
 * the sidecar may come after it. Its fields are the central record's own
 * — flags +8, method +10, CRC-32 +16, sizes +20 and +24, start disk +34,
 * local header +42 (APPNOTE.TXT 4.3.12) — and an encrypted one, or one
 * whose sizes need Zip64, is not paired: it comes out as itself. */
static int zip_side(UncCtx *c, UncSideZip *z, uint32_t srel, int rsrc,
                    uint8_t *iobuf, uint32_t iocap,
                    uint8_t *obuf, uint32_t ocap)
{
    const uint8_t *cd = z->cd + srel;
    uint32_t csize = unc_get_u32le(cd + 20), usize = unc_get_u32le(cd + 24);
    uint32_t flags = unc_get_u16le(cd + 8);
    uint32_t crc = UNC_CRC32_INIT, done0 = c->ps.done;
    UncBufIn in;
    ExoSink es;
    int err;

    if (!rsrc) {
        if (z->caprel == srel) return z->cap.state == UNC_AD_YES;
        z->caprel = srel;
        unc_ad_init(&z->cap, usize);
        if ((flags & 0x0001) || csize == ZIP64_ESC32 || usize == ZIP64_ESC32)
            goto peeked;
    }
    if (!zip_at_data(c, unc_get_u16le(cd + 34), unc_get_u32le(cd + 42))) {
        if (rsrc) return UNC_ERR_CORRUPT;
        goto peeked;
    }
    exo_sink_init(&es, c);
    if (rsrc) {
        es.split = 1;
        es.rs = z->cap.roff;
        es.re = z->cap.roff + z->cap.rlen;
    } else {
        es.side = &z->cap;
    }
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = csize;
    err = zip_decode(c, &in, &es, unc_get_u16le(cd + 10), flags, usize,
                     &crc, 0, obuf, ocap);
    if (rsrc)
        return err == UNC_OK && ~crc != unc_get_u32le(cd + 16)
             ? UNC_ERR_CRC : err;
    c->ps.done = done0;              /* counted by the fork's own pass */
    if (err == UNC_ERR_ABORTED) {
        z->caprel = UNC_SIZE_UNKNOWN;
        return err;
    }
  peeked:
    unc_ad_end(&z->cap);
    return z->cap.state == UNC_AD_YES;
}

/* 0x334d's Finder flags and dates, which the CENTRAL directory does not
 * carry: deark's ef_infozipmac reads type and creator and then
 * `if(eii->is_central) goto done`, and every field measured here is
 * exactly 14 bytes long for that reason. The rest of the record is in
 * the LOCAL header, and is DEFLATED unless flag 0x0004 says otherwise.
 *
 * The attribute record, once uncompressed — all little-endian:
 *   0  fdFlags Short, fdLocation.v/.h Short, fdFldr Short
 *   8  FXInfo 16 bytes
 *   24 FVersNum Byte, ACUser Byte
 *   26 FlCrDat, FlMdDat, FlBkDat ULong
 *   38 CrGMTOffs, MdGMTOffs, BkGMTOffs Long, signed — OPTIONAL
 * Source: reference/notes/zip_extrafld_infozip.txt, *Attributes*.
 *
 * The three dates are taken UNADJUSTED, and that is the one place
 * this differs from both reference implementations. The document says
 * of them: "These time numbers are original Mac FileTime values
 * (local time!)", and of the offsets that they "may be used to
 * support timestamp adjustment after inter-timezone transfer". This
 * engine's consumer is `ioFlCrDat`/`ioFlMdDat` (mac/macextract_mac.c),
 * which are local Mac times — so the stored value is already the
 * wanted one and adding the offset would move every date by a
 * timezone. XADMaster adds it because it is building an absolute
 * NSDate; that is right for XADMaster and wrong here.
 *
 * THE TWO REFERENCE IMPLEMENTATIONS DISAGREE ON THE SIGN, so neither
 * adjudicates this: XADMaster does `create += readInt32LE` and deark
 * does `de_mac_time_to_timestamp(mt_raw - mt_offset)`, and both then
 * label the result UTC. They cannot both be right. The document is
 * what settles it, and it settles it by making the question moot —
 * FlCrDat is the local Mac time already, and local is what the sink
 * wants, so no offset of either sign enters.
 *
 * The choice IS observable here and has no oracle: every entry of
 * rexnebular_1_0_0.zip carries CrGMTOffs = MdGMTOffs = BkGMTOffs =
 * -18000, so this engine's dates stand 5 h from `lsar`'s on all 22.
 * A MacZip fixture whose dates were graded against `lsar` would fail
 * on that difference, and the failure would be the oracle's.
 *
 * Flag bit 3 (64-bit dates) refuses the record: this engine's dates
 * are uint32. Bit 4 says the offsets are ABSENT, which costs nothing
 * now that they are not wanted.
 *
 * Only ever called for an entry whose central record carried a 0x334d,
 * so an archive with no Macintosh field in it pays nothing at all —
 * not the seek, not the read, and not the inflate. */
#define ZIP_MACATTR_WANT 38u    /* through FlBkDat */

/* The record is read as it inflates: the first 38 bytes kept, the GMT
 * offsets and the charset skipped (`fixed` is where they end), then the
 * FullPath C-string skipped and the Finder comment C-string copied into
 * `cmt`, which may be NULL. */
typedef struct {
    uint8_t  buf[ZIP_MACATTR_WANT];
    uint32_t got, fixed;
    uint8_t  strs;               /* C-strings ended: 0 path, 1 comment */
    uint8_t *cmt;
    uint32_t clen;
} ZipAttrSink;

static int zip_attr_emit(void *ctx, const uint8_t *p, int32_t n)
{
    ZipAttrSink *a = (ZipAttrSink *)ctx;
    for (; n > 0; n--, p++) {
        if (a->got < a->fixed) {
            if (a->got < ZIP_MACATTR_WANT) a->buf[a->got] = *p;
            a->got++;
        } else if (a->strs < 2) {
            if (!*p) a->strs++;
            else if (a->strs == 1 && a->cmt && a->clen < UNC_ENTRY_COMMENT_MAX)
                a->cmt[a->clen++] = *p;
        }
    }
    return UNC_OK;
}

/* A 0x334d date, local Macintosh time (above). Below one day is "never
 * set", as both reference implementations have it; so, here, is the
 * last day before the wrap: rexnebular_1_0_0.zip's backup fields read
 * 0 on some entries and 0xFFFFAB9F (-21,601 s) on the rest, beside a
 * BkGMTOffs of -18000 on all, and a backup in February 2040 is not one.
 * That the second value is "never" moved by a zone is a hypothesis
 * (DECISIONS.md 2026-10-17, *the archives' own Finder info*). */
static int zip_mac_date_ok(uint32_t t)
{
    return t >= 86400u && t <= 0xFFFFFFFFu - 86400u;
}

/* `cmt` is where a Finder comment goes, UNC_ENTRY_COMMENT_MAX bytes, or
 * NULL for none; returns its length. */
static uint32_t zip_mac_attrs(UncCtx *c, uint32_t part, uint32_t lhoffs,
                              UncEntryInfo *e, uint8_t *cmt)
{
    uint8_t lh[30];
    uint8_t ex[256];
    uint32_t lnamelen, lextralen, exlen, q;

    if (zip_seek(c, part, lhoffs) != UNC_OK ||
        unc_read_full(c->io, lh, 30) != UNC_OK)
        return 0;
    if (!(lh[0] == 'P' && lh[1] == 'K' && lh[2] == 3 && lh[3] == 4)) return 0;
    lnamelen  = unc_get_u16le(lh + 26);
    lextralen = unc_get_u16le(lh + 28);
    if (!lextralen) return 0;
    exlen = lextralen < sizeof ex ? lextralen : (uint32_t)sizeof ex;
    if (zip_seek(c, part, lhoffs + 30 + lnamelen) != UNC_OK ||
        unc_read_full(c->io, ex, (int32_t)exlen) != UNC_OK)
        return 0;

    for (q = 0; q + 4 <= exlen; ) {
        uint32_t id = unc_get_u16le(ex + q);
        uint32_t sz = unc_get_u16le(ex + q + 2);
        const uint8_t *d = ex + q + 4;
        if (sz + 4u > exlen - q) break;
        if (id != 0x334d || sz < 14) { q += 4 + sz; continue; }
        {
            uint32_t ulen = unc_get_u32le(d);
            uint32_t fl   = unc_get_u16le(d + 4);
            ZipAttrSink a;
            uint32_t k;
            int ok = 0;

            if (fl & 0x0008) return 0;   /* 64-bit dates: not read */
            a.got = 0;
            a.fixed = ZIP_MACATTR_WANT + ((fl & 0x0010) ? 0u : 12u) + 2u;
            a.strs = 0;
            a.cmt = cmt;
            a.clen = 0;
            if (fl & 0x0004) {
                /* Stored in the field itself, right after type and
                 * creator — no compression method and no CRC. */
                (void)zip_attr_emit(&a, d + 14, (int32_t)(sz - 14));
                ok = 1;
            } else if (sz >= 20 && unc_get_u16le(d + 14) == 8 &&
                       ulen >= ZIP_MACATTR_WANT && ulen <= 1000000u) {
                /* u16le method (8 = deflate), u32le CRC, then the
                 * stream. Anything else — Info-ZIP could in principle
                 * write method 6 there, which deark declines too — is
                 * left unread rather than guessed at. */
                uint8_t iobuf[128], obuf[64];
                UncBufIn in;
                uint32_t produced = 0;
                unc_bufin_init(&in, c->io, NULL, iobuf, (uint32_t)sizeof iobuf);
                in.limit = sz - 20;
                ok = zip_seek(c, part, lhoffs + 30 + lnamelen + q + 4 + 20)
                         == UNC_OK &&
                     unc_inflate_raw(&in, c->al, obuf, (uint32_t)sizeof obuf,
                                     ulen, &produced, NULL,
                                     zip_attr_emit, &a) == UNC_OK;
            }
            if (!ok || a.got < ZIP_MACATTR_WANT) return 0;
            /* The whole FInfo/DInfo and FXInfo/DXInfo, put back into
             * Macintosh order: type and creator are the field's own four
             * bytes each (a folder's frRect, `docs/` above), the rest
             * little-endian words and one long, as Info-ZIP's own
             * Macintosh UnZip reads them.
             * Source: unzip60/macos/source/macos.c, DecodeMac3ExtraField
             * (fdFlags, fdLocation.v/.h, fdFldr, fdIconID, three
             * fdReserved words, the fdScript and fdXFlags bytes,
             * fdComment, the fdPutAway long, then FVersNum and ACUser,
             * the three dates, the GMT offsets unless flag bit 4, the
             * TextEncodingBase word, FullPath and FinderComment as
             * C-strings); reference/notes/zip_extrafld_infozip.txt is
             * the same table. */
            for (k = 0; k < 8; k++) e->finder_info[k] = d[6 + k];
            for (k = 0; k < 8; k += 2) {
                e->finder_info[8 + k] = a.buf[k + 1];
                e->finder_info[9 + k] = a.buf[k];
                e->finder_info[16 + k] = a.buf[8 + k + 1];
                e->finder_info[17 + k] = a.buf[8 + k];
            }
            e->finder_info[24] = a.buf[16];
            e->finder_info[25] = a.buf[17];
            e->finder_info[26] = a.buf[19];
            e->finder_info[27] = a.buf[18];
            for (k = 0; k < 4; k++) e->finder_info[28 + k] = a.buf[23 - k];
            e->meta |= UNC_META_FINFO | UNC_META_FXINFO;
            e->finder_flags = unc_get_u16le(a.buf);
            {
                uint32_t cr = unc_get_u32le(a.buf + 26);
                uint32_t mo = unc_get_u32le(a.buf + 30);
                uint32_t bk = unc_get_u32le(a.buf + 34);
                if (zip_mac_date_ok(cr)) e->create_date = cr;
                if (zip_mac_date_ok(mo)) e->mod_date = mo;
                if (zip_mac_date_ok(bk)) {
                    e->backup_date = bk;
                    e->meta |= UNC_META_BACKUP;
                }
            }
            return a.clen;
        }
    }
    return 0;
}

/* One central-directory record's extra fields. Four matter here:
 * WinZip's AES (0x9901), Zip64 (0x0001), and the two Macintosh writers'
 * fields that carry Finder metadata — Info-ZIP's 0x334d and ZipIt's
 * 0x2705/0x2805.
 *
 * A Zip64 field holds only those values whose central-directory field
 * carries the escape (0xFFFFFFFF, or 0xFFFF for a disk number), in the
 * fixed order uncompressed size, compressed size, local-header offset,
 * start disk — so the record has to be walked in order, not indexed, and
 * the scan cannot stop at the first field it recognises.
 * Source: APPNOTE.TXT 4.5.3 — "the order of the fields in the zip64
 * extended information record is fixed, but the fields MUST only appear
 * if the corresponding Local or Central directory record field is set
 * to 0xFFFF or 0xFFFFFFFF".
 *
 * Each Zip64 value is 64 bits and this engine addresses 32, so the low
 * half is taken and the high half must be zero — the same rule the
 * end-of-central-directory record is read by (DECISIONS.md 2026-08-25).
 * A high half that is set refuses that ENTRY and leaves the walk alone
 * (UNC_ERR_TOOLARGE), whether it is a size this engine cannot hold or a
 * position it cannot reach. The ARCHIVE-level Zip64 fields are a
 * different refusal: they end the walk with UNC_ERR_UNSUPPORTED,
 * because without them there is no directory to walk. */
typedef struct {
    uint32_t usize, csize, lhoffs, startdisk;
    int      aeskeybytes, aesversion;
    uint32_t aesmethod;
    int      err;                /* UNC_OK, or this entry's refusal */
    /* Finder metadata off a Macintosh writer's extra field. 0 means
     * "not stated", which is what UncEntryInfo already uses. */
    uint32_t mtype, mcreator;
    uint16_t mflags;
    uint8_t  mhave;              /* a Macintosh field was recognised */
    uint8_t  mbin;               /* ZipIt 0x2605 seen: the entry's data
                                  * is a MacBinary stream */
    /* ZipIt 0x2605's FileName, as an offset into the extra field and a
     * length — not a copy. The field may be in the caller's `exbuf`,
     * which is in scope for exactly as long as `ex` is, and the leaf
     * substitution is done inside that same scope. 0 means the field was
     * absent, empty, or longer than the record it sits in. */
    uint32_t mbnameoff;
    uint32_t mbnamelen;
    uint8_t  mattrs;             /* 0x334d seen: the attribute record
                                  * is in the LOCAL header, so Finder
                                  * flags and the dates need a second
                                  * read (zip_mac_attrs) */
} ZipExtra;

static void zip_extra_scan(const uint8_t *ex, uint32_t exlen,
                           uint32_t method, uint32_t flags, ZipExtra *z)
{
    /* Where this record starts within the extra field. `ex` walks
     * forward; the caller keeps the pointer it passed, so a position
     * handed back to it has to be measured from there. */
    uint32_t at0 = 0;

    while (exlen >= 4) {
        uint32_t id = unc_get_u16le(ex);
        uint32_t sz = unc_get_u16le(ex + 2);
        if (sz + 4u > exlen) break;
        if (id == 0x0001) {
            uint32_t at = 4;
            if (z->usize == ZIP64_ESC32 && at + 8u <= sz + 4u) {
                if (unc_get_u32le(ex + at + 4)) z->err = UNC_ERR_TOOLARGE;
                else z->usize = unc_get_u32le(ex + at);
                at += 8;
            }
            if (z->csize == ZIP64_ESC32 && at + 8u <= sz + 4u) {
                if (unc_get_u32le(ex + at + 4)) z->err = UNC_ERR_TOOLARGE;
                else z->csize = unc_get_u32le(ex + at);
                at += 8;
            }
            if (z->lhoffs == ZIP64_ESC32 && at + 8u <= sz + 4u) {
                if (unc_get_u32le(ex + at + 4)) z->err = UNC_ERR_TOOLARGE;
                else z->lhoffs = unc_get_u32le(ex + at);
                at += 8;
            }
            if (z->startdisk == 0xFFFFu && at + 4u <= sz + 4u)
                z->startdisk = unc_get_u32le(ex + at);
        } else if (id == 0x9901 && sz >= 7 && method == 99 &&
                   (flags & 0x0001)) {
            /* WinZip's AES puts the real compression method, the key
             * length and its own version here; method 99 means "look
             * there". Source: APPNOTE.TXT APPENDIX E, which sets the
             * compression method to 99 and names header id 0x9901, and
             * reference/notes/winzip_aes.txt, which is the layout
             * APPENDIX E points at: version (1 or 2), the two-character
             * vendor id "AE" (0x4541), a strength byte of 1, 2 or 3 for
             * a 128-, 192- or 256-bit key, then the real method. */
            uint32_t ver = unc_get_u16le(ex + 4);
            uint32_t vendor = unc_get_u16le(ex + 6);
            uint32_t strength = ex[8];
            if ((ver == 1 || ver == 2) && vendor == 0x4541 &&
                strength >= 1 && strength <= 3) {
                z->aesversion = (int)ver;
                z->aeskeybytes = (int)(8 + 8 * strength);  /* 16/24/32 */
                z->aesmethod = unc_get_u16le(ex + 9);
            }
        } else if (id == 0x334d && sz >= 14) {
            /* Info-ZIP's Macintosh field ("M3"), written by MacZip —
             * the Macintosh port of Info-ZIP's zip, which is the only
             * common writer that puts Finder metadata in a zip at all.
             * The first fourteen bytes are the whole of what the
             * CENTRAL directory carries: the uncompressed length of the
             * attribute record, a flag word, then type and creator.
             * Source: reference/notes/zip_extrafld_infozip.txt,
             * *Info-ZIP Macintosh Extra Field (new)*, which gives the
             * central-header version as exactly BSize, Flags, fdType,
             * fdCreator and stops there — the local-header version is
             * the one that goes on. APPNOTE.TXT lists 0x334d in its
             * header-id table (4.6.1) and specifies no layout for it,
             * which is why the Info-ZIP document is the citation.
             *
             * Byte-wise through unc_get_* like everything else: a
             * record at an odd offset in the extra field would fault a
             * 68000 on a word read (CLAUDE.md, 68000 discipline). */
            z->mtype = unc_get_u32be(ex + 10);
            z->mcreator = unc_get_u32be(ex + 14);
            z->mhave = 1;
            z->mattrs = 1;
        } else if (id == 0x2705 && sz >= 12 &&
                   unc_get_u32be(ex + 4) == 0x5A504954ul) {
            /* ZipIt's short field for FILES: the signature 'ZPIT',
             * then type and creator, then Finder flags BIG-endian.
             * Source: APPNOTE.TXT 4.6.5 — '"ZPIT" beLong
             * extra-field signature, FileType Byte[4], Creator
             * Byte[4], fdFlags beShort attributes from FInfo.frFlags,
             * MAY be omitted'. "MAY be omitted" is why the flags are
             * read only once the field is long enough to hold them,
             * and the signature is checked first because every one of
             * these three blocks is identified by it. */
            z->mtype = unc_get_u32be(ex + 8);
            z->mcreator = unc_get_u32be(ex + 12);
            if (sz >= 14) z->mflags = unc_get_u16be(ex + 16);
            z->mhave = 1;
        } else if (id == 0x2605 && sz >= 13 &&
                   unc_get_u32be(ex + 4) == 0x5A504954ul) {
            /* ZipIt's LONG field. What it says about the entry is
             * that the entry is MacBinary: APPNOTE.TXT 4.6.4 is
             * explicit — "This block MUST be present if the file is
             * stored MacBinary-encoded and it SHOULD NOT be used if
             * the file is not stored MacBinary-encoded". Its own
             * fdType and fdCreator sit behind a variable-length
             * FileName and are not read, because the MacBinary header
             * carries both and is the thing the forks are measured
             * from anyway — one source for the entry rather than two
             * that can disagree.
             *
             * The FileName IS read, since 2026-10-07, and it is the
             * name the Macintosh file HAD: APPNOTE calls it the "full
             * Macintosh filename", and where it disagrees with the
             * zip's own name it is the zip's that was converted to
             * MS-DOS form on the way in (FORMATS.md, *ZipIt's own
             * archives*). Recorded as a position, substituted by the
             * caller — see `nread` in unc_zip_extract.
             * Source: APPNOTE.TXT 4.6.4 — '"ZPIT" beLong, FnLen Byte,
             * FileName variable, FileType Byte[4], Creator Byte[4]',
             * whose minimum is the 13 bytes guarded for here, and
             * whose FnLen is what bounds the name below. */
            z->mbin = 1;
            z->mhave = 1;
            {
                uint32_t fnlen = ex[8];
                /* 'ZPIT' + FnLen + the name + fdType + fdCreator must
                 * fit the record the field declares. A FnLen that does
                 * not is a field this does not read rather than a
                 * reason to refuse the entry: everything else about it
                 * is still true. */
                if (fnlen && 4u + 1u + fnlen + 8u <= sz) {
                    z->mbnameoff = at0 + 9u;
                    z->mbnamelen = fnlen;
                }
            }
        } else if (id == 0x2805 && sz >= 6 &&
                   unc_get_u32be(ex + 4) == 0x5A504954ul) {
            /* ZipIt's short field for DIRECTORIES: 'ZPIT' then Finder
             * flags, and no type or creator — a folder has none.
             * Source: APPNOTE.TXT 4.6.6 — '"ZPIT" beLong, frFlags
             * beShort attributes from DInfo.frFlags, MAY be omitted,
             * View beShort ZipIt view flag, MAY be omitted'. */
            z->mflags = unc_get_u16be(ex + 8);
            z->mhave = 1;
        }
        ex += 4 + sz;
        exlen -= 4 + sz;
        at0 += 4 + sz;
    }
}

int unc_zip_extract(UncCtx *c)
{
    uint32_t eocd = 0, scanend;
    uint8_t *iobuf = NULL, *obuf, *cdbuf = NULL;
    UncCrypt *cr;
    uint32_t iocap = UNC_IOBUF, ocap = EXO_BUF;
    uint32_t nentries, cdoffs, cdsize, cdrel, disknum, cddisk;
    uint32_t lastpart0 = 0;
    uint8_t eo[22];
    uint8_t ce[46];
    ZipScan scan;
    uint32_t i;
    int err = UNC_OK;
    /* Mac OS X's sidecars, when the directory names any (unc_sidecar.c). */
    UncSideZip *sd = NULL;
    /* Which minimum match length this archive's Implode entries were
     * written with: -1 not settled yet, 0 APPNOTE.TXT 5.3.4's reading,
     * 1 PKZIP 1.01/1.02's. Per ARCHIVE and not per entry, which is what
     * makes the probe affordable — the pass below is paid once, not 19
     * times, on an archive of the shape PKZIP's own distribution has
     * (FORMATS.md, *Implode*, for the figures).
     *
     * That scope ASSUMES one writer per archive, and the assumption is
     * wider than the measurement behind it: no archive of the 1,537
     * swept on 2026-10-08 mixes the two readings (29,799 bug-capable
     * entries, classified per entry), but a zip is appendable and
     * PKZIP 1.1 wrote Implode too, so the format allows one that does.
     * It is BOUNDED rather than relied on — see the recovery below,
     * where an inherited verdict that turns out wrong costs the entry
     * it was wrong about and not the rest of the archive.
     *
     * Source for the architecture: reference/deark/modules/zip.c
     * `d->mml_bug_policy`, which is likewise archive-wide and set from
     * the first bug-capable member. */
    int imppol = -1;
    /* Comment buffers, allocated the first time an entry needs one: the
     * per-file comment when the directory is not in memory, and a
     * 0x334d Finder comment. Two, since an entry can have both and the
     * one kept must outlive the other's read. */
    uint8_t *cmt = NULL, *fcmt = NULL;

    /* Where the end-of-central-directory record may be. A whole archive
     * ends where the file does; a segmented one ends where its LAST
     * part does, which is where a zip writes the record. Neither needs
     * to know how big the set is altogether. */
    if (c->segmap) {
        lastpart0 = (uint32_t)c->segmap->nparts - 1u;
        scanend = c->segmap->part_size(c->segmap->ctx, c->segmap->nparts);
    } else {
        scanend = unc_io_size32(c->io);
    }
    if (scanend == UNC_SIZE_UNKNOWN || scanend < 22) return UNC_ERR_FORMAT;

    scan.c = c;
    scan.part0 = lastpart0;
    if (unc_zip_scan_eocd(&scan, zip_scan_read, scanend, &eocd) != UNC_OK)
        return UNC_ERR_FORMAT;
    err = zip_seek(c, lastpart0, eocd);
    if (err != UNC_OK) return err;
    if (unc_read_full(c->io, eo, 22) != UNC_OK) return UNC_ERR_FORMAT;

    /* "number of this disk" and "disk where the central directory
     * starts": 0 and 0 for an archive in one file. */
    disknum  = unc_get_u16le(eo + 4);
    cddisk   = unc_get_u16le(eo + 6);
    nentries = unc_get_u16le(eo + 10);
    cdsize   = unc_get_u32le(eo + 12);
    cdoffs   = unc_get_u32le(eo + 16);

    /* Zip64 end-of-central-directory, when there is one.
     *
     * Every field above is 16 or 32 bits, so an archive with more than
     * 65,535 entries (or one that outgrows 4 GB) carries the real counts
     * in a second record, and a 20-byte LOCATOR immediately before the
     * one just read says where. Without this, a 70,000-entry zip walks
     * 65,535 entries and reports success: the count does not overflow
     * into an error, it wraps into a smaller archive.
     *
     * Only the counts are taken. A value that does not fit 32 bits means
     * a file this engine cannot address at all (offsets are uint32
     * throughout, macextract.h), and is refused cleanly rather than
     * truncated — Zip64 proper stays out of scope (OPEN_ITEMS.md, part
     * 1). Both halves of each 64-bit field are read as two uint32s and
     * the high half is only ever compared against zero, so no 64-bit
     * arithmetic enters the engine.
     *
     * Source: APPNOTE.TXT 4.3.15 (the Zip64 end of central directory
     * LOCATOR, signature 0x07064b50, which says which part the record
     * is on and where) and 4.3.14 (the record itself, 0x06064b50). */
    if (eocd >= 20) {
        uint8_t lo[20];
        if (zip_seek(c, lastpart0, eocd - 20) == UNC_OK &&
            unc_read_full(c->io, lo, 20) == UNC_OK &&
            unc_get_u32le(lo) == 0x07064b50u) {
            uint32_t z64disk = unc_get_u32le(lo + 4);
            uint32_t z64lo   = unc_get_u32le(lo + 8);
            uint32_t z64hi   = unc_get_u32le(lo + 12);
            uint8_t  z6[56];

            if (z64hi != 0) return UNC_ERR_UNSUPPORTED;
            err = zip_seek(c, z64disk, z64lo);   /* SEGMENTED if the
                                                  * record is on a part
                                                  * we were not given */
            if (err != UNC_OK) return err;
            if (unc_read_full(c->io, z6, 56) != UNC_OK)
                return UNC_ERR_TRUNCATED;
            if (unc_get_u32le(z6) == 0x06064b50u) {
                /* numentries, central size and central offset are each
                 * 64-bit here; the high half of any of them puts the
                 * archive out of reach. */
                if (unc_get_u32le(z6 + 36) != 0 ||
                    unc_get_u32le(z6 + 44) != 0 ||
                    unc_get_u32le(z6 + 52) != 0)
                    return UNC_ERR_UNSUPPORTED;
                disknum  = unc_get_u32le(z6 + 16);
                cddisk   = unc_get_u32le(z6 + 20);
                nentries = unc_get_u32le(z6 + 32);
                cdsize   = unc_get_u32le(z6 + 40);
                cdoffs   = unc_get_u32le(z6 + 48);
            }
        }
    }

    /* The set the archive says it is must be the set that was assembled.
     * This is the check that catches parts put in the wrong order or
     * taken from the wrong archive, because filenames put them there and
     * a filename is evidence of nothing (see macextract.h). */
    if (!c->segmap) {
        if (disknum != 0) return UNC_ERR_SEGMENTED;
    } else if ((uint32_t)c->segmap->nparts != disknum + 1) {
        return UNC_ERR_CORRUPT;
    }

    /* The archive's OWN comment, which a zip writes immediately after
     * the record just read. It belongs to no entry, so it leaves by the
     * sink's own callback, once, before the first begin_entry — the
     * same route Compact Pro's takes (fmt_cpt.c).
     *
     * It gets an allocation of its own, freed before the extraction
     * buffers are taken, so a comment shows up in peak RAM only while
     * it is being delivered and a host with no comment callback pays
     * nothing at all. zip states the length in 16 bits, so the ceiling
     * is 64 KB; the one corpus archive that has a comment has 495
     * bytes of it. An allocation that fails drops the comment and
     * extracts the archive, because the comment is worth less than the
     * entries — the same trade both hosts already make when they
     * cannot write it out (cli/main.c, mac/macextract_mac.c).
     *
     * Source: APPNOTE.TXT 4.3.16 — ".ZIP file comment length 2 bytes"
     * closes the fixed part of the record, so the length is the u16 at
     * EOCD+20 and the bytes follow it. It is what `lsar` reports as
     * XADComment. */
    {
        uint32_t clen = unc_get_u16le(eo + 20);

        /* The scanner accepts a record whose comment runs off the end
         * of the file — it only requires the fixed 22 bytes to fit
         * (fmt_zipseg.c). Bounding the length by what is actually
         * there does not change the OUTCOME, because the read below
         * would fail anyway; what it buys is the allocation, which a
         * length field of 0xFFFF would otherwise make 64 KB on a
         * machine that has a megabyte. */
        if (clen && c->sink->comment && clen <= scanend - eocd - 22u) {
            uint8_t *cbuf = (uint8_t *)unc_alloc(c->al, clen);
            if (cbuf) {
                int cret = 0;
                if (zip_seek(c, lastpart0, eocd + 22u) == UNC_OK &&
                    unc_read_full(c->io, cbuf, (int32_t)clen) == UNC_OK)
                    cret = c->sink->comment(c->sink->ctx, cbuf,
                                            (uint16_t)clen);
                unc_free(c->al, cbuf);
                if (cret < 0) return UNC_ERR_SINK;
            }
        }
    }

    /* The cipher state rides along with the two buffers: one allocation,
     * and ~450 bytes that only an encrypted archive ever touches. */
    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap + (uint32_t)sizeof *cr);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;
    cr = (UncCrypt *)(void *)(obuf + ocap);
    unc_crypt_init(cr);

    /* Read the whole central directory once, so that walking it does not
     * interleave with reading entry data. On one file that saves seeks;
     * across a set it saves going back to the last part between every
     * entry, which is a disk swap each (DECISIONS.md 2026-08-09).
     *
     * The bound is the allocator's, not a number invented here: if the
     * directory does not fit in the budget, the reader falls back to
     * fetching one record at a time, exactly as it used to. */
    if (cdsize && cdsize <= UNC_READ_MAX) {
        cdbuf = (uint8_t *)unc_alloc(c->al, cdsize);
        if (cdbuf) {
            if (zip_seek(c, cddisk, cdoffs) != UNC_OK ||
                unc_read_full(c->io, cdbuf, (int32_t)cdsize) != UNC_OK) {
                unc_free(c->al, cdbuf);
                unc_free(c->al, iobuf);
                return UNC_ERR_TRUNCATED;
            }
        }
    }

    /* Pairing a sidecar with its file wants the whole directory: without
     * it, a sidecar comes out as the file it is stored as. */
    if (cdbuf) sd = unc_side_zip_open(c->al, cdbuf, cdsize, nentries);

    cdrel = 0;                    /* bytes into the directory, either way */
    for (i = 0; i < nentries; i++) {
        uint32_t method, flags, wantcrc, csize, usize;
        uint32_t namelen, extralen, commentlen, lhoffs, startdisk;
        uint32_t mtype, mcreator;
        uint16_t mflags;
        uint8_t mattrs, mbin, mbok;
        uint8_t mb[128];
        uint32_t mbds, mbde, mbrs, mbre;
        int aeskeybytes, aesversion;
        int z64err;
        uint32_t aesmethod;
        const uint8_t *cd, *namep;
        uint8_t namebuf[256];
        uint32_t nread, plen, srel;
        int isdir, namesub;
        UncEntryInfo e;
        int sret, est;

        if (cdbuf) {
            if (cdrel + 46 > cdsize) { err = UNC_ERR_TRUNCATED; break; }
            cd = cdbuf + cdrel;
        } else {
            if (zip_seek(c, cddisk, cdoffs + cdrel) != UNC_OK ||
                unc_read_full(c->io, ce, 46) != UNC_OK) {
                err = UNC_ERR_TRUNCATED;
                break;
            }
            cd = ce;
        }
        if (!(cd[0] == 'P' && cd[1] == 'K' && cd[2] == 1 && cd[3] == 2)) {
            err = UNC_ERR_CORRUPT;
            break;
        }
        flags      = unc_get_u16le(cd + 8);
        method     = unc_get_u16le(cd + 10);
        wantcrc    = unc_get_u32le(cd + 16);
        csize      = unc_get_u32le(cd + 20);
        usize      = unc_get_u32le(cd + 24);
        namelen    = unc_get_u16le(cd + 28);
        extralen   = unc_get_u16le(cd + 30);
        commentlen = unc_get_u16le(cd + 32);
        startdisk  = unc_get_u16le(cd + 34);   /* "disk number start" */
        lhoffs     = unc_get_u32le(cd + 42);   /* relative to that disk */

        /* The name is read into `namebuf` when the record came off the
         * stream, and pointed at in place when the directory is in
         * memory — no copy, and no libc in the engine either way. */
        nread = namelen < sizeof namebuf ? namelen : (uint32_t)sizeof namebuf;
        if (cdbuf) {
            if (cdrel + 46 + nread > cdsize) { err = UNC_ERR_TRUNCATED; break; }
            namep = cdbuf + cdrel + 46;
        } else {
            namep = namebuf;
            if (nread && unc_read_full(c->io, namebuf, (int32_t)nread)
                != UNC_OK) {
                err = UNC_ERR_TRUNCATED;
                break;
            }
        }

        /* A trailing separator is what makes the record a DIRECTORY, and
         * it is read here rather than below because the leaf may be
         * replaced in between (the 0x2605 FileName, next): the field is a
         * bare name and carries no separator, so what the record said
         * about being a folder has to be taken off the record's own
         * name. */
        plen = nread;
        isdir = plen > 0 && namep[plen - 1] == '/';
        while (plen > 0 && namep[plen - 1] == '/') plen--;
        namesub = 0;
        /* The folders Mac OS X keeps its sidecars in are not the user's:
         * never emitted (XADMacArchiveParser.m, -addEntryWithDictionary:). */
        if (isdir && unc_side_kind(namep, plen, 1) == UNC_SIDE_DIR)
            goto next_rec;

        /* The extra fields, for AES and for Zip64. Where the directory
         * is in memory they are read in place; where it is being
         * streamed a record at a time they are fetched behind the name,
         * bounded by `exbuf` — a Zip64 field is 32 bytes at most and an
         * AES one 11, and both are written first by every writer seen. */
        {
            ZipExtra z;
            uint8_t exbuf[64];
            const uint8_t *ex = NULL;
            uint32_t exlen = 0;

            z.usize = usize;
            z.csize = csize;
            z.lhoffs = lhoffs;
            z.startdisk = startdisk;
            z.aeskeybytes = 0;
            z.aesversion = 0;
            z.aesmethod = method;
            z.err = UNC_OK;
            z.mtype = 0;
            z.mcreator = 0;
            z.mflags = 0;
            z.mhave = 0;
            z.mattrs = 0;
            z.mbin = 0;
            z.mbnameoff = 0;
            z.mbnamelen = 0;
            if (cdbuf) {
                if (extralen && cdrel + 46 + namelen + extralen <= cdsize) {
                    ex = cdbuf + cdrel + 46 + namelen;
                    exlen = extralen;
                }
            } else if (extralen) {
                exlen = extralen < sizeof exbuf ? extralen
                                                : (uint32_t)sizeof exbuf;
                if (zip_seek(c, cddisk, cdoffs + cdrel + 46 + namelen)
                        == UNC_OK &&
                    unc_read_full(c->io, exbuf, (int32_t)exlen) == UNC_OK)
                    ex = exbuf;
                else
                    exlen = 0;
            }
            if (ex) zip_extra_scan(ex, exlen, method, flags, &z);
            /* A value the escape stands for and Zip64 did not supply
             * stays 0xFFFFFFFF, which is UNC_SIZE_UNKNOWN: the entry
             * lists with `?` for its size, exactly as an oversized tar
             * member does. */
            usize = z.usize;
            csize = z.csize;
            lhoffs = z.lhoffs;
            startdisk = z.startdisk;
            aeskeybytes = z.aeskeybytes;
            aesversion = z.aesversion;
            aesmethod = z.aesmethod;
            z64err = z.err;
            mtype = z.mtype;
            mcreator = z.mcreator;
            mflags = z.mflags;
            mattrs = z.mattrs;
            mbin = z.mbin;

            /* ZipIt's 0x2605 FileName becomes the leaf this entry comes
             * out under, since 2026-10-07. APPNOTE.TXT 4.6.4 calls it
             * the "full Macintosh filename", and it is the right name in
             * every field in reach: where it disagrees with the zip's
             * own, it is the zip's that went through ZipIt's "dosify
             * filenames" conversion on the way in (FORMATS.md, *ZipIt's
             * own archives*).
             *
             * It is a LEAF and not a path, so only the last component
             * moves and the enclosing folders keep whatever the zip
             * called them. In the one archive here where this fires that
             * leaves `PSYCHO!/` upper-cased: 3 of its 4 wrong
             * components, not 4.
             *
             * Built in `namebuf`, which in the streamed case already
             * holds the record's name and in the in-memory case is
             * otherwise unused — so there is no second buffer and the
             * 256 B it costs this frame were already being paid. The
             * field is in `ex`, which is `cdbuf` or `exbuf` and never
             * `namebuf`, so the source and the destination cannot
             * overlap.
             *
             * NOT done when the record's own name did not fit `namebuf`:
             * the directory prefix would be measured from a cut path,
             * and such an entry is reported truncated instead. The
             * longest name in the corpus is 120 bytes. */
            if (z.mbnamelen && ex && namelen <= nread) {
                uint32_t dir = plen, k;
                while (dir > 0 && namep[dir - 1] != '/') dir--;
                if (dir + z.mbnamelen <= sizeof namebuf) {
                    for (k = 0; k < dir; k++) namebuf[k] = namep[k];
                    for (k = 0; k < z.mbnamelen; k++) {
                        uint8_t ch = ex[z.mbnameoff + k];
                        /* The engine's own path rule, applied here for
                         * the first time to a name a FORMAT stated
                         * rather than one a walk built: a '/' can occur
                         * in an HFS name and a ':' cannot, so the two
                         * are swapped per component (DECISIONS.md M4,
                         * unc_entry_path_append). Without it a field
                         * could put a separator inside a leaf and
                         * invent a folder. UNEXERCISED: not one of the
                         * 23 fields in reach holds a '/' (FORMATS.md,
                         * *Implode, and what the corpus cannot reach*). */
                        namebuf[dir + k] = ch == '/' ? (uint8_t)':' : ch;
                    }
                    namep = namebuf;
                    plen = dir + z.mbnamelen;
                    namesub = 1;
                }
            }
        }

        unc_entry_clear(&e);
        {
            unc_entry_set_path(&e, namep, plen);  /* '/' native, raw bytes */
            /* The record's name was cut to `namebuf` before the funnel
             * could see how long it really was. `namesub` cannot be set
             * here — a substitution is refused on a cut name — and the
             * test is written against it anyway, so that the two can
             * never both be true silently. */
            if (namelen > nread && !namesub) {
                e.name_truncated = 1;
                e.name_full_len = (uint16_t)(namelen > 65535u ? 65535u
                                                              : namelen);
                /* Where the directory is in memory the whole name is
                 * still there, so a host with room can be given it. */
                if (cdbuf && cdrel + 46 + namelen <= cdsize)
                    unc_entry_long_name(c, &e, cdbuf + cdrel + 46, namelen);
            }
            e.is_dir = (uint8_t)isdir;
        }
        e.data_size = e.is_dir ? 0 : usize;
        e.comp_data_size = csize;
        e.rsrc_size = 0;
        e.method_data = (uint8_t)(method > 255 ? 255 : method);
        /* Finder metadata, where a Macintosh writer stated it. A
         * DIRECTORY is given its Finder flags and no type or creator:
         * both reference implementations read 0x334d's type/creator
         * slots unconditionally, but a folder has neither, and MacZip
         * fills them with DInfo bytes instead — `docs/` in
         * rexnebular_1_0_0.zip reads 0x002f000c/0x0154012b, which is a
         * rectangle and a point, not two codes. ZipIt says the same by
         * construction: its directory field (0x2805) has no room for
         * them at all. */
        e.finder_flags = mflags;
        if (!e.is_dir) {
            e.type = mtype;
            e.creator = mcreator;
        }
        /* The record's MS-DOS time and date at +12/+14, local time with
         * no zone (APPNOTE.TXT 4.4.6: "stored in standard MS-DOS
         * format"); a Macintosh field's own dates replace them below. */
        e.mod_date = unc_dos_to_mac(unc_get_u16le(cd + 14),
                                    unc_get_u16le(cd + 12));
        /* Locked, from the external attributes at +38, read as the
         * version-made-by host at +5 says (APPNOTE.TXT 4.4.2, 4.4.15).
         * Hosts whose high half is a POSIX mode — Info-ZIP's own list
         * for Unix, VMS, Atari, QDOS, Acorn, BeOS, Tandem, THEOS and
         * AtheOS — are locked when it has no owner write (0200), unless
         * the half is 0, where UnZip falls back to the DOS byte too.
         * Every other host, Macintosh (7) included, by the MS-DOS
         * read-only bit (0x01) of the low byte. Amiga's protection bits
         * are not read. Source: unzip60/unix/unix.c, mapattr; and for
         * host 7, unzip60/macos/source/macos.c, mapattr ("only care
         * about read-only bit, so just look at MS-DOS side of attrs")
         * then FSpSetFLock — MacZip's own UnZip locks the file from
         * that bit, whatever the host. Measured on
         * rexnebular_1_0_0.zip, host 7: 0x81240001 on its read-only
         * disk images, 0x81b60000 on the rest. */
        {
            uint32_t host = cd[5], xa = unc_get_u32le(cd + 38);
            if (host != 1) {
                if (host <= 30 && ((0x4007302Cul >> host) & 1u) &&
                    (xa >> 16))
                    e.locked = (xa & 0x00800000ul) ? UNC_LOCK_NO
                                                   : UNC_LOCK_YES;
                else
                    e.locked = (xa & 1u) ? UNC_LOCK_YES : UNC_LOCK_NO;
            }
        }
        /* The per-file comment after the name and extra field: in place
         * where the directory is in memory, copied otherwise. A
         * 0x334d Finder comment, which IS the Get Info comment, wins
         * over it below. */
        if (commentlen) {
            uint32_t cl = commentlen < UNC_ENTRY_COMMENT_MAX
                        ? commentlen : UNC_ENTRY_COMMENT_MAX;
            uint32_t at = cdrel + 46 + namelen + extralen;
            if (cdbuf) {
                if (at + cl <= cdsize) {
                    e.comment = cdbuf + at;
                    e.comment_len = (uint16_t)cl;
                }
            } else {
                if (!cmt) cmt = (uint8_t *)unc_alloc(c->al,
                                                     UNC_ENTRY_COMMENT_MAX);
                if (cmt && zip_seek(c, cddisk, cdoffs + at) == UNC_OK &&
                    unc_read_full(c->io, cmt, (int32_t)cl) == UNC_OK) {
                    e.comment = cmt;
                    e.comment_len = (uint16_t)cl;
                }
            }
        }
        if (mattrs) {
            uint32_t fcl;
            if (!fcmt) fcmt = (uint8_t *)unc_alloc(c->al,
                                                   UNC_ENTRY_COMMENT_MAX);
            fcl = zip_mac_attrs(c, startdisk, lhoffs, &e, fcmt);
            if (fcl) {
                e.comment = fcmt;
                e.comment_len = (uint16_t)fcl;
            }
        }

        /* ZipIt's long field: the entry's data is a MacBinary stream,
         * and what the entry is called for is inside its header. */
        mbok = 0;
        mbds = mbde = mbrs = mbre = 0;
        sret = mbin && !e.is_dir && !(flags & 0x0001)
             ? zip_mb_peek(c, startdisk, lhoffs, method, flags, csize, usize,
                           mb, iobuf, iocap, obuf, ocap) : 0;
        if (sret < 0) { err = sret; break; }
        if (sret) {
            uint32_t sec  = unc_get_u16be(mb + 120);
            uint32_t dlen = unc_get_u32be(mb + 83);
            uint32_t rlen = unc_get_u32be(mb + 87);
            mbds = 128u + ((sec + 127u) & ~127u);
            mbde = mbds + dlen;
            mbrs = mbds + ((dlen + 127u) & ~127u);
            mbre = mbrs + rlen;
            e.data_size = dlen;
            e.rsrc_size = rlen;
            /* Finder info, lock and dates, as fmt_macbinary.c reads a
             * header; not the comment, which is after both forks in a
             * stream not yet decoded (fmt_lzh.c says the same). */
            {
                /* A header that leaves a date 0 (MacLHA 2.00 writes both so)
                 * leaves this container's own one standing. */
                uint32_t crd = e.create_date, mdd = e.mod_date;
                (void)unc_macbinary_meta(&e, mb);
                if (!e.create_date) e.create_date = crd;
                if (!e.mod_date) e.mod_date = mdd;
            }
            mbok = 1;
        }

        /* A Mac OS X sidecar: put on its file, which takes its Finder
         * info, comment, dates, lock and resource fork; not emitted itself
         * when its file takes it. One that pairs with nothing, or is not
         * AppleDouble, comes out as itself. */
        srel = UNC_SIZE_UNKNOWN;
        if (sd && !mbok) {
            int side;
            uint32_t t = unc_side_zip_pair(sd, cdrel, &side);
            if (t != UNC_SIZE_UNKNOWN) {
                sret = zip_side(c, sd, side ? cdrel : t, 0,
                                iobuf, iocap, obuf, ocap);
                if (sret < 0) { err = sret; break; }
                if (sret && side) goto next_rec;
                if (sret) {
                    srel = t;
                    unc_ad_apply(&sd->cap, &e);
                    if (!e.is_dir) e.rsrc_size = sd->cap.rlen;
                }
            }
        }

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; break; }

        if (sret == 0 && e.is_dir) {
            if (c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
        } else if (sret == 0) {
            est = UNC_OK;
            if (!c->opt.list_only) {
                if ((flags & 0x0001) && (flags & 0x0040)) {
                    /* PKWARE's "strong encryption": general purpose
                     * bit 6, which APPNOTE.TXT 4.4.4 says "MUST also
                     * set bit 0". Its key material is in a record
                     * nothing here parses. OPEN_ITEMS.md. */
                    est = UNC_ERR_ENCRYPTED;
                } else if (method == 99 && (flags & 0x0001) &&
                           !aeskeybytes) {
                    /* Method 99 says "see the AES extra field", and
                     * there is not one (or it is a version or a key
                     * length this does not read). */
                    est = UNC_ERR_ENCRYPTED;
                } else if (aesmethod > 6 && aesmethod != 8) {
                    /* Stored, Shrink, the four Reduces, Implode and
                     * deflate. Method 6 joined on 2026-10-07
                     * (DECISIONS.md, *the method that was out for a
                     * premise with no halves left*), method 1 on
                     * 2026-10-08 (*the method a Macintosh wrote once*)
                     * and 2 to 5 on 2026-10-11 (*Reduce comes in*);
                     * every other method the format has ever had —
                     * DCL Implode, bzip2, LZMA, PPMd, Zstandard — is a
                     * per-entry refusal, and so is a method number
                     * nothing has defined. */
                    est = UNC_ERR_UNSUPPORTED;
                } else if (z64err != UNC_OK) {
                    /* Zip64 states this entry's size or position past
                     * what a uint32 reaches. Per entry: the directory
                     * is intact, so the next one is still found. */
                    est = z64err;
                } else {
                    /* Local header gives the true data offset (its
                     * name/extra lengths may differ from the CD's). */
                    uint8_t lh[30];
                    int attempt = 0;
                    /* Did THIS entry settle the archive's verdict, or
                     * did it inherit one? Only an inherited verdict can
                     * be wrong about the entry in front of it. */
                    int settled_here = 0;

                    /* Settle the minimum match length before a byte of
                     * this entry reaches the sink, which is the only
                     * moment a second reading can be tried at all
                     * (zip_imp_dry, above).
                     *
                     * 5.3.4 is probed FIRST and a match ends it, so a
                     * conforming archive pays one probe pass and a
                     * conforming entry at an unambiguous combination
                     * pays nothing. The 1.01/1.02 reading is adopted
                     * only on positive evidence — it reproduced the
                     * stored CRC-32 where 5.3.4 did not — and if
                     * NEITHER does, the verdict stays unsettled: the
                     * entry is corrupt rather than informative, it
                     * falls through to the ordinary decode under 5.3.4
                     * and fails with the status that decode gives it,
                     * and the next entry gets to settle the archive.
                     *
                     * Not for an ENCRYPTED entry: the probe runs before
                     * `unc_password` and must not ask twice, and the
                     * cipher would have to be re-keyed per pass. Such
                     * an entry is decoded under 5.3.4 as before. */
                    if (method == 6 && imppol < 0 && zip_imp_ambig(flags) &&
                        !(flags & 0x0001) && usize != UNC_SIZE_UNKNOWN &&
                        usize != 0) {
                        int r = zip_imp_dry(c, startdisk, lhoffs, flags,
                                            csize, usize, wantcrc, 0,
                                            iobuf, iocap, obuf, ocap);
                        if (r < 0) { est = r; goto entry_done; }
                        if (r) { imppol = 0; settled_here = 1; }
                        else {
                            r = zip_imp_dry(c, startdisk, lhoffs, flags,
                                            csize, usize, wantcrc, 1,
                                            iobuf, iocap, obuf, ocap);
                            if (r < 0) { est = r; goto entry_done; }
                            if (r) { imppol = 1; settled_here = 1; }
                        }
                    }
                  retry_entry:
                    est = zip_seek(c, startdisk, lhoffs);
                    if (est != UNC_OK) {
                        /* fall through to end_entry with this status */
                    } else if (unc_read_full(c->io, lh, 30) != UNC_OK ||
                        !(lh[0] == 'P' && lh[1] == 'K' && lh[2] == 3 &&
                          lh[3] == 4)) {
                        est = UNC_ERR_CORRUPT;
                    } else {
                        UncBufIn in;
                        uint32_t crc = UNC_CRC32_INIT;
                        ExoSink es;
                        exo_sink_init(&es, c);
                        if (mbok) {
                            es.split = 1;
                            es.ds = mbds; es.de = mbde;
                            es.rs = mbrs; es.re = mbre;
                        }
                        /* The data follows the header's own name and
                         * extra fields; skipping forward rather than
                         * seeking is what lets an entry begin in one
                         * part and continue in the next. */
                        est = zip_skip(c, (uint32_t)unc_get_u16le(lh + 26) +
                                          unc_get_u16le(lh + 28));
                        if (est == UNC_OK && aeskeybytes) {
                            /* WinZip's AES: a salt, a two-byte password
                             * verifier, the data, and ten bytes of
                             * HMAC-SHA1 over the ciphertext. The key
                             * derivation is 1000 rounds of PBKDF2 and
                             * is the slow part on a 68000 — seconds,
                             * once per entry. */
                            uint8_t hdrbuf[16 + 2];
                            uint32_t overhead =
                                (uint32_t)(aeskeybytes / 2) + 2u + 10u;
                            est = unc_password(c, attempt > 0);
                            if (est != UNC_OK) goto entry_done;
                            if (csize < overhead) { est = UNC_ERR_CORRUPT;
                                                    goto entry_done; }
                            if (unc_read_full(c->io, hdrbuf,
                                    (int32_t)(aeskeybytes / 2) + 2) != UNC_OK) {
                                est = UNC_ERR_TRUNCATED;
                                goto entry_done;
                            }
                            est = unc_crypt_winzip_aes(cr, c->pw, c->pwlen,
                                    hdrbuf, aeskeybytes,
                                    hdrbuf + aeskeybytes / 2);
                            if (est == UNC_ERR_PASSWORD) {
                                attempt++;
                                goto retry_entry;
                            }
                            unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
                            in.limit = csize - overhead;
                            in.crypt = cr;
                            est = zip_decode(c, &in, &es, aesmethod, flags,
                                             usize, &crc, 0, obuf, ocap);
                            if (est == UNC_OK) {
                                /* The ten bytes after the data are the
                                 * authentication code, and they are what
                                 * grades an AES entry: AE-2 stores no
                                 * CRC at all. */
                                uint8_t want[10], got[20];
                                unc_hmac_final(&cr->hmac, got);
                                if (unc_read_full(c->io, want, 10) != UNC_OK)
                                    est = UNC_ERR_TRUNCATED;
                                else {
                                    int q;
                                    for (q = 0; q < 10; q++)
                                        if (want[q] != got[q]) est = UNC_ERR_CRC;
                                }
                            }
                            if (est == UNC_OK && aesversion == 1 &&
                                ~crc != wantcrc)
                                est = UNC_ERR_CRC;
                            goto entry_done;
                        }
                        if (est == UNC_OK && (flags & 0x0001)) {
                            /* PKWARE's stream cipher. Twelve bytes of
                             * header come first; the last of them is a
                             * check byte — the top byte of the CRC, or
                             * of the local time field where the CRC is
                             * only in the data descriptor. One byte in
                             * 256 gets a wrong password past it, which
                             * the entry CRC then catches. */
                            uint8_t test = (uint8_t)((flags & 0x0008)
                                ? (unc_get_u32le(lh + 10) >> 8)
                                : (wantcrc >> 24));
                            est = unc_password(c, attempt > 0);
                            if (est == UNC_OK) {
                                int k;
                                if (csize < 12) est = UNC_ERR_CORRUPT;
                                else {
                                    unc_crypt_zip(cr, c->pw, c->pwlen);
                                    unc_bufin_init(&in, c->io, &c->ps,
                                                   iobuf, iocap);
                                    in.limit = csize;
                                    in.crypt = cr;
                                    for (k = 0; k < 12; k++) {
                                        int b = unc_bufin_next(&in);
                                        if (b < 0) { est = in.err; break; }
                                        if (k == 11 && (uint8_t)b != test)
                                            est = UNC_ERR_PASSWORD;
                                    }
                                }
                                if (est == UNC_ERR_PASSWORD) {
                                    attempt++;
                                    goto retry_entry;
                                }
                                if (est == UNC_OK)
                                    est = zip_decode(c, &in, &es, method,
                                                     flags, usize, &crc,
                                                     0, obuf, ocap);
                                if (est == UNC_OK &&
                                    ~crc != wantcrc)
                                    est = UNC_ERR_CRC;
                            }
                            goto entry_done;
                        }
                        if (est == UNC_OK) {
                            unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
                            in.limit = csize;
                            /* The archive's verdict, applied to every
                             * Implode entry and not only to the
                             * bug-capable ones: at the two combinations
                             * where the readings coincide the flag makes
                             * no difference, so there is nothing to
                             * gate. Unsettled (-1) means 5.3.4, which
                             * is also what a corrupt first entry
                             * leaves. */
                            est = zip_decode(c, &in, &es, method, flags,
                                             usize, &crc,
                                             imppol > 0 ? 1u : 0u,
                                             obuf, ocap);
                        }
                        if (est == UNC_OK &&
                            ~crc != wantcrc)
                            est = UNC_ERR_CRC;
                        /* An INHERITED verdict that was wrong about this
                         * entry: the archive mixes writers after all.
                         * Settling per archive assumes it does not, and
                         * what is measured is narrower than that — no
                         * archive of 1,537 mixes (FORMATS.md, *Implode*)
                         * — so the assumption is bounded here instead of
                         * being relied on. One probe pass, paid only on
                         * an entry that has ALREADY failed: if the other
                         * reading reproduces the stored CRC-32, then the
                         * bytes were good and the rule was wrong, which
                         * is a CRC failure and not the truncation the
                         * desynchronised decode reported; and the
                         * archive's verdict goes back to unsettled so
                         * the next ambiguous entry probes for itself
                         * rather than inheriting the same mistake.
                         *
                         * The entry itself is still lost: its bytes have
                         * reached the sink, and begin_entry is called
                         * once per entry (macextract.h, *Sink*), which
                         * is the whole reason the verdict is settled
                         * before the first byte. What this bounds is the
                         * REST of the archive (DECISIONS.md 2026-10-08,
                         * *the writer a zip is allowed to have twice*).
                         */
                        if (est != UNC_OK && method == 6 && !settled_here &&
                            imppol >= 0 && zip_imp_ambig(flags) &&
                            !(flags & 0x0001) &&
                            usize != UNC_SIZE_UNKNOWN && usize != 0) {
                            int r = zip_imp_dry(c, startdisk, lhoffs, flags,
                                                csize, usize, wantcrc,
                                                imppol > 0 ? 0u : 1u,
                                                iobuf, iocap, obuf, ocap);
                            if (r > 0) { est = UNC_ERR_CRC; imppol = -1; }
                        }
                    }
                }
            }
          entry_done:
            if (est == UNC_OK && srel != UNC_SIZE_UNKNOWN &&
                sd->cap.rlen && !c->opt.list_only)
                est = zip_side(c, sd, srel, 1, iobuf, iocap, obuf, ocap);
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
            if (unc_fatal(est)) {
                err = est;
                break;
            }
        }

      next_rec:
        cdrel += 46 + namelen + extralen + commentlen;
    }

    unc_free(c->al, sd);
    unc_free(c->al, fcmt);
    unc_free(c->al, cmt);
    unc_free(c->al, cdbuf);
    unc_free(c->al, iobuf);
    return err;
}

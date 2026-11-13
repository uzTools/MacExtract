/*
 * fmt_mar.c — MAR, Hampa Hug's Macintosh archive (`.mar` for a folder,
 * `.mac` for a single file: one format, two conventions).
 *
 * An archive is one item, a file or a folder, written as 128-byte
 * records. A folder is a 'fold' record, its items, and a '----' record;
 * a file is a 'file' record and then up to three stored blocks — the
 * data fork, the resource fork and the Get Info comment, in that order.
 * A block is its bytes, a 4-byte CRC of them, and zeros to the next
 * multiple of 128; an empty block is not written at all. Nothing is
 * compressed inside the format: mar 0.2.0 compresses the WHOLE archive
 * with Unix compress(1)'s LZW, which this engine already unwraps as an
 * envelope and then reads the MAR inside.
 *
 *   +0    u32  magic, "MAR" 0x80
 *   +4    u32  'file', 'fold' or '----'
 *   +8    Str63 name: a length byte and 63 bytes of field
 *   +72   u32  data fork length
 *   +76   u32  resource fork length
 *   +80   u32  comment length
 *   +84   u32  flags: bit 0 locked, bit 4 a folder
 *   +88   u32  created, +92 modified: Macintosh dates, the volume's clock
 *   +96   16   FInfo for a file, DInfo for a folder, as the Finder keeps it
 *   +112  u16  a folder's scroll, v then h: DXInfo's frScroll
 *   +124  u32  CRC of bytes 0..123
 *
 * Both CRCs are CRC-32 over 0x1EDC6F41, most significant bit first, from
 * 0 and not inverted (fmt_mar_probe.c).
 *
 * Source: the format's author's two implementations, read for their
 * facts and not copied (GPL-2.0-only; NOTICE says why that matters):
 * reference/mar/mac-utils (mac-utils 20210820-08c01f11),
 * src/lib/mar.h and mar.c for the ids, the field offsets and the header
 * CRC, src/lib/crc.c for the block CRC's parameters, src/mar/
 * mar_extract.c (mar_extract_block) for the block and its padding; and
 * reference/mar/mar-0.2.0-src (mar 0.2.0's own Macintosh source),
 * src/mar_dec.c for what its expander writes back — the 16 bytes of Finder
 * info whole, a folder's scroll into DXInfo, the lock from bit 0 of the
 * flags — and for the two Finder flags it clears on the first item by
 * default, inited and on-desk (mar_decode_fd, par_clear_first), of
 * which neither is cleared here: the shell clears on-desk on every item
 * and writes a top folder inited (DECISIONS.md 2026-11-06, *the desk no
 * folder is put on*). Its comment block it skips; this reader hands it
 * on. Graded against both archives hampa published alongside StuffIt
 * copies of the same files (FORMATS.md, *MAR*).
 *
 * Harness: tests/harness/run_mar.py
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_mar_priv.h"

#define MAR_BUF (2u * UNC_IOBUF)
/* The comment's room, rounded up so the path walker after it is
 * 4-aligned. */
#define MAR_CMT ((UNC_ENTRY_COMMENT_MAX + 3u) & ~3u)

/* What a block occupies: its bytes, its CRC and the padding, or nothing
 * for an empty one. UNC_U32_MAX for a length no file could hold. */
static uint32_t mar_span(uint32_t n)
{
    if (n == 0) return 0;
    if (n > UNC_MAC_MAX) return UNC_U32_MAX;
    return (n + 4u + 127u) & ~127u;
}

/* Step `*at` over a span, one at a time: at 32 bits two forks near 2 GB
 * would wrap a sum. 0 where the result cannot be addressed. */
static int mar_skip(unc_off_t *at, uint32_t span)
{
    if (span == UNC_U32_MAX || span > UNC_OFF_MAX - *at) return 0;
    *at += span;
    return 1;
}

/* Read the block of `n` bytes at `at` through its CRC, counting it as
 * progress. Each chunk goes to `fork` unless that is -1; the first `keep`
 * bytes are copied to `kbuf` as well. UNC_ERR_CRC if the stored CRC
 * disagrees. */
static int mar_block(UncCtx *c, unc_off_t at, uint32_t n, int fork,
                     uint8_t *buf, uint8_t *kbuf, uint32_t keep)
{
    uint32_t crc = 0, left = n, done = 0;
    uint8_t want[4];
    if (c->io->seek(c->io->ctx, at) < 0) return UNC_ERR_IO;
    while (left > 0) {
        uint32_t k = left < MAR_BUF ? left : MAR_BUF, i;
        int err = unc_read_full(c->io, buf, (int32_t)k);
        if (err != UNC_OK) return err;
        crc = unc_mar_crc(crc, buf, k);
        for (i = 0; i < k && done + i < keep; i++) kbuf[done + i] = buf[i];
        err = unc_progress_add(&c->ps, k);
        if (err != UNC_OK) return err;
        if (fork >= 0 && !c->opt.test_only &&
            c->sink->write(c->sink->ctx, (UncFork)fork, buf, (int32_t)k) < 0)
            return UNC_ERR_SINK;
        done += k;
        left -= k;
    }
    if (unc_read_full(c->io, want, 4) != UNC_OK) return UNC_ERR_TRUNCATED;
    return unc_get_u32be(want) == crc ? UNC_OK : UNC_ERR_CRC;
}

int unc_mar_extract(UncCtx *c)
{
    uint8_t h[MAR_HDR];
    uint8_t *buf, *cmt;
    UncPath *path;
    unc_off_t pos = 0, fsize = c->io->size(c->io->ctx);
    int depth = 0, err = UNC_OK;

    buf = (uint8_t *)unc_alloc(c->al, MAR_BUF + MAR_CMT +
                                      (uint32_t)sizeof *path);
    if (!buf) return UNC_ERR_MEM;
    cmt = buf + MAR_BUF;
    /* The walker in the allocation, not on the stack (fmt_sqp.c says
     * why). */
    path = (UncPath *)(void *)(cmt + MAR_CMT);
    unc_path_init(path, c);

    for (;;) {
        UncEntryInfo e;
        uint32_t id, dlen, rlen, clen, dspan, rspan, cspan, nlen;
        int top = depth == 0, sret, est = UNC_OK, k;
        unc_off_t next;

        if (unc_read_at(c->io, pos, h, (int32_t)MAR_HDR) != UNC_OK) {
            /* The archive ends where its one item does; anything short
             * of that is a cut. */
            err = pos == 0 ? UNC_ERR_FORMAT : UNC_ERR_TRUNCATED;
            break;
        }
        if (!unc_mar_hdr_ok(h)) {
            err = pos == 0 ? UNC_ERR_FORMAT : UNC_ERR_CORRUPT;
            break;
        }
        id = unc_get_u32be(h + 4);
        pos += MAR_HDR;
        /* Headers count too: an archive of empty files and folders is
         * nothing else, and would otherwise never call back. */
        err = unc_progress_add(&c->ps, MAR_HDR);
        if (err != UNC_OK) break;

        if (id == MAR_END) {
            if (top) { err = UNC_ERR_CORRUPT; break; }
            unc_path_pop(path);
            if (--depth == 0) break;
            continue;
        }
        if (id != MAR_FILE && id != MAR_FOLDER) {
            err = pos == MAR_HDR ? UNC_ERR_FORMAT : UNC_ERR_CORRUPT;
            break;
        }

        nlen = h[8] > 63 ? 63 : h[8];
        unc_entry_clear(&e);
        unc_path_leaf(path, &e, h + 9, nlen);
        e.create_date = unc_get_u32be(h + 88);
        e.mod_date = unc_get_u32be(h + 92);
        e.finder_flags = unc_get_u16be(h + 104);
        for (k = 0; k < 16; k++) e.finder_info[k] = h[96 + k];
        e.meta = UNC_META_FINFO;
        /* mar's expander clears on-desk and inited on the first item
         * (mar_dec.c, par_clear_first). Neither here: the shell clears
         * on-desk on every item, and writes the top item at (-1, -1),
         * inited if a folder, so the Finder places it and still opens its
         * window as stored (DECISIONS.md 2026-10-19, *the place outside
         * the archive*; 2026-11-06, *the desk no folder is put on*). */

        if (id == MAR_FOLDER) {
            /* frScroll, and the rest of DXInfo zero: what the expander's
             * PBSetCatInfo writes on a folder it has just made. */
            for (k = 0; k < 4; k++) e.finder_info[16 + k] = h[112 + k];
            e.meta |= UNC_META_FXINFO;
            e.is_dir = 1;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0 && c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
            (void)unc_path_push(path, h + 9, nlen);
            depth++;
            continue;
        }

        e.type = unc_get_u32be(h + 96);
        e.creator = unc_get_u32be(h + 100);
        e.locked = (h[87] & 1) ? UNC_LOCK_YES : UNC_LOCK_NO;
        dlen = unc_get_u32be(h + 72);
        rlen = unc_get_u32be(h + 76);
        clen = unc_get_u32be(h + 80);
        dspan = mar_span(dlen);
        rspan = mar_span(rlen);
        cspan = mar_span(clen);
        e.data_size = e.comp_data_size = dlen;
        e.rsrc_size = e.comp_rsrc_size = rlen;
        next = pos;
        if (!mar_skip(&next, dspan) || !mar_skip(&next, rspan) ||
            !mar_skip(&next, cspan)) {
            /* Where the next record is cannot be said, so the walk ends
             * with this entry. */
            est = UNC_ERR_TOOLARGE;
        } else if (fsize != UNC_OFF_UNKNOWN && next > fsize) {
            est = UNC_ERR_TRUNCATED;
        }

        /* The comment, ahead of the forks it follows: the entry carries
         * it from begin_entry. A comment whose CRC fails is not handed
         * on, and the entry fails with it. A listing reads only what the
         * entry carries and judges it no more than the forks it does not
         * read: `l` reports what `x` would of the archive's shape — an
         * entry cut, or too large to place — and of no block's CRC
         * (DECISIONS.md 2026-11-05, *the comment a listing read whole*). */
        if (est == UNC_OK && clen) {
            uint32_t keep = clen < UNC_ENTRY_COMMENT_MAX
                            ? clen : UNC_ENTRY_COMMENT_MAX;
            est = c->opt.list_only
                ? unc_read_at(c->io, pos + dspan + rspan, cmt, (int32_t)keep)
                : mar_block(c, pos + dspan + rspan, clen, -1, buf, cmt, keep);
            if (est == UNC_OK) {
                e.comment = cmt;
                e.comment_len = (uint16_t)keep;
            }
        }

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; break; }
        if (sret == 0) {
            if (!c->opt.list_only) {
                int ferr = UNC_OK;
                if (est != UNC_ERR_TOOLARGE && est != UNC_ERR_TRUNCATED) {
                    if (dlen)
                        ferr = mar_block(c, pos, dlen, UNC_FORK_DATA,
                                         buf, NULL, 0);
                    if (ferr == UNC_OK && rlen)
                        ferr = mar_block(c, pos + dspan, rlen, UNC_FORK_RSRC,
                                         buf, NULL, 0);
                }
                if (ferr != UNC_OK) est = ferr;
            }
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
            if (unc_fatal(est)) { err = est; break; }
        }
        if (est == UNC_ERR_TOOLARGE) break;
        /* What the entry occupies and was not read for counts too: the
         * padding and CRCs, and every block of one skipped or listed
         * (DECISIONS.md 2026-11-05, *the bytes a listing never counted*).
         * Headers and blocks read have counted up to here, so `done` is
         * where the entry began plus what of it was read. */
        c->ps.done = (uint32_t)next;
        if (top) break;
        pos = next;
    }

    unc_free(c->al, buf);
    return err;
}

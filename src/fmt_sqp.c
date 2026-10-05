/*
 * fmt_sqp.c — AppleLink package (.pkg) decoder. The format's own name is
 * SqueezePlay.
 *
 * A package is two directories and then the members' bytes. Everything
 * is addressed absolutely, so a member is read where its record says it
 * is and nothing has to be walked to reach it:
 *
 *   +0        u8     items in the SQP directory (<= 50)
 *   +1        u8     version: 0 or 1
 *   +2        u8[8]  eight bytes nothing reads
 *   +10              SQP directory: count x 86-byte records
 *
 * Version 0 stops there and those records ARE the items, flat. Version 1
 * — both real packages, and everything Aladdin's own writer produces —
 * carries a second directory and that is the one the expander reads:
 *
 *   +86n+10   u32    items in the HFS directory, then eight zero bytes
 *   +86n+22          HFS directory: count x 90-byte records, each a u16
 *                    LEVEL and a u16 that is non-zero for a FOLDER,
 *                    followed by the same 86 bytes
 *   then             the members' bytes
 *
 * The two counts need not agree: the SQP directory is a flat list of the
 * FILES, capped at 50 and skipping anything typed 'HBSF', 'PIT ' or
 * 'SIT!', so a package with a folder in it has an 86-byte hole where
 * that item's SQP record would be. The header's count is what LOCATES
 * the HFS directory; the item count is the second header's.
 *
 * A record carries both forks as (compressed length, absolute offset,
 * expanded length), and one flag byte with one stored bit per fork:
 *
 *   +4/+12/+80  the DATA fork, stored when bit 1 of +84 is set
 *   +0/+16/+76  the RESOURCE fork, stored when bit 2 of +84 is set
 *   +20         the 16 bytes of Finder info — an FInfo for a file, a
 *               DInfo for a folder, so type and creator are a window
 *               rectangle in a folder's record and are not reported
 *   +36         Str31 name; +68/+72 the two dates
 *
 * There is no checksum anywhere in the format, of a fork or of the
 * container: what says a fork decoded is that its stream ended exactly
 * at the declared length.
 *
 * The codec is Unix compress(1)'s LZW at 13 bits with the clear code
 * enabled, which is `unc_lzw.c` with no change at all — see the note
 * above the call. Its one departure from `compress` is that the clear
 * arrives only when the table FILLS: this writer has no ratio test.
 *
 * Source: `AppleLink Package Translator` 3.0.3 ("Copyright © 1990-1992
 * Aladdin Systems, Inc."), `'Othe' 1`, 33,300 bytes of 68k carrying 148
 * MacsBug symbols, so every routine below is named by the binary:
 * `ReadFileAndBuildLinkedList` @0x2faa for the layout and the version
 * test, `RdHFSDirectory` @0x5e06 for the four extra bytes,
 * `CalculateFolderSize` @0x113c for what a level means, `DoWork` @0x0
 * for the two forks and their stored bits (@0x618 and @0x96e),
 * `GetExpandedSize` @0x13ac for the two lengths, and `Decompress`
 * @0x2a78 with `GetCode` @0x2b98 for the codec. `tools/derive_sqp.py`
 * is the same reading in Python, with 29 byte patterns checked at the
 * offsets they are claimed to sit at, graded against both real
 * packages; FORMATS.md (*AppleLink packages*) has the figures and what
 * is READ but UNGRADED.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* The 86-byte record's fields. */
#define SQP_RCLEN   4     /* resource fork, compressed */
#define SQP_DCLEN   8     /* data fork, compressed     */
#define SQP_DOFF   12
#define SQP_ROFF   16
#define SQP_TYPE   20
#define SQP_CREATOR 24
#define SQP_FFLAGS 28
#define SQP_NAME   36     /* Str31: one length byte, 31 of name */
#define SQP_CTIME  68
#define SQP_MTIME  72
#define SQP_RLEN   76     /* resource fork, expanded   */
#define SQP_DLEN   80     /* data fork, expanded       */
#define SQP_FLAGS  84

#define SQP_F_STORED_DATA 0x02    /* DoWork @0x618, btst #1 */
#define SQP_F_STORED_RSRC 0x04    /* DoWork @0x96e, btst #2 */

/* Stream one fork out, through the sink.
 *
 * `clen` bounds the input: the forks are laid out back to back and
 * nothing marks the end of one, so a corrupt stream that kept asking
 * would read the NEXT fork's bytes and decode them as its own. `elen`
 * bounds the output, which is also what says the fork is complete — a
 * stream that runs dry first is truncation, and there is no checksum
 * here to notice it any other way.
 */
static int sqp_fork(UncCtx *c, UncFork which,
                    uint32_t off, uint32_t clen, uint32_t elen, int stored,
                    uint8_t *iobuf, uint32_t iocap,
                    uint8_t *obuf, uint32_t ocap)
{
    UncBufIn in;
    uint32_t left = elen;
    int err = UNC_OK;

    if (elen == 0) return UNC_OK;
    if (c->io->seek(c->io->ctx, off) < 0) return UNC_ERR_IO;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = clen;

    if (stored) {
        while (left > 0) {
            uint32_t n = left < ocap ? left : ocap, i;
            for (i = 0; i < n; i++) {
                int b = unc_bufin_next(&in);
                if (b < 0) return in.err;
                obuf[i] = (uint8_t)b;
            }
            if (!c->opt.test_only &&
                c->sink->write(c->sink->ctx, which, obuf, (int32_t)n) < 0)
                return UNC_ERR_SINK;
            left -= n;
        }
        return UNC_OK;
    }

    {
        /* 13 bits with the clear code on, which is what `compress`
         * calls block mode: ResetDecompressor @0x25ac starts at 9 bits
         * with the first free code at 257, GetCode @0x2bd2 stops
         * widening at 13 and Decompress @0x2abe treats 256 as the
         * clear. That IS unc_lzw.c's configuration — the same one ARC
         * method 9 asks for — so the decoder is reused unchanged
         * (DECISIONS.md 2026-10-05, *the deviation that was the
         * reference*). */
        UncLzw z;
        err = unc_lzw_init(&z, c->al, &in, 13, 1, clen);
        if (err != UNC_OK) return err;
        while (left > 0) {
            int32_t want = (int32_t)(left < ocap ? left : ocap);
            int32_t got = unc_lzw_read(&z, obuf, want);
            if (got < 0) { err = (int)got; break; }
            if (got == 0) { err = UNC_ERR_TRUNCATED; break; }
            if (!c->opt.test_only &&
                c->sink->write(c->sink->ctx, which, obuf, got) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
            left -= (uint32_t)got;
        }
        unc_lzw_free(&z, c->al);
    }
    return err;
}

int unc_sqp_extract(UncCtx *c)
{
    uint8_t hdr[12];
    uint8_t rec[90];
    uint8_t *iobuf, *obuf;
    uint32_t iocap = UNC_IOBUF, ocap = UNC_IOBUF;
    UncPath *path;
    uint32_t base, stride, pre, n, i, fsize;
    int version, err = UNC_OK;

    if (unc_read_at(c->io, 0, hdr, 10) != UNC_OK) return UNC_ERR_FORMAT;
    version = hdr[1];
    /* ReadFileAndBuildLinkedList @0x3074: 0 and 1, and an error
     * message for anything else. */
    if (version > 1) return UNC_ERR_UNSUPPORTED;
    fsize = unc_io_size32(c->io);

    if (version == 0) {
        n = hdr[0];
        base = 10;
        stride = 86;
        pre = 0;
    } else {
        base = 86u * hdr[0] + 10u;
        if (unc_read_at(c->io, base, hdr, 12) != UNC_OK)
            return UNC_ERR_TRUNCATED;
        n = unc_get_u32be(hdr);
        /* The reader takes this count as a WORD (@0x3174), so a
         * package cannot declare more items than that. */
        if (n > 0xFFFFu) return UNC_ERR_CORRUPT;
        base += 12;
        stride = 90;
        pre = 4;
    }
    if (fsize != UNC_SIZE_UNKNOWN &&
        (base > fsize || n > (fsize - base) / stride))
        return UNC_ERR_TRUNCATED;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap + (uint32_t)sizeof *path);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;
    /* The path walker is in the allocation rather than on the stack: it
     * is 368 B on the 68000 target and this function already holds a
     * 302-byte entry, and the stack is 4 KB for the whole call chain
     * (CLAUDE.md). Measured: the deepest chain here is 748 B —
     * unc_sqp_extract 516, sqp_fork 172, unc_lzw_read 60
     * (`-fstack-usage`, FORMATS.md, *Stack*).
     * 4-aligned: the two buffers before it are 4,096 B each and the
     * block itself comes from the allocator. */
    path = (UncPath *)(void *)(obuf + ocap);
    unc_path_init(path, c);

    for (i = 0; i < n; i++) {
        UncEntryInfo e;
        const uint8_t *r = rec + pre;
        uint32_t dlen, rlen, dclen, rclen, doff, roff;
        uint32_t level = 1;
        int folder = 0, nlen, sret, eerr;

        if (unc_read_at(c->io, base + stride * i, rec, (int32_t)stride)
                != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            break;
        }
        if (pre) {
            level = unc_get_u16be(rec);
            folder = unc_get_u16be(rec + 2) != 0;
            if (level < 1) level = 1;
        }
        nlen = r[SQP_NAME];
        if (nlen > 31) nlen = 31;      /* Str31 — the field holds no more */

        /* A folder owns the items after it whose level is greater
         * (CalculateFolderSize @0x113c), so the path is a stack of
         * names indexed by level. Its own record's lengths are never
         * read by the expander — DoItemsReverse @0x1ecc branches away
         * before DoWork — and they are not read here either. */
        while (path->depth >= (int)level) unc_path_pop(path);

        unc_entry_clear(&e);
        unc_path_leaf(path, &e, r + SQP_NAME + 1, (uint32_t)nlen);
        /* The 16 bytes at +20 are whatever PBGetCatInfo left in
         * ioFlFndrInfo, which `AddItems` @0x2378 copies whole — so for a
         * FILE they are an FInfo and for a FOLDER a DInfo, where the
         * first eight bytes are the folder's window rectangle rather
         * than a type and a creator. The Finder flags survive either
         * way, both structures carrying them at +8, and so do the two
         * dates at +68 and +72 (ioFlCrDat and ioDrCrDat are the same
         * field of the same union). A folder's type and creator are
         * left UNKNOWN rather than reported as a rectangle. */
        e.finder_flags = unc_get_u16be(r + SQP_FFLAGS);
        e.create_date  = unc_get_u32be(r + SQP_CTIME);
        e.mod_date     = unc_get_u32be(r + SQP_MTIME);
        if (!folder) {
            e.type    = unc_get_u32be(r + SQP_TYPE);
            e.creator = unc_get_u32be(r + SQP_CREATOR);
        }

        if (folder) {
            e.is_dir = 1;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0 && c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
            /* Descend whatever the sink decided: the items inside are
             * named by the archive and not by what the host took. */
            (void)unc_path_push(path, r + SQP_NAME + 1, (uint32_t)nlen);
            continue;
        }

        dclen = unc_get_u32be(r + SQP_DCLEN);
        rclen = unc_get_u32be(r + SQP_RCLEN);
        doff  = unc_get_u32be(r + SQP_DOFF);
        roff  = unc_get_u32be(r + SQP_ROFF);
        dlen  = unc_get_u32be(r + SQP_DLEN);
        rlen  = unc_get_u32be(r + SQP_RLEN);
        e.data_size = dlen;
        e.rsrc_size = rlen;
        e.comp_data_size = dclen;
        e.comp_rsrc_size = rclen;
        e.method_data = (uint8_t)((r[SQP_FLAGS] & SQP_F_STORED_DATA) ? 0 : 1);
        e.method_rsrc = (uint8_t)((r[SQP_FLAGS] & SQP_F_STORED_RSRC) ? 0 : 1);

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; break; }
        if (sret > 0) continue;
        if (c->opt.list_only) {
            if (c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
            continue;
        }

        eerr = sqp_fork(c, UNC_FORK_DATA, doff, dclen, dlen,
                        r[SQP_FLAGS] & SQP_F_STORED_DATA,
                        iobuf, iocap, obuf, ocap);
        if (eerr == UNC_OK)
            eerr = sqp_fork(c, UNC_FORK_RSRC, roff, rclen, rlen,
                            r[SQP_FLAGS] & SQP_F_STORED_RSRC,
                            iobuf, iocap, obuf, ocap);
        if (c->sink->end_entry(c->sink->ctx, eerr) < 0) {
            err = UNC_ERR_SINK;
            break;
        }
        if (unc_fatal(eerr)) { err = eerr; break; }
    }

    unc_free(c->al, iobuf);
    return err;
}

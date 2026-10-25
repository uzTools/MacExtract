/*
 * fmt_macbinary.c — MacBinary I/II/III decoder.
 *
 * MacBinary is a flat 128-byte header + data fork + resource fork,
 * each fork zero-padded to a 128-byte boundary.
 *
 * Source: reference/notes/macbinary_ii.txt — the MacBinary II Standard
 * as revised 7/24/87, which states the whole header, says it "includes
 * all necessary information needed from the original MacBinary standard
 * document", and gives the order a reader is meant to decide the
 * version in; and reference/notes/macbinary_iii.txt, the December 1996
 * MacBinary III proposal, for the 'mBIN' signature at offset 102 and
 * for the amended order that looks at it first.
 *
 * Header fields used (offsets in bytes):
 *     0  zero
 *     1  name length (1..63 in the II standard, which is what is
 *        accepted; the III standard narrows it to 1..31)
 *     2  name bytes (MacRoman)
 *    65  type (4)        69  creator (4)
 *    73  Finder flags, high byte (bit 7 "Locked" in I and II, "isAlias"
 *        in III)
 *    74  zero
 *    75  fdLocation, vertical then horizontal (2 + 2)
 *    79  fdFldr, "file's window or folder ID" (2)
 *    81  "Protected" flag, in the low-order bit
 *    82  zero
 *    83  data fork size (4)      87  resource fork size (4)
 *    91  creation date (4, Mac 1904 epoch)
 *    95  modification date (4)
 *    99  Get Info comment length (2, MacBinary II) — the text follows
 *        the resource fork
 *   101  Finder flags, low byte (MacBinary II)
 *   102  'mBIN' signature (MacBinary III)
 *   106  fdScript, 107 fdXFlags (MacBinary III, "from the ... fxInfo
 *        record")
 *   108..115 zero
 *   120  secondary header length (2) — data starts at 128 + pad128(it)
 *   124  CRC-16/XMODEM of bytes 0..123 (MacBinary II/III)
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_macbinary_priv.h"

/* unc_macbinary_meta, what a header says about the file, is in
 * fmt_macbinary_probe.c: the LZH and zip readers reach it too, so it stays
 * resident on the Macintosh while this reader is an overlay. */

/* Stream `size` fork bytes from the current position to the sink,
 * then skip the padding up to a 128-byte boundary.
 * Returns UNC_OK or an error; short input yields UNC_ERR_TRUNCATED
 * after delivering what was available. */
static int mb_stream_fork(UncCtx *c, UncFork fork, uint32_t size,
                          uint8_t *buf, uint32_t bufsz)
{
    int err = unc_copy_fork(c, fork, size, buf, bufsz);
    if (err != UNC_OK) return err;
    /* Skip zero padding to the next 128-byte boundary. */
    return unc_skip(c->io, MB_PAD(size) - size);
}

int unc_macbinary_extract(UncCtx *c)
{
    uint8_t hdr[MB_HDR];
    UncEntryInfo e;
    uint32_t datasize, rsrcsize, extsize, cmtlen, bufsz, need;
    uint8_t *buf;
    int err, sret;

    err = unc_read_at(c->io, 0, hdr, MB_HDR);
    if (err != UNC_OK) return err;
    /* The probe, which is mb_version > 0: on the Macintosh it is in the
     * host vector and mb_version is not. */
    if (unc_macbinary_probe(hdr, MB_HDR, NULL) == UNC_FORMAT_UNKNOWN)
        return UNC_ERR_FORMAT;

    datasize = unc_get_u32be(hdr + 83);
    rsrcsize = unc_get_u32be(hdr + 87);
    extsize  = unc_get_u16be(hdr + 120);

    unc_entry_clear(&e);
    unc_entry_set_name(&e, hdr + 2, hdr[1]);
    /* The Get Info comment, II and III: its length at 99, and the text
     * "on the 128-boundary immediately following the Resource Fork, if
     * present, else the Data Fork, if present, else immediately
     * following the header" (reference/notes/
     * macbinary_specs_theunarchiver.md, the original standard's
     * amendment, which II adopts). MacBinary I has no field: the probe
     * holds 99..125 at zero for it. */
    cmtlen = unc_macbinary_meta(&e, hdr) >= 2 ? unc_get_u16be(hdr + 99) : 0;
    if (cmtlen > UNC_ENTRY_COMMENT_MAX) cmtlen = UNC_ENTRY_COMMENT_MAX;
    e.data_size    = datasize;
    e.rsrc_size    = rsrcsize;
    e.comp_data_size = datasize;
    e.comp_rsrc_size = rsrcsize;

    /* One block for the copy and the comment behind it, which has to
     * outlive the copy: the sink may read it until end_entry returns. */
    bufsz = c->opt.list_only ? 0 : UNC_PROGRESS_STEP;
    need = bufsz + cmtlen;
    buf = need ? (uint8_t *)unc_alloc(c->al, need) : NULL;
    if (cmtlen && buf) {
        /* A comment that cannot be read is dropped, not an error: the
         * forks are the file, and `unar`, which grades a cut file here
         * (tools/run_truncation.py), reads no comment at all. */
        uint32_t at = MB_HDR + MB_PAD(extsize);
        uint32_t pd = MB_PAD(datasize), pr = MB_PAD(rsrcsize);
        if (pd >= datasize && pr >= rsrcsize &&          /* no wrap */
            pd <= UNC_U32_MAX - at && pr <= UNC_U32_MAX - at - pd &&
            unc_read_at(c->io, at + pd + pr, buf + bufsz,
                        (int32_t)cmtlen) == UNC_OK) {
            e.comment = buf + bufsz;
            e.comment_len = (uint16_t)cmtlen;
        }
    }

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret != 0) {
        unc_free(c->al, buf);
        if (sret < 0) return UNC_ERR_SINK;
        return UNC_OK;              /* sink skipped the only entry */
    }

    err = UNC_OK;
    if (!c->opt.list_only) {
        if (!buf) err = UNC_ERR_MEM;
        if (err == UNC_OK) {
            /* Data fork begins after the (padded) secondary header. */
            if (c->io->seek(c->io->ctx, MB_HDR + MB_PAD(extsize)) < 0)
                err = UNC_ERR_IO;
            if (err == UNC_OK)
                err = mb_stream_fork(c, UNC_FORK_DATA, datasize, buf, bufsz);
            if (err == UNC_OK)
                err = mb_stream_fork(c, UNC_FORK_RSRC, rsrcsize, buf, bufsz);
        }
    }

    sret = c->sink->end_entry(c->sink->ctx, err);
    unc_free(c->al, buf);
    if (sret < 0) return UNC_ERR_SINK;
    /* Per-entry errors were reported via end_entry; fatal ones stop us. */
    if (unc_fatal(err))
        return err;
    return UNC_OK;
}

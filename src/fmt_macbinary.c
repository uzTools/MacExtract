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
 * MacBinary I has no CRC, so it is accepted only under the stricter
 * tests the II standard sets out for exactly that case: "Offsets
 * 101-125 ... should all be 0", the name length in 1..63, and the two
 * fork lengths bounded. Two of those are read here more strictly than
 * written and one less, and each difference is deliberate:
 *
 *   - zero is required from offset 99 rather than 101. 99 is the Get
 *     Info comment length, which the II standard adds and then reports
 *     that "to the best of our knowledge, no program has implemented
 *     this feature"; a MacBinary I header has nothing there at all.
 *   - the fork lengths are bounded by UNC_MAC_MAX (2 GB) rather than by
 *     the standard's 0x007FFFFF. The smaller figure is a 1987 statement
 *     about how large a Macintosh file could be, not about the format,
 *     and this engine already refuses what it cannot address.
 *   - nonzero creation and modification dates are required, which no
 *     standard asks for. It is XADMaster's test and it is kept: a
 *     MacBinary I header has no checksum, so without it the whole of
 *     the evidence is a handful of zero bytes.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define MB_HDR 128
#define MB_PAD(n) (((n) + 127u) & ~127u)

/* CRC-16 with reflected polynomial 0xA001 (CRC-16/USB when init and
 * final xor are 0xFFFF). The standard specifies one checksum and this
 * is not it: XADMaster is the sole source, accepting this as a fallback
 * for files made by encoders that reached for the wrong table.
 * Source: reference/XADMaster/XADMacArchiveParser.m (XADCRCTable_a001
 * use, and the nonzero-date test above) — LGPL, see NOTICE. Bitwise form; runs over 124 bytes only, speed is
 * irrelevant. */
static uint16_t mb_crc16_a001(uint16_t crc, const uint8_t *buf, int32_t len)
{
    int32_t i;
    int b;
    for (i = 0; i < len; i++) {
        crc ^= buf[i];
        for (b = 0; b < 8; b++)
            crc = (crc & 1) ? (uint16_t)((crc >> 1) ^ 0xA001) : (uint16_t)(crc >> 1);
    }
    return crc;
}

/* Returns MacBinary version 1..3, or 0 if the header is not MacBinary.
 *
 * The III standard says to look at the 'mBIN' signature FIRST and fall
 * back to the II procedure if it is absent. The order here is the other
 * way round — the zero fills and the name, then the CRC, and only then
 * 'mBIN' to tell III from II — and the two agree, because a MacBinary
 * III header carries the II checksum as well. Reading the CRC first
 * costs a III file nothing and buys the signature test a header that
 * has already been checked. */
static int mb_version(const uint8_t *b, int32_t len)
{
    int i;
    if (len < MB_HDR) return 0;

    /* Zero fill bytes. */
    if (b[0] != 0) return 0;
    if (b[74] != 0) return 0;
    if (b[82] != 0) return 0;
    for (i = 108; i <= 115; i++) if (b[i] != 0) return 0;

    /* Valid name. */
    if (b[1] == 0 || b[1] > 63) return 0;
    for (i = 0; i < b[1]; i++) if (b[i + 2] == 0) return 0;

    /* MacBinary II/III: header CRC at 124 (CRC-16/XMODEM over 0..123). */
    if (unc_crc16_xmodem(0, b, 124) == unc_get_u16be(b + 124) ||
        (mb_crc16_a001(0xFFFF, b, 124) ^ 0xFFFF) == unc_get_u16be(b + 124)) {
        if (unc_get_u32be(b + 102) == 0x6D42494Eu) return 3; /* 'mBIN' */
        return 2;
    }

    /* MacBinary I: no checksum, so the structural tests are all the
     * evidence there is (see file comment). */
    for (i = 99; i <= 125; i++) if (b[i] != 0) return 0;
    if (unc_get_u32be(b + 83) > UNC_MAC_MAX) return 0; /* data fork size */
    if (unc_get_u32be(b + 87) > UNC_MAC_MAX) return 0; /* rsrc fork size */
    if (unc_get_u32be(b + 91) == 0) return 0;          /* creation date  */
    if (unc_get_u32be(b + 95) == 0) return 0;          /* mod date       */
    return 1;
}

UncFormat unc_macbinary_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return (mb_version(head, len) > 0)
           ? UNC_FORMAT_MACBINARY : UNC_FORMAT_UNKNOWN;
}

/* Everything a MacBinary header says about the file, into `e`: type,
 * creator, flags and the two dates, as before, and since 2026-10-17 the
 * rest of the Finder info, the lock and, for III, the two bytes of FXInfo
 * it keeps. Shared with the two archivers that carry a Macintosh file as a
 * MacBinary stream, ZipIt (fmt_exo.c) and MacLHA (fmt_lzh.c), so that one
 * header is read one way. Returns the version, 1..3; a header the probe
 * refuses (MacLHA 2.00's, which has no dates) is read as MacBinary I,
 * which is what fmt_lzh.c has already established it is.
 *
 * Source: reference/notes/macbinary_ii.txt and macbinary_iii.txt.
 *  - Bytes 65..80 are the FInfo, in the FInfo's own order — the original
 *    standard says "the following 16 bytes are a standard Finder Info
 *    record" (reference/notes/macbinary_specs_theunarchiver.md) — except
 *    byte 74, whose zero keeps a MacBinary I reader working: the flags'
 *    low byte is at 101 since II. So finder_info[0..15] is 65..80 with
 *    101 in place of 74. Both standards tell a DOWNLOADER to zero
 *    fdLocation and fdFldr and clear inited; this delivers them as the
 *    archive holds them, because the brief is to bring the file back as
 *    it was, and the Macintosh shell decides inited (DECISIONS.md
 *    2026-10-17, *the envelopes' own Finder info*).
 *  - FXInfo, III only: fdScript at 106 and fdXFlags at 107, which are
 *    FXInfo bytes 8 and 9 (reference/notes/rfc1740.txt, struct FXInfo).
 *    III keeps nothing else of the record, and the other fourteen are
 *    stated as zero, what a file the File Manager has just created holds;
 *    the shell clears 10..15 itself. In II, 102..115 are "not defined
 *    above" and so "should be set to zero", and no FXInfo is stated.
 *  - The lock: 81's low-order bit, "Protected", in every version —
 *    macutils, the oracle here, names offset 81 I_LOCKOFF
 *    (reference/macutils/fileio/machdr.h) and copies PackIt's "file
 *    locked" word into it (macunpack/pit.c). And 73's bit 7, which I and
 *    II both call "Locked", in MacBinary I only: III renamed the bit
 *    isAlias, and a II file written under System 7 has the alias bit
 *    there. A I header, with no CRC, predates both. */
int unc_macbinary_meta(UncEntryInfo *e, const uint8_t *b)
{
    int v = mb_version(b, MB_HDR), k;
    uint8_t hi;
    if (v == 0) v = 1;
    e->type         = unc_get_u32be(b + 65);
    e->creator      = unc_get_u32be(b + 69);
    /* In a I header 73's bit 7 is the lock and nothing else: I predates
     * aliases, and left in the flags it is System 7's isAlias, which made
     * a locked file a broken alias (DECISIONS.md 2026-10-17, *the
     * envelopes' own Finder info*). So it is the lock below, and masked
     * here. */
    hi = (uint8_t)(v == 1 ? b[73] & 0x7F : b[73]);
    e->finder_flags = (uint16_t)((hi << 8) | b[101]);
    e->create_date  = unc_get_u32be(b + 91);
    e->mod_date     = unc_get_u32be(b + 95);
    for (k = 0; k < 16; k++) e->finder_info[k] = b[65 + k];
    e->finder_info[8] = hi;
    e->finder_info[9] = b[101];
    e->meta |= UNC_META_FINFO;
    if (v == 3) {
        for (k = 16; k < 32; k++) e->finder_info[k] = 0;
        e->finder_info[24] = b[106];
        e->finder_info[25] = b[107];
        e->meta |= UNC_META_FXINFO;
    }
    e->locked = ((b[81] & 0x01) || (v == 1 && (b[73] & 0x80)))
              ? UNC_LOCK_YES : UNC_LOCK_NO;
    return v;
}

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
    if (mb_version(hdr, MB_HDR) == 0) return UNC_ERR_FORMAT;

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

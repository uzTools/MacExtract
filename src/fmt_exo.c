/*
 * fmt_exo.c — the exogenous formats: gzip (.gz), Unix compress (.Z),
 * tar, and zip (store + deflate).
 *
 * These are byte-oriented Unix/PC formats with public specs:
 *   gzip: RFC 1952. zip: PKWARE APPNOTE (EOCD + central directory).
 *   tar: POSIX ustar. .Z: compress(1) LZW (see unc_lzw.c).
 * Cross-checked against reference/XADMaster (XADGzipParser.m,
 * XADZipParser.m, XADTarParser.m, XADCompressParser.m) — LGPL, see
 * NOTICE. Deflate decoding uses vendored zlib (third_party/zlib).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* Twice UNC_IOBUF. These readers move whole runs rather than bytes:
 * inflate hands back a block at a time, LZW a phrase, and tar copies
 * member data straight through. */
#define EXO_BUF (2u * UNC_IOBUF)

/* Shared emit callback: write to sink data fork. */
typedef struct ExoSink {
    UncCtx *c;
    int     failed;
} ExoSink;

static int exo_emit(void *ctx, const uint8_t *p, int32_t n)
{
    ExoSink *s = (ExoSink *)ctx;
    if (s->c->opt.test_only) return UNC_OK;
    if (s->c->sink->write(s->c->sink->ctx, UNC_FORK_DATA, p, n) < 0)
        return UNC_ERR_SINK;
    return UNC_OK;
}

static void exo_hint_name(UncCtx *c, UncEntryInfo *e)
{
    if (c->opt.name_hint && c->opt.name_hint_len)
        unc_entry_set_path(e, c->opt.name_hint, c->opt.name_hint_len);
}

/* ------------------------------------------------------------------ */
/* gzip (RFC 1952)                                                    */
/* ------------------------------------------------------------------ */

UncFormat unc_gzip_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return (len >= 3 && head[0] == 0x1F && head[1] == 0x8B && head[2] == 8)
           ? UNC_FORMAT_GZIP : UNC_FORMAT_UNKNOWN;
}

int unc_gzip_extract(UncCtx *c)
{
    uint8_t hdr[10], *iobuf, *obuf;
    uint32_t iocap = UNC_IOBUF, ocap = EXO_BUF;
    UncBufIn in;
    UncEntryInfo e;
    ExoSink es;
    int flg, sret, est = UNC_OK;
    int err = UNC_OK;

    if (unc_read_at(c->io, 0, hdr, 10) != UNC_OK) return UNC_ERR_FORMAT;
    if (hdr[0] != 0x1F || hdr[1] != 0x8B) return UNC_ERR_FORMAT;
    if (hdr[2] != 8) return UNC_ERR_UNSUPPORTED;   /* only deflate exists */
    flg = hdr[3];

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;

    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    if (c->io->seek(c->io->ctx, 10) < 0) { err = UNC_ERR_IO; goto out; }

    /* Optional header fields, in order: FEXTRA, FNAME, FCOMMENT, FHCRC. */
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
    if (flg & 0x10) {   /* FCOMMENT */
        int b;
        do {
            b = unc_bufin_next(&in);
            if (b < 0) { err = UNC_ERR_TRUNCATED; goto out; }
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

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) { err = UNC_ERR_SINK; goto out; }
    if (sret > 0) goto out;

    if (!c->opt.list_only) {
        uint32_t produced = 0, crc = UNC_CRC32_INIT;
        es.c = c;
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
    unc_free(c->al, iobuf);
    return err;
}

/* ------------------------------------------------------------------ */
/* Unix compress .Z                                                   */
/* ------------------------------------------------------------------ */

UncFormat unc_compressz_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return (len >= 3 && head[0] == 0x1F && head[1] == 0x9D)
           ? UNC_FORMAT_COMPRESS_Z : UNC_FORMAT_UNKNOWN;
}

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
/* tar (POSIX ustar; pre-POSIX v7 headers accepted via checksum)      */
/* ------------------------------------------------------------------ */

/* Parse an octal field (space/NUL padded). Returns value or -1. */
static int64_t tar_octal(const uint8_t *p, int32_t n)
{
    int64_t v = 0;
    int32_t i = 0;
    while (i < n && (p[i] == ' ' || p[i] == 0)) i++;
    if (i == n) return 0;
    for (; i < n && p[i] >= '0' && p[i] <= '7'; i++)
        v = v * 8 + (p[i] - '0');
    return v;
}

static int tar_checksum_ok(const uint8_t *h)
{
    int64_t stored = tar_octal(h + 148, 8);
    int32_t i;
    int64_t uns = 0, sig = 0;
    for (i = 0; i < 512; i++) {
        uint8_t b = (i >= 148 && i < 156) ? (uint8_t)' ' : h[i];
        uns += b;
        sig += (int8_t)((i >= 148 && i < 156) ? ' ' : (int8_t)h[i]);
    }
    return stored == uns || stored == sig;   /* GNU tolerates signed sums */
}

/* An octal header field: octal digits terminated/padded by NUL or
 * space (leading spaces allowed), or all NUL. */
static int tar_field_ok(const uint8_t *p, int32_t n)
{
    int32_t i = 0;
    while (i < n && p[i] == ' ') i++;
    while (i < n && p[i] >= '0' && p[i] <= '7') i++;
    while (i < n && (p[i] == 0 || p[i] == ' ')) i++;
    return i == n;
}

UncFormat unc_tar_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    int32_t i;
    if (len < 512) return UNC_FORMAT_UNKNOWN;
    if (!tar_checksum_ok(head)) return UNC_FORMAT_UNKNOWN;

    /* POSIX/old-GNU: "ustar" magic at 257 plus the checksum. */
    if (head[257] == 'u' && head[258] == 's' && head[259] == 't' &&
        head[260] == 'a' && head[261] == 'r')
        return UNC_FORMAT_TAR;

    /* Pre-POSIX v7 tar has NO magic. XADTarParser falls back to the
     * *filename* for these, which our content-only rule forbids, so
     * we demand structure instead: a valid checksum plus well-formed
     * v7 fields (see DECISIONS.md M9/M10 follow-up).
     *   - name: NUL-terminated printable, non-empty
     *   - mode/uid/gid/size/mtime: octal fields
     *   - typeflag: NUL or '0'..'7' */
    if (head[0] == 0) return UNC_FORMAT_UNKNOWN;
    for (i = 0; i < 100 && head[i]; i++)
        if (head[i] < 0x20 || head[i] == 0x7F) return UNC_FORMAT_UNKNOWN;
    if (i == 100) return UNC_FORMAT_UNKNOWN;                    /* name not terminated */
    if (!tar_field_ok(head + 100, 8)) return UNC_FORMAT_UNKNOWN;   /* mode  */
    if (!tar_field_ok(head + 108, 8)) return UNC_FORMAT_UNKNOWN;   /* uid   */
    if (!tar_field_ok(head + 116, 8)) return UNC_FORMAT_UNKNOWN;   /* gid   */
    if (!tar_field_ok(head + 124, 12)) return UNC_FORMAT_UNKNOWN;  /* size  */
    if (!tar_field_ok(head + 136, 12)) return UNC_FORMAT_UNKNOWN;  /* mtime */
    if (head[156] != 0 && (head[156] < '0' || head[156] > '7')) return UNC_FORMAT_UNKNOWN;
    return UNC_FORMAT_TAR;
}

int unc_tar_extract(UncCtx *c)
{
    uint8_t h[512];
    unc_off_t pos = 0, fsize;
    int seen = 0;
    int err = UNC_OK;
    uint8_t *iobuf;
    uint32_t iocap = EXO_BUF;

    fsize = c->io->size(c->io->ctx);
    iobuf = (uint8_t *)unc_alloc(c->al, iocap);
    if (!iobuf) return UNC_ERR_MEM;

    for (;;) {
        int64_t size;
        uint32_t datalen;
        int typeflag, zero = 1, sret, est, isdir, oversize;
        int64_t next;
        int32_t i;
        UncEntryInfo e;
        uint8_t path[256];
        uint32_t plen = 0;

        if (unc_read_at(c->io, pos, h, 512) != UNC_OK) {
            /* EOF at a block boundary: tolerated (missing end blocks) */
            err = seen ? UNC_OK : UNC_ERR_FORMAT;
            break;
        }
        for (i = 0; i < 512; i++) if (h[i]) { zero = 0; break; }
        if (zero) break;   /* end-of-archive marker */

        if (!tar_checksum_ok(h)) {
            err = seen ? UNC_ERR_CORRUPT : UNC_ERR_FORMAT;
            break;
        }
        seen = 1;

        size = tar_octal(h + 124, 12);
        typeflag = h[156];
        if (size < 0) { err = UNC_ERR_CORRUPT; break; }
        /* A member past the engine's 32-bit reach is refused as an
         * ENTRY, not as an archive: its header states how long it is,
         * so where the NEXT member begins is known exactly and the
         * rest of the tar still reads. What ends the walk is the NEXT
         * member's position leaving 32 bits — the 4 GB container limit,
         * which is every format's (FORMATS.md, *Size limits*), and it
         * is checked after this member is reported rather than before,
         * so the last one a header describes is still named. */
        oversize = size > UNC_MAC_MAX;
        datalen = oversize ? UNC_SIZE_UNKNOWN : (uint32_t)size;
        next = (int64_t)pos + 512 + ((size + 511) & ~(int64_t)511);

        /* Name: ustar prefix + '/' + name (raw bytes, '/' native). */
        if (h[345] && h[257] == 'u') {   /* prefix field in use */
            for (i = 0; i < 155 && h[345 + i]; i++) path[plen++] = h[345 + i];
            path[plen++] = '/';
        }
        for (i = 0; i < 100 && h[i]; i++) path[plen++] = h[i];
        /* Directory: typeflag '5' (ustar) or a trailing '/' in the
         * name (the only marking pre-POSIX v7 tar has). */
        isdir = typeflag == '5' ||
                (plen > 0 && path[plen - 1] == '/');
        /* Strip the trailing '/' of directory names. */
        while (plen > 0 && path[plen - 1] == '/') plen--;
        /* Drop "." components ("./name" prefixes are routine in v7
         * tars; GNU tar and unar both strip them on extraction). */
        {
            uint32_t r = 0, w = 0, cs = 0;
            for (r = 0; r <= plen; r++) {
                if (r == plen || path[r] == '/') {
                    if (r - cs == 1 && path[cs] == '.')
                        w = w > 0 ? w - 1 : 0;   /* drop ".", undo sep */
                    if (r < plen && w > 0 && path[w - 1] != '/')
                        path[w++] = '/';
                    cs = r + 1;
                } else path[w++] = path[r];
            }
            plen = w;
            while (plen > 0 && path[plen - 1] == '/') plen--;
        }
        if (plen == 0 && isdir) {
            /* The "./" root entry itself: nothing to create. */
            if (next < 0 || (uint64_t)next > (uint64_t)UNC_OFF_MAX) {
                err = UNC_ERR_CORRUPT; break;
            }
            pos = (unc_off_t)next;
            continue;
        }

        unc_entry_clear(&e);
        unc_entry_set_path(&e, path, plen);
        /* ustar can state 256 bytes (155 + '/' + 100) and the engine
         * carries 255, so `path` still holds what the entry lost. */
        if (e.name_truncated) unc_entry_long_name(c, &e, path, plen);
        e.mod_date = 0;
        e.rsrc_size = 0;

        if (isdir) {
            e.is_dir = 1;
            e.data_size = 0;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0 && c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
        } else if (!oversize &&
                   (typeflag == '0' || typeflag == 0)) {  /* regular file */
            e.data_size = datalen;
            e.comp_data_size = datalen;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0) {
                est = UNC_OK;
                if (!c->opt.list_only) {
                    uint32_t left = datalen;
                    unc_off_t at = pos + 512;
                    if (fsize != UNC_SIZE_UNKNOWN && at + datalen > fsize) {
                        est = UNC_ERR_TRUNCATED;
                    } else if (c->io->seek(c->io->ctx, at) < 0) {
                        est = UNC_ERR_IO;
                    } else {
                        while (left > 0 && est == UNC_OK) {
                            int32_t n = left < iocap ? (int32_t)left
                                                     : (int32_t)iocap;
                            est = unc_read_full(c->io, iobuf, n);
                            if (est == UNC_OK) {
                                int perr = unc_progress_add(&c->ps, (uint32_t)n);
                                if (perr != UNC_OK) est = perr;
                            }
                            if (est == UNC_OK && !c->opt.test_only &&
                                c->sink->write(c->sink->ctx, UNC_FORK_DATA,
                                               iobuf, n) < 0)
                                est = UNC_ERR_SINK;
                            left -= (uint32_t)n;
                        }
                    }
                }
                if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                    err = UNC_ERR_SINK;
                    break;
                }
                if (unc_fatal(est)) {
                    err = est;
                    break;
                }
            }
        } else {
            /* Links, devices, GNU extensions and members over 2 GB:
             * reported, not extracted. */
            e.data_size = datalen;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0 &&
                c->sink->end_entry(c->sink->ctx, oversize
                                   ? UNC_ERR_TOOLARGE
                                   : UNC_ERR_UNSUPPORTED) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
        }

        if (next < 0 || (uint64_t)next > (uint64_t)UNC_OFF_MAX) {
            err = UNC_ERR_CORRUPT; break;
        }
        pos = (unc_off_t)next;
    }

    unc_free(c->al, iobuf);
    return err;
}

/* ------------------------------------------------------------------ */
/* zip (EOCD + central directory; store and deflate)                  */
/* ------------------------------------------------------------------ */

UncFormat unc_zip_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    if (len < 4) return UNC_FORMAT_UNKNOWN;
    /* Local file header or (rarely first) central dir / EOCD magic. */
    if (head[0] == 'P' && head[1] == 'K' &&
        ((head[2] == 3 && head[3] == 4) ||
         (head[2] == 5 && head[3] == 6)))    /* empty archive */
        return UNC_FORMAT_ZIP;
    /* A local header displaced to offset 4: what a splitting zip writes
     * when it puts a marker in front. That archive may be a set of one,
     * in which case it is an ordinary zip and reads as one — the four
     * bytes are simply part of every offset it records.
     * Source: reference/XADMaster/XADZipParser.m
     * +recognizeFileWithHandle:, `bytes[4..7] == PK\3\4`. Segmented
     * sets are caught before this by unc_zipseg_probe. */
    return (len >= 8 && head[4] == 'P' && head[5] == 'K' &&
           head[6] == 3 && head[7] == 4)
           ? UNC_FORMAT_ZIP : UNC_FORMAT_UNKNOWN;
}

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

/* Decode one entry's data from a reader already positioned at it (and,
 * for an encrypted entry, already past the twelve-byte encryption
 * header and reading through a cipher). Accumulates the CRC-32 the
 * caller compares against the directory's. */
static int zip_decode(UncCtx *c, UncBufIn *in, ExoSink *es, uint32_t method,
                      uint32_t usize, uint32_t *crc,
                      uint8_t *obuf, uint32_t ocap)
{
    uint32_t produced = 0;
    int est;

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

/* The value a central-directory field carries when the real one is in
 * the Zip64 extra field instead. Not a ceiling: the format's own
 * escape, which happens to be all-ones. */
#define ZIP64_ESC32 0xFFFFFFFFu

/* One central-directory record's extra fields. Two matter here: WinZip's
 * AES (0x9901) and Zip64 (0x0001).
 *
 * A Zip64 field holds only those values whose central-directory field
 * carries the escape (0xFFFFFFFF, or 0xFFFF for a disk number), in the
 * fixed order uncompressed size, compressed size, local-header offset,
 * start disk — so the record has to be walked in order, not indexed, and
 * the scan cannot stop at the first field it recognises.
 * Source: XADMaster XADZipParser.m, -parseCentralDirectoryRecord
 * (extid==1), quoting APPNOTE.TXT 4.5.3.
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
} ZipExtra;

static void zip_extra_scan(const uint8_t *ex, uint32_t exlen,
                           uint32_t method, uint32_t flags, ZipExtra *z)
{
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
             * there". Source: XADZipParser.m. */
            uint32_t ver = unc_get_u16le(ex + 4);
            uint32_t vendor = unc_get_u16le(ex + 6);
            uint32_t strength = ex[8];
            if ((ver == 1 || ver == 2) && vendor == 0x4541 &&
                strength >= 1 && strength <= 3) {
                z->aesversion = (int)ver;
                z->aeskeybytes = (int)(8 + 8 * strength);  /* 16/24/32 */
                z->aesmethod = unc_get_u16le(ex + 9);
            }
        }
        ex += 4 + sz;
        exlen -= 4 + sz;
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
     * Source: reference/XADMaster/XADZipParser.m,
     * -parseWithCentralDirectoryAtOffset:zip64Offset: — record layout,
     * field order and the 0x06064b50 / 0x07064b50 signatures. */
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
     * Source: reference/XADMaster/XADZipParser.m,
     * -parseWithCentralDirectoryAtOffset:zip64Offset: — the comment
     * length is the u16 at EOCD+20 and the bytes follow the record,
     * which is what `lsar` reports as XADComment. */
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

    cdrel = 0;                    /* bytes into the directory, either way */
    for (i = 0; i < nentries; i++) {
        uint32_t method, flags, wantcrc, csize, usize;
        uint32_t namelen, extralen, commentlen, lhoffs, startdisk;
        int aeskeybytes, aesversion;
        int z64err;
        uint32_t aesmethod;
        const uint8_t *cd, *namep;
        uint8_t namebuf[256];
        uint32_t nread;
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
        }

        unc_entry_clear(&e);
        {
            uint32_t plen = nread;
            int isdir = plen > 0 && namep[plen - 1] == '/';
            while (plen > 0 && namep[plen - 1] == '/') plen--;
            unc_entry_set_path(&e, namep, plen);  /* '/' native, raw bytes */
            /* The record's name was cut to `namebuf` before the funnel
             * could see how long it really was. */
            if (namelen > nread) {
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
                    /* PKWARE's "strong encryption": its key material is
                     * in a record nothing here parses, and XADMaster
                     * refuses it too. OPEN_ITEMS.md. */
                    est = UNC_ERR_ENCRYPTED;
                } else if (method == 99 && (flags & 0x0001) &&
                           !aeskeybytes) {
                    /* Method 99 says "see the AES extra field", and
                     * there is not one (or it is a version or a key
                     * length this does not read). */
                    est = UNC_ERR_ENCRYPTED;
                } else if (aesmethod != 0 && aesmethod != 8) {
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
                        es.c = c;
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
                            est = zip_decode(c, &in, &es, aesmethod, usize,
                                             &crc, obuf, ocap);
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
                                                     usize, &crc, obuf, ocap);
                                if (est == UNC_OK &&
                                    ~crc != wantcrc)
                                    est = UNC_ERR_CRC;
                            }
                            goto entry_done;
                        }
                        if (est == UNC_OK) {
                            unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
                            in.limit = csize;
                            est = zip_decode(c, &in, &es, method, usize,
                                             &crc, obuf, ocap);
                        }
                        if (est == UNC_OK &&
                            ~crc != wantcrc)
                            est = UNC_ERR_CRC;
                    }
                }
            }
          entry_done:
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
            if (unc_fatal(est)) {
                err = est;
                break;
            }
        }

        cdrel += 46 + namelen + extralen + commentlen;
    }

    unc_free(c->al, cdbuf);
    unc_free(c->al, iobuf);
    return err;
}

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

int unc_gzip_probe(const uint8_t *head, int32_t len)
{
    return len >= 3 && head[0] == 0x1F && head[1] == 0x8B && head[2] == 8;
}

int unc_gzip_extract(UncCtx *c)
{
    uint8_t hdr[10], *iobuf, *obuf;
    uint32_t iocap = 4096, ocap = 8192;
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
        uint32_t produced = 0, crc = 0xFFFFFFFFu;
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
                if (unc_get_u32le(tr) != (crc ^ 0xFFFFFFFFu)) est = UNC_ERR_CRC;
                else if (unc_get_u32le(tr + 4) != produced) est = UNC_ERR_CRC;
            }
        }
    }
    if (c->sink->end_entry(c->sink->ctx, est) < 0) err = UNC_ERR_SINK;

out:
    unc_free(c->al, iobuf);
    return err;
}

/* ------------------------------------------------------------------ */
/* Unix compress .Z                                                   */
/* ------------------------------------------------------------------ */

int unc_compressz_probe(const uint8_t *head, int32_t len)
{
    return len >= 3 && head[0] == 0x1F && head[1] == 0x9D;
}

int unc_compressz_extract(UncCtx *c)
{
    uint8_t hdr[3], *iobuf, *obuf;
    uint32_t iocap = 4096, ocap = 8192;
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
        est = unc_lzw_init(&z, c->al, &in, maxbits, blockmode);
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
    if (est == UNC_ERR_SINK || est == UNC_ERR_ABORTED) err = est;

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

int unc_tar_probe(const uint8_t *head, int32_t len)
{
    int32_t i;
    if (len < 512) return 0;
    if (!tar_checksum_ok(head)) return 0;

    /* POSIX/old-GNU: "ustar" magic at 257 plus the checksum. */
    if (head[257] == 'u' && head[258] == 's' && head[259] == 't' &&
        head[260] == 'a' && head[261] == 'r')
        return 1;

    /* Pre-POSIX v7 tar has NO magic. XADTarParser falls back to the
     * *filename* for these, which our content-only rule forbids, so
     * we demand structure instead: a valid checksum plus well-formed
     * v7 fields (see DECISIONS.md M9/M10 follow-up).
     *   - name: NUL-terminated printable, non-empty
     *   - mode/uid/gid/size/mtime: octal fields
     *   - typeflag: NUL or '0'..'7' */
    if (head[0] == 0) return 0;
    for (i = 0; i < 100 && head[i]; i++)
        if (head[i] < 0x20 || head[i] == 0x7F) return 0;
    if (i == 100) return 0;                    /* name not terminated */
    if (!tar_field_ok(head + 100, 8)) return 0;   /* mode  */
    if (!tar_field_ok(head + 108, 8)) return 0;   /* uid   */
    if (!tar_field_ok(head + 116, 8)) return 0;   /* gid   */
    if (!tar_field_ok(head + 124, 12)) return 0;  /* size  */
    if (!tar_field_ok(head + 136, 12)) return 0;  /* mtime */
    if (head[156] != 0 && (head[156] < '0' || head[156] > '7')) return 0;
    return 1;
}

int unc_tar_extract(UncCtx *c)
{
    uint8_t h[512];
    uint32_t pos = 0, fsize;
    int seen = 0;
    int err = UNC_OK;
    uint8_t *iobuf;
    uint32_t iocap = 8192;

    fsize = c->io->size(c->io->ctx);
    iobuf = (uint8_t *)unc_alloc(c->al, iocap);
    if (!iobuf) return UNC_ERR_MEM;

    for (;;) {
        int64_t size;
        uint32_t datalen, padded;
        int typeflag, zero = 1, sret, est, isdir;
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
        if (size < 0 || size > 0x7FFFFFFF) { err = UNC_ERR_CORRUPT; break; }
        datalen = (uint32_t)size;
        padded = (datalen + 511u) & ~511u;

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
            if (pos + 512 + padded < pos) { err = UNC_ERR_CORRUPT; break; }
            pos += 512 + padded;
            continue;
        }

        unc_entry_clear(&e);
        unc_entry_set_path(&e, path, plen);
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
        } else if (typeflag == '0' || typeflag == 0) {   /* regular file */
            e.data_size = datalen;
            e.comp_data_size = datalen;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0) {
                est = UNC_OK;
                if (!c->opt.list_only) {
                    uint32_t left = datalen, at = pos + 512;
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
                if (est == UNC_ERR_SINK || est == UNC_ERR_ABORTED ||
                    est == UNC_ERR_IO) {
                    err = est;
                    break;
                }
            }
        } else {
            /* Links, devices, GNU extensions: reported, not extracted. */
            e.data_size = datalen;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0 &&
                c->sink->end_entry(c->sink->ctx, UNC_ERR_UNSUPPORTED) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
        }

        if (pos + 512 + padded < pos) { err = UNC_ERR_CORRUPT; break; }
        pos += 512 + padded;
    }

    unc_free(c->al, iobuf);
    return err;
}

/* ------------------------------------------------------------------ */
/* zip (EOCD + central directory; store and deflate)                  */
/* ------------------------------------------------------------------ */

int unc_zip_probe(const uint8_t *head, int32_t len)
{
    /* Local file header or (rarely first) central dir / EOCD magic. */
    if (len < 4) return 0;
    if (head[0] != 'P' || head[1] != 'K') return 0;
    return (head[2] == 3 && head[3] == 4) ||
           (head[2] == 5 && head[3] == 6);   /* empty archive */
}

static int zip_emit(void *ctx, const uint8_t *p, int32_t n)
{
    return exo_emit(ctx, p, n);
}

int unc_zip_extract(UncCtx *c)
{
    uint32_t fsize, scan, eocd = 0;
    uint8_t *tail = NULL, *iobuf = NULL, *obuf;
    uint32_t iocap = 4096, ocap = 8192;
    uint32_t nentries, cdoffs, cpos;
    uint8_t ce[46];
    int found = 0;
    uint32_t i;
    int err = UNC_OK;

    fsize = c->io->size(c->io->ctx);
    if (fsize == UNC_SIZE_UNKNOWN || fsize < 22) return UNC_ERR_FORMAT;

    /* Find the end-of-central-directory record in the last 66,000
     * bytes (EOCD is 22 bytes + up to 65,535 of comment). */
    scan = fsize < 66000 ? fsize : 66000;
    tail = (uint8_t *)unc_alloc(c->al, scan);
    if (!tail) return UNC_ERR_MEM;
    if (unc_read_at(c->io, fsize - scan, tail, (int32_t)scan) != UNC_OK) {
        unc_free(c->al, tail);
        return UNC_ERR_FORMAT;
    }
    for (i = scan - 22; ; i--) {
        if (tail[i] == 'P' && tail[i + 1] == 'K' &&
            tail[i + 2] == 5 && tail[i + 3] == 6) {
            eocd = i;
            found = 1;
            break;
        }
        if (i == 0) break;
    }
    if (!found) { unc_free(c->al, tail); return UNC_ERR_FORMAT; }

    nentries = unc_get_u16le(tail + eocd + 10);
    cdoffs   = unc_get_u32le(tail + eocd + 16);
    unc_free(c->al, tail);

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;

    cpos = cdoffs;
    for (i = 0; i < nentries; i++) {
        uint32_t method, flags, wantcrc, csize, usize;
        uint32_t namelen, extralen, commentlen, lhoffs;
        uint8_t name[256];
        uint32_t nread;
        UncEntryInfo e;
        int sret, est;

        if (unc_read_at(c->io, cpos, ce, 46) != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            break;
        }
        if (!(ce[0] == 'P' && ce[1] == 'K' && ce[2] == 1 && ce[3] == 2)) {
            err = UNC_ERR_CORRUPT;
            break;
        }
        flags      = unc_get_u16le(ce + 8);
        method     = unc_get_u16le(ce + 10);
        wantcrc    = unc_get_u32le(ce + 16);
        csize      = unc_get_u32le(ce + 20);
        usize      = unc_get_u32le(ce + 24);
        namelen    = unc_get_u16le(ce + 28);
        extralen   = unc_get_u16le(ce + 30);
        commentlen = unc_get_u16le(ce + 32);
        lhoffs     = unc_get_u32le(ce + 42);

        nread = namelen < sizeof name ? namelen : (uint32_t)sizeof name;
        if (nread &&
            unc_read_at(c->io, cpos + 46, name, (int32_t)nread) != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            break;
        }

        unc_entry_clear(&e);
        {
            uint32_t plen = nread;
            int isdir = plen > 0 && name[plen - 1] == '/';
            while (plen > 0 && name[plen - 1] == '/') plen--;
            unc_entry_set_path(&e, name, plen);   /* '/' native, raw bytes */
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
                if (flags & 0x0001) {
                    est = UNC_ERR_ENCRYPTED;
                } else if (method != 0 && method != 8) {
                    est = UNC_ERR_UNSUPPORTED;
                } else {
                    /* Local header gives the true data offset (its
                     * name/extra lengths may differ from the CD's). */
                    uint8_t lh[30];
                    if (unc_read_at(c->io, lhoffs, lh, 30) != UNC_OK ||
                        !(lh[0] == 'P' && lh[1] == 'K' && lh[2] == 3 &&
                          lh[3] == 4)) {
                        est = UNC_ERR_CORRUPT;
                    } else {
                        uint32_t dataat = lhoffs + 30 +
                            unc_get_u16le(lh + 26) + unc_get_u16le(lh + 28);
                        UncBufIn in;
                        uint32_t crc = 0xFFFFFFFFu, produced = 0;
                        ExoSink es;
                        es.c = c;
                        if (c->io->seek(c->io->ctx, dataat) < 0) {
                            est = UNC_ERR_IO;
                        } else if (method == 0) {
                            uint32_t left = usize;
                            est = UNC_OK;
                            unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
                            in.limit = csize;
                            while (left > 0 && est == UNC_OK) {
                                int b = unc_bufin_next(&in);
                                if (b < 0) { est = in.err; break; }
                                obuf[produced % ocap] = (uint8_t)b;
                                if (++produced % ocap == 0) {
                                    crc = unc_crc32(crc, obuf, (int32_t)ocap);
                                    est = exo_emit(&es, obuf, (int32_t)ocap);
                                }
                                left--;
                            }
                            if (est == UNC_OK && produced % ocap) {
                                crc = unc_crc32(crc, obuf,
                                                (int32_t)(produced % ocap));
                                est = exo_emit(&es, obuf,
                                               (int32_t)(produced % ocap));
                            }
                        } else {
                            unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
                            in.limit = csize;
                            est = unc_inflate_raw(&in, c->al, obuf, ocap,
                                                  usize, &produced, &crc,
                                                  zip_emit, &es);
                            if (est == UNC_OK && produced != usize)
                                est = UNC_ERR_TRUNCATED;
                        }
                        if (est == UNC_OK &&
                            (crc ^ 0xFFFFFFFFu) != wantcrc)
                            est = UNC_ERR_CRC;
                    }
                }
            }
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
            if (est == UNC_ERR_SINK || est == UNC_ERR_ABORTED ||
                est == UNC_ERR_IO) {
                err = est;
                break;
            }
        }

        cpos += 46 + namelen + extralen + commentlen;
    }

    unc_free(c->al, iobuf);
    return err;
}

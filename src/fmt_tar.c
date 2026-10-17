/*
 * fmt_tar.c — tar: POSIX ustar, pre-POSIX v7 headers (accepted by their
 * checksum alone), and pax extended headers.
 *
 * Source: reference/notes/posix_ustar.txt (POSIX.1-2017, the pax page,
 * "ustar Interchange Format" and "pax Extended Header"), cited at each
 * field below. The probe and the octal field readers are fmt_exo_probe.c's.
 *
 * Its own file, out of fmt_exo.c, since 2026-10-17: that file's 'OVLY'
 * image was within 600 B of the 32 KB a 68000's 16-bit PC-relative
 * references reach, and the metadata the three readers gained that day
 * would not fit beside it (DECISIONS.md 2026-10-17, *the archives' own
 * Finder info*). Tar calls no codec and nothing else in that image, so
 * it went into the small image only zip kept until then, `ovl_zipold`.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"
#include "fmt_exo_priv.h"
#include "unc_date.h"

/* Twice UNC_IOBUF, as fmt_exo.c's readers: member data is copied
 * straight through. */
#define TAR_BUF (2u * UNC_IOBUF)

/* ------------------------------------------------------------------ */
/* tar (POSIX ustar; pre-POSIX v7 headers accepted via checksum)      */
/* ------------------------------------------------------------------ */

int unc_tar_extract(UncCtx *c)
{
    uint8_t h[512];
    unc_off_t pos = 0, fsize;
    int seen = 0;
    int err = UNC_OK;
    uint8_t *iobuf;
    uint32_t iocap = TAR_BUF;
    /* What a pax 'x' header said about the member after it: its mtime
     * (Mac date, 0 for none) and its comment, in a buffer allocated the
     * first time one turns up. */
    uint32_t xmtime = 0, xclen = 0;
    uint8_t *xcmt = NULL;

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

        /* A pax extended header, 'x' for the member after it and 'g' for
         * all those after it, is records "%d %s=%s\n" of a decimal
         * length counting the whole record, a keyword and a value.
         * Source: reference/notes/posix_ustar.txt, *pax Extended Header*
         * ("This record shall override the mtime field in the following
         * header block(s)"; `comment`; *pax Extended Header File Times*:
         * decimal seconds, an optional fraction). Read: an 'x' header's
         * mtime and comment. A 'g' header is stepped over and applies
         * nothing, which is what this reader did with both before: they
         * were reported as members nobody could extract. */
        if ((typeflag == 'x' || typeflag == 'g') && !oversize) {
            if (typeflag == 'x' && datalen <= iocap &&
                unc_read_at(c->io, pos + 512, iobuf, (int32_t)datalen)
                    == UNC_OK) {
                uint32_t r = 0;
                xmtime = 0;
                xclen = 0;
                while (r < datalen) {
                    uint32_t len = 0, k = r, key, val;
                    while (k < datalen && iobuf[k] >= '0' && iobuf[k] <= '9'
                           && len < 100000u)
                        len = len * 10u + (uint32_t)(iobuf[k++] - '0');
                    if (k == r || k >= datalen || iobuf[k] != ' ' ||
                        len > datalen - r || len < 4)
                        break;
                    key = k + 1;
                    for (val = key; val < r + len && iobuf[val] != '='; val++) {}
                    if (val + 1 >= r + len) break;
                    val++;                     /* past '=' */
                    if (val - key == 6 && iobuf[key] == 'm' &&
                        iobuf[key + 1] == 't' && iobuf[key + 2] == 'i' &&
                        iobuf[key + 3] == 'm' && iobuf[key + 4] == 'e') {
                        uint32_t t = 0, q = val;
                        while (q < r + len && iobuf[q] >= '0' &&
                               iobuf[q] <= '9' && t <= 429496728u)
                            t = t * 10u + (uint32_t)(iobuf[q++] - '0');
                        if (q > val && q < r + len &&
                            (iobuf[q] == '.' || iobuf[q] == '\n'))
                            xmtime = unc_unix_to_mac(t);
                    } else if (val - key == 8 && iobuf[key] == 'c' &&
                               iobuf[key + 1] == 'o' && iobuf[key + 2] == 'm' &&
                               iobuf[key + 3] == 'm' && iobuf[key + 4] == 'e' &&
                               iobuf[key + 5] == 'n' && iobuf[key + 6] == 't') {
                        uint32_t n = r + len - 1 - val;   /* less '\n' */
                        if (!xcmt)
                            xcmt = (uint8_t *)unc_alloc(c->al,
                                                        UNC_ENTRY_COMMENT_MAX);
                        if (xcmt) {
                            uint32_t q;
                            if (n > UNC_ENTRY_COMMENT_MAX)
                                n = UNC_ENTRY_COMMENT_MAX;
                            for (q = 0; q < n; q++) xcmt[q] = iobuf[val + q];
                            xclen = n;
                        }
                    }
                    r += len;
                }
            }
            if (next < 0 || (uint64_t)next > (uint64_t)UNC_OFF_MAX) {
                err = UNC_ERR_CORRUPT; break;
            }
            pos = (unc_off_t)next;
            continue;
        }

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
        /* The mode's owner-write bit, 00200 (S_IWUSR), is the lock, and
         * mtime the modification date, a Unix time; a pax mtime before
         * this header overrides it. Source: reference/notes/posix_ustar.txt,
         * *ustar Interchange Format* (mode at 100, mtime at 136, octal;
         * the mode table). */
        e.locked = (tar_octal(h + 100, 8) & 0200) ? UNC_LOCK_NO
                                                  : UNC_LOCK_YES;
        {
            int64_t mt = tar_octal(h + 136, 12);
            if (mt > 0 && mt <= 0xFFFFFFFFll)
                e.mod_date = unc_unix_to_mac((uint32_t)mt);
        }
        if (xmtime) e.mod_date = xmtime;
        if (xclen) {
            e.comment = xcmt;
            e.comment_len = (uint16_t)xclen;
        }
        xmtime = xclen = 0;
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

    unc_free(c->al, xcmt);
    unc_free(c->al, iobuf);
    return err;
}

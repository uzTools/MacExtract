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
 * Mac OS X's sidecars since 2026-10-17: bsdtar's `._name`, the member
 * before `name`, is held and put on it (src/unc_sidecar.c; DECISIONS.md
 * 2026-10-17, *the sidecars Mac OS X left beside the file*).
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

/* A member's path: ustar prefix + '/' + name, raw bytes, '/' native,
 * "." components dropped and the trailing '/' gone. Sets *isdir. */
static uint32_t tar_path(const uint8_t *h, uint8_t *path, int *isdirp)
{
    uint32_t plen = 0;
    int32_t i;
    int isdir;
    /* Name: ustar prefix + '/' + name (raw bytes, '/' native). */
    if (h[345] && h[257] == 'u') {   /* prefix field in use */
        for (i = 0; i < 155 && h[345 + i]; i++) path[plen++] = h[345 + i];
        path[plen++] = '/';
    }
    for (i = 0; i < 100 && h[i]; i++) path[plen++] = h[i];
    /* Directory: typeflag '5' (ustar) or a trailing '/' in the
     * name (the only marking pre-POSIX v7 tar has). */
    isdir = h[156] == '5' ||
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
    *isdirp = isdir;
    return plen;
}

/* bsdtar's sidecar, `._name` just before `name` (unc_sidecar.c): what is
 * kept between the two members. Allocated at the first member named as a
 * sidecar, so a tar without one pays nothing. */
typedef struct TarSide {
    UncAdCap cap;
    unc_off_t at;               /* where the sidecar's bytes start */
    uint8_t pend;               /* the next member takes `cap`     */
    uint8_t h[512];
    uint8_t path[256];
} TarSide;

/* The member at `pos`, `len` bytes, is named as a sidecar: 1 if the next
 * member, at `next`, is the file or folder it names and it reads as one —
 * then it is held for that member and not emitted. 0 otherwise, including
 * when there is no memory for it: it then comes out as itself. */
static int tar_side(UncCtx *c, TarSide **pts, const uint8_t *path,
                    uint32_t plen, unc_off_t pos, uint32_t len, int64_t next,
                    uint8_t *buf, uint32_t cap)
{
    TarSide *ts = *pts;
    uint32_t n2, left = len;
    unc_off_t at = pos + 512;
    int dir2, t2, k2;
    int64_t sz;
    if (!ts) {
        ts = (TarSide *)unc_alloc(c->al, (uint32_t)sizeof *ts);
        if (!ts) return 0;
        ts->pend = 0;
        *pts = ts;
    }
    /* Over a pax header or two, which bsdtar writes for a member whose
     * name or times ustar cannot hold: the member they describe is the
     * one the sidecar must name. */
    for (k2 = 0; ; k2++) {
        if (next < 0 || (uint64_t)next > (uint64_t)UNC_OFF_MAX - 512 ||
            unc_read_at(c->io, (unc_off_t)next, ts->h, 512) != UNC_OK ||
            !tar_checksum_ok(ts->h))
            return 0;
        t2 = ts->h[156];
        if ((t2 != 'x' && t2 != 'g') || k2 == 2) break;
        sz = tar_octal(ts->h + 124, 12);
        if (sz < 0) return 0;
        next += 512 + ((sz + 511) & ~(int64_t)511);
    }
    n2 = tar_path(ts->h, ts->path, &dir2);
    if (!dir2 && ((t2 != '0' && t2 != 0) ||
                  tar_octal(ts->h + 124, 12) > (int64_t)UNC_MAC_MAX))
        return 0;
    if (!unc_side_of(path, plen, ts->path, n2)) return 0;
    unc_ad_init(&ts->cap, len);
    while (left > 0) {
        uint32_t k = left < cap ? left : cap;
        if (unc_read_at(c->io, at, buf, (int32_t)k) != UNC_OK ||
            unc_ad_feed(&ts->cap, buf, k))
            break;
        at += k;
        left -= k;
    }
    unc_ad_end(&ts->cap);
    if (ts->cap.state != UNC_AD_YES) return 0;
    ts->at = pos + 512;
    ts->pend = 1;
    return 1;
}

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
    TarSide *ts = NULL;

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
        int pend;

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
                            /* UTF-8 ("the value field for all other
                             * keywords ... shall be encoded using UTF-8",
                             * reference/notes/posix_ustar.txt, pax), so
                             * the cut backs off a continuation byte. */
                            if (n > UNC_ENTRY_COMMENT_MAX) {
                                n = UNC_ENTRY_COMMENT_MAX;
                                while (n && (iobuf[val + n] & 0xC0u) == 0x80u)
                                    n--;
                            }
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

        plen = tar_path(h, path, &isdir);
        if (plen == 0 && isdir) {
            /* The "./" root entry itself: nothing to create. */
            if (next < 0 || (uint64_t)next > (uint64_t)UNC_OFF_MAX) {
                err = UNC_ERR_CORRUPT; break;
            }
            pos = (unc_off_t)next;
            continue;
        }

        /* Mac OS X's sidecars (unc_sidecar.c): their folders are never
         * emitted, and one held for this member is put on it. A sidecar
         * held for the next member takes its own pax header's values with
         * it, so they do not land on that member. */
        if (isdir && unc_side_kind(path, plen, 1) == UNC_SIDE_DIR)
            goto tar_next;
        pend = ts && ts->pend;
        if (ts) ts->pend = 0;
        if (!isdir && !oversize && (typeflag == '0' || typeflag == 0) &&
            unc_side_kind(path, plen, 0) == UNC_SIDE_FILE &&
            tar_side(c, &ts, path, plen, pos, datalen, next, iobuf, iocap)) {
            xmtime = xclen = 0;
            goto tar_next;
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
        /* Both are Unix times: an instant (macextract.h). */
        if (e.mod_date) e.meta |= UNC_META_MD_UTC;
        if (xclen) {
            e.comment = xcmt;
            e.comment_len = (uint16_t)xclen;
            e.meta |= UNC_META_CMT_UTF8;
        }
        xmtime = xclen = 0;
        e.rsrc_size = 0;
        if (pend) {
            unc_ad_apply(&ts->cap, &e);
            if (!isdir) e.rsrc_size = ts->cap.rlen;
        }

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
                    /* The held sidecar's resource fork, read in place. */
                    if (est == UNC_OK && pend && ts->cap.rlen) {
                        if (c->io->seek(c->io->ctx,
                                        ts->at + ts->cap.roff) < 0)
                            est = UNC_ERR_IO;
                        else
                            est = unc_copy_fork(c, UNC_FORK_RSRC,
                                                ts->cap.rlen, iobuf, iocap);
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

      tar_next:
        if (next < 0 || (uint64_t)next > (uint64_t)UNC_OFF_MAX) {
            err = UNC_ERR_CORRUPT; break;
        }
        pos = (unc_off_t)next;
    }

    unc_free(c->al, ts);
    unc_free(c->al, xcmt);
    unc_free(c->al, iobuf);
    return err;
}

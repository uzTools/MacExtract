/* fmt_zipseg_priv.h — what a spanned zip part's probe and its reader share.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_ZIPSEG_PRIV_H
#define UNC_FMT_ZIPSEG_PRIV_H

#include "unc_internal.h"

/* EOCD: 22 fixed bytes plus a comment of up to 65,535. */
#define ZS_EOCD_FIXED   22
#define ZS_EOCD_MAXBACK (ZS_EOCD_FIXED + 65535u)

/* The six fields of the record both zip probes judge a file by.
 *
 * Source: reference/notes/zip_appnote.txt 4.3.16, the End of central
 * directory record, read in order from its signature: "number of this
 * disk" at 4, "number of the disk with the start of the central
 * directory" at 6, "total number of entries in the central directory on
 * this disk" at 8, "total number of entries in the central directory"
 * at 10, "size of the central directory" at 12, "offset of start of
 * central directory with respect to the starting disk number" at 16.
 * Every one is Intel byte order (4.4.1.1) and read a byte at a time. */
typedef struct {
    uint32_t disknum;    /* 4.4.19 */
    uint32_t cddisk;     /* 4.4.20 */
    uint32_t here;       /* 4.4.21 — entries in the directory on this disk */
    uint32_t total;      /* 4.4.22 */
    uint32_t cdsize;     /* 4.4.23 */
    uint32_t cdoff;      /* 4.4.24 */
} ZsEocd;

/* The scanner's reader, for a caller that has a plain stream. */
int zs_io_read_at(void *ctx, uint32_t off, void *buf, int32_t len);

/* The record's offset, by the backwards scan unc_zip_scan_eocd does.
 * Inline, as it was when the probe and the reader shared a file: a
 * call to a one-line wrapper is 30 B on a 68000. */
static inline int zs_find_eocd(UncIO *io, uint32_t fsize, uint32_t *at)
{
    return unc_zip_scan_eocd(io, zs_io_read_at, fsize, at);
}

int zs_read_eocd(UncIO *io, uint32_t at, ZsEocd *e);

#endif

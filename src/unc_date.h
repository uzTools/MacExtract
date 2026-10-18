/*
 * unc_date.h — foreign timestamps as Macintosh dates (seconds since
 * 1904-01-01 00:00, the unit of ioFlCrDat/ioFlMdDat).
 *
 * Static functions in a header, not a resident routine: their callers
 * (fmt_exo.c, fmt_arc.c, fmt_lzh.c) are each in an 'OVLY' image of its
 * own, so each image carries the copy it uses and the resident
 * application carries none (FORMATS.md, *Overlays*).
 *
 * THE TIME ZONE RULE (DECISIONS.md 2026-10-17, *the archives' own Finder
 * info*, and *dates in the Macintosh's own zone*, the maintainer's):
 *   - an MS-DOS date and time is the WALL CLOCK of the machine that
 *     wrote it, with no zone; so is a Macintosh date. It is carried
 *     across as wall clock, unchanged, and not marked.
 *   - a Unix time (and a Windows FILETIME) is an instant, UTC. The
 *     engine knows no zone, so it becomes the Macintosh date whose wall
 *     clock reads that instant in UTC: unix + 2,082,844,800 — and the
 *     reader sets that date's UNC_META_*_UTC bit (macextract.h), so a
 *     host that knows its zone can show it in local time.
 *
 * 0 is "not stated" to every host (macextract.h), so a date this cannot
 * represent — before 1904, after 2040-02-06 06:28:15, or a field out of
 * range — comes back 0 rather than wrapped.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_DATE_H
#define UNC_DATE_H

#include <stdint.h>

/* 1904-01-01 to 1970-01-01 in seconds: 66 years, 17 of them leap. */
#define UNC_MAC_UNIX_DELTA 2082844800u

/* A Unix time, as an unsigned count; a negative one (before 1970) is the
 * caller's to bring in, since only tar can hold one. */
static inline uint32_t unc_unix_to_mac(uint32_t t)
{
    return t <= 0xFFFFFFFFu - UNC_MAC_UNIX_DELTA ? t + UNC_MAC_UNIX_DELTA
                                                 : 0;
}

/* An MS-DOS date and time word: date bits 15-9 years since 1980, 8-5
 * month 1-12, 4-0 day 1-31; time bits 15-11 hours, 10-5 minutes, 4-0
 * seconds / 2.
 * Source: reference/lha/src/header.c, generic_to_unix_stamp (the field
 * layout, the days-before-month table, and "if MSDOS format date and
 * time were zero, then we set time to be zero here too"); the same
 * packing is APPNOTE.TXT 4.4.6's "standard MS-DOS format". The leap
 * rule is the Gregorian one, which header.c applies too; within the
 * 1980-2107 a DOS date can hold, only 2100 is affected. */
#if defined(__GNUC__)
/* Not inlined: a file calls it from two or three places, and every copy
 * is ~150 B of an image that has none to spare (fmt_tar.c says why). */
__attribute__((unused, noinline))
#endif
static uint32_t unc_dos_to_mac(uint32_t date, uint32_t time)
{
    static const uint16_t before[12] = { 0, 31, 59, 90, 120, 151, 181,
                                         212, 243, 273, 304, 334 };
    uint32_t y = (date >> 9) & 0x7Fu, m = (date >> 5) & 0x0Fu,
             d = date & 0x1Fu;
    uint32_t hh = (time >> 11) & 0x1Fu, mm = (time >> 5) & 0x3Fu,
             ss = (time & 0x1Fu) * 2u;
    uint32_t days;

    if (m < 1 || m > 12 || d < 1 || hh > 23 || mm > 59 || ss > 59)
        return 0;
    /* 1904-01-01 to 1980-01-01 is 76 years, 19 of them leap (1904 to
     * 1976), then whole years since 1980, a leap day for each leap year
     * before this one (1980 is one; 2100 is not). */
    days = 27759u + y * 365u + (y + 3u) / 4u - (y > 120u ? 1u : 0u);
    y += 1980u;
    days += before[m - 1] + d - 1u;
    if (m > 2 && (y & 3u) == 0 && y != 2100u) days++;
    if (days > 49709u) return 0;   /* 2040-02-06 on: no Mac date whole */
    return days * 86400u + hh * 3600u + mm * 60u + ss;
}

#endif

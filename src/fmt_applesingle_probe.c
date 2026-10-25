/* fmt_applesingle_probe.c — the AppleSingle / AppleDouble probe.
 *
 * Every probe is in its reader's `_probe.c` (DECISIONS.md 2026-10-20, *one
 * place for every probe*), and the Macintosh application carries them all,
 * with the sniffer, in one `'OVLY'` image run before the release and given
 * back with it (DECISIONS.md 2026-10-21, *the probes that left with the
 * bundle*). What a probe and its reader share is defined once, here, and
 * stays resident for the reader.
 *
 * The magics and the byte-swapped pair it also accepts are
 * fmt_applesingle_priv.h's; what accepting them rests on is
 * fmt_applesingle.c's file comment.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_applesingle_priv.h"

/* The magics and versions of fmt_applesingle_priv.h, compared as the
 * bytes they are: a probe that compares fields with small constants
 * should compare bytes (DECISIONS.md 2026-10-09, *the probe was the
 * outlier*). Either byte order of the magic goes with either of the
 * version, exactly as the word compares before 2026-10-20 had it. */
UncFormat unc_applesingle_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    int single;
    (void)io;
    if (len < 8) return UNC_FORMAT_UNKNOWN;
    if (head[0] == 0x00 && head[1] == 0x05 && head[2] == 0x16 &&
        (head[3] == 0x00 || head[3] == 0x07))
        single = head[3] == 0x00;                 /* 00 05 16 00 / 07 */
    else if (head[1] == 0x16 && head[2] == 0x05 && head[3] == 0x00 &&
             (head[0] == 0x00 || head[0] == 0x07))
        single = head[0] == 0x00;                 /* 00 / 07 16 05 00 */
    else
        return UNC_FORMAT_UNKNOWN;
    if (head[4] != 0x00 || head[7] != 0x00 ||
        !((head[5] == 0x02 && head[6] == 0x00) ||  /* 00 02 00 00 */
          (head[5] == 0x00 && head[6] == 0x02)))   /* 00 00 02 00 */
        return UNC_FORMAT_UNKNOWN;
    return single ? UNC_FORMAT_APPLESINGLE : UNC_FORMAT_APPLEDOUBLE;
}

/* The reader's, kept here because it is SHARED: fmt_applesingle.c calls
 * it, and so do fmt_mime.c (multipart/appledouble) and unc_sidecar.c (Mac
 * OS X's `._` files). On the Macintosh those are images that reach it
 * through the host vector, so it is resident, and the reader is not. */
/* Seconds between the Mac epoch (1904-01-01) and the AppleSingle
 * dates epoch (2000-01-01): 96 years of 365 days + 24 leap days =
 * 35064 days = 3029529600 s = 0xB492F400 (naive time, no leap secs). */
#define AS_EPOCH_2000_AS_MAC 0xB492F400u

/* One of the fixed records, 8 to 12, into `e`: `p` holds the entry's first
 * `n` bytes, at most 32 (the largest, entry 9). Shared with fmt_mime.c,
 * whose multipart/appledouble header part is this same structure, so the
 * two read one record one way.
 *
 * Source: reference/notes/rfc1740.txt, appendix B.
 *  - 8, ASFileDates: create, modify, backup, access, each signed seconds
 *    from 2000-01-01 GMT, and "Any unknown entries are set to 0x80000000".
 *    An unknown date is left unstated — 0 for the two the engine has
 *    always carried, which is its "unknown", and no UNC_META_BACKUP for
 *    the third. Until 2026-10-17 the first two were converted anyway and
 *    came out as 1931-12-13. Access has nowhere to go: HFS keeps none.
 *  - 9, ASFinderInfo: FInfo then FXInfo, 16 bytes each. A record cut
 *    short states only the halves it holds whole.
 *  - 10, ASMacInfo: three filler bytes, then ioFlAttrib, whose 0x01 is
 *    AS_LOCKED. (0x02, AS_PROTECTED, is the copy-protect bit; HFS keeps
 *    it in no field a program can set.)
 *  - 12, ASMsdosInfo: a filler byte, then the attribute, whose 0x01 is
 *    AS_DOS_READONLY — read-only on DOS is how HFS spells locked.
 * Either of 10 or 12 locks the file; neither unlocks one the other
 * locked. Entry 11, ProDOS's access word, is not read: the RFC gives its
 * size and not its bits, and no reference here does. */
void unc_as_record(UncEntryInfo *e, uint32_t id, const uint8_t *p, uint32_t n)
{
    uint32_t k, d;
    switch (id) {
    case 8:
        for (k = 0; k + 4 <= n && k < 12; k += 4) {
            d = unc_get_u32be(p + k);
            if (d == 0x80000000u) continue;
            d += AS_EPOCH_2000_AS_MAC;
            /* GMT seconds: an instant, so each date is marked UTC
             * (macextract.h; DECISIONS.md 2026-10-17, *dates in the
             * Macintosh's own zone*, which also has mpack's writer,
             * which does not follow the RFC here). */
            if (k == 0) {
                e->create_date = d;
                e->meta |= UNC_META_CR_UTC;
            } else if (k == 4) {
                e->mod_date = d;
                e->meta |= UNC_META_MD_UTC;
            } else {
                e->backup_date = d;
                e->meta |= UNC_META_BACKUP | UNC_META_BK_UTC;
            }
        }
        break;
    case 9:
        if (n >= 10) {
            e->type         = unc_get_u32be(p);
            e->creator      = unc_get_u32be(p + 4);
            e->finder_flags = unc_get_u16be(p + 8);
        }
        for (k = 0; k < n && k < 32; k++) e->finder_info[k] = p[k];
        if (n >= 16) e->meta |= UNC_META_FINFO;
        if (n >= 32) e->meta |= UNC_META_FXINFO;
        break;
    case 10:
    case 12:
        k = id == 10 ? 3u : 1u;
        if (n > k && e->locked != UNC_LOCK_YES)
            e->locked = (p[k] & 0x01) ? UNC_LOCK_YES : UNC_LOCK_NO;
        break;
    default:
        break;
    }
}

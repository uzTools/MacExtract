/* fmt_applesingle_probe.c — the AppleSingle / AppleDouble probe.
 *
 * Every probe is in its reader's `_probe.c`, resident, so the reader can
 * be an overlay: unc_sniff calls every probe for every file it is handed,
 * before any image is chosen (DECISIONS.md 2026-10-20, *one place for
 * every probe*). What a probe and its reader share is defined once, here.
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

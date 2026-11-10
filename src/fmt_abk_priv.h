/* fmt_abk_priv.h — what Apple Backup's probe, its set identity and its
 * reader share.
 *
 * The layout, and where each fact comes from, is src/fmt_abk.c's file
 * comment.
 *
 * SPDX-License-Identifier: 0BSD
 */
#ifndef UNC_FMT_ABK_PRIV_H
#define UNC_FMT_ABK_PRIV_H

#include "unc_internal.h"

#define ABK_DISK_MAGIC 0x434D574Cul   /* 'CMWL', at +2 of every disk     */
#define ABK_ITEM_MAGIC 0x524C4457ul   /* 'RLDW', at +2 of every item     */
#define ABK_DISK_HDR   0x3Au          /* the disk header's fields         */
#define ABK_FIRST      0x600u         /* the first item: past the 0x200-
                                       * byte header and 0x400 of boot
                                       * blocks                           */
#define ABK_ITEM_HDR   0x70u
#define ABK_ALIGN      0x200u         /* every item starts on one         */

/* The disk header's own claims about itself: its magic, a disk number
 * within the count, and a used length within the file's. Everything a
 * describe, a match and the reader ask of a disk before trusting it. */
static inline int abk_disk_ok(const uint8_t *h)
{
    uint16_t n = unc_get_u16be(h + 6), t = unc_get_u16be(h + 8);
    uint32_t used = unc_get_u32be(h + 0x36);
    return unc_get_u32be(h + 2) == ABK_DISK_MAGIC && n >= 1 && n <= t &&
           used >= ABK_FIRST && used <= unc_get_u32be(h + 0x32);
}

#endif

/* fmt_abk_probe.c — the probe for one disk of an Apple Backup set.
 *
 * Every probe is in its reader's `_probe.c` (DECISIONS.md 2026-10-20, *one
 * place for every probe*), and the Macintosh application carries them all,
 * with the sniffer, in one `'OVLY'` image run before the release and given
 * back with it (DECISIONS.md 2026-10-21, *the probes that left with the
 * bundle*).
 *
 * The layout, and where each fact comes from, is fmt_abk.c's file comment.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_abk_priv.h"

/* A disk: 'CMWL' at +2, a disk number within the count and a used length
 * within the file's (abk_disk_ok), and the first item's 'RLDW' at 0x600.
 * Every disk has an item there — a disk that ends before 0x600 has no
 * room for one, and an item cut at a disk's end is repeated at 0x600 of
 * the next — so two four-byte magics, 0x600 apart, are what claims one.
 * Its byte 0 is the version's high byte, 0x01 in every disk here, so
 * MacBinary below cannot take one; nothing above it has 'CMWL' at +2. */
UncFormat unc_abk_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint8_t item[6];

    if (len < (int32_t)ABK_DISK_HDR || !abk_disk_ok(head))
        return UNC_FORMAT_UNKNOWN;
    if (unc_get_u32be(head + 0x36) < ABK_FIRST + ABK_ITEM_HDR ||
        unc_read_at(io, ABK_FIRST, item, 6) != UNC_OK ||
        unc_get_u32be(item + 2) != ABK_ITEM_MAGIC)
        return UNC_FORMAT_UNKNOWN;
    return UNC_FORMAT_ABK;
}

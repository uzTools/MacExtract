/* fmt_tome_probe.c — the Apple Installer Tome's probe, in the sniffer's
 * image.
 *
 * The magic and the record count are the specification's (fmt_tome.c).
 * The specification leaves the rest of the header unread; the long
 * tested beside them is MEASURED, constant over every Tome this machine
 * holds — 39 files off the System 7.5.5 and Mac OS 8.6 install media and
 * the 13 one-file Tomes QuickDraw GX keeps in 'part' resources: the
 * long at 0x16 is 0x24, where the records begin (DECISIONS.md
 * 2026-11-10, *the archive the Installer reads*). A four-byte magic alone
 * is weak; with it the test is eight bytes, a count that is not zero, and
 * a table that fits the file.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_tome_priv.h"

UncFormat unc_tome_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t n;
    unc_off_t size;
    if (len < (int32_t)TOME_HDR || unc_get_u32be(head) != TOME_MAGIC ||
        unc_get_u32be(head + 0x16) != TOME_HDR)
        return UNC_FORMAT_UNKNOWN;
    n = unc_get_u16be(head + 0x1a);
    if (n == 0)
        return UNC_FORMAT_UNKNOWN;
    size = io->size(io->ctx);
    if (size != UNC_OFF_UNKNOWN && TOME_HDR + n * TOME_REC > size)
        return UNC_FORMAT_UNKNOWN;
    return UNC_FORMAT_TOME;
}

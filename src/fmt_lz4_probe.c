/* fmt_lz4_probe.c — an LZ4 frame's probe, in the sniffer's image.
 *
 * Source: reference/notes/lz4_Frame_format.md: the magic number, then a
 * frame descriptor whose version is 01, whose reserved bits are zero and
 * whose block maximum size is one of the four the specification defines.
 * The header checksum is left to the reader: the magic and these bits are
 * already a test no other format here passes.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_lz4_priv.h"

UncFormat unc_lz4_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint8_t flg, bd;
    (void)io;
    if (len < 7 || unc_get_u32le(head) != LZ4_MAGIC) return UNC_FORMAT_UNKNOWN;
    flg = head[4];
    bd = head[5];
    if ((flg & LZ4_FLG_VERSION) != LZ4_FLG_V01 || (flg & LZ4_FLG_RESV) ||
        (bd & LZ4_BD_RESV) || (bd >> 4) < 4)
        return UNC_FORMAT_UNKNOWN;
    return UNC_FORMAT_LZ4;
}

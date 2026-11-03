/* fmt_mar_priv.h — what fmt_mar.c and its probe share.
 *
 * Source: reference/mar/mac-utils/src/lib/mar.h (MAR_MAGIC, MAR_FILE,
 * MAR_FOLDER_START, MAR_FOLDER_END, MAR_CRC_POLY) and src/lib/mar.c
 * (mar_calc_crc, mar_is_mar). The rest of the layout, and where each field
 * comes from, is in fmt_mar.c's header comment.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_MAR_PRIV_H
#define UNC_FMT_MAR_PRIV_H

#include "unc_internal.h"

#define MAR_HDR      128u
#define MAR_MAGIC    0x4D415280u   /* "MAR" 0x80 */
#define MAR_FILE     0x66696C65u   /* 'file' */
#define MAR_FOLDER   0x666F6C64u   /* 'fold' */
#define MAR_END      0x2D2D2D2Du   /* '----' */

/* CRC-32 over polynomial 0x1EDC6F41, most significant bit first, from 0,
 * nothing inverted: the header's at +124 over its first 124 bytes, and
 * each stored block's in the 4 bytes after it. */
uint32_t unc_mar_crc(uint32_t crc, const uint8_t *p, uint32_t n);

/* The record's magic and CRC both hold. */
int unc_mar_hdr_ok(const uint8_t *h);

#endif

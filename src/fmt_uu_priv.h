/* fmt_uu_priv.h — what uuencode's probe and its decoder both need.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_UU_PRIV_H
#define UNC_FMT_UU_PRIV_H

#include "unc_internal.h"

#define UU_LINE_MAX   UNC_UU_LINE_MAX
#define UU_DEC_MAX    UNC_UU_DEC_MAX
#define UU_SCAN_MAX   8192u
#define UU_SIXB(c) (((c) - 0x20) & 0x3f)

/* UUTool encodes with one of two alphabets, and `unc_uu_line_is_data`
 * reports which of them a line could have come from. Source: the
 * application's own `HEXA` 128 "PC" and `HEXA` 129 "UNIX" tables,
 * read out of UUTool 2.3.2 by tools/derive_mu.py. */
#define UU_TBL_PC     1     /* value v -> 0x20+v, the standard alphabet */
#define UU_TBL_UNIX   2     /* the low values moved up past it: 0x3b..0x7d */
#define UU_TBL_ANY    (UU_TBL_PC | UU_TBL_UNIX)
/* The two ranges. "PC" is 0x20..0x5f as UUTool's table gives it, plus
 * 0x60, which is how every Unix `uuencode` since 4.2BSD spells the
 * value ZERO so that a mailer stripping trailing whitespace cannot eat
 * it: ENC(c) = (c) ? ((c) & 077) + ' ' : '`'. The two UNIX generations
 * together are 0x3b..0x7d, and 0x60 is inside them as a value of its
 * own, so a backtick narrows nothing and the two spellings of zero both
 * read as zero under UU_SIXB. A character outside both ranges is not a
 * uu character at all.
 * Source: reference/mpack/uudecode.c, which takes ' ' OR '`' as the
 * zero-length line at st_decode and st_nextlast — the same value, the
 * two ways encoders write it. Narrowing this to 0x5f on 2026-10-06 cost
 * every file BSD and GNU uuencode write (BLOCKERS.md). */
#define UU_CH_MIN     0x20
#define UU_UNIX_MIN   0x3b  /* below this: "PC" only   */
#define UU_PC_MAX     0x60  /* above this: "UNIX" only */
#define UU_CH_MAX     0x7d

int unc_uu_line_is_data(const uint8_t *line, int32_t len);

#endif

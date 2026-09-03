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

int unc_uu_line_is_data(const uint8_t *line, int32_t len);

#endif

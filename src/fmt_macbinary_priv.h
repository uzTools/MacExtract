/* fmt_macbinary_priv.h — what MacBinary's probe and its reader share.
 *
 * SPDX-License-Identifier: 0BSD
 */
#ifndef UNC_FMT_MACBINARY_PRIV_H
#define UNC_FMT_MACBINARY_PRIV_H

#include "unc_internal.h"

#define MB_HDR 128
#define MB_PAD(n) (((n) + 127u) & ~127u)

/* MacBinary version 1..3, or 0 if the header is not MacBinary. */
int mb_version(const uint8_t *b, int32_t len);

#endif

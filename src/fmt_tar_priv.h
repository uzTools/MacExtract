/* fmt_tar_priv.h — what tar's probe and its reader share.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_TAR_PRIV_H
#define UNC_FMT_TAR_PRIV_H

#include "unc_internal.h"

int64_t tar_octal(const uint8_t *p, int32_t n);
int tar_field_ok(const uint8_t *p, int32_t n);
int tar_checksum_ok(const uint8_t *h);

#endif

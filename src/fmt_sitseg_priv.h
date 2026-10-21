/* fmt_sitseg_priv.h — what a StuffIt segment's probe and its reader share.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_SITSEG_PRIV_H
#define UNC_FMT_SITSEG_PRIV_H

#include "unc_internal.h"

/* Parse and validate a header. Returns UNC_OK or UNC_ERR_FORMAT.
 * `desc` may be NULL to validate only. */
int sitseg_parse(const uint8_t *h, int32_t len, UncSegmentDesc *desc);

#endif

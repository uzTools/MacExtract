/* fmt_exo_priv.h — what the non-Macintosh probes and their decoder share.
 *
 * The probes stay resident and the decoder can be an overlay, so tar's two
 * field checks are declared here and defined once, in the probe file.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_EXO_PRIV_H
#define UNC_FMT_EXO_PRIV_H

#include "unc_internal.h"

int64_t tar_octal(const uint8_t *p, int32_t n);
int tar_field_ok(const uint8_t *p, int32_t n);
int tar_checksum_ok(const uint8_t *h);

#endif

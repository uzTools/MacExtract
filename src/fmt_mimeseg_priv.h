/* fmt_mimeseg_priv.h — what a `message/partial` part's probe and its reader share.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_MIMESEG_PRIV_H
#define UNC_FMT_MIMESEG_PRIV_H

#include "unc_internal.h"

typedef struct MsegInfo {
    uint32_t body;               /* offset of the first body byte      */
    int      part;               /* the `number` parameter             */
    int      nparts;             /* the `total` parameter, or 0        */
    uint8_t  id[UNC_SEG_FP_LEN]; /* the `id` parameter, first 26 bytes */
    uint32_t idlen;
    int      partial;            /* the Content-Type was message/partial */
} MsegInfo;

/* Walk a part's headers for the three parameters that matter; then
 * everything mpack refuses a part for, in its own order. */
int mseg_scan(UncIO *io, MsegInfo *mi);
int mseg_ok(const MsegInfo *mi);

#endif

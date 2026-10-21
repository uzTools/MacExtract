/* fmt_ddseg_priv.h — what a DiskDoubler `SPLT` part's probe and its reader share.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_DDSEG_PRIV_H
#define UNC_FMT_DDSEG_PRIV_H

#include "unc_internal.h"

#define DS_ID        4          /* start of the 26 fingerprint bytes:
                                 * split time, both fork lengths, type,
                                 * creator, flags and the two dates */
#define DS_DATALEN   8
#define DS_RSRCLEN  12
#define DS_TYPE     16
#define DS_CREATOR  20
#define DS_FFLAGS   24
#define DS_MTIME    32
#define DS_CTIME    36
#define DS_NPARTS   40
#define DS_INDEX    42
#define DS_PAYLEN   44
#define DS_CRC      48
#define DS_MAGIC2   90

/* Parse and validate a header. `desc` may be NULL to validate only;
 * `paylen`, if given, receives this part's payload length. */
int ddseg_parse(const uint8_t *h, int32_t len, UncSegmentDesc *desc,
                uint32_t *paylen);

#endif

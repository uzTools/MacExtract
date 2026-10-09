/* fmt_pf_priv.h — what fmt_pf.c and its resident probe share.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_PF_PRIV_H
#define UNC_FMT_PF_PRIV_H

#define PF_MAGIC  0x43534954u          /* 'CSIT' */
#define PF_HDR    18u
#define PF_REC    308u
#define PF_FOOT   12u
#define PF_FIXED  (PF_HDR + PF_REC + PF_FOOT)

#endif

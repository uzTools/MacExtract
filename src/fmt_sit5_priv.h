/* fmt_sit5_priv.h — what StuffIt 5's probe and its decoder both need.
 *
 * They are compiled into different places: the probe stays resident, the
 * decoder goes into an overlay. One definition, in the probe, declared here
 * — rather than a copy in each, which is what rule #1 forbids.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_SIT5_PRIV_H
#define UNC_FMT_SIT5_PRIV_H

#include "unc_internal.h"



extern const char sit5_banner[] ;

#endif

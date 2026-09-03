/* fmt_binhex_priv.h — what BinHex's probe and its decoder both need.
 *
 * They are compiled into different places: the probe stays resident, the
 * decoder goes into an overlay. One definition, in the probe, declared here
 * — rather than a copy in each, which is what rule #1 forbids.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_BINHEX_PRIV_H
#define UNC_FMT_BINHEX_PRIV_H

#include "unc_internal.h"

#define BH_SNIFF_LIMIT 8192

extern const char bh_banner[40] ;

#endif

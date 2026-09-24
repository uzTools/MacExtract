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

/* How far into the file we are willing to look for the banner when
 * sniffing. No specification bounds this — Lewis says only that a hqx
 * file "begins with a description which should be ignored" — so 8 KB is
 * a choice, and it is the same one XADMaster makes. */
#define BH_SNIFF_LIMIT 8192

/* The banner, truncated exactly where the spec says to stop comparing:
 * "when decoding, you should only check the string up to 'with
 * BinHex'". Source: binhex40_lewis.txt. What follows is the version
 * number, which is why it is not compared. */
extern const char bh_banner[40] ;

#endif

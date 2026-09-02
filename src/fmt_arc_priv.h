/* fmt_arc_priv.h — the header check shared by ARC's probe and its decoder.
 *
 * The two are compiled into different places: the probe is resident, the
 * decoder can be an overlay (BRANCH_NOTES.md). This is the one thing they
 * both need.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_ARC_PRIV_H
#define UNC_FMT_ARC_PRIV_H

#include "unc_internal.h"

#define ARC_M_STORED_OLD  0x01
#define ARC_M_STORED      0x02
#define ARC_M_PACKED      0x03
#define ARC_M_SQUEEZED    0x04
#define ARC_M_CRUNCH5     0x05
#define ARC_M_CRUNCH6     0x06
#define ARC_M_CRUNCH7     0x07
#define ARC_M_CRUNCH8     0x08
#define ARC_M_SQUASHED    0x09
#define ARC_M_CRUSHED     0x0a
#define ARC_M_DISTILLED   0x0b
#define ARC_M_INFO        0x14   /* archive info      (ARC 7.x)      */
#define ARC_M_FILEINFO    0x15   /* extended file info                */
#define ARC_M_OSINFO      0x16   /* OS-specific info                  */
#define ARC_M_DIR         0x1e
#define ARC_M_DIREND      0x1f
#define ARC_M_COMPRESSED  0x7f

#define ARC_HDR_MIN       0x1d   /* 0x1a, method, 13 name, 4+2+2+2, 4 */
#define ARC_NAME_LEN      13
#define AM_MAGIC1      0
#define AM_KIND        1
#define AM_FNAME       2      /* 31 bytes, NUL-padded */
#define AM_FTYPE      34
#define AM_FAUTH      38
#define AM_FINFO      42
#define AM_FDATA      50      /* data fork length   */
#define AM_FRSRC      54      /* rsrc fork length   */
#define AM_MAGIC2     59      /* the PC ARC header starts here */
#define AM_HDRBYTES   88

#define arc_is_item(m) ((m) == ARC_M_INFO || (m) == ARC_M_FILEINFO || \
                        (m) == ARC_M_OSINFO)

int arc_name_ok(const uint8_t *p);

#endif

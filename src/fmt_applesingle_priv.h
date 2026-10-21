/* fmt_applesingle_priv.h — what AppleSingle's probe and its reader share.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_APPLESINGLE_PRIV_H
#define UNC_FMT_APPLESINGLE_PRIV_H

#include "unc_internal.h"

/* The byte-swapped pair is a tolerance the RFC forbids; fmt_applesingle.c's
 * file comment says whose it is. */
#define AS_MAGIC_SINGLE     0x00051600u
#define AS_MAGIC_DOUBLE     0x00051607u
#define AS_MAGIC_SINGLE_LE  0x00160500u
#define AS_MAGIC_DOUBLE_LE  0x07160500u
#define AS_VERSION          0x00020000u
#define AS_VERSION_LE       0x00000200u

#endif

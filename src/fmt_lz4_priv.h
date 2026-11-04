/* fmt_lz4_priv.h — what fmt_lz4.c and its probe share.
 *
 * Source: reference/notes/lz4_Frame_format.md (*General Structure*, *Frame
 * Descriptor*, *Skippable Frames*).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_LZ4_PRIV_H
#define UNC_FMT_LZ4_PRIV_H

#include "unc_internal.h"

/* The magic numbers, little-endian in the file. */
#define LZ4_MAGIC       0x184D2204u
#define LZ4_SKIP_LO     0x184D2A50u   /* ..0x184D2A5F: a skippable frame */

/* FLG: version (7-6) must be 01, bit 1 reserved; BD: bit 7 and 3-0
 * reserved, the block maximum size code in 6-4, 4 to 7. */
#define LZ4_FLG_VERSION 0xC0u
#define LZ4_FLG_V01     0x40u
#define LZ4_FLG_INDEP   0x20u
#define LZ4_FLG_BCSUM   0x10u
#define LZ4_FLG_CSIZE   0x08u
#define LZ4_FLG_CCSUM   0x04u
#define LZ4_FLG_RESV    0x02u
#define LZ4_FLG_DICT    0x01u
#define LZ4_BD_RESV     0x8Fu

#endif

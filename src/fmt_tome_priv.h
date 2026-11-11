/* fmt_tome_priv.h — what fmt_tome.c and its probe share.
 *
 * The layout, and where every field comes from, is in fmt_tome.c's
 * header comment.
 *
 * SPDX-License-Identifier: 0BSD
 */
#ifndef UNC_FMT_TOME_PRIV_H
#define UNC_FMT_TOME_PRIV_H

#include "unc_internal.h"

#define TOME_MAGIC   0x6B630001u   /* "kc" 00 01 */
#define TOME_HDR     0x24u         /* the header, and where the records start */
#define TOME_REC     0x80u         /* one record */

/* A resource fork holding 'part' resources (fmt_tome.c, *Parts*). */
#define TOME_PART    0x70617274u   /* 'part' */
#define TOME_PARTVER 2u            /* the word at 0x10 of a part's Tome */
#define TOME_RMAP    30u           /* a resource map's header and type count */
#define TOME_PTYPES  28u           /* the type entries the probe reads */

#endif

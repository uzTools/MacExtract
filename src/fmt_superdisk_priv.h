/* fmt_superdisk_priv.h — what SuperDisk!'s probe and its decoder both need.
 *
 * The probe stays resident and the decoder can be an overlay, so the record
 * walk they share is declared here and defined once, in the probe file, which
 * that overlay compiles too.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_SUPERDISK_PRIV_H
#define UNC_FMT_SUPERDISK_PRIV_H

#include "unc_internal.h"

#define SD_TAG_END    0x27u
#define SD_TAG_FILE   0x28u
#define SD_TAG_DIR    0x29u
#define SD_TAG_UPDIR  0x2Au
#define SD_BLOCKMAX   0x8000u      /* the largest ulen a block may claim */
#define SD_WINDOW     0x10000u     /* SlowFastB reaches back 49120 bytes */
#define SD_MODULEMAX  64u          /* modules before we call it a loop      */
#define SD_MAXLEN 24

extern const char sd_modsig[];

int sd_records_start(UncIO *io, uint32_t *start, int *has_module);

#endif

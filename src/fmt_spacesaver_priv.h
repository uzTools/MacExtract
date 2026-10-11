/* fmt_spacesaver_priv.h — the header parse shared by the probe and the decoder.
 *
 * It exists because the two are compiled into different places: the PROBE is
 * resident, the DECODER can be an overlay. A probe of ~150 bytes must never
 * live in a blob that the sniffer would then have to load for every file it
 * looks at — that is the whole difference between loading a decoder on demand
 * and loading it always (BRANCH_NOTES.md).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_SPACESAVER_PRIV_H
#define UNC_FMT_SPACESAVER_PRIV_H

#include "unc_internal.h"

#define SS_HDRLEN   84u
#define SS_MAGIC1   0x53495421u        /* 'SIT!' */
#define SS_MAGIC2   0x44464433u        /* 'DFD3' */
typedef struct SsFork {
    uint32_t clen;      /* compressed bytes                            */
    uint32_t ulen;      /* original bytes; 0 = the fork is not there   */
    uint32_t off;       /* where its stream starts, from byte 0        */
    uint8_t  pset;      /* which preset dictionary ('PrAm' index)      */
    uint8_t  method;    /* compressor index; bit 7 = the PowerPC build */
} SsFork;

typedef struct SsHead {
    uint32_t version;
    uint32_t flags;
    SsFork   fork[2];   /* [0] data, [1] resource                      */
    uint32_t type, creator;
    uint16_t finder_flags;
} SsHead;

void ss_parse(const uint8_t *h, SsHead *o);
int  ss_head_ok(const SsHead *o);

#endif

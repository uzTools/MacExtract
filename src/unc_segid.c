/*
 * unc_segid.c — which set a file belongs to, and as which part: the
 * schemes' describe and match, apart from the joiner (unc_segment.c).
 *
 * A file of its own because the Macintosh build carries it in an image
 * rather than resident: the sniffer's, which already holds every parser
 * these call, and Compact Pro's for the one match a set still asks once
 * that image has been given back (mac/ovl_shim.c; DECISIONS.md
 * 2026-11-09, *the set's identity that left*).
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "unc_internal.h"

typedef struct SegId {
    UncFormat scheme;
    /* Describe the set a file belongs to, or UNC_ERR_FORMAT. */
    int (*describe)(UncIO *io, UncSegmentDesc *desc);
    /* Which part of a set this file is, or 0. NULL where the parts
     * carry no identity - which is not the same as "no", and
     * macextract.h says why. */
    int (*match)(const UncSegmentDesc *d, const uint8_t *head, int32_t len);
} SegId;

/* In the order unc_segment_describe tries them, which src/unc_formats.h's
 * UNC_SEGIDS lists and argues. */
#define SEG_ID_ROW(f, describe, match) { f, describe, match },
static const SegId seg_ids[] = {
    UNC_SEGIDS(SEG_ID_ROW)
};

#define SEG_IDS (sizeof seg_ids / sizeof seg_ids[0])

int unc_segment_describe(UncIO *io, UncSegmentDesc *desc)
{
    unsigned i;

    if (!io || !desc) return UNC_ERR_FORMAT;
    for (i = 0; i < SEG_IDS; i++)
        if (seg_ids[i].describe(io, desc) == UNC_OK) return UNC_OK;
    return UNC_ERR_FORMAT;
}

int unc_segment_describe_as(UncIO *io, UncFormat scheme,
                            UncSegmentDesc *desc)
{
    const SegId *s = seg_ids;

    if (!io || !desc) return UNC_ERR_FORMAT;
    for (; s < seg_ids + SEG_IDS; s++)
        if (s->scheme == scheme)
            return s->describe(io, desc) == UNC_OK ? UNC_OK : UNC_ERR_FORMAT;
    return UNC_ERR_FORMAT;
}

int unc_segment_match(const UncSegmentDesc *d,
                      const uint8_t *head, int32_t len)
{
    const SegId *s = seg_ids;

    if (!d || !head) return 0;
    /* A scheme whose parts carry no identity cannot answer this. Said
     * explicitly rather than left to fall out of a failed header parse,
     * because the two outcomes mean opposite things (see macextract.h). */
    for (; s < seg_ids + SEG_IDS; s++)
        if (s->scheme == d->scheme)
            return s->match ? s->match(d, head, len) : 0;
    return 0;
}

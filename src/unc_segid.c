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

/* The ORDER is the order unc_segment_describe tries them in. SPLIT has
 * no row: a part of a plain NAME.001 split is an anonymous slice of
 * bytes, so nothing here can recognise one, and a host that has decided
 * by name builds the descriptor itself. */
static const SegId seg_ids[] = {
    /* StuffIt first: it decides on 100 bytes at offset 0, where the zip
     * scheme has to hunt backwards from the end of the file. */
    { UNC_FORMAT_SITSEG,  unc_sitseg_describe,  unc_sitseg_match },
    /* Apple Backup ahead of Compact Pro, whose describe would take one of
     * its disks: a version byte of 1 at 0 and a non-zero longword at 4
     * are all a Compact Pro segment has to show. 'CMWL' at +2 is what an
     * Apple Backup disk has, and every disk states the count. */
    { UNC_FORMAT_ABK,     unc_abk_describe,     unc_abk_match },
    /* Compact Pro next: like StuffIt it decides on a header at offset 0.
     * Unlike StuffIt, a part that is not the LAST one answers with
     * nparts == 0 - it knows the set it belongs to but not how big the
     * set is, and the host is expected to go and find the final segment. */
    { UNC_FORMAT_CPTSEG,  unc_cptseg_describe,  unc_cptseg_match },
    /* DiskDoubler's `SPLT`, also decided at offset 0 - and on a second
     * copy of its magic at offset 90, so it is the cheapest to refuse. */
    { UNC_FORMAT_DDSEG,   unc_ddseg_describe,   unc_ddseg_match },
    { UNC_FORMAT_ZIPSEG,  unc_zipseg_describe,  NULL },
    /* message/partial, whose describe() reads a mail header block and
     * is therefore the dearest of them: it goes after every scheme that
     * decides on a magic at offset 0. */
    { UNC_FORMAT_MIMESEG, unc_mimeseg_describe, NULL }
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

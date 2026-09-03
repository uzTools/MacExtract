/*
 * unc_encinfo.c — does this archive contain an encrypted entry?
 *
 * Answered by the READERS, before anything is decoded: each of them knows,
 * and since 2026-09-03 each sets `UncEntryInfo.encrypted` (macextract.h).
 * This runs a LIST pass — extraction minus the writes, which is what
 * `list_only` has always been — and reports whether any entry said yes.
 *
 * It used to walk Compact Pro's index and zip's central directory here, by
 * hand, from offsets copied out of those readers. That worked and was wrong
 * in kind: a second copy of a format's layout is what rule #1 forbids, and it
 * could only ever answer for the two formats somebody had written out. This
 * answers for all five that can know — StuffIt, StuffIt 5, Compact Pro, zip,
 * PackIt — and needs nothing when a sixth arrives.
 *
 * ARC still cannot say. It has no flag; XADMaster says so in as many words.
 * A format that cannot say answers UNKNOWN, and a caller must treat UNKNOWN
 * as YES: on `overlay-eager` the answer decides whether the cipher overlay is
 * kept, and there is no reload.
 *
 * The cost is one walk of the archive's headers before extraction. That is an
 * archive read, not an application-disk read, which is the distinction that
 * branch cares about.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

typedef struct {
    int any;
} EncScan;

static int enc_begin(void *ctx, const UncEntryInfo *e)
{
    if (e->encrypted) ((EncScan *)ctx)->any = 1;
    return 1;                     /* skip the data: this is a header walk */
}

static int enc_write(void *ctx, UncFork fork, const void *b, int32_t n)
{
    (void)ctx; (void)fork; (void)b; (void)n;
    return 0;
}

static int enc_end(void *ctx, int status)
{
    (void)ctx; (void)status;
    return 0;
}

/* Which formats can answer at all. A format not listed here returns UNKNOWN
 * whatever the walk finds, because a walk that reports "no encrypted entry"
 * from a reader that never sets the flag is not evidence. */
static int enc_can_answer(UncFormat fmt)
{
    switch (fmt) {
    case UNC_FORMAT_SIT:  case UNC_FORMAT_SIT5:
    case UNC_FORMAT_COMPACTPRO: case UNC_FORMAT_ZIP:
    case UNC_FORMAT_PACKIT:
        return 1;
    default:
        return 0;
    }
}

int unc_archive_encrypted(UncFormat fmt, UncIO *io, UncAlloc *al)
{
    EncScan scan;
    UncSink sk;
    UncOptions opt;
    int ret;
    uint32_t i;

    if (io == NULL || al == NULL || !enc_can_answer(fmt))
        return UNC_ENC_UNKNOWN;

    scan.any = 0;
    for (i = 0; i < sizeof opt; i++) ((char *)&opt)[i] = 0;
    opt.list_only = 1;
    sk.ctx = &scan;
    sk.begin_entry = enc_begin;
    sk.write = enc_write;
    sk.end_entry = enc_end;
    sk.comment = NULL;

    if (io->seek(io->ctx, 0) < 0) return UNC_ENC_UNKNOWN;
    ret = unc_extract_as(fmt, io, &sk, al, NULL, &opt);
    if (io->seek(io->ctx, 0) < 0) return UNC_ENC_UNKNOWN;

    /* A walk that did not finish has not seen every entry, and a part of a
     * multi-part set is exactly that: the directory of a set lives in its
     * LAST part, so the first part — the one a user opens — cannot answer.
     * UNC_ERR_SEGMENTED arrives here rather than being guarded for. */
    if (ret != UNC_OK) return UNC_ENC_UNKNOWN;
    return scan.any ? UNC_ENC_YES : UNC_ENC_NO;
}

/*
 * unc_sniff.c — format sniffing: the probe order, and the walk over it.
 *
 * Split from unc_engine.c on 2026-10-21 so that the Macintosh application
 * can carry it, with every probe, in an 'OVLY' image of its own, run from
 * the bundle before the release and given back with it (DECISIONS.md
 * 2026-10-21, *the probes that left with the bundle*). Nothing here
 * changed in the move; the resident control build links it as before.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "unc_internal.h"

/* ------------------------------------------------------------------ */
/* Sniffing                                                           */
/*                                                                    */
/* Content only, never extensions. We read the first UNC_SNIFF_HEAD   */
/* bytes and hand them to cheap per-format probes, in the order       */
/* src/unc_formats.h's UNC_PROBES lists and argues them.              */
/* ------------------------------------------------------------------ */

#define UNC_SNIFF_HEAD 512

#define UNC_PROBE_ALL(fn, answers) fn,
static const UncProbe unc_sniff_order[] = {
    UNC_PROBES(UNC_PROBE_ALL)
};

/* The probes that can answer an envelope format (unc_format_is_envelope),
 * in the same order; every other probe answers only formats that are
 * not. */
#define UNC_PROBE_ENVELOPE_ENVELOPE(fn) fn,
#define UNC_PROBE_ENVELOPE_ARCHIVE(fn)
#define UNC_PROBE_ENV(fn, answers) UNC_PROBE_ENVELOPE_##answers(fn)
static const UncProbe unc_sniff_envelope_order[] = {
    UNC_PROBES(UNC_PROBE_ENV)
};

static UncFormat sniff_with(UncIO *io, const UncProbe *order, unsigned n)
{
    uint8_t head[UNC_SNIFF_HEAD];
    int32_t len = 0;
    unsigned i;

    if (io->seek(io->ctx, 0) < 0) return UNC_FORMAT_UNKNOWN;
    /* Tolerate short files: read as much as available. */
    while (len < UNC_SNIFF_HEAD) {
        int32_t r = io->read(io->ctx, head + len, UNC_SNIFF_HEAD - len);
        if (r <= 0) break;
        len += r;
    }
    if (len <= 0) return UNC_FORMAT_UNKNOWN;

    for (i = 0; i < n; i++) {
        UncFormat f = order[i](head, len, io);
        if (f != UNC_FORMAT_UNKNOWN) return f;
    }
    return UNC_FORMAT_UNKNOWN;
}

UncFormat unc_sniff(UncIO *io)
{
    return sniff_with(io, unc_sniff_order,
                      sizeof unc_sniff_order / sizeof unc_sniff_order[0]);
}

UncFormat unc_sniff_envelope(UncIO *io)
{
    return sniff_with(io, unc_sniff_envelope_order,
                      sizeof unc_sniff_envelope_order /
                      sizeof unc_sniff_envelope_order[0]);
}

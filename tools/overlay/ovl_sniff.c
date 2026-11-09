/* ovl_sniff.c — the entry of the sniffer's image: unc_sniff and the
 * twenty-six probes it walks, compiled unmodified, and the one lookup a
 * StuffIt set's part 1 needs (fmt_sitseg_end.c), the encryption check
 * and the envelope peek the release asks before it gives the bundle back
 * (unc_encinfo.c, unc_peek.c), and which set a file belongs to
 * (unc_segid.c), whose parsers are the probes'. The EAGER lifetime runs
 * it from the bundle before the release and gives it back with the rest;
 * the LAZY one reads it once and keeps it like any other image
 * (DECISIONS.md 2026-10-21, *the probes that left with the bundle*).
 *
 * Its forwards file leaves out unc_macbinary_probe, which this image
 * defines itself (tools/overlay/mkforwards.py, SNIFF).
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "overlay.h"
#include "ovl_host_gen.h"

const OverlayHostFns *g_ovl_fns = (const OverlayHostFns *)-1;

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b);
int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    g_ovl_fns = (const OverlayHostFns *)host->fns;
    switch (which) {
    case OVL_SELFTEST:
        return 0x4F4B;
    case OVL_SNIFF:
        return (int32_t)unc_sniff((UncIO *)a);
    case OVL_SNIFF_ENVELOPE:
        return (int32_t)unc_sniff_envelope((UncIO *)a);
    case OVL_ARCHIVE_ENCRYPTED:
        return (int32_t)unc_archive_encrypted((UncFormat)(long)b, (UncIO *)a);
    case OVL_ENVELOPE_PEEK: {
        int enc;
        UncFormat f = unc_envelope_peek((UncIO *)a, (UncAlloc *)b, &enc);
        return (int32_t)(((enc + 1) << 8) | (int)f);
    }
    case OVL_SEG_FIRST_END: {
        const OvlArgs *g = (const OvlArgs *)a;
        return (int32_t)unc_segment_first_end(
            (const UncSegmentDesc *)g->obj, (UncIO *)g->in, g->len);
    }
    case OVL_SEG_DESCRIBE: {
        const OvlArgs *g = (const OvlArgs *)a;
        UncIO *io = (UncIO *)g->in;
        UncSegmentDesc *d = (UncSegmentDesc *)g->obj;
        return (int32_t)(g->len == OVL_SEG_EVERY
                         ? unc_segment_describe(io, d)
                         : unc_segment_describe_as(io, (UncFormat)g->len, d));
    }
    case OVL_SEG_MATCH: {
        const OvlArgs *g = (const OvlArgs *)a;
        return (int32_t)unc_segment_match((const UncSegmentDesc *)g->obj,
                                          (const uint8_t *)g->in,
                                          (int32_t)g->len);
    }
    default:
        return -1;
    }
}

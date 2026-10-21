/* fmt_cptseg_probe.c — the probe for one segment of a Compact Pro set.
 *
 * Every probe is in its reader's `_probe.c` (DECISIONS.md 2026-10-20, *one
 * place for every probe*), and the Macintosh application carries them all,
 * with the sniffer, in one `'OVLY'` image run before the release and given
 * back with it (DECISIONS.md 2026-10-21, *the probes that left with the
 * bundle*). What a probe and its reader share is defined once, here, and
 * stays resident for the reader.
 *
 * The scheme's layout, and why it is DERIVED rather than transcribed, is
 * fmt_cptseg.c's file comment.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_cptseg_priv.h"

/* A segment, told apart from an ordinary archive by two facts that
 * cannot both be true of one: an ordinary archive is volume 1 AND
 * carries an index. Volume 2+ is a segment whatever else it says, and
 * volume 1 with no index is the first segment of a set.
 *
 * Deliberately weaker than the other probes in this engine, and the
 * reason is in the format: a middle segment is a chunk of compressed
 * data with an 8-byte hat, and there is nothing else in it to check.
 * The FINAL segment is checked properly — unc_cpt_probe walks its index
 * CRC — so a set is only ever adjudicated by the part that can be.
 *
 * That bargain was paid once — `Read First.PKG`, a real AppleLink
 * package, is byte 0 = 1 with a zero longword at 4 and sniffed as a
 * first segment — so a segment with NO index must now also carry a
 * non-zero set identity. That field's whole job is to tell one set's
 * parts from another's, and 0 identifies nothing. Measured: of the 82
 * raw Compact Pro files reachable on this machine, carrying 75 distinct
 * identities, none is 0; `tools/synth_cptsplit.py` already refused to
 * draw one (`return h or 1`). The FINAL segment is unaffected — it is
 * adjudicated by unc_cpt_probe's walk, which is strictly stronger
 * (OPEN_ITEMS.md, *AppleLink `.pkg`*). */
UncFormat unc_cptseg_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t idx;

    if (len < CPTS_HDR || head[0] != 1) return UNC_FORMAT_UNKNOWN;
    idx = unc_get_u32be(head + 4);
    if (head[1] == 0) return UNC_FORMAT_UNKNOWN;                  /* there is no volume 0 */
    /* No index to check, so the identity has to be one (above). */
    if (idx == 0 && unc_get_u16be(head + 2) == 0) return UNC_FORMAT_UNKNOWN;
    if (head[1] == 1) return (idx == 0)
           ? UNC_FORMAT_CPTSEG : UNC_FORMAT_UNKNOWN;           /* first of a set       */
    /* Volume 2+: a segment. If it carries an index it is the final one,
     * and then it must survive the same walk an archive does — that is
     * the one check available here, and it is worth making, because a
     * final segment is also the file this scheme is opened by. */
    if (idx == 0) return UNC_FORMAT_CPTSEG;
    return (unc_cpt_probe(head, len, io))
           ? UNC_FORMAT_CPTSEG : UNC_FORMAT_UNKNOWN;
}

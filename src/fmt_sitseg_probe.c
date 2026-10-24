/* fmt_sitseg_probe.c — the probe for one part of a StuffIt segmented set,
 * and the header parse it shares with the reader (sitseg_parse).
 *
 * Every probe is in its reader's `_probe.c` (DECISIONS.md 2026-10-20, *one
 * place for every probe*), and the Macintosh application carries them all,
 * with the sniffer, in one `'OVLY'` image run before the release and given
 * back with it (DECISIONS.md 2026-10-21, *the probes that left with the
 * bundle*). What a probe and its reader share is defined once, here, and
 * stays resident for the reader.
 *
 * Source: reference/XADMaster/XADStuffItSplitParser.m — every offset
 * below; fmt_sitseg.c's file comment states the layout, and what it
 * costs that nothing else describes it. NOT its first two bytes, which
 * it requires to be B0 56 and which StuffIt writes as a per-set value
 * (measured 2026-10-24; below, and fmt_sitseg.c).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_sitseg_priv.h"

/* Header field offsets. */
#define SS_PART      3
#define SS_NAMELEN   4
#define SS_NAME      5
#define SS_FP       68          /* start of the 26 fingerprint bytes */
#define SS_TYPE     68
#define SS_CREATOR  72
#define SS_FFLAGS   76
#define SS_CTIME    78
#define SS_MTIME    82
#define SS_RSRCLEN  86
#define SS_DATALEN  90
#define SS_CRC      94          /* CRC-16/ARC of bytes 0..93, big-endian */

/* Parse and validate a header. Returns UNC_OK or UNC_ERR_FORMAT.
 * `desc` may be NULL to validate only. */
int sitseg_parse(const uint8_t *h, int32_t len, UncSegmentDesc *desc)
{
    int32_t i;
    uint32_t nl, rsrc, data;

    if (len < UNC_SEG_HEAD) return UNC_ERR_FORMAT;
    /* Bytes 0 and 1 are NOT tested. XADMaster requires B0 56, and so did
     * this until 2026-10-24, when the first sets StuffIt itself cut were
     * read here: 41 A7 from StuffIt Lite 3.0.5 and InstallerMaker 2.0,
     * 35 63 and 52 0C from Deluxe 5.0, 93 E1 from DropSegment 5.0 — the
     * same in every part of a set, and given by no CRC-16 or sum of the
     * file or the header that was tried. Measured in Deluxe 2.0.1's own
     * code the same day: QuickDraw's _Random, drawn once per set and
     * never seeded, so a launch's first set is 16,807 = 41 A7
     * (fmt_sitseg.c; DECISIONS.md 2026-10-24, *the two bytes the writer
     * drew*).
     * Every B0 56 part on this machine was written by
     * tools/synth_sitsplit.py (BLOCKERS.md, *Withdrawn claims*). What
     * stands in for them is measured on the 42 real parts of eight sets
     * and in Deluxe 2.0.1's code: byte 2 is zero (the part number is a
     * 16-bit word at 2), and 94-95 are a CRC-16/ARC of bytes 0..93
     * (96-99 are the two running CRCs fmt_sitseg.c describes; 96-97
     * are tested below, where the fork length is known). The header CRC
     * is required since the evening of
     * 2026-10-24, and is the 1-in-65,536 the two magic bytes were
     * (DECISIONS.md 2026-10-24, *the check the header carries*). */
    if (h[2] != 0x00) return UNC_ERR_FORMAT;
    if (h[SS_PART] == 0) return UNC_ERR_FORMAT;
    if (unc_get_u16be(h + SS_CRC) != unc_crc16_arc(0, h, SS_CRC))
        return UNC_ERR_FORMAT;
    nl = h[SS_NAMELEN];
    if (nl == 0 || nl > 63) return UNC_ERR_FORMAT;
    for (i = 0; i < (int32_t)nl; i++)
        if (h[SS_NAME + i] == 0) return UNC_ERR_FORMAT;

    /* HFS caps a fork at 2 GB and the engine is 32-bit throughout; a sum
     * that wraps would make `total` describe less than the forks it is
     * the total of. Tested always, not only when describing: without the
     * two magic bytes it is part of what the probe stands on. */
    rsrc = unc_get_u32be(h + SS_RSRCLEN);
    data = unc_get_u32be(h + SS_DATALEN);
    if (rsrc > UNC_MAC_MAX || data > UNC_MAC_MAX) return UNC_ERR_FORMAT;
    if (rsrc == 0 && data == 0) return UNC_ERR_FORMAT;
    /* Bytes 96-97 are the resource fork's running CRC, so a file with no
     * resource fork stores 0 there - the sum of nothing. Required only
     * then: it was required always until the evening of 2026-10-24, on
     * 42 parts that all happened to be cut from files with no resource
     * fork, and refused every part of a file with one (DECISIONS.md
     * 2026-10-24, *the two bytes the writer drew*). */
    if (rsrc == 0 && (h[96] != 0x00 || h[97] != 0x00)) return UNC_ERR_FORMAT;

    if (desc) {
        desc->scheme   = UNC_FORMAT_SITSEG;
        desc->part     = h[SS_PART];
        desc->head_len = UNC_SEG_HEAD;
        desc->name_len = (uint16_t)nl;
        for (i = 0; i < (int32_t)nl; i++) desc->name[i] = h[SS_NAME + i];
        desc->name[nl] = 0;
        for (i = 0; i < UNC_SEG_FP_LEN; i++) desc->fp[i] = h[SS_FP + i];

        desc->rsrc_size    = rsrc;
        desc->data_size    = data;
        desc->total        = rsrc + data;
        desc->type         = unc_get_u32be(h + SS_TYPE);
        desc->creator      = unc_get_u32be(h + SS_CREATOR);
        desc->finder_flags = unc_get_u16be(h + SS_FFLAGS);
        desc->create_date  = unc_get_u32be(h + SS_CTIME);
        desc->mod_date     = unc_get_u32be(h + SS_MTIME);
    }
    return UNC_OK;
}

/* And where the length is known, the part's payload fits in the file it
 * is a piece of: nothing a real part can fail, and arithmetic a header
 * read off something else rarely survives. */
UncFormat unc_sitseg_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t size;

    if (sitseg_parse(head, len, NULL) != UNC_OK) return UNC_FORMAT_UNKNOWN;
    size = io ? unc_io_size32(io) : UNC_SIZE_UNKNOWN;
    if (size != UNC_SIZE_UNKNOWN && size >= UNC_SEG_HEAD &&
        size - UNC_SEG_HEAD > unc_get_u32be(head + SS_RSRCLEN)
                              + unc_get_u32be(head + SS_DATALEN))
        return UNC_FORMAT_UNKNOWN;
    return UNC_FORMAT_SITSEG;
}

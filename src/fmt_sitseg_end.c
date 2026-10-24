/* fmt_sitseg_end.c — where part 1 of a StuffIt segmented set ends, when
 * that file's resource fork says so.
 *
 * A file of its own for the Macintosh application's sake: there it is
 * compiled into the sniffer's image and not into the resident engine,
 * because nothing calls it until a host opens part 1 of a set, and a
 * StuffIt set keeps the bundle whole while it joins (mac/ovl_shim.c).
 * Everywhere else it is linked like the rest.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* Where part 1's segment ends in its own file: `datalen`, unless the
 * file's resource fork, `rsrc` (NULL for none), holds an 'endD' 0 of
 * four bytes that says it ends sooner.
 *
 * Measured 2026-10-24 on Now Utilities 6.0's Disk 1 (1996), a fat
 * installer, the one set on this machine that needs it: 'endD' 0 is
 * 1,132,983, the offset in the data fork where the PowerPC fragment
 * its 'cfrg' 0 names ("Install SEA Join PPC", at 1,132,984) begins,
 * less one byte; the CRC-16/ARC its header stores at 98 is that of the
 * payload ending there, and the payload total less Disk 2's agrees.
 * The four letters sit in CODE 2 of that extractor and of
 * InstallerMaker 2.0's, whose part 1 has no 'endD' and needs none (its
 * data fork ends where its segment does). Nothing published describes
 * the resource; what it means is that one file's measurement.
 *
 * The resource fork is walked with small reads rather than taken in
 * whole: an extractor's is 100 KB and more, and four bytes of it are
 * wanted. Layout: Inside Macintosh: More Macintosh Toolbox, "Resource
 * File Format", as unc_resfork_find reads it (unc_crypt.c). */
uint32_t unc_segment_first_end(const UncSegmentDesc *desc, UncIO *rsrc,
                               uint32_t datalen)
{
    uint8_t b[8];
    uint32_t dataoff, mapoff, tl, ntypes, i;

    if (!desc || !rsrc || desc->scheme != UNC_FORMAT_SITSEG) return datalen;
    if (unc_read_at(rsrc, 0, b, 8) != UNC_OK) return datalen;
    dataoff = unc_get_u32be(b);
    mapoff  = unc_get_u32be(b + 4);
    /* Both bounded so that no sum below can wrap 32 bits. */
    if (dataoff > UNC_MAC_MAX || mapoff > UNC_MAC_MAX) return datalen;
    if (unc_read_at(rsrc, mapoff + 24, b, 2) != UNC_OK) return datalen;
    tl = mapoff + unc_get_u16be(b);
    if (unc_read_at(rsrc, tl, b, 2) != UNC_OK) return datalen;
    ntypes = (uint32_t)unc_get_u16be(b) + 1u;
    for (i = 0; i < ntypes; i++) {
        uint32_t re, end;
        if (unc_read_at(rsrc, tl + 2u + 8u * i, b, 8) != UNC_OK) break;
        if (unc_get_u32be(b) != 0x656E6444u /* 'endD' */) continue;
        /* The first reference: 'endD' has one, ID 0. */
        re = tl + unc_get_u16be(b + 6);
        if (unc_read_at(rsrc, re, b, 8) != UNC_OK) break;
        if (unc_get_u16be(b) != 0) break;
        if (unc_read_at(rsrc, dataoff + (unc_get_u32be(b + 4) & 0x00FFFFFFu),
                        b, 8) != UNC_OK) break;
        end = unc_get_u32be(b + 4);
        if (unc_get_u32be(b) == 4 && end > UNC_SEG_HEAD && end < datalen)
            return end;
        break;
    }
    return datalen;
}

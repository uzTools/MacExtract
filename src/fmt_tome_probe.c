/* fmt_tome_probe.c — the Apple Installer Tome's probe, in the sniffer's
 * image.
 *
 * The magic and the record count are the specification's (fmt_tome.c).
 * The specification leaves the rest of the header unread; the long
 * tested beside them is MEASURED, constant over every Tome this machine
 * holds — 39 files off the System 7.5.5 and Mac OS 8.6 install media and
 * the 13 one-file Tomes QuickDraw GX keeps in 'part' resources: the
 * long at 0x16 is 0x24, where the records begin (DECISIONS.md
 * 2026-11-10, *the archive the Installer reads*). A four-byte magic alone
 * is weak; with it the test is eight bytes, a count that is not zero, and
 * a table that fits the file.
 *
 * A file that is a RESOURCE FORK holding 'part' resources is a Tome too
 * (fmt_tome.c, *Parts*): its 16-byte header's map lies inside the file,
 * and the first resource of type 'part' among the map's first
 * TOME_PTYPES types opens with the magic and version 2. The header's
 * layout is Inside Macintosh's (src/unc_crypt.c transcribes it); that
 * every 'part' seen has been among the first 28 types is MEASURED, over
 * the six files of them here (at most ten types; DECISIONS.md
 * 2026-11-11, *the parts the Installer expands*).
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_tome_priv.h"

/* The resource fork's case: a map that fits, a 'part' in its type list,
 * and that part's first bytes. */
static UncFormat tome_parts_probe(const uint8_t *head, UncIO *io,
                                  unc_off_t size)
{
    uint8_t m[TOME_RMAP + 8 * TOME_PTYPES];
    uint32_t doff = unc_get_u32be(head), moff = unc_get_u32be(head + 4);
    uint32_t mlen = unc_get_u32be(head + 12), tl, nt, i, want;

    if (size == UNC_OFF_UNKNOWN || doff < 16 || mlen < TOME_RMAP ||
        moff > (uint32_t)size || mlen > (uint32_t)size - moff)
        return UNC_FORMAT_UNKNOWN;
    want = mlen < sizeof m ? mlen : (uint32_t)sizeof m;
    if (unc_read_at(io, moff, m, (int32_t)want) != UNC_OK)
        return UNC_FORMAT_UNKNOWN;
    tl = unc_get_u16be(m + 24);
    if (tl + 2u > want) return UNC_FORMAT_UNKNOWN;
    nt = (unc_get_u16be(m + tl) + 1u) & 0xFFFFu;
    for (i = 0; i < nt && tl + 10u + 8u * i <= want; i++) {
        const uint8_t *te = m + tl + 2 + 8 * i;
        uint8_t ref[12];
        uint8_t p[0x12];
        if (unc_get_u32be(te) != TOME_PART) continue;
        if (unc_read_at(io, (unc_off_t)moff + tl + unc_get_u16be(te + 6),
                        ref, 12) != UNC_OK ||
            unc_read_at(io, (unc_off_t)doff + 4u +
                            ((uint32_t)ref[5] << 16 | unc_get_u16be(ref + 6)),
                        p, 0x12) != UNC_OK)
            return UNC_FORMAT_UNKNOWN;
        return unc_get_u32be(p) == TOME_MAGIC &&
               unc_get_u16be(p + 0x10) == TOME_PARTVER
               ? UNC_FORMAT_TOME : UNC_FORMAT_UNKNOWN;
    }
    return UNC_FORMAT_UNKNOWN;
}

UncFormat unc_tome_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t n;
    unc_off_t size;
    if (len >= 16 && unc_get_u32be(head) != TOME_MAGIC) {
        size = io->size(io->ctx);
        return tome_parts_probe(head, io, size);
    }
    if (len < (int32_t)TOME_HDR || unc_get_u32be(head) != TOME_MAGIC ||
        unc_get_u32be(head + 0x16) != TOME_HDR)
        return UNC_FORMAT_UNKNOWN;
    n = unc_get_u16be(head + 0x1a);
    if (n == 0)
        return UNC_FORMAT_UNKNOWN;
    size = io->size(io->ctx);
    if (size != UNC_OFF_UNKNOWN && TOME_HDR + n * TOME_REC > size)
        return UNC_FORMAT_UNKNOWN;
    return UNC_FORMAT_TOME;
}

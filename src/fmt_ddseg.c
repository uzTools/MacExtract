/*
 * fmt_ddseg.c — one part of a DiskDoubler "Split" set (`SPLT`).
 *
 * DERIVED from specimens, not transcribed: no reference implements
 * this container. `unar` 1.10.8 reads neither a part nor the parts
 * concatenated by hand, and no published description of the layout
 * exists. What is below was read off the four parts in
 * `ssokolow/diskdoubler-test-files` (CC0) and confirmed by
 * reassembling both sets byte for byte, forks included —
 * DECISIONS.md 2026-08-21; `tools/run_segments.py` re-runs it,
 * against those same parts registered as fixtures.
 *
 * DiskDoubler's Split command cuts ANY file into numbered pieces; it
 * is not a DiskDoubler archive format, which is why the type and
 * creator of the original are in every header rather than assumed.
 * The specimens hold `DDAR` and `DDA2` archives because that is what
 * was split, and the joined file goes back to whatever reads it.
 *
 *   Every part begins with a 94-byte header:
 *      0  'SPLT'
 *      4  the Mac's TickCount when the file was split (1/60 s since
 *         the machine booted) — written once per SET, which is why it
 *         is equal across the parts and different between sets.
 *         MEASURED 2026-08-21: three splits 72 s apart under emulation
 *         differ by 4,324 and 4,330, i.e. 60.06 and 60.14 per second
 *      8  data fork length of the original file (4)
 *     12  resource fork length (4)
 *     16  type (4)      20  creator (4)      24  Finder flags (2)
 *     32  modification date (4)              36  creation date (4)
 *     40  part count (2)                     42  index, 0-based (2)
 *     44  this part's payload length (4)
 *     48  CRC-16/XMODEM of this part's payload (2)
 *     90  'SPLT' again
 *
 *   The payload follows. Concatenating the payloads of parts 1..N in
 *   index order yields the original file: its DATA fork, then its
 *   resource fork — the opposite order to StuffIt's split, and the
 *   reason unc_sitseg_emit takes the order as an argument.
 *
 * Three things a part proves that a StuffIt part does not, and one it
 * does not prove:
 *   - the set's SIZE is stored (part count at 40), as well as the
 *     payload total, so a missing tail is detectable;
 *   - the part's own payload LENGTH is stored, so the joiner does not
 *     have to take the file's size as the payload's (unc_segment.c);
 *   - each payload carries a CRC. The joiner checks it whenever a
 *     part is read straight through — it accumulates one as the bytes
 *     go past and compares at the part boundary — and skips the check
 *     on a part something seeked backwards inside, because re-reading
 *     the part to finish the sum would cost a disk swap on the
 *     one-drive Mac this scheme exists for (DECISIONS.md 2026-08-21).
 *   - there is NO name: the original file's name is the host's, from
 *     the part's own filename, exactly as for a plain .NNN split.
 *
 * The dates are assigned modification-then-creation, which is the
 * order DiskDoubler's file header uses (fmt_dd.c, dd_parse_filehdr)
 * and the only assignment under which the one specimen pair that
 * differs reads as a file modified AFTER it was created.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_ddseg_priv.h"

uint16_t unc_ddseg_stored_crc(const uint8_t *head)
{
    return unc_get_u16be(head + DS_CRC);
}

int unc_ddseg_describe(UncIO *io, UncSegmentDesc *desc)
{
    uint8_t head[UNC_DDSEG_HEAD];
    int err;

    if (!io || !desc) return UNC_ERR_FORMAT;
    err = unc_read_at(io, 0, head, UNC_DDSEG_HEAD);
    if (err != UNC_OK) return UNC_ERR_FORMAT;   /* too short to be one */
    return ddseg_parse(head, UNC_DDSEG_HEAD, desc, NULL);
}

/* Does this header belong to `desc`'s set, and as which part?
 * The identity is the 26 bytes every part of a set shares — which
 * includes both fork lengths, the type, the creator and the dates, so
 * two files split on the same afternoon do not collide on it. */
int unc_ddseg_match(const UncSegmentDesc *desc, const uint8_t *head,
                    int32_t len)
{
    UncSegmentDesc cand;
    int32_t i;

    if (ddseg_parse(head, len, &cand, NULL) != UNC_OK) return 0;
    if (cand.nparts != desc->nparts) return 0;
    for (i = 0; i < UNC_SEG_FP_LEN; i++)
        if (cand.fp[i] != desc->fp[i]) return 0;
    return (int)cand.part;
}

/* What the joiner takes from a part it has just opened: the payload
 * length the part declares, checked against the file it arrived in and
 * against the set it claims to belong to. `size` is the whole part.
 *
 * This is why a `SPLT` part with anything appended to it still joins,
 * where every other scheme here would fold the trailing bytes into the
 * stream — the length is in the header, not in the directory. */
int unc_ddseg_payload(const UncSegmentDesc *desc, const uint8_t *head,
                      int32_t len, int part, uint32_t size, uint32_t *payload)
{
    UncSegmentDesc cand;
    uint32_t paylen;

    if (ddseg_parse(head, len, &cand, &paylen) != UNC_OK) return UNC_ERR_CORRUPT;
    if (unc_ddseg_match(desc, head, len) != part) return UNC_ERR_CORRUPT;
    if (size < UNC_DDSEG_HEAD || size - UNC_DDSEG_HEAD < paylen)
        return UNC_ERR_TRUNCATED;
    *payload = paylen;
    return UNC_OK;
}

/* A part read on its own, with no volume source behind it: that is a
 * whole file exactly when the set has one part. Otherwise the caller
 * is told what it has — the one case in the engine that returns
 * UNC_ERR_SEGMENTED. */
int unc_ddseg_extract(UncCtx *c)
{
    UncSegmentDesc desc;
    uint32_t size;
    int err;

    err = unc_ddseg_describe(c->io, &desc);
    if (err != UNC_OK) return err;
    if (desc.nparts != 1 || desc.part != 1) return UNC_ERR_SEGMENTED;

    size = unc_io_size32(c->io);
    if (size == UNC_SIZE_UNKNOWN || size < UNC_DDSEG_HEAD)
        return UNC_ERR_SEGMENTED;
    if (size - UNC_DDSEG_HEAD < desc.total) return UNC_ERR_SEGMENTED;

    /* The name is the host's — there is none in the file. */
    {
        static const uint8_t fallback[] = "split";
        const uint8_t *src = fallback;
        uint16_t n = (uint16_t)(sizeof fallback - 1), i;
        if (c->opt.name_hint && c->opt.name_hint_len) {
            src = c->opt.name_hint;
            n = c->opt.name_hint_len;
            if (n > UNC_NAME_MAX) n = UNC_NAME_MAX;
        }
        for (i = 0; i < n; i++) desc.name[i] = src[i];
        desc.name[n] = 0;
        desc.name_len = n;
    }
    return unc_sitseg_emit(c, &desc, UNC_DDSEG_HEAD, 1, NULL);
}

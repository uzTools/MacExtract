/*
 * fmt_sitseg.c — one part of a StuffIt segmented ("split") set.
 *
 * XADMaster is the SOLE source of this header, and the re-citation
 * that moved BinHex, MacBinary, AppleSingle, zip, tar and gzip onto
 * their own specifications (DECISIONS.md 2026-09-19, *the facts that
 * were somebody else's to state*) found nothing to move this onto:
 * Aladdin published nothing about it, and neither deark nor macutils
 * reads it. So it stays, and so does what that costs.
 *
 * Source: reference/XADMaster/XADStuffItSplitParser.m — the whole
 * layout below.
 * Layout (reference/XADMaster/XADStuffItSplitParser.m,
 * +recognizeFileWithHandle:, +volumesForHandle: and -parse — LGPL,
 * see NOTICE):
 *
 *   Every part begins with a 100-byte header:
 *      0  two bytes, the same in every part of a set and not derived
 *      1  from the file. XADMaster requires B0 56; StuffIt does not write
 *         it (measured 2026-10-24, below), and nothing tests them.
 *      2  0x00        (XADMaster: "assume there are less than 256 parts")
 *      3  part number, 1-based
 *      4  name length of the ORIGINAL file, 1..63, no NUL in the name
 *      5  name bytes
 *     68  type (4)     72  creator (4)     76  Finder flags (2)
 *     78  creation date (4)                78+4 modification date (4)
 *     86  resource fork length (4)         90  data fork length (4)
 *
 *   The payload follows. Concatenating the payloads of parts 1..N in
 *   order yields the original file: its resource fork, then its data
 *   fork. Bytes 5+namelen..67 are whatever was in StuffIt's name
 *   buffer; nothing here reads them.
 *
 * Measured 2026-10-24 on the first sets StuffIt itself cut to be read
 * here — StuffIt Deluxe 2.0.1, StuffIt Lite 3.0.5 (two sets of one
 * file), Deluxe 5.0 (two files), DropSegment 5.0 and InstallerMaker 2.0,
 * written on emulated Macs
 * by MacStamp's session — and on Now Utilities 6.0's two installer disks
 * (1996):
 *     0-1  41 A7 (Lite, both sets, AND InstallerMaker over another file),
 *          35 63 and 52 0C (Deluxe 5.0, two files), 93 E1 (DropSegment),
 *          D3 36 (Now Utilities). No CRC-16 or sum of the file or the
 *          header fits all six. Hypothesis: a random set ID, QuickDraw's
 *          Random — 0x41A7 is 16,807, its first value from the seed
 *          InitGraf sets, and the two 41 A7 sets were each the first
 *          thing done on a freshly booted emulator
 *    94-95 a CRC-16/ARC of this header's bytes 0..93: 42 parts of 42,
 *          seven writers, StuffIt Deluxe 2.0.1 (1991) to 5.0. Required
 *          by sitseg_parse since the evening of 2026-10-24; it stands
 *          where the two magic bytes stood (DECISIONS.md 2026-10-24,
 *          *the check the header carries*)
 *    96-97 zero in every part
 *    98-99 a CRC-16/ARC RUNNING across the set: over the payloads of
 *          parts 1..n, so the last part's is the whole file's. The
 *          joiner checks it as each part's last payload byte goes past
 *          (unc_segment.c, seg_read); unc_sitseg_extract below, a lone
 *          part read with no joiner, does not.
 * tools/synth_sitsplit.py writes both CRCs as StuffIt does, since the
 * evening of 2026-10-24; zero before.
 * And part 1 of a self-extracting set is an application's DATA fork,
 * which in a fat installer goes on past the segment: Now Utilities'
 * Disk 1 carries 56,206 bytes of PowerPC code after it. Its resource
 * fork says where the segment stops (fmt_sitseg_end.c).
 * All of it is in BLOCKERS.md, *Withdrawn claims*, and DECISIONS.md
 * 2026-10-24.
 *
 * A part is matched to its set by name length + name bytes + the 26
 * bytes at offset 68 — XADMaster's memcmp, and the reason the part
 * NUMBER is trustworthy while the FILENAME is not consulted at all.
 *
 * Two properties of the header carry the rest of the design:
 *   - rsrclen + datalen is the exact payload total, so from part 1
 *     alone we know how much is still missing and when the set is
 *     complete. No part count is stored anywhere (XADMaster does not
 *     look for one either: it stops at the first gap).
 *   - a one-part set is just a file with a 100-byte hat: it extracts
 *     with no volume source at all.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_sitseg_priv.h"

int unc_sitseg_describe(UncIO *io, UncSegmentDesc *desc)
{
    uint8_t head[UNC_SEG_HEAD];
    int err;

    if (!io || !desc) return UNC_ERR_FORMAT;
    err = unc_read_at(io, 0, head, UNC_SEG_HEAD);
    if (err != UNC_OK) return UNC_ERR_FORMAT;   /* too short to be one */
    err = sitseg_parse(head, UNC_SEG_HEAD, desc);
    /* The payload total ends the walk; there is no part count stored. */
    if (err == UNC_OK) desc->nparts = 0;
    return err;
}

/* Does this file belong to the set `desc` describes, and as which part?
 * A StuffIt part carries the original's name and a fingerprint; both
 * must agree. 0 = it does not belong, or cannot be told.
 * The dispatch across schemes is unc_segment_match, in unc_segment.c. */
int unc_sitseg_match(const UncSegmentDesc *desc,
                     const uint8_t *head, int32_t len)
{
    UncSegmentDesc cand;
    int32_t i;

    if (sitseg_parse(head, len, &cand) != UNC_OK) return 0;
    if (cand.name_len != desc->name_len) return 0;
    for (i = 0; i < (int32_t)desc->name_len; i++)
        if (cand.name[i] != desc->name[i]) return 0;
    for (i = 0; i < UNC_SEG_FP_LEN; i++)
        if (cand.fp[i] != desc->fp[i]) return 0;
    return (int)cand.part;
}

/* The CRC-16/ARC a part stores at 98, over the payloads of parts 1..its
 * own. The joiner folds the same sum as the parts go past and holds
 * each part to its stored value (unc_segment.c). */
uint16_t unc_sitseg_stored_crc(const uint8_t *head)
{
    return unc_get_u16be(head + 98);
}

/* ------------------------------------------------------------------ */
/* Extraction                                                         */
/*                                                                    */
/* The joined payload is one file: resource fork, then data fork. That */
/* makes this an envelope format in the same shape as MacBinary, and   */
/* the archive usually inside it is the next layer's problem.          */
/* ------------------------------------------------------------------ */

/* Emit the single entry described by `desc`, reading its forks from
 * `base` onwards. `base` is UNC_SEG_HEAD for a lone part read
 * directly, and 0 for the joined stream the joiner presents.
 *
 * Shared with UNC_FORMAT_SPLIT, which is this same shape with nothing
 * in front of it: one entry, one fork, sizes and name supplied rather
 * than parsed (unc_segment.c). */
int unc_sitseg_emit(UncCtx *c, const UncSegmentDesc *desc, uint32_t base,
                    int data_first, const int *ioerr)
{
    UncEntryInfo e;
    int err, sret;

    unc_entry_clear(&e);
    unc_entry_set_name(&e, desc->name, desc->name_len);
    e.type           = desc->type;
    e.creator        = desc->creator;
    e.finder_flags   = desc->finder_flags;
    e.create_date    = desc->create_date;
    e.mod_date       = desc->mod_date;
    e.data_size      = desc->data_size;
    e.rsrc_size      = desc->rsrc_size;
    e.comp_data_size = desc->data_size;
    e.comp_rsrc_size = desc->rsrc_size;

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) return UNC_ERR_SINK;
    if (sret > 0) return UNC_OK;

    err = UNC_OK;
    if (!c->opt.list_only) {
        uint32_t bufsz = UNC_PROGRESS_STEP;
        uint8_t *buf = (uint8_t *)unc_alloc(c->al, bufsz);
        if (!buf) err = UNC_ERR_MEM;
        if (err == UNC_OK) {
            UncFork f1 = data_first ? UNC_FORK_DATA : UNC_FORK_RSRC;
            UncFork f2 = data_first ? UNC_FORK_RSRC : UNC_FORK_DATA;
            uint32_t n1 = data_first ? desc->data_size : desc->rsrc_size;
            uint32_t n2 = data_first ? desc->rsrc_size : desc->data_size;
            if (c->io->seek(c->io->ctx, base) < 0) err = UNC_ERR_IO;
            /* Whichever fork the stream begins with: StuffIt's split
             * puts the resource fork first, DiskDoubler's the data. */
            if (err == UNC_OK)
                err = unc_copy_fork(c, f1, n1, buf, bufsz);
            if (err == UNC_OK)
                err = unc_copy_fork(c, f2, n2, buf, bufsz);
            unc_free(c->al, buf);
        }
    }
    /* A failed read says only that it failed. When the stream is the
     * joiner's, its own verdict is the one the entry should carry: the
     * part whose CRC did not match, not "I/O error". */
    if (err == UNC_ERR_IO && ioerr && *ioerr != UNC_OK) err = *ioerr;

    if (c->sink->end_entry(c->sink->ctx, err) < 0) return UNC_ERR_SINK;
    if (unc_fatal(err))
        return err;
    return UNC_OK;
}

/* Extract a part read on its own, with no volume source behind it.
 * That succeeds exactly when this one file holds the whole payload —
 * a set of one. Otherwise the caller is told what it has, which is
 * the only case in the engine that returns UNC_ERR_SEGMENTED. */
int unc_sitseg_extract(UncCtx *c)
{
    UncSegmentDesc desc;
    uint32_t size;
    int err;

    err = unc_segment_describe(c->io, &desc);
    if (err != UNC_OK) return err;

    size = unc_io_size32(c->io);
    if (size == UNC_SIZE_UNKNOWN || size < UNC_SEG_HEAD) return UNC_ERR_SEGMENTED;
    if (desc.part != 1) return UNC_ERR_SEGMENTED;
    if (size - UNC_SEG_HEAD < desc.total) return UNC_ERR_SEGMENTED;

    return unc_sitseg_emit(c, &desc, UNC_SEG_HEAD, 0, NULL);
}

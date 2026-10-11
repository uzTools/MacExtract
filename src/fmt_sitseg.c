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
 *      0  0xB0
 *      1  0x56
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
 *   fork. Bytes 5+namelen..67 and 94..99 are described by no reference
 *   implementation, and nothing here reads them.
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
#include "unc_internal.h"

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

/* Parse and validate a header. Returns UNC_OK or UNC_ERR_FORMAT.
 * `desc` may be NULL to validate only. */
static int sitseg_parse(const uint8_t *h, int32_t len, UncSegmentDesc *desc)
{
    int32_t i;
    uint32_t nl;

    if (len < UNC_SEG_HEAD) return UNC_ERR_FORMAT;
    if (h[0] != 0xB0 || h[1] != 0x56 || h[2] != 0x00) return UNC_ERR_FORMAT;
    if (h[SS_PART] == 0) return UNC_ERR_FORMAT;
    nl = h[SS_NAMELEN];
    if (nl == 0 || nl > 63) return UNC_ERR_FORMAT;
    for (i = 0; i < (int32_t)nl; i++)
        if (h[SS_NAME + i] == 0) return UNC_ERR_FORMAT;

    if (desc) {
        uint32_t rsrc = unc_get_u32be(h + SS_RSRCLEN);
        uint32_t data = unc_get_u32be(h + SS_DATALEN);

        /* HFS caps a fork at 2 GB and the engine is 32-bit throughout;
         * a sum that wraps would make `total` describe less than the
         * forks it is the total of. */
        if (rsrc > UNC_MAC_MAX || data > UNC_MAC_MAX) return UNC_ERR_FORMAT;

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

UncFormat unc_sitseg_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    return (sitseg_parse(head, len, NULL) == UNC_OK)
           ? UNC_FORMAT_SITSEG : UNC_FORMAT_UNKNOWN;
}

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
                    int data_first)
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

    return unc_sitseg_emit(c, &desc, UNC_SEG_HEAD, 0);
}

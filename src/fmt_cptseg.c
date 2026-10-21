/*
 * fmt_cptseg.c — one segment of a Compact Pro segmented archive.
 *
 * The one scheme here whose layout is DERIVED rather than transcribed.
 * No reference implementation reads it: XADCompactProParser.m reads
 * the archive volume byte into a variable it has commented out,
 * macunpack stores its copy unused, and The Unarchiver's own format
 * wiki calls
 * the three fields involved "meaning not entirely clear"
 * (reference/notes/cpt_specs_theunarchiver.md). What IS documented is
 * what the scheme promises, by the author, in
 * reference/notes/cpt_users_guide.txt:
 *
 *   "a segmented archive may have as many as 255 segments"
 *   "Segment files may be moved from one disk or folder to another and
 *    may be named in any manner you wish. The names of the files are
 *    not important since Compact Pro saves information inside the
 *    files to determine their proper ordering."
 *   "you must open the FINAL segment ... in order to access its
 *    contents."
 *
 * The bytes behind those promises were measured on real segmented sets
 * cut by Compact Pro 1.51 itself under Mini vMac (tools/vmac/cptsegment.py,
 * DECISIONS.md 2026-08-14). Every segment carries the same 8-byte
 * header an ordinary archive has:
 *
 *     0  0x01          signature
 *     1  volume        1-based, consecutive; <= 255 by the manual
 *     2  identity(2)   ONE value shared by every segment of the set,
 *                      drawn per set — distinct in all 68 single-volume
 *                      archives in the corpus. This is the "information
 *                      inside the files", and it is why names may be
 *                      anything.
 *     4  index offset  0 in every segment but the LAST, which carries
 *                      it relative to its own start.
 *
 * An entry is addressed as (volume, offset within that volume's file),
 * counted from that segment's start, header included — so the reader
 * works in ADDRESSED mode like a spanned zip, and unc_cpt_extract does
 * the translation through UncSegMap. The payloads concatenate to the
 * unsegmented archive's data region byte for byte: segmenting re-chunks
 * an archive and rewrites its directory, and recompresses nothing.
 *
 * What would falsify the above, and is therefore refused here: an
 * identity that differs between segments of one set, a non-final
 * segment carrying an index offset, or a final segment claiming to be
 * volume 1.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_cptseg_priv.h"

int unc_cptseg_describe(UncIO *io, UncSegmentDesc *desc)
{
    uint8_t head[CPTS_HDR];
    uint32_t idx;

    if (unc_read_at(io, 0, head, CPTS_HDR) != UNC_OK) return UNC_ERR_FORMAT;
    if (head[0] != 1 || head[1] == 0) return UNC_ERR_FORMAT;
    idx = unc_get_u32be(head + 4);
    if (head[1] == 1 && idx != 0) return UNC_ERR_FORMAT;   /* plain archive */
    /* The same rule the probe applies, so the two walks agree. */
    if (idx == 0 && unc_get_u16be(head + 2) == 0) return UNC_ERR_FORMAT;

    {
        int i;
        /* Nothing else is knowable from a segment header: the format
         * stores no original filename and no fork sizes here, and the
         * index that has them is in the final part. Zeroed, not guessed. */
        desc->name[0]  = 0;
        desc->name_len = 0;
        for (i = 0; i < UNC_SEG_FP_LEN; i++) desc->fp[i] = 0;
        desc->data_size = desc->rsrc_size = 0;
        desc->type = desc->creator = 0;
        desc->finder_flags = 0;
        desc->create_date = desc->mod_date = 0;
    }
    desc->scheme   = UNC_FORMAT_CPTSEG;
    desc->part     = head[1];
    desc->head_len = CPTS_HDR;
    desc->total    = UNC_SIZE_UNKNOWN;    /* addressed: nobody's business */
    /* The set identity, in the fingerprint the host matches candidates
     * against. Two bytes is all the format spends on it. */
    desc->fp[0] = head[2];
    desc->fp[1] = head[3];
    /* Only the FINAL segment says how many there are — by being the
     * last one, which is what carrying the index means. From any other
     * part this is 0, and the host is expected to go and find the final
     * one; it can, because every part identifies itself. */
    desc->nparts = idx ? head[1] : 0;
    return UNC_OK;
}

int unc_cptseg_match(const UncSegmentDesc *desc, const uint8_t *head,
                     int32_t len)
{
    uint32_t idx;

    if (len < CPTS_HDR || head[0] != 1) return 0;
    if (head[1] == 0) return 0;
    if (head[2] != desc->fp[0] || head[3] != desc->fp[1]) return 0;
    idx = unc_get_u32be(head + 4);
    /* Structure as well as identity: within a known set, only the last
     * segment carries an index and every other one must not. A file
     * that shares the two identity bytes by accident — one in 65,536 —
     * has to agree about that too before it is let in. */
    if (desc->nparts) {
        if (head[1] > desc->nparts) return 0;
        if ((head[1] == desc->nparts) != (idx != 0)) return 0;
    } else if (head[1] == 1 && idx != 0) {
        return 0;                          /* an ordinary archive */
    }
    return head[1];
}

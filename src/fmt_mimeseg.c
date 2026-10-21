/*
 * fmt_mimeseg.c — a message split across several FILES: `message/partial`
 * (RFC 2046 section 5.2.2), which is how a file too big for a mail
 * gateway crossed one. The sixth join scheme, and the only one whose
 * parts are text.
 *
 * Sources (transcribed, never guessed):
 *   reference/mpack/decode.c handlePartial() — the three parameters
 *       that matter (`id`, `number`, `total`), the sanity checks it
 *       applies to them (an id is required, a number is 1-based and
 *       may not exceed the total), and the reassembly itself: the
 *       BODIES of the parts, in number order, concatenated.
 *   reference/mpack/encode.c — what `mpack -m` writes, which is what
 *       tools/run_mime.py grades this against.
 *   reference/mpack/decode.c ParseHeaders() — a header line, and a
 *       continuation line that begins with space or tab; the blank
 *       line that ends the header block. The PARAMETER parsing is
 *       shared with src/fmt_mime.c rather than transcribed twice.
 *
 * What is joined is each part's body and nothing else. mpack composes
 * a standalone message out of the enclosing headers as well, because
 * its result is a file somebody may read; here the joined stream is
 * handed straight to the MIME walk, and part 1's body already begins
 * with the enclosed message's own headers. DECISIONS.md 2026-08-29.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_mimeseg_priv.h"

int unc_mimeseg_describe(UncIO *io, UncSegmentDesc *desc)
{
    MsegInfo mi;
    uint32_t i;

    if (mseg_scan(io, &mi) != UNC_OK) return UNC_ERR_FORMAT;
    if (!mseg_ok(&mi)) return UNC_ERR_FORMAT;

    for (i = 0; i < sizeof *desc; i++) ((uint8_t *)desc)[i] = 0;
    desc->scheme = UNC_FORMAT_MIMESEG;
    desc->part = (uint16_t)mi.part;
    desc->nparts = (uint16_t)mi.nparts;
    /* The identity is the `id` parameter, which every part of a set
     * repeats — the first 26 bytes of it, which is what a fingerprint
     * holds. Two sets that agree that far would be read as one; the
     * scheme that has been in this engine longest identifies itself
     * with two bytes. */
    for (i = 0; i < mi.idlen && i < UNC_SEG_FP_LEN; i++) desc->fp[i] = mi.id[i];
    /* A part's own headers are its header, and they are not all the
     * same length — so this is the length of THIS part's, and the
     * joiner asks again for every part it opens (unc_mimeseg_head). */
    desc->head_len = mi.body;
    /* Nothing in the format states how many bytes the message weighs:
     * `total` counts PARTS. The joiner learns the length when it opens
     * the last one. */
    desc->total = UNC_SIZE_UNKNOWN;
    desc->name_len = 0;
    desc->name[0] = 0;
    return UNC_OK;
}

/* This part's own header length, and the check that it is the part the
 * joiner asked for: the number and the id are in every part, so a set
 * assembled out of the wrong files is caught here rather than in the
 * joined stream. */
int unc_mimeseg_head(const UncSegmentDesc *d, UncIO *io, int part,
                     uint32_t size, uint32_t *out)
{
    MsegInfo mi;
    uint32_t i;

    (void)size;
    if (mseg_scan(io, &mi) != UNC_OK) return UNC_ERR_CORRUPT;
    if (!mseg_ok(&mi)) return UNC_ERR_CORRUPT;
    if (mi.part != part) return UNC_ERR_CORRUPT;
    for (i = 0; i < UNC_SEG_FP_LEN; i++)
        if (mi.id[i] != d->fp[i]) return UNC_ERR_CORRUPT;
    *out = mi.body;
    return UNC_OK;
}

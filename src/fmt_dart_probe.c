/* fmt_dart_probe.c — DART's header reader, which is also its probe.
 *
 * Resident on this branch: sniffing a file must not load a decoder in
 * order to decide the file is not one. DART is the sharpest case of that
 * rule in the engine — it has no signature, so the probe reads the whole
 * block-length table and checks it against the file's size, and the
 * decoder needs exactly the same reader. Both get it from here.
 *
 * Sources are named in fmt_dart.c, which is the other half.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_dart_priv.h"

/* ------------------------------------------------------------------ */
/* Header                                                             */
/* ------------------------------------------------------------------ */

/* The type/size pairs a DART may state. There is no signature anywhere
 * in the format, so this table is a third of the identification: the
 * disk identifiers come from DartIntf.h and the sizes each may carry
 * from DART.cs's FormatToKind, which is the only reading that pairs
 * them. `digit` completes the file type DartIntf.h names for that pair.
 *
 * The four pairs FormatToKind accepts and DartIntf.h names no type for
 * — a Lisa 800K, an Apple II 400K, a 720K Macintosh, a 1440K MS-DOS low
 * -density — are not in this table and are not recognized. A DART of a
 * shape Apple's own header has no file type for is a shape DART could
 * not have written, and admitting one would mean inventing the constant
 * it should carry (CLAUDE.md, rule 1). */
static const struct DartKind dart_kinds[] = {
    { 1,   400u, '1' },           /* kMacDisk      'DMd1' Macintosh 400K */
    { 2,   400u, '2' },           /* kLisaDisk     'DMd2' Lisa 400K      */
    { 1,   800u, '3' },           /* kMacDisk      'DMd3' Macintosh 800K */
    { 3,   800u, '4' },           /* kAppleIIDisk  'DMd4' Apple II 800K  */
    { 17,  720u, '5' },           /* kMSDOSLowDD   'DMd5' MS-DOS 720K    */
    { 16, 1440u, '6' },           /* kMacHiDDisk   'DMd6' Macintosh 1.4M */
    { 18, 1440u, '7' }            /* kMSDOSHiDDisk 'DMd7' MS-DOS 1.4M    */
};


const struct DartKind *dart_kind(uint8_t type, uint16_t kb)
{
    unsigned i;
    for (i = 0; i < sizeof dart_kinds / sizeof dart_kinds[0]; i++)
        if (dart_kinds[i].type == type && dart_kinds[i].kb == kb)
            return &dart_kinds[i];
    return NULL;
}

/* How many bytes chunk `i` occupies in the file, or 0 for a length that
 * cannot be one. Source: DART-notes.md, "The meaning of each block
 * length can depend on the compression type used".
 *
 * The cap is the format's own: DART falls back to storing a chunk whole
 * — marking it 0xFFFF — when compressing it does not pay, so compressed
 * data longer than the chunk it expands to is not something DART wrote.
 * That is enforced HERE rather than in the walk so that identification
 * and extraction agree about what a well-formed table is. */
uint32_t dart_chunk_bytes(uint8_t cmp, uint16_t blen)
{
    uint32_t n;

    if (cmp == DART_CMP_NONE || blen == DART_STORED) return DART_CHUNK_BYTES;
    n = (cmp == DART_CMP_RLE) ? (uint32_t)blen * 2u : (uint32_t)blen;
    if (n == 0 || n > DART_CHUNK_BYTES) return 0;
    return n;
}

/* Read and check the header out of `head`. Returns UNC_OK, or
 * UNC_ERR_FORMAT for anything that is not a DART header. */
int dart_parse(const uint8_t *head, int32_t len, DartHead *h)
{
    uint32_t i;

    if (len < 4) return UNC_ERR_FORMAT;
    h->cmp  = head[0];
    h->type = head[1];
    h->kb   = unc_get_u16be(head + 2);
    if (h->cmp > DART_CMP_NONE) return UNC_ERR_FORMAT;
    if (!dart_kind(h->type, h->kb)) return UNC_ERR_FORMAT;

    /* The size decides the table's length and not the other way round.
     * Getting it wrong moves the payload by 64 bytes and yields a
     * volume that reads as noise. DartIntf.h: "you can decide whether
     * to interpret the file header as HDSrcInfoRec or SrcInfoRec". */
    h->slots  = (uint16_t)(h->kb <= 800u ? DART_SLOTS_SMALL : DART_SLOTS_LARGE);
    h->hdrlen = (uint16_t)(4u + 2u * h->slots);
    /* kb/20: a chunk is 20480 bytes, which is 20 KB of the disk. */
    h->blocks = (uint16_t)(h->kb / 20u);
    if (h->blocks == 0 || h->blocks > h->slots) return UNC_ERR_FORMAT;
    if (len < (int32_t)h->hdrlen) return UNC_ERR_FORMAT;

    h->payload = 0;
    h->maxchunk = 0;
    for (i = 0; i < h->slots; i++) {
        uint16_t e = unc_get_u16be(head + 4 + 2 * i);
        h->blen[i] = e;
        /* Entries past the end of the disk are zero, and entries inside
         * it are not: DART-notes.md, and the check DART.cs makes.
         * Neither half is decoration — a table whose unused slots are
         * not zero is something else that got this far. */
        if (i >= h->blocks) {
            if (e != 0) return UNC_ERR_FORMAT;
            continue;
        }
        if (e == 0) return UNC_ERR_FORMAT;
        {
            uint32_t n = dart_chunk_bytes(h->cmp, e);
            if (n == 0) return UNC_ERR_FORMAT;
            h->payload += n;
            if (n > h->maxchunk) h->maxchunk = n;
        }
    }
    return UNC_OK;
}

/* Four bytes and a table of lengths is a weak signature, and the
 * arithmetic is what makes it strong: the chunk sizes the table states
 * have to add up to the rest of the FILE, to the byte. That is the test
 * that settled the format in the first place (a byte-length reading of
 * a real archive came out 300,951 short) and it is what keeps this
 * probe from claiming anything that merely starts with three plausible
 * bytes. All five specimens in reference/ciderpress2/ and the real 1990
 * archive beside them consume to their last byte (TESTING.md, *DART*). */
UncFormat unc_dart_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    DartHead h;
    uint32_t size;

    if (!io) return UNC_FORMAT_UNKNOWN;
    if (dart_parse(head, len, &h) != UNC_OK) return UNC_FORMAT_UNKNOWN;
    size = unc_io_size32(io);
    if (size == UNC_SIZE_UNKNOWN) return UNC_FORMAT_UNKNOWN;
    if (size != (uint32_t)h.hdrlen + h.payload) return UNC_FORMAT_UNKNOWN;
    return UNC_FORMAT_DART;
}


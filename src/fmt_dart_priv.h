/* fmt_dart_priv.h — what DART's probe and its decoder share.
 *
 * The probe stays resident and the decoder can be an overlay, so the
 * header reader they both need is declared here and defined once, in
 * fmt_dart_probe.c. DART has no signature at all: the probe IS the
 * header reader, which is why the shared part is larger here than for
 * any other format on this branch (BRANCH_NOTES.md).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_DART_PRIV_H
#define UNC_FMT_DART_PRIV_H

#include "unc_internal.h"

/* One chunk: forty sectors of 512 (20,480 bytes), then their forty tags
 * of 12 (480 more). Source: DartIntf.h, DDBLOCKSIZE, and the "How DART
 * creates a disk image" note above it. Only the total appears below —
 * nothing here separates a chunk's data from its tags, because what is
 * being written is a DART and not a volume. */
#define DART_CHUNK_BYTES  20960u
/* A length entry of -1: the chunk is stored whole. DartIntf.h, "If the
 * block length is -1, then the block isn't compressed". */
#define DART_STORED       0xFFFFu

/* Header: srcCmp, srcType, srcSize, then the table. Forty entries for a
 * disk up to 800K and seventy-two above it, so 84 bytes or 148.
 * Source: DartIntf.h, SrcInfoRec and HDSrcInfoRec. */
#define DART_SLOTS_SMALL  40u
#define DART_SLOTS_LARGE  72u
#define DART_HDR_MAX      (4u + 2u * DART_SLOTS_LARGE)

/* Compression identifiers, DartIntf.h. */
#define DART_CMP_RLE      0
#define DART_CMP_LZH      1
#define DART_CMP_NONE     2

typedef struct DartHead {
    uint8_t  cmp;
    uint8_t  type;
    uint16_t kb;
    uint16_t slots;        /* 40 or 72 */
    uint16_t hdrlen;       /* 4 + 2 * slots */
    uint16_t blocks;       /* chunks the disk actually occupies */
    uint16_t blen[DART_SLOTS_LARGE];
    uint32_t payload;      /* bytes of chunk data the table accounts for */
    uint32_t maxchunk;     /* the longest of them, which is the buffer   */
} DartHead;

/* 'DMd' and a digit; 'DART'. DartIntf.h, the file types and
 * kDartCreator. */
#define DART_TYPE_STEM 0x444D6400u
#define DART_CREATOR   0x44415254u

/* The seven type/size pairs a DART may state, and the digit that
 * completes each one's file type. Defined in fmt_dart_probe.c. */
struct DartKind { uint8_t type; uint16_t kb; uint8_t digit; };
const struct DartKind *dart_kind(uint8_t type, uint16_t kb);
uint32_t dart_chunk_bytes(uint8_t cmp, uint16_t blen);
int      dart_parse(const uint8_t *head, int32_t len, DartHead *h);

#endif

/* fmt_vise_priv.h — what Installer VISE's probe, its set identity and its
 * reader share.
 *
 * The layout, and where each fact comes from, is src/fmt_vise.c's file
 * comment.
 *
 * SPDX-License-Identifier: 0BSD
 */
#ifndef UNC_FMT_VISE_PRIV_H
#define UNC_FMT_VISE_PRIV_H

#include "unc_internal.h"

#define VISE_MAGIC     0x53564354ul   /* 'SVCT', at 0 of every segment   */
#define VISE_CAT_MAGIC 0x43564354ul   /* 'CVCT', the catalogue's         */
#define VISE_PACK      0x5041434Bul   /* 'PACK', before a later one's body */
#define VISE_HDR       44u            /* a segment's header; its payload
                                       * starts here                     */
#define VISE_CAT_HDR   20u
#define VISE_PACK_LEN  0x50u

/* The segment header's fields (measured on 29 installers and the three
 * segments of one set; fmt_vise.c). */
#define VISE_H_PART    4u             /* this segment's number, 1-based  */
#define VISE_H_STAMP   12u            /* the same in every segment of a set */
#define VISE_H_VER     16u
#define VISE_H_COUNT   20u            /* segment 1: how many there are   */
#define VISE_H_CAT     36u            /* segment 1: the catalogue        */

/* The catalogue's record suffixes, by archive version: the bytes between
 * a folder's 78 fixed bytes, or a file's 120, and its name. 0 when the
 * version is not one this engine reads. Each is MEASURED on the specimens
 * of that version (fmt_vise.c), and agrees with systemless's vise.rs for
 * every version both have. VISE_X marks the generation (VISE X, for Mac
 * OS X) whose name lengths are two bytes later, at +78 and +120, and whose
 * files are in a second file beside the installer, Installer.data. */
#define VISE_KNOWN 0x100u
#define VISE_X     0x200u
static inline uint32_t vise_suffixes(uint32_t ver)
{
    switch (ver) {
    case 0x80010201ul: case 0x80010202ul:  return VISE_KNOWN;
    case 0x80010300ul: case 0x80010301ul:
    case 0x80010302ul: case 0x80010303ul:  return VISE_KNOWN | 6u << 16;
    case 0x80010304ul:              return VISE_KNOWN | 22u << 16 | 16u << 24;
    case 0x80010307ul:              return VISE_KNOWN | 66u << 16 | 62u << 24;
    case 0x80010308ul: case 0x8001030Aul:
    case 0x8001030Bul:              return VISE_KNOWN | 70u << 16 | 66u << 24;
    case 0x8001030Cul: case 0x8001030Dul:
                                    return VISE_KNOWN | 78u << 16 | 74u << 24;
    case 0x80010A50ul: case 0x80010B00ul:
                       return VISE_KNOWN | VISE_X | 96u << 16 | 88u << 24;
    default:                               return 0;
    }
}
#define VISE_DSUF(s) (((s) >> 16) & 0xFFu)
#define VISE_FSUF(s) ((s) >> 24)
#define VISE_DLEN(s) ((s) & VISE_X ? 78u : 76u)    /* a folder's name length */
#define VISE_FLEN(s) ((s) & VISE_X ? 120u : 118u)  /* a file's               */

/* A first segment's own claims: the magic, a version this engine reads,
 * segment 1 of a count of at least one, and a catalogue past the header. */
static inline int vise_first_ok(const uint8_t *h)
{
    return unc_get_u32be(h) == VISE_MAGIC &&
           vise_suffixes(unc_get_u32be(h + VISE_H_VER)) != 0 &&
           unc_get_u32be(h + VISE_H_PART) == 1 &&
           unc_get_u32be(h + VISE_H_COUNT) >= 1 &&
           unc_get_u32be(h + VISE_H_COUNT) <= UNC_SEG_MAX_PARTS &&
           unc_get_u32be(h + VISE_H_CAT) >= VISE_HDR;
}

#endif

/*
 * unc_canon_dec.c — the canonical-Huffman symbol decoder, on its own.
 *
 * Its own file so that every overlay image that decodes canonical codes
 * links a copy of it and calls it directly. Until 2026-11-10 it lived in
 * unc_huffman.c, in ovl_codecs, and every SYMBOL crossed the host vector
 * through a generated forward (tools/overlay/mkforwards.py) to reach it:
 * a copy in each of ovl_cptdd, ovl_lzh, ovl_now and ovl_stuffit was
 * -1.3 to -3.7 % of Mac Plus engine ticks on top of the rewrite below,
 * for ~800 B an image, which ovl_codecs gives back — every one of those
 * formats keeps ovl_codecs too (FORMATS.md, *The canonical decoder in
 * each image*; DECISIONS.md 2026-11-10, *the forward every symbol took*).
 *
 * The table it reads is built by unc_canon_build_ext in unc_huffman.c,
 * whose sources it shares: RFC 1951 section 3.2.2 and puff.c's decode()
 * (reference/notes/).
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "unc_internal.h"

/* The low eight bits, reversed.
 *
 * An LSB-first stream hands a code's bits out in the opposite order
 * from the one fastlen[] is indexed by, so the ten-bit window has to be
 * turned round before it can be looked up. Two lookups and three shifts
 * per SYMBOL, against ten of everything per symbol for the walk it
 * replaces (DECISIONS.md 2026-08-27, the fast table StuffIt could not
 * reach). 256 bytes of const, shared by every UncCanon there is — which
 * is why it is done this way round rather than by storing a symbol per
 * table entry, as zlib does. That would be 2 KB more per UncCanon, and
 * DiskDoubler holds three of them at once and Now Compress two, on the
 * heap, inside budgets FORMATS.md states to the byte. */
static const uint8_t unc_revbyte[256] = {
    0x00, 0x80, 0x40, 0xc0, 0x20, 0xa0, 0x60, 0xe0, 0x10, 0x90, 0x50, 0xd0,
    0x30, 0xb0, 0x70, 0xf0, 0x08, 0x88, 0x48, 0xc8, 0x28, 0xa8, 0x68, 0xe8,
    0x18, 0x98, 0x58, 0xd8, 0x38, 0xb8, 0x78, 0xf8, 0x04, 0x84, 0x44, 0xc4,
    0x24, 0xa4, 0x64, 0xe4, 0x14, 0x94, 0x54, 0xd4, 0x34, 0xb4, 0x74, 0xf4,
    0x0c, 0x8c, 0x4c, 0xcc, 0x2c, 0xac, 0x6c, 0xec, 0x1c, 0x9c, 0x5c, 0xdc,
    0x3c, 0xbc, 0x7c, 0xfc, 0x02, 0x82, 0x42, 0xc2, 0x22, 0xa2, 0x62, 0xe2,
    0x12, 0x92, 0x52, 0xd2, 0x32, 0xb2, 0x72, 0xf2, 0x0a, 0x8a, 0x4a, 0xca,
    0x2a, 0xaa, 0x6a, 0xea, 0x1a, 0x9a, 0x5a, 0xda, 0x3a, 0xba, 0x7a, 0xfa,
    0x06, 0x86, 0x46, 0xc6, 0x26, 0xa6, 0x66, 0xe6, 0x16, 0x96, 0x56, 0xd6,
    0x36, 0xb6, 0x76, 0xf6, 0x0e, 0x8e, 0x4e, 0xce, 0x2e, 0xae, 0x6e, 0xee,
    0x1e, 0x9e, 0x5e, 0xde, 0x3e, 0xbe, 0x7e, 0xfe, 0x01, 0x81, 0x41, 0xc1,
    0x21, 0xa1, 0x61, 0xe1, 0x11, 0x91, 0x51, 0xd1, 0x31, 0xb1, 0x71, 0xf1,
    0x09, 0x89, 0x49, 0xc9, 0x29, 0xa9, 0x69, 0xe9, 0x19, 0x99, 0x59, 0xd9,
    0x39, 0xb9, 0x79, 0xf9, 0x05, 0x85, 0x45, 0xc5, 0x25, 0xa5, 0x65, 0xe5,
    0x15, 0x95, 0x55, 0xd5, 0x35, 0xb5, 0x75, 0xf5, 0x0d, 0x8d, 0x4d, 0xcd,
    0x2d, 0xad, 0x6d, 0xed, 0x1d, 0x9d, 0x5d, 0xdd, 0x3d, 0xbd, 0x7d, 0xfd,
    0x03, 0x83, 0x43, 0xc3, 0x23, 0xa3, 0x63, 0xe3, 0x13, 0x93, 0x53, 0xd3,
    0x33, 0xb3, 0x73, 0xf3, 0x0b, 0x8b, 0x4b, 0xcb, 0x2b, 0xab, 0x6b, 0xeb,
    0x1b, 0x9b, 0x5b, 0xdb, 0x3b, 0xbb, 0x7b, 0xfb, 0x07, 0x87, 0x47, 0xc7,
    0x27, 0xa7, 0x67, 0xe7, 0x17, 0x97, 0x57, 0xd7, 0x37, 0xb7, 0x77, 0xf7,
    0x0f, 0x8f, 0x4f, 0xcf, 0x2f, 0xaf, 0x6f, 0xef, 0x1f, 0x9f, 0x5f, 0xdf,
    0x3f, 0xbf, 0x7f, 0xff
};

/* The next UNC_CANON_FAST_BITS bits of an LSB-first window, MSB-first,
 * so that it indexes the same table an MSB-first window does. */
static uint32_t unc_rev_fast(uint32_t v)
{
    uint32_t r = ((uint32_t)unc_revbyte[v & 0xFFu] << 8) |
                  (uint32_t)unc_revbyte[(v >> 8) & 0xFFu];
    return r >> (16 - UNC_CANON_FAST_BITS);
}

/* The bit-at-a-time walk: puff.c's decode(), with `first` read out of the
 * table this build already has rather than carried along. Take one more
 * bit, and if the code is inside this length's run it names the symbol at
 * that offset from where the length's codes start. Out of line, so that
 * the table hit below needs none of the registers it does. */
static UNC_NOINLINE int canon_walk(const UncCanon *c, UncBitIn *bi)
{
    uint32_t code = 0, base = 0;
    int l;

    for (l = 1; l <= c->maxlen; l++) {
        int bit = unc_bitin_bit(bi);
        if (bit < 0) return -1;
        code = (code << 1) | (uint32_t)bit;
        if (code - c->first[l] < c->count[l])
            return c->sym[base + (code - c->first[l])];
        base += c->count[l];
    }
    return -1;   /* invalid: a code the incomplete set does not use */
}

/* One peek, one table lookup, one consume — instead of a call into the
 * bit reader and two array compares PER BIT (28-32 % of a DiskDoubler or
 * Now Compress run and 20 % of a Compact Pro one until 2026-08-27).
 * Both directions since that day: StuffIt method 13, SpaceSaver method 3
 * and ARC read LSB-first, and one reversal of the peeked window lets them
 * index the same table (DECISIONS.md 2026-08-27). The direction is tested
 * ONCE, not inside the peek: folding the two paths into one expression put
 * a second branch on the MSB path and cost Now Compress, Compact Pro and
 * LZH 1.7-2.7 % each, measured.
 *
 * Since 2026-11-10 the bit state is in locals for the whole hit, the
 * refill reads the window directly, and the walk is out of line: -Os saves
 * four registers instead of seven, and the symbol is one add away from
 * the code (`cdelta`, unc_internal.h). -3.2 to -7.1 % of Mac Plus engine
 * ticks on Compact Pro, LZH, Now Compress, method 13 and DiskDoubler's
 * method 10 (FORMATS.md, *The canonical decoder in each image*).
 *
 * The refill takes only bytes already in the window, as unc_bitin_fill
 * does, so it cannot cross a substream's limit or set the sticky error
 * early; at a window boundary the walk runs, which is correct whatever is
 * buffered. */
UNC_HOT int unc_canon_decode(const UncCanon *c, UncBitIn *bi)
{
    UncBufIn *in;
    uint32_t buf, peek, pos;
    int32_t n;
    int fl;

    n = bi->nbits;
    buf = bi->bitbuf;
    if (bi->le) {
        if (n < UNC_CANON_FAST_BITS) {
            in = bi->in;
            pos = in->pos;
            do {
                if (pos >= in->len) {
                    in->pos = pos; bi->bitbuf = buf; bi->nbits = n;
                    return canon_walk(c, bi);
                }
                buf |= (uint32_t)in->buf[pos++] << n;
                n += 8;
            } while (n < UNC_CANON_FAST_BITS);
            in->pos = pos;
        }
        peek = unc_rev_fast(buf & UNC_CANON_FAST_MASK);
        fl = c->fastlen[peek];
        if (fl) {
            bi->nbits = n - fl;
            bi->bitbuf = buf >> fl;
            return c->sym[(int16_t)((peek >> (UNC_CANON_FAST_BITS - fl))
                                     + c->cdelta[fl])];
        }
    } else {
        if (n < UNC_CANON_FAST_BITS) {
            in = bi->in;
            pos = in->pos;
            do {
                if (pos >= in->len) {
                    in->pos = pos; bi->bitbuf = buf; bi->nbits = n;
                    return canon_walk(c, bi);
                }
                buf = (buf << 8) | in->buf[pos++];
                n += 8;
            } while (n < UNC_CANON_FAST_BITS);
            in->pos = pos;
        }
        peek = (buf >> (n - UNC_CANON_FAST_BITS)) & UNC_CANON_FAST_MASK;
        fl = c->fastlen[peek];
        if (fl) {
            bi->nbits = n - fl;
            bi->bitbuf = buf;
            return c->sym[(int16_t)((peek >> (UNC_CANON_FAST_BITS - fl))
                                     + c->cdelta[fl])];
        }
    }
    bi->bitbuf = buf;
    bi->nbits = n;
    return canon_walk(c, bi);
}

/*
 * unc_reduce.c — zip's Reduce, methods 2 to 5.
 *
 * Two stages, applied in reverse. The outer one is a byte coder: every
 * byte value has a "follower set" of up to 32 bytes that tend to come
 * after it, sent once at the head of the stream, and a byte that is in
 * its predecessor's set costs 1 + B(N) bits instead of 9. The inner one
 * is an LZ77 over a 4 KB window, escaped by the byte 144 (0x90): 144 0
 * is a literal 144, and 144 V [extra] D is a copy whose length and
 * distance are split between V's two halves at a point the method
 * number sets — factor 1 to 4 for methods 2 to 5.
 *
 * Source: reference/notes/zip_appnote.txt 5.2, which states the whole
 * method, read beside reference/deark/foreign/ozunreduce.h (Jason
 * Summers, 2019, MIT or public domain), the implementation deark calls.
 * The layout is this engine's. Measured on the stored CRC-32 of 2,379
 * wild entries (FORMATS.md, *Reduce*):
 *
 *   - the window starts as 4,096 zero bytes (5.2.5: "assume that all
 *     the data before the start of the output stream is filled with
 *     zeros"). 1,480 of the 2,371 good entries reach into it.
 *
 * Two places where this and ozur differ, both on streams no CRC-good
 * entry contains:
 *
 *   - a copy longer than its distance is copied byte by byte, as 5.2.5
 *     says ("copy Len+3 bytes from this position"), so it repeats a run
 *     the way any LZ77 does. ozur refuses it. The 3 wild entries that
 *     have one fail their CRC either way;
 *   - an index past a follower set's count is refused: 5.2.4 defines
 *     S(j)[I] only for I < N(j). ozur reads its zeroed table and gives 0.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define RED_WIN 4096u            /* ozur's OZUR_CIRCBUF_SIZE */
#define RED_SETMAX 32u
#define RED_SET (RED_SETMAX + 1u) /* a count, then up to 32 bytes */

/* B(N), "the minimal number of bits required to encode the value of
 * N-1", for 1 <= N <= 32 (ozur_func_B). A table, because the decode
 * loop wants it once per byte and a 68000 has no instruction for it. */
static const uint8_t red_b[RED_SETMAX + 1u] = {
    0, 1, 1, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5
};

/* The bit reader is local rather than `UncBitIn`: a profile of a 549 KB
 * entry on a 68000 put 43 % of the instructions in the shared reader's
 * two out-of-line calls a byte (FORMATS.md, *Reduce*). `bb` and `nb`
 * stay in registers, LSB first, as zip writes them.
 *
 * RED_TOP fills from bytes ALREADY in the reader's window, so it never
 * reads past the entry's end or sets the reader's sticky error early;
 * RED_NEED takes one byte at a time through the reader proper, and is
 * the only route that can fail — exactly where `ozur` would. */
#define RED_TOP()                                                       \
    while (nb <= 24 && in->pos < in->len) {                             \
        bb |= (uint32_t)in->buf[in->pos++] << nb;                       \
        nb += 8;                                                        \
    }
#define RED_NEED(n)                                                     \
    while (nb < (n)) {                                                  \
        int x_ = unc_bufin_next(in);                                    \
        if (x_ < 0) { err = in->err; goto out; }                        \
        bb |= (uint32_t)x_ << nb;                                       \
        nb += 8;                                                        \
    }

int unc_reduce_decode(UncAlloc *al, UncBufIn *in, uint32_t factor,
                      uint32_t usize, uint32_t *crc, uint8_t *obuf,
                      uint32_t ocap, UncPutRun emit, void *ectx)
{
    uint8_t *set;                /* [k * 33] set k's count, then bytes */
    uint32_t bb = 0, pos = 0, w = 0, len = 0, mask, i;
    uint32_t nb = 0;
    uint8_t last = 0, v = 0;
    int state = 0, err = UNC_OK;

    if (factor < 1u || factor > 4u || ocap < RED_WIN) return UNC_ERR_CORRUPT;
    if (usize == 0) return UNC_OK;
    mask = 0xffu >> factor;

    set = (uint8_t *)unc_alloc(al, 256u * RED_SET);
    if (!set) return UNC_ERR_MEM;
    for (i = 0; i < RED_WIN; i++) obuf[i] = 0;

    /* The follower sets, 255 down to 0 (ozur_part1_readfollowersets). */
    for (i = 256u; i-- > 0;) {
        uint8_t *s = set + i * RED_SET;
        uint32_t n, z;
        RED_TOP();
        RED_NEED(6);
        n = bb & 63u;
        bb >>= 6;
        nb -= 6;
        if (n > RED_SETMAX) { err = UNC_ERR_CORRUPT; goto out; }
        s[0] = (uint8_t)n;
        for (z = 1; z <= n; z++) {
            RED_TOP();
            RED_NEED(8);
            s[z] = (uint8_t)bb;
            bb >>= 8;
            nb -= 8;
        }
    }

    /* `obuf` is the window: emitted each time it fills, and the history
     * a copy reaches into stays where it is (ozur_emit_byte). */
    while (pos < usize) {
        const uint8_t *s = set + (uint32_t)last * RED_SET;
        uint32_t c;

        /* Stage 1, one byte (ozur_part1_getnextbyte): a literal if the
         * set is empty or a 1 bit says so, else an index into it. At
         * most 9 bits, so one top-up covers the symbol unless the
         * window ends inside it. */
        if (nb < 9) RED_TOP();
        if (s[0] != 0) {
            RED_NEED(1);
            c = bb & 1u;
            bb >>= 1;
            nb -= 1;
            if (c == 0) {
                uint32_t k = red_b[s[0]];
                RED_NEED(k);
                c = bb & ((1u << k) - 1u);
                bb >>= k;
                nb -= k;
                /* An index past the set's count: APPNOTE.TXT leaves it
                 * undefined, `ozur` reads its zeroed table and gives 0,
                 * and no wild entry has one. Refused — an index the
                 * writer never sent is damage. */
                if (c >= s[0]) { err = UNC_ERR_CORRUPT; goto out; }
                c = s[1 + c];
                goto staged;
            }
        }
        RED_NEED(8);
        c = bb & 0xffu;
        bb >>= 8;
        nb -= 8;
    staged:
        last = (uint8_t)c;

        /* Stage 2 (ozur_part2). */
        if (state == 0) {
            if (c == 144u) { state = 1; continue; }
        } else if (state == 1) {
            if (c != 0) {
                v = (uint8_t)c;
                len = c & mask;
                state = len == mask ? 2 : 3;
                continue;
            }
            c = 144u;                /* 144 0 is a literal 144 */
            state = 0;
        } else if (state == 2) {
            len += c;
            state = 3;
            continue;
        } else {
            uint32_t dist = ((uint32_t)(v >> (8u - factor)) << 8) + c + 1u;
            uint32_t n = len + 3u;
            uint32_t from = (w - dist) & (RED_WIN - 1u);
            state = 0;
            if (n > usize - pos) n = usize - pos;
            pos += n;
            /* In runs that neither end of the window interrupts, forward
             * and a byte at a time, so a copy longer than its distance
             * reads bytes it has just written — a repeated run. */
            while (n > 0) {
                uint32_t run = n, j;
                if (run > RED_WIN - w) run = RED_WIN - w;
                if (run > RED_WIN - from) run = RED_WIN - from;
                for (j = 0; j < run; j++) obuf[w + j] = obuf[from + j];
                w += run;
                from = (from + run) & (RED_WIN - 1u);
                n -= run;
                if (w == RED_WIN) {
                    *crc = unc_crc32(*crc, obuf, (int32_t)w);
                    if ((err = emit(ectx, obuf, w)) != UNC_OK) goto out;
                    w = 0;
                }
            }
            continue;
        }
        obuf[w++] = (uint8_t)c;
        pos++;
        if (w == RED_WIN) {
            *crc = unc_crc32(*crc, obuf, (int32_t)w);
            if ((err = emit(ectx, obuf, w)) != UNC_OK) goto out;
            w = 0;
        }
    }

    if (w) {
        *crc = unc_crc32(*crc, obuf, (int32_t)w);
        err = emit(ectx, obuf, w);
    }
out:
    unc_free(al, set);
    return err;
}

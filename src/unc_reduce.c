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
 * Source: reference/deark/foreign/ozunreduce.h (Jason Summers, 2019,
 * MIT or public domain), which deark's fmtutil-zip.c calls, and which
 * was written from PKWARE's APPNOTE.TXT. Every rule below is that
 * file's; the layout is this engine's. Two of its rules read as
 * defensive and are not, measured on the stored CRC-32 of 2,379 wild
 * entries (FORMATS.md, *Reduce*):
 *
 *   - the window starts as 4,096 zero bytes, and a copy may reach back
 *     into them. 1,480 of the 2,371 good entries do, and fail
 *     without the zeros;
 *   - a copy longer than its distance is corrupt (ozur_emit_copy_of_
 *     prev_bytes). None of the CRC-good entries has one, and the three
 *     entries that do fail their CRC with overlap allowed too.
 *
 * An index past a follower set's count reads 0, as ozur's zeroed table
 * does; no wild entry has one.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define RED_WIN 4096u            /* ozur's OZUR_CIRCBUF_SIZE */
#define RED_SETMAX 32u

/* B(N), "the minimal number of bits required to encode the value of
 * N-1", for 1 <= N <= 32 (ozur_func_B). */
static int red_bits(uint32_t n)
{
    int b = 1;
    while ((1u << b) < n) b++;
    return b;
}

int unc_reduce_decode(UncAlloc *al, UncBufIn *in, uint32_t factor,
                      uint32_t usize, uint32_t *crc, uint8_t *obuf,
                      uint32_t ocap, UncPutRun emit, void *ectx)
{
    /* [k * 33] is set k's count, [k * 33 + 1 ...] its bytes. */
    uint8_t *set;
    UncBitIn bi;
    uint32_t pos = 0, w = 0, len = 0, mask, i;
    uint8_t last = 0, v = 0;
    int state = 0, err = UNC_OK;

    if (factor < 1u || factor > 4u || ocap < RED_WIN) return UNC_ERR_CORRUPT;
    if (usize == 0) return UNC_OK;
    mask = 0xffu >> factor;

    set = (uint8_t *)unc_alloc(al, 256u * (RED_SETMAX + 1u));
    if (!set) return UNC_ERR_MEM;
    for (i = 0; i < 256u * (RED_SETMAX + 1u); i++) set[i] = 0;
    for (i = 0; i < RED_WIN; i++) obuf[i] = 0;

    unc_bitin_init_le(&bi, in);

    /* The follower sets, 255 down to 0 (ozur_part1_readfollowersets). */
    for (i = 256u; i-- > 0;) {
        uint8_t *s = set + i * (RED_SETMAX + 1u);
        uint32_t n, z;
        int32_t b = unc_bitin_bits_le(&bi, 6);
        if (b < 0) { err = bi.err; goto out; }
        n = (uint32_t)b;
        if (n > RED_SETMAX) { err = UNC_ERR_CORRUPT; goto out; }
        s[0] = (uint8_t)n;
        for (z = 1; z <= n; z++) {
            if ((b = unc_bitin_bits_le(&bi, 8)) < 0) { err = bi.err; goto out; }
            s[z] = (uint8_t)b;
        }
    }

    /* `obuf` is the window: emitted each time it fills, and the history
     * a copy reaches into stays where it is (ozur_emit_byte). */
    while (pos < usize) {
        const uint8_t *s = set + (uint32_t)last * (RED_SETMAX + 1u);
        uint8_t c;
        int32_t b;

        /* Stage 1, one byte (ozur_part1_getnextbyte): a literal if the
         * set is empty or a 1 bit says so, else an index into it. */
        b = s[0] != 0 ? unc_bitin_bits_le(&bi, 1) : 1;
        if (b == 0) {
            if ((b = unc_bitin_bits_le(&bi, red_bits(s[0]))) < 0) {
                err = bi.err;
                break;
            }
            c = s[1 + (uint32_t)b];   /* past the count: 0, as ozur's */
        } else {
            if (b < 0 || (b = unc_bitin_bits_le(&bi, 8)) < 0) {
                err = bi.err;
                break;
            }
            c = (uint8_t)b;
        }
        last = c;

        /* Stage 2 (ozur_part2). */
        if (state == 0) {
            if (c == 144u) { state = 1; continue; }
        } else if (state == 1) {
            if (c != 0) {
                v = c;
                len = v & mask;
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
            if (n > dist) { err = UNC_ERR_CORRUPT; break; }
            while (n-- > 0 && pos < usize) {
                obuf[w++] = obuf[from];
                from = (from + 1u) & (RED_WIN - 1u);
                pos++;
                if (w == RED_WIN) {
                    *crc = unc_crc32(*crc, obuf, (int32_t)w);
                    if ((err = emit(ectx, obuf, w)) != UNC_OK) goto out;
                    w = 0;
                }
            }
            continue;
        }
        obuf[w++] = c;
        pos++;
        if (w == RED_WIN) {
            *crc = unc_crc32(*crc, obuf, (int32_t)w);
            if ((err = emit(ectx, obuf, w)) != UNC_OK) goto out;
            w = 0;
        }
    }

    if (err == UNC_OK && w) {
        *crc = unc_crc32(*crc, obuf, (int32_t)w);
        err = emit(ectx, obuf, w);
    }
out:
    unc_free(al, set);
    return err;
}

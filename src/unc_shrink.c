/*
 * unc_shrink.c — zip method 1, Shrink.
 *
 * Moved out of unc_lzw.c on 2026-10-11, unchanged, so that it can sit
 * beside Reduce in the one image only zip keeps (FORMATS.md, *Shrink*,
 * *Reduce*). It shares no code with compress(1)'s LZW.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* LZW with LSB-first codes of 9 bits growing to 13, and no automatic
 * growth: code 256 is an escape, and the code after it says what to do.
 *
 *   256, 1   one bit wider (an error at 13)
 *   256, 2   PARTIAL clear: free every dynamic code that is no other
 *            code's parent, and fill freed slots lowest first from then
 *            on — so a new string lands in the first FREE slot, not at
 *            the end of the table
 *
 * Source: reference/notes/zip_appnote.txt 5.1 names the method and no
 * more, so the format is reference/deark/src/fmtutil-lzw.c (Jason
 * Summers, MIT), its DE_LZWFMT_ZIPSHRINK paths: `delzw_process_code`
 * for the escape, `delzw_partial_clear`, `delzw_find_first_free_entry`,
 * `delzw_process_data_code` and `delzw_emit_code`. Every rule below is
 * one of those, including two that look like defensive code and are
 * not, because the archives need them (FORMATS.md, *Shrink*):
 *
 *   - a code naming a FREE slot is not an error. It is the string about
 *     to be defined — the old code's string plus its own first byte —
 *     which lands in the first free slot, whatever number the code
 *     said. 1,798 of 2,246 wild entries take this path.
 *   - a walk that reaches a FREE slot emits the previous string's first
 *     byte for it and carries on up the OLD code's string. A partial
 *     clear can free the old code itself, and the next string is then
 *     defined on a parent that no longer exists. 1 of 2,246 entries
 *     needs it, and comes out CRC-bad without it.
 *
 * XADMaster's XADZipShrinkHandle.m is NOT the source, and is the reason
 * this cites deark: it performs a partial clear as a FULL one, and
 * `unar` fails every entry that has one (FORMATS.md, *Shrink*).
 *
 * Three bytes per slot — a parent word and a byte — because a code is
 * 13 bits and the word's top two carry the rest: whether the slot is in
 * use, and the partial clear's "has a child" mark. Codes 0..255 and the
 * escape are fixed by their number. 24,576 B for a full table, where a
 * separate kind byte made it 32,768 and a big Shrink entry's peak
 * 47,286 B (FORMATS.md, *Shrink*).
 *
 * Sized from the INPUT: every code is at least 9 bits and defines at
 * most one string, and a new string takes the lowest free slot, so the
 * highest slot one can reach is 257 + (compressed bits / 9). That is
 * lzw_cap_from_input's idea, above, and simpler here, because the width
 * only grows when the stream says so. */
#define SHR_SLOTS   8192u       /* 13-bit codes */
#define SHR_FIRST   257u        /* 0..255 bytes, 256 the escape */
#define SHR_FREE    0u
#define SHR_USED    1u
#define SHR_ROOT    2u
#define SHR_ESC     3u
#define SHR_INUSE   0x8000u     /* parent word: the slot holds a string */
#define SHR_MARK    0x4000u     /* parent word: partial clear's mark */
#define SHR_CODE    0x1FFFu

typedef struct ShrTab {
    uint16_t *parent;
    uint8_t  *byte;
    uint32_t  cap;
} ShrTab;

/* A code past `cap` was never given a string, which is what FREE says. */
#define SHR_KIND_OF(t, k) ((k) < 256u ? SHR_ROOT : (k) == 256u ? SHR_ESC \
    : (k) < (t)->cap && ((t)->parent[k] & SHR_INUSE) ? SHR_USED : SHR_FREE)

/* The length of code `k`'s string, walking exactly as shr_put does.
 * `old` stands in for a FREE slot met on the way (above). 0 means the
 * walk passed SHR_SLOTS bytes without reaching a byte code, which only
 * a corrupt stream can make it do: deark's own bound. */
static uint32_t shr_len(const ShrTab *t, uint32_t k, uint32_t old)
{
    uint32_t n = 0;

    for (;;) {
        uint32_t kind;
        if (n == SHR_SLOTS) return 0;
        n++;
        kind = SHR_KIND_OF(t, k);
        if (kind == SHR_FREE) { k = old; continue; }
        if (kind == SHR_ROOT) return n;
        k = t->parent[k] & SHR_CODE;
    }
}

/* Write code `k`'s `n`-byte string into `dst`, last byte first, and
 * return its first byte. `first` is the previous string's first byte,
 * which is what a FREE slot stands for. */
static uint8_t shr_put(const ShrTab *t, uint32_t k, uint32_t old,
                       uint8_t first, uint8_t *dst, uint32_t n)
{
    for (;;) {
        uint32_t kind = SHR_KIND_OF(t, k);
        if (kind == SHR_FREE) {
            dst[--n] = first;
            k = old;
            continue;
        }
        dst[--n] = t->byte[k];
        if (kind == SHR_ROOT) return t->byte[k];
        k = t->parent[k] & SHR_CODE;
    }
}

/* Define a new string, `parent`'s plus `byte`, in the lowest free slot
 * at or after `*next`. Returns the slot, or -1 when the table is full,
 * which only a corrupt stream can make it. */
static int32_t shr_add(ShrTab *t, uint32_t *next, uint32_t *top,
                       uint32_t parent, uint8_t byte)
{
    uint32_t k = *next;

    while (k < t->cap && (t->parent[k] & SHR_INUSE)) k++;
    if (k >= t->cap) return -1;
    /* A mark already on a free slot stays: deark's add leaves `flags`
     * alone, and shr_partial_clear can mark a slot above `top`. */
    t->parent[k] = (uint16_t)((t->parent[k] & SHR_MARK) | SHR_INUSE |
                              parent);
    t->byte[k] = byte;
    *next = k + 1u;
    if (k > *top) *top = k;
    return (int32_t)k;
}

/* Free every dynamic code that is no used code's parent. The range
 * stops at the highest slot ever used, as deark's does: a mark left
 * above it would survive to that slot's first use, and is left to. */
static void shr_partial_clear(ShrTab *t, uint32_t top)
{
    uint32_t i;

    for (i = SHR_FIRST; i <= top; i++) {
        uint32_t p = t->parent[i] & SHR_CODE;
        if ((t->parent[i] & SHR_INUSE) && p >= SHR_FIRST && p < t->cap)
            t->parent[p] |= SHR_MARK;
    }
    for (i = SHR_FIRST; i <= top; i++) {
        if (t->parent[i] & SHR_MARK) {
            t->parent[i] &= (uint16_t)~SHR_MARK;
        } else {
            t->parent[i] = 0;
            t->byte[i] = 0;
        }
    }
}

int unc_shrink_decode(UncAlloc *al, UncBufIn *in, uint32_t usize,
                      uint32_t *crc, uint8_t *obuf, uint32_t ocap,
                      UncPutRun emit, void *ectx)
{
    ShrTab t;
    uint8_t *mem;
    UncBitIn bi;
    uint32_t i, width = 9, next = SHR_FIRST, top = SHR_FIRST - 1u;
    uint32_t old = 0, pos = 0, fill = 0;
    uint8_t first = 0;          /* the last string's first byte */
    int have = 0, esc = 0, err = UNC_OK;

    if (usize == 0) return UNC_OK;

    t.cap = SHR_SLOTS;
    if (in->limit < 0x10000000u) {
        uint32_t want = SHR_FIRST + in->limit * 8u / 9u + 1u;
        if (want < t.cap) t.cap = want;
    }
    mem = (uint8_t *)unc_alloc(al, t.cap * 3u);
    if (!mem) return UNC_ERR_MEM;
    t.parent = (uint16_t *)(void *)mem;               /* 2-aligned: alloc */
    t.byte = mem + t.cap * 2u;
    for (i = 0; i < t.cap; i++) {
        t.parent[i] = 0;
        t.byte[i] = (uint8_t)(i < 256u ? i : 0u);
    }

    unc_bitin_init_le(&bi, in);

    while (pos < usize) {
        uint32_t code, kind, out, n;
        /* The bits are taken here when the reader's window holds them,
         * which is all but once per window: the shared reader's
         * out-of-line call per code was a quarter of a Shrink run's
         * 68000 instructions (FORMATS.md, *Shrink*). */
        if (unc_bitin_fill(&bi, (int)width)) {
            code = bi.bitbuf & ((1u << width) - 1u);
            bi.bitbuf >>= width;
            bi.nbits -= (int32_t)width;
        } else {
            int32_t v = unc_bitin_bits_le(&bi, (int)width);
            if (v < 0) { err = bi.err; break; }
            code = (uint32_t)v;
        }

        if (esc) {
            esc = 0;
            if (code == 1 && width < 13u) width++;
            else if (code == 2) {
                shr_partial_clear(&t, top);
                next = SHR_FIRST;
                /* A tick per clear: two walks of the table for 18 bits
                 * of input, so a stream of nothing else spends ~17
                 * minutes of a Mac Plus between the reader's 8 KB
                 * ticks, and Cancel with it (FORMATS.md, *Shrink*). */
                if (in->ps &&
                    (err = unc_progress_at(in->ps, in->ps->done)) != UNC_OK)
                    break;
            }
            else { err = UNC_ERR_CORRUPT; break; }
            continue;
        }
        kind = SHR_KIND_OF(&t, code);
        if (kind == SHR_ESC) { esc = 1; continue; }

        /* Which string comes out. A FREE slot (after the first code) is
         * the string being defined, so it is defined first — the old
         * string plus the old string's first byte — and that is what
         * comes out. Anything else comes out as it stands, and defines
         * the old string plus ITS first byte afterwards. */
        out = code;
        if (have && kind == SHR_FREE) {
            int32_t k = shr_add(&t, &next, &top, old, first);
            if (k < 0) { err = UNC_ERR_CORRUPT; break; }
            out = (uint32_t)k;
        }

        n = shr_len(&t, out, old);
        if (n == 0 || n > ocap) { err = UNC_ERR_CORRUPT; break; }
        if (fill + n > ocap) {
            *crc = unc_crc32(*crc, obuf, (int32_t)fill);
            if ((err = emit(ectx, obuf, fill)) != UNC_OK) break;
            fill = 0;
        }
        {
            uint8_t lead = shr_put(&t, out, old, first, obuf + fill, n);
            uint32_t take = usize - pos < n ? usize - pos : n;
            fill += take;
            pos += take;
            if (!have) {
                /* The first code defines nothing, and its own slot's
                 * byte is what the next string's first byte is taken
                 * from — deark's `last_value = ct[code].value`. */
                have = 1;
                first = (uint8_t)(code < t.cap ? t.byte[code] : 0u);
            } else {
                if (kind != SHR_FREE &&
                    shr_add(&t, &next, &top, old, lead) < 0) {
                    err = UNC_ERR_CORRUPT;
                    break;
                }
                first = lead;
            }
        }
        old = code;
    }

    if (err == UNC_OK && fill) {
        *crc = unc_crc32(*crc, obuf, (int32_t)fill);
        err = emit(ectx, obuf, fill);
    }
    unc_free(al, mem);
    return err;
}

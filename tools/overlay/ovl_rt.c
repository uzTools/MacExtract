/* ovl_rt.c — the four routines gcc emits calls to whether or not anybody
 * wrote one, compiled into every overlay image.
 *
 * An image links no libc: it is a flat -mpcrel blob, and the only archive on
 * its link line is libgcc. Every symbol therefore has to be defined inside
 * it, or forwarded to the application through the host vector
 * (tools/overlay/mkforwards.py). That is fine for engine helpers, which are
 * called by name from source anybody can read — and useless against calls
 * the COMPILER invents, which appear in no source file and are found only
 * when the link fails.
 *
 * `-fno-builtin` does not stop it and neither does
 * `-fno-tree-loop-distribute-patterns`. Both are on mkoverlay.sh's command
 * line, and with both, at -Os -mcpu=68000 -mpcrel, a plain struct assignment
 * of 400 bytes still emits a call to `memcpy` (measured 2026-09-25 with the
 * exact flags). The loop-distribution flag covers the `for (i = 0; i < n;
 * i++) p[i] = 0;` idiom that arrived with main's fused Compact Pro stages and
 * nothing else; it is one idiom, and this class has as many as the optimiser
 * has passes.
 *
 * So the net is here rather than in a flag. The four are compiled with
 * -ffunction-sections like everything else, so --gc-sections drops every one
 * nothing references: an image that needs none is byte-for-byte the image it
 * was before this file existed, which is checked rather than assumed
 * (BRANCH_NOTES.md, *the runtime net*).
 *
 * These are correctness, not speed. Byte-wise on purpose: no unaligned
 * dereference, nothing to prove about 68000 word alignment. Resident code
 * calls Retro68's libc, which is faster, so an image that pulls one of these
 * into a hot path is slower than the same code resident — mkoverlay.sh prints
 * which routines an image took, because a silent performance change is the
 * one thing this file could cost.
 *
 * No engine source includes this file and no engine rule is bent by it: the
 * "no libc in the engine" rule is about src/, and these are four definitions
 * in the overlay glue under tools/.
 */

typedef __SIZE_TYPE__ ovl_size_t;   /* size_t without a header: an image
                                     * compiles freestanding. */

void *memcpy(void *dst, const void *src, ovl_size_t n)
{
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    while (n-- > 0) *d++ = *s++;
    return dst;
}

void *memmove(void *dst, const void *src, ovl_size_t n)
{
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    if (d == s || n == 0) return dst;
    if (d < s) { while (n-- > 0) *d++ = *s++; return dst; }
    d += n; s += n;                       /* overlapping upward: copy down */
    while (n-- > 0) *--d = *--s;
    return dst;
}

void *memset(void *dst, int c, ovl_size_t n)
{
    unsigned char *d = (unsigned char *)dst;
    unsigned char v = (unsigned char)c;
    while (n-- > 0) *d++ = v;
    return dst;
}

int memcmp(const void *a, const void *b, ovl_size_t n)
{
    const unsigned char *p = (const unsigned char *)a;
    const unsigned char *q = (const unsigned char *)b;
    while (n-- > 0) {
        if (*p != *q) return (int)*p - (int)*q;
        p++; q++;
    }
    return 0;
}

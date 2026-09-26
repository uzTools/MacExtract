/* ovl_load_test.c — the overlay loader, asserted off the Macintosh.
 *
 * Runs the REAL loader (mac/ovl_load_eager.c or mac/ovl_load_lazy.c, chosen
 * by the build exactly as the application chooses it) against the REAL images
 * the build just wrote, through the mock Memory and Resource Managers in
 * tests/ovlbox/ovlbox.c. Every assertion here is a property that, until
 * 2026-09-26, could only be read off a probe build's completion alert on an
 * emulated Macintosh:
 *
 *   - the eager lifetime reads the bundle ONCE and never re-reads it, and the
 *     lazy one reads once per image and not twice;
 *   - every relocation in every image lands at the address the image actually
 *     runs at — checked against the raw file's own trailer, arithmetic and
 *     all, including for a KEPT image whose copy is relocated a second time
 *     by the DIFFERENCE of two addresses;
 *   - the documented instruction-cache flush is reached at both fixup sites,
 *     and falls through without a trap on a 64K ROM;
 *   - what the eager release keeps and what it gives back, per format, and
 *     that an image wanted after the release is reported rather than
 *     returned.
 *
 * It does NOT call an image's entry point: the images are m68k code, this
 * program is built both natively and for m68k, and only the m68k lane could.
 * Calling them is tests/run_mac_sink.sh's overlay lane, which extracts
 * fixtures byte-exact through the same images under qemu-m68k.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ovlbox.h"
#include "overlay.h"
#include "macextract.h"

/* The loader's own header needs the engine's internals; both are on the
 * include path the harness passes. */
OverlayEntry ovl_image(short id);
OverlayEntry ovl_image_q(short id, int expected);
void ovl_preload(void);
void ovl_release_if_unwanted(UncFormat fmt, UncIO *io);
unsigned long ovl_be32(const unsigned char *p);
unsigned short ovl_be16(const unsigned char *p);
void ovl_fixup(unsigned char *base, unsigned long size, long delta);
extern short gWantedAfterRelease, gKeepFail, gRelFmt;
extern short gFlushHas, gFlushCalls;

/* The Ptr-level calls mac/mac_mocks.h declares and tests/mac_sink_test.c
 * defines. This program is not the sink test, so the two the loader reaches
 * are here — and nowhere else, which is why ovlbox.c does not define them:
 * the sink test's overlay lane links its own. */
void BlockMoveData(const void *src, void *dst, Size n)
{
    memmove(dst, src, (size_t)n);
}

static int gFails;

#define CHECK(cond, ...)                                                   \
    do { if (!(cond)) { printf("  FAIL: "); printf(__VA_ARGS__);           \
                        printf("\n"); gFails++; } } while (0)

static const short kIds[] = {
    OVL_ID_CRYPT, OVL_ID_SPACESAVER, OVL_ID_CPTDD, OVL_ID_LZH, OVL_ID_ARC,
    OVL_ID_NOW, OVL_ID_SUPERDISK, OVL_ID_PACKIT, OVL_ID_TEXT, OVL_ID_STUFFIT,
    OVL_ID_EXO, OVL_ID_CODECS, OVL_ID_BINHEX, OVL_ID_BTOA
};
#define NIDS ((int)(sizeof kIds / sizeof kIds[0]))

/* The raw image as the build wrote it, for the expectations: its trailer says
 * which longs the loader must have patched, and its bytes say what they held
 * before. */
static unsigned char *raw_image(const char *dir, short id, long *len)
{
    char path[900];
    FILE *f;
    unsigned char *buf;
    long n;
    snprintf(path, sizeof path, "%s/%d.bin", dir, (int)id);
    f = fopen(path, "rb");
    if (f == NULL) return NULL;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    buf = (unsigned char *)malloc((size_t)n);
    if (buf == NULL || fread(buf, 1, (size_t)n, f) != (size_t)n) {
        free(buf); fclose(f); return NULL;
    }
    fclose(f);
    *len = n;
    return buf;
}

/* Every relocation the trailer lists, at the address the image is loaded at.
 *
 * This is the check the build could not make: mkoverlay.sh asks a linked image
 * for its relocations, and the loader is what applies them. A delta computed
 * the wrong way round, an offset read little-endian, a trailer written for a
 * different image — all of them land here, per image, at its real address.
 */
static int check_relocs(const char *what, short id, const unsigned char *mem,
                        const unsigned char *raw, long rawlen)
{
    unsigned long n, table, i;
    int bad = 0;
    if (rawlen < 4) return 0;
    n = ovl_be32(raw + rawlen - 4);
    if (n == 0 || n > ((unsigned long)rawlen - 4) / 4) return 0;
    table = (unsigned long)rawlen - 4 - n * 4;
    for (i = 0; i < n; i++) {
        unsigned long off = ovl_be32(raw + table + i * 4);
        unsigned long want, got;
        if (off + 4 > table) continue;
        /* Truncated to 32 bits, which is what the loader writes: four bytes,
         * big-endian. On the Macintosh a pointer IS 32 bits and the
         * truncation is invisible; on a 64-bit host it is the whole reason an
         * image cannot be CALLED here, only checked (the m68k lane calls
         * them). */
        want = (ovl_be32(raw + off) + (unsigned long)mem) & 0xFFFFFFFFUL;
        got = ovl_be32(mem + off);
        if (want != got) {
            printf("  FAIL: %s image %d: relocation at +%lu is 0x%08lx, "
                   "wanted 0x%08lx (base %p)\n", what, (int)id, off,
                   got, want, (const void *)mem);
            bad++;
            gFails++;
        }
    }
    if (!bad && n)
        printf("  image %d: %lu relocation(s) correct at %p\n",
               (int)id, n, (const void *)mem);
    return bad;
}

/* The trailer's guards, on crafted input. ovl_fixup must leave an image alone
 * rather than patch something arbitrary: a count that cannot fit, an offset
 * inside the trailer itself, an image too short to have one. */
static void fixup_guards(void)
{
    unsigned char img[32];
    unsigned char before[32];
    int i;

    printf("ovl_fixup guards\n");

    /* n = 0: nothing happens, and the image is not touched. */
    memset(img, 0xAA, sizeof img);
    memset(img + 28, 0, 4);
    memcpy(before, img, sizeof img);
    ovl_fixup(img, sizeof img, 0x1000);
    CHECK(memcmp(img, before, sizeof img) == 0, "n=0 patched something");

    /* n larger than the image can hold: refused whole. */
    memset(img, 0xAA, sizeof img);
    img[28] = 0; img[29] = 0; img[30] = 0xFF; img[31] = 0xFF;
    memcpy(before, img, sizeof img);
    ovl_fixup(img, sizeof img, 0x1000);
    CHECK(memcmp(img, before, sizeof img) == 0, "an absurd count was applied");

    /* An offset that points INTO the trailer is skipped, not patched — this
     * is the guard that stands between a debug-section offset and a hang
     * (tools/overlay/mkreloctrailer.py). */
    memset(img, 0xAA, sizeof img);
    img[24] = 0; img[25] = 0; img[26] = 0; img[27] = 24;   /* off = 24 */
    img[28] = 0; img[29] = 0; img[30] = 0; img[31] = 1;    /* n = 1 */
    memcpy(before, img, sizeof img);
    ovl_fixup(img, sizeof img, 0x1000);
    CHECK(memcmp(img, before, sizeof img) == 0,
          "an offset inside the trailer was patched");

    /* A real one, and the arithmetic: +4 holds 0x00000010, delta 0x1000. */
    memset(img, 0, sizeof img);
    img[4] = 0; img[5] = 0; img[6] = 0; img[7] = 0x10;
    img[24] = 0; img[25] = 0; img[26] = 0; img[27] = 4;
    img[28] = 0; img[29] = 0; img[30] = 0; img[31] = 1;
    ovl_fixup(img, sizeof img, 0x1000);
    CHECK(ovl_be32(img + 4) == 0x1010UL, "0x10 + 0x1000 came out as 0x%lx",
          ovl_be32(img + 4));

    /* A negative delta, which is what the eager keep hands it when the copy
     * lands below the bundle. */
    ovl_fixup(img, sizeof img, -0x1000);
    CHECK(ovl_be32(img + 4) == 0x10UL, "a negative delta did not undo it");

    /* Too short to have a trailer at all. */
    for (i = 0; i < 4; i++) {
        unsigned char tiny[4];
        memset(tiny, 0x55, sizeof tiny);
        ovl_fixup(tiny, (unsigned long)i, 0x1000);
        CHECK(tiny[0] == 0x55, "a %d-byte image was patched", i);
    }
}

int main(int argc, char **argv)
{
    const char *rawdir = argc >= 2 ? argv[1] : NULL;
    UncIO io;
    int i;
    long reads0, flushes0;

    if (rawdir == NULL) {
        fprintf(stderr, "usage: %s <raw-image-dir>   ($OVLBOX_IMAGES is the "
                        "manifest the loader reads)\n", argv[0]);
        return 2;
    }
    memset(&io, 0, sizeof io);

    fixup_guards();

    if (getenv("OVLBOX_NO_FLUSH_ROUTE") != NULL) {
        /* A 64K ROM offers neither trap. The flush must fall through without
         * calling one, and every image must still load. */
        ovlbox_set_flush_route(0);
        printf("flush route: none (a 64K ROM)\n");
    }

    if (ovlbox_load_manifest(getenv("OVLBOX_IMAGES")) <= 0) {
        fprintf(stderr, "ovl_load_test: no images — $OVLBOX_IMAGES is %s\n",
                getenv("OVLBOX_IMAGES") ? getenv("OVLBOX_IMAGES") : "unset");
        return 2;
    }

    ovl_preload();
#ifdef OVL_LANE_EAGER
    printf("eager: preload read %ld resource(s), %ld flush(es)\n",
           ovlbox_reads, ovlbox_flushes);
    CHECK(ovlbox_reads == 1, "the bundle took %ld reads, not 1", ovlbox_reads);
    CHECK(ovlbox_flushes == (getenv("OVLBOX_NO_FLUSH_ROUTE") ? 0 : 1),
          "the bundle fixup flushed %ld time(s)", ovlbox_flushes);
#else
    printf("lazy: preload read %ld resource(s) (it reads nothing, by design)\n",
           ovlbox_reads);
    CHECK(ovlbox_reads == 0, "the lazy lifetime read %ld resource(s) at launch",
          ovlbox_reads);
#endif

    /* Every image is found, and every relocation in it is right where it
     * sits. In the eager lifetime that is inside the bundle; in the lazy one
     * each is its own resource and each read is counted. */
    printf("every image, found and relocated\n");
    for (i = 0; i < NIDS; i++) {
        long rawlen = 0;
        unsigned char *raw = raw_image(rawdir, kIds[i], &rawlen);
        OverlayEntry e;
        long before = ovlbox_reads;
        CHECK(raw != NULL, "no raw image for id %d in %s", (int)kIds[i], rawdir);
        if (raw == NULL) continue;
        e = ovl_image(kIds[i]);
        CHECK(e != NULL, "image %d did not load", (int)kIds[i]);
        if (e == NULL) { free(raw); continue; }
        check_relocs("loaded", kIds[i], (const unsigned char *)e, raw, rawlen);
#ifdef OVL_LANE_EAGER
        CHECK(ovlbox_reads == before, "image %d cost a second read", (int)kIds[i]);
#else
        CHECK(ovlbox_reads == before + 1,
              "image %d read %ld time(s), not once", (int)kIds[i],
              ovlbox_reads - before);
        /* Asked twice, read once. */
        { OverlayEntry again = ovl_image(kIds[i]);
          CHECK(again == e, "image %d moved between two asks", (int)kIds[i]);
          CHECK(ovlbox_reads == before + 1, "image %d was re-read", (int)kIds[i]); }
#endif
        free(raw);
    }

    /* Nothing the loader hands out may move, and the mock is the instrument
     * for it: every unlocked block moves on every allocation here, where a
     * Macintosh compacts only when it must. So force an allocation and ask
     * again — an image the loader forgot to lock changes address, and its
     * relocations are then wrong for where it sits.
     *
     * Neither lifetime has ever moved one; the eager one locks the bundle at
     * preload and each copy after MoveHHi, and the lazy one locks each image
     * before its first fixup. This is what says so without a Macintosh. */
    printf("every image stays put across a compaction\n");
    {
        OverlayEntry before[NIDS];
        Handle junk;
        long moves0 = ovlbox_moves;
        for (i = 0; i < NIDS; i++) before[i] = ovl_image(kIds[i]);
        junk = NewHandle(64L * 1024);       /* whatever moves, moves now */
        CHECK(junk != NULL, "the mock heap refused 64 KB");
        for (i = 0; i < NIDS; i++) {
            OverlayEntry now = ovl_image(kIds[i]);
            CHECK(now == before[i], "image %d moved from %p to %p",
                  (int)kIds[i], (void *)before[i], (void *)now);
        }
        DisposeHandle(junk);
        printf("  %ld block(s) moved, none of them an image\n",
               ovlbox_moves - moves0);
    }

    reads0 = ovlbox_reads;
    flushes0 = ovlbox_flushes;

#ifdef OVL_LANE_EAGER
    /* The release, for StuffIt: three keeps — the decoder, the ciphers
     * (StuffIt flags encryption per entry, so the release cannot know and
     * must keep them) and always the codecs. StuffIt rather than LZH because
     * its image is the one carrying real relocations, and a KEPT image is
     * relocated a second time, by the DIFFERENCE between the copy's address
     * and the bundle's. That arithmetic is the subtlest line in either
     * loader and this is the only test of it anywhere. */
    printf("the release, for a StuffIt\n");
    ovl_release_if_unwanted(UNC_FORMAT_SIT, &io);
    CHECK(gKeepFail == 0, "a keep failed: kf=%d", (int)gKeepFail);
    CHECK(ovlbox_reads == reads0, "the release cost %ld disk read(s)",
          ovlbox_reads - reads0);
    CHECK(ovlbox_flushes == flushes0 + (getenv("OVLBOX_NO_FLUSH_ROUTE") ? 0 : 3),
          "three keeps flushed %ld time(s)", ovlbox_flushes - flushes0);
    {
        long rawlen = 0;
        unsigned char *raw = raw_image(rawdir, OVL_ID_STUFFIT, &rawlen);
        OverlayEntry e = ovl_image(OVL_ID_STUFFIT);
        CHECK(e != NULL, "the kept StuffIt image is gone");
        if (e && raw) check_relocs("kept", OVL_ID_STUFFIT,
                                   (const unsigned char *)e, raw, rawlen);
        free(raw);
        raw = raw_image(rawdir, OVL_ID_CODECS, &rawlen);
        e = ovl_image(OVL_ID_CODECS);
        CHECK(e != NULL, "the codecs image was not kept");
        if (e && raw) check_relocs("kept", OVL_ID_CODECS,
                                   (const unsigned char *)e, raw, rawlen);
        free(raw);
    }
    /* And what it gave back. A StuffIt entry may be encrypted and the
     * release cannot tell, so the ciphers STAY; every other decoder goes. */
    CHECK(ovl_image_q(OVL_ID_CRYPT, 1) != NULL,
          "the ciphers were released for a format that can carry one");
    CHECK(ovl_image_q(OVL_ID_LZH, 1) == NULL,
          "another format's decoder survived the release");
    CHECK(gWantedAfterRelease == 0,
          "the quiet form of the ask still raised the alarm (wa=%d)",
          (int)gWantedAfterRelease);
    /* The LOUD form is what the alarm is for: a decoder asking for an image
     * after the release is a defect, and the diagnostic must say so. */
    CHECK(ovl_image(OVL_ID_LZH) == NULL, "a released image came back");
    CHECK(gWantedAfterRelease == OVL_ID_LZH,
          "wa=%d after asking for a released image", (int)gWantedAfterRelease);
    CHECK(ovlbox_reads == reads0, "something re-read the resource fork");
    printf("  rf=%d wa=%d kf=%d fc=%d fn=%d\n", (int)gRelFmt,
           (int)gWantedAfterRelease, (int)gKeepFail, (int)gFlushHas,
           (int)gFlushCalls);
#else
    /* The lazy lifetime releases nothing, and its release entry point must be
     * a no-op rather than a hole: the shell calls it either way. */
    printf("the release, which this lifetime does not have\n");
    ovl_release_if_unwanted(UNC_FORMAT_LZH, &io);
    for (i = 0; i < NIDS; i++)
        CHECK(ovl_image(kIds[i]) != NULL,
              "image %d went away in a lifetime that releases nothing",
              (int)kIds[i]);
    CHECK(ovlbox_reads == reads0, "the release re-read %ld resource(s)",
          ovlbox_reads - reads0);
#endif

    printf("mock heap: %ld handle(s) live, %ld relocatable move(s)\n",
           ovlbox_handles, ovlbox_moves);

    if (gFails) {
        printf("ovl_load_test: %d FAILURE(S)\n", gFails);
        return 1;
    }
    printf("ovl_load_test: ok\n");
    return 0;
}

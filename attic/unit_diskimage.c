/*
 * attic/unit_diskimage.c — the unit tests for the retired disk-image
 * probes (attic/fmt_diskimage.c), lifted out of tests/unit_formats.c on
 * 2026-08-27. NOT BUILT: tests/ holds what ci.sh compiles, and these
 * test code that is no longer in the engine.
 *
 * Kept with the probes so that restoring them is one move rather than a
 * rewrite. Both functions were called from test_all() in
 * tests/unit_main.c, and both fail against a probe whose corroborating
 * field has been removed - each one was mutation-tested (TESTING.md's
 * "Disk images" section, also in this directory's README).
 */

/* DiskCopy 4.2 is DETECT-ONLY: unc_sniff must name it, and extraction must
 * refuse cleanly rather than pretend. The probe is deliberately strict (the
 * magic word is only 16 bits), so also check that each guard rejects. */
static void test_diskcopy(void)
{
    uint8_t h[128];
    UncIO io;
    MemIO m;
    int i;

    /* Minimal valid 800K GCR header: name, dataSize 819200, tags 19200. */
    for (i = 0; i < (int)sizeof h; i++) h[i] = 0;
    h[0] = 4;                                    /* Pascal name length */
    h[1] = 'D'; h[2] = 'i'; h[3] = 's'; h[4] = 'k';
    h[0x40] = 0x00; h[0x41] = 0x0C; h[0x42] = 0x80; h[0x43] = 0x00;  /* 819200 */
    h[0x44] = 0x00; h[0x45] = 0x00; h[0x46] = 0x4B; h[0x47] = 0x00;  /*  19200 */
    h[0x50] = 0x01;                              /* GCR CLV dsdd (800K) */
    h[0x51] = 0x22;                              /* format byte, not checked */
    h[0x52] = 0x01; h[0x53] = 0x00;              /* magic "private word" */

    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKCOPY);

    /* A tagless GCR image is equally valid. */
    h[0x44] = h[0x45] = h[0x46] = h[0x47] = 0;
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKCOPY);

    /* 1440K MFM, which can never carry tags. */
    h[0x40] = 0x00; h[0x41] = 0x16; h[0x42] = 0x80; h[0x43] = 0x00;  /* 1474560 */
    h[0x50] = 0x03;
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKCOPY);
    h[0x47] = 0x0C;                              /* ...so any tag size is wrong */
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKCOPY);
    h[0x47] = 0x00;

    /* Encoding must agree with the declared data size. */
    h[0x50] = 0x01;                              /* says 800K, size says 1440K */
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKCOPY);
    h[0x50] = 0x03;

    /* Unknown encoding, over-long Pascal name, wrong magic: all rejected. */
    h[0x50] = 0x07;
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKCOPY);
    h[0x50] = 0x03;

    h[0] = 64;
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKCOPY);
    h[0] = 4;

    h[0x53] = 0x01;
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKCOPY);
    h[0x53] = 0x00;

    /* Detect-only: it is named, but extracting it is refused cleanly. */
    {
        UncAlloc al;
        UncSink sk;
        CapSink cap;
        test_make_memio(&io, &m, h, sizeof h);
        test_make_alloc(&al);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_DISKCOPY, &io, &sk, &al, NULL, NULL)
              == UNC_ERR_UNSUPPORTED);
        CHECK(cap.count == 0);
    }
}

/* Every OTHER disk image is detect-only for the same reason. The four
 * volume structures the probe reads live past the sniff window, so each
 * case here is a buffer with something at 512, 1024 or sector 16 and
 * nothing anywhere else — which is also the point: none of these is a
 * plausible archive, and the probe must not need them to be.
 *
 * tools/run_diskimage.py is where real images are graded (an ISO written
 * by pycdlib, an HFS volume written by hformat, both confirmed by deark);
 * this is the part that runs with no reference tree at all. */
static void test_diskimage(void)
{
    uint8_t img[4096];
    uint8_t *cd;
    UncIO io;
    MemIO m;
    int i;

    /* HFS: "BD" at 1024, allocation block size a nonzero multiple of 512. */
    for (i = 0; i < (int)sizeof img; i++) img[i] = 0;
    img[1024] = 'B'; img[1025] = 'D';
    img[1044] = 0x00; img[1045] = 0x00; img[1046] = 0x20; img[1047] = 0x00;
    test_make_memio(&io, &m, img, sizeof img);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKIMAGE);

    img[1046] = 0x00; img[1047] = 0x00;              /* size 0 */
    test_make_memio(&io, &m, img, sizeof img);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKIMAGE);
    img[1047] = 0x64;                                /* 100: not a sector */
    test_make_memio(&io, &m, img, sizeof img);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKIMAGE);

    /* HFS+ and HFSX: the signature, plus a file that is whole sectors. */
    for (i = 0; i < (int)sizeof img; i++) img[i] = 0;
    img[1024] = 'H'; img[1025] = '+';
    test_make_memio(&io, &m, img, sizeof img);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKIMAGE);
    img[1025] = 'X';
    test_make_memio(&io, &m, img, sizeof img);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKIMAGE);
    test_make_memio(&io, &m, img, sizeof img - 3);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKIMAGE);
    /* ...and a volume too short to hold a header is not one either. */
    test_make_memio(&io, &m, img, 1024 + 512);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKIMAGE);
    test_make_memio(&io, &m, img, 1024);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKIMAGE);

    /* Apple Partition Map: an entry in sector 1 AND in sector 2. */
    for (i = 0; i < (int)sizeof img; i++) img[i] = 0;
    img[512] = 'P'; img[513] = 'M';
    img[1024] = 'P'; img[1025] = 'M';
    test_make_memio(&io, &m, img, sizeof img);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKIMAGE);
    img[512] = 0;                                    /* sector 1 gone */
    test_make_memio(&io, &m, img, sizeof img);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKIMAGE);
    img[512] = 'P'; img[1024] = 0;                   /* sector 2 gone */
    test_make_memio(&io, &m, img, sizeof img);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKIMAGE);
    /* The two reserved bytes are part of the signature deark matches. */
    img[1024] = 'P'; img[1025] = 'M'; img[1026] = 1;
    test_make_memio(&io, &m, img, sizeof img);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKIMAGE);

    /* ISO 9660 and its two relatives, at 2048-byte sectors: a descriptor
     * at sector 16 and another at sector 17. 36 KB is past what belongs
     * on this stack. */
    cd = (uint8_t *)malloc(36864);
    CHECK(cd != NULL);
    if (cd) {
        static const char *sig[3] = { "CD001", "CD-I ", "CDROM" };
        int k;
        for (k = 0; k < 3; k++) {
            int at = (k == 2) ? 8 : 0;               /* High Sierra is at +8 */
            int j;
            for (i = 0; i < 36864; i++) cd[i] = 0;
            for (j = 0; j < 2; j++) {
                uint8_t *d = cd + 2048 * (16 + j) + at;
                d[0] = (uint8_t)(j == 0 ? 1 : 255);  /* primary, terminator */
                for (i = 0; i < 5; i++) d[1 + i] = (uint8_t)sig[k][i];
            }
            test_make_memio(&io, &m, cd, 36864);
            CHECK(unc_sniff(&io) == UNC_FORMAT_DISKIMAGE);

            /* Sector 16 alone is not enough. */
            for (i = 0; i < 8; i++) cd[2048 * 17 + at + i] = 0;
            test_make_memio(&io, &m, cd, 36864);
            CHECK(unc_sniff(&io) != UNC_FORMAT_DISKIMAGE);
        }

        /* A descriptor type deark rejects (4..254) is rejected here too. */
        for (i = 0; i < 36864; i++) cd[i] = 0;
        for (i = 0; i < 2; i++) {
            uint8_t *d = cd + 2048 * (16 + i);
            int j;
            d[0] = 9;
            for (j = 0; j < 5; j++) d[1 + j] = (uint8_t)"CD001"[j];
        }
        test_make_memio(&io, &m, cd, 36864);
        CHECK(unc_sniff(&io) != UNC_FORMAT_DISKIMAGE);
        free(cd);
    }

    /* The raw CD layouts: 2352-byte sectors with the data 16 bytes in. */
    cd = (uint8_t *)malloc(2352 * 18);
    CHECK(cd != NULL);
    if (cd) {
        int j;
        for (i = 0; i < 2352 * 18; i++) cd[i] = 0;
        for (j = 0; j < 2; j++) {
            uint8_t *d = cd + 2352 * (16 + j) + 16;
            d[0] = (uint8_t)(j == 0 ? 1 : 255);
            for (i = 0; i < 5; i++) d[1 + i] = (uint8_t)"CD001"[i];
        }
        test_make_memio(&io, &m, cd, 2352 * 18);
        CHECK(unc_sniff(&io) == UNC_FORMAT_DISKIMAGE);
        free(cd);
    }

    /* Detect-only: named, and extraction refused cleanly. */
    {
        UncAlloc al;
        UncSink sk;
        CapSink cap;
        for (i = 0; i < (int)sizeof img; i++) img[i] = 0;
        img[1024] = 'H'; img[1025] = '+';
        test_make_memio(&io, &m, img, sizeof img);
        test_make_alloc(&al);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_DISKIMAGE, &io, &sk, &al, NULL, NULL)
              == UNC_ERR_UNSUPPORTED);
        CHECK(cap.count == 0);
        CHECK(!unc_format_extractable(UNC_FORMAT_DISKIMAGE));
    }
}

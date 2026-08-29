/*
 * fmt_foreign.c — archives this engine does NOT extract, named anyway.
 *
 * Every format here is a PC-side or modern archive: none is a Macintosh
 * format, none carries a resource fork, and each is served by a
 * maintained extractor on any machine that can run one, so extracting
 * them stays out by the brief (OPEN_ITEMS.md, part 1). Naming them does
 * not stay out, and the difference is what the user can do next.
 *
 * Somebody who opens an unarchiver is telling you they believe they have
 * an archive. "Not recognized" answers that with the one thing that is
 * both true and useless — it reads as "your file is damaged", and the
 * next move is a re-download that will not help. "This is a RAR archive"
 * says the file is fine and names the family, which is the whole of what
 * this program can honestly contribute to a file it will never open.
 * (A DISK IMAGE is the opposite case and was retired for it: see
 * attic/fmt_diskimage.c and DECISIONS.md 2026-08-27.)
 *
 * The rule for what is in this file: a magic number from a reference
 * implementation in `reference/`, and nothing invented. Four more were
 * added on 2026-08-29 once their references were fetched — and one of
 * them, lzip, had been in `reference/deark` the whole time. What is
 * still left out is AAR, for want of a reference, and **brotli, which
 * cannot be identified at all**: RFC 7932 section 9.1 is its entire
 * stream header, one to seven bits of WBITS, with no magic, no
 * signature and no version byte (OPEN_ITEMS.md, part 1). A `.zipx`
 * needs nothing: it is a zip, the zip probe claims it, and its entries
 * are refused one at a time by method.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* Every test below reads the head buffer only, at a fixed offset, and
 * returns the moment it matches: this runs on every file that reaches it
 * and a 68000 pays for each byte compared. */

static int mem_is(const uint8_t *p, const char *lit, int32_t n)
{
    int32_t i;
    for (i = 0; i < n; i++)
        if (p[i] != (uint8_t)lit[i]) return 0;
    return 1;
}

/* ARJ's is the one signature short enough to occur by accident — two
 * bytes — so it is corroborated the way XADMaster corroborates it: the
 * basic header's declared size is in range and its stored CRC-32 checks
 * out. Source: XADARJParser.m, -recognizeFileWithHandle (which scans;
 * this looks at offset 0 only, where an archive that is not a
 * self-extracting .exe keeps it) and reference/deark/modules/arj.c,
 * de_identify_arj, for the 32..2600 bounds. */
static int arj_at_zero(const uint8_t *head, int32_t len)
{
    int32_t size;

    if (len < 40) return 0;
    if (head[0] != 0x60 || head[1] != 0xea) return 0;
    size = (int32_t)unc_get_u16le(head + 2);
    if (size < 32 || size > 2600) return 0;
    if (4 + size + 4 > len) return 0;
    return unc_get_u32le(head + 4 + size) ==
           ~unc_crc32(UNC_CRC32_INIT, head + 4, size);
}

/* bzip2: "BZh" + a level digit, then either a block header or the
 * end-of-stream marker — an empty archive has no block.
 * Source: XADBzip2Parser.m, -recognizeFileWithHandle. */
static int bzip2_head(const uint8_t *h, int32_t len)
{
    if (len < 10) return 0;
    if (!(h[0] == 'B' && h[1] == 'Z' && h[2] == 'h' &&
          h[3] >= '1' && h[3] <= '9')) return 0;
    if (h[4] == 0x31 && h[5] == 0x41 && h[6] == 0x59 &&
        h[7] == 0x26 && h[8] == 0x53 && h[9] == 0x59) return 1;
    return h[4] == 0x17 && h[5] == 0x72 && h[6] == 0x45 &&
           h[7] == 0x38 && h[8] == 0x50 && h[9] == 0x90;
}

/* cpio, in the five shapes deark identifies: three ASCII magics and the
 * two byte orders of the binary one. Source:
 * reference/deark/modules/cpio.c, identify_cpio_internal. The binary
 * form is 16 bits and deark rates it 70 rather than 100 for that
 * reason; it is kept because `.cpgz` — cpio under gzip — is exactly what
 * a modern Mac makes of a folder, and the gzip layer unwraps to one. */
static int cpio_head(const uint8_t *h, int32_t len)
{
    if (len < 6) return 0;
    if (mem_is(h, "070707", 6) || mem_is(h, "070701", 6) ||
        mem_is(h, "070702", 6)) return 1;
    return (h[0] == 0xc7 && h[1] == 0x71) || (h[0] == 0x71 && h[1] == 0xc7);
}

/* The whole set, strongest magic first. Returns the format, or
 * UNC_FORMAT_UNKNOWN. */
UncFormat unc_foreign_probe(const uint8_t *head, int32_t len,
                            UncIO *io)
{
    (void)io;
    /* RAR, all three generations. 1.5-4.x and 5.x share their first
     * seven bytes and differ in the eighth, so 5 is tested first;
     * "RE~^" is RAR 1.3/1.4, which predates the signature.
     * Source: XADRARParser.m (IsRARSignature, IsAncientRARSignature)
     * and XADRAR5Parser.m (IsRAR5Signature). */
    if (len >= 8 && mem_is(head, "Rar!\x1a\x07\x01", 7) && head[7] == 0x00)
        return UNC_FORMAT_RAR5;
    if (len >= 7 && mem_is(head, "Rar!\x1a\x07\x00", 7))
        return UNC_FORMAT_RAR;
    if (len >= 4 && head[0] == 0x52 && head[1] == 0x45 &&
        head[2] == 0x7e && head[3] == 0x5e)
        return UNC_FORMAT_RAR;

    /* 7-Zip. Source: XAD7ZipParser.m, Is7ZipSignature. */
    if (len >= 32 && mem_is(head, "7z\xbc\xaf\x27\x1c", 6) && head[6] == 0x00)
        return UNC_FORMAT_7Z;

    /* xz. Source: XADXZParser.m, -recognizeFileWithHandle. */
    if (len >= 6 && head[0] == 0xfd && mem_is(head + 1, "7zXZ", 4) &&
        head[5] == 0x00)
        return UNC_FORMAT_XZ;

    if (bzip2_head(head, len)) return UNC_FORMAT_BZIP2;

    /* Microsoft Cabinet. Source: XADCABParser.m. */
    if (len >= 4 && mem_is(head, "MSCF", 4)) return UNC_FORMAT_CAB;

    /* Zoo: its magic is 32 bits, but at offset 0x14 rather than 0, so it
     * cannot collide with anything probed before it. Source:
     * XADZooParser.m and reference/deark/modules/zoo.c. */
    if (len >= 0x22 && head[0x14] == 0xdc && head[0x15] == 0xa7 &&
        head[0x16] == 0xc4 && head[0x17] == 0xfd)
        return UNC_FORMAT_ZOO;

    /* ar, which is also what a .deb is made of.
     * Source: reference/deark/modules/ar.c, de_identify_ar. */
    if (len >= 8 && mem_is(head, "!<arch>\x0a", 8)) return UNC_FORMAT_AR;

    if (cpio_head(head, len)) return UNC_FORMAT_CPIO;
    if (arj_at_zero(head, len)) return UNC_FORMAT_ARJ;

    /* Zstandard, both frame kinds: the ordinary one is magic 0xFD2FB528
     * and a stream may also OPEN with a skippable frame, whose magic is
     * any of 0x184D2A50..0x184D2A5F. Both little-endian.
     * Source: reference/notes/zstd_rfc8878.txt, sections 3.1.1 and
     * 3.1.2 (RFC 8878). */
    if (len >= 4) {
        if (head[0] == 0x28 && head[1] == 0xb5 && head[2] == 0x2f &&
            head[3] == 0xfd)
            return UNC_FORMAT_ZSTD;
        if ((head[0] & 0xf0) == 0x50 && head[1] == 0x2a &&
            head[2] == 0x4d && head[3] == 0x18)
            return UNC_FORMAT_ZSTD;
    }

    /* lrzip: "LRZI", then a major and a minor version byte, in a header
     * the writer always emits whole. The 24 is `MAGIC_LEN`, which is
     * what stops four ASCII letters in a text file from being claimed.
     * Source: reference/lrzip/lrzip.c, write_magic and get_magic. */
    if (len >= 24 && mem_is(head, "LRZI", 4)) return UNC_FORMAT_LRZIP;

    /* Microsoft's WIM. The magic is eight bytes and the header size at
     * +8 corroborates it: wimlib accepts one value, 208.
     * Source: reference/wimlib/include/wimlib/header.h, WIM_MAGIC and
     * WIM_HEADER_DISK_SIZE. */
    if (len >= 12 && mem_is(head, "MSWIM\0\0\0", 8) &&
        unc_get_u32le(head + 8) == 208u)
        return UNC_FORMAT_WIM;

    /* lzip. Four ASCII bytes and nothing to corroborate them with —
     * which is why deark, the reference, gives it a confidence of 50
     * where it gives xz and 7z 90. It is last for that reason.
     * Source: reference/deark/modules/unsupported.c, get_fmt. */
    if (len >= 4 && mem_is(head, "LZIP", 4)) return UNC_FORMAT_LZIP;

    return UNC_FORMAT_UNKNOWN;
}

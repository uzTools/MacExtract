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
 * them, lzip, had been in `reference/deark` the whole time. Apple
 * Archive joined them on 2026-09-01, once a reference was found for it
 * too. What is still left out is **brotli, which cannot be identified
 * at all**: RFC 7932 section 9.1 is its entire
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
 * bytes — so it is corroborated: the basic header's declared size is in
 * range and its stored CRC-32 checks out.
 * Source: reference/deark/modules/arj.c (MIT) — g_arj_hdr_id for the
 * two bytes, de_identify_arj for the 30..2600 bounds (deark names the
 * ARJ TECHNOTE for the ceiling) and arj_read_member for the contract
 * this checks: a CRC-32 of the basic header, stored little-endian
 * immediately after it. This looks at offset 0 only, where an archive
 * that is not a self-extracting .exe keeps it; deark's identify does
 * the same and its parser scans.
 * The bounds were XADARJParser.m's 32 and its 40-byte minimum until
 * 2026-09-27, when the file was re-cited to deark and took deark's
 * numbers with it (DECISIONS.md, *the signatures that were already on
 * the disk*). No fixture exercises this path either way. */
static int arj_at_zero(const uint8_t *head, int32_t len)
{
    int32_t size;

    if (len < 38) return 0;
    if (head[0] != 0x60 || head[1] != 0xea) return 0;
    size = (int32_t)unc_get_u16le(head + 2);
    if (size < 30 || size > 2600) return 0;
    if (4 + size + 4 > len) return 0;
    return unc_get_u32le(head + 4 + size) ==
           ~unc_crc32(UNC_CRC32_INIT, head + 4, size);
}

/* bzip2: "BZh" + a level digit, then either a block header or the
 * end-of-stream marker — an empty archive has no block.
 * Source: reference/deark/modules/unsupported.c (MIT), get_fmt, for
 * "BZh" and the block header 0x314159265359. deark does not state the
 * EMPTY form, and it needs no reference: `bzip2 -c < /dev/null` writes
 * 42 5a 68 39 17 72 45 38 50 90, measured here 2026-09-27, which is
 * the second branch byte for byte. */
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

/* Membership in a short set of bytes, as a string constant: on a 68000
 * the string is data, which is free here, where the run of comparisons
 * it replaces is code, which is not (FORMATS.md, *What the application
 * costs the engine*). Written out as such, Apple Archive's sixteen
 * field subtypes put the Macintosh build 196 B over its ceiling. */
static int in_set(const char *set, uint8_t c)
{
    while (*set)
        if ((uint8_t)*set++ == c) return 1;
    return 0;
}

/* Apple Archive, in both of its shapes. Uncompressed is "AA01" — or the
 * legacy "YAA1" it replaced, which is the same format — followed by the
 * first header's size as a little-endian 16-bit count that INCLUDES
 * those six bytes, so a value under 6 is not one; and where that header
 * carries a field, the field's subtype byte corroborates it — three
 * bytes of field name and a fourth out of a closed set of sixteen,
 * which is what stops four letters of ordinary text from being
 * claimed. A compressed archive opens "pbz" and a codec letter
 * instead.
 *
 * `pbzx` is also the payload stream inside an Apple flat package, so
 * one of those is named an Apple Archive here. That is the right answer
 * for what this file is for — the user is told which family the file
 * belongs to and that it is not damaged — and no worse than the rest of
 * the set, none of which is opened either.
 *
 * Source: reference/libNeoAppleArchive/libNeoAppleArchive/
 * libNeoAppleArchive_internal.h (AAR_MAGIC, YAA_MAGIC, PBZE_MAGIC,
 * PBZZ_MAGIC, PBZB_MAGIC) and neo_aa_header.c. The two codecs that
 * library names but does not yet write — lzma `x` and lz4 `4` — are
 * from reference/notes/Apple_Archive.md; its own
 * docs/NeoAAArchiveGeneric.md is what says they belong to the format. */
static int aar_head(const uint8_t *h, int32_t len)
{
    uint16_t hsize;

    /* 10 bytes: the six-byte prologue and the first field key. The
     * smallest archive libNeoAppleArchive will write is 71 B. */
    if (len < 10) return 0;
    if (mem_is(h, "pbz", 3)) return in_set("ezbx4", h[3]);
    if (!mem_is(h, "AA01", 4) && !mem_is(h, "YAA1", 4)) return 0;
    hsize = unc_get_u16le(h + 4);
    if (hsize < 6) return 0;
    return hsize == 6 || in_set("*1248ABCFGHIJPST", h[9]);
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
     * Source: reference/deark/modules/rar.c (MIT), rar_get_fmtver —
     * g_rar5_sig, g_rar4_sig and g_rar_oldsig, the three in that
     * order. */
    if (len >= 8 && mem_is(head, "Rar!\x1a\x07\x01", 7) && head[7] == 0x00)
        return UNC_FORMAT_RAR5;
    if (len >= 7 && mem_is(head, "Rar!\x1a\x07\x00", 7))
        return UNC_FORMAT_RAR;
    if (len >= 4 && head[0] == 0x52 && head[1] == 0x45 &&
        head[2] == 0x7e && head[3] == 0x5e)
        return UNC_FORMAT_RAR;

    /* 7-Zip. Source: reference/deark/modules/unsupported.c (MIT),
     * get_fmt. */
    if (len >= 32 && mem_is(head, "7z\xbc\xaf\x27\x1c", 6) && head[6] == 0x00)
        return UNC_FORMAT_7Z;

    /* xz. Source: reference/deark/modules/unsupported.c (MIT),
     * get_fmt, which states all six bytes. */
    if (len >= 6 && head[0] == 0xfd && mem_is(head + 1, "7zXZ", 4) &&
        head[5] == 0x00)
        return UNC_FORMAT_XZ;

    if (bzip2_head(head, len)) return UNC_FORMAT_BZIP2;

    /* Microsoft Cabinet. Source: reference/deark/modules/cab.c (MIT),
     * de_identify_cab. */
    if (len >= 4 && mem_is(head, "MSCF", 4)) return UNC_FORMAT_CAB;

    /* Zoo: its magic is 32 bits, but at offset 0x14 rather than 0, so it
     * cannot collide with anything probed before it.
     * Source: reference/deark/modules/zoo.c (MIT), de_identify_zoo,
     * which states the offset and all four bytes. */
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

    if (aar_head(head, len)) return UNC_FORMAT_AAR;

    /* lzip. Four ASCII bytes and nothing to corroborate them with —
     * which is why deark, the reference, gives it a confidence of 50
     * where it gives xz and 7z 90. It is last for that reason.
     * Source: reference/deark/modules/unsupported.c, get_fmt. */
    if (len >= 4 && mem_is(head, "LZIP", 4)) return UNC_FORMAT_LZIP;

    return UNC_FORMAT_UNKNOWN;
}

/*
 * neoaa_write.c — write an Apple Archive with libNeoAppleArchive, then
 * read it back with the same library.
 *
 * This is the oracle for the Apple Archive probe (FORMATS.md, *Archives
 * named but not extracted*). It is the same tier as bzip2, xz and 7z in
 * tools/run_foreign.py: the subject is written by an implementation that
 * is not ours, and parsed again by that implementation before the probe
 * is asked about it, so a specimen the probe rejects is known to be a
 * real archive rather than a header this repository invented.
 *
 * Built by tools/build_neoaa.sh; not part of the engine, and not
 * compiled by ci.sh's build. License: LGPL-2.1-or-later (the library it
 * links is MIT).
 *
 * Usage: neoaa_write <input-dir> <output-file> raw|lzfse|zlib|lzbitmap
 */
#include <stdio.h>
#include <string.h>
#include <libNeoAppleArchive.h>

int main(int argc, char **argv)
{
    NeoAAArchivePlain plain;
    NeoAAArchiveGeneric back;
    const char *algo;

    if (argc != 4) {
        fprintf(stderr, "usage: %s <dir> <out> raw|lzfse|zlib|lzbitmap\n",
                argv[0]);
        return 2;
    }
    algo = argv[3];

    plain = neo_aa_archive_plain_from_directory(argv[1]);
    if (!plain) {
        fprintf(stderr, "neoaa_write: cannot read %s\n", argv[1]);
        return 1;
    }
    if (!strcmp(algo, "raw"))
        neo_aa_archive_plain_write_path(plain, argv[2]);
    else if (!strcmp(algo, "lzfse"))
        neo_aa_archive_plain_compress_write_path(plain,
            NEO_AA_COMPRESSION_LZFSE, argv[2]);
    else if (!strcmp(algo, "zlib"))
        neo_aa_archive_plain_compress_write_path(plain,
            NEO_AA_COMPRESSION_ZLIB, argv[2]);
    else if (!strcmp(algo, "lzbitmap"))
        neo_aa_archive_plain_compress_write_path(plain,
            NEO_AA_COMPRESSION_LZBITMAP, argv[2]);
    else {
        fprintf(stderr, "neoaa_write: unknown algorithm %s\n", algo);
        return 2;
    }

    /* Read it back with the writer's own reader. Without this the tool
     * would only prove that it wrote SOMETHING. */
    back = neo_aa_archive_generic_from_path(argv[2]);
    if (!back) {
        fprintf(stderr, "neoaa_write: %s does not read back as an "
                        "Apple Archive\n", argv[2]);
        return 1;
    }
    return 0;
}

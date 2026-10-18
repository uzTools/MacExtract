#!/bin/sh
# build_neoaa.sh — build libNeoAppleArchive out of the read-only
# reference/ tree, plus tools/neoaa_write.c, to get an Apple Archive
# WRITER on this machine. Nothing under reference/ is modified.
#
# WHY. Apple Archive is out of scope (OPEN_ITEMS.md, part 1), and since
# 2026-10-18 the engine does not recognise it either: tools/run_foreign.py
# requires a real one to sniff as unknown and extract nothing. A header
# this repository built would only prove that about our own reading of
# the format. This library writes real archives in four shapes: raw
# `AA01` and the `pbze`/`pbzz`/`pbzb` codecs.
#
# libNeoAppleArchive's own Makefile wants clang, homebrew's openssl and
# an install step; none of that is needed for the writer, so the three
# core sources are compiled here directly with EXCLUDE_AEA_SUPPORT=1.
# The two compression submodules come from the same clone.
#
# Usage: sh tools/build_neoaa.sh [--force]
# Prints the path of the binary on stdout.
set -e
cd "$(dirname "$0")/.."

SRC=reference/libNeoAppleArchive/libNeoAppleArchive
OUT=build/neoaa
BIN=$OUT/neoaa_write

if [ "$1" != "--force" ] && [ -x "$BIN" ]; then
    echo "$BIN"
    exit 0
fi

[ -d "$SRC/compression/lzfse/src" ] || {
    echo "build_neoaa: $SRC is missing or has no submodules; run" >&2
    echo "  tools/fetch_references.sh, then git -C" \
         "reference/libNeoAppleArchive submodule update --init --depth 1" >&2
    exit 1
}

rm -rf "$OUT"
mkdir -p "$OUT"
INC="-I$SRC -I$SRC/compression/lzfse/src -I$SRC/compression/libzbitmap"

for f in "$SRC"/neo_aa_header.c \
         "$SRC"/libNeoAppleArchive_internal.c \
         "$SRC"/libNeoAppleArchive.c \
         "$SRC"/compression/libzbitmap/libzbitmap.c \
         "$SRC"/compression/lzfse/src/lzfse_decode.c \
         "$SRC"/compression/lzfse/src/lzfse_decode_base.c \
         "$SRC"/compression/lzfse/src/lzfse_encode.c \
         "$SRC"/compression/lzfse/src/lzfse_encode_base.c \
         "$SRC"/compression/lzfse/src/lzfse_fse.c \
         "$SRC"/compression/lzfse/src/lzvn_decode_base.c \
         "$SRC"/compression/lzfse/src/lzvn_encode_base.c; do
    ${CC:-cc} -c "$f" -o "$OUT/$(basename "$f" .c).o" \
        -O1 -DEXCLUDE_AEA_SUPPORT=1 $INC -w
done

${CC:-cc} -O1 -w $INC tools/neoaa_write.c "$OUT"/*.o -o "$BIN" -lz

[ -x "$BIN" ] || { echo "build_neoaa: build produced no binary" >&2; exit 1; }
echo "$BIN"

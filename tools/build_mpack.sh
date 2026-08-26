#!/bin/sh
# build_mpack.sh — build munpack out of the read-only reference/ tree,
# for use as the second implementation the MIME suite grades against
# (TESTING.md, "base64 and MIME"). Nothing under reference/ is modified:
# the tree is copied to build/mpack/ and built there.
#
# WHY MUNPACK. mpack/munpack 1.6 (John G. Myers, CMU) is the program the
# format came with, and its own tree holds the Macintosh port that wrote
# multipart/appledouble in the first place. src/fmt_mime.c is
# transcribed from its decode.c and part.c; this builds the same source
# as a DECODER, so a message our engine reads has to come out of both
# the same way.
#
# What it cannot check is the resource fork: the Unix munpack has no
# notion of one, and writes an application/applefile part as an opaque
# file — TESTING.md says what covers that instead.
#
# The source is 1994 K&R C and modern gcc rejects its configure probe
# ("main(){return(0);}" has no return type), so the compiler is pinned
# to gnu89 with warnings off. reference/ stays untouched either way.
#
# Usage: sh tools/build_mpack.sh [--force]
# Prints the path of the binary on stdout.
set -e
cd "$(dirname "$0")/.."

SRC=reference/mpack
OUT=build/mpack
BIN=$OUT/munpack

if [ "$1" != "--force" ] && [ -x "$BIN" ]; then
    echo "$BIN"
    exit 0
fi

[ -d "$SRC" ] || {
    echo "build_mpack: $SRC is missing; run tools/fetch_references.sh" >&2
    exit 1
}

rm -rf "$OUT"
mkdir -p build
cp -r "$SRC" "$OUT"
(cd "$OUT" && CC="gcc -std=gnu89 -w" ./configure --quiet >/dev/null 2>&1 \
           && make >/dev/null 2>&1)

[ -x "$BIN" ] || { echo "build_mpack: build produced no binary" >&2; exit 1; }
echo "$BIN"

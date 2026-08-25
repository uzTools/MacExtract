#!/bin/sh
# build_deark.sh — build deark out of the read-only reference/ tree, for
# use as the oracle for ARC/PAK method 0x0b (TESTING.md, "A second
# oracle"). Nothing under reference/ is modified: the tree is copied to
# build/deark/ and built there.
#
# WHY A THIRD ORACLE. `unar` is this project's primary oracle and it is
# WRONG about Distilled: it starts the 8 KB window at zero where PAK
# fills it with spaces, so every match reaching back past the start of
# the data decodes to the wrong bytes at the right length — 6 of the 10
# members of one real archive (BLOCKERS.md). deark is an independent
# implementation and agrees with the CRC PAK itself stored, on all 21
# Distilled members in reach. It does NOT implement Crushed, so it
# replaces `unar` for one method rather than in general.
#
# deark needs nothing but a C compiler and make.
#
# Usage: sh tools/build_deark.sh [--force]
# Prints the path of the binary on stdout.
set -e
cd "$(dirname "$0")/.."

SRC=reference/deark
OUT=build/deark
BIN=$OUT/deark

if [ "$1" != "--force" ] && [ -x "$BIN" ]; then
    echo "$BIN"
    exit 0
fi

[ -d "$SRC" ] || {
    echo "build_deark: $SRC is missing; run tools/fetch_references.sh" >&2
    exit 1
}

rm -rf "$OUT"
mkdir -p build
cp -r "$SRC" "$OUT"
(cd "$OUT" && make >/dev/null 2>&1)

[ -x "$BIN" ] || { echo "build_deark: build produced no binary" >&2; exit 1; }
echo "$BIN"

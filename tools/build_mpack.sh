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
# -p, and it is load-bearing: this tree ships a generated Makefile.in that is
# ten minutes NEWER than the Makefile.am it came from (2003-07-21 23:49 against
# 23:39), which is what stops automake's maintainer rule
#
#     $(srcdir)/Makefile.in: Makefile.am $(top_srcdir)/configure.in ...
#             cd $(top_srcdir) && $(AUTOMAKE) --foreign ...
#
# from ever firing. A plain `cp -r` discards those dates and stamps every file
# with the current time, so whether Makefile.am lands newer than Makefile.in
# comes down to which side of a clock tick each one is written on. When it does,
# make runs automake 1.17 over a 1994 tree and dies with "required file
# './depcomp' not found", Error 63 — silently, because both the configure and
# the make below are redirected. Measured 2026-09-09: 3 failures in 8 runs
# without -p, 0 in 40 with it (DECISIONS.md 2026-09-09, the oracle that built
# two times in three).
cp -pR "$SRC" "$OUT"
# Kept, and shown on failure. Both halves used to go to /dev/null, so the
# timestamp defect above produced a silent exit 2 and tools/run_mime.py
# reported it as a missing reference tree — which it then SKIPPED over,
# green (DECISIONS.md 2026-09-09).
LOG=$OUT.log
if ! (cd "$OUT" && CC="gcc -std=gnu89 -w" ./configure --quiet && make) \
        >"$LOG" 2>&1; then
    echo "build_mpack: the build failed. Last lines of $LOG:" >&2
    tail -20 "$LOG" >&2
    exit 1
fi

[ -x "$BIN" ] || {
    echo "build_mpack: the build reported success and produced no binary." >&2
    echo "build_mpack: last lines of $LOG:" >&2
    tail -20 "$LOG" >&2
    exit 1
}
echo "$BIN"

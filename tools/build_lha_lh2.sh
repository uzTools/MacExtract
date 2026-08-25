#!/bin/sh
# build_lha_lh2.sh — fetch the LHa that decodes -lh2-, so it can WRITE one.
#
# LZH's -lh2- and -lh3- were the two methods this project could not grade:
# no corpus archive uses either, lhasa has no decoder for them, and the LHa
# in reference/ carries the coders without ever selecting them. The
# maintained fork (jca02266/lha) DOES decode both — and, like everything
# else, cannot write either, which is what kept -lh2- out of scope.
#
# So this fetches that fork's source into reference/ (pristine, sha-pinned,
# never modified in place) and tools/run_lzh.py builds it on demand with
# tools/lha-lh2/lh2-encoder.patch applied — the mirror of its own
# decode_p_dyn, plus the schedule the position tree grows on. Archives it
# writes are verified by ITS OWN decoder before this engine reads one.
#
#   sh tools/build_lha_lh2.sh     # fetch the source, once
#   python3 tools/run_lzh.py ...  # builds it and grades -lh2-
#
# The source lives in reference/ and the build in build/, deliberately:
# ci.sh's `make clean` empties build/, and an encoder that vanished there
# took the -lh2- grading with it silently.
set -e
cd "$(dirname "$0")/.."

# Pinned to a COMMIT, not a branch or a release: the 2021 release predates
# this tree's own fixes for modern compilers and segfaults while encoding,
# and a branch name is not a version.
REV=16619b066b189ef289bb8b07b37d1c38d550da99
SHA=171cb8bc09ee9610b09d7366ed5e5459972d790937fbcce385e7cb89d1910226
TAR=reference/lha-lh2-$REV.tar.gz

if [ -f "$TAR" ] && echo "$SHA  $TAR" | sha256sum -c - >/dev/null 2>&1; then
    echo "lha-lh2: have $TAR"
    exit 0
fi

mkdir -p reference
echo "lha-lh2: fetching $REV"
curl -fsSL --max-time 240 -o "$TAR.part" \
    "https://codeload.github.com/jca02266/lha/tar.gz/$REV" || {
    echo "lha-lh2: fetch failed — the -lh2- cases will be skipped" >&2
    rm -f "$TAR.part"; exit 1; }
echo "$SHA  $TAR.part" | sha256sum -c - >/dev/null || {
    echo "lha-lh2: SHA-256 mismatch — verify it by hand before trusting it" >&2
    rm -f "$TAR.part"; exit 1; }
mv "$TAR.part" "$TAR"
echo "lha-lh2: have $TAR — tools/run_lzh.py builds the encoder from it"

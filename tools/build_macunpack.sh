#!/bin/sh
# build_macunpack.sh — build macutils' `macunpack` out of the read-only
# reference/ tree, for use as the SECOND oracle (TESTING.md, "A second
# oracle"). Nothing under reference/ is modified: the tree is copied to
# build/macunpack/ and the copy is patched.
#
# Two build fixes are applied, neither of which changes what the code
# does:
#   1. lzh.c declares six objects `static` after lzh.h declared them
#      `extern`, which C99 compilers reject (macunpack's own lzh, not a
#      format we read).
#   2. crc/makefile links makecrc with a literal `cc`, ignoring $(CC),
#      which breaks a cross-width build.
#
# -m32 IS NOT A PREFERENCE. util.c's get4() returns `unsigned long` and
# sit.c assigns it to a `long`, so the sign test that selects a STORED
# method-6 segment is only reachable while long is 32 bits. Built LP64,
# macunpack reads a stored segment as an enormous Huffman segment and
# dies with "Premature EOF" — i.e. the oracle silently loses the exact
# branch tools/synth_sit6.py exists to adjudicate. Measured 2026-08-08.
#
# Usage: sh tools/build_macunpack.sh [--force]
# Prints the path of the binary on stdout.
set -e
cd "$(dirname "$0")/.."

SRC=reference/macutils
OUT=build/macunpack
BIN=$OUT/macunpack/macunpack

if [ "$1" != "--force" ] && [ -x "$BIN" ]; then
    echo "$BIN"
    exit 0
fi

[ -d "$SRC" ] || {
    echo "build_macunpack: $SRC is missing; run tools/fetch_references.sh" >&2
    exit 1
}
echo 'int main(void){return 0;}' | cc -m32 -x c - -o /tmp/m32probe$$ 2>/dev/null || {
    echo "build_macunpack: no -m32 toolchain; see the note above" >&2
    exit 1
}
rm -f /tmp/m32probe$$

rm -rf "$OUT"
mkdir -p build
cp -r "$SRC" "$OUT"

sed -i \
    -e 's/^static int lzh_fsize;/int lzh_fsize;/' \
    -e 's/^static int lzh_kind;/int lzh_kind;/' \
    -e 's/^static char \*lzh_file;/char *lzh_file;/' \
    -e 's/^static char \*lzh_data;/char *lzh_data;/' \
    -e 's/^static char \*lzh_finfo;/char *lzh_finfo;/' \
    -e 's/^static char \*lzh_pointer;/char *lzh_pointer;/' \
    "$OUT/macunpack/lzh.c"
sed -i 's|^\tcc -O -o makecrc makecrc.o|\t$(CC) $(CFLAGS) -o makecrc makecrc.o|' \
    "$OUT/crc/makefile"

(cd "$OUT" && make CC=cc \
    CF="-m32 -DBSD -DTYPES_H -DDIRENT_H -DTERMIOS_H -DNODOT -std=gnu89 -w -fcommon -O1" \
    >/dev/null 2>&1)

[ -x "$BIN" ] || { echo "build_macunpack: build produced no binary" >&2; exit 1; }
echo "$BIN"

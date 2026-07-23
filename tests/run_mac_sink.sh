#!/bin/sh
# run_mac_sink.sh — exercise the ACTUAL Mac shell sink/allocator/io
# code (mac/unclassic_mac.c) against the real engine on Linux, through
# a mock Toolbox (tests/mac_sink_test.c). Catches memory/endianness
# bugs in the Mac glue that the Linux CLI's own sink never touches.
#
#   1. native x86-64 under ASan+UBSan (fast, LE 64-bit)
#   2. big-endian m68k under qemu-m68k (the real target's endianness/
#      word size), when the cross-toolchain is available — skipped
#      gracefully otherwise.
#
# Output is compared byte-for-byte (both forks) against the committed
# oracle manifests, like the main differential suite.
set -e
cd "$(dirname "$0")/.."

# A spread of fixtures: different StuffIt methods, a CPT with nested
# folders, an Arsenic SIT5 (big block), a resource-only entry.
FIXTURES="derived-ASCbeep.sit derived-apple.art.sit alpha401.cpt \
          derived-Compact_Pro_Package derived-resforkkiller.sit \
          derived-PackIt.pit synth-exo-tar.tar"

verify() {  # <runner...> ; reads $FIXTURES
    runner="$1"
    mode="$2"   # empty = file-backed mio_*; "ram" = slurp-to-RAM xio_* path
    for fx in $FIXTURES; do
        [ -f "fixtures/$fx" ] || continue
        [ -f "fixtures/manifests/$fx.json" ] || continue
        out="$(mktemp -d)"
        $runner "fixtures/$fx" "$out" $mode >/dev/null 2>&1 || {
            echo "mac-sink: FAILED extracting $fx"; rm -rf "$out"; return 1; }
        python3 tools/check_mac_sink.py "fixtures/manifests/$fx.json" "$out" || {
            rm -rf "$out"; return 1; }
        rm -rf "$out"
    done
}

echo "mac-sink: native x86-64 (ASan+UBSan)"
gcc -std=gnu99 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all \
    -Iinclude -Isrc -Ithird_party/zlib \
    tests/mac_sink_test.c src/*.c third_party/zlib/*.c -o build/mac_sink_asan
verify ./build/mac_sink_asan
verify ./build/mac_sink_asan ram   # exercise the Mac app's RAM-slurp/xio_* path
echo "mac-sink: native OK (file + RAM paths)"

if command -v m68k-linux-gnu-gcc >/dev/null 2>&1 && command -v qemu-m68k >/dev/null 2>&1; then
    echo "mac-sink: big-endian m68k (qemu)"
    m68k-linux-gnu-gcc -std=gnu99 -O2 -static -mcpu=68000 \
        -Iinclude -Isrc -Ithird_party/zlib \
        tests/mac_sink_test.c src/*.c third_party/zlib/*.c -o build/mac_sink_m68k
    verify "qemu-m68k build/mac_sink_m68k"
    verify "qemu-m68k build/mac_sink_m68k" ram
    echo "mac-sink: m68k big-endian OK (file + RAM paths)"
else
    echo "mac-sink: m68k cross-toolchain absent, skipping big-endian check"
fi

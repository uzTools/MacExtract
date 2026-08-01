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

# Two-fork files (non-empty data AND resource fork) — the case where the
# data and resource paths can disagree, so every write variant is proven
# byte-exact against these as well as against $FIXTURES.
BOTHFORK_FIXTURES="3d_windows.sea.bin compact-pro-134.bin \
                   ACInfo_Comm.sit.bin bitmap11.sit.bin"

verify() {  # <runner...> [mode] [fixture-list] ; defaults to $FIXTURES
    runner="$1"
    mode="$2"        # empty = file-backed mio_*; "ram" = slurp-to-RAM xio_*
    list="${3:-$FIXTURES}"
    for fx in $list; do
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
# Cmd-. / per-entry-error cleanup: sink_end must delete the file an aborted
# entry created in sink_begin (no partial output left behind).
./build/mac_sink_asan --cancel "$(mktemp -d)" || { echo "mac-sink: cancel-cleanup FAILED"; exit 1; }
echo "mac-sink: native OK (file + RAM paths + cancel cleanup)"

# The alternative write path. The default streams each chunk straight to the
# File Manager; UNC_MAC_STAGE_WRITES accumulates whole forks in RAM and writes
# them in sink_end, which is what the shell used to do. Both must be
# byte-exact, and the staging path has two sub-variants of its own
# (UNC_MAC_FORCE_SHAREBUF packs both forks into one block).
echo "mac-sink: native x86-64, staging write path (+ shared block)"
gcc -std=gnu99 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all \
    -DUNC_MAC_STAGE_WRITES -Iinclude -Isrc -Ithird_party/zlib \
    tests/mac_sink_test.c src/*.c third_party/zlib/*.c -o build/mac_sink_stage
verify ./build/mac_sink_stage
verify ./build/mac_sink_stage "" "$BOTHFORK_FIXTURES"
./build/mac_sink_stage --cancel "$(mktemp -d)" || {
    echo "mac-sink: staging cancel-cleanup FAILED"; exit 1; }
gcc -std=gnu99 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all \
    -DUNC_MAC_STAGE_WRITES -DUNC_MAC_FORCE_SHAREBUF \
    -Iinclude -Isrc -Ithird_party/zlib \
    tests/mac_sink_test.c src/*.c third_party/zlib/*.c -o build/mac_sink_sharebuf
verify ./build/mac_sink_sharebuf "" "$BOTHFORK_FIXTURES"
verify ./build/mac_sink_sharebuf ram "$BOTHFORK_FIXTURES"
echo "mac-sink: staging + shared-block OK (both forks byte-exact)"

if command -v m68k-linux-gnu-gcc >/dev/null 2>&1 && command -v qemu-m68k >/dev/null 2>&1; then
    # NOTE on the 68000 alignment guarantee: qemu-m68k's default CPU is
    # 68020+, which silently tolerates unaligned access, so it does NOT
    # prove 68000 alignment. `qemu-m68k -cpu m68000` DOES fault on unaligned
    # access (address error) like real hardware, but the prebuilt static
    # m68k-linux-gnu libc is compiled for 68020+ and its memcpy/memset do
    # unaligned block moves, so -cpu m68000 aborts inside libc (false
    # positive) before reaching our code. The engine's own multi-byte reads
    # all go through byte-wise big-endian helpers, so alignment is enforced
    # mechanically by the native `-fsanitize=alignment` build (ci.sh variant
    # 1) and holds by construction; on the real Mac, Retro68's libc is
    # 68000-clean. qemu here therefore checks big-endian/32-bit word size,
    # and Mini vMac in Plus config is the real-runtime 68000 oracle.
    echo "mac-sink: big-endian m68k (qemu)"
    m68k-linux-gnu-gcc -std=gnu99 -O2 -static -mcpu=68000 \
        -Iinclude -Isrc -Ithird_party/zlib \
        tests/mac_sink_test.c src/*.c third_party/zlib/*.c -o build/mac_sink_m68k
    verify "qemu-m68k build/mac_sink_m68k"
    verify "qemu-m68k build/mac_sink_m68k" ram
    echo "mac-sink: m68k big-endian OK (file + RAM paths)"
    verify "qemu-m68k build/mac_sink_m68k" "" "$BOTHFORK_FIXTURES"
    m68k-linux-gnu-gcc -std=gnu99 -O2 -static -mcpu=68000 \
        -DUNC_MAC_STAGE_WRITES -DUNC_MAC_FORCE_SHAREBUF \
        -Iinclude -Isrc -Ithird_party/zlib \
        tests/mac_sink_test.c src/*.c third_party/zlib/*.c -o build/mac_sink_sb68
    verify "qemu-m68k build/mac_sink_sb68" "" "$BOTHFORK_FIXTURES"
    echo "mac-sink: m68k both write paths OK (both forks byte-exact)"
else
    echo "mac-sink: m68k cross-toolchain absent, skipping big-endian check"
fi

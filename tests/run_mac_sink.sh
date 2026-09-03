#!/bin/sh
# run_mac_sink.sh — exercise the ACTUAL Mac shell sink/allocator/io
# code (mac/macextract_mac.c) against the real engine on Linux, through
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
# folders, an Arsenic SIT5 (big block), a resource-only entry, and a THINK C
# project holding both "X" and a real "X.rsrc" — two files that only collide
# if the sidecar convention makes them (2026-08-08), and the two archives in
# the corpus that carry an archive COMMENT, which the shell writes out as a
# document of its own: a Compact Pro Note (2026-08-23) and the one zip whose
# end-of-central-directory comment is 495 bytes, twice what a Note can hold
# (2026-08-26).
FIXTURES="derived-ASCbeep.sit derived-apple.art.sit alpha401.cpt \
          derived-Compact_Pro_Package derived-resforkkiller.sit \
          derived-PackIt.pit synth-exo-tar.tar derived-Unzip101.sit \
          derived-BootTime.cpt derived-DigSim_RAM_Circuit.cpt \
          derived-MUSFMT10.ZIP"

# Two-fork files (non-empty data AND resource fork) — the case where the
# data and resource paths can disagree, so every write variant is proven
# byte-exact against these as well as against $FIXTURES.
BOTHFORK_FIXTURES="3d_windows.sea.bin compact-pro-134.bin \
                   ACInfo_Comm.sit.bin bitmap11.sit.bin"

# Multi-entry archives across four container families, including one with
# nested folders (an unticked FOLDER entry is still created when a ticked
# entry inside it needs it) and one with an archive comment.
SELECT_FIXTURES="derived-Unzip101.sit derived-resforkkiller.sit \
                 derived-PackIt.pit synth-exo-tar.tar \
                 derived-BootTime.cpt derived-DigSim_RAM_Circuit.cpt \
                 derived-MUSFMT10.ZIP derived-Compact_Pro_Package"

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
# The figure the low-memory alert quotes. UI cannot be tested here; the
# arithmetic behind it can, and it is the half that can go wrong quietly.
./build/mac_sink_asan --shortfall || { echo "mac-sink: shortfall FAILED"; exit 1; }
# What the shell does to a name HFS cannot take as it stands: 31 characters
# per component, and the collision that cutting creates numbered ~1. Its
# own code, and until 2026-08-28 it had no test — the subjects are
# generated, because no fixture reaches either cap (TESTING.md).
python3 tools/run_macnames.py --sink ./build/mac_sink_asan || {
    echo "mac-sink: name-shortening FAILED"; exit 1; }
# Selective extraction: the entries that were ticked, and no others.
# Graded as two halves — even-numbered entries and odd-numbered ones —
# which must be disjoint and together byte-for-byte the whole archive.
# Neither "extracted everything" nor "extracted nothing" can pass that,
# which is the point: the skip is one `return` and its failure mode is
# silence. Archives of one entry are skipped (exit 2), because one entry
# is not a choice and the shell does not offer the box for it.
select_check() {
    for fx in $SELECT_FIXTURES; do
        [ -f "fixtures/$fx" ] || continue
        a="$(mktemp -d)"; e="$(mktemp -d)"; o="$(mktemp -d)"
        "$1" "fixtures/$fx" "$a" >/dev/null 2>&1
        "$1" --select even "fixtures/$fx" "$e" >/dev/null 2>&1
        case $? in
            0) ;;
            2) rm -rf "$a" "$e" "$o"; continue ;;
            *) echo "mac-select: FAILED listing $fx"; return 1 ;;
        esac
        "$1" --select odd "fixtures/$fx" "$o" >/dev/null 2>&1 || {
            echo "mac-select: FAILED extracting the odd half of $fx"
            return 1; }
        printf '%s: ' "$fx"
        python3 tools/check_mac_select.py "$a" "$e" "$o" || {
            rm -rf "$a" "$e" "$o"; return 1; }
        rm -rf "$a" "$e" "$o"
    done
}
select_check ./build/mac_sink_asan || { echo "mac-sink: selection FAILED"; exit 1; }

echo "mac-sink: native OK (file + RAM paths + cancel cleanup + shortfall + names)"

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
    # And the unit tests, for the one part of the engine no fixture
    # reaches on this machine: the ciphers. Their vectors come from
    # openssl and python (tools/check_crypt.py), they are full of 32-bit
    # rotations and byte-order assumptions, and nothing else runs them
    # anywhere but little-endian x86.
    m68k-linux-gnu-gcc -std=gnu99 -O2 -static -mcpu=68000 \
        -Iinclude -Isrc -Ithird_party/zlib \
        tests/unit_main.c src/*.c third_party/zlib/*.c -o build/unit_m68k
    qemu-m68k build/unit_m68k
    echo "mac-sink: m68k unit tests OK (the cipher vectors included)"
else
    echo "mac-sink: m68k cross-toolchain absent, skipping big-endian check"
fi

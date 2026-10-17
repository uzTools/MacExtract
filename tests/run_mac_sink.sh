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
          derived-MUSFMT10.ZIP ddtf-dd377ad.dd derived-800saywhat301j.sit \
          synth-sit14.sit synth-sqp-forks.pkg \
          synth-exo-zip-implode.zip"

# `synth-exo-zip-implode.zip` was added 2026-10-07 with zip method 6, and
# it is the only big-endian run that decoder gets: the two wild Implode
# fixtures are PC software with no forks and have never been in this lane,
# and the one Macintosh Implode archive is a specimen that cannot be
# committed. Every multi-byte field it reads — the Shannon-Fano trees, the
# distance operand assembled from two pieces, the dictionary index — is
# read bit-wise or byte-wise, so an endianness mistake would show here and
# in `tests/run_overlay_host.sh`, which derives its oracle list from this
# one and therefore runs it through the real `'OVLY'` loader as well
# (FORMATS.md, *Implode*).
#
# `synth-sqp-forks.pkg` was added 2026-10-05 with AppleLink packages. It is
# the two-fork case: a member with both forks, one with only a resource fork
# and one with only a data fork, which is what makes it the right one here —
# this lane is the Mac shell's own fork writer, big-endian, under qemu-m68k.
# Every multi-byte field in that container is read byte-wise, so an endianness
# mistake in it would show here and nowhere else in `ci.sh`.

# `synth-sit14.sit` was added 2026-10-03 with StuffIt method 14, whose two
# real subjects are multi-megabyte installers no suite can hold (TESTING.md,
# *StuffIt method 14*). This is the only lane that runs that decoder
# BIG-ENDIAN, under qemu-m68k, which is the target it was written for.

# `derived-800saywhat301j.sit` was added 2026-09-22 with the UTF-8 fold. Its
# three Japanese names have no MacRoman spelling at all, so the shell writes a
# row of '_' for each; until it joined this list no ARCHIVE exercised the fold
# anywhere but on an emulator, and `mac_sink_test.c --utf8` drives the shell
# through sink_begin without an engine in front of it. Two of its names are
# stored DECOMPOSED, which is what makes the count of '_' an assertion rather
# than a formality (tools/check_mac_sink.py, macpath()).
#
# `ddtf-dd377ad.dd` was added 2026-09-22 with the DDAR walk: this list had
# no DiskDoubler archive in it at all, so the one container walk that steps
# by a length the record states — and which changed that day — had never run
# big-endian. Seven entries, both forks each, and the header trailer shape
# (docs/formats/diskdoubler-container.md).

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
        python3 tools/check_mac_sink.py "fixtures/manifests/$fx.json" "$out" \
                "fixtures/$fx" || { rm -rf "$out"; return 1; }
        rm -rf "$out"
    done
}

# ---- the six compiles, launched together ------------------------------------
#
# Each of these is a whole-program build of the engine -- 54 translation units
# in one gcc -- and run one after another they were 115 s of a 24-minute ci.sh,
# most of it with one of this machine's two cores idle. They are independent of
# each other and of every check below, so they are started here and waited for
# immediately before the binary each one produces is used: a failed compile
# still stops the lane that needs it, and the failure still names that lane
# (DECISIONS.md 2026-10-06, *the twenty-four minutes*).
mkdir -p build
if command -v m68k-linux-gnu-gcc >/dev/null 2>&1 \
   && command -v qemu-m68k >/dev/null 2>&1; then
    HAVE_M68K=yes
else
    HAVE_M68K=no
fi

gcc -std=gnu99 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all \
    -Iinclude -Isrc -Ithird_party/zlib \
    tests/mac_sink_test.c src/*.c third_party/zlib/*.c -o build/mac_sink_asan &
pid_asan=$!
gcc -std=gnu99 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all \
    -DUNC_MAC_STAGE_WRITES -Iinclude -Isrc -Ithird_party/zlib \
    tests/mac_sink_test.c src/*.c third_party/zlib/*.c -o build/mac_sink_stage &
pid_stage=$!
gcc -std=gnu99 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all \
    -DUNC_MAC_STAGE_WRITES -DUNC_MAC_FORCE_SHAREBUF \
    -Iinclude -Isrc -Ithird_party/zlib \
    tests/mac_sink_test.c src/*.c third_party/zlib/*.c -o build/mac_sink_sharebuf &
pid_sharebuf=$!
if [ "$HAVE_M68K" = yes ]; then
    m68k-linux-gnu-gcc -std=gnu99 -O2 -static -mcpu=68000 \
        -Iinclude -Isrc -Ithird_party/zlib \
        tests/mac_sink_test.c src/*.c third_party/zlib/*.c -o build/mac_sink_m68k &
    pid_m68k=$!
    m68k-linux-gnu-gcc -std=gnu99 -O2 -static -mcpu=68000 \
        -DUNC_MAC_STAGE_WRITES -DUNC_MAC_FORCE_SHAREBUF \
        -Iinclude -Isrc -Ithird_party/zlib \
        tests/mac_sink_test.c src/*.c third_party/zlib/*.c -o build/mac_sink_sb68 &
    pid_sb68=$!
    m68k-linux-gnu-gcc -std=gnu99 -O2 -static -mcpu=68000 \
        -Iinclude -Isrc -Ithird_party/zlib \
        tests/unit_main.c src/*.c third_party/zlib/*.c -o build/unit_m68k &
    pid_unit68=$!
fi

echo "mac-sink: native x86-64 (ASan+UBSan)"
wait $pid_asan || { echo "mac-sink: native ASan build FAILED"; exit 1; }
verify ./build/mac_sink_asan
verify ./build/mac_sink_asan ram   # exercise the Mac app's RAM-slurp/xio_* path
# Cmd-. / per-entry-error cleanup: sink_end must delete the file an aborted
# entry created in sink_begin (no partial output left behind).
./build/mac_sink_asan --cancel "$(mktemp -d)" || { echo "mac-sink: cancel-cleanup FAILED"; exit 1; }
# The figure the low-memory alert quotes. UI cannot be tested here; the
# arithmetic behind it can, and it is the half that can go wrong quietly.
./build/mac_sink_asan --shortfall || { echo "mac-sink: shortfall FAILED"; exit 1; }
# Every metadata field the shell writes — Finder info, extended Finder info,
# backup date, comment, lock, and a folder's date kept across what is
# written inside it — each with a control in which the mock drops that
# write and the check must fail (DECISIONS.md 2026-10-17).
./build/mac_sink_asan --meta "$(mktemp -d)" || { echo "mac-sink: meta FAILED"; exit 1; }
# Folder dates through the one-entry cache, in the three orders the review
# named: a subfolder between a folder's files, a folder entry after its
# files, a failed entry's delete (DECISIONS.md 2026-10-17, *the date held
# once per folder*).
./build/mac_sink_asan --dirdates "$(mktemp -d)" || { echo "mac-sink: dirdates FAILED"; exit 1; }
# The time left in the progress dialog: it must not go back up while the
# rate holds (DECISIONS.md 2026-10-16, *the estimate that went back up*).
./build/mac_sink_asan --eta || { echo "mac-sink: eta FAILED"; exit 1; }
# What the shell does to a name HFS cannot take as it stands: 31 characters
# per component, and the collision that cutting creates numbered ~1. Its
# own code, and until 2026-08-28 it had no test — the subjects are
# generated, because no fixture reaches either cap (TESTING.md).
python3 tools/run_macnames.py --sink ./build/mac_sink_asan || {
    echo "mac-sink: name-shortening FAILED"; exit 1; }
# The archive's comment, when `Comments` and `Comments~1` are already there:
# the report must name the file it wrote. It named the first number tried,
# `Comments~1`, for a note written as `Comments~2` until 2026-10-15. Sees
# that one line and that the file exists; not what is in it (verify does).
if [ -f fixtures/derived-Compact_Pro_Package ]; then
    out="$(mktemp -d)"
    echo x > "$out/Comments"; echo x > "$out/Comments~1"
    rep=$(./build/mac_sink_asan fixtures/derived-Compact_Pro_Package "$out" 2>&1 \
          | grep '^report: Archive comment' || true)
    if [ "$rep" != "report: Archive comment saved as Comments~2" ] \
       || [ ! -f "$out/Comments~2" ]; then
        echo "mac-sink: comment rename FAILED: '$rep'"; rm -rf "$out"; exit 1
    fi
    rm -rf "$out"
fi
echo "mac-sink: native OK (file + RAM paths + cancel cleanup + meta + shortfall + eta + names + comment)"

# The alternative write path. The default streams each chunk straight to the
# File Manager; UNC_MAC_STAGE_WRITES accumulates whole forks in RAM and writes
# them in sink_end, which is what the shell used to do. Both must be
# byte-exact, and the staging path has two sub-variants of its own
# (UNC_MAC_FORCE_SHAREBUF packs both forks into one block).
echo "mac-sink: native x86-64, staging write path (+ shared block)"
wait $pid_stage || { echo "mac-sink: staging build FAILED"; exit 1; }
verify ./build/mac_sink_stage
verify ./build/mac_sink_stage "" "$BOTHFORK_FIXTURES"
./build/mac_sink_stage --cancel "$(mktemp -d)" || {
    echo "mac-sink: staging cancel-cleanup FAILED"; exit 1; }
wait $pid_sharebuf || { echo "mac-sink: shared-block build FAILED"; exit 1; }
verify ./build/mac_sink_sharebuf "" "$BOTHFORK_FIXTURES"
verify ./build/mac_sink_sharebuf ram "$BOTHFORK_FIXTURES"
echo "mac-sink: staging + shared-block OK (both forks byte-exact)"

if [ "$HAVE_M68K" = yes ]; then
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
    wait $pid_m68k || { echo "mac-sink: m68k build FAILED"; exit 1; }
    verify "qemu-m68k build/mac_sink_m68k"
    verify "qemu-m68k build/mac_sink_m68k" ram
    # The estimate's products are sized for a 32-bit long; this is the
    # lane where a long is 32 bits.
    qemu-m68k build/mac_sink_m68k --eta || { echo "mac-sink: m68k eta FAILED"; exit 1; }
    echo "mac-sink: m68k big-endian OK (file + RAM paths)"
    verify "qemu-m68k build/mac_sink_m68k" "" "$BOTHFORK_FIXTURES"
    wait $pid_sb68 || { echo "mac-sink: m68k shared-block build FAILED"; exit 1; }
    verify "qemu-m68k build/mac_sink_sb68" "" "$BOTHFORK_FIXTURES"
    echo "mac-sink: m68k both write paths OK (both forks byte-exact)"
    # The UTF-8 fold on a BIG-ENDIAN 32-bit machine. It is byte
    # arithmetic over a 16-bit table and a shift-and-or decode, which is
    # exactly the shape that reads differently on the target, and the
    # native run above is little-endian 64-bit. One case, because the
    # other twelve are file-system work qemu only makes slower.
    python3 tools/run_macnames.py --sink "qemu-m68k build/mac_sink_m68k" \
        --case utf8 || { echo "mac-sink: m68k macnames FAILED"; exit 1; }
    # And the unit tests, for the one part of the engine no fixture
    # reaches on this machine: the ciphers. Their vectors come from
    # openssl and python (tools/check_crypt.py), they are full of 32-bit
    # rotations and byte-order assumptions, and nothing else runs them
    # anywhere but little-endian x86.
    wait $pid_unit68 || { echo "mac-sink: m68k unit-test build FAILED"; exit 1; }
    qemu-m68k build/unit_m68k
    echo "mac-sink: m68k unit tests OK (the cipher vectors included)"
else
    echo "mac-sink: m68k cross-toolchain absent, skipping big-endian check"
fi

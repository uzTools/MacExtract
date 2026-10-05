#!/bin/sh
# ci.sh — full build + test matrix. Must be green before every commit.
#
#   0. documentation invariants (tools/check_docs.py) — cheap, so it runs first
#   1. gcc, ASan + UBSan + alignment sanitizer, unit tests + diff tests
#   2. gcc -m32 (32-bit), unit tests + diff tests (skipped gracefully
#      if multilib is unavailable)
#
# Diff tests run only if fixtures + manifests exist (tests/run_diff.sh).

set -e
cd "$(dirname "$0")"

fail() { echo "CI: FAILED: $*" >&2; exit 1; }

echo "=== documentation invariants ==="
python3 tools/check_docs.py || fail "documentation checks"

# A function that always returns a tuple, tested for truthiness: the test
# cannot fail, and Python says nothing. Cheap, so it runs beside the docs
# check (DECISIONS.md 2026-09-25, *the skip that could not fire, again*).
echo "=== tuple-truth lint ==="
python3 tools/check_tuple_truth.py || fail "tuple-truth lint"

# The three CRC tables said "generated mechanically from the polynomials"
# for months with nothing checking it. This rebuilds all three from the
# PUBLISHED polynomial and compares 768 entries; --selftest bends one
# entry of each first, so a pass means something.
echo "=== CRC tables are their polynomials ==="
python3 tools/check_crc_tables.py --selftest || fail "CRC table check"

# NOTICE is the only inventory of borrowed code since 2026-09-27. A prose
# list goes stale the moment a file sheds its last citation, and three
# files were recorded as shed while still carrying one. This fails both
# ways: on a file that gains a citation, and on one that loses its last.
echo "=== provenance inventory matches the source ==="
python3 tools/check_provenance.py --selftest || fail "provenance inventory"

echo "=== variant 1: sanitizers (ASan+UBSan+alignment) ==="
make clean >/dev/null
make BUILD=build/san \
     CFLAGS="-O1 -g -fsanitize=address,undefined,alignment -fno-sanitize-recover=all" \
     all >/dev/null || fail "sanitizer build"
./build/san/unit_tests || fail "unit tests (sanitizers)"
MACEXTRACT=build/san/macextract sh tests/run_diff.sh || fail "diff tests (sanitizers)"
MACEXTRACT=build/san/macextract sh tests/run_robustness.sh || fail "robustness tests (sanitizers)"
# The property run_robustness.sh cannot have: it accepts exit 0 on a
# truncated archive, so a walk that hands over the entries before the cut
# and reports success passes it 9,320 variants clean. This asks the
# oracle instead — where unar calls a cut archive broken, so must we.
python3 tools/run_truncation.py --bin build/san/macextract \
    || fail "truncation tests"
# The one engine property the byte comparisons cannot see: whether a
# decoder ever lets its caller breathe. A format that never calls the
# progress callback extracts perfectly and freezes the Mac's dialog for
# the whole run, with both Cancel routes out of reach — which Now
# Compress did until 2026-08-28, found on an emulated Mac.
python3 tools/run_ticks.py --probe build/san/tick_probe \
    --macextract build/san/macextract || fail "progress-callback coverage"
python3 tools/run_unwrap.py build/san/macextract || fail "envelope unwrap tests"
python3 tools/run_multihqx.py --macextract build/san/macextract \
    || fail "multi-document BinHex tests"
MACEXTRACT=build/san/macextract sh tests/run_collide.sh || fail "collision tests"
python3 tools/fuzz.py -n 150 --seed 7 --macextract build/san/macextract || fail "fuzz smoke"
python3 tools/run_segments.py --macextract build/san/macextract \
    || fail "segmented-archive tests"
# The two formats M13 brought in scope have no corpus fixtures at all,
# so both suites generate their own and hand them to a second
# implementation to grade: `unar` for ARC, `hexbin` for the UUTool shape.
python3 tools/run_arc.py --macextract build/san/macextract || fail "ARC tests"
# ARC methods 0x0a/0x0b are PAK's, and nothing on Linux writes them, so
# their archives come from PAK 2.51 under DOSBox (tools/pak.py) or from
# the two real specimens. Skips politely when neither is present.
python3 tools/run_pak.py --macextract build/san/macextract || fail "PAK method tests"
# The OTHER method 0x0a: ARC 7.x's Trimmed, which shares the number
# with PAK's Crushed. This suite also checks the discriminator, by
# holding the same input files under both dialects.
python3 tools/run_arcplus.py --macextract build/san/macextract \
    || fail "ARC+Plus (Trimmed) tests"
python3 tools/run_uu.py --macextract build/san/macextract || fail "uuencode tests"
# A zip counts its entries in 16 bits, so past 65,535 the count comes
# from the Zip64 record instead. Generated: nothing in the corpus is
# that large, and the failure it guards against is silent. Also the
# per-ENTRY Zip64 escape, which arrives at 2 GB and not at 4.
python3 tools/run_ziplarge.py --macextract build/san/macextract \
    || fail "large-zip (Zip64 entry count) tests"
# The other half of the same question: a member over 2 GB is refused per
# ENTRY, a position over 4 GB ends the walk. Sparse subjects, graded by
# GNU tar, which has neither limit.
python3 tools/run_sizelimits.py --macextract build/san/macextract \
    || fail "size-limit tests"
# The third limit of the same family, and the one that was silent until
# 2026-08-27: a name longer than UNC_NAME_MAX, or than one directory
# entry takes. Shortened and numbered like a filesystem's, never
# refused. Generated, because the longest name in the corpus is 120
# bytes.
python3 tools/run_names.py --macextract build/san/macextract \
    || fail "over-long name tests"
# What a small Macintosh refuses, decided on Linux. The Mac shell's
# allocator is a running total against a cap, and `--budget` is the same
# rule, so a tier's memory result can be swept here in seconds instead of
# one emulator boot per fixture. Two lanes: the RESIDENT one holds the
# engine to a fixed ceiling per tier, the SHIPPED one gives each format —
# and each envelope layer — the budget the 'OVLY' release leaves it, and
# asserts the refused fixtures by name. Only what a machine has agreed
# with is asserted; a tally that moves is a memory regression or a memory
# win, and either should be deliberate (TESTING.md, *The tiers a budget
# predicts*).
python3 tools/run_tiers.py --check --macextract build/san/macextract \
    || fail "memory-budget tier check"
# --only: acting on the entries the user named. `unar` has no per-file
# selection, so the reference side is this engine's own FULL extraction
# — which the diff suite above grades against `unar`. The assertion that
# can fail is the strict subset: an --only that did nothing would pass
# every byte comparison.
python3 tools/run_only.py --macextract build/san/macextract \
    || fail "--only (selective extraction) tests"
# The three walks — listing, extracting, and one that SKIPS every second
# entry — must offer the same entries in the same order. Nothing else
# here compares walks with each other: every other suite watches the
# output of ONE. Envelopes are peeled on the way in, or a .sit.bin would
# only ever test the MacBinary wrapper. Both assertions were made to
# fail before they were believed (TESTING.md).
python3 tools/run_walk.py --probe build/san/walk_probe \
    --macextract build/san/macextract || fail "walk-agreement tests"
# The other kind of walk: the HOST-side ones that read a Macintosh volume
# back and grade what an application wrote onto it. Eight of them, four
# columns, no emulator and no ROM — seconds. Its four EXPECT_* sets fail
# in both directions, so a walk that regresses and a walk that is fixed
# both say so. Skips cleanly without hfsutils.
python3 tools/vmac/walkprobe.py --check > /dev/null \
    || fail "volume-walk probe (tools/vmac/walkprobe.py --check)"
# Now Compress has exactly one REAL fixture, and it reaches two of the
# five shapes a block can have. The rest — and the offset-delta search,
# and folders, and several files in one archive — are generated the same
# way and handed to `unar`, which is the implementation fmt_now.c was
# transcribed from. One of the generated archives is committed as a
# fixture too, so the diff suite grades those paths without `unar`.
python3 tools/run_now.py --macextract build/san/macextract \
    || fail "Now Compress tests"
# ...and the READER half of that search, graded by the container's own
# arithmetic rather than by this engine: rebase a generated archive's
# block table and require tools/derive_now.py to get the same blocks back
# out of the result (TESTING.md, *Now Compress*).
NOWTMP=$(mktemp -d)
python3 tools/synth_now.py -o "$NOWTMP/plain.now" \
    && python3 tools/mutate_now.py --delta 100 "$NOWTMP/plain.now" \
        "$NOWTMP/rebased.now" --check > /dev/null \
    || fail "offset-delta re-read (tools/mutate_now.py --delta --check)"
rm -rf "$NOWTMP"
# SuperDisk! is the one format in the corpus that neither `unar` nor
# `macunpack` can read at all, so the oracle manifests describe only the
# envelope. Its two archives were graded fork by fork by their OWN
# self-extractors on an emulated Mac (tools/vmac/superdisk.py
# --adjudicate); this replays that verdict by content.
python3 tools/run_superdisk.py --macextract build/san/macextract \
    || fail "SuperDisk! tests"
# ...and the same format's SECOND implementation, off the Macintosh:
# Alysis's own Add-In Modules, lifted out of a corpus fixture and run under
# qemu-m68k (tools/sdmodule/). Every method 1..9 goes through both readers.
# Skips cleanly without qemu-m68k or the cross-compiler.
python3 tools/sdmodule/run_sdmodule.py --macextract build/san/macextract \
    || fail "SuperDisk! module differential"
# btoa/atob (M26). No corpus file and no second reader — `unar` does not
# know the format — so the ORIGINAL implementation is the encoder: the
# suite compiles reference/btoa and grades our decoder against what it
# writes, in both framings. Skips cleanly without reference/.
python3 tools/run_btoa.py --macextract build/san/macextract \
    || fail "btoa tests"
# base64 and MIME (M36). No corpus file either — the sniff sweep claims
# none of the 940 — so the cases are generated and graded by TWO other
# implementations: munpack 1.6, which src/fmt_mime.c is transcribed
# from, and deark for the base64 half. Skips cleanly without reference/.
python3 tools/run_mime.py --macextract build/san/macextract \
    || fail "base64/MIME tests"
# LZH/LHA (M28). The corpus has one real `.lzh` and seven of lhasa's,
# all in the diff suite above; this is the sweep over the rest of that
# collection — 160-odd archives from fourteen writers — graded against
# TWO other implementations, lhasa (independent) and LHa 1.14i (the
# original, used as the encoder). Skips cleanly without reference/.
python3 tools/run_lzh.py --macextract build/san/macextract \
    || fail "LZH tests"
# The archives this engine NAMES and never extracts (RAR, 7z, xz, bzip2,
# Cabinet, Zoo, ar, cpio, ARJ). Signatures only, so the suite writes real
# archives with the tools that are here, grades the synthetic ones with
# deark, spoils every corroborating field, and sweeps the corpus — a Mac
# archive named as a PC one would be worse than no name at all.
python3 tools/run_foreign.py --macextract build/san/macextract \
    || fail "foreign-archive naming tests"
# Decryption (M25). Nothing in the corpus is encrypted, so this suite
# generates its own: `zip -P` and `arc g<pw>` write two of the five
# schemes themselves, and the three with no encoder here — StuffIt
# classic, StuffIt 5, PackIt — are generated and then adjudicated by
# `unar -p`, which is a different implementation of each cipher.
python3 tools/run_crypt.py --macextract build/san/macextract \
    || fail "decryption tests"
# The optimized StuffIt archives, graded by the program that WROTE them:
# StuffIt Deluxe 2.0.1 under Mini vMac stuffed a text file with `Text 1`
# enabled and unstuffed it again, and what it hands back is the only
# definition of correct there is for an Optimizer that undoes nothing.
# Skips cleanly with no specimens (TESTING.md).
python3 tools/run_sitopt.py --macextract build/san/macextract \
    || fail "StuffIt Optimizer tests"
# StuffIt SpaceSaver has no oracle and no committed fixture either: what
# grades it is a file SpaceSaver itself wrote under Mini vMac, which
# lives beside the emulator's other state. Skips cleanly when there is
# none, so this says nothing on a fresh clone (TESTING.md).
python3 tools/run_spacesaver.py --macextract build/san/macextract \
    || fail "SpaceSaver tests"
# ...and SpaceSaver's own codecs, off the Macintosh: each `CMod` module
# holds a compressor as well as an expander, and qemu-m68k runs either
# (tools/ssmodule/). That is where a specimen of methods 1, 2 and 3 comes
# from — nothing else here writes one — and it grades what this engine
# reads for the two methods it implements. Needs the installed control
# panel in the emulator cache; skips cleanly without it.
python3 tools/ssmodule/run_ssmodule.py --macextract build/san/macextract \
    || fail "SpaceSaver module differential"
# Nine archives ZipIt itself wrote: the subjects for its three Macintosh
# extra fields, which until 2026-10-04 were all generated here. Five are
# self-extracting and are passed `-f Zip`; the other four are sniffed
# unaided, which the suite asserts. Specimens rather than fixtures
# because a ZipIt SEA is not recognised (OPEN_ITEMS.md); the two plain
# ones that are fixtures, `MrTs_Paint_Folder.zip` and
# `NPWritersKit.zip`, run_diff.py grades with no oracle. Skips cleanly
# with no specimens (TESTING.md).
python3 tools/run_zipit.py --macextract build/san/macextract \
    || fail "ZipIt tests"

echo "=== variant 1b: sampled inverse BWT (forced, + budget) ==="
# The Arsenic decoder falls back to a sampled occurrence index when the
# 4-bytes-per-byte transform vector does not fit. It is chosen by an
# allocation failing, so an unconstrained run never reaches it: force it,
# and separately run StuffIt 5 under the budget a 1 MB Mac Plus leaves
# the engine, which is what picks the fallback's sampling rate for real.
make BUILD=build/ars CFLAGS="-O1 -g -fsanitize=address,undefined,alignment \
     -fno-sanitize-recover=all -DUNC_ARS_FORCE_SAMPLED" all >/dev/null \
     || fail "forced-sampled build"
./build/ars/unit_tests || fail "unit tests (forced sampled)"
MACEXTRACT=build/ars/macextract sh tests/run_diff.sh || fail "diff tests (forced sampled)"
MACEXTRACT=build/ars/macextract sh tests/run_robustness.sh \
    || fail "robustness tests (forced sampled)"
python3 tools/run_diff.py --macextract build/san/macextract \
    --format "StuffIt 5" --budget 615348 || fail "StuffIt 5 diff under 1 MB budget"

# The deep end of the sampling dial, which neither run above reaches: a
# budget big enough to hold the block at all is big enough to keep `target`
# high, so no real run makes a query whose scan spans most of the block.
# Force target=1 and check byte-exactness there. No sanitizers (variant 1b
# already covers this code under ASan at the default target) and size-capped,
# because at target=1 the walk is quadratic — the whole StuffIt 5 set costs
# 8.4 min this way, the capped subset ~25 s.
make BUILD=build/ars1 \
     CFLAGS="-O2 -DUNC_ARS_FORCE_SAMPLED -DARS_INDEX_TARGET=1u" all >/dev/null \
     || fail "target=1 build"
./build/ars1/unit_tests || fail "unit tests (target=1)"
python3 tools/run_diff.py --macextract build/ars1/macextract \
    --format "StuffIt 5" --max-size 100000 || fail "StuffIt 5 diff at target=1"

echo "=== variant 1c: the LZW length escape (forced) ==="
# unc_lzw.c keeps each string's length in one byte and walks up the
# parents when it saturates. The longest string in the corpus is 223
# bytes, so no fixture reaches that walk: move the saturation point to 4
# and nearly every string does. Byte-exactness is the whole test, and it
# is a test — with the walk broken by one token this build differs on
# 112 of the 113 LZW fixtures and the default build on none
# (TESTING.md, *The LZW string length*).
make BUILD=build/lzwlen CFLAGS="-O1 -g -fsanitize=address,undefined,alignment \
     -fno-sanitize-recover=all -DUNC_LZW_LEN_MAX=4" all >/dev/null \
     || fail "LZW length-escape build"
./build/lzwlen/unit_tests || fail "unit tests (LZW length escape)"
MACEXTRACT=build/lzwlen/macextract sh tests/run_diff.sh \
    || fail "diff tests (LZW length escape)"

echo "=== variant 3b: Mac sink (native ASan + big-endian m68k) ==="
sh tests/run_mac_sink.sh || fail "mac sink tests"

# The OVERLAY LOADER, which no suite here reached until 2026-09-26. The
# application's fourteen 'OVLY' images exist only in a Retro68 build, so every
# lane above — and the 932 fixtures, and the 9,320 robustness variants — runs
# the decoders as ordinary linked code. This one builds the same images with
# the m68k-linux toolchain, runs the REAL loader against them through a mock
# Memory and Resource Manager, and extracts fixtures through them under
# qemu-m68k. `--mutate` breaks the loader six ways and requires each break to
# be caught, because a suite this new has not yet earned the benefit of the
# doubt (tests/ovlbox/README.md, TESTING.md *The overlay loader, off the
# Macintosh*). Skips cleanly without the cross-compiler or qemu-m68k.
echo "=== variant 3c: the overlay loader, off the Macintosh ==="
sh tests/run_overlay_host.sh --mutate || fail "overlay loader (host lane)"

echo "=== variant 2: 32-bit (-m32) ==="
if echo 'int main(void){return 0;}' | gcc -m32 -x c - -o build/m32probe 2>/dev/null; then
    rm -f build/m32probe
    make BUILD=build/m32 CFLAGS="-O2 -m32" all >/dev/null || fail "-m32 build"
    ./build/m32/unit_tests || fail "unit tests (-m32)"
    MACEXTRACT=build/m32/macextract sh tests/run_diff.sh || fail "diff tests (-m32)"
else
    echo "CI: -m32 unavailable, skipping 32-bit variant"
fi

echo "=== variant 3: release build (warnings are errors) ==="
make BUILD=build/rel CFLAGS="-O2 -Werror" all >/dev/null || fail "release build"
./build/rel/unit_tests || fail "unit tests (release)"

# The engine carries a container offset in unc_off_t. Every lane above
# builds the host default, 64 bits; the MACINTOSH build is 32 bits and
# is the one that ships on a floppy, so it is graded here against the
# same fixtures and the same oracle. The width that ships to a Mac is
# not allowed to be the width nothing runs. (DECISIONS.md 2026-08-28,
# *what a width costs*.)
echo "=== variant 5: 32-bit container offsets (the Macintosh width) ==="
make BUILD=build/off32 OFFDEFS= \
     CFLAGS="-O1 -g -fsanitize=address,undefined,alignment -fno-sanitize-recover=all" \
     all >/dev/null || fail "32-bit offset build"
./build/off32/macextract --version | grep -q "offsets: 32-bit" \
    || fail "variant 5 did not build the 32-bit configuration"
./build/off32/unit_tests || fail "unit tests (32-bit offsets)"
MACEXTRACT=build/off32/macextract sh tests/run_diff.sh || fail "diff tests (32-bit offsets)"
MACEXTRACT=build/off32/macextract sh tests/run_robustness.sh \
    || fail "robustness tests (32-bit offsets)"
python3 tools/run_sizelimits.py --macextract build/off32/macextract \
    || fail "size-limit tests (32-bit offsets)"

echo "=== variant 4: Retro68 Mac shell (compile-only, optional) ==="
sh tools/build_mac.sh || fail "mac build"

# dist/ is a committed binary and the only download this project offers, and
# nothing compared it with anything until 2026-09-22 — it had gone stale by
# 591 B of resource fork. The build above has just written the application
# this tree produces, so the comparison is free. MacBinary stores the file's
# dates, so the first 128 bytes differ between two runs over identical code
# and the PAYLOAD does not (tools/make_dist.sh says so at the top, and it is
# what this asserts every run).
if [ -f build/mac/MacExtract.bin ]; then
    [ -f dist/MacExtract.bin ] || fail "dist/MacExtract.bin is missing — run: sh tools/make_dist.sh"
    built=$(tail -c +129 build/mac/MacExtract.bin | sha256sum | cut -d' ' -f1)
    shipped=$(tail -c +129 dist/MacExtract.bin | sha256sum | cut -d' ' -f1)
    [ "$built" = "$shipped" ] || fail "dist/MacExtract.bin is STALE: it is not the application this tree builds.
       Fix: run \`sh tools/make_dist.sh\` and commit dist/ in the SAME commit
       as the change to mac/ or src/ (CLAUDE.md, Rules). Re-read dist/README.txt
       while you are there."
    echo "dist: MacExtract.bin matches the build ($built)"
fi

# Nothing watched the application's SIZE until 2026-09-23, and it moved
# 10,112 B in a month without a status file noticing. Every byte is
# resident on the target, so it is heap the Macintosh no longer has, and
# at the sys6-512K tier the narrowest passing fixture has 6,952 B of
# headroom (DECISIONS.md 2026-09-23, *the ten kilobytes nothing watched*).
python3 tools/check_app_size.py build/mac/MacExtract.code.bin \
    || fail "application size moved without acknowledgement"

# The images the Retro68 build has just written are the bytes dist/ ships, and
# variant 3c graded a SECOND toolchain's build of the same sources. This runs
# the real loader against the shipped ones: found, relocated at the address
# they run at, kept, released. It is the only check anywhere that the bundle's
# own directory and the 30 relocations across its six images are right — and
# Retro68's images carry those where the m68k-linux build of the same sources
# carries 15 in one image, so 3c alone does not cover them. They cannot be
# CALLED here (measured: SIGSEGV); executing them is the emulator tiers'
# (DECISIONS.md 2026-09-26, *the loader that could be run after all*).
echo "=== variant 3d: the SHIPPED overlay images, through the real loader ==="
sh tests/run_overlay_host.sh --shipped-only || fail "shipped overlay images"

# variant 4b, added 2026-09-09: the OVERLAY configuration, EAGER — the
# lifetime the application ships. Merging a new format in once passed every check
# above and left this unlinkable, a resident decoder calling unc_lzah_decode
# which lives in the codecs image, because ci.sh built only the configuration
# without overlays. A feature that IS a build configuration has to be built.
echo "=== variant 4b: the overlay configuration, eager ==="
UNC_AT_OVERLAY=1 sh tools/build_mac.sh || fail "overlay build (eager)"

# The shipped lane's budgets are made OF the image sizes, one per format
# (FORMATS.md, *What each format is granted*), and the images do not exist
# until the build above: `make clean` runs first and the tier check runs in
# variant 1, so this is the only point in the run where they can be graded.
python3 tools/run_tiers.py --check-images \
    || fail "the overlay images moved — re-take run_tiers.py's IMAGES"

# variant 4c: the LAZY lifetime — the same fourteen images, one resource
# each, read when a format turns out to want one. It is not shipped, and that
# is precisely why it is built: the two lifetimes were separate branches until
# 2026-09-25, and because neither tree compiled the other, the same
# build-staleness fix had to be found and written twice, days apart. An
# unbuilt variant is a variant that rots.
echo "=== variant 4c: the overlay configuration, lazy ==="
UNC_AT_OVERLAY=1 UNC_OVL_LAZY=1 UNC_MAC_BUILD_DIR=build/mac-lazy \
    sh tools/build_mac.sh || fail "overlay build (lazy)"

# variant 4d, added 2026-09-26: the RESIDENT control — every decoder linked
# in, the instrument the overlay figures are measured against (FORMATS.md,
# *Overlays*). It was the one configuration nothing built, and it rotted
# exactly as 4c's comment says: a four-byte predicate in src/fmt_arc.c put it
# 4 B over its own ratchet, green everywhere else because that file is in an
# overlay in both shipped lifetimes (DECISIONS.md 2026-09-26). A control that
# is not built is not a control.
echo "=== variant 4d: the overlay configuration, resident control ==="
UNC_AT_OVERLAY=1 UNC_OVL_RESIDENT=1 UNC_MAC_BUILD_DIR=build/mac-resident \
    sh tools/build_mac.sh || fail "overlay build (resident control)"

# Every format's granted budget is OVL_SAVED less the images it keeps, so a
# stale OVL_SAVED is a stale budget for all of them at once — and it went 32 B
# stale on 2026-09-26 with FORMATS.md corrected and run_tiers.py not, which
# then read as part of the residue under the model (BLOCKERS.md, *Corrected
# figures*). It is the difference of the two builds above, so it can be
# graded, and this is the first point in the run where both exist.
python3 tools/run_tiers.py --check-saved \
    || fail "OVL_SAVED no longer matches build/mac and build/mac-resident"

echo "CI: all green"

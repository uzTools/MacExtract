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

echo "=== variant 1: sanitizers (ASan+UBSan+alignment) ==="
make clean >/dev/null
make BUILD=build/san \
     CFLAGS="-O1 -g -fsanitize=address,undefined,alignment -fno-sanitize-recover=all" \
     all >/dev/null || fail "sanitizer build"
./build/san/unit_tests || fail "unit tests (sanitizers)"
MACEXTRACT=build/san/macextract sh tests/run_diff.sh || fail "diff tests (sanitizers)"
MACEXTRACT=build/san/macextract sh tests/run_robustness.sh || fail "robustness tests (sanitizers)"
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
# 2026-08-27: a name longer than UNC_NAME_MAX. Generated, because the
# longest name in the corpus is 120 bytes.
python3 tools/run_names.py --macextract build/san/macextract \
    || fail "over-long name tests"
# Now Compress has exactly one REAL fixture, and it reaches two of the
# five shapes a block can have. The rest — and the offset-delta search,
# and folders, and several files in one archive — are generated the same
# way and handed to `unar`, which is the implementation fmt_now.c was
# transcribed from. One of the generated archives is committed as a
# fixture too, so the diff suite grades those paths without `unar`.
python3 tools/run_now.py --macextract build/san/macextract \
    || fail "Now Compress tests"
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
    --format "StuffIt 5" --budget 597036 || fail "StuffIt 5 diff under 1 MB budget"

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

echo "=== variant 3b: Mac sink (native ASan + big-endian m68k) ==="
sh tests/run_mac_sink.sh || fail "mac sink tests"

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

echo "=== variant 4: Retro68 Mac shell (compile-only, optional) ==="
sh tools/build_mac.sh || fail "mac build"

echo "CI: all green"

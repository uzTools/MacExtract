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
UNCLASSIC=build/san/unclassic sh tests/run_diff.sh || fail "diff tests (sanitizers)"
UNCLASSIC=build/san/unclassic sh tests/run_robustness.sh || fail "robustness tests (sanitizers)"
python3 tools/run_unwrap.py build/san/unclassic || fail "envelope unwrap tests"
python3 tools/run_multihqx.py --unclassic build/san/unclassic \
    || fail "multi-document BinHex tests"
UNCLASSIC=build/san/unclassic sh tests/run_collide.sh || fail "collision tests"
python3 tools/fuzz.py -n 150 --seed 7 --unclassic build/san/unclassic || fail "fuzz smoke"
python3 tools/run_segments.py --unclassic build/san/unclassic \
    || fail "segmented-archive tests"
# The two formats M13 brought in scope have no corpus fixtures at all,
# so both suites generate their own and hand them to a second
# implementation to grade: `unar` for ARC, `hexbin` for the UUTool shape.
python3 tools/run_arc.py --unclassic build/san/unclassic || fail "ARC tests"
python3 tools/run_uu.py --unclassic build/san/unclassic || fail "uuencode tests"

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
UNCLASSIC=build/ars/unclassic sh tests/run_diff.sh || fail "diff tests (forced sampled)"
UNCLASSIC=build/ars/unclassic sh tests/run_robustness.sh \
    || fail "robustness tests (forced sampled)"
python3 tools/run_diff.py --unclassic build/san/unclassic \
    --format "StuffIt 5" --budget 678392 || fail "StuffIt 5 diff under 1 MB budget"

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
python3 tools/run_diff.py --unclassic build/ars1/unclassic \
    --format "StuffIt 5" --max-size 100000 || fail "StuffIt 5 diff at target=1"

echo "=== variant 3b: Mac sink (native ASan + big-endian m68k) ==="
sh tests/run_mac_sink.sh || fail "mac sink tests"

echo "=== variant 2: 32-bit (-m32) ==="
if echo 'int main(void){return 0;}' | gcc -m32 -x c - -o build/m32probe 2>/dev/null; then
    rm -f build/m32probe
    make BUILD=build/m32 CFLAGS="-O2 -m32" all >/dev/null || fail "-m32 build"
    ./build/m32/unit_tests || fail "unit tests (-m32)"
    UNCLASSIC=build/m32/unclassic sh tests/run_diff.sh || fail "diff tests (-m32)"
else
    echo "CI: -m32 unavailable, skipping 32-bit variant"
fi

echo "=== variant 3: release build (warnings are errors) ==="
make BUILD=build/rel CFLAGS="-O2 -Werror" all >/dev/null || fail "release build"
./build/rel/unit_tests || fail "unit tests (release)"

echo "=== variant 4: Retro68 Mac shell (compile-only, optional) ==="
sh tools/build_mac.sh || fail "mac build"

echo "CI: all green"

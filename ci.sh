#!/bin/sh
# ci.sh — full build + test matrix. Must be green before every commit.
#
#   1. gcc, ASan + UBSan + alignment sanitizer, unit tests + diff tests
#   2. gcc -m32 (32-bit), unit tests + diff tests (skipped gracefully
#      if multilib is unavailable)
#
# Diff tests run only if fixtures + manifests exist (tests/run_diff.sh).

set -e
cd "$(dirname "$0")"

fail() { echo "CI: FAILED: $*" >&2; exit 1; }

echo "=== variant 1: sanitizers (ASan+UBSan+alignment) ==="
make clean >/dev/null
make BUILD=build/san \
     CFLAGS="-O1 -g -fsanitize=address,undefined,alignment -fno-sanitize-recover=all" \
     all >/dev/null || fail "sanitizer build"
./build/san/unit_tests || fail "unit tests (sanitizers)"
UNCLASSIC=build/san/unclassic sh tests/run_diff.sh || fail "diff tests (sanitizers)"
UNCLASSIC=build/san/unclassic sh tests/run_robustness.sh || fail "robustness tests (sanitizers)"
python3 tools/run_unwrap.py build/san/unclassic || fail "envelope unwrap tests"
python3 tools/fuzz.py -n 150 --seed 7 --unclassic build/san/unclassic || fail "fuzz smoke"

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

echo "CI: all green"

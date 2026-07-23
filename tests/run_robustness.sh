#!/bin/sh
# run_robustness.sh — for every green fixture, generate truncated and
# bit-flipped variants and require the engine to fail cleanly:
# no crash, no hang, no sanitizer trip. Exit codes 0/1 are both fine
# (a mangled archive may still partially extract); death by signal is not.
#
# Env: UNCLASSIC = path to the CLI binary (sanitizer build recommended)

set -e
cd "$(dirname "$0")/.."

UNCLASSIC="${UNCLASSIC:-build/san/unclassic}"

if [ ! -d fixtures/manifests ] || [ -z "$(ls fixtures/manifests 2>/dev/null)" ]; then
    echo "robustness: no manifests present, skipping"
    exit 0
fi

python3 tools/run_robustness.py --unclassic "$UNCLASSIC"

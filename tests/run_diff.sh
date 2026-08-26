#!/bin/sh
# run_diff.sh — differential tests: extract every fixture with the
# engine and compare byte-for-byte against the committed oracle
# manifests (built from unar/macunpack output by tools/make_manifests.py).
#
# Env: MACEXTRACT = path to the CLI binary (default build/san/macextract)
#
# Skips politely when no fixtures/manifests are present (fresh clone).

set -e
cd "$(dirname "$0")/.."

MACEXTRACT="${MACEXTRACT:-build/san/macextract}"

if [ ! -d fixtures/manifests ] || [ -z "$(ls fixtures/manifests 2>/dev/null)" ]; then
    echo "diff: no manifests present, skipping (run tools/harvest.sh first)"
    exit 0
fi

python3 tools/run_diff.py --macextract "$MACEXTRACT"

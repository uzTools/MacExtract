#!/bin/sh
# run_collide.sh — output-path collisions must be a per-entry error,
# never a silent overwrite.
#
# An archive holding both "X" and "X.rsrc" — a THINK C project — puts
# the second entry's data fork on the first entry's sidecar under the
# default ".rsrc" convention. Letting the last writer win destroys a
# fork that was extracted correctly. `derived-Unzip101.sit` is that
# shape: "Source/UnZip.π" carries a 7,048 B resource fork and
# "Source/UnZip.π.rsrc" is a real, resource-only entry of 5,656 B.
#
# Env: UNCLASSIC = path to the CLI binary (default build/san/unclassic)
#
# Skips politely when the fixture is absent (fixtures are not committed).

set -e
cd "$(dirname "$0")/.."

UNCLASSIC="${UNCLASSIC:-build/san/unclassic}"
FIXTURE=fixtures/derived-Unzip101.sit

if [ ! -f "$FIXTURE" ]; then
    echo "collide: $FIXTURE absent, skipping (run tools/harvest.py --restore)"
    exit 0
fi

fail() { echo "collide: FAILED: $*" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# 1. The default refuses, names the path, and keeps the fork it already
#    wrote. This is the case that used to lose 7,048 bytes in silence.
out="$tmp/default"
mkdir -p "$out"
if "$UNCLASSIC" x -nr -o "$out" "$FIXTURE" >"$tmp/1.out" 2>"$tmp/1.err"; then
    fail "default forks: expected a nonzero exit on the collision"
fi
grep -q "output path already exists" "$tmp/1.err" \
    || fail "default forks: collision not reported (stderr: $(cat "$tmp/1.err"))"
sz=$(wc -c < "$out/Source/UnZip.π.rsrc")
[ "$sz" = 7048 ] || fail "default forks: sidecar is $sz bytes, want 7048 (clobbered)"

# 2. `--forks hidden` is the way out, and gets both entries whole.
out="$tmp/hidden"
mkdir -p "$out"
"$UNCLASSIC" x -nr --forks hidden -o "$out" "$FIXTURE" \
    || fail "--forks hidden: expected a clean extraction"
sz=$(wc -c < "$out/Source/._UnZip.π")
[ "$sz" = 7048 ] || fail "--forks hidden: ._UnZip.π is $sz bytes, want 7048"
sz=$(wc -c < "$out/Source/._UnZip.π.rsrc")
[ "$sz" = 5656 ] || fail "--forks hidden: ._UnZip.π.rsrc is $sz bytes, want 5656"

# 3. `--overwrite` restores the old behaviour, for re-extracting into a
#    directory that already holds output.
out="$tmp/overwrite"
mkdir -p "$out"
"$UNCLASSIC" x -nr --overwrite -o "$out" "$FIXTURE" \
    || fail "--overwrite: expected a zero exit"
"$UNCLASSIC" x -nr --overwrite -o "$out" "$FIXTURE" \
    || fail "--overwrite: expected a zero exit on re-extraction"
if "$UNCLASSIC" x -nr -o "$out" "$FIXTURE" >/dev/null 2>&1; then
    fail "re-extracting without --overwrite should refuse"
fi

echo "collide: OK (refused by default, --forks hidden clean, --overwrite restores)"

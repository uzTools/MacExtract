#!/bin/sh
# run_arsenic_m68k.sh — the StuffIt 5 differential on a 68000 build of the
# engine, under qemu-m68k, on all three rungs of Arsenic's inverse BWT.
#
# src/sit_arsenic.c divides with an inline `divu.w` on a 68000 and with C
# everywhere else (ars_divu). Every other lane in ci.sh runs the C body, so
# without this one nothing here would grade the instruction the Macintosh
# executes. Built with the cross-compiler at the shipped -Os -mcpu=68000;
# qemu-m68k emulates divu.w's quotient and remainder exactly.
#
# What it CANNOT see: Retro68's own code generation (a different GCC; the
# emulator tiers run that), cycle counts (the tick probe), and alignment —
# qemu-m68k's default CPU tolerates unaligned access (tests/run_mac_sink.sh).
#
# Skips cleanly without the cross-compiler or qemu-m68k.
set -u
cd "$(dirname "$0")/.." || exit 1
if ! command -v m68k-linux-gnu-gcc >/dev/null 2>&1 \
   || ! command -v qemu-m68k >/dev/null 2>&1; then
    echo "arsenic-m68k: no m68k-linux-gnu-gcc or qemu-m68k, skipped"
    exit 0
fi
B=build/ars68k
mkdir -p "$B"
rc=0
for r in table: half:-DUNC_ARS_FORCE_HALF sampled:-DUNC_ARS_FORCE_SAMPLED; do
    n=${r%%:*}
    d=${r#*:}
    m68k-linux-gnu-gcc -static -std=c99 -Os -mcpu=68000 \
        -fno-tree-loop-distribute-patterns \
        -Iinclude -Ithird_party/zlib -DZ_TESTW=0 -DNO_GZIP $d \
        cli/main.c src/*.c third_party/zlib/*.c -o "$B/macextract-$n" \
        || { echo "arsenic-m68k: $n build FAILED"; exit 1; }
    if ! m68k-linux-gnu-objdump -d "$B/macextract-$n" | grep -q 'divuw'; then
        echo "arsenic-m68k: $n build has no divu.w — the asm path is not built"
        exit 1
    fi
    printf '#!/bin/sh\nexec qemu-m68k "%s" "$@"\n' "$PWD/$B/macextract-$n" \
        > "$B/q-$n"
    chmod +x "$B/q-$n"
    python3 tools/run_diff.py --macextract "$B/q-$n" --format "StuffIt 5" \
        || { echo "arsenic-m68k: $n FAILED"; rc=1; }
done
# The 1 MB floor's budget, which picks the rungs for real (ci.sh, variant 1b).
python3 tools/run_diff.py --macextract "$B/q-table" --format "StuffIt 5" \
    --budget 615348 || { echo "arsenic-m68k: 1 MB budget FAILED"; rc=1; }
exit $rc

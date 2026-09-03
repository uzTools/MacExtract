#!/bin/sh
# build_mac.sh — cross-compile the Macintosh shell.
#
# Locates a Retro68 toolchain via (in order): $RETRO68, m68k-apple-macos-gcc
# in PATH, or /opt/Retro68-build/toolchain. Skips gracefully when absent.
# Output: build/mac/macextract.{APPL,bin,dsk}
set -e
cd "$(dirname "$0")/.."

TOOLCHAIN=""
if [ -n "$RETRO68" ] && [ -d "$RETRO68" ]; then
    TOOLCHAIN="$RETRO68"
elif command -v m68k-apple-macos-gcc >/dev/null 2>&1; then
    TOOLCHAIN="$(dirname "$(dirname "$(command -v m68k-apple-macos-gcc)")")"
elif [ -x /opt/Retro68-build/toolchain/bin/m68k-apple-macos-gcc ]; then
    TOOLCHAIN=/opt/Retro68-build/toolchain
fi

CMAKEFILE="$TOOLCHAIN/m68k-apple-macos/cmake/retro68.toolchain.cmake"
if [ -z "$TOOLCHAIN" ] || [ ! -f "$CMAKEFILE" ]; then
    echo "mac: Retro68 m68k toolchain not found — skipping the Mac build."
    echo "mac: to build it: clone https://github.com/autc04/Retro68 and run"
    echo "mac:   ./build-toolchain.bash   then set RETRO68=<install prefix>"
    exit 0
fi

echo "mac: using Retro68 at $TOOLCHAIN"
cmake -B build/mac -S mac \
      -DCMAKE_TOOLCHAIN_FILE="$CMAKEFILE" \
      -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build build/mac -- -j"$(nproc)"
ls -la build/mac/MacExtract.APPL build/mac/MacExtract.bin build/mac/MacExtract.dsk

# ---- the code ceiling -------------------------------------------------------
#
# CODE is the only part of this application that costs the engine anything.
# Measured 2026-08-30 by ballast, on a 1 MB Mac Plus under System 6.0.8, with
# the ballast VERIFIED present in the binary that ran (three earlier attempts
# measured nothing because --gc-sections had dropped it, or because it sat in
# the other main):
#
#   +11,308 B of code  -> FreeMem 647,096 -> 635,768   (1:1)
#   + 6,132 B of .data -> FreeMem 647,096 -> 647,096   (free)
#
# CODE resources are handles INSIDE the heap FreeMem() reports; the A5 global
# world is outside it. So tables, strings and globals are free, and every byte
# of compiled code comes off every extraction:
#
#   budget = 708,100 - code        (autotest build, 1 MB, System 6.0.8)
#
# This is a RATCHET, not a budget. It is set at the code size on the day it
# was introduced, so growth has to be a decision rather than an accident:
# raise it deliberately, knowing that each byte is a byte off the budget on
# the smallest supported machine. Between 2026-08-24 and 2026-08-30 code grew
# ~32,000 B unnoticed, the budget fell from 597,036 to 565,176, and three
# corpus archives stopped fitting on a 1 MB Mac Plus with nothing failing.
# That is what this is here to stop happening again.
# Raised 2026-08-31 from 147,268 to 147,296: +16 B for the memory message
# that depends on whether there is a partition to grow, and +8 B for the test
# that stops a SUCCESSFUL extraction reporting a memory failure. Paid for many
# times over by the same day's stack re-pricing, which returned 12,272 B —
# but recorded here rather than absorbed, because that is the point of a
# ratchet.
# Raised again 2026-08-31 from 147,296 to 147,424: +128 B to take the
# documents the Finder hands over in AppParmHandle, so an archive dropped on
# the icon extracts. Bought deliberately and with a measured alternative
# refused: CountAppFiles/GetAppFiles are glue rather than traps in the
# Multiversal libraries and cost 344 B for less (DECISIONS.md 2026-08-31,
# *the drop the Finder does not make*). The 512 KB machine, whose Finder has
# no such gesture, pays the 128 B for nothing — which is the trade, stated.
# Raised again 2026-09-01 from 147,424 to 147,588: +164 B for the Apple
# Archive probe, once a reference for the format was found (DECISIONS.md
# 2026-09-01, *the search, not the reference*). Bought on the same terms as
# the rest of the named-only set: one engine, not a Macintosh subset of one.
# Two attempts at making it cheaper are in the probe -- the subtype set is a
# string constant rather than sixteen comparisons, and the length floor is
# one test rather than three -- and they bought 52 B of the 216 the first
# version cost. That 12 % is the figure worth remembering about code shape
# on this target.
# Raised on this branch, 2026-09-03, from 147,588 to 150,192: +2,644 B for
# selective extraction — the listing walk in RunExtract, the chooser box
# (SelListDraw, SelFilter, ChooseEntries) and the per-entry test in
# sink_begin. Deliberate and priced rather than absorbed: on a 1 MB Mac
# Plus that is 2,644 B off EVERY extraction's budget, including the runs
# of a user who never unticks anything. BRANCH_NOTES.md on this branch
# has what it buys and what the alternatives cost.
UNC_MAC_MAX_CODE=${UNC_MAC_MAX_CODE:-150192}
# The A5 ratchet, added 2026-09-02 with the measurement that made it
# necessary: 16,384 B of .data cost 16,418 B of budget, so data is not free
# and never was (FORMATS.md, *What the application costs the engine*; the
# withdrawn claim is in BLOCKERS.md). Set at the size on the day, like the
# code ceiling: 44,096 B = 32,644 data + 11,452 bss. It had grown unwatched
# the whole time this file said data was free.
# Raised on this branch, 2026-09-03, from 44,096 to 44,160: +64 B, which is
# the chooser's two strings and the four globals that pair the two walks
# up. The store itself is NOT here — it is a NewPtr taken before the
# engine's budget is worked out and given back before the extracting
# walk, so it costs the extraction nothing (BRANCH_NOTES.md).
UNC_MAC_MAX_A5=${UNC_MAC_MAX_A5:-44160}
SIZE="$TOOLCHAIN/bin/m68k-apple-macos-size"
GDB=build/mac/MacExtract.code.bin.gdb
if [ -x "$SIZE" ] && [ -f "$GDB" ]; then
    code=$("$SIZE" "$GDB" | awk 'NR==2 {print $1}')
    a5=$("$SIZE" "$GDB" | awk 'NR==2 {print $2 + $3}')
    echo "mac: code $code B (ceiling $UNC_MAC_MAX_CODE B)"
    echo "mac: A5   $a5 B (ceiling $UNC_MAC_MAX_A5 B) — data + bss, and it"
    echo "mac:      costs the engine one for one, same as code" 
    if [ "$a5" -gt "$UNC_MAC_MAX_A5" ]; then
        over=$((a5 - UNC_MAC_MAX_A5))
        echo "mac: FAIL — the A5 world is $over B over its ceiling." >&2
        echo "mac: that is $over B off every extraction's budget, exactly as" >&2
        echo "mac: code would be: the A5 world sits above ApplLimit, so it" >&2
        echo "mac: lowers the heap's ceiling by its own size. Put the table" >&2
        echo "mac: in a RESOURCE, which is free until it is loaded." >&2
        echo "mac: FORMATS.md, *What the application costs the engine*." >&2
        exit 1
    fi
    if [ "$code" -gt "$UNC_MAC_MAX_CODE" ]; then
        over=$((code - UNC_MAC_MAX_CODE))
        echo "mac: FAIL — code is $over B over the ceiling." >&2
        echo "mac: that is $over B off every extraction's budget on a 1 MB Mac" >&2
        echo "mac: Plus. Raise UNC_MAC_MAX_CODE deliberately, or put the new" >&2
        echo "mac: material in resources or tables, which cost nothing." >&2
        echo "mac: FORMATS.md, *What the application costs the engine*." >&2
        exit 1
    fi
else
    echo "mac: no m68k size tool — code ceiling NOT checked"
fi

echo "mac: OK — this only proves it compiles. tools/vmac/run.py replays fixtures"
echo "mac: on a real emulated Mac Plus; tools/vmac/README.md is how to run it."

#!/bin/sh
# build_mac.sh — cross-compile the Macintosh shell.
#
# Locates a Retro68 toolchain via (in order): $RETRO68, m68k-apple-macos-gcc
# in PATH, or /opt/Retro68-build/toolchain. Skips gracefully when absent.
# The ceilings below are measured with Retro68 afedcdc (2026-10-17) and its
# multiversal 057c802, the first to inline traps with register outputs
# (multiversal pull request 20); an older one builds larger and fails them
# (DECISIONS.md 2026-10-19, *the toolchain that inlined PurgeSpace*).
# Output: $UNC_MAC_BUILD_DIR/macextract.{APPL,bin,dsk}, build/mac by default.
#
# The build directory is settable because CMake reads UNC_AT_* and UNC_OVL_*
# from the environment at CONFIGURE time: reusing one directory for two
# configurations keeps the first one for ever, silently. ci.sh builds the
# eager lifetime into build/mac and the lazy one into build/mac-lazy for
# exactly that reason.
set -e
cd "$(dirname "$0")/.."
BUILD_DIR=${UNC_MAC_BUILD_DIR:-build/mac}

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
cmake -B "$BUILD_DIR" -S mac \
      -DCMAKE_TOOLCHAIN_FILE="$CMAKEFILE" \
      -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$BUILD_DIR" -- -j"$(nproc)"
ls -la "$BUILD_DIR"/MacExtract.APPL "$BUILD_DIR"/MacExtract.bin "$BUILD_DIR"/MacExtract.dsk

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
#
# The A5 ratchet, added 2026-09-02 with the measurement that made it
# necessary: 16,384 B of .data cost 16,418 B of budget, so data is not free
# and never was (FORMATS.md, *What the application costs the engine*; the
# withdrawn claim is in BLOCKERS.md). Set at the size on the day, like the
# code ceiling: 44,096 B = 32,644 data + 11,452 bss. It had grown unwatched
# the whole time this file said data was free.
#
# A CEILING PER CONFIGURATION, because one ceiling measured on another build
# cannot fire. The figures above are the RESIDENT control build, which carries
# every decoder; the shipped build's resident code is a third of that, so
# holding it to 153,804 B would let it triple before anything complained —
# which is the "a test that passes may not be testing anything" trap in this
# repository's own CLAUDE.md.
#
# Set 2026-09-25, at the size each configuration was on the day overlays
# became the build. Moved deliberately, in the commit that moves it, and
# say what the bytes bought: on this target every byte of resident code is a
# byte off the budget of every extraction.
#
# The figures are tools/budgets.txt's, with every other size this tree
# asserts about its builds: tools/retake_budgets.py rewrites them from the
# builds, which is the deliberate step, and the commit says what the bytes
# bought. Their history is that file's git log and DECISIONS.md; it was
# kept here, a paragraph a change, until 2026-11-13.
. tools/budgets.txt           # the cwd is the repository root (above)
if [ -n "$UNC_OVL_RESIDENT" ]; then
    UNC_MAC_MAX_CODE=${UNC_MAC_MAX_CODE:-$UNC_MAC_CODE_DEFAULT}
    UNC_MAC_MAX_A5=${UNC_MAC_MAX_A5:-$UNC_MAC_A5_DEFAULT}
elif [ -n "$UNC_OVL_LAZY" ]; then
    UNC_MAC_MAX_CODE=${UNC_MAC_MAX_CODE:-$UNC_MAC_CODE_LAZY}
    UNC_MAC_MAX_A5=${UNC_MAC_MAX_A5:-$UNC_MAC_A5_LAZY}
else
    UNC_MAC_MAX_CODE=${UNC_MAC_MAX_CODE:-$UNC_MAC_CODE_EAGER}
    UNC_MAC_MAX_A5=${UNC_MAC_MAX_A5:-$UNC_MAC_A5_EAGER}
fi
SIZE="$TOOLCHAIN/bin/m68k-apple-macos-size"
GDB="$BUILD_DIR"/MacExtract.code.bin.gdb
# A ceiling that is not a number compares as nothing and the check passes
# on it — which a rebase placeholder did once, and ci.sh went green with
# "ceiling RATCHET B" on its screen (2026-09-19). Refuse it.
case "$UNC_MAC_MAX_CODE$UNC_MAC_MAX_A5" in
    *[!0-9]*) echo "mac: FAIL — a ratchet ceiling is not a number: code '$UNC_MAC_MAX_CODE', A5 '$UNC_MAC_MAX_A5'" >&2; exit 1 ;;
esac
if [ -x "$SIZE" ] && [ -f "$GDB" ]; then
    # `size`'s text column still counts the MacsBug names after
    # --mac-strip-macsbug: Elf2Mac parks them in a NOLOAD section that keeps
    # its ALLOC flag, and no byte of it reaches a CODE resource. Subtract
    # that section so the figure is what the Segment Loader places
    # (DECISIONS.md 2026-10-22, *the names in the code*).
    names=$("$SIZE" -A "$GDB" | awk '$1 == ".strippedmacsbugnames" {print $2}')
    code=$(( $("$SIZE" "$GDB" | awk 'NR==2 {print $1}') - ${names:-0} ))
    a5=$("$SIZE" "$GDB" | awk 'NR==2 {print $2 + $3}')
    echo "mac: code $code B (ceiling $UNC_MAC_MAX_CODE B)"
    echo "mac: A5   $a5 B (ceiling $UNC_MAC_MAX_A5 B) — data + bss, and it"
    echo "mac:      costs the engine one for one, same as code" 
    if [ "$a5" -gt "$UNC_MAC_MAX_A5" ]; then
        over=$((a5 - UNC_MAC_MAX_A5))
        echo "mac: FAIL — data + bss is $over B over its ceiling." >&2
        echo "mac: that is $over B off every extraction's budget, exactly as" >&2
        echo "mac: code would be: data rides in CODE 1 and bss is a heap block" >&2
        echo "mac: (--mac-single), so both come out of the heap the engine is" >&2
        echo "mac: then given. Put the table in a RESOURCE, which is free until" >&2
        echo "mac: it is loaded. FORMATS.md, *What the application costs the engine*." >&2
        exit 1
    fi
    # mac/mac_start.c is the entry point and, unlike Retro68's _start, runs
    # no constructor and no destructor: the application has none. One added
    # anywhere — a C++ object, __attribute__((constructor)), a library that
    # registers one — would be linked and silently never run, so its list
    # being non-empty fails here (DECISIONS.md 2026-10-22, *the runtime the
    # application did not need*).
    NM="$TOOLCHAIN/bin/m68k-apple-macos-nm"
    if [ -x "$NM" ]; then
        bad=$("$NM" "$GDB" | awk '
            { a[$3] = $1 }
            END {
                n = split("__CTOR_LIST__:__CTOR_END__ __DTOR_LIST__:__DTOR_END__ __init_section:__init_section_end __fini_section:__fini_section_end", p, " ")
                for (i = 1; i <= n; i++) {
                    split(p[i], q, ":")
                    if (!(q[1] in a) || !(q[2] in a)) { print q[1] " (absent)"; continue }
                    if (a[q[1]] != a[q[2]]) print q[1]
                }
            }')
        if [ -n "$bad" ]; then
            echo "mac: FAIL — not empty, and mac/mac_start.c would never run it: $bad" >&2
            echo "mac: either remove the constructor or make mac_start.c call" >&2
            echo "mac: Retro68CallConstructors / Retro68CallDestructors." >&2
            exit 1
        fi
        echo "mac: constructors, destructors, .init, .fini: none (mac_start.c runs none)"
        # mac/fm_inline.h expands seven File Manager calls at each call
        # site. A call GCC chose not to expand, or a pointer taken to one,
        # links Retro68's library copy instead and compiles without a word;
        # fail on it (DECISIONS.md 2026-11-11, *the glue the shell expands*).
        glue=$("$NM" "$GDB" | awk '$3 ~ /^(FSREAD|FSWRITE|SETFPOS|GETEOF|SETEOF|FLUSHVOL|FSCLOSE)$/ {print $3}' | tr '\n' ' ')
        if [ -n "$glue" ]; then
            echo "mac: FAIL — library File Manager glue linked: $glue" >&2
            echo "mac: mac/fm_inline.h expands these; find the call it did not." >&2
            exit 1
        fi
        echo "mac: File Manager glue linked: none of the seven mac/fm_inline.h expands"
        # gDirMemo is placed on Retro68ApplyRelocations by the link
        # (mac/CMakeLists.txt) and spans into Retro68Relocate: both are run
        # once by mac/mac_start.c before main and never again. Fail a link
        # where anything else starts inside the span, or the span is shorter
        # than the memo's kDirMemo rows of 8 B.
        rows=$(sed -n 's/^#define kDirMemo \([0-9][0-9]*\).*/\1/p' mac/macextract_mac.c)
        memo=$("$NM" -S -n "$GDB" | awk -v need=$((rows * 8)) '
            function h(x,   i, v) {
                v = 0
                for (i = 1; i <= length(x); i++)
                    v = v * 16 + index("0123456789abcdef", substr(tolower(x), i, 1)) - 1
                return v
            }
            NF == 4 && $4 == "Retro68ApplyRelocations" { a = h($1) }
            NF == 4 && $4 == "Retro68Relocate" { r = h($1); e = h($1) + h($2) }
            NF >= 3 && $NF == "gDirMemo" { m = h($1) }
            { if (NF >= 3) { addr[NR] = h($1); name[NR] = $NF } }
            END {
                if (!a || !r || m != a || r < a || need <= 0) { print "unplaced"; exit }
                for (i in addr)
                    if (addr[i] > a && addr[i] < e && name[i] != "Retro68Relocate" &&
                        name[i] != "gDirMemo" && name[i] != "Retro68ApplyRelocations") {
                        print "shares its span with " name[i]; exit }
                if (e - a < need) { print "needs " need " B, the span is " e - a; exit }
                print "ok " e - a " " need
            }')
        case "$memo" in
            ok*) echo "mac: gDirMemo on the relocator: ${memo#ok } B (span, need)" ;;
            *)   echo "mac: FAIL — gDirMemo on the relocator: $memo" >&2
                 echo "mac: mac/macextract_mac.c says what it rests on." >&2
                 exit 1 ;;
        esac
    else
        echo "mac: no m68k nm — the constructor guard NOT checked"
    fi
    if [ "$code" -gt "$UNC_MAC_MAX_CODE" ]; then
        over=$((code - UNC_MAC_MAX_CODE))
        echo "mac: FAIL — code is $over B over the ceiling." >&2
        echo "mac: that is $over B off every extraction's budget on a 1 MB Mac" >&2
        echo "mac: Plus. If deliberate: tools/retake_budgets.py, or put the new" >&2
        echo "mac: material in resources or tables, which cost nothing." >&2
        echo "mac: FORMATS.md, *What the application costs the engine*." >&2
        exit 1
    fi
else
    echo "mac: no m68k size tool — code ceiling NOT checked"
fi

echo "mac: OK — this only proves it compiles. tools/vmac/run.py replays fixtures"
echo "mac: on a real emulated Mac Plus; tools/vmac/README.md is how to run it."

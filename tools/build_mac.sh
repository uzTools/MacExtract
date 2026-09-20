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
# Raised again 2026-09-09 from 147,588 to 149,756: +2,168 B for DART, the
# first format here whose output is a file of its own format (DECISIONS.md
# 2026-09-09). Bought on the same terms as every other format — one engine,
# not a Macintosh subset of one — and the one that most earns it on this
# target: what a compressed DART is FOR is mounting, and MacMount refuses
# one until something expands it.
# Raised 2026-09-18 from 149,756 to 149,832: +76 B for the LZ coders that
# hand their output back a run at a time out of their own windows instead
# of a byte at a time through a pointer, net of 158 B Arsenic gave back by
# writing through the fork writer (DECISIONS.md 2026-09-18). A first
# version cost 468 B; a flush is a loop and a call, and one site per coder
# was the difference. Bought for −2.4 to −9.4 % of instructions on the
# formats that use them.
# Raised 2026-09-19 from 149,832 to 149,868: +36 B for the three-byte
# inverse-BWT transform vector — the two byte-wise accessors against one
# long load. A quarter off the engine's largest allocation, two corpus
# archives onto the fast path at 1 MB (DECISIONS.md 2026-09-19).
# Raised 2026-09-19 from 149,868 to 150,896: +1,028 B for UNC_HOT on Compact
# Pro's two functions, unc_cpt_lzh_fork and cpt_rle_push, priced with the
# tick probe on a 7 MHz Mac Plus: engine 10,256 -> 8,735 ticks on
# derived-XferIt_1.5b4.sea, -14.8 % of every Compact Pro extraction and of
# DiskDoubler method 8 (DECISIONS.md 2026-09-19, the second entry).
# Raised 2026-09-19 from 150,896 to 150,928: +32 B for Now Compress's block
# slots, which slide the history window once per four blocks instead of
# once per block: engine 945 -> 793 ticks on derived-Expand_Now_1.0.1.sea,
# -16.1 %, on a 7 MHz Mac Plus. Its UNC_HOT marks were measured on the same
# run at 0.3 % for 1,152 B and refused (DECISIONS.md 2026-09-19, third entry).
# Raised 2026-09-19 from 150,928 to 151,684: +756 B for building the two DES
# SP tables and Compact Pro's CRC-64 table at key setup instead of carrying
# them as const data — which took 5,588 B OUT of the A5 world (below), so
# the budget is 4,832 B better off on every extraction and the tables cost
# 2 KB of heap only while an encrypted entry is decoded (DECISIONS.md
# 2026-09-19, the transient tables). More code than the 300 B estimated:
# the generator is two S-box conventions and a CRC loop at -Os.
# LOWERED 2026-09-19 from 151,684 to 151,572: −112 B, the -lh1- coder's
# tree machinery rewritten from the published LZHUF instead of XADMaster's
# transcription of it — and 10.1 % faster on the Plus, 6.5 KB less heap
# (DECISIONS.md 2026-09-19, the tree that was Yoshizaki's).
# LOWERED 2026-09-19 from 151,572 to 151,156: −416 B, StuffItDES folded onto
# standard DES's round — one SP table kind instead of two, and revbits and
# the second round function gone. The whole fall is inside unc_crypt.c.obj
# (9,676 → 9,260 B); A5 and peak heap are unchanged, both measured
# (DECISIONS.md 2026-09-19, the DES that was only wearing a disguise).
# Raised 2026-09-19 from 151,572 to 152,060: +488 B for Arsenic rewritten
# from Russotto's write-up with bzip2's two-level MTF and a grouped symbol
# search — derived-a2basic.dmg.sit's engine time on a 7 MHz Plus 29,885 ->
# 18,922 ticks, -36.7 %, peaks 1.4 KB lower (DECISIONS.md 2026-09-19, the
# rank that was walked a byte at a time).
# Rebased 2026-09-19: the two entries above landed from two sessions, and the
# ceiling is the rebased build's measured size, not either side's number.
# Raised 2026-09-19 from 151,644 to 151,720: +76 B for Compact Pro's LZH and
# RLE stages fused — a match copied out of the window and run through the RLE
# in one pass, and the run-length expansion written into the staging buffer
# rather than a byte at a time through a call. −33 % of the 68000
# instructions on derived-XferIt_1.5b4.sea and on
# derived-Guy_s_Mac_Consultants.cpt, −44 to −47 % of Linux Ir on DiskDoubler
# method 8, peak heap unchanged on all 245 fixtures of the two formats, and
# A5 12 B LOWER (DECISIONS.md 2026-09-19, the byte that went to two places
# at once).
# LOWERED 2026-09-19 from 151,720 to 151,696: −16 B for the run-length
# threshold that the entry above says is not there and that the first commit
# left in the file set to 1, and −8 B for making cpt_rle_emit's error sticky
# (+8 B of A5, so that half is free rather than cheap).
# Raised 2026-09-19 from 151,696 to 151,836: +140 B for LZH's static and
# LArc decoders rewritten from lhasa, with the match copied into the window
# and the writer's staging buffer in one pass instead of walked out a call
# per byte. −17.8 % of the 68000's instructions on aminet-lha_68k.lha,
# −20.1 % on the -lh7- fixture and −46.4 % on LArc's long.lzs, engine
# 3,527 → 3,046 ticks (−13.6 %) on a 7 MHz Mac Plus, peak heap identical on all 168 LZH
# specimens (DECISIONS.md 2026-09-19, the match that was walked twice).
# Two cheaper shapes were measured and refused there, and UNC_HOT on the
# new copy loop cost 416 B for 3.8 % MORE instructions.
# Raised 2026-09-19 from 151,836 to 151,976: +140 B for the LZW decoder
# rewritten on the public compress(1) description (and −8 B from the
# canonical Huffman codes rewritten on RFC 1951, in the same commit). The
# decoder knows each string's LENGTH before it walks it, so it writes
# straight into the caller's buffer from the far end instead of staging the
# reversed string and copying it out; that copy was 17.8 % of a `.Z` run.
# On a 7 MHz Mac Plus, engine 713 → 646 ticks (−9.4 %) on
# `popper-1.7.tar.Z` and 2,850 → 2,801 (−1.7 %) on `derived-xmasbeeps.sit`
# — a fraction of the −23.0 % and −12.1 % the Linux counts showed, because
# the byte copy removed is what a 68000 does cheapest. Peak heap identical
# on all 113 fixtures that reach the decoder, because the length lives in
# the byte per symbol the staging array used to be (DECISIONS.md
# 2026-09-19, the buffer that became a length). Two shapes measured and
# refused there; a third — 128 B cheaper here for 1.5-3 % more Linux
# instructions and NOTHING a tick probe can see — was taken, which is what
# this ceiling is for.
# Raised 2026-09-20 from 151,976 to 152,216: +240 B for BinHex, where a
# character used to be touched three times — copied into the line buffer,
# scanned there for validity, looked up again when its six bits were
# wanted. The line is now taken out of the reader's own buffer in one
# scan for its terminator, judged and converted to 6-bit values in the
# same pass, and four characters become three bytes at once, two of them
# served from the decoder. −35.8 % of the 68000's instructions on
# macburger-helper.hqx and −36.8 % on a2basic-09.hqx, and on a 7 MHz Mac
# Plus engine 3,771 → 2,386 ticks, −36.7 % — the closest a 68000 count
# and a tick probe have come to agreeing here.
# All 238 B of it are inside fmt_binhex.c.obj (2,181 -> 2,419 B); the
# heap allocation is unchanged and so is the peak (DECISIONS.md
# 2026-09-20, the character that was touched three times).
UNC_MAC_MAX_CODE=${UNC_MAC_MAX_CODE:-152216}
# The A5 ratchet, added 2026-09-02 with the measurement that made it
# necessary: 16,384 B of .data cost 16,418 B of budget, so data is not free
# and never was (FORMATS.md, *What the application costs the engine*; the
# withdrawn claim is in BLOCKERS.md). Set at the size on the day, like the
# code ceiling: 44,096 B = 32,644 data + 11,452 bss. It had grown unwatched
# the whole time this file said data was free.
# Raised 2026-09-09 from 44,096 to 44,260: +164 B for DART, attributed by
# diffing the linked image's .data symbols — 28 B of type table, 20 B of
# format row, 4 B of probe pointer, 4 B on unc_strerror's switch table, and
# ~100 B of message text. The type table was 56 B in the first draft and
# holds one DIGIT per row instead of a whole OSType, which cost 8 B of code
# to save 24 B here: on this target both come off the same budget, so that
# is 16 B, and it is the second time composing a constant beat storing it
# (DECISIONS.md 2026-09-01, *two byte reads*).
# LOWERED 2026-09-19 from 44,260 to 38,652: −5,588 B, the two DES SP tables
# and the CRC-64 table gone from the A5 world (built at key setup instead;
# DECISIONS.md 2026-09-19, the transient tables). A ratchet is set at the
# size on the day, and that cuts both ways: what was given back is locked
# in, so growing back into it is a decision too.
# Raised 2026-09-19 from 38,652 to 38,668: +16 B with the same rewrite —
# rodata alignment around the 64-byte length table, not a new table.
# 2026-09-19: NOT raised for the LZH rewrite above, which took the A5 world
# from 38,640 to 38,660 B — 20 B of the 28 B of slack the same day's Compact
# Pro work left under this ceiling, and the slack is what a ratchet is for.
# LOWERED 2026-09-19 from 38,668 to 38,648 with the LZW and Huffman rewrite
# above: +8 B from the LZW decoder's new state and −20 B from the canonical
# Huffman build, which carries the code space left as a counter (puff.c's
# `left`, unsigned here) instead of comparing a running total against a
# shifted constant. Net −12 B, and a ratchet is set at the size on the day,
# so it is locked in.
# Raised 2026-09-20 from 38,648 to 38,664 with the BinHex work above:
# +16 B, and NOT a new table — fmt_binhex.c.obj carries no data at all,
# before or after. It is rodata alignment shifting under 240 B of new
# text, the same effect measured on 2026-09-19 (+16 B "rodata alignment
# around the 64-byte length table, not a new table").
UNC_MAC_MAX_A5=${UNC_MAC_MAX_A5:-38664}
SIZE="$TOOLCHAIN/bin/m68k-apple-macos-size"
GDB=build/mac/MacExtract.code.bin.gdb
# A ceiling that is not a number compares as nothing and the check passes
# on it — which a rebase placeholder did once, and ci.sh went green with
# "ceiling RATCHET B" on its screen (2026-09-19). Refuse it.
case "$UNC_MAC_MAX_CODE$UNC_MAC_MAX_A5" in
    *[!0-9]*) echo "mac: FAIL — a ratchet ceiling is not a number: code '$UNC_MAC_MAX_CODE', A5 '$UNC_MAC_MAX_A5'" >&2; exit 1 ;;
esac
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

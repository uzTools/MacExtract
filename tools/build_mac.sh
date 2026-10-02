#!/bin/sh
# build_mac.sh — cross-compile the Macintosh shell.
#
# Locates a Retro68 toolchain via (in order): $RETRO68, m68k-apple-macos-gcc
# in PATH, or /opt/Retro68-build/toolchain. Skips gracefully when absent.
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
# Raised 2026-09-20 from 152,216 to 152,356: +140 B for StuffIt method
# 13, which handed every output byte to unc_fork_put — `static inline`,
# but it carries a call to the flush, so gcc leaves it out of line at
# -Os and a 68000 profile put the jsr, its ten instructions and the rts
# at 13.6 % of a method-13 run. The decoder writes into its own window
# anyway, so the window is the staging buffer: runs are flushed from it
# through unc_fork_write, at a quarter of the window and at the end.
# derived-Ultimate_Copland_1.1.sit.1 on a 7 MHz Mac Plus, engine
# 4,395 → 3,867 ticks, −12.0 %; 68000 instructions −11.6 %; peak heap
# identical at 81,226 B, and 948 fixtures byte-identical against the
# old binary (DECISIONS.md 2026-09-20, the window that was already the
# staging buffer).
# LOWERED 2026-09-20 from 152,356 to 152,336: −20 B for Arsenic's two
# products, which went through libgcc's __mulsi3 because the 68000 has
# no 32x32 multiply. A model's total never passes its limit by more
# than one increment, so `low` and `freq[n]` are 11-bit numbers and
# only `renorm` needs 32 bits: two `mulu.w` and a shift is the
# identity, and it is SMALLER than the call it replaces. Engine
# 18,916 → 17,002 ticks on derived-a2basic.dmg.sit at 4 MB, −10.1 %
# (DECISIONS.md 2026-09-20, what a helper call costs that its count
# does not say).
# Raised 2026-09-21 from 152,336 to 152,392: +56 B for a Now Compress
# correctness fix, not an optimisation. The sliding history was sized
# from the archive's LARGEST FORK on the strength of a comment saying a
# back-reference cannot reach further than the fork has produced; the
# window spans MEMBERS, and an archive Now Compress itself wrote names
# offsets of 6,228 and 13,000 against a 6,000-byte window. The bound is
# now the SUM of every fork, still capped at 32 KB. No fixture's peak
# heap changes — every Now archive in the corpus already has a fork
# over 32 KB (DECISIONS.md 2026-09-21, the window that stopped at the
# fork; BLOCKERS.md, *Withdrawn claims*).
# LOWERED 2026-09-21 from 152,392 to 152,188 with Now Compress's coders
# rewritten from docs/formats/now-compress.md: −204 B, the 346-byte staging
# array for a shape-3 block's two code tables moved into the per-archive
# allocation the tables themselves live in, and the block table's checksum
# walks sharing one byte-sum. Engine 790 -> 792 ticks on
# derived-Expand_Now_1.0.1.sea at 7 MHz, which is the instrument's own
# resolution, and −616 B of this file's deepest call chain (DECISIONS.md
# 2026-09-21, asking the program that wrote it). A ratchet is set at the
# size on the day and that cuts both ways.
# Raised 2026-09-21 from 152,188 to 152,596 for StuffIt method 6's fixed
# code book, and this is a TRADE rather than growth: the 257-entry pair
# of tables it replaces was **A5**, not code, so the ceiling below came
# down 1,000 B in the same change. Net **−592 B off every extraction's
# budget on a 1 MB Mac Plus**, +1,028 B of transient heap while a
# method-6 fork is being read (peak 40,982 -> 42,010 on
# `derived-INITLoader.sit`), and 3 -> 3 engine ticks, which is that
# instrument's resolution. A one-loop zeroing of the two arrays was
# tried and is worth nothing: +4 B of code for −4 B of A5.
# DECISIONS.md 2026-09-21, *the table that was twenty-six bytes*.
# Raised 2026-09-22 from 152,596 to 153,176 for the UTF-8 fold: +580 B,
# measured on the one object before and after — `Utf8ToMacRoman` inlined
# into sink_begin (1,114 -> 1,596 B of .text) plus RepLostChars. Its
# table is A5 and is in the ceiling below, +316 B, so the fold costs
# **896 B off every extraction's budget on a 1 MB Mac Plus**, and what
# it buys is that StuffIt 5's names reach an HFS volume as names rather
# than as mojibake (DECISIONS.md 2026-09-22, *a name an HFS volume can
# hold*). Stack: sink_begin 400 -> 412 B, ExtractOne unchanged.
# Raised 2026-09-22 from 153,176 to 153,192 with the DiskDoubler DDAR
# walk: +16 B, and a TRADE — it steps by the record's own span and
# checks that against the file header's arithmetic, where it used to
# step by the header alone and skip what looked like a stray header.
# The A5 ceiling below came down 16 B in the same change, so the budget
# is unmoved (DECISIONS.md 2026-09-22, *the page that was never
# written*).
# Raised 2026-09-22 from 153,192 to 153,240 for the 1990 DiskDoubler
# header: +48 B linked, +46 B of object text (fmt_dd.c 8,888 -> 8,918,
# fmt_stubs.c 1,057 -> 1,073, `m68k-apple-macos-size` before and after).
# What that buys is a file neither this engine nor `unar` could open —
# 0xABCD0054 is the magic WORD 0xABCD and the header's own SIZE, and
# DiskDoubler ß05 of 1990 writes 48 (DECISIONS.md 2026-09-22, *the
# header that was a length*). The first draft cost 144 B and matched a
# word plus a RANGE, with the two length pairs standing in for the
# header CRC a short header does not have; taking only the two sizes
# that have specimens makes each one a whole 32-bit magic, which is
# stronger per byte and 96 B cheaper. Third time composing or
# constraining a constant has beaten storing one on this target.
# Raised 2026-09-23 from 153,240 to 153,256: +16 B for two bounds checks
# in fmt_now.c that refuse a stored or Huffman-then-LZSS block whose
# length exceeds its fork's output buffer — a heap overflow on crafted
# input, pre-existing, confirmed under ASan (DECISIONS.md 2026-09-23,
# the block that was bigger than its fork). Memory safety, so bought on
# any terms; A5 fell 16 B the same commit.
# --- and, on top of every entry above, what this branch itself costs ---
# +116 B for taking the engine's budget at its FIRST ALLOCATION rather than
# before the extraction, and from PurgeSpace rather than FreeMem. On a branch
# whose whole point is code that arrives after the budget was granted, that is
# a correctness fix and not a feature — see BRANCH_NOTES.md. It is 116 B off
# every extraction and it is bought knowingly.
# +72 B on 2026-09-02 for splitting five formats' probes out of their decoders
# (fmt_lzh_probe.c, fmt_cpt_probe.c, fmt_arc_probe.c, fmt_spacesaver_probe.c
# and the private headers that go with them). Each split costs a function
# prologue and a header include in the DEFAULT build, which carries both
# halves anyway. It is bought for what it buys on the overlay build, where the
# decoders are not resident at all: 42,044 B of code and 17,040 B of A5 world
# (BRANCH_NOTES.md).
# +228 B the same day for the second pass of probe splits (StuffIt, StuffIt 5,
# PackIt, btoa, BinHex, SuperDisk!, uuencode, base64, MIME). What it buys is
# on the overlay build, where the resident set falls to 73,052 B of code and
# 22,036 B of A5 world — and where the largest single CODE resource, the thing
# a small machine has to place, falls from 142,152 B to 67,600 B.
# +32 B for splitting fmt_exo's four probes out (gzip, Unix compress, tar,
# zip). The last of the splits, and the one that let zlib leave the resident
# build with its decoder.
# +76 B on 2026-09-09 for splitting DART's probe out. DART's probe IS its
# header reader — the format has no signature — so dart_parse, dart_kind and
# dart_chunk_bytes stop being static and stop being inlined into the decoder.
# What it buys is on the overlay build, where a decoder leaves the resident
# set entirely.
# Merged main 2026-09-24. The running totals these entries used to carry were
# main's ceiling of the day plus the deltas above, and main's has moved 5,668 B
# since; what each change cost stands, the totals do not, so the ceiling below
# is the merged build MEASURED rather than that arithmetic.
# LOWERED 2026-09-25 from 153,804 to 151,584: DART left the engine, and on
# this configuration it was all resident (-2,220 B).
# RAISED 2026-09-26, +4 B, and here is what the 4 B bought: arc_retryable()
# in src/fmt_arc.c, a named predicate replacing two inline comparisons, so
# that a garbled ARC entry whose stream ran SHORT is retried with the
# password instead of refused (DECISIONS.md 2026-09-26, *the guard that was
# on the other side*). It costs the RESIDENT control 4 B and the shipped
# build 0 — fmt_arc is in an overlay there — which is also how it got in:
# nothing built this configuration. `ci.sh` builds it since the same day.
# RAISED 2026-10-01, the CONTROL ONLY, for zip's four Macintosh extra
# fields: Info-ZIP's 0x334d and ZipIt's 0x2605/0x2705/0x2805, which carry
# the type, creator, Finder flags and dates a Macintosh-written zip has
# always held and this engine read none of (DECISIONS.md 2026-10-01).
# Resident 152,068 -> 154,092; **the shipped build did not move at all**,
# eager code and A5 both +0, because every byte of it is in the
# `ovl_exo` image, which went 27,252 -> 29,252 and is released for every
# archive that is not a zip. So this is 2,024 B off every extraction in
# the control and 0 B in what ships — the widest that gap has been, and
# the reason the overlay build exists.
# `run_tiers.py --check` moves no tally on either lane with the images
# and the resident budgets re-taken: 71/71, 67/71, 64/71 resident at
# 651,508 / 222,620 / 127,220, and 71/71, 69/71, 66/71 shipped, the same
# fixtures by name. What it costs the control is headroom — the narrowest
# passing fixture at sys6-512K keeps about 10,436 B of its 12,460.
# What the bytes bought: a zip written on a Macintosh extracts with its
# Finder metadata, and a ZipIt entry gives back BOTH FORKS instead of a
# MacBinary stream in the data fork. dist/README.txt's "type and creator
# codes and dates all survive" was false for zip until this.
UNC_MAC_CODE_DEFAULT=158116
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
# LOWERED 2026-09-20 from 38,664 to 38,652 with the method-13 work
# above: −12 B, the two dead branches' error constants gone with the
# per-byte put. A ratchet is set at the size on the day, and that cuts
# both ways.
# LOWERED 2026-09-20 from 38,652 to 38,640 with the Arsenic work above:
# −12 B more.
# Raised 2026-09-21 from 38,640 to 38,648 with the Now Compress fix
# above: +8 B, and NOT a new table — measured, `m68k-apple-macos-size`
# on that one object before and after: text 4,658 -> 4,712, data 0,
# bss 0. It is rodata alignment shifting under the new text, the same
# effect measured twice on 2026-09-19 and 2026-09-20.
# Raised 2026-09-21 from 38,648 to 38,660 with the Now Compress rewrite
# above: +12 B, and NOT a new table — measured, `m68k-apple-macos-size` on
# that one object before and after: data 0, bss 0, rodata 270 -> 270, with
# only its text moving. It is rodata alignment shifting under changed text,
# the same effect measured on 2026-09-19, -20 and -21, and the code ceiling
# came down by 204 B in the same change.
# LOWERED 2026-09-21 from 38,660 to 37,660 with the method-6 work: the
# fixed code book was 1,028 B of `.rodata` in the A5 world (measured on
# the object alone, `m68k-apple-macos-size`: text 0, data 8, rodata
# 1,028) and is now 26 bytes plus a builder that costs 408 B of code.
# A ratchet is set at the size on the day and that cuts both ways.
# Raised 2026-09-22 from 37,660 to 37,976 with the UTF-8 fold above:
# +316 B, and it IS a new table — measured on that one object before and
# after, `.rodata` 11 -> 268 B for MacRoman's 128-entry high half, and
# `.rodata.str1.1` 1,862 -> 1,915 B for the one report line it adds.
# LOWERED 2026-09-22 from 37,976 to 37,960 with the DDAR walk above:
# -16 B. A ratchet is set at the size on the day and that cuts both ways.
# Raised 2026-09-22 from 37,960 to 37,976 with the 1990 DiskDoubler
# header above: +16 B, and NOT a new table — measured, both objects
# carry ZERO data before and after (`m68k-apple-macos-size`). It is
# rodata alignment shifting under 46 B of new text, the same effect
# measured on 2026-09-19 and 2026-09-20. Total cost on a 1 MB Mac Plus:
# 64 B, code and A5 together, both coming off the budget one for one.
# LOWERED 2026-09-23 from 37,976 to 37,960 with the fmt_now.c bounds
# checks above: -16 B of rodata alignment shifting under the +16 B of
# new text, the same one-for-one effect (DECISIONS.md 2026-09-23, the
# block that was bigger than its fork).
# --- and what this branch itself costs on top of them ------------------
# Nothing, and that is measured rather than assumed. The splits cost this
# branch +20 B of A5 world on 2026-09-02 and +20 B on 2026-09-09; after
# merging main on 2026-09-24 the branch's A5 world is 37,956 B, which is
# 4 B BELOW main's own ceiling of 37,960. The 40 B is not there to be found:
# both entries were rodata alignment shifting under changed text, the effect
# main's own A5 history records four times, and it has since shifted back.
# A ratchet is set at the size on the day, so 37,956 was what was locked in.
# LOWERED 2026-09-25 from 37,956 to 37,792 with DART's removal (-164 B).
# LOWERED 2026-09-26, −4 B, at the size on the day: the same change moved
# 4 B out of the A5 world as it put 4 B into code. A ratchet is lowered on
# the terms it is raised.
UNC_MAC_A5_DEFAULT=37884
# A CEILING PER CONFIGURATION, because one ceiling measured on another build
# cannot fire. The figures above are the RESIDENT control build, which carries
# every decoder; the shipped build's resident code is a third of that, so
# holding it to 153,804 B would let it triple before anything complained —
# which is the "a test that passes may not be testing anything" trap in this
# repository's own CLAUDE.md.
#
# Set 2026-09-25, at the size each configuration was on the day overlays
# became the build. Raise one deliberately, in the commit that grows it, and
# say what the bytes bought: on this target every byte of resident code is a
# byte off the budget of every extraction.
# LOWERED 2026-09-25 when DART left the engine: eager 54,028 -> 53,332,
# lazy 52,600 -> 51,956, resident 153,804 -> 151,584, with the A5 figures
# following. A ratchet is lowered on the same terms it is raised — at the
# size on the day — so that what a format gave back cannot be spent by
# accident later (DECISIONS.md 2026-09-25, *the disk images that found
# another home*). Most of DART was in its own image, which is why the
# shipped build gives back 696 B of code where the resident one gives
# back 2,220 B.
# MOVED 2026-09-26 by the Compact Pro segment identity check, and it moved
# both ways: code +24 B in all three configurations, A5 **-24 B** in eager
# and lazy and +8 B in the resident control. Rodata crossing between the
# two columns under changed text, which is why the shipped build's total
# footprint is unchanged and its CODE ceiling still had to rise: they are
# separate ceilings, and a byte of resident code is a byte off every
# extraction's budget where a byte of A5 is already paid for.
#   eager     53,332 -> 53,356   A5 18,988 -> 18,964
#   lazy      51,956 -> 51,980   A5 19,084 -> 19,060
#   resident 151,588 -> 151,612  A5 37,788 -> 37,796
# Each measured against a build with src/fmt_cptseg.c reverted, so every
# figure is this change's and nothing else's. The two A5 ceilings are
# LOWERED on the same terms they would be raised — at the size on the day —
# so the 24 B this gave back cannot be spent later by accident.
# What the bytes bought: `unc_cptseg_probe` no longer claims a file from
# another format. A real AppleLink package, `Read First.PKG`, is
# `01 01 00 00` with a zero index and was sniffed as the first segment of a
# Compact Pro set until this commit (DECISIONS.md 2026-09-26, *the bargain
# that was finally paid*).
# LOWERED 2026-09-27, all six ceilings, at the size on the day: the
# AppleLink `.pkg` probe was removed once the routine it transcribed turned
# out to be the StuffIt translator API's COMMAND parser rather than a file
# test (DECISIONS.md 2026-09-27, *the recogniser that was a command line*).
# Eager code 53,356 -> 52,884 and A5 18,964 -> 18,940; lazy 51,980 ->
# 51,508 and 19,060 -> 19,036; resident 151,612 -> 151,140 and 37,796 ->
# 37,724. That is **496 B off every extraction's budget on a 1 MB Mac
# Plus**, given back, and a ratchet is lowered on the same terms it would
# be raised so that it cannot be spent later by accident.
# RAISED 2026-09-28, all six, for the StuffIt add-on module fields — the six
# header bytes and the 0x40 flag that say a fork went through an Optimizer,
# a Compressor or an Encryptor module (FORMATS.md, *Where an archive names
# the module*). Eager code 52,884 -> 52,972 and A5 18,940 -> 18,964; lazy
# 51,508 -> 51,596 and 19,036 -> 19,060; resident 151,140 -> 151,432 and
# 37,724 -> 37,768. **112 B off every extraction on a 1 MB Mac Plus in the
# shipped build**, and 336 B in the control — the difference is that most of
# this lands in the StuffIt 'OVLY' image, which grew 208 B and is released
# for every archive that is not a StuffIt one.
# RAISED AGAIN the same day, control only, 151,432 -> 151,492 and 37,768 ->
# 37,772: the rule that an Optimizer nothing can undo is DECODED rather than
# refused (FORMATS.md, *What Aladdin's own output says*). **The shipped
# build does not move at all** — that code is in the StuffIt image, which
# grew 48 B — so this costs a 1 MB Mac Plus nothing and the control 64 B.
# What the bytes bought: a fork whose method byte says an Optimizer ran
# decodes fine and yields the OPTIMIZED bytes — a text file with its
# resources deleted, under the original's name, with the header's CRC
# agreeing. It is refused per entry now instead. `run_tiers.py --check`
# moves no tally in either lane with the images re-taken: 71/71, 67/71,
# 64/71 resident and 71/71, 69/71, 66/71 shipped, the same fixtures by name.
# RAISED 2026-09-29, all six, for UNDOING the 2.0 Optimizers rather than
# refusing them: `Sound 1` and `Photoshop 1` delta-code a fork and are undone
# exactly, and `MacPaint 1`'s remnant is rebuilt into a valid painting
# (FORMATS.md, *What an Optimizer did to the fork*). Eager code 52,972 ->
# 53,216 and A5 18,964 -> 19,008; lazy 51,596 -> 51,840 and 19,060 ->
# 19,104; resident 151,492 -> 152,068 and 37,772 -> 37,820. **288 B off
# every extraction on a 1 MB Mac Plus in the shipped build**, 624 B in the
# control — the gap is the StuffIt 'OVLY' image, which carries most of it
# and is released for every archive that is not a StuffIt one. The two
# filters themselves are in `unc_fork_flush`, which is resident because
# every format funnels through it; 44 B of the A5 figure is one sentence
# the Macintosh report needs, because a file that is not the one that was
# archived cannot come out under its name in silence.
# What the bytes bought: an entry `Sound 1` or `Photoshop 1` optimized now
# extracts BYTE FOR BYTE with the archive's own CRC-16 agreeing, and one
# `MacPaint 1` optimized extracts as the same valid document StuffIt Deluxe
# itself gives back. Three of the five Optimizers, where the day before
# every one of them with a 'DCMP' was refused. `run_tiers.py --check` is
# what says whether it cost a fixture.
UNC_MAC_CODE_EAGER=53216
UNC_MAC_A5_EAGER=19008
UNC_MAC_CODE_LAZY=51840
UNC_MAC_A5_LAZY=19104
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

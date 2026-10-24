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
# RAISED 2026-10-02 to 158,972: StuffIt 2.x's five ciphers (above).
# The CONTROL carries them resident where the release has them in the
# crypt overlay, which is the whole point of the control — +856 B of
# code and +8 of A5 here against +8 and -8 in what ships.
# RAISED 2026-10-03 to 161,596, the CONTROL ONLY: StuffIt method 14
# (src/sit14.c, 2,613 B of text and no data or bss at all, measured off
# the object). **The shipped build did not move**, eager code and A5
# both +0, because the decoder goes in the `ovl_stuffit` image — 23,670
# -> 26,274 B, read at launch and released for every archive that is
# not a StuffIt one. 4 B of the 2,624 came out of the A5 world below,
# which is the rodata-alignment effect this file records either way.
# What the bytes bought: the 80 entries of StuffIt Deluxe 7.0.3's own
# installer and the 71 of 5.5's that this engine listed and refused
# (DECISIONS.md 2026-10-03).
# RAISED 2026-10-05 to 163,744, the CONTROL ONLY: the AppleLink package
# decoder (src/fmt_sqp.c, 1,474 B of m68k text) and its resident probe
# (src/fmt_sqp_probe.c, 666 B), plus the engine's table row and the
# shim. The SHIPPED build pays the 740 B that is the probe and the
# dispatch; the decoder itself is in the new `ovl_sqp` image, 1,972 B,
# read at launch and released for every archive that is not a package
# (DECISIONS.md 2026-10-05).
# +316 on 2026-10-05 for the zip-behind-a-stub probe (see the eager
# pair below): resident and shipped moved by the same 316 B, which is
# what says none of it went into an overlay image.
# RAISED 2026-10-05 to 164,080, the CONTROL ONLY, +20: PackIt's resync
# for an entry nothing can decrypt now steps the eight-byte cipher grid
# its own writer pads to instead of scanning byte-wise, which is
# PackIt III 1.3's arithmetic rather than macutils' loop
# (src/fmt_packit.c; FORMATS.md, *PackIt's two ciphers*). **A5 fell by
# the same 20** — the rodata-alignment effect this file records either
# way — so CODE + A5 is 201,984 B in the control for the second build
# running and OVL_SAVED does not move. The SHIPPED build did not move
# at all: the decoder is in `ovl_packit`, 2,648 -> 2,672 B.
# Raised 2026-10-06 from 164,080 to 164,324: +244 B for the uu and BinHex
# work of that day — the per-document alphabet test
# (`unc_uu_line_is_data`) and DeHQX's part separator in
# `src/fmt_binhex.c`. Both files are in an overlay in both SHIPPED
# lifetimes, so this is the control carrying what the release does not,
# and OVL_SAVED rises by the same 256 B that CODE + A5 does here
# (FORMATS.md, *Three configurations, one tree*). The shipped pair moved
# +8 of CODE and −8 of A5: net nothing.
# +328 of CODE on 2026-10-07 for the folder-depth rule. This control
# carries every decoder resident, so it pays for the per-format half
# too — 208 B of the 328 — where the shipped pair pays 120 and keeps
# the rest in 'OVLY' images (the eager pair below, and DECISIONS.md
# 2026-10-07).
# RAISED 2026-10-07, 164,408 -> 166,264, by **1,856 B of CODE and 0 of
# A5** for zip method 6 (Implode). This is the whole price of the
# format, and it is paid HERE and nowhere else: `src/fmt_exo.c` is in
# `ovl_exo`, so the eager and lazy pairs below do not move by a single
# byte and nothing comes off any extraction's budget. The image is
# 29,252 -> 31,176 B (run_tiers.py's IMAGES) and the download 225,408 ->
# 227,328 B. The standing estimate for this format was "~1.5-2 KB of
# CODE, estimated, never measured"; 1,856 B of a build nothing ships is
# what it turned out to be (DECISIONS.md 2026-10-07, *the method that
# was out for a premise with no halves left*; FORMATS.md, *Implode*).
# RAISED 2026-10-08, 166,264 -> 166,932, by **668 B of CODE and 4 of A5**
# for PKZIP 1.01/1.02's minimum match length: the rule itself is one
# ternary, and the rest is the probe that decides which of the two
# readings an archive wants — a decode of ONE entry with no output,
# graded by the CRC-32 the archive stored. Paid here and nowhere else
# again: `src/fmt_exo.c` is in `ovl_exo`, so the eager and lazy pairs
# below do not move by a byte, the image is 31,176 -> 31,832 B
# (run_tiers.py's IMAGES) and the download 227,328 -> 227,840 B — this
# read 227,968 until 2026-10-08, against a committed dist/ of 227,840
# and FORMATS.md's own figure, so it was one block out. What
# the bytes bought: three entries of PKZIP 1.01's own distribution,
# refused with a checksum error the day before, come out byte-exact
# (DECISIONS.md 2026-10-08, *the second attempt that had nowhere to
# go*; FORMATS.md, *Implode*).
# RAISED 2026-10-08 again, 166,884 -> 167,036, by 152 B: the recovery that
# bounds a wrong per-archive verdict to the entry it was wrong about —
# one probe under the other reading, on an entry that has ALREADY failed,
# and the archive back to unsettled afterwards. Paid in `ovl_exo` and not
# resident: the shipped pair is unmoved at 54,272 and 19,056, the image
# goes 31,784 -> 31,936 B and the bundle 158,600 -> 158,752. What the
# bytes bought: a mixed archive costs the one entry whose verdict was
# wrong instead of every entry after it, measured on a three-entry
# subject (DECISIONS.md 2026-10-08, *the writer a zip is allowed to have
# twice*; TESTING.md, *Implode*, lane 4).
# RAISED 2026-10-08 a third time, 167,036 -> 168,200, by 1,164 B for zip
# method 1, Shrink, which joined the scope the same day. Paid in the
# images and not resident: the shipped pair is unmoved, `ovl_codecs` goes
# 6,404 -> 7,520 B, `ovl_exo` 31,936 -> 32,036, the bundle 158,752 ->
# 159,968 and the download 228,096 -> 229,248. The decoder is in
# `src/unc_lzw.c` and so in the CODECS image, not in `ovl_exo` beside the
# zip reader that calls it, because `ovl_exo` would not link: past 32 KB
# a 68000 `-mpcrel` image's 16-bit PC-relative references stop reaching
# (FORMATS.md, *Shrink*; DECISIONS.md 2026-10-08, *the method a
# Macintosh wrote once*).
# RAISED 2026-10-09, 168,200 -> 169,816, by 1,616 B for Aladdin Private
# File: here the reader is resident too, so this is the whole of it —
# 1,248 B of reader that the shipped builds keep in `ovl_stuffit`, and
# the same 368 B of probe, shims and table row they pay (eager pair,
# below). LOWERED the same day to 169,796, -20: RC4's indices kept in
# registers and the reader's record kept once, both in images when
# shipped and so resident only here. LOWERED again to 169,784, -12: the
# Private File footer read through unc_read_full rather than a bare call
# (DECISIONS.md 2026-10-09, *the read nothing sent short*).
# RAISED the same day, 169,784 -> 169,880, +96: Shrink ticks after every
# partial clear (+76 in `unc_shrink_decode`) and the zip peek returns a
# Cancel (+20 in `unc_zip_extract`). Both in images when shipped — the
# eager pair is unmoved, `ovl_codecs` 7,520 -> 7,628 and `ovl_exo` 32,036
# -> 32,056 — and a crafted stream of clears had ~17 minutes of a Mac
# Plus between ticks without them (FORMATS.md, *Shrink*).
# RAISED the same day, 169,880 -> 169,908, +28: zip's two dry passes put
# `done` back after they decode, so the progress bar counts an entry once
# (DECISIONS.md 2026-10-09, *the bar that counted the peek*); `ovl_exo`
# 32,056 -> 32,084 when shipped, the eager pair unmoved.
# RAISED the same day, 169,908 -> 170,044, +136: DiskDoubler moves its
# cursor inside the buffer it already holds instead of re-reading it
# (`ddn_seek` +72, `dd_fork` +74 at the overlay's flags), and MacLHA's peek
# and uuencode's scan stop counting input twice (DECISIONS.md 2026-10-09,
# *DiskDoubler read every block six times*). In images when shipped:
# `ovl_cptdd` +144, `ovl_lzh` +18, `ovl_text` +8, the eager pair unmoved.
# RAISED 2026-10-10, 170,044 -> 170,056, +12, with the A5 ceiling's -12:
# a method-13 fork's encryptor id is not read (DECISIONS.md 2026-10-10,
# *the installer's own key*). The total is unmoved; the A5 side was not
# attributed per symbol. `ovl_stuffit` +24 when shipped, the eager pair
# unmoved.
# RAISED 2026-10-11, 170,056 -> 171,232, +1,176 B for zip Reduce, methods
# 2-5: the decoder, its call, and the shim's patch of `ovl_zipold` into the
# vector. Shipped, the decoder is in that image beside Shrink and the
# eager pair pays only the keep and the patch (FORMATS.md, *Reduce*).
# LOWERED the same evening to 171,224, -8, with both decoders made faster.
# RAISED the same day to 171,952, +728, for `JPEG Lossy` at every width
# and mode (DECISIONS.md 2026-10-11, *the constant was a square*); A5
# fell 24 to 37,984 and its ceiling is left. Shipped, all of it is in
# `ovl_stuffit`, 27,938 -> 28,614 B, the eager pair unmoved.
# RAISED 2026-10-11 to 172,048, +96, for the LC 475's zip and top-folder
# fixes (the eager pair above names the pieces): ExtractOne +38, sink_begin
# +58. No overlay here, so nothing quits. A5 unmoved at 37,984: `gTopLost`'s
# byte went into padding.
# LOWERED 2026-10-12 to 172,040, -8, for the menu bar and the titled
# progress window, the same pieces as the eager pair below (+180 on the
# first commit, before the shell was trimmed). A5 37,992, +8, under its
# ceiling: `.data` alignment.
# RAISED 2026-10-12 to 172,064, +24, for the Finder's list read by
# position rather than through a pointer into a block that can move: all
# of it `main`, where DropNext is inlined. No overlay here, so no reload.
# A5 38,000, +8, `_sdata`'s padding (DECISIONS.md 2026-10-12, *the reload
# that the list needs*).
# RAISED 2026-10-12 to 172,392, +328, for Arsenic's progress while it
# decodes a block and builds either inverse (DECISIONS.md 2026-10-12, *the
# block nobody could cancel*). A5 37,992, -8, alignment, under its ceiling.
# Shipped, all of it is `ovl_stuffit`, 28,614 -> 28,926 B (+312 at the
# overlay's flags), the eager pair unmoved.
# RAISED 2026-10-13 to 172,620, +228, for MIME's progress (the input its
# writing passes consumed, through a relay) and its walk passing a Cancel
# up instead of ending the message (DECISIONS.md 2026-10-13, *the mail
# that counted itself three times*). A5 37,988, -4, alignment. Shipped,
# all of it is `ovl_text`, 11,510 -> 11,750 B, the eager pair unmoved.
# RAISED 2026-10-13 to 172,876, +256, for ejecting the disk a split
# set's last part came from before asking for the next (DECISIONS.md
# 2026-10-13, *the disk that was still in the drive*). A5 37,924, -64:
# the two messages are DITLs, and `.data` alignment.
# RAISED 2026-10-14 to 172,956, +80, for unmounting that disk as well as
# ejecting it (DECISIONS.md 2026-10-14, *the icon the eject left behind*).
# A5 37,940, +16, alignment.
# RAISED 2026-10-14 to 175,312, +2,356, for `.hex` and `.hcx`, BinHex
# before 4.0 (DECISIONS.md 2026-10-14, *the BinHex before 4.0*): the
# decoder, resident in this build, and the probe in every build. Shipped,
# the decoder is `ovl_binhex`, 2,590 -> 4,986 B.
# RAISED the same day to 175,348, +36: the shim went in the shipped build,
# and this one, which never had it, pays the dispatch on UncCtx.fmt.
# RAISED 2026-10-14 to 175,408, +60, for refusing a fork of 2 GB or more
# as one entry instead of ending the run on "The disk is full"
# (DECISIONS.md 2026-10-14, *the file the disk was too full for*). A5
# 38,032, +4, the message and alignment.
# -12 on 2026-10-15: `JPEG Lossy` capped in width only (DECISIONS.md
# 2026-10-15, *the height nothing needed*).
# +36 on 2026-10-16: every file chosen in Standard File ends the launch,
# and an application ends a chain of layers (DECISIONS.md 2026-10-16, *the
# format that ends the launch*, *the installer that was a layer*); A5 -20.
# +12 on 2026-10-16: GrowApplZone in main() replaces MaxApplZone, which
# a 64K ROM does not have (DECISIONS.md 2026-10-15, *the purge
# MaxApplZone never did*; merged from the branch rom64k). A5 +20, .data
# padding behind the longer text.
# +20 on 2026-10-16: the progress dialog's time left from the byte counts
# rather than the percentage, timed per layer (DECISIONS.md 2026-10-16,
# *the estimate that went back up*); prog_tick +14, ExtractOne +8. A5 -20.
# +8 on 2026-10-16: the password dialog, OK on an empty field waiting
# and the refusal on a line of its own (DECISIONS.md 2026-10-16, *the
# empty password*); A5 -8, padding.
# +92 on 2026-10-16: a folder's Finder flags and dates are set, as a
# file's are, so a custom folder icon survives (DECISIONS.md 2026-10-16,
# *the folders that lost their icons*), less the empty password's test;
# A5 +4.
# RAISED 2026-10-17, 175,564 -> 176,428, by 864 B of CODE and 0 of A5 for
# the Finder metadata carried to the disk (DECISIONS.md 2026-10-17, *the
# metadata, carried to the disk*): the eager pair's pieces below, and the
# AppleLink reader's 16-byte copy, resident here.
# +40 code and +24 A5 the same day for the review: the archive's inited
# bit kept where it stated the Finder info and the file has no bundle, and
# fdPutAway, frPutAway and frOpenChain cleared (DECISIONS.md 2026-10-17,
# *the bit that kept the position*); the A5 is alignment.
# +12 code and -12 A5 the same day for the second review: a folder's date
# held in a one-entry cache instead of per item, and EnsureDir looking a
# name up before creating it (DECISIONS.md 2026-10-17, *the date held once
# per folder*). CODE + A5 unmoved.
# +428 code and -12 A5 on 2026-10-17 for StuffIt classic's and
# DiskDoubler's Finder info, resident here: sit_finder 310, new (not
# inlined), unc_sit_extract +60, unc_dd_extract +28, StampCat +12 (the
# eager pair above); the A5 is `.data` alignment stepping back
# (DECISIONS.md 2026-10-17, *the window Expander puts back*).
# +744 code and -8 A5 on 2026-10-17 for the envelopes' Finder info
# (DECISIONS.md 2026-10-17, *the envelopes' own Finder info*): the eager
# pair's resident pieces below, and here the readers that are images there
# — MIME's records and comment, the begin-line mode, UUTool's .finfo. A5
# 37,464, under its ceiling.
# +16 code and +8 A5 on 2026-10-17 at the merge of meta-envelopes: a
# MacBinary I header's lock bit masked out of the Finder flags, where
# System 7 reads it as isAlias (DECISIONS.md 2026-10-17, *the envelopes'
# own Finder info*).
# +4,520 code on 2026-10-17 for the archives' own Finder info (DECISIONS.md
# 2026-10-17, *the archives' own Finder info*): every reader that is an
# image when shipped is resident here — PackIt, StuffIt 5, Now Compress,
# SuperDisk!, Private File, ArcMac, zip, tar, gzip and LZH, with a copy of
# the MS-DOS date conversion in each of the three files that use it. The
# shipped and lazy pairs do not move. A5 37,552.
# +4,084 code and +12 A5 on 2026-10-17 for Mac OS X's sidecars, every
# image's code resident here: src/unc_sidecar.c, new, zip's half of them in
# src/fmt_exo.c and tar's in src/fmt_tar.c (DECISIONS.md 2026-10-17, *the
# sidecars Mac OS X left beside the file*).
# +660 code on 2026-10-17 for the dates in the Macintosh's own zone
# (DECISIONS.md): the eager pair's resident pieces, and here the readers
# that are images there — tar, gzip, zip's 0x334d offsets, LZH's marks.
# +1,344 code and +48 A5 on 2026-10-18 for the Spotlight comment, every
# image's code resident here: the attribute walk, the property-list reader
# and the UTF-16 to UTF-8 conversion in src/unc_sidecar.c, 48 B of it the
# attribute's name and the "bplist0" magic as data (DECISIONS.md
# 2026-10-18, *the comment Spotlight kept*).
# 2026-10-18, the question after the look (DECISIONS.md): the destination
# asked once the format is known, Cancel there quits, and the named-format
# alert gone; shipped CODE +44, A5 -44: 0 B of budget.
# -1,328 code on 2026-10-18, the formats it only named (the eager pair
# below; the same pieces, all resident in every configuration).
# +72 code and -8 A5 on 2026-10-18: the peek's own allocator, so a split set
# beside an AppleSingle with a comment no longer crashes (DECISIONS.md
# 2026-10-18, *the allocator nobody had built yet*): the control.
# +228 code and -4 A5 on 2026-10-18: the comment at the top of the output,
# Find… where the parts are and a progress line drawn without a blank
# (DECISIONS.md 2026-10-18, *the comment the root kept*): the control.
# +36 code on 2026-10-18: "Unknown format." and "Archive damaged."
# (DECISIONS.md 2026-10-18, *the format nobody reads*): the control.
# +764 code and -12 A5 on 2026-10-18 (the A5 under its ceiling): an
# application's bundle registered in the Desktop Database as StuffIt
# Expander registers it, so its inited bit and position are kept
# (DECISIONS.md 2026-10-18, *the icon Expander registers*): the control.
# +20 code and +12 A5 on 2026-10-19: the location (-1, -1) at the top of
# the output (DECISIONS.md 2026-10-19, *the place outside the archive*): the control.
# +76 code and -12 A5 on 2026-10-19: the top folder's custom-icon bit set
# when the run ends (DECISIONS.md 2026-10-19, *the icon that came late*): the control.
# -72 code on 2026-10-19: the toolchain update, PurgeSpace inlined
# (DECISIONS.md 2026-10-19, *the toolchain that inlined PurgeSpace*): the control.
# -32 code on 2026-10-20, A5 unchanged: one place for every probe
# (DECISIONS.md 2026-10-20, *one place for every probe*): the control,
# whose ceiling had 4 B of slack (188,100 on the day, TIERS_CONTROL 225,008).
# -72 code and +8 A5 on 2026-10-21: the sniffer in a file of its own,
# unc_sniff.c, which this build links as before (DECISIONS.md 2026-10-21,
# *the probes that left with the bundle*): the control.
# +52 code on 2026-10-21 for the same working directory as the eager pair
# (DECISIONS.md 2026-10-21, *the Desktop Manager System 6 can have*); A5
# 36,896, down 20 of `.data` alignment, and the ceiling comes down with it.
# RE-BASED 2026-10-22, 188,080 -> 177,900: the MacsBug names are stripped
# and the figure no longer counts them — 10,176 B of this build's text was
# names (DECISIONS.md 2026-10-22, *the names in the code*). A5 36,900, +4
# of `.data` alignment with the names gone, and the ceiling follows.
# -2,504 on 2026-10-22, 177,900 -> 175,396: Elf2Mac's --mac-single and
# mac/mac_start.c — Retro68's multi-segment loader and newlib's exit chain
# gone (DECISIONS.md 2026-10-22, *the runtime the application did not need*): the control.
# +28 on 2026-10-22, 175,396 -> 175,424, with data + bss -28 below: no
# working directory at the top of the output (DECISIONS.md 2026-10-22,
# *the working directory the bundle closed*): the control, its sum unmoved.
# +352 on 2026-10-22, 175,424 -> 175,776: the eleven malformed-input fixes
# (four out-of-bounds reads, two StuffIt 5 guards, the gzip multi-member
# loop, and four more). This is the RESIDENT control, where every decoder
# is linked in; the shipped overlay build is unmoved (its decoders are in
# the 'OVLY' bundle, its code ceiling held at 41,380), so the Mac Plus
# floor budget does not change — only this measurement baseline does.
# +8 on 2026-10-23, 175,776 -> 175,784: Compact Pro's fork-extent check
# hoisted ahead of the encrypted path (the control; shipped unmoved).
# +80 on 2026-10-24, 175,784 -> 175,864, A5 -16 below: the StuffIt segment
# probe tests what StuffIt writes instead of B0 56 (DECISIONS.md
# 2026-10-24, *the magic StuffIt never wrote*): the control. The shipped
# pair goes DOWN 32 (CODE -4, A5 -28), the parse it shares with the
# resident reader having lost a branch.
# +500 on 2026-10-24, 175,864 -> 176,364, A5 +12 below: a fat installer's
# part 1 cut short by its 'endD' (DECISIONS.md 2026-10-24, *the length part 1 kept in its resource fork*):
# unc_segment_first_end resident here (332 B) and the shell's read of
# part 1's resource fork.
# +80 on 2026-10-24, 176,364 -> 176,444, A5 +32 below: the running CRC a
# StuffIt segment stores at 98 is held part by part in the joiner
# (DECISIONS.md 2026-10-24, *the sum each part carries*): the control, and the
# shipped pair +80 and +16 — the joiner and the scheme are resident in
# every build.
UNC_MAC_CODE_DEFAULT=176444
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
# UNMOVED 2026-10-03 by StuffIt method 14, and that is measured rather
# than assumed: `size -A` puts src/sit14.c at 2,613 B of text, 0 of
# .data and 0 of .bss, so it has nothing to put here. It read 4 B higher
# in the middle of that work and went back when the decoder's own text
# changed — rodata alignment, the effect recorded four times above.
# RAISED 2026-10-05 from 37,892 to 37,920: +28 B for the AppleLink
# package format — the engine table's row, its printed name, and the
# probe's pointer in the sniff order. Measured on the same tree as the
# code figure above.
# +4 on 2026-10-05, with the code ceiling above.
# +12 on 2026-10-06, with the code ceiling above: rodata alignment under
# the new text in two files that carry no data of their own, the effect
# this file has now recorded four times.
# +4 on 2026-10-06, and the FIFTH record of the same effect: the
# method-14 sort fix took src/sit14.c from 2,572 to 2,566 B of text with
# .data and .bss still 0 (`size`, Retro68 -Os), and the control build's
# CODE fell by the same 4 — 164,320 against the 164,324 ceiling above,
# which is left standing as slack. CODE + A5 does not move, so
# OVL_SAVED does not either (TESTING.md, *The sort that dropped what it
# could not hold*).
# LOWERED 2026-10-06 from 37,920 to 37,916, and the SIXTH record of the
# same effect: the AppleLink probe's name test took src/fmt_sqp_probe.c
# from 666 to 670 B of text with .data and .bss still 0, the control's
# CODE rose to the 164,324 ceiling above and its A5 fell 4. CODE + A5
# does not move, so OVL_SAVED does not either (DECISIONS.md 2026-10-06,
# *the directory of empty records*).
# +24 on 2026-10-07 for the folder-depth rule: the engine's one new
# message, which the Macintosh report borrows rather than keeping a
# sentence of its own (DECISIONS.md 2026-10-07).
# LOWERED 2026-10-08, 37,928 -> 37,916, by PKZIP 1.01/1.02's minimum
# match length: the control's A5 falls 12 B while its CODE rises 620,
# rodata crossing between the two columns under changed text — the same
# effect the six records above are about. Lowered on the terms a ratchet
# is raised on, at the size on the day, so the 12 B cannot be spent
# later by accident. The two shipped pairs do not move in either column
# (DECISIONS.md 2026-10-08).
# RAISED 2026-10-08, 37,916 -> 37,924, by the recovery that bounds a wrong
# per-archive minimum-match-length verdict to the entry it was wrong about
# (DECISIONS.md 2026-10-08, *the writer a zip is allowed to have twice*).
# Attributed as far as the image allows: of the 126 .data and .bss symbols,
# exactly one moved — `_sdata`, 46 -> 54 B — and no named object grew, which
# is the `.data` ALIGN padding this file already records twice under changed
# text rather than a table anyone can point at. The SHIPPED pair does not
# move in either column: `src/fmt_exo.c` is in `ovl_exo`, so what grew there
# is the image (+152 B) and not one byte of what a 1 MB Mac Plus keeps
# resident.
# RAISED 2026-10-09, 37,924 -> 37,976: +64 B for Private File against a
# base of 37,912 (this ceiling had 12 B of slack) — the eager pair's 32 B
# and 32 of `.data` alignment, which steps the other way there.
# LOWERED the same day to 37,964, -12, with the code ceiling above.
# RAISED the same day to 37,976, +12, as the code ceiling above fell 12:
# the total is unmoved, and of the 126 .data and .bss symbols none changed
# size — the `.data` ALIGN padding stepping under shorter text, as above.
# RAISED the same day to 37,980, +4, with the code ceiling's +28: again no
# data symbol changed size (all 126 compared), so alignment.
# LOWERED the same day to 37,972, -8, with the code ceiling's +136.
# LOWERED 2026-10-10 to 37,960, -12, with the code ceiling's +12.
# RAISED 2026-10-11 to 38,000, +40, with the code ceiling's +1,176: no
# data symbol changed size against the previous commit's build, only
# `_sdata`'s padding. Alignment again.
# RAISED the same evening to 38,008, +8, as the code ceiling fell 8: the
# total is unmoved, and neither decoder has data in A5 — alignment, read
# from the totals and not compared symbol by symbol.
# LOWERED 2026-10-13 to 37,924, -84, with the code ceiling's +256: the
# "has not been found" sentence moved into DITL 131, and alignment.
# RAISED 2026-10-14 to 37,940, +16, with the code ceiling's +80: no data
# was added, alignment.
# RAISED 2026-10-14 to 38,000, +60, with the code ceiling's +2,356: the
# format's name and table row, and alignment.
# RAISED the same day to 38,028, +28, with the code ceiling's +36:
# alignment, no data added.
# RAISED 2026-10-14 to 38,032, +4, with the code ceiling's +60.
# -548 on 2026-10-15: the strings, moved into mac/macextract_strings.h and
# shortened (DECISIONS.md 2026-10-15, *the words in one file*).
# -20 on 2026-10-16, with the code ceiling's +36: the password prompt's
# shorter wording.
# +20 on 2026-10-16 with the code ceiling's +12: padding, no data added.
# -20 on 2026-10-16 with the code ceiling's +20: padding, the time left.
# -8 on 2026-10-16 with the code ceiling's +8: padding.
# +4 on 2026-10-16 with the code ceiling's +92.
# +72 on 2026-10-17 with the code ceiling's +4,520: three copies of the
# 24-byte days-before-month table, resident in this configuration only.
# -12 on 2026-10-17 with the code ceiling's +428: padding.
# +12 on 2026-10-17 with the code ceiling's +660: gZone, a vector slot,
# and padding.
# -704 on 2026-10-18 with the code ceiling's -1,328: the sixteen formats'
# table rows, the `extractable` column and their names (DECISIONS.md
# 2026-10-18, *the formats it only named*).
# +16 on 2026-10-18 to 36,908, the two messages' strings in the control
# (DECISIONS.md 2026-10-18, *the format nobody reads*).
# +8 on 2026-10-21 to 36,916 with the code ceiling's -72: the sniffer's table
# in a file of its own, unc_sniff.c, and its alignment (DECISIONS.md
# 2026-10-21, *the probes that left with the bundle*).
# -680 on 2026-10-22 to 36,220 with the code ceiling's -2,504: newlib's
# stdio and atexit state and the multi-segment loader's globals (DECISIONS.md 2026-10-22, *the runtime the application did not need*).
# Since --mac-single this figure is data + bss in the HEAP, not an A5 world:
# data rides in CODE 1 and bss is a block Retro68Relocate allocates.
# -28 on 2026-10-22 to 36,192, with the code ceiling's +28: the working
# directory left the top of the output (DECISIONS.md 2026-10-22, *the
# working directory the bundle closed*); not looked into further.
# +24 on 2026-10-23, 36,192 -> 36,216: data + bss alignment shifting under
# Compact Pro's hoisted fork-extent check (the RESIDENT control only; the
# shipped build's A5 is unmoved, so the floor budget does not change).
# -16 on 2026-10-24, 36,216 -> 36,200, with the segment probe (above).
# +12 on 2026-10-24, 36,200 -> 36,212, `.data` alignment under the 'endD'
# read (above).
# +32 on 2026-10-24, 36,212 -> 36,244: the scheme table's two new columns,
# a CRC routine and a flag per row, with the segment CRC check (above).
UNC_MAC_A5_DEFAULT=36244
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
# RAISED 2026-10-02 by EIGHT BYTES, and the A5 figure fell by the same
# eight: `unc_crypt_sit` takes a third thing now — WHICH of StuffIt
# 2.x's fork ciphers an entry wants — and the one resident piece of that
# is `mac/ovl_shim.c` putting it into the overlay call's argument block.
# Everything else is in the two overlays: the choice is made in
# `fmt_sit.c` (StuffIt's image) and the ciphers live in the crypt one.
# What the eight bytes bought: **every cipher StuffIt 2.x has.** `DES`
# and `DESex` are standard DES in CBC, `NewDE` and `NewDEx` are
# StuffItDES in CBC, and an entry `PassLock` "protected" is read without
# a password because that module enciphers nothing — five schemes that
# were refused the day before, each graded against a known plaintext
# (FORMATS.md, *The three ways 2.0.1 encrypts*). `run_tiers.py --check`
# is what says whether it cost a fixture.
# RAISED 2026-10-05 by 740 B of code and 36 of A5 for AppleLink
# packages, and that 740 B is the whole of what the format costs a
# machine that never opens one: the PROBE is 666 B of it (resident,
# because the sniffer calls it for every file), and the rest is
# `mac/ovl_shim.c`'s dispatch and the engine's table row. The decoder
# is 1,474 B and is in the `ovl_sqp` image, which is released for every
# archive that is not a package. Two cheaper probe shapes were measured
# and both were 6 B worse (DECISIONS.md 2026-10-05).
# RAISED 2026-10-05 by 316 B of code and 4 of A5, all six ceilings, so
# that a zip BEHIND something else is recognised: a self-extracting
# archive's first bytes are code, and the probe now reads the
# end-of-central-directory record it was already scanning for rather
# than throwing it away (src/fmt_zipseg.c, `zs_cd_is_there`). All of it
# is resident in every configuration and none of it is in an 'OVLY'
# image, because the sniffer calls that probe for every file it is
# handed — the same shape as the AppleLink probe above. **320 B off
# every extraction's budget on a 1 MB Mac Plus**, and the same 316 B in
# the control, which is the sign that no overlay absorbed any of it.
# What the bytes bought: all five ZipIt self-extracting specimens
# recognised with nothing forced, four of them through their MacBinary
# envelope the way a user hands one over (FORMATS.md, *What the zip pair
# claims, and what it costs*) — and five files of 8,364 that are not
# archives at all stopped being claimed as a spanned-zip part on four
# chance bytes (BLOCKERS.md, *Withdrawn claims*). The I/O cost is +0
# reads on every file the sniffer rejects and one 4-byte read on a zip,
# measured. `run_tiers.py --check` is what says whether it cost a
# fixture.
# +8 code and −8 A5 on 2026-10-06, for the uu probe's per-document
# alphabet test: what rejects an English sentence that declares 45 bytes
# is having a space AND lower case in it, and the probe is resident
# because the sniffer calls it for every file it is handed. CODE + A5 is
# unchanged at 73,392 B, so nothing comes off any extraction's budget —
# and A5 is a ratchet too, so the eight bytes it gave back are locked in
# (DECISIONS.md 2026-10-06, *the alphabet nothing here had seen*).
# +4 code and −4 A5 on 2026-10-06, for the lower bound on an AppleLink
# record's name length — the test that keeps a file of zeros out, which
# the probe answered "AppleLink package" for until that day. CODE + A5 is
# unchanged at 73,392 B again, so nothing comes off any extraction's
# budget, and the four bytes of A5 are locked in by lowering the ceiling
# with them (DECISIONS.md 2026-10-06, *the directory of empty records*).
# RAISED 2026-10-07 by 120 B of code and 40 of A5 for the folder-depth rule,
# then LOWERED again the same day when the limit it enforced was deleted
# (below). What that rule did, while it existed: an entry nested past
# UNC_PATH_MAXDEPTH was OFFERED with the path the engine could represent,
# carried `path_too_deep` and failed per entry with UNC_ERR_TOODEEP instead
# of being written into a folder it was never in. The constant, the flag and
# the error code are all gone; a component with no room left is CUT now.
# In THIS configuration the five decoders are in 'OVLY' images, so what
# is resident is the walker (`unc_path_push`/`pop`/`leaf`), the engine's
# message, and the Macintosh shell's refusal to create the folder — the
# per-format plumbing is overlay bytes and comes off no budget.
# What the bytes bought: the five path walks agreed for the first time.
# Three of them used to MISFILE every entry after a refused push into a
# real folder — silently, because the path is plausible and nothing in it
# looks cut — and the other two threw away the rest of the archive,
# 43 entries of 91 on the subject that measures it. Nothing in the corpus
# reaches 24 levels; the deepest is 4 (FORMATS.md, *How deep anything
# actually nests*), so this is 160 B against a limit no fixture meets, and
# 1.3% of the 12,460 B the narrowest 512 KB fixture has spare
# (tools/check_app_size.py). `run_tiers.py --check` is what says whether
# it cost a fixture (DECISIONS.md 2026-10-07).
# +8 code and -8 A5 on 2026-10-07, same day, for the claim a too-deep
# entry must NOT make: `name_full_len` 0 and never `name_truncated` 2,
# because the path the walk holds down there is not that entry's name.
# CODE + A5 is unchanged at 73,552 B, so nothing comes off any
# extraction's budget — and A5 is a ratchet too, so the eight bytes it
# gave back are locked in (DECISIONS.md 2026-10-07, *the two limits at
# once*).
# LOWERED 2026-10-07, 54,340 -> 54,272 of code against +4 of A5:
# **-64 B, and removing a limit is supposed to give bytes back.** It did
# not at first. The depth limit went for +376, then +128 after two trims,
# and the number only turned negative when a reader said it should be
# negative and would not take the explanations.
#
# Each explanation was true and none was the cause. +202 of it was
# `path_longbuf` being OUTLINED the moment `pop` became a second caller,
# which cost the function plus its inlined copies in two others;
# resolving the buffer once in `unc_path_init` put those back. The rest
# was the thing itself: the walker kept the path TWICE, once as reported
# and once uncut, each with a per-level stack of restore points — and
# `UNC_PATH_MAXDEPTH` existed to size those stacks. Dropping one stack
# left the other to be reconstructed on every pop, which is where the
# bytes went.
#
# What was wrong was keeping two. The uncut path now goes straight into
# the host's `long_name` buffer (the CLI offers 64 KB) and the walk holds
# ONE path with ONE length, so `path_full_add` — 152 B of it — is deleted
# outright and `unc_path_push` is 34 B smaller than before any of this.
# Paid in stack as well: `UncPath` is ~100 B smaller and the engine's
# deepest chain falls 3,386 -> 3,310 B (DECISIONS.md 2026-10-07, *the
# limit that was three transcriptions*).
# RAISED 2026-10-09 by 368 B of code and 32 of A5 for Aladdin Private File
# (`.pf`), measured against HEAD built the same way: **400 B off every
# extraction's budget on a 1 MB Mac Plus.** Of the code, 186 B is the
# probe, resident because the sniffer calls it for every file; 80 B the
# shim that keys RC4 from MD5 in the crypt image (`unc_crypt_pf`); 46 B
# the one that dispatches the reader; the rest the release switch's case
# and alignment. The A5 is the engine's table row and name, one sniff
# slot and two host-vector slots (`unc_crypt_apply`, `unc_crypt_pf`, so
# the reader can reach the cipher from `ovl_stuffit`), less 28 B of
# `.data` alignment that stepped back. The reader is 1,248 B and is in
# `ovl_stuffit` — it was resident on the first build, at +1,652, and
# moved for that reason. **The probe was 222 B on the first commit**:
# written through unc_get_u16be, the 68000 rebuilt every field with
# shifts before comparing it with a small constant, and byte compares
# took it to 186 (DECISIONS.md 2026-10-09, *the specimen was one
# search away*). What was bought: the last
# format on Aladdin's own engine list, graded byte-exact on three files
# Private File 2.0 wrote (FORMATS.md, *Private File*).
# `run_tiers.py --check` is what says whether it cost a fixture.
# +80 code and +16 A5 on 2026-10-11 for the SIXTEENTH image, `ovl_zipold`
# — zip's Shrink and Reduce, which only zip keeps, where they had been in
# the codecs image every format keeps. The code is the release's fourth
# keep (+24), the shim patching a second image into the vector through one
# routine shared with the codecs (`ovl_patched`, +24 net) and the zip shim
# asking for it (+20), 68 B by symbol and 12 of alignment between
# functions; the A5 is a fourth keep slot's 6 B and `_sdata` padding. What it buys: 2,064 B back in every format that is
# not zip, measured on `ovl_codecs` 8,468 -> 6,404 (FORMATS.md, *Reduce*).
# +140 code and +4 A5 on 2026-10-11 for three defects the first real
# Macintosh found, an LC 475, measured against HEAD built the same way:
# **144 B off every extraction's budget on a 1 MB Mac Plus.** By symbol:
# +38 in ExtractOne, where RunExtract is inlined — a `.zip` is a set only
# if its own end record says so, or every plain zip failed as "more
# parts"; +58 in sink_begin, where EnsureDir is inlined — a top-level
# folder already on the disk is numbered rather than merged into, and the
# A5 is its one flag, `gTopLost`, after a 16-entry table (+64 A5) was cut;
# +34 to quit after an archive whose decoders were released (ovl_spent 24,
# main 10), after its own 4-byte flag was cut; 10 of alignment
# (DECISIONS.md 2026-10-11, *the zip that was a set of one*, *the folder
# that is already there*, *one archive per launch*).
# -8 code and -8 A5 on 2026-10-12 for a way out of the application on
# System 7: **16 B BACK on every extraction's budget**, measured against
# the build before it. By symbol: +64 in prog_tick, where ProgressPump is
# inlined — FindWindow, MenuSelect, About's NoteAlert, Quit as Cancel;
# -20 in main, which draws the menu bar and no longer asks whether
# WaitNextEvent exists or keeps `gHasWNE`; -32 for NGetTrapAddress's glue,
# which only that question used; -20 of alignment, and the A5 is `.data`
# alignment too. **The first commit was +184 and +8**; trimmed the same
# day: Cmd-Q (MenuKey) and dragging the window cost 32 B each, a quit flag
# 48 (Quit is Cancel, and the application quits after an archive anyway),
# NULL checks on our own MENUs 32, and reading About's number from 'vers'
# 1 rather than writing it in the DITL 64 (DECISIONS.md 2026-10-12, *the
# application nobody could leave*). The 16 B is partly alignment luck.
# +192 code and +0 A5 on 2026-10-12 for the reload a list of archives
# needs: **192 B off every extraction's budget on a 1 MB Mac Plus.** By
# symbol: `ovl_reload` 114, new — dispose the kept copies, ReserveMem the
# bundle's size so it lands low as at launch, read it again; `main` +62,
# 24 of it DropNext reading the list by position and 38 the reload and its
# alert, which is a resource (ALRT 135) so that its text is not A5; 16 of
# alignment. The first version was +240 and +96: the alert's string was
# 72 B of A5, and moving the copies high after each release, instead of
# reserving low, was 76 B more (DECISIONS.md 2026-10-12, *the reload that
# the list needs*).
# +256 code and -48 A5 on 2026-10-13 for ejecting the disk a split set's
# last part came from: **208 B off every extraction's budget.** By
# symbol: SegAskUser +156 (the eject, inlined, and the alert chosen by
# it), SegDriveOfFile 82, new, 18 of alignment. Both sentences are DITLs
# (131 and 136), so the alert's text left A5; the first version kept
# them as strings and was +352 and +80 (DECISIONS.md 2026-10-13, *the
# disk that was still in the drive*).
# +80 code and +16 A5 on 2026-10-14 for unmounting that disk too, so the
# Finder keeps no dimmed icon per floppy of a set: **96 B off every
# extraction's budget.** The loop that forgets the parts on it, the
# UnmountVol, and SegDriveOf no longer inlined; the A5 is alignment
# (DECISIONS.md 2026-10-14, *the icon the eject left behind*).
# +400 code and +16 A5 on 2026-10-14 for `.hex` and `.hcx`, BinHex before
# 4.0: **416 B off every extraction's budget.** By symbol: the BinHex probe
# +222 (it now tells the two encodings from 4.0 in the same scan),
# `unc_hecx_is_header` 76, new, shared with the decoder; the shim 56; the
# table row 20; the release switch's case and alignment 26; and the name,
# 16, which is the A5. The decoder is in
# `ovl_binhex`, 2,590 -> 4,986 B (DECISIONS.md 2026-10-14, *the BinHex
# before 4.0*).
# -68 code and +4 A5 the same day: the shim went, both encodings now
# entering through `unc_binhex_extract`, which reads the new UncCtx.fmt.
# `ovl_binhex` +8 (DECISIONS.md, same entry). The A5 is alignment.
# +60 code and +36 A5 on 2026-10-14 for refusing a fork of 2 GB or more
# as one entry: **96 B off every extraction's budget.** sink_begin +56, in
# the create loop's existing failure path — a check of its own with its own
# RepEntryFailed call cost +144, the call making RepEntryFailed a 78 B
# function where it had been inlined; the A5 is the message (DECISIONS.md
# 2026-10-14, *the file the disk was too full for*).
# -560 A5 on 2026-10-15, code unchanged: every word the application shows
# moved into mac/macextract_strings.h and was shortened, which is 564 B of
# string literals out of the A5 world; the ceiling comes down with it
# (DECISIONS.md 2026-10-15, *the words in one file*).
# +36 code and -20 A5 on 2026-10-16: every file chosen in Standard File
# ends the launch, and an application ends a chain of layers; the A5 is
# the password prompt's shorter wording (DECISIONS.md 2026-10-16, *the
# format that ends the launch*, *the installer that was a layer*).
# +12 code on 2026-10-16, GrowApplZone (the default pair above); A5 -12,
# padding.
# +20 code and +12 A5 on 2026-10-16 for the time left taken from the byte
# counts and timed per layer: **32 B off every extraction's budget.**
# prog_tick +14, ExtractOne +8; the A5 is 12 zero bytes ahead of `.data`'s
# aligned head, nothing else in it moved (DECISIONS.md 2026-10-16, *the
# estimate that went back up*).
# +8 code and -8 A5 on 2026-10-16: the password dialog (DECISIONS.md
# 2026-10-16, *the empty password*); 0 B of budget.
# +92 code and +4 A5 on 2026-10-16: folders' Finder flags (the default
# pair above): 96 B off every extraction's budget.
# +820 code and +12 A5 on 2026-10-17 for the Finder metadata carried to the
# disk: **832 B off every extraction's budget on a 1 MB Mac Plus.** By
# symbol: `unc_appledouble_extract` +300 (entry 4's comment, entry 8's
# backup date, entry 9 whole, entries 10 and 12's lock, entries 8-12 read
# once before the switch, and a cut file called truncated rather than
# complete: +60 code and +4 A5 of the total), StampCat +202 (FInfo/FXInfo whole, the backup
# date, the comment through the Desktop Manager, the lock), DirMd 112, new
# (a folder's date held across a create or delete inside it), sink_begin
# +130 and sink_end +46 (its three call pairs), MyHDelete no longer inlined
# and ExtractOne +32 (the unlock before an unwrapped layer is deleted); the
# A5 is `_sdata` padding. **The first cut was +1,032**: three param blocks
# side by side, two date helpers, two 16-byte arrays copied apart, three
# reads where one does, and a PBHGetVolParms that PBDTGetPath makes
# redundant on every System measured (DECISIONS.md 2026-10-17).
# +40 code and -8 A5 the same day for the review: StampCat's inited rule
# and the three cleared directory IDs; **32 B more off every budget, 864
# in all** (DECISIONS.md 2026-10-17, *the bit that kept the position*).
# +16 code and -16 A5 the same day for the second review (the default
# pair above): 0 B off any budget, 864 in all.
# +16 code and +16 A5 on 2026-10-17 for StampCat writing the flags the
# Finder info STATES, which a reader may have masked as its format's own
# expander does (StuffIt classic): **32 B off every extraction's budget.**
# StampCat +12 and 4 of alignment; the A5 is 16 zero bytes of `*fill*`
# under `.data`'s ALIGN (0x20), nothing in it moved (DECISIONS.md
# 2026-10-17, *the window Expander puts back*).
# +464 code and +16 A5 on 2026-10-17 for the envelopes' Finder info:
# **480 B off every extraction's budget.** By symbol: unc_macbinary_meta
# 234, new (one MacBinary header read one way, for MacBinary, ZipIt and
# MacLHA: FInfo whole, the lock, III's two FXInfo bytes),
# unc_macbinary_extract +126 (the Get Info comment after the resource
# fork, read before the entry is offered), unc_as_record 290, new, and
# unc_appledouble_extract -230 (AppleSingle's fixed records as one function
# MIME's image calls too, and RFC 1740's unknown date kept unknown); the
# A5 is gOvlFns's two slots, +8, and 8 of `.data` alignment (DECISIONS.md
# 2026-10-17, *the envelopes' own Finder info*).
# +12 code and -12 A5 on 2026-10-17 at the merge of meta-envelopes, the
# same mask: 0 B of budget.
# +0 code and +32 A5 on 2026-10-17 for Mac OS X's sidecars: nine host-vector
# slots (the sidecar code ovl_zipold patches in for zip's reader in
# ovl_exo, and unc_copy_fork for tar), 36 B, less alignment. **32 B off
# every extraction's budget**; the code is all in images (DECISIONS.md
# 2026-10-17, *the sidecars Mac OS X left beside the file*).
# +356 code and +12 A5 on 2026-10-17 for the dates in the Macintosh's own
# zone: **368 B off every extraction's budget.** By object: the shell +316
# (ZoneProbe 146, ZoneMove, and the three marked dates moved in
# sink_begin), unc_macbinary_meta +22 (a payload's dates clear the
# container's mark), unc_as_record +16 (AppleSingle's marks); the A5 is
# gZone, +4, the vector slot Implode's move to ovl_zipold needs, +4, and
# 4 of `.data` alignment (DECISIONS.md 2026-10-17, *dates in the
# Macintosh's own zone*).
# +80 code and +16 A5 on 2026-10-18 for the Spotlight comment: the shell
# folds a UTF-8 comment into MacRoman with the name's Utf8ToMacRoman, which
# two callers stop GCC inlining (always_inline measured +256 code, A5 +0).
# The 16 B of A5 are no table of ours: 16 zero bytes at the head of .data,
# and the lazy build moved -20 for the same change (hypothesis: layout).
# **96 B off every extraction's budget** (DECISIONS.md 2026-10-18, *the
# comment Spotlight kept*).
# 2026-10-18, the question after the look (DECISIONS.md): the destination
# asked once the format is known, Cancel there quits, and the named-format
# alert gone; shipped CODE +44, A5 -44: 0 B of budget.
# -1,328 code and -704 A5 on 2026-10-18, the formats it only named, gone
# (DECISIONS.md 2026-10-18, *the formats it only named*): the probe
# `unc_foreign_probe` (1,156 B) and `unc_sitx_probe` (90 B), the sixteen
# table rows and the `extractable` column (`unc_formats` 960 -> 512 B),
# two slots of `unc_sniff_order` (-8) and their names and literals.
# **2,032 B onto every extraction's budget**, the same in all three
# configurations, so OVL_SAVED does not move.
# +72 code and +24 A5 on 2026-10-18: the peek's own allocator, so a split set
# beside an AppleSingle with a comment no longer crashes (DECISIONS.md
# 2026-10-18, *the allocator nobody had built yet*): 96 B off every budget.
# +228 code and -4 A5 on 2026-10-18: the comment at the top of the output,
# Find… where the parts are and a progress line drawn without a blank
# (DECISIONS.md 2026-10-18, *the comment the root kept*): 224 B off every
# budget.
# +32 code on 2026-10-18: "Unknown format." and "Archive damaged."
# (DECISIONS.md 2026-10-18, *the format nobody reads*); A5 unchanged: 32 B off every budget.
# +760 code and +40 A5 on 2026-10-18: an application's bundle registered
# in the Desktop Database as StuffIt Expander registers it, so its inited
# bit and position are kept (DECISIONS.md 2026-10-18, *the icon Expander
# registers*): 800 B off every budget.
# +24 code and -24 A5 on 2026-10-19: the location (-1, -1) at the top of
# the output (DECISIONS.md 2026-10-19, *the place outside the archive*): 0 B of budget.
# +72 code and +24 A5 on 2026-10-19: the top folder's custom-icon bit set
# when the run ends (DECISIONS.md 2026-10-19, *the icon that came late*): 96 B off every budget.
# -72 code and -24 A5 on 2026-10-19: the toolchain update, PurgeSpace
# inlined (DECISIONS.md 2026-10-19, *the toolchain that inlined PurgeSpace*): 96 B back on every budget.
# -32 code on 2026-10-20, A5 unchanged: every probe in its reader's
# `_probe.c`, and StuffIt classic's probe comparing bytes (DECISIONS.md
# 2026-10-20, *one place for every probe*): 32 B back on every budget.
# -9,284 code and -364 A5 on 2026-10-21: the sniffer and every probe in an
# 'OVLY' image of their own, run from the bundle before the release
# (DECISIONS.md 2026-10-21, *the probes that left with the bundle*): 9,648 B
# back on every budget but an envelope layer's, which keeps the bundle.
# +52 code and +12 A5 on 2026-10-21: the bundle's resource fork opened
# through a working directory and OpenRFPerm, where HOpenResFile bombed
# System 6.0.8 under AppleShare's Desktop Mgr INIT (DECISIONS.md
# 2026-10-21, *the Desktop Manager System 6 can have*): 64 B off every
# budget; the A5 is `.data` alignment, nothing new is in it.
# RE-BASED 2026-10-22, 48,316 -> 43,900: the MacsBug names stripped, 4,414 B
# of this build's text (DECISIONS.md 2026-10-22, *the names in the code*).
# -2,552 code and -1,304 data + bss on 2026-10-22: Elf2Mac's --mac-single
# and mac/mac_start.c (DECISIONS.md 2026-10-22, *the runtime the application did not need*). The machine gave every shipped budget
# +4,980 B, more than these 3,856: the jump table, six stub segments and the
# relocations trimmed at launch were resident and never counted here.
# +32 code on 2026-10-22, data + bss unchanged: no working directory for a
# bundle at the top of the output, where System 7 and the Desktop Mgr INIT
# handed back the Finder's own and it was closed (DECISIONS.md 2026-10-22,
# *the working directory the bundle closed*): 32 B off every budget.
# -832 code and +32 data on 2026-10-23: the 21 decoder shims one routine
# and a table, the release's `switch` a two-byte row per format
# (DECISIONS.md 2026-10-23, *the shims that were one function*): 800 B back
# on every budget. The +32 is that table, `gKeepSet`.
# -4 and -28 on 2026-10-24, 40,548 -> 40,544 and 16,268 -> 16,240: the
# StuffIt segment parse the shipped pair keeps resident lost a branch
# (DECISIONS.md 2026-10-24, *the magic StuffIt never wrote*).
# +200 and +24 on 2026-10-24, 40,544 -> 40,744 and 16,240 -> 16,264: the
# shell reads part 1's resource fork for its 'endD' (+126) and asks the
# sniffer's image where the segment ends through a 74 B shim; the lookup
# itself is in that image, not here (DECISIONS.md 2026-10-24, *the length part 1 kept in its resource fork*).
# The 24 B is `*fill*` under `. = ALIGN (0x20)`: CODE + A5 +224 either way
# the shell's code was arranged.
# +80 and +16 on 2026-10-24, 40,744 -> 40,824 and 16,264 -> 16,280: the
# running CRC-16/ARC a StuffIt segment stores at 98, held part by part as
# the set is joined (DECISIONS.md 2026-10-24, *the sum each part carries*). All
# of it resident: the joiner and the StuffIt scheme are the shell's, not an
# image's, and the CRC routine was already here for the forks.
UNC_MAC_CODE_EAGER=40824
UNC_MAC_A5_EAGER=16280
# +8 on 2026-10-02 for the same reason as the eager pair above: the
# overlay call that now says WHICH of StuffIt 2.x's ciphers an entry
# wants. A5 fell to 19,096 and its ceiling is left where it was.
# +740 and +44 on 2026-10-05 for the same reason as the eager pair.
# +316 code on 2026-10-05 for the zip-behind-a-stub probe, same as the
# eager pair; A5 fell 4 B to 19,144 and the ceiling comes down with it.
# +8 and −8 on 2026-10-06 for the same reason as the eager pair.
# +4 code and +28 A5 on 2026-10-06 for the AppleLink name test, and this
# configuration is the one that pays for it: the 28 B is `*fill*` under
# the linker script's `. = ALIGN (0x20)` at the head of `.data`, read off
# the map, because `_sdata` lands at 0xcfa4 here instead of 0xcfa0 once
# the text is 4 B longer. The same 4 B of text costs the eager and
# resident builds nothing at all in CODE + A5 (both pairs above), so this
# is the alignment effect those ceilings have recorded six times, in the
# one configuration where it steps the wrong way (DECISIONS.md
# 2026-10-06, *the directory of empty records*).
# +120 code and +8 A5 on 2026-10-07 for the folder-depth rule, the same
# resident pieces as the eager pair above.
# +368 code and +64 A5 on 2026-10-09 for Private File, the same resident
# pieces as the eager pair above; the A5 is 32 B more than there because
# the `.data` alignment that gave 28 B back in the eager build steps the
# other way in this one.
# +56 code and +8 A5 on 2026-10-11 for `ovl_zipold`, the shim half of the
# eager pair's change (this lifetime has no release to teach).
# +120 code and -24 A5 on 2026-10-11 for the LC 475's three fixes, the
# same pieces as the eager pair above: ExtractOne +38, sink_begin +58,
# main +10, ovl_spent +4 (here it only answers 0), 10 of alignment. The
# A5 FELL despite `gTopLost`'s byte: `.data` alignment stepped back, and
# the ceiling comes down with it.
# -8 code and +8 A5 on 2026-10-12 for the menu bar and the titled
# progress window, the same pieces as the eager pair above; the A5 is
# `.data` alignment.
# +80 code and +16 A5 on 2026-10-12 for the same reload, which this
# lifetime never runs: the branch is in `main` whatever the loader, `main`
# +62 and a 4-byte `ovl_reload` that answers 1, and the A5 is `_sdata`'s
# padding. Not shipped, so not trimmed further.
# +260 code and -52 A5 on 2026-10-13 for the same eject as the eager pair.
# +76 code and -12 A5 on 2026-10-14 for the same unmount.
# +400 code and +48 A5 on 2026-10-14 for BinHex before 4.0, the same
# resident pieces as the eager pair above; the A5 is 32 B more than there,
# `.data` alignment again.
# -64 code the same day, the shim gone as in the eager pair above.
# +56 code and +8 A5 on 2026-10-14 for the same refusal.
# +36 code on 2026-10-16 for the same two; A5 18,636, under its ceiling.
# +12 code on 2026-10-16, GrowApplZone; A5 18,624, under its ceiling.
# +24 code on 2026-10-16 for the same time left; A5 18,632, under it.
# +8 code on 2026-10-16, the password dialog; A5 18,624, under its ceiling.
# +92 code on 2026-10-16, folders' Finder flags; A5 18,628, under its
# ceiling.
# +820 code on 2026-10-17, the Finder metadata (the eager pair above); A5
# 18,608, under its ceiling.
# +40 code the same day for the review (the eager pair above); A5 18,632,
# under its ceiling.
# +16 code the same day, the second review; A5 18,616, under its ceiling.
# +12 code on 2026-10-17, StampCat writing the stated flags (the eager pair
# above); A5 18,636, +20 of padding, under its ceiling.
# +460 code on 2026-10-17, the envelopes' Finder info (the eager pair
# above); A5 18,652, under its ceiling.
# +16 code on 2026-10-17, the same mask.
# +352 code on 2026-10-17, the dates in the Macintosh's own zone (the eager
# pair above); A5 18,696, under its ceiling.
# +84 code on 2026-10-18, the Spotlight comment (the eager pair above);
# A5 18,676, under its ceiling.
# -1,328 code on 2026-10-18, the formats it only named (the eager pair
# above); A5 -704 to 17,964, under its ceiling.
# +76 code on 2026-10-18, the same allocator.
# +228 code on 2026-10-18, the same three.
# +28 code on 2026-10-18, the same two messages.
# +764 code on 2026-10-18, the bundle registered (the eager pair above);
# A5 17,984, under its ceiling.
# +20 code on 2026-10-19, the same.
# +76 code on 2026-10-19, the same.
# -72 code on 2026-10-19, the toolchain update.
# -36 code on 2026-10-20, one place for every probe (the eager pair
# above); A5 18,000, under its ceiling.
# -9,280 code on 2026-10-21, the probes that left with the bundle (the eager
# pair above); A5 17,632, under its ceiling.
# +52 code on 2026-10-21 for the same working directory as the eager pair;
# A5 17,644, under its ceiling.
# RE-BASED 2026-10-22, 46,740 -> 42,428: the MacsBug names stripped, 4,308 B
# of this build's text (the eager pair above).
# -2,552 code on 2026-10-22, the runtime the eager pair above lost; data +
# bss 16,332, under its ceiling.
# +32 code on 2026-10-22, no working directory at the top of the output (the
# eager pair above); data + bss 16,332, under its ceiling.
# -704 code on 2026-10-23, the decoder shims one routine (the eager pair
# above; the release table is the eager loader's alone); data + bss 16,332,
# under its ceiling.
# +200 code on 2026-10-24, the 'endD' read (the eager pair above); data +
# bss 16,324, under its ceiling.
# +76 code on 2026-10-24, the segment CRC check (the eager pair above);
# data + bss 16,344, under its ceiling.
UNC_MAC_CODE_LAZY=39480
UNC_MAC_A5_LAZY=19200
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
    else
        echo "mac: no m68k nm — the constructor guard NOT checked"
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

#!/usr/bin/env python3
"""run_tiers.py — predict a Macintosh tier's memory refusals on Linux.

Every "N/71" in FORMATS.md's small-machine tables costs an emulator run:
one boot per fixture, minutes of host clock, an X server and a ROM. What
decides those numbers is not the Macintosh — it is the engine's
allocation profile against a budget, and the CLI's `--budget` applies
exactly the same rule the Mac shell's allocator does (a running total
against a cap, refused per entry).

`run_budget.py` beside this one is the other half: it sweeps the whole
CORPUS at one cap and reports per format. This file sweeps the Mac
SAMPLE at the tiers' own budgets and asserts the tallies.

TWO LANES, and they grade different things
------------------------------------------
- **resident** — one budget per tier, which is what a build with every
  decoder linked in has. That build still exists as the control
  (`UNC_OVL_RESIDENT=1`), and this lane is a REGRESSION DETECTOR: a
  decoder that starts asking for more memory moves a tally here whatever
  the Macintosh shell does with its resources.
- **shipped** (`--shipped`) — one budget per tier PER FORMAT, which is
  what the `'OVLY'` build has: the decoders are fifteen images read as
  one bundle at launch, and everything the sniffed format cannot want is
  released before the engine takes its budget (FORMATS.md, *Overlays*).
  This is the lane that predicts what a user's Macintosh refuses.

Both are swept in seconds:

    tools/run_tiers.py --check                       # both lanes, asserted
    tools/run_tiers.py --tier sys3-512K              # resident, one tier
    tools/run_tiers.py --tier sys3-512K --shipped    # shipped, one tier
    tools/run_tiers.py --budget 129244 --list tools/vmac/sample.txt
    tools/run_tiers.py --tier floor-1M --macextract build/rel/macextract
    tools/run_tiers.py --check-saved     # OVL_SAVED against the two builds

Each prints one line per refusal with the shortfall, and the tally. The
resident lane reproduced all three tiers exactly when a resident build
last ran on them (2026-09-22) — 71/71, 67/71 and 64/71, the same four and
seven fixtures by name — and again on 2026-10-09: 72/72, 68/72 and 63/72,
the same four and nine, which it asserts by name from that day. The shipped lane reproduces all three tiers a machine
ran on 2026-10-09: 72/72 at the floor target, **70/72** at System 3.0 /
512 KB and **66/72** at System 6.0.8 / 512 KB, refusing the same
fixtures by name — after the budgets were re-taken, because on the stale
ones it said 67/72 and passed `a2ps.V4.3.tar.Z` (FORMATS.md, *512 KB
machines*).

How the shipped lane gets a budget per format
---------------------------------------------
Everything below is derived rather than restated: the keep set comes out
of `mac/ovl_load_eager.c`'s own switch, the format names out of the
engine's table, the image sizes out of the build. A second copy of any
of them would grade something other than what the Macintosh runs.

    budget(tier, format) = resident budget(tier) + OVL_SAVED + OVL_RESIDUE
                           - sum(kept image sizes) - 8 per kept image

`OVL_SAVED` is the resident `CODE` + A5 the overlay build does not carry;
a kept image is a locked copy on the heap, and an envelope keeps the
whole bundle instead. The arithmetic reproduces all three granted budgets
the machine has measured (FORMATS.md, *What it buys, against the
control*) — but each layer of a `.sit.hqx` gets its OWN budget on the
Macintosh, because the shell re-takes one per envelope layer, so this
lane sweeps a fixture layer by layer and a fixture passes only if every
layer does. Why it is built this way: DECISIONS.md 2026-09-26, *a budget
per format, and one per layer*.

What it CANNOT see, and why the emulator stays
----------------------------------------------
- **The budget itself, which is the one that has actually bitten.** It
  is `FreeMem() - 20,480` measured on the machine (FORMATS.md,
  *Budget*), so every constant here goes stale the moment the
  application's size does. `--check-saved` notices since 2026-10-09, when
  all three were 16,888 B stale (TIERS_CONTROL); it cannot notice a new
  System, emulator or ROM. All three were also
  stale on 2026-09-22 — two by 21,666 B — and the one-fixture
  System 6.0.8 / 512 KB disagreement that had been filed under
  fragmentation below was this, entirely.
- **Whether a Compact Pro or zip archive is encrypted.** The shell asks
  `unc_archive_encrypted` and releases the ciphers on a definite NO;
  that walk is not reachable from the CLI, so this lane keeps them for
  those two formats always and grants 10,252 B LESS than the machine
  does (measured 2026-10-09: on the System 6.0.8 512Ke a zip with
  nothing encrypted is granted what a tar is). Deliberately pessimistic, and it decides nothing: the narrowest
  margin on any Compact Pro or zip layer in the sample is 138,989 B
  (`derived-MUSFMT10.ZIP` at System 6.0.8 / 512 KB, re-measured
  2026-10-09 at the re-taken budgets).
- **Fragmentation.** The budget is one number; the Memory Manager also
  has to find ONE piece that big. The Mac shell reports that case
  separately (`gShortPiece`, "Memory is too broken up"), and nothing
  here models it. **No disagreement currently rests on it** — the one
  that did was the stale budget above — so this is a limit of the model
  with nothing yet standing on it.
- **Struct sizes.** A 68000 build packs differently: `derived-a2basic`
  peaks at 37,356 B before its block here and 37,372 B there. Tens of
  bytes, not thousands — but a fixture that misses by 20 bytes is not
  decided by this file.
- **The probe's own weight.** Every budget here was read off a
  `-D UNC_AT_BUDGET` build, and that switch costs the shipped
  configuration 400 B of `CODE` + A5 and the control 320 B (measured
  2026-09-27, `m68k-apple-macos-size`). The sweeps whose tallies these
  assert run WITHOUT it, so every budget in TIERS is ~320 B lower than
  the build being graded actually has, and every shipped prediction
  ~400 B lower. Pessimistic, and it decides nothing at the margins
  below; it is not corrected arithmetically, because that is how the
  floor budget was once made worse.
- **Anything that is not memory.** Names, CRCs, the File Manager, the
  interface. Those are `tools/vmac/run.py`'s.
- **What the shortfall means.** It is a floor: the first refused
  request's, not the entry's demand (which is why both front ends say
  "at least"). `synth-dd-m5.dd` at the 512 KB budget reports 928 B and
  wants 203,680.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# Measured budgets, one per tier that has ever refused anything. Each is
# `FreeMem() - 20,480` taken on the machine with `-D UNC_AT_BUDGET`;
# FORMATS.md (*Budget*, *512 KB machines*) is where they come from and
# the only place they should be corrected.
#
# THESE ARE THE RESIDENT BUILD'S BUDGETS, which is what a build with every
# decoder linked in has and not what ships. The shipped build's budget is one
# of these PLUS what the overlay release gives back for the sniffed format,
# which is the `--shipped` lane below.
TIERS = {
    "sys3-512K": (205476, "System 3.0, Macintosh 512Ke (225,956 B free)"),
    "sys6-512K": (110076, "System 6.0.8, Macintosh 512Ke (130,556 B free)"),
    "floor-1M":  (634364, "System 6.0.8, 1 MB Mac Plus — the floor target"),
}

# RE-TAKEN on all three machines 2026-10-09 (`-D UNC_OVL_RESIDENT -D
# UNC_AT_BUDGET`, derived-PCCTS.tar), and all three had fallen by the
# identical 16,888 B. They had been lowered once since 2026-09-27, by the
# 2,024 B derived below, while OVL_SAVED — which --check-saved keeps
# current — rose 117,040 -> 134,032 as the control build grew. The shipped
# lane is base + OVL_SAVED, so every per-format budget it printed from
# 2026-10-02 to this re-take was ~16.5 KB too generous, and the System 6.0.8
# 512Ke sweep that day refused `a2ps.V4.3.tar.Z`, which the stale model
# passed (BLOCKERS.md, *Withdrawn claims*). **A control-build change moves
# this table one for one; re-take it, or lower it by the control's growth,
# whenever --check-saved makes you move OVL_SAVED.**
#
# So the control's size those budgets were read against is pinned, and
# --check-saved (in ci.sh) fails when the control build moves away from it:
# OVL_SAVED was the only term of base + OVL_SAVED that anything checked,
# and a sum whose terms are kept current at different rates is wrong by
# exactly the term nobody re-takes.
# **Raised by 96 B the same day, and TIERS lowered by the same 96, DERIVED
# and not re-measured**: the control's CODE grew 169,784 -> 169,880 for
# Shrink's tick per partial clear and the zip peek's Cancel (FORMATS.md,
# *Shrink*), A5 unmoved. **And by 32 more, same terms**: CODE +28 and A5
# +4 when zip's dry passes stopped counting progress (DECISIONS.md
# 2026-10-09, *the bar that counted the peek*). **And by 128 more**: CODE
# +136 and A5 -8 when DiskDoubler stopped re-reading its own buffer and
# MacLHA's peek and uuencode's scan stopped counting twice (DECISIONS.md
# 2026-10-09, *DiskDoubler read every block six times*).
# **MEASURED the same evening, and the 256 B landed to the byte** on all
# three machines: 205,476, 110,076 and 634,364 B, `FreeMem()` 225,956,
# 130,556 and 654,844 B, against this control. So TIERS is a machine
# measurement again, and not a derivation.
TIERS_CONTROL = 208016     # build/mac-resident, CODE + A5, 2026-10-09

# What the MACHINE measured: each budget plus the control it was read
# against, which a change to the application cannot move — so moving
# TIERS_CONTROL without moving TIERS by the same amount fails
# --check-saved, which it did not until 2026-10-09 (the message below told
# a reader to move TIERS_CONTROL and nothing tied the two together). Only
# a re-take on the machine changes these.
TIERS_MACHINE = {
    "sys3-512K": 413492,   # 205,476 + 208,016, measured 2026-10-09 (and
    "sys6-512K": 318092,   # 110,076 + 208,016   205,732 + 207,760 that
    "floor-1M":  842380,   # 634,364 + 208,016   morning: the same sums)
}

# DERIVED, not re-measured, 2026-10-01: all three fell by 2,024 B — the
# resident CODE the zip Macintosh extra fields added to the CONTROL build
# (tools/build_mac.sh, UNC_MAC_CODE_DEFAULT). The relationship is one for
# one and has landed one for one on three machines twice (below), so the
# arithmetic is the measurement here and no emulator was booted for it.
# **The SHIPPED lane is unaffected**: that material is all in `ovl_exo`
# and is released for every archive that is not a zip. No tally moved on
# either lane: 71/71, 67/71, 64/71 resident and 71/71, 69/71, 66/71
# shipped, the same fixtures by name.

# Re-taken on all three machines TWICE on 2026-09-27, and each time all three
# moved by the identical amount: +4,746 B with the merge and DART's removal in
# (219,362 -> 224,108, 123,962 -> 128,708, 648,250 -> 652,996), then +536 B
# when the AppleLink probe left (DECISIONS.md 2026-09-27, *the recogniser that
# was a command line*). One application-size change landing one for one on
# three machines and two systems, which is what this target is supposed to do;
# the sys3 figure was PREDICTED from the other two before the first of those
# runs. **496 B of application bought 536 B of budget** — 40 B more than the
# arithmetic, which is the same rounding slack recorded below in the other
# direction. No tally moved on either lane, either time: 71/71, 67/71 and
# 64/71 resident with the same names (FORMATS.md, *512 KB machines*).

# Re-taken 2026-09-22 with the 1990 DiskDoubler header in, and **all three
# fell by exactly 32 B**: 219,394 -> 219,362, 123,994 -> 123,962 and
# 648,282 -> 648,250. The arithmetic predicted 64 — the change is +48 B of
# code and +16 B of A5, and both are supposed to come off the budget one
# for one — so half of it did not arrive. That gap is recorded rather than
# explained: a CODE resource is a handle of its own size and the A5 world
# is rounded, so a few tens of bytes of growth can land inside slack that
# was already paid for. **The measurement is the number**; the arithmetic
# is what says when to go and take one.

# All three re-taken on the machine on 2026-09-22 with `-D UNC_AT_BUDGET`,
# and all three had drifted the same way: 197728, 102328 and 648100 were
# 21,666, 21,666 and 182 bytes low. A budget is `FreeMem() - 20,480` on a
# binary, so every one of these goes stale whenever the application's size
# does — and none of them had been re-taken since 2026-08-31, across the
# stack cut and a month of decoder work. The floor figure had been made
# WORSE by arithmetic in the meantime: 896 B was subtracted from it for the
# UTF-8 fold, which is the right sum applied to a stale base, and it moved
# away from the machine rather than towards it.

SHORT = re.compile(r"at least (\d+) bytes more memory")

# What the RESIDENT lane asserts: every tier an emulator has independently
# agreed with for that build, which since 2026-09-22 is all three. Each
# matched the machine fixture for fixture that day — `floor-1M` 71/71, `sys3-512K`
# 67/71 (the same four names), `sys6-512K` 64/71 (the same seven).
# `sys6-512K` was a diagnostic until that day because it read 59/69 where the
# machine said 58 and later 63; it is asserted now, because the disagreement
# was the stale budget above and not the model.
#
# A tally that moves here is either a memory regression or a memory WIN;
# both want the number below changed deliberately, which is the point of
# pinning it. 69 -> 71 on 2026-09-22: the sample gained the two StuffIt 5
# fixtures whose names are UTF-8, and `derived-Cool_Tools__.sit` needs
# 242,464 B, so it is a 512 KB refusal on both systems. Nothing that was
# passing stopped. 71 -> 72 on 2026-10-09: `shrink-wild-titanic.zip`
# joined, the first Shrink archive on a Macintosh; at 38,777 B it passes
# every tier, so each tally rose one.
# 65 -> 63 at sys6-512K the same day, with TIERS re-taken 16,888 B lower:
# `derived-Terrainman_2.0__.sea` and `derived-LHA_Expander_1.0.3.sea` fall
# out. That was the model's until the same evening, when the resident build
# ran the sample on all three machines and refused exactly these fixtures.
#
# BY NAME since then, as the shipped lane is, and for the same reason: a
# count cannot fail on two different refusals.
EXPECT = {
    "floor-1M": (),
    "sys3-512K": ("derived-Cool_Tools__.sit",
                  "derived-Library_ISBN_Barcoder.sit",
                  "derived-a2basic.dmg.sit", "synth-dd-m5.dd"),
    "sys6-512K": ("derived-Cool_Tools__.sit", "derived-Expand_Now_1.0.1.sea",
                  "derived-LHA_Expander_1.0.3.sea",
                  "derived-Library_ISBN_Barcoder.sit",
                  "derived-Terrainman_2.0__.sea",
                  "derived-Troi-ClipSave-Plug-in1.1.sit",
                  "derived-a2basic.dmg.sit", "popper-1.7.tar.Z",
                  "synth-dd-m5.dd"),
}

# ---------------------------------------------------------------------------
# The shipped build's model: a budget per tier PER FORMAT.
# ---------------------------------------------------------------------------

# What the overlay build does NOT carry resident, in bytes: the control's
# `CODE` + A5 less the shipped build's, 152,068 + 37,820 - 53,216 - 19,008.
# All four measured 2026-09-28 with `m68k-apple-macos-size` (FORMATS.md,
# *Three configurations, one tree*), which is the only place to correct them.
# It read 117,056 — a set two corrections old — until 2026-09-27: v0.34.0's
# Compact Pro segment check had moved all four figures and this line was not
# one of the places corrected. check_saved() below grades it against the two
# builds whenever they and the toolchain are present, so the next 32 B fails
# `ci.sh` instead of surfacing as a residue — and it caught the AppleLink
# probe's removal the same day, and the StuffIt add-on module fields on
# 2026-09-28: **+224 B**, because that change costs the control 336 B of
# resident code and A5 and the shipped build 112 B. And **+336 B** on
# 2026-09-29, for undoing the 2.0 Optimizers rather than refusing them: the
# control 624 B and the shipped build 288 B (FORMATS.md, *What an Optimizer
# did to the fork*).
#
# And **+4096 B** on 2026-10-02, for `JPEG Lossy`: sit_ccube.c costs the
# control 6,112 B of resident CODE and A5 and the shipped build NOTHING —
# every byte of it is in the StuffIt overlay, which grew 18,582 -> 23,174 B.
#
# NOT COMPENSATED ANYWHERE, deliberately. TIERS above and OVL_RESIDUE below
# are measurements taken on the machine against a build **624 B smaller**,
# so every shipped prediction here is now ~1,200 B more generous than the
# Macintosh will be until both are re-taken there. Arithmetic is not a
# substitute for that measurement — subtracting from a stale one is how the
# floor budget was once made worse (DECISIONS.md 2026-09-22, *the fold, on a
# Macintosh*) — and it decides nothing: the narrowest margin between a
# passing layer's demand and its budget is 16,490 B. **WITHDRAWN
# 2026-10-09**: that margin was a2ps's, and by then the uncompensated drift
# had grown to 16.9 KB and taken it — TIERS above, re-taken that day.
# 2026-10-01: 117,664 -> 119,680 with zip's Macintosh extra fields in.
# The whole +2,016 is the gap widening rather than anything new being
# saved — the control took +2,024 B of resident CODE and the shipped
# build took none, the 8 B being the A5 the control gave back. This is
# the number the overlay build exists to make large.
# 2026-10-03: 124,640 -> 127,264 with StuffIt method 14 in, and the same
# shape again: the control took +2,620 B of resident CODE and +4 of A5
# and the shipped build took neither, every byte of the decoder being in
# the `ovl_stuffit` image.
# 2026-10-05: 127,264 -> 128,592 with AppleLink packages in, and this one
# moves BOTH sides: the control took +2,148 B of resident CODE and +28 of
# A5, the shipped build +788 and +60. The shipped half is the PROBE (666 B,
# resident because the sniffer calls it for every file), the release
# switch's new case, the shim and the engine's table row; the decoder is
# in the new `ovl_sqp` image. Like the rows above, nothing here is
# compensated: the three TIERS budgets below are machine measurements
# against a build 788 B smaller, so every shipped prediction is that much
# more generous than the Macintosh will be until they are re-taken there
# (FORMATS.md, *Three configurations, one tree*).
# 2026-10-05, same day, the zip-behind-a-stub probe: **UNCHANGED at
# 128,592**, and that is the interesting part. The control took +316 B of
# resident CODE and +4 of A5 and so did the shipped build — identically,
# because `src/fmt_zipseg.c` is resident in every configuration and
# nothing of it can go into an image: the sniffer calls that probe for
# every file it is handed. A difference of two equal numbers does not
# move, so this line is right by arithmetic rather than by luck, and
# check_saved() grades it either way. Not compensated either: the three
# TIERS budgets below are now a further 320 B more generous than the
# Macintosh will be until they are re-taken there (FORMATS.md, *What the
# zip pair claims, and what it costs*).
# 2026-10-07 again, the depth limit going: **129,072 -> 128,944**, -128 B.
# The shipped build grew 160 of code and gave back 32 of A5 for the
# re-scanning pop; the resident control grew only 48 and gave back 48,
# because the five decoders it carries each LOST the per-entry refusal.
# A difference of two numbers moving apart is what this line is.
# 2026-10-07, the folder-depth rule: **128,848 -> 129,040**, +192 B. The
# control pays +328 of CODE and +24 of A5 because it carries every decoder
# resident, the shipped build +120 and +40, and the difference of the two
# is what moves. NOT compensated, on the same terms as the rows above: the
# three TIERS budgets below are now a further 192 B more generous than the
# Macintosh will be until they are re-taken there (FORMATS.md, *How deep
# anything actually nests*).
# +32 on 2026-10-07, same day, for the claim a too-deep entry must not
# make about its name: the resident control carries that in five decoders
# and the shipped build's CODE + A5 does not move at all (73,552 B either
# side), so the whole of it is difference.
# **+1,856 on 2026-10-07, 129,008 -> 130,864, for zip method 6
# (Implode)**, and every byte of it is difference: the control's CODE
# rises 164,408 -> 166,264 with A5 unmoved, and the shipped build's CODE
# and A5 do not move at all. `src/fmt_exo.c` is in `ovl_exo`, so what
# ships pays the image (29,252 -> 31,176 B, IMAGES below) and nothing
# resident. Not compensated, on the same terms as every row above: the
# three TIERS budgets are a further 1,856 B more generous than the
# Macintosh will be until they are re-taken there — which is why the
# gain is also subtracted again by the image, one format at a time, in
# granted() (FORMATS.md, *Implode*).
# **+608 on 2026-10-08, 130,864 -> 131,472, for PKZIP 1.01/1.02's
# minimum match length** (*Implode*), and it is the same shape as the
# row above: the control's CODE rises 166,264 -> 166,884 and its A5
# FALLS 12 B, while the shipped build's CODE and A5 do not move at all
# in either configuration, so the whole of it is difference. What ships
# pays the image (31,176 -> 31,784 B, IMAGES below) and nothing
# resident. Not compensated, on the same terms as every row above
# (DECISIONS.md 2026-10-08, *the second attempt that had nowhere to
# go*).
# **+1,152 on 2026-10-08, 131,632 -> 132,784, for zip method 1
# (Shrink)**, the same shape again: the control's CODE rises 167,036 ->
# 168,200 and its A5 falls 12 B, and the shipped build's 54,272 + 19,056
# do not move. What ships pays two images instead of one — `ovl_codecs`
# 6,404 -> 7,520 and `ovl_exo` 31,936 -> 32,036 — because the decoder
# could not go in `ovl_exo` and is in `src/unc_lzw.c` (FORMATS.md,
# *Shrink*). Every format keeps the codecs image, so a grant moves by
# +1,152 - 1,116 = +36 B where only that one changed, and by -64 B for
# the formats that keep `ovl_exo` as well, and for an envelope, which
# keeps the whole bundle. Not compensated, on the same terms as every
# row above.
# **+1,280 on 2026-10-09, 132,784 -> 134,064, for Aladdin Private File**:
# the control's CODE +1,616 and A5 +64, the shipped build's +368 and +32,
# so the images hold the 1,248 B reader (in `ovl_stuffit`) and the rest is
# `.data` alignment stepping differently in the two builds. A Private
# File is an envelope and keeps the whole bundle, so its grant is the
# bundle's; for every other format the grant moves by +1,280 less
# whatever of `ovl_stuffit` (+1,676) and `ovl_crypt` (+108) it keeps.
# **-32 the same day, 134,064 -> 134,032**: the control's CODE -20 and
# A5 -12 when RC4's indices left the struct for the loop and the reader
# stopped keeping its record twice (DECISIONS.md 2026-10-09, *the
# specimen was one search away*); the shipped
# build does not move, both changes being in images.
# **+96 the same day, 134,032 -> 134,128**: the control's CODE +96 for
# Shrink's tick per partial clear (+76, `ovl_codecs` +108 with the
# forward it now calls) and the zip peek's Cancel (+20, `ovl_exo`); the
# shipped build does not move. TIERS fell by the same 96, so a grant moves
# by minus what of those two images it keeps.
# **+32 the same day, 134,128 -> 134,160**: the control's CODE +28 and A5
# +4 when zip's dry passes stopped counting progress; `ovl_exo` +28, the
# shipped build unmoved.
# **+128 the same day, 134,160 -> 134,288**: the control's CODE +136 and
# A5 -8 for DiskDoubler's buffer reuse and the MacLHA and uuencode
# progress counts; `ovl_cptdd` +144, `ovl_lzh` +18, `ovl_text` +8, the
# shipped build unmoved. No tally moved on either lane.
OVL_SAVED = 134288

# A relocatable block costs 8 bytes of header (Inside Macintosh: Memory), and
# every kept image is one — as is the bundle an envelope holds on to.
OVL_HANDLE = 8

# The constant the machine-measured granted budgets leave over the arithmetic
# above. **Re-measured 2026-09-27 with base and grant from one tree and one
# probe pair, over ELEVEN keep sets** — every row of FORMATS.md's *What each
# format is granted* that the Mac sample can reach, the envelope included —
# and all eleven leave the same constant to the byte (FORMATS.md, *What it
# buys, against the control*).
#
# 320 B of it is attributed: the probe build is not the shipped build, and
# `-D UNC_AT_BUDGET` costs the eager configuration 400 B of `CODE` + A5
# against the control's 304 B, so the pair the budgets are read off saves
# 116,720 B where the shipped pair saves 117,040 B. **The 346 B left over is
# reproducible** — it was the same 346 B either side of the AppleLink probe's
# removal, which moved the shipped build 496 B and every gain in this model
# not at all. It was +1,138 B on 2026-09-24's branch, measured against a base
# from that branch, and that is NOT a structural constant (DECISIONS.md
# 2026-09-27, *the residue that was two numbers*).
#
# DROPPING IT CHANGES NO PREDICTION, because the narrowest margin between a
# passing layer's demand and its budget is **29,613 B** across the three tiers
# this lane asserts — `popper-1.7.tar.Z`'s compress layer at System 3.0 /
# 512 KB, which needs 147,765 B of 177,378 — and 29,749 B on System 6.0.8 /
# 512 KB, gzip's layer (re-measured 2026-10-09 by bisecting every layer of
# all 72 fixtures at the re-taken budgets). It was 16,490 B on 2026-09-27,
# held by `a2ps.V4.3.tar.Z`, which the machine has refused since — so the
# nearest fixtures are now on the OTHER side: `synth-dd-m5.dd` is 1,274 B
# short at System 3.0 / 512 KB (1,130 until `ovl_cptdd` grew 144 B the same
# day, DERIVED: its demand did not move) and a2ps 4,070 B short at System 6.0.8.
# (DECISIONS.md 2026-09-26, *a budget per format, and one per layer*.)
OVL_RESIDUE = -666

# The fifteen images and the bundle they are read as, in bytes, measured
# 2026-09-26 off `build/mac/` and STUFFIT re-taken 2026-09-28, +208 B for the
# add-on module fields (FORMATS.md, *Where an archive names the module*) —
# which is where that change lands in the shipped build: resident code took
# 88 B of it and the rest is in the image, read at launch and released for
# every archive that is not a StuffIt one. **+48 B more the same day**, for
# the rule that an Optimizer nothing can undo is DECODED rather than
# refused, which the specimens settled; resident code and A5 did not move
# for it at all. **STUFFIT re-taken again 2026-10-03, +2,604 B for
# method 14** (src/sit14.c), 2,608 B of it in the image: resident code and
# A5 did not move for that either. **OVL_ID_SQP joined 2026-10-05**,
# 1,972 B, and it is the whole of what an AppleLink package's decoder
# costs the shipped build. **PACKIT re-taken 2026-10-05, -4 B**: the
# resync for an entry nothing can decrypt now steps the eight-byte
# cipher grid PackIt's own writer pads to, instead of scanning
# byte-wise, and the magic test it shares with the archive walk is
# written once instead of twice — which more than pays for the grid
# (FORMATS.md, *PackIt's two ciphers*). They are checked against that
# build whenever it is present (check_images below), so this table cannot
# drift silently while the toolchain is installed; it is stated rather than
# only read so that the lane still runs where Retro68 is not.
# **Five images re-taken 2026-10-07 for the folder-depth rule**, +220 B of
# bundle in total: CPTDD +52, NOW +118, PACKIT +4, SQP +32, SUPERDISK +16.
# **And re-taken again the same day when the depth LIMIT went**, -68 B
# net: CPTDD -72, NOW +22, PACKIT -4, SQP -4, SUPERDISK -14. Four of the
# five are smaller than they were that morning, the per-entry refusal
# each carried having gone with the limit; NOW is the one that grew,
# because its per-level entry counts have to survive a level the path
# string could not hold (fmt_now.c). The cost
# of removing the limit is resident, in the walker, not here
# (tools/build_mac.sh's eager pair).
# This is where that rule's per-format half lives — the `deep` test and the
# per-entry UNC_ERR_TOODEEP in each of the five walks — and it is in the
# images rather than resident on purpose: the shipped build pays 120 B of
# CODE and 40 of A5 for the walker and the message, and these 220 B are
# read at launch and released as soon as the sniff says what the archive is
# (FORMATS.md, *How deep anything actually nests*). NOW is the largest
# because its tree is implied by counts rather than marked, so it carries
# an accumulator and two ordered pop loops instead of one test.
# **STUFFIT and CRYPT re-taken 2026-10-09 for Private File**: +1,676 B
# for its reader, which lodges in the StuffIt image, and +108 B for the
# MD5-then-RC4 key setup in the cipher one. Then -12 and -4 the same
# day: the reader's record kept once, and RC4's indices in registers.
# **CODECS +108 and EXO +20 the same day** for a tick per Shrink partial
# clear and a Cancel the zip peek returns (FORMATS.md, *Shrink*).
# **CPTDD +144, LZH +18 and TEXT +8 the same day**: DiskDoubler moves its
# cursor inside the buffer it already has instead of re-reading it, and
# MacLHA's peek and uuencode's scan stop counting input twice
# (DECISIONS.md 2026-10-09, *DiskDoubler read every block six times*).
# **STUFFIT +24 B 2026-10-10**: a method-13 fork's encryptor id is not
# read (DECISIONS.md 2026-10-10, *the installer's own key*); a helper
# function and a clear-in-place came out at +24 and +36.
IMAGES = {
    "OVL_ID_ARC":         8120,
    "OVL_ID_BINHEX":      2590,
    "OVL_ID_BTOA":        2756,
    "OVL_ID_CODECS":      7628,
    "OVL_ID_CPTDD":       15908,
    "OVL_ID_CRYPT":       10244,
    "OVL_ID_EXO":         32084,
    "OVL_ID_LZH":         9586,
    "OVL_ID_NOW":         5078,
    "OVL_ID_PACKIT":      2644,
    "OVL_ID_SPACESAVER":  16722,
    "OVL_ID_STUFFIT":     27938,
    "OVL_ID_SQP":         2000,
    "OVL_ID_SUPERDISK":   7058,
    "OVL_ID_TEXT":        11510,
}
BUNDLE = 162064

# What the SHIPPED lane asserts, and it is the refused fixtures BY NAME
# rather than a tally: a tier that refuses two different fixtures and still
# counts 69 is exactly what a count cannot fail on. `sys3-512K` was run on
# the v0.33.0 binary on 2026-09-25 (`sys30.py --emu mv-512Ke`), the 1 MB
# floor on the v0.34.0 binary on 2026-09-26, and `sys6-512K` on v0.34.0 on
# 2026-09-27 (FORMATS.md, *512 KB machines* and *Floor target
# verification*).
#
# `sys6-512K` JOINED on 2026-09-27, and it is the one tier where this lane
# made a prediction before anything ran it: it said 66/71 and named five
# fixtures, and `run.py --emu mv-512Ke --system System6.hfv` on the v0.34.0
# binary returned 66/71 refusing those five and no others. That is the only
# unfalsified-then-tested prediction the model has, which is why the sweep
# was worth a boot (FORMATS.md, *512 KB machines*; DECISIONS.md 2026-09-27).
EXPECT_SHIPPED = {
    "floor-1M": (),
    "sys3-512K": ("derived-Library_ISBN_Barcoder.sit", "synth-dd-m5.dd"),
    # a2ps.V4.3.tar.Z joined 2026-10-09: the machine refused it (66/72) where
    # this lane, on a base 16,888 B stale, had passed it (TIERS above).
    "sys6-512K": ("a2ps.V4.3.tar.Z",
                  "derived-Cool_Tools__.sit", "derived-Library_ISBN_Barcoder.sit",
                  "derived-a2basic.dmg.sit", "popper-1.7.tar.Z",
                  "synth-dd-m5.dd"),
}

CCOMMENT = re.compile(r"/\*.*?\*/", re.S)


def formats(path=os.path.join(REPO, "src", "unc_engine.c")):
    """Every format's printed name and whether it is an envelope layer.

    Parsed from the engine's own table, because `sniff` prints those names
    and the shell unwraps exactly the rows flagged envelope: a copy here
    would be a model of a different program.
    """
    text = CCOMMENT.sub(" ", open(path, encoding="utf-8").read())
    body = text.split("unc_formats[] = {", 1)
    if len(body) != 2:
        raise SystemExit("run_tiers: cannot find unc_formats[] in %s" % path)
    out = {}
    for m in re.finditer(r"\{\s*(UNC_FORMAT_\w+),\s*\"([^\"]*)\",\s*(\d)\s*,"
                         r"\s*(\d)\s*,", body[1]):
        out[m.group(1)] = (m.group(2), m.group(4) == "1")
    if len(out) < 30:
        raise SystemExit("run_tiers: parsed %d formats, expected 30+ — the "
                         "engine's table changed shape" % len(out))
    return out


def keep_sets(path=os.path.join(REPO, "mac", "ovl_load_eager.c")):
    """Which images each format keeps, read out of the loader that does it.

    Returns {UNC_FORMAT_*: frozenset(OVL_ID_*)} plus the key "default" for
    everything the switch does not name. An empty set means the BUNDLE is
    kept whole, which is what an envelope does.
    """
    text = CCOMMENT.sub(" ", open(path, encoding="utf-8").read())
    if "ovl_keep(OVL_ID_CODECS" not in text:
        raise SystemExit("run_tiers: the loader no longer always keeps the "
                         "codecs image — this model says it does")
    if "if (crypt) ovl_keep(OVL_ID_CRYPT" not in text:
        raise SystemExit("run_tiers: the loader's cipher keep changed shape")
    body = text.split("switch (fmt) {", 1)
    if len(body) != 2:
        raise SystemExit("run_tiers: cannot find the release switch in %s"
                         % path)
    body = body[1]

    out, pend, want, crypt = {}, [], None, True
    for m in re.finditer(r"case\s+(UNC_FORMAT_\w+)\s*:|(default)\s*:|"
                         r"want\s*=\s*(OVL_ID_\w+)|crypt\s*=\s*0|"
                         r"(break)\s*;|(return)\s*;|(\n\s*\})", body):
        case, dflt, image, brk, ret, end = m.groups()
        if case or dflt:
            pend.append(case or "default")
        elif image:
            want = image
        elif m.group(0).startswith("crypt"):
            crypt = False
        elif brk or ret:
            keep = set()
            if ret:                      # an envelope: nothing is released
                keep = None
            else:
                if want:
                    keep.add(want)
                if crypt:
                    keep.add("OVL_ID_CRYPT")
                keep.add("OVL_ID_CODECS")
            for name in pend:
                out[name] = frozenset(keep) if keep is not None else frozenset()
            pend, want, crypt = [], None, True
            if ret and "default" in out:
                break                    # past the default: the switch is done
        elif end:
            break
    if "default" not in out or out["default"]:
        raise SystemExit("run_tiers: the release switch's default no longer "
                         "keeps the whole bundle")
    if len(out) < 15:
        raise SystemExit("run_tiers: parsed %d release cases, expected 15+"
                         % len(out))
    for keep in out.values():
        for image in keep:
            if image not in IMAGES:
                raise SystemExit("run_tiers: the loader keeps %s and this "
                                 "file has no size for it" % image)
    return out


def check_images(builddir=os.path.join(REPO, "build", "mac")):
    """Grade IMAGES against the build, where there is one. Returns a note."""
    bundle = os.path.join(builddir, "ovl_bundle.bin")
    if not os.path.exists(bundle):
        return "image sizes not checked (no %s)" % builddir
    bad = []
    for ident, size in sorted(IMAGES.items()):
        p = os.path.join(builddir,
                         "ovl_" + ident[len("OVL_ID_"):].lower() + ".bin")
        if not os.path.exists(p):
            bad.append("%s: no %s" % (ident, os.path.basename(p)))
        elif os.path.getsize(p) != size:
            bad.append("%s: %d B built, %d B here"
                       % (ident, os.path.getsize(p), size))
    if os.path.getsize(bundle) != BUNDLE:
        bad.append("bundle: %d B built, %d B here"
                   % (os.path.getsize(bundle), BUNDLE))
    if bad:
        raise SystemExit("run_tiers: the overlay images have moved —\n    "
                         + "\n    ".join(bad)
                         + "\n  Re-take IMAGES/BUNDLE from build/mac and say "
                           "so in the commit: a budget per format is made of "
                           "these numbers.")
    return "image sizes agree with %s" % os.path.relpath(builddir, REPO)


def code_and_a5(builddir):
    """`CODE` + A5 for one build, the way tools/build_mac.sh reads them.

    Returns None where the build or the m68k size tool is absent, which is
    every machine without Retro68 installed — this lane still runs there.
    """
    toolchain = os.environ.get("RETRO68", "/opt/Retro68-build/toolchain")
    size = os.path.join(toolchain, "bin", "m68k-apple-macos-size")
    gdb = os.path.join(builddir, "MacExtract.code.bin.gdb")
    if not os.access(size, os.X_OK) or not os.path.exists(gdb):
        return None
    out = subprocess.run([size, gdb], capture_output=True, text=True)
    row = out.stdout.splitlines()[1].split()          # text data bss ...
    return int(row[0]) + int(row[1]) + int(row[2])


def check_saved(ship=os.path.join(REPO, "build", "mac"),
                control=os.path.join(REPO, "build", "mac-resident")):
    """Grade OVL_SAVED against the two builds it is the difference of.

    Every format's gain is OVL_SAVED less the images it keeps, so a stale
    OVL_SAVED is a stale budget for all thirty formats at once — and it went
    32 B stale on 2026-09-26 with FORMATS.md corrected and this file not,
    which then read as part of the residue. A difference of two builds can be
    checked, so it is.
    """
    for t, (base, _desc) in TIERS.items():
        if base + TIERS_CONTROL != TIERS_MACHINE[t]:
            raise SystemExit(
                "run_tiers: TIERS[%s] + TIERS_CONTROL is %d B and the machine "
                "measured %d B —\n  move TIERS by exactly what "
                "TIERS_CONTROL moved, or re-take both on the machine."
                % (t, base + TIERS_CONTROL, TIERS_MACHINE[t]))
    a, b = code_and_a5(control), code_and_a5(ship)
    if a is None or b is None:
        return None
    if a - b != OVL_SAVED:
        raise SystemExit(
            "run_tiers: OVL_SAVED is %d B and the builds say %d B —\n"
            "    %s: %d B of CODE + A5\n    %s: %d B\n"
            "  Re-take OVL_SAVED, FORMATS.md's *Three configurations, one "
            "tree*\n  and OVL_RESIDUE together: the residue is measured "
            "against OVL_SAVED,\n  so correcting one alone moves every "
            "format's budget by the difference."
            % (OVL_SAVED, a - b, os.path.relpath(control, REPO), a,
               os.path.relpath(ship, REPO), b))
    if a != TIERS_CONTROL:
        raise SystemExit(
            "run_tiers: %s is %d B of CODE + A5 and TIERS was measured "
            "against %d B —\n  every budget in TIERS moves one for one "
            "with the control. Re-take them on\n  the machine (-D "
            "UNC_OVL_RESIDENT -D UNC_AT_BUDGET), or lower all three by "
            "the\n  growth and say so, then move TIERS_CONTROL."
            % (os.path.relpath(control, REPO), a, TIERS_CONTROL))
    return ("OVL_SAVED agrees with %s less %s (%d B), and TIERS was taken "
            "against this control"
            % (os.path.relpath(control, REPO), os.path.relpath(ship, REPO),
               OVL_SAVED))


def gain(keep):
    """What the overlay release gives this format's layer, in bytes."""
    if not keep:                          # the whole bundle stays
        return OVL_SAVED + OVL_RESIDUE - BUNDLE - OVL_HANDLE
    return (OVL_SAVED + OVL_RESIDUE - sum(IMAGES[i] for i in keep)
            - OVL_HANDLE * len(keep))


def names(listfile):
    out = []
    for line in open(listfile, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line.split("#")[0].strip())
    return out


def sweep(binary, fixtures, budget, fixdir):
    fails = []
    for n in fixtures:
        p = os.path.join(fixdir, n)
        if not os.path.exists(p):
            print("run_tiers: missing fixture %s" % p, file=sys.stderr)
            return None
        r = subprocess.run([binary, "t", "--budget", str(budget), p],
                           capture_output=True, text=True)
        m = SHORT.search(r.stderr)
        if m:
            fails.append((n, int(m.group(1))))
        elif r.returncode != 0:
            fails.append((n, -1))
    return fails


# --- the shipped lane -------------------------------------------------------

def sniff(binary, path):
    r = subprocess.run([binary, "sniff", path], capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def peel(binary, path, tmp, fmts):
    """The layers the Mac shell would take this file apart in.

    One (format, file) per layer, outermost first. The shell calls its
    extractor once per envelope layer and re-takes a budget each time
    (mac/macextract_mac.c, ExtractOne), so each layer is measured against the
    budget the release leaves for ITS format — which is the whole reason this
    lane cannot sweep a fixture in one call.
    """
    env = {name: e for name, (_, e) in fmts.items()}
    byname = {n: ident for ident, (n, _) in fmts.items()}
    out, cur, depth = [], path, 0
    while True:
        shown = sniff(binary, cur)
        if shown == "unknown":
            break                    # an envelope's payload, not an archive
        ident = byname.get(shown)
        if ident is None:
            print("run_tiers: `sniff` said %r, which is in no format table"
                  % shown, file=sys.stderr)
            return None
        out.append((ident, shown, cur))
        if not env[ident]:
            break
        depth += 1
        if depth > 4:
            print("run_tiers: %s nests deeper than this model peels"
                  % os.path.basename(path), file=sys.stderr)
            return None
        d = os.path.join(tmp, "%s.L%d" % (os.path.basename(path), depth))
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        subprocess.run([binary, "x", "-nr", "-o", d, cur],
                       capture_output=True, text=True)
        got = [os.path.join(dp, f) for dp, _, fn in os.walk(d) for f in fn
               if not f.endswith(".rsrc")]
        if len(got) != 1:
            print("run_tiers: unwrapping %s gave %d files, and an envelope "
                  "layer is one" % (os.path.basename(cur), len(got)),
                  file=sys.stderr)
            return None
        cur = got[0]
    return out


def sweep_shipped(binary, fixtures, base, fixdir, keep, fmts, tmp):
    """Sweep at `base` plus what each layer's format gets back."""
    fails = []
    for n in fixtures:
        p = os.path.join(fixdir, n)
        if not os.path.exists(p):
            print("run_tiers: missing fixture %s" % p, file=sys.stderr)
            return None
        layers = peel(binary, p, tmp, fmts)
        if layers is None:
            return None
        if not layers:
            # Nothing to measure is not a pass: a sweep that peeled every
            # fixture to nothing would report the whole sample clear.
            print("run_tiers: %s sniffs as nothing this engine reads" % n,
                  file=sys.stderr)
            return None
        for ident, shown, path in layers:
            budget = base + gain(keep.get(ident, keep["default"]))
            r = subprocess.run([binary, "t", "-nr", "--budget", str(budget),
                                path], capture_output=True, text=True)
            m = SHORT.search(r.stderr)
            if m:
                fails.append((n, int(m.group(1)), shown, budget))
                break
            if r.returncode != 0:
                fails.append((n, -1, shown, budget))
                break
    return fails


def report(fails, indent):
    for f in sorted(fails, key=lambda x: x[1]):
        short = "{:,}".format(f[1]) if f[1] >= 0 else "(other failure)"
        extra = "" if len(f) < 4 else "   [%s at %s B]" % (f[2],
                                                           "{:,}".format(f[3]))
        print("%s%-42s short by at least %s%s" % (indent, f[0], short, extra))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--macextract", default=os.path.join(REPO, "build",
                                                         "rel", "macextract"))
    ap.add_argument("--list", default=os.path.join(HERE, "vmac", "sample.txt"))
    ap.add_argument("--fixtures", default=os.path.join(REPO, "fixtures"))
    ap.add_argument("--tier", choices=sorted(TIERS))
    ap.add_argument("--budget", type=int,
                    help="an explicit cap, instead of a tier's")
    ap.add_argument("--shipped", action="store_true",
                    help="the 'OVLY' build: a budget per format, per layer")
    ap.add_argument("--check", action="store_true",
                    help="sweep both lanes' asserted tiers, fail on a change")
    ap.add_argument("--check-images", action="store_true",
                    help="grade IMAGES against build/mac and stop; `make "
                         "clean` means --check runs before that build exists")
    ap.add_argument("--check-saved", action="store_true",
                    help="grade OVL_SAVED against build/mac and "
                         "build/mac-resident and stop; needs BOTH built, so "
                         "it runs after ci.sh's resident control")
    a = ap.parse_args()
    if a.check_images:
        print("run_tiers: %s" % check_images())
        return 0
    if a.check_saved:
        # Asked for by name, so not being able to check is a failure: ci.sh
        # runs this after both builds, and a step that cannot fail is not
        # a check.
        r = check_saved()
        if r is None:
            raise SystemExit("run_tiers: --check-saved needs build/mac, "
                             "build/mac-resident and the m68k size tool")
        print("run_tiers: %s" % r)
        return 0
    if not a.tier and not a.budget and not a.check:
        ap.error("give --tier, --budget or --check")
    if not os.path.exists(a.macextract):
        raise SystemExit("run_tiers: no %s — build it first" % a.macextract)

    fixtures = names(a.list)
    keep = fmts = tmp = None
    if a.shipped or a.check:
        fmts, keep = formats(), keep_sets()
        print("run_tiers: %s" % check_images())
        print("run_tiers: %s" % (check_saved() or
                                 "OVL_SAVED not checked (no m68k size tool, "
                                 "or build/mac and build/mac-resident are "
                                 "not both built)"))
        tmp = tempfile.mkdtemp(prefix="run_tiers.")
    try:
        if a.check:
            bad = 0
            for tier, want in sorted(EXPECT.items()):
                fails = sweep(a.macextract, fixtures, TIERS[tier][0],
                              a.fixtures)
                if fails is None:
                    return 1
                got = len(fixtures) - len(fails)
                ok = sorted(f[0] for f in fails) == sorted(want)
                print("run_tiers: resident %-11s %d/%d pass at %d bytes%s"
                      % (tier, got, len(fixtures), TIERS[tier][0],
                         "" if ok else "   EXPECTED %d, refusing %s"
                         % (len(fixtures) - len(want),
                            ", ".join(want) or "nothing")))
                report(fails, "     ")
                bad += not ok
            for tier in sorted(TIERS):
                fails = sweep_shipped(a.macextract, fixtures, TIERS[tier][0],
                                      a.fixtures, keep, fmts, tmp)
                if fails is None:
                    return 1
                got = len(fixtures) - len(fails)
                want = EXPECT_SHIPPED.get(tier)
                note = "   (not asserted: no machine has run this tier)"
                if want is not None:
                    note = ("" if sorted(f[0] for f in fails) == sorted(want)
                            else "   EXPECTED %d, refusing %s"
                                 % (len(fixtures) - len(want),
                                    ", ".join(want) or "nothing"))
                    bad += bool(note)
                print("run_tiers: shipped  %-11s %d/%d pass, per format%s"
                      % (tier, got, len(fixtures), note))
                report(fails, "     ")
            return 1 if bad else 0

        budget = a.budget or TIERS[a.tier][0]
        what = a.tier and TIERS[a.tier][1] or "an explicit budget"
        if a.shipped:
            fails = sweep_shipped(a.macextract, fixtures, budget, a.fixtures,
                                  keep, fmts, tmp)
            if fails is None:
                return 1
            print("run_tiers: %d of %d pass on the shipped build — %s"
                  % (len(fixtures) - len(fails), len(fixtures), what))
            print("   a budget per format: %d B resident, plus %s B by format"
                  % (budget, "{:,} to {:,}".format(
                      min(gain(k) for k in keep.values()),
                      max(gain(k) for k in keep.values()))))
            report(fails, "   ")
            return 0

        fails = sweep(a.macextract, fixtures, budget, a.fixtures)
        if fails is None:
            return 1
        print("run_tiers: %d of %d pass at %d bytes — %s"
              % (len(fixtures) - len(fails), len(fixtures), budget, what))
        report(fails, "   ")
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

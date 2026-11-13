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
  what the `'OVLY'` build has: the decoders and the sniffer are seventeen images read as
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
of `mac/release_plan.inc.c`'s own table, the format names out of the
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
- **Nothing about encryption it does not ask.** The shell drops the
  ciphers for the formats its release condition names when
  `unc_archive_encrypted` says NO; since 2026-11-03 this lane reads that
  condition out of `mac/release_plan.inc.c` and asks the same function
  through `tools/encinfo_probe.c`, layer by layer. Until then it kept the
  ciphers for Compact Pro and zip always and granted 10,252 B less than the
  machine (DECISIONS.md 2026-11-03, *the ciphers a header can refuse*).
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
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import budgets  # noqa: E402
import unc_formats  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# The figures below are tools/budgets.txt's (tools/budgets.py), with every
# other size this tree asserts about its builds: tools/retake_budgets.py
# rewrites the ones a build measures, and the machine's are re-taken on the
# emulator. Their history is that file's git log and DECISIONS.md; it was
# kept here, a paragraph a change, until 2026-11-13.

# What the MACHINE measured: each tier's budget, `FreeMem() - 20,480` taken
# with `-D UNC_OVL_RESIDENT -D UNC_AT_BUDGET` (FORMATS.md, *Budget*, *512 KB
# machines*), plus the control it was read against. A change to the
# application cannot move these sums; only a re-take on the machine does.
TIERS_MACHINE = {
    "sys3-512K": budgets.get("TIERS_MACHINE_SYS3_512K"),
    "sys6-512K": budgets.get("TIERS_MACHINE_SYS6_512K"),
    "floor-1M":  budgets.get("TIERS_MACHINE_FLOOR_1M"),
}

# The resident control's CODE + A5 (build/mac-resident): what those budgets
# were read against, pinned, so that --check-saved (in ci.sh) fails when the
# control build moves away from it. A sum whose terms are kept current at
# different rates is wrong by exactly the term nobody re-takes.
# **What this control cannot see: the autotest harness.** The budgets were
# read from an autotest build (`UNC_MAC_AUTOTEST`), and build/mac-resident
# has no harness in it, so harness growth lowers what a sweep is granted and
# moves nothing --check-saved compares.
TIERS_CONTROL = budgets.get("TIERS_CONTROL")

# THE RESIDENT BUILD'S BUDGETS, which is what a build with every decoder
# linked in has and not what ships: the machine's sum less the control. A
# control-build change moves them one for one (DECISIONS.md 2026-10-09, *the
# base nobody re-took*). The shipped build's budget is one of these PLUS what
# the overlay release gives back for the sniffed format, which is the
# `--shipped` lane below.
TIERS = {
    "sys3-512K": (TIERS_MACHINE["sys3-512K"] - TIERS_CONTROL,
                  "System 3.0, Macintosh 512Ke (204,168 B free)"),
    "sys6-512K": (TIERS_MACHINE["sys6-512K"] - TIERS_CONTROL,
                  "System 6.0.8, Macintosh 512Ke (108,764 B free)"),
    "floor-1M":  (TIERS_MACHINE["floor-1M"] - TIERS_CONTROL,
                  "System 6.0.8, 1 MB Mac Plus — the floor target"),
}


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
# 65 -> 64 at sys6-512K on 2026-10-11, DERIVED and not run on the
# machine: the control's +704 B for `JPEG Lossy` at every width and mode
# puts `derived-DD_Expand.sea` 436 B short, where it had 268 B to spare.
# The shipped lanes do not move: the material is all in `ovl_stuffit`
# (DECISIONS.md 2026-10-11, *the constant was a square*).
# 64 -> 63 at sys6-512K on 2026-11-02, DERIVED: `derived-PuzzleGetter_0.8.sit`
# (below). 63 -> 64 on 2026-11-03, DERIVED: it left again.
# 64 -> 62 at sys6-512K on 2026-11-11, DERIVED: the 'part' resources (below).
# 62 -> 63 on 2026-11-13, DERIVED: `derived-PuzzleGetter_0.8.sit` left again
# with the folder memo's 1,600 B of A5 (below).
EXPECT = {
    "floor-1M": (),
    "sys3-512K": ("derived-Cool_Tools__.sit",
                  "derived-Library_ISBN_Barcoder.sit",
                  "derived-a2basic.dmg.sit", "synth-dd-m5.dd"),
    "sys6-512K": ("derived-Cool_Tools__.sit", "derived-DD_Expand.sea",
                  "derived-Expand_Now_1.0.1.sea",
                  "derived-LHA_Expander_1.0.3.sea",
                  "derived-Library_ISBN_Barcoder.sit",
                  # `derived-PuzzleGetter_0.8.sit` joined 2026-11-02,
                  # DERIVED, needing 101,582 B of 101,064 (DECISIONS.md
                  # 2026-11-02, *the dialogs that became the application*),
                  # and left 2026-11-03: StuffIt 5's folder table is no
                  # longer a fixed 18,440 B, and it needs 83,654 (bisected;
                  # DECISIONS.md 2026-11-03, *the folders past the table*).
                  "derived-Terrainman_2.0__.sea",
                  "derived-Troi-ClipSave-Plug-in1.1.sit",
                  # Joined 2026-10-17: the control grew 4,592 B with the
                  # archives' Finder info, every reader resident in it, and
                  # this one needs between 98,780 and 103,372 B. The
                  # shipped lane does not move (DECISIONS.md 2026-10-17,
                  # *the archives' own Finder info*).
                  # Left 2026-10-22: the MacsBug names stripped give the
                  # control 10,176 B back, and this one needed less than
                  # that (DECISIONS.md 2026-10-22, *the names in the code*).
                  "derived-a2basic.dmg.sit", "popper-1.7.tar.Z",
                  "synth-dd-m5.dd",
                  # Both joined 2026-11-11, DERIVED: the control grew
                  # 4,800 B with an Installer Tome's 'part' resources,
                  # every reader resident in it. The shipped lane does
                  # not move (DECISIONS.md 2026-11-11, *the parts the
                  # Installer expands*).
                  # PuzzleGetter, the second, left 2026-11-13: the folder
                  # memo's 1,600 B went from A5 onto the relocator's dead
                  # code (DECISIONS.md 2026-11-13, *the memo on the
                  # relocator*).
                  "a2ps.V4.3.tar.Z"),
                  # Five more were refused from 2026-11-12 while Installer
                  # VISE was resident in the control, and left with it the
                  # same day (DECISIONS.md 2026-11-12, *VISE parked*).
}

# ---------------------------------------------------------------------------
# The shipped build's model: a budget per tier PER FORMAT.
# ---------------------------------------------------------------------------

# What the overlay build does NOT carry resident, in bytes: the control's
# `CODE` + A5 less the shipped build's (FORMATS.md, *Three configurations,
# one tree*). check_saved() below grades it against the two builds whenever
# they and the toolchain are present, so a stale figure fails `ci.sh`
# instead of surfacing as a residue.
OVL_SAVED = budgets.get("OVL_SAVED")

# A relocatable block costs 8 bytes of header (Inside Macintosh: Memory).
# Since 2026-11-11 what a release keeps is ONE block, the bundle's own, cut
# down to a directory of 4 B and 12 B an image, then the images, each
# aligned to 4 as tools/overlay/mkbundle.py aligns them (mac/ovl_load_eager.c,
# ovl_pack); until then each kept image was a handle of its own.
OVL_HANDLE = 8
OVL_DIR_HEAD = 4
OVL_DIR_ENTRY = 12

# The constant the machine-measured granted budgets leave over the arithmetic
# above: the shipped and the resident budget probes booted back to back on
# all three tiers, the measured shipped budget less TIERS + OVL_SAVED, the
# images kept and their headers, the most pessimistic of the three. Part of
# it is attributed — the probe build is not the shipped build, and `-D
# UNC_AT_BUDGET` costs the two configurations different amounts — and the
# rest is reproducible (DECISIONS.md 2026-09-27, *the residue that was two
# numbers*; 2026-11-11, *the glue the shell expands*). Re-taken on the
# machine, never from a build.
OVL_RESIDUE = budgets.get("OVL_RESIDUE")

# The images and the bundle they are read as, in bytes, off `build/mac/`.
# check_images() below grades them against that build whenever it is
# present, so this table cannot drift from what the Macintosh reads.
IMAGES = budgets.images()
BUNDLE = budgets.get("BUNDLE")

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
    # derived-Cool_Tools__.sit and derived-a2basic.dmg.sit left 2026-11-03,
    # predicted here and then run on the machine: a StuffIt 5 header with no
    # password hash releases the ciphers (DECISIONS.md 2026-11-03, *the
    # ciphers a header can refuse*). a2ps.V4.3.tar.Z and popper-1.7.tar.Z
    # left the same day the same way: an envelope that names what it holds
    # keeps only that (*the envelope that said what it held*).
    "sys6-512K": ("derived-Library_ISBN_Barcoder.sit", "synth-dd-m5.dd"),
}

CCOMMENT = re.compile(r"/\*.*?\*/", re.S)


def formats():
    """Every format's printed name and whether it is an envelope layer.

    Read from the engine's own list (src/unc_formats.h, through
    tools/unc_formats.py), because `sniff` prints those names and the shell
    unwraps exactly the ENVELOPE rows: a copy here would be a model of a
    different program.
    """
    return {f.id: (f.name, f.kind == "ENVELOPE")
            for f in unc_formats.formats()}


PLAN = os.path.join(REPO, "mac", "release_plan.inc.c")


def plan_rows(text):
    """The release table's rows as (format, image, set of flags): every
    FORMAT of src/unc_formats.h with a KEEP column, the image its run row
    names. `text` is the plan's own source, which must still build gKeepSet
    from that list (DECISIONS.md 2026-11-11, *the release decided in the
    bundle*)."""
    if "UNC_FORMATS(KEEP_SET_ROW)" not in text:
        raise SystemExit("run_tiers: %s no longer builds gKeepSet from "
                         "src/unc_formats.h" % PLAN)
    out = []
    for f in unc_formats.formats():
        if f.keep is None:
            continue
        if f.run is None:
            raise SystemExit("run_tiers: %s keeps its run row's image and "
                             "has no run row" % f.id)
        fl = set(x.strip() for x in f.keep.split("|")) - {"0"}
        if fl - {"KEEP_CRYPT", "KEEP_PEEK", "KEEP_ZIPOLD"}:
            raise SystemExit("run_tiers: a release flag this model does not "
                             "know: %s" % f.keep)
        out.append((f.id, f.run[0], fl))
    return out


def keep_sets(path=PLAN):
    """Which images each format keeps, read out of the plan the loader keeps.

    Returns {UNC_FORMAT_*: frozenset(OVL_ID_*)} plus the key "default" for
    everything the table does not name. An empty set means the BUNDLE is
    kept whole, which is what an envelope does.
    """
    text = CCOMMENT.sub(" ", open(path, encoding="utf-8").read())
    # The plan's keeps, one `*k++ =` each: the format's own image, the two a
    # peeked envelope adds (peek_keep()'s), zip's old methods, the ciphers
    # and the codecs. A keep of another shape would be an image the model
    # under-charges, so anything else is refused rather than skipped.
    keeps = re.findall(r"(?:if\s*\(([^;{}]*?)\)\s*)?\*k\+\+\s*=\s*([^;]+);",
                       text)
    want = [("", "(unsigned char)want"),
            ("", "(unsigned char)inner"),
            ("", "OVL_ID_SNIFF - OVL_ID_CRYPT"),
            ("row & KEEP_ZIPOLD", "OVL_ID_ZIPOLD - OVL_ID_CRYPT"),
            ("row & KEEP_CRYPT", "0"),
            ("", "OVL_ID_CODECS - OVL_ID_CRYPT")]
    if [(c.strip(), v.strip()) for c, v in keeps] != want:
        raise SystemExit("run_tiers: the release plan's keeps changed shape "
                         "— this model reads six, the codecs always: %r"
                         % keeps)
    out = {"default": frozenset()}
    for fmt, image, fl in plan_rows(text):
        if "KEEP_PEEK" in fl:
            continue                     # an envelope: peek_rows()
        keep = {image, "OVL_ID_CODECS"}
        if "KEEP_CRYPT" in fl:
            keep.add("OVL_ID_CRYPT")
        if "KEEP_ZIPOLD" in fl:
            keep.add("OVL_ID_ZIPOLD")
        out[fmt] = frozenset(keep)
    if len(out) < 15:
        raise SystemExit("run_tiers: parsed %d release rows, expected 15+"
                         % len(out))
    for keep in out.values():
        for image in keep:
            if image not in IMAGES:
                raise SystemExit("run_tiers: the loader keeps %s and this "
                                 "file has no size for it" % image)
    return out


def cipher_release(path=PLAN):
    """The formats whose ciphers the loader drops on a definite NO from
    unc_archive_encrypted, read out of the condition that does it."""
    text = CCOMMENT.sub(" ", open(path, encoding="utf-8").read())
    m = re.search(r"if\s*\(\s*\(row\s*&\s*KEEP_CRYPT\)\s*&&\s*\(([^;{}]*?)\)"
                  r"\s*\)\s*\{[^{}]*?OVL_ARCHIVE_ENCRYPTED[^{}]*?"
                  r"if\s*\(\s*enc\s*==\s*UNC_ENC_NO\s*\)\s*row\s*&=\s*~KEEP_CRYPT",
                  text)
    if not m:
        raise SystemExit("run_tiers: the loader's cipher release changed "
                         "shape")
    return frozenset(re.findall(r"as\s*==\s*(UNC_FORMAT_\w+)", m.group(1)))


def peek_rows(path=PLAN):
    """The envelopes the loader peeks into, and the image each one's reader
    is in: the KEEP_PEEK rows of its table."""
    text = CCOMMENT.sub(" ", open(path, encoding="utf-8").read())
    return {fmt: image for fmt, image, fl in plan_rows(text)
            if "KEEP_PEEK" in fl}


def encinfo_probe(tmp):
    """tools/encinfo_probe.c, built once: the engine's own
    unc_archive_encrypted, which the CLI does not reach. Returns a function
    from a layer's path to "yes", "no" or "unknown"."""
    probe = os.path.join(tmp, "encinfo_probe")
    src = [os.path.join(HERE, "encinfo_probe.c")]
    src += sorted(glob.glob(os.path.join(REPO, "src", "*.c")))
    src += sorted(glob.glob(os.path.join(REPO, "third_party", "zlib", "*.c")))
    inc = ["-I" + os.path.join(REPO, d)
           for d in ("include", "src", os.path.join("third_party", "zlib"))]
    cc = subprocess.run(["cc", "-O1", "-o", probe] + inc + src,
                        capture_output=True, text=True)
    if cc.returncode != 0:
        raise SystemExit("run_tiers: encinfo_probe did not build: "
                         + cc.stderr.strip().split("\n")[-1])

    def ask(path, peek=False):
        if not peek:
            out = subprocess.run([probe, path], capture_output=True,
                                 text=True).stdout.split()
            return out[0] if out else "unknown"
        # "<inner format name> <yes|no|unknown> <peak> <path>", the name
        # possibly with spaces in it, "-" for none.
        line = subprocess.run([probe, "--peek", path], capture_output=True,
                              text=True).stdout.strip()
        if not line.endswith(path):
            return None, "unknown", 0
        name, enc, peak = line[:-len(path)].rstrip().rsplit(" ", 2)
        return (None if name == "-" else name), enc, int(peak)
    return ask


# The reserve the shell leaves when it takes a budget: `FreeMem() - 20,480`
# (FORMATS.md, *Budget*). The peek runs on NewPtr before the budget is
# taken, so what it can have is a budget plus this.
RESERVE = 20480


def unnamed_keeps(path=PLAN):
    """What an envelope whose payload's first bytes name nothing keeps beside
    its own reader: the plan's `gUnnamed` table (DECISIONS.md 2026-11-11,
    *the head that named nothing*), each entry an offset from OVL_ID_CRYPT."""
    text = CCOMMENT.sub(" ", open(path, encoding="utf-8").read())
    m = re.search(r"gUnnamed\[\]\s*=\s*\{([^}]*)\}", text)
    if not m:
        raise SystemExit("run_tiers: the plan's gUnnamed changed shape")
    out = set()
    for e in m.group(1).split(","):
        e = e.strip()
        if not e:
            continue
        if e == "0":
            out.add("OVL_ID_CRYPT")
            continue
        mm = re.fullmatch(r"(OVL_ID_\w+)\s*-\s*OVL_ID_CRYPT", e)
        if not mm or mm.group(1) not in IMAGES:
            raise SystemExit("run_tiers: a gUnnamed entry this model cannot "
                             "read: %r" % e)
        out.add(mm.group(1))
    return frozenset(out)


def peek_keep(ident, path, base, keep, peek, release, ask, fmts):
    """What an envelope layer keeps, as ovl_release_if_unwanted decides it:
    its own reader, the format its first bytes name and what that keeps, and
    the sniffer; its own reader and gUnnamed when the peek names nothing, or
    cannot run in the heap the bundle leaves (a peek that fails names
    nothing); or the whole bundle (an empty set) when it names a format this
    table does not keep, or another envelope."""
    name, enc, peak = ask(path, peek=True)
    if name is None or peak > base + gain(frozenset()) + RESERVE:
        return frozenset(unnamed_keeps() | {peek[ident]})
    inner = next((k for k, (n, _env) in fmts.items() if n == name), None)
    if inner is None or inner not in keep or inner in peek:
        return frozenset()
    k = set(keep[inner]) | {peek[ident], "OVL_ID_SNIFF"}
    if inner in release and enc == "no":
        k.discard("OVL_ID_CRYPT")
    return frozenset(k)


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
    # And the other direction: an image the build has and this table does
    # not. Until 2026-10-11 only the table was walked, so a sixteenth image
    # showed up as nothing but a bundle that had grown.
    import glob
    for p in sorted(glob.glob(os.path.join(builddir, "ovl_*.bin"))):
        name = os.path.basename(p)[len("ovl_"):-len(".bin")]
        if name.startswith("bundle"):        # the bundle, and its Rez fork
            continue
        if "OVL_ID_" + name.upper() not in IMAGES:
            bad.append("OVL_ID_%s: %d B built, not in tools/budgets.txt"
                       % (name.upper(), os.path.getsize(p)))
    if os.path.getsize(bundle) != BUNDLE:
        bad.append("bundle: %d B built, %d B here"
                   % (os.path.getsize(bundle), BUNDLE))
    if bad:
        raise SystemExit("run_tiers: the overlay images have moved —\n    "
                         + "\n    ".join(bad)
                         + "\n  Run tools/retake_budgets.py and say in the "
                           "commit what moved: a budget per format is made "
                           "of these numbers.")
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
    # The stripped MacsBug names stay in the ELF as a NOLOAD section that
    # `size` still counts as text; no byte of it is resident. Same
    # subtraction as tools/build_mac.sh (DECISIONS.md 2026-10-22, *the
    # names in the code*).
    names = 0
    full = subprocess.run([size, "-A", gdb], capture_output=True, text=True)
    for line in full.stdout.splitlines():
        cols = line.split()
        if cols and cols[0] == ".strippedmacsbugnames":
            names = int(cols[1])
    return int(row[0]) + int(row[1]) + int(row[2]) - names


def check_saved(ship=os.path.join(REPO, "build", "mac"),
                control=os.path.join(REPO, "build", "mac-resident")):
    """Grade OVL_SAVED against the two builds it is the difference of.

    Every format's gain is OVL_SAVED less the images it keeps, so a stale
    OVL_SAVED is a stale budget for all thirty formats at once — and it went
    32 B stale on 2026-09-26 with FORMATS.md corrected and this file not,
    which then read as part of the residue. A difference of two builds can be
    checked, so it is.
    """
    a, b = code_and_a5(control), code_and_a5(ship)
    if a is None or b is None:
        return None
    if a - b != OVL_SAVED:
        raise SystemExit(
            "run_tiers: OVL_SAVED is %d B and the builds say %d B —\n"
            "    %s: %d B of CODE + A5\n    %s: %d B\n"
            "  Run tools/retake_budgets.py, which re-takes it with "
            "TIERS_CONTROL and the\n  grants FORMATS.md derives from them, "
            "and say in the commit what moved."
            % (OVL_SAVED, a - b, os.path.relpath(control, REPO), a,
               os.path.relpath(ship, REPO), b))
    if a != TIERS_CONTROL:
        raise SystemExit(
            "run_tiers: %s is %d B of CODE + A5 and TIERS was measured "
            "against %d B —\n  every budget in TIERS moves one for one "
            "with the control. Run\n  tools/retake_budgets.py."
            % (os.path.relpath(control, REPO), a, TIERS_CONTROL))
    return ("OVL_SAVED agrees with %s less %s (%d B), and TIERS was taken "
            "against this control"
            % (os.path.relpath(control, REPO), os.path.relpath(ship, REPO),
               OVL_SAVED))


def gain(keep):
    """What the overlay release gives this format's layer, in bytes."""
    if not keep:                          # the whole bundle stays
        return OVL_SAVED + OVL_RESIDUE - BUNDLE - OVL_HANDLE
    return (OVL_SAVED + OVL_RESIDUE - OVL_HANDLE - OVL_DIR_HEAD
            - sum((IMAGES[i] + 3) // 4 * 4 + OVL_DIR_ENTRY for i in keep))


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


def sweep_shipped(binary, fixtures, base, fixdir, keep, fmts, tmp,
                  release=frozenset(), ask=None, peek=None):
    """Sweep at `base` plus what each layer's format gets back. A layer of
    a format in `release` keeps no ciphers when `ask` says NO, as the
    loader does."""
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
            k = keep.get(ident, keep["default"])
            if peek and ident in peek:
                k = peek_keep(ident, path, base, keep, peek, release, ask,
                              fmts)
            elif ident in release and "OVL_ID_CRYPT" in k and \
                    ask(path) == "no":
                k = k - {"OVL_ID_CRYPT"}
            budget = base + gain(k)
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
    keep = fmts = tmp = ask = peek = None
    release = frozenset()
    if a.shipped or a.check:
        fmts, keep, release = formats(), keep_sets(), cipher_release()
        peek = peek_rows()
        print("run_tiers: %s" % check_images())
        print("run_tiers: %s" % (check_saved() or
                                 "OVL_SAVED not checked (no m68k size tool, "
                                 "or build/mac and build/mac-resident are "
                                 "not both built)"))
        tmp = tempfile.mkdtemp(prefix="run_tiers.")
        ask = encinfo_probe(tmp)
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
                                      a.fixtures, keep, fmts, tmp,
                                      release, ask, peek)
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
                                  keep, fmts, tmp, release, ask, peek)
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

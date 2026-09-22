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

So a whole tier can be swept here in five seconds:

    tools/run_tiers.py --tier sys3-512K
    tools/run_tiers.py --budget 123962 --list tools/vmac/sample.txt
    tools/run_tiers.py --tier floor-1M --macextract build/rel/macextract

It prints one line per refusal with the shortfall, and the tally. On
2026-09-22, with all three budgets re-taken on the machine the same day,
it reproduced ALL THREE tiers exactly — 71/71, 67/71 and 64/71, the same
four and seven fixtures by name that the emulators refuse. It had never
matched the third before, and what was wrong was the budget and not the
model.

What it CANNOT see, and why the emulator stays
----------------------------------------------
- **The budget itself, which is the one that has actually bitten.** It
  is `FreeMem() - 20,480` measured on the machine (FORMATS.md,
  *Budget*), so every constant here goes stale the moment the
  application's size does, and this file cannot notice. All three were
  stale on 2026-09-22 — two by 21,666 B — and the one-fixture
  System 6.0.8 / 512 KB disagreement that had been filed under
  fragmentation below was this, entirely.
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
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# Measured budgets, one per tier that has ever refused anything. Each is
# `FreeMem() - 20,480` taken on the machine with `-D UNC_AT_BUDGET`;
# FORMATS.md (*Budget*, *512 KB machines*) is where they come from and
# the only place they should be corrected.
TIERS = {
    "sys3-512K": (219362, "System 3.0, Macintosh 512Ke (239,842 B free)"),
    "sys6-512K": (123962, "System 6.0.8, Macintosh 512Ke (144,442 B free)"),
    "floor-1M":  (648250, "System 6.0.8, 1 MB Mac Plus — the floor target"),
}

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

# What --check asserts: every tier an emulator has independently agreed
# with, which since 2026-09-22 is all three. Each matches the machine
# fixture for fixture — `floor-1M` 71/71, `sys3-512K` 67/71 (the same
# four names), `sys6-512K` 64/71 (the same seven). `sys6-512K` was a
# diagnostic until that day because it read 59/69 where the machine said
# 58 and later 63; it is asserted now, because the disagreement was the
# stale budget above and not the model.
#
# A tally that moves here is either a memory regression or a memory WIN;
# both want the number below changed deliberately, which is the point of
# pinning it. 69 -> 71 on 2026-09-22: the sample gained the two StuffIt 5
# fixtures whose names are UTF-8, and `derived-Cool_Tools__.sit` needs
# 242,464 B, so it is a 512 KB refusal on both systems. Nothing that was
# passing stopped.
EXPECT = {"floor-1M": 71, "sys3-512K": 67, "sys6-512K": 64}


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
    ap.add_argument("--check", action="store_true",
                    help="sweep the asserted tiers and fail on a change")
    a = ap.parse_args()
    if not a.tier and not a.budget and not a.check:
        ap.error("give --tier, --budget or --check")
    if not os.path.exists(a.macextract):
        raise SystemExit("run_tiers: no %s — build it first" % a.macextract)

    fixtures = names(a.list)
    if a.check:
        bad = 0
        for tier, want in sorted(EXPECT.items()):
            fails = sweep(a.macextract, fixtures, TIERS[tier][0], a.fixtures)
            if fails is None:
                return 1
            got = len(fixtures) - len(fails)
            print("run_tiers: %-11s %d/%d pass at %d bytes%s"
                  % (tier, got, len(fixtures), TIERS[tier][0],
                     "" if got == want else "   EXPECTED %d" % want))
            for n, short in sorted(fails, key=lambda x: x[1]):
                print("     %-42s short by at least %s"
                      % (n, "{:,}".format(short) if short >= 0
                         else "(other failure)"))
            bad += got != want
        return 1 if bad else 0

    budget = a.budget or TIERS[a.tier][0]
    what = a.tier and TIERS[a.tier][1] or "an explicit budget"
    fails = sweep(a.macextract, fixtures, budget, a.fixtures)
    if fails is None:
        return 1
    print("run_tiers: %d of %d pass at %d bytes — %s"
          % (len(fixtures) - len(fails), len(fixtures), budget, what))
    for n, short in sorted(fails, key=lambda x: x[1]):
        print("   %-44s short by at least %s"
              % (n, "{:,}".format(short) if short >= 0 else "(other failure)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

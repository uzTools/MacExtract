#!/usr/bin/env python3
"""run_tiers.py — predict a Macintosh tier's memory refusals on Linux.

Every "N/69" in FORMATS.md's small-machine tables costs an emulator run:
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
    tools/run_tiers.py --budget 102328 --list tools/vmac/sample.txt
    tools/run_tiers.py --tier floor-1M --macextract build/rel/macextract

It prints one line per refusal with the shortfall, and the tally. On
2026-09-01 it reproduced the System 3.0 / 512 KB tier exactly — 66/69,
the same three fixtures the emulator refuses — and put System 6.0.8 /
512 KB at 59/69 against the emulator's 58/69.

What it CANNOT see, and why the emulator stays
----------------------------------------------
- **Fragmentation.** The budget is one number; the Memory Manager also
  has to find ONE piece that big. The Mac shell reports that case
  separately (`gShortPiece`, "Memory is too broken up"), and nothing
  here models it. That is the likeliest reason for the one-fixture
  disagreement above.
- **The budget itself.** It is `FreeMem() - 20,480` measured on the
  machine (FORMATS.md, *Budget*), so it moves when the application's
  own size does. A figure here is only as current as that measurement.
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
    "sys3-512K": (197728, "System 3.0, Macintosh 512Ke (218,208 B free)"),
    "sys6-512K": (102328, "System 6.0.8, Macintosh 512Ke (122,808 B free)"),
    "floor-1M":  (648100, "System 6.0.8, 1 MB Mac Plus — the floor target"),
}

SHORT = re.compile(r"at least (\d+) bytes more memory")

# What --check asserts. Only the two tiers an emulator has independently
# agreed with are here: `sys3-512K` matches the Mini vMac run fixture for
# fixture (66/69, the same three), and `floor-1M` is the floor target's
# 69/69. `sys6-512K` is a diagnostic and NOT asserted — this file puts it
# at 59/69 where the machine said 58, and one fixture of disagreement was
# exactly the fragmentation this cannot model. The machine says 63/69 since
# 2026-09-04, so the gap is four; the budget above is probably pre-stack-cut
# and wants one -D UNC_AT_BUDGET boot to re-take (TESTING.md, *The tiers a
# budget predicts*). Still a diagnostic, still not asserted. A tally that moves here is
# either a memory regression or a memory WIN; both want the number below
# changed deliberately, which is the point of pinning it.
EXPECT = {"floor-1M": 69, "sys3-512K": 66}


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

#!/usr/bin/env python3
"""tzrun.py — dates in the Macintosh's own zone, read off an emulated disk.

    tools/vmac/tzrun.py [--tier NAME ...] [FIXTURE]
    tools/vmac/tzrun.py --tier sys7-tz fixtures/derived-MUSFMT10.ZIP
    tools/vmac/tzrun.py --check TIER RUNDIR      # grade disks a run kept

Runs one archive (default `fixtures/synth-exo-tar.tar`, whose two members
carry Unix mtimes) through the autotest application on each tier, keeps
the output disk, and reads every entry's catalog dates back
(tools/vmac/hfscat.py). Each is held to what `macextract l --meta` states
for it: a date the engine marks as an instant (`Z`, UNC_META_*_UTC) must
be on the disk moved by the tier's zone, and every other date unmoved
(mac/macextract_mac.c, ZoneShift; DECISIONS.md 2026-10-17, *dates in the
Macintosh's own zone*).

The tiers, and the shift each must show:

  sys7-tz   System 7.0.1, mv-4M-tz: extended parameter RAM says 5 h west
            (tools/vmac/setup.sh) — -18,000 s
  sys7      System 7.0.1, mv-4M: the location never set — 0
  sys6-tz   System 6.0.8, mv-4M-tz — -18,000 s: it has Gestalt and a
            Script Manager that answers, measured 2026-10-17
  sys30-tz  System 3.0, mv-4M-tz: no Gestalt trap, so the zone cannot be
            asked — 0

The tar's dates are all instants; a zip's MS-DOS dates are all wall
clocks, and on `sys7-tz` none of them may move — the second command.
A tier whose zone shift is wrong fails, and so does one where any
unmarked date moved. The control is in the table: the same application
and archive show both shifts, so a run that applied none anywhere, or
applied one everywhere, fails a tier.

**What it cannot see.** A real Map control panel writing the record: the
zone is put into PRAM by the emulator build (setup.sh says why), so what
Map writes, and whether its daylight-saving box changes gmtDelta, is not
measured here. Mac OS 9. A 512 KB machine.
"""
import argparse
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import hfscat                                                   # noqa: E402

TIERS = {
    "sys7-tz": (["run.py", "--system", "Sys7.img", "--emu", "mv-4M-tz",
                 "--expect"], -18000),
    "sys7": (["run.py", "--system", "Sys7.img", "--emu", "mv-4M",
              "--expect"], 0),
    "sys6-tz": (["run.py", "--system", "System6.hfv", "--emu", "mv-4M-tz",
                 "--expect"], -18000),
    "sys30-tz": (["sys30.py", "--emu", "mv-4M-tz"], 0),
}


def stated(cli, fixture):
    """{leaf name: [(field, value, marked)]} from `l --meta`'s t rows."""
    r = subprocess.run([cli, "l", "--meta", fixture], capture_output=True)
    out = {}
    for line in r.stdout.decode("utf-8", "surrogateescape").split("\n"):
        if not line.startswith("t "):
            continue
        f = line.split(" ", 3)
        leaf = f[3].rstrip("/").split("/")[-1]
        out[leaf] = [(k, int(v.rstrip("Z"), 16), v.endswith("Z"))
                     for k, v in (("crdat", f[1]), ("mddat", f[2]))
                     if v != "-"]
    return out


def grade(tier, rundir, want, shift):
    disks = glob.glob(os.path.join(rundir, "fixture-*", "out.dsk"))
    if len(disks) != 1:
        return ["%s: %d output disks in %s" % (tier, len(disks), rundir)], 0
    recs = hfscat.records(open(disks[0], "rb").read())
    got = {r["path"][-1].decode("mac-roman"): hfscat.fields(r) for r in recs}
    bad, n = [], 0
    for leaf, ds in want.items():
        g = got.get(leaf)
        if g is None:
            bad.append("%s: %s not on the disk" % (tier, leaf))
            continue
        for k, v, z in ds:
            n += 1
            w = (v + (shift if z else 0)) & 0xFFFFFFFF
            if g[k] != w:
                bad.append("%s: %s %s %08x, wanted %08x (%s, %+d)"
                           % (tier, leaf, k, g[k], w,
                              "marked" if z else "wall clock",
                              shift if z else 0))
    return bad, n


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixture", nargs="?",
                    default=os.path.join(REPO, "fixtures",
                                         "synth-exo-tar.tar"))
    ap.add_argument("--tier", action="append", choices=sorted(TIERS))
    ap.add_argument("--check", nargs=2, metavar=("TIER", "RUNDIR"))
    ap.add_argument("--cli", default=os.path.join(REPO, "build", "rel",
                                                  "macextract"))
    a = ap.parse_args()
    want = stated(a.cli, a.fixture)
    if not any(want.values()):
        raise SystemExit("tzrun: %s states no date" % a.fixture)
    fails = 0
    runs = ([tuple(a.check)] if a.check else
            [(t, None) for t in (a.tier or sorted(TIERS))])
    for tier, rundir in runs:
        drv, shift = TIERS[tier]
        if rundir is None:
            cmd = [sys.executable, os.path.join(HERE, drv[0])] + drv[1:] + [
                "--keep-disks", a.fixture]
            r = subprocess.run(cmd, capture_output=True, text=True)
            kept = [l.split("disks kept in ")[1].strip()
                    for l in r.stdout.splitlines() if "disks kept in " in l]
            if not kept:
                sys.stdout.write(r.stdout[-2000:])
                print("tzrun: %s kept no disks" % tier)
                fails += 1
                continue
            rundir = os.path.dirname(kept[0])
        bad, n = grade(tier, rundir, want, shift)
        for b in bad:
            print("tzrun: FAIL %s" % b)
        print("tzrun: %s: %d date(s) read back, %s (%s)"
              % (tier, n, "all as wanted" if not bad else
                 "%d WRONG" % len(bad), rundir))
        fails += bool(bad) or not n
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

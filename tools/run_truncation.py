#!/usr/bin/env python3
"""run_truncation.py — is a cut archive NOTICED?

    tools/run_truncation.py [--bin build/macextract] [--per-format 2]

`run_robustness.py` already truncates every fixture — and requires only
that the program terminates quickly with a normal exit code, which
**exit 0 satisfies**. So a format that walks a truncated archive, hands
over the entries before the cut and reports success passes it, 9,320
variants clean, while the user is told a run is complete that is missing
half its files. DiskDoubler did exactly that from M13 until 2026-08-29
(BLOCKERS.md), and nothing here could have said so.

This asks the other question: when the ORACLE calls a cut archive
broken, do we? `lsar` is the adjudicator, as everywhere else in this
project — a disagreement is a fixture where `unar` reports a parse
failure and `macextract t` exits 0.

**What this cannot see.** Three things, and they are why it is a
disagreement check rather than a "truncation must be an error" rule:

  - a format that CANNOT notice. A tar has no directory and no end
    marker, so a cut tar is indistinguishable from a short one; `unar`
    accepts those too, and so do we. The check passes, correctly, and
    says nothing about tar.
  - a format `unar` does not read at all (Alysis SuperDisk!, Now
    Compress, StuffIt SpaceSaver): it fails on the whole archive too,
    so its failure is not evidence about the cut one. Those rows can
    only ever agree by accident of our own exit code.
  - WHERE the archive was cut. Three fractions are sampled per fixture;
    a hole that only opens at one particular offset will not be found
    by three.
"""
import argparse, collections, glob, json, os, subprocess, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FIX = os.path.join(ROOT, "fixtures")
FRACTIONS = (0.25, 0.5, 0.75)
SIZE_CAP = 3 << 20          # a cut of a 3 MB archive says nothing more


def fixtures_by_format(per_format):
    """The most-entried fixtures of each format.

    NOT the first two alphabetically, which is what this did for an
    hour: for DiskDoubler that picked two SINGLE-FILE `.dd` fixtures,
    which have no walk to cut, and the check passed against a build with
    the defect deliberately put back. A truncation says something about
    a format's walk, so the fixtures with the most entries are the ones
    to cut."""
    cand = collections.defaultdict(list)
    for m in sorted(glob.glob(os.path.join(FIX, "manifests", "*.json"))):
        name = os.path.basename(m)[:-5]
        path = os.path.join(FIX, name)
        if not os.path.exists(path) or os.path.getsize(path) > SIZE_CAP:
            continue
        try:
            man = json.load(open(m))
        except Exception:
            continue
        cand[man.get("format") or "?"].append(
            (len(man.get("entries") or ()), name))
    byfmt = collections.defaultdict(list)
    for fmt, rows in cand.items():
        rows.sort(key=lambda r: (-r[0], r[1]))
        byfmt[fmt] = [n for _, n in rows[:per_format]]
    return byfmt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=os.path.join(ROOT, "build", "macextract"))
    ap.add_argument("--per-format", type=int, default=2)
    args = ap.parse_args()

    if subprocess.run(["which", "lsar"], capture_output=True).returncode != 0:
        print("truncation: no lsar — skipped (it is the adjudicator)")
        return 0
    if not os.path.exists(args.bin):
        print("truncation: no %s — skipped" % args.bin)
        return 0

    byfmt = fixtures_by_format(args.per_format)
    cut = os.path.join(ROOT, "build", ".truncation-variant")
    checked = 0
    silent = []
    for fmt, names in sorted(byfmt.items()):
        for n in names:
            blob = open(os.path.join(FIX, n), "rb").read()
            for frac in FRACTIONS:
                if int(len(blob) * frac) < 8:
                    continue
                with open(cut, "wb") as f:
                    f.write(blob[:int(len(blob) * frac)])
                ours = subprocess.run([args.bin, "t", cut], capture_output=True)
                try:
                    theirs = subprocess.run(["lsar", cut], capture_output=True,
                                            timeout=120)
                except subprocess.TimeoutExpired:
                    continue                       # the oracle says nothing
                checked += 1
                if ours.returncode == 0 and theirs.returncode != 0:
                    silent.append((fmt, n, frac))
    if os.path.exists(cut):
        os.remove(cut)

    for fmt, n, frac in silent:
        print("TRUNCATION FAIL %s: %s cut to %d%% is called complete, and "
              "unar calls it broken" % (fmt, n, int(frac * 100)))
    print("truncation: %d cut archive(s) checked across %d format(s), "
          "%d silent" % (checked, len(byfmt), len(silent)))
    return 1 if silent else 0


if __name__ == "__main__":
    sys.exit(main())

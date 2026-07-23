#!/usr/bin/env python3
"""run_budget.py — simulate a small Mac: run the whole corpus through
`unclassic t --budget N` (default 400 KB) and report, per format, which
fixtures cannot be fully verified under the cap and why.

Per-entry failures under budget pressure are expected and acceptable
(UNC_ERR_MEM per entry, "block too large for memory budget"); crashes
or hangs are not.
"""
import argparse, json, os, re, subprocess, sys
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIXDIR = os.path.join(ROOT, "fixtures")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unclassic",
                    default=os.path.join(ROOT, "build/rel/unclassic"))
    ap.add_argument("--budget", type=int, default=400 * 1024)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    mandir = os.path.join(FIXDIR, "manifests")
    stats = defaultdict(lambda: [0, 0, 0])   # fmt -> [ok, partial, hw-max]
    failures = []
    for mf in sorted(os.listdir(mandir)):
        if not mf.endswith(".json"):
            continue
        with open(os.path.join(mandir, mf)) as f:
            man = json.load(f)
        fx = os.path.join(FIXDIR, man["fixture"])
        if not os.path.exists(fx):
            continue
        fmt = man.get("format") or "?"
        r = subprocess.run(
            [args.unclassic, "t", "--stats", "--budget", str(args.budget), fx],
            capture_output=True, timeout=300)
        errtext = r.stderr.decode("utf-8", "replace")
        hw = re.search(r"high-water (\d+)", errtext)
        if hw:
            stats[fmt][2] = max(stats[fmt][2], int(hw.group(1)))
        if r.returncode == 0:
            stats[fmt][0] += 1
        else:
            stats[fmt][1] += 1
            reason = "?"
            m = re.search(r": ([a-z][^\n]*)\n", errtext)
            if m:
                reason = m.group(1)
            failures.append((fmt, man["fixture"], reason))
            if args.verbose:
                print(f"  budget-limited: {man['fixture']} ({fmt}): {reason}")

    print(f"budget {args.budget} bytes:")
    print(f"{'format':<15} {'full':>5} {'limited':>8} {'peak-mem':>9}")
    for fmt in sorted(stats):
        ok, part, hw = stats[fmt]
        print(f"{fmt:<15} {ok:>5} {part:>8} {hw:>9}")
    if failures:
        reasons = defaultdict(int)
        for fmt, fx, reason in failures:
            reasons[(fmt, reason.split(":")[-1].strip())] += 1
        print("\nlimited fixtures by reason:")
        for (fmt, reason), n in sorted(reasons.items()):
            print(f"  {n:>4}  {fmt}: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""run_ticks.py — does every format let its caller breathe?

`UncProgress.tick` is the engine's only cooperative yield: on classic Mac
OS it is where the application pumps events, so a decoder that does not
call it freezes the progress dialog and disables both Cancel routes for
the whole extraction. include/macextract.h bounds the interval; nothing
enforced it until 2026-08-28, when Now Compress turned out never to have
called it at all — found on an emulated Mac, three Cmd-. into a 9.9 MB
entry that ignored all of them (DECISIONS.md 2026-08-28).

Two rules, applied to every fixture in the corpus:

  1. an archive the engine EXTRACTS (ret == UNC_OK) that is larger than
     MIN_SIZE must tick at least once. Below that a tick may never come
     due, because the pump fires per 8 KB consumed;
  2. no gap between consecutive ticks may exceed MAX_GAP.

MAX_GAP is 32 KB rather than the shared reader's 8 KB because a
block-structured format reads a whole compressed block before it can
decode anything, and Now Compress's is NOW_INBLOCK = 32 KB. That is the
largest interval any format here has, and it is a measurement rather
than a margin: everything else in the corpus comes in at 8,192 B.

    tools/run_ticks.py --probe build/san/tick_probe
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

MIN_SIZE = 64 * 1024
MAX_GAP = 32 * 1024


def measure(probe, paths):
    """Run the probe over `paths`; yield (path, ret, ticks, max_gap, size).

    In batches, because the probe takes many files per run and a fixture
    corpus is a thousand of them."""
    out = []
    for i in range(0, len(paths), 64):
        batch = paths[i:i + 64]
        r = subprocess.run([probe] + batch, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"run_ticks: probe failed on {batch[0]}...: "
                             f"{r.stderr.strip()}")
        for line in r.stdout.splitlines():
            # The path may contain spaces; the four fields never do.
            parts = line.rsplit(" ", 4)
            if len(parts) != 5:
                raise SystemExit("run_ticks: unparsable probe line: " + line)
            path = parts[0]
            vals = {}
            for kv in parts[1:]:
                k, _, v = kv.partition("=")
                vals[k] = int(v)
            out.append((path, vals["ret"], vals["ticks"],
                        vals["max_gap"], vals["size"]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", default=os.path.join(REPO, "build", "tick_probe"))
    ap.add_argument("--fixtures", default=os.path.join(REPO, "fixtures"))
    args = ap.parse_args()

    if not os.path.exists(args.probe):
        print(f"run_ticks: no probe at {args.probe} — skipping")
        return 0
    if not os.path.isdir(args.fixtures):
        print("run_ticks: no fixtures — skipping")
        return 0

    paths = sorted(os.path.join(args.fixtures, n)
                   for n in os.listdir(args.fixtures)
                   if not n.endswith(".md") and
                   os.path.isfile(os.path.join(args.fixtures, n)))
    if not paths:
        print("run_ticks: no fixtures — skipping")
        return 0

    rows = measure(args.probe, paths)
    silent = [r for r in rows if r[1] == 0 and r[4] > MIN_SIZE and r[2] == 0]
    wide = [r for r in rows if r[3] > MAX_GAP]
    worst = max((r[3] for r in rows), default=0)

    for path, ret, ticks, gap, size in silent:
        print(f"run_ticks: FAIL {os.path.basename(path)}: {size} B extracted "
              f"with NO progress callback at all — a Mac would sit on a frozen "
              f"dialog for the whole of it, with Cancel out of reach")
    for path, ret, ticks, gap, size in wide:
        print(f"run_ticks: FAIL {os.path.basename(path)}: {gap} B between "
              f"progress callbacks, over the {MAX_GAP} B bound")
    print(f"run_ticks: {len(rows)} fixtures, "
          f"{sum(1 for r in rows if r[2])} of them ticking, "
          f"widest gap {worst} B (bound {MAX_GAP} B)")
    return 1 if silent or wide else 0


if __name__ == "__main__":
    sys.exit(main())

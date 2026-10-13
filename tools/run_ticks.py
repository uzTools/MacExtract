#!/usr/bin/env python3
"""run_ticks.py — does every format let its caller breathe?

`UncProgress.tick` is the engine's only cooperative yield: on classic Mac
OS it is where the application pumps events, so a decoder that does not
call it freezes the progress dialog and disables both Cancel routes for
the whole extraction. include/macextract.h bounds the interval; nothing
enforced it until 2026-08-28, when Now Compress turned out never to have
called it at all — found on an emulated Mac, three Cmd-. into a 9.9 MB
entry that ignored all of them (DECISIONS.md 2026-08-28).

Envelopes are peeled on the way in (`tools/envelopes.py`), because 419
of the 932 fixtures are a wrapper around the archive that matters:
until 2026-08-28 this suite asked BinHex whether it ticks, over and
over, and never reached the StuffIt walk inside. That is the same blind
spot the rule below is about — a check that cannot fail on a property it
never looks at.

Two rules, applied to every archive the corpus holds, at every layer:

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
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

sys.path.insert(0, HERE)
from envelopes import layers                            # noqa: E402
from concurrent import futures                           # noqa: E402

MIN_SIZE = 64 * 1024
MAX_GAP = 32 * 1024

# Progress that runs past the archive's size: (name, size) -> how far past,
# in bytes. A RATCHET, not a tolerance: a layer not listed fails at any
# overrun, a listed one fails if it grows, and one that shrinks or clears
# is reported so the entry can come down. EMPTY since 2026-10-09: the 66
# layers it held when this lane first looked — DiskDoubler re-reading its
# own buffer, MacLHA's peek and uuencode's scan counting input the decode
# read again — were each fixed in the format (DECISIONS.md 2026-10-09,
# *the bar that counted the peek*, and *DiskDoubler read every block six
# times*).
KNOWN_OVERRUN = {}


def measure(probe, paths):
    """Run the probe over `paths`; yield
    (path, ret, ticks, max_gap, size, overrun).

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
            # The path may contain spaces; the six fields never do.
            parts = line.rsplit(" ", 6)
            if len(parts) != 7:
                raise SystemExit("run_ticks: unparsable probe line: " + line)
            path = parts[0]
            vals = {}
            for kv in parts[1:]:
                k, _, v = kv.partition("=")
                vals[k] = int(v)
            out.append((path, vals["ret"], vals["ticks"],
                        vals["max_gap"], vals["size"], vals["overrun"]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", default=os.path.join(REPO, "build", "tick_probe"))
    ap.add_argument("--macextract",
                    default=os.path.join(REPO, "build", "macextract"))
    ap.add_argument("--fixtures", default=os.path.join(REPO, "fixtures"))
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1,
                    help="fixtures measured at once (default: one per CPU). "
                         "Output does not depend on it.")
    args = ap.parse_args()

    # The CLI is tested FIRST and is an error, not a skip: without it this
    # suite measures nothing, and returning 0 would report success for a
    # run that never happened. The probe and the fixtures below are real
    # optional dependencies and do still skip.
    if not os.path.exists(args.macextract):
        print(f"run_ticks: no CLI at {args.macextract}")
        return 1
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

    # `--jobs` fixtures at a time, and the peeled files are removed as soon
    # as they have been measured: peeling the whole corpus first would put a
    # second copy of it on disk, where this keeps one per job. Each job owns
    # its own working directory, and the rows are collected in the order the
    # fixtures were submitted, so the grading below is unchanged.
    def peel_and_measure(item):
        i, p = item
        work = os.path.join(tmp, "w%d" % i)
        os.mkdir(work)
        try:
            chain = layers(args.macextract, p, work)
            return len(chain) - 1, measure(args.probe, chain)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    rows = []
    peeled = 0
    tmp = tempfile.mkdtemp()
    try:
        with futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
            for layers_peeled, got in ex.map(peel_and_measure,
                                             enumerate(paths)):
                peeled += layers_peeled
                rows += got
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    silent = [r for r in rows if r[1] == 0 and r[4] > MIN_SIZE and r[2] == 0]
    wide = [r for r in rows if r[3] > MAX_GAP]
    # Progress past the total: input a dry pass read counted again by the
    # decode proper. The bar reads 100 % with work left.
    over = [r for r in rows
            if r[5] > KNOWN_OVERRUN.get((os.path.basename(r[0]), r[4]), 0)]
    seen = {}
    for r in rows:
        k = (os.path.basename(r[0]), r[4])
        seen[k] = max(seen.get(k, 0), r[5])
    for k, was in sorted(KNOWN_OVERRUN.items()):
        if k in seen and seen[k] < was:
            print(f"run_ticks: {k[0]}: progress overrun {was} -> {seen[k]} B; "
                  f"lower KNOWN_OVERRUN")
    worst = max((r[3] for r in rows), default=0)

    for path, ret, ticks, gap, size, _o in silent:
        print(f"run_ticks: FAIL {os.path.basename(path)}: {size} B extracted "
              f"with NO progress callback at all — a Mac would sit on a frozen "
              f"dialog for the whole of it, with Cancel out of reach")
    for path, ret, ticks, gap, size, _o in wide:
        print(f"run_ticks: FAIL {os.path.basename(path)}: {gap} B between "
              f"progress callbacks, over the {MAX_GAP} B bound")
    for path, ret, ticks, gap, size, o in over:
        print(f"run_ticks: FAIL {os.path.basename(path)}: progress ran "
              f"{o} B past the archive's {size} B — the bar reads 100 % "
              f"with work left")
    print(f"run_ticks: {len(rows)} archives ({peeled} of them peeled out of "
          f"an envelope), {sum(1 for r in rows if r[2])} of them ticking, "
          f"widest gap {worst} B (bound {MAX_GAP} B)")
    return 1 if silent or wide or over else 0


if __name__ == "__main__":
    sys.exit(main())

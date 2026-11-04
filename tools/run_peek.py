#!/usr/bin/env python3
"""run_peek.py — unc_envelope_peek against the whole unwrap, over the corpus.

The Macintosh shell keeps an envelope's reader and what the format under it
needs, and gives the rest of the overlay bundle back, when the first bytes of
the envelope's payload name that format (`src/unc_peek.c`; DECISIONS.md
2026-11-03, *the envelope that said what it held*). A release cannot be
undone mid-run, so a WRONG name would leave the layer under it without its
reader: the layer fails for memory where it worked before.

So for every fixture that sniffs as an envelope this unwraps the layer whole
(`macextract x -nr`), sniffs what came out, and asks the peek through
`tools/encinfo_probe.c --peek`:

  * a peek that names a format other than the whole payload's FAILS;
  * a peek that names nothing is counted, not failed: that envelope keeps the
    whole bundle, as every envelope did before;
  * the peek's own peak allocation is reported, since the shell runs it
    before the release, while the whole bundle is still in memory.

It also fails if fewer envelopes are named than the floor below, so a peek
that quietly stopped naming anything — which no disagreement would show —
does not pass.

WHAT IT CANNOT SEE: a payload the corpus does not hold; whether the peek's
allocations FIT on a Macintosh (`run_tiers.py` charges the peak against the
heap the bundle leaves; fragmentation is the emulator's to find); and the
shell's use of the answer (`mac/ovl_load_eager.c`), which only the emulator
tiers run.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import run_tiers  # noqa: E402

# Measured 2026-11-04: 301 of 466 envelope fixtures named, 0 wrong; a 256 B
# window names 4, which this floor fails.
NAMED_FLOOR = 290


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract",
                    default=os.path.join(REPO, "build", "rel", "macextract"))
    args = ap.parse_args()

    envelopes = {n for n, env in run_tiers.formats().values() if env}
    tmp = tempfile.mkdtemp(prefix="run_peek-", dir=os.path.join(REPO, ".tmp"))
    try:
        ask = run_tiers.encinfo_probe(tmp)

        def sniff(path):
            r = subprocess.run([args.macextract, "sniff", path],
                               capture_output=True, text=True)
            return r.stdout.strip().split(": ", 1)[-1] \
                if r.returncode == 0 else None

        problems, named, silent, peak, peakof = [], 0, 0, 0, ""
        for path in sorted(glob.glob(os.path.join(REPO, "fixtures", "*"))):
            if not os.path.isfile(path) or path.endswith((".md", ".json")):
                continue
            if sniff(path) not in envelopes:
                continue
            name, _enc, pk = ask(path, peek=True)
            if pk > peak:
                peak, peakof = pk, os.path.basename(path)
            if name is None:
                silent += 1
                continue
            out = os.path.join(tmp, "x")
            shutil.rmtree(out, ignore_errors=True)
            os.mkdir(out)
            subprocess.run([args.macextract, "x", "-nr", "--forks", "hidden",
                            "-o", out, path], capture_output=True)
            files = [os.path.join(r, f) for r, _, fs in os.walk(out)
                     for f in fs if not f.startswith("._")]
            whole = sniff(files[0]) if len(files) == 1 else None
            if whole != name:
                problems.append("%s: the peek says %s, the whole payload %s"
                                % (os.path.basename(path), name, whole))
            else:
                named += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if named < NAMED_FLOOR:
        problems.append("only %d envelopes named, fewer than %d"
                        % (named, NAMED_FLOOR))
    print("run_peek: %d envelopes named, %d not, peak %d B (%s)"
          % (named, silent, peak, peakof))
    for p in problems:
        print("run_peek: FAIL " + p)
    print("run_peek: %d problem(s)" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

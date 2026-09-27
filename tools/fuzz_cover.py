#!/usr/bin/env python3
"""fuzz_cover.py — which DECODERS does the fuzzer actually enter?

`tools/fuzz_reach.py` answers this for the eight ciphers, one planted
fault at a time.  Nothing answered it for the decoders, and the answer
turned out to matter: the one heap overflow this project has found in a
decoder — `now_next_block`, checking a length against `incap` where the
buffer is `blkcap` — was found by a hand-crafted archive under ASan and
NOT by the fuzzer, and the reason is visible here.

The instrument is coverage rather than planted faults, because for a
decoder "was this function entered" is exactly what gcov reports and
one build answers it for every decoder at once:

    tools/fuzz_cover.py [-n 3000] [--seed 11] [--keep]

It builds `build/cov` with `--coverage`, runs `tools/fuzz.py` against
it, and prints per-family how many functions were never entered.

WHAT IT CANNOT SEE, and both matter:

  * **Entered is not exercised.** A decoder whose first line ran counts
    as reached here even if every interesting branch inside it did not.
    This is a floor on coverage, not a measure of it.
  * **It says nothing about correctness.** gcov counts execution; a
    decoder that runs and produces the wrong bytes is invisible to it.
    That is `run_diff.sh`'s job, against the oracle.
  * It is a measurement of ONE seed and ONE case count. A family at
    zero may be sampling rather than structure — re-run larger before
    concluding, which is how the 400-case and 3,000-case runs of
    2026-09-27 were told apart.

Not in `ci.sh`: it rebuilds the engine and runs thousands of cases.
What `ci.sh` carries is the RESULT, in TESTING.md.
"""

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build", "cov")

# The decoder families, by the prefix their functions carry.
FAMILIES = [
    ("StuffIt classic",   r"^sit\d*_"),
    ("StuffIt 5",         r"^sit5_"),
    ("Arsenic",           r"^ars_|^arsenic"),
    ("Compact Pro",       r"^cpt_"),
    ("DiskDoubler",       r"^dd_"),
    ("Now Compress",      r"^now_"),
    ("LZH -lh1-/method 5", r"^lzah_"),
    ("LZH -lh2-/-lh3-",   r"^lz[ds]_"),
    ("LZH container",     r"^lzh_"),
    ("ARC",               r"^arc_"),
    ("PackIt",            r"^pit_"),
    ("BinHex",            r"^hqx_|^binhex_"),
]


def run(*a, **kw):
    return subprocess.run(a, cwd=ROOT, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--keep", action="store_true",
                    help="reuse an existing build/cov and its counters")
    a = ap.parse_args()

    if not a.keep:
        run("make", "clean", stdout=subprocess.DEVNULL)
        r = run("make", "BUILD=build/cov", "CFLAGS=-O0 -g --coverage",
                "LDFLAGS=--coverage", "all",
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if r.returncode:
            print(r.stderr.decode()[-2000:])
            return 1
        for f in os.listdir(BUILD):
            if f.endswith(".gcda"):
                os.remove(os.path.join(BUILD, f))
        r = run(sys.executable, "tools/fuzz.py", "-n", str(a.n),
                "--seed", str(a.seed),
                "--macextract", os.path.join("build", "cov", "macextract"),
                stdout=subprocess.PIPE)
        print(r.stdout.decode().strip().splitlines()[-1])

    # ENGINE functions only, decided per gcov invocation: the coverage
    # build carries tests/ too, and its helpers (pit_synth, cpt_synth,
    # ...) match the family patterns while being nothing the fuzzer
    # could ever enter. In `gcov -f` output the functions come BEFORE
    # the File line they belong to, so this filters per run rather than
    # by splitting the text — which silently mis-assigned them.
    fns = []
    for f in sorted(os.listdir(BUILD)):
        if not f.endswith(".gcno"):
            continue
        r = subprocess.run(["gcov", "-n", "-f", f[:-5]], cwd=BUILD,
                           capture_output=True, text=True)
        files = re.findall(r"File '([^']+)'", r.stdout)
        if not files or not all(x.startswith("src/") for x in files):
            continue
        fns += re.findall(r"Function '([^']+)'\nLines executed:([\d.]+)%",
                          r.stdout)

    if not fns:
        print("fuzz_cover: gcov reported nothing — was the build "
              "instrumented?")
        return 1
    zero = {n for n, p in fns if float(p) == 0.0}
    allf = {n for n, p in fns}

    print("fuzz_cover: %d cases, seed %d, %d functions, %d never entered"
          % (a.n, a.seed, len(allf), len(zero)))
    bad = 0
    for name, rx in FAMILIES:
        r = re.compile(rx)
        mem = sorted(n for n in allf if r.search(n))
        if not mem:
            continue
        dead = [n for n in mem if n in zero]
        flag = "  <-- never fuzzed" if len(dead) == len(mem) else ""
        print("  %-20s %3d function(s), %3d never entered%s"
              % (name, len(mem), len(dead), flag))
        if dead:
            print("       " + ", ".join(dead[:10])
                  + (" ..." if len(dead) > 10 else ""))
        if len(dead) == len(mem):
            bad += 1
    if bad:
        print("  %d whole family(ies) at zero — a method with no specimen in "
              "the corpus cannot be reached by mutating the corpus." % bad)
    return 0


if __name__ == "__main__":
    sys.exit(main())

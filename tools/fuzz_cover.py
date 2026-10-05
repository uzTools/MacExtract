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
    tools/fuzz_cover.py --keep-build --fuzz-arg=--no-stream   # the before
    tools/fuzz_cover.py --keep-build --detail "StuffIt method 14"

(`--fuzz-arg=X`, not `--fuzz-arg X`: argparse reads a leading `--` as
the next option and says only "expected one argument".)

It builds `build/cov` with `--coverage`, runs `tools/fuzz.py` against
it, and prints per-family how many functions were never entered.

WHAT IT CANNOT SEE, and both matter:

  * **Entered is not exercised.** A decoder whose first line ran counts
    as reached here even if every interesting branch inside it did not.
    This is a floor on coverage, not a measure of it.
  * **It says nothing about correctness.** gcov counts execution; a
    decoder that runs and produces the wrong bytes is invisible to it.
    That is `run_diff.sh`'s job, against the oracle.
  * It is a measurement of ONE seed and ONE case count, and **the
    per-family counts are noisy**: at 3,000 cases, seeds 11 and 12 over
    an identical build have differed by thirteen functions in a family —
    ARC 0 against 13, StuffIt classic 8 against 1 (measured 2026-10-05;
    the same comparison on 2026-09-27 gave five at most). **A single-run
    delta in a family is not a finding.** What the instrument says
    reliably is whether a family is WHOLLY at zero, and whether a change
    moves a family in and out of that state at more than one seed.
  * A family at zero in a small run may be sampling rather than
    structure — the 400-case and 3,000-case runs of 2026-09-27 were
    told apart that way.

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
#
# The prefixes are SPELLED OUT rather than globbed, because a row that
# quietly swallows a decoder cannot report on it: `^sit\d*_` put method
# 14's eleven functions inside "StuffIt classic" from the day they
# landed, and a family of 34 cannot read as wholly at zero — which is
# the one signal this tool calls reliable. Method 14's own state was
# therefore unreadable here, at the case count where it was entirely
# unfuzzed and at the one where it is not (TESTING.md, *Fuzzing*).
# Anything matching no row is counted as unclassified below, which is
# what makes a new prefix visible instead of invisible.
FAMILIES = [
    ("StuffIt classic",   r"^sit_|^sit13_|^sit5_|^sit6_"),
    ("StuffIt method 14", r"^sit14_|^unc_sit14_"),
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
    ("BinHex",            r"^bh_|^unc_binhex_"),
]


def run(*a, **kw):
    return subprocess.run(a, cwd=ROOT, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--keep", action="store_true",
                    help="reuse an existing build/cov and its counters")
    # Comparing two settings of fuzz.py means two runs over ONE build,
    # or the comparison carries a rebuild in it as well: --keep-build
    # resets the counters and runs again, and --fuzz-arg is what says
    # what to run (e.g. --fuzz-arg --no-stream for the before).
    ap.add_argument("--keep-build", action="store_true",
                    help="reuse build/cov, clear its counters, fuzz again")
    ap.add_argument("--fuzz-arg", action="append", default=[],
                    metavar="ARG", help="pass ARG through to tools/fuzz.py "
                                        "(repeatable)")
    # Never-entered is a floor, and a change that moves a family off
    # zero is invisible in it afterwards: every later gain is in LINES
    # of functions already counted as reached. --detail prints them.
    ap.add_argument("--detail", metavar="FAMILY",
                    help="also print every function of this family with "
                         "its line percentage (a family name above, or a "
                         "regex)")
    a = ap.parse_args()

    # `ci.sh` opens with `make clean`, i.e. `rm -rf build`, so a
    # --keep after one has nothing to read and used to say so with a
    # traceback from os.listdir.
    if (a.keep or a.keep_build) and not os.path.isdir(BUILD):
        print("fuzz_cover: no %s — drop --keep/--keep-build and let it "
              "build (ci.sh's own `make clean` removes it)" % BUILD)
        return 1

    if not a.keep:
        if not a.keep_build:
            # BUILD= on the clean, because `make clean` without it is
            # `rm -rf build` — which takes build/san (what ci.sh and
            # fuzz.py default to) and every oracle built under build/:
            # deark, lha, mpack, unar. This tool rebuilds one directory
            # and only that one needs emptying.
            run("make", "BUILD=" + BUILD, "clean",
                stdout=subprocess.DEVNULL)
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
                *a.fuzz_arg, stdout=subprocess.PIPE)
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
    classified = set()
    for name, rx in FAMILIES:
        r = re.compile(rx)
        mem = sorted(n for n in allf if r.search(n))
        classified |= set(mem)
        # A row matching nothing is the shape the BinHex row was in
        # until 2026-10-05: its regex named `hqx_`/`binhex_` and the
        # functions are `bh_`, so the family printed no line at all and
        # read as absent rather than as unmeasured.
        if not mem:
            print("  %-20s   0 function(s)  <-- this row matches nothing"
                  % name)
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
    if a.detail:
        rx = dict(FAMILIES).get(a.detail, a.detail)
        r = re.compile(rx)
        pct = {}
        for n, p in fns:                # one function, one highest reading
            pct[n] = max(pct.get(n, 0.0), float(p))
        mem = sorted(n for n in pct if r.search(n))
        print("  %s (%s): %d function(s)" % (a.detail, rx, len(mem)))
        for n in mem:
            print("       %-28s %5.1f %% of lines" % (n, pct[n]))

    rest = sorted(allf - classified)
    print("  %d engine function(s) in no family above%s"
          % (len(rest), (": " + ", ".join(rest[:8])
                         + (" ..." if len(rest) > 8 else "")) if rest else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

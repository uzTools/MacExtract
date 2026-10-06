#!/usr/bin/env python3
"""run_robustness.py — corrupted-input tests.

For every implemented-format fixture: generate truncated and bit-flipped
variants and require `macextract t` to terminate quickly with a normal
exit code. Death by signal (sanitizer abort, segfault) or timeout (hang)
is a failure. Deterministic: RNG seeded per fixture name.
"""
import argparse, hashlib, json, os, random, subprocess, sys, tempfile
from concurrent import futures

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIXDIR = os.path.join(ROOT, "fixtures")

from run_diff import IMPLEMENTED  # single source of truth


def variants(blob, seed):
    rng = random.Random(seed)
    out = []
    for frac in (0.25, 0.5, 0.75, 0.98):
        out.append(("trunc%d" % (frac * 100), blob[:int(len(blob) * frac)]))
    for i in range(6):
        b = bytearray(blob)
        for _ in range(rng.randint(1, 8)):
            pos = rng.randrange(len(b))
            b[pos] ^= 1 << rng.randrange(8)
        out.append(("flip%d" % i, bytes(b)))
    return out


def check_fixture(macextract, fixture, timeout):
    """Every variant of ONE fixture, as (tested, [failure messages]).

    A worker owns a fixture rather than a variant: the ten variants are
    made FROM the archive's bytes, so per-fixture work holds one copy of
    the corpus's largest archive per job instead of ten.
    """
    with open(os.path.join(FIXDIR, fixture), "rb") as f:
        blob = f.read()
    if not blob:
        return 0, []
    tested, msgs = 0, []
    for tag, var in variants(blob, fixture):
        tested += 1
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
            tf.write(var)
            vpath = tf.name
        try:
            r = subprocess.run([macextract, "t", vpath],
                               capture_output=True, timeout=timeout)
            if r.returncode < 0 or r.returncode > 2:
                out = [f"ROBUSTNESS FAIL {fixture}[{tag}]: exit {r.returncode}"]
                err = r.stderr.decode("utf-8", "replace")
                out += [f"    {line}" for line in err.splitlines()[:6]]
                msgs.append("\n".join(out))
        except subprocess.TimeoutExpired:
            msgs.append(f"ROBUSTNESS FAIL {fixture}[{tag}]: HANG")
        finally:
            os.unlink(vpath)
    return tested, msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default=os.path.join(ROOT, "build/san/macextract"))
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1,
                    help="fixtures checked at once (default: one per CPU). "
                         "Output does not depend on it.")
    args = ap.parse_args()

    if not os.path.exists(args.macextract):
        print("robustness: no CLI at %s" % args.macextract)
        return 1

    mandir = os.path.join(FIXDIR, "manifests")
    manifests = sorted(f for f in os.listdir(mandir)
                       if f.endswith(".json")) if os.path.isdir(mandir) else []

    work = []
    for mf in manifests:
        with open(os.path.join(mandir, mf)) as f:
            man = json.load(f)
        fx = os.path.join(FIXDIR, man["fixture"])
        if man.get("format") not in IMPLEMENTED or not os.path.exists(fx):
            continue
        work.append(man["fixture"])

    # One process per variant, 9,510 of them under ASan, was the single
    # largest line in a ci.sh run. The cases, their seeds and the ORDER
    # they are reported in are unchanged -- map() yields in submission
    # order, so a failing variant prints where it always did
    # (DECISIONS.md 2026-10-06, *the twenty-four minutes*).
    tested = bad = 0
    with futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for n, msgs in ex.map(
                lambda fixture: check_fixture(args.macextract, fixture,
                                              args.timeout), work):
            tested += n
            bad += len(msgs)
            for m in msgs:
                print(m)
    print(f"robustness: {tested - bad}/{tested} variants clean")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""run_robustness.py — corrupted-input tests.

For every implemented-format fixture: generate truncated and bit-flipped
variants and require `macextract t` to terminate quickly with a normal
exit code. Death by signal (sanitizer abort, segfault) or timeout (hang)
is a failure. Deterministic: RNG seeded per fixture name.
"""
import argparse, hashlib, json, os, random, subprocess, sys, tempfile

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default=os.path.join(ROOT, "build/san/macextract"))
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()

    if not os.path.exists(args.macextract):
        print("robustness: no CLI at %s" % args.macextract)
        return 1

    mandir = os.path.join(FIXDIR, "manifests")
    manifests = sorted(f for f in os.listdir(mandir)
                       if f.endswith(".json")) if os.path.isdir(mandir) else []

    tested = bad = 0
    for mf in manifests:
        with open(os.path.join(mandir, mf)) as f:
            man = json.load(f)
        fx = os.path.join(FIXDIR, man["fixture"])
        if man.get("format") not in IMPLEMENTED or not os.path.exists(fx):
            continue
        with open(fx, "rb") as f:
            blob = f.read()
        if not blob:
            continue
        for tag, var in variants(blob, man["fixture"]):
            tested += 1
            with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
                tf.write(var)
                vpath = tf.name
            try:
                r = subprocess.run([args.macextract, "t", vpath],
                                   capture_output=True, timeout=args.timeout)
                if r.returncode < 0 or r.returncode > 2:
                    bad += 1
                    print(f"ROBUSTNESS FAIL {man['fixture']}[{tag}]: "
                          f"exit {r.returncode}")
                    err = r.stderr.decode("utf-8", "replace")
                    for line in err.splitlines()[:6]:
                        print(f"    {line}")
            except subprocess.TimeoutExpired:
                bad += 1
                print(f"ROBUSTNESS FAIL {man['fixture']}[{tag}]: HANG")
            finally:
                os.unlink(vpath)
    print(f"robustness: {tested - bad}/{tested} variants clean")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""fuzz.py — randomized robustness pass across all formats.

Three generators, seeded and reproducible:
  1. mutation: take a random corpus fixture, apply 1..64 random byte
     mutations / truncations / duplications;
  2. splice: concatenate random slices of two fixtures;
  3. garbage: pure random bytes with a real format magic prefix.

Every case runs `unclassic t --budget 4M` (the sanitizer build) with a
timeout. Any nonzero-but-clean exit is fine; crashes (signals),
sanitizer aborts, or timeouts fail the run.
"""
import argparse, os, random, subprocess, sys, tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIXDIR = os.path.join(ROOT, "fixtures")

MAGICS = [
    b"SIT!\x00\x01\x00\x00\x00\x00rLau",
    b"StuffIt (c)1997-2026 Aladdin Systems, Inc., "
    b"http://www.aladdinsys.com/StuffIt/\x0d\x0a",
    b"SIT!DFD3\x00\x00\x00\x03\x00\x00\x00T",
    b"PMag", b"PMa4", b"\x01\x01\x00\x00", b"\x1f\x8b\x08", b"\x1f\x9d\x90",
    b"PK\x03\x04", b"(This file must be converted with BinHex 4.0)\r:",
]


def corpus():
    out = []
    for f in sorted(os.listdir(FIXDIR)):
        p = os.path.join(FIXDIR, f)
        if os.path.isfile(p) and f != "SOURCES.md" and \
           os.path.getsize(p) < 512 * 1024:
            out.append(p)
    return out


def mutate(data, rng):
    buf = bytearray(data)
    for _ in range(rng.randrange(1, 65)):
        kind = rng.randrange(4)
        if not buf:
            break
        if kind == 0:      # flip
            buf[rng.randrange(len(buf))] ^= 1 << rng.randrange(8)
        elif kind == 1:    # overwrite run
            at = rng.randrange(len(buf))
            n = min(rng.randrange(1, 128), len(buf) - at)
            buf[at:at + n] = bytes(rng.randrange(256) for _ in range(n))
        elif kind == 2:    # truncate
            buf = buf[:rng.randrange(1, len(buf) + 1)]
        else:              # duplicate a slice
            at = rng.randrange(len(buf))
            n = min(rng.randrange(1, 512), len(buf) - at)
            buf[at:at] = buf[at:at + n]
    return bytes(buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unclassic",
                    default=os.path.join(ROOT, "build/san/unclassic"))
    ap.add_argument("-n", "--iterations", type=int, default=500)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=20.0)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    seeds = corpus()
    if not seeds:
        print("fuzz: no corpus fixtures present", file=sys.stderr)
        return 1
    cache = {}
    bad = 0

    with tempfile.TemporaryDirectory() as tmp:
        for i in range(args.iterations):
            kind = rng.randrange(3)
            if kind == 0:
                src = rng.choice(seeds)
                data = cache.setdefault(src, open(src, "rb").read())
                blob = mutate(data, rng)
            elif kind == 1:
                s1 = rng.choice(seeds)
                s2 = rng.choice(seeds)
                d1 = cache.setdefault(s1, open(s1, "rb").read())
                d2 = cache.setdefault(s2, open(s2, "rb").read())
                c1 = rng.randrange(len(d1) + 1)
                c2 = rng.randrange(len(d2) + 1)
                blob = d1[:c1] + d2[c2:]
            else:
                blob = rng.choice(MAGICS) + \
                    bytes(rng.randrange(256) for _ in range(rng.randrange(4096)))

            path = os.path.join(tmp, "case")
            with open(path, "wb") as f:
                f.write(blob)
            try:
                r = subprocess.run(
                    [args.unclassic, "t", "--budget", str(4 << 20), path],
                    capture_output=True, timeout=args.timeout)
            except subprocess.TimeoutExpired:
                bad += 1
                keep = os.path.join(ROOT, f"fuzz-hang-{args.seed}-{i}.bin")
                os.replace(path, keep)
                print(f"FUZZ HANG at iteration {i}, kept {keep}")
                continue
            if r.returncode < 0 or r.returncode > 1 or \
               b"Sanitizer" in r.stderr or b"runtime error" in r.stderr:
                bad += 1
                keep = os.path.join(ROOT, f"fuzz-crash-{args.seed}-{i}.bin")
                os.replace(path, keep)
                print(f"FUZZ FAIL at iteration {i} "
                      f"(exit {r.returncode}), kept {keep}")
                print(r.stderr.decode("utf-8", "replace")[:400])

    print(f"fuzz: {args.iterations} cases, {bad} failures (seed {args.seed})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

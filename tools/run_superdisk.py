#!/usr/bin/env python3
"""run_superdisk.py — the Alysis SuperDisk! suite.

The corpus holds two SuperDisk! archives and nothing else can read
them: `unar` and `macunpack` both stop at the BinHex envelope, so the
oracle manifests in `fixtures/manifests/` describe the envelope's
payload and say nothing about what is inside it. The grading was done
once, on an emulated Mac, by the archives' own self-extractors
(`tools/vmac/superdisk.py --adjudicate`); this replays that verdict
offline by fork content.

    tools/run_superdisk.py --macextract build/macextract

Every hash below was produced by THIS reader and then confirmed
fork-for-fork against what the original extractor wrote on a System 7
volume — resource forks with bytes 16..127 masked, the
`tools/vmac_check.py` convention, because the Resource Manager stamps
that region whenever it touches a file. The unmasked hash is recorded
here because it is the one a regression can be checked against; the
masked comparison is what says it is right.

Re-confirm with:

    tools/vmac/superdisk.py --adjudicate fixtures/super-disk-utility.hqx
    tools/vmac/superdisk.py --adjudicate fixtures/alysis-disk-expander-12.hqx
"""
import argparse
import hashlib
import os
import random
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# fixture -> [(path the sink writes, size, sha256)]
EXPECTED = {
    "super-disk-utility.hqx": [
        ("Read Me and More/Application/SuperDisk! Utilities", 0,
         "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        ("Read Me and More/Application/SuperDisk! Utilities.rsrc", 14389,
         "5116b35fcb0b64b7378a8559d69eb24aef790328e03f0e982d5f1725ad44bc4d"),
        ("Read Me and More/PLEASE READ/SD! Utilities : MSWord4.0", 5120,
         "2382de0bac69dadc812b2229d8c4d4e842e36cf77cec4d79751dfcb7f6ba838c"),
        ("Read Me and More/PLEASE READ/SD! Utilities : MacWrite", 4796,
         "41040a3e6283f2aaba8645a61130f8c8a842ca100fe55288ce08062476037182"),
    ],
    "alysis-disk-expander-12.hqx": [
        ("Disk Expander /Disk Expander", 0,
         "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        ("Disk Expander /Disk Expander.rsrc", 66953,
         "b1a8eaebc19deac69e3d5fc1031eb890d95fb3d69ce73c59f273f05f6e3f24ce"),
        ("Disk Expander /Read Me", 1748,
         "c713f7c9520287f928edf44d984e0fbf8c576ae0009b0453702f37368dc7ba4c"),
    ],
}

# The payload inside each envelope, and what a sniff of it must say.
# Listing never recurses through an envelope — only `x` does — so the
# check has to be made on the payload itself, which is also the path a
# user takes with a file that arrived unwrapped.
PAYLOAD = {
    "super-disk-utility.hqx": "SD! Utilities.x",
    "alysis-disk-expander-12.hqx": "Disk Expander .X",
}
SNIFF = "SuperDisk!"


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def run_one(exe, fixture, entries, verbose):
    src = os.path.join(REPO, "fixtures", fixture)
    if not os.path.exists(src):
        print("superdisk: %s is not in the corpus, skipped" % fixture)
        return 0, 0
    work = tempfile.mkdtemp(prefix="sdtest-")
    out = os.path.join(work, "out")
    bad = 0
    try:
        env = os.path.join(work, "env")
        r = subprocess.run([exe, "x", "-nr", "-o", env, src],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("superdisk: %s: envelope failed rc=%d %s"
                  % (fixture, r.returncode, r.stderr.strip()))
            return len(entries), len(entries)
        payload = os.path.join(env, PAYLOAD[fixture])
        got_fmt = subprocess.run([exe, "sniff", payload], capture_output=True,
                                 text=True).stdout.strip()
        if got_fmt != SNIFF:
            print("superdisk: %s: sniffed as %r, expected %r"
                  % (fixture, got_fmt, SNIFF))
            bad += 1
        listing = subprocess.run([exe, "l", payload], capture_output=True,
                                 text=True)
        nfiles = len([ln for ln in listing.stdout.splitlines()
                      if ln.startswith("f ")])
        wantfiles = len([e for e in entries if not e[0].endswith(".rsrc")])
        if nfiles != wantfiles:
            print("superdisk: %s: listed %d file(s), expected %d"
                  % (fixture, nfiles, wantfiles))
            bad += 1
        r = subprocess.run([exe, "x", "-o", out, payload], capture_output=True,
                           text=True)
        if r.returncode != 0:
            print("superdisk: %s: extract failed rc=%d %s"
                  % (fixture, r.returncode, r.stderr.strip()))
            return len(entries), len(entries)
        got = set()
        for root, _, files in os.walk(out):
            for n in files:
                got.add(os.path.relpath(os.path.join(root, n), out))
        for name, size, want in entries:
            p = os.path.join(out, name)
            if not os.path.isfile(p):
                print("superdisk: %s: MISSING %s" % (fixture, name))
                bad += 1
                continue
            got.discard(name)
            have = os.path.getsize(p)
            digest = sha(p)
            ok = have == size and digest == want
            bad += not ok
            if verbose or not ok:
                print("  %-56s %7d B  %s" % (name[-56:], have,
                                             "ok" if ok else "MISMATCH"))
        for extra in sorted(got):
            print("superdisk: %s: UNEXPECTED %s" % (fixture, extra))
            bad += 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return bad, len(entries)


def robustness(exe, fixture, timeout):
    """Truncated and bit-flipped payloads must fail cleanly.

    `run_robustness.py` and `fuzz.py` both work from the corpus, which
    holds the ENVELOPE — and `t` does not unwrap envelopes, only `x`
    does — so neither of them ever reaches this parser. Without this the
    format would have had 8,090 robustness variants aimed at its BinHex
    wrapper and none at itself.

    The format is FORCED rather than sniffed, and that is the point: a
    truncated SuperDisk! file loses the 0x27 record its probe insists
    on, so it sniffs as *unknown* and the run would exit cleanly having
    parsed nothing. Every truncation case here was doing exactly that
    until `-f` was added."""
    src = os.path.join(REPO, "fixtures", fixture)
    if not os.path.exists(src):
        return 0, 0
    work = tempfile.mkdtemp(prefix="sdfuzz-")
    bad = ran = 0
    try:
        env = os.path.join(work, "env")
        if subprocess.run([exe, "x", "-nr", "-o", env, src],
                          capture_output=True).returncode != 0:
            return 0, 0
        blob = open(os.path.join(env, PAYLOAD[fixture]), "rb").read()
        rng = random.Random(fixture)
        cases = [("trunc%d" % int(f * 100), blob[:int(len(blob) * f)])
                 for f in (0.05, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 0.98,
                           0.995)]
        for i in range(48):
            b = bytearray(blob)
            for _ in range(rng.randint(1, 8)):
                b[rng.randrange(len(b))] ^= 1 << rng.randrange(8)
            cases.append(("flip%d" % i, bytes(b)))
        for tag, data in cases:
            p = os.path.join(work, tag)
            open(p, "wb").write(data)
            ran += 1
            try:
                r = subprocess.run([exe, "t", "-f", SNIFF, "--budget", str(4 << 20), p],
                                   capture_output=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                print("superdisk: %s/%s: TIMEOUT" % (fixture, tag))
                bad += 1
                continue
            if r.returncode < 0:
                print("superdisk: %s/%s: died with signal %d"
                      % (fixture, tag, -r.returncode))
                bad += 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return bad, ran


def budget(exe, fixture, entries):
    """An entry too big for the budget is that ENTRY's error.

    Both forks in `alysis-disk-expander-12` are method 11, and the budget
    here is chosen so that EVERY one of them is refused — which is what
    makes it a usable probe. What is being checked is not that they fail
    but that the archive KEEPS GOING: the engine's contract is that
    allocation failure is per-entry, never per-archive (CLAUDE.md, 68000
    discipline). Returning UNC_ERR_MEM from the record loop instead
    abandoned the rest of the archive at the first oversized fork, and the
    only visible difference is which entries are named in the errors.

    **The budget was 50,000 until 2026-08-24 and had to come down to
    20,000.** Not because the check got weaker — it asserts exactly what
    it did — but because its precondition stopped holding: SlowFastB's
    window was a flat 96 KB whatever the fork, and is now sized from the
    fork, so `Read Me` began fitting inside 50,000 and extracting. A probe
    that works by making everything fail has to be re-aimed whenever the
    thing it aims at gets smaller, and it says so on the tin: at 50,000 it
    reports 1 of 2 entries named and calls that stopping early."""
    src = os.path.join(REPO, "fixtures", fixture)
    if not os.path.exists(src):
        return 0, 0
    work = tempfile.mkdtemp(prefix="sdbud-")
    try:
        env = os.path.join(work, "env")
        if subprocess.run([exe, "x", "-nr", "-o", env, src],
                          capture_output=True).returncode != 0:
            return 0, 0
        payload = os.path.join(env, PAYLOAD[fixture])
        r = subprocess.run([exe, "x", "--budget", "20000", "-o",
                            os.path.join(work, "out"), payload],
                           capture_output=True, text=True)
        named = [n for n, _, _ in entries
                 if not n.endswith(".rsrc") and n.split("/")[-1] in r.stderr]
        want = len([n for n, _, _ in entries if not n.endswith(".rsrc")])
        if len(named) != want:
            print("superdisk: %s: budget run named %d of %d entries, so it "
                  "stopped early: %s" % (fixture, len(named), want,
                                         r.stderr.strip().replace("\n", " | ")))
            return 1, 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0, 1


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--macextract", default=os.path.join(REPO, "build", "macextract"))
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--timeout", type=float, default=30.0)
    a = ap.parse_args()

    bad = total = 0
    for fixture, entries in sorted(EXPECTED.items()):
        b, n = run_one(a.macextract, fixture, entries, a.verbose)
        bad += b
        total += n
    print("superdisk: %d fork(s) checked, %d bad" % (total, bad))

    rbad = rran = 0
    for fixture in sorted(EXPECTED):
        b, n = robustness(a.macextract, fixture, a.timeout)
        rbad += b
        rran += n
    print("superdisk: %d corrupted variant(s), %d bad" % (rran, rbad))

    gbad = gran = 0
    for fixture, entries in sorted(EXPECTED.items()):
        b, n = budget(a.macextract, fixture, entries)
        gbad += b
        gran += n
    print("superdisk: %d budget run(s), %d bad" % (gran, gbad))
    return 1 if bad or rbad or gbad else 0


if __name__ == "__main__":
    sys.exit(main())

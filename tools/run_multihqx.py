#!/usr/bin/env python3
"""run_multihqx.py — several BinHex documents in one file.

A .hqx posting can hold more than one file; comp.binaries.mac is full of
them. Until 2026-08-15 this engine decoded the first document and exited
0, and the differential suite could not see it because `unar` does the
same (OPEN_ITEMS.md, DECISIONS.md 2026-08-15).

Real corpus documents are concatenated here — with a posting's worth of
text between them, which is what the files in the wild look like — and
graded three ways:

  1. against the same fixtures extracted ONE AT A TIME with `-nr`, so a
     document inside a multi-document file must decode to exactly what
     it decodes to alone;
  2. against `hexbin` (macutils), the reference that handles this case:
     it decodes a document and then re-scans the same input for the next
     header. It is the oracle here for the same reason macunpack is the
     oracle for StuffIt method 6 — the tool the differential suite uses
     cannot do it;
  3. the two ways it must fail: a truncated last document is a per-entry
     error with the earlier documents intact, and a banner with nothing
     usable after it is reported rather than swallowed.

Skips cleanly when the fixtures are absent, like the other suites.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIXDIR = os.path.join(ROOT, "fixtures")

# Small real .hqx fixtures; the SETS below are built from them.
PARTS = ["export-hc.hqx", "mac-rot13.hqx", "downer.hqx"]

BETWEEN = (b"\n--- part 2 of the digest ---\n"
           b"Content-Type: application/mac-binhex40; name=\"next.hqx\"\n\n")


def md5(b):
    return hashlib.md5(b).hexdigest()


def forks_of(outdir):
    """{data md5: rsrc md5} for every entry under outdir (`--forks hidden`)."""
    out = {}
    for dirpath, _, names in os.walk(outdir):
        for n in names:
            if n.startswith("._"):
                continue
            p = os.path.join(dirpath, n)
            r = os.path.join(dirpath, "._" + n)
            rb = open(r, "rb").read() if os.path.exists(r) else b""
            out[md5(open(p, "rb").read())] = md5(rb)
    return out


def macbinary_forks(path):
    """(data md5, rsrc md5) out of one MacBinary file, as hexbin writes."""
    b = open(path, "rb").read()
    dl = int.from_bytes(b[83:87], "big")
    rl = int.from_bytes(b[87:91], "big")
    ro = 128 + (dl + 127) // 128 * 128
    return md5(b[128:128 + dl]), md5(b[ro:ro + rl])


def extract(unclassic, path, args=()):
    """Returns (returncode, {data md5: rsrc md5}) for one file."""
    tmp = tempfile.mkdtemp()
    try:
        r = subprocess.run([unclassic, "x", "-nr", "--forks", "hidden",
                            "-o", tmp, path, *args],
                           capture_output=True, timeout=300)
        return r.returncode, forks_of(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def hexbin_forks(path):
    """The oracle's answer, or None if macutils' hexbin is not installed."""
    if shutil.which("hexbin") is None:
        return None
    tmp = tempfile.mkdtemp()
    try:
        subprocess.run(["hexbin", path], cwd=tmp, capture_output=True,
                       timeout=300)
        got = {}
        for n in sorted(os.listdir(tmp)):
            if n.endswith(".bin"):
                d, r = macbinary_forks(os.path.join(tmp, n))
                got[d] = r
        return got
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check(unclassic, parts, tmpdir):
    problems = []

    # What each document decodes to on its own is the expectation.
    want = {}
    for p in parts:
        rc, got = extract(unclassic, os.path.join(FIXDIR, p))
        if rc != 0:
            problems.append(f"{p} alone: exit {rc}")
        want.update(got)

    joined = os.path.join(tmpdir, "digest.hqx")
    with open(joined, "wb") as out:
        for i, p in enumerate(parts):
            if i:
                out.write(BETWEEN)
            out.write(open(os.path.join(FIXDIR, p), "rb").read())

    rc, got = extract(unclassic, joined)
    if rc != 0:
        problems.append(f"joined: exit {rc}")
    if got != want:
        problems.append(f"joined: {len(got)} document(s), expected {len(want)}"
                        f" with identical forks")

    oracle = hexbin_forks(joined)
    if oracle is None:
        problems.append("NOTE: hexbin absent, oracle step not run")
    elif oracle != got:
        problems.append(f"hexbin disagrees: oracle {len(oracle)} document(s),"
                        f" us {len(got)}")

    # A truncated last document: the earlier ones survive, and the error
    # is per entry. `x` exits non-zero because an entry failed.
    cut = os.path.join(tmpdir, "cut.hqx")
    whole = open(joined, "rb").read()
    with open(cut, "wb") as f:
        f.write(whole[:-len(whole) // (2 * len(parts))])
    rc, got = extract(unclassic, cut)
    if rc == 0:
        problems.append("truncated last document: exit 0, should report it")
    if len(got) < len(parts) - 1:
        problems.append(f"truncated: {len(got)} documents survived, "
                        f"expected {len(parts) - 1}")

    # A banner with nothing usable after it must not be swallowed.
    liar = os.path.join(tmpdir, "liar.hqx")
    with open(liar, "wb") as f:
        f.write(open(os.path.join(FIXDIR, parts[0]), "rb").read())
        f.write(b"\n(This file must be converted with BinHex 4.0)\n"
                b"and here the posting stops\n")
    rc, _ = extract(unclassic, liar)
    if rc == 0:
        problems.append("banner with no document: exit 0, should report it")

    return problems


def main():
    unclassic = os.path.join(ROOT, "build/san/unclassic")
    argv = sys.argv[1:]
    if argv and argv[0] == "--unclassic":
        unclassic = argv[1]
    elif argv:
        unclassic = argv[0]

    missing = [p for p in PARTS
               if not os.path.exists(os.path.join(FIXDIR, p))]
    if missing:
        print(f"multihqx: SKIP ({len(missing)} fixture(s) absent)")
        return 0

    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        for n in (2, 3):
            sub = os.path.join(tmp, str(n))
            os.makedirs(sub)
            problems = check(unclassic, PARTS[:n], sub)
            hard = [p for p in problems if not p.startswith("NOTE:")]
            for p in problems:
                print(f"    {p}")
            if hard:
                fails += 1
                print(f"MULTIHQX FAIL: {n} documents in one file")
            else:
                print(f"multihqx ok: {n} documents in one file")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

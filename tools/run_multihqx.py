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


def extract(macextract, path, args=()):
    """Returns (returncode, {data md5: rsrc md5}) for one file."""
    tmp = tempfile.mkdtemp()
    try:
        r = subprocess.run([macextract, "x", "-nr", "--forks", "hidden",
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


def check(macextract, parts, tmpdir):
    problems = []

    # What each document decodes to on its own is the expectation.
    want = {}
    for p in parts:
        rc, got = extract(macextract, os.path.join(FIXDIR, p))
        if rc != 0:
            problems.append(f"{p} alone: exit {rc}")
        want.update(got)

    joined = os.path.join(tmpdir, "digest.hqx")
    with open(joined, "wb") as out:
        for i, p in enumerate(parts):
            if i:
                out.write(BETWEEN)
            out.write(open(os.path.join(FIXDIR, p), "rb").read())

    rc, got = extract(macextract, joined)
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
    rc, got = extract(macextract, cut)
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
    rc, _ = extract(macextract, liar)
    if rc == 0:
        problems.append("banner with no document: exit 0, should report it")

    return problems


def check_posted(macextract, tmp):
    """ONE document cut across several postings, each part carrying its
    own mail header — the other half of "multipart", and the half that
    puts junk INSIDE the stream rather than between documents.

    hexbin reads these (hqx.c skips a line that holds "intermediate
    garbage"), and until 2026-08-15 we did not: the ':' in "From:" ended
    the document and the entry came back truncated. Also pinned here is
    the edge of the rule — a junk line built ONLY of alphabet characters
    is indistinguishable from data and is still consumed, which BinHex's
    per-fork CRC then catches as a per-entry error rather than silence.
    """
    os.makedirs(tmp, exist_ok=True)
    problems = []
    src = os.path.join(FIXDIR, PARTS[0])
    lines = open(src, "rb").read().split(b"\n")
    half = len(lines) // 2

    rc, want = extract(macextract, src)
    if rc != 0:
        problems.append(f"posted: the fixture alone exits {rc}")

    posted = os.path.join(tmp, "posted.hqx")
    with open(posted, "wb") as f:
        f.write(b"From: someone\nSubject: " + PARTS[0].encode() + b" (1/2)\n\n")
        f.write(b"\n".join(lines[:half]) + b"\n")
        f.write(b"\nFrom: someone\nSubject: " + PARTS[0].encode() + b" (2/2)\n\n")
        f.write(b"[ part 2 of 2 -- append to part 1 ]\n\n")
        f.write(b"\n".join(lines[half:]))

    rc, got = extract(macextract, posted)
    if rc != 0:
        problems.append(f"posted: exit {rc}")
    if got != want:
        problems.append(f"posted: {len(got)} document(s) with different forks, "
                        f"expected the {len(want)} the single file gives")

    # The edge: alphabet-only junk cannot be told from data, so it is
    # taken as data and the CRC objects. Silence would be the bug.
    edged = os.path.join(tmp, "edged.hqx")
    with open(edged, "wb") as f:
        f.write(b"\n".join(lines[:half]) + b"\nAB:CD\n" + b"\n".join(lines[half:]))
    rc, _ = extract(macextract, edged)
    if rc == 0:
        problems.append("edged: alphabet-only junk mid-stream was accepted "
                        "silently; the CRC should have objected")
    return problems


def main():
    macextract = os.path.join(ROOT, "build/san/macextract")
    argv = sys.argv[1:]
    if argv and argv[0] == "--macextract":
        macextract = argv[1]
    elif argv:
        macextract = argv[0]

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
            problems = check(macextract, PARTS[:n], sub)
            hard = [p for p in problems if not p.startswith("NOTE:")]
            for p in problems:
                print(f"    {p}")
            if hard:
                fails += 1
                print(f"MULTIHQX FAIL: {n} documents in one file")
            else:
                print(f"multihqx ok: {n} documents in one file")

        problems = check_posted(macextract, os.path.join(tmp, "posted"))
        for p in problems:
            print(f"    {p}")
        if problems:
            fails += 1
            print("MULTIHQX FAIL: one document posted in several parts")
        else:
            print("multihqx ok: one document posted in several parts")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

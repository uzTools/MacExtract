#!/usr/bin/env python3
"""run_ziplarge.py — zips with more entries than a 16-bit count can hold.

A zip's end-of-central-directory record counts its entries in 16 bits.
Past 65,535 the real count lives in a Zip64 record, and a reader that
trusts the 16-bit field does not fail: it walks 65,535 entries and
reports success, silently dropping the rest. That is what this checks,
and it is why the archives here are generated rather than harvested —
nothing in the corpus is that large.

Graded three ways, none of them our own output:

  CPython's `zipfile`  wrote the archives, and its `namelist()` is the
                       count that was intended.
  `lsar`               The Unarchiver, an independent reader, over the
                       same file. Skipped if it is not installed.
  the boundary itself  65,535 entries (no Zip64 record) and 65,536
                       (one) are both built, so a reader that ignores
                       Zip64 passes the first and fails the second.

Also checked: a Zip64 locator whose record sits past 4 GB is refused
rather than truncated to something addressable, and a locator whose
record signature does not match falls back to the 16-bit count instead
of erroring — XADMaster's behaviour, which fmt_exo.c follows.

What this CANNOT see: anything about archives that are actually larger
than 4 GB. Every file here is a few megabytes with a large entry COUNT;
the size limits are measured separately (FORMATS.md, *Size limits*).
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile


def build(path, n):
    """A stored zip of n one-byte entries. Past 65,535 CPython writes the
    Zip64 record; below it, it does not."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for i in range(n):
            z.writestr("f%06d.txt" % i, b"x")


def ours_list(unclassic, path):
    """Entry names as our CLI lists them, or None if it failed."""
    r = subprocess.run([unclassic, "l", path], capture_output=True)
    if r.returncode != 0:
        return None
    names = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5 and parts[0] in ("f", "d"):
            names.append(parts[4])
    return names


def lsar_count(path):
    if not shutil.which("lsar"):
        return None
    r = subprocess.run(["lsar", path], capture_output=True)
    if r.returncode != 0:
        return None
    return len(r.stdout.decode("utf-8", "replace").splitlines()) - 1


def check_count(unclassic, path, want, label, problems):
    got = ours_list(unclassic, path)
    if got is None:
        problems.append("%s: listing failed, expected %d entries" % (label, want))
        return
    if len(got) != want:
        problems.append("%s: listed %d entries, wanted %d" % (label, len(got), want))
        return
    second = lsar_count(path)
    if second is not None and second != want:
        problems.append("%s: lsar says %d entries, zipfile says %d"
                        % (label, second, want))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unclassic", default="build/unclassic")
    args = ap.parse_args()

    problems = []
    ran = 0
    tmp = tempfile.mkdtemp()
    try:
        # The boundary, from both sides. 65,535 needs no Zip64 record;
        # 65,536 does, and is the case that used to come back short.
        for n in (65535, 65536):
            p = os.path.join(tmp, "n%d.zip" % n)
            build(p, n)
            want = len(zipfile.ZipFile(p).namelist())
            if want != n:                     # the generator itself
                problems.append("n%d.zip: zipfile wrote %d entries" % (n, want))
            check_count(args.unclassic, p, n, "n%d.zip" % n, problems)
            ran += 1

        # An ordinary small file that carries Zip64 structures anyway:
        # extraction must be unaffected.
        p = os.path.join(tmp, "small64.zip")
        payload = b"hello from a zip64 container\n" * 10
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            with z.open(zipfile.ZipInfo("hello.txt"), "w", force_zip64=True) as f:
                f.write(payload)
        out = os.path.join(tmp, "out")
        os.mkdir(out)
        r = subprocess.run([args.unclassic, "x", "-o", out, p],
                           capture_output=True)
        got = os.path.join(out, "hello.txt")
        if r.returncode != 0 or not os.path.exists(got):
            problems.append("small64.zip: forced-Zip64 file did not extract")
        elif open(got, "rb").read() != payload:
            problems.append("small64.zip: extracted bytes differ")
        ran += 1

        # A locator whose record sits past 4 GB is out of reach: refuse,
        # do not truncate the offset into something addressable.
        p = os.path.join(tmp, "far64.zip")
        build(p, 65536)
        raw = bytearray(open(p, "rb").read())
        loc = raw.rfind(b"PK\x06\x07")
        if loc < 0:
            problems.append("far64.zip: no Zip64 locator to edit")
        else:
            raw[loc + 12:loc + 16] = struct.pack("<I", 1)   # offset high word
            open(p, "wb").write(bytes(raw))
            r = subprocess.run([args.unclassic, "l", p], capture_output=True)
            if r.returncode == 0:
                problems.append("far64.zip: a record past 4 GB was accepted")
        ran += 1

        # A locator pointing at something that is not a Zip64 record:
        # fall back to the 16-bit count rather than failing the archive.
        p = os.path.join(tmp, "nosig64.zip")
        build(p, 65536)
        raw = bytearray(open(p, "rb").read())
        rec = raw.rfind(b"PK\x06\x06")
        if rec < 0:
            problems.append("nosig64.zip: no Zip64 record to edit")
        else:
            raw[rec:rec + 4] = b"PK\x06\x05"
            open(p, "wb").write(bytes(raw))
            got = ours_list(args.unclassic, p)
            if got is None or len(got) != 65535:
                problems.append("nosig64.zip: expected the 16-bit count "
                                "(65535), got %s"
                                % ("failure" if got is None else len(got)))
        ran += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("ZIPLARGE FAIL " + p)
    print("ziplarge: %d case(s) checked, %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

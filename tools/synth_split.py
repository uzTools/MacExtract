#!/usr/bin/env python3
"""synth_split.py — generate plain NAME.001 / NAME.002 split sets.

There is no format to generate: a split is a file cut into pieces plus
the convention that the pieces are numbered. So the generator is a
dozen lines, and what matters is what the pieces are cut FROM, because
that decides who can adjudicate the result.

  * a plain data file. The oracle joins this one — XADSplitFileParser
    is tried only after every content parser has declined — so the join
    itself is checked against `unar`, byte for byte.

  * a zip archive. The oracle CANNOT join this one: part 1 begins with
    a local file header and is read as the truncated zip it is a slice
    of. That shape is the reason this scheme was implemented at all
    (`Archive.sit.001` is how these sets appear in the wild), and it is
    adjudicated three other ways instead — against the original bytes,
    against our own read of the unsplit archive, and against the source
    tree that was zipped.

Each case returns (kind, wholepath, partpaths, srcdir). `srcdir` is
None where the payload is not an archive. Part order is the numbering,
which is all the scheme has.
"""
import os
import random
import shutil
import subprocess


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _cut(whole, n):
    """Cut `whole` into n numbered parts, the last one short.

    Sized so no part comes out empty, and deliberately NOT a round
    number: a part boundary in the middle of whatever structure the
    payload has is the whole risk this scheme carries.
    """
    data = open(whole, "rb").read()
    sz = (len(data) + n - 1) // n
    assert sz * (n - 1) < len(data), "that many parts would leave one empty"
    paths = []
    for i in range(n):
        p = "%s.%03d" % (whole, i + 1)
        _write(p, data[i * sz:(i + 1) * sz])
        paths.append(p)
    return paths


def _payload(seed, n):
    """Bytes that no probe in the engine recognizes, so the oracle's
    content parsers all decline and its split parser gets a turn."""
    r = random.Random(seed)
    return bytes(r.randrange(1, 250) for _ in range(n))


# --- cases ---------------------------------------------------------------

def case_blob3(d):
    """A plain file in 3 parts: the case the oracle can also join."""
    whole = os.path.join(d, "blob.dat")
    _write(whole, _payload(41, 30000))
    return ("blob", whole, _cut(whole, 3), None)


def case_blob7(d):
    """More parts, and a payload size that does not divide evenly."""
    whole = os.path.join(d, "seven.dat")
    _write(whole, _payload(42, 30011))
    return ("blob", whole, _cut(whole, 7), None)


def case_zip5(d):
    """An archive in 5 parts: what a real split of a .sit looks like,
    with an archive this environment can generate."""
    src = os.path.join(d, "src")
    for i in range(4):
        _write(os.path.join(src, "f%d.bin" % i), _payload(50 + i, 20000))
    _write(os.path.join(src, "deep", "inside.bin"), _payload(60, 9000))
    _write(os.path.join(src, "small.txt"), b"a small one\n")
    whole = os.path.join(d, "Archive.zip")
    subprocess.run(["zip", "-q", "-r", "-X", "-0", whole, "src"],
                   cwd=d, check=True)
    return ("zip", whole, _cut(whole, 5), src)


CASES = {
    "blob3": case_blob3,
    "blob7": case_blob7,
    "zip5":  case_zip5,
}


def available():
    """The zip case needs Info-ZIP; the blob cases need nothing."""
    return shutil.which("zip") is not None

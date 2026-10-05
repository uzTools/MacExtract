#!/usr/bin/env python3
"""synth_zipsplit.py — generate spanned ("split") zip sets with Info-ZIP.

The generator here is `zip -s` itself, not a hand-rolled writer, and that
is the point: a spanned zip is defined by what the producer does with the
"disk number start" fields, and a writer of our own would only ever
encode our reading of them. tools/synth_sitsplit.py writes StuffIt parts
by hand because nothing in this environment produces them; `zip` is in
this environment, so it does the work.

Every case builds the SAME content twice — once split, once whole — so
run_segments.py has a fourth opinion that owes nothing to the segment
code: the unsplit archive read by the same engine.

Each case returns (srcdir, partpaths, wholepath). Part order is the
order the format's own naming implies (.z01 ... .zNN, then .zip last),
which is what the CLI has to reconstruct from the directory.

`zip` refuses a split size under 64 KB, so every case here uses 64k and
sizes its files to straddle that boundary on purpose.
"""
import os
import random
import shutil
import subprocess

SPLIT = "64k"


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _rand(seed, n):
    """Incompressible bytes, so a stored and a deflated case differ."""
    return random.Random(seed).randbytes(n)


def _text(seed, n):
    """Compressible bytes, so deflate actually has something to do."""
    r = random.Random(seed)
    words = [b"alpha", b"beta", b"gamma", b"delta", b"epsilon"]
    out = bytearray()
    while len(out) < n:
        out += r.choice(words) + b" "
    return bytes(out[:n])


def _zip(d, name, method_args, srcrel):
    """Build `name`.zip split and whole, from srcrel inside d."""
    split = os.path.join(d, name + ".zip")
    whole = os.path.join(d, name + "-whole.zip")
    base = ["zip", "-q", "-r", "-X"] + list(method_args)
    subprocess.run(base + ["-s", SPLIT, split, srcrel], cwd=d, check=True)
    subprocess.run(base + [whole, srcrel], cwd=d, check=True)
    return split, whole


def _parts_of(d, name):
    """The set's files in the order the format's naming implies.

    Deliberately built here from the naming rule rather than read back
    from the CLI, so the test's idea of the right order owes nothing to
    the code under test.
    """
    out = []
    n = 1
    while True:
        p = os.path.join(d, "%s.z%02d" % (name, n))
        if not os.path.exists(p):
            break
        out.append(p)
        n += 1
    last = os.path.join(d, name + ".zip")
    if os.path.exists(last):
        out.append(last)
    return out


"""Cases whose entries are all STORED, recorded where the method is
chosen rather than guessed from a case name later.

It matters to run_segments.py: an archive that only stores decodes with
one fixed buffer, so its peak heap is that buffer plus the central
directory and nothing else — which is what lets a budget be aimed at
the directory alone. Anything deflated allocates a window on top and a
budget aimed that way starves the decoder instead."""
STORED = set()


def _finish(d, name, method_args, srcrel, case=None):
    _zip(d, name, method_args, srcrel)
    if case and "-0" in method_args:
        STORED.add(case)
    return (os.path.join(d, srcrel), _parts_of(d, name),
            os.path.join(d, name + "-whole.zip"))


# --- cases ---------------------------------------------------------------

def case_stored(d):
    """Stored entries, several of them straddling a part boundary."""
    src = os.path.join(d, "src")
    for i in range(5):
        _write(os.path.join(src, "f%d.bin" % i), _rand(100 + i, 60000))
    _write(os.path.join(src, "small.txt"), b"a small one\n")
    return _finish(d, "Stored", ["-0"], "src", "zstored")


def case_deflate(d):
    """Deflated entries: a COMPRESSED stream crossing a part boundary."""
    src = os.path.join(d, "src")
    for i in range(4):
        _write(os.path.join(src, "t%d.txt" % i), _text(200 + i, 400000))
    _write(os.path.join(src, "raw.bin"), _rand(9, 90000))
    return _finish(d, "Deflate", ["-9"], "src", "zdeflate")


def case_nested(d):
    """Folders, an 8-bit name, and an empty file."""
    src = os.path.join(d, "src")
    _write(os.path.join(src, "one", "two", "deep.bin"), _rand(11, 70000))
    _write(os.path.join(src, "one", "beside.bin"), _rand(12, 70000))
    _write(os.path.join(src, "Appé", "inside.bin"), _rand(13, 30000))
    _write(os.path.join(src, "empty.bin"), b"")
    return _finish(d, "Nested", ["-0"], "src", "znested")


def case_many(d):
    """Enough parts that the extension rolls over .z09 -> .z10."""
    src = os.path.join(d, "src")
    for i in range(12):
        _write(os.path.join(src, "p%02d.bin" % i), _rand(300 + i, 60000))
    return _finish(d, "Many", ["-0"], "src", "zmany")


def case_solo(d):
    """`zip -s` output that did not need splitting after all.

    One file, the spanning marker present, "number of this disk" 0.
    Nothing is missing and nothing needs joining — the case that makes
    the marker useless as evidence of segmentation.
    """
    src = os.path.join(d, "src")
    _write(os.path.join(src, "only.txt"), b"fits in one part\n")
    return _finish(d, "Solo", ["-0"], "src", "zsolo")


def case_spancd(d):
    """A set whose CENTRAL DIRECTORY does not fit in the last part.

    `zip -s` splits the directory too once it outgrows a part, and the
    last part then holds only its tail: "number of the disk with the
    start of the central directory" is an EARLIER part than "number of
    this disk", and the directory's declared offset and size belong to
    that earlier one. Measured 2026-10-05 at 1,200 entries and 64 KB
    per part: disk 7 of 8, the directory starting on disk 6, 132,048
    bytes of it, and 238 of the 1,201 entries in the file the EOCD is
    in.

    Nothing here reached that shape until this case existed, and the
    first draft of `zs_cd_is_there` (src/fmt_zipseg.c) refused such a
    part by requiring the directory to fit in front of the record that
    points at it — true of every single-file archive and false here.
    Long names, because it is the DIRECTORY that has to overflow and a
    name is the only part of an entry that is stored in it twice.
    """
    src = os.path.join(d, "src")
    for i in range(1200):
        _write(os.path.join(src,
               "an-entry-whose-name-is-long-so-the-directory-grows-%04d.bin"
               % i), _rand(400 + i, 200))
    return _finish(d, "SpanCD", ["-0"], "src", "zspancd")


CASES = {
    "zstored":  case_stored,
    "zdeflate": case_deflate,
    "znested":  case_nested,
    "zmany":    case_many,
    "zsolo":    case_solo,
    "zspancd":  case_spancd,
}


def available():
    """Info-ZIP is the generator; without it these cases cannot run."""
    return shutil.which("zip") is not None

#!/usr/bin/env python3
"""synth_ddsplit.py — generate DiskDoubler `SPLT` sets.

The four real specimens are in `ssokolow/diskdoubler-test-files`, which
is a `git clone` rather than a fixture, and they are what grade the
FORMAT (`tools/run_ddtf.py`, byte-exact against the originals both
were made from). This generator grades the READER, and reaches what
two specimens cannot: a set of one, twelve parts, a cut inside the
resource fork, a part with bytes appended after its payload, and the
three ways a set can be wrong.

The header is written from the layout in `src/fmt_ddseg.c`, which was
derived from those specimens — so a case passing here says the reader
matches that layout, and only run_ddtf.py says the layout matches
DiskDoubler. Both are needed; neither substitutes for the other.

Each case returns (whole, rsrc, parts, srcdir):
  whole   the file the parts join back into (its data fork)
  rsrc    that file's resource fork, as bytes
  parts   the part paths, in index order
  srcdir  the tree a zip payload was made from, or None
"""
import os
import random
import shutil
import subprocess
import struct

HEAD = 94


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _crc16_xmodem(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def part_header(ident, datalen, rsrclen, index, nparts, payload,
                type_=b"DDA2", creator=b"DDAP", flags=0x0100,
                mtime=0xE0364FA6, ctime=0xE0364F79, paylen=None):
    """One 94-byte header. `paylen` overrides the declared length,
    which is how the mutation cases lie about it."""
    h = bytearray(HEAD)
    h[0:4] = b"SPLT"
    struct.pack_into(">I", h, 4, ident)
    struct.pack_into(">I", h, 8, datalen)
    struct.pack_into(">I", h, 12, rsrclen)
    h[16:20] = type_
    h[20:24] = creator
    struct.pack_into(">H", h, 24, flags)
    struct.pack_into(">I", h, 32, mtime)
    struct.pack_into(">I", h, 36, ctime)
    struct.pack_into(">H", h, 40, nparts)
    struct.pack_into(">H", h, 42, index)
    struct.pack_into(">I", h, 44, len(payload) if paylen is None else paylen)
    struct.pack_into(">H", h, 48, _crc16_xmodem(payload))
    h[90:94] = b"SPLT"
    return bytes(h)


def cut(whole, rsrc, n, ident=0x0009BE6, tail=b"", suffix="%d"):
    """Cut a file's two forks into `n` parts, data fork first.

    `tail` is appended to every part AFTER its payload — a `SPLT` part
    declares its own length, so trailing bytes must not reach the join.
    """
    data = open(whole, "rb").read()
    stream = data + rsrc
    sz = (len(stream) + n - 1) // n
    assert n == 1 or sz * (n - 1) < len(stream), "a part would come out empty"
    paths = []
    for i in range(n):
        pay = stream[i * sz:(i + 1) * sz]
        p = "%s.%s" % (whole, suffix % (i + 1))
        _write(p, part_header(ident, len(data), len(rsrc), i, n, pay) + pay + tail)
        paths.append(p)
    return paths


def _payload(seed, n):
    r = random.Random(seed)
    return bytes(r.randrange(1, 250) for _ in range(n))


# --- cases ---------------------------------------------------------------

def case_forks2(d):
    """Two parts, cut inside the DATA fork — the specimens' shape."""
    whole = os.path.join(d, "Report.dd")
    _write(whole, _payload(11, 24000))
    rsrc = _payload(12, 3000)
    return (whole, rsrc, cut(whole, rsrc, 2), None)


def case_forkcut(d):
    """Three parts with a cut inside the RESOURCE fork, which the two
    specimens never reach: one has no resource fork and the other's is
    342 bytes, entirely inside the last part."""
    whole = os.path.join(d, "Big.dd")
    _write(whole, _payload(21, 9000))
    rsrc = _payload(22, 21000)
    return (whole, rsrc, cut(whole, rsrc, 3), None)


def case_one(d):
    """A set of ONE: a file with a 94-byte hat, which must extract with
    no other part beside it and no volume source at all."""
    whole = os.path.join(d, "Lone.dd")
    _write(whole, _payload(31, 5000))
    rsrc = _payload(32, 700)
    return (whole, rsrc, cut(whole, rsrc, 1), None)


def case_twelve(d):
    """Twelve parts, and a length that does not divide evenly."""
    whole = os.path.join(d, "Many.dd")
    _write(whole, _payload(41, 30011))
    rsrc = _payload(42, 1001)
    return (whole, rsrc, cut(whole, rsrc, 12), None)


def case_tail(d):
    """Every part carries 64 bytes after its payload. The header says
    where the payload ends, so the join must be unaffected — the one
    thing no other scheme here can do."""
    whole = os.path.join(d, "Padded.dd")
    _write(whole, _payload(51, 12000))
    rsrc = _payload(52, 900)
    return (whole, rsrc, cut(whole, rsrc, 3, tail=b"\xAA" * 64), None)


def case_named(d):
    """Parts named nothing like each other and nothing like the file.
    They are matched by CONTENT, so this must join exactly as the
    others do — and the joined file takes its name from the part that
    was OPENED, because the format stores none."""
    whole = os.path.join(d, "Scattered.dd")
    _write(whole, _payload(61, 16000))
    rsrc = _payload(62, 400)
    parts = cut(whole, rsrc, 3)
    renamed = []
    for i, p in enumerate(parts):
        q = os.path.join(d, ["zzz.bin", "aaa.bin", "middle.bin"][i])
        os.rename(p, q)
        renamed.append(q)
    return (whole, rsrc, renamed, None)


def case_numbered(d):
    """Parts named .001 / .002 — the plain-split convention. Both hosts
    decide a plain split by NAME before the sniff has a say, so this
    set must be joined as the scheme its HEADER declares: joining it as
    a plain split would fold every 94-byte header into the file, and
    quietly."""
    whole = os.path.join(d, "Numbered.dd")
    _write(whole, _payload(91, 20000))
    rsrc = _payload(92, 512)
    return (whole, rsrc, cut(whole, rsrc, 3, suffix="%03d"), None)


def case_zip4(d):
    """An archive payload in 4 parts, so the join can be checked all
    the way through to a source tree."""
    src = os.path.join(d, "src")
    for i in range(3):
        _write(os.path.join(src, "f%d.bin" % i), _payload(70 + i, 15000))
    _write(os.path.join(src, "deep", "inside.bin"), _payload(80, 7000))
    whole = os.path.join(d, "Archive.zip")
    subprocess.run(["zip", "-q", "-r", "-X", "-0", whole, "src"],
                   cwd=d, check=True)
    return (whole, b"", cut(whole, b"", 4), src)


CASES = {
    "forks2":  case_forks2,
    "forkcut": case_forkcut,
    "one":     case_one,
    "twelve":  case_twelve,
    "tail":    case_tail,
    "named":   case_named,
    "numbered": case_numbered,
    "zip4":    case_zip4,
}


def available():
    """Only the zip case needs anything (Info-ZIP)."""
    return shutil.which("zip") is not None

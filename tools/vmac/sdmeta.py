#!/usr/bin/env python3
"""sdmeta.py — what SuperDisk!'s own extractor does with +18..21 and a
folder's 20 bytes.

A SuperDisk! file record is 30 bytes (src/fmt_superdisk.c, from the
format's own decoders disassembled): lengths, type, creator, flags at
+16, then four bytes nobody has decoded, then two dates at +22 and +26.
A folder record carries 20 bytes the engine discards. This builds a
stream out of a real archive's records (`synth_sd.borrow`) with those
bytes replaced by sentinels, runs `super-disk-utility.hqx`'s own
self-extractor over it (`superdisk.run_selfextractor`, System 7), and
reads the catalog records back (`hfscat.py`).

    sdmeta.py --run

Sentinels: file +18..21 is (0x0113, 0x0115) for the file in the folder
and (0x0066, 0x0077) for the one at the root; the folder's 20 bytes are
0x01 at even offsets and the offset itself at odd ones, so each word
names its place.

What it CANNOT see:
- **another SuperDisk! extractor** (Disk Expander's modules, the control
  panel): one self-extractor's code;
- **the writer side**: whether SuperDisk! ever writes these bytes from a
  file's catalog record is not asked here;
- **Get Info comments** (the Desktop file).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import hfscat                                              # noqa: E402
import superdisk as SD                                     # noqa: E402
import synth_sd as S                                       # noqa: E402

from sitmeta import FIXTURES                               # noqa: E402

FIXTURE = os.path.join(FIXTURES, "super-disk-utility.hqx")
DIRINFO = bytes(o if o % 2 else 0x01 for o in range(20))
LOC_IN, LOC_ROOT = b"\x01\x13\x01\x15", b"\x00\x66\x00\x77"


def build(orig):
    dirinfo, finfo, blocks, dlen = S.borrow(orig)
    fin = finfo[:18] + LOC_IN + finfo[22:]
    froot = finfo[:18] + LOC_ROOT + finfo[22:]
    body = (S._tag8(0x29) + S._pstr(b"SentFold") + DIRINFO +
            S._tag8(0x28) + S._pstr(b"inner.txt") + fin + blocks +
            S._tag8(0x2A) +
            S._tag8(0x28) + S._pstr(b"outer.txt") + froot + blocks)
    return orig[:8] + body + S._tag8(0x27), finfo


def main():
    fixture = FIXTURE
    work = SD.R.work_tmp("sdmeta-")
    name, ftype, creator, orig, rsrc = SD.unwrap(fixture, work)
    blob, finfo = build(orig)
    print("sdmeta: borrowed file record %s" % finfo.hex())
    img = SD.run_selfextractor(work, name, ftype, creator, blob, rsrc,
                               "sdmeta")
    recs = hfscat.records(open(img, "rb").read())
    for want in (b"SentFold", b"inner.txt", b"outer.txt"):
        hit = [r for r in recs if r["path"][-1] == want]
        if len(hit) != 1:
            print("sdmeta: %-10s %d records" % (want.decode(), len(hit)))
            continue
        r = hit[0]
        f = hfscat.fields(r)
        if r["kind"] == hfscat.DIR:
            print("sdmeta: folder %s  DInfo %s  DXInfo %s" % (
                "/".join(x.decode("mac-roman") for x in r["path"]),
                r["rec"][22:38].hex(), r["rec"][38:54].hex()))
            print("        sentinel   %s" % DIRINFO.hex())
        else:
            print("sdmeta: file   %s  FInfo %s  loc %s  FXInfo %s" % (
                "/".join(x.decode("mac-roman") for x in r["path"]),
                r["rec"][4:20].hex(), f["fdLocation"],
                r["rec"][56:72].hex()))
    print("sdmeta: screenshots in %s" % os.path.join(SD.SHOTS, "sdmeta"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

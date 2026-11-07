#!/usr/bin/env python3
"""run_fileandfolder.py — the CLI when a file and a folder want one name.

    tools/run_fileandfolder.py [--cli build/san/macextract]

A file and a folder cannot share a name in one folder. A file already
there is not touched: the folder is numbered past it, `X~1`, and every
entry of that folder finds the same one. A file whose name a folder
already has is numbered past it. The Macintosh application does the same
(DECISIONS.md 2026-11-07, *the folder numbered past a file*), graded by
`tools/run_macnames.py`'s `file-and-folder` and `file-in-place` cases and
on the emulator (`interactive.py --chain`).

Until 2026-11-07 the CLI made folders with a bare mkdir -p and failed
every entry under a folder whose name a file held ("Not a directory").

Every subject is generated here: zips, and BinHex from
`tools/synth_wrapped.py`. What this CANNOT see: the Macintosh's own
answer (see above); a name past 99 numbers, where the entry fails.
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_wrapped                                          # noqa: E402


def zipbytes(entries):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for name, data in entries:
            z.writestr(name, data)
    return b.getvalue()


def tree(d):
    out = {}
    for root, _, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            out[os.path.relpath(p, d)] = open(p, "rb").read()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", default="build/san/macextract")
    args = ap.parse_args()
    cli = os.path.abspath(args.cli)
    if not os.path.exists(cli):
        print("fileandfolder: %s absent, skipped" % args.cli)
        return 0

    problems = []
    tmp = tempfile.mkdtemp()
    ran = [0]

    def case(tag, fname, data, want, notice=None, rc_want=0):
        ran[0] += 1
        d = os.path.join(tmp, tag)
        os.mkdir(d)
        open(os.path.join(d, fname), "wb").write(data)
        r = subprocess.run([cli, "x", "-o", ".", fname], cwd=d,
                           capture_output=True)
        got = tree(d)
        err = r.stderr.decode("utf-8", "replace")
        if r.returncode != rc_want:
            problems.append("%s: exit %d, wanted %d (%s)"
                            % (tag, r.returncode, rc_want, err.strip()))
        if got != want:
            problems.append("%s: wrote %r, wanted %r"
                            % (tag, sorted(got), sorted(want)))
        if notice and notice not in err:
            problems.append("%s: no notice %r in %r" % (tag, notice, err))

    def hqx(name, payload):
        return synth_wrapped.binhex(name, payload, ftype=b"ZIP ",
                                    creator=b"ZIP ")

    try:
        # The layer `Z` is in the way while its folder `Z/` is made.
        z = hqx("Z", zipbytes([("Z/a.txt", b"a\n"), ("Z/b.txt", b"b\n")]))
        case("chain", "Z.hqx", z,
             {"Z.hqx": z, "Z~1/a.txt": b"a\n", "Z~1/b.txt": b"b\n"},
             notice="the folder is Z~1")
        # The next layer fails (a CRC): the layer is kept, as before. The
        # CLI keeps the failed entry's bytes, as it does everywhere.
        bad = bytearray(zipbytes([("Z/a.txt", b"a\n"), ("Z/b.txt", b"b\n")]))
        bad[bad.index(b"b\n")] ^= 0x01
        z = hqx("Z", bytes(bad))
        case("chain-fails", "Z.hqx", z,
             {"Z.hqx": z, "Z": bytes(bad), "Z~1/a.txt": b"a\n",
              "Z~1/b.txt": b"c\n"}, rc_want=1)
        # The archive extracted beside itself: the user's file untouched.
        a = zipbytes([("Achain/one.txt", b"1\n"), ("Achain/two.txt", b"2\n")])
        case("beside", "Achain", a,
             {"Achain": a, "Achain~1/one.txt": b"1\n",
              "Achain~1/two.txt": b"2\n"}, notice="the folder is Achain~1")
        # One archive holding both: the second is numbered, top and below.
        for order in ("file-first", "folder-first"):
            for where in ("", "In/"):
                ents = [(where + "X", b"f\n"), (where + "X/y.txt", b"y\n")]
                if order == "folder-first":
                    ents.reverse()
                    want = {where + "X~1": b"f\n", where + "X/y.txt": b"y\n"}
                else:
                    want = {where + "X": b"f\n", where + "X~1/y.txt": b"y\n"}
                zz = zipbytes(ents)
                want["a.zip"] = zz
                case(order + ("-below" if where else ""), "a.zip", zz, want)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("FILEANDFOLDER FAIL " + p)
    print("fileandfolder: %d case(s), %d problem(s)" % (ran[0], len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""nowmeta.py — which Now Compress record bytes does Now QuickFiler restore?

A Now Compress entry record is 110 bytes (docs/formats/now-compress.md,
*The archive layer*): type at +38, creator +42, Finder flags +46, two
dates at +54 and +58, then fields nobody has assigned — the rest of the
16 bytes from +38 (+48..53), a third date at +62, and +66..81. This
builds an archive whose unassigned bytes are sentinels, hands it to
QuickFiler's own **Dearchive** (`nowcompress.dearchive`), and reads every
expanded file's and folder's catalog record back (`hfscat.py`).

    nowmeta.py --make      write the sentinel archive, no emulator
    nowmeta.py --run       one boot of Now Utilities 5.0.1, then the report

The archive is `synth_now.build_archive` with the options of the rung
Now Compress accepts (`ladder-trail`, synth_now.py), one folder holding
one file and one file at the top. A sentinel byte at an odd offset IS
that offset; at an even one it is 0x01 in a file record and 0x02 in a
folder's, so a word reads 0x01NN and names its own place.

What it CANNOT see:
- **Now Utilities 6.0's QuickFiler**, or any other reader.
- **Whether the encoder ever writes these bytes**: that is the writer
  side, which this does not drive.
- **Get Info comments** (the Desktop file).
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import hfscat                                              # noqa: E402
import synth_now as N                                      # noqa: E402

OUT = os.path.join(os.path.expanduser("~"), ".cache", "macextract",
                   "sitmeta", "now")
REC0, REC = 24, 110
FILE_GAPS = list(range(48, 54)) + list(range(62, 82))
DIR_GAPS = list(range(38, 54)) + list(range(62, 82))


def build():
    text = N.sample_data()["text"][:3000]
    # Sub is NESTED: a top-level folder's location is whatever the
    # expander and the Finder choose for the new item (the first run
    # gave Fold (0x70,0x1c8), none of its sentinels).
    tree = [N.folder("Fold", [N.folder("Sub", [N.file(
                "inner", data=text, shapes=("newlzss",), chunk=0x8000)])]),
            N.file("outer", data=text[:2000], shapes=("newlzss",),
                   chunk=0x8000)]
    blob = bytearray(N.build_archive(tree, 0, lead=True, sums=True,
                                     arch=True, word=True, tailwords=True,
                                     trailer=True))
    n = struct.unpack(">I", blob[8:12])[0]
    for i in range(n):
        at = REC0 + REC * i
        isdir = blob[at + 37] & 0x10
        page = 0x02 if isdir else 0x01
        for o in (DIR_GAPS if isdir else FILE_GAPS):
            blob[at + o] = o if o % 2 else page
        struct.pack_into(">I", blob, at + 106, sum(blob[at:at + 106]))
    return bytes(blob)


def make():
    from arcmac import macbinary
    os.makedirs(OUT, exist_ok=True)
    blob = build()
    open(os.path.join(OUT, "sentinel.now"), "wb").write(blob)
    mb = os.path.join(OUT, "sentinel.bin")
    open(mb, "wb").write(macbinary("sentinel", N.ARCHIVE_TYPE,
                                   N.ARCHIVE_CREATOR, blob, b""))
    print("nowmeta: %s, %d B" % (mb, len(blob)))
    return mb, blob


def report(img, blob):
    recs = hfscat.records(open(img, "rb").read())
    n = struct.unpack(">I", blob[8:12])[0]
    for i in range(n):
        h = blob[REC0 + REC * i:REC0 + REC * (i + 1)]
        print("nowmeta: record %d, %s" % (i, h[1:1 + h[0]].decode()))
        name = h[1:1 + h[0]]
        hit = [r for r in recs if r["path"][-1] == name]
        if len(hit) != 1:
            print("nowmeta: %-8s %d records on the volume" % (
                name.decode(), len(hit)))
            continue
        r = hit[0]
        f = hfscat.fields(r)
        rec = r["rec"]
        if r["kind"] == hfscat.DIR:
            span = [("DInfo", 22, 16), ("DXInfo", 38, 16),
                    ("dirBkDat", 18, 4)]
        else:
            span = [("FInfo", 4, 16), ("FXInfo", 56, 16),
                    ("filBkDat", 52, 4), ("filFlags", 2, 1)]
        print("nowmeta: %s %s" % ("folder" if r["kind"] == hfscat.DIR
                                  else "file  ", name.decode()))
        for label, off, size in span:
            v = rec[off:off + size]
            # every 2-byte piece, and where in the record it came from
            src = []
            for k in range(0, size, 2):
                w = v[k:k + 2]
                at = [o for o in range(REC - 1) if h[o:o + 2] == w] \
                    if any(w) else []
                src.append("%s%s" % (w.hex(), "@" + ",".join(map(str, at))
                                     if at else ""))
            print("   %-9s %s" % (label, " ".join(src)))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--make", action="store_true")
    p.add_argument("--run", action="store_true")
    a = p.parse_args()
    if a.make:
        make()
        return 0
    if a.run:
        import nowcompress as NC
        mb, blob = make()
        outdir = os.path.join(OUT, "run2")
        NC.dearchive(outdir, [mb])
        report(os.path.join(outdir, "volume.img"), blob)
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""mar_unix.py — MAR archives written by the format's author's own Unix
writer, `mar -c` from mac-utils, from subjects whose every byte is known.

    tools/mar_unix.py            build the writer, write the archives
    tools/mar_unix.py --list     what is in the specimen directory

The writer is built from reference/mar/mac-utils into build/mar-hampa and
RUN, never linked into anything and never committed: it is GPL-2.0-only
(NOTICE). What it writes goes to

    ~/.cache/macextract/vmac/specimens/mar/unix/NAME.mar|.mac
    ~/.cache/macextract/vmac/specimens/mar/unix/NAME.json   the subject

and tools/run_mar.py grades the engine against each subject.

Subjects are MacBinary II files, which is how `mar -c` takes a file's two
forks and its Finder fields (mac-utils src/mar/mar_create.c,
mar_encode_file: a 128-byte header passing mb_get_version's CRC-16 test),
and a `.folder` MacBinary II header of type 'fold' and id 1 for a
folder's own fields (mar_encode_folder_start_inf). One plain file, with no
header, goes in as a data fork alone; its date is its Unix mtime.

What this writer cannot be asked for: a Get Info comment (mb_get_macfile
passes none on), a folder's window rectangle or scroll, and the LZW form,
which only mar 0.2.0 on a Macintosh writes (tools/vmac/README.md, *MAR*).
"""
import binascii
import json
import os
import shutil
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "reference", "mar", "mac-utils")
BUILD = os.path.join(ROOT, "build", "mar-hampa")
VMAC = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
OUT = os.path.join(VMAC, "specimens", "mar", "unix")


def writer():
    """Build mac-utils' `mar` out of the read-only reference tree."""
    binp = os.path.join(BUILD, "src", "mar", "mar")
    if os.path.exists(binp):
        return binp
    if not os.path.isdir(SRC):
        sys.exit("mar_unix: %s is missing; run tools/fetch_references.sh" % SRC)
    shutil.rmtree(BUILD, ignore_errors=True)
    shutil.copytree(SRC, BUILD)
    for cmd in (["sh", "./configure"], ["make", "-j8"]):
        r = subprocess.run(cmd, cwd=BUILD, capture_output=True, text=True)
        if r.returncode:
            sys.exit("mar_unix: %s failed:\n%s" % (cmd[-1], r.stderr[-2000:]))
    return binp


def crc16_ccitt(b):
    """CRC-16/XMODEM, MacBinary II's header check (poly 0x1021, init 0)."""
    return binascii.crc_hqx(b, 0)


def macbinary(name, data=b"", rsrc=b"", typ=b"????", creator=b"????",
              flags=0, v=0, h=0, fldr=0, protected=False, ctime=0, mtime=0,
              folder=False):
    """A MacBinary II file: the header (offsets as mac-utils' macbinary.c
    reads them) and both forks, each padded to 128."""
    hd = bytearray(128)
    hd[0] = 1 if folder else 0
    hd[1] = len(name)
    hd[2:2 + len(name)] = name
    hd[65:69], hd[69:73] = typ, creator
    hd[73] = flags >> 8
    struct.pack_into(">hhH", hd, 75, v, h, fldr)
    hd[81] = 1 if protected else 0
    struct.pack_into(">IIII", hd, 83, len(data), len(rsrc), ctime, mtime)
    hd[101] = flags & 0xFF
    hd[122], hd[123] = 129, 129
    struct.pack_into(">H", hd, 124, crc16_ccitt(bytes(hd[:124])))
    pad = lambda b: b + bytes((128 - len(b) % 128) % 128)
    return bytes(hd) + pad(data) + pad(rsrc)


def text(seed, n):
    out, i = bytearray(), seed
    while len(out) < n:
        out += b"MAR subject %d line %d\r" % (seed, i)
        i += 1
    return bytes(out[:n])


def binary(seed, n):
    out, x = bytearray(), seed * 2654435761 & 0xFFFFFFFF
    while len(out) < n:
        x = (x * 1103515245 + 12345) & 0xFFFFFFFF
        out.append(x >> 16 & 0xFF)
    return bytes(out)


# Each subject: (kind, name, fields), folders holding a list.
FILES = {
    "both": dict(data=text(1, 5000), rsrc=binary(2, 1234), typ=b"APPL",
                 creator=b"TEST", flags=0x2100, v=64, h=32,
                 ctime=0xD9000000, mtime=0xD9000100),
    "locked": dict(data=text(3, 777), typ=b"TEXT", creator=b"ttxt",
                   flags=0x0100, v=10, h=20, protected=True,
                   ctime=0xD9000200, mtime=0xD9000300),
    "rsrconly": dict(rsrc=binary(4, 300), typ=b"rsrc", creator=b"RSED",
                     ctime=0xD9000400, mtime=0xD9000500),
    "empty": dict(typ=b"TEXT", creator=b"ttxt", ctime=0xD9000600,
                  mtime=0xD9000700),
}
FOLDERS = {
    "Top": dict(flags=0x0100, v=40, h=50, fldr=0x0200,
                ctime=0xD8000000, mtime=0xD8000100),
    "Inner": dict(flags=0x0000, v=5, h=6, fldr=0x0100,
                  ctime=0xD8000200, mtime=0xD8000300),
}
PLAIN_MTIME = 1500000000          # 2017-07-14 02:40:00 UTC


def tree(work):
    """Top/{Both Forks, Locked, Plain, Inner/{Rsrc Only, Empty, Empty
    Folder}} as the writer's input: MacBinary files, `.folder` headers."""
    top = os.path.join(work, "Top")
    inner = os.path.join(top, "Inner")
    os.makedirs(os.path.join(inner, "Empty Folder"))
    for d, k in ((top, "Top"), (inner, "Inner")):
        with open(os.path.join(d, ".folder"), "wb") as f:
            f.write(macbinary(k.encode(), typ=b"fold", folder=True,
                              **FOLDERS[k]))
    for d, n, k in ((top, "Both Forks", "both"), (top, "Locked", "locked"),
                    (inner, "Rsrc Only", "rsrconly"),
                    (inner, "Empty", "empty")):
        with open(os.path.join(d, n), "wb") as f:
            f.write(macbinary(n.encode(), **FILES[k]))
    p = os.path.join(top, "Plain")
    with open(p, "wb") as f:
        f.write(text(5, 4321))
    os.utime(p, (PLAIN_MTIME, PLAIN_MTIME))
    return top


def describe():
    """The subject, as the archive must give it back: the fields each
    MacBinary header carries, by the path inside the archive."""
    rows = {}
    for path, k in (("Top", "Top"), ("Top/Inner", "Inner")):
        f = FOLDERS[k]
        rows[path] = dict(is_dir=True, flags=f["flags"], v=f["v"], h=f["h"],
                          view=f["fldr"], ctime=f["ctime"],
                          mtime=f["mtime"])
    rows["Top/Inner/Empty Folder"] = dict(is_dir=True)
    for path, k in (("Top/Both Forks", "both"), ("Top/Locked", "locked"),
                    ("Top/Inner/Rsrc Only", "rsrconly"),
                    ("Top/Inner/Empty", "empty")):
        f = FILES[k]
        rows[path] = dict(data=f.get("data", b"").hex(),
                          rsrc=f.get("rsrc", b"").hex(),
                          type=f["typ"].decode(), creator=f["creator"].decode(),
                          flags=f.get("flags", 0), v=f.get("v", 0),
                          h=f.get("h", 0), locked=f.get("protected", False),
                          ctime=f["ctime"], mtime=f["mtime"])
    rows["Top/Plain"] = dict(data=text(5, 4321).hex(), rsrc="",
                             unix_mtime=PLAIN_MTIME)
    return rows


def main():
    if "--list" in sys.argv:
        for n in sorted(os.listdir(OUT)) if os.path.isdir(OUT) else []:
            print(os.path.join(OUT, n))
        return 0
    mar = writer()
    os.makedirs(OUT, exist_ok=True)
    work = os.path.join(ROOT, ".tmp", "mar_unix")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    top = tree(work)
    rows = describe()
    jobs = [("tree.mar", top, rows)]
    single = os.path.join(top, "Both Forks")
    jobs.append(("single.mac", single,
                 {"Both Forks": rows["Top/Both Forks"]}))
    for name, src, want in jobs:
        out = os.path.join(OUT, name)
        if os.path.exists(out):
            os.remove(out)
        r = subprocess.run([mar, "-c", out, os.path.basename(src)],
                           cwd=os.path.dirname(src), capture_output=True,
                           text=True)
        if r.returncode or not os.path.exists(out):
            sys.exit("mar_unix: mar -c %s failed: %s" % (name, r.stderr))
        with open(os.path.splitext(out)[0] + ".json", "w") as f:
            json.dump(want, f, indent=1, sort_keys=True)
        print("mar_unix: %s, %d B" % (out, os.path.getsize(out)))
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

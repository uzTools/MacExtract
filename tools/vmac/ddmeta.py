#!/usr/bin/env python3
"""ddmeta.py — what DiskDoubler 3.7 keeps of a file's Finder info, and where.

DiskDoubler's 84-byte header has type at +32, creator at +36 and Finder
flags at +40 (docs/formats/diskdoubler-container.md), then bytes nobody
has assigned: +42..47 and +58..77. This asks DiskDoubler itself, twice.

    ddmeta.py --writer     compress a subject whose catalog record carries
                           sentinels; report where they land in the header
    ddmeta.py --reader     expand two copies of that file, one with the
                           header's unassigned bytes overwritten by other
                           sentinels; report what the expanded files got
    ddmeta.py --show FILE  the header's unassigned bytes, no emulator

A sentinel is a value that names where it was put: FXInfo is written as
0x51..0x60, the backup date as 0xA5A6A7A8, the location as (0x0123,
0x0145). Both runs use `diskdoubler.py`'s System 7 image with the INIT
installed, its Settings path (which personalizes the INIT, as every run
must) and its menu coordinates; Expand is the item under Compress, y 44,
measured off `specimens/diskdoubler/probe/04-dd-menu.png`.

What it CANNOT see:
- **Any DiskDoubler but 3.7**, and the DDAR/DDA2 archive records — only
  the single-file header.
- **Whether the Finder rewrote a location after DiskDoubler did.** The
  volume window is open while it works, so the reader run gives each
  copy a catalog location of its own: a value that comes back equal to
  the HEADER's sentinel cannot have come from the Finder.
- **Get Info comments** (the Desktop file).
"""
import argparse
import json
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import diskdoubler as D                                   # noqa: E402
import hfscat                                             # noqa: E402
from arcmac import macbinary                              # noqa: E402

OUT = os.path.join(os.path.dirname(D.HOME), "sitmeta", "dd")
VOL = b"DDwork"
DD_EXPAND_Y = 44

# The subject's catalog record, file record offsets (hfscat.py)
SENT_LOC = b"\x01\x23\x01\x45"            # fdLocation, FInfo +10
SENT_FX = bytes(range(0x51, 0x61))        # FXInfo, the whole 16 bytes
SENT_BK = b"\xa5\xa6\xa7\xa8"             # filBkDat
SENT_FLAGS = b"\x04\x20"                  # fdFlags: custom icon | 0x20


def header_gaps(h):
    return dict(flags=h[40:42].hex(), at42=h[42:48].hex(),
                at58=h[58:78].hex(), at78=h[78:84].hex())


def boot_and(img, tag, steps):
    s = D.Session(D.BOOT, [img], os.path.join(OUT, tag))
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*D.VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.menu(D.DD_MENU_X, D.DD_SETTINGS_Y, "pick-settings")
        D.personalize(s)
        s.shot("settings", wait=15.0)
        D.pick_method(s, "A")
        steps(s)
        s.mac.click(*D.VOLUME_ICON)
        s.mac.command_key("y")                 # Put Away: flush the writes
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()


def records(img):
    return {r["path"]: r for r in hfscat.records(open(img, "rb").read())}


def writer():
    if not os.path.exists(D.BOOT):
        D.install()
    work = D.R.work_tmp("ddmeta-")
    apps = D.extract_app(work)
    subj = os.path.join(work, "subject.bin")
    open(subj, "wb").write(macbinary(D.SUBJECT_NAME, "TEXT", "ttxt",
                                     D.SUBJECT_DATA, D.make_rsrc()))
    img = os.path.join(work, "ddwork.img")
    D.make_volume(img, VOL.decode(), apps + [subj])
    path = (VOL, D.SUBJECT_NAME.encode())
    hfscat.patch(img, path, 4 + 8, SENT_FLAGS)
    hfscat.patch(img, path, 4 + 10, SENT_LOC)
    hfscat.patch(img, path, 56, SENT_FX)
    hfscat.patch(img, path, 52, SENT_BK)
    before = records(img)[path]["rec"]

    def steps(s):
        s.mac.key("s")
        s.shot("selected", wait=3.0)
        s.menu(D.DD_MENU_X, D.DD_COMPRESS_Y, "pick-compress")
        s.shot("compressing", wait=45.0)
        s.mac.key("Return")
        s.shot("done", wait=20.0)

    boot_and(img, "writer", steps)
    after = records(img).get(path)
    files = D.volume_files(img)
    ftype, creator, data, rsrc = files[path[1:]]
    h = D.header(data) and data[:84]
    os.makedirs(OUT, exist_ok=True)
    res = dict(before=before.hex(), after=after and after["rec"].hex(),
               type=ftype, creator=creator, header=h and h.hex(),
               data=data.hex(), rsrc=rsrc.hex())
    json.dump(res, open(os.path.join(OUT, "writer.json"), "w"), indent=0)
    print("ddmeta: the compressed subject is %s/%s" % (ftype, creator))
    if not h:
        raise SystemExit("ddmeta: the subject did not come back compressed")
    print("ddmeta: header", header_gaps(h))
    for name, v in (("fdFlags", SENT_FLAGS), ("fdLocation", SENT_LOC),
                    ("FXInfo", SENT_FX), ("filBkDat", SENT_BK)):
        at = [o for o in range(84 - len(v) + 1) if h[o:o + len(v)] == v]
        print("  %-10s %s -> header %s" % (name, v.hex(),
                                          at or "NOWHERE"))
    if after:
        f = hfscat.fields(after)
        print("  the compressed file's own record: loc %s, FXInfo %s, "
              "bkdat %08x" % (f["fdLocation"], after["rec"][56:72].hex(),
                              f["bkdat"]))
    return 0


def crc_xmodem(data):
    """CRC-16, polynomial 0x1021, initial 0, MSB first, no final XOR."""
    c = 0
    for x in data:
        c ^= x << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


# Header sentinels for the reader run: a different value per byte, and
# none equal to the catalog sentinels above.
def reader():
    w = json.load(open(os.path.join(OUT, "writer.json")))
    data, rsrc = bytes.fromhex(w["data"]), bytes.fromhex(w["rsrc"])
    probe = bytearray(data)
    probe[42:48] = b"\x00\x66\x00\x77\x00\x05"   # loc (102,119), fdFldr 5
    probe[58:78] = bytes(range(0x81, 0x95))
    # +82 is a CRC-16/XMODEM of bytes 0..81 — measured 2026-10-17 on all
    # 70 single-file headers here (69 corpus, 1 DiskDoubler 3.7 wrote for
    # --writer), and DiskDoubler refuses a header whose word disagrees:
    # "Corrupted file or wrong file type", the first --reader run.
    struct.pack_into(">H", probe, 82, crc_xmodem(bytes(probe[:82])))
    # a trailer copy, if this file has one, is left as it was
    work = D.R.work_tmp("ddmeta-")
    apps = D.extract_app(work)
    bins = []
    for name, d in (("Probe", bytes(probe)), ("Control", data)):
        p = os.path.join(work, name + ".bin")
        open(p, "wb").write(macbinary(name, w["type"], w["creator"], d, rsrc))
        bins.append(p)
    img = os.path.join(work, "ddread.img")
    D.make_volume(img, VOL.decode(), apps + bins)
    # each copy's own catalog location, distinct from every sentinel
    hfscat.patch(img, (VOL, b"Probe"), 14, b"\x00\x30\x00\x40")
    hfscat.patch(img, (VOL, b"Control"), 14, b"\x00\x30\x00\xa0")

    def steps(s):
        for key, name in (("p", "probe"), ("c", "control")):
            s.mac.key(key)
            s.shot(name + "-selected", wait=3.0)
            s.menu(D.DD_MENU_X, DD_EXPAND_Y, "pick-expand-" + name)
            s.shot(name + "-expanding", wait=30.0)
            s.mac.key("Return")
            s.shot(name + "-done", wait=10.0)

    boot_and(img, "reader", steps)
    recs = records(img)
    files = D.volume_files(img)
    out = {}
    for name in (b"Probe", b"Control"):
        r = recs.get((VOL, name))
        ftype, creator, d, _ = files.get((name,), ("?", "?", b"", b""))
        expanded = D.header(d) is None
        f = hfscat.fields(r) if r else None
        print("ddmeta: %-8s %s/%s %s  loc %s fdFldr %s FXInfo %s bkdat %s"
              % (name.decode(), ftype, creator,
                 "EXPANDED" if expanded else "still compressed",
                 f and f["fdLocation"], f and f["fdFldr"],
                 r and r["rec"][56:72].hex(), f and "%08x" % f["bkdat"]))
        out[name.decode()] = dict(rec=r and r["rec"].hex(), type=ftype,
                                  creator=creator, expanded=expanded)
    json.dump(out, open(os.path.join(OUT, "reader.json"), "w"), indent=0)
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--writer", action="store_true")
    p.add_argument("--reader", action="store_true")
    p.add_argument("--show", nargs="*")
    a = p.parse_args()
    if a.writer:
        return writer()
    if a.reader:
        return reader()
    for f in a.show or []:
        h = open(f, "rb").read(84)
        print(os.path.basename(f), header_gaps(h))
    return 0


if __name__ == "__main__":
    sys.exit(main())

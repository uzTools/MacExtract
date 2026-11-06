#!/usr/bin/env python3
"""ondesk.py — what the System 7 Finder does with a file flagged on-desk
(0x0001) that is NOT on the desk: inside a folder, on a mounted volume.

    tools/vmac/ondesk.py [--keep]

The volume, built here with hfsutils and `hfscat.patch()`:

    Top        a folder, inited, with a window rectangle
      Desky    a file, flags 0x0101 (inited | on-desk), at (40, 40)
      Plain    the same without on-desk: the control

One boot of System 7.0.1 with its Finder (`ndd.py`'s boot image, which
carries Norton DiskDoubler's Finder menu and nothing else): photograph
the desktop, open the volume, open Top, photograph each step, Put Away
the volume so the Finder's writes reach it, then read every catalog
record back. The question is whether the Finder moves Desky to the
Desktop Folder, rewrites its flags or its place, or leaves it alone.
The shell clears on-desk on every item (DECISIONS.md 2026-11-06, *the
desk no folder is put on*); this asks whether that matters below the top.

What it CANNOT see:
- **A file written while the Finder runs.** The volume is mounted at
  boot, so a Finder that converts System 6 desktop items only when it
  mounts a volume (hypothesis, untested) is what this measures; what it
  does with a file our application writes afterwards needs a second boot.
- **System 6, System 7.5 and later, Mac OS 8 and 9.**
- **A folder flagged on-desk.** Only a file is.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                        # noqa: E402
import hfscat                                          # noqa: E402
from arcmac import macbinary                           # noqa: E402
from diskdoubler import Session, make_volume, VOLUME_ICON  # noqa: E402
import ndd                                             # noqa: E402

VOL = "OnDesk"
SHOTS = os.path.join(R.VMAC_HOME, "specimens", "ondesk")
# A folder's DInfo: frRect (top, left, bottom, right), frFlags inited,
# frLocation, frView by icon.
TOP_DINFO = struct.pack(">hhhhHhhH", 60, 40, 240, 400, 0x0100, 30, 30,
                        0x0100)


def finfo(flags, v, h):
    return struct.pack(">4s4sHhhh", b"TEXT", b"ttxt", flags, v, h, 0)


def build(img):
    work = os.path.dirname(img)
    make_volume(img, VOL, [], size_kb=1440)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        subprocess.run(["hmount", img], check=True, capture_output=True,
                       env=env)
        subprocess.run(["hmkdir", VOL + ":Top"], check=True,
                       capture_output=True, env=env)
        for name in ("Desky", "Plain"):
            p = os.path.join(work, name + ".bin")
            open(p, "wb").write(macbinary(name, "TEXT", "ttxt",
                                          b"on-desk probe\r", b""))
            subprocess.run(["hcopy", "-m", p, VOL + ":Top:"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    key = lambda *p: tuple(x.encode("mac-roman") for x in (VOL,) + p)  # noqa
    hfscat.patch(img, key("Top"), 22, TOP_DINFO)
    hfscat.patch(img, key("Top", "Desky"), 4, finfo(0x0101, 40, 40))
    hfscat.patch(img, key("Top", "Plain"), 4, finfo(0x0100, 40, 120))


def show(img, tag):
    print("ondesk: %s" % tag)
    for r in hfscat.records(open(img, "rb").read()):
        path = "/".join(x.decode("mac-roman") for x in r["path"])
        f = hfscat.fields(r)
        if r["kind"] == hfscat.DIR:
            print("ondesk:   d %-28s frFlags=%04x frLocation=%s" %
                  (path, f["frFlags"], f["frLocation"]))
        else:
            print("ondesk:   f %-28s fdFlags=%04x fdLocation=%s fdFldr=%d" %
                  (path, f["fdFlags"], f["fdLocation"], f["fdFldr"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", action="store_true", help="keep the work dir")
    a = ap.parse_args()
    if a.keep:
        os.environ["HARNESS_KEEP_IMAGES"] = "1"
    work = R.work_tmp("ondesk-")
    img = os.path.join(work, "ondesk.img")
    build(img)
    show(img, "before the boot")
    if not os.path.exists(ndd.BOOT):
        ndd.install()
    s = Session(ndd.BOOT, [img], SHOTS)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.mac.key("Escape")
        time.sleep(0.5)
        s.mac.key("t")                         # type-select Top; no Return
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("top-open", wait=10.0)
        s.mac.command_key("w")                 # close Top
        s.shot("top-closed", wait=4.0)
        s.mac.command_key("w")                 # close the volume window
        s.shot("desktop-after", wait=4.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")                 # Put Away: flush
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    show(img, "after the boot")
    print("ondesk: screenshots in %s" % s.shots)
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

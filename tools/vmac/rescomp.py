#!/usr/bin/env python3
"""rescomp.py — Alysis Resource Compressor 2.0, for the codecs nothing writes.

SuperDisk!'s methods 10 ("SlowFastA"), 13 ("SlowFastC") and 20 ("Tennessee")
are declined per entry because no reachable file uses them: both corpus
archives use 7 and 11, and Alysis's own 1991 control panel writes 1 or 6 at
every setting (`sdcompress.py --sweep`). The compressor that DID write them
would be SuperDisk! 2.x, which the vendor's own technology page describes and
which does not survive on Macintosh Repository, Macintosh Garden, Info-Mac's
`cmp` directory or archive.org.

**This application is the same generation and it is reachable** (Macintosh
Garden, 26 KB): `APPL/Zeee`, version 2.01, 1993, and it carries the whole
codec library as `Cmpr` resources — 1, 2, 9, **10**, 11 (twice), **13** and
**20**, the same resource IDs and the same module bodies as Disk Expander
1.2's. It compresses RESOURCES rather than writing SuperDisk archives, so its
container is Apple's, not the block chain — but a codec stream is a codec
stream, and the block header around one is three fields this project already
knows.

    tools/vmac/rescomp.py --modules    what it carries (no emulator)
    tools/vmac/rescomp.py --probe      boot it and photograph its UI
    tools/vmac/rescomp.py --compress   compress a subject, read it back

**And it is not the producer, which this harness is what established
(2026-08-25).** Driven under Mini vMac it compresses: a `STR` resource of
8,001 bytes came back at **472**, on screen and on the volume. But what it
writes is APPLE's container — signature `A89F6572`, header version 8,
`decompressedLength` 8,001 — with `defProcID` **0**, which is the System's own
decompressor and not one of the `Cmpr` modules; and none of the seven modules
reproduces the subject from that payload under any framing tried
(`tools/sdmodule/`). Its twenty-three help topics offer no codec choice
either: the only options are which RESOURCES to act on. The modules are there
for the Decompress button — for reading what other Alysis products wrote.

So the producer of methods 10, 13 and 20 is still not in hand. What is left,
in order of cheapness: Disk Expander 1.2's own extension, whose `INIT 32` has
a compress path (command 2) walking a method table at 0xf2e; the modules
driven directly, where Tennessee already compresses 4,800 bytes to 102 under
`qemu-m68k`; and SuperDisk! 2.x itself, which the vendor's technology page
describes ("faster and tighter compression algorithms") and which is not on
Macintosh Repository, Macintosh Garden, Info-Mac's `cmp` directory or
archive.org.

**The module header offsets used here are Alysis's own**, from the header
file published at `alysis.us/sdtechnology.htm` (Wayback, 2024 snapshot):
`moduleIdentifier 4`, `moduleNumber 28`, `moduleSize 38`,
`moduleCharacteristics 42`, `moduleName 60`, and commands `1 initialize,
2 compress, 3 decompress`. Everything `tools/sdmodule/` derived by
disassembly agrees with it field for field.

License: LGPL-2.1-or-later. See LICENSE and NOTICE.
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
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "tools", "sdmodule"))

import run as R                                            # noqa: E402
from arcmac import macbinary                               # noqa: E402
from diskdoubler import Session, make_volume, make_rsrc, cli  # noqa: E402
from run_sdmodule import resource_data                     # noqa: E402

WORK = os.path.join(R.VMAC_HOME, "sdisk")
SPECIMENS = os.path.join(R.VMAC_HOME, "specimens", "rescomp")
SIT = os.path.join(WORK, "arc2.sit")
URL = "http://old.mac.gdn/apps/Alysis_Resource_Compressor_2.0.sit"
SHA = "9f07900169c02c30fd2216750ff93a13cbec218d99cb79e6637f4f3d02305e3d"
APP = "Alysis Resource Compressor 2.0"
SYSTEM = "Sys7.img"

# A subject worth compressing: one STR resource of repetitive text, which
# every codec in the library should shrink.
SUBJECT_TEXT = b"\xff" + b"Alysis codec probe. " * 400
SUBJECT_DATA = b"Alysis Resource Compressor probe.\r" * 40


def fetch():
    os.makedirs(WORK, exist_ok=True)
    if os.path.exists(SIT):
        import hashlib
        if hashlib.sha256(open(SIT, "rb").read()).hexdigest() == SHA:
            return SIT
    subprocess.run(["curl", "-sL", "--max-time", "180", "-o", SIT, URL],
                   check=True)
    return SIT


def app_fork():
    """The application's resource fork, extracted with this project's CLI."""
    out = tempfile.mkdtemp(prefix="rc-")
    r = subprocess.run([cli(), "x", "-o", out, fetch()], capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"rescomp: extracting {SIT} failed")
    return out, os.path.join(out, APP + ".rsrc")


def modules():
    """Every codec the application carries, by Alysis's own header layout."""
    out, fork_path = app_fork()
    try:
        fork = open(fork_path, "rb").read()
        res = resource_data(fork)
        flags = [("overwritesSource", 0x8000), ("replacesDestination", 0x4000),
                 ("carryOverWorking", 0x2000), ("initialClearWorking", 0x1000),
                 ("alwaysClearWorking", 0x0800),
                 ("requiresInitialization", 0x0400),
                 ("requiresPassword", 0x0200), ("transformationModule", 0x0100),
                 ("realTime/ownFileIO", 0x0080)]
        print(f"rescomp: {APP} carries {len(res.get('Cmpr', []))} codecs")
        # A resource can hold more than one module end to end — `Cmpr` 22
        # is SlowFastB followed by Tennessee — so the signature is
        # searched for rather than assumed to be at the front.
        found = []
        for rid, rname, blob in res.get("Cmpr", []):
            at = 0
            while True:
                i = blob.find(b"SuperDisk! Add-In Module", at)
                if i < 0:
                    break
                m, at = i - 4, i + 4
                found.append((struct.unpack(">H", blob[m + 28:m + 30])[0], rid,
                              struct.unpack(">I", blob[m + 38:m + 42])[0],
                              struct.unpack(">H", blob[m + 42:m + 44])[0],
                              blob[m + 61:m + 61 + blob[m + 60]]))
        for num, rid, size, chars, nm in sorted(found):
            name = nm.decode("mac_roman", "replace")
            print(f"  Cmpr {rid:5d}  module {num:3d}  {size:6d} B  {name!r:16s}"
                  f"  0x{chars:04x} "
                  + ", ".join(f for f, b in flags if chars & b))
        return 0
    finally:
        shutil.rmtree(out, ignore_errors=True)


def build_volume(tag):
    """A work volume: the application and one subject with a fat resource."""
    out, _ = app_fork()
    work = tempfile.mkdtemp(prefix="rcwork-")
    try:
        appbin = os.path.join(work, "app.bin")
        data = open(os.path.join(out, APP), "rb").read()
        rsrc = open(os.path.join(out, APP + ".rsrc"), "rb").read()
        open(appbin, "wb").write(macbinary(APP, "APPL", "Zeee", data, rsrc))
        subj = os.path.join(work, "subject.bin")
        open(subj, "wb").write(macbinary("Subject", "TEXT", "ttxt",
                                         SUBJECT_DATA, make_rsrc(SUBJECT_TEXT)))
        vol = os.path.join(WORK, "rcwork-%s.dsk" % tag)
        make_volume(vol, "RCwork", [appbin, subj], size_kb=4096)
        return vol
    finally:
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


# The Finder, on Sys7.img with a second volume mounted. Measured off this
# harness's own first frames — a look-and-adjust loop by nature.
WORK_VOLUME = (470, 110)          # the RCwork icon, below the boot volume
APP_ICON = (40, 90)               # in the RCwork window, measured off 02-
SUBJECT_ICON = (167, 90)
FILE_MENU_X = 40                  # the application's own menu bar
EDIT_MENU_X = 78
# File menu items, measured off 04-file-menu.png. Open and Quit have
# keyboard equivalents and are pressed that way; Compress does not.
FILE_COMPRESS_Y = 77
FILE_DECOMPRESS_Y = 92
# The Finder's Special menu, for the shut down that flushes the volume.
# Measured off 09-special-menu.png: the first run aimed at 118 and landed on
# **Restart**, which unmounts nothing in time — the Subject came back with its
# new resource data written and its resource MAP still the old one, which
# parses as garbage. Shut Down is the item that flushes.
SPECIAL_X = 245
SHUT_DOWN_Y = 139


def probe(keep=False):
    """Boot, launch the application, and photograph what it offers.

    Nothing is clicked blind: the volume window, the application's own
    window and both of its menus are photographed so the next mode can
    aim at measured coordinates.
    """
    vol = build_volume("probe")
    boot = os.path.join(R.VMAC_HOME, SYSTEM)
    s = Session(boot, [vol], os.path.join(SPECIMENS, "probe"))
    try:
        s.boot()
        s.shot("desktop", wait=10.0)
        s.mac.click(*WORK_VOLUME, double=True)
        s.shot("work-volume", wait=8.0)
        s.mac.click(*APP_ICON, double=True)
        s.shot("launched", wait=20.0)
        s.peek(FILE_MENU_X, "file-menu")
        s.peek(EDIT_MENU_X, "edit-menu")
    finally:
        time.sleep(4)
        s.close()
    print("rescomp: screenshots in %s — LOOK AT THEM, then set the "
          "coordinates below" % s.shots)
    if not keep:
        os.remove(vol)
    return 0


def compress(keep=False):
    """Open the subject, press Compress, and read back what it wrote.

    The application compresses RESOURCES, so what comes back is Apple's
    container with an Alysis codec inside it — which is the point: the
    stream is written by the original software, and a SuperDisk! block
    header around one is three fields.
    """
    vol = build_volume("compress")
    before = open(vol, "rb").read()
    boot = os.path.join(R.VMAC_HOME, SYSTEM)
    s = Session(boot, [vol], os.path.join(SPECIMENS, "compress"))
    try:
        s.boot()
        s.shot("desktop", wait=10.0)
        s.mac.click(*WORK_VOLUME, double=True)
        s.shot("work-volume", wait=8.0)
        s.mac.click(*APP_ICON, double=True)
        s.shot("launched", wait=20.0)

        s.mac.command_key("o")                 # File > Open
        s.shot("open-dialog", wait=8.0)
        s.mac._xdo("type", "--delay", "150", "Subject")
        time.sleep(1.5)
        s.mac.key("Return")
        s.shot("opened", wait=10.0)            # the resource list

        s.menu(FILE_MENU_X, FILE_COMPRESS_Y, "compress-menu")
        s.shot("compressed", wait=25.0)
        s.mac.command_key("q")
        s.shot("quit", wait=12.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=45.0)
    finally:
        time.sleep(8)
        s.close()
    rc = report(vol, before)
    if not keep:
        os.remove(vol)
    return rc


def report(vol, before):
    """What the volume holds now, and what the subject's resources became."""
    after = open(vol, "rb").read()
    print("rescomp: the work volume %s during the run"
          % ("CHANGED" if after != before else "did NOT change"))
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    out = tempfile.mktemp(suffix=".bin")
    try:
        if subprocess.run(["hmount", vol], capture_output=True,
                          env=env).returncode:
            print("rescomp: the volume will not mount")
            return 1
        print(subprocess.run(["hls", "-l", ":"], capture_output=True,
                             env=env).stdout.decode("mac_roman", "replace"))
        if subprocess.run(["hcopy", "-m", ":Subject", out], capture_output=True,
                          env=env).returncode:
            print("rescomp: no Subject on the volume")
            return 1
        d = open(out, "rb").read()
        dl = struct.unpack(">I", d[0x53:0x57])[0]
        rl = struct.unpack(">I", d[0x57:0x5B])[0]
        ro = 128 + ((dl + 127) & ~127)
        fork = d[ro:ro + rl]
        print(f"rescomp: Subject data {dl} B, resource fork {rl} B")
        try:
            res = resource_data(fork)
        except Exception as e:
            print(f"rescomp: the resource map does not parse ({e}) — that is "
                  f"what a volume flushed mid-write looks like, not a finding. "
                  f"Header says data {struct.unpack('>I', fork[8:12])[0]} B, "
                  f"map at {struct.unpack('>I', fork[4:8])[0]}")
            open(os.path.join(SPECIMENS, "Subject.bin"), "wb").write(d)
            return 1
        print("rescomp: resources:",
              ", ".join(f"{t}:{[i[0] for i in v]}" for t, v in sorted(res.items())))
        for t, items in sorted(res.items()):
            for rid, name, blob in items:
                sig = struct.unpack(">I", blob[:4])[0] if len(blob) >= 4 else 0
                tag = ("APPLE-COMPRESSED" if sig == 0xA89F6572 else "plain")
                print(f"  {t} {rid}: {len(blob)} B  {tag}  head {blob[:16].hex()}")
                if sig == 0xA89F6572:
                    hlen, hver, attr = struct.unpack(">HBB", blob[4:8])
                    ulen = struct.unpack(">I", blob[8:12])[0]
                    print(f"      headerLength {hlen} version {hver} "
                          f"attributes 0x{attr:02x} decompressed {ulen} B")
                    print(f"      header tail {blob[12:hlen].hex()}")
        open(os.path.join(SPECIMENS, "Subject.bin"), "wb").write(d)
        print("rescomp: kept", os.path.join(SPECIMENS, "Subject.bin"))
        return 0
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true", help="fetch the archive")
    ap.add_argument("--modules", action="store_true",
                    help="list the codecs it carries; no emulator")
    ap.add_argument("--probe", action="store_true",
                    help="boot it and photograph its UI")
    ap.add_argument("--compress", action="store_true",
                    help="open the subject, press Compress, read it back")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if a.setup:
        fetch()
        print("rescomp: have", SIT)
    elif a.modules:
        return modules()
    elif a.probe:
        return probe(a.keep)
    elif a.compress:
        return compress(a.keep)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

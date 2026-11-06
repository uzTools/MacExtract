#!/usr/bin/env python3
"""zipitmeta.py — what ZipIt writes in, and reads back from, the View word
of its directory field `0x2805`.

APPNOTE.TXT 4.6.6 defines `0x2805` as 'ZPIT', the folder's DInfo.frFlags,
then "View beShort ZipIt view flag", each MAY be omitted. Every `0x2805`
field this project has seen (12, three archives) holds View 0, so nothing
says what a non-zero one means, and `src/fmt_exo.c` does not read it
(OPEN_ITEMS.md, *the metadata the archives hold and the readers drop*).
This asks ZipIt 1.4 itself (`specimens/zipit/zipit-1.4.sea`, a fat
binary: 16 68k `CODE` resources), on System 7.0.1 (`ndd.py`'s boot image).
Every step is a measured coordinate or a Command key: the shareware
window's "Not yet" is clicked (Return does not press it), and Extract
needs a row selected.

    zipitmeta.py --probe     launch ZipIt, photograph its menus
    zipitmeta.py --writer    zip two folders with planted DInfo, twice (the
                             second after View > by Name); print every 0x2805
    zipitmeta.py --reader    extract a zip whose folders carry 0x2805 with
                             their own frFlags and View; print the folders

Results: DECISIONS.md 2026-11-06, *the field ZipIt 1.4 never wrote*.

What it CANNOT see: ZipIt 2.x, the only writer of 0x2805 seen (a PowerPC
Carbon application: Mac OS 9, not this tier); ZipIt 1.x on System 6; a
file's Finder info (only folders are planted); anything a dialog asks that
the steps do not answer — photograph the step after the one that matters
(tools/vmac/README.md).
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
import run as R                                        # noqa: E402
import hfscat                                          # noqa: E402
from arcmac import macbinary                           # noqa: E402
from diskdoubler import Session, make_volume, VOLUME_ICON  # noqa: E402
import ndd                                             # noqa: E402

VOL = "ZipWork"
SEA = os.path.join(R.VMAC_HOME, "specimens", "zipit", "zipit-1.4.sea")
SHOTS = os.path.join(R.VMAC_HOME, "specimens", "zipit", "meta")


def cli():
    for b in ("rel", "san", ""):
        p = os.path.join(REPO, "build", b, "macextract")
        if os.path.exists(p):
            return p
    raise SystemExit("zipitmeta: build the CLI first (make)")


def zipit_files(work):
    """ZipIt 1.4's application and its Plug-ins folder, decoded by this
    engine out of the self-extractor's data fork: [(path, type, creator,
    data, rsrc)]."""
    mb = os.path.join(work, "sea")
    os.makedirs(mb)
    subprocess.run([cli(), "x", "-o", mb, SEA], check=True,
                   capture_output=True)
    sea = os.path.join(mb, "ZipIt 1.4.sea")
    out = os.path.join(work, "z")
    os.makedirs(out)
    subprocess.run([cli(), "x", "-f", "Zip", "-o", out, sea], check=True,
                   capture_output=True)
    meta = subprocess.run([cli(), "l", "--meta", "-f", "Zip", sea],
                          check=True, capture_output=True).stdout.decode(
                              "utf-8", "surrogateescape")
    finfo = {}
    for line in meta.split("\n"):
        if line.startswith("m "):
            f = line.split(" ", 6)
            finfo[f[6]] = bytes.fromhex(f[1]) if f[1] != "-" else None
    files = []
    for rel in ("ZipIt", "Plug-ins/Mac SEA", "Plug-ins/PC SEA"):
        p = os.path.join(out, rel)
        rp = p + ".rsrc"
        fi = finfo.get(rel) or bytes(16)
        files.append((rel, fi[:4].decode("mac-roman"), fi[4:8].decode("mac-roman"),
                      open(p, "rb").read(),
                      open(rp, "rb").read() if os.path.exists(rp) else b""))
    return files


def volume(img, work, subject_files=()):
    """ZipIt at the root, its Plug-ins beside it, and a folder `Subject`."""
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    make_volume(img, VOL, [], size_kb=4096)
    try:
        subprocess.run(["hmount", img], check=True, capture_output=True, env=env)
        files = zipit_files(work) + list(subject_files)
        dirs = {"/".join(rel.split("/")[:k]) for rel, *_ in files
                for k in range(1, rel.count("/") + 1)} | {"Subject"}
        for d in sorted(dirs, key=lambda d: d.count("/")):
            subprocess.run(["hmkdir", VOL + ":" + d.replace("/", ":")],
                           check=True, capture_output=True, env=env)
        for i, (rel, t, c, data, rsrc) in enumerate(files):
            p = os.path.join(work, "f%d.bin" % i)
            name = rel.split("/")[-1]
            open(p, "wb").write(macbinary(name, t, c, data, rsrc))
            where = VOL + ":" + ":".join(rel.split("/")[:-1])
            subprocess.run(["hcopy", "-m", p, where + (":" if "/" in rel else "")],
                           check=True, capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


SUBJECT = [("Subject/Note", "TEXT", "ttxt", b"zipitmeta subject\r" * 40, b"")]

# Menu titles' x, System 7.0.1 at 512x342, measured off probe/04-launched-later.png.
MENUS = {"file": 50, "edit": 90, "view": 130, "zip": 170, "method": 215,
         "translate": 275}


# The shareware window's "Not yet", measured off probe/05-personalized.png;
# Return does not press it.
NOT_YET = (136, 194)


def personalize(s):
    """ZipIt's first launch asks for a name and an organization."""
    for k in ("T", "e", "s", "t"):
        s.mac.key(k)
        time.sleep(0.15)
    s.mac.key("Tab")
    time.sleep(0.3)
    for k in ("M", "E", "x", "t"):
        s.mac.key(k)
        time.sleep(0.15)
    s.mac.key("Return")
    time.sleep(3.0)


def probe(keep):
    work = R.work_tmp("zipit-")
    img = os.path.join(work, "zipwork.img")
    volume(img, work, SUBJECT)
    if not os.path.exists(ndd.BOOT):
        ndd.install()
    s = Session(ndd.BOOT, [img], os.path.join(SHOTS, "probe"))
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.mac.key("Escape")
        time.sleep(0.5)
        s.mac.key("z")                          # ZipIt; never Return
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("launched", wait=20.0)
        s.shot("launched-later", wait=10.0)
        personalize(s)
        s.shot("personalized", wait=5.0)
        s.mac.click(*NOT_YET)                  # the shareware window
        s.shot("not-yet", wait=5.0)
        for name, x in MENUS.items():
            s.peek(x, "menu-" + name)
        s.menu(MENUS["zip"], 27, "pick-add")
        s.shot("add-dialog", wait=6.0)
    finally:
        time.sleep(3)
        s.close()
    print("zipitmeta: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# The Add dialog's buttons and the menus' items, measured off the probe's
# frames (System 7.0.1, 512x342).
ADD_DONE = (377, 150)
FILE_SAVEAS_Y, VIEW_BYNAME_Y = 91, 43

# The writer run's two folders: each catalog field a value of its own.
WRITER_DIRS = [
    (("Subject",), struct.pack(">hhhhHhhH", 40, 30, 200, 300, 0x0104, 21, 22, 0x0400)),
    (("Subject", "Inner"), struct.pack(">hhhhHhhH", 50, 40, 210, 310, 0x0108, 31, 32, 0x0500)),
]
WRITER_FILES = [("Subject/Note", "TEXT", "ttxt", b"zipitmeta subject\r" * 40, b""),
                ("Subject/Inner/Deep", "TEXT", "ttxt", b"zipitmeta inner\r" * 40, b"")]


def zip2805(blob):
    """[(name, frFlags, View, field hex)] for every 0x2805 field in a zip's
    central directory (APPNOTE.TXT 4.3.12, 4.6.6)."""
    out, i = [], 0
    while True:
        i = blob.find(b"PK\x01\x02", i)
        if i < 0 or i + 46 > len(blob):
            return out
        nl, xl = struct.unpack("<HH", blob[i + 28:i + 32])
        name = blob[i + 46:i + 46 + nl].decode("mac-roman")
        ex = blob[i + 46 + nl:i + 46 + nl + xl]
        k = 0
        while k + 4 <= len(ex):
            eid, sz = struct.unpack("<HH", ex[k:k + 4])
            f = ex[k + 4:k + 4 + sz]
            if eid == 0x2805 and sz >= 8:
                out.append((name, struct.unpack(">H", f[4:6])[0],
                            struct.unpack(">H", f[6:8])[0], f.hex()))
            k += 4 + sz
        i += 4


def typed(s, text):
    for ch in text:
        s.mac.key(ch)
        time.sleep(0.15)


def save_as(s, name, tag):
    s.menu(MENUS["file"], FILE_SAVEAS_Y, "pick-saveas-" + tag)
    s.shot("save-dialog-" + tag, wait=5.0)
    s.mac.command_key("a")                     # the name field's text
    typed(s, name)
    s.mac.key("Return")
    s.shot("saved-" + tag, wait=10.0)


def writer(keep):
    work = R.work_tmp("zipit-")
    img = os.path.join(work, "zipwork.img")
    volume(img, work, WRITER_FILES)
    for path, dinfo in WRITER_DIRS:
        hfscat.patch(img, tuple(x.encode("mac-roman") for x in (VOL,) + path),
                     22, dinfo)
    if not os.path.exists(ndd.BOOT):
        ndd.install()
    s = Session(ndd.BOOT, [img], os.path.join(SHOTS, "writer"))
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.mac.key("Escape")
        time.sleep(0.5)
        s.mac.key("z")
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("launched", wait=30.0)
        personalize(s)
        s.shot("personalized", wait=5.0)       # the shareware window draws
        s.mac.click(*NOT_YET)
        s.shot("not-yet", wait=5.0)
        s.menu(MENUS["zip"], 27, "pick-add")
        s.shot("add-dialog", wait=6.0)
        typed(s, "su")                         # type-select Subject
        s.shot("add-selected", wait=2.0)
        s.mac.command_key("g")                 # Add
        s.shot("added", wait=15.0)
        s.mac.click(*ADD_DONE)
        s.shot("archive-window", wait=5.0)
        save_as(s, "Azip", "a")
        s.menu(MENUS["view"], VIEW_BYNAME_Y, "pick-byname")
        s.shot("by-name", wait=4.0)
        save_as(s, "Bzip", "b")
        s.mac.command_key("q")
        s.shot("quit", wait=8.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")                 # Put Away: flush
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    got = ndd.read_forks(img)
    for path, (t, c, data, rsrc) in sorted(got.items()):
        if data[:2] == b"PK":
            keptp = os.path.join(s.shots, path[-1])
            open(keptp, "wb").write(data)
            print("zipitmeta: %s, %d B, kept" % ("/".join(path), len(data)))
            for name, fl, view, hx in zip2805(data):
                print("zipitmeta:   %-24s frFlags=%04x View=%04x  %s"
                      % (name, fl, view, hx))
    print("zipitmeta: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# The reader run's zip: each folder a 0x2805 field with flags and a View
# of its own, so whatever lands on the extracted folder names its source.
# The archive window's first row, measured off reader/08-archive-open.png.
SENT_ROW = (60, 113)
READER_DIRS = [("Sent/", 0x0102, 0x0300), ("Sent/Inner/", 0x0106, 0x0500)]


def sentinel_zip():
    """A zip in ZipIt's own field layout (APPNOTE.TXT 4.6.5, 4.6.6), the
    same extra field in the local header and the central directory."""
    import io
    import zipfile
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for name, fl, view in READER_DIRS:
            zi = zipfile.ZipInfo(name, (1995, 6, 15, 0, 0, 0))
            zi.external_attr = 0o40755 << 16 | 0x10
            zi.extra = struct.pack("<HH", 0x2805, 8) + b"ZPIT" + struct.pack(">HH", fl, view)
            z.writestr(zi, b"")
        for name in ("Sent/Note", "Sent/Inner/Deep"):
            zi = zipfile.ZipInfo(name, (1995, 6, 15, 0, 0, 0))
            zi.extra = struct.pack("<HH", 0x2705, 12) + b"ZPIT" + b"TEXTttxt"
            z.writestr(zi, b"zipitmeta reader subject\r" * 20)
    return out.getvalue()


def reader(keep):
    work = R.work_tmp("zipit-")
    img = os.path.join(work, "zipwork.img")
    volume(img, work, [("Sentzip", "ZIP ", "ZIP ", sentinel_zip(), b"")])
    if not os.path.exists(ndd.BOOT):
        ndd.install()
    s = Session(ndd.BOOT, [img], os.path.join(SHOTS, "reader"))
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.mac.key("Escape")
        time.sleep(0.5)
        s.mac.key("z")
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("launched", wait=30.0)
        personalize(s)
        s.shot("personalized", wait=5.0)
        s.mac.click(*NOT_YET)
        s.shot("not-yet", wait=5.0)
        s.mac.command_key("o")                 # File > Open
        s.shot("open-dialog", wait=6.0)
        typed(s, "se")                         # Sentzip
        s.shot("open-selected", wait=2.0)
        s.mac.key("Return")
        s.shot("archive-open", wait=10.0)
        s.mac.click(*SENT_ROW)                 # Extract wants a selection
        s.shot("row-selected", wait=2.0)
        s.mac.command_key("e")                 # Zip > Extract
        s.shot("extract-dialog", wait=6.0)
        s.mac.key("Return")
        s.shot("extracting", wait=15.0)
        s.shot("extracted", wait=10.0)
        s.mac.command_key("q")
        s.shot("quit", wait=8.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")                 # Put Away: flush
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    for r in hfscat.records(open(img, "rb").read()):
        if r["kind"] == hfscat.DIR and len(r["path"]) > 1:
            f = hfscat.fields(r)
            print("zipitmeta: %-24s frFlags=%04x frView=%04x frRect=%s frLocation=%s"
                  % ("/".join(x.decode("mac-roman") for x in r["path"][1:]),
                     f["frFlags"], f["frView"], f["frRect"], f["frLocation"]))
    print("zipitmeta: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--writer", action="store_true")
    ap.add_argument("--reader", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if a.keep:
        os.environ["HARNESS_KEEP_IMAGES"] = "1"
    if a.probe:
        probe(a.keep)
    elif a.writer:
        writer(a.keep)
    elif a.reader:
        reader(a.keep)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

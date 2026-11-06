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
    zipitmeta.py --facts     four files (one forked, one commented), zipped:
                             fields, MacBinary, linefeeds, dates
    zipitmeta.py --facts2    the same with a resource-only file, linefeeds
                             turned off on two entries
    zipitmeta.py --facts-read   --facts2's archive extracted by ZipIt
    zipitmeta.py --segments  a 1 MB file in 385K segments

Results: DECISIONS.md 2026-11-06, *the field ZipIt 1.4 never wrote*,
*what ZipIt does with a Macintosh file*.

ZipIt 2.2.2 (PowerPC Carbon, CarbonLib 1.5 or later) has no mode here: it
was driven by hand under QEMU on `sitzip.CARBON_BOOT` (CarbonLib 1.6),
through `os9mouse` with `os9_paths()` pointing it at an overlay, transfer
disk and monitor of its own, and `os9_disk()` building that disk (ZipIt,
the writer's folders, the sentinel zip). The steps, all Command keys but
four clicks: Finder type-select and Cmd-O; personalize; "Not yet" (greyed
for a few seconds); Cmd-G, Navigation Services, Choose; Cmd-S; select a
row, Cmd-E, "Choose a Folder"; Cmd-Q; put the volume away. The frames are
in the vmac cache, `specimens/zipit/meta/os9/`.

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


def volume(img, work, subject_files=(), size_kb=4096):
    """ZipIt at the root, its Plug-ins beside it, and a folder `Subject`."""
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    make_volume(img, VOL, [], size_kb=size_kb)
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


# ------------------------------------------------------------------
# ZipIt 2.2.2, the only writer of 0x2805 seen: a PowerPC Carbon
# application (`Joy!peffpwpc`, CarbonLib imported with no minimum version),
# so Mac OS 9 under QEMU (tools/vmac/os9mouse.py), on an overlay, transfer
# disk and monitor socket of its own: the shared `sit5/` overlay carries
# other sessions' installs.
# ------------------------------------------------------------------

SEA2 = os.path.join(R.VMAC_HOME, "specimens", "zipit", "zipit-2.2.2.sea")
OS9DIR = os.path.join(os.path.dirname(R.VMAC_HOME), "zipit2")
OS9VOL = "zipwork"


def zipit2_app(work):
    """ZipIt 2.2.2's CFM executable, out of its bundle: (type, creator,
    data, rsrc)."""
    mb = os.path.join(work, "sea2")
    os.makedirs(mb)
    subprocess.run([cli(), "x", "-o", mb, SEA2], check=True, capture_output=True)
    sea = os.path.join(mb, "ZipIt 2.2.2.sea")
    out = os.path.join(work, "z2")
    os.makedirs(out)
    subprocess.run([cli(), "x", "-f", "Zip", "-o", out, sea], check=True,
                   capture_output=True)
    p = os.path.join(out, "ZipIt.app", "Contents", "MacOS", "ZipIt")
    data = open(p, "rb").read()
    if data[:12] != b"Joy!peffpwpc":
        raise SystemExit("zipitmeta: %s is not a PowerPC PEF" % p)
    return ("APPL", "ZIP ", data, open(p + ".rsrc", "rb").read())


def os9_disk(out, work):
    """The transfer disk: ZipIt, the writer's two folders with their DInfo
    planted, and the reader's sentinel zip, on an Apple_HFS partition
    behind the boot disk's own map (tools/vmac/mkapmdisk.py)."""
    import mkapmdisk
    import os9mouse
    vol = os.path.join(work, "vol.hfs")
    t, c, data, rsrc = zipit2_app(work)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    make_volume(vol, OS9VOL, [], size_kb=32 * 1024)
    try:
        run = lambda *a: subprocess.run(a, check=True, capture_output=True, env=env)  # noqa
        run("hmount", vol)
        for d in ("Subject", "Subject:Inner"):
            run("hmkdir", OS9VOL + ":" + d)
        items = [("ZipIt", t, c, data, rsrc),
                 ("Sentzip", "ZIP ", "ZIP ", sentinel_zip(), b"")] + \
            [(rel, ft, fc, fd, fr) for rel, ft, fc, fd, fr in WRITER_FILES]
        for i, (rel, ft, fc, fd, fr) in enumerate(items):
            p = os.path.join(work, "x%d.bin" % i)
            open(p, "wb").write(macbinary(rel.split("/")[-1], ft, fc, fd, fr))
            parent = ":".join(rel.split("/")[:-1])
            run("hcopy", "-m", p, OS9VOL + ":" + (parent + ":" if parent else ""))
        run("humount", vol)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    for path, dinfo in WRITER_DIRS:
        hfscat.patch(vol, tuple(x.encode("mac-roman") for x in (OS9VOL,) + path),
                     22, dinfo)
    start = mkapmdisk.find_hfs_start(os9mouse.MASTER)
    blocks = os.path.getsize(vol) // mkapmdisk.BLK
    with open(out, "wb") as f:
        f.write(mkapmdisk.clone_head(os9mouse.MASTER, start + blocks, OS9VOL,
                                     start, blocks))
        with open(vol, "rb") as v:
            shutil.copyfileobj(v, f)
    return start


def os9_volume(disk, start):
    """The transfer disk's HFS volume, as bytes, for hfscat."""
    import mkapmdisk
    with open(disk, "rb") as f:
        f.seek(start * mkapmdisk.BLK)
        return f.read()


def os9_paths():
    """Point os9mouse at this harness's own overlay, disk and socket."""
    import os9mouse
    os.makedirs(OS9DIR, exist_ok=True)
    os9mouse.OVERLAY = os.path.join(OS9DIR, "os9.qcow2")
    os9mouse.XFER = os.path.join(OS9DIR, "xfer.img")
    os9mouse.MON = os.path.join(OS9DIR, "mon.sock")
    os9mouse.SHOTS = os.path.join(OS9DIR, "shots")
    return os9mouse


# ------------------------------------------------------------------
# --facts: which field ZipIt 1.4 gives a file with a resource fork and one
# without, whether its MacBinary carries the Get Info comment, how an
# entry marked for linefeed conversion is stored, and which date a file's
# zip entry gets.
# ------------------------------------------------------------------

FACTS_FILES = [
    ("Subject/Binary", "????", "????", bytes(range(256)) * 8, b""),
    ("Subject/Forked", "TEXT", "ttxt", b"forked text\r" * 30, None),
    ("Subject/Plain", "TEXT", "ttxt", b"plain text\r" * 30, b""),
    ("Subject/Texty", "TEXT", "ttxt", b"line one\rline two\rline three\r" * 10, b""),
]
# Each file's creation and modification date, Mac seconds: all distinct,
# so a date on the zip entry or on an extracted file names its source.
FACTS_DATES = {"Binary": (0xA0000000, 0xA1000000), "Forked": (0xA2000000, 0xA3000000),
               "Plain": (0xA4000000, 0xA5000000), "Texty": (0xA6000000, 0xA7000000)}
COMMENT = "zipitmeta comment"
ADD_OPEN = (377, 178)                  # the Add dialog's Open, probe/14-add-dialog.png
ZIP_LINEFEEDS_Y = 155                  # Zip > Add/Strip Linefeeds
ROW0_Y, ROW_H = 96, 12                 # the archive window's rows, facts/15-archive-window.png
MB_X, LF_X = 432, 464                  # its MB and LF columns, the same frame


def facts_files():
    import diskdoubler
    out = []
    for rel, t, c, data, rsrc in FACTS_FILES:
        if rsrc is None:
            rsrc = diskdoubler.make_rsrc(b"\x1ezipitmeta: a resource fork")
        out.append((rel, t, c, data, rsrc))
    return out


def facts(keep, second=False):
    """`second`: also a resource-only file `Resy`, no Return after Add
    All, MacBinary forced on `Forked` and linefeeds turned off on `Plain`
    by clicking their MB and LF cells."""
    work = R.work_tmp("zipit-")
    img = os.path.join(work, "zipwork.img")
    files = facts_files()
    if second:
        import diskdoubler
        files.append(("Subject/Resy", "rsrc", "RSED", b"",
                      diskdoubler.make_rsrc(b"\x1ezipitmeta: resources only")))
    volume(img, work, files, size_kb=8192)
    for name, (cr, md) in FACTS_DATES.items():
        key = tuple(x.encode("mac-roman") for x in (VOL, "Subject", name))
        hfscat.patch(img, key, 44, struct.pack(">II", cr, md))
    if not os.path.exists(ndd.BOOT):
        ndd.install()
    s = Session(ndd.BOOT, [img], os.path.join(SHOTS, "facts2" if second else "facts"))
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        # The Get Info comment, typed into the Finder's own Get Info window.
        s.mac.key("Escape")
        time.sleep(0.5)
        typed(s, "su")
        s.mac.command_key("o")
        s.shot("subject", wait=6.0)
        for who in (("f", "r") if second else ("f",)):
            s.mac.key("Escape")
            time.sleep(0.5)
            typed(s, who)
            s.mac.command_key("i")
            s.shot("get-info-" + who, wait=5.0)
            for ch in COMMENT:
                s.mac.key("space" if ch == " " else ch)
                time.sleep(0.12)
            s.shot("commented-" + who, wait=2.0)
            s.mac.command_key("w")             # the info window: the comment is kept
            s.shot("info-closed-" + who, wait=3.0)
        s.mac.command_key("w")                 # the Subject window
        s.shot("subject-closed", wait=3.0)
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
        s.mac.command_key("g")
        s.shot("add-dialog", wait=6.0)
        typed(s, "su")
        s.mac.click(*ADD_OPEN)                 # into Subject
        s.shot("in-subject", wait=4.0)
        s.mac.command_key("a")                 # Add All
        s.shot("added-all", wait=15.0)
        if not second:
            s.mac.key("Return")                # pressed Add again: Binary twice
            s.shot("after-return", wait=4.0)
        s.mac.click(*ADD_DONE)
        s.shot("archive-window", wait=5.0)
        if second:
            # Rows: Binary, Forked, Plain, Resy, Texty. Linefeeds by the
            # menu on a selected row; MacBinary by its cell once Forked
            # converts no linefeeds (ZipIt refuses both on one entry).
            for row, tag in ((1, "forked"), (2, "plain")):
                s.mac.click(60, ROW0_Y + row * ROW_H)
                time.sleep(1.0)
                s.menu(MENUS["zip"], ZIP_LINEFEEDS_Y, "pick-lf-" + tag)
                s.mac.click(250, 185)                  # the pointer off the columns, inside the list
                s.shot("lf-" + tag, wait=3.0)
            s.mac.click(MB_X, ROW0_Y + 1 * ROW_H)
            s.mac.click(250, 185)
            s.shot("forked-mb", wait=3.0)
        save_as(s, "Azip", "a")
        s.mac.command_key("q")
        s.shot("quit", wait=8.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    report_facts(img, s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def zip_entries(blob):
    """Every central-directory record: name, made-by, flags, method, DOS
    time and date, internal and external attributes, extra fields
    (APPNOTE.TXT 4.3.12)."""
    out, i = [], 0
    while True:
        i = blob.find(b"PK\x01\x02", i)
        if i < 0 or i + 46 > len(blob):
            return out
        (vmade, vneed, flags, method, mtime, mdate, crc, csz, usz, nl, xl,
         cl, disk, iattr, eattr, loff) = struct.unpack("<HHHHHHIIIHHHHHII",
                                                      blob[i + 4:i + 46])
        name = blob[i + 46:i + 46 + nl].decode("mac-roman")
        ex = blob[i + 46 + nl:i + 46 + nl + xl]
        fields, k = [], 0
        while k + 4 <= len(ex):
            eid, sz = struct.unpack("<HH", ex[k:k + 4])
            fields.append((eid, ex[k + 4:k + 4 + sz]))
            k += 4 + sz
        out.append(dict(name=name, made=vmade, flags=flags, method=method,
                        dos=(mdate, mtime), iattr=iattr, eattr=eattr,
                        loff=loff, csz=csz, usz=usz, fields=fields))
        i += 4


def report_facts(img, shots):
    import zlib
    vol = open(img, "rb").read()
    for r in hfscat.records(vol):
        if r["kind"] != hfscat.DIR and len(r["path"]) == 3 and r["path"][1] == b"Subject":
            f = hfscat.fields(r)
            print("zipitmeta: catalog %-8s crdat=%08x mddat=%08x" % (
                r["path"][2].decode(), f["crdat"], f["mddat"]))
    got = ndd.read_forks(img)
    for path, (t, c, data, rsrc) in sorted(got.items()):
        if data[:2] != b"PK":
            continue
        open(os.path.join(shots, path[-1]), "wb").write(data)
        print("zipitmeta: %s, %d B, kept" % ("/".join(path), len(data)))
        for e in zip_entries(data):
            d, t_ = e["dos"]
            dos = "%04d-%02d-%02d %02d:%02d:%02d" % (1980 + (d >> 9), (d >> 5) & 15, d & 31,
                                                    t_ >> 11, (t_ >> 5) & 63, (t_ & 31) * 2)
            print("zipitmeta:   %-16s made=%04x flags=%04x method=%d %s iattr=%04x "
                  "eattr=%08x %d->%d" % (e["name"], e["made"], e["flags"], e["method"],
                                         dos, e["iattr"], e["eattr"], e["usz"], e["csz"]))
            for eid, f in e["fields"]:
                print("zipitmeta:     %04x %s" % (eid, f.hex()))
            lh = e["loff"]
            nl, xl = struct.unpack("<HH", data[lh + 26:lh + 30])
            body = data[lh + 30 + nl + xl:lh + 30 + nl + xl + e["csz"]]
            raw = body if e["method"] == 0 else (
                zlib.decompress(body, -15) if e["method"] == 8 else b"")
            if raw[:2] == b"\0" + bytes([len(e["name"].split("/")[-1])]) or \
                    (len(raw) >= 128 and raw[0] == 0 and raw[74] == 0):
                dl, rl = struct.unpack(">II", raw[83:91])
                cl = struct.unpack(">H", raw[99:101])[0]
                print("zipitmeta:     MacBinary: data %d rsrc %d comment length %d, "
                      "header byte 122 (version) %d, 123 %d" % (dl, rl, cl, raw[122], raw[123]))
                end = 128 + ((dl + 127) // 128) * 128 + ((rl + 127) // 128) * 128
                print("zipitmeta:     after the forks: %r" % raw[end:end + 64])
            elif raw:
                print("zipitmeta:     data starts %r" % raw[:40])
    print("zipitmeta: screenshots in %s" % shots)


# ------------------------------------------------------------------
# --facts-read: ZipIt 1.4 extracting the archive --facts2 made (kept as
# specimens/zipit/meta/azip-facts2.zip): which dates the files get, and
# what the text attribute does to the data.
# ------------------------------------------------------------------

FACTS_ZIP = os.path.join(SHOTS, "azip-facts2.zip")


def facts_read(keep):
    work = R.work_tmp("zipit-")
    img = os.path.join(work, "zipwork.img")
    volume(img, work, [("Xdir/Azip", "ZIP ", "ZIP ", open(FACTS_ZIP, "rb").read(), b"")],
           size_kb=8192)
    if not os.path.exists(ndd.BOOT):
        ndd.install()
    s = Session(ndd.BOOT, [img], os.path.join(SHOTS, "facts-read"))
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
        s.mac.command_key("o")                 # File > Open: Standard File
        s.shot("open-dialog", wait=6.0)
        typed(s, "x")                          # Xdir
        s.mac.key("Return")                    # opens the folder
        s.shot("in-xdir", wait=3.0)
        typed(s, "a")
        s.mac.key("Return")                    # opens Azip
        s.shot("archive-open", wait=10.0)
        s.mac.click(60, ROW0_Y + 17)           # a row, then Select All
        s.mac.command_key("a")
        s.shot("all-selected", wait=2.0)
        s.mac.command_key("e")
        s.shot("extract-dialog", wait=6.0)
        s.mac.key("Return")
        s.shot("extracting", wait=15.0)
        s.shot("extracted", wait=10.0)
        s.mac.command_key("q")
        s.shot("quit", wait=8.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    vol = open(img, "rb").read()
    got = ndd.read_forks(img)
    for r in hfscat.records(vol):
        if r["kind"] == hfscat.DIR or b"Desktop" in r["path"][-1]:
            continue
        p = r["path"]
        if p[1] in (b"Plug-ins", b"ZipIt") or p[-1] == b"Azip":
            continue
        f = hfscat.fields(r)
        key = tuple(x.decode("mac-roman") for x in p[1:])
        d, rs = got.get(key, (None, None, b"", b""))[2:]
        print("zipitmeta: %-14s %s/%s fdFlags=%04x crdat=%08x mddat=%08x data %d %r rsrc %d"
              % ("/".join(key), f["type"].decode("mac-roman"), f["creator"].decode("mac-roman"),
                 f["fdFlags"], f["crdat"], f["mddat"], len(d), d[:24], len(rs)))
    print("zipitmeta: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------
# --segments: what a segmented ZipIt archive is. Its strings say it only
# segments archives whose entries are all deflated, asks "Save segment #%d
# as:" for each, and wants the FINAL segment opened to read one.
# ------------------------------------------------------------------

ZIP_SEGSIZE_Y = 171                    # Zip > Set Segment Size…
# The dialog is drawn centred, not at DLOG 151's rectangle: its "Mac
# single sided (385K)" radio and OK, measured off segments/11-segsize-dialog.png.
SEG_385K = (157, 185)
SEG_OK = (315, 231)


def segments(keep):
    import hashlib
    big = b"".join(hashlib.sha256(b"zipitmeta %d" % k).digest()
                   for k in range(1024 * 1024 // 32))
    work = R.work_tmp("zipit-")
    img = os.path.join(work, "zipwork.img")
    volume(img, work, [("Subject/Big", "????", "????", big, b"")], size_kb=8192)
    if not os.path.exists(ndd.BOOT):
        ndd.install()
    s = Session(ndd.BOOT, [img], os.path.join(SHOTS, "segments"))
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
        s.mac.command_key("g")
        s.shot("add-dialog", wait=6.0)
        typed(s, "su")
        s.mac.click(*ADD_OPEN)
        s.shot("in-subject", wait=4.0)
        s.mac.command_key("a")                 # Add All: Big
        s.shot("added", wait=30.0)
        s.mac.click(*ADD_DONE)
        s.shot("archive-window", wait=5.0)
        s.menu(MENUS["zip"], ZIP_SEGSIZE_Y, "pick-segsize")
        s.shot("segsize-dialog", wait=4.0)
        s.mac.click(*SEG_385K)
        s.shot("segsize-385", wait=2.0)
        s.mac.click(*SEG_OK)
        s.shot("segsize-set", wait=3.0)
        s.mac.command_key("s")
        for n in range(1, 6):
            s.shot("save-%d" % n, wait=8.0)
            s.mac.command_key("a")
            typed(s, "Seg%d" % n)
            s.mac.key("Return")
            s.shot("saving-%d" % n, wait=25.0)
        s.mac.command_key("q")
        s.shot("quit", wait=8.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    got = ndd.read_forks(img)
    for path, (t, c, data, rsrc) in sorted(got.items()):
        if path[0] in ("Plug-ins",) or path[-1] in ("ZipIt", "Big"):
            continue
        sig = data[:4]
        eocd = data.rfind(b"PK\x05\x06")
        tail = ""
        if eocd >= 0:
            (disk, cddisk, n_here, n_all, cdsize, cdoff) = struct.unpack(
                "<HHHHII", data[eocd + 4:eocd + 20])
            tail = " EOCD: this disk %d, CD on disk %d, %d/%d entries, CD %d B at %d" % (
                disk, cddisk, n_here, n_all, cdsize, cdoff)
        keptp = os.path.join(s.shots, path[-1])
        open(keptp, "wb").write(data)
        print("zipitmeta: %-14s %s/%s %8d B starts %s%s" % (
            "/".join(path), t, c, len(data), sig.hex(), tail))
    print("zipitmeta: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--writer", action="store_true")
    ap.add_argument("--reader", action="store_true")
    ap.add_argument("--facts", action="store_true")
    ap.add_argument("--facts2", action="store_true")
    ap.add_argument("--facts-read", action="store_true")
    ap.add_argument("--segments", action="store_true")
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
    elif a.facts:
        facts(a.keep)
    elif a.facts2:
        facts(a.keep, second=True)
    elif a.facts_read:
        facts_read(a.keep)
    elif a.segments:
        segments(a.keep)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

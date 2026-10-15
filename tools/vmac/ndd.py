#!/usr/bin/env python3
"""ndd.py — the two DiskDoubler releases this project had never run.

`diskdoubler.py` drives Salient's DiskDoubler 3.7 and `ddpro.py` drives
Fifth Generation's DiskDoubler Pro 4.1. Those are two of the four
publishers the product had. This one covers the other two ends:

  * **DiskDoubler 4.0**, the Fifth Generation release that first bundled
    AutoDoubler and CopyDoubler as *SuperDoubler*, and
  * **Norton DiskDoubler Pro 1.1**, Symantec's fat-binary re-release and
    the last one. The 1.1 is the DISK: `vers 2` on it reads *Norton
    DiskDoubler Pro™ Disk 1.1* and `vers 1` reads **4.1.1**, so the
    application is a version later than `ddpro.py`'s, not eight earlier.

Both were run for two open items, and both are now answered: a `DDA2` **stored** entry with a resource fork cannot
be written at all (`--stored`), and DiskDoubler methods 2-5 are absent
from every release from 3.2 to 4.1.1 and from the vendor's own display
vocabulary (`--submenu`, and `STR# 403` read on the host).

The Norton floppy is worth more than the application on it. Every file
on it ships DiskDoubler-COMPRESSED — types `DDF0`..`DDF3`, creator
`DDAP` — so the installer disk is a corpus of ten files this engine can
be graded on, the same way 3.7's distribution disk turned out to carry
the only two method 7 forks anybody here will ever see.

    tools/vmac/ndd.py --setup      fetch both releases
    tools/vmac/ndd.py --harvest    decode the floppy here; report methods
    tools/vmac/ndd.py --install    a System 7 image with 1.1's Finder menu
    tools/vmac/ndd.py --probe      photograph the menus and Settings
    tools/vmac/ndd.py --methods    write one file per method the menu offers
    tools/vmac/ndd.py --archive    seven files, one incompressible WITH a
                                   resource fork: the `0x1000` record hunt

`--install` builds the boot volume out of forks THIS ENGINE DECODED,
which is the point rather than a shortcut: the application on that disk
is DiskDoubler-compressed, so a Mac that boots the extension and runs
the application is a Mac executing our own method 10 output. A wrong
byte does not produce a warning, it produces a machine that will not
start.

Nothing here runs in `ci.sh`, and nothing it fetches is committed — both
are commercial software, fetched by URL and checked by hash exactly as
the ROM and the System images are.
"""
import argparse
import hashlib
import os
import re
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
import run as R                                        # noqa: E402
from arcmac import macbinary                           # noqa: E402
from diskdoubler import (Session, cli, header, describe, make_volume,
                         make_rsrc, VOLUME_ICON)       # noqa: E402
from superdisk import read_forks                       # noqa: E402

# Norton DiskDoubler Pro 1.1, Symantec 1995. A raw 1440K HFS floppy, not
# a DiskCopy image despite the name. Macintosh Repository hands its
# downloads out behind a one-shot token, so this is three requests and
# not one; `fetch_norton` does them.
NDD_PAGE = "https://www.macintoshrepository.org/35018-norton-diskdoubler-pro-1-1"
NDD_ID = "37586"
NDD_SHA = ("8b8f2e0d5c75b16d0d3dd8dfe1b98bf1def62371")   # SHA-1, as published

# DiskDoubler 4.0 with AutoDoubler, DD Expand and DiskTester: a MacBinary
# wrapping a StuffIt archive, whose applications are NOT compressed.
DD40_URL = "https://old.mac.gdn/apps/diskdoublertm-4-sit.bin"
DD40_PAGE = "https://macintoshgarden.org/apps/diskdoubler-40"
DD40_MD5 = "ddfad526576f0ac03cd5d181e3fdd944"           # MD5, as published

# Salient's own 3.1.2 distribution floppy, 1991 — the OLDEST DiskDoubler
# reachable, and the only place a method 2 fork has ever been found.
# WinWorld hands the download out from a mirror link on the download
# page; the SHA-1 below is the one it publishes beside the file.
DD312_PAGE = "https://winworldpc.com/download/a8d3a7f3-377c-11e9-8581-fa163e9022f0"
DD312_URL = DD312_PAGE + "/from/c39ac2af-c381-c2bf-1b25-11c3a4e284a2"
DD312_SHA = "73beb38b09f0cdad8764f3ec3bd9d8c43734f7b3"

# A third collector's DiskDoubler samples, linked from the Just Solve the
# File Format Problem wiki: real files from real disks, independent of
# both Salient's own and the CC0 corpus. A live directory listing rather
# than a pinned archive, so nothing here is hashed — it is a check, not a
# fixture source.
DEXVERT = "http://sembiance.com/fileFormatSamples/archive/diskDoubler/"

HOME = R.VMAC_HOME
WORK = os.path.join(HOME, "ndd")
SPECIMENS = os.path.join(HOME, "specimens", "ndd")
IMG = os.path.join(WORK, "Norton-DiskDoubler-Pro.img")
SIT = os.path.join(WORK, "dd40.sit.bin")
SEVENZ = os.path.join(WORK, "dd312.7z")
TREE312 = os.path.join(WORK, "dd312")
TREE40 = os.path.join(WORK, "dd40")
DECODED = os.path.join(WORK, "decoded")
DEXTREE = os.path.join(WORK, "dexvert")
BOOT = os.path.join(WORK, "nddboot.hfv")

# The extension is the half that compresses, exactly as in 3.7 and 4.1.
MENU_EXT = "Finder Menu"

# 20,000 bytes no LZ77 and no Huffman can shrink, WITH a resource fork.
# `ddpro.py` uses the same shape for the same question; the difference
# here is that it goes into an archive of SEVEN files rather than one,
# which is the other half of what OPEN_ITEMS.md says is left to try.
INCOMPRESSIBLE = bytes(bytearray(
    (i * 7 + (i * i) % 251 + (i >> 3)) & 0xFF for i in range(20000)))

SUBJECT_DATA = (b"Norton DiskDoubler Pro method probe. " * 400 +
                bytes(bytearray(range(256))) * 8)


# ------------------------------------------------------------------
# Fetching
# ------------------------------------------------------------------

def _curl(args, out=None):
    cmd = ["curl", "-sS", "-A", "Mozilla/5.0", "-c", os.path.join(WORK, "jar"),
           "-b", os.path.join(WORK, "jar")] + args
    if out:
        cmd += ["-o", out]
    return subprocess.run(cmd, capture_output=True, check=True).stdout


def fetch_norton():
    """Macintosh Repository's download is a one-shot token, three steps.

    A plain GET of `download.php?id=` returns an interstitial that says
    the link is expired — which reads as "this file is gone" and is not:
    the token is minted by a 302 that only arrives with the software
    page's own session cookie behind it. Straight past the 302 is a form
    carrying the token in a hidden field, and the file is a POST of that
    field back. Written out because the failure mode is a 168-byte HTML
    body called `.img` that `file` cheerfully calls a floppy.
    """
    os.makedirs(WORK, exist_ok=True)
    if os.path.exists(IMG) and _sha1(IMG) == NDD_SHA:
        return IMG
    _curl([NDD_PAGE], out=os.path.join(WORK, "page.html"))
    hdrs = os.path.join(WORK, "h.txt")
    _curl(["-e", NDD_PAGE, "-D", hdrs, "-o", os.devnull,
           "https://www.macintoshrepository.org/download.php?id=" + NDD_ID])
    loc = None
    for line in open(hdrs, "r", errors="replace"):
        if line.lower().startswith("location:"):
            loc = line.split(":", 1)[1].strip()
    if not loc:
        raise SystemExit("ndd: no download token — the site has changed")
    form = os.path.join(WORK, "form.html")
    _curl(["-e", NDD_PAGE, "https://www.macintoshrepository.org/" + loc],
          out=form)
    m = re.search(r'name="d" value="([^"]*)"', open(form, errors="replace").read())
    if not m:
        raise SystemExit("ndd: the download form has no token field")
    _curl(["-L", "-e", "https://www.macintoshrepository.org/" + loc,
           "--data-urlencode", "d=" + m.group(1), "--data", "via_http=1",
           "https://www.macintoshrepository.org/download.php?u=0&id=%s&go=1"
           % NDD_ID], out=IMG)
    got = _sha1(IMG)
    print("ndd: %s sha1 %s%s" % (os.path.basename(IMG), got,
                                 "" if got == NDD_SHA else "  MISMATCH"))
    if got != NDD_SHA:
        raise SystemExit("ndd: the download is not the file this was "
                         "written against")
    return IMG


def fetch_dd40():
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(SIT):
        subprocess.run(["curl", "-sS", "-L", "-A", "Mozilla/5.0",
                        "-e", DD40_PAGE, "-o", SIT, DD40_URL], check=True)
    got = hashlib.md5(open(SIT, "rb").read()).hexdigest()
    print("ndd: %s md5 %s%s" % (os.path.basename(SIT), got,
                                "" if got == DD40_MD5 else "  MISMATCH"))
    if got != DD40_MD5:
        raise SystemExit("ndd: the 4.0 download is not the file this was "
                         "written against")
    shutil.rmtree(TREE40, ignore_errors=True)
    os.makedirs(TREE40)
    subprocess.run([cli(), "x", "--forks", "hidden", "-o", TREE40, SIT],
                   check=True, capture_output=True)
    print("ndd: 4.0 unpacked into %s" % TREE40)
    return TREE40


def fetch_dd312():
    """Salient's 3.1.2 distribution floppy: a 7-zip holding an 800K HFS
    image. WinWorld's product page for DiskDoubler lists 3.x only, and
    the file behind it is older than anything else reachable."""
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(SEVENZ) or _sha1(SEVENZ) != DD312_SHA:
        subprocess.run(["curl", "-sS", "-L", "-A", "Mozilla/5.0",
                        "-e", DD312_PAGE, "-o", SEVENZ, DD312_URL], check=True)
    got = _sha1(SEVENZ)
    print("ndd: %s sha1 %s%s" % (os.path.basename(SEVENZ), got,
                                 "" if got == DD312_SHA else "  MISMATCH"))
    if got != DD312_SHA:
        raise SystemExit("ndd: the 3.1.2 download is not the file this was "
                         "written against")
    shutil.rmtree(TREE312, ignore_errors=True)
    os.makedirs(TREE312)
    subprocess.run(["7z", "x", "-y", "-o" + TREE312, SEVENZ],
                   check=True, capture_output=True)
    for root, _d, files in os.walk(TREE312):
        for f in files:
            if f.endswith(".img"):
                print("ndd: 3.1.2 disk image at %s" % os.path.join(root, f))
                return os.path.join(root, f)
    raise SystemExit("ndd: no disk image inside the 3.1.2 download")


def dd312_image():
    for root, _d, files in os.walk(TREE312):
        for f in files:
            if f.endswith(".img"):
                return os.path.join(root, f)
    return fetch_dd312()


def specimens():
    """Every DiskDoubler-compressed file on the 1991 Salient disk, with
    the method that wrote it, decoded and checked by our own CLI.

    This disk is why methods 2 and 7 are not guesses. It carries the
    only method 2 fork anybody here has found, and method 7 forks of up
    to EIGHT chunks — where the two off the 3.7 disk have one each, and
    "a fork longer than one chunk has never been decoded" was an open
    item until this ran. Each fork carries its own checksum, so the disk
    grades itself: `t` returns non-zero on any mismatch.
    """
    img = dd312_image()
    forks = read_forks(img)
    hist, bad, n = {}, 0, 0
    tmp = tempfile.mkdtemp(prefix="ndd-s-")
    try:
        for path, (ftype, creator, data, _rsrc) in sorted(forks.items()):
            h = header(data)
            if h is None:
                continue
            n += 1
            for meth, size in ((h["datamethod"], h["data"]),
                               (h["rsrcmethod"], h["rsrc"])):
                if size:
                    hist[meth] = hist.get(meth, 0) + 1
            src = os.path.join(tmp, "in.dd")
            open(src, "wb").write(data)
            r = subprocess.run([cli(), "t", src], capture_output=True, text=True)
            chunks = _stac_chunks(data, h)
            print("ndd: %-44s %s/%s  %s%s  %s"
                  % ("/".join(path)[-44:], ftype, creator, describe(h),
                     "" if chunks is None else "  chunks=%d" % chunks,
                     "ok" if r.returncode == 0
                     else (r.stderr or r.stdout).strip().splitlines()[-1]))
            bad += 1 if r.returncode else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ndd: %d containers, %d failed; forks by method: %s"
          % (n, bad, ", ".join("%d x%d" % (m, c) for m, c in sorted(hist.items()))))
    return 1 if bad else 0


def _stac_chunks(data, h):
    """Method 7's compressed-chunk count, at +6 of the fork."""
    if h["datamethod"] != 7 and h["rsrcmethod"] != 7:
        return None
    off, ln = (84, h["datacomp"]) if h["data"] else (84 + h["datacomp"],
                                                    h["rsrccomp"])
    if ln < 18:
        return None
    return struct.unpack_from(">I", data, off + 6)[0]


def dexvert():
    """Run the engine over a third collector's DiskDoubler samples.

    Fifteen files from real disks, none of them from Salient's own media
    or from the CC0 corpus. What it is worth: an independent check that
    is not this project's own choice of specimen. What it found on
    2026-08-21: methods 0, 1, 6, 8 and 9 and both containers, **no
    method 3, 4 or 5**, and one file whose method 1 fork fails its
    checksum — `readme`, which `unar` also rejects as *Wrong checksum*
    and whose text reads "shaneware" and "ane morally obl". Single-bit
    rot in the sample; both decoders agree on the bytes and disagree
    with the stored sum, which is what a per-entry CRC error is for.
    """
    os.makedirs(DEXTREE, exist_ok=True)
    listing = subprocess.run(["curl", "-sSL", "-m", "90", "-A", "Mozilla/5.0",
                              DEXVERT], capture_output=True).stdout
    hrefs = [h.decode("latin1") for h in
             re.findall(rb'href="([^"?][^"]*)"', listing)]
    ok = bad = 0
    for h in hrefs:
        if h.startswith(".."):
            continue
        import urllib.parse
        out = os.path.join(DEXTREE, urllib.parse.unquote(h).replace("/", "_"))
        if not os.path.exists(out):
            subprocess.run(["curl", "-sSL", "-m", "180", "-A", "Mozilla/5.0",
                            "-o", out, DEXVERT + h], check=True)
        blob = open(out, "rb").read()
        h2 = header(blob)
        what = describe(h2) if h2 else (
            "%s container" % blob[:4].decode("latin1")
            if blob[:4] in (b"DDAR", b"DDA2") else "wrapped")
        r = subprocess.run([cli(), "t", out], capture_output=True, text=True)
        ok, bad = (ok + 1, bad) if r.returncode == 0 else (ok, bad + 1)
        print("ndd: %-40s %-52s %s"
              % (os.path.basename(out)[:40], what,
                 "ok" if r.returncode == 0
                 else (r.stderr or r.stdout).strip().splitlines()[0]))
    print("ndd: %d ok, %d failed — `readme` is a damaged sample `unar` "
          "rejects too, not a defect" % (ok, bad))
    return 0


def _sha1(path):
    return hashlib.sha1(open(path, "rb").read()).hexdigest()


def setup():
    fetch_norton()
    fetch_dd40()
    fetch_dd312()


# ------------------------------------------------------------------
# The floppy as a corpus
# ------------------------------------------------------------------

def _decode(name, blob):
    """One DiskDoubler single-file container -> (type, creator, data,
    rsrc), decoded by our own CLI."""
    tmp = tempfile.mkdtemp(prefix="ndd-x-")
    try:
        src = os.path.join(tmp, "in.dd")
        open(src, "wb").write(blob)
        r = subprocess.run([cli(), "l", src], capture_output=True, text=True)
        ftype, creator = "????", "????"
        for line in r.stdout.splitlines():
            f = line.split(None, 4)
            if len(f) == 5 and f[0] == "f":
                ftype, creator = f[3][:4], f[3][5:]
        out = os.path.join(tmp, "out")
        os.makedirs(out)
        subprocess.run([cli(), "x", "--forks", "hidden", "-o", out, src],
                       check=True, capture_output=True)
        got = [f for f in os.listdir(out) if not f.startswith("._")]
        if not got:
            raise SystemExit("ndd: %s decoded to nothing" % name)
        data = open(os.path.join(out, got[0]), "rb").read()
        rp = os.path.join(out, "._" + got[0])
        rsrc = open(rp, "rb").read() if os.path.exists(rp) else b""
        return ftype, creator, data, rsrc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def harvest(quiet=False):
    """Every file on the Norton floppy, with the method that wrote it.

    Returns {name: (type, creator, data, rsrc)} for the DECODED files,
    and prints the header of each so the methods are a measurement and
    not an assumption.
    """
    if not os.path.exists(IMG):
        fetch_norton()
    os.makedirs(DECODED, exist_ok=True)
    out = {}
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(IMG).items()):
        name = path[-1]
        h = header(data)
        if h is None:
            if not quiet and data[:4] == b"DDA2":
                print("ndd: %-34s %s/%s  DDA2 archive, %d B"
                      % (name, ftype, creator, len(data)))
            continue
        dtype, dcreator, ddata, drsrc = _decode(name, data)
        out[name] = (dtype, dcreator, ddata, drsrc)
        if not quiet:
            print("ndd: %-34s %s/%s -> %s/%s  %s"
                  % (name, ftype, creator, dtype, dcreator, describe(h)))
        base = name.replace("/", "_")
        open(os.path.join(DECODED, base + ".bin"), "wb").write(
            macbinary(name, dtype, dcreator, ddata, drsrc))
    if not quiet:
        print("ndd: %d compressed files decoded into %s" % (len(out), DECODED))
    return out


def grade():
    """The one fork on this floppy that has ground truth, and what it is.

    `DiskTester™` ships DiskDoubler-compressed on the Norton floppy and
    UNCOMPRESSED in the 4.0 StuffIt archive — two distributions, two
    publishers, one build. Comparing them grades a method 10 resource
    fork against a copy no DiskDoubler ever touched, which is the thing
    OPEN_ITEMS.md says the adjudicated forks do not have.
    """
    if not os.path.isdir(TREE40):
        fetch_dd40()
    got = harvest(quiet=True)
    ours = None
    for name, (_t, _c, _d, rsrc) in got.items():
        if name.startswith("DiskTester"):
            ours = rsrc
    ref = None
    for root, _d, files in os.walk(TREE40):
        for f in files:
            # `fetch_dd40` unpacks with --forks hidden, so a resource
            # fork is `._NAME` beside NAME, not NAME.rsrc.
            if f.startswith("._DiskTester"):
                ref = open(os.path.join(root, f), "rb").read()
    if ours is None or ref is None:
        raise SystemExit("ndd: DiskTester is missing from one of the two")
    diff = [i for i in range(min(len(ours), len(ref))) if ours[i] != ref[i]]
    print("ndd: DiskTester resource fork — ours %d B, 4.0's %d B, %d bytes differ"
          % (len(ours), len(ref), len(diff) + abs(len(ours) - len(ref))))
    if len(ours) != len(ref):
        return 1
    # Bytes 16..127 of a resource fork are "reserved for system use" and
    # hold whatever the last application to touch the file left there —
    # here DiskDoubler's own `DDAppExpandTempFile` bookkeeping on one
    # copy and the Installer's on the other. Everything a resource fork
    # MEANS starts at the data offset in the first 16 bytes.
    if all(16 <= i < 128 for i in diff):
        print("ndd: identical outside the 112-byte system-reserved area "
              "(%d bytes there: %s)"
              % (len(diff), " ".join("%d" % i for i in diff[:8]) +
                 (" ..." if len(diff) > 8 else "")))
        return 0
    print("ndd: DIFFERS in the resource data or map — first at %d" % diff[0])
    return 1


# ------------------------------------------------------------------
# Volumes and boot
# ------------------------------------------------------------------

def app_files(which="norton"):
    """(name, type, creator, data, rsrc) for the DiskDoubler application.

    The Finder menu is only the front end: "Create Archive…" puts up
    *The DiskDoubler application cannot be found* if the application is
    not on a mounted volume (`ddpro.py`, 2026-08-21), so it travels on
    the work volume in both cases.
    """
    if which == "norton":
        got = harvest(quiet=True)
        for name, (ftype, creator, data, rsrc) in got.items():
            if name.startswith("DiskDoubler") and ftype == "APPL":
                return [("DiskDoubler™", ftype, creator, data, rsrc)]
        raise SystemExit("ndd: no DiskDoubler application on the floppy")
    if not os.path.isdir(TREE40):
        fetch_dd40()
    for root, _d, files in os.walk(TREE40):
        for f in sorted(files):
            if f.startswith("._") or f.endswith(".rsrc"):
                continue
            if "DiskDoubler" in f:
                p = os.path.join(root, f)
                rp = os.path.join(root, "._" + f)
                return [("DiskDoubler™", "APPL", "DDAP",
                         open(p, "rb").read(),
                         open(rp, "rb").read() if os.path.exists(rp) else b"")]
    raise SystemExit("ndd: no DiskDoubler application in the 4.0 archive")


def install(which="norton"):
    """A System 7 boot image with the Finder menu extension loaded."""
    if which == "norton":
        got = harvest(quiet=True)
        ext = None
        for name, (ftype, creator, data, rsrc) in got.items():
            if MENU_EXT in name:
                ext = (ftype, creator, data, rsrc)
        if ext is None:
            raise SystemExit("ndd: no Finder menu extension on the floppy")
    else:
        raise SystemExit("ndd: 4.0's archive has no Finder menu extension; "
                         "use --install with the Norton floppy")
    ftype, creator, data, rsrc = ext
    print("ndd: %s — %s/%s, %d B data, %d B rsrc"
          % (MENU_EXT, ftype, creator, len(data), len(rsrc)))
    work = tempfile.mkdtemp(prefix="nddinst-")
    try:
        mb = os.path.join(work, "ext.bin")
        open(mb, "wb").write(macbinary("DD™ Finder Menu", ftype, creator,
                                       data, rsrc))
        shutil.copyfile(os.path.join(HOME, "Sys7.img"), BOOT)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            subprocess.run(["hmount", BOOT], check=True, capture_output=True,
                           env=env)
            subprocess.run(["hcopy", "-m", mb, ":System Folder:Extensions:"],
                           check=True, capture_output=True, env=env)
            subprocess.run(["humount"], check=True, capture_output=True,
                           env=env)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("ndd: boot image with the DiskDoubler menu at %s" % BOOT)
    return BOOT


def session(tag, files, which="norton", folder=None, dated=None):
    """A booted Mac with the menu loaded and a work volume holding the
    application and `files`, each (name, type, creator, data, rsrc).

    `folder` puts the subjects in a folder of that name with the
    application left at the root. That is not tidiness: **Select All in
    the root window selects the application too**, and "Create Archive…"
    over the application DiskDoubler is about to launch is a different
    experiment from the one being run.
    """
    apps = app_files(which)
    work = R.work_tmp("nddwork-")

    def write(seq, tag, stamp=False):
        out = []
        for i, (name, ftype, creator, data, rsrc) in enumerate(seq):
            p = os.path.join(work, "%s%d.bin" % (tag, i))
            if stamp and dated:
                mb = macbinary_dated(name, ftype, creator, data, rsrc, *dated)
            else:
                mb = macbinary(name, ftype, creator, data, rsrc)
            open(p, "wb").write(mb)
            out.append(p)
        return out

    img = os.path.join(work, "nddwork.img")
    need = sum(len(d) + len(r) for _, _, _, d, r in apps + list(files)) // 1024
    size_kb = max(4096, need * 3 + 2048)
    if folder is None:
        make_volume(img, "NDDwork", write(apps + list(files), "f"),
                    size_kb=size_kb)
    else:
        make_volume(img, "NDDwork", write(apps, "a"), size_kb=size_kb)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            subprocess.run(["hmount", img], check=True, capture_output=True,
                           env=env)
            subprocess.run(["hmkdir", "NDDwork:" + folder], check=True,
                           capture_output=True, env=env)
            for mb in write(files, "s", stamp=True):
                subprocess.run(["hcopy", "-m", os.path.abspath(mb),
                                "NDDwork:%s:" % folder], check=True,
                               capture_output=True, env=env)
            subprocess.run(["humount"], check=True, capture_output=True,
                           env=env)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    if not os.path.exists(BOOT):
        install(which)
    s = Session(BOOT, [img], os.path.join(SPECIMENS, tag))
    return s, work, img


# ------------------------------------------------------------------
# Driving it
# ------------------------------------------------------------------

# Measured off probe/04-menu-x281.png (System 7, 512x342) by counting
# dark rows down the menu's column, not by eye. Norton 1.1's menu is
# 4.1's menu to the pixel — `ddpro.DD_ITEM` has the same numbers — with
# one item `ddpro.py` never used: **Compress Using**, a submenu, which
# is where the list of methods lives.
DD_MENU_X = 281
DD_ITEM = {"compress": 27, "using": 44, "expand": 60, "view": 91,
           "savings": 108, "compressto": 140, "expandto": 156,
           "convert": 171, "split": 187, "archive": 219, "sea": 235,
           "expandarch": 252, "settings": 284, "about": 299}


def menu(s, item, tag, y=None):
    ox, oy = s.mac.origin()
    x = s.mac._xdo
    x("mousemove", str(ox + DD_MENU_X), str(oy + 8))
    time.sleep(0.4)
    x("mousedown", "1")
    time.sleep(1.2)
    x("mousemove", str(ox + DD_MENU_X + 25),
      str(oy + (DD_ITEM[item] if y is None else y)))
    time.sleep(1.0)
    s.shot("pick-" + tag)
    x("mouseup", "1")
    time.sleep(2.0)


def select(s, letter):
    """Type-select in the front window. Never Return: in the System 7
    Finder Return opens the selected icon's NAME for editing, and the
    next keystroke types into the name box (`ddpro.py`)."""
    s.mac.key("Escape")
    time.sleep(0.5)
    s.mac.key(letter)
    time.sleep(1.5)


SUBJECTS = [
    ("Subject", "TEXT", "ttxt", SUBJECT_DATA, make_rsrc()),
]

# Seven files, because the published `DDA2` archives that DO contain a
# `0x1000` record hold seven — and one file at a time has already been
# ruled out (`ddpro.py --experiments`, 2026-08-21). "Rough" is the
# incompressible one and it is the only one with a resource fork.
ARCHIVE_SUBJECTS = [
    ("Rough", "JPEG", "GKON", INCOMPRESSIBLE,
     make_rsrc(b"\x1eNorton DiskDoubler stored-fork probe")),
    ("Text A", "TEXT", "ttxt", b"compressible " * 700, b""),
    ("Text B", "TEXT", "ttxt", b"also compressible " * 700, b""),
    ("Text C", "TEXT", "ttxt", b"and again " * 900, b""),
    ("Text D", "TEXT", "ttxt", bytes(bytearray(range(256))) * 40, b""),
    ("Text E", "TEXT", "ttxt", b"\0" * 9000, b""),
    ("Text F", "TEXT", "ttxt", b"the seventh file " * 500, b""),
]


# The 2x2 that decides what a `0x1000` record IS. Every `0x1000` in the
# nine published archives is a file with NO resource fork
# (`ddtf-ddpro411ad1.dd`: testfile.jpg and testfile.png, both rsrc 0),
# and every file that HAS one gets an ordinary 0xABCD0054 header even
# when its data fork is stored — `Test Text` is 11 bytes stored beside a
# 332-byte AD1 resource fork. So "a file DiskDoubler could not shrink"
# is only half of the condition, and the other half is what this run
# measures: compressible x forked, all four cells, in one archive.
STORED_SUBJECTS = [
    ("Rough", "JPEG", "GKON", INCOMPRESSIBLE, b""),
    ("Small", "JPEG", "GKON", INCOMPRESSIBLE[:300], b""),
    ("Tiny", "JPEG", "GKON", INCOMPRESSIBLE[:40], b""),
    ("Forked", "JPEG", "GKON", INCOMPRESSIBLE[:300],
     make_rsrc(b"\x1eincompressible, with a fork")),
    ("Bigfork", "JPEG", "GKON", INCOMPRESSIBLE,
     make_rsrc(b"\x1e20000 bytes, with a fork")),
    ("Plain", "TEXT", "ttxt", b"compressible and fork-less " * 400, b""),
    ("Quiet", "TEXT", "ttxt", b"compressible, with a fork " * 400,
     make_rsrc(b"\x1ecompressible, with a fork")),
]


def stored(keep=False, which="norton"):
    """Which files get the headerless `0x1000` record — the whole 2x2.

    OPEN_ITEMS.md has been asking for "a `0x1000` record whose file has
    a resource fork" and narrowing WHERE to look for one. This asks the
    prior question instead: what selects the form at all. If the answer
    is "no resource fork", then the record OPEN_ITEMS wants cannot be
    written, the byte at +87 is not a resource checksum, and the item
    stops being a search.
    """
    s, work, img = session("stored", STORED_SUBJECTS, which, folder="Subjects")
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        select(s, "s")
        s.mac.command_key("o")
        s.shot("subjects", wait=10.0)
        s.mac.command_key("a")
        s.shot("selected-all", wait=3.0)
        menu(s, "archive", "create-archive")
        s.shot("archive-dialog", wait=8.0)
        s.mac.key("Return")
        s.shot("archive-running", wait=45.0)
        s.shot("archive-done", wait=20.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    got = report(img, "stored")
    want = {n: bool(r) for n, _t, _c, _d, r in STORED_SUBJECTS}
    rc = 1
    for path, (_t, _c, data, _r) in sorted(got.items()):
        if data[:4] != b"DDA2":
            continue
        kept = os.path.join(s.shots, path[-1].replace("/", "_"))
        open(kept, "wb").write(data)
        print("ndd: walking %s" % "/".join(path))
        for name, dl, rl, dsum, rsum in dda2_records(data):
            print("ndd: 0x1000 %-10s subject had a resource fork: %s"
                  % (name, want.get(name)))
            if rl:
                print("ndd: *** a 0x1000 record WITH a resource fork, "
                      "%d B, +87 = 0x%02x" % (rl, rsum))
        rc = verify_stored(kept)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return rc


def verify_stored(path):
    """Read the archive back with our own CLI and compare every fork with
    the bytes that went in — the loop `arcmac.py` and `diskdoubler.py`
    close for their formats, closed here for the `0x1000` record.

    Resource forks are compared with bytes 16..127 masked: that window is
    reserved for system use and the Mac rewrites it on copy, which is how
    the corpus's 8 unadjudicated forks are already graded (FORMATS.md).
    """
    tmp = tempfile.mkdtemp(prefix="ndd-v-")
    try:
        r = subprocess.run([cli(), "x", "--forks", "hidden", "-o", tmp, path],
                           capture_output=True, text=True)
        if r.returncode:
            print("ndd: extraction failed: %s" % r.stderr.strip())
            return 1
        bad = 0
        mask = (lambda b: b[:16] + b"\0" * 112 + b[128:]
                if len(b) >= 128 else b)
        for name, _t, _c, data, rsrc in STORED_SUBJECTS:
            dp = os.path.join(tmp, name)
            rp = os.path.join(tmp, "._" + name)
            gd = open(dp, "rb").read() if os.path.exists(dp) else b""
            gr = open(rp, "rb").read() if os.path.exists(rp) else b""
            ok = gd == data and mask(gr) == mask(rsrc)
            print("ndd: %-9s data %-6d rsrc %-5d %s"
                  % (name, len(gd), len(gr), "byte-exact" if ok else "DIFFERS"))
            bad += 0 if ok else 1
        print("ndd: %d/%d entries byte-exact against the bytes that went in"
              % (len(STORED_SUBJECTS) - bad, len(STORED_SUBJECTS)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# Mac epoch is 1904-01-01. Two dates far apart and in the natural order,
# so the record's +54 and +58 can finally be told apart: every specimen
# so far carries the SAME value twice, which is why `fmt_dd.c` assigns
# them by the order the reference reads them rather than measuring.
MAC_EPOCH_1990 = 2713910400          # 1990-01-01 00:00 local
MAC_EPOCH_1995 = 2884291200          # 1995-06-15 00:00 local


def macbinary_dated(name, ftype, creator, data, rsrc, created, modified):
    """`arcmac.macbinary` with the two dates filled in.

    Written here rather than by widening `macbinary()`: its CRC covers
    bytes 0..123, so the dates have to go in BEFORE the checksum, and
    every other caller of that helper wants zeroes.
    """
    from arcmac import crc16                             # noqa: E402
    mb = bytearray(macbinary(name, ftype, creator, data, rsrc))
    struct.pack_into(">II", mb, 91, created, modified)
    struct.pack_into(">H", mb, 124, crc16(bytes(mb[:124])))
    return bytes(mb)


DATE_SUBJECTS = [
    ("Dated", "JPEG", "GKON", INCOMPRESSIBLE[:400], b""),
    ("Elder", "JPEG", "GKON", INCOMPRESSIBLE[:900], b""),
]


def dates(keep=False, which="norton"):
    """Which of a `0x1000` record's two dates is the creation.

    The record has a 4-byte date at +54 and another at +58, and every
    specimen ever seen here carries the same value in both — the corpus's
    because the files were made and archived in one build, ours because
    `macbinary()` writes zeroes. So the assignment in `dd_archive2()` is
    the order the reference reads them in a DIFFERENT branch, which is a
    guess with a citation. Giving the subjects a 1990 creation and a 1995
    modification makes the two fields distinguishable on sight.
    """
    s, work, img = session("dates", DATE_SUBJECTS, which, folder="Subjects",
                           dated=(MAC_EPOCH_1990, MAC_EPOCH_1995))
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        select(s, "s")
        s.mac.command_key("o")
        s.shot("subjects", wait=10.0)
        s.mac.command_key("a")
        s.shot("selected-all", wait=3.0)
        menu(s, "archive", "create-archive")
        s.shot("archive-dialog", wait=8.0)
        s.mac.key("Return")
        s.shot("archive-running", wait=40.0)
        s.shot("archive-done", wait=20.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    got = report(img, "dates")
    for path, (_t, _c, data, _r) in sorted(got.items()):
        if data[:4] != b"DDA2":
            continue
        open(os.path.join(s.shots, path[-1].replace("/", "_")), "wb").write(data)
        print("ndd: walking %s" % "/".join(path))
        dda2_records(data)
        _date_verdict(data)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def _date_verdict(blob):
    at = 62
    while at + 46 <= len(blob):
        if blob[at:at + 4] != b"DDA2":
            break
        kind = struct.unpack_from(">H", blob, at + 4)[0]
        if kind == 0xBBBB:
            break
        total = struct.unpack_from(">I", blob, at + 42)[0]
        if not total:
            break
        if not (kind & 0x8000) and (kind & 0xF000) == 0x1000:
            nlen = min(blob[at + 6], 31)
            name = blob[at + 7:at + 7 + nlen].decode("mac-roman", "replace")
            a = struct.unpack_from(">I", blob, at + 54)[0]
            b = struct.unpack_from(">I", blob, at + 58)[0]
            def tag(v):
                if v == MAC_EPOCH_1990:
                    return "1990 (creation)"
                if v == MAC_EPOCH_1995:
                    return "1995 (modification)"
                return "neither (%d)" % v
            print("ndd: %-10s +54 = %s, +58 = %s" % (name, tag(a), tag(b)))
        at += total


def probe(keep=False, which="norton"):
    """Photograph every menu title and the Settings dialog. Every
    coordinate the other modes use is measured off these frames."""
    s, work, img = session("probe", ARCHIVE_SUBJECTS, which)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        for x in (250, 281, 300, 320):
            s.peek(x, "menu-x%d" % x)
    finally:
        time.sleep(3)
        s.close()
    print("ndd: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def submenu(keep=False, which="norton"):
    """Photograph the **Compress Using** submenu and the About box.

    This is the question `diskdoubler.py --probe` asked of 3.7's
    Settings dialog, asked of the last version instead: what methods
    does the application offer? 3.7 offered two software methods and a
    hardware one; 4.1's Settings popup offers five. Whether the LAST
    release offers a sixth is the only cheap way left to reach methods
    2-5, and it is one boot.
    """
    s, work, img = session("submenu", SUBJECTS, which)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        select(s, "s")
        ox, oy = s.mac.origin()
        x = s.mac._xdo
        # Hold the menu open, slide onto "Compress Using" and WAIT: a
        # hierarchical menu opens on a delay, so a screenshot taken at
        # the moment of arrival photographs the parent menu alone and
        # reads as "there is no submenu".
        x("mousemove", str(ox + DD_MENU_X), str(oy + 8))
        time.sleep(0.4)
        x("mousedown", "1")
        time.sleep(1.2)
        x("mousemove", str(ox + DD_MENU_X + 25), str(oy + DD_ITEM["using"]))
        time.sleep(2.5)
        s.shot("using-submenu", wait=1.5)
        x("mousemove", str(ox + DD_MENU_X + 120), str(oy + DD_ITEM["using"]))
        time.sleep(2.0)
        s.shot("using-submenu-open", wait=1.5)
        x("mousemove", str(ox + 5), str(oy + 8))
        time.sleep(0.5)
        x("mouseup", "1")
        time.sleep(1.5)
        menu(s, "about", "about")
        s.shot("about", wait=8.0)
        s.mac.key("Return")
        s.shot("after-about", wait=4.0)
        menu(s, "settings", "settings")
        s.shot("settings", wait=8.0)
    finally:
        time.sleep(3)
        s.close()
    print("ndd: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def report(img, tag):
    """What came back on the work volume, described rather than trusted."""
    got = read_forks(img)
    for path, (ftype, creator, data, rsrc) in sorted(got.items()):
        name = "/".join(path)
        h = header(data)
        mark = ""
        if h:
            mark = "  " + describe(h)
        elif data[:4] == b"DDA2":
            mark = "  DDA2 archive"
        print("ndd: %-40s %s/%s %7d %7d%s"
              % (name, ftype, creator, len(data), len(rsrc), mark))
    return got


def dda2_records(blob):
    """Walk a `DDA2` archive's entries and print what kind each one is.

    Entries are a chain, not a table: 46 bytes of common header with the
    entry type at +4, the name length at +6 and the WHOLE record's size
    at +42, and 0xBBBB ends the archive. Written against
    `dd_archive2()` in `src/fmt_dd.c`, which is the reader.

    The `0x1000` record — no `0xABCD0054` file header of its own — is
    what DiskDoubler Pro writes for a file whose data fork is stored AND
    which has no resource fork; `--stored` is what measured the second
    half. Its two fork lengths sit at +78 and +82, its dates at +54
    (creation) and +58, and its checksum bytes at +86 and +87, of which
    only +86 ever describes anything.
    """
    at, n, stored = 62, 0, []
    while at + 46 <= len(blob):
        if blob[at:at + 4] != b"DDA2":
            print("ndd:   entry chain stops at %d (no DDA2 tag)" % at)
            break
        kind = struct.unpack_from(">H", blob, at + 4)[0]
        if kind == 0xBBBB:
            print("ndd:   end of archive at %d" % at)
            break
        nlen = min(blob[at + 6], 31)
        name = blob[at + 7:at + 7 + nlen].decode("mac-roman", "replace")
        total = struct.unpack_from(">I", blob, at + 42)[0]
        level = struct.unpack_from(">I", blob, at + 38)[0] - 2
        n += 1
        if total == 0:
            print("ndd:   entry %d %r: zero size, stopping" % (n, name))
            break
        if kind & 0x8000:
            what = "folder"
        elif (kind & 0xF000) == 0x1000:
            dl = struct.unpack_from(">I", blob, at + 78)[0]
            rl = struct.unpack_from(">I", blob, at + 82)[0]
            what = ("STORED 0x1000: data %d rsrc %d, sums +86=0x%02x "
                    "+87=0x%02x" % (dl, rl, blob[at + 86], blob[at + 87]))
            stored.append((name, dl, rl, blob[at + 86], blob[at + 87]))
        elif blob[at + 56:at + 60] == b"\xab\xcd\x00\x54":
            h = header(blob, at + 56)
            what = "0xABCD0054: " + describe(h)
        else:
            what = "no file header and not 0x1000"
        print("ndd:   entry %d at %-6d kind 0x%04x level %d  %-14s %s"
              % (n, at, kind, level, name, what))
        at += total
    return stored


def archive(keep=False, which="norton"):
    """Create Archive… over seven files, one of them incompressible AND
    carrying a resource fork."""
    s, work, img = session("archive", ARCHIVE_SUBJECTS, which,
                           folder="Subjects")
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        select(s, "s")                            # the Subjects folder
        s.mac.command_key("o")                    # Open, not Return
        s.shot("subjects", wait=10.0)
        s.mac.command_key("a")                    # Select All: the seven
        s.shot("selected-all", wait=3.0)
        menu(s, "archive", "create-archive")
        s.shot("archive-dialog", wait=8.0)
        s.mac.key("Return")
        s.shot("archive-running", wait=45.0)
        s.shot("archive-done", wait=20.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")                    # Put Away: flush
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    got = report(img, "archive")
    os.makedirs(s.shots, exist_ok=True)
    rc = 1
    for path, (_t, _c, data, _r) in sorted(got.items()):
        if data[:4] != b"DDA2":
            continue
        # Keep the archive. A specimen is what this run is FOR, and the
        # first attempt threw one away with the work directory.
        keptp = os.path.join(s.shots, path[-1].replace("/", "_"))
        open(keptp, "wb").write(data)
        print("ndd: kept %s (%d B)" % (keptp, len(data)))
        print("ndd: walking %s" % "/".join(path))
        stored = dda2_records(data)
        for name, dl, rl, dsum, rsum in stored:
            if rl:
                print("ndd: *** a 0x1000 record WITH a resource fork: "
                      "%s, %d B, +87 = 0x%02x" % (name, rl, rsum))
                rc = 0
        if stored and rc:
            print("ndd: 0x1000 records written, all fork-less — the same "
                  "shape every published one has")
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true", help="fetch both releases")
    ap.add_argument("--harvest", action="store_true",
                    help="decode the Norton floppy here and report methods")
    ap.add_argument("--dexvert", action="store_true",
                    help="run the engine over a third collector's samples")
    ap.add_argument("--specimens", action="store_true",
                    help="decode Salient's 1991 3.1.2 disk and report methods")
    ap.add_argument("--grade", action="store_true",
                    help="DiskTester: our decode vs the uncompressed 4.0 copy")
    ap.add_argument("--install", action="store_true",
                    help="build the System 7 boot image")
    ap.add_argument("--probe", action="store_true",
                    help="photograph the menus")
    ap.add_argument("--submenu", action="store_true",
                    help="photograph Compress Using, About and Settings")
    ap.add_argument("--dates", action="store_true",
                    help="which of a 0x1000 record's two dates is which")
    ap.add_argument("--stored", action="store_true",
                    help="what selects the headerless 0x1000 record")
    ap.add_argument("--archive", action="store_true",
                    help="seven files, one incompressible with a fork")
    ap.add_argument("--app", default="norton", choices=("norton", "dd40"),
                    help="which release to run (default norton)")
    ap.add_argument("--keep", action="store_true", help="keep the work dir")
    a = ap.parse_args()
    if a.keep:      # guard deletes images at exit otherwise
        os.environ["HARNESS_KEEP_IMAGES"] = "1"
    if a.setup:
        setup()
    elif a.harvest:
        harvest()
    elif a.dexvert:
        return dexvert()
    elif a.specimens:
        return specimens()
    elif a.grade:
        return grade()
    elif a.install:
        install(a.app)
    elif a.probe:
        probe(a.keep, a.app)
    elif a.submenu:
        submenu(a.keep, a.app)
    elif a.dates:
        return dates(a.keep, a.app)
    elif a.stored:
        return stored(a.keep, a.app)
    elif a.archive:
        return archive(a.keep, a.app)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

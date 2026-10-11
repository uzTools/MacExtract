#!/usr/bin/env python3
"""diskdoubler.py — find out what DiskDoubler itself can WRITE, by running it.

DiskDoubler defines eleven compression methods and this engine implements
the ones the corpus could grade. The rest were declined on the grounds
that no specimen exists — a claim about this machine's reach, not about
the format, and the way to test it is the one `nowcompress.py` and
`arcmac.py` already use: run the original application under Mini vMac and
look at what it produces.

    diskdoubler.py --setup           fetch DiskDoubler 3.7, unpack its disk
    diskdoubler.py --wild --extract  every DD container ON that disk, by method
    diskdoubler.py --install         a System 7 image with the DD INIT loaded
    diskdoubler.py --probe           photograph the menus and dialogs
    diskdoubler.py --make A          compress the subject with one method
    diskdoubler.py --combine         a DDAR archive with a folder in it
    diskdoubler.py --beta            compress with DiskDoubler ß05, 1990
    diskdoubler.py --beta-verify     grade what ß05 wrote
    diskdoubler.py --verify          decode every specimen and grade it

**The answer, measured 2026-08-20.** The Settings dialog's "How To
Compress" popup has four items, and between them they write two methods:

    Method A (fastest)               -> method 1, Unix compress
    Method B (usually smaller)       -> method 8, Compact Pro
    Smallest Guess (let DD choose)   -> method 8 on the subject here
    Smallest (try both)              -> method 8 on the subject here

With a Sigma Designs compression card fitted the popup grows a "Sigma
Hardware" item, which is **method 7 (Stac LZS)** — and nothing here
emulates that card, so no keyboard on this machine can produce one. It
did not have to: Salient built the 3.7 distribution disk on a machine
that had the card, and two THINK C libraries on it are method 7
(`--wild`). The menu strings are MENU 5019 (no card) and 5021 (card) in
the application's resource fork.

Methods 2, 3, 4 and 5 are NOT reachable from this application at all.
They were recorded here as belonging to "DiskDoubler 1.x and 2.x, no
copy of either reachable from here" until 2026-09-22, which was a guess
about which version rather than a measurement: the oldest DiskDoubler
that exists anywhere reachable is ß05 of 1990 (--beta, below), and it
offers no settings at all — its one Compress command writes method 1.
So nothing here says which version those four methods came from.

Specimens land in `$UNC_VMAC_HOME/specimens/diskdoubler/`, beside the
emulator rather than under `build/`, which `make clean` removes. Nothing
here runs in `ci.sh`.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                      # noqa: E402
from interactive import Mac                          # noqa: E402
from arcmac import macbinary             # noqa: E402
from mkboot import FINDER_OWN             # noqa: E402

# DiskDoubler 3.7, commercial, fetched by URL and checked by hash exactly
# like the ROM and the System images; nothing from it is committed. The
# 3.7 disk is the last one whose compressor predates the AD/DDn methods
# of 4.0, which is why it is the one worth running.
DD37_URL = "https://old.mac.gdn/apps/diskdoublertm_3-7_disk-i.zip"
DD37_PAGE = "https://macintoshgarden.org/apps/diskdoubler-37"
DD37_SHA = "8cccf39aad06bbe60b92ac85ba2978f43ae3851d97e14cb7bb98ebac649ff811"

HOME = R.VMAC_HOME
WORK = os.path.join(HOME, "diskdoubler")
SPECIMENS = os.path.join(HOME, "specimens", "diskdoubler")
ZIP = os.path.join(WORK, "dd37.zip")
RAW = os.path.join(WORK, "dd37.hfv")
BOOT = os.path.join(WORK, "ddboot.hfv")           # System 7 + the DD INIT

DD_MAGIC = 0xABCD0054

# The subject: a data fork that compresses well and a resource fork that
# identifies itself from its own first bytes, so whatever comes back out
# says what it is without being trusted.
SUBJECT_NAME = "Subject"
SUBJECT_DATA = (b"DiskDoubler method probe. " * 400 +
                bytes(range(256)) * 4 +
                b"tail" )


def cli():
    for build in ("rel", "san", ""):
        p = os.path.join(REPO, "build", build, "macextract")
        if os.path.exists(p):
            return p
    raise SystemExit("diskdoubler: build the CLI first (make)")


# ------------------------------------------------------------------
# Reading DiskDoubler containers without decoding them
# ------------------------------------------------------------------

def header(blob, off=0):
    """The single-file container's 84-byte header, or None."""
    if len(blob) - off < 84:
        return None
    if struct.unpack_from(">I", blob, off)[0] != DD_MAGIC:
        return None
    dl, dcl, rl, rcl = struct.unpack_from(">IIII", blob, off + 4)
    return {
        "datamethod": blob[off + 20] & 0x7F,
        "rsrcmethod": blob[off + 21] & 0x7F,
        "data": dl, "datacomp": dcl, "rsrc": rl, "rsrccomp": rcl,
        "info1": blob[off + 22], "info2": blob[off + 52],
        "datacrc": struct.unpack_from(">H", blob, off + 48)[0],
        "rsrccrc": struct.unpack_from(">H", blob, off + 50)[0],
    }


METHOD_NAMES = {
    0: "stored", 1: "Compress", 2: "method 2", 3: "RLE", 4: "Huffman",
    5: "method 5", 6: "AD2", 7: "Stac LZS", 8: "Compact Pro", 9: "AD1",
    10: "DDn",
}


def describe(h):
    return ("data %d (%s) %d->%d, rsrc %d (%s) %d->%d"
            % (h["datamethod"], METHOD_NAMES.get(h["datamethod"], "?"),
               h["data"], h["datacomp"],
               h["rsrcmethod"], METHOD_NAMES.get(h["rsrcmethod"], "?"),
               h["rsrc"], h["rsrccomp"]))


# ------------------------------------------------------------------
# Fetching and unpacking the distribution disk
# ------------------------------------------------------------------

def fetch():
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(ZIP):
        subprocess.run(["curl", "-sS", "-L", "-A", "Mozilla/5.0",
                        "-e", DD37_PAGE, "-o", ZIP, DD37_URL], check=True)
    got = hashlib.sha256(open(ZIP, "rb").read()).hexdigest()
    print("diskdoubler: %s sha256 %s" % (os.path.basename(ZIP), got))
    with zipfile.ZipFile(ZIP) as z:
        names = [i.filename for i in z.infolist() if "XtraStuf" not in i.filename]
        blob = z.read(names[0])
    # DiskCopy 4.2: an 84-byte header, then the sectors. The header names
    # the data length, which is what says the image is whole.
    dlen = struct.unpack_from(">I", blob, 64)[0]
    if len(blob) < 84 + dlen:
        raise SystemExit("diskdoubler: DiskCopy image is short")
    open(RAW, "wb").write(blob[84:84 + dlen])
    print("diskdoubler: %s — %d bytes of HFS" % (RAW, dlen))
    return RAW


def volume_files(img, invisible=True):
    """path tuple -> (type, creator, data, rsrc) for a whole volume.

    Names are carried as BYTES all the way to `hcopy`. An HFS name is
    Mac Roman and hfsutils takes it verbatim, so decoding it and handing
    back a str makes Python re-encode it as UTF-8 — and every name with a
    ™ or an ƒ in it then fails to open. On this disk that is most of the
    interesting files, and the failure is silent: the walk simply returns
    fewer of them.

    **`-a`, since 2026-09-22.** `hls` hides a file whose Finder INVISIBLE
    bit is set, and this walk descends, so the flag buys two things: an
    invisible FILE anywhere on the volume, and an invisible FOLDER, whose
    whole subtree it used to walk straight past (`walkprobe.py`, the
    hidden-folder column). Pass `invisible=False` for the listing as it
    was.

    **What the flag costs here is nothing, and that was checked rather
    than assumed.** It surfaces the Finder's own bookkeeping, which
    `FINDER_OWN` drops, and all six callers select by DiskDoubler header,
    by exact name, or by a magic number — not one of them compares fork
    SETS, which is the thing that makes the same flag expensive for
    `superdisk.read_forks` (OPEN_ITEMS.md, *Volume walks that cannot see
    an invisible file*).
    """
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    out, dropped = {}, []

    def walk(prefix):
        listing = subprocess.run([b"hls"] + ([b"-a"] if invisible else [])
                                 + [b"-1F"], capture_output=True,
                                 env=env).stdout
        for name in [n for n in listing.split(b"\n") if n.strip()]:
            if (invisible and not prefix
                    and name.decode("mac-roman", "replace") in FINDER_OWN):
                dropped.append(name.decode("mac-roman", "replace"))
                continue
            if name.endswith(b":"):
                name = name[:-1]
                subprocess.run([b"hcd", name], capture_output=True, env=env)
                walk(prefix + (name,))
                subprocess.run([b"hcd", b"::"], capture_output=True, env=env)
                continue
            if name.endswith(b"*") or name.endswith(b"/"):
                name = name[:-1]
            tmp = tempfile.mktemp(suffix=".bin").encode()
            if subprocess.run([b"hcopy", b"-m", name, tmp], capture_output=True,
                              env=env).returncode != 0:
                continue
            blob = open(tmp, "rb").read()
            os.unlink(tmp)
            dlen, rlen = struct.unpack(">II", blob[83:91])
            roff = 128 + ((dlen + 127) & ~127)
            out[prefix + (name,)] = (blob[65:69].decode("mac-roman"),
                                     blob[69:73].decode("mac-roman"),
                                     blob[128:128 + dlen], blob[roff:roff + rlen])
    try:
        subprocess.run(["hmount", img], check=True, capture_output=True, env=env)
        walk(())
        subprocess.run(["humount"], capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    # What `-a` cost on this harness's own volumes, printed rather than
    # assumed.
    print("diskdoubler: -a surfaced and FINDER_OWN dropped: %s"
          % (", ".join(sorted(dropped)) or "nothing"))
    return out


def show(path):
    return "/".join(p.decode("mac-roman") for p in path)


def wild(extract=False):
    """Every DiskDoubler container on the distribution disk, by method.

    The disk ships its own files compressed, which is why it is a corpus
    as well as an application: the two THINK C libraries on it are the
    only method 7 specimens this project has, and no keyboard here can
    make another — method 7 is what the Sigma Designs card wrote.
    """
    if not os.path.exists(RAW):
        fetch()
    dest = os.path.join(SPECIMENS, "wild")
    if extract:
        os.makedirs(dest, exist_ok=True)
    found = 0
    for path, (ftype, creator, data, rsrc) in sorted(volume_files(RAW).items()):
        h = header(data) or header(rsrc)
        if not h:
            continue
        found += 1
        print("  %-40s %s/%s  %s" % (show(path)[-40:], ftype, creator,
                                     describe(h)))
        if extract:
            name = path[-1].decode("mac-roman").replace("/", "_")
            p = os.path.join(dest, name + ".dd")
            open(p, "wb").write(data if header(data) else rsrc)
    print("diskdoubler: %d compressed file(s) on the 3.7 disk%s"
          % (found, (" -> %s" % dest) if extract else ""))
    return found


def extract_app(dest):
    """The DiskDoubler application, its data file and its help file, as
    MacBinary. The application launches on its own; the other two are
    what it looks for beside itself."""
    if not os.path.exists(RAW):
        fetch()
    files = volume_files(RAW)
    want = ("DiskDoubler\u2122 App", "DiskDoublerData(3.7)",
            "DiskDoubler\u2122 Help")
    out = []
    for path, (ftype, creator, data, rsrc) in files.items():
        name = path[-1].decode("mac-roman")
        if name in want:
            p = os.path.join(dest, name.replace("/", "_") + ".bin")
            open(p, "wb").write(macbinary(name, ftype, creator, data, rsrc))
            out.append(p)
    if not out:
        raise SystemExit("diskdoubler: no application on the 3.7 disk")
    return out


# ------------------------------------------------------------------
# Volumes
# ------------------------------------------------------------------

def make_rsrc(text=b"\x1eDiskDoubler method probe fork"):
    """A real resource fork: a STR resource, so what comes back can be
    read as a resource fork rather than compared as a blob."""
    data = struct.pack(">I", len(text)) + text
    doff, dlen = 256, len(data)
    moff = doff + dlen
    types = struct.pack(">H", 0) + b"STR " + struct.pack(">HH", 0, 10)
    refs = struct.pack(">hHII", 128, 0xFFFF, 0, 0)
    tloff, nloff = 28, 28 + len(types) + len(refs)
    hdr = struct.pack(">IIII", doff, moff, dlen, nloff)
    mp = hdr + b"\0" * 4 + struct.pack(">HHHH", 0, 0, tloff, nloff) + types + refs
    return hdr + b"\0" * (doff - 16) + data + mp


def make_volume(path, volname, macbins, size_kb=4096):
    open(path, "wb").truncate(size_kb * 1024)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        subprocess.run(["hformat", "-l", volname, path], check=True,
                       capture_output=True, env=env)
        subprocess.run(["hmount", path], check=True, capture_output=True, env=env)
        for mb in macbins:
            subprocess.run(["hcopy", "-m", os.path.abspath(mb), volname + ":"],
                           check=True, capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


def install():
    """A System 7 boot image with the DiskDoubler INIT in Extensions.

    The application does NOT run on its own: launched with no INIT loaded
    it takes the personalization, writes it back into its own resource
    fork and quits without ever showing a window — which looks exactly
    like a crash on a screenshot. DiskDoubler is an extension with an
    application beside it, and the extension is the half that compresses.
    """
    if not os.path.exists(RAW):
        fetch()
    work = tempfile.mkdtemp(prefix="ddinst-")
    try:
        files = volume_files(RAW)
        init = None
        for path, (ftype, creator, data, rsrc) in files.items():
            if path[-1].decode("mac-roman") == "DiskDoubler\u2122 INIT":
                init = os.path.join(work, "ddinit.bin")
                open(init, "wb").write(macbinary("DiskDoubler\u2122 INIT",
                                                 ftype, creator, data, rsrc))
        if not init:
            raise SystemExit("diskdoubler: no INIT on the 3.7 disk")
        shutil.copyfile(os.path.join(HOME, "Sys7.img"), BOOT)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            subprocess.run(["hmount", BOOT], check=True, capture_output=True,
                           env=env)
            subprocess.run(["hcopy", "-m", init,
                            ":System Folder:Extensions:"], check=True,
                           capture_output=True, env=env)
            subprocess.run(["humount"], check=True, capture_output=True, env=env)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("diskdoubler: boot image with the DiskDoubler INIT at %s" % BOOT)
    return BOOT


# ------------------------------------------------------------------
# Driving DiskDoubler
# ------------------------------------------------------------------

class Session:
    """A booted Mac with screenshots kept per step."""

    def __init__(self, boot, extra, shots, mem="mv-4M"):
        self.work = tempfile.mkdtemp(prefix="dd-")
        self.shots = shots
        os.makedirs(shots, exist_ok=True)
        self.n = 0
        self.mac = Mac(boot, mem, self.work, extra=tuple(extra))

    def shot(self, tag, wait=2.0):
        """Screenshot WITHOUT parking the pointer: parking closes a menu
        being held open."""
        time.sleep(wait)
        self.n += 1
        p = os.path.join(self.shots, "%02d-%s.png" % (self.n, tag))
        for _ in range(30):
            if self.mac.dpy.screenshot(p):
                return p
            time.sleep(0.4)
        raise SystemExit("diskdoubler: no screenshot")

    def boot(self):
        self.mac.settle(os.path.join(self.work, "s.png"), interval=8.0,
                        timeout=420.0, stable=3)

    def menu(self, title_x, item_y, tag):
        ox, oy = self.mac.origin()
        x = self.mac._xdo
        x("mousemove", str(ox + title_x), str(oy + 8))
        time.sleep(0.4)
        x("mousedown", "1")
        time.sleep(1.2)
        x("mousemove", str(ox + title_x + 25), str(oy + item_y))
        time.sleep(1.0)
        self.shot(tag)
        x("mouseup", "1")
        time.sleep(2.0)

    def peek(self, title_x, tag):
        """Pull a menu down, photograph it, and cancel — the step that
        measures an item's y before anything clicks one."""
        ox, oy = self.mac.origin()
        x = self.mac._xdo
        x("mousemove", str(ox + title_x), str(oy + 8))
        time.sleep(0.4)
        x("mousedown", "1")
        time.sleep(1.5)
        self.shot(tag)
        x("mousemove", str(ox + 5), str(oy + 8))
        time.sleep(0.5)
        x("mouseup", "1")
        time.sleep(1.0)

    def close(self):
        self.mac.close()


# The Settings dialog, measured from `--probe` screenshots (System 7,
# 512x342): the "How To Compress" popup and its four items, and OK.
POPUP = (270, 46)
POPUP_ITEMS = {"A": 46, "B": 60, "guess": 74, "both": 88}
POPUP_X = 300
SETTINGS_OK = (388, 267)
DD_MENU_X = 281
DD_COMPRESS_Y = 29
DD_SETTINGS_Y = 138
VOLUME_ICON = (470, 110)


def personalize(s):
    """The INIT personalizes itself the first time a DD command is used
    and writes the answer into its own copy in the System Folder. Mini
    vMac boots from a COPY of the image, so this happens on every run
    rather than once."""
    s.shot("personalize", wait=15.0)
    s.mac.click(300, 95)
    s.mac._xdo("type", "--delay", "120", "MacExtract")
    s.mac.key("Tab")
    s.mac._xdo("type", "--delay", "120", "test")
    s.mac.click(415, 214)                               # OK, no default button
    s.shot("postage", wait=10.0)
    s.mac.key("Return")                                 # "Don't Waste The Postage!"


def pick_method(s, which):
    """Hold the "How To Compress" popup open and release on an item."""
    ox, oy = s.mac.origin()
    x = s.mac._xdo
    x("mousemove", str(ox + POPUP[0]), str(oy + POPUP[1]))
    time.sleep(0.4)
    x("mousedown", "1")
    time.sleep(1.2)
    x("mousemove", str(ox + POPUP_X), str(oy + POPUP_ITEMS[which]))
    time.sleep(1.0)
    s.shot("pick-%s" % which)
    x("mouseup", "1")
    time.sleep(1.5)
    s.shot("chosen-%s" % which, wait=1.0)
    s.mac.click(*SETTINGS_OK)
    time.sleep(2.0)


# ------------------------------------------------------------------
# The Combine command — the two 'DDAR' record shapes no fixture has
# ------------------------------------------------------------------
#
# All 36 entries in the corpus's 7 'DDAR' archives are files with a full
# compressed-file header behind them. **Not one is a folder, and not one
# sets the 0x20 flag** that says the forks follow the record raw — so
# six offsets of that record are read by nothing here, and
# docs/formats/diskdoubler-container.md has to say they are XADMaster's
# and macutils' statement rather than a measurement.
#
# Combine is what writes a 'DDAR', and one archive can carry both
# shapes: a FOLDER holding two files, beside a file of bytes nothing
# compresses.

DD_COMBINE_Y = 59        # measured off probe/04-dd-menu.png, like the rest

COMBINE_NAME = "Nested"


def incompressible(nbytes, seed=7):
    """Bytes with no structure for DiskDoubler to find — the same LCG
    `split_subject` uses, which is what made Split have something to
    cut."""
    out = bytearray()
    x = seed & 0xFFFFFFFF
    while len(out) < nbytes:
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        out += x.to_bytes(4, "big")
    return bytes(out[:nbytes])


COMBINE_TREE = [
    (("Payload", "Nest"), "One", b"one one one one one\r" * 40, None),
    (("Payload", "Nest"), "Two", b"two two two two two\r" * 40, None),
    (("Payload",), "Raw", incompressible(24 * 1024), None),
]

# The second tree exists for the 0x20 flag alone, which the first one
# did not produce: every entry it wrote has a full compressed-file
# header behind it, method 0 included. So this one offers the shapes a
# record might plausibly be written raw for — a file DiskDoubler has
# ALREADY compressed, a file with a resource fork, and an empty one.
COMBINE_TREE_RAW = [
    (("Payload", "Nest"), "One", b"one one one one one\r" * 40, None),
    (("Payload",), "Raw", incompressible(24 * 1024), None),
    (("Payload",), "Forked", b"a short data fork\r", "rsrc"),
    (("Payload",), "Empty", b"", None),
    (("Payload",), "Already.dd", "already", "dd"),
]


def make_volume_tree(path, volname, items, size_kb=4096):
    """`make_volume`, with folders. items: [(folder tuple, macbin path)]."""
    open(path, "wb").truncate(size_kb * 1024)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        subprocess.run(["hformat", "-l", volname, path], check=True,
                       capture_output=True, env=env)
        subprocess.run(["hmount", path], check=True, capture_output=True, env=env)
        made = set()
        for folder, mb in items:
            for i in range(len(folder)):
                d = folder[:i + 1]
                if d in made:
                    continue
                subprocess.run(["hmkdir", volname + ":" + ":".join(d)],
                               capture_output=True, env=env)
                made.add(d)
            dest = volname + ":" + (":".join(folder) + ":" if folder else "")
            subprocess.run(["hcopy", "-m", os.path.abspath(mb), dest],
                           check=True, capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


def session_with_tree(tag, tree):
    work = tempfile.mkdtemp(prefix="ddwork-")
    apps = extract_app(work)
    items = [((), a) for a in apps]
    for i, (folder, name, data, extra) in enumerate(tree):
        p = os.path.join(work, "t%d.bin" % i)
        if data == "already":
            src = os.path.join(SPECIMENS, "subject-A.dd")
            if not os.path.exists(src):
                raise SystemExit("diskdoubler: --combine raw wants "
                                 "%s — run --make A first" % src)
            data = open(src, "rb").read()
        rsrc = make_rsrc() if extra == "rsrc" else b""
        ftype, creator = (("DDF3", "DDAP") if extra == "dd"
                          else ("TEXT", "ttxt"))
        open(p, "wb").write(macbinary(name, ftype, creator, data, rsrc))
        items.append((folder, p))
    img = os.path.join(work, "ddwork.img")
    make_volume_tree(img, "DDwork", items)
    if not os.path.exists(BOOT):
        install()
    s = Session(BOOT, [img], os.path.join(SPECIMENS, tag))
    return s, work, img


def combine(which="tree", keep=False):
    """Make a 'DDAR' archive holding a folder and an incompressible file."""
    tree = COMBINE_TREE if which == "tree" else COMBINE_TREE_RAW
    s, work, img = session_with_tree("combine-" + which, tree)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.menu(DD_MENU_X, DD_SETTINGS_Y, "pick-settings")
        personalize(s)
        s.shot("settings", wait=15.0)
        s.mac.click(*SETTINGS_OK)
        time.sleep(2.0)
        # Selected by TYPING, not by clicking an icon whose position
        # nothing here knows: the Finder selects by name.
        s.mac.key("p")                                  # "Payload"
        s.shot("payload-selected", wait=3.0)
        s.mac.command_key("o")                          # Open
        s.shot("payload-open", wait=8.0)
        s.mac.command_key("a")                          # Select All
        s.shot("all-selected", wait=3.0)
        s.peek(DD_MENU_X, "dd-menu")                    # is Combine enabled?
        s.menu(DD_MENU_X, DD_COMBINE_Y, "pick-combine")
        s.shot("combine-dialog", wait=10.0)
        s.mac._xdo("type", "--delay", "120", COMBINE_NAME)
        s.shot("combine-named", wait=3.0)
        s.mac.key("Return")
        s.shot("combining", wait=45.0)
        s.mac.key("Return")                             # any report
        s.shot("done", wait=20.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")                          # Put Away, to flush
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()

    os.makedirs(SPECIMENS, exist_ok=True)
    kept = 0
    for path, (ftype, creator, data, rsrc) in sorted(volume_files(img).items()):
        if not data[:4] == b"DDAR":
            continue
        name = show(path)
        out = os.path.join(SPECIMENS, "combine-%s.dd" % which)
        open(out, "wb").write(data)
        print("  %s  %s/%s  %d B -> %s" % (name, ftype, creator, len(data), out))
        kept += 1
    if not kept:
        print("diskdoubler: no DDAR came back — see %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if kept else 1


def verify_combine():
    """Grade the Combine specimens against the files that were fed in.

    The oracle here is the ENCODER's input, the same bargain
    `nowcompress.py` and `sdcompress.py` make: DiskDoubler was handed
    these bytes and these folders, so what comes back out of this
    engine either is them or is not. `unar` is asked as well, with
    `-k hidden` — `-k visible` has a GNUstep path bug and answers 422
    bytes where the fork is 340, which looks exactly like an oracle
    disagreement and is not one (TESTING.md, *Resource forks on Linux*).
    """
    trees = {"tree": COMBINE_TREE, "raw": COMBINE_TREE_RAW}
    total = bad = 0
    for which, tree in sorted(trees.items()):
        spec = os.path.join(SPECIMENS, "combine-%s.dd" % which)
        if not os.path.exists(spec):
            print("diskdoubler: no %s — run --combine %s" % (spec, which))
            continue
        want = {}
        for folder, name, data, extra in tree:
            if data == "already":
                continue            # Combine expands it; see the note
            path = "/".join(list(folder[1:]) + [name])
            want[path] = (data, make_rsrc() if extra == "rsrc" else b"")
        out = tempfile.mkdtemp(prefix="ddcomb-")
        try:
            subprocess.run([cli(), "x", "--forks", "hidden", "-o", out, spec],
                           capture_output=True)
            for path, (data, rsrc) in sorted(want.items()):
                total += 1
                p = os.path.join(out, path)
                got = open(p, "rb").read() if os.path.exists(p) else None
                side = os.path.join(os.path.dirname(p),
                                    "._" + os.path.basename(p))
                gotr = open(side, "rb").read() if os.path.exists(side) else b""
                if got != data:
                    bad += 1
                    print("  %s :: %s data %s, wanted %d B"
                          % (which, path,
                             "absent" if got is None else "%d B" % len(got),
                             len(data)))
                elif rsrc and rsrc not in gotr:
                    bad += 1
                    print("  %s :: %s resource fork differs" % (which, path))
                else:
                    print("  %s :: %-14s %6d B data, %4d B rsrc — as fed in"
                          % (which, path, len(data), len(rsrc)))
        finally:
            shutil.rmtree(out, ignore_errors=True)
    print("diskdoubler: %d Combine entr(y/ies) graded against the bytes "
          "DiskDoubler was given, %d disagreement(s)" % (total, bad))
    return 1 if bad else 0


def session_with_subject(tag):
    """A booted Mac with the DiskDoubler INIT loaded and a work volume
    holding the subject file."""
    work = tempfile.mkdtemp(prefix="ddwork-")
    apps = extract_app(work)
    subj = os.path.join(work, "subject.bin")
    open(subj, "wb").write(macbinary(SUBJECT_NAME, "TEXT", "ttxt",
                                     SUBJECT_DATA, make_rsrc()))
    img = os.path.join(work, "ddwork.img")
    make_volume(img, "DDwork", apps + [subj])
    if not os.path.exists(BOOT):
        install()
    s = Session(BOOT, [img], os.path.join(SPECIMENS, tag))
    return s, work, img


# ------------------------------------------------------------------
# DiskDoubler ß05, 1990 — the oldest one that COMPRESSES
# ------------------------------------------------------------------
#
# Everything docs/formats/diskdoubler-container.md measures was measured
# on 3.7, 4.0 and Pro 4.1, which is one generation of the application.
# `DiskDoublerExpand3.sit` on Macintosh Garden's `apps/disk-doubler` page
# carries a fourth: an INIT whose `vers` 1 reads
# "ß05@DiskDoubler(tm) ß05. Copyright 1990 Salient.", four versions older
# than the 3.1.2 this project had been calling the oldest, and the first
# compressor older than 3.7 to turn up anywhere (DECISIONS.md 2026-09-22,
# *the version that could not have written it*).
#
# It is an INIT and nothing else: no application, no Combine, no Split.
# Its Finder menu is `Compress Selection;Expand Selection;(-;About
# DiskDoubler(tm)`, so the way to make it write a file is to install it,
# select something in the Finder and pull that menu down.
#
# **What it answered, 2026-09-22.** The magic long 0xABCD0054 is a word
# 0xABCD and a 16-bit HEADER SIZE: 1990 writes 48 and lays those 48 bytes
# out field for field like the first 48 of the 84, it writes no header
# trailer, and it stamps the file ZIVM/LZIV rather than DD01. Neither
# this engine nor `unar` opens one. --beta-verify grades it against the
# bytes DiskDoubler was given; the write-up is
# docs/formats/diskdoubler-container.md, "The header size, and the 1990
# header".
BETA_URL = "https://old.mac.gdn/apps/DiskDoublerExpand3.sit"
BETA_PAGE = "https://macintoshgarden.org/apps/disk-doubler"
BETA_SHA = "051e50c11441146db2e3592deed022dda1bacbafc0fe477c30353fcc55b81ebc"
BETA_SIT = os.path.join(WORK, "older", "DiskDoublerExpand3.sit")
BETA_INIT_NAME = "DiskDoubler\u2122"
BETA_BOOT = os.path.join(WORK, "ddbeta.hfv")

# Measured off `--beta-probe` screenshots, System 6.0.8, 512x342. The INIT
# adds its menu to the FINDER's menu bar, so the title sits after the
# Finder's own five: Apple 19-27, File 43-63, Edit 79-101, View 117-146,
# Special 162-205, **DD 221-234**. The item ys are the menu it drops,
# `Compress Selection;Expand Selection;(-;About DiskDoubler(tm)`.
BETA_MENU_X = 227
BETA_COMPRESS_Y = 29
BETA_EXPAND_Y = 43


def fetch_beta():
    """The 1990 INIT, by URL and sha256 like the 3.7 disk. Nothing from
    it is committed."""
    os.makedirs(os.path.dirname(BETA_SIT), exist_ok=True)
    if not os.path.exists(BETA_SIT):
        subprocess.run(["curl", "-sS", "-L", "-A", "Mozilla/5.0",
                        "-e", BETA_PAGE, "-o", BETA_SIT, BETA_URL], check=True)
    got = hashlib.sha256(open(BETA_SIT, "rb").read()).hexdigest()
    if got != BETA_SHA:
        raise SystemExit("diskdoubler: %s sha256 %s, expected %s"
                         % (os.path.basename(BETA_SIT), got, BETA_SHA))
    return BETA_SIT


def beta_init(dest):
    """The INIT out of that archive, as MacBinary.

    Read with this project's own CLI, which is the only StuffIt 5 reader
    here — and a circularity worth naming: if it read the archive wrong
    the INIT would not run, and an INIT that does not run writes nothing,
    so the experiment cannot be quietly passed by a bad extraction.
    """
    fetch_beta()
    work = tempfile.mkdtemp(prefix="ddbeta-")
    subprocess.run([cli(), "x", "--forks", "hidden", BETA_SIT, "-o", work],
                   check=True, capture_output=True)
    listed = subprocess.run([cli(), "l", BETA_SIT], check=True,
                            capture_output=True).stdout.decode("utf-8")
    ftype = creator = None
    for line in listed.splitlines()[1:]:
        cols = line.split(None, 4)
        if len(cols) == 5 and cols[4].split("/")[-1] == BETA_INIT_NAME:
            ftype, creator = cols[3].split("/")
    if not ftype:
        raise SystemExit("diskdoubler: no %s in %s"
                         % (BETA_INIT_NAME, BETA_SIT))
    data = rsrc = b""
    for root, _d, files in os.walk(work):
        for f in files:
            if os.fsdecode(f) == BETA_INIT_NAME:
                data = open(os.path.join(root, f), "rb").read()
            elif os.fsdecode(f) == "._" + BETA_INIT_NAME:
                rsrc = open(os.path.join(root, f), "rb").read()
    if not rsrc:
        raise SystemExit("diskdoubler: %s has no resource fork" % BETA_INIT_NAME)
    p = os.path.join(dest, "ddbeta.bin")
    open(p, "wb").write(macbinary(BETA_INIT_NAME, ftype, creator, data, rsrc))
    shutil.rmtree(work, ignore_errors=True)
    print("diskdoubler: %s is %s/%s, %d B of resource fork"
          % (BETA_INIT_NAME, ftype, creator, len(rsrc)))
    return p


def install_beta():
    """A **System 6.0.8** boot image with the 1990 INIT in the System
    Folder. System 6 rather than the System 7 `install()` builds,
    because this INIT is two years older than System 7 and patches the
    Finder's menu bar — and because System 6.0.8 is the tier every other
    result here is quoted on."""
    work = tempfile.mkdtemp(prefix="ddbeta-")
    try:
        init = beta_init(work)
        shutil.copyfile(os.path.join(HOME, "System6.hfv"), BETA_BOOT)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            subprocess.run(["hmount", BETA_BOOT], check=True,
                           capture_output=True, env=env)
            subprocess.run(["hcopy", "-m", init, ":System Folder:"],
                           check=True, capture_output=True, env=env)
            subprocess.run(["humount"], check=True, capture_output=True,
                           env=env)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("diskdoubler: System 6.0.8 with the 1990 INIT at %s" % BETA_BOOT)
    return BETA_BOOT


def beta_session(tag, subject=None):
    """A booted Mac with the 1990 INIT loaded and a work volume holding
    the subject file."""
    work = tempfile.mkdtemp(prefix="ddbetawork-")
    subj = os.path.join(work, "subject.bin")
    open(subj, "wb").write(macbinary(SUBJECT_NAME, "TEXT", "ttxt",
                                     SUBJECT_DATA if subject is None else subject,
                                     make_rsrc()))
    img = os.path.join(work, "ddbetawork.img")
    make_volume(img, "DDwork", [subj])
    if not os.path.exists(BETA_BOOT):
        install_beta()
    s = Session(BETA_BOOT, [img], os.path.join(SPECIMENS, tag))
    return s, work, img


def beta_probe(keep=False, peeks=()):
    """Boot with the INIT in and photograph the menu bar, then every
    menu on it. Nothing is clicked: this is the run that MEASURES the
    coordinates `--beta` then uses, because an INIT's menu sits wherever
    the Finder's own menus leave room."""
    s, work, img = beta_session("beta-probe")
    try:
        s.boot()
        s.shot("desktop", wait=8.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        for x in peeks:
            s.peek(x, "menu-x%03d" % x)
    finally:
        time.sleep(3)
        s.close()
    print("diskdoubler: frames in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def beta(keep=False):
    """Compress the subject with the 1990 INIT and report what it wrote.

    The three questions this answers, all of them about a header this
    project has only ever seen one generation of
    (docs/formats/diskdoubler-container.md):

      * is the magic `0xABCD0054`, or is that long word a `0xABCD` and a
        HEADER SIZE the 1990 build writes differently?
      * does the file end with a byte-identical copy of its own header,
        the way 63 of the corpus's 66 compressed files do?
      * what file TYPE does it stamp — `DD01`, which neither this engine
        nor XADMaster recognises?
    """
    s, work, img = beta_session("beta")
    try:
        s.boot()
        s.shot("desktop", wait=8.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.mac.key("s")                                  # select "Subject"
        s.shot("selected", wait=3.0)
        s.menu(BETA_MENU_X, BETA_COMPRESS_Y, "pick-compress")
        s.shot("compressing", wait=45.0)
        s.mac.key("Return")                             # any report
        s.shot("done", wait=20.0)
        # Mini vMac flushes a guest's sector writes when the volume is
        # ejected, so a run killed with it mounted reads back unchanged.
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")                          # Put Away
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()

    os.makedirs(SPECIMENS, exist_ok=True)
    kept = 0
    for path, (ftype, creator, data, rsrc) in sorted(volume_files(img).items()):
        name = path[-1].decode("mac-roman")
        blob = data if data[:2] == b"\xab\xcd" else rsrc
        print("  %-24s %s/%s  %d B data, %d B rsrc"
              % (name, ftype, creator, len(data), len(rsrc)))
        if blob[:2] != b"\xab\xcd":
            continue
        p = os.path.join(SPECIMENS, "beta-%s.dd" % name.replace("/", "_"))
        open(p, "wb").write(blob)
        open(os.path.join(SPECIMENS, "beta-in-data"), "wb").write(SUBJECT_DATA)
        open(os.path.join(SPECIMENS, "beta-in-rsrc"), "wb").write(make_rsrc())
        beta_describe(blob, ftype, creator)
        print("  wrote %s" % p)
        kept += 1
    if not kept:
        print("diskdoubler: nothing came back compressed — see %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if kept else 1


def beta_describe(blob, ftype, creator):
    """Read the three questions off the bytes, without assuming the
    84-byte shape the rest of this file reads."""
    magic, hsize = struct.unpack_from(">HH", blob, 0)
    print("    magic word 0x%04x, header size at +2 = %d" % (magic, hsize))
    print("    so the long a reader matches on is 0x%04x%04x"
          % (magic, hsize))
    dl, dcl, rl, rcl = struct.unpack_from(">IIII", blob, 4)
    print("    data %d -> %d, rsrc %d -> %d" % (dl, dcl, rl, rcl))
    print("    methods %d/%d, info1 0x%02x%s"
          % (blob[20], blob[21], blob[22],
             ", info2 0x%02x" % blob[52] if hsize > 52 else
             " (no info2: the header stops at %d)" % hsize))
    print("    type/creator IN the header: %s/%s"
          % (blob[32:36].decode("mac-roman"),
             blob[36:40].decode("mac-roman")))
    print("    dates: %s / %s" % (blob[24:28].hex(), blob[28:32].hex()))
    print("    the file itself is stamped %s/%s" % (ftype, creator))
    print("    %d + %d + %d = %d, and the file is %d B"
          % (hsize, dcl, rcl, hsize + dcl + rcl, len(blob)))
    print("    header trailer: %s"
          % ("yes, byte-identical"
             if len(blob) >= 2 * hsize and blob[-hsize:] == blob[:hsize]
             else "NO — nothing follows the two forks"))


def beta_verify():
    """Grade the 1990 specimen against the bytes DiskDoubler was given.

    The oracle is the ENCODER's input, the same bargain `--verify-combine`
    and `nowcompress.py` make; `unar` cannot open one of these at all.

    Two passes, answering different questions:

    * **the file as it is.** Since 2026-09-22 the engine reads the size
      word at +2, so a 48-byte header is a shape it knows and the
      specimen goes in untouched. That grades the code that ships.
    * **the file rewritten with an 84-byte header**, the checksums of
      those same forks written where an 84-byte header keeps them. This
      is what ESTABLISHED the claim before any of it was implemented,
      and it is kept because it is the stronger statement: the forks
      come back byte-exact THROUGH a checksum this file did not compute
      — 0xd766 and 0x116a are the two DiskDoubler 3.7 itself stored for
      the same forks — so the two headers share their first 48 bytes
      field for field and the codec is the same one.
    """
    spec = os.path.join(SPECIMENS, "beta-Subject.dd")
    if not os.path.exists(spec):
        raise SystemExit("diskdoubler: no 1990 specimen — run --beta first")
    blob = open(spec, "rb").read()
    want_d = open(os.path.join(SPECIMENS, "beta-in-data"), "rb").read()
    want_r = open(os.path.join(SPECIMENS, "beta-in-rsrc"), "rb").read()
    hsize = struct.unpack_from(">H", blob, 2)[0]
    dcl, rcl = struct.unpack_from(">I", blob, 8)[0], \
        struct.unpack_from(">I", blob, 16)[0]
    # The stored sum is the fork's plain bytes plus compress's own three
    # header bytes, which method 1 adds in (src/fmt_dd.c, dd_lzc). Computed
    # from the INPUT, so the decoder cannot influence it. Those three are
    # read in clear because a 1990 file is not XOR-garbled — its info1 is
    # 0x1f, under the 0x2a the rule tests for.
    m = blob[hsize:hsize + 3]
    adj = sum(m)

    def ck(b):
        return (sum(b) + adj) & 0xFFFF
    h84 = bytearray(blob[:48]) + bytearray(36)
    h84[2:4] = struct.pack(">H", 84)
    struct.pack_into(">HH", h84, 48, ck(want_d), ck(want_r))

    def decode(name, payload):
        work = tempfile.mkdtemp(prefix="ddbetaverify-")
        try:
            path = os.path.join(work, name)
            open(path, "wb").write(payload)
            out = os.path.join(work, "out")
            os.makedirs(out)
            r = subprocess.run([cli(), "x", "--forks", "hidden", path,
                                "-o", out], capture_output=True)
            d, rs = os.path.join(out, name), os.path.join(out, "._" + name)
            return (r.returncode,
                    open(d, "rb").read() if os.path.exists(d) else b"",
                    open(rs, "rb").read() if os.path.exists(rs) else b"")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    bad = 0
    for tag, name, payload in (
            ("as written, a 48-byte header", "Subject", blob),
            ("rewritten with an 84-byte header", "as84",
             bytes(h84) + blob[hsize:])):
        ret, got_d, got_r = decode(name, payload)
        print("  %s:" % tag)
        if ret != 0:
            print("    the engine returned %d" % ret)
        for label, got, want in (("data", got_d, want_d),
                                 ("rsrc", got_r, want_r)):
            if got == want:
                print("    %s fork: %d B byte-exact" % (label, len(got)))
            else:
                bad += 1
                print("    %s fork: MISMATCH - %d B out, %d B in"
                      % (label, len(got), len(want)))
    print("  the sums written into the 84-byte rewrite came from the INPUT: "
          "0x%04x and 0x%04x, and DiskDoubler 3.7 stored those two for the "
          "same forks" % (ck(want_d), ck(want_r)))
    print("diskdoubler: the 1990 file decodes as it is, and its first 48 "
          "bytes are the 84-byte header's, %d disagreement(s)" % bad)
    return 1 if bad else 0


# ------------------------------------------------------------------
# The Split command
# ------------------------------------------------------------------

DD_SPLIT_Y = 75          # measured off probe/04-dd-menu.png, like the rest

# Three files, split one after another in ONE session, to find out what
# the 4 bytes at offset +4 of a `SPLT` header are (OPEN_ITEMS.md). They
# are equal across the parts of a set and different between sets, and
# every checksum tried over the payload, the forks and the file has been
# ruled out. The two TWINS are byte-identical and are split minutes
# apart; ODD differs in content and length. So:
#
#   twins equal, ODD different      -> a function of the CONTENT
#   all three different, increasing -> a function of WHEN (a tick count)
#   twins different by ~= the ticks between them   -> the same, measured
#
# Content that compresses badly, so Split has something to cut: a plain
# counter would let DiskDoubler's own compression change the sizes.
SPLIT_KB = 260


def split_subject(seed):
    """`SPLIT_KB` KB of bytes that depend on `seed` and nothing else."""
    out = bytearray()
    x = seed & 0xFFFFFFFF
    while len(out) < SPLIT_KB * 1024:
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        out += x.to_bytes(4, "big")
    return bytes(out)


SPLIT_FILES = [("Twin A", split_subject(1)),
               ("Twin B", split_subject(1)),
               ("Odd", split_subject(2)[:SPLIT_KB * 1024 - 3072])]


def session_with_files(tag, files):
    """A booted Mac with the DiskDoubler INIT loaded and a work volume
    holding `files` — [(name, data)] — beside the application."""
    work = tempfile.mkdtemp(prefix="ddwork-")
    apps = extract_app(work)
    mbs = []
    for i, (name, data) in enumerate(files):
        p = os.path.join(work, "f%d.bin" % i)
        open(p, "wb").write(macbinary(name, "TEXT", "ttxt", data, b""))
        mbs.append(p)
    img = os.path.join(work, "ddwork.img")
    make_volume(img, "DDwork", apps + mbs)
    if not os.path.exists(BOOT):
        install()
    s = Session(BOOT, [img], os.path.join(SPECIMENS, tag))
    return s, work, img


def probe_split(keep=False):
    """Photograph what the Split command asks for. Everything after this
    is coordinates read off these screenshots."""
    s, work, img = session_with_files("probe-split", SPLIT_FILES)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.menu(DD_MENU_X, DD_SETTINGS_Y, "pick-settings")
        personalize(s)
        s.shot("settings", wait=15.0)
        s.mac.click(*SETTINGS_OK)
        time.sleep(2.0)
        s.mac.key("t")                                  # select "Twin A"
        s.shot("selected", wait=3.0)
        s.peek(DD_MENU_X, "dd-menu")
        s.menu(DD_MENU_X, DD_SPLIT_Y, "pick-split")
        s.shot("split-dialog", wait=8.0)
        s.shot("split-dialog-again", wait=10.0)
    finally:
        time.sleep(3)
        s.close()
    print("diskdoubler: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def probe(keep=False):
    """Boot with the INIT loaded and photograph the menus and dialogs.
    This is the step that measured every coordinate above."""
    s, work, img = session_with_subject("probe")
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.peek(DD_MENU_X, "dd-menu")
        s.menu(DD_MENU_X, DD_SETTINGS_Y, "pick-settings")
        personalize(s)
        s.shot("settings", wait=15.0)
        ox, oy = s.mac.origin()
        s.mac._xdo("mousemove", str(ox + POPUP[0]), str(oy + POPUP[1]))
        time.sleep(0.4)
        s.mac._xdo("mousedown", "1")
        s.shot("how-to-compress", wait=1.5)
        s.mac._xdo("mouseup", "1")
        time.sleep(1.0)
    finally:
        time.sleep(3)
        s.close()
    print("diskdoubler: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def make(which="A", keep=False):
    """Compress the subject with one of the methods the menu offers, and
    report what DiskDoubler wrote."""
    if which not in POPUP_ITEMS:
        raise SystemExit("diskdoubler: --method is one of %s"
                         % ", ".join(sorted(POPUP_ITEMS)))
    s, work, img = session_with_subject(which)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.menu(DD_MENU_X, DD_SETTINGS_Y, "pick-settings")
        personalize(s)
        s.shot("settings", wait=15.0)
        pick_method(s, which)
        s.mac.key("s")                                  # select "Subject"
        s.shot("selected", wait=3.0)
        s.menu(DD_MENU_X, DD_COMPRESS_Y, "pick-compress")
        s.shot("compressing", wait=45.0)
        s.mac.key("Return")                             # any report
        s.shot("done", wait=20.0)
        # Mini vMac flushes a guest's sector writes when the volume is
        # ejected, so a run killed with it mounted reads back unchanged.
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")                          # Put Away
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()

    os.makedirs(SPECIMENS, exist_ok=True)
    got = volume_files(img)
    kept = 0
    for path, (ftype, creator, data, rsrc) in sorted(got.items()):
        name = path[-1].decode("mac-roman")
        if name != SUBJECT_NAME:
            continue
        h = header(data) or header(rsrc)
        print("  %-10s %s/%s  %s" % (which, ftype, creator,
                                     describe(h) if h else "NOT compressed"))
        if h:
            p = os.path.join(SPECIMENS, "subject-%s.dd" % which)
            open(p, "wb").write(data if header(data) else rsrc)
            open(os.path.join(SPECIMENS, "in-data"), "wb").write(SUBJECT_DATA)
            open(os.path.join(SPECIMENS, "in-rsrc"), "wb").write(make_rsrc())
            print("  wrote %s" % p)
            kept += 1
    if not kept:
        print("diskdoubler: nothing came back compressed — see %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if kept else 1


# ------------------------------------------------------------------
# The forks neither oracle can decode, graded by DiskDoubler itself
# ------------------------------------------------------------------

# Two corpus fixtures hold 11 forks that `unar` fails on and `macunpack`
# — built with its own DiskDoubler support — fails on too, so nothing
# grades our output for them (OPEN_ITEMS.md). Both are SELF-EXTRACTING,
# which means each one carries a third implementation in its resource
# fork, the same bargain superdisk.py and nowcompress.py already make.
# The fixture named here is the ENVELOPE, because that is what still has
# the resource fork: the derived `.sea` in fixtures/ is its data fork
# alone, and a self-extractor without its code is just an archive.
ADJUDICATE = {
    "lha-expander-103.hqx": "derived-LHA_Expander_1.0.3.sea",
    "terrain-man-20.hqx": "derived-Terrainman_2.0__.sea",
}


def ours_path(root, path):
    """Where OUR extraction put the file the Mac has at `path`.

    A DiskDoubler self-extractor asks "Expand To:" and creates a folder;
    everything it writes lands inside it, including entries that sit at
    the TOP LEVEL of the archive, which our side writes at the root. So
    a path is tried as it stands and then with its first component
    dropped, and whichever one exists is the answer — rather than a rule
    about the folder, because the two specimens disagree about it: the
    Terrainman archive's own folder shares the destination's name and
    merged with it, so its nested paths need no adjustment and its two
    top-level entries do (measured 2026-08-21, when a global rule made
    3 of 23 forks "differ" in one specimen and all 10 in the other).
    """
    def at(parts):
        p = os.path.join(root, *[c.replace("/", ":") for c in parts])
        h, t = os.path.split(p)
        return p, (os.path.exists(p) or os.path.exists(os.path.join(h, "._" + t)))
    p, ok = at(path)
    if ok or len(path) < 2:
        return p
    alt, ok2 = at(path[1:])
    return alt if ok2 else p


def adjudicate(fixture, keep=False, write=False):
    """Run a DiskDoubler self-extractor under System 7 and compare every
    fork it writes with what our engine makes of the same archive."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    from vmac_check import mask_reserved                   # noqa: E402
    from superdisk import unwrap, read_forks               # noqa: E402

    name_only = os.path.basename(fixture)
    payload = ADJUDICATE.get(name_only)
    fixpath = fixture if os.path.exists(fixture) else \
        os.path.join(REPO, "fixtures", name_only)
    if not os.path.exists(fixpath):
        raise SystemExit("diskdoubler: no such fixture: %s" % fixture)
    inner = os.path.join(REPO, "fixtures", payload) if payload else fixpath

    work = tempfile.mkdtemp(prefix="ddadj-")
    tag = "adj-" + name_only.split(".")[0]
    name, ftype, creator, data, rsrc = unwrap(fixpath, work)
    print("diskdoubler: %s — %s %s/%s, %d B data, %d B rsrc"
          % (name_only, name, ftype, creator, len(data), len(rsrc)))
    if not rsrc:
        raise SystemExit("diskdoubler: %s has no resource fork, so there is "
                         "no extractor in it to run" % name_only)
    mb = os.path.join(work, "app.bin")
    open(mb, "wb").write(macbinary(name, ftype, creator, data, rsrc))

    img = os.path.join(work, "adj.img")
    open(img, "wb").truncate(25 * 1024 * 1024)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        subprocess.run(["hformat", "-l", "Adj", img], check=True,
                       capture_output=True, env=env)
        subprocess.run(["hmount", img], check=True, capture_output=True,
                       env=env)
        subprocess.run(["hcopy", "-m", mb, "Adj:"], check=True,
                       capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)

    s = Session(os.path.join(HOME, "Sys7.img"), [img],
                os.path.join(SPECIMENS, tag))
    try:
        s.boot()
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        # Select All then Open, never a measured coordinate: the Finder
        # draws an icon where it likes, and a double-click on the wrong
        # few pixels selects instead of launching — which is what a
        # screenshot of the right window at the wrong moment looks like
        # (superdisk.py learned this the expensive way).
        s.mac.command_key("a")
        time.sleep(2)
        s.mac.command_key("o")
        s.shot("launched", wait=45.0)
        s.mac.key("Return")               # wherever it asks to put them
        s.shot("expanding", wait=90.0)
        s.mac.key("Return")
        s.shot("done", wait=90.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")            # Put Away: flush the writes
        s.shot("ejected", wait=20.0)
    finally:
        time.sleep(5)
        s.close()

    theirs = read_forks(img)
    ours = tempfile.mkdtemp(prefix="ddadj-ours-")
    subprocess.run([cli(), "x", "--forks", "hidden", "-o", ours, inner],
                   capture_output=True)
    bad = seen = raw_bad = 0
    verdict = {}                      # entry path -> {fork: bytes the Mac wrote}
    for path, (ftype2, creator2, tdata, trsrc) in sorted(theirs.items()):
        if path[-1] == name:
            continue                                   # the extractor itself
        mine = ours_path(ours, path)
        head, tail = os.path.split(mine)
        odata = open(mine, "rb").read() if os.path.isfile(mine) else b""
        side = os.path.join(head, "._" + tail)
        orsrc = open(side, "rb").read() if os.path.isfile(side) else b""
        for fork, a, b, ra, rb in (("data", tdata, odata, tdata, odata),
                                   ("rsrc", mask_reserved(trsrc),
                                    mask_reserved(orsrc), trsrc, orsrc)):
            if not a and not b:
                continue
            seen += 1
            same = a == b
            bad += not same
            # RAW as well as masked. The mask exists because the Resource
            # Manager stamps bytes 16..127 of a resource fork when it
            # touches the file — but if it did not touch these, the Mac's
            # bytes are exact ground truth and can go in a manifest, which
            # a masked comparison could never justify.
            rawsame = ra == rb
            raw_bad += not rawsame
            verdict.setdefault("/".join(path), {})[fork] = (ra, rawsame)
            shown = "/".join(path)
            print("  %-40s %s/%s %-4s %8d B  %s%s"
                  % (shown[-40:], ftype2, creator2, fork, len(a),
                     "IDENTICAL" if same else "DIFFERS",
                     " (with the reserved header masked)"
                     if same and not rawsame else ""))
    shutil.rmtree(ours, ignore_errors=True)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    print("diskdoubler: %d fork(s) compared with DiskDoubler's own "
          "extractor, %s" % (seen, "all identical" if not bad and seen
                             else "%d DIFFER" % bad))
    if raw_bad:
        print("diskdoubler: %d of them agree only with the resource-fork "
              "reserved header masked" % raw_bad)
    print("diskdoubler: screenshots in %s" % os.path.join(SPECIMENS, tag))
    if write and not bad and seen:
        n, notes = write_verdict(inner, verdict)
        print("diskdoubler: %d fork(s) written into the manifest as "
              "adjudicated, %d more noted as agreeing with the resource "
              "header masked" % (n, notes))
    return 1 if (bad or not seen) else 0


ADJ_ID = ("DiskDoubler's own self-extractor under System 7 "
          "(tools/vmac/diskdoubler.py --adjudicate)")

MASKED_NOTE = (" — but DiskDoubler's own self-extractor agrees on this fork "
               "with the resource header's OS-stamped bytes 16..127 masked "
               "(tools/vmac/diskdoubler.py --adjudicate, 2026-08-21)")


def write_verdict(fixture, verdict):
    """Record the Mac's bytes for forks no oracle could adjudicate.

    Only forks currently marked `unadjudicated` are touched, only where
    the Mac's RAW bytes are what we produced — a fork that agrees only
    with the reserved header masked is not exact ground truth and stays
    unadjudicated, with the reason left as it was. This is the same
    per-fork provenance `make_manifests.py` writes when the second
    oracle rescues a fork.
    """
    man_path = os.path.join(REPO, "fixtures", "manifests",
                            os.path.basename(fixture) + ".json")
    man = json.load(open(man_path))
    n = notes = 0
    for e in man["entries"]:
        un = e.get("unadjudicated")
        if not un:
            continue
        # The Mac's key is its own path, which carries the folder the
        # extractor expanded INTO; an entry at the top level of the
        # archive is at the top level of our output and one level down
        # on the volume. Same fallback as ours_path, from the other end.
        got = verdict.get(e["name"])
        if not got:
            for k, v in verdict.items():
                if k.split("/", 1)[-1] == e["name"]:
                    got = v
                    break
        if not got:
            continue
        for fork in ("data", "rsrc"):
            if fork not in un or fork not in got:
                continue
            blob, rawsame = got[fork]
            if not rawsame:
                # Agreed with the reserved header masked, and that is
                # worth recording where the fork's reason lives: the
                # Resource Manager stamps bytes 16..127 whenever it
                # touches a file, so the Mac can never be a byte-exact
                # oracle for a resource fork — it can for a data fork.
                if MASKED_NOTE not in un[fork]:
                    un[fork] = un[fork] + MASKED_NOTE
                    notes += 1
                continue
            e[fork + "_size"] = len(blob)
            e[fork + "_sha256"] = hashlib.sha256(blob).hexdigest()
            e[fork + "_oracle"] = ADJ_ID
            del un[fork]
            n += 1
        if not un:
            del e["unadjudicated"]
    if n or notes:
        man["entries"].sort(key=lambda x: x["name"])
        with open(man_path, "w") as fh:
            json.dump(man, fh, indent=1, ensure_ascii=False, sort_keys=True)
            fh.write("\n")
    return n, notes


def forks_of(d, appledouble):
    """{name: (data, rsrc)} for a directory of extracted forks, dropping
    empty forks so the two conventions can be compared at all."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    from make_manifests import parse_appledouble          # noqa: E402
    out = {}
    if not os.path.isdir(d):
        return out
    for n in os.listdir(d):
        p = os.path.join(d, n)
        if not os.path.isfile(p):
            continue
        if n.startswith("._"):
            name, fork = n[2:], "rsrc"
            blob = (parse_appledouble(p)[0] if appledouble
                    else open(p, "rb").read())
        else:
            name, fork = n, "data"
            blob = open(p, "rb").read()
        if not blob:
            continue
        out.setdefault(name, {})[fork] = blob
    return {k: sorted(v.items()) for k, v in out.items()}


def verify_wild():
    """Grade the specimens off the distribution disk against `unar`.

    There is no input to compare these with — nobody here compressed
    them — so the two things that grade them are the fork checksum the
    compressor wrote (which the engine enforces, so a decode that
    reaches the end is already checked) and a second implementation.
    `unar` is that; `macunpack` is not, since its method 7 has never run
    (BLOCKERS.md).
    """
    d = os.path.join(SPECIMENS, "wild")
    if not os.path.isdir(d):
        print("diskdoubler: no --wild --extract specimens, skipped")
        return 0
    if not shutil.which("unar"):
        print("diskdoubler: unar is not installed, wild specimens ungraded")
        return 0
    bad = 0
    for f in sorted(os.listdir(d)):
        if not f.endswith(".dd"):
            continue
        p = os.path.join(d, f)
        h = header(open(p, "rb").read())
        work = tempfile.mkdtemp(prefix="ddwild-")
        try:
            ours, theirs = os.path.join(work, "a"), os.path.join(work, "b")
            r = subprocess.run([cli(), "x", "--forks", "hidden", "-o", ours, p],
                               capture_output=True, text=True)
            subprocess.run(["unar", "-q", "-k", "hidden", "-o", theirs, p],
                           capture_output=True)
            # `unar -k hidden` writes the resource fork as an APPLEDOUBLE
            # file, our "._" sidecar is the fork itself, and unar omits an
            # empty data fork altogether. Compare the forks, not the files.
            # FORKS ONLY, not names: the single-file container carries
            # no name, so both tools take it from the host file — and
            # they read those bytes differently (we say Mac Roman, unar
            # says UTF-8), which makes "IACUtilities.π" disagree for a
            # reason that has nothing to do with decoding. What the name
            # rule does is checked by `test_diskdoubler` instead.
            mine = forks_of(ours, appledouble=False)
            oracle = forks_of(theirs, appledouble=True)
            same = sorted(mine.values()) == sorted(oracle.values()) and bool(mine)
            bad += not same or r.returncode != 0
            note = "unar agrees" if same else "DIFFERS from unar"
            if r.returncode != 0:
                note = "rc=%d %s" % (r.returncode, r.stderr.strip()[:60])
            print("  %-30s %-52s %s"
                  % (f[:30], describe(h) if h else "no header", note))
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return bad


def verify():
    """Decode every specimen with our own CLI and check it against the
    bytes that went in — the loop closed without an oracle: compressed on
    an emulated Mac, decoded here, compared with the input."""
    if not os.path.isdir(SPECIMENS):
        print("diskdoubler: no specimens yet — run --make")
        return 1
    want = {"": SUBJECT_DATA, ".rsrc": make_rsrc()}
    bad = seen = 0
    bad += verify_wild()
    for f in sorted(os.listdir(SPECIMENS)):
        if not f.endswith(".dd"):
            continue
        p = os.path.join(SPECIMENS, f)
        h = header(open(p, "rb").read())
        out = tempfile.mkdtemp(prefix="ddver-")
        try:
            r = subprocess.run([cli(), "x", "-o", out, p], capture_output=True,
                               text=True)
            names = sorted(os.listdir(out))
            for n in names:
                blob = open(os.path.join(out, n), "rb").read()
                ext = ".rsrc" if n.endswith(".rsrc") else ""
                if not blob and not want[ext]:
                    continue
                seen += 1
                same = blob == want[ext]
                bad += not same
                print("  %-20s %-8s %7d B  %s"
                      % (f, ext or "data", len(blob),
                         "EXACT" if same else "DIFFERS"))
            if r.returncode != 0:
                print("  %-20s rc=%d %s" % (f, r.returncode, r.stderr.strip()))
                bad += 1
        finally:
            shutil.rmtree(out, ignore_errors=True)
        print("  %-20s %s" % (f, describe(h) if h else "no header"))
    print("diskdoubler: %d fork(s) checked, %s"
          % (seen, "all exact" if not bad and seen else "%d wrong" % bad))
    return 1 if bad or not seen else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true", help="fetch the 3.7 disk")
    ap.add_argument("--wild", action="store_true",
                    help="report every compressed file on that disk")
    ap.add_argument("--extract", action="store_true",
                    help="with --wild, keep those files as specimens")
    ap.add_argument("--install", action="store_true",
                    help="build a System 7 image with the DiskDoubler INIT")
    ap.add_argument("--probe", action="store_true",
                    help="boot the application and photograph each step")
    ap.add_argument("--beta-probe", action="store_true",
                    help="boot the 1990 INIT and photograph every menu, "
                         "which is how --beta's coordinates are measured")
    ap.add_argument("--peek", metavar="X,X,...",
                    help="with --beta-probe, menu-title x positions to pull "
                         "down and photograph")
    ap.add_argument("--beta-verify", action="store_true",
                    help="grade the 1990 specimen against the bytes "
                         "DiskDoubler was given")
    ap.add_argument("--beta", action="store_true",
                    help="compress the subject with DiskDoubler ß05, 1990, "
                         "and report the header it writes")
    ap.add_argument("--probe-split", action="store_true",
                    help="photograph what the Split command asks for")
    ap.add_argument("--combine", nargs="?", const="tree",
                    choices=("tree", "raw"),
                    help="a DDAR archive: `tree` holds a folder, `raw` "
                         "offers the shapes that might be written with no "
                         "file header — the two record shapes no corpus "
                         "fixture has")
    ap.add_argument("--verify-combine", action="store_true",
                    help="grade the Combine specimens against their inputs")
    ap.add_argument("--make", metavar="METHOD", nargs="?", const="A",
                    help="compress the subject with A, B, guess or both")
    ap.add_argument("--verify", action="store_true",
                    help="decode the specimens and check them against the input")
    ap.add_argument("--adjudicate", metavar="FIXTURE",
                    help="run a self-extracting fixture under System 7 and "
                         "compare every fork it writes with ours (%s)"
                         % ", ".join(sorted(ADJUDICATE)))
    ap.add_argument("--write-manifest", action="store_true",
                    help="with --adjudicate, record the Mac's bytes for the "
                         "forks no oracle could grade")
    ap.add_argument("--keep", action="store_true", help="keep the work dir")
    args = ap.parse_args()
    if args.setup:
        fetch()
    if args.install:
        install()
    if args.wild:
        wild(args.extract)
    if args.probe:
        probe(args.keep)
    if args.beta_probe:
        return beta_probe(args.keep,
                          [int(x) for x in (args.peek or "").split(",") if x])
    if args.beta:
        return beta(args.keep)
    if args.beta_verify:
        return beta_verify()
    if args.probe_split:
        probe_split(args.keep)
    if args.make:
        make(args.make, args.keep)
    if args.combine:
        return combine(args.combine, args.keep)
    if args.verify_combine:
        return verify_combine()
    if args.adjudicate:
        return adjudicate(args.adjudicate, args.keep,
                          args.write_manifest)
    if args.verify:
        return verify()
    if not (args.setup or args.install or args.wild or args.probe
            or args.probe_split or args.make or args.verify
            or args.combine or args.verify_combine or args.adjudicate
            or args.beta or args.beta_probe or args.beta_verify):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

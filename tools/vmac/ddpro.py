#!/usr/bin/env python3
"""ddpro.py — drive DiskDoubler Pro 4.1 under Mini vMac.

`diskdoubler.py` runs DiskDoubler 3.7, whose two software methods are 1
and 8. DiskDoubler **Pro** 4.1 is the other half of the format: its
Settings dialog offers AD1, AD2, DD1, DD2 and DD3, which write methods 9,
6 and 10, and its archives are `DDA2` rather than `DDAR`. Two things in
OPEN_ITEMS.md need it, and neither can be answered by reading a file:

  * a `DDA2` **stored** entry with a RESOURCE fork. **ANSWERED
    2026-08-21: there is none, and there cannot be.** The `0x1000` form
    is written only when the data fork is stored AND the file has no
    resource fork, so `+87` never describes one; `+54` and `+58` are the
    creation and modification dates, also measured. Both by
    `tools/vmac/ndd.py --stored` and `--dates` (DECISIONS.md, the
    Symantec release). What `--experiments` here produced —
    an ordinary header with a stored data fork beside an AD1 resource
    fork — is half of that answer.
  * what the 4 bytes at `+4` of a `SPLT` header MEAN. **ANSWERED
    2026-08-21: the Mac's `TickCount` when the file was split.** They are
    equal across the parts of a set and different between sets, and no
    checksum of any fork or of the file accounts for them; splitting the
    same file twice, minutes apart, separated a content hash from a clock
    — three files split 72 s apart differ by 4,324 and 4,330 ticks
    (DECISIONS.md 2026-08-21, later still; FORMATS.md).

    tools/vmac/ddpro.py --setup        fetch 4.1 and unpack it
    tools/vmac/ddpro.py --install      a System 7 image with its Finder menu
    tools/vmac/ddpro.py --probe        photograph the menus and dialogs
    tools/vmac/ddpro.py --experiments  one session: archive an incompressible
                                       file that HAS a resource fork, then
                                       split three files
    tools/vmac/ddpro.py --check-stored describe the archive that came back

Nothing here runs in `ci.sh`, and nothing it fetches is committed — the
archive is commercial software, fetched by URL and checked by hash
exactly as the ROM and the System images are.
"""
import argparse
import hashlib
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
import run as R                                        # noqa: E402
from arcmac import macbinary                           # noqa: E402
from diskdoubler import (Session, cli, header, describe, make_volume,
                         make_rsrc, VOLUME_ICON)       # noqa: E402

PRO_URL = "https://old.mac.gdn/apps/DiskDoubler_Pro_4.1.sit_.hqx"
PRO_PAGE = "https://macintoshgarden.org/apps/diskdoubler-40"
PRO_SHA = "cafbc606bc8b9a6eaeb44d3707e382e90c8a665692249c5d5817c049c4e0ae47"

HOME = R.VMAC_HOME
WORK = os.path.join(HOME, "ddpro")
SPECIMENS = os.path.join(HOME, "specimens", "ddpro")
HQX = os.path.join(WORK, "ddpro41.hqx")
TREE = os.path.join(WORK, "tree")
BOOT = os.path.join(WORK, "ddproboot.hfv")

# The extension is the half that compresses: DiskDoubler puts its
# commands in the Finder's menu bar, exactly as 3.7's INIT does.
# Matched as a SUBSTRING, not spelled out: the name on the volume is
# "DD™ Finder Menu" in Mac Roman, and what lands in a Linux directory
# depends on how the CLI transcoded it. The words are stable; the bytes
# around them are not.
MENU_EXT = "Finder Menu"

# Two subjects for --stored. The JPEG-like one is incompressible so
# DiskDoubler Pro stores it, and unlike every stored entry seen so far it
# has a RESOURCE fork.
INCOMPRESSIBLE = bytes(bytearray(
    (i * 7 + (i * i) % 251 + (i >> 3)) & 0xFF for i in range(20000)))


def fetch():
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(HQX):
        subprocess.run(["curl", "-sS", "-L", "-A", "Mozilla/5.0",
                        "-e", PRO_PAGE, "-o", HQX, PRO_URL], check=True)
    got = hashlib.sha256(open(HQX, "rb").read()).hexdigest()
    print("ddpro: %s sha256 %s%s" % (os.path.basename(HQX), got,
                                     "" if got == PRO_SHA else "  MISMATCH"))
    if got != PRO_SHA:
        raise SystemExit("ddpro: the download is not the file this was "
                         "written against")
    shutil.rmtree(TREE, ignore_errors=True)
    os.makedirs(TREE)
    subprocess.run([cli(), "x", "--forks", "hidden", "-o", TREE, HQX],
                   check=True, capture_output=True)
    print("ddpro: unpacked into %s" % TREE)
    return TREE


def find(name):
    """(path, rsrc path) of one file in the unpacked tree, by substring."""
    for root, _d, files in os.walk(TREE):
        for f in sorted(files):
            if f.startswith("._"):
                continue
            if name in f:
                return (os.path.join(root, f),
                        os.path.join(root, "._" + f))
    raise SystemExit("ddpro: nothing matching %r in %s — run --setup"
                     % (name, TREE))


def type_creator(path):
    """The type and creator our own CLI reports for a file in the tree.

    Read from the archive listing rather than assumed: an extension with
    the wrong type is an extension System 7 will not load, and that
    failure looks exactly like the application not working.
    """
    tmp = tempfile.mkdtemp(prefix="ddpro-l-")
    try:
        # `l` does not recurse through an envelope — only `x` does — so
        # the BinHex layer has to come off before the StuffIt archive
        # inside it can be listed (TESTING.md).
        subprocess.run([cli(), "x", "-nr", "-o", tmp, HQX], check=True,
                       capture_output=True)
        inner = [os.path.join(tmp, f) for f in os.listdir(tmp)
                 if not f.startswith("._") and not f.endswith(".rsrc")]
        if not inner:
            return "INIT", "DDAP"
        r = subprocess.run([cli(), "l", inner[0]], capture_output=True,
                           text=True)
        for line in r.stdout.splitlines():
            f = line.split(None, 4)
            if len(f) == 5 and f[0] == "f" and MENU_EXT in f[4]:
                return f[3][:4], f[3][5:]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return "INIT", "DDAP"


def install():
    """A System 7 boot image with DiskDoubler Pro's Finder menu loaded."""
    if not os.path.isdir(TREE):
        fetch()
    data_p, rsrc_p = find(MENU_EXT)
    ftype, creator = type_creator(data_p)
    data = open(data_p, "rb").read()
    rsrc = open(rsrc_p, "rb").read() if os.path.exists(rsrc_p) else b""
    print("ddpro: %s — %s/%s, %d B data, %d B rsrc"
          % (MENU_EXT, ftype, creator, len(data), len(rsrc)))
    work = tempfile.mkdtemp(prefix="ddproinst-")
    try:
        mb = os.path.join(work, "ext.bin")
        open(mb, "wb").write(macbinary("DD\u2122 Finder Menu", ftype, creator,
                                       data, rsrc))
        shutil.copyfile(os.path.join(HOME, "Sys7.img"), BOOT)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            subprocess.run(["hmount", BOOT], check=True, capture_output=True,
                           env=env)
            subprocess.run(["hcopy", "-m", mb,
                            ":System Folder:Extensions:"], check=True,
                           capture_output=True, env=env)
            subprocess.run(["humount"], check=True, capture_output=True,
                           env=env)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("ddpro: boot image with the DiskDoubler Pro menu at %s" % BOOT)
    return BOOT


def app_files():
    """The DiskDoubler Pro application, as (name, type, creator, data,
    rsrc).

    The Finder menu is only the front end: "Create Archive…" puts up
    *The DiskDoubler application cannot be found. Please locate it.* if
    the application is not on a mounted volume (measured 2026-08-21).
    3.7 behaves the same way, which is why `diskdoubler.py` copies its
    application onto the work volume too.
    """
    data_p, rsrc_p = find("DiskDoubler")
    # The name is spelled out here rather than taken from the host file:
    # what a Mac Roman "™" became in a Linux directory depends on the
    # transcoding, and an application the extension looks for by name
    # would not be found under a mangled one.
    return [("DiskDoubler\u2122", "APPL", "DDAP",
             open(data_p, "rb").read(),
             open(rsrc_p, "rb").read() if os.path.exists(rsrc_p) else b"")]


def session(tag, files):
    """A booted Mac with the menu loaded and a work volume holding the
    application and `files`, each (name, type, creator, data, rsrc)."""
    files = app_files() + list(files)
    work = tempfile.mkdtemp(prefix="ddprowork-")
    mbs = []
    for i, (name, ftype, creator, data, rsrc) in enumerate(files):
        p = os.path.join(work, "f%d.bin" % i)
        open(p, "wb").write(macbinary(name, ftype, creator, data, rsrc))
        mbs.append(p)
    img = os.path.join(work, "ddprowork.img")
    # Room for the subjects AND for what DiskDoubler writes beside them:
    # a split leaves the original in place, so a 1 MB file needs 1 MB
    # more. The first run of --experiments had 1 MB free and the splits
    # had nowhere to go.
    need = sum(len(d) + len(r) for _, _, _, d, r in files) // 1024
    make_volume(img, "DDpro", mbs, size_kb=max(4096, need * 3 + 2048))
    if not os.path.exists(BOOT):
        install()
    s = Session(BOOT, [img], os.path.join(SPECIMENS, tag))
    return s, work, img


# The DD menu, measured off probe/04-menu-x281.png (System 7, 512x342).
DD_MENU_X = 281
DD_ITEM = {"compress": 27, "expand": 59, "split": 187,
           "archive": 219, "sea": 235, "settings": 283}

SUBJECTS_STORED = [
    ("Rough", "JPEG", "GKON", INCOMPRESSIBLE,
     make_rsrc(b"\x1eDiskDoubler Pro stored-fork probe")),
]

# Three files split in one session. Alpha and Beta are BYTE-IDENTICAL
# with different names; Zeta differs in both. The menu item says "Split
# File (760K)", so a subject has to be bigger than that to come out in
# more than one piece. Names start with different letters because the
# Finder is driven by type-select and "Twin A"/"Twin B" would not
# separate.
SPLIT_KB = 1000


def split_bytes(seed, kb=SPLIT_KB):
    out = bytearray()
    x = seed & 0xFFFFFFFF
    while len(out) < kb * 1024:
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        out += x.to_bytes(4, "big")
    return bytes(out[:kb * 1024])


SUBJECTS_SPLIT = [
    ("Alpha", "TEXT", "ttxt", split_bytes(1), b""),
    ("Beta", "TEXT", "ttxt", split_bytes(1), b""),
    ("Zeta", "TEXT", "ttxt", split_bytes(2, 900), b""),
]


def probe(keep=False):
    """Photograph the menu and the Settings dialog. Every coordinate any
    other mode here uses was measured off these frames."""
    s, work, img = session("probe", SUBJECTS_STORED + SUBJECTS_SPLIT)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        # The Finder menu bar with the extension loaded: photograph every
        # menu title in turn rather than guessing which one is DD's.
        for x in (250, 281, 300, 320):
            s.peek(x, "menu-x%d" % x)
    finally:
        time.sleep(3)
        s.close()
    print("ddpro: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def menu(s, item, tag):
    """Pull the DD menu down and release on one item."""
    ox, oy = s.mac.origin()
    x = s.mac._xdo
    x("mousemove", str(ox + DD_MENU_X), str(oy + 8))
    time.sleep(0.4)
    x("mousedown", "1")
    time.sleep(1.2)
    x("mousemove", str(ox + DD_MENU_X + 25), str(oy + DD_ITEM[item]))
    time.sleep(1.0)
    s.shot("pick-" + tag)
    x("mouseup", "1")
    time.sleep(2.0)


def select(s, letter):
    """Type-select a file in the front window by its first letter.

    Escape first, and never Return: **Return opens the selected icon's
    name for EDITING** in the System 7 Finder, and the next keystroke
    then types into the name box rather than selecting anything. That is
    how the first run of --experiments renamed its own subject to "a"
    (2026-08-21) — the Return that was meant for a report the archive
    step does not print.
    """
    s.mac.key("Escape")
    time.sleep(0.5)
    s.mac.key(letter)
    time.sleep(1.5)


def experiments(keep=False):
    """One session, two questions (see the module docstring).

    Order matters for the second one: Alpha and Beta hold the SAME bytes
    under different names and are split a minute or so apart, so what
    their `SPLT` identities do — equal, or different by about the ticks
    between them — is the measurement.
    """
    s, work, img = session("experiments", SUBJECTS_STORED + SUBJECTS_SPLIT)
    marks = []
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)

        # 1. an archive holding an incompressible file that HAS a
        #    resource fork: the `DDA2` stored entry nobody has seen.
        select(s, "r")
        s.shot("selected-rough", wait=2.0)
        menu(s, "archive", "create-archive")
        s.shot("archive-dialog", wait=8.0)
        s.mac.key("Return")
        s.shot("archive-done", wait=45.0)
        s.shot("after-archive", wait=10.0)

        # 2. three splits, timed.
        for letter, tag in (("a", "alpha"), ("b", "beta"), ("z", "zeta")):
            marks.append((tag, time.time()))
            select(s, letter)
            s.shot("selected-" + tag, wait=2.0)
            menu(s, "split", "split-" + tag)
            s.shot("split-%s-running" % tag, wait=40.0)
            s.shot("split-%s-done" % tag, wait=20.0)

        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")                   # Put Away: flush
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()

    for tag, t in marks:
        print("ddpro: %s split started at +%.0f s" % (tag, t - marks[0][1]))
    got = report(img, "exp")
    splt_headers(got)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def volume_files(img):
    """path tuple -> (type, creator, data, rsrc) for a whole volume."""
    from superdisk import read_forks                    # noqa: E402
    return read_forks(img)


def report(img, tag):
    """What came back on the work volume, described rather than trusted."""
    os.makedirs(SPECIMENS, exist_ok=True)
    got = volume_files(img)
    for path, (ftype, creator, data, rsrc) in sorted(got.items()):
        name = "/".join(p for p in path)
        h = header(data) or header(rsrc)
        print("  %-34s %s/%s %7d B data %6d B rsrc  %s"
              % (name[-34:], ftype, creator, len(data), len(rsrc),
                 describe(h) if h else ""))
        out = os.path.join(SPECIMENS, "%s-%s" % (tag, path[-1].replace("/", "_")))
        if data:
            open(out, "wb").write(data)
        if rsrc:
            open(out + ".rsrc", "wb").write(rsrc)
    return got


def splt_headers(got):
    """Print the `SPLT` header fields of every part on the volume."""
    rows = []
    for path, (_t, _c, data, _r) in sorted(got.items()):
        if len(data) < 94 or data[:4] != b"SPLT" or data[90:94] != b"SPLT":
            continue
        rows.append((path[-1],
                     struct.unpack_from(">I", data, 4)[0],
                     struct.unpack_from(">I", data, 8)[0],
                     struct.unpack_from(">I", data, 12)[0],
                     struct.unpack_from(">H", data, 40)[0],
                     struct.unpack_from(">H", data, 42)[0],
                     struct.unpack_from(">I", data, 32)[0],
                     struct.unpack_from(">I", data, 36)[0]))
    if not rows:
        print("ddpro: no SPLT parts on the volume")
        return rows
    print("  %-20s %10s %8s %8s %5s %5s %10s %10s"
          % ("part", "+4", "datalen", "rsrclen", "n", "idx", "mtime", "ctime"))
    for r in rows:
        print("  %-20s %10d %8d %8d %5d %5d %10d %10d" % r)
    ids = sorted(set(r[1] for r in rows))
    print("ddpro: %d part(s), %d distinct identity value(s): %s"
          % (len(rows), len(ids), ", ".join("0x%08X" % i for i in ids)))
    return rows


def check_stored(path=None):
    """Read the archive --experiments made and answer the two questions
    about a `DDA2` STORED entry that no corpus archive can.

    The record layout is DECISIONS.md 2026-08-21: `+54` and `+58` the
    two dates, `+62` type, `+66` creator, `+78` data length, `+82`
    resource length, `+86` and `+87` the forks' XOR checksums, payload
    at `+90`. What the corpus could not show is a stored entry with a
    RESOURCE fork: both stored files in every published archive are
    fork-less, so `+87` had only ever been 0.
    """
    if path is None:
        cands = sorted(f for f in os.listdir(SPECIMENS)
                       if f.endswith(".dd")) if os.path.isdir(SPECIMENS) else []
        if not cands:
            raise SystemExit("ddpro: no archive specimen — run --experiments")
        path = os.path.join(SPECIMENS, cands[0])
    blob = open(path, "rb").read()
    print("ddpro: %s, %d B" % (os.path.basename(path), len(blob)))
    want_data = SUBJECTS_STORED[0][3]
    want_rsrc = SUBJECTS_STORED[0][4]
    xor = lambda b: 0 if not b else __import__("functools").reduce(
        lambda a, c: a ^ c, b, 0)
    # Walk the DDA2 entry chain: the archive header is 8 bytes, each
    # record declares its own total size at +4 (DECISIONS.md).
    off = 8
    found = 0
    while off + 90 <= len(blob):
        total = struct.unpack_from(">I", blob, off + 4)[0]
        etype = struct.unpack_from(">H", blob, off + 2)[0]
        if total < 90 or off + total > len(blob):
            break
        if etype == 0x1000:                      # stored: no file header
            dlen = struct.unpack_from(">I", blob, off + 78)[0]
            rlen = struct.unpack_from(">I", blob, off + 82)[0]
            c1, c2 = blob[off + 86], blob[off + 87]
            d1 = struct.unpack_from(">I", blob, off + 54)[0]
            d2 = struct.unpack_from(">I", blob, off + 58)[0]
            data = blob[off + 90:off + 90 + dlen]
            rsrc = blob[off + 90 + dlen:off + 90 + dlen + rlen]
            print("  stored entry: %d B data, %d B rsrc" % (dlen, rlen))
            print("  +86 = 0x%02X, XOR of the data fork = 0x%02X  %s"
                  % (c1, xor(data), "MATCH" if c1 == xor(data) else "NO"))
            print("  +87 = 0x%02X, XOR of the rsrc fork = 0x%02X  %s"
                  % (c2, xor(rsrc), "MATCH" if c2 == xor(rsrc) else "NO"))
            print("  +54 = %u, +58 = %u, difference %d s" % (d1, d2, d1 - d2))
            print("  data fork is the file that went in: %s"
                  % (data == want_data))
            print("  rsrc fork is the file that went in: %s"
                  % (rsrc == want_rsrc))
            found += 1
        off += total
    if not found:
        print("  no stored (0x1000) entry in this archive")
    return 0 if found else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true", help="fetch 4.1")
    ap.add_argument("--install", action="store_true",
                    help="build a System 7 image with the Finder menu")
    ap.add_argument("--probe", action="store_true",
                    help="photograph the menus and dialogs")
    ap.add_argument("--check-stored", nargs="?", const="", metavar="ARCHIVE",
                    help="read the archive --experiments made and report "
                         "what its stored entry says")
    ap.add_argument("--experiments", action="store_true",
                    help="one session: an archive holding an incompressible "
                         "file with a resource fork, then three splits")
    ap.add_argument("--keep", action="store_true", help="keep the work dir")
    a = ap.parse_args()
    if a.setup:
        fetch()
    if a.install:
        install()
    if a.probe:
        probe(a.keep)
    if a.experiments:
        return experiments(a.keep)
    if a.check_stored is not None:
        return check_stored(a.check_stored or None)
    if not (a.setup or a.install or a.probe or a.experiments
            or a.check_stored is not None):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

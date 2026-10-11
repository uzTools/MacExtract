#!/usr/bin/env python3
"""privatefile.py — have Aladdin Private File 2.0 encrypt known files.

Private File (`.pf`) was the one format on Aladdin's engine list with no
specimen anywhere this project looked (OPEN_ITEMS.md history, DECISIONS.md
2026-10-08). This makes them the way SpaceSaver's and PackIt's were made:
run the writer under Mini vMac on known contents and known passwords, and
read the results back off the volume.

The application is NOT installed by its installer. `Aladdin Private File
Installer` is an InstallerMaker application whose data fork is a StuffIt
archive this engine already opens, and `PF Encrypt™` inside it is a plain
68K application with its cipher in its own `CODE` 4 ("ACL/Crypto") — no
StuffIt Engine, no extension. So it goes straight onto a copy of the
System 7.0.1 image, in `Startup Items`, and the Finder launches it at
boot: no icon to find, no type-select.

    tools/vmac/privatefile.py --fetch          download and unpack
    tools/vmac/privatefile.py --probe          boot and photograph
    tools/vmac/privatefile.py --make TAG       encrypt the subjects

Downloads live in ~/.cache/macextract/privatefile/ and are never committed.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                          # noqa: E402
from diskdoubler import Session, cli                     # noqa: E402
import synth_wrapped as W                                # noqa: E402

CACHE = os.path.expanduser("~/.cache/macextract/privatefile")
PAGE = "http://macintoshgarden.org/apps/aladdin-private-file-20"
URL = "https://old.mac.gdn/apps/private_file_2.0.sit"
SIT = os.path.join(CACHE, "private_file_2.0.sit")
INST = os.path.join(CACHE, "inst")
APP = "PF Encrypt™"
SPECIMENS = os.path.join(R.VMAC_HOME, "specimens", "privatefile")

# Known contents. Every byte value, a run, and a length that is not a
# multiple of anything a block cipher would want — so a stream cipher and
# a block cipher fail differently on it.
ALPHA = (b"Private File 2.0 encrypted this, under Mini vMac.\r" * 6 +
         bytes(range(256)) + bytes(37))
FORKED_DATA = b"data fork of Forked\r" * 20
FORKED_RSRC = b"RSRC" + bytes(range(200)) * 3 + b"tail"

# (name, type, creator, data, rsrc, password). The password is what is
# typed for that file. SIX characters at least: GetNewPassword dims OK
# while the field holds fewer (`cmpi.b #6`, CODE 4 @0x3e76), and the
# first walk typed "abc" into a dialog that then ignored Return.
SUBJECTS = [
    ("Alpha", b"TEXT", b"ttxt", ALPHA, b"", "swordfish"),
    ("Forked", b"PICT", b"8BIM", FORKED_DATA, FORKED_RSRC, "hushnow"),
    # An EMPTY data fork, and a password longer than an MD5 block's
    # worth of nothing in particular — the key is still five bytes.
    ("Gamma", b"rsrc", b"RSED", b"", FORKED_RSRC[::-1],
     "correct-horse-battery"),
]


# PF Encrypt's menu bar, measured off probe/03: Apple, then File, whose
# first item is Encrypt… A Command key sent before anything has clicked
# the emulator window never arrives (no window manager gives it focus),
# so the first action is a menu pick by mouse.
FILE_X = 53
ENCRYPT_Y = 28


# The Encrypt picker, measured off probe/04: its own dialog, not
# Standard File — a file list on the left, "Items to Encrypt" on the
# right, Add between them. It opens in the APPLICATION's folder, which
# here is Startup Items, so the way to the subjects is Desktop and then
# the volume.
PICK_DESKTOP = (257, 121)
PICK_ADD = (257, 180)
PICK_ENCRYPT = (458, 290)
PICK_ROW1 = (100, 72)
PICK_ROW_H = 16


def pick_row(s, n, double=False):
    s.mac.click(PICK_ROW1[0], PICK_ROW1[1] + n * PICK_ROW_H, double=double)
    time.sleep(0.8)


def fetch():
    os.makedirs(CACHE, exist_ok=True)
    if not os.path.exists(SIT):
        subprocess.run(["curl", "-sS", "-L", "-A", "Mozilla/5.0", "-e",
                        PAGE, "-o", SIT, URL], check=True)
    x = os.path.join(CACHE, "x")
    shutil.rmtree(x, ignore_errors=True)
    subprocess.run([cli(), "x", "-o", x, SIT], check=True)
    inst = [os.path.join(r, f) for r, _d, fs in os.walk(x) for f in fs
            if f == "Aladdin Private File Installer"][0]
    shutil.rmtree(INST, ignore_errors=True)
    # --overwrite: the payload names `PF Encrypt™` twice, a 312-byte
    # placeholder first and the application last, and the last one wins.
    subprocess.run([cli(), "x", "--overwrite", "-o", INST, inst],
                   check=True)


def app_macbinary(work):
    rsrc = open(os.path.join(INST, APP + ".rsrc"), "rb").read()
    p = os.path.join(work, "app.bin")
    open(p, "wb").write(W.macbinary(APP, b"", rsrc, b"APPL", b"CStf"))
    return p


def boot_image(work, subjects=SUBJECTS):
    if not os.path.exists(os.path.join(INST, APP + ".rsrc")):
        fetch()
    boot = os.path.join(work, "boot.hfv")
    shutil.copyfile(os.path.join(R.VMAC_HOME, "Sys7.img"), boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        def h(*a):
            subprocess.run(list(a), check=True, capture_output=True, env=env)
        h("hmount", boot)
        h("hmkdir", ":System Folder:Startup Items")
        h("hcopy", "-m", app_macbinary(work),
          ":System Folder:Startup Items:".encode("mac_roman"))
        for i, (n, t, c, d, r, _pw) in enumerate(subjects):
            p = os.path.join(work, "s%d.bin" % i)
            open(p, "wb").write(W.macbinary(n, d, r, t, c))
            h("hcopy", "-m", p, ":")
        h("humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    return boot


def probe(keep=False):
    work = tempfile.mkdtemp(prefix="pf-")
    s = Session(boot_image(work), [], os.path.join(SPECIMENS, "probe"))
    try:
        s.boot()
        s.shot("booted", wait=10.0)
        s.shot("booted-2", wait=20.0)
        s.menu(FILE_X, ENCRYPT_Y, "file-menu")
        s.shot("encrypt-dialog", wait=8.0)
        s.mac.click(*PICK_DESKTOP)
        s.shot("desktop-level", wait=3.0)
        pick_row(s, 0, double=True)
        s.shot("volume-level", wait=4.0)
    finally:
        time.sleep(2)
        s.close()
    print("privatefile: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# The Finder's Special menu on this image (sitcrypt.py measured both):
# 139, not 123, which is Restart.
SPECIAL_X = 225
SHUT_DOWN_Y = 139
QUIT_Y = 76                    # PF Encrypt's File menu, fourth item


def encrypt_one(s, row, password, tag):
    """File ▸ Encrypt…, the subject at `row` of the volume, the password
    twice. Every step photographed: the password dialog's shape is only
    knowable by looking."""
    s.menu(FILE_X, ENCRYPT_Y, tag + "-menu")
    s.shot(tag + "-picker", wait=6.0)
    s.mac.click(*PICK_DESKTOP)
    time.sleep(2.0)
    pick_row(s, 0, double=True)            # the volume
    time.sleep(3.0)
    pick_row(s, row)
    s.mac.click(*PICK_ADD)
    s.shot(tag + "-added", wait=2.0)
    s.mac.click(*PICK_ENCRYPT)
    s.shot(tag + "-password", wait=6.0)
    s.mac._xdo("type", "--delay", "150", password)
    s.shot(tag + "-typed", wait=1.0)
    s.mac.key("Return")
    s.shot(tag + "-verify", wait=4.0)
    s.mac._xdo("type", "--delay", "150", password)
    s.mac.key("Return")
    s.shot(tag + "-done", wait=20.0)


def harvest(boot, out):
    """Every file on the volume's root that was not put there, as
    MacBinary — the subjects' encrypted twins, whatever they are named."""
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    got = []
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        names = subprocess.run(["hls", "-1a"], check=True,
                               capture_output=True, env=env).stdout
        before = {n for n, *_ in SUBJECTS} | {
            "Desktop Folder", "HyperCard", "Read Me", "SimpleText",
            "System Folder", "Trash", "Desktop DB", "Desktop DF",
            "Desktop"}
        for raw in names.split(b"\n"):
            n = raw.decode("mac_roman")
            if not n or n in before:
                continue
            dst = os.path.join(out, n.replace("/", ":") + ".bin")
            subprocess.run(["hcopy", "-m", ":" .encode() + raw, dst],
                           check=True, capture_output=True, env=env)
            got.append(dst)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    return got


def make(tag, keep=False):
    work = tempfile.mkdtemp(prefix="pf-")
    shots = os.path.join(SPECIMENS, tag)
    s = Session(boot_image(work), [], shots)
    try:
        s.boot()
        s.shot("booted", wait=25.0)
        # Last row first: a finished `.pf` lands beside its original
        # and sorts after it, so encrypting row 0 first would move row 1.
        for row in reversed(range(len(SUBJECTS))):
            n, *_r, pw = SUBJECTS[row]
            encrypt_one(s, row, pw, n.lower())
        s.menu(FILE_X, QUIT_Y, "quit")
        s.shot("quit", wait=8.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=40.0)
    finally:
        time.sleep(5)
        s.close()
    got = harvest(os.path.join(s.work, "boot.hfv"), shots)
    print("privatefile: screenshots in %s" % shots)
    for g in got:
        print("privatefile: lifted %s (%d B)" % (g, os.path.getsize(g)))
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return got


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--make", metavar="TAG")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if a.fetch:
        fetch()
    elif a.make:
        make(a.make, a.keep)
    elif a.probe:
        probe(a.keep)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()

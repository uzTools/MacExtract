#!/usr/bin/env python3
"""spacesaver.py — run Aladdin's SpaceSaver under Mini vMac.

StuffIt SpaceSaver is one of the two formats this project cannot even
NAME: no reference implementation, no published layout, and no specimen,
so `unc_sniff` answers *unknown* and OPEN_ITEMS.md has carried it since
the section existed.

It is reachable. SpaceSaver ships inside StuffIt Deluxe, and the
Deluxe 5.0.1 CD-ROM on Macintosh Garden carries a **standalone
`SpaceSaver 5.0 Installer`** beside it — one installer on one volume,
where the 3.5.1 and 4.0 distributions are two-floppy InstallerMaker sets.

    tools/vmac/spacesaver.py --setup     fetch the CD, lift the installer
    tools/vmac/spacesaver.py --probe     boot with it and photograph
    tools/vmac/spacesaver.py --install   run the installer
    tools/vmac/spacesaver.py --make      compress a subject, keep the file

The goal in order of value: a specimen at all (which is what makes the
format nameable), then what marks a compressed file, then the container.
The route the container would take is the one SuperDisk! and DiskDoubler
Pro both took — read it out of the software that writes it, and grade by
compressing known bytes.

Nothing here runs in `ci.sh`, and nothing it fetches is committed.
"""
import argparse
import hashlib
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
import run as R                                        # noqa: E402
from arcmac import macbinary                           # noqa: E402
from diskdoubler import (cli, Session, make_volume, make_rsrc,
                         VOLUME_ICON)                  # noqa: E402

# The StuffIt Deluxe 5.0.1 CD, which is where a standalone SpaceSaver
# installer lives. 156 MB zipped; the ISO inside is Apple-partitioned and
# `hmount` opens it directly.
CD_URL = "https://old.mac.gdn/apps/STUFFIT_DLX_SS_501.iso_.zip"
CD_PAGE = "https://macintoshgarden.org/apps/stuffit-deluxe"

HOME = R.VMAC_HOME
WORK = os.path.join(HOME, "spacesaver")
SPECIMENS = os.path.join(HOME, "specimens", "spacesaver")
ZIP = os.path.join(WORK, "ss501.zip")
ISO = os.path.join(WORK, "STUFFIT_DLX_SS_501.ISO")
INSTALLER = os.path.join(WORK, "ss5-installer.bin")
BOOT = os.path.join(WORK, "ssboot.hfv")


def fetch():
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(ISO):
        if not os.path.exists(ZIP):
            subprocess.run(["curl", "-sS", "-L", "-A", "Mozilla/5.0",
                            "-e", CD_PAGE, "-o", ZIP, CD_URL], check=True)
        subprocess.run(["7z", "x", "-y", "-o" + WORK, ZIP],
                       check=True, capture_output=True)
    print("spacesaver: ISO %d bytes" % os.path.getsize(ISO))
    if not os.path.exists(INSTALLER):
        lift_installer()
    print("spacesaver: installer %d bytes at %s"
          % (os.path.getsize(INSTALLER), INSTALLER))
    return INSTALLER


def lift_installer():
    """Copy the standalone SpaceSaver installer off the CD.

    Its name carries a Mac Roman '®', so the name goes to `hcopy` as the
    RAW BYTES `hls` printed — the rule `superdisk.read_forks` already
    records, and the reason a folder called "Terrainman 2.0 ƒ" was once
    silently skipped.
    """
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        subprocess.run(["hmount", ISO], check=True, capture_output=True,
                       env=env)
        names = subprocess.run(["hls", "-1"], capture_output=True,
                               env=env).stdout.split(b"\n")
        for x in names:
            if b"SpaceSaver" in x and b"Installer" in x:
                subprocess.run([b"hcopy", b"-m", b":" + x,
                                INSTALLER.encode()], check=True,
                               capture_output=True, env=env)
                return
        raise SystemExit("spacesaver: no SpaceSaver installer on the CD")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


SUBJECT = (b"SpaceSaver probe. " * 500 + bytes(bytearray(range(256))) * 8)

SUBJECTS = [("Alpha", "TEXT", "ttxt", SUBJECT, b""),
            ("Forked", "PICT", "8BIM", SUBJECT[:3000],
             make_rsrc(b"\x1eSpaceSaver probe fork"))]


def session(tag, with_installer=True):
    work = tempfile.mkdtemp(prefix="sswork-")
    mbs = []
    if with_installer:
        p = os.path.join(work, "inst.bin")
        shutil.copyfile(INSTALLER, p)
        mbs.append(p)
    for i, (n, t, c, d, r) in enumerate(SUBJECTS):
        p = os.path.join(work, "s%d.bin" % i)
        open(p, "wb").write(macbinary(n, t, c, d, r))
        mbs.append(p)
    img = os.path.join(work, "sswork.img")
    make_volume(img, "SSwork", mbs, size_kb=16384)
    if not os.path.exists(BOOT):
        shutil.copyfile(os.path.join(HOME, "Sys7.img"), BOOT)
    s = Session(BOOT, [img], os.path.join(SPECIMENS, tag))
    return s, work, img


def probe(keep=False):
    """Boot with the installer on a volume and launch it.

    The open question this answers first is whether a 1998 installer runs
    on System 7.0.1 at all — SpaceSaver 5.0 may want 7.5. A refusal here
    is a result, not a failure: it says the 3.5.1 or 4.0 two-floppy set
    is the route instead.
    """
    if not os.path.exists(INSTALLER):
        fetch()
    s, work, img = session("probe")
    try:
        s.boot()
        s.shot("desktop", wait=6.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "inst")
        time.sleep(1.5)
        s.shot("selected", wait=0.5)
        s.mac.command_key("o")
        s.shot("launched", wait=30.0)
        s.shot("launched-2", wait=15.0)
    finally:
        time.sleep(3)
        s.close()
    print("spacesaver: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# Measured off the install frames (System 7, 512x342).
CONTINUE = (313, 260)
AGREE = (458, 314)          # the licence panel's default button
ANYWAY_YES = (323, 140)     # "requires 7.5.3 ... Install anyway?"


def launch_installer(s):
    s.boot()
    s.shot("desktop", wait=6.0)
    s.mac.click(*VOLUME_ICON, double=True)
    s.shot("volume", wait=10.0)
    s.mac.key("Escape")
    time.sleep(0.6)
    s.mac._xdo("type", "--delay", "120", "inst")
    time.sleep(1.5)
    s.mac.command_key("o")
    s.shot("launched", wait=30.0)


def install(keep=False):
    """Walk the installer, photographing every step.

    Written to photograph rather than to assume: an InstallerMaker flow
    is splash, then some number of panels, then a destination, and the
    only way to learn which buttons exist is to look. Return is pressed
    at each stage because InstallerMaker's default button is the one that
    advances — and unlike the Finder, a dialog is where Return is safe.
    """
    if not os.path.exists(INSTALLER):
        fetch()
    s, work, img = session("install")
    try:
        launch_installer(s)
        s.mac.click(*CONTINUE)
        # The licence panel is slow to come up and slower to take a
        # keystroke. Pressing Return too early does nothing, and the next
        # frame then shows the licence still on screen — which reads as
        # "Agree was not the default button" and is not.
        s.shot("licence", wait=30.0)
        # CLICK Agree rather than pressing Return. Return is the default
        # button by the heavy border and does eventually work, but not
        # reliably on the first press — three runs pressed it and
        # photographed the licence still on screen afterwards. Both
        # buttons here are measured off the frames, not estimated.
        # The FIRST input this panel receives is swallowed — a click on
        # Agree and a Return both leave it on screen, and the first walk
        # only got past it on its second Return. So send both: the click
        # wakes the window, the Return activates the default button.
        s.mac.click(*AGREE)
        time.sleep(8.0)
        s.mac.key("Return")
        # The version alert arrives well after the licence closes. A
        # click sent too early lands on nothing, and the frame after it
        # shows the alert still up — which reads as "the click missed the
        # button" rather than "the button was not there yet".
        s.shot("after-agree", wait=30.0)
        # "This software requires system software version 7.5.3, which
        # this system does not have. Install anyway?" — the default is
        # NO, so a blind Return quits the installer. That is what the
        # first walk did, and the frame after it looks exactly like a
        # finished install: the Finder, with the volume open.
        # TWO "Install anyway?" alerts, not one: System 7.5.3 required
        # (we have 7.0.1) and 8000K of physical memory required (the
        # emulated Plus has 4 MB). Both default to No.
        for i in range(3):
            s.mac.click(*ANYWAY_YES)
            s.shot("anyway%d" % i, wait=18.0)
        for i in range(5):
            s.mac.key("Return")
            s.shot("step%d" % i, wait=18.0)
    finally:
        time.sleep(5)
        s.close()
    print("spacesaver: screenshots in %s" % s.shots)
    print("spacesaver: boot image kept at %s — a second run reuses it, so "
          "whatever the installer wrote is still there" % BOOT)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# StuffIt Deluxe 3.5.1: a two-floppy InstallerMaker set, and the era
# System 7.0.1 actually fits. Both floppies are mounted at once, so the
# swap the installer would otherwise ask for never happens.
D351 = os.path.join(WORK, "disks", "StuffIt Deluxe 3.5.1")
SPLASH_CONTINUE = (313, 263)
WELCOME_CONTINUE = (460, 314)   # the read-me panel, which comes BEFORE
                                # the registration one — a walk that
                                # assumed otherwise typed a name into the
                                # read-me and then clicked Register on an
                                # empty form
REG_NAME = (300, 124)
REG_ORG = (300, 146)
REG_NUMBER = (300, 170)
REG_REGISTER = (374, 204)
INSTALLER_ICON = (145, 120)     # measured off the frame, not estimated: an
                                # earlier guess of (168, 115) landed right of
                                # the glyph and selected the volume behind it


def disks351():
    d1 = os.path.join(D351, "StuffIt Deluxe\u2122 Disk 1.hfv")
    d2 = os.path.join(D351, "StuffIt Deluxe\u2122 Disk 2.hfv")
    for d in (d1, d2):
        if not os.path.exists(d):
            raise SystemExit("spacesaver: %s missing — run --setup351" % d)
    return d1, d2


def setup351():
    """Fetch StuffIt Deluxe 3.5.1 and lay its two floppies out raw.

    The download is a MacBinary wrapping a `.sea` wrapping two DiskCopy
    4.2 images; the 84-byte DiskCopy header comes off so Mini vMac can
    mount them, the same step `diskdoubler.fetch` makes.
    """
    import struct
    os.makedirs(WORK, exist_ok=True)
    sea = os.path.join(WORK, "sd351.sea.bin")
    if not os.path.exists(sea):
        subprocess.run(["curl", "-sS", "-L", "-A", "Mozilla/5.0", "-e",
                        CD_PAGE, "-o", sea,
                        "https://old.mac.gdn/apps/stuffit-deluxe-351-sea.bin"],
                       check=True)
    inner = os.path.join(WORK, "t")
    shutil.rmtree(inner, ignore_errors=True)
    os.makedirs(inner)
    subprocess.run([cli(), "x", "-nr", "-o", inner, sea], check=True,
                   capture_output=True)
    seaf = [os.path.join(inner, f) for f in os.listdir(inner)
            if f.endswith(".sea")][0]
    out = os.path.join(WORK, "disks")
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run([cli(), "x", "-o", out, seaf], check=True,
                   capture_output=True)
    for root, _d, files in os.walk(out):
        for f in files:
            if not f.endswith(".img") or f.startswith("._"):
                continue
            p = os.path.join(root, f)
            b = open(p, "rb").read()
            dlen = struct.unpack_from(">I", b, 64)[0]
            open(p[:-4] + ".hfv", "wb").write(b[84:84 + dlen])
            print("spacesaver: %s -> %d bytes of HFS" % (f, dlen))
    return disks351()


def probe351(keep=False):
    """Boot with both floppies mounted and photograph the desktop."""
    d1, d2 = disks351()
    work = tempfile.mkdtemp(prefix="sswork-")
    mbs = []
    for i, (n, t, c, d, r) in enumerate(SUBJECTS):
        q = os.path.join(work, "s%d.bin" % i)
        open(q, "wb").write(macbinary(n, t, c, d, r))
        mbs.append(q)
    img = os.path.join(work, "sswork.img")
    make_volume(img, "SSwork", mbs, size_kb=16384)
    if not os.path.exists(BOOT):
        shutil.copyfile(os.path.join(HOME, "Sys7.img"), BOOT)
    s = Session(BOOT, [d1, d2, img], os.path.join(SPECIMENS, "probe351"))
    try:
        s.boot()
        s.shot("desktop", wait=8.0)
        s.shot("desktop-2", wait=6.0)
    finally:
        time.sleep(3)
        s.close()
    print("spacesaver: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def session351(tag):
    d1, d2 = disks351()
    work = tempfile.mkdtemp(prefix="sswork-")
    mbs = []
    for i, (n, t, c, d, r) in enumerate(SUBJECTS):
        q = os.path.join(work, "s%d.bin" % i)
        open(q, "wb").write(macbinary(n, t, c, d, r))
        mbs.append(q)
    img = os.path.join(work, "sswork.img")
    make_volume(img, "SSwork", mbs, size_kb=16384)
    if not os.path.exists(BOOT):
        shutil.copyfile(os.path.join(HOME, "Sys7.img"), BOOT)
    s = Session(BOOT, [d1, d2, img], os.path.join(SPECIMENS, tag))
    return s, work, img


def install351(keep=False):
    """Run StuffIt Deluxe 3.5.1's installer with both floppies mounted.

    Disk 1's window opens itself on boot with the installer in it, so the
    walk starts with a type-select. Every step is photographed because an
    InstallerMaker flow is only knowable by looking, and because a blind
    Return is what quit the 5.0 installer on an alert whose default was
    No.
    """
    s, work, img = session351("install351")
    try:
        s.boot()
        s.shot("desktop", wait=8.0)
        # Double-click the icon rather than type-select it: Disk 1's
        # window opens itself on boot but does not take the keyboard, so
        # Escape-then-type selected nothing and Cmd-O opened nothing —
        # and the frame after that is the Finder, which looks exactly
        # like an installer that has not drawn yet.
        s.mac.click(*INSTALLER_ICON, double=True)
        s.shot("launched", wait=35.0)
        s.mac.click(*SPLASH_CONTINUE)
        s.shot("welcome", wait=20.0)
        s.mac.click(*WELCOME_CONTINUE)
        s.shot("registration", wait=20.0)
        # A registration panel: name, organization, registration number,
        # Cancel and Register. Whether the number is REQUIRED is the
        # question — try a name and organization alone first rather than
        # assuming, because the alternative is looking for a serial and
        # that is a different thing from reading a file format.
        s.mac.click(*REG_NAME)
        time.sleep(1.0)
        s.mac._xdo("type", "--delay", "120", "unclassic")
        s.mac.click(*REG_ORG)
        time.sleep(1.0)
        s.mac._xdo("type", "--delay", "120", "test")
        for code in CODES_35:
            s.mac.click(*REG_NUMBER)
            time.sleep(1.0)
            for _ in range(40):
                s.mac.key("BackSpace")      # Cmd-A does not select here
            time.sleep(1.0)
            s.mac._xdo("type", "--delay", "120", code)
            time.sleep(1.5)
            # Twice: every panel in this installer swallows its first
            # input, Register included.
            s.mac.click(*REG_REGISTER)
            time.sleep(6.0)
            s.mac.click(*REG_REGISTER)
            s.shot("try-" + code[:9], wait=22.0)
            s.mac.click(*REG_OK)            # dismiss "invalid", if shown
            time.sleep(3.0)
        s.shot("after-register", wait=15.0)
        for i in range(6):
            s.mac.key("Return")
            s.shot("step%d" % i, wait=20.0)
    finally:
        time.sleep(5)
        s.close()
    print("spacesaver: screenshots in %s" % s.shots)
    print("spacesaver: boot image kept at %s" % BOOT)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


D40 = os.path.join(WORK, "d40")

# Published on Macintosh Garden's StuffIt Deluxe page for these
# discontinued versions. "S" + five digits is the 3.0.7 scheme and 3.5.1
# rejects it, so the DLX forms are tried too — several per boot, because
# a boot is ten minutes and a wrong guess is cheap only if it shares one.
# For 3.5 specifically. The Garden page's own codes are for 3.0.7 ("S"
# and five digits) and 5.x (DLXF-/DLXG-), and 3.5.1 and 4.0 reject every
# one of them.
CODES_35 = ["DLXC-963-029519", "DLXC-907-029528"]
CODES = ["S12345", "DLXF-0859-006229", "DLXG-1112-268709",
         "DLXF-0835-001225"]

REG_OK = (356, 143)          # the "invalid" alert's OK button


def disks40():
    out = []
    for root, _d, files in os.walk(D40):
        for f in sorted(files):
            if f.endswith(".img") and not f.startswith("._") \
                    and "Updater" not in f:
                out.append(os.path.join(root, f))
    if not out:
        raise SystemExit("spacesaver: no 4.0 disks — run --setup40")
    return out


def setup40():
    os.makedirs(WORK, exist_ok=True)
    sit = os.path.join(WORK, "sd40.sit")
    if not os.path.exists(sit):
        subprocess.run(["curl", "-sS", "-L", "-A", "Mozilla/5.0", "-e",
                        CD_PAGE, "-o", sit,
                        "https://old.mac.gdn/apps/StuffIt_Deluxetm_4.0.sit"],
                       check=True)
    shutil.rmtree(D40, ignore_errors=True)
    subprocess.run([cli(), "x", "-o", D40, sit], check=True,
                   capture_output=True)
    for d in disks40():
        print("spacesaver: %s (%d B)" % (os.path.basename(d),
                                         os.path.getsize(d)))
    return disks40()


def install40(keep=False):
    """Run StuffIt Deluxe 4.0's installer, trying each published code.

    Same shape as 3.5.1's — splash, read-me, registration — but untried,
    and its disks are already raw HFS so no DiskCopy header comes off.
    Every code is tried inside ONE boot: the invalid-number alert has an
    OK button, so the form can be cleared and retyped without starting
    the machine again.
    """
    disks = disks40()
    work = tempfile.mkdtemp(prefix="sswork-")
    mbs = []
    for i, (n, t, c, d, r) in enumerate(SUBJECTS):
        q = os.path.join(work, "s%d.bin" % i)
        open(q, "wb").write(macbinary(n, t, c, d, r))
        mbs.append(q)
    img = os.path.join(work, "sswork.img")
    make_volume(img, "SSwork", mbs, size_kb=16384)
    if not os.path.exists(BOOT):
        shutil.copyfile(os.path.join(HOME, "Sys7.img"), BOOT)
    s = Session(BOOT, disks + [img], os.path.join(SPECIMENS, "install40"))
    try:
        s.boot()
        s.shot("desktop", wait=10.0)
        # 4.0's disk does NOT open its own window the way 3.5.1's does,
        # so the volume is opened first. Without this the installer click
        # lands on bare desktop and every step after it photographs an
        # empty Finder — which reads as "the installer quit".
        s.mac.click(470, 165, double=True)
        s.shot("volume-open", wait=12.0)
        s.mac.click(*INSTALLER_ICON, double=True)
        s.shot("launched", wait=35.0)
        s.mac.click(*SPLASH_CONTINUE)
        s.shot("welcome", wait=20.0)
        s.mac.click(*WELCOME_CONTINUE)
        s.shot("registration", wait=20.0)
        s.mac.click(*REG_NAME)
        time.sleep(1.0)
        s.mac._xdo("type", "--delay", "120", "unclassic")
        for code in CODES:
            s.mac.click(*REG_NUMBER)
            time.sleep(1.0)
            # Cmd-A does NOT select the text in a System 7 dialog field:
            # one run typed all four codes into it end to end
            # ("S12345DLXF-085DLXF-0835-001225DLX...") and tested none of
            # them. Backspace enough times to empty it instead.
            for _ in range(40):
                s.mac.key("BackSpace")
            time.sleep(1.0)
            s.mac._xdo("type", "--delay", "120", code)
            time.sleep(1.5)
            s.mac.click(*REG_REGISTER)
            time.sleep(5.0)
            s.mac.click(*REG_REGISTER)
            s.shot("try-" + code[:8], wait=18.0)
            s.mac.click(*REG_OK)              # dismiss "invalid", if shown
            time.sleep(3.0)
        s.shot("after-codes", wait=10.0)
    finally:
        time.sleep(5)
        s.close()
    print("spacesaver: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


INSTALLED = os.path.join(WORK, "ssinstalled.hfv")


def keep_installed():
    """Save the emulator's working copy of the boot image.

    `run.py` boots from a COPY so every run starts pristine — which is
    right for replaying fixtures and wrong for an installer, whose whole
    output is the change to that image. The copy lives in the Session's
    temp dir and survives the run, so it is lifted out afterwards. A
    check of the ORIGINAL boot image after an install shows nothing and
    reads as "the installer did not write anything".
    """
    import glob
    cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"), key=os.path.getmtime)
    if not cands:
        raise SystemExit("spacesaver: no session copy found")
    shutil.copyfile(cands[-1], INSTALLED)
    print("spacesaver: kept %s (%d B)" % (INSTALLED, os.path.getsize(INSTALLED)))
    return INSTALLED


def probe_installed(keep=False):
    """Boot the image SpaceSaver was installed into and look around.

    SpaceSaver is `cdev/SMKR` in Control Panels; StuffIt Deluxe also puts
    `~Magic Menu` there, which is what adds Finder commands. Which of the
    two compresses a file is the question.
    """
    if not os.path.exists(INSTALLED):
        raise SystemExit("spacesaver: no installed image — run --install351 "
                         "then --keep-installed")
    work = tempfile.mkdtemp(prefix="sswork-")
    mbs = []
    for i, (n, t, c, d, r) in enumerate(SUBJECTS):
        q = os.path.join(work, "s%d.bin" % i)
        open(q, "wb").write(macbinary(n, t, c, d, r))
        mbs.append(q)
    img = os.path.join(work, "sswork.img")
    make_volume(img, "SSwork", mbs, size_kb=16384)
    s = Session(INSTALLED, [img], os.path.join(SPECIMENS, "installed"))
    try:
        s.boot()
        s.shot("desktop", wait=12.0)
        for x in (250, 281, 310, 340, 370):
            s.peek(x, "menu-x%d" % x)
    finally:
        time.sleep(3)
        s.close()
    print("spacesaver: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# The Magic Menu, measured off installed/03-menu-x281.png. SpaceSaver
# itself is a control panel with no commands of its own; Magic Menu is
# what puts "SpaceSaver Compress" in the Finder's menu bar.
MAGIC_X = 283
MAGIC_COMPRESS_Y = 104


def make(keep=False):
    """Compress subjects with SpaceSaver and keep what it wrote."""
    if not os.path.exists(INSTALLED):
        raise SystemExit("spacesaver: no installed image")
    work = tempfile.mkdtemp(prefix="sswork-")
    mbs = []
    for i, (n, t, c, d, r) in enumerate(SUBJECTS):
        q = os.path.join(work, "s%d.bin" % i)
        open(q, "wb").write(macbinary(n, t, c, d, r))
        mbs.append(q)
    img = os.path.join(work, "sswork.img")
    make_volume(img, "SSwork", mbs, size_kb=16384)
    s = Session(INSTALLED, [img], os.path.join(SPECIMENS, "make"))
    try:
        s.boot()
        s.shot("desktop", wait=12.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=12.0)
        for name, letter in (("Alpha", "a"), ("Forked", "f")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac.key(letter)
            time.sleep(1.5)
            s.shot("selected-" + name, wait=0.5)
            ox, oy = s.mac.origin()
            x = s.mac._xdo
            x("mousemove", str(ox + MAGIC_X), str(oy + 8))
            time.sleep(0.5)
            x("mousedown", "1")
            time.sleep(1.5)
            x("mousemove", str(ox + MAGIC_X + 40),
              str(oy + MAGIC_COMPRESS_Y))
            time.sleep(1.2)
            s.shot("pick-" + name)
            x("mouseup", "1")
            s.shot("compressed-" + name, wait=30.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    report_make(img, s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def report_make(img, shots):
    from superdisk import read_forks                    # noqa: E402
    os.makedirs(shots, exist_ok=True)
    known = dict((n, (d, r)) for n, _t, _c, d, r in SUBJECTS)
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(img).items()):
        name = "/".join(path)
        orig = known.get(path[-1])
        mark = ""
        if orig and (len(data) != len(orig[0]) or data != orig[0]):
            mark = "  CHANGED (was %d B)" % len(orig[0])
            out = os.path.join(shots, path[-1] + ".ss")
            open(out, "wb").write(data)
            if rsrc:
                open(out + ".rsrc", "wb").write(rsrc)
            mark += " -> kept %s" % out
        print("spacesaver: %-24s %s/%s %8d %8d%s"
              % (name, ftype, creator, len(data), len(rsrc), mark))
        if data[:8]:
            print("             first16 %s" % data[:16].hex())


def panel(keep=False):
    """Open the SpaceSaver control panel and photograph it.

    "SpaceSaver Compress" from the Magic Menu leaves the file byte for
    byte unchanged — read back off the volume, not judged from the
    Finder, which would show the logical size either way. The likeliest
    reason is that SpaceSaver ships switched OFF, and its control panel
    is where that lives.
    """
    work = tempfile.mkdtemp(prefix="sswork-")
    img = os.path.join(work, "sswork.img")
    make_volume(img, "SSwork", [], size_kb=4096)
    s = Session(INSTALLED, [img], os.path.join(SPECIMENS, "panel"))
    try:
        s.boot()
        s.shot("desktop", wait=12.0)
        # Down the boot volume to Control Panels, the route `sdcompress`
        # settled on: the Apple menu is a timing fight and this proves
        # the panel is installed.
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=12.0)
        for prefix, tag in (("System F", "sysfolder"),
                            ("Control P", "cpanels")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac._xdo("type", "--delay", "120", prefix)
            time.sleep(1.5)
            s.mac.command_key("o")
            s.shot("opened-" + tag, wait=14.0)
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "~StuffIt")
        time.sleep(2.0)
        s.shot("selected-panel", wait=0.5)
        s.mac.command_key("o")
        s.shot("panel", wait=25.0)
        s.shot("panel-2", wait=10.0)
    finally:
        time.sleep(3)
        s.close()
    print("spacesaver: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def make_boot(keep=False):
    """Compress subjects that live on the STARTUP disk.

    The panel shows SpaceSaver switched On, and "SpaceSaver Compress" on
    a file sitting on a second volume changes nothing. SpaceSaver is a
    disk-space saver for the disk you boot from, so the subjects go onto
    the boot image itself — and the result is read back out of the
    session's working COPY of that image, the same place the installer's
    output had to be lifted from.
    """
    import glob
    boot = os.path.join(WORK, "ssmake.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssmb-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        for n, t, c, d, r in SUBJECTS:
            q = os.path.join(tmp, n + ".bin")
            open(q, "wb").write(macbinary(n, t, c, d, r))
            subprocess.run(["hcopy", "-m", q, ":"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "makeboot"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(470, 55, double=True)          # the startup disk
        s.shot("bootvol", wait=12.0)
        for name, letter in (("Alpha", "a"), ("Forked", "f")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac.key(letter)
            time.sleep(1.5)
            s.shot("selected-" + name, wait=0.5)
            ox, oy = s.mac.origin()
            x = s.mac._xdo
            x("mousemove", str(ox + MAGIC_X), str(oy + 8))
            time.sleep(0.5)
            x("mousedown", "1")
            time.sleep(1.5)
            x("mousemove", str(ox + MAGIC_X + 40),
              str(oy + MAGIC_COMPRESS_Y))
            time.sleep(1.2)
            s.shot("pick-" + name)
            x("mouseup", "1")
            s.shot("after-" + name, wait=35.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    from superdisk import read_forks                    # noqa: E402
    known = dict((n, d) for n, _t, _c, d, _r in SUBJECTS)
    os.makedirs(s.shots, exist_ok=True)
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(out).items()):
        if path[-1] not in known:
            continue
        orig = known[path[-1]]
        changed = data != orig
        print("spacesaver: %-10s %s/%s data %d (was %d) rsrc %d  %s"
              % (path[-1], ftype, creator, len(data), len(orig), len(rsrc),
                 "COMPRESSED" if changed else "unchanged"))
        if changed:
            q = os.path.join(s.shots, path[-1] + ".ss")
            open(q, "wb").write(data)
            if rsrc:
                open(q + ".rsrc", "wb").write(rsrc)
            print("             kept %s; first 32 bytes %s"
                  % (q, data[:32].hex()))
    return 0


# The control panel's 2x2 of icon buttons, measured off panel/06-panel.png:
# the window's rules sit at y=118, y=213 and y=312, and the banner ends
# around x=218, so the cells centre here.
SS_IDLE_TIME = (260, 165)
SS_COMPRESSION = (347, 165)
SS_DONT_COMPRESS = (260, 262)


def open_ss_panel(s):
    """Boot the installed image and leave SpaceSaver's panel open."""
    s.boot()
    s.shot("desktop", wait=14.0)
    s.mac.click(470, 55, double=True)
    s.shot("bootvol", wait=12.0)
    for prefix, tag in (("System F", "sysfolder"), ("Control P", "cpanels")):
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", prefix)
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("opened-" + tag, wait=14.0)
    s.mac.key("Escape")
    time.sleep(0.6)
    s.mac._xdo("type", "--delay", "120", "~StuffIt")
    time.sleep(2.0)
    s.mac.command_key("o")
    s.shot("panel", wait=25.0)


def idle(keep=False):
    """Photograph SpaceSaver's Idle Time page.

    SpaceSaver is a background compressor: "SpaceSaver Compress" from the
    Magic Menu leaves a file byte-identical, and this page is where the
    delay before it acts is set. What the choices ARE decides how long a
    run has to sit still afterwards.
    """
    work = tempfile.mkdtemp(prefix="sswork-")
    img = os.path.join(work, "sswork.img")
    make_volume(img, "SSwork", [], size_kb=4096)
    s = Session(INSTALLED, [img], os.path.join(SPECIMENS, "idle"))
    try:
        open_ss_panel(s)
        # "Compression & Other" FIRST. Idle Time opens a MODAL dialog, so
        # a click aimed at the other button while it is up lands inside
        # that dialog instead — on "Drive", as it happens — and the frame
        # captioned "compression-page" shows the Idle Time page again.
        # Twice each: every panel in this software swallows its first
        # input.
        s.mac.click(*SS_COMPRESSION)
        time.sleep(4.0)
        s.mac.click(*SS_COMPRESSION)
        s.shot("compression-page", wait=10.0)
        s.mac.key("Return")                     # dismiss it, whatever it is
        s.shot("after-compression", wait=8.0)
        s.mac.click(*SS_IDLE_TIME)
        time.sleep(4.0)
        s.mac.click(*SS_IDLE_TIME)
        s.shot("idle-page", wait=8.0)
    finally:
        time.sleep(3)
        s.close()
    print("spacesaver: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# The Idle Time Settings dialog, measured off idle/06-idle-page.png.
IDLE_MINUTES = (253, 99)
IDLE_ADD = (336, 209)
IDLE_OK = (427, 297)


def enroll(keep=False):
    """Enrol the startup disk with SpaceSaver and let it idle.

    The Idle Time page says why nothing has compressed: *"but only if
    they are located on the following disks:"* over an EMPTY list. Until
    a disk is added, SpaceSaver has nothing it is allowed to touch. The
    delay also defaults to ten minutes of no user activity, which no run
    here has ever sat still for.

    So: add the startup disk, set the delay to one minute, OK, close the
    panel, and then do nothing at all for several minutes — the one thing
    a screenshot harness never does.
    """
    import glob
    boot = os.path.join(WORK, "ssenroll.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssen-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        # Dated 1990, not today. The page compresses "files not modified
        # in the last 1 Months" and `hcopy` stamps whatever it writes with
        # the current date — so freshly copied subjects are exactly the
        # files SpaceSaver is configured to leave alone. MacBinary dates
        # survive the copy (measured in `ndd.py --dates`).
        from ndd import macbinary_dated, MAC_EPOCH_1990   # noqa: E402
        for n, t, c, d, r in SUBJECTS:
            q = os.path.join(tmp, n + ".bin")
            open(q, "wb").write(macbinary_dated(n, t, c, d, r,
                                                MAC_EPOCH_1990,
                                                MAC_EPOCH_1990))
            subprocess.run(["hcopy", "-m", q, ":"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "enroll"))
    try:
        open_ss_panel(s)
        s.mac.click(*SS_IDLE_TIME)
        time.sleep(4.0)
        s.mac.click(*SS_IDLE_TIME)
        s.shot("idle-page", wait=10.0)
        # The delay is left at its default ten minutes rather than
        # edited: a backspace-and-retype of that field did not visibly
        # change it, and out-waiting it is one parameter instead of two.
        # enrol the startup disk, which is the drive the page already shows
        s.mac.click(*IDLE_ADD)
        time.sleep(3.0)
        s.mac.click(*IDLE_ADD)
        s.shot("added", wait=6.0)
        s.mac.click(*IDLE_OK)
        time.sleep(3.0)
        s.mac.click(*IDLE_OK)
        s.shot("settings-ok", wait=8.0)
        s.mac.command_key("w")                  # close the control panel
        s.shot("panel-closed", wait=8.0)
        # And now the part that matters: sit absolutely still, for
        # longer than the ten minutes the page asks for. Six was not
        # enough — which is the whole reason nothing had compressed.
        for i in range(11):
            s.shot("idling%d" % i, wait=100.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    from superdisk import read_forks                    # noqa: E402
    known = dict((n, d) for n, _t, _c, d, _r in SUBJECTS)
    os.makedirs(s.shots, exist_ok=True)
    hit = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(out).items()):
        if path[-1] not in known:
            continue
        orig = known[path[-1]]
        changed = data != orig
        print("spacesaver: %-10s %s/%s data %d (was %d) rsrc %d  %s"
              % (path[-1], ftype, creator, len(data), len(orig), len(rsrc),
                 "COMPRESSED" if changed else "unchanged"))
        if changed:
            hit += 1
            q = os.path.join(s.shots, path[-1] + ".ss")
            open(q, "wb").write(data)
            if rsrc:
                open(q + ".rsrc", "wb").write(rsrc)
            print("             kept %s; first 32 %s" % (q, data[:32].hex()))
    return 0 if hit else 1


def namerule(keep=False):
    """Trigger SpaceSaver the way it is actually configured to trigger.

    Its "Compression and Other Settings" page reads: *Immediately
    compress files, folders, and disks whose ... Name begins or ends
    with: `small`*. That is the on-demand mechanism — a NAME rule — and
    it is why "SpaceSaver Compress" from the Magic Menu, an enrolled
    disk, 1990 dates and eighteen minutes of idling all left the subjects
    byte-identical: none of them was ever called anything ending in
    "small".

    So the subjects are renamed in the Finder. Return opens an icon's
    name for editing and Right-arrow drops the selection to the end, the
    same pair `sdcompress.py` uses.
    """
    import glob
    boot = os.path.join(WORK, "ssname.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssnm-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        for n, t, c, d, r in SUBJECTS:
            q = os.path.join(tmp, n + ".bin")
            open(q, "wb").write(macbinary(n, t, c, d, r))
            subprocess.run(["hcopy", "-m", q, ":"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "namerule"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        # CLOSE the "StuffIt Deluxe Folder" window the installed system
        # opens at startup, rather than trying to raise the volume window
        # past it — clicking that window's title bar did not raise it, and
        # the type-select then went to the wrong window and selected
        # nothing. Cmd-W closes whatever is front; do it a few times, then
        # open the volume, which is now the only window there is.
        # The FIRST input after boot is swallowed — the same thing both
        # Aladdin installers do, and why three Cmd-Ws in a row left the
        # window open while a later Cmd-O worked fine: that one was
        # preceded by a click. So wake the input path with a harmless
        # click on empty desktop, then close.
        # On its TITLE BAR, not the desktop: a click on empty desktop
        # DEACTIVATES the front window — the menu bar greys out View and
        # Label — and Cmd-W then has nothing to close, which photographs
        # identically to a Cmd-W that never arrived.
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.shot("windows-closed", wait=6.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        for name, letter in (("Alpha", "a"), ("Forked", "f")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac.key(letter)
            time.sleep(1.5)
            s.shot("selected-" + name, wait=0.5)
            s.mac.key("Return")           # open the name for editing
            time.sleep(2.0)
            s.mac.key("Right")            # to the end, keeping the name
            time.sleep(0.8)
            s.mac._xdo("type", "--delay", "150", "small")
            time.sleep(1.5)
            s.shot("typed-" + name, wait=0.5)
            # Return does not commit this name box — one leaves it
            # editing, two leave the old name on the volume. Enter is the
            # keystroke a Finder name box actually takes, and clicking
            # ANOTHER ICON commits it the way a person would. Both, in
            # that order, and neither is destructive if the other already
            # worked.
            s.mac.key("KP_Enter")
            time.sleep(4.0)
            s.mac.click(155, 310)          # HyperCard, a different icon
            time.sleep(4.0)
            s.shot("renamed-" + name, wait=35.0)
        s.shot("settled", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    from superdisk import read_forks                    # noqa: E402
    known = dict((n, d) for n, _t, _c, d, _r in SUBJECTS)
    os.makedirs(s.shots, exist_ok=True)
    hit = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(out).items()):
        base = path[-1]
        orig = known.get(base) or known.get(base[:-5])
        if orig is None:
            continue
        changed = data != orig
        print("spacesaver: %-16s %s/%s data %d (was %d) rsrc %d  %s"
              % (base, ftype, creator, len(data), len(orig), len(rsrc),
                 "COMPRESSED" if changed else "unchanged"))
        if changed:
            hit += 1
            q = os.path.join(s.shots, base + ".ss")
            open(q, "wb").write(data)
            if rsrc:
                open(q + ".rsrc", "wb").write(rsrc)
            print("             kept %s; first 48 %s" % (q, data[:48].hex()))
    return 0 if hit else 1


ENROLLED = os.path.join(WORK, "ssenrolled.hfv")


def namefirst(keep=False):
    """Put subjects on the disk ALREADY matching the rule, and wait.

    The rule is *"Immediately compress files … whose Name begins or ends
    with `small`"*, and renaming a file in the Finder to match has not
    worked from this harness. So the name is right before the file ever
    reaches the machine — which also answers something unmeasured:
    whether SpaceSaver acts on a matching name APPEARING, or only on a
    name CHANGE.

    The base image is the one where enrolling the startup disk in Idle
    Time actually stuck, so the idle sweep has somewhere to look too.
    Both mechanisms get their chance in one boot.
    """
    import glob
    base = ENROLLED if os.path.exists(ENROLLED) else INSTALLED
    boot = os.path.join(WORK, "ssnamefirst.hfv")
    shutil.copyfile(base, boot)
    print("spacesaver: base image %s" % os.path.basename(base))

    # Matching and non-matching, so the rule itself is the variable.
    named = [("Alphasmall", "TEXT", "ttxt", SUBJECT, b""),
             ("smallForked", "PICT", "8BIM", SUBJECT[:3000],
              make_rsrc(b"\x1eSpaceSaver probe fork")),
             ("Control", "TEXT", "ttxt", SUBJECT, b"")]
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssnf-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        from ndd import macbinary_dated, MAC_EPOCH_1990   # noqa: E402
        for n, t, c, d, r in named:
            q = os.path.join(tmp, n + ".bin")
            open(q, "wb").write(macbinary_dated(n, t, c, d, r,
                                                MAC_EPOCH_1990,
                                                MAC_EPOCH_1990))
            subprocess.run(["hcopy", "-m", q, ":"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "namefirst"))
    try:
        s.boot()
        s.shot("desktop", wait=15.0)
        # Show the volume so the Finder actually looks at the files, then
        # leave the machine alone.
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=15.0)
        for i in range(8):
            s.shot("waiting%d" % i, wait=100.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    from superdisk import read_forks                    # noqa: E402
    known = dict((n, d) for n, _t, _c, d, _r in named)
    os.makedirs(s.shots, exist_ok=True)
    hit = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(out).items()):
        base_n = path[-1]
        if base_n not in known:
            continue
        orig = known[base_n]
        changed = data != orig
        print("spacesaver: %-14s %s/%s data %d (was %d) rsrc %d  %s"
              % (base_n, ftype, creator, len(data), len(orig), len(rsrc),
                 "COMPRESSED" if changed else "unchanged"))
        if changed:
            hit += 1
            q = os.path.join(s.shots, base_n + ".ss")
            open(q, "wb").write(data)
            if rsrc:
                open(q + ".rsrc", "wb").write(rsrc)
            print("             kept %s; first 48 %s" % (q, data[:48].hex()))
    return 0 if hit else 1


def namevol(keep=False):
    """Rename on a volume that can be PUT AWAY, so the change is flushed.

    The rename itself was never the problem. A frame shows both subjects
    committed on screen as `Alphasmall` and `Forkedsmall` — no edit box —
    while the disk image still holds `Alpha` and `Forked`. HFS directory
    changes sit in the cache until the volume is unmounted, and the boot
    volume never is: the emulator is killed instead, and whatever the
    Finder had not written goes with it. The installer's writes survived
    because the system ran on for minutes afterwards.

    So the subjects go on a SECOND volume, which Cmd-Y (Put Away)
    unmounts — the flush every other harness here relies on — and that
    volume is a file this side of the emulator, so no session copy has to
    be hunted for either.
    """
    base = ENROLLED if os.path.exists(ENROLLED) else INSTALLED
    boot = os.path.join(WORK, "ssnamevol.hfv")
    shutil.copyfile(base, boot)

    from ndd import macbinary_dated, MAC_EPOCH_1990       # noqa: E402
    work = tempfile.mkdtemp(prefix="sswork-")
    mbs = []
    for n, t, c, d, r in SUBJECTS:
        q = os.path.join(work, n + ".bin")
        open(q, "wb").write(macbinary_dated(n, t, c, d, r,
                                            MAC_EPOCH_1990, MAC_EPOCH_1990))
        mbs.append(q)
    img = os.path.join(work, "sswork.img")
    make_volume(img, "SSwork", mbs, size_kb=16384)

    s = Session(boot, [img], os.path.join(SPECIMENS, "namevol"))
    try:
        s.boot()
        s.shot("desktop", wait=15.0)
        s.mac.click(250, 38)                    # activate the stray window
        time.sleep(2.5)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.shot("windows-closed", wait=6.0)
        s.mac.click(*VOLUME_ICON, double=True)  # SSwork
        s.shot("volume", wait=14.0)
        for name, letter in (("Alpha", "a"), ("Forked", "f")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac.key(letter)
            time.sleep(1.5)
            s.shot("selected-" + name, wait=0.5)
            s.mac.key("Return")
            time.sleep(2.0)
            s.mac.key("Right")
            time.sleep(0.8)
            s.mac._xdo("type", "--delay", "150", "small")
            time.sleep(1.5)
            s.mac.key("KP_Enter")
            time.sleep(3.0)
            s.mac.click(200, 150)               # empty space in the window
            s.shot("renamed-" + name, wait=30.0)
        s.shot("settled", wait=45.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")                  # Put Away: the flush
        s.shot("ejected", wait=25.0)
    finally:
        time.sleep(8)
        s.close()

    from superdisk import read_forks                    # noqa: E402
    known = dict((n, d) for n, _t, _c, d, _r in SUBJECTS)
    os.makedirs(s.shots, exist_ok=True)
    hit = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(img).items()):
        b = path[-1]
        orig = known.get(b) or known.get(b[:-5])
        if orig is None:
            continue
        changed = data != orig
        print("spacesaver: %-14s %s/%s data %d (was %d) rsrc %d  %s"
              % (b, ftype, creator, len(data), len(orig), len(rsrc),
                 "COMPRESSED" if changed else "unchanged"))
        if changed:
            hit += 1
            q = os.path.join(s.shots, b + ".ss")
            open(q, "wb").write(data)
            if rsrc:
                open(q + ".rsrc", "wb").write(rsrc)
            print("             kept %s; first 48 %s" % (q, data[:48].hex()))
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if hit else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--install", action="store_true",
                    help="walk the installer")
    ap.add_argument("--setup351", action="store_true",
                    help="fetch StuffIt Deluxe 3.5.1's two floppies")
    ap.add_argument("--probe351", action="store_true",
                    help="boot with both floppies mounted")
    ap.add_argument("--install351", action="store_true",
                    help="run the 3.5.1 installer")
    ap.add_argument("--setup40", action="store_true",
                    help="fetch StuffIt Deluxe 4.0")
    ap.add_argument("--keep-installed", action="store_true",
                    help="lift the installed boot image out of /tmp")
    ap.add_argument("--namevol", action="store_true",
                    help="rename on a volume that Put Away can flush")
    ap.add_argument("--namefirst", action="store_true",
                    help="subjects already named to match the rule")
    ap.add_argument("--namerule", action="store_true",
                    help="rename subjects to end in 'small', its trigger")
    ap.add_argument("--enroll", action="store_true",
                    help="enrol the startup disk and let SpaceSaver idle")
    ap.add_argument("--idle", action="store_true",
                    help="photograph the Idle Time and Compression pages")
    ap.add_argument("--make-boot", action="store_true",
                    help="compress subjects that live on the startup disk")
    ap.add_argument("--panel", action="store_true",
                    help="open the SpaceSaver control panel")
    ap.add_argument("--make", action="store_true",
                    help="compress subjects with SpaceSaver")
    ap.add_argument("--probe-installed", action="store_true",
                    help="boot the installed image and peek the menus")
    ap.add_argument("--install40", action="store_true",
                    help="run the 4.0 installer, trying each published code")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if a.setup:
        fetch()
    elif a.probe:
        probe(a.keep)
    elif a.install:
        install(a.keep)
    elif a.setup351:
        setup351()
    elif a.probe351:
        probe351(a.keep)
    elif a.install351:
        install351(a.keep)
    elif a.setup40:
        setup40()
    elif a.keep_installed:
        keep_installed()
    elif a.namevol:
        return namevol(a.keep)
    elif a.namefirst:
        return namefirst(a.keep)
    elif a.namerule:
        return namerule(a.keep)
    elif a.enroll:
        return enroll(a.keep)
    elif a.idle:
        idle(a.keep)
    elif a.make_boot:
        return make_boot(a.keep)
    elif a.panel:
        panel(a.keep)
    elif a.make:
        return make(a.keep)
    elif a.probe_installed:
        probe_installed(a.keep)
    elif a.install40:
        install40(a.keep)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

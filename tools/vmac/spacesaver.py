#!/usr/bin/env python3
"""spacesaver.py — run Aladdin's SpaceSaver under Mini vMac.

SpaceSaver ships inside StuffIt Deluxe, and the Deluxe 5.0.1 CD-ROM on
Macintosh Garden carries a **standalone `SpaceSaver 5.0 Installer`**
beside it — one installer on one volume, where the 3.5.1 and 4.0
distributions are two-floppy InstallerMaker sets.

    tools/vmac/spacesaver.py --setup     fetch the CD, lift the installer
    tools/vmac/spacesaver.py --probe     boot with it and photograph
    tools/vmac/spacesaver.py --install   run the installer
    tools/vmac/spacesaver.py --make      compress a subject, keep the file
    tools/vmac/spacesaver.py --layout    read the container out of the
                                         installed panel and engine

**`--layout` is the one that pays**, and it boots nothing: the container
was read out of Aladdin's own engine on 2026-08-22 (FORMATS.md, *StuffIt
SpaceSaver's container*), the route SuperDisk! and DiskDoubler Pro both
took. What is still wanted is a specimen — ten emulator runs have not
produced one — and the two codecs, which sit in the same resource fork.

Nothing here runs in `ci.sh`, and nothing it fetches is committed.
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
        # `-a`, 2026-09-23: the installer is found by searching the
        # listing for its name, so a listing that hides a file cannot
        # find one that is invisible.
        names = subprocess.run([b"hls", b"-a", b"-1"], capture_output=True,
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
        s.mac._xdo("type", "--delay", "120", "MacExtract")
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
        # And then SHUT DOWN. The first time this ran the emulator was
        # killed here, and the image `--keep-installed` lifted has no
        # `SpaceSaver Preferences` in it and an extension that never
        # installs — the flush rule at the top of tools/vmac/README.md,
        # paid for a second time.
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=40.0)
    finally:
        time.sleep(8)
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
        s.mac._xdo("type", "--delay", "120", "MacExtract")
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



# The Finder's Special menu on this System 7.0.1 image, measured off
# `namerule/01-desktop.png`: the title "Special" spans x=207..250, and
# the menu is Clean Up Window / Empty Trash / - / Eject Disk / Erase Disk
# / - / Restart / Shut Down, the same eight rows `arcmac.py` picks 123
# out of on System 6.
SPECIAL_X = 225
# Shut Down is at 139. 123 is RESTART, one item above it, which is what
# every mode here picked until 2026-09-01 — measured off the twenty-five
# `*-special-menu.png` this file had taken, all of them highlighting the
# band y=116..131 (BLOCKERS.md, withdrawn claims; the same trap is
# `rescomp.py`'s, in tools/vmac/README.md).
SHUT_DOWN_Y = 139


def init0_gate(fork):
    """Where INIT 0 decides not to install, and what the byte there is.

    Found 2026-08-25 by disassembling the control panel's own `INIT 0`
    (the cdev carries INIT 0 and INIT 1; the panel is what has always
    worked here, the extension is what never has):

        2a50  link   a6,#-26
        2a5c  _SysEnvirons          ; the record at fp@(-22)
        2a5e  move.l fp@(-18),fp@(-26)
        2a66  _Button               ; hold the mouse down to disable
        2a6a  bne.s  2a74           ; ...and 2a74 shows ICN# -4063 and RETURNS
        2a6c  btst   #0,fp@(-23)    ; a byte of what was just copied
        2a72  beq.s  2a8c           ; clear -> on to the named checks

    **Everything SpaceSaver can complain about is behind that branch**:
    no Gestalt trap is STR# 1001 #1, a missing `PERS` resource is #20, a
    'SLip' Gestalt already registered is #8, and each of those sets a
    reason and shows the same failed icon at the end. The early exit at
    2a74 sets no reason at all — and Mini vMac cannot photograph the
    startup icon parade (`--parade`, 30 shots, all of them the settled
    desktop), so twelve runs saw neither.

    Returns the offset of the branch byte within the resource fork.
    """
    import sys as _sys
    _sys.path.insert(0, os.path.join(REPO, "tools", "sdmodule"))
    from run_sdmodule import resource_data                # noqa: E402
    res = resource_data(fork)
    blob = None
    for rid, _name, data in res.get("INIT", []):
        if rid == 0:
            blob = data
    if blob is None:
        raise SystemExit("spacesaver: the control panel has no INIT 0")
    at = fork.find(blob[:64])
    if at < 0 or fork.find(blob[:64], at + 1) >= 0:
        raise SystemExit("spacesaver: cannot place INIT 0 in the fork")
    if blob[0x2A72] != 0x67:
        raise SystemExit("spacesaver: INIT 0 @0x2a72 is %02x, not a BEQ — "
                         "this is a different build" % blob[0x2A72])
    return at + 0x2A72


def patch_init(keep=False):
    """Turn that BEQ into a BRA, and see what SpaceSaver does next.

    A one-byte change to a local test image, to answer a question twelve
    emulator runs could not: is the gate above what has kept every run
    empty, or is the extension refusing for one of the reasons it has
    strings for? Anything this run produces is written by Alysis's own
    compressor — the patch is in the install decision, not in the codec —
    but it is a PATCHED run and every result from it says so.
    """
    out = os.path.join(WORK, "sspatched.hfv")
    shutil.copyfile(INSTALLED, out)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="sspatch-")
    try:
        subprocess.run(["hmount", out], check=True, capture_output=True,
                       env=env)
        listing = subprocess.run(["hls", "-a", ":System Folder:Control Panels:"],
                                 capture_output=True, env=env).stdout
        names = [n.strip() for n in listing.split(b"\n") if b"SpaceSaver" in n]
        if not names:
            raise SystemExit("spacesaver: no control panel on the image")
        path = b":System Folder:Control Panels:" + names[0]
        mb = os.path.join(tmp, "panel.bin")
        subprocess.run(["hcopy", "-m", path, mb.encode()], check=True,
                       capture_output=True, env=env)
        blob = bytearray(open(mb, "rb").read())
        dl = struct.unpack(">I", blob[0x53:0x57])[0]
        ro = 128 + ((dl + 127) & ~127)
        # The MacBinary CRC covers the header, not the forks, so a byte
        # patched in place needs no header repair.
        off = ro + init0_gate(bytes(blob[ro:]))
        print("spacesaver: INIT 0 gate at MacBinary offset %d (%02x -> 60)"
              % (off, blob[off]))
        blob[off] = 0x60
        open(mb, "wb").write(bytes(blob))
        subprocess.run(["hdel", path], check=True, capture_output=True, env=env)
        subprocess.run(["hcopy", "-m", mb.encode(),
                        b":System Folder:Control Panels:"], check=True,
                       capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)
    print("spacesaver: patched image at %s" % out)
    return specimen(keep, base=out, tag="patched")


def specimen(keep=False, base=None, tag="specimen"):
    """Rename the subjects so SpaceSaver compresses them, then SHUT DOWN.

    Everything here is `--namerule`, which has been photographed doing
    the rename correctly, plus the one step it was missing. Mini vMac
    writes the guest's sectors through buffered stdio and flushes when a
    volume is ejected; killing the emulator with the boot volume still
    mounted throws away whatever the Finder had not written, which is why
    ten runs read back byte-identical subjects. Special > Shut Down
    ejects every volume. `arcmac.py`'s `shutdown()` says the same thing
    and has said it since ARC specimens were made this way — this
    harness simply never called it.

    The subjects go on the BOOT volume, not a second one: the name rule
    is what fires, the boot volume is the disk the panel is enrolled for,
    and a shutdown flushes it just as well.
    """
    import glob
    boot = os.path.join(WORK, "ss%s-run.hfv" % tag)
    shutil.copyfile(base or INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssspec-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
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
    s = Session(boot, [], os.path.join(SPECIMENS, tag))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        # Wake the input path with a click on the front window's TITLE
        # bar, then close what the installed system opens at startup.
        # Both notes are `--namerule`'s, measured.
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
            s.mac.key("Return")           # open the name for editing
            time.sleep(2.0)
            s.mac.key("Right")            # to the end, keeping the name
            time.sleep(0.8)
            s.mac._xdo("type", "--delay", "150", "small")
            time.sleep(1.5)
            s.mac.key("KP_Enter")         # Enter commits; Return does not
            time.sleep(4.0)
            s.mac.click(155, 310)         # another icon, as a person would
            time.sleep(4.0)
            s.shot("renamed-" + name, wait=35.0)
        s.shot("settled", wait=45.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_specimen(out, s.shots)


def report_specimen(img, shots, subjects=None):
    """Say what came back, and keep anything that is a SpaceSaver file.

    A changed subject is not enough on its own — the point of the run is
    a file with `SIT!DFD3` at offset 0, so that is what is reported and
    what decides the exit status.
    """
    from superdisk import read_forks                    # noqa: E402
    known = dict((n, d) for n, _t, _c, d, _r in (subjects or SUBJECTS))
    os.makedirs(shots, exist_ok=True)
    hit = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(img).items()):
        base = path[-1]
        orig = known.get(base) or known.get(base[:-5])
        if orig is None:
            continue
        ss = data[:8] == b"SIT!DFD3"
        print("spacesaver: %-16s %s/%s data %d (was %d) rsrc %d  %s"
              % (base, ftype, creator, len(data), len(orig), len(rsrc),
                 "SPACESAVER" if ss else
                 ("changed, not a SpaceSaver file" if data != orig
                  else "unchanged")))
        if data == orig:
            continue
        q = os.path.join(SPECIMENS, base + ".ss")
        open(q, "wb").write(data)
        if rsrc:
            open(q + ".rsrc", "wb").write(rsrc)
        # The bytes that went in, beside what came out: this is the only
        # oracle the format has, so the specimen is useless without it.
        open(q + ".orig", "wb").write(orig)
        print("             kept %s" % q)
        hit += ss
    return 0 if hit else 1


# Matching and non-matching names, all dated 1990: the Idle Time page
# compresses "files not modified in the last 1 Months", and the
# Compression page's rule fires on a name that begins or ends with
# "small". One boot gives both mechanisms their chance, and `Control`
# says which of them fired.
IDLE_SUBJECTS = [("Alphasmall", "TEXT", "ttxt", SUBJECT, b""),
                 ("smallForked", "PICT", "8BIM", SUBJECT[:3000],
                  make_rsrc(b"\x1eSpaceSaver probe fork")),
                 ("Control", "TEXT", "ttxt", SUBJECT, b"")]


def idlespec(keep=False):
    """Enrol the startup disk, idle, and SHUT DOWN — all in one boot.

    Both halves of this have been done before and neither result
    survived. `--enroll` added the startup disk to the Idle Time list
    and sat still for eighteen minutes, then the emulator was killed:
    Mini vMac had not flushed the volume, so the image it left behind
    was both unbootable and empty of whatever had happened. Every run
    built on that image — `--namefirst`, `--namevol` — then failed to
    boot at all, and each one's "unchanged" readback was recorded as a
    measurement of SpaceSaver rather than of a dead machine.

    So: one boot does the enrolling, the idling and the shutdown, and
    the readback comes from an image that was flushed.
    """
    import glob
    boot = os.path.join(WORK, "ssidle.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssidle-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        from ndd import macbinary_dated, MAC_EPOCH_1990   # noqa: E402
        for n, t, c, d, r in IDLE_SUBJECTS:
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
    s = Session(boot, [], os.path.join(SPECIMENS, "idlespec"))
    try:
        open_ss_panel(s)
        s.mac.click(*SS_IDLE_TIME)
        time.sleep(4.0)
        s.mac.click(*SS_IDLE_TIME)
        s.shot("idle-page", wait=10.0)
        s.mac.click(*IDLE_ADD)                  # enrol the startup disk
        time.sleep(3.0)
        s.mac.click(*IDLE_ADD)
        s.shot("added", wait=6.0)
        s.mac.click(*IDLE_OK)
        time.sleep(3.0)
        s.mac.click(*IDLE_OK)
        s.shot("settings-ok", wait=8.0)
        s.mac.command_key("w")                  # close the control panel
        s.shot("panel-closed", wait=8.0)
        # Sit absolutely still for longer than the ten minutes the page
        # asks for. A screenshot is a host-side grab of the X window and
        # injects no event, so it does not count as user activity.
        for i in range(11):
            s.shot("idling%d" % i, wait=100.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_specimen(out, s.shots, IDLE_SUBJECTS)


def magic(keep=False):
    """Ask Magic Menu to compress the subjects, then SHUT DOWN.

    The one mechanism that needs neither a name rule nor an idle timer:
    Magic Menu puts *SpaceSaver Compress* in the Finder's menu bar, and
    it acts on the selection. It was tried once before and read back
    unchanged — on an image nobody had flushed, which is now known to
    measure nothing (BLOCKERS.md). Same command, on the boot volume,
    ending in Special > Shut Down.
    """
    import glob
    boot = os.path.join(WORK, "ssmagic.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssmagic-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
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
    s = Session(boot, [], os.path.join(SPECIMENS, "magic"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)                    # wake the input path
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
            s.mac.key(letter)                   # type-select
            time.sleep(1.5)
            s.shot("selected-" + name, wait=0.5)
            s.menu(MAGIC_X, MAGIC_COMPRESS_Y, "compress-" + name)
            s.shot("after-" + name, wait=45.0)
        s.shot("settled", wait=30.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_specimen(out, s.shots)


def magicname(keep=False):
    """The two halves in ONE run: a matching NAME and a menu command.

    `INIT 1` patches `_MenuSelect`, `_MenuKey` and `_PBEject`, and
    installs its own menu behind a preference byte by patching
    `_DrawMenuBar` and `_SystemMenu`. **Nothing patches the File
    Manager**, so a rename is not an event and cannot fire anything —
    which is what every naming run has been waiting for. The name rule
    is a FILTER; something else has to ask.

    So: subjects that already END in `small` when they are copied onto
    the image — no Finder rename needed if the name is only a filter —
    and then Magic Menu's *SpaceSaver Compress* on each selection, the
    command `--magic` uses. `--namerule` did the first half, `--magic`
    the second, and no run has done both.
    """
    import glob
    boot = os.path.join(WORK, "ssmagicname.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssmn-")
    # THREE sizes, because mCompressFile @0x5510 refuses a file whose
    # every fork is smaller than a threshold its caller passes in, and
    # returns -37 for it — an OSErr, not an alert. Every subject any run
    # has ever used is 11 KB or less, so a size gate would have refused
    # all fourteen of them silently. A 400 KB subject settles it.
    big = (b"SpaceSaver probe, at length. " * 14000)[:400000]
    named = [(n + " small", t, c, d, r) for n, t, c, d, r in SUBJECTS]
    named.append(("Bigone small", "TEXT", "ttxt", big, b""))
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        for n, t, c, d, r in named:
            q = os.path.join(tmp, n.replace(" ", "_") + ".bin")
            open(q, "wb").write(macbinary(n, t, c, d, r))
            subprocess.run(["hcopy", "-m", q, ":"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "magicname"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.shot("windows-closed", wait=6.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        for name, letter in (("Bigone", "b"), ("Alpha", "a"),
                             ("Forked", "f")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac.key(letter)
            time.sleep(1.5)
            s.shot("selected-" + name, wait=0.5)
            s.menu(MAGIC_X, MAGIC_COMPRESS_Y, "compress-" + name)
            s.shot("after-" + name, wait=45.0)
        s.shot("settled", wait=30.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_specimen(out, s.shots)


def volname(keep=False):
    """Attach the keyword to the DISK, which is what the guide suggests.

    "If you attach a compress keyword to a disk or folder, everything
    contained on that disk or in that folder gets compressed" — the 5.0
    User's Guide, page 12. Every attempt so far has renamed FILES; a
    volume rename is a different Finder operation and a different path
    through whatever watches names.
    """
    import glob
    boot = os.path.join(WORK, "ssvolname.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssvn-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
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
    s = Session(boot, [], os.path.join(SPECIMENS, "volname"))
    try:
        s.boot()
        s.shot("desktop", wait=16.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.shot("windows-closed", wait=6.0)
        # The volume icon itself, top right of the desktop.
        s.mac.click(470, 55)
        time.sleep(2.0)
        s.shot("volume-selected", wait=1.0)
        s.mac.key("Return")                 # open the name box
        time.sleep(2.5)
        s.mac.key("Right")
        time.sleep(0.8)
        s.mac._xdo("type", "--delay", "150", " small")
        time.sleep(1.5)
        s.shot("volume-typed", wait=1.0)
        s.mac.key("KP_Enter")
        time.sleep(5.0)
        s.mac.click(250, 200)               # commit by clicking the desktop
        s.shot("volume-renamed", wait=45.0)
        for i in range(4):
            s.shot("settling%d" % i, wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=45.0)
    finally:
        time.sleep(10)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    from superdisk import read_forks                    # noqa: E402
    hit = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(out).items()):
        if len(path) > 1 or not path:
            continue
        mark = "SPACESAVER FILE" if data[:8] == b"SIT!DFD3" else ""
        print("spacesaver: %-18s %s/%s %8d B %s"
              % (path[-1], ftype, creator, len(data), mark))
        if mark:
            hit += 1
            q = os.path.join(s.shots, path[-1].replace(" ", "_") + ".ss")
            open(q, "wb").write(data)
    return 0 if hit else 1


def twonames(keep=False):
    """The control: fire the rule that WORKS beside the one that does not.

    2026-08-25: `Forked` -> `Forked.SIT` became a StuffIt archive in the
    same boot where `Alpha` -> `Alphasmall` did nothing, so the watcher
    is alive and the `small` rule is what is inert. The suffix here now
    has a LEADING SPACE — `Alpha small` — because the page says "Name
    begins or ends WITH", and every run that used a spaced name had it
    applied by `hcopy`, where no rename ever happened.

    Both are ticked on the same page and both are name rules on the same
    event — `.SIT` has been seen to turn a file into a StuffIt archive,
    `small` has never done anything. Renaming one subject each way in
    ONE boot says whether the mechanism is alive at that moment, which
    no run so far can: every `small` run that measured nothing might
    have been a boot where nothing was watching at all.
    """
    import glob
    boot = os.path.join(WORK, "sstwonames.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="sstn-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
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
    s = Session(boot, [], os.path.join(SPECIMENS, "twonames"))
    try:
        s.boot()
        s.shot("desktop", wait=16.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        # Alpha -> Alphasmall (the rule that has never fired),
        # Forked -> Forked.SIT (the rule that has).
        # The keyword at the BEGINNING, which the guide calls the more
        # useful form — Left goes to the start of the name box, Right to
        # its end. `Alphasmall` and `Alpha small` have both been tried
        # and neither fired; `.SIT` fires in the same boot either way.
        for name, letter, where, text in (("Alpha", "a", "Left", "small "),
                                          ("Forked", "f", "Right", ".SIT")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac.key(letter)
            time.sleep(1.5)
            s.shot("selected-" + name, wait=0.5)
            s.mac.key("Return")
            time.sleep(2.0)
            s.mac.key(where)
            time.sleep(0.8)
            s.mac._xdo("type", "--delay", "150", text)
            time.sleep(1.5)
            s.shot("typed-" + name, wait=0.5)
            s.mac.key("KP_Enter")
            time.sleep(4.0)
            s.mac.click(155, 310)
            time.sleep(5.0)
            s.shot("after-" + name, wait=45.0)
        s.shot("settled", wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=45.0)
    finally:
        time.sleep(10)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    from superdisk import read_forks                    # noqa: E402
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(out).items()):
        if not any(k in path[-1] for k in ("Alpha", "Forked")):
            continue
        what = ("SpaceSaver file" if data[:8] == b"SIT!DFD3"
                else "StuffIt archive" if data[:4] in (b"SIT!", b"StuffIt")
                else "unchanged")
        print("spacesaver: %-16s %s/%s %8d B  %s"
              % (path[-1], ftype, creator, len(data), what))
    return 0


def enrollrename(keep=False):
    """Enrol the disk, THEN rename in the Finder. The untried cell.

    Read off the panel with `--pages`, changing nothing: the
    *Compression and Other* page has **both** rules ticked — "Name
    begins or ends with `small`" and "Stuff or expand item when its name
    is changed by adding or removing .SIT/.SEA" — and the second is the
    one this project has already seen FIRE, so rename events are
    noticed. The *Idle Time* page, meanwhile, ships with an EMPTY list
    of disks.

    So the hypothesis is that the `small` rule is gated on the disk
    being enrolled and the `.SIT` rule is not. `--enroll` enrolled but
    never renamed; `--namerule` renamed but never enrolled. This does
    both, in one boot, and shuts down so the volume is flushed.
    """
    import glob
    boot = os.path.join(WORK, "ssenrollrename.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="sser-")
    big = (b"SpaceSaver probe, at length. " * 14000)[:400000]
    plain = list(SUBJECTS) + [("Bigone", "TEXT", "ttxt", big, b"")]
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        from ndd import macbinary_dated, MAC_EPOCH_1990   # noqa: E402
        for n, t, c, d, r in plain:
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
    s = Session(boot, [], os.path.join(SPECIMENS, "enrollrename"))
    try:
        open_ss_panel(s)
        s.mac.click(*SS_IDLE_TIME)
        time.sleep(3.0)
        s.mac.click(*SS_IDLE_TIME)
        s.shot("idle-page", wait=10.0)
        s.mac.click(*IDLE_ADD)
        time.sleep(3.0)
        s.mac.click(*IDLE_ADD)
        s.shot("added", wait=6.0)
        s.mac.click(*IDLE_OK)
        time.sleep(3.0)
        s.mac.click(*IDLE_OK)
        s.shot("settings-ok", wait=8.0)
        s.mac.click(*SS_CLOSE_BOX)
        time.sleep(2.0)
        s.mac.click(*SS_CLOSE_BOX)
        s.shot("panel-closed", wait=8.0)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.shot("windows-closed", wait=6.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        for name, letter in (("Bigone", "b"), ("Alpha", "a"),
                             ("Forked", "f")):
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
            s.shot("typed-" + name, wait=0.5)
            s.mac.key("KP_Enter")
            time.sleep(4.0)
            s.mac.click(155, 310)
            time.sleep(4.0)
            s.shot("renamed-" + name, wait=40.0)
        for i in range(3):
            s.shot("settling%d" % i, wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=45.0)
    finally:
        time.sleep(10)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    from superdisk import read_forks                    # noqa: E402
    hit = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(out).items()):
        if not any(k in path[-1] for k in ("Alpha", "Forked", "Bigone")):
            continue
        print("spacesaver: %-16s %s/%s data %d rsrc %d head=%r"
              % (path[-1], ftype, creator, len(data), len(rsrc), data[:8]))
        if data[:8] == b"SIT!DFD3":
            hit += 1
            q = os.path.join(s.shots, path[-1].replace(" ", "_") + ".ss")
            open(q, "wb").write(data)
            print("             A SPACESAVER FILE: kept %s" % q)
    return 0 if hit else 1


def uirename(keep=False):
    """Rename through the Finder, on the freshly installed system.

    A name written by `hcopy` matches the rule but nothing ever
    happened: no rename, no close, no event. The panel says
    *"Immediately compress files ... whose Name begins or ends with"*,
    so the rename itself is the event, and it has to be done the way a
    person does it — select, Return, type, Enter, then click another
    icon, which is what actually commits a Finder name box.

    Runs against `ssboot.hfv`, the image `--freshinstall` leaves behind,
    so nothing here depends on the much-patched older install.
    """
    import glob
    src = BOOT if os.path.exists(BOOT) else INSTALLED
    boot = os.path.join(WORK, "ssuirename.hfv")
    shutil.copyfile(src, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssui-")
    big = (b"SpaceSaver probe, at length. " * 14000)[:400000]
    plain = list(SUBJECTS) + [("Bigone", "TEXT", "ttxt", big, b"")]
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        from ndd import macbinary_dated, MAC_EPOCH_1990   # noqa: E402
        for n, t, c, d, r in plain:
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
    s = Session(boot, [], os.path.join(SPECIMENS, "uirename"))
    try:
        s.boot()
        s.shot("desktop", wait=16.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.shot("windows-closed", wait=6.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        for name, letter in (("Bigone", "b"), ("Alpha", "a"),
                             ("Forked", "f")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac.key(letter)
            time.sleep(1.5)
            s.shot("selected-" + name, wait=0.5)
            s.mac.key("Return")            # open the name box
            time.sleep(2.0)
            s.mac.key("Right")             # keep the name, go to its end
            time.sleep(0.8)
            s.mac._xdo("type", "--delay", "150", "small")
            time.sleep(1.5)
            s.shot("typed-" + name, wait=0.5)
            s.mac.key("KP_Enter")          # Return leaves it editing
            time.sleep(4.0)
            s.mac.click(155, 310)          # another icon commits it
            time.sleep(4.0)
            s.shot("renamed-" + name, wait=40.0)
        for i in range(4):
            s.shot("settling%d" % i, wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=45.0)
    finally:
        time.sleep(10)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    from superdisk import read_forks                    # noqa: E402
    hit = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(out).items()):
        if not any(k in path[-1] for k in ("Alpha", "Forked", "Bigone")):
            continue
        print("spacesaver: %-14s %s/%s data %d rsrc %d head=%r"
              % (path[-1], ftype, creator, len(data), len(rsrc), data[:8]))
        if data[:8] == b"SIT!DFD3":
            hit += 1
            q = os.path.join(s.shots, path[-1].replace(" ", "_") + ".ss")
            open(q, "wb").write(data)
            print("             A SPACESAVER FILE: kept %s" % q)
    return 0 if hit else 1


def pages(keep=False):
    """Read every page of the panel, CHANGING NOTHING.

    On a freshly installed copy, what is already switched on is what a
    user would be using. Each of the four buttons — Idle Time,
    Compression & Other, Don't Compress, About SpaceSaver — is opened
    and photographed, then dismissed with Cancel so that nothing is
    written back. Only after reading these is it worth touching a
    setting.
    """
    boot = os.path.join(WORK, "sspages.hfv")
    src = BOOT if os.path.exists(BOOT) else INSTALLED
    shutil.copyfile(src, boot)
    s = Session(boot, [], os.path.join(SPECIMENS, "pages"))
    try:
        open_ss_panel(s)
        s.shot("panel-main", wait=6.0)
        for spot, tag in ((SS_IDLE_TIME, "idle-time"),
                          (SS_COMPRESSION, "compression-other"),
                          (SS_DONT_COMPRESS, "dont-compress")):
            s.mac.click(*spot)
            time.sleep(3.0)
            s.mac.click(*spot)            # the first input is swallowed
            s.shot("page-" + tag, wait=12.0)
            s.shot("page-" + tag + "-again", wait=6.0)
            s.mac.key("Escape")           # Cancel: change nothing
            time.sleep(2.5)
            s.mac.key("Escape")
            s.shot("after-" + tag, wait=6.0)
    finally:
        time.sleep(6)
        s.close()
    print("spacesaver: frames in %s" % s.shots)
    return 0


INSTALL_BUTTON = (390, 278)     # "Install" on the Standard Install panel
DEST_INSTALL = (378, 220)       # "Install" on the destination chooser
WARN_YES = (399, 137)           # "Yes" on the restart warning


def freshinstall(keep=False):
    """Install SpaceSaver the way a user would, onto a FRESH system.

    Every install so far has layered onto `ssboot.hfv`, which
    `session351` only copies from the stock system when it does not
    already exist — so the installed image this project has been driving
    for a fortnight has had installers run over it repeatedly, with
    patched INITs and deleted extensions in between. This starts from
    the stock `Sys7.img` every time.

    Two differences from `--install351`, both about being a user rather
    than a script: the registration number is left EMPTY instead of
    being fed codes that are known to be rejected, and every installer
    panel is photographed before anything is pressed — an Easy/Custom
    choice would decide whether SpaceSaver is installed at all, and
    pressing Return six times accepts whatever is in front of it.
    """
    if os.path.exists(BOOT):
        os.remove(BOOT)                       # a genuinely fresh system
    s, work, img = session351("freshinstall")
    try:
        s.boot()
        s.shot("desktop", wait=10.0)
        s.mac.click(*INSTALLER_ICON, double=True)
        s.shot("launched", wait=40.0)
        s.mac.click(*SPLASH_CONTINUE)
        s.shot("welcome", wait=22.0)
        s.mac.click(*WELCOME_CONTINUE)
        s.shot("registration", wait=22.0)
        # Name, organisation AND the serial. Leaving it empty gets
        # "The registration number that you have entered is invalid."
        # and the alert does not take Return — measured 2026-08-25, a
        # whole run spent stuck on it. `DLXC-963-029519` is the 3.5
        # code the maintainer supplied and the one 3.5.1 accepts
        # (DECISIONS.md 2026-08-22, what the registration wall costs).
        s.mac.click(*REG_NAME)
        time.sleep(1.0)
        s.mac._xdo("type", "--delay", "120", "MacExtract")
        s.mac.click(*REG_ORG)
        time.sleep(1.0)
        s.mac._xdo("type", "--delay", "120", "test")
        s.mac.click(*REG_NUMBER)
        time.sleep(1.0)
        s.mac._xdo("type", "--delay", "120", CODES_35[0])
        s.shot("registration-filled", wait=3.0)
        s.mac.click(*REG_REGISTER)
        time.sleep(5.0)
        s.mac.click(*REG_REGISTER)
        s.shot("after-register", wait=25.0)
        # Standard Install, then the destination chooser, then the
        # success alert. Photograph BEFORE each Return so the panel being
        # accepted is on record.
        # Click the buttons rather than pressing Return: one run got
        # through on Return and the next sat on the destination chooser
        # with the same keystroke, which is the swallowed-first-input
        # behaviour every panel in this installer has. Coordinates read
        # off `07-standard-install.png` and `08-destination.png`.
        # ONE click per button — a button is not an icon — and WALK the
        # pointer to it first. A warp followed immediately by a click
        # lands short (the same thing that made a menu pick open the
        # neighbouring menu), and 66 px short of "Yes" is "No".
        ox, oy = s.mac.origin(cached=False)

        def press(mx, my, tag=None):
            out = subprocess.run(["xdotool", "getmouselocation", "--shell"],
                                 env=s.mac.env, capture_output=True,
                                 text=True).stdout
            g = dict(l.split("=", 1) for l in out.strip().splitlines()
                     if "=" in l)
            hx, hy = int(g.get("X", 0)), int(g.get("Y", 0))
            tx, ty = ox + mx, oy + my
            n = max(abs(tx - hx), abs(ty - hy)) // 30 + 1
            for i in range(1, n + 1):
                s.mac._xdo("mousemove", str(hx + (tx - hx) * i // n),
                           str(hy + (ty - hy) * i // n))
                time.sleep(0.25)
            time.sleep(1.0)
            if tag:
                s.shot(tag)
            s.mac._xdo("click", "1")
            time.sleep(2.5)

        s.shot("standard-install", wait=16.0)
        press(*INSTALL_BUTTON, tag="on-install-button")
        s.shot("destination", wait=18.0)
        press(*DEST_INSTALL, tag="on-dest-install")
        # "Your Macintosh needs to be restarted after installation is
        # complete. Do you wish to continue?" — Yes. The copy happens
        # after this and BEFORE any restart, so answering it is safe.
        # This installer's alerts default to NO (tools/vmac/README.md), so
        # Return is not the answer here — click Yes, walked, with the
        # pointer photographed ON it before the button goes down.
        s.shot("restart-warning", wait=18.0)
        press(*WARN_YES, tag="on-yes")
        s.shot("copying", wait=55.0)
        s.shot("copying-2", wait=55.0)
        s.shot("success", wait=45.0)
        # **Do not press Restart.** That alert's only button restarts the
        # guest, and Mini vMac flushes a volume on EJECT or shutdown, not
        # on a guest restart — so the whole install is discarded and the
        # image comes back stock (measured 2026-08-25: "Installation was
        # successful", then a disk with nothing on it). Quit the
        # installer instead and shut down through the Finder, which is
        # what flushes.
        s.mac.command_key("q")
        s.shot("after-quit", wait=20.0)
        s.mac.command_key("q")
        s.shot("after-quit-2", wait=20.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=50.0)
    finally:
        time.sleep(10)
        s.close()
    print("spacesaver: screenshots in %s" % s.shots)
    print("spacesaver: fresh boot image at %s" % BOOT)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def enrollidle(keep=False):
    """Enrol the disk AND pick Idle Now, in one boot that is flushed.

    Every earlier attempt was missing one of the three things that have
    to hold together, and each was missing a different one:

      * a name matching the `small` rule — `--namerule` had it,
        `--magic` did not;
      * SpaceSaver's OWN menu, whose icon is at x=425 and not at Magic
        Menu's 283 (measured 2026-08-25, `--ssmenu`);
      * an ENROLLED volume — the Idle Time page's list is empty on the
        installed image, so the scan has nothing it may touch, and the
        one image that had a volume in it (`ssenrolled.hfv`) is the torn
        one `enroll()` left behind by never shutting down (BLOCKERS.md).

    So this does all three in a single boot and ends with Shut Down, so
    what it wrote survives.
    """
    import glob
    boot = os.path.join(WORK, "ssenrollidle.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssei-")
    big = (b"SpaceSaver probe, at length. " * 14000)[:400000]
    named = [(n + " small", t, c, d, r) for n, t, c, d, r in SUBJECTS]
    named.append(("Bigone small", "TEXT", "ttxt", big, b""))
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        from ndd import macbinary_dated, MAC_EPOCH_1990   # noqa: E402
        for n, t, c, d, r in named:
            q = os.path.join(tmp, n.replace(" ", "_") + ".bin")
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
    s = Session(boot, [], os.path.join(SPECIMENS, "enrollidle"))
    try:
        open_ss_panel(s)
        s.mac.click(*SS_IDLE_TIME)
        time.sleep(4.0)
        s.mac.click(*SS_IDLE_TIME)              # the first input is swallowed
        s.shot("idle-page", wait=10.0)
        s.mac.click(*IDLE_ADD)
        time.sleep(3.0)
        s.mac.click(*IDLE_ADD)
        s.shot("added", wait=6.0)
        s.mac.click(*IDLE_OK)
        time.sleep(3.0)
        s.mac.click(*IDLE_OK)
        s.shot("settings-ok", wait=8.0)
        # Cmd-W does not close this panel — measured on
        # `idlespec/09-panel-closed.png`, which is why SS_CLOSE_BOX
        # exists. Leaving it open leaves SpaceSaver's own window
        # frontmost, which is the opposite of idle.
        s.mac.click(*SS_CLOSE_BOX)
        time.sleep(2.0)
        s.mac.click(*SS_CLOSE_BOX)
        s.shot("panel-closed", wait=8.0)
        s.mac.command_key("w")                  # and the folder behind it
        s.shot("folder-closed", wait=6.0)

        ox, oy = s.mac.origin(cached=False)
        x = s.mac._xdo

        def walk(mx, my):
            out = subprocess.run(["xdotool", "getmouselocation", "--shell"],
                                 env=s.mac.env, capture_output=True,
                                 text=True).stdout
            g = dict(l.split("=", 1) for l in out.strip().splitlines()
                     if "=" in l)
            hx, hy = int(g.get("X", 0)), int(g.get("Y", 0))
            tx, ty = ox + mx, oy + my
            n = max(abs(tx - hx), abs(ty - hy)) // 30 + 1
            for i in range(1, n + 1):
                x("mousemove", str(hx + (tx - hx) * i // n),
                  str(hy + (ty - hy) * i // n))
                time.sleep(0.25)
            time.sleep(0.8)

        walk(SS_MENU_X, 8)
        x("mousedown", "1")
        time.sleep(1.6)
        s.shot("menu-opened")
        walk(SS_MENU_X - 60, SS_MENU_IDLE_NOW)
        s.shot("hover-idlenow")
        x("mouseup", "1")
        s.shot("after-pick", wait=30.0)
        # Then leave it alone. A screenshot is not input, so the guest
        # goes on believing nobody is there.
        for i in range(6):
            s.shot("working%d" % i, wait=90.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=45.0)
    finally:
        time.sleep(10)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    from superdisk import read_forks                    # noqa: E402
    hit = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(out).items()):
        if not path[-1].endswith("small"):
            continue
        print("spacesaver: %-14s %s/%s data %d rsrc %d head=%r"
              % (path[-1], ftype, creator, len(data), len(rsrc), data[:8]))
        if data[:8] == b"SIT!DFD3":
            hit += 1
            q = os.path.join(s.shots, path[-1].replace(" ", "_") + ".ss")
            open(q, "wb").write(data)
            print("             A SPACESAVER FILE: kept %s" % q)
    return 0 if hit else 1


def idleenrolled(keep=False):
    """Idle Now, on a volume that is actually ENROLLED.

    The last missing half. `--idlepick` picked *Idle Now* correctly from
    SpaceSaver's own menu (x=425, measured) and nothing happened, and the
    preferences say why: the volume-list blob on `ssinstalled.hfv` is
    empty, while the image a previous session enrolled carries
    `System_7_0_1`. Idle-time compression scans enrolled volumes, so on
    the base image it has nothing to scan.

    So: boot the enrolled image, put subjects matching the `small` rule
    on it, and pick Idle Now.
    """
    import glob
    base = os.path.join(WORK, "ssenrolled.hfv")
    if not os.path.exists(base):
        raise SystemExit("spacesaver: no ssenrolled.hfv — run --enroll first")
    boot = os.path.join(WORK, "ssidleenrolled.hfv")
    shutil.copyfile(base, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssie-")
    big = (b"SpaceSaver probe, at length. " * 14000)[:400000]
    named = [(n + " small", t, c, d, r) for n, t, c, d, r in SUBJECTS]
    named.append(("Bigone small", "TEXT", "ttxt", big, b""))
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        for n, t, c, d, r in named:
            q = os.path.join(tmp, n.replace(" ", "_") + ".bin")
            open(q, "wb").write(macbinary(n, t, c, d, r))
            subprocess.run(["hcopy", "-m", q, ":"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "idleenrolled"))
    try:
        s.boot()
        s.shot("desktop", wait=16.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.shot("windows-closed", wait=6.0)

        ox, oy = s.mac.origin(cached=False)
        x = s.mac._xdo

        def walk(mx, my):
            out = subprocess.run(["xdotool", "getmouselocation", "--shell"],
                                 env=s.mac.env, capture_output=True,
                                 text=True).stdout
            g = dict(l.split("=", 1) for l in out.strip().splitlines()
                     if "=" in l)
            hx, hy = int(g.get("X", 0)), int(g.get("Y", 0))
            tx, ty = ox + mx, oy + my
            n = max(abs(tx - hx), abs(ty - hy)) // 30 + 1
            for i in range(1, n + 1):
                x("mousemove", str(hx + (tx - hx) * i // n),
                  str(hy + (ty - hy) * i // n))
                time.sleep(0.25)
            time.sleep(0.8)

        walk(SS_MENU_X, 8)
        x("mousedown", "1")
        time.sleep(1.6)
        s.shot("opened")
        walk(SS_MENU_X - 60, SS_MENU_IDLE_NOW)
        s.shot("hover-idlenow")
        x("mouseup", "1")
        s.shot("after-pick", wait=30.0)
        s.shot("working", wait=60.0)
        s.shot("working-2", wait=90.0)
        s.shot("settled", wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=40.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_specimen(out, s.shots)


def calib(keep=False):
    """Where does a Mac coordinate actually land? Measure, do not assume.

    Two runs on 2026-08-25 asked for the same x and hit points ~140 px
    apart, so the mapping from Mac coordinates to X coordinates is not
    what the harness assumes — and a click that misses still lands on
    something, which is why a wrong pick photographs a plausible screen.
    This moves the pointer to known Mac positions along the menu bar and
    photographs each, so the offset can be read off the frames.
    """
    boot = os.path.join(WORK, "sscalib.hfv")
    shutil.copyfile(INSTALLED, boot)
    s = Session(boot, [], os.path.join(SPECIMENS, "calib"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        win = s.mac.dpy.window()
        out = subprocess.run(["xdotool", "getwindowgeometry", "--shell", win],
                             env=s.mac.env, capture_output=True,
                             text=True).stdout
        print("spacesaver: window geometry:\n%s" % out.strip())
        print("spacesaver: origin() returns %r" % (s.mac.origin(),))
        ox, oy = s.mac.origin()
        for x in (100, 283, 425, 470):
            s.mac._xdo("mousemove", str(ox + x), str(oy + 100))
            time.sleep(1.0)
            s.shot("at-x%d" % x)
    finally:
        time.sleep(5)
        s.close()
    print("spacesaver: frames in %s" % s.shots)
    return 0


def idlepick(keep=False):
    """Drive SpaceSaver's menu by hand, photographing every step.

    `Session.menu` drags to `title_x + 25`, which for a menu at the RIGHT
    edge of the bar is outside the box: System 7 shifts a dropdown left
    to fit the screen, so SpaceSaver's spans roughly x=258..443 under an
    icon at 425. This presses on the icon, shoots BEFORE moving so the
    menu that opened is identifiable, then hovers each item.
    """
    import glob
    boot = os.path.join(WORK, "ssidlepick.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssip-")
    big = (b"SpaceSaver probe, at length. " * 14000)[:400000]
    named = [(n + " small", t, c, d, r) for n, t, c, d, r in SUBJECTS]
    named.append(("Bigone small", "TEXT", "ttxt", big, b""))
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        for n, t, c, d, r in named:
            q = os.path.join(tmp, n.replace(" ", "_") + ".bin")
            open(q, "wb").write(macbinary(n, t, c, d, r))
            subprocess.run(["hcopy", "-m", q, ":"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "idlepick"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.shot("windows-closed", wait=6.0)

        ox, oy = s.mac.origin(cached=False)   # never trust the cache here
        print("spacesaver: origin at pick time: %d,%d" % (ox, oy))
        x = s.mac._xdo

        def where():
            out = subprocess.run(["xdotool", "getmouselocation", "--shell"],
                                 env=s.mac.env, capture_output=True,
                                 text=True).stdout
            g = dict(l.split("=", 1) for l in out.strip().splitlines()
                     if "=" in l)
            return int(g.get("X", -1)), int(g.get("Y", -1))

        def settle(mx, my):
            """Walk the pointer there, and say where it actually ended up.

            A single long warp does not arrive: jumping from (250, 38) to
            (425, 8) pressed at Mac x=283 and opened the neighbouring
            menu — twice, with the origin verified correct both times
            (2026-08-25). The sweep that walks the bar in ~15 px steps
            lands every time, so this walks too, and logs the host
            pointer so a miss is visible in the log rather than only in
            a frame nobody reads.
            """
            hx, hy = where()
            tx, ty = ox + mx, oy + my
            steps = max(abs(tx - hx), abs(ty - hy)) // 30 + 1
            for i in range(1, steps + 1):
                x("mousemove", str(hx + (tx - hx) * i // steps),
                  str(hy + (ty - hy) * i // steps))
                time.sleep(0.25)
            time.sleep(0.8)
            gx, gy = where()
            print("spacesaver: asked Mac(%d,%d) -> host(%d,%d), pointer at "
                  "host(%d,%d) = Mac(%d,%d)"
                  % (mx, my, tx, ty, gx, gy, gx - ox, gy - oy))

        settle(SS_MENU_X, 8)
        x("mousedown", "1")
        time.sleep(1.8)
        s.shot("opened")                       # which menu IS this?
        for y, tag in ((SS_MENU_IDLE_ON, "hover-toggle"),
                       (SS_MENU_IDLE_NOW, "hover-idlenow")):
            settle(SS_MENU_X - 60, y)
            s.shot(tag)
        x("mouseup", "1")
        s.shot("after-pick", wait=30.0)
        s.shot("working", wait=60.0)
        s.shot("settled", wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=40.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_specimen(out, s.shots)


def idlemenu(keep=False):
    """Ask SpaceSaver's own menu to compress, with matching names present.

    The menu's toggle reads *Turn Idle Time Off*, so idle-time
    compression is already ON; *Idle Now* runs the scan without waiting
    for the machine to go quiet. The subjects are named to match the
    `small` rule, which is the filter that scan applies.
    """
    import glob
    boot = os.path.join(WORK, "ssidlemenu.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssim-")
    big = (b"SpaceSaver probe, at length. " * 14000)[:400000]
    named = [(n + " small", t, c, d, r) for n, t, c, d, r in SUBJECTS]
    named.append(("Bigone small", "TEXT", "ttxt", big, b""))
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        for n, t, c, d, r in named:
            q = os.path.join(tmp, n.replace(" ", "_") + ".bin")
            open(q, "wb").write(macbinary(n, t, c, d, r))
            subprocess.run(["hcopy", "-m", q, ":"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "idlemenu"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.shot("windows-closed", wait=6.0)
        s.menu(SS_MENU_X, SS_IDLE_NOW_Y, "idle-now")
        s.shot("working", wait=45.0)
        s.shot("working-2", wait=60.0)
        s.shot("settled", wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=40.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_specimen(out, s.shots)


def ssmenu(keep=False):
    """Find SpaceSaver's OWN menu, then use it.

    `STR# 1024` is *About SpaceSaver Menu...;(-;Turn Idle-Time On;Idle
    Now;(-;Open Control Panel*, and `STR# -4064` calls the mechanism
    "Idle Time Compression ... while your computer is inactive". So the
    name rule is a FILTER the idle scanner applies, and the scanner is
    what has to be switched on — which is what this menu does.

    `--idlenow` went looking for it with `~Magic Menu™` DELETED and
    found no icon menu, at Magic Menu's own x. A System 7 menu bar puts
    extension icons at the RIGHT end, so this photographs every icon
    position across the right of the bar before choosing anything.
    """
    import glob
    boot = os.path.join(WORK, "ssmenu.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssmenu-")
    big = (b"SpaceSaver probe, at length. " * 14000)[:400000]
    named = [(n + " small", t, c, d, r) for n, t, c, d, r in SUBJECTS]
    named.append(("Bigone small", "TEXT", "ttxt", big, b""))
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        for n, t, c, d, r in named:
            q = os.path.join(tmp, n.replace(" ", "_") + ".bin")
            open(q, "wb").write(macbinary(n, t, c, d, r))
            subprocess.run(["hcopy", "-m", q, ":"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    s = Session(boot, [], os.path.join(SPECIMENS, "ssmenu"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.shot("windows-closed", wait=6.0)
        # Photograph every icon slot, shooting straight after the PRESS so
        # the frame names the menu that opened rather than whatever the
        # drag afterwards wandered into. The origin is re-queried because
        # a cached (0,0) shifts every coordinate 144 px (interactive.py).
        ox, oy = s.mac.origin(cached=False)
        print("spacesaver: origin %d,%d" % (ox, oy))
        xdo = s.mac._xdo
        for bx in (270, 285, 300, 400, 415, 425, 440, 455, 470, 485):
            xdo("mousemove", str(ox + bx), str(oy + 8))
            time.sleep(0.5)
            xdo("mousedown", "1")
            time.sleep(1.4)
            s.shot("press-x%d" % bx)
            xdo("mouseup", "1")
            time.sleep(0.8)
            s.mac.key("Escape")
            time.sleep(0.6)
        s.shot("after-sweep", wait=4.0)
    finally:
        time.sleep(6)
        s.close()
    print("spacesaver: frames in %s" % s.shots)
    return 0


MAGIC_INFO_Y = MAGIC_COMPRESS_Y + 16      # the item below Compress


def ssinfo(keep=False):
    """Ask the application what it thinks of the file.

    *SpaceSaver Compress* is silent when it declines — `mCompressFile`
    @0x549c returns an `OSErr`, and only some refusals reach the
    `STR# 1001` alerts. The menu item BELOW it, *SpaceSaver Info...*,
    exists to report on a selection, so it is the cheapest question to
    ask after `--magicname` showed the command running and doing
    nothing (OPEN_ITEMS.md).

    Same subjects as `--magicname`, including the 400 KB one: select,
    choose Info, photograph whatever it says.
    """
    import glob
    boot = os.path.join(WORK, "ssinfo.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssinfo-")
    big = (b"SpaceSaver probe, at length. " * 14000)[:400000]
    named = [(n + " small", t, c, d, r) for n, t, c, d, r in SUBJECTS]
    named.append(("Bigone small", "TEXT", "ttxt", big, b""))
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        for n, t, c, d, r in named:
            q = os.path.join(tmp, n.replace(" ", "_") + ".bin")
            open(q, "wb").write(macbinary(n, t, c, d, r))
            subprocess.run(["hcopy", "-m", q, ":"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    s = Session(boot, [], os.path.join(SPECIMENS, "ssinfo"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(3):
            s.mac.command_key("w")
            time.sleep(2.5)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac.key("b")                      # Bigone small
        time.sleep(1.5)
        s.shot("selected", wait=0.5)
        s.menu(MAGIC_X, MAGIC_INFO_Y, "info-menu")
        s.shot("info-dialog", wait=20.0)
        s.shot("info-dialog-again", wait=10.0)
        s.mac.key("Return")
        s.shot("after-return", wait=8.0)
    finally:
        time.sleep(6)
        s.close()
    print("spacesaver: frames in %s" % s.shots)
    return 0


# The SpaceSaver panel's close box, measured off `idlespec/09-panel-closed.png`
# where Cmd-W did not close it: the window's title bar runs from x=163 to
# x=392 at y=98..112, so the box is at its left end.
SS_CLOSE_BOX = (171, 105)


def enrollmagic(keep=False):
    """Enrol the disk, THEN ask Magic Menu to compress. One boot.

    Two mechanisms have now been driven correctly on a machine that
    booted and was flushed, and neither compressed anything: idle time
    with the disk enrolled (`--idlespec`), and Magic Menu's *SpaceSaver
    Compress* on an unenrolled disk (`--magic`, whose menu shot shows the
    item highlighted over the selected file). The Idle Time page's
    wording is the remaining candidate — *"but only if they are located
    on the following disks"* — so this run does both: enrol the startup
    disk, close the panel, and then issue the command.
    """
    import glob
    boot = os.path.join(WORK, "ssenrollmagic.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssem-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
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
    s = Session(boot, [], os.path.join(SPECIMENS, "enrollmagic"))
    try:
        open_ss_panel(s)
        s.mac.click(*SS_IDLE_TIME)
        time.sleep(4.0)
        s.mac.click(*SS_IDLE_TIME)
        s.shot("idle-page", wait=10.0)
        s.mac.click(*IDLE_ADD)
        time.sleep(3.0)
        s.mac.click(*IDLE_ADD)
        s.shot("added", wait=6.0)
        s.mac.click(*IDLE_OK)
        time.sleep(3.0)
        s.mac.click(*IDLE_OK)
        s.shot("settings-ok", wait=8.0)
        s.mac.click(*SS_CLOSE_BOX)              # the panel's own close box
        s.shot("panel-closed", wait=8.0)
        for _ in range(3):                      # and the Finder's windows
            s.mac.command_key("w")
            time.sleep(2.5)
        s.shot("windows-closed", wait=6.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        for name, letter in (("Bigone", "b"), ("Alpha", "a"),
                             ("Forked", "f")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac.key(letter)
            time.sleep(1.5)
            s.shot("selected-" + name, wait=0.5)
            s.menu(MAGIC_X, MAGIC_COMPRESS_Y, "compress-" + name)
            s.shot("after-" + name, wait=45.0)
        s.shot("settled", wait=30.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_specimen(out, s.shots)


def rename_to(s, letter, suffix, tag):
    """Type-select an icon and append `suffix` to its name, in place.

    The sequence `--specimen` proved: Return opens the name box with the
    whole name selected, Right drops the selection to the end, Enter
    commits it (Return does not), and clicking another icon commits it
    the way a person would.
    """
    s.mac.key("Escape")
    time.sleep(0.6)
    s.mac.key(letter)
    time.sleep(1.5)
    s.mac.key("Return")
    time.sleep(2.0)
    s.mac.key("Right")
    time.sleep(0.8)
    s.mac._xdo("type", "--delay", "150", suffix)
    time.sleep(1.5)
    s.mac.key("KP_Enter")
    time.sleep(4.0)
    s.mac.click(155, 310)                  # another icon commits it
    time.sleep(3.0)
    s.shot("renamed-" + tag, wait=35.0)


def suffix(keep=False):
    """Ask the SAME page for two different things, and see which fires.

    The *Compression and Other Settings* page has two rename rules
    ticked (photographed, `idle/06-compression-page.png`): compress
    anything whose name begins or ends with `small`, and **stuff or
    expand an item when `.SIT` is added to its name**. The first has
    been driven correctly on a machine that booted and was flushed and
    did nothing. The second is a different subsystem — Magic Menu's
    stuffing rather than SpaceSaver's compressor — reading the same
    rename event.

    So: one boot, one rename each. If `.SIT` produces an archive and
    `small` produces nothing, the rename event reaches the extension and
    the compressor is what is refusing; if neither fires, no rename
    reaches it at all and the trigger is not what the page says.
    """
    import glob
    boot = os.path.join(WORK, "sssuffix.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="sssfx-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
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
    s = Session(boot, [], os.path.join(SPECIMENS, "suffix"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(6):                      # more windows than Cmd-Ws
            s.mac.command_key("w")              # was the last run's mistake
            time.sleep(2.0)
        s.shot("windows-closed", wait=6.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        rename_to(s, "a", "small", "Alpha")     # the compression rule
        rename_to(s, "f", ".SIT", "Forked")     # the stuffing rule
        s.shot("settled", wait=45.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_volume(out, s.shots)


def report_volume(img, shots):
    """Everything at the root of the volume, not just what was expected.

    A run that only looks up the names it put there cannot see a file
    the Mac CREATED — and both rules on that page make a new file, one
    of them deleting the original.
    """
    from superdisk import read_forks                    # noqa: E402
    known = dict((n, d) for n, _t, _c, d, _r in SUBJECTS)
    os.makedirs(SPECIMENS, exist_ok=True)
    hit = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(img).items()):
        if len(path) != 1:
            continue                            # root only
        base = path[0]
        orig = known.get(base) or known.get(base[:-5]) or known.get(base[:-4])
        mark = ""
        if data[:8] == b"SIT!DFD3":
            mark = "  <- SPACESAVER"
            hit += 1
        elif data[:4] == b"SIT!":
            mark = "  <- StuffIt archive"
            hit += 1
        elif orig is not None and data != orig:
            mark = "  <- changed"
        print("spacesaver: %-24s %s/%s data %7d rsrc %6d%s"
              % (base, ftype, creator, len(data), len(rsrc), mark))
        if mark:
            # Only a SpaceSaver file gets the `.ss` name the suite globs
            # for: the `.SIT` rename rule writes a StuffIt ARCHIVE, and a
            # suite that grades it as a specimen fails on a file that was
            # never a specimen.
            ext = ".ss" if data[:8] == b"SIT!DFD3" else ".other"
            q = os.path.join(SPECIMENS, base.replace("/", "_") + ext)
            open(q, "wb").write(data)
            if rsrc:
                open(q + ".rsrc", "wb").write(rsrc)
            if orig is not None:
                open(q + ".orig", "wb").write(orig)
            print("                          kept %s" % q)
    return 0 if hit else 1


# The Deluxe folder's names carry a Mac Roman trademark sign (0xAA), so
# every path here goes to `hcd`/`hcopy` as RAW BYTES — the rule
# `superdisk.read_forks` already states, and the reason a folder called
# `Terrainman 2.0 ƒ` was once silently skipped.
DELUXE = b"StuffIt Deluxe\xaa Folder"
DROPDIR = b"Drag & Drop Applications"


def drop(keep=False):
    """Launch `DropCompress™` and hand it a subject.

    What the rename runs established: a rename DOES reach the extension
    — `Forked` renamed to `Forked.SIT` came back a 228-byte StuffIt
    archive — and the *compress* rule on the same page still does
    nothing. So the trigger is not the obstacle; SpaceSaver's compressor
    is simply not being asked.

    `DropCompress™` is what the Deluxe folder calls the droplet, and a
    droplet launched with no document opens a file dialog. The subjects
    are copied into ITS folder first, so the dialog lists them where it
    opens and a type-select plus Return is the whole interaction.
    """
    import glob
    boot = os.path.join(WORK, "ssdrop.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssdrop-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        subprocess.run([b"hcd", b":" + DELUXE + b":" + DROPDIR],
                       check=True, capture_output=True, env=env)
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
    s = Session(boot, [], os.path.join(SPECIMENS, "drop"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(6):
            s.mac.command_key("w")
            time.sleep(2.0)
        s.shot("windows-closed", wait=6.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        for prefix, tag in (("StuffIt D", "deluxe"), ("Drag", "dropdir")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac._xdo("type", "--delay", "120", prefix)
            time.sleep(1.5)
            s.mac.command_key("o")
            s.shot("opened-" + tag, wait=14.0)
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "DropC")
        time.sleep(1.5)
        s.shot("selected-droplet", wait=0.5)
        s.mac.command_key("o")
        s.shot("droplet-open", wait=30.0)
        # A Standard File dialog: type the name, then Open.
        s.mac._xdo("type", "--delay", "150", "Alpha")
        time.sleep(2.0)
        s.shot("dialog-typed", wait=1.0)
        s.mac.key("Return")
        s.shot("after-open", wait=45.0)
        s.shot("settled", wait=30.0)
        s.mac.command_key("q")
        s.shot("quit", wait=20.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_tree(out, s.shots)


def report_tree(img, shots):
    """Everything on the volume that is a SpaceSaver file or changed.

    Not just the root: the subjects are in a folder three levels down,
    and a droplet may write its output beside them or anywhere else.
    """
    from superdisk import read_forks                    # noqa: E402
    known = dict((n, d) for n, _t, _c, d, _r in SUBJECTS)
    os.makedirs(SPECIMENS, exist_ok=True)
    hit = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(img).items()):
        base = path[-1]
        orig = (known.get(base) or known.get(base[:-5]) or
                known.get(base[:-4]))
        mark = ""
        if data[:8] == b"SIT!DFD3":
            mark = "  <- SPACESAVER"
        elif orig is not None and data != orig:
            mark = "  <- changed"
        elif orig is None:
            continue
        print("spacesaver: %-40s %s/%s data %7d rsrc %6d%s"
              % ("/".join(path)[-40:], ftype, creator, len(data), len(rsrc),
                 mark))
        if mark:
            hit += mark.endswith("SPACESAVER")
            ext = ".ss" if data[:8] == b"SIT!DFD3" else ".other"
            q = os.path.join(SPECIMENS, base.replace("/", "_") + ext)
            open(q, "wb").write(data)
            if rsrc:
                open(q + ".rsrc", "wb").write(rsrc)
            if orig is not None:
                open(q + ".orig", "wb").write(orig)
            print("     kept %s" % q)
    return 0 if hit else 1


# Icon positions inside the open `Drag & Drop Applications` window,
# measured off `drop/07-droplet-open.png`. A Finder window remembers
# where its icons are, so these are stable for this image.
DROPLET_ICON = (62, 110)
ALPHA_ICON = (122, 110)
FORKED_ICON = (122, 157)


def drag_icon(s, src, dst, tag):
    """Drag one Finder icon onto another.

    In several steps with a pause each: the Finder samples the mouse
    once a tick, and a press-and-release two milliseconds apart is a
    click on the source rather than a drag onto the target — the same
    reason `interactive.py` sends Command chords as keydown/keyup.
    """
    ox, oy = s.mac.origin()
    x = s.mac._xdo
    x("mousemove", str(ox + src[0]), str(oy + src[1]))
    time.sleep(0.6)
    x("mousedown", "1")
    time.sleep(0.8)
    for k in range(1, 5):                       # four intermediate steps
        ix = src[0] + (dst[0] - src[0]) * k // 4
        iy = src[1] + (dst[1] - src[1]) * k // 4
        x("mousemove", str(ox + ix), str(oy + iy))
        time.sleep(0.5)
    time.sleep(1.0)
    s.shot("dragging-" + tag)
    x("mouseup", "1")
    time.sleep(2.0)


def dragdrop(keep=False):
    """Drop a subject ON `DropCompress™`, which is what a droplet is for.

    Launching it with no document showed no dialog at all
    (`drop/07-droplet-open.png`: the menu bar goes to `File` alone and
    nothing opens), so the only way to give it a file is the way a
    person would. Both icons sit in one window at positions the Finder
    remembers, so the drag is two coordinates.
    """
    import glob
    boot = os.path.join(WORK, "ssdrag.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssdrag-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        subprocess.run([b"hcd", b":" + DELUXE + b":" + DROPDIR],
                       check=True, capture_output=True, env=env)
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
    s = Session(boot, [], os.path.join(SPECIMENS, "dragdrop"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(6):
            s.mac.command_key("w")
            time.sleep(2.0)
        s.shot("windows-closed", wait=6.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        for prefix, tag in (("StuffIt D", "deluxe"), ("Drag", "dropdir")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac._xdo("type", "--delay", "120", prefix)
            time.sleep(1.5)
            s.mac.command_key("o")
            s.shot("opened-" + tag, wait=14.0)
        drag_icon(s, ALPHA_ICON, DROPLET_ICON, "alpha")
        s.shot("after-alpha", wait=60.0)
        s.shot("settled", wait=45.0)
        s.mac.command_key("q")                  # in case it is still up
        s.shot("quit", wait=15.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_tree(out, s.shots)


# SpaceSaver's OWN menu, from `STR# 1024` in the control panel:
#   About SpaceSaver Menu...;(-;Turn Idle-Time On;Idle Now;(-;Open Control Panel
# Six rows at the usual 15-pixel pitch, two of them separators.
#
# **x is 425, MEASURED** (`--ssmenu`, 2026-08-25): press each slot across
# the bar and photograph what opens. It was 283 here — Magic Menu's icon —
# which is why `--idlenow` deleted `~Magic Menu™` to give SpaceSaver the
# bar to itself and then reported "no icon menu at all": it was pressing
# the hole Magic Menu had left. System 7 puts extension icons at the RIGHT
# end, and SpaceSaver's dropdown is shifted left to fit, spanning x=258..443.
SS_MENU_X = 425
SS_MENU_IDLE_ON = 60
SS_MENU_IDLE_NOW = 75


def idlenow(keep=False):
    """Ask SpaceSaver to do its idle sweep NOW, from its own menu.

    `STR# 1024` is a menu this machine has never shown: the menu bar
    carries Magic Menu's icon menu instead, and Magic Menu's own
    *SpaceSaver Compress* does nothing. The one explicit "do it now"
    this software has is **Idle Now**, in the menu SpaceSaver installs
    when its *Show Menu* option is on — so this run deletes
    `~Magic Menu™` from the Control Panels folder before booting and
    takes the slot it was using.

    The disk is enrolled first, because the idle sweep's own page says
    it compresses "files not modified in the last 1 Months ... but only
    if they are located on the following disks", and the subjects are
    stamped 1990 for the same sentence.
    """
    import glob
    boot = os.path.join(WORK, "ssidlenow.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssin-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        # The name carries a Mac Roman trademark sign; raw bytes, as
        # everywhere else here.
        r = subprocess.run([b"hdel",
                            b":System Folder:Control Panels:~Magic Menu\xaa"],
                           capture_output=True, env=env)
        print("spacesaver: removed Magic Menu: %s"
              % ("ok" if r.returncode == 0 else
                 r.stderr.decode("utf-8", "replace").strip()))
        from ndd import macbinary_dated, MAC_EPOCH_1990   # noqa: E402
        for n, t, c, d, r2 in SUBJECTS:
            q = os.path.join(tmp, n + ".bin")
            open(q, "wb").write(macbinary_dated(n, t, c, d, r2,
                                                MAC_EPOCH_1990,
                                                MAC_EPOCH_1990))
            subprocess.run(["hcopy", "-m", q, ":"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "idlenow"))
    try:
        open_ss_panel(s)
        s.mac.click(*SS_IDLE_TIME)
        time.sleep(4.0)
        s.mac.click(*SS_IDLE_TIME)
        s.shot("idle-page", wait=10.0)
        s.mac.click(*IDLE_ADD)
        time.sleep(3.0)
        s.mac.click(*IDLE_ADD)
        s.shot("added", wait=6.0)
        s.mac.click(*IDLE_OK)
        time.sleep(3.0)
        s.mac.click(*IDLE_OK)
        s.shot("settings-ok", wait=8.0)
        s.mac.click(*SS_CLOSE_BOX)
        s.shot("panel-closed", wait=8.0)
        for _ in range(6):
            s.mac.command_key("w")
            time.sleep(2.0)
        s.shot("windows-closed", wait=6.0)
        s.menu(SS_MENU_X, SS_MENU_IDLE_ON, "menu-idle-on")
        s.shot("idle-on", wait=8.0)
        s.menu(SS_MENU_X, SS_MENU_IDLE_NOW, "menu-idle-now")
        s.shot("idle-now", wait=60.0)
        s.shot("settled", wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_volume(out, s.shots)


def parade(keep=False):
    """Photograph the startup icon parade, which nothing here ever has.

    Every run so far takes its first frame after the desktop has
    settled, and an extension that fails to install says so THERE — a
    crossed-out icon, or an alert that is gone by the time the Finder is
    up. `STR# 1001` in the control panel has seven ways for SpaceSaver
    to decline: the wrong system version, not enough memory, several
    copies at startup, a locked preferences file or startup volume, not
    enough free space, and "this copy has not been correctly installed".

    The `Idle Now` run made this worth doing: with `~Magic Menu™`
    deleted the menu bar carried NO icon menu at all, so the menu
    SpaceSaver's own *Show Menu* option promises was never installed.
    """
    boot = os.path.join(WORK, "ssparade.hfv")
    shutil.copyfile(INSTALLED, boot)
    s = Session(boot, [], os.path.join(SPECIMENS, "parade"))
    try:
        # No boot() first: the point is the frames BEFORE the desktop —
        # and Mini vMac runs unthrottled, so a Mac Plus is at the Finder
        # about two seconds after the process starts. Sampling every 2.5 s
        # photographed the settled desktop sixteen times.
        for i in range(30):
            s.shot("boot%02d" % i, wait=0.15)
        s.boot()
        s.shot("desktop", wait=10.0)
    finally:
        time.sleep(3)
        s.close()
    print("spacesaver: parade in %s" % s.shots)
    return 0


def commit(keep=False):
    """OK the Compression page, THEN rename — in one boot.

    Every earlier run assumed the rule on that page was in force because
    the page draws it ticked, with `small` in the field. Nothing has
    ever pressed OK on it and kept the result: `--idle` did press Return
    (the page's default button is OK) but its image was killed, and
    every other run opened the panel for the Idle Time page only.

    So this one commits the page and renames a subject in the same boot,
    and the machine is shut down afterwards like the rest.
    """
    import glob
    boot = os.path.join(WORK, "sscommit.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="sscm-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
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
    s = Session(boot, [], os.path.join(SPECIMENS, "commit"))
    try:
        open_ss_panel(s)
        s.mac.click(*SS_COMPRESSION)
        time.sleep(4.0)
        s.mac.click(*SS_COMPRESSION)
        s.shot("compression-page", wait=10.0)
        s.mac.key("Return")                     # OK is the default button
        s.shot("committed", wait=10.0)
        s.mac.click(*SS_CLOSE_BOX)
        s.shot("panel-closed", wait=8.0)
        for _ in range(6):
            s.mac.command_key("w")
            time.sleep(2.0)
        s.shot("windows-closed", wait=6.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        rename_to(s, "a", "small", "Alpha")
        s.shot("settled", wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    return report_volume(out, s.shots)


def newest_session_image(before):
    """The boot image Mini vMac has just been writing to.

    `run.py` boots from a COPY in the session's temp dir, so the image
    that carries what the guest did is that copy, not the file passed in.
    """
    import glob
    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    return sorted(cands, key=os.path.getmtime)[-1]


def twoboot(keep=False):
    """Create SpaceSaver's preferences, THEN reboot, THEN rename.

    The installed image has no `SpaceSaver Preferences` file: the
    installer never made one, and the control panel makes it the first
    time it is OK'd. `STR# -4064` says what the extension does without
    one — *"The SpaceSaver Preferences file could neither be found nor
    created"* — and an extension installs at STARTUP, so on this image
    it has never installed at all. That fits everything else: no
    SpaceSaver menu even with Magic Menu deleted, and no trigger of any
    kind doing anything.

    So this takes two boots. The first opens the panel and OKs it, which
    writes the preferences, and shuts down so they survive. The second
    boots the image that now has them and renames a subject.
    """
    boot = os.path.join(WORK, "ssprefs.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="sstb-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
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

    import glob
    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "twoboot"))
    try:
        open_ss_panel(s)
        s.mac.click(*SS_COMPRESSION)
        time.sleep(4.0)
        s.mac.click(*SS_COMPRESSION)
        s.shot("compression-page", wait=10.0)
        s.mac.key("Return")                     # OK writes the preferences
        s.shot("committed", wait=10.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    ready = os.path.join(WORK, "ssready.hfv")
    shutil.copyfile(newest_session_image(before), ready)
    from superdisk import read_forks                    # noqa: E402
    have = any(p[-1].startswith("SpaceSaver Pref")
               for p in read_forks(ready))
    print("spacesaver: preferences after boot 1: %s"
          % ("written" if have else "STILL MISSING"))

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s2 = Session(ready, [], os.path.join(SPECIMENS, "twoboot2"))
    try:
        s2.boot()
        s2.shot("desktop", wait=14.0)
        s2.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(6):
            s2.mac.command_key("w")
            time.sleep(2.0)
        s2.shot("windows-closed", wait=6.0)
        s2.mac.click(470, 55, double=True)
        s2.shot("bootvol", wait=14.0)
        rename_to(s2, "a", "small", "Alpha")
        s2.shot("settled", wait=60.0)
        s2.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s2.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s2.close()

    out = newest_session_image(before)
    print("spacesaver: reading back %s" % out)
    return report_volume(out, s2.shots)


def deluxe(keep=False):
    """Launch `StuffIt Deluxe™` and photograph its menus.

    The compressor is in `SSEn 1` of `StuffIt Engine™`, and the engine
    is a shared library — the extension in Control Panels is one client
    of it, and the application is another. Every attempt so far has gone
    through the extension, which on this machine does not install. The
    application does not need it.

    A probe, not an attempt: it opens each menu and photographs it, so
    the next run knows what to click.
    """
    boot = os.path.join(WORK, "ssdeluxe.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="ssdlx-")
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
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

    s = Session(boot, [], os.path.join(SPECIMENS, "deluxe"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(6):
            s.mac.command_key("w")
            time.sleep(2.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "StuffIt D")
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("opened-folder", wait=14.0)
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "StuffIt D")
        time.sleep(1.5)
        s.shot("selected-app", wait=0.5)
        s.mac.command_key("o")
        s.shot("launched", wait=40.0)
        for x in (40, 80, 120, 165, 210, 255, 300):
            s.peek(x, "menu-x%d" % x)
        s.mac.command_key("q")
        s.shot("quit", wait=20.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=25.0)
    finally:
        time.sleep(8)
        s.close()
    print("spacesaver: screenshots in %s" % s.shots)
    return 0


# ---------------------------------------------------------------------------
# Reading the format out of the software, which is what --layout does.
#
# SpaceSaver's container is written and read by two resources on the
# installed image: `SSEn 1` in `StuffIt Engine™`, which carries MacsBug
# symbols and so names every routine, and `ACMP 1` in the control panel,
# which only sniffs. Everything printed below is parsed out of those
# bytes; DECISIONS.md (2026-08-22, the layout) records what the
# disassembly of the named routines says and how it was read.

# What the layout was read out of. Each entry is a byte pattern that must
# be present in the named resource, so a different build of SpaceSaver
# makes this print FAIL rather than silently confirm today's reading.
WITNESSES = [
    ("eng", "SSEn", 1, "ReadSSHeader: ioReqCount = 84 at offset 0",
     b"\x70\x54\x2d\x40\xff\xf2"),
    ("eng", "SSEn", 1, "ReadSSHeader: cmpi.l #'SIT!',(a3)",
     b"\x0c\x93SIT!"),
    ("eng", "SSEn", 1, "ReadSSHeader: cmpi.l #'DFD3',4(a3)",
     b"\x0c\xabDFD3\x00\x04"),
    ("eng", "SSEn", 1, "DefaultSSHeader: move.l #'SIT!',(a3)",
     b"\x26\xbcSIT!"),
    ("eng", "SSEn", 1, "DefaultSSHeader: version 3, header length 84",
     b"\x70\x03\x27\x40\x00\x08\x70\x54\x27\x40\x00\x0c"),
    ("eng", "SSEn", 1, "MakeDFile: type 'SPSV', creator 'SIT!'",
     b"\x26\xbcSPSV\x27\x7cSIT!\x00\x04"),
    ("eng", "SSEn", 1, "mCompressFile: EOF rounded up to a multiple of 256",
     b"\x41\xe8\x00\xff\x20\x08\x02\x40\xff\x00"),
    ("eng", "SSEn", 1, "IsFileCmpressed: type 'SPSV', or a data fork "
     "length whose low byte is 0",
     b"\x0c\xaeSPSV\xff\x28\x67\x0e\x20\x2e\xff\x3e"
     b"\x02\x80\x00\x00\x00\xff"),
    ("ss", "ACMP", 1, "the control panel reads 8 bytes and compares both",
     b"\x0c\xaeSIT!"),
]

# The 84-byte header, and the 16-byte fork record inside it. Field names
# are this project's; the software names none of them.
SS_HEADER = [
    (0, 4, "'SIT!'", "first magic"),
    (4, 4, "'DFD3'", "second magic"),
    (8, 4, "version", "3. UpdateSSHeader converts 1 and 2 in place"),
    (12, 4, "header length", "84"),
    (16, 4, "flags", "0x00000041 in everything this engine writes; "
     "bit 0 required to compress, bit 0 or 1 to expand"),
    (20, 16, "fork record", "DATA fork"),
    (36, 16, "fork record", "RESOURCE fork"),
    (52, 4, "fdType", "the file's type before compression"),
    (56, 4, "fdCreator", "its creator"),
    (60, 2, "fdFlags", "its Finder flags; six bits are restored from here"),
    (62, 2, "zero", "set to 0 on every write"),
    (64, 20, "reserved", "zeroed on every write"),
]

SS_FORK_RECORD = [
    (0, 4, "compressed length", "bytes the module wrote"),
    (4, 4, "original length", "0 means the fork is absent, and then the "
     "two bytes below are 0 too"),
    (8, 4, "offset", "from the start of the data fork"),
    (12, 1, "parameter set", "indexes the engine's 'PrAm' resources; 0 in "
     "everything this engine writes"),
    (13, 1, "compressor", "index below, bit 7 = the PowerPC module"),
    (14, 2, "zero", "cleared by SetupAFork"),
]


def resources(fork):
    """A resource fork's bytes -> {type: {id: (name, data)}}.

    Inside Macintosh I-121. The map holds a type list of (type, count-1,
    offset) and, per type, a reference list of (id, name offset, attrs,
    24-bit data offset, handle).
    """
    dataoff, mapoff, _, maplen = struct.unpack(">IIII", fork[:16])
    m = fork[mapoff:mapoff + maplen]
    typeoff, nameoff = struct.unpack(">HH", m[24:28])
    out = {}
    for i in range(struct.unpack(">H", m[typeoff:typeoff + 2])[0] + 1):
        e = typeoff + 2 + i * 8
        rtype = m[e:e + 4].decode("mac-roman")
        count = struct.unpack(">H", m[e + 4:e + 6])[0] + 1
        reflist = typeoff + struct.unpack(">H", m[e + 6:e + 8])[0]
        out[rtype] = {}
        for j in range(count):
            r = reflist + j * 12
            rid = struct.unpack(">h", m[r:r + 2])[0]
            noff = struct.unpack(">h", m[r + 2:r + 4])[0]
            doff = struct.unpack(">I", b"\0" + m[r + 5:r + 8])[0]
            name = ""
            if noff >= 0:
                p = nameoff + noff
                name = m[p + 1:p + 1 + m[p]].decode("mac-roman", "replace")
            p = dataoff + doff
            n = struct.unpack(">I", fork[p:p + 4])[0]
            out[rtype][rid] = (name, fork[p + 4:p + 4 + n])
    return out


def macsbug_symbols(code):
    """Offsets and names of the MacsBug symbols in a 68k code resource.

    A symbol sits after its routine's RTS: a length byte 0x80|n, n name
    bytes, padded to even, then a word. So the offset reported here is
    where the routine ENDS, and the next one starts at name + 2.
    """
    out, i = [], 0
    while i < len(code) - 2:
        n = code[i] & 0x1f
        if 0x81 <= code[i] <= 0x9f and n >= 3:
            s = code[i + 1:i + 1 + n]
            if re.fullmatch(rb"[A-Za-z_][A-Za-z0-9_ .]*", s):
                out.append((i, s.decode()))
                i += 1 + n
                continue
        i += 1
    return out


def layout():
    """Read the container layout out of the installed SpaceSaver.

    No emulator: the resources come off the disk image with `hcopy`, and
    everything printed is parsed from them. `--make` would give a
    specimen to check it against; this gives the layout without one.
    """
    from superdisk import read_forks                    # noqa: E402
    if not os.path.exists(INSTALLED):
        raise SystemExit("spacesaver: no installed image — run --install351 "
                         "then --keep-installed")
    forks, wanted = read_forks(INSTALLED), {}
    for path, (ftype, creator, _data, rsrc) in forks.items():
        if creator == "SMKR":
            wanted["ss"] = (path[-1], ftype, creator, rsrc)
        elif creator == "SITe":
            wanted["eng"] = (path[-1], ftype, creator, rsrc)
    for key in ("ss", "eng"):
        if key not in wanted:
            raise SystemExit("spacesaver: %s not on %s" % (key, INSTALLED))
    res = {}
    for key, (name, ftype, creator, rsrc) in wanted.items():
        res[key] = resources(rsrc)
        print("%-22s %s/%s  %d B resource fork, %d types"
              % (name, ftype, creator, len(rsrc), len(res[key])))

    print("\nThe engine's routines, from its own MacsBug symbols "
          "(offset = where each ENDS):")
    syms = macsbug_symbols(res["eng"]["SSEn"][1][1])
    keep = ("SSHeader", "Fork", "File", "Compressor", "IsFileCmpressed")
    for off, name in syms:
        if any(k in name for k in keep):
            print("  %06x  %s" % (off, name))
    print("  ... %d symbols in all" % len(syms))

    print("\nCompression header, 84 bytes at offset 0 of the data fork:")
    for off, size, name, note in SS_HEADER:
        print("  +%-3d %-3d %-18s %s" % (off, size, name, note))
    print("\n  fork record, 16 bytes:")
    for off, size, name, note in SS_FORK_RECORD:
        print("    +%-3d %-2d %-18s %s" % (off, size, name, note))
    print("\n  The two records are fixed: data first, then resource. The"
          "\n  LARGER fork's stream is written first, at offset 84, and the"
          "\n  other follows it — read each one at its own offset. The data"
          "\n  fork's EOF is rounded up to a multiple of 256, which is how"
          "\n  a compressed file is recognised without opening it; the"
          "\n  compressed file's resource fork is empty.")

    print("\nCompressor modules, each field read from the module's own "
          "header:")
    print("  %-4s %-4s %-3s %-3s %-9s %s"
          % ("id", "idx", "rev", "ppc", "cpus", "name"))
    for key in ("ss", "eng"):
        for rid in sorted(res[key].get("CMod", {})):
            name, code = res[key]["CMod"][rid]
            sel, ppc, cpus = struct.unpack(">HHI", code[0x20:0x28])
            print("  %-4d %-4d %-3d %-3s %08x  %s"
                  % (rid, sel >> 8, sel & 0xff, "yes" if ppc else "-",
                     cpus, name))
        break                              # both files carry the same set
    print("  idx is the fork record's compressor byte. A module runs on a"
          "\n  CPU when bit (31 - Gestalt 'cput') of its mask is set, with"
          "\n  PowerPC's 0x0101.. mapped down to 8..; where two modules"
          "\n  claim the same idx the higher rev wins. Entry vectors are"
          "\n  bra.w at +0x00, +0x08, +0x10 and +0x18: +0x08 compresses,"
          "\n  +0x10 expands, and a PowerPC module's PEF starts at +0x2c.")

    # The modules themselves, written out where `tools/ssmodule/` and
    # `gen_ss_dict.py` look for them: `CMod 4`'s last eighteen bytes are
    # what an unfilled method 2 table entry points at, so they are
    # needed to decode as much as the `PrAm` table below is.
    for rid in sorted(res["ss"].get("CMod", {})):
        _n, code = res["ss"]["CMod"][rid]
        os.makedirs(SPECIMENS, exist_ok=True)
        q = os.path.join(SPECIMENS, "CMod%d.bin" % rid)
        with open(q, "wb") as f:
            f.write(code)

    # The preset dictionary, written out where the suite looks for it.
    # It is Aladdin's, so it lives beside the ROM and the System image
    # rather than in the repository (`tools/run_spacesaver.py`).
    pram = res["ss"].get("PrAm", {})
    for rid in sorted(pram):
        name, data = pram[rid]
        q = os.path.join(SPECIMENS, "PrAm%d.bin" % rid)
        os.makedirs(SPECIMENS, exist_ok=True)
        open(q, "wb").write(data)
        print("\n'PrAm' %d: %d bytes, the LZSS window's preset contents "
              "-> %s" % (rid, len(data), q))
        print("  first 60: %r" % data[:60].decode("mac-roman", "replace"))

    print("\nWhat this reading rests on:")
    bad = 0
    for key, rtype, rid, what, pattern in WITNESSES:
        code = res[key].get(rtype, {}).get(rid, ("", b""))[1]
        at = code.find(pattern)
        bad += at < 0
        print("  %-6s %s %s" % ("%s %d" % (rtype, rid),
                                "%06x" % at if at >= 0 else "MISSING",
                                what))
    print("spacesaver: %d of %d witnesses found"
          % (len(WITNESSES) - bad, len(WITNESSES)))
    return 1 if bad else 0


# What the AppleLink `.pkg` reading rests on, in the translator's own
# bytes. Same idea as WITNESSES above: a different build makes this
# print MISSING rather than silently confirm today's reading.
PKG_WITNESSES = [
    ("the tokenizer skips space, tab and CR", b"\x0c\x13\x00\x20\x67"),
    ("token 1 is compared with STR# 129 item 1",
     b"\x2f\x3c\x00\x01\x00\x81"),
    ("token 3 is compared with item 4 (\"to\")",
     b"\x2f\x3c\x00\x04\x00\x81"),
    ("and with item 9 (\"into\")", b"\x2f\x3c\x00\x09\x00\x81"),
]


def pkg(keep=False):
    """Read AppleLink `.pkg`'s recogniser out of Aladdin's translator.

    The StuffIt Deluxe 3.5.1 installation made for SpaceSaver carries
    fourteen translators, and one of them is `PKG Expand Translator` —
    the only implementation of AppleLink's package format this project
    has ever had sight of (BLOCKERS.md). No emulator: the resources come
    off the disk image with `hcopy` and everything below is parsed from
    them.
    """
    from superdisk import read_forks                    # noqa: E402
    import struct
    if not os.path.exists(INSTALLED):
        raise SystemExit("spacesaver: no installed image")
    forks = read_forks(INSTALLED)
    found = None
    for path, (ftype, creator, _d, rsrc) in forks.items():
        if path[-1] == "PKG Expand Translator":
            found = (path, ftype, creator, rsrc)
    if not found:
        raise SystemExit("spacesaver: no PKG Expand Translator on %s"
                         % INSTALLED)
    path, ftype, creator, rsrc = found
    print("%s  %s/%s  %d B resource fork" % ("/".join(path), ftype, creator,
                                             len(rsrc)))
    res = resources(rsrc)
    name = res["Name"][0][1]
    code = res["Othe"][0][1]
    print("  'Name' 0: %r — what the engine calls this translator"
          % name[1:1 + name[0]].decode("mac-roman"))
    print("  'Othe' 0: %d bytes of 68k" % len(code))

    strs = res["STR#"][129][1]
    cnt = struct.unpack(">H", strs[:2])[0]
    p, items = 2, []
    for _ in range(cnt):
        n = strs[p]
        items.append(strs[p + 1:p + 1 + n].decode("mac-roman", "replace"))
        p += 1 + n
    print("\n  'STR#' 129, which is the grammar's vocabulary:")
    for i, it in enumerate(items, 1):
        print("    %2d  %r" % (i, it))

    print("\n  The recogniser @0x2952 accepts a file when its first"
          "\n  whitespace-delimited token is item 1 and its third is item 4"
          "\n  or item 9 — so a package is TEXT, and that is its whole"
          "\n  magic. `macextract sniff` implements exactly that and no more.")

    print("\n  What this reading rests on:")
    bad = 0
    for what, pattern in PKG_WITNESSES:
        at = code.find(pattern)
        bad += at < 0
        print("    %-8s %s" % ("%06x" % at if at >= 0 else "MISSING", what))
    print("spacesaver: %d of %d witnesses found"
          % (len(PKG_WITNESSES) - bad, len(PKG_WITNESSES)))
    return 1 if bad else 0


# ---------------------------------------------------------------------------
# Running that recogniser, with a package this machine wrote.
#
# `--pkg` reads the grammar out of `PKG Expand Translator`; `--pkgexpand`
# feeds it back. Nothing here invents a byte of the format: the line is
# `Decode <item> to|into <destination>`, exactly the three tokens @0x2952
# tests, and `STR# 129` supplies both words. What is being asked is not
# "is our decoder right" — there is no decoder — but whether a package
# HAS a payload at all, which is the open item (OPEN_ITEMS.md).

# StuffIt Deluxe 3.5.1's Translate menu, measured off `--deluxe`'s
# `12-menu-x300.png`: the menu box is x=262..429, its items are 16 px
# apart from y=76, and "PKG Expand..." is the seventh below the
# separator. Not a submenu, so Mini vMac can select it.
TRANSLATE_X = 300
PKG_EXPAND_Y = 171
CPT_EXPAND_Y = 123                      # "CPT Expand...", four items above
CONVERT_BUTTON = (452, 289)             # DropConvert's Convert button

# A real Compact Pro archive, as the calibration for an empty file list.
CPT_FIXTURE = "derived-keyAhead.cpt"

# The folder the application lives in, as the raw Mac Roman bytes `hls`
# prints: everything the run touches goes in there, so a package, its
# item and its destination are all in one directory and no path syntax
# is being tested by accident.
SIT_FOLDER = b"StuffIt Deluxe\xaa Folder"

PKG_INNER = "Widget"
PKG_PAYLOAD = (b"AppleLink package probe. " * 40 +
               bytes(bytearray(range(256))))
PKG_FORK = b"\x1cAppleLink package probe fork"

# What a package IS, to Aladdin: @0x37f0 of the translator reads the
# candidate's Finder info and accepts it when its TYPE is 'PACT' or its
# CREATOR is 'EXTR' — a type test, not the token test @0x2952 does. The
# first run of this mode wrote its packages as TEXT/ttxt and PKG
# Expand's Standard File dialog listed no files at all, only folders
# (`01-...` through `44-...`, 2026-09-01). So the type is the gate and
# the text is what is read after it, and both are measured.
PKG_TYPES = {
    "Both": ("PACT", "EXTR"),
    "Type": ("PACT", "ttxt"),
    "Maker": ("TEXT", "EXTR"),
    "Plain": ("TEXT", "ttxt"),
    "Gone": ("PACT", "EXTR"),
}

# One package per question. `Plain` is the control that must NOT appear
# in the dialog, and `Gone` names an item that does not exist: between
# them a run where nothing happens is told from a run where the menu was
# never clicked, which is the whole difficulty with a null result here.
PACKAGES = [
    ("Both.pkg", "Bo", 'Decode "Payload.hqx" to "OutA"',
     "type and creator both Aladdin's — the question"),
    ("Type.pkg", "Ty", 'Decode Payload.hqx into OutB',
     "type only, and the other two vocabulary words"),
    ("Maker.pkg", "Ma", 'Decode "Payload.hqx" to "OutC"',
     "creator only — @0x37f0 accepts either"),
    ("Gone.pkg", "Go", 'Decode "Nowhere.hqx" to "OutD"',
     "no such item — expect STR# 129 item 13"),
    ("Plain.pkg", None, 'Decode "Payload.hqx" to "OutD"',
     "TEXT/ttxt: must not be listed at all"),
]


def pkgexpand(keep=False):
    """Hand Aladdin's own PKG Expand a package written here.

    OPEN_ITEMS.md files AppleLink `.pkg` as waiting on a specimen. That
    is an assumption, not a property: the format is TEXT whose whole
    grammar `--pkg` transcribed, so this machine can write one, and the
    second reader — the translator that grammar came out of — is on this
    image. The measured hypothesis is that a package is a transfer
    MANIFEST naming files that sit beside it (DECISIONS.md 2026-08-23),
    and a manifest is settled by putting the named file there and
    watching what the expander does with it.

    Five packages, one boot, four of them opened: the fifth is TEXT/ttxt
    and its result is that PKG Expand's Standard File dialog does not
    list it (PKG_TYPES). Ends with Special > Shut Down, because Mini
    vMac flushes a volume on eject and the read-back is half the run.
    """
    import glob
    from synth_wrapped import binhex                   # noqa: E402
    if not os.path.exists(INSTALLED):
        raise SystemExit("spacesaver: no installed image — --keep-installed")
    boot = os.path.join(WORK, "sspkgexpand.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="sspkg-")
    dest = b":" + SIT_FOLDER + b":"
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        for d in (b"OutA", b"OutB", b"OutC", b"OutD"):
            subprocess.run([b"hmkdir", dest + d], check=True,
                           capture_output=True, env=env)
        hqx = binhex(PKG_INNER, PKG_PAYLOAD, make_rsrc(PKG_FORK),
                     ftype=b"TEXT", creator=b"ttxt")
        q = os.path.join(tmp, "payload.bin")
        open(q, "wb").write(macbinary("Payload.hqx", "TEXT", "ttxt", hqx))
        subprocess.run([b"hcopy", b"-m", q.encode(), dest], check=True,
                       capture_output=True, env=env)
        for name, _prefix, line, _why in PACKAGES:
            ftype, creator = PKG_TYPES[name.split(".")[0]]
            q = os.path.join(tmp, name + ".bin")
            open(q, "wb").write(macbinary(name, ftype, creator,
                                          line.encode("mac-roman") + b"\r"))
            subprocess.run([b"hcopy", b"-m", q.encode(), dest], check=True,
                           capture_output=True, env=env)
        cpt = os.path.join(REPO, "fixtures", CPT_FIXTURE)
        q = os.path.join(tmp, "cpt.bin")
        open(q, "wb").write(macbinary("Test.cpt", "PACT", "CPCT",
                                      open(cpt, "rb").read()))
        subprocess.run([b"hcopy", b"-m", q.encode(), dest], check=True,
                       capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)
    for name, _prefix, line, why in PACKAGES:
        ftype, creator = PKG_TYPES[name.split(".")[0]]
        print("spacesaver: %-12s %s/%s  %-46s %s"
              % (name, ftype, creator, line, why))

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "pkgexpand"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        # Launching the application: `--deluxe`'s sequence, which is the
        # one that has been photographed working.
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(6):
            s.mac.command_key("w")
            time.sleep(2.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "StuffIt D")
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("opened-folder", wait=14.0)
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "StuffIt D")
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("launched", wait=40.0)
        # Photograph the menu before picking from it: the item's y is a
        # measurement off a screenshot and this is the control for it.
        s.peek(TRANSLATE_X, "translate-menu")

        # The calibration, and the reason it is here: PKG Expand's
        # Standard File dialog listed NO files in two earlier runs, and
        # an empty list is only evidence about packages if the same
        # dialog lists something for a translator whose file is there.
        # CPT Expand's filter is type 'PACT' (@0x2e1c of `CompactPro
        # Translator`), and `Test.cpt` is one.
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "Te")
        time.sleep(1.5)
        s.shot("cpt-selected", wait=0.5)
        s.menu(TRANSLATE_X, CPT_EXPAND_Y, "cpt-pick")
        s.shot("cpt-dialog", wait=6.0)
        s.mac.key("Escape")
        s.shot("cpt-cancelled", wait=4.0)

        # And the question: the same command with the package SELECTED
        # in the application's own window, which is what neither earlier
        # run did — PKG Expand's dialog offers only FOLDERS (its filter
        # tests ioFlAttrib bit 4, @0x215e), and `DITL 2051` carries a
        # button reading "Expand into selected folder", so the file it
        # works on cannot be the one that dialog asks for.
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "Bo")
        time.sleep(1.5)
        s.shot("pkg-selected", wait=0.5)
        s.menu(TRANSLATE_X, PKG_EXPAND_Y, "pkg-pick")
        s.shot("pkg-dialog", wait=6.0)
        s.mac._xdo("type", "--delay", "120", "OutA")
        time.sleep(1.5)
        s.shot("pkg-dest-typed", wait=0.5)
        s.mac.key("Return")
        s.shot("pkg-opened", wait=8.0)
        s.shot("pkg-settled", wait=20.0)
        s.mac.key("Return")
        s.shot("pkg-after", wait=6.0)
        s.mac.key("Escape")
        s.shot("pkg-escaped", wait=4.0)
        s.mac.command_key("q")
        s.shot("quit", wait=20.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    if keep:
        shutil.copyfile(out, os.path.join(WORK, "sspkgexpand-run.hfv"))
    return report_pkgexpand(out, s.shots)


def pkgexpander(keep=False):
    """The same packages, handed to StuffIt Expander instead.

    `--pkgexpand` established what PKG Expand's own dialog will take: a
    FOLDER and nothing else, while CPT Expand in the same application
    and the same boot lists files. So the command that names a package
    is not that one. StuffIt Expander is on this image too, in
    `Drag & Drop Applications` — **3.5.2**, not the 4.0.2 this docstring
    claimed until 2026-10-02; its `vers` resource says so and
    `zipmeta.py --table` reads it. It shares the engine and therefore
    the translators — its Expand dialog lists everything the engine
    claims it can open, which is the question stated as a listing.

    `Payload.hqx` goes in beside the packages as the control that must
    SUCCEED: if BinHex does not expand, the run says nothing about the
    packages.
    """
    import glob
    from synth_wrapped import binhex                   # noqa: E402
    if not os.path.exists(INSTALLED):
        raise SystemExit("spacesaver: no installed image — --keep-installed")
    boot = os.path.join(WORK, "sspkgexpander.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="sspkgx-")
    dest = b":" + SIT_FOLDER + b":Drag & Drop Applications:"
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        hqx = binhex(PKG_INNER, PKG_PAYLOAD, make_rsrc(PKG_FORK),
                     ftype=b"TEXT", creator=b"ttxt")
        q = os.path.join(tmp, "payload.bin")
        open(q, "wb").write(macbinary("Payload.hqx", "TEXT", "ttxt", hqx))
        subprocess.run([b"hcopy", b"-m", q.encode(), dest], check=True,
                       capture_output=True, env=env)
        for name, _prefix, line, _why in PACKAGES:
            ftype, creator = PKG_TYPES[name.split(".")[0]]
            q = os.path.join(tmp, name + ".bin")
            open(q, "wb").write(macbinary(name, ftype, creator,
                                          line.encode("mac-roman") + b"\r"))
            subprocess.run([b"hcopy", b"-m", q.encode(), dest], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "pkgexpander"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(6):
            s.mac.command_key("w")
            time.sleep(2.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        for pick in ("StuffIt D", "Drag"):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac._xdo("type", "--delay", "120", pick)
            time.sleep(1.5)
            s.mac.command_key("o")
            s.shot("opened-" + pick.split()[0].lower(), wait=14.0)
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "StuffIt E")
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("launched", wait=45.0)
        # Command-E is Expand..., read out of the application's MENU 129
        # (tools/vmac/expander.py). The DIALOG is the measurement: it
        # lists what the engine says it can open.
        for pick, tag in (("Payload", "control"), ("Plain", "package"),
                          ("Both", "typed")):
            s.mac.command_key("e")
            s.shot(tag + "-dialog", wait=8.0)
            s.mac._xdo("type", "--delay", "120", pick)
            time.sleep(1.5)
            s.shot(tag + "-typed", wait=0.5)
            s.mac.key("Return")
            s.shot(tag + "-started", wait=8.0)
            s.shot(tag + "-settled", wait=20.0)
            s.mac.key("Return")
            s.shot(tag + "-after", wait=6.0)
        s.mac.command_key("q")
        s.shot("quit", wait=25.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    if keep:
        shutil.copyfile(out, os.path.join(WORK, "sspkgexpander-run.hfv"))
    return report_pkgexpander(out, s.shots)


def pkgconvert(keep=False):
    """The third route: `DropConvert™`, whose whole job is translators.

    PKG Expand asks for a folder and offers no way to name one
    (`--pkgexpand`); StuffIt Expander lists a package and silently does
    nothing with it (`--pkgexpander`). `DropConvert™` (APPL/SITC) sits
    in the same folder and exists to run a chosen translator over a
    file, so it is the one place left where the AppleLink module can be
    pointed at a package this machine wrote.

    A probe as much as an attempt: it photographs every menu the
    application has before touching anything, because nothing here knows
    its interface.
    """
    import glob
    from synth_wrapped import binhex                   # noqa: E402
    if not os.path.exists(INSTALLED):
        raise SystemExit("spacesaver: no installed image — --keep-installed")
    boot = os.path.join(WORK, "sspkgconvert.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="sspkgc-")
    dest = b":" + SIT_FOLDER + b":Drag & Drop Applications:"
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        hqx = binhex(PKG_INNER, PKG_PAYLOAD, make_rsrc(PKG_FORK),
                     ftype=b"TEXT", creator=b"ttxt")
        q = os.path.join(tmp, "payload.bin")
        open(q, "wb").write(macbinary("Payload.hqx", "TEXT", "ttxt", hqx))
        subprocess.run([b"hcopy", b"-m", q.encode(), dest], check=True,
                       capture_output=True, env=env)
        for name, _prefix, line, _why in PACKAGES:
            ftype, creator = PKG_TYPES[name.split(".")[0]]
            q = os.path.join(tmp, name + ".bin")
            open(q, "wb").write(macbinary(name, ftype, creator,
                                          line.encode("mac-roman") + b"\r"))
            subprocess.run([b"hcopy", b"-m", q.encode(), dest], check=True,
                           capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    s = Session(boot, [], os.path.join(SPECIMENS, "pkgconvert"))
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(6):
            s.mac.command_key("w")
            time.sleep(2.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        for pick in ("StuffIt D", "Drag"):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac._xdo("type", "--delay", "120", pick)
            time.sleep(1.5)
            s.mac.command_key("o")
            s.shot("opened-" + pick.split()[0].lower(), wait=14.0)
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "DropCon")
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("launched", wait=45.0)
        # Its whole menu bar is File, and File is `Convert... Cmd-C` and
        # `Quit` — photographed 2026-09-01, which is the only reason this
        # run presses C. `Payload.hqx` goes first as the control that
        # must succeed.
        s.peek(40, "file-menu")
        # Convert... is a two-pane chooser: a file list on the left, an
        # "Items to Convert:" list on the right, `Add >>` as the default
        # button and `Convert` at (452, 289) — measured off
        # `07-control-dialog.png`. So the gesture is type, Return, click.
        for pick, tag in (("Payload", "control"), ("Plain", "package")):
            s.mac.command_key("c")
            s.shot(tag + "-dialog", wait=8.0)
            s.mac._xdo("type", "--delay", "120", pick)
            time.sleep(1.5)
            s.shot(tag + "-typed", wait=0.5)
            s.mac.key("Return")                  # Add >>
            s.shot(tag + "-added", wait=4.0)
            s.mac.click(*CONVERT_BUTTON)
            s.shot(tag + "-converting", wait=8.0)
            s.mac.key("Return")                  # whatever it asks next
            s.shot(tag + "-started", wait=8.0)
            s.shot(tag + "-settled", wait=20.0)
            s.mac.key("Return")
            s.shot(tag + "-after", wait=8.0)
            s.mac.key("Escape")
            time.sleep(1.5)
        s.mac.command_key("q")
        s.shot("quit", wait=25.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    print("spacesaver: reading back %s" % out)
    if keep:
        shutil.copyfile(out, os.path.join(WORK, "sspkgconvert-run.hfv"))
    return report_pkgexpander(out, s.shots)


def report_pkgexpander(img, shots):
    """Everything new in the folder the packages were put in.

    The control decides whether the run means anything: `Widget` is
    inside `Payload.hqx` and exists nowhere else, so it appears if and
    only if the engine expanded something.
    """
    from superdisk import read_forks                   # noqa: E402
    want_rsrc = make_rsrc(PKG_FORK)
    known = {"Payload.hqx", "StuffIt Expander\u2122", "DropStuff\u2122",
             "DropConvert\u2122", "DropCompress\u2122"}
    known |= set(n for n, _p, _l, _w in PACKAGES)
    control = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(img).items()):
        if "Drag & Drop Applications" not in path:
            continue
        if path[-1] in known:
            continue
        note = ""
        if path[-1] == PKG_INNER:
            # The DATA fork is the comparison. A resource fork read back
            # off a Mac is never byte-identical — the Resource Manager
            # rewrites the map's live fields when the Finder opens the
            # file to draw its icon (BLOCKERS.md 2026-08-23) — so its
            # LENGTH is what is checked.
            same = data == PKG_PAYLOAD and len(rsrc) == len(want_rsrc)
            note = ("the payload, data byte-exact, fork %d B"
                    % len(rsrc)) if same else "the payload, DIFFERS"
            control += same
        print("spacesaver: %-46s %s/%s data %d rsrc %d  %s"
              % ("/".join(path[-3:]), ftype, creator, len(data), len(rsrc),
                 note))
    print("spacesaver: control (BinHex) %s; screenshots in %s"
          % ("expanded" if control else "DID NOT EXPAND — the run says "
             "nothing about packages", shots))
    return 0 if control else 1


def report_pkgexpand(img, shots):
    """Say what is in the four destination folders, and what it is.

    The verdict is one thing: did `Widget` — the file inside
    `Payload.hqx`, which exists nowhere on the volume until something
    decodes it — appear, and does it match byte for byte. Anything else
    is reported and decides nothing.
    """
    from superdisk import read_forks                   # noqa: E402
    from synth_wrapped import binhex                   # noqa: E402
    want_rsrc = make_rsrc(PKG_FORK)
    hits = 0
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(img).items()):
        if not any(c in ("OutA", "OutB", "OutC", "OutD") for c in path):
            continue
        verdict = "unexpected"
        if path[-1] == PKG_INNER:
            same = data == PKG_PAYLOAD and rsrc == want_rsrc
            verdict = "DECODED, byte-exact" if same else "decoded, DIFFERS"
            hits += same
        print("spacesaver: %-40s %s/%s data %d rsrc %d  %s"
              % ("/".join(path), ftype, creator, len(data), len(rsrc),
                 verdict))
    print("spacesaver: %d byte-exact payload(s) in the destinations; "
          "screenshots in %s" % (hits, shots))
    return 0 if hits else 1


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
    ap.add_argument("--deluxe", action="store_true",
                    help="launch StuffIt Deluxe and photograph its menus")
    ap.add_argument("--twoboot", action="store_true",
                    help="write the preferences, reboot, then rename")
    ap.add_argument("--commit", action="store_true",
                    help="OK the Compression page, then rename")
    ap.add_argument("--parade", action="store_true",
                    help="photograph the startup icons")
    ap.add_argument("--idlenow", action="store_true",
                    help="SpaceSaver's own menu: Idle Now")
    ap.add_argument("--dragdrop", action="store_true",
                    help="drag a subject onto DropCompress")
    ap.add_argument("--drop", action="store_true",
                    help="hand a subject to DropCompress")
    ap.add_argument("--suffix", action="store_true",
                    help="drive both rename rules on the settings page")
    ap.add_argument("--enrollmagic", action="store_true",
                    help="enrol the disk, close the panel, then compress")
    ap.add_argument("--volname", action="store_true",
                    help="attach the keyword to the DISK, not a file")
    ap.add_argument("--twonames", action="store_true",
                    help="rename one file .SIT and one small, same boot")
    ap.add_argument("--enrollrename", action="store_true",
                    help="enrol the disk, then rename in the Finder")
    ap.add_argument("--uirename", action="store_true",
                    help="rename in the Finder on the fresh install")
    ap.add_argument("--pages", action="store_true",
                    help="photograph every panel page, changing nothing")
    ap.add_argument("--freshinstall", action="store_true",
                    help="install onto a stock system, photographing each panel")
    ap.add_argument("--enrollidle", action="store_true",
                    help="enrol the disk and pick Idle Now, one flushed boot")
    ap.add_argument("--idleenrolled", action="store_true",
                    help="Idle Now on a volume that is enrolled")
    ap.add_argument("--calib", action="store_true",
                    help="measure where a Mac coordinate actually lands")
    ap.add_argument("--idlepick", action="store_true",
                    help="drive SpaceSaver's own menu with explicit geometry")
    ap.add_argument("--idlemenu", action="store_true",
                    help="SpaceSaver's own menu: Idle Now, names matching")
    ap.add_argument("--ssmenu", action="store_true",
                    help="photograph the menu-bar icons and find SpaceSaver's")
    ap.add_argument("--info", action="store_true",
                    help="ask Magic Menu's SpaceSaver Info... about a file")
    ap.add_argument("--magicname", action="store_true",
                    help="a matching NAME and a menu command in one run")
    ap.add_argument("--magic", action="store_true",
                    help="Magic Menu's SpaceSaver Compress, then shut down")
    ap.add_argument("--idlespec", action="store_true",
                    help="enrol the disk, idle, shut down — one boot")
    ap.add_argument("--patch-init", action="store_true",
                    help="open INIT 0's install gate on a copy of the image, "
                         "then run --specimen against it")
    ap.add_argument("--specimen", action="store_true",
                    help="rename the subjects, then SHUT DOWN so the "
                         "volume is flushed")
    ap.add_argument("--pkg", action="store_true",
                    help="read AppleLink .pkg's recogniser out of the "
                         "translator beside SpaceSaver")
    ap.add_argument("--pkgexpand", action="store_true",
                    help="write a package here and hand it to Aladdin's own "
                         "PKG Expand, then read the volume back")
    ap.add_argument("--pkgexpander", action="store_true",
                    help="hand the same packages to StuffIt Expander, whose "
                         "Expand dialog lists what the engine can open")
    ap.add_argument("--pkgconvert", action="store_true",
                    help="the same packages through DropConvert, the droplet "
                         "that exists to run a translator")
    ap.add_argument("--layout", action="store_true",
                    help="read the container layout out of the installed "
                         "control panel and engine")
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
    elif a.deluxe:
        return deluxe(a.keep)
    elif a.twoboot:
        return twoboot(a.keep)
    elif a.commit:
        return commit(a.keep)
    elif a.parade:
        return parade(a.keep)
    elif a.idlenow:
        return idlenow(a.keep)
    elif a.dragdrop:
        return dragdrop(a.keep)
    elif a.drop:
        return drop(a.keep)
    elif a.suffix:
        return suffix(a.keep)
    elif a.enrollmagic:
        return enrollmagic(a.keep)
    elif a.volname:
        return volname(a.keep)
    elif a.twonames:
        return twonames(a.keep)
    elif a.enrollrename:
        return enrollrename(a.keep)
    elif a.uirename:
        return uirename(a.keep)
    elif a.pages:
        return pages(a.keep)
    elif a.freshinstall:
        return freshinstall(a.keep)
    elif a.enrollidle:
        return enrollidle(a.keep)
    elif a.idleenrolled:
        return idleenrolled(a.keep)
    elif a.calib:
        return calib(a.keep)
    elif a.idlepick:
        return idlepick(a.keep)
    elif a.idlemenu:
        return idlemenu(a.keep)
    elif a.ssmenu:
        return ssmenu(a.keep)
    elif a.info:
        return ssinfo(a.keep)
    elif a.magicname:
        return magicname(a.keep)
    elif a.magic:
        return magic(a.keep)
    elif a.idlespec:
        return idlespec(a.keep)
    elif a.specimen:
        return specimen(a.keep)
    elif a.patch_init:
        return patch_init(a.keep)
    elif a.pkg:
        return pkg(a.keep)
    elif a.pkgexpand:
        return pkgexpand(a.keep)
    elif a.pkgexpander:
        return pkgexpander(a.keep)
    elif a.pkgconvert:
        return pkgconvert(a.keep)
    elif a.layout:
        return layout()
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

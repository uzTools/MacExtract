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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--install", action="store_true",
                    help="walk the installer")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if a.setup:
        fetch()
    elif a.probe:
        probe(a.keep)
    elif a.install:
        install(a.keep)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

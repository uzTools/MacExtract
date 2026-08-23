#!/usr/bin/env python3
"""sitcrypt.py — have StuffIt Deluxe encrypt something, and settle a question.

StuffIt classic's password machinery is transcribed from XADMaster, and
transcription is where this project keeps finding the one thing the
reference got right for reasons it does not state. One of those is open:
**Debian's `unar` 1.10.8 and the XADMaster master this engine follows
derive the archive key differently once the password reaches eight
bytes.** Under eight they agree. At eight and above the newer code runs
its iteration a second time, and no file on this machine could say which
matches what Aladdin's software actually wrote — every encrypted `.sit`
here is generated, so it only ever agrees with whoever generated it.

StuffIt Deluxe 3.5.1 is installed under Mini vMac (spacesaver.py put it
there while chasing SpaceSaver), and it writes StuffIt classic archives
with passwords. So: have it encrypt a known file under a password of
NINE characters, read the archive back, and see which reading gets the
bytes out. That is the whole point of the harness.

    tools/vmac/sitcrypt.py --map        photograph the application's menus
    tools/vmac/sitcrypt.py              make the archive and read it back

The archive has to come off the volume as MacBinary: StuffIt classic
keeps the block that verifies a password in the archive's RESOURCE fork
('MKey' 0), and a data fork on its own cannot be decrypted by anything.

Output lands in $UNC_VMAC_HOME/specimens/sitcrypt/.
"""
import argparse
import json
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
from diskdoubler import Session, make_volume             # noqa: E402
import synth_wrapped as W                                # noqa: E402

WORK = os.path.join(R.VMAC_HOME, "spacesaver")
INSTALLED = os.path.join(WORK, "ssinstalled.hfv")
SPECIMENS = os.path.join(R.VMAC_HOME, "specimens", "sitcrypt")

# NINE characters: the whole question is what happens at eight and above.
PASSWORD = "swordfish"
SHORT_PASSWORD = "hushnow"          # seven, where the two readings agree

SUBJECT_NAME = "Subject"
SUBJECT_DATA = b"StuffIt Deluxe 3.5.1 encrypted this, under Mini vMac.\r" * 8
SUBJECT_RSRC = b"RSRC" + bytes(range(64)) * 2

# System 7's Finder, on the 512x342 screen this image boots into.
VOLUME_ICON = (470, 110)       # SITwork; the boot volume is above it
FOLDER_TITLE = (200, 33)       # the folder window this image boots with
SPECIAL_X = 225
SHUT_DOWN_Y = 123
SF_DRIVE = (377, 192)          # Standard File's Drive button


def subject_macbinary(work):
    p = os.path.join(work, "subject.bin")
    with open(p, "wb") as f:
        f.write(W.macbinary(SUBJECT_NAME, SUBJECT_DATA, SUBJECT_RSRC,
                            b"TEXT", b"ttxt"))
    return p


APP_FOLDER = "StuffIt Deluxe\u2122 Folder"


def session(tag):
    """The installed StuffIt Deluxe volume, with the subject ON it.

    ONE volume, deliberately. The first version put the subject on a
    second disk and Shut Down then stopped on *"Please insert the disk:
    SITwork"* — so the boot volume was never flushed and the archive
    came off it forty bytes short, with a resource map claiming a length
    the file did not have. That is this project's oldest emulator trap
    (tools/vmac/README.md) wearing a new hat.

    The subject goes INSIDE the application's own folder, which is the
    folder the Stuff dialog opens in, so no navigation is needed either.
    """
    if not os.path.exists(INSTALLED):
        raise SystemExit("sitcrypt: no %s — tools/vmac/spacesaver.py "
                         "--install351 makes it" % INSTALLED)
    work = tempfile.mkdtemp(prefix="sitcrypt-")
    boot = os.path.join(work, "boot-sit.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        subprocess.run(["hcopy", "-m", subject_macbinary(work),
                        (":" + APP_FOLDER + ":").encode("mac_roman")],
                       check=True, capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    s = Session(boot, [], os.path.join(SPECIMENS, tag))
    return s, work, None


def launch(s, args):
    """Launch the application out of the window the Finder already has open.

    This image boots with `StuffIt Deluxe™ Folder` open and frontmost, so
    there is no volume to open — and opening one is how the first attempt
    went wrong: the icon at the top right is the WORK volume, its window
    holds only `Subject`, and a type-select of "StuffIt D" matched that
    on its first letter and opened it in TeachText. Nine characters of
    the password then went into a text document.
    """
    s.boot()
    s.shot("desktop", wait=8.0)
    s.mac.click(*FOLDER_TITLE)          # make sure that window is active
    time.sleep(1.5)
    s.mac.key("Escape")
    time.sleep(0.6)
    s.mac._xdo("type", "--delay", "120", "StuffIt Deluxe")
    time.sleep(1.5)
    s.shot("app-selected", wait=1.0)
    s.mac.command_key("o")
    s.shot("launched", wait=args.launch_wait)


# Measured off the --map and first --make screenshots. StuffIt Deluxe's
# Stuff dialog is its OWN, not Standard File: a file list on the left, an
# "Items to Stuff" list on the right, and the control this harness exists
# for — an "Encrypt with password" checkbox — at the bottom of it. There
# is no need for Translate ▸ Change Password…, which is dimmed until an
# archive has contents anyway.
ARCHIVE_NAME = "Secret"
STUFF_DESKTOP = (263, 121)
STUFF_OPEN = (263, 146)
STUFF_ADD = (263, 178)
# Rows are SIXTEEN apart, not fifteen: at fifteen the click for row 5
# landed on row 4 and stuffed the 727 KB application instead of the
# subject, which produces a perfectly good encrypted archive of the
# wrong thing.
STUFF_ROW1 = (100, 71)
STUFF_ROW_H = 16
STUFF_ENCRYPT = (325, 269)
STUFF_GO = (452, 289)


def stuff_row(s, n):
    """Click row n (0-based) of the Stuff dialog's file list."""
    s.mac.click(STUFF_ROW1[0], STUFF_ROW1[1] + n * STUFF_ROW_H)
    time.sleep(0.8)


def phase_make(s, args):
    """New archive → Stuff the subject into it with Encrypt ticked.

    The password is asked for when the stuffing starts, and twice: once
    for it and once to verify.
    """
    s.mac.command_key("n")                       # File ▸ New…
    s.shot("new-dialog", wait=4.0)
    s.mac._xdo("type", "--delay", "150", ARCHIVE_NAME)
    s.shot("new-named", wait=1.5)
    s.mac.key("Return")
    s.shot("archive-open", wait=6.0)

    s.mac.command_key("s")                       # Archive ▸ Stuff…
    s.shot("stuff-dialog", wait=5.0)
    # The dialog opens in the application's own folder, which is where
    # the subject was put. Rows are photographed as they are clicked, so
    # a wrong --subject-row is visible rather than silent — the run that
    # took row 0 on the work volume encrypted its invisible `Desktop DB`
    # instead, correctly, which is the sort of success that reads as a
    # failure.
    stuff_row(s, args.subject_row)
    s.shot("stuff-subject", wait=1.0)
    s.mac.click(*STUFF_ADD)
    s.shot("stuff-added", wait=2.0)
    s.mac.click(*STUFF_ENCRYPT)
    s.shot("stuff-encrypt", wait=1.5)
    s.mac.click(*STUFF_GO)
    s.shot("password-dialog", wait=5.0)
    s.mac._xdo("type", "--delay", "150", args.password)
    s.shot("password-typed", wait=1.5)
    s.mac.key("Return")
    s.shot("password-verify", wait=3.0)
    s.mac._xdo("type", "--delay", "150", args.password)
    s.mac.key("Return")
    s.shot("stuffed", wait=15.0)

    s.mac.command_key("q")
    s.shot("quit", wait=8.0)
    s.mac.key("Return")                          # "save changes?", if asked
    s.shot("quit-2", wait=8.0)
    s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
    s.shot("shutting-down", wait=35.0)


def read_archive(image, outdir, name):
    """Copy the archive off as MacBinary — BOTH forks, because the
    password verifier is in the resource one.

    It is looked for ANYWHERE on the volume: File ▸ New saves into
    whatever folder Standard File was last in, which here is the
    application's own, not the root.
    """
    import checkdisk as CD
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        if CD.hfs(env, "hmount", image).returncode != 0:
            return None
        hit = [p for p in CD.walk(env) if p[-1] == name]
        dest = None
        if hit:
            src = ":" + ":".join(hit[0])
            dest = os.path.join(outdir, name + ".bin")
            got = CD.hfs(env, "hcopy", "-m", src.encode("mac_roman"),
                         dest.encode())
            if got.returncode != 0:
                dest = None
        CD.hfs(env, "humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    return dest if dest and os.path.exists(dest) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emu", default="mv-4M")
    ap.add_argument("--launch-wait", type=float, default=30.0)
    ap.add_argument("--password", default=PASSWORD)
    ap.add_argument("--map", action="store_true",
                    help="launch and photograph every menu, so the next "
                         "run knows what to click")
    ap.add_argument("--subject-row", type=int, default=5,
                    help="which row of the Stuff dialog's listing is "
                         "`Subject`. The application's folder holds Drag & "
                         "Drop Applications, Icon, Read Us First!, Scripting "
                         "Tools, StuffIt Deluxe\u2122, Subject, Tutorial "
                         "Files — so 5, and the screenshot says whether that "
                         "was right")
    ap.add_argument("--tag", default=None,
                    help="name the specimen, so runs with different "
                         "password lengths do not overwrite each other")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    os.makedirs(SPECIMENS, exist_ok=True)

    tag = args.tag or ("map" if args.map else "make")
    s, work, _img = session(tag)
    os.makedirs(os.path.join(SPECIMENS, tag), exist_ok=True)
    try:
        launch(s, args)
        if args.map:
            for x in (25, 60, 100, 145, 195, 245, 295, 345):
                s.peek(x, "menu-x%d" % x)
            return 0
        phase_make(s, args)
    finally:
        time.sleep(4)
        s.close()

    if args.map:
        return 0
    # The archive may be on either volume; look on both.
    got = None
    for nm in (ARCHIVE_NAME + ".sit", ARCHIVE_NAME):
        got = read_archive(os.path.join(s.work, "boot.hfv"),
                           os.path.join(SPECIMENS, tag), nm)
        if got:
            break
    if not got:
        print("sitcrypt: no %s on the volume — look at the screenshots "
              "in %s" % (ARCHIVE_NAME, s.shots))
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        return 1
    meta = {"made_by": "StuffIt Deluxe 3.5.1 on System 7.0.1 under Mini vMac",
            "password": args.password,
            "subject": {"name": SUBJECT_NAME,
                        "data": SUBJECT_DATA.hex(),
                        "rsrc": SUBJECT_RSRC.hex()},
            "bytes": os.path.getsize(got)}
    with open(os.path.join(SPECIMENS, tag, "made.json"), "w") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    print("sitcrypt: %d bytes -> %s" % (os.path.getsize(got), got))
    if args.keep:
        print("sitcrypt: workdir kept at %s" % work)
    else:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

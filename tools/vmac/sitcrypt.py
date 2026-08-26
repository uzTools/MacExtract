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
    tools/vmac/sitcrypt.py --btoa-send  have the btoa/atob translator encode
                                        a subject, by Apple event

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

# The subject the TRANSLATOR gets, and it is a different one: chosen for
# what it makes a btoa ENCODER do, the same way tools/run_btoa.py chooses
# its own. Every byte value, so no character of the base-85 alphabet goes
# untried; a run of zeros, which btoa writes as `z`; four spaces, which
# version 5 writes as `y`; and a length that is not a multiple of four,
# so the last group is padded.
BTOA_DATA = (bytes(range(256)) + bytes(48) + b"    " * 4 +
             b"aetran sent an Apple event and this came back.\r" * 3 +
             b"tail")
# No resource fork. A file that has one is btoa'd through MacBinary (the
# translator's STR# 130 has `.MBin` in it), and then the specimen would
# grade the MacBinary reader as much as the btoa decoder. One thing at a
# time; the fork case is worth a second run, not a confused first one.

# System 7's Finder, on the 512x342 screen this image boots into.
VOLUME_ICON = (470, 110)       # SITwork; the boot volume is above it
FOLDER_TITLE = (200, 33)       # the folder window this image boots with
SPECIAL_X = 225
SHUT_DOWN_Y = 123
SF_DRIVE = (377, 192)          # Standard File's Drive button


def subject_macbinary(work, data=SUBJECT_DATA, rsrc=SUBJECT_RSRC):
    p = os.path.join(work, "subject.bin")
    with open(p, "wb") as f:
        f.write(W.macbinary(SUBJECT_NAME, data, rsrc, b"TEXT", b"ttxt"))
    return p


APP_FOLDER = "StuffIt Deluxe\u2122 Folder"


def session(tag, subject=None, extra=()):
    """The installed StuffIt Deluxe volume, with the subject ON it.

    ONE volume, deliberately. The first version put the subject on a
    second disk and Shut Down then stopped on *"Please insert the disk:
    SITwork"* — so the boot volume was never flushed and the archive
    came off it forty bytes short, with a resource map claiming a length
    the file did not have. That is this project's oldest emulator trap
    (tools/vmac/README.md) wearing a new hat.

    The subject goes INSIDE the application's own folder, which is the
    folder the Stuff dialog opens in, so no navigation is needed either —
    and it is the folder `aetran` reads its own FSSpec out of, so
    everything `--btoa-send` touches is in one directory. `subject` is
    the subject's data fork and `extra` any further MacBinary files to
    put beside it.
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
        subj = (subject_macbinary(work) if subject is None
                else subject_macbinary(work, subject, b""))
        for mb in (subj,) + tuple(extra):
            subprocess.run(["hcopy", "-m", mb,
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


# The Translate menu, and the btoa/atob submenu inside it. Measured off
# the --map screenshots; the submenu's y is what --btoa-peek finds.
TRANSLATE_X = 295
BTOA_ITEM_Y = 86


def phase_btoa_peek(s):
    """Photograph the Translate menu with the pointer walking down it.

    The item wanted is a SUBMENU ("btoa/atob >"), so the shot has to be
    taken with the pointer resting on it — that is what makes the
    submenu draw, and its items' coordinates are what the real run
    needs.
    """
    ox, oy = s.mac.origin()
    x = s.mac._xdo
    for y in (57, 72, 86, 100, 115):
        x("mousemove", str(ox + TRANSLATE_X), str(oy + 8))
        time.sleep(0.4)
        x("mousedown", "1")
        time.sleep(1.0)
        x("mousemove", str(ox + TRANSLATE_X + 25), str(oy + y))
        time.sleep(1.5)
        s.shot("translate-y%d" % y)
        x("mouseup", "1")
        time.sleep(1.5)


# Measured off btoapeek/08: pressing Translate and dragging to y=115
# opens the btoa/atob submenu, which draws to the LEFT because the menu
# is near the right edge of a 512-pixel screen. "Binary to ASCII..." is
# its first item.
# Measured off btoapeek/08: pressing Translate and dragging to y=115
# opens the btoa/atob submenu, which draws to the LEFT because the menu
# is near the right edge of a 512-pixel screen. "Binary to ASCII..." is
# its first item — and it CANNOT BE SELECTED here. Three attempts (a
# diagonal jump, a sideways entry, and stepped motion ten pixels at a
# time, tags btoa/btoa2/btoa3): the submenu draws, the pointer sits on
# the item, the item never highlights, and the release selects nothing.
# The parent item stays highlighted throughout, so the Menu Manager
# never hands tracking to the submenu.
#
# The route was removed rather than left in, because it fails into the
# FINDER: the row click and Return meant for the save dialog renamed the
# subject to `Subject.ascii`, which then looks exactly like a specimen
# and is not one. `--btoa-drop` below is the way that does not do that.
ASCII_NAME = "Subject.ascii"


VOLUME_NAME = "System_7"
DC_OPEN = (258, 146)
DC_ADD = (258, 180)
DC_CONVERT = (458, 289)


def phase_btoa_drop(s, args):
    """Have DropConvert(tm) — Aladdin's translator droplet — encode the
    subject as btoa, so the decoder is graded by something other than
    the Unix original.

    The droplet, not the Translate menu: that menu's `btoa/atob` item is
    a SUBMENU, and under xdotool the pointer reaches its "Binary to
    ASCII..." without the item ever highlighting, so the release selects
    nothing (`dconv/btoa2`). DropConvert has one menu with `Convert...
    (Cmd-C)` in it and needs no drag at all.
    """
    x = s.mac._xdo
    s.mac.key("Escape")
    time.sleep(0.5)
    x("type", "--delay", "120", "Drag")
    time.sleep(1.2)
    s.mac.command_key("o")
    s.shot("droplets", wait=6.0)
    s.mac.key("Escape")
    time.sleep(0.5)
    x("type", "--delay", "120", "DropConvert")
    time.sleep(1.2)
    s.mac.command_key("o")
    s.shot("dc-launched", wait=25.0)

    s.mac.command_key("c")                 # Convert...
    s.shot("dc-picker", wait=6.0)
    # Standard File opens in the droplet's own folder; the subject is one
    # level up, in the application's folder. Command-Up is Standard
    # File's "enclosing folder".
    # Its picker is DropConvert's own, not Standard File: a file list on
    # the left, an "Items to Convert" list on the right, Add/Remove
    # between them — the Stuff dialog's shape. It opens in the droplet's
    # own folder, and Command-Up goes to the DESKTOP rather than one
    # level up (measured, btoadrop/05), so the way to the subject is
    # down from there.
    x("key", "--clearmodifiers", "Meta+Up")
    s.shot("dc-desktop", wait=3.0)
    for step, (typed, tag) in enumerate(((VOLUME_NAME, "volume"),
                                         (APP_FOLDER[:7], "appfolder"))):
        x("type", "--delay", "150", typed)
        time.sleep(1.2)
        s.mac.click(*DC_OPEN)
        s.shot("dc-in-%s" % tag, wait=3.0)
    x("type", "--delay", "150", SUBJECT_NAME)
    time.sleep(1.2)
    s.shot("dc-subject")
    s.mac.click(*DC_ADD)
    s.shot("dc-added", wait=2.0)
    s.mac.click(*DC_CONVERT)
    s.shot("dc-converting", wait=8.0)
    s.shot("dc-settled", wait=12.0)
    s.mac.command_key("q")
    s.shot("dc-quit", wait=8.0)
    s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
    s.shot("shutting-down", wait=35.0)


# ------------------------------------------------------------------
# The translator, driven by Apple event — `--btoa-send`
# ------------------------------------------------------------------

AETRAN_SRC = os.path.join(REPO, "tools", "aetran")
AETRAN_BUILD = os.path.join(REPO, "build", "aetran")
# The translator MacBinary-wraps the file and btoa's THAT, so its output
# is `Subject.MBin.ascii` and not the name anybody would guess. It is
# found by what the translator STAMPS it — TEXT/'asci' — rather than by
# name: a name is what the last attempt at this got wrong, when the
# Finder renamed the subject to `Subject.ascii` and the run reported a
# specimen that was the plain subject.
ASCII_TYPE = "TEXT"
ASCII_CREATOR = "asci"
AE_LOG = "AEResult"


def build_aetran():
    """Cross-compile the sender. Toolchain located the way
    tools/build_mac.sh locates it, and this is the only harness that
    builds a Macintosh binary of its own."""
    mb = os.path.join(AETRAN_BUILD, "aetran.bin")
    chain = os.environ.get("RETRO68") or "/opt/Retro68-build/toolchain"
    cmakefile = os.path.join(chain, "m68k-apple-macos", "cmake",
                             "retro68.toolchain.cmake")
    if not os.path.exists(cmakefile):
        raise SystemExit("sitcrypt: no Retro68 toolchain (set RETRO68); "
                         "tools/build_mac.sh says where to get one")
    subprocess.run(["cmake", "-B", AETRAN_BUILD, "-S", AETRAN_SRC,
                    "-DCMAKE_TOOLCHAIN_FILE=" + cmakefile,
                    "-DCMAKE_BUILD_TYPE=Release"],
                   check=True, capture_output=True)
    subprocess.run(["cmake", "--build", AETRAN_BUILD], check=True,
                   capture_output=True)
    if not os.path.exists(mb):
        raise SystemExit("sitcrypt: aetran did not build")
    return mb


def phase_btoa_send(s, args):
    """Launch `aetran`, which sends StuffIt Deluxe the translate event.

    Nothing here clicks a menu. The application is launched by the sender
    itself, so this drives exactly one thing — the Finder, opening the
    sender out of the window the image boots with — and every later step
    happens inside the Macintosh where no coordinate can miss it.

    The screenshots are for a run that stops; the run's RESULT is two
    files on the volume, `Subject.ascii` and the sender's own `AEResult`.
    """
    s.mac.key("Escape")
    time.sleep(0.6)
    s.mac._xdo("type", "--delay", "120", "aetran")
    time.sleep(1.5)
    s.shot("aetran-selected", wait=1.0)
    s.mac.command_key("o")
    s.shot("aetran-launched", wait=20.0)
    # StuffIt Deluxe is 727 KB and comes up from a floppy-speed emulated
    # disk; the sender waits up to twenty seconds for its process and
    # five minutes for the reply, so this waits longer than both.
    # A Return between every shot, because the shapes that name no
    # destination leave the translator's own "Save ASCII file as:" box on
    # the screen — and a modal dialog in the other application blocks
    # every later attempt until it is answered. Its default name is the
    # one the sender asked for anyway. In the Finder the same keystroke
    # opens a rename box on whatever is selected, so Escape closes that
    # again before the next one.
    for i in range(args.send_shots):
        s.shot("running-%d" % i, wait=args.send_wait)
        s.mac.key("Return")
        time.sleep(1.0)
        s.mac.key("Escape")
    s.shot("settling", wait=args.send_wait)
    s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
    s.shot("shutting-down", wait=45.0)


def find_encoded(image):
    """The translator's output, found by TYPE/CREATOR rather than by
    name, and returned as (name, data fork bytes)."""
    from superdisk import read_forks                     # noqa: E402
    hits = [(path[-1], data)
            for path, (ftype, creator, data, _r) in read_forks(image).items()
            if ftype == ASCII_TYPE and creator == ASCII_CREATOR]
    if len(hits) != 1:
        return None, None
    return hits[0]


def macbinary_forks(path):
    """(data, rsrc) out of a MacBinary file written by hcopy -m."""
    blob = open(path, "rb").read()
    import struct as _s
    dlen, rlen = _s.unpack_from(">I", blob, 83)[0], _s.unpack_from(">I", blob,
                                                                  87)[0]
    data = blob[128:128 + dlen]
    off = 128 + dlen + (-dlen % 128)
    return data, blob[off:off + rlen]


def decode_layer(cli, path, outdir, extra=()):
    """One `macextract x` of `path` into a fresh directory. Returns
    (name, bytes) for the single file it yielded, or (None, None)."""
    got = tempfile.mkdtemp(prefix="btoa-out-", dir=outdir)
    r = subprocess.run([cli, "x", "-o", got, path] + list(extra),
                       capture_output=True)
    names = sorted(os.listdir(got))
    if r.returncode != 0 or len(names) != 1:
        print("sitcrypt: %s: our decoder wrote %r (exit %d)\n%s"
              % (os.path.basename(path), names, r.returncode,
                 r.stderr.decode("utf-8", "replace").strip()))
        return None, None
    return names[0], open(os.path.join(got, names[0]), "rb").read()


def grade_btoa(outdir, ascii_path):
    """Decode the Macintosh-written stream with our own CLI, and say
    whether the bytes that come back are the bytes that went in.

    TWO layers, because the translator wraps before it encodes: the btoa
    stream holds a MacBinary file and the MacBinary file holds the
    subject. `macextract` takes them one at a time here rather than being
    trusted to chain them, so the grade says which layer was read.

    Then encode the same PAYLOAD with btoa 5.2.1 and diff the streams.
    That half is not pass/fail — the whole point of the specimen is that
    it came from a different encoder, so a difference is a measurement.
    """
    import run_btoa as RB                                # noqa: E402
    cli = None
    for build in ("rel", "san", ""):
        p = os.path.join(REPO, "build", build, "macextract")
        if os.path.exists(p):
            cli = p
            break
    if cli is None:
        print("sitcrypt: no CLI to grade with (make)")
        return False

    work = tempfile.mkdtemp(prefix="btoa-grade-")
    try:
        name, payload = decode_layer(cli, ascii_path, work)
        if payload is None:
            return False
        print("sitcrypt: btoa layer -> %r, %d bytes" % (name, len(payload)))
        inner = os.path.join(outdir, "payload.bin")
        open(inner, "wb").write(payload)
        name2, back = decode_layer(cli, inner, work)
        if back is None:
            return False
        ok = back == BTOA_DATA
        print("sitcrypt: MacBinary layer -> %r, %d bytes, %s"
              % (name2, len(back),
                 "BYTE-EXACT" if ok else "DIFFERS from the subject"))
        if not ok:
            open(os.path.join(outdir, "decoded.bin"), "wb").write(back)

        # The reference encodes the same payload, in both framings, and
        # the comparison is with the stream the Macintosh wrote.
        if RB.build():
            mac = open(ascii_path, "rb").read()
            for label, flags in (("v5", []), ("v4", ["-o"])):
                ref = os.path.join(outdir, "reference-%s.ascii" % label)
                with open(ref, "wb") as f:
                    subprocess.run([RB.BIN] + flags + [inner], stdout=f,
                                   stderr=subprocess.DEVNULL)
                got = open(ref, "rb").read()
                if got == mac:
                    print("sitcrypt: vs btoa 5.2.1 %s: IDENTICAL" % label)
                    continue
                a, b = got.split(b"\n"), mac.split(b"\n")
                diff = [i for i in range(max(len(a), len(b)))
                        if a[i:i + 1] != b[i:i + 1]]
                print("sitcrypt: vs btoa 5.2.1 %s: %d of %d lines differ%s"
                      % (label, len(diff), max(len(a), len(b)),
                         "" if len(diff) != 1 else
                         "\n  reference: %s\n  Macintosh: %s"
                         % (a[diff[0]].decode("ascii", "replace"),
                            b[diff[0]].decode("ascii", "replace"))))
        return ok
    finally:
        shutil.rmtree(work, ignore_errors=True)


def list_folder(image):
    """What is in the application's folder now — the only way to see what
    DropConvert decided to call its output, and in what format."""
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        if subprocess.run(["hmount", image], capture_output=True,
                          env=env).returncode != 0:
            return ""
        out = subprocess.run(["hls", "-l",
                              (":" + APP_FOLDER + ":").encode("mac_roman")],
                             capture_output=True, env=env).stdout
        subprocess.run(["humount"], capture_output=True, env=env)
        return out.decode("mac_roman", "replace")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


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
    ap.add_argument("--btoa-drop", action="store_true",
                    help="encode the subject with the DropConvert droplet")
    ap.add_argument("--droplet-peek", action="store_true",
                    help="photograph the Drag_Drop Applications folder")
    ap.add_argument("--btoa-peek", action="store_true",
                    help="photograph the Translate menu item by item, to "
                         "find where the btoa/atob submenu is")
    ap.add_argument("--btoa-send", action="store_true",
                    help="have the btoa/atob translator encode the subject "
                         "by Apple event, with no menu at all")
    ap.add_argument("--send-shots", type=int, default=4,
                    help="how many screenshots to take while the sender "
                         "waits for its reply")
    ap.add_argument("--send-wait", type=float, default=20.0)
    ap.add_argument("--tag", default=None,
                    help="name the specimen, so runs with different "
                         "password lengths do not overwrite each other")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    os.makedirs(SPECIMENS, exist_ok=True)

    tag = args.tag or ("map" if args.map
                       else "btoapeek" if args.btoa_peek
                       else "btoasend" if args.btoa_send
                       else "droplets" if args.droplet_peek
                       else "btoadrop" if args.btoa_drop
                       else "make")
    if args.btoa_send:
        s, work, _img = session(tag, subject=BTOA_DATA,
                                extra=(build_aetran(),))
    else:
        s, work, _img = session(tag)
    outdir = os.path.join(SPECIMENS, tag)
    os.makedirs(outdir, exist_ok=True)
    try:
        # The sender is an application like the droplet is, so this one
        # also stays in the Finder rather than opening StuffIt Deluxe
        # first — `aetran` launches it itself.
        if args.btoa_send:
            s.boot()
            s.shot("desktop", wait=8.0)
            s.mac.click(*FOLDER_TITLE)
            time.sleep(1.5)
            phase_btoa_send(s, args)
            s.close()
            print(list_folder(os.path.join(s.work, "boot.hfv")))
            log = read_archive(os.path.join(s.work, "boot.hfv"), outdir,
                               AE_LOG)
            if log:
                print("---- %s ----\n%s"
                      % (AE_LOG, macbinary_forks(log)[0]
                         .decode("mac_roman", "replace").replace("\r", "\n")))
            else:
                print("sitcrypt: the sender wrote no %s — look at %s"
                      % (AE_LOG, s.shots))
            name, data = find_encoded(os.path.join(s.work, "boot.hfv"))
            if data is None:
                print("sitcrypt: no %s/%s file on the volume — look at the "
                      "screenshots in %s"
                      % (ASCII_TYPE, ASCII_CREATOR, s.shots))
                return 1
            path = os.path.join(outdir, name)
            open(path, "wb").write(data)
            print("sitcrypt: %d bytes -> %s" % (os.path.getsize(path), path))
            with open(os.path.join(outdir, "made.json"), "w") as f:
                json.dump({"made_by": "the btoa/atob Translator, driven by "
                                      "Apple event under StuffIt Deluxe "
                                      "3.5.1 on System 7.0.1 under Mini vMac",
                           "what": "btoa (xbtoa) stream, of a MacBinary "
                                   "wrapper the translator added itself",
                           "name": name,
                           "subject": BTOA_DATA.hex(),
                           "bytes": os.path.getsize(path)},
                          f, indent=1, sort_keys=True)
            return 0 if grade_btoa(outdir, path) else 1
        # This one stays in the FINDER — the droplet is an application of
        # its own and StuffIt Deluxe must not be running in front of it.
        if args.droplet_peek or args.btoa_drop:
            s.boot()
            s.shot("desktop", wait=8.0)
            s.mac.click(*FOLDER_TITLE)
            time.sleep(1.5)
            if args.btoa_drop:
                phase_btoa_drop(s, args)
                s.close()
                print(list_folder(os.path.join(s.work, "boot.hfv")))
                return 0
            phase_droplet_peek(s)
            return 0
        launch(s, args)
        if args.map:
            for x in (25, 60, 100, 145, 195, 245, 295, 345):
                s.peek(x, "menu-x%d" % x)
            return 0
        if args.btoa_peek:
            phase_btoa_peek(s)
            return 0
        phase_make(s, args)
    finally:
        time.sleep(4)
        s.close()

    if args.map:
        return 0
    # The archive may be on either volume; look on both.
    got = None
    names = [ARCHIVE_NAME + ".sit", ARCHIVE_NAME]
    for nm in names:
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
            "what": "encrypted .sit",
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

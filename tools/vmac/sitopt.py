#!/usr/bin/env python3
"""sitopt.py — how far a machine with no licence gets towards an optimized archive.

StuffIt Deluxe 2.0 could hand a fork to an external module before
compressing it — an Optimizer, a Compressor or an Encryptor, each a file
of type 'SITe' in a folder of the System Folder. Where an archive RECORDS
which module it used is read out of the application itself (FORMATS.md,
*Where an archive names the module*), and this engine refuses such an
entry per entry. What has never existed here is one of those archives, so
the refusal is graded against entries built to the reading.

**This went after one and did not get it.** What it establishes instead
is exactly where the wall is, so that MANUAL_TESTS.md §8 can ask somebody
with a licensed copy for two minutes rather than for a guess:

- 2.0.1 **installs by copying**: the download is a StuffIt archive of two
  DiskCopy images, disk 1 holds an installer whose DATA fork is another
  StuffIt archive, and `macextract` unwraps the lot. Where each piece
  goes is Aladdin's own `UnInstall Dlx Files Script`, on disk 2, which
  erases `{system}Optimizers:Text 1` and the rest by name. The installer
  is never run.
- 2.0.1 **launches, and then asks for a serial number and checks it.**
  It also refuses OK until a signature is drawn in a box. None of the
  codes published on the page the software comes from are accepted, and
  nothing here goes looking for one or reads the check out of the binary
  (DECISIONS.md 2026-08-22, the line `spacesaver.py` drew for 3.5.1).
- **Magic Menu runs without one**, and is the half of StuffIt that has
  ever worked on this machine: ⌘S stuffs the selection with no dialog.
  Its `StuffIt Options ▸` submenu offers compression method and
  Leave/Delete Originals — **no Optimizer**, which is the second wall.

    tools/vmac/sitopt.py --setup        fetch the two 2.0.1 floppies
    tools/vmac/sitopt.py --install      build the System 6 boot volume
    tools/vmac/sitopt.py --personalize  meet the licence dialog
    tools/vmac/sitopt.py --magic        the Finder with Magic Menu loaded
    tools/vmac/sitopt.py --stuff        stuff a file, read the archive back
    tools/vmac/sitopt.py --options      the `StuffIt Options ▸` submenu
    tools/vmac/sitopt.py --install351   the 3.5.1 image, 2.0's modules added
    tools/vmac/sitopt.py --map351       launch 3.5.1 and peek its menus
    tools/vmac/sitopt.py --show <path>  print any StuffIt archive's headers

`--show` is the one mode that needs no emulator and is the reason this
file will still be useful when somebody answers §8: it prints, per entry,
the method bytes and the six module bytes, and diffs two archives'
headers when it is given both.

What this CANNOT see:

- **whether byte 106 really holds the module id.** That needs an archive
  an Optimizer wrote.
- **whether 3.5.1 would use a 2.0 module.** `--install351` puts `Text 1`
  in both of the places 3.5 might look; the application that would list
  it does not launch here (BLOCKERS.md, withdrawn claims).
- **the 512 KB machine.** It boots `mv-4M` throughout: 2.0.1's resource
  fork alone is 423 KB.
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
import run as R                                          # noqa: E402
from arcmac import macbinary, hfs                        # noqa: E402
from diskdoubler import Session                          # noqa: E402

CACHE = os.path.join(os.path.expanduser("~"), ".cache", "macextract", "sit2")
MAIN_SIT = os.path.join(CACHE, "stuffit-deluxe-v2.sit")
OPT_SIT = os.path.join(CACHE, "deluxe-2-optional.sit")
MAIN_MD5 = "45b940a528fe2bc18560bf0b2ae60f7a"
PAGE = "https://macintoshgarden.org/apps/stuffit-deluxe"
MAIN_URL = "https://old.mac.gdn/apps/stuffit-deluxe-v2.sit"
OPT_URL = "https://old.mac.gdn/apps/deluxe-2-optional.sit"

WORK = os.path.join(R.VMAC_HOME, "sitopt")
BOOT = os.path.join(WORK, "sitopt.hfv")
SPECIMENS = os.path.join(R.VMAC_HOME, "specimens", "sitopt")
VOL = "Macintosh"                       # System6.hfv's volume name

CLI = os.path.join(REPO, "build", "macextract")

# What goes where. The destinations are Aladdin's own: `UnInstall Dlx
# Files Script`, on disk 2 of the 2.0.1 box, erases
# `{system}Optimizers:Text 1` and `{system}Encryptors:PassLock`, and the
# application's STR# 267 ("9 Magic Fldrs") names the eight folders it
# looks in. The types are the payload's, as `macextract l` prints them.
INSTALL = [
    ((), "StuffIt Deluxe™", "APPL", "SIT!"),
    (("System Folder", "Optimizers"), "Optimizers/Text 1", "SITe", "SIT!"),
    (("System Folder", "Optimizers"), "Optimizers/MacPaint 1", "SITe", "SIT!"),
    (("System Folder", "Encryptors"), "Encryptors/PassLock", "SITe", "SIT!"),
    # The Engine goes loose in the System Folder too: `{system}
    # Extensions:` is the System 7 place the uninstall script names, and
    # System 6 has no such folder, so it is put in both.
    (("System Folder", "Extensions"), "Extensions/StuffIt Engine™",
     "SITE", "SITE"),
    (("System Folder",), "Extensions/StuffIt Engine™", "SITE", "SITE"),
    # Without this the application stops at a Standard File dialog before
    # it draws a window — *"Couldn't open 'StuffIt Deluxe Preferences' in
    # folder 'Preferences' on 'Macintosh'"* — and every menu photographed
    # after that belongs to a modal dialog (the first --map run).
    (("System Folder", "Preferences"),
     "Preferences/StuffIt Deluxe Preferences", "Pref", "SIT!"),
    # Magic Menu and its two extensions, LOOSE in the System Folder,
    # which is where System 6 loads an INIT or a cdev from — it has no
    # Extensions or Control Panels folder. This is the half of 2.0 that
    # stuffs from the Finder, and the half that might not ask for a
    # serial number: the application does and checks it (below).
    (("System Folder",), "Magic Menu™", "cdev", "MAGM"),
    (("System Folder",), "StuffIt Deluxe Extension", "FEXT", "MAGM"),
    (("System Folder",), "Mail Extension", "FEXT", "MAGM"),
    # …and in `Extensions:` as well, which is where the uninstall script
    # says they go. Loose in the System Folder, Magic Menu loads and its
    # menu holds "Help…" and "About Magic Menu™…" and nothing else — the
    # compression items come from this extension and it had not been
    # found (`specimens/sitopt/magic/09-menu-x230.png`).
    (("System Folder", "Extensions"), "StuffIt Deluxe Extension",
     "FEXT", "MAGM"),
    (("System Folder", "Extensions"), "Mail Extension", "FEXT", "MAGM"),
]

# The subject. Every one of Text 1's three actions has something to do to
# it: leading spaces to convert to tabs, trailing spaces to strip, and a
# resource fork to delete. The bytes are CR-terminated because a
# Macintosh text file is.
SUBJECT_NAME = "Subject"
SUBJECT_DATA = (b"    indented four spaces   \r"
                b"        indented eight   \r"
                b"no indent, trailing tab\t\r"
                b"    mixed \t indent and trailing spaces    \r") * 6

SCRIPT_NAME = "Optimize Script"
# StuffIt Deluxe 2.0's script language. Vocabulary: STR# 257 in the
# application ("Script Commands/Misc"); the shape of a line is the four
# scripts in the payload's `Sample Scripts` folder. `{Startup}` is the
# boot volume, which is the only volume this run has — one volume,
# because Shut Down ejects a second one and the Finder then asks for it
# back before the boot volume has flushed (tools/vmac/README.md).
SCRIPT = "\r".join([
    "; written by tools/vmac/sitopt.py",
    'Write Status To "{Startup}Status.out"',
    "Continue On Error",
    "; the CONTROL first: the same subject with no Optimizer enabled",
    'New Archive "{Startup}Plain.sit"',
    'Stuff "{Startup}Subject" with fast',
    "Close",
    "; and now with the text Optimizer on",
    'Enable Optimizer "Text 1"',
    'New Archive "{Startup}Optimized.sit"',
    'Stuff "{Startup}Subject" with fast',
    "Close",
    "; the same again at Better, in case the method matters",
    'New Archive "{Startup}OptBetter.sit"',
    'Stuff "{Startup}Subject" with better',
    "Close",
    "Quit",
    "",
])


def make_rsrc():
    """A minimal resource fork, so `Delete resources` has work to do.

    A real one: a resource map with a single 'STR ' resource, laid out
    per Inside Macintosh I-121 as tools/vmac/spacesaver.py's reader
    parses it. Text 1 deletes resources from a text file, and a fork it
    cannot parse is not a test of that.
    """
    body = b"\x1cStuffIt Deluxe 2.0.1 wrote it"
    data = len(body).to_bytes(4, "big") + body
    # type list: one type, one reference
    reflist = (0).to_bytes(2, "big") + (0xFFFF).to_bytes(2, "big") + \
        b"\x00" + (0).to_bytes(3, "big") + (0).to_bytes(4, "big")
    typelist = (0).to_bytes(2, "big") + b"STR " + (0).to_bytes(2, "big") + \
        (2 + 8).to_bytes(2, "big")
    themap = bytes(16) + bytes(4) + bytes(2) + \
        (28).to_bytes(2, "big") + (28 + len(typelist) +
                                   len(reflist)).to_bytes(2, "big") + \
        typelist + reflist
    dataoff = 256
    head = (dataoff).to_bytes(4, "big") + \
        (dataoff + len(data)).to_bytes(4, "big") + \
        len(data).to_bytes(4, "big") + len(themap).to_bytes(4, "big")
    return head + bytes(dataoff - len(head)) + data + themap


def fetch():
    """Both floppies, in the foreground: a backgrounded download on this
    machine stalls in poll() with no error (tools/vmac/README.md)."""
    os.makedirs(CACHE, exist_ok=True)
    for url, dest in ((MAIN_URL, MAIN_SIT), (OPT_URL, OPT_SIT)):
        if os.path.exists(dest):
            print("sitopt: have %s" % os.path.basename(dest))
            continue
        subprocess.run(["curl", "-fsSL", "-e", PAGE, "-o", dest, url],
                       check=True)
        print("sitopt: fetched %s (%d B)" % (os.path.basename(dest),
                                             os.path.getsize(dest)))
    got = hashlib.md5(open(MAIN_SIT, "rb").read()).hexdigest()
    if got != MAIN_MD5:
        raise SystemExit("sitopt: %s is md5 %s, expected %s — a different "
                         "build of 2.0.1 is a different reading"
                         % (MAIN_SIT, got, MAIN_MD5))
    print("sitopt: md5 %s as recorded" % got)


def payload(work):
    """The installer's payload, extracted by this project's own engine.

    Two nested envelopes and an archive: the download is a StuffIt
    archive of two DiskCopy images; disk 1 holds one file, an installer
    whose DATA fork is itself a StuffIt archive. `macextract` unwraps
    the lot, which is also the only claim here that needs no new code.
    """
    if not os.path.exists(MAIN_SIT):
        raise SystemExit("sitopt: no %s — --setup fetches it" % MAIN_SIT)
    if not os.path.exists(CLI):
        raise SystemExit("sitopt: no %s — `make` builds it" % CLI)
    outer = os.path.join(work, "floppies")
    subprocess.run([CLI, "x", "-o", outer, MAIN_SIT], check=True,
                   capture_output=True)
    d1 = None
    for root, _dirs, files in os.walk(outer):
        for f in files:
            if f.endswith("Disk 1.image"):
                d1 = os.path.join(root, f)
    if not d1:
        raise SystemExit("sitopt: no 'Disk 1.image' in %s" % MAIN_SIT)
    # A DiskCopy 4.2 image is an 84-byte header and then the volume.
    raw = os.path.join(work, "disk1.dsk")
    blob = open(d1, "rb").read()
    open(raw, "wb").write(blob[84:])
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    inst = os.path.join(work, "installer.bin")
    try:
        hfs(env, "hmount", raw)
        name = "StuffIt Deluxe™ Installer".encode("mac_roman")
        got = hfs(env, "hcopy", "-m", name, inst.encode())
        if got.returncode != 0:
            raise SystemExit("sitopt: cannot copy the installer off disk 1")
        hfs(env, "humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    tree = os.path.join(work, "payload")
    subprocess.run([CLI, "x", "-o", tree, inst], check=True,
                   capture_output=True)
    return tree


def install(args):
    """A System 6 boot volume with 2.0.1's pieces where they belong."""
    os.makedirs(WORK, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sitopt-")
    tree = payload(work)
    src = os.path.join(R.VMAC_HOME, "System6.hfv")
    if not os.path.exists(src):
        raise SystemExit("sitopt: no %s" % src)
    shutil.copyfile(src, BOOT)

    items = []                                  # (folder tuple, macbin path)
    for i, (folder, rel, ftype, creator) in enumerate(INSTALL):
        data = os.path.join(tree, rel)
        rsrc = data + ".rsrc"
        if not os.path.exists(data):
            raise SystemExit("sitopt: the payload has no %s" % rel)
        name = rel.split("/")[-1]
        mb = os.path.join(work, "i%d.bin" % i)
        # The Preferences file is the one with no resource fork at all;
        # everything else here is a resource fork with an empty data one.
        open(mb, "wb").write(macbinary(
            name, ftype, creator, open(data, "rb").read(),
            open(rsrc, "rb").read() if os.path.exists(rsrc) else b""))
        items.append((folder, mb))

    subj = os.path.join(work, "subject.bin")
    open(subj, "wb").write(macbinary(SUBJECT_NAME, "TEXT", "ttxt",
                                     SUBJECT_DATA, make_rsrc()))
    items.append(((), subj))
    # Aladdin's own text file, with Aladdin's own resource fork, beside
    # the synthetic one: a second subject this harness did not shape.
    doc = os.path.join(tree, "Tutorial Files", "A Document")
    if os.path.exists(doc):
        mb = os.path.join(work, "doc.bin")
        open(mb, "wb").write(macbinary("A Document", "TEXT", "MPS ",
                                       open(doc, "rb").read(),
                                       open(doc + ".rsrc", "rb").read()))
        items.append(((), mb))
    scr = os.path.join(work, "script.bin")
    # TEXT/SIT!, which is what the payload's own Sample Scripts are: the
    # Standard File pick in Execute Script… filters on it.
    open(scr, "wb").write(macbinary(SCRIPT_NAME, "TEXT", "SIT!",
                                    SCRIPT.encode("mac_roman")))
    items.append(((), scr))

    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        hfs(env, "hmount", BOOT)
        made = set()
        for folder, mb in items:
            for i in range(len(folder)):
                d = folder[:i + 1]
                if d not in made:
                    # A failure here is "it is already there", which is
                    # true of `System Folder` on every boot image. The
                    # hcopy below is what has to succeed.
                    subprocess.run(
                        ["hmkdir",
                         (VOL + ":" + ":".join(d)).encode("mac_roman")],
                        capture_output=True, env=env)
                    made.add(d)
            dest = VOL + ":" + (":".join(folder) + ":" if folder else "")
            got = hfs(env, "hcopy", "-m", os.path.abspath(mb),
                      dest.encode("mac_roman"))
            if got.returncode != 0:
                raise SystemExit("sitopt: hcopy to %s failed: %s"
                                 % (dest, got.stderr))
        hfs(env, "humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
    print("sitopt: boot volume at %s (%d B)" % (BOOT, os.path.getsize(BOOT)))
    return BOOT


# ------------------------------------------------------------------
# Driving it
# ------------------------------------------------------------------

# System 6's Finder, on the 512x342 screen: arcmac.py's coordinates, and
# 123 is Shut Down on THIS system — it is Restart on the System 7 image
# spacesaver.py builds, which is the difference that cost a run there.
SPECIAL_X = 175
SHUT_DOWN_Y = 123
BOOT_ICON = (470, 60)


# The application's icon in the volume window, and the icon is CLICKED
# rather than type-selected: the first run typed "StuffIt Deluxe" into an
# active window and selected nothing at all, so ⌘O opened nothing and
# every menu photographed after it was the Finder's
# (`map/04-launched.png`). One click, one screenshot, then ⌘O — a wrong
# icon is then visible rather than silent.
APP_ICON = (365, 105)


def launch(s, args):
    """Open the boot volume and launch the application."""
    s.boot()
    s.shot("desktop", wait=6.0)
    s.mac.click(*BOOT_ICON, double=True)
    s.shot("volume", wait=10.0)
    s.mac.click(*APP_ICON)
    s.shot("app-selected", wait=2.0)
    s.mac.command_key("o")
    s.shot("launched", wait=args.launch_wait)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emu", default="mv-4M")
    ap.add_argument("--launch-wait", type=float, default=40.0)
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--personalize", action="store_true")
    ap.add_argument("--no-codes", action="store_true",
                    help="one OK with the serial field empty")
    ap.add_argument("--install351", action="store_true")
    ap.add_argument("--plain351", action="store_true",
                    help="the control: 3.5.1 with no module added")
    ap.add_argument("--map351", action="store_true")
    ap.add_argument("--magic", action="store_true")
    ap.add_argument("--stuff", action="store_true")
    ap.add_argument("--options", action="store_true")
    ap.add_argument("--map", action="store_true")
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--show", nargs="?", const=True,
                    help="an archive, or a directory of them")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--tag", default="make")
    ap.add_argument("--script-wait", type=float, default=90.0)
    ap.add_argument("--no-expert", action="store_true",
                    help="this build already has Expert menus")
    args = ap.parse_args()

    if args.setup:
        fetch()
        return 0
    if args.install:
        install(args)
        return 0
    if args.personalize:
        return phase_personalize(args)
    if args.install351:
        install351(args)
        return 0
    if args.map351:
        return phase_map351(args)
    if args.magic:
        return phase_magic(args)
    if args.stuff:
        return phase_stuff(args)
    if args.options:
        return phase_options(args)
    if args.map:
        return phase_map(args)
    if args.make:
        return phase_make(args)
    if args.show:
        return show_path(args.show if args.show is not True
                         else os.path.join(SPECIMENS, args.tag))
    ap.print_help()
    return 2


# The personalization dialog 2.0.1 shows the first time it is launched:
# Name, Organization, Serial No., a signature box, Cancel and OK.
# Measured off map/05-menubar.png. **The serial is left empty on
# purpose** — this project fills a form with its own details and does
# not go looking for somebody's registration number, which is the line
# `spacesaver.py` drew for 3.5.1 and 4.0 (DECISIONS.md 2026-08-22). If
# 2.0.1 refuses an empty one, that is the answer and the run stops.
REG_NAME = (300, 96)
REG_ORG = (300, 120)
REG_SERIAL = (300, 150)
REG_OK = (310, 281)
ALERT_OK = (256, 166)        # the "invalid"/"must sign" alert's OK

# What 2.0.1 asks for, established one refusal at a time: with the
# serial empty and no mark in the box it says *"You must type in and
# sign your name"*, and with the box marked it says *"The serial number
# you have entered is invalid"*. So the signature is required and the
# SERIAL IS CHECKED — 2.0.1 joins 3.5.1 and 4.0 at the same wall.
#
# The codes below are the ones already published on the Macintosh
# Garden page this software is downloaded from, as `spacesaver.py`
# records them: "S" + five digits is 3.0.7's scheme and the DLX forms
# are 5.x's. Nothing here goes looking for a registration number, and
# nothing here reads the check out of the application — that is the
# line this project drew for 3.5.1 (DECISIONS.md 2026-08-22).
PUBLISHED_CODES = ["S12345", "DLXC-963-029519", "DLXC-907-029528",
                   "DLXF-0859-006229", "DLXG-1112-268709",
                   "DLXF-0835-001225"]


def sign(s):
    """Draw a mark in the signature box: the dialog will not take OK
    without one. A dragged stroke, because the box is a little QuickDraw
    canvas with a pencil — clicks alone leave it empty."""
    ox, oy = s.mac.origin()
    x = s.mac._xdo
    path = [(180, 205), (205, 180), (230, 210), (255, 182), (285, 208),
            (320, 190)]
    x("mousemove", str(ox + path[0][0]), str(oy + path[0][1]))
    time.sleep(0.4)
    x("mousedown", "1")
    for (qx, qy), (px, py) in zip(path, path[1:]):
        for i in range(1, 6):            # a few points per leg, so the
            x("mousemove", str(ox + qx + (px - qx) * i // 5),
              str(oy + qy + (py - qy) * i // 5))
            time.sleep(0.08)
    time.sleep(0.3)
    x("mouseup", "1")
    time.sleep(0.8)


def phase_personalize(args):
    """Take the personalization once, and keep the image that has it.

    The application writes what is typed back into its own resource fork
    — the same shape as DiskDoubler's (tools/vmac/diskdoubler.py) — so
    this has to happen on an image that is then KEPT, or every later run
    meets the dialog again. Mini vMac boots a copy in the session's temp
    directory, and that copy is what is lifted back.
    """
    s = Session(BOOT, [], os.path.join(SPECIMENS, "personalize"),
                mem=args.emu)
    try:
        launch(s, args)
        s.mac.click(*REG_NAME)
        time.sleep(0.8)
        s.mac._xdo("type", "--delay", "120", "MacExtract")
        s.mac.click(*REG_ORG)
        time.sleep(0.8)
        s.mac._xdo("type", "--delay", "120", "github.com/unclassic")
        s.shot("filled", wait=2.0)
        # "You must type in and sign your name." — the name and the
        # organization are not enough, and the SERIAL is not what it
        # asks for: with the serial field empty it complains about the
        # signature box and nothing else, which is how this run
        # established that 2.0.1 does not check a registration number at
        # all (`personalize/07-settled.png` of the run before this one).
        sign(s)
        s.shot("signed", wait=2.0)
        # Every code in one boot: the alert has an OK button, so the
        # field can be cleared and retyped without booting again —
        # `spacesaver.py --install40`'s lesson, and ⌘A does not select a
        # dialog field's text, so it is emptied with BackSpace.
        for code in ([""] if args.no_codes else PUBLISHED_CODES):
            if code:
                s.mac.click(*REG_SERIAL)
                time.sleep(0.8)
                for _ in range(24):
                    s.mac.key("BackSpace")
                s.mac._xdo("type", "--delay", "120", code)
                time.sleep(1.0)
            s.mac.click(*REG_OK)
            s.shot("try-%s" % (code or "empty"), wait=10.0)
            s.mac.click(*ALERT_OK)          # dismiss "invalid", if shown
            time.sleep(2.0)
        s.shot("after-codes", wait=10.0)
        s.shot("settled", wait=20.0)
        s.mac.command_key("q")
        s.shot("quit", wait=12.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        if os.path.exists(written):
            shutil.copyfile(written, BOOT)
            print("sitopt: personalized image kept at %s" % BOOT)
    finally:
        time.sleep(4)
        s.close()
    return 0


# ------------------------------------------------------------------
# The other way in: StuffIt Deluxe 3.5.1, which already runs here
# ------------------------------------------------------------------
#
# 2.0.1 will not run: it wants a serial number and checks it (above).
# 3.5.1 IS installed and registered on this machine — `spacesaver.py
# --install351` put it there and `sitcrypt.py` drives it — and it still
# knows what an Optimizer is: its application carries *"No optimizers
# are installed"*, and StuffIt Expander 4.0.2's Read Me says an
# optimized archive needs *"the StuffIt Deluxe or the StuffIt Lite
# application, and the 2.0 optimizer used to compress the archive"* —
# which says 3.x uses the 2.0 modules rather than replacing them.
#
# So: drop 2.0's `Text 1` into the 3.5.1 installation and see whether it
# is listed. 3.5 moved Aladdin's folders under `Extensions:Aladdin:`
# (Translators and Viewers are there on this image), so the module goes
# BOTH there and in 2.0's own `{system}Optimizers:` — one boot then
# answers which, or neither.
BOOT351 = os.path.join(WORK, "sitopt351.hfv")
SS_INSTALLED = os.path.join(R.VMAC_HOME, "spacesaver", "ssinstalled.hfv")
VOL351 = "System_7_0_1"
APP_FOLDER351 = "StuffIt Deluxe™ Folder"
# sitcrypt.py's, for this image: it boots with the application's folder
# open and frontmost, and 123 is RESTART on System 7 — Shut Down is 139.
FOLDER_TITLE351 = (200, 33)
SPECIAL_X351 = 225
SHUT_DOWN_Y351 = 139


def install351(args):
    """The 3.5.1 image, with 2.0's Optimizers added to it."""
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(SS_INSTALLED):
        raise SystemExit("sitopt: no %s — tools/vmac/spacesaver.py "
                         "--install351 makes it" % SS_INSTALLED)
    work = tempfile.mkdtemp(prefix="sitopt351-")
    tree = payload(work)
    shutil.copyfile(SS_INSTALLED, BOOT351)
    items = []
    # --plain351 is the CONTROL: the same image, the same copy, the same
    # launch, and no module added. Without it "the application did not
    # come up" says nothing about the modules (it was the harness twice
    # already today).
    mods = () if args.plain351 else ("Text 1", "MacPaint 1")
    for i, mod in enumerate(mods):
        data = os.path.join(tree, "Optimizers", mod)
        mb = os.path.join(work, "m%d.bin" % i)
        open(mb, "wb").write(macbinary(mod, "SITe", "SIT!", b"",
                                       open(data + ".rsrc", "rb").read()))
        items.append((("System Folder", "Extensions", "Aladdin",
                       "Optimizers"), mb))
        items.append((("System Folder", "Optimizers"), mb))
    subj = os.path.join(work, "subject.bin")
    open(subj, "wb").write(macbinary(SUBJECT_NAME, "TEXT", "ttxt",
                                     SUBJECT_DATA, make_rsrc()))
    items.append(((APP_FOLDER351,), subj))
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        hfs(env, "hmount", BOOT351)
        made = set()
        for folder, mb in items:
            for i in range(len(folder)):
                d = folder[:i + 1]
                if d not in made:
                    subprocess.run(
                        ["hmkdir",
                         (VOL351 + ":" + ":".join(d)).encode("mac_roman")],
                        capture_output=True, env=env)
                    made.add(d)
            dest = VOL351 + ":" + ":".join(folder) + ":"
            got = hfs(env, "hcopy", "-m", os.path.abspath(mb),
                      dest.encode("mac_roman"))
            if got.returncode != 0:
                raise SystemExit("sitopt: hcopy to %s failed" % dest)
        hfs(env, "humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
    print("sitopt: 3.5.1 image with 2.0's Optimizers at %s" % BOOT351)
    return BOOT351


APP_ICON351 = (105, 90)


def launch351(s, args):
    """This image boots with the application's folder open, so nothing
    has to be navigated to — but ⌘O is NOT how to open it.

    Two runs went the way sitcrypt.py does it (click the title, Escape,
    type-select, ⌘O) and the application never came up, control
    included. The screenshot says why: at the moment of ⌘O the menu bar
    is still *File Edit View Label Special* — Magic Menu's `Archive` and
    `Translate` menus arrive a few seconds later — so the Finder is
    still settling and the command key goes nowhere. A double-click on
    the icon, and a wait that is not a guess about how long an
    installing extension takes.
    """
    s.boot()
    s.shot("desktop", wait=12.0)
    s.mac.click(*FOLDER_TITLE351)
    s.shot("window-active", wait=8.0)
    # Type-select, not a coordinate: the window opens SCROLLED past the
    # application — a double-click where the icon is in the photograph
    # of a later run opened `Subject` in SimpleText instead — and typing
    # the name both selects it and scrolls it into view.
    s.mac.key("Escape")
    time.sleep(0.6)
    s.mac._xdo("type", "--delay", "120", "StuffIt Deluxe")
    s.shot("app-selected", wait=4.0)
    # ⌘O does not open it. Three runs tried — including one control
    # with nothing added to the image — and the Finder stayed frontmost
    # for 75 s each time, with the application selected and Magic Menu's
    # menus already installed. sitcrypt.py appears to launch it the same
    # way and does not: every dialog in its runs is MAGIC MENU's, over a
    # Finder menu bar (`specimens/sitcrypt/pw8/04-new-dialog.png`), so
    # nothing here had ever launched this application at all. A
    # double-click on the icon does, and the icon is where type-select
    # has just scrolled it.
    s.mac.click(*APP_ICON351, double=True)
    s.shot("launched", wait=args.launch_wait)


def phase_map351(args):
    """Launch 3.5.1 with the 2.0 Optimizers installed and peek its
    menus — the one question being whether anything now lists `Text 1`
    where it used to say *"No optimizers are installed"*."""
    img = os.path.join(WORK, "run-map351.hfv")
    shutil.copyfile(BOOT351, img)
    s = Session(img, [], os.path.join(SPECIMENS, "map351"), mem=args.emu)
    try:
        launch351(s, args)
        s.shot("menubar", wait=2.0)
        for x in range(25, 460, 45):
            s.peek(x, "menu-x%03d" % x)
        s.mac.command_key("q")
        s.shot("quit", wait=10.0)
        s.menu(SPECIAL_X351, SHUT_DOWN_Y351, "special-menu")
        s.shot("off", wait=35.0)
    finally:
        time.sleep(4)
        s.close()
    print("sitopt: shots in %s" % os.path.join(SPECIMENS, "map351"))
    return 0


def phase_magic(args):
    """The Finder with 2.0's Magic Menu loaded, and nothing launched.

    2.0.1's application will not run here (it checks its serial number),
    but Magic Menu is an INIT and a cdev: it adds Aladdin's menus to the
    FINDER and stuffs through the Engine without the application. Every
    dialog in `sitcrypt.py`'s successful runs turns out to be 3.5.1's
    Magic Menu, over a Finder menu bar — so this is the half of StuffIt
    that has ever actually worked on this machine.

    The question is whether its Stuff dialog reaches an Optimizer.
    3.5.1's does not (`specimens/sitcrypt/pw8/07-stuff-dialog.png`: a
    file list, "Items to Stuff", "Delete item when finished" and
    "Encrypt with password", and nothing else).
    """
    img = os.path.join(WORK, "run-magic.hfv")
    shutil.copyfile(BOOT, img)
    s = Session(img, [], os.path.join(SPECIMENS, "magic"), mem=args.emu)
    try:
        s.boot()
        s.shot("desktop", wait=12.0)
        s.mac.click(*BOOT_ICON, double=True)
        s.shot("volume", wait=12.0)
        s.mac._xdo("type", "--delay", "120", "Subject")
        s.shot("subject-selected", wait=3.0)
        for x in range(30, 480, 40):
            s.peek(x, "menu-x%03d" % x)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
    finally:
        time.sleep(4)
        s.close()
    print("sitopt: shots in %s" % os.path.join(SPECIMENS, "magic"))
    return 0


SUBJECT_ICON = (105, 170)
MAGIC_X = 230


def phase_stuff(args):
    """Select the subject and open Magic Menu's Stuff dialog.

    The one control this whole harness is looking for: the Addendum says
    an Optimizer is turned on *"from the Optimizers dialog (in Expert
    menus, from either the Options menu or from a Stuff or QuickStuff
    dialog)"*. The Options menu belongs to the application, which will
    not run here; the Stuff dialog belongs to Magic Menu, which does.
    Magic Menu's own `StuffIt Options ▸` is a SUBMENU, and a submenu
    item cannot be selected under Mini vMac at all — three ways
    measured, tools/vmac/README.md — so the dialog is the only way in.
    """
    img = os.path.join(WORK, "run-stuff.hfv")
    shutil.copyfile(BOOT, img)
    s = Session(img, [], os.path.join(SPECIMENS, args.tag), mem=args.emu)
    try:
        s.boot()
        s.shot("desktop", wait=12.0)
        s.mac.click(*BOOT_ICON, double=True)
        s.shot("volume", wait=12.0)
        # A CLICK, not a type-select: with nothing selected the menu
        # reads "Stuff Disk" instead of "Stuff File", which is how the
        # first probe showed the type-select had not taken.
        s.mac.click(*SUBJECT_ICON)
        s.shot("subject-selected", wait=3.0)
        s.peek(MAGIC_X, "magic-menu")
        s.mac.command_key("s")
        s.shot("stuffed", wait=15.0)
        # ⌘S shows no dialog at all: it stuffs the selection and
        # `Subject.sit` appears in the window. Shut Down, or Mini vMac
        # never flushes the volume and the archive is only a photograph.
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        outdir = os.path.join(SPECIMENS, args.tag)
        if os.path.exists(written):
            env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
            try:
                if subprocess.run(["hmount", written], capture_output=True,
                                  env=env).returncode == 0:
                    dest = os.path.join(outdir, "Subject.sit.bin")
                    subprocess.run(["hcopy", "-m",
                                    (VOL + ":Subject.sit").encode(),
                                    dest.encode()], capture_output=True,
                                   env=env)
                    subprocess.run(["humount"], capture_output=True, env=env)
                    if os.path.exists(dest):
                        print("sitopt: %s (%d B) — written by StuffIt "
                              "Deluxe 2.0.1's own Engine"
                              % (dest, os.path.getsize(dest)))
                        data, _r = forks(dest)
                        for off, h in entry_headers(data):
                            print("  @%-6d %s" % (off, describe(h)))
            finally:
                shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        time.sleep(4)
        s.close()
    print("sitopt: shots in %s" % os.path.join(SPECIMENS, args.tag))
    return 0


MAGIC_OPTIONS_Y = 122


def phase_options(args):
    """Try to open `Magic ▸ StuffIt Options ▸`, which is a SUBMENU.

    Everything else is exhausted: 2.0.1's application checks its serial
    number, 3.5.1's has never launched here either, and Magic Menu's
    control panel is an on/off switch (its DITL -4064 is "No Magic",
    "Help" and a version string). The Addendum puts the Optimizers
    dialog in the application's Options menu or in a Stuff dialog, and
    Magic Menu's ⌘S shows no dialog — it stuffs. So this submenu is the
    last way in, against a trap this project has already measured three
    ways on the other Magic Menu: submenu items never highlight under
    Mini vMac (tools/vmac/README.md).
    """
    img = os.path.join(WORK, "run-options.hfv")
    shutil.copyfile(BOOT, img)
    s = Session(img, [], os.path.join(SPECIMENS, args.tag), mem=args.emu)
    try:
        s.boot()
        s.shot("desktop", wait=12.0)
        s.mac.click(*BOOT_ICON, double=True)
        s.shot("volume", wait=12.0)
        s.mac.click(*SUBJECT_ICON)
        s.shot("subject-selected", wait=3.0)
        ox, oy = s.mac.origin()
        x = s.mac._xdo
        x("mousemove", str(ox + MAGIC_X), str(oy + 8))
        time.sleep(0.5)
        x("mousedown", "1")
        time.sleep(1.5)
        # Down the menu one step at a time: a jump is one of the three
        # ways already measured not to work.
        for y in range(20, MAGIC_OPTIONS_Y + 1, 10):
            x("mousemove", str(ox + MAGIC_X + 20), str(oy + y))
            time.sleep(0.25)
        s.shot("options-item", wait=2.0)
        for px in range(MAGIC_X + 30, 420, 15):
            x("mousemove", str(ox + px), str(oy + MAGIC_OPTIONS_Y + 4))
            time.sleep(0.25)
        s.shot("submenu", wait=2.0)
        for y in range(MAGIC_OPTIONS_Y + 4, MAGIC_OPTIONS_Y + 40, 8):
            x("mousemove", str(ox + 420), str(oy + y))
            time.sleep(0.25)
        s.shot("submenu-item", wait=2.0)
        x("mouseup", "1")
        s.shot("after", wait=8.0)
    finally:
        time.sleep(4)
        s.close()
    print("sitopt: shots in %s" % os.path.join(SPECIMENS, args.tag))
    return 0


def phase_map(args):
    """Launch and photograph the menu bar and every menu in it.

    The application's MENU resources are already read (FORMATS.md): File,
    Edit, Archive, Other, Options, Windows, Scripts. What a screenshot
    adds is where each title sits and which of them are INSTALLED —
    Options and Scripts are the Expert menus, and Edit's last item is the
    switch between the two sets.
    """
    # A copy, like --make: a run that cannot reach Shut Down leaves the
    # image half-written, and the one the next run boots should be the
    # one --install made.
    img = os.path.join(WORK, "run-map.hfv")
    shutil.copyfile(BOOT, img)
    s = Session(img, [], os.path.join(SPECIMENS, "map"), mem=args.emu)
    try:
        launch(s, args)
        s.shot("menubar", wait=2.0)
        for x in range(30, 480, 40):
            s.peek(x, "menu-x%03d" % x)
        s.mac.command_key("q")
        s.shot("quit", wait=10.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=30.0)
    finally:
        time.sleep(4)
        s.close()
    print("sitopt: shots in %s" % os.path.join(SPECIMENS, "map"))
    return 0


# The Scripts menu and Execute Script… in it, and the Edit menu's last
# item, which is the switch between Standard and Expert menus (its title
# is STR# 258's "Switch to Expert Menus"). Measured off --map.
EDIT_X = 78
EDIT_SWITCH_Y = 156
SCRIPTS_X = 395
EXECUTE_Y = 20

# What the run writes, at the root of the one volume it has.
ARCHIVES = ["Plain.sit", "Optimized.sit", "OptBetter.sit"]
STATUS = "Status.out"


def phase_make(args):
    """Run the script, then read the archives and the status file back.

    **This cannot work on this machine and is kept deliberately.** It
    wants the application, which will not run without a serial number
    (module docstring); what it does is the two minutes MANUAL_TESTS.md
    §8 asks somebody with a licensed copy for, written down as code —
    Scripts ▸ Execute Script… on a script whose vocabulary is STR# 257's
    (`Enable Optimizer`, `New Archive`, `Stuff … with fast`,
    `Write Status To`). Run it on an image where the application starts
    and it should produce the pair; run it here and it photographs a
    licence dialog. --force says you know which.

    The application QUITS itself — the script's last command — so the
    Finder is frontmost for Shut Down without a ⌘Q that might land on a
    modal dialog instead.
    """
    if not args.force:
        raise SystemExit(
            "sitopt: --make drives the APPLICATION, which does not run "
            "here: it checks its serial number (--personalize shows the "
            "dialog, MANUAL_TESTS.md §8). --force runs it anyway.")
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    img = os.path.join(WORK, "run-%s.hfv" % args.tag)
    shutil.copyfile(BOOT, img)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        # Expert menus first: Options and Scripts are not installed in the
        # Standard set, and Edit's last item is the switch. Harmless if
        # this build already starts in Expert menus — the item toggles,
        # and --map photographs which way round it was.
        if not args.no_expert:
            s.menu(EDIT_X, EDIT_SWITCH_Y, "edit-switch")
            s.shot("expert", wait=3.0)
        s.menu(SCRIPTS_X, EXECUTE_Y, "scripts-menu")
        s.shot("script-picker", wait=6.0)
        s.mac._xdo("type", "--delay", "120", "Optimize")
        s.shot("script-selected", wait=2.0)
        s.mac.key("Return")
        s.shot("script-running", wait=args.script_wait)
        s.shot("script-done", wait=20.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
    finally:
        time.sleep(5)
        s.close()
    read_back(img, outdir)
    return show(outdir)


def read_back(img, outdir):
    """Copy the archives and the status file off, as MacBinary.

    MacBinary because a StuffIt archive's resource fork is not decoration:
    an encrypted one keeps its password verifier there, and this project's
    own reader wants the whole file.
    """
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        if subprocess.run(["hmount", img], capture_output=True,
                          env=env).returncode != 0:
            print("sitopt: cannot mount %s" % img)
            return
        for name in ARCHIVES + [STATUS]:
            dest = os.path.join(outdir, name + ".bin")
            got = subprocess.run(["hcopy", "-m", (VOL + ":" + name).encode(),
                                  dest.encode()], capture_output=True,
                                 env=env)
            if got.returncode != 0:
                print("sitopt: %-16s NOT on the volume" % name)
        subprocess.run(["humount"], capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


def forks(path):
    """A MacBinary file's two forks."""
    d = open(path, "rb").read()
    dl = int.from_bytes(d[83:87], "big")
    rl = int.from_bytes(d[87:91], "big")
    off = 128 + ((dl + 127) // 128) * 128
    return d[128:128 + dl], d[off:off + rl]


def entry_headers(sit):
    """Every 112-byte entry header in a StuffIt archive, in order.

    A walk and nothing else — the offsets it reads are named in
    src/fmt_sit.c and this prints them rather than deciding anything, so
    a difference between two archives is visible without a decoder.
    """
    out = []
    if sit[:4] != b"SIT!" or sit[10:14] != b"rLau":
        return out
    total = int.from_bytes(sit[6:10], "big")
    pos = 22
    while pos + 112 <= len(sit) and pos + 112 <= total:
        h = sit[pos:pos + 112]
        rc = int.from_bytes(h[92:96], "big")
        dc = int.from_bytes(h[96:100], "big")
        out.append((pos, h))
        folder = (h[1] & 0x6F) in (0x20, 0x21)
        pos += 112 if folder else 112 + rc + dc
    return out


def describe(h):
    nl = min(h[2], 31)
    return ("rmeth=%02x dmeth=%02x  46=%-3d 47=%-3d  104..109=%s  "
            "rlen=%-6d dlen=%-6d rcomp=%-6d dcomp=%-6d  %r"
            % (h[0], h[1], h[46], h[47],
               " ".join("%3d" % b for b in h[104:110]),
               int.from_bytes(h[84:88], "big"),
               int.from_bytes(h[88:92], "big"),
               int.from_bytes(h[92:96], "big"),
               int.from_bytes(h[96:100], "big"),
               h[3:3 + nl].decode("mac-roman", "replace")))


def show_path(path):
    """Print the entry headers of any StuffIt archive, MacBinary or not.

    The mode that needs no emulator: what MANUAL_TESTS.md §8 points at,
    for grading an archive somebody else's registered copy wrote. Given
    two, it diffs their first entry's header — which is the whole of the
    evidence an Optimizer leaves.
    """
    paths = []
    if os.path.isdir(path):
        paths = [os.path.join(path, f) for f in sorted(os.listdir(path))
                 if f.lower().endswith((".sit", ".bin", ".sit.bin"))]
    else:
        paths = [path]
    heads = {}
    for p in paths:
        blob = open(p, "rb").read()
        data = blob
        if blob[:4] != b"SIT!":
            try:
                data, _r = forks(p)
            except Exception:
                pass
        hs = entry_headers(data)
        if not hs:
            print("%s: not a StuffIt archive this can walk" % p)
            continue
        print("=== %s" % p)
        for off, h in hs:
            print("  @%-6d %s" % (off, describe(h)))
        heads[p] = [h for _o, h in hs]
    if len(heads) == 2:
        (pa, a), (pb, b) = sorted(heads.items())
        if len(a) == len(b) == 1:
            diff = [i for i in range(110) if a[0][i] != b[0][i]]
            print("=== %s against %s" % (os.path.basename(pa),
                                         os.path.basename(pb)))
            print("  header bytes that differ: %s"
                  % (", ".join(str(i) for i in diff) or "none"))
            for i in diff:
                print("    %3d: %3d  %3d" % (i, a[0][i], b[0][i]))
    return 0


def show(outdir):
    """Print what came back, and the one comparison that matters."""
    status = os.path.join(outdir, STATUS + ".bin")
    if os.path.exists(status):
        print("=== %s, as the application wrote it" % STATUS)
        data, _ = forks(status)
        for line in data.decode("mac-roman", "replace").split("\r"):
            if line.strip():
                print("  " + line)
    heads = {}
    for name in ARCHIVES:
        p = os.path.join(outdir, name + ".bin")
        if not os.path.exists(p):
            continue
        data, rsrc = forks(p)
        print("=== %s (data %d B, rsrc %d B)" % (name, len(data), len(rsrc)))
        heads[name] = [h for _off, h in entry_headers(data)]
        for off, h in entry_headers(data):
            print("  @%-6d %s" % (off, describe(h)))
    if "Plain.sit" in heads and "Optimized.sit" in heads:
        a, b = heads["Plain.sit"], heads["Optimized.sit"]
        if len(a) == len(b) == 1:
            diff = [i for i in range(110) if a[0][i] != b[0][i]]
            print("=== the control against the optimized one")
            print("  header bytes that differ: %s"
                  % (", ".join(str(i) for i in diff) or "none"))
            for i in diff:
                print("    %3d: plain %3d  optimized %3d" % (i, a[0][i],
                                                             b[0][i]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

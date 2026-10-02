#!/usr/bin/env python3
"""sitopt.py — have StuffIt Deluxe 2.0.1 write an OPTIMIZED archive.

StuffIt Deluxe 2.0 could hand a fork to an external module before
compressing it — an Optimizer, a Compressor or an Encryptor, each a file
of type 'SITe' in a folder of the System Folder. Where an archive RECORDS
which module it used was read out of the application's own code
(FORMATS.md, *Where an archive names the module*); this is what confirms
that reading against archives the application itself wrote, and it
corrected one line of it.

    tools/vmac/sitopt.py --setup        fetch the two 2.0.1 floppies
    tools/vmac/sitopt.py --install      build the System 6 boot volume
    tools/vmac/sitopt.py --personalize  register it, and KEEP that image
    tools/vmac/sitopt.py --make --force --no-expert   run the script
    tools/vmac/sitopt.py --unstuff      2.0.1 unstuffs its own archive
    tools/vmac/sitopt.py --show <path>  any archive's entry headers
    tools/vmac/sitopt.py --magic        the Finder with Magic Menu loaded
    tools/vmac/sitopt.py --stuff        Magic Menu's ⌘S, read back
    tools/vmac/sitopt.py --options      the `StuffIt Options ▸` submenu
    tools/vmac/sitopt.py --dcmpdata     run MacPaint 1's COMP and DCMP

**It installs by COPYING.** The download is a StuffIt archive of two
DiskCopy images; disk 1 holds an installer whose DATA fork is another
StuffIt archive, and `macextract` unwraps the lot. Where each piece goes
is Aladdin's own `UnInstall Dlx Files Script`, on disk 2, which erases
`{system}Optimizers:Text 1` and the rest by name. The installer is never
run, so no dialog of its is guessed at.

**The serial is published on the page the download is on** —
`macintoshgarden.org/apps/stuffit-deluxe-2`, *"A nnnnn (where 'n' = any
number)"*. It is NOT `/apps/stuffit-deluxe`, whose codes `spacesaver.py`
carries for 3.0.7 and 5.x; those were tried first, refused, and written
up as a registration wall before anybody opened the right page
(BLOCKERS.md, withdrawn claims).

**The run is a SCRIPT.** StuffIt Deluxe 2.0 has its own language —
vocabulary in the application's STR# 257, shapes in the payload's
`Sample Scripts` — and ⌘E runs a TEXT/'SIT!' file of it. So the control
and the optimized pair come out of one boot, written by commands whose
spelling is Aladdin's rather than by clicks on a checkbox at a
coordinate, and `Write Status To` brings back the application's own
account of what it did.

**What the specimens settled**, and it is not what was expected: `Text 1`
writes **255** into byte 106, not its module id of 5, and 2.0.1's own
unstuffer hands back the OPTIMIZED bytes. 255 means an Optimizer nothing
can undo, so this engine decodes those entries and refuses only the ids a
'DCMP' could restore. `tools/run_sitopt.py` grades that.

What this CANNOT see:

- **`Sound 1`, `Photoshop 1`, `Photoshop:JPEG Lossy`.** Two of the five
  modules are exercised; nothing on this machine is a document the
  other three take. `MacPaint 1` needed one too, and MacPaint 2.0 drew
  it — `--add-paint`, then `--paint`.
- **whether the other four modules restore anything.** `MacPaint 1` is
  driven both ways by `--dcmpdata` and rebuilds a valid document;
  nothing has run `Sound 1`, `Photoshop 1` or `JPEG Lossy`, and `Text
  1` has no `DCMP` to run.
- **whether 3.5.1 would use a 2.0 module.** `--install351` puts `Text 1`
  in both places 3.5 might look; that application does not launch here.
- **the 512 KB machine.** It boots `mv-4M`: the resource fork alone is
  423 KB.
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
import run as R                                          # noqa: E402
from arcmac import macbinary, hfs                        # noqa: E402
from diskdoubler import Session                          # noqa: E402

CACHE = os.path.join(os.path.expanduser("~"), ".cache", "macextract", "sit2")
MAIN_SIT = os.path.join(CACHE, "stuffit-deluxe-v2.sit")
OPT_SIT = os.path.join(CACHE, "deluxe-2-optional.sit")
MAIN_MD5 = "45b940a528fe2bc18560bf0b2ae60f7a"
PAGE = "https://macintoshgarden.org/apps/stuffit-deluxe-2"
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
    # All five. The first run installed two and the application said so
    # rather than guessing — *"* * * Optimizer Not Found: Sound 1"* in
    # the script's own status file, which is why `Write Status To` is on
    # every script here.
    (("System Folder", "Optimizers"), "Optimizers/Text 1", "SITe", "SIT!"),
    (("System Folder", "Optimizers"), "Optimizers/MacPaint 1", "SITe", "SIT!"),
    (("System Folder", "Optimizers"), "Optimizers/Sound 1", "SITe", "SIT!"),
    (("System Folder", "Optimizers"), "Optimizers/Photoshop 1", "SITe",
     "SIT!"),
    # The one whose Macintosh name has a SLASH in it. `macextract`
    # applies the reversible '/'->':' swap on the way out (a ':' cannot
    # occur in an HFS name and a '/' can), so the payload file is
    # `Photoshop:JPEG Lossy` here and has to go back the other way
    # before it reaches the volume — the uninstall script on disk 2
    # erases `{system}Optimizers:Photoshop/JPEG Lossy`.
    (("System Folder", "Optimizers"), "Optimizers/Photoshop:JPEG Lossy",
     "SITe", "SIT!"),
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


def one_resource(rtype, rid, body):
    """A resource fork holding exactly one resource.

    Inside Macintosh I-121, the same layout `spacesaver.resources()`
    parses: a 16-byte header, the data, then a map with one type entry
    and one reference.
    """
    data = len(body).to_bytes(4, "big") + body
    reflist = rid.to_bytes(2, "big", signed=True) + \
        (0xFFFF).to_bytes(2, "big") + b"\x00" + (0).to_bytes(3, "big") + \
        (0).to_bytes(4, "big")
    typelist = (0).to_bytes(2, "big") + rtype.encode("mac_roman") + \
        (0).to_bytes(2, "big") + (2 + 8).to_bytes(2, "big")
    # 16 bytes of header copy, 4 of handle, 2 of file ref, **2 of
    # attributes**, then the two offsets — the attributes word is what
    # the first version of this left out, which put `typeListOffset`
    # two bytes early and made every fork it built unreadable. Nothing
    # noticed until `Photoshop 1` declined a subject built to its own
    # test: Get1Resource returned NULL and the module was right to say
    # no. Inside Macintosh I-121, and `spacesaver.resources()` parses
    # what this writes.
    themap = bytes(16) + bytes(4) + bytes(2) + bytes(2) + \
        (28).to_bytes(2, "big") + \
        (28 + len(typelist) + len(reflist)).to_bytes(2, "big") + \
        typelist + reflist
    dataoff = 256
    head = (dataoff).to_bytes(4, "big") + \
        (dataoff + len(data)).to_bytes(4, "big") + \
        len(data).to_bytes(4, "big") + len(themap).to_bytes(4, "big")
    return head + bytes(dataoff - len(head)) + data + themap


def make_rsrc():
    """A resource fork with one 'STR ' in it, so `Text 1`'s *Delete
    resources* has something to delete."""
    return one_resource("STR ", 0, b"\x1cStuffIt Deluxe 2.0.1 wrote it")


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
        name = rel.split("/")[-1].replace(":", "/")
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
    ap.add_argument("--add-paint", action="store_true")
    ap.add_argument("--paint", action="store_true")
    ap.add_argument("--makepaint", action="store_true")
    ap.add_argument("--makemods", action="store_true")
    ap.add_argument("--unstuffapp", action="store_true")
    ap.add_argument("--dcmp", action="store_true")
    ap.add_argument("--dcmpdata", action="store_true")
    ap.add_argument("--add-photoshop", action="store_true")
    ap.add_argument("--psdoc", action="store_true")
    ap.add_argument("--psjpeg", action="store_true")
    ap.add_argument("--psmatrix", action="store_true")
    ap.add_argument("--psmenus", action="store_true")
    ap.add_argument("--psopts", action="store_true")
    ap.add_argument("--psenc", action="store_true")
    ap.add_argument("--psencgui", action="store_true")
    ap.add_argument("--enctext", action="store_true")
    ap.add_argument("--psdes", action="store_true")
    ap.add_argument("--psex", action="store_true")
    ap.add_argument("--psrest", action="store_true")
    ap.add_argument("--psfold", action="store_true")
    ap.add_argument("--pssea", action="store_true")
    ap.add_argument("--password", default="swordfish")
    ap.add_argument("--quality", type=int,
                    help="set the JPEG Optimizer's Q before stuffing "
                         "(its own dialog; the default is 25)")
    # A SECOND subject, for one question: `CCOD`+0x3826's
    # round-toward-zero correction is in the module's code and the exact
    # output does not want it (FORMATS.md, *What an Optimizer did to the
    # fork*). One image cannot say whether the trace mis-read that tail
    # or the image never takes it; a second one with different content
    # can, so the drawing and the document name are arguments now.
    ap.add_argument("--drawing", choices=("zigzag", "grid"),
                    default="zigzag",
                    help="what --psdoc draws: the original five zigzag "
                         "strokes, or a dense grid (high-frequency, which "
                         "is what exercises the IDCT's rounding)")
    ap.add_argument("--psname", default=PS_DOC,
                    help="the Photoshop document's name on the volume")
    ap.add_argument("--add-archive",
                    help="a MacBinary archive to put on the image first")
    ap.add_argument("--add-modules", action="store_true")
    ap.add_argument("--magic", action="store_true")
    ap.add_argument("--stuff", action="store_true")
    ap.add_argument("--options", action="store_true")
    ap.add_argument("--map", action="store_true")
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--show", nargs="?", const=True,
                    help="an archive, or a directory of them")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--unstuff", action="store_true")
    ap.add_argument("--image", help="boot this image instead")
    ap.add_argument("--archive", help="which archive to unstuff")
    ap.add_argument("--item", help="the entry it holds")
    ap.add_argument("--against", help="MacBinary to compare with")
    ap.add_argument("--icon", help="x,y of the archive icon")
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
    if args.unstuff:
        return phase_unstuff(args)
    if args.add_paint:
        return add_paint(args)
    if args.paint:
        return phase_paint(args)
    if args.makepaint:
        return phase_makepaint(args)
    if args.add_modules:
        return add_modules(args)
    if args.makemods:
        return phase_makemods(args)
    if args.unstuffapp:
        return phase_unstuffapp(args)
    if args.dcmp:
        return phase_dcmp(args)
    if args.dcmpdata:
        return phase_dcmpdata(args)
    if args.add_photoshop:
        return add_photoshop(args)
    if args.pssea:
        return phase_pssea(args)
    if args.psfold:
        return phase_psfold(args)
    if args.psrest:
        return phase_psrest(args)
    if args.psex:
        return phase_psex(args)
    if args.psdes:
        return phase_psdes(args)
    if args.enctext:
        return phase_enctext(args)
    if args.psencgui:
        return phase_psencgui(args)
    if args.psenc:
        return phase_psenc(args)
    if args.psopts:
        return phase_psopts(args)
    if args.psmenus:
        return phase_psmenus(args)
    if args.psmatrix:
        return phase_psmatrix(args)
    if args.psdoc:
        return phase_psdoc(args)
    if args.psjpeg:
        return phase_psjpeg(args)
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
# **"A" and five digits, any digits.** Published on the page these two
# downloads come from, `macintoshgarden.org/apps/stuffit-deluxe-2`,
# against the installer set itself: *"Requires a name and serial
# activation: A nnnnn (where 'n' = any number, for example: A 12345).
# Note: Entering the code with caps lock on, may be necessary."*
#
# The six codes this list held first were `spacesaver.py`'s, which are
# from `/apps/stuffit-deluxe` — 3.0.7's "S"+5 and 5.x's DLX forms — and
# 2.0.1 refused every one of them, correctly. They were the wrong
# version's, and the page that has this file says so; nobody had opened
# it (BLOCKERS.md, withdrawn claims).
PUBLISHED_CODES = ["A 12345"]


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


MADE = os.path.join(WORK, "sitopt-made.hfv")
PAINTED = os.path.join(WORK, "sitopt-painted.hfv")
ARCHIVE_ICON = (240, 170)   # Optimized.sit; OptBetter.sit is at 172


def phase_unstuff(args):
    """Have 2.0.1 unstuff its OWN optimized archive, and keep what it writes.

    The question this settles is a behaviour, not a reading. `Text 1`
    has no 'DCMP' — nothing it does is undone — so the optimized bytes
    may be all that exists, in which case extracting them is what
    Aladdin's software itself does and refusing the entry loses a user
    their file. If instead 2.0.1 produces the ORIGINAL, something
    restores it and refusing is right. `unar` writes the optimized
    bytes and calls it a success either way.

    Booted from the image `--make` wrote, with the original `Subject`
    DELETED first so that what comes back cannot be it.
    """
    src = args.image or MADE
    arc_name = args.archive or "Optimized.sit"
    item = args.item or SUBJECT_NAME
    if not os.path.exists(src):
        raise SystemExit("sitopt: no %s — --make writes it" % src)
    img = os.path.join(WORK, "run-unstuff.hfv")
    shutil.copyfile(src, img)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        hfs(env, "hmount", img)
        subprocess.run(["hdel", (VOL + ":" + item).encode()],
                       capture_output=True, env=env)
        hfs(env, "humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        s.boot()
        s.shot("desktop", wait=12.0)
        s.mac.click(*BOOT_ICON, double=True)
        s.shot("volume", wait=12.0)
        s.mac.click(*(args.icon and tuple(int(v) for v in args.icon.split(",")) or ARCHIVE_ICON))
        s.shot("archive-selected", wait=3.0)
        s.mac.command_key("u")
        s.shot("unstuffed", wait=20.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            if subprocess.run(["hmount", written], capture_output=True,
                              env=env).returncode == 0:
                dest = os.path.join(outdir, "unstuffed.bin")
                subprocess.run(["hcopy", "-m", (VOL + ":" + item).encode(),
                                dest.encode()], capture_output=True, env=env)
                subprocess.run(["humount"], capture_output=True, env=env)
                if os.path.exists(dest):
                    data, rsrc = forks(dest)
                    print("sitopt: 2.0.1 unstuffed it to %d B of data, "
                          "%d B of resource" % (len(data), len(rsrc)))
                    print("  same as the ORIGINAL subject: %s"
                          % (data == SUBJECT_DATA))
                    print("  first 60 bytes: %r" % data[:60])
                    if args.against and os.path.exists(args.against):
                        od, orr = forks(args.against)
                        print("  == %s: data %s, rsrc %s"
                              % (os.path.basename(args.against),
                                 data == od, rsrc == orr))
                else:
                    print("sitopt: nothing called Subject came back")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        time.sleep(4)
        s.close()
    return 0


PAINT_SEA = ("/media/mac/Utilities/6/MacPaint/macpaint2.0.sea_.hqx")
PAINT_NAME = "Mac Paint 2.0"
PAINT_ICON = (172, 170)        # measured off paint1/02-volume.png
PAINT_DOC = "Painting"


def add_paint(args):
    """Put MacPaint 2.0 on the REGISTERED image, without rebuilding it.

    `--install` makes the volume from `System6.hfv` and would throw away
    the personalization `--personalize` wrote into the application's own
    resource fork, so anything added afterwards is added in place.

    MacPaint is here because `MacPaint 1` is the Optimizer that CAN be
    undone — it carries a 'DCMP' where `Text 1` does not — and it keys
    on type 'PNTG' (the literal is in its 'COMP' resource three times).
    Nothing in the 933-fixture corpus is a PNTG: the manifests have six
    'sfil' sounds and no paint document at all. So the document is made
    by the program that invented the format.
    """
    if not os.path.exists(BOOT):
        raise SystemExit("sitopt: no %s — --install then --personalize" % BOOT)
    if not os.path.exists(PAINT_SEA):
        raise SystemExit("sitopt: no %s" % PAINT_SEA)
    work = tempfile.mkdtemp(prefix="sitopt-paint-")
    try:
        out = os.path.join(work, "app")
        subprocess.run([CLI, "x", "-o", out, PAINT_SEA], check=True,
                       capture_output=True)
        data = os.path.join(out, PAINT_NAME)
        mb = os.path.join(work, "paint.bin")
        open(mb, "wb").write(macbinary(PAINT_NAME, "APPL", "MPNT",
                                       open(data, "rb").read(),
                                       open(data + ".rsrc", "rb").read()))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", BOOT)
            got = hfs(env, "hcopy", "-m", mb, (VOL + ":").encode())
            if got.returncode != 0:
                raise SystemExit("sitopt: hcopy failed: %s" % got.stderr)
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("sitopt: MacPaint 2.0 added to %s" % BOOT)
    return 0


def phase_paint(args):
    """Draw in MacPaint and save the document, so a PNTG exists.

    Every step is photographed because none of the coordinates are
    known: this application has never run here.
    """
    img = os.path.join(WORK, "run-paint.hfv")
    shutil.copyfile(BOOT, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        s.boot()
        s.shot("desktop", wait=12.0)
        s.mac.click(*BOOT_ICON, double=True)
        s.shot("volume", wait=12.0)
        # CLICK the icon. Type-select and ⌘O renamed the application to
        # `Painting` on the first run — the Finder took the keystrokes
        # because nothing had launched — which is `sitcrypt.py`'s
        # oldest trap wearing a third hat.
        s.mac.click(*PAINT_ICON)
        s.shot("app-selected", wait=3.0)
        s.mac.command_key("o")
        s.shot("launched", wait=args.launch_wait)
        # A few strokes in the middle of whatever canvas is there. The
        # point is bytes that are not a blank page: `MacPaint 1` removes
        # what is not artwork and must leave artwork alone.
        ox, oy = s.mac.origin()
        x = s.mac._xdo
        for row in (120, 150, 180):
            x("mousemove", str(ox + 140), str(oy + row))
            time.sleep(0.3)
            x("mousedown", "1")
            for px in range(140, 340, 12):
                x("mousemove", str(ox + px), str(oy + row + (px % 24) - 12))
                time.sleep(0.05)
            x("mouseup", "1")
            time.sleep(0.4)
        s.shot("drawn", wait=3.0)
        s.mac.command_key("s")
        s.shot("save-dialog", wait=8.0)
        s.mac._xdo("type", "--delay", "120", PAINT_DOC)
        s.shot("save-named", wait=2.0)
        s.mac.key("Return")
        s.shot("saved", wait=10.0)
        s.mac.command_key("q")
        s.shot("quit", wait=10.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            if subprocess.run(["hmount", written], capture_output=True,
                              env=env).returncode == 0:
                out = subprocess.run(["hls", "-l", (VOL + ":").encode()],
                                     capture_output=True, env=env)
                for line in out.stdout.decode("mac-roman",
                                              "replace").splitlines():
                    if PAINT_DOC in line:
                        print("sitopt: %s" % line.strip())
                dest = os.path.join(outdir, PAINT_DOC + ".bin")
                subprocess.run(["hcopy", "-m", (VOL + ":" + PAINT_DOC).encode(),
                                dest.encode()], capture_output=True, env=env)
                subprocess.run(["humount"], capture_output=True, env=env)
                if os.path.exists(dest):
                    shutil.copyfile(written, PAINTED)
                    print("sitopt: kept the image with it at %s" % PAINTED)
                else:
                    print("sitopt: no %s on the volume" % PAINT_DOC)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        time.sleep(4)
        s.close()
    return 0


# The second script, and the one the whole reading hangs on: `MacPaint
# 1` carries a 'DCMP', so it is the REVERSIBLE kind, and what it writes
# into byte 106 is the question `Text 1` could not answer (it writes the
# 255 sentinel). Named so its first letters collide with nothing else on
# the volume — `Painting` is right beside it in the picker.
PAINT_SCRIPT_NAME = "Run Paint"
PAINT_SCRIPT = "\r".join([
    "; written by tools/vmac/sitopt.py",
    'Write Status To "{Startup}PaintStatus.out"',
    "Continue On Error",
    'New Archive "{Startup}PlainPaint.sit"',
    'Stuff "{Startup}Painting" with fast',
    "Close",
    'Enable Optimizer "MacPaint 1"',
    'New Archive "{Startup}OptPaint.sit"',
    'Stuff "{Startup}Painting" with fast',
    "Close",
    "Quit",
    "",
])
PAINT_ARCHIVES = ["PlainPaint.sit", "OptPaint.sit"]


def phase_makepaint(args):
    """Stuff the MacPaint document twice: Optimizer off, then on."""
    if not os.path.exists(PAINTED):
        raise SystemExit("sitopt: no %s — --paint makes it" % PAINTED)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    img = os.path.join(WORK, "run-%s.hfv" % args.tag)
    shutil.copyfile(PAINTED, img)
    work = tempfile.mkdtemp(prefix="sitopt-ps-")
    try:
        mb = os.path.join(work, "script.bin")
        open(mb, "wb").write(macbinary(PAINT_SCRIPT_NAME, "TEXT", "SIT!",
                                       PAINT_SCRIPT.encode("mac_roman")))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            hfs(env, "hcopy", "-m", mb, (VOL + ":").encode())
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.peek(SCRIPTS_X, "scripts-menu")
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Run")
        s.shot("script-selected", wait=3.0)
        s.mac.key("Return")
        s.shot("script-running", wait=args.script_wait)
        s.shot("script-done", wait=20.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            if subprocess.run(["hmount", written], capture_output=True,
                              env=env).returncode == 0:
                for n in PAINT_ARCHIVES + ["PaintStatus.out", "Painting"]:
                    subprocess.run(["hcopy", "-m", (VOL + ":" + n).encode(),
                                    os.path.join(outdir,
                                                 n + ".bin").encode()],
                                   capture_output=True, env=env)
                subprocess.run(["humount"], capture_output=True, env=env)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        time.sleep(4)
        s.close()
    st = os.path.join(outdir, "PaintStatus.out.bin")
    if os.path.exists(st):
        data, _r = forks(st)
        print("=== PaintStatus.out")
        for line in data.decode("mac-roman", "replace").split("\r"):
            if line.strip():
                print("  " + line)
    return show_path(outdir)


# The last three modules, and what each of them actually asks for —
# which took two runs to stop guessing at. `Sound 1` is for **Sound
# Designer II** files, not sounds in general: its COMP compares the
# file's type against 'FSSD' and then wants an 'INFO' 1000 resource,
# and it declined the corpus's 'sfil' suitcase (`derived-Eagle.sit`)
# exactly as it should. `Photoshop 1` compares against **'8BIM'**,
# Photoshop 1.0's own type rather than the later '8BPS', and wants an
# '8BIM' 1000 resource. Both tests are read out of the modules' own
# code (mods_subjects, below).
#
# **`Photoshop/JPEG Lossy` is the one that could falsify the rule.** It
# carries a 'DCMP' (id 3) like the other reversible modules, but what it
# does is lossy — and 255, the value this engine DECODES, is the value
# the application's own Get Info pane prints as " lossy". If a lossy
# module writes 255 while having a 'DCMP', decoding it gives bytes
# nobody can check.
PHOTO_NAME = "Photo"
MODS_SCRIPT_NAME = "Modules Script"
MODS_SCRIPT = "\r".join([
    "; written by tools/vmac/sitopt.py",
    'Write Status To "{Startup}ModStatus.out"',
    "Continue On Error",
    'New Archive "{Startup}PlainMods.sit"',
    'Stuff "{Startup}Sound2" with fast',
    'Stuff "{Startup}Photo" with fast',
    "Close",
    'Enable Optimizer "Sound 1"',
    'New Archive "{Startup}OptSound.sit"',
    'Stuff "{Startup}Sound2" with fast',
    "Close",
    'Enable Optimizer "Photoshop 1"',
    'New Archive "{Startup}OptPhoto.sit"',
    'Stuff "{Startup}Photo" with fast',
    "Close",
    'Disable Optimizer "Photoshop 1"',
    'Enable Optimizer "Photoshop/JPEG Lossy"',
    'New Archive "{Startup}OptJpeg.sit"',
    'Stuff "{Startup}Photo" with fast',
    "Close",
    "Quit",
    "",
])
MODS_ARCHIVES = ["PlainMods.sit", "OptSound.sit", "OptPhoto.sit",
                 "OptJpeg.sit"]


def mods_subjects(work):
    """The two subjects, as MacBinary. Returns [(path, note)]."""
    out = []
    # The Photoshop document, written by ImageMagick and read back by
    # deark before it is used.
    psd = os.path.join(work, "test.psd")
    # RGB and not tiny, and then made to satisfy the module's OWN test.
    #
    # Source: `Photoshop 1`'s COMP resource, disassembled. Asked whether
    # it will take a file (selector -1 in the parameter at +12), it
    # compares the long at +32 of the file's record against **'8BIM'** —
    # Photoshop 1.0's own file type, not the later '8BPS' — then opens
    # the RESOURCE fork and does Get1Resource('8BIM', 1000): at least
    # ten bytes, and the word at +8 must be 1 or 3..7, which is the
    # colour mode. An ImageMagick PSD is type 8BPS with an empty
    # resource fork, and both Photoshop modules declined it twice.
    #
    # So the data fork is a real PSD (deark reads it as mode 3, three
    # channels) and the resource fork is built to that test. **That
    # makes the subject synthetic where it counts**: it shows what the
    # module does once it accepts a file, not what a real Photoshop
    # document looks like.
    r = subprocess.run(["convert", "-size", "160x120", "gradient:navy-orange",
                        "-depth", "8", psd], capture_output=True)
    if r.returncode == 0 and os.path.exists(psd):
        blob = open(psd, "rb").read()
        if blob[:4] != b"8BPS":
            raise SystemExit("sitopt: ImageMagick did not write a PSD")
        info = bytes(6) + (8).to_bytes(2, "big") + (3).to_bytes(2, "big") + \
            bytes(6)                     # depth 8 at +6, mode 3 at +8
        mb = os.path.join(work, "photo.bin")
        open(mb, "wb").write(macbinary(PHOTO_NAME, "8BIM", "8BIM", blob,
                                       one_resource("8BIM", 1000, info)))
        out.append((mb, "%s, 8BIM/8BIM, %d B of PSD + an '8BIM' 1000 "
                    "resource (mode 3)" % (PHOTO_NAME, len(blob))))
    # And a Sound Designer II file, which is what `Sound 1` asks for:
    # its COMP compares the same field against **'FSSD'** and then wants
    # Get1Resource('INFO', 1000). The corpus's six sounds are 'sfil'
    # suitcases and it declined one, correctly.
    sd2 = os.path.join(work, "sd2.bin")
    pcm = bytes((i * 7) % 256 for i in range(8192))
    open(sd2, "wb").write(macbinary("Sound2", "FSSD", "Sd2a", pcm,
                                    one_resource("INFO", 1000, bytes(32))))
    out.append((sd2, "Sound2, FSSD/Sd2a, %d B + an 'INFO' 1000 resource"
                % len(pcm)))
    return out


def add_modules(args):
    """Add the three Optimizers the first install missed, IN PLACE.

    `--install` rebuilds the volume from `System6.hfv` and would throw
    away the registration, so anything added after `--personalize` is
    added to the image rather than baked into a fresh one.
    """
    target = args.image or PAINTED
    if not os.path.exists(target):
        raise SystemExit("sitopt: no %s" % target)
    work = tempfile.mkdtemp(prefix="sitopt-mod-")
    try:
        tree = payload(work)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", target)
            for i, rel in enumerate(("Sound 1", "Photoshop 1",
                                     "Photoshop:JPEG Lossy")):
                src = os.path.join(tree, "Optimizers", rel)
                if not os.path.exists(src + ".rsrc"):
                    raise SystemExit("sitopt: no %s in the payload" % rel)
                mb = os.path.join(work, "m%d.bin" % i)
                open(mb, "wb").write(macbinary(
                    rel.replace(":", "/"), "SITe", "SIT!", b"",
                    open(src + ".rsrc", "rb").read()))
                dest = (VOL + ":System Folder:Optimizers:")
                got = hfs(env, "hcopy", "-m", mb,
                          dest.encode("mac_roman"))
                if got.returncode != 0:
                    raise SystemExit("sitopt: hcopy %s failed: %s"
                                     % (rel, got.stderr))
                print("sitopt: installed %s" % rel.replace(":", "/"))
            out = subprocess.run(
                ["hls", (VOL + ":System Folder:Optimizers:").encode()],
                capture_output=True, env=env)
            print("sitopt: Optimizers folder now: %s"
                  % " ".join(out.stdout.decode("mac-roman",
                                               "replace").split()))
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def phase_makemods(args):
    """Sound 1, Photoshop 1 and JPEG Lossy, in one boot.

    Same shape as --makepaint: put the subjects and a script on a copy
    of the registered image, run it with ⌘E, read the archives back.
    """
    base = args.image or PAINTED
    if not os.path.exists(base):
        raise SystemExit("sitopt: no %s — --paint makes it" % base)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    img = os.path.join(WORK, "run-%s.hfv" % args.tag)
    shutil.copyfile(base, img)
    work = tempfile.mkdtemp(prefix="sitopt-mods-")
    try:
        items = mods_subjects(work)
        for _p, note in items:
            print("sitopt: subject %s" % note)
        mb = os.path.join(work, "script.bin")
        open(mb, "wb").write(macbinary(MODS_SCRIPT_NAME, "TEXT", "SIT!",
                                       MODS_SCRIPT.encode("mac_roman")))
        items.append((mb, "the script"))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            for p, _n in items:
                got = hfs(env, "hcopy", "-m", p, (VOL + ":").encode())
                if got.returncode != 0:
                    raise SystemExit("sitopt: hcopy %s failed" % p)
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.peek(SCRIPTS_X, "scripts-menu")
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Mod")
        s.shot("script-selected", wait=3.0)
        s.mac.key("Return")
        s.shot("script-running", wait=args.script_wait)
        s.shot("script-done", wait=25.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            if subprocess.run(["hmount", written], capture_output=True,
                              env=env).returncode == 0:
                for n in MODS_ARCHIVES + ["ModStatus.out", "Sound2",
                                          PHOTO_NAME]:
                    subprocess.run(["hcopy", "-m", (VOL + ":" + n).encode(),
                                    os.path.join(outdir,
                                                 n + ".bin").encode()],
                                   capture_output=True, env=env)
                subprocess.run(["humount"], capture_output=True, env=env)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        time.sleep(4)
        s.close()
    st = os.path.join(outdir, "ModStatus.out.bin")
    if os.path.exists(st):
        data, _r = forks(st)
        print("=== ModStatus.out")
        for line in data.decode("mac-roman", "replace").split("\r"):
            if line.strip():
                print("  " + line)
    return show_path(outdir)


# Having the APPLICATION unstuff an optimized archive. Magic Menu
# refuses one — *"Please use StuffIt Deluxe instead"* — and StuffIt
# Deluxe is what has the module, so this is the measurement behind the
# claim that a 'DCMP' restores the original. The module's code runs;
# what this does not do is call it directly (OPEN_ITEMS.md).
UNST_SCRIPT_NAME = "Zunstuff"


def unst_script(archive):
    """The application's own script for unstuffing ONE archive."""
    return "\r".join([
        "; written by tools/vmac/sitopt.py",
        'Write Status To "{Startup}UnStatus.out"',
        "Continue On Error",
        'Destination "{Startup}Out:"',
        "; UnStuff works on the OPEN archive's entries, not on a file:",
        '; the first attempt said "* * * No open archive!" for both lines.',
        "; ONE archive, because two of them both write `Painting` into the",
        "; destination and the second run could not say which file it got.",
        'Open Archive "{Startup}%s"' % archive,
        'UnStuff "*"',
        "Close",
        "Quit",
        "",
    ])


def phase_unstuffapp(args):
    """StuffIt Deluxe 2.0.1 unstuffs an archive its own Engine refused —
    the subject is deleted first, so what comes back cannot be it.

    `--archive` and `--item` say which; the defaults are the `MacPaint 1`
    pair. For a module whose archive is not already on the boot image —
    `Sound 1`, `Photoshop 1` and `JPEG Lossy` were stuffed on a
    different boot — pass `--image` and `--add-archive` and this copies
    the archive on first.
    """
    base = args.image or os.path.join(WORK, "sitopt-paintmade.hfv")
    if not os.path.exists(base):
        raise SystemExit("sitopt: no %s — --makepaint makes it" % base)
    arcname = args.archive or "OptPaint.sit"
    item = args.item or PAINT_DOC
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    img = os.path.join(WORK, "run-%s.hfv" % args.tag)
    shutil.copyfile(base, img)
    work = tempfile.mkdtemp(prefix="sitopt-un-")
    try:
        mb = os.path.join(work, "script.bin")
        open(mb, "wb").write(macbinary(
            UNST_SCRIPT_NAME, "TEXT", "SIT!",
            unst_script(arcname).encode("mac_roman")))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            if args.add_archive:
                hfs(env, "hcopy", "-m", os.path.abspath(args.add_archive),
                    (VOL + ":").encode())
            subprocess.run(["hdel", (VOL + ":" + item).encode()],
                           capture_output=True, env=env)
            subprocess.run(["hmkdir", (VOL + ":Out").encode()],
                           capture_output=True, env=env)
            hfs(env, "hcopy", "-m", mb, (VOL + ":").encode())
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.peek(SCRIPTS_X, "scripts-menu")
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Zun")
        s.shot("script-selected", wait=3.0)
        s.mac.key("Return")
        s.shot("script-running", wait=args.script_wait)
        s.shot("script-done", wait=25.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            if subprocess.run(["hmount", written], capture_output=True,
                              env=env).returncode == 0:
                out = subprocess.run(["hls", "-l", (VOL + ":Out:").encode()],
                                     capture_output=True, env=env)
                print("=== Out:")
                for line in out.stdout.decode("mac-roman",
                                              "replace").splitlines():
                    print("  " + line.strip())
                for n in ("Out:" + item, "UnStatus.out"):
                    subprocess.run(
                        ["hcopy", "-m", (VOL + ":" + n).encode(),
                         os.path.join(outdir,
                                      n.split(":")[-1] + ".bin").encode()],
                        capture_output=True, env=env)
                subprocess.run(["humount"], capture_output=True, env=env)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        time.sleep(4)
        s.close()
    st = os.path.join(outdir, "UnStatus.out.bin")
    if os.path.exists(st):
        data, _r = forks(st)
        print("=== UnStatus.out")
        for line in data.decode("mac-roman", "replace").split("\r"):
            if line.strip():
                print("  " + line)
    got = os.path.join(outdir, item + ".bin")
    ref = args.against or os.path.join(SPECIMENS, "paintmake",
                                       "Painting.bin")
    if os.path.exists(got) and os.path.exists(ref):
        gd, gr = forks(got)
        rd, rr = forks(ref)
        print("=== what the application restored")
        print("  data %d B (the subject is %d), identical: %s"
              % (len(gd), len(rd), gd == rd))
        print("  rsrc %d B (the subject is %d), identical: %s"
              % (len(gr), len(rr), gr == rr))
        if gd != rd and len(gd) == len(rd) and rd:
            n = sum(1 for i in range(len(rd)) if gd[i] != rd[i])
            print("  same length, %d of %d bytes differ" % (n, len(rd)))
    else:
        print("sitopt: nothing came back in Out:")
    return 0


PROBE_BIN = os.path.join(REPO, "build", "dcmptest", "DcmpTest.bin")


def phase_dcmp(args):
    """Run `tools/vmac/dcmptest` against an installed Optimizer.

    Launched AS THE FINDER, the way `traptest` is: the volume window has
    a dozen icons by now and type-select has already renamed an
    application once on this image. Booting straight into the probe
    needs no navigation at all.
    """
    if not os.path.exists(PROBE_BIN):
        raise SystemExit(
            "sitopt: no %s — build it:\n"
            "  cmake -B build/dcmptest -S tools/vmac/dcmptest "
            "-DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/"
            "retro68.toolchain.cmake && cmake --build build/dcmptest"
            % PROBE_BIN)
    base = args.image or BOOT
    img = os.path.join(WORK, "run-dcmp.hfv")
    shutil.copyfile(base, img)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        hfs(env, "hmount", img)
        sysf = VOL + ":System Folder:"
        subprocess.run(["hrename", (sysf + "Finder").encode(),
                        (sysf + "TheFinder").encode()],
                       capture_output=True, env=env)
        got = hfs(env, "hcopy", "-m", PROBE_BIN, sysf.encode())
        if got.returncode != 0:
            raise SystemExit("sitopt: hcopy of the probe failed")
        subprocess.run(["hrename", (sysf + "DcmpTest").encode(),
                        (sysf + "Finder").encode()],
                       capture_output=True, env=env)
        hfs(env, "humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    s = Session(img, [], os.path.join(SPECIMENS, args.tag), mem=args.emu)
    try:
        s.boot()
        s.shot("probe", wait=20.0)
        s.shot("probe-settled", wait=25.0)
    finally:
        time.sleep(3)
        s.close()
    print("sitopt: shots in %s" % os.path.join(SPECIMENS, args.tag))
    return 0


# The image --dcmpdata boots: `Painting` in the root and `MacPaint 1`
# installed. --paint made it and --makepaint kept it.
PAINTMADE = os.path.join(WORK, "sitopt-paintmade.hfv")


def remnant(data):
    """What an optimized MacPaint entry stores, from the module's own code.

    `MacPaint 1`'s 'COMP' copies the document from offset 512 to the end
    into a temp file starting at offset 4, then writes that file's own
    length into the first four bytes; its 'DCMP' reads the same file back
    from offset 4 and writes it to the rebuilt document at 512, after
    512 bytes it never initialises. So the remnant is the artwork with a
    length in front of it, and the header is what the Optimizer throws
    away (FORMATS.md, *What a module gives back*).
    """
    art = data[512:]
    return (4 + len(art)).to_bytes(4, "big") + art


def phase_dcmpdata(args):
    """Drive `MacPaint 1`'s DATA PATH, both halves, on a Macintosh.

    A round trip: the 'COMP' is handed the document and makes the
    remnant, and the 'DCMP' is handed a CInfoPBRec for a fresh file and
    that remnant in chunks. Nothing this harness built goes into either
    module — it only grades what comes out, against the document and
    against what StuffIt Deluxe 2.0.1's own unstuffer produced from the
    same archive (`specimens/sitopt/unapp3`).
    """
    if not os.path.exists(PROBE_BIN):
        raise SystemExit(
            "sitopt: no %s — build it:\n"
            "  cmake -B build/dcmptest -S tools/vmac/dcmptest "
            "-DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/"
            "retro68.toolchain.cmake && cmake --build build/dcmptest"
            % PROBE_BIN)
    base = args.image or PAINTMADE
    if not os.path.exists(base):
        raise SystemExit("sitopt: no %s — --add-paint and --paint make it"
                         % base)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    img = os.path.join(WORK, "run-dcmpdata.hfv")
    shutil.copyfile(base, img)
    work = tempfile.mkdtemp(prefix="sitopt-")
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        hfs(env, "hmount", img)
        # The subject comes OFF the image, so the remnant is built from
        # the same bytes the module will be asked to rebuild.
        orig = os.path.join(work, "Painting.bin")
        got = hfs(env, "hcopy", "-m", (VOL + ":" + PAINT_DOC).encode(),
                  orig.encode())
        if got.returncode != 0:
            raise SystemExit("sitopt: no %s on %s" % (PAINT_DOC, base))
        data, rsrc = forks(orig)
        print("sitopt: %s is %d B data, %d B rsrc"
              % (PAINT_DOC, len(data), len(rsrc)))
        rem = remnant(data)
        print("sitopt: the remnant the COMP should make is %d B, first "
              "long %d" % (len(rem), int.from_bytes(rem[:4], "big")))
        sysf = VOL + ":System Folder:"
        subprocess.run(["hrename", (sysf + "Finder").encode(),
                        (sysf + "TheFinder").encode()],
                       capture_output=True, env=env)
        if hfs(env, "hcopy", "-m", PROBE_BIN, sysf.encode()).returncode != 0:
            raise SystemExit("sitopt: hcopy of the probe failed")
        subprocess.run(["hrename", (sysf + "DcmpTest").encode(),
                        (sysf + "Finder").encode()],
                       capture_output=True, env=env)
        hfs(env, "humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)

    s = Session(img, [], outdir, mem=args.emu)
    written = os.path.join(s.work, "boot.hfv")
    try:
        # **Not `s.boot()`.** That waits for three identical frames eight
        # seconds apart, and this screen never gives them: the probe
        # replaced the Finder and never called `InitCursor`, so System 6
        # leaves the WATCH up and spins it — it is there in the middle
        # of `01-report.png`. The settle ran its full timeout and
        # returned after the machine had powered off, and both frames of
        # two runs came back "You may now switch off your Macintosh
        # safely." A boot here is under a minute; wait for it by the
        # clock, and photograph the report while it is up.
        time.sleep(90.0)
        s.shot("report", wait=2.0)
        s.shot("report-again", wait=45.0)
        s.shot("off", wait=140.0)
    finally:
        time.sleep(4)
        s.close()

    # The probe calls _FlushVol and then loops; nothing shuts the machine
    # down, so that call is the only reason any of this is on the image.
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        if subprocess.run(["hmount", written], capture_output=True,
                          env=env).returncode != 0:
            print("sitopt: cannot mount the image the emulator wrote")
            return 1
        for name, as_ in (("Rebuilt", "Rebuilt"),
                          ("System Folder:Optimizers:Paint Temp 0",
                           "PaintTemp0")):
            dest = os.path.join(outdir, as_ + ".bin")
            if subprocess.run(["hcopy", "-m", (VOL + ":" + name).encode(),
                               dest.encode()], capture_output=True,
                              env=env).returncode != 0:
                print("sitopt: %-24s NOT on the volume" % name)
        subprocess.run(["humount"], capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    print("sitopt: shots and files in %s" % outdir)
    return grade_dcmpdata(outdir, data, rem)


def grade_dcmpdata(outdir, data, rem):
    """What the run has to show for itself.

    Three checks, and the first is the one that decides whether the data
    path is proven: the rebuilt document has to agree with what StuffIt
    Deluxe 2.0.1's own unstuffer produced from the same archive. It can
    only agree from offset 512 on — the 512 bytes before it are a stack
    frame the module never initialises, which is measured in the
    specimen and is why "byte-exact" is not the standard here.
    """
    bad = 0
    ref = os.path.join(SPECIMENS, "unapp3", "Painting.bin")
    got = os.path.join(outdir, "Rebuilt.bin")
    if not os.path.exists(got):
        print("sitopt: nothing was rebuilt")
        return 1
    gd, gr = forks(got)
    print("=== what the DCMP rebuilt")
    print("  data %d B (the original is %d)" % (len(gd), len(data)))
    print("  rsrc %d B" % len(gr))
    if len(gd) != len(data) or len(gr) != 0:
        print("  PROBLEM: the lengths are not the original's with no rsrc")
        bad += 1
    if gd[512:] == data[512:]:
        print("  artwork from 512 on: IDENTICAL to the original")
    else:
        print("  PROBLEM: the artwork does not match")
        bad += 1
    n = min(512, len(gd), len(data))
    print("  header: %d of %d bytes differ from the original"
          % (sum(1 for i in range(n) if gd[i] != data[i]), n))
    if os.path.exists(ref):
        rd, _rr = forks(ref)
        print("  vs StuffIt Deluxe's own unstuffed file:")
        print("    from 512 on: %s" % ("IDENTICAL" if gd[512:] == rd[512:]
                                       else "DIFFERENT"))
        if gd[512:] != rd[512:]:
            bad += 1
        n = min(512, len(gd), len(rd))
        print("    header: %d of %d bytes differ from its header"
              % (sum(1 for i in range(n) if gd[i] != rd[i]), n))
    else:
        print("  (no unapp3/Painting.bin to compare with)")
    tmp = os.path.join(outdir, "PaintTemp0.bin")
    if os.path.exists(tmp):
        td, _tr = forks(tmp)
        print("=== the remnant the COMP made, %d B" % len(td))
        if td == rem:
            print("  IDENTICAL to a length in front of the document"
                  " from 512 on")
        else:
            print("  PROBLEM: differs from the one this harness built")
            bad += 1
    else:
        print("=== the COMP's temp file did not come off the image")
    print("sitopt: %d problem(s)" % bad)
    return 1 if bad else 0


# ------------------------------------------------------------------
# Photoshop 1.0.7, and a document its own Optimizer can actually read
# ------------------------------------------------------------------
#
# `Photoshop/JPEG Lossy` refused the subject `--makemods` built for it,
# and so did StuffIt Deluxe itself (FORMATS.md). The subject was the
# problem: its data fork was a modern `8BPS` PSD wearing Photoshop 1.0's
# `8BIM` type, and the module reads an image's geometry out of the
# `8BIM` 1000 RESOURCE and its pixels out of the DATA fork raw. Given a
# document Photoshop 1.0 wrote, the same module round-trips it.
#
# The application is 1990 and its own page says "Macintosh SE or newer";
# it runs on Mini vMac's Mac Plus anyway, which is the only variant
# built here.
PS_URL = "https://old.mac.gdn/apps/AdobePhotoshop1.img_.sit"
PS_PAGE = "https://macintoshgarden.org/apps/photoshop-107"
PS_SIT = os.path.join(os.path.expanduser("~"), ".cache", "macextract",
                      "ps1", "AdobePhotoshop1.img_.sit")
PS_MD5 = "9993070033425d5e1fd291d1db7b0f5b"
PS_IMAGE = os.path.join(WORK, "sitopt-ps.hfv")
PS_APP = "Adobe Photoshop\u2122 1.0"
PS_DOC = "PSDoc"
# Where the application's icon sits in the volume window, and the
# PENCIL in its toolbox — the default tool is the marquee and the first
# run drew a selection rectangle instead of a line.
PS_ICON = (300, 172)
PS_PENCIL = (41, 180)


def ps_fetch():
    """The Mini vMac disk image of Photoshop 1.0.7, in the foreground —
    a backgrounded download on this machine stalls in poll()."""
    os.makedirs(os.path.dirname(PS_SIT), exist_ok=True)
    if not os.path.exists(PS_SIT):
        subprocess.run(["curl", "-fsSL", "-e", PS_PAGE, "-o", PS_SIT,
                        PS_URL], check=True)
    got = hashlib.md5(open(PS_SIT, "rb").read()).hexdigest()
    if got != PS_MD5:
        raise SystemExit("sitopt: %s is md5 %s, expected %s"
                         % (PS_SIT, got, PS_MD5))
    print("sitopt: Photoshop 1.0.7, md5 %s as recorded" % got)


def add_photoshop(args):
    """Photoshop 1.0.7 onto the image that has all five Optimizers.

    The download is a StuffIt archive of ONE DiskCopy image, which this
    project's own engine unwraps; the 84-byte header comes off the same
    way `--install` takes it off StuffIt's floppies.
    """
    ps_fetch()
    base = args.image or os.path.join(WORK, "sitopt-painted.hfv")
    if not os.path.exists(base):
        raise SystemExit("sitopt: no %s — --add-modules makes it" % base)
    work = tempfile.mkdtemp(prefix="sitopt-ps-")
    try:
        tree = os.path.join(work, "out")
        subprocess.run([CLI, "x", "-o", tree, PS_SIT], check=True,
                       capture_output=True)
        src = None
        for root, _d, files in os.walk(tree):
            for f in files:
                if f.endswith(".img"):
                    src = os.path.join(root, f)
        if not src:
            raise SystemExit("sitopt: no .img in %s" % PS_SIT)
        raw = os.path.join(work, "ps.dsk")
        open(raw, "wb").write(open(src, "rb").read()[84:])
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", raw)
            for name, dest in ((PS_APP, "app.bin"), ("PS Prefs", "prefs.bin")):
                got = subprocess.run(
                    ["hcopy", "-m", name.encode("mac_roman"),
                     os.path.join(work, dest).encode()],
                    capture_output=True, env=env)
                if got.returncode != 0:
                    raise SystemExit("sitopt: %s is not on the floppy" % name)
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.copyfile(base, PS_IMAGE)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", PS_IMAGE)
            for dest in ("app.bin", "prefs.bin"):
                hfs(env, "hcopy", "-m", os.path.join(work, dest),
                    (VOL + ":").encode())
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("sitopt: Photoshop 1.0.7 is on %s" % PS_IMAGE)
    return 0


def stroke(x, ox, oy, pts):
    """One pencil stroke through `pts`. A classic application joins
    successive mouse positions, so a straight line needs two of them and
    not one per pixel — which is the difference between a 40-second
    drawing and a four-minute one."""
    x("mousemove", str(ox + pts[0][0]), str(oy + pts[0][1]))
    time.sleep(0.25)
    x("mousedown", "1")
    for px, py in pts[1:]:
        x("mousemove", str(ox + px), str(oy + py))
        time.sleep(0.06)
    x("mouseup", "1")
    time.sleep(0.3)


def draw(s, which):
    """Draw in the canvas with the pencil.

    `zigzag` is the original: five wavy strokes on white, which leaves
    most of the image flat — 2 distinct byte values in the document and
    58 after the module had been through it.

    `grid` is the second subject, and it is chosen for the ARITHMETIC
    rather than for looking like anything: a 6-pixel comb against a
    12-pixel one puts an edge in nearly every 8x8 block, in both
    directions at once, so the blocks carry AC energy everywhere
    instead of in five bands. That is what multiplies the number of
    times the output stage rounds a negative value, which is the one
    question a second image is for (FORMATS.md, *What an Optimizer did
    to the fork*).
    """
    ox, oy = s.mac.origin()
    x = s.mac._xdo
    if which == "zigzag":
        for row in (110, 140, 170, 200, 230):
            stroke(x, ox, oy, [(px, row + ((px // 8) % 7) * 3)
                               for px in range(100, 300, 8)])
        return
    for row in range(105, 239, 6):                  # the horizontal comb
        stroke(x, ox, oy, [(100, row), (300, row)])
    for col in range(100, 301, 12):                 # and the vertical one
        stroke(x, ox, oy, [(col, 105), (col, 238)])
    stroke(x, ox, oy, [(100, 105), (300, 238)])     # two diagonals, which
    stroke(x, ox, oy, [(300, 105), (100, 238)])     # no block can predict


def phase_psdoc(args):
    """Draw in Photoshop 1.0.7 and save its NATIVE document.

    256x256 RGB rather than the dialog's 512: a quarter of the pixels is
    a quarter of every later step on a 7 MHz machine, and the point is a
    real `8BIM` file, not a big one. What comes off is 196,608 bytes of
    raw pixels — 256*256*3, no header at all — with the geometry in an
    `8BIM` 1000 resource of ten bytes, which is the resource the
    Optimizer's acceptance test reads.
    """
    img = os.path.join(WORK, "run-psdoc.hfv")
    if not os.path.exists(PS_IMAGE):
        raise SystemExit("sitopt: no %s — --add-photoshop makes it" % PS_IMAGE)
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        s.boot()
        s.mac.click(*BOOT_ICON, double=True)
        time.sleep(14)
        s.mac.click(*PS_ICON)
        time.sleep(3)
        s.mac.command_key("o")
        s.shot("launched", wait=90.0)
        s.mac.command_key("n")
        time.sleep(8)
        s.mac._xdo("type", "--delay", "140", "256")
        s.mac.key("Tab")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "140", "256")
        s.shot("new-dialog", wait=3.0)
        s.mac.key("Return")
        s.shot("new-doc", wait=20.0)
        s.mac.click(*PS_PENCIL)
        s.shot("pencil", wait=3.0)
        draw(s, args.drawing)
        s.shot("drawn", wait=4.0)
        s.mac.command_key("s")
        time.sleep(12)
        s.mac._xdo("type", "--delay", "140", args.psname)
        s.shot("save-named", wait=3.0)
        s.mac.key("Return")
        s.shot("saved", wait=25.0)
        s.mac.command_key("q")
        s.shot("quit", wait=25.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        read_one(os.path.join(s.work, "boot.hfv"), args.psname, outdir)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


PSJ_SCRIPT_NAME = "Zpsjpeg"


def psj_script(doc):
    """The round trip, for whichever document --psname names."""
    return "\r".join([
        "; written by tools/vmac/sitopt.py",
        'Write Status To "{Startup}PSStatus.out"',
        "Continue On Error",
        "; the control first, with no Optimizer enabled",
        'New Archive "{Startup}PlainPS.sit"',
        'Stuff "{Startup}%s" with fast' % doc,
        "Close",
        'Enable Optimizer "Photoshop/JPEG Lossy"',
        'New Archive "{Startup}JpegPS.sit"',
        'Stuff "{Startup}%s" with fast' % doc,
        "Close",
        'Disable Optimizer "Photoshop/JPEG Lossy"',
        "; and ask for the same document straight back",
        'Destination "{Startup}Out:"',
        'Open Archive "{Startup}JpegPS.sit"',
        'UnStuff "*"',
        "Close",
        "Quit",
        "",
    ])


def phase_psjpeg(args):
    """Stuff a REAL Photoshop document with `JPEG Lossy` and unstuff it,
    in one boot — the round trip the synthetic subject could not do."""
    doc = os.path.join(SPECIMENS, args.against or "psdoc",
                       args.psname + ".bin")
    if not os.path.exists(doc):
        raise SystemExit("sitopt: no %s — --psdoc makes it" % doc)
    if not os.path.exists(PS_IMAGE):
        raise SystemExit("sitopt: no %s — --add-photoshop makes it" % PS_IMAGE)
    img = os.path.join(WORK, "run-psjpeg.hfv")
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sitopt-psj-")
    try:
        mb = os.path.join(work, "script.bin")
        open(mb, "wb").write(macbinary(
            PSJ_SCRIPT_NAME, "TEXT", "SIT!",
            psj_script(args.psname).encode("mac_roman")))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            hfs(env, "hcopy", "-m", doc, (VOL + ":").encode())
            hfs(env, "hcopy", "-m", mb, (VOL + ":").encode())
            subprocess.run(["hmkdir", (VOL + ":Out").encode()],
                           capture_output=True, env=env)
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        s.boot()
        launch(s, args)
        if args.quality:
            s.menu(EDIT_X, EDIT_SWITCH_Y, "expert-menus")
            set_jpeg_quality(s, args.quality)
        s.peek(SCRIPTS_X, "scripts-menu")
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Zps")
        s.shot("script-selected", wait=3.0)
        s.mac.key("Return")
        s.shot("running", wait=args.script_wait)
        s.shot("done", wait=45.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        for n in ("PlainPS.sit", "JpegPS.sit", "PSStatus.out",
                  "Out:" + args.psname):
            read_one(written, n, outdir)
    finally:
        time.sleep(3)
        s.close()
    got = os.path.join(outdir, args.psname + ".bin")
    if os.path.exists(got):
        od, orr = forks(doc)
        gd, gr = forks(got)
        print("=== what `JPEG Lossy` gave back")
        print("  data %d B (in: %d), identical: %s"
              % (len(gd), len(od), gd == od))
        print("  rsrc %d B (in: %d), identical: %s"
              % (len(gr), len(orr), gr == orr))
        if len(gd) == len(od) and gd != od:
            n = sum(1 for i in range(len(od)) if gd[i] != od[i])
            print("  %d of %d pixel bytes differ (%.1f%%) — it is LOSSY"
                  % (n, len(od), 100.0 * n / len(od)))
    return show_path(outdir)


MX_SCRIPT_NAME = "Zpsmatrix"
MX_METHODS = ("faster", "better", "optimal")
MX_ARCHIVES = tuple("J%s.sit" % m.capitalize() for m in MX_METHODS)


def mx_script(doc):
    """The same document through every compression method the script
    language has, with `JPEG Lossy` enabled throughout.

    The question is whether an optimized fork is always STORED. The
    engine reads the method nibble of an optimized entry and decodes
    C-Cube's payload out of the stored bytes (`src/fmt_sit.c`); if 2.0.1
    will compress an Optimizer's output as well, that path needs the
    remnant decompressed first, and nothing here has ever asked it for
    anything but `fast`. `optimal` is the application's own "try them
    and keep the smallest", so it is the one most likely to say yes.

    One UnStuff, not three: the restored file is the oracle and the
    three archives should produce the same one, which is itself worth
    asserting.
    """
    out = ["; written by tools/vmac/sitopt.py",
           'Write Status To "{Startup}MxStatus.out"',
           "Continue On Error",
           'Enable Optimizer "Photoshop/JPEG Lossy"']
    for m, arc in zip(MX_METHODS, MX_ARCHIVES):
        out += ['New Archive "{Startup}%s"' % arc,
                'Stuff "{Startup}%s" with %s' % (doc, m),
                "Close"]
    out += ['Disable Optimizer "Photoshop/JPEG Lossy"',
            'Destination "{Startup}Out:"',
            'Open Archive "{Startup}%s"' % MX_ARCHIVES[1],
            'UnStuff "*"',
            "Close", "Quit", ""]
    return "\r".join(out)


# The Options menu of the REGISTERED 2.0.1, measured off
# `specimens/sitopt/psmenus1/12-menu-x230.png` by counting ink per row
# rather than by eye: items are 16 px apart from y=28, with separators
# at 140 and 172.
OPTIONS_X = 230
OPT_OPTIMIZERS_Y = 156          # "Compression Optimizers…"
OPT_CUSTOM_ENC_Y = 236          # "Custom Encryption…"
# Cancel, off `psopts1/07-dialog-optimizers.png`. **Neither ⌘. nor
# Escape dismisses these dialogs** — measured 2026-10-02, when both were
# tried and the next shot was the same dialog still up, so the run's
# second menu action never happened and photographed it again. A 1990
# modal wants its button clicked.
OPT_CANCEL = (211, 299)


# The two dialogs' own geometry, off `specimens/sitopt/psopts2`.
OPT_OK = (295, 299)             # the Optimizers dialog
ENC_PASSLOCK = (170, 76)        # the first row of the encryptor list
ENC_OK = (340, 285)
ENC_CANCEL = (340, 312)
# The JPEG module's row in the Optimizers list: Text 1, Sound 1,
# Photoshop/JPEG Lossy, Photoshop 1, MacPaint 1 at 16 px from y=84, and
# the checkmark column is to the LEFT of the name (x=145 in the shot).
OPT_JPEG_ROW = (200, 120)

ENC_SCRIPT_NAME = "Zpsenc"
ENC_SCRIPT = "\r".join([
    "; written by tools/vmac/sitopt.py",
    'Write Status To "{Startup}EncStatus.out"',
    "Continue On Error",
    'Enable Optimizer "Photoshop/JPEG Lossy"',
    'New Archive "{Startup}EncJpeg.sit"',
    'Stuff "{Startup}PSDoc2" with fast',
    "Close",
    "Quit",
    "",
])


ENC_ARCHIVE = "EncG.sit"

# The JPEG module's OWN dialog, which opens when its row in the
# Optimizers list is clicked — measured off
# `specimens/sitopt/psenc2/21-stuffed.png`. It says: "Please specify the
# JPEG quantization level to use. Values of 20 to 30 are recommended.
# Values over 30 cause image degradation.", a Q field, a "Prompt for Q
# on each file." checkbox and OK. So the quality IS settable, and 25 is
# only its default — which is the opposite of what the activation list
# alone suggested.
JPEG_Q_FIELD = (398, 219)       # focused and SELECTED when it opens:
                                # typing replaces, clicking would append
JPEG_Q_PROMPT = (205, 253)      # "Prompt for Q on each file."
JPEG_Q_OK = (256, 278)


def set_jpeg_quality(s, q):
    """Open the Optimizers list, click the JPEG module, set Q, come back.

    Nothing is typed into the Q field after a click: the field comes up
    with its contents selected, so the first keystroke replaces them —
    measured the hard way, when a run that typed a file name while this
    dialog was up left `PSDoc2` in the quantization field and swallowed
    every keystroke after it (`specimens/sitopt/psenc2`).
    """
    s.menu(OPTIONS_X, OPT_OPTIMIZERS_Y, "menu-optimizers")
    s.shot("opt-dialog", wait=8.0)
    s.mac.click(*OPT_JPEG_ROW)
    s.shot("module-dialog", wait=6.0)
    s.mac._xdo("type", "--delay", "160", str(q))
    s.shot("q-typed", wait=3.0)
    s.mac.click(*JPEG_Q_PROMPT)         # stop it asking per file
    s.shot("q-no-prompt", wait=2.0)
    s.mac.click(*JPEG_Q_OK)
    s.shot("q-ok", wait=5.0)
    s.mac.click(*OPT_OK)
    s.shot("opt-closed", wait=5.0)


def opt_encryptors(work):
    """The optional disk's encryptor modules, extracted HERE rather than
    read out of a cache.

    `~/.cache/macextract/sit2/opt/` holds a copy from an earlier
    session, and on 2026-10-02 it was 82 bytes longer than the archive's
    own `NewDEx` and did not parse as a resource fork at all — so the
    module installed from it was ignored by the application, and the
    Custom Encryption list still showed one name. Extracting on every
    run costs a second and cannot go stale. The ids are the proof it
    worked: a module's 'COMP'/'DCMP' id is `(kind - 1) << 8 | id`, so
    NewDEx is 515 and DESex 576.
    """
    if not os.path.exists(OPT_SIT):
        raise SystemExit("sitopt: no %s — --setup fetches it" % OPT_SIT)
    out = os.path.join(work, "optional")
    subprocess.run([CLI, "x", "-o", out, OPT_SIT], check=True,
                   capture_output=True)
    for root, _dirs, files in os.walk(out):
        if os.path.basename(root) == "Encryptors":
            return root
    raise SystemExit("sitopt: no Encryptors folder in %s" % OPT_SIT)
ENC_ROWS = (76, 92, 108)        # the list, 16 px apart from the first


def phase_psex(args):
    """Install `NewDEx` and `DESex` and make an archive with each.

    They are the optional disk's ENCRYPTOR MODULES — `deluxe-2-optional.sit`,
    which this project has — and nothing here has ever had an archive
    from either, so `src/fmt_sit.c` refuses ids 3 and 64 by name. The
    built-in `DES` and `NewDE` are decoded (FORMATS.md, *The three ways
    2.0.1 encrypts*), and the obvious question is whether the modules
    are the same two ciphers packaged differently.

    One archive per row of the Custom Encryption list, named by ROW
    rather than by module: the dialog's order is not known in advance,
    and the entry header's own encryptor id says which module wrote it
    (2 PassLock, 3 NewDEx, 64 DESex). The subject is `Subject`, which
    the image already carries, so a plain archive of it from any other
    run is the plaintext.
    """
    img = os.path.join(WORK, "run-psex.hfv")
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sitopt-ex-")
    try:
        encdir = opt_encryptors(work)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            for mod in ("NewDEx", "DESex"):
                rsrc = os.path.join(encdir, mod + ".rsrc")
                if not os.path.exists(rsrc):
                    raise SystemExit("sitopt: no %s in the optional disk's "
                                     "payload" % mod)
                mb = os.path.join(work, mod + ".bin")
                # Resource fork only, like `PassLock`: these modules have
                # no data fork at all.
                open(mb, "wb").write(macbinary(mod, "SITe", "SIT!", b"",
                                               open(rsrc, "rb").read()))
                hfs(env, "hcopy", "-m", mb,
                    (VOL + ":System Folder:Encryptors:").encode())
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.menu(EDIT_X, EDIT_SWITCH_Y, "expert-menus")
        for n, y in enumerate(ENC_ROWS):
            tag = "ABC"[n]
            s.menu(OPTIONS_X, OPT_CUSTOM_ENC_Y, "menu-enc-%s" % tag)
            s.shot("enc-list-%s" % tag, wait=8.0)
            s.mac.click(ENC_PASSLOCK[0], y)
            s.shot("enc-picked-%s" % tag, wait=3.0)
            s.mac.click(*ENC_OK)
            s.shot("enc-armed-%s" % tag, wait=5.0)
            s.mac.command_key("n")
            s.shot("new-%s" % tag, wait=10.0)
            s.mac._xdo("type", "--delay", "140", "Enc" + tag)
            s.mac.key("Return")
            s.shot("made-%s" % tag, wait=12.0)
            s.mac.command_key("s")
            s.shot("stuff-%s" % tag, wait=10.0)
            s.mac._xdo("type", "--delay", "140", "Subject")
            s.mac.key("Return")
            s.shot("stuffing-%s" % tag, wait=10.0)
            for _ in (1, 2):
                s.mac._xdo("type", "--delay", "140", args.password)
                s.mac.key("Return")
                s.shot("pw-%s" % tag, wait=8.0)
            s.shot("stuffed-%s" % tag, wait=20.0)
            s.mac.command_key("w")
            s.shot("closed-%s" % tag, wait=8.0)
        s.mac.command_key("q")
        s.shot("quit", wait=15.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        for n in ("EncA.sit", "EncB.sit", "EncC.sit"):
            read_one(written, n, outdir)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


SEA_SCRIPT_NAME = "Zsea"
SEA_SCRIPT = "\r".join([
    "; written by tools/vmac/sitopt.py",
    'Write Status To "{Startup}SeaStatus.out"',
    "Continue On Error",
    'New Archive "{Startup}RSea3.sit"',
    'Stuff "{Startup}Subject" with fast',
    'Save As "{Startup}RSea3.sea" Self-UnStuffing',
    "Close",
    "Quit",
    "",
])


def unstuffer(work):
    """`UnStuffIt Deluxe™`, out of its own installer on disk 2.

    `Save As … Self-UnStuffing` is the right syntax — the status file
    says *"(Self-UnStuffing option)"* — and 2.0.1 then answers *"No
    Self-UnStuffer can be found that supports this archive"*, because
    the box installs that half separately. The installer's DATA fork is
    a StuffIt archive, the same shape as disk 1's, so the application
    inside it is lifted out here rather than by running an installer
    under the emulator.
    """
    d2 = os.path.join(CACHE, "v2", "StuffIt Deluxe v2",
                      "StuffIt Deluxe\u2122 Disk 2.image")
    if not os.path.exists(d2):
        raise SystemExit("sitopt: no %s — --setup fetches it" % d2)
    raw = os.path.join(work, "disk2.dsk")
    open(raw, "wb").write(open(d2, "rb").read()[84:])   # the DiskCopy header
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    inst = os.path.join(work, "unstuffinst.bin")
    try:
        hfs(env, "hmount", raw)
        hfs(env, "hcopy", "-m",
            "UnStuffIt Deluxe\u2122 Installer".encode("mac_roman"), inst)
        hfs(env, "humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    data = os.path.join(work, "inst.data")
    blob = open(inst, "rb").read()
    dlen = struct.unpack(">I", blob[83:87])[0]
    open(data, "wb").write(blob[128:128 + dlen])
    out = os.path.join(work, "ustree")
    subprocess.run([CLI, "x", "-o", out, data], check=True, capture_output=True)
    for root, _dirs, files in os.walk(out):
        for f in files:
            if f.startswith("UnStuffIt Deluxe") and not f.endswith(".rsrc"):
                return os.path.join(root, f)
    raise SystemExit("sitopt: no UnStuffIt Deluxe in the disk 2 installer")


def phase_pssea(args):
    """A SELF-EXTRACTING archive, which needs the other half of the box."""
    img = os.path.join(WORK, "run-pssea.hfv")
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sitopt-sea-")
    try:
        us = unstuffer(work)
        mb = os.path.join(work, "script.bin")
        open(mb, "wb").write(macbinary(SEA_SCRIPT_NAME, "TEXT", "SIT!",
                                       SEA_SCRIPT.encode("mac_roman")))
        usb = os.path.join(work, "us.bin")
        open(usb, "wb").write(macbinary(
            "UnStuffIt Deluxe\u2122", "APPL", "USTD",
            open(us, "rb").read(),
            open(us + ".rsrc", "rb").read()))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            hfs(env, "hcopy", "-m", mb, (VOL + ":").encode())
            # Loose on the volume AND in the System Folder: STR# 267's
            # "9 Magic Fldrs" is where the application looks, and which
            # of them holds a self-unstuffer is not written down here.
            hfs(env, "hcopy", "-m", usb, (VOL + ":").encode())
            hfs(env, "hcopy", "-m", usb,
                (VOL + ":System Folder:").encode())
            # STR# 267's eight folders are Preferences, Help, Viewers,
            # Compressors, Encryptors, Optimizers, Translators and
            # Extensions — none of them for a self-unstuffer, so the
            # third copy goes where the Engine lives and the fourth
            # beside the application, which is the only other place a
            # 1990 application looks.
            subprocess.run(["hmkdir",
                            (VOL + ":System Folder:Extensions").encode()],
                           capture_output=True, env=env)
            hfs(env, "hcopy", "-m", usb,
                (VOL + ":System Folder:Extensions:").encode())
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Zsea")
        s.mac.key("Return")
        s.shot("running", wait=args.script_wait)
        s.shot("done", wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        for n in ("RSea3.sea", "RSea3.sit", "SeaStatus.out"):
            read_one(written, n, outdir)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


FOLD_SCRIPT_NAME = "Zfold"
FOLD_SCRIPT = "\r".join([
    "; written by tools/vmac/sitopt.py",
    'Write Status To "{Startup}FoldStatus.out"',
    "Continue On Error",
    "; a FOLDER, which puts folder markers in the entry stream",
    'New Archive "{Startup}RFold.sit"',
    'Stuff "{Startup}Papers" with fast',
    "Close",
    "; and a self-extracting one, through Save As rather than New",
    'New Archive "{Startup}RSea2.sit"',
    'Stuff "{Startup}Subject" with fast',
    'Save As "{Startup}RSea2.sea" Self-UnStuffing',
    "Close",
    "Quit",
    "",
])


def phase_psfold(args):
    """A folder and a self-extractor — the last two shapes.

    `--psrest` asked for both and got neither: the folder it named is
    not on this image, and `New Archive … Self-UnStuffing` came back
    *"Unknown Option"*. So the folder is MADE here first, with two files
    in it, and the self-extractor goes through `Save As`, which is the
    other word STR# 257 has for it. Disk 2 of the box carries an
    `UnStuffIt Deluxe™ Installer` and nothing here has run it, so the
    likely answer is the application's own *"No Self-UnStuffer can be
    found"* — which is an answer, and the status file will say it.
    """
    img = os.path.join(WORK, "run-psfold.hfv")
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sitopt-fold-")
    try:
        mb = os.path.join(work, "script.bin")
        open(mb, "wb").write(macbinary(FOLD_SCRIPT_NAME, "TEXT", "SIT!",
                                       FOLD_SCRIPT.encode("mac_roman")))
        one = os.path.join(work, "one.bin")
        two = os.path.join(work, "two.bin")
        open(one, "wb").write(macbinary("First", "TEXT", "ttxt",
                                        b"the first file in the folder\r" * 4,
                                        make_rsrc()))
        open(two, "wb").write(macbinary("Second", "TEXT", "ttxt",
                                        b"and the second\r" * 7, b""))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            hfs(env, "hcopy", "-m", mb, (VOL + ":").encode())
            subprocess.run(["hmkdir", (VOL + ":Papers").encode()],
                           capture_output=True, env=env)
            for f in (one, two):
                hfs(env, "hcopy", "-m", f, (VOL + ":Papers:").encode())
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Zfold")
        s.mac.key("Return")
        s.shot("running", wait=args.script_wait)
        s.shot("done", wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        for n in ("RFold.sit", "RSea2.sit", "RSea2.sea", "FoldStatus.out"):
            read_one(written, n, outdir)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


REST_SCRIPT_NAME = "Zrest"
REST_SCRIPT = "\r".join([
    "; written by tools/vmac/sitopt.py",
    'Write Status To "{Startup}RestStatus.out"',
    "Continue On Error",
    "; every compression word left: `guess` is the menu's Best Guess",
    'New Archive "{Startup}RGuess.sit"',
    'Stuff "{Startup}Subject" with guess',
    "Close",
    'New Archive "{Startup}RNone.sit"',
    'Stuff "{Startup}Subject" with none',
    "Close",
    "; a 1.5.1-compatible archive, which is a FORMAT and not a method",
    'New Archive "{Startup}R151.sit" 1.5.1',
    'Stuff "{Startup}Subject" with fast',
    "Close",
    "; a FOLDER, so the entry stream carries folder markers",
    'New Archive "{Startup}RFolder.sit"',
    'Stuff "{Startup}Tutorial Files" with fast',
    "Close",
    "; and a self-unstuffing one",
    'New Archive "{Startup}RSea.sit" Self-UnStuffing',
    'Stuff "{Startup}Subject" with fast',
    "Close",
    "Quit",
    "",
])


def phase_psrest(args):
    """Ask 2.0.1 for everything it can still be asked for.

    What is left after the Optimizers, the ciphers and the four
    compression words this project has measured: `guess` (the menu's
    Best Guess), `none`, a **1.5.1-compatible** archive, a FOLDER, and a
    **self-unstuffing** one. Each is a shape the engine may or may not
    read, and `Continue On Error` means a line the script language does
    not accept is logged and the run goes on — so a wrong guess at the
    syntax costs a line of the status file rather than the boot.
    """
    img = os.path.join(WORK, "run-psrest.hfv")
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sitopt-rest-")
    try:
        mb = os.path.join(work, "script.bin")
        open(mb, "wb").write(macbinary(REST_SCRIPT_NAME, "TEXT", "SIT!",
                                       REST_SCRIPT.encode("mac_roman")))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            hfs(env, "hcopy", "-m", mb, (VOL + ":").encode())
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Zrest")
        s.mac.key("Return")
        s.shot("running", wait=args.script_wait)
        s.shot("done", wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        for n in ("RGuess.sit", "RNone.sit", "R151.sit", "RFolder.sit",
                  "RSea.sit", "RestStatus.out"):
            read_one(written, n, outdir)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


DES_SCRIPT_NAME = "Zdes"
DES_SCRIPT = "\r".join([
    "; written by tools/vmac/sitopt.py",
    'Write Status To "{Startup}DesStatus.out"',
    "Continue On Error",
    'New Archive "{Startup}DesT.sit"',
    'Stuff "{Startup}Subject" with fast des',
    "Close",
    'New Archive "{Startup}NewdeT.sit"',
    'Stuff "{Startup}Subject" with fast newde',
    "Close",
    "; and the control, with the same subject and no security word",
    'New Archive "{Startup}NoneT.sit"',
    'Stuff "{Startup}Subject" with fast',
    "Close",
    "Quit",
    "",
])


def phase_psdes(args):
    """Are `NewDE™` and `DES` modules, or are they built in?

    The Options menu lists them as items of their own BESIDE `Custom
    Encryption…`, which is the plug-in route and the only one that
    reaches `PassLock`. STR# 257 has `des` and `newde` as script words,
    so a script can ask for them by name — which this does, with a
    control in the same boot. Two outcomes and both are answers: an
    archive, which means the application carries the cipher and this
    project can grade a 1990 encrypted archive at last; or
    `* * * Encryptor Not Found:` in the status file, which means they
    are modules Aladdin shipped separately and this machine has
    neither.

    `tools/vmac/README.md` records the claim this is testing: that a
    script cannot encrypt. That was measured for the MENU's setting and
    ASSUMED for these two words, which is not the same thing.
    """
    img = os.path.join(WORK, "run-psdes.hfv")
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sitopt-des-")
    try:
        mb = os.path.join(work, "script.bin")
        open(mb, "wb").write(macbinary(DES_SCRIPT_NAME, "TEXT", "SIT!",
                                       DES_SCRIPT.encode("mac_roman")))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            hfs(env, "hcopy", "-m", mb, (VOL + ":").encode())
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Zdes")
        s.mac.key("Return")
        # A password dialog, if either word reaches a cipher, is the
        # application's and arrives mid-script; type into it blind and
        # photograph, the way --psenc does.
        for n in (1, 2, 3, 4):
            s.shot("running%d" % n, wait=12.0)
            s.mac._xdo("type", "--delay", "140", args.password)
            s.mac.key("Return")
        s.shot("done", wait=45.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        for n in ("DesT.sit", "NewdeT.sit", "NoneT.sit", "DesStatus.out"):
            read_one(written, n, outdir)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


ENCT_SCRIPT_NAME = "Zenct"
ENCT_SCRIPT = "\r".join([
    "; written by tools/vmac/sitopt.py",
    'Write Status To "{Startup}EncTStatus.out"',
    "Continue On Error",
    'New Archive "{Startup}PlainT.sit"',
    'Stuff "{Startup}Subject" with fast',
    "Close",
    "Quit",
    "",
])
ENCT_ARCHIVE = "EncT"           # the save field already carries ".sit"


def phase_enctext(args):
    """Does `PassLock` encrypt ANYTHING? The control for the first one.

    The archive `--psencgui` wrote has both forks byte-identical to the
    unencrypted archive of the same document, plus 23 bytes on each —
    7 of padding and 16 of key — so on that evidence the module is
    password PROTECTION and not encryption. One archive is not a
    format, and the first one was an optimized, STORED fork, so this
    asks again with an ordinary text file and a compressed method: the
    same subject, password-protected through the application's own
    Stuff, and a plain archive of it from a script in the same boot.
    """
    img = os.path.join(WORK, "run-enctext.hfv")
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sitopt-enct-")
    try:
        mb = os.path.join(work, "script.bin")
        open(mb, "wb").write(macbinary(ENCT_SCRIPT_NAME, "TEXT", "SIT!",
                                       ENCT_SCRIPT.encode("mac_roman")))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            hfs(env, "hcopy", "-m", mb, (VOL + ":").encode())
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.menu(EDIT_X, EDIT_SWITCH_Y, "expert-menus")
        # the protected one, through the application's own Stuff
        s.menu(OPTIONS_X, OPT_CUSTOM_ENC_Y, "menu-encryption")
        s.shot("enc-dialog", wait=8.0)
        s.mac.click(*ENC_PASSLOCK)
        s.mac.click(*ENC_OK)
        s.shot("enc-armed", wait=5.0)
        s.mac.command_key("n")
        s.shot("new-archive", wait=10.0)
        s.mac._xdo("type", "--delay", "140", ENCT_ARCHIVE)
        s.mac.key("Return")
        s.shot("archive-made", wait=12.0)
        s.mac.command_key("s")
        s.shot("stuff-dialog", wait=10.0)
        s.mac._xdo("type", "--delay", "140", "Subject")
        s.shot("subject-selected", wait=4.0)
        s.mac.key("Return")
        s.shot("stuff-return", wait=10.0)
        for n in (1, 2):
            s.mac._xdo("type", "--delay", "140", args.password)
            s.mac.key("Return")
            s.shot("password%d" % n, wait=8.0)
        s.shot("stuffed", wait=25.0)
        s.mac.command_key("w")
        s.shot("closed", wait=8.0)
        # and the control, from a script, which cannot encrypt
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Zenct")
        s.mac.key("Return")
        s.shot("script-done", wait=45.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        for n in ("EncT.sit", "PlainT.sit", "EncTStatus.out"):
            read_one(written, n, outdir)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


def phase_psencgui(args):
    """The same archive through the APPLICATION's own Stuff, because the
    script's cannot be encrypted.

    Measured 2026-10-02 (`specimens/sitopt/psenc1`): arming `PassLock`
    from Options ▸ Custom Encryption… ticks that item — the menu
    photograph after the run shows it — and a scripted `Stuff … with
    fast` then writes an archive byte-for-byte the shape of an
    unencrypted one, with no prompt and no error. The script language's
    security words are `newde` and `des` (STR# 257) and neither names an
    installed encryptor, so a script cannot ask for the one that is
    here. The interactive Stuff can: File ▸ New Archive… (⌘N), then
    Archive ▸ Stuff… (⌘S), and PassLock asks for the password itself.
    """
    doc = os.path.join(SPECIMENS, args.against or "psdoc2",
                       args.psname + ".bin")
    if not os.path.exists(doc):
        raise SystemExit("sitopt: no %s — --psdoc makes it" % doc)
    img = os.path.join(WORK, "run-psencgui.hfv")
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        hfs(env, "hmount", img)
        hfs(env, "hcopy", "-m", doc, (VOL + ":").encode())
        hfs(env, "humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.menu(EDIT_X, EDIT_SWITCH_Y, "expert-menus")
        s.menu(OPTIONS_X, OPT_CUSTOM_ENC_Y, "menu-encryption")
        s.shot("enc-dialog", wait=8.0)
        s.mac.click(*ENC_PASSLOCK)
        s.mac.click(*ENC_OK)
        s.shot("enc-armed", wait=5.0)
        # The JPEG Optimizer, ticked in the dialog rather than by
        # script — and clicking its row opens the MODULE's own dialog,
        # which is what swallowed the first attempt's keystrokes. Q is
        # left at the default on purpose: the plaintext payload is then
        # the one `ps-jpeg2` already holds, 22,097 bytes of it, so
        # whoever implements PassLock has an exact answer to check
        # against rather than only a file that decrypts without error.
        set_jpeg_quality(s, 25)
        # File ▸ New Archive…, which is a Standard File save
        s.mac.command_key("n")
        s.shot("new-archive", wait=10.0)
        s.mac._xdo("type", "--delay", "140", ENC_ARCHIVE)
        s.shot("archive-named", wait=3.0)
        s.mac.key("Return")
        s.shot("archive-made", wait=12.0)
        # Archive ▸ Stuff…, a Standard File open: type-select, Return
        s.mac.command_key("s")
        s.shot("stuff-dialog", wait=10.0)
        s.mac._xdo("type", "--delay", "140", args.psname)
        s.shot("subject-selected", wait=4.0)
        s.mac.key("Return")
        s.shot("stuff-return", wait=10.0)
        # PassLock asks for the password itself, and nothing here knows
        # its dialog: type, Return, photograph, and do it again in case
        # it verifies. A shot between each is what makes a wrong guess
        # readable afterwards.
        for n in (1, 2, 3):
            s.mac._xdo("type", "--delay", "140", args.password)
            s.shot("password%d-typed" % n, wait=3.0)
            s.mac.key("Return")
            s.shot("password%d" % n, wait=10.0)
        s.shot("stuffed", wait=40.0)
        s.mac.command_key("w")
        s.shot("closed", wait=8.0)
        s.mac.command_key("q")
        s.shot("quit", wait=15.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        read_one(os.path.join(s.work, "boot.hfv"), ENC_ARCHIVE, outdir)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


def phase_psenc(args):
    """An entry that is OPTIMIZED and ENCRYPTED, which needs both.

    `PassLock` is a `SITe` module in the System Folder's Encryptors
    folder — one of the three 2.x encryptors OPEN_ITEMS.md records as
    never seen here — and it is reached from Options ▸ Custom
    Encryption…, not from the script language, whose STR# 257 has
    `newde` and `des` and no password at all. So the encryptor is armed
    through the DIALOG and the stuffing is left to a script.

    The password prompt is the fragile part: it is the application's,
    it arrives mid-script, and nothing here knows how many times. The
    run types it, photographs, and types it again at each wait, which
    is harmless if no dialog is up — the keystrokes land in a script
    that is not reading the keyboard.
    """
    doc = os.path.join(SPECIMENS, args.against or "psdoc2",
                       args.psname + ".bin")
    if not os.path.exists(doc):
        raise SystemExit("sitopt: no %s — --psdoc makes it" % doc)
    img = os.path.join(WORK, "run-psenc.hfv")
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sitopt-enc-")
    try:
        mb = os.path.join(work, "script.bin")
        open(mb, "wb").write(macbinary(ENC_SCRIPT_NAME, "TEXT", "SIT!",
                                       ENC_SCRIPT.encode("mac_roman")))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            hfs(env, "hcopy", "-m", doc, (VOL + ":").encode())
            hfs(env, "hcopy", "-m", mb, (VOL + ":").encode())
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.menu(EDIT_X, EDIT_SWITCH_Y, "expert-menus")
        # arm PassLock
        s.menu(OPTIONS_X, OPT_CUSTOM_ENC_Y, "menu-encryption")
        s.shot("enc-dialog", wait=8.0)
        s.mac.click(*ENC_PASSLOCK)
        s.shot("enc-selected", wait=3.0)
        s.mac.click(*ENC_OK)
        s.shot("enc-armed", wait=5.0)
        # and the menu again, to photograph which item is ticked now
        s.peek(OPTIONS_X, "options-after")
        # run the script
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Zpse")
        s.shot("script-selected", wait=3.0)
        s.mac.key("Return")
        for n in range(1, 5):
            s.shot("running%d" % n, wait=12.0)
            s.mac._xdo("type", "--delay", "140", args.password)
            s.mac.key("Return")
        s.shot("done", wait=60.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        for n in ("EncJpeg.sit", "EncStatus.out"):
            read_one(written, n, outdir)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


def phase_psopts(args):
    """Photograph the two dialogs behind the Options menu.

    `Compression Optimizers…` is where an Optimizer is turned on, and
    the question is whether it is also where one is CONFIGURED: every
    JPEG specimen here is quality 25, which is the module's `Pref` 128,
    and nothing has ever asked for another. `Custom Encryption…` is the
    other half: `PassLock` sits in the System Folder's Encryptors
    folder and no archive here has ever used it, so what that dialog
    lists is the whole question of whether this machine can make one.

    Both are opened, photographed and cancelled by CLICKING Cancel:
    neither ⌘. nor Escape closes them. A dialog that will not cancel
    costs only the shutdown — the shots are written on the HOST, so the
    photograph survives a hang, which is why this runs before anything
    tries to make an archive with what it finds.
    """
    img = os.path.join(WORK, "run-psopts.hfv")
    if not os.path.exists(PS_IMAGE):
        raise SystemExit("sitopt: no %s — --add-photoshop makes it" % PS_IMAGE)
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        s.menu(EDIT_X, EDIT_SWITCH_Y, "expert-menus")
        for tag, y in (("optimizers", OPT_OPTIMIZERS_Y),
                       ("custom-encryption", OPT_CUSTOM_ENC_Y)):
            s.menu(OPTIONS_X, y, "menu-" + tag)
            s.shot("dialog-" + tag, wait=8.0)
            s.mac.click(*OPT_CANCEL)
            s.shot("after-" + tag, wait=5.0)
        s.mac.command_key("q")
        s.shot("quit", wait=12.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


def phase_psmenus(args):
    """Peek every menu of the REGISTERED 2.0.1, which `--map` never saw.

    `--map` runs on `sitopt.hfv`, where the application stops at its
    personalization dialog, so the menu sweep it produced is a
    photograph of that dialog twelve times. This runs the same sweep on
    the image Photoshop and the Optimizers live on, which IS registered.

    Two questions, both of them about what a user could ask for that
    this project never has: where `Optimizers…` lives and whether an
    Optimizer has settings (the JPEG one encodes at quality 25, which
    is its `Pref` 128 and the only quality any specimen here carries),
    and what the Stuff dialog's Security popup offers now that
    `PassLock` is in the System Folder. Peeks only — a menu is pulled
    down, photographed and released, so nothing is clicked and no
    modal dialog can swallow the run.
    """
    img = os.path.join(WORK, "run-psmenus.hfv")
    if not os.path.exists(PS_IMAGE):
        raise SystemExit("sitopt: no %s — --add-photoshop makes it" % PS_IMAGE)
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        launch(s, args)
        # Expert menus first: Options and Scripts are not installed in
        # the standard set, and Archive's own items differ between them.
        s.menu(EDIT_X, EDIT_SWITCH_Y, "expert-menus")
        s.shot("menubar", wait=3.0)
        for x in range(30, 480, 40):
            s.peek(x, "menu-x%03d" % x)
        s.mac.command_key("q")
        s.shot("quit", wait=12.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


def phase_psmatrix(args):
    """Every compression method over an optimized fork, in one boot."""
    doc = os.path.join(SPECIMENS, args.against or "psdoc2",
                       args.psname + ".bin")
    if not os.path.exists(doc):
        raise SystemExit("sitopt: no %s — --psdoc makes it" % doc)
    img = os.path.join(WORK, "run-psmatrix.hfv")
    shutil.copyfile(PS_IMAGE, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    os.makedirs(outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sitopt-mx-")
    try:
        mb = os.path.join(work, "script.bin")
        open(mb, "wb").write(macbinary(MX_SCRIPT_NAME, "TEXT", "SIT!",
                                       mx_script(args.psname)
                                       .encode("mac_roman")))
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", img)
            hfs(env, "hcopy", "-m", doc, (VOL + ":").encode())
            hfs(env, "hcopy", "-m", mb, (VOL + ":").encode())
            subprocess.run(["hmkdir", (VOL + ":Out").encode()],
                           capture_output=True, env=env)
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        s.boot()
        launch(s, args)
        s.peek(SCRIPTS_X, "scripts-menu")
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Zpsm")
        s.shot("script-selected", wait=3.0)
        s.mac.key("Return")
        s.shot("running", wait=args.script_wait)
        s.shot("done", wait=90.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        for n in MX_ARCHIVES + ("MxStatus.out", "Out:" + args.psname):
            read_one(written, n, outdir)
    finally:
        time.sleep(3)
        s.close()
    return show_path(outdir)


def read_one(image, name, outdir):
    """One file off a written image, as MacBinary."""
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        if subprocess.run(["hmount", image], capture_output=True,
                          env=env).returncode != 0:
            return
        dest = os.path.join(outdir, name.split(":")[-1] + ".bin")
        if subprocess.run(["hcopy", "-m", (VOL + ":" + name).encode(),
                           dest.encode()], capture_output=True,
                          env=env).returncode != 0:
            print("sitopt: %-16s NOT on the volume" % name)
        subprocess.run(["humount"], capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


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
# Measured off `personalize/07-try-A 12345.png`, the first screenshot
# anything here has of 2.0.1's own menu bar: File Edit Archive Other
# Options Scripts Windows — and it comes up in EXPERT menus already, so
# the Edit menu's switch is not needed (--no-expert).
EDIT_X = 68
EDIT_SWITCH_Y = 156
SCRIPTS_X = 280
EXECUTE_Y = 20

# What the run writes, at the root of the one volume it has.
ARCHIVES = ["Plain.sit", "Optimized.sit", "OptBetter.sit"]
STATUS = "Status.out"


def phase_make(args):
    """Run the script, then read the archives and the status file back.

    Scripts ▸ Execute Script… (⌘E) on a script whose vocabulary is
    STR# 257's: `Enable Optimizer`, `New Archive`, `Stuff … with fast`,
    `Write Status To`. It needs the image `--personalize` registered —
    on an unregistered one the application stops at its licence dialog,
    and every keystroke after that goes to the Finder, which renames
    things. `--force` was a guard from when that wall was thought to be
    permanent; it is kept so that mistake is a refusal rather than a
    renamed file.

    The application QUITS itself — the script's last command — so the
    Finder is frontmost for Shut Down without a ⌘Q that might land on a
    modal dialog instead.
    """
    if not args.force:
        raise SystemExit(
            "sitopt: --make drives the APPLICATION, which needs the image "
            "--personalize registered. Pass --force once you have run "
            "that (and do NOT re-run --install after it).")
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
        # ⌘E, not the menu item: `Scripts ▸ Execute Script…` opened the
        # menu and selected nothing at y=20 (make1/06-script-picker.png
        # is a Finder-less desktop where the picker should be), and the
        # item carries a command key. This file's own advice.
        s.peek(SCRIPTS_X, "scripts-menu")
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
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
    # The image the emulator WROTE, not the one it was given: Mini vMac
    # boots a copy in the session's temp directory (interactive.py's
    # Mac.__init__), so mounting `img` reports every archive missing
    # from a run that made all three.
    read_back(os.path.join(s.work, "boot.hfv"), outdir)
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

    The mode that needs no emulator, for reading an archive somebody
    else's copy wrote. Given two, it diffs their first entry's header —
    which is the whole of the evidence an Optimizer leaves.
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

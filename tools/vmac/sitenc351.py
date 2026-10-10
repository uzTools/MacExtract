#!/usr/bin/env python3
"""sitenc351.py — can StuffIt Deluxe 3.5.1 put a 2.x cipher on a method-13 fork?

`sit_enc_id` (src/fmt_sit.c) ignores the encryptor id at bytes 107/109
of a method-13 fork, because InstallerMaker 1.0.3 leaves stray values
there. That is safe only if nothing writes a REAL id beside method 13 —
which is to say, only if StuffIt Deluxe 3.x cannot reach `DES` (id 1),
`PassLock` (2), `NewDEx` (3) or `DESex` (64). This asks the 3.5.1
APPLICATION, with all three of 2.0's Encryptor modules installed where
2.0 looked for them and where 3.5 keeps its other Aladdin folders.

    tools/vmac/sitenc351.py --install [--plain]   build the image
    tools/vmac/sitenc351.py --probe               menus and Preferences
    tools/vmac/sitenc351.py --script              run ZENC351, read back
    tools/vmac/sitenc351.py --script --variants   ZENC351B, the other spellings

**The application is LAUNCHED by a double-click** (`sitopt.launch351`):
⌘O on this image goes nowhere, which is why this project believed until
2026-10-10 that it never launched (BLOCKERS.md, withdrawn claims).

What this CANNOT see:

- **Encryptor modules other than 2.0's three.** A third party's module
  in 3.5.1's folders is not tried; nothing here has one.
- **StuffIt Deluxe 3.0.x, 3.5.0, Lite 3.x or the 4.x line.** 3.5.1 is
  the only 3.x application on this machine.
- **the Apple-event route.** The `stuff` event's only security parameter
  is the boolean `encryption` (the application's `aete`), so it cannot
  name a cipher and is not driven here.
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
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE)))
import sitopt as O                                       # noqa: E402
from arcmac import macbinary, hfs                        # noqa: E402
from diskdoubler import Session                          # noqa: E402

WORK = O.WORK
BOOT = os.path.join(WORK, "sitenc351.hfv")
SPECIMENS = os.path.join(O.R.VMAC_HOME, "specimens", "sitenc351")
VOL = O.VOL351
APPF = O.APP_FOLDER351
OPT_DIR = os.path.join(os.path.dirname(O.OPT_SIT), "opt")
OPT_ENC = os.path.join(OPT_DIR, "Deluxe-2-Optional", "Encryptors")

# Where a module might be looked for. 2.0.1's STR# 267 ("9 Magic Fldrs")
# names `Encryptors` in the System Folder; 3.5.1's names Help, Viewers,
# Optimizers, Translators, Aladdin, Preferences and Extensions, and keeps
# Viewers and Translators under `Extensions:Aladdin:` on this image.
FOLDERS = (("System Folder", "Encryptors"),
           ("System Folder", "Extensions", "Aladdin", "Encryptors"))

SCRIPT_NAME = "ZENC351"
# 3.5.1's vocabulary is its STR# 257: `better`, `newde`, `des`,
# `encrypt` and `encryptor` are all in it. `better` is the method 3.5.1
# writes as 13 (the three `sitcrypt.py` archives). The module syntax is
# a guess at 2.0.1's, `with <level> encryptor "<name>"`; 3.5.1 reads the
# name as an archive to stuff into (`specimens/sitenc351/script2`), and
# --variants tries the other spellings.
SCRIPT = "\r".join([
    "; written by tools/vmac/sitenc351.py",
    'Write Status To "{Startup}Enc351.out"',
    "Continue On Error",
    'New Archive "{Startup}E-des.sit"',
    'Stuff "{Startup}%s:Subject" with better des' % APPF,
    "Close",
    'New Archive "{Startup}E-newde.sit"',
    'Stuff "{Startup}%s:Subject" with better newde' % APPF,
    "Close",
    'New Archive "{Startup}E-encrypt.sit"',
    'Stuff "{Startup}%s:Subject" with better encrypt' % APPF,
    "Close",
    'New Archive "{Startup}E-newdex.sit"',
    'Stuff "{Startup}%s:Subject" with better encryptor "NewDEx"' % APPF,
    "Close",
    'New Archive "{Startup}E-desex.sit"',
    'Stuff "{Startup}%s:Subject" with better encryptor "DESex"' % APPF,
    "Close",
    'New Archive "{Startup}E-passlock.sit"',
    'Stuff "{Startup}%s:Subject" with better encryptor "PassLock"' % APPF,
    "Close",
    "; the control: the same subject, no security word",
    'New Archive "{Startup}E-none.sit"',
    'Stuff "{Startup}%s:Subject" with better' % APPF,
    "Close",
    "Quit",
    "",
])
# The second run: every other way the vocabulary could name a module.
# 3.5.1 read `encryptor "NewDEx"` above as an archive to stuff INTO
# ("No archive: NewDEx"), so these try the word unquoted, after a
# cipher word, and through `Set`, with `Enable Optimizer` as the
# control for STR# 256's "< Optimizers, compressors and encryptors: No
# longer supported. >".
SCRIPT_B = "\r".join([
    "; written by tools/vmac/sitenc351.py --variants",
    'Write Status To "{Startup}Enc351b.out"',
    "Continue On Error",
    'Enable Optimizer "Text 1"',
    'Set encryptor "NewDEx"',
    'New Archive "{Startup}V-bare.sit"',
    'Stuff "{Startup}%s:Subject" with better encryptor NewDEx' % APPF,
    "Close",
    'New Archive "{Startup}V-after.sit"',
    'Stuff "{Startup}%s:Subject" with better newde encryptor "NewDEx"'
    % APPF,
    "Close",
    'New Archive "{Startup}V-set.sit"',
    'Stuff "{Startup}%s:Subject" with better encrypt' % APPF,
    "Close",
    "Quit",
    "",
])
OUTPUTS_B = ("V-bare.sit", "V-after.sit", "V-set.sit", "Enc351b.out")
# What each run's archives are, by the status file of the first runs
# (`specimens/sitenc351/script2`, `variants1`): the three cipher words,
# and `encrypt` after `Set encryptor`, wrote an encrypted fork pair; the
# control did not; the `encryptor "<name>"` lines wrote an empty archive.
ENCRYPTED = ("E-des.sit", "E-newde.sit", "E-encrypt.sit", "V-set.sit")
PLAIN = ("E-none.sit",)
OUTPUTS = ("E-des.sit", "E-newde.sit", "E-encrypt.sit", "E-newdex.sit",
           "E-desex.sit", "E-passlock.sit", "E-none.sit", "Enc351.out")

# System 7's menus on this image, read off `specimens/sitopt/map351/`:
# File at 60, Edit at ~90, Archive at 235; items are 16 px apart from
# y=27, separators included. Preferences is Edit's ninth row.
EDIT_X = 90
PREFS_Y = 27 + 16 * 8
# In Preferences (`specimens/sitenc351/probe1/07-prefs.png`): the Menus
# box's "Script" checkbox, off by default, and OK. "Default Stuffing
# Settings" there is two checkboxes, Compression and Encryption, and no
# list of ciphers.
PREFS_SCRIPT = (300, 273)
PREFS_OK = (466, 286)
PREFS_HOME = (150, 300)   # a MOVE off the box, so the shot shows it


def modules(work):
    """2.0's three Encryptors as MacBinary: PassLock off disk 1's
    payload, NewDEx and DESex off the optional disk."""
    tree = O.payload(work)
    if not os.path.isdir(OPT_ENC):
        if not os.path.exists(O.OPT_SIT):
            raise SystemExit("sitenc351: no %s — sitopt.py --setup"
                             % O.OPT_SIT)
        subprocess.run([O.CLI, "x", "-o", OPT_DIR, O.OPT_SIT], check=True,
                       capture_output=True)
    out = []
    for name, rsrc in (("PassLock", os.path.join(tree, "Encryptors",
                                                 "PassLock.rsrc")),
                       ("NewDEx", os.path.join(OPT_ENC, "NewDEx.rsrc")),
                       ("DESex", os.path.join(OPT_ENC, "DESex.rsrc"))):
        if not os.path.exists(rsrc):
            raise SystemExit("sitenc351: no %s — sitopt.py --setup" % rsrc)
        mb = os.path.join(work, name + ".bin")
        open(mb, "wb").write(macbinary(name, "SITe", "SIT!", b"",
                                       open(rsrc, "rb").read()))
        out.append(mb)
    return out


def install(args):
    if not os.path.exists(O.SS_INSTALLED):
        raise SystemExit("sitenc351: no %s — spacesaver.py --install351"
                         % O.SS_INSTALLED)
    os.makedirs(WORK, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sitenc351-")
    items = []
    try:
        if not args.plain:
            for mb in modules(work):
                for f in FOLDERS:
                    items.append((f, mb))
        subj = os.path.join(work, "subject.bin")
        open(subj, "wb").write(macbinary(O.SUBJECT_NAME, "TEXT", "ttxt",
                                         O.SUBJECT_DATA, O.make_rsrc()))
        items.append(((APPF,), subj))
        for i, (name, text) in enumerate(((SCRIPT_NAME, SCRIPT),
                                          (SCRIPT_NAME + "B", SCRIPT_B))):
            scr = os.path.join(work, "script%d.bin" % i)
            open(scr, "wb").write(macbinary(name, "TEXT", "SIT!",
                                            text.encode("mac_roman")))
            items.append(((APPF,), scr))
        shutil.copyfile(O.SS_INSTALLED, BOOT)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            hfs(env, "hmount", BOOT)
            made = set()
            for folder, mb in items:
                for i in range(len(folder)):
                    d = folder[:i + 1]
                    if d not in made:
                        subprocess.run(
                            ["hmkdir", (VOL + ":" + ":".join(d))
                             .encode("mac_roman")],
                            capture_output=True, env=env)
                        made.add(d)
                dest = VOL + ":" + ":".join(folder) + ":"
                got = hfs(env, "hcopy", "-m", os.path.abspath(mb),
                          dest.encode("mac_roman"))
                if got.returncode != 0:
                    raise SystemExit("sitenc351: hcopy to %s failed" % dest)
            hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("sitenc351: %s (%s)" % (BOOT, "no modules" if args.plain else
                                  "PassLock, NewDEx, DESex in %d folders"
                                  % len(FOLDERS)))


def shut_down(s):
    """Quit first: with the application frontmost there is no Special
    menu, Shut Down never runs and the image is never flushed."""
    s.mac.command_key("q")
    s.shot("quit", wait=10.0)
    s.menu(O.SPECIAL_X351, O.SHUT_DOWN_Y351, "special-menu")
    s.shot("off", wait=35.0)


def phase_probe(args):
    """The application's menus, its Preferences, and what ⌘E does."""
    img = os.path.join(WORK, "run-sitenc351.hfv")
    shutil.copyfile(BOOT, img)
    s = Session(img, [], os.path.join(SPECIMENS, args.tag), mem=args.emu)
    try:
        O.launch351(s, args)
        s.peek(EDIT_X, "edit-menu")
        s.menu(EDIT_X, PREFS_Y, "prefs-item")
        s.shot("prefs", wait=6.0)
        s.mac.key("Escape")
        s.shot("prefs-closed", wait=4.0)
        s.mac.command_key("e")
        s.shot("cmd-e", wait=8.0)
        s.mac.key("Escape")
        shut_down(s)
    finally:
        time.sleep(4)
        s.close()
    print("sitenc351: shots in %s" % os.path.join(SPECIMENS, args.tag))
    return 0


def outputs(args):
    return OUTPUTS_B if args.variants else OUTPUTS


def read_back(image, outdir, names):
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        if subprocess.run(["hmount", image], capture_output=True,
                          env=env).returncode != 0:
            print("sitenc351: the written image does not mount")
            return
        for n in names:
            dest = os.path.join(outdir, n + ".bin")
            got = subprocess.run(["hcopy", "-m",
                                  (VOL + ":" + n).encode("mac_roman"),
                                  dest.encode()], capture_output=True,
                                 env=env)
            if got.returncode != 0:
                print("sitenc351: %-16s NOT on the volume" % n)
        subprocess.run(["humount"], capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


def made(outdir, args):
    """What `tools/run_crypt.py` grades the run against: the password
    every dialog was answered with, the subject's two forks, and which
    archive each script line wrote."""
    json.dump({"password": args.password,
               "script": SCRIPT_NAME + ("B" if args.variants else ""),
               "subject": {"name": O.SUBJECT_NAME,
                           "data": O.SUBJECT_DATA.hex(),
                           "rsrc": O.make_rsrc().hex()},
               "encrypted": [n + ".bin" for n in outputs(args)
                             if n in ENCRYPTED],
               "plain": [n + ".bin" for n in outputs(args) if n in PLAIN]},
              open(os.path.join(outdir, "made.json"), "w"), indent=1)


def show(outdir, names):
    for n in names:
        p = os.path.join(outdir, n + ".bin")
        if not os.path.exists(p):
            continue
        data, _r = O.forks(p)
        if n.endswith(".out"):
            print("---- %s\n%s" % (n, data.decode("mac_roman")
                                   .replace("\r", "\n")))
            continue
        print("%s:" % n)
        for off, h in O.entry_headers(data):
            print("  @%-6d %s" % (off, O.describe(h)))


def phase_script(args):
    """⌘E, pick the script, answer every password dialog the same way."""
    img = os.path.join(WORK, "run-sitenc351.hfv")
    shutil.copyfile(BOOT, img)
    outdir = os.path.join(SPECIMENS, args.tag)
    s = Session(img, [], outdir, mem=args.emu)
    try:
        O.launch351(s, args)
        s.menu(EDIT_X, PREFS_Y, "prefs-item")
        s.shot("prefs", wait=6.0)
        s.mac.click(*PREFS_SCRIPT)
        ox, oy = s.mac.origin()
        s.mac._xdo("mousemove", str(ox + PREFS_HOME[0]), str(oy + PREFS_HOME[1]))
        s.shot("script-ticked", wait=2.0)
        s.mac.click(*PREFS_OK)
        s.shot("script-menu", wait=4.0)
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120",
                   SCRIPT_NAME + ("B" if args.variants else ""))
        s.mac.key("Return")
        for n in range(1, args.answers + 1):
            s.shot("running%d" % n, wait=12.0)
            s.mac._xdo("type", "--delay", "140", args.password)
            s.mac.key("Return")
        s.shot("done", wait=45.0)
        shut_down(s)
        read_back(os.path.join(s.work, "boot.hfv"), outdir, outputs(args))
        made(outdir, args)
    finally:
        time.sleep(3)
        s.close()
    show(outdir, outputs(args))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emu", default="mv-4M")
    ap.add_argument("--launch-wait", type=float, default=40.0)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--plain", action="store_true",
                    help="the control image: no module added")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--script", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--made", action="store_true",
                    help="(re)write a run's made.json from --password")
    ap.add_argument("--variants", action="store_true",
                    help="run ZENC351B, the other spellings")
    ap.add_argument("--answers", type=int, default=8)
    ap.add_argument("--password", default="swordfish")
    ap.add_argument("--tag", default="probe")
    args = ap.parse_args()
    if args.install:
        install(args)
        return 0
    if args.probe:
        return phase_probe(args)
    if args.script:
        return phase_script(args)
    if args.made:
        made(os.path.join(SPECIMENS, args.tag), args)
        return 0
    if args.show:
        show(os.path.join(SPECIMENS, args.tag), outputs(args))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

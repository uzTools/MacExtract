#!/usr/bin/env python3
"""marenc.py — MAR archives written by mar 0.2.0 itself, on an emulated Mac.

mar 0.2.0 is Hampa Hug's own Macintosh writer, and the only one that types
what it writes — creator `MARc`, `MARd` a folder's `.mar`, `MARf` a file's
`.mac`, `ZIVU` either compressed (reference/mar/mar-0.2.0-src/src/mar_io.c)
— and the only one that writes the LZW form. This runs it on System 6.0.8:
File > Encode... (Command-E) and File > Compress... (Command-Z), each on a
folder and on a file, the archive written beside its source.

    marenc.py --setup      build the volume: mar, a folder and a file
    marenc.py --explore    boot, open the volume, launch mar, photograph
    marenc.py --make       boot, drive mar, read the archives back
    marenc.py --list       what the last --make left

The application is `mar-0.2.0-mpw-3.5.68k` out of `fixtures/mar-twin-
mar020.sit`, hampa's own StuffIt archive of mar 0.2.0 (fixtures/SOURCES.md).
It is GPL-2.0-only and is RUN here, never linked into anything (NOTICE).
The subjects are `tools/mar_unix.py`'s, the same bytes its Unix writer is
given. Archives, their Finder type and creator, and the screenshots land in

    ~/.cache/macextract/vmac/specimens/mar/mac/
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
import arcmac as A                                  # noqa: E402
import mar_unix as U                                # noqa: E402

HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
OUT = os.path.join(HOME, "specimens", "mar", "mac")
IMG = os.path.join(OUT, "volume.img")
TWIN = os.path.join(REPO, "fixtures", "mar-twin-mar020.sit")
APP = "mar-0.2.0-mpw-3.5.68k"
VOL = "MAR"


def app_macbinary(work):
    """The application, both forks and its type/creator, out of the twin."""
    out = os.path.join(work, "app")
    r = subprocess.run([A.cli(), "x", "--forks", "hidden", "-o", out, TWIN],
                       capture_output=True)
    if r.returncode:
        raise SystemExit("marenc: cannot extract %s: %s" % (TWIN, r.stderr))
    for dp, _, fn in os.walk(out):
        if APP in fn:
            data = open(os.path.join(dp, APP), "rb").read()
            rp = os.path.join(dp, "._" + APP)
            rsrc = open(rp, "rb").read() if os.path.exists(rp) else b""
            p = os.path.join(work, "app.bin")
            open(p, "wb").write(A.macbinary("mar", "APPL", "MARc", data, rsrc))
            return p
    raise SystemExit("marenc: no %s in %s" % (APP, TWIN))


def setup():
    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp(prefix="marenc-")
    try:
        app = app_macbinary(work)
        subj = {}
        for n, k in (("Two Forks", "both"), ("Locked", "locked"),
                     ("Rsrc Only", "rsrconly")):
            p = os.path.join(work, k + ".bin")
            open(p, "wb").write(U.macbinary(n.encode(), **U.FILES[k]))
            subj[n] = p
        open(IMG, "wb").truncate(1400 * 1024)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            A.hfs(env, "hformat", "-l", VOL, IMG)
            A.hfs(env, "hmount", IMG)
            A.hfs(env, "hcopy", "-m", app, VOL + ":")
            A.hfs(env, "hcopy", "-m", subj["Two Forks"], VOL + ":")
            A.hfs(env, "hmkdir", VOL + ":Subject")
            A.hfs(env, "hmkdir", VOL + ":Subject:Inner")
            A.hfs(env, "hcopy", "-m", subj["Locked"], VOL + ":Subject:")
            A.hfs(env, "hcopy", "-m", subj["Rsrc Only"],
                  VOL + ":Subject:Inner:")
            A.hfs(env, "humount")
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
        print("marenc: volume ready (%s)" % IMG)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def session(system):
    if not os.path.exists(IMG):
        setup()
    return A.Session(os.path.join(HOME, system), [IMG],
                     os.path.join(OUT, "shots"))


def explore(system):
    s = session(system)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(470, 110, double=True)           # open the volume
        s.shot("volume", wait=8.0)
        s.mac.click(175, 105, double=True)           # launch mar
        s.shot("launched", wait=12.0)
        s.mac.command_key("e")                       # File > Encode...
        s.shot("encode-dialog", wait=5.0)
    finally:
        time.sleep(3)
        s.close()


# Standard File's list in mar's own System 6 dialog, sorted by name:
# Desktop 111, mar 127, Subject 143, then what this writes. Every archive
# sorts between Subject and Two Forks, so Two Forks moves down a row each.
ROW0 = 111
OPEN_BTN, FOLDER_BTN = (378, 210), (378, 235)


def run_one(s, key, row, folder, tag):
    """File > Encode... (e) or Compress... (z) on the item at ROW. The
    Folder button takes the folder the dialog is IN, not the row selected
    (measured: from the volume's root it offered "MAR.mar"), so a folder is
    opened first; a file is opened directly. Either way mar then asks where
    to save, its own name filled in, and Return takes it."""
    s.mac.command_key(key)
    s.shot(tag + "-dialog", wait=5.0)
    s.mac.click(150, row, double=True)
    s.shot(tag + "-opened", wait=3.0)
    if folder:
        s.mac.click(*FOLDER_BTN)
        s.shot(tag + "-folder", wait=3.0)
        # Save opens IN the folder being archived (measured: Subject.mar
        # went inside Subject), where the next run would archive it too.
        # Up one level by the pop-up over the list: press its title, drag to
        # the second item, the volume, let go.
        ox, oy = s.mac.origin()
        x = s.mac._xdo
        x("mousemove", str(ox + 210), str(oy + 79))
        time.sleep(0.4)
        x("mousedown", "1")
        time.sleep(1.0)
        x("mousemove", str(ox + 210), str(oy + 79 + 18))
        time.sleep(0.8)
        s.shot(tag + "-popup", wait=0.3)
        x("mouseup", "1")
        s.shot(tag + "-up", wait=2.0)
    s.mac.key("Return")
    s.shot(tag + "-done", wait=30.0)


def make(system):
    """Folder and file, plain and compressed, then read them back."""
    setup()                      # a fresh volume: a killed run damages it
    s = session(system)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(470, 110, double=True)
        s.shot("volume", wait=8.0)
        s.mac.click(175, 105, double=True)
        s.shot("launched", wait=12.0)
        run_one(s, "e", ROW0 + 32, True, "fold-enc")    # Subject.mar
        run_one(s, "z", ROW0 + 32, True, "fold-lzw")    # Subject.mar.Z
        run_one(s, "e", ROW0 + 80, False, "file-enc")   # Two Forks.mac
        run_one(s, "z", ROW0 + 80, False, "file-lzw")   # Two Forks.mac.Z
        s.mac.command_key("q")
        s.shot("quit", wait=8.0)
        s.shutdown()
        s.shot("off", wait=25.0)
    finally:
        time.sleep(5)
        s.close()
    got = A.read_volume(IMG, os.path.join(OUT, "readback"))
    meta = {}
    for name, (typ, crt, data, rsrc) in sorted(got.items()):
        print("  %-20s %s/%s  data %7d  rsrc %7d"
              % (name, typ, crt, len(data), len(rsrc)))
        if name.endswith((".mar", ".mac", ".Z")):
            open(os.path.join(OUT, name), "wb").write(data)
            meta[name] = {"type": typ, "creator": crt, "size": len(data)}
    with open(os.path.join(OUT, "written.json"), "w") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--explore", action="store_true")
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--system", default="System6.hfv")
    a = ap.parse_args()
    if a.setup:
        setup()
    if a.explore:
        explore(a.system)
    if a.make:
        make(a.system)
    if a.list:
        print(open(os.path.join(OUT, "written.json")).read())
    if not (a.setup or a.explore or a.make or a.list):
        print(__doc__.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())

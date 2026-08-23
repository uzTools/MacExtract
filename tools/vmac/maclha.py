#!/usr/bin/env python3
"""maclha.py — make a Macintosh LZH archive with MacLHA, forks and all.

MacLHA writes a Macintosh file into a `.lzh` by compressing a MacBinary
stream, so an entry carries BOTH forks and its Finder metadata; that is
what `src/fmt_lzh.c` splits back out. Every MacLHA specimen this project
can reach — sixteen of them, in lhasa's collection — holds a
data-fork-only file, so the resource half of that split had never met a
byte written by MacLHA (OPEN_ITEMS.md). This makes one.

The encoder is **MacLHA 2.00 itself**, which is already in the corpus:
`fixtures/derived-MacLHa_2.00.sit`, off nic.funet.fi. `--setup` extracts
the application with our own CLI, rebuilds it as MacBinary and builds a
volume with a two-fork subject beside it; `--make` boots, drives the
application and reads the archive back; `--check` extracts that archive
with our CLI and compares both forks against the bytes that went in.

    maclha.py --setup     build the volume
    maclha.py --make      boot, drive MacLHA, write an archive, read it back
    maclha.py --check     grade the archive against the subject's forks

Specimens land in `$UNC_VMAC_HOME/specimens/maclha/`, beside the emulator
rather than under `build/`, which `make clean` removes.

The UI is documented in the application's own `MacLHa.doc` (Japanese,
Shift-JIS; the menus and buttons are English): FILE ▸ NewArchive opens an
empty listing, `add` opens a Standard File dialog for the file to store,
`save` asks where to put the archive and then compresses.
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
import arcmac as A                                  # noqa: E402
from interactive import Mac                         # noqa: E402

HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/unclassic/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "maclha")
FIXTURE = os.path.join(REPO, "fixtures", "derived-MacLHa_2.00.sit")

SUBJECT_NAME = "TwoForks"
SUBJECT_DATA = (b"THIS IS THE DATA FORK of a MacLHA specimen.\r" * 40)
SUBJECT_RSRC = A.make_rsrc(b"\x16MacLHA fork-split test")


def cli():
    return A.cli()


def setup():
    """Extract MacLHA from the corpus fixture and build the volume."""
    os.makedirs(SPECIMENS, exist_ok=True)
    if not os.path.exists(FIXTURE):
        raise SystemExit("maclha: no %s (tools/harvest.py --restore)" % FIXTURE)
    work = tempfile.mkdtemp(prefix="maclha-")
    try:
        out = os.path.join(work, "out")
        os.makedirs(out)
        r = subprocess.run([cli(), "x", "-nr", "--forks", "hidden",
                            "-o", out, FIXTURE], capture_output=True)
        if r.returncode != 0:
            raise SystemExit("maclha: cannot extract MacLHA: %s"
                             % r.stderr.decode()[:200])
        # APPL/LARC, and it is a resource-only application: the data
        # fork of `MacLHa 2.00` is empty.
        data = open(os.path.join(out, "MacLHa 2.00"), "rb").read()
        rsrc = open(os.path.join(out, "._MacLHa 2.00"), "rb").read()
        appbin = os.path.join(SPECIMENS, "MacLHa.bin")
        open(appbin, "wb").write(
            A.macbinary("MacLHa 2.00", "APPL", "LARC", data, rsrc))

        subj = os.path.join(work, "subject.bin")
        open(subj, "wb").write(A.macbinary(SUBJECT_NAME, "TEXT", "ttxt",
                                           SUBJECT_DATA, SUBJECT_RSRC))
        img = os.path.join(SPECIMENS, "volume.img")
        A.make_volume(img, "LHa", [appbin, subj])
        open(os.path.join(SPECIMENS, "in-data"), "wb").write(SUBJECT_DATA)
        open(os.path.join(SPECIMENS, "in-rsrc"), "wb").write(SUBJECT_RSRC)
        print("maclha: volume ready (%s), application %d B of resources"
              % (img, len(rsrc)))
        return img
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Session(A.Session):
    """arcmac's session, with a menu pull that is not the Finder's."""

    def app_menu(self, title_x, item_y, tag):
        self.menu(title_x, item_y, tag)


def explore(system="System6.hfv", mem="mv-4M"):
    """Boot, launch MacLHA, and photograph each menu pulled down.

    The application's own documentation names the menu items but not
    where they are, and Mini vMac is driven by coordinates."""
    img = os.path.join(SPECIMENS, "volume.img")
    if not os.path.exists(img):
        setup()
    s = Session(os.path.join(HOME, system), [img],
                os.path.join(SPECIMENS, "shots"), mem=mem)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(470, 110, double=True)           # open the volume
        s.shot("volume", wait=8.0)
        s.mac.click(105, 110, double=True)           # launch MacLHa
        s.shot("launched", wait=25.0)
        for name, x in (("file", 42), ("edit", 76), ("options", 118)):
            ox, oy = s.mac.origin()
            xd = s.mac._xdo
            xd("mousemove", str(ox + x), str(oy + 8))
            time.sleep(0.4)
            xd("mousedown", "1")
            time.sleep(1.5)
            s.shot("menu-" + name)
            xd("mousemove", str(ox + x), str(oy + 8))
            time.sleep(0.5)
            xd("mouseup", "1")
            time.sleep(1.0)
    finally:
        time.sleep(3)
        s.close()


def make(system="System6.hfv", mem="mv-4M"):
    """Boot, drive MacLHA, and read the archive it wrote back off the disk.

    Driven by the keyboard where MacLHA offers a shortcut, because two of
    the three settings menus are HIERARCHICAL and Mini vMac cannot select
    a submenu item at all (tools/vmac/README.md). Nothing here needs one:
    the Options menu already has `MacBinary` checked, which is the
    setting that makes the payload a Macintosh file rather than a data
    fork, and it is the default."""
    img = os.path.join(SPECIMENS, "volume.img")
    if not os.path.exists(img):
        setup()
    s = Session(os.path.join(HOME, system), [img],
                os.path.join(SPECIMENS, "shots"), mem=mem)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(470, 110, double=True)           # open the volume
        s.shot("volume", wait=8.0)
        s.mac.click(105, 110, double=True)           # launch MacLHa
        s.shot("launched", wait=25.0)
        s.mac.command_key("n")                       # File ▸ New Archive…
        s.shot("new", wait=6.0)
        # The empty listing window: Extract / Add / Delete / Save /
        # Cancel down the right edge, and `Save` stays greyed until
        # something has been added.
        s.mac.click(465, 120)                        # Add
        s.shot("add-dialog", wait=6.0)
        # A Standard File dialog with the volume's one document already
        # selected: Select File adds it, Done closes the dialog.
        s.mac.click(389, 225)                        # Select File
        s.shot("selected", wait=4.0)
        s.mac.click(389, 281)                        # Done
        s.shot("listed", wait=6.0)
        s.mac.click(465, 239)                        # Save
        s.shot("save-dialog", wait=6.0)
        s.mac.key("Return")
        s.shot("compressed", wait=25.0)
        s.mac.command_key("q")                       # File ▸ Quit
        s.shot("quit", wait=20.0)
        # Shut Down, not SIGKILL: Mini vMac only flushes a volume when
        # it is ejected, so killing the emulator loses what the guest
        # wrote (arcmac.py says the same, having lost a file that way).
        s.shutdown()
        s.shot("off", wait=25.0)
    finally:
        time.sleep(5)
        s.close()

    got = A.read_volume(img, os.path.join(SPECIMENS, "readback"))
    for name, (typ, crt, data, rsrc) in sorted(got.items()):
        print("  %-20s %s/%s  data %7d  rsrc %7d"
              % (name, typ, crt, len(data), len(rsrc)))
        if name.lower().endswith(".lzh"):
            open(os.path.join(SPECIMENS, name), "wb").write(data)
    return got


def check():
    """Extract MacLHA's archive with our CLI and grade both forks."""
    want_d = open(os.path.join(SPECIMENS, "in-data"), "rb").read()
    want_r = open(os.path.join(SPECIMENS, "in-rsrc"), "rb").read()
    arcs = [f for f in sorted(os.listdir(SPECIMENS))
            if f.lower().endswith(".lzh")]
    if not arcs:
        raise SystemExit("maclha: no archive — run --make first")
    bad = 0
    for a in arcs:
        out = tempfile.mkdtemp(prefix="maclha-out-")
        try:
            r = subprocess.run([cli(), "x", "-nr", "--forks", "hidden",
                                "-o", out, os.path.join(SPECIMENS, a)],
                               capture_output=True)
            d = os.path.join(out, SUBJECT_NAME)
            rs = os.path.join(out, "._" + SUBJECT_NAME)
            gd = open(d, "rb").read() if os.path.exists(d) else b""
            gr = open(rs, "rb").read() if os.path.exists(rs) else b""
            ok = r.returncode == 0 and gd == want_d and gr == want_r
            print("  %-18s %s  data %d/%d  rsrc %d/%d%s"
                  % (a, "OK" if ok else "MISMATCH", len(gd), len(want_d),
                     len(gr), len(want_r),
                     "" if r.returncode == 0
                     else "  (" + r.stderr.decode()[:80].strip() + ")"))
            bad += 0 if ok else 1
        finally:
            shutil.rmtree(out, ignore_errors=True)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--explore", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--system", default="System6.hfv")
    args = ap.parse_args()
    if args.setup:
        setup()
    if args.make:
        make(args.system)
    if args.explore:
        explore(args.system)
    if args.check:
        return 1 if check() else 0
    if not (args.setup or args.make or args.explore or args.check):
        print(__doc__.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())

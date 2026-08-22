#!/usr/bin/env python3
"""sdcompress.py — run Alysis SuperDisk!'s COMPRESSOR under Mini vMac.

`superdisk.py` grades this engine with SuperDisk!'s own *expanders*, which
is all the corpus's two self-extracting archives can offer. Methods 10
("SlowFastA"), 13 ("SlowFastC") and 20 ("Tennessee") stayed declined
because nothing here writes them, and OPEN_ITEMS.md said the compressor
"does not survive here, only its expander".

**It survives.** Macintosh Repository carries the 1991 `SuperDisk!`
control panel (`cdev`/`AlyS`, an 89 KB resource fork), which is the half
that compresses: it watches the file system and squeezes anything whose
name gains its extension.

    tools/vmac/sdcompress.py --setup     fetch and unpack it
    tools/vmac/sdcompress.py --install   System 7 with the control panel
    tools/vmac/sdcompress.py --probe     photograph the panel's options

Its own help strings name three modes a general compressor does not
have — JPEG lossy, lossy sound, and a lossless sound/video optimiser —
so what the numbered methods ARE is a measurement waiting to be taken,
not something to infer from a `Cmpr` name.

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
from diskdoubler import (cli, Session, make_volume, VOLUME_ICON)  # noqa: E402

# Macintosh Repository's one-shot token, the same three-request dance
# `ndd.py` documents.
MR_PAGE = "https://www.macintoshrepository.org/37412-superdisk-"
MR_ID = "39344"
SHA = "a4ebff39ccede448d57929d396ad61acf12e3471726af9e1993bd8c8fa99d62e"

HOME = R.VMAC_HOME
WORK = os.path.join(HOME, "sdisk")
SPECIMENS = os.path.join(HOME, "specimens", "sdcompress")
HQX = os.path.join(WORK, "sd-39344.bin")
TREE = os.path.join(WORK, "tree")
BOOT = os.path.join(WORK, "sdboot.hfv")

PANEL = "SuperDisk!"        # matched as a substring: the real name leads
                            # with a space, to sort to the top of a folder


def fetch():
    """Three requests, because a plain GET answers with an interstitial
    that SAYS the link expired — see `ndd.fetch_norton` for the trap."""
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(HQX):
        jar = os.path.join(WORK, "jar")
        ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
        def c(args, out=None):
            cmd = ["curl", "-sS", "-m", "300", "-A", ua, "-c", jar, "-b", jar] + args
            if out:
                cmd += ["-o", out]
            return subprocess.run(cmd, capture_output=True, check=True).stdout
        c([MR_PAGE], os.devnull)
        hdr = os.path.join(WORK, "h.txt")
        c(["-e", MR_PAGE, "-D", hdr,
           "https://www.macintoshrepository.org/download.php?id=" + MR_ID],
          os.devnull)
        loc = None
        for line in open(hdr, errors="replace"):
            if line.lower().startswith("location:"):
                loc = line.split(":", 1)[1].strip()
        if not loc:
            raise SystemExit("sdcompress: no download token — site changed, "
                             "or you are being rate-limited (it is one-shot "
                             "per session; use a fresh cookie jar per file)")
        form = os.path.join(WORK, "form.html")
        c(["-e", MR_PAGE, "https://www.macintoshrepository.org/" + loc], form)
        import re
        m = re.search(r'name="d" value="([^"]*)"', open(form, errors="replace").read())
        if not m:
            raise SystemExit("sdcompress: no token field in the form")
        c(["-L", "-e", "https://www.macintoshrepository.org/" + loc,
           "--data-urlencode", "d=" + m.group(1), "--data", "via_http=1",
           "https://www.macintoshrepository.org/download.php?u=0&id=%s&go=1"
           % MR_ID], HQX)
    got = hashlib.sha256(open(HQX, "rb").read()).hexdigest()
    print("sdcompress: %s sha256 %s%s (%d B)"
          % (os.path.basename(HQX), got, "" if got == SHA else "  MISMATCH",
             os.path.getsize(HQX)))
    if got != SHA:
        raise SystemExit("sdcompress: the download is not the file this was "
                         "written against")
    if os.path.getsize(HQX) < 10000:
        raise SystemExit("sdcompress: that is the 'link expired' page, not "
                         "the file")
    shutil.rmtree(TREE, ignore_errors=True)
    os.makedirs(TREE)
    subprocess.run([cli(), "x", "--forks", "hidden", "-o", TREE, HQX],
                   check=True, capture_output=True)
    print("sdcompress: unpacked into %s" % TREE)
    return TREE


def find(name):
    for root, _d, files in os.walk(TREE):
        for f in sorted(files):
            if f.startswith("._"):
                continue
            if name in f:
                return os.path.join(root, f), os.path.join(root, "._" + f)
    raise SystemExit("sdcompress: nothing matching %r — run --setup" % name)


def panel_file():
    """The control panel as (name, type, creator, data, rsrc)."""
    if not os.path.isdir(TREE):
        fetch()
    p, rp = find(PANEL)
    return (" SuperDisk!", "cdev", "AlyS",
            open(p, "rb").read(),
            open(rp, "rb").read() if os.path.exists(rp) else b"")


def install():
    """System 7 with the control panel in place.

    A `cdev` goes in `Control Panels`, not `Extensions` — this one also
    carries an `INIT -492`, so it loads at startup from there and the
    compressing half is running before the Finder appears.
    """
    name, ftype, creator, data, rsrc = panel_file()
    print("sdcompress: %s — %s/%s, %d B data, %d B rsrc"
          % (name.strip(), ftype, creator, len(data), len(rsrc)))
    work = tempfile.mkdtemp(prefix="sdinst-")
    try:
        mb = os.path.join(work, "panel.bin")
        open(mb, "wb").write(macbinary(name, ftype, creator, data, rsrc))
        shutil.copyfile(os.path.join(HOME, "Sys7.img"), BOOT)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            subprocess.run(["hmount", BOOT], check=True, capture_output=True,
                           env=env)
            subprocess.run(["hcopy", "-m", mb,
                            ":System Folder:Control Panels:"], check=True,
                           capture_output=True, env=env)
            subprocess.run(["humount"], check=True, capture_output=True,
                           env=env)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("sdcompress: boot image with the control panel at %s" % BOOT)
    return BOOT


SUBJECT = (b"Alysis SuperDisk! method probe. " * 300 +
           bytes(bytearray(range(256))) * 6)

SUBJECTS = [("Alpha", "TEXT", "ttxt", SUBJECT, b""),
            ("Beta", "TEXT", "ttxt", SUBJECT[:4000], b"")]


def session(tag):
    work = tempfile.mkdtemp(prefix="sdwork-")
    mbs = []
    for i, (n, t, c, d, r) in enumerate(SUBJECTS):
        p = os.path.join(work, "s%d.bin" % i)
        open(p, "wb").write(macbinary(n, t, c, d, r))
        mbs.append(p)
    img = os.path.join(work, "sdwork.img")
    make_volume(img, "SDwork", mbs, size_kb=8192)
    # ALWAYS rebuild the boot image. Mini vMac writes back, and this
    # control panel saves its settings AND its current page into the
    # System Folder — so a second run opens where the first one left off
    # and a coordinate measured on page 1 lands on page 2's buttons.
    # One run turned compression off that way and photographed a
    # settings page while believing it had opened a file dialog.
    install()
    s = Session(BOOT, [img], os.path.join(SPECIMENS, tag))
    return s, work, img


def probe(keep=False):
    """Boot with the panel loaded and photograph it.

    Two things this has to establish before anything else is worth
    running: that the INIT loads at all (a control panel that fails shows
    a crossed-out icon at startup), and what the panel's options are —
    its help strings mention JPEG and sound modes that no `Cmpr` name
    accounts for.
    """
    s, work, img = session("probe")
    try:
        s.boot()
        s.shot("desktop", wait=6.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        # Apple menu -> Control Panels
        ox, oy = s.mac.origin()
        s.mac._xdo("mousemove", str(ox + 12), str(oy + 8))
        time.sleep(0.4)
        s.mac._xdo("mousedown", "1")
        time.sleep(1.2)
        s.shot("apple-menu")
        s.mac._xdo("mousemove", str(ox + 40), str(oy + 40))
        time.sleep(1.0)
        s.shot("apple-menu-open")
        s.mac._xdo("mouseup", "1")
        s.shot("after-apple", wait=8.0)
    finally:
        time.sleep(3)
        s.close()
    print("sdcompress: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def rename_append(s, letter, suffix, tag):
    """Append to a Finder icon's name, in place.

    Return on a selected icon opens its name for editing with the WHOLE
    name selected — the trap every other harness here avoids, and the
    tool for this job. Right-arrow drops the selection to the end so the
    suffix is appended rather than replacing what is there.
    """
    s.mac.key("Escape")
    time.sleep(0.6)
    s.mac.key(letter)
    time.sleep(1.5)
    s.shot("selected-" + tag, wait=0.5)
    s.mac.key("Return")                   # open the name for editing
    time.sleep(1.5)
    s.mac.key("Right")                    # to the end, keeping the name
    time.sleep(0.5)
    s.mac._xdo("type", "--delay", "150", suffix)
    time.sleep(1.0)
    s.shot("typed-" + tag, wait=0.5)
    s.mac.key("Return")                   # commit the rename
    time.sleep(2.0)


def make(keep=False):
    """Rename the subjects so SuperDisk! compresses them, then read the
    volume back and report what method each archive used."""
    s, work, img = session("make")
    try:
        s.boot()
        s.shot("desktop", wait=6.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        rename_append(s, "a", ".x", "alpha")
        s.shot("after-alpha", wait=20.0)
        rename_append(s, "b", ".X", "beta")
        s.shot("after-beta", wait=20.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    report(img, s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def report(img, shots):
    from superdisk import read_forks                    # noqa: E402
    os.makedirs(shots, exist_ok=True)
    for path, (ftype, creator, data, rsrc) in sorted(read_forks(img).items()):
        name = "/".join(path)
        mark = ""
        if len(data) >= 12:
            # An archive is eight bytes nobody reads, then the record
            # stream; the method byte lives in each block chain. What we
            # want first is simply whether the shape changed at all.
            mark = "  first12=" + data[:12].hex()
        print("sdcompress: %-28s %s/%s %8d %8d%s"
              % (name, ftype, creator, len(data), len(rsrc), mark))
        if ftype in ("SDar", "Alys") or name.lower().endswith((".x", ".X")):
            out = os.path.join(shots, path[-1].replace("/", "_"))
            open(out, "wb").write(data)
            print("             kept %s" % out)
            r = subprocess.run([cli(), "l", "-v", out], capture_output=True,
                               text=True)
            for line in (r.stdout + r.stderr).strip().splitlines()[:6]:
                print("             %s" % line)


BOOTVOL_ICON = (470, 55)     # the System 7 volume, above the work volume


def panel(keep=False):
    """Open the control panel from the System Folder and photograph it.

    Not via the Apple menu: two attempts at holding that open produced
    frames with the title inverted and no menu, which is a timing fight
    worth avoiding. Navigating the boot volume also PROVES the panel is
    installed, which the Apple menu would not.
    """
    s, work, img = session("panel")
    try:
        s.boot()
        s.shot("desktop", wait=6.0)
        s.mac.click(*BOOTVOL_ICON, double=True)
        s.shot("bootvol", wait=10.0)
        for prefix, tag in (("System F", "sysfolder"), ("Control P", "cpanels")):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac._xdo("type", "--delay", "120", prefix)
            time.sleep(1.5)
            s.shot("selected-" + tag, wait=0.5)
            s.mac.command_key("o")
            s.shot("opened-" + tag, wait=12.0)
        # The panel's name leads with a space so it sorts first; typing
        # a space is how type-select reaches it.
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("key", "space")
        time.sleep(1.5)
        s.shot("selected-panel", wait=0.5)
        s.mac.command_key("o")
        s.shot("panel-open", wait=20.0)
        s.shot("panel-open-2", wait=8.0)
    finally:
        time.sleep(3)
        s.close()
    print("sdcompress: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# Measured off panel/08-panel-open.png (System 7, 512x342).
MAKE_FILE = (190, 73)
MORE_OPTIONS = (136, 292)
NEXT_PAGE = (272, 303)


def open_panel(s):
    """Boot, and leave the control panel open and frontmost."""
    s.boot()
    s.shot("desktop", wait=6.0)
    s.mac.click(*BOOTVOL_ICON, double=True)
    s.shot("bootvol", wait=10.0)
    for prefix, tag in (("System F", "sysfolder"), ("Control P", "cpanels")):
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", prefix)
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("opened-" + tag, wait=12.0)
    s.mac.key("Escape")
    time.sleep(0.6)
    s.mac._xdo("key", "space")
    time.sleep(1.5)
    s.mac.command_key("o")
    s.shot("panel-open", wait=20.0)


def makefile(keep=False):
    """Press "Make File" and see what SuperDisk! offers.

    The control panel is the compressor's whole UI: a "Make File"
    button, three 3-D icon buttons (Auto X, Alerts, Security) and a
    paged options area. Which of those writes methods 10, 13 or 20 is
    the question; this photographs the path to it.
    """
    s, work, img = session("makefile")
    try:
        open_panel(s)
        # "Make File" is the top button on the FIRST page only. Paging
        # first replaces it with the Compress setting's Off/Light/Tighter
        # buttons, and clicking the same coordinate then hits "Off" —
        # which is how one run turned compression off and photographed a
        # settings page instead of a file dialog.
        s.mac.click(*MAKE_FILE)
        s.shot("make-file", wait=12.0)
        s.shot("make-file-2", wait=10.0)
        s.mac.key("Return")
        s.shot("after-return", wait=12.0)
    finally:
        time.sleep(3)
        s.close()
    print("sdcompress: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# The standard file dialog "Make File" puts up, measured off
# makefile/06-make-file.png.
SF_DESKTOP = (374, 142)
SF_OPEN = (374, 214)


def compress(keep=False):
    """Compress a subject with SuperDisk! and report the method it used.

    "Make File" opens a standard file dialog; Desktop gets to the work
    volume, and Return is the dialog's default button (Open), which is
    safe here in a way it never is in the Finder.
    """
    s, work, img = session("compress")
    try:
        open_panel(s)
        s.mac.click(*MAKE_FILE)
        s.shot("file-dialog", wait=12.0)
        s.mac.click(*SF_DESKTOP)
        s.shot("desktop-level", wait=6.0)
        s.mac._xdo("type", "--delay", "150", "SDwork")
        time.sleep(1.5)
        s.shot("picked-volume", wait=0.5)
        s.mac.key("Return")
        s.shot("in-volume", wait=8.0)
        s.mac._xdo("type", "--delay", "150", "Alpha")
        time.sleep(1.5)
        s.shot("picked-alpha", wait=0.5)
        s.mac.key("Return")
        s.shot("compressing", wait=25.0)
        s.shot("compressed", wait=15.0)
        s.mac.key("Return")
        s.shot("after", wait=8.0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    report(img, s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--panel", action="store_true",
                    help="open the control panel and photograph it")
    ap.add_argument("--makefile", action="store_true",
                    help="press Make File and photograph what it offers")
    ap.add_argument("--compress", action="store_true",
                    help="compress a subject and report the method")
    ap.add_argument("--make", action="store_true",
                    help="rename subjects so SuperDisk! compresses them")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if a.setup:
        fetch()
    elif a.install:
        install()
    elif a.probe:
        probe(a.keep)
    elif a.panel:
        panel(a.keep)
    elif a.makefile:
        makefile(a.keep)
    elif a.compress:
        return compress(a.keep)
    elif a.make:
        return make(a.keep)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

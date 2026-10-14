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
import sdhuff                                           # noqa: E402

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

# Chosen to separate the header fields from each other, not to be
# convenient: the first specimen had its data size, its "second" size and
# its name length all indistinguishable from one another.
from ndd import make_rsrc, MAC_EPOCH_1990, MAC_EPOCH_1995   # noqa: E402

SUBJECTS = [
    # data 11,136 / no resource fork / 5-char name — the baseline
    ("Alpha", "TEXT", "ttxt", SUBJECT, b"", None),
    # a RESOURCE fork, so the two size fields at +0 and +4 come apart
    ("Forked", "PICT", "8BIM", SUBJECT[:3000],
     make_rsrc(b"\x1eSuperDisk single-file probe"), None),
    # distinct dates, so any date field shows itself
    ("Dated", "APPL", "MyAp", SUBJECT[:2000], b"",
     (MAC_EPOCH_1990, MAC_EPOCH_1995)),
    # a long name, to confirm the Pascal string and where the body starts
    ("LongerNameHere 12345", "TEXT", "ttxt", SUBJECT[:1500], b"", None),
    # over 32 KB of output, so the block chain has to be more than one
    ("Big", "TEXT", "ttxt", SUBJECT * 4, b"", None),
]


def session(tag, subjects=None):
    from ndd import macbinary_dated                      # noqa: E402
    work = R.work_tmp("sdwork-")
    mbs = []
    for i, (n, t, c, d, r, dates) in enumerate(subjects or SUBJECTS):
        p = os.path.join(work, "s%d.bin" % i)
        mb = (macbinary_dated(n, t, c, d, r, *dates) if dates
              else macbinary(n, t, c, d, r))
        open(p, "wb").write(mb)
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


# The settings page, measured off makefile/07-next-page.png. Three axis
# icons down the left — the help text calls them the can, the rabbit and
# the elephant — and three value buttons to their right that swap when an
# axis is chosen.
AXIS = {"compress": (133, 105), "speed": (133, 182), "memory": (133, 250)}
VALUE = [(180, 74), (180, 99), (180, 123)]
LAST_PAGE = (205, 303)


def settings_page(s):
    """Get from the panel's first page to the settings page."""
    s.mac.click(*MORE_OPTIONS)
    time.sleep(3.0)
    s.mac.click(*NEXT_PAGE)
    time.sleep(3.0)


def axes(keep=False):
    """Photograph each axis's value buttons.

    The three values are not labelled until their axis is chosen, and the
    help text only hints at them ("the rabbit will jump slower, indicating
    the 'Fast' speed"). What they actually say decides how many runs the
    method sweep needs.
    """
    s, work, img = session("axes")
    try:
        open_panel(s)
        settings_page(s)
        s.shot("settings", wait=4.0)
        for name, xy in AXIS.items():
            s.mac.click(*xy)
            s.shot("axis-" + name, wait=4.0)
    finally:
        time.sleep(3)
        s.close()
    print("sdcompress: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# One subject per setting, all holding the SAME bytes, so the only thing
# that differs between the outputs is the setting. Make File writes
# `<name>.x` beside its input and never asks where, so distinct names are
# how the outputs are told apart.
SWEEP_DATA = (b"Alysis SuperDisk! settings sweep. " * 260 +
              bytes(bytearray(range(256))) * 6)
# The Speed axis first and alone: it is the one with three values over a
# family the method table calls SlowFastA, SlowFastB and SlowFastC, and a
# shorter sweep is a sweep that finishes. Names deliberately unlike any
# control panel's, because a run that loses the panel types them into the
# Finder — one did, and renamed a control panel to "Coff".
# Each entry is a name and the settings to apply before compressing it.
# Speed alone found method 6 where the default gives 1; pinning Speed at
# "Fast" and walking Compress is the next place a method could change.
SWEEP = [("Zfast", [("speed", 0)]),
         ("Zfaster", [("speed", 1)]),
         ("Zfastest", [("speed", 2)]),
         ("Zfastoff", [("speed", 0), ("compress", 0)]),
         ("Zfasttight", [("speed", 0), ("compress", 1)]),
         ("Zfasttighter", [("speed", 0), ("compress", 2)])]


def set_axis(s, axis, value, tag):
    """Choose an axis, then one of its three values.

    The panel's own text: changes "remain in effect until you change them
    again, as long as you activate them by closing the control panel."
    So the caller closes and reopens before compressing anything.
    """
    s.mac.click(*AXIS[axis])
    time.sleep(2.5)
    s.mac.click(*VALUE[value])
    time.sleep(2.0)
    s.shot("set-" + tag, wait=1.0)


def reopen_panel(s, tag):
    """Close the panel to activate the setting, then open it at page 1.

    Cmd-W, not the close box: a click at the measured close-box
    coordinate did NOT close the window in one run, and the next click —
    "Make File" at a page-1 coordinate — landed on the settings page's
    "Off" button instead, so no dialog opened and the name meant for it
    was typed into the Finder, renaming a control panel to "Coff".
    Closing by keystroke removes the coordinate from the chain.

    Reopening lands on whichever page was last shown, so "Last Page" is
    pressed twice to walk back to the front before anything is clicked
    there.
    """
    s.mac.command_key("w")
    s.shot("closed-" + tag, wait=5.0)
    s.mac.key("Escape")
    time.sleep(0.6)
    s.mac._xdo("key", "space")
    time.sleep(1.5)
    s.mac.command_key("o")
    s.shot("reopened-" + tag, wait=14.0)
    for _ in range(2):
        s.mac.click(*LAST_PAGE)
        time.sleep(2.5)
    s.shot("page1-" + tag, wait=2.0)


def sweep(keep=False):
    """Compress the same bytes once per setting and report each method."""
    s, work, img = session("sweep",
                           [(n, "TEXT", "ttxt", SWEEP_DATA, b"", None)
                            for n, _st in SWEEP])
    try:
        open_panel(s)
        first = True
        for name, settings in SWEEP:
            settings_page(s)
            for axis, value in settings:
                set_axis(s, axis, value, "%s-%s" % (name, axis))
            reopen_panel(s, name)
            make_one(s, name, name, first)
            first = False
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    sweep_report(img, s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def sweep_report(img, shots):
    """The method each setting produced, read out of the first block."""
    import struct
    from superdisk import read_forks                    # noqa: E402
    os.makedirs(shots, exist_ok=True)
    got = read_forks(img)
    print("sdcompress: setting -> method")
    for name, settings in SWEEP:
        blob = None
        for path, (_t, _c, data, _r) in got.items():
            if path[-1] == name + ".x":
                blob = data
        if blob is None:
            print("  %-14s %-22s (no output)" % (name, settings))
            continue
        open(os.path.join(shots, name + ".x"), "wb").write(blob)
        try:
            nlen = blob[30]
            body = 31 + nlen
            body += body & 1
            clen, ulen, meth = struct.unpack_from(">HHH", blob, body)
            stored = "stored" if (clen & 0x8000) else "method %d" % meth
            print("  %-14s %-22s %-10s  %d -> %d bytes"
                  % (name, settings, stored,
                     struct.unpack_from(">I", blob, 4)[0], len(blob)))
        except Exception as e:
            print("  %-14s %-22s unreadable (%s)" % (name, settings, e))


# Subjects sized to put the END of a coded flag bitmap exactly on a 32-bit
# refill boundary. That is the one place Alysis's own two implementations
# disagree — the 1991 self-extractor this engine follows puts the literals at
# the bit reader's cursor plus two, the 1992 Add-In Module reads one refill
# further (OPEN_ITEMS.md, FORMATS.md's method table). One block per subject,
# because a file under 32 KB is one block, so `ulen` IS the subject's size
# and the bitmap is ceil(ulen/8) BYTES.
#
# The first four subjects (2026-08-25) were sized `ceil(size/8) % 4 == 0`,
# which is a rule about a flat 8-bit code and about nothing the panel writes;
# all four missed, and the conclusion drawn was that a subject size cannot
# reach the boundary at all. **Measured 2026-08-28** (`tools/sdhuff.py`, over
# those same four blocks): the panel codes each flag BYTE in ONE bit — 0xff,
# eight predictions right — and this subject's five other flag bytes in two,
# so the bitmap is `nflags + 5` bits. The four came to 130, 133, 260 and 261
# bits: 2, 5, 4 and 5 past a refill.
#
#   nflags = ceil(size/8),  bits = nflags + 5,  bits % 32 == 0  ->  on it
BOUNDARY = [("Qhit1", 1240),       # 155 flag bytes -> 160 bits: ON it
            ("Qoff1", 1248),       # 156 -> 161: one bit past, the control
            ("Qhit2", 2008),       # 251 -> 256 bits: ON it
            ("Qoff2", 2016)]       # 252 -> 257: the control


def boundary(keep=False):
    """Ask the 1991 compressor for a block on the refill boundary.

    Speed "Fast" is what the sweep found produces method 6 — the wide
    variant with a Huffman-coded flag bitmap — where the default gives
    method 1 and no bitmap to code.
    """
    s, work, img = session("boundary",
                           [(n, "TEXT", "ttxt", SWEEP_DATA[:sz], b"", None)
                            for n, sz in BOUNDARY])
    try:
        open_panel(s)
        settings_page(s)
        set_axis(s, "speed", 0, "fast")
        reopen_panel(s, "fast")
        for i, (name, _sz) in enumerate(BOUNDARY):
            make_one(s, name, name, i == 0)
        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    rc = boundary_report(img, s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return rc


def boundary_report(img, shots):
    """What the compressor wrote, and whether this engine reads it back.

    The verdict is one comparison: the subject bytes that went in against
    what `macextract x` gets out. If a block on the boundary comes back
    byte-exact, this engine's reading is the compressor's, and the 1992
    module — which `tools/sdmodule/run_sdmodule.py` will then disagree
    with on the same file — is the one that is wrong.
    """
    import struct
    from superdisk import read_forks                    # noqa: E402
    os.makedirs(shots, exist_ok=True)
    got = read_forks(img)
    bad = 0
    for name, size in BOUNDARY:
        blob = None
        for path, (_t, _c, data, _r) in got.items():
            if path[-1] == name + ".x":
                blob = data
        if blob is None:
            print("sdcompress: %-10s (no output)" % name)
            bad += 1
            continue
        out = os.path.join(shots, name + ".x")
        open(out, "wb").write(blob)
        nlen = blob[30]
        body = 31 + nlen
        body += body & 1
        clen, ulen, meth = struct.unpack_from(">HHH", blob, body)
        m = sdhuff.flag_bits(blob[body + 6:body + (clen & 0x7FFF)], ulen) \
            if not (clen & 0x8000) and sdhuff.coded_bitmap(meth) else None
        nflags = sdhuff.nflags_for(ulen)
        tmp = tempfile.mkdtemp(prefix="sdb-")
        try:
            subprocess.run([cli(), "x", "-o", tmp, out],
                           capture_output=True, text=True)
            f = os.path.join(tmp, name)
            back = open(f, "rb").read() if os.path.exists(f) else b""
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        ok = back == SWEEP_DATA[:size]
        bad += not ok
        where = ("no coded bitmap" if m is None else
                 "RUN, no bits" if m["run"] else
                 "%d bits, %%32=%d%s" % (m["bits"], m["bits"] % 32,
                                         " ON THE BOUNDARY"
                                         if m["boundary"] else ""))
        print("sdcompress: %-10s ulen %5d method %2d flags %4d %-26s -> %s"
              % (name, ulen, 0 if (clen & 0x8000) else meth, nflags, where,
                 "byte-exact" if ok else "WRONG"))
    print("sdcompress: specimens in %s — now run "
          "tools/sdmodule/run_sdmodule.py, which grades the same blocks "
          "through the 1992 module" % shots)
    return 1 if bad else 0


def make_one(s, name, tag, first):
    """One trip through "Make File" and its standard file dialog."""
    s.mac.click(*MAKE_FILE)
    s.shot("dialog-" + tag, wait=10.0)
    if first:
        s.mac.click(*SF_DESKTOP)
        time.sleep(2.0)
        s.mac._xdo("type", "--delay", "150", "SDwork")
        time.sleep(1.5)
        s.mac.key("Return")
        s.shot("in-volume-" + tag, wait=8.0)
    s.mac._xdo("type", "--delay", "150", name)
    time.sleep(2.0)
    s.shot("picked-" + tag, wait=0.5)
    s.mac.key("Return")
    s.shot("done-" + tag, wait=30.0)
    s.mac.key("Return")                     # dismiss whatever it says
    time.sleep(3.0)


def specimens(keep=False):
    """Compress every subject, so the header fields can be told apart.

    The first specimen had its data size, its second size field and its
    name length all equal or zero, which is exactly the shape that makes
    a layout look obvious and be wrong.
    """
    s, work, img = session("specimens")
    try:
        open_panel(s)
        for i, (name, _t, _c, _d, _r, _dt) in enumerate(SUBJECTS):
            make_one(s, name, name.split()[0][:8], i == 0)
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


def verify(keep=False):
    """Read the specimens back and compare with the bytes that went in.

    The header layout was derived from these five, so this is the loop
    that keeps it honest: change the reader and this says so without
    booting anything. Resource forks are compared with bytes 16..127
    masked, the convention `vmac_check.py` uses — the Resource Manager
    stamps that window whenever it touches a file.
    """
    spec = os.path.join(SPECIMENS, "specimens")
    if not os.path.isdir(spec):
        raise SystemExit("sdcompress: no specimens yet — run --specimens")
    bad = 0
    for name, _t, _c, data, rsrc, _d in SUBJECTS:
        f = os.path.join(spec, name + ".x")
        if not os.path.exists(f):
            print("sdcompress: %-22s MISSING" % name)
            bad += 1
            continue
        tmp = tempfile.mkdtemp(prefix="sdv-")
        try:
            r = subprocess.run([cli(), "x", "--forks", "hidden", "-o", tmp, f],
                               capture_output=True, text=True)
            gd = gr = b""
            for root, _dd, fs in os.walk(tmp):
                for x in fs:
                    q = os.path.join(root, x)
                    if x.startswith("._"):
                        gr = open(q, "rb").read()
                    else:
                        gd = open(q, "rb").read()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        mask = (lambda b: b[:16] + b"\0" * 112 + b[128:]
                if len(b) >= 128 else b)
        ok = (r.returncode == 0 and gd == data and mask(gr) == mask(rsrc))
        print("sdcompress: %-22s data %-6d rsrc %-4d  %s"
              % (name, len(gd), len(gr),
                 "byte-exact" if ok else "DIFFERS"))
        bad += 0 if ok else 1
    swp = os.path.join(SPECIMENS, "sweep")
    n = 0
    if os.path.isdir(swp):
        import struct
        for name, settings in SWEEP:
            f = os.path.join(swp, name + ".x")
            if not os.path.exists(f):
                continue
            n += 1
            blob = open(f, "rb").read()
            nlen = blob[30]
            body = 31 + nlen
            body += body & 1
            clen, ulen, meth = struct.unpack_from(">HHH", blob, body)
            tmp = tempfile.mkdtemp(prefix="sdv-")
            try:
                r = subprocess.run([cli(), "x", "--forks", "hidden",
                                    "-o", tmp, f], capture_output=True,
                                   text=True)
                gd = b""
                for root, _dd, fs in os.walk(tmp):
                    for x in fs:
                        if not x.startswith("._"):
                            gd = open(os.path.join(root, x), "rb").read()
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            ok = r.returncode == 0 and gd == SWEEP_DATA
            print("sdcompress: %-14s %-10s  %s"
                  % (name, "stored" if (clen & 0x8000) else "method %d" % meth,
                     "byte-exact" if ok else "DIFFERS"))
            bad += 0 if ok else 1
    print("sdcompress: %d of %d byte-exact against the bytes that went in"
          % (len(SUBJECTS) + n - bad, len(SUBJECTS) + n))
    return 1 if bad else 0


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
    ap.add_argument("--sweep", action="store_true",
                    help="compress the same bytes once per setting")
    ap.add_argument("--axes", action="store_true",
                    help="photograph each settings axis's values")
    ap.add_argument("--verify", action="store_true",
                    help="read the specimens back and compare")
    ap.add_argument("--specimens", action="store_true",
                    help="compress every subject, for the header layout")
    ap.add_argument("--compress", action="store_true",
                    help="compress a subject and report the method")
    ap.add_argument("--make", action="store_true",
                    help="rename subjects so SuperDisk! compresses them")
    ap.add_argument("--boundary", action="store_true",
                    help="compress subjects sized to land a coded flag "
                         "bitmap on a 32-bit refill boundary")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if a.keep:      # guard deletes images at exit otherwise
        os.environ["HARNESS_KEEP_IMAGES"] = "1"
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
    elif a.sweep:
        return sweep(a.keep)
    elif a.axes:
        axes(a.keep)
    elif a.verify:
        return verify(a.keep)
    elif a.specimens:
        return specimens(a.keep)
    elif a.compress:
        return compress(a.keep)
    elif a.make:
        return make(a.keep)
    elif a.boundary:
        return boundary(a.keep)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

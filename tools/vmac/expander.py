#!/usr/bin/env python3
"""expander.py — the yardstick: this application beside StuffIt Expander 4.0.2.

Every Mac Plus figure this project publishes is absolute — 141 s for a 278 KB
StuffIt archive — and an absolute number answers the wrong question. What a
user weighs is whether this is faster or slower than the free tool they would
otherwise run on that machine. Until this file existed, nothing here had ever
executed that tool: FORMATS.md, *Compared with StuffIt Expander 4.0.2*, is
Aladdin's documentation set against our measurements, and says so.

This boots both applications on the same emulated Mac Plus, at authentic
7 MHz, over the same archive on the same volume, and times them with one
instrument.

    tools/vmac/expander.py --fetch                  # download 4.0.2, unpack it
    tools/vmac/expander.py --sizes                  # both SIZE resources; no emulator
    tools/vmac/expander.py fixtures/derived-Export.sit
    tools/vmac/expander.py --json y.json --only ours fixtures/*.sit

ONE EMULATOR AT A TIME, and nothing else on this box: at 1x the emulator paces
itself against real time, so a second CPU-heavy process inflates the very
number being measured (tools/vmac/README.md).

The instrument
--------------
Both applications are driven to the same point — a Standard File dialog with
the archive selected — and then timed from **the Return or click that starts
the work** to **the last change of the Mac's screen buffer** before it holds
still for `--quiet` seconds. Expander has no way to be asked what it took, so
the clock is outside both applications: macclock.py reads the emulated
`Ticks` and screen buffer from Mini vMac's memory at 50 Hz, and the figure is
emulated ticks / 60.15 — Mac Plus seconds, to about two ticks — with host
seconds and their ratio beside it. `--calibrate` times clockcal's known
waits through the same code (tools/vmac/README.md has the readings).

Until 2026-10-19 this was screenshots every `--poll` seconds, a one-poll
(±3 s) error and ~50 ms of stolen CPU a poll.

What it cannot see
------------------
- **Whether Expander's output is correct.** The run is graded on whether it
  produced files at all. Nothing here compares its bytes with ours.
- **Anything about the formats Expander cannot open alone.** 4.0.2 needs
  DropStuff with Expander Enhancer — System 7 only, and not free — for zip,
  gzip, tar, uuencode, ARC and the rest, so this compares the four families it
  handles on System 6 by itself. A comparison over the other twenty would be
  measuring an unavailable configuration.
- **Repaint gaps.** "Finished" here is "the screen stopped changing for
  `--quiet` seconds". Both progress indicators repaint far more often than
  that, but neither guarantees it — the output check is what catches a stop
  called too early, by finding the extraction incomplete.
- Everything macclock.py cannot see: emulator fidelity, disk time, ticks
  lost to masked interrupts, the pointer in the screen buffer.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
import run as R                                              # noqa: E402
import guard                                                 # noqa: E402
import macclock as MC                                        # noqa: E402
import checkdisk as CD                                       # noqa: E402
from interactive import Mac, build_interactive_app           # noqa: E402
from arcmac import macbinary                                 # noqa: E402
from mkboot import HFS                                       # noqa: E402
from spacesaver import resources                             # noqa: E402

# StuffIt Expander 4.0.2, April 1996, free — Macintosh Garden's copy, which is
# the one FORMATS.md's capability table was read out of. MacBinary around a
# StuffIt self-extracting archive around a 400K HFS image; `macextract x`
# walks all three, and the image it produces is byte-identical to unar's.
GARDEN_PAGE = "https://macintoshgarden.org/apps/stuffit-expander-402"
DIST_SHA = "00e48e48cabc8a9dd295e12531193b3f37c46f87788daf64d1c219d6b11e01a1"
IMG_MD5 = "888c0ca0b93f6ee0ff67e89926e20f83"   # the 400K image inside it

WORK = os.path.join(R.VMAC_HOME, "expander")
DIST = os.path.join(WORK, "stuffit_expander_4.0.2.sea_.bin")
APPBIN = os.path.join(WORK, "Expander.bin")
APP_NAME = "Expander"           # also the boot-block shell name, max 15 bytes

# The four families 4.0.2 opens with no add-on, and the type/creator a real
# one carries. Standard File is what needs them: our own application asks for
# every file (`SFGetFile(..., -1, ...)`), Expander's dialog filters on type,
# so an archive copied as a plain data fork is invisible to it — which is what
# tools/vmac/cptsegment.py hit first, and mkboot's --macbin exists for.
TYPES = {
    "StuffIt": ("SIT!", "SIT!"),
    "StuffIt 5": ("SIT!", "SIT!"),
    "Compact Pro": ("PACT", "CPCT"),
    "BinHex 4": ("TEXT", "ttxt"),
    "MacBinary": ("BINA", "????"),
}


def cli():
    if not os.path.exists(CD.CLI):
        raise SystemExit(f"expander: no CLI at {CD.CLI} — run `make BUILD=build/rel`")
    return CD.CLI


def sniff(path):
    """The engine's own name for a file's format, e.g. "Compact Pro"."""
    return subprocess.run([cli(), "sniff", path], capture_output=True,
                          text=True).stdout.strip()


# ------------------------------------------------------------------
# Fetching
# ------------------------------------------------------------------

def fetch(force=False):
    """Download the distribution, verify it, and rebuild the application.

    Macintosh Garden signs its download URLs and answers a bare GET with
    HTTP 418, so the page is fetched first with a cookie jar and the signed
    link taken out of it — the same two-step arcmac.py uses.
    """
    os.makedirs(WORK, exist_ok=True)
    if force or not os.path.exists(DIST):
        ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
        jar = os.path.join(WORK, "jar")
        page = os.path.join(WORK, "page.html")
        subprocess.run(["curl", "-sS", "-m", "120", "-L", "-A", ua,
                        "-c", jar, "-b", jar, "-o", page, GARDEN_PAGE],
                       check=True)
        html = open(page, errors="replace").read()
        url = next((u for u in html.split('"')
                    if "download.macintoshgarden.org" in u
                    and "stuffit_expander_4.0.2" in u), None)
        if not url:
            raise SystemExit("expander: no download link on the Garden page")
        subprocess.run(["curl", "-sS", "-m", "300", "-L", "-A", ua, "-c", jar,
                        "-b", jar, "-e", GARDEN_PAGE, "-o", DIST,
                        "https:" + url.lstrip(":")], check=True)
    blob = open(DIST, "rb").read()
    got = hashlib.sha256(blob).hexdigest()
    if got != DIST_SHA:
        raise SystemExit(f"expander: {DIST} has sha256 {got}, expected "
                         f"{DIST_SHA} — the upstream file changed; check it "
                         f"by hand rather than editing this constant")

    tree = os.path.join(WORK, "dist")
    shutil.rmtree(tree, ignore_errors=True)
    subprocess.run([cli(), "x", "-o", tree, DIST], check=True,
                   capture_output=True)
    img = os.path.join(tree, "StuffIt Expander 4.0.2.img")
    if not os.path.exists(img):
        raise SystemExit("expander: no disk image inside the self-extractor")
    md5 = hashlib.md5(open(img, "rb").read()).hexdigest()
    if md5 != IMG_MD5:
        raise SystemExit(f"expander: the image inside is md5 {md5}, expected "
                         f"{IMG_MD5}")
    app = app_from_image(img)
    shutil.copyfile(app, APPBIN)
    d, r = forks(APPBIN)
    print(f"expander: {APPBIN} — {len(r)} B of resources, "
          f"version {version(r)}, SIZE {size_str(r)}")


def app_from_image(img):
    """Copy the application off the 400K HFS image, as MacBinary.

    hfsutils refuses a volume "smaller than 800K", which is the whole of why
    FORMATS.md said this needed "an HFS reader this machine does not have".
    It does not: the image is padded to 800K in a temporary copy and mounts.
    Reading only ever follows the MDB's own extents, so the padding is never
    looked at.
    """
    tmp = os.path.join(WORK, "padded.img")
    shutil.copyfile(img, tmp)
    with open(tmp, "r+b") as f:
        f.truncate(max(os.path.getsize(img), 800 * 1024))
    out = os.path.join(WORK, "app.bin")
    hfs = HFS(tmp)
    try:
        # The application is the one APPL on the volume, found rather than
        # typed: its name carries a trademark sign (MacRoman 0xAA) and it
        # sits in a folder whose name is not the volume's.
        found, stack = None, [hfs.vol + ":"]
        while stack:
            d = stack.pop()
            # `invisible=True`: the walk looks for the ONE APPL on the
            # volume, and a listing that hides an invisible file would
            # report "no application" for one that is there (2026-09-23).
            for isdir, name in hfs.ls(d, invisible=True):
                child = d.rstrip(":") + ":" + name
                if isdir:
                    stack.append(child)
                elif "APPL/SITx" in hfs.run("hdir", child).stdout:
                    found = child
        if not found:
            raise SystemExit("expander: no APPL on the distribution image")
        hfs.run("hcopy", "-m", found, out)
    finally:
        hfs.close()
        os.remove(tmp)
    return out
    return out


# ------------------------------------------------------------------
# Reading an application without running it
# ------------------------------------------------------------------

def forks(macbin):
    """(data, resource) out of a MacBinary file."""
    b = open(macbin, "rb").read()
    dlen, rlen = struct.unpack(">II", b[83:91])
    p = 128 + (dlen + 127) // 128 * 128
    return b[128:128 + dlen], b[p:p + rlen]


def size_res(rsrc):
    """(preferred, minimum) partition in bytes, from 'SIZE' (-1).

    Inside Macintosh VI: a flags word, then the two sizes as longs. This is
    what the Finder's Get Info box shows and what the Process Manager gives
    the application on System 7 and later.
    """
    r = resources(rsrc).get("SIZE", {})
    if -1 not in r:
        return None
    return struct.unpack(">II", r[-1][1][2:10])


def size_str(rsrc):
    s = size_res(rsrc)
    return "unknown" if not s else "%d KB preferred, %d KB minimum" % (
        s[0] // 1024, s[1] // 1024)


def version(rsrc):
    v = resources(rsrc).get("vers", {}).get(1)
    if not v:
        return "unknown"
    n = v[1][6]
    return v[1][7:7 + n].decode("mac-roman", "replace")


def sizes(ours):
    """Both applications' memory partitions. No emulator, no boot."""
    for label, path in (("StuffIt Expander 4.0.2", APPBIN), ("MacExtract", ours)):
        _, r = forks(path)
        print("%-24s %8d B of resources   %s"
              % (label, len(r), size_str(r)))


# ------------------------------------------------------------------
# One timed run
# ------------------------------------------------------------------

def typed_copy(fixture, workdir, expander=True):
    """The fixture as MacBinary carrying the type/creator a real one has.

    Both volumes are built from this one file, so the two applications are
    handed a byte-identical disk and the only difference between the runs is
    which application is on it.
    """
    fmt = sniff(fixture)
    if fmt not in TYPES and expander:
        raise SystemExit(
            f"expander: {os.path.basename(fixture)} is {fmt}, which "
            f"Expander 4.0.2 cannot open without DropStuff with Expander "
            f"Enhancer (System 7, not free) — there is no fair run to make")
    # Our dialog lists every file and the engine sniffs content, so a
    # format Expander cannot open still gets a run of ours alone.
    ftype, creator = TYPES.get(fmt, ("????", "????"))
    name = os.path.basename(fixture)[:31]
    out = os.path.join(workdir, "typed.bin")
    with open(out, "wb") as f:
        f.write(macbinary(name, ftype, creator, data=open(fixture, "rb").read()))
    return out, name, fmt


def ram_size(emu):
    """The emulated machine's RAM in bytes, from the build's own config."""
    cfg = open(os.path.join(R.VMAC_HOME, emu, "cfg", "EMCONFIG.h")).read()
    return sum(int(m, 16) for m in
               re.findall(r"#define kRAM[ab]_Size (0x[0-9A-Fa-f]+)", cfg))


def stopwatch(mac, emu):
    """A macclock.Watch on this Mac's emulated RAM (tools/vmac/macclock.py)."""
    pid = MC.emulator_pid(mac.proc)
    return MC.Watch(MC.MacMemory(pid, ram_size(emu)), hz=50.0)


def timed(watch, act, quiet, timeout, snap=None):
    """Do `act`, then time to the last screen change before `quiet` s still.

    The mark is taken immediately before the action is delivered, in both
    clocks; the end is the last sample at which the Mac's screen buffer
    differed from the one before it. Returns macclock.reading() plus
    `timed_out`, or None if nothing ever changed."""
    t0 = watch.mark()
    act()
    changes, out = watch.until_quiet(quiet, timeout, snap=snap)
    r = MC.reading(t0, changes)
    if r is not None:
        r["timed_out"] = out
    return r


def names_on(img):
    """Every file on an HFS image, as ':'-separated Mac paths."""
    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    try:
        if CD.hfs(env, "hmount", img).returncode != 0:
            return []
        got = sorted(CD.mac_path(n) for n in CD.walk(env))
        CD.hfs(env, "humount")
        return got
    finally:
        shutil.rmtree(home, ignore_errors=True)


def live_names(workdir, before):
    """What the RUNNING emulator has already written to its image.

    A copy is mounted rather than the file itself: hfsutils would open the
    image the emulator is writing, and the run is the thing being measured.
    """
    live = os.path.join(workdir, "live.hfv")
    shutil.copyfile(os.path.join(workdir, "boot.hfv"), live)
    try:
        return [n for n in names_on(live) if n not in before]
    finally:
        os.remove(live)


def run_one(which, appbin, fixture, args, workdir, shots):
    """Boot one application on one archive and time the extraction."""
    typed, macname, fmt = typed_copy(fixture, workdir,
                                     expander=(which == "expander"))
    stock = os.path.join(R.VMAC_HOME, args.system)
    boot = os.path.join(workdir, f"boot-{which}.hfv")
    argv = [sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin,
            boot, "--macbin", f"{typed}:{macname}"]
    if which == "expander":
        argv += ["--app-name", APP_NAME]
    R.sh(*argv)
    before = set(names_on(boot))     # the stock image is not empty: mkboot's
                                     # walk uses `hdir`, which hides invisible
                                     # files, so custom-icon `Icon` files
                                     # survive in folders it could not remove

    scratch = os.path.join(shots, f".{which}.png")
    shot = lambda n: mac.shot(os.path.join(shots, f"{which}-{n}.png"))  # noqa: E731
    mac = Mac(boot, args.emu, workdir)
    elapsed = quitsecs = None
    mid = post = None
    quitdrew = flush = None
    watch = timing = None
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit(f"expander: the {which} machine never booted")
        shot("1-launched")
        # Nothing here has assigned X keyboard focus yet: settle() only
        # screenshots, and origin() is where interactive.py's focus call
        # lives. Without it Command-E goes to the root window and the Mac
        # never sees a keystroke — which looks exactly like an application
        # that ignores its own menu shortcut.
        mac.origin(cached=False)
        if which == "expander":
            # Command-E is "Expand..." (MENU 129, read out of the application
            # itself). Everything Expander does that is not a drag lands
            # there, and a Command key avoids the pointer entirely.
            mac.command_key("e")
            time.sleep(3.0)
            shot("2-open")
            # No click on the file list: Expander's dialog is Standard File
            # with Aladdin's own DLOG, so the list sits ~48 px higher than
            # the stock one and the row interactive.py measured is BELOW the
            # last item. Clicking there picked `System Folder` and Return
            # opened it, photographed. The first row is preselected and
            # mkboot leaves exactly one expandable file on the volume.
            # Pointer onto the button first, THEN the mark, then the press:
            # a Mac Plus draws its own pointer into the screen buffer, so
            # the move is a screen change the stopwatch would otherwise
            # count as the application's first response.
            ox, oy = mac.origin()
            mac._xdo("mousemove", str(ox + EXPAND_BUTTON[0]),
                     str(oy + EXPAND_BUTTON[1]))
            time.sleep(0.6)
            act = lambda: mac._xdo("click", "1")       # noqa: E731
        else:
            # NOT a click on the first row, which is what this did until
            # 2026-09-20: Standard File sorts by name and our dialog shows
            # every file, so the first row is the archive only when its
            # name happens to sort first. The Finder's own `Desktop` file
            # is on this volume, so `macburger-helper.hqx` and
            # `unshar-111.hqx` both sat BELOW it — and the run extracted
            # `Desktop`, reported "This file could not be extracted" in
            # three seconds, and printed a number. `derived-FirstClass_
            # Demo.cpt` sorts before `Desktop` and is why this went unseen.
            # Type-ahead names the file instead of guessing where it is.
            select_by_name(mac, macname)
            shot("2-selected")
            mac.key("Return")            # Open -> destination dialog
            time.sleep(3.0)
            shot("2-destination")
            act = lambda: mac._xdo("key", "Return")    # Save -> beside it
        watch = stopwatch(mac, args.emu)
        started = os.path.join(shots, f"{which}-2b-started.png")
        timing = timed(watch, act, args.quiet, args.timeout,
                       snap=(2.0, lambda: mac.shot(started)))
        elapsed = None if timing is None or timing["timed_out"] \
            else timing["mac_s"]
        shot("3-finished")
        # Is the output on the host image BEFORE the application is told to
        # quit? Nothing had ever asked: the volume was only ever read after
        # the emulator had been killed, so "Expander's writes are still in
        # the File Manager's cache" was an inference from one empty image
        # and not an observation of when the bytes land. The emulator writes
        # to workdir/boot.hfv as it runs, so a read-only mount of a COPY
        # answers it and cannot disturb the run.
        mid = live_names(workdir, before)
        # The quit, timed — because the two applications do not have their
        # output in the same place when the clock above stops.
        #
        # Our sink calls FlushVol after closing each fork
        # (mac/macextract_mac.c), so its files are on the image the moment
        # the alert goes up. Expander leaves its writes in the File
        # Manager's cache: a 278 KB archive expanded for 56 s, progress
        # window photographed every step of it, and the image afterwards
        # held nothing at all. So `seconds` is "the screen stopped
        # changing" for both, and it is ALSO "the output is on the volume"
        # for one of them only.
        #
        # Quitting is what commits the other one, and how long that takes
        # is the size of the asymmetry. It is timed the same way as the
        # extraction and reported separately: `seconds` keeps the meaning
        # every published figure was taken with, `quit` is new, and the
        # comparison a user cares about — archive in, files on disk — is
        # the sum.
        if which == "expander":
            qmark = watch.mark()
            mac.command_key("q")
        else:
            mac.key("Return")            # dismiss the alert or the report
            time.sleep(2.0)
            qmark = watch.mark()
            mac.command_key(".")         # Cancel the next SFGetFile -> quit
        # How long the commit itself takes, watched on the host rather than
        # on the screen: Expander's writes land at the quit and the screen
        # never repaints, so the only instrument that can see this one is
        # the image file. Ours is already complete here and returns 0.
        flush = None
        if not mid:
            t0 = time.time()
            while time.time() - t0 < 180.0:
                if live_names(workdir, before):
                    flush = round(time.time() - t0, 1)
                    break
                time.sleep(2.0)
        else:
            flush = 0.0
        qch, _ = watch.until_quiet(min(args.quiet, 30.0),
                                   min(args.timeout, 600.0))
        q = MC.reading(qmark, qch)
        quitsecs = q["mac_s"] if q else 0.0
        shot("4-quit")
        post = live_names(workdir, before)
        # Whether the quit key did anything at all. An application that is
        # still running photographs identically, and a quit that never
        # happened would otherwise be read as a quit that cost nothing.
        quitdrew = open(os.path.join(shots, f"{which}-3-finished.png"), "rb").read() \
            != open(os.path.join(shots, f"{which}-4-quit.png"), "rb").read()
    finally:
        if watch is not None:
            watch.mem.close()
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    written = names_on(os.path.join(workdir, "boot.hfv"))   # Mac()'s own copy
    produced = [n for n in written if n not in before]
    return {"app": which, "fixture": os.path.basename(fixture), "format": fmt,
            "seconds": None if elapsed is None else round(elapsed, 1),
            "quit": None if quitsecs is None else round(quitsecs, 1),
            "to_disk": None if elapsed is None or quitsecs is None
                       else round(elapsed + quitsecs, 1),
            "on_disk_before_quit": mid,
            "on_disk_after_quit": post,
            "quit_redrew": quitdrew,
            "flush_seconds": flush,
            "timing": timing,
            "output": produced}


# The Expand button in Aladdin's dialog, measured off this harness's own
# `expander-2-open.png`. Drive, the nearest button an aimless click could
# reach, is 46 px above it and greyed.
#
# Pressed with the mouse rather than with Return, which is what the three
# lessons in interactive.py argue against — and deliberately, because it is
# what every figure in FORMATS.md was taken with. Return was tried first and
# looked like it did nothing; the volume it left behind was empty for the
# FLUSH reason below, not because of the key, so whether Return works here is
# untested rather than disproved. Re-testing it would cost one boot.
EXPAND_BUTTON = (379, 194)


def select_by_name(mac, macname):
    """Select a file in Standard File by typing its name.

    Standard File selects the first item whose name begins with what has
    been typed, and keeps matching while the keystrokes keep coming
    (Inside Macintosh I-519, the standard file package's key handling).
    Eight characters is more than enough to separate any fixture from
    `Desktop`, `System Folder` and the Expander's folder, and stopping at
    the first character that is not plain ASCII keeps xdotool out of
    keysym trouble — a prefix that is short is still a prefix."""
    prefix = ""
    for ch in macname:
        if not (ch.isalnum() or ch in "-_ ."):
            break
        prefix += ch
        if len(prefix) >= 8:
            break
    if not prefix:
        raise SystemExit(f"expander: cannot type a prefix of {macname!r}")
    mac._xdo("type", "--delay", "80", prefix)
    time.sleep(1.0)


# ------------------------------------------------------------------
# Calibration: a known duration, through the same instrument
# ------------------------------------------------------------------

def build_clockcal():
    """tools/vmac/clockcal, built the way interactive.py builds ours."""
    bdir = os.path.join(R.REPO, "build", "clockcal")
    toolchain = os.environ.get("RETRO68", "/opt/Retro68-build/toolchain")
    subprocess.run(["cmake", "-B", bdir, "-S", os.path.join(HERE, "clockcal"),
                    "-DCMAKE_TOOLCHAIN_FILE=" + os.path.join(
                        toolchain, "m68k-apple-macos", "cmake",
                        "retro68.toolchain.cmake")],
                   check=True, capture_output=True)
    subprocess.run(["cmake", "--build", bdir], check=True, capture_output=True)
    return os.path.join(bdir, "ClockCal.bin")


def calibrate(args, keys):
    """Time clockcal's fixed busy waits with the stopwatch the runs use.

    Each key asks for a known number of ticks (clockcal/main.c); the reading
    should be that many plus the keystroke's latency, in ticks, and that
    many sixtieths of a second in host time if Mini vMac keeps real time.
    'j' and 'k' are 600 and 660 ticks: the end moved by exactly one second,
    which the instrument must see."""
    want = {c: (ord(c) - 96) * 60 for c in "abcdefghijklmnopqrstuvwxyz"}
    want.update({c: int(c) * 600 for c in "123456789"})
    workdir = tempfile.mkdtemp(prefix="clockcal-")
    boot = os.path.join(workdir, "cal.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
         os.path.join(R.VMAC_HOME, args.system), build_clockcal(), boot,
         "--app-name", "ClockCal")
    mac = Mac(boot, args.emu, workdir)
    rows, watch = [], None
    try:
        scratch = os.path.join(workdir, "s.png")
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("expander: clockcal never booted")
        mac.origin(cached=False)
        watch = stopwatch(mac, args.emu)
        for c in keys:
            # The wait draws nothing, so `quiet` must outlast it: a quiet
            # shorter than the silence ends the reading at the START mark
            # (2 ticks, the first time this ran) — the instrument's own
            # blind spot, met on purpose.
            r = timed(watch, lambda: mac._xdo("key", c),
                      want[c] / MC.TICK_HZ + 5.0, 900.0)
            r = dict(r or {}, key=c, asked=want[c])
            rows.append(r)
            print("clockcal %s: asked %5d ticks  read %5s ticks (%+d)  "
                  "%7.3f s Mac  %7.3f s host  ratio %s  first %.3f s"
                  % (c, want[c], r.get("ticks"),
                     (r.get("ticks") or 0) - want[c], r.get("mac_s", 0),
                     r.get("host_s", 0), r.get("ratio"), r.get("first_s", 0)),
                  flush=True)
        mac.shot(os.path.join(args.outdir, "clockcal.png"))
    finally:
        if watch is not None:
            watch.mem.close()
        mac.close()
        shutil.rmtree(workdir, ignore_errors=True)
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fixtures", nargs="*")
    p.add_argument("--fetch", action="store_true",
                   help="download StuffIt Expander 4.0.2 and unpack it")
    p.add_argument("--sizes", action="store_true",
                   help="print both applications' SIZE resources and stop")
    p.add_argument("--only", choices=("ours", "expander"),
                   help="run just one of the two")
    p.add_argument("--emu", default="mv-4M-1x",
                   help="emulator build; only the 1x ones may be quoted")
    p.add_argument("--system", default="System6.hfv")
    p.add_argument("--ours", help="MacBinary of the application to time "
                                  "(e.g. dist/MacExtract.bin); default: "
                                  "build it from source")
    p.add_argument("--repeat", type=int, default=1,
                   help="time each fixture and application this many times")
    p.add_argument("--calibrate", metavar="KEYS",
                   help="time clockcal's known waits instead, e.g. jkjk6")
    p.add_argument("--quiet", type=float, default=60.0,
                   help="seconds the screen must hold still before the work "
                        "is called finished")
    p.add_argument("--timeout", type=float, default=2400.0)
    p.add_argument("--boot-timeout", type=float, default=300.0)
    p.add_argument("-o", "--outdir",
                   help="screenshots; default a run directory under .tmp/")
    p.add_argument("--json")
    p.add_argument("--keep", help="build the disks in this directory and "
                                  "leave them there, to be looked at by hand")
    args = p.parse_args()

    if not args.outdir:
        args.outdir = guard.run_dir("expander")
    os.makedirs(args.outdir, exist_ok=True)
    if args.calibrate:
        rows = calibrate(args, args.calibrate)
        if args.json:
            json.dump(rows, open(args.json, "w"), indent=1)
        return 0
    if args.fetch:
        fetch()
        if not args.fixtures:
            return 0
    if not os.path.exists(APPBIN):
        raise SystemExit("expander: no Expander.bin — run --fetch first")
    ours = args.ours or build_interactive_app()
    if args.sizes:
        sizes(ours)
        return 0
    if not args.fixtures:
        p.error("nothing to time")

    rows = []
    for fixture in args.fixtures:
        for n in range(args.repeat):
            for which, app in (("ours", ours), ("expander", APPBIN)):
                if args.only and args.only != which:
                    continue
                workdir = args.keep or tempfile.mkdtemp(prefix="expander-")
                os.makedirs(workdir, exist_ok=True)
                shots = os.path.join(args.outdir, "%s-%d" % (
                    os.path.basename(fixture).replace(".", "_"), n + 1))
                os.makedirs(shots, exist_ok=True)
                try:
                    row = run_one(which, app, fixture, args, workdir, shots)
                finally:
                    if not args.keep:
                        shutil.rmtree(workdir, ignore_errors=True)
                row["run"] = n + 1
                rows.append(row)
                if args.json:            # after every run: a crash keeps data
                    json.dump(rows, open(args.json, "w"), indent=1)
                t = row["timing"] or {}
                secs = "never settled" if row["seconds"] is None \
                    else "%.2f s" % row["seconds"]
                # The names are the evidence that both applications did the
                # same work, and one fixture here writes 312 of them — so
                # the line says how many and shows the first few; --json
                # keeps every one.
                out = row["output"]
                shown = ", ".join(out[:3]) + (" ..." if len(out) > 3 else "")
                print("expander: %-8s #%d %-32s %-11s %10s  host %s s  "
                      "ratio %s  (+%.1f s to quit)  wrote %d: %s"
                      % (which, n + 1, row["fixture"], row["format"], secs,
                         t.get("host_s"), t.get("ratio"), row["quit"] or 0,
                         len(out), shown or "NOTHING"), flush=True)

    print()
    print("%-30s %-11s %17s %17s %6s" % ("Fixture", "Format", "MacExtract",
                                          "Expander", "ratio"))
    ok = True

    def span(v):
        if not v:
            return "-"
        v = sorted(v)
        med = v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1]
                                                   + v[len(v) // 2]) / 2
        return "%.1f s [%.1f-%.1f]" % (med, v[0], v[-1]), med

    for fixture in args.fixtures:
        base = os.path.basename(fixture)
        got = [r for r in rows if r["fixture"] == base]
        for r in got:
            if r["seconds"] is None or not r["output"]:
                ok = False
        a = span([r["seconds"] for r in got
                  if r["app"] == "ours" and r["seconds"]])
        b = span([r["seconds"] for r in got
                  if r["app"] == "expander" and r["seconds"]])
        print("%-30s %-11s %17s %17s %6s"
              % (base[:30], got[0]["format"] if got else "?",
                 a[0] if a != "-" else "-", b[0] if b != "-" else "-",
                 "%.2fx" % (b[1] / a[1]) if a != "-" and b != "-" else "-"))
    print("\nratio > 1 means Expander took longer. Seconds are Mac Plus "
          "seconds: emulated Ticks / 60.15, median [min-max] over the runs, "
          "from the action to the last change of the Mac's screen buffer.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""interactive.py — drive the INTERACTIVE Mac application under Mini vMac.

`run.py` replays fixtures through the `-DUNC_MAC_AUTOTEST` build, which has no
user interface at all: no SFGetFile, no progress dialog, no alerts. That build
proves the engine and the sink. It says nothing about the application a person
actually uses, and the whole of that surface went unverified when the sink was
rewritten to stream its writes.

This drives the real application the way a person would — clicking Open in
SFGetFile, watching the progress dialog, pressing Cmd-. — and captures a
screenshot at each step. **The screenshots are most of the result**: there is
no bit grid to decode here, so a human (or a model that can see) looks at them
and decides. Every phase but `--e2e` does end on ONE thing that can fail by
itself, read off the volume the Mac wrote to, because a screenshot of the wrong
dialog looks exactly like a screenshot of the right one — this phase once
reported an extraction "settled after ~134s" having spent all of it in a
"Replace existing" alert. (`--e2e` has no such line: what it is for is a
photograph, an extracted application drawing its own splash screen.) The checks
that still need a real machine are in MANUAL_TESTS.md.

    tools/vmac/interactive.py fixtures/derived-EmpireBuilderDemo.sit -o /tmp/shots

**Run one phase at a time.** The waits between clicks are seconds, and a Mac
sharing its core with a second emulator drops below 1x and desynchronises the
whole choreography without anything failing.

Five phases, because they need different machines: the default, `--e2e`,
`--wd`, `--dest` and `--segments`. `--help` describes the last three, and
`--drop`, which photographs what the FINDER does with an archive dragged onto
the application's icon.

The default one installs the application as the boot shell (as every other
harness here does) and concentrates on cancelling:

    1-launched.png    application is up, SFGetFile listing the archive
    1b-destination.png where should the files go? (SFPutFile, opened in the
                      archive's own folder, so Return means "beside it")
    2-extracting.png  progress dialog, part way through
    3-cancelled.png   the alert after the Cancel button
    4-back.png        back at SFGetFile, ready for another file
    6-cmd-period.png  the same cancel reached by Cmd-. instead
    5-complete.png    a second run allowed to finish: the success alert

`--e2e` keeps the FINDER instead, and follows the user's whole story — which
needs a Finder at both ends, to launch the application and then to launch what
the application extracted:

    e2e-1-desktop.png               booted to the Finder
    e2e-2-volume.png                boot volume open, showing the application
    e2e-3-sfgetfile.png             launched by double-click
    e2e-4-other-volume.png          Drive switched to the second volume
    e2e-5-back-to-boot.png          Drive switched back
    e2e-5b-destination.png          the destination dialog
    e2e-6-complete.png              "Extraction complete."
    e2e-7-back-in-finder.png        quit; the extracted files are in the window
    e2e-8-extracted-app-running.png the extracted APPL, double-clicked

Mini vMac maps the host Alt key to the Mac Command key; see command_key() for
why the chord is sent as an explicit hold rather than an xdotool chord.
"""
import argparse, glob, os, re, shutil, signal, subprocess, sys, tempfile, time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402
from mkboot import LISTING_DATE                              # noqa: E402
import checkdisk as CD                                       # noqa: E402
from mkboot import FINDER_OWN                                # noqa: E402

# `hdir`'s name column on a BYTES listing — a text listing cannot carry the
# carriage return inside `Icon\r`.
LISTING_DATE_B = re.compile(LISTING_DATE.pattern.encode("ascii"))


def build_interactive_app(defines=()):
    """Build the normal (non-autotest) application, returning its MacBinary.

    `defines` are probe switches (`-D UNC_AT_RESERVE`), each turned into a -D
    by mac/CMakeLists.txt. The environment is otherwise stripped of UNC_MAC_*
    and UNC_AT_* so that a stray export cannot silently change what is being
    driven; each combination gets its own build directory, because CMake reads
    these at CONFIGURE time and reusing one would keep the first for ever."""
    tag = "-".join(["interactive"] + sorted(d.lower() for d in defines))
    bdir = os.path.join(R.REPO, "build", "mac-" + tag)
    toolchain = os.environ.get("RETRO68", "/opt/Retro68-build/toolchain")
    cmakefile = os.path.join(toolchain, "m68k-apple-macos", "cmake",
                             "retro68.toolchain.cmake")
    if not os.path.exists(cmakefile):
        raise SystemExit(f"interactive: no Retro68 toolchain at {toolchain}")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("UNC_MAC_", "UNC_AT_"))}   # plain build
    for d in defines:
        env[d] = "1"
    subprocess.run(["cmake", "-B", bdir, "-S", os.path.join(R.REPO, "mac"),
                    f"-DCMAKE_TOOLCHAIN_FILE={cmakefile}",
                    "-DCMAKE_BUILD_TYPE=Release"],
                   check=True, capture_output=True, env=env)
    subprocess.run(["cmake", "--build", bdir, "--", "-j", str(os.cpu_count())],
                   check=True, capture_output=True, env=env)
    return os.path.join(bdir, "MacExtract.bin")


class Mac:
    """A booted Mini vMac with keyboard and mouse."""

    def __init__(self, bootimg, emudir, workdir, extra=()):
        emu = os.path.join(R.VMAC_HOME, emudir, "minivmac")
        rom = os.path.join(R.VMAC_HOME, "vMac.ROM")
        if not os.path.exists(emu):
            raise SystemExit(f"interactive: no emulator at {emu} — run setup.sh")
        boot = os.path.join(workdir, "boot.hfv")
        shutil.copyfile(bootimg, boot)
        self.dpy = R.Display()
        self.proc = subprocess.Popen([emu, "-r", rom, boot, *extra],
                                     env=dict(os.environ, DISPLAY=self.dpy.name),
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     start_new_session=True)
        self.env = dict(os.environ, DISPLAY=self.dpy.name)
        self._origin = None

    def _xdo(self, *args):
        subprocess.run(["xdotool", *args], env=self.env, capture_output=True)

    def origin(self, cached=True):
        """Top-left of the Mac screen within the X root, so Mac coordinates can
        be clicked directly. With no window manager the emulator lands wherever
        it likes, and hard-coding an offset silently clicks the desktop.

        **Re-query it when a run depends on the answer.** The window is
        512x342 at (144, 129) once the emulator has placed it, and 0 before
        that; a cached (0, 0) puts every later Mac coordinate 144 px left
        and 129 px up, which lands on something plausible rather than on
        nothing. Measured 2026-08-25: a menu click asking for x=425 opened
        the menu whose icon is at x=283, and the run photographed the wrong
        menu while reporting a successful pick."""
        if self._origin is None or not cached:
            win = self.dpy.window()
            if not win:
                raise SystemExit("interactive: emulator window never appeared")
            out = subprocess.run(["xdotool", "getwindowgeometry", "--shell", win],
                                 env=self.env, capture_output=True,
                                 text=True).stdout
            g = dict(l.split("=", 1) for l in out.strip().splitlines())
            self._origin = (int(g["X"]), int(g["Y"]))
            # There is no window manager on this display, so nothing ever
            # assigns keyboard focus and key events go to the root window
            # instead of the emulator. Mouse events are delivered by position
            # and work regardless, which makes the failure look like "the Mac
            # ignores this particular key" rather than "it receives no keys".
            self._xdo("windowfocus", "--sync", win)
        return self._origin

    def click(self, x, y, double=False):
        """Click at Mac-screen coordinates."""
        ox, oy = self.origin()
        self._xdo("mousemove", str(ox + x), str(oy + y))
        time.sleep(0.4)
        self._xdo("click", "--repeat", "2" if double else "1",
                  "--delay", "80", "1")
        time.sleep(0.4)

    def drag(self, x0, y0, x1, y1, steps=12):
        """Drag from one Mac-screen point to another, with the button held.

        Stepped rather than one jump: the emulated Mac samples its mouse once
        a tick, so a press and a release at two different places with nothing
        in between is read as a click at the second one — which for a Finder
        icon is "selected", not "dragged", and the two are told apart only by
        a screenshot nobody would question. The same ±63 px ADB limit that
        bites the Mac OS 9 harness does not apply here (Mini vMac sets the
        position directly), but the tick sampling does."""
        ox, oy = self.origin()
        self._xdo("mousemove", str(ox + x0), str(oy + y0))
        time.sleep(0.5)
        self._xdo("mousedown", "1")
        time.sleep(0.5)
        for i in range(1, steps + 1):
            self._xdo("mousemove", str(ox + x0 + (x1 - x0) * i // steps),
                      str(oy + y0 + (y1 - y0) * i // steps))
            time.sleep(0.12)
        time.sleep(0.5)
        self._xdo("mouseup", "1")
        time.sleep(1.0)

    def key(self, keys):
        self._xdo("key", "--delay", "60", keys)
        time.sleep(0.4)

    def command_key(self, ch):
        """Hold the Mac's Command key and tap <ch>.

        Sent as explicit keydown/keyup with a hold in between rather than as
        an `xdotool key alt+x` chord: the chord form presses and releases
        inside a couple of milliseconds, and the emulated Mac — which only
        scans its keyboard once a tick — can sample the modifier and the key
        in different scans and see a bare keypress. A plain Return goes
        through the chord form fine, which is exactly why this was worth
        pinning down: the failure looked like "Cmd-. does not work" rather
        than "the chord was never delivered".

        Mini vMac maps host Alt to Mac Command (XK_Alt_L -> MKC_formac_Command
        in its X11 glue)."""
        self._xdo("keydown", "alt")
        time.sleep(0.3)
        self._xdo("key", ch)
        time.sleep(0.3)
        self._xdo("keyup", "alt")
        time.sleep(0.5)

    def park(self):
        """Move the pointer off the Mac screen entirely, so the arrow cursor
        does not sit on top of whatever is being photographed."""
        self._xdo("mousemove", "790", "590")
        time.sleep(0.3)

    def shot(self, path, scale=None):
        self.park()
        for _ in range(40):
            if self.dpy.screenshot(path):
                if scale:
                    subprocess.run(["convert", path, "-scale", scale, path],
                                   check=True, capture_output=True)
                return
            time.sleep(0.5)
        raise SystemExit("interactive: could not screenshot the emulator")

    def close(self):
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        self.dpy.close()

    def settle(self, path, interval=10.0, timeout=900.0, stable=2, quiet=None):
        """Screenshot until the screen stops changing; return seconds waited.

        Used instead of a fixed sleep both for "has it finished booting" and
        for "has the extraction finished". At 1x the answer is minutes and
        varies with the archive, so a fixed wait is either wrong or wasteful.
        While work is in progress the progress dialog repaints its percentage,
        so consecutive shots differ; when the alert goes up the screen is
        static. Returns the elapsed time, which is a real Mac Plus figure.

        **"Static" is only ever "unchanged since the last poll", and that is
        not the same question.** The progress dialog repaints when the engine
        calls back, which is every 8–16 KB of INPUT — so on a slow decode the
        gap between repaints is tens of seconds, two polls land inside one
        gap, and a running extraction reads as a finished one. Pass `quiet`
        (SECONDS the screen must be unchanged) for any settle that means "has
        the extraction finished": it must exceed the worst repaint gap, not
        the poll interval. `stable` alone is fine for "has it booted", where
        what precedes the static screen is continuous repainting.

        Found on 2026-08-09: --dest reported the output on the wrong volume
        because this returned at 33%, and the phase then read a half-written
        disk. Nothing about that failure named the harness.
        """
        need = stable - 1 if quiet is None else max(1, round(quiet / interval))
        started = time.time()
        prev, same = None, 0
        while time.time() - started < timeout:
            time.sleep(interval)
            self.shot(path)
            cur = open(path, "rb").read()
            same = same + 1 if cur == prev else 0
            prev = cur
            if same >= need:
                return time.time() - started
        return None


# Buttons are pressed with Return, not with the mouse.
#
# The first version of this clicked SFGetFile's Open button at a measured
# coordinate and hit *Drive* instead, one row up — which switched to an empty
# volume and made every screenshot after the first meaningless while still
# "succeeding". Return activates the default button (Open in Standard File, OK
# in a note alert) and cannot be off by a row.
#
# The file list is a different matter: it has no keyboard default, so the row
# is clicked. Standard File pre-selects the first item and mkboot strips the
# volume to one archive, so the first row IS the archive.
SF_FIRST_ROW = (150, 137)
SF_ROW_HEIGHT = 16      # one Standard File row, at the system font size

# ...and the row is not in the same place on both systems. System 7 replaces
# the Standard File dialog with its own — a directory pop-up menu above the
# list, a Desktop button beside it — and its first row sits ten points higher.
# A System 6 coordinate lands on the SECOND item there, which is how a System 7
# run came to report UNC_ERR_FORMAT about a file that is not an archive
# (DECISIONS.md 2026-08-24, the low-memory message). Measured off this
# harness's own frames, one per system.
SF_ROWS = {"System6.hfv": (150, 137), "Sys7.img": (150, 127),
           # System 3.0 puts it where System 6 does: the application places
           # this dialog itself, at SFGetFile's `where`. What differs is the
           # LISTING — 3.0 shows the invisible `DeskTop` file, so the second
           # row is not what it is on 6. The first row is still the archive.
           "Sys30.img": (150, 137)}

# System 7's Desktop button, which System 6's dialog does not have. Measured
# off the same frame.
SF7_DESKTOP = (374, 160)


def calibrate(system):
    """Point the Standard File coordinates at the system about to be booted.

    Rebinds rather than threading `system` through twenty call sites: one run
    boots one system, and a phase that silently used the other system's
    geometry is exactly the failure this exists to stop.
    """
    global SF_FIRST_ROW, SF_SUBFOLDER_ROW, SF_SECOND_ROW
    global FINDER_VOLUME_ICON, FINDER_APP_ICON, FINDER_EXTRACTED_APPL
    row = SF_ROWS.get(system)
    if row is None:
        raise SystemExit(f"interactive: no Standard File geometry for {system} "
                         f"— boot it once, look at the first frame, and add "
                         f"its first row to SF_ROWS")
    SF_FIRST_ROW = SF_SUBFOLDER_ROW = row
    SF_SECOND_ROW = (row[0], row[1] + SF_ROW_HEIGHT)
    # The Finder coordinates only matter to --e2e, which is the only phase
    # that keeps the Finder; leave them alone rather than failing a phase
    # that never clicks one. phase_e2e refuses on its own if they are absent.
    icons = FINDER_ICONS.get(system)
    if icons:
        FINDER_VOLUME_ICON = icons["volume"]
        FINDER_APP_ICON = icons["app"]
        # `extracted` is --e2e's alone; --drop never clicks it, and a system
        # whose geometry was measured for one phase should not fail the other.
        FINDER_EXTRACTED_APPL = icons.get("extracted", FINDER_EXTRACTED_APPL)


def sf_to_volume_root(mac, system):
    """Bring Standard File to the BOOT VOLUME's root, wherever it opened.

    System 6 opens there already. System 7's Process Manager gives every
    application a default directory — its own — so under the boot-shell
    arrangement the dialog opens inside the System Folder, listing `Finder`,
    `System` and the application. Desktop, then the volume, is a two-click
    route to the root that needs no menu tracking.

    The volume is taken to be the first row of the desktop listing, which
    holds only mounted volumes: true with one volume mounted, and the phases
    that mount a second one navigate with Drive instead.
    """
    if system == "System6.hfv":
        return
    mac.click(*SF7_DESKTOP)
    time.sleep(2.0)
    mac.click(*SF_FIRST_ROW, double=True)
    time.sleep(3.0)

# How long the screen must hold still before an extraction is called
# finished, in seconds. Not a poll interval: see Mac.settle, where the
# reason it has to be this long is that the progress dialog repaints once
# per engine callback and those are 8–16 KB of input apart. Every settle
# that waits for an extraction passes this; the ones that wait for a boot
# do not need it.
EXTRACT_QUIET = 120.0

# The same question after a Cancel, where the wait is shorter because
# something is expected to happen rather than to stop happening.
CANCEL_QUIET = 15.0


def wait_for_alert(mac, scratch, timeout=240.0):
    """Wait for the screen to stop moving after a Cancel or a Cmd-period.

    Not a fixed sleep. The cancel is noticed in the engine's progress
    callback, which fires every 8–16 KB of INPUT, so how long the alert
    takes to come up is a property of the archive and the machine. Three
    seconds was enough until 2026-08-09 and then was not — and nothing
    failed when it stopped being enough: the phase photographed the
    progress dialog as "3-cancelled", the alert as "4-back", and every
    frame after that was one step behind the name it was saved under.
    """
    return mac.settle(scratch, interval=2.0, quiet=CANCEL_QUIET,
                      timeout=timeout)

# The progress dialog's Cancel button, measured off 2-extracting.png. Cancel
# by button and Cancel by Cmd-. are separate checklist items reaching the same
# code by different routes (Dialog Manager hit-testing vs. the keyDown check
# in ProgressPump), so both are exercised.
#
# THIS MOVES WHENEVER THE DIALOG DOES, and nothing here will say so: a click on
# the wrong spot lands on inert dialog background, the extraction runs happily
# to completion, and the run still produces a 3-cancelled.png — of the progress
# dialog, not the alert. It was (342, 138) until 2026-08-07, when the DLOG grew
# from 80 to 110 points tall to make room for the progress bar and the button
# moved down with it. Derive it from the resources rather than guessing:
# DLOG 128 is at (top 80, left 80) and the Cancel item's DITL rect is
# {78, 220, 98, 300}, so the centre is (80+260, 80+88).
PROGRESS_CANCEL = (340, 168)

# Standard File's Drive button, one row above Open — the row that a mis-aimed
# click once landed on by accident (see above). With two volumes mounted it
# cycles between them, which is the volume-navigation checklist item.
# Measured off e2e-3-sfgetfile.png; the dialog is placed by the application at
# SFGetFile's `where` (82, 90), so this moves if that does.
SF_DRIVE = (377, 192)

# The Finder, in --e2e mode. Coordinates measured off the numbered screenshots
# that mode writes; they are stable because the boot image is rebuilt
# identically each run, and re-measuring them from the shots is the fix if the
# volume's contents ever change.
# One row per system, for the same reason WD_ICONS is a table: each system
# remembers its own window placement and each leaves a different number of
# items in the volume, so a constant is silently wrong on the other one.
# `volume` is the boot disk on the desktop, `app` is MacExtract in the open
# volume window, `extracted` is the application the run itself extracts.
#
# System 6 opens a window of FOUR items — System Folder, archive.sit, an empty
# folder mkboot.py cannot delete, the application — and `extracted` is the
# sixth and last once the two entries of derived-ScrollbarPattern.sit are
# there. System 3.0 has no leftover folder, so the same window holds THREE and
# every icon after the first sits one place to the left. Measured off each
# system's own e2e-2-volume.png and e2e-7-back-in-finder.png; a different
# fixture moves `extracted`.
FINDER_ICONS = {
    "System6.hfv": {"volume": (480, 40), "app": (240, 110),
                    "archive": (111, 103), "extracted": (367, 104)},
    "Sys30.img":   {"volume": (472, 45), "app": (237, 97),
                    "archive": (175, 92), "extracted": (170, 168)},
    # System 7.0.1 opens its volume window near the BOTTOM of the screen,
    # so these are nothing like the other two and the control drag has to
    # move up rather than down (see phase_drop).
    "Sys7.img":    {"volume": (480, 40), "app": (221, 310),
                    "archive": (157, 310)},
}

FINDER_VOLUME_ICON = FINDER_ICONS["System6.hfv"]["volume"]
FINDER_APP_ICON = FINDER_ICONS["System6.hfv"]["app"]
FINDER_EXTRACTED_APPL = FINDER_ICONS["System6.hfv"]["extracted"]


# The working-directory phase's own coordinates. SF_SUBFOLDER_ROW is the row
# the folder occupies in SFGetFile's list; FINDER_FOLDER_ICON is that folder on
# the Finder desktop afterwards. Both measured off this phase's screenshots.
# calibrate() re-points this at the booted system's own first row.
SF_SUBFOLDER_ROW = (150, 137)

# Finder icon positions differ between the two system images, because each
# remembers its own window placement: System 6.0.8 opens the volume window at
# the top left, System 7.0.1 near the bottom of the screen. Measured off
# wd-2-volume.png for each. They are a table rather than constants because
# this is a look-and-adjust loop by nature — the first System 7 attempt
# clicked bare desktop with System 6 coordinates and launched nothing.
#
# `folder` was 66 until 2026-08-09 and opened the SYSTEM FOLDER: four icons at
# the Finder's default spacing overlap their neighbours' labels on a 512-point
# screen, so being one icon out looks like a normal window. wd-7 is only
# illustration now — the phase decides on the volume's own directory — but
# re-measure it off wd-2-volume.png whenever the volume's contents change.
WD_ICONS = {
    "System6.hfv": {"app": (240, 110), "folder": (106, 106)},
    "Sys7.img":    {"app": (222, 313), "folder": (157, 313)},
}

# The folder --wd puts the archive in, so that the archive's folder and the
# volume root are different directories. Named once: the harness builds the
# volume with it and then looks for the output inside it.
ARCHIVE_FOLDER = "Archives"


def accept_destination(mac, pause=3.0):
    """Press Return on the destination dialog.

    Since 2026-08-09 the application asks where the files should go, with
    SFPutFile. Standard File keeps ONE current folder across SFGetFile and
    SFPutFile, so the dialog opens in the folder the archive was chosen
    from and Return means "beside the archive" — the behaviour every phase
    here was written against. A phase that needs output SOMEWHERE ELSE
    navigates before calling this.
    """
    time.sleep(pause)
    mac.key("Return")
    time.sleep(1.5)


# SFPutFile's Drive button. Two things move it away from SF_DRIVE: its
# layout is NOT SFGetFile's (there is a name field along the bottom and
# the buttons sit lower), and since 2026-08-09 the application opens it 30
# points down and right of the open dialog, ON PURPOSE, so that the second
# dialog visibly moves rather than looking like the first one redrawn.
# Measured off 1b-destination.png; if that offset changes in
# `mac/macextract_mac.c`, this moves with it.
SFPUT_DRIVE = (337 + 30, 181 + 30)


def volume_names(img, dirs=False):
    """Every file on an HFS image, as checkdisk.py's component tuples.

    With `dirs`, the folders as well — see `checkdisk.walk`.

    Not `hls -1` split on whitespace: a Mac filename contains spaces
    ("Demo Manual V1.6" is three fields, one name), may begin with a dot,
    and may sit in a folder. checkdisk.walk already handles all three,
    including the '/'-in-a-name case, so it is used rather than restated.
    """
    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    try:
        if CD.hfs(env, "hmount", img).returncode != 0:
            raise SystemExit(f"interactive: {img} will not mount")
        names = set(CD.walk(env, dirs=dirs))
        CD.hfs(env, "humount")
        return names
    finally:
        shutil.rmtree(home, ignore_errors=True)


def expected_names(fixture, workdir):
    """The names the Mac should have written, as component tuples.

    The same mapping checkdisk.py makes, less one difference that matters:
    extract with the CLI, drop the "._" sidecars (a resource fork is part
    of the file on a Mac), map the CLI's `<archive>.comment.txt` to the
    `Comments` document the Mac shell writes instead, undo the engine's
    reversible '/'->':' swap and cap each component at 31 characters as
    ComponentToStr63 does. The fixture is copied to `archive.sit` first
    because that is the name the Mac saw, and gzip/.Z derive an output
    name from the archive's.

    **The difference: no `-nr` here.** checkdisk.py grades the AUTOTEST
    build, which calls RunExtract once; these phases drive the shipped
    application, which has unwrapped envelope chains since 2026-08-14. A
    single-level reference says a chained fixture should leave
    `boogers152.sit` on the volume, where the application leaves the two
    files inside it — so every phase using this would have failed on any
    chained fixture, in the direction that looks like an application bug
    (DECISIONS.md 2026-08-27).

    What this CANNOT see: it compares NAMES only. A file of the right name
    and the wrong bytes passes here — run.py and checkdisk.py are what
    compare forks. This phase asks one question, "which volume did the
    output land on", and a name is enough to answer it.
    """
    if not os.path.exists(CD.CLI):
        print(f"interactive: no CLI at {CD.CLI} — run `make BUILD=build/rel`")
        return set()
    asmac = os.path.join(workdir, "as-the-mac-saw-it", "archive.sit")
    os.makedirs(os.path.dirname(asmac), exist_ok=True)
    shutil.copyfile(fixture, asmac)
    ref = os.path.join(workdir, "linux-out")
    subprocess.run([CD.CLI, "x", "--forks", "hidden", asmac, "-o", ref],
                   capture_output=True)
    comment_file = os.path.basename(asmac) + ".comment.txt"
    utf8 = CD.names_are_utf8(fixture, CD.CLI)
    want = set()
    for root, _dirs, files in os.walk(ref):
        for f in files:
            if f.startswith("._"):
                continue
            rel = os.path.relpath(os.path.join(root, f), ref)
            raw = rel.split(os.sep)
            if [unicodedata.normalize("NFC", c) for c in raw] == [comment_file]:
                want.add(("Comments",))
                continue
            want.add(tuple(unicodedata.normalize("NFC", CD.mac_component(c, utf8))
                           for c in raw))
    if not want:
        print(f"interactive: the CLI extracted nothing from {fixture} — "
              f"there is no output to look for")
    return want


# The end-of-run report box, measured off its own resource
# (mac/macextract.r, DLOG 133 at {30,26,330,486} with the items inside it).
# Re-measure all three if that resource moves.
REPORT_OK   = (437, 304)     # the OK button
REPORT_SAVE = (322, 304)     # "Save as Text..."
REPORT_DOWN = (462, 268)     # the scroll bar's down arrow


def report_archive(path):
    """A DiskDoubler archive built to make the report say everything it
    can say, and nothing that needs a big file: names too long for HFS,
    one that fits only once its extension goes, a duplicate that has to
    be numbered, two folders that shorten to the same name, and one
    entry whose checksum is broken so a per-entry FAILURE is listed
    beside the renames. Enough entries to overflow the box, so the
    scroll bar is live and can be photographed doing something.

    Generated rather than taken from the corpus: the longest name in 932
    fixtures is 120 bytes but none of them collides, and nothing in the
    corpus is damaged (TESTING.md).
    """
    sys.path.insert(0, os.path.join(R.REPO, "tools"))
    import synth_dd                                          # noqa: E402
    tree = [synth_dd.file("MyQuarterlyReportForTheBoard.rtf", data=b"rtf\n"),
            synth_dd.file("Chapter One Draft Revised Final Version.txt",
                          data=b"draft\n"),
            synth_dd.file("Notes.txt", data=b"first\n"),
            synth_dd.file("Notes.txt", data=b"second\n"),
            synth_dd.folder("Correspondence With The Publisher A",
                            [synth_dd.file("letter.txt", data=b"A\n")]),
            synth_dd.folder("Correspondence With The Publisher B",
                            [synth_dd.file("letter.txt", data=b"B\n")]),
            synth_dd.file("BrokenBecauseItsChecksumIsWrong.txt",
                          data=b"DAMAGEDDAMAGED\n", stored=True)]
    for i in range(18):
        tree.append(synth_dd.file("Photograph Of The Summer Of 1994 no%d.pict"
                                  % i, data=b"pict\n"))
    tmp = tempfile.mkdtemp(prefix="report-")
    built, _ = synth_dd.write_one(tmp, "report", tree)
    raw = bytearray(open(built, "rb").read())
    at = raw.find(b"DAMAGEDDAMAGED")
    assert at > 0, "the payload to damage is not in the archive"
    raw[at] ^= 0x01                    # one bit: its checksum, nothing else
    open(path, "wb").write(bytes(raw))
    shutil.rmtree(tmp, ignore_errors=True)


def deep_archive(path):
    """An archive nested past `UNC_PATH_MAXDEPTH`, for the one report line
    nothing in the corpus can reach.

    The engine carries 24 levels of folder and nothing on this disk nests
    past 4 (FORMATS.md, *How deep anything actually nests*), so an entry
    below the limit — whose path the engine cannot represent and therefore
    refuses to place — can only be generated. `tools/synth_deep.py` writes
    the tree and says what each part of it is for; this takes the
    DiskDoubler one because the report is the same whatever walk found the
    entry, and `DDAR` is the cheapest of the five to build.
    """
    sys.path.insert(0, os.path.join(R.REPO, "tools"))
    import synth_dd                                          # noqa: E402
    import synth_deep                                        # noqa: E402
    open(path, "wb").write(
        synth_dd.build_ddar(synth_deep.dd_tree(DEEP_DEPTH, synth_dd)))


def volume_text(img, name):
    """One TEXT file's contents, read off an HFS image as lines."""
    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    dst = os.path.join(home, "out.txt")
    try:
        if CD.hfs(env, "hmount", img).returncode != 0:
            return None
        got = CD.hfs(env, "hcopy", "-t", name, dst)
        CD.hfs(env, "humount")
        if got.returncode != 0 or not os.path.exists(dst):
            return None
        with open(dst, "rb") as f:
            return f.read().decode("mac_roman").splitlines()
    finally:
        shutil.rmtree(home, ignore_errors=True)


def report_reached_image(img, second=False):
    """Where the report actually is, when the host cannot read it.

    The control for the floppy workaround `phase_report_utf8` carries.
    That workaround rested on a HYPOTHESIS — that 300 KB across a
    seven-deep tree grows the catalog and what is written after that
    does not reach the image — and a hypothesis nothing can read is not
    one this repository keeps (CLAUDE.md, the reproduction rule).

    **Measured 2026-09-22, and it replaces the hypothesis.** Run with
    `--utf8-to-boot`, the report is unreadable off the boot volume by
    any HFS tool, and its bytes are in the image all the same: the three
    `_` lines and `Extraction complete.` are there, in order, complete.
    The extraction's own output — 300 KB written to the same volume
    minutes earlier — is both in the image AND in the catalog, five
    entries deep, `Icon\r` included. So what is lost is **the catalog
    update for the last file written**, not the file, and not "what the
    guest wrote after a point": the File Manager lays a data fork's
    blocks down before it records the entry, and the run ends between
    the two.

    That is why no flush helped: four remedies were tried against a
    write that had already happened. It also says what the workaround
    is worth — sending the report to another volume gets a catalog
    entry written on a volume whose catalog is not in that state, which
    is a sidestep and is still the right one.

    Two readings, printed whatever they say:

      - the CATALOG, which is what every harness here reads — `hls -a`
        at the volume root, so an invisible file counts as present;
      - the BLOCKS, a raw search for a string only the saved document
        can contain. Not its NAME: `Extraction Report` is the default
        `SFPutFile` offers, so it is in the application's own resources
        on the same volume, and searching for it answers YES either way.
        That is the shape of the error this reading is built to avoid.

    **`second=True` is the discriminator**, and it is the one level below
    this that was left open: whether the lost catalog update is sitting in
    Mini vMac's buffered stdio or in the guest's own volume cache. With
    `--utf8-second` the report is saved TWICE, the second time under
    `Second`, so one more file and one more catalog update follow the
    first. The three outcomes read differently:

      - `Second` in the catalog and the report NOT: the first entry was
        overwritten or reordered, not merely unflushed — a property of
        the ORDER the File Manager records in;
      - NEITHER in it: whatever holds the tail holds both, which is a
        buffer with more than one update in it;
      - the report in it and `Second` NOT: the tail simply MOVED, which
        is the buffer reading with the blame on whichever write is last.
    """
    # The three-`_` line as the DOCUMENT spells it. The application's
    # resources hold the template without the name, so this matches the
    # saved file and nothing else — verified at one hit.
    SAVED = "_______ was named in characters".encode("mac_roman")
    raw = open(img, "rb").read()
    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    try:
        listed = []
        if CD.hfs(env, "hmount", img).returncode == 0:
            out = CD.hfs(env, "hls", "-a", "-1").stdout
            listed = [x.decode("mac_roman") for x in out.split(b"\n") if x]
            CD.hfs(env, "humount")
    finally:
        shutil.rmtree(home, ignore_errors=True)
    print("interactive: the volume's CATALOG holds: "
          + (", ".join(repr(x) for x in listed) or "<nothing; it did not mount>"))
    print("interactive: the report is in the catalog       : %s"
          % ("YES" if REPORT_FILE in listed else "NO"))
    print("interactive: the extraction's output is in it   : %s"
          % ("YES" if any(x.startswith("800-SAY-WHAT") for x in listed) else "NO"))
    print("interactive: the report's TEXT is in the image  : %s"
          % ("YES" if SAVED in raw else "NO"))
    if SAVED in raw and REPORT_FILE not in listed:
        print("interactive: so the bytes landed and the catalog entry did "
              "not — the reproduction, not the hypothesis")
    if second:
        got1 = REPORT_FILE in listed
        got2 = UTF8_SECOND_FILE in listed
        print("interactive: the SECOND report is in the catalog: %s"
              % ("YES" if got2 else "NO"))
        if got2 and not got1:
            verdict = ("the later entry landed and the earlier did not — "
                       "ORDERING, not an unflushed tail")
        elif not got2 and not got1:
            verdict = ("neither entry landed — whatever holds the tail "
                       "holds more than one update")
        elif got1 and not got2:
            verdict = ("the tail simply MOVED to the last write — the "
                       "buffer reading")
        else:
            verdict = ("both landed, so a second write is enough to place "
                       "the first — the first was unflushed, not lost")
        print("interactive: discriminator says: " + verdict)


def phase_report(args, appbin, workdir, shot):
    """The end-of-run report: what was renamed, what failed, and the
    outcome last. It replaces the "Extraction complete." alert on any
    run that has something per-entry to say.

    Five things are photographed and one is asserted. The photographs
    are the box, the box scrolled six lines, Standard File over it after
    "Save as Text", the box redrawn once that is dismissed — which is
    what proves the list and the default ring come back — and SFGetFile
    afterwards. A screen with no scrollback is the whole reason that
    button exists. The assertion
    is the SAVED DOCUMENT, read back off the volume the Mac wrote it to:
    it must hold the rename lines for the names this archive was built
    to bend, and the line for the entry that failed. A photograph of a
    box full of text cannot fail; a missing line in that file can.

    Ignores the fixture argument — the archive is generated.
    """
    stock = os.path.join(R.VMAC_HOME, args.system)
    bootimg = os.path.join(workdir, "boot-report.hfv")
    arch = os.path.join(workdir, "report.dd")
    report_archive(arch)
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin, bootimg,
         "--data", f"{arch}:archive.sit")

    scratch = os.path.join(args.outdir, ".settle.png")
    mac = Mac(bootimg, args.emu, workdir)
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never settled")
        sf_to_volume_root(mac, args.system)
        mac.click(*SF_FIRST_ROW)
        mac.key("Return")
        accept_destination(mac)
        mac.settle(scratch, interval=5.0, quiet=EXTRACT_QUIET,
                   timeout=args.complete_timeout)
        shot(mac, "report-1-box.png")          # the list, the outcome last

        for _ in range(6):                     # the scroll bar's down arrow
            mac.click(*REPORT_DOWN)
            time.sleep(0.4)
        time.sleep(1.5)
        shot(mac, "report-2-scrolled.png")

        mac.click(*REPORT_SAVE)                # "Save as Text..."
        time.sleep(4.0)
        shot(mac, "report-3-save.png")         # Standard File, over the box
        mac.key("Return")                      # Save, under the offered name
        time.sleep(5.0)
        shot(mac, "report-4-saved.png")        # the box again, ring and all

        mac.click(*REPORT_OK)
        time.sleep(3.0)
        shot(mac, "report-5-back.png")         # back at SFGetFile
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    written = os.path.join(workdir, "boot.hfv")     # Mac()'s private copy
    names = {CD.mac_path(n) for n in volume_names(written)}
    lines = volume_text(written, "Extraction Report")
    print("interactive: the volume holds " + ", ".join(sorted(names)))
    if lines is None:
        print("interactive: NO saved report on the volume")
        return False
    for l in lines:
        print("interactive: report | " + l)

    want_lines = [
        # the stem is cut and the extension kept
        "MyQuarterlyReportForTheBoard.rtf renamed to "
        "MyQuarterlyReportForTheBoar.rtf",
        # a duplicate is numbered BEFORE the extension
        "Notes.txt renamed to Notes~1.txt",
        # the damaged entry, named as the ARCHIVE names it — the file
        # this shell would have written was deleted when it failed
        "BrokenBecauseItsChecksumIsWrong.txt is damaged: "
        "its checksum does not match",
        # and the line only a WHOLE name can carry: eighteen photographs
        # whose names differ at character 34, each said in full, so which
        # one became ~11 is answerable
        "Photograph Of The Summer Of 1994 no11.pict renamed to "
        "Photograph Of The Summe~11.pict",
        # two folders that shorten alike are TWO folders, the second
        # numbered the way a file is (2026-09-03) — and both are named
        "Folder Correspondence With The Publisher A renamed to "
        "Correspondence With The Publish",
        "Folder Correspondence With The Publisher B renamed to "
        "Correspondence With The Publi~1",
    ]
    missing = [w for w in want_lines if w not in lines]
    # "finished", not "complete": entries failed, and not "some entries
    # could not be extracted" either — they are named above, one line each.
    if not lines or "Extraction finished." not in lines[-1]:
        missing.append("<the outcome, on the last line of the document>")
    for m in missing:
        print("interactive: NOT in the saved report: " + m)
    # And the names the report claims: they have to be what is on disk.
    # `names` are checkdisk paths (":Name" at the volume root).
    for n in ("MyQuarterlyReportForTheBoar.rtf", "Notes~1.txt",
              # the eighteenth photograph proves the numbering goes past ~9,
              # and keeps its suffix while doing it
              "Photograph Of The Summe~17.pict",
              # and the two folders are TWO folders, each holding its own
              # letter.txt — a merge would have put one letter~1.txt in
              # the first of them (2026-09-03)
              "Correspondence With The Publish:letter.txt",
              "Correspondence With The Publi~1:letter.txt"):
        if ":" + n not in names:
            missing.append(n)
            print(f"interactive: the report names {n}, the volume does not")
    ok = not missing
    print("interactive: report " + ("COMPLETE" if ok else "WRONG"))
    return ok


# How deep `--report-deep` nests, and the path the report must name. The
# engine stops descending at UNC_PATH_MAXDEPTH (24), so `D25` is the last
# folder it can name and `f25.txt` — inside `D25`, which it could not
# descend into — is the first entry whose path it cannot represent.
DEEP_DEPTH = 30
DEEP_FLAT = "/".join("D%02d" % i for i in range(1, 25))


def phase_report_deep(args, appbin, workdir, shot):
    """The report line for an entry nested deeper than the engine can place.

    The other half of the folder-depth rule, and the half no automated
    suite on Linux can reach: `tools/run_depth.py` grades the ENGINE and
    the CLI, and the Macintosh shell has its own refusal — it declines the
    entry at begin_entry rather than walking a path whose deepest folders
    are missing from the middle of it (macextract.h, `path_too_deep`).

    Three frames and one assertion. The frames are the box, the box
    scrolled, and the box after Save as Text. The assertion is the SAVED
    DOCUMENT, read back off the volume the Mac wrote it to: it must name
    the entries the engine could not place, in the engine's own words, and
    end on the outcome. A photograph of a box full of text cannot fail; a
    missing line in that file can.

    **The other half of the rule — that the flattened folder is NOT
    created — is not asserted here, and cannot be.** `hls` will not list
    the root of a volume this build leaves behind, the same hfsutils
    limitation `phase_report_utf8` records for the same reason: `hcopy`
    fetches the document by name and a listing comes back EMPTY (measured
    again 2026-10-07, on this phase, against a volume that held the tree
    correctly — an assertion written here on folders found nothing and
    read as the application's fault). That half is `run.py --keep-disks`
    then `checkdisk.py --fixture`, which compares the whole Out volume
    against the Linux extraction: 49 files and 25 folders, where the
    application of 2026-10-06 wrote 61 and 30 (TESTING.md, *The
    folder-depth limit*).

    Ignores the fixture argument — the archive is generated.
    """
    stock = os.path.join(R.VMAC_HOME, args.system)
    bootimg = os.path.join(workdir, "boot-deep.hfv")
    arch = os.path.join(workdir, "deep.dd")
    deep_archive(arch)
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin, bootimg,
         "--data", f"{arch}:archive.sit")
    # Extract to a FLOPPY and not beside the archive, for the reason
    # `phase_report_utf8` does: a report saved onto a boot volume this
    # application has just written a deep tree to is on the image and not
    # in its catalog, so the host cannot read it (DECISIONS.md 2026-09-22,
    # *the file that was on the disk and not in the catalog*). Measured
    # again here on 2026-10-07 — 49 files across 25 levels put that volume
    # in the same state, and the first run of this phase read NO saved
    # report off it while photographing a correct box.
    destdsk = os.path.join(workdir, "dest.dsk")
    R.make_floppy(destdsk, "Dest", size_kb=1440)

    scratch = os.path.join(args.outdir, ".settle.png")
    mac = Mac(bootimg, args.emu, workdir, extra=(destdsk,))
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never settled")
        # Standard File opens on the last-inserted volume, the empty
        # floppy; drive back to the boot volume for the archive.
        mac.click(*SF_DRIVE)
        time.sleep(2.0)
        mac.click(*SF_FIRST_ROW)
        mac.key("Return")
        time.sleep(3.0)
        mac.click(*SFPUT_DRIVE)                # ...and away to the floppy
        time.sleep(1.5)
        accept_destination(mac, pause=1.0)
        mac.settle(scratch, interval=5.0, quiet=EXTRACT_QUIET,
                   timeout=args.complete_timeout)
        shot(mac, "deep-1-box.png")

        for _ in range(6):
            mac.click(*REPORT_DOWN)
            time.sleep(0.4)
        time.sleep(1.5)
        shot(mac, "deep-2-scrolled.png")

        mac.click(*REPORT_SAVE)
        time.sleep(4.0)
        mac.key("Return")
        time.sleep(5.0)
        shot(mac, "deep-3-saved.png")

        mac.click(*REPORT_OK)
        time.sleep(3.0)
        time.sleep(FLUSH_WAIT)
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    lines = volume_text(destdsk, "Extraction Report")
    missing = []
    if lines is None:
        print("interactive: NO saved report on the volume")
        return False
    for l in lines:
        print("interactive: report | " + l)

    # The engine's own sentence, which this shell borrows rather than
    # keeping a literal of its own (macextract_mac.c says why).
    want = DEEP_FLAT + "/f25.txt nested too deep to place"
    if not any(want in l for l in lines):
        missing.append(want)
    if "Extraction finished." not in lines[-1]:
        missing.append("<the outcome, on the last line of the document>")
    for m in missing:
        print("interactive: NOT in the saved report: " + m)

    ok = not missing
    print("interactive: report-deep " + ("COMPLETE" if ok else "WRONG"))
    return ok


# The one archive in the corpus whose names a Macintosh cannot write, and
# the lines it must put in the report. `derived-800saywhat301j.sit` is a
# StuffIt 5 archive from a Japanese publisher: three of its entries are
# named in kana and kanji, MacRoman has a byte for none of those, and the
# shell writes one '_' per code point (FORMATS.md, *A name in the wrong
# encoding is not a name*).
#
# The counts are the whole point of the assertion and they are NOT the
# character counts a reader would guess: `ユーザーライセンスの購入` is
# thirteen code points and not twelve, because the archive stores `ザ`
# DECOMPOSED — `サ` plus U+3099 — and the fold replaces each of them.
# The oracle manifests hold the composed spelling, which is why nothing
# noticed until this ran on a Macintosh.
# How long to let Mini vMac flush before Mac.close() SIGKILLs it. See
# phase_report_utf8 for what it is for and what it cost to find.
FLUSH_WAIT = 30.0

# What Save as Text offers as the document's name, and what the volume is
# therefore searched for. It is ALSO in the application's own resources,
# which is why report_reached_image() searches the blocks for the
# document's CONTENT and the catalog for this.
REPORT_FILE = "Extraction Report"
# The second report, saved under a name of its own by `--utf8-second`.
# Its only job is to be the NEXT catalog update after the first one's.
UTF8_SECOND_FILE = "Second"

UTF8_REPORT_FIXTURE = "derived-800saywhat301j.sit"
UTF8_REPORT_LINES = [
    "_______ was named in characters this Macintosh cannot write",
    "_______.rtf was named in characters this Macintosh cannot write",
    "_____________.rtf was named in characters this Macintosh cannot write",
]
# The names those lines are ABOUT — `800-SAY-WHAT 3.0.1J:_______` and the
# two `.rtf`s — are not checked here, and deliberately: `run.py
# --keep-disks` then `checkdisk.py` already compares them off the Out
# volume for this very fixture, with both forks, as part of a 71-fixture
# sweep. This phase would be a second, weaker copy of that check, and it
# cannot even make it — hfsutils will not list the ROOT of a volume the
# interactive build leaves behind ("Current HFS directory 'Dest::' no
# longer exists"), though `hcopy` still fetches a file from it by name,
# which is why the document below can be read and a listing cannot.


def phase_report_utf8(args, appbin, workdir, shot):
    """The report line no generated archive can make it say.

    `--report` builds its own DiskDoubler archive, and no DiskDoubler
    archive can reach this line: the fold runs only where the ENGINE says
    the names are UTF-8, which `fmt_sit5.c` alone does. So this phase
    ignores the fixture argument the other way round — it uses one real
    corpus archive, named above.

    Four frames and one assertion. The frames are the box, Standard File
    over it after **Save as Text**, the box redrawn once that is
    dismissed, and SFGetFile afterwards; there is no scrolled frame
    because four lines do not fill the box, and `--report` is where the
    live scroll bar is photographed. The assertion is the saved DOCUMENT,
    for the reason `--report` asserts one: a photograph of a box full of
    '_' cannot fail, and a missing line in that file can.

    **The output goes to a floppy and not beside the archive**, which is
    the one way this phase differs from `--report` and it is not
    cosmetic. Extracting this archive onto the BOOT volume leaves the
    saved report unreadable on the host: the Macintosh has the file —
    frame 4 photographs it in Standard File's own listing — and `hcopy`
    off the image cannot find it. Four things did not help: a 30 s flush
    wait, Mini vMac's Control-Q, SIGTERM instead of SIGKILL, and the
    shell's own `FlushVol`, already called at `macextract_mac.c`'s
    Save-as-Text.

    **What it is, measured rather than guessed, is `--utf8-to-boot`'s
    doing**: the report's BYTES are on the image — the three `_` lines
    and `Extraction complete.`, in order, complete — and its **catalog
    entry is not**, while the 300 KB the extraction wrote to the same
    volume minutes earlier is in both. So nothing is lost after a point;
    what is lost is the directory record for the last file written, and
    no flush could have helped because the write had already happened.
    `report_reached_image` reads both, and DECISIONS.md 2026-09-22, *the
    file that was on the disk and not in the catalog*, has the rest.
    Sending the report to another volume gets its entry written on a
    volume whose catalog is not in that state: a sidestep, and the right
    one.

    **`--utf8-second` is the level below that, and it is settled too.**
    Saving the report a second time under its own name puts one more
    catalog update after the lost one, and BOTH entries then land — so
    the first was unflushed rather than lost, and a fixed tail of Mini
    vMac's buffered stdio is ruled out, since both entries live in the
    same catalog leaf (DECISIONS.md 2026-09-22, *the entry a second
    write placed*).
    """
    fixture = os.path.join(R.REPO, "fixtures", UTF8_REPORT_FIXTURE)
    if not os.path.exists(fixture):
        print(f"interactive: no {UTF8_REPORT_FIXTURE} in fixtures/ — this "
              f"phase has no subject (fixtures/SOURCES.md)")
        return False
    stock = os.path.join(R.VMAC_HOME, args.system)
    bootimg = os.path.join(workdir, "boot-utf8.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin,
         bootimg, "--data", f"{fixture}:archive.sit")
    destdsk = os.path.join(workdir, "dest.dsk")
    R.make_floppy(destdsk, "Dest", size_kb=1440)

    scratch = os.path.join(args.outdir, ".settle.png")
    mac = Mac(bootimg, args.emu, workdir, extra=(destdsk,))
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never settled")
        # Standard File opens on the last-inserted volume, the empty
        # floppy; drive back to the boot volume for the archive.
        mac.click(*SF_DRIVE)
        time.sleep(2.0)
        mac.click(*SF_FIRST_ROW)
        mac.key("Return")
        time.sleep(3.0)
        if not getattr(args, "utf8_to_boot", False):
            mac.click(*SFPUT_DRIVE)            # ...and away to the floppy
            time.sleep(1.5)
        accept_destination(mac, pause=1.0)
        mac.settle(scratch, interval=5.0, quiet=EXTRACT_QUIET,
                   timeout=args.complete_timeout)
        shot(mac, "utf8-1-box.png")            # the three lines, outcome last
        mac.click(*REPORT_SAVE)
        time.sleep(4.0)
        shot(mac, "utf8-2-save.png")
        mac.key("Return")
        time.sleep(5.0)
        shot(mac, "utf8-3-saved.png")
        if getattr(args, "utf8_second", False):
            # The DISCRIMINATOR. Save the report a SECOND time, under a
            # name of its own, so one more small file and one more catalog
            # update land on this volume after the first report's. Which
            # of the two entries survives is the whole reading; see
            # `report_reached_image`.
            mac.click(*REPORT_SAVE)
            time.sleep(4.0)
            mac._xdo("type", "--delay", "120", UTF8_SECOND_FILE)
            time.sleep(1.0)
            shot(mac, "utf8-3b-second-named.png")
            mac.key("Return")
            time.sleep(5.0)
            shot(mac, "utf8-3c-second-saved.png")
        mac.click(*REPORT_OK)
        time.sleep(3.0)
        shot(mac, "utf8-4-back.png")
        time.sleep(FLUSH_WAIT)
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    written = os.path.join(workdir, "boot.hfv")     # Mac()'s private copy
    if getattr(args, "utf8_to_boot", False):
        keep = os.path.join(args.outdir, "utf8-boot.hfv")
        shutil.copyfile(written, keep)
        print("interactive: the boot volume this run wrote is kept at "
              + keep)
        report_reached_image(keep, second=getattr(args, "utf8_second", False))
    lines = (volume_text(destdsk, "Extraction Report")
             or volume_text(written, "Extraction Report"))
    if lines is None:
        print("interactive: NO saved report on either volume")
        return False
    for l in lines:
        print("interactive: report | " + l)
    missing = [w for w in UTF8_REPORT_LINES if w not in lines]
    # Nothing FAILED here — every entry came out, under a name the disk
    # can hold — so the outcome is the clean one even though the box is
    # up. That is the difference between this phase and --report.
    if not lines or "Extraction complete." not in lines[-1]:
        missing.append("<'Extraction complete.', on the last line>")
    for m in missing:
        print("interactive: NOT in the saved report: " + m)
    ok = not missing
    print("interactive: utf8 report " + ("COMPLETE" if ok else "WRONG"))
    return ok


def phase_dest(args, appbin, workdir, shot):
    """Does choosing a different folder actually send the files there?

    The destination dialog defaulting to the archive's folder is what
    --wd checks. This checks the other half, which is the whole reason
    the dialog exists: a set of floppies cannot write its output onto
    the disk it is about to ask you to eject.

    The archive is on the boot volume and an empty floppy is mounted
    beside it. The walk switches the DESTINATION dialog to that floppy
    and extracts. Afterwards the host reads both volumes: the files must
    be on the floppy and must NOT be on the boot volume. That is an
    assertion, not a screenshot — "Extraction complete." looks the same
    wherever the bytes went.

    Give it a SMALL fixture with a folder in it — `derived-Downer.sit` is
    what this was written against. Small because the phase waits out
    EXTRACT_QUIET after the last repaint and nothing here is measuring
    speed; with a folder because "which volume" and "did the folder come
    with it" are the same read of the same volume.
    """
    stock = os.path.join(R.VMAC_HOME, args.system)
    bootimg = os.path.join(workdir, "boot-dest.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin, bootimg,
         "--data", f"{args.fixture}:archive.sit")
    destdsk = os.path.join(workdir, "dest.dsk")
    R.make_floppy(destdsk, "Dest")

    scratch = os.path.join(args.outdir, ".settle.png")
    elapsed = None
    mac = Mac(bootimg, args.emu, workdir, extra=(destdsk,))
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never settled")
        # Standard File opens on the last-inserted volume, which is the
        # empty floppy. Drive over to the boot volume to find the archive.
        mac.click(*SF_DRIVE)
        time.sleep(2.0)
        shot(mac, "dest-1-sfgetfile.png")

        mac.click(*SF_FIRST_ROW)
        mac.key("Return")                    # Open -> destination dialog
        time.sleep(3.0)
        shot(mac, "dest-2-destination.png")  # opens on the archive's volume

        mac.click(*SFPUT_DRIVE)              # ...and away to the floppy
        time.sleep(2.0)
        shot(mac, "dest-3-other-volume.png")

        mac.key("Return")                    # Save -> extraction
        elapsed = mac.settle(scratch, interval=5.0, quiet=EXTRACT_QUIET,
                             timeout=args.complete_timeout)
        shot(mac, "dest-4-complete.png")
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    written = os.path.join(workdir, "boot.hfv")     # Mac()'s private copy
    want = expected_names(args.fixture, workdir)
    if not want:
        return False
    on_dest = volume_names(destdsk)
    on_boot = volume_names(written)

    missing = sorted(n for n in want if n not in on_dest)
    leaked = sorted(n for n in want if n in on_boot)
    print(f"interactive: chosen volume holds "
          f"{sorted(CD.mac_path(n) for n in on_dest)}")
    print(f"interactive: archive's volume holds "
          f"{sorted(CD.mac_path(n) for n in on_boot)}")
    if missing:
        print("interactive: NOT on the chosen volume: "
              + ", ".join(CD.mac_path(n) for n in missing))
    if leaked:
        print("interactive: leaked onto the archive's volume: "
              + ", ".join(CD.mac_path(n) for n in leaked))
    if elapsed is None:
        print("interactive: the extraction never settled")
    ok = not missing and not leaked
    print("interactive: destination " + ("HONOURED" if ok else "WRONG"))
    return ok


def phase_wd(args, appbin, workdir, shot):
    """Does the extraction land beside the archive, or at the volume root?

    Standard File hands back `SFReply.vRefNum`, and the application passes it
    to the File Manager with `dirID` 0. On System 7 and later that refNum is a
    WORKING DIRECTORY reference rather than a plain volume refNum, which
    OPEN_ITEMS.md has listed as untested code since M10 — and it could not
    have been tested before now, because every previous run put the archive at
    the volume ROOT, where the working directory and the root are the same
    directory and a mistake has nowhere to show.

    So: archive inside a folder, navigate into the folder in SFGetFile, and
    look at where the output actually landed.
    """
    stock = os.path.join(R.VMAC_HOME, args.system)
    bootimg = os.path.join(workdir, "boot-wd.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin, bootimg,
         "--finder", "--data",
         f"{args.fixture}:{ARCHIVE_FOLDER}:archive.sit")

    icons = WD_ICONS.get(args.system)
    if icons is None:
        raise SystemExit(f"interactive: no Finder icon positions known for "
                         f"{args.system} — run once, look at wd-2-volume.png, "
                         f"and add them to WD_ICONS")
    mac = Mac(bootimg, args.emu, workdir)
    try:
        if mac.settle(os.path.join(args.outdir, ".settle.png"),
                      interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never reached the Finder")
        shot(mac, "wd-1-desktop.png")

        mac.click(*FINDER_VOLUME_ICON, double=True)       # open the boot volume
        time.sleep(4.0)
        shot(mac, "wd-2-volume.png")                      # Archives + macextract

        mac.click(*icons["app"], double=True)             # launch macextract
        time.sleep(args.launch_wait)
        shot(mac, "wd-3-sfgetfile.png")                   # at the volume root

        mac.click(*SF_SUBFOLDER_ROW, double=True)         # descend into Archives
        time.sleep(3.0)
        shot(mac, "wd-4-in-folder.png")                   # now inside it

        mac.click(*SF_FIRST_ROW)                          # the archive
        mac.key("Return")
        shot(mac, "wd-4b-destination.png")   # opens INSIDE Archives, not at /
        accept_destination(mac)
        mac.settle(os.path.join(args.outdir, ".settle.png"),
                   interval=5.0, quiet=EXTRACT_QUIET,
                   timeout=args.complete_timeout)
        shot(mac, "wd-5-complete.png")
        mac.key("Return")                                 # dismiss the alert
        time.sleep(2.0)
        mac.command_key("period")                         # quit to the Finder
        time.sleep(args.launch_wait)
        shot(mac, "wd-6-root-after.png")   # the ROOT: must NOT hold the output

        mac.click(*icons["folder"], double=True)          # open Archives
        time.sleep(5.0)
        shot(mac, "wd-7-folder-after.png") # the FOLDER: must hold the output
    finally:
        mac.close()

    # The verdict comes off the volume, not off wd-6 and wd-7. Those two
    # frames are aimed at Finder icons by coordinate, and on 2026-08-09
    # wd-7 photographed the System Folder — the volume's icons overlap at
    # the Finder's default spacing, so "the output is not in this window"
    # was true of a window nobody meant to open.
    want = expected_names(args.fixture, workdir)
    got = volume_names(os.path.join(workdir, "boot.hfv"))
    missing = sorted(n for n in want if (ARCHIVE_FOLDER,) + n not in got)
    at_root = sorted(n for n in want if n in got)
    print("interactive: the volume holds "
          + ", ".join(sorted(CD.mac_path(n) for n in got)))
    if missing:
        print(f"interactive: NOT inside {ARCHIVE_FOLDER}: "
              + ", ".join(CD.mac_path(n) for n in missing))
    if at_root:
        print("interactive: at the volume ROOT, where a working-directory "
              "mistake puts it: " + ", ".join(CD.mac_path(n) for n in at_root))
    ok = bool(want) and not missing and not at_root
    print("interactive: working directory " + ("HONOURED" if ok else "WRONG"))
    print("interactive: wd-6 is the volume root and wd-7 the archive's folder; "
          "the print above is what decides.")
    return ok


def phase_e2e(args, appbin, workdir, shot):
    """The user's whole story, in one boot, with the FINDER left in place.

    Everything else here runs the application as the boot shell, which is not
    how anyone uses it and which cannot answer two of the checklist items at
    all: the Finder has to exist for the application to be double-clicked, and
    it has to exist afterwards for an EXTRACTED application to be
    double-clicked. Standard File's Drive button needs a second volume, so one
    is mounted.

        launch from the Finder -> SFGetFile -> Drive (volume navigation) ->
        open -> progress dialog -> "Extraction complete." -> quit ->
        double-click the extracted application
    """
    if args.system not in FINDER_ICONS:
        raise SystemExit(f"interactive: no Finder icon geometry for "
                         f"{args.system} — boot it once with --e2e on a "
                         f"system that has some, look at e2e-2-volume.png, "
                         f"and add its icons to FINDER_ICONS")
    stock = os.path.join(R.VMAC_HOME, args.system)
    bootimg = os.path.join(workdir, "boot-e2e.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin, bootimg,
         "--finder", "--data", f"{args.fixture}:archive.sit")
    # A second volume, so Drive has somewhere to go. Its contents do not
    # matter; that SFGetFile switches to it and back is the point.
    second = os.path.join(workdir, "second.dsk")
    R.make_floppy(second, "Second")

    mac = Mac(bootimg, args.emu, workdir, extra=(second,))
    try:
        if mac.settle(os.path.join(args.outdir, ".settle.png"),
                      interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never reached the Finder")
        shot(mac, "e2e-1-desktop.png")

        mac.click(*FINDER_VOLUME_ICON, double=True)      # open the boot volume
        time.sleep(4.0)
        shot(mac, "e2e-2-volume.png")

        mac.click(*FINDER_APP_ICON, double=True)         # launch macextract
        time.sleep(args.launch_wait)
        shot(mac, "e2e-3-sfgetfile.png")

        mac.click(*SF_DRIVE)                             # -> the other volume
        time.sleep(2.0)
        shot(mac, "e2e-4-other-volume.png")
        mac.click(*SF_DRIVE)                             # -> back again
        time.sleep(2.0)
        shot(mac, "e2e-5-back-to-boot.png")

        mac.click(*SF_FIRST_ROW)
        mac.key("Return")                                # Open
        shot(mac, "e2e-5b-destination.png")              # where do they go?
        accept_destination(mac)                          # beside the archive
        elapsed = mac.settle(os.path.join(args.outdir, ".settle.png"),
                             interval=5.0, quiet=EXTRACT_QUIET,
                             timeout=args.complete_timeout)
        shot(mac, "e2e-6-complete.png")
        mac.key("Return")                                # dismiss the alert
        time.sleep(2.0)

        # Cmd-. is Standard File's Cancel; the application's SFGetFile loop
        # ends on !reply.good, so this is how it quits back to the Finder.
        mac.command_key("period")
        time.sleep(args.launch_wait)
        shot(mac, "e2e-7-back-in-finder.png")

        mac.click(*FINDER_EXTRACTED_APPL, double=True)   # launch what we made
        time.sleep(args.launch_wait)
        shot(mac, "e2e-8-extracted-app-running.png")
    finally:
        mac.close()
    print(f"interactive: e2e extraction settled after "
          f"~{elapsed if elapsed is None else round(elapsed)}s of emulated "
          f"Mac Plus time")


# The "locate part N" alert (ALRT 131). Its default button is item 1,
# Find..., so that one is reached with Return and never needs a coordinate.
# Skip and Cancel do: DLOG-style arithmetic off mac/macextract.r, where the
# ALRT is at (top 90, left 80) and the DITL rects are {92,196,112,266} and
# {92,110,112,180}, giving the centres below. THEY MOVE IF THE ALERT DOES.
SEG_SKIP = (311, 192)
SEG_CANCEL = (225, 192)

# Rows in Standard File's list are 16 points apart; the first is SF_FIRST_ROW.
# calibrate() recomputes this for the booted system.
SF_SECOND_ROW = (SF_FIRST_ROW[0], SF_FIRST_ROW[1] + SF_ROW_HEIGHT)


def cut_into_parts(fixture, workdir, n=3):
    """Cut an archive into `n` StuffIt segment parts. Returns (bytes, name,
    [paths]) — the same split --segments uses, so both phases agree on what
    a part is."""
    sys.path.insert(0, os.path.join(R.REPO, "tools"))
    from synth_sitsplit import header                            # noqa: E402

    original = open(fixture, "rb").read()
    name = os.path.basename(fixture).encode("mac_roman")[:31] or b"Joined"
    cuts = [len(original) * i // n for i in range(n)] + [len(original)]
    parts = []
    for i in range(n):
        p = os.path.join(workdir, "part%d" % (i + 1))
        with open(p, "wb") as f:
            f.write(header(i + 1, name, 0, len(original)))
            f.write(original[cuts[i]:cuts[i + 1]])
        parts.append(p)
    return original, name, parts


def drop_disk(mac, image):
    """Insert a disk image into the RUNNING emulator.

    Mini vMac's X11 build takes a disk at runtime through exactly one
    door — XDND — and there is no window manager or file manager on this
    display to drag from, so tools/vmac/xdnd_insert.c is the missing drag
    source. Built on demand into the emulator's own directory.
    """
    exe = os.path.join(R.VMAC_HOME, "xdnd_insert")
    src = os.path.join(HERE, "xdnd_insert.c")
    if not os.path.exists(exe) or os.path.getmtime(src) > os.path.getmtime(exe):
        subprocess.run(["cc", "-O2", "-o", exe, src, "-lX11"], check=True)
    r = subprocess.run([exe, image], env=dict(os.environ, DISPLAY=mac.dpy.name),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"interactive: the drop failed: {r.stderr.strip()}")


def phase_diskswap(args, appbin, workdir, shot):
    """Does putting the disk in answer the question, without a click?

    The application asks for part 2. The part is on a floppy that is not
    in the machine. A person's answer is to put the disk in — and until
    now that did nothing: they still had to work through an alert about a
    disk already sitting in the drive.

    The walk inserts TWO disks. The first is a decoy holding no part of
    this set, and the alert must still be there afterwards; that is the
    negative control, and without it the phase could not tell "the
    application reacted to the right disk" from "the alert went away".
    The second holds parts 2 and 3, and nothing is clicked after it goes
    in. The phase ends on the joined file read back off the boot volume,
    byte for byte against the fixture, because "Extraction complete." is
    not evidence about bytes.
    """
    original, name, parts = cut_into_parts(args.fixture, workdir)

    bootimg = os.path.join(workdir, "boot-swap.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
         os.path.join(R.VMAC_HOME, args.system), appbin, bootimg,
         "--data", f"{parts[0]}:archive.sit")
    decoy = os.path.join(workdir, "decoy.dsk")
    R.make_floppy(decoy, "Decoy", extras=[(parts[0], "not-the-one")])
    later = os.path.join(workdir, "later.dsk")
    R.make_floppy(later, "Later",
                  extras=[(parts[1], "part-two"), (parts[2], "zzz")])

    scratch = os.path.join(args.outdir, ".settle.png")
    elapsed, still_asking = None, None
    mac = Mac(bootimg, args.emu, workdir)      # neither floppy at boot
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never settled")
        shot(mac, "swap-1-launched.png")

        mac.click(*SF_FIRST_ROW)               # archive.sit = part 1
        mac.key("Return")
        accept_destination(mac)                # onto the boot volume
        wait_for_alert(mac, scratch)
        shot(mac, "swap-2-locate.png")         # "Part 2 has not been found"
        asking = open(scratch, "rb").read()

        # The decoy: a disk of this set's part 1, which is not what was
        # asked for. The alert must survive it.
        drop_disk(mac, decoy)
        time.sleep(8.0)
        mac.shot(scratch)
        still_asking = open(scratch, "rb").read() == asking
        shot(mac, "swap-3-after-decoy.png")

        # The real one. Nothing is clicked from here on.
        drop_disk(mac, later)
        elapsed = mac.settle(scratch, interval=5.0, quiet=EXTRACT_QUIET,
                             timeout=args.complete_timeout)
        shot(mac, "swap-4-complete.png")
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    got = read_joined(os.path.join(workdir, "boot.hfv"), name, workdir)
    ok = got == original
    print(f"interactive: the decoy disk "
          + ("left the alert up" if still_asking else "DISMISSED THE ALERT"))
    print(f"interactive: joined file off the boot volume: "
          + ("BYTE-EXACT" if ok else
             f"WRONG ({len(got) if got is not None else 'not found'} B, "
             f"{len(original)} B expected)"))
    if elapsed is not None:
        print(f"interactive: settled ~{elapsed:.0f}s after the disk went in")
    ok = ok and bool(still_asking)
    print("interactive: disk insertion " + ("HANDLED" if ok else "NOT HANDLED"))
    return ok


def read_joined(image, name, workdir):
    """The joined archive off an HFS image, or None. MacRoman throughout:
    the volume holds names like `StuffIt Expander™`, and a `text=True`
    decode of a listing raises on those — on the path that only runs when
    the run has already failed."""
    out = os.path.join(workdir, "joined-read.bin")
    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    try:
        if CD.hfs(env, "hmount", image).returncode != 0:
            return None
        got = CD.hfs(env, "hcopy", "-r", b":" + name, out.encode())
        if got.returncode != 0:
            # `-a`: this line runs only when the file was NOT found, so a
            # listing that hides an invisible file is misleading exactly
            # when it is read (2026-09-23).
            listing = CD.hfs(env, "hls", "-a", "-l").stdout.decode("mac_roman")
            print("interactive: not on the volume, which holds:\n" + listing)
        CD.hfs(env, "humount")
        return open(out, "rb").read() if got.returncode == 0 else None
    finally:
        shutil.rmtree(home, ignore_errors=True)


def build_named_set(kind, workdir, fixture):
    """A set whose parts are placed by NAME, and the one file it must
    produce. Both schemes are given ONE payload on purpose: the check at
    the end is a byte comparison, and one file can be compared without
    walking a tree off an HFS volume.

    **`zip` needs a fixture larger than 64 KB.** `zip -s 64k` marks the
    archive as split whatever its size, so a smaller payload produces one
    `Aset.zip` and no `Aset.z01` at all — a one-part set the application
    correctly refuses with *"This archive has more parts. Find them and
    try again."* That photographs as an application bug and is an
    invocation error; it cost a run on 2026-09-23.
    `fixtures/derived-xmasbeeps.sit` (286 KB) is what this is driven with.
    `split` has no such floor: it cuts any payload into three.
    """
    d = os.path.join(workdir, "namedset")
    os.makedirs(d, exist_ok=True)
    blob = open(fixture, "rb").read()
    # The stem begins with "A" so that the first part is the FIRST ROW of
    # Standard File whatever else is on the volume. The boot volume's root
    # holds an invisible `Desktop` file, and a set called Set.z01 sorts
    # AFTER it: the first version of this clicked row one, opened Desktop,
    # and the application said the file could not be extracted — which it
    # cannot, entirely correctly. A harness bug that photographs as an
    # application bug, which is the shape this directory keeps meeting.
    if kind == "zip":
        shutil.copyfile(fixture, os.path.join(d, "payload.bin"))
        R.sh("zip", "-q", "-0", "-s", "64k", os.path.join(d, "Aset.zip"),
             "payload.bin", cwd=d)
        os.remove(os.path.join(d, "payload.bin"))
        parts = sorted(glob.glob(os.path.join(d, "Aset.z*")))
        return parts, b"payload.bin", blob
    cut = (len(blob) + 2) // 3
    parts = []
    for i in range(3):
        p = os.path.join(d, "Ablob.%03d" % (i + 1))
        with open(p, "wb") as f:
            f.write(blob[i * cut:(i + 1) * cut])
        parts.append(p)
    return parts, b"Ablob", blob


def volume_entries(image, ignore=()):
    """Every NAME at the root of <image>, minus the Finder's own and
    <ignore>. The entry set three phases compare against what the
    application should have written.

    Extracted 2026-09-23 from `phase_wrapped`, `phase_chain` and
    `phase_named`, which held three copies of it. Two things follow from
    having one:

    - **`walkprobe.py` can grade it.** The copies could not be graded by
      anything: each was inline in a phase that drives an emulator, so
      "these select by a name they chose themselves, so `-a` is
      harmless" was a reading of the code rather than a measurement.
      Three of the nine ungraded listers become one graded walk.
    - **the `Icon\r` bug is fixed once.** All three called
      `splitlines()`, which splits on a carriage return as well — and a
      CR is a legal HFS filename character, the last one of `Icon\r`.
      `hdir` prints it verbatim, so a custom folder icon arrived as a
      name cut in half. The same defect the two Compact Pro walks had,
      in a different spelling.
    """
    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    try:
        if CD.hfs(env, "hmount", image).returncode != 0:
            return set()
        listing = CD.hfs(env, "hdir", "-a", ":").stdout
        CD.hfs(env, "humount")
    finally:
        shutil.rmtree(home, ignore_errors=True)
    drop = set(ignore) | FINDER_OWN
    got = set()
    # split on b"\n" alone: splitlines() would cut `Icon\r` in two.
    for raw in listing.split(b"\n"):
        m = LISTING_DATE_B.search(raw)
        if not m:
            continue
        nm = m.group(1).decode("mac_roman", "replace")
        if nm not in drop:
            got.add(nm)
    return got


def phase_wrapped(args, appbin, workdir, shot):
    """A set whose parts are each in their own envelope — Archive.sit.1.hqx,
    which is how one was actually downloaded.

    Every part is BinHex- or MacBinary-wrapped, under names that say
    nothing, and the one the user opens is part 1. The application has to
    take the envelope off THAT, notice the result is a segment, go back to
    the folder the user's file came from, look inside the other envelopes
    for the missing parts, decode them next to the output, join, and tidy
    up after itself. The check is the archive's own contents, against the
    Linux CLI on the same set.
    """
    sys.path.insert(0, os.path.join(R.REPO, "tools"))
    import synth_wrapped as W                                # noqa: E402
    from synth_sitsplit import header                        # noqa: E402

    original = open(args.fixture, "rb").read()
    inner = os.path.basename(args.fixture).encode("mac_roman")[:31]
    d = os.path.join(workdir, "wrapped")
    os.makedirs(d, exist_ok=True)
    cuts = [0, len(original) // 3, 2 * len(original) // 3, len(original)]
    raw = []
    for i in range(3):
        p = os.path.join(d, "raw%d" % (i + 1))
        with open(p, "wb") as f:
            f.write(header(i + 1, inner, 0, len(original)))
            f.write(original[cuts[i]:cuts[i + 1]])
        raw.append(p)
    # Part 1 in BinHex and named to sort first; the others in different
    # envelopes under names that resemble nothing.
    W.wrap_file(raw[0], d, "hqx", dest_name="Apart.sit.1")
    W.wrap_file(raw[1], d, "bin", dest_name="zzz-download")
    W.wrap_file(raw[2], d, "hqx", dest_name="Other.9")
    onvol = ["Apart.sit.1.hqx", "zzz-download.bin", "Other.9.hqx"]

    data = []
    for n in onvol:
        data += ["--data", f"{os.path.join(d, n)}:{n}"]
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
         os.path.join(R.VMAC_HOME, args.system), appbin,
         os.path.join(workdir, "boot-wrapped.hfv"), *data)

    scratch = os.path.join(args.outdir, ".settle.png")
    mac = Mac(os.path.join(workdir, "boot-wrapped.hfv"), args.emu, workdir)
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never settled")
        shot(mac, "wrapped-1-sfgetfile.png")
        mac.click(*SF_FIRST_ROW)                 # Apart.sit.1.hqx
        mac.key("Return")
        accept_destination(mac)
        mac.settle(scratch, interval=5.0, quiet=EXTRACT_QUIET,
                   timeout=args.complete_timeout)
        shot(mac, "wrapped-2-complete.png")
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    got = {n for n in volume_entries(os.path.join(workdir, "boot.hfv"),
                                     ignore={"System Folder", "MacExtract"}
                                     | set(onvol))
           if not n.startswith("StuffIt Expander")}

    # The reference CLI, same binary and same guard as phase_chain: this
    # named `build/dev` until 2026-09-03, which nothing builds and which
    # `make clean` (rm -rf build) removes, so the phase died on a
    # traceback for anyone who had run `./ci.sh` and nothing else.
    if not os.path.exists(CD.CLI):
        print(f"interactive: no CLI at {CD.CLI} — run `make BUILD=build/rel`")
        return False
    ref = os.path.join(workdir, "_cli")
    os.makedirs(ref, exist_ok=True)
    R.sh(CD.CLI, "x", "-o", ref, os.path.join(d, "Apart.sit.1.hqx"))
    want = set(os.listdir(ref))
    left = [g for g in got if g.startswith("MacExtract part")]
    ok = got == want and not left
    print(f"interactive: the volume holds {sorted(got)}")
    print(f"interactive: the Linux CLI gives {sorted(want)}")
    print("interactive: " + ("MATCH" if got == want else "MISMATCH")
          + ("; decoded parts left behind: %s" % left if left
             else "; nothing of ours left behind"))
    return ok


def phase_chain(args, appbin, workdir, shot):
    """Does the application take ALL the envelope layers off?

    A real download is chained — Archive.sit.hqx — and until 2026-08-14
    this application took one layer off and stopped, leaving the user to
    open the result again. README.md promised otherwise the whole time.
    So this drives the chain through the real UI and compares the NAMES
    on the volume against what the Linux CLI produces from the same file,
    which has always recursed. The intermediate must be gone too: a
    passing name set with `boogers152.sit` still sitting there would mean
    the layers came off and the litter did not.
    """
    onmac = "Achain" + os.path.splitext(args.fixture)[1]
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
         os.path.join(R.VMAC_HOME, args.system), appbin,
         os.path.join(workdir, "boot-chain.hfv"),
         "--data", f"{args.fixture}:{onmac}")
    bootimg = os.path.join(workdir, "boot-chain.hfv")

    scratch = os.path.join(args.outdir, ".settle.png")
    mac = Mac(bootimg, args.emu, workdir)
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never settled")
        shot(mac, "chain-1-sfgetfile.png")
        mac.click(*SF_FIRST_ROW)
        mac.key("Return")
        accept_destination(mac)
        mac.settle(scratch, interval=5.0, quiet=EXTRACT_QUIET,
                   timeout=args.complete_timeout)
        shot(mac, "chain-2-complete.png")
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    # What the Mac ended up with, at the root of the volume it wrote to.
    # `Desktop` was in this ignore set by hand until 2026-09-23;
    # `volume_entries` drops the whole of FINDER_OWN, which also covers
    # the `Desktop DB`/`Desktop DF` a later System writes instead.
    got = {n for n in volume_entries(
               os.path.join(workdir, "boot.hfv"),
               ignore={"System Folder", "StuffIt Expander\u2122 4.0.1 Folder",
                       "MacExtract", onmac})
           if not n.startswith("StuffIt Expander")}

    # What the Linux CLI makes of the same file, recursion and all. The
    # same binary every other reference in this file uses: this named
    # `build/dev` until 2026-08-27, which nothing here builds, so the
    # phase died on a traceback for anyone who had run `./ci.sh` and
    # nothing else.
    if not os.path.exists(CD.CLI):
        print(f"interactive: no CLI at {CD.CLI} — run `make BUILD=build/rel`")
        return False
    ref = os.path.join(workdir, "_cli")
    os.makedirs(ref, exist_ok=True)
    R.sh(CD.CLI, "x", "-o", ref, args.fixture)
    want = set(os.listdir(ref))

    ok = got == want
    print(f"interactive: after the chain, the volume holds {sorted(got)}")
    print(f"interactive: the Linux CLI produces           {sorted(want)}")
    print("interactive: " + ("MATCH" if ok else "MISMATCH")
          + " — and the intermediate is "
          + ("gone" if not any(g.endswith(".sit") and g != onmac for g in got)
             else "STILL THERE"))
    return ok


def phase_named(args, appbin, workdir, shot):
    """The two schemes that are placed by FILENAME, on the Mac.

    Compact Pro and StuffIt sets are found by header, so run.py can drive
    them under any names at all. These two cannot be: a spanned zip part
    proves nothing about itself unless it is the first or last, and a
    .NNN split part proves nothing anywhere. The names ARE the scheme, so
    the parts have to reach the Mac under their real ones — which the
    autotest cannot do, since it opens a file called `archive.sit`. Hence
    Standard File, where the name comes from the user.

    Ends on a byte comparison, not a screenshot: the one file the set
    must produce is read back off the volume the Mac wrote to.
    """
    parts, outname, expect = build_named_set(args.named, workdir, args.fixture)
    for_each = []
    for p in parts:
        for_each += ["--data", f"{p}:{os.path.basename(p)}"]
    bootimg = os.path.join(workdir, "boot-named.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
         os.path.join(R.VMAC_HOME, args.system), appbin, bootimg, *for_each)

    scratch = os.path.join(args.outdir, ".settle.png")
    mac = Mac(bootimg, args.emu, workdir)
    elapsed = None
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never settled")
        shot(mac, f"named-{args.named}-1-sfgetfile.png")
        # Sorted case-insensitively, the first row is the FIRST part —
        # Set.z01 or Blob.001 — which is deliberately not the one that
        # carries the count in either scheme.
        mac.click(*SF_FIRST_ROW)
        mac.key("Return")
        shot(mac, f"named-{args.named}-2-destination.png")
        accept_destination(mac)
        elapsed = mac.settle(scratch, interval=5.0, quiet=EXTRACT_QUIET,
                             timeout=args.complete_timeout)
        shot(mac, f"named-{args.named}-3-complete.png")
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    # What the joined set produced, compared against the Linux CLI on the
    # same parts. NOT "is the joined file on the volume": since 2026-08-14
    # the application unwraps what it joins, so a set whose payload is an
    # archive — which both of these are — leaves that archive's CONTENTS
    # behind and deletes the archive. This phase checked for the file and
    # failed the day the loop landed; the application was right and the
    # expectation was a day old.
    onvol = {os.path.basename(p) for p in parts}
    got = {n for n in volume_entries(os.path.join(workdir, "boot.hfv"),
                                     ignore={"System Folder", "MacExtract"}
                                     | set(onvol))
           if not n.startswith("StuffIt Expander")}

    # The reference CLI, same binary and same guard as phase_chain — see
    # phase_wrapped for what the old `build/dev` path cost.
    if not os.path.exists(CD.CLI):
        print(f"interactive: no CLI at {CD.CLI} — run `make BUILD=build/rel`")
        return False
    ref = os.path.join(workdir, "_cli")
    os.makedirs(ref, exist_ok=True)
    R.sh(CD.CLI, "x", "-o", ref, parts[0])
    want = set(os.listdir(ref))
    ok = got == want
    print(f"interactive: the volume holds {sorted(got)}")
    print(f"interactive: the Linux CLI gives {sorted(want)}")
    print("interactive: " + ("MATCH" if ok else "MISMATCH")
          + f" for the {args.named} set")
    if elapsed is not None:
        print(f"interactive: settled ~{elapsed:.0f}s after opening part 1")
    return ok


def phase_segments(args, appbin, workdir, shot):
    """The segmented-archive dialog: can a person actually find part 2?

    run.py proves the JOIN, but only through the autotest build, which has
    no user and does not compile SegAskUser at all — every part in those
    runs was found by the folder scan. This is the other half: part 1 sits
    alone on the boot volume and the rest are on a second floppy, so the
    scan must fail and the alert must come up.

    The walk is deliberately the awkward one. The wrong part is offered
    first, to see whether it is refused BY FINGERPRINT and named for what
    it actually is, and only then the right one — which should also drag
    in the part beside it, because locating one part rescans its folder.

    Unlike the other phases this one does not end at a screenshot: the
    boot volume is read back afterwards and the joined file compared,
    byte for byte, against the archive the parts were cut from. A
    screenshot of "Extraction complete." is not evidence that the bytes
    are right.
    """
    import struct
    sys.path.insert(0, os.path.join(R.REPO, "tools"))
    from synth_sitsplit import header, HEAD                  # noqa: E402

    original = open(args.fixture, "rb").read()
    name = os.path.basename(args.fixture).encode("mac_roman")[:31] or b"Joined"
    cuts = [0, len(original) // 3, 2 * len(original) // 3, len(original)]
    parts = []
    for i in range(3):
        p = os.path.join(workdir, "part%d" % (i + 1))
        with open(p, "wb") as f:
            f.write(header(i + 1, name, 0, len(original)))
            f.write(original[cuts[i]:cuts[i + 1]])
        parts.append(p)

    # Part 1 alone on the boot volume; parts 2 and 3 on a floppy, under
    # names that resemble neither the archive nor each other. Sorted by
    # the Finder they read "part-two", then "zzz", so the WRONG one (part
    # 3) is the second row and the right one is the first.
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
         os.path.join(R.VMAC_HOME, args.system), appbin,
         os.path.join(workdir, "boot-interactive.hfv"),
         "--data", f"{parts[0]}:archive.sit")
    bootimg = os.path.join(workdir, "boot-interactive.hfv")
    partsdsk = os.path.join(workdir, "parts.dsk")
    R.make_floppy(partsdsk, "Parts",
                  extras=[(parts[1], "part-two"), (parts[2], "zzz")])

    scratch = os.path.join(args.outdir, ".settle.png")
    mac = Mac(bootimg, args.emu, workdir, extra=(partsdsk,))
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never settled")
        shot(mac, "seg-1-launched.png")

        # Standard File opens on the LAST-INSERTED volume, which is the
        # Parts floppy, not the boot disk. The first version of this phase
        # assumed otherwise and opened "part-two" — so the app asked for
        # part 1, entirely correctly, and the screenshot looked like a bug
        # in the application. Drive first, and photograph the result before
        # clicking a row.
        mac.click(*SF_DRIVE)                 # -> the boot volume
        time.sleep(2.0)
        shot(mac, "seg-2-boot-volume.png")

        mac.click(*SF_FIRST_ROW)             # archive.sit = part 1
        mac.key("Return")
        accept_destination(mac)              # onto the boot volume
        time.sleep(10.0)
        shot(mac, "seg-3-locate.png")        # part 2 is not beside part 1

        mac.key("Return")                    # default button: Find...
        time.sleep(3.0)
        # Which volume Standard File lands on here is NOT ours to assume:
        # it depends on what has consumed the disk-inserted event for the
        # parts floppy, which changes with what the alert is doing. So it
        # is photographed before anything is clicked, and the Drive click
        # below is aimed using that frame.
        shot(mac, "seg-3b-find-opens-on.png")
        mac.click(*SF_DRIVE)                 # over to the Parts floppy
        time.sleep(2.0)
        shot(mac, "seg-4-parts-volume.png")

        mac.click(*SF_SECOND_ROW)            # "zzz" — part THREE, on purpose
        mac.key("Return")
        time.sleep(4.0)
        shot(mac, "seg-5-wrong-part.png")    # refused, and named as part 3

        mac.key("Return")                    # dismiss; back to the alert
        time.sleep(2.0)
        mac.key("Return")                    # Find... again
        time.sleep(3.0)
        shot(mac, "seg-6-sfgetfile-again.png")

        # Standard File reopens on the volume it was last left on, so no
        # second Drive click here; seg-6 is what says whether that held.
        mac.click(*SF_FIRST_ROW)             # "part-two" — the right one
        mac.key("Return")
        elapsed = mac.settle(scratch, interval=5.0, quiet=EXTRACT_QUIET,
                             timeout=args.complete_timeout)
        shot(mac, "seg-7-complete.png")
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    # The bytes, not the screenshot — but the RIGHT bytes, which took a
    # correction. This phase used to read back a file named after the
    # original archive and compare it to the archive the parts were cut
    # from. That file never appears: the shipped application unwraps
    # envelope chains, so the joined `.sit` is consumed and its CONTENTS
    # are what land on the volume. The check therefore failed on every run
    # while the Mac was doing exactly the right thing — the same shape of
    # error `expected_names` documents for chained fixtures, and in the
    # same direction, "looks like an application bug" (DECISIONS.md
    # 2026-08-27). Verified 2026-08-31: the volume held `Cal 3.02`,
    # `Cal.Intro` and `Calendar Tools`, both forks and type/creator intact.
    written = os.path.join(workdir, "boot.hfv")     # Mac()'s private copy
    want = expected_names(args.fixture, workdir)
    if not want:
        return False
    on_boot = volume_names(written)
    missing = sorted(n for n in want if n not in on_boot)
    print(f"interactive: the joined archive's contents on the boot volume: "
          f"{sorted(CD.mac_path(n) for n in on_boot)}")
    if missing:
        print("interactive: MISSING after the join: "
              + ", ".join(CD.mac_path(n) for n in missing))
    if elapsed is not None:
        print(f"interactive: settled ~{elapsed:.0f}s after the part was given")
    print("interactive: joined set extracted: "
          + ("COMPLETE" if not missing else "INCOMPLETE"))
    return not missing


def phase_password(args, appbin, workdir, shot):
    """Does the application ask for a password, and take one?

    The engine asks its host for a password when an entry turns out to
    need one — not before — so the only way to see that path is to drive
    the dialog. The archive is the encrypted StuffIt classic one
    tools/synth_crypt.py writes, which is also the one shape where the
    key material is NOT in the file being read: 'MKey' lives in the
    archive's resource fork, so this checks the Mac side of that too.
    A MacBinary file is what carries both forks onto the volume.

    Two asks, deliberately: the first password given is WRONG, so the
    dialog has to come back saying so. That is the retry path, and it is
    the one a user meets most.

    Ends on the extracted bytes read off the volume, so the phase can
    fail on its own rather than on somebody reading a screenshot.
    """
    sys.path.insert(0, os.path.join(R.REPO, "tools"))
    import synth_crypt as SC                                # noqa: E402
    import synth_wrapped as W                               # noqa: E402

    password = "hushnow"
    sit, rsrc = SC.build_sit_des(password.encode("mac_roman"))
    binpath = os.path.join(workdir, "secret.bin")
    open(binpath, "wb").write(W.macbinary("Secret.sit", sit, rsrc,
                                          b"SIT!", b"SIT!"))
    stock = os.path.join(R.VMAC_HOME, args.system)
    bootimg = os.path.join(workdir, "boot-password.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin,
         bootimg, "--macbin", f"{binpath}:Secret.sit")

    scratch = os.path.join(args.outdir, ".settle.png")
    mac = Mac(bootimg, args.emu, workdir)
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never settled")
        shot(mac, "pw-1-sfgetfile.png")
        # SECOND row: the boot volume has an invisible-to-the-Finder
        # `Desktop` file that sorts before `Secret.sit`, and clicking
        # the first row opens that instead — which looks exactly like a
        # failure to read the archive.
        mac.click(SF_FIRST_ROW[0], SF_FIRST_ROW[1] + SF_ROW_HEIGHT)
        mac.key("Return")                     # Open -> destination dialog
        time.sleep(3.0)
        shot(mac, "pw-2-destination.png")
        mac.key("Return")                     # Save -> extraction starts
        time.sleep(8.0)
        shot(mac, "pw-3-asked.png")
        for ch in "wrongone":                 # the refused one, first
            mac.key(ch)
        shot(mac, "pw-4-typed-wrong.png")
        mac.key("Return")
        time.sleep(4.0)
        shot(mac, "pw-5-asked-again.png")
        for ch in password:
            mac.key(ch)
        shot(mac, "pw-6-typed.png")
        mac.key("Return")
        mac.settle(scratch, interval=5.0, quiet=EXTRACT_QUIET,
                   timeout=args.complete_timeout)
        shot(mac, "pw-7-complete.png")
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    written = os.path.join(workdir, "boot.hfv")
    bad = 0
    for name, data, rsrcfork in SC.SIT_CASES:
        got = read_joined(written, name.encode("mac_roman"), workdir)
        if got is None:
            print(f"interactive: {name!r} is not on the volume")
            bad += 1
            continue
        if got != data:
            print(f"interactive: {name!r} came out {len(got)} bytes, "
                  f"wanted {len(data)}")
            bad += 1
    print("interactive: password dialog "
          + ("WORKS — every entry decrypted" if not bad else "FAILED"))
    return bad == 0


def phase_drop(args, appbin, workdir, shot):
    """Does the FINDER hand a dropped document to this application?

    The application has no code to receive one — nothing here reads
    AppParmHandle — so what this measures is the FINDER's half: whether
    dropping an archive on the application's icon launches it at all, on the
    system being booted. That is the question that decides whether the
    receiving code is worth its bytes, and it is a property of the system
    rather than of anything in this repository.

    Get Info is photographed in the same boot, because the 'vers' resources
    have never been seen displayed either (OPEN_ITEMS.md, *No Finder has been
    seen displaying the version*).

        drop-1-desktop.png    booted to the Finder
        drop-2-volume.png     boot volume open: the archive and the application
        drop-3-getinfo.png    Get Info on the application: the version line,
                              taken FIRST because the drop lands the archive
                              on top of the icon this clicks
        drop-4-control.png    THE CONTROL — the archive icon dragged to empty
                              space. If it did not move, no later frame means
                              anything, because the drag was never delivered
        drop-5-dropped.png    the archive dragged onto the application's icon
        drop-6-after-wait.png the same, after a launch's worth of seconds
        drop-7-extracted.png  the destination dialog accepted and the
                              extraction run, so the frame says the
                              application was handed the right FILE rather
                              than merely woken up

    **What this cannot see.** It photographs; it reads nothing off the volume.
    A frame showing Standard File proves the application launched, but not
    that it was told WHICH file — nothing in the application looks, so that
    half cannot be tested until the receiving code exists. A frame showing the
    desktop unchanged is only evidence once drop-3 shows the control drag
    moved the icon."""
    if args.system not in FINDER_ICONS:
        raise SystemExit(f"interactive: no Finder icon geometry for "
                         f"{args.system} — boot it once with --e2e, look at "
                         f"e2e-2-volume.png, and add its icons to FINDER_ICONS")
    icons = FINDER_ICONS[args.system]
    bootimg = os.path.join(workdir, "boot-drop.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock_image(args),
         appbin, bootimg, "--finder", "--data", f"{args.fixture}:archive.sit")

    # The archive has to LOOK like one to the Finder. mkboot's --data copies
    # a data fork and nothing else, so the file lands with hfsutils' default
    # type — and a Finder that gates a drop on the application's 'FREF' list
    # would refuse a type nobody declared, which is indistinguishable from a
    # Finder that has no such gesture at all. 'SIT!' is what StuffIt itself
    # writes and what a downloaded .sit carries.
    import mkboot as MB
    hfs = MB.HFS(bootimg)
    hfs.run("hattrib", "-t", args.drop_type, "-c", "SIT!",
            hfs.path("archive.sit"))
    hfs.run("humount", bootimg, check=False)

    mac = Mac(bootimg, args.emu, workdir)
    try:
        if mac.settle(os.path.join(args.outdir, ".settle.png"),
                      interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: the machine never reached the Finder")
        shot(mac, "drop-1-desktop.png")

        mac.click(*icons["volume"], double=True)          # open the boot volume
        time.sleep(4.0)
        shot(mac, "drop-2-volume.png")

        # Get Info BEFORE anything is dragged. After the drop the archive
        # sits ON TOP of the application's icon, so a click there selects
        # the archive and photographs the wrong file's Info window — which
        # is exactly what the first System 7 run did.
        mac.click(*icons["app"])
        time.sleep(1.0)
        mac.command_key("i")
        time.sleep(4.0)
        shot(mac, "drop-3-getinfo.png")
        mac.command_key("w")                              # close the Info window
        time.sleep(2.0)

        arc = icons.get("archive")
        if arc is None:
            print("interactive: no `archive` icon coordinate for "
                  f"{args.system} — read it off drop-2-volume.png and add it "
                  "to FINDER_ICONS; doing Get Info only")
        else:
            # The control: does a drag reach the Finder at all? Move the
            # archive a little way into empty space and photograph that it
            # went there. Without this frame, an application that fails to
            # launch and a drag that never happened are the same picture.
            # Down, unless the window sits low enough that down is off the
            # screen — System 7 opens its volume window near the bottom edge.
            dy = -70 if arc[1] > 200 else 70
            mac.drag(arc[0], arc[1], arc[0], arc[1] + dy)
            time.sleep(2.0)
            shot(mac, "drop-4-control.png")

            # And the question: the same gesture, onto the application.
            mac.drag(arc[0], arc[1] + dy, *icons["app"])
            time.sleep(2.0)
            shot(mac, "drop-5-dropped.png")
            time.sleep(args.launch_wait)
            shot(mac, "drop-6-after-wait.png")

            # If it launched, it went straight to the DESTINATION dialog —
            # the Open dialog is what the dropped document replaces. Let it
            # extract, so the run says the application was handed the right
            # file and not merely woken up. Harmless when nothing launched:
            # Return goes to a Finder with nothing selected.
            mac.key("Return")
            time.sleep(2.0)
            elapsed = mac.settle(os.path.join(args.outdir, ".settle.png"),
                                 interval=5.0, quiet=EXTRACT_QUIET,
                                 timeout=args.complete_timeout)
            shot(mac, "drop-7-extracted.png")
            print(f"interactive: drop settled after "
                  f"~{elapsed if elapsed is None else round(elapsed)}s")

    finally:
        mac.close()
    return True


def stock_image(args):
    return os.path.join(R.VMAC_HOME, args.system)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixture", help="archive to put on the boot volume")
    ap.add_argument("-o", "--outdir", default="vmac-shots",
                    help="where to write the screenshots")
    ap.add_argument("--emu", default="mv-4M-1x",
                    help="emulator build under $UNC_VMAC_HOME. The default is "
                         "the 1x (authentic Mac Plus speed) one: at all-out "
                         "speed the extraction is over before the progress "
                         "dialog can be photographed, and Cmd-. has nothing "
                         "left to cancel")
    ap.add_argument("--boot-timeout", type=float, default=300.0,
                    help="seconds to allow for boot + launch before giving up")
    ap.add_argument("--extract-wait", type=float, default=15.0,
                    help="seconds to let the extraction run before Cmd-.")
    ap.add_argument("--complete-timeout", type=float, default=900.0,
                    help="seconds to allow the second run to finish (Mac Plus "
                         "speed: minutes, not seconds)")
    ap.add_argument("--launch-wait", type=float, default=25.0,
                    help="seconds to allow a Finder double-click to open an "
                         "application (Mac Plus speed)")
    ap.add_argument("--system", default="System6.hfv",
                    help="system image under $UNC_VMAC_HOME (System6.hfv or "
                         "Sys7.img)")
    ap.add_argument("--wd", action="store_true",
                    help="the working-directory phase: put the archive in a "
                         "SUBFOLDER, navigate into it with SFGetFile, and "
                         "check the extraction lands beside the archive rather "
                         "than at the volume root. On System 7 and later "
                         "SFReply.vRefNum is a working-directory reference, "
                         "and this is the only arrangement that can tell a "
                         "mishandled one from a correct one — at the volume "
                         "root the two are the same directory.")
    ap.add_argument("--dest", action="store_true",
                    help="the destination phase: switch the destination "
                         "dialog to a second volume and check on the HOST "
                         "that the files landed there and not beside the "
                         "archive. Asserts; does not just photograph.")
    ap.add_argument("--diskswap", action="store_true",
                    help="the disk-swap phase: hold the fixture's parts on "
                         "a floppy that is NOT in the machine, let the "
                         "application ask for one, and INSERT IT while the "
                         "alert is up. A decoy disk goes in first and must "
                         "not dismiss anything. Ends on the joined bytes.")
    ap.add_argument("--wrapped", action="store_true",
                    help="drive a set whose parts are each inside an "
                         "envelope (Archive.sit.1.hqx)")
    ap.add_argument("--chain", action="store_true",
                    help="drive a chained file (.sit.hqx) and check that "
                         "every envelope layer comes off")
    ap.add_argument("--named", choices=("zip", "split"),
                    help="drive a set placed by FILENAME: a spanned zip "
                         "or a plain .NNN split, through Standard File")
    ap.add_argument("--segments", action="store_true",
                    help="the segmented-archive phase: cut the fixture into "
                         "three parts, leave part 1 alone on the boot volume "
                         "and put the others on a second floppy, so the "
                         "'locate part N' alert has to come up. Offers the "
                         "WRONG part first. Ends by reading the joined file "
                         "back off the boot volume and comparing it to the "
                         "fixture, so this phase can fail on its own.")
    ap.add_argument("--password", action="store_true",
                    help="the password phase: extract an ENCRYPTED archive, "
                         "answer the dialog wrongly once and then correctly, "
                         "and check on the host that every entry came out. "
                         "Ignores the fixture argument: the archive is "
                         "generated, because nothing in the corpus is "
                         "encrypted.")
    ap.add_argument("--report", action="store_true",
                    help="the end-of-run report phase: extract a generated "
                         "archive whose names cannot be written as they "
                         "stand and one of whose entries is damaged, "
                         "photograph the report box, scroll it, save it as "
                         "a document, and read that document back off the "
                         "volume. Ignores the fixture argument.")
    ap.add_argument("--report-deep", action="store_true",
                    help="the report line for an entry nested deeper than "
                         "the engine carries folders: extract a generated "
                         "archive 30 levels deep, read the saved report back "
                         "off the volume, and check that the flattened "
                         "folder was NOT created. Ignores the fixture "
                         "argument; nothing in the corpus nests past 4.")
    ap.add_argument("--report-utf8", action="store_true",
                    help="the report line a generated archive cannot make: "
                         "a StuffIt 5 archive whose names are UTF-8 and "
                         "hold characters MacRoman has no byte for, so the "
                         "shell writes '_' and says so per component. Uses "
                         "fixtures/" + UTF8_REPORT_FIXTURE + " and ignores "
                         "the fixture argument.")
    ap.add_argument("--utf8-to-boot", action="store_true",
                    help="the CONTROL for --report-utf8's floppy: extract "
                         "onto the BOOT volume, the way that phase did "
                         "before the workaround, keep the image and say "
                         "which of this run's writes reached it. Settles "
                         "whether the report alone is lost or nothing the "
                         "guest wrote arrives at all.")
    ap.add_argument("--utf8-second", action="store_true",
                    help="the DISCRIMINATOR for --utf8-to-boot: save the "
                         "report a second time under its own name, so one "
                         "more catalog update follows the lost one, and say "
                         "which of the two entries reached the image. Tells "
                         "an ordering problem from an unflushed buffer "
                         "tail.")
    ap.add_argument("--drop-type", default="SIT!",
                    help="the four-character TYPE to give the archive in the "
                         "--drop phase. The Finder matches this against the "
                         "application's 'FREF' list, so it is half the "
                         "experiment; '????' is what a raw download carries "
                         "and matches no declared type.")
    ap.add_argument("--drop", action="store_true",
                    help="the Finder-drop phase: drag an archive onto the "
                         "application's icon and photograph what the FINDER "
                         "does, with a control drag first so a drag that was "
                         "never delivered cannot pass for a refusal. "
                         "Photographs Get Info in the same boot.")
    ap.add_argument("-D", dest="defines", action="append", default=[],
                    help="probe build switch (repeatable), e.g. -D UNC_AT_RESERVE")
    ap.add_argument("--e2e", action="store_true",
                    help="run the Finder end-to-end phase INSTEAD of the "
                         "cancel phases: launch by double-click, navigate "
                         "volumes with Drive, extract to completion, quit, "
                         "then double-click the application that was "
                         "extracted. Needs a fixture containing an APPL.")
    args = ap.parse_args()
    if args.utf8_to_boot and not args.report_utf8:
        ap.error("--utf8-to-boot is the control for --report-utf8 and means "
                 "nothing without it")
    if args.utf8_second and not args.utf8_to_boot:
        ap.error("--utf8-second discriminates between two readings of what "
                 "--utf8-to-boot measures, and needs it")

    calibrate(args.system)
    os.makedirs(args.outdir, exist_ok=True)
    appbin = build_interactive_app(tuple(args.defines))
    workdir = tempfile.mkdtemp(prefix="vmac-interactive-")
    bootimg = os.path.join(workdir, "boot-interactive.hfv")
    stock = os.path.join(R.VMAC_HOME, args.system)
    if not os.path.exists(stock):
        raise SystemExit(f"interactive: no {args.system} — run tools/vmac/setup.sh")

    def shot(mac, name):
        # e2e shots are upscaled: they are read for Finder icon positions and
        # for dialog text, not decoded, and a 512x342 1bpp screen is hard work
        # at native size.
        mac.shot(os.path.join(args.outdir, name),
                 scale="200%" if (args.e2e or args.drop) else None)

    if args.drop:
        try:
            ok = phase_drop(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.report:
        try:
            ok = phase_report(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.report_deep:
        try:
            ok = phase_report_deep(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.report_utf8:
        try:
            ok = phase_report_utf8(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.diskswap:
        try:
            ok = phase_diskswap(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.password:
        try:
            ok = phase_password(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.dest:
        try:
            ok = phase_dest(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.wrapped:
        try:
            ok = phase_wrapped(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.chain:
        try:
            ok = phase_chain(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.named:
        try:
            ok = phase_named(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.segments:
        try:
            ok = phase_segments(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.wd:
        try:
            ok = phase_wd(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0 if ok else 1

    if args.e2e:
        try:
            phase_e2e(args, appbin, workdir, shot)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
        return 0

    # The archive goes on the boot volume: the application extracts next to it,
    # so it must be writable, and SFGetFile opens on the boot volume.
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin, bootimg,
         "--data", f"{args.fixture}:archive.sit")

    # Phase 1: cancel part way through. Fresh boot, so the volume holds
    # nothing but the archive and anything visible afterwards was left by
    # this run.
    scratch = os.path.join(args.outdir, ".settle.png")
    mac = Mac(bootimg, args.emu, workdir)
    try:
        boot = mac.settle(scratch, interval=5.0, timeout=args.boot_timeout)
        if boot is None:
            raise SystemExit("interactive: the machine never settled — no SFGetFile")
        shot(mac, "1-launched.png")

        sf_to_volume_root(mac, args.system)  # System 7 opens in the System Folder
        mac.click(*SF_FIRST_ROW)            # select the archive
        mac.key("Return")                   # Open
        shot(mac, "1b-destination.png")     # "Extract the files into..."
        accept_destination(mac)             # Return: beside the archive
        time.sleep(args.extract_wait)
        shot(mac, "2-extracting.png")

        mac.click(*PROGRESS_CANCEL)         # Cancel button
        wait_for_alert(mac, scratch)
        shot(mac, "3-cancelled.png")

        mac.key("Return")                   # dismiss the alert
        time.sleep(2.0)
        shot(mac, "4-back.png")

        # Cmd-. is a separate route to the same cancel: it is caught by hand
        # in ProgressPump rather than by the Dialog Manager.
        mac.click(*SF_FIRST_ROW)
        mac.key("Return")
        accept_destination(mac)
        time.sleep(args.extract_wait)
        mac.command_key("period")
        wait_for_alert(mac, scratch)
        shot(mac, "6-cmd-period.png")
    finally:
        mac.close()

    # Phase 2: let it finish. A second boot rather than a second pass in the
    # same session, so the success alert is not confused by the half-extracted
    # output phase 1 left behind (which would also drag the name-collision
    # path in and make the screenshot mean two things at once).
    mac = Mac(bootimg, args.emu, workdir)
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit("interactive: second boot never settled")
        sf_to_volume_root(mac, args.system)
        mac.click(*SF_FIRST_ROW)
        mac.key("Return")
        accept_destination(mac)
        elapsed = mac.settle(scratch, interval=10.0, quiet=EXTRACT_QUIET,
                             timeout=args.complete_timeout)
        shot(mac, "5-complete.png")
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    # One assertion, on the volume phase 2 wrote to. The rest of this phase
    # is photographs, and a photograph of the wrong dialog is indistinguishable
    # from a photograph of the right one unless somebody looks: on 2026-08-09
    # this run reported "settled after ~134s" having spent every second of it
    # in a "Replace existing" alert, with nothing extracted at all. The names
    # cannot be argued with.
    try:
        want = expected_names(args.fixture, workdir)
        got = volume_names(os.path.join(workdir, "boot.hfv"))
        absent = sorted(n for n in want if n not in got)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if elapsed is None:
        print(f"interactive: still working after {args.complete_timeout:.0f}s")
    else:
        print(f"interactive: extraction settled after ~{elapsed:.0f}s "
              f"of emulated Mac Plus time (boot took ~{boot:.0f}s)")
    if absent:
        print("interactive: NOT on the boot volume after phase 2: "
              + ", ".join(CD.mac_path(n) for n in absent))
    print("interactive: phase 2 output " + ("INCOMPLETE" if absent else "COMPLETE"))
    print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
    print("Everything else here is judged by eye: this driver guarantees the")
    print("same clicks in the same order, and asserts only on those names.")
    return 1 if absent or not want else 0


if __name__ == "__main__":
    sys.exit(main())

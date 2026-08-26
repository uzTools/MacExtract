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
`--wd`, `--dest` and `--segments`. `--help` describes the last three.

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
import argparse, glob, os, shutil, signal, subprocess, sys, tempfile, time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402
from mkboot import LISTING_DATE                              # noqa: E402
import checkdisk as CD                                       # noqa: E402


def build_interactive_app():
    """Build the normal (non-autotest) application, returning its MacBinary."""
    bdir = os.path.join(R.REPO, "build", "mac-interactive")
    toolchain = os.environ.get("RETRO68", "/opt/Retro68-build/toolchain")
    cmakefile = os.path.join(toolchain, "m68k-apple-macos", "cmake",
                             "retro68.toolchain.cmake")
    if not os.path.exists(cmakefile):
        raise SystemExit(f"interactive: no Retro68 toolchain at {toolchain}")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("UNC_MAC_", "UNC_AT_"))}   # plain build
    subprocess.run(["cmake", "-B", bdir, "-S", os.path.join(R.REPO, "mac"),
                    f"-DCMAKE_TOOLCHAIN_FILE={cmakefile}",
                    "-DCMAKE_BUILD_TYPE=Release"],
                   check=True, capture_output=True, env=env)
    subprocess.run(["cmake", "--build", bdir, "--", "-j", str(os.cpu_count())],
                   check=True, capture_output=True, env=env)
    return os.path.join(bdir, "unclassic.bin")


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
SF_ROWS = {"System6.hfv": (150, 137), "Sys7.img": (150, 127)}

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
    row = SF_ROWS.get(system)
    if row is None:
        raise SystemExit(f"interactive: no Standard File geometry for {system} "
                         f"— boot it once, look at the first frame, and add "
                         f"its first row to SF_ROWS")
    SF_FIRST_ROW = SF_SUBFOLDER_ROW = row
    SF_SECOND_ROW = (row[0], row[1] + SF_ROW_HEIGHT)


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
FINDER_VOLUME_ICON = (480, 40)      # boot disk, top right of the desktop
# Fourth of the four items in the open volume window, whose order is
# System Folder, archive.sit, an empty folder mkboot.py cannot delete, then
# the application. Measured off e2e-2-volume.png.
FINDER_APP_ICON = (240, 110)
# The extracted application, sixth and last item once the run has finished
# (System Folder, archive.sit, that empty folder, unclassic, then the two
# entries of derived-ScrollbarPattern.sit). Measured off e2e-7; a different
# fixture puts it somewhere else.
FINDER_EXTRACTED_APPL = (367, 104)


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
# `mac/unclassic_mac.c`, this moves with it.
SFPUT_DRIVE = (337 + 30, 181 + 30)


def volume_names(img):
    """Every file on an HFS image, as checkdisk.py's component tuples.

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
        names = set(CD.walk(env))
        CD.hfs(env, "humount")
        return names
    finally:
        shutil.rmtree(home, ignore_errors=True)


def expected_names(fixture, workdir):
    """The names the Mac should have written, as component tuples.

    The same mapping checkdisk.py makes: extract with the CLI, drop the
    "._" sidecars (a resource fork is part of the file on a Mac), undo the
    engine's reversible '/'->':' swap and cap each component at 31
    characters as ComponentToStr63 does. The fixture is copied to
    `archive.sit` first because that is the name the Mac saw, and gzip/.Z
    derive an output name from the archive's.

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
    subprocess.run([CD.CLI, "x", "-nr", "--forks", "hidden", asmac, "-o", ref],
                   capture_output=True)
    want = set()
    for root, _dirs, files in os.walk(ref):
        for f in files:
            if f.startswith("._"):
                continue
            rel = os.path.relpath(os.path.join(root, f), ref)
            comps = [unicodedata.normalize("NFC", c) for c in rel.split(os.sep)]
            want.add(tuple(c.replace(":", "/")[:31] for c in comps))
    if not want:
        print(f"interactive: the CLI extracted nothing from {fixture} — "
              f"there is no output to look for")
    return want


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
        shot(mac, "wd-2-volume.png")                      # Archives + unclassic

        mac.click(*icons["app"], double=True)             # launch unclassic
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

        mac.click(*FINDER_APP_ICON, double=True)         # launch unclassic
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
# Skip and Cancel do: DLOG-style arithmetic off mac/unclassic.r, where the
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
            listing = CD.hfs(env, "hls", "-l").stdout.decode("mac_roman")
            print("interactive: not on the volume, which holds:\n" + listing)
        CD.hfs(env, "humount")
        return open(out, "rb").read() if got.returncode == 0 else None
    finally:
        shutil.rmtree(home, ignore_errors=True)


def build_named_set(kind, workdir, fixture):
    """A set whose parts are placed by NAME, and the one file it must
    produce. Both schemes are given ONE payload on purpose: the check at
    the end is a byte comparison, and one file can be compared without
    walking a tree off an HFS volume."""
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

    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    try:
        CD.hfs(env, "hmount", os.path.join(workdir, "boot.hfv"))
        listing = CD.hfs(env, "hdir", ":").stdout.decode("mac_roman")
        CD.hfs(env, "humount")
    finally:
        shutil.rmtree(home, ignore_errors=True)
    got = set()
    for line in listing.splitlines():
        m = LISTING_DATE.search(line)
        if not m:
            continue
        nm = m.group(1)
        if nm in ("System Folder", "Desktop", "unclassic") or \
                nm.startswith("StuffIt Expander") or nm in onvol:
            continue
        got.add(nm)

    ref = os.path.join(workdir, "_cli")
    os.makedirs(ref, exist_ok=True)
    R.sh(os.path.join(R.REPO, "build", "dev", "unclassic"), "x", "-o", ref,
         os.path.join(d, "Apart.sit.1.hqx"))
    want = set(os.listdir(ref))
    left = [g for g in got if g.startswith("unclassic part")]
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
    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    try:
        CD.hfs(env, "hmount", os.path.join(workdir, "boot.hfv"))
        listing = CD.hfs(env, "hdir", ":").stdout.decode("mac_roman")
        CD.hfs(env, "humount")
    finally:
        shutil.rmtree(home, ignore_errors=True)
    ignore = {"System Folder", "StuffIt Expander\u2122 4.0.1 Folder", "Desktop",
              "unclassic", onmac}
    got = set()
    for line in listing.splitlines():
        m = LISTING_DATE.search(line)
        if m and m.group(1) not in ignore and \
                not m.group(1).startswith("StuffIt Expander"):
            got.add(m.group(1))

    # What the Linux CLI makes of the same file, recursion and all.
    ref = os.path.join(workdir, "_cli")
    os.makedirs(ref, exist_ok=True)
    R.sh(os.path.join(R.REPO, "build", "dev", "unclassic"), "x", "-o", ref,
         args.fixture)
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
    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    try:
        CD.hfs(env, "hmount", os.path.join(workdir, "boot.hfv"))
        listing = CD.hfs(env, "hdir", ":").stdout.decode("mac_roman")
        CD.hfs(env, "humount")
    finally:
        shutil.rmtree(home, ignore_errors=True)
    onvol = {os.path.basename(p) for p in parts}
    got = set()
    for line in listing.splitlines():
        m = LISTING_DATE.search(line)
        if not m:
            continue
        nm = m.group(1)
        if nm in ("System Folder", "Desktop", "unclassic") or \
                nm.startswith("StuffIt Expander") or nm in onvol:
            continue
        got.add(nm)

    ref = os.path.join(workdir, "_cli")
    os.makedirs(ref, exist_ok=True)
    R.sh(os.path.join(R.REPO, "build", "dev", "unclassic"), "x", "-o", ref,
         parts[0])
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

    # The bytes, not the screenshot. Read the joined file back off the
    # volume the Mac actually wrote to — which is Mac()'s private COPY of
    # the boot image, not the image handed to it. Reading the template
    # instead reports "not found" for a run that worked perfectly, which
    # is how this was first written.
    written = os.path.join(workdir, "boot.hfv")
    out = os.path.join(workdir, "joined.bin")
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    verdict, listing = "NOT FOUND", ""
    try:
        subprocess.run(["hmount", written], check=True, capture_output=True,
                       env=env)
        got = subprocess.run(["hcopy", "-r", ":" + name.decode("mac_roman"), out],
                             capture_output=True, env=env)
        if got.returncode != 0:
            # Say what IS on the volume: "not found" on its own cannot
            # distinguish a wrong name from a failed extraction. Decoded
            # as MacRoman, not as text=True: the volume holds `StuffIt
            # Expander™ 4.0.1 Folder`, so a UTF-8 decode raises — and it
            # raises only on the path that runs when the run has ALREADY
            # failed, taking the diagnostic down with it.
            listing = subprocess.run(["hls", "-l"], capture_output=True,
                                     env=env).stdout.decode("mac_roman").strip()
        subprocess.run(["humount", written], capture_output=True, env=env)
        if got.returncode == 0 and os.path.exists(out):
            verdict = ("BYTE-EXACT" if open(out, "rb").read() == original
                       else "DIFFERS")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)

    print(f"interactive: joined file read back off the boot volume: {verdict} "
          f"({len(original)} B expected)")
    if listing:
        print("interactive: the volume holds:\n" + listing)
    if elapsed is not None:
        print(f"interactive: settled ~{elapsed:.0f}s after the part was given")
    return verdict == "BYTE-EXACT"


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
    ap.add_argument("--e2e", action="store_true",
                    help="run the Finder end-to-end phase INSTEAD of the "
                         "cancel phases: launch by double-click, navigate "
                         "volumes with Drive, extract to completion, quit, "
                         "then double-click the application that was "
                         "extracted. Needs a fixture containing an APPL.")
    args = ap.parse_args()

    calibrate(args.system)
    os.makedirs(args.outdir, exist_ok=True)
    appbin = build_interactive_app()
    workdir = tempfile.mkdtemp(prefix="vmac-interactive-")
    bootimg = os.path.join(workdir, "boot-interactive.hfv")
    stock = os.path.join(R.VMAC_HOME, args.system)
    if not os.path.exists(stock):
        raise SystemExit(f"interactive: no {args.system} — run tools/vmac/setup.sh")

    def shot(mac, name):
        # e2e shots are upscaled: they are read for Finder icon positions and
        # for dialog text, not decoded, and a 512x342 1bpp screen is hard work
        # at native size.
        mac.shot(os.path.join(args.outdir, name), scale="200%" if args.e2e else None)

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

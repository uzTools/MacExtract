#!/usr/bin/env python3
"""interactive.py — drive the INTERACTIVE Mac application under Mini vMac.

`run.py` replays fixtures through the `-DUNC_MAC_AUTOTEST` build, which has no
user interface at all: no SFGetFile, no progress dialog, no alerts. That build
proves the engine and the sink. It says nothing about the application a person
actually uses, and the whole of that surface went unverified when the sink was
rewritten to stream its writes.

This drives the real application the way a person would — clicking Open in
SFGetFile, watching the progress dialog, pressing Cmd-. — and captures a
screenshot at each step. **The screenshots are the result.** There is no bit
grid to decode here and no oracle to compare against; a human (or a model that
can see) looks at them and decides. That is exactly the manual checklist in
MANUAL_TESTS.md, with the tedious, error-prone driving automated so it can be
repeated identically.

    tools/vmac/interactive.py fixtures/derived-EmpireBuilderDemo.sit -o /tmp/shots

Steps captured, in order:

    1-launched.png    application is up, SFGetFile listing the archive
    2-extracting.png  progress dialog, part way through
    3-cancelled.png   the alert after Cmd-.
    4-back.png        back at SFGetFile, ready for another file
    5-complete.png    a second run allowed to finish: the success alert

Mini vMac maps the host Alt key to the Mac Command key; see command_key() for
why the chord is sent as an explicit hold rather than an xdotool chord.
"""
import argparse, os, shutil, signal, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402


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

    def __init__(self, bootimg, emudir, workdir):
        emu = os.path.join(R.VMAC_HOME, emudir, "minivmac")
        rom = os.path.join(R.VMAC_HOME, "vMac.ROM")
        if not os.path.exists(emu):
            raise SystemExit(f"interactive: no emulator at {emu} — run setup.sh")
        boot = os.path.join(workdir, "boot.hfv")
        shutil.copyfile(bootimg, boot)
        self.dpy = R.Display()
        self.proc = subprocess.Popen([emu, "-r", rom, boot],
                                     env=dict(os.environ, DISPLAY=self.dpy.name),
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     start_new_session=True)
        self.env = dict(os.environ, DISPLAY=self.dpy.name)
        self._origin = None

    def _xdo(self, *args):
        subprocess.run(["xdotool", *args], env=self.env, capture_output=True)

    def origin(self):
        """Top-left of the Mac screen within the X root, so Mac coordinates can
        be clicked directly. With no window manager the emulator lands wherever
        it likes, and hard-coding an offset silently clicks the desktop."""
        if self._origin is None:
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

    def shot(self, path):
        self.park()
        for _ in range(40):
            if self.dpy.screenshot(path):
                return
            time.sleep(0.5)
        raise SystemExit("interactive: could not screenshot the emulator")

    def close(self):
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        self.dpy.close()

    def settle(self, path, interval=10.0, timeout=900.0, stable=2):
        """Screenshot until the screen stops changing; return seconds waited.

        Used instead of a fixed sleep both for "has it finished booting" and
        for "has the extraction finished". At 1x the answer is minutes and
        varies with the archive, so a fixed wait is either wrong or wasteful.
        While work is in progress the progress dialog repaints its percentage,
        so consecutive shots differ; when the alert goes up the screen is
        static. Returns the elapsed time, which is a real Mac Plus figure."""
        started = time.time()
        prev, same = None, 0
        while time.time() - started < timeout:
            time.sleep(interval)
            self.shot(path)
            cur = open(path, "rb").read()
            same = same + 1 if cur == prev else 0
            prev = cur
            if same >= stable - 1:
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

# The progress dialog's Cancel button, measured off 2-extracting.png. Cancel
# by button and Cancel by Cmd-. are separate checklist items reaching the same
# code by different routes (Dialog Manager hit-testing vs. the keyDown check
# in ProgressPump), so both are exercised.
PROGRESS_CANCEL = (342, 138)


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
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    appbin = build_interactive_app()
    workdir = tempfile.mkdtemp(prefix="vmac-interactive-")
    bootimg = os.path.join(workdir, "boot-interactive.hfv")
    stock = os.path.join(R.VMAC_HOME, "System6.hfv")
    if not os.path.exists(stock):
        raise SystemExit("interactive: no System6.hfv — run tools/vmac/setup.sh")
    # The archive goes on the boot volume: the application extracts next to it,
    # so it must be writable, and SFGetFile opens on the boot volume.
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin, bootimg,
         "--data", f"{args.fixture}:archive.sit")

    def shot(mac, name):
        mac.shot(os.path.join(args.outdir, name))

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

        mac.click(*SF_FIRST_ROW)            # select the archive
        mac.key("Return")                   # Open -> extraction starts
        time.sleep(args.extract_wait)
        shot(mac, "2-extracting.png")

        mac.click(*PROGRESS_CANCEL)         # Cancel button
        time.sleep(3.0)
        shot(mac, "3-cancelled.png")

        mac.key("Return")                   # dismiss the alert
        time.sleep(2.0)
        shot(mac, "4-back.png")

        # Cmd-. is a separate route to the same cancel: it is caught by hand
        # in ProgressPump rather than by the Dialog Manager.
        mac.click(*SF_FIRST_ROW)
        mac.key("Return")
        time.sleep(args.extract_wait)
        mac.command_key("period")
        time.sleep(3.0)
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
        mac.click(*SF_FIRST_ROW)
        mac.key("Return")
        elapsed = mac.settle(scratch, interval=10.0, timeout=args.complete_timeout)
        shot(mac, "5-complete.png")
    finally:
        mac.close()
        shutil.rmtree(workdir, ignore_errors=True)
        if os.path.exists(scratch):
            os.remove(scratch)

    if elapsed is None:
        print(f"interactive: still working after {args.complete_timeout:.0f}s")
    else:
        print(f"interactive: extraction settled after ~{elapsed:.0f}s "
              f"of emulated Mac Plus time (boot took ~{boot:.0f}s)")
    print(f"interactive: screenshots in {args.outdir} — LOOK AT THEM.")
    print("Nothing here is self-checking: this driver only guarantees the same")
    print("clicks happen in the same order. Judging is the reader's job.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

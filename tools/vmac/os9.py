#!/usr/bin/env python3
"""os9.py — boot Mac OS 9 on emulated PowerPC with the application attached.

The Retro68 application is 68k-only and would run on a PowerPC Mac through the
68LC040 emulator built into Mac OS. That layer, and everything else above
System 6 — the WaitNextEvent branch, `SFReply.vRefNum` as a System 7+ working
directory reference, HFS+ names, the SIZE partition under a real Process
Manager — has never been exercised. This is the harness for exercising it.

    tools/vmac/os9.py --setup                 # fetch the Mac OS 9 disk image
    tools/vmac/os9.py fixtures/foo.sit -o shots/

It boots `qemu-system-ppc -M mac99,via=pmu` headless, attaches a second disk
built by mkapmdisk.py holding the application and one archive, and screenshots
through QEMU's own monitor (`screendump`) — no X server involved, unlike the
Mini vMac harness.

**STATUS: incomplete.** What is established, with screenshots:

  * Mac OS 9.2 boots to the Finder desktop under this configuration, in about
    four minutes of host time.
  * The transfer volume mounts and appears on the desktop, so the application
    and a test archive are reachable from inside Mac OS 9.

What is NOT done: opening the volume, launching the application and driving
its UI, which is where the actual verification would happen. Until that runs,
**nothing about the application on Mac OS 9 is verified** — see OPEN_ITEMS.md.
The Finder needs mouse work (double-click the volume, double-click the
application) and the icon positions in a freshly opened window are not known
in advance, so it wants the same
screenshot-look-adjust loop the System 6 driver went through.
"""
import argparse, os, re, shutil, socket, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402

QEMU_HOME = os.path.join(os.path.dirname(R.VMAC_HOME), "qemu-ppc")

# Desktop icon positions on the settled 1024x768 Mac OS 9 desktop, measured
# off desktop.png. Volumes stack down the right-hand edge in mount order: the
# boot disk ("untitled") first, then the transfer volume ("unclassic").
XFER_VOLUME_ICON = (974, 120)
# The application inside the transfer volume's window, once opened. Measured
# off volume.png — re-measure it there if the volume's contents change.
XFER_APP_ICON = (60, 100)
DISK = os.path.join(QEMU_HOME, "MacOS9.img")

# A pre-installed Mac OS 9.2 disk, Apple-partitioned, from the Internet
# Archive. Apple's copyright, so it is fetched and hashed like everything else
# under fixtures/ — never committed.
DISK_URL = "https://archive.org/download/mac-os9/MacOS9.img"
# archive.org publishes a SHA-1 per file; setup.sh hashes everything it fetches
# and this did not, which is how the local copy drifted from upstream without
# anyone noticing. See verify_disk().
DISK_SHA1 = "a6e39e049d99c56d0a2c08bf2631079f6f14bd56"


class Qemu:
    def __init__(self, disks, monitor):
        # -device usb-tablet is not cosmetic: it is the only reason clicking
        # can work at all. mac99's default pointer is an ADB mouse, which is
        # RELATIVE — `info mice` duly reports "QEMU HID Mouse" — so the
        # monitor's `mouse_move X Y` applies X and Y as a DELTA, and the
        # 0..32767 absolute coordinates this harness computes slam the pointer
        # into a screen corner. Every click then lands on bare desktop. Three
        # attempts to open a volume failed exactly that way, and the symptom
        # (the Finder comes forward, nothing opens) looks identical to a
        # mis-measured icon or a too-slow double click, which is what the first
        # two fixes chased. A USB tablet is an absolute device.
        argv = ["qemu-system-ppc", "-M", "mac99,via=pmu", "-m", "512",
                "-boot", "c", "-g", "1024x768x32", "-display", "none",
                "-device", "usb-tablet",
                "-monitor", f"unix:{monitor},server,nowait"]
        for i, d in enumerate(disks):
            argv += ["-drive", f"file={d},format=raw,media=disk,index={i}"]
        self.mon_path = monitor
        if os.path.exists(monitor):
            os.remove(monitor)
        self.proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     start_new_session=True)
        for _ in range(240):        # wait for the monitor to accept a client
            if os.path.exists(monitor):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(monitor)
                    s.close()
                    return
                except OSError:
                    pass
            if self.proc.poll() is not None:
                raise SystemExit("os9: qemu exited:\n" + self.proc.stdout.read())
            time.sleep(0.5)
        raise SystemExit("os9: qemu monitor never came up")

    def use_absolute_pointer(self):
        """Make the USB tablet the ACTIVE pointer.

        Adding -device usb-tablet is necessary and not sufficient. QEMU keeps
        the original relative ADB mouse selected, and `info mice` shows which
        with a leading '*':

            Mouse #3: QEMU HID Tablet (absolute)
          * Mouse #2: QEMU HID Mouse          <- still the active one

        `mouse_move` goes to the ACTIVE device, so without this the absolute
        coordinates are still applied as deltas and every click still lands in
        a corner. Verified against `info mice` rather than assumed, because the
        symptom of getting it wrong is indistinguishable from a bad icon
        coordinate — which cost three boots to work out the first time."""
        reply = self.ask("info mice")
        index = None
        for line in reply.splitlines():
            if "(absolute)" in line:
                m = re.search(r"Mouse #(\d+)", line)
                if m:
                    index = m.group(1)
                    break
        if index is None:
            raise SystemExit("os9: qemu reports no absolute pointing device; "
                             "clicking cannot work. Is -device usb-tablet "
                             "still on the command line?\n" + reply)
        self.mon(f"mouse_set {index}")
        after = self.ask("info mice")
        if not any(l.strip().startswith("*") and "(absolute)" in l
                   for l in after.splitlines()):
            raise SystemExit("os9: mouse_set did not take; the active pointer "
                             "is still relative:\n" + after)
        return index

    def ask(self, cmd, wait=1.2):
        """Send a monitor command and return its reply, stripped of the
        terminal escapes the HMP echoes back."""
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.mon_path)
        time.sleep(0.4)
        try:
            s.recv(65536)
        except OSError:
            pass
        s.sendall((cmd + "\n").encode())
        time.sleep(wait)
        try:
            out = s.recv(1 << 16).decode(errors="replace")
        except OSError:
            out = ""
        s.close()
        return re.sub(r"\x1b\[[0-9;]*[A-Za-z]|[\x00-\x08\x0b-\x1f]", "", out)

    def mon(self, cmd, wait=1.2):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.mon_path)
        time.sleep(0.3)
        try:
            s.recv(65536)
        except OSError:
            pass
        s.sendall((cmd + "\n").encode())
        time.sleep(wait)
        s.close()

    def shot(self, path):
        """QEMU writes PPM; convert so the result is viewable like the rest."""
        ppm = path + ".ppm"
        self.mon(f"screendump {ppm}")
        if not os.path.exists(ppm):
            return None
        subprocess.run(["convert", ppm, path], capture_output=True)
        os.remove(ppm)
        return path

    def click(self, x, y, double=False):
        """Click at 1024x768 screen coordinates. QEMU's absolute pointer uses
        a 0..32767 space on both axes regardless of the guest resolution.

        The button events go down ONE monitor connection in a single write.
        They used to be four separate mon() calls, and mon() sleeps 0.3 s
        before sending so the monitor's banner can arrive — which put roughly
        0.9 s between the two clicks of a "double click". The classic Mac
        double-click threshold is about half that, so the Finder saw two
        single clicks, the volume never opened, and the failure looked like a
        mis-measured icon coordinate rather than a broken primitive."""
        self.mon(f"mouse_move {int(x * 32767 / 1024)} {int(y * 32767 / 768)}", 0.5)
        # One connection, with deliberate gaps between the button events:
        # 60 ms down/up, 180 ms between clicks — inside the Mac's ~0.5 s
        # double-click threshold and above one 60 Hz input frame. This timing
        # was NOT what broke the Finder clicks (the pointer was in the wrong
        # place entirely; see usb-tablet above), but the original four separate
        # mon() calls really did put ~0.9 s between clicks, which would have
        # bitten the moment the pointer was fixed.
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.mon_path)
        time.sleep(0.3)
        try:
            s.recv(65536)
        except OSError:
            pass
        for i in range(2 if double else 1):
            if i:
                time.sleep(0.18)
            s.sendall(b"mouse_button 1\n")
            time.sleep(0.06)
            s.sendall(b"mouse_button 0\n")
            time.sleep(0.06)
        time.sleep(0.6)
        s.close()
        time.sleep(0.8)

    def settle(self, scratch, interval=20.0, timeout=1200.0, stable=2):
        """Screenshot until the screen stops changing; return seconds waited.

        Replaces a fixed sleep. The fixed wait was 260 s "because OS 9 takes
        about four minutes to reach the Finder here", which was true on the
        machine that measured it and false on a loaded one — the boot simply
        had not finished when the screenshot was taken, and the run produced
        nothing at all rather than saying why. Booting is exactly the kind of
        thing whose duration is a property of the host, not of the guest, so
        it should be waited for and not predicted."""
        started = time.time()
        prev, same = None, 0
        while time.time() - started < timeout:
            time.sleep(interval)
            if self.proc.poll() is not None:
                return None                       # qemu died; caller reports
            if not self.shot(scratch):
                continue
            cur = self._body(scratch)
            same = same + 1 if cur == prev else 0
            prev = cur
            if same >= stable - 1:
                return time.time() - started
        return None

    @staticmethod
    def _body(path):
        """The screen BELOW the menu bar, as raw pixels.

        Comparing whole frames does not work on Mac OS 9: the menu bar carries
        a clock, so two shots a minute apart are never byte-identical and a
        settled desktop never looks settled. The first version of settle() hung
        until its timeout on a machine that had in fact reached the Finder
        minutes earlier. Everything this harness cares about — volume icons,
        windows, dialogs — is below the menu bar."""
        out = subprocess.run(["convert", path, "-crop", "1024x748+0+20",
                              "+repage", "-depth", "8", "rgb:-"],
                             capture_output=True)
        return out.stdout

    def close(self):
        try:
            os.killpg(os.getpgid(self.proc.pid), 9)
        except (ProcessLookupError, PermissionError):
            pass


def sha1(path):
    import hashlib
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_disk(fatal=True):
    """Is the master image still the one upstream published?

    It matters more here than it looks. Mac OS 9 writes to its boot volume as a
    matter of course — Desktop DB, temporary items, the "unmounted cleanly"
    flag — so a single boot leaves the image different from what was fetched,
    and a QEMU run that is killed rather than shut down leaves it dirty. That
    is why nothing may boot this file directly; see boot_copy()."""
    got = sha1(DISK)
    if got == DISK_SHA1:
        return True
    msg = (f"os9: {DISK} does not match the published SHA-1\n"
           f"os9:   want {DISK_SHA1}\n"
           f"os9:   got  {got}\n"
           f"os9: it has been written to — re-fetch it with --setup --force")
    if fatal:
        raise SystemExit(msg)
    print(msg)
    return False


def boot_copy(workdir):
    """A throwaway copy of the master image to actually boot.

    tools/vmac/run.py has done this since M10 ("every run starts from a
    pristine image: System 6 writes to the boot volume as it goes"), and
    BLOCKERS.md records that repeated boot-and-kill cycles corrupt it. That
    lesson was never carried over here: os9.py booted the master in place, so
    every run quietly damaged the one artifact it depends on, and there was no
    hash to notice."""
    dst = os.path.join(workdir, "boot.img")
    print(f"os9: copying the master image to {dst} (2 GB; the master is never booted)")
    shutil.copyfile(DISK, dst)
    return dst


def setup(force=False):
    os.makedirs(QEMU_HOME, exist_ok=True)
    if os.path.exists(DISK) and not force:
        if verify_disk(fatal=False):
            print(f"have {DISK}")
            return
        raise SystemExit("os9: refusing to overwrite silently — pass --force")
    print(f"fetching {DISK_URL} (2 GB)")
    subprocess.run(["curl", "-fsSL", "-o", DISK + ".part", DISK_URL], check=True)
    got = sha1(DISK + ".part")
    if got != DISK_SHA1:
        raise SystemExit(f"os9: SHA-1 mismatch on the download: got {got}, "
                         f"want {DISK_SHA1} — check upstream by hand")
    os.rename(DISK + ".part", DISK)
    print(f"os9: ready — {DISK}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixture", nargs="?", help="archive to put on the transfer disk")
    ap.add_argument("--force", action="store_true",
                    help="with --setup, re-fetch even if a copy is present "
                         "(use when verify_disk() reports drift)")
    ap.add_argument("--setup", action="store_true", help="fetch the Mac OS 9 disk")
    ap.add_argument("-o", "--outdir", default="os9-shots")
    ap.add_argument("--launch", action="store_true",
                    help="after the desktop settles, open the transfer volume "
                         "and double-click the application. Coordinates are at "
                         "the top of this file and were measured off the "
                         "screenshots this mode writes")
    ap.add_argument("--launch-wait", type=float, default=120.0,
                    help="seconds to allow the application to open; the 68k "
                         "emulator makes this slower than a native launch")
    ap.add_argument("--boot-wait", type=float, default=1800.0,
                    help="host seconds to allow for the desktop to SETTLE (the "
                         "harness waits for the screen to stop changing rather "
                         "than sleeping a fixed time). Four minutes is the "
                         "best case on an idle machine; a loaded one takes "
                         "much longer, so this bound is generous on purpose")
    args = ap.parse_args()

    if args.setup:
        setup(args.force)
        return 0
    if not args.fixture:
        ap.error("give a fixture, or --setup")
    if not os.path.exists(DISK):
        raise SystemExit("os9: no Mac OS 9 disk — run tools/vmac/os9.py --setup")

    os.makedirs(args.outdir, exist_ok=True)
    sys.path.insert(0, HERE)
    from interactive import build_interactive_app
    appbin = build_interactive_app()

    xfer = os.path.join(args.outdir, "transfer.img")
    R.sh(sys.executable, os.path.join(HERE, "mkapmdisk.py"), DISK, xfer,
         "32", "unclassic",
         "--macbinary", f"{appbin}:unclassic",
         "--data", f"{args.fixture}:archive.sit")

    verify_disk()
    boot = boot_copy(args.outdir)
    q = Qemu([boot, xfer], os.path.join(args.outdir, "mon.sock"))
    try:
        print(f"os9: absolute pointer is mouse #{q.use_absolute_pointer()}")
        scratch = os.path.join(args.outdir, ".settle.png")
        waited = q.settle(scratch, timeout=args.boot_wait)
        if waited is None:
            raise SystemExit(
                f"os9: the screen never stopped changing within "
                f"{args.boot_wait:.0f}s, or qemu exited. On a loaded host this "
                f"boot takes considerably longer than the four minutes the "
                f"docstring quotes; raise --boot-wait rather than assuming the "
                f"guest is broken.")
        print(f"os9: desktop settled after ~{waited:.0f}s")
        print(q.shot(os.path.join(args.outdir, "desktop.png")))

        if args.launch:
            # Open the transfer volume and launch the application from it.
            # There is no way to avoid the Finder here: the boot volume is
            # HFS+ inside an HFS wrapper and nothing in this environment can
            # write HFS+, so the application cannot be placed in Startup
            # Items offline. See BLOCKERS.md.
            q.click(*XFER_VOLUME_ICON, double=True)
            time.sleep(20)
            print(q.shot(os.path.join(args.outdir, "volume.png")))
            q.click(*XFER_APP_ICON, double=True)
            time.sleep(args.launch_wait)
            print(q.shot(os.path.join(args.outdir, "launched.png")))
            print("os9: launched.png is the result. SFGetFile on screen means "
                  "the 68k binary runs under the 68LC040 emulator; anything "
                  "else — a crash dialog, an unchanged window — is the "
                  "finding.")
        if os.path.exists(scratch):
            os.remove(scratch)
    finally:
        q.close()
    print("os9: the transfer volume should be on the desktop. Driving the "
          "Finder from here is not implemented — see this file's docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

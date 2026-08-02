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
import argparse, os, shutil, socket, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402

QEMU_HOME = os.path.join(os.path.dirname(R.VMAC_HOME), "qemu-ppc")
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
        argv = ["qemu-system-ppc", "-M", "mac99,via=pmu", "-m", "512",
                "-boot", "c", "-g", "1024x768x32", "-display", "none",
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
        a 0..32767 space on both axes regardless of the guest resolution."""
        self.mon(f"mouse_move {int(x * 32767 / 1024)} {int(y * 32767 / 768)}", 0.5)
        for _ in range(2 if double else 1):
            self.mon("mouse_button 1", 0.15)
            self.mon("mouse_button 0", 0.15)
        time.sleep(0.8)

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
    ap.add_argument("--boot-wait", type=float, default=260.0,
                    help="host seconds before the first screenshot; OS 9 takes "
                         "about four minutes to reach the Finder here")
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
        time.sleep(args.boot_wait)
        print(q.shot(os.path.join(args.outdir, "desktop.png")))
    finally:
        q.close()
    print("os9: the transfer volume should be on the desktop. Driving the "
          "Finder from here is not implemented — see this file's docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

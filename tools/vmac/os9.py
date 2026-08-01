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
import argparse, os, socket, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402

QEMU_HOME = os.path.join(os.path.dirname(R.VMAC_HOME), "qemu-ppc")
DISK = os.path.join(QEMU_HOME, "MacOS9.img")

# A pre-installed Mac OS 9.2 disk, Apple-partitioned, from the Internet
# Archive. Apple's copyright, so it is fetched and hashed like everything else
# under fixtures/ — never committed.
DISK_URL = "https://archive.org/download/mac-os9/MacOS9.img"


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


def setup():
    os.makedirs(QEMU_HOME, exist_ok=True)
    if os.path.exists(DISK):
        print(f"have {DISK}")
        return
    print(f"fetching {DISK_URL} (2 GB)")
    subprocess.run(["curl", "-fsSL", "-o", DISK + ".part", DISK_URL], check=True)
    os.rename(DISK + ".part", DISK)
    print(f"os9: ready — {DISK}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixture", nargs="?", help="archive to put on the transfer disk")
    ap.add_argument("--setup", action="store_true", help="fetch the Mac OS 9 disk")
    ap.add_argument("-o", "--outdir", default="os9-shots")
    ap.add_argument("--boot-wait", type=float, default=260.0,
                    help="host seconds before the first screenshot; OS 9 takes "
                         "about four minutes to reach the Finder here")
    args = ap.parse_args()

    if args.setup:
        setup()
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

    q = Qemu([DISK, xfer], os.path.join(args.outdir, "mon.sock"))
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

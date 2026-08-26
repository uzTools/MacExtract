#!/usr/bin/env python3
"""mountcheck.py <image.dsk>... — does this disk image mount on a real Mac?

Boots the stock System 6.0.8 image to the Finder with the given images
attached and photographs the desktop. A volume that mounts appears as an icon
down the right-hand edge; one that does not, does not — and the difference is
the whole point, because hfsutils will happily read an image that classic Mac
OS refuses (`tools/vmac/mkapmdisk.py` learned that the hard way on OS 9).

    tools/vmac/mountcheck.py dist/MacExtract.dsk -o /tmp/shots

This is what backs the claim that the bootstrap distribution's 800K image is
usable: `dist/MacExtract.dsk` has to mount on a machine that has no unarchiver
and no way to get one, or the distribution does not solve the problem it
exists for.

Not self-checking: the screenshot is the result.
"""
import argparse, os, shutil, signal, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402


def open_volume(dpy, args):
    """Double-click a mounted volume and photograph the window it opens.

    The offset is QUERIED, never assumed: with no window manager the
    emulator lands wherever it likes inside the 800x600 root, and a
    hard-coded origin puts every click on the desktop instead — which
    looks like "the Finder ignored the double-click" rather than like a
    miss (interactive.py, `origin`)."""
    env = dict(os.environ, DISPLAY=dpy.name)
    win = dpy.window()
    if not win:
        raise SystemExit("mountcheck: emulator window never appeared")
    out = subprocess.run(["xdotool", "getwindowgeometry", "--shell", win],
                         env=env, capture_output=True, text=True).stdout
    g = dict(l.split("=", 1) for l in out.strip().splitlines())
    mx, my = (int(v) for v in args.open_at.split(","))
    subprocess.run(["xdotool", "mousemove",
                    str(int(g["X"]) + mx), str(int(g["Y"]) + my)],
                   env=env, capture_output=True)
    time.sleep(0.5)
    subprocess.run(["xdotool", "click", "--repeat", "2", "--delay", "80", "1"],
                   env=env, capture_output=True)
    time.sleep(6.0)                     # the Finder reads the disk's catalog
    subprocess.run(["xdotool", "mousemove", "790", "590"],
                   env=env, capture_output=True)
    time.sleep(1.0)
    png = os.path.join(args.outdir, "opened.png")
    if not dpy.screenshot(png):
        raise SystemExit("mountcheck: could not screenshot the opened volume")
    subprocess.run(["convert", png, "-scale", "200%", png],
                   check=True, capture_output=True)
    return png


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="*", help="disk images to attach")
    ap.add_argument("-o", "--outdir", default="vmac-shots")
    ap.add_argument("--emu", default="mv-4M", help="emulator build to boot")
    ap.add_argument("--boot", default="System6.hfv",
                    help="boot image under $UNC_VMAC_HOME (default the stock "
                         "System 6.0.8). Point it at another system to check "
                         "that the system itself boots on this machine.")
    ap.add_argument("--settle", type=float, default=40.0,
                    help="seconds to allow for boot and for the Finder to "
                         "mount everything")
    ap.add_argument("--open", action="store_true",
                    help="also double-click the first mounted volume and "
                         "photograph the window it opens, as opened.png. What "
                         "is IN the download, not just that it mounted. The "
                         "icons come out unobstructed here because the volume "
                         "holds one item; on a boot volume the Finder paints "
                         "neighbouring labels over each other (this "
                         "directory's README, under `--e2e`). "
                         "docs/screens/0-icon.png comes from this.")
    ap.add_argument("--open-at", default="472,112", metavar="X,Y",
                    help="Mac-screen coordinates of that volume's icon "
                         "(default the slot directly under the boot disk)")
    args = ap.parse_args()

    stock = os.path.join(R.VMAC_HOME, args.boot)
    rom = os.path.join(R.VMAC_HOME, "vMac.ROM")
    emu = os.path.join(R.VMAC_HOME, args.emu, "minivmac")
    for p in (stock, rom, emu):
        if not os.path.exists(p):
            raise SystemExit(f"mountcheck: missing {p} — run tools/vmac/setup.sh")
    os.makedirs(args.outdir, exist_ok=True)

    work = tempfile.mkdtemp(prefix="mountcheck-")
    try:
        # Copies, not the originals: System 6 writes to every volume it
        # mounts (the Desktop file), and a distribution artifact must come
        # out of this check exactly as it went in.
        boot = os.path.join(work, "boot.hfv")
        shutil.copyfile(stock, boot)
        attached = []
        for img in args.images:
            dst = os.path.join(work, os.path.basename(img))
            shutil.copyfile(img, dst)
            attached.append(dst)

        dpy = R.Display()
        proc = subprocess.Popen([emu, "-r", rom, boot, *attached],
                                env=dict(os.environ, DISPLAY=dpy.name),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                start_new_session=True)
        try:
            time.sleep(args.settle)
            subprocess.run(["xdotool", "mousemove", "790", "590"],
                           env=dict(os.environ, DISPLAY=dpy.name),
                           capture_output=True)
            png = os.path.join(args.outdir, "mounted.png")
            for _ in range(60):
                if dpy.screenshot(png):
                    break
                time.sleep(0.5)
            else:
                raise SystemExit("mountcheck: could not screenshot the emulator")
            subprocess.run(["convert", png, "-scale", "200%", png],
                           check=True, capture_output=True)
            print(f"mountcheck: {png} — look for one volume icon per image, "
                  f"below the boot disk")
            if args.open:
                print(f"mountcheck: {open_volume(dpy, args)} — the volume's "
                      f"own window")
        finally:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            dpy.close()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

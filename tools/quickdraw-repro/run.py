#!/usr/bin/env python3
"""run.py — drive qd_repro on an emulated Mac Plus and photograph the result.

Answers one question: does QuickDraw really bomb after the File Manager has
run on System 6.0.8, as BLOCKERS.md claimed? The program writes its log to the
framebuffer with its own 5x7 font, so the log survives QuickDraw failing, and
the top eight scan lines carry one marker square per completed probe — out of
reach of System 6's centred system-error dialog, so a bomb still says where.

    tools/quickdraw-repro/run.py                  # every variant, both shells
    tools/quickdraw-repro/run.py --inspect        # boot to the Finder, look

The matrix, all on the same emulator, ROM and System image the fixture replays
use (tools/vmac/setup.sh):

    startup   default | no-maxapplzone | no-moremasters
    shell     the application itself (as tools/vmac/run.py installs it) |
              the Finder, with the application double-clicked like any other
    memory    4 MB | 1 MB

The screenshots are the primary result — saved 3x upscaled, so the 5x7 log is
comfortable to read and a bomb or a Sad Mac is unmistakable. They are also
decoded back to text and checked (decode_log.py), so a sweep gives a verdict
without anyone having to squint at twelve pictures.
"""
import argparse, os, shutil, signal, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
# Order matters: this directory and tools/vmac BOTH contain a run.py, and a
# script's own directory is already on sys.path, so tools/vmac has to come
# first or `import run` re-imports this file under a second name.
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools", "vmac"))
import decode_log                                            # noqa: E402
import run as R                                              # noqa: E402

APP = "qd_repro"

# Finder coordinates, in Mac screen pixels, measured off --inspect screenshots.
# They are stable because the boot image is rebuilt identically every run, but
# they are the first thing to re-measure if the Finder mode stops working.
VOLUME_ICON = (480, 40)       # the boot disk, top right of the desktop
APP_ICON = (112, 107)         # qd_repro in the freshly opened volume window,
                              # second of the three items the stripped volume
                              # holds (System Folder, qd_repro, and one empty
                              # folder mkboot.py cannot delete — see rmtree)

VARIANTS = {
    "default": {},
    "no-maxapplzone": {"QR_NO_MAXAPPLZONE": "1"},
    "no-moremasters": {"QR_NO_MOREMASTERS": "1"},
}


def build(variant):
    """Build one variant, returning its MacBinary. Each gets its own build
    directory: CMake reads the switches from the environment at CONFIGURE
    time, so a shared directory would keep the first variant for ever."""
    bdir = os.path.join(HERE, "build", variant)
    toolchain = os.environ.get("RETRO68", "/opt/Retro68-build/toolchain")
    cmakefile = os.path.join(toolchain, "m68k-apple-macos", "cmake",
                             "retro68.toolchain.cmake")
    if not os.path.exists(cmakefile):
        raise SystemExit(f"qd_repro: no Retro68 toolchain at {toolchain}")
    env = {k: v for k, v in os.environ.items() if not k.startswith("QR_")}
    env.update(VARIANTS[variant])
    subprocess.run(["cmake", "-B", bdir, "-S", HERE,
                    f"-DCMAKE_TOOLCHAIN_FILE={cmakefile}",
                    "-DCMAKE_BUILD_TYPE=Release"],
                   check=True, capture_output=True, env=env)
    subprocess.run(["cmake", "--build", bdir, "--", "-j", str(os.cpu_count())],
                   check=True, capture_output=True, env=env)
    return os.path.join(bdir, f"{APP}.bin")


def make_boot(appbin, dest, finder):
    stock = os.path.join(R.VMAC_HOME, "System6.hfv")
    if not os.path.exists(stock):
        raise SystemExit("qd_repro: no System6.hfv — run tools/vmac/setup.sh")
    argv = [sys.executable, os.path.join(REPO, "tools", "vmac", "mkboot.py"),
            stock, appbin, dest, "--app-name", APP]
    if finder:
        argv.append("--finder")
    R.sh(*argv)


class Mac:
    """A booted Mini vMac. Same arrangement as tools/vmac/interactive.py: no
    window manager, so input focus has to be set by hand, and the host pointer
    is parked off-screen before every screenshot."""

    def __init__(self, bootimg, emudir, workdir):
        emu = os.path.join(R.VMAC_HOME, emudir, "minivmac")
        rom = os.path.join(R.VMAC_HOME, "vMac.ROM")
        if not os.path.exists(emu):
            raise SystemExit(f"qd_repro: no emulator at {emu} — run setup.sh")
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
        if self._origin is None:
            win = self.dpy.window()
            if not win:
                raise SystemExit("qd_repro: emulator window never appeared")
            out = subprocess.run(["xdotool", "getwindowgeometry", "--shell", win],
                                 env=self.env, capture_output=True,
                                 text=True).stdout
            g = dict(l.split("=", 1) for l in out.strip().splitlines())
            self._origin = (int(g["X"]), int(g["Y"]))
            self._xdo("windowfocus", "--sync", win)
        return self._origin

    def click(self, x, y, double=False):
        ox, oy = self.origin()
        self._xdo("mousemove", str(ox + x), str(oy + y))
        time.sleep(0.4)
        self._xdo("click", "--repeat", "2" if double else "1", "--delay", "60", "1")
        time.sleep(0.6)

    def shot(self, path, scale="300%"):
        self._xdo("mousemove", "790", "590")     # park off the Mac screen
        time.sleep(0.3)
        for _ in range(60):
            if self.dpy.screenshot(path):
                subprocess.run(["convert", path, "-scale", scale, path],
                               check=True, capture_output=True)
                return
            time.sleep(0.5)
        raise SystemExit("qd_repro: could not screenshot the emulator")

    def close(self):
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        self.dpy.close()


def one(variant, finder, mem, outdir, settle, inspect=False):
    tag = f"{variant}-{'finder' if finder else 'shell'}-{mem}"
    workdir = tempfile.mkdtemp(prefix="qdrepro-")
    # Mac() copies its own pristine boot.hfv from this one for every launch,
    # so the two names must differ.
    bootimg = os.path.join(workdir, "boot-master.hfv")
    try:
        make_boot(build(variant), bootimg, finder)
        mac = Mac(bootimg, f"mv-{mem}", workdir)
        try:
            time.sleep(settle)
            if finder:
                # Inspect shots go in a subdirectory: outdir holds one PNG per
                # configuration and nothing else, so `decode_log.py outdir/*`
                # is always exactly the sweep.
                insp = os.path.join(outdir, "inspect")
                if inspect:
                    os.makedirs(insp, exist_ok=True)
                    mac.shot(os.path.join(insp, f"{tag}-0-desktop.png"))
                mac.click(*VOLUME_ICON, double=True)     # open the boot volume
                time.sleep(3.0)
                if inspect:
                    mac.shot(os.path.join(insp, f"{tag}-1-window.png"))
                mac.click(*APP_ICON, double=True)        # launch the app
                time.sleep(settle)
            png = os.path.join(outdir, f"{tag}.png")
            mac.shot(png)
            markers, lines = decode_log.decode(png)
            why = decode_log.verdict(markers, lines)
            print(f"{'PASS' if not why else 'FAIL'}  {tag:28s} "
                  f"markers={markers}/{decode_log.MARKERS_EXPECTED}  {png}",
                  flush=True)
            for line in lines:
                print("      " + line)
            for w in why:
                print("      !! " + w)
            return not why
        finally:
            mac.close()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--outdir", default="qd-repro-shots")
    ap.add_argument("--variant", action="append", choices=sorted(VARIANTS),
                    help="restrict to one startup variant (repeatable)")
    ap.add_argument("--mem", action="append", choices=("4M", "1M"),
                    help="restrict to one memory size (repeatable)")
    ap.add_argument("--shell", action="append", choices=("app", "finder"),
                    help="restrict to one boot shell (repeatable)")
    ap.add_argument("--settle", type=float, default=25.0,
                    help="seconds to let the machine boot / the app run")
    ap.add_argument("--inspect", action="store_true",
                    help="in Finder mode, also photograph the desktop and the "
                         "open volume window — how the click coordinates at "
                         "the top of this file were measured")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    runs = []
    for variant in args.variant or sorted(VARIANTS):
        for shell in args.shell or ("app", "finder"):
            for mem in args.mem or ("4M", "1M"):
                runs.append(one(variant, shell == "finder", mem, args.outdir,
                                args.settle, args.inspect))
    npass = sum(runs)
    print(f"\n{npass}/{len(runs)} PASS — screenshots in {args.outdir}")
    return 0 if npass == len(runs) else 1


if __name__ == "__main__":
    sys.exit(main())

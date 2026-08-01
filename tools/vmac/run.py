#!/usr/bin/env python3
"""run.py — replay fixtures through the Mac shell on an emulated Mac Plus.

For each fixture this builds three disk images, boots a stripped System 6.0.8
straight into the UNC_MAC_AUTOTEST build of the Mac application (no Finder, no
mouse automation — see mkboot.py), waits for the app to paint its result grid
on the framebuffer, screenshots it, and cross-checks the decoded aggregate
against the same engine's Linux output (tools/vmac_check.py).

    In        1440 KB floppy holding the fixture, named "archive.sit"
              (the autotest build opens exactly that name)
    Out       1440 KB empty floppy, the extraction target
    boot      the System 6.0.8 hard disk

Prerequisites: tools/vmac/setup.sh (once), Xvfb, ImageMagick, hfsutils.

    tools/vmac/run.py fixtures/adobenumbers.sit
    tools/vmac/run.py --mem 1M --json out.json fixtures/*.sit

WALL CLOCK IS NOT MAC PLUS TIME: the emulator is built "all out", i.e. as fast
as the host allows, so --timeout bounds host seconds and says nothing about how
long a real 7 MHz 68000 would take. Correctness results are speed-independent;
timing claims must not be drawn from this harness.
"""
import argparse, json, os, shutil, signal, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
from decode_grid import decode                                # noqa: E402

# Deliberately NOT under build/: `make clean` removes that whole tree, which
# would silently throw away ~80 MB of downloads and both emulator builds.
DEFAULT_VMAC_HOME = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "unclassic", "vmac")
VMAC_HOME = os.environ.get("UNC_VMAC_HOME", DEFAULT_VMAC_HOME)
# Mini vMac's X window is always titled "minivmac", whatever -n the build used,
# and is exactly the 512x342 Mac screen with no border.
EMU_WINDOW_NAME = "minivmac"
FLOPPY_KB = 1440           # a real 1.44 MB floppy; Mini vMac mounts it as one
ARCHIVE_NAME = "archive.sit"

# Non-result statuses the app can paint in the grid's `ret` slot. Kept in step
# with the kAt* codes in mac/unclassic_mac.c.
AT_RUNNING = -1000         # alive, still working — keep waiting
UNC_ERR_ABORTED = -8       # include/unclassic.h
AT_STATUS = {-1000: "app alive, extraction not finished",
             -1001: 'no volume named "In" mounted (bad disk set)',
             -1002: 'no volume named "Out" mounted (bad disk set)'}


def signed32(v):
    return v - (1 << 32) if v >= (1 << 31) else v


def sh(*argv, **kw):
    return subprocess.run(argv, check=True, capture_output=True, text=True,
                          errors="surrogateescape", **kw)


def make_floppy(path, volname, payload=None, size_kb=FLOPPY_KB):
    """Create a fresh HFS floppy image, optionally with one data-fork file."""
    with open(path, "wb") as f:
        f.truncate(size_kb * 1024)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        subprocess.run(["hformat", "-l", volname, path],
                       check=True, capture_output=True, env=env)
        if payload:
            subprocess.run(["hmount", path], check=True, capture_output=True, env=env)
            # -r: raw copy, data fork only. The archive is a plain byte stream;
            # its type/creator are irrelevant because the app opens it by name.
            subprocess.run(["hcopy", "-r", payload, f"{volname}:{ARCHIVE_NAME}"],
                           check=True, capture_output=True, env=env)
            subprocess.run(["humount", path], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


def build_autotest_app(defines=()):
    """Build the UNC_MAC_AUTOTEST application, returning its MacBinary path.

    `defines` are extra UNC_* build switches (mac/CMakeLists.txt turns each
    into a -D). Each combination gets its own build directory, because CMake
    reads these from the environment at CONFIGURE time — reusing one directory
    would silently keep the first combination for ever."""
    tag = "-".join(["autotest"] + sorted(d.lower() for d in defines))
    bdir = os.path.join(REPO, "build", "mac-" + tag)
    env = dict(os.environ, UNC_MAC_AUTOTEST="1")
    for d in defines:
        env[d] = "1"
    toolchain = os.environ.get("RETRO68", "/opt/Retro68-build/toolchain")
    cmakefile = os.path.join(toolchain, "m68k-apple-macos", "cmake",
                             "retro68.toolchain.cmake")
    if not os.path.exists(cmakefile):
        raise SystemExit(f"run: no Retro68 toolchain at {toolchain} "
                         f"(set RETRO68)")
    subprocess.run(["cmake", "-B", bdir, "-S", os.path.join(REPO, "mac"),
                    f"-DCMAKE_TOOLCHAIN_FILE={cmakefile}",
                    "-DCMAKE_BUILD_TYPE=Release"],
                   check=True, capture_output=True, env=env)
    subprocess.run(["cmake", "--build", bdir, "--", "-j", str(os.cpu_count())],
                   check=True, capture_output=True, env=env)
    return os.path.join(bdir, "unclassic.bin")


def build_boot_image(appbin, dest, system="System6.hfv"):
    stock = os.path.join(VMAC_HOME, system)
    if not os.path.exists(stock):
        raise SystemExit(f"run: no {system} — run tools/vmac/setup.sh first")
    sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin, dest)


class Display:
    """A private Xvfb. Each run gets its own so runs cannot see, or steal
    input focus from, each other."""

    def __init__(self):
        self._win = None
        for n in range(90, 200):
            if os.path.exists(f"/tmp/.X{n}-lock"):
                continue
            self.num = n
            # Depth 24: Mini vMac's X11 glue picks a visual it can XPutImage
            # into, and on an 8-bit Xvfb the very first PutImage dies with
            # BadMatch, taking the emulator with it a few seconds after boot.
            self.proc = subprocess.Popen(
                ["Xvfb", f":{n}", "-screen", "0", "800x600x24", "-nolisten", "tcp"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(200):                    # wait for it to accept clients
                time.sleep(0.05)
                if subprocess.run(["xdotool", "getdisplaygeometry"],
                                  env=dict(os.environ, DISPLAY=f":{n}"),
                                  capture_output=True).returncode == 0:
                    return
            self.close()
        raise SystemExit("run: no free X display")

    @property
    def name(self):
        return f":{self.num}"

    def window(self):
        """X id of the emulator window, or None if it is not up yet.

        Capturing the root window instead would work only by luck: with no
        window manager the emulator lands at an arbitrary offset inside the
        800x600 root, and decode_grid.py seeds its search for the calibration
        squares at Mac coordinates with only +-16 px of slack, so an offset
        screenshot decodes as "no grid at all"."""
        if self._win:
            return self._win
        r = subprocess.run(["xdotool", "search", "--name", EMU_WINDOW_NAME],
                           env=dict(os.environ, DISPLAY=self.name),
                           capture_output=True, text=True)
        ids = r.stdout.split()
        self._win = ids[-1] if ids else None
        return self._win

    def screenshot(self, path):
        """Capture the emulator window alone; returns False until it exists."""
        win = self.window()
        if not win:
            return False
        subprocess.run(["import", "-display", self.name, "-window", win,
                        "-silent", path], check=True, capture_output=True)
        return True

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def run_one(fixture, mem, timeout, poll, workdir, bootimg, keep_png=None,
            emu_dir=None):
    """Boot the Mac on one fixture.

    Returns (values or None, seconds, png, emulator-exited). The last one
    matters: a run that ends because the EMULATOR went away is not the same
    as one that ran out of time, and reporting both as "nothing decodable
    within <timeout>s" sent one reader looking for a Mac-side bug over what
    was a five-second host-side flake."""
    emu = os.path.join(VMAC_HOME, emu_dir or f"mv-{mem}", "minivmac")
    rom = os.path.join(VMAC_HOME, "vMac.ROM")
    if not os.path.exists(emu):
        raise SystemExit(f"run: no emulator at {emu} — run tools/vmac/setup.sh")

    boot = os.path.join(workdir, "boot.hfv")
    indsk = os.path.join(workdir, "in.dsk")
    outdsk = os.path.join(workdir, "out.dsk")
    png = os.path.join(workdir, "screen.png")
    shutil.copyfile(bootimg, boot)          # every run starts from a pristine
    make_floppy(indsk, "In", payload=fixture)   # image: System 6 writes to the
    make_floppy(outdsk, "Out")                  # boot volume as it goes

    dpy = Display()
    started = time.time()
    vals = None
    died = False
    # When the app first paints ANY grid it is alive and has not started work
    # (it paints kAtRunning before touching a disk). The gap between that and
    # the final grid is the extraction alone, with the boot excluded — which
    # is the only number worth quoting on a 1x machine.
    t_alive = None
    try:
        # start_new_session: the emulator must not share our process group, or
        # a stray signal to the group takes it down mid-write.
        proc = subprocess.Popen([emu, "-r", rom, boot, indsk, outdsk],
                                env=dict(os.environ, DISPLAY=dpy.name),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                start_new_session=True)
        # Park the host pointer away from the result grid. Mini vMac drives the
        # Mac cursor from it, and the cursor's saved background can stamp the
        # desktop pattern back over cells the app has already painted.
        subprocess.run(["xdotool", "mousemove", "780", "580"],
                       env=dict(os.environ, DISPLAY=dpy.name),
                       capture_output=True)
        deadline = started + timeout
        while time.time() < deadline:
            time.sleep(poll)
            if proc.poll() is not None:
                died = True
                break                        # emulator died; take a last look
            if not dpy.screenshot(png):
                continue                     # emulator window not mapped yet
            got = decode(png)
            if got is not None:
                if t_alive is None:
                    t_alive = time.time()
                # A grid whose ret slot says "running" means the app is up and
                # the extraction is simply not done — keep waiting, but
                # remember it so a timeout can say "alive but slow" instead of
                # the far vaguer "no grid".
                vals = got
                if signed32(got[1]) != AT_RUNNING:
                    break
    finally:
        elapsed = time.time() - started
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        if keep_png and os.path.exists(png):
            shutil.copyfile(png, keep_png)
        dpy.close()
    boot = (t_alive - started) if t_alive else None
    extract = (time.time() - t_alive) if t_alive else None
    return vals, elapsed, png, died, boot, extract


def check_cancel(vals):
    """Verdict for a UNC_AT_CANCEL run.

    The application aborts once one entry has completed, so the cancel lands
    inside a later entry. The question is whether that entry left anything on
    the volume, and the grid answers it directly: files actually present must
    equal the entries that completed. `dirs` guards the count — the on-Mac
    walk is one level deep, so anything but a flat archive makes it partial."""
    completed, ret, files, dirs = vals[0], signed32(vals[1]), vals[2], vals[3]
    if dirs:
        return None, (f"archive is not flat ({dirs} folder(s) at the root) — "
                      f"the file count is partial, pick a flat fixture")
    if ret != UNC_ERR_ABORTED:
        return False, (f"expected UNC_ERR_ABORTED ({UNC_ERR_ABORTED}), "
                       f"got {ret} — the run did not actually cancel")
    if completed < 1:
        return False, ("cancelled before any entry completed — nothing was "
                       "proven; use an archive with more entries")
    ok = files == completed
    return ok, (f"{'no partial output' if ok else 'PARTIAL OUTPUT LEFT'}: "
                f"{completed} entr{'y' if completed == 1 else 'ies'} completed, "
                f"{files} file(s) on the volume")


def check(fixture, png, manifest_dir):
    """Cross-check the on-screen grid against the Linux engine's output."""
    man = os.path.join(manifest_dir, os.path.basename(fixture) + ".json")
    if not os.path.exists(man):
        return None, f"no oracle manifest for {os.path.basename(fixture)}"
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "vmac_check.py"),
                        man, png], capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixtures", nargs="*",
                    help="paths to fixtures; omit when using --list")
    ap.add_argument("--list", dest="listfile",
                    help="file of fixture names, one per line, '#' comments "
                         "(see tools/vmac/sample.txt)")
    ap.add_argument("--mem", default="4M", choices=("4M", "1M"),
                    help="emulated RAM; 1M is the project's floor target")
    ap.add_argument("--system", default="System6.hfv",
                    help="system image under $UNC_VMAC_HOME. The default is "
                         "System 6.0.8, the floor target; Sys7.img is the "
                         "System 7.0.1 tier, where Standard File returns a "
                         "working-directory refNum and the Process Manager "
                         "honours the 'SIZE' partition")
    ap.add_argument("--timeout", type=float, default=300.0,
                    help="host seconds to wait for a result grid (not Mac time)")
    ap.add_argument("--poll", type=float, default=5.0,
                    help="host seconds between screenshots. This is also the "
                         "granularity of the timing split, so lower it for a "
                         "1x run")
    ap.add_argument("--emu", default=None,
                    help="emulator build under $UNC_VMAC_HOME; defaults to "
                         "mv-<mem>, which runs ALL OUT. Pass mv-4M-1x for "
                         "authentic 7 MHz Mac Plus timing — the only build a "
                         "timing claim may be drawn from")
    ap.add_argument("--json", help="write per-fixture results here")
    ap.add_argument("--pngdir", help="keep each run's final screenshot here")
    ap.add_argument("-D", dest="defines", action="append", default=[],
                    metavar="UNC_...",
                    help="extra build switch for the application, e.g. "
                         "-D UNC_MAC_STAGE_WRITES (repeatable)")
    args = ap.parse_args()

    fixtures = list(args.fixtures)
    if args.listfile:
        for line in open(args.listfile):
            name = line.split("#")[0].strip()
            if name:
                fixtures.append(os.path.join(REPO, "fixtures", name))
    if not fixtures:
        ap.error("no fixtures given (pass paths, or --list)")
    missing = [f for f in fixtures if not os.path.exists(f)]
    if missing:
        raise SystemExit("run: fixtures not present: " + ", ".join(missing))

    appbin = build_autotest_app(args.defines)
    # Private to this invocation. A shared path would let a second run.py
    # rewrite the boot image while this one is copying it, which shows up as
    # an emulator that dies seconds after launch — a confusing way to
    # discover that two sweeps were overlapping.
    bootdir = tempfile.mkdtemp(prefix="vmacboot-")
    bootimg = os.path.join(bootdir, "boot-autotest.hfv")
    build_boot_image(appbin, bootimg, args.system)
    if args.pngdir:
        os.makedirs(args.pngdir, exist_ok=True)
    manifest_dir = os.path.join(REPO, "fixtures", "manifests")

    results, npass = [], 0
    for fixture in fixtures:
        name = os.path.basename(fixture)
        workdir = tempfile.mkdtemp(prefix="vmacrun-")
        keep = os.path.join(args.pngdir, name + ".png") if args.pngdir else None
        try:
            vals, secs, png, died, boot, extract = run_one(
                fixture, args.mem, args.timeout, args.poll, workdir, bootimg,
                keep, args.emu)
            status = AT_STATUS.get(signed32(vals[1])) if vals else None
            if vals is None and died:
                verdict, detail = "EMUDIED", (
                    f"the emulator process exited after {secs:.0f}s with no "
                    f"grid painted — a host-side failure (X server, disk "
                    f"images, a stray signal), not a Mac-side result. Re-run "
                    f"this fixture before reading anything into it")
            elif vals is None:
                verdict, detail = "NOGRID", (
                    f"nothing decodable within {args.timeout:.0f}s — the app "
                    f"never painted its 'alive' grid, so it did not launch "
                    f"or bombed before starting")
            elif signed32(vals[1]) == AT_RUNNING:
                verdict, detail = "TIMEOUT", (
                    f"app alive but still extracting after {args.timeout:.0f}s")
            elif status:
                verdict = "SETUP"
                detail = f"{status}; {vals[0]} volume(s) mounted"
            elif "UNC_AT_CANCEL" in args.defines:
                ok, detail = check_cancel(vals)
                verdict = "PASS" if ok else ("SETUP" if ok is None else "FAIL")
            else:
                ok, detail = check(fixture, png, manifest_dir)
                verdict = "PASS" if ok else "FAIL"
            timing = ""
            if boot is not None and extract is not None:
                timing = f" [boot {boot:.0f}s + extract {extract:.0f}s]"
            print(f"{verdict:8s} {name:44s} {secs:6.1f}s{timing}  {detail}",
                  flush=True)
            npass += verdict == "PASS"
            results.append(dict(fixture=name, mem=args.mem,
                                system=args.system, verdict=verdict,
                                emu=args.emu or f"mv-{args.mem}",
                                seconds=round(secs, 1),
                                boot_s=round(boot, 1) if boot else None,
                                extract_s=round(extract, 1) if extract else None,
                                detail=detail, values=vals))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    shutil.rmtree(bootdir, ignore_errors=True)
    print(f"\n{npass}/{len(fixtures)} PASS at {args.mem} on {args.system}")
    if args.json:
        json.dump(results, open(args.json, "w"), indent=1)
    return 0 if npass == len(fixtures) else 1


if __name__ == "__main__":
    sys.exit(main())

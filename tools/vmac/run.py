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



def _die_cleanly(signum, frame):
    """Turn a signal into a normal unwind so `finally` blocks run.

    Both harnesses start their emulator with start_new_session=True, on
    purpose: a stray signal to the process group must not take it down
    mid-write. The cost is that a driver killed by a `timeout` never reaches
    its cleanup and the emulator survives as an orphan — observed repeatedly,
    including two Xvfb displays and a qemu-system-ppc that had to be killed by
    hand, all of them competing for the CPU the next run needs. Raising
    SystemExit instead of dying in place lets the existing cleanup do its job.
    """
    raise SystemExit(f"interrupted by signal {signum}")


signal.signal(signal.SIGTERM, _die_cleanly)
signal.signal(signal.SIGINT, _die_cleanly)

def signed32(v):
    return v - (1 << 32) if v >= (1 << 31) else v


def sh(*argv, **kw):
    return subprocess.run(argv, check=True, capture_output=True, text=True,
                          errors="surrogateescape", **kw)


def make_floppy(path, volname, payload=None, extras=(), size_kb=FLOPPY_KB):
    """Create a fresh HFS floppy image, optionally with data-fork files.

    `payload` lands as ARCHIVE_NAME, which is the file the autotest app
    opens. `extras` are (host path, Mac name) pairs put beside it — the
    other parts of a segmented set, whose names are deliberately NOT
    required to resemble each other, since the app finds them by
    reading their headers.
    """
    with open(path, "wb") as f:
        f.truncate(size_kb * 1024)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        subprocess.run(["hformat", "-l", volname, path],
                       check=True, capture_output=True, env=env)
        files = ([(payload, ARCHIVE_NAME)] if payload else []) + list(extras)
        if files:
            subprocess.run(["hmount", path], check=True, capture_output=True, env=env)
            # -r: raw copy, data fork only. The archive is a plain byte stream;
            # its type/creator are irrelevant because the app opens it by name.
            for src, macname in files:
                subprocess.run(["hcopy", "-r", src, f"{volname}:{macname}"],
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
        # Xvfb picks the display and tells us which one, over a pipe. This
        # used to look for a free number by testing /tmp/.X<n>-lock and then
        # starting Xvfb on it, which is check-then-act: two runs started
        # together both saw :90 free, the second Xvfb died of the taken
        # lock, and its `xdotool getdisplaygeometry` probe succeeded anyway
        # — against the FIRST run's server. The two then shared a display
        # and photographed each other's emulator, so a fixture was graded
        # against another fixture's screen. Measured 2026-08-15, running
        # the 4 MB and 1 MB tiers in parallel as this directory's README
        # suggests; three fixtures "failed" with another run's numbers.
        #
        # Depth 24: Mini vMac's X11 glue picks a visual it can XPutImage
        # into, and on an 8-bit Xvfb the very first PutImage dies with
        # BadMatch, taking the emulator with it a few seconds after boot.
        r, w = os.pipe()
        self.proc = subprocess.Popen(
            ["Xvfb", "-displayfd", str(w), "-screen", "0", "800x600x24",
             "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, pass_fds=(w,))
        os.close(w)
        got = b""
        with os.fdopen(r, "rb") as pipe:
            for _ in range(200):
                chunk = pipe.read()
                if chunk:
                    got += chunk
                    break
                time.sleep(0.05)
        if not got.strip().isdigit():
            self.close()
            raise SystemExit("run: Xvfb did not report a display number")
        self.num = int(got.strip())
        for _ in range(200):                    # wait for it to accept clients
            if subprocess.run(["xdotool", "getdisplaygeometry"],
                              env=dict(os.environ, DISPLAY=self.name),
                              capture_output=True).returncode == 0:
                return
            time.sleep(0.05)
        self.close()
        raise SystemExit("run: Xvfb never accepted clients")

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
            emu_dir=None, extras=(), out_kb=FLOPPY_KB):
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
    make_floppy(indsk, "In", payload=fixture, extras=extras)  # image: System 6
    # `out_kb` exists to make the DESTINATION run out of room on purpose:
    # the full-disk path is otherwise unreachable, and a path nothing has
    # ever executed is not a path anyone should trust. See --out-kb.
    make_floppy(outdsk, "Out", size_kb=out_kb)  # boot volume as it goes

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
        # UNC_VMAC_PARK overrides the position so the claim above can be
        # TESTED rather than merely obeyed: park the pointer inside the grid
        # and see whether the decode still succeeds.
        park = os.environ.get("UNC_VMAC_PARK", "780,580").split(",")
        subprocess.run(["xdotool", "mousemove", park[0], park[1]],
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


def check_wd(vals):
    """Verdict for a UNC_AT_WD run.

    The application extracted through a WORKING DIRECTORY refNum with dirID 0
    — the shape SFGetFile hands it — into a subfolder of the Out volume. The
    files belong in that subfolder. If the working directory were mishandled
    they would land in the volume ROOT instead, which is precisely what no
    earlier harness here could detect, because they all extracted into a root
    to begin with."""
    entries, ret, errors = vals[0], signed32(vals[1]), vals[2]
    root_files, sub_files, wdref = vals[3], vals[4], signed32(vals[5])
    errs = signed32(vals[6])
    derr, werr = errs >> 16, (errs & 0xFFFF)
    if werr >= 0x8000:
        werr -= 0x10000
    if derr or werr:
        return None, (f"setup failed: DirCreate={derr}, OpenWD={werr} — no "
                      f"working directory was made, so nothing was tested")
    if ret != 0 or errors:
        return False, f"extraction failed: ret={ret}, {errors} entry error(s)"
    if entries == 0:
        return None, "no entries extracted — pick a fixture with content"
    if root_files:
        return False, (f"WRONG DIRECTORY: {root_files} file(s) landed in the "
                       f"volume ROOT instead of the working directory "
                       f"(wdRefNum {wdref}); {sub_files} landed correctly")
    ok = sub_files == entries
    return ok, (f"{'output landed in the working directory' if ok else 'COUNT MISMATCH'}: "
                f"{entries} entr{'y' if entries == 1 else 'ies'} extracted, "
                f"{sub_files} file(s) in the folder, {root_files} in the root "
                f"(wdRefNum {wdref})")


def check_interleave(vals):
    """Verdict for a UNC_AT_INTERLEAVE run.

    Reads one file twice on one volume — once undisturbed, once with a new
    file created and written on that same volume between every chunk — and
    compares the two CRC-32s.

    **PASS here means the interleave is HARMLESS**, i.e. the claim that reads
    go to zeros while the same volume is being written does NOT reproduce, and
    the whole-archive RAM slurp in RunExtract() is buying nothing. FAIL means
    the claim is real and finally has a reproduction. Say which way round it
    is in the text, because a bare PASS/FAIL on a negative test is exactly the
    kind of thing that gets read backwards a month later."""
    len_a, len_b, len_c = vals[0], vals[2], vals[7]
    crc_a, crc_b, crc_c = vals[3], vals[4], vals[6]
    rounds = vals[5] & 0xFFFF
    werr = vals[5] >> 16
    werr = werr - 0x10000 if werr >= 0x8000 else werr
    if len_a == 0:
        return None, "read nothing at all — the input file was not opened"
    if rounds == 0:
        return None, "no interleaved writes happened, so nothing was tested"
    if werr:
        return None, (f"could not create the interleaved files (err {werr}) — "
                      f"the volume, not the read, is what failed")
    seq_ok = (crc_a == crc_b) and (len_a == len_b)
    seek_ok = (crc_a == crc_c) and (len_a == len_c)
    if seq_ok and seek_ok:
        return True, (f"interleave is HARMLESS: {len_a} B, CRC {crc_a:08x}, "
                      f"read identically three ways — undisturbed, and twice "
                      f"more with {rounds} file creations on the same volume "
                      f"in between (sequential, and seeking before every "
                      f"read) — so the RAM slurp is not needed for this")
    which = []
    if not seq_ok:
        which.append(f"sequential {len_b} B CRC {crc_b:08x}")
    if not seek_ok:
        which.append(f"seeking {len_c} B CRC {crc_c:08x}")
    return False, (f"interleave CORRUPTS the read, so the slurp is justified: "
                   f"undisturbed {len_a} B CRC {crc_a:08x} vs "
                   + "; ".join(which) + f" over {rounds} rounds")


def check(fixture, png, manifest_dir, expect=False):
    """Cross-check the on-screen grid against the Linux engine's output.

    A fixture with no committed manifest is normally NOT graded: an
    archive nobody has an oracle for could otherwise pass by agreeing
    with nothing. `--expect` says grade it anyway, against this engine's
    own Linux output — which is what the SuperDisk! archives and the
    ArcMac specimens need, because they are payloads inside envelopes
    and have no manifest of their own. What adjudicates the Linux side
    for those is their own suite (run_superdisk.py, run_arc.py); this
    run adds the Mac to a verdict already reached, rather than reaching
    one on its own. TESTING.md.
    """
    man = os.path.join(manifest_dir, os.path.basename(fixture) + ".json")
    cmd = [sys.executable, os.path.join(REPO, "tools", "vmac_check.py")]
    if os.path.exists(man):
        cmd += [man, png]
    elif expect:
        cmd += ["--fixture", fixture, png]
    else:
        return None, f"no oracle manifest for {os.path.basename(fixture)}"
    r = subprocess.run(cmd, capture_output=True, text=True)
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
    ap.add_argument("--expect", action="store_true",
                    help="grade a file that has no oracle manifest against "
                         "this engine's own Linux output — for archives that "
                         "are payloads inside envelopes (SuperDisk!, the "
                         "ArcMac specimens), which have no manifest")
    ap.add_argument("--json", help="write per-fixture results here")
    ap.add_argument("--pngdir", help="keep each run's final screenshot here")
    ap.add_argument("--keep-disks", action="store_true",
                    help="do not delete the run's In/Out disk images, so\n                         the host can look at what the Mac actually\n                         wrote instead of only at the on-screen grid")
    ap.add_argument("--extra-file", action="append", default=[],
                    metavar="HOSTPATH:MACNAME",
                    help="put another file on the In floppy beside the "
                         "fixture. Used for the other parts of a segmented "
                         "set, whose names are deliberately unlike the "
                         "fixture's: the app matches them by header, not name")
    ap.add_argument("--out-kb", type=int, default=FLOPPY_KB,
                    help="size of the DESTINATION volume in KB (default "
                         f"{FLOPPY_KB}). Make it too small for the fixture "
                         "and the run exercises the full-disk path: the "
                         "shell should stop the run once, with ret = "
                         "UNC_ERR_ABORTED (-8), rather than failing every "
                         "remaining entry. It reports FAIL by construction "
                         "-- read the numbers, not the verdict.")
    ap.add_argument("-D", dest="defines", action="append", default=[],
                    metavar="UNC_...",
                    help="extra build switch for the application, e.g. "
                         "-D UNC_MAC_STAGE_WRITES (repeatable)")
    args = ap.parse_args()

    extras = []
    for spec in args.extra_file:
        host, _, macname = spec.rpartition(":")
        if not host or not macname:
            ap.error(f"--extra-file wants HOSTPATH:MACNAME, got {spec!r}")
        if not os.path.exists(host):
            raise SystemExit(f"run: no such file: {host}")
        extras.append((host, macname))

    fixtures = list(args.fixtures)
    if args.listfile:
        for line in open(args.listfile):
            name = line.split("#")[0].strip()
            if name:
                fixtures.append(os.path.join(REPO, "fixtures", name))
    # A list of names is not a set of names. sample.txt carried four
    # duplicates from M12 to 2026-08-21, so every sweep of every tier ran
    # them twice and every tier result counted them twice (BLOCKERS.md).
    # Deduplicated here rather than in the file alone, because the file is
    # edited by hand and this is not.
    seen, unique = set(), []
    for f in fixtures:
        if f in seen:
            print(f"run: {os.path.basename(f)} is listed more than once; "
                  f"running it once", flush=True)
            continue
        seen.add(f)
        unique.append(f)
    fixtures = unique
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
                keep, args.emu, extras=extras, out_kb=args.out_kb)
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
            elif "UNC_AT_WD" in args.defines:
                ok, detail = check_wd(vals)
                verdict = "PASS" if ok else ("SETUP" if ok is None else "FAIL")
            elif "UNC_AT_CANCEL" in args.defines:
                ok, detail = check_cancel(vals)
                verdict = "PASS" if ok else ("SETUP" if ok is None else "FAIL")
            elif "UNC_AT_INTERLEAVE" in args.defines:
                ok, detail = check_interleave(vals)
                verdict = "PASS" if ok else ("SETUP" if ok is None else "FAIL")
            else:
                ok, detail = check(fixture, png, manifest_dir, args.expect)
                verdict = "PASS" if ok else ("SETUP" if ok is None else "FAIL")
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
            if args.keep_disks:
                print(f"         disks kept in {workdir}", flush=True)
            else:
                shutil.rmtree(workdir, ignore_errors=True)

    shutil.rmtree(bootdir, ignore_errors=True)
    print(f"\n{npass}/{len(fixtures)} PASS at {args.mem} on {args.system}")
    if args.json:
        json.dump(results, open(args.json, "w"), indent=1)
    return 0 if npass == len(fixtures) else 1


if __name__ == "__main__":
    sys.exit(main())

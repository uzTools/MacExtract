#!/usr/bin/env python3
"""sys30.py — replay fixtures through the Mac shell on **System 3.0**.

Same result as `run.py`, on the oldest system a Macintosh Plus can boot: it
builds the In/Out floppies, boots the autotest application, waits for the
result grid, and grades it with `tools/vmac_check.py` against the same
committed oracle manifests. Everything about the grading is `run.py`'s.

    tools/vmac/sys30.py --list tools/vmac/sample.txt --mem 1M

**Why this is not just `run.py --system Sys30.img`.** Every other harness here
installs the application as the boot shell by rewriting the boot blocks'
`bbShellName` (mkboot.py, offset 0x1A). **System 3.0 ignores that field**:
a shell named `NoSuchApp`, one named `MacExtract` with the application in the
blessed folder, and one with it at the volume root all boot to the Finder with
a byte-identical framebuffer (measured 2026-08-30; DECISIONS.md, *the shell
name System 3.0 does not read*). So the application is launched the way a
person launches it — boot to the Finder, double-click the volume,
double-click the application.

Two things worth knowing before reading a number off this:

- **The Finder is NOT in memory while the engine works**, here or anywhere
  else. Single-tasking Mac OS unloads it when an application launches: on
  System 6.0.8 a boot-shell launch and a double-click launch differ by 12
  bytes of free heap (FORMATS.md, *512 KB machines*). Peak-heap figures are
  therefore comparable against `run.py`'s. What differs between systems is
  the SYSTEM heap.
- **The clicks are fixed coordinates**, measured off the volume window this
  harness's own boot image opens. They are stable because that image is
  rebuilt identically every run; they are wrong the moment the volume's
  contents change, and the symptom is NOGRID on every fixture — which looks
  exactly like an application that will not launch. Re-measure from the
  screenshot in --outdir before believing that.

What it cannot see: everything `run.py` cannot see (TESTING.md), plus the
user interface — this is the `UNC_MAC_AUTOTEST` build, which has no
SFGetFile, no progress dialog and no alerts. `interactive.py --system
Sys30.img --e2e` is what covers those.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402
sys.path.insert(0, os.path.join(R.REPO, "tools"))
from decode_grid import decode                               # noqa: E402

SYSTEM = "Sys30.img"        # System 3.0 / Finder 5.1, "System Tools" (800K)
# Both measured off this harness's own screenshots. The volume icon is where
# the Finder parks the boot disk; the application is the second of the two
# items in the window mkboot.py --finder leaves behind (System Folder, then
# MacExtract).
VOL_ICON = (472, 45)
APP_ICON = (170, 97)
# The desktop is up in under 3 s at "all out" speed; 8 s is slack, not a
# measurement. Both waits are host seconds and neither belongs in a timing
# claim — see run.py's header.
DESKTOP_WAIT = 8.0
WINDOW_WAIT = 5.0


def build_boot(appbin, dest):
    """A System 3.0 boot volume with the Finder left in place and the
    application at the volume root, for double-clicking."""
    stock = os.path.join(R.VMAC_HOME, SYSTEM)
    if not os.path.exists(stock):
        raise SystemExit(f"sys30: no {stock} — see tools/vmac/README.md")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin, dest,
         "--finder")


def _origin(dpy, env):
    """Where the emulator window landed. Queried, never assumed: with no
    window manager it sits at an arbitrary offset in the root window."""
    out = subprocess.run(["xdotool", "getwindowgeometry", "--shell", dpy.window()],
                         env=env, capture_output=True, text=True).stdout
    g = dict(line.split("=", 1) for line in out.strip().splitlines())
    return int(g["X"]), int(g["Y"])


def _dclick(env, ox, oy, x, y):
    subprocess.run(["xdotool", "mousemove", str(ox + x), str(oy + y)],
                   env=env, capture_output=True)
    time.sleep(0.4)
    subprocess.run(["xdotool", "click", "--repeat", "2", "--delay", "80", "1"],
                   env=env, capture_output=True)
    # Park the pointer off the grid, for the reason run.py parks it.
    subprocess.run(["xdotool", "mousemove", "780", "580"],
                   env=env, capture_output=True)


def run_one(fixture, bootimg, emu_dir, png, timeout, poll):
    """Boot, click the application into life, and wait for its grid."""
    work = tempfile.mkdtemp(prefix="sys30-")
    boot = os.path.join(work, "boot.hfv")
    indsk = os.path.join(work, "in.dsk")
    outdsk = os.path.join(work, "out.dsk")
    shutil.copyfile(bootimg, boot)          # every run starts from a pristine
    R.make_floppy(indsk, "In", payload=fixture)                     # image
    R.make_floppy(outdsk, "Out")

    emu = os.path.join(R.VMAC_HOME, emu_dir, "minivmac")
    rom = os.path.join(R.VMAC_HOME, "vMac.ROM")
    if not os.path.exists(emu):
        raise SystemExit(f"sys30: no emulator at {emu} — run tools/vmac/setup.sh")

    dpy = R.Display()
    env = dict(os.environ, DISPLAY=dpy.name)
    vals, started = None, time.time()
    proc = subprocess.Popen([emu, "-r", rom, boot, indsk, outdsk], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        for _ in range(120):
            if dpy.window():
                break
            time.sleep(0.5)
        # A window that never came up used to reach _origin anyway and die
        # there with a TypeError, which took the WHOLE SWEEP down: it
        # happened at fixture 70 of 71 on 2026-09-22 and cost the tally of
        # the sixty-nine that had already passed. One fixture that cannot
        # be started is one fixture's failure — the same NOGRID verdict a
        # run that starts and paints nothing gets — so say so and go on.
        if not dpy.window():
            print(f"sys30: the emulator window never appeared for "
                  f"{os.path.basename(fixture)} — reported as NOGRID",
                  flush=True)
            return None, time.time() - started
        ox, oy = _origin(dpy, env)
        time.sleep(DESKTOP_WAIT)
        _dclick(env, ox, oy, *VOL_ICON)     # open the boot volume
        time.sleep(WINDOW_WAIT)
        _dclick(env, ox, oy, *APP_ICON)     # launch MacExtract
        while time.time() - started < timeout:
            time.sleep(poll)
            if proc.poll() is not None:
                break                       # emulator died; take a last look
            if not dpy.screenshot(png):
                continue
            got = decode(png)
            if got is not None:
                vals = got
                if R.signed32(got[1]) != R.AT_RUNNING:
                    break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        dpy.close()
        shutil.rmtree(work, ignore_errors=True)
    return vals, time.time() - started


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixtures", nargs="*")
    ap.add_argument("--list", dest="listfile",
                    help="file of fixture names, one per line, # comments")
    ap.add_argument("--mem", default="4M", choices=("4M", "1M"),
                    help="emulated RAM (default 4M)")
    ap.add_argument("--emu", default=None,
                    help="emulator build directory (default mv-<mem>)")
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--poll", type=float, default=4.0)
    ap.add_argument("-o", "--outdir", default="sys30-shots",
                    help="where each run's final screenshot is kept")
    ap.add_argument("--json", help="write per-fixture results here")
    ap.add_argument("-D", dest="defines", action="append", default=[],
                    help="extra UNC_* build switch (repeatable), e.g. "
                         "-D UNC_AT_BUDGET — same meaning as run.py's")
    a = ap.parse_args()

    fixdir = os.path.join(R.REPO, "fixtures")
    fixtures = list(a.fixtures)
    if a.listfile:
        for line in open(a.listfile):
            line = line.split("#")[0].strip()
            if line:
                fixtures.append(os.path.join(fixdir, line))
    if not fixtures:
        raise SystemExit("sys30: no fixtures given")

    os.makedirs(a.outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sys30-boot-")
    bootimg = os.path.join(work, "boot30.hfv")
    build_boot(R.build_autotest_app(tuple(a.defines)), bootimg)
    emu_dir = a.emu or f"mv-{a.mem}"
    # The machine is the EMULATOR BUILD, not --mem: --emu overrides it, and a
    # summary that reports --mem's default while a different machine ran is
    # how a 512 KB result gets filed as a 4 MB one.
    machine = emu_dir.replace("mv-", "")
    manifests = os.path.join(fixdir, "manifests")

    results, npass, nbad = [], 0, 0
    try:
        for fixture in fixtures:
            base = os.path.basename(fixture)
            png = os.path.join(a.outdir, base + ".png")
            vals, secs = run_one(fixture, bootimg, emu_dir, png,
                                 a.timeout, a.poll)
            man = os.path.join(manifests, base + ".json")
            if vals is None:
                verdict = "NOGRID"
                detail = (f"nothing decodable within {a.timeout:.0f}s — the "
                          f"application never painted its 'alive' grid")
            elif not os.path.exists(man):
                verdict = "NOMAN"
                detail = ("no oracle manifest; grid "
                          f"{[R.signed32(v) for v in vals]}")
            else:
                r = subprocess.run(
                    [sys.executable, os.path.join(R.REPO, "tools", "vmac_check.py"),
                     man, png], capture_output=True, text=True)
                verdict = "PASS" if r.returncode == 0 else "FAIL"
                detail = (r.stdout + r.stderr).strip().replace("\n", " ")
            npass += verdict == "PASS"
            nbad += verdict in ("FAIL", "NOGRID")
            print(f"{verdict:7s} {base:45s} {secs:5.1f}s  {detail}", flush=True)
            results.append(dict(fixture=base, verdict=verdict, detail=detail,
                                secs=round(secs, 1),
                                grid=[R.signed32(v) for v in vals] if vals else None))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"\n{npass}/{len(fixtures)} PASS on System 3.0 ({machine})")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(results, f, indent=1)
    return 1 if nbad else 0


if __name__ == "__main__":
    sys.exit(main())

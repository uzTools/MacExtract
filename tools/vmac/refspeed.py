#!/usr/bin/env python3
"""refspeed.py — MacExtract beside each format's own Macintosh program.

`expander.py` times this application against StuffIt Expander 4.0.2, which
opens four families. This times it against the program that wrote, or was
the reference expander for, every other format it can find on this machine:
each one booted alone as the startup application of a stock volume (or on
its own harness's System 7 volume where it needs an INIT), the archive on
the same volume, both driven to the point where one keystroke or click
starts the work, and both timed with `macclock.py` exactly as `expander.py`
times (from that action to the last change of the screen buffer before it
holds still for `--quiet` seconds, in emulated ticks / 60.15).

    tools/vmac/refspeed.py --list
    tools/vmac/refspeed.py --ref cpt151 --repeat 2 --json t.json FIXTURE
    tools/vmac/refspeed.py --ref ours --system System6.hfv FIXTURE

Every run is graded: the files it left on the volume are pulled (`hcopy
-m`, after the program has quit, so its cache is on the image) and their
data forks and masked resource forks compared, as multisets, with what the
Linux engine writes for the same archive (`macextract x --forks hidden`,
`-nr` where the program removes one layer only). The engine is graded
against `unar`/`macunpack` by the differential suite; a fast wrong answer is
reported as such, never as a time.

ONE EMULATOR AT A TIME: at 1x a second busy process inflates host time
(ticks stay honest; the JSON `ratio` says how far the host lagged).

What it cannot see
------------------
- Everything `macclock.py` and `expander.py` cannot: emulator fidelity,
  disk time, masked-interrupt ticks, work that draws nothing for longer
  than `--quiet` (the output check catches that only if the program is
  still writing when it is told to quit).
- A program's own cache: like Expander, most of these leave writes in the
  File Manager's cache until they quit; the time stops at the screen, the
  `quit` figure is reported beside it (as `expander.py` does).
- Names. The grade is by fork contents; where a program names a file
  differently (a `.gz` stripped or not) the time is still the same work.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                              # noqa: E402
import guard                                                 # noqa: E402
import macclock as MC                                        # noqa: E402
from interactive import Mac                                  # noqa: E402
from arcmac import macbinary                                 # noqa: E402
from vmac_check import mask_reserved                         # noqa: E402
from expander import (names_on, select_by_name, stopwatch,   # noqa: E402
                      timed, forks, EXPAND_BUTTON)
from cptexp import pull                                      # noqa: E402

V = R.VMAC_HOME
SPEC = os.path.join(V, "specimens")
CACHE = os.path.join(V, "speed")      # the reference programs, as MacBinary
PAUSE = os.path.join(REPO, ".tmp", "emu-pause")
ENGINE = os.environ.get("MACEXTRACT", os.path.join(REPO, "build", "rel",
                                                   "macextract"))

# Steps: ("cmd", ch) Command-ch; ("key", name); ("type", text);
# ("select",) type-ahead the archive's name; ("click", x, y); ("dclick", x, y);
# ("sleep", s); ("shot", name); ("settle", quiet) wait for a still screen.
# `act` is the ONE step that starts the work and is timed; `post` runs after
# the screen has held still, and must leave the program quit or idle with its
# writes committed.
OURS_PRE = [("select",), ("shot", "selected"), ("key", "Return"),
            ("sleep", 3.0), ("shot", "destination")]
OURS = dict(app=None, app_name="MacExtract", pre=OURS_PRE,
            act=("key", "Return"),
            post=[("key", "Return"), ("sleep", 2.0), ("cmd", ".")],
            ftype=None)

REFS = {
    "ours": OURS,
    # StuffIt Expander 4.0.2: expander.py's own drive, unchanged.
    "exp402": dict(app=os.path.join(V, "expander", "Expander.bin"),
                   app_name="Expander",
                   pre=[("cmd", "e"), ("sleep", 3.0), ("select",),
                        ("shot", "selected"), ("move", *EXPAND_BUTTON)],
                   act=("press",),
                   post=[("cmd", "q"), ("sleep", 10.0)],
                   ignore=(":System Folder:", "Comments about ")),
}


def load_more():
    """Programs whose drive was measured after this file was written live
    in refspeed_progs.py beside it, one dict per program, merged here."""
    try:
        import refspeed_progs                                # noqa: E402
        REFS.update(refspeed_progs.REFS)
    except ImportError:
        pass


# ------------------------------------------------------------------
# Gate: one emulator machine-wide, never beside ci.sh
# ------------------------------------------------------------------

def busy():
    mine = {os.getpid()}
    emu = ci = 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) in mine:
            continue
        try:
            comm = open(f"/proc/{pid}/comm").read().strip()
            args = open(f"/proc/{pid}/cmdline").read().replace("\0", " ")
        except OSError:
            continue
        if comm == "minivmac" or comm.startswith("qemu-system"):
            emu += 1
        if args.startswith("/bin/sh ./ci.sh") or args.startswith("sh ./ci.sh"):
            ci += 1
    return emu, ci


def gate(strict=300.0):
    """No ci.sh at all; no other emulator for `strict` s, then beside one
    at most (memory: emulator-gate-must-be-bounded)."""
    t0 = time.time()
    while True:
        while os.path.exists(PAUSE):
            print("refspeed: paused by .tmp/emu-pause", flush=True)
            time.sleep(60)
        emu, ci = busy()
        if not ci and (emu == 0 or (emu <= 1 and time.time() - t0 > strict)):
            if emu:
                print("refspeed: proceeding beside one other emulator",
                      flush=True)
            return emu
        time.sleep(20)


# ------------------------------------------------------------------
# The reference output
# ------------------------------------------------------------------

def rkey(b):
    return hashlib.sha256(mask_reserved(b)).hexdigest()


def engine_forks(fixture, work, nr=False):
    """(data multiset, masked rsrc multiset, files) the engine writes."""
    out = os.path.join(work, "ref-out")
    shutil.rmtree(out, ignore_errors=True)
    argv = [ENGINE, "x", "--forks", "hidden", "-o", out] + \
        (["-nr"] if nr else []) + [fixture]
    subprocess.run(argv, capture_output=True)
    data, rsrc, n = Counter(), Counter(), 0
    for root, _, fs in os.walk(out):
        for f in fs:
            b = open(os.path.join(root, f), "rb").read()
            if f.startswith("._"):
                if b:
                    rsrc[rkey(b)] += 1
            elif f.endswith(".comment.txt"):
                continue
            else:
                n += 1
                data[hashlib.sha256(b).hexdigest()] += 1
    shutil.rmtree(out, ignore_errors=True)
    return data, rsrc, n


def grade(got, ref):
    data, rsrc, n = ref
    gd = Counter(hashlib.sha256(d).hexdigest() for d, _ in got.values())
    gr = Counter(rkey(r) for _, r in got.values() if r)
    return {"files": len(got), "engine_files": n,
            "data_agree": gd == data, "rsrc_agree": gr == rsrc,
            "data_extra": len(gd - data), "data_missing": len(data - gd),
            "rsrc_extra": len(gr - rsrc), "rsrc_missing": len(rsrc - gr)}


def fill(img, free_mb, work):
    """Leave about `free_mb` MB free on the volume with one zero-filled
    file, `Filler`. UnZip 1.01 skips every file "no space on volume" with
    23 MB free on the stock volume and extracts with 3 MB (measured
    2026-11-14); both programs of a pair are run on the same filled
    volume."""
    home = tempfile.mkdtemp(prefix="hfs-", dir=guard.TMP)
    env = dict(os.environ, HOME=home)
    try:
        subprocess.run(["hmount", img], env=env, check=True,
                       capture_output=True)
        out = subprocess.run(["hvol"], env=env, capture_output=True,
                             text=True).stdout
        free = int(out.split("Volume has ")[1].split()[0])
        n = free - int(free_mb * 1024 * 1024)
        if n > 0:
            raw = os.path.join(work, "filler.raw")
            with open(raw, "wb") as f:
                f.truncate(n)
            subprocess.run(["hcopy", "-r", raw, ":Filler"], env=env,
                           check=True, capture_output=True)
            os.remove(raw)
        subprocess.run(["humount"], env=env, capture_output=True)
    finally:
        shutil.rmtree(home, ignore_errors=True)


# ------------------------------------------------------------------
# One run
# ------------------------------------------------------------------

class CaretWatch(MC.Watch):
    """A Watch that does not count a blinking text caret as a change.

    A console program (suntar 1.3.1, whose drive was explored and never
    run at 1x) keeps an insertion caret blinking after the work is done,
    so the screen never holds still. A change whose differing bytes
    all lie in one 1-byte-wide column (8 pixels) of at most 20 rows is
    taken for the caret and not counted; anything wider is. What it cannot
    see: real work that changes only such a sliver for longer than
    `--quiet` — the output check is what would catch that."""

    def sample(self):
        s = self.mem.screen()
        return time.monotonic(), self.mem.ticks(), s, s

    def mark(self):
        t, k, h, _ = self.sample()
        self.prev = h
        return t, k

    def until_quiet(self, quiet, timeout, snap=None):
        start = time.monotonic()
        changes, last = [], start
        while True:
            time.sleep(self.dt)
            if snap and time.monotonic() - start >= snap[0]:
                snap[1]()
                snap = None
            t, k, s, _ = self.sample()
            if s != self.prev:
                diff = [i for i in range(len(s)) if s[i] != self.prev[i]]
                cols = {i % 64 for i in diff}
                rows = {i // 64 for i in diff}
                self.prev = s
                if not (len(cols) == 1 and max(rows) - min(rows) < 20):
                    changes.append((t, k))
                    last = t
            elif t - last >= quiet:
                return changes, False
            if t - last >= quiet:
                return changes, False
            if t - start > timeout:
                return changes, True


def do(mac, step, macname, shots, tag):
    op = step[0]
    if op == "cmd":
        mac.command_key(step[1])
    elif op == "key":
        mac.key(step[1])
    elif op == "type":
        mac._xdo("type", "--delay", "80", step[1])
        time.sleep(0.6)
    elif op == "select":
        select_by_name(mac, macname if len(step) < 2 else step[1])
    elif op == "click":
        mac.click(step[1], step[2])
    elif op == "dclick":
        mac.click(step[1], step[2], double=True)
    elif op == "move":                 # pointer there; `press` clicks it
        ox, oy = mac.origin()
        mac._xdo("mousemove", str(ox + step[1]), str(oy + step[2]))
        time.sleep(0.6)
    elif op == "press":
        mac._xdo("click", "1")
    elif op == "sleep":
        time.sleep(step[1])
    elif op == "shot":
        mac.shot(os.path.join(shots, f"{tag}-{step[1]}.png"))
    elif op == "settle":
        mac.settle(os.path.join(shots, ".settle.png"), interval=3.0,
                   timeout=900.0, quiet=step[1])
    else:
        raise SystemExit(f"refspeed: unknown step {step!r}")


def run_one(name, spec, fixture, args, shots, n):
    work = tempfile.mkdtemp(prefix=f"refspeed-{name}-", dir=guard.TMP)
    tag = f"{name}-{n}"
    try:
        macname = (spec.get("macname") or os.path.basename(fixture))[:31]
        ftype, creator = spec.get("ftype") or ("????", "????")
        if args.ftype:
            ftype, creator = args.ftype.split("/")
        typed = os.path.join(work, "typed.bin")
        open(typed, "wb").write(macbinary(macname, ftype, creator,
                                          data=open(fixture, "rb").read()))
        system = spec.get("system") or args.system
        boot = os.path.join(work, "boot-in.hfv")
        app = spec["app"] or args.ours
        argv = [sys.executable, os.path.join(HERE, "mkboot.py"),
                os.path.join(V, system), app, boot,
                "--macbin", f"{typed}:{macname}",
                "--app-name", spec.get("app_name", "MacExtract")]
        for extra in spec.get("extra", ()):
            argv += ["--macbin", extra]
        R.sh(*argv)
        if args.free:
            fill(boot, args.free, work)
        before = set(names_on(boot))
        gate()
        mac = Mac(boot, args.emu, work)
        watch = timing = q = None
        try:
            if mac.settle(os.path.join(work, "s.png"), interval=5.0,
                          timeout=300.0) is None:
                raise SystemExit(f"refspeed: {name} never booted")
            mac.shot(os.path.join(shots, f"{tag}-1-launched.png"))
            mac.origin(cached=False)
            for st in spec["pre"]:
                do(mac, st, macname, shots, tag)
            watch = stopwatch(mac, args.emu)
            if spec.get("caret"):
                watch = CaretWatch(watch.mem, hz=50.0)
            started = os.path.join(shots, f"{tag}-2b-started.png")
            act = spec["act"]
            if act[0] == "cmd":
                # The Command key goes down BEFORE the mark, so the span
                # holds one keystroke, as our own Return does; it comes up
                # after the key, inside the span, while the Mac works.
                mac._xdo("keydown", "alt")
                time.sleep(0.4)

                def go():
                    mac._xdo("key", act[1])
                    time.sleep(0.3)
                    mac._xdo("keyup", "alt")
            else:
                def go():
                    do(mac, act, macname, shots, tag)
            timing = timed(watch, go,
                           args.quiet, args.timeout,
                           snap=(2.0, lambda: mac.shot(started)))
            mac.shot(os.path.join(shots, f"{tag}-3-finished.png"))
            qmark = watch.mark()
            for st in spec["post"]:
                do(mac, st, macname, shots, tag)
            qch, _ = watch.until_quiet(15.0, 300.0)
            q = MC.reading(qmark, qch)
            mac.shot(os.path.join(shots, f"{tag}-4-quit.png"))
        finally:
            if watch is not None:
                watch.mem.close()
            mac.close()
        img = os.path.join(work, "boot.hfv")
        ign = spec.get("ignore", (":System Folder:",))
        new = [p for p in names_on(img) if p not in before
               and not any(s in p for s in ign)]
        got = pull(img, new, work)
        ref = engine_forks(fixture, work, nr=spec.get("nr", False))
        g = grade(got, ref)
        return {"prog": name, "fixture": os.path.basename(fixture),
                "size": os.path.getsize(fixture), "system": system,
                "emu": args.emu, "run": n, "free_mb": args.free,
                "seconds": None if not timing or timing["timed_out"]
                else timing["mac_s"],
                "quit": q["mac_s"] if q else None,
                "timing": timing, "grade": g, "new": new[:50],
                "date": time.strftime("%Y-%m-%d")}
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


def main():
    load_more()
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fixtures", nargs="*")
    p.add_argument("--ref", default="ours", help="program; --list names them")
    p.add_argument("--list", action="store_true")
    p.add_argument("--ours", default=os.path.join(REPO, "dist", "MacExtract.bin"))
    p.add_argument("--emu", default="mv-4M-1x")
    p.add_argument("--system", default="System6.hfv")
    p.add_argument("--ftype", help="TYPE/CRTR to give the archive")
    p.add_argument("--repeat", type=int, default=2)
    p.add_argument("--free", type=float, default=0,
                   help="leave about this many MB free on the volume")
    p.add_argument("--quiet", type=float, default=60.0)
    p.add_argument("--timeout", type=float, default=3000.0)
    p.add_argument("-o", "--outdir")
    p.add_argument("--json")
    p.add_argument("--keep", action="store_true")
    args = p.parse_args()
    if args.list:
        for k in sorted(REFS):
            print(k, REFS[k].get("app"))
        return 0
    spec = REFS[args.ref]
    if not args.outdir:
        args.outdir = guard.run_dir("refspeed")
    os.makedirs(args.outdir, exist_ok=True)
    rows = json.load(open(args.json)) if args.json and \
        os.path.exists(args.json) else []
    for fx in args.fixtures:
        shots = os.path.join(args.outdir, os.path.basename(fx).replace(".", "_"))
        os.makedirs(shots, exist_ok=True)
        for n in range(1, args.repeat + 1):
            r = run_one(args.ref, spec, os.path.abspath(fx), args, shots, n)
            rows.append(r)
            if args.json:
                json.dump(rows, open(args.json, "w"), indent=1)
            t = r["timing"] or {}
            g = r["grade"]
            print("refspeed: %-8s #%d %-34s %8s s  ticks %s  ratio %s  "
                  "quit %s s  files %d/%d data %s rsrc %s" % (
                      args.ref, n, r["fixture"], r["seconds"], t.get("ticks"),
                      t.get("ratio"), r["quit"], g["files"], g["engine_files"],
                      g["data_agree"], g["rsrc_agree"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""superdisk.py — grade Alysis SuperDisk! extraction with SuperDisk!'s own extractor.

The corpus holds two SuperDisk! archives and both are self-extracting
applications, so each one carries the implementation it should be graded
against — the same bargain `nowcompress.py --adjudicate` makes for the
1995 `.sea`. `unar` and `macunpack` both stop at the envelope, so without
this there is no oracle for the format at all.

    tools/vmac/superdisk.py --list                    what the corpus holds
    tools/vmac/superdisk.py --adjudicate FIXTURE.hqx  run it, compare forks
    tools/vmac/superdisk.py --on-mac                  replay both payloads
                                                      through OUR application

The archive is unwrapped from its envelope with our own CLI, rebuilt as
MacBinary and put on a 25 MB volume; System 7 boots, the application is
double-clicked, its "Save the expanded file as:" box is accepted with
Return, and every fork it wrote is compared with `macextract x`.

Resource forks are compared with bytes 16..127 masked, the convention
`tools/vmac_check.py` uses: the Resource Manager stamps that region
whenever it touches a file.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                       # noqa: E402
from arcmac import macbinary                          # noqa: E402
from nowcompress import Session                       # noqa: E402

HOME = R.VMAC_HOME
SHOTS = os.path.join(HOME, "specimens", "superdisk")

FIXTURES = ["alysis-disk-expander-12.hqx", "super-disk-utility.hqx"]


def cli():
    exe = os.path.join(REPO, "build", "macextract")
    if not os.path.exists(exe):
        subprocess.run(["make", "-C", REPO], check=True, capture_output=True)
    return exe


def unwrap(fixture, work):
    """The archive itself, out of its envelope: (name, type, creator, data, rsrc)."""
    out = os.path.join(work, "payload")
    os.makedirs(out, exist_ok=True)
    subprocess.run([cli(), "x", "-nr", "-o", out, fixture], check=True,
                   capture_output=True)
    listing = subprocess.run([cli(), "l", "-nr", fixture], capture_output=True,
                             text=True).stdout
    tc, name = None, None
    for line in listing.splitlines():
        f = line.split(None, 4)
        if len(f) == 5 and f[0] == "f":
            tc, name = f[3], f[4]
    if not name:
        raise SystemExit("superdisk: %s holds no file" % fixture)
    data = open(os.path.join(out, name), "rb").read()
    rp = os.path.join(out, name + ".rsrc")
    rsrc = open(rp, "rb").read() if os.path.exists(rp) else b""
    return name, tc[:4], tc[5:], data, rsrc


def read_forks(img):
    """path -> (type, creator, data, rsrc) for every file on a volume."""
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    out = {}

    def walk(prefix):
        """`prefix` is a TUPLE of components: an HFS name may contain a
        slash, so a joined path cannot be split back apart.

        Names go to `hcd` and `hcopy` as the RAW BYTES `hls` printed, not
        as text. HFS names are Mac Roman and Python would hand a str to
        the shell as UTF-8, so a folder called "Terrainman 2.0 ƒ" was
        neither descended into nor copied — and a walk that silently
        skips a folder reports zero forks, which reads as "the
        application wrote nothing" rather than "this could not read it"
        (measured 2026-08-21, on a run whose screenshot showed the
        folder sitting on the volume).
        """
        listing = subprocess.run(["hls", "-1"], capture_output=True,
                                 env=env).stdout
        for raw in [n for n in listing.split(b"\n") if n.strip()]:
            name = raw.decode("mac-roman", "replace")
            if subprocess.run([b"hcd", raw], capture_output=True,
                              env=env).returncode == 0:
                walk(prefix + (name,))
                subprocess.run(["hcd", "::"], capture_output=True, env=env)
                continue
            tmp = tempfile.mktemp(suffix=".bin")
            if subprocess.run([b"hcopy", b"-m", raw, tmp.encode()],
                              capture_output=True,
                              env=env).returncode != 0:
                continue
            blob = open(tmp, "rb").read()
            os.unlink(tmp)
            dlen, rlen = struct.unpack(">II", blob[83:91])
            roff = 128 + ((dlen + 127) & ~127)
            out[prefix + (name,)] = (blob[65:69].decode("mac-roman"),
                                     blob[69:73].decode("mac-roman"),
                                     blob[128:128 + dlen], blob[roff:roff + rlen])
    try:
        subprocess.run(["hmount", img], check=True, capture_output=True, env=env)
        walk(())
        subprocess.run(["humount"], capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    return out


def adjudicate(fixture, keep=False):
    from vmac_check import mask_reserved                # noqa: E402
    work = tempfile.mkdtemp(prefix="sdadj-")
    tag = os.path.basename(fixture).split(".")[0]
    name, ftype, creator, data, rsrc = unwrap(fixture, work)
    print("superdisk: %s — %s %s/%s, %d B data, %d B rsrc"
          % (os.path.basename(fixture), name, ftype, creator, len(data), len(rsrc)))
    mb = os.path.join(work, "app.bin")
    open(mb, "wb").write(macbinary(name, ftype, creator, data, rsrc))

    img = os.path.join(work, "adj.img")
    open(img, "wb").truncate(25 * 1024 * 1024)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    subprocess.run(["hformat", "-l", "Adj", img], check=True,
                   capture_output=True, env=env)
    subprocess.run(["hmount", img], check=True, capture_output=True, env=env)
    subprocess.run(["hcopy", "-m", mb, "Adj:"], check=True,
                   capture_output=True, env=env)
    subprocess.run(["humount"], check=True, capture_output=True, env=env)

    shots = os.path.join(SHOTS, tag)
    s = Session(os.path.join(HOME, "Sys7.img"), [img], shots)
    try:
        s.boot()
        s.mac.click(470, 110, double=True)              # open the volume
        time.sleep(10)
        s.shot("volume", wait=3.0)
        # Select All, then Open. The volume holds exactly one item, so
        # this needs no coordinate at all — and a coordinate is what
        # broke here: double-clicking a measured point launched the
        # first archive and merely selected the second, whose icon the
        # Finder had drawn a few pixels higher. The run "succeeded"
        # having launched nothing, which is what a screenshot of the
        # right window and the wrong moment always looks like.
        s.mac.command_key("a")
        time.sleep(2)
        s.mac.command_key("o")
        s.shot("launched", wait=45.0)
        s.mac.key("Return")                             # accept the save box
        s.shot("expanding", wait=90.0)
        s.mac.key("Return")
        s.shot("done", wait=90.0)
        s.mac.click(470, 110)
        s.mac.command_key("y")                          # Put Away: flush
        s.shot("ejected", wait=20.0)
    finally:
        time.sleep(5)
        s.close()

    theirs = read_forks(img)
    ours = tempfile.mkdtemp()
    subprocess.run([cli(), "x", "--forks", "hidden", "-o", ours, fixture],
                   check=True, capture_output=True)
    bad = seen = 0
    for path, (ftype, creator, data, rsrc) in sorted(theirs.items()):
        if path[-1] == name:
            continue                                    # the archive itself
        # The sink writes a component's slash as a colon, HFS's own
        # separator, which is the one character a Mac name cannot hold.
        mine = os.path.join(ours, *[p.replace("/", ":") for p in path])
        head, tail = os.path.split(mine)
        ours_data = open(mine, "rb").read() if os.path.isfile(mine) else b""
        side = os.path.join(head, "._" + tail)
        ours_rsrc = open(side, "rb").read() if os.path.isfile(side) else b""
        for fork, a, b in (("data", data, ours_data),
                           ("rsrc", mask_reserved(rsrc), mask_reserved(ours_rsrc))):
            if not a and not b:
                continue
            seen += 1
            same = a == b
            bad += not same
            shown = "/".join(path)
            print("  %-40s %s/%s %-4s %8d B  %s"
                  % (shown[-40:], ftype, creator, fork, len(a),
                     "IDENTICAL" if same else "DIFFERS"))
    shutil.rmtree(ours, ignore_errors=True)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    print("superdisk: %d fork(s) compared, %s"
          % (seen, "all identical" if not bad and seen else "%d DIFFER" % bad))
    print("superdisk: screenshots in %s" % shots)
    return bad or not seen


def listing():
    for f in FIXTURES:
        p = os.path.join(REPO, "fixtures", f)
        if not os.path.exists(p):
            print("%s: not in the corpus" % f)
            continue
        print("== %s" % f)
        r = subprocess.run([cli(), "l", p], capture_output=True, text=True)
        sys.stdout.write(r.stdout or r.stderr)


def on_mac(mem="4M", system="System6.hfv"):
    """Replay both payloads through OUR Mac application.

    The archives are payloads INSIDE envelopes, so they are in no
    `--list` file and a sweep of the corpus leaves them out silently —
    which is what OPEN_ITEMS.md recorded until this existed. They also
    have no oracle manifest, since `unar` stops at the envelope, so the
    run is graded with `run.py --expect`: the aggregate on screen
    against this engine's own Linux output, whose SuperDisk! side is
    adjudicated fork by fork by the archives' own self-extractors
    (`--adjudicate`, replayed offline by `tools/run_superdisk.py`).
    """
    work = tempfile.mkdtemp(prefix="sdmac-")
    bad = ran = 0
    try:
        for f in FIXTURES:
            p = os.path.join(REPO, "fixtures", f)
            if not os.path.exists(p):
                print("superdisk: %s is not in the corpus, skipped" % f)
                continue
            out = os.path.join(work, f)
            os.makedirs(out)
            subprocess.run([cli(), "x", "-nr", "-o", out, p], check=True,
                           capture_output=True)
            for name in sorted(os.listdir(out)):
                if name.endswith(".rsrc"):
                    continue
                ran += 1
                r = subprocess.run(
                    [sys.executable, os.path.join(HERE, "run.py"),
                     os.path.join(out, name), "--expect", "--mem", mem,
                     "--system", system], capture_output=True, text=True)
                bad += r.returncode != 0
                sys.stdout.write(r.stdout + r.stderr)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("superdisk: %d payload(s) replayed on the Mac at %s, %s"
          % (ran, mem, "all PASS" if not bad and ran else "%d FAILED" % bad))
    return 1 if (bad or not ran) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true",
                    help="list what the corpus's SuperDisk! archives hold")
    ap.add_argument("--adjudicate", metavar="FIXTURE",
                    help="run the self-extractor under System 7 and compare")
    ap.add_argument("--on-mac", action="store_true",
                    help="replay both payloads through our own Mac "
                         "application, graded with run.py --expect")
    ap.add_argument("--mem", default="4M", choices=("4M", "1M"))
    ap.add_argument("--system", default="System6.hfv")
    ap.add_argument("--keep", action="store_true", help="keep the work volume")
    a = ap.parse_args()
    if a.list:
        listing()
        return 0
    if a.adjudicate:
        return adjudicate(a.adjudicate, a.keep)
    if a.on_mac:
        return on_mac(a.mem, a.system)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

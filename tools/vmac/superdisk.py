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
    tools/vmac/superdisk.py --nest                    hand that extractor a
                                                      stream written HERE

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
import synth_sd                                       # noqa: E402

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


def run_selfextractor(work, name, ftype, creator, data, rsrc, tag):
    """Put a self-extracting archive on a fresh volume, run it, hand back
    the volume. Shared by --adjudicate and --nest, which differ only in
    what data fork the application is given."""
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
    return img


def adjudicate(fixture, keep=False):
    from vmac_check import mask_reserved                # noqa: E402
    work = tempfile.mkdtemp(prefix="sdadj-")
    tag = os.path.basename(fixture).split(".")[0]
    name, ftype, creator, data, rsrc = unwrap(fixture, work)
    print("superdisk: %s — %s %s/%s, %d B data, %d B rsrc"
          % (os.path.basename(fixture), name, ftype, creator, len(data), len(rsrc)))
    img = run_selfextractor(work, name, ftype, creator, data, rsrc, tag)

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


# ------------------------------------------------------------------
# A record stream this project writes, read back by the format's own
# extractor
# ------------------------------------------------------------------

# The 20 bytes a folder record carries after its name, and the 8 nobody
# reads at the head of the file, are copied from a real archive rather
# than invented: neither field is understood, and a wrong guess in
# either would be indistinguishable from the failure this run is
# looking for.


def decoded(work, orig):
    """The borrowed fork's plaintext, through our own reader — the one
    thing a builder cannot produce, since producing it means
    compressing."""
    one, _dlen = synth_sd.one_file(orig)
    arc = os.path.join(work, "one.x")
    open(arc, "wb").write(one)
    out = os.path.join(work, "plain")
    subprocess.run([cli(), "x", "-o", out, arc], check=True,
                   capture_output=True)
    return open(os.path.join(out, "plain.txt"), "rb").read()


def rootfile_probe(keep=False, invented=False):
    """Does that extractor read a stream whose FIRST record is a file?

    The first `--nest` run bombed with the Macintosh's *unimplemented
    trap* on a stream that differed from the ones that work in three
    ways at once, and two are now cleared: depth is not it (`--nest` at
    ten folders is byte-exact) and the stored block is not it
    (`--stored`). What is left is the record itself, and this asks the
    half that costs nothing to build — a file at the root, before any
    folder record, which is the one thing neither corpus archive does.
    """
    work = tempfile.mkdtemp(prefix="sdroot-")
    name, ftype, creator, orig, rsrc = unwrap(
        os.path.join(REPO, "fixtures", "super-disk-utility.hqx"), work)
    blob, dlen = synth_sd.one_file(orig, invented)
    print("superdisk: %d B, one %d B file and no folder at all, its record "
          "%s" % (len(blob), dlen,
                  "INVENTED" if invented else "borrowed from the corpus"))
    plain = decoded(work, orig)
    img = run_selfextractor(work, name, ftype, creator, blob, rsrc,
                            "invented" if invented else "rootfile")
    theirs = {"/".join(k): v[2] for k, v in read_forks(img).items()
              if k[-1] != name}
    got = theirs.pop("plain.txt", None)
    state = ("MISSING" if got is None else
             "made" if got == plain else "CONTENT DIFFERS")
    print("  theirs plain.txt   %s" % state)
    for extra in sorted(theirs):
        print("  UNEXPECTED on the Mac: %s" % extra)
    print("superdisk: %s" % ("a file at the root is read"
                             if state == "made" else
                             "a file at the root is NOT read"))
    print("superdisk: screenshots in %s"
          % os.path.join(SHOTS, "invented" if invented else "rootfile"))
    if keep:
        print("superdisk: kept %s" % work)
    else:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if state != "made" else 0


def stored_probe(keep=False):
    """Does the format's own extractor read a stored block at all?"""
    work = tempfile.mkdtemp(prefix="sdstore-")
    name, ftype, creator, orig, rsrc = unwrap(
        os.path.join(REPO, "fixtures", "super-disk-utility.hqx"), work)
    plain = decoded(work, orig)
    blob, fold = synth_sd.stored_pair(orig, plain)
    archive = os.path.join(work, "stored.x")
    open(archive, "wb").write(blob)
    print("superdisk: %d B, one folder holding the same %d B file coded "
          "and stored" % (len(blob), len(plain)))

    out = os.path.join(work, "ours")
    os.makedirs(out)
    rc, _cut = _ours(archive, out)
    for leaf in ("coded.txt", "stored.txt"):
        got = os.path.join(out, fold, leaf)
        ok = os.path.isfile(got) and open(got, "rb").read() == plain
        print("  ours   %-11s %s" % (leaf, "ok" if ok else "MISMATCH"))
        rc |= not ok

    img = run_selfextractor(work, name, ftype, creator, blob, rsrc, "stored")
    theirs = {"/".join(k): v[2] for k, v in read_forks(img).items()
              if k[-1] != name}
    bad = 0
    for leaf in ("coded.txt", "stored.txt"):
        got = theirs.pop("%s/%s" % (fold, leaf), None)
        state = ("MISSING" if got is None else
                 "made" if got == plain else "CONTENT DIFFERS")
        bad += state != "made"
        print("  theirs %-11s %s" % (leaf, state))
    for extra in sorted(theirs):
        print("  UNEXPECTED on the Mac: %s" % extra)
    print("superdisk: %s" % ("the Macintosh reads a stored block" if not bad
                             else "the Macintosh did NOT write %d of 2" % bad))
    print("superdisk: screenshots in %s" % os.path.join(SHOTS, "stored"))
    if keep:
        print("superdisk: kept %s" % work)
    else:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if (bad or rc) else 0


def _ours(archive, out):
    """Extract with our own CLI; return (paths written, {full: written})
    from the report the host prints for names that did not fit."""
    r = subprocess.run([cli(), "x", "--forks", "hidden", "-o", out, archive],
                       capture_output=True, text=True)
    cut, full = {}, None
    for line in (r.stdout + r.stderr).splitlines():
        if line.startswith("macextract:     written as "):
            if full is not None:
                cut[full] = line[len("macextract:     written as "):]
            full = None
        elif line.startswith("macextract:   ") and not line.endswith(":"):
            full = line[len("macextract:   "):]
    return r.returncode, cut


def nest(depth=10, keep=False):
    """Hand the format's own extractor a record stream written HERE.

    OPEN_ITEMS.md carried SuperDisk!'s path cap as untested code: the
    walk reaches `unc_path_leaf`'s 255-byte cap through a container
    nothing off the Macintosh reads, so a generated stream could only
    ever be graded against the transcription that wrote it. It can be
    graded against the archives' own self-extractor instead — the same
    second reader `--adjudicate` uses — by giving that application a
    data fork this project built.

    The Macintosh creates each component through the File Manager and
    never assembles a path, so **what it makes on the volume IS the
    uncut path**, which is exactly what `unc_path_leaf` reports when it
    cuts one.
    """
    from vmac_check import mask_reserved                # noqa: E402
    work = tempfile.mkdtemp(prefix="sdnest-")
    archive = os.path.join(work, "nest.x")
    name, ftype, creator, orig, rsrc = unwrap(
        os.path.join(REPO, "fixtures", "super-disk-utility.hqx"), work)
    blob, paths, dlen = synth_sd.nest(orig, depth)
    open(archive, "wb").write(blob)
    print("superdisk: a %d-deep record stream, %d B, %d files of %d B"
          % (depth, len(blob), len(paths), dlen))

    img = run_selfextractor(work, name, ftype, creator, blob, rsrc, "nest")
    theirs = read_forks(img)

    out = os.path.join(work, "ours")
    os.makedirs(out)
    rc, cut = _ours(archive, out)

    made = {}
    for path, (_ft, _cr, data, _rs) in theirs.items():
        if path[-1] == name:
            continue                                    # the application
        made["/".join(path)] = data
    want = None
    bad = 0
    for path in paths:
        got = made.pop(path, None)
        state = "made" if got is not None else "MISSING"
        if got is not None:
            if want is None:
                want = got
            if got != want or len(got) != dlen:
                state = "CONTENT DIFFERS"
        bad += state != "made"
        if len(path) <= 255:
            print("  %-14s %3d B path  %s" % (state, len(path), path[-40:]))
        else:
            # Past the cap: the host must have been told, and the uncut
            # path it was told must be the one the Macintosh built.
            told = path in cut
            bad += not told
            print("  %-14s %3d B path  uncut-reported=%-3s %s"
                  % (state, len(path), "yes" if told else "NO", path[-40:]))
    for extra in sorted(made):
        print("  UNEXPECTED on the Mac: %s" % extra)
        bad += 1
    for f in sorted(cut):
        if f not in paths and not any(p.startswith(f + "/") for p in paths):
            print("  a cut was reported for a path the archive does not "
                  "declare: %s" % f)
            bad += 1
    print("superdisk: %d file(s), %s" % (len(paths),
                                         "the Macintosh agrees" if not bad
                                         else "%d DISAGREE" % bad))
    print("superdisk: screenshots in %s" % os.path.join(SHOTS, "nest"))
    if keep:
        print("superdisk: kept %s" % work)
    else:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if (bad or rc) else 0


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
    ap.add_argument("--nest", action="store_true",
                    help="hand the self-extractor a deeply nested record "
                         "stream written here, and compare what it makes")
    ap.add_argument("--stored", action="store_true",
                    help="ask that extractor whether it reads a STORED "
                         "block, the one block shape no corpus archive has")
    ap.add_argument("--rootfile", action="store_true",
                    help="ask it whether a stream may OPEN with a file "
                         "record, which neither corpus archive does")
    ap.add_argument("--invented", action="store_true",
                    help="with --rootfile: guess the file record's fields "
                         "instead of copying them, and see what that costs")
    ap.add_argument("--depth", type=int, default=10,
                    help="how many 31-character folders to nest (default 10)")
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
    if a.nest:
        return nest(a.depth, a.keep)
    if a.stored:
        return stored_probe(a.keep)
    if a.rootfile:
        return rootfile_probe(a.keep, a.invented)
    if a.on_mac:
        return on_mac(a.mem, a.system)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

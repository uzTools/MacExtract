#!/usr/bin/env python3
"""pak.py — drive PAK 2.51 (NoGate Consulting, 1990) under DOSBox.

ARC methods 0x0a (Crushed) and 0x0b (Distilled) are PAK's, and PAK is
the only program that ever WROTE them: no Linux archiver does, and the
Macintosh side of this project never saw one. So the specimens that
grade fmt_arc.c come from the original DOS binary, run headless.

    tools/pak.py --setup        fetch DOSBox and PAK 2.51 (needs network)
    tools/pak.py --make DIR     write the generated corpus into DIR
    tools/pak.py --check DIR    extract it with the CLI and compare

Everything lands in $UNC_PAK_HOME (default ~/.cache/macextract/pak/), and
nothing here is committed: DOSBox is a Debian package, PAK is shareware.

Three things about this harness are worth knowing before changing it:

  - DOSBox needs no X server. SDL_VIDEODRIVER=dummy is enough, and the
    guest's console output is invisible either way, so every command
    redirects to a file INSIDE the guest when its text is wanted.
  - The distribution PAK251.EXE is a self-extracting PAK archive that
    asks "Continue? [Y/N]" and waits forever if nothing answers. The
    guest's own `<` redirection answers it; there is no host-side stdin
    to pipe into.
  - PAK picks a method per file unless told otherwise. `/CR` forces
    Crushed and `/O` forces Distilled ("only use Distill or Implode"),
    which is what makes a corpus that covers both.

Sources: PAK.DOC, sections "Crunch, Squash, and Crush (/C, /S, /CR)" and
"Only use Distill or Implode (/O)", from the distribution itself.
"""
import argparse
import hashlib
import os
import random
import shutil
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.environ.get("UNC_PAK_HOME",
                      os.path.expanduser("~/.cache/macextract/pak"))
DOS = os.path.join(HOME, "dos")          # the DOSBox C: drive
ROOTFS = os.path.join(HOME, "root")      # unpacked .deb tree

# 1990-10-08, the SIMTEL20 mirror textfiles.com serves.
PAK251_URL = ("http://cd.textfiles.com/simtel/simtel20/MSDOS/"
              "ARCHIVRS/PAK251.EXE")
# sha256 0a3195a3a23f4d95…, 103,338 B. Printed on every fetch rather than
# enforced: this is a tool, not a fixture, and a mirror serving a
# different build should be visible rather than fatal.


def dosbox_bin():
    """The DOSBox to use: the system one if there is one, else ours."""
    local = os.path.join(ROOTFS, "usr", "bin", "dosbox")
    if os.path.exists(local):
        return local
    return shutil.which("dosbox")


def have_pak():
    return os.path.exists(os.path.join(DOS, "PAK.EXE")) and dosbox_bin()


def run_dos(commands, drive=None, timeout=300):
    """Run commands at the DOS prompt with `drive` mounted as C:."""
    exe = dosbox_bin()
    if not exe:
        raise RuntimeError("no dosbox; run tools/pak.py --setup")
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["HOME"] = HOME
    lib = os.path.join(ROOTFS, "usr", "lib", "x86_64-linux-gnu")
    if os.path.isdir(lib):
        env["LD_LIBRARY_PATH"] = lib
    # `cycles=max` is worth setting: at DOSBox's default 3000 cycles the
    # 300 KB member takes minutes per method, and this guest does
    # nothing that cares about being period-accurate in SPEED.
    argv = [exe, "-noconsole", "-c", "config -set cpu cycles=max",
            "-c", "mount c %s" % (drive or DOS), "-c", "c:"]
    for c in commands:
        argv += ["-c", c]
    argv += ["-c", "exit"]
    return subprocess.run(argv, capture_output=True, timeout=timeout, env=env)


# --------------------------------------------------------------- setup

def apt_fetch(pkgs, into):
    os.makedirs(into, exist_ok=True)
    r = subprocess.run(["apt-get", "download"] + pkgs,
                       cwd=into, capture_output=True)
    # A 404 on one package of a hundred is normal (a point release moved
    # on); the build only needs the ones DOSBox actually dlopens.
    return r.returncode == 0 or any(f.endswith(".deb")
                                    for f in os.listdir(into))


def setup_dosbox():
    if dosbox_bin():
        print("pak: dosbox present at %s" % dosbox_bin())
        return True
    deb = os.path.join(HOME, "deb")
    r = subprocess.run(["apt-cache", "depends", "--recurse", "--no-recommends",
                        "--no-suggests", "--no-conflicts", "--no-breaks",
                        "--no-replaces", "--no-enhances", "dosbox"],
                       capture_output=True, text=True)
    pkgs = sorted({ln.strip() for ln in r.stdout.splitlines()
                   if ln and not ln.startswith((" ", "|"))
                   and not ln.startswith("<")})
    if not pkgs:
        pkgs = ["dosbox", "libsdl1.2debian", "libsdl-net1.2",
                "libsdl-sound1.2", "libpng16-16t64"]
    if not apt_fetch(pkgs, deb):
        print("pak: could not download dosbox", file=sys.stderr)
        return False
    os.makedirs(ROOTFS, exist_ok=True)
    for f in sorted(os.listdir(deb)):
        if f.endswith(".deb"):
            subprocess.run(["dpkg", "-x", os.path.join(deb, f), ROOTFS],
                           capture_output=True)
    ok = bool(dosbox_bin())
    print("pak: dosbox %s" % ("unpacked" if ok else "MISSING"))
    return ok


def fetch_pak():
    os.makedirs(DOS, exist_ok=True)
    sfx = os.path.join(DOS, "PAK251.EXE")
    if not os.path.exists(sfx):
        r = subprocess.run(["curl", "-sSL", "-o", sfx, PAK251_URL],
                           capture_output=True)
        if r.returncode != 0 or not os.path.exists(sfx):
            print("pak: could not fetch %s" % PAK251_URL, file=sys.stderr)
            return False
    print("pak: PAK251.EXE %d bytes, sha256 %s"
          % (os.path.getsize(sfx),
             hashlib.sha256(open(sfx, "rb").read()).hexdigest()[:16]))

    if os.path.exists(os.path.join(DOS, "PAK.EXE")):
        return True
    # The distribution is a self-extracting PAK archive. It asks before
    # doing anything, and the answer has to come from inside the guest.
    open(os.path.join(DOS, "ANS.TXT"), "w").write("Y\r\n")
    run_dos(["PAK251.EXE > SFX.LOG < ANS.TXT"])
    ok = os.path.exists(os.path.join(DOS, "PAK.EXE"))
    print("pak: PAK 2.51 %s" % ("unpacked" if ok else "MISSING"))
    return ok


# ---------------------------------------------------------- the corpus

def sample_inputs():
    """The files PAK is asked to compress. Deterministic, so a corpus
    made on one machine is the corpus made on another.

    Each one is here for a reason:

      TEXT.TXT  ordinary English prose, the case both methods were
                tuned for.
      REPEAT.TXT one sentence over and over. Its matches reach back
                past the start of the data into the window PAK
                pre-fills with SPACES, which is the case XADMaster
                gets wrong (DECISIONS.md) — without this file a
                decoder can be wrong and look right.
      RUNS.TXT  long runs of one byte, so the RLE90 filter Crushed
                chains sees something to do, including a literal 0x90.
      RAND.BIN  incompressible, which is what makes Crushed switch
                its code framing: literals dominate its 500-symbol
                window and the literal bit comes back.
      BIG.BIN   large and varied enough to fill Crushed's 8192-symbol
                table, which is the only way to reach the replacement
                scan at all.
      ONE.TXT / EMPTY.TXT  the degenerate lengths.
    """
    rnd = random.Random(20260825)
    words = ("the quick brown fox jumps over a lazy dog while pack my box "
             "with five dozen liquor jugs and waltz nymph for quick jigs "
             "vex bud").split()
    text = []
    for _ in range(400):
        text.append(" ".join(rnd.choice(words) for _ in range(rnd.randint(4, 12))))
    text = ("\r\n".join(text) + "\r\n").encode("ascii")

    repeat = b"The quick brown fox jumps over the lazy dog. " * 40

    runs = bytearray()
    for i in range(60):
        runs += bytes([65 + (i % 26)]) * (i * 7 + 3)
        runs += b"\x90\x90"                      # the escape byte itself
    runs += b"\r\n"

    rand = bytes(rnd.randrange(256) for _ in range(40000))

    big = bytearray()
    while len(big) < 300000:
        big += bytes(rnd.randrange(256) for _ in range(rnd.randint(3, 9)))
        big += text[rnd.randrange(0, max(1, len(text) - 200)):][:rnd.randint(10, 200)]

    return {
        "TEXT.TXT": text,
        "REPEAT.TXT": repeat,
        "RUNS.TXT": bytes(runs),
        "RAND.BIN": rand,
        "BIG.BIN": bytes(big),
        "ONE.TXT": b"x",
        "EMPTY.TXT": b"",
    }


# The archives to write: name -> (DOS 8.3 name, PAK options, members or
# None for all). The guest names are spelled out rather than derived,
# because deriving them from the host names collided at eight
# characters — and `PAK A` ADDS to an existing archive, so a collision
# does not overwrite, it silently merges two cases into one.
CORPUS = {
    "pak-crushed.pak":        ("CRUSH1.PAK", "/CR", None),
    "pak-distilled.pak":      ("DIST1.PAK",  "/O",  None),
    "pak-default.pak":        ("DEFAULT.PAK", "",   None),
    "pak-crushed-text.pak":   ("CRUSH2.PAK", "/CR",
                               ["TEXT.TXT", "REPEAT.TXT", "RUNS.TXT"]),
    "pak-distilled-text.pak": ("DIST2.PAK",  "/O",
                               ["TEXT.TXT", "REPEAT.TXT", "RUNS.TXT"]),
    "pak-crushed-big.pak":    ("CRUSH3.PAK", "/CR", ["BIG.BIN"]),
    "pak-distilled-big.pak":  ("DIST3.PAK",  "/O",  ["BIG.BIN"]),
}


def make(outdir):
    if not have_pak():
        print("pak: SKIPPED — no PAK 2.51 (run tools/pak.py --setup)")
        return 1
    work = os.path.join(HOME, "work")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    inputs = sample_inputs()
    for name, blob in inputs.items():
        open(os.path.join(work, name), "wb").write(blob)

    cmds = []
    for arch, (dosname, opt, members) in sorted(CORPUS.items()):
        names = members if members else sorted(inputs)
        cmds.append("PAK.EXE A %s %s %s" % (opt, dosname, " ".join(names)))
    shutil.copy(os.path.join(DOS, "PAK.EXE"), os.path.join(work, "PAK.EXE"))
    run_dos(cmds, drive=work)

    os.makedirs(outdir, exist_ok=True)
    made = 0
    for arch, (dosname, _opt, _members) in sorted(CORPUS.items()):
        src = os.path.join(work, dosname)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(outdir, arch))
            made += 1
        else:
            print("pak: %s was not written" % arch, file=sys.stderr)
    # The inputs go with them: a corpus nothing can be compared against
    # is not a corpus.
    ind = os.path.join(outdir, "input")
    os.makedirs(ind, exist_ok=True)
    for name, blob in inputs.items():
        open(os.path.join(ind, name), "wb").write(blob)
    print("pak: wrote %d archives to %s" % (made, outdir))
    return 0 if made == len(CORPUS) else 1


# ------------------------------------------------------------- reading

def members(path):
    """Walk one ARC/PAK archive: [(method, name, crc, usize)].

    The header layout is fmt_arc.c's, kept here so the harness can say
    which methods a generated archive actually holds without asking the
    thing under test.
    """
    d = open(path, "rb").read()
    off, out = 0, []
    while off + 29 <= len(d) and d[off] == 0x1A and d[off + 1] != 0:
        method = d[off + 1]
        name = d[off + 2:off + 15].split(b"\0")[0].decode("latin1")
        csize, _dt, _tm, crc = struct.unpack("<IHHH", d[off + 15:off + 25])
        usize = struct.unpack("<I", d[off + 25:off + 29])[0]
        out.append((method, name, crc, usize))
        off += 29 + csize
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--make", metavar="DIR")
    ap.add_argument("--list", metavar="ARCHIVE")
    args = ap.parse_args()

    if args.setup:
        os.makedirs(HOME, exist_ok=True)
        ok = setup_dosbox() and fetch_pak()
        return 0 if ok else 1
    if args.make:
        return make(args.make)
    if args.list:
        for m, name, crc, usize in members(args.list):
            print("method 0x%02x  %-14s %8d  crc %#06x" % (m, name, usize, crc))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

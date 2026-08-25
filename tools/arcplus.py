#!/usr/bin/env python3
"""arcplus.py — drive ARC+Plus 7.12 (SEA, 1991) under DOSBox.

ARC method 0x0a is two methods. PAK calls it Crushed; ARC 7.x calls it
Trimmed and means a different algorithm (tools/pak.py has the other
one). Nothing on Linux writes Trimmed either, so its archives come from
SEA's own DOS binary, run headless.

    tools/arcplus.py --setup        fetch ARC+Plus 7.12 (needs network)
    tools/arcplus.py --carve SFX -o OUT [--member NAME]
    tools/arcplus.py --make DIR     write the generated corpus into DIR
    tools/arcplus.py --list ARCHIVE

DOSBox itself comes from tools/pak.py, which is also where the runner
and the $UNC_PAK_HOME cache live; this module is the ARC 7 half.

Three things learned getting it to run, none of them guessable:

  - The distribution is a DOS self-extractor whose payload is an
    ordinary ARC archive. `--carve` finds it structurally — the offset
    where a header chain walks cleanly to the end-of-archive marker —
    so no third-party tool is needed to bootstrap.
  - `ARC.EXE` with no arguments pages its usage screen and waits for a
    keypress forever. Every command here redirects stdin from a file.
  - The DOS binaries are BOUND executables (an MZ program with an NE
    image behind it), so `file` calls them OS/2 and they run under
    DOSBox regardless. The one in `XARC.ZIP` really is OS/2-only.
"""
import argparse
import os
import struct
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pak                                          # noqa: E402

# ARC+Plus 7.12, ~1991-01-24, as textfiles.com serves it.
ARC712_URL = "http://cd.textfiles.com/svplatinum/CDR31/ARC712.ZIP"
DOS = os.path.join(pak.HOME, "arc7")


def members(path_or_bytes, base=0):
    """[(method, name, offset_of_payload, csize, usize, crc)] for one
    ARC/PAK archive. Informational items (0x14/0x15/0x16) are included:
    the caller wants to see them, since their presence is what says an
    archive is ARC 7's rather than PAK's."""
    d = (open(path_or_bytes, "rb").read() if isinstance(path_or_bytes, str)
         else path_or_bytes)
    off, out = base, []
    while off + 29 <= len(d) and d[off] == 0x1A and d[off + 1] != 0:
        m = d[off + 1]
        name = d[off + 2:off + 15].split(b"\0")[0].decode("latin1")
        csize, _dt, _tm, crc = struct.unpack("<IHHH", d[off + 15:off + 25])
        usize = struct.unpack("<I", d[off + 25:off + 29])[0]
        out.append((m, name, off + 29, csize, usize, crc))
        off += 29 + csize
    return out


def find_archive(blob):
    """The offset of the ARC archive embedded in a self-extractor.

    Structural, not a signature: an offset qualifies when its header
    chain walks to an end-of-archive marker at (or within two bytes of)
    the end of the file, having passed at least two members. A wrong
    offset fails within a header or two, so this is decisive rather
    than heuristic.
    """
    for off in range(0, len(blob) - 29):
        if blob[off] != 0x1A or blob[off + 1] in (0, 0x1A):
            continue
        p, n = off, 0
        while p + 29 <= len(blob) and blob[p] == 0x1A and blob[p + 1] != 0:
            csize = struct.unpack("<I", blob[p + 15:p + 19])[0]
            if csize > len(blob):
                break
            p += 29 + csize
            n += 1
            if n > 4096:
                break
        if (n >= 2 and p + 2 <= len(blob) and blob[p] == 0x1A
                and blob[p + 1] == 0 and len(blob) - (p + 2) <= 2):
            return off
    return None


def carve(sfx, out, member=None):
    blob = open(sfx, "rb").read()
    off = find_archive(blob)
    if off is None:
        print("arcplus: no archive found in %s" % sfx, file=sys.stderr)
        return 1
    arc = blob[off:]
    if member is None:
        open(out, "wb").write(arc)
        print("arcplus: carved %d bytes from offset %d" % (len(arc), off))
        return 0
    for m, name, at, csize, usize, _crc in members(arc):
        if name != member:
            continue
        if m != 0x02:
            print("arcplus: %s is method %#04x, not stored — this mode "
                  "copies bytes and does not decode" % (name, m),
                  file=sys.stderr)
            return 1
        open(out, "wb").write(arc[at:at + csize])
        print("arcplus: extracted %s (%d bytes)" % (name, csize))
        return 0
    print("arcplus: no member %s" % member, file=sys.stderr)
    return 1


# --------------------------------------------------------------- setup

def setup():
    os.makedirs(DOS, exist_ok=True)
    zp = os.path.join(DOS, "ARC712.ZIP")
    if not os.path.exists(zp):
        r = subprocess.run(["curl", "-sSL", "-o", zp, ARC712_URL],
                           capture_output=True)
        if r.returncode != 0 or not os.path.exists(zp):
            print("arcplus: could not fetch %s" % ARC712_URL, file=sys.stderr)
            return 1
    subprocess.run(["unzip", "-o", "-q", zp, "-d", DOS], capture_output=True)
    sfx = os.path.join(DOS, "ARC712.EXE")
    if not os.path.exists(sfx):
        print("arcplus: ARC712.EXE not in the distribution", file=sys.stderr)
        return 1

    outer = os.path.join(DOS, "ARC712.arc")
    if carve(sfx, outer) != 0:
        return 1
    # The DOS binaries are in a nested archive, stored, so carving it out
    # needs no decoder either.
    inner = os.path.join(DOS, "ARCDOS.arc")
    if carve(sfx, inner, member="ARCDOS.ARC") != 0:
        return 1

    # ARC.EXE itself is Trimmed-compressed inside that one, so THIS is
    # the step that needs a decoder — our own, which is the method under
    # test. That is fine for a bootstrap and not for grading: what
    # grades the decoder is deark, the archives' own CRCs, and the
    # plain copy of XARC.EXE another CD carries (TESTING.md).
    cli = os.path.join(ROOT, "build", "rel", "unclassic")
    if not os.path.exists(cli):
        cli = os.path.join(ROOT, "build", "unclassic")
    if not os.path.exists(cli):
        print("arcplus: no CLI built; run `make BUILD=build/rel`", file=sys.stderr)
        return 1
    r = subprocess.run([cli, "x", "-o", DOS, inner], capture_output=True)
    ok = os.path.exists(os.path.join(DOS, "ARC.EXE"))
    print("arcplus: ARC+Plus 7.12 %s" % ("unpacked" if ok else "MISSING"))
    return 0 if ok else 1


def have_arc7():
    return os.path.exists(os.path.join(DOS, "ARC.EXE")) and pak.dosbox_bin()


# ---------------------------------------------------------- the corpus

# ARC 7 chooses Trimmed for anything it can shrink and stores the rest,
# and has no switch to force it, so the corpus is shaped by its inputs
# rather than by options. They are pak.py's, deliberately: the two
# formats are then graded on the same bytes.
CORPUS = {
    "arc7-all.arc":    ("ALL.ARC", None),
    "arc7-text.arc":   ("TEXT.ARC", ["TEXT.TXT", "REPEAT.TXT", "RUNS.TXT"]),
    "arc7-big.arc":    ("BIG.ARC", ["BIG.BIN"]),
}


def make(outdir):
    if not have_arc7():
        print("arcplus: SKIPPED — no ARC+Plus (run tools/arcplus.py --setup)")
        return 1
    work = os.path.join(pak.HOME, "arc7work")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    inputs = pak.sample_inputs()
    for name, blob in inputs.items():
        open(os.path.join(work, name), "wb").write(blob)
    open(os.path.join(work, "KEYS.TXT"), "w").write("\r\n" * 4)
    shutil.copy(os.path.join(DOS, "ARC.EXE"), os.path.join(work, "ARC.EXE"))

    cmds = []
    for arch, (dosname, sel) in sorted(CORPUS.items()):
        names = sel if sel else sorted(inputs)
        cmds.append("ARC.EXE A %s %s > NUL < KEYS.TXT" % (dosname, " ".join(names)))
    pak.run_dos(cmds, drive=work, timeout=900)

    os.makedirs(outdir, exist_ok=True)
    made = 0
    for arch, (dosname, _sel) in sorted(CORPUS.items()):
        src = os.path.join(work, dosname)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(outdir, arch))
            made += 1
        else:
            print("arcplus: %s was not written" % arch, file=sys.stderr)
    ind = os.path.join(outdir, "input")
    os.makedirs(ind, exist_ok=True)
    for name, blob in inputs.items():
        open(os.path.join(ind, name), "wb").write(blob)
    print("arcplus: wrote %d archives to %s" % (made, outdir))
    return 0 if made == len(CORPUS) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--carve", metavar="SFX")
    ap.add_argument("--member")
    ap.add_argument("-o", metavar="OUT")
    ap.add_argument("--make", metavar="DIR")
    ap.add_argument("--list", metavar="ARCHIVE")
    args = ap.parse_args()

    if args.setup:
        return setup()
    if args.carve:
        if not args.o:
            print("arcplus: --carve needs -o", file=sys.stderr)
            return 1
        return carve(args.carve, args.o, args.member)
    if args.make:
        return make(args.make)
    if args.list:
        for m, name, _at, csize, usize, crc in members(args.list):
            kind = " (item)" if m in (0x14, 0x15, 0x16) else ""
            print("method %#04x  %-14s %8d -> %8d  crc %#06x%s"
                  % (m, name, csize, usize, crc, kind))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

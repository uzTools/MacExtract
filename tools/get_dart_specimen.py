#!/usr/bin/env python3
"""get_dart_specimen.py — one A/UX 3.0.1 DART archive, out of the StuffIt
it travels in.

Two of the four disks of Apple's A/UX 3.0.1 retail floppy set are the
only DART archives this project has that Apple's own tool wrote in the
"best" method AND that nobody here chose the contents of: an 800K *Read
Me* disk and a 1.4 MB *Installation Boot Disk*. The second is the only
72-slot archive the corpus has ever held, which is the one place a disk's
SIZE changes a DART's layout (FORMATS.md, *DART*).

They are reachable in exactly one place — a `.sit` on Macintosh Garden's
own FTP repository — so `fixtures/SOURCES.md` names this script as their
provenance, `synthetic:tools/get_dart_specimen.py <disk>`, and
`tools/harvest.py --restore` rebuilds them through it. The disk is named
by a one-word key rather than by its name inside the archive, because
both of those have spaces in them and the `synthetic:` line is split on
whitespace.

**The member is unpacked by THIS ENGINE's CLI**, which is the point: the
SHA-256s below were pinned by MacMount's `tools/get_real_samples.py` from
`unar`'s output, so a StuffIt 5 walk that gets one byte wrong here does
not produce a fixture, it produces a failure. `unar` is used only when no
`macextract` binary has been built yet.

The wrapper is taken from `reference/macgarden/` when that is present
(tools/fetch_references.sh puts it there); otherwise it is downloaded to
`build/` and cached, because two members come out of the one archive.
With neither — a fresh clone with no network — it exits **3**, which
`tools/check_docs.py` reports as a skipped row rather than a failure.
Every other exit code is a real failure.

Be sparing with that host: public credentials, one volunteer's bandwidth.

    tools/get_dart_specimen.py readme -o fixtures/x.dart
    tools/get_dart_specimen.py --show bootdisk
"""
import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
NAME = "APPLE_AUX_3-0-1_RETAIL_FLOPPY_IMAGES_DART.sit"
REF = os.path.join(ROOT, "reference", "macgarden", NAME)
CACHE = os.path.join(ROOT, "build", NAME)
URL = "ftp://mirror:mirror@ftp.macintosh.garden/apps/" + NAME

# The two disks: key, the name the member carries inside the archive,
# and the SHA-256 MacMount pinned for it (tools/get_real_samples.py
# there). The archive holds two more — `Installation Boot Disk SE.dart`
# (480,641 B, 800K) and `Read Me For quadra & cen.dart` (1,011,073 B,
# 1440K) — which are the same two shapes again and are left where they
# are: one disk of each geometry is what the 40/72-slot split needs.
DISKS = {
    "readme": ("Read Me Mac SE.dart",
               "a6207871a1d795622bd4b2a9c8b7f710e0dd893cda9a1885b5d01a1bba10dff3"),
    "bootdisk": ("Installation Boot Disk Qua.dart",
                 "45c2af73cd0c33eeddd09a73e0171aea11e6455ce9ef1e8294f235cbd0df64be"),
}


def archive():
    """The wrapper's bytes, or None when it cannot be had."""
    for path in (REF, CACHE):
        if os.path.exists(path):
            return open(path, "rb").read()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    r = subprocess.run(["curl", "-sSL", "-f", "--connect-timeout", "30",
                        "-o", CACHE, URL])
    if r.returncode != 0 or not os.path.exists(CACHE):
        if os.path.exists(CACHE):
            os.remove(CACHE)
        return None
    return open(CACHE, "rb").read()


def unpacker(explicit):
    """(argv builder, label) for whatever can open a StuffIt 5 here."""
    if explicit:
        return explicit, "macextract"
    for rel in ("build/rel/macextract", "build/san/macextract",
                "build/macextract"):
        path = os.path.join(ROOT, rel)
        if os.path.exists(path):
            return path, "macextract"
    tool = shutil.which("unar")
    return (tool, "unar") if tool else (None, None)


def member(data, want, tool, kind, forks):
    """One member's data fork — and, with `forks`, its resource fork.

    Matched on the BASENAME because both unpackers decide the directory
    they write into, and this archive keeps its members in two of them
    (`DMd3/DART` and `DMd6/DART`, the Finder folders of the floppy set).
    """
    with tempfile.TemporaryDirectory() as tmp:
        arc = os.path.join(tmp, "archive.sit")
        open(arc, "wb").write(data)
        out = os.path.join(tmp, "out")
        os.makedirs(out)
        if kind == "macextract":
            argv = [tool, "x", arc, "-o", out]
        else:
            argv = [tool, "-nr", "-D", "-f", "-q", "-k", "skip", "-o", out,
                    arc]
        subprocess.run(argv, capture_output=True, timeout=300)
        for root, _dirs, files in os.walk(out):
            if want in files:
                path = os.path.join(root, want)
                fork = None
                if forks and os.path.exists(path + ".rsrc"):
                    fork = open(path + ".rsrc", "rb").read()
                return open(path, "rb").read(), fork
    return None, None


def resources(fork):
    """(type, id) -> data, out of a classic resource fork. The same few
    fields tools/run_dart.py reads; not a general reader."""
    do, mo = struct.unpack_from(">II", fork, 0)
    tlo = struct.unpack_from(">H", fork, mo + 24)[0]
    ntypes = struct.unpack_from(">H", fork, mo + tlo)[0] + 1
    out = {}
    for i in range(ntypes):
        off = mo + tlo + 2 + i * 8
        t = fork[off:off + 4].decode("mac_roman")
        n = struct.unpack_from(">H", fork, off + 4)[0] + 1
        ro = struct.unpack_from(">H", fork, off + 6)[0]
        for j in range(n):
            e = mo + tlo + ro + j * 12
            rid = struct.unpack_from(">h", fork, e)[0]
            dofs = struct.unpack_from(">I", fork, e + 4)[0] & 0xFFFFFF
            dlen = struct.unpack_from(">I", fork, do + dofs)[0]
            out[(t, rid)] = fork[do + dofs + 4:do + dofs + 4 + dlen]
    return out


def show(fork):
    """What DART itself recorded about the disk, out of the member's
    resource fork: 'CKSM' 1 (tags), 'CKSM' 2 (data), and the 'DART' 0
    Pascal string the application spelled both into in 1993. This is
    where the constants tools/run_dart.py grades against come from."""
    if fork is None:
        print("no resource fork came out (unar was the unpacker, or the "
              "member has none)")
        return 1
    res = resources(fork)
    for rid, what in ((1, "tags"), (2, "data")):
        got = res.get(("CKSM", rid))
        print("'CKSM' %d (%s): %s" % (rid, what, "%08X" % struct.unpack(
            ">I", got)[0] if got else "absent"))
    got = res.get(("DART", 0))
    if got:
        print("'DART' 0: %s" % got[1:1 + got[0]].decode("mac_roman"))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("disk", choices=sorted(DISKS),
                    help="which of the two disks to take")
    ap.add_argument("-o", "--output")
    ap.add_argument("--macextract", help="the CLI to unpack with")
    ap.add_argument("--show", action="store_true",
                    help="print the checksums DART recorded, and stop")
    args = ap.parse_args()
    if not args.output and not args.show:
        ap.error("-o is required unless --show is given")

    tool, kind = unpacker(args.macextract)
    if tool is None:
        print("get_dart_specimen: nothing here can open a StuffIt 5 — "
              "build the CLI (make) or install unar", file=sys.stderr)
        return 3
    data = archive()
    if data is None:
        print("get_dart_specimen: no reference/macgarden/%s and the FTP "
              "will not answer" % NAME, file=sys.stderr)
        return 3

    want, pin = DISKS[args.disk]
    blob, fork = member(data, want, tool, kind, args.show)
    if blob is None:
        print("get_dart_specimen: %s (unpacked by %s) has no member %r"
              % (NAME, kind, want), file=sys.stderr)
        return 1
    got = hashlib.sha256(blob).hexdigest()
    if got != pin:
        print("get_dart_specimen: %r came out as %d B / %s, pinned as %s"
              % (want, len(blob), got[:12] + "…", pin[:12] + "…"),
              file=sys.stderr)
        return 1
    if args.show:
        return show(fork)
    open(args.output, "wb").write(blob)
    return 0


if __name__ == "__main__":
    sys.exit(main())

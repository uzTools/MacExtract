#!/usr/bin/env python3
"""run_ddtf.py — DiskDoubler graded against the bytes that went in.

`ssokolow/diskdoubler-test-files` (CC0) is nine sets of the same seven
small files, compressed on a real Power Mac G4 by DiskDoubler 3.7.7 and
DiskDoubler Pro 4.1.1 in every method their menus offer, published
BESIDE the originals. That is what makes it the only DiskDoubler
grading here that does not go through another decoder: the oracle is
the source file, not `unar`'s opinion of the archive.

    tools/run_ddtf.py --fetch                 # clone to /tmp, then check
    tools/run_ddtf.py --corpus /path/to/clone

It checks four things and fails on any mismatch:

  * 63 single-file `0xABCD0054` containers  (7 files x 9 methods)
  * 9 `DDAR` / `DDA2` archives
  * 10 self-extractors, and the same 10 BinHexed
  * every extracted fork against the published original, byte for byte

`testfile.TIF` has no published original — it was made on the Mac — so
it is checked for agreement across all nine independent compressions
instead, forks included.

What it CANNOT see: dates, type/creator and Finder flags (the corpus
publishes the forks, and its AppleDouble sidecars carry a Finder info
block the Mac rewrote on copy); the five methods no shipping
DiskDoubler menu offers; and anything about `SPLT`, whose four
specimens this script skips because nothing here reads them yet
(OPEN_ITEMS.md).
"""
import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://github.com/ssokolow/diskdoubler-test-files.git"

# The seven files in every set. testfile.TIF is the one with no original.
NAMES = ["Test Image", "Test Text", "testfile.PICT", "testfile.TIF",
         "testfile.jpg", "testfile.png", "testfile.txt"]
NO_ORIGINAL = "testfile.TIF"


def ad_rsrc(path):
    """The resource fork out of an AppleDouble sidecar."""
    with open(path, "rb") as fh:
        d = fh.read()
    if len(d) < 26 or struct.unpack_from(">I", d, 0)[0] != 0x00051607:
        raise ValueError("%s is not AppleDouble" % path)
    n = struct.unpack_from(">H", d, 24)[0]
    for i in range(n):
        eid, off, ln = struct.unpack_from(">III", d, 26 + i * 12)
        if eid == 2:
            return d[off:off + ln]
    return b""


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


class Check(object):
    def __init__(self):
        self.ok = 0
        self.bad = []

    def eq(self, what, got, want):
        if got == want:
            self.ok += 1
        else:
            self.bad.append("%s: %d bytes, expected %d"
                            % (what, len(got), len(want)))


def extract(cli, archive, out):
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([cli, "x", "--forks", "hidden", "-o", out, archive],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.returncode, r.stderr.decode("utf-8", "replace").strip()


def find_root(top):
    """Descend through single-directory levels to where the files are."""
    root = top
    for _ in range(4):
        ents = os.listdir(root)
        if len(ents) == 1 and os.path.isdir(os.path.join(root, ents[0])):
            root = os.path.join(root, ents[0])
        else:
            return root
    return root


def check_set(chk, root, srcdir, label, tif):
    """Compare an extracted set of the seven files with the originals."""
    for name in NAMES:
        got = os.path.join(root, name)
        if not os.path.exists(got):
            chk.bad.append("%s: %s missing" % (label, name))
            continue
        rsrc = os.path.join(root, "._" + name)
        gotr = read(rsrc) if os.path.exists(rsrc) else b""
        if name == NO_ORIGINAL:
            tif.setdefault("data", set()).add(hashlib.sha256(read(got)).hexdigest())
            tif.setdefault("rsrc", set()).add(hashlib.sha256(gotr).hexdigest())
            continue
        chk.eq("%s: %s" % (label, name), read(got), read(os.path.join(srcdir, name)))
        orig = os.path.join(srcdir, "._" + name)
        chk.eq("%s: %s rsrc" % (label, name), gotr,
               ad_rsrc(orig) if os.path.exists(orig) else b"")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--unclassic", default=os.path.join(REPO, "build", "unclassic"))
    ap.add_argument("--corpus", default="/tmp/diskdoubler-test-files")
    ap.add_argument("--fetch", action="store_true",
                    help="git clone the corpus to --corpus first")
    args = ap.parse_args()

    if args.fetch:
        if os.path.exists(args.corpus):
            shutil.rmtree(args.corpus)
        subprocess.check_call(["git", "clone", "--depth", "1", URL, args.corpus])
    build = os.path.join(args.corpus, "build")
    srcdir = os.path.join(args.corpus, "sources")
    if not os.path.isdir(build):
        sys.exit("no corpus at %s — pass --fetch or --corpus" % args.corpus)

    chk = Check()
    tif_single, tif_arc, tif_sea = {}, {}, {}
    tmp = tempfile.mkdtemp(prefix="ddtf-")
    try:
        variants = sorted(d for d in os.listdir(build)
                          if os.path.isdir(os.path.join(build, d)))
        # 1. the single-file container, one directory per method
        singles = 0
        for v in variants:
            for name in sorted(os.listdir(os.path.join(build, v))):
                out = os.path.join(tmp, "one", v, name)
                rc, err = extract(args.unclassic, os.path.join(build, v, name), out)
                if rc != 0:
                    chk.bad.append("%s/%s: %s" % (v, name, err))
                    continue
                singles += 1
                # The container carries no name; the host's supplies one,
                # and the CLI drops the extension it arrived with.
                stem = name.rsplit(".", 1)[0] if "." in name else name
                got = os.path.join(out, stem)
                rsrc = os.path.join(out, "._" + stem)
                gotr = read(rsrc) if os.path.exists(rsrc) else b""
                if name == NO_ORIGINAL:
                    tif_single.setdefault("data", set()).add(
                        hashlib.sha256(read(got)).hexdigest())
                    tif_single.setdefault("rsrc", set()).add(
                        hashlib.sha256(gotr).hexdigest())
                    continue
                chk.eq("%s/%s" % (v, name), read(got),
                       read(os.path.join(srcdir, name)))
                orig = os.path.join(srcdir, "._" + name)
                chk.eq("%s/%s rsrc" % (v, name), gotr,
                       ad_rsrc(orig) if os.path.exists(orig) else b"")

        # 2. the archives, and 3. the self-extractors with and without BinHex
        archives, seas = 0, 0
        for name in sorted(os.listdir(build)):
            path = os.path.join(build, name)
            if not os.path.isfile(path) or name.startswith("._"):
                continue
            if name.endswith(".dd"):
                kind, tif = "archive", tif_arc
            elif name.endswith(".sea") or name.endswith(".sea.hqx"):
                kind, tif = "sea", tif_sea
            else:
                continue                      # .sit wrappers, .dd.1/.2 SPLT
            out = os.path.join(tmp, kind, name)
            rc, err = extract(args.unclassic, path, out)
            if rc != 0:
                chk.bad.append("%s: %s" % (name, err))
                continue
            if kind == "archive":
                archives += 1
            else:
                seas += 1
            check_set(chk, find_root(out), srcdir, name, tif)

        for what, seen in (("single-file", tif_single), ("archive", tif_arc),
                           ("self-extractor", tif_sea)):
            for fork, hashes in sorted(seen.items()):
                if len(hashes) != 1:
                    chk.bad.append("%s %s of %s differs across methods: %d hashes"
                                   % (NO_ORIGINAL, fork, what, len(hashes)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("ddtf: %d single-file containers, %d archives, %d self-extractors"
          % (singles, archives, seas))
    print("ddtf: %d forks compared with the published originals, %d mismatched"
          % (chk.ok, len(chk.bad)))
    for line in chk.bad:
        print("  FAIL " + line)
    return 1 if chk.bad else 0


if __name__ == "__main__":
    sys.exit(main())

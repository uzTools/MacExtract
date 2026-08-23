#!/usr/bin/env python3
"""get_lhasa_fixture.py — one archive out of lhasa's test collection.

`fixtures/SOURCES.md` records every fixture as something re-fetchable,
and these seven come out of a tarball rather than off a URL of their
own: lhasa (Simon Howard) ships ~160 `.lzh` archives written by fourteen
different LHA implementations, and they are the only specimens of the
format this project has beyond one Amiga file. SOURCES.md names this
script as their provenance, `synthetic:tools/get_lhasa_fixture.py <member>`.

The member is taken from `reference/lhasa/` when that is present
(tools/fetch_references.sh puts it there); otherwise the tarball is
downloaded to `build/` and cached. With neither — a fresh clone with no
network — it exits **3**, which `tools/check_docs.py` reports as a
skipped row rather than a failure. Every other exit code is a real
failure.

    tools/get_lhasa_fixture.py maclha_224/l1_lh5.lzh -o fixtures/x.lzh
"""
import argparse
import os
import shutil
import subprocess
import sys
import tarfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REF = os.path.join(ROOT, "reference", "lhasa", "test", "archives")
TARBALL = os.path.join(ROOT, "build", "lhasa-0.4.0.tar.xz")
URL = ("http://deb.debian.org/debian/pool/main/l/lhasa/"
       "lhasa_0.4.0.orig.tar.xz")
PREFIX = "lhasa-0.4.0/test/archives/"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("member", help="path under test/archives, e.g. "
                                   "maclha_224/l1_lh5.lzh")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()

    local = os.path.join(REF, args.member)
    if os.path.exists(local):
        shutil.copyfile(local, args.output)
        return 0

    if not os.path.exists(TARBALL):
        os.makedirs(os.path.dirname(TARBALL), exist_ok=True)
        r = subprocess.run(["curl", "-sSL", "-f", "-o", TARBALL, URL])
        if r.returncode != 0 or not os.path.exists(TARBALL):
            print("get_lhasa_fixture: no reference/lhasa and the tarball "
                  "will not download", file=sys.stderr)
            return 3
    with tarfile.open(TARBALL) as tf:
        with tf.extractfile(PREFIX + args.member) as src:
            with open(args.output, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())

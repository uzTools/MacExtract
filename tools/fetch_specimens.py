#!/usr/bin/env python3
"""fetch_specimens.py — the specimens this project downloads rather than makes.

Three sets are graded against files that no emulator here can produce
and that may not be committed (copyrighted, like everything in
`fixtures/`). All were found on Discmaster, which indexes the contents
of archived CD-ROMs and disk images and serves each file raw; the tables
beside this script record size, sha256 and URL for every one.

    tools/fetch_specimens.py                 fetch what is missing
    tools/fetch_specimens.py --check         verify what is present
    tools/fetch_specimens.py --only spacesaver

  spacesaver  48 files SpaceSaver itself wrote, 46 of them with the
              uncompressed ORIGINAL beside them — a second copy of the
              same file from a CD pressed before that machine had
              SpaceSaver on it. `tools/run_spacesaver.py` grades them
              (TESTING.md).
  applelink   eight AppleLink packages, between them reaching every path
              the format has (FORMATS.md, *What the eight real packages
              exercise*). `tools/run_sqp.py` grades the engine on them,
              `tools/derive_sqp.py` the reading.
  zipit       9 archives ZipIt itself wrote — five self-extracting, four
              a plain `.zip`. `tools/run_zipit.py` grades them
              (TESTING.md).

How they were found, and how to find more, is DECISIONS.md 2026-09-26
(the magic in somebody else's index).
"""
import argparse
import hashlib
import os
import sys
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SETS = {
    # set name    table                     directory under HOME/specimens
    "spacesaver": ("spacesaver.tsv", "spacesaver"),
    "applelink":  ("applelink.tsv", "applelink"),
    "zipit":      ("zipit.tsv", "zipit"),
}
# `run_spacesaver.py` wants NAME.ss and NAME.ss.orig beside each other.
SUFFIX = {"ss": ".ss", "orig": ".ss.orig", "pkg": "",
          "sea": ".sea", "zip": ".zip"}


def table(name):
    path = os.path.join(REPO, "tools", "specimens", SETS[name][0])
    for line in open(path, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        stem, role, size, sha, url = line.rstrip("\n").split("\t")
        yield stem + SUFFIX[role], int(size), sha, url


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=sorted(SETS), action="append")
    ap.add_argument("--check", action="store_true",
                    help="do not download; report what is present and whether "
                         "it still hashes correctly")
    a = ap.parse_args()

    bad = got = had = missing = 0
    for name in (a.only or sorted(SETS)):
        out = os.path.join(HOME, "specimens", SETS[name][1])
        if not a.check:
            os.makedirs(out, exist_ok=True)
        for fname, size, sha, url in table(name):
            path = os.path.join(out, fname)
            if os.path.exists(path):
                blob = open(path, "rb").read()
            elif a.check:
                missing += 1
                continue
            else:
                try:
                    with urllib.request.urlopen(url, timeout=120) as r:
                        blob = r.read()
                except Exception as e:          # network, 404, anything
                    print("specimens: %s: %s" % (fname, e))
                    bad += 1
                    continue
                open(path, "wb").write(blob)
                got += 1
            if len(blob) != size or hashlib.sha256(blob).hexdigest() != sha:
                print("specimens: %s: %d bytes, sha256 %s — expected %d/%s"
                      % (fname, len(blob), hashlib.sha256(blob).hexdigest(),
                         size, sha))
                bad += 1
            elif os.path.exists(path):
                had += 1
    print("specimens: %d fetched, %d already correct, %d missing, "
          "%d failure(s)" % (got, had - got, missing, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""check_mac_select.py <all-dir> <even-dir> <odd-dir>

Grade selective extraction on the property it actually has to hold:
extracting the even-numbered entries and extracting the odd-numbered
ones must produce two DISJOINT sets of files whose union is, byte for
byte, what extracting the whole archive produces.

That is what "the entries the user ticked, and no others" means, and it
is the wording that matters: a shell that ignored the choice and
extracted everything fails the disjointness half, and one that skipped
too much fails the union half. Either alone can be passed by accident.

Folders are not compared: an unticked folder ENTRY is still created when
a ticked entry inside it needs it, which is correct and not a file.
"""
import hashlib, os, sys


def tree(root):
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(dirpath, f)
            out[os.path.relpath(p, root)] = p
    return out


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    alld, evend, oddd = (tree(a) for a in sys.argv[1:4])
    # The archive's own comment belongs to the archive rather than to any
    # entry: the shell writes it out on whichever walk extracts, so both
    # halves carry it and it is not part of what was chosen.
    for t in (alld, evend, oddd):
        t.pop("Comments", None)
    bad = 0
    both = set(evend) & set(oddd)
    for p in sorted(both):
        print(f"  IN BOTH HALVES: {p}")
        bad += 1
    union = dict(evend)
    union.update(oddd)
    for p in sorted(set(alld) - set(union)):
        print(f"  MISSING from both halves: {p}")
        bad += 1
    for p in sorted(set(union) - set(alld)):
        print(f"  EXTRA, in no whole extraction: {p}")
        bad += 1
    for p in sorted(set(alld) & set(union)):
        if sha(alld[p]) != sha(union[p]):
            print(f"  BYTES DIFFER: {p}")
            bad += 1
    if bad:
        print(f"mac-select: {bad} problem(s)")
        return 1
    # A split that put everything on one side would pass the three tests
    # above and mean nothing, so the halves have to be halves.
    if not evend or not oddd:
        print("mac-select: one half is empty — the choice did nothing")
        return 1
    print(f"mac-select: OK — {len(evend)} + {len(oddd)} files, disjoint, "
          f"union = {len(alld)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

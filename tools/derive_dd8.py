#!/usr/bin/env python3
"""derive_dd8.py — measure the two facts DiskDoubler method 8 rests on.

`src/unc_internal.h` says, citing `XADDiskDoublerParser.m` case 8, that
DiskDoubler method 8 IS Compact Pro's two decode stages, and that its
Huffman block is 0xfff0 where Compact Pro's is 0x1fff0.  Both were
transcribed.  Neither has to be: a method-8 fork decoded with those
stages at that block size either reproduces the bytes an independent
oracle recorded for it, or it does not.

So this decodes every method-8 fork in the corpus with the Compact Pro
reader `tools/derive_cpt.py` already provides — which is written from
The Unarchiver's three published wiki pages and from nothing else, not
from XADMaster — and sweeps the block size across a grid.  The claim
is measured if exactly one block size works and it is the stated one.

What it CANNOT see: whether some OTHER pair of stages would also
reproduce these forks.  It measures that Compact Pro's stages suffice,
not that nothing else would.  It also says nothing about method 8 in
archives this corpus does not have.

    tools/derive_dd8.py [--fixture NAME ...] [-v]

Not in `ci.sh`: it needs the fixtures, which are not committed.  It
skips cleanly without them.
"""

import argparse
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import derive_cpt as CPT      # the stages, from the published pages
import derive_ddc as DDC      # the container, from this project's own

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "fixtures")

# The grid runs DOWN as well as up, and that is the point. A block
# size larger than the cost the stream ever reaches never flushes, so
# every such size decodes identically and pins nothing. A size SMALLER
# than that cost makes the decoder look for a tree that is not there,
# and fails. The largest failing size therefore measures how much cost
# these streams actually reach — which is what says whether the corpus
# can pin 0xfff0 at all.
GRID = [0x100, 0x400, 0x1000, 0x2000, 0x3FF0, 0x7FF0, 0xBFF0,
        0xFFF0, 0x13FF0, 0x1FFF0, 0x3FFF0]
CLAIMED = 0xFFF0
DD8_PREFIX = 16                # the sum-selector before the coder


def forks(path):
    """Every method-8 fork: (name, kind, offset, complen, outlen, sha)."""
    man = os.path.join(FIX, "manifests", os.path.basename(path) + ".json")
    if not os.path.exists(man):
        return []
    byname = {}
    for e in json.load(open(man))["entries"]:
        byname[e["name"]] = e

    d = open(path, "rb").read()
    shape, ents = DDC.read_container(d, os.path.basename(path))
    if not ents:
        return []

    out = []
    for e in ents:
        if e.get("is_dir") or e.get("stored"):
            continue
        if not e.get("path") or any(x is None for x in e["path"]):
            continue          # an end-of-directory record carries no name
        name = b"/".join(e["path"]).decode("mac-roman")
        leaf = e["path"][-1].decode("mac-roman")
        m = byname.get(name) or byname.get(leaf)
        if not m:
            continue
        # The data fork's compressed bytes come first, then the
        # resource fork's (docs/formats/diskdoubler-container.md).
        at = e["payload"]
        for kind in ("data", "rsrc"):
            comp = e[kind + "_comp"]
            if e[kind + "_method"] == 8 and comp and m.get(kind + "_size"):
                out.append((name, kind, at, comp,
                            m[kind + "_size"], m[kind + "_sha256"]))
            at += comp
    return out


def decode(d, at, comp, nout, blocksize):
    """Compact Pro's coder, at one block size.

    The two stages are FUSED in the published reading — `lzh` sinks
    through an `Rle` object rather than returning an intermediate — so
    this is one call, not two (`tools/derive_cpt.py`, check).

    The 16 bytes before it are the container's, not the coder's: a
    method-8 fork opens with sixteen bytes whose SUM selects the path,
    zero meaning the LZH coder. Every method-8 fork in reach sums to
    zero. That framing is docs/formats/diskdoubler-container.md's.
    """
    return CPT.lzh(d, at + DD8_PREFIX, nout, blocksize=blocksize)[:nout]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", action="append", default=[])
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(FIX, "*.dd")))
    if a.fixture:
        paths = [p for p in paths
                 if os.path.basename(p) in a.fixture]
    if not paths:
        print("derive-dd8: no .dd fixtures here — skipped")
        return 0

    works = {b: 0 for b in GRID}
    floors = []
    total = 0
    archives = 0
    failures = []

    for p in paths:
        fs = forks(p)
        if not fs:
            continue
        archives += 1
        d = open(p, "rb").read()
        for name, kind, at, comp, nout, sha in fs:
            total += 1
            hit = []
            for bs in GRID:
                try:
                    out = decode(d, at, comp, nout, bs)
                except Exception:
                    continue
                if len(out) == nout and hashlib.sha256(out).hexdigest() == sha:
                    hit.append(bs)
                    works[bs] += 1
            if a.verbose or not hit:
                print("  %-34s %-4s %6d B  %s"
                      % (name, kind, nout,
                         ", ".join("0x%X" % b for b in hit) or "NONE"))
            if not hit:
                failures.append((os.path.basename(p), name, kind))
            else:
                miss = [b for b in GRID if b < min(hit)]
                if miss:
                    floors.append((nout, max(miss)))

    if not total:
        print("derive-dd8: no method-8 forks in reach — skipped")
        return 0

    print("derive-dd8: %d method-8 fork(s) in %d archive(s), decoded with "
          "Compact Pro's two stages" % (total, archives))
    for bs in GRID:
        mark = "  <- the citation's" if bs == CLAIMED else ""
        print("            0x%-6X %3d/%d%s" % (bs, works[bs], total, mark))

    ok = works[CLAIMED] == total
    alone = [b for b in GRID if works[b] == total]
    if ok and alone == [CLAIMED]:
        print("            MEASURED: Compact Pro's stages read every one, "
              "and 0x%X is the only block size in the grid that does."
              % CLAIMED)
        return 0
    if ok:
        top = max((f for _, f in floors), default=0)
        big = max((n for n, _ in floors), default=0)
        print("            PARTIAL: 0x%X reads every fork, and so does every "
              "other size at or above 0x%X."
              % (CLAIMED, min(alone)))
        print("            The corpus cannot pin it: the largest block size "
              "that FAILS anywhere is 0x%X, so no stream here reaches even "
              "that much cost, and every size above it never flushes. The "
              "biggest method-8 fork in reach is %d B." % (top, big))
        print("            What would pin it: a method-8 fork whose coder "
              "output crosses 0x%X cost units — 2 per literal, 3 per match."
              % CLAIMED)
        return 0
    print("            NOT measured: %d fork(s) no block size reads."
          % len(failures))
    for f in failures[:10]:
        print("              %s: %s %s" % f)
    return 1


if __name__ == "__main__":
    sys.exit(main())

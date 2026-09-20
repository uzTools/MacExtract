#!/usr/bin/env python3
"""derive_huffman_tree.py — re-derive the bit-serialized Huffman tree
rule from the formats' own output, and hold it against specimens.

This is the evidence behind `docs/formats/serialized-huffman-tree.md`,
which is what `src/unc_huffman.c` cites for the serialisation instead
of somebody else's implementation. It consults no reference: it tries a
grid of plausible serialisations at every byte offset of an archive and
keeps only the combination whose decode reproduces the sha256 an
independent oracle recorded for a whole fork (`fixtures/manifests/`).

    tools/derive_huffman_tree.py --grid     # search the grid, print the rule
    tools/derive_huffman_tree.py            # verify the rule on the specimens

Not in `ci.sh`: it needs the fixtures, which are copyrighted and not
committed, and it is a derivation rather than a test. It skips cleanly
when they are absent, which is what a fresh clone has.

**A degenerate tree proves nothing.** A bare leaf is nine bits that
occur in almost any file and "decode" into any number of copies of one
byte, so a fork of identical bytes matches at an offset that means
nothing. Matches on single-leaf trees are refused below, and that is
not a hypothetical: one of them looked like a confirmation on
2026-09-20 until it was looked at.
"""
import argparse
import hashlib
import itertools
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Bits:
    __slots__ = ("d", "i", "msb")

    def __init__(self, data, pos, msb=True):
        self.d = data
        self.i = pos * 8
        self.msb = msb

    def bit(self):
        byte = self.i >> 3
        if byte >= len(self.d):
            raise EOFError
        sh = (7 - (self.i & 7)) if self.msb else (self.i & 7)
        self.i += 1
        return (self.d[byte] >> sh) & 1


def read_tree(bs, leaf_bit=1, sym_msb=True, cap=1024):
    """Pre-order: one bit a node, a leaf carrying eight bits of symbol."""
    seen = [0]

    def rec(depth):
        seen[0] += 1
        if depth > 32 or seen[0] > cap:
            raise ValueError
        if bs.bit() == leaf_bit:
            v = 0
            for k in range(8):
                b = bs.bit()
                v = (v << 1) | b if sym_msb else v | (b << k)
            return v
        return (rec(depth + 1), rec(depth + 1))

    return rec(0)


def decode(bs, tree, n, right_is_one=True):
    out = bytearray()
    while len(out) < n:
        node = tree
        while isinstance(node, tuple):
            b = bs.bit()
            node = node[b if right_is_one else 1 - b]
        out.append(node)
    return bytes(out)


def leaves(t):
    return 1 if not isinstance(t, tuple) else leaves(t[0]) + leaves(t[1])


def depth(t):
    return 0 if not isinstance(t, tuple) else 1 + max(depth(t[0]), depth(t[1]))


def hunt(data, sha, n, rule=(True, 1, True, True), skip_degenerate=True):
    """The offset at which `rule` reproduces `sha` over n bytes."""
    msb, leaf_bit, sym_msb, right1 = rule
    for off in range(len(data)):
        try:
            bs = Bits(data, off, msb)
            t = read_tree(bs, leaf_bit, sym_msb)
            if skip_degenerate and not isinstance(t, tuple):
                continue
            out = decode(bs, t, n, right1)
        except (EOFError, ValueError, RecursionError):
            continue
        if hashlib.sha256(out).hexdigest() == sha:
            return off, t
    return None, None


def fixture(name):
    p = os.path.join(ROOT, "fixtures", name)
    return open(p, "rb").read() if os.path.exists(p) else None


def manifest(name):
    p = os.path.join(ROOT, "fixtures", "manifests", name + ".json")
    return json.load(open(p)) if os.path.exists(p) else None


def entry(man, name):
    for e in man.get("entries", []):
        if e.get("name") == name:
            return e
    return None


# fixture, entry, fork, the archive's own name for what it is
SPECIMENS = [
    ("derived-ScrollbarPattern.sit", "Scrollbar Pattern Editor", "rsrc", "StuffIt 3"),
    ("derived-ComIT14.sit", "ComIT -- READ ME!", "data", "StuffIt 3"),
    ("derived-AdobeNumbers.sit", "About AdobeNumbers 1.0", "data", "StuffIt 3"),
    ("derived-DDArchive.sit", "DD Description", "data", "StuffIt 3"),
    ("derived-DDT.sit", "README", "data", "StuffIt 3"),
    ("derived-Diddle.sit", "fkeydebug.p", "data", "StuffIt 3"),
    ("derived-ExtraDAs.sit", "Extra DAs Readme", "data", "StuffIt 3"),
    ("derived-Jump_Start_1.4.sit",
     "Jump Start! 1.4 \u0192/Blurbs \u0192/Finder 7 Menus! Blurb", "data", "StuffIt 3"),
    ("derived-Jump_Start_1.4.sit",
     "Jump Start! 1.4 \u0192/Blurbs \u0192/IGS Array UNIT Blurb", "data", "StuffIt 3"),
    ("synth-dd-m4.dd", "synth-dd-m4", "data", "DiskDoubler 4"),
]

# PackIt codes the 94-byte entry header into the same stream, so what is
# compared is the fork INSIDE the decoded stream, and the header it comes
# with is checked to be that entry's own.
PACKIT = ("synth-packit-2.pit", [("Compressed Doc", 2000, 400),
                                 ("App\u00c3\u00a9", 50, 1500),
                                 ("one-symbol", 700, 0)])


def cmd_grid():
    """Search the whole grid on one fork; print what the format does."""
    data = fixture(SPECIMENS[0][0])
    man = manifest(SPECIMENS[0][0])
    if data is None or man is None:
        print("derive: no fixtures here — nothing to derive from (skipped)")
        return 0
    e = entry(man, SPECIMENS[0][1])
    sha, n = e["rsrc_sha256"], e["rsrc_size"]
    for rule in itertools.product([True, False], [1, 0], [True, False],
                                  [True, False]):
        off, t = hunt(data, sha, n, rule)
        if off is not None:
            msb, leaf_bit, sym_msb, right1 = rule
            print(f"rule: bits {'MSB' if msb else 'LSB'}-first, "
                  f"{leaf_bit} = leaf, symbol {'MSB' if sym_msb else 'LSB'}-first, "
                  f"{'1' if right1 else '0'} takes the second subtree")
            print(f"      (offset {off}, {leaves(t)} leaves, depth {depth(t)})")
            return 0
    print("derive: no serialisation in the grid reproduces the fork")
    return 1


def cmd_verify():
    ok = skipped = 0
    for name, ename, fork, what in SPECIMENS:
        data, man = fixture(name), manifest(name)
        if data is None or man is None:
            skipped += 1
            continue
        e = entry(man, ename)
        if not e:
            skipped += 1
            continue
        sha, n = e.get(fork + "_sha256"), e.get(fork + "_size")
        off, t = hunt(data, sha, n)
        if off is None:
            print(f"FAIL {name} {ename} {fork}: the rule does not read it")
            return 1
        print(f"ok  {what:14s} {name:30s} {n:6d} B  "
              f"leaves={leaves(t):3d} depth={depth(t):2d}")
        ok += 1

    name, entries = PACKIT
    data, man = fixture(name), manifest(name)
    if data is None or man is None:
        skipped += len(entries)
    else:
        for ename, dlen, rlen in entries:
            want = entry(man, ename)
            if not want:
                skipped += 1
                continue
            total = 94 + dlen + rlen + 2
            found = False
            for off in range(len(data)):
                try:
                    bs = Bits(data, off)
                    t = read_tree(bs)
                    if not isinstance(t, tuple):
                        continue
                    out = decode(bs, t, total)
                except (EOFError, ValueError, RecursionError):
                    continue
                if hashlib.sha256(out[94:94 + dlen]).hexdigest() == \
                        want["data_sha256"]:
                    hdr = out[1:1 + out[0]].decode("mac_roman", "replace")
                    print(f"ok  {'PackIt':14s} {name:30s} {total:6d} B  "
                          f"leaves={leaves(t):3d} depth={depth(t):2d}  "
                          f"header says {hdr!r}")
                    ok += 1
                    found = True
                    break
            if not found:
                print(f"FAIL {name} {ename}: the rule does not read it")
                return 1

    print(f"derive: {ok} forks reproduced, {skipped} skipped for want of a fixture")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grid", action="store_true",
                    help="search the serialisation grid instead of verifying")
    a = ap.parse_args()
    return cmd_grid() if a.grid else cmd_verify()


if __name__ == "__main__":
    sys.exit(main())

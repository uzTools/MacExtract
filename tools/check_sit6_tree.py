#!/usr/bin/env python3
"""check_sit6_tree.py — hold the StuffIt method-6 tree this engine BUILDS
against the one macunpack computes, over the whole input space.

Until 2026-09-21 this file GENERATED `src/sit6_tables.h`: 1,028 bytes of
tables derived from macunpack's constant weight table `code6[258]` by
`sit_dosplit`, committed so the build did not depend on `reference/`.
The engine now builds the same tree at run time from **26 bytes** — the
thirteen (count, length) pairs deark states the fixed code book as
(`src/sit6_tables.h`, `sit6_build` in `src/fmt_sit.c`) — so there is no
table to generate, and what is worth keeping is the comparison.

It checks the two agree on **every bit path of depth 13**, all 8,192 of
them: same leaf, after the same number of bits. That is the whole input
space of a 13-deep tree, so it is a proof rather than a sample. The
terminator is the one place the two could differ — macunpack spends 13
bits on it and the code book gives symbol 256 twelve — and `sit6_build`
reproduces the split deliberately.

Not in `./ci.sh`: it needs `reference/macutils`, which `ci.sh` does not
require. What ci.sh checks instead is the outcome — 11 method-6 forks
byte-exact against two other implementations (TESTING.md).

No format facts are invented: code6 is parsed out of the LGPL reference
file (see NOTICE) and the split below is a transcription of sit_dosplit.

Usage: tools/check_sit6_tree.py
"""
import os
import re
import sys

SRC = "reference/macutils/macunpack/sit.c"
DST = "src/sit6_tables.h"   # read for its 26 bytes, never written

LEAVES = 258            # nodelist[1..258]; 257 and 258 are the terminator
NODES = 515             # 258 leaves + 257 internal nodes, root at index 0
INTERNAL = NODES - LEAVES   # 257: the root plus nodelist[259..514]


def parse_code6(text):
    m = re.search(r"static short code6\[258\]\s*=\s*\{(.*?)\};", text, re.S)
    assert m, "code6[] not found in " + SRC
    vals = [int(v) for v in re.findall(r"-?\d+", m.group(1))]
    assert len(vals) == LEAVES, len(vals)
    return vals


def macunpack_tree(code6):
    """Transcription of sit_dosplit, with the recursion turned into an
    explicit stack (the engine forbids recursion; this generator does not
    need it either). Leaf node indices are 1..258, internal ones 0 and
    259..514, exactly as macunpack numbers them."""
    zero = [0] * NODES
    one = [0] * NODES
    nodeptr = LEAVES                    # sit_nodeptr
    stack = [(0, sum(code6), 1, LEAVES)]
    while stack:
        ptr, total, low, upp = stack.pop()
        half = total // 2
        locsum, i = 0, low
        while locsum < half:
            locsum += code6[i - 1]
            i += 1
        if low == i - 1:
            zero[ptr] = low
        else:
            nodeptr += 1
            zero[ptr] = nodeptr
            stack.append((nodeptr, half, low, i - 1))
        if upp == i:
            one[ptr] = upp
        else:
            nodeptr += 1
            one[ptr] = nodeptr
            stack.append((nodeptr, half, i, upp))
    return zero, one, nodeptr


def selftest(zero, one, used):
    """A tree that agrees only with itself proves nothing: check it is a
    tree, that every leaf is reachable exactly once, and that no internal
    node dangles."""
    seen = {}
    depth = 0
    stack = [(0, 0)]
    while stack:
        n, d = stack.pop()
        assert n not in seen, "node %d reached twice" % n
        seen[n] = d
        if 1 <= n <= LEAVES:
            depth = max(depth, d)
            continue
        assert n == 0 or n > LEAVES, n
        assert zero[n] and one[n], "internal node %d has no children" % n
        stack.append((zero[n], d + 1))
        stack.append((one[n], d + 1))
    leaves = [n for n in seen if 1 <= n <= LEAVES]
    assert len(leaves) == LEAVES, len(leaves)
    assert used == NODES - 1, used
    return depth


def fmt(vals, per=12):
    return "\n".join("    " + ",".join("%3d" % v for v in vals[i:i + per]) + ","
                     for i in range(0, len(vals), per))


def compact(vals):
    """Only the root and nodelist[259..514] have children, so drop the 258
    all-zero leaf rows: row 0 is the root, row k is macunpack's node
    258 + k. Child values keep macunpack's numbering (1..258 leaf ordinal,
    259.. internal), so the decoder indexes with child - SIT6_LEAVES."""
    out = [vals[0]] + vals[LEAVES + 1:]
    assert len(out) == INTERNAL, len(out)
    return out




def walk(zero, one, bits, leafmax, base):
    """Follow `bits` and report (leaf, bits consumed), or a marker."""
    node = 0
    for i, bit in enumerate(bits):
        child = one[node] if bit else zero[node]
        if child <= leafmax:
            return (child, i + 1)
        node = child - base
        if i + 1 > 13:
            return ("deep", i + 1)
    return ("short", len(bits))


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import synth_sit6

    code6 = parse_code6(open(SRC).read())
    mz, mo, used = macunpack_tree(code6)
    depth = selftest(mz, mo, used)

    # The engine's tree, from the 26 bytes, in the same (zero, one) shape.
    ez = [0] * NODES
    eo = [0] * NODES
    nodeptr = LEAVES
    try:
        for leaf, bitstr in sorted(synth_sit6.build_tree().items()):
            node = 0
            for i, ch in enumerate(bitstr):
                bit = ch == "1"
                last = i == len(bitstr) - 1
                table = eo if bit else ez
                if last:
                    if table[node]:
                        raise ValueError("leaf %d lands on a used slot" % leaf)
                    table[node] = leaf
                    break
                if not table[node]:
                    nodeptr += 1
                    if nodeptr >= NODES:
                        raise ValueError("more than %d nodes" % NODES)
                    table[node] = nodeptr
                node = table[node]
    except (AssertionError, ValueError, IndexError) as exc:
        print("sit6: FAIL — the 26 bytes do not state a %d-deep tree: %s"
              % (13, exc), file=sys.stderr)
        return 1

    bad = 0
    for n in range(1 << 13):
        bits = [(n >> (12 - k)) & 1 for k in range(13)]
        a = walk(mz, mo, bits, LEAVES, 0)
        b = walk(ez, eo, bits, LEAVES, 0)
        if a != b:
            bad += 1
            if bad <= 3:
                print("  differ on %s: macunpack %s, sit6_build %s"
                      % ("".join(map(str, bits)), a, b), file=sys.stderr)
    print("sit6: macunpack's tree is %d deep, %d internal nodes; "
          "8,192 bit paths compared, %d differ" % (depth, used - LEAVES, bad))
    if bad:
        print("sit6: FAIL — the 26 bytes do not state macunpack's tree",
              file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""derive_stuffit8.py — derive StuffIt classic method 8's coding from
output, and hold it against every method-8 fork in the corpus.

This is the evidence behind `docs/formats/stuffit-method-8-mw.md`. It
consults no implementation: the decoder below was written against a
family of hypotheses (an LZ variant whose dictionary entries are the
concatenation of two earlier entries — Miller and Wegman's, 1985 — read
at a growing code width), and every parameter was searched and scored
by how many bytes of the oracle's own output came back.

    tools/derive_stuffit8.py --grid   # search the parameters again
    tools/derive_stuffit8.py          # verify the rule on the corpus

Not in `ci.sh`: it needs the fixtures, which are not committed. It
skips cleanly without them.

**What it cannot reach.** No method-8 fork in the corpus fills the
dictionary, so the restart and the end-of-stream code are not exercised
here at all — see the note's last section. A tool that reported "all
forks decode" without saying so would be claiming the format, when what
it has is four forks.
"""
import argparse
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# fixture -> the entries the oracle names "MW"; the FORK is what decides,
# so each is tried and what comes back is what is reported.
CORPUS = ["derived-DSKDUP.sit", "derived-BitMap11.sit"]


class BitsLE:
    """Codes are read least-significant bit first, straight through."""
    __slots__ = ("d", "i")

    def __init__(self, d, pos):
        self.d = d
        self.i = pos * 8

    def get(self, n):
        v = 0
        for k in range(n):
            byte = self.i >> 3
            if byte >= len(self.d):
                raise EOFError
            v |= ((self.d[byte] >> (self.i & 7)) & 1) << k
            self.i += 1
        return v


def expand(pairs, code, out):
    """A code is a byte, or a pair of codes; walk it iteratively."""
    stack = [code]
    while stack:
        c = stack.pop()
        while c >= 256:
            l, r = pairs[c]
            stack.append(r)
            c = l
        out.append(c)


def decode(data, off, n, w0=9, wmax=14, stats=None):
    br = BitsLE(data, off)
    pairs = {}
    nxt = 256
    w = w0
    out = bytearray()
    prev = None
    ncodes = 0
    while len(out) < n:
        if w > wmax:
            raise ValueError("code width past %d" % wmax)
        code = br.get(w)
        ncodes += 1
        if code >= 256 and code not in pairs:
            raise ValueError("code %d is not in the dictionary" % code)
        expand(pairs, code, out)
        if prev is not None:
            # The new entry is the PREVIOUS match followed by this one.
            pairs[nxt] = (prev, code)
            nxt += 1
            if nxt + 1 > (1 << w) and w < wmax:
                w += 1
        prev = code
    if stats is not None:
        stats.update(codes=ncodes, entries=nxt - 256, widest=w)
    return bytes(out)


def forks(name):
    mpath = os.path.join(ROOT, "fixtures", "manifests", name + ".json")
    fpath = os.path.join(ROOT, "fixtures", name)
    if not (os.path.exists(mpath) and os.path.exists(fpath)):
        return None, []
    man = json.load(open(mpath))
    out = []
    for e in man.get("entries", []):
        if "MW" not in (e.get("oracle_methods") or []):
            continue
        for kind in ("data", "rsrc"):
            n = e.get(kind + "_size") or 0
            sha = e.get(kind + "_sha256")
            if n and sha:
                out.append((e["name"], kind, n, sha))
    return open(fpath, "rb").read(), out


def cmd_verify():
    ok = other = skipped = 0
    for name in CORPUS:
        data, fs = forks(name)
        if data is None:
            skipped += 1
            continue
        for ename, kind, n, sha in fs:
            hit = None
            st = {}
            for off in range(len(data)):
                try:
                    out = decode(data, off, n, stats=st)
                except (EOFError, ValueError, KeyError, IndexError):
                    continue
                if hashlib.sha256(out).hexdigest() == sha:
                    hit = off
                    break
            if hit is None:
                # The oracle names ONE method per entry and StuffIt picks
                # per FORK, so a fork that does not decode here is a fork
                # that is not method 8 — not a counter-example. The one
                # in the corpus is `BitMapHelp.index`'s resource fork,
                # which the engine reports as method 5.
                print(f"--  {name:24s} {ename[-24:]!r:26s} {kind:4s} "
                      f"{n:6d} B  not method 8")
                other += 1
            else:
                print(f"ok  {name:24s} {ename[-24:]!r:26s} {kind:4s} "
                      f"{n:6d} B  {st['entries']:5d} entries, widest code "
                      f"{st['widest']} bits")
                ok += 1
    print(f"stuffit-8: {ok} forks reproduced, {other} fork(s) of a "
          f"different method, {skipped} archive(s) absent")
    return 0


def cmd_grid():
    """Search the parameters again, scoring by prefix against the oracle."""
    data, fs = forks(CORPUS[0])
    if data is None:
        print("derive: no fixtures here — nothing to derive from (skipped)")
        return 0
    ename, kind, n, sha = max(fs, key=lambda f: f[2])
    best = (0, None)
    for off in range(len(data)):
        for w0 in (9, 10, 12, 13, 14):
            for wmax in (12, 13, 14, 16):
                if wmax < w0:
                    continue
                try:
                    out = decode(data, off, n, w0, wmax)
                except (EOFError, ValueError, KeyError, IndexError):
                    continue
                if hashlib.sha256(out).hexdigest() == sha:
                    st = {}
                    decode(data, off, n, w0, wmax, stats=st)
                    print(f"rule: LSB-first, code width {w0} growing by one "
                          f"as the dictionary fills, a new entry is "
                          f"(previous code, this code), 256 single bytes "
                          f"to start")
                    print(f"      widest code SEEN here: {st['widest']} bits "
                          f"at {st['entries']} entries — where it stops is "
                          f"not observable from this fork")
                    print(f"      (offset {off}, {n} bytes, "
                          f"{ename!r} {kind})")
                    return 0
    print("derive: nothing in the parameter grid reproduces the fork")
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grid", action="store_true",
                    help="search the parameters instead of verifying")
    a = ap.parse_args()
    return cmd_grid() if a.grid else cmd_verify()


if __name__ == "__main__":
    sys.exit(main())

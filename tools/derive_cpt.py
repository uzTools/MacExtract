#!/usr/bin/env python3
"""derive_cpt.py — read Compact Pro archives from the FORMAT's own
published description, and say where that description is wrong.

The Unarchiver's format wiki documents Compact Pro in three pages, and
`tools/fetch_references.sh` fetched only the first of them until
2026-09-20 even though its last line links the other two:

    reference/notes/cpt_specs_theunarchiver.md    the container
    reference/notes/cpt_lzh_theunarchiver.md      the LZSS+Huffman coder
    reference/notes/rle8182_theunarchiver.md      the 0x81 0x82 RLE

This reader is written from those three and from nothing else — not
from `src/fmt_cpt.c`, not from XADMaster, not from macutils. Where the
pages turned out to be wrong or silent, the correction is marked
**CORRECTION** below and was established by experiment: the archives
decode byte for byte against the sha256 an independent oracle recorded
for them, or they do not.

    tools/derive_cpt.py [fixture.cpt ...]

Not in `ci.sh`: it needs the fixtures, which are not committed. It
skips cleanly without them.
"""
import argparse
import glob
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def be(b, o, n):
    return int.from_bytes(b[o:o + n], "big")


def archive_base(d):
    """0, or 128 for an archive still inside its MacBinary wrapper."""
    if d[:1] == b"\x01":
        return 0
    if len(d) > 128 and d[128] == 0x01:
        return 128
    raise ValueError("not a Compact Pro archive")


def entries(d, base=0):
    """Container: the spec page's three tables, and they are right.

    CORRECTION: the file-header table lists "Offset to file data" TWICE,
    at N+2 both times, so a reader that takes the rows at face value is
    four bytes out from there on. The fields after it are at N+6 type,
    N+10 creator, N+14 and N+18 the dates, N+22 Finder flags, N+24 CRC,
    N+28 flags, N+30/34 the uncompressed lengths, N+38/42 the
    compressed ones, and the next header begins at N+46.
    """
    off = base + be(d, base + 4, 4)
    nfiles = be(d, off + 4, 2)
    p = off + 7 + d[off + 6]
    out = []
    # "The directory structure can be entirely inferred from the entry
    # count field": a directory header carries the number of files and
    # directories BELOW it, sub-directories included, so a stack of
    # (name, remaining) rebuilds the paths. Names repeat across folders
    # — one archive here has twelve pairs — so a reader that keeps only
    # the leaf compares the wrong fork against the wrong hash.
    stack = []
    for _ in range(nfiles):
        while stack and stack[-1][1] == 0:
            stack.pop()
        nl = d[p]
        n = nl & 0x7F
        name = d[p + 1:p + 1 + n].decode("mac_roman", "replace")
        q = p + 1 + n
        if stack:
            stack[-1][1] -= 1
        if nl & 0x80:                      # a directory: name and a count
            stack.append([name, be(d, q, 2)])
            p = q + 2
            continue
        path = "/".join([s[0] for s in stack] + [name])
        out.append(dict(name=name, path=path, off=base + be(d, q + 1, 4),
                        flags=be(d, q + 27, 2),
                        rlen=be(d, q + 29, 4), dlen=be(d, q + 33, 4),
                        rclen=be(d, q + 37, 4), dclen=be(d, q + 41, 4)))
        p = q + 45
    return out


class MSB:
    """"All values are read most significant bit first", and they are."""
    __slots__ = ("d", "p")

    def __init__(self, d, byte):
        self.d = d
        self.p = byte * 8

    def bit(self):
        return (self.d[self.p >> 3] >> (7 - (self.p & 7))) & 1 if \
            (self.p >> 3) < len(self.d) else self._eof()

    def _eof(self):
        raise EOFError

    def take(self):
        v = self.bit()
        self.p += 1
        return v

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.take()
        return v

    def align(self):
        self.p = (self.p + 7) & ~7

    def bytepos(self):
        return self.p >> 3


def build(lengths):
    """The page's code construction, with its `Reverse16` NOT applied.

    CORRECTION: the page says to add `Reverse16(code)`. Read
    most-significant-bit-first, as the same page says the stream is,
    the code IS the top `length` bits of the accumulator; reversing
    them decodes nothing. Ascending (length, value), max 15 bits, as
    the page says.
    """
    table = {}
    code = 0
    for length in range(1, 16):
        for i, l in enumerate(lengths):
            if l != length:
                continue
            table[(length, code >> (16 - length))] = i
            code += 1 << (16 - length)
    return table


def read_code(d, p, nsyms):
    """CORRECTION: the page says each code is "of fixed size" — 256, 64
    or 128 entries as nibbles. It is not. Each list is preceded by a
    BYTE COUNT: that many bytes of two lengths each, high nibble first,
    and every length after them is zero. Confirmed independently of any
    implementation by Kraft's equality, which comes out at exactly
    1.000000 for all three codes when the count byte is read and
    nowhere near it when it is not.
    """
    n = d[p]
    p += 1
    L = []
    for k in range(n):
        b = d[p + k]
        L.append(b >> 4)
        L.append(b & 15)
    L = L[:nsyms] + [0] * (nsyms - len(L))
    return build(L), p + n


def sym(bs, table):
    code = 0
    for length in range(1, 16):
        code = (code << 1) | bs.take()
        if (length, code) in table:
            return table[(length, code)]
    raise ValueError("no code of 15 bits or fewer matches")


class Rle:
    """The 0x81 0x82 filter as a state machine, because the length in
    the entry header counts the bytes it PRODUCES and the LZSS layer
    below has no length of its own — so the decode has to stop when
    this has enough, not when the LZSS has.

    CORRECTION: neither page says which layer the header's length
    measures. It is this one: driving the LZSS by it instead reads
    past the end of short forks and stops short on forks whose
    `0x81 0x82 0x00` escapes make the filter SHRINK its input.
    """
    def __init__(self, want):
        self.out = bytearray()
        self.want = want
        self.st = 0
        self.prev = 0

    def full(self):
        return len(self.out) >= self.want

    def push(self, b):
        if self.st == 0:
            if b == 0x81:
                self.st = 1
            else:
                self.out.append(b)
                self.prev = b
        elif self.st == 1:
            if b == 0x82:
                self.st = 2
            else:
                self.out.append(0x81)
                self.prev = 0x81
                self.st = 0
                self.push(b)
        else:
            self.st = 0
            if b == 0:
                self.out.extend(b"\x81\x82")
                self.prev = 0x82
            else:
                self.out.extend(bytes([self.prev]) * (b - 1))


def lzh(d, off, nout, blocksize=0x1FFF0):
    """The page's LZSS loop, its block accounting and its flush rule —
    all three as written, and they are right.

    CORRECTION: the offset. The page says to copy "starting at one byte
    less than the offset value before the previously output byte". The
    13 bits ARE the distance back from the byte about to be written,
    with nothing added, and **an offset of 0 is legal** — it names the
    byte being written, which a copy that goes through the window one
    byte at a time produces. Match length is the length code's symbol
    with nothing added either.
    """
    win = bytearray(8192)
    wpos = 0
    rle = Rle(nout)
    p = off
    first = True
    blockstart = 0
    bs = None
    while not rle.full():
        if not first:
            bs.align()
            consumed = bs.bytepos() - blockstart
            p = bs.bytepos() + (3 if (consumed & 1) else 2)
        tl, p = read_code(d, p, 256)
        tn, p = read_code(d, p, 64)
        to, p = read_code(d, p, 128)
        first = False
        bs = MSB(d, p)
        blockstart = p
        cost = 0
        while cost < blocksize and not rle.full():
            if bs.take():
                v = sym(bs, tl)
                rle.push(v)
                win[wpos & 8191] = v
                wpos += 1
                cost += 2
            else:
                mlen = sym(bs, tn)
                dist = (sym(bs, to) << 6) | bs.bits(6)
                for _ in range(mlen):
                    b = win[(wpos - dist) & 8191]
                    rle.push(b)
                    win[wpos & 8191] = b
                    wpos += 1
                cost += 3
    return bytes(rle.out)


def rle8182(src):
    """The RLE page, as written."""
    out = bytearray()
    i = 0
    while i < len(src):
        b = src[i]
        if b == 0x81 and i + 1 < len(src) and src[i + 1] == 0x82:
            if i + 2 >= len(src):
                out.append(b)
                i += 1
                continue
            n = src[i + 2]
            i += 3
            if n == 0:
                out.extend(b"\x81\x82")
            else:
                out.extend(bytes([out[-1] if out else 0]) * (n - 1))
        else:
            out.append(b)
            i += 1
    return bytes(out)


def check(path):
    d = open(path, "rb").read()
    mp = os.path.join(ROOT, "fixtures", "manifests",
                      os.path.basename(path) + ".json")
    if not os.path.exists(mp):
        return 0, 0
    man = {e["name"]: e for e in json.load(open(mp))["entries"]}
    base = archive_base(d)
    ok = bad = 0
    for e in entries(d, base):
        m = man.get(e["path"]) or man.get(e["name"])
        if not m:
            continue
        for kind, clen, ulen, bit, off in (
                ("rsrc", e["rclen"], e["rlen"], 0x02, e["off"]),
                ("data", e["dclen"], e["dlen"], 0x04, e["off"] + e["rclen"])):
            want = m.get(kind + "_size") or 0
            sha = m.get(kind + "_sha256")
            if not want or not sha:
                continue
            try:
                out = (lzh(d, off, want) if (e["flags"] & bit)
                       else rle8182(d[off:off + clen]))[:want]
                good = hashlib.sha256(out).hexdigest() == sha
            except Exception as exc:
                print(f"  FAIL {e['name'][:24]:26s} {kind} {want:7d} B  {exc}")
                bad += 1
                continue
            if not good:
                print(f"  FAIL {e['name'][:24]:26s} {kind} {want:7d} B  bytes differ")
                bad += 1
            else:
                ok += 1
    return ok, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixtures", nargs="*")
    a = ap.parse_args()
    paths = a.fixtures or sorted(glob.glob(os.path.join(ROOT, "fixtures", "*.cpt")))
    if not paths:
        print("derive-cpt: no fixtures here (skipped)")
        return 0
    tok = tbad = nfile = 0
    for p in paths:
        ok, bad = check(p)
        if ok or bad:
            nfile += 1
            print(f"{os.path.basename(p):34s} {ok:3d} fork(s) reproduced"
                  + (f", {bad} NOT" if bad else ""))
        tok += ok
        tbad += bad
    print(f"derive-cpt: {tok} forks of {nfile} archive(s) read from the "
          f"published description, {tbad} not")
    return 1 if tbad else 0


if __name__ == "__main__":
    sys.exit(main())

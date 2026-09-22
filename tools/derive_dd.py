#!/usr/bin/env python3
"""derive_dd.py — read DiskDoubler's DD (method 10) from the FORMAT's
own published description, and say where that description is wrong.

The Unarchiver's format wiki documents it, and
`tools/fetch_references.sh` fetches the page since 2026-09-20:

    reference/notes/dd_dd_theunarchiver.md

This reader is written from that page and from nothing else — not from
`src/fmt_dd.c`, not from XADMaster. The corrections it needs are
marked **CORRECTION** below and in docs/formats/diskdoubler-dd.md.

**It does not use a container parser**, because the wiki does not
document DiskDoubler's containers ("see XADDiskDoublerParser.m for
now") and this reader is not allowed to. It finds compressed blocks by
the checksum every DD block header carries — byte 21 is the XOR of the
twenty before it — which is a locator the FORMAT supplies.

    tools/derive_dd.py [archive ...]

Not in `ci.sh`: it needs the fixtures, which are not committed.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "reference", "notes", "dd_dd_theunarchiver.md")


def selectors():
    """The page's table of 32 offset selectors, parsed out of the page.

    CORRECTION: the page also gives a formula —
    `((2+(selector&1))<<bits)+1` — and it disagrees with this table for
    selectors 0 to 3, which have base 1, 2, 3 and 4 and no extra bits.
    The table is the one that decodes.
    """
    rows = re.findall(r"^\| (\d+)\s*\| (\d+)\s*\| (\d+)\s*\|$",
                      open(PAGE).read(), re.M)
    return {int(a): (int(b), int(c)) for a, b, c in rows}


def be(b, o, n):
    return int.from_bytes(b[o:o + n], "big")


class MSB:
    __slots__ = ("d", "p", "end")

    def __init__(self, d, byte, end):
        self.d = d
        self.p = byte * 8
        self.end = end

    def bit(self):
        if (self.p >> 3) >= self.end:
            raise EOFError
        v = (self.d[self.p >> 3] >> (7 - (self.p & 7))) & 1
        self.p += 1
        return v

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v


def build(lengths):
    """Canonical codes, shortest first, assigned in symbol order and
    read most-significant-bit first. The page does not say how codes
    are derived from lengths at all — this is the convention that
    decodes, and the only one of four tried that does."""
    t = {}
    code = 0
    for length in range(1, 33):
        for i, l in enumerate(lengths):
            if l == length:
                t[(length, code)] = i
                code += 1
        code <<= 1
    return t


def read_huff(d, p, end):
    """The page's Huffman header, and it is right: a big-endian u32 of
    parameters, then the code lengths, then the data at `bytes of code
    length data` + 4 from the start."""
    hdr = be(d, p, 4)
    nent = ((hdr >> 24) & 0xFF) + 1
    nbytes = (hdr >> 13) & 0x7FF
    bpl = (hdr >> 3) & 0x1F
    zero = (hdr >> 2) & 1
    bs = MSB(d, p + 4, end)
    L = []
    for _ in range(nent):
        L.append(bs.bits(bpl) if (not zero or bs.bit()) else 0)
    return build(L), p + 4 + nbytes


def block(d, p, SEL, out=None):
    """One block: a 22-byte header, then the three streams.

    CORRECTION (order): the header lists the compressed sizes as run
    lengths, literals, offsets — but the streams themselves are in the
    order the page's prose gives, **offset, literal, run length**. A
    reader that follows the header's order decodes nothing.

    CORRECTION (match length): the page says a match copies "the code
    plus two (maybe)" bytes. It is plus two; the parenthesis can go.
    """
    usize = be(d, p, 4)
    crun, clit, coff = be(d, p + 8, 2), be(d, p + 10, 2), be(d, p + 12, 2)
    flags = d[p + 14]
    x = 0
    for k in range(21):
        x ^= d[p + k]
    if x != d[p + 21]:
        raise ValueError("block header checksum")
    q = p + 22
    offp, litp, runp = q, q + coff, q + coff + clit
    end = q + coff + clit + crun
    if out is None:
        out = bytearray()
    base_len = len(out)
    if flags & 0x40:                       # the block is not compressed
        out.extend(d[q:q + usize])
        return out, q + usize
    trun, rp = read_huff(d, runp, runp + crun)
    runbs = MSB(d, rp, runp + crun)
    if flags & 0x80:                       # literals are Huffman coded
        tlit, lp = read_huff(d, litp, litp + clit)
        litbs = MSB(d, lp, litp + clit)
        lit = lambda: decode(litbs, tlit)          # noqa: E731
    else:
        cur = [litp]

        def lit():
            v = d[cur[0]]
            cur[0] += 1
            return v
    toff, op = read_huff(d, offp, offp + coff)
    offbs = MSB(d, op, offp + coff)
    # The window spans BLOCKS — "matches in later blocks can reference
    # data from earlier blocks if they are within the window" — so the
    # output accumulates across them and a match indexes back into all
    # of it, not into this block's share.
    while len(out) - base_len < usize:
        code = decode(runbs, trun)
        if code == 0:
            out.append(lit())
        elif code < 128:
            base, bits = SEL[decode(offbs, toff)]
            dist = base + (offbs.bits(bits) if bits else 0)
            for _ in range(code + 2):
                out.append(out[-dist])
        else:
            for _ in range(1 << (code - 128)):
                out.append(lit())
    return out, end


def decode(bs, t):
    code = 0
    for length in range(1, 33):
        code = (code << 1) | bs.bit()
        if (length, code) in t:
            return t[(length, code)]
    raise ValueError("no code")


def integrate(b):
    """The delta variant: what the coder produces is not the fork, it is
    the fork's first difference. Each byte is an increment on the one
    before it.

    CORRECTION (the page does not mention this at all): method 10 has
    two forms. The page names them — "DD1" and "DD2" — and describes
    one. In the other, EVERY byte of the LZSS output is a difference:
    literals and match bytes alike, so the transform sits outside the
    coder and not inside its literal stream. That is what the two forks
    of `derived-Terrainman_2.0__.sea` are, and with it they read.
    """
    out = bytearray(len(b))
    prev = 0
    for i, v in enumerate(b):
        prev = (prev + v) & 0xFF
        out[i] = prev
    return bytes(out)


def fork(d, start, nout, SEL, delta=False):
    out = bytearray()
    p = start
    while len(out) < nout:
        before = len(out)
        out, p = block(d, p, SEL, out)
        if len(out) == before:
            raise ValueError("empty block")
    out = bytes(out[:nout])
    return integrate(out) if delta else out


def blocks_at(d):
    """Every offset whose 22 bytes check out as a DD block header."""
    for p in range(len(d) - 22):
        x = 0
        for k in range(21):
            x ^= d[p + k]
        if x == d[p + 21] and 0 < be(d, p, 4) <= 0x20000:
            yield p


# ------------------------------------------------------------------ AD

def ad_block(d, p, out):
    """One AD block (methods 6 and 9), from
    reference/notes/dd_ad_theunarchiver.md.

    A 12-byte header — u16 compressed size, u16 uncompressed size, four
    unused, the XOR of the compressed data, flags, one more unused, and
    the XOR of the eleven bytes before it. Bit 0 of the flags says the
    block is compressed. Then a most-significant-bit-first stream:

      0          a literal, eight bits
      1 0 ...    an eight-bit offset
      1 1 ...    a twelve-bit offset
      then 0     copy two, 10 0 copy three, 10 1 copy four,
                 11 + four bits copy that many plus five

    The dictionary is the block, not a sliding window, and offsets
    count back from where the next byte goes.
    """
    clen, ulen = be(d, p, 2), be(d, p + 2, 2)
    flags = d[p + 9]
    x = 0
    for k in range(11):
        x ^= d[p + k]
    if x != d[p + 11]:
        raise ValueError("AD header checksum")
    q = p + 12
    # CORRECTION: the page says "bit 0 of the flags field indicates
    # whether the block is compressed or not" without saying which way
    # round. A block with 2,752 bytes in and 4,096 out has that bit
    # CLEAR, so it is set for an UNCOMPRESSED block.
    if flags & 1:
        out.extend(d[q:q + ulen])
        return out, q + clen
    y = 0
    for k in range(clen):
        y ^= d[q + k]
    if y != d[p + 8]:
        raise ValueError("AD data checksum")
    bs = MSB(d, q, q + clen)
    base = len(out)
    while len(out) - base < ulen:
        if not bs.bit():
            out.append(bs.bits(8))
            continue
        dist = bs.bits(12) if bs.bit() else bs.bits(8)
        if not bs.bit():
            n = 2
        elif not bs.bit():
            n = 3 if not bs.bit() else 4
        else:
            n = bs.bits(4) + 5
        # "the last match can apparently stretch outside the block
        # size. In this case, the match should be truncated to fit."
        n = min(n, ulen - (len(out) - base))
        for _ in range(n):
            out.append(out[-dist])
    return out, q + clen


def ad_fork(d, start, nout):
    out = bytearray()
    p = start
    while len(out) < nout:
        before = len(out)
        out, p = ad_block(d, p, out)
        if len(out) == before:
            raise ValueError("empty AD block")
    return bytes(out[:nout])


def ad_blocks_at(d):
    for p in range(len(d) - 12):
        x = 0
        for k in range(11):
            x ^= d[p + k]
        if x == d[p + 11] and 0 < be(d, p + 2, 2) <= 8192 and be(d, p, 2):
            yield p


def check(path, SEL, delta):
    d = open(path, "rb").read()
    mp = os.path.join(ROOT, "fixtures", "manifests",
                      os.path.basename(path) + ".json")
    if not os.path.exists(mp):
        return 0, 0
    want = []
    adwant = []
    for e in json.load(open(mp))["entries"]:
        ms = e.get("oracle_methods") or []
        if "AD/AD1" in ms or "ADn" in ms:
            for kind in ("data", "rsrc"):
                n = e.get(kind + "_size") or 0
                sha = e.get(kind + "_sha256")
                if n and sha:
                    adwant.append((e["name"], kind, n, sha))
        if "DDn" not in ms:
            continue
        for kind in ("data", "rsrc"):
            n = e.get(kind + "_size") or 0
            sha = e.get(kind + "_sha256")
            if n and sha:
                want.append((e["name"], kind, n, sha))
    if not (want or adwant):
        return 0, 0
    starts = list(blocks_at(d))
    adstarts = list(ad_blocks_at(d)) if adwant else []
    ok = bad = 0
    for name, kind, n, sha in want:
        hit = False
        # Which of method 10's two forms a fork uses is a CONTAINER fact
        # and this reader has no container parser, so it tries both. A
        # decoder that reads the entry header does not have to: see
        # docs/formats/diskdoubler-dd.md, "Which form a fork uses".
        for p in starts:
            for dl in (False, True):
                try:
                    out = fork(d, p, n, SEL, dl)
                except Exception:
                    continue
                if hashlib.sha256(out).hexdigest() == sha:
                    hit = True
                    if dl:
                        delta[0] += 1
                        # NAMED, not just counted, since 2026-09-22: the
                        # container states which forks these are, and a
                        # count cannot be held against a list
                        # (tools/derive_ddc.py).
                        delta.append("%s :: %s %s"
                                     % (os.path.basename(path), name, kind))
                    break
            if hit:
                break
        if hit:
            ok += 1
        else:
            print(f"  --   {name[-28:]:30s} {kind} {n:7d} B  not read here")
            bad += 1
    for name, kind, n, sha in adwant:
        hit = False
        for p in adstarts:
            try:
                out = ad_fork(d, p, n)
            except Exception:
                continue
            if hashlib.sha256(out).hexdigest() == sha:
                hit = True
                break
        if hit:
            ok += 1
        else:
            print(f"  --   {name[-28:]:30s} {kind} {n:7d} B  AD not read here")
            bad += 1
    return ok, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixtures", nargs="*")
    a = ap.parse_args()
    if not os.path.exists(PAGE):
        print("derive-dd: no reference/notes/dd_dd_theunarchiver.md — run "
              "tools/fetch_references.sh (skipped)")
        return 0
    SEL = selectors()
    delta = [0]
    if len(SEL) != 32:
        raise SystemExit(f"derive-dd: the page's selector table has {len(SEL)} rows")
    paths = a.fixtures or sorted(glob.glob(os.path.join(ROOT, "fixtures", "*.sea")) +
                                 glob.glob(os.path.join(ROOT, "fixtures", "*.dd")))
    if not paths:
        print("derive-dd: no fixtures here (skipped)")
        return 0
    tok = tbad = narch = 0
    for p in paths:
        ok, bad = check(p, SEL, delta)
        if ok or bad:
            narch += 1
            print(f"{os.path.basename(p):40s} {ok:3d} fork(s)"
                  + (f", {bad} not" if bad else ""))
        tok += ok
        tbad += bad
    print(f"derive-dd: {tok} DD/AD forks of {narch} archive(s) read from the "
          f"published description, {tbad} not"
          + (f" ({delta[0]} by the delta form)" if delta[0] else ""))
    for d in delta[1:]:
        print("  delta form: " + d)
    return 0


if __name__ == "__main__":
    sys.exit(main())

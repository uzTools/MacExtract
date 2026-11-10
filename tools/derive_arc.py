#!/usr/bin/env python3
"""derive_arc.py — derive ARC's container and three of its coders from
the output of a real ARC, and hold them against the corpus.

Evidence behind `docs/formats/arc-container-and-coders.md`. It consults
no implementation of the format. With `--grid` it makes ARC 5.21q
(`tools/get_arc.sh`, an implementation descended from SEA's own, not
from XADMaster) compress inputs chosen here, then searches the
parameter space of each coder and keeps what reproduces the input
byte for byte. Without `--grid` it re-reads the corpus fixtures with
the rules so derived and checks them against the oracle's sha256.

    tools/derive_arc.py --grid    # derive, needs tools/get_arc.sh
    tools/derive_arc.py --garble  # ARC's `g` against the garble rule, needs tools/get_arc.sh
    tools/derive_arc.py           # verify against fixtures/manifests

Not in `ci.sh`: it needs either the encoder or the fixtures, neither of
which a fresh clone has. It skips cleanly without them.

What it does NOT derive, and the note says so: methods 5, 6 and 7 (the
older Crunch variants, which this encoder will not write), method 10
in either dialect — PAK's Crushed and ARC 7's Trimmed — and the
Distilled coder, which is deark's already.
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arc_bin import arc_bin                                 # noqa: E402
ARC = arc_bin()


# ---------------------------------------------------------------- container

def members(d):
    """Every member: (method, name, data offset, csize, osize).

    The header is 0x1a, a method byte, 13 bytes of name, then u32 the
    compressed size, u16 date, u16 time, u16 CRC — and, for every
    method but 1, u32 the original size. Method 1 has no such field
    and its data is its own length. Verified by walking three archives
    end to end: a real ARC 5, a real ARC 7 (whose method 20 and 21
    items `unar` refuses) and a real PAK.
    """
    p = 0
    out = []
    while p + 29 <= len(d) and d[p] == 0x1a:
        m = d[p + 1]
        if m == 0:                       # end of archive
            break
        name = d[p + 2:p + 15].split(b"\0")[0].decode("latin1")
        csize, date, tm, crc = struct.unpack("<IHHH", d[p + 15:p + 25])
        if m == 1:
            osize, hl = csize, 25
        else:
            osize = struct.unpack("<I", d[p + 25:p + 29])[0]
            hl = 29
        out.append((m, name, p + hl, csize, osize))
        p += hl + csize
    return out


# ------------------------------------------------------------------ filters

def rle90(sym):
    """0x90 <n>: n == 0 is a literal 0x90, else the previous byte
    repeats n-1 more times. ARC calls a member that is only this
    "packed"."""
    out = bytearray()
    prev = None
    i = 0
    while i < len(sym):
        b = sym[i]
        i += 1
        if b != 0x90:
            out.append(b)
            prev = b
            continue
        if i >= len(sym):
            break
        n = sym[i]
        i += 1
        if n == 0:
            out.append(0x90)
            prev = 0x90
        elif prev is not None:
            out.extend(bytes([prev]) * (n - 1))
    return bytes(out)


class BitsLE:
    def __init__(self, d, bitpos):
        self.d = d
        self.p = bitpos

    def get(self, n):
        v = 0
        for k in range(n):
            byte = self.p >> 3
            if byte >= len(self.d):
                raise EOFError
            v |= ((self.d[byte] >> (self.p & 7)) & 1) << k
            self.p += 1
        return v


# ------------------------------------------------------------------- coders

def squeezed(d, off, nwant):
    """Method 4: RLE90 under a Huffman tree written as node PAIRS.

    u16 the node count, then that many pairs of s16, all little-endian:
    a negative value is a leaf holding symbol -value-1 (256 ends the
    stream), a non-negative one is the index of another pair. Decoding
    starts at pair 0 and reads one bit per step, LSB first, the bit
    choosing which of the pair to follow.
    """
    n = int.from_bytes(d[off:off + 2], "little")
    if not 0 < n <= 512 or off + 2 + 4 * n > len(d):
        raise ValueError("not a tree")
    base = off + 2
    pairs = [(int.from_bytes(d[base + 4 * k:base + 4 * k + 2], "little", signed=True),
              int.from_bytes(d[base + 4 * k + 2:base + 4 * k + 4], "little", signed=True))
             for k in range(n)]
    bits = BitsLE(d, (base + 4 * n) * 8)
    sym = bytearray()
    # The caller's byte count is what stops a real decoder; the stream's
    # last code can be followed by padding bits that decode to anything,
    # and on the last member of an archive they run off the end of the
    # file. Both endings are handled: the 256 symbol and the length.
    try:
        while len(sym) <= nwant + 512:
            node = 0
            while node >= 0:
                node = pairs[node][bits.get(1)]
            v = -node - 1
            if v == 256:
                break
            sym.append(v & 0xFF)
    except EOFError:
        pass
    return rle90(bytes(sym))


def lzw(d, bitpos, wmax, end=None):
    """LSB-first LZW: 9 bits growing to wmax, 256 clears the table,
    the first free code is 257."""
    bits = BitsLE(d if end is None else d[:end], bitpos)
    dic = {}
    nxt = 257
    w = 9
    out = bytearray()
    prev = None
    while True:
        try:
            code = bits.get(w)
        except EOFError:
            break
        if code == 256:
            dic, nxt, w, prev = {}, 257, 9, None
            continue
        if code < 256:
            s = bytes([code])
        elif code in dic:
            s = dic[code]
        elif prev is not None and code == nxt:
            s = prev + prev[:1]
        else:
            break
        out.extend(s)
        if prev is not None and nxt < (1 << wmax):
            dic[nxt] = prev + s[:1]
            nxt += 1
            if nxt >= (1 << w) and w < wmax:
                w += 1
        prev = s
    return bytes(out)


def crunched(d, off, nwant):
    """Method 8: the member's FIRST BYTE is the maximum code width,
    then LZW, then RLE90 over what it produces."""
    return rle90(lzw(d, (off + 1) * 8, d[off]))


def squashed(d, off, nwant):
    """Method 9: LZW to 13 bits and nothing else — no width byte in
    front of it and no RLE90 behind it."""
    return lzw(d, off * 8, 13)


DERIVED = {1: ("stored", lambda d, o, n: d[o:o + n]),
           2: ("stored", lambda d, o, n: d[o:o + n]),
           3: ("packed (RLE90)", lambda d, o, n: rle90(d[o:o + n])),
           4: ("squeezed", squeezed),
           8: ("crunched", crunched),
           9: ("squashed", squashed)}


# ------------------------------------------------------------------ commands

def cmd_verify():
    name = "synth-arc-mixed.arc"
    fp = os.path.join(ROOT, "fixtures", name)
    mp = os.path.join(ROOT, "fixtures", "manifests", name + ".json")
    if not (os.path.exists(fp) and os.path.exists(mp)):
        print("derive-arc: no fixtures here (skipped)")
        return 0
    d = open(fp, "rb").read()
    man = {e["name"]: e for e in json.load(open(mp))["entries"]}
    ok = undone = 0
    for m, ename, off, csize, osize in members(d):
        e = man.get(ename)
        if not e:
            continue
        if m not in DERIVED:
            print(f"--  method {m:2d}  {ename:8s}  not derived here")
            undone += 1
            continue
        what, fn = DERIVED[m]
        try:
            out = fn(d, off, osize)[:osize]
        except Exception as exc:
            print(f"FAIL method {m:2d}  {ename:8s}  {exc}")
            return 1
        good = hashlib.sha256(out).hexdigest() == e["data_sha256"]
        print(f"{'ok ' if good else 'FAIL'} method {m:2d}  {ename:8s}  "
              f"{osize:6d} B  {what}")
        if not good:
            return 1
        ok += 1
    print(f"derive-arc: {ok} members reproduced, {undone} method(s) not derived here")
    return 0


def cmd_grid():
    if not ARC:
        print("derive-arc: no `arc` encoder — run tools/get_arc.sh first (skipped)")
        return 0
    wd = tempfile.mkdtemp(prefix="arcderive-")
    import random
    random.seed(7)
    skew = b"".join(bytes([random.choice(b"abcdeeeeefffffgggg  \n")])
                    for _ in range(3000))
    runs = b"A" * 300 + bytes(range(256)) + b"B" * 500 + b"hello world " * 40
    open(os.path.join(wd, "sq.txt"), "wb").write(skew)
    open(os.path.join(wd, "run.bin"), "wb").write(runs)
    want = {"sq.txt": skew, "run.bin": runs}
    made = []
    for args, tag in ((["a", "test.arc", "sq.txt", "run.bin"], "default"),
                      (["aq", "sq9.arc", "run.bin"], "squash")):
        subprocess.run([ARC] + args, cwd=wd, capture_output=True)
        made.append(os.path.join(wd, args[1]))
    seen = 0
    for path in made:
        d = open(path, "rb").read()
        for m, ename, off, csize, osize in members(d):
            if m not in DERIVED:
                continue
            what, fn = DERIVED[m]
            out = fn(d, off, osize)[:osize]
            good = out == want.get(ename)
            print(f"{'ok ' if good else 'FAIL'} method {m:2d}  {what:14s} "
                  f"{ename:8s} {osize:6d} B  from a real ARC 5.21q")
            if not good:
                return 1
            seen += 1
    print(f"derive-arc: {seen} member(s) written by ARC itself and read back")
    return 0


# ------------------------------------------------------------------ garble

def _xor(data, key, start=0):
    return bytes(b ^ key[(start + i) % len(key)] for i, b in enumerate(data))


# How a member's stored bytes might be ungarbled. The first is the
# reading under test (`unc_crypt_xor`, `fmt_arc.c`'s two passwords): the
# password UPPER-CASED, XORed over the member's COMPRESSED bytes by
# position, starting again at its first character for every member. The
# others must fail, or the check cannot: the password as typed, and the
# key running on from one member into the next.
GARBLE_RULES = [("upper-cased, from 0 in each member", True, False, True),
                ("as typed, from 0 in each member", False, False, False),
                ("upper-cased, running on across members", True, True, False)]


def cmd_garble():
    """ARC 5.21q's own `g<password>` against the reading in unc_crypt.c.

    The same inputs are archived twice by the same ARC, once without a
    password and once with one; the headers must be identical, and each
    member's garbled bytes, ungarbled by a rule, must equal the
    UNGARBLED archive's bytes for that member — its compressed stream,
    not its plaintext, whichever method ARC chose. Only ARC's output and
    this file are in the loop; no decoder runs."""
    if not ARC:
        print("derive-arc: no `arc` encoder — run tools/get_arc.sh first (skipped)")
        return 0
    os.makedirs(os.path.join(ROOT, ".tmp"), exist_ok=True)
    wd = tempfile.mkdtemp(prefix="arcgarble-", dir=os.path.join(ROOT, ".tmp"))
    import random
    import shutil
    random.seed(11)
    files = {
        "sq.txt": b"".join(bytes([random.choice(b"abcdeeeeefffffgggg  \n")])
                           for _ in range(3001)),
        "run.bin": b"A" * 300 + bytes(range(256)) + b"B" * 501,
        "noise.bin": bytes(random.randrange(256) for _ in range(1003)),
        "fox.txt": b"the quick brown fox jumps over the lazy dog " * 80,
    }
    for n, b in files.items():
        open(os.path.join(wd, n), "wb").write(b)
    pw = "k3yWord"                       # 7: divides none of the sizes
    names = list(files)
    subprocess.run([ARC, "a", "plain.arc"] + names, cwd=wd,
                   capture_output=True)
    subprocess.run([ARC, "ag" + pw, "garbled.arc"] + names, cwd=wd,
                   capture_output=True)
    plain = open(os.path.join(wd, "plain.arc"), "rb").read()
    garb = open(os.path.join(wd, "garbled.arc"), "rb").read()
    shutil.rmtree(wd, ignore_errors=True)
    pm, gm = members(plain), members(garb)
    if len(pm) != len(files) or [m[:2] + m[3:] for m in pm] != \
            [m[:2] + m[3:] for m in gm]:
        print("FAIL the garbled archive's headers differ from the plain one's")
        return 1
    methods = sorted({m[0] for m in pm})
    if not any(m != 2 for m in methods):
        print("FAIL ARC stored every member, so nothing grades the "
              "COMPRESSED bytes")
        return 1
    if garb == plain:
        print("FAIL `g` changed nothing")
        return 1
    bad = 0
    for label, upper, running, want in GARBLE_RULES:
        key = (pw.upper() if upper else pw).encode()
        pos = 0
        good = True
        for (m, ename, off, csize, osize), p_ in zip(gm, pm):
            got = _xor(garb[off:off + csize], key, pos if running else 0)
            if got != plain[p_[2]:p_[2] + csize]:
                good = False
            pos += csize
        verdict = "ok " if good == want else "FAIL"
        print(f"{verdict} key {label:40s} "
              f"{'reproduces' if good else 'does not reproduce'} "
              f"the unpassworded archive")
        bad += good != want
    if bad:
        return 1
    print(f"derive-arc: garble = the password upper-cased, XORed over each "
          f"member's compressed bytes from its first character, on "
          f"{len(gm)} members (methods {', '.join(map(str, methods))}) "
          f"ARC 5.21q garbled itself")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grid", action="store_true",
                    help="derive from archives a real ARC writes here")
    ap.add_argument("--garble", action="store_true",
                    help="grade the garble against ARC's own g<password>")
    a = ap.parse_args()
    if a.garble:
        return cmd_garble()
    return cmd_grid() if a.grid else cmd_verify()


if __name__ == "__main__":
    sys.exit(main())

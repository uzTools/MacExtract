#!/usr/bin/env python3
"""run_ddcode.py — grade the engine's DiskDoubler methods 2, 5 and 7
against Salient's own decoders, run under qemu-m68k.

`DiskDoubler™ App` 3.1.2 (Salient, 1991) decodes methods 2 and 5 (the
splay-tree code) and method 7 (Stac LZS, in software when no Sigma card is
fitted) in its `CODE` 11; docs/formats/diskdoubler-splay-stac.md is what was
read off it. `dd_run.c` calls those two routines as subroutines. This sends
the same compressed forks to them and, wrapped in a 0xABCD0054 container, to
the CLI, and compares:

  F  every method 2, 5 and 7 fork in a DiskDoubler header anywhere in
     fixtures/, the DiskDoubler specimens, and the 3.1.2 floppy itself
     (22 method-7 forks of up to 8 chunks, the method-2 `XCMD.h`)
  S  splay forks written by tools/vmac/ddencode.py's encoder: method 2,
     and method 5 at all four tree counts, over random and skewed data,
     both XOR settings
  L  Stac forks written by this file's encoder (RFC 1974, section 2.5.5's
     grammar): greedy forks of random and repetitive data up to 200 KB,
     and hand-made token lists for every length boundary, the longest
     offsets of both forms, matches far longer than the window, a short
     offset written in the long form, an end marker in either form, a
     chunk table of many entries

and requires the CLI's forks to equal Salient's where Salient answers noErr,
and the CLI to refuse where Salient refuses (the cases where the two are
expected to differ are named, with why, in EXPECT_DIFFER). Then `--mutate`
(run by default after the grade) patches one instruction of Salient's code
per class and requires that class to disagree.

    tools/ddcode/run_ddcode.py [--cli BUILD/macextract] [--cases N]
                               [--seed S] [--no-mutate]

The application is copied off the cached 3.1.2 floppy with hfsutils and
never committed: it lives in the cache and in `.tmp/`.

What it CANNOT see:
  - a match reaching before the start of the fork: Salient's window is an
    uninitialised stack buffer, so what it copies is whatever was there;
    the engine refuses the fork. No case here sends one
  - the Sigma card's own decoder (`CODE` 11 @0x2cc8), which needs the card
  - anything about the container: forks are cut out of their headers by
    the offsets in docs/formats/diskdoubler-container.md and re-wrapped

SPDX-License-Identifier: 0BSD
"""
import argparse
import glob
import hashlib
import os
import random
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TMP = os.path.join(REPO, ".tmp", "ddcode")
VMAC = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
FLOPPY = os.path.join(VMAC, "ndd", "dd312",
                      "DiskDoubler 3.1.2 for Macintosh (3.5-800k)",
                      "Disk Doubler 3.1 (Salient).img")
APP_PATH = ":DiskDoubler™ App"
sys.path.insert(0, os.path.join(REPO, "tools", "vmac"))
import ddencode  # noqa: E402  (the splay encoder and the header CRC)

CODES = {
    11: "13006053dc5b5c242b262cdf9199ea37078d1e52d77b06d8ea866bc4bdfc41af",
    7: "92afc0f23c759ba0c102fcac80388b5b6113c69933d0c636b48eaa3c6bb4e042",
}
# Instructions docs/formats/diskdoubler-splay-stac.md cites, where it says.
WITNESS = [
    (11, 0x1e90, "0c4701ff"),        # tree init: parents for nodes 2..511
    (11, 0x1ed2, "0c4700ff"),        # children for internal nodes 1..255
    (11, 0x1f58, "0c450001"),        # splay: stop when the parent is the root
    (11, 0x1fbc, "c06dfc12"),        # next context: symbol AND (count - 1)
    (11, 0x2374, "08070007"),        # descent: bit 7 first, 1 is right
    (11, 0x23a4, "322df9f8"),        # the XOR, after the splay
    (11, 0x34f4, "1b7c00fffc28"),    # Stac: the check byte starts at 0xff
    (11, 0x355e, "48780012"),        # the 18-byte chunk-table header
    (11, 0x36c4, "700b"),            # an 11-bit offset ...
    (11, 0x36c8, "7007"),            # ... or a 7-bit one
    (11, 0x36de, "4a46"),            # offset 0 ends the stream
    (11, 0x371e, "0c44000f"),        # length nibbles continue on 15
    (11, 0x3762, "024607ff"),        # the 2,048-byte window
    (11, 0x3776, "4603"),            # the output is complemented
    (11, 0x38b6, "4640"),            # so is the input
    (7, 0x008c, "3c3c1021"),         # the chunk table's CRC-16 polynomial
]
# One patch per class: (class, segment, offset, old, new, what it breaks).
MUTATIONS = [
    ("S", 11, 0x2374, "08070007", "08070006",
     "the descent reads bit 6 for bit 7"),
    ("S", 11, 0x1fbc, "c06dfc12", "c06dfc14",
     "the next context is masked with the count, not count - 1"),
    ("S", 11, 0x2398, "4ebafb86", "4e714e71", "no splay: the trees stay "
     "complete"),
    ("L", 11, 0x36ee, "5480", "5680", "lengths start at 3, not 2"),
    ("L", 11, 0x371e, "0c44000f", "0c44000e",
     "length nibbles continue on 14"),
    ("L", 11, 0x3762, "024607ff", "024603ff", "a 1,024-byte window"),
    ("L", 11, 0x36c4, "700b", "700a", "10-bit long offsets"),
]
# Cases on which Salient and the engine are expected to answer differently,
# by name prefix, with the reason. Each is asserted to differ.
EXPECT_DIFFER = {
    "L-crc-bad": "Salient checks the chunk table's CRC-16 (-20999); the "
                 "engine skips the table",
    "L-long65537": "Salient's fast copy counts with dbf, 16 bits (CODE 11 "
                   "@0x377e), so a match over 65,536 bytes copies its length "
                   "mod 65,536; a writer's chunk is 12,288 bytes",
    "L-past-end": "a stream that decodes past the header's length: Salient "
                  "writes on and checks all of it, the engine stops at the "
                  "length and checks what it kept",
    "L-short": "a stream that ends before the header's length: Salient "
               "answers noErr with fewer bytes, the engine refuses it as "
               "truncated",
    "L-one": "a fork of length 1 is its byte, stored, to Salient (CODE 11 "
             "@0x3520); the engine wants the chunk table",
    "S-m5-16-": "Salient takes method 5 counts of 32, 64, 128 and 256 only "
                "(@0x1dfc); the engine decodes 16 with the mask",
}


def sh(*cmd, **kw):
    return subprocess.run(list(cmd), capture_output=True, **kw)


# ------------------------------------------------------------- Salient's code

def rsrc_fork(macbinary):
    dl, rl = struct.unpack(">II", macbinary[83:91])
    off = 128 + ((dl + 127) // 128) * 128
    return macbinary[off:off + rl]


def resource(fork, rtype, rid):
    """Inside Macintosh: More Macintosh Toolbox, Resource File Format."""
    doff, moff = struct.unpack(">II", fork[:8])
    m = fork[moff:]
    tl_off = struct.unpack(">H", m[24:26])[0]
    tl = m[tl_off:]
    for i in range(struct.unpack(">h", tl[:2])[0] + 1):
        t, cnt, ref = struct.unpack(">4shH", tl[2 + 8 * i:10 + 8 * i])
        if t != rtype:
            continue
        for j in range(cnt + 1):
            e = tl[ref + 12 * j:ref + 12 * j + 12]
            if struct.unpack(">h", e[:2])[0] == rid:
                at = doff + int.from_bytes(e[5:8], "big")
                n = struct.unpack(">I", fork[at:at + 4])[0]
                return fork[at + 4:at + 4 + n]
    raise SystemExit("run-ddcode: no %s %d in the application" % (rtype, rid))


def floppy_files():
    """Every file on the 3.1.2 floppy, as MacBinary, copied once."""
    out = os.path.join(TMP, "floppy")
    if os.path.isdir(out):
        return out
    if not os.path.exists(FLOPPY):
        raise SystemExit("run-ddcode: %s is not here" % FLOPPY)
    for tool in ("hmount", "hcopy", "humount", "hls"):
        if not shutil.which(tool):
            raise SystemExit("run-ddcode: needs hfsutils")
    os.makedirs(TMP, exist_ok=True)
    vol = os.path.join(TMP, "floppy.img")
    shutil.copyfile(FLOPPY, vol)
    os.makedirs(out + ".part", exist_ok=True)
    try:
        subprocess.run(["hmount", vol], check=True, capture_output=True)
        listing = sh("hls", "-R", "-1", ":").stdout.split(b"\n")
        folder = b":"
        n = 0
        for line in listing:
            if line.endswith(b":") and line.startswith(b":"):
                folder = line
                continue
            if not line or line.endswith(b":"):
                continue
            path = folder + line
            dst = os.path.join(out + ".part", "%03d.bin" % n)
            if subprocess.run(["hcopy", "-m", path, dst],
                              capture_output=True).returncode == 0:
                n += 1
            if path == APP_PATH.encode("mac_roman"):
                shutil.copyfile(dst, os.path.join(TMP, "app312.bin"))
    finally:
        subprocess.run(["humount"], capture_output=True)
        os.remove(vol)
    os.rename(out + ".part", out)
    return out


def lift(mutation=None):
    floppy_files()
    fork = rsrc_fork(open(os.path.join(TMP, "app312.bin"), "rb").read())
    paths = {}
    for seg, digest in CODES.items():
        code = bytearray(resource(fork, b"CODE", seg))
        if hashlib.sha256(code).hexdigest() != digest:
            raise SystemExit("run-ddcode: CODE %d is not the one this was "
                             "read from" % seg)
        for wseg, off, want in WITNESS:
            want = bytes.fromhex(want)
            if wseg == seg and bytes(code[off:off + len(want)]) != want:
                raise SystemExit("run-ddcode: CODE %d @0x%x is not %s"
                                 % (seg, off, want.hex()))
        tag = ""
        if mutation and mutation[1] == seg:
            _, _, off, old, new, _ = mutation
            old, new = bytes.fromhex(old), bytes.fromhex(new)
            assert code[off:off + len(old)] == old
            code[off:off + len(new)] = new
            tag = "-m"
        p = os.path.join(TMP, "code%d%s.bin" % (seg, tag))
        open(p, "wb").write(code)
        paths[seg] = p
    return paths[11], paths[7]


def build_runner():
    exe = os.path.join(TMP, "dd_run")
    r = sh("m68k-linux-gnu-gcc", "-std=gnu99", "-O2", "-static",
           "-fomit-frame-pointer", "-o", exe, os.path.join(HERE, "dd_run.c"),
           env=dict(os.environ, TMPDIR=TMP))
    if r.returncode:
        raise SystemExit("run-ddcode: building dd_run failed:\n"
                         + r.stderr.decode())
    return exe


def salient(exe, codes, lines):
    """One answer per line: (OSErr, output bytes)."""
    r = subprocess.run(["qemu-m68k", "-B", "0x20000000", exe] + list(codes),
                       input=("\n".join(lines) + "\n").encode(),
                       capture_output=True, timeout=3000)
    out = r.stdout.decode().splitlines()
    if r.returncode or len(out) != len(lines):
        raise SystemExit("run-ddcode: dd_run answered %d of %d lines (exit "
                         "%d) %s" % (len(out), len(lines), r.returncode,
                                     r.stderr[-300:]))
    res = []
    for o in out:
        f = o.split(" ")
        if f[0] == "signal":
            res.append((None, b""))
        else:
            res.append((int(f[0]), bytes.fromhex(f[1]) if len(f) > 1 else b""))
    return res


# ------------------------------------------------------------- the forks

class Fork:
    """One compressed fork and what its header says about it."""

    def __init__(self, name, method, comp, outlen, check, xor):
        self.name, self.method, self.comp = name, method, comp
        self.outlen, self.check, self.xor = outlen, check, xor

    def line(self):
        if self.method == 7:
            return "L %d %d %s" % (self.outlen, self.check & 0xFF,
                                   self.comp.hex())
        return "S %d %d %d %d %s" % (1 if self.method == 5 else 0, self.xor,
                                     self.outlen, self.check,
                                     self.comp.hex())

    def container(self):
        """A 0xABCD0054 file holding this fork as its data fork.
        Offsets: docs/formats/diskdoubler-container.md."""
        h = bytearray(84)
        h[0:4] = b"\xab\xcd\x00\x54"
        struct.pack_into(">IIII", h, 4, self.outlen, len(self.comp), 0, 0)
        h[20] = self.method
        h[22] = 0x2A if self.xor else 0
        h[32:40] = b"UNCLUNCL"
        struct.pack_into(">H", h, 48, self.check)
        struct.pack_into(">H", h, 82, ddencode.crc16_xmodem(bytes(h[:82])))
        return bytes(h) + self.comp


def forks_in(blob, name):
    """Every fork of method 2, 5 or 7 behind a DiskDoubler file header
    whose own CRC holds, wherever in `blob` it sits."""
    out = []
    at = blob.find(b"\xab\xcd\x00\x54")
    while at >= 0:
        h = blob[at:at + 84]
        if (len(h) == 84 and struct.unpack(">H", h[82:84])[0]
                == ddencode.crc16_xmodem(h[:82])):
            ds, dc, rs, rc = struct.unpack(">IIII", h[4:20])
            info1, info2 = h[22], h[52]
            xor = 0x5A if info1 >= 0x2A and not info2 & 0x80 else 0
            pos = at + 84
            for tag, size, comp, meth, ck in (
                    ("data", ds, dc, h[20], h[48:50]),
                    ("rsrc", rs, rc, h[21], h[50:52])):
                body = blob[pos:pos + comp]
                pos += comp
                if meth in (2, 5, 7) and size and len(body) == comp:
                    out.append(Fork("%s@%d.%s" % (name, at, tag), meth, body,
                                    size, struct.unpack(">H", ck)[0], xor))
        at = blob.find(b"\xab\xcd\x00\x54", at + 1)
    return out


def check_tables(forks):
    """What docs/formats/diskdoubler-splay-stac.md says of every method-7
    fork's chunk table: +2 is 12,288, the entry count is the output length
    over 12,288 rounded up, and the entries sum to the stream's length."""
    n7 = 0
    for f in forks:
        if f.method != 7:
            continue
        n7 += 1
        size, count = struct.unpack(">II", f.comp[2:10])
        ent = struct.unpack(">%dH" % count, f.comp[18:18 + 2 * count])
        if (size != 12288 or count != -(-f.outlen // 12288)
                or sum(ent) != len(f.comp) - 18 - 2 * count):
            raise SystemExit("run-ddcode: %s's chunk table is not as "
                             "described" % f.name)
    return n7


def corpus_forks():
    roots = [os.path.join(REPO, "fixtures"),
             os.path.join(VMAC, "specimens", "diskdoubler"),
             floppy_files()]
    seen, out = set(), []
    for root in roots:
        for p in sorted(glob.glob(os.path.join(root, "**", "*"),
                                  recursive=True)):
            if not os.path.isfile(p) or os.path.getsize(p) > 64 << 20:
                continue
            blob = open(p, "rb").read()
            for f in forks_in(blob, "F-" + os.path.relpath(p, root)):
                key = hashlib.sha256(f.comp).hexdigest()
                if key not in seen:
                    seen.add(key)
                    out.append(f)
    return out


# ------------------------------------------------------------- Stac, encoded

class Bits:
    def __init__(self):
        self.v, self.n = 0, 0

    def put(self, v, n):
        self.v = (self.v << n) | (v & ((1 << n) - 1))
        self.n += n

    def bytes(self):
        pad = -self.n % 8
        return (self.v << pad).to_bytes((self.n + pad) // 8, "big")


def stac_tokens(tokens):
    """RFC 1974 section 2.5.5 (ANSI X3.241-1994 section 3.2): a literal is 0
    and eight bits; a match is 1, then 1 and seven bits or 0 and eleven
    bits of offset, then the length: 00 01 10 for 2-4, 1100..1110 for 5-7,
    1111 and nibbles from 8, a nibble of 15 meaning another follows; the
    end marker is a seven-bit offset of zero. DiskDoubler's window holds
    the complement of each byte it outputs (CODE 11 @0x3776), so a literal
    carries the complement; a match copies either way."""
    b = Bits()
    for t in tokens:
        if t[0] == "lit":                  # DiskDoubler: the byte's complement
            b.put(0, 1)
            b.put(t[1] ^ 0xFF, 8)
            continue
        if t[0] == "end":
            b.put(1, 1)
            if t[1] == 7:
                b.put(1, 1)
                b.put(0, 7)
            else:
                b.put(0, 1)
                b.put(0, 11)
            continue
        _, off, n, form = t
        b.put(1, 1)
        if form == 7:
            b.put(1, 1)
            b.put(off, 7)
        else:
            b.put(0, 1)
            b.put(off, 11)
        if n < 5:
            b.put(n - 2, 2)
        elif n < 8:
            b.put(0b1100 | (n - 5), 4)
        else:
            b.put(0b1111, 4)
            n -= 8
            while n >= 15:
                b.put(15, 4)
                n -= 15
            b.put(n, 4)
    return b.bytes()


def stac_greedy(data, maxlen=1 << 30):
    """A plain LZSS search over the 2,048-byte window."""
    tok, i, heads = [], 0, {}
    while i < len(data):
        best, boff = 0, 0
        key = data[i:i + 2]
        for j in reversed(heads.get(key, [])[-48:]):
            if i - j > 2047:
                break
            n = 0
            while (i + n < len(data) and n < maxlen
                   and data[j + n] == data[i + n]):
                n += 1
            if n > best:
                best, boff = n, i - j
        if best >= 2:
            tok.append(("m", boff, best, 7 if boff < 128 else 11))
            step = best
        else:
            tok.append(("lit", data[i]))
            step = 1
        for k in range(i, i + step):
            heads.setdefault(data[k:k + 2], []).append(k)
        i += step
    return tok


def stac_play(tokens):
    """What a token list decodes to, by the grammar: the oracle for the
    encoder, not for anything graded."""
    out = bytearray()
    for t in tokens:
        if t[0] == "lit":
            out.append(t[1])
        elif t[0] == "end":
            break
        else:
            for _ in range(t[2]):
                out.append(out[-t[1]])
    return bytes(out)


def stac_fork(name, tokens, chunks=1, outlen=None, crc_ok=True):
    """DiskDoubler's method-7 fork: an 18-byte header, `chunks` 16-bit
    entries, the header's CRC-16 over all but its first two bytes, then the
    stream, every byte complemented. docs/formats/diskdoubler-splay-stac.md,
    measured off Salient's decoder and the 3.1.2 floppy's forks."""
    plain = stac_play(tokens)
    stream = bytes(b ^ 0xFF for b in stac_tokens(tokens))
    head = bytearray(18 + 2 * chunks)
    struct.pack_into(">HHI", head, 2, 0x3000, 0, chunks)
    for k in range(chunks):
        struct.pack_into(">H", head, 18 + 2 * k, len(stream) // chunks)
    crc = ddencode.crc16_xmodem(bytes(head[2:]))
    struct.pack_into(">H", head, 0, crc if crc_ok else crc ^ 1)
    n = len(plain) if outlen is None else outlen
    x = 0
    for c in plain[:n]:
        x ^= c
    if n % 2 == 0:
        x ^= 0xFF
    return Fork(name, 7, bytes(head) + stream, n, x, 0)


def stac_cases(rnd, n):
    out = []
    lit = lambda s: [("lit", c) for c in s]                   # noqa: E731
    end7, end11 = [("end", 7)], [("end", 11)]
    seed = bytes(rnd.randrange(256) for _ in range(2100))
    for k in range(2, 70):                      # every length to past 4 nibbles
        out.append(stac_fork("L-len%d" % k,
                             lit(b"ab") + [("m", 2, k, 7)] + lit(b"z") + end7))
    for k in (82, 83, 97, 98, 127, 128, 255, 256, 2047, 2048, 2049, 2100,
              4096, 5000, 12288, 65535, 65536, 65537):
        out.append(stac_fork("L-long%d-d1" % k,
                             lit(b"Q") + [("m", 1, k, 7)] + end7))
        out.append(stac_fork("L-long%d-d9" % k,
                             lit(b"123456789") + [("m", 9, k, 11)] + end7))
    for off in (1, 2, 126, 127):
        out.append(stac_fork("L-off7-%d" % off,
                             lit(seed[:off + 3]) + [("m", off, 6, 7)] + end7))
    for off in (1, 5, 127, 128, 129, 1000, 2046, 2047):
        out.append(stac_fork("L-off11-%d" % off,
                             lit(seed[:2050]) + [("m", off, 9, 11)] + end7))
    out.append(stac_fork("L-end11", lit(b"hello, world") + end11))
    out.append(stac_fork("L-empty-end", end7, outlen=0))
    out.append(stac_fork("L-trailing", lit(b"tail") + end7 + lit(b"junk")))
    out.append(stac_fork("L-past-end", lit(b"abcdefgh") + end7, outlen=6))
    out.append(stac_fork("L-short", lit(b"abcdefgh") + end7, outlen=12))
    out.append(stac_fork("L-crc-bad", lit(b"the table is wrong") + end7,
                         crc_ok=False))
    out.append(stac_fork("L-chunks200", lit(b"chunks!") + end7, chunks=200))
    for off in (15, 16, 17):
        out.append(stac_fork("L-off11-%d" % off,
                             lit(seed[:40]) + [("m", off, 9, 11)] + end7))
    out.append(Fork("L-one", 7, b"\x5a", 1, 0x5a, 0))
    for i in range(n):
        size = rnd.choice((3, 100, 2047, 2048, 2049, 12288, 40000, 200000))
        kind = i % 3
        if kind == 0:
            data = bytes(rnd.randrange(256) for _ in range(size))
        elif kind == 1:
            alpha = bytes(rnd.randrange(256) for _ in range(rnd.randrange(2, 9)))
            data = bytes(rnd.choice(alpha) for _ in range(size))
        else:
            words = [bytes(rnd.randrange(97, 123)
                           for _ in range(rnd.randrange(1, 12)))
                     for _ in range(60)]
            data = b" ".join(rnd.choice(words) for _ in range(size // 6))
        tok = stac_greedy(data)
        if stac_play(tok) != data:
            raise SystemExit("run-ddcode: the Stac encoder is wrong")
        out.append(stac_fork("L-rand%d-%d" % (i, len(data)), tok + end7,
                             chunks=1 + len(data) // 12288))
    return out


def splay_cases(rnd, n):
    out = []
    subjects = [("probe", ddencode.SUBJECT), ("all", ddencode.SUBJECT_ALL),
                ("one", b"x"), ("zeros", bytes(5000))]
    for i in range(n):
        size = rnd.choice((1, 2, 255, 256, 257, 4000, 65536))
        if i % 2:
            data = bytes(rnd.randrange(256) for _ in range(size))
        else:
            data = bytes(rnd.choice(b"etaoin shrdlu\n\x00\xff")
                         for _ in range(size))
        subjects.append(("rand%d" % i, data))
    for count in (16, 100, 3):          # outside what Salient allows
        data = ddencode.SUBJECT
        plain = bytes(c ^ 0x5A for c in data)
        comp = bytes([count]) + ddencode.enc_splay(plain, count)
        out.append(Fork("S-m5-%d-probe" % count, 5, comp, len(data),
                        sum(data) & 0xFFFF, 0x5A))
    for name, data in subjects:
        for xor in (0, 0x5A):
            plain = bytes(c ^ xor for c in data)
            comp = ddencode.enc_splay(plain)
            out.append(Fork("S-m2-%s-x%d" % (name, xor), 2, comp, len(data),
                            sum(data) & 0xFFFF, xor))
            for count in (256, 128, 64, 32):
                comp = bytes([count & 0xFF]) + ddencode.enc_splay(plain, count)
                out.append(Fork("S-m5-%d-%s-x%d" % (count, name, xor), 5,
                                comp, len(data), sum(data) & 0xFFFF, xor))
    return out


# ------------------------------------------------------------- the engine

def engine(cli, forks):
    """Each fork through the CLI: its data fork, or None if refused."""
    work = os.path.join(TMP, "work")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    res = []
    for i, f in enumerate(forks):
        src = os.path.join(work, "%d.dd" % i)
        open(src, "wb").write(f.container())
        dst = os.path.join(work, "%d" % i)
        os.makedirs(dst)
        r = sh(cli, "x", "-o", dst, src)
        names = [n for n in os.listdir(dst) if not n.endswith(".rsrc")]
        if r.returncode or len(names) != 1:
            res.append(None)
        else:
            res.append(open(os.path.join(dst, names[0]), "rb").read())
        shutil.rmtree(dst)
        os.remove(src)
    return res


def grade(forks, theirs, ours, quiet=False):
    bad = 0
    for f, (err, data), mine in zip(forks, theirs, ours):
        expect_differ = next((v for k, v in EXPECT_DIFFER.items()
                              if f.name.startswith(k)), None)
        if err == 0:
            agree = mine is not None and mine == data[:f.outlen] \
                and len(data) >= f.outlen
        else:
            agree = mine is None
        if expect_differ:
            agree = not agree
        if not agree:
            bad += 1
            if not quiet:
                print("  DIFFER %s: Salient %s %d B, engine %s" % (
                    f.name, err, len(data),
                    "refused" if mine is None else "%d B" % len(mine)))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", default=os.path.join(REPO, "build", "rel",
                                                  "macextract"))
    ap.add_argument("--cases", type=int, default=24)
    ap.add_argument("--seed", type=int, default=19910308)
    ap.add_argument("--no-mutate", action="store_true")
    a = ap.parse_args()
    for tool in ("m68k-linux-gnu-gcc", "qemu-m68k"):
        if not shutil.which(tool):
            raise SystemExit("run-ddcode: needs %s" % tool)
    os.makedirs(TMP, exist_ok=True)
    exe = build_runner()
    codes = lift()
    rnd = random.Random(a.seed)
    classes = {"F": corpus_forks(), "S": splay_cases(rnd, a.cases),
               "L": stac_cases(rnd, a.cases)}
    by = {m: sum(1 for f in classes["F"] if f.method == m) for m in (2, 5, 7)}
    print("F: method 2 x%d, 5 x%d, 7 x%d; %d chunk tables as described"
          % (by[2], by[5], by[7], check_tables(classes["F"])))
    total = 0
    answers = {}
    for cls, forks in classes.items():
        theirs = salient(exe, codes, [f.line() for f in forks])
        ours = engine(a.cli, forks)
        answers[cls] = (forks, theirs, ours)
        ok_s = sum(1 for e, _ in theirs if e == 0)
        bad = grade(forks, theirs, ours)
        total += bad
        print("%s: %d forks, Salient noErr on %d, %d disagreements"
              % (cls, len(forks), ok_s, bad))
    if total:
        print("run-ddcode: FAILED, %d disagreements" % total)
        return 1
    if not a.no_mutate:
        for m in MUTATIONS:
            cls = m[0]
            forks, _, ours = answers[cls]
            theirs = salient(exe, lift(m), [f.line() for f in forks])
            bad = grade(forks, theirs, ours, quiet=True)
            print("mutation %s @0x%x (%s): %d disagreements"
                  % (cls, m[2], m[5], bad))
            if bad == 0:
                print("run-ddcode: FAILED, a mutation went unseen")
                return 1
    print("run-ddcode: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

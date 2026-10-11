#!/usr/bin/env python3
"""decode.py — C-Cube JPEG-in-TIFF, the payload a StuffIt 2.0 `JPEG Lossy`
Optimizer stores, decoded on Linux and graded against Aladdin's own output.

This is the PROTOTYPE the engine's decoder is written from, and the place
the format's syntax is recorded in runnable form. It is not shipped and
`ci.sh` does not run it: it needs a specimen, like every other harness
whose subject is emulator output (TESTING.md).

    tools/ccube/decode.py <payload.bin> --against <2.0.1's own output.bin>

`payload.bin` is an optimized entry's stored data fork — the 80-byte
module header, then the TIFF. `--show` prints the IFD.

WHAT THE FORMAT IS — read out of one specimen first, then corrected
against 36 more on 2026-10-11 (FORMATS.md, *What an Optimizer did to the
fork*; `tools/run_sitcombo.py` grades the engine on all of them):

  * 80 bytes of module header: the module's colour code at +0 (1 RGB,
    2 HSB, 3 HSL, 4 CMYK, 5 channels coded one by one), channels at +2,
    WIDTH at +4 and height at +6 (this said the other way round until a
    non-square document existed), quality at +8, the length after the
    header at +10, then the offset of each TIFF from +14, ending with the
    total. RGB is one three-channel TIFF; CMYK a three-channel one and a
    one-channel one; the rest one one-channel TIFF per channel.
  * Each TIFF's `Compression` is **32865**, C-Cube's own code from before
    TIFF 6.0 gave old-style JPEG the number 6. Nothing reads it: `libtiff`
    parses the directory and hands back a black frame.
  * One quantisation table per channel at private tag **33606**, 64 words
    **in zigzag order**; DC and AC Huffman tables at **33607**/**33608**,
    `BITS[16]` then `HUFFVAL`. One channel's tag holds the table offset,
    three channels' the offset of three.
  * `TileOffsets` (324) holds the offset of an ARRAY of segment offsets,
    even when its count is 1.
  * **A three-channel MCU is 2 luma blocks, one Cb and one Cr — 4:2:2**,
    16x8; a one-channel MCU is one 8x8 block.
  * **(w + 39) // 40 restart segments per MCU row, each of
    (segs*mcu + w - 1) // (segs*mcu) MCUs** — C3a+0x4366's arithmetic.
    A 256-wide row is 7 segments of 3, which is the only width this file
    knew; the encoder codes the padding flat.
  * Each segment ends `FF Dn` then **one pad byte**. The restart index
    runs continuously mod 8 across the whole image, and **the DC
    predictors are NOT reset by it**.
  * Chroma is upsampled by interpolation at the module's full precision
    — an odd column is the mean of its neighbours, the image's last one
    repeats — and converted at CCOD+0xd98, which reduces to
    `y + (k * c2) >> 15` with `c2` twice the chroma's distance from 128.
    Replication is indistinguishable on grey content, which is all this
    file had until 2026-10-11.
  * Bits are MSB-first with JPEG's `FF 00` stuffing, and the last byte
    of a segment is padded with 1s.

WHAT IT CANNOT SEE: widths over 512, heights over 300, and any quality
the module's dialog refuses (it takes 5..255 and refuses 1..3).

License: LGPL-2.1-or-later. See LICENSE and NOTICE.
"""
import argparse
import struct
import sys

ZIG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5,
       12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
       35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
       58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]


class Bits(object):
    """MSB-first, with JPEG's FF 00 stuffing."""

    def __init__(self, b):
        self.b, self.i, self.bit = b, 0, 0

    def get(self):
        if self.i >= len(self.b):
            raise EOFError
        v = (self.b[self.i] >> (7 - self.bit)) & 1
        self.bit += 1
        if self.bit == 8:
            self.bit = 0
            prev = self.b[self.i]
            self.i += 1
            if prev == 0xFF and self.i < len(self.b) and self.b[self.i] == 0:
                self.i += 1
        return v

    def recv(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.get()
        return v

    def left(self):
        return (len(self.b) - self.i) * 8 - self.bit


def extend(v, n):
    return v - (1 << n) + 1 if n and v < (1 << (n - 1)) else v


def huff(bits, vals):
    code, k, lut = 0, 0, {}
    for length in range(1, 17):
        for _ in range(bits[length - 1]):
            lut[(length, code)] = vals[k]
            k += 1
            code += 1
        code <<= 1
    return lut


def decode(br, lut):
    code = 0
    for length in range(1, 17):
        code = (code << 1) | br.get()
        if (length, code) in lut:
            return lut[(length, code)]
    raise ValueError("no such Huffman code")


def block(br, dc, ac):
    s = decode(br, dc)
    co = [0] * 64
    co[0] = extend(br.recv(s), s) if s else 0
    k = 1
    while k < 64:
        rs = decode(br, ac)
        run, size = rs >> 4, rs & 15
        if size == 0:
            if run == 15:
                k += 16
                continue
            break
        k += run
        if k > 63:
            break
        co[k] = extend(br.recv(size), size)
        k += 1
    return co


def ifd(t):
    off = struct.unpack(">I", t[4:8])[0]
    n = struct.unpack(">H", t[off:off + 2])[0]
    out = {}
    for i in range(n):
        e = off + 2 + i * 12
        tag, typ, cnt = struct.unpack(">HHI", t[e:e + 8])
        size = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8}.get(typ, 1) * cnt
        if size <= 4:
            raw = t[e + 8:e + 8 + size]
        else:
            raw = t[struct.unpack(">I", t[e + 8:e + 12])[0]:][:size]
        out[tag] = (typ, cnt, raw)
    return out


# C-Cube's own IDCT, transcribed from CCOD+0x2f3c (FORMATS.md, *What an
# Optimizer did to the fork*). Cosines at 2^9; each rotation sums its two
# 32-bit products and then shifts right 9, rounding TOWARD ZERO; the
# coefficients are pre-scaled << 3 and the result descaled by (x+16)>>5.
# With this the decoder is byte-exact against StuffIt Deluxe 2.0.1's own
# output. A float IDCT is not: it differs on 0.96 % of samples, every one
# by exactly 1, because C-Cube's is an approximation and being more
# accurate than it is the wrong target.
C1, C2, C3, C4, C5, C6, C7 = 502, 473, 426, 362, 284, 196, 100


def sh(x):
    """asr.l #9, then addq.l #1 if the result is negative."""
    v = x >> 9
    return v + 1 if v < 0 else v


def idct1(x):
    """One 8-point pass, as CCOD+0x2f3c does it."""
    a4 = sh(C7 * x[1] - C1 * x[7])
    a7 = sh(C7 * x[7] + C1 * x[1])
    a5 = sh(C3 * x[5] - C5 * x[3])
    a6 = sh(C5 * x[5] + C3 * x[3])
    e0 = sh(C4 * (x[0] + x[4]))
    e1 = sh(C4 * (x[0] - x[4]))
    a2 = sh(C6 * x[2] - C2 * x[6])
    a3 = sh(C2 * x[2] + C6 * x[6])
    b4, b5 = a4 + a5, a4 - a5
    b6, b7 = a7 - a6, a7 + a6
    b0, b1 = e0 + a3, e1 + a2
    b2, b3 = e1 - a2, e0 - a3
    d5 = sh(C4 * (b6 - b5))
    d6 = sh(C4 * (b6 + b5))
    return [b0 + b7, b1 + d6, b2 + d5, b3 + b4,
            b3 - b4, b2 - d5, b1 - d6, b0 - b7]


def idct(c):
    """Columns first, then rows — which is what the de-zigzag table's
    stride says, and the two passes are the same code."""
    cc = [v << 3 for v in c]
    t = [0] * 64
    for col in range(8):
        v = idct1([cc[r * 8 + col] for r in range(8)])
        for r in range(8):
            t[r * 8 + col] = v[r]
    out = [0] * 64
    for r in range(8):
        v = idct1(t[r * 8:r * 8 + 8])
        for k in range(8):
            out[r * 8 + k] = v[k]
    return out


RTZ = False          # --rtz: the correction the disassembly has


def sample(x):
    """(x + 16) >> 5, the level shift, and the clamp.

    **No round-toward-zero correction here**, unlike every rotation in
    the network above, and CCOD+0x3826 was read as applying one until
    2026-10-02. On the first subject, with it, 709 of 65,536 luma samples
    miss by one; without it, none do.

    `--rtz` is the experiment that settled why. A second, dense subject
    reaches `v < 0` **9,645** times and `--rtz` is wrong on every one
    of them, while this is byte-exact on both subjects — so the branch
    IS taken and the correction is not the module's. The attribution of
    it to CCOD+0x3826 was a misreading of the disassembly and is
    withdrawn (BLOCKERS.md). The switch is kept because it is the
    instrument that said so.
    """
    v = (x + 16) >> 5
    if RTZ and v < 0:
        v += 1
    v += 128
    return 0 if v < 0 else (255 if v > 255 else v)


def chroma2(row, x, w):
    """Twice the chroma's distance from 128 at column x, interpolated."""
    j = x >> 1
    a = row[j] - 128
    if not x & 1:
        return a + a
    return a + (row[j + 1] - 128 if j + 1 < (w + 1) // 2 else a)


def one_tiff(t):
    """One TIFF's planes, as a list of bytes objects."""
    e = ifd(t)
    w = struct.unpack(">H", e[256][2])[0]
    h = struct.unpack(">H", e[257][2])[0]
    spp = struct.unpack(">H", e[277][2])[0]

    def offsets(tag):
        cnt = e[tag][1]
        if cnt == 1:
            return [struct.unpack(">I", e[tag][2])[0]]
        return list(struct.unpack(">%dI" % cnt, e[tag][2]))
    q = [struct.unpack(">64H", t[o:o + 128]) for o in offsets(33606)]
    dcs, acs = [], []
    for tag, into in ((33607, dcs), (33608, acs)):
        for o in offsets(tag):
            bits = t[o:o + 16]
            into.append(huff(bits, t[o + 16:o + 16 + sum(bits)]))
    ptr = struct.unpack(">I", e[324][2])[0] if e[324][1] == 1 else None
    if ptr is not None:     # one segment, and still the offset of an array
        offs = [struct.unpack(">I", t[ptr:ptr + 4])[0]]
    else:
        offs = [o for o in offsets(324) if o]
    mcu_w = 16 if spp == 3 else 8
    segs_row = (w + 39) // 40
    per_seg = (segs_row * mcu_w + w - 1) // (segs_row * mcu_w)
    stride = segs_row * per_seg * mcu_w
    rows = (h + 7) // 8
    comps = ((0, 2), (1, 1), (2, 1)) if spp == 3 else ((0, 1),)
    P = [[[0] * stride for _ in range(rows * 8)] for _ in range(3)]
    pred = [0, 0, 0]
    for si in range(segs_row * rows):
        seg = t[offs[si]:]
        for p in range(len(seg) - 1):
            if seg[p] == 0xFF and 0xD0 <= seg[p + 1] <= 0xD7:
                seg = seg[:p]
                break
        br = Bits(seg)
        row, col0 = si // segs_row, (si % segs_row) * per_seg
        for m in range(per_seg):
            mx = col0 + m
            for comp, count in comps:
                for k in range(count):
                    co = block(br, dcs[comp], acs[comp])
                    pred[comp] += co[0]
                    co[0] = pred[comp]
                    deq = [0] * 64
                    for z in range(64):
                        deq[ZIG[z]] = co[z] * q[comp][z]
                    px = idct(deq)
                    ox = mx * mcu_w + k * 8 if comp == 0 else mx * 8
                    for yy in range(8):
                        for xx in range(8):
                            P[comp][row * 8 + yy][ox + xx] = \
                                sample(px[yy * 8 + xx])
    if spp == 1:
        return [bytes(P[0][y][x] for y in range(h) for x in range(w))], w, h

    def clamp(v):
        return 0 if v < 0 else (255 if v > 255 else v)
    # CCOD+0xd98's conversion: 1.402, 1.772 and the green terms at 2^14,
    # applied to the doubled, interpolated chroma at 2^15.
    out = [bytearray(w * h) for _ in range(3)]
    for y in range(h):
        for x in range(w):
            yy = P[0][y][x]
            cb = chroma2(P[1][y], x, w)
            cr = chroma2(P[2][y], x, w)
            out[0][y * w + x] = clamp(yy + ((22965 * cr) >> 15))
            out[1][y * w + x] = clamp(yy + ((-11703 * cr - 5631 * cb) >> 15))
            out[2][y * w + x] = clamp(yy + ((29036 * cb) >> 15))
    return [bytes(o) for o in out], w, h


def run(payload):
    if payload[80:84] != b"MM\x00\x2a":
        raise SystemExit("decode: not a C-Cube payload (no TIFF after +80)")
    w, h = struct.unpack(">HH", payload[4:8])
    total = 80 + struct.unpack(">I", payload[10:14])[0]
    offs, k = [], 14
    while k + 4 <= 80:
        v = struct.unpack(">I", payload[k:k + 4])[0]
        if v >= total:
            break
        offs.append(v)
        k += 4
    planes = b""
    for i, o in enumerate(offs):
        end = offs[i + 1] if i + 1 < len(offs) else total
        got, tw, th = one_tiff(payload[o:end])
        if (tw, th) != (w, h):
            raise SystemExit("decode: a TIFF of %dx%d in a %dx%d document"
                             % (tw, th, w, h))
        planes += b"".join(got)
    return planes, w, h


def forks(path):
    d = open(path, "rb").read()
    dl = int.from_bytes(d[83:87], "big")
    return d[128:128 + dl]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("--against", help="MacBinary of 2.0.1's own restored file")
    ap.add_argument("--out", help="write the planar RGB here")
    ap.add_argument("--rtz", action="store_true",
                    help="apply CCOD+0x3826's round-toward-zero "
                         "correction in the output stage")
    args = ap.parse_args()
    global RTZ
    RTZ = args.rtz
    got, w, h = run(open(args.payload, "rb").read())
    print("ccube: decoded %dx%d, %d bytes planar RGB" % (w, h, len(got)))
    if args.out:
        open(args.out, "wb").write(got)
    if args.against:
        ref = forks(args.against)
        if len(ref) != len(got):
            print("ccube: PROBLEM: %d bytes against %d" % (len(got), len(ref)))
            return 1
        diff = [abs(got[i] - ref[i]) for i in range(len(ref))]
        n = sum(1 for d in diff if d)
        print("ccube: vs 2.0.1's own output — %d of %d bytes differ (%.2f %%), "
              "largest %d" % (n, len(ref), 100.0 * n / len(ref), max(diff)))
        if n and not args.rtz:
            print("ccube: PROBLEM: this decoder is meant to be BYTE-EXACT")
            return 1
        if n:
            # --rtz is an experiment, not the decoder: a difference here
            # is the measurement being asked for.
            print("ccube: (--rtz) that is the measurement, not a failure")
    return 0


if __name__ == "__main__":
    sys.exit(main())

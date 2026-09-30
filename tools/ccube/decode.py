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

WHAT THE FORMAT IS, all of it read out of one specimen and confirmed by
decoding it (FORMATS.md, *What an Optimizer did to the fork*):

  * 80 bytes of module header: version, channels at +2, height at +4,
    width at +6, quality at +8, the payload length at +12, the header
    length at +16 and the total at +20. Then a TIFF, `MM\\0*`.
  * `Compression` is **32865**, C-Cube's own code from before TIFF 6.0
    gave old-style JPEG the number 6. Nothing reads it: `libtiff` parses
    the directory and hands back a black frame.
  * Three quantisation tables at private tag **33606**, 64 words each,
    **in zigzag order** — Annex K's luminance and chrominance tables
    scaled by the quality.
  * Three DC Huffman tables at **33607** and three AC at **33608**,
    `BITS[16]` then `HUFFVAL`, 256 symbols each (C-Cube pads a DC table
    out to the full alphabet).
  * `TileOffsets`/`TileByteCounts` (324/325) index the entropy data. The
    declared count is 230 and **the last six entries are zero**.
  * **An MCU is 2 luma blocks, one Cb and one Cr — 4:2:2** — and a
    segment is **exactly 3 MCUs**, so 48 pixels wide by 8 tall.
  * **Seven segments per tile row**, which is 21 MCUs = 336 pixels for
    a 256-pixel image: the encoder pads the width out and codes the
    padding flat, which is why the last two segments of every row are
    11 bytes whatever the picture does.
  * Each segment ends `FF Dn` then **one pad byte**. The restart index
    runs continuously mod 8 across the whole image, and **the DC
    predictors are NOT reset by it** — only the very first segment
    carries a non-zero DC difference on a flat image.
  * Bits are MSB-first with JPEG's `FF 00` stuffing, and the last byte
    of a segment is padded with 1s.

WHAT IT CANNOT SEE: one specimen, 256x256, quality 25, three channels.
Nothing here has a second image, another quality or a greyscale
document, so every "always" above is an always over one file.

License: LGPL-2.1-or-later. See LICENSE and NOTICE.
"""
import argparse
import math
import struct
import sys

ZIG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5,
       12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
       35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
       58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]
MCU_W, MCU_H = 16, 8
MCUS_PER_SEG = 3
SEGS_PER_ROW = 7


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


# A float IDCT, which is not what the module uses. It agrees with
# Aladdin's own output on 99.04 % of bytes and differs by exactly 1 on
# the rest — and **no standard IDCT does better**: jpeg-6b's islow is
# worse (1.065 %), and a separable integer transform swept over 8..16
# bits and every descale split only reaches 4.48 % on the inked blocks
# against this one's 4.83 %. C-Cube's arithmetic is its own, it is in
# the 31,952-byte `C3a` resource, and matching it byte for byte would
# mean reproducing a 1990 approximation on purpose (FORMATS.md).
# Do not spend an afternoon re-trying those three.
_C = [[(0.353553390593 if u == 0 else 0.5) *
       math.cos((2 * x + 1) * u * math.pi / 16) for u in range(8)]
      for x in range(8)]


def idct(b):
    out = [[0.0] * 8 for _ in range(8)]
    for y in range(8):
        for x in range(8):
            s = 0.0
            for v in range(8):
                for u in range(8):
                    c = b[v * 8 + u]
                    if c:
                        s += c * _C[x][u] * _C[y][v]
            out[y][x] = s
    return out


def run(payload):
    t = payload[80:]
    if t[:4] != b"MM\x00\x2a":
        raise SystemExit("decode: not a C-Cube payload (no TIFF after +80)")
    e = ifd(t)
    w = struct.unpack(">H", e[256][2])[0]
    h = struct.unpack(">H", e[257][2])[0]
    q = [struct.unpack(">64H", t[o:o + 128])
         for o in struct.unpack(">3I", e[33606][2])]
    dcs, acs = [], []
    for tag, into in ((33607, dcs), (33608, acs)):
        for o in struct.unpack(">3I", e[tag][2]):
            bits = t[o:o + 16]
            into.append(huff(bits, t[o + 16:o + 16 + sum(bits)]))
    offs = struct.unpack(">%dI" % e[324][1], e[324][2])
    cnts = struct.unpack(">%dI" % e[325][1], e[325][2])
    segs = [(o, c) for o, c in zip(offs, cnts) if c]
    stride = SEGS_PER_ROW * MCUS_PER_SEG * MCU_W
    Y = [[0.0] * stride for _ in range(h)]
    CB = [[0.0] * (stride // 2) for _ in range(h)]
    CR = [[0.0] * (stride // 2) for _ in range(h)]
    pred = [0, 0, 0]
    for si, (o, c) in enumerate(segs):
        seg = t[o:o + c]
        for p in range(len(seg) - 1):
            if seg[p] == 0xFF and 0xD0 <= seg[p + 1] <= 0xD7:
                seg = seg[:p]
                break
        br = Bits(seg)
        row, col0 = si // SEGS_PER_ROW, (si % SEGS_PER_ROW) * MCUS_PER_SEG
        for m in range(MCUS_PER_SEG):
            mx = col0 + m
            for comp, count in ((0, 2), (1, 1), (2, 1)):
                for k in range(count):
                    co = block(br, dcs[comp], acs[comp])
                    pred[comp] += co[0]
                    co[0] = pred[comp]
                    deq = [0] * 64
                    for z in range(64):
                        deq[ZIG[z]] = co[z] * q[comp][z]
                    px = idct(deq)
                    if comp == 0:
                        ox, oy = mx * MCU_W + k * 8, row * 8
                        for yy in range(8):
                            for xx in range(8):
                                Y[oy + yy][ox + xx] = px[yy][xx]
                    else:
                        ox, oy = mx * 8, row * 8
                        tgt = CB if comp == 1 else CR
                        for yy in range(8):
                            for xx in range(8):
                                tgt[oy + yy][ox + xx] = px[yy][xx]
    def clamp(v):
        return 0 if v < 0 else (255 if v > 255 else int(v + 0.5))
    out = bytearray(w * h * 3)
    for y in range(h):
        for x in range(w):
            yy = Y[y][x] + 128
            cb = CB[y][x // 2]
            cr = CR[y][x // 2]
            out[y * w + x] = clamp(yy + 1.402 * cr)
            out[w * h + y * w + x] = clamp(yy - 0.344136 * cb - 0.714136 * cr)
            out[2 * w * h + y * w + x] = clamp(yy + 1.772 * cb)
    return bytes(out), w, h


def forks(path):
    d = open(path, "rb").read()
    dl = int.from_bytes(d[83:87], "big")
    return d[128:128 + dl]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("--against", help="MacBinary of 2.0.1's own restored file")
    ap.add_argument("--out", help="write the planar RGB here")
    args = ap.parse_args()
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
        if max(diff) > 1:
            print("ccube: PROBLEM: a difference larger than IDCT rounding")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

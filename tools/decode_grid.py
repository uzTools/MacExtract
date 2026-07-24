#!/usr/bin/env python3
"""decode_grid.py <macscreen.png> — decode the Mini vMac autotest bit grid.

The Mac app (mac/unclassic_mac.c, at_report) writes its results straight to
the framebuffer as a black/white grid on the 512x342 Mac screen: three solid
calibration squares at known screen positions, then a 16-bit sync word 0xA55A
followed by eight 32-bit values, MSB first, row-major across 16 columns.

The three calibration squares (Mac centres (36,44),(476,44),(36,300)) are
located in the image and used to solve the Mac->image transform, so the
decoder is robust to crop offset and any integer scaling. Each cell is read by
majority vote over a small patch to shrug off a stray pixel.

Values: [nfiles, ret, errors, sumDataCRC, totalDataLen, sumRsrcCRC,
         totalRsrcLen, peakBytes]. Exits non-zero if the sync word is wrong.
"""
import sys, re, subprocess

COLS, X0, Y0, PITCH, FILL = 16, 96, 72, 14, 10   # must match at_report()
NVALS = 8
NBITS = 16 + NVALS * 32
# calibration square centres, in Mac-screen coordinates
CAL = [(36, 44), (476, 44), (36, 300)]


def load_pgm(path):
    pgm = subprocess.run(["convert", path, "-compress", "none", "pgm:-"],
                         capture_output=True).stdout
    toks = re.sub(rb'#[^\n]*', b'', pgm).split()
    assert toks[0] == b'P2', toks[0]
    w, h = int(toks[1]), int(toks[2])
    px = list(map(int, toks[4:4 + w * h]))
    return w, h, px


def centroid(px, w, h, cx, cy, rad=16):
    sx = sy = n = 0
    for y in range(max(0, cy - rad), min(h, cy + rad)):
        base = y * w
        for x in range(max(0, cx - rad), min(w, cx + rad)):
            if px[base + x] < 128:
                sx += x; sy += y; n += 1
    return (sx / n, sy / n) if n >= 40 else None


def decode(path):
    """Decode the grid in <path>; return the 8 values, or None if no valid grid.
    Values: [nfiles, ret, errors, sumDataCRC, totalDataLen, sumRsrcCRC,
             totalRsrcLen, peakBytes]."""
    w, h, px = load_pgm(path)
    found = [centroid(px, w, h, cx, cy) for cx, cy in CAL]
    if any(f is None for f in found):
        return None
    (tlx, tly), (trx, _tqy), (blx, bly) = found
    sx = (trx - tlx) / (CAL[1][0] - CAL[0][0])
    sy = (bly - tly) / (CAL[2][1] - CAL[0][1])
    ox = tlx - CAL[0][0] * sx
    oy = tly - CAL[0][1] * sy

    def cell_bit(idx):
        col, row = idx % COLS, idx // COLS
        mx = X0 + col * PITCH + FILL / 2.0
        my = Y0 + row * PITCH + FILL / 2.0
        ix, iy = int(round(ox + mx * sx)), int(round(oy + my * sy))
        black = tot = 0
        for dy in (-2, 0, 2):
            for dx in (-2, 0, 2):
                x, y = ix + dx, iy + dy
                if 0 <= x < w and 0 <= y < h:
                    tot += 1
                    if px[y * w + x] < 128:
                        black += 1
        return 1 if black * 2 > tot else 0

    bits = [cell_bit(i) for i in range(NBITS)]

    def word(start, n):
        v = 0
        for i in range(n):
            v = (v << 1) | bits[start + i]
        return v

    if word(0, 16) != 0xA55A:
        return None
    return [word(16 + i * 32, 32) for i in range(NVALS)]


def main():
    w, h, px = load_pgm(sys.argv[1])

    # Locate the three calibration squares (assume ~1:1 to seed the search).
    found = [centroid(px, w, h, cx, cy) for cx, cy in CAL]
    if any(f is None for f in found):
        print(f"calibration squares not all found: {found} — no grid / bombed")
        return 2
    (tlx, tly), (trx, tqy), (blx, bly) = found
    sx = (trx - tlx) / (CAL[1][0] - CAL[0][0])       # image px per Mac px, x
    sy = (bly - tly) / (CAL[2][1] - CAL[0][1])       # image px per Mac px, y
    ox = tlx - CAL[0][0] * sx                          # image x of Mac x=0
    oy = tly - CAL[0][1] * sy

    def cell_bit(idx):
        col, row = idx % COLS, idx // COLS
        mx = X0 + col * PITCH + FILL / 2.0
        my = Y0 + row * PITCH + FILL / 2.0
        ix, iy = int(round(ox + mx * sx)), int(round(oy + my * sy))
        black = tot = 0                                # majority vote over 3x3
        for dy in (-2, 0, 2):
            for dx in (-2, 0, 2):
                x, y = ix + dx, iy + dy
                if 0 <= x < w and 0 <= y < h:
                    tot += 1
                    if px[y * w + x] < 128:
                        black += 1
        return 1 if black * 2 > tot else 0

    bits = [cell_bit(i) for i in range(NBITS)]

    def word(start, n):
        v = 0
        for i in range(n):
            v = (v << 1) | bits[start + i]
        return v

    sync = word(0, 16)
    if sync != 0xA55A:
        print(f"BAD SYNC 0x{sync:04X} (expected 0xA55A) — miscalibrated / bombed")
        return 2
    vals = [word(16 + i * 32, 32) for i in range(NVALS)]
    names = ["nfiles", "ret", "errors", "sumDataCRC", "totalDataLen",
             "sumRsrcCRC", "totalRsrcLen", "peakBytes"]
    for n, v in zip(names, vals):
        sv = v - (1 << 32) if v >= (1 << 31) else v
        print(f"  {n:14s} = {v:10d}  (0x{v:08X}, signed {sv})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

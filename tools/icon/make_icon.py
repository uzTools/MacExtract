#!/usr/bin/env python3
"""MacExtract - application icon family for classic Mac OS.

Self-contained: needs only Python 3. Pillow is optional and used solely for
the PNG preview; without it the .r file is still written.

    python3 make_icon.py            # writes macextract_icons.r
    python3 make_icon.py --ascii    # also prints the bitmaps as text

An open carton lettered EXTRACT, with a document and a block rising out of
it. Emits ICN#, ics#, icl4, ics4, icl8, ics8, FREF and BNDL, all at ID 128.

DO NOT REPLACE mac/macextract_icons.r WITH ITS OUTPUT. That file has since
gained resources written by hand and not emitted here -- the '****' FREF
129 and its BNDL entry, and both 'vers' -- and a whole-file regeneration
deletes them silently. Run it elsewhere and splice the members that
changed (DECISIONS.md 2026-10-11, *the icon that did not darken*).
"""
import sys
from collections import deque

OUT_R = "macextract_icons.r"
OUT_PNG = "macextract-icon.png"
CREATOR = "MExt"

# ======================================================== drawing primitives


class C:
    def __init__(self, w=32, h=32):
        self.w, self.h = w, h
        self.g = [[0]*w for _ in range(h)]

    def set(self, x, y, v=1):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.g[y][x] = v

    def hline(self, x0, x1, y, v=1):
        for x in range(min(x0, x1), max(x0, x1)+1):
            self.set(x, y, v)

    def vline(self, x, y0, y1, v=1):
        for y in range(min(y0, y1), max(y0, y1)+1):
            self.set(x, y, v)

    def line(self, x0, y0, x1, y1, v=1):
        dx, dy = abs(x1-x0), -abs(y1-y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx+dy
        while True:
            self.set(x0, y0, v)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2*err
            if e2 >= dy:
                err += dy; x0 += sx
            if e2 <= dx:
                err += dx; y0 += sy

    def rect(self, x0, y0, x1, y1, v=1):
        self.hline(x0, x1, y0, v); self.hline(x0, x1, y1, v)
        self.vline(x0, y0, y1, v); self.vline(x1, y0, y1, v)

    def fill(self, x0, y0, x1, y1, v=1):
        for y in range(y0, y1+1):
            for x in range(x0, x1+1):
                self.set(x, y, v)

    def ascii(self):
        return "\n".join("".join("#" if v else "." for v in r) for r in self.g)


def ruled(c, x0, y0, x1, y1, n=3, fold=0):
    """A sheet of paper with a dog-eared top-right corner and rule lines."""
    c.fill(x0, y0, x1, y1, 0)
    if fold:
        c.hline(x0, x1-fold, y0)
        c.line(x1-fold, y0, x1, y0+fold)
        c.vline(x1-fold, y0, y0+fold)
        c.hline(x1-fold, x1, y0+fold)
        c.vline(x1, y0+fold, y1)
    else:
        c.hline(x0, x1, y0)
        c.vline(x1, y0, y1)
    c.vline(x0, y0, y1)
    step = max(2, (y1-y0-fold)//(n+1))
    y, k = y0+fold+step, 0
    while k < n and y < y1-1:
        c.hline(x0+2, x1-2, y)
        y += step
        k += 1


def square(c, x0, y0, s):
    c.fill(x0, y0, x0+s, y0+s, 0)
    c.rect(x0, y0, x0+s, y0+s)


def boxrect(c, x0, y0, x1, y1):
    c.fill(x0, y0, x1, y1, 0)
    c.vline(x0, y0, y1)
    c.vline(x1, y0, y1)
    c.hline(x0, x1, y1)
    c.hline(x0, x1, y0)


# 3x5 face. N, M and W are omitted on purpose: three columns cannot hold
# their diagonals, and an N drawn this small is indistinguishable from an M.
F35 = {
    'A': [".#.", "#.#", "###", "#.#", "#.#"],
    'C': [".##", "#..", "#..", "#..", ".##"],
    'E': ["###", "#..", "##.", "#..", "###"],
    'R': ["##.", "#.#", "##.", "#.#", "#.#"],
    'T': ["###", ".#.", ".#.", ".#.", ".#."],
    'X': ["#.#", "#.#", ".#.", "#.#", "#.#"],
}


def text_w(s):
    return len(s)*4 - 1


def draw_text(c, s, x, y):
    for ch in s.upper():
        g = F35.get(ch)
        if g:
            for r, row in enumerate(g):
                for k, v in enumerate(row):
                    if v == '#':
                        c.set(x+k, y+r)
        x += 4


# ================================================================= geometry
BOX = (0, 17, 31, 30)
WORD = "EXTRACT"
BOX32 = (BOX[0]+1, BOX[1]+1, BOX[2]-1, BOX[3]-1)
DOC32 = (14, 5, 27, 16)
BLK32 = (4, 9, 11, 16)


def icon32():
    c = C(32, 32)
    square(c, 3, 8, 9)
    ruled(c, 13, 4, 28, 20, n=3, fold=4)
    boxrect(c, *BOX)
    cx = (BOX[0]+BOX[2])//2
    draw_text(c, WORD, cx - text_w(WORD)//2, 22)
    return c


# 16x16 keeps the proportions of 32x32: carton 44% of the height, block
# square, document half the width. Its lettering is one pixel per letter of
# EXTRACT - unreadable by design, so the small icon echoes the large one.
ART16 = [
    "................",
    "................",
    ".......######...",
    ".......#....##..",
    ".#######....###.",
    ".#....##.####.#.",
    ".#....##......#.",
    ".#....##.####.#.",
    ".#....##......#.",
    "################",
    "#..............#",
    "#.#.#.#.#.#.##.#",
    "#.#.....#.#....#",
    "#.#.#.....#.#..#",
    "#..............#",
    "################",
]
BOX16, DOC16 = (1, 10, 14, 14), (8, 3, 13, 8)
BLK16, TEXT16 = (2, 5, 5, 8), (2, 11, 13, 13)


def icon16():
    c = C(16, 16)
    c.g = [[1 if ch == '#' else 0 for ch in r] for r in ART16]
    return c


# ==================================================================== masks
def mask(c, w, h):
    """Opaque silhouette: ink, plus anything the ink encloses."""
    seen = [[False]*w for _ in range(h)]
    q = deque()
    for x in range(w):
        for y in (0, h-1):
            if not c.g[y][x] and not seen[y][x]:
                seen[y][x] = True; q.append((x, y))
    for y in range(h):
        for x in (0, w-1):
            if not c.g[y][x] and not seen[y][x]:
                seen[y][x] = True; q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x+dx, y+dy
            if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] \
                    and not c.g[ny][nx]:
                seen[ny][nx] = True; q.append((nx, ny))
    return [[1 if (c.g[y][x] or not seen[y][x]) else 0 for x in range(w)]
            for y in range(h)]


# ================================================================= palettes
PAL4 = [(255, 255, 255), (252, 243, 5), (255, 100, 3), (221, 9, 7),
        (242, 8, 132), (71, 0, 165), (0, 0, 211), (2, 171, 234),
        (31, 183, 20), (0, 100, 18), (86, 44, 5), (144, 113, 58),
        (192, 192, 192), (128, 128, 128), (64, 64, 64), (0, 0, 0)]
W4, ORA4, CYA4, BLK4 = 0, 2, 7, 15

# 256-colour indices: a 6x6x6 cube plus ramps - see PALETTE in HEADER below.
LEVELS = [255, 204, 153, 102, 51, 0]


def cube(r, g, b):
    def near(v):
        return min(range(6), key=lambda i: abs(LEVELS[i]-v))
    ri, gi, bi = near(r), near(g), near(b)
    return 255 if (ri, gi, bi) == (5, 5, 5) else 36*ri + 6*gi + bi


def rgb_of(i):
    if i == 255:
        return (0, 0, 0)
    if i >= 215:
        return RAMPS[i - 215]
    r, rem = divmod(i, 36)
    g, b = divmod(rem, 6)
    return (LEVELS[r], LEVELS[g], LEVELS[b])


# Apple's 34 icon colours, the ResEdit "Apple Icon Colors" palette.
# Source: Macintosh Human Interface Guidelines, ch. 8, "Selection mechanism
# for color icons" -- "only the 34 colors shown in Figure 8-23 get darkened
# when a color icon is selected"; the RGB values, which the figure does not
# print, from Kreative Korp's MoCCP, gpl/AppleIconColors.gpl. Every 8-bit
# pixel must be one of these, or that part of the icon stays the same shade
# when it is selected -- which the first version's cyan box and orange block
# did, seen on an LC 475 on 2026-10-11 (DECISIONS.md, *the icon that did
# not darken*).
ICON34 = [(255, 255, 204), (255, 204, 153), (204, 153, 102), (255, 102, 51),
          (51, 255, 153), (0, 187, 0), (51, 153, 102), (51, 102, 102),
          (153, 255, 255), (0, 153, 255), (0, 0, 221), (51, 0, 153),
          (204, 204, 255), (153, 153, 255), (102, 102, 204), (51, 51, 102),
          (255, 102, 204), (153, 0, 102), (153, 102, 153), (255, 255, 255),
          (238, 238, 238), (221, 221, 221), (204, 204, 204), (187, 187, 187),
          (170, 170, 170), (136, 136, 136), (119, 119, 119), (85, 85, 85),
          (68, 68, 68), (34, 34, 34), (17, 17, 17), (0, 0, 0),
          (255, 255, 0), (221, 0, 0)]


def icon8(r, g, b):
    """The 256-colour index of one of Apple's 34 icon colours, and only
    those: the ramps at 215-254 included, which cube() cannot reach."""
    assert (r, g, b) in ICON34, (r, g, b)
    if (r, g, b) == (0, 0, 0):
        return 255
    if r in LEVELS and g in LEVELS and b in LEVELS:
        return cube(r, g, b)
    return 215 + RAMPS.index((r, g, b))


# Indices 215-254: four ramps of ten, red, green, blue, grey, each
# 238..17 in steps of 17 minus the cube's multiples of 51. Source: the
# Mac OS 8-bit palette, MoCCP gpl/MacOS8Bit.gpl, which this table was
# checked against entry for entry.
_RAMP = [v for v in range(238, 0, -17) if v % 51]
RAMPS = ([(v, 0, 0) for v in _RAMP] + [(0, v, 0) for v in _RAMP] +
         [(0, 0, v) for v in _RAMP] + [(v, v, v) for v in _RAMP])

CY_HI, CY_MID, CY_LO = (icon8(153, 255, 255), icon8(0, 153, 255),
                        icon8(102, 102, 204))
CY_SHADOW = icon8(102, 102, 204)
OR_HI, OR_MID, OR_LO = (icon8(255, 204, 153), icon8(255, 102, 51),
                        icon8(221, 0, 0))
PAPER, PAPER_LO = icon8(255, 255, 255), icon8(204, 204, 204)
BLACK8, W8 = 255, icon8(255, 255, 255)


def flat(mono, msk, w, boxr, docr, blkr):
    g = [[W4]*w for _ in range(w)]
    for r, idx in ((boxr, CYA4), (docr, W4), (blkr, ORA4)):
        for y in range(r[1], r[3]+1):
            for x in range(r[0], r[2]+1):
                g[y][x] = idx
    for y in range(w):
        for x in range(w):
            if mono[y][x]:
                g[y][x] = BLK4
            elif not msk[y][x]:
                g[y][x] = W4
    return g


def tone(mono, msk, w, boxr, docr, blkr, textr=None):
    """Three tones per surface. textr gets a south-east shadow under the
    lettering - used at 16x16 only, where the one-pixel columns otherwise
    read as loose dots instead of a label."""
    g = [[W8]*w for _ in range(w)]
    bx0, by0, bx1, by1 = boxr
    for y in range(by0, by1+1):
        c = CY_HI if y == by0 else (CY_LO if y == by1 else CY_MID)
        for x in range(bx0, bx1+1):
            g[y][x] = c
    dx0, dy0, dx1, dy1 = docr
    for y in range(dy0, dy1+1):
        for x in range(dx0, dx1+1):
            g[y][x] = PAPER_LO if y == dy1 else PAPER
    kx0, ky0, kx1, ky1 = blkr
    for y in range(ky0, ky1+1):
        for x in range(kx0, kx1+1):
            d = ((x-kx0)/max(1, kx1-kx0) + (y-ky0)/max(1, ky1-ky0))/2
            g[y][x] = OR_HI if d < 0.34 else (OR_LO if d > 0.66 else OR_MID)
    if textr:
        tx0, ty0, tx1, ty1 = textr
        for y in range(ty0, ty1+2):
            for x in range(tx0, tx1+2):
                if 0 <= y < w and 0 <= x < w and not mono[y][x] \
                        and mono[y-1][x-1] and msk[y][x]:
                    g[y][x] = CY_SHADOW
    for y in range(w):
        for x in range(w):
            if mono[y][x]:
                g[y][x] = BLACK8
            elif not msk[y][x]:
                g[y][x] = W8
    return g


# =================================================================== output
def to_hex(g, w, h):
    rows = []
    for y in range(h):
        v = 0
        for x in range(w):
            v = (v << 1) | g[y][x]
        rows.append(v.to_bytes(w//8, "big").hex().upper())
    return rows


def hex4(g, w, h):
    return [bytes((g[y][x] << 4) | g[y][x+1]
                  for x in range(0, w, 2)).hex().upper() for y in range(h)]


def hex8(g, w, h):
    return [bytes(g[y]).hex().upper() for y in range(h)]


def block(rows, per):
    return "\n".join('        $"' + " ".join(rows[k:k+per]) + '"'
                     for k in range(0, len(rows), per))


HEADER = """/* MacExtract - application icon family, classic Mac OS.
   Generated by tools/icon/make_icon.py - edit the script, not the hex.

   An open carton lettered EXTRACT, with a document and a block rising out.
   The label states what the application does; the application is MacExtract.

   All members share resource ID 128. The Finder picks the deepest member the
   screen can show, so this is additive: a 1-bit Mac Plus under System 6 uses
   'ICN#' and never looks at the colour members. The colour members carry no
   mask of their own - the Finder reuses the 'ICN#'/'ics#' mask, which is why
   the colour art is generated from the 1-bit art rather than redrawn.

   'icl4'/'ics4' are flat: the 16-colour table holds no usable cyan shades.
   'icl8'/'ics8' are modelled in three tones per surface. Smooth gradients
   are NOT possible from the colour cube alone - six levels per channel band
   badly over twelve pixels - so the shading is stepped, as period 8-bit
   icons were. The 32x32 lettering is left crisp: the letters sit on the
   pixel grid, so there is no partial coverage to anti-alias and any halo
   merely thickens them. At 16x16 a south-east shadow IS applied, because
   there the one-pixel columns need filling out to read as a label.

   PALETTE: every 'icl8'/'ics8' pixel is one of Apple's 34 icon colours,
   because only those darken when the Finder draws the icon selected
   (Human Interface Guidelines, ch. 8). The indices are the Macintosh
   256-colour palette's - a 6x6x6 cube at 36*r + 6*g + b over the levels
   (255,204,153,102,51,0), four ramps at 215-254 and black at 255 -
   checked entry for entry against MoCCP's MacOS8Bit.gpl.

   After installing, rebuild the Desktop file (hold Cmd-Option at boot) or
   the Finder will keep showing the previous icon.                        */

/* Retro68's Rez has no built-in type declarations: without this include it
   stops at the first resource with "Can't find type definition for 'ICN#'".
   Multiverse.r is the only RInclude that declares ICN#, ics#, icl4, ics4,
   icl8, ics8, FREF and BNDL. */
#include "Multiverse.r"
"""


def signature_hex(text="MacExtract"):
    b = text.encode("mac-roman")[:255]
    return (bytes([len(b)]) + b).hex().upper()


SIGNATURE = signature_hex()


def emit(i32, m32, i16, m16, f32, f16, t32, t16):
    return f"""{HEADER}
resource 'ICN#' (128) {{
    {{  /* icon */
{block(to_hex(i32.g, 32, 32), 2)}
    ,   /* mask */
{block(to_hex(m32, 32, 32), 2)}
    }}
}};

resource 'ics#' (128) {{
    {{  /* icon */
{block(to_hex(i16.g, 16, 16), 4)}
    ,   /* mask */
{block(to_hex(m16, 16, 16), 4)}
    }}
}};

/* 16 colours: 0 white, 2 orange, 7 cyan, 15 black. */

resource 'icl4' (128) {{
{block(hex4(f32, 32, 32), 1)}
}};

resource 'ics4' (128) {{
{block(hex4(f16, 16, 16), 2)}
}};

/* 256 colours, three tones per surface, Apple's icon colours only - see PALETTE above. */

resource 'icl8' (128) {{
{block(hex8(t32, 32, 32), 1)}
}};

resource 'ics8' (128) {{
{block(hex8(t16, 16, 16), 1)}
}};

/* The BNDL owner must match the application's creator code. Keep it in step
   with the creator set in the build and in the 'SIZE' resource.          */

resource 'FREF' (128) {{ 'APPL', 0, "" }};
resource 'BNDL' (128) {{
    '{CREATOR}', 0,
    {{ 'ICN#', {{ 0, 128 }},
       'FREF', {{ 0, 128 }} }}
}};

/* The SIGNATURE resource: type = the creator code, ID 0. The Finder wants
   it present to register an application's bundle; without it the 'BNDL' is
   ignored and the generic application diamond is drawn, with every other
   piece correct. Emitted as raw `data` because Rez has no type declaration
   for an arbitrary four-character type. Contents are conventionally a
   Pascal string describing the application. */
data '{CREATOR}' (0, "MacExtract") {{
    $"{SIGNATURE}"
}};
"""


def preview(path, i32, i16, f32, f16, t32, t16):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow not installed - skipping the PNG preview")
        return
    im = Image.new("RGB", (1010, 560), (238, 238, 238))
    d = ImageDraw.Draw(im)
    sets = [("1-bit  ICN# / ics#", i32.g, i16.g,
             lambda v: (0, 0, 0) if v else (255, 255, 255)),
            ("16 colours  icl4 / ics4", f32, f16, lambda v: PAL4[v]),
            ("256 colours  icl8 / ics8", t32, t16, rgb_of)]
    for i, (name, g32, g16, pal) in enumerate(sets):
        ox = 16 + i*330
        d.text((ox, 10), name, fill="black")
        for y in range(32):
            for x in range(32):
                d.rectangle([ox+x*9, 28+y*9, ox+(x+1)*9-1, 28+(y+1)*9-1],
                            fill=pal(g32[y][x]))
        for y in range(16):
            for x in range(16):
                d.rectangle([ox+x*9, 330+y*9, ox+(x+1)*9-1, 330+(y+1)*9-1],
                            fill=pal(g16[y][x]))
        for j, s in enumerate((1, 2, 3)):
            px = ox + [0, 50, 120][j]
            for y in range(32):
                for x in range(32):
                    d.rectangle([px+x*s, 478+y*s, px+(x+1)*s-1, 478+(y+1)*s-1],
                                fill=pal(g32[y][x]))
            for y in range(16):
                for x in range(16):
                    d.rectangle([px+x*s, 528+y*s, px+(x+1)*s-1, 528+(y+1)*s-1],
                                fill=pal(g16[y][x]))
    im.save(path)
    print("wrote", path)


def main():
    i32, i16 = icon32(), icon16()
    m32, m16 = mask(i32, 32, 32), mask(i16, 16, 16)
    f32 = flat(i32.g, m32, 32, BOX32, DOC32, BLK32)
    f16 = flat(i16.g, m16, 16, BOX16, DOC16, BLK16)
    t32 = tone(i32.g, m32, 32, BOX32, DOC32, BLK32)          # crisp lettering
    t16 = tone(i16.g, m16, 16, BOX16, DOC16, BLK16, TEXT16)  # shadowed
    with open(OUT_R, "w") as f:
        f.write(emit(i32, m32, i16, m16, f32, f16, t32, t16))
    print("wrote", OUT_R)
    preview(OUT_PNG, i32, i16, f32, f16, t32, t16)
    if "--ascii" in sys.argv:
        print("\n32x32:\n" + i32.ascii())
        print("\n16x16:\n" + i16.ascii())


if __name__ == "__main__":
    main()

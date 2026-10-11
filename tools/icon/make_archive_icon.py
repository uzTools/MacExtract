#!/usr/bin/env python3
"""The ARCHIVE document icon — what a MacExtract stub draws on the archives
it claims (DECISIONS.md 2026-10-11, *where the stubs can live*).

    python3 make_archive_icon.py --r archive_icons.r [--id 129]
    python3 make_archive_icon.py --icn out.icn     # raw 'ICN#': icon + mask
    python3 make_archive_icon.py --ics out.ics     # raw 'ics#'
    python3 make_archive_icon.py --preview out.png # every member, enlarged
    python3 make_archive_icon.py --ascii

Apple's blank document carrying MacExtract's own small icon — the
Finder's convention for a document of an application. Emits ICN#, ics#,
icl4, ics4, icl8 and ics8.

**The sheets are Apple's, pixel for pixel**, measured 2026-10-11, not
drawn from memory: the 32x32 is the System 3.0 and 6.0.8 Finders' blank
document, `ICN#` 132 in `Finder` (columns 4-28, a 6-pixel fold; System
7.0.1's `ICN#` -4000 is the same shape one column to the left), and the
16x16 is System 7.0.1's `ics#` -4000 in `System` (columns 1-13, a 3-pixel
fold; System 6 has no small document icon). `page()` below reproduces
both exactly.

The 32x32 miniature IS `make_icon.py`'s 16x16, unchanged, and is coloured
as that one is. The 16x16 cannot hold it, so it keeps the carton, the
lettering row, the block and the folded document, with the block and the
document touching as they do in the application icon. Chosen 2026-10-11
over a ruled variant, a solid carton and four other designs.

**The colours are `make_icon.py`'s**, taken by name, so the two families
stay in step: Apple's 34 icon colours only, because only those darken
when the Finder draws a colour icon selected (that file, *ICON34*).
"""
import argparse, os, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_icon as M                                        # noqa: E402


def page(c, x0, y0, x1, y1, fold):
    """A document outline with its top-right corner folded down."""
    c.hline(x0, x1 - fold, y0)
    c.line(x1 - fold, y0, x1, y0 + fold)
    c.vline(x1 - fold, y0, y0 + fold)
    c.hline(x1 - fold, x1, y0 + fold)
    c.vline(x1, y0 + fold, y1)
    c.vline(x0, y0, y1)
    c.hline(x0, x1, y1)


# Where make_icon.py's 16x16 sits inside the 32x32 sheet: centred in the
# sheet's width, in its lower half.
MINI = (8, 12)


def shift(r, dx, dy):
    return tuple(v + (dx if k % 2 == 0 else dy) for k, v in enumerate(r))


def icon32():
    c = M.C(32, 32)
    page(c, 4, 0, 28, 31, 6)
    for y, row in enumerate(M.ART16):
        for x, ch in enumerate(row):
            if ch == "#":
                c.set(MINI[0] + x, MINI[1] + y)
    return c


# The colour surfaces of the 32x32 are the miniature's, moved to where it
# sits.
BOX32, DOC32 = shift(M.BOX16, *MINI), shift(M.DOC16, *MINI)
BLK32, TEXT32 = shift(M.BLK16, *MINI), shift(M.TEXT16, *MINI)

ART16 = [
    ".##########.....",
    ".#........##....",
    ".#........#.#...",
    ".#........####..",
    ".#...........#..",
    ".#....###....#..",
    ".#.####.##...#..",
    ".#.#.##..#...#..",
    ".#.#########.#..",
    ".#.#.......#.#..",
    ".#.#.#.#.#.#.#..",
    ".#.#.......#.#..",
    ".#.#########.#..",
    ".#...........#..",
    ".#...........#..",
    ".#############..",
]
# Its surfaces, stated as make_icon.py states its own: interiors, with the
# ink drawn over them.
BOX16, DOC16, BLK16, TEXT16 = ((4, 9, 10, 11), (7, 6, 8, 7), (4, 7, 4, 7),
                               (4, 10, 10, 10))


def icon16():
    c = M.C(16, 16)
    c.g = [[1 if ch == "#" else 0 for ch in r] for r in ART16]
    return c


def family():
    i32, i16 = icon32(), icon16()
    m32, m16 = M.mask(i32, 32, 32), M.mask(i16, 16, 16)
    f32 = M.flat(i32.g, m32, 32, BOX32, DOC32, BLK32)
    f16 = M.flat(i16.g, m16, 16, BOX16, DOC16, BLK16)
    # Both lettering rows are one pixel high, as make_icon.py's own 16x16
    # is, so both take its south-east shadow.
    t32 = M.tone(i32.g, m32, 32, BOX32, DOC32, BLK32, TEXT32)
    t16 = M.tone(i16.g, m16, 16, BOX16, DOC16, BLK16, TEXT16)
    # The 16x16 block's interior is one pixel, and tone() shades a lone
    # pixel as the highlight of a gradient, which nearly vanishes against
    # the paper; the middle orange is what reads as the block.
    t16[BLK16[1]][BLK16[0]] = M.OR_MID
    return i32, i16, m32, m16, f32, f16, t32, t16


def packed(g, w):
    """Rows of 1-bit pixels, MSB first — the layout of 'ICN#' and 'ics#'."""
    out = bytearray()
    for row in g:
        for x in range(0, w, 8):
            b = 0
            for k in range(8):
                b = (b << 1) | row[x + k]
            out.append(b)
    return bytes(out)


def resources():
    """The family as raw resource data, by type — for a tool that writes
    resource forks itself rather than through Rez (companion/make_stub.py)."""
    i32, i16, m32, m16, f32, f16, t32, t16 = family()
    raw = lambda rows: bytes.fromhex("".join(rows))
    return {b"ICN#": packed(i32.g, 32) + packed(m32, 32),
            b"ics#": packed(i16.g, 16) + packed(m16, 16),
            b"icl4": raw(M.hex4(f32, 32, 32)), b"ics4": raw(M.hex4(f16, 16, 16)),
            b"icl8": raw(M.hex8(t32, 32, 32)), b"ics8": raw(M.hex8(t16, 16, 16))}


def emit(rid, i32, i16, m32, m16, f32, f16, t32, t16):
    B, H = M.block, M.to_hex
    return f"""/* MacExtract - the ARCHIVE document icon, for the stubs that claim
   archives for it. Generated by tools/icon/make_archive_icon.py - edit
   the script, not the hex. */

#include "Multiverse.r"

resource 'ICN#' ({rid}, "Archive") {{
    {{  /* icon */
{B(H(i32.g, 32, 32), 2)}
    ,   /* mask */
{B(H(m32, 32, 32), 2)}
    }}
}};

resource 'ics#' ({rid}, "Archive") {{
    {{  /* icon */
{B(H(i16.g, 16, 16), 4)}
    ,   /* mask */
{B(H(m16, 16, 16), 4)}
    }}
}};

resource 'icl4' ({rid}, "Archive") {{
{B(M.hex4(f32, 32, 32), 1)}
}};

resource 'ics4' ({rid}, "Archive") {{
{B(M.hex4(f16, 16, 16), 2)}
}};

resource 'icl8' ({rid}, "Archive") {{
{B(M.hex8(t32, 32, 32), 1)}
}};

resource 'ics8' ({rid}, "Archive") {{
{B(M.hex8(t16, 16, 16), 1)}
}};
"""


def preview(path, i32, i16, f32, f16, t32, t16, scale=8):
    """1-bit, 16 and 256 colours side by side, each 32x32 over its 16x16
    at twice the scale. A PPM converted with ImageMagick: no Pillow."""
    mono = lambda g: [[(0, 0, 0) if v else (255, 255, 255) for v in r] for r in g]
    sets = [(mono(i32.g), mono(i16.g)),
            ([[M.PAL4[v] for v in r] for r in f32], [[M.PAL4[v] for v in r] for r in f16]),
            ([[M.rgb_of(v) for v in r] for r in t32], [[M.rgb_of(v) for v in r] for r in t16])]
    gap, cell = 2 * scale, 32 * scale
    W = len(sets) * (cell + gap) + gap
    H = 2 * cell + 3 * gap
    img = [[(204, 204, 204)] * W for _ in range(H)]
    for i, (g32, g16) in enumerate(sets):
        ox = gap + i * (cell + gap)
        for g, oy, s in ((g32, gap, scale), (g16, 2 * gap + cell, 2 * scale)):
            for y, row in enumerate(g):
                for x, rgb in enumerate(row):
                    for yy in range(s):
                        img[oy + y * s + yy][ox + x * s:ox + (x + 1) * s] = [rgb] * s
    with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as f:
        f.write(f"P6\n{W} {H}\n255\n".encode())
        f.write(bytes(v for row in img for px in row for v in px))
    subprocess.run(["convert", f.name, path], check=True)
    os.unlink(f.name)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--r", help="write the Rez source for the whole family")
    ap.add_argument("--id", type=int, default=129)
    ap.add_argument("--icn")
    ap.add_argument("--ics")
    ap.add_argument("--preview")
    ap.add_argument("--ascii", action="store_true")
    a = ap.parse_args()
    fam = family()
    i32, i16, m32, m16, f32, f16, t32, t16 = fam
    icn = packed(i32.g, 32) + packed(m32, 32)
    ics = packed(i16.g, 16) + packed(m16, 16)
    assert len(icn) == 256 and len(ics) == 64
    if a.r:
        open(a.r, "w").write(emit(a.id, *fam))
    if a.icn:
        open(a.icn, "wb").write(icn)
    if a.ics:
        open(a.ics, "wb").write(ics)
    if a.preview:
        preview(a.preview, i32, i16, f32, f16, t32, t16)
    if a.ascii:
        print(i32.ascii() + "\n\n" + i16.ascii())


if __name__ == "__main__":
    main()

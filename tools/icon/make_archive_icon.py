#!/usr/bin/env python3
"""The ARCHIVE document icon — what a MacExtract stub draws on the archives
it claims (DECISIONS.md 2026-10-11, *where the stubs can live*).

    python3 make_archive_icon.py --icn out.icn     # raw 'ICN#': icon + mask
    python3 make_archive_icon.py --ics out.ics     # raw 'ics#'
    python3 make_archive_icon.py --pbm DIR         # 32 and 16 as PBM
    python3 make_archive_icon.py --ascii

A dog-eared document whose lower half IS the application's carton,
lettered EXTRACT pixel for pixel as `make_icon.py` draws it: the
application is that carton with a document rising out, an archive is a
document that is that carton. Chosen over a parcel tied with twine, which
read as packed but not as MacExtract's (2026-10-11), and over the carton
with its flaps closed, which read as a tray. 1-bit only for now;
the colour members `make_icon.py` derives for the application are not
made here.

Uses `make_icon.py`'s canvas and mask, so the mask rule is the
application's: ink, plus anything the ink encloses.
"""
import argparse, os, sys

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


def icon32():
    c = M.C(32, 32)
    page(c, 0, 0, 31, M.BOX[3], 8)      # the page ends where the carton does
    for y, x1 in ((5, 20), (8, 20), (11, 26)):
        c.hline(4, x1, y)
    M.boxrect(c, *M.BOX)
    cx = (M.BOX[0] + M.BOX[2]) // 2
    M.draw_text(c, M.WORD, cx - M.text_w(M.WORD) // 2, 22)
    return c


def icon16():
    """The application's own 16x16 carton, rows 9-15, under a folded page."""
    c = M.C(16, 16)
    page(c, 0, 0, 15, 9, 5)
    c.hline(2, 7, 2); c.hline(2, 7, 4); c.hline(2, 12, 7)
    for y in range(9, 16):
        c.g[y] = [1 if ch == "#" else 0 for ch in M.ART16[y]]
    return c


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


def family():
    i32, i16 = icon32(), icon16()
    icn = packed(i32.g, 32) + packed(M.mask(i32, 32, 32), 32)
    ics = packed(i16.g, 16) + packed(M.mask(i16, 16, 16), 16)
    return i32, i16, icn, ics


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--icn")
    ap.add_argument("--ics")
    ap.add_argument("--pbm")
    ap.add_argument("--ascii", action="store_true")
    a = ap.parse_args()
    i32, i16, icn, ics = family()
    assert len(icn) == 256 and len(ics) == 64
    if a.icn:
        open(a.icn, "wb").write(icn)
    if a.ics:
        open(a.ics, "wb").write(ics)
    if a.pbm:
        for c, n in ((i32, 32), (i16, 16)):
            with open(os.path.join(a.pbm, f"archive{n}.pbm"), "w") as f:
                f.write(f"P1\n{n} {n}\n" + "\n".join(
                    " ".join(str(v) for v in r) for r in c.g) + "\n")
    if a.ascii:
        print(i32.ascii() + "\n\n" + i16.ascii())


if __name__ == "__main__":
    main()

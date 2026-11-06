#!/usr/bin/env python3
"""Put an icon designer's families into MacExtract's Rez sources.

    tools/icon/import_icons.py ICONS.rsrc [--app 131] [--doc 134]

ICONS.rsrc is a resource fork (`macextract x` writes one beside the file
it extracts) holding ICN#, ics#, icl4, ics4, icl8 and ics8 families. The
--app family becomes the application's, ID 128 in mac/macextract_icons.r;
the --doc family the archive document icon, ID 129 in
mac/macextract_archive_icons.r, which the companion helpers carry too
(tools/icon/make_archive_icon.py reads it back for them). Only those
twelve resources are rewritten: the FREFs, the BNDL, the signature and
both 'vers' in macextract_icons.r are left as they stand.

Refused, before anything is written:
- a family missing any of the six members;
- a 1-bit pixel outside its mask, which the Finder would never draw;
- an 'icl8'/'ics8' pixel outside Apple's 34 icon colours, which would
  not darken when the Finder draws the icon selected (Macintosh Human
  Interface Guidelines, ch. 8; DECISIONS.md 2026-10-11, *the icon that
  did not darken*). The colour members carry no mask: the Finder uses the
  1-bit one, so only pixels inside it are checked.

After installing, rebuild the Desktop file (hold Cmd-Option at boot) or
the Finder keeps showing the previous icon.
"""
import argparse
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_R = os.path.join(ROOT, "mac", "macextract_icons.r")
DOC_R = os.path.join(ROOT, "mac", "macextract_archive_icons.r")
FAMILY = ("ICN#", "ics#", "icl4", "ics4", "icl8", "ics8")
SIZE = {"ICN#": 256, "ics#": 64, "icl4": 512, "ics4": 128, "icl8": 1024,
        "ics8": 256}

# Apple's 34 icon colours, the ResEdit "Apple Icon Colors" palette.
# Source: Macintosh Human Interface Guidelines, ch. 8; the RGB values from
# Kreative Korp's MoCCP, gpl/AppleIconColors.gpl.
ICON34 = [(255, 255, 204), (255, 204, 153), (204, 153, 102), (255, 102, 51),
          (51, 255, 153), (0, 187, 0), (51, 153, 102), (51, 102, 102),
          (153, 255, 255), (0, 153, 255), (0, 0, 221), (51, 0, 153),
          (204, 204, 255), (153, 153, 255), (102, 102, 204), (51, 51, 102),
          (255, 102, 204), (153, 0, 102), (153, 102, 153), (255, 255, 255),
          (238, 238, 238), (221, 221, 221), (204, 204, 204), (187, 187, 187),
          (170, 170, 170), (136, 136, 136), (119, 119, 119), (85, 85, 85),
          (68, 68, 68), (34, 34, 34), (17, 17, 17), (0, 0, 0),
          (255, 255, 0), (221, 0, 0)]
# The Macintosh 256-colour palette: a 6x6x6 cube at 36*r + 6*g + b over
# these levels, four ramps of ten at 215-254, black at 255. Source: MoCCP,
# gpl/MacOS8Bit.gpl, checked entry for entry.
LEVELS = [255, 204, 153, 102, 51, 0]
_RAMP = [v for v in range(238, 0, -17) if v % 51]
RAMPS = ([(v, 0, 0) for v in _RAMP] + [(0, v, 0) for v in _RAMP] +
         [(0, 0, v) for v in _RAMP] + [(v, v, v) for v in _RAMP])


def rgb_of(i):
    if i == 255:
        return (0, 0, 0)
    if i >= 215:
        return RAMPS[i - 215]
    r, rem = divmod(i, 36)
    g, b = divmod(rem, 6)
    return (LEVELS[r], LEVELS[g], LEVELS[b])


def resources(fork):
    """{(type, id): data} of a resource fork (Inside Macintosh: More
    Macintosh Toolbox, Resource Manager, *Resource File Format*)."""
    doff, moff, _dlen, mlen = struct.unpack(">IIII", fork[:16])
    m = fork[moff:moff + mlen]
    tl = struct.unpack(">H", m[24:26])[0]
    out = {}
    for i in range(struct.unpack(">H", m[tl:tl + 2])[0] + 1):
        typ, cnt, ref = struct.unpack(">4sHH", m[tl + 2 + 8 * i:tl + 10 + 8 * i])
        for j in range(cnt + 1):
            e = tl + ref + 12 * j
            rid, _noff, ao = struct.unpack(">hHI", m[e:e + 8])
            at = doff + (ao & 0xFFFFFF)
            n = struct.unpack(">I", fork[at:at + 4])[0]
            out[(typ.decode("mac-roman"), rid)] = fork[at + 4:at + 4 + n]
    return out


def family(res, rid):
    fam = {}
    for t in FAMILY:
        d = res.get((t, rid))
        if d is None:
            raise SystemExit("import_icons: %s %d is missing" % (t, rid))
        if len(d) != SIZE[t]:
            raise SystemExit("import_icons: %s %d is %d bytes, not %d"
                             % (t, rid, len(d), SIZE[t]))
        fam[t] = d
    ok = {i for i in range(256) if rgb_of(i) in ICON34}
    for t1, t8, w in (("ICN#", "icl8", 32), ("ics#", "ics8", 16)):
        n = w * w // 8
        bits = lambda d, o: [(d[o + k // 8] >> (7 - k % 8)) & 1 for k in range(w * w)]
        icon, mask = bits(fam[t1], 0), bits(fam[t1], n)
        stray = sum(1 for k in range(w * w) if icon[k] and not mask[k])
        if stray:
            raise SystemExit("import_icons: %s %d has %d pixel(s) outside its "
                             "mask" % (t1, rid, stray))
        off = sorted({fam[t8][k] for k in range(w * w)
                      if mask[k] and fam[t8][k] not in ok})
        if off:
            raise SystemExit("import_icons: %s %d uses colour(s) %s, not among "
                             "Apple's 34 icon colours" % (t8, rid, off))
    return fam


def rez(t, rid, d):
    """One resource as Rez source, in the layout the files already use."""
    h = d.hex().upper()
    row = {"ICN#": 8, "ics#": 4, "icl4": 32, "ics4": 16, "icl8": 64,
           "ics8": 32}[t]                     # hex digits per pixel row
    per = {"ICN#": 2, "ics#": 4, "icl4": 1, "ics4": 2, "icl8": 1, "ics8": 1}[t]
    rows = [h[k:k + row] for k in range(0, len(h), row)]
    def block(rs):
        return "\n".join('        $"' + " ".join(rs[k:k + per]) + '"'
                         for k in range(0, len(rs), per))
    if t in ("ICN#", "ics#"):
        half = len(rows) // 2
        body = ("    {  /* icon */\n" + block(rows[:half]) +
                "\n    ,   /* mask */\n" + block(rows[half:]) + "\n    }")
    else:
        body = block(rows)
    return "resource '%s' (%d) {\n%s\n};" % (t, rid, body)


def splice(path, rid, fam):
    src = open(path).read()
    for t in FAMILY:
        pat = re.compile(r"resource '%s' \(%d\) \{.*?\n\};" % (re.escape(t), rid),
                         re.S)
        if len(pat.findall(src)) != 1:
            raise SystemExit("import_icons: %s: not one %s %d to replace"
                             % (path, t, rid))
        src = pat.sub(lambda _m: rez(t, rid, fam[t]), src)
    open(path, "w").write(src)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rsrc", help="a resource fork holding the families")
    ap.add_argument("--app", type=int, default=131,
                    help="the application's family (default 131)")
    ap.add_argument("--doc", type=int, default=134,
                    help="the archive document's family (default 134)")
    ap.add_argument("--app-r", default=APP_R)
    ap.add_argument("--doc-r", default=DOC_R)
    a = ap.parse_args()
    res = resources(open(a.rsrc, "rb").read())
    app, doc = family(res, a.app), family(res, a.doc)
    splice(a.app_r, 128, app)
    splice(a.doc_r, 129, doc)
    print("import_icons: %d -> %s 128, %d -> %s 129"
          % (a.app, a.app_r, a.doc, a.doc_r))


if __name__ == "__main__":
    main()

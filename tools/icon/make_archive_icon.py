#!/usr/bin/env python3
"""The ARCHIVE document icon, read back from mac/macextract_archive_icons.r
for what writes resource forks itself: the companion helpers carry it
(companion/make_stub.py), and tools/vmac/deskclaim.py takes its 1-bit
members. The art comes from tools/icon/import_icons.py; this only reads.

    python3 make_archive_icon.py --icn out.icn     # raw 'ICN#': icon + mask
    python3 make_archive_icon.py --ics out.ics     # raw 'ics#'
    python3 make_archive_icon.py --ascii           # the 1-bit members
"""
import argparse
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC_R = os.path.join(ROOT, "mac", "macextract_archive_icons.r")
FAMILY = ("ICN#", "ics#", "icl4", "ics4", "icl8", "ics8")


def resources(path=DOC_R, rid=129):
    """The family as raw resource data, by type (bytes keys)."""
    src = open(path).read()
    out = {}
    for t in FAMILY:
        m = re.findall(r"resource '%s' \(%d\) \{(.*?)\n\};" % (re.escape(t), rid),
                       src, re.S)
        if len(m) != 1:
            raise SystemExit("make_archive_icon: %s: not one %s %d" % (path, t, rid))
        out[t.encode()] = bytes.fromhex("".join(
            "".join(s.split()) for s in re.findall(r'\$"([0-9A-Fa-f ]*)"', m[0])))
    return out


def ascii(data, w):
    n = w * w // 8
    bit = lambda o, k: (data[o + k // 8] >> (7 - k % 8)) & 1
    return "\n".join("".join("#" if bit(0, y * w + x) else
                             ("." if bit(n, y * w + x) else " ")
                             for x in range(w)) for y in range(w))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--icn")
    ap.add_argument("--ics")
    ap.add_argument("--ascii", action="store_true")
    a = ap.parse_args()
    r = resources()
    assert len(r[b"ICN#"]) == 256 and len(r[b"ics#"]) == 64
    if a.icn:
        open(a.icn, "wb").write(r[b"ICN#"])
    if a.ics:
        open(a.ics, "wb").write(r[b"ics#"])
    if a.ascii:
        print(ascii(r[b"ICN#"], 32) + "\n\n" + ascii(r[b"ics#"], 16))


if __name__ == "__main__":
    main()

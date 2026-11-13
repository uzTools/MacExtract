#!/usr/bin/env python3
"""make_stub.py — turn the one stub build into the stub for one creator.

    python3 companion/make_stub.py build/stub/Stub.bin --creator 'SIT!' \\
        --types 'SIT!' -o 'SIT! Helper.bin'

The Finder hands a double-clicked document only to an application whose
own creator is the document's, and registers an application for good only
by a bundle filed under its creator (DECISIONS.md 2026-10-10, *the
double-click that goes by the application's creator*; 2026-10-11, *where
the stubs can live*). So each stub carries:

  - the file creator it claims, and the Finder's hasBundle flag, which
    nothing in the Retro68 chain sets (tools/icon/set_bundle_bit.py);
  - a 'BNDL' owned by that creator, its signature resource, and 'FREF's:
    'APPL' for itself and one per document type, all local icon 0;
  - an 'open' resource listing the types it claims that MacExtract's own
    bundle does not: none for every helper but DiskDoubler's, so that
    Macintosh Easy Open does not offer a helper beside MacExtract for an
    orphaned document (DECISIONS.md 2026-11-13, *the helper that is not
    offered*), and DiskDoubler's 40 icon types for that one, which
    MacExtract's bundle leaves to it, so that it is what Easy Open offers
    for them (*the helper Easy Open offers for DiskDoubler's icons*);
  - one icon family, the archive icon, read from
    mac/macextract_archive_icons.r (tools/icon/make_archive_icon.py),
    for the helper and its documents alike: a second family, MacExtract's
    own for the helper, cost each helper file 2,304 B, and the maintainer
    chose the space (2026-11-03).

The resource-fork and MacBinary code is tools/vmac/deskclaim.py's, which
the stand-in stubs of 2026-10-10/11 were written with.
"""
import argparse, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "vmac"))
sys.path.insert(0, os.path.join(ROOT, "tools", "icon"))
import deskclaim as D                                         # noqa: E402
import make_archive_icon as A                                 # noqa: E402

FAMILY = (b"ICN#", b"ics#", b"icl4", b"ics4", b"icl8", b"ics8")
ICON = 128
PURGEABLE = 0x20
HAS_BUNDLE, INITED = 0x2000, 0x0100


def ostype(s):
    b = s.encode("mac_roman")
    if len(b) != 4:
        raise SystemExit(f"make_stub: {s!r} is not a four-character code")
    return b


def bndl(owner, ntypes):
    """Source: Inside Macintosh: Macintosh Toolbox Essentials, Finder
    Interface, the bundle resource — owner, owner ID 0, type count - 1, then
    per type its pair count - 1 and (local ID, resource ID) pairs."""
    icn = struct.pack(">Hhh", 0, 0, ICON)
    frefs = [(0, 128)] + [(1, 129 + k) for k in range(ntypes)]
    fref = struct.pack(">H", len(frefs) - 1) + b"".join(
        struct.pack(">hh", l, r) for l, r in frefs)
    return owner + struct.pack(">hH", 0, 1) + b"ICN#" + icn + b"FREF" + fref


def unc_version():
    """UNC_VERSION, from include/macextract.h: the helpers carry
    MacExtract's own version (the maintainer, 2026-11-04)."""
    for line in open(os.path.join(ROOT, "include", "macextract.h")):
        if line.startswith("#define UNC_VERSION "):
            return line.split('"')[1]
    raise SystemExit("make_stub: no UNC_VERSION in include/macextract.h")


def vers(version, what):
    """A 'vers' resource. Source: the Rez template in Retro68's
    Multiverse.r — major, minor-and-bug-fix, stage (release $80),
    non-release revision, region (verUS 0), short and long version
    strings. Filled as mac/macextract_icons.r fills MacExtract's: byte 2 is
    the minor written as two hex digits that read as the number, since the
    field's BCD nibbles cannot hold a minor over 9."""
    major, minor = (int(x) for x in version.split(".")[:2])
    sv, lv = version.encode("mac_roman"), f"{version}, {what}".encode("mac_roman")
    return (bytes([int(str(major), 16), int(str(minor % 100), 16), 0x80, 0])
            + struct.pack(">h", 0) + bytes([len(sv)]) + sv
            + bytes([len(lv)]) + lv)


def stamp(stub, creator, types, name=None, version=None):
    """The stub build's MacBinary `stub` made the helper for `creator`
    (four bytes) and `types` (a list of four-byte codes), named `name` in
    its MacBinary header if given, carrying `version` (MacExtract's
    UNC_VERSION by default) in 'vers' 1, which Get Info shows."""
    h, d, r = D.macbin_split(stub)
    res, fattr = D.rsrc_read(r)
    if any(t in (b"BNDL", b"FREF") + FAMILY for t, *_ in res):
        raise SystemExit("make_stub: the stub build already has a bundle")

    for t, data in A.resources().items():
        res.append((t, ICON, PURGEABLE, None, data))
    res.append((b"FREF", 128, PURGEABLE, None, b"APPL" + struct.pack(">h", 0) + b"\0"))
    for k, t in enumerate(types):
        res.append((b"FREF", 129 + k, PURGEABLE, None, t + struct.pack(">h", 0) + b"\0"))
    res.append((b"BNDL", 128, PURGEABLE, None, bndl(creator, len(types))))
    # The 'open' lists what Easy Open may offer this helper for: the types
    # it claims that MacExtract's own bundle does not, so that no orphaned
    # document gets two rows, MacExtract's and a helper's (DECISIONS.md
    # 2026-11-13, *the helper that is not offered*, *the helper Easy Open
    # offers for DiskDoubler's icons*). Source: Inside Macintosh: More
    # Macintosh Toolbox, 7-44, Figure 7-11: signature, filler 0, file type
    # count, the types.
    res.append((b"open", 128, PURGEABLE, None, open_resource(creator, types)))
    sig = b"MacExtract helper"
    res.append((creator, 0, PURGEABLE, None, bytes([len(sig)]) + sig))
    res.append((b"vers", 1, PURGEABLE, None,
                vers(version or unc_version(), "MacExtract helper")))

    h = bytearray(h)
    if name is not None:
        # Source: the MacBinary II header, as tools/vmac/deskclaim.py reads
        # it: the name's length at 1 and its bytes from 2, 63 at most.
        n = name.encode("mac_roman")[:63]
        h[1:65] = bytes([len(n)]) + n + b"\0" * (63 - len(n))
    h[69:73] = creator
    flags = ((h[73] << 8) | h[101] | HAS_BUNDLE) & ~INITED
    h[73], h[101] = flags >> 8, flags & 0xFF
    return D.macbin_join(bytes(h), d, D.rsrc_write(res, fattr))


def main_app_types(path=os.path.join(ROOT, "mac", "macextract_icons.r")):
    """The types MacExtract's own bundle claims: its 'FREF's."""
    import re
    out = set()
    for m in re.finditer(r"^resource 'FREF' \(\d+\) \{ '(.{4})'",
                         open(path, encoding="mac_roman").read(), re.M):
        out.add(m.group(1).encode("mac_roman"))
    if len(out) < 20:
        raise SystemExit("make_stub: read %d FREFs from %s" % (len(out), path))
    return out


def open_resource(creator, types):
    """'open' 128 for a helper claiming `types`: the ones MacExtract's own
    bundle does not claim, in the helper's order."""
    main = main_app_types()
    own = [t for t in types if t not in main]
    return creator + struct.pack(">hH", 0, len(own)) + b"".join(own)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stub", help="the stub build's MacBinary (Stub.bin)")
    ap.add_argument("--creator", required=True)
    ap.add_argument("--types", nargs="+", required=True,
                    help="document types this creator writes")
    ap.add_argument("--name", help="the file name in the MacBinary header")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    out = stamp(open(a.stub, "rb").read(), ostype(a.creator),
                [ostype(t) for t in a.types], a.name)
    open(a.out, "wb").write(out)
    print(f"make_stub: {a.out}: creator {a.creator}, types {' '.join(a.types)}")


if __name__ == "__main__":
    main()

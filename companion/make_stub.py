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
  - one icon family, the archive icon (tools/icon/make_archive_icon.py),
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stub", help="the stub build's MacBinary (Stub.bin)")
    ap.add_argument("--creator", required=True)
    ap.add_argument("--types", nargs="+", required=True,
                    help="document types this creator writes")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    creator = ostype(a.creator)
    types = [ostype(t) for t in a.types]

    h, d, r = D.macbin_split(open(a.stub, "rb").read())
    res, fattr = D.rsrc_read(r)
    if any(t in (b"BNDL", b"FREF") + FAMILY for t, *_ in res):
        raise SystemExit("make_stub: the stub build already has a bundle")

    for t, data in A.resources().items():
        res.append((t, ICON, PURGEABLE, None, data))
    res.append((b"FREF", 128, PURGEABLE, None, b"APPL" + struct.pack(">h", 0) + b"\0"))
    for k, t in enumerate(types):
        res.append((b"FREF", 129 + k, PURGEABLE, None, t + struct.pack(">h", 0) + b"\0"))
    res.append((b"BNDL", 128, PURGEABLE, None, bndl(creator, len(types))))
    sig = b"MacExtract helper"
    res.append((creator, 0, PURGEABLE, None, bytes([len(sig)]) + sig))

    h = bytearray(h)
    h[69:73] = creator
    flags = ((h[73] << 8) | h[101] | HAS_BUNDLE) & ~INITED
    h[73], h[101] = flags >> 8, flags & 0xFF
    open(a.out, "wb").write(D.macbin_join(bytes(h), d, D.rsrc_write(res, fattr)))
    print(f"make_stub: {a.out}: creator {a.creator}, types {' '.join(a.types)}")


if __name__ == "__main__":
    main()

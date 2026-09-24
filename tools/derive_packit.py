#!/usr/bin/env python3
"""derive_packit.py — read PackIt from the FORMAT's own published
description, and say where that description is wrong.

The inventory said PackIt's container could only come from macutils'
`macunpack/pit.c`, because "PackIt's own format is trivial; the app is
not here". Both halves were beside the point: the format is
**published**, in a 1986 freeware document that describes it field by
field, and `tools/fetch_references.sh` fetches it since 2026-09-21:

    reference/notes/packit_unpackit.txt

That is R. Scott McGinnis's `UNPACKIT.DOC`, appendices B and C — the
manual of a DOS extractor, written from the Macintosh side by somebody
who was not Harry Chesley. The page that named it is
`reference/notes/PackIt.md`, which this project had had since the
first reference fetch and had never followed.

This reader is written from that document and from this project's own
`docs/formats/serialized-huffman-tree.md` — not from `pit.c`, not from
XADMaster. The corrections the document needs are marked
**CORRECTION** below and in `docs/formats/packit.md`.

    tools/derive_packit.py [archive ...]

Not in `ci.sh`: it needs the fixtures, which are not committed.
"""
import argparse
import glob
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "reference", "notes", "packit_unpackit.txt")

# Appendix B's table of subfile types. It lists "PMa5" twice, for
# simple encryption and for DES; macutils' README.unpit knows only the
# first two. Neither encrypted form appears in the corpus.
STORED, HUFF, END = b"PMag", b"PMa4", b"PEnd"
ENCRYPTED = (b"PMa5", b"PMa6")

HDR = 94                # appendix C's header, its own CRC included


class Bits:
    """Most-significant bit first, the stream running forward."""
    __slots__ = ("d", "p")

    def __init__(self, d, at):
        self.d = d
        self.p = at * 8

    def bit(self):
        if (self.p >> 3) >= len(self.d):
            raise EOFError
        v = (self.d[self.p >> 3] >> (7 - (self.p & 7))) & 1
        self.p += 1
        return v

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v


def read_tree(bs):
    """The bit-serialized tree: 1 is a leaf and eight bits of symbol,
    0 is an internal node followed by its zero and one subtrees.

    Source: docs/formats/serialized-huffman-tree.md, this project's
    own, derived from the output of the three formats that write one.
    The UNPACKIT document does not describe the compression at all —
    it says "huffman encoded" and stops.
    """
    if bs.bit():
        return bs.bits(8)
    zero = read_tree(bs)
    one = read_tree(bs)
    return (zero, one)


def decode(bs, tree, n):
    out = bytearray()
    while len(out) < n:
        node = tree
        while isinstance(node, tuple):
            node = node[bs.bit()]
        out.append(node)
    return bytes(out)


def header(h):
    """Appendix C, field for field.

    CORRECTION: the appendix gives the name as "NameLen 1, Name 63" and
    then lists no padding, so a reader that takes the length at face
    value walks off by however much the name is short of 63. The field
    is FIXED: one length byte and 63 bytes of name whatever the length
    says. Every entry in the corpus has it.
    """
    nlen = h[0]
    name = h[1:1 + min(nlen, 63)].decode("mac-roman", "replace")
    dsize = int.from_bytes(h[76:80], "big")
    rsize = int.from_bytes(h[80:84], "big")
    return name, dsize, rsize


def entries(d, at=0):
    """Walk the concatenated subfiles.

    CORRECTION: appendix B says a PackIt file begins with a MacBinary
    header, and the corpus says otherwise — four of its five specimens
    start at the first type word. MacBinary is how a `.pit` crossed a
    modem in 1986, not part of the format; the one specimen that has
    one is named `.bin` here for that reason.
    """
    out = []
    while at + 4 <= len(d):
        kind = d[at:at + 4]
        if kind == END:
            return out
        if kind == STORED:
            h = d[at + 4:at + 4 + HDR]
            if len(h) < HDR:
                return out
            name, dsize, rsize = header(h)
            p = at + 4 + HDR
            out.append((name, kind, d[p:p + dsize], d[p + dsize:p + dsize + rsize]))
            # ... the forks, then the two-byte CRC over both.
            at = p + dsize + rsize + 2
            continue
        if kind == HUFF:
            bs = Bits(d, at + 4)
            tree = read_tree(bs)
            # The header is coded INTO the same stream as the forks, so
            # the sizes that say how long the stream is are inside it.
            h = decode(bs, tree, HDR)
            name, dsize, rsize = header(h)
            body = decode(bs, tree, dsize + rsize + 2)
            out.append((name, kind, body[:dsize], body[dsize:dsize + rsize]))
            at = (bs.p + 7) // 8
            continue
        if kind in ENCRYPTED:
            out.append((None, kind, None, None))
            return out
        return out
    return out


def check(path):
    d = open(path, "rb").read()
    mp = os.path.join(ROOT, "fixtures", "manifests",
                      os.path.basename(path) + ".json")
    if not os.path.exists(mp):
        return 0, 0
    start = 0
    if d[:4] not in (STORED, HUFF, END) and len(d) > 128 + 4:
        start = 128                       # a MacBinary envelope
    want = {}
    for e in json.load(open(mp))["entries"]:
        for kind in ("data", "rsrc"):
            sha = e.get(kind + "_sha256")
            if sha:
                want[(e["name"], kind)] = sha
    ok = bad = 0
    for name, kind, data, rsrc in entries(d, start):
        if data is None:
            print(f"  --   {name} {kind.decode()} encrypted, out of scope")
            continue
        for what, blob in (("data", data), ("rsrc", rsrc)):
            sha = want.get((name, what))
            if sha is None:
                continue
            if hashlib.sha256(blob).hexdigest() == sha:
                ok += 1
            else:
                print(f"  --   {name[-28:]:30s} {what} {len(blob):7d} B  "
                      f"not read here ({kind.decode()})")
                bad += 1
    return ok, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixtures", nargs="*")
    a = ap.parse_args()
    if not os.path.exists(DOC):
        print("derive-packit: no reference/notes/packit_unpackit.txt — run "
              "tools/fetch_references.sh (skipped)")
        return 0
    paths = a.fixtures or sorted(glob.glob(os.path.join(ROOT, "fixtures", "*.pit"))
                                 + glob.glob(os.path.join(ROOT, "fixtures", "*pit*.bin")))
    if not paths:
        print("derive-packit: no fixtures here (skipped)")
        return 0
    tok = tbad = narch = 0
    for p in paths:
        ok, bad = check(p)
        if ok or bad:
            narch += 1
            print(f"{os.path.basename(p):40s} {ok:3d} fork(s)"
                  + (f", {bad} not" if bad else ""))
        tok += ok
        tbad += bad
    print(f"derive-packit: {tok} fork(s) of {narch} archive(s) read from the "
          f"published description, {tbad} not")
    return 0


if __name__ == "__main__":
    sys.exit(main())

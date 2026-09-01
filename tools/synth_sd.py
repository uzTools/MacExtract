#!/usr/bin/env python3
"""synth_sd.py — write Alysis SuperDisk! record streams.

The corpus's two SuperDisk! archives nest one folder inside another and
stop: the deepest path in either is 49 bytes, so `fmt_superdisk.c`'s
record walk has never reached `unc_path_leaf`'s 255-byte cap, and its
folder chain has never been longer than two. This writes streams that do.

**There is no second reader for this container off the Macintosh.**
`unar` and `macunpack` both stop at the BinHex envelope, so a stream
written here can only be graded by the format's own self-extracting
application on an emulated Mac — `tools/vmac/superdisk.py --nest` and
`--stored`, which give that application a data fork built by this file
and read back what it makes. Every claim these builders rest on was put
to it that way before it was asserted offline.

  Source: `CODE 2` of `super-disk-utility.hqx` — the record walk at
          0x2e4 (the 8-byte tag, the Pascal name padded to even, a
          folder's 20 bytes and a file's 30) and the block loop at
          0x5f4 (a block's length counts itself; bit 15 marks stored,
          except 0x8002 — @0x614).

Field VALUES nothing here decodes — the 8 bytes at the head of the file,
a folder's 20 and the four unread bytes inside a file's 30 — are COPIED
from a real archive rather than invented. A wrong guess in any of them
would be indistinguishable from the failure a run is looking for, and
inventing one would be inventing a format detail (CLAUDE.md, rule #1).

Blocks are borrowed for the same reason: a block written here would be a
stored block, and **no stored block exists in the corpus** — all seven
across both fixtures are coded, methods 7 and 11 — so putting one in the
way of a question about paths would test two things at once. What a
stored block does is asked separately, by `stored_pair()`.
"""
import struct
import sys

CAP = 255                     # UNC_NAME_MAX
MAXNAME = 31                  # what a Macintosh name takes


def _tag8(t):
    return bytes([t]) + b"\0" * 7


def _pstr(name):
    b = bytes([len(name)]) + name
    return b + (b"\0" if len(b) & 1 else b"")


def borrow(orig):
    """A folder's 20 bytes, and a real file's 30 bytes and block chain,
    lifted out of an archive. Returns (dirinfo, fileinfo, blocks, dlen)
    for the first data-fork-only file under a folder."""
    at, dirinfo = 8, None
    while True:
        tag = orig[at]
        if tag == 0x27:
            raise ValueError("no borrowable file in this archive")
        if tag == 0x2A:
            at += 8
            continue
        nlen = orig[at + 8]
        p = at + 9 + nlen
        if p & 1:
            p += 1
        if tag == 0x29:
            if dirinfo is None:
                dirinfo = orig[p:p + 20]
            at = p + 20
            continue
        dlen, rlen = struct.unpack_from(">II", orig, p)
        info, body, end = orig[p:p + 30], p + 30, p + 30
        for want in (dlen, rlen):
            done = 0
            while done < want:
                n = struct.unpack_from(">H", orig, end)[0]
                if n & 0x8000:
                    raise ValueError("a stored block in the corpus")
                ulen = struct.unpack_from(">H", orig, end + 2)[0]
                done += min(ulen, want - done)
                end += n
        if dlen and not rlen and dirinfo is not None:
            return dirinfo, info, orig[body:end], dlen
        at = end


def nest(orig, depth=10):
    """A stream whose folder path SUMS past the cap.

    Folder names are exactly 31 characters, so a path of d of them
    measures 32d-1 bytes: d=8 is 255 exactly — the last that fits — and
    the file inside it is the first entry the cap cuts. Every file
    carries the same borrowed fork, so what differs between entries is
    only the path. A file at the ROOT comes last, so its absence
    separates "the walk never came back up" from "it never descended".

    Returns (bytes, [declared file paths], fork length).
    """
    dirinfo, finfo, blocks, dlen = borrow(orig)
    paths, body, here = [], b"", []
    for d in range(1, depth + 1):
        fold = ("F%02d" % d).encode() + b"x" * (MAXNAME - 3)
        body += _tag8(0x29) + _pstr(fold) + dirinfo
        here.append(fold.decode())
        leaf = ("depth%02d.txt" % d).encode()
        body += _tag8(0x28) + _pstr(leaf) + finfo + blocks
        paths.append("/".join(here + [leaf.decode()]))
    body += _tag8(0x2A) * depth
    body += _tag8(0x28) + _pstr(b"control.txt") + finfo + blocks
    paths.append("control.txt")
    return orig[:8] + body + _tag8(0x27), paths, dlen


# A file's 30 bytes as this project would GUESS them, rather than as a
# real archive writes them: the four bytes at +18 that nothing here
# decodes are filled in, and the type, creator, flags and dates are
# chosen. Kept only to be run against the borrowed record — see
# `one_file(invented=True)`.
_INVENTED = (b"TEXT" + b"ttxt" + struct.pack(">H", 0x0100) + b"\0\7\0\4" +
             struct.pack(">II", 0xA4D0A7A5, 0xA4D0A7A6))


def one_file(orig, invented=False):
    """The borrowed fork on its own, so a caller can decode it.

    With `invented`, everything about the file record EXCEPT the two
    lengths is guessed rather than copied. Nothing should be built that
    way; the option exists so that what happens when it is can be
    measured rather than asserted (CLAUDE.md, rule #1)."""
    _dirinfo, finfo, blocks, dlen = borrow(orig)
    if invented:
        finfo = finfo[:8] + _INVENTED
    return (orig[:8] + _tag8(0x28) + _pstr(b"plain.txt") + finfo + blocks +
            _tag8(0x27)), dlen


def stored_pair(orig, plain):
    """The same file twice, coded and stored, in one folder.

    DECISIONS.md 2026-08-20 reads a stored block off `CODE 2` @0x614 as
    a length with bit 15 set, counting its own two header bytes, except
    0x8002. Nothing in the corpus has one, so that reading has never
    been put to the extractor it was read out of. `plain` is the
    borrowed fork's DECODED bytes, so the file record — its `dlen`
    included — is byte for byte the one the coded case uses, and the
    block encoding is the only thing that differs.

    Returns (bytes, folder name).
    """
    dirinfo, finfo, blocks, dlen = borrow(orig)
    if len(plain) != dlen:
        raise ValueError("plaintext is %d B, the record says %d"
                         % (len(plain), dlen))
    stored = struct.pack(">H", 0x8000 | (len(plain) + 2)) + plain
    fold = b"AB" + b"y" * (MAXNAME - 2)
    body = (_tag8(0x29) + _pstr(fold) + dirinfo +
            _tag8(0x28) + _pstr(b"coded.txt") + finfo + blocks +
            _tag8(0x28) + _pstr(b"stored.txt") + finfo + stored +
            _tag8(0x2A))
    return orig[:8] + body + _tag8(0x27), fold.decode()


def main():
    if len(sys.argv) != 3:
        sys.stderr.write("usage: synth_sd.py PAYLOAD.x OUT.x\n"
                         "  PAYLOAD.x is an unwrapped corpus archive, the "
                         "one whose fields and blocks are borrowed\n")
        return 2
    orig = open(sys.argv[1], "rb").read()
    blob, paths, dlen = nest(orig)
    open(sys.argv[2], "wb").write(blob)
    print("%s: %d B, %d files of %d B" % (sys.argv[2], len(blob),
                                          len(paths), dlen))
    for p in paths:
        print("  %3d B %s%s" % (len(p), p[:40], "..." if len(p) > 40 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

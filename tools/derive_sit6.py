#!/usr/bin/env python3
"""derive_sit6.py — read StuffIt method 6 ("fixed Huffman") from a
description written against deark, and say where that description
needs correcting.

`src/fmt_sit.c`'s method 6 was transcribed from macutils' `macunpack`
(LGPL) and was the last of that transcription left in the file. The
code BOOK stopped being macutils' on 2026-09-21; what remained was the
**framing** — the segment header, the stored-segment rule and the
PackBits tail. deark implements all three under MIT and credits
macunpack as documentation, using none of its code:

    reference/deark/modules/stuffit.c   do_decompr_fixedhuff
                                        sit_fixedhuff_init_tree
    reference/deark/src/fmtutil-rle.c   my_packbits_codec_addbuf

This reader is written from those and from the container page
(`reference/notes/sit_format_theunarchiver.md`) — not from
`src/fmt_sit.c` and not from `reference/macutils/`. Where the
description is silent or wrong the correction is marked **CORRECTION**
and was established by decoding whole forks against the sha256 an
independent oracle recorded for them.

    tools/derive_sit6.py [archive.sit ...]     # default: fixtures/*.sit

Not in `ci.sh`: it needs the fixtures, which are not committed, and it
is a derivation rather than a test. It skips cleanly without them.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEARK = os.path.join(ROOT, "reference", "deark", "modules", "stuffit.c")

NUMCODES = 257          # FIXEDHUFF_NUMCODES; symbol 256 is the stop code


def codebook_runs():
    """The 26 bytes: `cdlen_RLEcounts` and `cdlen_RLElengths`, read out
    of deark's source rather than copied here, so this tool cannot
    agree with the engine by sharing a typo with it."""
    if not os.path.exists(DEARK):
        return None
    txt = open(DEARK).read()
    out = {}
    for m in re.finditer(r"static const u8 (cdlen_RLE\w+)\s*\[\d+\]\s*="
                         r"\s*\{(.*?)\}", txt, re.S):
        out[m.group(1)] = [int(v) for v in re.findall(r"\d+", m.group(2))]
    if len(out) != 2:
        return None
    return list(zip(out["cdlen_RLEcounts"], out["cdlen_RLElengths"]))


def codebook(runs):
    """{(nbits, code): symbol}.

    deark: expand the runs to 257 code lengths, then walk the symbols
    **in their own order** — not sorted by length — giving each the
    code that follows the previous one: shift right and add one when
    shorter, add one and shift left when longer, add one when equal.
    That is why this is not a canonical code.
    """
    lengths = []
    for count, bits in runs:
        lengths += [bits] * count
    lengths = lengths[:NUMCODES]
    if len(lengths) != NUMCODES:
        raise SystemExit("derive-sit6: the runs do not add up to 257 codes")
    table = {}
    code = 0
    prevlen = 0
    for sym, ln in enumerate(lengths):
        if prevlen == 0:
            code = 0
        elif ln < prevlen:
            code = (code >> (prevlen - ln)) + 1
        else:
            code = (code + 1) << (ln - prevlen)
        prevlen = ln
        if (ln, code) in table:
            raise SystemExit("derive-sit6: two symbols share a code")
        table[(ln, code)] = sym
    return table


class MSB:
    """The bitstream is read most-significant bit first. deark's
    `de_bitreader` defaults to that order and `do_decompr_fixedhuff`
    does not change it."""
    __slots__ = ("d", "p", "end")

    def __init__(self, d, byte, endbyte):
        self.d = d
        self.p = byte * 8
        self.end = endbyte * 8

    def bit(self):
        if self.p >= self.end:
            return None
        v = (self.d[self.p >> 3] >> (7 - (self.p & 7))) & 1
        self.p += 1
        return v


def read_symbol(bs, table):
    code = 0
    for ln in range(1, 25):
        b = bs.bit()
        if b is None:
            return None
        code = (code << 1) | b
        if (ln, code) in table:
            return table[(ln, code)]
    raise ValueError("no code of 24 bits or fewer matches")


def packbits(src, limit):
    """Standard PackBits, deark's `my_packbits_codec_addbuf`: a code
    byte below 128 introduces `1 + b` literals, 128 is a no-op, and
    above 128 it repeats the next byte `257 - b` times. The caller's
    remaining output length is a maximum, not an expectation."""
    out = bytearray()
    p = 0
    while p < len(src) and len(out) < limit:
        b = src[p]
        p += 1
        if b < 128:
            n = 1 + b
            out += src[p:p + n]
            p += n
        elif b > 128:
            if p >= len(src):
                break
            out += bytes([src[p]]) * (257 - b)
            p += 1
    return bytes(out[:limit])


def method6(d, off, clen, ulen, table, stats):
    """A fork is a sequence of independent BLOCKS, each of which
    decodes to a PackBits stream that is then expanded into the fork.

    deark's framing, field for field:

      s32  size      counted from its own first byte
      size < 0       stored: |size| - 4 bytes of PackBits, no Huffman
      size >= 0      u32 length after Huffman, s16 code count, that
                     many bytes naming what each leaf ordinal stands
                     for, then the bitstream to the block's end

    A block below 10 bytes (4 for a stored one) ends the fork, as does
    a fork that has produced the bytes the entry header declared.
    """
    end = off + clen
    pos = off
    out = bytearray()
    while len(out) < ulen:
        if pos + 4 > end:
            break
        raw = int.from_bytes(d[pos:pos + 4], "big", signed=True)
        pos += 4
        if raw >= 0:
            if raw < 10:
                break
            block_end = pos - 4 + raw
            if block_end > end:
                raise ValueError("block runs past the fork")
            interm = int.from_bytes(d[pos:pos + 4], "big")
            pos += 4
            ndefs = int.from_bytes(d[pos:pos + 2], "big", signed=True)
            pos += 2
            if ndefs < 0 or ndefs > 256:
                raise ValueError("num code defs %d" % ndefs)
            trans = d[pos:pos + ndefs]
            pos += ndefs
            bs = MSB(d, pos, block_end)
            mid = bytearray()
            while len(mid) < interm:
                v = read_symbol(bs, table)
                if v is None:
                    break                       # ran out of block
                if v > 255:
                    break                       # the stop code
                # CORRECTION: deark indexes `translation[val]` with no
                # bound against the count the block declared. A block
                # that names 12 bytes and codes a thirteenth is reading
                # whatever the previous block left in that array —
                # macunpack does the same, and it is a wrong fork
                # rather than a refused one. No block in the corpus
                # does it; `src/fmt_sit.c` refuses it.
                if v >= ndefs:
                    raise ValueError("code %d, %d declared" % (v, ndefs))
                mid.append(trans[v])
            stats["huff"] += 1
            # deark stops at the declared length and never reads the
            # stop code; `src/fmt_sit.c` reads on and REQUIRES one.
            # Which of the two is right is a property of the streams,
            # so it is measured here rather than assumed: read one
            # more symbol and record what it is.
            if len(mid) == interm:
                stats["bylen"] += 1
                try:
                    v = read_symbol(bs, table)
                except ValueError:
                    v = None
                if v is None:
                    stats["thenblockend"] += 1
                elif v > 255:
                    stats["thenstop"] += 1
                else:
                    stats["thenmore"] += 1
            src = bytes(mid)
        else:
            raw = -raw
            if raw < 4:
                break
            block_end = pos - 4 + raw
            if block_end > end:
                raise ValueError("block runs past the fork")
            src = d[pos:pos + raw - 4]
            stats["stored"] += 1
        out += packbits(src, ulen - len(out))
        pos = block_end
        stats["blocks"] += 1
    return bytes(out)


def be(b, o, n):
    return int.from_bytes(b[o:o + n], "big")


def walk(d):
    """The container page's file header: 112 bytes always, method 32
    opening a folder and 33 closing it, the forks after each header."""
    p = 22
    stack = []
    while p + 112 <= len(d):
        rm, dm, nl = d[p], d[p + 1], d[p + 2]
        name = d[p + 3:p + 3 + min(nl, 63)].decode("mac_roman", "replace")
        if rm == 32:
            stack.append(name)
            p += 112
            continue
        if rm == 33:
            if stack:
                stack.pop()
            p += 112
            continue
        rlen, dlen = be(d, p + 84, 4), be(d, p + 88, 4)
        rclen, dclen = be(d, p + 92, 4), be(d, p + 96, 4)
        yield ("/".join(stack + [name]), rm & 15, dm & 15, p + 112,
               rlen, dlen, rclen, dclen)
        p += 112 + rclen + dclen


def check(path, table, stats):
    d = open(path, "rb").read()
    mp = os.path.join(ROOT, "fixtures", "manifests",
                      os.path.basename(path) + ".json")
    if not os.path.exists(mp):
        return 0, 0
    man = {e["name"]: e for e in json.load(open(mp))["entries"]}
    ok = bad = 0
    for name, rm, dm, off, rlen, dlen, rclen, dclen in walk(d):
        m = man.get(name)
        if not m:
            continue
        for kind, meth, ulen, clen, o in (("rsrc", rm, rlen, rclen, off),
                                          ("data", dm, dlen, dclen,
                                           off + rclen)):
            sha = m.get(kind + "_sha256")
            if meth != 6 or not sha:
                continue
            try:
                out = method6(d, o, clen, ulen, table, stats)
                good = hashlib.sha256(out).hexdigest() == sha
            except Exception as exc:
                print(f"  FAIL {name[-26:]:28s} {kind} {ulen:7d} B  {exc}")
                bad += 1
                continue
            if good:
                ok += 1
            else:
                print(f"  FAIL {name[-26:]:28s} {kind} {ulen:7d} B  "
                      f"bytes differ ({len(out)} of {ulen})")
                bad += 1
    return ok, bad


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixtures", nargs="*")
    a = ap.parse_args()
    runs = codebook_runs()
    if runs is None:
        print("derive-sit6: no reference/deark/modules/stuffit.c "
              "— run tools/fetch_references.sh (skipped)")
        return 0
    table = codebook(runs)
    paths = a.fixtures or sorted(glob.glob(os.path.join(ROOT, "fixtures",
                                                        "*.sit")))
    if not paths:
        print("derive-sit6: no fixtures here (skipped)")
        return 0
    stats = {"blocks": 0, "huff": 0, "stored": 0, "bylen": 0,
             "thenstop": 0, "thenmore": 0, "thenblockend": 0}
    tok = tbad = narch = 0
    for p in paths:
        ok, bad = check(p, table, stats)
        if ok or bad:
            narch += 1
            print(f"{os.path.basename(p):40s} {ok:3d} fork(s)"
                  + (f", {bad} NOT" if bad else ""))
        tok += ok
        tbad += bad
    print(f"derive-sit6: {tok} method-6 forks of {narch} archive(s) read "
          f"from deark's description, {tbad} not")
    print(f"             {stats['blocks']} blocks — {stats['huff']} Huffman, "
          f"{stats['stored']} stored")
    print(f"             {stats['bylen']} of {stats['huff']} Huffman blocks "
          f"reached the declared length; the symbol after it is the stop "
          f"code in {stats['thenstop']}, a byte in {stats['thenmore']}, "
          f"absent in {stats['thenblockend']}")
    return 1 if tbad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""derive_sit13.py — read StuffIt method 13 from the FORMAT's own
published description, and say where that description is wrong.

The Unarchiver's format wiki documents method 13 in full, tables and
all, and `tools/fetch_references.sh` fetches it since 2026-09-20:

    reference/notes/sit13_theunarchiver.md    the coder and its tables
    reference/notes/sit_format_theunarchiver.md   the container

This reader is written from those two and from nothing else — not from
`src/fmt_sit.c`, not from `XADStuffIt13Handle.m`. Where the pages are
wrong or ambiguous the correction is marked **CORRECTION** below and
was established by decoding whole forks against the sha256 an
independent oracle recorded for them.

    tools/derive_sit13.py [archive.sit ...]      # default: a sample

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
NOTE = os.path.join(ROOT, "reference", "notes", "sit13_theunarchiver.md")


def tables():
    """The page's Tables section, parsed out of the page itself."""
    if not os.path.exists(NOTE):
        return None
    txt = open(NOTE).read()
    out = {}
    for m in re.finditer(r"static const int (\w+)\[(\d+)\]=\s*\{(.*?)\}",
                         txt, re.S):
        name, n, body = m.group(1), int(m.group(2)), m.group(3)
        vals = [int(x, 0) for x in re.findall(r"0x[0-9a-fA-F]+|\d+", body)]
        if len(vals) != n:
            raise SystemExit(f"derive-sit13: {name} has {len(vals)} of {n}")
        out[name] = vals
    return out


class LSB:
    """"All values are read least significant bit first", and they are."""
    __slots__ = ("d", "p")

    def __init__(self, d, byte):
        self.d = d
        self.p = byte * 8

    def bit(self):
        v = (self.d[self.p >> 3] >> (self.p & 7)) & 1
        self.p += 1
        return v

    def bits(self, n):
        v = 0
        for k in range(n):
            v |= self.bit() << k
        return v


def build(lengths):
    """The page's construction: ascending (length, value), 32 bits,
    `Reverse32` applied — and here the reversal IS needed, because the
    stream is read least-significant-bit first. (Compact Pro's page
    says the same thing about a stream that is read MSB-first, where
    it is not: docs/formats/compact-pro.md.)"""
    t = {}
    code = 0
    for length in range(1, 33):
        for i, l in enumerate(lengths):
            if l != length:
                continue
            r = int(format(code, "032b")[::-1], 2)
            t[(length, r & ((1 << length) - 1))] = i
            code += 1 << (32 - length)
    return t


def decoder(table):
    def dec(bs):
        code = 0
        for length in range(1, 33):
            code |= bs.bit() << (length - 1)
            if (length, code) in table:
                return table[(length, code)]
        raise ValueError("no code of 32 bits or fewer matches")
    return dec


def meta_table(T):
    return {(l, c): i for i, (c, l)
            in enumerate(zip(T["MetaCodes"], T["MetaCodeLengths"]))}


def read_lengths(bs, n, META):
    """CORRECTION: the page's list of meta-code meanings ends with
    "Finally, set the length of the next code entry ... in addition to
    any code entries you may have set while processing the input
    value", and that "in addition" is load-bearing — values 34, 35 and
    36 set their repeats AND one more entry after them. A reader that
    treats the repeats as the whole of those cases produces lengths
    that miss Kraft's equality (1.53 instead of 1.00 on the first fork
    tried), which is how this was found without any implementation to
    compare against."""
    L = [0] * n
    i = 0
    cur = 0
    while i < n:
        code = 0
        v = None
        for length in range(1, 16):
            code |= bs.bit() << (length - 1)
            if (length, code) in META:
                v = META[(length, code)]
                break
        if v is None:
            raise ValueError("no meta code")
        if v < 31:
            cur = v + 1
        elif v == 31:
            cur = 0
        elif v == 32:
            cur += 1
        elif v == 33:
            cur -= 1
        else:
            rep = (bs.bits(1) if v == 34 else
                   bs.bits(3) + 2 if v == 35 else bs.bits(6) + 10)
            for _ in range(rep):
                if i < n:
                    L[i] = max(cur, 0)
                    i += 1
        if i < n:
            L[i] = max(cur, 0)
            i += 1
    return L


def sit13(d, off, nout, T, META, seen=None):
    sel = d[off] >> 4
    if seen is not None:
        seen[sel] = seen.get(sel, 0) + 1
    bs = LSB(d, off + 1)
    if sel == 0:
        first = build(read_lengths(bs, 321, META))
        second = first if (d[off] & 0x08) else \
            build(read_lengths(bs, 321, META))
        offs = build(read_lengths(bs, (d[off] & 0x07) + 10, META))
    elif 1 <= sel <= 5:
        first = build(T["FirstTreeLengths_%d" % sel])
        second = build(T["SecondTreeLengths_%d" % sel])
        offs = build(T["OffsetTreeLengths_%d" % sel])
    else:
        raise ValueError("code selector %d" % sel)
    dfirst, dsecond, doffs = decoder(first), decoder(second), decoder(offs)
    win = bytearray(65536)
    wpos = 0
    out = bytearray()
    dec = dfirst
    while len(out) < nout:
        v = dec(bs)
        if v < 256:
            out.append(v)
            win[wpos & 65535] = v
            wpos += 1
            dec = dfirst
            continue
        if v == 320:
            break
        mlen = (v - 253 if v <= 317 else
                bs.bits(10) + 65 if v == 318 else bs.bits(15) + 65)
        nb = doffs(bs)
        # CORRECTION: the page says the match "starts at the position
        # of the last byte written minus the offset value". It is one
        # further back than that: the distance is measured from the
        # byte ABOUT TO BE written, so it is the offset plus one.
        dist = (0 if nb == 0 else (1 << (nb - 1)) | bs.bits(nb - 1)) + 1
        for _ in range(mlen):
            b = win[(wpos - dist) & 65535]
            out.append(b)
            win[wpos & 65535] = b
            wpos += 1
        dec = dsecond
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


def check(path, T, META, seen, cap):
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
        for kind, meth, ulen, o in (("rsrc", rm, rlen, off),
                                    ("data", dm, dlen, off + rclen)):
            want = m.get(kind + "_size") or 0
            sha = m.get(kind + "_sha256")
            if not want or not sha or meth != 13 or want > cap:
                continue
            try:
                out = sit13(d, o, ulen, T, META, seen)[:want]
                good = hashlib.sha256(out).hexdigest() == sha
            except Exception as exc:
                print(f"  FAIL {name[-26:]:28s} {kind} {want:7d} B  {exc}")
                bad += 1
                continue
            if good:
                ok += 1
            else:
                print(f"  FAIL {name[-26:]:28s} {kind} {want:7d} B  bytes differ")
                bad += 1
    return ok, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixtures", nargs="*")
    ap.add_argument("--cap", type=int, default=200000,
                    help="skip forks larger than this (Python is slow)")
    a = ap.parse_args()
    T = tables()
    if T is None:
        print("derive-sit13: no reference/notes/sit13_theunarchiver.md "
              "— run tools/fetch_references.sh (skipped)")
        return 0
    META = meta_table(T)
    paths = a.fixtures or sorted(glob.glob(os.path.join(ROOT, "fixtures", "*.sit")))
    if not paths:
        print("derive-sit13: no fixtures here (skipped)")
        return 0
    seen = {}
    tok = tbad = narch = 0
    for p in paths:
        ok, bad = check(p, T, META, seen, a.cap)
        if ok or bad:
            narch += 1
            print(f"{os.path.basename(p):40s} {ok:3d} fork(s)"
                  + (f", {bad} NOT" if bad else ""))
        tok += ok
        tbad += bad
    sel = ", ".join(f"{k}: {v}" for k, v in sorted(seen.items()))
    print(f"derive-sit13: {tok} method-13 forks of {narch} archive(s) read "
          f"from the published description, {tbad} not")
    print(f"              code selectors met — {sel or 'none'}")
    return 1 if tbad else 0


if __name__ == "__main__":
    sys.exit(main())

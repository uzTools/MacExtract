#!/usr/bin/env python3
"""lzahexp.py — StuffIt Expander 4.0.2 fed a method-5 fork whose matches
reach into the window's preload.

StuffIt method 5 and LZH's -lh1- are one coder (src/unc_lzah.c), whose
4 KB window starts preloaded. What it starts as is XADMaster's reading
(XADLZHDynamicHandle.m, resetLZSSHandle: 256 runs of 13, a rising and a
falling ramp, 128 zeros, then spaces); lhasa fills the -lh1- window with
spaces. The corpus cannot tell the two apart: its one fixture that
reaches the preload reaches only the trailing spaces (DECISIONS.md
2026-09-28, *the preload nothing reaches*).

This builds one classic StuffIt archive holding one data fork coded with
method 5, five 60-byte matches at the start, each aimed at a different
part of the window as XADMaster lays it out, then 40 literal bytes, and
has Expander 4.0.2 expand it (`mwexp.py`'s flow). What Expander wrote is
compared with what each candidate fill gives.

The encoder is the inverse of src/unc_lzah.c's decoder (the published
LZHUF tree, the 64 distance-code lengths), and is checked against that
decoder: this engine must read the archive back as the XADMaster fill
says before the emulator is booted.

What it CANNOT see: a fill that agrees with one candidate over these 300
bytes and differs elsewhere in the window (each region is sampled at one
place); and -lh1- in an LZH archive, which is LHarc's reader, not
Aladdin's.

    tools/vmac/lzahexp.py -o <shotdir> [--build-only out.sit]
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import mwexp                                                 # noqa: E402

N_CHAR, T = 314, 627
R_ = T - 1
MAX_FREQ = 0x8000
WINDOW = 4096
# src/unc_lzah.c, lzah_distlengths
DISTLEN = [3, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6,
           6, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7,
           7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
           8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8]


def dist_codes():
    """Canonical codes over DISTLEN, as lzah_build_dist assigns them."""
    out, code, prev = [], 0, DISTLEN[0]
    for sym, ln in enumerate(DISTLEN):
        if sym:
            code = (code + 1) << (ln - prev)
        prev = ln
        out.append((code, ln))
    return out


class Tree:
    """src/unc_lzah.c's lzah_start, lzah_reconst and lzah_update."""

    def __init__(self):
        self.freq = [0] * (T + 1)
        self.son = [0] * T
        self.prnt = [0] * (T + N_CHAR)
        for i in range(N_CHAR):
            self.freq[i] = 1
            self.son[i] = i + T
            self.prnt[i + T] = i
        i, j = 0, N_CHAR
        while j <= R_:
            self.freq[j] = self.freq[i] + self.freq[i + 1]
            self.son[j] = i
            self.prnt[i] = self.prnt[i + 1] = j
            i += 2
            j += 1
        self.freq[T] = 0xFFFF
        self.prnt[R_] = 0

    def reconst(self):
        f, s, p = self.freq, self.son, self.prnt
        j = 0
        for i in range(T):
            if s[i] >= T:
                f[j] = (f[i] + 1) // 2
                s[j] = s[i]
                j += 1
        i, j = 0, N_CHAR
        while j < T:
            k = i + 1
            fr = f[i] + f[k]
            f[j] = fr
            k = j
            while k > 0 and fr < f[k - 1]:
                k -= 1
            for l in range(j, k, -1):
                f[l] = f[l - 1]
                s[l] = s[l - 1]
            f[k] = fr
            s[k] = i
            i += 2
            j += 1
        for i in range(T):
            k = s[i]
            if k >= T:
                p[k] = i
            else:
                p[k] = p[k + 1] = i

    def update(self, c):
        f, s, p = self.freq, self.son, self.prnt
        if f[R_] == MAX_FREQ:
            self.reconst()
        c = p[c + T]
        while True:
            f[c] += 1
            k = f[c]
            l = c + 1
            if k > f[l]:
                l += 1
                while k > f[l]:
                    l += 1
                l -= 1
                f[c] = f[l]
                f[l] = k
                i = s[c]
                p[i] = l
                if i < T:
                    p[i + 1] = l
                j = s[l]
                s[l] = i
                p[j] = c
                if j < T:
                    p[j + 1] = c
                s[c] = j
                c = l
            c = p[c]
            if c == 0:
                break

    def code(self, c):
        """The bits from the root down to symbol c's leaf."""
        # The leaf is the node whose son is T + c; each level's bit is
        # which of its parent's two children it is (the decoder takes
        # son[parent] + bit).
        bits = []
        node = self.prnt[c + T]
        while True:
            par = self.prnt[node]
            bits.append(node - self.son[par])
            if par == R_:
                break
            node = par
        return bits[::-1]


def encode(tokens):
    """tokens: ('lit', byte) or ('match', length, offset); MSB-first bits."""
    t = Tree()
    dc = dist_codes()
    bits = []
    for tok in tokens:
        if tok[0] == "lit":
            c = tok[1]
        else:
            _, ln, off = tok
            assert 3 <= ln <= 60 and 1 <= off <= WINDOW
            c = 0x100 + ln - 3
        bits += t.code(c)
        t.update(c)
        if tok[0] == "match":
            v = off - 1
            code, ln2 = dc[v >> 6]
            bits += [(code >> (ln2 - 1 - k)) & 1 for k in range(ln2)]
            bits += [((v & 63) >> (5 - k)) & 1 for k in range(6)]
    bits += [0] * (-len(bits) % 8)
    return bytes(int("".join(map(str, bits[i:i + 8])), 2)
                 for i in range(0, len(bits), 8))


def fill_xadmaster():
    """src/unc_lzah.c's lzah_preload, mode LH1."""
    w = bytearray(WINDOW)
    for i in range(256):
        for j in range(13):
            w[i * 13 + 18 + j] = i
    for i in range(256):
        w[256 * 13 + 18 + i] = i
    for i in range(256):
        w[256 * 13 + 256 + 18 + i] = 255 - i
    for i in range(128):
        w[256 * 13 + 512 + 18 + i] = 0
    for i in range(128 - 18):
        w[256 * 13 + 512 + 128 + 18 + i] = 0x20
    return w


def play(tokens, window):
    w = bytearray(window)
    out = bytearray()
    pos = 0
    for tok in tokens:
        if tok[0] == "lit":
            w[pos % WINDOW] = tok[1]
            out.append(tok[1])
            pos += 1
        else:
            _, ln, off = tok
            frm = pos - off
            for _k in range(ln):
                b = w[frm % WINDOW]
                w[pos % WINDOW] = b
                out.append(b)
                pos += 1
                frm += 1
    return bytes(out)


# Where each match lands, as XADMaster lays the window out.
TARGETS = (("runs of 13, from 0x41", 18 + 0x41 * 13),
           ("the rising ramp", 256 * 13 + 18),
           ("the falling ramp", 256 * 13 + 256 + 18),
           ("the zeros", 256 * 13 + 512 + 18),
           ("the spaces", 256 * 13 + 512 + 128 + 18))


def stream():
    toks, pos = [], 0
    for _label, idx in TARGETS:
        off = pos + WINDOW - idx
        toks.append(("match", 60, off))
        pos += 60
    toks += [("lit", b) for b in b"and forty literal bytes after the five.\r"]
    return toks


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-o", "--outdir", default=None)
    p.add_argument("--emu", default="mv-4M")
    p.add_argument("--build-only", default=None,
                   help="write the archive here, check it, and stop")
    p.add_argument("--crc-of", default="xad", choices=("xad", "spaces"),
                   help="whose output the entry header's CRC-16 is over")
    a = p.parse_args()
    toks = stream()
    comp = encode(toks)
    want = {"XADMaster's fill": play(toks, fill_xadmaster()),
            "lhasa's spaces": play(toks, bytes([0x20]) * WINDOW),
            "zeros": play(toks, bytes(WINDOW))}
    data = want["XADMaster's fill"]
    entry = "Lzah5"
    crcd = want["lhasa's spaces"] if a.crc_of == "spaces" else data
    arc = mwexp.archive(entry, crcd, comp, method=5)
    # The engine (XADMaster's fill) must read this as built, or the
    # encoder is wrong and the emulator would measure nothing.
    if a.crc_of == "spaces":
        mwexp.expand("lzah5s", entry, arc, want, len(data), len(comp), a)
        return
    path = a.build_only or os.path.join(REPO, ".tmp", "lzahexp-check.sit")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, "wb").write(arc)
    out = os.path.join(REPO, ".tmp", "lzahexp-check")
    os.makedirs(out, exist_ok=True)
    cli = os.environ.get("MACEXTRACT", os.path.join(REPO, "build", "rel", "macextract"))
    r = subprocess.run([cli, "x", "--overwrite", "-o", out, path],
                       capture_output=True, text=True)
    got = open(os.path.join(out, entry), "rb").read() \
        if os.path.exists(os.path.join(out, entry)) else None
    print("lzahexp: the engine reads the archive as XADMaster's fill: %s (exit %d)"
          % (got == data, r.returncode), flush=True)
    if got != data:
        raise SystemExit("lzahexp: the encoder disagrees with the engine")
    if a.build_only:
        return
    mwexp.expand("lzah5", entry, arc, want, len(data), len(comp), a)


if __name__ == "__main__":
    main()

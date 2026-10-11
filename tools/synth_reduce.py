#!/usr/bin/env python3
"""synth_reduce.py — a zip whose entries are Reduce streams, one per factor.

**An encoder, because nothing here is one.** Zip methods 2-5 are in scope
since 2026-10-11, and what the corpus holds is four wild archives, one per
compression factor (FORMATS.md, *Reduce*). No tool on this machine WRITES
the method: PKZIP dropped it after 0.92, Info-ZIP never wrote it, and
deark and this engine only read it. So this writes it, for two things:

  1. **A committed fixture**, `fixtures/synth-exo-zip-reduce.zip`, graded
     by deark through the ordinary manifest — four entries, one per
     factor, each body starting with zeros that the first copy takes from
     before the start of the output, and carrying the byte 144 the
     escape has to spell out.
  2. **The named seed `tools/fuzz.py` needs.** Its generators 1 and 2 draw
     from ~950 fixtures, so four small Reduce archives are fuzzed a
     handful of times in 3,000 cases; `--ranges` declares exactly the bytes
     that are follower sets and coded stream, and the stream generator
     mutates inside them (TESTING.md, *Fuzzing*).

**Graded by deark, not by this engine.** deark reads Reduce through
`foreign/ozunreduce.h`, an implementation this project did not write, and
the manifest is built from its output; the CRC-32 stored here is the same
check every wild entry was graded by.

Every rule comes from reference/notes/zip_appnote.txt 5.2:

  5.2.2/5.2.3 the follower sets, S(255) first, each a 6-bit count and that
    many 8-bit bytes, at most 32;
  5.2.4 the probabilistic stage: with Last-Character starting at 0, a
    byte is 8 bits if S(Last) is empty, else a 1 bit then 8 bits, or a
    0 bit then an index of B(N) bits — B(N) the bits needed for N-1;
  5.2.5 the repeated-byte stage, escaped by DLE (144): 144 0 is a literal
    144; 144 V [extra] D is a copy of L(V)+3 bytes (plus `extra` when
    L(V) is all ones) from D(V, D) back, where the data before the start
    is zeros;
  the bit order is zip's, least significant first (5.2's reader reads
    "bits from the input stream" as the Implode and Shrink sections do).

What this does NOT write, deliberately: a copy longer than its distance
(5.2.5 permits it, and `ozur` — the oracle — refuses it, so a fixture
carrying one could not be graded), and an index past a set's count
(5.2.4 does not define it). The unit tests cover both
(`test_zip_reduce_rules`).
"""
import argparse
import json
import os
import struct
import sys
import zlib

DOS_TIME = 0x6000           # 12:00:00
DOS_DATE = 0x1A4B           # 1993-02-11
DLE = 144


class BitWriter:
    """LSB first, as zip writes every bit stream."""
    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def put(self, value, nbits):
        self.acc |= (value & ((1 << nbits) - 1)) << self.n
        self.n += nbits
        while self.n >= 8:
            self.out.append(self.acc & 0xFF)
            self.acc >>= 8
            self.n -= 8

    def done(self):
        if self.n:
            self.out.append(self.acc & 0xFF)
            self.acc = 0
            self.n = 0
        return bytes(self.out)


def b_of(n):
    """B(N): the minimal number of bits to encode N-1 (5.2.4)."""
    b = 1
    while (1 << b) < n:
        b += 1
    return b


def body():
    """Deterministic content: a zero run that the first copy takes from
    before the start, text with repeats near and far, the byte 144 alone
    and in runs, a long repeat (a length byte after V), and a stretch of
    pseudo-random bytes that misses every follower set."""
    out = bytearray(300)                                   # zeros
    words = (b"reduce follower set escape distance length window "
             b"PKZIP 0.92 Phil Katz 1989 compression factor ")
    for i in range(40):
        out += words[(i * 7) % 40:] + words[:(i * 7) % 40]
        out += b"\r\n"
    out += bytes([DLE]) + b"DLE alone" + bytes([DLE, DLE, DLE]) + b"three"
    block = bytes((i * 37 + 11) & 0xFF for i in range(300))
    out += block + b"--" + block                           # long copy
    x = 12345
    for _ in range(700):                                   # LCG noise
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out.append((x >> 16) & 0xFF)
    out += words * 3
    return bytes(out)


def lz_stage(data, factor):
    """5.2.5 in reverse: the byte stream the probabilistic stage codes.

    Greedy, longest match first, no copy longer than its distance. The
    distance a factor can say is (2**factor - 1) * 256 + 256; the length
    is L(V) + 3, and L(V) all ones takes one more byte. A copy whose V
    would be 0 cannot be said — 144 0 is a literal — so a length-3 copy
    at a distance under 257 is left as literals."""
    mask = 0xFF >> factor
    maxdist = 256 << factor
    maxlen = mask + 255 + 3
    hist = bytes(4096) + data       # the zeros before the start
    base = 4096
    index = {}
    for k in range(base - maxdist, base):
        index.setdefault(hist[k:k + 3], []).append(k)
    out = bytearray()
    i = 0
    while i < len(data):
        p = base + i
        best_len, best_dist = 0, 0
        for q in reversed(index.get(hist[p:p + 3], [])):
            dist = p - q
            if dist > maxdist:
                break
            limit = min(maxlen, dist, len(data) - i)
            n = 0
            while n < limit and hist[q + n] == hist[p + n]:
                n += 1
            if n > best_len:
                best_len, best_dist = n, dist
                if n == min(maxlen, len(data) - i):
                    break           # nothing longer exists further back
        dhi = (best_dist - 1) >> 8 if best_len else 0
        if best_len >= 3 and not (dhi == 0 and best_len == 3):
            L = best_len - 3
            dlo = (best_dist - 1) & 0xFF
            if L >= mask:
                out += bytes([DLE, (dhi << (8 - factor)) | mask, L - mask, dlo])
            else:
                out += bytes([DLE, (dhi << (8 - factor)) | L, dlo])
            step = best_len
        else:
            c = data[i]
            out += bytes([DLE, 0]) if c == DLE else bytes([c])
            step = 1
        for k in range(p, p + step):
            index.setdefault(hist[k:k + 3], []).append(k)
        i += step
    return bytes(out)


def prob_stage(stream):
    """5.2.2-5.2.4 in reverse: follower sets from what actually follows
    each byte, most frequent first, at most 32, then the coded stream."""
    follows = [dict() for _ in range(256)]
    last = 0
    for c in stream:
        follows[last][c] = follows[last].get(c, 0) + 1
        last = c
    sets = []
    for j in range(256):
        ranked = sorted(follows[j].items(), key=lambda kv: (-kv[1], kv[0]))
        sets.append([c for c, n in ranked if n >= 2][:32])
    bw = BitWriter()
    for j in range(255, -1, -1):
        bw.put(len(sets[j]), 6)
        for c in sets[j]:
            bw.put(c, 8)
    last = 0
    for c in stream:
        s = sets[last]
        if not s:
            bw.put(c, 8)
        elif c in s:
            bw.put(0, 1)
            bw.put(s.index(c), b_of(len(s)))
        else:
            bw.put(1, 1)
            bw.put(c, 8)
        last = c
    return bw.done()


def encode(data, factor):
    return prob_stage(lz_stage(data, factor))


def unreduce(data, usize, factor):
    """The reading 5.2 states, for this file's own check that what it
    wrote decodes. It is NOT the grader — deark is."""
    pos, acc, n = 0, 0, 0

    def bits(k):
        nonlocal pos, acc, n
        while n < k:
            acc |= data[pos] << n
            pos += 1
            n += 8
        v = acc & ((1 << k) - 1)
        acc >>= k
        n -= k
        return v
    sets = [None] * 256
    for j in range(255, -1, -1):
        sets[j] = [bits(8) for _ in range(bits(6))]
    out = bytearray()
    hist = bytearray(4096)
    mask = 0xFF >> factor
    last, state, V, L = 0, 0, 0, 0
    while len(out) < usize:
        s = sets[last]
        if not s or bits(1):
            c = bits(8)
        else:
            c = s[bits(b_of(len(s)))]
        last = c
        if state == 0:
            if c == DLE:
                state = 1
            else:
                out.append(c)
        elif state == 1:
            if c:
                V, L = c, c & mask
                state = 2 if L == mask else 3
            else:
                out.append(DLE)
                state = 0
        elif state == 2:
            L += c
            state = 3
        else:
            dist = (V >> (8 - factor)) * 256 + c + 1
            for _ in range(L + 3):
                k = len(out) - dist
                out.append(out[k] if k >= 0 else 0)
            state = 0
    return bytes(out[:usize])


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--ranges", help="write the compressed byte spans "
                                     "here as JSON, for tools/fuzz.py")
    a = ap.parse_args()

    data = body()
    blob = bytearray()
    central = bytearray()
    ranges = []
    for factor in (1, 2, 3, 4):
        method = factor + 1
        stream = encode(data, factor)
        if unreduce(stream, len(data), factor) != data:
            print("synth_reduce: factor %d does not decode to its input — "
                  "the writer is wrong" % factor, file=sys.stderr)
            return 1
        fn = ("factor%d.txt" % factor).encode("ascii")
        crc = zlib.crc32(data) & 0xFFFFFFFF
        lhoffs = len(blob)
        # Version needed 1.0: Reduce predates every later feature.
        blob += struct.pack("<IHHHHHIIIHH", 0x04034B50, 10, 0, method,
                            DOS_TIME, DOS_DATE, crc, len(stream), len(data),
                            len(fn), 0)
        blob += fn
        ranges.append((len(blob), len(blob) + len(stream)))
        blob += stream
        central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 10, 10, 0,
                               method, DOS_TIME, DOS_DATE, crc, len(stream),
                               len(data), len(fn), 0, 0, 0, 0, 0, lhoffs)
        central += fn
    cdoffs = len(blob)
    blob += central
    blob += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 4, 4, len(central),
                        cdoffs, 0)
    with open(a.output, "wb") as fh:
        fh.write(blob)
    if a.ranges:
        with open(a.ranges, "w") as fh:
            json.dump([list(r) for r in ranges], fh)
    print("synth_reduce: %s — 4 entries of %d B, %d B, compressed %s"
          % (os.path.basename(a.output), len(data), len(blob),
             "/".join(str(hi - lo) for lo, hi in ranges)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

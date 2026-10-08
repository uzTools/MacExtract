#!/usr/bin/env python3
"""synth_implode.py — a zip whose entries are PKZIP 1.x Implode streams.

**An encoder, because nothing here is one.** Zip method 6 is in scope
since 2026-10-07 and the whole of what the corpus holds is 10 entries
across three archives — 7 in the two PKZIP 1.x fixtures and 3 in a
ZipIt specimen that cannot be committed. No Linux tool WRITES the
method: Info-ZIP's `zip` dropped it before 1.0, and `unar` and deark
decode it but neither compresses. PKZIP 1.01, 1.02 and 1.10 do write it
here, under DOSBox (`tools/pkzip_writers.py`, since 2026-10-08), but
only at 4 K/two trees and 8 K/three, never at a combination where the
two minimum-match-length rules disagree. So the shapes a fixture cannot
reach are written here. PKUNZIP 1.01/1.02 refuse every stream this
writes, the agreeing shapes included (OPEN_ITEMS.md).

What that buys, and each of the three is a different thing:

  1. **A committed fixture**, `fixtures/synth-exo-zip-implode.zip`,
     graded by `unar` through the ordinary manifest like every other —
     so `ci.sh` reads an Implode stream with no specimen present and
     no oracle at run time.
  2. **The named seed `tools/fuzz.py` needs.** Its generators 1 and 2
     draw from ~950 fixtures, so a format with two subjects is fuzzed
     about 2.3 times in 3,000 cases; `--ranges` declares exactly the
     bytes that are a Shannon-Fano stream, and the stream generator
     mutates inside them (TESTING.md, *Fuzzing*).
  3. **The parameter combinations on a dial.** It writes all four of
     them — 4 K and 8 K dictionary against two and three trees — and
     `--only` names one, so a combination the corpus does not reach can
     be made rather than waited for, and FORMATS.md says which those
     are rather than letting a green run imply coverage.
  4. **Streams PKZIP 1.01 and 1.02 would have written**, since
     2026-10-08: those two took the minimum match length from the
     DICTIONARY SIZE rather than from the literal tree's presence, and
     `8k-2trees-mmlbug` and `4k-3trees-mmlbug` are the only two
     combinations where that is observable at all. One of the two is
     carried by a real file — `fixtures/pkz101.exe`, PKZIP 1.01's own
     distribution, three entries at 4 K/three trees — and **the other
     is not: nothing authentic on this disk is 8 K with two trees**,
     so for that half this writer is the only subject there is and
     deark is its second reader (FORMATS.md, *Implode*).

**Graded by two implementations, not by this engine.** `unar` and deark
both read method 6; `tools/run_implode.py` requires both to agree with
the bytes that went in, and the CRC-32 this writer stores is the same
check PKZIP's own files are graded by.

Every number here comes from the specification or from the reference
implementation, never from memory:

  reference/notes/zip_appnote.txt 5.3 — the whole method: 5.3.2 the
    dictionary size and its flag bit, 5.3.3 the tree count and the
    order the trees are stored in, 5.3.4 the literal tree and the
    minimum match length that follows from it, 5.3.5/5.3.6 the length
    and distance alphabets, 5.3.7 how a tree is stored, 5.3.8 how the
    codes come out of the bit lengths, 5.3.9 the token stream
  reference/deark/src/fmtutil-lzh.c (MIT) — the reference decoder read
    beside it: `implode_read_a_tree`, `implode_read_trees`,
    `decompress_implode_internal`

Usage:
    synth_implode.py -o OUT.zip [--ranges OUT.json]
    synth_implode.py -o OUT.zip --only 8k-3trees
"""
import argparse
import heapq
import json
import os
import struct
import sys
import zlib


# --- the bit writer -------------------------------------------------
# 5.3.9's stream is read least-significant-bit-first within each byte,
# and a Shannon-Fano code is read most-significant-bit-first out of
# that — which is 5.3.8 step 3's reversal performed by the reading
# rather than by the table. So a code of length L goes out one bit at a
# time from its top bit down, and a raw field goes out from its bottom
# bit up.
class BitOut:
    def __init__(self):
        self.buf = bytearray()
        self.cur = 0
        self.n = 0

    def bit(self, b):
        if b:
            self.cur |= 1 << self.n
        self.n += 1
        if self.n == 8:
            self.buf.append(self.cur)
            self.cur = 0
            self.n = 0

    def raw(self, value, nbits):
        """A field: least-significant bit first (5.3.9's "read N bits")."""
        for i in range(nbits):
            self.bit((value >> i) & 1)

    def code(self, value, nbits):
        """A Shannon-Fano code: most-significant bit first."""
        for i in range(nbits - 1, -1, -1):
            self.bit((value >> i) & 1)

    def done(self):
        if self.n:
            self.buf.append(self.cur)
            self.cur = 0
            self.n = 0
        return bytes(self.buf)


# --- the trees ------------------------------------------------------

def sf_codes(lengths):
    """5.3.8 steps 1, 2 and 4, without step 3 — the reversal is the
    reader's (see BitOut.code). Visit the symbols longest code first and
    within one length in DECREASING symbol order; give the first a code
    of zero; take each one after it from the previous code shifted right
    by the drop in length, plus one.

    Returns {symbol: (code, length)}."""
    out = {}
    code = 0
    prevlen = 0
    first = True
    for l in range(max(lengths), 0, -1):
        for v in range(len(lengths) - 1, -1, -1):
            if lengths[v] != l:
                continue
            if first:
                code = 0
                first = False
            else:
                code = (code >> (prevlen - l)) + 1
            prevlen = l
            assert code < (1 << l), "over-subscribed at length %d" % l
            out[v] = (code, l)
    return out


def store_tree(lengths):
    """5.3.7: a count byte holding (number of RLE bytes - 1), then that
    many bytes of "high nibble = values at this bit length - 1, low
    nibble = bit length - 1". Run-length encoded over the symbols in
    order, each run at most 16 long and each length at most 16."""
    runs = []
    for l in lengths:
        assert 1 <= l <= 16
        if runs and runs[-1][0] == l and runs[-1][1] < 16:
            runs[-1][1] += 1
        else:
            runs.append([l, 1])
    assert len(runs) <= 256
    out = bytearray([len(runs) - 1])
    for l, n in runs:
        out.append(((n - 1) << 4) | (l - 1))
    return bytes(out)


def read_stored_tree(blob, pos, nsyms):
    """The inverse of `store_tree`, for the selftest only: 5.3.7 read
    rather than written. Asserting the stored form in BOTH directions is
    what makes the example's four bytes a pin on the layout and not just
    on the construction. `src/fmt_exo.c`'s `imp_read_lengths` is the
    engine's copy of this."""
    nrle = blob[pos] + 1
    pos += 1
    lengths = []
    for _ in range(nrle):
        b = blob[pos]
        pos += 1
        lengths.extend([(b & 0x0F) + 1] * ((b >> 4) + 1))
    if len(lengths) != nsyms:
        raise ValueError("%d values, expected %d" % (len(lengths), nsyms))
    return lengths, pos, nrle


def flat_lengths(nsyms, nbits):
    """A complete tree with every code the same length, which needs
    2**nbits == nsyms. The cheapest legal tree there is, and the one
    that makes a match's operand arithmetic readable."""
    assert 1 << nbits == nsyms
    return [nbits] * nsyms


def skewed_lengths(nsyms, maxlen=16):
    """A COMPLETE tree whose codes run from a couple of bits to
    `maxlen`, so that the decoder's bit-at-a-time walk is driven over
    its whole range instead of one length.

    Built so that completeness is structural rather than checked: start
    from the skinniest complete code that reaches `maxlen` at all —
    1, 2, ..., maxlen-1, maxlen, maxlen, whose Kraft sum is exactly 1 —
    and then SPLIT the shallowest leaf into two one bit longer, which
    preserves the sum and adds one symbol. Repeat until there are
    `nsyms` of them; the deep tail is never the shallowest, so it
    survives.

    A complete 64-symbol code has an average length near 6, so a
    16-bit code in one is not a thing a compressor would write — which
    is the point: two of the 24 trees in reach state a length-16 code
    and none of the 256-value ones does (FORMATS.md, *Implode, and what
    the corpus cannot reach*)."""
    lengths = list(range(1, maxlen)) + [maxlen, maxlen]
    if len(lengths) > nsyms:
        raise ValueError("%d symbols cannot carry a %d-bit code"
                         % (nsyms, maxlen))
    heapq.heapify(lengths)
    while len(lengths) < nsyms:
        d = heapq.heappop(lengths)
        if d + 1 > maxlen:
            raise ValueError("no room below %d bits for %d symbols"
                             % (maxlen, nsyms))
        heapq.heappush(lengths, d + 1)
        heapq.heappush(lengths, d + 1)
    out = sorted(lengths)
    assert sum(2 ** (maxlen - l) for l in out) == 2 ** maxlen
    return out


# --- one entry's stream ---------------------------------------------

# The tokens every shape emits, in order. Chosen for what each one
# reaches in the decoder rather than for compression:
#
#   literal runs            the literal path, both with a tree and with
#                           8 raw bits
#   (dist, length)          the ordinary match
#   a length of 63 + MML    5.3.9's escape, where 8 more bits follow
#   a match at distance 0   overlapping its own output, one byte wide
#   a match reaching back
#     past the start        5.3.9's "assume ... filled with zeros"
#   a match at the largest
#     distance the
#     dictionary holds      the distance operand at its full width
TEXT = (b"the quick brown fox jumps over the lazy dog, and the dog "
        b"did not mind at all.\n")


def encode(dictsize, three, body_out, mml=None):
    """One Implode stream, and the bytes it decodes to.

    `body_out` is appended to as tokens are emitted, so the caller gets
    the plaintext this stream IS rather than having to decode it — and
    `run_implode.py` then holds two other implementations to it.

    `mml` overrides the minimum match length. The default is 5.3.4's —
    3 where a literal tree is stored, 2 where it is not — and the
    override is what writes a stream PKZIP 1.01 or 1.02 wrote, which
    took it from the DICTIONARY SIZE instead. The flag word is
    identical either way, which is why the two readings can disagree at
    all: nothing in the entry says which was used, so the stored CRC-32
    is the only thing that can answer (FORMATS.md, *Implode*)."""
    lowbits = 7 if dictsize == 8192 else 6
    if mml is None:
        mml = 3 if three else 2

    # 5.3.5: the length alphabet is 64 values, mml..mml+63.
    # 5.3.6: the distance alphabet is 64 values, the upper 6 bits.
    # The distance tree is flat — six bits a code, which is complete
    # over 64 values and makes a match's operand arithmetic readable.
    # The length tree is given the full spread up to a 16-bit code
    # instead, so that one tree per entry drives the decoder's walk over
    # its whole range and the other drives the one-length case.
    distlen = flat_lengths(64, 6)
    lenlen = skewed_lengths(64)
    lencode = sf_codes(lenlen)
    distcode = sf_codes(distlen)
    header = bytearray()
    litcode = None
    if three:
        litlen = skewed_lengths(256)
        litcode = sf_codes(litlen)
        header += store_tree(litlen)
    header += store_tree(lenlen)
    header += store_tree(distlen)

    bits = BitOut()
    out = bytearray()

    def literal(b):
        bits.bit(1)
        if litcode is not None:
            c, n = litcode[b]
            bits.code(c, n)
        else:
            bits.raw(b, 8)
        out.append(b)

    def match(dist, length):
        """`dist` is the APPNOTE operand: the match starts dist+1 bytes
        back. `length` is the real length, mml..mml+63+255."""
        assert 0 <= dist < dictsize
        assert mml <= length <= mml + 63 + 255
        bits.bit(0)
        bits.raw(dist & ((1 << lowbits) - 1), lowbits)
        c, n = distcode[dist >> lowbits]
        bits.code(c, n)
        lc = length - mml
        if lc >= 63:
            c, n = lencode[63]
            bits.code(c, n)
            bits.raw(lc - 63, 8)
        else:
            c, n = lencode[lc]
            bits.code(c, n)
        # The same copy 5.3.9 describes, so the caller's plaintext is
        # the stream's and not a guess at it.
        start = len(out) - 1 - dist
        for i in range(length):
            at = start + i
            out.append(0 if at < 0 else out[at])

    # A match before anything has been written: 5.3.9's zeros.
    match(dictsize - 1, mml + 4)
    for b in TEXT:
        literal(b)
    # An ordinary match: the whole of TEXT again.
    match(len(TEXT) - 1, len(TEXT))
    # An overlapping one-byte run, which is how a long fill is coded.
    literal(ord("="))
    match(0, mml + 40)
    # The escape: a length past 63 + mml, so eight more bits follow.
    for b in TEXT:
        literal(b)
    match(len(TEXT) - 1, mml + 63 + 7)
    # Enough literals to pass the dictionary, so the window wraps and a
    # match crosses its end.
    filler = bytes((i * 37 + 11) & 0xFF for i in range(dictsize + 300))
    for b in filler:
        literal(b)
    match(dictsize - 1, 200)
    for b in b"end.\n":
        literal(b)

    body_out += out
    return bytes(header) + bits.done()


# --- the reading side, for a grader and for a sweep -----------------

class BitIn:
    """5.3.9's stream: least-significant bit first within each byte."""
    def __init__(self, data, pos, end=None):
        self.d = data
        self.p = pos
        self.end = len(data) if end is None else end
        self.buf = 0
        self.n = 0

    def bit(self):
        if self.n == 0:
            if self.p >= self.end:
                raise EOFError
            self.buf = self.d[self.p]
            self.p += 1
            self.n = 8
        b = self.buf & 1
        self.buf >>= 1
        self.n -= 1
        return b

    def raw(self, k):
        v = 0
        for i in range(k):
            v |= self.bit() << i
        return v


def decode(data, pos, clen, usize, flag8k, flag3trees, mml=None):
    """One Implode stream back to its bytes. The inverse of `encode`, and
    it shares this file's `sf_codes` and `read_stored_tree` with it so
    that there is ONE Python reading of 5.3 here rather than two.

    `mml` overrides the minimum match length, which is the whole point of
    exposing it: PKZIP 1.01 and 1.02 took it from the DICTIONARY SIZE
    rather than from the literal tree's presence, so a stream can be
    tried both ways and graded by the CRC-32 the archive stored — which
    is how `tools/scan_discmaster.py`'s `implode` probe asks a stranger's
    zip which generation wrote it, and how deark's own
    `detect_implode_mml_bug` decides.

    Used by `--selftest` to round-trip every shape this file writes, and
    by that probe. NOT by the engine, which is `src/fmt_exo.c`."""
    end = pos + clen
    p = pos
    nvals = (256, 64, 64) if flag3trees else (64, 64)
    trees = []
    for nv in nvals:
        lengths, p, _nrle = read_stored_tree(data, p, nv)
        codes = sf_codes(lengths)
        trees.append({(c, l): v for v, (c, l) in codes.items()})
    if flag3trees:
        littree, lentree, disttree = trees
    else:
        littree = None
        lentree, disttree = trees
    if mml is None:
        mml = 3 if flag3trees else 2
    dictsize = 8192 if flag8k else 4096
    lowbits = 7 if flag8k else 6

    br = BitIn(data, p, end)
    out = bytearray()

    def code(tree):
        c = 0
        for l in range(1, 17):
            c = (c << 1) | br.bit()
            if (c, l) in tree:
                return tree[(c, l)]
        raise ValueError("no code of any length")

    while len(out) < usize:
        if br.bit():
            out.append(code(littree) if littree is not None else br.raw(8))
        else:
            lo = br.raw(lowbits)
            dist = (code(disttree) << lowbits) | lo
            lc = code(lentree)
            mlen = mml + 63 + br.raw(8) if lc == 63 else mml + lc
            start = len(out) - 1 - dist
            if start < -dictsize:
                raise ValueError("distance past the dictionary")
            for i in range(mlen):
                at = start + i
                out.append(0 if at < 0 else out[at])
    return bytes(out[:usize])


# --- the zip --------------------------------------------------------

# (name, dictionary, three trees, minimum match length or None for
# 5.3.4's). All four combinations, because the point of writing them is
# that a fixture reaches only some: the two PKZIP 1.x fixtures are
# 4K/2-tree and 8K/3-tree, and 8K/2-tree and 4K/3-tree come only from a
# ZipIt specimen that cannot be committed (FORMATS.md, *Implode, and
# what the corpus cannot reach*).
SHAPES = (
    ("4k-2trees", 4096, False, None),
    ("4k-3trees", 4096, True, None),
    ("8k-2trees", 8192, False, None),
    ("8k-3trees", 8192, True, None),
)

# PKZIP 1.01 and 1.02's reading: the minimum match length comes from the
# DICTIONARY SIZE — 3 at 8 K, 2 at 4 K — rather than from the literal
# tree's presence. Only these two combinations can tell the two readings
# apart; with both flag bits set or neither, both rules name the same
# length and a stream is the same stream.
#
# NOT in SHAPES, and that is deliberate: both this engine and deark
# settle the question per ARCHIVE from the first bug-capable entry, so a
# committed fixture holding both readings would make the differential
# suite grade that decision rather than the decoder. `run_implode.py`
# writes these two into an archive of their own.
BUGSHAPES = (
    ("8k-2trees-mmlbug", 8192, False, 3),
    ("4k-3trees-mmlbug", 4096, True, 2),
)
ALLSHAPES = SHAPES + BUGSHAPES

# --mixed: one archive carrying BOTH readings, bug-written entry first,
# at the same ambiguous flag combination. No writer is known to make one
# — no archive of 1,537 in the 2026-10-08 sweep mixes — but a zip is
# appendable and PKZIP 1.1 wrote Implode too, so it is a shape the
# format allows and the engine has to behave sanely on. The order is
# fixed and load-bearing: the FIRST entry settles the archive, so a
# bug-written first entry is what leaves the two after it inheriting a
# verdict that is wrong about them. Graded by `run_implode.py`'s fourth
# lane against each entry's own stored CRC-32, which is the only oracle
# available here: deark settles per archive as well, so it gets the same
# entries wrong (DECISIONS.md 2026-10-08, *the writer a zip is allowed
# to have twice*).
MIXEDSHAPES = (
    ("mixed-bug", 4096, True, 2),
    ("mixed-spec", 4096, True, None),
    ("mixed-spec2", 4096, True, None),
)

DOS_DATE = 0x1421          # 1990-01-01, matching synth_exo.py's MTIME
DOS_TIME = 0x0000


# APPNOTE.TXT 5.3.8's own worked example, verbatim: the stored tree
# `0x02, 0x42, 0x01, 0x13`, the bit lengths it decodes to, and the codes
# the construction must produce for them. The document prints the codes
# bit-reversed (its step 3); `sf_codes` omits that step because reading
# a code most-significant-bit-first out of a least-significant-bit-first
# stream performs it, so the expectation here is each printed code with
# its own bits reversed back.
#
# This is the strongest pin available for the construction: it is the
# specification's table rather than any implementation's output, and it
# holds `sf_codes` — which `src/fmt_exo.c`'s `imp_build` has to agree
# with, or `tools/run_implode.py` fails on every shape.
APPNOTE_EXAMPLE_STORED = bytes((0x02, 0x42, 0x01, 0x13))
APPNOTE_EXAMPLE_LENGTHS = (3, 3, 3, 3, 3, 2, 4, 4)
# value: the code 5.3.8 prints in its "Order Restored" column
APPNOTE_EXAMPLE_CODES = ("101", "001", "110", "010", "100", "11",
                         "1000", "0000")


def selftest():
    """Hold `sf_codes` and `store_tree` to APPNOTE 5.3.8's example.
    Returns the number of failures."""
    bad = 0
    lengths, pos, nrle = read_stored_tree(APPNOTE_EXAMPLE_STORED, 0, 8)
    if tuple(lengths) != APPNOTE_EXAMPLE_LENGTHS:
        print("synth_implode: 5.3.8's example stores %r, decoded as %r"
              % (APPNOTE_EXAMPLE_LENGTHS, tuple(lengths)), file=sys.stderr)
        bad += 1
    if pos != len(APPNOTE_EXAMPLE_STORED) or nrle != 3:
        print("synth_implode: 5.3.8's example is 3 RLE bytes over %d, read "
              "%d over %d" % (len(APPNOTE_EXAMPLE_STORED), nrle, pos),
              file=sys.stderr)
        bad += 1
    if store_tree(list(APPNOTE_EXAMPLE_LENGTHS)) != APPNOTE_EXAMPLE_STORED:
        print("synth_implode: storing 5.3.8's lengths does not give its own "
              "bytes back: %r" % (store_tree(list(APPNOTE_EXAMPLE_LENGTHS)),),
              file=sys.stderr)
        bad += 1
    codes = sf_codes(list(APPNOTE_EXAMPLE_LENGTHS))
    for v, printed in enumerate(APPNOTE_EXAMPLE_CODES):
        want = int(printed[::-1], 2)        # un-reverse 5.3.8's step 3
        got, n = codes[v]
        if (got, n) != (want, len(printed)):
            print("synth_implode: 5.3.8 gives value %d the code %s (%d bits); "
                  "sf_codes gives %s (%d bits)"
                  % (v, printed, len(printed),
                     format(got, "0%db" % n)[::-1], n), file=sys.stderr)
            bad += 1
    # And a round trip per shape, through this file's own reader: the
    # encoder and the decoder share `sf_codes` and `read_stored_tree`,
    # so this cannot catch a wrong reading of 5.3.8 — the example above
    # is what does that — but it does catch a wrong WRITING of the
    # token stream, which the example cannot reach.
    for name, dictsize, three, mml in ALLSHAPES:
        body = bytearray()
        stream = encode(dictsize, three, body, mml)
        try:
            got = decode(stream, 0, len(stream), len(body),
                         dictsize == 8192, three, mml)
        except Exception as e:                            # noqa: BLE001
            print("synth_implode: %s does not read back: %s" % (name, e),
                  file=sys.stderr)
            bad += 1
            continue
        if got != bytes(body):
            print("synth_implode: %s reads back %d B, coded %d"
                  % (name, len(got), len(body)), file=sys.stderr)
            bad += 1
    # **A bug stream that also reads back under 5.3.4 would grade
    # nothing**, so that is asserted rather than assumed. Each of the two
    # is read with the minimum match length the SPECIFICATION's rule
    # gives its flag word, and is required to come out wrong or not at
    # all. (It cannot be an accident either way: the lengths this writer
    # codes are mml-relative, so every match in the stream shifts by one
    # byte.)
    for name, dictsize, three, mml in BUGSHAPES:
        body = bytearray()
        stream = encode(dictsize, three, body, mml)
        try:
            got = decode(stream, 0, len(stream), len(body),
                         dictsize == 8192, three)     # 5.3.4's reading
        except Exception:                                 # noqa: BLE001
            continue                      # refused, which is a failure
        if got == bytes(body):
            print("synth_implode: %s reads back IDENTICALLY under "
                  "APPNOTE 5.3.4's minimum match length, so it is not a "
                  "subject for the 1.01/1.02 rule at all" % name,
                  file=sys.stderr)
            bad += 1
    if not bad:
        print("synth_implode: selftest ok (APPNOTE.TXT 5.3.8's worked "
              "example, %d codes, the stored form both ways, all %d "
              "shapes round-tripped, and both PKZIP 1.01/1.02 shapes "
              "refused by 5.3.4's rule)"
              % (len(APPNOTE_EXAMPLE_CODES), len(ALLSHAPES)))
    return bad


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output")
    ap.add_argument("--ranges", help="write the compressed byte spans "
                                     "here as JSON, for tools/fuzz.py")
    ap.add_argument("--only", action="append", default=[], metavar="SHAPE",
                    help="one or more of: "
                         + ", ".join(s[0] for s in ALLSHAPES)
                         + ". The default is the four 5.3.4 shapes; the "
                           "two `-mmlbug` ones are only written when "
                           "named, because they belong in an archive of "
                           "their own")
    ap.add_argument("--plain", help="write the concatenated plaintext of "
                                    "every entry here, for a grader")
    ap.add_argument("--mixed", action="store_true",
                    help="write MIXEDSHAPES instead: one archive carrying "
                         "both readings, the bug-written entry first, so "
                         "the two after it inherit a verdict that is wrong "
                         "about them")
    ap.add_argument("--selftest", action="store_true",
                    help="hold the code construction to APPNOTE.TXT "
                         "5.3.8's own worked example and stop")
    a = ap.parse_args()

    if a.selftest:
        return 1 if selftest() else 0

    if not a.output:
        ap.error("-o/--output is required (or --selftest)")

    shapes = MIXEDSHAPES if a.mixed else SHAPES
    if a.only:
        known = {s[0] for s in ALLSHAPES}
        bad = [n for n in a.only if n not in known]
        if bad:
            print("synth_implode: no shape named %s — have %s"
                  % (", ".join(bad), ", ".join(sorted(known))),
                  file=sys.stderr)
            return 1
        shapes = tuple(s for s in ALLSHAPES if s[0] in a.only)

    blob = bytearray()
    ranges = []
    central = bytearray()
    plain = bytearray()
    bodies = []
    nent = 0
    for name, dictsize, three, mml in shapes:
        body = bytearray()
        stream = encode(dictsize, three, body, mml)
        fn = ("%s.txt" % name).encode("ascii")
        # 5.3.2 and 5.3.3: bit 1 is the dictionary size, bit 2 the tree
        # count. Nothing else is set — no data descriptor, no
        # encryption, no UTF-8 name flag.
        flags = (0x0002 if dictsize == 8192 else 0) | (0x0004 if three else 0)
        crc = zlib.crc32(bytes(body)) & 0xFFFFFFFF
        lhoffs = len(blob)
        blob += struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, flags, 6,
                            DOS_TIME, DOS_DATE, crc, len(stream), len(body),
                            len(fn), 0)
        blob += fn
        # What fuzz.py may mutate: the trees and the token stream, which
        # is the whole of the entry's data and nothing of its framing.
        ranges.append((len(blob), len(blob) + len(stream)))
        blob += stream
        central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20,
                               flags, 6, DOS_TIME, DOS_DATE, crc,
                               len(stream), len(body), len(fn), 0, 0,
                               0, 0, 0, lhoffs)
        central += fn
        plain += body
        bodies.append((name, bytes(body)))
        nent += 1

    cdoffs = len(blob)
    blob += central
    blob += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, nent, nent,
                        len(central), cdoffs, 0)

    with open(a.output, "wb") as fh:
        fh.write(blob)
    if a.ranges:
        with open(a.ranges, "w") as fh:
            json.dump([list(r) for r in ranges], fh)
    if a.mixed and a.plain:
        # The mixed lane grades per ENTRY, and its three bodies differ
        # (the minimum match length changes the matches the encoder can
        # take), so the concatenation is useless to it: write one file
        # per entry beside the path given.
        for name, body in bodies:
            with open("%s.%s" % (a.plain, name), "wb") as fh:
                fh.write(body)
    if a.plain:
        with open(a.plain, "wb") as fh:
            fh.write(plain)
    print("synth_implode: %s — %d entr%s, %d B, %d compressed span(s)"
          % (os.path.basename(a.output), nent,
             "y" if nent == 1 else "ies", len(blob), len(ranges)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

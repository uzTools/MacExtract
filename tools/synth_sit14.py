#!/usr/bin/env python3
"""synth_sit14.py — write a StuffIt 5 archive whose forks use method 14.

Why this exists: no corpus fixture uses method 14. The two archives that
settled the decoder are StuffIt Deluxe 5.5's and 7.0.3's own installer
payloads, 6.6 MB and 12.4 MB of commercial software that this machine
cannot commit and `harvest.py --restore` would have to fetch through a
browser user agent (FORMATS.md, *Method 14*). So the shape is written
here instead, from scratch, and graded against `unar` — which reads
method 14 — exactly as the ciphers are in synth_crypt.py.

This is an ENCODER for the format sit14.c decodes, and that is the point:
it was written from the same reading of libxad's SIT_14 and agrees with a
third implementation about every byte it produces. What it does not do is
SEARCH for matches — the symbol script is written by hand below, so that
each case names the shape it covers rather than depending on what a
matcher happened to find.

    tools/synth_sit14.py -o fixtures/synth-sit14.sit
    tools/synth_sit14.py --wrap -o seed.sit --ranges seed.ranges

`--wrap` adds a fifth entry whose FORK is 278,896 B, which is the only
shape that reaches sit14_flush's window wrap — and is NOT the committed
fixture, because 294,528 B of peak heap is a tier (DECISIONS.md
2026-10-06, *the fork that was cheaper than the file*). It is graded by
tools/run_sit14wrap.py and fuzzed as fuzz.py's `sit14-wrap` shape.

Deterministic: same bytes every run (check_docs.py compares the sha256 in
fixtures/SOURCES.md, which is the DEFAULT output — `--wrap` adds to it
and must leave those 1,859 bytes alone).
"""
import argparse
import hashlib
import json
import struct
import sys

SIT5_BANNER = (b"StuffIt (c)1997-2026 Aladdin Systems, Inc., "
               b"http://www.aladdinsys.com/StuffIt/\x0d\x0a")

LITSYMS = 308
OFFSYMS = 75
LENCODES = 52
LENBIAS = 4


# ---------------------------------------------------------------------------
# The two ladders, which are the decoder's and are built the same way
# ---------------------------------------------------------------------------

def ladders():
    lenbase, lenextra, k = [], [], 0
    for i in range(LENCODES):
        e = (i - 4) >> 2 if i >= 4 else 0
        lenextra.append(e)
        lenbase.append(k)
        k += 1 << e
    offbase, offextra, k = [], [], 1
    for i in range(OFFSYMS):
        e = (i - 3) >> 2 if i >= 3 else 0
        offextra.append(e)
        offbase.append(k)
        k += 1 << e
    return lenbase, lenextra, offbase, offextra


LENBASE, LENEXTRA, OFFBASE, OFFEXTRA = ladders()


def len_code(length):
    """The (symbol, extra-bit value) that codes a match of `length`."""
    for i in range(LENCODES):
        lo = LENBASE[i] + LENBIAS
        if lo <= length <= lo + (1 << LENEXTRA[i]) - 1:
            return 0x100 + i, length - lo
    raise ValueError("match length %d is past the ladder" % length)


def off_code(dist):
    for i in range(OFFSYMS):
        lo = OFFBASE[i]
        if lo <= dist <= lo + (1 << OFFEXTRA[i]) - 1:
            return i, dist - lo
    raise ValueError("distance %d is past the ladder" % dist)


# ---------------------------------------------------------------------------
# Bits, LSB-first within each byte (libxad's xadIOGetBitsLow)
# ---------------------------------------------------------------------------

class BitOut:
    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def put(self, value, bits):
        for i in range(bits):
            self.acc |= ((value >> i) & 1) << self.n
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc)
                self.acc = 0
                self.n = 0

    def align(self):
        """Pad the byte with ZEROS, which is what the decoder's reading of
        xadIOByteBoundary rests on (sit14.c)."""
        if self.n:
            self.out.append(self.acc)
            self.acc = 0
            self.n = 0

    def bytes(self):
        assert self.n == 0, "align() before taking the bytes"
        return bytes(self.out)


# ---------------------------------------------------------------------------
# Canonical codes — SIT14_Update and the assignment after it, in Python
# ---------------------------------------------------------------------------

def sit14_sort(key, val):
    """libxad's SIT14_Update: the partition decides where equal lengths
    end up, and that decides the codes, so it is transcribed rather than
    replaced by sorted()."""
    stack = []
    first, last = 0, len(key)
    while True:
        while last - first > 1:
            i, j = first, last
            while True:
                i += 1
                while i < last and key[first] > key[i]:
                    i += 1
                j -= 1
                while j > first and key[first] < key[j]:
                    j -= 1
                if j > i:
                    key[i], key[j] = key[j], key[i]
                    val[i], val[j] = val[j], val[i]
                if not j > i:
                    break
            if first != j:
                key[first], key[j] = key[j], key[first]
                val[first], val[j] = val[j], val[first]
                i = j + 1
                if last - i <= j - first:
                    stack.append((i, last))
                    last = j
                else:
                    stack.append((first, j))
                    first = i
            else:
                first += 1
        if not stack:
            return
        first, last = stack.pop()


def assign_codes(lens):
    """Each symbol's code, bit-reversed the way the decoder expects to
    take it off the bottom of the stream."""
    key, val = list(lens), list(range(len(lens)))
    sit14_sort(key, val)
    codes = [0] * len(lens)
    i = 0
    while i < len(lens) and key[i] == 0:
        i += 1
    j = 0
    while i < len(lens):
        if i:
            j <<= (key[i] - key[i - 1])
        rev, l = 0, j
        for _ in range(key[i]):
            rev = (rev << 1) | (l & 1)
            l >>= 1
        codes[val[i]] = rev
        i += 1
        j += 1
    return codes


def put_code(bo, code, length):
    for b in range(length):
        bo.put((code >> b) & 1, 1)


# ---------------------------------------------------------------------------
# Serializing a tree
# ---------------------------------------------------------------------------

# Width 5 gives raw values 0..31: 0..29 are lengths 1..30 at bias 1, 30 is
# "this symbol is unused" and 31 introduces a repeat.
WIDTH = 5
BIAS = 1


def length_script(lens):
    """The raw values that spell `lens` out, with runs of three or more
    turned into the repeat escape — which is the escape 8,665 of the
    7.0.3 payload's tree reads use (FORMATS.md, *Method 14*)."""
    zero = (1 << WIDTH) - 2
    rep = (1 << WIDTH) - 1
    script = []
    i = 0
    while i < len(lens):
        v = zero if lens[i] == 0 else lens[i] - BIAS
        script.append(("raw", v))
        i += 1
        run = 0
        while i + run < len(lens) and lens[i + run] == lens[i - 1]:
            run += 1
        while run >= 3:
            take = min(run, (1 << WIDTH) - 1 + 3)
            script.append(("rep", take - 3))
            i += take
            run -= take
    return script


def write_tree(bo, lens, nested):
    """One tree: the header, then the code lengths, then the boundary the
    decoder byte-aligns on."""
    bo.put(1, 1)                 # a zero escape exists
    bo.put(WIDTH - 2, 2)
    bo.put(BIAS - 1, 3)
    bo.put(1 if nested else 0, 2)

    # Both escapes are values in the same alphabet as a length, and a
    # repeat is TWO of them: the escape, then the count less three.
    script = []
    for kind, v in length_script(lens):
        if kind == "rep":
            script.append((1 << WIDTH) - 1)
        script.append(v)

    if not nested:
        for v in script:
            bo.put(v, WIDTH)
    else:
        # The nested alphabet is the OUTER width's raw values — 32 of
        # them — and every one gets a 5-bit code, which is a complete
        # code and needs no frequency count.
        sub = [WIDTH] * (1 << WIDTH)
        write_tree(bo, sub, False)
        subcodes = assign_codes(sub)
        for v in script:
            put_code(bo, subcodes[v], sub[v])
    bo.align()


# ---------------------------------------------------------------------------
# A block
# ---------------------------------------------------------------------------

def write_block(bo, script, nested):
    """`script` is a list of ('lit', byte) and ('match', length, dist).
    Returns the bytes it expands to."""
    litlens = [0] * LITSYMS
    offlens = [0] * OFFSYMS
    for item in script:
        if item[0] == "lit":
            litlens[item[1]] = 1
        else:
            sym, _ = len_code(item[1])
            litlens[sym] = 1
            osym, _ = off_code(item[2])
            offlens[osym] = 1

    # A flat code over the symbols each block actually uses: the length
    # is ceil(log2(count)) for all of them, which is a valid canonical
    # code and keeps the generator free of a Huffman builder.
    def flatten(flags):
        used = [i for i, f in enumerate(flags) if f]
        if not used:
            return [0] * len(flags), []
        width = max(1, (len(used) - 1).bit_length())
        out = [0] * len(flags)
        for i in used:
            out[i] = width
        return out, used

    litlens, _ = flatten(litlens)
    offlens, _ = flatten(offlens)
    litcodes = assign_codes(litlens)
    offcodes = assign_codes(offlens)

    out = bytearray()
    for item in script:
        if item[0] == "lit":
            out.append(item[1])
        else:
            length, dist = item[1], item[2]
            at = len(out) - dist
            if at < 0:
                raise ValueError("a match before the start of the fork")
            for _ in range(length):
                out.append(out[at])
                at += 1

    body = BitOut()
    write_tree(body, litlens, nested)
    write_tree(body, offlens, nested)
    for item in script:
        if item[0] == "lit":
            put_code(body, litcodes[item[1]], litlens[item[1]])
        else:
            sym, extra = len_code(item[1])
            put_code(body, litcodes[sym], litlens[sym])
            if LENEXTRA[sym - 0x100]:
                body.put(extra, LENEXTRA[sym - 0x100])
            osym, oextra = off_code(item[2])
            put_code(body, offcodes[osym], offlens[osym])
            if OFFEXTRA[osym]:
                body.put(oextra, OFFEXTRA[osym])
    body.align()
    blob = body.bytes()

    bo.put(len(blob) & 0xFFFF, 16)      # crunched size: the decoder skips
    bo.put(len(blob) >> 16, 16)         # it, and so does libxad
    bo.put(len(out) & 0xFFFF, 16)
    bo.put(len(out) >> 16, 16)
    for b in blob:
        bo.put(b, 8)
    return bytes(out)


def encode(blocks):
    """blocks: a list of (script, nested). Returns (stream, decoded)."""
    bo = BitOut()
    bo.put(len(blocks), 16)
    out = bytearray()
    for script, nested in blocks:
        out += write_block(bo, script, nested)
    bo.align()
    return bo.bytes(), bytes(out)


# ---------------------------------------------------------------------------
# What the fixture covers
# ---------------------------------------------------------------------------

def lits(text):
    return [("lit", b) for b in text]


def wrap_case():
    """A fork past the format's window, which is what reaches the second
    half of sit14.c's `sit14_flush`.

    The window is sized to the FORK (`sit14_winsize`), so a flush can
    straddle the end of it only once `pos` has passed 0x40000 — and the
    flush threshold is a quarter of the window, so the flush points sit
    on multiples of it until a match pushes them off. Seventeen maximum
    matches do both: the fork is 278,896 B, the flush at 196,648 carries
    65,548 B, which is 52 B past the end of the window, and decoding
    goes on for another 16 KB after it.
    /* Source: src/sit14.c, SIT14_WINDOW/sit14_winsize/sit14_flush,
       transcribed from libxad SIT_14 */

    It costs 458 B of stream. That is the whole trick: what has to be
    large is the FORK, and a fork is what a match ladder makes cheap —
    the shape was filed as out of reach for a seed on the strength of a
    17,799 B figure that was the largest fork the four shapes above
    happen to decode to, not a limit of this encoder (BLOCKERS.md,
    *Withdrawn claims*).

    The distances cycle rather than repeat, and the literal in front of
    each match changes, so the fork has no period under 4,096 B — a
    payload periodic in p would hide a wrap that misplaced a multiple of
    p bytes, i.e. would be graded by `unar` and agree anyway.
    """
    script = lits(bytes((i * 13 + 5) & 0xFF for i in range(300)))
    dists = [4, 301, 16388, 33000]
    for i in range(17):
        script.append(("lit", (i * 37 + 1) & 0xFF))
        script.append(("match", 16387, dists[i % len(dists)]))
    return script


def cases(wrap=False):
    """One entry per shape, each named for what it is the only subject of."""
    out = []

    # 1. Literals alone, in two blocks: the block loop runs twice and the
    #    second block's trees replace the first's.
    out.append(("literals-two-blocks", [
        (lits(bytes((i * 7 + 3) & 0xFF for i in range(200))), False),
        (lits(bytes((i * 31 + 11) & 0xFF for i in range(100))), False),
    ]))

    # 2. Matches with no extra bits: length 4 at distance 1 is the
    #    shortest match the ladder can state, and distance 1 is the
    #    overlapping copy that has to be byte at a time.
    out.append(("matches-shortest", [
        (lits(b"abcd") + [("match", 4, 1), ("match", 4, 4)] + lits(b"xy"),
         False),
    ]))

    # 3. Extra bits on both ladders at once, and the longest match the
    #    format can code (16,387 bytes — the 7.0.3 payload reaches it).
    script = lits(bytes((i * 13 + 5) & 0xFF for i in range(300)))
    script += [("match", 12, 8), ("match", 100, 300), ("match", 1000, 64)]
    script += [("match", 16387, 1)]
    out.append(("extra-bits-and-the-longest-match", [(script, False)]))

    # 4. The nested tree — the code lengths themselves Huffman-coded,
    #    which is what 524 of the 7.0.3 payload's 1,132 tree reads do.
    out.append(("nested-tree", [
        (lits(bytes((i * 5 + 1) & 0xFF for i in range(256)))
         + [("match", 20, 128)], True),
    ]))

    # 5. The window wrap, only with --wrap: this entry's fork is 278,896
    #    B and the four above are 18,389 B all told, so it is NOT in the
    #    committed fixture — a 256 KB window is a peak-RAM figure, a
    #    budget-sweep row and a Macintosh tier, and none of those should
    #    move to cover a branch (DECISIONS.md 2026-10-06).
    if wrap:
        out.append(("window-wrap", [(wrap_case(), False)]))

    return out


# ---------------------------------------------------------------------------
# The StuffIt 5 container
# ---------------------------------------------------------------------------

CRC16_TABLE = None


def crc16_arc(data):
    global CRC16_TABLE
    if CRC16_TABLE is None:
        CRC16_TABLE = []
        for n in range(256):
            c = n
            for _ in range(8):
                c = (c >> 1) ^ (0xA001 if c & 1 else 0)
            CRC16_TABLE.append(c)
    crc = 0
    for b in data:
        crc = (crc >> 8) ^ CRC16_TABLE[(crc ^ b) & 0xFF]
    return crc


def build(wrap=False):
    """Returns (bytes, ranges) — `ranges` being the half-open byte span of
    each entry's method-14 stream in the file, the same contract
    `synth_crypt.py --ranges` has for ciphertext. A mutator confined to
    those spans corrupts what the DECODER reads and nothing the
    container checks on the way in: 1,345 B of the 1,859, the rest being
    an 80-byte banner and four entry headers that refuse the file when a
    mutation lands in them. Worth 95.5 % of the decoder's lines to
    98.5 % over 120 cases (TESTING.md, *Fuzzing*)."""
    entries = []
    for name, blocks in cases(wrap):
        stream, data = encode(blocks)
        entries.append((name, data, stream))

    head = bytearray(82)
    head[:len(SIT5_BANNER)] = SIT5_BANNER[:82]
    head += bytes([5, 0])                        # version 5, no flags
    head += struct.pack(">I", 0)                 # total size (patched)
    head += struct.pack(">I", 0)
    head += struct.pack(">H", len(entries))
    head += struct.pack(">I", 0)                 # first entry (patched)
    head += struct.pack(">H", 0)                 # crc, unchecked by both
    firstoffs = len(head)
    struct.pack_into(">I", head, 94, firstoffs)

    body = bytearray()
    ranges = []
    for name, data, stream in entries:
        nb = name.encode("mac_roman")
        e = bytearray()
        e += struct.pack(">I", 0xA5A5A5A5)       # 0  id
        e += bytes([1, 0])                       # 4  version, ?
        e += struct.pack(">H", 0)                # 6  header size (patched)
        e += bytes([0, 0])                       # 8  ?, flags
        e += struct.pack(">II", 0xA5000000, 0xA6000000)   # 10 dates
        e += struct.pack(">III", 0, 0, 0)        # 18 prev, next, parent
        e += struct.pack(">H", len(nb))          # 30 name length
        e += struct.pack(">H", 0)                # 32 header crc (unchecked)
        e += struct.pack(">II", len(data), len(stream))   # 34 sizes
        e += struct.pack(">H", crc16_arc(data))  # 42 crc over the OUTPUT
        e += struct.pack(">H", 0)                # 44 ?
        e += bytes([14, 0])                      # 46 method 14, no key
        e += nb
        struct.pack_into(">H", e, 6, len(e))
        e += struct.pack(">H", 0)                # flags2: no resource fork
        e += struct.pack(">H", 0)
        e += b"TEXTttxt"
        e += struct.pack(">H", 0)                # finder flags
        e += bytes(22)                           # version 1 filler
        ranges.append((firstoffs + len(body) + len(e),
                       firstoffs + len(body) + len(e) + len(stream)))
        e += stream
        body += e

    struct.pack_into(">I", head, 84, firstoffs + len(body))
    blob = bytes(head) + bytes(body)
    # The ranges are what a mutator trusts, and a range off by a header
    # would point it at the container — which costs reach and nothing
    # else, so nothing would say so. Checked here, where both halves
    # are in hand.
    assert len(ranges) == len(entries)          # or zip() checks a prefix
    for (lo, hi), (_n, _d, stream) in zip(ranges, entries):
        assert blob[lo:hi] == stream, "stream range %d..%d is not it" % (lo, hi)
    return blob, ranges


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--wrap", action="store_true",
                    help="add the fifth shape, a fork past the format's "
                         "0x40000-byte window — the only one that reaches "
                         "sit14_flush's wrap. Not the committed fixture: "
                         "its 278,896-byte fork would move a peak-RAM "
                         "figure and a Macintosh tier")
    ap.add_argument("--ranges",
                    help="write the method-14 stream ranges of the output "
                         "to this file as JSON, for a mutator that wants "
                         "the decoder and not the container")
    args = ap.parse_args()
    blob, ranges = build(args.wrap)
    with open(args.out, "wb") as fh:
        fh.write(blob)
    if args.ranges:
        with open(args.ranges, "w") as fh:
            json.dump(ranges, fh)
    print("%s: %d B, sha256 %s, %d stream(s) over %d B"
          % (args.out, len(blob), hashlib.sha256(blob).hexdigest(),
             len(ranges), sum(hi - lo for lo, hi in ranges)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

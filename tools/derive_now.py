#!/usr/bin/env python3
"""derive_now.py — one of Now Compress's stream shapes, derived from
the application's own output, and a tool that re-runs the reading.

Now Compress is the last format in this project's inventory with **no
published description of any kind** — no wiki page, no specification,
no second implementation: `XADNowCompressHandle.m` is the only account
of it that exists (OPEN_ITEMS.md). So this one could not be fetched;
it had to be measured.

What it was measured from is the application itself.
`tools/vmac/nowcompress.py` drives Now Compress under the emulator and
compresses files chosen here, keeping the inputs beside the outputs in
`$UNC_VMAC_HOME/specimens/now/`. This tool reads those pairs back with
a decoder written from nothing but the bytes.

    tools/derive_now.py                       the harness's specimens
    tools/derive_now.py ARCHIVE...            walk a .sea or .now
    tools/derive_now.py --expect DIR ARCHIVE  grade it against DIR, a
                                              directory of extracted forks

**All four coders, the block structure, and the container a compressed
file and an archive share** — a compressed file is an archive of one
entry. Every specimen the harness has made reads byte for byte — 85
archive blocks of 85, 101 specimens across twelve cases — and so does
every block of both corpus archives: the 1993 `Expand Now`
self-extractor, 3 of 3, and the 1995 `SyntheticReferences2.0`, 306 of
306, whose 9.9 MB fork alone is 304 blocks of the coder an archive
uses.

**Nothing is searched for.** A block table is one layout at one offset
width, a shape-3 block's header says where its stream starts and ends,
and four checksums — over the file header, each entry record, each
block table and each block — say a walk is on the rails
(docs/formats/now-compress.md).

Not in `ci.sh`: it needs the emulator's specimen directory.
"""
import argparse
import os
import sys

HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "now")

# Every stream this reads puts its payload here. Four specimens, two
# modes, two very different files — so it is a fixed header and not a
# coincidence, but 164 is an observation and not a field anybody has
# read out of the header.
PAYLOAD_AT = 164


def decode(d, p, nout=None, hist=b"", endbyte=None):
    """The shape.

    A flag byte, then eight tokens, its bits taken most significant
    first: a 1 is a literal byte, a 0 is a match.

    **A match is two bytes holding a 3-bit length and a 13-bit
    distance** — `length = (b0 & 7) + 2` and
    `distance = ((b0 >> 3) << 8) | b1` — and a length of 2, the low
    three bits zero, escapes to a third byte carrying `length - 2`.
    That is the same rule shape 2 uses on symbols instead of bytes,
    which is what says it is right: this note read it as "a length
    byte then a distance byte" until 2026-09-21, a reading that agrees
    with this one whenever the distance is under 256 and which every
    shape-1 specimen here obeys (BLOCKERS.md, *Withdrawn claims*).

    Nothing in the stream says when to stop. The caller's byte count
    does — the same as StuffIt method 8 and ARC's squeeze.
    """
    out = bytearray()
    while (p < endbyte) if endbyte is not None else (len(out) < nout):
        if p >= len(d):
            raise EOFError
        flags = d[p]
        p += 1
        for bit in range(8):
            if endbyte is not None:
                if p >= endbyte and bit:
                    break
            elif len(out) >= nout:
                break
            if flags & (0x80 >> bit):
                out.append(d[p])
                p += 1
            else:
                s, low = d[p], d[p + 1]
                p += 2
                ln = (s & 7) + 2
                dist = ((s >> 3) << 8) | low
                if (s & 7) == 0:
                    ln = d[p] + 2
                    p += 1
                if dist == 0 or dist > len(hist) + len(out):
                    raise ValueError("distance %d" % dist)
                for _ in range(ln):
                    at = len(hist) + len(out) - dist
                    out.append(hist[at] if at < len(hist)
                               else out[at - len(hist)])
    return bytes(out[:nout] if nout is not None else out), p


# ------------------------------------------------------------ shape 2

TABLE_AT = 163          # where the 128-byte code-length table sits


def build(lengths):
    """Canonical, shortest first, assigned in symbol order, read
    most-significant-bit first."""
    t = {}
    code = 0
    for length in range(1, 17):
        for i, l in enumerate(lengths):
            if l == length:
                t[(length, code)] = i
                code += 1
        code <<= 1
    return t


class Bits:
    __slots__ = ("d", "p")

    def __init__(self, d, bitpos):
        self.d = d
        self.p = bitpos

    def bit(self):
        v = (self.d[self.p >> 3] >> (7 - (self.p & 7))) & 1
        self.p += 1
        return v

    def sym(self, t):
        c = 0
        for length in range(1, 17):
            c = (c << 1) | self.bit()
            if (length, c) in t:
                return t[(length, c)]
        raise ValueError("no code")


def table_at(d, at=TABLE_AT):
    """256 code lengths, four bits each, high nibble first, then **a
    count of "extra length" entries and that many symbol indices**,
    each of which gains 16 — the escape that lets a code run past the
    15 four bits can hold. Kraft's equality is what says the result is
    a code.

    No block the ENCODER wrote has ever set that count — the deepest
    code in any specimen is 13, and `--case deep` asked for a deeper one
    eight times in vain. What the escape means was measured instead by
    writing one: `tools/mutate_now.py --recode 20`, read back by Now
    Compress's own Decompress.
    """
    L, esc = table_lengths(d, at)
    if abs(sum(2.0 ** -x for x in L if x) - 1.0) > 1e-9:
        raise ValueError("not a code-length table")
    return build(L)


def table_lengths(d, at):
    """The lengths and the escape entries behind them."""
    L = []
    for k in range(128):
        b = d[at + k]
        L.append(b >> 4)
        L.append(b & 15)
    n = d[at + 128]
    esc = [d[at + 129 + i] for i in range(n)]
    for sym in esc:
        L[sym] += 16
    return L, esc


def table_stream_at(ds, at, nesc):
    """Where a Huffman block's stream starts, in bytes: past the table
    and its `nesc` escape entries, then a pad to an EVEN offset from
    the block's own start (`ds`). With no escape entries the sum — one
    flush byte, 128 of table, one count — is already even, which is why
    every block here starts exactly there."""
    p = at + 128 + 1 + nesc
    if (p - ds) & 1:
        p += 1
    return p


def decode_huff(d, t, bitstart, nout, hist=b""):
    """Shape 1's framing, with every byte of it Huffman-coded.

    The flag byte is a symbol like any other — which is why symbol 255
    carries the shortest code in a file of incompressible data: a flag
    of eight literals IS 0xff, and it occurs once per eight bytes.

    A match is two symbols: `length = (S & 7) + 2` and
    `distance = ((S >> 3) << 8) | D` — the same 13-bit reach shape 1
    has, because this IS shape 1's stream. A length of 2 — the low
    three bits zero — escapes to a third symbol carrying `length - 2`.
    """
    return decode_huff_at(d, t, Bits(d, bitstart), nout, hist)


def decode_huff_at(d, t, r, nout=None, hist=b"", endbit=None):
    """The same, carrying on from a bit reader already positioned."""
    out = bytearray()
    while (r.p < endbit) if endbit is not None else (len(out) < nout):
        flags = r.sym(t)
        for b in range(8):
            if endbit is not None:
                if r.p >= endbit and b:
                    break
            elif len(out) >= nout:
                break
            if flags & (0x80 >> b):
                out.append(r.sym(t))
            else:
                S = r.sym(t)
                D = r.sym(t)
                ln = (S & 7) + 2
                dist = ((S >> 3) << 8) | D
                if (S & 7) == 0:
                    ln = r.sym(t) + 2
                if dist == 0 or dist > len(hist) + len(out):
                    raise ValueError("distance %d" % dist)
                for _ in range(ln):
                    at = len(hist) + len(out) - dist
                    out.append(hist[at] if at < len(hist)
                               else out[at - len(hist)])
    return bytes(out[:nout] if nout is not None else out)


def decode_huffonly(d, at, nout=None, endbit=None):
    """Huffman and nothing else: the same 128-byte table, then one
    symbol per output byte — no flag bits and no matches.

    The stream starts **one byte** after the table in all three blocks
    that use it: the 1993 archive's middle block and two members of the
    `tokdist` case. That is not the gap a shape-2 block has, which is
    23 bits in one specimen and 18 in another and still unexplained.
    """
    t = table_at(d, at)
    _, esc = table_lengths(d, at)
    r = Bits(d, table_stream_at(at - 1, at, len(esc)) * 8)
    if endbit is None:
        return bytes(r.sym(t) for _ in range(nout))
    out = bytearray()
    while r.p < endbit:
        out.append(r.sym(t))
    return bytes(out[:nout] if nout is not None else out)


LZSS_PREFIX = (0x00, 0x03)      # what the encoder writes there
_warned = {}                    # anything else is reported once


def decode_shape2(d, at, nout=None, hist=b"", endbit=None):
    """A Huffman-over-LZSS block, from a position nothing searches for.

    The 128-byte table sits at `at`; **one zero byte** follows it, and
    then the LZSS stream — whose first two bytes are the constant
    `00 03` that opens a shape-1 block too, coded through the same
    table like every other byte. Reading those two as the stream's
    first flag byte and match is what made this look like a gap of "23
    bits in one specimen and 18 in another": the gap was the prefix,
    and the prefix is two symbols whose code lengths differ per block.

    They are skipped rather than checked, because a decoder does not
    need them and because `tools/synth_now.py` writes `00 00` there —
    its fixtures have exercised the engine for a year without anybody
    noticing that the encoder writes `00 03`, the engine skipping two
    bytes either way.
    """
    t = table_at(d, at)
    _, esc = table_lengths(d, at)
    r = Bits(d, table_stream_at(at - 1, at, len(esc)) * 8)
    got = (r.sym(t), r.sym(t))          # the prefix, skipped like shape 1's
    if got != LZSS_PREFIX and not _warned.get(got):
        _warned[got] = 1
        print("derive-now: an LZSS stream opens %s, not %s"
              % (got, LZSS_PREFIX), file=sys.stderr)
    return decode_huff_at(d, t, r, nout, hist, endbit)


def try_huff(d, want):
    """The stream begins a few bits after the table, and what sits
    between them is not understood — so it is searched for, within a
    byte or two, rather than claimed."""
    try:
        t = table_at(d)
    except (ValueError, IndexError):
        return None
    for bs in range((TABLE_AT + 128) * 8, (TABLE_AT + 128 + 6) * 8):
        try:
            if decode_huff(d, t, bs, len(want)) == want:
                return bs
        except Exception:
            continue
    return None


def kraft_tables(d, lo, hi):
    """Every offset in [lo, hi) where 128 bytes of nibbles are a
    complete prefix code. Kraft's equality is a strong enough filter
    that it finds the tables and almost nothing else."""
    out = []
    for at in range(max(0, lo), min(hi, len(d) - 128)):
        L = []
        for k in range(128):
            b = d[at + k]
            L.append(b >> 4)
            L.append(b & 15)
        if abs(sum(2.0 ** -x for x in L if x) - 1.0) < 1e-9:
            out.append(at)
    return out


BLOCK = 32768

# What a record's mode means, and how many bytes sit between the
# record's offset and the block's data.
# Four mode words are attested: 0x0000 stored, 0x0010 and 0x001f
# shape 1, 0x003f shape 2. The pair 0x0010/0x001f is the SAME payload
# written by Faster and by Smaller — the two files differ in that word
# and nowhere else — so the low bits are not the coder. **Bit 0x20 is
# the coder** on this evidence, and four data points is what that
# claim rests on.
STORED = 0x0000
LZSS_BITS = 0x1F        # the low bits say an LZSS layer is there
HUFFMAN_BIT = 0x20      # and this one a Huffman layer over it
ARCHIVE_BIT = 0x40      # while this is the coder an archive uses
IN_ARCHIVE = 0x100


def block_kind(mode):
    """The mode word is a set of layers, not a number.

    The low five bits say the block is LZSS-coded, `0x20` that a Huffman
    code sits over it, `0x40` that the block uses the archive coder, and
    `0x100` that it is inside an archive. So `0x20` ALONE is a Huffman
    code over the bytes with no LZSS at all — which is the shape the
    1993 archive's middle block uses and the one this reader could not
    place until 2026-09-21, because it was decoding it as `0x3f`.
    """
    if not mode & (LZSS_BITS | HUFFMAN_BIT | ARCHIVE_BIT):
        return "stored", 0
    if mode & ARCHIVE_BIT:
        return "shape3", 0
    if mode & HUFFMAN_BIT:
        return ("shape2" if mode & LZSS_BITS else "huffman"), 1
    return "shape1", 2


def records(d, limit=64):
    """The fork's block table: 8-byte records from offset 144 — a u16
    offset, a u16 mode, **a u16 padding count** and a u16 that is zero
    in every specimen. The list ends with a record whose offset is the
    fork's own size, which is how a reader knows it has them all.

    **The padding count is how many bytes sit between the end of a
    block's stream and its four-byte checksum**, and it is 1 on four of
    the harness's shape-1 blocks and 0 on the rest. Measured: the
    shape-1 decoder stops exactly `padding + 4` bytes before the next
    block's offset, on every one of them. This note recorded those four
    bytes as "zero in every specimen" until 2026-09-21, which they are
    not.

    Modes seen: 0x0000 stored, 0x0010 shape 1, 0x003f shape 2. A fork
    may mix them — `mixed.bin` is (170, stored) then (32942, shape 2)
    then the 33,430-byte sentinel.
    """
    out = []
    p = 144
    while p + 8 <= len(d) and len(out) < limit:
        off = int.from_bytes(d[p:p + 2], "big")
        mode = int.from_bytes(d[p + 2:p + 4], "big")
        pad = int.from_bytes(d[p + 4:p + 6], "big")
        out.append((off, mode, pad))
        p += 8
        if off == len(d):
            return out
    return None                     # no sentinel: not a bare fork


def read_fork(d, nout):
    """Decode a whole fork from its block table.

    Where a shape-2 block's stream begins is read, not searched: one
    byte after its table, and then the two symbols of the `00 03` every
    LZSS stream opens with, whose coded lengths are what made the gap
    look like "23 bits in one specimen and 18 in another".
    """
    recs = records(d)
    if not recs:
        return None
    out = bytearray()
    for (off, mode, pad), (nxt, _, _) in zip(recs, recs[1:]):
        if len(out) >= nout:
            break
        n = min(BLOCK, nout - len(out))
        kind, skip = block_kind(mode)
        at = off + skip
        if kind == "stored":
            out.extend(d[at:at + n])
        elif kind == "shape1":
            piece, _ = decode(d, at, n)
            out.extend(piece)
        elif kind == "huffman":
            out.extend(decode_huffonly(d, at, n))
        else:
            out.extend(decode_shape2(d, at, n, bytes(out)))
    return bytes(out[:nout])


def fork_checksums(d):
    """Every block of a bare fork, checked against its own trailer: the
    last four bytes of a block are the 32-bit sum of the bytes before
    them, in every shape (`shape3_check`). Returns (agreed, total)."""
    recs = records(d)
    if not recs:
        return 0, 0
    ok = tot = 0
    for (off, _, _), (nxt, _, _) in zip(recs, recs[1:]):
        if nxt <= off + 4:
            continue
        stored, calc = shape3_check(d, off, nxt)
        tot += 1
        ok += stored == calc
    return ok, tot


def read_blocks(d, want):
    """A fork is a sequence of BLOCKS, each coded its own way.

    Demonstrated rather than parsed: this walks the expected output and
    asks, of each block in turn, whether it was stored or coded with
    shape 2, searching a window for the block's table. A real decoder
    would read that from the block header instead — which is the part
    of this format still undescribed, and the reason this function is
    in a derivation tool and not in `src/`.
    """
    pos = 0          # bytes of output accounted for
    at = 0           # bytes of stream consumed
    plan = []
    while pos < len(want):
        n = min(BLOCK, len(want) - pos)
        here = d.find(want[pos:pos + n], at)
        if here >= 0 and here - at < 400:      # the block is stored
            plan.append(("stored", here, n))
            pos += n
            at = here + n
            continue
        hit = None
        for tb in kraft_tables(d, at, at + 400):
            for bs in range((tb + 128) * 8, (tb + 128 + 8) * 8):
                try:
                    out = decode_huff(d, table_at(d, tb), bs, n)
                except Exception:
                    continue
                if out == want[pos:pos + n]:
                    hit = (tb, bs)
                    break
            if hit:
                break
        if not hit:
            return None
        plan.append(("huffman", hit[0], n))
        pos += n
        at = (hit[1] // 8) + 1
    return plan


# ------------------------------------------------- the archive layer

# An archive is not a fork, and that is why the corpus's two real
# specimens read as nonsense for as long as they were treated as one.
# Its members' data areas carry the SAME header tail a bare fork has —
# first-block offset, then the block table — but at their own offsets,
# which the member records at the top of the file give.
MEMBER_AT = 24          # the first member record
MEMBER_LEN = 110        # and the stride between them


def members(d):
    """The archive's member records.

    The file header is 24 bytes: `0x0002`, the compression setting in a
    block mode word's own vocabulary, a u32 of 32,768 or 65,536,
    **the entry count as a u32 at +8**, and at +20 the sum of the
    bytes before it. The records follow at 24, **110 bytes each**, and
    this reads the fields it can name:

        +0    a Pascal name, 1 + up to 31 bytes
        +36   flags; **bit 0x10 marks a DIRECTORY**, found by comparing
              the two folder records of the `tree` archive against its
              five file records — the only bit that is set in both and
              clear in all five. The 1995 archive's folder has 0x14
              there, so the test is the bit and not the word
        +38   type, +42 creator (zero on a folder)
        +82   u16, the entries a folder holds: the table is a pre-order
              flattening, so that many records follow it
        +86   u32 data fork length
        +90   u32 resource fork length
        +98   u32 start of the member's data area, +102 its end
        +106  u32 **the sum of the record's first 106 bytes** — the same
              checksum idiom a block's trailer and a block table's end
              use, and it agrees on every record of every archive here,
              folders included

    Returns (name, data length, resource length, start, end) for the
    FILES: a directory record is skipped by its flag rather than by its
    bounds failing to parse, which is how this told them apart for the
    first half of 2026-09-21.
    """
    if len(d) < MEMBER_AT + MEMBER_LEN:
        return None
    n = int.from_bytes(d[8:12], "big")
    if not 1 <= n <= 0xFFFF:
        return None
    out = []
    for k in range(n):
        b = MEMBER_AT + MEMBER_LEN * k
        if b + MEMBER_LEN > len(d):
            return None
        r = d[b:b + MEMBER_LEN]
        if r[0] > 31:
            return None
        if int.from_bytes(r[106:110], "big") != (sum(r[:106]) & 0xFFFFFFFF):
            return None
        if int.from_bytes(r[36:38], "big") & 0x10:
            continue                            # a directory: no data area
        name = r[1:1 + r[0]].decode("mac-roman", "replace")
        dlen = int.from_bytes(r[86:90], "big")
        rlen = int.from_bytes(r[90:94], "big")
        st = int.from_bytes(r[98:102], "big")
        en = int.from_bytes(r[102:106], "big")
        if not 0 < st < en <= len(d):
            continue
        out.append((name, dlen, rlen, st, en))
    return out or None


def member_blocks(d, st, en):
    """One member's block table.

    A member's data area opens with **a u32 saying where its first block
    begins**, and that number is also where the table ENDS, so it says
    how many records there are:

        st + 0     u32, the first block's offset
        st + 4     n records of [u16 mode][u16 padding][u32 END offset],
                   n = (first - st - 4) / 8 - 1
        then       four bytes, then a u32 equal to the sum of every byte
                   of the data area before it
        first      the first block

    One place and one width, on **all 108 members here** — the two
    corpus archives, the sixteen bare forks and every archive the
    harness has made — with that checksum agreeing on every one. This
    reader read the same bytes as [offset][mode][padding] records at one
    of two places and one of two widths until 2026-09-21; the two
    readings pick out the same blocks, and this one needs no special
    case for the 1993 archive (whose leading record the other one
    dropped) or for the 1995 archive's 2.9 MB (which no u16 offset can
    reach). `0d4c`/`0037`, the two words that reading could not name,
    are the mode and padding of a LEADING record that produces no bytes.

    Returned in this tool's own vocabulary — (start, mode, padding) per
    block, ending with a sentinel whose start is the member's end —
    because a start is what the decoders here take.

    **A record whose end offset repeats the one before it** produces no
    bytes: it is the boundary between a member's two forks, which is
    what it is in the 1995 archive's `SynRef2.0 INFO`, and the record
    5.0.1 writes in front of every table. The engine calls it a stream
    restart and reloads its dictionary cache there (FORMATS.md, *Now
    Compress*).
    """
    if st + 8 > len(d):
        return None
    first = int.from_bytes(d[st:st + 4], "big")
    n = (first - st - 4) // 8 - 1
    if n < 0 or n > 4096 or st + 4 + 8 * n + 8 > len(d) or first > len(d):
        return None
    recs, last, p = [], first, st + 4
    for _ in range(n):
        mode = int.from_bytes(d[p:p + 2], "big")
        pad = int.from_bytes(d[p + 2:p + 4], "big")
        end = int.from_bytes(d[p + 4:p + 8], "big")
        recs.append((last, mode, pad))
        last = end
        p += 8
    if last != en:
        return None
    if int.from_bytes(d[p + 4:p + 8], "big") != (sum(d[st:p + 4]) & 0xFFFFFFFF):
        return None
    recs.append((last, 0, 0))
    return recs


# The coder lives in the mode word's bits, and the archive sets one the
# bare forks never do:
#   0x0000 / 0x0100  stored          0x0020  Huffman only
#   0x0010 / 0x001f  shape 1         0x003f  Huffman over shape 1
#                                    0x0040  shape 3, below


def archive_kind(mode):
    """The same layers, one bit wider: see `block_kind`."""
    return block_kind(mode)


# ------------------------------------------------------- shape 3

# Every shape-3 block in every specimen begins with 0x2f, and five
# bytes in sits a complete prefix code — which is what makes the rest
# of the header readable without knowing what bytes 1..4 mean.
SHAPE3_MAGIC = 0x2F
CLC_AT = 5              # 16 code lengths, four bits each
TABLE_AT_BIT = 128      # the main table, after 24 bits this reader
                        # cannot account for and that are zero in all
                        # eight specimens


def shape3_clc(b):
    """The code-length code: **twenty** four-bit lengths at byte 5, for
    the values 0..19 the two tables are written in — twenty because a
    distance entry is stored as its code length plus two, so 17 has to
    fit.

    Kraft's equality is the check and it is exact on every shape-3
    block seen. The last four are zero in all of them, which is why
    reading sixteen worked and left "24 bits this note cannot account
    for" behind it (docs/formats/now-compress.md, *The header*).
    """
    L = []
    for k in range(10):
        L.append(b[CLC_AT + k] >> 4)
        L.append(b[CLC_AT + k] & 15)
    if abs(sum(2.0 ** -x for x in L if x) - 1.0) > 1e-12:
        raise ValueError("code-length code is not complete")
    return build(L)


SHAPE3_SYMS = 290       # 256 literals, an unused 256, 33 lengths
SHAPE3_DISTS = 56       # and this many distance classes


def shape3_table(b):
    """The main table: **290 code lengths**, one per symbol, each written
    in the code-length code — zeros and all.

    Reading it as "until the code is complete" is what the 2026-09-21
    note said, and it is wrong: the code often completes before the end
    and the remaining symbols are written as zeros, so a reader that
    stops early starts the NEXT table at the wrong bit. Four of the
    harness's blocks looked like they had a 271- or 274-symbol alphabet
    for exactly that reason.

    Symbols 0..255 are the literals; 257..289 are the match lengths
    (`shape3_len`), and 256 is used by nothing here.
    """
    t = shape3_clc(b)
    r = Bits(b, TABLE_AT_BIT)
    lens = [r.sym(t) for _ in range(SHAPE3_SYMS)]
    kraft = sum(2.0 ** -v for v in lens if v)
    used = sum(1 for v in lens if v)
    if abs(kraft - 1.0) > 1e-9 and used != 1:
        # one symbol is written with a length of 1 and so sums to 0.5:
        # `runa.bin` codes one match symbol and no literal at all
        raise ValueError("main table is not a complete code")
    return lens, r.p


def shape3_len(sym):
    """A match symbol -> (the class's shortest length, extra bits).

    257..271 ARE the lengths 3..17; then the classes widen — two of 2,
    five of 4, three of 8, four of 16, four of 32 — and 289 spans
    226..257, so **257 bytes is the longest match this format has**.

    Measured, not guessed: `nowcompress.py --case toklen` plants a match
    of a chosen length in each member and the token is read against it,
    and three files' block arithmetic agrees (docs/formats/now-compress.md).
    """
    if not 257 <= sym <= 289:
        return None, None
    table, ln = [], 3
    for extra, count in ((0, 15), (1, 2), (2, 5), (3, 3), (4, 4), (5, 4)):
        for _ in range(count):
            table.append((ln, extra))
            ln += 1 << extra
    return table[sym - 257]


def shape3_dist(idx):
    """A distance symbol -> (the class's shortest distance, extra bits).

    1..7 ARE the distances 1..7; 8..27 go four to an octave; 28..35 are
    eight classes of 256; above that the width doubles every four. The
    last class, 55, starts at 57,600 and spans 8,192 — which is where
    the 65,791 this project measured off its own engine's table in
    DECISIONS.md 2026-09-21 comes from, reached here from the other side.

    Measured the same way: `--case tokdist` plants a match at a chosen
    distance, 40 of them from 2 to 16,384.
    """
    if idx <= 7:
        return idx, 0
    if idx <= 27:
        extra = idx // 4 - 1
        return (4 + idx % 4) << extra, extra
    if idx <= 35:
        return 256 + (idx - 28) * 256, 8
    extra, base, j = 9 + (idx - 36) // 4, 2304, 36
    while j + 4 <= idx:
        base += 4 << (9 + (j - 36) // 4)
        j += 4
    return base + ((idx - j) << (9 + (j - 36) // 4)), extra


def shape3_tables(d, off):
    """Both code tables of a shape-3 block, and where its stream starts.

    The distance table follows the main one in the same code-length
    code, 56 entries, zeros for the classes the block does not use and
    all. **Where the stream starts the HEADER says, twice over**: byte
    1 of the block is the stream's byte offset plus 85, and the bits of
    flush between the tables and the stream are `(16 - byte 4) mod 16`
    — nought when that byte is nought, which is 20 blocks of the 1995
    archive and none of the 75 the rule was derived from. Both accounts
    agree on all 381 blocks read here, which is what says either is
    right (docs/formats/now-compress.md, *The header*).
    """
    clc = shape3_clc(d[off:])
    r = Bits(d, off * 8 + TABLE_AT_BIT)
    t1 = [r.sym(clc) for _ in range(SHAPE3_SYMS)]
    t2 = [v if v == 0 else v - 2         # stored as the code length PLUS TWO
          for v in (r.sym(clc) for _ in range(SHAPE3_DISTS))]
    end = r.p - off * 8
    start = end + ((16 - d[off + 4]) & 15)   # byte 4: bits of flush, mod 16
    if start != (d[off + 1] - 85) * 8:       # byte 1: the same as a byte offset
        raise ValueError("the header's two accounts of the stream differ")
    return t1, t2, start


def shape3_stream(bits, start, t1, t2, hist, nout=None, endbit=None):
    """The stream itself: a literal symbol, or a match — its length
    symbol, that length's extra bits, a distance symbol and that
    distance's extra bits.

    `hist` is everything the archive has produced already: the window
    spans members, which is why a match may point back past this
    member's own beginning.
    """
    out = bytearray()
    p = start
    while (p < endbit) if endbit is not None else (len(out) < nout):
        if nout is not None and len(out) >= nout and endbit is None:
            break
        s, p = bit_sym(bits, p, t1)
        if s < 256:
            out.append(s)
            continue
        base, extra = shape3_len(s)
        if base is None:
            raise ValueError("symbol %d is not a match" % s)
        ln = base + (int(bits[p:p + extra], 2) if extra else 0)
        p += extra
        idx, p = bit_sym(bits, p, t2)
        dbase, dextra = shape3_dist(idx)
        dist = dbase + (int(bits[p:p + dextra], 2) if dextra else 0)
        p += dextra
        for _ in range(ln):
            if nout is not None and len(out) >= nout:
                break
            at = len(hist) + len(out) - dist
            if at < 0:
                raise ValueError("distance %d reaches past the start" % dist)
            out.append(hist[at] if at < len(hist) else out[at - len(hist)])
    return bytes(out), p


def bit_sym(bits, p, table):
    """One symbol out of a string of '0'/'1', most significant bit first."""
    c = 0
    for length in range(1, 17):
        if p + length > len(bits):
            raise EOFError
        c = (c << 1) | (1 if bits[p + length - 1] == "1" else 0)
        if (length, c) in table:
            return table[(length, c)], p + length
    raise ValueError("no code at bit %d" % p)


def shape3_decode(d, off, end, hist, nout=None, want=None, padding=0):
    """Decode one shape-3 block. **Nothing outside the block is needed:
    how much it produces is a result, not an input** — the stream runs
    from where the header says to where byte 3 says, and `nout` only
    caps the output for a caller that knows a fork ends inside it.

    Nothing here is searched for, and the
    header's own account of where the stream ENDS is checked against
    where it did: after the last token come `(16 - byte 3) mod 16` bits
    of flush and then the four-byte trailer, on all 381 blocks read
    here."""
    bits = "".join(str((d[off + (i >> 3)] >> (7 - (i & 7))) & 1)
                   for i in range((end - off) * 8))
    t1lens, t2lens, start = shape3_tables(d, off)
    endbit = ((end - off) * 8 - 8 * padding - 32
              - ((16 - d[off + 3]) & 15))
    out, last = shape3_stream(bits, start, build(t1lens), build(t2lens),
                              hist, nout, endbit)
    if last != endbit:
        raise ValueError("the stream does not end where byte 3 says")
    return (out[:nout] if nout is not None else out), start


def shape3_check(d, off, end):
    """The block's last four bytes are a **32-bit sum of every byte
    before them in the block** — the trailer the note had down as
    "presumably a checksum", and it is one. Returns (stored, computed).
    """
    stored = int.from_bytes(d[end - 4:end], "big")
    return stored, sum(d[off:end - 4]) & 0xFFFFFFFF


def read_archive(d, want=None):
    """Walk an archive and report what each member's blocks are.

    `want` maps a member name to the bytes that went in, when they are
    known; a block is then decoded and compared. **The member record's
    own fork lengths say how long each fork is**, so how much a block
    has to produce is read rather than assumed even when nothing is
    expected. The stream is the RESOURCE fork first, which those two
    lengths and the fork-boundary record together make checkable.
    Returns a list of (member, size, [(kind, offset, mode, read, end)]).
    """
    ms = members(d)
    if not ms:
        return None
    out = []
    hist = bytearray()          # the window spans members, so this does too
    for name, dlen, rlen, st, en in ms:
        recs = member_blocks(d, st, en)
        if not recs:
            out.append((name, dlen, None))
            continue
        blocks = []
        pos = 0
        forks = (want or {}).get(name)
        if isinstance(forks, (bytes, bytearray)):
            forks = [forks]
        sizes = [n for n in (rlen, dlen) if n] or [0]
        fork = 0
        w = forks[0] if forks else None
        for (off, mode, pad), (nxt, _, _) in zip(recs, recs[1:]):
            if nxt == off:
                # A record that produces no bytes says the next block
                # STARTS a stream. Where bytes have already come out of
                # this member it is the boundary between its two forks
                # (the 1995 archive's `SynRef2.0 INFO`); in front of a
                # table it is what 5.0.1 writes before every one, and
                # there is no fork to close.
                if pos:
                    fork += 1
                    pos = 0
                    w = forks[fork] if forks and fork < len(forks) else None
                continue
            kind, skip = archive_kind(mode)
            left = (len(w) - pos) if w is not None else (
                sizes[fork] - pos if fork < len(sizes) else 0)
            # A block says how much it produces: its stream runs to the
            # bit its header names, and a stored one holds its own
            # bytes. `left` only caps the last block of a fork.
            n = min(BLOCK, left)
            if kind == "stored":
                n = min(n, nxt - off - 4 - pad)
            read = None
            if n > 0:
                try:
                    if kind == "stored":
                        got = d[off:off + n]
                    elif kind == "shape1":
                        got = decode(d, off + skip, n, bytes(hist),
                                     nxt - 4 - pad)[0]
                    elif kind == "huffman":
                        got = decode_huffonly(
                            d, off + skip, n,
                            (nxt - pad) * 8 - 32 - ((16 - d[off]) & 15))
                    elif kind == "shape2":
                        got = decode_shape2(
                            d, off + skip, n, bytes(hist),
                            (nxt - pad) * 8 - 32 - ((16 - d[off]) & 15))
                    else:
                        got, _ = shape3_decode(d, off, nxt, bytes(hist), n,
                                               padding=pad)
                    # graded where something is expected; where nothing
                    # is, a decode that runs to the end its header names
                    # is still worth reporting
                    read = (got == w[pos:pos + n]) if w is not None else "decoded"
                    if w is None:
                        hist += got
                        n = len(got)        # the block said how much
                except Exception:
                    read = False
            blocks.append((kind, off, mode, read, nxt))
            if w is not None and n > 0:
                hist += w[pos:pos + n]
            pos += n
        out.append((name, dlen, blocks))
    return out


def decode_huff_safe(d, t, bs, n, hist=b""):
    try:
        return decode_huff(d, t, bs, n, hist)
    except Exception:
        return None


def report_archive(path, d, want):
    ms = read_archive(d, want)
    print(f"    {os.path.basename(path)}: ", end="")
    if ms is None:
        print("not an archive this reader knows")
        return 0, 0
    print(f"{len(ms)} member(s)")
    ok = tot = 0
    for name, usize, blocks in ms:
        if blocks is None:
            print(f"      {name:12s} {usize:7d} B  no block table")
            continue
        parts = []
        for kind, off, mode, read, nxt in blocks:
            tot += 1
            if read is True or read == "decoded":
                ok += 1
            mark = {True: "ok", False: "--", None: "?",
                    "decoded": "(decodes)"}[read]
            parts.append(f"{kind}@{off} ({mode:#06x}) {mark}")
        print(f"      {name:12s} {usize:7d} B  " + ", ".join(parts))
        for kind, off, mode, read, nxt in blocks:
            if kind != "shape3":
                continue
            try:
                t1, t2, stream = shape3_tables(d, off)
            except Exception as e:
                print(f"        shape 3 @{off}: {e}")
                continue
            nlit = sum(1 for v in t1[:256] if v)
            ndist = sum(1 for v in t2 if v)
            stored, calc = shape3_check(d, off, nxt)
            print(f"        shape 3 @{off}: {nlit} literals and "
                  f"{sum(1 for v in t1[256:] if v)} match symbols coded, "
                  f"{ndist} distance classes, stream from bit {stream}, "
                  f"checksum {'ok' if stored == calc else 'WRONG'}")
    return ok, tot


def archives(paths, expect=None):
    """The archive pass: the harness's own `.sea` files, and any given
    on the command line.

    `expect` is a directory of extracted forks — what `macextract x`
    writes — so a corpus archive, which has no `in-` files beside it,
    can be graded too: a member's stream is its RESOURCE fork followed
    by its data fork.
    """
    ok = tot = 0
    for path in paths:
        d = open(path, "rb").read()
        want = {}
        folder = os.path.dirname(path)
        for f in os.listdir(folder) if os.path.isdir(folder) else []:
            if f.startswith("in-"):
                want[f[3:]] = [open(os.path.join(folder, f), "rb").read()]
        for root, _, files in os.walk(expect) if expect else []:
            for f in files:
                if f.endswith(".rsrc"):
                    continue
                data = open(os.path.join(root, f), "rb").read()
                rsrc = os.path.join(root, f + ".rsrc")
                want[f] = ([open(rsrc, "rb").read()] if os.path.exists(rsrc)
                           else []) + [data]
        a, t = report_archive(path, d, want)
        ok += a
        tot += t
    return ok, tot


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archives", nargs="*", help="a .sea or .now to walk")
    ap.add_argument("--expect", metavar="DIR",
                    help="a directory of extracted forks to grade against")
    args = ap.parse_args()
    if args.archives:
        print("derive-now: archives")
        ok, tot = archives(args.archives, args.expect)
        how = ("read and graded against DIR" if args.expect else
               "decoded; --expect DIR grades them against extracted forks")
        print(f"derive-now: {ok} of {tot} member block(s) {how}")
        return 0
    if not os.path.isdir(SPECIMENS):
        print("derive-now: no specimens — tools/vmac/nowcompress.py --case all "
              "makes them (skipped)")
        return 0
    ok = huff = stored = blocks = other = 0
    for mode in sorted(os.listdir(SPECIMENS)):
        mdir = os.path.join(SPECIMENS, mode)
        if not os.path.isdir(mdir):
            continue
        for f in sorted(os.listdir(mdir)):
            if not f.endswith(".dat"):
                continue
            base = f[:-4]
            inp = os.path.join(mdir, "in-" + base)
            if not os.path.exists(inp):
                continue
            d = open(os.path.join(mdir, f), "rb").read()
            want = open(inp, "rb").read()
            try:
                out, end = decode(d, PAYLOAD_AT, len(want))
            except Exception:
                out, end = None, None
            table_read = read_fork(d, len(want))
            if table_read == want:
                cok, ctot = fork_checksums(d)
                print(f"ok  {mode:8s} {base:10s} {len(want):6d} B from "
                      f"{len(d):6d}  block table: "
                      + ", ".join(f"{hex(o)}/{hex(m)}"
                                  for o, m, _ in records(d))
                      + f"; {cok}/{ctot} checksum(s)")
                ok += 1
                continue
            if out == want:
                print(f"ok  {mode:8s} {base:10s} {len(want):6d} B from "
                      f"{len(d):6d}  payload {PAYLOAD_AT}..{end}, "
                      f"trailer {d[end:].hex(' ')}")
                ok += 1
            elif len(want) > BLOCK and (plan := read_blocks(d, want)):
                shapes = ", ".join(f"{k} {n} B" for k, _, n in plan)
                print(f"ok  {mode:8s} {base:10s} {len(want):6d} B from "
                      f"{len(d):6d}  {len(plan)} blocks: {shapes}")
                blocks += 1
            elif (hb := try_huff(d, want)) is not None:
                print(f"ok  {mode:8s} {base:10s} {len(want):6d} B from "
                      f"{len(d):6d}  shape 2, table {TABLE_AT}, stream bit {hb}")
                huff += 1
            elif d == want:
                # `archive` mode stores the member and compresses the
                # .sea around it: the fork IS the file, byte for byte.
                print(f"ok  {mode:8s} {base:10s} {len(want):6d} B from "
                      f"{len(d):6d}  stored, not compressed at all")
                stored += 1
            else:
                print(f"--  {mode:8s} {base:10s} {len(want):6d} B from "
                      f"{len(d):6d}  another shape")
                other += 1
    print(f"derive-now: {ok} specimen(s) read from their block table, "
          f"{huff} by shape 2 alone, {blocks} by several blocks, "
          f"{stored} stored, {other} not read")
    seas = []
    for mode in sorted(os.listdir(SPECIMENS)):
        mdir = os.path.join(SPECIMENS, mode)
        if not os.path.isdir(mdir):
            continue
        for f in sorted(os.listdir(mdir)):
            if f.endswith(".sea.dat"):
                seas.append(os.path.join(mdir, f))
    if seas:
        print("derive-now: archives")
        a, t = archives(seas)
        print(f"derive-now: {a} of {t} member block(s) read")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

**All four coders, the block structure and the archive container.**
Every compressed specimen the harness has made reads byte for byte — 76
blocks of 76 — and so does every block of both corpus archives: the
1993 `Expand Now` self-extractor, 3 of 3, and the 1995
`SyntheticReferences2.0`, 306 of 306, whose 9.9 MB fork alone is 304
blocks of the coder an archive uses — the one that was read no further
than its code table until 2026-09-21.

What is still searched for rather than read is where a block's bit
stream begins; it is on a byte boundary a byte or two past the tables,
and `shape3_tables` says what is known about which
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


def decode(d, p, nout, hist=b""):
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
    while len(out) < nout:
        if p >= len(d):
            raise EOFError
        flags = d[p]
        p += 1
        for bit in range(8):
            if len(out) >= nout:
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
    return bytes(out[:nout]), p


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
    """256 code lengths, four bits each, high nibble first. Kraft's
    equality is what says it is one."""
    L = []
    for k in range(128):
        b = d[at + k]
        L.append(b >> 4)
        L.append(b & 15)
    if abs(sum(2.0 ** -x for x in L if x) - 1.0) > 1e-9:
        raise ValueError("not a code-length table")
    return build(L)


def decode_huff(d, t, bitstart, nout, hist=b""):
    """Shape 1's framing, with every byte of it Huffman-coded.

    The flag byte is a symbol like any other — which is why symbol 255
    carries the shortest code in a file of incompressible data: a flag
    of eight literals IS 0xff, and it occurs once per eight bytes.

    A match is two symbols: `length = (S & 7) + 2` and
    `distance = ((S >> 3) << 8) | D`, so the reach is 11 bits where
    shape 1 had 8. A length of 2 — the low three bits zero — escapes
    to a third symbol carrying `length - 2`.
    """
    return decode_huff_at(d, t, Bits(d, bitstart), nout, hist)


def decode_huff_at(d, t, r, nout, hist=b""):
    """The same, carrying on from a bit reader already positioned."""
    out = bytearray()
    while len(out) < nout:
        flags = r.sym(t)
        for b in range(8):
            if len(out) >= nout:
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
    return bytes(out[:nout])


def decode_huffonly(d, at, nout):
    """Huffman and nothing else: the same 128-byte table, then one
    symbol per output byte — no flag bits and no matches.

    The stream starts **one byte** after the table in all three blocks
    that use it: the 1993 archive's middle block and two members of the
    `tokdist` case. That is not the gap a shape-2 block has, which is
    23 bits in one specimen and 18 in another and still unexplained.
    """
    t = table_at(d, at)
    r = Bits(d, (at + 128 + 1) * 8)
    return bytes(r.sym(t) for _ in range(nout))


LZSS_PREFIX = (0x00, 0x03)      # every LZSS stream starts with these


def decode_shape2(d, at, nout, hist=b""):
    """A Huffman-over-LZSS block, from a position nothing searches for.

    The 128-byte table sits at `at`; **one zero byte** follows it, and
    then the LZSS stream — whose first two bytes are the constant
    `00 03` that opens a shape-1 block too, coded through the same
    table like every other byte. Reading those two as the stream's
    first flag byte and match is what made this look like a gap of "23
    bits in one specimen and 18 in another": the gap was the prefix,
    and the prefix is two symbols whose code lengths differ per block.
    """
    t = table_at(d, at)
    r = Bits(d, (at + 128 + 1) * 8)
    got = (r.sym(t), r.sym(t))
    if got != LZSS_PREFIX:
        raise ValueError("the stream does not open with %s" % (LZSS_PREFIX,))
    return decode_huff_at(d, t, r, nout, hist)


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
        out.append((off, mode))
        p += 8
        if off == len(d):
            return out
    return None                     # no sentinel: not a bare fork


def read_fork(d, nout):
    """Decode a whole fork from its block table.

    The one thing still searched is where a shape-2 block's BIT stream
    begins: 23 bits after its table in one specimen and 18 in another,
    so something variable sits between them that this note has not
    identified. A Huffman-ONLY block (`0x20`) has no such trouble: its
    stream starts one byte after the table.
    """
    recs = records(d)
    if not recs:
        return None
    out = bytearray()
    for (off, mode), (nxt, _) in zip(recs, recs[1:]):
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
    for (off, _), (nxt, _) in zip(recs, recs[1:]):
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

    Word 5 of the file header is the member count; the records follow
    at 24, **110 bytes each**, and this reads the fields it can name:

        +0    a Pascal name, 1 + up to 31 bytes
        +38   type, +42 creator
        +80   the entries inside a FOLDER (2 in the 1995 archive's one,
              0 in every file record of a 5.0.1 archive; the 1993 one
              has 0x20000 there, so this field is not read the same way
              across versions)
        +86   u32 data fork length
        +90   u32 resource fork length
        +98   u32 start of the member's data area, +102 its end
        +106  u32 **the sum of the record's first 106 bytes** — the same
              checksum idiom a block's trailer and a block table's end
              use, and it agrees on every record of every archive here,
              folders included

    Returns (name, data length, resource length, start, end). A record
    whose bounds do not parse is a folder — the 1995 archive opens with
    one — and is skipped rather than taken as the end of the archive,
    which is what this did until 2026-09-21.
    """
    if len(d) < MEMBER_AT + MEMBER_LEN:
        return None
    n = int.from_bytes(d[10:12], "big")
    if not 1 <= n <= 512:
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
    """One member's block table: eight-byte records — an offset, a u16
    mode and a u16 padding count (`records`) — ending on the record
    whose offset is the member's end.

    **It sits at one of two places, and the header says which.** The
    member's data area opens with the first block's offset at `st + 2`,
    and the table's first record must repeat it. In everything Now
    Compress 5.0.1 wrote the table is at `st + 10`, with two words this
    reader cannot name (`0d4c`, `0037`) between; in the corpus's 1993
    `derived-Expand_Now_1.0.1.sea` those two words are absent and the
    table starts at `st + 2`. Reading the later layout into the older
    file loses the FIRST block, which is how that archive came to look
    like two blocks for a fork that needs three — and its three add up
    to 88,942 bytes exactly.

    **And an archive over 64 KB widens the record**: the 1995
    `derived-SyntheticReferences2.0.sea` addresses 2.9 MB, which a u16
    offset cannot reach, so its records are a u32 offset, a u16 mode
    and a u16 padding count — the same eight bytes with the offset
    taking the zero half. Both widths are tried and the terminator — a
    record whose offset is the member's end — is what says which is
    right.

    **A record whose offset repeats the one before it** produces no
    bytes. This reader treats it as the boundary between a member's two
    forks, which is what it is in the 1995 archive's `SynRef2.0 INFO`;
    the engine calls the same record a stream restart and reloads its
    dictionary cache there (FORMATS.md, *Now Compress*). Both accounts
    are of one record, and the archive has two of them — that one, and
    the repeat that opens the big member's table by restating the
    first-block offset its header already gave.
    """
    first16 = int.from_bytes(d[st + 2:st + 4], "big")
    for width, at in ((2, st + 10), (2, st + 2), (4, st + 8), (4, st)):
        recs = []
        p = at
        while p + 8 <= len(d) and len(recs) < 2048:
            off = int.from_bytes(d[p:p + width], "big")
            mode = int.from_bytes(d[p + width:p + width + 2], "big")
            recs.append((off, mode))
            p += 8
            if off == en:
                break
        else:
            continue
        if not recs or recs[-1][0] != en:
            continue
        if width == 2 and recs[0][0] != first16:
            continue
        if width == 4 and recs[0][0] != int.from_bytes(d[at:at + 4], "big"):
            continue
        return recs
    return None


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
    """The code-length code: sixteen four-bit lengths at byte 5, for
    the sixteen lengths 0..15 the main table is written in.

    Kraft's equality is the check, and it is exact on all eight
    shape-3 blocks known — four made to order, two in the harness's own
    archive and two in a 1993 one.
    """
    L = []
    for k in range(8):
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


def shape3_stream(bits, start, t1, t2, hist, nout):
    """The stream itself: a literal symbol, or a match — its length
    symbol, that length's extra bits, a distance symbol and that
    distance's extra bits.

    `hist` is everything the archive has produced already: the window
    spans members, which is why a match may point back past this
    member's own beginning.
    """
    out = bytearray()
    p = start
    while len(out) < nout:
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
            if len(out) >= nout:
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


def shape3_decode(d, off, end, hist, nout, want=None, padding=0):
    """Decode one shape-3 block. Nothing here is searched for, and the
    header's own account of where the stream ENDS is checked against
    where it did: after the last token come `(16 - byte 3) mod 16` bits
    of flush and then the four-byte trailer, on all 381 blocks read
    here."""
    bits = "".join(str((d[off + (i >> 3)] >> (7 - (i & 7))) & 1)
                   for i in range((end - off) * 8))
    t1lens, t2lens, start = shape3_tables(d, off)
    out, last = shape3_stream(bits, start, build(t1lens), build(t2lens),
                              hist, nout)
    tail = (end - off) * 8 - last - 8 * padding
    if tail != 32 + ((16 - d[off + 3]) & 15):
        raise ValueError("the stream does not end where byte 3 says")
    return out, start


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
        for (off, mode), (nxt, _) in zip(recs, recs[1:]):
            if nxt == off:
                # a record repeated is a fork boundary: no bytes of its
                # own, the next block starts the member's other fork
                fork += 1
                pos = 0
                w = forks[fork] if forks and fork < len(forks) else None
                continue
            kind, skip = archive_kind(mode)
            left = (len(w) - pos) if w is not None else (
                sizes[fork] - pos if fork < len(sizes) else 0)
            n = min(BLOCK, left)
            read = None
            if n > 0:
                try:
                    if kind == "stored":
                        got = d[off:off + n]
                    elif kind == "shape1":
                        got = decode(d, off + skip, n, bytes(hist))[0]
                    elif kind == "huffman":
                        got = decode_huffonly(d, off + skip, n)
                    elif kind == "shape2":
                        got = decode_shape2(d, off + skip, n, bytes(hist))
                    else:
                        got, _ = shape3_decode(d, off, nxt, bytes(hist), n)
                    # graded where something is expected; where nothing
                    # is, a decode that runs to the fork length the
                    # record states is still worth reporting
                    read = (got == w[pos:pos + n]) if w is not None else "decoded"
                    if w is None:
                        hist += got
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
                      + ", ".join(f"{hex(o)}/{hex(m)}" for o, m in records(d))
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

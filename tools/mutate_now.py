#!/usr/bin/env python3
"""mutate_now.py — change one field of a Now Compress file and fix the
checksums that field sits under.

**What it is for.** Three fields of this format are written by the
encoder and read by nothing here: a shape-3 block header's byte 2, the
two bytes `00 03` that open an LZSS stream, and the byte between a
Huffman table and its stream (docs/formats/now-compress.md, *What this
note does NOT describe*). "Nothing here reads it" is a claim about this
reader. The only way to make it a claim about the FORMAT is to change
the field and hand the file back to the program that wrote it:
`tools/vmac/nowcompress.py --expand` runs Now Compress's own Decompress
over a compressed file, and `--adjudicate` runs a self-extracting
archive's own decoder over an archive.

So each mutation here is chosen to be one a correct reader cannot
notice — every checksum the format has is recomputed — and the question
put to the Macintosh is whether the bytes that come out are still the
bytes that went in.

    tools/mutate_now.py --byte2 0x5a   IN.dat OUT.dat
    tools/mutate_now.py --prefix 5aa5  IN.dat OUT.dat
    tools/mutate_now.py --count 1      IN.dat OUT.dat
    tools/mutate_now.py --delta 4096   IN.dat OUT.dat
    tools/mutate_now.py --splice OUT.dat IN.bin OUT.bin   (MacBinary)

**The block table is a ladder rather than one question.** `--delta`
moves every offset the table stores; `--first-only`, `--records-only`
and `--record K` move one subset of them, and a negative delta moves
them the other way. Each reading of how the format's own decoder
anchors that table — correct everything by one constant, ignore the
stored first-block offset, ignore the offsets altogether — predicts a
different row of that ladder to survive, which is what makes it worth
running rather than arguing (docs/formats/now-compress.md, *The archive
layer*).

Every mutation prints what it changed, and `--check` decodes the result
with `tools/derive_now.py` to show that OUR reader still gets the
original bytes out — which is what says the file is well formed and the
question is a fair one.
"""
import argparse
import os
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import derive_now as D                                    # noqa: E402


# ------------------------------------------------------------------
# Walking any Now Compress file: an archive, or a compressed fork —
# which is an archive of ONE entry (docs/formats/now-compress.md).
# ------------------------------------------------------------------

def blocks(d):
    """Yield (member, start, end, mode, padding) for every block."""
    ms = D.members(d)
    if not ms:
        raise SystemExit("mutate-now: not a Now Compress file")
    for name, dlen, rlen, st, en in ms:
        recs = D.member_blocks(d, st, en)
        if not recs:
            continue
        for (off, mode, pad), (nxt, _, _) in zip(recs, recs[1:]):
            if nxt == off:
                continue                    # a fork boundary: no bytes
            yield name, off, nxt, mode, pad


def fix_trailer(d, off, end):
    """A block's last four bytes are the 32-bit sum of every byte before
    them in the block. Recompute it."""
    d[end - 4:end] = struct.pack(">I", sum(d[off:end - 4]) & 0xFFFFFFFF)


# ------------------------------------------------------------------
# The mutations
# ------------------------------------------------------------------

def mutate_byte2(d, value):
    """Byte 2 of every shape-3 block header, the one byte of its five
    that nothing here or in `src/fmt_now.c` reads."""
    n = 0
    for name, off, end, mode, pad in list(blocks(d)):
        if D.archive_kind(mode)[0] != "shape3":
            continue
        if d[off + 2] == value:
            value ^= 0xFF                   # always actually change it
        d[off + 2] = value
        fix_trailer(d, off, end)
        n += 1
    return n, "byte 2 := %#04x" % value


def mutate_prefix(d, two):
    """The two bytes every LZSS stream opens with.

    In a shape-1 block they are the block's first two bytes and are
    written over directly. In a shape-2 block they are the first two
    SYMBOLS of the Huffman stream, so they are replaced by two symbols
    of the same code length, which leaves every bit after them where it
    was.
    """
    n, how = 0, []
    for name, off, end, mode, pad in list(blocks(d)):
        kind, skip = D.archive_kind(mode)
        if kind == "shape1":
            d[off:off + 2] = two
            fix_trailer(d, off, end)
            n += 1
            how.append("shape1@%d" % off)
        elif kind == "shape2":
            at = off + skip
            lens, esc = D.table_lengths(d, at)
            t = D.build(lens)
            start = D.table_stream_at(at - 1, at, len(esc)) * 8
            r = D.Bits(d, start)
            p0 = r.p
            s0 = r.sym(t)
            p1 = r.p
            s1 = r.sym(t)
            p2 = r.p
            # a symbol of the same code length, so nothing after moves
            code = {v: k for k, v in t.items()}
            rep = []
            for sym, bitlen in ((s0, p1 - p0), (s1, p2 - p1)):
                alt = [s for s in range(256)
                       if lens[s] == bitlen and s != sym]
                if not alt:
                    break
                rep.append(alt[0])
            if len(rep) != 2:
                continue
            for sym, at_bit in zip(rep, (p0, p1)):
                length, c = code[sym]
                for i in range(length):
                    bit = (c >> (length - 1 - i)) & 1
                    k = at_bit + i
                    if bit:
                        d[k >> 3] |= 0x80 >> (k & 7)
                    else:
                        d[k >> 3] &= ~(0x80 >> (k & 7)) & 0xFF
            fix_trailer(d, off, end)
            n += 1
            how.append("shape2@%d (%d,%d -> %d,%d)"
                       % (off, s0, s1, rep[0], rep[1]))
    return n, "LZSS prefix := %s: %s" % (two.hex(), ", ".join(how))


def mutate_count(d, value):
    """The byte between a Huffman table and its stream, which
    `src/fmt_now.c` reads as the count of "extra length" entries."""
    n = 0
    for name, off, end, mode, pad in list(blocks(d)):
        kind, skip = D.archive_kind(mode)
        if kind not in ("shape2", "huffman"):
            continue
        d[off + skip + 128] = value
        fix_trailer(d, off, end)
        n += 1
    return n, "the count byte := %d" % value


def deep_code(data, depth):
    """A COMPLETE prefix code over the symbols in `data` whose deepest
    code is exactly `depth`.

    A legal code need not be an optimal one, and Now Compress's own
    coder will not produce a deep one — every shape puts an LZ layer
    under the Huffman one and it eats the skew (docs/formats/
    now-compress.md, *A code length past 15*). So the code is built
    rather than fitted: a chain of lengths 1, 2, ... depth, depth, which
    satisfies Kraft's equality exactly, and then the shallowest leaf is
    split in two as many times as there are symbols left to place. The
    rarest symbols take the deepest codes, so the stream grows as little
    as this can manage.
    """
    freq = Counter(data)
    order = [s for s, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))]
    if len(order) < depth + 1:
        raise SystemExit("mutate-now: %d symbols cannot carry a code %d deep"
                         % (len(order), depth))
    lens = list(range(1, depth + 1)) + [depth]      # the chain
    for _ in range(len(order) - len(lens)):
        lens.sort()
        shallow = lens.pop(0)                       # split it in two
        lens += [shallow + 1, shallow + 1]
    lens.sort()
    assert abs(sum(2.0 ** -x for x in lens) - 1.0) < 1e-12
    return {sym: ln for sym, ln in zip(order, lens)}


def mutate_recode(d, maxlen):
    """Re-code a one-block file's Huffman region with a code at most
    `maxlen` deep, and lay the file back out around it.

    **This is how a specimen for the escape past 15 gets made.** Now
    Compress will not write a code deeper than 15 (eight attempts,
    docs/formats/now-compress.md) and a whole file written here from
    scratch it calls damaged, shallow code and all — so the only way to
    hand it a deep code is to take a file it wrote and change nothing
    but the code. At `maxlen` 15 that is a CONTROL: the same file, the
    same machinery, a code it can already read.
    """
    import synth_now as S                              # noqa: E402
    ms = D.members(d)
    if not ms or len(ms) != 1:
        raise SystemExit("mutate-now: --recode wants a one-entry file")
    name, dlen, rlen, st, en = ms[0]
    recs = D.member_blocks(d, st, en)
    real = [(o, m, p) for (o, m, p), (nxt, _, _) in zip(recs, recs[1:])
            if nxt != o]
    if len(real) != 1:
        raise SystemExit("mutate-now: --recode wants a one-BLOCK file")
    off, mode, pad = real[0]
    kind, skip = D.archive_kind(mode)
    if kind not in ("shape2", "huffman"):
        raise SystemExit("mutate-now: --recode wants a Huffman block")

    # The region's symbols ARE the bytes a decoder gets from it: shape
    # 1's stream under a shape-2 block, the output itself under a
    # Huffman-only one.
    at = off + skip
    lens, esc = D.table_lengths(d, at)
    t = D.build(lens)
    r = D.Bits(d, D.table_stream_at(at - 1, at, len(esc)) * 8)
    endbit = (en - pad) * 8 - 32 - ((16 - d[off]) & 15)
    syms = bytearray()
    while r.p < endbit:
        syms.append(r.sym(t))
    lengths = deep_code(syms, maxlen) if maxlen > 15 else None
    payload = S.encode_huffman(bytes(syms), 0x100, maxlen=maxlen,
                               lengths=lengths)
    deep = sum(1 for v in (lengths or S.huffman_lengths(
        Counter(syms), maxlen)).values() if v > 15)

    out = bytearray(d[:off]) + payload + bytes(pad + 4)
    newend = len(out)
    # the record's end offset, then the table's checksum, then the
    # entry record's data-area end and its own checksum
    p = st + 4
    while True:
        e = int.from_bytes(out[p + 4:p + 8], "big")
        if e == en:
            out[p + 4:p + 8] = struct.pack(">I", newend)
            break
        p += 8
    tail = st + 4
    while int.from_bytes(out[tail + 4:tail + 8], "big") != newend:
        tail += 8
    tail += 8 + 4
    out[tail:tail + 4] = struct.pack(">I", sum(out[st:tail]) & 0xFFFFFFFF)
    rec = 24
    out[rec + 102:rec + 106] = struct.pack(">I", newend)
    out[rec + 106:rec + 110] = struct.pack(
        ">I", sum(out[rec:rec + 106]) & 0xFFFFFFFF)
    fix_trailer(out, off, newend - pad)
    d[:] = out
    return 1, ("re-coded at most %d deep: %d symbol(s) escape past 15, "
               "%d B -> %d B" % (maxlen, deep, en, newend))


def mutate_delta(d, delta, which="all"):
    """Rebase a member's block table: the offsets it STORES fall short of
    the real ones by `delta`, which is the shape `src/fmt_now.c`'s
    offset-delta search exists to correct (now_find_delta). The table's
    own checksum is recomputed over the stored values, so the file is
    consistent — the question is whether the format's own decoder
    corrects it.

    **`which` says WHICH offsets move, and that is the whole point of
    the ladder**: every reading of how a decoder anchors this table
    predicts a different answer for a different subset.

        "all"       the u32 and every record's end offset
        "first"     the u32 alone, every record left correct
        "records"   every record's end offset, the u32 left correct
        an int k    the end offset of record k alone, counting the
                    leading no-bytes record 5.0.1 writes as 0

    A negative `delta` moves the offsets the other way — past the block
    rather than short of it — which is the case an "always correct
    forward" reading and an "ignore them" reading disagree about.

    The table is the one this project derived: a u32 at the start of the
    member's data area saying where the first block begins, then one
    `[mode][padding][end offset]` record per block from +4. This
    docstring described the `[offset][mode][padding]` framing at +2 or
    +10 until 2026-09-21, which is the reading the note dropped that day
    and which this function never used.
    """
    ms = D.members(d)
    n = 0
    for name, dlen, rlen, st, en in ms:
        first = int.from_bytes(d[st:st + 4], "big")
        nrec = (first - st - 4) // 8 - 1
        if nrec < 0 or st + 4 + 8 * nrec + 8 > len(d):
            continue
        if which in ("all", "first"):
            d[st:st + 4] = struct.pack(">I", first - delta)
        p = st + 4
        for k in range(nrec):
            if which in ("all", "records") or which == k:
                end = int.from_bytes(d[p + 4:p + 8], "big")
                d[p + 4:p + 8] = struct.pack(">I", end - delta)
            p += 8
        p += 4                              # the four bytes before the sum
        d[p:p + 4] = struct.pack(">I", sum(d[st:p]) & 0xFFFFFFFF)
        n += 1
    how = {"all": "every stored offset",
           "first": "the first-block offset alone",
           "records": "every record's end offset, the first-block offset left"
                      " correct"}.get(which, "record %s's end offset alone"
                                             % which)
    return n, "%s -= %d" % (how, delta)


# ------------------------------------------------------------------
# What this project writes that Now Compress will not read
# ------------------------------------------------------------------

# One rung per way a file `tools/synth_now.py` writes differs from one
# Now Compress wrote, measured by diffing the two records field for
# field. The file header is not in the list: the two agree on all 24
# bytes, checksum included.
SYNTH_GROUPS = ("namepad", "spare", "finder", "dates", "leadrec")


def mutate_like_synth(d, group):
    """Make a file the ENCODER wrote look, in ONE respect, like a file
    written here — which Now Compress calls *"damaged and cannot be
    repaired"* however right every field this project has measured is
    (docs/formats/now-compress.md, *What this note does NOT describe*).

    **A refusal of a file with five differences in it names none of
    them.** Each group below is one of those differences applied to a
    file Decompress reads today, so a rung that is refused names the
    field; a ladder every rung of which survives says the cause is not
    in these fields at all, and the next place to look is the block
    payload — which `--recode` has already put a stream written here
    through the same decoder intact.

        namepad  the 23 bytes after a short Pascal name, which the
                 encoder leaves full of catalogue-shaped values and
                 this project zeroes
        spare    the u32 at +94 of an entry record, which no field this
                 project names accounts for
        finder   the Finder flags at +46 (0x0100, `kHasBeenInited`)
        dates    created and modified, +54 and +58
        leadrec  the leading `0d4c 0037` record 5.0.1 writes in front of
                 every block table and this project does not write at
                 all — the one structural difference of the five, so the
                 file is laid out again eight bytes shorter
    """
    rec = 24
    if group == "namepad":
        at = rec + 1 + d[rec]
        was = bytes(d[at:rec + 32])
        d[at:rec + 32] = bytes(len(was))
        how = "the %d bytes after the name zeroed (were %s)" % (
            len(was), was.hex() or "zero already")
    elif group == "spare":
        was = int.from_bytes(d[rec + 94:rec + 98], "big")
        d[rec + 94:rec + 98] = bytes(4)
        how = "the u32 at +94 zeroed (was %#x)" % was
    elif group == "finder":
        was = int.from_bytes(d[rec + 46:rec + 48], "big")
        d[rec + 46:rec + 48] = bytes(2)
        how = "the Finder flags zeroed (were %#06x)" % was
    elif group == "dates":
        d[rec + 54:rec + 58] = struct.pack(">I", 0x9E7C0000)
        d[rec + 58:rec + 62] = struct.pack(">I", 0x9E7C0E10)
        how = "created and modified := what synth_now.py writes"
    elif group == "leadrec":
        return drop_leading_record(d)
    else:
        raise SystemExit("mutate-now: no such group %r" % group)
    d[rec + 106:rec + 110] = struct.pack(
        ">I", sum(d[rec:rec + 106]) & 0xFFFFFFFF)
    return 1, how


def zero_field(d, at, n):
    """Zero `n` bytes at `at` of the entry record and fix its checksum —
    for bisecting INSIDE a field once a group has been shown to matter.

    `--like-synth namepad` zeros all 23 bytes after a short name at once;
    when that is refused, the question becomes which of them, and this
    is how it gets asked without inventing a group name for a field
    nobody has identified yet.
    """
    rec = 24
    if at < 0 or at + n > 106:
        raise SystemExit("mutate-now: --zero is inside the 106 bytes the "
                         "record's checksum covers")
    was = bytes(d[rec + at:rec + at + n])
    d[rec + at:rec + at + n] = bytes(n)
    d[rec + 106:rec + 110] = struct.pack(
        ">I", sum(d[rec:rec + 106]) & 0xFFFFFFFF)
    return 1, "%d byte(s) at +%d zeroed (were %s)" % (n, at, was.hex())


def take_head(d, other):
    """Give this file the 24-byte header and 110-byte entry record of
    another one, keeping everything that describes its OWN data area.

    The halving step, for when every named difference has been tested
    one at a time and the file is still refused: a one-entry file is a
    134-byte head and a data area, so the head of one and the body of
    the other put the cause on one side of that line in a single rung.
    Both directions are this one option — `--head` a file the encoder
    wrote onto one written here, and the reverse.
    """
    head = bytearray(open(other, "rb").read()[:24 + 110])
    if len(head) < 134:
        raise SystemExit("mutate-now: --head wants a Now Compress file")
    rec, mine = 24, d[24:24 + 110]
    for at, n in ((86, 4), (90, 4), (98, 4), (102, 4)):
        head[rec + at:rec + at + n] = mine[at:at + n]   # the fork lengths
                                                       # and the data bounds
    head[rec + 106:rec + 110] = struct.pack(
        ">I", sum(head[rec:rec + 106]) & 0xFFFFFFFF)
    head[20:24] = struct.pack(">I", sum(head[:20]) & 0xFFFFFFFF)
    d[:134] = head
    return 1, "the header and entry record of %s" % os.path.basename(other)


def drop_leading_record(d):
    """Take the leading record out of a one-entry file's block table and
    lay the file out again around the eight bytes it loses.

    That record produces no bytes — its end offset repeats the
    first-block offset the u32 already gave — and 5.0.1 writes one in
    front of every table while the 1993 archive writes none, so a
    decoder that needs it would already refuse that archive. This asks
    whether its own decoder needs it.
    """
    ms = D.members(d)
    if not ms or len(ms) != 1:
        raise SystemExit("mutate-now: --like-synth leadrec wants a "
                         "one-entry file")
    name, dlen, rlen, st, en = ms[0]
    first = int.from_bytes(d[st:st + 4], "big")
    nrec = (first - st - 4) // 8 - 1
    recs = [bytes(d[st + 4 + 8 * k:st + 12 + 8 * k]) for k in range(nrec)]
    lead = int.from_bytes(recs[0][4:8], "big")
    if lead != first or nrec < 2:
        raise SystemExit("mutate-now: this table has no leading record")
    spare = bytes(d[st + 4 + 8 * nrec:st + 8 + 8 * nrec])   # the four bytes
    tail = bytes(d[first:en])                               # the blocks

    out = bytearray(d[:st])
    out += struct.pack(">I", first - 8)
    for r in recs[1:]:
        out += r[:4] + struct.pack(">I", int.from_bytes(r[4:8], "big") - 8)
    out += spare
    out += struct.pack(">I", sum(out[st:]) & 0xFFFFFFFF)
    out += tail
    out += d[en:]
    rec = 24
    out[rec + 102:rec + 106] = struct.pack(">I", en - 8)
    out[rec + 106:rec + 110] = struct.pack(
        ">I", sum(out[rec:rec + 106]) & 0xFFFFFFFF)
    d[:] = out
    return 1, ("the leading %s record dropped, %d B -> %d B"
               % (recs[0][:4].hex(), en, en - 8))


# The mode and padding 5.0.1 writes in the record it puts in front of
# every block table (docs/formats/now-compress.md, *A member's blocks*).
LEAD_RECORD = bytes.fromhex("0d4c0037")


def add_leading_record(d):
    """Put that record into a one-entry file that has none — the inverse
    of `drop_leading_record`, and the specimen that makes the answer
    positive rather than negative.

    A file written here is refused; dropping this record from a file the
    encoder wrote gets the SAME refusal. Neither says the record is what
    was missing — for that, a file that lacks one has to gain one and be
    read (DECISIONS.md 2026-09-21, *the control that stopped the wrong
    answer*).
    """
    ms = D.members(d)
    if not ms or len(ms) != 1:
        raise SystemExit("mutate-now: --add-leadrec wants a one-entry file")
    name, dlen, rlen, st, en = ms[0]
    first = int.from_bytes(d[st:st + 4], "big")
    nrec = (first - st - 4) // 8 - 1
    recs = [bytes(d[st + 4 + 8 * k:st + 12 + 8 * k]) for k in range(nrec)]
    if nrec and int.from_bytes(recs[0][4:8], "big") == first:
        raise SystemExit("mutate-now: this table already has one")
    spare = bytes(d[st + 4 + 8 * nrec:st + 8 + 8 * nrec])
    tail = bytes(d[first:en])

    out = bytearray(d[:st])
    out += struct.pack(">I", first + 8)
    out += LEAD_RECORD + struct.pack(">I", first + 8)      # produces no bytes
    for r in recs:
        out += r[:4] + struct.pack(">I", int.from_bytes(r[4:8], "big") + 8)
    out += spare
    out += struct.pack(">I", sum(out[st:]) & 0xFFFFFFFF)
    out += tail
    out += d[en:]
    rec = 24
    out[rec + 102:rec + 106] = struct.pack(">I", en + 8)
    out[rec + 106:rec + 110] = struct.pack(
        ">I", sum(out[rec:rec + 106]) & 0xFFFFFFFF)
    d[:] = out
    return 1, ("a leading %s record added, %d B -> %d B"
               % (LEAD_RECORD.hex(), en, en + 8))


# ------------------------------------------------------------------
# MacBinary
# ------------------------------------------------------------------

def crc16(b):
    """The MacBinary II header CRC: x^16 + x^12 + x^5 + 1, zero seed."""
    crc = 0
    for byte in b:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 \
                else (crc << 1) & 0xFFFF
    return crc


def rename(d, name):
    """Change the name a compressed file carries INSIDE it — the entry
    record's Pascal name — and fix that record's checksum. Several
    mutations of one specimen have to sit on one volume, and Now
    Compress names what it expands after this field.

    **What follows the name is left alone**, and that is not tidiness:
    the encoder leaves 23 catalogue-shaped bytes there and this rewrote
    them as zeros until 2026-09-21, which is `--like-synth namepad`
    applied to every file on the volume — including the control. Give a
    rung a name as long as the one it replaces and those bytes never
    move.
    """
    raw = name.encode("mac-roman")
    if not 1 <= len(raw) <= 31:
        raise SystemExit("mutate-now: a name is 1..31 bytes")
    rec = 24
    d[rec] = len(raw)
    d[rec + 1:rec + 1 + len(raw)] = raw
    d[rec + 106:rec + 110] = struct.pack(
        ">I", sum(d[rec:rec + 106]) & 0xFFFFFFFF)
    return name


def splice(datafork, src, dst, name=None):
    """Put a data fork into a MacBinary file, fixing the length and the
    header's CRC so the Mac takes it."""
    blob = bytearray(open(src, "rb").read())
    new = open(datafork, "rb").read()
    if name:
        raw = name.encode("mac-roman")
        blob[1] = len(raw)
        blob[2:2 + 63] = raw + bytes(63 - len(raw))
    dlen = struct.unpack(">I", blob[0x53:0x57])[0]
    rlen = struct.unpack(">I", blob[0x57:0x5B])[0]
    roff = 128 + ((dlen + 127) & ~127)
    rsrc = bytes(blob[roff:roff + rlen])
    blob[0x53:0x57] = struct.pack(">I", len(new))
    blob[124:126] = struct.pack(">H", crc16(bytes(blob[:124])))
    out = bytearray(blob[:128])
    out += new
    out += bytes((-len(new)) % 128)
    out += rsrc
    out += bytes((-len(rsrc)) % 128)
    open(dst, "wb").write(bytes(out))
    return len(new), len(rsrc)


def check(orig, mutated):
    """Decode both with derive_now and report whether OUR reader gets the
    same bytes out of each — which is what makes the mutation a fair
    question rather than a corruption."""
    same = bad = 0
    a = D.read_archive(orig)
    b = D.read_archive(mutated)
    if a is None or b is None:
        print("mutate-now: --check needs an archive this reader walks")
        return 1
    for (na, _, ba), (nb, _, bb) in zip(a, b):
        if (ba is None) != (bb is None):
            bad += 1
            print("  %s: %s" % (na, "no longer reads as a member"
                                if bb is None else "did not read before"))
            continue
        for xa, xb in zip(ba or [], bb or []):
            if xa[3] == xb[3]:
                same += 1
            else:
                bad += 1
                print("  %s @%d: %s -> %s" % (na, xa[1], xa[3], xb[3]))
    print("mutate-now: %d block(s) read the same, %d changed" % (same, bad))
    # A mutation nothing read is a mutation nothing checked. That line
    # above said "0 block(s) read the same, 0 changed" and this returned
    # 0 until 2026-10-05, and EVERY --delta run took that route: this
    # reader had no offset-delta search, so a rebased table read as no
    # table at all and the vacuous pass looked like a verdict
    # (DECISIONS.md 2026-10-05).
    if not same and not bad:
        print("mutate-now: --check compared NOTHING, which is not a pass")
        return 1
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--byte2", type=lambda s: int(s, 0))
    ap.add_argument("--prefix", help="two bytes, hex")
    ap.add_argument("--count", type=lambda s: int(s, 0))
    ap.add_argument("--delta", type=lambda s: int(s, 0))
    ap.add_argument("--first-only", action="store_true",
                    help="with --delta, move only the u32 that says where "
                         "the first block begins")
    ap.add_argument("--records-only", action="store_true",
                    help="with --delta, move every record's end offset and "
                         "leave that u32 correct")
    ap.add_argument("--record", type=int, metavar="K",
                    help="with --delta, move the end offset of record K "
                         "alone")
    ap.add_argument("--zero", metavar="AT:LEN",
                    help="zero LEN bytes at +AT of the entry record, for "
                         "bisecting inside a field")
    ap.add_argument("--add-leadrec", action="store_true",
                    help="put the leading 0d4c 0037 record into a table "
                         "that has none, the inverse of --like-synth leadrec")
    ap.add_argument("--head", metavar="FILE",
                    help="take FILE's 24-byte header and 110-byte entry "
                         "record, keeping this file's own data area")
    ap.add_argument("--like-synth", metavar="GROUP",
                    help="make an encoder-written file look like one this "
                         "project writes, in one respect: %s"
                         % ", ".join(SYNTH_GROUPS))
    ap.add_argument("--recode", type=int, metavar="MAXLEN",
                    help="re-code a one-block file's Huffman region with a "
                         "code at most MAXLEN deep")
    ap.add_argument("--splice", nargs=2, metavar=("IN.bin", "OUT.bin"),
                    help="put DST's bytes into a MacBinary file")
    ap.add_argument("--rename", metavar="NAME",
                    help="rename the file inside and out, so several "
                         "mutations of one specimen fit on one volume")
    ap.add_argument("--check", action="store_true",
                    help="decode both and report what changed")
    args = ap.parse_args()

    d = bytearray(open(args.src, "rb").read())
    orig = bytes(d)
    did = []
    if args.rename:
        did.append((1, "named %s" % rename(d, args.rename)))
    if args.byte2 is not None:
        did.append(mutate_byte2(d, args.byte2))
    if args.prefix:
        did.append(mutate_prefix(d, bytes.fromhex(args.prefix)))
    if args.count is not None:
        did.append(mutate_count(d, args.count))
    if args.zero:
        at, _, n = args.zero.partition(":")
        did.append(zero_field(d, int(at, 0), int(n or 1, 0)))
    if args.add_leadrec:
        did.append(add_leading_record(d))
    if args.head:
        did.append(take_head(d, args.head))
    if args.like_synth:
        did.append(mutate_like_synth(d, args.like_synth))
    if args.recode is not None:
        did.append(mutate_recode(d, args.recode))
    if args.delta is not None:
        which = ("first" if args.first_only else
                 "records" if args.records_only else
                 args.record if args.record is not None else "all")
        did.append(mutate_delta(d, args.delta, which))
    if not did:
        raise SystemExit("mutate-now: nothing asked for")
    open(args.dst, "wb").write(bytes(d))
    for n, how in did:
        print("mutate-now: %d block(s): %s" % (n, how))
    rc = 0
    if args.check:
        rc = check(orig, bytes(d))
    if args.splice:
        n, r = splice(args.dst, args.splice[0], args.splice[1], args.rename)
        print("mutate-now: %s, %d B data + %d B resource"
              % (args.splice[1], n, r))
    return rc


if __name__ == "__main__":
    sys.exit(main())

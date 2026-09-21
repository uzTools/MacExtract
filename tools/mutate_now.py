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


def mutate_delta(d, delta, firstonly=False):
    """Rebase a member's block table: every offset it STORES falls short
    of the real one by `delta`, which is the shape `src/fmt_now.c`'s
    offset-delta search exists to correct (now_find_delta). The table's
    own checksum is recomputed over the stored values, so the file is
    consistent — the question is whether the format's own decoder
    corrects it.

    The 5.0.1 layout only: the table at +10 of the member's data area,
    with the first-block offset at +2 restated by the first record.
    """
    ms = D.members(d)
    n = 0
    for name, dlen, rlen, st, en in ms:
        first = int.from_bytes(d[st:st + 4], "big")
        nrec = (first - st - 4) // 8 - 1
        if nrec < 0 or st + 4 + 8 * nrec + 8 > len(d):
            continue
        d[st:st + 4] = struct.pack(">I", first - delta)
        p = st + 4
        for _ in range(nrec):
            if not firstonly:
                end = int.from_bytes(d[p + 4:p + 8], "big")
                d[p + 4:p + 8] = struct.pack(">I", end - delta)
            p += 8
        p += 4                              # the four bytes before the sum
        d[p:p + 4] = struct.pack(">I", sum(d[st:p]) & 0xFFFFFFFF)
        n += 1
    return n, ("the first-block offset alone -= %d" if firstonly
               else "every stored offset -= %d") % delta


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
    Compress names what it expands after this field."""
    raw = name.encode("mac-roman")
    if not 1 <= len(raw) <= 31:
        raise SystemExit("mutate-now: a name is 1..31 bytes")
    rec = 24
    d[rec:rec + 32] = bytes([len(raw)]) + raw + bytes(31 - len(raw))
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
        for xa, xb in zip(ba or [], bb or []):
            if xa[3] == xb[3]:
                same += 1
            else:
                bad += 1
                print("  %s @%d: %s -> %s" % (na, xa[1], xa[3], xb[3]))
    print("mutate-now: %d block(s) read the same, %d changed" % (same, bad))
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
    if args.recode is not None:
        did.append(mutate_recode(d, args.recode))
    if args.delta is not None:
        did.append(mutate_delta(d, args.delta, args.first_only))
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

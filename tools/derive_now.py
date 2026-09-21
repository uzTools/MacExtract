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

    tools/derive_now.py                 the harness's specimens
    tools/derive_now.py ARCHIVE...      walk a .sea or .now

**Two coders, the block structure and the archive container.** Every
compressed specimen the harness has made reads byte for byte, and the
corpus's 1993 `derived-Expand_Now_1.0.1.sea` walks into the three
blocks its fork needs — but the coder two of those three use is read
only as far as its code table, so nothing in the corpus decodes here
yet. `src/fmt_now.c` still cites XADMaster for everything, and will
until that stream is described (docs/formats/now-compress.md).

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


def decode(d, p, nout):
    """The shape.

    A flag byte, then eight tokens, its bits taken most significant
    first: a 1 is a literal byte, a 0 is a match.

    A match is two bytes — `length - 2`, then the distance — EXCEPT
    that a length byte of zero is an escape, and then the token is
    three bytes: zero, the distance, and `length - 2`. So a match
    reaches 2..257 bytes back at most 255 bytes, which is why this
    shape only ever appears on small forks: the encoder picks another
    when a file needs a longer reach.

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
                n = d[p]
                if n == 0:
                    dist, ln = d[p + 1], d[p + 2] + 2
                    p += 3
                else:
                    ln, dist = n + 2, d[p + 1]
                    p += 2
                if dist == 0 or dist > len(out):
                    raise ValueError("distance %d" % dist)
                for _ in range(ln):
                    out.append(out[-dist])
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


def decode_huff(d, t, bitstart, nout):
    """Shape 1's framing, with every byte of it Huffman-coded.

    The flag byte is a symbol like any other — which is why symbol 255
    carries the shortest code in a file of incompressible data: a flag
    of eight literals IS 0xff, and it occurs once per eight bytes.

    A match is two symbols: `length = (S & 7) + 2` and
    `distance = ((S >> 3) << 8) | D`, so the reach is 11 bits where
    shape 1 had 8. A length of 2 — the low three bits zero — escapes
    to a third symbol carrying `length - 2`.
    """
    r = Bits(d, bitstart)
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
                if dist == 0 or dist > len(out):
                    raise ValueError("distance %d" % dist)
                for _ in range(ln):
                    out.append(out[-dist])
    return bytes(out[:nout])


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
HUFFMAN_BIT = 0x20


def block_kind(mode):
    if mode == STORED:
        return "stored", 0
    if mode & HUFFMAN_BIT:
        return "shape2", 1
    return "shape1", 2


def records(d, limit=64):
    """The fork's block table: 8-byte records from offset 144 — a u16
    offset, a u16 mode, and four bytes that are zero in every specimen
    here. The list ends with a record whose offset is the fork's own
    size, which is how a reader knows it has them all.

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
    identified.
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
        else:
            t = table_at(d, at)
            for bs in range((at + 128) * 8, (at + 128 + 6) * 8):
                try:
                    piece = decode_huff(d, t, bs, n)
                except Exception:
                    continue
                out.extend(piece)
                break
            else:
                return None
    return bytes(out[:nout])


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
    at 24, 110 bytes each. Of each record this reads the five fields
    it can name: a Pascal name in the first ten bytes, the member's
    uncompressed size at +88, and at +98 and +102 the bounds of its
    data area — which is where its own fork-shaped header sits.
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
        nl = d[b]
        if nl > 31:
            return None
        name = d[b + 1:b + 1 + nl].decode("mac-roman", "replace")
        usize = int.from_bytes(d[b + 88:b + 90], "big")
        st = int.from_bytes(d[b + 98:b + 102], "big")
        en = int.from_bytes(d[b + 102:b + 106], "big")
        if not 0 < st < en <= len(d):
            return None
        out.append((name, usize, st, en))
    return out


def member_blocks(d, st, en):
    """One member's block table: eight-byte records — a u16 offset, a
    u16 mode, four more bytes — ending on the record whose offset is
    the member's end.

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
    """
    first = int.from_bytes(d[st + 2:st + 4], "big")
    for at in (st + 10, st + 2):
        recs = []
        p = at
        while p + 8 <= len(d) and len(recs) < 64:
            off = int.from_bytes(d[p:p + 2], "big")
            mode = int.from_bytes(d[p + 2:p + 4], "big")
            recs.append((off, mode))
            p += 8
            if off == en:
                break
        else:
            continue
        if recs and recs[0][0] == first and recs[-1][0] == en:
            return recs
    return None


# The coder lives in the mode word's bits, and the archive adds one the
# bare forks never set:
#   0x0000 / 0x0100  stored          0x0020  shape 2
#   0x0010 / 0x001f  shape 1         0x0040  shape 3, below
ARCHIVE_BIT = 0x40


def archive_kind(mode):
    if mode & ARCHIVE_BIT:
        return "shape3", 0
    if mode & HUFFMAN_BIT:
        return "shape2", 1
    if mode & 0x1F:
        return "shape1", 2
    return "stored", 0


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


def shape3_table(b):
    """The main table: one code length per symbol, each written in the
    code-length code, **ending where the code is complete** — nothing
    states its length and the trailing absent symbols are not sent.

    Symbols 0..255 are the literals. What follows them is the match
    alphabet and is not read here.
    """
    t = shape3_clc(b)
    r = Bits(b, TABLE_AT_BIT)
    lens, kraft = [], 0.0
    while kraft < 1.0 - 1e-12:
        v = r.sym(t)
        lens.append(v)
        if v:
            kraft += 2.0 ** -v
        if len(lens) > 600:
            raise ValueError("table does not close")
    if abs(kraft - 1.0) > 1e-12:
        raise ValueError("table overshoots")
    return lens, r.p


def read_archive(d, want=None):
    """Walk an archive and report what each member's blocks are.

    `want` maps a member name to the bytes that went in, when they are
    known; a block is then decoded and compared. Returns a list of
    (member, [(kind, offset, read)]).
    """
    ms = members(d)
    if not ms:
        return None
    out = []
    for name, usize, st, en in ms:
        recs = member_blocks(d, st, en)
        if not recs:
            out.append((name, usize, None))
            continue
        blocks = []
        pos = 0
        w = (want or {}).get(name)
        for (off, mode), (nxt, _) in zip(recs, recs[1:]):
            kind, skip = archive_kind(mode)
            n = min(BLOCK, (len(w) - pos) if w else BLOCK)
            read = None
            if w is not None and n > 0:
                try:
                    if kind == "stored":
                        read = d[off:off + n] == w[pos:pos + n]
                    elif kind == "shape1":
                        read = decode(d, off + skip, n)[0] == w[pos:pos + n]
                    elif kind == "shape2":
                        t = table_at(d, off + skip)
                        read = any(
                            decode_huff_safe(d, t, bs, n) == w[pos:pos + n]
                            for bs in range((off + skip + 128) * 8,
                                            (off + skip + 128 + 8) * 8))
                    else:
                        read = False
                except Exception:
                    read = False
            blocks.append((kind, off, mode, read))
            pos += n
        out.append((name, usize, blocks))
    return out


def decode_huff_safe(d, t, bs, n):
    try:
        return decode_huff(d, t, bs, n)
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
        for kind, off, mode, read in blocks:
            tot += 1
            if read:
                ok += 1
            mark = {True: "ok", False: "--", None: "?"}[read]
            parts.append(f"{kind}@{off} ({mode:#06x}) {mark}")
        print(f"      {name:12s} {usize:7d} B  " + ", ".join(parts))
        for kind, off, mode, read in blocks:
            if kind != "shape3":
                continue
            try:
                lens, endbit = shape3_table(d[off:])
            except Exception as e:
                print(f"        shape 3 @{off}: {e}")
                continue
            nlit = sum(1 for v in lens[:256] if v)
            print(f"        shape 3 @{off}: code-length code complete, "
                  f"{len(lens)} symbols, {nlit} literals coded, "
                  f"stream from bit {endbit}")
    return ok, tot


def archives(paths):
    """The archive pass: the harness's own `.sea` files, and any given
    on the command line."""
    ok = tot = 0
    for path in paths:
        d = open(path, "rb").read()
        want = {}
        folder = os.path.dirname(path)
        for f in os.listdir(folder) if os.path.isdir(folder) else []:
            if f.startswith("in-"):
                want[f[3:]] = open(os.path.join(folder, f), "rb").read()
        a, t = report_archive(path, d, want)
        ok += a
        tot += t
    return ok, tot


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archives", nargs="*", help="a .sea or .now to walk")
    args = ap.parse_args()
    if args.archives:
        print("derive-now: archives")
        ok, tot = archives(args.archives)
        print(f"derive-now: {ok} of {tot} member block(s) read")
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
                print(f"ok  {mode:8s} {base:10s} {len(want):6d} B from "
                      f"{len(d):6d}  block table: "
                      + ", ".join(f"{hex(o)}/{hex(m)}" for o, m in records(d)))
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
    print(f"derive-now: {ok} specimen(s) by shape 1, {huff} by shape 2, "
          f"{blocks} by several blocks, {stored} stored, {other} not read")
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
        print(f"derive-now: {a} of {t} member block(s) read; the rest are "
              f"shape 3, whose tables this reads and whose stream it does not")
    return 0


if __name__ == "__main__":
    sys.exit(main())

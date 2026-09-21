#!/usr/bin/env python3
"""synth_now.py — write Now Compress archives.

The corpus holds exactly ONE real Now Compress archive, and it is a
single file with a single fork whose blocks use two of the five shapes a
block can have. Everything else fmt_now.c implements — stored,
LZSS-only and Huffman-then-LZSS blocks, the offset-delta search,
directories, data forks, several files in one archive — had no archive
to run against.

So this writes them. Each archive is graded by `unar`, whose
XADNowCompressHandle is the implementation fmt_now.c was transcribed
from: tools/run_now.py extracts every archive here with both and
requires both to agree with the bytes that went in.

  Source: reference/XADMaster/XADNowCompressParser.m  (header, entry
          table, the per-file (offset, length) addressing)
  Source: reference/XADMaster/XADNowCompressHandle.m  (block table,
          its checksum, the delta search, and all five block shapes)

What this cannot prove is that the REFERENCE reads the format right:
for the three shapes no fixture reaches, it is the only implementation
there is, so agreement here is agreement about a transcription. The two
shapes the fixture does reach are the ones graded against a real
archive, and they are graded in the differential suite.
"""
import heapq
import os
import sys
from collections import Counter

HISTORY = 0x8000            # the sliding window kept between blocks


# ------------------------------------------------------------------
# Bits and canonical Huffman codes
# ------------------------------------------------------------------

def u16(v):
    return bytes(((v >> 8) & 0xFF, v & 0xFF))


def u32(v):
    return bytes(((v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF))


class BitW:
    """MSB-first bit writer. The format counts its stream in bits: the
    decoder derives the count from the payload's length less `16 -
    endbits`, so `endbits` is how much of the last 16-bit word is real,
    and the padding it describes can be at most 15 bits.

    A whole spare BYTE is always left, which is more than the alignment
    needs. XADMaster's bit reader tracks its position as
    `currbyte*8 - (numbits & 7)` and raises end-of-buffer as soon as
    `currbyte` passes the end, so it needs the padding to cover whatever
    its register is still holding — at most 7 bits. Below that it can
    refuse a stream this decoder reads perfectly well, which is a
    property of the oracle rather than of the format, but a generated
    archive it cannot read grades nothing. Measured 2026-08-15: with
    3 or fewer spare bits `unar` fails a block it otherwise decodes.
    """

    def __init__(self):
        self.bits = []

    def put(self, value, n):
        for i in range(n - 1, -1, -1):
            self.bits.append((value >> i) & 1)

    def finish(self):
        pad = (-len(self.bits)) % 8 + 8       # 8..15 bits, i.e. endbits 1..8
        bits = self.bits + [0] * pad
        out = bytearray()
        for i in range(0, len(bits), 8):
            b = 0
            for k in range(8):
                b = (b << 1) | bits[i + k]
            out.append(b)
        # numbits = len(out)*8 - (16 - endbits), which must be len(self.bits).
        return bytes(out), 16 - pad


def _huffman_lengths(freq):
    """Plain Huffman code lengths, deterministic in symbol order."""
    if len(freq) == 1:
        return {next(iter(freq)): 1}
    tie = 0
    heap = []
    for sym in sorted(freq):
        heap.append((freq[sym], tie, (sym,)))
        tie += 1
    heapq.heapify(heap)
    lengths = dict.fromkeys(freq, 0)
    while len(heap) > 1:
        w1, _, g1 = heapq.heappop(heap)
        w2, _, g2 = heapq.heappop(heap)
        for s in g1 + g2:
            lengths[s] += 1
        heapq.heappush(heap, (w1 + w2, tie, g1 + g2))
        tie += 1
    return lengths


def huffman_lengths(freq, maxlen):
    """Code lengths no longer than `maxlen`. Flattening the weights and
    retrying converges on a balanced code, which is short enough for any
    alphabet here; the codes only have to be legal, not optimal."""
    freq = dict(freq)
    while True:
        lengths = _huffman_lengths(freq)
        if max(lengths.values()) <= maxlen:
            return lengths
        freq = {s: max(1, w // 2) for s, w in freq.items()}


def canonical(lengths):
    """Codes in (length, symbol) order, shortest starting at zero — what
    unc_canon_build builds and what XADPrefixCode's
    shortestCodeIsZeros:YES means."""
    bylen = {}
    for sym, ln in lengths.items():
        if ln:
            bylen.setdefault(ln, []).append(sym)
    codes = {}
    code = 0
    for ln in range(1, max(lengths.values()) + 1):
        for sym in sorted(bylen.get(ln, ())):
            codes[sym] = (code, ln)
            code += 1
        code <<= 1
    return codes


def encode_huffman(data, numvalues, maxlen=15, lengths=None):
    """One UnpackHuffman region: endbits, the code as 4-bit lengths in
    symbol order, then a count of symbols whose length gains 16 and
    their indices, then word alignment from the region's start, then the
    codes.

    A length over 15 does not fit a nibble, which is what that second
    list is for; `maxlen` above 15 is how the archive that exercises it
    is made. The corpus fixture's deepest code is 12 (measured
    2026-08-15), so nothing else here reaches that branch.

    `lengths` overrides the code entirely, which is how a code DEEPER
    than the data deserves gets written: a legal prefix code need not be
    an optimal one, and `tools/mutate_now.py --recode` uses that to put
    an escape into a block Now Compress itself wrote.
    """
    if lengths is None:
        freq = Counter(data)
        if len(freq) < 2:
            for sym in range(numvalues):    # a code needs two symbols
                if sym not in freq:
                    freq[sym] = 1
                    break
        lengths = huffman_lengths(freq, maxlen)
    assert max(lengths.values()) <= 31       # 15 in the nibble, plus 16
    codes = canonical(lengths)

    def nibble(sym):
        ln = lengths.get(sym, 0)
        return ln - 16 if ln > 15 else ln

    table = bytearray()
    for i in range(numvalues // 2):
        table.append((nibble(2 * i) << 4) | nibble(2 * i + 1))
    extra = sorted(s for s, ln in lengths.items() if ln > 15)
    table.append(len(extra))
    table += bytes(extra)

    body = BitW()
    for byte in data:
        code, ln = codes[byte]
        body.put(code, ln)
    payload, endbits = body.finish()

    out = bytearray([endbits]) + table
    if len(out) & 1:
        out.append(0)
    return bytes(out + payload)


# ------------------------------------------------------------------
# Matching
# ------------------------------------------------------------------

def find_matches(buf, base, maxoffset, maxlength, minlength=3):
    """Greedy LZ77 over buf[base:], allowed to reach back into buf[:base]
    (the history) as far as `maxoffset`. Yields ("l", byte) and
    ("m", length, offset)."""
    index = {}
    for i in range(max(0, base - maxoffset), base):
        if i + 3 <= len(buf):
            index.setdefault(buf[i:i + 3], []).append(i)
    pos = base
    out = []
    while pos < len(buf):
        best_len, best_off = 0, 0
        if pos + minlength <= len(buf):
            key = buf[pos:pos + 3]
            for cand in reversed(index.get(key, ())):
                off = pos - cand
                if off > maxoffset or off < 1:
                    continue
                ln = 0
                while (ln < maxlength and pos + ln < len(buf) and
                       buf[cand + ln] == buf[pos + ln]):
                    ln += 1
                if ln > best_len:
                    best_len, best_off = ln, off
                if best_len >= maxlength:
                    break
        if best_len >= minlength:
            out.append(("m", best_len, best_off))
            step = best_len
        else:
            out.append(("l", buf[pos]))
            step = 1
        for i in range(pos, pos + step):
            if i + 3 <= len(buf):
                index.setdefault(buf[i:i + 3], []).append(i)
        pos += step
    return out


# ------------------------------------------------------------------
# The two LZSS variants
# ------------------------------------------------------------------

def encode_lzss(data):
    """UnpackLZSS: two skipped bytes, then groups of eight items under a
    flag byte — 1 a literal, 0 a match with a 13-bit offset and a length
    that is either 3 bits or a whole byte. Matches cannot reach before
    the block's own output, so no history is offered."""
    items = find_matches(data, 0, 0x1FFF, 257)
    out = bytearray(b"\x00\x00")             # skipped by the decoder
    for i in range(0, len(items), 8):
        group = items[i:i + 8]
        flags = 0
        for k, it in enumerate(group):
            if it[0] == "l":
                flags |= 0x80 >> k
        out.append(flags)
        for it in group:
            if it[0] == "l":
                out.append(it[1])
            else:
                _, length, offset = it
                short = length - 2 if 3 <= length <= 9 else 0
                out.append(((offset >> 5) & 0xF8) | short)
                out.append(offset & 0xFF)
                if not short:
                    out.append(length - 2)
    return bytes(out)


LEN_EXTRA = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
             1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5)
LEN_BASE = (0x0000, 0x0001, 0x0002, 0x0003, 0x0004, 0x0005, 0x0006, 0x0007,
            0x0008, 0x0009, 0x000a, 0x000b, 0x000c, 0x000d, 0x000e, 0x000f,
            0x0010, 0x0012, 0x0014, 0x0018, 0x001c, 0x0020, 0x0024, 0x0028,
            0x0030, 0x0038, 0x0040, 0x0050, 0x0060, 0x0070, 0x0080, 0x00a0,
            0x00c0, 0x00e0)
OFF_EXTRA = (0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2,
             3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 8, 8, 8, 8,
             8, 8, 8, 8, 9, 9, 9, 9, 10, 10, 10, 10, 11, 11, 11, 11,
             12, 12, 12, 12, 13, 13, 13, 13)
OFF_BASE = (0x0000, 0x0001, 0x0002, 0x0003, 0x0004, 0x0005, 0x0006, 0x0007,
            0x0008, 0x000a, 0x000c, 0x000e, 0x0010, 0x0014, 0x0018, 0x001c,
            0x0020, 0x0028, 0x0030, 0x0038, 0x0040, 0x0050, 0x0060, 0x0070,
            0x0080, 0x00a0, 0x00c0, 0x00e0, 0x0100, 0x0200, 0x0300, 0x0400,
            0x0500, 0x0600, 0x0700, 0x0800, 0x0900, 0x0b00, 0x0d00, 0x0f00,
            0x1100, 0x1500, 0x1900, 0x1d00, 0x2100, 0x2900, 0x3100, 0x3900,
            0x4100, 0x5100, 0x6100, 0x7100, 0x8100, 0xa100, 0xc100, 0xe100)


def _selector(value, bases, extras):
    for sel in range(len(bases) - 1, -1, -1):
        if bases[sel] <= value <= bases[sel] + (1 << extras[sel]) - 1:
            return sel, value - bases[sel]
    raise ValueError("no selector for %d" % value)


def encode_newlzss(data, history=b""):
    """UnpackNewLZSS: a 0x15a-byte table of code lengths, itself Huffman
    coded over 20 values, then one stream of literals and matches under
    two codes. Matches may reach back into the 32 KB history."""
    hist = history[-HISTORY:]
    buf = hist + data
    items = find_matches(buf, len(hist), min(len(hist) + len(data), 0xFFFF),
                         257)

    mainfreq, offfreq = Counter(), Counter()
    for it in items:
        if it[0] == "l":
            mainfreq[it[1]] += 1
        else:
            lsel, _ = _selector(it[1] - 2, LEN_BASE, LEN_EXTRA)
            osel, _ = _selector(it[2], OFF_BASE, OFF_EXTRA)
            mainfreq[0x100 + lsel] += 1
            offfreq[osel] += 1
    if not offfreq:
        offfreq[0] = 1                       # a code needs a symbol
    mainlen = huffman_lengths(mainfreq, 15)
    # Stored two longer than they are, and every value in the table is a
    # symbol of a 20-value code, so 17 is the ceiling here.
    offlen = huffman_lengths(offfreq, 15)

    header = bytearray(0x15a)
    for sym, ln in mainlen.items():
        header[sym] = ln
    for sym, ln in offlen.items():
        header[0x122 + sym] = ln + 2
    huffheader = encode_huffman(bytes(header), 20)

    maincodes = canonical(mainlen)
    offcodes = canonical(offlen)
    body = BitW()
    for it in items:
        if it[0] == "l":
            code, ln = maincodes[it[1]]
            body.put(code, ln)
        else:
            lsel, lextra = _selector(it[1] - 2, LEN_BASE, LEN_EXTRA)
            osel, oextra = _selector(it[2], OFF_BASE, OFF_EXTRA)
            code, ln = maincodes[0x100 + lsel]
            body.put(code, ln)
            if LEN_EXTRA[lsel]:
                body.put(lextra, LEN_EXTRA[lsel])
            code, ln = offcodes[osel]
            body.put(code, ln)
            if OFF_EXTRA[osel]:
                body.put(oextra, OFF_EXTRA[osel])
    payload, endbits = body.finish()

    out = bytearray(u16((len(huffheader) + 0x2F59) & 0xFFFF))
    out.append(0)
    out.append(endbits)
    out += huffheader
    if len(out) & 1:                         # WordAlign from the block start
        out.append(0)
    return bytes(out + payload)


# ------------------------------------------------------------------
# Blocks, block tables, entries
# ------------------------------------------------------------------

SHAPES = ("stored", "lzss", "huffman", "hufflzss", "newlzss")


def encode_block(shape, piece, history):
    """(flags, payload). The flag bits are the reference's:
    0x20 Huffman, 0x20|0x1f Huffman then LZSS, 0x40 new LZSS,
    0x1f alone LZSS, nothing at all stored."""
    if shape == "stored":
        return 0x0000, piece
    if shape == "lzss":
        return 0x0001, encode_lzss(piece)
    if shape == "huffman":
        return 0x0020, encode_huffman(piece, 0x100)
    if shape == "huffdeep":                  # same shape, deeper code
        return 0x0020, encode_huffman(piece, 0x100, maxlen=25)
    if shape == "hufflzss":
        return 0x0021, encode_huffman(encode_lzss(piece), 0x100)
    if shape == "newlzss":
        return 0x0040, encode_newlzss(piece, history)
    raise ValueError(shape)


def encode_stream(stream, shapes, chunk, dictcache, use_dict, restarts=()):
    """Cut a file's fork bytes into blocks, tracking what the decoder's
    32 KB window will hold at each one. A block that STARTS a stream gets
    the dictionary cache rather than the running window, and is also the
    only kind of block that writes the cache back — which is the
    reference's rule, transcribed, not an inference from it."""
    blocks = []
    window = dictcache
    dictnow = dictcache
    pos, i = 0, 0
    while pos < len(stream):
        piece = stream[pos:pos + chunk]
        shape = shapes[i % len(shapes)]
        isfirst = (i == 0) or (i in restarts)
        if isfirst:
            window = dictnow
        history = window if (use_dict or not isfirst) else b""
        blocks.append(encode_block(shape, piece, history))
        window = (window + piece)[-HISTORY:]
        if isfirst:
            dictnow = window
        pos += len(piece)
        i += 1
    return blocks, dictnow


# The mode and padding Now Compress 5.0.1 writes in the record it puts
# in front of a compressed file's block table. The file the program
# accepted on 2026-09-21 had these, so this writes these.
LEAD_WORDS = bytes.fromhex("0d4c0037")


def build_table(blocks, table_off, delta=0, padding=0, restarts=(),
                restart_words=None):
    """A file's block table: the first data offset, one 8-byte record per
    block, four bytes, and a 32-bit sum of everything before them. Every
    offset stored is the real one less `delta`, which is how the archives
    that need the delta search are made.

    `restarts` names blocks before which a zero-length record is written:
    the reference reads that as "the next block starts a stream", which
    is what makes it reload the dictionary cache mid-table.

    `restart_words` are the mode and padding to write in such a record.
    They mean nothing to any reader here — the field that carries the
    meaning is the end offset — and the encoder's own values are not
    constant either (`0d4c 0037` in every file 5.0.1 wrote here,
    `84e4 01e4` in the 1995 archive). The default is zeros, which every
    archive this file writes has used since M12 and `unar` reads; the
    compressed files handed to Now Compress itself carry 5.0.1's pair,
    because that is what the specimen it accepted had in it and nothing
    here has measured the difference.
    """
    nrecs = len(blocks) + len(restarts)
    first = table_off + 4 + 8 * nrecs + 8
    recs, blob = bytearray(), bytearray()
    checksum = sum(u32(first - delta))
    last = first
    for i, (flags, payload) in enumerate(blocks):
        if i in restarts:
            rec = (restart_words or (u16(0) + u16(0))) + u32(last - delta)
            recs += rec
            checksum += sum(rec)
        nxt = last + len(payload) + padding + 4
        rec = u16(flags) + u16(padding) + u32(nxt - delta)
        recs += rec
        checksum += sum(rec)
        blob += payload + bytes(padding + 4)
        last = nxt
    tail = bytes(4)
    checksum += sum(tail)
    table = u32(first - delta) + recs + tail + u32(checksum & 0xFFFFFFFF)
    assert len(table) == 4 + 8 * nrecs + 8
    return bytes(table), bytes(blob)


def entry_record(name, isdir, numdir, datasize, rsrcsize, datastart, dataend,
                 typ=b"TEXT", creator=b"UNCL"):
    rec = bytearray(110)
    raw = name.encode("mac-roman")
    assert 1 <= len(raw) <= 31
    rec[0] = len(raw)
    rec[1:1 + len(raw)] = raw
    rec[36:38] = u16(0x10 if isdir else 0x00)
    rec[38:42] = typ
    rec[42:46] = creator
    rec[54:58] = u32(0x9E7C0000)             # creation, seconds since 1904
    rec[58:62] = u32(0x9E7C0E10)             # modification
    rec[82:84] = u16(numdir)
    rec[86:90] = u32(datasize)
    rec[90:94] = u32(rsrcsize)
    rec[98:102] = u32(datastart)
    rec[102:106] = u32(dataend)
    rec[106:110] = u32(sum(rec[0:106]))      # what unc_sniff checks
    return bytes(rec)


def folder(name, children):
    return {"name": name, "isdir": True, "children": children}


def file(name, data=b"", rsrc=b"", shapes=("stored",), chunk=4096,
         padding=0, use_dict=False, restarts=(), typ=b"TEXT",
         creator=b"UNCL"):
    return {"name": name, "isdir": False, "data": data, "rsrc": rsrc,
            "shapes": shapes, "chunk": chunk, "padding": padding,
            "use_dict": use_dict, "restarts": restarts, "typ": typ,
            "creator": creator}


def build_archive(tree, delta=0, lead=False, sums=False, arch=False):
    """Lay out a whole archive: 24-byte header, the entry records in
    depth-first order, then one block table and its blocks per file.

    `delta` is how far the offsets a table STORES fall short of the real
    ones; "relative" means each table's offsets are relative to itself,
    which is the shape that makes the first one obviously wrong.

    `lead` and `sums` exist to ask **Now Compress** about these archives,
    which nothing had until 2026-09-21: they are graded by `unar`, which
    accepts them, and they differ from what the encoder writes in ways
    nothing here checks (TESTING.md, *what the derivation tools cannot
    see*). Each is one rung of that ladder and both default OFF, so the
    thirteen archives and the committed fixture are unchanged:

    - `lead` writes the **fork-boundary record** in front of each
      member's first block. Every member of every file the encoder wrote
      has exactly one, and a compressed FILE without one is refused
      (docs/formats/now-compress.md, *A member's blocks*). These members
      are data-only, so the boundary belongs at the head.
    - `sums` fills in the four things the file header and the blocks
      leave at zero: the setting at +2, the 65,536 at +4, the byte sum at
      +20, and **each block's four-byte trailer**.
    - `arch` sets the `0x0100` bit every mode word in an archive Now
      Compress wrote carries and none of these has: `0140` shape 3,
      `0120` Huffman only, `0100` stored, against the `0040`/`0020`
      written here (docs/formats/now-compress.md, *The archive layer*).
    """
    flat = []

    def walk(node):
        flat.append(node)
        if node["isdir"]:
            for child in node["children"]:
                walk(child)
    for node in tree:
        walk(node)

    at = 24 + 110 * len(flat)
    streams, dictcache = {}, bytes(HISTORY)
    for i, node in enumerate(flat):
        if node["isdir"]:
            continue
        stream = node["rsrc"] + node["data"]
        restarts = node["restarts"]
        if lead:
            restarts = tuple(sorted(set(restarts) | {0}))
        blocks, dictcache = encode_stream(stream, node["shapes"],
                                          node["chunk"], dictcache,
                                          node["use_dict"], restarts)
        d = at if delta == "relative" else delta
        if arch:
            blocks = [(flags | 0x0100, payload) for flags, payload in blocks]
        table, blob = build_table(blocks, at, d, node["padding"], restarts,
                                  LEAD_WORDS if lead else None)
        if sums:
            blob = bytearray(blob)
            end = 0
            for _flags, payload in blocks:
                end += len(payload) + node["padding"]
                blob[end:end + 4] = u32(sum(blob[end - len(payload)
                                                 - node["padding"]:end]))
                end += 4
            blob = bytes(blob)
        streams[i] = (at, table + blob)
        at += len(table) + len(blob)

    out = bytearray(24)
    out[0:2] = b"\x00\x02"
    if sums:
        out[2:4] = u16(0x0160)               # the setting an archive carries
        out[4:8] = u32(0x10000)              # the window an archive needs
    out[8:12] = u32(len(flat))
    for i, node in enumerate(flat):
        if node["isdir"]:
            out += entry_record(node["name"], True, len(node["children"]),
                                0, 0, 0, 0, b"fold", b"MACS")
        else:
            start, blob = streams[i]
            out += entry_record(node["name"], False, 0, len(node["data"]),
                                len(node["rsrc"]), start, start + len(blob),
                                node["typ"], node["creator"])
    if sums:
        out[20:24] = u32(sum(out[:20]))
    for i in sorted(streams):
        out += streams[i][1]
    return bytes(out)


# ------------------------------------------------------------------
# The sample content, and the archives made of it
# ------------------------------------------------------------------

def sample_data():
    """Content chosen so every block shape has something to do: prose
    that repeats (matches), a narrow alphabet (Huffman), and bytes that
    compress to nothing at all."""
    prose = (b"Now Compress was Now Software's, and it shipped with Now "
             b"Utilities. It compresses a fork at a time, in blocks.\n")
    text = (prose * 60)[:6000]
    runs = b"".join(bytes([0x41 + (i % 5)]) * 37 for i in range(200))[:5000]
    noise = bytes((i * 181 + (i >> 3) * 7) & 0xFF for i in range(4096))
    # Fibonacci frequencies force a Huffman code one symbol deep per
    # symbol, which is how a length over 15 — and so the "extra length"
    # list that carries it — is reached at all.
    counts = [1, 1]
    while len(counts) < 18:
        counts.append(counts[-1] + counts[-2])
    deep = b"".join(bytes([0x41 + i]) * n for i, n in enumerate(counts))
    return {"text": text, "runs": runs, "noise": noise, "deep": deep}


def archives():
    """name -> (tree, delta). The expected content is read back out of
    the tree by run_now.py, so there is one description, not two."""
    d = sample_data()
    out = {}

    # One archive per block shape, each holding all three kinds of
    # content so the shape is exercised on more than one distribution.
    for shape in SHAPES:
        out["synth-now-%s" % shape] = ([
            file("text", data=d["text"], shapes=(shape,), chunk=2048),
            file("runs", data=d["runs"], shapes=(shape,), chunk=1500),
            file("noise", data=d["noise"], shapes=(shape,), chunk=4096),
        ], 0)

    # Every shape in one stream, so a block of each kind decodes against
    # a history the previous shape left behind, and one block carries
    # padding — the record field that stands between two blocks.
    out["synth-now-mixed"] = ([
        file("mixed", data=d["text"] + d["runs"] + d["noise"],
             shapes=SHAPES, chunk=1024, padding=2),
    ], 0)

    # A folder tree, both forks, and the fork ORDER: the archive stores
    # the resource fork first and lists it second.
    out["synth-now-tree"] = ([
        folder("Folder", [
            file("two forks", data=d["text"][:900], rsrc=d["runs"][:700],
                 shapes=("newlzss",), chunk=800, typ=b"APPL",
                 creator=b"NCdc"),
            folder("Nested", [
                file("deep", data=d["noise"][:300], shapes=("huffman",)),
            ]),
            file("rsrc only", rsrc=d["text"][:512], shapes=("lzss",)),
        ]),
        file("beside", data=d["runs"][:64], shapes=("stored",)),
        folder("Empty", []),
    ], 0)

    # A Huffman code deeper than a nibble can express, so the "extra
    # length" list carries the top bit of the length. The corpus fixture
    # never needs it — its deepest code is 12.
    out["synth-now-longcodes"] = ([
        file("deep", data=d["deep"], shapes=("huffdeep",), chunk=99999),
    ], 0)

    # The offsets in the table are wrong by a constant, which is what
    # the checksum walk in now_find_delta exists to recover. Two shapes
    # of wrong: obviously wrong (the reference does not even try zero),
    # and plausible but wrong (the checksum has to fail first).
    out["synth-now-delta"] = ([
        file("shifted", data=d["text"][:3000], shapes=("newlzss", "huffman"),
             chunk=1000),
    ], "relative")
    out["synth-now-delta-small"] = ([
        file("shifted", data=d["text"][:3000], shapes=("lzss", "stored"),
             chunk=1000),
    ], 8)

    # The dictionary cache: a stream's first block may reach back into
    # the history the PREVIOUS stream left — which the reference calls
    # absurd and implements anyway — and a zero-length table record
    # makes that happen in the middle of a table as well.
    out["synth-now-dict"] = ([
        file("first", data=d["text"][:2000], shapes=("newlzss",), chunk=2000),
        file("second", data=d["text"][:1800], shapes=("newlzss",), chunk=900,
             use_dict=True),
        # The restart is on the THIRD block, deliberately: on the second
        # it would be unfalsifiable, because the cache saved after the
        # first block still holds exactly what the running window holds,
        # so ignoring the marker changes nothing. Measured — with the
        # marker there, deleting the code that reads it left the suite
        # green (2026-08-15).
        file("restart", data=d["text"][:2400], shapes=("newlzss",), chunk=800,
             use_dict=True, restarts=(2,)),
    ], 0)
    return out


def empty_stream_tree():
    """A zero-length file in the MIDDLE of an archive, which is the one
    shape the oracle cannot read.

    Its stream has no blocks at all, and `produceBlockAtOffset` tests
    `nextblock >= numblocks` with an `if` rather than a `while`: after
    loading a header that declares zero blocks it indexes `blocks[0]`
    anyway, which still holds the PREVIOUS file's first block (the array
    is only reallocated when a file needs more entries than the last
    one). So the file after the empty one is decoded at a stale offset.
    Put the empty file last and nothing ever asks for another block, so
    it reads fine — which is how the boundary was located.
    """
    d = sample_data()
    return [
        folder("Folder", [
            file("two forks", data=d["text"][:150], rsrc=d["runs"][:120],
                 shapes=("newlzss",)),
            file("empty"),                    # no forks, so no blocks
            file("after", data=d["text"][:200], shapes=("huffman",)),
        ]),
        file("beside", data=d["runs"][:64], shapes=("stored",)),
    ]


def expected(tree):
    """path -> (data, rsrc) for every file in a tree, and path -> None
    for every folder."""
    out = {}

    def walk(node, prefix):
        path = prefix + node["name"]
        if node["isdir"]:
            out[path] = None
            for child in node["children"]:
                walk(child, path + "/")
        else:
            out[path] = (node["data"], node["rsrc"])
    for node in tree:
        walk(node, "")
    return out


def build_fork(name, data, shapes=("huffman",), chunk=0x8000,
               typ=b"????", creator=b"UNIX", mode=0x003F):
    """A compressed FILE, which is an archive of one entry.

    Measured 2026-09-21: what Now Compress writes when it compresses a
    file rather than archiving one is the same 24-byte header and the
    same 110-byte entry record an archive has, with an entry count of 1,
    followed by that entry's data area (docs/formats/now-compress.md,
    *A compressed file is an archive of one entry*). `shapes` picks the
    coder: `huffman` writes a code no deeper than 15, `huffdeep` one
    that needs the escape.

    This writes one so that the encoder's own **Decompress** can be
    asked to read it — `tools/vmac/nowcompress.py --expand`. The escape
    past 15 is what it was written for: Now Compress refuses to produce
    a code deeper than 15 (eight attempts, *What this note does NOT
    describe*), so the only way to find out whether its decoder reads
    one is to write the file here. Unlike the archives above, the block
    trailers here are the real 32-bit sums and the file header carries
    its checksum, because a file with those wrong is not a fair question.

    **And the table opens with a leading record, since 2026-09-21.**
    Without one Now Compress calls the file *"damaged and cannot be
    repaired"* however right the rest of it is, which is what made every
    file this function wrote unreadable to the program it was written
    for — measured both ways round, by dropping that record from a file
    the encoder wrote and by adding one to a file this wrote
    (docs/formats/now-compress.md, *A member's blocks*). `restarts`
    reaches `build_table` only: before the first block there is no
    dictionary to reload, so the record the format wants costs the
    stream nothing.
    """
    blocks, _ = encode_stream(data, shapes, chunk, bytes(HISTORY), False)
    st = 24 + 110
    table, blob = build_table(blocks, st, restarts=(0,),
                              restart_words=LEAD_WORDS)
    blob = bytearray(blob)
    at = 0                                   # fill in each block's trailer
    for _flags, payload in blocks:
        at += len(payload)
        blob[at:at + 4] = u32(sum(bytes(blob[at - len(payload):at])))
        at += 4
    rec = entry_record(name, False, 0, len(data), 0, st,
                       st + len(table) + len(blob), typ, creator)
    hdr = bytearray(24)
    hdr[0:2] = u16(0x0002)
    hdr[2:4] = u16(mode)
    hdr[4:8] = u32(0x8000)                   # what the encoder writes here
    hdr[8:12] = u32(1)                       # one entry
    hdr[20:24] = u32(sum(hdr[:20]))
    return bytes(hdr) + rec + bytes(table) + bytes(blob)


def write_one(outdir, name, tree, delta=0):
    path = os.path.join(outdir, name + ".now")
    with open(path, "wb") as fh:
        fh.write(build_archive(tree, delta))
    return path, expected(tree)


def write_all(outdir):
    """The archives both implementations must agree on."""
    made = {}
    for name, (tree, delta) in archives().items():
        path, want = write_one(outdir, name, tree, delta)
        made[path] = want
    return made


def write_empty_stream(outdir):
    """The one archive they do not agree on; see empty_stream_tree."""
    return write_one(outdir, "synth-now-empty", empty_stream_tree())


# The one archive committed as a fixture, so the differential suite grades
# these paths against a committed `unar` manifest even where `unar` itself
# is absent. fixtures/SOURCES.md restores it with `-o`.
FIXTURE = "synth-now-mixed"


# What a plain (not self-extracting) Now Compress archive is on a
# Macintosh. `NCdo`/`NCdc` is what the encoder stamps a compressed FILE
# with here; `NCar` is one of the four document types **Expand Now's own
# `FREF` resources claim** (128 APPL, 129 fold, 130 ****, 131 NCdo, 132
# NCap, 133 NCar, 134 NCsg, 135 disk), which is how the type for an
# archive was found without making one.
ARCHIVE_TYPE, ARCHIVE_CREATOR = "NCar", "NCdc"


def ladder(outdir, control=None):
    """The four rungs that ask **Now Compress** about the archives this
    project writes, plus a control it must accept.

    Graded by `unar` since M12 and never put to the encoder: the
    thirteen archives differ from what Now Compress writes in ways
    nothing here checks, and *"our reader accepts it"* is the tolerance
    that cannot fail (BLOCKERS.md's list of mechanisms). Two of those
    differences are now separable, so this is a ladder and not a
    question — a rung each, and both together:

    | file | what it is |
    |---|---|
    | `ladder-control` | a real archive Now Compress wrote, its data fork retyped |
    | `ladder-plain` | what `synth_now.py` has written since M12 |
    | `ladder-sums` | plus the header's setting, window and byte sum, and every block trailer |
    | `ladder-lead` | plus the fork-boundary record every member the encoder wrote has |
    | `ladder-both` | plus both |
    | `ladder-arch` | plus the `0x0100` bit every archive mode word carries |

    `tools/vmac/nowcompress.py --dearchive` puts them on one volume and
    gives the lot to QuickFiler's **Dearchive**.
    """
    from arcmac import macbinary
    os.makedirs(outdir, exist_ok=True)
    tree = [file("alpha", data=sample_data()["text"][:3000],
                 shapes=("newlzss",), chunk=1500),
            file("beta", data=sample_data()["runs"][:2000],
                 shapes=("huffman",), chunk=2000)]
    rungs = [("plain", dict(lead=False, sums=False)),
             ("sums", dict(lead=False, sums=True)),
             ("lead", dict(lead=True, sums=False)),
             ("both", dict(lead=True, sums=True)),
             ("arch", dict(lead=True, sums=True, arch=True))]
    made = []
    if control:
        made.append(("control", open(control, "rb").read()))
    for name, kw in rungs:
        made.append((name, build_archive(tree, 0, **kw)))
    out = []
    for name, blob in made:
        mb = os.path.join(outdir, "ladder-%s.bin" % name)
        open(mb, "wb").write(macbinary("ladder-" + name, ARCHIVE_TYPE,
                                       ARCHIVE_CREATOR, blob, b""))
        open(os.path.join(outdir, "ladder-%s.now" % name), "wb").write(blob)
        out.append(mb)
        print("  ladder-%-8s %6d B" % (name, len(blob)))
    return out


def main():
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--ladder":
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "vmac"))
        ladder(args[1], args[2] if len(args) > 2 else None)
        return 0
    if len(args) == 2 and args[0] == "-o":
        tree, delta = archives()[FIXTURE]
        with open(args[1], "wb") as fh:
            fh.write(build_archive(tree, delta))
        return 0
    if len(args) != 1:
        print("usage: synth_now.py <outdir> | synth_now.py -o <file>\n"
          "       synth_now.py --ladder <outdir> [CONTROL.dat]",
          file=sys.stderr)
        return 2
    os.makedirs(sys.argv[1], exist_ok=True)
    made = write_all(sys.argv[1])
    made.update([write_empty_stream(sys.argv[1])])
    for path in sorted(made):
        print("%s (%d bytes)" % (path, os.path.getsize(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

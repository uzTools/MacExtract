#!/usr/bin/env python3
"""synth_pit.py — deterministic synthetic PackIt fixtures.

Real-world Huffman-compressed .pit files have proven unreachable (the
surviving mirrors carry only stored-mode archives), so we synthesize
them from the format description (XADPackItParser.m + macutils pit.c +
unpit 0.3.1) and validate every generated file against the `unar`
oracle before it may be used as a fixture.

Note: `macunpack` cross-checks only stored (PMag) entries. For
Huffman (PMa4) entries macutils reads the trailing fork CRC
little-endian (pit.c: `getihuffbyte() | getihuffbyte() << 8`), which
disagrees with XADMaster, unpit 0.3.1's getcrc(), and the nocash spec
(all big-endian, same as stored mode) — a macutils bug, see
DECISIONS.md M3.

Deterministic: same --seed, same bytes. Provenance recorded in
SOURCES.md as `synthetic:tools/synth_pit.py --seed N`.
"""
import argparse, heapq, os, random, struct, sys


def crc16_xmodem(data, crc=0):
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


class BitWriter:
    def __init__(self):
        self.bits = []

    def bit(self, b):
        self.bits.append(b)

    def nbits(self, v, n):
        for i in range(n - 1, -1, -1):
            self.bits.append((v >> i) & 1)

    def bytes(self):
        out = bytearray()
        acc = 0
        n = 0
        for b in self.bits:
            acc = (acc << 1) | b
            n += 1
            if n == 8:
                out.append(acc)
                acc = n = 0
        if n:
            out.append(acc << (8 - n))
        return bytes(out)


def build_huffman(data):
    """Return {sym: bitstring} for the bytes present in data."""
    freq = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1
    if not freq:
        freq[0] = 1
    if len(freq) == 1:
        # Tree with a single leaf: decoder emits it with 0 bits/symbol,
        # which the PackIt serialization supports (root is a leaf).
        (sym,) = freq
        return {sym: ""}
    heap = [(f, i, sym) for i, (sym, f) in enumerate(sorted(freq.items()))]
    heapq.heapify(heap)
    nxt = len(heap)
    while len(heap) > 1:
        f1, _, n1 = heapq.heappop(heap)
        f2, _, n2 = heapq.heappop(heap)
        heapq.heappush(heap, (f1 + f2, nxt, (n1, n2)))
        nxt += 1
    tree = heap[0][2]
    codes = {}
    stack = [(tree, "")]
    while stack:
        node, prefix = stack.pop()
        if isinstance(node, tuple):
            stack.append((node[0], prefix + "0"))
            stack.append((node[1], prefix + "1"))
        else:
            codes[node] = prefix
    return codes


def emit_tree(bw, codes):
    """Serialize the code tree: 1+8bits = leaf, 0 = branch(zero, one)."""
    # Rebuild the shape from the codes.
    if len(codes) == 1:
        bw.bit(1)
        bw.nbits(next(iter(codes)), 8)
        return
    root = {}
    for sym, code in codes.items():
        node = root
        for c in code[:-1]:
            node = node.setdefault(c, {})
        node[code[-1]] = sym
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            bw.bit(0)
            # zero branch is emitted first: push one-side first (LIFO)
            stack.append(node["1"])
            stack.append(node["0"])
        else:
            bw.bit(1)
            bw.nbits(node, 8)


def entry_header(name, dlen, rlen, type4=b"TEXT", creator=b"ttxt"):
    hdr = bytearray(94)
    nb = name.encode("mac_roman")[:63]
    hdr[0] = len(nb)
    hdr[1:1 + len(nb)] = nb
    hdr[64:68] = type4
    hdr[68:72] = creator
    hdr[72:74] = b"\x00\x00"          # finder flags
    # Offsets per macutils pit.h: lock @74 (zero), dlen @76, rlen @80,
    # ctim @84, mtim @88, CRC @92.
    struct.pack_into(">II", hdr, 76, dlen, rlen)
    struct.pack_into(">II", hdr, 84, 0xA5000000, 0xA6000000)  # create, mod
    struct.pack_into(">H", hdr, 92, crc16_xmodem(hdr[:92]))
    return bytes(hdr)


def stored_entry(name, data, rsrc):
    payload = data + rsrc
    return (b"PMag" + entry_header(name, len(data), len(rsrc)) + payload +
            struct.pack(">H", crc16_xmodem(payload)))


def huffman_entry(name, data, rsrc):
    hdr = entry_header(name, len(data), len(rsrc))
    payload = data + rsrc
    stream = hdr + payload + struct.pack(">H", crc16_xmodem(payload))
    codes = build_huffman(stream)
    bw = BitWriter()
    emit_tree(bw, codes)
    for b in stream:
        for c in codes[b]:
            bw.bit(int(c))
    return b"PMa4" + bw.bytes()


def make_archive(seed):
    rng = random.Random(seed)
    words = [b"the", b"quick", b"brown", b"fox", b"MacPlus ", b"System6 ",
             b"\x00\x01\x02", b"resource", b"PackIt! "]
    def blob(n):
        out = bytearray()
        while len(out) < n:
            out += rng.choice(words)
        return bytes(out[:n])
    parts = []
    parts.append(stored_entry("Read Me", blob(300), b""))
    parts.append(huffman_entry("Compressed Doc", blob(2000), blob(400)))
    parts.append(huffman_entry("App\xc3\xa9", blob(50), blob(1500)))
    parts.append(stored_entry("empty.rsrc only", b"", blob(120)))
    parts.append(huffman_entry("one-symbol", b"A" * 700, b""))
    return b"".join(parts) + b"PEnd"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()
    with open(args.output, "wb") as f:
        f.write(make_archive(args.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())

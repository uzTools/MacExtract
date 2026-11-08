#!/usr/bin/env python3
"""synth_arc.py — synthetic ARC archives, one per compression method.

The corpus holds no `.arc` at all (measured 2026-08-15 by innermost
format over all 805 fixtures), and the one ARC encoder reachable from
here — Debian's `arc` 5.21q — emits only methods 2, 4, 8 and 9. The
methods macutils says ArcMac actually used are 1..7:

    "Nearly PC-Arc compatible.  Arc knows 8 compression methods, I have
     seen all of them used by ArcMac, except the LZW techniques."
        -- reference/macutils/README

So the missing methods are GENERATED here, and the point of generating
them is that `unar` — which implements every one of them, in
XADARCCrunchHandle.m and XADSqueezeHandle.m — adjudicates the result.
A generator alone would be our own code grading our own code.

Layouts and algorithms come from the same two references the decoder
was transcribed from:
    reference/XADMaster/XADARCParser.m        (header, method numbers)
    reference/XADMaster/XADRLE90Handle.m      (the 0x90 run filter)
    reference/XADMaster/XADSqueezeHandle.m    (method 4's tree)
    reference/XADMaster/XADARCCrunchHandle.m  (methods 5/6/7's table)

Usage:  synth_arc.py <outdir>
"""
import os, struct, sys, heapq

# ---------------------------------------------------------------- CRC

def crc16(data):
    """IBM CRC-16, poly 0xA001 reflected, init 0, no final xor —
    XADCRCHandle's IBMCRC16 ... conditioned:NO."""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF

# ------------------------------------------------------------- RLE90

def rle90_encode(data):
    """Inverse of XADRLE90Handle: 0x90 introduces a run of the byte
    just emitted; 0x90 0x00 is a literal 0x90."""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b == 0x90:
            out += b"\x90\x00"
            i += 1
            continue
        out.append(b)
        i += 1
        run = 0
        while i < n and data[i] == b and run < 253:
            run += 1
            i += 1
        if run >= 3:
            out += bytes([0x90, run + 1])
        elif run:
            # Not worth a run; emit literally (0x90 can not appear here).
            out += bytes([b]) * run
    return bytes(out)

# ------------------------------------------------------------ squeeze

class BitLE:
    """LSB-first bit writer — CSInputNextSymbolUsingCodeLE's mirror,
    which is what method 4's Huffman codes are read with."""
    def __init__(self):
        self.out = bytearray()
        self.cur = 0
        self.n = 0

    def bit(self, b):
        if b:
            self.cur |= 1 << self.n
        self.n += 1
        if self.n == 8:
            self.out.append(self.cur)
            self.cur = 0
            self.n = 0

    def flush(self):
        if self.n:
            self.out.append(self.cur)
            self.cur = 0
            self.n = 0
        return bytes(self.out)


class BitBE:
    """MSB-first bit writer. Methods 5/6/7 read their 12-bit codes with
    CSInputNextBitString, and in XADMaster it is the LE-suffixed call
    that means LSB-first (reference/XADMaster/CSInputBuffer.h)."""
    def __init__(self):
        self.out = bytearray()
        self.cur = 0
        self.n = 0

    def bits(self, value, count):
        for i in range(count - 1, -1, -1):
            self.cur = (self.cur << 1) | ((value >> i) & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.cur)
                self.cur = 0
                self.n = 0

    def flush(self):
        if self.n:
            self.out.append(self.cur << (8 - self.n))
            self.cur = 0
            self.n = 0
        return bytes(self.out)


def squeeze_encode(data):
    """Method 4's payload: a node table, then LSB-first Huffman codes,
    terminated by symbol 256."""
    freq = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1
    freq[256] = 1
    if len(freq) == 1:                      # a tree needs two leaves
        freq[0 if 0 not in freq else 1] = 1

    heap = [(f, i, ('leaf', s)) for i, (s, f) in enumerate(sorted(freq.items()))]
    heapq.heapify(heap)
    uid = len(heap)
    while len(heap) > 1:
        f1, _, a = heapq.heappop(heap)
        f2, _, b = heapq.heappop(heap)
        heapq.heappush(heap, (f1 + f2, uid, ('node', a, b)))
        uid += 1
    tree = heap[0][2]

    # Serialize depth-first into pairs; node 0 is the root, a negative
    # entry -(value+1) is a leaf. XADSqueezeHandle reads nodes[2*n] and
    # nodes[2*n+1] as the zero and one branches.
    nodes = []

    def alloc(t):
        idx = len(nodes) // 2
        nodes.extend([0, 0])
        for side in (1, 2):
            child = t[side]
            if child[0] == 'leaf':
                nodes[idx * 2 + side - 1] = -(child[1] + 1)
            else:
                nodes[idx * 2 + side - 1] = alloc(child)
        return idx

    if tree[0] == 'leaf':                   # degenerate, cannot happen
        raise SystemExit("squeeze: single-leaf tree")
    alloc(tree)

    codes = {}

    def walk(idx, prefix):
        for side in (0, 1):
            v = nodes[idx * 2 + side]
            if v < 0:
                codes[-(v + 1)] = prefix + [side]
            else:
                walk(v, prefix + [side])

    walk(0, [])

    bw = BitLE()
    for b in data:
        for bit in codes[b]:
            bw.bit(bit)
    for bit in codes[256]:
        bw.bit(bit)

    out = bytearray(struct.pack('<H', len(nodes) // 2))
    for v in nodes:
        out += struct.pack('<h', v)
    out += bw.flush()
    return bytes(out)

# -------------------------------------------------------------- crunch

class CrunchTable:
    """The hash-addressed table of XADARCCrunchHandle, mirrored so the
    encoder knows which index the decoder will assign to a string."""

    def __init__(self, fast):
        self.fast = fast
        self.used = [False] * 4096
        self.next = [0] * 4096
        self.parent = [-1] * 4096
        self.byte = [0] * 4096
        self.index_of = {}

    def update(self, parentcode, byte):
        if self.fast:
            index = (((parentcode + byte) & 0xFFFF) * 15073) & 0xFFF
        else:
            index = ((parentcode + byte) | 0x0800) & 0xFFFF
            index = ((index * index) >> 6) & 0xFFF
        if self.used[index]:
            while self.next[index]:
                index = self.next[index]
            nxt = (index + 101) & 0xFFF
            while self.used[nxt]:
                nxt = (nxt + 1) & 0xFFF
            self.next[index] = nxt
            index = nxt
        self.used[index] = True
        self.next[index] = 0
        self.parent[index] = parentcode
        self.byte[index] = byte
        self.index_of[(parentcode, byte)] = index
        return index


def crunch_encode(data, fast):
    """Methods 5/6/7's payload: 12-bit codes, LSB-first."""
    t = CrunchTable(fast)
    numfree = 4096 - 256
    roots = {}
    for i in range(256):
        roots[i] = t.update(-1, i)

    bw = BitBE()
    if not data:
        return b""
    cur = roots[data[0]]
    for b in data[1:]:
        nxt = t.index_of.get((cur, b))
        if nxt is not None:
            cur = nxt
            continue
        bw.bits(cur, 12)
        if numfree:
            t.update(cur, b)
            numfree -= 1
        cur = roots[b]
    bw.bits(cur, 12)
    return bw.flush()

# ------------------------------------------------------------ compress

def compress_encode(data, maxbits):
    """Methods 8 and 9 are Unix compress in block mode, which the
    decoder runs through unc_lzw.c. The width grows when the table size
    reaches a power of two, and code 256 is reserved for the clear that
    this encoder never emits (the table simply stops growing) — mirrors
    unc_lzw_read's own rule so the two stay in step.

    Bits are LSB-first, which is compress's one departure from
    everything else in the classic Mac world."""
    out = bytearray()
    cur = 0
    nbits = 0

    def emit(code, width):
        nonlocal cur, nbits
        cur |= code << nbits
        nbits += width
        while nbits >= 8:
            out.append(cur & 0xFF)
            cur >>= 8
            nbits -= 8

    maxsymbols = 1 << maxbits
    table = {}
    width = 9
    nsym = 257                        # the DECODER's table size
    emitted = 0

    def put(code):
        """Emit one code, then age the decoder's table by exactly what
        reading that code will do to it. The decoder adds an entry per
        code EXCEPT the first, so an encoder that adds on every code
        runs one entry ahead and widens one code early — which is
        precisely how this was wrong the first time: our decoder and
        `unar` both rejected the stream, agreeing with each other."""
        nonlocal width, nsym, emitted
        emit(code, width)
        emitted += 1
        if emitted >= 2 and nsym < maxsymbols:
            nsym += 1
            if nsym < maxsymbols and (nsym & (nsym - 1)) == 0:
                width += 1

    if not data:
        return b""
    prev = data[0]
    for b in data[1:]:
        key = (prev, b)
        if key in table:
            prev = table[key]
            continue
        put(prev)
        # The entry the decoder will create when it reads the NEXT code
        # lands at index 256 + (codes emitted so far).
        index = 256 + emitted
        if index < maxsymbols:
            table[key] = index
        prev = b
    put(prev)
    if nbits:
        out.append(cur & 0xFF)
    return bytes(out)

# --------------------------------------------------------------- ARC

def header(method, name, comp, uncomp, crc, mtime=(0x5B21, 0x7000)):
    """Source: XADARCParser.m — 0x1a, method, 13-byte name, u32le
    compressed size, u16le date, u16le time, u16le CRC, u32le size."""
    nb = name.encode('ascii')[:12] + b'\0'
    nb = nb + b'\0' * (13 - len(nb))
    h = bytes([0x1A, method]) + nb + struct.pack('<I', comp)
    h += struct.pack('<HH', mtime[0], mtime[1]) + struct.pack('<H', crc)
    if method != 1:
        h += struct.pack('<I', uncomp)
    return h


def entry(method, name, data):
    if method == 1 or method == 2:
        payload = data
    elif method == 3:
        payload = rle90_encode(data)
    elif method == 4:
        payload = squeeze_encode(rle90_encode(data))
    elif method == 5:
        payload = crunch_encode(data, False)
    elif method == 6:
        payload = crunch_encode(rle90_encode(data), False)
    elif method == 7:
        payload = crunch_encode(rle90_encode(data), True)
    elif method == 8:
        payload = b"\x0c" + compress_encode(rle90_encode(data), 12)
    elif method == 9:
        payload = compress_encode(data, 13)
    else:
        raise SystemExit("synth_arc: method %d is not generated here" % method)
    return header(method, name, len(payload), len(data), crc16(data)) + payload


def build(path, items):
    """items: [(method, name, bytes)] — plus the end marker."""
    out = bytearray()
    for method, name, data in items:
        out += entry(method, name, data)
    out += b'\x1a\x00'
    with open(path, 'wb') as f:
        f.write(bytes(out))


def sample_data():
    """Content chosen so every stage does something: runs for RLE90, a
    skewed alphabet for the Huffman tree, repeats for LZW."""
    text = (b"the quick brown fox jumps over the lazy dog. " * 40)
    runs = b"A" * 300 + b"\x90" * 4 + b"B" * 700 + b"mixed" * 50
    tiny = b"hello hello hello\n"
    return {"text.txt": text, "runs.bin": runs, "tiny.txt": tiny}


def main():
    data = sample_data()

    # `-o <file>` writes the one archive committed as a fixture, which is
    # the form fixtures/SOURCES.md restores with (harvest.py: "the script
    # must accept -o <path> and be deterministic"). Without it that line
    # could not be restored at all.
    if len(sys.argv) == 3 and sys.argv[1] == "-o":
        build(sys.argv[2], [(m, "m%d.bin" % m, data["text.txt"])
                            for m in (1, 2, 3, 4, 5, 6, 7, 8, 9)])
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: synth_arc.py <outdir> | "
                         "synth_arc.py -o <file>")
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)

    made = []
    for method in (1, 2, 3, 4, 5, 6, 7, 8, 9):
        path = os.path.join(out, "synth-arc-m%d.arc" % method)
        build(path, [(method, n, d) for n, d in data.items()])
        made.append(path)

    # One archive holding every generated method at once, which is what
    # a real ARC looks like: arc picks per file.
    path = os.path.join(out, "synth-arc-mixed.arc")
    build(path, [(m, "m%d.bin" % m, data["text.txt"])
                 for m in (1, 2, 3, 4, 5, 6, 7, 8, 9)])
    made.append(path)

    for p in made:
        print(p)


if __name__ == "__main__":
    main()

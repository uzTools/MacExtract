#!/usr/bin/env python3
"""sdhuff.py — SuperDisk!'s Huffman region, in Python, for MEASURING.

`src/fmt_superdisk.c` decodes this region; what it never reports is how
many BITS the region cost. That number is the whole of one open question:
a region's neighbour starts at the bit reader's cursor plus two, the
cursor moves in 32-bit refills, and when a region ends EXACTLY on a
refill the 1991 self-extractor and the 1992 Add-In Module part company
over where the next one begins (FORMATS.md, the method table).

So this transcribes the same reader and counts. Source, in both cases:
`src/fmt_superdisk.c` — `sd_huff_start`, `sd_huff_bit`, `sd_huff_next`,
`sd_huff_end` and `sd_block_head` — which came from CODE 2 of the 1991
self-extractor.

What the counting found (2026-08-28), and it was written down the other
way round for three days: **the panel codes each flag BYTE, not each flag
bit.** A byte of 0xff — eight predictions right — is one bit; this
subject family's five other flag bytes are two bits each. So a bitmap of
`nflags` bytes costs `nflags + 5` bits, which is a function of the
SUBJECT SIZE and can be aimed at a refill boundary.
"""
import struct


def u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


class Region:
    """One Huffman region. `bits` is what it cost once it is drained."""

    def __init__(self, src, at):
        self.src = src
        self.bits = 0
        self.acc = 0
        self.nbits = 0
        self.lengths = []
        if u16(src, at) == 0xFFFF:            # a single repeated value
            self.run = True
            self.runval = u16(src, at + 2)
            self.left = u16(src, at + 4)
            self.pos = at + 8
            return
        self.run = False
        self.left = u16(src, at)
        self.startbits = src[at + 2]
        self.sym = at + 8
        self.pos = at + u16(src, at + 4)
        ct = at + 10 + u16(src, at + 6)
        self.lim = []
        d0 = u16(src, ct)
        i = 0
        while True:
            self.lim.append(d0)
            d0 = (d0 * 2) & 0xFFFFFFFF
            prev = u16(src, ct + i * 2)
            nxt = struct.unpack_from(">h", src, ct + (i + 1) * 2)[0]
            if nxt < 0:
                break
            d0 = (d0 + (nxt - prev)) & 0xFFFFFFFF
            i += 1
        self.lim.append(0xFFFF0000)

    def _bit(self):
        if self.nbits == 0:
            self.acc = u32(self.src, self.pos)
            self.pos += 4
            self.nbits = 32
        b = self.acc >> 31
        self.acc = (self.acc << 1) & 0xFFFFFFFF
        self.nbits -= 1
        self.bits += 1
        return b

    def next(self):
        self.left -= 1
        if self.run:
            return self.runval
        was = self.bits
        code = base = 0
        limit = self.lim[0]
        for _ in range(self.startbits):
            code = (code << 1) | self._bit()
        i = 1
        while code >= limit:
            code = (code << 1) | self._bit()
            base += limit
            limit = self.lim[i]
            i += 1
        self.lengths.append(self.bits - was)
        return self.src[self.sym + (code - base)]

    def end(self):
        """Where the next region begins, the 1991 reading (`sd_huff_end`)."""
        return self.pos if self.run else self.pos + 2


def nflags_for(ulen):
    """How many flag BYTES a coded bitmap carries: one bit per output
    byte, capped by the stored form's size (`sd_block_body`)."""
    return min((ulen + 7) >> 3, ((ulen >> 3) + 4) & ~1)


def flag_bits(body, ulen):
    """Measure one block's flag bitmap.

    `body` is the block past its 6-byte header, `ulen` its output length.
    Returns a dict: `run` (the region is a repeat, so it costs no bits),
    `nflags`, `bits`, and `boundary` — the region ended exactly on a
    32-bit refill, which is the case the two references read differently.
    """
    n = nflags_for(ulen)
    r = Region(body, 0)
    if r.run:
        return {"run": True, "nflags": n, "bits": 0, "boundary": False,
                "flags": [r.runval] * n}
    flags = [r.next() for _ in range(n)]
    return {"run": False, "nflags": n, "bits": r.bits,
            "boundary": r.bits % 32 == 0, "flags": flags}


def block_head(d, at):
    """(clen, ulen, method, stored) — `sd_block_head`."""
    n = u16(d, at)
    if n & 0x8000:
        if n == 0x8002:
            return 0x8002, 0x8000, 0, True
        n &= 0x7FFF
        return n, n - 2, 0, True
    return n, u16(d, at + 2), d[at + 5], False


def blocks(d, at, want):
    """Walk one fork's block chain: (offset, clen, ulen, method, stored)."""
    done = 0
    while done < want:
        clen, ulen, meth, stored = block_head(d, at)
        if ulen > want - done:
            ulen = want - done
        yield at, clen, ulen, meth, stored
        done += ulen
        at += clen


def single_forks(d):
    """(first block offset, data length, resource length) for the
    single-file container the control panel writes."""
    dlen, rlen = struct.unpack_from(">II", d, 4)
    at = 31 + d[30]
    if at & 1:
        at += 1
    return at, dlen, rlen


def coded_bitmap(method):
    """Methods whose flag bitmap is Huffman-coded: 2 and 4, and the same
    two over a 16-bit context (6 and 8)."""
    return method in (2, 4, 6, 8)


def measure_single(path):
    """Every coded flag bitmap in one single-file container."""
    d = open(path, "rb").read()
    at, dlen, rlen = single_forks(d)
    out = []
    for want in (dlen, rlen):
        if not want:
            continue
        for off, clen, ulen, meth, stored in blocks(d, at, want):
            if not stored and coded_bitmap(meth):
                m = flag_bits(d[off + 6:off + clen], ulen)
                m["ulen"] = ulen
                m["method"] = meth
                m.pop("flags")
                out.append(m)
        for off, clen, _u, _m, _s in blocks(d, at, want):
            at = off + clen
    return out


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        for m in measure_single(p):
            print("%-44s method %d ulen %5d flags %4d %s"
                  % (p.split("/")[-1], m["method"], m["ulen"], m["nflags"],
                     "RUN, no bits" if m["run"] else
                     "%d bits, %%32=%d%s" % (m["bits"], m["bits"] % 32,
                                             "  ON THE BOUNDARY"
                                             if m["boundary"] else "")))

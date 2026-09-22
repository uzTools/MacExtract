#!/usr/bin/env python3
"""synth_sit6.py — deterministic synthetic StuffIt method 6 fixture.

Method 6 ("fixed Huffman") occurs exactly once in the harvested corpus:
one 34,818-byte resource fork in derived-INITLoader.sit, made of two
Huffman-coded segments. That fork therefore exercises neither the STORED
segment (a negative segment size, PackBits with no Huffman layer) nor
several PackBits control bytes — no 0x80 filler, no shortest run, no
segment boundary falling inside a run. This generates an archive that
does, so those paths are checked against a reference implementation
rather than against our own unit tests.

The oracle for this fixture is macunpack AND deark, not unar: The
Unarchiver recognizes method 6 and refuses it (TESTING.md, "A second
oracle" and "A third oracle").

Container layout and the method byte come from the same sources as the
parser in src/fmt_sit.c. The segment framing and the PackBits semantics
come from docs/formats/stuffit-method-6.md, this project's own note,
written against reference/deark/modules/stuffit.c (MIT) — they came
from reference/macutils/macunpack/sit.c until 2026-09-22; the code tree
is built from the 26 bytes in src/sit6_tables.h the same way
src/fmt_sit.c's sit6_build builds it — the header stopped carrying the
expanded tree on 2026-09-21. It used to be derived
from that same file, so this script does not need reference/ present.

Deterministic: no randomness, no timestamps. Provenance in SOURCES.md as
`synthetic:tools/synth_sit6.py`.

Usage: synth_sit6.py -o fixtures/synth-sit-fixhuf.sit
"""
import argparse, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.path.join(HERE, "..", "src", "sit6_tables.h")

CRC16_ARC_POLY = 0xA001
LEAVES = 258
TERMINATOR = 257            # leaf ordinals 257 and 258 both end a segment


def crc16_arc(data, crc=0):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ CRC16_ARC_POLY if crc & 1 else crc >> 1
    return crc & 0xFFFF


def runlengths():
    """The 13 (count, bits) pairs `src/sit6_tables.h` states the fixed
    code book as, so the 26 bytes are written down once and this reads
    the same copy the engine compiles."""
    text = open(TABLES).read()
    out = {}
    for m in re.finditer(r"static const uint8_t (\w+)\[SIT6_RUNS\]"
                         r"\s*=\s*\{(.*?)\};", text, re.S):
        out[m.group(1)] = [int(v) for v in re.findall(r"\d+", m.group(2))]
    return list(zip(out["sit6_runlen"], out["sit6_runbits"]))


def build_tree():
    """{leaf ordinal: bit string}, built the way `sit6_build` builds it.

    Expand the run-lengths to 257 code lengths, then give each symbol in
    turn the code that follows the one before it — shift left when
    longer, shift right and add one when shorter, add one when equal.
    The leaf ordinal is the symbol plus one, and the terminator gets the
    thirteenth bit macunpack's tree spends on it, reaching ordinal 257
    or 258 (docs: src/sit6_tables.h).
    """
    lens = []
    for count, bits in runlengths():
        lens += [bits] * count
    codes, prev, prevlen = {}, 0, 0
    for sym, ln in enumerate(lens):
        if prevlen == 0:
            cur = 0
        elif ln < prevlen:
            cur = (prev >> (prevlen - ln)) + 1
        else:
            cur = (prev + 1) << (ln - prevlen)
        prev, prevlen = cur, ln
        codes[sym + 1] = format(cur, "0%db" % ln)
    term = codes.pop(LEAVES - 1)          # symbol 256: the terminator
    codes[LEAVES - 1] = term + "0"
    codes[LEAVES] = term + "1"
    assert len(codes) == LEAVES, len(codes)
    return codes


CODES = build_tree()


# --- PackBits ---------------------------------------------------------
# Source: docs/formats/stuffit-method-6.md, *PackBits, once per
# block*. n < 0x80 introduces n + 1 literals,
# n == 0x80 is a no-op, and n > 0x80 repeats the next byte 0x101 - n
# times. The generator emits these shapes explicitly rather than running
# a compressor, because the point is to cover the control bytes the real
# fixture never uses.

def literals(data):
    out = bytearray()
    for i in range(0, len(data), 128):
        chunk = data[i:i + 128]
        out.append(len(chunk) - 1)
        out += chunk
    return bytes(out)


def run(value, count):
    """One run token. count must be 2..128 (0x101 - n for n in 0xFF..0x81)."""
    assert 2 <= count <= 128, count
    return bytes((0x101 - count, value))


FILLER = bytes((0x80,))     # a control byte that produces nothing


def unpackbits(seg):
    """The decoder these tokens are written against; used by the selftest
    so the generator cannot agree only with itself."""
    out, p = bytearray(), 0
    while p < len(seg):
        n = seg[p]; p += 1
        if n < 0x80:
            out += seg[p:p + n + 1]; p += n + 1
        elif n != 0x80:
            out += bytes([seg[p]]) * (0x101 - n); p += 1
    return bytes(out)


# --- Huffman segment --------------------------------------------------

def huff_segment(pb):
    """Code one PackBits stream with the fixed tree. The segment names
    the bytes it uses in frequency order, so the commonest byte gets
    leaf ordinal 1 — the shortest code, exactly as a real encoder would
    use the fixed weights."""
    freq = {}
    for b in pb:
        freq[b] = freq.get(b, 0) + 1
    alphabet = sorted(freq, key=lambda b: (-freq[b], b))
    assert len(alphabet) <= LEAVES - 2, "too many distinct bytes"
    ordinal = {b: i + 1 for i, b in enumerate(alphabet)}

    bits = "".join(CODES[ordinal[b]] for b in pb) + CODES[TERMINATOR]
    bits += "0" * (-len(bits) % 8)          # pad: never decoded, the
    stream = bytes(int(bits[i:i + 8], 2)    # terminator comes first
                   for i in range(0, len(bits), 8))

    body = struct.pack(">IH", len(pb), len(alphabet)) + bytes(alphabet) + stream
    return struct.pack(">i", len(body) + 4) + body


def stored_segment(pb):
    """A negative size means the PackBits stream is stored as-is."""
    return struct.pack(">i", -(len(pb) + 4)) + pb


# --- Cases ------------------------------------------------------------
# Each case is (name, data-fork segments, resource-fork segments), where a
# segment is (kind, packbits bytes). Both forks are method 6 so the
# resource side of the decoder is exercised too.

def cases():
    alpha = bytes(range(0x20, 0xA0))
    return [
        # The branch the real fixture never takes: stored segments only.
        ("Stored only", [
            ("stored", literals(b"stored segment, no Huffman layer\n")),
            ("stored", run(0x2A, 128) + literals(b"|") + run(0x2D, 2)),
        ], [
            ("stored", literals(b"r") + FILLER + run(0x00, 64)),
        ]),
        # Stored and Huffman segments in one fork, in both orders.
        ("Mixed segments", [
            ("stored", literals(b"first segment is stored\n")),
            ("huff", literals(b"second is Huffman coded\n") + run(0x2E, 40)),
            ("stored", run(0x21, 3)),
        ], [
            ("huff", literals(alpha) + run(0xFF, 100)),
            ("stored", literals(b"tail")),
        ]),
        # Every PackBits control-byte edge: the longest literal block
        # (0x7F), a single literal (0x00), the longest run (0x81), the
        # shortest run (0xFF), and fillers between them.
        ("Control bytes", [
            ("huff", literals(bytes(range(128))) + FILLER +
                     literals(b"x") + FILLER + FILLER +
                     run(0x5A, 128) + run(0x5B, 2) +
                     literals(bytes(range(128, 256)))),
        ], [
            ("stored", FILLER + run(0x90, 2) + FILLER +
                       literals(bytes(range(128))) + run(0x90, 128)),
        ]),
        # A one-byte alphabet (the whole segment is one repeated code)
        # and a 254-byte one, near the most a segment can name.
        ("Alphabet edges", [
            ("huff", run(0x81, 128) * 8),
        ], [
            ("huff", literals(bytes(range(1, 255)))),
        ]),
        # Many small segments, so the segment loop runs more times than
        # the two of the real fixture.
        ("Many segments", [
            (("huff" if i % 2 else "stored"),
             literals(b"segment %02d\n" % i) + run(0x20, i + 2))
            for i in range(12)
        ], [
            ("stored", literals(b"s")),
        ]),
    ]


def fork_bytes(segments):
    """The encoded fork, and what it decodes to."""
    enc, out = bytearray(), bytearray()
    for kind, pb in segments:
        enc += stored_segment(pb) if kind == "stored" else huff_segment(pb)
        out += unpackbits(pb)
    return bytes(enc), bytes(out)


def entry_header(name, rsrc, data, rcomp, dcomp):
    h = bytearray(112)
    h[0] = 6                                    # rsrc method: fixed Huffman
    h[1] = 6                                    # data method: fixed Huffman
    nb = name.encode("mac_roman")
    assert len(nb) <= 31
    h[2] = len(nb)
    h[3:3 + len(nb)] = nb
    h[66:74] = b"TEXTttxt"                      # type + creator
    struct.pack_into(">I", h, 84, len(rsrc))
    struct.pack_into(">I", h, 88, len(data))
    struct.pack_into(">I", h, 92, len(rcomp))
    struct.pack_into(">I", h, 96, len(dcomp))
    struct.pack_into(">H", h, 100, crc16_arc(rsrc))
    struct.pack_into(">H", h, 102, crc16_arc(data))
    struct.pack_into(">H", h, 110, crc16_arc(bytes(h[:110])))
    return bytes(h)


def build():
    body = bytearray()
    entries = cases()
    for name, dsegs, rsegs in entries:
        dcomp, data = fork_bytes(dsegs)
        rcomp, rsrc = fork_bytes(rsegs)
        body += entry_header(name, rsrc, data, rcomp, dcomp)
        body += rcomp + dcomp                   # rsrc fork first
    out = bytearray(22)
    out[0:4] = b"SIT!"
    struct.pack_into(">H", out, 4, len(entries))
    struct.pack_into(">I", out, 6, 22 + len(body))
    out[10:14] = b"rLau"
    struct.pack_into(">I", out, 16, 22)         # header size
    return bytes(out) + bytes(body)


def selftest():
    """Decode every segment back the way sit_fixhuf does — walking the
    tree bit by bit — and check it reproduces the PackBits stream. An
    encoder that agrees only with itself proves nothing."""
    rev = {v: k for k, v in CODES.items()}
    for name, dsegs, rsegs in cases():
        for segs in (dsegs, rsegs):
            for kind, pb in segs:
                if kind == "stored":
                    assert stored_segment(pb)[4:] == pb
                    continue
                enc = huff_segment(pb)
                explen, ncodes = struct.unpack(">IH", enc[4:10])
                alphabet = enc[10:10 + ncodes]
                bits = "".join(format(b, "08b") for b in enc[10 + ncodes:])
                got, prefix = bytearray(), ""
                for c in bits:
                    prefix += c
                    if prefix not in rev:
                        continue
                    leaf = rev[prefix]
                    prefix = ""
                    if leaf >= TERMINATOR:
                        break
                    got.append(alphabet[leaf - 1])
                assert bytes(got) == pb, f"{name}: encoder is not an inverse"
                assert explen == len(pb), (explen, len(pb))
                assert prefix == "", f"{name}: terminator not reached"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()
    selftest()
    with open(args.output, "wb") as f:
        f.write(build())
    return 0


if __name__ == "__main__":
    sys.exit(main())

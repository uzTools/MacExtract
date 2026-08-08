#!/usr/bin/env python3
"""synth_sit1.py — deterministic synthetic StuffIt method 1 (RLE90) fixture.

Method 1 occurs exactly once in the harvested corpus: one 470-byte
resource fork in derived-New_Python.sit, which the oracle does
adjudicate (see DECISIONS.md, 2026-08-08). That fork exercises 25 run
escapes and one literal-0x90 escape, and nothing else — no run OF 0x90,
no maximum-length run, no run ending the output. This generates an
archive that does, so those paths are checked against unar rather than
against our own unit tests.

Container layout and the method byte come from the same sources as the
parser in src/fmt_sit.c: reference/XADMaster/XADStuffItParser.m and
reference/macutils/macunpack/sit.c. RLE90 itself is the inverse of
XADRLE90Handle.m: 0x90 introduces a token, a following 0 means a
literal 0x90, and a following c >= 2 means the previous byte stands for
c bytes in total (c == 1 is invalid).

Deterministic: no randomness, no timestamps. Provenance in SOURCES.md
as `synthetic:tools/synth_sit1.py`.

Usage: synth_sit1.py -o fixtures/synth-sit-rle90.sit
"""
import argparse, struct, sys

CRC16_ARC_POLY = 0xA001


def crc16_arc(data, crc=0):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ CRC16_ARC_POLY if crc & 1 else crc >> 1
    return crc & 0xFFFF


def rle90_runs(data):
    """Split data into (byte, count) runs."""
    runs, i = [], 0
    while i < len(data):
        j = i
        while j < len(data) and data[j] == data[i]:
            j += 1
        runs.append((data[i], j - i))
        i = j
    return runs


def rle90_encode(data, min_run=3):
    """Encode to RLE90. min_run tunes when a run token is preferred over
    plain literals, which is how the max-length and short-run tokens are
    forced into the stream deliberately."""
    out = bytearray()

    def literal(v):
        out.append(v)
        if v == 0x90:
            out.append(0x00)          # 0x90 0x00 == one literal 0x90

    for value, count in rle90_runs(data):
        while count:
            # A token can express at most 255 bytes in total, including
            # the literal that seeds it.
            n = min(count, 255)
            if n >= min_run:
                literal(value)
                out += bytes((0x90, n))
                count -= n
            else:
                for _ in range(count):
                    literal(value)
                count = 0
    return bytes(out)


# Each case is (name, data-fork payload, resource-fork payload). Both
# forks are method 1, so the resource side of the decoder is exercised
# too — the one real fixture only has method 1 on its resource fork.
def cases():
    return [
        # A run longer than one token can express, so the decoder must
        # pick up a second token for the same byte value.
        ("Long run", b"A" * 300 + b"tail", b"B" * 512),
        # Runs OF the escape byte, and a literal 0x90 next to one.
        ("Escape runs", bytes([0x90]) * 7 + b"x" + bytes([0x90]) +
                        b"y" + bytes([0x90]) * 2,
         bytes([0x90, 0x90, 0x41, 0x90]) + b"z" * 4),
        # A run of exactly 255 — the largest a single token can carry —
        # immediately followed by another.
        ("Max run", b"\xff" * 255 + b"\x00" * 255,
         b"M" * 255 + bytes([0x90]) * 255),
        # Output that ENDS in a run, so the decoder finishes inside a
        # token rather than on a literal.
        ("Trailing run", b"header:" + b"=" * 64, b"." * 40),
        # No runs at all: every byte a literal, including 0x90 twice.
        ("All literals", bytes(range(256)), bytes(range(255, -1, -1))),
        # Shortest legal token (c == 2) and a one-byte fork.
        ("Short run", b"aabbccdd", b"q"),
    ]


def entry_header(name, rsrc, data, rcomp, dcomp):
    h = bytearray(112)
    h[0] = 1                                    # rsrc method: RLE90
    h[1] = 1                                    # data method: RLE90
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
    for name, data, rsrc in entries:
        # min_run 2 on the last case forces the shortest legal token.
        mr = 2 if name == "Short run" else 3
        rcomp = rle90_encode(rsrc, mr)
        dcomp = rle90_encode(data, mr)
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
    """The encoder must be the inverse of the decoder it is written
    against; a generator that agrees only with itself proves nothing."""
    for name, data, rsrc in cases():
        for payload in (data, rsrc):
            enc = rle90_encode(payload, 2 if name == "Short run" else 3)
            dec, i, prev = bytearray(), 0, None
            while i < len(enc):
                b = enc[i]; i += 1
                if b != 0x90:
                    dec.append(b); prev = b
                    continue
                c = enc[i]; i += 1
                if c == 0:
                    dec.append(0x90); prev = 0x90
                else:
                    assert c >= 2, "c == 1 is not a legal token"
                    dec += bytes([prev]) * (c - 1)
            assert bytes(dec) == payload, f"{name}: encoder is not an inverse"


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

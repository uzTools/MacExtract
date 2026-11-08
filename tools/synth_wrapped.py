#!/usr/bin/env python3
"""synth_wrapped.py — put each part of a segmented set in its own envelope.

A real download is not a bare set of parts. It is Archive.sit.1.hqx,
Archive.sit.2.hqx, ... : every part BinHex- or MacBinary-encoded on its
own, because that is what carried a Macintosh file over a 7-bit network.
Nothing in the harvested corpus has that shape (the corpus has no
segmented archive at all — synth_sitsplit.py), so the fixtures for it
are generated here and wrapped around the parts that module produces.

Two envelopes, both layouts transcribed from the reference the matching
decoder cites and from nowhere else:

  MacBinary II  Source: reference/XADMaster/XADMacArchiveParser.m
                (+macBinaryVersionForHeader:), as read by
                src/fmt_macbinary.c — 128-byte header, then each fork
                padded to a 128-byte boundary. The version-2 header CRC
                at offset 124 is CRC-16/XMODEM over bytes 0..123.

  BinHex 4.0    Source: reference/XADMaster/XADBinHexParser.m, as read
                by src/fmt_binhex.c — banner line, ':', then a 6-bit
                encoding of: namelen, name, version, type, creator,
                flags, datalen, rsrclen, header CRC, data fork, its
                CRC, resource fork, its CRC. Every CRC is
                CRC-16/XMODEM with init 0.

The 0x90 run-length marker is only ever used to escape a literal 0x90
(as 0x90 0x00). Runs are legal and are not emitted: an encoder is free
not to compress, and the shortest correct encoder is the one least able
to be wrong about a format this file must not invent.

Deterministic: no randomness, no timestamps.

Usage:
    synth_wrapped.py --envelope hqx --in DIR --out DIR
"""
import argparse, os, struct, sys

# Arbitrary but fixed, and deliberately NOT the type of what is inside:
# a wrapper says nothing about its payload, and nothing here may read it.
TYPE, CREATOR = b"????", b"????"
CREATED, MODIFIED = 0xA8B4C1E0, 0xA8B4C2F0


def crc16_xmodem(data, crc=0):
    """CRC-16/XMODEM: poly 0x1021, init 0, no reflection, no final xor.
    The same function src/unc_util.c implements for the decoders."""
    for ch in data:
        crc ^= ch << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 \
                else (crc << 1) & 0xFFFF
    return crc


def pad128(b):
    return b"\0" * ((-len(b)) % 128)


def macbinary(name, data, rsrc=b"", ftype=TYPE, creator=CREATOR):
    """MacBinary II: 128-byte header + padded data fork + padded rsrc."""
    n = name.encode("mac_roman")
    if not 1 <= len(n) <= 63:
        raise ValueError("name length must be 1..63")
    h = bytearray(128)
    h[1] = len(n)
    h[2:2 + len(n)] = n
    h[65:69] = ftype
    h[69:73] = creator
    struct.pack_into(">I", h, 83, len(data))
    struct.pack_into(">I", h, 87, len(rsrc))
    struct.pack_into(">I", h, 91, CREATED)
    struct.pack_into(">I", h, 95, MODIFIED)
    struct.pack_into(">H", h, 124, crc16_xmodem(bytes(h[:124])))
    return bytes(h) + data + pad128(data) + rsrc + pad128(rsrc)


BH_ALPHABET = ("!\"#$%&'()*+,-012345689@ABCDEFGHIJKLMNPQRSTUVXYZ[`"
               "abcdefhijklmpqr")
BH_BANNER = "(This file must be converted with BinHex 4.0)"


def _bh_rle(b):
    """Escape the marker; emit no runs (see the module docstring)."""
    out = bytearray()
    for ch in b:
        out.append(ch)
        if ch == 0x90:
            out.append(0x00)
    return bytes(out)


def _bh_6bit(b):
    """Pack to 6-bit codes, zero-padding the last group."""
    bits = "".join(format(ch, "08b") for ch in b)
    bits += "0" * ((-len(bits)) % 6)
    return "".join(BH_ALPHABET[int(bits[i:i + 6], 2)]
                   for i in range(0, len(bits), 6))


def binhex(name, data, rsrc=b"", ftype=TYPE, creator=CREATOR, flags=0):
    n = name.encode("mac_roman")
    if not 1 <= len(n) <= 63:
        raise ValueError("name length must be 1..63")
    head = bytes([len(n)]) + n + b"\0" + ftype + creator + \
        struct.pack(">HII", flags, len(data), len(rsrc))
    stream = head + struct.pack(">H", crc16_xmodem(head)) + \
        data + struct.pack(">H", crc16_xmodem(data)) + \
        rsrc + struct.pack(">H", crc16_xmodem(rsrc))
    body = _bh_6bit(_bh_rle(stream))
    lines = [body[i:i + 64] for i in range(0, len(body), 64)] or [""]
    return (BH_BANNER + "\n:" + "\n".join(lines) + ":\n").encode("ascii")


ENVELOPES = {
    "bin": (macbinary, ".bin"),
    "hqx": (binhex, ".hqx"),
}


def wrap_file(src, destdir, envelope, dest_name=None):
    """Wrap one file, keeping its name inside the envelope. Returns the
    path written. The wrapper's own filename is the payload's plus the
    envelope's extension, which is the convention every one of these
    downloads followed — and which nothing in the reader relies on."""
    fn, ext = ENVELOPES[envelope]
    with open(src, "rb") as f:
        data = f.read()
    inner = os.path.basename(src)
    out = os.path.join(destdir, (dest_name or inner) + ext)
    with open(out, "wb") as f:
        f.write(fn(inner, data))
    return out


def wrap_dir(srcdir, destdir, envelope, per_part=None, rename=None):
    """Wrap every file of srcdir into destdir.

    per_part: {basename: envelope} overriding the envelope for one part,
    so a set can be mixed — which is not a curiosity but the normal
    result of collecting parts from more than one place.
    rename: {basename: new base name}, for proving that the wrapper's
    name is not what places a part.
    """
    os.makedirs(destdir, exist_ok=True)
    written = []
    for name in sorted(os.listdir(srcdir)):
        src = os.path.join(srcdir, name)
        if not os.path.isfile(src):
            continue
        env = (per_part or {}).get(name, envelope)
        written.append(wrap_file(src, destdir, env,
                                 (rename or {}).get(name)))
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--envelope", choices=sorted(ENVELOPES), default="hqx")
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    a = ap.parse_args()
    for p in wrap_dir(a.src, a.dst, a.envelope):
        print(os.path.basename(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())

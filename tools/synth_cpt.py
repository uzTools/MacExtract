#!/usr/bin/env python3
"""synth_cpt.py — a minimal Compact Pro writer, with and without encryption.

Compact Pro's encryption is the one scheme here that no reference
implementation reads: The Unarchiver's own format notes say "the
algorithm for this is unknown", macutils skips the file, and CptExpand
refuses it in as many words. src/unc_crypt.c reads it out of Compact
Pro 1.51's own code (DECISIONS.md 2026-08-23), and a reading like that
is a hypothesis until the application itself grades it.

That is what this exists for, and it did: the archives it writes are
handed to Compact Pro 1.51 under Mini vMac (tools/vmac/cptcrypt.py),
which extracts them with its own CRC over both decrypted forks passing
— the same arrangement that graded DiskDoubler methods 3, 4 and 5
against Salient's own expander. The other direction is graded too, and
is the stronger one: `cptcrypt.py --make` has the application encrypt
known subjects for this engine to read back.

Only the RLE method is written (flags bits 1 and 2 clear). That is a
real Compact Pro method, it is what the reader calls method 0, and it
keeps the container honest without a second encoder to be wrong about.
The UNencrypted output is checked by `unar` and by us, so everything
except the cipher is graded on this side of the world.

Usage: synth_cpt.py -o out.cpt [--password PW]
"""
import argparse
import struct
import sys

ESC1, ESC2 = 0x81, 0x82
POLY64 = 0xEDB88320


def crc32(data, crc=0xFFFFFFFF):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
    return crc & 0xFFFFFFFF


def rle_encode(data):
    """The inverse of the decoder in src/fmt_cpt.c. No runs are emitted:
    an encoder is free not to compress, and 0x81 0x82 0x00 is the one
    escape a literal stream needs."""
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] == ESC1 and i + 1 < len(data) and data[i + 1] == ESC2:
            out += bytes([ESC1, ESC2, 0])
            i += 2
        else:
            out.append(data[i])
            i += 1
    return bytes(out)


# ---------------------------------------------------------------------------
# The cipher, as read out of Compact Pro 1.51 `CODE` 3. Encrypting is the
# same register with the roles of the two bytes swapped.
# ---------------------------------------------------------------------------

def crc64_table():
    rows = []
    for i in range(256):
        hi = lo = 0
        v = i
        for _ in range(8):
            fb = (lo ^ v) & 1
            lo = (lo >> 1) | ((hi & 1) << 31)
            hi >>= 1
            if fb:
                hi ^= POLY64
                lo ^= POLY64
            v >>= 1
        rows.append((hi, lo))
    return rows


T = crc64_table()


class CptCipher:
    def __init__(self, password):
        key = bytearray(9)
        for i, b in enumerate(password):
            key[(i & 7) + 1] = (key[(i & 7) + 1] + b) & 0xFF
        key[0] = min(len(password), 8)
        self.hi, self.lo = 0x01234567, 0x89ABCDEF
        for i in range(1, key[0] + 1):
            self._step(key[i])

    def _step(self, plain):
        idx = (plain ^ (self.lo & 0xFF)) & 0xFF
        lo = (((self.hi << 24) | (self.lo >> 8)) ^ T[idx][1]) & 0xFFFFFFFF
        self.hi = ((self.hi >> 8) ^ T[idx][0]) & 0xFFFFFFFF
        self.lo = lo

    def encrypt(self, data):
        out = bytearray()
        for b in data:
            out.append(b ^ ((self.lo >> 8) & 0xFF))
            self._step(b)
        return bytes(out)

    def decrypt(self, data):
        out = bytearray()
        for b in data:
            p = b ^ ((self.lo >> 8) & 0xFF)
            out.append(p)
            self._step(p)
        return bytes(out)


# ---------------------------------------------------------------------------

CASES = [
    # name, type, creator, data fork, resource fork
    ("Plain Text", b"TEXT", b"ttxt",
     b"Compact Pro encrypted this, and only Compact Pro can say so.\r" * 4,
     b""),
    ("Two Forks", b"BINA", b"CPCT",
     bytes((i * 7 + 3) & 0xFF for i in range(600)),
     bytes(range(256)) + b"\x81\x82\x81\x82" * 8),
    ("Rsrc Only", b"rsrc", b"RSED", b"", b"resource bytes " * 20),
]


def build(password=None):
    body = bytearray()
    entries = []
    for name, ftype, creator, data, rsrc in CASES:
        rc = rle_encode(rsrc)
        dc = rle_encode(data)
        crc = crc32(rsrc)
        crc = crc32(data, crc)
        if password is not None:
            # One cipher per ENTRY, running across the resource fork and
            # then the data fork without resetting — and opening with
            # EIGHT bytes that the reader decrypts and discards. They
            # are a salt: the register steps on them, so two entries
            # with the same password and the same content still encrypt
            # differently. Compact Pro writes eight random ones; these
            # are derived from the entry index so the fixture is
            # reproducible. The eight are counted in the compressed
            # length of the first fork that has any bytes.
            c = CptCipher(password)
            salt = bytes((i * 37 + len(entries) * 11 + 5) & 0xFF
                         for i in range(8))
            head = c.encrypt(salt)
            rc = c.encrypt(rc)
            dc = c.encrypt(dc)
            if rc:
                rc = head + rc
            else:
                dc = head + dc
        entries.append((name, ftype, creator, len(body), rc, dc,
                        len(rsrc), len(data), crc))
        body += rc + dc

    index = bytearray()
    index += struct.pack(">H", len(CASES))
    index += b"\x00"                                    # no comment
    for (name, ftype, creator, off, rc, dc, rlen, dlen, crc) in entries:
        nb = name.encode("mac_roman")
        index.append(len(nb))
        index += nb
        meta = bytearray()
        meta.append(1)                                  # volume
        meta += struct.pack(">I", 8 + off)              # offset to the forks
        meta += ftype + creator
        meta += struct.pack(">II", 0xA5000000, 0xA6000000)
        meta += struct.pack(">H", 0)                    # finder flags
        meta += struct.pack(">I", crc)
        meta += struct.pack(">H", 1 if password is not None else 0)
        meta += struct.pack(">IIII", rlen, dlen, len(rc), len(dc))
        assert len(meta) == 45, len(meta)
        index += meta

    head = bytearray()
    head.append(1)                                      # signature
    head.append(1)                                      # volume
    head += struct.pack(">H", 0x4350)                   # cross-volume magic
    head += struct.pack(">I", 8 + len(body))            # index offset
    return (bytes(head) + bytes(body) +
            struct.pack(">I", crc32(bytes(index))) + bytes(index))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--password", default=None)
    args = ap.parse_args()
    pw = args.password.encode("mac_roman") if args.password else None
    open(args.output, "wb").write(build(pw))
    return 0


if __name__ == "__main__":
    sys.exit(main())

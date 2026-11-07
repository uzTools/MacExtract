#!/usr/bin/env python3
"""mkdc42.py — wrap a raw 400K, 800K or 1440K floppy image as Disk Copy 4.2.

    tools/mkdc42.py RAW.img OUT.dsk --name "MacExtract"
    tools/mkdc42.py --check OUT.dsk RAW.img

Writes no tag block (tag size 0), as the tagless 800K images Disk Copy
itself made do. The file is the data fork only: Disk Copy on a Mac opens it
once it is typed 'dImg'/'dCpy'.

Source: reference/notes/DiskCopy42.md for the header, and the DiscFerret
wiki's Apple_DiskCopy_4.2 page (fetched 2026-11-07) for the checksum: add
each big-endian 16-bit word, then rotate the 32-bit sum right by one. That
checksum matches the stored one on 11 Disk Copy images in
~/.cache/macextract (400K, 800K and 1440K; DECISIONS.md 2026-11-07, *the
floppies twice*).
"""
import argparse
import sys

# (data size) -> (disk encoding at 0x50, format byte at 0x51).
# Source: reference/notes/DiskCopy42.md, *Disk Encoding byte* and *Format
# byte*, and the DiscFerret page: 0x02 is a Mac 400K GCR disk, 0x22 a
# two-sided one, and for MFM 0x22 is two-sided with 512-byte sectors.
KINDS = {
    409600: (0x00, 0x02),
    819200: (0x01, 0x22),
    1474560: (0x03, 0x22),
}


def checksum(data):
    a = 0
    for i in range(0, len(data), 2):
        a = (a + ((data[i] << 8) | data[i + 1])) & 0xFFFFFFFF
        a = ((a >> 1) | (a << 31)) & 0xFFFFFFFF
    return a


def header(raw, name):
    if len(raw) not in KINDS:
        raise SystemExit(f"mkdc42: {len(raw)} B is not a 400K, 800K or 1440K disk")
    n = name.encode("mac_roman")
    if len(n) > 63:
        raise SystemExit("mkdc42: the name is longer than 63 bytes")
    enc, fmt = KINDS[len(raw)]
    h = bytes([len(n)]) + n.ljust(63, b"\0")
    h += len(raw).to_bytes(4, "big") + (0).to_bytes(4, "big")
    h += checksum(raw).to_bytes(4, "big") + (0).to_bytes(4, "big")
    h += bytes([enc, fmt, 0x01, 0x00])
    assert len(h) == 0x54
    return h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="read DC42 back: magic, sizes, checksum, data == RAW")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--name", default="")
    o = ap.parse_args()
    if o.check:
        d = open(o.a, "rb").read()
        raw = open(o.b, "rb").read()
        ds = int.from_bytes(d[0x40:0x44], "big")
        ok = (d[0x52:0x54] == b"\x01\x00" and ds == len(raw)
              and len(d) == 0x54 + ds
              and int.from_bytes(d[0x48:0x4C], "big") == checksum(d[0x54:])
              and d[0x54:] == raw)
        print(f"mkdc42: {o.a}: {d[1:1 + d[0]].decode('mac_roman')!r}, "
              f"{ds} B, encoding {d[0x50]}, format 0x{d[0x51]:02X}, "
              f"{'same as' if ok else 'NOT the same as'} {o.b}")
        return 0 if ok else 1
    raw = open(o.a, "rb").read()
    with open(o.b, "wb") as f:
        f.write(header(raw, o.name) + raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())

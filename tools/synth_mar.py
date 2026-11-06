#!/usr/bin/env python3
"""synth_mar.py — MAR archives whose every field is known, for the paths
the two real archives do not reach.

    synth_mar.py --case single -o synth-mar-single.mac
    synth_mar.py --case tree   -o synth-mar-tree.mar
    synth_mar.py --case tree --lzw 12 -o x.mar   (wrapped as mar 0.2.0's
                                                   Command-key encode does)
    synth_mar.py --case tree --describe           (the items, as JSON)

The layout is src/fmt_mar.c's header comment, which cites the format's
author: mac-utils' src/lib/mar.c for the header, src/mar/mar_create.c
(mar_create_block_raw) for a block — its bytes, a CRC-32 of them, zeros
to the next 128 — and mar 0.2.0's mar_enc.c, which writes no block for
an empty fork. **This is this repository's reading of the format, not
the author's writer**, so what it can grade is the engine against that
reading; what grades the reading is the two archives hampa wrote
(tools/run_mar.py, *What it cannot see*).

`--lzw BITS` writes what mar 0.2.0's own LZW encoder writes — its
behaviour read in reference/mar/mar-0.2.0-src/src/lzw.c, not its code,
which is GPL-2.0-only (NOTICE): no padding at a width change or after a
clear, a clear the moment the table fills. tools/run_mar.py decodes it
with gzip as well as with the engine.

Deterministic: the same case gives the same bytes.
"""
import argparse
import json
import struct
import sys

MAGIC, FILE, FOLD, END = 0x4D415280, b"file", b"fold", b"----"
POLY = 0x1EDC6F41


def crc32(data, crc=0):
    """CRC-32 over 0x1EDC6F41, most significant bit first, from 0, nothing
    inverted (mac-utils src/lib/mar.c, mar_calc_crc)."""
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ POLY if crc & 0x80000000 else crc << 1) \
                & 0xFFFFFFFF
    return crc


def header(kind, name, dlen=0, rlen=0, clen=0, flags=0, ctime=0, mtime=0,
           finfo=bytes(16), scroll=(0, 0)):
    h = bytearray(128)
    struct.pack_into(">I4s", h, 0, MAGIC, kind)
    assert len(name) <= 63
    h[8] = len(name)
    h[9:9 + len(name)] = name
    struct.pack_into(">IIIIII", h, 72, dlen, rlen, clen, flags, ctime, mtime)
    h[96:112] = finfo
    struct.pack_into(">hh", h, 112, *scroll)
    struct.pack_into(">I", h, 124, crc32(bytes(h[:124])))
    return bytes(h)


def block(data):
    if not data:
        return b""
    out = data + struct.pack(">I", crc32(data))
    return out + bytes((128 - len(out) % 128) % 128)


def finfo_file(typ, creator, fl, v=0, h=0, fldr=0):
    return typ + creator + struct.pack(">HhhH", fl, v, h, fldr)


def finfo_dir(rect, fl, v, h, view):
    return struct.pack(">hhhhHhhH", *rect, fl, v, h, view)


def text(seed, n):
    """n bytes that compress, and differ by seed."""
    words = [b"Macintosh ", b"archive ", b"fork ", b"%d " % seed,
             b"resource ", b"Finder\r"]
    out = bytearray()
    i = seed
    while len(out) < n:
        out += words[i % len(words)]
        i = i * 7 + 3
    return bytes(out[:n])


# A comment past the 255 bytes the engine carries (UNC_ENTRY_COMMENT_MAX),
# so the cut is graded.
LONG_COMMENT = b"".join(b"Comment line %03d. " % i for i in range(20))

# Each item: (kind, name, fields). Folders hold a list of items.
CASES = {
    # A `.mac`: one file, both forks, a comment, locked, and the two Finder
    # flags mar 0.2.0 clears on the first item set, so their clearing shows.
    "single": [
        ("file", b"Read Me First", dict(
            data=text(1, 3000), rsrc=text(2, 700), comment=b"Get Info says hi",
            flags=1, ctime=0xD0000000, mtime=0xD0000100,
            finfo=finfo_file(b"TEXT", b"ttxt", 0x0101 | 0x0400, 40, 60, 0))),
    ],
    "tree": [
        ("fold", b"Top Folder", dict(
            flags=0x10, ctime=0xD1000000, mtime=0xD1000200,
            finfo=finfo_dir((40, 20, 300, 400), 0x0101, 10, 20, 0x0100),
            scroll=(-4, 8)), [
            ("file", b"Both Forks", dict(
                data=text(3, 5000), rsrc=text(4, 1234),
                ctime=0xD1000010, mtime=0xD1000020,
                finfo=finfo_file(b"APPL", b"TEST", 0x2100, 64, 32, 0))),
            ("file", b"Data Only", dict(
                data=text(5, 127),
                finfo=finfo_file(b"TEXT", b"ttxt", 0x0100, 0, 0, 0))),
            ("file", b"Rsrc Only", dict(
                rsrc=text(6, 124),
                finfo=finfo_file(b"rsrc", b"RSED", 0x0000, 5, 5, 0))),
            ("file", b"Empty", dict(
                finfo=finfo_file(b"TEXT", b"ttxt", 0, 0, 0, 0))),
            ("fold", b"Inner", dict(
                flags=0x10,
                finfo=finfo_dir((50, 50, 200, 300), 0x0100, 30, 40, 0x0200),
                scroll=(0, -16)), [
                ("file", b"A/B slash", dict(
                    data=text(7, 129), comment=LONG_COMMENT,
                    finfo=finfo_file(b"TEXT", b"ttxt", 0x0100, 1, 2, 0))),
                ("file", b"Locked", dict(
                    data=text(8, 600), flags=1,
                    finfo=finfo_file(b"TEXT", b"ttxt", 0x0100, 3, 4, 0))),
                ("fold", b"Empty Folder", dict(
                    flags=0x10,
                    finfo=finfo_dir((0, 0, 100, 100), 0x0100, 0, 0, 0)), []),
            ]),
            ("file", b"A name of forty-one characters, too long", dict(
                data=text(9, 10),
                finfo=finfo_file(b"TEXT", b"ttxt", 0x0100, 0, 0, 0))),
        ]),
    ],
}


def write(items):
    out = bytearray()
    for it in items:
        kind, name, f = it[0], it[1], it[2]
        if kind == "file":
            d, r, c = f.get("data", b""), f.get("rsrc", b""), \
                f.get("comment", b"")
            out += header(FILE, name, len(d), len(r), len(c), f.get("flags", 0),
                          f.get("ctime", 0), f.get("mtime", 0), f["finfo"])
            out += block(d) + block(r) + block(c)
        else:
            out += header(FOLD, name, 0, 0, 0, f.get("flags", 0x10),
                          f.get("ctime", 0), f.get("mtime", 0), f["finfo"],
                          f.get("scroll", (0, 0)))
            out += write(it[3])
            out += header(END, b"")
    return bytes(out)


def describe(items, prefix=""):
    """What the engine must deliver, item by item: the path with '/' in
    a name swapped to ':', and the Finder info as stored. mar 0.2.0's
    expander clears on-desk and inited on the first item (mar_dec.c,
    par_clear_first); the shell clears on-desk on every item instead and
    writes a top folder inited (src/fmt_mar.c says why)."""
    rows = []
    for it in items:
        kind, name, f = it[0], it[1], it[2]
        path = prefix + name.replace(b"/", b":").decode("mac_roman")
        fi = bytearray(f["finfo"])
        row = {"name": path, "finder_flags": struct.unpack(">H",
               f["finfo"][8:10])[0], "finfo": fi.hex(),
               "ctime": f.get("ctime", 0), "mtime": f.get("mtime", 0)}
        if kind == "file":
            row.update(type=f["finfo"][:4].decode("mac_roman"),
                       creator=f["finfo"][4:8].decode("mac_roman"),
                       data=f.get("data", b"").hex(),
                       rsrc=f.get("rsrc", b"").hex(),
                       comment=f.get("comment", b"")[:255].hex(),
                       locked=bool(f.get("flags", 0) & 1))
            rows.append(row)
        else:
            sv, sh = f.get("scroll", (0, 0))
            row.update(is_dir=True,
                       fxinfo=struct.pack(">hh", sv, sh).hex() + "00" * 12)
            rows.append(row)
            rows += describe(it[3], path + "/")
    return rows


class _Bits:
    """Codes packed least significant bit first, as compress(1) packs them."""

    def __init__(self, head):
        self.out = bytearray(head)
        self.acc = 0
        self.n = 0

    def put(self, code, width):
        self.acc |= code << self.n
        self.n += width
        while self.n >= 8:
            self.out.append(self.acc & 0xFF)
            self.acc >>= 8
            self.n -= 8

    def align(self):
        if self.n:
            self.out.append(self.acc & 0xFF)
        self.acc = self.n = 0


def lzw(data, bits, pad_after_clear=False):
    """What mar 0.2.0's Command-key encode writes: its BEHAVIOUR, as read in
    reference/mar/mar-0.2.0-src/src/lzw.c, written here from that reading
    rather than from its code. A compress(1) header with block mode set;
    codes of 9 bits at first and the first free code 257; one bit wider
    once the next code to be assigned no longer fits; the table full at
    2**bits - 1; a clear (256) written the moment it fills, at the width
    then in force; and NO padding after a clear or anywhere else, where
    compress(1) pads to a group of eight codes.

    `pad_after_clear` is a CONTROL only: a zero byte after the first clear,
    which that encoder never writes (tools/run_mar.py)."""
    w = _Bits([0x1F, 0x9D, 0x80 | bits])
    if not data:
        return bytes(w.out)
    limit = (1 << bits) - 1
    table, nxt, width = {}, 257, 9
    cur = data[0]
    for b in data[1:]:
        if (cur, b) in table:
            cur = table[cur, b]
            continue
        w.put(cur, width)
        if nxt < limit:
            if nxt >= 1 << width:
                width += 1
            table[cur, b] = nxt
        nxt += 1
        if nxt > limit:
            w.put(256, width)
            table, nxt, width = {}, 257, 9
            if pad_after_clear:
                pad_after_clear = False
                w.align()
                w.out.append(0)
        cur = b
    w.put(cur, width)
    w.align()
    return bytes(w.out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, choices=sorted(CASES))
    ap.add_argument("--lzw", type=int)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("-o")
    a = ap.parse_args()
    if a.describe:
        json.dump(describe(CASES[a.case]), sys.stdout, indent=1)
        print()
        return
    blob = write(CASES[a.case])
    if a.lzw:
        blob = lzw(blob, a.lzw)
    with open(a.o, "wb") as f:
        f.write(blob)


if __name__ == "__main__":
    main()

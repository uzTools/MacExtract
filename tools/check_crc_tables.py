#!/usr/bin/env python3
"""Check that src/unc_util.c's three CRC tables ARE their polynomials.

The tables were transcribed from reference/XADMaster/CRC.m and
reference/macutils, and the file said all along that they were
"generated mechanically from the polynomials".  Nothing checked that.
This does: it rebuilds each table from the polynomial the PUBLISHED
description states, compares it entry for entry with what the source
carries, and asserts the standard check value.  A table that is one
entry off, or a polynomial someone edited, fails here.

Where each polynomial is published, none of it from an implementation:

  * CRC-16/XMODEM, poly 0x1021, init 0x0000, MSB-first, no final xor.
    reference/notes/binhex40_lewis.txt, section "CRCs", states the
    bitwise algorithm step by step: shift the register left, xor the
    polynomial when the bit shifted out was 1.  Used by MacBinary
    II/III, BinHex 4 and PackIt.

  * CRC-32, poly 0x04C11DB7 reflected -> table constant 0xEDB88320.
    reference/notes/zip_appnote.txt states the polynomial and the
    0xdebb20e3 residue.  Used by zip, gzip, Arsenic and Compact Pro.

  * CRC-16/ARC, poly 0x8005 reflected -> 0xA001, init 0, no final xor.
    reference/deark/modules/... and reference/lhasa each BUILD this
    table from 0xA001 rather than listing it; the polynomial is the
    same 0x8005 every description of ARC's CRC gives.  Used by
    StuffIt classic's header and fork CRCs.

Run standalone, or from ci.sh.  --selftest proves it can fail.
"""

import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "unc_util.c"


def gen_msb16(poly):
    """MSB-first 16-bit table, the shape binhex40_lewis.txt describes."""
    t = []
    for n in range(256):
        c = n << 8
        for _ in range(8):
            c = ((c << 1) ^ poly) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        t.append(c)
    return t


def gen_reflected(poly, width):
    """Reflected table: CRC-32 with 0xEDB88320, CRC-16/ARC with 0xA001."""
    mask = (1 << width) - 1
    t = []
    for n in range(256):
        c = n
        for _ in range(8):
            c = ((c >> 1) ^ poly) if c & 1 else (c >> 1)
            c &= mask
        t.append(c)
    return t


def crc_msb16(table, data, init=0):
    c = init
    for b in data:
        c = ((c << 8) ^ table[((c >> 8) ^ b) & 0xFF]) & 0xFFFF
    return c


def crc_reflected(table, data, init, width):
    mask = (1 << width) - 1
    c = init
    for b in data:
        c = (table[(c ^ b) & 0xFF] ^ (c >> 8)) & mask
    return c


def parse_table(text, name):
    """Pull `static const ... name[256] = { ... };` out of the source."""
    m = re.search(r"\b" + re.escape(name) + r"\[256\]\s*=\s*\{(.*?)\};",
                  text, re.S)
    if not m:
        raise SystemExit("check_crc_tables: %s not found in %s" % (name, SRC))
    vals = [int(v, 16) for v in re.findall(r"0x([0-9a-fA-F]+)", m.group(1))]
    if len(vals) != 256:
        raise SystemExit("check_crc_tables: %s has %d entries, want 256"
                         % (name, len(vals)))
    return vals


def check(tables, quiet=False):
    """Returns a list of failure strings; empty means every table agrees."""
    bad = []
    nine = b"123456789"

    want = gen_msb16(0x1021)
    if tables["unc_crc16_table"] != want:
        i = next(i for i in range(256) if tables["unc_crc16_table"][i] != want[i])
        bad.append("unc_crc16_table differs from poly 0x1021 at entry %d "
                   "(source 0x%04x, polynomial 0x%04x)"
                   % (i, tables["unc_crc16_table"][i], want[i]))
    elif crc_msb16(want, nine) != 0x31C3:
        bad.append("CRC-16/XMODEM check value is 0x%04x, want 0x31C3"
                   % crc_msb16(want, nine))

    want = gen_reflected(0xEDB88320, 32)
    if tables["unc_crc32_table"] != want:
        i = next(i for i in range(256) if tables["unc_crc32_table"][i] != want[i])
        bad.append("unc_crc32_table differs from poly 0xEDB88320 at entry %d "
                   "(source 0x%08x, polynomial 0x%08x)"
                   % (i, tables["unc_crc32_table"][i], want[i]))
    else:
        v = crc_reflected(want, nine, 0xFFFFFFFF, 32) ^ 0xFFFFFFFF
        if v != 0xCBF43926:
            bad.append("CRC-32 check value is 0x%08x, want 0xCBF43926" % v)

    want = gen_reflected(0xA001, 16)
    if tables["unc_crc16_arc_table"] != want:
        i = next(i for i in range(256)
                 if tables["unc_crc16_arc_table"][i] != want[i])
        bad.append("unc_crc16_arc_table differs from poly 0xA001 at entry %d "
                   "(source 0x%04x, polynomial 0x%04x)"
                   % (i, tables["unc_crc16_arc_table"][i], want[i]))
    elif crc_reflected(want, nine, 0, 16) != 0xBB3D:
        bad.append("CRC-16/ARC check value is 0x%04x, want 0xBB3D"
                   % crc_reflected(want, nine, 0, 16))

    if not bad and not quiet:
        print("check_crc_tables: ok (3 tables, 768 entries, 3 check values)")
    return bad


def main():
    text = SRC.read_text()
    names = ("unc_crc16_table", "unc_crc32_table", "unc_crc16_arc_table")
    tables = {n: parse_table(text, n) for n in names}

    if "--selftest" in sys.argv:
        # Establish that this check CAN fail: bend one entry of each table
        # and confirm each is caught. CLAUDE.md, "a test that passes may
        # not be testing anything".
        for n in names:
            hurt = {k: list(v) for k, v in tables.items()}
            hurt[n][137] ^= 0x01
            if not check(hurt, quiet=True):
                raise SystemExit("check_crc_tables: SELFTEST FAILED — a bent "
                                 "%s passed" % n)
        print("check_crc_tables: selftest ok (3 bent tables, 3 caught)")

    bad = check(tables)
    if bad:
        for b in bad:
            print("check_crc_tables: FAIL: " + b)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""synth_envelopes.py — envelopes that state every Finder field they can hold.

    tools/synth_envelopes.py --case mb2 -o out.bin
    tools/synth_envelopes.py --list

No fixture in the corpus is a MacBinary file with a Get Info comment, a
MacBinary III header with a script or extended-flags byte, a MacBinary I
header with its "Locked" bit, a uuencode or base64 file with a read-only
mode, or a MIME multipart/appledouble with dates and a comment (measured
2026-10-17 over the corpus and the specimen cache). So these are written
here, to the letter of each standard, and tools/run_meta.py holds the
engine to them — and to a second reader wherever one reads the field:

  mb1     MacBinary I (reference/notes/macbinary_specs_theunarchiver.md,
          the original standard): no CRC, 99..125 zero, and 73's bit 7,
          "Locked", set.
  mb2     MacBinary II (reference/notes/macbinary_ii.txt): fdLocation,
          fdFldr, the "Protected" bit at 81, and a Get Info comment —
          length at 99, text on the 128-byte boundary after the resource
          fork.
  mb3     MacBinary III (reference/notes/macbinary_iii.txt): 'mBIN',
          fdScript at 106, fdXFlags at 107, 73's bit 7 as isAlias (not a
          lock), a secondary header (120) and a comment longer than the
          255 bytes the engine carries.
  uu-ro   plain uuencode, "begin 444": no owner write, so locked
          (reference/notes/posix_ustar.txt, S_IWUSR 00200).
  uu-rw   plain uuencode, "begin 644".
  uu-mu   UUTool's shape (tools/synth_uu.py) with a .finfo carrying an
          icon position and a folder, and a first-line mode of 0444 that
          is UUTool's preference and not the file's: no lock stated.
  b64-ro  sharutils' "begin-base64 400 <name>".
  mime-ad multipart/appledouble shaped as mpack's encode_applefile()
          writes it (reference/mpack/macfile.c): entries 3, 9 (32 bytes),
          8 (all four dates), 4 (the comment), 2, in that order, the
          applefile part base64, the data fork after it.

`describe(case)` is what each case states, by FIELD, built from the
values below and not from the bytes the builder wrote, so that a layout
the builder got wrong and the engine copied cannot agree with itself.
"""
import argparse
import base64
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import synth_as                     # noqa: E402  EMPTY_RSRC, the 2000 epoch
import synth_uu                     # noqa: E402  uu_lines

DATA = b"The data fork of a file that crossed the wire whole.\r" * 6
RSRC = synth_as.EMPTY_RSRC


def crc16_xmodem(b):
    c = 0
    for x in b:
        c ^= x << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def pad128(b):
    return b + bytes(-len(b) % 128)


# Each MacBinary case, field by field.
MB = {
    "mb1": dict(version=1, name=b"Locked In One", type=b"TEXT",
                creator=b"ttxt", flags=0x8100, v=0x30, h=0x40, fldr=0,
                protected=0, comment=None, script=0, xflags=0, sec=0),
    "mb2": dict(version=2, name=b"Placed And Protected", type=b"TEXT",
                creator=b"ttxt", flags=0x0120, v=0x50, h=0x64, fldr=7,
                protected=1,
                comment=b"Get Info comment, carried after the resource fork.",
                script=0, xflags=0, sec=0),
    "mb3": dict(version=3, name=b"An Alias In Three", type=b"adrp",
                creator=b"MACS", flags=0x8400, v=-1, h=-1, fldr=0,
                protected=0,
                comment=(b"A comment longer than the engine carries. " * 8)[:300],
                script=0x81, xflags=0x02, sec=10),
}


def macbinary(c):
    h = bytearray(128)
    h[1] = len(c["name"])
    h[2:2 + len(c["name"])] = c["name"]
    h[65:69] = c["type"]
    h[69:73] = c["creator"]
    h[73] = c["flags"] >> 8
    struct.pack_into(">hhH", h, 75, c["v"], c["h"], c["fldr"])
    h[81] = c["protected"]
    struct.pack_into(">IIII", h, 83, len(DATA), len(RSRC),
                     0xA5000000, 0xA5000100)
    if c["version"] >= 2:
        struct.pack_into(">H", h, 99, len(c["comment"] or b""))
        h[101] = c["flags"] & 0xFF
        struct.pack_into(">H", h, 120, c["sec"])
        h[122] = 130 if c["version"] == 3 else 129
        h[123] = 129
    if c["version"] == 3:
        h[102:106] = b"mBIN"
        h[106] = c["script"]
        h[107] = c["xflags"]
    if c["version"] >= 2:
        struct.pack_into(">H", h, 124, crc16_xmodem(bytes(h[:124])))
    out = bytes(h)
    if c["sec"]:
        out += pad128(b"S" * c["sec"])
    out += pad128(DATA) + pad128(RSRC)
    if c["comment"]:
        out += c["comment"]
    return out


def mb_describe(c):
    # FInfo, from the fields: fdType, fdCreator, fdFlags, fdLocation (v, h),
    # fdFldr — libhfs apple.h / RFC 1740's struct FInfo.
    finfo = (c["type"] + c["creator"] +
             struct.pack(">HhhH", c["flags"], c["v"], c["h"], c["fldr"]))
    if c["version"] == 1:
        finfo = finfo[:9] + b"\0" + finfo[10:]   # I has no low byte
        # ...and I's bit 7 of the high byte is the lock, not System 7's
        # isAlias, so it does not reach the flags (DECISIONS.md 2026-10-17,
        # *the envelopes' own Finder info*, at the merge).
        finfo = finfo[:8] + bytes([finfo[8] & 0x7F]) + finfo[9:]
    fx = "-"
    if c["version"] == 3:
        # FXInfo: fdIconID, fdUnused[3], fdScript, fdXFlags, fdComment,
        # fdPutAway.
        fx = struct.pack(">H6sBBHI", 0, b"", c["script"], c["xflags"],
                         0, 0).hex()
    locked = c["protected"] or (c["version"] == 1 and c["flags"] & 0x8000)
    cm = c["comment"] if c["version"] >= 2 else None
    return {c["name"].decode("mac-roman"): dict(
        finfo=finfo.hex(), fxinfo=fx, backup="-",
        lock="L" if locked else "n",
        comment=cm[:255].hex() if cm else "-")}


# uuencode and base64.
UUFINFO = dict(type=b"TEXT", creator=b"R*ch", flags=0x0100, v=0x22,
               h=0x33, fldr=0x0011)


def uu(case):
    if case == "uu-ro":
        return synth_uu.plain("read-only.txt", DATA, mode="444").encode()
    if case == "uu-rw":
        return synth_uu.plain("writable.txt", DATA, mode="644").encode()
    if case == "uu-mu":
        f = UUFINFO
        info = f["type"] + f["creator"] + struct.pack(
            ">HhhH", f["flags"], f["v"], f["h"], f["fldr"])

        def section(first, payload):
            lines = [first] + synth_uu.uu_lines(payload) + ["`", "end"]
            return lines
        lines = section('begin 0444 "Placed By UUTool"', DATA)
        lines += section("begin 0700 .rsrc", RSRC)
        lines += section("begin 0700 .finfo", info)
        return ("\n".join(lines) + "\n").encode()
    if case == "b64-ro":
        body = base64.encodebytes(DATA).decode()
        return ("begin-base64 400 owner-read-only.txt\n" + body +
                "====\n").encode()
    raise KeyError(case)


def uu_describe(case):
    if case == "uu-ro":
        return {"read-only.txt": dict(lock="L", finfo="-")}
    if case == "uu-rw":
        return {"writable.txt": dict(lock="n", finfo="-")}
    if case == "b64-ro":
        return {"owner-read-only.txt": dict(lock="L")}
    f = UUFINFO
    finfo = (f["type"] + f["creator"] +
             struct.pack(">HhhH", f["flags"], f["v"], f["h"], f["fldr"]))
    return {"Placed By UUTool": dict(finfo=finfo.hex(), lock="-")}


# MIME multipart/appledouble, mpack's shape.
AD = dict(name=b"Mailed Whole",
          finfo=b"TEXTttxt" + struct.pack(">HhhH", 0x0100, 0x40, 0x48, 0),
          fxinfo=struct.pack(">H6sBBHI", 0, b"", 0, 0, 0x1234, 0x55),
          dates=(0x1A000000, 0x1A000100, 0x1B000000, 0x1C000000),
          comment=b"A Get Info comment that travelled by mail.")


def applefile():
    """The application/applefile part: an AppleDouble header, entries in
    encode_applefile()'s order."""
    ents = [(3, AD["name"]), (9, AD["finfo"] + AD["fxinfo"]),
            (8, struct.pack(">4I", *AD["dates"])), (4, AD["comment"]),
            (2, RSRC)]
    head = struct.pack(">II16sH", 0x00051607, 0x00020000, b"\0" * 16,
                       len(ents))
    off = len(head) + 12 * len(ents)
    table, body = b"", b""
    for eid, b in ents:
        table += struct.pack(">III", eid, off + len(body), len(b))
        body += b
    return head + table + body


def mime():
    b = "=-=-=-=-=-macextract-appledouble"
    return ("MIME-Version: 1.0\r\n"
            "Content-Type: multipart/appledouble; boundary=\"%s\"\r\n\r\n"
            "--%s\r\nContent-Type: application/applefile\r\n"
            "Content-Transfer-Encoding: base64\r\n\r\n%s\r\n"
            "--%s\r\nContent-Type: application/octet-stream; "
            "name=\"Mailed Whole\"\r\n"
            "Content-Transfer-Encoding: base64\r\n\r\n%s\r\n--%s--\r\n"
            % (b, b, base64.encodebytes(applefile()).decode()
               .replace("\n", "\r\n"), b,
               base64.encodebytes(DATA).decode().replace("\n", "\r\n"),
               b)).encode()


CASES = dict({k: (lambda k=k: macbinary(MB[k])) for k in MB},
             **{k: (lambda k=k: uu(k))
                for k in ("uu-ro", "uu-rw", "uu-mu", "b64-ro")},
             **{"mime-ad": mime})
SUFFIX = {"mb1": ".bin", "mb2": ".bin", "mb3": ".bin", "uu-ro": ".uu",
          "uu-rw": ".uu", "uu-mu": ".uu", "b64-ro": ".b64",
          "mime-ad": ".mim"}


def build(case):
    return CASES[case]()


def describe(case):
    if case in MB:
        return mb_describe(MB[case])
    if case == "mime-ad":
        return {AD["name"].decode(): dict(lock="-")}
    return uu_describe(case)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", choices=sorted(CASES))
    ap.add_argument("-o", "--out")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.case:
        for k in sorted(CASES):
            print(k, describe(k))
        return
    blob = build(a.case)
    if a.out:
        open(a.out, "wb").write(blob)
    else:
        sys.stdout.buffer.write(blob)


if __name__ == "__main__":
    main()

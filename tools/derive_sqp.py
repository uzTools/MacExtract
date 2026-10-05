#!/usr/bin/env python3
"""derive_sqp.py — read the AppleLink `.pkg` format out of Aladdin's own
expander, and grade that reading against the two real packages.

The format's internal name is **SqueezePlay**: the expander's `'HBSF' 0`
resource is the Pascal string `SQUEEZEPLAY 1.0`, and its routines are
`RdSQPDirectory`, `WrSQPDirectory`, `InitSqp`.

**The reference implementation is `AppleLink Package Translator`, version
3.0.3, "Copyright (c) 1990-1992 Aladdin Systems, Inc."**, which ships in
the StuffIt Deluxe **3.0.7** installer and nowhere later: 3.5 replaced it
with `PKG Expand Translator`, whose code resource is a *CompactPro* build
that recognises a package by its extension and hands the file to the
engine's generic dispatcher (DECISIONS.md 2026-10-05). Its `'Othe' 1` is
33,300 bytes of 68k carrying **148 MacsBug symbols**, so every routine
below is named by the binary itself rather than guessed at.

Everything this script implements is cited to a routine and an offset in
that resource, and `--witness` checks thirteen byte patterns that a
different build would fail — so a changed input makes this print FAIL
rather than silently confirm today's reading.

    tools/derive_sqp.py                  grade the two real packages
    tools/derive_sqp.py --witness        check the reading against the binary
    tools/derive_sqp.py --layout         print the layout it read

Not in `ci.sh`: it needs the two packages (`tools/fetch_specimens.py
--only applelink`) and, for `--witness`, the translator resource, which is
copyrighted and not committed. It skips cleanly without either.
`tools/vmac/README.md` (*The AppleLink package expander*) has the one
command that rebuilds the resource from the 3.0.7 installer.
"""
import argparse
import hashlib
import os
import struct
import sys

HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "applelink")
TRANSLATOR = os.path.join(HOME, "pkgeng", "alink307.bin")

# ---------------------------------------------------------------------------
# What the reading rests on. Each is a byte pattern in `'Othe' 1` of
# `AppleLink Package Translator` 3.0.3, with the routine it sits in.
WITNESSES = [
    ("RdSQPDirectory @0x5e72: reads an 86-byte record",
     "70562d40fffc486df814"),
    ("WrSQPDirectory @0x5f80: seeks to 86 * index ...",
     "c2fc00564842c4fc0056"),
    ("WrSQPDirectory: ... + 10, and writes from node+12",
     "740ad282"),
    ("WrHFSDirectory @0x5eb2: HFS directory at 86 * count + 22",
     "7056c1ee00127216"),
    ("WrHFSDirectory: 90-byte records, written from node+8",
     "c4fc005a4843c6fc005a"),
    ("ResetDecompressor @0x25ac: code width starts at 9",
     "3b7c0009fef0"),
    ("ResetDecompressor: first free code is 257",
     "3b7c0101feec"),
    ("Decompress @0x2a78: 256 is the clear code",
     "0c470100"),
    ("Decompress: the table stops growing at 8192",
     "0c472000"),
    ("GetCode @0x2b98: the 13th bit is the last",
     "700db06dfef0"),
    ("GetExpandedSize @0x13ac: node+88 + node+92 is the expanded size",
     "202c0058d0ac005c"),
    ("DoWork @0x0: bit 1 of node+96 selects stored over LZW",
     "082b00010060"),
    ("DoWork: a stored fork's length comes from node+92",
     "2e2b005c"),
]

# ---------------------------------------------------------------------------
# The container.
#
# Source: WrSQPDirectory @0x5f80 writes record `i` at 86*i + 10 and takes
# its 86 bytes from the in-memory node at node+12; WrHFSDirectory @0x5eb2
# writes the second directory at 86*count + 22, 90 bytes per record taken
# from node+8 — so an HFS record is the same fields with four more bytes
# in front of them, and a field at SQP record +N is at node +N+12.
#
#   +0    u8      number of items
#   +1    u8      version (1)
#   +2    u8[8]   zero
#   +10           SQP directory: count x 86-byte records
#   +86n+10 u32   number of items, again; u8[8] zero
#   +86n+22       HFS directory: count x 90-byte records
#   +86n+22+90n   the members' bytes, in record order
#
#   -- an SQP record, with the routine that names each field --
#   +8    u32     compressed length          DoWork, the copy loop's budget
#   +12   u32     absolute offset of the member   DoWork @0x606, SetFPos
#   +20   OSType  file type                  the field the engine tests
#   +24   OSType  creator
#   +28   u16     Finder flags
#   +36   Str31   name (32 bytes)
#   +68   u32     creation date
#   +72   u32     modification date
#   +76   u32     resource fork length       GetExpandedSize, node+88
#   +80   u32     data fork length           GetExpandedSize, node+92
#   +84   u16     flags; bit 1 = stored      DoWork @0x618, btst #1
# sha256 of each member's expanded data fork, recorded 2026-10-05 from the
# reading below. These are the regression oracle: nothing else here can
# tell a decoder that is subtly wrong from one that is right, because the
# packages carry no per-member checksum of their own (FORMATS.md,
# *AppleLink packages*).
EXPANDED = {
    ("Read First.PKG", "Antipiracy-Read Me First"):
        "fb90a04992654064a28ee6c2d1387d3b6d3fbc985860d1acf01e2eebf5f38641",
    ("ALink.PKG", "FileMaker Import"):
        "21b65275c91266f57d0ea1e18b17385ed69092689407ac9efba3c8e3477d5602",
    ("ALink.PKG", "Package Data"):
        "0885443117e8ed179f8c026cf7bb810aa23c86701d12447127f9fef650ee3f2a",
    ("ALink.PKG", "Trademark Data"):
        "473810d521350ca969ee46839cebcf5c5c992bbdef63e556c47f53cc61c16239",
}

HDR = 10
SQP_REC = 86
HFS_REC = 90
F_STORED = 1 << 1


def directory(d):
    """(count, [record]) — the SQP directory."""
    if len(d) < HDR:
        raise ValueError("shorter than a header")
    count, version = d[0], d[1]
    recs = []
    for i in range(count):
        p = HDR + SQP_REC * i
        r = d[p:p + SQP_REC]
        if len(r) < SQP_REC:
            raise ValueError("directory runs off the end")
        recs.append({
            "clen": struct.unpack(">I", r[8:12])[0],
            "off": struct.unpack(">I", r[12:16])[0],
            "type": r[20:24].decode("mac-roman"),
            "creator": r[24:28].decode("mac-roman"),
            "finder": struct.unpack(">H", r[28:30])[0],
            "name": r[37:37 + r[36]].decode("mac-roman", "replace"),
            "ctime": struct.unpack(">I", r[68:72])[0],
            "mtime": struct.unpack(">I", r[72:76])[0],
            "rlen": struct.unpack(">I", r[76:80])[0],
            "dlen": struct.unpack(">I", r[80:84])[0],
            "flags": struct.unpack(">H", r[84:86])[0],
        })
    return count, version, recs


def hfs_directory_at(count):
    """Source: WrHFSDirectory @0x5eb2 — 86 * count + 22."""
    return SQP_REC * count + 22


def members_start(count):
    return hfs_directory_at(count) + HFS_REC * count


# ---------------------------------------------------------------------------
# The codec: `compress`-style LZW, read off GetCode @0x2b98 and
# Decompress @0x2a78. InitLzw @0x26b0 builds the two mask tables this
# uses and allocates the prefix/suffix/stack buffers.
RMASK = [0x00, 0x01, 0x03, 0x07, 0x0f, 0x1f, 0x3f, 0x7f, 0xff]
INIT_BITS = 9
MAX_BITS = 13
MAX_CODE = 8192
CLEAR = 256
FIRST = 257


class GetCode:
    """GetCode @0x2b98. Codes are packed LSB-first in blocks of n_bits
    bytes, and a width change discards the rest of the block — which is
    `compress`'s getcode() and is why the refill reads exactly n_bits
    bytes and then sets size = (n << 3) - (n_bits - 1)."""

    def __init__(self, data):
        self.d, self.p = data, 0
        self.buf = bytearray(256)
        self.n_bits, self.maxcode = INIT_BITS, (1 << INIT_BITS) - 1
        self.free_ent, self.clear_flag = FIRST, 0
        self.offset, self.size = 0, 0

    def _byte(self):
        if self.p >= len(self.d):
            return -1
        c = self.d[self.p]
        self.p += 1
        return c

    def get(self):
        if self.clear_flag or self.offset >= self.size \
           or self.free_ent > self.maxcode:
            if self.free_ent > self.maxcode:
                self.n_bits += 1
                self.maxcode = MAX_CODE if self.n_bits == MAX_BITS \
                    else (1 << self.n_bits) - 1
            if self.clear_flag:
                self.n_bits = INIT_BITS
                self.maxcode = (1 << INIT_BITS) - 1
                self.clear_flag = 0
            n = 0
            while n < self.n_bits:
                c = self._byte()
                if c < 0:
                    break
                self.buf[n] = c
                n += 1
            if n == 0:
                return -1
            self.offset = 0
            self.size = (n << 3) - (self.n_bits - 1)
        off, bits = self.offset, self.n_bits
        i, off = off >> 3, off & 7
        val = self.buf[i] >> off
        i += 1
        bits -= 8 - off
        off = 8 - off
        if bits >= 8:
            val |= self.buf[i] << off
            i += 1
            off += 8
            bits -= 8
        val |= (self.buf[i] & RMASK[bits]) << off
        self.offset += self.n_bits
        return val & 0xffff


def decompress(data, stats=None):
    """Decompress @0x2a78.

    CORRECTION to anyone's memory of Unix `compress`: on a clear code
    this expander sets the next free code to **256**, not 257 (@0x2ae0),
    so the clear code's own slot is reused from then on. That is what the
    binary does and it is not what `compress` does.
    """
    b = GetCode(data)
    prefix = [0] * (MAX_CODE + 1)
    suffix = bytearray(MAX_CODE + 1)
    for i in range(256):
        suffix[i] = i
    out, stack = bytearray(), bytearray()
    oldcode = b.get()
    if stats is not None:
        stats["codes"] += 1
    if oldcode < 0:
        return out
    finchar = oldcode & 0xff
    out.append(finchar)
    code = b.get()
    while code >= 0:
        if code == CLEAR:
            if stats is not None:
                stats["clears"] += 1
            prefix[:256] = [0] * 256
            b.clear_flag, b.free_ent = 1, CLEAR
            code = b.get()
            if code < 0:
                break
        incode = code
        if code >= b.free_ent:
            stack.append(finchar)
            code = oldcode
        while code >= 256:
            stack.append(suffix[code])
            code = prefix[code]
            if len(stack) > MAX_CODE:
                # A corrupt stream can make the prefix chain cyclic; the
                # 68k original would walk it into the weeds.
                raise ValueError("cyclic prefix chain at code %d" % incode)
        finchar = suffix[code]
        stack.append(finchar)
        while stack:
            out.append(stack.pop())
        if b.free_ent < MAX_CODE:
            prefix[b.free_ent] = oldcode
            suffix[b.free_ent] = finchar
            b.free_ent += 1
        oldcode = incode
        if stats is not None:
            stats["n_bits"] = max(stats["n_bits"], b.n_bits)
            stats["free_ent"] = max(stats["free_ent"], b.free_ent)
            stats["codes"] += 1
        code = b.get()
    return out


def member(d, rec, stats=None):
    """The member's data fork.

    The resource fork is a second stream in the same region, handled by
    the same stored-or-LZW branch (DoWork @0x9f2). Both real packages
    carry rlen == 0, so this script does not claim to place it: that part
    is READ but UNGRADED (OPEN_ITEMS.md).
    """
    raw = d[rec["off"]:rec["off"] + rec["clen"]]
    if rec["flags"] & F_STORED:
        return raw[:rec["dlen"]], "stored"
    # No limit: the stream has to RUN OUT at the declared length. Passing
    # rec["dlen"] in as a ceiling would make the length check assert a
    # property of this decoder's own truncation and it could never fail.
    return decompress(raw, stats), "lzw"


# ---------------------------------------------------------------------------
def witness():
    if not os.path.exists(TRANSLATOR):
        print("derive_sqp: no %s — see tools/vmac/README.md, "
              "*The AppleLink package expander*" % TRANSLATOR)
        return 0
    code = open(TRANSLATOR, "rb").read()
    print("AppleLink Package Translator 3.0.3, 'Othe' 1: %d B" % len(code))
    bad = 0
    for what, hx in WITNESSES:
        at = code.find(bytes.fromhex(hx))
        bad += at < 0
        print("  %-8s %s" % ("%06x" % at if at >= 0 else "MISSING", what))
    print("derive_sqp: %d of %d witnesses found"
          % (len(WITNESSES) - bad, len(WITNESSES)))
    return 1 if bad else 0


def layout():
    print(__doc__.split("Everything this script")[0].rstrip())
    print("\nThe container, as read:\n")
    for line in open(os.path.abspath(__file__)):
        if line.startswith("#   "):
            print("  " + line[4:].rstrip())
    return 0


def grade():
    pkgs = sorted(f for f in os.listdir(SPECIMENS)) \
        if os.path.isdir(SPECIMENS) else []
    if not pkgs:
        print("derive_sqp: no packages in %s — run "
              "tools/fetch_specimens.py --only applelink" % SPECIMENS)
        return 0
    total = exact = clears = widest = 0
    for fn in pkgs:
        d = open(os.path.join(SPECIMENS, fn), "rb").read()
        count, version, recs = directory(d)
        start = members_start(count)
        print("%s — %d B, %d item%s, version %d"
              % (fn, len(d), count, "" if count == 1 else "s", version))
        print("  SQP directory 0x%x..0x%x, HFS directory 0x%x..0x%x, "
              "members from 0x%x"
              % (HDR, HDR + SQP_REC * count, hfs_directory_at(count),
                 members_start(count), start))
        if recs and recs[0]["off"] != start:
            print("  !! first member is at 0x%x, not 0x%x"
                  % (recs[0]["off"], start))
        for r in recs:
            st = {"clears": 0, "n_bits": 0, "free_ent": 0, "codes": 0}
            out, how = member(d, r, st)
            digest = hashlib.sha256(out).hexdigest()
            want = EXPANDED.get((fn, r["name"]))
            ok = len(out) == r["dlen"] and r["rlen"] == 0 \
                and (want is None or want == digest)
            total += 1
            exact += ok
            print("  %-26s %s/%s %5d -> %5d B (want %d) %-6s %s"
                  % (repr(r["name"]), r["type"], r["creator"], r["clen"],
                     len(out), r["dlen"], how, "OK" if ok else "MISMATCH"))
            note = "" if want is None else (
                "  matches" if want == digest else "  != RECORDED")
            print("      sha256 %s%s" % (digest, note))
            if how == "lzw":
                widest = max(widest, st["n_bits"])
                clears += st["clears"]
                print("      %d codes; %d clear code(s); widest %d bits; "
                      "table reached %d"
                      % (st["codes"], st["clears"], st["n_bits"],
                         st["free_ent"]))
        end = max((r["off"] + r["clen"] for r in recs), default=start)
        print("  members tile 0x%x..0x%x; file is 0x%x  %s"
              % (start, end, len(d),
                 "exact" if end == len(d) else "!! SHORT"))
    print("derive_sqp: %d of %d members expand to their declared length"
          % (exact, total))
    # Say what the specimens do NOT exercise, rather than leaving it to be
    # inferred from a pass (TESTING.md, *AppleLink packages: SqueezePlay*).
    print("derive_sqp: UNEXERCISED by these packages — %s%sthe resource "
          "fork and the stored mode"
          % ("the clear code (%d seen), " % clears if clears == 0 else "",
             "widths above %d of 13 bits, " % widest if widest < MAX_BITS
             else ""))
    return 0 if exact == total else 1


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--witness", action="store_true")
    ap.add_argument("--layout", action="store_true")
    a = ap.parse_args()
    if a.layout:
        return layout()
    if a.witness:
        return witness()
    return grade()


if __name__ == "__main__":
    sys.exit(main())

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
that resource, and `--witness` checks twenty-nine byte patterns AT the
offsets they are claimed to sit at — so a changed input makes this print
FAIL rather than silently confirm today's reading.

    tools/derive_sqp.py                  grade the two real packages
    tools/derive_sqp.py --witness        check the reading against the binary
    tools/derive_sqp.py --layout         print the layout it read

Not in `ci.sh`: it needs the two packages (`tools/fetch_specimens.py
--only applelink`) and, for `--witness`, the translator resource, which is
copyrighted and not committed. It skips cleanly without either. What IS
in `ci.sh` is `tools/run_sqp.py`, which grades the ENGINE — against these
packages when they are present, and against `tools/synth_sqp.py` always
(TESTING.md, *AppleLink packages: SqueezePlay*).
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
# What the reading rests on. Each is (offset, what, bytes): a pattern in
# `'Othe' 1` of `AppleLink Package Translator` 3.0.3, the routine it sits
# in, and the offset it sits AT — checked at that offset, because six of
# these patterns occur more than once in the resource and an address is
# half of what identifies them.
WITNESSES = [
    (0x5e76, "RdSQPDirectory @0x5e72: reads an 86-byte record",
     "70562d40fffc486df814"),
    (0x5e10, "RdHFSDirectory @0x5e06: reads FOUR bytes, then the same 86",
     "70042d40fffc"),
    (0x5fb6, "WrSQPDirectory @0x5f80: seeks to 86 * index ...",
     "c2fc00564842c4fc0056"),
    (0x5fc6, "WrSQPDirectory: ... + 10, and writes from node+12",
     "740ad282"),
    (0x5ed6, "WrHFSDirectory @0x5eb2: HFS directory at 86 * count + 22",
     "7056c1ee00127216"),
    (0x5ee8, "WrHFSDirectory: 90-byte records, written from node+8",
     "c4fc005a4843c6fc005a"),
    (0x3074, "ReadFileAndBuildLinkedList @0x2faa: the version is 0 or 1",
     "0c400001"),
    (0x309a, "ReadFileAndBuildLinkedList: version 1's second header is at "
             "86 * count + 10", "c1fc0056d07c000a"),
    (0x31be, "ReadFileAndBuildLinkedList: a version-0 item is level 1 and "
             "not a folder", "397c00010008426c000a"),
    (0x118e, "CalculateFolderSize @0x113c: a non-zero folder flag recurses",
     "4a68000a"),
    (0x11d0, "CalculateFolderSize: a folder owns the items after it whose "
             "level is greater", "bc680008"),
    (0x25b2, "ResetDecompressor @0x25ac: code width starts at 9",
     "3b7c0009fef0"),
    (0x25e2, "ResetDecompressor: first free code is 257",
     "3b7c0101feec"),
    (0x2abe, "Decompress @0x2a78: 256 is the clear code",
     "0c470100"),
    (0x2ae0, "Decompress: a clear sets the next free code to 256 — which is "
             "`compress`'s own `free_ent = FIRST - 1`", "3b7c0100feec"),
    (0x2b46, "Decompress: the table stops growing at 8192",
     "0c472000"),
    (0x2bd2, "GetCode @0x2b98: the 13th bit is the last",
     "700db06dfef0"),
    (0x2632, "ResetCompressor @0x260e: the hash table is 8,599 entries",
     "2e3c00002197"),
    (0x288e, "Compress @0x27de: the table is cleared when it FILLS, and "
             "this binary has no other reason to clear it", "0c6d2000fec4"),
    (0x29f2, "PutCode @0x28fe: writing a clear takes the width back to 9",
     "3b7c0009fecc"),
    (0x13cc, "GetExpandedSize @0x13ac: node+88 + node+92 is the expanded size",
     "202c0058d0ac005c"),
    (0x0618, "DoWork @0x0: bit 1 of the flag byte at node+96 selects stored "
             "over LZW for the DATA fork", "082b00010060"),
    (0x0532, "DoWork: a stored data fork's length comes from node+92",
     "2e2b005c"),
    (0x0714, "DoWork: there is a resource fork when node+16 is non-zero",
     "4aab0010"),
    (0x096e, "DoWork @0x96e: bit 2 of the SAME byte selects stored for the "
             "RESOURCE fork", "082b00020060"),
    (0x0976, "DoWork: a stored resource fork's length comes from node+88",
     "2e2b0058"),
    (0x0bea, "DoSqForward @0xb60: a package is created as type 'HBSF', "
             "creator 'GEOL'", "2f3c47454f4c2f3c48425346"),
    (0x0c46, "DoSqForward: the header's count byte is capped at 50",
     "0c470032"),
    (0x1d62, "DoItemsForward @0x1ca2: and the SQP directory takes only the "
             "first 50 items", "7032b050"),
]

# ---------------------------------------------------------------------------
# The container.
#
# Source: ReadFileAndBuildLinkedList @0x2faa is the reader, and it is
# what the layout below is taken from; DoSqForward @0xb60,
# WrSQPDirectory @0x5f80 and WrHFSDirectory @0x5eb2 are the writer and
# agree with it from the other side.
#
#   +0    u8      number of items in the SQP directory (<= 50)
#   +1    u8      version: 0 or 1
#   +2    u8[8]   eight bytes, zero in both packages, read by nothing
#   +10           SQP directory: count x 86-byte records
#
#   version 0 ends there: those ARE the items, each at level 1 and none
#   a folder (@0x31be). version 1 carries a second directory, and it is
#   the one the expander reads:
#
#   +86n+10 u32   number of items in the HFS directory; u8[8] zero
#   +86n+22       HFS directory: count x 90-byte records --
#                 u16 level, u16 non-zero if a FOLDER, then the same 86
#   then           the members' bytes
#
#   The two counts need not agree. The SQP directory is a flat list of
#   the FILES, capped at 50, skipping anything typed 'HBSF', 'PIT ' or
#   'SIT!' (@0x1d5e) -- so a package with a folder in it has an 86-byte
#   hole where that item's SQP record would be. The header's count is
#   what LOCATES the HFS directory; the item count is the second
#   header's.
#
#   -- an SQP record, with the routine that names each field --
#   +0    u32     zero; written as zero (AddItems @0x239c), read nowhere
#   +4    u32     resource fork's compressed length   DoWork @0x714, @0x944
#   +8    u32     data fork's compressed length       DoWork @0x45a, @0x5ce
#   +12   u32     data fork's absolute offset         DoWork @0x606, SetFPos
#   +16   u32     resource fork's absolute offset     DoWork @0x816
#   +20   FInfo   16 bytes: type, creator, Finder flags, location, folder
#   +36   Str31   name (32 bytes)
#   +68   u32     creation date
#   +72   u32     modification date
#   +76   u32     resource fork's expanded length     GetExpandedSize, node+88
#   +80   u32     data fork's expanded length         GetExpandedSize, node+92
#   +84   u8      flags: bit 1 = data fork stored, bit 2 = resource fork
#                 stored (DoWork @0x618 and @0x96e, both `btst` on the
#                 BYTE). Bit 7 is set by InitSqp @0x5d56 and tested
#                 nowhere; bits 3 to 6 are the list's own state and are
#                 cleared when a package is read (@0x312c).
#   +85   u8      zero
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
SQP_MAX = 50
F_STORED_DATA = 1 << 1
F_STORED_RSRC = 1 << 2


def _record(r):
    """The 86 bytes, as fields."""
    return {
        "rclen": struct.unpack(">I", r[4:8])[0],
        "dclen": struct.unpack(">I", r[8:12])[0],
        "doff": struct.unpack(">I", r[12:16])[0],
        "roff": struct.unpack(">I", r[16:20])[0],
        "type": r[20:24].decode("mac-roman"),
        "creator": r[24:28].decode("mac-roman"),
        "finder": struct.unpack(">H", r[28:30])[0],
        "name": r[37:37 + r[36]].decode("mac-roman", "replace"),
        "ctime": struct.unpack(">I", r[68:72])[0],
        "mtime": struct.unpack(">I", r[72:76])[0],
        "rlen": struct.unpack(">I", r[76:80])[0],
        "dlen": struct.unpack(">I", r[80:84])[0],
        "flags": r[84],
    }


def directory(d):
    """(version, sqp_count, [record]) — the items, from whichever
    directory the expander would read."""
    if len(d) < HDR:
        raise ValueError("shorter than a header")
    sqp_count, version = d[0], d[1]
    if version > 1:
        raise ValueError("version %d is not 0 or 1" % version)
    recs = []
    if version == 0:
        for i in range(sqp_count):
            p = HDR + SQP_REC * i
            r = d[p:p + SQP_REC]
            if len(r) < SQP_REC:
                raise ValueError("directory runs off the end")
            rec = _record(r)
            rec["level"], rec["folder"] = 1, 0
            recs.append(rec)
        return version, sqp_count, recs
    base = SQP_REC * sqp_count + HDR
    if len(d) < base + 12:
        raise ValueError("no second header")
    n = struct.unpack(">I", d[base:base + 4])[0]
    for i in range(n):
        p = base + 12 + HFS_REC * i
        r = d[p:p + HFS_REC]
        if len(r) < HFS_REC:
            raise ValueError("HFS directory runs off the end")
        rec = _record(r[4:])
        rec["level"] = struct.unpack(">H", r[0:2])[0]
        rec["folder"] = struct.unpack(">H", r[2:4])[0]
        recs.append(rec)
    return version, sqp_count, recs


def members_start(version, sqp_count, n):
    """Source: DoSqForward @0xc8e reserves 86 * count, then writes 12
    bytes and reserves 90 * n."""
    if version == 0:
        return HDR + SQP_REC * sqp_count
    return SQP_REC * sqp_count + 22 + HFS_REC * n


def paths(recs):
    """The path of each item, folders applied: CalculateFolderSize
    @0x113c reads the items after a folder whose level is greater as its
    children."""
    out, stack = [], []
    for r in recs:
        del stack[max(r["level"] - 1, 0):]
        name = r["name"].replace("/", ":")
        out.append("/".join(stack + [name]))
        if r["folder"]:
            stack.append(name)
    return out


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

    On a clear code this expander sets the next free code to **256**
    (@0x2ae0), so the clear code's own slot is reused from then on. That
    is what `compress` itself does — `free_ent = FIRST - 1` in
    reference/macutils/macunpack/de_compress.c — and the claim that it
    was a DEVIATION from compress is withdrawn (BLOCKERS.md). What sets
    257 is deark's rendering of the same algorithm, and `src/unc_lzw.c`
    follows deark: the two differ only in a table slot no valid stream
    ever names (DECISIONS.md 2026-10-05).
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


def fork(d, off, clen, elen, stored, stats=None):
    """One fork — the same stored-or-LZW branch for both (DoWork @0x618
    for the data fork, @0x96e for the resource fork)."""
    if elen == 0:
        return b"", "empty"
    raw = d[off:off + clen]
    if stored:
        return raw[:elen], "stored"
    # No limit: the stream has to RUN OUT at the declared length. Passing
    # elen in as a ceiling would make the length check assert a property
    # of this decoder's own truncation and it could never fail.
    return bytes(decompress(raw, stats)), "lzw"


def member(d, rec, stats=None):
    """(data fork, how) and (resource fork, how)."""
    data = fork(d, rec["doff"], rec["dclen"], rec["dlen"],
                rec["flags"] & F_STORED_DATA, stats)
    rsrc = fork(d, rec["roff"], rec["rclen"], rec["rlen"],
                rec["flags"] & F_STORED_RSRC, stats)
    return data, rsrc


# ---------------------------------------------------------------------------
def witness():
    if not os.path.exists(TRANSLATOR):
        print("derive_sqp: no %s — see tools/vmac/README.md, "
              "*The AppleLink package expander*" % TRANSLATOR)
        return 0
    code = open(TRANSLATOR, "rb").read()
    print("AppleLink Package Translator 3.0.3, 'Othe' 1: %d B" % len(code))
    bad = 0
    for at, what, hx in WITNESSES:
        b = bytes.fromhex(hx)
        ok = code[at:at + len(b)] == b
        bad += not ok
        print("  %06x %-3s %s" % (at, "ok" if ok else "NO", what))
    print("derive_sqp: %d of %d witnesses at the offsets claimed"
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
    stored = forks = 0
    for fn in pkgs:
        d = open(os.path.join(SPECIMENS, fn), "rb").read()
        version, sqp_count, recs = directory(d)
        start = members_start(version, sqp_count, len(recs))
        print("%s — %d B, %d item%s, version %d (SQP directory: %d)"
              % (fn, len(d), len(recs), "" if len(recs) == 1 else "s",
                 version, sqp_count))
        print("  SQP directory 0x%x..0x%x, HFS directory 0x%x..0x%x, "
              "members from 0x%x"
              % (HDR, HDR + SQP_REC * sqp_count,
                 SQP_REC * sqp_count + 22, start, start))
        ranges = []
        for r, path in zip(recs, paths(recs)):
            st = {"clears": 0, "n_bits": 0, "free_ent": 0, "codes": 0}
            if r["folder"]:
                print("  %-26s FOLDER, level %d" % (repr(path), r["level"]))
                total += 1
                exact += 1
                continue
            (data, dhow), (rsrc, rhow) = member(d, r, st)
            digest = hashlib.sha256(data).hexdigest()
            want = EXPANDED.get((fn, path))
            ok = (len(data) == r["dlen"] and len(rsrc) == r["rlen"]
                  and (want is None or want == digest))
            total += 1
            exact += ok
            forks += r["rlen"] > 0
            stored += (dhow == "stored") + (rhow == "stored")
            if r["dlen"]:
                ranges.append((r["doff"], r["dclen"]))
            if r["rlen"]:
                ranges.append((r["roff"], r["rclen"]))
            print("  %-26s %s/%s %5d -> %5d B (want %d) %-6s | rsrc %d -> %d "
                  "%-6s %s"
                  % (repr(path), r["type"], r["creator"], r["dclen"],
                     len(data), r["dlen"], dhow, r["rclen"], len(rsrc), rhow,
                     "OK" if ok else "MISMATCH"))
            print("      sha256 %s%s"
                  % (digest, "" if want is None else
                     ("  matches" if want == digest else "  != RECORDED")))
            if dhow == "lzw" or rhow == "lzw":
                widest = max(widest, st["n_bits"])
                clears += st["clears"]
                print("      %d codes; %d clear code(s); widest %d bits; "
                      "table reached %d"
                      % (st["codes"], st["clears"], st["n_bits"],
                         st["free_ent"]))
        end = max((o + n for o, n in ranges), default=start)
        tiled = sum(n for _, n in ranges) == len(d) - start and end == len(d)
        print("  members tile 0x%x..0x%x; file is 0x%x  %s"
              % (start, end, len(d), "exact" if tiled else "!! NOT TILED"))
        if not tiled:
            exact = -1
    print("derive_sqp: %d of %d members expand to their declared length"
          % (exact, total))
    # Say what the specimens do NOT exercise, rather than leaving it to be
    # inferred from a pass (TESTING.md, *AppleLink packages: SqueezePlay*).
    missing = []
    if clears == 0:
        missing.append("the clear code (0 seen)")
    if widest < MAX_BITS:
        missing.append("widths above %d of 13 bits" % widest)
    if forks == 0:
        missing.append("the resource fork")
    if stored == 0:
        missing.append("the stored mode")
    print("derive_sqp: UNEXERCISED by these packages — %s"
          % (", ".join(missing) if missing else "nothing"))
    print("derive_sqp: tools/synth_sqp.py writes each of those, and "
          "tools/run_sqp.py grades the engine on them")
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

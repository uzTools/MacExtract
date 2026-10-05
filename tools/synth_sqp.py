#!/usr/bin/env python3
"""synth_sqp.py — write AppleLink `.pkg` (SqueezePlay) packages.

The two real packages exercise four of the format's paths and not the
rest: no member has a resource fork, none is stored, no LZW stream
reaches a clear code or a 13-bit width, and both are version 1 with no
folder (FORMATS.md, *AppleLink packages*). Nothing on this machine
writes one — the only writer is Aladdin's own translator, which needs a
Macintosh and a package it will not let you choose (BLOCKERS.md) — so
this does, and `tools/run_sqp.py` grades the engine against the bytes
that went in.

**This is an ENCODER read out of the same binary as the decoder, and
that is the whole of its authority.** Every parameter below cites a
routine in `'Othe' 1` of `AppleLink Package Translator` 3.0.3 by name
and offset, the same resource `tools/derive_sqp.py --witness` checks;
the compressor is `Compress` @0x27de and `PutCode` @0x28fe, which are
Unix `compress`'s `compress()` and `output()`, and the container is
`DoSqForward` @0xb60 with `WrSQPDirectory` @0x5f80 and `WrHFSDirectory`
@0x5eb2. What it CANNOT do is prove that Aladdin's expander reads what
it writes: no package these bytes produced has ever been handed to one.
So a pass means the engine agrees with this repository's reading of the
format, not with Aladdin — and the two REAL packages remain the only
authentic bytes anything here is graded on (TESTING.md, *AppleLink
packages*).

    tools/synth_sqp.py --case plain -o out.pkg
    tools/synth_sqp.py --list                  # the cases, one per line
    tools/synth_sqp.py --describe plain        # what a case holds, as JSON

Deterministic: every case is built from a fixed seed, so the same case
is the same bytes for ever (fixtures/SOURCES.md records the sha256).
"""
import argparse
import json
import os
import struct
import sys

# --------------------------------------------------------------------------
# The codec, from the compressor side.
#
# Source: `Compress` @0x27de and `PutCode` @0x28fe. Both are Unix
# compress(1)'s own routines — `compress()` and `output()` — with the
# ratio-watching `cl_block` heuristic LEFT OUT: the only clear this
# writer can emit is the one at @0x28b6, when the table is full. The
# hash table is 8,599 entries (`InitLzw` @0x26b0 allocates 34,396 and
# 17,198 bytes, and `ResetHashTable` @0x2cba fills 8,599 longs with -1),
# and `hshift` is the doubling loop at @0x2632.
HSIZE = 8599
MAXBITS = 13
MAXMAXCODE = 1 << MAXBITS        # @0x288e: cmpiw #8192
CLEAR = 256                      # @0x28c0: pea 0x100
FIRST = 257                      # @0x28ba, @0x25e2
INIT_BITS = 9                    # @0x2620, @0x25b2

LMASK = [0xff, 0xfe, 0xfc, 0xf8, 0xf0, 0xe0, 0xc0, 0x80, 0x00]
RMASK = [0x00, 0x01, 0x03, 0x07, 0x0f, 0x1f, 0x3f, 0x7f, 0xff]


def _hshift():
    """Source: @0x2632 — fcode = HSIZE; while 65536 > fcode: fcode *= 2."""
    n, fcode = 0, HSIZE
    while fcode < 65536:
        n += 1
        fcode += fcode
    return 8 - n


class _Out:
    """PutCode @0x28fe. Codes are packed LSB-first into a buffer of
    n_bits BYTES — eight codes — and the buffer is flushed whole. A
    width change or a clear flushes it early, so the tail of that block
    is padding, and the padding is whatever was left in the buffer: the
    first two stores OR into it and only the last one overwrites, which
    is `output()` byte for byte and is why this keeps the buffer rather
    than clearing it."""

    def __init__(self):
        self.out = bytearray()
        self.buf = bytearray(MAXBITS + 1)
        self.offset = 0
        self.n_bits = INIT_BITS
        self.maxcode = (1 << INIT_BITS) - 1
        self.free_ent = FIRST

    def put(self, code):
        clear_flg = code == CLEAR
        if code < 0:
            # @0x2a30: flush (offset + 7) / 8 bytes and stop.
            if self.offset > 0:
                n = (self.offset + 7) // 8
                self.out += self.buf[:n]
                self.offset = 0
            return
        r_off = self.offset & 7
        bp = self.offset >> 3
        bits = self.n_bits
        v = code
        self.buf[bp] = ((self.buf[bp] & RMASK[r_off]) |
                        ((v << r_off) & LMASK[r_off])) & 0xff
        bp += 1
        bits -= 8 - r_off
        v >>= 8 - r_off
        if bits >= 8:
            self.buf[bp] = v & 0xff
            bp += 1
            v >>= 8
            bits -= 8
        if bits:
            self.buf[bp] = v & 0xff
        self.offset += self.n_bits
        if self.offset == self.n_bits * 8:
            self.out += self.buf[:self.n_bits]
            self.offset = 0
        # @0x29b0: a width change or a clear ends the block early.
        if self.free_ent > self.maxcode or clear_flg:
            if self.offset > 0:
                self.out += self.buf[:self.n_bits]
                self.offset = 0
            if clear_flg:
                self.n_bits = INIT_BITS
                self.maxcode = (1 << INIT_BITS) - 1
            else:
                self.n_bits += 1
                self.maxcode = (MAXMAXCODE if self.n_bits == MAXBITS
                                else (1 << self.n_bits) - 1)


def lzw_compress(data):
    """Compress @0x27de. Returns the code stream."""
    o = _Out()
    if not data:
        o.put(-1)
        return bytes(o.out)
    shift = _hshift()
    htab = [-1] * HSIZE
    codetab = [0] * HSIZE
    ent = data[0]
    for c in data[1:]:
        fcode = (c << MAXBITS) + ent
        # No modulo: hsize is 8,599 and the xor of two 13-bit values is
        # under 8,192, so the index cannot leave the table (@0x2826
        # indexes it straight).
        i = (c << shift) ^ ent
        matched = False
        if htab[i] == fcode:                          # @0x282e
            ent = codetab[i]
            continue
        if htab[i] >= 0:                              # @0x2840: not empty
            disp = HSIZE - i                          # @0x2844
            if i == 0:
                disp = 1
            while True:                               # @0x2858: probe
                i -= disp
                if i < 0:
                    i += HSIZE
                if htab[i] == fcode:                  # @0x286e
                    ent = codetab[i]
                    matched = True
                    break
                if htab[i] <= 0:                      # @0x287e: bgt probes on
                    break
        if matched:
            continue
        o.put(ent)                                    # @0x2882
        ent = c
        if o.free_ent < MAXMAXCODE:                   # @0x288e
            codetab[i] = o.free_ent
            o.free_ent += 1
            htab[i] = fcode
        else:
            # @0x28b6: the table is full — reset it, and say so. This is
            # the ONLY clear this writer emits; `compress`'s ratio test
            # is not in this binary.
            # ResetHashTable clears htab alone; codetab is only ever
            # read where htab matched, so it is left as it is.
            htab = [-1] * HSIZE
            o.free_ent = FIRST
            o.put(CLEAR)
    o.put(ent)                                        # @0x28d6
    o.put(-1)                                         # @0x28de
    return bytes(o.out)


# --------------------------------------------------------------------------
# The container.
#
# Source: DoSqForward @0xb60 writes the 10-byte header (count byte,
# version 1, eight bytes), reserves 86 * count, writes the 12-byte
# second header (a u32 count and eight bytes) and reserves 90 * count;
# WrSQPDirectory @0x5f80 writes record i at 86 * i + 10 and
# WrHFSDirectory @0x5eb2 writes its own at 86 * count + 22 + 90 * i,
# four bytes of level and folder flag ahead of the same 86. The count
# byte is min(GetItemCount(), 50) @0xc46 and the SQP directory holds
# only the FILES — DoItemsForward @0x1d5e skips a folder and anything
# typed 'HBSF', 'PIT ' or 'SIT!' — so its unwritten slots stay zero.
HDR = 10
SQP_REC = 86
HFS_REC = 90
SQP_MAX = 50
F_STORED_DATA = 1 << 1           # DoWork @0x618, btst #1 on the BYTE at +84
F_STORED_RSRC = 1 << 2           # DoWork @0x96e, btst #2 on the same byte
F_DEFAULT = 0x80                 # InitSqp @0x5d56, bset #7 — never tested
SKIP_TYPES = (b"HBSF", b"PIT ", b"SIT!")

PKG_TYPE = b"HBSF"               # DoSqForward @0xbea: Create('HBSF','GEOL')
PKG_CREATOR = b"GEOL"


def _record(it, data_off, data_clen, rsrc_off, rsrc_clen, flags):
    """One 86-byte SQP record."""
    r = bytearray(SQP_REC)
    struct.pack_into(">I", r, 0, 0)                    # +0: zeroed @0x239c
    struct.pack_into(">I", r, 4, rsrc_clen)
    struct.pack_into(">I", r, 8, data_clen)
    struct.pack_into(">I", r, 12, data_off)
    struct.pack_into(">I", r, 16, rsrc_off)
    r[20:24] = it["type"]
    r[24:28] = it["creator"]
    struct.pack_into(">H", r, 28, it["finder"])        # the FInfo, 16 bytes
    name = it["name"].encode("mac-roman")[:31]
    r[36] = len(name)
    r[37:37 + len(name)] = name
    struct.pack_into(">I", r, 68, it["ctime"])
    struct.pack_into(">I", r, 72, it["mtime"])
    struct.pack_into(">I", r, 76, len(it["rsrc"]))
    struct.pack_into(">I", r, 80, len(it["data"]))
    r[84] = flags
    r[85] = 0
    return bytes(r)


def _encode_fork(raw):
    """One fork, as DoWork @0x4d0 writes it: compressed unless that
    saved nothing, in which case stored and the flag set."""
    if not raw:
        return b"", False
    packed = lzw_compress(raw)
    if len(raw) - len(packed) >= 1:
        return packed, False
    return raw, True


def build(items, version=1):
    """The package. `items` are dicts; see CASES below for the shape."""
    if version not in (0, 1):
        raise ValueError("version must be 0 or 1")
    if version == 0 and any(it["folder"] for it in items):
        # ReadFileAndBuildLinkedList @0x31be gives every version-0 item
        # level 1 and no folder flag, so a tree cannot be expressed.
        raise ValueError("a version-0 package is flat")

    # What each member's two forks weigh, in record order.
    enc = []
    for it in items:
        if it["folder"]:
            enc.append((b"", False, b"", False))
            continue
        d, ds = _encode_fork(it["data"])
        r, rs = _encode_fork(it["rsrc"])
        enc.append((d, ds, r, rs))

    sqp_items = [i for i, it in enumerate(items)
                 if not it["folder"] and it["type"] not in SKIP_TYPES]
    count_byte = min(len(items), SQP_MAX)
    if version == 0:
        count_byte = len(items)
        sqp_items = list(range(len(items)))
        start = HDR + SQP_REC * count_byte
    else:
        start = SQP_REC * count_byte + 22 + HFS_REC * len(items)

    # Place the members: each fork in record order, contiguous from
    # `start`, so the directory tiles the file to its last byte — which
    # is what both real packages do and what the sniffer requires.
    at = start
    place = []
    for d, ds, r, rs in enc:
        doff = at if d else 0
        at += len(d)
        roff = at if r else 0
        at += len(r)
        place.append((doff, len(d), roff, len(r)))

    out = bytearray()
    out += bytes([count_byte, version]) + b"\0" * 8
    sqp = bytearray(SQP_REC * count_byte)
    for slot, idx in enumerate(sqp_items[:count_byte]):
        d, ds, r, rs = enc[idx]
        doff, dlen, roff, rlen = place[idx]
        flags = F_DEFAULT | (F_STORED_DATA if ds else 0) | \
                (F_STORED_RSRC if rs else 0)
        sqp[SQP_REC * slot:SQP_REC * (slot + 1)] = _record(
            items[idx], doff, dlen, roff, rlen, flags)
    out += sqp
    if version == 1:
        out += struct.pack(">I", len(items)) + b"\0" * 8
        for idx, it in enumerate(items):
            d, ds, r, rs = enc[idx]
            doff, dlen, roff, rlen = place[idx]
            flags = F_DEFAULT | (F_STORED_DATA if ds else 0) | \
                    (F_STORED_RSRC if rs else 0)
            out += struct.pack(">HH", it["level"], 1 if it["folder"] else 0)
            out += _record(it, doff, dlen, roff, rlen, flags)
    if len(out) != start:
        raise AssertionError("directory is %d B, expected %d"
                             % (len(out), start))
    for idx in range(len(items)):
        d, ds, r, rs = enc[idx]
        out += d
        out += r
    return bytes(out)


# --------------------------------------------------------------------------
# Content. Deterministic, and shaped to reach a named path.
def _lcg(n, seed):
    """Incompressible bytes: compress(1) on these writes MORE than it
    reads, which is what makes a member STORED without forcing a flag."""
    out = bytearray(n)
    x = seed & 0xFFFFFFFF
    for i in range(n):
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        out[i] = (x >> 16) & 0xFF
    return bytes(out)


def _text(n, seed):
    """Compressible Mac-Roman text."""
    words = ["AppleLink", "package", "SqueezePlay", "Aladdin", "expand",
             "memo", "Tuesday", "February", "1992", "the", "and", "of"]
    out = bytearray()
    x = seed
    while len(out) < n:
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        out += words[(x >> 16) % len(words)].encode("mac-roman") + b" "
        if (x >> 8) & 7 == 0:
            out += b"\r"
    return bytes(out[:n])


def _wide(n, seed):
    """Enough distinct strings to fill the 8,192-entry table and clear
    it: a stream of bytes with just enough structure to define a new
    code almost every time."""
    out = bytearray()
    x = seed & 0xFFFFFFFF
    while len(out) < n:
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        out += bytes([(x >> 16) & 0x3F, (x >> 22) & 0x3F, 0x20])
    return bytes(out[:n])


def item(name, data=b"", rsrc=b"", type=b"TEXT", creator=b"ttxt",
         finder=0, ctime=0xA5BDA166, mtime=0xA5BDA166, folder=False,
         level=1):
    if folder:
        # The 16 bytes at record +20 are the Finder info PBGetCatInfo
        # returned (AddItems @0x2378 copies all 16), and for a directory
        # that is a DInfo: the first eight bytes are the folder's window
        # rectangle, not a type and a creator. Zero here, and the engine
        # reports a folder's type and creator as unknown.
        type = creator = b"\0\0\0\0"
    return {"name": name, "data": data, "rsrc": rsrc, "type": type,
            "creator": creator, "finder": finder, "ctime": ctime,
            "mtime": mtime, "folder": folder, "level": level}


def case_plain():
    """The specimens' shape: version 1, LZW data forks, no resource
    fork, no stored member."""
    return [item("FileMaker Import", _text(3098, 1), creator=b"MACA"),
            item("Package Data", _text(3097, 2), creator=b"MACA"),
            item("Trademark Data", _text(4579, 3), creator=b"MACA")], 1


def case_forks():
    """A resource fork on every member, and one member that is nothing
    but a resource fork — the path `rlen` = 0 leaves unreached in both
    real packages."""
    return [item("Both Forks", _text(2000, 11), _text(1500, 12)),
            item("Resource Only", b"", _text(900, 13), type=b"FKEY",
                 creator=b"MACS"),
            item("Data Only", _text(700, 14))], 1


def case_stored():
    """Incompressible forks, so the writer's own rule stores them: bit 1
    of the record's flag byte for the data fork, bit 2 for the resource
    fork (DoWork @0x618, @0x96e)."""
    return [item("Random Data", _lcg(2048, 21), _lcg(1024, 22)),
            item("Mixed", _text(1200, 23), _lcg(600, 24)),
            item("Tiny", b"!", b"")], 1


def case_clear():
    """Long enough to fill the table and clear it, which also takes the
    code width to 13 — the two paths no real package reaches."""
    # 36,000 bytes reaches the ceiling twice: 18,738 codes, 13 bits, and
    # TWO clears, so the second generation's own clear is exercised too.
    return [item("Table Filler", _wide(36000, 31)),
            item("Short After", _text(300, 32))], 1


def case_v0():
    """Version 0: no HFS directory at all, records at +10
    (ReadFileAndBuildLinkedList @0x3092)."""
    return [item("Flat One", _text(1500, 41)),
            item("Flat Two", _text(900, 42), _text(400, 43))], 0


def case_folder():
    """A tree. The HFS directory's four extra bytes are a level and a
    folder flag (RdHFSDirectory @0x5e06; CalculateFolderSize @0x113c
    reads the nodes after a folder whose level is greater as its
    children), and the SQP directory skips folders — so its first slot
    stays zero here."""
    return [item("Top", _text(500, 51)),
            item("Folder", folder=True),
            item("Inside", _text(800, 52), level=2),
            item("Deeper", folder=True, level=2),
            item("Bottom", _text(600, 53), _text(200, 54), level=3),
            item("After", _text(400, 55))], 1


CASES = {
    "plain": case_plain,
    "forks": case_forks,
    "stored": case_stored,
    "clear": case_clear,
    "v0": case_v0,
    "folder": case_folder,
}


def describe(name):
    items, version = CASES[name]()
    out = {"case": name, "version": version, "entries": []}
    for it in items:
        if it["folder"]:
            out["entries"].append({"name": it["name"], "folder": True,
                                   "level": it["level"]})
            continue
        d, ds = _encode_fork(it["data"])
        r, rs = _encode_fork(it["rsrc"])
        out["entries"].append({
            "name": it["name"], "level": it["level"],
            "type": it["type"].decode("ascii"),
            "creator": it["creator"].decode("ascii"),
            "data_size": len(it["data"]), "rsrc_size": len(it["rsrc"]),
            "data_stored": ds, "rsrc_stored": rs,
            "data_packed": len(d), "rsrc_packed": len(r),
        })
    return out


def paths(items, version):
    """(path, item) for each entry, with folders applied — the names the
    engine is expected to report."""
    out, stack = [], []
    for it in items:
        if version == 1:
            del stack[max(it["level"] - 1, 0):]
        name = it["name"].replace("/", ":")
        out.append(("/".join(stack + [name]), it))
        if it["folder"]:
            stack.append(name)
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default="plain", choices=sorted(CASES))
    ap.add_argument("-o", "--out")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--describe", metavar="CASE")
    a = ap.parse_args()
    if a.list:
        for name in sorted(CASES):
            print(name)
        return 0
    if a.describe:
        print(json.dumps(describe(a.describe), indent=1, sort_keys=True))
        return 0
    items, version = CASES[a.case]()
    blob = build(items, version)
    if a.out:
        d = os.path.dirname(a.out)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(a.out, "wb") as f:
            f.write(blob)
        print("synth_sqp: %s — %d B, %d item%s, version %d"
              % (a.out, len(blob), len(items),
                 "" if len(items) == 1 else "s", version))
    else:
        sys.stdout.buffer.write(blob)
    return 0


if __name__ == "__main__":
    sys.exit(main())

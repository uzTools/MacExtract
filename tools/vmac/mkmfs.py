#!/usr/bin/env python3
"""mkmfs.py — build (and read back) a 400K MFS floppy image.

MFS is the file system a 64K-ROM Macintosh has: a true Macintosh 512K reads
nothing else, so the only way to put this application in front of one is to
write the volume here. Retro68 cannot: `--cc name.dsk` calls libhfs and always
produces an 800K HFS volume, which that ROM Sad Macs on
(FORMATS.md, *A true Macintosh 512K*).

Structure — Source: Inside Macintosh, Volume II (1985), "Data Organization on
Volumes", pp. II-119..II-123, Figures 6, 7 and 8:

    logical block 0,1   system startup information (the boot blocks)
    logical block 2,3   master directory block: 64 bytes of volume
                        information, then the volume allocation block map,
                        12 bits per allocation block, first entry for
                        allocation block 2
    logical block 4..   file directory, one variable-length entry per file
    logical block 16..  allocation blocks, numbered from 2

The GEOMETRY of a 400K volume (drDirSt 4, drBlLen 12, drNmAlBlks 391,
drAlBlkSiz 1024, drClpSiz 8192, drAlBlSt 16) is not in the book; it is read
off an Apple-initialized 400K volume, Sys11.img, and `--list` prints the same
fields from any image so the two can be compared.

MacBinary header offsets — Source: src/fmt_macbinary.c, itself transcribed
from reference/XADMaster/XADMacArchiveParser.m.

    mkmfs.py out.img --name "MacExtract" dist/MacExtract.bin
    mkmfs.py --list out.img
    mkmfs.py --extract System Sys11.img System.bin       # lift a file out
    mkmfs.py out.img --boot Sys11.img --shell TrapTest System.bin app.bin
    mkmfs.py out.img --boot Sys30.img System.bin probe.bin:Finder
"""

import argparse
import struct
import sys
import time

BLOCK = 512
SIG = 0xD2D7                    # drSigWord, "always $0207" in the book's
                                # figure — a scanning error for $D2D7, the
                                # value the VCB structure on II-125 gives and
                                # the value every real volume carries.

# 400K geometry, read off an Apple-initialized volume (see the docstring).
G400 = dict(dir_st=4, bl_len=12, n_alloc=391, al_blk_siz=1024, clp_siz=8192,
            al_bl_st=16, blocks=800)

MAC_EPOCH_DELTA = 2082844800    # 1904-01-01 .. 1970-01-01, in seconds


def mactime(unix=None):
    return int((unix if unix is not None else time.time()) + MAC_EPOCH_DELTA)


# ---------------------------------------------------------------- MacBinary

class MacFile:
    """One file: name, type, creator, Finder flags, both forks."""

    def __init__(self, name, type_, creator, flags, data, rsrc,
                 crdat=None, mddat=None):
        self.name, self.type, self.creator = name, type_, creator
        self.flags, self.data, self.rsrc = flags, data, rsrc
        self.crdat = crdat or mactime()
        self.mddat = mddat or self.crdat

    @classmethod
    def from_macbinary(cls, path, name=None):
        b = open(path, "rb").read()
        if len(b) < 128:
            raise SystemExit(f"mkmfs: {path} is too short for MacBinary")
        nlen = b[1]
        if not 1 <= nlen <= 63:
            raise SystemExit(f"mkmfs: {path} has no MacBinary name length")
        mbname = b[2:2 + nlen].decode("mac_roman")
        type_, creator = b[65:69], b[69:73]
        flags = struct.unpack(">H", bytes([b[73], b[101]]))[0]
        dlen, rlen = struct.unpack(">II", b[83:91])
        crdat, mddat = struct.unpack(">II", b[91:99])
        start = 128 + ((struct.unpack(">H", b[120:122])[0] + 127) & ~127)
        data = b[start:start + dlen]
        rsrc_at = start + ((dlen + 127) & ~127)
        rsrc = b[rsrc_at:rsrc_at + rlen]
        if len(data) != dlen or len(rsrc) != rlen:
            raise SystemExit(f"mkmfs: {path} is truncated")
        return cls(name or mbname, type_, creator, flags, data, rsrc,
                   crdat or None, mddat or None)


# ------------------------------------------------------------- the 12-bit map

def map_pack(entries, nbytes):
    """Pack 12-bit entries, two to three bytes, into nbytes."""
    out = bytearray(nbytes)
    for i, e in enumerate(entries):
        off = (i * 3) // 2
        if i % 2 == 0:
            out[off] = (e >> 4) & 0xFF
            out[off + 1] = (out[off + 1] & 0x0F) | ((e & 0x0F) << 4)
        else:
            out[off] = (out[off] & 0xF0) | ((e >> 8) & 0x0F)
            out[off + 1] = e & 0xFF
    return bytes(out)


def map_unpack(buf, count):
    out = []
    for i in range(count):
        off = (i * 3) // 2
        if i % 2 == 0:
            out.append((buf[off] << 4) | (buf[off + 1] >> 4))
        else:
            out.append(((buf[off] & 0x0F) << 8) | buf[off + 1])
    return out


# --------------------------------------------------------------------- build

def build(files, volname, bootblocks=None, geom=G400):
    size = geom["blocks"] * BLOCK
    img = bytearray(size)
    per_alloc = geom["al_blk_siz"] // BLOCK

    if bootblocks:
        img[0:2 * BLOCK] = bootblocks[:2 * BLOCK]

    # Allocation blocks are numbered from 2 (0 and 1 mean "unused" and "last
    # block of the file" in the map), so entry i of the map describes block
    # i + 2 — II-122.
    amap = [0] * geom["n_alloc"]
    next_free = 2

    def put_fork(payload):
        """Write one fork, chain its blocks, return its first block or 0."""
        nonlocal next_free
        if not payload:
            return 0, 0
        nblk = (len(payload) + geom["al_blk_siz"] - 1) // geom["al_blk_siz"]
        first = next_free
        for k in range(nblk):
            blk = first + k
            if blk - 2 >= geom["n_alloc"]:
                raise SystemExit("mkmfs: volume full")
            start = (geom["al_bl_st"] + (blk - 2) * per_alloc) * BLOCK
            chunk = payload[k * geom["al_blk_siz"]:(k + 1) * geom["al_blk_siz"]]
            img[start:start + len(chunk)] = chunk
            amap[blk - 2] = 1 if k == nblk - 1 else blk + 1
        next_free += nblk
        return first, nblk * geom["al_blk_siz"]

    entries = []
    for fnum, f in enumerate(files, start=1):
        dstart, dphys = put_fork(f.data)
        rstart, rphys = put_fork(f.rsrc)
        name = f.name.encode("mac_roman")[:255]
        e = bytearray()
        e += bytes([0x80, 0])                       # flFlags (used), flTyp
        e += f.type + f.creator + struct.pack(">H", f.flags) + b"\0" * 6
        e += struct.pack(">IHIIHII", fnum, dstart, len(f.data), dphys,
                         rstart, len(f.rsrc), rphys)
        e += struct.pack(">II", f.crdat, f.mddat)
        e += bytes([len(name)]) + name
        if len(e) % 2:
            e += b"\0"
        entries.append(bytes(e))

    # "Entries are always an integral number of words and don't cross logical
    # block boundaries" — II-122.
    dir_blocks = [bytearray(BLOCK) for _ in range(geom["bl_len"])]
    at = [0] * geom["bl_len"]
    for e in entries:
        for i in range(geom["bl_len"]):
            if at[i] + len(e) <= BLOCK:
                dir_blocks[i][at[i]:at[i] + len(e)] = e
                at[i] += len(e)
                break
        else:
            raise SystemExit("mkmfs: file directory full")
    for i, b in enumerate(dir_blocks):
        off = (geom["dir_st"] + i) * BLOCK
        img[off:off + BLOCK] = b

    now = mactime()
    vn = volname.encode("mac_roman")[:27]
    mdb = struct.pack(">HIIHHHHHIIHIH", SIG, now, 0, 0, len(files),
                      geom["dir_st"], geom["bl_len"], geom["n_alloc"],
                      geom["al_blk_siz"], geom["clp_siz"], geom["al_bl_st"],
                      len(files) + 1, sum(1 for e in amap if e == 0))
    mdb += bytes([len(vn)]) + vn
    img[2 * BLOCK:2 * BLOCK + len(mdb)] = mdb
    # The map begins at byte 64 of the master directory block and runs on
    # into logical block 3 — II-122.
    packed = map_pack(amap, 2 * BLOCK - 64)
    img[2 * BLOCK + 64:2 * BLOCK + 64 + len(packed)] = packed
    return bytes(img)


# ---------------------------------------------------------------------- read

def entries_of(img):
    """Yield one dict per file in the file directory."""
    dirst, bllen = struct.unpack(">HH", img[2 * BLOCK + 14:2 * BLOCK + 18])
    for i in range(bllen):
        blk = img[(dirst + i) * BLOCK:(dirst + i + 1) * BLOCK]
        at = 0
        while at + 51 <= BLOCK and blk[at] & 0x80:
            nlen = blk[at + 50]
            yield dict(
                name=blk[at + 51:at + 51 + nlen].decode("mac_roman"),
                type=blk[at + 2:at + 6], creator=blk[at + 6:at + 10],
                flags=struct.unpack(">H", blk[at + 10:at + 12])[0],
                nums=struct.unpack(">IHIIHII", blk[at + 18:at + 42]),
                dates=struct.unpack(">II", blk[at + 42:at + 50]))
            at += (51 + nlen + 1) & ~1


def read_fork(img, first, length):
    """Follow one fork's chain through the block map."""
    alblksiz, = struct.unpack(">I", img[2 * BLOCK + 20:2 * BLOCK + 24])
    nmalblks, = struct.unpack(">H", img[2 * BLOCK + 18:2 * BLOCK + 20])
    alblst, = struct.unpack(">H", img[2 * BLOCK + 28:2 * BLOCK + 30])
    amap = map_unpack(img[2 * BLOCK + 64:4 * BLOCK], nmalblks)
    per = alblksiz // BLOCK
    out, blk = bytearray(), first
    while blk >= 2 and len(out) < length:
        off = (alblst + (blk - 2) * per) * BLOCK
        out += img[off:off + alblksiz]
        nxt = amap[blk - 2]
        if nxt == 1:
            break
        blk = nxt
    return bytes(out[:length])


def extract(image, name, out):
    """Write one file out as MacBinary I (no CRC; mkmfs reads it back)."""
    img = open(image, "rb").read()
    for e in entries_of(img):
        if e["name"] != name:
            continue
        fnum, dstart, dlen, dphys, rstart, rlen, rphys = e["nums"]
        data = read_fork(img, dstart, dlen) if dstart else b""
        rsrc = read_fork(img, rstart, rlen) if rstart else b""
        nm = name.encode("mac_roman")[:63]
        h = bytearray(128)
        h[1] = len(nm)
        h[2:2 + len(nm)] = nm
        h[65:69], h[69:73] = e["type"], e["creator"]
        h[73], h[101] = e["flags"] >> 8, e["flags"] & 0xFF
        struct.pack_into(">II", h, 83, dlen, rlen)
        struct.pack_into(">II", h, 91, *e["dates"])
        with open(out, "wb") as f:
            f.write(h)
            f.write(data + b"\0" * (-len(data) % 128))
            f.write(rsrc + b"\0" * (-len(rsrc) % 128))
        print(f"mkmfs: {name!r} -> {out} (data {dlen}, rsrc {rlen})")
        return 0
    print(f"mkmfs: {image} has no file named {name!r}", file=sys.stderr)
    return 1


def dump(path):
    img = open(path, "rb").read()
    (sig, crdate, lsbkup, atrb, nmfls, dirst, bllen, nmalblks, alblksiz,
     clpsiz, alblst, nxtfnum, freebks) = struct.unpack(
         ">HIIHHHHHIIHIH", img[2 * BLOCK:2 * BLOCK + 36])
    vnlen = img[2 * BLOCK + 36]
    vn = img[2 * BLOCK + 37:2 * BLOCK + 37 + vnlen].decode("mac_roman")
    if sig != SIG:
        print(f"{path}: not MFS (signature {sig:#06x})")
        return 1
    print(f"{path}: MFS volume {vn!r}, {len(img)} bytes")
    print(f"  drNmFls {nmfls}  drDirSt {dirst}  drBlLen {bllen}  "
          f"drNmAlBlks {nmalblks}  drAlBlkSiz {alblksiz}")
    print(f"  drClpSiz {clpsiz}  drAlBlSt {alblst}  drNxtFNum {nxtfnum}  "
          f"drFreeBks {freebks}  drAtrb {atrb:#06x}")
    amap = map_unpack(img[2 * BLOCK + 64:4 * BLOCK], nmalblks)

    def chain(first):
        out, b = [], first
        while b >= 2 and len(out) < nmalblks + 1:
            out.append(b)
            b = amap[b - 2]
            if b == 1:
                break
        return out

    for e in entries_of(img):
        fnum, dstart, dlen, dphys, rstart, rlen, rphys = e["nums"]
        print(f"  {e['name']:<32} {e['type'].decode('mac_roman')}/"
              f"{e['creator'].decode('mac_roman')} #{fnum} "
              f"data {dlen}@{dstart}{chain(dstart) if dstart else []} "
              f"rsrc {rlen}@{rstart}{chain(rstart) if rstart else []}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("image")
    ap.add_argument("files", nargs="*",
                    help="MacBinary files to put on it, each optionally "
                         "PATH:MACNAME to land under a different name — the "
                         "same spelling mkboot.py uses")
    ap.add_argument("--name", default="Untitled", help="volume name")
    ap.add_argument("--boot", help="image to copy logical blocks 0-1 from, "
                                   "which is what makes the volume bootable")
    ap.add_argument("--shell", help="rewrite the boot blocks' shell name, so "
                                    "the ROM launches this application "
                                    "instead of the Finder")
    ap.add_argument("--extract", metavar="NAME",
                    help="pull NAME out of the image as MacBinary; the "
                         "remaining positional argument is the output file")
    ap.add_argument("--list", action="store_true", help="read one back")
    a = ap.parse_args()
    if a.list:
        return dump(a.image)
    if a.extract:
        if len(a.files) != 1:
            raise SystemExit("mkmfs: --extract needs exactly one output file")
        return extract(a.image, a.extract, a.files[0])
    boot = None
    if a.boot:
        boot = bytearray(open(a.boot, "rb").read(2 * BLOCK))
        if boot[0:2] != b"LK":
            raise SystemExit(f"mkmfs: {a.boot} has no 'LK' boot blocks")
        if a.shell:
            # Boot block layout: Inside Macintosh II-83, "The Boot Blocks" —
            # the same Str15 field tools/vmac/mkboot.py rewrites on HFS.
            nm = a.shell.encode("mac_roman")
            if len(nm) > 15:
                raise SystemExit("mkmfs: shell name exceeds 15 bytes")
            boot[0x1A] = len(nm)
            boot[0x1B:0x2A] = nm.ljust(15, b"\0")
        boot = bytes(boot)
    elif a.shell:
        raise SystemExit("mkmfs: --shell needs --boot")
    files = []
    for spec in a.files:
        path, _, macname = spec.partition(":")
        files.append(MacFile.from_macbinary(path, macname or None))
    open(a.image, "wb").write(build(files, a.name, boot))
    print(f"mkmfs: wrote {a.image} — {len(files)} file(s), volume {a.name!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

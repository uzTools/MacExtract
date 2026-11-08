#!/usr/bin/env python3
"""synth_dd.py — write DiskDoubler `DDAR` and `DDA2` archives.

The corpus's nine real DiskDoubler archives reach one folder between
them: the four `DDAR` ones are flat, and the five `DDA2` ones hold a
single `sources` folder at one level. So the two directory walks
`src/fmt_dd.c` implements — `DDAR`'s isdir/enddir records and `DDA2`'s
dirlevel counter — were read from the reference and never run against a
tree with anything in it.

This writes those trees. `unar` grades them: XADDiskDoublerParser.m is
what both walks were transcribed from, and it reads every record shape
written here, so a disagreement about a path is a disagreement between
two implementations rather than with ourselves.

  Source: reference/XADMaster/XADDiskDoublerParser.m  parseArchive
          (the 124-byte `DDAR` record, its 63-byte name, isdir/enddir,
          and the stored-in-archive branch at finderflags & 0x20)
  Source: reference/XADMaster/XADDiskDoublerParser.m  parseArchive2
          (the `DDA2` record, its 31-byte name, entrytype, and
          dirlevel - 2)
  Source: reference/XADMaster/XADDiskDoublerParser.m
          parseFileHeaderWithHandle (the 80 bytes after 0xABCD0054)

Field VALUES that neither reader reads — the archive headers both walks
skip, and the name an enddir record carries — are written as zero or as
the folder's own name; no specimen says what DiskDoubler puts there, and
nothing here or in the reference looks.

What this cannot see: whether DiskDoubler itself writes the trees this
way. Both readers agree on what the records mean, and only a deep
archive written by DiskDoubler could say that the records are what it
would have written (OPEN_ITEMS.md).
"""
import os
import struct

FILEHDR = 80                  # after the 0xABCD0054 magic
DDAR_REC = 124                # magic + 120
MAGIC = 0xABCD0054


def u16(v):
    return struct.pack(">H", v & 0xFFFF)


def u32(v):
    return struct.pack(">I", v & 0xFFFFFFFF)


def crc16(data):
    """CRC-16/XModem, big-endian at the end of every header a
    DiskDoubler file starts with: 76 bytes for `DDAR`, 60 for `DDA2`,
    82 for a 0xABCD0054 file header. XADMaster's table is the 0x1021
    table byte-swapped and it compares against the stored value
    byte-swapped too, which is this. Checked against all nine specimens.
    Source: XADDiskDoublerParser.m recognizeFileWithHandle."""
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def sum16(data):
    """The checksum methods 0..5 carry: a 16-bit sum of the fork's
    bytes. Source: XADDiskDoublerParser.m handleForEntryWithDictionary,
    XADChecksumHandle mask:0xffff."""
    return sum(data) & 0xFFFF


# A 1990 date in Macintosh epoch seconds, which is what the specimens
# carry; the value is never compared, only carried through.
MTIME = 0xE0364FA6
CTIME = 0xE0364F79


def folder(name, children):
    return {"name": name, "isdir": True, "children": children}


def file(name, data=b"", rsrc=b"", stored=False, typ=b"TEXT",
         creator=b"UNCL"):
    """One file. `stored` picks the record that holds its forks with no
    file header of its own — `DDAR`'s finderflags & 0x20 branch."""
    return {"name": name, "isdir": False, "data": data, "rsrc": rsrc,
            "stored": stored, "typ": typ, "creator": creator}


def expected(tree):
    """path -> (data, rsrc) for every file, path -> None for every
    folder. The same shape synth_now.expected() returns."""
    out = {}

    def walk(node, prefix):
        path = prefix + node["name"]
        if node["isdir"]:
            out[path] = None
            for child in node["children"]:
                walk(child, path + "/")
        else:
            out[path] = (node["data"], node["rsrc"])
    for node in tree:
        walk(node, "")
    return out


# ------------------------------------------------------------------
# 'DDAR'
# ------------------------------------------------------------------

def _ddar_record(name, isdir=0, enddir=0, datasize=0, rsrcsize=0,
                 typ=b"TEXT", creator=b"UNCL", finderflags=0x0100,
                 datacrc=0, rsrccrc=0):
    """One 124-byte record: a Pascal-style name in a fixed 63-byte
    field at +8, and at +74 the ENTRY's whole span.

    `datasize` was the uncompressed data fork's length here until
    2026-09-22, which is not what DiskDoubler writes and which nothing
    read — the walk stepped by the file header's own arithmetic
    instead. An archive DiskDoubler 3.7's Combine command wrote here
    settled it: +74 is what a walk steps by, and +78 is 0 in all 44
    records on this disk (docs/formats/diskdoubler-container.md,
    "DDAR"). These archives say so now, so they can be fed to a reader
    that believes the field."""
    r = bytearray(DDAR_REC)
    r[0:4] = b"DDAR"
    n = name[:63]
    r[8] = len(n)
    r[9:9 + len(n)] = n
    r[72] = isdir
    r[73] = enddir
    r[74:78] = u32(datasize)
    r[78:82] = u32(rsrcsize)
    r[82:86] = u32(CTIME)
    r[86:90] = u32(MTIME)
    r[90:94] = typ
    r[94:98] = creator
    r[98:100] = u16(finderflags)
    r[118:120] = u16(datacrc)
    r[120:122] = u16(rsrccrc)
    return bytes(r)


def _file_header(data, rsrc, typ, creator, finderflags=0x0100):
    """The 84 bytes of 0xABCD0054 + the 80-byte file header, method 0
    for both forks. info1 is 0, which is below the 0x2a that turns
    method 1's obfuscation on, so the forks are written as they are."""
    h = bytearray(FILEHDR)
    h[0:4] = u32(len(data))
    h[4:8] = u32(len(data))        # stored: compressed length is the length
    h[8:12] = u32(len(rsrc))
    h[12:16] = u32(len(rsrc))
    h[16] = 0                      # data method 0
    h[17] = 0                      # resource method 0
    h[18] = 0                      # info1
    h[20:24] = u32(MTIME)
    h[24:28] = u32(CTIME)
    h[28:32] = typ
    h[32:36] = creator
    h[36:38] = u16(finderflags)
    h[44:46] = u16(sum16(data))
    h[46:48] = u16(sum16(rsrc))
    h[48] = 0                      # info2
    h[50:52] = u16(0)              # data delta
    h[52:54] = u16(0)              # resource delta
    h[74:76] = u16(sum16(data))
    h[76:78] = u16(sum16(rsrc))
    out = bytearray(u32(MAGIC) + bytes(h))
    out[82:84] = u16(crc16(out[:82]))     # what the recogniser checks
    return bytes(out)


def build_ddar(tree):
    """Depth-first: a folder is one record, its children follow, and an
    enddir record closes it."""
    out = bytearray(b"DDAR" + bytes(74))
    out[76:78] = u16(crc16(out[:76]))     # the rest of the header is unread

    def emit(node):
        if node["isdir"]:
            out.extend(_ddar_record(node["name"].encode("mac-roman"),
                                    isdir=1))
            for child in node["children"]:
                emit(child)
            # The name an enddir record carries is not read by either
            # implementation; the folder's own is the readable choice.
            out.extend(_ddar_record(node["name"].encode("mac-roman"),
                                    enddir=1))
            return
        data, rsrc = node["data"], node["rsrc"]
        name = node["name"].encode("mac-roman")
        if node["stored"]:
            out.extend(_ddar_record(name, datasize=len(data),
                                    rsrcsize=len(rsrc), typ=node["typ"],
                                    creator=node["creator"],
                                    finderflags=0x0120,
                                    datacrc=sum16(data),
                                    rsrccrc=sum16(rsrc)))
            out.extend(data)
            out.extend(rsrc)
            return
        # The span of a record with a file header behind it: that
        # header, then both compressed forks. A real DiskDoubler file
        # may carry a copy of its header at the end and then the span
        # is 84 bytes more; an archive Combine wrote itself carries
        # none, and neither do these.
        # The record is the STORED file's catalog entry, and a file
        # DiskDoubler compressed is creator DDAP, its own type and creator
        # inside the header below: DDF0/DDAP is two records of
        # Symantec's DD3.7.7AuxFiles.dd (fixtures/im2-DD3.7.7AuxFiles.dd;
        # docs/formats/diskdoubler-container.md, "DDAR"). These wrote the
        # entry's own pair here until 2026-10-25, which a reader that
        # expands only DDAP records takes for a file stored as it was.
        out.extend(_ddar_record(name, datasize=FILEHDR + 4 + len(data) + len(rsrc),
                                rsrcsize=0, typ=b"DDF0", creator=b"DDAP"))
        out.extend(_file_header(data, rsrc, node["typ"], node["creator"]))
        out.extend(data)
        out.extend(rsrc)

    for node in tree:
        emit(node)
    return bytes(out)


# ------------------------------------------------------------------
# 'DDA2'
# ------------------------------------------------------------------

DDA2_REC = 46                 # up to and including totalsize
DDA2_DIR = 88                 # what DiskDoubler Pro 4.1.1 writes
DDA2_FILE = 60                # record + 10 unused + the 0xABCD0054 magic


def _dda2_record(name, entrytype, dirlevel, totalsize):
    r = bytearray(DDA2_REC)
    r[0:4] = b"DDA2"
    r[4:6] = u16(entrytype)
    n = name[:31]
    r[6] = len(n)
    r[7:7 + len(n)] = n
    r[38:42] = u32(dirlevel + 2)      # both walks subtract 2
    r[42:46] = u32(totalsize)
    return bytes(r)


def build_dda2(tree, archive_name="synth-dd"):
    """The first record names the archive itself and sits one level
    ABOVE the root, which is what makes its dirlevel negative and both
    walks skip it — the shape all five DiskDoubler Pro 4.1.1 specimens
    have. A folder does not deepen the level counter, so its children
    sit one level below the folder's own record."""
    out = bytearray(b"DDA2" + bytes(58))
    out[60:62] = u16(crc16(out[:60]))     # the rest of the header is unread
    dir_tail = bytes(DDA2_DIR - DDA2_REC)

    def dirrec(name, level):
        body = bytearray(dir_tail)
        body[8:12] = u32(CTIME)                # +54 in the record
        body[12:16] = u32(MTIME)               # +58
        return _dda2_record(name, 0x9000, level, DDA2_DIR) + bytes(body)

    out.extend(dirrec(archive_name.encode("mac-roman"), -1))

    def emit(node, level):
        if node["isdir"]:
            out.extend(dirrec(node["name"].encode("mac-roman"), level))
            for child in node["children"]:
                emit(child, level + 1)
            return
        # `stored` is a DDAR record shape. DDA2 has one too — entrytype
        # 0x1000, which DiskDoubler Pro writes for a fork-less file with
        # a stored data fork — but XADMaster has no branch for it and
        # raises, so a generated one could not be graded; the five real
        # DiskDoubler Pro archives are what covers it (run_ddtf.py).
        data, rsrc = node["data"], node["rsrc"]
        hdr = _file_header(data, rsrc, node["typ"], node["creator"])
        total = DDA2_FILE + FILEHDR + len(data) + len(rsrc)
        out.extend(_dda2_record(node["name"].encode("mac-roman"),
                                0x5000, level, total))
        out.extend(bytes(DDA2_FILE - DDA2_REC - 4))   # unused, then magic
        out.extend(hdr)
        out.extend(data)
        out.extend(rsrc)

    for node in tree:
        emit(node, 0)
    # 0xbbbb ends the walk. Its totalsize is never used.
    out.extend(_dda2_record(b"", 0xBBBB, 0, DDA2_REC))
    return bytes(out)


def write_one(outdir, name, tree, kind="ddar"):
    path = os.path.join(outdir, name + ".dd")
    with open(path, "wb") as fh:
        fh.write(build_ddar(tree) if kind == "ddar" else build_dda2(tree))
    return path, expected(tree)


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    tree = [folder("Folder", [file("leaf.txt", data=b"hello\n")])]
    for kind in ("ddar", "dda2"):
        p, want = write_one(out, "synth-dd-" + kind, tree, kind)
        print(p, sorted(want))

#!/usr/bin/env python3
"""hfsplus.py — both forks of every file on an HFS Plus volume, read-only.

    tools/hfsplus.py IMAGE [--list] [--path 'A:B:c']    (the volume, or an
                                                          APM disk holding it)
    tools/hfsplus.py --check IMAGE [--limit N]           the control: agree
                                                          with 7-Zip

hfsutils reads HFS and stops at an HFS Plus volume's wrapper, and 7-Zip
reads an HFS Plus volume's data forks but not its resource forks. The
Installer Tomes' resource forks are graded against the files Mac OS 9
installed (tests/harness/run_tome.py), so this reads both.

Source: reference/notes/tn1150_hfsplus.txt (Apple's TN1150, fetched by
tools/fetch_references.sh) for every structure: HFSPlusVolumeHeader at
1024 into the volume (blockSize at +40, catalogFile at +272, extentsFile
at +192); HFSPlusForkData (logicalSize u64, clumpSize, totalBlocks, then
eight HFSPlusExtentDescriptors of startBlock and blockCount); the B-tree's
BTNodeDescriptor (kind at +8, numRecords at +10, record offsets as u16s
counted back from the node's end), BTHeaderRec in node 0 at +14
(firstLeafNode +10, nodeSize +18), kBTLeafNode -1; HFSPlusCatalogKey
(keyLength, parentID, HFSUniStr255) and the record after it; the
catalog's folder (1) and file (2) records — a file's userInfo at +48
(fdType, fdCreator), dataFork at +88 and resourceFork at +168, a folder's
folderID at +8; and an embedded volume's start, drAlBlSt + drEmbedExtent.
startBlock * (drAlBlkSiz / 512) sectors, from drEmbedSigWord 'H+' at +124
and drEmbedExtent at +126 of the wrapper's MDB. drAlBlkSiz (+20) and
drAlBlSt (+28) as tools/vmac/hfscat.py reads them (libhfs). The partition
map through tools/vmac/mkapmdisk.py's find_hfs_start.

**What it cannot see**: a fork or a catalog in more than eight extents,
whose rest is in the extents overflow file this does not read — it refuses
such a fork rather than return part of it; hard links and aliases, which
it returns as the files they are; names compared NFC, so two names that
differ only in normalisation are one.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vmac"))


def be16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def be32(b, o):
    return struct.unpack_from(">I", b, o)[0]


class Volume:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.base = self._find_volume(path)
        vh = self._read(self.base + 1024, 512)
        if vh[0:2] not in (b"H+", b"HX"):
            raise SystemExit("hfsplus: no HFS Plus volume header in %s" % path)
        self.bs = be32(vh, 40)
        self.catalog = self._fork(vh, 272)
        self.files = {}
        self._walk()

    def _read(self, off, n):
        self.f.seek(off)
        return self.f.read(n)

    def _find_volume(self, path):
        head = self._read(0, 2048)
        starts = [0]
        if head[512:514] == b"PM":
            import mkapmdisk
            starts.insert(0, mkapmdisk.find_hfs_start(path) * 512)
        for s in starts:
            mdb = self._read(s + 1024, 512)
            if mdb[0:2] in (b"H+", b"HX"):
                return s
            if mdb[0:2] == b"BD" and mdb[124:126] == b"H+":
                alblk, alst = be32(mdb, 20), be16(mdb, 28)
                start = be16(mdb, 126)
                return s + (alst + start * (alblk // 512)) * 512
        raise SystemExit("hfsplus: no HFS Plus volume in %s" % path)

    def _fork(self, rec, at):
        size = struct.unpack_from(">Q", rec, at)[0]
        total = be32(rec, at + 12)
        ext = [(be32(rec, at + 16 + 8 * i), be32(rec, at + 20 + 8 * i))
               for i in range(8)]
        covered = sum(c for _, c in ext)
        return size, total, covered, ext

    def read_fork(self, fork):
        size, total, covered, ext = fork
        if covered < total:
            raise ValueError("fork in more than eight extents")
        out = bytearray()
        for start, count in ext:
            if count == 0 or len(out) >= size:
                break
            out += self._read(self.base + start * self.bs, count * self.bs)
        if len(out) < size:
            raise ValueError("fork shorter than its extents say")
        return bytes(out[:size])

    def _walk(self):
        cat = self.read_fork(self.catalog)
        nodesize = be16(cat, 14 + 18)
        node = be32(cat, 14 + 10)
        names, parents, files = {}, {}, []
        seen = set()
        while node and node not in seen:
            seen.add(node)
            n = cat[node * nodesize:(node + 1) * nodesize]
            if struct.unpack_from(">b", n, 8)[0] != -1:
                raise SystemExit("hfsplus: leaf chain reaches a non-leaf node")
            for i in range(be16(n, 10)):
                off = be16(n, nodesize - 2 * (i + 1))
                klen = be16(n, off)
                parent = be32(n, off + 2)
                nlen = be16(n, off + 6)
                name = n[off + 8:off + 8 + 2 * nlen].decode("utf-16-be")
                rec = n[off + 2 + klen:]
                kind = struct.unpack_from(">h", rec, 0)[0]
                if kind == 1:
                    fid = be32(rec, 8)
                    names[fid], parents[fid] = name, parent
                elif kind == 2:
                    files.append((parent, name, rec[48:52], rec[52:56],
                                  self._fork(rec, 88), self._fork(rec, 168)))
            node = be32(n, 0)
        self.volname = names.get(2, "")
        for parent, name, ty, cr, dfork, rfork in files:
            parts = [name]
            p = parent
            while p in names and parents.get(p) != 1:
                parts.append(names[p])
                p = parents[p]
            # ':' joins: no Mac name holds one, and '/' is a letter in
            # them ("Global Village Gold/Silver/Merc").
            path = ":".join(unicodedata.normalize("NFC", x)
                            for x in reversed(parts))
            self.files[path] = (ty, cr, dfork, rfork)

    def forks(self, path):
        ty, cr, d, r = self.files[path]
        return ty, cr, self.read_fork(d), self.read_fork(r)


def check(image, limit):
    """Both forks of the first `limit` files equal 7-Zip's: `7z e -so`
    writes a file's data fork and then its resource fork (measured on a
    modem script, 14,583 + 820 B), so the two together are compared. And
    the comparison sees one byte changed (its control)."""
    v = Volume(image)
    paths = sorted(v.files)[:limit]
    bad = 0
    with tempfile.TemporaryDirectory(dir=os.path.join(
            os.path.dirname(HERE), ".tmp")) as tmp:
        for p in paths:
            # 7-Zip names a '/' in a Mac name '_', and its paths start
            # with the volume's name.
            z = "/".join(c.replace("/", "_") for c in
                         [v.volname] + p.split(":"))
            # 7-Zip matches the name as the volume stores it, decomposed
            # (measured: "Español" answers only as NFD).
            r = subprocess.run(["7z", "e", "-so", image,
                                unicodedata.normalize("NFD", z)],
                               capture_output=True)
            _, _, d, rs = v.forks(p)
            if r.stdout != d + rs:
                bad += 1
                print("hfsplus: %s differs from 7-Zip's" % p)
            elif r.stdout and r.stdout[:-1] + bytes([r.stdout[-1] ^ 1]) \
                    == d + rs:
                bad += 1
                print("hfsplus: CONTROL: a changed byte compares equal")
    print("hfsplus: %d files, both forks; %d differ from 7-Zip's"
          % (len(paths), bad))
    return 1 if bad or not paths else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--path", help="'System Folder:Finder', ':'-separated")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    a = ap.parse_args()
    if a.check:
        return check(a.image, a.limit)
    v = Volume(a.image)
    if a.path:
        ty, cr, d, r = v.forks(a.path)
        print("%r/%r data %d rsrc %d" % (ty, cr, len(d), len(r)))
        return 0
    for p, (ty, cr, d, r) in sorted(v.files.items()):
        sys.stdout.buffer.write(("%s %s %10d %10d %s\n" % (
            ty.hex(), cr.hex(), d[0], r[0], p)).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

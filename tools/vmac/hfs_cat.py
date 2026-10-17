#!/usr/bin/env python3
"""hfs_cat.py — read every catalog record of an HFS volume image.

    tools/vmac/hfs_cat.py IMAGE [--json] [--path NAME]

What `hls` does not show: for a FILE its whole FInfo and FXInfo, the
three dates and the locked bit; for a FOLDER its DInfo and DXInfo and the
three dates. That is everything this project's Macintosh shell is asked
to put on the disk (DECISIONS.md 2026-10-17, *the metadata, carried to
the disk*), so this is how a run on the emulator is graded for it.

    f  path  type creator flags  FInfo=<32 hex> FXInfo=<32 hex>
             cr=<8 hex> md=<8 hex> bk=<8 hex> locked=0|1
    d  path  DInfo=<32 hex> DXInfo=<32 hex> cr=... md=... bk=...

Source: hfsutils' libhfs, `/opt/Retro68/hfsutils/libhfs/apple.h`
(`MDB`, `NodeDescriptor`, `BTHdrRec`, `CatDataRec`, `FInfo`, `FXInfo`,
`DInfo`, `DXInfo`) for every offset below, and `record.c` (lines 478-481
and 534) for the locked bit being bit 0 of `filFlags`. The offsets are
those structures' fields summed in declaration order, all big-endian and
unpadded, which is how libhfs's `d_fetch*` reads them:

    file record    +2 filFlags  +4 FInfo(16)  +44 filCrDat  +48 filMdDat
                   +52 filBkDat  +56 FXInfo(16)
    folder record  +6 dirDirID  +10 dirCrDat  +14 dirMdDat  +18 dirBkDat
                   +22 DInfo(16)  +38 DXInfo(16)

**What it cannot see.** A catalog bigger than the three extents the master
directory block lists (the extents-overflow file is not read): it says so
and stops rather than read short. HFS+ (`H+`), MFS and a volume behind a
partition map are refused. Whatever lives outside the catalog: a Get Info
comment is in the Desktop Manager's `Desktop DB` on System 7 and in the
Finder's `Desktop` file on System 6 and earlier, not here — `--fcmt`
lists the latter's `FCMT` resources, and nothing here parses `Desktop DB`.
Folder lock: HFS keeps no locked bit for a folder (libhfs has none), so
none is printed.
"""
import json
import struct
import sys


def be16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def be32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def read_catalog(img):
    """Bytes of the catalog file, or SystemExit."""
    mdb = img[1024:1024 + 162]
    if mdb[0:2] != b"BD":
        raise SystemExit("hfs_cat: no HFS master directory block at 1024")
    if be16(mdb, 124) == 0x482B:                       # drEmbedSigWord 'H+'
        raise SystemExit("hfs_cat: an HFS+ volume inside a wrapper; not read")
    alblksiz = be32(mdb, 20)                           # drAlBlkSiz
    alblst = be16(mdb, 28)                             # drAlBlSt
    ctsize = be32(mdb, 146)                            # drCTFlSize
    out = b""
    for i in range(3):                                 # drCTExtRec
        start, count = be16(mdb, 150 + 4 * i), be16(mdb, 152 + 4 * i)
        if count == 0:
            continue
        off = alblst * 512 + start * alblksiz
        out += img[off:off + count * alblksiz]
    if len(out) < ctsize:
        raise SystemExit("hfs_cat: the catalog continues in the extents-"
                         "overflow file, which this does not read")
    return out[:ctsize]


def leaf_records(cat):
    """Yield (key bytes, data bytes) for every leaf record, in order."""
    nodesize = be16(cat, 14 + 18)                      # BTHdrRec.bthNodeSize
    node = be32(cat, 14 + 10)                          # bthFNode
    seen = set()
    while node and node not in seen:
        seen.add(node)
        nd = cat[node * nodesize:(node + 1) * nodesize]
        if len(nd) < nodesize or nd[8] != 0xFF:        # ndLeafNode
            raise SystemExit("hfs_cat: node %d is not a leaf" % node)
        for i in range(be16(nd, 10)):                  # ndNRecs
            ro = be16(nd, nodesize - 2 * (i + 1))
            klen = nd[ro]
            key = nd[ro + 1:ro + 1 + klen]
            do = ro + 1 + klen
            do += do & 1                               # data is word-aligned
            yield key, nd[do:]
        node = be32(nd, 0)                             # ndFLink


def records(img):
    cat = read_catalog(img)
    names, dirs, files = {}, {}, []
    for key, data in leaf_records(cat):
        parid = be32(key, 1)
        name = key[6:6 + key[5]].decode("mac-roman")
        t = data[0]
        if t == 1:
            dirid = be32(data, 6)
            names[dirid] = (parid, name)
            dirs[dirid] = dict(
                kind="d", parent=parid, name=name, dirid=dirid,
                cr=be32(data, 10), md=be32(data, 14), bk=be32(data, 18),
                finfo=data[22:38].hex(), fxinfo=data[38:54].hex())
        elif t == 2:
            files.append(dict(
                kind="f", parent=parid, name=name,
                locked=data[2] & 1,
                type=data[4:8].decode("mac-roman"),
                creator=data[8:12].decode("mac-roman"),
                flags=be16(data, 12),
                finfo=data[4:20].hex(), fxinfo=data[56:72].hex(),
                cr=be32(data, 44), md=be32(data, 48), bk=be32(data, 52)))

    def path(parid, name):
        parts = [name]
        while parid in names and names[parid][0] != 1:  # 1: the root's parent
            parid, n = names[parid]
            parts.append(n)
        return ":".join(reversed(parts))

    out = []
    for d in dirs.values():
        if d["parent"] == 1:
            continue                                   # the volume itself
        d["path"] = path(d["parent"], d["name"])
        out.append(d)
    for f in files:
        f["path"] = path(f["parent"], f["name"])
        out.append(f)
    return sorted(out, key=lambda r: r["path"])


def fcmt(img, name="Desktop"):
    """The Finder's FCMT resources from a System 6-or-earlier `Desktop`
    file at the root, {id: bytes}. Read through hfsutils, because the
    file's resource fork may live anywhere on the volume."""
    import os, shutil, subprocess, tempfile
    home = tempfile.mkdtemp(prefix="hfscat-")
    env = dict(os.environ, HOME=home)
    try:
        src = os.path.join(home, "img")
        with open(src, "wb") as f:
            f.write(img)
        subprocess.run(["hmount", src], check=True, capture_output=True,
                       env=env)
        mb = os.path.join(home, "dt.bin")
        r = subprocess.run(["hcopy", "-m", ":" + name, mb],
                           capture_output=True, env=env)
        subprocess.run(["humount"], capture_output=True, env=env)
        if r.returncode:
            return None
        d = open(mb, "rb").read()
    finally:
        shutil.rmtree(home, ignore_errors=True)
    # MacBinary: data fork then resource fork, each padded to 128.
    dl, rl = be32(d, 83), be32(d, 87)
    rs = d[128 + (dl + 127) // 128 * 128:][:rl]
    # Resource fork layout: Inside Macintosh: More Macintosh Toolbox,
    # as read by this repository's own tools (tools/vmac/README.md).
    doff, moff = be32(rs, 0), be32(rs, 4)
    m = rs[moff:]
    tl = be16(m, 24)
    out = {}
    for i in range(be16(m, tl) + 1):
        t = m[tl + 2 + 8 * i:tl + 6 + 8 * i]
        n = be16(m, tl + 6 + 8 * i) + 1
        ro = be16(m, tl + 8 + 8 * i)
        if t != b"FCMT":
            continue
        for j in range(n):
            r = m[tl + ro + 12 * j:tl + ro + 12 * j + 12]
            rid = struct.unpack(">h", r[:2])[0]
            off = int.from_bytes(r[5:8], "big")
            ln = be32(rs, doff + off)
            out[rid] = rs[doff + off + 4:doff + off + 4 + ln]
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--path", help="only this path (':'-separated)")
    ap.add_argument("--fcmt", nargs="?", const="Desktop",
                    help="also list FCMT resources of this root file")
    a = ap.parse_args()
    img = open(a.image, "rb").read()
    rs = records(img)
    if a.path:
        rs = [r for r in rs if r["path"] == a.path]
    if a.json:
        out = {"records": rs}
        if a.fcmt:
            c = fcmt(img, a.fcmt)
            out["fcmt"] = None if c is None else {
                str(k): v.hex() for k, v in c.items()}
        print(json.dumps(out, indent=1))
        return
    for r in rs:
        if r["kind"] == "f":
            print("f %-40s %-4s %-4s %04x FInfo=%s FXInfo=%s cr=%08x md=%08x "
                  "bk=%08x locked=%d" % (r["path"], r["type"], r["creator"],
                                         r["flags"], r["finfo"], r["fxinfo"],
                                         r["cr"], r["md"], r["bk"],
                                         r["locked"]))
        else:
            print("d %-40s DInfo=%s DXInfo=%s cr=%08x md=%08x bk=%08x"
                  % (r["path"], r["finfo"], r["fxinfo"], r["cr"], r["md"],
                     r["bk"]))
    if a.fcmt:
        c = fcmt(img, a.fcmt)
        if c is None:
            print("no %s file" % a.fcmt)
        else:
            for k, v in sorted(c.items()):
                print("FCMT %6d %r" % (k, v))


if __name__ == "__main__":
    main()

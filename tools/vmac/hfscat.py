#!/usr/bin/env python3
"""hfscat.py — every catalog record on an HFS image, with its Finder info.

    tools/vmac/hfscat.py IMAGE [--all]      one line per file and folder
    tools/vmac/hfscat.py --check IMAGE      the control: agree with hfsutils

hfsutils lists a type, a creator and a date and nothing else, and every
question about what an extractor RESTORED — icon position, window
rectangle, the extended Finder info, the backup date, the locked bit — is
in the catalog record it does not show. This walks the catalog B-tree's
leaf chain and returns each record whole, keyed by its folder path.

Layouts, all from libhfs's transcription of Inside Macintosh
(/opt/Retro68/hfsutils/libhfs/apple.h):

  MDB         drCTFlSize at +146, drCTExtRec at +150 (three ExtDescriptors);
              drAlBlkSiz at +20, drAlBlSt at +28, both from 1024 (`MDB`).
  node        NodeDescriptor: ndFLink +0, ndType +8 (0xff leaf), ndNRecs +10;
              record offsets are words counted back from the node's end.
  header rec  BTHdrRec at +14: bthFNode +10, bthNodeSize +18.
  key         CatKeyRec: ckrKeyLen +0, ckrParID +2, ckrCName (Str31) +6;
              the data record follows at +1+keyLen, rounded up to even.
  cdrDirRec   (cdrType 1) dirFlags +2, dirVal +4, dirDirID +6, dirCrDat +10,
              dirMdDat +14, dirBkDat +18, dirUsrInfo (DInfo) +22,
              dirFndrInfo (DXInfo) +38, dirResrv +54; 70 bytes.
  cdrFilRec   (cdrType 2) filFlags +2 (bit 0: locked), filUsrWds (FInfo) +4,
              filFlNum +20, filLgLen +26, filRLgLen +36, filCrDat +44,
              filMdDat +48, filBkDat +52, filFndrInfo (FXInfo) +56; 102 bytes.

What it CANNOT see:
- a catalog in more than the three extents the MDB holds: it refuses one
  rather than reading it short (the extents overflow file is not walked);
- Get Info comments, which are in the Finder's Desktop file, not here;
- anything an application has not yet flushed: a volume a running
  emulator is writing is read as it stands on the host.
"""
import os
import struct
import sys

DIR, FILE = 1, 2


def be16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def be32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def _catalog_bytes(img, segs=None):
    mdb = img[1024:1024 + 512]
    if mdb[:2] != b"BD":
        raise ValueError("no HFS master directory block at 1024")
    alblk = be32(mdb, 20)
    alst = be16(mdb, 28)
    size = be32(mdb, 146)
    out = b""
    for i in range(3):
        start, count = be16(mdb, 150 + 4 * i), be16(mdb, 152 + 4 * i)
        if count:
            off = alst * 512 + start * alblk
            if segs is not None:
                segs.append((len(out), off, count * alblk))
            out += img[off:off + count * alblk]
    if len(out) < size:
        raise ValueError("catalog continues in the extents overflow file, "
                         "which this does not walk")
    return out[:size]


def records(img):
    """Every directory and file record: dicts with path, kind, the raw
    record bytes and `at`, the record's byte offset in the image.
    Threads (cdrType 3/4) are skipped."""
    segs = []
    cat = _catalog_bytes(img, segs)

    def absolute(c):
        for base, off, n in segs:
            if base <= c < base + n:
                return off + c - base
        raise ValueError("catalog offset %d outside its extents" % c)
    nodesize = be16(cat, 14 + 18)
    node = be32(cat, 14 + 10)                        # bthFNode
    raw = []
    seen = set()
    while node and node not in seen:
        seen.add(node)
        nd = cat[node * nodesize:(node + 1) * nodesize]
        if nd[8] != 0xFF:
            raise ValueError("node %d on the leaf chain is not a leaf" % node)
        for i in range(be16(nd, 10)):
            ro = be16(nd, nodesize - 2 * (i + 1))
            klen = nd[ro]
            if klen == 0:
                continue                             # a deleted record
            parid = be32(nd, ro + 2)
            name = nd[ro + 7:ro + 7 + nd[ro + 6]]
            d = ro + 1 + klen
            d += d & 1
            kind = nd[d]
            if kind == DIR:
                rec = nd[d:d + 70]
            elif kind == FILE:
                rec = nd[d:d + 102]
            else:
                continue
            raw.append((parid, name, kind, rec,
                        absolute(node * nodesize + d)))
        node = be32(nd, 0)                           # ndFLink
    dirs = {be32(r, 6): (p, n) for p, n, k, r, a in raw if k == DIR}

    def path(parid, name):
        parts = [name]
        while parid in dirs:                         # the root's parent is 1
            parid, n = dirs[parid]
            parts.append(n)
        return tuple(reversed(parts))

    return [dict(path=path(p, n), kind=k, rec=r, at=a,
                 id=be32(r, 6) if k == DIR else be32(r, 20))
            for p, n, k, r, a in raw]


def patch(image, path, offset, value):
    """Overwrite `value` at `offset` inside the catalog record of `path`
    (a tuple of names, volume first) in the image FILE, and read it back.
    The catalog carries no checksum, so this is all a Finder would see."""
    with open(image, "r+b") as f:
        img = f.read()
        hit = [r for r in records(img) if r["path"] == tuple(path)]
        if len(hit) != 1:
            raise ValueError("%d records named %r" % (len(hit), path))
        f.seek(hit[0]["at"] + offset)
        f.write(value)
    again = [r for r in records(open(image, "rb").read())
             if r["path"] == tuple(path)][0]
    if again["rec"][offset:offset + len(value)] != value:
        raise ValueError("patch did not read back")


def fields(r):
    """The record's Finder-visible fields, by name, as integers."""
    rec = r["rec"]
    s16 = lambda o: struct.unpack_from(">h", rec, o)[0]      # noqa: E731
    if r["kind"] == DIR:
        di, dx = 22, 38
        return {"dirFlags": be16(rec, 2), "crdat": be32(rec, 10),
                "mddat": be32(rec, 14), "bkdat": be32(rec, 18),
                "frRect": tuple(s16(di + 2 * i) for i in range(4)),
                "frFlags": be16(rec, di + 8),
                "frLocation": (s16(di + 10), s16(di + 12)),
                "frView": be16(rec, di + 14),
                "frScroll": (s16(dx), s16(dx + 2)),
                "frOpenChain": be32(rec, dx + 4),
                "frScript": rec[dx + 8], "frXFlags": rec[dx + 9],
                "frComment": be16(rec, dx + 10),
                "frPutAway": be32(rec, dx + 12)}
    fi, fx = 4, 56
    return {"filFlags": rec[2], "type": rec[fi:fi + 4],
            "creator": rec[fi + 4:fi + 8], "fdFlags": be16(rec, fi + 8),
            "fdLocation": (s16(fi + 10), s16(fi + 12)),
            "fdFldr": s16(fi + 14),
            "crdat": be32(rec, 44), "mddat": be32(rec, 48),
            "bkdat": be32(rec, 52),
            "fdIconID": s16(fx), "fdUnused": rec[fx + 2:fx + 8],
            "fdScript": rec[fx + 8], "fdXFlags": rec[fx + 9],
            "fdComment": s16(fx + 10), "fdPutAway": be32(rec, fx + 12),
            "dlen": be32(rec, 26), "rlen": be32(rec, 36)}


def check(image, shift=0):
    """The control: every file's type and creator against hfsutils' own
    listing. Returns the number of disagreements. `shift` moves the FInfo
    offset by that many bytes, which is how the check is shown able to
    fail (`--check IMAGE --shift 2`)."""
    import subprocess
    import tempfile
    home = tempfile.mkdtemp(prefix="hfscat-")
    env = dict(os.environ, HOME=home)
    subprocess.run(["hmount", image], env=env, capture_output=True, check=True)
    mine = records(open(image, "rb").read())
    bad = 0
    try:
        for r in mine:
            p = b":".join(r["path"])
            if r["kind"] != FILE:
                continue
            ls = subprocess.run([b"hls", b"-ld", p], env=env,
                                capture_output=True).stdout
            rec = r["rec"]
            # hls prints a NUL in a type as a space
            want = (rec[4 + shift:8 + shift] + b"/" +
                    rec[8 + shift:12 + shift]).replace(b"\0", b" ")
            if want not in ls:
                bad += 1
                print("hfscat: DISAGREE %r: hls says %r, record says %r"
                      % (p, ls.strip(), want))
    finally:
        subprocess.run(["humount"], env=env, capture_output=True)
    print("hfscat: %d records, %d files checked against hls, %d disagree"
          % (len(mine), sum(r["kind"] == FILE for r in mine), bad))
    return bad


def main():
    if sys.argv[1:2] == ["--check"]:
        shift = int(sys.argv[4]) if sys.argv[3:4] == ["--shift"] else 0
        return 1 if check(sys.argv[2], shift) else 0
    for r in records(open(sys.argv[1], "rb").read()):
        f = fields(r)
        name = ":".join(x.decode("mac-roman") for x in r["path"])
        if r["kind"] == DIR:
            print("d %-40s rect=%s flags=%04x loc=%s view=%04x scroll=%s"
                  % (name, f["frRect"], f["frFlags"], f["frLocation"],
                     f["frView"], f["frScroll"]))
        else:
            print("f %-40s %s/%s flags=%04x loc=%s fldr=%d lock=%d"
                  % (name, f["type"].decode("mac-roman"),
                     f["creator"].decode("mac-roman"), f["fdFlags"],
                     f["fdLocation"], f["fdFldr"], f["filFlags"] & 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

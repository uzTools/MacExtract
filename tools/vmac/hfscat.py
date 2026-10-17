#!/usr/bin/env python3
"""hfscat.py — every catalog record on an HFS image, whole, with its Finder info.

    tools/vmac/hfscat.py IMAGE [--json] [--path A:B:y] [--fcmt [DeskTop]]
    tools/vmac/hfscat.py --check IMAGE [--shift N]    the control: agree with hls

hfsutils lists a type, a creator and a date and nothing else, and every
question about what an extractor RESTORED — icon position, window
rectangle, the extended Finder info, the backup date, the locked bit — is
in the catalog record it does not show. This walks the catalog B-tree's
leaf chain and returns each record whole, keyed by its folder path, with
the fields the graders compare decoded beside the raw bytes:

    f  path  type creator flags  FInfo=<32 hex> FXInfo=<32 hex>
             cr=<8 hex> md=<8 hex> bk=<8 hex> locked=0|1
    d  path  DInfo=<32 hex> DXInfo=<32 hex> cr=... md=... bk=...

Two readers were written for this, one for the measurement of where each
format keeps its Finder info and one for grading what the shell writes;
this is the one that survived, because it keeps the raw record and its
offset in the image (`patch()` plants a sentinel before a boot, and the
lining-up compares header bytes to catalog bytes) and because it carries
its own control, `--check` against `hls`, which `--shift 2` shows able
to fail (DECISIONS.md 2026-10-17, *the window StuffIt kept in the name*).

Layouts, all from libhfs's transcription of Inside Macintosh
(/opt/Retro68/hfsutils/libhfs/apple.h), the structures' fields summed in
declaration order, big-endian and unpadded, as libhfs's `d_fetch*` reads
them; `record.c` for the locked bit being bit 0 of `filFlags`:

  MDB         drCTFlSize at +146, drCTExtRec at +150 (three ExtDescriptors);
              drAlBlkSiz at +20, drAlBlSt at +28, both from 1024 (`MDB`);
              drEmbedSigWord at +124 is 'H+' on an HFS+ wrapper.
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
  HFS+ (an 'H+' wrapper), MFS and a volume behind a partition map are
  refused too;
- Get Info comments, which are in the Finder's Desktop file (System 6 and
  earlier; `--fcmt` lists that file's `FCMT` resources through hfsutils)
  or the Desktop Manager's `Desktop DB` (System 7, not parsed);
- a folder's lock: HFS keeps no locked bit for a folder (libhfs has none);
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
    if be16(mdb, 124) == 0x482B:                       # drEmbedSigWord 'H+'
        raise ValueError("an HFS+ volume inside a wrapper; not read")
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
    """Every directory and file record, the volume's root included, as
    dicts: `path` (a tuple of names as bytes, volume first), `rel` (the
    path below the volume, ':'-joined, MacRoman decoded; '' for the root),
    `kind` (DIR or FILE), `rec` (the raw record), `at` (the record's byte
    offset in the image), `id`, and decoded: `cr`, `md`, `bk`, `finfo`
    and `fxinfo` (FInfo/FXInfo or DInfo/DXInfo, 32 hex digits each),
    `flags` (fdFlags or frFlags); for a file also `locked`, `type` and
    `creator`. Threads (cdrType 3/4) are skipped."""
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
        if len(nd) < nodesize or nd[8] != 0xFF:
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

    out = []
    for p, n, k, r, a in raw:
        full = path(p, n)
        d = dict(path=full, kind=k, rec=r, at=a,
                 rel=":".join(x.decode("mac-roman") for x in full[1:]))
        if k == DIR:
            d.update(id=be32(r, 6), cr=be32(r, 10), md=be32(r, 14),
                     bk=be32(r, 18), finfo=r[22:38].hex(),
                     fxinfo=r[38:54].hex(), flags=be16(r, 30))
        else:
            d.update(id=be32(r, 20), cr=be32(r, 44), md=be32(r, 48),
                     bk=be32(r, 52), finfo=r[4:20].hex(),
                     fxinfo=r[56:72].hex(), flags=be16(r, 12),
                     locked=r[2] & 1, type=r[4:8].decode("mac-roman"),
                     creator=r[8:12].decode("mac-roman"))
        out.append(d)
    return out


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


def fcmt(img, name="Desktop"):
    """The Finder's FCMT resources from a System 6-or-earlier `Desktop`
    file at the root, {id: bytes}, or None without the file. Read through
    hfsutils, because the file's resource fork may live anywhere on the
    volume."""
    import shutil
    import subprocess
    import tempfile
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
    import argparse
    import json
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--check", action="store_true",
                    help="every file's type/creator against hls")
    ap.add_argument("--shift", type=int, default=0,
                    help="with --check: misread FInfo by N bytes (must fail)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--path", help="only this path below the volume "
                    "(':'-separated)")
    ap.add_argument("--fcmt", nargs="?", const="Desktop",
                    help="also list FCMT resources of this root file")
    a = ap.parse_args()
    if a.check:
        return 1 if check(a.image, a.shift) else 0
    img = open(a.image, "rb").read()
    try:
        rs = records(img)
    except ValueError as e:
        raise SystemExit("hfscat: %s" % e)
    if a.path:
        rs = [r for r in rs if r["rel"] == a.path]
    if a.json:
        out = {"records": [
            {k: (v.hex() if isinstance(v, bytes) else
                 [x.decode("mac-roman") for x in v] if k == "path" else v)
             for k, v in r.items()} for r in rs]}
        if a.fcmt:
            c = fcmt(img, a.fcmt)
            out["fcmt"] = None if c is None else {
                str(k): v.hex() for k, v in c.items()}
        print(json.dumps(out, indent=1))
        return 0
    for r in rs:
        name = ":".join(x.decode("mac-roman") for x in r["path"])
        if r["kind"] == FILE:
            print("f %-40s %-4s %-4s %04x FInfo=%s FXInfo=%s cr=%08x md=%08x "
                  "bk=%08x locked=%d" % (name, r["type"], r["creator"],
                                         r["flags"], r["finfo"], r["fxinfo"],
                                         r["cr"], r["md"], r["bk"],
                                         r["locked"]))
        else:
            print("d %-40s DInfo=%s DXInfo=%s cr=%08x md=%08x bk=%08x"
                  % (name, r["finfo"], r["fxinfo"], r["cr"], r["md"],
                     r["bk"]))
    if a.fcmt:
        c = fcmt(img, a.fcmt)
        if c is None:
            print("no %s file" % a.fcmt)
        elif not c:
            print("%s holds no FCMT resource" % a.fcmt)
        else:
            for k, v in sorted(c.items()):
                print("FCMT %6d %r" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())

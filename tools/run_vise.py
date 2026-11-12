#!/usr/bin/env python3
"""run_vise.py — Installer VISE (src/fmt_vise.c), graded by the installers'
own CRC-32s and, where it reads, by mrmidi/installer-vise.

    run_vise.py [--macextract BIN] [--extra DIR]
    run_vise.py --manifest FIXTURE...     # write fixtures/manifests/*.json

The installers are the corpus's `vise-wild-*` fixtures and the three files
of the `vise-set-epson-sp700` set, and with --extra every file in DIR as well. The
catalogue is read HERE, independently of the engine, for every path, size,
type, creator, flag word and CRC compared: Python's own parse of the
layout in fmt_vise.c's header comment, and zlib for a compressed
catalogue (its stream is DEFLATE with every pair of bytes swapped).

  1. The CRC-32s. For every record stored in the archive, the engine's two
     forks, data then resource, must have the CRC-32 the record holds,
     and its path (folders by depth), sizes, type, creator and Finder
     flags must be the ones this file reads. Nothing that is not stored —
     a record of segment 0 — may come out, nor a folder that holds none of
     what is.
  2. installer-vise, run in tools/sandbox.py, for the versions it reads
     (the compressed catalogues of 0x80010308 and later): its forks, which
     it writes flat, must be the engine's as a multiset.
  3. The set: the Epson installer and its two segments, every file's CRC;
     then without the third segment, its files and the one that runs into
     it refused by name and the rest unchanged.
  4. An installer that stores nothing it installs is refused, and lists
     nothing.
  5. Damage: payload bytes changed and the file cut, on the smallest
     installer: no crash, no hang, every cut refused, and every changed
     payload byte a refused entry (the CRC sees it).

And CONTROLS, each of which must fail: a fork of the engine's output
changed in one byte (section 1's comparison), a record's CRC changed in
the archive (the engine's own check), and the folders read as INDEXES, as
ScummVM reads 3.5's (the paths of `vise-wild-acrobat-movie` must then
differ from the engine's: depth is what the test distinguishes).

**What it cannot see.** Dates, which no reader here grades (run_diff.py
does not compare them either). Whether the paths are the ones the
installer would write: this file and the engine read the same layout, and
only the emulator settled that, on two installers (DECISIONS.md
2026-11-11, *the installer that was an archive*). A record whose extra
bytes after its name hold a signature, which both readers would take for
the next record. The versions no specimen here has (0x80010306,
0x8001030B, 0x8001030D), which the engine does not recognise.
"""
import argparse
import collections
import glob
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXDIR = os.path.join(ROOT, "fixtures")
CACHE = os.path.expanduser("~/.cache/macextract/specimens/vise")
IVSRC = os.environ.get("UNC_INSTALLER_VISE", os.path.join(
    ROOT, "reference", "installer-vise", "src"))
FAILS = []

# Record suffixes by version: (folder, file), and VISE X's name lengths two
# bytes later. fmt_vise_priv.h's table.
SUFFIX = {0x80010201: (0, 0), 0x80010202: (0, 0), 0x80010300: (6, 0),
          0x80010301: (6, 0), 0x80010302: (6, 0), 0x80010303: (6, 0),
          0x80010304: (22, 16), 0x80010307: (66, 62), 0x80010308: (70, 66),
          0x8001030A: (70, 66), 0x8001030B: (70, 66), 0x8001030C: (78, 74),
          0x8001030D: (78, 74), 0x80010A50: (96, 88), 0x80010B00: (96, 88)}
VISE_X = (0x80010A50, 0x80010B00)


def fail(msg):
    FAILS.append(msg)
    print("  FAIL", msg)


def run(cmd, **kw):
    kw.setdefault("timeout", 900)
    return subprocess.run(cmd, capture_output=True, **kw)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def data_fork(blob):
    """The data fork of a MacBinary file, or the file as it is."""
    if len(blob) > 128 and blob[0] == 0 and 0 < blob[1] < 64 and \
            blob[128:132] == b"SVCT":
        dl = struct.unpack(">I", blob[83:87])[0]
        return blob[128:128 + dl]
    return blob


def swap(b):
    a = bytearray(b)
    a[0:len(a) // 2 * 2:2], a[1:len(a) // 2 * 2:2] = \
        b[1:len(b) // 2 * 2:2], b[0:len(b) // 2 * 2:2]
    return bytes(a)


def catalogue(d):
    """(version, nparts, [record dicts]) read from a first segment."""
    ver = struct.unpack(">I", d[16:20])[0]
    nparts = struct.unpack(">I", d[20:24])[0]
    cat = struct.unpack(">I", d[36:40])[0]
    blen, comp = struct.unpack(">II", d[cat + 4:cat + 12])
    n = struct.unpack(">H", d[cat + 16:cat + 18])[0]
    p = cat + 20
    pack = d[p:p + 4] == b"PACK"
    if pack:
        p += 0x50
        body = d[p:p + blen]
    else:
        body = d[p:cat + 20 + blen]
    if comp:
        body = zlib.decompressobj(-15).decompress(swap(body))
    ds, fs = SUFFIX[ver]
    dl, fl = (78, 120) if ver in VISE_X else (76, 118)
    pos = [m.start() for m in re.finditer(rb"[FD]VCT", body)][:n]
    recs, stack = [], []
    for k, at in enumerate(pos):
        r = body[at + 4:at + 128]
        isdir = body[at] == ord("D")
        if isdir:
            depth = struct.unpack(">H", r[68:70])[0]
            nl = r[dl]
            name = body[at + 82 + ds:at + 82 + ds + nl]
        else:
            depth = struct.unpack(">H", r[92:94])[0]
            nl = r[fl]
            name = body[at + 124 + fs:at + 124 + fs + nl]
        parent = stack[depth - 1] if depth else None
        rec = dict(k=k, dir=isdir, name=name, depth=depth, parent=parent)
        if isdir:
            del stack[depth:]
            stack.append(k)
        else:
            u = lambda o: struct.unpack(">I", r[o:o + 4])[0]
            rec.update(type=r[40:44], creator=r[44:48],
                       flags=struct.unpack(">H", r[48:50])[0],
                       dlen=u(68), rlen=u(76), crc=u(80),
                       seg=struct.unpack(">H", r[94:96])[0])
        recs.append(rec)
    return ver, nparts, recs


def paths(recs, index=False):
    """Each record's path, its folders by depth (or, with `index`, by the
    1-based folder index ScummVM reads 3.5's parent as)."""
    out, dirs = {}, [r for r in recs if r["dir"]]
    for r in recs:
        chain, q = [], r
        while q is not None:
            chain.append(q["name"].replace(b"/", b":"))
            if index:
                par = q["depth"]
                q = dirs[par - 1] if par and par <= len(dirs) else None
            else:
                q = recs[q["parent"]] if q["parent"] is not None else None
        out[r["k"]] = b"/".join(reversed(chain))
    return out


def stored(recs, nparts):
    return [r for r in recs if not r["dir"] and 1 <= r["seg"] <= nparts]


def readf(p):
    try:
        with open(p, "rb") as f:
            return f.read()
    except OSError:
        return None


def ours(mx, path, out, parts=()):
    """{path: (data, rsrc, type, creator, flags)} and the CLI's exit code
    and stderr, from `l --finder` and `x`."""
    extra = [a for p in parts for a in ("--part", p)]
    lst = run([mx, "l", "--finder", "--raw-names"] + extra + [path])
    files = {}
    for line in lst.stdout.split(b"\n"):
        m = re.match(rb"^f +(\d+) +(\d+) ([0-9a-f]{8})/([0-9a-f]{8}) "
                     rb"([0-9a-f]{4}) (.*)$", line)
        if m:
            files[m.group(6)] = (int(m.group(5), 16), m.group(3), m.group(4))
    x = run([mx, "x", "--raw-names", "-o", out] + extra + [path])
    got = {}
    for p, (flags, ty, cr) in files.items():
        fp = os.path.join(out.encode(), p.replace(b"/", os.sep.encode()))
        got[p] = (readf(fp), readf(fp + b".rsrc") or b"",
                  bytes.fromhex(ty.decode()), bytes.fromhex(cr.decode()),
                  flags)
    return got, x.returncode, x.stderr


def grade(mx, path, work, quiet=False, parts=()):
    """Section 1 for one installer; returns (version, files graded, the
    extracted forks by path, the catalogue records)."""
    d = data_fork(open(path, "rb").read())
    ver, nparts, recs = catalogue(d)
    want = stored(recs, nparts)
    pth = paths(recs)
    out = os.path.join(work, "x")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    got, rc, err = ours(mx, path, out, parts)
    base = os.path.basename(path)
    if rc != 0:
        fail("%s: x exited %d: %s" % (base, rc, err.decode("mac_roman")[-300:]))
    expect = {pth[r["k"]]: r for r in want}
    if set(got) != set(expect):
        fail("%s: the files are not the catalogue's: extra %s, missing %s"
             % (base, sorted(set(got) - set(expect))[:3],
                sorted(set(expect) - set(got))[:3]))
    folders = set()
    for r in want:
        q = r["parent"]
        while q is not None:
            folders.add(pth[q])
            q = recs[q]["parent"]
    for p, r in expect.items():
        g = got.get(p)
        if g is None or g[0] is None:
            continue
        data, rsrc, ty, cr, flags = g
        c = zlib.crc32(rsrc, zlib.crc32(data)) & 0xFFFFFFFF
        if (len(data), len(rsrc)) != (r["dlen"], r["rlen"]):
            fail("%s: %s: %d/%d bytes, the record says %d/%d" % (
                base, p, len(data), len(rsrc), r["dlen"], r["rlen"]))
        elif c != r["crc"]:
            fail("%s: %s: CRC-32 %08x, the record's %08x" % (base, p, c,
                                                             r["crc"]))
        if (ty, cr, flags) != (r["type"], r["creator"], r["flags"]):
            fail("%s: %s: %s/%s %04x, the record's %s/%s %04x" % (
                base, p, ty, cr, flags, r["type"], r["creator"], r["flags"]))
    if not quiet:
        print("  %-34s %08x %4d files, %3d folders" % (base, ver, len(want),
                                                      len(folders)))
    return ver, len(want), got, recs


def installer_vise(path, work):
    """installer-vise's forks as a multiset, or None where it cannot run."""
    if not os.path.isdir(os.path.join(IVSRC, "installer_vise")):
        return None
    box = os.path.join(work, "iv")
    shutil.rmtree(box, ignore_errors=True)
    os.makedirs(os.path.join(box, "rich"))
    open(os.path.join(box, "rich", "__init__.py"), "w").close()
    # A stand-in for rich.progress: installer-vise imports it for its
    # progress bar alone.
    with open(os.path.join(box, "rich", "progress.py"), "w") as f:
        f.write("class _C:\n    def __init__(self, *a, **k): pass\n"
                "BarColumn = SpinnerColumn = TextColumn = "
                "TimeElapsedColumn = _C\n"
                "class Progress(_C):\n"
                "    def add_task(self, *a, **k): return 0\n"
                "    def update(self, *a, **k): pass\n"
                "    def advance(self, *a, **k): pass\n"
                "    def __enter__(self): return self\n"
                "    def __exit__(self, *a): return False\n")
    with open(os.path.join(box, "drive.py"), "w") as f:
        f.write("import sys\nsys.path[:0] = ['/iv', '/src']\n"
                "from installer_vise.archive import Archive\n"
                "from installer_vise.extract import extract_archive\n"
                "extract_archive(Archive.open('/in.bin'), '/out', "
                "progress=False, max_workers=1)\n")
    outd = os.path.join(work, "ivout")
    shutil.rmtree(outd, ignore_errors=True)
    os.makedirs(outd)
    df = os.path.join(work, "in.bin")
    with open(df, "wb") as f:
        f.write(data_fork(open(path, "rb").read()))
    r = run([sys.executable, os.path.join(ROOT, "tools", "sandbox.py"),
             "--ro", box + ":/iv", "--ro", IVSRC + ":/src",
             "--ro", df + ":/in.bin", "--rw", outd + ":/out", "--",
             "python3", "-I", "/iv/drive.py"])
    if r.returncode != 0:
        return ("error", r.stderr.decode("utf-8", "replace").strip()
                .splitlines()[-1:])
    files = os.path.join(outd, "files")
    ms = collections.Counter()
    for name in os.listdir(files):
        if name.endswith(".rsrc"):
            continue
        data = readf(os.path.join(files, name)) or b""
        rsrc = readf(os.path.join(files, name + ".rsrc")) or b""
        ms[(sha(data), sha(rsrc))] += 1
    for name in os.listdir(files):
        if name.endswith(".rsrc") and not os.path.exists(
                os.path.join(files, name[:-5])):
            ms[(sha(b""), sha(readf(os.path.join(files, name))))] += 1
    return ms


def multiset(got):
    return collections.Counter((sha(g[0] or b""), sha(g[1])) for g in
                               got.values())


def main_grade(mx, extra, work):
    inst = sorted(glob.glob(os.path.join(FIXDIR, "vise-wild-*")))
    inst = [p for p in inst if not p.endswith("-stub")]
    if not inst:
        fail("no vise-wild-* fixture in fixtures/")
    if extra:
        inst += sorted(glob.glob(os.path.join(extra, "*")))
    inst += sorted(glob.glob(os.path.join(FIXDIR, "vise-x-*")))
    inst = [p for p in inst if not p.endswith(".data")]
    myth = os.path.join(CACHE, "myth-installer.bin")
    if os.path.exists(myth):
        inst.append(myth)
    # VISE X's payload is a second file: the fixture's is beside it, the
    # cached Office 2004 updater's is named.
    office = (os.path.join(CACHE, "office2004", "catalogue.bin"),
              os.path.join(CACHE, "office2004", "Installer.data"))
    parts = {}
    if all(os.path.exists(f) for f in office):
        inst.append(office[0])
        parts[office[0]] = (office[1],)
    print("1. the CRC-32s, %d installers" % len(inst))
    graded = {}
    for p in inst:
        try:
            graded[p] = grade(mx, p, work, parts=parts.get(p, ()))
        except (KeyError, struct.error, zlib.error) as e:
            fail("%s: %r" % (os.path.basename(p), e))
    print("2. installer-vise")
    if not os.path.isdir(IVSRC):
        print("  SKIPPED: no %s (tools/fetch_references.sh)" % IVSRC)
    for p, (ver, n, got, recs) in graded.items():
        if ver < 0x80010308 or ver in VISE_X:
            continue
        ms = installer_vise(p, work)
        base = os.path.basename(p)
        if ms is None:
            continue
        if isinstance(ms, tuple):
            fail("%s: installer-vise: %s" % (base, ms[1]))
        elif ms != multiset(got):
            fail("%s: installer-vise's forks are not the engine's" % base)
        else:
            print("  %-34s %d files, equal" % (base, sum(ms.values())))
    return graded


def set_grade(mx, work):
    print("3. the Epson set")
    fx = [os.path.join(FIXDIR, "vise-set-epson-sp700" + s)
          for s in ("", ".2", ".3")]
    if not all(os.path.exists(f) for f in fx):
        fail("the vise-set-epson-sp700 fixtures are not all here")
        return
    ver, n, got, recs = grade(mx, fx[0], work)
    want = stored(recs, 3)
    # Without the third segment: its files, and the one that runs into it.
    t = os.path.join(work, "two")
    shutil.rmtree(t, ignore_errors=True)
    os.makedirs(t)
    for f in fx[:2]:
        shutil.copy(f, t)
    out = os.path.join(work, "x2")
    shutil.rmtree(out, ignore_errors=True)
    r = run([mx, "x", "--raw-names", "-o", out,
             os.path.join(t, os.path.basename(fx[0]))])
    # Each refused file by name; the archive's own line, which names the
    # installer, is not one of them.
    refused = [l for l in r.stderr.split(b"\n") if b"missing segment" in l
               and os.path.basename(fx[0]).encode() + b":" not in l]
    seg3 = [x for x in want if x["seg"] == 3]
    if r.returncode == 0 or len(refused) != len(seg3) + 1:
        fail("without segment 3: exit %d, %d refused, %d expected"
             % (r.returncode, len(refused), len(seg3) + 1))
    else:
        print("  without segment 3: %d refused by name, %d out"
              % (len(refused), n - len(refused)))


def stub_grade(mx):
    print("4. an installer that stores nothing")
    p = os.path.join(FIXDIR, "vise-wild-netscape-stub")
    if not os.path.exists(p):
        fail("no vise-wild-netscape-stub fixture")
        return
    t = run([mx, "t", p])
    l = run([mx, "l", p])
    rows = [x for x in l.stdout.split(b"\n") if x[:2] in (b"f ", b"d ")]
    if t.returncode == 0 or rows:
        fail("the stub: exit %d, %d rows listed" % (t.returncode, len(rows)))
    else:
        print("  refused, nothing listed")


def damage(mx, path, work):
    print("5. damage, %s" % os.path.basename(path))
    blob = open(path, "rb").read()
    ver, nparts, recs = catalogue(blob)
    cat = struct.unpack(">I", blob[36:40])[0]
    hit = refused = 0
    for i, at in enumerate(range(60, cat, max(1, cat // 40))):
        b = bytearray(blob)
        b[at] ^= 0x5A
        v = os.path.join(work, "v.bin")
        with open(v, "wb") as f:
            f.write(b)
        r = run([mx, "t", v], timeout=120)
        if r.returncode < 0 or r.returncode > 2:
            fail("byte %d changed: exit %d" % (at, r.returncode))
        hit += 1
        refused += r.returncode != 0
    for cut in range(100, len(blob), max(1, len(blob) // 30)):
        v = os.path.join(work, "v.bin")
        with open(v, "wb") as f:
            f.write(blob[:cut])
        r = run([mx, "t", v], timeout=120)
        if r.returncode == 0 or r.returncode > 2 or r.returncode < 0:
            fail("cut at %d: exit %d" % (cut, r.returncode))
    print("  %d payload bytes changed, %d refused; cuts all refused"
          % (hit, refused))
    if refused < hit:
        fail("%d changed payload bytes came out as if whole" % (hit - refused))


def controls(mx, graded, work):
    print("controls")
    # (a) a fork changed after extraction must fail section 1's check.
    p = os.path.join(FIXDIR, "vise-wild-sizzler")
    g = graded.get(p)
    if g is None:
        g = grade(mx, p, work, quiet=True)
    ver, n, got, recs = g
    pth = paths(recs)
    r = stored(recs, 1)[0]
    data = bytearray(got[pth[r["k"]]][0] or b"\0")
    data[len(data) // 2] ^= 1
    c = zlib.crc32(got[pth[r["k"]]][1], zlib.crc32(bytes(data))) & 0xFFFFFFFF
    if c == r["crc"]:
        fail("control: a changed fork kept its CRC")
    # (b) a record's CRC changed in the archive: the engine must refuse.
    blob = bytearray(open(p, "rb").read())
    cat = struct.unpack(">I", blob[36:40])[0]
    at = blob.index(b"FVCT", cat)
    blob[at + 4 + 80] ^= 1
    v = os.path.join(work, "c.bin")
    with open(v, "wb") as f:
        f.write(blob)
    t = run([mx, "t", v])
    if t.returncode == 0 or b"checksum" not in t.stderr:
        fail("control: a wrong CRC in the record was not refused")
    # (c) folders read as indexes must give other paths on this one.
    p = os.path.join(FIXDIR, "vise-wild-acrobat-movie")
    if os.path.exists(p):
        ver, nparts, recs = catalogue(open(p, "rb").read())
        a, b = paths(recs), paths(recs, index=True)
        if all(a[r["k"]] == b[r["k"]] for r in stored(recs, nparts)):
            fail("control: depth and index read the same paths here")
    print("  three controls run" if not FAILS else "  controls with failures")


def write_manifest(mx, path, work):
    base = os.path.basename(path)
    ver, n, got, recs = grade(mx, path, work)
    pth = paths(recs)
    ms = installer_vise(path, work) \
        if 0x80010308 <= ver and ver not in VISE_X else None
    iv = ms if isinstance(ms, collections.Counter) and ms == multiset(got) \
        else None
    entries = []
    for r in stored(recs, struct.unpack(">I", data_fork(
            open(path, "rb").read())[20:24])[0]):
        data, rsrc, ty, cr, flags = got[pth[r["k"]]]
        orc = "the record's CRC-32 over both forks"
        if iv:
            orc += ", and installer-vise"
        entries.append(dict(
            name=pth[r["k"]].decode("mac_roman"),
            type=ty.decode("mac_roman"), creator=cr.decode("mac_roman"),
            finder_flags=flags,
            data_size=len(data), data_sha256=sha(data), data_oracle=orc,
            rsrc_size=len(rsrc), rsrc_sha256=sha(rsrc), rsrc_oracle=orc))
    blob = open(path, "rb").read()
    man = dict(entries=entries, fixture=base, format="Installer VISE",
               oracle=("each file's own CRC-32, data then resource fork, as "
                       "the installer stores it, with the catalogue read "
                       "independently of the engine; installer-vise for "
                       "the compressed catalogues (tools/run_vise.py)"),
               sha256=sha(blob), size=len(blob))
    out = os.path.join(FIXDIR, "manifests", base + ".json")
    with open(out, "w") as f:
        json.dump(man, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    print("  wrote", os.path.relpath(out, ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract",
                    default=os.path.join(ROOT, "build", "rel", "macextract"))
    ap.add_argument("--extra")
    ap.add_argument("--manifest", nargs="+")
    a = ap.parse_args()
    tmpbase = os.path.join(ROOT, ".tmp")
    os.makedirs(tmpbase, exist_ok=True)
    work = tempfile.mkdtemp(prefix="vise-", dir=tmpbase)
    try:
        if a.manifest:
            for t in a.manifest:
                write_manifest(a.macextract, t, work)
            return 1 if FAILS else 0
        graded = main_grade(a.macextract, a.extra, work)
        set_grade(a.macextract, work)
        stub_grade(a.macextract)
        small = min((p for p in graded if p.startswith(FIXDIR)),
                    key=os.path.getsize, default=None)
        if small:
            damage(a.macextract, small, work)
        controls(a.macextract, graded, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if FAILS:
        print("run_vise: %d FAILURES" % len(FAILS))
        return 1
    print("run_vise: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

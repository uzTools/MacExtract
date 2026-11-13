#!/usr/bin/env python3
"""run_viseold.py — the VISE before Installer VISE 3.5 (src/fmt_viseold.c),
graded by installed copies of two of its files and by its own stream.

    run_viseold.py [--macextract BIN]
    run_viseold.py --manifest FIXTURE...   # write fixtures/manifests/*.json

The archives are the corpus's `vise-old-*` fixtures. This file reads each
one ITSELF — header, catalogue and stream — with a decoder transcribed from
the 68k of MindVision's own 'Dcmp' (fmt_viseold.c's header comment), and
holds the engine to it:

  1. Every archive: the stream must end at the catalogue to the byte and
     expand to the sum of the records' lengths, the format's only
     consistency; then the engine's files must be this reading's, every
     path, both forks, type, creator and Finder flags.
  2. Installed copies, which owe nothing to either reader. DeltaSymbol.TT
     (in `vise-old-deltasymbol`) against the one on PC World's July 1994
     disc: the whole resource fork equal but for the 240 bytes the Resource
     Manager reserves (16..255), where an installed file keeps its own
     Finder record. Serial Tool (the last file of `vise-old-powertalk-cis`,
     after 550 KB of one stream) against four Serial Tool 1.0.2 from Apple's
     Basic Connectivity Set, a magazine disc and a Telecom disk: every
     resource equal but 'vers' 2, which names the bundle it shipped in.
     The copies are in the cache (ORACLES); without them this section is
     reported as not run.
  3. Damage, on the smallest archive: stream bytes changed and the file
     cut: no crash, no hang, every cut refused. How many changed bytes
     are refused is printed, not required: nothing in the format can see
     a change that leaves the stream's end where it was.

And CONTROLS, each of which must fail: this file's decoder with a STABLE
sort in place of the quicksort (no stream may then end at its catalogue:
the tie order is what the codes are); a resource of the engine's
DeltaSymbol.TT changed in one byte (section 2's comparison); a record's
length raised by one in the archive (the engine must refuse it).

**What it cannot see.** Dates and the Finder location, which nothing
grades. A stream damaged in a way that keeps its length, which the format
has no checksum to catch (section 3 counts how often that is). Whether the
paths are the ones the installer writes: an Apple Installer script that
installs a `.vct` may name its target otherwise ('infa' atoms), and no
installer was run. Section 1 is the same reading done twice by one author
— it catches a slip in either transcription, not a misreading of the
68k; sections 2 and the first control are what test the reading.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # beside it
import run_vise  # noqa: E402  (its run, ours and sha)

ROOT = os.path.dirname(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))
FIXDIR = os.path.join(ROOT, "fixtures")
CACHE = os.path.expanduser("~/.cache/macextract/specimens/vise/old/oracle")
# The installed copies, fetched from Discmaster as AppleDouble (/file/ of
# the `.rsrc` row): (cache file, the URL path after /file/).
ORACLES = {
    "deltasymbol-pcw0794.rsrc":
        "22928/pcw-0794.bin/mac/Demos⁄Tours/DeltaGraph•demo/DeltaSymbol.TT/"
        "DeltaSymbol.TT.rsrc",
    "serialtool-0.rsrc":
        "32701/ADC Developer CD (1993-08) (''CD Slickers'')_dmg/Disc01.dmg/"
        "Tool Chest/Networking & Communications/Communications Toolbox/"
        "Basic Connectivity Set 1.1.1/Serial Tool/Serial Tool.rsrc",
    "serialtool-1.rsrc":
        "20850/Mac Magazin and MacEasy Magazine CD - Issue 08.iso/"
        "Sharewarebibliothek/DFÜ/commsService 2.0.2 Final/Comms Tools/"
        "Serial Tool/Serial Tool.rsrc",
    "serialtool-2.rsrc":
        "32738/Mac Tech Seed May '96/Mac Tech Seed May '96.toast/mac/"
        "Unity a3c3/CD Extras/Apple Telecom/PC Card Modems/Apple Telecom "
        "Disk 1/Telecom Software/Serial Tool/Serial Tool.rsrc",
    "serialtool-4.rsrc":
        "37787/Hexen-Mac-IBM-source.rar/Hexen-Mac-IBM-source.iso/Mac Hexen/"
        "(Ship Directory)/Put In System Folder/Comm Toolbox Tools/"
        "Serial Tool/Serial Tool.rsrc",
}
FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("  FAIL", msg)


# ---- this file's own reading of the format --------------------------------

def lengths(b, p):
    n = b[p]
    p += 1
    out = []
    for _ in range(n):
        v = b[p]
        p += 1
        out += [v & 31] * ((v >> 5) + 1)
    if len(out) > 256:
        raise ValueError("more than 256 lengths")
    return out + [0] * (256 - len(out)), p


def quicksort(idx, L, lo, hi):
    """'Dcmp' 0x7cc: sort(lo, hi), recursive as the 68k is."""
    i, j = lo, hi - 1
    piv = L[idx[(hi + lo - 1) // 2]]
    while True:
        while L[idx[i]] < piv:
            i += 1
        while L[idx[j]] > piv:
            j -= 1
        if j >= i:
            idx[i], idx[j] = idx[j], idx[i]
            i += 1
            j -= 1
        if j < i:
            break
    if j > lo:
        quicksort(idx, L, lo, j + 1)
    if hi > i:
        quicksort(idx, L, i, hi)


def stable(idx, L, lo, hi):
    """The control's sort: by length, ties in symbol order."""
    idx[lo:hi] = sorted(idx[lo:hi], key=lambda s: L[s])


def tree(L, sort):
    """{(node, bit): child}, a child a node number or 0x8000 | symbol."""
    idx = list(range(256))
    sort(idx, L, 0, 256)
    code, cur, depth = [0] * 256, 0, 32
    for i in range(255, -1, -1):
        s = idx[i]
        if L[s] <= 0:
            break
        depth = min(depth, L[s])
        code[s] = cur
        k = depth
        while k and (cur >> (k - 1)) & 1:
            cur &= ~(1 << (k - 1))
            k -= 1
        if k:
            cur |= 1 << (k - 1)
    kid, nxt = {}, 1
    for s in range(256):
        if not L[s]:
            continue
        node = 0
        for k in range(1, L[s]):
            b = (code[s] >> (k - 1)) & 1
            v = kid.get((node, b))
            if v is None:
                kid[(node, b)] = v = nxt
                nxt += 1
            elif v & 0x8000:
                raise ValueError("prefix clash")
            node = v
        b = (code[s] >> (L[s] - 1)) & 1
        if (node, b) in kid:
            raise ValueError("prefix clash")
        kid[(node, b)] = 0x8000 | s
    return kid


def expand(b, at, end, sort=quicksort):
    """The stream at `at`: (bytes, where it ended)."""
    size = struct.unpack(">I", b[at:at + 4])[0]
    lowb = ((b[at + 4] >> 2) & 3) + 5
    p = at + 5
    trees = []
    for _ in range(3):
        L, p = lengths(b, p)
        trees.append(tree(L, sort))
    lit, ln, dist = trees
    bit = p * 8

    def one():
        nonlocal bit
        if bit >> 3 >= end:
            raise ValueError("past the stream")
        v = (b[bit >> 3] >> (bit & 7)) & 1
        bit += 1
        return v

    def sym(t):
        node = 0
        while True:
            v = t.get((node, one()))
            if v is None:
                raise ValueError("no such code")
            if v & 0x8000:
                return v & 0xFF
            node = v

    out = bytearray()
    while len(out) < size:
        if one():
            out.append(sym(lit))
        else:
            low = 0
            for k in range(lowb):
                low |= one() << k
            d = low + (sym(dist) << lowb) + 3
            n = sym(ln) + 3
            if d > len(out):
                raise ValueError("a match before the start")
            for _ in range(n):
                out.append(out[-d])
    return bytes(out[:size]), (bit + 7) >> 3


def read(path, sort=quicksort):
    """(files {path: (data, rsrc, type, creator, flags)}, a problem or
    None) as this file reads the archive."""
    b = open(path, "rb").read()
    cat = struct.unpack(">I", b[20:24])[0]
    n = struct.unpack(">H", b[cat:cat + 2])[0]
    recs = [b[cat + 4 + 80 * i:cat + 84 + 80 * i] for i in range(n)]
    total = sum(struct.unpack(">I", r[26:30])[0] +
                struct.unpack(">I", r[34:38])[0] for r in recs if r[0] == 0x33)
    try:
        out, end = expand(b, 24, cat, sort)
    except (ValueError, IndexError) as e:
        return {}, "the stream does not decode: %s" % e
    problem = None
    if end != cat or len(out) != total:
        problem = "the stream ends at %d, the catalogue is at %d; %d bytes " \
                  "for %d" % (end, cat, len(out), total)
    files, up, p = {}, [], 0
    for r in recs:
        name = r[49:49 + r[48]].replace(b"/", b":")
        if r[0] == 0x80:
            up.append(name)
        elif r[0] == 0xC0:
            up.pop()
        else:
            rl = struct.unpack(">I", r[26:30])[0]
            dl = struct.unpack(">I", r[34:38])[0]
            files[b"/".join(up + [name])] = (
                out[p + rl:p + rl + dl], out[p:p + rl], r[2:6], r[6:10],
                struct.unpack(">H", r[10:12])[0])
            p += rl + dl
    return files, problem


# ---- the resource forks of section 2 ---------------------------------------

def appledouble(b, want=2):
    n = struct.unpack(">H", b[24:26])[0]
    for i in range(n):
        eid, off, ln = struct.unpack(">III", b[26 + 12 * i:38 + 12 * i])
        if eid == want:
            return b[off:off + ln]
    return b""


def resources(f):
    do, mo, dl, ml = struct.unpack(">IIII", f[:16])
    m = f[mo:mo + ml]
    tl = struct.unpack(">H", m[24:26])[0]
    out = {}
    for i in range(struct.unpack(">H", m[tl:tl + 2])[0] + 1):
        t, c, ro = struct.unpack(">4sHH", m[tl + 2 + 8 * i:tl + 10 + 8 * i])
        for j in range(c + 1):
            e = m[tl + ro + 12 * j:tl + ro + 12 * j + 8]
            rid = struct.unpack(">h", e[:2])[0]
            off = int.from_bytes(e[5:8], "big")
            ln = struct.unpack(">I", f[do + off:do + off + 4])[0]
            out[(t, rid)] = f[do + off + 4:do + off + 4 + ln]
    return out


def oracle(name):
    p = os.path.join(CACHE, name)
    return appledouble(open(p, "rb").read()) if os.path.exists(p) else None


def installed(got):
    """Section 2 over the engine's forks: the problems found, or None when
    the copies are not here."""
    ds = oracle("deltasymbol-pcw0794.rsrc")
    st = [oracle(k) for k in sorted(ORACLES) if k.startswith("serialtool")]
    if ds is None or None in st:
        return None
    bad = []
    mine = got["vise-old-deltasymbol"].get(b"DeltaSymbol.TT")
    if mine is None or len(mine[1]) != len(ds) or \
            mine[1][:16] != ds[:16] or mine[1][256:] != ds[256:]:
        bad.append("DeltaSymbol.TT is not the installed copy outside "
                   "bytes 16..255")
    elif resources(mine[1]) != resources(ds):
        bad.append("DeltaSymbol.TT's resources are not the installed copy's")
    mine = got["vise-old-powertalk-cis"].get(b"Serial Tool")
    for i, ref in enumerate(st):
        a = resources(mine[1]) if mine else {}
        r = resources(ref)
        if set(a) != set(r) or any(a[k] != r[k] for k in a
                                   if k != (b"vers", 2)):
            bad.append("Serial Tool is not installed copy %d but its "
                       "'vers' 2" % i)
    return bad


# ---- the sections -----------------------------------------------------------

def fixtures():
    return sorted(os.path.join(FIXDIR, f) for f in os.listdir(FIXDIR)
                  if f.startswith("vise-old-"))


def grade(mx, work):
    print("1. every archive, read here and by the engine")
    got, nfiles = {}, 0
    for path in fixtures():
        base = os.path.basename(path)
        want, problem = read(path)
        if problem:
            fail("%s: %s" % (base, problem))
        out = os.path.join(work, "x")
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        mine, rc, err = run_vise.ours(mx, path, out)
        if rc != 0:
            fail("%s: x exited %d: %s" % (base, rc, err.decode(
                "mac_roman")[-300:]))
        if set(mine) != set(want):
            fail("%s: the files are not the catalogue's: extra %s, missing %s"
                 % (base, sorted(set(mine) - set(want))[:3],
                    sorted(set(want) - set(mine))[:3]))
        for p, w in want.items():
            g = mine.get(p)
            if g is not None and (g[0] or b"", g[1], g[2], g[3], g[4]) != w:
                fail("%s: %s is not this file's reading" % (base, p))
        got[base] = mine
        nfiles += len(want)
    print("  %d archives, %d files" % (len(got), nfiles))
    return got


def damage(mx, work):
    path = min(fixtures(), key=os.path.getsize)
    print("3. damage, %s" % os.path.basename(path))
    blob = open(path, "rb").read()
    cat = struct.unpack(">I", blob[20:24])[0]
    hit = refused = 0
    for at in range(30, cat, max(1, cat // 40)):
        b = bytearray(blob)
        b[at] ^= 0x5A
        v = os.path.join(work, "v.bin")
        with open(v, "wb") as f:
            f.write(b)
        r = run_vise.run([mx, "t", v], timeout=120)
        if r.returncode < 0 or r.returncode > 2:
            fail("byte %d changed: exit %d" % (at, r.returncode))
        hit += 1
        refused += r.returncode != 0
    cuts = 0
    for cut in range(30, len(blob), max(1, len(blob) // 30)):
        v = os.path.join(work, "v.bin")
        with open(v, "wb") as f:
            f.write(blob[:cut])
        r = run_vise.run([mx, "t", v], timeout=120)
        cuts += 1
        if r.returncode == 0 or r.returncode > 2 or r.returncode < 0:
            fail("cut at %d: exit %d" % (cut, r.returncode))
    print("  %d stream bytes changed, %d of them refused; %d cuts, all "
          "refused" % (hit, refused, cuts))


def controls(mx, got, work):
    print("controls")
    # (a) a stable sort must leave no stream ending at its catalogue.
    for path in fixtures():
        if read(path, stable)[1] is None:
            fail("control: %s reads with a stable sort too"
                 % os.path.basename(path))
    # (b) one resource changed must fail section 2.
    if installed(got) is not None:
        g = dict(got)
        ds = dict(g["vise-old-deltasymbol"])
        d, r, ty, cr, fl = ds[b"DeltaSymbol.TT"]
        r = bytearray(r)
        r[len(r) // 2] ^= 1
        ds[b"DeltaSymbol.TT"] = (d, bytes(r), ty, cr, fl)
        g["vise-old-deltasymbol"] = ds
        if not installed(g):
            fail("control: a changed DeltaSymbol.TT passed section 2")
    # (c) a record's length raised by one: the engine must refuse it.
    p = os.path.join(FIXDIR, "vise-old-deltasymbol")
    blob = bytearray(open(p, "rb").read())
    cat = struct.unpack(">I", blob[20:24])[0]
    struct.pack_into(">I", blob, cat + 4 + 26,
                     struct.unpack(">I", blob[cat + 30:cat + 34])[0] + 1)
    v = os.path.join(work, "c.bin")
    with open(v, "wb") as f:
        f.write(blob)
    if run_vise.run([mx, "t", v]).returncode == 0:
        fail("control: a record one byte longer than its stream passed")
    print("  three controls run" if not FAILS else "  controls with failures")


def write_manifest(path):
    base = os.path.basename(path)
    files, problem = read(path)
    if problem:
        fail("%s: %s" % (base, problem))
        return
    orc = ("tests/harness/run_viseold.py's own decoder, read out of the 68k; the "
           "stream ends at its catalogue")
    entries = []
    for p, (data, rsrc, ty, cr, fl) in sorted(files.items()):
        entries.append(dict(
            name=p.decode("mac_roman"), type=ty.decode("mac_roman"),
            creator=cr.decode("mac_roman"), finder_flags=fl,
            data_size=len(data), data_sha256=run_vise.sha(data),
            data_oracle=orc, rsrc_size=len(rsrc),
            rsrc_sha256=run_vise.sha(rsrc), rsrc_oracle=orc))
    blob = open(path, "rb").read()
    man = dict(entries=entries, fixture=base, format="Installer VISE",
               oracle=("tests/harness/run_viseold.py's own reading of the stream "
                       "and catalogue; DeltaSymbol.TT and Serial Tool also "
                       "against installed copies"),
               sha256=run_vise.sha(blob), size=len(blob))
    out = os.path.join(FIXDIR, "manifests", base + ".json")
    with open(out, "w") as f:
        json.dump(man, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    print("  wrote", os.path.relpath(out, ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract",
                    default=os.path.join(ROOT, "build", "rel", "macextract"))
    ap.add_argument("--manifest", nargs="+")
    a = ap.parse_args()
    if a.manifest:
        for t in a.manifest:
            write_manifest(t)
        return 1 if FAILS else 0
    if not fixtures():
        print("run_viseold: no vise-old-* fixtures; nothing run")
        return 0
    tmpbase = os.path.join(ROOT, ".tmp")
    os.makedirs(tmpbase, exist_ok=True)
    work = tempfile.mkdtemp(prefix="viseold-", dir=tmpbase)
    try:
        got = grade(a.macextract, work)
        print("2. installed copies")
        bad = installed(got)
        if bad is None:
            print("  NOT RUN: the copies are not in %s" % CACHE)
        else:
            for m in bad:
                fail(m)
            print("  DeltaSymbol.TT and Serial Tool x4: %s"
                  % ("equal" if not bad else "%d problems" % len(bad)))
        damage(a.macextract, work)
        controls(a.macextract, got, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if FAILS:
        print("run_viseold: %d FAILURES" % len(FAILS))
        return 1
    print("run_viseold: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

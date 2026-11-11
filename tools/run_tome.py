#!/usr/bin/env python3
"""run_tome.py — Apple Installer Tomes (src/fmt_tome.c), graded by deark and
by the files Apple's Installer installed.

    run_tome.py [--macextract BIN] [--deark BIN] [--extra DIR]
    run_tome.py --manifest FIXTURE...     # write fixtures/manifests/*.json

The Tomes are the corpus's `tome-*` fixtures, and with --extra every file in
DIR as well (the 39 off the System 7.5.5 and Mac OS 8.6 media, DECISIONS.md
2026-11-10, *the archive the Installer reads*). The record table is read
here, independently of the engine, for every name, length, type, creator and
flag word compared.

  1. deark: every fork deark's own Tome module decodes must equal the
     engine's byte for byte. deark has no text codec and fails those forks;
     they are counted, and graded by section 2 where Apple's copy exists.
     deark also widens InstaCompOne's long distance one output byte early
     (position 1644; DECISIONS.md, same entry) — no fork of the corpus's
     Tomes reaches that, and a disagreement is a failure here either way.
  2. Installed copies: the System 7.5.5 disk the `tome-wild-install*`
     fixtures came from holds what Apple's Installer installed out of them.
     A file found there by name, type and creator must have the engine's
     data fork byte for byte and its resource fork resource for resource
     (the map's header carries the Resource Manager's own run-time fields);
     where the installed copy's 'vers' 1 differs it is another release and
     is counted, not graded. Skipped, LOUDLY, where the disk image is not
     cached.
  3. Damage: every 61st byte of a fork stream changed, and the file cut at
     every 997th byte. There is no checksum, so a change can decode to the
     right length silently; what must hold is no crash, no hang, and every
     cut entry refused. The number refused of the changed ones is reported.

And CONTROLS: both comparisons of a fork changed in one byte must fail, and
a record claiming one byte more than its stream's tokens use must be refused
— the exact end is the one test of a stream the format leaves, and this
proves it is made. Every one of the 1,201 forks of the 39 Tomes ends with
its output complete and no bit of input left.

**What it cannot see.** The forks' own checksum, which nobody has
identified. A text-codec fork with no installed copy here (the 8.6
fixtures' modem scripts and Web Sharing's text forks): only the exact end
grades it. The two longest text-codec length codes, which no stream here
uses. Tomes in 'part' resources, which the engine does not read
(OPEN_ITEMS.md). Dates, which run_diff.py does not compare either.
"""
import argparse
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
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXDIR = os.path.join(ROOT, "fixtures")
VMAC = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
DISK755 = os.path.join(VMAC, "macosinstall755.dsk")
OS9IMG = os.path.expanduser(os.environ.get(
    "UNC_OS9_IMG", "~/.cache/macextract/qemu-ppc/MacOS9.img"))
FAILS = []
LISTRE = re.compile(rb"^f +(\d+) +(\d+) ([0-9a-f]{8})/([0-9a-f]{8}) "
                    rb"([0-9a-f]{4}) (.*)$")


def fail(msg):
    FAILS.append(msg)
    print("  FAIL", msg)


def run(cmd, **kw):
    kw.setdefault("timeout", 600)
    return subprocess.run(cmd, capture_output=True, **kw)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def records(data):
    """The record table, read here independently of the engine."""
    n = struct.unpack(">H", data[0x1a:0x1c])[0]
    out = []
    for i in range(n):
        r = data[0x24 + i * 0x80:0x24 + (i + 1) * 0x80]
        dl, do, dc = struct.unpack(">III", r[0x3c:0x48])
        rl, ro, rc = struct.unpack(">III", r[0x4c:0x58])
        out.append(dict(at=0x24 + i * 0x80,
                        name=r[7:7 + min(r[6], 31)],
                        type=r[0x26:0x2a], creator=r[0x2a:0x2e],
                        flags=struct.unpack(">H", r[0x36:0x38])[0],
                        data=(dl if dc else 0, do, dc),
                        rsrc=(rl if rc else 0, ro, rc)))
    return out


def ours(mx, path, out):
    """The engine's forks by record index: [(data, rsrc)], or None."""
    lst = run([mx, "l", "--finder", "--raw-names", path])
    if lst.returncode != 0:
        return None
    rows = [m for m in map(LISTRE.match, lst.stdout.split(b"\n")) if m]
    x = run([mx, "x", "--raw-names", "-o", out, path])
    if x.returncode != 0:
        # Each entry refused is named; the rest are still graded.
        for line in x.stderr.decode("mac_roman").splitlines():
            fail("%s: %s" % (os.path.basename(path), line.strip()))
    got = []
    for m in rows:
        p = os.path.join(out.encode(), m.group(6).replace(b"/", b":"))
        got.append((readf(p), readf(p + b".rsrc"), m))
    return got


def readf(p):
    try:
        with open(p, "rb") as f:
            return f.read()
    except OSError:
        return None


def adf_rsrc(blob):
    """Entry 2 of an AppleDouble file."""
    n = struct.unpack(">H", blob[24:26])[0] if len(blob) >= 26 else 0
    for i in range(n):
        eid, off, ln = struct.unpack(">III", blob[26 + 12 * i:38 + 12 * i])
        if eid == 2:
            return blob[off:off + ln]
    return b""


def same_name(raw, nm):
    """deark's file name for a record's name: MacRoman to UTF-8, the
    characters a file name cannot hold replaced by '_'
    (reference/deark/src/deark-util.c). Its Tome module keeps a trailing
    space (" PowerBook Display ", measured)."""
    want = raw.decode("mac_roman")
    return len(want) == len(nm) and \
        all(a == b or b == "_" for a, b in zip(want, nm))


def deark_forks(deark, path, out, recs):
    """{record index: {'data'|'rsrc': bytes}} for every fork deark wrote.
    deark numbers the FILES it writes — a data fork and an AppleDouble file
    each — so they are matched to records by name, in order; and a fork it
    reported failing is not taken, whatever it wrote."""
    r = run([deark, "-m", "tome", "-od", out, "-o", "x", path])
    errs = (r.stdout + r.stderr).decode("utf-8", "replace")
    failed = {}
    for line in errs.splitlines():
        m = re.search(r"Decompression failed for file (.*)\[(data|rsrc) fork\]"
                      r": (.*)$", line)
        if m:
            failed[(m.group(1), m.group(2))] = m.group(3).strip()
    files = []
    for f in os.listdir(out):
        m = re.match(r"^x\.(\d{3,})\.(.*)$", f)
        if m:
            files.append((int(m.group(1)), m.group(2), f))
    files.sort()
    got, i = {}, 0
    for _, nm, f in files:
        adf = nm.endswith(".adf")
        if adf:
            nm = nm[:-4]
        while i < len(recs) and not same_name(recs[i]["name"], nm):
            i += 1
        if i == len(recs):
            fail("%s: deark wrote %r, which no record names"
                 % (os.path.basename(path), f))
            break
        fork = "rsrc" if adf else "data"
        if (recs[i]["name"].decode("mac_roman"), fork) not in failed:
            blob = open(os.path.join(out, f), "rb").read()
            got.setdefault(i, {})[fork] = adf_rsrc(blob) if adf else blob
        if adf:
            i += 1
    for i, r in enumerate(recs):
        for fork in ("data", "rsrc"):
            why = failed.get((r["name"].decode("mac_roman"), fork))
            if why:
                got.setdefault(i, {})[fork + "_why"] = why
    return got


# --- resource forks, resource by resource --------------------------------

def resources(r):
    """{(type, id): (attributes, name, bytes)}, or None if not a fork."""
    if r is None or len(r) < 16:
        return {} if r == b"" else None
    try:
        do, mo, _, ml = struct.unpack(">IIII", r[:16])
        m = r[mo:mo + ml]
        tl, nl = struct.unpack(">HH", m[24:28])
        t = m[tl:]
        out = {}
        for i in range(struct.unpack(">H", t[:2])[0] + 1):
            ty, c, off = struct.unpack(">4sHH", t[2 + 8 * i:10 + 8 * i])
            for j in range(c + 1):
                rid, no, a = struct.unpack(">hhI",
                                           t[off + 12 * j:off + 12 * j + 8])
                o = do + (a & 0xffffff)
                nm = b"" if no == -1 else \
                    m[nl + no + 1:nl + no + 1 + m[nl + no]]
                ln = struct.unpack(">I", r[o:o + 4])[0]
                out[(ty, rid)] = (a >> 24, nm, r[o + 4:o + 4 + ln])
        return out
    except (struct.error, IndexError):
        return None


# --- the installed System 7.5.5 ------------------------------------------

class Volume:
    """hfsutils over one image, with a scratch HOME for its .hcwd. `strict`:
    this disk holds what Apple's Installer installed out of these very
    Tomes, so any difference between a file of one release is a failure."""

    name = "System 7.5.5"
    strict = True

    def __init__(self, img, home):
        self.env = dict(os.environ, HOME=home)
        r = run(["hmount", img], env=self.env)
        self.ok = r.returncode == 0
        self.index = {}
        if not self.ok:
            return
        ls = run(["hls", "-R", "-l"], env=self.env).stdout
        d = b""
        for line in ls.split(b"\n"):
            if line.startswith(b":") and line.endswith(b":"):
                d = line
                continue
            m = re.match(rb"^f\s+(.{4})/(.{4})\s+\d+\s+\d+\s+\w{3}\s+\d+\s+"
                         rb"\S+ (.*)$", line)
            if m:
                self.index.setdefault((m[3], m[1], m[2]), []).append(d + m[3])

    def lookup(self, rec):
        return self.index.get((rec["name"], rec["type"], rec["creator"]), [])

    def label(self, hp):
        return hp.decode("mac_roman")

    def forks(self, hpath, tmp):
        dst = os.path.join(tmp, "inst.bin")
        if os.path.exists(dst):
            os.unlink(dst)
        run([b"hcopy", b"-m", hpath, dst.encode()], env=self.env)
        mb = readf(dst)
        if not mb or len(mb) < 128:
            return None, None
        dl, rl = struct.unpack(">II", mb[83:91])
        return mb[128:128 + dl], mb[128 + ((dl + 127) // 128) * 128:][:rl]

    def close(self):
        if self.ok:
            run(["humount"], env=self.env)


class OS9Volume:
    """The Mac OS 9 image's HFS Plus volume, both forks through
    tools/hfsplus.py, whose own control agrees with 7-Zip on every file of
    it. A LATER release than the Tomes here: equal bytes grade a fork, and a
    difference fails only between two copies of one 'vers' 1. Resources
    are compared without 'vers' 2, the release's own stamp."""

    name = "Mac OS 9"
    strict = False

    def __init__(self, img):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import hfsplus
        self.v = hfsplus.Volume(img)
        self.ok = True
        self.index = {}
        for p, (ty, cr, _, _) in self.v.files.items():
            leaf = p.rsplit(":", 1)[-1]
            self.index.setdefault((leaf, ty, cr), []).append(p)

    def lookup(self, rec):
        name = unicodedata.normalize("NFC", rec["name"].decode("mac_roman"))
        return self.index.get((name, rec["type"], rec["creator"]), [])

    def label(self, p):
        return p

    def forks(self, p, tmp):
        try:
            return self.v.forks(p)[2:]
        except ValueError:
            return None, None

    def close(self):
        pass


def vers1(res):
    v = (res or {}).get((b"vers", 1))
    return v[2] if v else None


def installed_verdict(vol, rec, mine, tmp):
    """{'data'|'rsrc': 'equal' | 'release' | 'absent' | a failure string}
    for the forks the record has: a data fork byte for byte, a resource
    fork resource for resource (the map's header holds the Resource
    Manager's run-time fields). 'release' is a difference between two
    releases of the file: their 'vers' 1 differ, or on a non-strict volume
    neither says."""
    forks = [f for f in ("data", "rsrc") if rec[f][2]]
    out = {f: "absent" for f in forks}
    A = resources(mine[1] or b"")
    for hp in vol.lookup(rec):
        d, r = vol.forks(hp, tmp)
        if d is None:
            continue
        B = resources(r)
        same = vers1(A) == vers1(B) and (vol.strict or vers1(A) is not None)
        if not vol.strict and A is not None and B is not None:
            # 'vers' 2 is the package's version, the release the file
            # shipped in: Mac OS 9 restamps it on files it carries
            # unchanged (measured: the only resource of 68 files that
            # differs), so a later release is compared without it.
            A = {k: x for k, x in A.items() if k != (b"vers", 2)}
            B = {k: x for k, x in B.items() if k != (b"vers", 2)}
        for f in forks:
            if out[f] == "equal":
                continue
            if f == "data":
                ok = d == (mine[0] or b"")
                why = "data fork differs from %s" % vol.label(hp)
            else:
                ok = A is not None and B is not None and A == B
                diff = sorted(k for k in set(A or {}) | set(B or {})
                              if (A or {}).get(k) != (B or {}).get(k))
                why = "resources differ from %s: %r" % (vol.label(hp),
                                                        diff[:6])
            out[f] = "equal" if ok else (why if same else "release")
    return out


# --- sections --------------------------------------------------------------

def grade(mx, deark, tomes, work, vols):
    tot = dict(deark=0, nodeark=0, ungraded=0)
    for v in vols:
        tot[v.name] = tot[v.name + " release"] = 0
    for t in tomes:
        base = os.path.basename(t)
        recs = records(open(t, "rb").read())
        a, b = os.path.join(work, "ours"), os.path.join(work, "deark")
        for d in (a, b):
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d)
        got = ours(mx, t, a)
        if got is None or len(got) != len(recs):
            fail("%s: the engine listed or extracted %s of %d records"
                 % (base, None if got is None else len(got), len(recs)))
            continue
        dk = deark_forks(deark, t, b, recs)
        for i, (rec, (od, orr, m)) in enumerate(zip(recs, got)):
            tag = "%s #%d %r" % (base, i, rec["name"].decode("mac_roman"))
            if m.group(3) != rec["type"].hex().encode() or \
               m.group(4) != rec["creator"].hex().encode() or \
               int(m.group(5), 16) != rec["flags"]:
                fail("%s: type/creator/flags %r" % (tag, m.groups()[2:5]))
            mine = (od or b"", orr or b"")
            if len(mine[0]) != rec["data"][0] or len(mine[1]) != rec["rsrc"][0]:
                fail("%s: lengths %d/%d, the record says %d/%d"
                     % (tag, len(mine[0]), len(mine[1]), rec["data"][0],
                        rec["rsrc"][0]))
            open_forks = set()
            for fork, k in (("data", 0), ("rsrc", 1)):
                if rec[fork][2] == 0:
                    continue
                theirs = dk.get(i, {}).get(fork)
                if theirs is None:
                    tot["nodeark"] += 1
                    open_forks.add(fork)
                elif theirs != mine[k]:
                    fail("%s %s: differs from deark" % (tag, fork))
                else:
                    tot["deark"] += 1
            for v in vols:
                for f, verdict in installed_verdict(v, rec, mine,
                                                    work).items():
                    if verdict == "equal":
                        if f in open_forks:
                            tot[v.name] += 1
                        open_forks.discard(f)
                    elif verdict == "release":
                        tot[v.name + " release"] += 1
                    elif verdict != "absent":
                        fail("%s: %s" % (tag, verdict))
            tot["ungraded"] += len(open_forks)
    print("  deark: %(deark)d forks equal; %(nodeark)d it cannot decode"
          % tot)
    for v in vols:
        print("  installed, %s: %d forks deark could not grade equal; %d "
              "forks another release" % (v.name, tot[v.name],
                                         tot[v.name + " release"]))
    print("  %(ungraded)d forks graded by no reader, by the exact end alone"
          % tot)
    return tot


def damage(mx, t, work):
    data = bytearray(open(t, "rb").read())
    recs = records(bytes(data))
    good = run([mx, "t", t]).returncode
    if good != 0:
        fail("%s: the undamaged Tome does not test clean" % os.path.basename(t))
    spans = [(r[f][1], r[f][2]) for r in recs for f in ("data", "rsrc")
             if r[f][2]]
    p = os.path.join(work, "damaged")
    changed = refused = 0
    for off, ln in spans:
        for k in range(0, ln, 61):
            d = bytearray(data)
            d[off + k] ^= 0x5A
            open(p, "wb").write(d)
            try:
                r = run([mx, "t", p], timeout=60)
            except subprocess.TimeoutExpired:
                fail("%s: a changed byte at %d hangs" % (t, off + k))
                continue
            changed += 1
            refused += r.returncode != 0
            if r.returncode < 0 or b"Sanitizer" in r.stderr:
                fail("%s: a changed byte at %d crashes: %r"
                     % (t, off + k, r.stderr[-200:]))
    cuts = 0
    for cut in list(range(1, len(data), 997)) + [len(data) - 1]:
        open(p, "wb").write(data[:cut])
        r = run([mx, "t", p], timeout=60)
        if r.returncode < 0 or b"Sanitizer" in r.stderr:
            fail("%s cut at %d: crashes" % (os.path.basename(t), cut))
        elif r.returncode == 0 and any(
                f[1] + f[2] > cut for rr in recs
                for f in (rr["data"], rr["rsrc"]) if f[2]):
            fail("%s cut at %d: exit 0 with a fork past the cut"
                 % (os.path.basename(t), cut))
        cuts += 1
    print("  %s: %d changed bytes, %d refused (no checksum: the rest decode "
          "to their length); %d cuts" % (os.path.basename(t), changed,
                                         refused, cuts))


def deark_bin():
    return DEARK[0]


DEARK = [None]


def controls(mx, t, work):
    before = len(FAILS)
    data = bytearray(open(t, "rb").read())
    recs = records(bytes(data))
    # A record claiming one byte more than its stream has: the output is
    # complete with a byte of input left, which the exact end refuses. (A
    # record claiming one byte LESS is accepted, and must be: the format's
    # end rule drops a token that runs past the stream as padding and fills
    # the fork with zeros — no stream of the 1,201 here needs it, and the
    # specification's author saw forks that do.)
    pick = None
    for r in recs:
        for fork in ("data", "rsrc"):
            if r[fork][2] and r[fork][1] + r[fork][2] < len(data):
                pick = (r, fork)
    if pick is None:
        fail("CONTROL: no fork with a byte after its stream")
        return
    rec, fork = pick
    d = bytearray(data)
    at = rec["at"] + (0x44 if fork == "data" else 0x54)
    d[at:at + 4] = struct.pack(">I", rec[fork][2] + 1)
    p = os.path.join(work, "long")
    open(p, "wb").write(d)
    if run([mx, "t", p]).returncode == 0:
        fail("CONTROL: a stream one byte longer than its tokens is accepted")
    # The two comparisons see one changed byte: deark's fork against the
    # engine's, and the resource-by-resource one, inside a resource.
    a, b = os.path.join(work, "c-ours"), os.path.join(work, "c-deark")
    for x in (a, b):
        shutil.rmtree(x, ignore_errors=True)
        os.makedirs(x)
    got = ours(mx, t, a)
    dk = deark_forks(deark_bin(), t, b, recs)
    i = next((i for i in dk if dk[i].get("rsrc")), None)
    if got is None or i is None:
        fail("CONTROL: no fork both decoders wrote")
        return
    mine = bytearray(got[i][1])
    res = resources(bytes(mine))
    (ty, rid), (_, _, body) = next((k, v) for k, v in res.items() if v[2])
    at = bytes(mine).find(body)
    mine[at] ^= 1
    if dk[i]["rsrc"] == bytes(mine):
        fail("CONTROL: deark's fork and one changed byte compare equal")
    if resources(bytes(mine)) == res:
        fail("CONTROL: a changed byte in %r %d is invisible resource for "
             "resource" % (ty, rid))
    if len(FAILS) == before:
        print("  controls: a stream with a byte left refused; both "
              "comparisons see one byte")


def write_manifest(mx, deark, t, work, vols):
    """fixtures/manifests/<fixture>.json from deark and Apple's installed
    copies; a fork neither grades is unadjudicated, with the reason."""
    base = os.path.basename(t)
    recs = records(open(t, "rb").read())
    b = os.path.join(work, "deark")
    shutil.rmtree(b, ignore_errors=True)
    os.makedirs(b)
    dk = deark_forks(deark, t, b, recs)
    a = os.path.join(work, "ours")
    shutil.rmtree(a, ignore_errors=True)
    os.makedirs(a)
    got = ours(mx, t, a)
    entries = []
    for i, rec in enumerate(recs):
        e = dict(name=rec["name"].decode("mac_roman").replace("/", ":"),
                 type=rec["type"].decode("mac_roman"),
                 creator=rec["creator"].decode("mac_roman"),
                 finder_flags=rec["flags"])
        mine = (got[i][0] or b"", got[i][1] or b"") if got else None
        verdicts = [(v, installed_verdict(v, rec, mine, work))
                    for v in vols] if mine else []
        un = {}
        for fork, k in (("data", 0), ("rsrc", 1)):
            e[fork + "_size"] = rec[fork][0]
            if rec[fork][2] == 0:
                e[fork + "_sha256"] = sha(b"")
                continue
            theirs = dk.get(i, {}).get(fork)
            by = [v for v, vd in verdicts if vd.get(fork) == "equal"]
            if theirs is not None:
                e[fork + "_sha256"] = sha(theirs)
                e[fork + "_oracle"] = "deark"
                continue
            why = dk.get(i, {}).get(fork + "_why", "it wrote nothing")
            if by and fork == "data":
                # The installed copy's own bytes, equal to the engine's.
                e[fork + "_sha256"] = sha(mine[0])
                e[fork + "_oracle"] = "Apple's Installer (%s)" % by[0].name
            elif by:
                un[fork] = ("equal resource for resource to what Apple's "
                            "Installer installed on %s (tools/run_tome.py); "
                            "deark: %s" % (by[0].name, why))
            else:
                un[fork] = ("no oracle: deark: %s; no installed copy of "
                            "this release is here; the stream ends exactly at "
                            "its stated length" % why)
        if un:
            e["unadjudicated"] = un
        entries.append(e)
    data = open(t, "rb").read()
    man = dict(entries=entries, fixture=base, format="Installer Tome",
               oracle=("deark's Tome module (stored and InstaCompOne forks), "
                       "and what Apple's Installer installed, on the System "
                       "7.5.5 disk and the Mac OS 9 image, for the rest "
                       "(tools/run_tome.py)"),
               sha256=sha(data), size=len(data))
    out = os.path.join(FIXDIR, "manifests", base + ".json")
    with open(out, "w") as f:
        json.dump(man, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    print("  wrote", os.path.relpath(out, ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract",
                    default=os.path.join(ROOT, "build", "rel", "macextract"))
    ap.add_argument("--deark",
                    default=os.path.join(ROOT, "reference", "deark", "deark"))
    ap.add_argument("--extra")
    ap.add_argument("--manifest", nargs="+")
    a = ap.parse_args()
    DEARK[0] = a.deark
    if not os.access(a.deark, os.X_OK):
        fail("deark is not built: %s" % a.deark)
        return 1
    tmpbase = os.path.join(ROOT, ".tmp")
    os.makedirs(tmpbase, exist_ok=True)
    work = tempfile.mkdtemp(prefix="tome-", dir=tmpbase)
    home = os.path.join(work, "home")
    os.makedirs(home)
    vols = []
    if os.path.exists(DISK755):
        v = Volume(DISK755, home)
        if v.ok:
            vols.append(v)
    if os.path.exists(OS9IMG):
        vols.append(OS9Volume(OS9IMG))
    try:
        if a.manifest:
            for t in a.manifest:
                write_manifest(a.macextract, a.deark, t, work, vols)
            return 0
        tomes = sorted(glob.glob(os.path.join(FIXDIR, "tome-*")))
        if not tomes:
            fail("no tome-* fixture in fixtures/")
        if a.extra:
            tomes += sorted(glob.glob(os.path.join(a.extra, "*")))
        print("1-2. deark and the installed copies, %d Tomes" % len(tomes))
        for name, path in (("System 7.5.5", DISK755), ("Mac OS 9", OS9IMG)):
            if not any(v.name == name for v in vols):
                print("  SKIPPED in section 2: no %s image at %s "
                      "(tools/vmac/README.md says where it comes from)"
                      % (name, path))
        grade(a.macextract, a.deark, tomes, work, vols)
        fx = [t for t in tomes if t.startswith(FIXDIR)]
        if fx:
            print("3. damage")
            small = min(fx, key=os.path.getsize)
            damage(a.macextract, small, work)
            controls(a.macextract, small, work)
    finally:
        for v in vols:
            v.close()
        shutil.rmtree(work, ignore_errors=True)
    if FAILS:
        print("run_tome: %d FAILED" % len(FAILS))
        return 1
    print("run_tome: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

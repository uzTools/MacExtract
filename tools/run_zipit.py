#!/usr/bin/env python3
"""run_zipit.py — the ZipIt suite: nine archives ZipIt itself wrote.

Until 2026-10-04 every subject for ZipIt's three Macintosh extra fields
was written here, and `0x2605`'s premise — that the field is present
when and only when the entry's data is a MacBinary stream — was
APPNOTE.TXT 4.6.4's word alone. These nine are ZipIt's own output:
ZipIt 1.4's distribution, a Japanese-market 1.x build and 2.2.2's, two
an EV Nova plug-in author made with 2.x in 2002, a White Knight script
set from 1994, a MacTech source drop from 2007, an Atari emulator a Mac
user re-zipped, and a zip living in somebody's resource fork.

    tools/fetch_specimens.py --only zipit        get them
    tools/run_zipit.py --macextract build/macextract

How they were found is the point: ZipIt's output is a plain `.zip`, so
no search by NAME can see one. Five are self-extracting and Discmaster's
identifier knows a ZipIt self-extractor on sight (`format=zipIt`); the
other four came out of a range scan of the first local header of all
3,029 zips on the CD-ROMs and FTP mirrors `fetch_specimens.py` already
indexes (DECISIONS.md 2026-10-04, *the archive that carried its own
extractor*).

A ZipIt SEA is a code stub with the zip behind it, and `unc_zip_probe`
reads the head, so the five self-extractors are passed `-f Zip`. The
zip WALKER needs no help — it addresses the central directory
absolutely — and the four plain ones are sniffed unaided, which this
suite asserts rather than assumes. `MrTs_Paint_Folder.zip` and
`NPWritersKit.zip` are corpus fixtures as well, so `run_diff.py` grades
a real ZipIt archive of each shape with no oracle at run time.

Four things are checked, and the tallies in EXPECT are asserted so that
a download that changed, or a parse that stopped parsing, fails here
instead of going quiet:

  1. an independent Python read of every ZipIt field — central copy
     against local copy, each size against what 'ZPIT' plus the
     declared members needs;
  2. `0x2605` against the bytes: the entry is decoded and its first
     128 bytes probed as MacBinary, in both directions;
  3. `l --finder` against `lsar`: name, type, creator, Finder flags
     and both fork lengths;
  4. `x` against `unar`: every data and resource fork byte for byte.

**What it cannot see.** It does not test that a ZipIt SEA is
RECOGNISED, because it is not (OPEN_ITEMS.md). It compares no fork of
an entry whose method is out of v1 scope, and UNGRADED below names
every one with the reason. And it adjudicates no date: `lsar` reports
zip's own MS-DOS stamp where a `0x2605` entry's MacBinary header
carries two Macintosh ones, so the two are not the same field.

Nothing here fails when the specimens are absent — it prints what it
skipped and returns 0, so a fresh clone stays green.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "zipit")

sys.path.insert(0, os.path.join(REPO, "tools"))
from make_manifests import parse_appledouble          # noqa: E402

ZIPIT_IDS = (0x2605, 0x2705, 0x2805)
ZPIT = 0x5A504954

# What each specimen holds, measured 2026-10-04:
#   (entries, 0x2605, 0x2705, 0x2805, MacBinary payloads)
# A tally that moves is a specimen that changed, and a zero would
# otherwise pass unnoticed.
EXPECT = {
    "zipit-1.4.sea":                 (11, 8, 3, 0, 6),
    "zipit-1.x-jp.sea":              (5, 4, 1, 0, 3),
    "zipit-2.2.2.sea":               (74, 5, 61, 8, 5),
    "zipit-JoesFinger.zip":          (1, 0, 1, 0, 0),
    "zipit-MacTech-23.08.zip":       (13, 0, 13, 0, 0),
    "zipit-MrTs_Paint.sea":          (1, 0, 1, 0, 0),
    "zipit-MrTs_Paint_and_more.sea": (6, 2, 1, 3, 2),
    "zipit-Psycho_1.0b1.zip":        (3, 3, 0, 0, 0),
    "zipit-r95dm13.zip":             (5, 0, 5, 0, 0),
}

# Declared ungraded: how many entries, and why. Printed on every run,
# and the COUNT is checked — a fourth refused entry in this archive, or
# a refusal in any other, fails here rather than widening the
# declaration by itself.
UNGRADED = {
    "zipit-Psycho_1.0b1.zip":
        (3, "of 3 entries: Zip method 6 (Implode), refused per entry and out "
            "of v1 scope (OPEN_ITEMS.md, Part 1). No fork is compared, and "
            "the MacBinary payload cannot be reached, so neither can the "
            "type, creator or Finder flags inside it"),
}


def macbinary_datafork(blob):
    """The data fork if `blob` is MacBinary, else `blob` itself."""
    if len(blob) > 128 and blob[0] == 0 and 1 <= blob[1] <= 63 and blob[74] == 0:
        dlen = struct.unpack(">I", blob[83:87])[0]
        if 128 + dlen <= len(blob):
            return blob[128:128 + dlen]
    return blob


def is_macbinary(raw):
    """The engine's own test, in Python: a 128-byte header whose fork
    spans fill the entry exactly (src/fmt_exo.c, `zip_mb_peek`)."""
    if raw is None or len(raw) < 128 or raw[0] != 0 or raw[74] != 0:
        return None
    nlen = raw[1]
    if not 1 <= nlen <= 63:
        return None
    dlen, rlen = struct.unpack(">II", raw[83:91])
    if 128 + -(-dlen // 128) * 128 + -(-rlen // 128) * 128 != len(raw):
        return None
    return dict(name=raw[2:2 + nlen], type=raw[65:69], creator=raw[69:73],
                dlen=dlen, rlen=rlen)


def extra_fields(ex):
    """(id, size, data) for every field in an extra-field record."""
    out, q = [], 0
    while q + 4 <= len(ex):
        hid, hsz = struct.unpack("<HH", ex[q:q + 4])
        if q + 4 + hsz > len(ex):
            break
        out.append((hid, hsz, ex[q + 4:q + 4 + hsz]))
        q += 4 + hsz
    return out


def walk(d):
    """Every central-directory entry of the zip at the END of `d`.

    A ZipIt SEA puts a code stub in front, so the archive is addressed
    from the record it declares and never from offset 0."""
    e = d.rfind(b"PK\x05\x06")
    if e < 0:
        return None
    nent = struct.unpack("<H", d[e + 10:e + 12])[0]
    p = struct.unpack("<I", d[e + 16:e + 20])[0]
    out = []
    for _ in range(nent):
        if d[p:p + 4] != b"PK\x01\x02":
            return None
        method = struct.unpack("<H", d[p + 10:p + 12])[0]
        csize, usize = struct.unpack("<II", d[p + 20:p + 28])
        nlen, elen, clen = struct.unpack("<HHH", d[p + 28:p + 34])
        lho = struct.unpack("<I", d[p + 42:p + 46])[0]
        name = d[p + 46:p + 46 + nlen]
        cex = extra_fields(d[p + 46 + nlen:p + 46 + nlen + elen])
        p += 46 + nlen + elen + clen
        lex, raw = [], None
        if d[lho:lho + 4] == b"PK\x03\x04":
            lnlen, lelen = struct.unpack("<HH", d[lho + 26:lho + 30])
            lex = extra_fields(d[lho + 30 + lnlen:lho + 30 + lnlen + lelen])
            at = lho + 30 + lnlen + lelen
            body = d[at:at + csize]
            if method == 0:
                raw = body
            elif method == 8:
                try:
                    raw = zlib.decompressobj(-15).decompress(body)
                except zlib.error:
                    raw = None
        out.append(dict(name=name, method=method, usize=usize, cex=cex,
                        lex=lex, raw=raw, mb=is_macbinary(raw)))
    return out


def zipit_field(ent):
    """The entry's ZipIt field, off the CENTRAL directory."""
    for hid, hsz, dat in ent["cex"]:
        if hid in ZIPIT_IDS:
            return hid, hsz, dat
    return None, None, None


def long_field_name(ent):
    """The 'full Macintosh filename' a 0x2605 field carries, or None."""
    hid, hsz, dat = zipit_field(ent)
    if hid != 0x2605 or len(dat) < 5:
        return None
    fnlen = dat[4]
    if hsz != 4 + 1 + fnlen + 8:
        return None
    return dat[5:5 + fnlen]


def check_fields(name, ents):
    """The format, read independently of the engine."""
    bad = 0
    tally = {0x2605: 0, 0x2705: 0, 0x2805: 0}
    macbin = 0
    for ent in ents:
        isdir = ent["name"].endswith(b"/")
        hid, hsz, dat = zipit_field(ent)
        if hid is None:
            print("zipit: %s: %r carries no ZipIt field" % (name, ent["name"]))
            bad += 1
            continue
        tally[hid] += 1
        if ent["cex"] != ent["lex"]:
            print("zipit: %s: %r central extra != local extra"
                  % (name, ent["name"]))
            bad += 1
        if len(dat) < 4 or struct.unpack(">I", dat[:4])[0] != ZPIT:
            print("zipit: %s: %r 0x%04x has no 'ZPIT' signature"
                  % (name, ent["name"], hid))
            bad += 1
            continue
        if hid == 0x2805:
            # 'ZPIT', then frFlags and the view word, both of which
            # "MAY be omitted" (APPNOTE.TXT 4.6.6).
            if hsz not in (4, 6, 8):
                print("zipit: %s: %r 0x2805 is %d bytes"
                      % (name, ent["name"], hsz))
                bad += 1
        elif hid == 0x2705:
            # 'ZPIT', type, creator, then fdFlags and a reserved word,
            # both of which may be omitted (APPNOTE.TXT 4.6.5).
            if hsz not in (12, 14, 16):
                print("zipit: %s: %r 0x2705 is %d bytes"
                      % (name, ent["name"], hsz))
                bad += 1
            if ent["mb"] is not None:
                print("zipit: %s: %r is MacBinary and carries 0x2705, "
                      "not 0x2605" % (name, ent["name"]))
                bad += 1
        else:                                   # 0x2605, the long field
            fnlen = dat[4]
            if hsz != 4 + 1 + fnlen + 8:
                print("zipit: %s: %r 0x2605 is %d bytes, FnLen %d wants %d"
                      % (name, ent["name"], hsz, fnlen, 4 + 1 + fnlen + 8))
                bad += 1
                continue
            ftype = dat[5 + fnlen:9 + fnlen]
            fcreator = dat[9 + fnlen:13 + fnlen]
            if isdir:
                # ZipIt 1.x writes the LONG field on directories, where
                # APPNOTE.TXT assigns 0x2805 — so its claim that the
                # data is MacBinary is false for these, and the engine
                # survives by probing the bytes rather than trusting
                # the flag. What it must not carry is Finder info a
                # folder has none of.
                if ftype != b"\0\0\0\0" or fcreator != b"\0\0\0\0":
                    print("zipit: %s: %r 0x2605 on a directory states %r/%r"
                          % (name, ent["name"], ftype, fcreator))
                    bad += 1
                continue
            if ent["raw"] is None:
                continue        # method out of scope; UNGRADED says so
            if ent["mb"] is None:
                print("zipit: %s: %r carries 0x2605 and is NOT MacBinary"
                      % (name, ent["name"]))
                bad += 1
                continue
            macbin += 1
            if (ftype, fcreator) != (ent["mb"]["type"], ent["mb"]["creator"]):
                print("zipit: %s: %r 0x2605 says %r/%r, MacBinary header "
                      "%r/%r" % (name, ent["name"], ftype, fcreator,
                                 ent["mb"]["type"], ent["mb"]["creator"]))
                bad += 1
    want = EXPECT.get(name)
    if want:
        got = (len(ents), tally[0x2605], tally[0x2705], tally[0x2805], macbin)
        if got != want:
            print("zipit: %s: tallies %s, expected %s (entries, 0x2605, "
                  "0x2705, 0x2805, MacBinary)" % (name, got, want))
            bad += 1
    return bad, tally, macbin


def alias_of(ents, ourname):
    """The name `unar` uses for the entry this engine calls `ourname`,
    where the two differ, or None.

    XADMaster renames a MacBinary entry to the name inside its
    MacBinary header; this engine keeps the name the zip records. The
    tolerance is not "ours is right": it holds only while ZipIt's OWN
    0x2605 FileName — APPNOTE.TXT 4.6.4's "full Macintosh filename" —
    is one of the two, which is what makes it able to fail."""
    for ent in ents:
        if ent["name"].rstrip(b"/").decode("mac_roman") != ourname:
            continue
        fname = long_field_name(ent)
        if fname is None:
            return None
        leaf = ent["name"].rstrip(b"/").split(b"/")[-1]
        folder = ent["name"].rstrip(b"/")[:-len(leaf)]
        if ent["mb"] is not None:
            # unar takes the MacBinary name; ours is the zip's, and the
            # field must back ours.
            if fname != leaf:
                return None
            return (folder + ent["mb"]["name"]).decode("mac_roman")
        # No reachable payload: unar takes the field's name, which must
        # therefore BE the field's name and not the zip's.
        if fname == leaf:
            return None
        return (folder + fname).decode("mac_roman")
    return None


def pair_up(ents, ours, theirs):
    """our name -> the name `unar` used for the same entry, or None."""
    out = {}
    for n in ours:
        if n in theirs:
            out[n] = n
            continue
        a = alias_of(ents, n)
        out[n] = a if a is not None and a in theirs else None
    return out


def ours_list(exe, path, force):
    """`l --finder`, parsed. Type, creator and flags come out as hex so
    a four-character code holding a space cannot move the name column
    (TESTING.md, *The Finder metadata...*)."""
    cmd = [exe, "l", "--finder"] + (["-f", "Zip"] if force else []) + [path]
    r = subprocess.run(cmd, capture_output=True, timeout=900)
    if r.returncode != 0:
        return None, r.stderr.decode("utf-8", "replace").strip()
    rows = {}
    for ln in r.stdout.decode("utf-8", "replace").splitlines():
        if ln.startswith("comment:"):      # the archive's own, printed once
            continue
        parts = ln.split(None, 5)
        if len(parts) < 6 or parts[0] not in ("d", "f", "l"):
            return None, "unparsable row: %r" % ln
        kind, dfork, rfork, codes, flags, nm = parts
        if "/" not in codes:
            return None, "unparsable row: %r" % ln
        typ, creator = codes.split("/", 1)
        rows[nm] = dict(kind=kind,
                        df=None if dfork == "-" else int(dfork),
                        rf=None if rfork == "-" else int(rfork),
                        type=int(typ, 16), creator=int(creator, 16),
                        flags=int(flags, 16))
    return rows, None


def theirs_list(path):
    """`lsar -json`, folded to one row per entry. A MacBinary entry is
    two rows there — data fork and resource fork — under one name."""
    r = subprocess.run(["lsar", "-json", path], capture_output=True,
                       timeout=900)
    if r.returncode != 0:
        return None
    try:
        j = json.loads(r.stdout.decode("utf-8", "replace"))
    except ValueError:
        return None
    out = {}
    for e in j.get("lsarContents", []):
        n = e["XADFileName"]
        d = out.setdefault(n, dict(df=0, rf=0, type=None, creator=None,
                                   flags=None,
                                   isdir=bool(e.get("XADIsDirectory"))))
        if e.get("XADIsResourceFork"):
            d["rf"] = e.get("XADFileSize", 0)
        elif not e.get("XADIsDirectory"):
            d["df"] = e.get("XADFileSize", 0)
        for key, fld in (("XADFileType", "type"),
                         ("XADFileCreator", "creator"),
                         ("XADFinderFlags", "flags")):
            if key in e and d[fld] is None:
                d[fld] = e[key] & 0xFFFFFFFF
    return out


def grade_list(exe, name, path, ents, force, refused):
    ours, err = ours_list(exe, path, force)
    if ours is None:
        print("zipit: %s: `l` FAILED (%s)" % (name, err))
        return 1, 0, 0
    theirs = theirs_list(path)
    if theirs is None:
        print("zipit: %s: lsar could not read it" % name)
        return 1, 0, 0
    bad = 0
    pair = pair_up(ents, ours, theirs)
    aliased = sum(1 for n, t in pair.items() if t is not None and t != n)
    for n in sorted(theirs):
        if n not in pair.values():
            print("zipit: %s: %r in lsar only" % (name, n))
            bad += 1
    for n in sorted(ours):
        o = ours[n]
        t = theirs.get(pair[n]) if pair[n] else None
        if t is None:
            print("zipit: %s: %r in ours only" % (name, n))
            bad += 1
            continue
        if o["kind"] == "d" and not t["isdir"]:
            print("zipit: %s: %r is a folder here, a file to lsar" % (name, n))
            bad += 1
        if o["kind"] != "d" and n not in refused:
            for fld in ("df", "rf"):
                if o[fld] != t[fld]:
                    print("zipit: %s: %r %s fork %s against lsar's %s"
                          % (name, n, fld, o[fld], t[fld]))
                    bad += 1
            for fld, wide in (("type", 8), ("creator", 8), ("flags", 4)):
                want = t[fld] if t[fld] is not None else 0
                if o[fld] != want:
                    print("zipit: %s: %r %s 0x%0*x against lsar's 0x%0*x"
                          % (name, n, fld, wide, o[fld], wide, want))
                    bad += 1
    return bad, len(ours), aliased


def collect(root):
    """name -> [data fork, resource fork]. `unar -k hidden` writes an
    AppleDouble `._NAME`; this engine writes the fork raw."""
    out = {}
    for dirpath, _, files in os.walk(root):
        for f in sorted(files):
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            blob = open(p, "rb").read()
            if f.startswith("._"):
                key = rel[:-len(f)] + f[2:]
                rsrc = parse_appledouble(p)[0]
                out.setdefault(key, [b"", b""])[1] = \
                    blob if rsrc is None else rsrc
            elif not f.endswith(".comment.txt"):
                out.setdefault(rel, [b"", b""])[0] = blob
    return out


def grade_extract(exe, name, path, ents, force, refused):
    work = tempfile.mkdtemp(prefix="zipit-")
    try:
        a, b = os.path.join(work, "unar"), os.path.join(work, "ours")
        os.makedirs(a)
        os.makedirs(b)
        subprocess.run(["unar", "-nr", "-D", "-f", "-q", "-k", "hidden",
                        "-e", "macintosh", "-o", a, path],
                       capture_output=True, timeout=1800)
        cmd = [exe, "x", "--forks", "hidden"] + \
              (["-f", "Zip"] if force else []) + ["-o", b, path]
        r = subprocess.run(cmd, capture_output=True, timeout=1800)
        if r.returncode != 0 and not refused:
            print("zipit: %s: `x` FAILED (%s)"
                  % (name, r.stderr.decode("utf-8", "replace").strip()))
            return 1, 0
        ta, tb = collect(a), collect(b)
        bad = forks = 0
        pair = pair_up(ents, tb, ta)
        for k in sorted(tb):
            want = ta.get(pair[k]) if pair[k] else None
            if want is None:
                print("zipit: %s: %r extracted here and not by unar"
                      % (name, k))
                bad += 1
                continue
            for i, which in ((0, "data"), (1, "rsrc")):
                if want[i] != tb[k][i]:
                    print("zipit: %s: %r %s fork DIFFERS (%d against unar's "
                          "%d)" % (name, k, which, len(tb[k][i]),
                                   len(want[i])))
                    bad += 1
                elif want[i]:
                    forks += 1
        return bad, forks
    finally:
        shutil.rmtree(work, ignore_errors=True)


def refused_names(ents):
    """The entries this build declines by method, which no fork
    comparison can reach. Method 0 and 8 are the two it reads."""
    return set(e["name"].rstrip(b"/").decode("mac_roman")
               for e in ents if e["method"] not in (0, 8))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--macextract", default="build/macextract")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    paths = [os.path.join(SPECIMENS, n) for n in sorted(EXPECT)]
    have = [p for p in paths if os.path.exists(p)]
    if not have:
        print("zipit: no specimens in %s, skipping "
              "(tools/fetch_specimens.py --only zipit)" % SPECIMENS)
        return 0
    for p in paths:
        if p not in have:
            print("zipit: %s absent, not graded" % os.path.basename(p))
    for tool in ("unar", "lsar"):
        if shutil.which(tool) is None:
            print("zipit: %s not installed, skipping" % tool)
            return 0

    bad = entries = macbin = forks = unaided = aliased = skipped = 0
    tally = {0x2605: 0, 0x2705: 0, 0x2805: 0}
    for p in have:
        name = os.path.basename(p)
        raw = open(p, "rb").read()
        d = macbinary_datafork(raw)
        ents = walk(d)
        if ents is None:
            print("zipit: %s: no zip behind the self-extractor" % name)
            bad += 1
            continue
        sfx = d[:4] != b"PK\x03\x04"
        # Where the file as downloaded is MacBinary, the suite hands
        # over the data fork — which is what `unc_macbinary` hands the
        # walker for a `.bin` fixture. Where it is not, the engine gets
        # the bytes as they came, and must sniff them itself.
        subject, tmp = p, None
        if d is not raw:
            tmp = tempfile.NamedTemporaryFile(prefix="zipit-", suffix=".zip",
                                              delete=False)
            tmp.write(d)
            tmp.close()
            subject = tmp.name
        try:
            if not sfx:
                r = subprocess.run([a.macextract, "sniff", subject],
                                   capture_output=True, timeout=300)
                got = r.stdout.decode("utf-8", "replace").strip()
                if got != "Zip":
                    print("zipit: %s: sniffed as %r, not Zip" % (name, got))
                    bad += 1
                else:
                    unaided += 1
            refused = refused_names(ents)
            want = UNGRADED.get(name, (0, None))[0]
            if len(refused) != want:
                print("zipit: %s: %d entr(y/ies) refused by method, "
                      "declared %d" % (name, len(refused), want))
                bad += 1
            skipped += len(refused)
            n, t, mb = check_fields(name, ents)
            bad += n
            for k in tally:
                tally[k] += t[k]
            macbin += mb
            n, cnt, al = grade_list(a.macextract, name, subject, ents, sfx,
                                    refused)
            bad += n
            entries += cnt
            aliased += al
            n, f = grade_extract(a.macextract, name, subject, ents, sfx,
                                 refused)
            bad += n
            forks += f
        finally:
            if tmp:
                os.unlink(tmp.name)
        if a.verbose:
            print("zipit: %s: %d entries, %s" % (name, len(ents),
                  "self-extracting, format forced" if sfx else "sniffed as Zip"))

    for k in sorted(UNGRADED):
        if os.path.join(SPECIMENS, k) in have:
            print("  DECLARED UNGRADED: %s — %d %s"
                  % (k, UNGRADED[k][0], UNGRADED[k][1]))
    if aliased:
        print("  %d entr(y/ies) named differently by unar, each adjudicated "
              "by ZipIt's own 0x2605 FileName" % aliased)
    print("zipit: %d archive(s), %d sniffed unaided, %d entries, %d forks "
          "byte-identical to unar; fields 0x2605 x%d (%d MacBinary payloads), "
          "0x2705 x%d, 0x2805 x%d; %d entr(y/ies) declined by method; "
          "%d failure(s)"
          % (len(have), unaided, entries, forks, tally[0x2605], macbin,
             tally[0x2705], tally[0x2805], skipped, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

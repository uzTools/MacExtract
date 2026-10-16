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

A ZipIt SEA is a code stub with the zip behind it. The five of them
needed `-f Zip` until 2026-10-05; since then the sniffer finds the
archive behind the stub from the end-of-central-directory record it was
already scanning for, so nothing here forces a format and all nine are
sniffed unaided — which this suite asserts rather than assumes. Four
arrived MacBinary-wrapped, and those are also extracted WHOLE, the way
a user hands one over, and compared with their data fork's extraction.
`MrTs_Paint_Folder.zip` and `NPWritersKit.zip` are corpus fixtures as
well, so `run_diff.py` grades a real ZipIt archive of each shape with
no oracle at run time.

Six things are checked, and the tallies in EXPECT are asserted so that
a download that changed, or a parse that stopped parsing, fails here
instead of going quiet:

  1. an independent Python read of every ZipIt field — central copy
     against local copy, each size against what 'ZPIT' plus the
     declared members needs;
  2. `0x2605` against the bytes: the entry is decoded and its first
     128 bytes probed as MacBinary, in both directions;
  3. `l --finder` against `lsar`: name, type, creator, Finder flags
     and both fork lengths;
  4. `x` against `unar`: every data and resource fork byte for byte;
  5. and for the four that arrived wrapped, `x` on the whole file
     against `x` on its data fork — the auto-unwrap route;
  6. every `0x2605` FileName against the name this engine LISTS, over
     these nine and `fixtures/*.zip` both. APPNOTE.TXT 4.6.4 calls the
     field the "full Macintosh filename" and `src/fmt_exo.c` has
     substituted it for the entry's leaf since 2026-10-07, so the
     assertion is that the substitution happened — on all 23 fields in
     reach, divergent or not. **The criterion inverted that day**: it
     used to be "a divergence on a decodable method is an alarm",
     which was a question about a gap and could not fire while
     Implode was out of scope. `selftest_coupling` proves the new one
     can fail, against a stub that answers with the zip's own names —
     this program's own behaviour the day before.

**What it cannot see.** The probe's own reasoning: these nine all
carry a well-formed record, so nothing here can fail on a corroboration
that stopped corroborating — `test_zip_behind_a_stub` in
tests/unit_formats.c bends each of the five in turn. It compares no
fork of an entry whose method is out of v1 scope, and UNGRADED below
names every one with the reason — **it is EMPTY since 2026-10-07**, when
method 6 landed and the three entries it held became graded like any
other. And it adjudicates no date: `lsar`
reports zip's own MS-DOS stamp where a `0x2605` entry's MacBinary
header carries two Macintosh ones, so the two are not the same field.
Check 6 reads these nine and `fixtures/*.zip` and nothing else, so a
ZipIt archive arriving in the corpus inside a `.hqx` or a `.sea`
carries fields it never sees; it prints what it swept. And it grades
the LEAF only, because the field is a leaf: an enclosing folder with no
entry and no field of its own keeps whatever the zip called it, which
is 1 of the 4 wrong name components in `zipit-Psycho_1.0b1.zip` and is
not a defect this suite can see.

Nothing here fails when the specimens are absent — it prints what it
skipped and returns 0, so a fresh clone stays green.
"""
import argparse
import contextlib
import glob
import io
import json
import os
import re
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
# **EMPTY as of 2026-10-07**, and kept because it was not. Its one row
# was `zipit-Psycho_1.0b1.zip` — 3 of 3 entries at Zip method 6
# (Implode), refused per entry, no fork compared and the MacBinary
# payload out of reach, so neither the type, the creator nor the Finder
# flags inside it could be graded either. Method 6 is implemented since
# that day, so all three entries are now graded like any other: six
# forks byte-identical to `unar`, and the three names ZipIt's own
# `0x2605` field states (DECISIONS.md 2026-10-07, *the method that was
# out for a premise with no halves left*).
UNGRADED = {}


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
    MacBinary HEADER; this engine uses ZipIt's `0x2605` FileName, which
    APPNOTE.TXT 4.6.4 calls the "full Macintosh filename". The
    tolerance is not "ours is right": it holds only while the field is
    one of the two names in play, which is what makes it able to fail.

    **One of its two branches went on 2026-10-07, and it went because it
    had become unfireable.** It read "no reachable payload: unar takes
    the field's name, which must therefore BE the field's name" — true
    while this engine extracted under the ZIP's name, and vacuous now
    that it extracts under the field's: where the harness cannot reach
    the payload, our name and `unar`'s are the same string and
    `pair_up` never asks. The MacBinary-header case below is the only
    way the two can still differ, and it is 1 of the 23 fields in reach
    (FORMATS.md, *ZipIt's own archives*)."""
    for ent in ents:
        fname = long_field_name(ent)
        if not fname:
            continue
        raw = ent["name"].rstrip(b"/")
        cut = raw.rfind(b"/")
        folder = raw[:cut + 1] if cut >= 0 else b""
        if (folder + fname.replace(b"/", b":")).decode("mac_roman") != ourname:
            continue
        if ent["mb"] is None:
            return None
        return (folder + ent["mb"]["name"]).decode("mac_roman")
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


def ours_list(exe, path):
    """`l --finder`, parsed. Type, creator and flags come out as hex so
    a four-character code holding a space cannot move the name column
    (TESTING.md, *The Finder metadata...*).

    Nothing is forced: since 2026-10-05 a self-extracting archive is
    sniffed like any other, so the format is the sniffer's answer and
    this suite grades it."""
    cmd = [exe, "l", "--finder", path]
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


def grade_list(exe, name, path, ents, refused):
    ours, err = ours_list(exe, path)
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


def grade_extract(exe, name, path, ents, refused):
    work = tempfile.mkdtemp(prefix="zipit-")
    try:
        a, b = os.path.join(work, "unar"), os.path.join(work, "ours")
        os.makedirs(a)
        os.makedirs(b)
        subprocess.run(["unar", "-nr", "-D", "-f", "-q", "-k", "hidden",
                        "-e", "macintosh", "-o", a, path],
                       capture_output=True, timeout=1800)
        cmd = [exe, "x", "--forks", "hidden", "-o", b, path]
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


def grade_wrapped(exe, name, raw_path, fork_path, refused):
    """The whole file as downloaded, against its data fork alone.

    Four of the nine arrived MacBinary-wrapped, which is how a Macintosh
    file crosses a network. The route a user takes is to hand that file
    over whole: the engine takes the envelope off and then has to
    recognise what is underneath — a stub with a zip behind it. Nothing
    else here walks that path, and until 2026-10-05 it ended in "format
    not recognized" after the envelope came off (DECISIONS.md).

    The data-fork extraction this compares against is the one
    grade_extract has already held against `unar`.

    **Two steps since 2026-10-16**: the envelope leaves the self-extractor,
    an application, where a chain of layers stops (DECISIONS.md
    2026-10-16, *the installer that was a layer*), so the whole file must
    give that one file, and opening it must give the data fork's
    extraction. An envelope whose MacBinary records no type still goes
    straight through."""
    work = tempfile.mkdtemp(prefix="zipitw-")
    try:
        a, b = os.path.join(work, "whole"), os.path.join(work, "fork")
        os.makedirs(a)
        os.makedirs(b)
        whole = raw_path
        # The envelope's own listing says whether what it holds is an
        # application; one whose MacBinary records no type is not, and
        # the chain goes on through it.
        lst = subprocess.run([exe, "l", raw_path], capture_output=True,
                             timeout=600).stdout.decode("mac_roman")
        if re.search(r"\sAPPL/", lst):
            app = os.path.join(work, "app")
            os.makedirs(app)
            r = subprocess.run([exe, "x", "--forks", "hidden", "-o", app,
                                raw_path], capture_output=True, timeout=1800)
            left = [f for f in os.listdir(app) if not f.startswith("._")]
            if r.returncode != 0 or len(left) != 1:
                print("zipit: %s: the envelope did not stop at the "
                      "application (%r)" % (name, sorted(os.listdir(app))))
                return 1
            whole = os.path.join(app, left[0])
        for out, subj in ((a, whole), (b, fork_path)):
            r = subprocess.run([exe, "x", "--forks", "hidden", "-o", out,
                                subj], capture_output=True, timeout=1800)
            if r.returncode != 0 and not refused:
                print("zipit: %s: `x` FAILED on %s (%s)"
                      % (name, os.path.basename(subj),
                         r.stderr.decode("utf-8", "replace").strip()))
                return 1
        ta, tb = collect(a), collect(b)
        if ta != tb:
            only_a = sorted(set(ta) - set(tb))
            only_b = sorted(set(tb) - set(ta))
            print("zipit: %s: unwrapping the whole file does not give the "
                  "data fork's extraction (%d vs %d items%s%s)"
                  % (name, len(ta), len(tb),
                     "; only whole: %r" % only_a if only_a else "",
                     "; only fork: %r" % only_b if only_b else ""))
            return 1
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def refused_names(ents):
    """The entries this build declines by method, which no fork
    comparison can reach. Stored, Implode and deflate are the three it
    reads from the header — **6 joined on 2026-10-07**, which emptied
    this set for `zipit-Psycho_1.0b1.zip` and with it the only UNGRADED
    declaration this suite had. Method 99 (WinZip AES) stays refused
    here even though the engine reads it, because a fork comparison
    needs a password as well as a method and nothing here supplies
    one."""
    return set(e["name"].rstrip(b"/").decode("mac_roman")
               for e in ents if e["method"] not in (0, 6, 8))


# What a `0x2605` entry must come out as, now that the field is read.
#
# **The criterion CHANGED MEANING on 2026-10-07.** Until that day this
# gate asked a question about a GAP: does a divergent FileName ever sit
# on an entry this build can decode? — because the engine extracted
# under the zip's own name, and the day the two stopped agreeing on
# something reachable was the day a file would come out misnamed. It
# returned 0 on every real run, because all 3 divergent fields on this
# disk are on Implode entries and Implode was out of scope.
#
# Both halves of that are gone: `src/fmt_exo.c` reads the FileName and
# substitutes it for the leaf, and it decodes method 6. So the question
# is now about an INVARIANT, and it is stronger: every `0x2605` field,
# divergent or not, decodable or not, must be the leaf this engine
# LISTS the entry under. A listing needs no decoder, so the gate no
# longer has a notion of a reachable method at all — `DECODED_METHODS`
# went with the old criterion.
#
# `selftest_coupling` proves it can fail, and proves it against the
# engine as it WAS: a stub that answers with the zip's own names, which
# is exactly what this program printed the day before.


def expected_names(ents):
    """{the zip's own path: (what it must list as, the field's leaf)}
    for every entry carrying a `0x2605` FileName.

    APPNOTE.TXT 4.6.4 calls the field the "full Macintosh filename", and
    it is a LEAF: the enclosing folders keep whatever the zip called
    them, which is the same rule `src/fmt_exo.c` applies and the reason
    `PSYCHO!/` stays upper-cased in the one archive where this fires."""
    out = {}
    for e in ents:
        fname = long_field_name(e)
        if fname is None or not fname:
            continue
        raw = e["name"].rstrip(b"/")
        cut = raw.rfind(b"/")
        want = (raw[:cut + 1] if cut >= 0 else b"") + fname.replace(b"/", b":")
        out[raw.decode("mac_roman")] = (want.decode("mac_roman"),
                                        fname.decode("mac_roman"))
    return out


def diverging_names(ents):
    """Every `0x2605` entry whose FileName is NOT the zip's own leaf.
    Reported rather than asserted: a divergence is the interesting case
    and the count is what moves when a specimen changes. Returns (the
    zip's name, the field's leaf, method) for each."""
    out = []
    for e in ents:
        fname = long_field_name(e)
        if not fname:
            continue
        leaf = e["name"].rstrip(b"/").split(b"/")[-1]
        if fname != leaf:
            out.append((e["name"].rstrip(b"/").decode("mac_roman"),
                        fname.decode("mac_roman"), e["method"]))
    return out


def grade_name_coupling(exe, paths):
    """Every `0x2605` FileName against the name this engine lists.

    One `l` per archive that carries a field, and none at all for one
    that does not; the expectation comes off the bytes, so the only
    thing being trusted here is the zip itself."""
    arch = fields = diverged = graded = bad = 0
    for p in paths:
        try:
            with open(p, "rb") as fh:
                raw = fh.read()
        except OSError:
            continue
        d = macbinary_datafork(raw)
        ents = walk(d)
        if ents is None:
            continue
        arch += 1
        want = expected_names(ents)
        fields += len(want)
        div = diverging_names(ents)
        diverged += len(div)
        if not want:
            continue
        # A specimen that arrived MacBinary-wrapped is listed through its
        # DATA FORK, the way main() grades one: `l` on the envelope lists
        # the envelope — one entry, the `.sea` itself — which is correct
        # and is not what this is asking about.
        subject, tmp = p, None
        if d is not raw:
            tmp = tempfile.NamedTemporaryFile(prefix="zipit-names-",
                                              suffix=".zip", delete=False)
            tmp.write(d)
            tmp.close()
            subject = tmp.name
        try:
            rows, err = ours_list(exe, subject)
        finally:
            if tmp:
                os.unlink(tmp.name)
        if rows is None:
            print("zipit: %s: `l` FAILED while grading 0x2605 names (%s)"
                  % (os.path.basename(p), err))
            bad += 1
            continue
        for zipname, (wantname, leaf) in sorted(want.items()):
            graded += 1
            if wantname in rows:
                continue
            bad += 1
            print("zipit: %s: 0x2605 FileName %r makes the entry %r, and "
                  "this build lists %s — the field is the name the "
                  "Macintosh file HAD (APPNOTE.TXT 4.6.4)"
                  % (os.path.basename(p), leaf, wantname,
                     "%r" % zipname if zipname in rows
                     else "neither that nor %r" % zipname))
    print("zipit: %d archive(s) swept for 0x2605 names, %d field(s), "
          "%d divergent, %d name(s) held against the listing"
          % (arch, fields, diverged, graded))
    return bad


def _coupling_case(method, leaf, fname, extra_first=b""):
    """A one-entry zip carrying a `0x2605` FileName, for the self-test.

    The field is APPNOTE.TXT 4.6.4's layout and nothing more — '"ZPIT"
    beLong, FnLen Byte, FileName variable, FileType Byte[4], Creator
    Byte[4]' — which is the same reading `long_field_name` above and
    `src/fmt_exo.c` both encode. The archive is written by
    tools/synth_crypt.py's writer rather than a second one here."""
    from synth_crypt import _zip        # imported here: only this needs it
    fn = fname.encode("mac_roman")
    f2605 = (struct.pack("<HH", 0x2605, 4 + 1 + len(fn) + 8) + b"ZPIT" +
             bytes([len(fn)]) + fn + b"TEXTttxt")
    body = b"not read by the gate\n"
    blob, _ = _zip([(leaf, method, zlib.crc32(body) & 0xFFFFFFFF, len(body),
                     extra_first + f2605, body)])
    return blob


OLD_ENGINE_STUB = """#!/usr/bin/env python3
# The engine as it was before 2026-10-07: a `l --finder` listing that
# answers with the ZIP's own leaf, which is what this program printed
# for a 0x2605 entry until the FileName was read. Generated by
# run_zipit.py's selftest as a NEGATIVE CONTROL: the name gate has to
# fail on it, or the gate is not grading the substitution.
import sys, zipfile
for n in zipfile.ZipFile(sys.argv[-1]).namelist():
    print("f 21 0 54455854/74747874 0000 %s" % n.rstrip("/"))
"""


def selftest_coupling(exe):
    """Prove the name gate can FAIL, and prove it against the engine as
    it WAS.

    Three one-entry zips say what the gate discriminates on — the two
    names, and a field whose declared length does not fit the record it
    sits in — and each is run TWICE: once against the real binary,
    which must come out clean, and once against a stub that answers
    with the zip's own leaf the way this program did the day before the
    substitution landed, which must come out dirty. A gate that cannot
    tell those two apart is grading nothing.

    Returns the number of cases that came out wrong."""
    aes = struct.pack("<HHH2sBH", 0x9901, 7, 2, b"AE", 3, 8)
    cases = [
        # method, zip's leaf, the field's FileName, extra before 0x2605,
        # fields graded, divergences, does the OLD engine fail it,
        # what it pins
        (0,  "README", "READ ME", b"", 1, 1, True,
         "stored: the field is the name, and the zip's own is not"),
        (6,  "README", "READ ME", b"", 1, 1, True,
         "Implode, decoded since 2026-10-07 — the live corpus shape"),
        (0,  "README", "README",  b"", 1, 0, False,
         "a field that agrees: graded, and the old engine passes it too, "
         "which is why an agreeing field proves nothing on its own"),
        (99, "README", "READ ME", aes, 1, 1, True,
         "WinZip AES, real method 8 in its 0x9901 field"),
        (8,  "READ ME", "READ ME", b"", 1, 0,  False,
         "a name with a space on both sides, so the gate is not merely "
         "preferring whichever of the two has one"),
    ]
    bad = 0
    d = tempfile.mkdtemp(prefix="zipit-selftest-")
    try:
        stub = os.path.join(d, "old_engine.py")
        with open(stub, "w") as fh:
            fh.write(OLD_ENGINE_STUB)
        os.chmod(stub, 0o755)
        for method, leaf, fname, pre, wfields, wdiv, oldfails, why in cases:
            blob = _coupling_case(method, leaf, fname, pre)
            p = os.path.join(d, "m%d-%s.zip"
                             % (method, fname.replace(" ", "_")))
            with open(p, "wb") as fh:
                fh.write(blob)
            ents = walk(blob)
            gdiv = len(diverging_names(ents)) if ents else -1
            gfields = len(expected_names(ents)) if ents else -1
            # The gate prints its own sweep line; one of those per case
            # ahead of the real one would read as the real one.
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                real = grade_name_coupling(exe, [p])
                old = grade_name_coupling(stub, [p])
            got = (gfields, gdiv, real, old > 0)
            wanted = (wfields, wdiv, 0, oldfails)
            if got != wanted:
                print("zipit: selftest: method %d, %r vs %r: got %r, "
                      "wanted %r (fields, divergent, this build's "
                      "failures, does the pre-2026-10-07 stub fail) — %s"
                      % (method, leaf, fname, got, wanted, why))
                print(said.getvalue(), end="")
                bad += 1
    finally:
        shutil.rmtree(d, ignore_errors=True)
    if not bad:
        print("zipit: selftest ok (%d built cases; the gate fails the "
              "pre-substitution stub on %d of them and this build on none)"
              % (len(cases), sum(1 for c in cases if c[6])))
    return bad


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--macextract", default="build/macextract")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    paths = [os.path.join(SPECIMENS, n) for n in sorted(EXPECT)]
    have = [p for p in paths if os.path.exists(p)]

    # Never trust a pass this cannot fail: the gate below has returned 0
    # every run since it was written, so it proves itself first, on
    # bytes built here and no specimen (CLAUDE.md, *Traps*).
    nbad = selftest_coupling(a.macextract)

    # The name coupling wants neither oracle, so it is swept first and
    # over the corpus zips as well — on a fresh clone it has nothing to
    # read and says so with a count of 0.
    nbad += grade_name_coupling(
        a.macextract,
        have + sorted(glob.glob(os.path.join(REPO, "fixtures", "*.zip"))))

    if not have:
        print("zipit: no specimens in %s, skipping "
              "(tools/fetch_specimens.py --only zipit)" % SPECIMENS)
        return 1 if nbad else 0
    for p in paths:
        if p not in have:
            print("zipit: %s absent, not graded" % os.path.basename(p))
    for tool in ("unar", "lsar"):
        if shutil.which(tool) is None:
            print("zipit: %s not installed, skipping" % tool)
            return 1 if nbad else 0

    bad = nbad
    entries = macbin = forks = unaided = aliased = skipped = 0
    wrapped = 0
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
            # Every one of the nine, self-extracting or not. This
            # assertion was `if not sfx` until 2026-10-05, when the
            # five SEAs stopped needing `-f Zip` (DECISIONS.md).
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
            n, cnt, al = grade_list(a.macextract, name, subject, ents,
                                    refused)
            bad += n
            entries += cnt
            aliased += al
            n, f = grade_extract(a.macextract, name, subject, ents,
                                 refused)
            bad += n
            forks += f
            if subject is not p:
                bad += grade_wrapped(a.macextract, name, p, subject, refused)
                wrapped += 1
        finally:
            if tmp:
                os.unlink(tmp.name)
        if a.verbose:
            print("zipit: %s: %d entries, %s, sniffed as Zip"
                  % (name, len(ents),
                     "self-extracting" if sfx else "a plain zip"))

    for k in sorted(UNGRADED):
        if os.path.join(SPECIMENS, k) in have:
            print("  DECLARED UNGRADED: %s — %d %s"
                  % (k, UNGRADED[k][0], UNGRADED[k][1]))
    if aliased:
        print("  %d entr(y/ies) named differently by unar, each adjudicated "
              "by ZipIt's own 0x2605 FileName" % aliased)
    print("zipit: %d archive(s), %d sniffed unaided, %d also extracted "
          "whole through their MacBinary envelope, %d entries, %d forks "
          "byte-identical to unar; fields 0x2605 x%d (%d MacBinary payloads), "
          "0x2705 x%d, 0x2805 x%d; %d entr(y/ies) declined by method; "
          "%d failure(s)"
          % (len(have), unaided, wrapped, entries, forks, tally[0x2605],
             macbin,
             tally[0x2705], tally[0x2805], skipped, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

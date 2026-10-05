#!/usr/bin/env python3
"""derive_ddc.py — DiskDoubler's three CONTAINERS, read from a
description this project measured, and graded against the oracle.

The coders have had a published description since 2026-09-20 and
`tools/derive_dd.py` reads them from it. The containers never have:
The Unarchiver's wiki lists `DiskDoublerSingleFormat`,
`DiskDoublerArchiveFormat1` and `DiskDoublerArchiveFormat2` by name and
then says "see XADDiskDoublerParser.m for now" — and those three pages
do not exist on that wiki at all (its index, `wikis.json`, has 40 pages
and none of them; checked 2026-09-22). So the description had to be
made here, the way Now Compress's was:

    docs/formats/diskdoubler-container.md

This reader is written from that document and from nothing else. What
it is FOR is the same thing `derive_dd.py` is for: a citation is a
claim, and this re-runs the reading that says the description is right.

    tools/derive_ddc.py [--grid] [--fixture NAME ...] [-v]

    (default)   read every DiskDoubler fixture's container and compare
                what it says with the oracle manifest: every entry's
                path, both fork lengths, and the type and creator
                wherever the oracle recorded them.
    --grid      re-derive the layout instead of assuming it — for each
                field, the set of offsets that agrees with the oracle
                across EVERY fixture. A field with one surviving offset
                is measured; a field with several is a field this
                corpus cannot pin, and the tool says which.

**What it cannot see**, and each of these is in the document too:

  - a single compressed file carries NO NAME. The name comes from the
    host's own file, so nothing here grades it;
  - the dates. No manifest records them, so this compares none. What
    pins them is `tools/vmac/ndd.py --dates`, which stamped two
    subjects with a 1990 creation and a 1995 modification and read the
    records back;
  - a field every fixture agrees on is a field this corpus cannot tell
    from a constant. `--grid` prints those as constants, with the
    value, rather than as facts about the format.

Not in `ci.sh`: it needs the fixtures, which are copyrighted and not
committed. It skips cleanly without them.
"""
import argparse
import collections
import glob
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXDIR = os.path.join(ROOT, "fixtures")
MANDIR = os.path.join(FIXDIR, "manifests")

DD_MAGIC = 0xABCD0054          # a compressed FILE's header
DDAR = b"DDAR"                 # DiskDoubler 3.x/4.x archive
DDA2 = b"DDA2"                 # DiskDoubler Pro archive


def u32(b, o):
    return struct.unpack(">I", b[o:o + 4])[0] if o + 4 <= len(b) else None


def u16(b, o):
    return struct.unpack(">H", b[o:o + 2])[0] if o + 2 <= len(b) else None


def fcc(v):
    return None if v is None else struct.pack(">I", v).decode("mac_roman")


def pstr(b, o, cap):
    """A Str63 at `o`: a length byte and that many bytes, capped."""
    n = b[o]
    if n > cap:
        n = cap
    return b[o + 1:o + 1 + n]


# --------------------------------------------------------------------
# The compressed FILE header — 84 bytes, magic included
#
# docs/formats/diskdoubler-container.md, "A compressed file". The same
# header appears three times: as a file of its own, and inside both
# archive containers wherever a record says one follows.
# --------------------------------------------------------------------

F_DATALEN, F_DATACOMP, F_RSRCLEN, F_RSRCCOMP = 4, 8, 12, 16
F_DATAMETH, F_RSRCMETH, F_INFO1 = 20, 21, 22
F_MTIME, F_CTIME, F_TYPE, F_CREATOR, F_FLAGS = 24, 28, 32, 36, 40
F_DATACRC, F_RSRCCRC, F_INFO2 = 48, 50, 52
F_DATADELTA, F_RSRCDELTA = 54, 56
F_SIZE = 84


def read_filehdr(b, at):
    if at + F_SIZE > len(b) or u32(b, at) != DD_MAGIC:
        return None
    return dict(
        data_size=u32(b, at + F_DATALEN), data_comp=u32(b, at + F_DATACOMP),
        rsrc_size=u32(b, at + F_RSRCLEN), rsrc_comp=u32(b, at + F_RSRCCOMP),
        data_method=b[at + F_DATAMETH] & 0x7F,
        rsrc_method=b[at + F_RSRCMETH] & 0x7F,
        type=fcc(u32(b, at + F_TYPE)), creator=fcc(u32(b, at + F_CREATOR)),
        flags=u16(b, at + F_FLAGS),
        mtime=u32(b, at + F_MTIME), ctime=u32(b, at + F_CTIME),
        data_delta=u16(b, at + F_DATADELTA),
        rsrc_delta=u16(b, at + F_RSRCDELTA),
        data_crc=u16(b, at + F_DATACRC), rsrc_crc=u16(b, at + F_RSRCCRC),
        info1=b[at + F_INFO1], info2=b[at + F_INFO2],
        payload=at + F_SIZE)


# --------------------------------------------------------------------
# 'DDAR' — DiskDoubler 3.x and 4.x
#
# docs/formats/diskdoubler-container.md, "DDAR". 78 bytes of archive
# header, then one 124-byte record per entry, each with its own 'DDAR'
# magic. The archive ends where the FILE ends: there is no end marker.
# --------------------------------------------------------------------

R_BODY = 78                    # where the first record is
R_NAME, R_ISDIR, R_ENDDIR = 8, 72, 73
R_SPAN, R_RSRCLEN = 74, 78     # +74 is the whole entry, not the data fork
R_CTIME, R_MTIME, R_TYPE, R_CREATOR, R_FLAGS = 82, 86, 90, 94, 98
R_DATACRC, R_RSRCCRC, R_HDRCRC = 118, 120, 122
R_SIZE = 124

R_FLAG_NOHDR = 0x20            # the forks follow raw, with no file header


def read_ddar(b):
    """Walk by the record's own +74, which is the ENTRY's whole span."""
    out, path, at = [], [], R_BODY
    while True:
        if at == len(b):
            return out                     # the archive ends where the FILE does
        if at + R_SIZE > len(b):
            raise ValueError("DDAR: %d bytes left over" % (len(b) - at))
        if b[at:at + 4] != DDAR:
            raise ValueError("DDAR: no record magic at %d" % at)
        name = pstr(b, at + R_NAME, 63)
        start = at + R_SIZE
        span = u32(b, at + R_SPAN)
        if b[at + R_ENDDIR]:
            path.pop()
            at = start
            continue
        if b[at + R_ISDIR]:
            out.append(dict(path=path + [name], is_dir=True, rec_at=at))
            path.append(name)
            at = start
            continue
        e = dict(path=path + [name], is_dir=False, rec_at=at)
        if u16(b, at + R_FLAGS) & R_FLAG_NOHDR:
            e.update(data_size=u32(b, at + R_SPAN),
                     rsrc_size=u32(b, at + R_RSRCLEN),
                     type=fcc(u32(b, at + R_TYPE)),
                     creator=fcc(u32(b, at + R_CREATOR)),
                     data_method=0, rsrc_method=0, stored=True)
        else:
            f = read_filehdr(b, start)
            if f is None:
                raise ValueError("DDAR: no file header at %d" % start)
            e.update(f)
            e["stored"] = False
            # What the entry holds is a compressed FILE, so its span is
            # that file's own length — its header, both forks, and the
            # byte-identical copy of the header a real DiskDoubler
            # writes at the end of one. Either shape, and nothing else.
            inner = F_SIZE + f["data_comp"] + f["rsrc_comp"]
            if span not in (inner, inner + F_SIZE):
                raise ValueError("DDAR: record at %d spans %d, its file is "
                                 "%d or %d" % (at, span, inner, inner + F_SIZE))
            e["trailer"] = (span == inner + F_SIZE)
        at = start + span
        out.append(e)


# --------------------------------------------------------------------
# 'DDA2' — DiskDoubler Pro
#
# docs/formats/diskdoubler-container.md, "DDA2". 62 bytes of archive
# header, then variable-length records that each state their own total
# size, ending at a record whose type word is 0xBBBB.
# --------------------------------------------------------------------

A_BODY = 62
A_TYPE, A_NAME = 4, 6
A_LEVEL, A_TOTAL = 38, 42
A_CTIME, A_MTIME = 54, 58          # folder records, and the stored shape
A_FILEHDR = 56                     # where a full file header follows
S_TYPE, S_CREATOR, S_FLAGS = 62, 66, 70
S_DATALEN, S_RSRCLEN, S_PAYLOAD = 78, 82, 90

A_END = 0xBBBB
A_DIR = 0x8000
A_STORED_MASK, A_STORED = 0xF000, 0x1000


def read_dda2(b):
    out, path, at = [], [], A_BODY
    lastlevel = 0
    while True:
        if at + 46 > len(b):
            if at <= len(b) and len(b) - at < 46:
                return out             # an archive that ends with no marker
            raise ValueError("DDA2: record at %d is past the end" % at)
        if b[at:at + 4] != DDA2:
            raise ValueError("DDA2: no record magic at %d" % at)
        etype = u16(b, at + A_TYPE)
        if etype == A_END:
            return out
        name = pstr(b, at + A_NAME, 31)
        level = u32(b, at + A_LEVEL) - 2
        total = u32(b, at + A_TOTAL)
        if total == 0:
            raise ValueError("DDA2: record at %d states no size" % at)
        if level < 0:                  # the archive's own bookkeeping
            at += total
            continue
        while lastlevel > level:
            path.pop()
            lastlevel -= 1
        lastlevel = level
        if etype & A_DIR:
            out.append(dict(path=path + [name], is_dir=True, rec_at=at))
            path.append(name)
            at += total
            continue
        e = dict(path=path + [name], is_dir=False, rec_at=at)
        if (etype & A_STORED_MASK) == A_STORED:
            e.update(data_size=u32(b, at + S_DATALEN),
                     rsrc_size=u32(b, at + S_RSRCLEN),
                     type=fcc(u32(b, at + S_TYPE)),
                     creator=fcc(u32(b, at + S_CREATOR)),
                     data_method=0, rsrc_method=0, stored=True)
        else:
            f = read_filehdr(b, at + A_FILEHDR)
            if f is None:
                raise ValueError("DDA2: no file header at %d" % (at + A_FILEHDR))
            e.update(f)
            e["stored"] = False
        out.append(e)
        at += total


def read_container(b, fixture):
    if b[:4] == DDAR:
        return "DDAR", read_ddar(b)
    if b[:4] == DDA2:
        return "DDA2", read_dda2(b)
    f = read_filehdr(b, 0)
    if f is None:
        return None, []
    # A compressed FILE states no name: it kept the host's, with ".dd"
    # on the end. Graded on everything BUT the name, which is the
    # host's question and not the container's.
    f = dict(f)
    f.update(path=[None], is_dir=False, stored=False)
    # A compressed file ends with a byte-identical copy of its own
    # 84-byte header — 63 of the corpus's 66, and the three without it
    # are this project's own synthetic specimens rather than files
    # DiskDoubler wrote. docs/formats/diskdoubler-container.md, "The
    # header is written twice".
    inner = F_SIZE + f["data_comp"] + f["rsrc_comp"]
    if len(b) == inner + F_SIZE and b[inner:inner + F_SIZE] == b[:F_SIZE]:
        f["trailer"] = True
    elif len(b) == inner:
        f["trailer"] = False
    else:
        raise ValueError("single: %d bytes, its forks say %d or %d"
                         % (len(b), inner, inner + F_SIZE))
    return "single", [f]


# --------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------

def fixtures(only):
    for mp in sorted(glob.glob(os.path.join(MANDIR, "*.json"))):
        man = json.load(open(mp))
        if "DiskDoubler" not in str(man.get("format", "")):
            continue
        if only and man["fixture"] not in only:
            continue
        path = os.path.join(FIXDIR, man["fixture"])
        if not os.path.exists(path):
            continue
        yield man, open(path, "rb").read()


def grade(man, entries, kind, problems, verbose):
    """Compare one container's reading with the oracle's manifest."""
    want = {e["name"]: e for e in man["entries"]}
    if kind == "single":
        got = {list(want)[0]: entries[0]} if len(want) == 1 else {}
        if len(want) != 1:
            problems.append("%s: the oracle lists %d entries in a single "
                            "compressed file" % (man["fixture"], len(want)))
            return 0
    else:
        got = {}
        for e in entries:
            got["/".join(c.decode("mac_roman") for c in e["path"])] = e
    checked = 0
    if set(got) != set(want):
        problems.append("%s: paths differ — ours only %r, oracle only %r"
                        % (man["fixture"], sorted(set(got) - set(want))[:3],
                           sorted(set(want) - set(got))[:3]))
        return 0
    for name, e in sorted(got.items()):
        w = want[name]
        if w.get("is_dir") or e.get("is_dir"):
            if bool(w.get("is_dir")) != bool(e.get("is_dir")):
                problems.append("%s: %r is a folder to one of us only"
                                % (man["fixture"], name))
            checked += 1
            continue
        for fork in ("data", "rsrc"):
            k = fork + "_size"
            if w.get(k) is None:
                continue
            if e.get(k) != w[k]:
                problems.append("%s: %r %s fork is %r, the oracle says %d"
                                % (man["fixture"], name, fork, e.get(k), w[k]))
            checked += 1
        for k in ("type", "creator"):
            if not w.get(k):
                continue
            if e.get(k) != w[k]:
                problems.append("%s: %r %s is %r, the oracle says %r"
                                % (man["fixture"], name, k, e.get(k), w[k]))
            checked += 1
        if verbose:
            print("  %-40s %8s/%-8s %s/%s meth %s/%s"
                  % (name[:40], e.get("data_size"), e.get("rsrc_size"),
                     e.get("type"), e.get("creator"),
                     e.get("data_method"), e.get("rsrc_method")))
    return checked


# --------------------------------------------------------------------
# --grid: derive the layout rather than assume it
# --------------------------------------------------------------------

def grid(only):
    """For each field, every offset that agrees with the oracle EVERYWHERE.

    The point is that the document's numbers are measured here rather
    than copied from somebody's parser. A field that survives at one
    offset is pinned by the corpus; a field that survives at several is
    not, and is named as such.

    Three shapes, and each is located by something the FORMAT supplies
    rather than by the layout under test: a compressed file's header is
    at zero and says so with its magic; an archive's first record is the
    first occurrence of the archive magic past byte 4; and a file header
    inside an archive is wherever the walk that the fork lengths already
    grade put it.
    """
    keep, votes = collections.defaultdict(dict), collections.Counter()

    def vote(shape, field, offs):
        votes[(shape, field)] += 1
        d = keep[shape]
        d[field] = offs if field not in d else (d[field] & offs)

    def want_u32(w, field):
        if field in ("type", "creator"):
            return (struct.unpack(">I", w[field].encode("mac_roman"))[0]
                    if w.get(field) else None)
        return w.get(field)

    for man, b in fixtures(only):
        ents = man["entries"]
        if b[:4] in (DDAR, DDA2):
            magic = b[:4]
            first = b.find(magic, 4)
            if first < 0 or not ents:
                continue
            vote(magic.decode(), "body", {first})
        elif len(ents) == 1:
            for field in ("data_size", "rsrc_size", "type", "creator"):
                v = want_u32(ents[0], field)
                if v is None:
                    continue
                vote("single", field,
                     {o for o in range(0, F_SIZE - 3) if u32(b, o) == v})

    # Every RECORD, wherever the walk put it — and the walk is the thing
    # the 643 assertions above already grade, so its record positions
    # are established before this asks what is inside one. The manifest
    # is sorted by name and the archive is not, so a record has to be
    # matched to its own entry rather than to the first.
    for man, b in fixtures(only):
        try:
            kind, entries = read_container(b, man["fixture"])
        except Exception:                              # noqa: BLE001
            continue
        if kind == "single":
            continue
        shape = kind
        span = R_SIZE if kind == "DDAR" else 90
        want = {e["name"]: e for e in man["entries"]}
        for e in entries:
            key = "/".join(c.decode("mac_roman") for c in e["path"])
            w = want.get(key)
            if w is None:
                continue
            rec = b[e["rec_at"]:e["rec_at"] + span]
            nm = key.split("/")[-1].encode("mac_roman")
            offs = set()
            o = rec.find(nm)
            while o >= 0:
                if o >= 1 and rec[o - 1] == len(nm):
                    offs.add(o - 1)
                o = rec.find(nm, o + 1)
            vote(shape, "name", offs)
            if e.get("is_dir") or not e.get("stored"):
                continue
            # Only a record that carries the forks ITSELF states their
            # lengths; the rest hand that to the file header.
            for field in ("data_size", "rsrc_size", "type", "creator"):
                v = want_u32(w, field)
                if v is None:
                    continue
                vote(shape + " (stored)", field,
                     {o for o in range(0, span - 3) if u32(rec, o) == v})

    # The file header WHEREVER it sits — the one shape with enough
    # type/creator votes to pin anything, because the oracle records
    # those for 87 entries inside the two archive containers and for
    # three compressed files.
    for man, b in fixtures(only):
        try:
            kind, entries = read_container(b, man["fixture"])
        except Exception:                              # noqa: BLE001
            continue
        want = {e["name"]: e for e in man["entries"]}
        for e in entries:
            if e.get("is_dir") or e.get("stored") or "payload" not in e:
                continue
            at = e["payload"] - F_SIZE
            key = ("/".join(c.decode("mac_roman") for c in e["path"])
                   if e["path"][0] is not None else list(want)[0])
            w = want.get(key)
            if not w:
                continue
            for field in ("data_size", "rsrc_size", "type", "creator"):
                v = want_u32(w, field)
                if v is None:
                    continue
                vote("filehdr", field,
                     {o for o in range(0, F_SIZE - 3)
                      if u32(b, at + o) == v})

    for shape in ("single", "filehdr", "DDAR", "DDAR (stored)",
                  "DDA2", "DDA2 (stored)"):
        if shape not in keep:
            continue
        print("grid: %s" % shape)
        for field, offs in sorted(keep[shape].items()):
            n = votes[(shape, field)]
            offs = sorted(offs)
            note = ("pinned" if len(offs) == 1 else
                    "NOT pinned — %d offsets survive" % len(offs))
            print("  %-10s %-22s %s (%d vote(s))"
                  % (field, str(offs[:6]), note, n))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", action="append")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(MANDIR):
        print("derive-ddc: no manifests here (skipped)")
        return 0
    if a.grid:
        return grid(a.fixture)

    problems, n, checked = [], 0, 0
    shapes = collections.Counter()
    methods = collections.Counter()
    trailer = collections.Counter()
    deltas = []
    for man, b in fixtures(a.fixture):
        if a.verbose:
            print(man["fixture"])
        try:
            kind, entries = read_container(b, man["fixture"])
        except Exception as exc:                       # noqa: BLE001
            problems.append("%s: %s" % (man["fixture"], exc))
            continue
        if kind is None:
            problems.append("%s: not a DiskDoubler container" % man["fixture"])
            continue
        n += 1
        shapes[kind] += 1
        for e in entries:
            if e.get("is_dir"):
                continue
            methods[(e.get("data_method"), e.get("rsrc_method"))] += 1
            if "trailer" in e:
                trailer[(kind, e["trailer"])] += 1
            for fork in ("data", "rsrc"):
                if e.get(fork + "_delta"):
                    deltas.append((man["fixture"],
                                   "/".join(c.decode("mac_roman")
                                            for c in e["path"]),
                                   fork, e[fork + "_delta"]))
        checked += grade(man, entries, kind, problems, a.verbose)

    if not n:
        print("derive-ddc: no DiskDoubler fixtures here (skipped)")
        return 0
    for p in problems:
        print("DERIVE-DDC " + p)
    print("derive-ddc: %d archive(s) — %s" % (n, ", ".join(
        "%s %d" % (k, v) for k, v in sorted(shapes.items()))))
    print("            %d assertion(s) against the oracle, %d disagreement(s)"
          % (checked, len(problems)))
    print("            methods (data/rsrc): " + ", ".join(
        "%s/%s x%d" % (d, r, c) for (d, r), c in sorted(methods.items(),
                                                        key=lambda kv: -kv[1])))
    print("            a compressed file ends with a copy of its own "
          "header: " + ", ".join(
              "%s %s %d" % (k, "yes" if t else "NO", v)
              for (k, t), v in sorted(trailer.items())))
    print("            the second form of method 10, per the container — "
          "hold this against `derive_dd.py`, which has no container and "
          "finds out by decoding:")
    for f, path, fork, dist in deltas:
        print("              %s :: %s %s (distance %d)" % (f, path, fork, dist))
    if not deltas:
        print("              none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

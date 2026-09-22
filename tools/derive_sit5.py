#!/usr/bin/env python3
"""derive_sit5.py — read the StuffIt 5 container from the FORMAT's own
published description, and say where that description is wrong.

The inventory row for `fmt_sit5.c` said the container parser was
XADMaster's and that "Russotto's write-up describes the SIT5 container
too". It does not: `reference/notes/arsenic_russotto.md` is method 15
and nothing else, start to finish. **The description that does exist is
one page from a file this project already had.**
`reference/notes/StuffIt.md` — the wiki page StuffIt method 13 was read
out of — names it in its *Sources* list, and it lives on the same
wiki, beside eight pages `tools/fetch_references.sh` already fetches:

    reference/notes/sit5_specs_theunarchiver.md   (StuffIt5Format)

This reader is written from that page alone. Where the page is wrong or
silent the fix is marked **CORRECTION** below and in
`docs/formats/stuffit5-container.md`.

    tools/derive_sit5.py [archive ...]

It reads containers, not streams: every entry's name, both forks'
lengths, their methods and their CRCs, and the tree the offsets make.
Those are checked against `fixtures/manifests/`, which an independent
oracle wrote — a name and two fork lengths per entry, and the count.

Not in `ci.sh`: it needs the fixtures, which are not committed.
"""
import argparse
import glob
import json
import os
import struct
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "reference", "notes",
                   "sit5_specs_theunarchiver.md")
FIXDIR = os.path.join(ROOT, "fixtures")

# "Archive header": an 80-byte banner whose four year digits vary.
BANNER_A = b"StuffIt (c)1997-"
BANNER_B = (b" Aladdin Systems, Inc., http://www.aladdinsys.com/StuffIt/"
            b"\x0d\x0a")
ID = 0xA5A5A5A5                 # "Identifier" at the top of every entry
FLAG_ENCRYPTED = 0x20           # "The known bits of the Flags field"
FLAG_FOLDER = 0x40
NONE = 0xFFFFFFFF               # the folder marker "ignored when reading"


def u16(b, at):
    return struct.unpack_from(">H", b, at)[0]


def u32(b, at):
    return struct.unpack_from(">I", b, at)[0]


class Sit5:
    def __init__(self, blob):
        self.b = blob
        self.entries = []
        self.notes = []

    def archive_header(self):
        b = self.b
        if b[:16] != BANNER_A or b[20:20 + len(BANNER_B)] != BANNER_B:
            raise ValueError("not a StuffIt 5 banner")
        # CORRECTION. The page's archive-header table gives offset 84
        # TWICE — "Total size of archive" and "Offset of first entry
        # header" — and then jumps to 86. Two fields cannot share an
        # offset, and following it puts the walk in the middle of the
        # banner's trailer. The entry count is a u16 at 92 and the
        # first entry's offset a u32 at 94, which is what every one of
        # the 31 archives here reads correctly with (and what Maconv's
        # copy of this table says: 092 and 094).
        version = b[82]
        flags = b[83]
        total = u32(b, 84)
        count = u16(b, 92)
        first = u32(b, 94)
        if version != 5:
            self.notes.append("version byte is %d, not 5" % version)
        if total != len(b):
            self.notes.append("total size %d, file is %d B" % (total, len(b)))
        return flags, count, first

    def entry(self, at):
        b = self.b
        if u32(b, at) != ID:
            raise ValueError("no 0xa5a5a5a5 identifier at %d" % at)
        ver = b[at + 4]
        hsize = u16(b, at + 6)
        flags = b[at + 9]
        prev, nxt = u32(b, at + 18), u32(b, at + 22)
        parent = u32(b, at + 26)
        nlen = u16(b, at + 30)
        dlen, dclen = u32(b, at + 34), u32(b, at + 38)
        dcrc = u16(b, at + 42)
        folder = bool(flags & FLAG_FOLDER)
        e = {"at": at, "ver": ver, "flags": flags, "next": nxt,
             "parent": parent, "folder": folder, "dlen": dlen,
             "dclen": dclen, "dcrc": dcrc, "prev": prev,
             "rlen": 0, "rclen": 0, "rcrc": 0, "rmethod": None,
             "encrypted": bool(flags & FLAG_ENCRYPTED)}
        if folder:
            e["nfiles"] = u16(b, at + 46)
            e["method"] = None
            p = at + 48
        else:
            e["method"] = b[at + 46]
            plen = b[at + 47]
            p = at + 48 + plen
        e["name"] = bytes(b[p:p + nlen])
        p += nlen
        # The comment fields are inside the header, so a header that
        # ends at `hsize` has none. The page does not say that; it is
        # what keeps a folder's "Unknown data until next entry" from
        # being read as a comment size.
        if p + 4 <= at + hsize:
            e["commentlen"] = u16(b, p)
        if folder:
            return e, None
        # "Second file header", which follows the file header.
        s = at + hsize
        f2 = u16(b, s)
        e["type"] = bytes(b[s + 4:s + 8])
        e["creator"] = bytes(b[s + 8:s + 12])
        # The page gives two columns of offsets, "32/36" and so on:
        # one four-byte field is "not included in version 3, included
        # in version 1".
        base = s + (36 if ver == 1 else 32)
        if f2 & 1:
            e["rlen"], e["rclen"] = u32(b, base), u32(b, base + 4)
            e["rcrc"] = u16(b, base + 8)
            e["rmethod"] = b[base + 12]
        e["second"] = s
        return e, f2

    def walk(self):
        flags, count, first = self.archive_header()
        seen = set()
        todo = [first]
        while todo:
            at = todo.pop(0)
            while at and at != NONE and at + 48 <= len(self.b):
                if at in seen:
                    raise ValueError("entry offset %d twice" % at)
                seen.add(at)
                e, _f2 = self.entry(at)
                # "If the Data fork uncompressed length field is set to
                # 0xffffffff for a folder entry, this entry is a
                # special marker ... ignored when reading."
                if not (e["folder"] and e["dlen"] == NONE):
                    self.entries.append(e)
                if e["folder"] and e["dlen"] != NONE:
                    # A folder's "Offset of first entry in folder" is
                    # the field the page calls the data fork length.
                    if e["dlen"] not in (0, NONE):
                        todo.append(e["dlen"])
                at = e["next"]
        return self.entries, count


def norm(s):
    return unicodedata.normalize("NFC", s)


def matchkey(name):
    """A classic Mac name may itself contain "/" — `ReadMe/Leerme` is a
    real entry in `derived-Domino_v1.4.sit` — so a path built with "/"
    is ambiguous. Flattening both separators for MATCHING only is the
    rule `make_manifests.py` already uses."""
    return name.replace(b":", b"_").replace(b"/", b"_")


def fullpath(entries, e):
    """The entry's path, from the "Offset of parent folder entry"
    chain. Nothing in the container stores a path; this is the tree the
    offsets make, and comparing it against the oracle's paths is what
    tests the tree rather than the record."""
    by_at = {x["at"]: x for x in entries}
    parts, seen = [e["name"]], {e["at"]}
    at = e["parent"]
    while at in by_at and at not in seen:
        seen.add(at)
        parts.append(by_at[at]["name"])
        at = by_at[at]["parent"]
    return b"/".join(reversed(parts))


def manifest_for(path):
    mp = os.path.join(FIXDIR, "manifests", os.path.basename(path) + ".json")
    if not os.path.exists(mp):
        return None
    return json.load(open(mp))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archives", nargs="*")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(DOC):
        print("derive-sit5: no reference/notes/sit5_specs_theunarchiver.md "
              "— run tools/fetch_references.sh (skipped)")
        return 0
    paths = a.archives
    if not paths:
        for mp in sorted(glob.glob(os.path.join(FIXDIR, "manifests",
                                                "*.json"))):
            man = json.load(open(mp))
            if man.get("format") == "StuffIt 5":
                p = os.path.join(FIXDIR, man["fixture"])
                if os.path.exists(p):
                    paths.append(p)
    if not paths:
        print("derive-sit5: no StuffIt 5 fixtures here (skipped)")
        return 0

    arcs = ents = bad = 0
    methods = {}
    for p in paths:
        with open(p, "rb") as fh:
            blob = fh.read()
        s = Sit5(blob)
        try:
            got, _count = s.walk()
        except (ValueError, struct.error, IndexError) as e:
            bad += 1
            print("  UNREADABLE %s: %s" % (os.path.basename(p), e))
            continue
        arcs += 1
        ents += len(got)
        for e in got:
            if not e["folder"]:
                methods[e["method"]] = methods.get(e["method"], 0) + 1
                if e["rmethod"] is not None:
                    methods[e["rmethod"]] = methods.get(e["rmethod"], 0) + 1
        for n in s.notes:
            print("  note %s: %s" % (os.path.basename(p), n))
        man = manifest_for(p)
        if not man:
            continue
        # The manifest holds one entry per FILE, with the full path and
        # both fork lengths. Names are compared as the archive's own
        # bytes: the oracle reports them decoded as MacRoman, which is
        # what `run_diff.py` reverses too.
        want = {}
        for e in man["entries"]:
            if e.get("is_dir"):
                continue
            try:
                key = norm(e["name"]).encode("mac_roman")
            except UnicodeEncodeError:
                key = norm(e["name"]).encode("utf-8")
            want[matchkey(key)] = e
        mine = {}
        for e in got:
            if not e["folder"]:
                mine[matchkey(fullpath(got, e))] = e
        if len(mine) != len(want):
            bad += 1
            print("  DIFFER %s: %d files, the manifest has %d"
                  % (os.path.basename(p), len(mine), len(want)))
            continue
        for name, e in sorted(mine.items()):
            w = want.get(name)
            if w is None:
                bad += 1
                print("  DIFFER %s: no manifest entry for %r"
                      % (os.path.basename(p), name))
                continue
            for fork, size in (("data", e["dlen"]), ("rsrc", e["rlen"])):
                ws = w.get(fork + "_size")
                if ws is not None and ws != size:
                    bad += 1
                    print("  DIFFER %s :: %r %s: header says %d B, the "
                          "oracle wrote %d B" % (os.path.basename(p),
                                                 name, fork, size, ws))
        if a.verbose:
            print("  %-44s %3d file(s)" % (os.path.basename(p), len(mine)))

    print("derive-sit5: %d archives, %d entries read from the wiki page "
          "alone" % (arcs, ents))
    print("             fork methods " + ", ".join(
        "%s:%d" % (k, v) for k, v in sorted(methods.items())))
    print("             %d disagreement(s) with the oracle manifests" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

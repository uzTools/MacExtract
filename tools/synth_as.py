#!/usr/bin/env python3
"""synth_as.py — AppleSingle files that carry every field the Finder keeps.

    tools/synth_as.py --case meta  -o fixtures/synth-as-meta.as
    tools/synth_as.py --case dosro -o fixtures/synth-as-dosro.as
    tools/synth_as.py --describe meta

No fixture in the corpus is an AppleSingle file with a comment, a backup
date, a whole FXInfo or a locked bit, so these are written here, to the
letter of reference/notes/rfc1740.txt (appendix A for the header, B for
the entries):

  meta   entries 1, 2, 3, 4 (comment), 8 (all four dates), 9 (FInfo with
         an icon position and a window, FXInfo with an icon id, a script
         byte, a comment id and a put-away folder), 10 (AS_LOCKED).
  dosro  entries 1, 3, 8 with the backup date 0x80000000 — the RFC's
         "unknown" — and 12 with AS_DOS_READONLY, which is how HFS spells
         locked; no entry 10.

`--describe` prints what each case states, which is what
tools/run_meta.py holds the engine to where `lsar` reads nothing (the lock
bits: XADMaster has no locked key).
"""
import argparse
import json
import struct
import sys

EPOCH_2000 = 0xB492F400        # 2000-01-01 in Mac seconds (fmt_applesingle.c)

def empty_rsrc():
    """A resource fork with no resources: data and map both at 256, an
    empty data area, and a 30-byte map whose type count is -1 — the
    header fields tools/vmac_check.py reads (mask_reserved) — with text
    in the application area, 128..255, which every reader compares. A
    fork that is not shaped like this is masked on the Macintosh and not
    on the host, and the emulator's read-back then disagrees with a fork
    that is byte-exact on the disk (measured 2026-10-17)."""
    head = struct.pack(">IIII", 256, 256, 0, 30)
    app = b"Application area: a resource fork kept whole.".ljust(128, b"\0")
    m = head + struct.pack(">IHHHH", 0, 0, 0, 28, 30) + struct.pack(">h", -1)
    return head + b"\0" * 112 + app + m


EMPTY_RSRC = empty_rsrc()

CASES = {
    "meta": dict(
        name=b"Kept Whole",
        data=b"The data fork of a file that keeps its Finder info.\r" * 8,
        rsrc=EMPTY_RSRC,
        comment=b"Get Info comment, carried by AppleSingle entry 4.",
        dates=(0x12345678, 0x12345F00, 0x13000000, 0x13000100),
        # FInfo: type, creator, fdFlags 0x0120 (inited clear, 0x0100 set
        # would be cleared on disk), fdLocation v=0x50 h=0x64, fdFldr -3
        finfo=b"TEXTttxt" + struct.pack(">HhhH", 0x2120, 0x50, 0x64, 0xFFFD),
        # FXInfo: fdIconID 0x0101, fdUnused 6 bytes, fdScript 0x81,
        # fdXFlags 0, fdComment 0x5389, fdPutAway 0x22
        fxinfo=struct.pack(">H", 0x0101) + b"\0" * 6 + b"\x81\0"
               + struct.pack(">HI", 0x5389, 0x22),
        macinfo=1,
        dos=None),
    "dosro": dict(
        name=b"Read Only",
        data=b"A file a DOS machine marked read-only.\r\n" * 4,
        rsrc=None,
        comment=None,
        dates=(0x10000000, 0x10000100, 0x80000000, 0x80000000),
        finfo=None, fxinfo=None, macinfo=None,
        dos=0x01),
}


def build(c):
    ents = []
    if c["data"] is not None:
        ents.append((1, c["data"]))
    if c["rsrc"] is not None:
        ents.append((2, c["rsrc"]))
    ents.append((3, c["name"]))
    if c["comment"] is not None:
        ents.append((4, c["comment"]))
    ents.append((8, struct.pack(">4I", *c["dates"])))
    if c["finfo"] is not None:
        ents.append((9, c["finfo"] + c["fxinfo"]))
    if c["macinfo"] is not None:
        ents.append((10, b"\0\0\0" + bytes([c["macinfo"]])))
    if c["dos"] is not None:
        ents.append((12, bytes([0, c["dos"]])))
    head = struct.pack(">II16sH", 0x00051600, 0x00020000, b"\0" * 16, len(ents))
    off = len(head) + 12 * len(ents)
    table, body = b"", b""
    for eid, b in ents:
        table += struct.pack(">III", eid, off + len(body), len(b))
        body += b
    return head + table + body


def describe(name):
    c = CASES[name]
    d = c["dates"]
    return {
        "name": c["name"].decode("mac-roman"),
        "finfo": None if c["finfo"] is None else c["finfo"].hex(),
        "fxinfo": None if c["fxinfo"] is None else c["fxinfo"].hex(),
        "backup": None if d[2] == 0x80000000
        else "%08x" % ((d[2] + EPOCH_2000) & 0xFFFFFFFF),
        "comment": None if c["comment"] is None else c["comment"].hex(),
        "locked": "L" if (c["macinfo"] or 0) & 1 or (c["dos"] or 0) & 1
        else ("n" if c["macinfo"] is not None or c["dos"] is not None
              else "-"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", choices=sorted(CASES), default="meta")
    ap.add_argument("-o", "--out")
    ap.add_argument("--describe", choices=sorted(CASES))
    a = ap.parse_args()
    if a.describe:
        print(json.dumps(describe(a.describe), indent=1, sort_keys=True))
        return
    blob = build(CASES[a.case])
    if a.out:
        open(a.out, "wb").write(blob)
        print("synth_as: %s — %d B" % (a.out, len(blob)))
    else:
        sys.stdout.buffer.write(blob)


if __name__ == "__main__":
    main()

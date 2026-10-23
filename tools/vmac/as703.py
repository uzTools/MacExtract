#!/usr/bin/env python3
"""as703.py — does StuffIt 7.0.3's Expander read AppleSingle and AppleDouble,
and what does it want them typed and named?

Asked by MacStamp (2026-10-23), which stamps a type and creator onto files
and needs to know what pair an AppleSingle file should carry for Aladdin's
last Mac OS 9 box to open it. The subject is `fixtures/synth-as-meta.as`
("Kept Whole": both forks, a comment, four dates, the lock), placed on
`compat9.py`'s Mac OS 9.2 transfer volume nine times, each in a folder of
its own, under a different name and pair:

    a1  Comment.as  BINA/SITx   the control — the 2026-10-19 run's shape
    a2  Comment.as  ????/SITx   no type
    a3  Comment     BINA/SITx   no extension
    a4  Comment     ????/SITx   neither
    a5  Comment.as  TEXT/SITx   a type that says text
    a6  Comment.as  ????/????   no pair at all: the Finder cannot hand this
                                over, so it goes through File > Expand
    d1  ._Comment + Comment     AppleDouble, Mac OS X's header name
    d2  %Comment  + Comment     AppleDouble, A/UX's header name
    d3  ._Comment alone         AppleDouble header with no data file

The AppleDouble header is the AppleSingle file with magic 0x00051607 and
no entry 1 (RFC 1740, section 2: "the data fork is stored in a separate
file"); the data file is entry 1's bytes. Creator `SITx` is the Expander's
signature, so the Finder's Cmd-Down hands the file over as an `odoc`
(compat9.py). Driven by hand, frame by frame, with os9mouse.Mac(attach=True).

    as703.py --assemble -o <dir>
    as703.py --assemble --set tigr -o <dir>   # one BINA/TIGR copy, for the Finder
    as703.py --boot -o <dir>      # compat9.boot
    as703.py --stop -o <dir>
    as703.py --read -o <dir>      # compat9.read: every file, both forks

What it cannot see: why the Expander refused, beyond its own alert; and
the Deluxe application, which is not driven.
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import compat9                                               # noqa: E402
import sitzip                                                # noqa: E402
from arcmac import macbinary                                 # noqa: E402

AS = os.path.join(REPO, "fixtures", "synth-as-meta.as")
AS_MAGIC, AD_MAGIC = 0x00051600, 0x00051607   # RFC 1740, sections 2 and 3


def appledouble(blob):
    """(header file, data file) for one AppleSingle file."""
    magic, ver, filler, n = struct.unpack(">II16sH", blob[:26])
    assert magic == AS_MAGIC
    ents, data = [], b""
    for i in range(n):
        eid, off, ln = struct.unpack(">III", blob[26 + 12 * i:38 + 12 * i])
        if eid == 1:
            data = blob[off:off + ln]
        else:
            ents.append((eid, blob[off:off + ln]))
    head = struct.pack(">II16sH", AD_MAGIC, ver, filler, len(ents))
    off = len(head) + 12 * len(ents)
    table, body = b"", b""
    for eid, b in ents:
        table += struct.pack(">III", eid, off + len(body), len(b))
        body += b
    return head + table + body, data


def subjects(which="pairs"):
    single = open(AS, "rb").read()
    header, data = appledouble(single)
    q = "????"
    if which == "tigr":
        # Mac OS 9's own Internet Config table maps application/applefile
        # to BINA/TIGR, creator application "Tiger", post-processed by
        # StuffIt Expander; nothing in either box carries TIGR. What a
        # double-click does with that pair is the question.
        return [("t1", "Comment.as", "BINA", "TIGR", single)]
    s = [("a1", "Comment.as", "BINA", "SITx", single),
         ("a2", "Comment.as", q, "SITx", single),
         ("a3", "Comment", "BINA", "SITx", single),
         ("a4", "Comment", q, "SITx", single),
         ("a5", "Comment.as", "TEXT", "SITx", single),
         ("a6", "Comment.as", q, q, single),
         ("d1", "._Comment", "BINA", "SITx", header),
         ("d1", "Comment", q, q, data),
         ("d2", "%Comment", "BINA", "SITx", header),
         ("d2", "Comment", q, q, data),
         ("d3", "._Comment", "BINA", "SITx", header)]
    return s


def assemble(outdir, which="pairs"):
    boot, xfer = sitzip.assemble("703", outdir)
    v = sitzip.Vol(xfer, partition=1)
    done = set()
    try:
        for folder, name, t, c, blob in subjects(which):
            if folder not in done:
                v.mkdir(folder)
                done.add(folder)
            v.put(macbinary(name, t, c, blob, b""), "%s:%s" % (folder, name))
    finally:
        v.close()
    print("as703: %d files in %d folders on %s"
          % (len(subjects(which)), len(done), xfer))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--assemble", action="store_true")
    p.add_argument("--set", choices=("pairs", "tigr"), default="pairs")
    p.add_argument("--boot", action="store_true")
    p.add_argument("--stop", action="store_true")
    p.add_argument("--read", action="store_true")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--limit", type=int, default=3 * 3600)
    a = p.parse_args()
    if a.assemble:
        assemble(a.out, a.set)
    elif a.boot:
        compat9.boot(a.out, a.limit)
    elif a.stop:
        compat9.stop(a.out)
    elif a.read:
        compat9.read(a.out)


if __name__ == "__main__":
    main()

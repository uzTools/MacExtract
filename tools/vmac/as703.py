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
    as703.py --assemble --set claims --app build/mac/MacExtract.bin -o <dir>
    as703.py --assemble --set boxes -o <dir>   # + StuffIt Deluxe and Tiger
    as703.py --assemble --set icons --app build/mac/MacExtract.bin -o <dir>
    as703.py --assemble --set adext --app dist/MacExtract.bin -o <dir>
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
    if which == "boxes":
        # The three things the first runs could not ask (DECISIONS.md
        # 2026-10-23, *the format 7.0.3 sniffs*): a BINA/TIGR file with
        # Tiger itself on the volume; AppleSingle and AppleDouble through
        # the Deluxe APPLICATION's own Open, not the Expander; and the
        # same two DROPPED on the Expander, from the volume's root.
        return [("t1", "Comment.as", "BINA", "TIGR", single),
                ("p1", "Comment.as", q, q, single),
                ("p2", "._Comment", "BINA", q, header),
                ("p2", "Comment", q, q, data),
                ("", "Drop.as", q, q, single),
                ("", "._Dropd", "BINA", q, header),
                ("", "Dropd", q, q, data)]
    if which == "icons":
        # The bundle's FREFs point at icon local ID 1 since 2026-10-23
        # (they pointed at 2..18, which the BNDL maps to nothing): a
        # document typed ApSi with MacExtract's creator should draw its
        # icon. And one of the four types added that day, ZIVM, on the
        # file MacCompress 3.2 itself wrote (maccompress.py), whose
        # creator LZIV is on no volume here.
        mcz = os.path.join(os.path.dirname(sitzip.CACHE), "vmac",
                           "specimens", "maccompress", "Alpha.mcz")
        return [("", "Single.as", "ApSi", "MExt", single),
                ("z1", "Alpha", "ZIVM", "LZIV", open(mcz, "rb").read())]
    if which == "sdar":
        # A SuperDisk! archive's data fork alone, stamped SDar/MExt — the
        # pair the maintainer chose on 2026-10-24 — double-clicked: the
        # Finder should launch MacExtract, the creator, and it should
        # extract. `derived-SD__Utilities.x`, 3 files.
        sd = os.path.join(REPO, "fixtures", "derived-SD__Utilities.x")
        return [("s1", "Utilities.x", "SDar", "MExt", open(sd, "rb").read())]
    if which == "adext":
        # MacStamp (2026-10-24): what MacExtract itself does with a loose
        # AppleDouble header, double-clicked. Creator MExt, so the Finder
        # hands each header to MacExtract; the three header names, beside
        # their data file, and Mac OS X's alone.
        return [("x1", "._Comment", q, "MExt", header),
                ("x1", "Comment", q, q, data),
                ("x2", "._Comment", q, "MExt", header),
                ("x3", "%Comment", q, "MExt", header),
                ("x3", "Comment", q, q, data),
                ("x4", "Comment.ad", q, "MExt", header),
                ("x4", "Comment", q, q, data)]
    if which == "claims":
        # The bundle's exact-type claims (mac/macextract_icons.r): the
        # Finder's alternate-program dialog should offer MacExtract for a
        # BINA file with no TIGR anywhere, and for a StuffIt archive whose
        # creator SIT! (StuffIt Deluxe) is absent. `--app` puts the build
        # under test on the volume.
        sit = open(os.path.join(REPO, "fixtures", "derived-Export.sit"), "rb").read()
        return [("t1", "Comment.as", "BINA", "TIGR", single),
                ("s1", "Export.sit", "SITD", "SIT!", sit)]
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


def deluxe_bin(outdir):
    """StuffIt Deluxe 7.0.3, the application, out of sitzip's payload."""
    data, idx = sitzip.payload("703")
    name = "StuffIt Deluxe"
    t, c, flags = idx[name]
    df, rf = sitzip.forks(data, name)
    out = os.path.join(outdir, "deluxe.bin")
    open(out, "wb").write(macbinary(name, t, c, df, rf, flags))
    return out


# Tiger 1.1 (Robert Lenoil, 1992), APPL/TIGR: Discmaster's copy of
# Info-Mac II's `Utility:Tiger 1.1:Tiger`, MacBinary, SHA-1 878a0f50...
TIGER = os.path.join(os.path.dirname(sitzip.CACHE), "compat", "tiger",
                     "Tiger.bin")
EXTRA_APPS = {}


def assemble(outdir, which="pairs", app=None):
    if which == "boxes":
        os.makedirs(outdir, exist_ok=True)
        EXTRA_APPS["boxes"] = [(deluxe_bin(outdir), "StuffIt Deluxe"),
                               (TIGER, "Tiger")]
    boot, xfer = sitzip.assemble("703", outdir)
    v = sitzip.Vol(xfer, partition=1)
    done = set()
    try:
        if app:
            v.put(open(app, "rb").read(), "MacExtract")
        for path, name in EXTRA_APPS.get(which, ()):
            v.put(open(path, "rb").read(), name)
        for folder, name, t, c, blob in subjects(which):
            if folder and folder not in done:
                v.mkdir(folder)
                done.add(folder)
            v.put(macbinary(name, t, c, blob, b""),
                  "%s:%s" % (folder, name) if folder else name)
    finally:
        v.close()
    print("as703: %d files in %d folders on %s"
          % (len(subjects(which)), len(done), xfer))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--assemble", action="store_true")
    p.add_argument("--set", choices=("pairs", "tigr", "claims", "boxes", "icons", "sdar", "adext"), default="pairs")
    p.add_argument("--app", help="a MacBinary MacExtract to put beside the Expander")
    p.add_argument("--boot", action="store_true")
    p.add_argument("--stop", action="store_true")
    p.add_argument("--read", action="store_true")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--limit", type=int, default=3 * 3600)
    a = p.parse_args()
    if a.assemble:
        assemble(a.out, a.set, a.app)
    elif a.boot:
        compat9.boot(a.out, a.limit)
    elif a.stop:
        compat9.stop(a.out)
    elif a.read:
        compat9.read(a.out)


if __name__ == "__main__":
    main()

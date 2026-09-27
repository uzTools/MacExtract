#!/usr/bin/env python3
"""Keep NOTICE's inventory of borrowed code honest, mechanically.

NOTICE is the single home for "what in this engine is still XADMaster's
or macutils'" (CLAUDE.md, *one home per finding*).  A prose list goes
stale the moment a file sheds its last citation, and this project has
been bitten three times by exactly that: `unc_lzah.c`'s preloads and
`fmt_binhex.c`'s macutils rules were both recorded as gone while still
in the source, and on 2026-09-27 `fmt_sit.c` was declared clean of
XADStuffItParser.m in three documents while carrying a `Source:` line
naming it (BLOCKERS.md, *Withdrawn claims*).

So the list is checked rather than remembered.  Every file under src/
that mentions XADMaster or macutils at all must be in exactly one of
the two sets below, and this fails when one is not:

  CARRIES     — still has code or a fact that is somebody else's, and
                is named in NOTICE's inventory.
  HISTORICAL  — mentions a reference only to say what it no longer
                owes, or to compare against it.  Nothing borrowed.

A file that gains a citation fails as unclassified: inventory it.  A
file in CARRIES that stops mentioning anything fails too — that is a
row that can leave, and the point of the check is that nobody has to
notice it by hand.

Moving a file from CARRIES to HISTORICAL is the act of shedding it:
do it in the same commit as the re-citation, with NOTICE.
"""

import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
NOTICE = ROOT / "NOTICE"

# Files that still carry somebody else's code or facts, and the one-line
# summary of WHAT. The detail is NOTICE's; OPEN_ITEMS.md holds only the
# ones with a route left.
CARRIES = {
    "unc_lzdyn.c":      "-lh2- and -lh3- (XADLZHOldHandles.m), whole file",
    "fmt_lzh.c":        "a NUL in a level 0/1 name field ends it (XADLZHParser.m)",
    "fmt_packit.c":     "the resync strategy (macutils pit.c) and both ciphers",
    "fmt_sit.c":        "the encrypted fork's key layout; three method-8 rules",
    "fmt_sit5.c":       "the encrypted archive only (XADStuffIt5Parser.m)",
    "fmt_dd.c":         "the DDAR 0x20 raw-fork shape",
    "fmt_arc.c":        "Crunch 5/6/7 and Crush, and the method numbers",
    "unc_crypt.c":      "StuffItDES, StuffIt 5's hash, PackIt's keytr1, ARC's garble",
    "fmt_binhex.c":     "macutils hexbin's rules about text that has been mailed",
    "fmt_uu.c":         "the same, plus UUTool's MU layout (macutils mu.c)",
    "fmt_mime.c":       "the uu terminator, as fmt_uu.c reads it",
    "unc_lzah.c":       "the -lh1-/method-5 window preload (resetLZSSHandle)",
    "fmt_macbinary.c":  "the CRC-16/0xA001 fallback and the nonzero-date test",
    "fmt_applesingle.c": "the byte-swapped header",
    "fmt_sitseg.c":     "the whole StuffIt split header",
    "fmt_stubs.c":      "DiskDoubler's two older headers (macutils dd.h)",
    "unc_internal.h":   "the MIME line rule, DiskDoubler method 8, the LZAH preload",
}

# Mentions a reference only to say what it no longer owes, or to
# compare against it. Nothing here is borrowed.
HISTORICAL = {
    "fmt_exo.c", "fmt_exo_probe.c", "fmt_foreign.c", "fmt_superdisk.c",
    "sit_arsenic.c", "unc_encinfo.c", "unc_huffman.c", "crypt_tables.h",
    "fmt_cpt.c", "fmt_cptseg.c", "fmt_now.c", "unc_util.c",
    "fmt_binhex_priv.h", "sit6_tables.h",
}

MENTION = re.compile(r"XAD|macutils")


def main():
    found = set()
    for p in sorted(SRC.glob("*.c")) + sorted(SRC.glob("*.h")):
        if MENTION.search(p.read_text(errors="replace")):
            found.add(p.name)

    bad = []

    for name in sorted(found - set(CARRIES) - HISTORICAL):
        bad.append("%s mentions a reference and is in neither set. If it "
                   "borrows something, add it to CARRIES and to NOTICE's "
                   "inventory; if the mention is only historical, add it to "
                   "HISTORICAL." % name)

    for name in sorted(set(CARRIES) - found):
        bad.append("%s is listed as carrying \"%s\" but no longer mentions "
                   "XADMaster or macutils at all. If it has shed its last "
                   "citation, move it to HISTORICAL, out of NOTICE's "
                   "inventory and out of OPEN_ITEMS.md." % (name, CARRIES[name]))

    for name in sorted(HISTORICAL - found):
        bad.append("%s is listed as historical but mentions neither "
                   "reference; drop it from HISTORICAL." % name)

    # NOTICE is the inventory's home, so every carrier must appear in it.
    notice = NOTICE.read_text()
    for name in sorted(CARRIES):
        if name not in notice:
            bad.append("NOTICE does not name src/%s, which carries \"%s\"."
                       % (name, CARRIES[name]))

    if "--selftest" in sys.argv:
        # A checker that matched nothing would pass forever.
        probe = found - set(CARRIES) - HISTORICAL
        if probe:
            raise SystemExit("check_provenance: SELFTEST: tree is already "
                             "unclassified, fix that first")
        if "unc_lzdyn.c" not in found:
            raise SystemExit("check_provenance: SELFTEST FAILED — the scan "
                             "found no mention in unc_lzdyn.c, so it is not "
                             "scanning anything")
        print("check_provenance: selftest ok (scan sees %d files)" % len(found))

    if bad:
        for b in bad:
            print("check_provenance: FAIL: " + b)
        return 1

    print("check_provenance: ok (%d carrying, %d historical, all in NOTICE)"
          % (len(CARRIES), len(HISTORICAL)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

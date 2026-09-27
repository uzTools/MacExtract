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
file in CARRIES whose last Source-marked citation goes fails too — that
is a row that can leave, and the point of the check is that nobody has
to notice it by hand.

LIVENESS IS THE SOURCE: MARKER, NOT THE MENTION, and that distinction
is the whole check.  The first version of this script tested for a
mention, and within the hour `src/fmt_mime.c` shed its last citation,
kept one historical sentence, and passed — failing in exactly the
direction the script was written to catch (BLOCKERS.md).

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
    "fmt_packit.c":     "the resync strategy (macutils pit.c) and both ciphers",
    "fmt_sit.c":        "three method-8 rules no specimen reaches",
    "fmt_sit5.c":       "the encrypted header's bit 5, which nothing here sets",
    "fmt_dd.c":         "the DDAR 0x20 raw-fork shape",
    "fmt_arc.c":        "Crunch 5/6/7 and Crush, and the method numbers",
    "unc_crypt.c":      "StuffItDES, StuffIt 5's hash, PackIt's keytr1, ARC's garble",
    "fmt_binhex.c":     "macutils hexbin's rules about text that has been mailed",
    "fmt_uu.c":         "the same, plus UUTool's MU layout (macutils mu.c)",
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
    "fmt_binhex_priv.h", "sit6_tables.h", "fmt_mime.c", "fmt_lzh.c",
}

MENTION = re.compile(r"XAD|macutils")

# A LIVE citation is Source-marked. That is NOTICE's own stated
# convention ("Files that transcribe XADMaster code carry a
# 'Source: reference/XADMaster/<file>' comment"), and it is the only
# mechanical way to tell a citation from a note saying what a file no
# longer owes. Checking MENTIONS instead misses the case that matters:
# on 2026-09-27 `src/fmt_mime.c` shed its last live citation and kept a
# historical sentence, and a mention-based check passed it — the check
# was wrong in exactly the direction it was built to catch.
LIVE = re.compile(r"Source:[^\n]*(XAD|macutils)")


def main():
    found = set()      # mentions either reference at all
    live = set()       # carries a Source-marked citation
    for p in sorted(SRC.glob("*.c")) + sorted(SRC.glob("*.h")):
        text = p.read_text(errors="replace")
        if MENTION.search(text):
            found.add(p.name)
        if LIVE.search(text):
            live.add(p.name)

    bad = []

    for name in sorted(found - set(CARRIES) - HISTORICAL):
        bad.append("%s mentions a reference and is in neither set. If it "
                   "borrows something, add it to CARRIES and to NOTICE's "
                   "inventory; if the mention is only historical, add it to "
                   "HISTORICAL." % name)

    for name in sorted(set(CARRIES) - live):
        bad.append("%s is listed as carrying \"%s\" but has no Source-marked "
                   "citation left. If it has shed its last, move it to "
                   "HISTORICAL, out of NOTICE's inventory and out of "
                   "OPEN_ITEMS.md; if it still borrows something, mark the "
                   "citation with a Source: line." % (name, CARRIES[name]))

    for name in sorted(live - set(CARRIES)):
        bad.append("%s carries a Source-marked citation but is not in "
                   "CARRIES. Inventory it in NOTICE." % name)

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
        # Liveness must be strictly narrower than mention, or the check
        # has collapsed back into the version that missed fmt_mime.c.
        if not (live < found):
            raise SystemExit("check_provenance: SELFTEST FAILED — every "
                             "mention counts as live, so a file that sheds "
                             "its last citation and keeps a historical note "
                             "would pass")
        print("check_provenance: selftest ok (%d mention, %d carry a live "
              "Source: citation)" % (len(found), len(live)))

    if bad:
        for b in bad:
            print("check_provenance: FAIL: " + b)
        return 1

    print("check_provenance: ok (%d carrying a live citation, %d historical, "
          "all in NOTICE)" % (len(CARRIES), len(HISTORICAL)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

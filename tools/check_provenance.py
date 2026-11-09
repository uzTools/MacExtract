#!/usr/bin/env python3
"""Keep NOTICE's inventory of borrowed code honest, mechanically.

NOTICE is the single home for "what in this engine is still XADMaster's,
libxad's or macutils'" (CLAUDE.md, *one home per finding*).  A prose list goes
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

THE LICENCE FOLLOWS THE CODE, NOT THE FACT (DECISIONS.md 2026-11-08, *the
code we wrote*). Everything this project wrote is 0BSD, the tree's default
in LICENSE. A file holding code transcribed from one of these references
keeps LGPL-2.1-or-later and says so in an SPDX-License-Identifier line:
CODE below, a subset of CARRIES. A file that carries only facts — a
layout, an offset, a rule — is 0BSD; CARRIES still lists it, because
leaving XADMaster is about where the knowledge came from, not only the
licence. Under src/ the LGPL line must be in exactly the CODE files.
Outside src/ a file with the line must have a live citation and be named
in NOTICE, so no file stays LGPL after its last citation goes.

What this cannot see: whether a citation is a fact or code — CODE is a
human reading, recorded once; a borrowing nobody marked with a Source:
line; and a citation of a reference other than these three.
"""

import re
import sys
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
NOTICE = ROOT / "NOTICE"

# Files that still carry somebody else's code or facts, and the one-line
# summary of WHAT. The detail is NOTICE's; OPEN_ITEMS.md holds only the
# ones with a route left.
CARRIES = {
    "unc_lzdyn.c":      "-lh2- and -lh3- (libxad's LhA.c), whole file",
    "fmt_sit.c":        "three method-8 rules no specimen reaches (libxad's SIT_mw)",
    "sit14.c":          "StuffIt 5's method 14, the whole file (libxad's SIT_14)",
    "fmt_dd.c":         "the per-method rules and the DDAR 0x20 raw-fork shape (libxad's DiskDoubler.c)",
    "fmt_arc.c":        "Crunch 5/6/7 and Crush, and the method numbers",
    "unc_lzah.c":       "the -lh1-/method-5 window preload (resetLZSSHandle)",
    "fmt_macbinary_probe.c": "the CRC-16/0xA001 fallback and the nonzero-date test",
    "fmt_applesingle.c": "the byte-swapped header",
    "fmt_sitseg.c":     "the whole StuffIt split header",
    "fmt_sitseg_probe.c": "the StuffIt split header's offsets",
    "fmt_dd_probe.c":   "the zero header CRC old files carry (XADDiskDoublerParser.m)",
    "unc_internal.h":   "the LZAH preload",
    "fmt_hecx.c":       "BinHex before 4.0 and .dl, the whole decoder (hexbin's hecx.c, dl.c)",
    "fmt_binhex_probe.c": "the .hex/.hcx header-line rule and the .dl first line (hexbin's hecx.c, hexbin.c)",
    "unc_sidecar.c":    "which names are Mac OS X sidecars, and the pairing rule",
    "unc_segment.c":    "the spanned-zip and .NNN split naming rules",
}

# The CARRIES files whose borrowing is CODE, transcribed, rather than facts:
# these, and only these, are LGPL-2.1-or-later (read 2026-11-08; NOTICE).
CODE = {
    "unc_lzdyn.c",  # libxad's -lh2-/-lh3-, the whole file
    "sit14.c",      # libxad's SIT_14, the whole file
    "fmt_hecx.c",   # hexbin's hecx.c and dl.c, the whole decoder
    "fmt_arc.c",    # XADMaster's Crunch and Crush handles
}

# Mentions a reference only to say what it no longer owes, or to
# compare against it. Nothing here is borrowed.
HISTORICAL = {
    "fmt_exo.c", "fmt_tar_probe.c", "fmt_now_probe.c",
    "fmt_superdisk.c",
    "fmt_uu.c", "fmt_binhex.c",
    "sit_arsenic.c", "unc_encinfo.c", "unc_huffman.c", "crypt_tables.h",
    "fmt_cpt.c", "fmt_cptseg.c", "fmt_now.c", "unc_util.c",
    "fmt_binhex_priv.h", "sit6_tables.h", "fmt_mime.c", "fmt_lzh.c",
    "fmt_packit.c", "unc_shrink.c", "fmt_sit5.c",
    "unc_crypt.c",  # StuffIt 5's key and ARC's garble left 2026-11-09
}

MENTION = re.compile(r"XAD|libxad|macutils")
# The tag opens a comment line (" * ", "# ", "/* "), so prose that quotes
# it, this file's included, is not a tag.
LGPL_TAG = re.compile(r"^[ \t/*#]*SPDX-License-Identifier:[ \t]*"
                      r"LGPL-2\.1-or-later[ \t]*(\*/)?[ \t]*$", re.M)
# Outside src/: every tracked text file but the fetched, vendored and
# shipped trees, and the Markdown and NOTICE, which cite rather than carry.
OUTSIDE_SKIP = re.compile(r"^(src|reference|fixtures|third_party|dist)/|\.md$|^NOTICE$")

# A LIVE citation is Source-marked. That is NOTICE's own stated
# convention ("Files that transcribe XADMaster code carry a
# 'Source: reference/XADMaster/<file>' comment"), and it is the only
# mechanical way to tell a citation from a note saying what a file no
# longer owes. Checking MENTIONS instead misses the case that matters:
# on 2026-09-27 `src/fmt_mime.c` shed its last live citation and kept a
# historical sentence, and a mention-based check passed it — the check
# was wrong in exactly the direction it was built to catch.
LIVE = re.compile(r"Source:[^\n]*(XAD|libxad|macutils)")


def tracked_outside_src():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split("\n")
    me = pathlib.Path(__file__).resolve()
    # This file quotes a Source: line in its own docstring.
    return [ROOT / f for f in out
            if f and not OUTSIDE_SKIP.search(f) and (ROOT / f).resolve() != me]


def main():
    found = set()      # mentions either reference at all
    live = set()       # carries a Source-marked citation
    tagged = set()     # carries the LGPL tag
    for p in sorted(SRC.glob("*.c")) + sorted(SRC.glob("*.h")):
        text = p.read_text(errors="replace")
        if MENTION.search(text):
            found.add(p.name)
        if LIVE.search(text):
            live.add(p.name)
        if LGPL_TAG.search(text):
            tagged.add(p.name)

    out_live, out_tagged = set(), set()
    for p in tracked_outside_src():
        try:
            text = p.read_text(errors="replace")
        except (IsADirectoryError, FileNotFoundError):
            continue
        rel = str(p.relative_to(ROOT))
        if LIVE.search(text):
            out_live.add(rel)
        if LGPL_TAG.search(text):
            out_tagged.add(rel)

    bad = []

    for name in sorted(CODE - set(CARRIES)):
        bad.append("src/%s is in CODE but not in CARRIES." % name)
    for name in sorted(CODE - tagged):
        bad.append("src/%s carries transcribed code but has no "
                   "\"SPDX-License-Identifier: LGPL-2.1-or-later\" line."
                   % name)
    for name in sorted(tagged - CODE):
        bad.append("src/%s says LGPL-2.1-or-later but is not in CODE; what "
                   "this project wrote, facts included, is 0BSD." % name)
    for rel in sorted(out_tagged - out_live):
        bad.append("%s says LGPL-2.1-or-later but cites nothing it carries; "
                   "what this project wrote is 0BSD." % rel)

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
    for rel in sorted(out_tagged):
        if rel not in notice:
            bad.append("NOTICE does not name %s, which is LGPL-2.1-or-later."
                       % rel)

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
        # The licence scan must see the carriers, or it passes on nothing.
        if not tagged or not out_live:
            raise SystemExit("check_provenance: SELFTEST FAILED — the "
                             "licence scan found no LGPL line under src/ or "
                             "no citation outside it, so it reads nothing")
        print("check_provenance: selftest ok (%d mention, %d carry a live "
              "Source: citation, %d outside src/)"
              % (len(found), len(live), len(out_live)))

    if bad:
        for b in bad:
            print("check_provenance: FAIL: " + b)
        return 1

    print("check_provenance: ok (%d carrying a live citation, %d of them code "
          "and LGPL, %d historical, all in NOTICE)"
          % (len(CARRIES), len(CODE), len(HISTORICAL)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

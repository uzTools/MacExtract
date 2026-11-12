#!/usr/bin/env python3
"""Check that every format and scheme the Macintosh build dispatches has a row.

On the Macintosh build with images every reader is found by UncCtx.fmt
(DECISIONS.md 2026-11-11, *the release decided in the bundle*, and
2026-11-12, *the format table that became three bitmaps*): mac/ovl_shim.c's
gRun names the image and entry point, unc_run_file sends three formats to
resident readers instead, and unc_segment_match asks the image gRun names
for a scheme flagged RUN_MATCH. A format with no row reads zero: the
ciphers' image at entry 0, its self-test, which returns 0x4F4B — an error
the shell reports with no name, on the Macintosh only. Nothing on Linux
calls any of it, so no host suite would notice.

What it reads:

  * src/unc_engine.c, UNC_FORMAT_ROWS: every F(format, ..., extractor) row
    is sent to unc_run_file by unc_extract_as, and needs gRun[format] or
    one of unc_run_file's comparisons;
  * src/unc_segment.c, seg_schemes: every row with SEG_READ(reader) is
    sent to unc_run by unc_extract_segments with fmt = the scheme, and
    needs gRun[scheme];
  * src/unc_segid.c, seg_ids, with mac/release_plan.inc.c's gKeepSet: a
    scheme with a match whose set the release reduces to a keep row keeps
    no sniffer, so its gRun row needs RUN_MATCH and must name an image
    that compiles the match (tools/overlay/images.py) and answers
    OVL_SEG_MATCH.

WHAT IT CANNOT SEE: whether a row names the RIGHT entry point (the
emulator tiers and tests/run_overlay_host.sh do); a decoder called by name
from inside the engine with some other fmt (there is none: a direct call
to a DECODER() alias is grepped for below); and tables written in a shape
these regexes do not parse — which fails here as "stopped checking" rather
than passing.

--selftest removes each gRun row, each RUN_MATCH flag and each of
unc_run_file's comparisons in turn, and requires every removal to fail.
Costs no shipped byte: nothing here is compiled.
"""

import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHIM = ROOT / "mac" / "ovl_shim.c"
ENGINE = ROOT / "src" / "unc_engine.c"
SEGMENT = ROOT / "src" / "unc_segment.c"
SEGID = ROOT / "src" / "unc_segid.c"
PLAN = ROOT / "mac" / "release_plan.inc.c"
sys.path.insert(0, str(ROOT / "tools" / "overlay"))
import images  # noqa: E402


def strip_comments(s):
    return re.sub(r"/\*.*?\*/", " ", s, flags=re.S)


def block(text, opener, where, closer="};"):
    i = text.find(opener)
    if i < 0:
        raise SystemExit("check_ovl_rows: %s has no %r — this check has "
                         "stopped checking" % (where, opener))
    j = text.index(closer, i + len(opener))
    return text[i + len(opener):j]


def grun_rows(shim):
    body = block(shim, "gRun[UNC_FORMAT__COUNT] = {", "mac/ovl_shim.c")
    out = {}
    for m in re.finditer(r"\[(UNC_FORMAT_\w+)\]\s*=\s*RUN\(\s*(OVL_ID_\w+)"
                         r"\s*,\s*(\w+)\s*,([^)]*)\)", body):
        out[m.group(1)] = (m.group(2), m.group(4))
    return out


def problems(shim_text):
    shim = strip_comments(shim_text)
    out = []
    aliases = set(re.findall(r"^DECODER\((\w+)\)", shim, flags=re.M))
    grun = grun_rows(shim)
    here = set(re.findall(r"c->fmt\s*==\s*(UNC_FORMAT_\w+)",
                          block(shim, "int unc_run_file(UncCtx *c)",
                                "mac/ovl_shim.c", "\n}")))

    rows = block(strip_comments(ENGINE.read_text()),
                 "#define UNC_FORMAT_ROWS(F, S)", "src/unc_engine.c",
                 "\n\n")
    files = re.findall(r"\bF\(\s*(UNC_FORMAT_\w+)\s*,\s*\"[^\"]*\"\s*,"
                       r"\s*\d\s*,\s*(\w+)\s*\)", rows)
    sets = re.findall(r"\bS\(\s*(UNC_FORMAT_\w+)\s*,", rows)
    schemes = re.findall(r"\{\s*(UNC_FORMAT_\w+)\s*,[^{}]*?"
                         r"SEG_READ\(\s*(\w+)\s*\)",
                         block(strip_comments(SEGMENT.read_text()),
                               "seg_schemes[] = {", "src/unc_segment.c"))
    ids = re.findall(r"\{\s*(UNC_FORMAT_\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\}",
                     block(strip_comments(SEGID.read_text()),
                           "seg_ids[] = {", "src/unc_segid.c"))
    keep = set(re.findall(r"\[\s*(UNC_FORMAT_\w+)\s*\]\s*=\s*KEEP\(",
                          block(strip_comments(PLAN.read_text()),
                                "gKeepSet[UNC_FORMAT__COUNT] = {",
                                "mac/release_plan.inc.c")))
    # A parse that finds next to nothing is a parse that broke.
    if len(aliases) < 20 or len(files) < 30 or len(sets) < 4 or \
            len(schemes) < 4 or len(grun) < 25 or len(here) < 3 or \
            len(ids) < 6 or len(keep) < 20:
        out.append("parsed %d aliases, %d file rows, %d set rows, %d "
                   "readers of a set, %d gRun rows, %d resident readers, "
                   "%d set identities, %d keep rows — this check has "
                   "stopped checking" % (len(aliases), len(files), len(sets),
                                         len(schemes), len(grun), len(here),
                                         len(ids), len(keep)))

    for f, fn in files:
        if f not in grun and f not in here:
            out.append("src/unc_engine.c sends %s (%s) to unc_run_file, and "
                       "mac/ovl_shim.c has no gRun row and no resident "
                       "reader for it" % (f, fn))
    for f, fn in schemes:
        if f not in grun:
            out.append("src/unc_segment.c sends the set %s (%s) to unc_run, "
                       "and mac/ovl_shim.c's gRun has no row for it"
                       % (f, fn))

    # Where each match is defined, and which images compile that file.
    defined = {}
    for p in sorted((ROOT / "src").glob("*.c")):
        for m in re.finditer(r"^int\s+(unc_\w+_match)\s*\(",
                             strip_comments(p.read_text()), flags=re.M):
            defined[m.group(1)] = "src/" + p.name
    img_srcs = dict(images.images())
    for scheme, _describe, match in ids:
        if match == "NULL" or scheme not in keep:
            continue
        row = grun.get(scheme)
        if row is None or "RUN_MATCH" not in row[1]:
            out.append("%s's set keeps its keep row and not the sniffer, "
                       "and mac/ovl_shim.c's gRun row for it has no "
                       "RUN_MATCH: its parts would be matched in an image "
                       "the release gave back" % scheme)
            continue
        src = defined.get(match)
        img = row[0]
        if src is None or src not in img_srcs.get(img, ()):
            out.append("%s's gRun row names %s for its match, which does "
                       "not compile %s (%s)" % (scheme, img, match, src))
            continue
        top = [s for s in img_srcs[img] if s.startswith("tools/overlay/")]
        if not any("OVL_SEG_MATCH" in (ROOT / s).read_text() for s in top):
            out.append("%s's gRun row names %s for its match, whose "
                       "dispatch has no OVL_SEG_MATCH" % (scheme, img))

    # The two tables are the only places fmt is set before a decoder runs;
    # a decoder called by name elsewhere in the engine would bypass them.
    for p in sorted((ROOT / "src").glob("*.c")):
        body = strip_comments(p.read_text())
        for fn in aliases:
            for m in re.finditer(r"\b%s\s*\(" % fn, body):
                line = body[body.rfind("\n", 0, m.start()) + 1:
                            body.find("\n", m.start())]
                if re.match(r"\s*int\s+%s\s*\(" % fn, line):
                    continue
                if re.search(r"\b[FS]\(|SEG_READ\(", line):
                    continue           # a row, which this check reads
                out.append("%s calls %s by name: its fmt is not one "
                           "this check reads" % (p.relative_to(ROOT), fn))
    return out


def main():
    text = SHIM.read_text()
    errs = problems(text)
    for e in errs:
        print("check_ovl_rows: " + e)
    if errs:
        return 1
    if "--selftest" in sys.argv[1:]:
        cuts = re.findall(r"^\s*\[UNC_FORMAT_\w+\]\s*=.*\n", text,
                          flags=re.M)
        if len(cuts) < 25:
            print("check_ovl_rows: selftest found %d gRun rows" % len(cuts))
            return 1
        cuts = [(c, "") for c in cuts]
        flags = [m.group(0) for m in
                 re.finditer(r"\[UNC_FORMAT_\w+\][^\n]*RUN_MATCH\)", text)]
        if len(flags) < 2:
            print("check_ovl_rows: selftest found %d RUN_MATCH rows"
                  % len(flags))
            return 1
        cuts += [(f, f.replace(" | RUN_MATCH)", ")")
                     .replace("RUN_MATCH)", "0)")) for f in flags]
        here = re.findall(r"^\s*if \(c->fmt == UNC_FORMAT_\w+\).*\n", text,
                          flags=re.M)
        cuts += [(h, "") for h in here]
        for old, new in cuts:
            if not problems(text.replace(old, new, 1)):
                print("check_ovl_rows: SELFTEST FAILED — %r -> %r was not "
                      "caught" % (old.strip(), new.strip()))
                return 1
        print("check_ovl_rows: selftest — each of %d gRun rows, %d "
              "RUN_MATCH flags and %d resident readers removed, each caught"
              % (len(cuts) - len(flags) - len(here), len(flags), len(here)))
    print("check_ovl_rows: every format and set sent to ovl_run has a gRun "
          "row, and every set matched outside the sniffer its RUN_MATCH")
    return 0


if __name__ == "__main__":
    sys.exit(main())

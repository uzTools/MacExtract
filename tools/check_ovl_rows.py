#!/usr/bin/env python3
"""Check that every format and scheme the Macintosh build dispatches has a row.

On the Macintosh build with images every reader is found by UncCtx.fmt
(DECISIONS.md 2026-11-11, *the release decided in the bundle*, and
2026-11-12, *the format table that became three bitmaps*): mac/ovl_shim.c's
gRun names the image and entry point, unc_run_file sends one format to
resident readers instead, and unc_segment_match asks the image gRun names
for a scheme flagged RUN_MATCH. A format with no row reads zero: the
ciphers' image at entry 0, its self-test, which returns 0x4F4B — an error
the shell reports with no name, on the Macintosh only. Nothing on Linux
calls any of it, so no host suite would notice.

What it reads: src/unc_formats.h, through tools/unc_formats.py, and
mac/ovl_shim.c's unc_run_file.

  * every FILE or ENVELOPE format is sent to unc_run_file by
    unc_extract_as, and needs a run row or one of unc_run_file's
    comparisons; one with a run row needs its extractor among the
    DECODER aliases, which is what reaches ovl_run;
  * every JOIN_READ scheme is sent to unc_run by unc_extract_segments with
    fmt = the scheme, and needs a run row, and its reader among the
    aliases;
  * every alias is some format's or scheme's: one left behind by a
    removal is a name nothing dispatches;
  * a SEGID with a match whose set the release reduces to a keep row keeps
    no sniffer, so its run row needs RUN_MATCH and must name an image that
    compiles the match (tools/overlay/images.py) and answers
    OVL_SEG_MATCH.

WHAT IT CANNOT SEE: whether a row names the RIGHT entry point (the
emulator tiers and tests/run_overlay_host.sh do); a decoder called by name
from inside the engine with some other fmt (there is none: a direct call
to a DECODER() alias is grepped for below); and a list written in a shape
tools/unc_formats.py does not parse — which fails there rather than
passing.

--selftest removes each run row, each RUN_MATCH flag, each alias and each
of unc_run_file's comparisons in turn, and requires every removal to fail.
Costs no shipped byte: nothing here is compiled.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHIM = ROOT / "mac" / "ovl_shim.c"
HEADER = ROOT / "src" / "unc_formats.h"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "overlay"))
import images  # noqa: E402
import unc_formats  # noqa: E402


def strip_comments(s):
    return re.sub(r"/\*.*?\*/", " ", s, flags=re.S)


def block(text, opener, where, closer="};"):
    i = text.find(opener)
    if i < 0:
        raise SystemExit("check_ovl_rows: %s has no %r — this check has "
                         "stopped checking" % (where, opener))
    j = text.index(closer, i + len(opener))
    return text[i + len(opener):j]


def problems(shim_text, hdr_text):
    shim = strip_comments(shim_text)
    out = []
    fmts = unc_formats.formats(hdr_text)
    aliases = set(unc_formats.decoders(hdr_text))
    ids = unc_formats.segids(hdr_text)
    grun = {f.id: f.run for f in fmts if f.run}
    keep = {f.id for f in fmts if f.keep is not None}
    here = set(re.findall(r"c->fmt\s*==\s*(UNC_FORMAT_\w+)",
                          block(shim, "int unc_run_file(UncCtx *c)",
                                "mac/ovl_shim.c", "\n}")))
    if "UNC_FORMATS(GRUN_ROW)" not in shim or \
            "UNC_DECODERS(DECODER)" not in shim:
        out.append("mac/ovl_shim.c no longer expands gRun and the aliases "
                   "from src/unc_formats.h — this check has stopped "
                   "checking")
    if len(here) < 1:
        out.append("parsed %d resident readers in unc_run_file — this check "
                   "has stopped checking" % len(here))

    used = set()
    for f in fmts:
        if f.kind == "PART":
            continue
        if f.id in here:
            continue
        if f.run is None:
            out.append("src/unc_formats.h: %s (%s) is sent to unc_run_file, "
                       "and has no run row and no resident reader in "
                       "mac/ovl_shim.c" % (f.id, f.extract))
        elif f.extract not in aliases:
            out.append("src/unc_formats.h: %s's extractor %s reaches no "
                       "image: it is not a DECODER" % (f.id, f.extract))
        used.add(f.extract)
    for f in fmts:
        if not f.join or f.join[0] != "READ":
            continue
        if f.run is None:
            out.append("src/unc_formats.h: the set %s (%s) is sent to "
                       "unc_run, and has no run row" % (f.id, f.join[2]))
        if f.join[2] not in aliases:
            out.append("src/unc_formats.h: the set %s's reader %s reaches "
                       "no image: it is not a DECODER" % (f.id, f.join[2]))
        used.add(f.join[2])
    for fn in sorted(aliases - used):
        out.append("src/unc_formats.h: DECODER(%s) is no format's extractor "
                   "nor any set's reader" % fn)

    # Where each match is defined, and which images compile that file.
    defined = {}
    for p in sorted((ROOT / "src").glob("*.c")):
        for m in re.finditer(r"^int\s+(unc_\w+_match)\s*\(",
                             strip_comments(p.read_text()), flags=re.M):
            defined[m.group(1)] = "src/" + p.name
    img_srcs = dict(images.images())
    for scheme, _describe, match in ids:
        if match is None or scheme not in keep:
            continue
        row = grun.get(scheme)
        if row is None or "RUN_MATCH" not in row[2]:
            out.append("%s's set keeps its keep row and not the sniffer, "
                       "and its run row has no RUN_MATCH: its parts would be "
                       "matched in an image the release gave back" % scheme)
            continue
        src = defined.get(match)
        img = row[0]
        if src is None or src not in img_srcs.get(img, ()):
            out.append("%s's run row names %s for its match, which does "
                       "not compile %s (%s)" % (scheme, img, match, src))
            continue
        top = [s for s in img_srcs[img] if s.startswith("tools/overlay/")]
        if not any("OVL_SEG_MATCH" in (ROOT / s).read_text() for s in top):
            out.append("%s's run row names %s for its match, whose "
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
                out.append("%s calls %s by name: its fmt is not one "
                           "this check reads" % (p.relative_to(ROOT), fn))
    return out


def main():
    shim, hdr = SHIM.read_text(), HEADER.read_text()
    errs = problems(shim, hdr)
    for e in errs:
        print("check_ovl_rows: " + e)
    if errs:
        return 1
    if "--selftest" in sys.argv[1:]:
        hcuts = [(m.group(0), "NORUN") for m in
                 re.finditer(r"\bRUN\(OVL_ID_\w+,[^)]*\)", hdr)]
        flags = [(m.group(0), m.group(0).replace(" | RUN_MATCH", "")
                  .replace("RUN_MATCH", "0")) for m in
                 re.finditer(r"\bRUN\(OVL_ID_\w+,[^)]*RUN_MATCH[^)]*\)",
                             hdr)]
        decs = [(m.group(0), "") for m in
                re.finditer(r"DECODER\(\w+\)", hdr)
                if not m.group(0).startswith("DECODER(fn")]
        here = re.findall(r"^\s*if \(c->fmt == UNC_FORMAT_\w+\).*\n", shim,
                          flags=re.M)
        if len(hcuts) < 25 or len(flags) < 2 or len(decs) < 20 or \
                len(here) < 1:
            print("check_ovl_rows: selftest found %d run rows, %d RUN_MATCH "
                  "flags, %d aliases, %d resident readers"
                  % (len(hcuts), len(flags), len(decs), len(here)))
            return 1
        for old, new in hcuts + flags + decs:
            if not problems(shim, hdr.replace(old, new, 1)):
                print("check_ovl_rows: SELFTEST FAILED — %r -> %r was not "
                      "caught" % (old.strip(), new.strip()))
                return 1
        for old in here:
            if not problems(shim.replace(old, "", 1), hdr):
                print("check_ovl_rows: SELFTEST FAILED — removing %r was not "
                      "caught" % old.strip())
                return 1
        print("check_ovl_rows: selftest — each of %d run rows, %d RUN_MATCH "
              "flags, %d aliases and %d resident readers removed, each "
              "caught" % (len(hcuts), len(flags), len(decs), len(here)))
    print("check_ovl_rows: every format and set sent to ovl_run has a run "
          "row and an alias, every alias a format, and every set matched "
          "outside the sniffer its RUN_MATCH")
    return 0


if __name__ == "__main__":
    sys.exit(main())

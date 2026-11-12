#!/usr/bin/env python3
"""Check that every format sent to mac/ovl_shim.c's ovl_run has a row in gRun.

On the Macintosh build every unc_*_extract name is an alias of ovl_run, which
finds the decoder's image by UncCtx.fmt in gRun (DECISIONS.md 2026-11-11,
*the release decided in the bundle*). A format with no row reads zero: the
ciphers' image at entry 0, its self-test, which returns 0x4F4B — an error the
shell reports with no name, on the Macintosh only. Nothing on Linux calls
ovl_run, so no host suite would notice.

The formats that reach ovl_run are UncCtx.fmt at the call, which is set in
two places, and this reads both tables:

  * src/unc_engine.c, unc_formats: unc_extract_as sets fmt to the row's
    format and calls the row's extractor;
  * src/unc_segment.c, seg_schemes: unc_extract_segments sets fmt to the
    scheme and calls the scheme's reader.

Every (format, extractor) pair whose extractor is a DECODER() alias in
mac/ovl_shim.c needs gRun[format].

WHAT IT CANNOT SEE: whether a row names the RIGHT image and entry point
(the emulator tiers and tests/run_overlay_host.sh do); a decoder called by
name from inside the engine with some other fmt (there is none: a direct
call is grepped for below); and tables written in a shape these regexes do
not parse — which fails here as "stopped checking" rather than passing.

--selftest removes each gRun row in turn and requires every removal to fail.
Costs no shipped byte: nothing here is compiled.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHIM = ROOT / "mac" / "ovl_shim.c"
ENGINE = ROOT / "src" / "unc_engine.c"
SEGMENT = ROOT / "src" / "unc_segment.c"


def strip_comments(s):
    return re.sub(r"/\*.*?\*/", " ", s, flags=re.S)


def block(text, opener, where):
    i = text.find(opener)
    if i < 0:
        raise SystemExit("check_ovl_rows: %s has no %r — this check has "
                         "stopped checking" % (where, opener))
    j = text.index("};", i)
    return text[i + len(opener):j]


def rows_of(text, opener, where):
    """Each top-level {...} of the table, as its comma-separated fields."""
    body = block(text, opener, where)
    return [[f.strip() for f in r.split(",")]
            for r in re.findall(r"\{([^{}]*)\}", body)]


def problems(shim_text):
    shim = strip_comments(shim_text)
    aliases = set(re.findall(r"^DECODER\((\w+)\)", shim, flags=re.M))
    grun = set(re.findall(r"\[(UNC_FORMAT_\w+)\]\s*=",
                          block(shim, "gRun[UNC_FORMAT__COUNT] = {",
                                "mac/ovl_shim.c")))
    sends = []
    for r in rows_of(strip_comments(ENGINE.read_text()),
                     "unc_formats[] = {", "src/unc_engine.c"):
        sends.append((r[0], r[-1], "src/unc_engine.c, unc_formats"))
    n_engine = len(sends)
    for r in rows_of(strip_comments(SEGMENT.read_text()),
                     "seg_schemes[] = {", "src/unc_segment.c"):
        sends.append((r[0], r[-1], "src/unc_segment.c, seg_schemes"))
    n_seg = len(sends) - n_engine

    out = []
    used = [(f, fn, w) for f, fn, w in sends if fn in aliases]
    # A parse that finds next to nothing is a parse that broke.
    if len(aliases) < 20 or n_engine < 20 or n_seg < 5 or len(used) < 25:
        out.append("parsed %d aliases, %d engine rows, %d schemes, %d "
                   "dispatched pairs — this check has stopped checking"
                   % (len(aliases), n_engine, n_seg, len(used)))
    for f, fn, w in used:
        if f not in grun:
            out.append("%s sends %s to %s, an alias of ovl_run, and "
                       "mac/ovl_shim.c's gRun has no row for it" % (w, f, fn))
    # The two tables are the only places fmt is set before a decoder runs;
    # a decoder called by name elsewhere in the engine would bypass them.
    for p in sorted((ROOT / "src").glob("*.c")):
        body = strip_comments(p.read_text())
        for fn in aliases:
            for m in re.finditer(r"\b%s\s*\(" % fn, body):
                line = body[body.rfind("\n", 0, m.start()) + 1:
                            body.find("\n", m.start())]
                if not re.match(r"\s*int\s+%s\s*\(" % fn, line):
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
        rows = re.findall(r"^\s*\[UNC_FORMAT_\w+\]\s*=.*\n", text, flags=re.M)
        if len(rows) < 25:
            print("check_ovl_rows: selftest found %d gRun rows" % len(rows))
            return 1
        for row in rows:
            if not problems(text.replace(row, "", 1)):
                print("check_ovl_rows: SELFTEST FAILED — removing %r "
                      "was not caught" % row.strip())
                return 1
        print("check_ovl_rows: selftest — each of %d rows removed, each "
              "caught" % len(rows))
    print("check_ovl_rows: every format sent to ovl_run has a gRun row")
    return 0


if __name__ == "__main__":
    sys.exit(main())

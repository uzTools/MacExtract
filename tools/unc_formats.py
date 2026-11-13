#!/usr/bin/env python3
"""unc_formats.py — src/unc_formats.h, read once for every tool that needs it.

src/unc_formats.h is where a format is registered: one FORMAT row, its
probe's place in the sniff order, its set identity and its decoder alias.
The C side expands those lists into every per-format table; the tools that
model or check those tables (check_ovl_rows.py, run_tiers.py,
stack_depth.py) read the same lists through this module rather than
parsing each table's expansion, so there is one parser and one shape.

    formats()  -> [Format], in the list's order
    probes()   -> [(fn, answers)], in the sniff order
    segids()   -> [(id, describe, match or None)], in describe order
    decoders() -> [fn]

A list that parses to nearly nothing raises SystemExit: a parse that broke
must not read as a table that emptied.

Run directly, it prints the four lists.
"""

import collections
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEADER = ROOT / "src" / "unc_formats.h"

Format = collections.namedtuple(
    "Format", "id name kind extract run keep join")
# run:  None, or (image, entry, flags)   flags a string, "0" for none
# keep: None, or flags                   a string, "0" for none
# join: None, or ("READ", flags, reader) or ("EMIT", flags, None)


def _strip_comments(s):
    return re.sub(r"/\*.*?\*/", " ", s, flags=re.S)


def list_body(name, text=None):
    """The body of `#define name(X) ...`, comments removed, continuations
    joined."""
    if text is None:
        text = HEADER.read_text(encoding="utf-8")
    text = _strip_comments(text)
    m = re.search(r"^#define %s\(\w+\)[ \t]*\\\n" % name, text, re.M)
    if not m:
        raise SystemExit("unc_formats.py: src/unc_formats.h has no %s list"
                         % name)
    out = []
    for line in text[m.end():].split("\n"):
        if line.rstrip().endswith("\\"):
            out.append(line.rstrip()[:-1])
        else:
            out.append(line)
            break
    return " ".join(out)


def calls(body, macro):
    """Every macro(...) call in body, as a list of its top-level arguments."""
    out = []
    i = 0
    while True:
        m = re.compile(r"\b%s\s*\(" % macro).search(body, i)
        if not m:
            return out
        depth, j, args, start = 1, m.end(), [], m.end()
        while depth:
            c = body[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif c == "," and depth == 1:
                args.append(body[start:j].strip())
                start = j + 1
            j += 1
        args.append(body[start:j - 1].strip())
        out.append([" ".join(a.split()) for a in args])
        i = j


def _inner(col, tag):
    """`TAG(a, b)` -> [a, b]; None if col is not that tag."""
    if not col.startswith(tag + "("):
        return None
    return calls(col, tag)[0]


def _str(s):
    m = re.fullmatch(r'"([^"]*)"', s)
    if not m:
        raise SystemExit("unc_formats.py: a name that is not a string: %s"
                         % s)
    return m.group(1)


def formats(text=None):
    out = []
    for a in calls(list_body("UNC_FORMATS", text), "FORMAT"):
        if len(a) != 7:
            raise SystemExit("unc_formats.py: a FORMAT row with %d columns: "
                             "%s" % (len(a), a))
        fid, name, kind, extract, run, keep, join = a
        if kind not in ("FILE", "ENVELOPE", "PART"):
            raise SystemExit("unc_formats.py: %s's kind is %s" % (fid, kind))
        r = None if run == "NORUN" else tuple(_inner(run, "RUN") or ())
        if r is not None and len(r) != 3:
            raise SystemExit("unc_formats.py: %s's run is %s" % (fid, run))
        k = None if keep == "NOKEEP" else (_inner(keep, "KEEP") or [None])[0]
        if keep != "NOKEEP" and k is None:
            raise SystemExit("unc_formats.py: %s's keep is %s" % (fid, keep))
        if join == "NOJOIN":
            j = None
        elif _inner(join, "JOIN_READ"):
            fl, rd = _inner(join, "JOIN_READ")
            j = ("READ", fl, rd)
        elif _inner(join, "JOIN_EMIT"):
            j = ("EMIT", _inner(join, "JOIN_EMIT")[0], None)
        else:
            raise SystemExit("unc_formats.py: %s's join is %s" % (fid, join))
        out.append(Format(fid, _str(name), kind,
                          None if extract == "0" else extract, r, k, j))
    if len(out) < 30:
        raise SystemExit("unc_formats.py: parsed %d FORMAT rows — the list "
                         "changed shape" % len(out))
    return out


def probes(text=None):
    out = [tuple(a) for a in calls(list_body("UNC_PROBES", text), "PROBE")]
    if len(out) < 25 or any(a[1] not in ("ARCHIVE", "ENVELOPE")
                            for a in out):
        raise SystemExit("unc_formats.py: the UNC_PROBES list changed shape")
    return out


def segids(text=None):
    out = [(a[0], a[1], None if a[2] == "0" else a[2])
           for a in calls(list_body("UNC_SEGIDS", text), "SEGID")]
    if len(out) < 5:
        raise SystemExit("unc_formats.py: the UNC_SEGIDS list changed shape")
    return out


def decoders(text=None):
    out = [a[0] for a in calls(list_body("UNC_DECODERS", text), "DECODER")]
    if len(out) < 20:
        raise SystemExit("unc_formats.py: the UNC_DECODERS list changed "
                         "shape")
    return out


if __name__ == "__main__":
    for f in formats():
        print(f)
    for p in probes():
        print("PROBE", *p)
    for s in segids():
        print("SEGID", *s)
    print("DECODER", " ".join(decoders()))

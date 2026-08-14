#!/usr/bin/env python3
"""Documentation invariants that would otherwise go stale silently.

Two of them, both cheap enough to run first in ci.sh:

1. DECISIONS.md's Contents index lists every `## ` entry, in order. An index
   nobody regenerates is worse than no index, because it reads as complete.
   `--fix` rewrites it from the headings.
2. No document cites another document by line number. Line numbers drift
   without anyone noticing; CLAUDE.md requires citing the section by name.
   Source files (`foo.c:41`) are fine - only `*.md:NN` is checked.
3. The version agrees in all three places it is written: UNC_VERSION in
   include/unclassic.h (the source of truth, which `unclassic --version`
   prints), the download section of README.md, and the first line of
   dist/README.txt, which make_dist.sh generates from the header. That
   constant sat at "0.4.0" through four releases because nothing read it
   and nothing checked it; a reader who sees a stale version on the
   release page now knows the publish step did not run, which is the one
   thing about a release this environment cannot check for itself.
"""

import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "DECISIONS.md"
INDEX_HEAD = "## Contents\n"
MD_LINE_CITE = re.compile(r"\b[A-Za-z_][\w./-]*\.md:\d+")


def entries(text):
    return [l[3:].strip() for l in text.split("\n")
            if l.startswith("## ") and l[3:].strip() != "Contents"]


def indexed(text):
    body = text.split(INDEX_HEAD, 1)[1].split("\n---\n", 1)[0]
    return [l[2:].strip() for l in body.split("\n") if l.startswith("- ")]


def check_index(fix):
    text = DECISIONS.read_text()
    want, have = entries(text), indexed(text)
    if want == have:
        return []
    if fix:
        head, rest = text.split(INDEX_HEAD, 1)
        preamble, tail = rest.split("\n---\n", 1)
        keep = "\n".join(l for l in preamble.split("\n")
                         if l and not l.startswith("- "))
        new = "\n".join(f"- {e}" for e in want)
        DECISIONS.write_text(f"{head}{INDEX_HEAD}{keep}\n\n{new}\n\n---\n{tail}")
        print(f"check_docs: rewrote DECISIONS.md index ({len(want)} entries)")
        return []
    missing = [e for e in want if e not in have]
    extra = [e for e in have if e not in want]
    out = ["DECISIONS.md: Contents index is out of date "
           "(run tools/check_docs.py --fix)"]
    out += [f"  not indexed: {e}" for e in missing]
    out += [f"  indexed but gone: {e}" for e in extra]
    if not missing and not extra:
        out.append("  same entries, wrong order")
    return out


VERSION_RE = re.compile(r'#define UNC_VERSION "([0-9][^"]*)"')


def check_version():
    """UNC_VERSION, README.md's download section and dist/README.txt's
    first line must agree."""
    bad = []
    header = (ROOT / "include" / "unclassic.h").read_text()
    m = VERSION_RE.search(header)
    if not m:
        return ["include/unclassic.h: no UNC_VERSION"]
    ver = m.group(1)

    readme = (ROOT / "README.md").read_text()
    if f"**v{ver}**" not in readme:
        bad.append(f"README.md does not state the current version (**v{ver}**)")

    dist = ROOT / "dist" / "README.txt"
    if dist.exists():
        first = dist.read_text().splitlines()[0]
        if f"v{ver}" not in first:
            bad.append(f"dist/README.txt says {first!r}, not v{ver} — "
                       f"run tools/make_dist.sh")
    return bad


def check_citations():
    out = []
    for path in sorted(ROOT.glob("*.md")) + sorted(ROOT.glob("tools/**/*.md")):
        for n, line in enumerate(path.read_text().split("\n"), 1):
            for hit in MD_LINE_CITE.findall(line):
                out.append(f"{path.relative_to(ROOT)}:{n}: cites {hit} by line "
                           "number; cite the section by name")
    return out


def main():
    fix = "--fix" in sys.argv[1:]
    problems = check_index(fix) + check_citations() + check_version()
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        print("check_docs: FAILED", file=sys.stderr)
        return 1
    print("check_docs: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

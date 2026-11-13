#!/usr/bin/env python3
"""check_harnesses.py — every format harness is named by the source it grades.

ci.sh runs every file in tests/harness/ (one loop, the same arguments), so
a harness is registered by being there. What ties one to its format is a
line in the header of that format's source, `Harness: tests/harness/X.py`,
so that removing a format's files shows which harnesses go with them. This
holds both directions:

  * every tests/harness/run_*.py is named by some src/ file's `Harness:`
    line — one nothing names is a test nobody will think to remove;
  * every `Harness:` line names a file that exists — one that does not is a
    harness removed while its format stayed.

    tools/check_harnesses.py              # check
    tools/check_harnesses.py --selftest   # and prove each direction fails
    tools/check_harnesses.py --of PATH    # the source files naming PATH

WHAT IT CANNOT SEE: whether a harness grades the format it is named by, or
grades it well; and the harnesses that are not a format's (the corpus
suites and the cross-cutting ones, which stay in tools/ with lines of
their own in ci.sh).
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS = os.path.join(ROOT, "tests", "harness")
NAMED = re.compile(r"^\s*\*\s*Harness:\s*tests/harness/(run_\w+\.py)\s*$",
                   re.M)


def harnesses():
    return sorted(f for f in os.listdir(HARNESS)
                  if f.startswith("run_") and f.endswith(".py"))


def sources():
    out = {}
    src = os.path.join(ROOT, "src")
    for f in sorted(os.listdir(src)):
        if f.endswith((".c", ".h")):
            out["src/" + f] = open(os.path.join(src, f),
                                   encoding="utf-8").read()
    return out


def named(srcs):
    """harness file -> [source files naming it]"""
    out = {}
    for path, text in srcs.items():
        for h in NAMED.findall(text):
            out.setdefault(h, []).append(path)
    return out


def problems(have, srcs):
    out = []
    n = named(srcs)
    if len(n) < 10:
        return ["%d harnesses named in src/ — this check has stopped "
                "checking" % len(n)]
    for h in have:
        if h not in n:
            out.append("tests/harness/%s is named by no source file: add "
                       "` * Harness: tests/harness/%s` to the header of the "
                       "format it grades" % (h, h))
    for h, where in sorted(n.items()):
        if h not in have:
            out.append("%s names tests/harness/%s, which does not exist"
                       % (", ".join(where), h))
    return out


def main():
    have, srcs = harnesses(), sources()
    if "--of" in sys.argv:
        h = os.path.basename(sys.argv[sys.argv.index("--of") + 1])
        print(", ".join(named(srcs).get(h, ["named by nothing"])))
        return 0
    errs = problems(have, srcs)
    for e in errs:
        print("check_harnesses: " + e)
    if errs:
        return 1
    if "--selftest" in sys.argv:
        # A harness nothing names, and a name with no harness.
        if not problems(have + ["run_selftest_unnamed.py"], srcs):
            print("check_harnesses: SELFTEST FAILED — an unnamed harness "
                  "was not caught")
            return 1
        path, text = next((p, t) for p, t in srcs.items()
                          if NAMED.search(t))
        bent = dict(srcs)
        bent[path] = NAMED.sub("", text, count=1)
        if not problems(have, bent):
            print("check_harnesses: SELFTEST FAILED — a harness whose name "
                  "was removed from %s was not caught" % path)
            return 1
        if not problems([h for h in have if h != NAMED.search(text).group(1)],
                        srcs):
            print("check_harnesses: SELFTEST FAILED — a named harness that "
                  "is missing was not caught")
            return 1
        print("check_harnesses: selftest — an unnamed harness, a removed "
              "name and a missing harness, each caught")
    print("check_harnesses: %d harnesses, each named by the source it grades"
          % len(have))
    return 0


if __name__ == "__main__":
    sys.exit(main())

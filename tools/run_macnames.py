#!/usr/bin/env python3
"""run_macnames.py — what the MACINTOSH shell does to a name it cannot
write as it stands.

    tools/run_macnames.py [--sink build/mac_sink_asan]

The engine cuts a name at `UNC_NAME_MAX` (255) and says so;
`tools/run_names.py` grades the CLI's answer to that. The Mac shell's
answer is different code and had none of its own: `ComponentToStr63`
caps every component at 31 characters — HFS's limit, so this happens to
every long Mac name and not just to remarkable ones — and the collision
that shortening creates is resolved by `BumpName`, off `dupFNErr` from
the File Manager rather than off the engine's flag. Neither had a test
until 2026-08-28, and OPEN_ITEMS.md said the shell did not number
collisions at all, which the first run of this file disproved
(BLOCKERS.md).

The subjects are DiskDoubler archives from `tools/synth_dd.py`, because
the shortening only bites at 31 bytes and the longest name in 932
fixtures is 120 — but no fixture nests deep enough for the ENGINE's cap
either, and both caps have to be reached in one archive shape to see
which one acted.

The code under test is `mac/macextract_mac.c` itself, through the mock
Toolbox of `tests/mac_sink_test.c` (TESTING.md, *The Mac sink*).

**What this cannot see.** A name holding a '/' — legal on HFS, and
carried to the shell as ':' for it to swap back. The mock builds a Linux
path out of the leaf, so such a name cannot be created there at all: the
create fails, `BumpName` cannot fix it, and the run stops. That is the
mock's boundary and not the shell's, so no case here uses one. Nor can
this see anything on screen: the shell reports no shortened name to the
user, which is the open half of the item this file closes.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_dd                                                # noqa: E402

CAP = 255                       # UNC_NAME_MAX
HFS = 31                        # one HFS name


def run(sink, archive, out):
    """(files under `out` as relative paths, exit code)."""
    r = subprocess.run([sink, archive, out], capture_output=True)
    got = {}
    for root, _, files in os.walk(out):
        for f in files:
            p = os.path.join(root, f)
            got[os.path.relpath(p, out)] = open(p, "rb").read()
    return got, r.returncode


def check(problems, cond, msg):
    if not cond:
        problems.append(msg)
    return cond


def case(sink, tmp, name, tree, kind="ddar"):
    p, _ = synth_dd.write_one(tmp, name, tree, kind)
    out = os.path.join(tmp, name + ".out")
    os.mkdir(out)
    return run(sink, p, out)


def collision_case(sink, tmp, problems):
    """Two files whose names are the same for 31 characters and differ
    after. Both must come out — the second under a numbered name, the
    way an 8.3 filesystem numbered what it had to shorten."""
    base = "B" * HFS
    got, rc = case(sink, tmp, "macname-collide",
                   [synth_dd.file(base + "one.txt", data=b"first\n"),
                    synth_dd.file(base + "two.txt", data=b"second\n")])
    check(problems, rc == 0, "collide: exit was %d" % rc)
    check(problems, len(got) == 2,
          "collide: wrote %r, wanted both files" % sorted(got))
    check(problems, sorted(got.values()) == [b"first\n", b"second\n"],
          "collide: the bytes are not the two entries: %r"
          % sorted(got.values()))
    check(problems, any(n.endswith("~1") for n in got),
          "collide: the second name was not numbered: %r" % sorted(got))
    check(problems, all(len(n) <= HFS for n in got),
          "collide: wrote a name longer than an HFS name: %r"
          % [len(n) for n in got])
    return 1


def folder_collision_case(sink, tmp, problems):
    """The same collision between two FOLDERS, where the answer is not
    the same: `EnsureDir` descends into a folder that already exists, so
    two folders shortening alike become one and their contents are
    merged. MEASURED 2026-08-28, and it is what a Mac user would get
    from the Finder; nothing is lost, but the path is not the
    archive's."""
    base = "C" * HFS
    got, rc = case(sink, tmp, "macname-dircollide",
                   [synth_dd.folder(base + "folderA",
                                    [synth_dd.file("x.txt", data=b"in A\n")]),
                    synth_dd.folder(base + "folderB",
                                    [synth_dd.file("y.txt", data=b"in B\n")])])
    check(problems, rc == 0, "dircollide: exit was %d" % rc)
    check(problems, sorted(got) == [base + "/x.txt", base + "/y.txt"],
          "dircollide: wrote %r, wanted both files in one merged folder"
          % sorted(got))
    check(problems, sorted(got.values()) == [b"in A\n", b"in B\n"],
          "dircollide: a merged folder lost a file: %r" % sorted(got.values()))
    return 1


def engine_cap_case(sink, tmp, problems):
    """The other cap, reached the only way a Macintosh format can reach
    it: four 63-byte folders sum to exactly 255, so the engine cuts the
    leaf's path onto the folder's own. The shell then shortens every
    component to 31 — which is why the whole path is short here — and
    the numbering is what keeps the file: without it the create would
    hit the folder."""
    node = synth_dd.file("leaf.txt", data=b"deep\n")
    for _ in range(4):
        node = synth_dd.folder("f" * 63, [node])
    got, rc = case(sink, tmp, "macname-deep", [node])
    check(problems, rc == 0, "deep: exit was %d" % rc)
    check(problems, len(got) == 1 and list(got.values()) == [b"deep\n"],
          "deep: wrote %r, wanted the one file" % sorted(got))
    if got:
        leaf = sorted(got)[0]
        check(problems, leaf.endswith("~1"),
              "deep: the cut path landed on its own folder and was not "
              "numbered: %r" % leaf)
        check(problems, all(len(c) <= HFS for c in leaf.split("/")),
              "deep: wrote a component longer than an HFS name: %r"
              % [len(c) for c in leaf.split("/")])
    return 1


def edge_cases(sink, tmp, problems):
    """Both sides of the 31-character cut, and the name that is nothing
    at all: a zero-length name becomes `_` rather than an unnamed file
    the File Manager would refuse."""
    got, rc = case(sink, tmp, "macname-edge",
                   [synth_dd.file("D" * HFS, data=b"exactly 31\n"),
                    synth_dd.file("E" * (HFS + 9), data=b"forty\n"),
                    synth_dd.file("", data=b"noname\n")])
    check(problems, rc == 0, "edge: exit was %d" % rc)
    check(problems, "D" * HFS in got and got["D" * HFS] == b"exactly 31\n",
          "edge: a 31-character name was not written whole: %r" % sorted(got))
    check(problems, "E" * HFS in got and got["E" * HFS] == b"forty\n",
          "edge: a 40-character name was not cut to 31: %r" % sorted(got))
    check(problems, got.get("_") == b"noname\n",
          "edge: a nameless entry was not written as `_`: %r" % sorted(got))
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sink", default="build/mac_sink_asan")
    args = ap.parse_args()
    if not os.path.exists(args.sink):
        print("macnames: %s absent, skipped" % args.sink)
        return 0

    problems = []
    ran = 0
    tmp = tempfile.mkdtemp()
    try:
        ran += collision_case(args.sink, tmp, problems)
        ran += folder_collision_case(args.sink, tmp, problems)
        ran += engine_cap_case(args.sink, tmp, problems)
        ran += edge_cases(args.sink, tmp, problems)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("MACNAMES FAIL " + p)
    print("macnames: %d case(s) checked, %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

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

Since 2026-08-29 it also grades the LINES of the end-of-run report —
what the Macintosh box says about each name it changed and each entry
that failed on its own. The mock prints them; what they say is the half
that can be wrong quietly.

**What this cannot see.** A name holding a '/' — legal on HFS, and
carried to the shell as ':' for it to swap back. The mock builds a Linux
path out of the leaf, so such a name cannot be created there at all: the
create fails, `BumpName` cannot fix it, and the run stops. That is the
mock's boundary and not the shell's, so no case here uses one. Nor can
this see the BOX: whether those lines are legible, scroll, and save as a
document is a question for an emulated Macintosh (tools/vmac/README.md).
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
    """(files under `out` as relative paths, exit code, report lines).

    The report lines are what the Macintosh box lists at the end of a
    run: the mock prints each one to stderr (tests/mac_sink_test.c), in
    the order the shell recorded them."""
    r = subprocess.run([sink, archive, out], capture_output=True)
    got = {}
    for root, _, files in os.walk(out):
        for f in files:
            p = os.path.join(root, f)
            got[os.path.relpath(p, out)] = open(p, "rb").read()
    lines = [l[len("report: "):]
             for l in r.stderr.decode("mac_roman").splitlines()
             if l.startswith("report: ")]
    return got, r.returncode, lines


def check(problems, cond, msg):
    if not cond:
        problems.append(msg)
    return cond


def case(sink, tmp, name, tree, kind="ddar", corrupt=None):
    p, _ = synth_dd.write_one(tmp, name, tree, kind)
    if corrupt:
        b = bytearray(open(p, "rb").read())
        i = b.find(corrupt)
        assert i > 0, "the payload to corrupt is not in the archive"
        b[i] ^= 0x01                  # one bit: the checksum, nothing else
        open(p, "wb").write(bytes(b))
    out = os.path.join(tmp, name + ".out")
    os.mkdir(out)
    return run(sink, p, out)


def collision_case(sink, tmp, problems):
    """Two files whose names are the same for 31 characters and differ
    after. Both must come out — the second under a numbered name, the
    way an 8.3 filesystem numbered what it had to shorten."""
    base = "B" * HFS
    got, rc, rep = case(sink, tmp, "macname-collide",
                   [synth_dd.file(base + "one.txt", data=b"first\n"),
                    synth_dd.file(base + "two.txt", data=b"second\n")])
    check(problems, rc == 0, "collide: exit was %d" % rc)
    check(problems, len(got) == 2,
          "collide: wrote %r, wanted both files" % sorted(got))
    check(problems, sorted(got.values()) == [b"first\n", b"second\n"],
          "collide: the bytes are not the two entries: %r"
          % sorted(got.values()))
    check(problems, any("~1." in n for n in got),
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
    got, rc, rep = case(sink, tmp, "macname-dircollide",
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
    got, rc, rep = case(sink, tmp, "macname-deep", [node])
    check(problems, rc == 0, "deep: exit was %d" % rc)
    check(problems, len(got) == 1 and list(got.values()) == [b"deep\n"],
          "deep: wrote %r, wanted the one file" % sorted(got))
    if got:
        leaf = sorted(got)[0]
        check(problems, "~1" in leaf,
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
    got, rc, rep = case(sink, tmp, "macname-edge",
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


def extension_case(sink, tmp, problems):
    """A name too long for HFS keeps its EXTENSION and loses stem, and a
    name that has to be numbered takes the `~1` BEFORE the extension.
    Cutting the other way leaves `...ForTheBoard.rt`, and `dup.txt~1`
    leaves a name that no longer says what opens it — which matters
    because a file that arrived with a suffix generally came off a
    machine that has no forks and no type or creator, so the suffix is
    all there is (2026-08-29; it was the first thing cut for a few
    hours, which was backwards)."""
    fits = "MyQuarterlyReportForTheBoard.rtf"        # 32; 31 without 1 stem
    huge = "AnotherVeryLongDocumentNameIndeedYesReally.rtf"
    got, rc, rep = case(sink, tmp, "macname-ext",
                        [synth_dd.file(fits, data=b"rtf\n"),
                         synth_dd.file(huge, data=b"big\n"),
                         synth_dd.file("dup.txt", data=b"d1\n"),
                         synth_dd.file("dup.txt", data=b"d2\n")])
    check(problems, rc == 0, "ext: exit was %d" % rc)
    check(problems, fits[:27] + ".rtf" in got,
          "ext: the stem was not what got cut: %r" % sorted(got))
    check(problems, huge[:27] + ".rtf" in got,
          "ext: a much longer name lost its extension: %r" % sorted(got))
    check(problems, "dup~1.txt" in got,
          "ext: the number did not go before the extension: %r" % sorted(got))
    check(problems, sorted(got.values()) == [b"big\n", b"d1\n", b"d2\n",
                                             b"rtf\n"],
          "ext: a file was lost: %r" % sorted(got.values()))
    check(problems, "dup.txt renamed to dup~1.txt" in rep,
          "ext: the numbered file is not in the report: %r" % rep)
    check(problems, (fits + " renamed to " + fits[:27] + ".rtf") in rep,
          "ext: the shortened name is not in the report: %r" % rep)
    return 1


def report_case(sink, tmp, problems):
    """What the end-of-run box lists. Every name this shell changed is
    named twice — the archive's and the disk's — and a folder that
    MERGED into one already there says so in different words, because
    what happened to the user's files is different: nothing is lost, but
    two folders are now one."""
    a = "D" * 33 + "alpha"
    b = "D" * 33 + "beta"
    got, rc, rep = case(sink, tmp, "macname-report",
                        [synth_dd.folder(a, [synth_dd.file("x.txt",
                                                           data=b"in A\n")]),
                         synth_dd.folder(b, [synth_dd.file("y.txt",
                                                           data=b"in B\n")])])
    check(problems, rc == 0, "report: exit was %d" % rc)
    renamed = [l for l in rep if " renamed to " in l]
    merged = [l for l in rep if " combined with " in l]
    check(problems, renamed == ["Folder " + a + " renamed to " + a[:31]],
          "report: the first folder is not reported once as renamed: %r" % rep)
    check(problems, merged == ["Folder " + b + " combined with " + b[:31]],
          "report: the merged folder is not reported once as merged: %r" % rep)
    check(problems, all(len(l) > 60 for l in rep),
          "report: a name was cut short of what the archive calls it — the "
          "list exists to say which file became which: %r" % rep)
    # The files in it are NOT reported: their own names were writable.
    check(problems, len(rep) == 2,
          "report: something with an untouched name was reported: %r" % rep)
    check(problems, sorted(got.values()) == [b"in A\n", b"in B\n"],
          "report: a merged folder lost a file: %r" % sorted(got.values()))
    return 1


def failure_case(sink, tmp, problems):
    """A per-entry failure that does not stop the archive. Until
    2026-08-29 the whole of what the user was told was "some entries
    could not be extracted", which names neither the entry nor what to
    do about it."""
    got, rc, rep = case(sink, tmp, "macname-fail",
                        [synth_dd.file("good.txt", data=b"GOOD\n",
                                       stored=True),
                         synth_dd.file("broken.txt", data=b"BROKENBROKEN\n",
                                       stored=True)],
                        corrupt=b"BROKENBROKEN")
    check(problems, got.get("good.txt") == b"GOOD\n",
          "fail: the sound entry did not come out: %r" % sorted(got))
    check(problems, any(l.startswith("broken.txt is damaged") for l in rep),
          "fail: the damaged entry is not named in the report: %r" % rep)
    check(problems, not any(l.startswith("good.txt") for l in rep),
          "fail: a sound entry was reported as a problem: %r" % rep)
    return 1


def crowd_case(sink, tmp, problems):
    """More names alike than the numbering had digits for. Until
    2026-08-29 the suffix ran "~1".."~9" and the TENTH such name
    returned -1 from begin_entry, which the engine reads as "abort the
    archive": everything after it was silently never written. Measured
    on a Mac Plus, with eighteen photographs (BLOCKERS.md).

    Now the suffix goes to "~99", and a name that still cannot be made
    unique fails ITS OWN entry — so the file after it comes out, which
    is the half that matters."""
    base = "F" * 20 + "Photograph Of The Summer no"
    tree = [synth_dd.file(base + "%02d" % i, data=b"pic%02d\n" % i)
            for i in range(102)]
    tree.append(synth_dd.file("zzz.txt", data=b"after them all\n"))
    got, rc, rep = case(sink, tmp, "macname-crowd", tree)
    check(problems, got.get("zzz.txt") == b"after them all\n",
          "crowd: the entry AFTER the crowd never came out — the archive "
          "was aborted rather than the entry: %d file(s)" % len(got))
    check(problems, len(got) == 101,
          "crowd: wrote %d files, wanted 100 numbered + 1" % len(got))
    check(problems, base[:28] + "~99" in got,
          "crowd: the numbering did not reach two digits: %r"
          % sorted(got)[-3:])
    failed = [l for l in rep if "could not be given a name of its own" in l]
    check(problems, len(failed) == 2,
          "crowd: wanted the 2 unplaceable entries reported, got %r" % failed)
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
        ran += extension_case(args.sink, tmp, problems)
        ran += report_case(args.sink, tmp, problems)
        ran += failure_case(args.sink, tmp, problems)
        ran += crowd_case(args.sink, tmp, problems)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("MACNAMES FAIL " + p)
    print("macnames: %d case(s) checked, %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

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
which one acted. One case uses a zip instead, and says why: a zip
declares no folders, so its folders exist only inside the paths of the
files in them.

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
import zipfile

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
    """The same collision between two FOLDERS, which since 2026-09-03 is
    answered the same way: the second folder is NUMBERED rather than
    descended into. Until then `EnsureDir` took whatever directory was
    already there, so two folders shortening alike became one and their
    contents mixed — nothing was lost, but the path was not the
    archive's and neither folder was where the archive put it."""
    base = "C" * HFS
    got, rc, rep = case(sink, tmp, "macname-dircollide",
                   [synth_dd.folder(base + "folderA",
                                    [synth_dd.file("x.txt", data=b"in A\n")]),
                    synth_dd.folder(base + "folderB",
                                    [synth_dd.file("y.txt", data=b"in B\n")])])
    check(problems, rc == 0, "dircollide: exit was %d" % rc)
    check(problems, sorted(got) == [base + "/x.txt", base[:29] + "~1/y.txt"],
          "dircollide: wrote %r, wanted the second folder numbered"
          % sorted(got))
    check(problems, sorted(got.values()) == [b"in A\n", b"in B\n"],
          "dircollide: a file was lost: %r" % sorted(got.values()))
    check(problems, all(len(c) <= HFS for n in got for c in n.split("/")),
          "dircollide: a numbered folder is longer than an HFS name: %r"
          % sorted(got))
    return 1


def path_folder_case(sink, tmp, problems):
    """The same two folders in a format that declares NO folders of its
    own — a zip, where the folders exist only inside the paths of the
    files in them, which is the shape most archives a user downloads
    have. Measured 2026-09-03: this was the WORSE case, because the box
    reported the first folder's rename and said nothing at all about the
    second, whose file had gone into it.

    Written here rather than with `synth_dd` for exactly that reason:
    every other case in this file uses DiskDoubler, which declares its
    folders, and the declaration is what the old report needed."""
    a = "D" * 33 + "alpha"
    b = "D" * 33 + "beta"
    p = os.path.join(tmp, "macname-pathdirs.zip")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(a + "/x.txt", b"in A\n")
        z.writestr(b + "/y.txt", b"in B\n")
    out = os.path.join(tmp, "macname-pathdirs.out")
    os.mkdir(out)
    got, rc, rep = run(sink, p, out)
    check(problems, rc == 0, "pathdirs: exit was %d" % rc)
    check(problems, sorted(got) == ["D" * 31 + "/x.txt", "D" * 29 + "~1/y.txt"],
          "pathdirs: wrote %r, wanted the second folder numbered too — a "
          "folder no entry declares is still a folder" % sorted(got))
    check(problems, rep == [("Folder " + a + " renamed to " + "D" * 31),
                            ("Folder " + b + " renamed to " + "D" * 29 + "~1")],
          "pathdirs: both folders must be named in the report, in full: %r"
          % rep)
    return 1


def folder_again_case(sink, tmp, problems):
    """The same archive extracted TWICE into the same destination. A
    folder that is already on the volume is not this run's to number —
    it is the user's, or the last run's — so the second run descends
    into it and the FILES inside are what gets numbered. Numbering the
    folder instead would spray `~1` over the first run's work, and a
    user who extracts an archive twice has said nothing about wanting
    two copies of its folders."""
    base = "H" * HFS
    tree = [synth_dd.folder(base + "folder",
                            [synth_dd.file("x.txt", data=b"in it\n")])]
    p, _ = synth_dd.write_one(tmp, "macname-diragain", tree)
    out = os.path.join(tmp, "macname-diragain.out")
    os.mkdir(out)
    run(sink, p, out)
    got, rc, rep = run(sink, p, out)
    check(problems, rc == 0, "diragain: exit was %d" % rc)
    check(problems, sorted(got) == [base + "/x.txt", base + "/x~1.txt"],
          "diragain: wrote %r, wanted one folder holding both runs' files"
          % sorted(got))
    check(problems, not any(l.startswith("Folder ") for l in rep),
          "diragain: a folder that was already there was reported: %r" % rep)
    return 1


def folder_crowd_case(sink, tmp, problems):
    """More FOLDERS alike than the numbering has digits for. `BumpName`
    writes two, so the hundred-and-first is where numbering stops — and
    what is left there is the old behaviour, a merge, which keeps every
    file. The alternative would be to fail the entry, and a folder that
    fails takes everything under it with it."""
    base = "G" * 20 + "Correspondence no"
    tree = [synth_dd.folder(base + "%03d" % i,
                            [synth_dd.file("letter%03d.txt" % i,
                                           data=b"no%03d\n" % i)])
            for i in range(101)]
    got, rc, rep = case(sink, tmp, "macname-dircrowd", tree)
    check(problems, rc == 0, "dircrowd: exit was %d" % rc)
    check(problems, len(got) == 101,
          "dircrowd: wrote %d files, wanted every one of the 101" % len(got))
    check(problems, len(set(os.path.dirname(n) for n in got)) == 100,
          "dircrowd: wanted 100 folders and the last one merged, got %d"
          % len(set(os.path.dirname(n) for n in got)))
    check(problems, base[:28] + "~99" in set(os.path.dirname(n) for n in got),
          "dircrowd: the folder numbering did not reach two digits: %r"
          % sorted(set(os.path.dirname(n) for n in got))[-3:])
    merged = [l for l in rep if " combined with " in l]
    check(problems, len(merged) == 1 and merged[0].startswith(
              "Folder " + base + "100 combined with "),
          "dircrowd: the folder past the numbering is not reported as "
          "merged: %r" % merged)
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
    named twice — the archive's and the disk's — including the SECOND of
    two folders that shorten alike, which since 2026-09-03 is a folder
    of its own with a number rather than a merge into the first."""
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
    check(problems, renamed == ["Folder " + a + " renamed to " + a[:31],
                                "Folder " + b + " renamed to " + b[:29] + "~1"],
          "report: both folders are not reported once each, in full: %r" % rep)
    check(problems, merged == [],
          "report: a folder was merged where it could have been numbered: %r"
          % rep)
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


def folder_table_full_case(sink, tmp, problems):
    """More folders than the memo has rows — 250 against 200 — which is
    where numbering stops and folders merge again. The assertion is not
    that they are numbered; it is that no folder is SPLIT. A run that
    forgot a folder half way through would send the rest of its files
    somewhere else, and one archive folder across two disk folders is
    worse than the merge numbering replaces, which is why the table
    never evicts (DECISIONS.md 2026-09-03)."""
    base = "I" * 20 + "Chapter"
    tree = [synth_dd.folder(base + "%03d" % i,
                            [synth_dd.file("a%03d.txt" % i, data=b"a%03d\n" % i),
                             synth_dd.file("b%03d.txt" % i, data=b"b%03d\n" % i)])
            for i in range(250)]
    got, rc, rep = case(sink, tmp, "macname-dirfull", tree)
    check(problems, rc == 0, "dirfull: exit was %d" % rc)
    check(problems, len(got) == 500,
          "dirfull: wrote %d files, wanted all 500" % len(got))
    split = [i for i in range(250)
             if os.path.dirname(next((n for n in got
                                      if os.path.basename(n) == "a%03d.txt" % i),
                                     "?/?"))
             != os.path.dirname(next((n for n in got
                                      if os.path.basename(n) == "b%03d.txt" % i),
                                     "!/!"))]
    check(problems, split == [],
          "dirfull: %d folder(s) were split across two folders on disk, "
          "starting at %r" % (len(split), split[:3]))
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
        ran += path_folder_case(args.sink, tmp, problems)
        ran += folder_again_case(args.sink, tmp, problems)
        ran += folder_crowd_case(args.sink, tmp, problems)
        ran += folder_table_full_case(args.sink, tmp, problems)
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

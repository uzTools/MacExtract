#!/usr/bin/env python3
"""run_depth.py — nesting is bounded by the PATH, and by nothing else.

The engine had a depth limit until 2026-10-07: `UNC_PATH_MAXDEPTH`, 24,
which three formats "chose independently" and which sized two fixed
arrays in `UncPath`. It was never measured against anything. A Macintosh
creates **250 levels** by dirID and reads all 250 back with noErr
(`tools/vmac/depthtest/`, FORMATS.md, *What the DESTINATION actually
allows*); HFS itself takes 89. The one real limit is the path STRING,
255 bytes, which is `UNC_NAME_MAX` and is also what a classic Str255 full
pathname holds.

So the rule this applies is now one sentence with no exception in it:

    An archive nests as deep as its paths will fit in UNC_NAME_MAX, and
    every entry is reported at exactly its own path. A component with no
    room left is CUT, which is the over-long path both hosts already
    shorten and report — there is no second failure mode.

The subjects nest to 30, which is past the old limit by six and which no
real archive comes near: the deepest on this disk is 4. They put a file
at every level on the way down, a TRAILER at every level on the way back
up, and a sentinel at the root. The trailers are the assertion with
teeth — four of the five walks pop by a COUNT, so a push that wrote
nothing and a pop that still happened leaves the walk shallower than it
went down and misfiles every entry after it into a real folder it was not
in, silently, because the path is plausible and nothing in it looks cut
(BLOCKERS.md, *what ignoring a refused push cost*).

How to re-run it:

    python3 tools/run_depth.py --macextract build/macextract

What this CANNOT see:

  * whether any real archive is ever this deep. None here is, so every
    subject is generated and this grades a RULE, not a corpus.
  * what happens past 255 bytes of PATH, which is where the one limit
    actually bites. `deep-dd-long.dd` reaches it — 31-character folder
    names fill the string around the eighth level — but a path cut at
    255 reports the same string for every entry below the cut, so
    nothing here can attribute a notice to an entry. `test_path_depth`
    in tests/unit_formats.c asserts that on the fields instead.
  * the two formats that carry a path WITHOUT this walker — StuffIt and
    Compact Pro go through `unc_entry_path_append`.
  * the destination's own limits. 30 levels of short names is nothing to
    ext4 or HFS; `tools/vmac/depthtest/` is what asked them.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_deep                                             # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROW = re.compile(r"^([dfl]) +\S+ +\S+ +\S+ +(.*)$")
DEPTH = 30


def check(problems, cond, msg):
    if not cond:
        problems.append(msg)
    return cond


def listing(macextract, path):
    r = subprocess.run([macextract, "l", path], capture_output=True)
    rows = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        m = ROW.match(line)
        if m:
            rows.append((m.group(1), m.group(2)))
    return rows


def extract(macextract, path, outdir):
    r = subprocess.run([macextract, "x", "-o", outdir, path],
                       capture_output=True)
    err = r.stderr.decode("utf-8", "replace")
    failed = 0
    m = re.search(r"(\d+) of (\d+) entries failed", err)
    if m:
        failed = int(m.group(1))
    return failed, err


def on_disk(outdir):
    files, dirs = set(), set()
    for root, ds, fs in os.walk(outdir):
        rel = os.path.relpath(root, outdir)
        for f in fs:
            files.add(os.path.normpath(os.path.join(rel, f)))
        for d in ds:
            dirs.add(os.path.normpath(os.path.join(rel, d)))
    return files, dirs


def sd_payload(macextract, tmp):
    """The SuperDisk! archive whose unread fields and blocks are
    borrowed. None where the fixture is absent."""
    fixture = os.path.join(REPO, "fixtures", "super-disk-utility.hqx")
    if not os.path.exists(fixture):
        return None
    env = os.path.join(tmp, "sdenv")
    r = subprocess.run([macextract, "x", "-nr", "-o", env, fixture],
                       capture_output=True)
    inner = os.path.join(env, "SD! Utilities.x")
    return inner if r.returncode == 0 and os.path.exists(inner) else None


CUTNOTE = re.compile(r"^macextract:   (.*)$")


def deep_and_cut(macextract, path, tmp, problems):
    """The one limit, reached: a path that fills UNC_NAME_MAX.

    An entry that is only too long gets `name_truncated` 2 and the WHOLE
    name through `UncOptions.long_name` — that is the engine's promise and
    `run_names.py` grades it. An entry that is also too deep has no whole
    name to give: what the walk holds is the path with folders missing
    from the middle of it. Offering THAT as the whole name is a falsehood
    a host cannot detect, and the engine did it until 2026-10-07 — the
    CLI printed `.../D24.../f30.txt` as "the archive's name" for an entry
    with six more folders in it.

    **The field-level assertion is `test_path_depth` in
    tests/unit_formats.c, not here, and that is forced.** A path cut at
    UNC_NAME_MAX reports the same 255-byte string for every entry below
    the cut, and that string is also a shallower entry's. Nothing at
    this level can attribute a notice to an entry, so an assertion
    written here fired on the collision and not on the defect
    (2026-10-07). What this does is keep the SUBJECT honest: if it ever
    stops reaching the limit, the unit test is still right and this file
    is the one that would quietly stop describing anything.
    """
    out = os.path.join(tmp, "out-longnames")
    shutil.rmtree(out, ignore_errors=True)
    _failed, err = extract(macextract, path, out)
    check(problems, "did not fit and were shortened" in err,
          "ddar-longnames: no name was reported cut — this subject is "
          "meant to fill the path string")
    check(problems, sum(1 for l in err.splitlines() if CUTNOTE.match(l)),
          "ddar-longnames: the run said nothing about a cut path")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--macextract", default="build/macextract")
    ap.add_argument("--keep", help="write the subjects here and keep them")
    a = ap.parse_args()

    problems = []
    tmp = a.keep or tempfile.mkdtemp(prefix="depth-")
    os.makedirs(tmp, exist_ok=True)
    try:
        folders, files = synth_deep.plan(DEPTH)
        declared = len(folders) + len(files)

        made = synth_deep.write(tmp, DEPTH, sd_payload(a.macextract, tmp))
        if not any(k == "superdisk" for k in made.values()):
            print("depth: SuperDisk! payload absent, that one format skipped")

        for path in sorted(made):
            kind = made[path]
            if kind == "ddar-longnames":
                deep_and_cut(a.macextract, path, tmp, problems)
                continue
            rows = listing(a.macextract, path)
            got = [p for _, p in rows]

            # 1. every entry the archive declares is offered.
            check(problems, len(rows) == declared,
                  "%s: %d entries offered, the archive declares %d"
                  % (kind, len(rows), declared))

            # 2. at exactly its OWN path, all 30 levels of it. This is
            #    what an unbalanced pop breaks, and it breaks it silently.
            missing = sorted((set(folders) | set(files)) - set(got))
            check(problems, not missing,
                  "%s: %d path(s) not reported as the archive has them, "
                  "e.g. %s" % (kind, len(missing), missing[:1]))

            # 3. and nothing at a path the archive does not have.
            extra = sorted(set(got) - (set(folders) | set(files)))
            check(problems, not extra,
                  "%s: %d path(s) reported that the archive does not have, "
                  "e.g. %s" % (kind, len(extra), extra[:1]))

            # 4. the root sentinel is at the ROOT. unc_path_pop clamps at
            #    0, so a walk that over-pops by fewer levels than it has
            #    left still lands this one — 2. is the assertion that bites.
            check(problems, "after.txt" in got,
                  "%s: the root sentinel is not at the root" % kind)

            # 5. extraction writes every one of them and fails nothing.
            out = os.path.join(tmp, "out-" + os.path.basename(path))
            shutil.rmtree(out, ignore_errors=True)
            failed, err = extract(a.macextract, path, out)
            check(problems, failed == 0,
                  "%s: %d entries failed; nothing here is past any limit"
                  % (kind, failed))
            wfiles, wdirs = on_disk(out)
            check(problems, wfiles == set(files),
                  "%s: wrote %d files, wanted %d (extra %s, missing %s)"
                  % (kind, len(wfiles), len(files),
                     sorted(wfiles - set(files))[:1],
                     sorted(set(files) - wfiles)[:1]))
            check(problems, wdirs == set(folders),
                  "%s: created %d folders, wanted %d (extra %s)"
                  % (kind, len(wdirs), len(folders),
                     sorted(wdirs - set(folders))[:1]))
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)

    if problems:
        for p in problems:
            print("depth: " + p)
        print("depth: %d problem(s)" % len(problems))
        return 1
    print("depth: %d formats nest %d levels deep, every entry at its own "
          "path, nothing refused — the path string is the only limit"
          % (len(made), DEPTH))
    return 0


if __name__ == "__main__":
    sys.exit(main())

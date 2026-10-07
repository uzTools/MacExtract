#!/usr/bin/env python3
"""run_depth.py — the five path walks must agree at UNC_PATH_MAXDEPTH.

`unc_path_push` refuses to descend past 24 levels, and the five walks
that call it used to do three different things about it. What that cost
is in BLOCKERS.md (*what ignoring a refused push cost*); the rule they
now share is one sentence:

    An entry the walk could not descend to is still OFFERED, with the
    path it could represent; it carries `path_too_deep`, it fails per
    entry with UNC_ERR_TOODEEP, and nothing is written for it. An entry
    the walk COULD represent is reported at exactly its own path,
    whatever happened deeper in.

The second half is the one with teeth. Four of the five walks pop by a
COUNT — a marker record (DiskDoubler's `enddir`, SuperDisk!'s
`SD_TAG_UPDIR`), a level counter (DDA2), or a per-directory entry count
(Now Compress) — so a refusal that was not counted left the walk
shallower than it went down and misfiled everything after it into a real
folder it was not in. That is silent: the path is plausible, nothing in
it looks cut, and an aggregate check over names and CRCs cannot see it
because every byte is right and only the folder is wrong.

The subjects come from `tools/synth_deep.py`, which nests to 30 and puts
a file at every level on the way down, a TRAILER at every level on the
way back up, and a sentinel at the root. The trailers are what catch an
unbalanced pop; see that file for why each part is there.

How to re-run it:

    python3 tools/run_depth.py --macextract build/macextract

What this CANNOT see:

  * whether 24 is the right limit, or whether any real archive reaches
    it. Nothing here does — the deepest nesting on this disk is 4
    (`tools/measure_depth.py`, FORMATS.md) — so every subject is
    generated and this suite grades a RULE, not a corpus.
  * the decoded bytes of a deep entry. Nothing is written for one, by
    the rule, so there is nothing to compare; what comes out of the
    representable part is compared by path and by length only.
  * whether the record shapes are what each application would write.
    They are the existing `tools/synth_*.py` shapes nested deeper, with
    those files' own provenance, and SuperDisk! has no second reader off
    the Macintosh at all.
  * the two formats that carry a path WITHOUT this walker — StuffIt and
    Compact Pro go through `unc_entry_path_append` and have no depth
    limit to reach.
  * that the engine makes no FALSE claim about a too-deep entry's name.
    Every deep path collapses to the same 255-byte string here, so a
    note cannot be attributed to an entry; `test_path_depth` in
    tests/unit_formats.c asserts that on the fields.
  * what a host SHOULD do with a path it cannot place. The rule is that
    the engine must not claim more than it has; whether a host refuses
    the entry, flattens it or asks the user is the host's, and only the
    two in this tree are exercised here.
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
MAXDEPTH = synth_deep.MAXDEPTH


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


DEEPLINE = re.compile(r"^macextract: (.*): nested too deep to place$")


def deep_and_cut(macextract, path, tmp, problems):
    """The two limits at once: a path cut by UNC_NAME_MAX AND deeper than
    UNC_PATH_MAXDEPTH.

    An entry that is only too long gets `name_truncated` 2 and the WHOLE
    name through `UncOptions.long_name` — that is the engine's promise and
    `run_names.py` grades it. An entry that is also too deep has no whole
    name to give: what the walk holds is the path with folders missing
    from the middle of it. Offering THAT as the whole name is a falsehood
    a host cannot detect, and the engine did it until 2026-10-07 — the
    CLI printed `.../D24.../f30.txt` as "the archive's name" for an entry
    with six more folders in it.

    **The field-level assertion is `test_path_depth` in
    tests/unit_formats.c, not here, and that is forced.** A too-deep
    path is itself cut at UNC_NAME_MAX on the way out, so every deep
    entry in this subject reports the SAME 255-byte string — and that
    string is also a shallow entry's. Nothing at this level can attribute
    a note to an entry, so an assertion written here fired on the
    collision and not on the defect (2026-10-07). What this does is keep
    the SUBJECT honest: if it ever stops reaching both limits, the unit
    test is still right and this file is the one that would quietly stop
    describing anything.
    """
    out = os.path.join(tmp, "out-longnames")
    shutil.rmtree(out, ignore_errors=True)
    _failed, err = extract(macextract, path, out)
    deep = sum(1 for l in err.splitlines() if DEEPLINE.match(l))
    cut = "did not fit and were shortened" in err
    check(problems, deep,
          "ddar-longnames: nothing was reported too deep — this subject "
          "is meant to reach both limits at once")
    check(problems, cut,
          "ddar-longnames: no name was reported cut — this subject is "
          "meant to reach UNC_NAME_MAX as well")


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
        # What a walk that stops at MAXDEPTH levels of folder can place.
        # A folder AT the limit is named from the path above it, so its own
        # name is representable and only what is inside it is not.
        ok_files = set(p for p in files if p.count("/") <= MAXDEPTH)
        ok_dirs = set(p for p in folders if p.count("/") <= MAXDEPTH)
        declared = len(folders) + len(files)
        deep = declared - len(ok_files) - len(ok_dirs)

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

            # 1. every entry the archive declares is offered, deep or not.
            check(problems, len(rows) == declared,
                  "%s: %d entries offered, the archive declares %d"
                  % (kind, len(rows), declared))

            # 2. everything representable is at its OWN path. This is what
            #    an unbalanced pop breaks, and it breaks it silently.
            missing = sorted((ok_files | ok_dirs) - set(got))
            check(problems, not missing,
                  "%s: %d representable path(s) not reported, e.g. %s"
                  % (kind, len(missing), missing[:1]))

            # 3. nothing is reported at a path deeper than the limit.
            over = [p for p in got if p.count("/") > MAXDEPTH]
            check(problems, not over,
                  "%s: %d path(s) past %d levels reported"
                  % (kind, len(over), MAXDEPTH))

            # 4. the root sentinel is at the ROOT. An over-popped walk can
            #    still land this one, because unc_path_pop clamps at 0 —
            #    which is why 2. above is the assertion that matters.
            check(problems, "after.txt" in got,
                  "%s: the root sentinel is not at the root" % kind)

            # 5. extraction fails exactly the entries it could not place,
            #    and writes exactly the ones it could.
            out = os.path.join(tmp, "out-" + os.path.basename(path))
            shutil.rmtree(out, ignore_errors=True)
            failed, err = extract(a.macextract, path, out)
            check(problems, failed == deep,
                  "%s: %d entries failed, wanted the %d it cannot place"
                  % (kind, failed, deep))
            wfiles, wdirs = on_disk(out)
            check(problems, wfiles == ok_files,
                  "%s: wrote %d files, wanted %d (extra %s, missing %s)"
                  % (kind, len(wfiles), len(ok_files),
                     sorted(wfiles - ok_files)[:1],
                     sorted(ok_files - wfiles)[:1]))
            check(problems, wdirs == ok_dirs,
                  "%s: created %d folders, wanted %d (extra %s)"
                  % (kind, len(wdirs), len(ok_dirs),
                     sorted(wdirs - ok_dirs)[:1]))
            # 6. and it SAYS so, per entry, in the engine's own words.
            check(problems, "nested too deep" in err,
                  "%s: nothing said about an entry it could not place"
                  % kind)
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)

    if problems:
        for p in problems:
            print("depth: " + p)
        print("depth: %d problem(s)" % len(problems))
        return 1
    print("depth: %d formats agree at %d levels — every representable entry "
          "at its own path, %d deeper ones offered and refused"
          % (len(made), MAXDEPTH, deep))
    return 0


if __name__ == "__main__":
    sys.exit(main())

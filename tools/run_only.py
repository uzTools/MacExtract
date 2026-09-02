#!/usr/bin/env python3
"""run_only.py — `--only`: acting on the entries the user named.

`--only NAME` restricts `l`, `x` and `t` to the entries named, and is
the CLI half of selective extraction. Underneath it is the one thing
`UncSink.begin_entry` could always do and no host had ever asked for:
return >0 for SOME entries and 0 for others while writing. Listing
returned >0 for every entry, and both hosts returned it for every
directory, so the branch was live in all 25 format files — but never
mixed, which is the shape a selection has.

What is asserted, and why it is not graded against our own output:

  a selected entry is byte-identical to the same entry from the FULL
  extraction of the same archive, fork for fork

which is transitive to `unar`, because the full extraction is what the
932-fixture differential suite grades (TESTING.md). `unar` has no
per-file selection of its own, so there is no direct oracle for a
subset, and this is the nearest thing that is not circular.

  the selection is a STRICT subset

is the assertion that can fail. Without it a `--only` that was ignored
entirely — the whole archive extracted every time — passes every
byte comparison above it, since a superset contains every file it is
compared against.

  a selector that matches nothing exits nonzero

because a mistyped name would otherwise extract nothing, say nothing
and exit 0.

The generated cases carry folders and resource forks on purpose: a
FOLDER is the entry both hosts have always skipped, and the two formats
that called `end_entry` for a skipped one anyway — Now Compress and
DiskDoubler, corrected 2026-08-28 — are the two built here.

What this CANNOT see:

  * whether skipping an entry SAVED anything. A format that seeks past
    a skipped entry (Compact Pro, StuffIt, zip, Now Compress) and one
    that decodes and discards it (PackIt, whose compressed entries state
    no end) pass this identically; nothing here measures time or I/O.
  * a defect that corrupts the full extraction and the selective one
    the same way. The reference side is our own full run; `unar` is
    what grades that, in the diff suite.
  * the Macintosh shell, which has no selection UI and does not use
    this option.
  * encrypted entries and segmented sets, neither of which the sweep
    reaches: the corpus has no encrypted archive, and a part of a set
    is exempt from filtering (it unwraps into the archive first).
  * anything about a fixture whose names had to be SHORTENED to reach
    this filesystem — the sweep skips those, because the path on disk
    is then not the name `--only` matches against.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_dd                                        # noqa: E402
import synth_now                                       # noqa: E402

TIMEOUT = 180


def run(mac, args, timeout=TIMEOUT):
    return subprocess.run([mac] + args, capture_output=True, timeout=timeout)


def tree(out):
    """{relative path: contents} for every file under `out`."""
    got = {}
    for root, _, files in os.walk(out):
        for f in files:
            p = os.path.join(root, f)
            with open(p, "rb") as fh:
                got[os.path.relpath(p, out)] = fh.read()
    return got


def rows(stdout):
    """The entry names of an `l` listing."""
    out = []
    for line in stdout.decode("utf-8", "replace").splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5 and parts[0] in ("f", "d"):
            out.append(parts[4])
    return out


def check(problems, cond, msg):
    if not cond:
        problems.append(msg)
    return cond


def under(path, sel):
    """Is `path` what selecting `sel` may produce? The entry itself, its
    resource-fork sidecar, or something inside it when it is a folder."""
    return path == sel or path == sel + ".rsrc" or path.startswith(sel + "/")


def selective(mac, problems, label, archive, full, sel, extra=()):
    """Extract `archive` with --only `sel` and hold it against `full`."""
    out = tempfile.mkdtemp()
    try:
        run(mac, ["x", archive, "-o", out, "--only", sel] + list(extra))
        got = tree(out)
    finally:
        shutil.rmtree(out, ignore_errors=True)

    if not check(problems, got, "%s: --only %r wrote nothing" % (label, sel)):
        return
    check(problems, len(got) < len(full),
          "%s: --only %r wrote %d of %d files — not a strict subset"
          % (label, sel, len(got), len(full)))
    for path, data in sorted(got.items()):
        if not check(problems, under(path, sel),
                     "%s: --only %r also wrote %r" % (label, sel, path)):
            continue
        if not check(problems, path in full,
                     "%s: --only %r wrote %r, which the full extraction "
                     "did not" % (label, sel, path)):
            continue
        check(problems, data == full[path],
              "%s: --only %r: %r differs from the full extraction "
              "(%d bytes vs %d)" % (label, sel, path, len(data),
                                    len(full[path])))


def full_extract(mac, archive):
    """(files, stderr) for a whole archive."""
    out = tempfile.mkdtemp()
    try:
        r = run(mac, ["x", archive, "-o", out])
        return tree(out), r.stderr.decode("utf-8", "replace")
    finally:
        shutil.rmtree(out, ignore_errors=True)


# ------------------------------------------------------------------
# Generated cases: run everywhere, fixtures or no fixtures
# ------------------------------------------------------------------

def zip_cases(mac, tmp, problems):
    """A plain zip: names, folders, several selectors, and the misses."""
    p = os.path.join(tmp, "only.zip")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("top.txt", b"the one at the top\n")
        z.writestr("a/x.txt", b"first inside a\n")
        z.writestr("a/y.txt", b"second inside a\n")
        z.writestr("b/z.txt", b"the one inside b\n")

    full, _ = full_extract(mac, p)
    if not check(problems, len(full) == 4,
                 "zip: the full extraction wrote %d files, expected 4"
                 % len(full)):
        return 0

    selective(mac, problems, "zip", p, full, "top.txt")
    selective(mac, problems, "zip", p, full, "a/x.txt")
    selective(mac, problems, "zip", p, full, "a")        # a folder

    # Two at once, from two different folders.
    out = os.path.join(tmp, "two")
    os.mkdir(out)
    run(mac, ["x", p, "-o", out, "--only", "a/y.txt", "--only", "b/z.txt"])
    check(problems, sorted(tree(out)) == ["a/y.txt", "b/z.txt"],
          "zip: two selectors wrote %s" % sorted(tree(out)))

    # A name that matches nothing: reported, and nonzero.
    out = os.path.join(tmp, "miss")
    os.mkdir(out)
    r = run(mac, ["x", p, "-o", out, "--only", "a/nope.txt"])
    check(problems, r.returncode != 0,
          "zip: --only with a name that matches nothing exited 0")
    check(problems, b"no entry of this archive has that name" in r.stderr,
          "zip: a selector that matched nothing was not reported")
    check(problems, not tree(out),
          "zip: a selector that matched nothing still wrote files")

    # One hit and one miss is still a miss — the run exits nonzero, and
    # the entry that DID match is extracted.
    out = os.path.join(tmp, "half")
    os.mkdir(out)
    r = run(mac, ["x", p, "-o", out, "--only", "top.txt", "--only", "nope"])
    check(problems, r.returncode != 0, "zip: one miss among two exited 0")
    check(problems, sorted(tree(out)) == ["top.txt"],
          "zip: the selector that matched was not extracted: %s"
          % sorted(tree(out)))

    # l and t take it too, and l stays a listing: no question, no prompt.
    r = run(mac, ["l", p])
    check(problems, len(rows(r.stdout)) == 4,
          "zip: an unfiltered listing has %d rows" % len(rows(r.stdout)))
    r = run(mac, ["l", p, "--only", "a"])
    check(problems, rows(r.stdout) == ["a/x.txt", "a/y.txt"],
          "zip: `l --only a` listed %s" % rows(r.stdout))
    r = run(mac, ["l", p, "--only", "nope"])
    check(problems, r.returncode != 0, "zip: `l --only nope` exited 0")
    r = run(mac, ["t", p, "--only", "a/x.txt"])
    check(problems, r.returncode == 0,
          "zip: `t --only a/x.txt` exited %d" % r.returncode)
    return 1


def mac_tree():
    """A folder holding two forked files, and one file beside it. The
    folder is what makes this worth building: it is the entry a host
    skips, and the entry two formats used to report the end of anyway."""
    return [
        synth_dd.folder("Folder", [
            synth_dd.file("one.txt", data=b"one's data fork\n",
                          rsrc=b"one's resource fork\n"),
            synth_dd.file("two.txt", data=b"two's data fork\n",
                          rsrc=b"two's resource fork\n"),
        ]),
        synth_dd.file("beside.txt", data=b"not in the folder\n"),
    ]


def dd_cases(mac, tmp, problems):
    """DiskDoubler, both containers. `DDAR` and `DDA2` each honoured a
    skipped FOLDER only from 2026-08-28; before that they called
    end_entry for one, against the contract in macextract.h."""
    ran = 0
    for kind in ("ddar", "dda2"):
        p, _ = synth_dd.write_one(tmp, "only-dd-" + kind, mac_tree(), kind)
        full, err = full_extract(mac, p)
        if not check(problems, len(full) == 5,
                     "dd/%s: the full extraction wrote %d files, expected 5 "
                     "(%s)" % (kind, len(full), err.strip())):
            continue
        selective(mac, problems, "dd/" + kind, p, full, "Folder/one.txt")
        selective(mac, problems, "dd/" + kind, p, full, "Folder")
        selective(mac, problems, "dd/" + kind, p, full, "beside.txt")
        ran += 1
    return ran


def now_cases(mac, tmp, problems):
    """Now Compress, whose entries are reached by stored offset — so a
    skip here costs nothing and must still land on the right entry."""
    tree_ = [
        synth_now.folder("Folder", [
            synth_now.file("one.txt", data=b"one's data fork\n",
                           rsrc=b"one's resource fork\n"),
            synth_now.file("two.txt", data=b"two's data fork\n",
                           rsrc=b"two's resource fork\n"),
        ]),
        synth_now.file("beside.txt", data=b"not in the folder\n"),
    ]
    p, _ = synth_now.write_one(tmp, "only-now", tree_)
    full, err = full_extract(mac, p)
    if not check(problems, len(full) == 5,
                 "now: the full extraction wrote %d files, expected 5 (%s)"
                 % (len(full), err.strip())):
        return 0
    selective(mac, problems, "now", p, full, "Folder/two.txt")
    selective(mac, problems, "now", p, full, "Folder")
    selective(mac, problems, "now", p, full, "beside.txt")
    return 1


# ------------------------------------------------------------------
# The corpus sweep
# ------------------------------------------------------------------

def sweep(mac, fixdir, stride, problems):
    """Real archives, sampled. Every format the corpus holds reaches
    this, including the ones that must DECODE an entry to skip past it."""
    names = sorted(f for f in os.listdir(fixdir)
                   if not f.endswith(".md") and
                   os.path.isfile(os.path.join(fixdir, f)))
    ran = skipped = 0
    for n in names[::stride]:
        path = os.path.join(fixdir, n)
        try:
            full, err = full_extract(mac, path)
        except subprocess.TimeoutExpired:
            skipped += 1
            continue
        # A name the filesystem shortened is no longer the name --only
        # matches against, so this fixture cannot source its selectors
        # from disk.
        if "did not fit and" in err or len(full) < 3:
            skipped += 1
            continue
        # Data forks only: a sidecar is not an entry of its own, it
        # rides along with the entry whose fork it is.
        picks = [p for p in sorted(full) if not p.endswith(".rsrc")]
        if len(picks) < 2:
            skipped += 1
            continue
        for sel in (picks[0], picks[len(picks) // 2]):
            try:
                selective(mac, problems, n, path, full, sel)
            except subprocess.TimeoutExpired:
                problems.append("%s: --only %r timed out" % (n, sel))
        ran += 1
    return ran, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default="build/macextract")
    ap.add_argument("--fixtures", default="fixtures")
    ap.add_argument("--stride", type=int, default=16,
                    help="sweep every Nth fixture (1 = all of them)")
    args = ap.parse_args()

    if not os.path.exists(args.macextract):
        print("only: no CLI at %s" % args.macextract)
        return 1

    problems = []
    ran = 0
    tmp = tempfile.mkdtemp()
    try:
        ran += zip_cases(args.macextract, tmp, problems)
        ran += dd_cases(args.macextract, tmp, problems)
        ran += now_cases(args.macextract, tmp, problems)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    swept = skipped = 0
    if os.path.isdir(args.fixtures):
        swept, skipped = sweep(args.macextract, args.fixtures, args.stride,
                               problems)
    else:
        print("only: no %s/, corpus sweep skipped" % args.fixtures)

    for p in problems:
        print("ONLY FAIL " + p)
    print("only: %d generated case(s), %d fixture(s) swept, %d passed over, "
          "%d problem(s)" % (ran, swept, skipped, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

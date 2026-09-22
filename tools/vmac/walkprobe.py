#!/usr/bin/env python3
"""walkprobe.py — what can each volume walk in this tree SEE?

Harnesses here read a Macintosh volume back — with `hls`, and two of
them with `hdir` — and grade what the application under test wrote onto
it. They do not agree about what a listing contains, and on 2026-09-22 that stopped being a style
question: `os9.py` reported a file MISSING that was on the volume the
whole time, 51,781 bytes of resource fork, because **`hls` hides a file
whose Finder INVISIBLE bit is set unless it is given `-a`** — so an
invisible entry was invisible to the COMPARISON as well as to the
Finder.

This builds one volume holding the four shapes that distinguish the
walks, runs every walk in the tree against it, and says which ones came
back short. It needs no emulator, no ROM and no X server; it is seconds.

    tools/vmac/walkprobe.py            # the table
    tools/vmac/walkprobe.py --check    # and assert it against EXPECT

**Four columns, because there are four blindnesses, and they are not
independent.** A walk can fail to see an invisible FILE; it can fail to
descend into a FOLDER; it can fail on an invisible FOLDER, which is
BOTH at once and is not implied by passing either; and it can drop a
LOCKED file, which has nothing to do with `-a` at all.

Until 2026-09-22 this probe could only report the first: the volume has
always carried the same four subjects inside `Folder`, but the verdict
compared leaf NAMES and the folder holds the same four names as the
root, so a walk returning two entries scored what a walk returning
eight did. Four of the eight never descend. That is not automatically a
defect — see `EXPECT_FLAT` — but it was not being stated either.

**The third and fourth columns are here because the volumes in
`~/.cache/macextract/vmac` hold both shapes and no probe had asked.**
Now QuickFiler writes `[Now QuickFiler Folder]` onto the volume it is
compressing on, and that folder is INVISIBLE while the database inside
it is not — the crossed cell, on six of the kept `specimens/now/*`
work volumes. And the Norton DiskDoubler Pro floppy carries
`[DiskExpress Activity Log]`, which is invisible AND locked. Measured
here, both directions, so neither is quoted:

    invisible directory   -> hidden by `hls` and `hdir` alike without -a
    locked file           -> listed by both, but `hdir` prints it `F`

That second line is the one that bites: `cptsegment.read_volume` and
`cptcrypt.read_volume` keep a listing line with `line.startswith("f")`,
which is a directory test that also throws away every locked file.

**And two of the eight were not here at all**, because they list with
`hdir` rather than `hls` and a grep for `hls` does not find them.
`hdir` hides the invisible bit exactly as `hls` does and takes the same
`-a`, which this re-derives on every run.

**The dot has nothing to do with it, and believing it did is how this
spread.** `checkdisk.py` has carried `-a` since it was written, with a
comment saying hfsutils hides names beginning with a dot — so every
later harness whose subject had no dotfiles could skip the flag and look
safe. Measured here as a 2x2, all four cells:

    leading dot, visible      -> listed without -a
    leading dot, INVISIBLE    -> hidden without -a
    no dot,      visible      -> listed without -a
    no dot,      INVISIBLE    -> hidden without -a

`.DS_Store` needed `-a` because a Macintosh writes it invisible, not
because of its name. The wrong explanation is what made the blind spot
look like somebody else's problem.

**What this cannot see.** Whether a walk that is blind here has ever
actually LOST anything: that depends on whether the application it
grades writes an invisible file, which is a question about each
application and not about the walk. Two readings answer it, and neither
is this probe: `lsar -j` prints `XADFinderFlags` for every archive in
the corpus, and every mountable image in `~/.cache/macextract/vmac`
can be listed twice, with `-a` and without. That is how
`[Now QuickFiler Folder]` was found — an invisible folder Now QuickFiler
writes onto the volume under test — and it is why the hidden-folder
column exists at all (DECISIONS.md 2026-09-22, *the folder the
application wrote and no walk could see*).

It also says nothing about the cost of fixing one — adding `-a` surfaces
the Finder's own invisible bookkeeping (`Desktop`, `Desktop DB`,
`Desktop DF`) on any volume a booted Mac has touched, so a walk whose
caller compares fork SETS needs a filter as well as a flag. Nor can it
see what `-a` BREAKS: making `Icon\r` reachable is what exposed a
`text=True` universal-newline bug in two walks, and only re-running the
harness finds that. OPEN_ITEMS.md, *One volume walk that cannot see an
invisible file*.

Nor can it see a walk it does not know about. Its own inventory is the
thing most likely to be wrong here, and it has been wrong once: for the
first day of its life this file said it ran "every walk in the tree"
while listing six of eight.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

INVISIBLE = 0x4000

# The four shapes, and what each one is for.
SUBJECTS = [
    ("Plain",   0,         b"visible data"),   # the control: everyone sees it
    ("Hidden",  INVISIBLE, b"invisible data"),  # the Finder invisible bit
    (".dotted", 0,         b"dotted data"),    # the dot, WITHOUT the bit
    ("Icon\r",  INVISIBLE, b""),               # a custom folder icon: both,
                                               # plus a name ending in a
                                               # control character
]
NAMES = {n for n, _f, _d in SUBJECTS}

# The folder the same four subjects are copied into, so that DEPTH is a
# column and not an assumption.
FOLDER = "Folder"

# And the same four again inside an INVISIBLE folder — the cell where the
# two blindnesses cross, and the one shape on this machine that a real
# application actually writes: `[Now QuickFiler Folder]`, invisible, with a
# visible database inside it, on six of the kept `specimens/now/*` work
# volumes. Passing either of the first two columns does not imply passing
# this one: `diskdoubler.volume_files` descends and is blind, so it walks
# straight past a folder it cannot see.
FOLDER_INV = "Hidden Folder"

# A LOCKED file at the root, visible, with no invisible bit. `hls` lists it
# either way; `hdir` prints it with a leading `F` rather than `f`, which is
# what makes a `line.startswith("f")` directory test drop it. Nothing to do
# with `-a`, which is why it needs its own subject.
LOCKED = "Locked"

# Which walks cannot see an INVISIBLE file today. A walk that leaves this
# list has been fixed; one that joins it has regressed. Either way the set
# here is meant to be changed deliberately.
# `arcmac.read_volume` left it on 2026-09-22, and `nowcompress`, the two
# Compact Pro walks and `diskdoubler.volume_files` the same day.
# `superdisk.read_forks` is last on purpose: ~30 callers across nine
# harnesses, several of which compare fork SETS.
EXPECT_BLIND = {
    "superdisk.read_forks",
}

# And which never descend into a folder. This is a SECOND blindness and it
# was not being measured at all: the volume has carried the same four
# subjects inside `Folder` since the probe was written, but the verdict
# compared leaf NAMES, and the folder holds the same four names as the
# root — so a walk that returned two entries and a walk that returned eight
# both scored 4/4. Measured 2026-09-22, the day the column was added.
#
# Root-only is not automatically a defect: both of these read volumes that
# `make_volume` builds flat and that one guest application writes to, and
# neither has ever made a folder. It is recorded so that the day one does,
# the probe says so rather than the harness reporting a file MISSING.
EXPECT_FLAT = {
    "arcmac.read_volume",
    "nowcompress.read_volume",
    "cptsegment.read_volume",
    "cptcrypt.read_volume",
}

# Which never reach a subject inside an INVISIBLE folder. Failing this is
# implied by being in either set above, but passing both does NOT imply
# passing here — a walk has to descend AND pass `-a` — so it is kept as its
# own line rather than derived. Measured 2026-09-22.
EXPECT_NO_HIDDEN_DIR = {
    "arcmac.read_volume",
    "nowcompress.read_volume",
    "superdisk.read_forks",
    "cptsegment.read_volume",
    "cptcrypt.read_volume",
}
# Four of those five are in it because they never descend at all, which is
# a recorded property and not a defect. `superdisk.read_forks` is the one
# that is there on its own merits: it descends, and walks straight past a
# folder it cannot see. `diskdoubler.volume_files` was the second until it
# took `-a` on 2026-09-22, which is what makes this column worth having —
# passing the first two does not imply passing this one.

# And which drop a LOCKED file. This is not `-a`: `hdir` lists it, with a
# leading `F`, and the two walks that keep a line on `line.startswith("f")`
# throw it away along with the directories that test is aimed at.
# Measured 2026-09-22.
# Empty since the two Compact Pro walks were fixed on 2026-09-22, and
# kept because it fails in the OTHER direction: the day a walk starts
# keeping a listing line on `startswith("f")` again, this says so. It has
# failed both ways already — it named those two before the fix and named
# them again, as gains, after it.
EXPECT_NO_LOCKED = set()


def build(img):
    """A 1.4 MB HFS volume carrying every shape the four columns need:
    the four subjects at the root, the same four inside a visible folder,
    the same four again inside an INVISIBLE one, and a locked file.

    The invisible folder is made invisible with `hattrib +i`, and the
    locked file locked with `hattrib +l` — the two attributes hfsutils can
    set that a MacBinary header cannot carry.
    """
    from arcmac import macbinary, make_rsrc                 # noqa: E402
    work = tempfile.mkdtemp(prefix="walkprobe-")
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        bins = []
        for name, flags, data in SUBJECTS:
            p = os.path.join(work, name.replace("\r", "CR") + ".bin")
            open(p, "wb").write(
                macbinary(name, "TEXT", "ttxt", data, make_rsrc(), flags))
            bins.append(p)
        locked = os.path.join(work, LOCKED + ".bin")
        open(locked, "wb").write(
            macbinary(LOCKED, "TEXT", "ttxt", b"locked data", make_rsrc(), 0))
        open(img, "wb").truncate(1400 * 1024)
        subprocess.run(["hformat", "-l", "Probe", img], check=True,
                       capture_output=True, env=env)
        subprocess.run(["hmount", img], check=True, capture_output=True,
                       env=env)
        for b in bins:
            subprocess.run(["hcopy", "-m", b, "Probe:"], check=True,
                           capture_output=True, env=env)
        for folder in (FOLDER, FOLDER_INV):
            subprocess.run(["hmkdir", "Probe:" + folder], check=True,
                           capture_output=True, env=env)
            for b in bins:
                subprocess.run(["hcopy", "-m", b, "Probe:%s:" % folder],
                               check=True, capture_output=True, env=env)
        subprocess.run(["hattrib", "+i", "Probe:" + FOLDER_INV], check=True,
                       capture_output=True, env=env)
        # The locked file goes on LAST: hfsutils will not write into a
        # locked item, and +l on the file itself is what the column needs.
        subprocess.run(["hcopy", "-m", locked, "Probe:"], check=True,
                       capture_output=True, env=env)
        subprocess.run(["hattrib", "+l", "Probe:" + LOCKED], check=True,
                       capture_output=True, env=env)
        subprocess.run(["humount"], capture_output=True, env=env)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(env["HOME"], ignore_errors=True)
    return img


def hls_2x2(img):
    """The measurement that says what `-a` is actually for. Returns the
    four cells so the claim is re-derived on every run rather than
    quoted."""
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        subprocess.run(["hmount", img], capture_output=True, env=env)
        seen = {}
        for flag in ("", "-a"):
            args = ["hls"] + ([flag] if flag else []) + ["-1"]
            out = subprocess.run(args, capture_output=True, env=env).stdout
            seen[flag] = {x.decode("mac_roman")
                          for x in out.split(b"\n") if x}
        subprocess.run(["humount"], capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    return seen


def listing_shapes(img):
    """The two facts the third and fourth columns rest on, re-derived.

    Returns (invisible_dir_hidden, locked_line_flag): whether `hdir` needs
    `-a` to show an invisible FOLDER — it does, exactly as for a file — and
    the leading character `hdir` gives a locked file, which is `F` and is
    the whole reason a `startswith("f")` test loses one.
    """
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        subprocess.run(["hmount", img], capture_output=True, env=env)
        plain = subprocess.run(["hdir", ":"], capture_output=True,
                               env=env).stdout.decode("mac_roman")
        alla = subprocess.run(["hdir", "-a", ":"], capture_output=True,
                              env=env).stdout.decode("mac_roman")
        subprocess.run(["humount"], capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    hidden = (FOLDER_INV not in plain) and (FOLDER_INV in alla)
    flag = "?"
    for line in alla.splitlines():
        if line.endswith(" " + LOCKED):
            flag = line.split()[0]
    return hidden, flag


def paths(x):
    """Whatever a walk returned, as a set of '/'-joined paths.

    The eight walks state their results four ways — a dict of leaf names, a
    dict of '/'-joined strings, a set of tuples of str, a set of tuples of
    BYTES — so this is where they are made comparable. Keeping the path
    rather than the leaf is what lets the two depth columns exist: four of
    the eight never descend, and a leaf-only comparison scores them the
    same as the four that do, because both folders hold the same four
    names as the root.
    """
    out = set()
    items = x.keys() if isinstance(x, dict) else x
    for k in items:
        if isinstance(k, (tuple, list)):
            k = "/".join(c.decode("mac_roman", "replace")
                         if isinstance(c, bytes) else str(c) for c in k)
        elif isinstance(k, bytes):
            k = k.decode("mac_roman", "replace")
        out.add(str(k))
    return out


def leaves(x):
    """Whatever a walk returned, as a set of leaf names."""
    return {p.rsplit("/", 1)[-1] for p in paths(x)}


def walks(img):
    """(label, paths) for every volume walk in this tree.

    Imported rather than reimplemented, so this measures the code the
    harnesses actually run.
    """
    got = []

    import arcmac
    d = tempfile.mkdtemp()
    got.append(("arcmac.read_volume", paths(arcmac.read_volume(img, d))))
    shutil.rmtree(d, ignore_errors=True)

    import nowcompress
    d = tempfile.mkdtemp()
    got.append(("nowcompress.read_volume",
                paths(nowcompress.read_volume(img, d))))
    shutil.rmtree(d, ignore_errors=True)

    import diskdoubler
    got.append(("diskdoubler.volume_files",
                paths(diskdoubler.volume_files(img))))

    import superdisk
    got.append(("superdisk.read_forks", paths(superdisk.read_forks(img))))

    # These two read with `hdir` rather than `hls`, which is why they were
    # not in this table until 2026-09-22 — a grep for `hls` does not find
    # them. `hdir` hides the invisible bit exactly as `hls` does, and takes
    # the same `-a`: measured here, 3 lines against 5 on this volume.
    # Both take a `skip` set of the names the harness put there itself;
    # nothing is skipped here.
    import cptsegment
    d = tempfile.mkdtemp()
    got.append(("cptsegment.read_volume",
                paths(cptsegment.read_volume(img, d, set()))))
    shutil.rmtree(d, ignore_errors=True)

    import cptcrypt
    d = tempfile.mkdtemp()
    got.append(("cptcrypt.read_volume",
                paths(cptcrypt.read_volume(img, d, set()))))
    shutil.rmtree(d, ignore_errors=True)

    import checkdisk
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    subprocess.run(["hmount", img], capture_output=True, env=env)
    got.append(("checkdisk.walk", paths(checkdisk.walk(env, (), 0))))
    subprocess.run(["humount"], capture_output=True, env=env)
    shutil.rmtree(env["HOME"], ignore_errors=True)

    import os9
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    subprocess.run(["hmount", img], capture_output=True, env=env)
    got.append(("os9._walk_volume", paths(os9._walk_volume(env))))
    subprocess.run(["humount"], capture_output=True, env=env)
    shutil.rmtree(env["HOME"], ignore_errors=True)

    return got


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="assert all four sets against their EXPECT_*")
    ap.add_argument("--keep", action="store_true", help="keep the volume")
    args = ap.parse_args()

    # hfsutils is what this whole probe is made of. Skip rather than fail
    # where it is absent, the way every other generated suite in ci.sh
    # does — a missing tool is not a regression.
    missing = [t for t in ("hformat", "hmount", "hcopy", "hmkdir", "hattrib",
                           "hls", "hdir", "humount") if not shutil.which(t)]
    if missing:
        print("walkprobe: SKIP — no %s" % ", ".join(missing))
        return 0

    work = tempfile.mkdtemp(prefix="walkprobe-img-")
    img = os.path.join(work, "probe.img")
    try:
        build(img)
        cells = hls_2x2(img)
        print("what `-a` is for, re-derived:")
        for name, flags, _d in SUBJECTS:
            print("  %-10s dot=%-3s invisible=%-3s  hls -1: %-6s  "
                  "hls -a -1: %s"
                  % (name.replace("\r", "\\r"),
                     "yes" if name.startswith(".") else "no",
                     "yes" if flags else "no",
                     "shown" if name in cells[""] else "HIDDEN",
                     "shown" if name in cells["-a"] else "HIDDEN"))
        dot_only = {n for n, f, _ in SUBJECTS if n.startswith(".") and not f}
        if not dot_only <= cells[""]:
            print("  NOTE: a dotted name was hidden WITHOUT the invisible "
                  "bit — the dot claim would be back")

        hidden_dir, locked_flag = listing_shapes(img)
        print("\nand what the other two columns rest on, re-derived:")
        print("  an INVISIBLE folder      hdir: %s   hdir -a: shown"
              % ("HIDDEN" if hidden_dir else "shown — the claim would be "
                 "back"))
        print("  a LOCKED file            hdir prints it %r, not 'f'"
              % locked_flag)

        print("\nwhat each walk sees, of %d subjects at the root, the same "
              "%d in a folder,\nthe same %d in an INVISIBLE folder, and one "
              "locked file:" % (len(NAMES), len(NAMES), len(NAMES)))
        blind, flat, nohid, nolock = set(), set(), set(), set()
        for label, seen in walks(img):
            root = {p for p in seen if "/" not in p}
            deep = {p.split("/", 1)[1] for p in seen
                    if p.startswith(FOLDER + "/")}
            hid = {p.split("/", 1)[1] for p in seen
                   if p.startswith(FOLDER_INV + "/")}
            missed = sorted(NAMES - root)
            if missed:
                blind.add(label)
            if not deep:
                flat.add(label)
            if not hid:
                nohid.add(label)
            if LOCKED not in root:
                nolock.add(label)
            print("  %-26s root %d/%d  folder %d/%d  hidden folder %d/%d  "
                  "locked %s%s"
                  % (label, len(NAMES & root), len(NAMES),
                     len(NAMES & deep), len(NAMES),
                     len(NAMES & hid), len(NAMES),
                     "yes" if LOCKED in root else "NO",
                     "   MISSES " + ", ".join(repr(m) for m in missed)
                     if missed else ""))
        if not args.check:
            return 0
        bad = 0
        for got, want, what, gained, lost in (
                (blind, EXPECT_BLIND, "blind to an invisible file",
                 "newly blind", "no longer blind"),
                (flat, EXPECT_FLAT, "root-only",
                 "newly root-only", "now descends"),
                (nohid, EXPECT_NO_HIDDEN_DIR, "blind to an invisible folder",
                 "newly blind to one", "now reads one"),
                (nolock, EXPECT_NO_LOCKED, "dropping a locked file",
                 "newly dropping one", "now keeps one")):
            if got == want:
                print("walkprobe: %d walk(s) %s, exactly the recorded set"
                      % (len(got), what))
                continue
            bad = 1
            print("\nwalkprobe: the '%s' set MOVED" % what)
            for x in sorted(got - want):
                print("  %s: %s" % (gained, x))
            for x in sorted(want - got):
                print("  %s: %s — take it out of the EXPECT set" % (lost, x))
        return bad
    finally:
        if args.keep:
            print("\nvolume kept at %s" % img)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

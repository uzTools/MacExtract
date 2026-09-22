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

**Two columns, because there are two blindnesses.** A walk can fail to
see an invisible FILE, and it can fail to descend into a FOLDER, and
until 2026-09-22 this probe could only report the first: the volume has
always carried the same four subjects inside `Folder`, but the verdict
compared leaf NAMES and the folder holds the same four names as the
root, so a walk returning two entries scored what a walk returning
eight did. Two of the eight never descend. That is not automatically a
defect — see `EXPECT_FLAT` — but it was not being stated either.

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
application and not about the walk. It also says nothing about the cost
of fixing one — adding `-a` surfaces the Finder's own invisible
bookkeeping (`Desktop`, `Desktop DB`, `Desktop DF`) on any volume a
booted Mac has touched, so a walk whose caller compares fork SETS needs
a filter as well as a flag. OPEN_ITEMS.md, *Volume walks that cannot see
an invisible file*.

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

# Which walks cannot see an INVISIBLE file today. A walk that leaves this
# list has been fixed; one that joins it has regressed. Either way the set
# here is meant to be changed deliberately.
# `arcmac.read_volume` left it on 2026-09-22.
EXPECT_BLIND = {
    "nowcompress.read_volume",
    "diskdoubler.volume_files",
    "superdisk.read_forks",
    "cptsegment.read_volume",
    "cptcrypt.read_volume",
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


def build(img):
    """A 1.4 MB HFS volume with the four subjects at the root and the
    same four inside a folder, so a walk is tested at depth as well."""
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
        open(img, "wb").truncate(1400 * 1024)
        subprocess.run(["hformat", "-l", "Probe", img], check=True,
                       capture_output=True, env=env)
        subprocess.run(["hmount", img], check=True, capture_output=True,
                       env=env)
        for b in bins:
            subprocess.run(["hcopy", "-m", b, "Probe:"], check=True,
                           capture_output=True, env=env)
        subprocess.run(["hmkdir", "Probe:Folder"], check=True,
                       capture_output=True, env=env)
        for b in bins:
            subprocess.run(["hcopy", "-m", b, "Probe:Folder:"], check=True,
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


def paths(x):
    """Whatever a walk returned, as a set of '/'-joined paths.

    The four walks state their results four ways — a dict of leaf names, a
    dict of '/'-joined strings, a set of tuples of str, a set of tuples of
    BYTES — so this is where they are made comparable. Keeping the path
    rather than the leaf is what lets the depth column exist: two of the six
    never descend, and a leaf-only comparison scores them the same as the
    four that do, because the folder holds the same four names.
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
                    help="assert both sets against EXPECT_BLIND and EXPECT_FLAT")
    ap.add_argument("--keep", action="store_true", help="keep the volume")
    args = ap.parse_args()

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

        print("\nwhat each walk sees, of %d subjects at the root and the "
              "same %d in a folder:" % (len(NAMES), len(NAMES)))
        blind, flat = set(), set()
        for label, seen in walks(img):
            root = {p for p in seen if "/" not in p}
            deep = {p.split("/", 1)[1] for p in seen
                    if p.startswith(FOLDER + "/")}
            missed = sorted(NAMES - root)
            if missed:
                blind.add(label)
            if not deep:
                flat.add(label)
            print("  %-26s root %d/%d   folder %d/%d%s%s"
                  % (label, len(NAMES & root), len(NAMES),
                     len(NAMES & deep), len(NAMES),
                     "   MISSES " + ", ".join(repr(m) for m in missed)
                     if missed else "",
                     "   ROOT ONLY" if not deep else ""))
        if not args.check:
            return 0
        bad = 0
        if blind == EXPECT_BLIND:
            print("\nwalkprobe: %d walk(s) blind, exactly the recorded set"
                  % len(blind))
        else:
            bad = 1
            print("\nwalkprobe: the blind set MOVED")
            for x in sorted(blind - EXPECT_BLIND):
                print("  newly blind: %s" % x)
            for x in sorted(EXPECT_BLIND - blind):
                print("  no longer blind: %s — take it out of EXPECT_BLIND" % x)
        if flat == EXPECT_FLAT:
            print("walkprobe: %d walk(s) root-only, exactly the recorded set"
                  % len(flat))
        else:
            bad = 1
            print("\nwalkprobe: the root-only set MOVED")
            for x in sorted(flat - EXPECT_FLAT):
                print("  newly root-only: %s" % x)
            for x in sorted(EXPECT_FLAT - flat):
                print("  now descends: %s — take it out of EXPECT_FLAT" % x)
        return bad
    finally:
        if args.keep:
            print("\nvolume kept at %s" % img)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

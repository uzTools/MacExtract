#!/usr/bin/env python3
"""metarun.py — the metadata, end to end, on an emulated Macintosh.

    tools/vmac/metarun.py [--system System6.hfv|Sys7.img] [--sys30]
    tools/vmac/metarun.py --check RUNDIR       # grade disks a run kept

Extracts `synth-as-meta.as`, `synth-sqp-meta.pkg` and `nested.pkg` (made
per run: A/x, A/B/y, A/z with a date on each folder) with the autotest
build and `-D UNC_AT_DTCOMMENT` (tools/vmac/run.py, or sys30.py for the
System 3.0 tier), keeps the disks, and reads back what the shell wrote:

  the CATALOG of the output disk (tools/vmac/hfs_cat.py) — for the file
      in the AppleSingle: FInfo, FXInfo, all three dates and the locked
      bit; for the AppleLink package: the folder's DInfo and its three
      dates, AFTER two files were written inside it, and each file's FInfo
      and dates;
  the REPORT the autotest leaves on the input disk, whose `DTCM` trailer
      holds what PBHGetVolParms and PBDTGetPath answered on the output
      volume and each file's comment read back with PBDTGetComment.

The expected values are the synthesizers' input (tools/synth_as.py,
tools/synth_sqp.py) with the rules the shell applies on purpose: Finder
flag 0x0100 (inited) cleared on a file with a bundle and kept otherwise,
and FXInfo's fdComment and fdPutAway (a folder's frOpenChain too) cleared
(mac/macextract_mac.c, StampCat; DECISIONS.md 2026-10-17). The comment is
expected where the volume reports bHasDesktopMgr and absent where it does
not.

**What it cannot see.** The Finder: whether it then DRAWS an icon at the
position, opens the window at the rectangle, or shows the comment — none
of that is read here. A folder's comment (no fixture here gives a folder
one). Anything on a second volume or a 512 KB machine.
"""
import argparse
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import hfs_cat                                                  # noqa: E402
import synth_as                                                 # noqa: E402
import synth_sqp                                                # noqa: E402

EPOCH_2000 = 0xB492F400
FIX = ("synth-as-meta.as", "synth-sqp-meta.pkg", "nested.pkg")
# `nested.pkg` is generated per run into .tmp/ (nested_items): files
# written into a folder after one of its subfolders, A/x, A/B/y, A/z, with
# a date on each folder (DECISIONS.md 2026-10-17, *the date held once per
# folder*).


def nested_items():
    return [synth_sqp.item("A", folder=True, ctime=0xB0000000,
                           mtime=0xB0000001),
            synth_sqp.item("x", synth_sqp._text(200, 81), level=2),
            synth_sqp.item("B", folder=True, level=2, ctime=0xB0000010,
                           mtime=0xB0000002),
            synth_sqp.item("y", synth_sqp._text(200, 82), level=3),
            synth_sqp.item("z", synth_sqp._text(200, 83), level=2)]


def fixture_path(f):
    if f == "nested.pkg":
        p = os.path.join(REPO, ".tmp", "nested.pkg")
        open(p, "wb").write(synth_sqp.build(nested_items(), 1))
        return p
    return os.path.join(REPO, "fixtures", f)


def shell_finfo(b, flags=None):
    """The 16 bytes as the shell writes them: inited (0x0100) kept, unless
    the file has a bundle (0x2000), where it is cleared so the Finder
    registers it (DECISIONS.md 2026-10-17, *the bit that kept the
    position*)."""
    b = bytearray(b)
    f = (b[8] << 8) | b[9]
    if f & 0x2000:
        f &= ~0x0100
    b[8], b[9] = f >> 8, f & 0xFF
    return bytes(b)


def shell_fxinfo(b, is_dir=False):
    """FXInfo/DXInfo as the shell writes them: the source volume's comment
    id and put-away folder (+10..15) cleared, and a folder's open chain
    (+4..7)."""
    b = bytearray(b)
    for i in range(10, 16):
        b[i] = 0
    if is_dir:
        b[4:8] = b"\0\0\0\0"
    return bytes(b)


def expected():
    """{fixture: {path: {field: value}}} in hfs_cat's vocabulary."""
    c = synth_as.CASES["meta"]
    d = c["dates"]
    exp = {"synth-as-meta.as": {
        "Kept Whole": dict(
            finfo=shell_finfo(c["finfo"]).hex(),
            fxinfo=shell_fxinfo(c["fxinfo"]).hex(),
            cr=(d[0] + EPOCH_2000) & 0xFFFFFFFF,
            md=(d[1] + EPOCH_2000) & 0xFFFFFFFF,
            bk=(d[2] + EPOCH_2000) & 0xFFFFFFFF,
            locked=1, comment=c["comment"])}}
    items, version = synth_sqp.case_meta()
    e = {}
    for path, it in synth_sqp.paths(items, version):
        rec = synth_sqp._record(it, 0, 0, 0, 0, 0)
        w = dict(finfo=shell_finfo(rec[20:36]).hex(), cr=it["ctime"],
                 md=it["mtime"])
        if not it["folder"]:
            w["locked"] = 0
        e[path.replace("/", ":")] = w
    exp["synth-sqp-meta.pkg"] = e
    exp["nested.pkg"] = {"A": dict(cr=0xB0000000, md=0xB0000001),
                         "A:B": dict(cr=0xB0000010, md=0xB0000002),
                         "A:x": dict(locked=0), "A:B:y": dict(locked=0),
                         "A:z": dict(locked=0)}
    return exp


def read_trailer(indsk):
    """(volparms err, vMAttrib, dtgetpath err, [(name, err, comment)])
    from the autotest report on the input disk, or None."""
    import shutil
    import tempfile
    home = tempfile.mkdtemp(prefix="hfs-", dir=os.path.join(REPO, ".tmp"))
    env = dict(os.environ, HOME=home)
    rep = os.path.join(home, "report")
    try:
        subprocess.run(["hmount", indsk], capture_output=True, env=env)
        c = subprocess.run(["hcopy", "-r", "report", rep],
                           capture_output=True, env=env)
        subprocess.run(["humount"], capture_output=True, env=env)
        if c.returncode:
            return None
        b = open(rep, "rb").read()
    finally:
        shutil.rmtree(home, ignore_errors=True)

    def u32(o):
        return int.from_bytes(b[o:o + 4], "big")

    def s32(o):
        v = u32(o)
        return v - (1 << 32) if v & 0x80000000 else v
    if b[:4] != b"UNCR":
        return None
    o = 12 + 4 * u32(8)
    n = u32(o)
    o += 4
    names = []
    for _ in range(n):
        o += 4
        names.append(b[o + 1:o + 1 + b[o]].decode("mac-roman"))
        o += 1 + b[o]
    if b[o:o + 4] != b"DTCM":
        return None
    vperr, attrib, dterr = s32(o + 4), u32(o + 8), s32(o + 12)
    o += 16
    recs = []
    for nm in names:
        err, ln = s32(o), b[o + 4]
        recs.append((nm, err, b[o + 5:o + 5 + ln]))
        o += 5 + ln
    return vperr, attrib, dterr, recs


def check(rundir):
    exp = expected()
    bad, n = [], 0
    dirs = sorted(glob.glob(os.path.join(rundir, "fixture-*")))
    if len(dirs) != len(FIX):
        return ["%d fixture directories in %s, wanted %d"
                % (len(dirs), rundir, len(FIX))], 0
    for d in dirs:
        img = open(os.path.join(d, "out.dsk"), "rb").read()
        got = {r["path"]: r for r in hfs_cat.records(img)}
        # Which fixture this directory ran: the one whose first expected
        # path is on its disk (the directories' names are random).
        fx = next((f for f in FIX if next(iter(exp[f])) in got), None)
        if fx is None:
            bad.append("%s: holds neither fixture's output" % d)
            continue
        for path, want in exp[fx].items():
            g = got.get(path)
            if g is None:
                bad.append("%s: %s is not on the disk" % (fx, path))
                continue
            for k, v in want.items():
                if k == "comment":
                    continue
                n += 1
                if g[k] != v:
                    bad.append("%s: %s %s %s, wanted %s" % (
                        fx, path, k,
                        g[k] if isinstance(g[k], str) else "%08x" % g[k],
                        v if isinstance(v, str) else "%08x" % v))
        t = read_trailer(os.path.join(d, "in.dsk"))
        if t is None:
            bad.append("%s: no DTCM trailer in the report" % fx)
            continue
        vperr, attrib, dterr, recs = t
        hasdt = vperr == 0 and (attrib >> 12) & 1
        print("metarun: %s: PBHGetVolParms %d, vMAttrib 0x%08x, "
              "PBDTGetPath %d" % (fx, vperr, attrib, dterr))
        for nm, err, cm in recs:
            want = None
            for path, w in exp[fx].items():
                if path.split(":")[-1] == nm and "comment" in w:
                    want = w["comment"]
            print("metarun:   %-12s PBDTGetComment %d %r" % (nm, err, cm))
            if want is None:
                continue
            n += 1
            if hasdt and cm != want:
                bad.append("%s: %s comment %r, wanted %r" % (fx, nm, cm, want))
            if not hasdt and cm:
                bad.append("%s: %s has a comment on a volume with no "
                           "Desktop Manager" % (fx, nm))
    return bad, n


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", metavar="RUNDIR")
    ap.add_argument("--system", default="System6.hfv")
    ap.add_argument("--sys30", action="store_true",
                    help="the System 3.0 tier (tools/vmac/sys30.py)")
    ap.add_argument("--mem", default="4M")
    ap.add_argument("--out-kb", type=int,
                    help="output volume size (run.py --out-kb). System 7.0.1 "
                         "gives a 1,440 KB floppy no Desktop Manager "
                         "(vMAttrib 0xE0, measured 2026-10-17), so the "
                         "comment needs a larger one there")
    a = ap.parse_args()
    rundir = a.check
    if not rundir:
        drv = (["sys30.py", "--mem", a.mem] if a.sys30
               else ["run.py", "--mem", a.mem, "--system", a.system])
        cmd = [sys.executable, os.path.join(HERE, drv[0])] + drv[1:] + [
            "-D", "UNC_AT_DTCOMMENT", "--keep-disks"] + (
            [] if a.sys30 else ["--expect"]) + (
            ["--out-kb", str(a.out_kb)] if a.out_kb else []) + [
            fixture_path(f) for f in FIX]
        r = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        kept = [l.split("disks kept in ")[1].strip()
                for l in r.stdout.splitlines() if "disks kept in " in l]
        if not kept:
            print("metarun: the run kept no disks")
            return 1
        rundir = os.path.dirname(kept[0])
    bad, n = check(rundir)
    for b in bad:
        print("metarun: FAIL %s" % b)
    print("metarun: %d value(s) read back, %s" % (
        n, "all as the archive states" if not bad else "%d WRONG" % len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

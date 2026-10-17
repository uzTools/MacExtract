#!/usr/bin/env python3
"""metarun.py — the metadata, end to end, on an emulated Macintosh.

    tools/vmac/metarun.py [--system System6.hfv|Sys7.img] [--sys30]
    tools/vmac/metarun.py --check RUNDIR       # grade disks a run kept
    tools/vmac/metarun.py --expander [--check-expander RUNDIR]

Extracts `synth-as-meta.as`, `synth-sqp-meta.pkg`, `nested.pkg` (made
per run: A/x, A/B/y, A/z with a date on each folder) and `synth-macosx.zip`
(Mac OS X's sidecars, tools/synth_macosx.py) with the autotest
build and `-D UNC_AT_DTCOMMENT` (tools/vmac/run.py, or sys30.py for the
System 3.0 tier), keeps the disks, and reads back what the shell wrote:

  the CATALOG of the output disk (tools/vmac/hfscat.py) — for the file
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

`--expander` is StuffIt classic against StuffIt Expander 4.0.2's OWN
output: seven corpus archives that between them hold every writer class
and every rule of FORMATS.md's table (`SIT_PICK`), and the sentinel
archives Expander extracted whole, each run through the application and
every catalog record read back, then held field for field against the
record Expander wrote for the same entry (tools/vmac/sitmeta.py's
results): FInfo/DInfo, FXInfo/DXInfo, three dates, the lock. The one
difference expected is the shell's own, on purpose: inited (0x0100) is
cleared where the flags carry a bundle (0x2000), which Expander keeps
(DECISIONS.md 2026-10-17, *the bit that kept the position*).

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
import hfscat                                                   # noqa: E402
import synth_as                                                 # noqa: E402
import synth_sqp                                                # noqa: E402
import synth_macosx                                             # noqa: E402

EPOCH_2000 = 0xB492F400
FIX = ("synth-as-meta.as", "synth-sqp-meta.pkg", "nested.pkg",
       "synth-macosx.zip")
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
    """{fixture: {path: {field: value}}} in hfscat's vocabulary, paths below the volume."""
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
    # Mac OS X's sidecars, put on their files (tools/synth_macosx.py): the
    # whole Finder info of each, the folder's DInfo/DXInfo, and Meta's RFC
    # 1740 entries — its dates, its lock and its comment.
    m = synth_macosx.describe("zip")["emit"]
    e = {}
    for path, w in m.items():
        g = {}
        if w["finfo"] != "-":
            g["finfo"] = shell_finfo(bytes.fromhex(w["finfo"])).hex()
            g["fxinfo"] = shell_fxinfo(bytes.fromhex(w["fxinfo"]),
                                       path == "Folder").hex()
        if path != "Folder":
            g["locked"] = 1 if w["lock"] == "L" else 0
        if w["comment"] != "-":
            g["comment"] = bytes.fromhex(w["comment"])
        e[path.replace("/", ":")] = g
    md = synth_macosx.META_DATES
    e["Folder:Meta"].update(cr=(md[0] + EPOCH_2000) & 0xFFFFFFFF,
                            md=(md[1] + EPOCH_2000) & 0xFFFFFFFF,
                            bk=(md[2] + EPOCH_2000) & 0xFFFFFFFF)
    exp["synth-macosx.zip"] = e
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
        got = {r["rel"]: r for r in hfscat.records(img)}
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


# StuffIt classic archives for --expander, chosen 2026-10-17 as the fewest
# small corpus archives that hold every writer class (version byte, 0x0986,
# name CRC) and every rule: a placed file, a (-1,-1) one, a locked one,
# flags 0x0001, a bundle, inited without a name CRC, a nested folder, a
# rectangle, a scroll, a view under version 1.
SIT_PICK = ("derived-Indexer_Script_1.0.sit", "derived-Fractional_Widths.sit",
            "derived-MacOS_Permissions_Lister_1..sit", "derived-ttxt_XTND.sit",
            "derived-DL111.sit", "derived-naffs7.sit", "derived-DEF.sit")


def sit_cases():
    """{archive name: (path to run, [(archive path tuple, kind, record)])}
    for SIT_PICK and every sentinel archive Expander extracted whole."""
    import run_meta
    sys.path.insert(0, os.path.join(REPO, "tools"))
    tmp = os.path.join(REPO, ".tmp", "metarun-sit")
    os.makedirs(tmp, exist_ok=True)
    out = {}
    for tag, a in run_meta.sitmeta_results():
        name = a["fixture"]
        if not (name in SIT_PICK or name.startswith("synth-")):
            continue
        ents = [e for e in a["entries"] if e["kind"] != "end"]
        if any("match" not in e for e in ents):
            continue
        blob = run_meta.sit_archive(a)
        if blob is None:
            continue
        p = os.path.join(tmp, name)
        open(p, "wb").write(blob)
        out[name] = (p, [(tuple(bytes.fromhex(x) for x in e["path"]),
                          e["kind"], bytes.fromhex(e["match"]["rec"]))
                         for e in ents])
    return out


def shell_rec(kind, rec):
    """Expander's record as the shell is meant to write it: the bundle
    rule, and FXInfo's source-volume ids cleared (0 in all Expander wrote,
    so the second changes nothing; it is stated so a change would show)."""
    b = bytearray(rec)
    fo = 4 + 8 if kind == "file" else 22 + 8
    f = (b[fo] << 8) | b[fo + 1]
    if f & 0x2000:
        f &= ~0x0100
    b[fo], b[fo + 1] = f >> 8, f & 0xFF
    xo = 56 if kind == "file" else 38
    b[xo + 10:xo + 16] = bytes(6)
    if kind == "dir":
        b[xo + 4:xo + 8] = bytes(4)
    return bytes(b)


SIT_FIELDS = {"file": (("FInfo", 4, 16), ("FXInfo", 56, 16), ("locked", 2, 1),
                       ("cr", 44, 4), ("md", 48, 4), ("bk", 52, 4)),
              "dir": (("DInfo", 22, 16), ("DXInfo", 38, 16), ("cr", 10, 4),
                      ("md", 14, 4), ("bk", 18, 4))}


def check_expander(rundir, cases, control=False):
    """Every entry of every archive the run kept, against Expander's
    record. With `control`, the expected records are Expander's with the
    shell's rule NOT applied and one field shifted, and must fail."""
    import json
    runs = json.load(open(os.path.join(rundir, "metarun-sit.json")))
    bad, n = [], 0
    for name, workdir in runs.items():
        _p, ents = cases[name]
        img = os.path.join(workdir, "out.dsk")
        if not os.path.exists(img):
            bad.append("%s: no output disk" % name)
            continue
        got = {}
        for r in hfscat.records(open(img, "rb").read()):
            got[(r["path"][1:], r["kind"])] = r["rec"]
        for path, kind, rec in ents:
            want = rec if control else shell_rec(kind, rec)
            if control:
                want = want[:5] + bytes([want[5] ^ 1]) + want[6:]
            g = got.get((path, hfscat.FILE if kind == "file"
                         else hfscat.DIR))
            label = "%s: %s" % (name, b":".join(path).decode("mac-roman"))
            if g is None:
                bad.append("%s is not on the disk" % label)
                continue
            for f, off, size in SIT_FIELDS[kind]:
                n += 1
                gv, wv = g[off:off + size], want[off:off + size]
                if f == "locked":
                    gv, wv = bytes([gv[0] & 1]), bytes([wv[0] & 1])
                if gv != wv:
                    bad.append("%s: %s %s, Expander %s"
                               % (label, f, gv.hex(), wv.hex()))
    return bad, n


def run_expander(a):
    import json
    cases = sit_cases()
    if not cases:
        print("metarun: no sitmeta.py results; nothing to grade")
        return 1
    names = sorted(cases)
    cmd = [sys.executable, os.path.join(HERE, "run.py"), "--mem", a.mem,
           "--system", a.system, "--keep-disks", "--expect",
           "--out-kb", str(a.out_kb or 4096)] + [cases[n][0] for n in names]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    runs, last, verdicts = {}, None, {}
    for line in r.stdout.splitlines():
        f = line.split()
        if len(f) > 1 and f[1] in cases:
            last = f[1]
            verdicts[last] = f[0]
        if "disks kept in " in line and last:
            runs[last] = line.split("disks kept in ")[1].strip()
            last = None
    if not runs:
        print("metarun: the run kept no disks")
        return 1
    rundir = os.path.dirname(next(iter(runs.values())))
    json.dump(runs, open(os.path.join(rundir, "metarun-sit.json"), "w"),
              indent=1)
    # The forks too: run.py's own verdict, the grid against this engine's
    # Linux output (--expect).
    failed = sorted(n for n in names if verdicts.get(n) != "PASS")
    for n in failed:
        print("metarun: FAIL %s: run.py says %s" % (n, verdicts.get(n)))
    return grade_expander(rundir, cases, len(names)) or bool(failed)


def grade_expander(rundir, cases, want_n):
    import json
    runs = json.load(open(os.path.join(rundir, "metarun-sit.json")))
    bad, n = check_expander(rundir, cases)
    if len(runs) != want_n:
        bad.append("%d archives ran of %d" % (len(runs), want_n))
    cbad, _cn = check_expander(rundir, cases, control=True)
    for b in bad:
        print("metarun: FAIL %s" % b)
    print("metarun: Expander 4.0.2, %d archive(s), %d value(s) read back, "
          "%s; the control (Expander's records less the shell's rule, one "
          "byte shifted) disagrees on %d" % (
              len(runs), n, "all as Expander wrote them" if not bad
              else "%d WRONG" % len(bad), len(cbad)))
    if not cbad:
        print("metarun: FAIL the control passed: the comparison compares "
              "nothing")
        return 1
    return 1 if bad else 0


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
    ap.add_argument("--expander", action="store_true",
                    help="StuffIt classic against Expander 4.0.2's own "
                         "output (see above)")
    ap.add_argument("--check-expander", metavar="RUNDIR")
    a = ap.parse_args()
    if a.check_expander:
        cases = sit_cases()
        return grade_expander(a.check_expander, cases, len(cases))
    if a.expander:
        return run_expander(a)
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

#!/usr/bin/env python3
"""run_meta.py — the engine's Finder metadata beyond type, creator and flags.

    tools/run_meta.py [--cli build/macextract] [--corpus] [--expander]

`macextract l --meta` prints, per entry, the FInfo/DInfo and FXInfo/DXInfo
bytes, the backup date, the lock and the Get Info comment the engine
delivers (cli/main.c, print_meta). This holds those rows to something
other than the engine:

  synth-as-meta.as, synth-as-dosro.as   `lsar` (XADMaster's AppleSingle
      parser) for the 32 bytes of Finder info, the comment and the backup
      date; tools/synth_as.py --describe for the lock, which XADMaster has
      no key for, and for the one place this engine and XADMaster differ
      by design: a backup date of 0x80000000 is the RFC's "unknown"
      (reference/notes/rfc1740.txt), which XADMaster reports as 2068.
  synth-sqp-meta.pkg                    tools/synth_sqp.py's own items —
      `lsar` does not read AppleLink packages at all.
  DiskDoubler 3.7's own file            the catalog record the subject had
      before 3.7 compressed it (tools/vmac/ddmeta.py --writer's result;
      skipped, and said so, where it is absent).
  --corpus                              every fixture: wherever the engine
      states a field and `lsar` reports the same field, they must agree.
  --expander                            StuffIt classic, against StuffIt
      Expander 4.0.2's OWN output: the catalog records tools/vmac/sitmeta.py
      read back off the disk Expander wrote, for every corpus archive and
      sentinel archive it ran (its results directory; skipped, and said so,
      where that is absent). Per entry, a file's FInfo, FXInfo, backup date
      and lock and a folder's DInfo, DXInfo and backup date must be what
      Expander wrote, field for field. A field the engine leaves unstated
      (`-`) counts as what a host writes on a new file: zero, unlocked.
      An archive Expander did not extract whole is left out, by name, as
      sitmeta.py's model check leaves it out.

Then a CONTROL per field: the engine's row is tampered with, one field at
a time, and the comparison must fail — or it was comparing nothing.

**What it cannot see.** With --expander: the dates (not in `l --meta`),
what the SHELL then writes (tools/vmac/sitgrade.py runs the application),
and any StuffIt reader but Expander 4.0.2. Otherwise: anything the engine does not deliver: an entry
whose archive stores a field this engine does not read yet prints `-` and
passes (the inventory of those is OPEN_ITEMS.md's). The lock, against any
reader but the synthesizer. Whether a host WRITES any of it: that is
tests/mac_sink_test.c --meta, and on an emulated Mac tools/vmac/hfscat.py.
"""
import argparse
import calendar
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
MAC_EPOCH = 2082844800                       # 1904-01-01 to 1970-01-01


def meta_rows(cli, path):
    r = subprocess.run([cli, "l", "--meta", path], capture_output=True)
    out = {}
    for line in r.stdout.decode("utf-8", "surrogateescape").splitlines():
        if not line.startswith("m "):
            continue
        f = line.split(" ", 6)
        out[f[6]] = dict(finfo=f[1], fxinfo=f[2], backup=f[3], lock=f[4],
                         comment=f[5])
    return out


def lsar_rows(path):
    r = subprocess.run(["lsar", "-j", path], capture_output=True)
    try:
        d = json.loads(r.stdout)
    except ValueError:
        return {}
    out = {}
    for e in d.get("lsarContents", []):
        if e.get("XADIsResourceFork") and e["XADFileName"] in out:
            continue                   # the data fork's row already holds it
        o = {}
        fi = e.get("XADFinderInfo")
        if fi is not None:
            b = fi.encode("latin-1")
            if len(b) >= 16:
                o["finfo"] = b[:16].hex()
            if len(b) >= 32:
                o["fxinfo"] = b[16:32].hex()
        if "XADComment" in e:
            o["comment"] = e["XADComment"].encode("mac-roman").hex()
        if "XADLastBackupDate" in e:
            t = calendar.timegm(time.strptime(e["XADLastBackupDate"][:19],
                                              "%Y-%m-%d %H:%M:%S"))
            o["backup"] = "%08x" % ((t + MAC_EPOCH) & 0xFFFFFFFF)
        out[e["XADFileName"]] = o
    return out


def compare(name, got, want, fields):
    bad = []
    for k in fields:
        if k in want and got.get(k) != want[k]:
            bad.append("%s: %s %s, wanted %s" % (name, k, got.get(k), want[k]))
    return bad


def expectations(cli):
    """[(fixture, {entry: {field: value}}, fields)]"""
    import synth_as
    import synth_sqp
    out = []
    for case in ("meta", "dosro"):
        fx = os.path.join(REPO, "fixtures", "synth-as-%s.as" % case)
        d = synth_as.describe(case)
        want = lsar_rows(fx)
        w = want.setdefault(d["name"], {})
        w["lock"] = d["locked"]
        # The design difference, stated once: the RFC's unknown.
        if d["backup"] is None:
            w["backup"] = "-"
        out.append((fx, want, ("finfo", "fxinfo", "comment", "backup",
                               "lock")))
    fx = os.path.join(REPO, "fixtures", "synth-sqp-meta.pkg")
    items, version = synth_sqp.case_meta()
    want = {}
    for path, it in synth_sqp.paths(items, version):
        rec = synth_sqp._record(it, 0, 0, 0, 0, 0)
        want[path] = {"finfo": rec[20:36].hex()}
    out.append((fx, want, ("finfo",)))
    # DiskDoubler 3.7's own compressed file (tools/vmac/ddmeta.py --writer),
    # against the catalog record it was compressed FROM: the FInfo whole,
    # the location 3.7's own Expand does not put back included.
    w = os.path.join(os.path.dirname(VMAC_HOME()), "sitmeta", "dd",
                     "writer.json")
    if os.path.exists(w):
        d = json.load(open(w))
        fx = os.path.join(REPO, ".tmp", "run_meta", "dd37-writer.dd")
        os.makedirs(os.path.dirname(fx), exist_ok=True)
        open(fx, "wb").write(bytes.fromhex(d["data"]))
        out.append((fx, {"dd37-writer": {
            "finfo": bytes.fromhex(d["before"])[4:20].hex()}}, ("finfo",)))
    else:
        print("run_meta: DiskDoubler 3.7's specimen SKIPPED: no %s" % w)
    return out


def VMAC_HOME():
    sys.path.insert(0, os.path.join(HERE, "vmac"))
    import run as R
    return R.VMAC_HOME


def corpus(cli):
    """Every fixture where the engine states a field lsar also reports."""
    bad, compared = [], 0
    fdir = os.path.join(REPO, "fixtures")
    for fn in sorted(os.listdir(fdir)):
        p = os.path.join(fdir, fn)
        if not os.path.isfile(p):
            continue
        rows = meta_rows(cli, p)
        stated = {n: {k: v for k, v in r.items() if v != "-"}
                  for n, r in rows.items()}
        if not any(stated.values()):
            continue
        oracle = lsar_rows(p)
        for n, r in stated.items():
            o = oracle.get(n)
            if o is None and len(oracle) == 1 and len(rows) == 1:
                # One entry each, named apart: a name-less AppleDouble
                # takes the host's file name, less `.ad`, here, and lsar
                # keeps it whole.
                o = next(iter(oracle.values()))
            if o is None:
                continue
            for k in ("finfo", "fxinfo", "comment", "backup"):
                if k in r and k in o:
                    compared += 1
                    if r[k] != o[k]:
                        bad.append("%s: %s: %s %s, lsar %s"
                                   % (fn, n, k, r[k], o[k]))
    return bad, compared


def meta_list(cli, path):
    """`l --meta`, in archive order: [(name, row)]."""
    r = subprocess.run([cli, "l", "--meta", path], capture_output=True)
    out = []
    for line in r.stdout.decode("utf-8", "surrogateescape").splitlines():
        if line.startswith("m "):
            f = line.split(" ", 6)
            out.append((f[6], dict(finfo=f[1], fxinfo=f[2], backup=f[3],
                                   lock=f[4])))
    return out


def sitmeta_results():
    """[(tag, archive result)] from tools/vmac/sitmeta.py's results
    directory, corpus and sentinel boots only."""
    import glob
    sys.path.insert(0, os.path.join(HERE, "vmac"))
    import sitmeta
    out = []
    for p in sorted(glob.glob(os.path.join(sitmeta.RESULTS, "*.json"))):
        r = json.load(open(p))
        if r["tag"].startswith(("corpus", "synth")):
            out += [(r["tag"], a) for a in r["archives"]]
    return out


def sit_archive(a):
    """The bytes Expander was given: a corpus fixture, or a sentinel
    archive rebuilt by sitmeta.py's own generator; None unless they hash
    to what the boot recorded."""
    import hashlib
    sys.path.insert(0, os.path.join(HERE, "vmac"))
    import sitmeta
    name = a["fixture"]
    blob = None
    if name.startswith("synth-") and name.endswith(".sit"):
        tag = name[6:-4]
        for n, kw, _w in sitmeta.SYNTH_SET + sitmeta.SYNTH_SET2 + \
                sitmeta.SYNTH_SET3:
            if n == tag:
                blob = sitmeta.synth_archive(top=n.encode(), **kw)
    else:
        p = os.path.join(REPO, "fixtures", name)
        if os.path.exists(p):
            blob = open(p, "rb").read()
    if blob is None or hashlib.sha256(blob).hexdigest() != a["sha256"]:
        return None
    return blob


def expander_want(kind, rec):
    """What Expander wrote, in `l --meta`'s vocabulary (hfscat.py's
    record layouts)."""
    if kind == "file":
        return dict(finfo=rec[4:20].hex(), fxinfo=rec[56:72].hex(),
                    backup="%08x" % int.from_bytes(rec[52:56], "big"),
                    lock="L" if rec[2] & 1 else "n")
    return dict(finfo=rec[22:38].hex(), fxinfo=rec[38:54].hex(),
                backup="%08x" % int.from_bytes(rec[18:22], "big"))


def printable(t):
    return "".join(ch for ch in t if ord(ch) >= 0x20)


def as_written(row):
    """An engine row as a host writes it on a new entry: what is not
    stated stays zero, and a lock not stated is no lock."""
    return dict(finfo="00" * 16 if row["finfo"] == "-" else row["finfo"],
                fxinfo="00" * 16 if row["fxinfo"] == "-" else row["fxinfo"],
                backup="00000000" if row["backup"] == "-" else row["backup"],
                lock="L" if row["lock"] == "L" else "n")


def expander(cli):
    """(failures, fields compared, archives graded, left out, pairs)
    where pairs is [(label, got, want)] for the controls."""
    res = sitmeta_results()
    if not res:
        return None
    tmp = os.path.join(REPO, ".tmp", "run_meta")
    os.makedirs(tmp, exist_ok=True)
    bad, n, graded, left, pairs = [], 0, 0, [], []
    for tag, a in res:
        ents = [e for e in a["entries"] if e["kind"] != "end"]
        if any("match" not in e for e in ents):
            left.append("%s (%s): not extracted whole by Expander"
                        % (a["fixture"], tag))
            continue
        blob = sit_archive(a)
        if blob is None:
            left.append("%s (%s): absent here, or not the bytes Expander "
                        "was given" % (a["fixture"], tag))
            continue
        p = os.path.join(tmp, "x-" + a["fixture"])
        open(p, "wb").write(blob)
        rows = meta_list(cli, p)
        os.unlink(p)
        if len(rows) != len(ents):
            bad.append("%s: the engine lists %d entries, Expander wrote %d"
                       % (a["fixture"], len(rows), len(ents)))
            continue
        graded += 1
        for (name, row), e in zip(rows, ents):
            # Order is what pairs them (both walks stop at the same
            # header); the leaf is a sanity check, compared as printable
            # text because the CLI drops control bytes (`Icon\r`).
            leaf = printable(bytes.fromhex(e["path"][-1]).decode("mac-roman"))
            mine = printable(name.split("/")[-1])
            if mine[:31] != leaf[:31] and mine.replace(":", "/")[:31] \
                    != leaf[:31]:
                bad.append("%s: entry order: %r against Expander's %r"
                           % (a["fixture"], name, leaf))
                continue
            want = expander_want(e["kind"], bytes.fromhex(e["match"]["rec"]))
            got = as_written(row)
            label = "%s: %s" % (a["fixture"], name)
            for k in want:
                n += 1
                pairs.append((label, e["kind"] + " " + k, got[k], want[k]))
                if got[k] != want[k]:
                    bad.append("%s: %s %s, Expander wrote %s"
                               % (label, k, got[k], want[k]))
    return bad, n, graded, left, pairs


def expander_controls(pairs):
    """Each field of each kind (a file's four, a folder's three), tampered
    with on the first entry where the engine and Expander agree, must be
    caught: a bit flipped in the bytes, the lock inverted."""
    caught, seen = 0, set()
    for label, k, got, want in pairs:
        if k in seen or got != want:
            continue
        seen.add(k)
        if k.endswith("lock"):
            g = "n" if got == "L" else "L"
        else:
            g = got[:-1] + "%x" % (int(got[-1], 16) ^ 1)
        caught += g != want
    return caught, len(seen)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cli", default=os.path.join(REPO, "build", "macextract"))
    ap.add_argument("--corpus", action="store_true")
    ap.add_argument("--expander", action="store_true")
    a = ap.parse_args()

    fails, n = [], 0
    exp = expectations(a.cli)
    for fx, want, fields in exp:
        if not os.path.exists(fx):
            print("run_meta: %s is missing — generate it (fixtures/SOURCES.md)"
                  % os.path.basename(fx))
            return 1
        got = meta_rows(a.cli, fx)
        for name, w in want.items():
            g = got.get(name)
            if g is None:
                fails.append("%s: %s not listed" % (os.path.basename(fx), name))
                continue
            n += sum(1 for k in fields if k in w)
            fails += compare("%s: %s" % (os.path.basename(fx), name), g, w,
                             fields)

    # The controls: each field tampered with in turn must be caught.
    caught = 0
    tried = 0
    for fx, want, fields in exp:
        got = meta_rows(a.cli, fx)
        for name, w in want.items():
            for k in fields:
                if k not in w or name not in got:
                    continue
                g = dict(got[name])
                g[k] = "-" if g[k] != "-" else "00"
                tried += 1
                caught += bool(compare(name, g, w, (k,)))
    print("run_meta: %d field(s) compared, %d control(s) caught of %d"
          % (n, caught, tried))
    if caught != tried or not tried:
        fails.append("a control passed: the comparison is not comparing")

    if a.corpus:
        bad, c = corpus(a.cli)
        print("run_meta: corpus, %d stated field(s) held against lsar" % c)
        fails += bad

    if a.expander:
        r = expander(a.cli)
        if r is None:
            print("run_meta: --expander SKIPPED: no sitmeta.py results "
                  "(tools/vmac/README.md, *Finder info, read back*)")
        else:
            bad, c, graded, left, pairs = r
            caught, tried = expander_controls(pairs)
            print("run_meta: Expander 4.0.2, %d archive(s), %d field(s) "
                  "held against what it wrote; %d left out; %d control(s) "
                  "caught of %d" % (graded, c, len(left), caught, tried))
            for x in left:
                print("run_meta:   left out: %s" % x)
            if caught != tried or tried != 7:
                bad.append("an Expander control passed, or a field of a "
                           "file or a folder was never compared")
            fails += bad

    for f in fails:
        print("run_meta: FAIL %s" % f)
    print("run_meta: %s" % ("OK" if not fails else "%d FAILED" % len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""run_meta.py — the engine's Finder metadata beyond type, creator and flags.

    tools/run_meta.py [--cli build/macextract] [--corpus]

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
  --corpus                              every fixture: wherever the engine
      states a field and `lsar` reports the same field, they must agree.

Then a CONTROL per field: the engine's row is tampered with, one field at
a time, and the comparison must fail — or it was comparing nothing.

**What it cannot see.** Anything the engine does not deliver: an entry
whose archive stores a field this engine does not read yet prints `-` and
passes (the inventory of those is OPEN_ITEMS.md's). The lock, against any
reader but the synthesizer. Whether a host WRITES any of it: that is
tests/mac_sink_test.c --meta, and on an emulated Mac tools/vmac/hfs_cat.py.
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
    return out


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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cli", default=os.path.join(REPO, "build", "macextract"))
    ap.add_argument("--corpus", action="store_true")
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

    for f in fails:
        print("run_meta: FAIL %s" % f)
    print("run_meta: %s" % ("OK" if not fails else "%d FAILED" % len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

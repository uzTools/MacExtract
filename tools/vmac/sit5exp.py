#!/usr/bin/env python3
"""sit5exp.py — StuffIt Expander 5.5 over the StuffIt 5 corpus, fork for fork.

`sitexp.py`'s flow for StuffIt 5 (TESTING.md, *What `unar` alone vouches for,
per format*: 820 forks, `unar` the sole oracle). Expander 5.5 is the one
inside StuffIt Deluxe 5.5, placed on a Mac OS 9.2 boot volume by `sitzip.py`
(tools/vmac/README.md); one QEMU boot per archive, the archive typed SIT5/SITx
and opened with the Expand dialog as `sitmeta.py --sit5 --plain` does. What
Expander wrote to the transfer volume is read back by `superdisk.read_forks`
and compared with the manifest the way `cptexp.py` does: data forks by sha256
as a multiset, resource forks masked (`compare_rsrc`).

    tools/vmac/sit5exp.py --json out.json --all [--offset N --limit M]
    tools/vmac/sit5exp.py --json out.json fixtures/derived-KeyGraphics.sit

Every run also holds a CONTROL: the same comparison against a reference with
one data hash replaced must come out as a disagreement (`control_detected`).

What it cannot see: names and folder structure (a multiset, plus the
informational `path_agree`), Finder info, and anything Expander 5.5 does not
write as a file.
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                              # noqa: E402
import sitzip as Z                                           # noqa: E402
import os9                                                   # noqa: E402
from arcmac import macbinary as _mb                          # noqa: E402
from superdisk import read_forks                             # noqa: E402
from cptexp import reference, compare_rsrc                   # noqa: E402

FIXDIR = os.path.join(REPO, "fixtures")
PAUSE = os.path.join(REPO, ".tmp", "emu-pause")
SUBJ = "Rsentinel.sit"
SKIP = {SUBJ, Z.APP_NAME}

# sitzip.drive waits up to 305 s for "Expander launched", a step whose screen
# change (the menu bar) never reaches its 2 % threshold, so every archive
# paid the whole wait (measured 2026-11-28: 305 s + 120 s of 750). Capped at
# 90 s; the Expand dialog that follows is the real check that it launched.
_wait = os9.Qemu.wait_change


def _capped(self, before, rect, scratch, timeout=180.0, **kw):
    return _wait(self, before, rect, scratch, timeout=min(timeout, 90.0), **kw)


os9.Qemu.wait_change = _capped


def fixtures():
    out = []
    for p in glob.glob(os.path.join(FIXDIR, "manifests", "*.json")):
        d = json.load(open(p))
        fx = d.get("fixture", "")
        if d.get("format") == "StuffIt 5" and os.path.exists(os.path.join(FIXDIR, fx)):
            out.append((d["size"], fx))
    return [f for _, f in sorted(out)]


def run_one(fixture, args):
    label = os.path.basename(fixture)
    outdir = os.path.join(args.workroot, "sit5exp-" + label)
    shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir)
    Z.SUBJECT, Z.SUBJECT_NAME = fixture, SUBJ
    Z.macbinary = lambda name, t, c, *a, **k: _mb(
        name, "SIT5" if name == SUBJ else t, c, *a, **k)
    ns = argparse.Namespace(boot_wait=600.0, settle_wait=300.0)
    t0 = time.time()
    try:
        Z.run("55", outdir, ns)
    except SystemExit as e:
        print("sit5exp: %s: run ended: %s" % (label, e), flush=True)
    part = os.path.join(outdir, "transfer.hfs")
    got = {}
    if os.path.exists(part):
        for path, (ft, cr, d, r) in read_forks(part).items():
            if path[-1] in SKIP and len(path) == 1:
                continue
            # Mac OS 9's own volume bookkeeping, not an archived file
            # (measured: DesktopPrinters DB, OpenFolderListDF, per boot)
            if path[0] in ("TheVolumeSettingsFolder", "Desktop DB", "Desktop DF"):
                continue
            got["/".join(path)] = (d or b"", r or b"")
    refdata, refn = reference(fixture)
    expdata = Counter(hashlib.sha256(d).hexdigest() for d, _ in got.values())
    res = {"fixture": label, "pulled": len(got), "engine_files": refn,
           "agree": expdata == refdata,
           "expander_only": [h[:16] for h in (expdata - refdata)],
           "engine_only": [h[:16] for h in (refdata - expdata)],
           "seconds": int(time.time() - t0),
           "names": {k: [len(d), len(r)] for k, (d, r) in got.items()}}
    compare_rsrc(got, fixture, outdir, res)
    # path-keyed data check, informational (Expander may rename)
    man = json.load(open(os.path.join(FIXDIR, "manifests", label + ".json")))
    want = {e["name"]: e["data_sha256"] for e in man["entries"]
            if not e.get("is_dir") and "data_sha256" in e}
    have = {}
    for k, (d, _) in got.items():
        have[k] = hashlib.sha256(d).hexdigest()
    res["path_agree"] = sum(1 for k, v in want.items() if have.get(k) == v)
    res["path_total"] = len(want)
    # control: one reference hash replaced must be seen as a difference
    bad = Counter(refdata)
    if bad:
        h = next(iter(bad))
        bad[h] -= 1
        bad = +bad
        bad["0" * 64] += 1
    res["control_detected"] = (expdata != bad) if refdata else None
    print(json.dumps(res), flush=True)
    if not args.keep:
        shutil.rmtree(outdir, ignore_errors=True)
    return res


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fixtures", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--workroot", default=os.path.join(REPO, ".tmp"))
    p.add_argument("--keep", action="store_true")
    p.add_argument("--json")
    a = p.parse_args()
    picks = [os.path.abspath(f) for f in a.fixtures]
    if a.all:
        picks += [os.path.join(FIXDIR, f) for f in fixtures()]
    picks = picks[a.offset:]
    if a.limit:
        picks = picks[:a.limit]
    out = []
    for f in picks:
        while os.path.exists(PAUSE):
            print("sit5exp: paused by %s" % PAUSE, flush=True)
            time.sleep(60)
        out.append(run_one(f, a))
        if a.json:
            json.dump(out, open(a.json, "w"), indent=1)
    ok = [r for r in out if r["agree"] and r["rsrc_agree"]]
    print("sit5exp: %d/%d archives agree on both forks" % (len(ok), len(out)))
    for r in out:
        if r not in ok:
            print("sit5exp:   DIFFERS %s" % json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""cptexp.py — StuffIt Expander 4.0.2 over the Compact Pro corpus, fork for fork.

The fork inventory (TESTING.md, *What `unar` alone vouches for, per format*)
found Compact Pro the largest block of forks `unar` is the SOLE oracle for.
Expander 4.0.2 reads `.cpt`, so it is a second implementation already on this
machine. This boots it over each Compact Pro fixture on the System 6.0.8 Mac
Plus `expander.py` uses, one boot per archive, pulls every file it wrote off
the volume (`hcopy -m`), and compares both forks with what this engine writes
for the same archive (`macextract x`) — which already matches `unar`. Where
they agree, Expander corroborates the engine and `unar` is no longer alone.

    tools/vmac/cptexp.py -o <shotdir> --json out.json FIXTURE.cpt ...
    tools/vmac/cptexp.py -o <shotdir> --json out.json --all   # every plain .cpt

The flow and its blind spots are exp402opt.py's (the resource map's reserved
bytes are masked, as Expander writes its own; the alert text is photographed,
not read). Plain `.cpt` only here: a `.sea` is run, not Expanded, and an
encrypted archive needs its own password — both are their own pass.
"""
import argparse
import glob
import hashlib
import json
import os
from collections import Counter
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                              # noqa: E402
from interactive import Mac                                  # noqa: E402
from vmac_check import mask_reserved                         # noqa: E402
from arcmac import macbinary                                 # noqa: E402
from expander import (APP_NAME, EXPAND_BUTTON, forks, names_on,  # noqa: E402
                      select_by_name)

FIXDIR = os.path.join(REPO, "fixtures")


def md5(b):
    return hashlib.md5(b).hexdigest()[:12]


def fork_key(d, r):
    """A fork pair as it is compared: the data exact, the resource masked of
    its map's reserved bytes, which Expander writes to its own taste
    (exp402opt.py; vmac_check.mask_reserved)."""
    return (md5(d), md5(mask_reserved(r)))


def reference(fixture, work):
    """The engine's forks for the archive, as a multiset of fork_key — keyed
    by content, not name, so duplicate leaf names across folders and the Mac
    `:`/Linux `/` split do not matter (`macextract x` writes the resource as
    a `.rsrc` sidecar)."""
    out = os.path.join(work, "ref")
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run([os.path.join(REPO, "build", "macextract"), "x",
                    "-o", out, fixture], capture_output=True)
    keys = Counter()
    n = 0
    for root, _, files in os.walk(out):
        for f in files:
            if f.endswith(".rsrc") and os.path.exists(os.path.join(root, f[:-5])):
                continue   # the sidecar of a file we read below
            p = os.path.join(root, f)
            r = p + ".rsrc"
            keys[fork_key(open(p, "rb").read(),
                          open(r, "rb").read() if os.path.exists(r) else b"")] += 1
            n += 1
    return keys, n


def pull(img, names, work):
    """Each new file on the volume, both forks (exp402opt.py's pull)."""
    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    got = {}
    try:
        subprocess.run(["hmount", img], env=env, capture_output=True)
        for i, n in enumerate(names):
            dst = os.path.join(work, f"pull{i}.bin")
            r = subprocess.run(["hcopy", "-m", n, dst], env=env,
                               capture_output=True)
            if r.returncode == 0 and os.path.exists(dst):
                got[n] = forks(dst)
        subprocess.run(["humount"], env=env, capture_output=True)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    return got


def run_one(fixture, args):
    label = os.path.basename(fixture)
    work = (tempfile.mkdtemp(prefix=f"cptexp-{label}-", dir=args.workroot)
            if args.workroot else R.work_tmp(f"cptexp-{label}-"))
    boot = os.path.join(work, "boot-in.hfv")
    macname = label[:31]
    mb = os.path.join(work, macname + ".bin")
    open(mb, "wb").write(macbinary(macname, "PACT", "CPCT",
                                   open(fixture, "rb").read()))
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
         os.path.join(R.VMAC_HOME, "System6.hfv"),
         os.path.join(R.VMAC_HOME, "expander", "Expander.bin"), boot,
         "--macbin", f"{mb}:{macname}", "--app-name", APP_NAME)
    before = set(names_on(boot))
    scratch = os.path.join(work, "scratch.png")
    shot = None
    mac = Mac(boot, args.emu, work)
    if args.outdir:
        shot = lambda n: mac.shot(os.path.join(args.outdir, f"{label}-{n}.png"))  # noqa
    try:
        if mac.settle(scratch, interval=4.0, timeout=300.0) is None:
            raise SystemExit(f"cptexp: {label}: never booted")
        if shot:
            shot("1-launched")
        mac.origin(cached=False)
        mac.command_key("e")
        time.sleep(3.0)
        select_by_name(mac, macname)
        if shot:
            shot("2-selected")
        mac.click(*EXPAND_BUTTON)
        mac.settle(scratch, interval=3.0, timeout=600.0, quiet=15.0)
        if shot:
            shot("3-after-expand")
        mac.key("Return")                     # dismiss whatever alert is up
        mac.settle(scratch, interval=3.0, timeout=300.0, quiet=9.0)
        mac.command_key("q")                  # commits Expander's writes
        time.sleep(10.0)
        mac.settle(scratch, interval=3.0, timeout=300.0, quiet=9.0)
        if shot:
            shot("4-quit")
    finally:
        mac.close()
    img = os.path.join(work, "boot.hfv")
    # Expander drops its own "StuffIt Expander Preferences" into the System
    # Folder on first run; the archive's files extract to the volume root.
    new = [n for n in names_on(img)
           if n not in before and ":System Folder:" not in n]
    got = pull(img, new, work)
    refkeys, refn = reference(fixture, work)
    # Compare by fork content, not name: Expander's multiset of (data, masked
    # resource) against the engine's. Equal means every fork agrees, whatever
    # the names; a short pull (hcopy cannot copy a `∏`/`™` name off the
    # volume) leaves `missing` files uncompared rather than failing.
    expkeys = Counter(fork_key(d, r) for d, r in got.values())
    agree = expkeys == refkeys
    missing = refn - len(got)
    res = {"fixture": label, "pulled": len(got), "engine_files": refn,
           "missing": missing, "agree": agree,
           # the forks Expander produced that the engine never did (a real
           # difference, if any) and vice versa
           "expander_only": [list(k) for k in (expkeys - refkeys)],
           "engine_only": [list(k) for k in (refkeys - expkeys)]}
    print(json.dumps(res), flush=True)
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return res


def plain_cpt():
    out = []
    for p in glob.glob(os.path.join(FIXDIR, "manifests", "*.json")):
        d = json.load(open(p))
        fx = d.get("fixture", "")
        if d.get("format") == "Compact Pro" and fx.endswith(".cpt") \
           and os.path.exists(os.path.join(FIXDIR, fx)):
            out.append((d["size"], fx))
    out.sort()
    return [fx for _, fx in out]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fixtures", nargs="*")
    p.add_argument("-o", "--outdir", default=None, help="screenshots (optional)")
    p.add_argument("--all", action="store_true", help="every plain .cpt fixture")
    p.add_argument("--limit", type=int, default=0, help="first N of --all")
    p.add_argument("--emu", default="mv-4M",
                   help="nothing is timed, so the all-out build is fine")
    p.add_argument("--workroot", default=None)
    p.add_argument("--keep", action="store_true")
    p.add_argument("--json")
    args = p.parse_args()
    if args.keep:
        os.environ["HARNESS_KEEP_IMAGES"] = "1"
    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
    picks = list(args.fixtures)
    if args.all:
        picks += [os.path.join(FIXDIR, f) for f in plain_cpt()]
    if args.limit:
        picks = picks[:args.limit]
    out = [run_one(f, args) for f in picks]
    clean = sum(1 for r in out if r["agree"])
    contra = [r for r in out if r["expander_only"]]
    gap = [r for r in out if not r["agree"] and not r["expander_only"]]
    print("cptexp: %d/%d clean; %d with an hcopy pull gap (no contradiction); "
          "%d CONTRADICT the engine" % (clean, len(out), len(gap), len(contra)),
          flush=True)
    for r in contra:
        print("cptexp:   CONTRADICTION %s expander_only=%s"
              % (r["fixture"], r["expander_only"]), flush=True)
    if args.json:
        json.dump(out, open(args.json, "w"), indent=1)
    return 0 if not contra else 1


if __name__ == "__main__":
    sys.exit(main())

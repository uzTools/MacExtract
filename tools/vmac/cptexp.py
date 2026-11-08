#!/usr/bin/env python3
"""cptexp.py — StuffIt Expander 4.0.2 over the Compact Pro corpus, fork for fork.

The fork inventory (TESTING.md, *What `unar` alone vouches for, per format*)
found Compact Pro the largest block of forks `unar` is the SOLE oracle for.
Expander 4.0.2 reads `.cpt`, so it is a second implementation already on this
machine. This boots it over each Compact Pro fixture on the System 6.0.8 Mac
Plus `expander.py` uses, one boot per archive, pulls every file it wrote off
the volume (`hcopy -m`), and compares both forks with the record: the data
fork against the manifest, the resource fork masked against `macextract x`'s,
checked equal to the manifest first (`compare_rsrc`). Where they agree,
Expander corroborates the engine and `unar` is no longer alone.

    tools/vmac/cptexp.py -o <shotdir> --json out.json FIXTURE.cpt ...
    tools/vmac/cptexp.py -o <shotdir> --json out.json --all   # every plain .cpt

The flow and its blind spots are exp402opt.py's (the resource map's reserved
bytes are masked, as Expander writes its own; the alert text is photographed,
not read). `--all` is the plain `.cpt`; a `.sea`, `.cmp` or package goes by
name and is typed PACT the same (TESTING.md). `touch .tmp/emu-pause` holds a
run between archives.
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
from arcmac import macbinary                                 # noqa: E402
from vmac_check import mask_reserved                         # noqa: E402
from expander import (APP_NAME, EXPAND_BUTTON, forks, names_on,  # noqa: E402
                      select_by_name)

FIXDIR = os.path.join(REPO, "fixtures")
PAUSE = os.path.join(REPO, ".tmp", "emu-pause")


MANDIR = os.path.join(FIXDIR, "manifests")


def reference(fixture):
    """The engine+unar record for this archive, from its manifest: the
    multiset of data-fork sha256 over its files (an empty fork is the sha256
    of no bytes), and the file count. The manifest has full paths and clean
    hashes, so duplicate leaf names across folders and a file literally named
    `*.rsrc` (GNU Chess's `gnuchess.∏.rsrc`) are unambiguous — unlike the
    CLI's `.rsrc` sidecar output, where they collide. The resource fork is
    compare_rsrc's: Expander writes its own header reserved bytes, so it
    agrees only AFTER masking, which the manifest's raw hash cannot
    express."""
    man = json.load(open(os.path.join(MANDIR, os.path.basename(fixture) + ".json")))
    files = [e for e in man["entries"] if not e.get("is_dir")]
    # a data fork the oracle failed has no hash; compare_rsrc adjudicates it
    return (Counter(e["data_sha256"] for e in files if "data_sha256" in e),
            len(files))


ENGINE = os.environ.get("MACEXTRACT",
                        os.path.join(REPO, "build", "rel", "macextract"))


def rsrc_key(r):
    return hashlib.sha256(mask_reserved(r)).hexdigest()


def rsrc_reference(fixture, work):
    """The archive's non-empty resource forks as a multiset of rsrc_key, and
    whether they ARE the record. The manifest holds raw hashes, and Expander
    writes the fork header's reserved bytes 16..127 to its own taste, so the
    comparison needs the bytes: `macextract x --forks hidden` writes each
    raw as `._NAME` (no `.rsrc` name to collide with an archived one —
    measured: the file holds the fork itself, not an AppleDouble). Its RAW
    multiset is checked against the manifest's first, so a masked agreement
    is an agreement with the record, not with the engine alone.

    A fork the oracle failed (`unadjudicated` in the manifest) has no hash
    to check against: the engine's bytes for it are returned apart, by exact
    path — the data raw, the resource masked — for Expander to adjudicate."""
    man = json.load(open(os.path.join(MANDIR, os.path.basename(fixture) + ".json")))
    files = [e for e in man["entries"] if not e.get("is_dir")]
    rec = Counter(e["rsrc_sha256"] for e in files if e.get("rsrc_size", 0) > 0)
    unadj = {(e["name"], k) for e in files for k in e.get("unadjudicated", {})}
    out = os.path.join(work, "rsrc-ref")
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run([ENGINE, "x", "--forks", "hidden", "-o", out, fixture],
                   capture_output=True)
    raw, masked = Counter(), Counter()
    adj_data, adj_rsrc = Counter(), Counter()
    for root, _, fs in os.walk(out):
        for f in fs:
            b = open(os.path.join(root, f), "rb").read()
            rel = os.path.relpath(os.path.join(root, f), out)
            if f.startswith("._"):
                name = os.path.join(os.path.dirname(rel), f[2:])
                if (name, "rsrc") in unadj:
                    if b:
                        adj_rsrc[rsrc_key(b)] += 1
                elif b:
                    raw[hashlib.sha256(b).hexdigest()] += 1
                    masked[rsrc_key(b)] += 1
            elif (rel, "data") in unadj:
                adj_data[hashlib.sha256(b).hexdigest()] += 1
    shutil.rmtree(out, ignore_errors=True)
    return masked, raw == rec, adj_data, adj_rsrc, len(unadj)


def compare_rsrc(got, fixture, work, res):
    """Add the resource-fork verdict to `res`: Expander's non-empty forks,
    masked, against the record's (rsrc_reference). Where the oracle failed a
    fork, Expander's fork left over from the record comparison is set
    against the engine's for it: `adjudicated` counts the forks where the
    two agree, and only then are they taken out of the difference lists."""
    ref, record, adj_data, adj_rsrc, n_unadj = rsrc_reference(fixture, work)
    exp = Counter(rsrc_key(r) for _, r in got.values() if r)
    extra_r = exp - ref
    adjudicated = 0
    if n_unadj:
        extra_d = Counter(h[:16] for h in res["expander_only"])
        want_d = Counter(h[:16] for h in adj_data)
        if want_d and want_d == extra_d:
            adjudicated += sum(want_d.values())
            res["expander_only"] = []
            res["agree"] = not res["engine_only"]
        if adj_rsrc and adj_rsrc == extra_r:
            adjudicated += sum(adj_rsrc.values())
            extra_r = Counter()
        res["unadjudicated_forks"] = n_unadj
        res["adjudicated"] = adjudicated
    if res["engine_files"] and not res["pulled"]:
        res["agree"] = False          # nothing to agree with, not agreement
    res.update({"rsrc_forks": sum(ref.values()), "rsrc_record": record,
                "rsrc_agree": record and not extra_r and not (ref - exp),
                "rsrc_expander_only": [h[:16] for h in extra_r],
                "rsrc_engine_only": [h[:16] for h in (ref - exp)]})
    return res


def pull(img, names, work):
    """Each new file on the volume, both forks (exp402opt.py's pull)."""
    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    got = {}
    try:
        subprocess.run(["hmount", img], env=env, capture_output=True)
        for i, n in enumerate(names):
            dst = os.path.join(work, f"pull{i}.bin")
            # hcopy wants the name in the volume's encoding (MacRoman), not
            # the UTF-8 of a `∏`/`™`/`π`; `names_on` handed it back decoded
            # (checkdisk.py does the same for its own forks).
            r = subprocess.run(
                ["hcopy", "-m", n.encode("mac_roman", "replace"), dst.encode()],
                env=env, capture_output=True)
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
    # Typed as a Compact Pro document (PACT/CPCT) so Standard File's filter
    # shows it. A `.sea` carries the same archive after a self-extractor
    # prefix, with the directory at the end, so Expander expands it in place
    # like a self-extracting zip — the APPL type a `.sea` really has is hidden
    # from the filter (measured 2026-11-07).
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
    # Folder on first run; and for a Compact Pro PACKAGE it writes the
    # package's comment as a "Comments about <name>" text file beside the
    # extracted folder — the engine and `unar` keep that as a Get Info
    # comment, not a file (measured 2026-11-07). Neither is an archived file.
    new = [n for n in names_on(img)
           if n not in before and ":System Folder:" not in n
           and not n.split(":")[-1].startswith("Comments about ")]
    got = pull(img, new, work)
    refdata, refn = reference(fixture)
    # Compare Expander's data-fork sha256 multiset against the manifest's.
    # Equal means every data fork agrees, whatever its name or folder; a
    # short pull (hcopy could not copy a name off the volume) shows as
    # `engine_only` with nothing in `expander_only` — a gap, not a difference.
    expdata = Counter(hashlib.sha256(d).hexdigest() for d, _ in got.values())
    agree = expdata == refdata
    res = {"fixture": label, "pulled": len(got), "engine_files": refn,
           "agree": agree,
           # a data fork Expander produced that the engine did not — a real
           # difference, if any; and the reverse, usually an hcopy pull gap
           "expander_only": [h[:16] for h in (expdata - refdata)],
           "engine_only": [h[:16] for h in (refdata - expdata)]}
    compare_rsrc(got, fixture, work, res)
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
    out = []
    for f in picks:
        # Another agent may need the one emulator: while .tmp/emu-pause
        # exists, wait between archives (never inside one).
        while os.path.exists(PAUSE):
            print("%s: paused by %s" % ("cptexp", PAUSE), flush=True)
            time.sleep(60)
        out.append(run_one(f, args))
    clean = sum(1 for r in out if r["agree"])
    contra = [r for r in out if r["expander_only"]]
    gap = [r for r in out if not r["agree"] and not r["expander_only"]]
    print("cptexp: %d/%d clean; %d with an hcopy pull gap (no contradiction); "
          "%d CONTRADICT the engine" % (clean, len(out), len(gap), len(contra)),
          flush=True)
    for r in contra:
        print("cptexp:   CONTRADICTION %s expander_only=%s"
              % (r["fixture"], r["expander_only"]), flush=True)
    rbad = [r for r in out if not r["rsrc_agree"]]
    print("%s: resource forks %d/%d archives agree masked (%d forks); %s"
          % ("cptexp", len(out) - len(rbad), len(out),
             sum(r["rsrc_forks"] for r in out),
             ", ".join("%s record=%s exp_only=%s eng_only=%s"
                       % (r["fixture"], r["rsrc_record"],
                          r["rsrc_expander_only"], r["rsrc_engine_only"])
                       for r in rbad) or "none differ"), flush=True)
    if args.json:
        json.dump(out, open(args.json, "w"), indent=1)
    return 0 if not contra else 1


if __name__ == "__main__":
    sys.exit(main())

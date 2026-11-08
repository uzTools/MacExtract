#!/usr/bin/env python3
"""sitexp.py — StuffIt Expander 4.0.2 over the classic StuffIt corpus, fork for fork.

With Compact Pro corroborated and recorded (`cptexp.py`; TESTING.md, *Compact
Pro against StuffIt Expander 4.0.2*), classic StuffIt is the largest block of
forks `unar` is still the sole oracle for (TESTING.md, *What `unar` alone
vouches for, per format* — 2,708 of 2,731). Expander 4.0.2 reads `.sit`, so it
is a second implementation already on this machine, and every fixture here
uses a classic method it opens by itself (LZ+Huffman, Compress, Huffman, LZAH,
MW, RLE, Fixed Huffman — none the StuffIt 5 arsenic that needs Expander 5).

This is `cptexp.py`'s flow for StuffIt: it boots Expander over each fixture on
the System 6.0.8 Mac Plus (`expander.py`), one boot per archive, pulls every
file it wrote off the volume (`hcopy -m`), and compares the DATA fork by
sha256 as a multiset against the archive's manifest — which already matches
`unar`. Where they agree, Expander corroborates the engine and `unar`, and the
forks leave `unar`-sole once recorded. `reference()` and `pull()` are shared
with `cptexp.py` verbatim, and so is `compare_rsrc`, the resource fork's
masked comparison against the record; only the Standard File type (`SIT!`),
the corpus filter and `--keep-comments` differ.

    tools/vmac/sitexp.py -o <shotdir> --json out.json FIXTURE.sit ...
    tools/vmac/sitexp.py --json out.json --all                # every StuffIt fixture
    tools/vmac/sitexp.py --json out.json --all --offset 0 --limit 40   # a <2h slice

One boot per archive, so no cross-archive filename collision can merge two
multisets (the reason this is not batched like `sitmeta.py`). ONE EMULATOR AT
A TIME and nothing else CPU-heavy on this box (tools/vmac/README.md).
"""
import argparse
import glob
import hashlib
import json
import os
from collections import Counter
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                              # noqa: E402
from interactive import Mac                                 # noqa: E402
from arcmac import macbinary                                # noqa: E402
from expander import APP_NAME, EXPAND_BUTTON, names_on, select_by_name  # noqa: E402
from cptexp import reference, pull, compare_rsrc                          # noqa: E402

FIXDIR = os.path.join(REPO, "fixtures")
PAUSE = os.path.join(REPO, ".tmp", "emu-pause")


def run_one(fixture, args):
    label = os.path.basename(fixture)
    work = (tempfile.mkdtemp(prefix=f"sitexp-{label}-", dir=args.workroot)
            if args.workroot else R.work_tmp(f"sitexp-{label}-"))
    boot = os.path.join(work, "boot-in.hfv")
    macname = label[:31]
    mb = os.path.join(work, macname + ".bin")
    # Typed SIT!/SIT! so Standard File's filter shows it (sitmeta.py does the
    # same). A StuffIt `.sea` carries the archive inside a self-extractor;
    # opened as SIT! Expander reads the embedded archive rather than launching
    # the stub — the same in-place trick cptexp.py uses for a `.cpt` `.sea`.
    open(mb, "wb").write(macbinary(macname, "SIT!", "SIT!",
                                   data=open(fixture, "rb").read()))
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
            raise SystemExit(f"sitexp: {label}: never booted")
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
    # Expander drops "StuffIt Expander Preferences" into the System Folder on
    # first run; cptexp.py also sees a package's "Comments about <name>" file.
    # Neither is an archived file (TESTING.md, *Compact Pro against ...*).
    new = [n for n in names_on(img)
           if n not in before and ":System Folder:" not in n
           and not (n.split(":")[-1].startswith("Comments about ")
                    and not args.keep_comments)]
    got = pull(img, new, work)
    refdata, refn = reference(fixture)
    expdata = Counter(hashlib.sha256(d).hexdigest() for d, _ in got.values())
    agree = expdata == refdata
    res = {"fixture": label, "pulled": len(got), "engine_files": refn,
           "agree": agree,
           "expander_only": [h[:16] for h in (expdata - refdata)],
           "engine_only": [h[:16] for h in (refdata - expdata)]}
    compare_rsrc(got, fixture, work, res)
    print(json.dumps(res), flush=True)
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return res


def stuffit_fixtures():
    out = []
    for p in glob.glob(os.path.join(FIXDIR, "manifests", "*.json")):
        d = json.load(open(p))
        fx = d.get("fixture", "")
        if d.get("format") == "StuffIt" and fx \
           and os.path.exists(os.path.join(FIXDIR, fx)):
            out.append((d.get("size", 0), fx))
    out.sort()
    return [fx for _, fx in out]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fixtures", nargs="*")
    p.add_argument("-o", "--outdir", default=None, help="screenshots (optional)")
    p.add_argument("--all", action="store_true", help="every StuffIt fixture")
    p.add_argument("--offset", type=int, default=0, help="skip the first N of --all")
    p.add_argument("--limit", type=int, default=0, help="at most N (after --offset)")
    p.add_argument("--emu", default="mv-4M",
                   help="nothing is timed, so the all-out build is fine")
    p.add_argument("--workroot", default=None)
    p.add_argument("--keep", action="store_true")
    p.add_argument("--keep-comments", action="store_true",
                   help="keep \"Comments about ...\" files: for an archive that "
                        "holds one as a real entry (InfoStack_folder.sit)")
    p.add_argument("--json")
    args = p.parse_args()
    if args.keep:
        os.environ["HARNESS_KEEP_IMAGES"] = "1"
    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
    picks = list(args.fixtures)
    if args.all:
        picks += [os.path.join(FIXDIR, f) for f in stuffit_fixtures()]
    picks = picks[args.offset:]
    if args.limit:
        picks = picks[:args.limit]
    out = []
    for f in picks:
        # Another agent may need the one emulator: while .tmp/emu-pause
        # exists, wait between archives (never inside one).
        while os.path.exists(PAUSE):
            print("%s: paused by %s" % ("sitexp", PAUSE), flush=True)
            time.sleep(60)
        out.append(run_one(f, args))
    clean = sum(1 for r in out if r["agree"])
    contra = [r for r in out if r["expander_only"]]
    gap = [r for r in out if not r["agree"] and not r["expander_only"]]
    print("sitexp: %d/%d clean; %d with an hcopy pull gap (no contradiction); "
          "%d CONTRADICT the engine" % (clean, len(out), len(gap), len(contra)),
          flush=True)
    for r in contra:
        print("sitexp:   CONTRADICTION %s expander_only=%s"
              % (r["fixture"], r["expander_only"]), flush=True)
    rbad = [r for r in out if not r["rsrc_agree"]]
    print("%s: resource forks %d/%d archives agree masked (%d forks); %s"
          % ("sitexp", len(out) - len(rbad), len(out),
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

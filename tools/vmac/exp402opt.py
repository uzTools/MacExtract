#!/usr/bin/env python3
"""exp402opt.py — StuffIt Expander 4.0.2 over StuffIt Deluxe 2.0.1's own archives.

README.md's comparison row *"Anything StuffIt Deluxe 2.0 itself wrote"* had
no measurement in Expander 4.0.2's column: the 🔴 it carried came from Deluxe
3.5.1's StuffIt Engine (TESTING.md, *The optimized StuffIt archives*). This
asks Expander itself, on the System 6.0.8 Mac Plus `expander.py` uses, one
boot per archive:

    tools/vmac/exp402opt.py -o <dir>                 # every subject
    tools/vmac/exp402opt.py -o <dir> DesT OptPaint   # some of them

Each subject is a specimen `sitopt.py` made with 2.0.1 (one per Optimizer,
one per cipher), copied onto the volume as MacBinary — both forks, because a
2.0.1 archive keeps nothing load-bearing in its resource fork but the
Standard File filter wants the type. The run selects it by name, presses
Expand, answers a password prompt with `swordfish` when the subject has one,
presses Return once for whatever alert is up, quits, and then reads the
volume: every new file is pulled off with `hcopy -m` and its two forks are
compared with `macextract x -p swordfish` over the same specimen.

What it cannot see
------------------
- **The alert TEXT.** It is photographed (`<subject>-3-*.png`) and has to be
  read off the frame; nothing here OCRs it.
- **Which reader in Expander refused**, only that the volume did or did not
  change and how the bytes compare.
- **Anything beyond a correct password.** A wrong one is never typed.
"""
import argparse
import hashlib
import json
import os
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

SPEC = os.path.join(R.VMAC_HOME, "specimens", "sitopt")
PASSWORD = "swordfish"

# (label, specimen, password?) — the subject each module or cipher is graded
# on in tools/run_sitopt.py.
SUBJECTS = [
    ("Plain", "make2/Plain.sit.bin", False),          # the control
    ("Text1", "make2/Optimized.sit.bin", False),      # Text 1
    ("MacPaint1", "paintmake/OptPaint.sit.bin", False),
    ("Sound1", "mods5/OptSound.sit.bin", False),
    ("Photoshop1", "mods5/OptPhoto.sit.bin", False),
    ("JPEGLossy", "ps-jpeg1/JpegPS.sit.bin", False),
    ("DES", "psdes1/DesT.sit.bin", True),
    ("NewDE", "psdes1/NewdeT.sit.bin", True),
    ("PassLock", "psex2/EncA.sit.bin", True),
    ("NewDEx", "psex2/EncB.sit.bin", True),
    ("DESex", "psex2/EncC.sit.bin", True),
]

# Plain TEXT files from `compat9.py`'s subject directory, for the MIME and
# BinHex rows: (label, [(host file, name on the volume)], the one opened).
# The mpack set goes on the volume WHOLE and part 01 is opened, which is what
# a user who saved three messages would do; the posting is the
# comp.binaries.mac shape Expander's Read Me says it supports.
SUBJ = os.path.join(os.path.dirname(R.VMAC_HOME), "compat", "subj")
TEXTS = [
    ("MimePartial", [("rot13.mime.01", "rot13.mime.01"),
                     ("rot13.mime.02", "rot13.mime.02"),
                     ("rot13.mime.03", "rot13.mime.03")], "rot13.mime.01"),
    ("MimeSingle", [("rot13-single.mime", "single.mime")], "single.mime"),
    ("PostedHqx", [("rot13-posted.hqx", "posted.hqx")], "posted.hqx"),
]

# Compact Pro 1.51's own encrypted archive (`cptcrypt.py --make`), which
# Expander's Read Me says it cannot open; asked rather than quoted.
CPT = ("CptCrypt", os.path.join(SPEC, "..", "cptmade", "Made.cpt"), "ohsecret")


def md5(b):
    return hashlib.md5(b).hexdigest()[:12]


def reference(spec, work):
    """What this engine writes for the specimen: {name: (data, rsrc)}."""
    out = os.path.join(work, "ref")
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run([os.path.join(REPO, "build", "macextract"), "x",
                    "-p", PASSWORD, "-o", out, spec], capture_output=True)
    got = {}
    for root, _, files in os.walk(out):
        for f in files:
            if f.endswith(".rsrc"):
                continue
            p = os.path.join(root, f)
            r = p + ".rsrc"
            got[f] = (open(p, "rb").read(),
                      open(r, "rb").read() if os.path.exists(r) else b"")
    return got


def pull(img, names, work):
    """Each new file on the volume, both forks."""
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


def run_one(label, rel, pw, args):
    work = (tempfile.mkdtemp(prefix=f"exp402-{label}-", dir=args.workroot)
            if args.workroot else R.work_tmp(f"exp402-{label}-"))
    shots = args.outdir
    boot = os.path.join(work, "boot-in.hfv")
    if label == CPT[0]:
        mb = os.path.join(work, "Made.cpt.bin")
        open(mb, "wb").write(macbinary("Made.cpt", "PACT", "CPCT",
                                       open(CPT[1], "rb").read()))
        spec, macname, put = None, "Made.cpt", ["--macbin", f"{mb}:Made.cpt"]
    elif isinstance(rel, tuple):                  # a TEXTS entry
        files, macname = rel
        spec = None
        put = []
        for host, name in files:
            mb = os.path.join(work, name + ".bin")
            open(mb, "wb").write(macbinary(
                name, "TEXT", "ttxt", open(os.path.join(SUBJ, host), "rb").read()))
            put += ["--macbin", f"{mb}:{name}"]
    else:
        spec = os.path.join(SPEC, rel)
        macname = os.path.basename(rel)[:-4]      # "DesT.sit"
        put = ["--macbin", f"{spec}:{macname}"]
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
         os.path.join(R.VMAC_HOME, "System6.hfv"),
         os.path.join(R.VMAC_HOME, "expander", "Expander.bin"), boot,
         *put, "--app-name", APP_NAME)
    before = set(names_on(boot))
    scratch = os.path.join(work, "scratch.png")
    mac = Mac(boot, args.emu, work)
    shot = lambda n: mac.shot(os.path.join(shots, f"{label}-{n}.png"))  # noqa
    try:
        if mac.settle(scratch, interval=4.0, timeout=300.0) is None:
            raise SystemExit(f"exp402opt: {label}: never booted")
        shot("1-launched")
        mac.origin(cached=False)
        mac.command_key("e")
        time.sleep(3.0)
        select_by_name(mac, macname)
        shot("2-selected")
        mac.click(*EXPAND_BUTTON)
        mac.settle(scratch, interval=3.0, timeout=600.0, quiet=15.0)
        shot("3-after-expand")
        if pw:
            mac._xdo("type", "--delay", "80",
                     CPT[2] if label == CPT[0] else PASSWORD)
            time.sleep(1.0)
            shot("3b-typed")
            mac.key("Return")
            mac.settle(scratch, interval=3.0, timeout=600.0, quiet=15.0)
            shot("3c-after-password")
        mac.key("Return")                     # dismiss whatever alert is up
        mac.settle(scratch, interval=3.0, timeout=300.0, quiet=9.0)
        shot("4-dismissed")
        mac.command_key("q")                  # commits Expander's writes
        time.sleep(10.0)
        mac.settle(scratch, interval=3.0, timeout=300.0, quiet=9.0)
        shot("5-quit")
    finally:
        mac.close()
    img = os.path.join(work, "boot.hfv")
    new = [n for n in names_on(img) if n not in before]
    got = pull(img, new, work)
    ref = reference(spec, work) if spec else {}
    rows = []
    for n, (d, r) in got.items():
        leaf = n.split(":")[-1]
        rd, rr = ref.get(leaf, (None, None))
        rows.append({"file": n, "data": [len(d), md5(d)],
                     "rsrc": [len(r), md5(r)],
                     "data_eq_ours": rd is not None and d == rd,
                     "rsrc_eq_ours": rr is not None
                     and mask_reserved(r) == mask_reserved(rr)})
    res = {"subject": label, "specimen": rel, "new": new, "files": rows,
           "ours": {k: [len(v[0]), md5(v[0]), len(v[1]), md5(v[1])]
                    for k, v in ref.items()}}
    print(json.dumps(res), flush=True)
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return res


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("subjects", nargs="*")
    p.add_argument("-o", "--outdir", required=True)
    p.add_argument("--emu", default="mv-4M",
                   help="nothing is timed, so the all-out build is fine")
    p.add_argument("--workroot", default=None)
    p.add_argument("--keep", action="store_true")
    p.add_argument("--json")
    args = p.parse_args()
    if args.keep:      # guard deletes images at exit otherwise
        os.environ["HARNESS_KEEP_IMAGES"] = "1"
    os.makedirs(args.outdir, exist_ok=True)
    every = SUBJECTS + [(lbl, (files, opened), False)
                        for lbl, files, opened in TEXTS] + [(CPT[0], None, True)]
    pick = [s for s in every if not args.subjects or s[0] in args.subjects]
    out = [run_one(*s, args) for s in pick]
    if args.json:
        json.dump(out, open(args.json, "w"), indent=1)


if __name__ == "__main__":
    main()

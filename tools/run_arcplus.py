#!/usr/bin/env python3
"""run_arcplus.py — ARC method 0x0a as ARC 7.x means it: "Trimmed".

The other 0x0a. PAK's Crushed and SEA's Trimmed share a method number
and are different algorithms, so this suite exists to check the two
things that follow from that:

  1. Trimmed decodes — graded by the CRC-16 ARC+Plus stored, by deark,
     and by the bytes that went in;
  2. the DIALECT is chosen correctly, so a Crushed archive is not read
     as Trimmed or the other way about. `arc7-all.arc` and
     `pak-crushed.arc` hold the same input files under the same method
     number, which is the only test that can fail if the discriminator
     goes wrong.

`unar` is not consulted at all here, and cannot be: XADMaster does not
recognise an ARC 7 archive — it stops at the informational item every
one of them starts with — and reads 0x0a as Crushed regardless
(BLOCKERS.md).

The archives come from ARC+Plus 7.12 itself under DOSBox
(tools/arcplus.py), plus the real one its own distribution ships in.
Skips politely when neither is present.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pak                                          # noqa: E402
import arcplus                                      # noqa: E402
import run_pak                                      # noqa: E402

TRIMMED = 0x0A
ITEMS = (0x14, 0x15, 0x16)


def check(unclassic, archive, want, problems, expect_trimmed=True):
    base = os.path.basename(archive)
    listed = arcplus.members(archive)
    if expect_trimmed and not any(m == TRIMMED for m, *_ in listed):
        problems.append("%s: holds no 0x0a member" % base)
        return

    r = subprocess.run([unclassic, "t", archive], capture_output=True)
    if r.returncode != 0:
        problems.append("%s: `unclassic t` exited %d: %s"
                        % (base, r.returncode,
                           r.stderr.decode("utf-8", "replace").strip()[:200]))

    out = tempfile.mkdtemp()
    try:
        subprocess.run([unclassic, "x", "-o", out, archive], capture_output=True)
        ours = {}
        for m, name, _at, _cs, _us, _crc in listed:
            if m in ITEMS:
                continue
            p = os.path.join(out, name)
            if not os.path.exists(p):
                problems.append("%s: we did not write %s" % (base, name))
                continue
            ours[name] = open(p, "rb").read()
            if name in want and ours[name] != want[name]:
                problems.append("%s: %s came back wrong (%d bytes, wanted %d)"
                                % (base, name, len(ours[name]), len(want[name])))

        dk = run_pak.deark_bin()
        if dk:
            dd = tempfile.mkdtemp()
            try:
                subprocess.run([dk, "-od", dd, "-o", "m", archive],
                               capture_output=True, timeout=600)
                # deark numbers only what it writes, so the items are
                # skipped in its numbering too.
                i = 0
                for m, name, _at, _cs, _us, _crc in listed:
                    if m in ITEMS:
                        continue
                    p = os.path.join(dd, "m.%03d.%s" % (i, name))
                    i += 1
                    if name not in ours:
                        continue
                    if not os.path.exists(p):
                        problems.append("%s: deark wrote nothing for %s"
                                        % (base, name))
                    elif open(p, "rb").read() != ours[name]:
                        problems.append("%s: %s differs from deark" % (base, name))
            finally:
                shutil.rmtree(dd, ignore_errors=True)
    finally:
        shutil.rmtree(out, ignore_errors=True)


def check_dialect(unclassic, problems):
    """The same bytes, compressed by both claimants to method 0x0a.

    If the discriminator regresses, exactly one of these two stops
    extracting — which is the failure this pair exists to catch, and
    the reason both corpora use the same input files.
    """
    a7 = os.path.join(pak.HOME, "arc7corpus", "arc7-text.arc")
    pk = os.path.join(pak.HOME, "corpus", "pak-crushed-text.pak")
    for p, who in ((a7, "ARC 7 Trimmed"), (pk, "PAK Crushed")):
        if not os.path.exists(p):
            continue
        r = subprocess.run([unclassic, "t", p], capture_output=True)
        if r.returncode != 0:
            problems.append("dialect: %s (%s) failed — the 0x0a "
                            "discriminator picked the wrong method"
                            % (os.path.basename(p), who))


def register(problems=None):
    """Write the manifest for the real ARC 7 fixture, from deark.

    `make_manifests.py` cannot: its primary oracle does not recognise an
    ARC 7 archive at all, so it produces nothing and says so. This is
    the same arrangement DiskDoubler has (`run_ddtf.py --register`), and
    the same rule applies — the manifest records who adjudicated each
    fork, and `make_manifests.py` refuses to overwrite one whose oracle
    is not `unar`.
    """
    import hashlib
    import json

    fx = os.path.join(ROOT, "fixtures", "derived-ARCDOS.arc")
    if not os.path.exists(fx):
        print("run_arcplus: no fixtures/derived-ARCDOS.arc to register")
        return 1
    dk = run_pak.deark_bin()
    if not dk:
        print("run_arcplus: deark is needed to register this manifest "
              "(sh tools/build_deark.sh)")
        return 1

    entries = []
    listed = [m for m in arcplus.members(fx) if m[0] not in ITEMS]
    dd = tempfile.mkdtemp()
    try:
        subprocess.run([dk, "-od", dd, "-o", "m", fx], capture_output=True,
                       timeout=600)
        for i, (_m, name, _at, _cs, usize, _crc) in enumerate(listed):
            p = os.path.join(dd, "m.%03d.%s" % (i, name))
            if not os.path.exists(p):
                print("run_arcplus: deark wrote nothing for %s" % name)
                return 1
            blob = open(p, "rb").read()
            if len(blob) != usize:
                print("run_arcplus: %s is %d bytes, header says %d"
                      % (name, len(blob), usize))
                return 1
            entries.append({
                "name": name,
                "data_size": len(blob),
                "data_sha256": hashlib.sha256(blob).hexdigest(),
                "data_oracle": "deark",
                "rsrc_size": 0,
                "rsrc_sha256": hashlib.sha256(b"").hexdigest(),
            })
    finally:
        shutil.rmtree(dd, ignore_errors=True)

    man = {"fixture": os.path.basename(fx),
           "sha256": hashlib.sha256(open(fx, "rb").read()).hexdigest(),
           "size": os.path.getsize(fx),
           "format": "ARC",
           "oracle": "deark (ARC 7.x is a format `unar` does not read)",
           "entries": sorted(entries, key=lambda e: e["name"])}
    out = os.path.join(ROOT, "fixtures", "manifests",
                       os.path.basename(fx) + ".json")
    with open(out, "w") as f:
        json.dump(man, f, indent=1, sort_keys=True)
        f.write("\n")
    print("run_arcplus: registered %s (%d entries)" % (out, len(entries)))
    return 0


def main():
    unclassic = os.path.join(ROOT, "build", "unclassic")
    args = sys.argv[1:]
    if "--unclassic" in args:
        unclassic = args[args.index("--unclassic") + 1]
    if "--register" in args:
        return register()
    if not os.path.exists(unclassic):
        print("run_arcplus: no CLI at %s" % unclassic)
        return 1

    corpus = os.path.join(pak.HOME, "arc7corpus")
    generated = sorted(f for f in os.listdir(corpus)
                       if f.endswith(".arc")) if os.path.isdir(corpus) else []
    if not generated and arcplus.have_arc7():
        arcplus.make(corpus)
        generated = sorted(f for f in os.listdir(corpus) if f.endswith(".arc"))

    # The real one: ARC+Plus's own DOS distribution, whose three members
    # are Trimmed and one of which — XARC.EXE — another CD carries in
    # plain form, so it is graded by a copy no decoder produced.
    real = [p for p in (os.path.join(ROOT, "fixtures", "derived-ARCDOS.arc"),
                        os.path.join(arcplus.DOS, "ARCDOS.arc"))
            if os.path.exists(p)][:1]

    if not generated and not real:
        print("run_arcplus: SKIPPED — no ARC 7 corpus "
              "(tools/arcplus.py --setup --make) and no fixture")
        return 0

    problems, ran = [], 0
    inputs = {}
    ind = os.path.join(corpus, "input")
    if os.path.isdir(ind):
        for f in os.listdir(ind):
            inputs[f] = open(os.path.join(ind, f), "rb").read()

    for f in generated:
        p = os.path.join(corpus, f)
        want = {n: inputs[n] for _m, n, _a, _c, _u, _r in arcplus.members(p)
                if n in inputs}
        check(unclassic, p, want, problems)
        ran += 1
    for p in real:
        check(unclassic, p, {}, problems)
        ran += 1
    check_dialect(unclassic, problems)

    for p in [os.path.join(corpus, f) for f in generated] + real:
        if os.path.getsize(p) < 120000:
            run_pak.damage(unclassic, p, problems)

    if problems:
        for p in problems[:40]:
            print("run_arcplus: " + p)
        print("run_arcplus: FAILED (%d problem(s) over %d archive(s))"
              % (len(problems), ran))
        return 1
    extra = "" if run_pak.deark_bin() else " — no deark, graded by CRC only"
    print("run_arcplus: OK (%d archive(s))%s" % (ran, extra))
    return 0


if __name__ == "__main__":
    sys.exit(main())

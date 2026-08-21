#!/usr/bin/env python3
"""segcheck.py — replay every segmented-archive scenario on the Mac.

The four joining schemes and the envelope step were each verified on an
emulated Mac Plus on 2026-08-14, and each by a command typed once. This
is those commands, in one place, so the claim can be re-run rather than
remembered — which is the difference between evidence and history.

`sample.txt` cannot carry these: it is a flat list of fixture names, and
the autotest opens a file called `archive.sit`, so a set needs extra
files beside it (StuffIt, Compact Pro) or its own real filenames (spanned
zip, `.NNN` splits). Two harnesses are therefore driven from here:

  run.py           for the schemes found by HEADER, whose parts may be
                   called anything — the parts go on the In floppy under
                   names that resemble nothing, and the on-screen grid is
                   compared against the Linux engine's output
  interactive.py   for everything else: the two schemes placed by NAME,
                   which need Standard File because the name is the
                   scheme; parts inside envelopes; and a chained file

Each scenario says what it would mean if it failed. Run one with
`--case NAME`, list them with `--list`.

    tools/vmac/segcheck.py                 # all of them, 4 MB
    tools/vmac/segcheck.py --mem 1M        # the floor target
    tools/vmac/segcheck.py --case cpt-middle

Budget roughly five minutes per scenario at 4 MB; the interactive ones
run on a 1x emulator and take longer, because they are watching a real
UI rather than racing to a result.
"""
import argparse, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                          # noqa: E402

FIX = os.path.join(REPO, "fixtures")

# case -> (what it proves, how it is driven)
CASES = {
    "sit-scattered": (
        "a StuffIt set whose parts are named nothing alike: found by header",
        "run"),
    "cpt-middle": (
        "a Compact Pro set OPENED AT A MIDDLE SEGMENT — the count lives only "
        "in the last one, so this fails if the search for it regresses",
        "run"),
    "cpt-truncated": (
        "the same set with its last segment withheld: must extract NOTHING, "
        "because without that segment there is no directory anywhere",
        "run"),
    "zip-named": ("a spanned zip opened at part 1 of 5, placed by name",
                  "interactive:--named:zip"),
    "split-named": ("a plain .NNN split opened at part 1 of 3",
                    "interactive:--named:split"),
    "wrapped": ("a set whose parts are each inside an envelope",
                "interactive:--wrapped"),
    "chain": ("a chained .sit.hqx: every layer off, intermediate removed",
              "interactive:--chain"),
    "ddseg-real": (
        "a DiskDoubler `SPLT` set CUT BY DISKDOUBLER ITSELF, both forks: "
        "the one scheme the Mac had never joined",
        "run"),
}


def sh(*argv, **kw):
    return subprocess.run(argv, cwd=REPO, **kw)


def cut_sit(fixture, workdir, anchor_name):
    """Three StuffIt segments; the anchor keeps the fixture's own name so
    run.py finds its manifest, the others are named nothing alike."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    from synth_sitsplit import header                     # noqa: E402
    blob = open(fixture, "rb").read()
    name = os.path.basename(fixture).encode("mac_roman")[:31]
    cut = (len(blob) + 2) // 3
    out = []
    for i, nm in enumerate([anchor_name, "middle-bit", "zz-tail"]):
        p = os.path.join(workdir, nm)
        with open(p, "wb") as f:
            f.write(header(i + 1, name, 0, len(blob)))
            f.write(blob[i * cut:(i + 1) * cut])
        out.append(p)
    return out


def cut_cpt(fixture, workdir, anchor_name, drop_last=False):
    """A real Compact Pro set, cut the way the application cuts one. The
    ANCHOR is segment 2 on purpose: opening a middle segment is the case
    that needs the search for the segment carrying the index."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import synth_cptsplit as C                            # noqa: E402
    parts = C.write_set(fixture, workdir, 24576, base="Set.cpt")
    names = [anchor_name, "disk-one", "third-piece", "LAST.BIT"]
    out = []
    order = [1, 0, 2, 3]          # anchor = segment 2
    for slot, idx in enumerate(order):
        if idx >= len(parts):
            continue
        dest = os.path.join(workdir, names[slot])
        shutil.move(parts[idx], dest)
        out.append((idx, dest))
    out.sort()
    paths = [p for _i, p in out]
    if drop_last:
        os.remove(paths[-1])
        paths = paths[:-1]
    anchor = os.path.join(workdir, anchor_name)
    return anchor, [p for p in paths if p != anchor]


def read_out_volume_forks(rundir, name):
    """Both forks of one file off a kept Out volume, or (None, None).

    `hcopy -r` gives the data fork only, which is all the other cases
    need. A joined `SPLT` set is the one case where the resource fork
    is most of the file, so this one goes through MacBinary.
    """
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    dest = os.path.join(env["HOME"], "got.bin")
    try:
        if subprocess.run(["hmount", os.path.join(rundir, "out.dsk")],
                          env=env, capture_output=True).returncode != 0:
            return None, None
        r = subprocess.run(["hcopy", "-m", ":" + name, dest],
                           env=env, capture_output=True)
        subprocess.run(["humount"], env=env, capture_output=True)
        if r.returncode != 0:
            return None, None
        blob = open(dest, "rb").read()
        dlen = int.from_bytes(blob[83:87], "big")
        rlen = int.from_bytes(blob[87:91], "big")
        pad = lambda n: (n + 127) // 128 * 128
        data = blob[128:128 + dlen]
        rsrc = blob[128 + pad(dlen):128 + pad(dlen) + rlen]
        return data, rsrc
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


def read_out_volume(rundir, name):
    """One file off a kept Out volume, as bytes, or None."""
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    dest = os.path.join(env["HOME"], "got.bin")
    try:
        if subprocess.run(["hmount", os.path.join(rundir, "out.dsk")],
                          env=env, capture_output=True).returncode != 0:
            return None
        r = subprocess.run(["hcopy", "-r", ":" + name, dest],
                           env=env, capture_output=True)
        subprocess.run(["humount"], env=env, capture_output=True)
        return open(dest, "rb").read() if r.returncode == 0 else None
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


# The real `SPLT` set the Mac case uses: registered from
# ssokolow/diskdoubler-test-files by tools/run_ddtf.py --register. Both
# forks, because the resource fork is the half a data-fork-only check
# would miss, and DiskDoubler Pro 4.1.1 cut it.
DDSEG_SET = "ddtf-ddpro411ad1.dd"
DDSEG_RSRC = "ddtf-ddpro411ad1.dd.ad"


def run_ddseg_real(case, mem, workdir):
    """A set DiskDoubler itself cut, joined on the Mac.

    Graded twice: the on-screen grid against this engine's Linux output
    (`run.py --expect`, since a part has no oracle manifest — nothing
    but DiskDoubler writes this container), and the joined FILE off the
    Out volume against the file the corpus publishes, both forks. The
    second is what makes the case worth its five minutes: the grid
    aggregates and so cannot fail on a name, and the resource fork is
    two thirds of what a joined `.sea` set contains.
    """
    parts = sorted(f for f in os.listdir(FIX)
                   if f.startswith(DDSEG_SET + ".") and f[-1].isdigit())
    whole = os.path.join(FIX, DDSEG_SET)
    side = os.path.join(FIX, DDSEG_RSRC)
    if len(parts) < 2 or not os.path.exists(whole) or not os.path.exists(side):
        print(f"segcheck: SKIP {case} (no real SPLT set in fixtures/ — "
              f"tools/run_ddtf.py --register)")
        return None
    sys.path.insert(0, os.path.join(REPO, "tools"))
    from make_manifests import parse_appledouble           # noqa: E402
    anchor = os.path.join(FIX, parts[0])
    argv = [sys.executable, os.path.join(HERE, "run.py"), anchor,
            "--mem", mem, "--expect", "--keep-disks"]
    for i, e in enumerate(parts[1:]):
        # Named nothing like part 1: a `SPLT` part is matched by the 26
        # identity bytes in its header, never by its filename.
        argv += ["--extra-file", f"{os.path.join(FIX, e)}:zzz-piece{i + 2}"]
    r = subprocess.run(argv, capture_output=True, text=True)
    out = r.stdout + r.stderr
    kept = [l.split("disks kept in", 1)[1].strip()
            for l in out.splitlines() if "disks kept in" in l]
    if not kept:
        return False, "run.py kept no disks to read"
    # The joined file takes the OPENED PART's name minus a trailing
    # ".N", and nothing else — a `SPLT` part carries no name, and the
    # ".N" rule is the only thing the host strips. run.py puts the
    # anchor on the floppy as ARCHIVE_NAME, which has no numeric suffix,
    # so the joined file is called exactly that. (Measured 2026-08-21;
    # the first version of this case looked for the name with the
    # extension removed, which is the rule for gzip and not for this.)
    got, gotr = read_out_volume_forks(kept[0], R.ARCHIVE_NAME)
    shutil.rmtree(kept[0], ignore_errors=True)
    want = open(whole, "rb").read()
    wantr = parse_appledouble(side)[0]
    if got is None:
        return False, ("the joined file is not on the Out volume as %r; "
                       "run.py said: %s"
                       % (R.ARCHIVE_NAME, out.strip().splitlines()[-1]
                          if out.strip() else "nothing"))
    # The resource fork is compared with bytes 16..127 masked, the
    # convention every other on-Mac check here uses: the Resource
    # Manager stamps that region of the header whenever it touches a
    # file, so a fork written on a Mac is never byte-identical to the
    # same fork on Linux, and a raw comparison fails on 112 bytes that
    # nothing points at (tools/vmac_check.py says why that is safe).
    from vmac_check import mask_reserved                  # noqa: E402
    bad = []
    if got != want:
        bad.append("data %d B (want %d)" % (len(got), len(want)))
    if mask_reserved(gotr) != mask_reserved(wantr):
        bad.append("rsrc %d B (want %d)" % (len(gotr), len(wantr)))
    if bad:
        return False, "the joined file differs: " + ", ".join(bad)
    grid = r.returncode == 0
    return grid, ("joined on the Mac byte for byte, %d B data + %d B rsrc "
                  "(the resource header's OS-stamped bytes masked), and the "
                  "grid agrees" % (len(want), len(wantr)) if grid else
                  "the file is right but the grid did not agree: " +
                  out.strip()[-200:])


def run_scheme(case, mem, workdir):
    if case == "ddseg-real":
        return run_ddseg_real(case, mem, workdir)
    fixture = {"sit-scattered": "derived-Downer.sit"}.get(
        case, "derived-Education7.1.cpt")
    src = os.path.join(FIX, fixture)
    if not os.path.exists(src):
        print(f"segcheck: SKIP {case} ({fixture} absent)")
        return None
    d = os.path.join(workdir, case)
    os.makedirs(d)
    if case == "sit-scattered":
        parts = cut_sit(src, d, fixture)
        anchor, extras = parts[0], parts[1:]
    else:
        anchor, extras = cut_cpt(src, d, fixture,
                                 drop_last=(case == "cpt-truncated"))
    argv = [sys.executable, os.path.join(HERE, "run.py"), anchor, "--mem", mem]
    for e in extras:
        argv += ["--extra-file", f"{e}:{os.path.basename(e)}"]
    # A StuffIt set yields the JOINED ARCHIVE — one file — where the
    # fixture's manifest describes what is INSIDE that archive, so the
    # grid can never match it and the disk is the only honest check.
    # (Compact Pro is different: its reader emits the archive's entries
    # directly, which is exactly what the manifest lists.)
    if case == "sit-scattered":
        argv += ["--keep-disks"]
    r = subprocess.run(argv, capture_output=True, text=True)
    out = r.stdout + r.stderr
    if case == "cpt-truncated":
        # A truncated set must FAIL the comparison by extracting nothing.
        ok = "0 file(s)" in out
        return ok, "extracted nothing, as it must" if ok else out.strip()[-200:]
    if case == "sit-scattered":
        kept = [l.split("disks kept in", 1)[1].strip()
                for l in out.splitlines() if "disks kept in" in l]
        if not kept:
            return False, "run.py kept no disks to read"
        got = read_out_volume(kept[0], os.path.basename(fixture))
        want = open(src, "rb").read()
        shutil.rmtree(kept[0], ignore_errors=True)
        if got is None:
            return False, "the joined archive is not on the Out volume"
        return got == want, ("joined byte-exact, %d B" % len(want)
                             if got == want else
                             "joined %d B, expected %d" % (len(got), len(want)))
    return r.returncode == 0, out.strip().splitlines()[-1] if out else ""


def run_interactive(spec, mem, workdir):
    fixture = os.path.join(FIX, "derived-Downer.sit")
    if "chain" in spec:
        fixture = os.path.join(FIX, "boogers-152.hqx")
    if "zip" in spec:
        fixture = os.path.join(FIX, "derived-EmpireBuilderDemo.sit")
    if not os.path.exists(fixture):
        print(f"segcheck: SKIP {spec} ({os.path.basename(fixture)} absent)")
        return None
    flags = spec.split(":")[1:]
    argv = [sys.executable, os.path.join(HERE, "interactive.py")]
    argv += ["--" + flags[0].lstrip("-")] if len(flags) == 1 else \
            ["--" + flags[0].lstrip("-"), flags[1]]
    argv += ["--emu", "mv-1M-1x" if mem == "1M" else "mv-4M-1x",
             "-o", os.path.join(workdir, "shots"), fixture]
    r = subprocess.run(argv, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().splitlines()
    tail = [l for l in out if "interactive:" in l]
    return r.returncode == 0, tail[-2] if len(tail) > 1 else (tail[-1] if tail else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", action="append")
    ap.add_argument("--mem", default="4M", choices=("4M", "1M"))
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for k, (why, how) in CASES.items():
            print(f"{k:15s} {how.split(':')[0]:12s} {why}")
        return 0

    cases = [c for c in (args.case or CASES) if c in CASES]
    workroot = tempfile.mkdtemp(prefix="segcheck-")
    results = []
    try:
        for c in cases:
            why, how = CASES[c]
            print(f"== {c}: {why}")
            r = (run_scheme(c, args.mem, workroot) if how == "run"
                 else run_interactive(how, args.mem, workroot))
            if r is None:
                continue
            ok, detail = r
            results.append((c, ok))
            print(f"   {'PASS' if ok else 'FAIL'}  {detail}")
    finally:
        shutil.rmtree(workroot, ignore_errors=True)

    bad = [c for c, ok in results if not ok]
    print(f"segcheck: {len(results) - len(bad)}/{len(results)} at {args.mem}"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

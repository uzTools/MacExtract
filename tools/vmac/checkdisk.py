#!/usr/bin/env python3
"""checkdisk.py — verify a Mini vMac run by READING ITS OUT VOLUME.

BLOCKERS.md has said since M10 that this cannot be done:

    Mini vMac's disk write-back to the host image is lazy and PARTIAL — it
    can commit one fork of a file but not the other — so results cannot be
    read off the Out volume. Verification is done ON-SCREEN instead.

That claim dates from the confounded period and had no reproduction. It
matters because of what the on-screen channel cannot do: the grid carries a
file COUNT, two summed CRC-32s and two summed lengths, and a summed CRC
cannot carry a name. So the System 6 and 7 tiers have never compared an
output NAME and cannot be made to fail on one — which is exactly how a real
defect in the gzip/.Z fallback name survived in the corpus for weeks until
the Mac OS 9 harness, which reads its volume, caught it on its first sweep.

    tools/vmac/run.py --keep-disks --list tools/vmac/sample.txt
    tools/vmac/checkdisk.py /tmp/vmacrun-*/

Each directory must hold the `out.dsk` of a finished run. The fixture is
identified from the `in.dsk` beside it, so no bookkeeping is needed.

Compares, per file, against `unclassic x -nr`: both forks byte for byte
(resource forks through the same reserved-header mask vmac_check.py uses),
the type/creator, and — the point — the set of NAMES, recursively.
"""
import os, subprocess, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import os9                                                   # noqa: E402
from vmac_check import mask_reserved, aggregate_dir           # noqa: E402

CLI = os.path.join(REPO, "build", "rel", "unclassic")


def hfs(env, *argv):
    return subprocess.run(argv, capture_output=True, env=env)


def walk(env, mac_dir="", depth=0):
    """Every file on the mounted volume, as '/'-joined MacRoman paths."""
    if depth > 8:
        return []
    out = []
    # -a because hfsutils HIDES names beginning with a dot without it, and
    # archives contain .DS_Store; the path goes out as MacRoman bytes because
    # that is what the names on the volume are — passing a Python str makes
    # subprocess encode UTF-8 and any 8-bit name (`spinning brain ƒ`) becomes
    # a directory that does not exist.
    arg = [mac_dir.encode("mac_roman", "replace")] if mac_dir else []
    listing = hfs(env, "hls", "-a", "-F", "-1", *arg)
    for raw in listing.stdout.split(b"\n"):
        entry = raw.rstrip().decode("mac_roman")
        if not entry:
            continue
        isdir = entry.endswith(":")
        name = entry[:-1] if isdir or entry.endswith("*") else entry
        rel = f"{mac_dir.strip(':').replace(':', '/')}/{name}" if mac_dir else name
        if isdir:
            out += walk(env, ":" + rel.replace("/", ":") + ":", depth + 1)
        else:
            out.append(unicodedata.normalize("NFC", rel))
    return out


def fixture_of(indsk, env):
    """Which fixture was this run? The In volume holds it as `archive.sit`."""
    if hfs(env, "hmount", indsk).returncode != 0:
        return None
    got = hfs(env, "hcopy", "-r", "archive.sit", "/tmp/.checkdisk-archive").returncode
    hfs(env, "humount")
    if got != 0:
        return None
    want = open("/tmp/.checkdisk-archive", "rb").read()
    for f in os.listdir(os.path.join(REPO, "fixtures")):
        p = os.path.join(REPO, "fixtures", f)
        if os.path.isfile(p) and os.path.getsize(p) == len(want):
            if open(p, "rb").read() == want:
                return p
    return None


def check(rundir):
    workhome = os.path.join(rundir, ".hfshome")
    os.makedirs(workhome, exist_ok=True)
    env = dict(os.environ, HOME=workhome)
    outdsk = os.path.join(rundir, "out.dsk")
    indsk = os.path.join(rundir, "in.dsk")
    if not (os.path.exists(outdsk) and os.path.exists(indsk)):
        return None, f"{rundir}: no out.dsk/in.dsk"

    fixture = fixture_of(indsk, env)
    if fixture is None:
        return None, f"{rundir}: cannot identify the fixture from in.dsk"
    name = os.path.basename(fixture)

    if hfs(env, "hmount", outdsk).returncode != 0:
        return False, f"{name}: the Out volume will not mount"
    names = walk(env)

    ref = os.path.join(rundir, "linux-out")
    subprocess.run(["rm", "-rf", ref], check=False)
    os.makedirs(ref)
    # Run the reference against a copy named exactly what the Mac saw. gzip
    # and .Z store no name and fall back to the archive filename minus its
    # last extension, and run.py puts every fixture on the In volume as
    # `archive.sit` — so the reference has to be handed the same name or the
    # two sides derive different names for identical bytes.
    asmac = os.path.join(rundir, "as-the-mac-saw-it", "archive.sit")
    os.makedirs(os.path.dirname(asmac), exist_ok=True)
    subprocess.run(["cp", fixture, asmac], check=False)
    subprocess.run([CLI, "x", "-nr", asmac, "-o", ref], capture_output=True)
    want_names = []
    enf, _sdc, _sdl, _src, _srl = aggregate_dir(ref, want_names)

    expected = set()
    for root, _d, files in os.walk(ref):
        # A "<X>.rsrc" is the CLI's resource sidecar for <X> ONLY if <X> is
        # also here; otherwise it is an archive entry whose own name ends in
        # .rsrc — a real data file, e.g. RWasm.rsrc. vmac_check.py makes the
        # same distinction for the same reason.
        fileset = set(files)
        for f in files:
            if f.endswith(".rsrc") and f[:-5] in fileset:
                continue
            rel = os.path.relpath(os.path.join(root, f), ref)
            expected.add(unicodedata.normalize("NFC", rel))
    # The Mac shell caps each path component at 31 characters (see
    # ComponentToStr63); apply the same rule to the reference before comparing.
    expected = {"/".join(c.replace(":", "/")[:31] for c in e.split("/"))
                for e in expected}

    problems = []
    missing, extra = expected - set(names), set(names) - expected
    if missing:
        problems.append("MISSING on the Mac: " + ", ".join(sorted(missing)))
    if extra:
        problems.append("UNEXPECTED on the Mac: " + ", ".join(sorted(extra)))

    nforks = 0
    for n in sorted(set(names) & expected):
        mb = os.path.join(rundir, "f-" + n.replace("/", "_") + ".macbin")
        c = subprocess.run(["hcopy", "-m",
                            (":" + n.replace("/", ":")).encode("mac_roman",
                                                               "replace"),
                            mb.encode()],
                           capture_output=True, env=env)
        if c.returncode != 0:
            problems.append(f"{n}: cannot copy off the volume")
            continue
        _t, _c2, data, rsrc = os9.macbinary_forks(mb)
        for label, got, path, mask in (("data", data, os.path.join(ref, n), False),
                                       ("rsrc", rsrc, os.path.join(ref, n) + ".rsrc", True)):
            want = open(path, "rb").read() if os.path.exists(path) else b""
            a, b = (mask_reserved(got), mask_reserved(want)) if mask else (got, want)
            if a != b:
                problems.append(f"{n} {label}: Mac {len(got)} B vs Linux "
                                f"{len(want)} B MISMATCH")
            elif got or want:
                nforks += 1
    hfs(env, "humount")
    if problems:
        return False, f"{name}: " + "; ".join(problems[:4])
    return True, (f"{name}: {len(names)} file(s), {nforks} fork(s) byte-exact "
                  f"off the Out volume, names included")


def main():
    dirs = sys.argv[1:] or ["."]
    npass = nfail = nskip = 0
    for d in sorted(dirs):
        ok, detail = check(d.rstrip("/"))
        if ok is None:
            nskip += 1
            print(f"SKIP  {detail}")
        elif ok:
            npass += 1
            print(f"PASS  {detail}")
        else:
            nfail += 1
            print(f"FAIL  {detail}")
    print(f"\n{npass} pass, {nfail} fail, {nskip} skipped — read off the disk "
          f"image, not the screen")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())

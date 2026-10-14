#!/usr/bin/env python3
"""run_unwrap.py — envelope auto-unwrap acceptance test.

Real-world files are chained (.sit.bin, .sit.hqx, .tar.Z). Extracting
the OUTER fixture with auto-unwrap enabled (the default) must produce
exactly the INNER layer's oracle manifest contents, with the
intermediate envelope file removed.
"""
import gzip, json, os, subprocess, sys, tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIXDIR = os.path.join(ROOT, "fixtures")
sys.path.insert(0, os.path.dirname(__file__))
from run_diff import normpath, sha256_file, collect_outputs, sidecar  # noqa: E402

# (outer fixture, manifest describing the fully-unwrapped contents)
CHAINS = [
    ("ACInfo_Comm.sit.bin", "derived-ACInfo_Comm.sit.json"),      # MacBinary -> SIT
    ("boogers-152.hqx", "derived-boogers152.sit.json"),           # BinHex -> SIT
    ("synth-exo-tar-Z.tar.Z", "synth-exo-tar.tar.json"),          # .Z -> tar
    ("Ultimate_Copland_1.1.sit.bin", "derived-Ultimate_Copland_1.1.sit.1.json"),
    ("popper-1.7.tar.Z", "derived-popper-1.7.tar.json"),   # real 1990 .Z -> v7 tar
]


def check(macextract, outer, manifest):
    fx = os.path.join(FIXDIR, outer)
    with open(os.path.join(FIXDIR, "manifests", manifest)) as f:
        man = json.load(f)
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([macextract, "x", "--forks", "hidden", "-o", tmp, fx],
                           capture_output=True, timeout=300)
        if r.returncode != 0:
            problems.append(f"exit {r.returncode}: {r.stderr.decode()[:200]}")
        files, dirs = collect_outputs(tmp)
        for e in man["entries"]:
            name = normpath(e["name"])
            if e.get("is_dir"):
                if name not in dirs and name not in files:
                    problems.append(f"missing dir {name!r}")
                continue
            p = files.pop(name, None)
            if p is None:
                problems.append(f"missing {name!r}")
                continue
            if sha256_file(p) != e["data_sha256"]:
                problems.append(f"{name!r}: data mismatch")
            rp = files.pop(sidecar(name), None)
            rsz = os.path.getsize(rp) if rp else 0
            if rsz != e["rsrc_size"]:
                problems.append(f"{name!r}: rsrc size {rsz} != {e['rsrc_size']}")
        for leftover in files:
            problems.append(f"leftover: {leftover!r}")  # envelope not removed?
    return problems


def check_same_name(macextract):
    """A layer with no name of its own is named after the file it came
    from, minus an extension — so when that file HAS none, the inner
    entry and the envelope being unwrapped are the same path. Until
    2026-10-14 the entry was written over the envelope while it was read,
    and the deletion of the envelope then removed the entry: exit 0 and
    an empty directory. Two nameless gzip layers in a file called `Same`
    are the smallest file that does it."""
    payload = b"the payload of two nameless layers\n" * 50
    with tempfile.TemporaryDirectory() as src, \
         tempfile.TemporaryDirectory() as tmp:
        fx = os.path.join(src, "Same")
        with open(fx, "wb") as f:
            f.write(gzip.compress(gzip.compress(payload, mtime=0), mtime=0))
        r = subprocess.run([macextract, "x", "-o", tmp, fx],
                           capture_output=True, timeout=120)
        got = sorted(os.listdir(tmp))
        p = os.path.join(tmp, "Same")
        if r.returncode != 0:
            return [f"exit {r.returncode}: {r.stderr.decode()[:200]}"]
        if got != ["Same"] or open(p, "rb").read() != payload:
            return [f"wanted Same holding the payload, got {got}"]
    return []


def main():
    macextract = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(ROOT, "build/san/macextract")
    fails = 0
    ran = 0
    for outer, manifest in CHAINS:
        if not os.path.exists(os.path.join(FIXDIR, outer)) or \
           not os.path.exists(os.path.join(FIXDIR, "manifests", manifest)):
            print(f"unwrap: SKIP {outer} (fixture/manifest absent)")
            continue
        ran += 1
        problems = check(macextract, outer, manifest)
        if problems:
            fails += 1
            print(f"UNWRAP FAIL {outer}")
            for p in problems[:6]:
                print(f"    {p}")
        else:
            print(f"unwrap ok: {outer} -> {manifest}")
    problems = check_same_name(macextract)
    ran += 1
    if problems:
        fails += 1
        print("UNWRAP FAIL two layers with one name")
        for p in problems:
            print(f"    {p}")
    else:
        print("unwrap ok: two nameless layers that share a name")
    print(f"unwrap: {ran - fails}/{ran} chains ok")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

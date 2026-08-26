#!/usr/bin/env python3
"""synth_exo.py — deterministic zip/gzip/tar/.Z fixtures for M8.

The system encoders (Info-ZIP zip, GNU gzip, GNU tar, ncompress) are
independent reference implementations, which makes their output ideal
differential ground truth; the oracle manifests still come from unar
like every other fixture. Determinism: fixed mtimes, TZ=UTC, gzip -n
or fixed input mtime, tar --sort=name --mtime/--owner/--group pinned,
zip -X with a sorted file list.

Usage: synth_exo.py --kind <name> -o <output>
Kinds: zip-deflate, zip-store, tar, gz, gz-named, Z, tar-Z
Provenance in SOURCES.md: synthetic:tools/synth_exo.py --kind K
"""
import argparse, os, random, shutil, subprocess, sys, tempfile

MTIME = "199001010000"          # touch -t format, interpreted in UTC


def build_tree(root, rng):
    os.makedirs(os.path.join(root, "docs"))
    os.makedirs(os.path.join(root, "bin"))
    with open(os.path.join(root, "README.txt"), "w") as f:
        f.write("macextract synthetic corpus\n" * 20)
    with open(os.path.join(root, "docs", "manual.txt"), "w") as f:
        f.write("the quick brown fox jumps over the lazy dog\n" * 50)
    with open(os.path.join(root, "bin", "blob.dat"), "wb") as f:
        f.write(bytes(rng.randrange(256) for _ in range(3000)))
    with open(os.path.join(root, "bin", "zeros.dat"), "wb") as f:
        f.write(b"\0" * 2048)
    paths = sorted(os.listdir(root))   # top level; the tools recurse
    for base, dirs, files in os.walk(root):
        for n in dirs + files:
            subprocess.run(["touch", "-t", MTIME,
                            os.path.join(base, n)], check=True)
    subprocess.run(["touch", "-t", MTIME, root], check=True)
    return sorted(paths)


def run(cmd, cwd):
    env = dict(os.environ, TZ="UTC")
    subprocess.run(cmd, cwd=cwd, env=env, check=True,
                   stdout=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True)
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()
    out = os.path.abspath(args.output)
    rng = random.Random(42)

    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "t")
        os.makedirs(tree)
        paths = build_tree(tree, rng)
        arc = os.path.join(tmp, "arc")

        if args.kind in ("zip-deflate", "zip-store"):
            level = "-9" if args.kind == "zip-deflate" else "-0"
            run(["zip", "-r", "-X", "-q", level, arc + ".zip"] + paths, tree)
            shutil.move(arc + ".zip", out)
        elif args.kind == "tar":
            run(["tar", "--format=ustar", "--sort=name", "--owner=0",
                 "--group=0", "--numeric-owner",
                 "--mtime=1990-01-01 00:00:00 UTC",
                 "-cf", arc + ".tar"] + paths, tree)
            shutil.move(arc + ".tar", out)
        elif args.kind == "tar-Z":
            run(["tar", "--format=ustar", "--sort=name", "--owner=0",
                 "--group=0", "--numeric-owner",
                 "--mtime=1990-01-01 00:00:00 UTC",
                 "-cf", arc + ".tar"] + paths, tree)
            run(["compress", "-f", arc + ".tar"], tmp)
            shutil.move(arc + ".tar.Z", out)
        elif args.kind == "gz":
            shutil.copy(os.path.join(tree, "docs", "manual.txt"), arc)
            run(["gzip", "-n", "-9", arc], tmp)
            shutil.move(arc + ".gz", out)
        elif args.kind == "gz-named":
            named = os.path.join(tmp, "manual.txt")
            shutil.copy(os.path.join(tree, "docs", "manual.txt"), named)
            subprocess.run(["touch", "-t", MTIME, named], check=True,
                           env=dict(os.environ, TZ="UTC"))
            run(["gzip", "-N", "-1", named], tmp)
            shutil.move(named + ".gz", out)
        elif args.kind == "Z":
            shutil.copy(os.path.join(tree, "docs", "manual.txt"), arc)
            run(["compress", "-f", arc], tmp)
            shutil.move(arc + ".Z", out)
        else:
            print("unknown kind", args.kind, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

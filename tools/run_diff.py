#!/usr/bin/env python3
"""run_diff.py — differential acceptance tests.

For every manifest in fixtures/manifests/ whose fixture is present:
  1. `unclassic x` into a temp dir
  2. compare every entry byte-for-byte against the oracle manifest:
     data fork sha256+size, resource fork sha256+size, and type/creator
     when recorded (via `unclassic l`).

Formats the engine does not implement yet are skipped (reported), not
failed: milestones land one format at a time. A manifest whose format
IS implemented must pass completely.
"""
import argparse, hashlib, json, os, subprocess, sys, tempfile, unicodedata

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIXDIR = os.path.join(ROOT, "fixtures")

# lsar format name -> our format name; grown as milestones land.
# Only fixtures whose format appears here are asserted on.
IMPLEMENTED = {
    "MacBinary": "MacBinary",              # M1
    "AppleSingle": "AppleSingle",          # M1
    "AppleDouble": "AppleDouble",          # M1
    "BinHex": "BinHex 4",                  # M2
    "PackIt": "PackIt",                    # M3
    # "Compact Pro": "Compact Pro",        # M4
    # "StuffIt": "StuffIt",                # M5/M6
    # "StuffIt 5": "StuffIt 5",            # M7
    # "Zip": "Zip", "gzip": "Gzip",        # M8
    # "Tar": "Tar", "Compress": "Unix compress",
}


def norm(name):
    # NFC-normalize, and neutralize path-separator sanitization
    # differences: classic Mac names may contain '/', which unar writes
    # as '_' and unclassic as ':' — map all three to '_' on both sides.
    n = unicodedata.normalize("NFC", name)
    return n.replace(":", "_").replace("/", "_")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def normpath(path):
    """norm() each path component, preserving directory separators."""
    return "/".join(norm(c) for c in path.split("/"))


def collect_outputs(tmp):
    """Map normalized relative path -> full path for files and dirs."""
    files, dirs = {}, set()
    for root, ds, fs in os.walk(tmp):
        rel = os.path.relpath(root, tmp)
        for d in ds:
            dirs.add(normpath(os.path.normpath(os.path.join(rel, d))))
        for f in fs:
            p = normpath(os.path.normpath(os.path.join(rel, f)))
            files[p] = os.path.join(root, f)
    return files, dirs


def parse_listing(out):
    """Parse `unclassic l` output -> {name: (type, creator)}."""
    meta = {}
    for line in out.splitlines():
        if not line.startswith("f "):
            continue
        # f <data> <rsrc> <type>/<creator> <name...>
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        tc = parts[3]
        if len(tc) == 9 and tc[4] == "/":
            meta[normpath(parts[4])] = (tc[:4], tc[5:])
    return meta


def check_fixture(unclassic, man, verbose):
    fx = os.path.join(FIXDIR, man["fixture"])
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([unclassic, "x", "-o", tmp, fx],
                           capture_output=True, timeout=300)
        if r.returncode != 0:
            problems.append(f"exit {r.returncode}: {r.stderr.decode()[:300]}")
        files, dirs = collect_outputs(tmp)

        lr = subprocess.run([unclassic, "l", fx], capture_output=True, timeout=60)
        listing = parse_listing(lr.stdout.decode("utf-8", "replace"))

        for e in man["entries"]:
            name = normpath(e["name"])
            if e.get("is_dir"):
                if name not in dirs and name not in files:
                    problems.append(f"missing dir: {name!r}")
                continue
            path = files.pop(name, None)
            if path is None:
                problems.append(f"missing file: {name!r}")
                continue
            sz = os.path.getsize(path)
            if sz != e["data_size"]:
                problems.append(f"{name!r}: data size {sz} != {e['data_size']}")
            elif sha256_file(path) != e["data_sha256"]:
                problems.append(f"{name!r}: data sha mismatch")
            rp = files.pop(name + ".rsrc", None)
            rsz = os.path.getsize(rp) if rp else 0
            if rsz != e["rsrc_size"]:
                problems.append(f"{name!r}: rsrc size {rsz} != {e['rsrc_size']}")
            elif rp and sha256_file(rp) != e["rsrc_sha256"]:
                problems.append(f"{name!r}: rsrc sha mismatch")
            if "type" in e and name in listing:
                t, c = listing[name]
                if t != e["type"] or (e.get("creator") and c != e["creator"]):
                    problems.append(
                        f"{name!r}: type/creator {t}/{c} != "
                        f"{e['type']}/{e.get('creator')}")
        for leftover in files:
            problems.append(f"unexpected output: {leftover!r}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unclassic", default=os.path.join(ROOT, "build/san/unclassic"))
    ap.add_argument("--all", action="store_true",
                    help="run even not-yet-implemented formats")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--format", help="only fixtures of this lsar format")
    args = ap.parse_args()

    mandir = os.path.join(FIXDIR, "manifests")
    manifests = sorted(f for f in os.listdir(mandir)
                       if f.endswith(".json")) if os.path.isdir(mandir) else []

    ran = passed = skipped_fmt = skipped_missing = 0
    fails = []
    for mf in manifests:
        with open(os.path.join(mandir, mf)) as f:
            man = json.load(f)
        if not os.path.exists(os.path.join(FIXDIR, man["fixture"])):
            skipped_missing += 1
            continue
        fmt = man.get("format")
        if args.format and fmt != args.format:
            continue
        if not args.all and fmt not in IMPLEMENTED:
            skipped_fmt += 1
            continue
        ran += 1
        problems = check_fixture(args.unclassic, man, args.verbose)
        if problems:
            fails.append((man["fixture"], problems))
            print(f"DIFF FAIL {man['fixture']} ({fmt})")
            for p in problems[:8]:
                print(f"    {p}")
            if len(problems) > 8:
                print(f"    ... {len(problems) - 8} more")
        else:
            passed += 1
            if args.verbose:
                print(f"diff ok: {man['fixture']} ({fmt})")

    print(f"diff: {passed}/{ran} fixtures ok "
          f"({skipped_fmt} formats pending, {skipped_missing} fixtures absent)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

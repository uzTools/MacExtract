#!/usr/bin/env python3
"""measure_depth.py — the deepest FOLDER nesting any archive here reaches.

Written on 2026-10-07 to ask whether `UNC_PATH_MAXDEPTH` (24) was
reachable by anything on this disk. It was not, and the constant is
deleted the same day — what bounds nesting now is the path STRING at
`UNC_NAME_MAX`, which eight 31-character folders already fill. The
question the answer serves has not changed: how deep the corpus actually
goes is about the corpus and not about the code, so it is measured
rather than argued: this lists every archive with `macextract l` and counts the
separators in the deepest path the listing prints.

Depth here is the number of enclosing FOLDERS, which is the quantity
`UncPath.depth` holds — a leaf at the archive's root is depth 0.

What this CANNOT see:

  * a depth the listing does not reach. An archive that fails partway
    reports the deepest path it got to, not the deepest it has; the
    `err` column says which rows those are.
  * nesting inside an inner archive that is not an ENVELOPE. Envelope
    layers are peeled with `tools/envelopes.py` so a `.dd.hqx` is
    measured as the DiskDoubler archive it is, but a `.sit` stored as
    one entry of a `.pkg` is one row here and its own tree is measured
    only when that inner file is listed in its own right.
  * a format that does not use the path walker at all. StuffIt and
    Compact Pro carry their own depth handling through
    `unc_entry_path_append`; they are listed for scale but none of
    this file's conclusions about `unc_path_push` apply to them.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import envelopes

ROW = re.compile(r"^[dfl] +\S+ +\S+ +\S+ +(.*)$")


def listing(cli, path):
    """(format, deepest, entries, failed) for one file."""
    try:
        p = subprocess.run([cli, "l", path], capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        return None, -1, 0, True
    out = p.stdout.decode("utf-8", "replace").splitlines()
    # The "<file>: <format>" banner is on stderr, not stdout.
    err = p.stderr.decode("utf-8", "replace").splitlines()
    fmt = ""
    for line in err:
        if line.startswith(path + ": "):
            fmt = line[len(path) + 2:].strip()
            break
    deepest, entries = 0, 0
    for line in out:
        m = ROW.match(line)
        if not m:
            continue
        entries += 1
        deepest = max(deepest, m.group(1).count("/"))
    return fmt, deepest, entries, p.returncode != 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", default="build/macextract")
    ap.add_argument("--per-file", action="store_true",
                    help="one row per archive instead of one per format")
    ap.add_argument("roots", nargs="*", default=["fixtures"])
    args = ap.parse_args()

    files = []
    for root in args.roots:
        if os.path.isfile(root):
            files.append(root)
            continue
        for dirpath, _, names in os.walk(root):
            for n in names:
                if n.endswith((".md", ".json", ".log", ".txt")):
                    continue
                files.append(os.path.join(dirpath, n))

    byfmt = {}
    for f in sorted(files):
        work = tempfile.mkdtemp(prefix="depth-")
        try:
            try:
                paths = envelopes.layers(args.cli, f, work)
            except Exception:
                paths = [f]
            for p in paths:
                fmt, deepest, entries, failed = listing(args.cli, p)
                if fmt is None or not fmt or fmt == "unknown":
                    continue
                if args.per_file:
                    print("%2d  %-24s %s%s" % (deepest, fmt, p,
                                               "  (err)" if failed else ""))
                cur = byfmt.setdefault(fmt, [0, 0, None, 0])
                cur[1] += 1
                cur[3] += entries
                if deepest > cur[0]:
                    cur[0], cur[2] = deepest, f
        finally:
            shutil.rmtree(work, ignore_errors=True)

    if not args.per_file:
        print("%-24s %8s %8s %7s  %s" % ("format", "archives", "entries",
                                         "deepest", "where"))
        for fmt in sorted(byfmt, key=lambda k: -byfmt[k][0]):
            d, n, where, ent = byfmt[fmt]
            print("%-24s %8d %8d %7d  %s" % (fmt, n, ent, d,
                                             os.path.basename(where or "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())

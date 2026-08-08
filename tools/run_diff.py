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
import argparse, hashlib, json, os, re, subprocess, sys, tempfile
import unicodedata

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
    "Compact Pro": "Compact Pro",          # M4
    "StuffIt": "StuffIt",                  # M5/M6
    "StuffIt 5": "StuffIt 5",              # M7
    "Zip": "Zip",                          # M8
    "Gzip": "Gzip",
    "Tar": "Tar",
    "Compress": "Unix compress",
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


def sidecar(path):
    """Resource-fork sidecar path for an entry: "dir/file" -> "dir/._file".

    Both sides of the diff use the "._" prefix (`unclassic --forks
    hidden`, `unar -k hidden`) rather than a ".rsrc" suffix, because
    the suffix collides with real entries in archives that hold both
    "X" and "X.rsrc". DECISIONS.md, 2026-08-08.
    """
    head, _, tail = path.rpartition("/")
    return f"{head}/._{tail}" if head else f"._{tail}"


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


ENTRY_ERR = re.compile(r"^unclassic: (.*): (.*)$")
TALLY = re.compile(r"^unclassic: (\d+) of (\d+) entries failed$")


def parse_entry_errors(stderr):
    """Return ({normalized entry name: reason}, all_entries_unsupported).

    `unclassic` reports a failed entry as "unclassic: NAME: reason" and
    finishes with "unclassic: N of M entries failed"; the whole-archive
    errors it prints instead name the FIXTURE path, and are left in the
    dict deliberately — they must never be excused as per-entry.
    """
    errs, tally = {}, None
    for line in stderr.splitlines():
        t = TALLY.match(line)
        if t:
            tally = (int(t.group(1)), int(t.group(2)))
            continue
        m = ENTRY_ERR.match(line)
        if m:
            errs[normpath(m.group(1))] = m.group(2)
    whole = (tally is not None and tally[0] == tally[1]
             and bool(errs)
             and all(r == "recognized but unsupported" for r in errs.values()))
    return errs, whole


def check_fixture(unclassic, man, verbose, budget=0):
    fx = os.path.join(FIXDIR, man["fixture"])
    cap = ["--budget", str(budget)] if budget else []
    problems, unadjudicated = [], 0
    excused = {normpath(e["name"]) for e in man["entries"]
               if e.get("unadjudicated")}
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([unclassic, "x", "-nr", "--forks", "hidden",
                            "-o", tmp, fx] + cap,
                           capture_output=True, timeout=300)
        un_errs, all_unsupported = parse_entry_errors(
            r.stderr.decode("utf-8", "replace"))
        if all_unsupported:
            # Every entry uses a method outside v1 scope, so there is
            # nothing here a diff could compare — the same situation as
            # a format we do not implement, arrived at per entry instead
            # of per archive. Reported separately, never silently.
            return [], 0, True
        if r.returncode != 0:
            # A per-entry error is excused only where the ORACLE also
            # failed that entry: both sides agree there is nothing to
            # get, and the excuse is anchored to unar's behaviour rather
            # than to ours, so it cannot grow to cover a regression.
            unexplained = {n: e for n, e in un_errs.items()
                           if n not in excused}
            if unexplained or not un_errs:
                problems.append(
                    f"exit {r.returncode}: {r.stderr.decode()[:300]}")
        files, dirs = collect_outputs(tmp)

        lr = subprocess.run([unclassic, "l", fx] + cap,
                            capture_output=True, timeout=60)
        listing = parse_listing(lr.stdout.decode("utf-8", "replace"))

        for e in man["entries"]:
            name = normpath(e["name"])
            if e.get("is_dir"):
                if name not in dirs and name not in files:
                    problems.append(f"missing dir: {name!r}")
                continue
            # Forks the oracle itself failed on carry no hashes: there
            # is no ground truth to compare against, so they are counted
            # and skipped rather than guessed at. The two halves of that
            # record cross-check each other — a missing hash with no
            # reason beside it, or a reason beside a hash, means the
            # manifest is malformed and the fixture fails.
            un = e.get("unadjudicated") or {}
            for fork in ("data", "rsrc"):
                if (fork + "_sha256" in e) == (fork in un):
                    problems.append(
                        f"{name!r}: malformed manifest, {fork} fork is "
                        f"{'both' if fork in un else 'neither'} adjudicated "
                        f"and unadjudicated")
            unadjudicated += len(un)
            path = files.pop(name, None)
            rp = files.pop(sidecar(name), None)
            if len(un) == 2:
                # Nothing to compare, but the entry must still exist: an
                # unadjudicated fork is not a licence to drop it, and a
                # name is the one thing an aggregate check never fails on.
                if path is None and rp is None and name not in listing:
                    problems.append(f"missing entry: {name!r}")
                continue
            # Where BOTH sides failed this entry, our engine may have
            # written nothing at all — but only its absence is excused.
            # Whatever it did write is still compared, so an entry that
            # fails on one fork keeps its other fork under the oracle.
            partial = name in un_errs and name in excused
            if path is None and not partial:
                problems.append(f"missing file: {name!r}")
                continue
            if "data" not in un and not (partial and path is None):
                sz = os.path.getsize(path)
                if sz != e["data_size"]:
                    problems.append(
                        f"{name!r}: data size {sz} != {e['data_size']}")
                elif sha256_file(path) != e["data_sha256"]:
                    problems.append(f"{name!r}: data sha mismatch")
            if "rsrc" not in un and not (partial and rp is None):
                rsz = os.path.getsize(rp) if rp else 0
                if rsz != e["rsrc_size"]:
                    problems.append(
                        f"{name!r}: rsrc size {rsz} != {e['rsrc_size']}")
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
    return problems, unadjudicated, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unclassic", default=os.path.join(ROOT, "build/san/unclassic"))
    ap.add_argument("--all", action="store_true",
                    help="run even not-yet-implemented formats")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--format", help="only fixtures of this lsar format")
    ap.add_argument("--budget", type=int, default=0,
                    help="run under an allocation cap, in bytes: every "
                         "fixture must still come out byte-exact. 678392 is "
                         "what a 1 MB Mac Plus leaves the engine.")
    ap.add_argument("--max-size", type=int, default=0,
                    help="only fixtures at most this many bytes. For build "
                         "variants that are correct but slow, where the point "
                         "is to cover a code path rather than the corpus.")
    args = ap.parse_args()

    mandir = os.path.join(FIXDIR, "manifests")
    manifests = sorted(f for f in os.listdir(mandir)
                       if f.endswith(".json")) if os.path.isdir(mandir) else []

    ran = passed = skipped_fmt = skipped_missing = 0
    unadj_forks = unadj_fixtures = skipped_unsupported = 0
    fails = []
    for mf in manifests:
        with open(os.path.join(mandir, mf)) as f:
            man = json.load(f)
        fxpath = os.path.join(FIXDIR, man["fixture"])
        if not os.path.exists(fxpath):
            skipped_missing += 1
            continue
        fmt = man.get("format")
        if args.format and fmt != args.format:
            continue
        if args.max_size and os.path.getsize(fxpath) > args.max_size:
            continue
        if not args.all and fmt not in IMPLEMENTED:
            skipped_fmt += 1
            continue
        ran += 1
        problems, unadj, unsupported = check_fixture(
            args.unclassic, man, args.verbose, args.budget)
        if unsupported:
            ran -= 1
            skipped_unsupported += 1
            continue
        if unadj:
            unadj_forks += unadj
            unadj_fixtures += 1
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

    cap = f" under a {args.budget} B budget" if args.budget else ""
    cap += f" (fixtures <= {args.max_size} B)" if args.max_size else ""
    print(f"diff{cap}: {passed}/{ran} fixtures ok "
          f"({skipped_fmt} formats pending, {skipped_missing} fixtures absent)")
    # Printed even when zero: this number is the only place a fork that
    # nothing compares shows up, and it must be cheap to notice growing.
    if skipped_unsupported:
        print(f"  {skipped_unsupported} fixture(s) skipped: every entry uses "
              f"a compression method outside v1 scope")
    print(f"  oracle-unadjudicated: {unadj_forks} fork(s) across "
          f"{unadj_fixtures} fixture(s) — the oracle failed on these, so "
          f"no second implementation adjudicates them (TESTING.md)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

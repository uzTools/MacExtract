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
    """Parse `unclassic l` output -> {name: (type, creator) or (None, None)}.

    Every listed entry is recorded, not only those with type/creator: the
    listing is how an entry the engine cannot extract is checked to be
    SEEN at all, and a zip entry has no type/creator to print (the field
    is a bare "/").
    """
    meta = {}
    for line in out.splitlines():
        if not line.startswith("f "):
            continue
        # f <data> <rsrc> <type>/<creator> <name...>
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        tc = parts[3]
        meta[normpath(parts[4])] = ((tc[:4], tc[5:])
                                    if len(tc) == 9 and tc[4] == "/"
                                    else (None, None))
    return meta


ENTRY_ERR = re.compile(r"^unclassic: (.*): (.*)$")
TALLY = re.compile(r"^unclassic: (\d+) of (\d+) entries failed$")


def parse_entry_errors(stderr):
    """Return {normalized entry name: reason}.

    `unclassic` reports a failed entry as "unclassic: NAME: reason"; the
    whole-archive errors it prints instead name the FIXTURE path, and are
    left in the dict deliberately — they must never be excused as
    per-entry.
    """
    errs = {}
    for line in stderr.splitlines():
        if TALLY.match(line):
            continue
        m = ENTRY_ERR.match(line)
        if m:
            errs[normpath(m.group(1))] = m.group(2)
    return errs


UNSUPPORTED = "recognized but unsupported"

# Compression methods v1 does not implement, NAMED AS THE ORACLE NAMES
# THEM (`XADCompressionName`, recorded per entry in the manifest). An
# entry our engine declines with "recognized but unsupported" is excused
# only if the oracle says its method is one of these — so the excuse is
# anchored to lsar, and a regression that made a SUPPORTED method report
# "unsupported" cannot buy itself an excuse. FORMATS.md is the scope.
#
# Deliberately only the methods the corpus actually contains: a method
# named here that lsar spells differently would excuse nothing, silently,
# whereas an unlisted one fails the suite loudly and gets added. Zip
# reduce/shrink and tar links belong here the day a fixture has one.
ORACLE_OUT_OF_SCOPE = {"Implode"}


def out_of_scope(entry):
    """True when the ORACLE says every method of this entry is outside v1
    scope. An entry with no recorded method is never out of scope: an
    absent field must not become an excuse."""
    m = entry.get("oracle_methods")
    return bool(m) and all(x in ORACLE_OUT_OF_SCOPE for x in m)


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
        un_errs = parse_entry_errors(r.stderr.decode("utf-8", "replace"))
        # An entry may produce nothing for exactly two reasons, both of
        # them the ORACLE's word rather than ours: it failed that entry
        # too, or it names the entry's compression method as one v1 does
        # not implement. Never because our binary said "unsupported" —
        # that would let a regression in the method dispatch grade itself.
        outofscope = {normpath(e["name"]) for e in man["entries"]
                      if out_of_scope(e)}
        if r.returncode != 0:
            unexplained = {n: er for n, er in un_errs.items()
                           if n not in excused
                           and not (er == UNSUPPORTED and n in outofscope)}
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
            # A fork WITH ground truth is compared, or it is missing.
            # Absence is excused only for an entry whose method the oracle
            # puts outside v1 scope — not merely because the oracle failed
            # the entry's OTHER fork, which used to excuse the whole entry
            # and made 6 fixtures' adjudicated forks unfailable.
            absent_ok = name in un_errs and name in outofscope
            if path is None and not absent_ok:
                problems.append(f"missing file: {name!r}")
                continue
            if absent_ok and path is None and rp is None:
                # Out of scope and nothing written: the name is still
                # ground truth and is the only thing left to check.
                if name not in listing:
                    problems.append(f"missing entry: {name!r}")
                continue
            if "data" not in un:
                sz = os.path.getsize(path) if path else 0
                if sz != e["data_size"]:
                    problems.append(
                        f"{name!r}: data size {sz} != {e['data_size']}")
                elif path and sha256_file(path) != e["data_sha256"]:
                    problems.append(f"{name!r}: data sha mismatch")
            if "rsrc" not in un:
                rsz = os.path.getsize(rp) if rp else 0
                if rsz != e["rsrc_size"]:
                    problems.append(
                        f"{name!r}: rsrc size {rsz} != {e['rsrc_size']}")
                elif rp and sha256_file(rp) != e["rsrc_sha256"]:
                    problems.append(f"{name!r}: rsrc sha mismatch")
            if "type" in e and listing.get(name, (None, None))[0]:
                t, c = listing[name]
                if t != e["type"] or (e.get("creator") and c != e["creator"]):
                    problems.append(
                        f"{name!r}: type/creator {t}/{c} != "
                        f"{e['type']}/{e.get('creator')}")
        for leftover in files:
            problems.append(f"unexpected output: {leftover!r}")
    return problems, unadjudicated


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
    unadj_forks = unadj_fixtures = oos_entries = 0
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
        problems, unadj = check_fixture(
            args.unclassic, man, args.verbose, args.budget)
        oos_entries += sum(1 for e in man["entries"] if out_of_scope(e))
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
    # No fixture is ever skipped for what OUR engine says about it; an
    # entry the oracle names as out of v1 scope is graded on its name and
    # on anything the engine did produce, and counted here.
    if oos_entries:
        print(f"  {oos_entries} entr(y/ies) the oracle names as compressed "
              f"with a method outside v1 scope: graded on name only")
    print(f"  oracle-unadjudicated: {unadj_forks} fork(s) across "
          f"{unadj_fixtures} fixture(s) — the oracle failed on these, so "
          f"no second implementation adjudicates them (TESTING.md)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

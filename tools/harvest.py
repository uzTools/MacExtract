#!/usr/bin/env python3
"""harvest.py — corpus harvester.

Fixture archives are copyrighted software and never committed; only
fixtures/SOURCES.md (URL + SHA-256 per file) is. Modes:

  harvest.py --probe URL [--name NAME]
      Download a candidate, verify the oracle (lsar) can read it,
      then register it: save under fixtures/, append to SOURCES.md.
      Rejects files > --max-size (default 512 KB) or unreadable ones.

  harvest.py --derive
      For each fixture that is an envelope (BinHex/MacBinary), extract
      the payload with the oracle (`unar -nr`) and, if the payload is
      itself an oracle-readable archive, register it as a derived
      fixture. Recorded in SOURCES.md as url `derived:unar-nr:<parent>`
      so --restore can reproduce it after downloading the parents.

  harvest.py --restore
      Re-download everything listed in SOURCES.md and verify hashes
      (derived fixtures are re-derived).

SOURCES.md line format (one per fixture):
  | name | sha256 | size | url |
"""
import argparse, hashlib, os, re, shutil, subprocess, sys, tempfile
import urllib.request, urllib.parse

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIXDIR = os.path.join(ROOT, "fixtures")
SOURCES = os.path.join(FIXDIR, "SOURCES.md")
HEADER = ("# Fixture corpus provenance\n\n"
          "Fixtures are not committed (copyrighted historical software).\n"
          "Each line records how to re-fetch one. Use "
          "`tools/harvest.py --restore`.\n\n"
          "| name | sha256 | size | url |\n|---|---|---|---|\n")


def sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "unclassic-harvest/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def oracle_ok(path):
    """Accept a candidate only if lsar parses it to >=1 entry."""
    try:
        r = subprocess.run(["lsar", "-nr", "-e", "macintosh", path],
                           capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        return False, "lsar timeout"
    if r.returncode != 0:
        return False, "lsar exit %d" % r.returncode
    lines = [l for l in r.stdout.decode("utf-8", "replace").splitlines()[1:]
             if l.strip()]
    if not lines:
        return False, "lsar found no entries"
    return True, "%d entries" % len(lines)


def load_sources():
    rows = {}
    if os.path.exists(SOURCES):
        for line in open(SOURCES):
            m = re.match(r"\| *([^|]+?) *\| *([0-9a-f]{64}) *\| *(\d+) *\| *([^|]+?) *\|",
                         line)
            if m:
                rows[m.group(1)] = (m.group(2), int(m.group(3)), m.group(4))
    return rows


def save_sources(rows):
    with open(SOURCES, "w") as f:
        f.write(HEADER)
        for name in sorted(rows):
            sha, size, url = rows[name]
            f.write(f"| {name} | {sha} | {size} | {url} |\n")


def probe(url, name, max_size):
    os.makedirs(FIXDIR, exist_ok=True)
    if not name:
        name = os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(url).path))
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    rows = load_sources()
    if name in rows:
        print(f"  skip (already registered): {name}")
        return True
    try:
        blob = fetch(url)
    except Exception as e:
        print(f"  fetch failed: {name}: {e}")
        return False
    if len(blob) == 0 or len(blob) > max_size:
        print(f"  rejected (size {len(blob)}): {name}")
        return False
    path = os.path.join(FIXDIR, name)
    with open(path, "wb") as f:
        f.write(blob)
    ok, why = oracle_ok(path)
    if not ok:
        os.unlink(path)
        print(f"  rejected ({why}): {name}")
        return False
    rows[name] = (sha256_bytes(blob), len(blob), url)
    save_sources(rows)
    print(f"  accepted: {name} ({len(blob)} bytes, {why})")
    return True


def derive_one(parent_path, rows, max_size):
    """Extract the payload of an envelope fixture; if it is an archive
    the oracle can read, save it as a derived fixture. Returns the new
    fixture name or None."""
    parent = os.path.basename(parent_path)
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(["unar", "-nr", "-D", "-f", "-q", "-k", "skip",
                           "-e", "macintosh", "-o", tmp, parent_path],
                          capture_output=True, timeout=120)
        if r.returncode != 0:
            return None
        produced = []
        for root, _, files in os.walk(tmp):
            for f in files:
                produced.append(os.path.join(root, f))
        if len(produced) != 1:
            return None      # not a single-payload envelope
        inner = produced[0]
        if os.path.getsize(inner) == 0 or os.path.getsize(inner) > max_size:
            return None
        ok, why = oracle_ok(inner)
        if not ok:
            return None
        base = os.path.basename(inner)
        stem = re.sub(r"[^A-Za-z0-9._-]", "_", base)
        name = "derived-" + stem
        if name in rows:
            return None
        dest = os.path.join(FIXDIR, name)
        shutil.copy(inner, dest)
        with open(dest, "rb") as f:
            blob = f.read()
        rows[name] = (sha256_bytes(blob), len(blob), f"derived:unar-nr:{parent}")
        print(f"  derived: {name} ({len(blob)} bytes, {why}) from {parent}")
        return name


def derive(max_size):
    rows = load_sources()
    parents = [n for n, (_, _, url) in rows.items() if not url.startswith("derived:")]
    n = 0
    for name in sorted(parents):
        path = os.path.join(FIXDIR, name)
        if not os.path.exists(path):
            continue
        if derive_one(path, rows, max_size):
            n += 1
    save_sources(rows)
    print(f"derive: {n} new derived fixtures")
    return True


def restore():
    rows = load_sources()
    ok = bad = kept = 0
    deferred = []
    for name, (sha, size, url) in sorted(rows.items()):
        path = os.path.join(FIXDIR, name)
        if os.path.exists(path) and sha256_bytes(open(path, "rb").read()) == sha:
            kept += 1
            continue
        if url.startswith("derived:"):
            deferred.append((name, sha, url))
            continue
        try:
            blob = fetch(url)
        except Exception as e:
            print(f"  fetch failed: {name}: {e}")
            bad += 1
            continue
        if sha256_bytes(blob) != sha:
            print(f"  HASH MISMATCH: {name} (source changed?)")
            bad += 1
            continue
        with open(path, "wb") as f:
            f.write(blob)
        ok += 1
    # Re-derive derived fixtures now that parents are present.
    for name, sha, url in deferred:
        parent = url.split(":", 2)[2]
        tmprows = dict(rows)
        tmprows.pop(name, None)
        got = derive_one(os.path.join(FIXDIR, parent), tmprows, 1 << 30)
        path = os.path.join(FIXDIR, name)
        gotpath = got and os.path.join(FIXDIR, got)
        if got and got != name:
            os.rename(gotpath, path)
        if os.path.exists(path) and sha256_bytes(open(path, "rb").read()) == sha:
            ok += 1
        else:
            print(f"  derive failed or hash mismatch: {name}")
            bad += 1
    print(f"restore: {ok} fetched, {kept} already present, {bad} failed")
    return bad == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", metavar="URL")
    ap.add_argument("--name")
    ap.add_argument("--max-size", type=int, default=512 * 1024)
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--derive", action="store_true")
    args = ap.parse_args()
    if args.restore:
        return 0 if restore() else 1
    if args.derive:
        return 0 if derive(args.max_size) else 1
    if args.probe:
        return 0 if probe(args.probe, args.name, args.max_size) else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

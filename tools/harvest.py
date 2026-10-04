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
    req = urllib.request.Request(url, headers={"User-Agent": "macextract-harvest/1.0"})
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


def preamble():
    """Everything SOURCES.md says above its table, kept verbatim.

    The file is rewritten whole on every registration, and until
    2026-10-04 that threw away the prose: HEADER was written back and
    the twelve lines of explanation after it were not, so one --probe
    deleted the paragraph saying which fixtures are not archives and
    must not have manifests. Nothing reads the file, so nothing failed;
    `git diff` saying "1 insertion, 13 deletions" is what caught it.
    Falls back to HEADER for a fresh clone.
    """
    marker = "| name | sha256 | size | url |"
    if os.path.exists(SOURCES):
        text = open(SOURCES, encoding="utf-8").read()
        if marker in text:
            return text[:text.index(marker)] + marker + "\n|---|---|---|---|\n"
    return HEADER


def save_sources(rows):
    head = preamble()
    with open(SOURCES, "w", encoding="utf-8") as f:
        f.write(head)
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
        if url.startswith("synthetic:"):
            # url form: synthetic:<script> <args...>; the script must
            # accept -o <path> and be deterministic.
            cmd = url.split(":", 1)[1].split()
            r = subprocess.run(
                [sys.executable, os.path.join(ROOT, cmd[0])] + cmd[1:] +
                ["-o", path], capture_output=True)
            if (r.returncode == 0 and os.path.exists(path)
                    and sha256_bytes(open(path, "rb").read()) == sha):
                ok += 1
            else:
                print(f"  synth failed or hash mismatch: {name}")
                bad += 1
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
        # `derived:member:<parent>:<member>` names ONE file out of an
        # envelope holding several, which `derive_one` refuses by
        # design (it cannot tell which payload a caller meant). The
        # PAK specimen that grades ARC method 0x0b travels inside a
        # four-file zip and is reachable no other way.
        # `derived:arcplus:<parent>:<member>` carves a DOS
        # self-extractor's payload out of a zipped distribution and
        # takes one STORED member of it — structurally, with no
        # decoder involved, so a fixture that grades a decoder is not
        # produced by one (tools/arcplus.py --carve).
        if url.startswith("derived:arcplus:"):
            _, _, parent, member = url.split(":", 3)
            path = os.path.join(FIXDIR, name)
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run(["unzip", "-o", "-q",
                                os.path.join(FIXDIR, parent), "-d", tmp],
                               capture_output=True, timeout=300)
                sfx = None
                for root, _, files in os.walk(tmp):
                    for f in files:
                        if f.upper().endswith(".EXE"):
                            sfx = os.path.join(root, f)
                if sfx:
                    subprocess.run([sys.executable,
                                    os.path.join(ROOT, "tools", "arcplus.py"),
                                    "--carve", sfx, "--member", member,
                                    "-o", path], capture_output=True, timeout=300)
            if os.path.exists(path) and sha256_bytes(open(path, "rb").read()) == sha:
                ok += 1
            else:
                print(f"  carve failed or hash mismatch: {name}")
                bad += 1
            continue
        # `derived:hfsvol:<image>:<mode>:<HFS path>` lifts ONE file out
        # of an emulator disk image with hfsutils; <mode> is hcopy's
        # letter, `r` for the data fork alone and `m` for MacBinary.
        # A DiskDoubler file wants `r`: its payload is in its own DATA
        # fork, and MacBinary-wrapping it makes `unar` stop at the
        # wrapper and report the DD01 file rather than expanding it, so
        # the manifest would describe the container and never the
        # contents. `<image>` is relative to the vmac cache
        # ($UNC_VMAC_HOME), because a distribution disk is emulator
        # material and lives under the same rule as the ROM and the
        # System images: fetched by tools/vmac/setup.sh, never
        # committed. Absent, the fixture simply cannot be restored,
        # which is the position every fixture is in on a fresh clone.
        if url.startswith("derived:hfsvol:"):
            _, _, image, mode, hfspath = url.split(":", 4)
            mode = "-" + (mode or "m")
            # An HFS path is absolute when it LEADS with the separator,
            # and the field splitting above has just eaten that colon.
            if not hfspath.startswith(":"):
                hfspath = ":" + hfspath
            vmac = os.environ.get("UNC_VMAC_HOME",
                                  os.path.expanduser(
                                      "~/.cache/macextract/vmac"))
            img = os.path.join(vmac, image)
            path = os.path.join(FIXDIR, name)
            if not os.path.exists(img):
                print(f"  no disk image for {name}: {img} "
                      f"(tools/vmac/setup.sh fetches it)")
                bad += 1
                continue
            r = subprocess.run(["hmount", img], capture_output=True,
                               timeout=120)
            if r.returncode == 0:
                # SOURCES.md holds the path as readable Unicode; the
                # volume holds MacRoman, so "Sample IAC \u0192" has to go
                # back to the 0xC4 byte hfsutils will match. Bytes are a
                # legal argv entry on POSIX.
                subprocess.run([b"hcopy", mode.encode(),
                                hfspath.encode("mac-roman"),
                                path.encode()],
                               capture_output=True, timeout=120)
            if os.path.exists(path) and \
                    sha256_bytes(open(path, "rb").read()) == sha:
                ok += 1
            else:
                print(f"  hfsvol extract failed or hash mismatch: {name}")
                bad += 1
            continue
        if url.startswith("derived:member:"):
            _, _, parent, member = url.split(":", 3)
            path = os.path.join(FIXDIR, name)
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run(["unar", "-nr", "-D", "-f", "-q", "-k", "skip",
                                "-o", tmp, os.path.join(FIXDIR, parent)],
                               capture_output=True, timeout=300)
                found = None
                for root, _, files in os.walk(tmp):
                    for f in files:
                        if f == member:
                            found = os.path.join(root, f)
                if found:
                    shutil.copy(found, path)
            if os.path.exists(path) and sha256_bytes(open(path, "rb").read()) == sha:
                ok += 1
            else:
                print(f"  member extract failed or hash mismatch: {name}")
                bad += 1
            continue
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

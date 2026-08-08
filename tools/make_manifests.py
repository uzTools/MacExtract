#!/usr/bin/env python3
"""make_manifests.py — build oracle manifests for every fixture.

For each file in fixtures/ (non-recursive, excluding manifests/ etc.),
run the oracle (unar, The Unarchiver's CLI) and record per entry:

  - data-fork SHA-256 + size
  - resource-fork SHA-256 + size (parsed out of the AppleDouble "._"
    files that `unar -k hidden` produces)
  - Mac type/creator codes when the oracle exposes them (from the
    AppleDouble Finder-info entry, falling back to `lsar -j`)

Manifests land in fixtures/manifests/<fixture>.json and are committed;
the fixtures themselves are not. See TESTING.md for the exact procedure.

Forks are taken from `-k hidden` ("._NAME") rather than `-k visible`
("NAME.rsrc") because the suffix convention is ambiguous whenever an
archive holds both "X" and "X.rsrc" — a THINK C project is exactly that
shape — while the prefix namespace is disjoint from real archive names.
The manifest itself records neither convention: entry name plus per-fork
hashes. DECISIONS.md, 2026-08-08.

When the oracle fails on individual ENTRIES but still walks the
container, the manifest is built from what it did produce and the forks
it failed on are recorded per entry as "unadjudicated" (fork -> the
oracle's own error text) with their hashes omitted. Nothing else is
lost: an archive where unar dies on one fork used to yield no manifest
at all, discarding every other fork it adjudicated perfectly well.
Discovery is by condition, never by fixture name. DECISIONS.md,
2026-08-08.

Oracle invocation (see TESTING.md for rationale):
    lsar -j -nr -e macintosh <fixture>          # format + metadata
    unar -nr -D -f -q -k hidden -e macintosh -o <tmp> <fixture>
"""
import argparse, hashlib, json, os, plistlib, re, struct, subprocess, sys
import tempfile, unicodedata

FIXDIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_appledouble(path):
    """Return (rsrc_bytes, type4cc, creator4cc) from an AppleDouble file.

    AppleDouble layout (per RFC 1740 / the files unar emits):
      u32 magic 0x00051607, u32 version, 16 bytes filler, u16 nentries,
      then nentries * (u32 id, u32 offset, u32 length).
      id 2 = resource fork, id 9 = Finder info (type + creator + flags).
    """
    with open(path, "rb") as f:
        blob = f.read()
    if len(blob) < 26 or struct.unpack(">I", blob[:4])[0] != 0x00051607:
        return None, None, None
    nent = struct.unpack(">H", blob[24:26])[0]
    rsrc, typ, creator = b"", None, None
    for i in range(nent):
        off = 26 + 12 * i
        if off + 12 > len(blob):
            break
        eid, eoff, elen = struct.unpack(">III", blob[off:off + 12])
        if eoff + elen > len(blob):
            continue
        if eid == 2:
            rsrc = blob[eoff:eoff + elen]
        elif eid == 9 and elen >= 8:
            typ = blob[eoff:eoff + 4].decode("mac_roman")
            creator = blob[eoff + 4:eoff + 8].decode("mac_roman")
    return rsrc, typ, creator


def norm(name):
    return unicodedata.normalize("NFC", name)


def matchkey(name):
    """Key for matching the oracle's own report against extracted paths.

    A classic Mac name may contain '/', which unar writes as '_' on
    disk while its progress report still prints it — so "F/G" on disk
    is ambiguous between a folder and a name. Flattening both
    separators to '_' removes the ambiguity for MATCHING only; manifest
    entry names are recorded exactly as walked.
    """
    return norm(name).replace(":", "_").replace("/", "_")


# `unar` has no machine-readable extraction report, so per-entry
# failures are read off its progress output. Both templates are literal
# strings in the reference tree: unar.m builds "  " + info line +
# "... Failed! (" + reason + ")" and the trailer at unar.m:307, and
# CommandLineCommon.m::MediumInfoLineForEntryWithDictionary joins the
# tags as "  (" + ", " + ")".
#
# The tag list can also carry "dir", "link" and "corrupted", which this
# pattern deliberately does NOT match: an unmatched failure line makes
# the parsed count disagree with the trailer, which refuses the whole
# manifest. Failing safe beats guessing at a shape never seen here.
# /* Source: reference/XADMaster/unar.m, CommandLineCommon.m */
FAIL_RE = re.compile(r"^  (.*)  \((\d+) B(, rsrc)?\)\.\.\. Failed! \((.*)\)$")
TRAILER_RE = re.compile(
    r"^Extraction to directory .* failed \((\d+) files? failed\.\)$")


def parse_oracle_failures(text):
    """Return (failures, trailer_count) from unar's output.

    failures: [(name, "data"|"rsrc", error text)]; trailer_count is the
    total unar itself reports, or None if it never said.
    """
    failures, trailer = [], None
    for line in text.splitlines():
        m = FAIL_RE.match(line)
        if m:
            failures.append((m.group(1), "rsrc" if m.group(3) else "data",
                             m.group(4)))
            continue
        t = TRAILER_RE.match(line)
        if t:
            trailer = int(t.group(1))
    return failures, trailer


def lsar_metadata(fixture):
    """Return (formatname, {normalized name: (type, creator)}) via lsar -j."""
    try:
        out = subprocess.run(
            ["lsar", "-j", "-nr", "-e", "macintosh", fixture],
            capture_output=True, timeout=60)
        # strict=False: lsar's JSON may contain raw control characters
        # (e.g. binary XADNextSolidEntry keys in PackIt archives).
        data = json.loads(out.stdout.decode("utf-8", "replace"), strict=False)
    except Exception:
        return None, {}
    fmt = data.get("lsarFormatName")
    meta = {}
    for e in data.get("lsarContents", []):
        name = norm(e.get("XADFileName", ""))
        t, c = e.get("XADFileType"), e.get("XADFileCreator")
        to4 = lambda v: struct.pack(">I", v).decode("mac_roman") if v else None
        meta[name] = (to4(t), to4(c))
    return fmt, meta


def build_manifest(fixture_path, verbose=False):
    name = os.path.basename(fixture_path)
    fmt, meta = lsar_metadata(fixture_path)
    # The "._" sidecar namespace is disjoint from real archive names in
    # every fixture harvested so far, which is why forks are taken from
    # `-k hidden` — but an entry literally named "._X" would collide
    # with the sidecar of "X", the one shape this convention cannot
    # represent. Refuse rather than guess; the fixture stays in the
    # corpus for robustness testing.
    for n in meta:
        if os.path.basename(n).startswith("._"):
            print(f"  oracle UNDECIDABLE on {name} "
                  f"(AppleDouble prefix collision: {n!r}), skipping",
                  file=sys.stderr)
            return None
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(
            ["unar", "-nr", "-D", "-f", "-q", "-k", "hidden",
             "-e", "macintosh", "-o", tmp, fixture_path],
            capture_output=True, timeout=300)
        # A non-zero exit is per-ENTRY failure or container failure, and
        # the difference is worth the whole manifest. Accept it as
        # per-entry only when unar's own report accounts for it exactly:
        # the parsed failures must match the total it prints, and every
        # name it names must be an entry lsar also lists. Otherwise the
        # output is not modelled and is not ground truth.
        failures, failed_names = {}, {}
        if r.returncode != 0:
            parsed, trailer = parse_oracle_failures(
                (r.stdout + r.stderr).decode("utf-8", "replace"))
            if not parsed or trailer is None or len(parsed) != trailer:
                print(f"  oracle FAILED on {name}: {r.stderr.decode()[:200]}",
                      file=sys.stderr)
                return None
            known = {matchkey(n) for n in meta}
            for ename, fork, err in parsed:
                if matchkey(ename) not in known:
                    print(f"  oracle UNRELIABLE on {name} (reports a failure "
                          f"for {ename!r}, which it does not list)",
                          file=sys.stderr)
                    return None
                failures.setdefault(matchkey(ename), {})[fork] = err
                failed_names[matchkey(ename)] = norm(ename)
            print(f"  oracle PARTIAL on {name}: "
                  f"{len(parsed)} fork(s) unadjudicated", file=sys.stderr)
        # GNUstep's fork-path bug is a `-k visible` bug: it comes from
        # appending ".rsrc" to a name its path code rejects (leading
        # '~'), and it can write the AppleDouble container into the
        # data-fork filename. Prefixing never calls that code, so this
        # warning should not appear here at all — if it does, something
        # is unmodelled and the output is not ground truth.
        if b"cannot append extension" in r.stderr:
            print(f"  oracle UNRELIABLE on {name} (fork path bug), skipping",
                  file=sys.stderr)
            return None
        entries = []
        for root, dirs, files in os.walk(tmp):
            dirs.sort()          # os.walk order is otherwise the
            rel = os.path.relpath(root, tmp)   # filesystem's, not ours
            fs = set(files)
            for d in sorted(dirs):
                p = norm(os.path.normpath(os.path.join(rel, d)))
                entries.append({"name": p, "is_dir": True})
            # One entry per name, whether it arrived as a data-fork
            # file, a "._" sidecar, or both. A sidecar with no data
            # file beside it is a real entry whose data fork is empty:
            # unar writes nothing for a 0-byte data fork (resource-only
            # entries, e.g. PackIt members and FKEY/cdev files).
            for base in sorted({f[2:] if f.startswith("._") else f
                                for f in fs}):
                p = norm(os.path.normpath(os.path.join(rel, base)))
                ent = {
                    "name": p,
                    "data_size": 0,
                    "data_sha256": hashlib.sha256(b"").hexdigest(),
                    "rsrc_size": 0,
                    "rsrc_sha256": hashlib.sha256(b"").hexdigest(),
                }
                if base in fs:
                    full = os.path.join(root, base)
                    ent["data_size"] = os.path.getsize(full)
                    ent["data_sha256"] = sha256_file(full)
                ad = os.path.join(root, "._" + base)
                if os.path.exists(ad):
                    rsrc, typ, creator = parse_appledouble(ad)
                    # Every "._" file unar writes is an AppleDouble
                    # container; one that is not means the oracle put
                    # something else there, which is not ground truth.
                    if rsrc is None:
                        print(f"  oracle UNRELIABLE on {name} "
                              f"(sidecar is not AppleDouble: {p!r})",
                              file=sys.stderr)
                        return None
                    ent["rsrc_size"] = len(rsrc)
                    ent["rsrc_sha256"] = hashlib.sha256(rsrc).hexdigest()
                    if typ:
                        ent["type"] = typ
                    if creator:
                        ent["creator"] = creator
                if "type" not in ent and p in meta and meta[p][0]:
                    ent["type"], ent["creator"] = meta[p][0], meta[p][1]
                # A fork the oracle failed on is not ground truth,
                # whatever it left on disk — and what it leaves varies:
                # a 0-byte file, a partial one (114,644 B of a failed
                # data fork in guysmaccontacts.sea), or a sidecar padded
                # to the DECLARED length (appledraw51.cpt). Record the
                # oracle's reason and drop the hashes.
                un = failures.pop(matchkey(p), None)
                if un:
                    # "no data-fork file means a 0-byte data fork" holds
                    # only for entries the oracle COMPLETED. On one it
                    # failed, absent output means it never got there, so
                    # the other fork is unadjudicated too rather than
                    # empty (derived-INITLoader.sit: sidecar written,
                    # data fork never attempted).
                    if base not in fs:
                        un.setdefault("data", "oracle wrote no output for "
                                              "this fork")
                    if not os.path.exists(ad):
                        un.setdefault("rsrc", "oracle wrote no output for "
                                              "this fork")
                    ent["unadjudicated"] = un
                    for fork in un:
                        ent.pop(fork + "_size", None)
                        ent.pop(fork + "_sha256", None)
                entries.append(ent)
        # An entry the oracle failed on before writing anything at all
        # is still an entry, and its NAME is still ground truth: record
        # it with both forks unadjudicated so the runner keeps checking
        # that we produce it, rather than silently tolerating one more
        # output file.
        for key, un in failures.items():
            full = dict(un)
            for fork in ("data", "rsrc"):
                full.setdefault(fork, "oracle wrote no output for this entry")
            entries.append({"name": failed_names[key], "unadjudicated": full})
    if not entries:
        print(f"  oracle produced nothing for {name}", file=sys.stderr)
        return None
    # Canonical order, so a rebuild on another machine produces the same
    # file. Every consumer looks entries up by name; none depends on the
    # order they were walked in.
    entries.sort(key=lambda e: e["name"])
    return {
        "fixture": name,
        "sha256": sha256_file(fixture_path),
        "size": os.path.getsize(fixture_path),
        "format": fmt,
        "oracle": "unar -nr -D -f -q -k hidden -e macintosh (v1.10.8)",
        "entries": entries,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="specific fixtures (default: all)")
    ap.add_argument("--force", action="store_true", help="rebuild existing")
    args = ap.parse_args()

    mandir = os.path.join(FIXDIR, "manifests")
    os.makedirs(mandir, exist_ok=True)

    if args.files:
        fixtures = args.files
    else:
        fixtures = [os.path.join(FIXDIR, f) for f in sorted(os.listdir(FIXDIR))
                    if os.path.isfile(os.path.join(FIXDIR, f))
                    and f not in ("SOURCES.md",)]

    made = skipped = failed = 0
    for fx in fixtures:
        out = os.path.join(mandir, os.path.basename(fx) + ".json")
        if os.path.exists(out) and not args.force:
            skipped += 1
            continue
        m = build_manifest(fx)
        if m is None:
            failed += 1
            # A stale manifest for an oracle-unreliable fixture is
            # worse than none: drop it.
            if os.path.exists(out):
                os.unlink(out)
                print(f"  removed stale manifest for {os.path.basename(fx)}",
                      file=sys.stderr)
            continue
        with open(out, "w") as f:
            json.dump(m, f, indent=1, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        made += 1
        print(f"  manifest: {os.path.basename(fx)} "
              f"({m['format']}, {len(m['entries'])} entries)")
    print(f"manifests: {made} built, {skipped} kept, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

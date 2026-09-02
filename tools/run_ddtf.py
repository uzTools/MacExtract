#!/usr/bin/env python3
"""run_ddtf.py — DiskDoubler graded against the bytes that went in.

`ssokolow/diskdoubler-test-files` (CC0) is nine sets of the same seven
small files, compressed on a real Power Mac G4 by DiskDoubler 3.7.7 and
DiskDoubler Pro 4.1.1 in every method their menus offer, published
BESIDE the originals. That is what makes it the only DiskDoubler
grading here that does not go through another decoder: the oracle is
the source file, not `unar`'s opinion of the archive.

    tools/run_ddtf.py --fetch                 # clone to /tmp, then check
    tools/run_ddtf.py --corpus /path/to/clone
    tools/run_ddtf.py --fetch --register      # and put it in fixtures/

It checks four things and fails on any mismatch:

  * 63 single-file `0xABCD0054` containers  (7 files x 9 methods)
  * 9 `DDAR` / `DDA2` archives, and the same 9 BinHexed
  * 10 self-extractors, and the same 10 BinHexed
  * every extracted fork against the published original, byte for byte

`--register` copies all 101 of those into `fixtures/`, writes a row per
file in `fixtures/SOURCES.md` (a raw URL pinned to the corpus commit, so
a later force-push cannot change what is fetched) and a manifest per
file built from the published originals rather than from a decoder. That
is what puts this corpus in `ci.sh`, where `run_diff.py` grades it like
any other fixture. It also registers the six `SPLT` parts, which
`run_segments.py` joins as sets.

Nothing in a manifest is our own output. The forks are the published
originals; `testfile.TIF` has none, so its two forks are `unar`'s decode
of the four DiskDoubler 3.7.7 archives, which agree; the entry NAMES are
the ones `lsar` reads out of the 63 single-file containers, which carry
them (so every method contributes its own); the "sources/" folder the
DiskDoubler Pro archives put them under is `lsar`'s too, from the four
entries it manages before giving up; and type/creator are recorded only
where `lsar` reads them off that very fixture.

`testfile.TIF` has no published original — it was made on the Mac — so
it is checked for agreement across all nine independent compressions
instead, forks included.

What it CANNOT see: dates, type/creator and Finder flags (the corpus
publishes the forks, and its AppleDouble sidecars carry a Finder info
block the Mac rewrote on copy); the five methods no shipping
DiskDoubler menu offers; and the six `SPLT` parts, which the engine
does read — they are three SETS rather than six files, and this script
grades file by file (tools/run_segments.py has the sets).
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://github.com/ssokolow/diskdoubler-test-files.git"

# The seven files in every set. testfile.TIF is the one with no original.
NAMES = ["Test Image", "Test Text", "testfile.PICT", "testfile.TIF",
         "testfile.jpg", "testfile.png", "testfile.txt"]
NO_ORIGINAL = "testfile.TIF"


def ad_rsrc(path):
    """The resource fork out of an AppleDouble sidecar."""
    with open(path, "rb") as fh:
        d = fh.read()
    if len(d) < 26 or struct.unpack_from(">I", d, 0)[0] != 0x00051607:
        raise ValueError("%s is not AppleDouble" % path)
    n = struct.unpack_from(">H", d, 24)[0]
    for i in range(n):
        eid, off, ln = struct.unpack_from(">III", d, 26 + i * 12)
        if eid == 2:
            return d[off:off + ln]
    return b""


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


class Check(object):
    def __init__(self):
        self.ok = 0
        self.bad = []

    def eq(self, what, got, want):
        if got == want:
            self.ok += 1
        else:
            self.bad.append("%s: %d bytes, expected %d"
                            % (what, len(got), len(want)))


def extract(cli, archive, out):
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([cli, "x", "--forks", "hidden", "-o", out, archive],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.returncode, r.stderr.decode("utf-8", "replace").strip()


def find_root(top):
    """Descend through single-directory levels to where the files are."""
    root = top
    for _ in range(4):
        ents = os.listdir(root)
        if len(ents) == 1 and os.path.isdir(os.path.join(root, ents[0])):
            root = os.path.join(root, ents[0])
        else:
            return root
    return root


def check_set(chk, root, srcdir, label, tif):
    """Compare an extracted set of the seven files with the originals."""
    for name in NAMES:
        got = os.path.join(root, name)
        if not os.path.exists(got):
            chk.bad.append("%s: %s missing" % (label, name))
            continue
        rsrc = os.path.join(root, "._" + name)
        gotr = read(rsrc) if os.path.exists(rsrc) else b""
        if name == NO_ORIGINAL:
            tif.setdefault("data", set()).add(hashlib.sha256(read(got)).hexdigest())
            tif.setdefault("rsrc", set()).add(hashlib.sha256(gotr).hexdigest())
            continue
        chk.eq("%s: %s" % (label, name), read(got), read(os.path.join(srcdir, name)))
        orig = os.path.join(srcdir, "._" + name)
        chk.eq("%s: %s rsrc" % (label, name), gotr,
               ad_rsrc(orig) if os.path.exists(orig) else b"")


# ------------------------------------------------------------------
# Putting the corpus in fixtures/
# ------------------------------------------------------------------

RAW = "https://raw.githubusercontent.com/ssokolow/diskdoubler-test-files/%s/%s"
FIXDIR = os.path.join(REPO, "fixtures")
MANDIR = os.path.join(FIXDIR, "manifests")


def flat(variant):
    """"sources.dd377.ad" -> "dd377ad": a fixture name is flat, and the
    dots in it would be read as extensions by the name rule below."""
    return variant.replace("sources.", "", 1).replace(".", "")


def fixture_name(rel):
    """corpus-relative path -> the name this file takes in fixtures/.

    The single-file container carries NO name, so the CLI takes the
    host's minus its last extension — which is why these names are
    built to survive that rule rather than to look like the corpus's.
    """
    parts = rel.split("/")
    if len(parts) == 3:                       # build/<variant>/<file>
        return "ddtf-%s-%s" % (flat(parts[1]), parts[2].replace(" ", "_"))
    bits = parts[1].split(".")                # build/sources.<variant>.<tail>
    variant, tail = ".".join(bits[:3]), bits[3:]
    if tail and tail[0] == "prompt":
        return "ddtf-%s-prompt.%s" % (flat(variant), ".".join(tail[1:]))
    return "ddtf-%s.%s" % (flat(variant), ".".join(tail))


def lsar_meta(path):
    """{entry basename: (type, creator)} for what `lsar` reads off THIS
    file. Empty where it reads nothing: the manifest then records no
    type for that entry rather than borrowing one from elsewhere."""
    r = subprocess.run(["lsar", "-j", path], capture_output=True)
    out = {}
    try:
        doc = json.loads(r.stdout.decode("utf-8", "replace"))
    except ValueError:
        return out
    for e in doc.get("lsarContents", []):
        name = e.get("XADFileName")
        t, c = e.get("XADFileType"), e.get("XADFileCreator")
        if not name or not isinstance(t, int) or not isinstance(c, int):
            continue
        fcc = lambda v: struct.pack(">I", v & 0xFFFFFFFF).decode("mac-roman")
        out[os.path.basename(name)] = (fcc(t), fcc(c))
    return out


def lsar_prefix(path):
    """The folder the entries sit in, as `lsar` reports it — "" for the
    DiskDoubler 3.7.7 archives, "sources/" for DiskDoubler Pro's."""
    r = subprocess.run(["lsar", "-j", path], capture_output=True)
    try:
        doc = json.loads(r.stdout.decode("utf-8", "replace"))
    except ValueError:
        return None
    pref = set()
    for e in doc.get("lsarContents", []):
        name = e.get("XADFileName") or ""
        head, sep, _ = name.rpartition("/")
        pref.add(head + sep)
    pref.discard("")
    if len(pref) > 1:
        return None
    return pref.pop() if pref else ""


def originals(corpus):
    """{name: (data, rsrc)} for the seven files, from the corpus itself.

    Six are published in `sources/`. `testfile.TIF` was made on the Mac
    and has no original, so its two forks are `unar`'s decode of the
    four DiskDoubler 3.7.7 archives — which must agree, or there is no
    ground truth for it and this refuses to write one.
    """
    src = os.path.join(corpus, "sources")
    out = {}
    for name in NAMES:
        if name == NO_ORIGINAL:
            continue
        p = os.path.join(src, name)
        ad = os.path.join(src, "._" + name)
        out[name] = (read(p), ad_rsrc(ad) if os.path.exists(ad) else b"")
    seen = set()
    for v in ("ad", "ads", "dda", "ddb"):
        arc = os.path.join(corpus, "build", "sources.dd377.%s.dd" % v)
        tmp = tempfile.mkdtemp(prefix="ddtf-tif-")
        try:
            subprocess.run(["unar", "-q", "-nr", "-D", "-k", "hidden",
                            "-e", "macintosh", "-o", tmp, arc],
                           capture_output=True)
            data = os.path.join(tmp, NO_ORIGINAL)
            ad = os.path.join(tmp, "._" + NO_ORIGINAL)
            if not os.path.exists(data):
                continue
            seen.add((read(data), ad_rsrc(ad) if os.path.exists(ad) else b""))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if len(seen) != 1:
        sys.exit("ddtf: %s is not adjudicated (%d readings from unar)"
                 % (NO_ORIGINAL, len(seen)))
    out[NO_ORIGINAL] = seen.pop()
    return out


def entry(name, forks, meta):
    e = {"name": name,
         "data_size": len(forks[0]),
         "data_sha256": hashlib.sha256(forks[0]).hexdigest(),
         "rsrc_size": len(forks[1]),
         "rsrc_sha256": hashlib.sha256(forks[1]).hexdigest()}
    tc = meta.get(os.path.basename(name))
    if tc:
        e["type"], e["creator"] = tc
    return e


ORACLE = ("the published originals in ssokolow/diskdoubler-test-files "
          "@%s (testfile.TIF: unar 1.10.8 on the four DiskDoubler 3.7.7 "
          "archives, which agree; names and type/creator: lsar 1.10.8 on "
          "this file)")


def write_manifest(fixname, path, entries, commit):
    man = {"fixture": fixname,
           "sha256": hashlib.sha256(read(path)).hexdigest(),
           "size": os.path.getsize(path),
           "format": "DiskDoubler",
           "oracle": ORACLE % commit[:12],
           "entries": sorted(entries, key=lambda e: e["name"])}
    with open(os.path.join(MANDIR, fixname + ".json"), "w") as fh:
        json.dump(man, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")


def register(corpus):
    """Copy the corpus into fixtures/, with a row and a manifest each."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import harvest                                        # noqa: E402
    import make_manifests                                 # noqa: E402

    commit = subprocess.check_output(
        ["git", "-C", corpus, "rev-parse", "HEAD"]).decode().strip()
    truth = originals(corpus)
    build = os.path.join(corpus, "build")
    os.makedirs(MANDIR, exist_ok=True)
    rows = harvest.load_sources()

    todo = []                                   # (relpath, kind)
    for v in sorted(os.listdir(build)):
        d = os.path.join(build, v)
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                todo.append(("build/%s/%s" % (v, n), "single"))
            continue
        if v.startswith("._") or v.endswith(".sit"):
            continue
        if v.endswith(".dd") or v.endswith(".sea"):
            todo.append(("build/" + v, "set"))
        elif v.endswith(".hqx"):
            todo.append(("build/" + v, "envelope"))
        elif v.rsplit(".", 1)[-1].isdigit():
            todo.append(("build/" + v, "part"))

    # A split set joins back into BOTH forks of the file it was cut
    # from, and the corpus publishes the resource fork of a split
    # original in an AppleDouble sidecar beside it. Without that sidecar
    # the joiner could only be graded on the data fork — two thirds of
    # the bytes in the `.sea` set would go unchecked — so the sidecars
    # of split originals are fixtures too. Like the parts themselves
    # they get no manifest: they are what run_segments.py grades a
    # joined set AGAINST, not archives to be extracted.
    for rel, kind in list(todo):
        if kind != "part":
            continue
        base = os.path.basename(rel).rsplit(".", 1)[0]
        side = "build/._" + base
        if os.path.exists(os.path.join(corpus, side)) and \
                (side, "sidecar") not in todo:
            todo.append((side, "sidecar"))

    made = 0
    for rel, kind in todo:
        src = os.path.join(corpus, rel)
        fixname = (fixture_name(rel.replace("/._", "/")) + ".ad"
                   if kind == "sidecar" else fixture_name(rel))
        blob = read(src)
        dst = os.path.join(FIXDIR, fixname)
        with open(dst, "wb") as fh:
            fh.write(blob)
        rows[fixname] = (hashlib.sha256(blob).hexdigest(), len(blob),
                         RAW % (commit, urllib.parse.quote(rel)))
        if kind == "single":
            base = os.path.basename(rel)
            out = fixname.rsplit(".", 1)[0] if "." in fixname else fixname
            write_manifest(fixname, dst,
                           [entry(out, truth[base], lsar_meta(src))], commit)
        elif kind == "set":
            pref = lsar_prefix(src)
            if pref is None:
                sys.exit("ddtf: lsar disagrees with itself about %s" % rel)
            meta = lsar_meta(src)
            entries = [entry(pref + n, truth[n], meta) for n in NAMES]
            if pref:
                entries.append({"name": pref.rstrip("/"), "is_dir": True})
            write_manifest(fixname, dst, entries, commit)
        elif kind == "envelope":
            # A BinHex layer is the oracle's own format, so this one is
            # graded the way every other .hqx in the corpus is: by unar,
            # on the file it unwraps. What is INSIDE it is graded by the
            # fixture that file also is — the payload's sha256 below is
            # the sha256 of another row in SOURCES.md.
            man = make_manifests.build_manifest(dst)
            if man is None:
                sys.exit("ddtf: the oracle cannot read %s" % fixname)
            with open(os.path.join(MANDIR, fixname + ".json"), "w") as fh:
                json.dump(man, fh, indent=1, ensure_ascii=False,
                          sort_keys=True)
                fh.write("\n")
        made += 1

    harvest.save_sources(rows)
    print("ddtf: registered %d fixtures at commit %s" % (made, commit[:12]))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--macextract", default=os.path.join(REPO, "build", "macextract"))
    ap.add_argument("--corpus", default="/tmp/diskdoubler-test-files")
    ap.add_argument("--fetch", action="store_true",
                    help="git clone the corpus to --corpus first")
    ap.add_argument("--register", action="store_true",
                    help="copy the corpus into fixtures/, with a "
                         "SOURCES.md row and a manifest for each file")
    args = ap.parse_args()

    if not os.path.exists(args.macextract):
        print("ddtf: no CLI at %s" % args.macextract)
        return 1

    if args.fetch:
        if os.path.exists(args.corpus):
            shutil.rmtree(args.corpus)
        subprocess.check_call(["git", "clone", "--depth", "1", URL, args.corpus])
    build = os.path.join(args.corpus, "build")
    srcdir = os.path.join(args.corpus, "sources")
    if not os.path.isdir(build):
        sys.exit("no corpus at %s — pass --fetch or --corpus" % args.corpus)

    if args.register:
        return register(args.corpus)

    chk = Check()
    tif_single, tif_arc, tif_sea = {}, {}, {}
    tmp = tempfile.mkdtemp(prefix="ddtf-")
    try:
        variants = sorted(d for d in os.listdir(build)
                          if os.path.isdir(os.path.join(build, d)))
        # 1. the single-file container, one directory per method
        singles = 0
        for v in variants:
            for name in sorted(os.listdir(os.path.join(build, v))):
                out = os.path.join(tmp, "one", v, name)
                rc, err = extract(args.macextract, os.path.join(build, v, name), out)
                if rc != 0:
                    chk.bad.append("%s/%s: %s" % (v, name, err))
                    continue
                singles += 1
                # The container carries no name; the host's supplies one,
                # and the CLI drops the extension it arrived with.
                stem = name.rsplit(".", 1)[0] if "." in name else name
                got = os.path.join(out, stem)
                rsrc = os.path.join(out, "._" + stem)
                gotr = read(rsrc) if os.path.exists(rsrc) else b""
                if name == NO_ORIGINAL:
                    tif_single.setdefault("data", set()).add(
                        hashlib.sha256(read(got)).hexdigest())
                    tif_single.setdefault("rsrc", set()).add(
                        hashlib.sha256(gotr).hexdigest())
                    continue
                chk.eq("%s/%s" % (v, name), read(got),
                       read(os.path.join(srcdir, name)))
                orig = os.path.join(srcdir, "._" + name)
                chk.eq("%s/%s rsrc" % (v, name), gotr,
                       ad_rsrc(orig) if os.path.exists(orig) else b"")

        # 2. the archives, and 3. the self-extractors, each with and
        #    without a BinHex layer around it
        counts = {"archive": 0, "archive-hqx": 0, "sea": 0, "sea-hqx": 0}
        for name in sorted(os.listdir(build)):
            path = os.path.join(build, name)
            if not os.path.isfile(path) or name.startswith("._"):
                continue
            if name.endswith(".dd"):
                kind, tif = "archive", tif_arc
            elif name.endswith(".dd.hqx"):
                kind, tif = "archive-hqx", tif_arc
            elif name.endswith(".sea"):
                kind, tif = "sea", tif_sea
            elif name.endswith(".sea.hqx"):
                kind, tif = "sea-hqx", tif_sea
            else:
                continue                      # .sit wrappers, .dd.1/.2 SPLT
            out = os.path.join(tmp, kind, name)
            rc, err = extract(args.macextract, path, out)
            if rc != 0:
                chk.bad.append("%s: %s" % (name, err))
                continue
            counts[kind] += 1
            check_set(chk, find_root(out), srcdir, name, tif)

        for what, seen in (("single-file", tif_single), ("archive", tif_arc),
                           ("self-extractor", tif_sea)):
            for fork, hashes in sorted(seen.items()):
                if len(hashes) != 1:
                    chk.bad.append("%s %s of %s differs across methods: %d hashes"
                                   % (NO_ORIGINAL, fork, what, len(hashes)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("ddtf: %d single-file containers, %d archives (%d BinHexed), "
          "%d self-extractors (%d BinHexed)"
          % (singles, counts["archive"], counts["archive-hqx"],
             counts["sea"], counts["sea-hqx"]))
    print("ddtf: %d forks compared with the published originals, %d mismatched"
          % (chk.ok, len(chk.bad)))
    for line in chk.bad:
        print("  FAIL " + line)
    return 1 if chk.bad else 0


if __name__ == "__main__":
    sys.exit(main())

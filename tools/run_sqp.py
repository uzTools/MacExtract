#!/usr/bin/env python3
"""run_sqp.py — AppleLink `.pkg` (SqueezePlay) tests.

Five lanes, and they grade different things:

1. **The two real packages**, when `tools/fetch_specimens.py --only
   applelink` has fetched them: the engine must sniff each as an
   AppleLink package and expand all four members to the sha256
   `tools/derive_sqp.py` recorded on 2026-10-05 from an independent
   reading of Aladdin's own expander. These are the only authentic
   bytes anything here is graded on, and they reach four of the
   format's paths and not the rest. Skips cleanly without them.

2. **Six synthesised packages** (`tools/synth_sqp.py`), which reach the
   rest: a resource fork, a stored fork, a stream with two clear codes
   and 13-bit widths, version 0, and a folder tree. Ground truth is the
   bytes that went in. What this lane CANNOT say is that Aladdin's
   expander would read those packages — no package written here has
   ever been handed to one (MANUAL_TESTS.md).

3. **gzip, on every LZW fork of every package in lanes 1 and 2.** A
   SqueezePlay fork is a Unix `compress` code stream: put the three
   bytes of a `.Z` header in front of it — `1f 9d`, then 13 bits with
   block mode — and `gzip -dc` decodes it. That makes the CODEC's
   oracle a second implementation rather than this repository's own
   reading, including for the clear code, which no real package
   contains. Skips cleanly without gzip.

4. **Negative controls.** Every test the sniffer makes is bent in turn
   and must make it answer `unknown`, and a package cut inside a
   member's stream must be reported per entry rather than extracted
   quietly. A probe nobody has watched fail is a probe that says yes.

5. **Corruption, aimed at the decoder.** `tools/fuzz.py` draws uniformly
   from the corpus, so a `.pkg` is 6 of 943 fixtures and
   `tools/fuzz_cover.py` measured the WALK at zero lines after 400 cases
   (the probe reached 83.9 %). This bends the six fixtures directly — a
   fixed seed, so it is the same 300 mutants every run — and requires no
   sanitizer report and no abnormal exit from the ones that still sniff
   as a package. Most do: a mutation has to land in the directory to
   break the tiling, and the directory is a tenth of the bytes.

    python3 tools/run_sqp.py --macextract build/san/macextract
    python3 tools/run_sqp.py --register        # rewrite the manifests

TESTING.md (*AppleLink packages: SqueezePlay*) is the write-up.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import synth_sqp as S                                   # noqa: E402

FIXDIR = os.path.join(ROOT, "fixtures")
MANDIR = os.path.join(FIXDIR, "manifests")
HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "applelink")

OURNAME = "AppleLink package"
ORACLE = ("tools/synth_sqp.py (the bytes it compressed), with gzip -dc "
          "reading every LZW fork through a .Z header")

# The four members of the two real packages. IMPORTED rather than copied:
# `tools/derive_sqp.py` recorded them from its own reading of Aladdin's
# translator and is their one home, so there is no second figure here to
# drift from it (CLAUDE.md, *one home per finding*). Its keys are
# (package, member).
_spec = importlib.util.spec_from_file_location(
    "derive_sqp", os.path.join(ROOT, "tools", "derive_sqp.py"))
_ds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ds)
REAL = {}
for (_pkg, _member), _sha in _ds.EXPANDED.items():
    REAL.setdefault(_pkg, {})[_member] = _sha

# One committed fixture per case (fixtures/SOURCES.md regenerates each
# with `synth_sqp.py --case <name>`), so run_diff.py, run_robustness.sh
# and run_truncation.py cover them too.
FIXTURES = {case: "synth-sqp-%s.pkg" % case for case in sorted(S.CASES)}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def run(args, **kw):
    return subprocess.run(args, capture_output=True, timeout=300, **kw)


# ---------------------------------------------------------------- lane 3
def gzip_available():
    return shutil.which("gzip") is not None


def gzip_expand(stream, tmp):
    """One LZW fork through gzip: `.Z` magic, then 13 bits with block
    mode (0x80), which is the configuration SqueezePlay hardwires."""
    p = os.path.join(tmp, "fork.Z")
    with open(p, "wb") as f:
        f.write(b"\x1f\x9d" + bytes([13 | 0x80]) + stream)
    r = run(["gzip", "-dc", p])
    return r.returncode, r.stdout


# ---------------------------------------------------------------- lanes
def extract(macextract, path, tmp):
    """(exit status, {name: bytes}, stderr) for one package."""
    out = os.path.join(tmp, "out")
    os.makedirs(out)
    r = run([macextract, "x", "-nr", "-o", out, path])
    got = {}
    for root, dirs, files in os.walk(out):
        rel = os.path.relpath(root, out)
        for f in files:
            name = os.path.normpath(os.path.join(rel, f)).replace(os.sep, "/")
            got[name] = open(os.path.join(root, f), "rb").read()
    return r.returncode, got, r.stderr.decode("utf-8", "replace")


def lane_real(macextract, bad, with_gzip):
    """Every real package in SPECIMENS, graded three ways.

    The two the project started with have a recorded sha256 per member
    (`REAL`).  The six found on 2026-10-06 do not and do not need one:
    each record states the expanded length of both its forks, so the
    WRITER's own arithmetic grades the length, `derive_sqp.py`'s reading
    grades the bytes against a second implementation of the container,
    and `gzip` grades every LZW stream against a program that has never
    heard of the format (DECISIONS.md 2026-10-06).
    """
    pkgs = sorted(os.listdir(SPECIMENS)) if os.path.isdir(SPECIMENS) else []
    if not pkgs:
        print("sqp: no real packages in %s — run tools/fetch_specimens.py "
              "--only applelink (lane 1 skipped)" % SPECIMENS)
        return 0
    n = recorded = gz = 0
    for fn in pkgs:
        path = os.path.join(SPECIMENS, fn)
        blob = open(path, "rb").read()
        r = run([macextract, "sniff", path])
        got = r.stdout.decode().strip()
        if got != OURNAME:
            bad.append("%s: sniff says %r, not %r" % (fn, got, OURNAME))
        version, sqpn, recs = _ds.directory(blob)
        want, collide = {}, set()
        for rec, member_path in zip(recs, _ds.paths(recs)):
            if rec["folder"]:
                continue
            (data, _), (rsrc, _) = _ds.member(blob, rec)
            # The data fork's file is written whether the member has one
            # or not — `Iconf Display` has three members with an empty
            # data fork, and each is a file on the way out.
            for suffix, fork, declared in (("", data, rec["dlen"]),
                                           (".rsrc", rsrc, rec["rlen"])):
                if suffix and declared == 0:
                    continue
                if len(fork) != declared:
                    bad.append("%s: %r's %s fork expands to %d B where its "
                               "own record declares %d"
                               % (fn, member_path, suffix or "data",
                                  len(fork), declared))
                if member_path + suffix in want:
                    collide.add(member_path + suffix)
                want[member_path + suffix] = fork
        with tempfile.TemporaryDirectory() as tmp:
            rc, files, err = extract(macextract, path, tmp)
            # `-nr` writes a resource fork as NAME.rsrc, and `Iconf
            # Display` holds a member called `bullseye π` and another
            # called `bullseye π.rsrc`: two members of one real package
            # that want one output file. The engine must REFUSE the
            # second rather than overwrite the first, per entry.
            if collide:
                if rc == 0:
                    bad.append("%s: %s is claimed by two members and the "
                               "engine did not refuse either"
                               % (fn, ", ".join(sorted(collide))))
                for name in sorted(collide):
                    if name not in err:
                        bad.append("%s: refused %r without saying so"
                                   % (fn, name))
            elif rc != 0:
                bad.append("%s: exit %d: %s" % (fn, rc, err[:200]))
            for name, fork in sorted(want.items()):
                if name in collide:
                    continue
                n += 1
                if name not in files:
                    bad.append("%s: no %r came out" % (fn, name))
                elif files[name] != fork:
                    bad.append("%s: %r is %d B where derive_sqp.py's reading "
                               "makes it %d" % (fn, name, len(files[name]),
                                                len(fork)))
            for name in files:
                if name.endswith(".rsrc") and name not in want:
                    bad.append("%s: wrote a resource fork for %r, whose "
                               "record declares rlen 0" % (fn, name))
            for name, digest in REAL.get(fn, {}).items():
                recorded += 1
                if name not in files:
                    bad.append("%s: no %r came out" % (fn, name))
                elif sha(files[name]) != digest:
                    bad.append("%s: %r is not the recorded sha256" % (fn, name))
            if with_gzip:
                gz += _gzip_real(blob, recs, _ds.paths(recs), fn, bad, tmp)
    print("sqp: lane 1 — %d fork(s) of %d real package(s) against "
          "derive_sqp.py's reading and their own declared lengths, %d of "
          "them against its recorded sha256" % (n, len(pkgs), recorded))
    if with_gzip:
        print("sqp: lane 1 — %d LZW fork(s) of those packages decoded by "
              "gzip through a .Z header, byte-identical" % gz)
    return n


def _gzip_real(blob, recs, paths_, fn, bad, tmp):
    """Lane 3, on a real package: gzip against the package's own bytes."""
    n = 0
    for rec, member_path in zip(recs, paths_):
        if rec["folder"]:
            continue
        for which, clen, off, elen, stored in (
                ("data", rec["dclen"], rec["doff"], rec["dlen"],
                 rec["flags"] & 0x02),
                ("rsrc", rec["rclen"], rec["roff"], rec["rlen"],
                 rec["flags"] & 0x04)):
            if elen == 0 or stored:
                continue
            rc, out = gzip_expand(blob[off:off + clen], tmp)
            n += 1
            if rc != 0 or out != _ds.fork(blob, off, clen, elen, stored)[0]:
                bad.append("%s: gzip disagrees about %r's %s fork "
                           "(exit %d, %d B out of %d declared)"
                           % (fn, member_path, which, rc, len(out), elen))
    return n


def lane_synth(macextract, bad, with_gzip):
    forks = gz = 0
    for case in sorted(S.CASES):
        items, version = S.CASES[case]()
        blob = S.build(items, version)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, FIXTURES[case])
            with open(path, "wb") as f:
                f.write(blob)
            r = run([macextract, "sniff", path])
            got = r.stdout.decode().strip()
            if got != OURNAME:
                bad.append("%s: sniff says %r, not %r" % (case, got, OURNAME))
            rc, files, err = extract(macextract, path, tmp)
            if rc != 0:
                bad.append("%s: exit %d: %s" % (case, rc, err[:200]))
            for path_, it in S.paths(items, version):
                if it["folder"]:
                    continue
                for suffix, want in (("", it["data"]), (".rsrc", it["rsrc"])):
                    if not want:
                        if path_ + suffix in files and suffix:
                            bad.append("%s: %r should not exist"
                                       % (case, path_ + suffix))
                        continue
                    forks += 1
                    have = files.get(path_ + suffix)
                    if have is None:
                        bad.append("%s: missing %r" % (case, path_ + suffix))
                    elif have != want:
                        bad.append("%s: %r differs from the bytes that went "
                                   "in (%d B out, %d in)"
                                   % (case, path_ + suffix, len(have),
                                      len(want)))
            # lane 3: the same forks, decoded by gzip from the package's
            # own bytes rather than by us.
            if with_gzip:
                gz += _gzip_lane(blob, items, version, case, bad, tmp)
    print("sqp: lane 2 — %d fork(s) across %d synthesised package(s) "
          "against the bytes that went in" % (forks, len(S.CASES)))
    if with_gzip:
        print("sqp: lane 3 — %d LZW fork(s) decoded by gzip through a .Z "
              "header, byte-identical" % gz)
    else:
        print("sqp: lane 3 skipped (no gzip)")
    return forks


def _gzip_lane(blob, items, version, case, bad, tmp):
    n = 0
    recs = _records(blob)
    for rec, it in zip(recs, items):
        if rec["folder"]:
            continue
        for which, clen, offs, elen, stored, want in (
                ("data", rec["dclen"], rec["doff"], rec["dlen"],
                 rec["flags"] & 0x02, it["data"]),
                ("rsrc", rec["rclen"], rec["roff"], rec["rlen"],
                 rec["flags"] & 0x04, it["rsrc"])):
            if elen == 0 or stored:
                continue
            rc, out = gzip_expand(blob[offs:offs + clen], tmp)
            n += 1
            if rc != 0 or out != want:
                bad.append("%s: gzip disagrees about %r's %s fork "
                           "(exit %d, %d B out of %d)"
                           % (case, it["name"], which, rc, len(out),
                              len(want)))
    return n


def _records(blob):
    """The records of a package, for the lanes that need the raw fork
    positions. The reading itself is tools/derive_sqp.py's; this is the
    same arithmetic and deliberately short."""
    sqpn, version = blob[0], blob[1]
    if version == 0:
        base, stride, pre, n = 10, 86, 0, sqpn
    else:
        base = 86 * sqpn + 10
        n = struct.unpack(">I", blob[base:base + 4])[0]
        base, stride, pre = base + 12, 90, 4
    out = []
    for i in range(n):
        raw = blob[base + stride * i:base + stride * (i + 1)]
        r = raw[pre:]
        out.append({
            "folder": pre and struct.unpack(">H", raw[2:4])[0] != 0,
            "rclen": struct.unpack(">I", r[4:8])[0],
            "dclen": struct.unpack(">I", r[8:12])[0],
            "doff": struct.unpack(">I", r[12:16])[0],
            "roff": struct.unpack(">I", r[16:20])[0],
            "rlen": struct.unpack(">I", r[76:80])[0],
            "dlen": struct.unpack(">I", r[80:84])[0],
            "flags": r[84],
        })
    return out


# ---------------------------------------------------------------- lane 4
def _bend(blob, at, value):
    b = bytearray(blob)
    b[at] = value
    return bytes(b)


def lane_negative(macextract, bad):
    """Every test the sniffer makes, bent in turn. A probe with no magic
    number earns its keep only if each of its tests can reject."""
    items, version = S.CASES["plain"]()
    blob = S.build(items, version)
    sqpn = blob[0]
    base = 86 * sqpn + 10
    cases = [
        ("the version byte", _bend(blob, 1, 2)),
        ("the eight zero bytes after it", _bend(blob, 5, 1)),
        ("the item count", _bend(blob, 0, sqpn + 1)),
        ("the second header's eight zero bytes",
         _bend(blob, base + 8, 1)),
        ("the second header's item count",
         _bend(blob, base + 3, blob[base + 3] + 1)),
        ("a record's name length", _bend(blob, base + 12 + 4 + 36, 32)),
        ("a record's level", _bend(blob, base + 12 + 1, 2)),
        ("a fork's compressed length",
         _bend(blob, base + 12 + 4 + 11, blob[base + 12 + 4 + 11] + 1)),
        ("a fork's offset",
         _bend(blob, base + 12 + 4 + 15, blob[base + 12 + 4 + 15] + 1)),
        ("one byte off the end", blob[:-1]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        for what, bent in cases:
            p = os.path.join(tmp, "bent.pkg")
            with open(p, "wb") as f:
                f.write(bent)
            r = run([macextract, "sniff", p])
            got = r.stdout.decode().strip()
            if got == OURNAME:
                bad.append("the sniffer still says %r with %s bent — that "
                           "test is not load-bearing" % (OURNAME, what))

        # And a cut MEMBER. The sniffer refuses it outright — the
        # directory no longer tiles — so this is the WALK's own answer,
        # which only `-f` reaches: the entry must be reported truncated
        # rather than handed over short (DECISIONS.md 2026-08-29, *a cut
        # archive*). Both halves are asserted, because "not recognized"
        # and "truncated" are different promises.
        p = os.path.join(tmp, "cut.pkg")
        with open(p, "wb") as f:
            f.write(blob[:len(blob) - 200])
        r = run([macextract, "sniff", p])
        if r.stdout.decode().strip() == OURNAME:
            bad.append("a package cut inside its last member still sniffs "
                       "as one — the tiling test is not load-bearing")
        r = run([macextract, "x", "-nr", "-f", OURNAME,
                 "-o", os.path.join(tmp, "o"), p])
        msg = (r.stdout + r.stderr).decode("utf-8", "replace")
        if r.returncode == 0 or "truncat" not in msg.lower():
            bad.append("a package cut 200 bytes into its last member "
                       "extracted with exit %d and no truncation reported: %s"
                       % (r.returncode, msg[:200]))
    print("sqp: lane 4 — %d bent packages rejected by the sniffer, and a cut "
          "member reported" % len(cases))


# ---------------------------------------------------------------- lane 5
def lane_fuzz(macextract, bad, n=300, seed=5):
    """The decoder on corrupt input, under whatever sanitizers the binary
    was built with. Deterministic: the same mutants every run."""
    import random
    rng = random.Random(seed)
    cases = sorted(S.CASES)
    blobs = {c: S.build(*S.CASES[c]()) for c in cases}
    sniffed = 0
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "mutant.pkg")
        out = os.path.join(tmp, "out")
        for _ in range(n):
            d = bytearray(blobs[cases[rng.randrange(len(cases))]])
            for _ in range(rng.randrange(1, 9)):
                d[rng.randrange(len(d))] ^= 1 << rng.randrange(8)
            with open(p, "wb") as f:
                f.write(bytes(d))
            r = run([macextract, "sniff", p])
            if r.stdout.decode().strip() != OURNAME:
                continue
            sniffed += 1
            shutil.rmtree(out, ignore_errors=True)
            os.makedirs(out)
            r = run([macextract, "x", "-nr", "-o", out, p])
            err = (r.stdout + r.stderr).decode("utf-8", "replace")
            if r.returncode not in (0, 1) or "Sanitizer" in err \
               or "runtime error" in err:
                bad.append("a mutant exited %d: %s"
                           % (r.returncode, err[:300]))
                break
    if sniffed < n // 2:
        bad.append("only %d of %d mutants still sniffed as a package — this "
                   "lane is testing the probe, not the decoder" % (sniffed, n))
    print("sqp: lane 5 — %d of %d mutants still sniff as a package and all "
          "of them decode without a sanitizer report" % (sniffed, n))


# ------------------------------------------------------------- registration
def register():
    """Write a fixture and a manifest per case. The manifest's oracle is
    the generator's own input, so make_manifests.py leaves it alone (its
    rebuild only touches manifests whose oracle is `unar`)."""
    if not os.path.isdir(MANDIR):
        os.makedirs(MANDIR)
    rows = []
    for case in sorted(S.CASES):
        items, version = S.CASES[case]()
        blob = S.build(items, version)
        name = FIXTURES[case]
        with open(os.path.join(FIXDIR, name), "wb") as f:
            f.write(blob)
        entries = []
        for path, it in S.paths(items, version):
            if it["folder"]:
                entries.append({"name": path, "is_dir": True})
                continue
            entries.append({
                "name": path,
                "type": it["type"].decode("ascii"),
                "creator": it["creator"].decode("ascii"),
                "finder_flags": it["finder"],
                "data_size": len(it["data"]),
                "data_sha256": sha(it["data"]),
                "rsrc_size": len(it["rsrc"]),
                "rsrc_sha256": sha(it["rsrc"]),
            })
        man = {
            "fixture": name,
            "format": "SqueezePlay",
            "oracle": ORACLE,
            "sha256": sha(blob),
            "size": len(blob),
            "entries": entries,
        }
        with open(os.path.join(MANDIR, name + ".json"), "w") as f:
            json.dump(man, f, indent=1, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        rows.append("| %s | %s | %d | synthetic:tools/synth_sqp.py --case %s |"
                    % (name, sha(blob), len(blob), case))
        print("registered %s (%d B, %d entries)" % (name, len(blob),
                                                    len(entries)))
    print("\nfixtures/SOURCES.md rows:")
    for r in rows:
        print(r)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--macextract",
                    default=os.path.join(ROOT, "build/san/macextract"))
    ap.add_argument("--register", action="store_true")
    a = ap.parse_args()
    if a.register:
        return register()
    if not os.path.exists(a.macextract):
        print("sqp: no CLI at %s" % a.macextract)
        return 1
    bad = []
    with_gzip = gzip_available()
    lane_real(a.macextract, bad, with_gzip)
    lane_synth(a.macextract, bad, with_gzip)
    lane_negative(a.macextract, bad)
    lane_fuzz(a.macextract, bad)
    if bad:
        print("\nsqp: FAILED")
        for b in bad:
            print("  " + b)
        return 1
    print("sqp: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

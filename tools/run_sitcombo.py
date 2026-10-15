#!/usr/bin/env python3
"""run_sitcombo.py — the combinations StuffIt Deluxe 2.0.1 had never been
asked for, graded by the program that wrote them.

`tools/run_sitopt.py`'s specimens are one subject per module at the
defaults. `tools/vmac/sitcombo.py` asked the same writer for everything
else it will do (2026-10-11), and this replays the result:

  setb, setk  `JPEG Lossy` over 12 documents Photoshop 1.0.7 drew and 21
              coloured ones in its layout: every width from 1 to 512,
              grey, CMYK, HSL, HSB, multichannel, indexed and bitmap
  setqlow/high  the same at Q=5 and Q=255, the ends the module accepts
  seta        `Photoshop 1` over Photoshop's own documents under every
              method; `Text 1` under Best Guess and in 1.5.1 archives;
              four Optimizers at once over a folder
  setp        `MacPaint 1` over a second, denser painting, every method
  setc        every Optimizer under `DES` and under `NewDE`
  setd        both ciphers over empty and resource-only forks, a fork of
              exactly eight blocks, every method, a folder, 11 entries
  sete        `PassLock`, `NewDEx` and `DESex` over optimized entries
  settall     `JPEG Lossy` over a 16 x 8,208 document, past the height
              this engine refused until 2026-10-15 (`sitopt.py
              --pssynth`, then `--psjpeg`); optional, graded when present

**The oracle is the writer.** A lossy or inexact module's answer is what
2.0.1 itself restored — each set unstuffed its own archives in the same
boot — and an exact one's is the document that went in. Nothing here is
graded against this engine's own output except where a set's control is
another archive this file already grades.

What this CANNOT see:

- **anything on a fresh clone.** The specimens are emulator output and
  are not committed; this skips cleanly and says so when they are absent.
- **a document Photoshop drew in colour.** The coloured ones (`cdocs/`)
  are built in Photoshop 1.0's own layout — PSOdd's resource fork with
  its `8BIM` 1000 rewritten — because driving the colour picker was not
  needed to answer the question: what is graded is 2.0.1's archive and
  2.0.1's restore of it, both authentic.
- **2.0.1's handling of a width over 512, or of a height over 300 but
  8,208.** A 8,208-pixel WIDTH crashed the emulated Mac once, mid-script,
  and left no archive to grade (DECISIONS.md 2026-10-15, *the height
  nothing needed*).

    tools/run_sitcombo.py --macextract build/macextract
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(os.path.expanduser("~"), ".cache", "macextract", "vmac",
                    "specimens")
COMBO = os.path.join(SPEC, "sitcombo")
OLD = os.path.join(SPEC, "sitopt")
PW = "swordfish"


def forks(path):
    d = open(path, "rb").read()
    dl = int.from_bytes(d[83:87], "big")
    rl = int.from_bytes(d[87:91], "big")
    off = 128 + ((dl + 127) // 128) * 128
    return d[128:128 + dl], d[off:off + rl]


def extract(cli, arc, pw=True):
    """(rc, messages, {relative path: bytes})."""
    out = tempfile.mkdtemp(prefix="sitcombo-")
    try:
        r = subprocess.run([cli, "x", "-o", out] + (["-p", PW] if pw else [])
                           + [arc], capture_output=True, text=True)
        files = {}
        for root, _d, fs in os.walk(out):
            for f in fs:
                p = os.path.join(root, f)
                files[os.path.relpath(p, out)] = open(p, "rb").read()
        return r.returncode, (r.stdout + r.stderr).strip(), files
    finally:
        shutil.rmtree(out, ignore_errors=True)


def same(got, want):
    """'' when equal; a reason otherwise. None/b'' both mean absent."""
    if not got and not want:
        return ""
    if got is None:
        return "missing"
    if want is None:
        return "unexpected %d B" % len(got)
    if got == want:
        return ""
    n = min(len(got), len(want))
    return "%d B against %d, %d differ" % (
        len(got), len(want), sum(1 for i in range(n) if got[i] != want[i]))


class Grader(object):
    def __init__(self, cli):
        self.cli = cli
        self.problems = []
        self.checked = 0

    def fork(self, label, got, want):
        self.checked += 1
        why = same(got, want)
        if why:
            self.problems.append("%s: %s" % (label, why))

    def entry(self, arc, name, want_data, want_rsrc, pw=True, skip_hdr=0):
        rc, msg, f = extract(self.cli, arc, pw)
        label = "%s/%s" % (os.path.relpath(arc, SPEC), name)
        if rc != 0:
            self.problems.append("%s: exit %d: %s" % (label, rc, msg[:160]))
            return msg
        d, r = f.get(name), f.get(name + ".rsrc")
        if skip_hdr:
            # `MacPaint 1` throws a painting's 512-byte header away and
            # nothing can put it back; this engine writes zeros there.
            self.fork(label + " header", d[:skip_hdr] if d else None,
                      bytes(skip_hdr))
            d, want_data = d[skip_hdr:] if d else d, want_data[skip_hdr:]
        self.fork(label + " data", d, want_data)
        if want_rsrc is not False:
            self.fork(label + " rsrc", r, want_rsrc or None)
        return msg

    def refuses(self, label, arc, args, expect):
        """`x`, not `t`: `l` and `t` never unwrap an envelope, so `t` on
        a MacBinary archive tests the MacBinary and accepts it."""
        self.checked += 1
        out = tempfile.mkdtemp(prefix="sitcombo-")
        try:
            r = subprocess.run([self.cli, "x", "-o", out] + args + [arc],
                               capture_output=True, text=True)
        finally:
            shutil.rmtree(out, ignore_errors=True)
        if r.returncode == 0:
            self.problems.append("%s: accepted" % label)
        elif expect not in r.stderr:
            self.problems.append("%s: expected %r, got %r"
                                 % (label, expect, r.stderr.strip()[:160]))


def p(*parts):
    return os.path.join(COMBO, *parts)


def jpeg(g):
    """`JPEG Lossy`: byte for byte against 2.0.1's own restore, and the
    resource fork against the document — which 2.0.1 does NOT give
    back, rewriting 30-odd bytes of the map."""
    cases = []
    for s, docdir in (("setb", None), ("setk", "cdocs")):
        for f in sorted(os.listdir(p(s))):
            if not (f.startswith("J") and f.endswith(".sit.bin")):
                continue
            n = f[1:-8]
            doc = (p(docdir, n + ".bin") if docdir
                   else p("ps-" + n, n + ".bin"))
            cases.append((p(s, f), n, p(s, n + ".bin"), doc))
    for s in ("setqlow", "setqhigh"):
        cases.append((p(s, "Q.sit.bin"), "PSDoc2", p(s, "PSDoc2.bin"),
                      os.path.join(OLD, "psdoc2", "PSDoc2.bin")))
    # Optional, so that a machine with the older sets still grades them.
    if os.path.isdir(p("settall")):
        cases.append((p("settall", "JTall8208.sit.bin"), "Tall8208",
                      p("settall", "Tall8208.bin"),
                      p("settall", "doc", "Tall8208.bin")))
    ref2 = os.path.join(OLD, "ps-jpeg2", "PSDoc2.bin")
    for a in ("DJpg", "NJpg"):
        cases.append((p("setc", a + ".sit.bin"), "PSDoc2", ref2,
                      os.path.join(OLD, "psdoc2", "PSDoc2.bin")))
    for arc, n, restored, doc in cases:
        want = forks(restored)[0]
        orig_d, orig_r = forks(doc)
        msg = g.entry(arc, n, want, orig_r)
        # Indexed and bitmap documents are DECLINED by the module, and
        # their entries are plain: the restore is the document itself.
        if want != orig_d and "rebuilt" not in msg:
            g.problems.append("%s: not reported as rebuilt" % arc)
    return len(cases)


def photoshop1(g):
    """`Photoshop 1` deltas a fork: exact, both forks, every method."""
    n = 0
    d1 = forks(os.path.join(OLD, "psdoc", "PSDoc.bin"))
    d2 = forks(os.path.join(OLD, "psdoc2", "PSDoc2.bin"))
    g.entry(p("seta", "P1Zig.sit.bin"), "PSDoc", *d1)
    for how in ("Fast", "Better", "Faster", "Optimal", "None", "Guess",
                "Old"):
        g.entry(p("seta", "P1%s.sit.bin" % how), "PSDoc2", *d2)
        n += 1
    for f in sorted(os.listdir(p("setb"))):
        if f.startswith("P") and f.endswith(".sit.bin"):
            name = f[1:-8]
            g.entry(p("setb", f), name, *forks(p("ps-" + name,
                                                 name + ".bin")))
            n += 1
    return n + 1


def mixed(g):
    """Four Optimizers at once over a folder, against 2.0.1's restore —
    and the resource forks, which the exact modules keep, against the
    subjects. `Text 1` under Best Guess and a 1.5.1 archive, whose
    stale 255s at 106/108 sit under method bytes WITHOUT the 0x40 bit."""
    _rc, _m, f = extract(g.cli, p("seta", "Mixed.sit.bin"))
    for m in ("MPaint", "MSubject", "MPhoto", "MSound", "MPlain"):
        want = forks(p("seta", m + ".bin"))[0]
        got = f.get("Mixed/" + m)
        if m == "MPaint":
            g.fork("Mixed/MPaint artwork", got[512:] if got else None,
                   want[512:])
        else:
            g.fork("Mixed/" + m, got, want)
    g.fork("Mixed/MPhoto rsrc", f.get("Mixed/MPhoto.rsrc"),
           forks(os.path.join(OLD, "psdoc2", "PSDoc2.bin"))[1])
    _rc, _m, plain = extract(g.cli, os.path.join(OLD, "make2",
                                                 "Plain.sit.bin"))
    g.entry(p("seta", "TOld.sit.bin"), "Subject", plain.get("Subject"),
            plain.get("Subject.rsrc"))
    _rc, _m, opt = extract(g.cli, os.path.join(OLD, "make2",
                                               "Optimized.sit.bin"))
    g.entry(p("seta", "TGuess.sit.bin"), "Subject", opt.get("Subject"),
            None)
    return 8


def macpaint(g):
    """`MacPaint 1` over a second painting, every method."""
    doc = forks(p("paint-Painting2", "Painting2.bin"))[0]
    restored = forks(p("setp", "Painting2.bin"))[0]
    if restored[512:] != doc[512:]:
        g.problems.append("setp: 2.0.1's own restore is not the artwork")
    for how in ("Fast", "Better", "Faster", "Optimal", "Guess"):
        g.entry(p("setp", "MP%s.sit.bin" % how), "Painting2", restored,
                None, skip_hdr=512)
    # `none` stuffs without the Optimizer and leaves a stale 4 at 106.
    g.entry(p("setp", "MPNone.sit.bin"), "Painting2", doc,
            forks(p("paint-Painting2", "Painting2.bin"))[1])
    return 6


def ciphers(g):
    """Every Optimizer under DES and NewDE, against the same entry
    unencrypted; the three plug-ins over optimized entries; and the
    ciphers' edges, against the subjects that went in."""
    plain = {
        "Paint": (os.path.join(OLD, "paintmake", "OptPaint.sit.bin"),
                  "Painting"),
        "Text": (os.path.join(OLD, "make2", "Optimized.sit.bin"), "Subject"),
        "Ps1": (p("seta", "P1Fast.sit.bin"), "PSDoc2"),
        "Snd": (os.path.join(OLD, "mods5", "OptSound.sit.bin"), "Sound2"),
    }
    n = 0
    for short, (pp, name) in plain.items():
        _rc, _m, f0 = extract(g.cli, pp)
        for pre in "DN":
            arc = p("setc", pre + short + ".sit.bin")
            g.entry(arc, name, f0.get(name), f0.get(name + ".rsrc"))
            g.refuses(arc + " without a password", arc, [],
                      "wrong password")
            n += 1
    _rc, _m, fp = extract(g.cli, os.path.join(OLD, "paintmake",
                                              "OptPaint.sit.bin"))
    d2 = forks(os.path.join(OLD, "psdoc2", "PSDoc2.bin"))
    for mod in ("PassLock", "NewDEx", "DESex"):
        arc = p("sete", "G%s.sit.bin" % mod)
        g.entry(arc, "Painting", fp.get("Painting"), None)
        g.entry(arc, "PSDoc2", *d2)
        n += 2
    sys.path.insert(0, os.path.join(HERE, "vmac"))
    import sitcombo as C                                 # noqa: E402
    import sitopt as S                                   # noqa: E402
    want = {"Empty": (b"", b""), "Exact8": (C.textish(64, 3), b""),
            "RsrcOnly": (b"", S.make_rsrc())}
    for i, (name, _how) in enumerate(C.BIG):
        want[name] = (C.textish(40000 + 777 * i, 11 + i), S.make_rsrc())
    want["Papers/First"] = (b"the first file in the folder\r" * 4,
                            S.make_rsrc())
    want["Papers/Second"] = (b"and the second\r" * 7, b"")
    for arc in ("DMix", "NMix", "PMix"):
        _rc, _m, f = extract(g.cli, p("setd", arc + ".sit.bin"))
        for k, (wd, wr) in want.items():
            g.fork("%s/%s data" % (arc, k), f.get(k), wd)
            g.fork("%s/%s rsrc" % (arc, k), f.get(k + ".rsrc"), wr or None)
            n += 1
    return n


def forkless(g, tmp):
    """The same archives with their resource fork gone, which is how a
    .sit sits on a Unix disk: the 'MKey' is in that fork, so no password
    can work and the message must say what is missing. Until 2026-10-11
    a DES one said the engine "does not implement" DES."""
    for arc, expect in (("DMix", "resource fork"), ("NMix", "encrypted")):
        raw = os.path.join(tmp, arc + ".sit")
        open(raw, "wb").write(forks(p("setd", arc + ".sit.bin"))[0])
        g.refuses(arc + " without its resource fork", raw, ["-p", PW],
                  expect)
        r = subprocess.run([g.cli, "t", "-p", PW, raw], capture_output=True,
                           text=True)
        if "does not implement" in r.stderr:
            g.problems.append(arc + ": forkless archive blamed on the "
                              "engine")
    return 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default=os.path.join(
        os.path.dirname(HERE), "build", "macextract"))
    args = ap.parse_args()
    need = [p(d) for d in ("seta", "setb", "setc", "setd", "sete", "setk",
                           "setp", "setqlow", "setqhigh", "cdocs")]
    missing = [d for d in need if not os.path.isdir(d)]
    if missing:
        print("run_sitcombo: SKIPPED — no specimens (%s); "
              "tools/vmac/sitcombo.py makes them" %
              os.path.relpath(missing[0], SPEC))
        return 0
    g = Grader(args.macextract)
    tmp = tempfile.mkdtemp(prefix="sitcombo-")
    try:
        counts = [("JPEG Lossy", jpeg(g)), ("Photoshop 1", photoshop1(g)),
                  ("mixed, Text 1", mixed(g)), ("MacPaint 1", macpaint(g)),
                  ("ciphers", ciphers(g)), ("forkless", forkless(g, tmp))]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("run_sitcombo: %s; %d checks" % (
        ", ".join("%s %d" % c for c in counts), g.checked))
    for pr in g.problems:
        print("  PROBLEM: " + pr)
    print("run_sitcombo: %d problem(s)" % len(g.problems))
    return 1 if g.problems else 0


if __name__ == "__main__":
    sys.exit(main())

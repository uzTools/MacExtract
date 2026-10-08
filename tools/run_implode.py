#!/usr/bin/env python3
"""run_implode.py — zip method 6 (Implode), on streams written here.

`tools/synth_implode.py` is the only thing on this machine that WRITES
the method, so this is where its output is held to something that is not
this engine. Four graders per entry, and that is the whole point:

  - **the writer's own plaintext**, which it emits with `--plain`: the
    bytes it coded, not a decode of what it wrote;
  - **`unar`**, which implements Implode (it is the corpus's primary
    oracle and adjudicates 5 of the 7 wild entries);
  - **deark**, which implements it independently and is the oracle
    `tools/make_manifests.py` records for the other 2
    (reference/deark/src/fmtutil-lzh.c, the file src/fmt_exo.c's
    decoder was read beside);
  - **the CRC-32 the writer stores**, which `macextract t` checks and is
    the same check a real PKZIP file is graded by.

Ahead of all four, `synth_implode.py --selftest` holds the code
construction to **APPNOTE.TXT 5.3.8's own worked example** — the stored
tree `0x02 0x42 0x01 0x13`, read and written both ways, and the eight
codes the document prints for it. That is the only check in this file
that is not downstream of this project's reading of the specification,
and it was made to fail three ways before it was believed.

An encoder of our own agreeing with our own decoder would prove nothing;
the two outside readers are what make it ground truth. All four shapes
the format's flag word can state are written — 4 K and 8 K dictionary
against two and three Shannon-Fano trees — where the committed fixtures
reach two of the four and a ZipIt specimen that cannot be committed
reaches the others (FORMATS.md, *Implode*).

A SECOND lane bends the streams: 240 mutants over a fixed seed, every
edit confined to the bytes `--ranges` declares compressed, each required
to exit cleanly with no sanitizer report. `tools/fuzz.py`'s stream
generator does the same thing in the general run; this one is here so
that the Implode paths are hammered on every `ci.sh` run rather than
when the draw happens to pick them.

    tools/run_implode.py --macextract build/san/macextract

A THIRD lane, since 2026-10-08: **the two streams PKZIP 1.01 and 1.02
would have written**, in an archive of their own. Those two versions
took the minimum match length from the DICTIONARY SIZE rather than from
the literal tree's presence, which is observable in exactly two of the
four combinations — and `8k-2trees-mmlbug` is the one of those two that
**no authentic file on this disk carries**, so for that half this writer
is the only subject there is. Graded the same way, with one addition and
one subtraction:

  - **deark is the second reader**, and it is not optional here the way
    it is above: it implements the rule, finds it by its own
    double-decode, and must agree byte for byte.
  - **`unar` must REFUSE both**, which is this lane's negative control.
    XADMaster has only 5.3.4's reading, so a stream it accepts was never
    the bug's; it fails these two exactly as it fails the three real
    ones in `fixtures/pkz101.exe`.

The authentic half is graded by `run_diff.py` through that fixture's own
manifest on every run, so this lane is the backstop for one combination
and the only subject for the other — FORMATS.md, *Implode*, says which
is which rather than letting a green run imply both.

**What it cannot see.** No Finder metadata and no fork split: a
MacBinary payload under an Implode entry is the ZipIt specimen's shape,
and `tools/run_zipit.py` is what grades that.

Skips cleanly — printing what it skipped, returning 0 — when `unar` or
deark is missing, so a fresh clone stays green.
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEARK = os.path.join(ROOT, "build", "deark", "deark")
SYNTH = os.path.join(ROOT, "tools", "synth_implode.py")

SHAPES = ("4k-2trees", "4k-3trees", "8k-2trees", "8k-3trees")
MUTANTS = 240


def write_seed(tmp, only=None):
    """The archive, its declared compressed spans, and the plaintext."""
    zp = os.path.join(tmp, "implode.zip")
    rp = os.path.join(tmp, "implode.ranges")
    pp = os.path.join(tmp, "implode.plain")
    cmd = [sys.executable, SYNTH, "-o", zp, "--ranges", rp, "--plain", pp]
    for n in only or ():
        cmd += ["--only", n]
    subprocess.run(cmd, check=True, capture_output=True)
    with open(rp) as fh:
        ranges = [tuple(r) for r in json.load(fh)]
    with open(pp, "rb") as fh:
        plain = fh.read()
    return zp, ranges, plain


def ours(exe, path, out):
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([exe, "x", "-o", out, path],
                       capture_output=True, timeout=900)
    if r.returncode != 0:
        return None, r.stderr.decode("utf-8", "replace").strip()
    return {n: open(os.path.join(out, n), "rb").read()
            for n in sorted(os.listdir(out))
            if not n.endswith(".comment.txt")}, None


def theirs_unar(path, out):
    os.makedirs(out, exist_ok=True)
    r = subprocess.run(["unar", "-nr", "-D", "-f", "-q", "-o", out, path],
                       capture_output=True, timeout=900)
    if r.returncode != 0:
        return None
    return {n: open(os.path.join(out, n), "rb").read()
            for n in sorted(os.listdir(out))}


def theirs_deark(path, out):
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([DEARK, "-od", out, path],
                       capture_output=True, timeout=900)
    text = (r.stdout + r.stderr).decode("utf-8", "replace")
    if "CRC check failed" in text or "Error" in text:
        return None, text.strip()
    got = {}
    for n in sorted(os.listdir(out)):
        # deark names each member `output.NNN.NAME`.
        parts = n.split(".", 2)
        got[parts[2] if len(parts) == 3 else n] = \
            open(os.path.join(out, n), "rb").read()
    return got, None


def grade_shapes(exe):
    """Every shape, against all four graders. Returns failures."""
    bad = 0
    tmp = tempfile.mkdtemp(prefix="implode-")
    try:
        zp, _ranges, plain = write_seed(tmp)
        mine, err = ours(exe, zp, os.path.join(tmp, "mine"))
        if mine is None:
            print("implode: `x` FAILED on the generated archive (%s)" % err)
            return 1
        them = theirs_unar(zp, os.path.join(tmp, "unar"))
        dk, dkerr = theirs_deark(zp, os.path.join(tmp, "deark"))
        if dk is None:
            print("implode: deark refused the generated archive (%s)"
                  % (dkerr or "no output"))
            bad += 1
        # The writer emits the shapes' plaintexts concatenated in order,
        # which is how it says what it coded rather than what it wrote.
        at = 0
        for shape in SHAPES:
            name = shape + ".txt"
            got = mine.get(name)
            if got is None:
                print("implode: %s: this build produced no such entry" % name)
                bad += 1
                continue
            want = plain[at:at + len(got)]
            at += len(got)
            if got != want:
                print("implode: %s: %d B out, and NOT the %d B the writer "
                      "coded" % (name, len(got), len(want)))
                bad += 1
            if them is not None and them.get(name) != got:
                print("implode: %s: differs from unar's" % name)
                bad += 1
            if dk is not None and dk.get(name) != got:
                print("implode: %s: differs from deark's" % name)
                bad += 1
        if at != len(plain):
            print("implode: the four entries account for %d of the writer's "
                  "%d plaintext bytes" % (at, len(plain)))
            bad += 1
        # `t` is the CRC-32 check, and it is the grader that needs no
        # second implementation at all: the writer stored it.
        r = subprocess.run([exe, "t", zp], capture_output=True, timeout=900)
        if r.returncode != 0:
            print("implode: `t` failed the generated archive (%s)"
                  % r.stderr.decode("utf-8", "replace").strip())
            bad += 1
        print("implode: %d shape(s) graded against the writer's plaintext, "
              "%s, %s and the stored CRC-32"
              % (len(SHAPES),
                 "unar" if them is not None else "unar (ABSENT)",
                 "deark" if dk is not None else "deark (ABSENT)"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad


BUGSHAPES = ("4k-3trees-mmlbug", "8k-2trees-mmlbug")


def grade_bugshapes(exe):
    """The PKZIP 1.01/1.02 minimum match length, on streams written that
    way. Returns failures.

    **One archive per shape**, not one archive holding both, and the
    reason is what the suite can see. Both this engine and deark settle
    the question per ARCHIVE from the first bug-capable entry, so in a
    two-entry archive only the first one is ever the subject — and which
    of the two it is changes what a bent build gets away with. Written
    one at a time, each shape has to settle its own archive: a probe that
    ignores the stored CRC-32 is then caught by `4k-3trees-mmlbug`, whose
    stream decodes to the right LENGTH and the wrong bytes under 5.3.4's
    reading, where `8k-2trees-mmlbug` runs out of stream instead and so
    is refused for a reason that has nothing to do with the CRC.
    """
    bad = 0
    for shape in BUGSHAPES:
        name = shape + ".txt"
        tmp = tempfile.mkdtemp(prefix="implode-bug-")
        try:
            zp, _ranges, plain = write_seed(tmp, only=(shape,))
            mine, err = ours(exe, zp, os.path.join(tmp, "mine"))
            if mine is None:
                print("implode: `x` FAILED on %s's archive (%s) — this build "
                      "has APPNOTE 5.3.4's minimum match length and only "
                      "that one" % (shape, err))
                bad += 1
                continue
            got = mine.get(name)
            if got is None:
                print("implode: %s: this build produced no such entry" % name)
                bad += 1
                continue
            if got != plain:
                print("implode: %s: %d B out, and NOT the %d B the writer "
                      "coded" % (name, len(got), len(plain)))
                bad += 1
            # deark is not optional on this lane the way it is above: it
            # is the only other implementation of the rule, and it finds
            # it by its own double-decode rather than being told.
            dk, dkerr = theirs_deark(zp, os.path.join(tmp, "deark"))
            if dk is None:
                if os.path.exists(DEARK):
                    print("implode: deark refused %s's archive (%s), and it "
                          "is the reader that implements this rule"
                          % (shape, dkerr or "no output"))
                    bad += 1
            elif dk.get(name) != got:
                print("implode: %s: differs from deark's" % name)
                bad += 1
            # The stored CRC-32, which is the grader a real PKZIP file
            # gets and the one no decoder here can influence.
            r = subprocess.run([exe, "t", zp], capture_output=True,
                               timeout=900)
            if r.returncode != 0:
                print("implode: `t` failed %s's archive (%s)"
                      % (shape, r.stderr.decode("utf-8", "replace").strip()))
                bad += 1
            # The negative control, and it is what says this stream is
            # the BUG's rather than one more ordinary one: XADMaster has
            # 5.3.4's reading and nothing else, so it has to refuse this
            # entry — the way it refuses the three real ones in
            # `fixtures/pkz101.exe`.
            if shutil.which("unar") is not None:
                if theirs_unar(zp, os.path.join(tmp, "unar")) is not None:
                    print("implode: unar ACCEPTED %s's archive, so that "
                          "stream is not the bug's — the writer wrote "
                          "5.3.4's minimum match length after all" % shape)
                    bad += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("implode: %d PKZIP 1.01/1.02 shape(s) graded against the writer's "
          "plaintext, %s and the stored CRC-32, one archive each, with %s"
          % (len(BUGSHAPES),
             "deark" if os.path.exists(DEARK) else "deark (ABSENT)",
             "unar refusing every one" if shutil.which("unar")
             else "unar ABSENT"))
    return bad


def bend(blob, ranges, rng):
    """One mutant: edits confined to the declared compressed spans —
    bit flips, byte-run overwrites and a cut. The same three
    `tools/fuzz.py`'s stream generator makes, for the same reason: a
    Shannon-Fano stream is a tree followed by what it codes, so an edit
    near the front changes the meaning of everything after it."""
    buf = bytearray(blob)
    spans = [(lo, min(hi, len(buf))) for lo, hi in ranges]
    spans = [s for s in spans if s[0] < s[1]]
    for _ in range(rng.randrange(1, 9)):
        if not spans:
            break
        lo, hi = spans[rng.randrange(len(spans))]
        kind = rng.randrange(8)
        if kind == 0:
            buf = buf[:rng.randrange(lo, hi)]
            spans = [(a, min(b, len(buf))) for a, b in spans]
            spans = [s for s in spans if s[0] < s[1]]
        elif kind == 1:
            at = rng.randrange(lo, hi)
            n = min(rng.randrange(1, 64), hi - at)
            buf[at:at + n] = bytes(rng.randrange(256) for _ in range(n))
        else:
            buf[rng.randrange(lo, hi)] ^= 1 << rng.randrange(8)
    return bytes(buf)


def grade_mutants(exe, n, seed):
    """Bent streams: a clean exit and no signal, every time."""
    bad = 0
    rng = random.Random(seed)
    tmp = tempfile.mkdtemp(prefix="implode-fuzz-")
    try:
        zp, ranges, _plain = write_seed(tmp)
        with open(zp, "rb") as fh:
            blob = fh.read()
        refused = 0
        for i in range(n):
            var = bend(blob, ranges, rng)
            p = os.path.join(tmp, "case.zip")
            with open(p, "wb") as fh:
                fh.write(var)
            try:
                r = subprocess.run([exe, "t", p], capture_output=True,
                                   timeout=120)
            except subprocess.TimeoutExpired:
                print("implode: mutant %d HUNG" % i)
                bad += 1
                continue
            if r.returncode < 0:
                print("implode: mutant %d died by signal %d"
                      % (i, -r.returncode))
                bad += 1
                continue
            text = (r.stdout + r.stderr).decode("utf-8", "replace")
            if "Sanitizer" in text or "runtime error" in text:
                print("implode: mutant %d: %s" % (i, text.strip()[:400]))
                bad += 1
                continue
            if r.returncode != 0:
                refused += 1
        print("implode: %d bent stream(s) clean, %d of them refused at least "
              "one entry — seed %d" % (n, refused, seed))
        # A lane where nothing was ever refused is a lane that bent
        # nothing: the edits are inside the stream, so the CRC-32 has to
        # object. (A mutant CAN come out clean — a flip in the padding
        # bits after the last token changes no output.)
        if refused == 0:
            print("implode: NOT ONE mutant was refused, so the edits are "
                  "not reaching the decoder — the declared ranges are wrong")
            bad += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad


# ---------------------------------------------------------------- lane 4
MIXED = ("mixed-bug", "mixed-spec", "mixed-spec2")


def grade_mixed(exe):
    """An archive carrying BOTH readings, which is the shape the
    per-archive verdict is wrong about. Returns failures.

    The verdict is settled once, from the first bug-capable entry, and
    that is what makes it affordable — 19.4 bug-capable entries per
    archive in the sweep's population. It is also an assumption about
    writers, and the measured part is narrower than the assumption: no
    archive of the 1,537 swept on 2026-10-08 mixes. A zip is appendable,
    so this lane holds what happens when one does. PKZIP itself does not
    make this shape: run under DOSBox, 1.10 adding to a 1.0x archive
    keeps the old stamps but writes no disagreeing combination of its
    own, and the current build extracts that real archive in full
    (tools/pkzip_writers.py). The shape needs two writers that BOTH
    write those combinations, and none is on this disk.

    What it asserts, in the order it matters:
      1. the entry that SETTLED the archive comes out;
      2. the next one, which inherited a verdict wrong about it, is
         REFUSED — its bytes have already reached the sink and
         begin_entry is called once per entry, so it cannot be rescued —
         and refused as a CHECKSUM failure, not as the truncation a
         desynchronised decode reports;
      3. the one AFTER that comes out, because the verdict went back to
         unsettled and the entry probed for itself. This is the whole
         point: the assumption costs one entry, not the rest of the
         archive.

    The oracle is each entry's own stored CRC-32, computed by the writer
    from the plaintext it coded. deark cannot be one here: it settles per
    archive as well, so it gets the same entries wrong.

    It fails on the build of 2026-10-08: two entries refused instead of
    one, both reported as truncated, and no third-entry output.
    """
    bad = 0
    tmp = tempfile.mkdtemp(prefix="implode-mixed-")
    try:
        zp = os.path.join(tmp, "mixed.zip")
        pp = os.path.join(tmp, "plain")
        subprocess.run([sys.executable, SYNTH, "--mixed", "-o", zp,
                        "--plain", pp], check=True, capture_output=True)
        want = {n: open("%s.%s" % (pp, n), "rb").read() for n in MIXED}
        out = os.path.join(tmp, "mine")
        os.makedirs(out, exist_ok=True)
        r = subprocess.run([exe, "x", "-o", out, zp],
                           capture_output=True, timeout=900)
        err = r.stderr.decode("utf-8", "replace")
        got = {}
        for n in MIXED:
            fp = os.path.join(out, n + ".txt")
            if os.path.exists(fp):
                got[n] = open(fp, "rb").read()
        if got.get("mixed-bug") != want["mixed-bug"]:
            print("implode: mixed-bug.txt did not come out, and it is the "
                  "entry that settles the archive — the verdict never "
                  "reached the 1.01/1.02 reading")
            bad += 1
        if got.get("mixed-spec") == want["mixed-spec"]:
            print("implode: mixed-spec.txt came out whole, so this build "
                  "does not settle the minimum match length per archive at "
                  "all and lane 3 should have failed first")
            bad += 1
        elif "checksum mismatch" not in err:
            print("implode: mixed-spec.txt was refused, but not as a "
                  "checksum failure: %r. Its bytes are not short; the rule "
                  "was wrong" % err.strip()[:120])
            bad += 1
        if got.get("mixed-spec2") != want["mixed-spec2"]:
            print("implode: mixed-spec2.txt did not come out, so a verdict "
                  "that was wrong about ONE entry was carried into the rest "
                  "of the archive")
            bad += 1
        if r.returncode == 0:
            print("implode: the mixed archive exited 0, and one of its "
                  "entries cannot be recovered — that entry has to be "
                  "reported")
            bad += 1
        if not bad:
            print("implode: 1 mixed archive — the entry that settles it and "
                  "the one after the refusal both come out, the inherited "
                  "verdict costs exactly the one entry it was wrong about, "
                  "and that one is a checksum failure")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--macextract", default="build/macextract")
    ap.add_argument("-n", type=int, default=MUTANTS)
    ap.add_argument("--seed", type=int, default=6)
    a = ap.parse_args()

    if shutil.which("unar") is None:
        print("implode: unar not installed — one of the two outside readers "
              "is absent, so this run proves less")
    if not os.path.exists(DEARK):
        print("implode: no %s (sh tools/build_deark.sh) — the other outside "
              "reader is absent" % os.path.relpath(DEARK, ROOT))
    # Before anything else, and before any binary is believed: the code
    # construction against the SPECIFICATION's own worked example. It
    # needs no oracle, no fixture and no engine, and it is the one check
    # here that is not downstream of this project's reading of 5.3.8.
    r = subprocess.run([sys.executable, SYNTH, "--selftest"],
                       capture_output=True, timeout=120)
    sys.stdout.write(r.stdout.decode("utf-8", "replace"))
    sys.stderr.write(r.stderr.decode("utf-8", "replace"))
    bad = 1 if r.returncode else 0
    bad += grade_shapes(a.macextract)
    bad += grade_bugshapes(a.macextract)
    bad += grade_mixed(a.macextract)
    bad += grade_mutants(a.macextract, a.n, a.seed)
    if bad:
        print("implode: %d failure(s)" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

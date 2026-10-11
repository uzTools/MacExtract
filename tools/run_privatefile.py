#!/usr/bin/env python3
"""run_privatefile.py — the Aladdin Private File (`.pf`) suite.

Nothing else reads Private File — not `unar`, not deark, not macunpack —
so the grader is the writer: files Private File 2.0's `PF Encrypt™`
encrypted under Mini vMac, from subjects whose bytes and passwords are
fixed in tools/vmac/privatefile.py. Each one is extracted here with its
password, through every layer (MacBinary, Private File, then the StuffIt
archive PF Encrypt makes before it encrypts), and BOTH forks are compared
with the bytes that went in.

    tools/vmac/privatefile.py --make NAME        make them (an emulator run)
    tools/run_privatefile.py --macextract build/macextract

They live outside the repository, beside the emulator's other state:

    ~/.cache/macextract/vmac/specimens/privatefile/NAME/SUBJECT.pf.bin

What a specimen cannot show is a REFUSAL, so the second half writes files
with tools/synth_pf.py — this project's own reading, which therefore
grades nothing about the format — and checks only that each is refused
the way a user should meet it: a wrong password, a flipped byte (both
CRCs are of the PLAINTEXT, so a flipped ciphertext byte is caught), a
truncation, and a header naming a derivation nothing here writes.

What it CANNOT see: the 16-byte key of Aladdin's domestic build (the one
writer here is the export build, which keys with five bytes — FORMATS.md),
and a Private File holding more than one item, which PF Encrypt makes as
one StuffIt archive and so reads like any other.

With no specimens it says so and runs the refusals alone, so a fresh
clone stays green. A PARTIAL set is a failure, and so is a specimen whose
subject is unknown: a lane that skipped them could lose its only check
against Private File's own output one file at a time and stay green.
"""
import argparse
import glob
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import synth_pf as S                                   # noqa: E402

HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "privatefile")


def subjects():
    """The subject table, out of the harness that typed the passwords —
    one copy of it, so a subject changed there is graded as changed."""
    spec = importlib.util.spec_from_file_location(
        "privatefile", os.path.join(REPO, "tools", "vmac", "privatefile.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return {n: (d, r, pw) for n, _t, _c, d, r, pw in m.SUBJECTS}


def run(mx, *args, env=None):
    return subprocess.run([mx] + list(args), capture_output=True, env=env)


def readf(p):
    return open(p, "rb").read() if os.path.exists(p) else None


def grade_specimens(mx, problems):
    subj = subjects()
    found = sorted(glob.glob(os.path.join(SPECIMENS, "*", "*.pf.bin")))
    if not found:
        print("run_privatefile: no specimens in %s — "
              "tools/vmac/privatefile.py --make makes them" % SPECIMENS)
        return 0
    seen = set(os.path.basename(p)[:-len(".pf.bin")] for p in found)
    for name in sorted(set(subj) - seen):
        problems.append("no specimen for subject %s, where %d others are "
                        "present" % (name, len(seen)))
    n = 0
    for p in found:
        name = os.path.basename(p)[:-len(".pf.bin")]
        if name not in subj:
            problems.append("%s: no subject named %s" % (p, name))
            continue
        data, rsrc, pw = subj[name]
        out = tempfile.mkdtemp(prefix="pf-")
        try:
            r = run(mx, "x", "-p", pw, "-o", out, p)
            got_d = readf(os.path.join(out, name))
            got_r = readf(os.path.join(out, name + ".rsrc")) or b""
            if r.returncode != 0 or got_d != data or got_r != rsrc:
                problems.append("%s: rc %d, data %s, rsrc %s: %s" % (
                    p, r.returncode, got_d == data, got_r == rsrc,
                    r.stderr.decode(errors="replace").strip()))
                continue
            # Unwrapped once by hand, the same specimen must REFUSE a
            # wrong password rather than decode to rubbish, and must list
            # under the name the record holds once the right one is given.
            bare = os.path.join(out, "bare.pf")
            subprocess.run([mx, "x", "-nr", "-o", out, p],
                           capture_output=True, check=True)
            os.rename(os.path.join(out, name + ".pf"), bare)
            r = run(mx, "t", "-p", pw + "x", bare)
            if r.returncode == 0 or b"wrong password" not in r.stderr:
                problems.append("%s: a wrong password was not refused" % p)
            r = run(mx, "l", "-p", pw, bare)
            if (name + ".sit").encode() not in r.stdout:
                problems.append("%s: listed %r, not %s.sit" % (
                    p, r.stdout, name))
            n += 1
        finally:
            shutil.rmtree(out, ignore_errors=True)
    print("run_privatefile: %d specimens graded byte-exact against "
          "their subjects" % n)
    return n


def refusals(mx, problems):
    tmp = tempfile.mkdtemp(prefix="pfsyn-")
    try:
        good = S.encode("Inner", b"TEXT", b"ttxt", b"plain\r" * 300,
                        b"fork" * 40, b"letmein")

        def case(label, blob, args, want_rc, want_err=None, env=None):
            p = os.path.join(tmp, label + ".pf")
            open(p, "wb").write(blob)
            r = run(mx, *(list(args) + [p]), env=env)
            err = r.stderr.decode(errors="replace")
            if (r.returncode != 0) != (want_rc != 0) or \
                    (want_err and want_err not in err):
                problems.append("refusal %s: rc %d, %r" % (
                    label, r.returncode, err.strip()))

        # The positive control first: a refusal case that cannot fail
        # proves nothing (CLAUDE.md, Traps).
        case("good", good, ("t", "-p", "letmein"), 0)
        # `UncIO` allows a short read before EOF and a file never returns
        # one, so the CLI's UNC_SHORT_READ is the only way to send one.
        # The footer was read with one bare call until 2026-10-09, and this
        # case failed on that build: both forks out, then "truncated".
        case("shortread", good, ("t", "-p", "letmein"), 0,
             env=dict(os.environ, UNC_SHORT_READ="7"))
        case("wrongpw", good, ("t", "-p", "letmeout"), 1, "wrong password")
        # A refused password and then the right one, through --ask: the
        # record is decrypted in place and re-read for each password
        # tried, so this is the path that breaks if the re-read goes.
        p = os.path.join(tmp, "retry.pf")
        open(p, "wb").write(good)
        r = subprocess.run([mx, "t", "--ask", p], input=b"letmeout\nletmein\n",
                           capture_output=True)
        if r.returncode != 0 or b"wrong, try again" not in r.stdout + r.stderr:
            problems.append("retry: rc %d, %r" % (r.returncode, r.stderr))
        case("nopw", good, ("t",), 1, "wrong password")
        flipped = bytearray(good)
        flipped[400] ^= 1                  # inside the data fork
        case("flipped", bytes(flipped), ("t", "-p", "letmein"), 1,
             "checksum mismatch")
        # A header naming derivation 0 is a Private File PFEngine has a
        # path for and nothing here writes: named, and refused per entry.
        odd = S.encode("Inner", b"TEXT", b"ttxt", b"x", b"", b"letmein",
                       derivation=0)
        case("method", odd, ("t", "-p", "letmein"), 1,
             "encrypted by a scheme we cannot read")
        # Cut short, the footer's 'CSIT' is gone and the file is not
        # claimed at all — which is what a truncated download should say.
        r = run(mx, "sniff", os.path.join(tmp, "good.pf"))
        if b"Private File" not in r.stdout:
            problems.append("sniff: %r" % r.stdout)
        p = os.path.join(tmp, "cut.pf")
        open(p, "wb").write(good[:-1])
        r = run(mx, "sniff", p)
        if b"Private File" in r.stdout:
            problems.append("a truncated file was still claimed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--macextract", default=os.path.join(REPO, "build",
                                                         "macextract"))
    a = ap.parse_args()
    problems = []
    grade_specimens(a.macextract, problems)
    refusals(a.macextract, problems)
    for p in problems:
        print("run_privatefile: FAIL %s" % p)
    if problems:
        return 1
    print("run_privatefile: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

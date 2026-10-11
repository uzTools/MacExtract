#!/usr/bin/env python3
"""derive_dehqx.py — two of BinHex's rules about mailed text, out of the
decoder written by the man who wrote the format's definition.

`src/fmt_binhex.c` cited macutils' `hexbin` for three rules that are
about text that has been MAILED rather than about an encoding. Two of
them are **DeHQX 2.0.1's**, and DeHQX is `fixtures/dehqx-201.hqx` — a
corpus fixture since M1 — by **Peter N Lewis**, who also wrote the
"BinHex 4.0 Definition" that this project already cites for the format
itself (NOTICE). Its documentation states both, in *How It Works*:

  * **the second document in one input** — "When it comes to the end of
    the HQX source, if [sic] checks for the terminating colon, and then
    continues scanning the file for the next '(This file...'", with the
    glossary defining a source file as "a file containing (parts of) one
    or more HQX sources";
  * **the part separator a posting is CUT at** — "If it encounters a
    line beginning with '--- end of part', it ignores the file until it
    encounters a line consisting only of '---', at which time it resumes
    dehqxing."

The second one was not a citation question at all. **This engine failed
a posting cut that way**, measured 2026-10-06: the resume line is `---`
and all three of those characters are in the BinHex alphabet, so it is
read as two bytes of data and the fork's CRC objects. `hexbin` reads
such a file — by the length half of its rule, which this project
declines for its own reasons (`src/fmt_binhex.c`) — so a second
implementation was getting it right the whole time.

What is left with macutils after this is ONE rule: the skip of a line
with intermediate garbage (OPEN_ITEMS.md).

    tools/derive_dehqx.py --witness   both sentences, in the fixture
    tools/derive_dehqx.py --grade     this engine over a posting cut at
                                      DeHQX's separator, against hexbin
    tools/derive_dehqx.py             both, skipping what is absent

**What this cannot see: a wild posting cut that way.** None of the 204
`.hqx` fixtures carries the separator (measured 2026-10-06 — they are
Info-Mac downloads, which are single postings), so the subject here is a
real fixture cut at the boundary the documentation DESCRIBES rather than
one somebody posted. The sentence is first-party and the failure it
predicted was real; the frequency of files shaped this way is not
something this corpus can say.

Not in `ci.sh`: it needs fixtures, which are copyrighted and not
committed. What IS in `ci.sh` is `tools/run_multihqx.py`, which carries
the same posting as a generated case.

License: LGPL-2.1-or-later. See LICENSE and NOTICE.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXDIR = os.path.join(ROOT, "fixtures")
FIXTURE = os.path.join(FIXDIR, "dehqx-201.hqx")
DOC = "DeHQX Documentation"

# The subject the posting is built from: a small real .hqx, the same one
# tools/run_multihqx.py cuts up.
SUBJECT = os.path.join(FIXDIR, "export-hc.hqx")

# What the documentation says, where this project relies on it. Each is
# checked verbatim against the file that ships beside the application,
# typo and all ("if checks for the terminating colon"). 0xc9 is
# MacRoman's ellipsis, which is why these are bytes rather than text.
WITNESSES = [
    ("the second document in one input (bh_find_banner, `limited` = 0)",
     b"When it comes to the end of the HQX source, if checks for the "
     b"terminating colon, and then continues scanning the file for the "
     b'next "(This file\xc9"'),
    ("and that a source file may hold more than one",
     b"Source file: a file containing (parts of) one or more HQX sources."),
    ("the part separator a posting is cut at (bh_refill_line)",
     b'If it encounters a line beginning with "--- end of part", it '
     b"ignores the file until it encounters a line consisting only of "
     b'"---", at which time it resumes dehqxing.'),
    ("and that mail headers may be in front of it",
     b"Source files may contain any NEWS or MAIL headers."),
]


def cli():
    for p in (os.path.join(ROOT, "build", "macextract"),
              os.path.join(ROOT, "build", "san", "macextract"),
              os.path.join(ROOT, "macextract")):
        if os.path.exists(p):
            return p
    return None


def documentation():
    """DeHQX's own documentation, out of the corpus fixture.

    Two layers — BinHex, then StuffIt — and this project's own CLI walks
    both, so no format knowledge lives here.
    """
    exe = cli()
    if not exe or not os.path.exists(FIXTURE):
        return None, None
    work = tempfile.mkdtemp(prefix="ddq-")
    subprocess.run([exe, "x", "-o", work, FIXTURE], capture_output=True)
    for dirpath, _d, files in os.walk(work):
        for f in files:
            if f == DOC:
                return work, open(os.path.join(dirpath, f), "rb").read()
    shutil.rmtree(work, ignore_errors=True)
    return None, None


def witness():
    work, doc = documentation()
    if doc is None:
        print("derive-dehqx: no %s — the fixture %s is absent or the CLI is "
              "not built" % (DOC, os.path.basename(FIXTURE)))
        return 0
    try:
        bad = 0
        print("derive-dehqx: %s, %d B" % (DOC, len(doc)))
        for what, needle in WITNESSES:
            at = doc.find(needle)
            bad += 0 if at >= 0 else 1
            print("  %-4s @%s %s"
                  % ("ok" if at >= 0 else "FAIL",
                     ("0x%04x" % at) if at >= 0 else "  --  ", what))
        print("derive-dehqx: %d of %d sentence(s) hold"
              % (len(WITNESSES) - bad, len(WITNESSES)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def posting(path):
    """One document cut at DeHQX's separator, as its documentation
    describes a part boundary: the first half, "--- end of part 1", a
    mail header, the resume line "---", the second half."""
    raw = open(SUBJECT, "rb").read().replace(b"\r\n", b"\n").replace(b"\r",
                                                                    b"\n")
    lines = raw.split(b"\n")
    half = len(lines) // 2
    open(path, "wb").write(
        b"\n".join(lines[:half]) + b"\n"
        b"--- end of part 1\n\n"
        b"From: someone\nSubject: export-hc.hqx (2/2)\n\n"
        b"---\n" + b"\n".join(lines[half:]))


def forks(outdir):
    out = {}
    for dirpath, _d, files in os.walk(outdir):
        for f in files:
            out[f] = open(os.path.join(dirpath, f), "rb").read()
    return out


def grade():
    exe = cli()
    if not exe or not os.path.exists(SUBJECT):
        print("derive-dehqx: no CLI or no %s" % os.path.basename(SUBJECT))
        return 0
    tmp = tempfile.mkdtemp(prefix="ddq-g-")
    bad = 0
    try:
        cut = os.path.join(tmp, "posted.hqx")
        posting(cut)
        whole, parts = os.path.join(tmp, "a"), os.path.join(tmp, "b")
        os.makedirs(whole), os.makedirs(parts)
        r1 = subprocess.run([exe, "x", "-nr", "-o", whole, SUBJECT],
                            capture_output=True)
        r2 = subprocess.run([exe, "x", "-nr", "-o", parts, cut],
                            capture_output=True)
        want, got = forks(whole), forks(parts)
        ok = r2.returncode == 0 and want == got
        bad += 0 if ok else 1
        print("  %-4s ours: the posting gives %d file(s), exit %d%s"
              % ("ok" if ok else "FAIL", len(got), r2.returncode,
                 "" if ok else " — " + r2.stderr.decode()[:90]))
        if r1.returncode != 0:
            print("  FAIL the subject alone exits %d" % r1.returncode)
            bad += 1
        if shutil.which("hexbin"):
            hb = tempfile.mkdtemp(prefix="ddq-h-")
            try:
                subprocess.run(["hexbin", "-f", cut], cwd=hb,
                               capture_output=True)
                blobs = [b for n, b in forks(hb).items()
                         if not n.endswith(".info")]
                same = [b for b in blobs if b in want.values()]
                print("  %-4s hexbin: %d fork(s), %d of them the same bytes"
                      % ("ok" if same else "FAIL", len(blobs), len(same)))
                bad += 0 if same else 1
            finally:
                shutil.rmtree(hb, ignore_errors=True)
        else:
            print("  --   no hexbin (tools/build_macunpack.sh): the second "
                  "implementation is then not consulted")
        print("derive-dehqx: %s" % ("the posting reads clean"
                                    if not bad else "FAILED"))
        return 1 if bad else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--witness", action="store_true",
                    help="both sentences, in the fixture")
    ap.add_argument("--grade", action="store_true",
                    help="this engine over a posting cut at the separator")
    a = ap.parse_args()
    rc = 0
    if a.witness or not a.grade:
        print("derive-dehqx: what the documentation says")
        rc |= witness()
    if a.grade or not a.witness:
        print("derive-dehqx: the posting")
        rc |= grade()
    return rc


if __name__ == "__main__":
    sys.exit(main())

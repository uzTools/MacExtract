#!/usr/bin/env python3
"""run_macgzip.py — files MacGzip itself wrote, graded against its input.

Every gzip in `fixtures/` came from a Unix `gzip` or from
`tools/synth_exo.py`; nothing graded what the Macintosh's own gzip makes
of a two-fork file. These eleven are MacGzip 1.1.3 68K (gzip 1.2.4
inside), run on emulated Mac OS 8.1 on 2026-10-14, over one subject:
"A Document", TEXT/ttxt, 292 bytes of data and 391 of resource, from
StuffIt Deluxe 5.0's tutorial folder.

    python3 tools/run_macgzip.py --macextract build/macextract

They live outside the repository with the other specimens, because the
subject is not this project's to distribute:

    ~/.cache/macextract/vmac/specimens/macgzip/lvl1.gz ... lvl9.gz
    ~/.cache/macextract/vmac/specimens/macgzip/binary.gz, ascii.gz
    ~/.cache/macextract/vmac/specimens/macgzip/source-A_Document.macbinary.bin

MacGzip's three modes, in its own Quick Intro's words: "Force MacBinary
mode" (lvl1-9, one per compression level its stepper offers; there is
no level 0), "Force Binary (raw) mode" (binary.gz) and "Force ASCII
(text) mode" (ascii.gz); the last two were told to discard the resource
fork. What each must extract to:

  - MacBinary: both forks of the subject, byte for byte, under the name
    the inner MacBinary header holds — gzip, then MacBinary, unwrapped
    by the CLI on its own;
  - Binary: the subject's data fork, byte for byte;
  - ASCII: the subject's data fork with every CR turned into LF, which
    is what MacGzip wrote. The engine converts nothing back.

The subject's forks are read here, from its MacBinary II header
(reference/notes/macbinary_ii.txt: lengths at 83 and 87, data at 128,
the resource fork after the data padded to 128), not by the engine
under test. Each specimen must also sniff as Gzip unaided, and the
MacBinary layer under one level, taken off with `-nr`, must list with
the subject's type, creator and fork lengths.

With no specimen directory it says so and returns 0, so a fresh clone
stays green. A directory missing any of the eleven, or the subject,
fails.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "macgzip")
SUBJECT = "source-A_Document.macbinary.bin"

EXPECT = dict([("lvl%d.gz" % n, "macbinary") for n in range(1, 10)] +
              [("binary.gz", "binary"), ("ascii.gz", "ascii")])


def be32(b, off):
    return (b[off] << 24) | (b[off + 1] << 16) | (b[off + 2] << 8) | b[off + 3]


def read_subject(path):
    """(name, type+creator, data fork, resource fork) of a MacBinary II
    file. Source: reference/notes/macbinary_ii.txt."""
    b = open(path, "rb").read()
    n = b[1]
    name = b[2:2 + n].decode("mac_roman")
    tc = b[65:73]
    dlen, rlen = be32(b, 83), be32(b, 87)
    rstart = 128 + ((dlen + 127) // 128) * 128
    return name, tc, b[128:128 + dlen], b[rstart:rstart + rlen]


def run(args, **kw):
    return subprocess.run(args, capture_output=True, timeout=120, **kw)


def grade(exe, spec, mode, subj):
    """Errors for one specimen, as a list of strings."""
    name, tc, data, rsrc = subj
    path = os.path.join(SPECIMENS, spec)
    stem = spec[:-3]
    errs = []
    r = run([exe, "sniff", path])
    if r.stdout.decode().strip() != "Gzip":
        errs.append("sniffs as %r, not Gzip" % r.stdout.decode().strip())

    work = tempfile.mkdtemp(prefix="macgzip-")
    try:
        r = run([exe, "x", "-o", work, path])
        if r.returncode != 0:
            return errs + ["x exited %d (%s)" % (
                r.returncode, r.stderr.decode("utf-8", "replace").strip())]
        got = sorted(os.listdir(work))
        if mode == "macbinary":
            want = {name: data, name + ".rsrc": rsrc}
        elif mode == "binary":
            want = {stem: data}
        else:
            want = {stem: data.replace(b"\r", b"\n")}
        if got != sorted(want):
            return errs + ["wrote %s, expected %s" % (got, sorted(want))]
        for fn, blob in sorted(want.items()):
            out = open(os.path.join(work, fn), "rb").read()
            if out != blob:
                errs.append("%s: %d bytes, expected %d — DIFFERS"
                            % (fn, len(out), len(blob)))

        if mode == "macbinary":
            # One layer down: the MacBinary stream MacGzip compressed.
            nr = os.path.join(work, "nr")
            os.mkdir(nr)
            r = run([exe, "x", "-nr", "-o", nr, path])
            inner = os.path.join(nr, stem)
            if r.returncode != 0 or not os.path.exists(inner):
                return errs + ["x -nr did not write %s" % stem]
            r = run([exe, "l", "--finder", inner])
            line = r.stdout.decode("utf-8", "replace").splitlines()[-1:]
            fields = line[0].split(None, 5) if line else []
            want_fields = ["f", str(len(data)), str(len(rsrc)),
                           "%s/%s" % (tc[:4].hex(), tc[4:].hex())]
            if fields[:4] != want_fields or fields[-1:] != [name]:
                errs.append("inner MacBinary lists as %r, expected %s ... %s"
                            % (line, want_fields, name))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default="build/macextract")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.macextract):
        print("macgzip: no CLI at %s" % a.macextract)
        return 1
    if not os.path.isdir(SPECIMENS):
        print("macgzip: no specimens in %s — skipped" % SPECIMENS)
        return 0
    missing = [f for f in sorted(EXPECT) + [SUBJECT]
               if not os.path.exists(os.path.join(SPECIMENS, f))]
    if missing:
        print("macgzip: specimen set incomplete, missing %s" % missing)
        return 1

    subj = read_subject(os.path.join(SPECIMENS, SUBJECT))
    bad = 0
    for spec in sorted(EXPECT):
        errs = grade(a.macextract, spec, EXPECT[spec], subj)
        for e in errs:
            print("macgzip: %s: %s" % (spec, e))
        if errs:
            bad += 1
        elif a.verbose:
            print("macgzip: %s: ok (%s)" % (spec, EXPECT[spec]))
    print("macgzip: %d of %d specimens graded, %d failed"
          % (len(EXPECT), len(EXPECT), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

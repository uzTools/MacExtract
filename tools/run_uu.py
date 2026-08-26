#!/usr/bin/env python3
"""run_uu.py — uuencoded files, adjudicated by macutils' `hexbin`.

No `.uu` exists in the corpus (measured 2026-08-15 by innermost format
over all 805 fixtures), so tools/synth_uu.py writes them. Each shape has
its own independent grader, which is the whole point:

  plain uuencode   `binascii.b2a_uu` (CPython) encodes it and the ground
                   truth is the bytes that went in — our decoder never
                   touches the encoding side.
  UUTool ("MU")    `hexbin` decodes it. That is the implementation
                   fmt_uu.c was transcribed from (hexbin/mu.c), so
                   agreement is between two implementations rather than
                   between a generator and its own mirror image. It is
                   the same reason `macunpack` grades StuffIt method 6.

Also checked: several documents in one file (the newsgroup shape), a
mail banner in front, CR line endings, and the two ways this must fail
— prose containing the word "begin" is not an archive, and a truncated
document is an error rather than a short file.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_uu                                     # noqa: E402

DATA = b"the quick brown fox jumps over the lazy dog.\n" * 30
RSRC = bytes(range(256)) * 3


def read(p):
    return open(p, "rb").read() if os.path.exists(p) else None


def check_ours(macextract, path, want, problems):
    """want: {name: (data fork, rsrc fork)}"""
    out = tempfile.mkdtemp()
    try:
        r = subprocess.run([macextract, "x", "-o", out, path],
                           capture_output=True)
        if r.returncode != 0:
            problems.append("%s: exit %d (%s)"
                            % (os.path.basename(path), r.returncode,
                               r.stderr.decode().strip()[:80]))
        for name, (df, rf) in want.items():
            if read(os.path.join(out, name)) != df:
                problems.append("%s: data fork of %s differs"
                                % (os.path.basename(path), name))
            got_rsrc = read(os.path.join(out, name + ".rsrc"))
            if rf and got_rsrc != rf:
                problems.append("%s: resource fork of %s differs"
                                % (os.path.basename(path), name))
            if not rf and got_rsrc is not None:
                problems.append("%s: %s grew a resource fork"
                                % (os.path.basename(path), name))
    finally:
        shutil.rmtree(out, ignore_errors=True)


def check_hexbin(path, forks, problems):
    """hexbin -f writes each fork as its own file; match by content."""
    out = tempfile.mkdtemp()
    try:
        subprocess.run(["hexbin", "-f", os.path.abspath(path)],
                       cwd=out, capture_output=True)
        blobs = [read(os.path.join(out, f)) for f in os.listdir(out)]
        for label, want in forks:
            if want not in blobs:
                problems.append("%s: hexbin does not agree on the %s fork"
                                % (os.path.basename(path), label))
    finally:
        shutil.rmtree(out, ignore_errors=True)


def main():
    macextract = os.path.join(ROOT, "build", "macextract")
    args = sys.argv[1:]
    if "--macextract" in args:
        macextract = args[args.index("--macextract") + 1]
    if not os.path.exists(macextract):
        print("run_uu: no CLI at %s" % macextract)
        return 1

    problems = []
    tmp = tempfile.mkdtemp()
    ran = 0
    try:
        subprocess.run([sys.executable,
                        os.path.join(ROOT, "tools", "synth_uu.py"), tmp],
                       capture_output=True, check=True)

        cases = {
            "synth-uu-plain.uu":     {"hello.txt": (DATA, b"")},
            "synth-uu-banner.uu":    {"hello.txt": (DATA, b"")},
            "synth-uu-multi.uu":     {"first.txt": (b"first file\n", b""),
                                      "second.bin": (bytes(range(200)), b"")},
            "synth-uu-mac.uu":       {"Mac File": (DATA, RSRC)},
            "synth-uu-mac-nrsrc.uu": {"Data Only": (DATA, b"")},
        }
        for name, want in cases.items():
            check_ours(macextract, os.path.join(tmp, name), want, problems)
            ran += 1

        if shutil.which("hexbin"):
            check_hexbin(os.path.join(tmp, "synth-uu-mac.uu"),
                         [("data", DATA), ("resource", RSRC)], problems)
            check_hexbin(os.path.join(tmp, "synth-uu-mac-nrsrc.uu"),
                         [("data", DATA)], problems)
            ran += 2
        else:
            print("run_uu: no `hexbin` — the UUTool shape is then graded "
                  "only against its own generator (tools/build_macunpack.sh)")

        # CR line endings: these files came off Macs.
        cr = os.path.join(tmp, "cr.uu")
        blob = open(os.path.join(tmp, "synth-uu-multi.uu"), "rb").read()
        open(cr, "wb").write(blob.replace(b"\n", b"\r"))
        check_ours(macextract, cr,
                   {"first.txt": (b"first file\n", b""),
                    "second.bin": (bytes(range(200)), b"")}, problems)
        ran += 1

        # A file posted in SEVERAL PARTS, each with its own mail header,
        # then joined: the headers land in the middle of the stream and
        # have to be stepped over (DECISIONS.md 2026-08-15).
        lines = open(os.path.join(tmp, "synth-uu-plain.uu")).read().splitlines(True)
        half = len(lines) // 2
        posted = os.path.join(tmp, "posted.uu")
        open(posted, "w").write(
            "From: someone\nSubject: hello.txt (1/2)\n\n" + "".join(lines[:half]) +
            "\nFrom: someone\nSubject: hello.txt (2/2)\n\n"
            "[ part 2 of 2 -- append to part 1 ]\n\n" + "".join(lines[half:]))
        check_ours(macextract, posted, {"hello.txt": (DATA, b"")}, problems)
        ran += 1

        # The same set as separate files, joined by the .001/.002 scheme
        # the CLI already has: this goes through split discovery, so it
        # proves the whole chain rather than the decoder alone.
        open(os.path.join(tmp, "split.uu.001"), "w").write(
            "From: someone\nSubject: hello.txt (1/2)\n\n" + "".join(lines[:half]))
        open(os.path.join(tmp, "split.uu.002"), "w").write(
            "From: someone\nSubject: hello.txt (2/2)\n\n" + "".join(lines[half:]))
        check_ours(macextract, os.path.join(tmp, "split.uu.001"),
                   {"hello.txt": (DATA, b"")}, problems)
        ran += 1

        # THE LIMITATION, asserted rather than described. uuencode carries
        # no length and no checksum, so a set missing its MIDDLE part
        # decodes to a SHORT file and nothing can object. If this ever
        # starts failing, the format grew a check nobody knew about.
        gap = os.path.join(tmp, "gap.uu")
        third = len(lines) // 3
        open(gap, "w").write("".join(lines[:third]) + "".join(lines[2 * third:]))
        out = tempfile.mkdtemp()
        r = subprocess.run([macextract, "x", "-o", out, gap], capture_output=True)
        got = read(os.path.join(out, "hello.txt"))
        if r.returncode != 0 or got is None or len(got) >= len(DATA):
            problems.append("gap.uu: a set missing a middle part no longer "
                            "decodes short and silent — re-read OPEN_ITEMS.md")
        shutil.rmtree(out, ignore_errors=True)
        ran += 1

        # Two ways it must fail.
        prose = os.path.join(tmp, "prose.txt")
        open(prose, "w").write("To begin with, nothing here is encoded.\n"
                               "begin the day with a walk\n")
        r = subprocess.run([macextract, "sniff", prose], capture_output=True)
        if b"uuencode" in r.stdout:
            problems.append("prose.txt: prose containing 'begin' sniffed as uu")
        ran += 1

        cut = os.path.join(tmp, "cut.uu")
        lines = open(os.path.join(tmp, "synth-uu-plain.uu")).read().splitlines()
        open(cut, "w").write("\n".join(lines[:6]) + "\n")
        out = tempfile.mkdtemp()
        r = subprocess.run([macextract, "x", "-o", out, cut], capture_output=True)
        if r.returncode == 0:
            problems.append("cut.uu: a truncated document was accepted")
        shutil.rmtree(out, ignore_errors=True)
        ran += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("UU FAIL " + p)
    print("uu: %d case(s) checked, %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""run_uu.py — uuencoded files, adjudicated by macutils' `hexbin`.

No `.uu` exists in the corpus (measured 2026-08-15 by innermost format
over all 805 fixtures), so tools/synth_uu.py writes them. Each shape has
its own independent grader, which is the whole point:

  plain uuencode   `binascii.b2a_uu` (CPython) encodes it and the ground
                   truth is the bytes that went in — our decoder never
                   touches the encoding side.
  UUTool ("MU")    `hexbin` decodes it — a second implementation,
                   reached a different way, so agreement is between two
                   implementations rather than between a generator and
                   its own mirror image. It is the same reason
                   `macunpack` grades StuffIt method 6. (It is no longer
                   what fmt_uu.c cites: the layout is UUTool's own since
                   2026-10-06, tools/derive_mu.py.)

Also checked: several documents in one file (the newsgroup shape), a
mail banner in front, CR line endings, **all three of UUTool's
alphabets and the spelling of zero that is Unix `uuencode`'s rather than
any of them** and the pair of cases that says the alphabet is half of how
a data line is told from mail, and the two ways this must fail — prose
containing the word "begin" is not an archive, and a truncated document
is an error rather than a short file.

The two WILD specimens are not generated and not here: `tools/run_diff.py`
grades `uu-wild-dictcol.uu` and `uu-wild-terrainman.uu` when they are in
`fixtures/`, and `tools/derive_mu.py --grade` replays both.
"""
import binascii
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_uu                                     # noqa: E402
from synth_wrapped import macbinary                 # noqa: E402

DATA = b"the quick brown fox jumps over the lazy dog.\n" * 30
RSRC = bytes(range(256)) * 3
BINARY = bytes(range(256)) * 2


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
            # UUTool's own default alphabet, in both generations
            "synth-uu-mac-unix20.uu":   {"Unix Table": (DATA, RSRC)},
            "synth-uu-mac-unix23.uu":   {"Later Table": (DATA, RSRC)},
            "synth-uu-plain-unix20.uu": {"hello.txt": (DATA, b"")},
            # What Unix `uuencode` writes: the standard alphabet with
            # zero spelled "`" (synth_uu.py, TABLE_PC_BQ).
            "synth-uu-plain-classic.uu": {"binary.bin": (BINARY, b"")},
        }
        for name, want in cases.items():
            check_ours(macextract, os.path.join(tmp, name), want, problems)
            ran += 1

        # Two things about the classic-spelling case, because the case
        # is worth exactly what they say. It regressed once and a green
        # suite could not see it: every generated plain document came
        # from `binascii.b2a_uu`, which spells zero as a SPACE, so no
        # fixture here held the other spelling at all (BLOCKERS.md).
        #
        #   1. that the document really mixes the two spellings — a zero
        #      and a value under 27 on ONE line is what fits neither
        #      half of the alphabet mask, and without such a line this
        #      case tests nothing the case above it does not;
        #   2. that CPython reads it, which makes the agreement one
        #      between two implementations rather than between our
        #      decoder and our own generator. `binascii.a2b_uu` takes
        #      either spelling: its own transform is (c - 0x20) & 0x3f.
        classic = open(os.path.join(tmp, "synth-uu-plain-classic.uu"),
                       "rb").read().split(b"\n")
        mixed = [l for l in classic
                 if 0x60 in l and any(0x20 <= c < 0x3b for c in l)]
        if not mixed:
            problems.append("synth-uu-plain-classic.uu: no line holds both "
                            "spellings, so the case tests nothing")
        got = b"".join(binascii.a2b_uu(l) for l in classic[1:]
                       if l and l not in (b"end", b"`"))
        if got != BINARY:
            problems.append("synth-uu-plain-classic.uu: CPython's a2b_uu "
                            "does not read what the generator wrote")
        ran += 2

        if shutil.which("hexbin"):
            check_hexbin(os.path.join(tmp, "synth-uu-mac.uu"),
                         [("data", DATA), ("resource", RSRC)], problems)
            check_hexbin(os.path.join(tmp, "synth-uu-mac-nrsrc.uu"),
                         [("data", DATA)], problems)
            check_hexbin(os.path.join(tmp, "synth-uu-mac-unix20.uu"),
                         [("data", DATA), ("resource", RSRC)], problems)
            check_hexbin(os.path.join(tmp, "synth-uu-mac-unix23.uu"),
                         [("data", DATA), ("resource", RSRC)], problems)
            ran += 4
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

        # CHAINED, since 2026-08-27: uuencode is an envelope, so a
        # document holding a MacBinary file is opened all the way down
        # and the intermediate deleted. No specimen of this has ever
        # been seen here — btoa's has (FORMATS.md, *btoa*), and the two
        # armours have the same shape, which is why they went in
        # together (DECISIONS.md 2026-08-27).
        inner = b"the file that was posted, not the wrapper\n" * 6
        mb = macbinary("Subject", inner)
        chain = os.path.join(tmp, "Subject.bin.uu")
        open(chain, "w").write(synth_uu.plain("Subject.bin", mb))
        out = tempfile.mkdtemp()
        subprocess.run([macextract, "x", "-o", out, chain], capture_output=True)
        if sorted(os.listdir(out)) != ["Subject"] or \
                read(os.path.join(out, "Subject")) != inner:
            problems.append("chained plain: %r" % sorted(os.listdir(out)))
        shutil.rmtree(out, ignore_errors=True)
        ran += 1

        # The UUTool shape chains too, and its resource fork goes with
        # the layer it is a fork OF — the wrapper's, not the payload's.
        # Same as BinHex, which has done this since M9.
        mchain = os.path.join(tmp, "mac-chain.uu")
        open(mchain, "w").write(synth_uu.uutool("Wrapped.bin", mb,
                                                bytes(range(256)),
                                                b"????", b"????"))
        out = tempfile.mkdtemp()
        subprocess.run([macextract, "x", "-o", out, mchain], capture_output=True)
        if sorted(os.listdir(out)) != ["Subject"] or \
                read(os.path.join(out, "Subject")) != inner:
            problems.append("chained UUTool: %r" % sorted(os.listdir(out)))
        shutil.rmtree(out, ignore_errors=True)
        ran += 1

        # -nr stops at the wrapper: the chain is the recursion, not
        # something the uu decoder started doing.
        out = tempfile.mkdtemp()
        subprocess.run([macextract, "x", "-nr", "-o", out, chain],
                       capture_output=True)
        if sorted(os.listdir(out)) != ["Subject.bin"]:
            problems.append("chained, -nr: %r" % sorted(os.listdir(out)))
        shutil.rmtree(out, ignore_errors=True)
        ran += 1

        # And the guard that makes the newsgroup shape safe: a file
        # holding SEVERAL documents yields several files, so there is no
        # single layer to recurse into and both wrappers survive.
        two = os.path.join(tmp, "two.uu")
        open(two, "w").write(synth_uu.plain("One.bin", mb) +
                             synth_uu.plain("Two.bin", mb))
        out = tempfile.mkdtemp()
        subprocess.run([macextract, "x", "-o", out, two], capture_output=True)
        if sorted(os.listdir(out)) != ["One.bin", "Two.bin"]:
            problems.append("two documents unwrapped: %r"
                            % sorted(os.listdir(out)))
        shutil.rmtree(out, ignore_errors=True)
        ran += 1

        # THE ALPHABET TELLS DATA FROM MAIL, and this is the pair that
        # says so rather than describing it. The same line — a valid
        # data line in the STANDARD alphabet — is inserted into two
        # documents: one written with that alphabet, where it is data
        # and the output grows by its 45 bytes, and one written with
        # UUTool's UNIX table, where no value encodes to a character
        # below 0x3b and it is therefore mail to be stepped over
        # (DECISIONS.md 2026-10-06, *the alphabet nothing here had
        # seen*). A reader that took the union of the two alphabets as
        # one range would absorb it in both.
        intruder = synth_uu.uu_line(b"x" * 45, synth_uu.TABLE_PC)
        for tag, table, want in (("pc", synth_uu.TABLE_PC, DATA[:45] + b"x" * 45 + DATA[45:]),
                                 ("unix", synth_uu.TABLE_UNIX20, DATA)):
            doc = synth_uu.plain("hello.txt", DATA, table=table).splitlines(True)
            mixed = os.path.join(tmp, "intruder-%s.uu" % tag)
            open(mixed, "w").write("".join(doc[:2]) + intruder + "\n"
                                   + "".join(doc[2:]))
            check_ours(macextract, mixed, {"hello.txt": (want, b"")}, problems)
            ran += 1

        # Two ways it must fail.
        prose = os.path.join(tmp, "prose.txt")
        open(prose, "w").write("To begin with, nothing here is encoded.\n"
                               "begin the day with a walk\n")
        r = subprocess.run([macextract, "sniff", prose], capture_output=True)
        if b"uuencode" in r.stdout:
            problems.append("prose.txt: prose containing 'begin' sniffed as uu")
        ran += 1

        # And the way widening the alphabet made it fail, which is the
        # harder one: the line AFTER a "begin" line is what the probe
        # rests on, and an English sentence starting with a capital M
        # declares 45 bytes and is short enough to be one. It is in
        # NEITHER alphabet — it has a space AND lower case — and that is
        # what has to reject it (DECISIONS.md 2026-10-06, *the alphabet
        # nothing here had seen*).
        prose2 = os.path.join(tmp, "prose2.txt")
        open(prose2, "w").write("begin reading at page five\n"
                                "Mary had a little lamb, her fleece\n")
        r = subprocess.run([macextract, "sniff", prose2], capture_output=True)
        if b"uuencode" in r.stdout:
            problems.append("prose2.txt: an English sentence after a 'begin' "
                            "line sniffed as uu — the probe takes the union "
                            "of the alphabets instead of one of them")
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

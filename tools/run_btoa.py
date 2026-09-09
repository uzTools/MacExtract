#!/usr/bin/env python3
"""run_btoa.py — btoa/atob, graded by btoa itself.

The corpus contains no btoa file (measured 2026-08-23: `xbtoa` appears
in none of the 903 fixtures), and no second reader exists — `unar` does
not recognise the format and macutils never had it. What it does have
is its ORIGINAL implementation: btoa 5.2.1 by Paul Rutter, Joe Orost
and Stefan Parmark, which `tools/fetch_references.sh` puts in
`reference/btoa/` and which this compiles and runs as the encoder.

So every case here is: the reference encodes a known file, we decode it,
and the bytes have to match what went in. Both framings are covered —
`xbtoa5` and, with `-o`, the older `xbtoa Begin` — because the two
checksum the stream differently (version 5 over the ENCODED characters,
version 4 over the decoded bytes) and nothing else would notice a
decoder that had them the wrong way round.

Skips cleanly, and says so, when `reference/btoa/` is not there.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.abspath(os.path.join(ROOT, "reference", "btoa"))
BIN = os.path.abspath(os.path.join(ROOT, "build", "btoa", "btoa"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synth_wrapped import macbinary                  # noqa: E402


def build():
    """Compile the reference. It is 1996 K&R C, so the warnings are
    switched off rather than fixed: this is somebody else's source and
    `reference/` is read-only.

    Returns (True, None) when it is there, (False, None) when
    reference/btoa was never fetched — a real skip — and (False, why)
    when the tree IS there and the compile failed. Those were one answer
    until 2026-09-09, and the caller reported both as a missing tree;
    the same conflation in tools/run_mime.py hid a real breakage
    (DECISIONS.md 2026-09-09)."""
    if os.path.exists(BIN):
        return True, None
    if not os.path.isdir(SRC):
        return False, None
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    r = subprocess.run(["gcc", "-w", "-O1", "-std=gnu89", "-o", BIN,
                        os.path.join(SRC, "btoa.c"),
                        os.path.join(SRC, "atob.c"),
                        os.path.join(SRC, "repair.c")],
                       capture_output=True)
    if r.returncode == 0 and os.path.exists(BIN):
        return True, None
    why = (r.stderr or r.stdout).decode("utf-8", "replace").strip()
    return False, why or "gcc exited %d and said nothing" % r.returncode


def subjects():
    """Files chosen for what they make the ENCODER do, not for size."""
    return {
        # A run of zeros becomes `z`, four spaces become `y` (version 5
        # only), and neither appears in ordinary text.
        "runs.bin": bytes(64) + b"AAAA" + b"    " * 4 + bytes(3),
        # Lengths that are not multiples of four: the last group is
        # padded and only (len-1)&3 + 1 of its bytes are real.
        "odd1.bin": b"x" * 101,
        "odd2.bin": b"y" * 102,
        "odd3.bin": b"z" * 103,
        "aligned.bin": b"w" * 104,
        # Every byte value, so no character of the alphabet goes untried.
        "all256.bin": bytes(range(256)) * 3,
        "one.bin": b"!",
        "text.txt": b"btoa is uuencode's rival from the Unix side.\n" * 9,
    }


def main():
    macextract = os.path.join(ROOT, "build", "macextract")
    args = sys.argv[1:]
    if "--macextract" in args:
        macextract = args[args.index("--macextract") + 1]
    if not os.path.exists(macextract):
        print("run_btoa: no CLI at %s" % macextract)
        return 1
    ok, why = build()
    if not ok:
        if why is None:
            print("run_btoa: SKIPPED — no reference/btoa "
                  "(tools/fetch_references.sh)")
            return 0
        print("run_btoa: reference/btoa is present and its oracle will not "
              "build, so nothing here is graded against the format's own "
              "implementation.")
        for line in why.splitlines():
            print("run_btoa:   " + line)
        print("run_btoa: fix the build, or delete reference/btoa to make "
              "this a skip.")
        return 1

    problems = []
    ran = 0
    tmp = tempfile.mkdtemp()
    try:
        data = subjects()
        for name, content in sorted(data.items()):
            src = os.path.join(tmp, name)
            open(src, "wb").write(content)
            for label, flags in (("v5", []), ("v4", ["-o"])):
                enc = os.path.join(tmp, "%s.%s.btoa" % (name, label))
                with open(enc, "wb") as f:
                    r = subprocess.run([BIN] + flags + [src], stdout=f,
                                       stderr=subprocess.DEVNULL)
                if r.returncode != 0 or os.path.getsize(enc) == 0:
                    problems.append("%s %s: the reference would not encode it"
                                    % (name, label))
                    continue
                out = tempfile.mkdtemp()
                try:
                    subprocess.run([macextract, "x", "-o", out, enc],
                                   capture_output=True)
                    got = sorted(os.listdir(out))
                    if len(got) != 1:
                        problems.append("%s %s: wrote %r" % (name, label, got))
                    elif open(os.path.join(out, got[0]), "rb").read() != content:
                        problems.append("%s %s: bytes differ" % (name, label))
                finally:
                    shutil.rmtree(out, ignore_errors=True)
                ran += 1

        # Version 5 names the file inside the archive; version 4 does
        # not, and the host's hint (the archive's own name) is what the
        # entry is called instead — the gzip rule.
        enc = os.path.join(tmp, "text.txt.v5.btoa")
        out = tempfile.mkdtemp()
        subprocess.run([macextract, "x", "-o", out, enc], capture_output=True)
        if os.listdir(out) != ["text.txt"]:
            problems.append("v5: the header's name was not used (%r)"
                            % os.listdir(out))
        shutil.rmtree(out, ignore_errors=True)
        ran += 1

        # Line endings. The reference writes LF, but the machine this
        # decoder is FOR writes CR and nothing else, and a btoa file that
        # reached a Mac and was saved by a Mac text editor comes back
        # that way. Skipping CR instead of ending the line on it turned
        # such a file into one enormous line, silently (fixed 2026-08-23);
        # nothing else in the suite could see it, because everything else
        # here is written by a Unix program.
        for label, term in (("cr", b"\r"), ("crlf", b"\r\n")):
            for ver in ("v5", "v4"):
                src = open(os.path.join(tmp, "odd1.bin.%s.btoa" % ver),
                           "rb").read()
                enc = os.path.join(tmp, "eol.%s.%s.btoa" % (ver, label))
                open(enc, "wb").write(src.replace(b"\n", term))
                out = tempfile.mkdtemp()
                subprocess.run([macextract, "x", "-o", out, enc],
                               capture_output=True)
                got = sorted(os.listdir(out))
                if len(got) != 1 or open(os.path.join(out, got[0]),
                                         "rb").read() != data["odd1.bin"]:
                    problems.append("%s line endings, %s: %r"
                                    % (label.upper(), ver, got))
                shutil.rmtree(out, ignore_errors=True)
                ran += 1

        # In front of a mail header, which is how these travelled.
        mail = os.path.join(tmp, "mail.btoa")
        with open(mail, "wb") as f:
            f.write(b"From: nobody\nSubject: here it is\n\n")
            f.write(open(os.path.join(tmp, "odd1.bin.v5.btoa"), "rb").read())
        out = tempfile.mkdtemp()
        subprocess.run([macextract, "x", "-o", out, mail], capture_output=True)
        got = sorted(os.listdir(out))
        if len(got) != 1 or open(os.path.join(out, got[0]), "rb").read() \
                != data["odd1.bin"]:
            problems.append("mail-wrapped: %r" % got)
        shutil.rmtree(out, ignore_errors=True)
        ran += 1

        # THE SHAPE A REAL ONE HAS. Aladdin's own translator
        # MacBinary-wraps before it encodes, so a btoa file off a Mac is
        # `Subject.MBin.ascii` — armour around a wrapper (FORMATS.md,
        # *btoa*). Both layers always read; until 2026-08-27 the CHAIN
        # did not, because btoa was not an envelope. Both framings, since
        # the Macintosh one is the older `xbtoa Begin`.
        inner = b"payload that travelled as MacBinary inside armour\n" * 7
        wrapped = os.path.join(tmp, "Subject.MBin")
        open(wrapped, "wb").write(macbinary("Subject", inner))
        for label, flags in (("v5", []), ("v4", ["-o"])):
            # Each in its own directory so the file can carry the name
            # the specimen carries: the v4 framing has no name of its
            # own, and the entry is then called after the archive.
            d = os.path.join(tmp, "chain-" + label)
            os.mkdir(d)
            enc = os.path.join(d, "Subject.MBin.ascii")
            with open(enc, "wb") as f:
                subprocess.run([BIN] + flags + [wrapped], stdout=f,
                               stderr=subprocess.DEVNULL)
            out = tempfile.mkdtemp()
            subprocess.run([macextract, "x", "-o", out, enc],
                           capture_output=True)
            got = sorted(os.listdir(out))
            if got != ["Subject"]:
                # A leftover here is the MacBinary layer: unwrapped but
                # not deleted, or not unwrapped at all.
                problems.append("chained %s: wrote %r, wanted the file "
                                "inside the wrapper alone" % (label, got))
            elif open(os.path.join(out, "Subject"), "rb").read() != inner:
                problems.append("chained %s: bytes differ" % label)
            shutil.rmtree(out, ignore_errors=True)
            ran += 1

        # And -nr still stops at the wrapper, which is what says the
        # chain is the recursion rather than something the decoder does.
        enc = os.path.join(tmp, "chain-v4", "Subject.MBin.ascii")
        out = tempfile.mkdtemp()
        subprocess.run([macextract, "x", "-nr", "-o", out, enc],
                       capture_output=True)
        if sorted(os.listdir(out)) != ["Subject.MBin"]:
            problems.append("-nr: %r" % sorted(os.listdir(out)))
        shutil.rmtree(out, ignore_errors=True)
        ran += 1

        # And the two ways it must FAIL. A flipped character has to be
        # an error, not 25% of a file: btoa carries a checksum per line
        # and three over the whole stream.
        good = open(os.path.join(tmp, "all256.bin.v5.btoa"), "rb").read()
        bad = bytearray(good)
        i = len(bad) // 2
        bad[i] = ord("#") if bad[i] != ord("#") else ord("!")
        broken = os.path.join(tmp, "broken.btoa")
        open(broken, "wb").write(bytes(bad))
        if subprocess.run([macextract, "t", broken],
                          capture_output=True).returncode == 0:
            problems.append("a flipped character was accepted")
        ran += 1

        cut = os.path.join(tmp, "cut.btoa")
        open(cut, "wb").write(good[:len(good) // 2])
        if subprocess.run([macextract, "t", cut],
                          capture_output=True).returncode == 0:
            problems.append("a truncated archive was accepted")
        ran += 1

        # The End line's R field, in the width a 32-BIT machine writes.
        # `Crot` is a `long` in btoa.c and the rotate assumes that is 32
        # bits, so this reference — built here on LP64 — prints sixteen
        # hex digits where every machine the format was written for
        # printed eight. The low 32 bits are the same value either way
        # (the carry the rotate adds does not depend on the bits above
        # 31), and the Macintosh specimen `sitcrypt.py --btoa-send`
        # produced is in the eight-digit form. So both are decoded, and
        # a wrong eight-digit R is still an error: without this the
        # suite could only ever see the form its own reference emits.
        for ver in ("v5", "v4"):
            src = open(os.path.join(tmp, "odd1.bin.%s.btoa" % ver),
                       "rb").read()
            lines = src.split(b"\n")
            end = max(i for i, ln in enumerate(lines) if ln.startswith(b"x"))
            fields = lines[end].split()
            if len(fields) < 11 or len(fields[10]) <= 8:
                continue                       # already the narrow form
            for label, tail in (("32bit", fields[10][-8:]),
                                ("32bit-wrong", b"%08x"
                                 % ((int(fields[10][-8:], 16) ^ 1)))):
                lines[end] = b" ".join(fields[:10] + [tail])
                enc = os.path.join(tmp, "rot.%s.%s.btoa" % (ver, label))
                open(enc, "wb").write(b"\n".join(lines))
                bad = subprocess.run([macextract, "t", enc],
                                     capture_output=True).returncode != 0
                if bad != label.endswith("wrong"):
                    problems.append("R in the 32-bit width, %s, %s: %s"
                                    % (ver, label,
                                       "refused" if bad else "accepted"))
                ran += 1

        # Prose that happens to contain the marker is not an archive.
        prose = os.path.join(tmp, "prose.txt")
        open(prose, "wb").write(b"this mentions xbtoa but not at a line "
                                b"start, so it is not one\n")
        r = subprocess.run([macextract, "sniff", prose], capture_output=True)
        if b"btoa" in r.stdout:
            problems.append("prose containing the marker was claimed")
        ran += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("run_btoa: " + p)
    print("btoa: %d case(s) checked, %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

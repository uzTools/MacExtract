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


def build():
    """Compile the reference. It is 1996 K&R C, so the warnings are
    switched off rather than fixed: this is somebody else's source and
    `reference/` is read-only."""
    if os.path.exists(BIN):
        return True
    if not os.path.isdir(SRC):
        return False
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    r = subprocess.run(["gcc", "-w", "-O1", "-std=gnu89", "-o", BIN,
                        os.path.join(SRC, "btoa.c"),
                        os.path.join(SRC, "atob.c"),
                        os.path.join(SRC, "repair.c")],
                       capture_output=True)
    return r.returncode == 0 and os.path.exists(BIN)


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
    unclassic = os.path.join(ROOT, "build", "unclassic")
    args = sys.argv[1:]
    if "--unclassic" in args:
        unclassic = args[args.index("--unclassic") + 1]
    if not os.path.exists(unclassic):
        print("run_btoa: no CLI at %s" % unclassic)
        return 1
    if not build():
        print("run_btoa: SKIPPED — no reference/btoa (tools/fetch_references.sh)")
        return 0

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
                    subprocess.run([unclassic, "x", "-o", out, enc],
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
        subprocess.run([unclassic, "x", "-o", out, enc], capture_output=True)
        if os.listdir(out) != ["text.txt"]:
            problems.append("v5: the header's name was not used (%r)"
                            % os.listdir(out))
        shutil.rmtree(out, ignore_errors=True)
        ran += 1

        # In front of a mail header, which is how these travelled.
        mail = os.path.join(tmp, "mail.btoa")
        with open(mail, "wb") as f:
            f.write(b"From: nobody\nSubject: here it is\n\n")
            f.write(open(os.path.join(tmp, "odd1.bin.v5.btoa"), "rb").read())
        out = tempfile.mkdtemp()
        subprocess.run([unclassic, "x", "-o", out, mail], capture_output=True)
        got = sorted(os.listdir(out))
        if len(got) != 1 or open(os.path.join(out, got[0]), "rb").read() \
                != data["odd1.bin"]:
            problems.append("mail-wrapped: %r" % got)
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
        if subprocess.run([unclassic, "t", broken],
                          capture_output=True).returncode == 0:
            problems.append("a flipped character was accepted")
        ran += 1

        cut = os.path.join(tmp, "cut.btoa")
        open(cut, "wb").write(good[:len(good) // 2])
        if subprocess.run([unclassic, "t", cut],
                          capture_output=True).returncode == 0:
            problems.append("a truncated archive was accepted")
        ran += 1

        # Prose that happens to contain the marker is not an archive.
        prose = os.path.join(tmp, "prose.txt")
        open(prose, "wb").write(b"this mentions xbtoa but not at a line "
                                b"start, so it is not one\n")
        r = subprocess.run([unclassic, "sniff", prose], capture_output=True)
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

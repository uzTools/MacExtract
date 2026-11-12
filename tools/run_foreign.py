#!/usr/bin/env python3
"""run_foreign.py — archives this engine does not have are not archives.

Until 2026-10-18 the engine NAMED sixteen formats it never extracted —
StuffIt X, RAR, RAR 5, 7-Zip, xz, bzip2, Microsoft Cabinet, Zoo, ar,
cpio, ARJ, Zstandard, lzip, lrzip, WIM and Apple Archive — and their
probes ran ahead of MacBinary's CRC and every weaker test, so no other
reader was ever asked about one. The recognition is gone (DECISIONS.md
2026-10-18, *the formats it only named*); what this keeps is the safety
it gave. Every specimen below must:

- sniff as `unknown`, and
- make `macextract x` exit non-zero, say "format not recognized" — what
  it says for any file it does not know — and write nothing at all.

A specimen is only worth something if it IS an archive of that family,
so each one is graded by an implementation that is not ours first:

1. **Real archives, written here** — bzip2, xz, 7z, WIM (p7zip writes
   it), cpio in its three header shapes, ar — and each OPENED by p7zip.
2. **Apple Archive**, in the four shapes libNeoAppleArchive writes and
   reads back.
3. **Synthetic headers, identified by deark** — StuffIt X, RAR 1.3, RAR
   1.5-4 and RAR 5, Cabinet, Zoo, ARJ, lzip — which nothing here writes.
   If deark does not call it that format, the case fails: it would prove
   nothing.
4. **Zstandard (both frame kinds) and lrzip, on the signature alone**:
   no writer and no deark module here. The magics are RFC 8878's
   (reference/notes/zstd_rfc8878.txt) and lrzip.c's.

Then the corpus: every fixture with a manifest must sniff as the format
its manifest's oracle names (run_diff.py's IMPLEMENTED map), every other
fixture as SOMETHING, and the one deliberate non-archive,
`synth-os9-rar.rar` (a RAR, written for the Mac OS 9 tier's refusal),
must pass the same contract as the specimens.

What it CANNOT see: a reader that claims a real archive of one of these
families whose head differs from every specimen here — a self-extracting
.exe, a RAR with a comment block first, a multi-volume part. None is in
the corpus either.

Skips cases whose tool is missing, by name.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import run_diff  # noqa: E402  (IMPLEMENTED: the oracle's names -> ours)

# What the CLI prints for a file it does not know (cli/main.c).
NOT_RECOGNIZED = "format not recognized"

# Fixtures that are not archives on purpose, and must stay that way.
NOT_ARCHIVES = ("synth-os9-rar.rar",)


def build(script, binary):
    path = os.path.abspath(os.path.join(ROOT, binary))
    if os.path.exists(path):
        return path
    r = subprocess.run(["sh", os.path.join(ROOT, "tools", script)],
                       capture_output=True)
    return path if r.returncode == 0 and os.path.exists(path) else None


def sniff(macextract, path):
    return subprocess.run([macextract, "sniff", path], capture_output=True,
                          text=True).stdout.strip()


def deark_says(deark, path):
    """deark's module name, and everything `-l` printed."""
    r = subprocess.run([deark, "-l", path], capture_output=True, text=True)
    text = r.stdout + r.stderr
    for line in text.split("\n"):
        if line.startswith("Module: "):
            return line[len("Module: "):].strip(), text
    return "", text


def sevenzip_opens(path):
    """p7zip parses the file as an archive — not just recognises it."""
    if not shutil.which("7z"):
        return None
    r = subprocess.run(["7z", "l", path], capture_output=True)
    return r.returncode == 0


def write_real(tmp):
    """Archives written by the format's own tool. Returns {path: family}."""
    subject = os.path.join(tmp, "a.txt")
    open(subject, "w").write("hello from a foreign archive\n" * 8)
    out = {}

    def run(argv, dest, stdout=False):
        with open(dest, "wb") if stdout else open(os.devnull, "wb") as fh:
            r = subprocess.run(argv, stdout=fh, stderr=subprocess.DEVNULL,
                               cwd=tmp)
        return r.returncode == 0 and os.path.exists(dest) and \
            os.path.getsize(dest) > 0

    if shutil.which("bzip2"):
        p = os.path.join(tmp, "t.bz2")
        if run(["bzip2", "-kc", subject], p, stdout=True):
            out[p] = "bzip2"
    if shutil.which("xz"):
        p = os.path.join(tmp, "t.xz")
        if run(["xz", "-kc", subject], p, stdout=True):
            out[p] = "xz"
    if shutil.which("7z"):
        p = os.path.join(tmp, "t.7z")
        if run(["7z", "a", "-bso0", "-bsp0", p, subject], p):
            out[p] = "7-Zip"
        p = os.path.join(tmp, "t.wim")
        if run(["7z", "a", "-twim", "-bso0", "-bsp0", p, subject], p):
            out[p] = "WIM"
    if shutil.which("cpio"):
        for fmt, name in (("newc", "t.newc.cpio"), ("odc", "t.odc.cpio"),
                          ("bin", "t.bin.cpio")):
            p = os.path.join(tmp, name)
            with open(p, "wb") as fh:
                r = subprocess.run(["cpio", "-o", "--format=" + fmt],
                                   input=b"a.txt\n", stdout=fh,
                                   stderr=subprocess.DEVNULL, cwd=tmp)
            if r.returncode == 0 and os.path.getsize(p) > 0:
                out[p] = "cpio"
    if shutil.which("ar"):
        p = os.path.join(tmp, "t.a")
        if run(["ar", "rc", p, subject], p):
            out[p] = "ar"
    return out


def zoo_header():
    """A Zoo archive header: the four bytes at 0x14 are deark's whole
    identify test. Source: reference/deark/modules/zoo.c
    (de_identify_zoo)."""
    h = bytearray(0x22)
    h[0:20] = b"ZOO 2.10 Archive.\x1a\x00\x00"
    h[0x14:0x18] = b"\xdc\xa7\xc4\xfd"
    return bytes(h) + bytes(64)


def arj_header():
    """An ARJ basic header: 0x60 0xEA, the header size, the header, and
    its CRC-32. Source: reference/deark/modules/arj.c."""
    hdr = bytes([34, 11, 1, 1, 2]) + bytes(29)
    crc = zlib.crc32(hdr) & 0xFFFFFFFF
    return b"\x60\xea" + struct.pack("<H", len(hdr)) + hdr + \
        struct.pack("<I", crc) + bytes(8)


# name: (bytes, deark's module, a phrase its -l must print, or None).
# Sources: reference/deark/modules/rar.c (all three RAR signatures),
# unsupported.c (StuffIt X, lzip), cab.c, zoo.c, arj.c.
DEARK_GRADED = {
    "s.sitx":  (b"StuffIt!" + bytes(64), "unsupported", "StuffIt X"),
    "s2.sitx": (b"StuffIt?" + bytes(64), "unsupported", "StuffIt X"),
    "s.rar":   (b"Rar!\x1a\x07\x00" + bytes(64), "rar", None),
    "s.rar5":  (b"Rar!\x1a\x07\x01\x00" + bytes(64), "rar", None),
    "s.rar13": (b"RE~^" + bytes(64), "rar", None),
    "s.cab":   (b"MSCF" + bytes(60), "cab", None),
    "s.zoo":   (zoo_header(), "zoo", None),
    "s.arj":   (arj_header(), "arj", None),
    "s.lz":    (b"LZIP\x01\x0c" + bytes(64), "unsupported", "lzip"),
}

# Signature only. Source: reference/notes/zstd_rfc8878.txt 3.1.1 (the
# frame magic) and 3.1.2 (0x184D2A50..5F, a skippable frame), both
# little-endian; reference/lrzip/lrzip.c, write_magic (MAGIC_LEN 24).
SIGNATURE_ONLY = {
    "s.zst":      b"\x28\xb5\x2f\xfd" + bytes(64),
    "skip.zst":   b"\x50\x2a\x4d\x18" + bytes(64),
    "skip5f.zst": b"\x5f\x2a\x4d\x18" + bytes(64),
    "s.lrz":      b"LRZI\x00\x06" + bytes(64),
}


def main():
    macextract = os.path.join(ROOT, "build", "macextract")
    args = sys.argv[1:]
    if "--macextract" in args:
        macextract = args[args.index("--macextract") + 1]
    if not os.path.exists(macextract):
        print("run_foreign: no CLI at %s" % macextract)
        return 1

    deark = build("build_deark.sh", "build/deark/deark")
    problems, ran, skipped = [], 0, []
    scratch = os.path.join(ROOT, ".tmp")
    tmp = tempfile.mkdtemp(dir=scratch if os.path.isdir(scratch) else None)

    def check(label, cond, detail=""):
        nonlocal ran
        ran += 1
        if not cond:
            problems.append("%s: %s" % (label, detail or "failed"))

    def not_an_archive(label, path):
        """The whole contract: unknown to sniff, and x writes nothing."""
        got = sniff(macextract, path)
        check("%s sniffs as unknown" % label, got == "unknown",
              "claimed as %r" % got)
        out = os.path.join(tmp, "out")
        os.mkdir(out)
        try:
            r = subprocess.run([macextract, "x", "-o", out, path],
                               capture_output=True, text=True)
            wrote = sorted(os.listdir(out))
        finally:
            shutil.rmtree(out, ignore_errors=True)
        check("%s refused" % label,
              r.returncode != 0 and NOT_RECOGNIZED in r.stderr,
              "exit %d, said %r" % (r.returncode, r.stderr.strip()[:80]))
        check("%s writes nothing" % label, not wrote,
              "wrote %s" % ", ".join(wrote[:5]))

    try:
        # 1. Real archives, confirmed to be archives by p7zip.
        real = write_real(tmp)
        for want in ("bzip2", "xz", "7-Zip", "WIM", "cpio", "ar"):
            if want not in real.values():
                skipped.append("%s (no writer here)" % want)
        for path, family in sorted(real.items()):
            base = os.path.basename(path)
            check("%s (%s) opens in p7zip" % (base, family),
                  sevenzip_opens(path) is not False,
                  "p7zip cannot parse the subject, so it proves nothing")
            not_an_archive("%s, a %s written by its own tool"
                           % (base, family), path)

        # 2. Apple Archive, in all four shapes it is written in.
        neoaa = build("build_neoaa.sh", "build/neoaa/neoaa_write")
        if neoaa:
            src = os.path.join(tmp, "aarsrc")
            os.mkdir(src)
            open(os.path.join(src, "a.txt"), "w").write("hello\n" * 8)
            for algo in ("raw", "lzfse", "zlib", "lzbitmap"):
                p = os.path.join(tmp, "t.%s.aar" % algo)
                r = subprocess.run([neoaa, src, p, algo], capture_output=True)
                if r.returncode != 0:
                    skipped.append("Apple Archive %s (writer failed: %s)"
                                   % (algo, r.stderr.decode().strip()[:60]))
                    continue
                not_an_archive("t.%s.aar, written and re-read by "
                               "libNeoAppleArchive" % algo, p)
        else:
            skipped.append("Apple Archive (libNeoAppleArchive not built)")

        # 3. Synthetic headers, graded by deark.
        for name, (data, module, phrase) in sorted(DEARK_GRADED.items()):
            p = os.path.join(tmp, name)
            open(p, "wb").write(data)
            if deark:
                mod, text = deark_says(deark, p)
                check("%s (deark)" % name,
                      mod == module and (phrase is None or phrase in text),
                      "deark says %r, not %r%s" % (
                          mod, module,
                          "" if phrase is None else " naming " + phrase))
            else:
                skipped.append("deark grading of %s" % name)
            not_an_archive(name, p)

        # 4. Signature only, and said so in the docstring.
        for name, data in sorted(SIGNATURE_ONLY.items()):
            p = os.path.join(tmp, name)
            open(p, "wb").write(data)
            not_an_archive(name, p)

        # 5. The corpus: no fixture changes format, and the one that is
        # not an archive on purpose stays one that is not.
        fixtures = os.path.join(ROOT, "fixtures")
        mandir = os.path.join(fixtures, "manifests")
        want = {}
        for mf in sorted(os.listdir(mandir)) if os.path.isdir(mandir) else []:
            if mf.endswith(".json"):
                man = json.load(open(os.path.join(mandir, mf)))
                want[man["fixture"]] = man.get("format")
        moved, lost, seen = [], [], 0
        for name in sorted(os.listdir(fixtures)) if os.path.isdir(fixtures) \
                else []:
            p = os.path.join(fixtures, name)
            if not os.path.isfile(p) or name.endswith(".md"):
                continue
            if name in NOT_ARCHIVES:
                not_an_archive("the corpus's deliberate non-archive %s"
                               % name, p)
                continue
            seen += 1
            got = sniff(macextract, p)
            if name in want:
                ours = run_diff.IMPLEMENTED.get(want[name])
                if got != ours:
                    moved.append("%s (%s, the oracle's %s)"
                                 % (name, got, want[name]))
            elif got == "unknown":
                lost.append(name)
        if seen:
            check("corpus sweep (%d fixtures): every manifest's format"
                  % seen, not moved,
                  "sniffed otherwise: %s" % ", ".join(moved[:5]))
            check("corpus sweep: no unmanifested fixture lost its format",
                  not lost, "unknown: %s" % ", ".join(lost[:5]))
        else:
            skipped.append("corpus sweep (no fixtures)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for s in skipped:
        print("run_foreign: skipped %s" % s)
    for p in problems:
        print("run_foreign: %s" % p, file=sys.stderr)
    if problems:
        print("run_foreign: FAILED (%d of %d)" % (len(problems), ran),
              file=sys.stderr)
        return 1
    print("run_foreign: ok (%d checks)" % ran)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""run_foreign.py — the archives this engine names but never extracts.

`src/fmt_foreign.c` is nothing but signatures, so the whole test is: the
right name for an archive, no name for anything else, and a clean refusal
either way. Three kinds of case, and they differ in how much they prove:

1. **Real archives, written here** — bzip2, xz, 7z, cpio in its three
   header shapes, ar. Each is written by that format's own tool and then
   OPENED by p7zip, so the subject is known to be a real archive of that
   family before our probe is asked about it.
2. **Synthetic headers, identified by deark** — Zoo, ARJ and Cabinet,
   which nothing here writes. deark has a module for each, so the header
   this builds is graded by an implementation that is not ours; if deark
   does not call it a `zoo`, it is not a zoo and the case is worthless.
3. **RAR and RAR 5, on the signature alone.** No writer here, no deark
   module, and p7zip will not identify a stub it cannot parse. What
   grades those two is `reference/XADMaster` (the constants) plus a
   one-off run against real archives out of libarchive's test suite
   (FORMATS.md, *Archives named but not extracted*) — not repeated here,
   because ci.sh does not use the network.

Then the negatives, which is where a signature file earns its keep: each
corroborating field is spoiled in turn, and the whole fixture corpus is
swept, since naming a Macintosh archive as a PC one would be worse than
not naming it at all.

Skips cases whose tool is missing, by name.
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def build(script, binary):
    path = os.path.abspath(os.path.join(ROOT, binary))
    if os.path.exists(path):
        return path
    r = subprocess.run(["sh", os.path.join(ROOT, "tools", script)],
                       capture_output=True)
    return path if r.returncode == 0 and os.path.exists(path) else None


def sniff(unclassic, path):
    return subprocess.run([unclassic, "sniff", path], capture_output=True,
                          text=True).stdout.strip()


def deark_module(deark, path):
    r = subprocess.run([deark, "-l", path], capture_output=True, text=True)
    for line in r.stdout.split("\n"):
        if line.startswith("Module: "):
            return line[len("Module: "):].strip()
    return ""


def sevenzip_opens(path):
    """p7zip parses the file as an archive — not just recognises it."""
    if not shutil.which("7z"):
        return None
    r = subprocess.run(["7z", "l", path], capture_output=True)
    return r.returncode == 0


def write_real(tmp):
    """Archives written by the format's own tool. Returns {path: name}."""
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
            out[p] = "ar archive"
    return out


def zoo_header():
    """A Zoo archive header. The magic is the four bytes at 0x14, which is
    deark's whole identify test and XADMaster's.
    Source: reference/deark/modules/zoo.c (de_identify_zoo),
    XADMaster/XADZooParser.m."""
    h = bytearray(0x22)
    h[0:20] = b"ZOO 2.10 Archive.\x1a\x00\x00"
    h[0x14:0x18] = b"\xdc\xa7\xc4\xfd"
    return bytes(h) + bytes(64)


def arj_header(size=34, crc_ok=True):
    """An ARJ basic header: 0x60 0xEA, the header size, the header, and
    its CRC-32. Source: XADMaster/XADARJParser.m for the CRC test,
    reference/deark/modules/arj.c for the size bounds."""
    hdr = bytes([34, 11, 1, 1, 2]) + bytes(size - 5)
    crc = zlib.crc32(hdr) & 0xFFFFFFFF
    if not crc_ok:
        crc ^= 0xFFFF
    return b"\x60\xea" + struct.pack("<H", len(hdr)) + hdr + \
        struct.pack("<I", crc) + bytes(8)


def main():
    unclassic = os.path.join(ROOT, "build", "unclassic")
    args = sys.argv[1:]
    if "--unclassic" in args:
        unclassic = args[args.index("--unclassic") + 1]
    if not os.path.exists(unclassic):
        print("run_foreign: no CLI at %s" % unclassic)
        return 1

    deark = build("build_deark.sh", "build/deark/deark")
    problems, ran, skipped = [], 0, []
    tmp = tempfile.mkdtemp()

    def check(label, cond, detail=""):
        nonlocal ran
        ran += 1
        if not cond:
            problems.append("%s: %s" % (label, detail or "failed"))

    def named(label, path, want):
        got = sniff(unclassic, path)
        check(label, got == want, "sniffed as %r, wanted %r" % (got, want))

    def unnamed(label, data):
        p = os.path.join(tmp, "neg.bin")
        open(p, "wb").write(data)
        got = sniff(unclassic, p)
        check(label, got == "unknown", "claimed as %r" % got)

    try:
        # 1. Real archives, confirmed to be archives by p7zip.
        real = write_real(tmp)
        for want in ("bzip2", "xz", "7-Zip", "cpio", "ar archive"):
            if want not in real.values():
                skipped.append("%s (no writer here)" % want)
        for path, want in sorted(real.items()):
            base = os.path.basename(path)
            named("%s written by its own tool" % base, path, want)
            opens = sevenzip_opens(path)
            check("%s opens in p7zip" % base, opens is not False,
                  "p7zip cannot parse the subject, so it proves nothing")

        # ...and extraction is refused cleanly, with the name in the message.
        for path, want in sorted(real.items()):
            r = subprocess.run([unclassic, "x", "-o", tmp, path],
                               capture_output=True, text=True)
            check("%s refused by name" % os.path.basename(path),
                  r.returncode != 0 and want in r.stderr,
                  "said %r" % (r.stderr.strip()[:80]))
            break        # one is enough; the path is shared

        # 2. Synthetic headers, graded by deark.
        synth = {"s.zoo": (zoo_header(), "Zoo", "zoo"),
                 "s.arj": (arj_header(), "ARJ", "arj"),
                 "s.cab": (b"MSCF" + bytes(60), "Microsoft Cabinet", "cab")}
        for name, (data, want, module) in sorted(synth.items()):
            p = os.path.join(tmp, name)
            open(p, "wb").write(data)
            named(name, p, want)
            if deark:
                mod = deark_module(deark, p)
                check("%s (deark)" % name, mod == module,
                      "deark says %r, not %r" % (mod, module))
            else:
                skipped.append("deark grading of %s" % name)

        # 3. RAR and RAR 5: signature only, and said so in the docstring.
        for name, data, want in (
                ("s.rar", b"Rar!\x1a\x07\x00" + bytes(64), "RAR"),
                ("s.rar5", b"Rar!\x1a\x07\x01\x00" + bytes(64), "RAR 5"),
                ("s.rar13", b"RE~^" + bytes(64), "RAR")):
            p = os.path.join(tmp, name)
            open(p, "wb").write(data)
            named(name, p, want)

        # 4. The negatives: every corroborating field, one at a time.
        unnamed("RAR signature with the wrong eighth byte",
                b"Rar!\x1a\x07\x02" + bytes(64))
        unnamed("7-Zip signature with the wrong reserved byte",
                b"7z\xbc\xaf\x27\x1c\x01" + bytes(64))
        unnamed("xz signature with the wrong terminator",
                b"\xfd7zXZ\x01" + bytes(64))
        unnamed("bzip2 with neither block nor end-of-stream magic",
                b"BZh9" + bytes(64))
        unnamed("bzip2 with a level digit out of range",
                b"BZh0\x31\x41\x59\x26\x53\x59" + bytes(64))
        unnamed("Zoo magic at the wrong offset",
                b"\xdc\xa7\xc4\xfd" + bytes(64))
        unnamed("ARJ with a broken header CRC", arj_header(crc_ok=False))
        unnamed("ARJ with a header size out of range",
                b"\x60\xea" + struct.pack("<H", 3000) + bytes(64))
        unnamed("cpio-shaped digits that are not a magic", b"070703" + bytes(64))
        unnamed("ar without its terminating newline", b"!<arch>!" + bytes(64))

        # 5. The corpus: not one Macintosh archive is a foreign one.
        fixtures = os.path.join(ROOT, "fixtures")
        foreign = {"RAR", "RAR 5", "7-Zip", "xz", "bzip2",
                   "Microsoft Cabinet", "Zoo", "ar archive", "cpio", "ARJ"}
        claimed, seen = [], 0
        for name in sorted(os.listdir(fixtures)) if os.path.isdir(fixtures) \
                else []:
            p = os.path.join(fixtures, name)
            if not os.path.isfile(p) or name.endswith(".md"):
                continue
            seen += 1
            got = sniff(unclassic, p)
            if got in foreign:
                claimed.append("%s (%s)" % (name, got))
        if seen:
            check("corpus sweep (%d fixtures)" % seen, not claimed,
                  "claimed: %s" % ", ".join(claimed[:5]))
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

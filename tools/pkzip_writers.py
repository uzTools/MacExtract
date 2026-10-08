#!/usr/bin/env python3
"""pkzip_writers.py — what PKZIP 1.01, 1.02 and 1.10 themselves WRITE.

Runs the three PKZIP.EXE binaries, taken out of their own distributions
(`fixtures/pkz101.exe` and `tools/specimens/implode.tsv`'s PKZ102/PKZ110),
under a headless DOSBox, and reads back the central directory of what
they wrote. Three questions, all about PKWARE's programs rather than about any
reader of ours:

  1. **Which Implode flag combinations does each version write?** Every
     file of the three distributions, plus a few generated shapes, is
     zipped by each version, and each entry's dictionary size and tree
     count is tabulated. A combination where APPNOTE.TXT 5.3.4 and the
     1.01/1.02 minimum match length disagree (flags 0x0002 and 0x0004)
     is reported by name.
  2. **Does a later version restamp the records it did not write?**
     A 1.02 archive is updated by 1.10 with -a, -u and -f, a 1.10
     archive by 1.02 with -a, and PKZ101.EXE itself by 1.10 with -a;
     every record's *version made by* is printed. The last one is then
     extracted by `macextract` and compared with the files that went in.
  3. **Which minimum match length does each version READ by?** Each
     PKUNZIP.EXE tests PKZ101.EXE, PKZIP 1.10's output from step 1 and
     the six shapes `tools/synth_implode.py` writes. This is the only
     place the 1.01/1.02 rule is observable in a shipped program,
     because step 1 finds their writers never use a combination where
     it matters.

    tools/pak.py --setup                    # DOSBox, no root
    tools/fetch_specimens.py --only implode
    tools/pkzip_writers.py --macextract build/rel/macextract

Measured 2026-10-08: DECISIONS.md, *the key that survives and has nothing
to separate*.

WHAT IT CANNOT SEE. It runs the binaries that were SHIPPED, in one
emulator, with the switches their manuals document. It cannot reach the
build that wrote PKZ101.EXE's own three 4 K/three-tree entries, which
none of these three reproduces, nor whatever wrote the spec-1.1 MS-DOS
archives in the wild at those combinations (`CPUTEST.ZIP`, below in the
entry); those writers are not on this disk. A run that reports no
disagreeing combination is a fact about these three binaries on these
inputs, not about PKZIP. Step 3 cannot tell WHY PKUNZIP 1.01/1.02
refuse a generated stream: they refuse all six shapes, including the two
where both rules agree, so that column is not evidence about the minimum
match length (OPEN_ITEMS.md). It is not in `ci.sh`: DOSBox is not a
build dependency.
"""
import argparse
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pak  # noqa: E402

SHAPES = ["4k-2trees", "8k-3trees", "4k-3trees", "8k-2trees",
          "4k-3trees-mmlbug", "8k-2trees-mmlbug"]
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.expanduser("~/.cache/macextract/vmac/specimens/implode")
DISTS = {
    "101": os.path.join(REPO, "fixtures", "pkz101.exe"),
    "102": os.path.join(SPEC, "implode-PKZ102.exe"),
    "110": os.path.join(SPEC, "implode-PKZ110.exe"),
}


def central(path):
    """[(name, version made by, method, flags)] from the central directory.
    Source: APPNOTE.TXT 4.3.12 (central header) and 4.3.16 (end record)."""
    d = open(path, "rb").read()
    e = d.rfind(b"PK\x05\x06")
    n, _, off = struct.unpack("<HII", d[e + 10:e + 20])
    # A PKSFX 1.x self-extractor's offsets are relative to the zip, which
    # starts where the directory's own stated position says it should.
    base = e - struct.unpack("<I", d[e + 12:e + 16])[0] - off
    p, out = base + off, []
    for _ in range(n):
        vm, _, fl, meth = struct.unpack("<HHHH", d[p + 4:p + 12])
        nl, xl, cl = struct.unpack("<HHH", d[p + 28:p + 34])
        out.append((d[p + 46:p + 46 + nl].decode("latin-1"), vm, meth, fl))
        p += 46 + nl + xl + cl
    return out


def combo(meth, fl):
    if meth != 6:
        return "method %d" % meth
    k8, t3 = bool(fl & 2), bool(fl & 4)
    tag = "%s/%dT" % ("8K" if k8 else "4K", 3 if t3 else 2)
    return tag + (" DISAGREE" if k8 != t3 else "")


def dosbox(work, lines):
    """One DOSBox session, from a conf file. tools/pak.py finds the binary,
    root-less or not; its own `-c` runner hung here on these commands."""
    conf = os.path.join(work, "..", "dosbox.conf")
    with open(conf, "w") as f:
        f.write("[sdl]\noutput=surface\n[cpu]\ncycles=max\n[autoexec]\n")
        f.write("mount c %s\nc:\n" % work)
        for ln in lines:
            f.write(ln + "\n")
        f.write("exit\n")
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    lib = os.path.join(pak.ROOTFS, "usr", "lib", "x86_64-linux-gnu")
    if os.path.isdir(lib):
        env["LD_LIBRARY_PATH"] = lib
    subprocess.run([pak.dosbox_bin(), "-conf", conf, "-noconsole"], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=600, check=True)


def generated(r):
    """A few shapes the distributions do not hold: binary-heavy, long
    distance repeats, text in sizes either side of the 4 K/8 K split."""
    words = b"the quick brown fox jumps over lazy dog archive".split()
    out = {}
    for n in (1000, 3000, 6000, 20000, 100000):
        s = b""
        while len(s) < n:
            s += b" ".join(r.choice(words) for _ in range(12)) + b"\r\n"
        out["GT%d.DAT" % (n // 1000)] = s[:n]
        out["GB%d.DAT" % (n // 1000)] = bytes(
            r.choice([0, 0, 0, 1, 2, 255, r.randrange(256)]) for _ in range(n))
    blk = bytes(r.choice(b"abcdefgh") for _ in range(6000))
    out["GR6.DAT"] = (blk * 6)[:30000]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default=os.path.join(REPO, "build", "rel", "macextract"))
    a = ap.parse_args()
    if not pak.dosbox_bin():
        sys.exit("pkzip_writers: no dosbox; run tools/pak.py --setup")
    for v, p in DISTS.items():
        if not os.path.exists(p):
            sys.exit("pkzip_writers: %s missing (tools/fetch_specimens.py --only implode)" % p)

    top = tempfile.mkdtemp(prefix="pkzw-")
    work = os.path.join(top, "c")
    os.mkdir(work)
    inputs = {}
    for v, p in DISTS.items():
        d = os.path.join(top, "d" + v)
        subprocess.run([a.macextract, "x", "-o", d, p], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        shutil.copy(os.path.join(d, "PKZIP.EXE"), os.path.join(work, "PK%s.EXE" % v))
        for nm in sorted(os.listdir(d)):
            src = os.path.join(d, nm)
            if os.path.isfile(src) and not nm.endswith(".txt") and len(nm) <= 12:
                stem, _, ext = nm.partition(".")
                inputs["%s%s.%s" % (stem[:5], v, ext[:3] or "DAT")] = open(src, "rb").read()
    inputs.update(generated(random.Random(1)))
    os.mkdir(os.path.join(work, "IN"))
    for nm, data in inputs.items():
        open(os.path.join(work, "IN", nm), "wb").write(data)

    # 1. what each version writes over the same inputs
    dosbox(work, ["PK%s.EXE W%s.ZIP IN\\*.* > W%s.LOG" % (v, v, v) for v in DISTS])
    disagree = 0
    for v in DISTS:
        tally = {}
        for _, _, meth, fl in central(os.path.join(work, "W%s.ZIP" % v)):
            c = combo(meth, fl)
            tally[c] = tally.get(c, 0) + 1
            disagree += "DISAGREE" in c
        print("PKZIP %s over %d inputs: %s" % (
            v, len(inputs), ", ".join("%s %d" % kv for kv in sorted(tally.items()))))

    # 2. who restamps whom
    open(os.path.join(work, "ADD.TXT"), "wb").write(b"added by another version\r\n" * 200)
    shutil.copy(DISTS["101"], os.path.join(work, "MIX.ZIP"))
    dosbox(work, [
        "PK102.EXE A.ZIP IN\\GT1.DAT IN\\GT6.DAT IN\\GB3.DAT > A.LOG",
        "copy A.ZIP F.ZIP", "copy A.ZIP U.ZIP",
        "PK110.EXE -a A.ZIP ADD.TXT > A2.LOG",
        "PK110.EXE -u U.ZIP IN\\GT20.DAT > U.LOG",
        "PK110.EXE -f F.ZIP > F.LOG",
        "PK110.EXE B.ZIP IN\\GT1.DAT IN\\GB3.DAT > B.LOG",
        "PK102.EXE -a B.ZIP ADD.TXT > B2.LOG",
        "PK110.EXE -a MIX.ZIP ADD.TXT > M.LOG",
    ])
    for z, what in (("A", "1.02 archive, then 1.10 -a"), ("U", "1.02 archive, then 1.10 -u"),
                    ("F", "1.02 archive, then 1.10 -f"), ("B", "1.10 archive, then 1.02 -a"),
                    ("MIX", "PKZ101.EXE, then 1.10 -a")):
        recs = central(os.path.join(work, z + ".ZIP"))
        print("%s: %s" % (what, ", ".join(
            "%s 0x%04x %s" % (n, vm, combo(m, f)) for n, vm, m, f in recs
            if z != "MIX" or vm != 0x000a or "DISAGREE" in combo(m, f))))

    out = os.path.join(top, "mixout")
    rc = subprocess.run([a.macextract, "x", "-o", out, os.path.join(work, "MIX.ZIP")],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    same = sum(open(os.path.join(out, n), "rb").read() ==
               open(os.path.join(top, "d101", n), "rb").read()
               for n in ("README.DOC", "ORDER.DOC", "OMBUDSMN.ASP"))
    same += open(os.path.join(out, "ADD.TXT"), "rb").read() == \
        open(os.path.join(work, "ADD.TXT"), "rb").read()
    print("macextract on PKZ101.EXE + 1.10: exit %d, %d of 4 checked entries byte-exact"
          % (rc, same))
    print("disagreeing combinations written by the shipped binaries: %d" % disagree)

    # 3. what each version's READER does with the other readings. Our own
    # generator's streams go in too, with version-needed lowered to 1.0
    # (the only bytes touched) so PKUNZIP 1.0x does not refuse them unread.
    for v in DISTS:
        shutil.copy(os.path.join(top, "d" + v, "PKUNZIP.EXE"),
                    os.path.join(work, "PU%s.EXE" % v))
    for shape in SHAPES:
        z = os.path.join(work, "G%d.ZIP" % SHAPES.index(shape))
        subprocess.run([sys.executable, os.path.join(REPO, "tools", "synth_implode.py"),
                        "--only", shape, "-o", z], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        d = bytearray(open(z, "rb").read())
        for sig, at, val in ((b"PK\x03\x04", 4, b"\x0a\x00"),
                             (b"PK\x01\x02", 4, b"\x0a\x00\x0a\x00")):
            i = d.find(sig)
            while i >= 0:
                d[i + at:i + at + len(val)] = val
                i = d.find(sig, i + 1)
        open(z, "wb").write(d)
    subjects = [("MIX.ZIP", "PKZ101.EXE"), ("W110.ZIP", "PKZIP 1.10's output")] + \
        [("G%d.ZIP" % i, "synth " + sh) for i, sh in enumerate(SHAPES)]
    dosbox(work, ["PU%s.EXE -t %s > %s.T%s" % (v, z, z[:-4], v[2])
                  for z, _ in subjects for v in DISTS])
    for z, what in subjects:
        row = []
        for v in DISTS:
            log = open(os.path.join(work, "%s.T%s" % (z[:-4], v[2])), "rb").read()
            log = log.decode("latin-1")
            row.append("%s %d ok/%d bad" % (v, log.count(" OK"), log.count("fails CRC")))
        print("PKUNZIP on %s: %s" % (what, ", ".join(row)))
    shutil.rmtree(top)


if __name__ == "__main__":
    main()

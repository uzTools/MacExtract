#!/usr/bin/env python3
"""run_lz4.py — LZ4 frames (src/fmt_lz4.c), graded against liblz4.

    run_lz4.py [--macextract BIN]

Every frame here is written by the reference library, liblz4, through
tools/synth_lz4.py; the engine must give back exactly the bytes it was
handed. Skipped, and said so, where liblz4 is absent.

  1. The matrix: block maximum size 64K, 256K, 1M and 4M; linked and
     independent blocks; content checksum, block checksums and content
     size each on and off; compression levels 0, 9 and 12 — over payloads
     chosen to reach every path: a MAR archive, incompressible bytes (the
     library stores such blocks raw), long runs (matches reaching far back,
     lengths past 255), and a payload past 4 MB (several maximum blocks).
  2. Streams: two frames concatenated (their concatenation, as the `lz4`
     tool decodes them), a skippable frame between two, an empty frame.
  3. Damage, each with what must happen: the header checksum, a block
     checksum and the content checksum changed (refused), a compressed
     byte changed under a content checksum (refused), cuts at every 997th
     byte and in the last 16 (never exit 0), a reserved bit set (not LZ4),
     a dictionary id (refused, there is no dictionary), trailing garbage
     after the last frame (refused).
  4. Through to the MAR inside: a `.mar.lz4` extracts to the MAR's files.

And CONTROLS: the comparison against a payload changed in one byte must
fail; a frame whose content checksum is changed must be refused, which
also proves the checksum is checked.

**What it cannot see.** Every frame is liblz4's; no other encoder is here,
and mar 0.2.0's acceptance of these shapes was measured once on an
emulated Mac (DECISIONS.md 2026-11-03, *the frame mar 0.2.0 reads*). The
legacy frame, which mar does not read either. A frame with a dictionary,
beyond its refusal.
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import synth_lz4 as Z  # noqa: E402

FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("  FAIL", msg)


def payloads():
    rnd = random.Random(7)
    mar = open(os.path.join(ROOT, "fixtures", "synth-mar-tree.mar"), "rb").read()
    noise = bytes(rnd.getrandbits(8) for _ in range(150000))
    runs = bytearray()
    for i in range(400):
        runs += bytes([i & 0xFF]) * (rnd.randrange(1, 900))
        runs += b"abcdefgh" * rnd.randrange(1, 40)
    big = bytearray()
    while len(big) < 4_700_000:
        big += b"Macintosh %07d " % len(big) + bytes(rnd.getrandbits(8)
                                                       for _ in range(7))
    return {"mar": mar, "noise": noise, "runs": bytes(runs) * 3,
            "big": bytes(big)}


def decode(cli, work, blob, name="t.lz4"):
    """The engine's unwrapped bytes and its exit status."""
    p = os.path.join(work, name)
    with open(p, "wb") as f:
        f.write(blob)
    out = os.path.join(work, "out")
    shutil.rmtree(out, ignore_errors=True)
    r = subprocess.run([cli, "x", "-nr", "-o", out, p], capture_output=True)
    got = None
    if os.path.isdir(out):
        fs = [os.path.join(dp, f) for dp, _, fn in os.walk(out) for f in fn]
        if len(fs) == 1:
            got = open(fs[0], "rb").read()
    return r.returncode, got


def main():
    cli = os.path.join(ROOT, "build", "macextract")
    if "--macextract" in sys.argv:
        cli = sys.argv[sys.argv.index("--macextract") + 1]
    if Z.lib() is None:
        print("run_lz4: no liblz4 here — skipped, and that is a gap")
        return 0
    os.makedirs(os.path.join(ROOT, ".tmp"), exist_ok=True)
    work = tempfile.mkdtemp(dir=os.path.join(ROOT, ".tmp"), prefix="run_lz4.")
    try:
        return lanes(cli, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def lanes(cli, work):
    P = payloads()

    # 1. The matrix.
    n = 0
    for pname, data in P.items():
        for block in (4, 5, 6, 7):
            for linked in (False, True):
                for cc, bc, cs in ((False, False, False), (True, False, True),
                                   (True, True, False)):
                    for level in ((0, 12) if pname != "big" else (0,)):
                        if pname == "big" and (cc, bc) == (True, True) \
                                and block < 6:
                            continue
                        f = Z.frame(data, block, linked, cc, bc, cs, level)
                        rc, got = decode(cli, work, f)
                        if rc or got != data:
                            fail(f"{pname} block {block} linked {linked} "
                                 f"cc {cc} bc {bc} cs {cs} level {level}: "
                                 f"exit {rc}, {'same' if got == data else 'differs'}")
                        n += 1
    f = Z.frame(P["runs"], 4, True, True, False, False, 9)
    rc, got = decode(cli, work, f)
    if rc or got != P["runs"]:
        fail("runs at level 9")
    n += 1
    print(f"run_lz4: {n} liblz4 frames, every byte back")

    # 2. Streams.
    a, b = P["mar"], P["runs"]
    fa, fb = Z.frame(a, 4, True, True), Z.frame(b, 5, False, False, True)
    for label, blob, want in (
            ("two frames", fa + fb, a + b),
            ("a skippable frame between", fa + Z.skippable(b"user data" * 50, 7)
             + fb, a + b),
            ("an empty frame", Z.frame(b"", 4, True, True), b"")):
        rc, got = decode(cli, work, blob)
        if rc or got != want:
            fail(f"{label}: exit {rc}, {'same' if got == want else 'differs'}")
    print("run_lz4: concatenated, skippable and empty frames")

    # 3. Damage.
    base = Z.frame(P["mar"], 4, True, True, True, True)
    # The descriptor: magic 4, FLG, BD, content size 8, HC.
    hc = 4 + 2 + 8
    first_block = hc + 1
    bsize = int.from_bytes(base[first_block:first_block + 4], "little") \
        & 0x7FFFFFFF
    bsum = first_block + 4 + bsize
    cases = 0

    def must_fail(label, blob):
        nonlocal cases
        rc, _ = decode(cli, work, blob)
        if rc == 0:
            fail(f"{label}: exit 0")
        cases += 1

    def flip(blob, at, bit=1):
        b = bytearray(blob)
        b[at] ^= bit
        return bytes(b)
    must_fail("header checksum", flip(base, hc))
    must_fail("block checksum", flip(base, bsum))
    must_fail("content checksum", flip(base, len(base) - 1))
    must_fail("a compressed byte", flip(base, first_block + 4 + bsize // 2,
                                        0x20))
    for cut in list(range(5, len(base), 997)) + list(range(len(base) - 16,
                                                           len(base))):
        must_fail(f"cut at {cut}", base[:cut])
    must_fail("trailing garbage", base + b"not a frame")
    rd = flip(base, 4, 0x02)                         # FLG reserved bit
    p = os.path.join(work, "r.lz4")
    open(p, "wb").write(rd)
    if subprocess.run([cli, "sniff", p], capture_output=True).stdout.decode().strip() == "LZ4":
        fail("a reserved bit set: still sniffed as LZ4")
    cases += 1
    # A dictionary id: FLG bit 0, four bytes after the content size, the
    # header checksum recomputed by the generator's own digest of liblz4.
    nod = Z.frame(b"x" * 100, 4, True)
    flg = nod[4] | 0x01
    desc = bytes([flg, nod[5]]) + b"\x01\x02\x03\x04"
    import ctypes  # noqa: F401  (the checksum below is liblz4's own)
    L = Z.lib()
    L.XXH32.restype = ctypes.c_uint
    L.XXH32.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint]
    h = (L.XXH32(desc, len(desc), 0) >> 8) & 0xFF
    dict_frame = nod[:4] + desc + bytes([h]) + nod[7:]
    must_fail("a dictionary id", dict_frame)
    print(f"run_lz4: {cases} damaged, cut and foreign frames refused")

    # 4. Through to the MAR's files.
    p = os.path.join(work, "Top.mar.lz4")
    open(p, "wb").write(Z.frame(P["mar"], 4, True, True))
    out = os.path.join(work, "chain")
    r = subprocess.run([cli, "x", "-o", out, p], capture_output=True)
    files = sum(len(fn) for _, _, fn in os.walk(out))
    if r.returncode or files < 7:
        fail(f"the MAR inside: exit {r.returncode}, {files} files")
    print(f"run_lz4: a .mar.lz4 through to the MAR's {files} files")

    # Controls.
    rc, got = decode(cli, work, Z.frame(P["mar"], 4, True))
    bent = bytearray(P["mar"])
    bent[100] ^= 1
    if got == bytes(bent):
        fail("control: a payload one byte off compared equal")
    print("run_lz4: controls fail as they must")

    print(f"run_lz4: {'FAIL' if FAILS else 'OK'} — {len(FAILS)} problems")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

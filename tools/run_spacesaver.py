#!/usr/bin/env python3
"""run_spacesaver.py — the StuffIt SpaceSaver suite.

SpaceSaver has no oracle but itself: `unar` and `macunpack` do not know
the format, so there are no manifests and there is nothing in
`fixtures/`. What WOULD grade this reader is a file SpaceSaver itself
wrote under Mini vMac, decoded here and compared with the bytes that
went in — the arrangement DiskDoubler's and SuperDisk!'s specimens
already use. There is not one yet (OPEN_ITEMS.md), so what runs today
is the synthetic pass at the bottom of this file.

    tools/vmac/spacesaver.py --idlespec      make one (an emulator run)
    tools/run_spacesaver.py --macextract build/macextract

Specimens live outside the repository, beside the emulator's other
state, because they are what SpaceSaver made of a subject rather than
anything this project may distribute:

    ~/.cache/macextract/vmac/specimens/spacesaver/NAME.ss        the file
    ~/.cache/macextract/vmac/specimens/spacesaver/NAME.ss.orig   its input
    ~/.cache/macextract/vmac/specimens/spacesaver/PrAm-4048.bin  the preset

The preset dictionary is Aladdin's ('PrAm' -4048, 9,679 bytes) and is
NOT committed either; `tools/vmac/spacesaver.py --layout --keep` writes
a copy out of the installed control panel. Without it the decoder
refuses the entry rather than inventing bytes, which this suite also
checks.

Nothing here fails when the specimens are absent — it prints what it
skipped and returns 0, so a fresh clone stays green.
"""
import argparse
import glob
import os
import random
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "spacesaver")
PRESET = os.path.join(SPECIMENS, "PrAm-4048.bin")


def specimens():
    """Every `.ss` that really is one.

    The harness writes anything a run CHANGED, and one of SpaceSaver's
    rename rules writes a StuffIt archive — which is not a specimen of
    this format and must not be graded as one."""
    out = []
    for p in sorted(glob.glob(os.path.join(SPECIMENS, "*.ss"))):
        with open(p, "rb") as f:
            if f.read(8) == b"SIT!DFD3":
                out.append(p)
            else:
                print("spacesaver: %s is not a SpaceSaver file, skipped"
                      % os.path.basename(p))
    return out


def grade(exe, path, verbose):
    """Decode one specimen and compare it with the bytes that went in."""
    orig = path + ".orig"
    if not os.path.exists(orig):
        # Not gradeable, but still a file SpaceSaver wrote: decoding it
        # must at least SUCCEED. A specimen that only ever printed
        # "skipped" would be one nothing looked at.
        r = subprocess.run([exe, "t"] +
                           (["--preset", PRESET] if os.path.exists(PRESET)
                            else []) + [path],
                           capture_output=True, timeout=300)
        if r.returncode != 0:
            print("spacesaver: %s: decode FAILED (%s)"
                  % (os.path.basename(path),
                     r.stderr.decode("utf-8", "replace").strip()))
            return 1, 1
        print("spacesaver: %s: decodes, no .orig beside it — not graded"
              % os.path.basename(path))
        return 0, 1
    want = open(orig, "rb").read()
    args = [exe, "x", "-o", None, path]
    work = tempfile.mkdtemp(prefix="ssgrade-")
    bad = 0
    try:
        args[3] = work
        if os.path.exists(PRESET):
            args[4:4] = ["--preset", PRESET]
        r = subprocess.run(args, capture_output=True, timeout=300)
        # SpaceSaver replaces a file in place and adds no extension, so
        # the CLI keeps the WHOLE basename as the entry's name (cli/
        # main.c) — `.ss` and all. Stripping it here looked for a file
        # nothing writes, and no specimen had ever reached this line.
        name = os.path.basename(path)
        got = os.path.join(work, name)
        if r.returncode != 0 or not os.path.exists(got):
            print("spacesaver: %s: FAILED (%s)"
                  % (name, r.stderr.decode("utf-8", "replace").strip()))
            return 1, 1
        data = open(got, "rb").read()
        if data != want:
            print("spacesaver: %s: %d bytes out, %d in — DIFFERS"
                  % (name, len(data), len(want)))
            bad = 1
        elif verbose:
            print("spacesaver: %s: %d bytes, identical" % (name, len(data)))
        # The resource fork, when the subject had one.
        rorig = path + ".rsrc"
        if os.path.exists(rorig):
            side = got + ".rsrc"
            rwant = open(rorig, "rb").read()
            rgot = open(side, "rb").read() if os.path.exists(side) else b""
            if rgot != rwant:
                print("spacesaver: %s: resource fork DIFFERS (%d vs %d)"
                      % (name, len(rgot), len(rwant)))
                bad = 1
        return bad, 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


def m2_default_matches():
    """...and so must the eighteen bytes method 2 falls back on.

    They are `CMod 4`'s own tail, generated into `src/ss_dict.h` by the
    same tool. A dictionary entry that was never filled points at them
    (DECISIONS.md 2026-08-25, methods 1 and 2), so a stale copy decodes
    those matches to the wrong bytes and nothing else notices.
    """
    mod = os.path.join(SPECIMENS, "CMod4.bin")
    if not os.path.exists(mod):
        return 0
    want = open(mod, "rb").read()[-18:]
    text = open(os.path.join(REPO, "src", "ss_dict.h")).read()
    if "ss_m2_default[" not in text:
        print("spacesaver: src/ss_dict.h has no ss_m2_default — regenerate "
              "with tools/gen_ss_dict.py")
        return 1
    start = text.index("ss_m2_default[")
    body = text[text.index("{", start) + 1:text.index("};", start)]
    got = bytes(int(b, 16) for b in body.replace("\n", "").split(",")
                if b.strip())
    if got != want:
        print("spacesaver: ss_m2_default does not match `CMod 4`'s tail "
              "— regenerate with tools/gen_ss_dict.py")
        return 1
    return 0


def builtin_matches(exe):
    """The committed dictionary must be the one SpaceSaver actually has.

    `src/ss_dict.h` is generated from the `PrAm` resources of an
    installed SpaceSaver and then committed, so the build needs neither
    the emulator nor a copy of the software — and a generated file that
    is committed is a file that can go stale. This compares the header's
    bytes with the resource, whenever the resource is present.
    """
    if not os.path.exists(PRESET):
        return 0
    want = open(PRESET, "rb").read()
    hdr = os.path.join(REPO, "src", "ss_dict.h")
    if not os.path.exists(hdr):
        print("spacesaver: no src/ss_dict.h")
        return 1
    text = open(hdr).read()
    start = text.index("ss_dict0[")
    body = text[text.index("{", start) + 1:text.index("};", start)]
    got = bytes(int(b, 16) for b in body.replace("\n", "").split(",")
                if b.strip())
    if got != want:
        where = ("%d bytes against %d" % (len(got), len(want))
                 if len(got) != len(want) else
                 "the same length, different bytes")
        print("spacesaver: src/ss_dict.h does not match the resource (%s) "
              "— regenerate with tools/gen_ss_dict.py" % where)
        return 1
    return 0


def robustness(exe, path, timeout):
    """Truncated and bit-flipped specimens must fail cleanly.

    `fuzz.py` and `run_robustness.py` both work from `fixtures/`, and no
    SpaceSaver file may be committed there, so without this the format
    would have no corrupted-input coverage at all. The format is FORCED
    rather than sniffed: a truncated header sniffs as *unknown* and the
    run would exit cleanly having parsed nothing.
    """
    blob = open(path, "rb").read()
    work = tempfile.mkdtemp(prefix="ssfuzz-")
    rng = random.Random(os.path.basename(path))
    bad = ran = 0
    try:
        cases = [("trunc%d" % int(f * 100), blob[:int(len(blob) * f)])
                 for f in (0.05, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 0.98,
                           0.995)]
        for i in range(48):
            b = bytearray(blob)
            for _ in range(rng.randint(1, 8)):
                b[rng.randrange(len(b))] ^= 1 << rng.randrange(8)
            cases.append(("flip%d" % i, bytes(b)))
        for tag, data in cases:
            p = os.path.join(work, tag)
            open(p, "wb").write(data)
            ran += 1
            args = [exe, "t", "-f", "StuffIt SpaceSaver",
                    "--budget", str(4 << 20)]
            if os.path.exists(PRESET):
                args += ["--preset", PRESET]
            try:
                r = subprocess.run(args + [p], capture_output=True,
                                   timeout=timeout)
            except subprocess.TimeoutExpired:
                print("spacesaver: %s: TIMEOUT" % tag)
                bad += 1
                continue
            if r.returncode < 0:
                print("spacesaver: %s: died with signal %d"
                      % (tag, -r.returncode))
                bad += 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return bad, ran



# ------------------------------------------------------------------
# A synthetic Alg 4 stream, encoded here from the disassembly
#
# The specimens are what grade this reader against SpaceSaver. This
# grades it against a SECOND implementation of the same reading — an
# encoder written from `CMod 21` @0x462 — over inputs the specimens do
# not reach: a window that wraps, several blocks, and a preset
# dictionary that is actually referenced. Two implementations of one
# misreading would agree, so this is a consistency check and not an
# oracle; it is here because it is the only thing that exercises the
# wrap at all.
# ------------------------------------------------------------------

# 15, because that is what Aladdin's encoder writes: `CMod 20` @0xe24
# stores a literal 15 as the stream header's third byte, so a real file
# has a 32,768-byte window. The decoder reads the byte and accepts 1..16
# — the field is a byte and the decompressor honours it — so the suite
# runs both this and the ceiling.
WBITS = 15
MAXDIST = (1 << WBITS) - 1
MINLEN, MAXLEN = 4, 35
# 65,536 of OUTPUT per block: @0x8fc computes the block count as
# ceil(ulen / 65536) and @0xa02 reads that much input at a time.
BLOCK = 65536


class BitWriter:
    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def put(self, value, bits):
        for i in range(bits):
            self.acc |= ((value >> i) & 1) << self.n
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc)
                self.acc = 0
                self.n = 0

    def done(self):
        if self.n:
            self.out.append(self.acc)
        return bytes(self.out)


def encode_alg4(data, preset=b"", wbits=WBITS):
    """Greedy LZSS in SpaceSaver's shape: flag bit, then either 8 bits of
    literal or 5 bits of (length - 4) and WBITS bits of distance."""
    maxdist = (1 << wbits) - 1
    hist = preset[-maxdist:] if preset else b""
    base = len(hist)
    buf = bytearray(hist) + bytearray(data)
    index = {}
    for i in range(max(0, base - maxdist), base - 3):
        index.setdefault(bytes(buf[i:i + 4]), []).append(i)

    blocks = []
    pos = base
    end = len(buf)
    while pos < end:
        stop = min(end, pos + BLOCK)
        w = BitWriter()
        produced = 0
        while pos < stop:
            best_len, best_dist = 0, 0
            key = bytes(buf[pos:pos + 4])
            if len(key) == 4:
                for cand in reversed(index.get(key, [])[-24:]):
                    dist = pos - cand
                    if dist < 1 or dist > maxdist:
                        continue
                    n = 0
                    while (n < MAXLEN and pos + n < stop and
                           buf[cand + n] == buf[pos + n]):
                        n += 1
                    if n > best_len:
                        best_len, best_dist = n, dist
                        if n == MAXLEN:
                            break
            if best_len >= MINLEN:
                w.put(0, 1)
                w.put(best_len - MINLEN, 5)
                w.put(best_dist, wbits)
                take = best_len
            else:
                w.put(1, 1)
                w.put(buf[pos], 8)
                take = 1
            for k in range(take):
                if pos + k >= 3:
                    index.setdefault(bytes(buf[pos + k - 3:pos + k + 1]),
                                     []).append(pos + k - 3)
            pos += take
            produced += take
        blocks.append((w.done(), produced))

    out = bytearray()
    out += bytes([len(blocks) & 0xff, (len(blocks) >> 8) & 0xff, wbits])
    for payload, ulen in blocks:
        clen = len(payload) + 6
        out += bytes([clen & 0xff, (clen >> 8) & 0xff, (clen >> 16) & 0xff])
        out += bytes([ulen & 0xff, (ulen >> 8) & 0xff, (ulen >> 16) & 0xff])
        out += payload
    return bytes(out)


def container(dstream, dulen, rstream=b"", rulen=0, method=4):
    """The 84-byte header, version 3, with the data fork's stream first."""
    h = bytearray(84)
    h[0:4] = b"SIT!"
    h[4:8] = b"DFD3"
    h[8:12] = (3).to_bytes(4, "big")
    h[12:16] = (84).to_bytes(4, "big")
    h[16:20] = (0x41).to_bytes(4, "big")
    h[20:24] = len(dstream).to_bytes(4, "big")
    h[24:28] = dulen.to_bytes(4, "big")
    h[28:32] = (84).to_bytes(4, "big")
    h[33] = method if dulen else 0
    h[36:40] = len(rstream).to_bytes(4, "big")
    h[40:44] = rulen.to_bytes(4, "big")
    h[44:48] = (84 + len(dstream)).to_bytes(4, "big")
    h[49] = method if rulen else 0
    h[52:56] = b"TEXT"
    h[56:60] = b"ttxt"
    body = bytes(h) + dstream + rstream
    pad = (-len(body)) % 256          # mCompressFile @0x56ba rounds up
    return body + b"\x00" * pad


def synthetic(exe, verbose):
    """Encode, decode, compare — including a case that needs the preset."""
    rng = random.Random(20260822)
    words = [b"the quick brown fox ", b"SpaceSaver ", b"\x00" * 40,
             b"Macintosh System 7 ", b"abcdefghijklmnop"]
    body = bytearray()
    while len(body) < 200000:
        body += rng.choice(words)
    body = bytes(body[:200000])
    preset = open(PRESET, "rb").read() if os.path.exists(PRESET) else b""

    cases = [("plain", body, b"")]
    # The ceiling as well as what the encoder writes: 16 is the widest
    # window the byte can ask for, and nothing real emits it.
    cases.append(("wide", body[:60000], b""))
    if preset:
        # A payload that starts with 4 KB of the dictionary itself: every
        # match at the start reaches back into the preset.
        cases.append(("preset", preset[-4096:] + body[:20000], preset))

    work = tempfile.mkdtemp(prefix="sssynth-")
    bad = 0
    try:
        for tag, data, pre in cases:
            stream = encode_alg4(data, pre, 16 if tag == "wide" else WBITS)
            # The archive and the output go in different directories:
            # the entry's name IS the archive's, so one directory means
            # the extractor refusing to write over its own input.
            src = os.path.join(work, "in")
            dst = os.path.join(work, "out")
            os.makedirs(src, exist_ok=True)
            os.makedirs(dst, exist_ok=True)
            p = os.path.join(src, "Synth" + tag)
            open(p, "wb").write(container(stream, len(data)))
            args = [exe, "x", "-o", dst, p]
            r = subprocess.run(args, capture_output=True, timeout=600)
            got = os.path.join(dst, "Synth" + tag)
            out = open(got, "rb").read() if os.path.exists(got) else b""
            if r.returncode != 0 or out != data:
                print("spacesaver: synthetic %s: %d bytes in, %d out — "
                      "DIFFERS (%s)" % (tag, len(data), len(out),
                                        r.stderr.decode("utf-8",
                                                        "replace").strip()))
                bad += 1
            elif verbose:
                print("spacesaver: synthetic %s: %d bytes, identical"
                      % (tag, len(data)))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return bad, len(cases)



def emit(dirname):
    """Write the two files the Macintosh tier is replayed with.

    Not committed — no SpaceSaver file may be (TESTING.md) — so they are
    made on demand. One is stored in both forks, which the Mac shell can
    extract with no dictionary at all; the other needs one, and is here
    to show the refusal happening the same way on both machines rather
    than crashing on a 68000.

        tools/run_spacesaver.py --emit /tmp/ssmac
        tools/vmac/run.py --expect /tmp/ssmac/*.ss
    """
    os.makedirs(dirname, exist_ok=True)
    data = b"SpaceSaver on a Mac Plus. " * 40
    rsrc = bytes(bytearray(range(256))) * 2
    h = bytearray(84)
    h[0:4] = b"SIT!"
    h[4:8] = b"DFD3"
    h[8:12] = (3).to_bytes(4, "big")
    h[12:16] = (84).to_bytes(4, "big")
    h[16:20] = (0x41).to_bytes(4, "big")
    h[20:24] = len(data).to_bytes(4, "big")
    h[24:28] = len(data).to_bytes(4, "big")
    h[28:32] = (84).to_bytes(4, "big")
    h[36:40] = len(rsrc).to_bytes(4, "big")
    h[40:44] = len(rsrc).to_bytes(4, "big")
    h[44:48] = (84 + len(data)).to_bytes(4, "big")
    h[52:56] = b"TEXT"
    h[56:60] = b"ttxt"
    body = bytes(h) + data + rsrc
    body += b"\x00" * ((-len(body)) % 256)
    stored = os.path.join(dirname, "Stored.ss")
    open(stored, "wb").write(body)
    print("spacesaver: %s (%d B, both forks stored)" % (stored, len(body)))

    # Method 4 that needs NO dictionary: encoded with an empty preset, so
    # every match reaches into what the file itself has already produced.
    # This is the one that runs the bit decoder on the 68000.
    body = (b"the quick brown fox jumps over the lazy dog. " * 300 +
            bytes(bytearray(range(256))) * 4)
    alg4 = os.path.join(dirname, "Alg4.ss")
    open(alg4, "wb").write(container(encode_alg4(body, b""), len(body)))
    print("spacesaver: %s (%d B, method 4, no dictionary needed)"
          % (alg4, os.path.getsize(alg4)))

    if not os.path.exists(PRESET):
        print("spacesaver: no preset at %s, so no dictionary case" % PRESET)
        return 0
    preset = open(PRESET, "rb").read()
    payload = preset[-3000:] + b"the quick brown fox " * 200
    needs = os.path.join(dirname, "NeedsDict.ss")
    open(needs, "wb").write(container(encode_alg4(payload, preset),
                                      len(payload)))
    print("spacesaver: %s (%d B, method 4, reaches into the dictionary)"
          % (needs, os.path.getsize(needs)))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--macextract", default=os.path.join(REPO, "build",
                                                        "macextract"))
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--emit", metavar="DIR",
                    help="write the two files the Macintosh tier replays")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.macextract):
        print("spacesaver: no CLI at %s" % a.macextract)
        return 1

    if a.emit:
        return emit(a.emit)

    bad = ran = fuzzed = fuzzbad = 0
    sbad, sran = synthetic(a.macextract, a.verbose)
    print("spacesaver: %d synthetic stream(s), %d failure(s)" % (sran, sbad))
    dbad = builtin_matches(a.macextract) + m2_default_matches()
    if not dbad and os.path.exists(PRESET):
        print("spacesaver: the built-in dictionary matches the resource")
    sbad += dbad

    files = specimens()
    if not files:
        print("spacesaver: no specimens in %s, skipped" % SPECIMENS)
        return 1 if sbad else 0
    if not os.path.exists(PRESET):
        print("spacesaver: no preset dictionary at %s — entries that reach "
              "into it will fail" % PRESET)

    for p in files:
        b, n = grade(a.macextract, p, a.verbose)
        bad += b
        ran += n
        fb, fn = robustness(a.macextract, p, a.timeout)
        fuzzbad += fb
        fuzzed += fn
    print("spacesaver: %d specimen(s), %d failure(s); %d corrupted variants, "
          "%d failure(s)" % (ran, bad, fuzzed, fuzzbad))
    return 1 if (bad or fuzzbad or sbad) else 0


if __name__ == "__main__":
    sys.exit(main())

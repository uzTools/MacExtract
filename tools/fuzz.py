#!/usr/bin/env python3
"""fuzz.py — randomized robustness pass across all formats.

Six generators, seeded and reproducible:
  1. mutation: take a random corpus fixture, apply 1..64 random byte
     mutations / truncations / duplications;
  2. splice: concatenate random slices of two fixtures;
  3. garbage: pure random bytes with a real format magic prefix;
  4. crypt: an archive tools/synth_crypt.py wrote under a known password,
     flipped in one to four bits — a quarter of the run, because the
     ciphers are unreachable without both a password and a container that
     survives (TESTING.md, *What the fuzzer cannot see*). Half of those
     flips land anywhere in the file and half inside the bytes the reader
     hands to a cipher, which synth_crypt.py reports as ranges: a flip
     anywhere has to get through whatever the container checks first, and
     targeting the ciphertext raises every shape's reach — measured, per
     shape, by tools/fuzz_reach.py.
  5. now-repair: flip bits inside a Now Compress block payload and fix
     the 32-bit sum that block carries, which is the only way past the
     gate that keeps every ordinary mutant out of those coders.
  6. stream: a NAMED seed, mutated only inside the byte ranges its
     generator declares as compressed — the decoder half of what the
     crypt generator's targeting does for the ciphers. Generators 1 and
     2 draw a seed out of ~950 fixtures, so a format whose only specimen
     is a small synthetic one is fuzzed by nothing in practice.

Every case runs `macextract t --budget 4194304 -p <password>` (the
sanitizer build) with a timeout. The budget is in BYTES and takes no
suffix — `--budget 4M` parses as four — and a budget too small to hold a
decoder's buffers refuses every entry, which looks exactly like a
robustness result and is not one.

Any nonzero-but-clean exit is fine; crashes (signals), sanitizer aborts,
or timeouts fail the run.
"""
import argparse, json, os, random, shutil, subprocess, sys, tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIXDIR = os.path.join(ROOT, "fixtures")

MAGICS = [
    b"SIT!\x00\x01\x00\x00\x00\x00rLau",
    b"StuffIt (c)1997-2026 Aladdin Systems, Inc., "
    b"http://www.aladdinsys.com/StuffIt/\x0d\x0a",
    b"SIT!DFD3\x00\x00\x00\x03\x00\x00\x00T",
    b"PMag", b"PMa4", b"\x01\x01\x00\x00", b"\x1f\x8b\x08", b"\x1f\x9d\x90",
    b"PK\x03\x04", b"(This file must be converted with BinHex 4.0)\r:",
]


# Encrypted seeds, and a password on every case. Without them the ciphers
# are not fuzzed AT ALL: an encrypted entry is refused at unc_password,
# which is before any key schedule runs, so no mutation of an ordinary
# fixture can reach src/unc_crypt.c. tools/synth_crypt.py writes one shape
# per cipher the engine has, all of them from scratch and in Python, so
# nothing copyrighted and nothing installed is needed: the coverage is the
# same wherever this runs. TESTING.md, *What the fuzzer cannot see*.
CRYPT_KINDS = ["sit-des", "sit5-rc4", "packit-xor", "packit-des", "cpt",
               "arc-garble", "zip-crypt", "zip-aes", "zip-aes128"]
CRYPT_PW = "swordfish"


def crypt_mutate(data, rng, ranges):
    """One to four single-bit flips, which is what the CIPHERS need: an
    encrypted archive mutated the ordinary way (1..64 edits, truncations,
    duplications) dies in its container long before any key is derived.
    Measured 2026-09-23 over 80 cases per setting, counting those that
    reach key setup — 1..2 flips: 25, 1..4: 35, 1..8: 24, 1..64: 9.

    Half the cases flip anywhere, which is what fuzzes the container of an
    encrypted archive; half flip only inside `ranges`, the bytes the
    reader hands to a cipher. The second half exists because a flip
    anywhere has to survive everything the container checks on the way —
    in PackIt's seed, the one entry deliberately left in the clear, whose
    header CRC ends the walk before anything encrypted. Targeting is
    worth 19 → 26 mutants of 30 on StuffIt classic and 20 → 29 on Compact
    Pro (TESTING.md, *Fuzzing*)."""
    buf = bytearray(data)
    targeted = bool(ranges) and rng.randrange(2) == 0
    for _ in range(rng.randrange(1, 5)):
        if targeted:
            lo, hi = ranges[rng.randrange(len(ranges))]
            hi = min(hi, len(buf))
            if lo >= hi:
                continue
            at = rng.randrange(lo, hi)
        else:
            at = rng.randrange(len(buf))
        buf[at] ^= 1 << rng.randrange(8)
    return bytes(buf)


def crypt_seeds(tmp, kinds=None):
    """One seed per cipher, with the byte ranges that are ciphertext.
    A shape that cannot be built is a failure and not a quiet skip: every
    one of them is pure Python, so the only way to lose one is a bug, and
    a seed lost quietly is a cipher fuzzed by nothing — which is what the
    first month of all eight of these ciphers was."""
    out = []
    for kind in kinds or CRYPT_KINDS:
        p = os.path.join(tmp, "seed-%s.bin" % kind)
        rp = p + ".ranges"
        try:
            subprocess.run([sys.executable,
                            os.path.join(ROOT, "tools", "synth_crypt.py"),
                            "--kind", kind, "-o", p,
                            "--ranges", rp,
                            "--password", CRYPT_PW],
                           check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as e:
            print("fuzz: cannot write the %s seed: %s" % (kind, e),
                  file=sys.stderr)
            return None
        out.append((p, [tuple(r) for r in json.load(open(rp))]))
    return out


# Methods no corpus fixture uses. `tools/fuzz_cover.py` measured the
# consequence on 2026-09-27: three of the four generators mutate a corpus
# fixture, so the fuzzer's reach is the CORPUS's coverage, and a method
# this project grades by generating a file was fuzzed by nothing at all —
# `src/unc_lzdyn.c` was 16 of 16 functions never entered. These seeds are
# the decoder half of what `synth_crypt.py` does for the ciphers: pure
# Python, deterministic, so the coverage is the same wherever this runs.
#
# -lh3- is generated here; -lh2- is COMMITTED, at tools/seeds/lh2.lzh.
# That asymmetry is the point: -lh3- has a pure-Python encoder in
# run_lzh.py, while -lh2- is written only by the patched LHa this repo
# builds on demand, and a seed a reproducible fuzzer needs cannot depend
# on a binary that may not be built. Committing the bytes gives every
# machine the same seed. How it was made is in TESTING.md, *Fuzzing*;
# it is this project's own output, not a corpus fixture.
SEED_DIR = os.path.join(ROOT, "tools", "seeds")
LH2_SEED = os.path.join(SEED_DIR, "lh2.lzh")
# DiskDoubler methods 3, 4 and 5, written by tools/vmac/ddencode.py
# --build, which needs no emulator. No corpus fixture uses any of them,
# so without these the fuzzer never entered dd_rle or dd_huffman. The
# same files are round-tripped by this engine and, for the vendor's
# verdict, read by Salient's own 1991 expander (TESTING.md).
DD_SEEDS = ("dd-Rle2.dd", "dd-HuffDeep.dd", "dd-Splay128.dd")


def method_seeds(tmp):
    """Archives for methods the corpus has no specimen of."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import run_lzh
    except Exception as e:                      # pragma: no cover
        print("fuzz: cannot import the -lh3- encoder: %s" % e,
              file=sys.stderr)
        return None
    text = b"LHarc 1.13 wrote -lh3- and almost nothing else ever did.\n" * 40
    cases = [
        ("text.txt", text, {}),
        ("runs.bin", b"=" * 400 + b"\0" * 600 + b"ab" * 300, {}),
        ("random.bin", bytes((i * 37 + (i >> 3) * 101) & 0xFF
                             for i in range(4000)), {}),
        ("one.bin", b"x", {}),                  # one symbol: takes the escape
        ("single.bin", b"Q" * 5000, {"single": True}),
        ("ptree.txt", text, {"send_p_tree": True}),
        # Matches, so the mutants can reach the decoder's LZSS half.
        ("lz.txt", text, {"lz": True}),
        ("lzruns.bin", b"=" * 400 + b"\0" * 600 + b"ab" * 300, {"lz": True}),
    ]
    # ONE ARCHIVE PER CASE, not one archive of ten. A mutant of a
    # ten-entry archive almost always breaks an earlier entry, and the
    # walk stops there — measured 2026-09-27, when the match cases were
    # added to a combined seed and `lzs_decode_p` stayed at 0 % while
    # the unmutated archive reached it. Split, each case is the FIRST
    # entry of its own archive and a mutation has to get past only it.
    out = []
    for i, c in enumerate(cases):
        p = os.path.join(tmp, "seed-lh3-%d.lzh" % i)
        with open(p, "wb") as f:
            f.write(run_lzh.lh3_archive([c]))
        out.append(p)
    if os.path.exists(LH2_SEED):
        out.append(LH2_SEED)
    for name in DD_SEEDS:
        p = os.path.join(SEED_DIR, name)
        if os.path.exists(p):
            out.append(p)
    return out


# A fifth generator: mutate a Now Compress block's PAYLOAD and then
# repair the 32-bit sum that block carries, so the file still passes
# every gate the container checks on the way in.
#
# It exists because `tools/fuzz_cover.py` measured, 2026-09-27, that the
# Now Compress coders are never entered however many ordinary mutants
# are thrown at them: the format checksums its block table and its
# blocks, so a random edit is refused before any coder runs. **That is
# the gate the one heap overflow ever found in a decoder here sat
# behind** — `now_next_block` checking a length against `incap` where
# the buffer is `blkcap`, found by a crafted archive under ASan and
# never by a mutant. More cases cannot get past a checksum; repairing it
# can.
#
# The repair is `tools/mutate_now.py`'s own `fix_trailer`, which that
# tool uses to make changes a correct reader cannot notice.
def now_repair(data, rng, mn):
    """Flip bits inside block payloads, then fix each block's trailer."""
    d = bytearray(data)
    try:
        bl = [(off, end) for _n, off, end, _m, _p in mn.blocks(d)]
    except BaseException:
        return bytes(d)
    # Leave the block header alone and stop short of the trailer: the
    # point is to corrupt what the CODER reads, not what the walk does.
    spans = [(off + 8, end - 4) for off, end in bl if end - 4 > off + 8]
    if not spans:
        return bytes(d)
    for _ in range(rng.randrange(1, 9)):
        lo, hi = spans[rng.randrange(len(spans))]
        d[rng.randrange(lo, hi)] ^= 1 << rng.randrange(8)
    for off, end in bl:
        mn.fix_trailer(d, off, end)
    return bytes(d)


# ...and the three archives whose block table carries a DELTA: every
# offset it stores is off the real one by a constant, which the reader
# has to recover before it can find a single block. NEITHER corpus
# archive has one, so `now_find_delta` was the one Now Compress
# function no amount of fuzzing entered — 3,000 cases at seeds 11 and
# 12, with the repair generator already in place (TESTING.md,
# *Fuzzing*). A mutant cannot grow a delta, because the shape is a
# table whose checksum AGREES while its offsets do not: the only way
# to fuzz that path is to seed it.
#
# Written here rather than committed, for the reason the -lh3- seeds
# are: pure Python, so the coverage is the same wherever this runs.
# They are also three of the archives `tools/run_now.py` grades three
# ways — input bytes, `unar`, this CLI — on every ci.sh run, so a seed
# here is a graded file and not merely one that parses.
DELTA_SEEDS = ("synth-now-delta", "synth-now-delta-small",
               "synth-now-delta-neg")


def now_seeds(tmp):
    """Files the repair generator can work on: the corpus's own Now
    Compress archives, and the rebased ones written here."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import mutate_now as mn
        import synth_now
    except Exception as e:                      # pragma: no cover
        print("fuzz: cannot import the Now Compress tools: %s" % e,
              file=sys.stderr)
        return None, None
    out = []
    for name in DELTA_SEEDS:
        tree, delta = synth_now.archives()[name]
        path = os.path.join(tmp, name + ".now")
        with open(path, "wb") as f:
            f.write(synth_now.build_archive(tree, delta))
        # A seed the repair generator cannot walk is a seed that fuzzes
        # nothing, and it would be invisible: `now_repair` hands back
        # what it was given when it finds no block. So say so and fail,
        # the way a missing cipher seed does.
        if not list(mn.blocks(bytearray(open(path, "rb").read()))):
            print("fuzz: no blocks in the %s seed — can mutate_now walk a "
                  "rebased table?" % name, file=sys.stderr)
            return None, None
        out.append(path)
    for p in corpus():
        try:
            if list(mn.blocks(bytearray(open(p, "rb").read()))):
                out.append(p)
        except BaseException:
            continue
    return out, mn


# A sixth generator: a seed named here rather than drawn, mutated only
# inside the byte ranges its generator declares as compressed.
#
# Generators 1 and 2 pick a seed out of the whole corpus, so what the
# fuzzer reaches is weighted by FILE COUNT and not by what is worth
# reaching. StuffIt 5's method 14 is the shape that makes this visible:
# its only specimen here is `synth_sit14.py`'s 1,859 B among ~950
# fixtures, so 1,500 cases entered not one of its eleven functions
# (DECISIONS.md 2026-10-03) and 3,000 enter ten of them, by about 2.3
# draws — a sample rather than a property of the format.
#
# NAMING the seed is most of the fix and the targeting is the rest,
# measured: 120 cases of this file mutated anywhere reach all eleven
# functions and 95.5 % of the entry function's lines, confined to the
# streams 98.5 % (TESTING.md, *Fuzzing*). So the banner argument — 80
# bytes of 1,859, which refuses the file when a mutation lands in it —
# is true per case and much weaker per hundred.
#
# The targeting is the same argument the crypt generator's `--ranges`
# rests on, in the other half of the engine, and the two halves can be
# told apart here too: `--stream-untargeted` names the seed and mutates
# it anywhere, which is what generator 1 does when it draws the file.
#
# Each tool takes `-o` and `--ranges` and writes the same bytes every
# run, so the coverage is the same wherever this runs.
#
# A named shape is (name, tool, filename, args). The second one is the
# first's archive with a fifth entry whose FORK is 278,896 B: method
# 14's window is sized to the fork, so `sit14_flush`'s wrap is reached
# by nothing smaller than 0x40000 B of output, and nothing says a seed
# has to be large to decode to that — 458 B of matches do it. It is a
# separate seed rather than a fifth case in the fixture because a 256 KB
# window is a peak-RAM figure and a Macintosh tier (DECISIONS.md
# 2026-10-06), and `tools/run_sit14wrap.py` is what grades it.
STREAM_SEEDS = (
    ("sit14", "synth_sit14.py", "seed-sit14.sit", ()),
    ("sit14-wrap", "synth_sit14.py", "seed-sit14-wrap.sit", ("--wrap",)),
)


def stream_mutate(data, rng, ranges):
    """Edits confined to `ranges`: bit flips, byte-run overwrites, and a
    cut. Not 1..64 edits the way `mutate` does — a stream is a Huffman
    code followed by whatever it codes, so an early edit changes the
    meaning of everything after it and a dozen more only move where the
    decoder gives up."""
    buf = bytearray(data)
    spans = [(lo, min(hi, len(buf))) for lo, hi in ranges]
    spans = [(lo, hi) for lo, hi in spans if lo < hi]
    if not spans:
        return bytes(buf)
    for _ in range(rng.randrange(1, 9)):
        lo, hi = spans[rng.randrange(len(spans))]
        kind = rng.randrange(8)
        if kind == 0:      # cut the file inside the stream: the decoder
            buf = buf[:rng.randrange(lo, hi)]   # has to run out of input
            spans = [(a, min(b, len(buf))) for a, b in spans]
            spans = [(a, b) for a, b in spans if a < b]
            if not spans:
                break
        elif kind == 1:    # overwrite a run
            at = rng.randrange(lo, hi)
            n = min(rng.randrange(1, 64), hi - at)
            buf[at:at + n] = bytes(rng.randrange(256) for _ in range(n))
        else:              # flip
            buf[rng.randrange(lo, hi)] ^= 1 << rng.randrange(8)
    return bytes(buf)


def stream_seeds(tmp, only=None):
    """One seed per named shape, with the ranges its generator calls
    compressed. A seed whose ranges are empty or outside the file would
    mutate nothing and read exactly like a clean run, so it is a failure
    here and not a skip — the way a missing cipher seed is.

    `only` keeps just the named shapes it lists, so that the before and
    the after of ADDING a shape come from one build and one instrument,
    the way --crypt-untargeted and --no-weight do for their changes. A
    name that matches no shape is a failure: a typo that silently
    measured the whole set would read as "the new shape buys nothing"."""
    out = []
    shapes = STREAM_SEEDS
    if only:
        known = {n for n, _t, _f, _a in STREAM_SEEDS}
        unknown = [n for n in only if n not in known]
        if unknown:
            print("fuzz: no stream shape named %s — have %s"
                  % (", ".join(unknown), ", ".join(sorted(known))),
                  file=sys.stderr)
            return None
        shapes = tuple(x for x in STREAM_SEEDS if x[0] in only)
    for name, tool, fname, targs in shapes:
        p = os.path.join(tmp, fname)
        rp = p + ".ranges"
        try:
            subprocess.run([sys.executable,
                            os.path.join(ROOT, "tools", tool),
                            "-o", p, "--ranges", rp, *targs],
                           check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as e:
            print("fuzz: cannot write the %s seed: %s" % (name, e),
                  file=sys.stderr)
            return None
        ranges = [tuple(r) for r in json.load(open(rp))]
        size = os.path.getsize(p)
        if not ranges or not all(0 <= lo < hi <= size for lo, hi in ranges):
            print("fuzz: the %s seed reports %d range(s) over %d B — a seed "
                  "whose streams cannot be located fuzzes nothing"
                  % (name, len(ranges), size), file=sys.stderr)
            return None
        out.append((name, p, ranges))
    return out


# How often generators 1 and 2 draw one of the NAMED seeds above rather
# than a corpus fixture.
#
# They are in the same pool as ~950 fixtures, so each is drawn about 2.3
# times in a 3,000-case run and the chance that a given one is drawn not
# at all is about a tenth — which is not a tail, it is a result that
# happened: the `-lh2-` family read 2 functions never entered at seed 12
# and 16 of 16, the whole file, one reshuffle later (TESTING.md,
# *Fuzzing*). The seed was committed in 2026-09-27 precisely so that
# family would stop being at zero, and whether it is was left to a draw.
#
# At one in thirty-two each named seed is drawn about six times instead,
# and the corpus keeps 97 % of the draws. That is enough: the `-lh2-`
# family reads 1 function never entered — `lzd_reconst`, the one that
# wants 32,768 codes — at every seed tried, 11, 12 and 13, where
# unweighted it gave 1, 2, 3 and 16 over four runs.
#
# 1/16 was measured too, and buys nothing: the same families, the same
# counts, at the same three seeds. What it does change is the total,
# which is LOWER at 1/32 at all three (147/137/150 against 174/163/156)
# — so the cheaper share is also the one that takes less from the
# corpus, and there is no reading of these runs in which 1/16 wins.
#
# What these runs CANNOT say is whether the 3 % costs a corpus family
# anything: ARC reads 7, 11 and 18 functions never entered at 1/32 and
# 15, 15 and 13 at 1/16, i.e. its worst run is the cheaper share's, so
# the draw and not the share is what moves it (TESTING.md, *Fuzzing*).
NAMED_SHARE = 32


def pick_seed(rng, seeds, named, share=NAMED_SHARE):
    """A seed for generator 1 or 2, with the named ones weighted up."""
    if named and rng.randrange(share) == 0:
        return named[rng.randrange(len(named))]
    return seeds[rng.randrange(len(seeds))]


def corpus():
    out = []
    for f in sorted(os.listdir(FIXDIR)):
        p = os.path.join(FIXDIR, f)
        if os.path.isfile(p) and f != "SOURCES.md" and \
           os.path.getsize(p) < 512 * 1024:
            out.append(p)
    return out


def mutate(data, rng):
    buf = bytearray(data)
    for _ in range(rng.randrange(1, 65)):
        kind = rng.randrange(4)
        if not buf:
            break
        if kind == 0:      # flip
            buf[rng.randrange(len(buf))] ^= 1 << rng.randrange(8)
        elif kind == 1:    # overwrite run
            at = rng.randrange(len(buf))
            n = min(rng.randrange(1, 128), len(buf) - at)
            buf[at:at + n] = bytes(rng.randrange(256) for _ in range(n))
        elif kind == 2:    # truncate
            buf = buf[:rng.randrange(1, len(buf) + 1)]
        else:              # duplicate a slice
            at = rng.randrange(len(buf))
            n = min(rng.randrange(1, 512), len(buf) - at)
            buf[at:at] = buf[at:at + n]
    return bytes(buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract",
                    default=os.path.join(ROOT, "build/san/macextract"))
    ap.add_argument("-n", "--iterations", type=int, default=500)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=20.0)
    # The two the reach instrument drives: tools/fuzz_reach.py plants a
    # fault in one cipher's key setup and needs every case aimed at it.
    ap.add_argument("--crypt-only", action="store_true",
                    help="every case an encrypted seed, not a quarter")
    ap.add_argument("--crypt-kind", action="append", choices=CRYPT_KINDS,
                    help="restrict the encrypted seeds to these shapes "
                         "(repeatable)")
    ap.add_argument("--crypt-untargeted", action="store_true",
                    help="flip anywhere in an encrypted seed, never inside "
                         "its ciphertext — what this did before 2026-09-26, "
                         "kept so the before and after are one instrument")
    # The two that make the stream generator measurable with
    # tools/fuzz_cover.py: one to point every case at it, one to say how
    # much of its reach is the NAMING and how much is the targeting.
    ap.add_argument("--stream-only", action="store_true",
                    help="every case a named stream seed, not a twentieth")
    ap.add_argument("--stream-untargeted", action="store_true",
                    help="mutate a stream seed anywhere, the way generator "
                         "1 would if it ever drew the file — kept so the "
                         "before and after are one instrument")
    ap.add_argument("--named-share", type=int, default=NAMED_SHARE,
                    metavar="N", help="draw a named method seed on one "
                                      "case in N (default %d); the figures "
                                      "that chose it are in TESTING.md, "
                                      "*Fuzzing*" % NAMED_SHARE)
    ap.add_argument("--no-weight", action="store_true",
                    help="draw the named method seeds with the same weight "
                         "as any fixture, which is what this did before "
                         "2026-10-05")
    ap.add_argument("--stream-shape", action="append", default=[],
                    metavar="NAME", help="use only these named stream "
                                         "shapes (repeatable): sit14, "
                                         "sit14-wrap. The default is all "
                                         "of them; naming one is how the "
                                         "before and after of adding a "
                                         "shape come from one build")
    ap.add_argument("--no-stream", action="store_true",
                    help="leave the stream seeds out altogether, which is "
                         "what this did before 2026-10-05")
    ap.add_argument("--keep-dir", default=ROOT,
                    help="where a failing case is kept (default: the repo "
                         "root, where somebody will notice it)")
    args = ap.parse_args()

    if not os.path.exists(args.macextract):
        print("fuzz: no CLI at %s" % args.macextract)
        return 1

    rng = random.Random(args.seed)
    cache = {}
    bad = 0

    with tempfile.TemporaryDirectory() as tmp:
        seeds = corpus()
        if not seeds:
            print("fuzz: no corpus fixtures present", file=sys.stderr)
            return 1
        extra = method_seeds(tmp)
        if extra is None:
            return 1
        seeds += extra
        named = [] if args.no_weight else extra
        nowfiles, nowmod = now_seeds(tmp)
        if nowfiles is None:
            return 1
        encrypted = crypt_seeds(tmp, args.crypt_kind)
        if encrypted is None:
            return 1
        streams = [] if args.no_stream \
            else stream_seeds(tmp, args.stream_shape)
        if streams is None:
            return 1
        print("fuzz: %d encrypted seeds (%s)"
              % (len(encrypted),
                 ", ".join(args.crypt_kind or CRYPT_KINDS)))
        print("fuzz: %d seed(s) for methods the corpus lacks "
              "(-lh3- generated, -lh2- and DiskDoubler 3/4/5 committed), "
              "drawn %s"
              % (len(extra),
                 "like any fixture" if args.no_weight
                 else "1 case in %d" % args.named_share))
        print("fuzz: %d Now Compress file(s) for the repair generator, "
              "%d of them with a rebased block table"
              % (len(nowfiles), len(DELTA_SEEDS)))
        print("fuzz: %d named stream seed(s) (%s), mutated %s"
              % (len(streams), ", ".join(n for n, _p, _r in streams) or "-",
                 "anywhere" if args.stream_untargeted
                 else "inside their declared streams"))
        ncrypt = 0
        nstream = 0
        for i in range(args.iterations):
            # A quarter of the run is the ciphers, because they are a
            # quarter of nothing otherwise: nine encrypted seeds among
            # ~950 fixtures would be drawn about once in 150.
            if args.stream_only:
                kind = 5
            else:
                kind = 3 if args.crypt_only or rng.randrange(4) == 3 \
                    else rng.randrange(3)
            # The repair generator is the only way past a checksum, and
            # a checksum is what keeps every ordinary mutant out of the
            # Now Compress coders. A twentieth of the ordinary cases is
            # enough: the coders go from 6 functions never entered to 1
            # at that share, reproduced at two seeds, and the rest of
            # the run stays with the generators that need the draws.
            #
            # It is NOT 20 because a sixth was measured to starve the
            # others — that was inferred from one run and is withdrawn:
            # per-family reach swings by up to thirteen functions
            # between seeds at 3,000 cases, so a single-run delta says
            # nothing (TESTING.md, *Fuzzing*; BLOCKERS.md). That figure
            # read "about five" here until 2026-10-05, a fourth place
            # citing it where the correction named three.
            #
            # The stream generator takes a twentieth as well, and from
            # the SAME draw, so adding it did not change how often the
            # Now Compress one fires.
            if kind not in (3, 5):
                share = rng.randrange(20)
                if share == 0 and nowfiles:
                    kind = 4
                elif share == 1 and streams:
                    kind = 5
            if kind == 3:
                # Round robin, not a random choice: a quarter of 150 is
                # 37 cases and there are nine shapes to get through, so
                # drawing them would leave one of the nine unfuzzed
                # about a fifth of the time.
                src, cranges = encrypted[ncrypt % len(encrypted)]
                ncrypt += 1
                data = cache.setdefault(src, open(src, "rb").read())
                blob = crypt_mutate(
                    data, rng,
                    [] if args.crypt_untargeted else cranges)
            elif kind == 4:
                src = nowfiles[rng.randrange(len(nowfiles))]
                data = cache.setdefault(src, open(src, "rb").read())
                blob = now_repair(data, rng, nowmod)
            elif kind == 5:
                # Round robin, not a draw, for the reason the ciphers
                # are: a twentieth of a 150-case smoke is 5 cases, so a
                # second named shape would be skipped outright often
                # enough to matter. There are two since 2026-10-06.
                _name, src, sranges = streams[nstream % len(streams)]
                nstream += 1
                data = cache.setdefault(src, open(src, "rb").read())
                blob = mutate(data, rng) if args.stream_untargeted \
                    else stream_mutate(data, rng, sranges)
            elif kind == 0:
                src = pick_seed(rng, seeds, named,
                                args.named_share)
                data = cache.setdefault(src, open(src, "rb").read())
                blob = mutate(data, rng)
            elif kind == 1:
                s1 = pick_seed(rng, seeds, named,
                               args.named_share)
                s2 = pick_seed(rng, seeds, named,
                               args.named_share)
                d1 = cache.setdefault(s1, open(s1, "rb").read())
                d2 = cache.setdefault(s2, open(s2, "rb").read())
                c1 = rng.randrange(len(d1) + 1)
                c2 = rng.randrange(len(d2) + 1)
                blob = d1[:c1] + d2[c2:]
            else:
                blob = rng.choice(MAGICS) + \
                    bytes(rng.randrange(256) for _ in range(rng.randrange(4096)))

            path = os.path.join(tmp, "case")
            with open(path, "wb") as f:
                f.write(blob)
            # The crypt cases EXTRACT rather than test: `t` does not
            # descend into the MacBinary a StuffIt archive arrives in, so
            # it never reaches that cipher at all — measured with a
            # planted fault, 2026-09-23 (TESTING.md).
            outdir = os.path.join(tmp, "out")
            shutil.rmtree(outdir, ignore_errors=True)
            if kind == 3:
                os.mkdir(outdir)
                cmd = [args.macextract, "x", "-o", outdir,
                       "--budget", str(4 << 20), "-p", CRYPT_PW, path]
            else:
                cmd = [args.macextract, "t", "--budget", str(4 << 20),
                       "-p", CRYPT_PW, path]
            try:
                r = subprocess.run(cmd, capture_output=True,
                                   timeout=args.timeout)
            except subprocess.TimeoutExpired:
                bad += 1
                keep = os.path.join(args.keep_dir,
                                    f"fuzz-hang-{args.seed}-{i}.bin")
                os.replace(path, keep)
                print(f"FUZZ HANG at iteration {i}, kept {keep}")
                continue
            if r.returncode < 0 or r.returncode > 1 or \
               b"Sanitizer" in r.stderr or b"runtime error" in r.stderr:
                bad += 1
                keep = os.path.join(args.keep_dir,
                                    f"fuzz-crash-{args.seed}-{i}.bin")
                os.replace(path, keep)
                print(f"FUZZ FAIL at iteration {i} "
                      f"(exit {r.returncode}), kept {keep}")
                print(r.stderr.decode("utf-8", "replace")[:400])

    print(f"fuzz: {args.iterations} cases, {ncrypt} of them encrypted, "
          f"{nstream} of them a named stream seed, "
          f"{bad} failures (seed {args.seed})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

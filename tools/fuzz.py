#!/usr/bin/env python3
"""fuzz.py — randomized robustness pass across all formats.

Four generators, seeded and reproducible:
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

Every case runs `macextract t --budget 4M -p <password>` (the sanitizer
build) with a timeout. Any nonzero-but-clean exit is fine; crashes (signals),
sanitizer aborts, or timeouts fail the run.
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
# -lh3- only, for now. -lh2- is written by the patched LHa this repo
# builds on demand, and a seed a reproducible fuzzer needs cannot depend
# on a binary that may not be built (TESTING.md, *Fuzzing*).
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
    ]
    p = os.path.join(tmp, "seed-lh3.lzh")
    with open(p, "wb") as f:
        f.write(run_lzh.lh3_archive(cases))
    return [p]


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


def now_seeds():
    """Corpus files the repair generator can work on, or []."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import mutate_now as mn
    except Exception:
        return [], None
    out = []
    for p in corpus():
        try:
            if list(mn.blocks(bytearray(open(p, "rb").read()))):
                out.append(p)
        except BaseException:
            continue
    return out, mn


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
        nowfiles, nowmod = now_seeds()
        encrypted = crypt_seeds(tmp, args.crypt_kind)
        if encrypted is None:
            return 1
        print("fuzz: %d encrypted seeds (%s)"
              % (len(encrypted),
                 ", ".join(args.crypt_kind or CRYPT_KINDS)))
        print("fuzz: %d generated seed(s) for methods the corpus lacks "
              "(-lh3-)" % len(extra))
        print("fuzz: %d Now Compress file(s) for the repair generator"
              % len(nowfiles))
        ncrypt = 0
        for i in range(args.iterations):
            # A quarter of the run is the ciphers, because they are a
            # quarter of nothing otherwise: nine encrypted seeds among
            # ~950 fixtures would be drawn about once in 150.
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
            # per-family reach swings by about five functions between
            # seeds at 3,000 cases, so a single-run delta says nothing
            # (TESTING.md, *Fuzzing*; BLOCKERS.md).
            if kind != 3 and nowfiles and rng.randrange(20) == 0:
                kind = 4
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
            elif kind == 0:
                src = rng.choice(seeds)
                data = cache.setdefault(src, open(src, "rb").read())
                blob = mutate(data, rng)
            elif kind == 1:
                s1 = rng.choice(seeds)
                s2 = rng.choice(seeds)
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
          f"{bad} failures (seed {args.seed})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

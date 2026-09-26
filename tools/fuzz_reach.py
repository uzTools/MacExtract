#!/usr/bin/env python3
"""fuzz_reach.py — does the fuzzer reach each cipher? Plant a fault and count.

A coverage claim needs an instrument that can tell "ran and passed" from
"never ran", and an exit code cannot: both are zero. Two cheaper
instruments lied about this in 2026-09-23 — scoring a case as having
reached the cipher when it exited 0 or printed the word "password" gave
`sit-des` 31 of 40 when the truth was 0 (DECISIONS.md, *the ciphers
nothing had ever fuzzed*).

So this is the ground truth, and it is deliberately crude: for one
cipher at a time, write an out-of-bounds store into that cipher's key
setup, rebuild, and count the mutants that trip the sanitizer. A mutant
that trips it EXECUTED the key setup; one that does not, did not.

    tools/fuzz_reach.py                    # every shape, 30 mutants each
    tools/fuzz_reach.py --kind cpt -n 60

**The control matters more than the count.** Before the mutants, the
UNMUTATED seed is run through the faulted build, and it has to trip the
fault: a planted fault is a test too, and 2026-09-23's first one was a
no-op that fired for nobody (`fault[pwlen & 7]` with a nine-character
password writes index 1). A site whose control does not fire is reported
as BROKEN and its count is not believed.

Nothing here is in `ci.sh`: it rebuilds the engine once per site and
takes minutes. What `ci.sh` carries is the RESULT, in TESTING.md.

**It edits `src/unc_crypt.c` and puts it back.** The restore is in a
`finally`, so a failure or a Control-C is covered and a kill is not: if
this is ever killed mid-run, `git diff src/unc_crypt.c` shows the fault
it left behind, and it refuses to start if one is already there.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRYPT = os.path.join(ROOT, "src", "unc_crypt.c")
BUILD = os.path.join(ROOT, "build", "reach")
CFLAGS = ("-O1 -g -fsanitize=address,undefined,alignment "
          "-fno-sanitize-recover=all")
PW = "swordfish"

# The fault: a four-byte automatic array written one past its end,
# through volatile so that neither the optimiser nor a compile-time
# bounds warning can remove it. ASan calls it a stack-buffer-overflow.
FAULT = ("    { volatile int reach_i_ = 4; volatile char reach_f_[4];\n"
         "      reach_f_[reach_i_] = 1; (void)reach_f_[0]; }\n")

# One row per shape synth_crypt.py writes, naming the function whose
# execution IS reaching that cipher. The last row is a second site for
# the same seed: unc_crypt_winzip_aes runs before the password verifier
# is checked, so reaching it does not prove the cipher itself ran, and
# aes_encrypt_block only runs on the far side of that check.
SITES = [
    ("sit-des",    "unc_crypt_sit"),
    ("sit5-rc4",   "unc_crypt_rc4"),
    ("packit-xor", "unc_crypt_packit_xor"),
    ("packit-des", "unc_crypt_packit_des"),
    ("cpt",        "unc_crypt_cpt"),
    ("arc-garble", "unc_crypt_xor"),
    ("zip-crypt",  "unc_crypt_zip"),
    ("zip-aes",    "unc_crypt_winzip_aes"),
    ("zip-aes128", "unc_crypt_winzip_aes"),
    ("zip-aes",    "aes_encrypt_block"),
]


def plant(src, func):
    """Insert the fault as the first statement of `func`."""
    m = re.search(r"^[A-Za-z_][^\n;]*\b" + re.escape(func) + r"\([^;]*?\)\s*\n\{\n",
                  src, re.M)
    if not m:
        raise SystemExit("fuzz_reach: cannot find %s() in src/unc_crypt.c"
                         % func)
    return src[:m.end()] + FAULT + src[m.end():]


def build():
    r = subprocess.run(["make", "BUILD=" + BUILD, "CFLAGS=" + CFLAGS,
                        os.path.join(BUILD, "macextract")],
                       cwd=ROOT, capture_output=True)
    if r.returncode != 0:
        sys.stdout.write(r.stderr.decode("utf-8", "replace")[-2000:])
        raise SystemExit("fuzz_reach: build failed")


def seed(kind, tmp):
    p = os.path.join(tmp, "seed-%s.bin" % kind)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools",
                                                 "synth_crypt.py"),
                    "--kind", kind, "-o", p, "--password", PW],
                   check=True, capture_output=True)
    return p


def trips(archive, tmp):
    """True if extracting this archive trips the sanitizer."""
    out = os.path.join(tmp, "out")
    shutil.rmtree(out, ignore_errors=True)
    os.mkdir(out)
    r = subprocess.run([os.path.join(BUILD, "macextract"), "x", "-o", out,
                        "--budget", str(4 << 20), "-p", PW, archive],
                       capture_output=True, timeout=60)
    return r.returncode < 0 or r.returncode > 1 or b"Sanitizer" in r.stderr \
        or b"runtime error" in r.stderr


def mutants(kind, n, fuzzseed, tmp, untargeted):
    """Run n crypt cases of one shape and return how many tripped it."""
    keep = os.path.join(tmp, "keep")
    os.makedirs(keep, exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fuzz.py"),
                        "-n", str(n), "--seed", str(fuzzseed),
                        "--crypt-only", "--crypt-kind", kind,
                        "--keep-dir", keep] +
                       (["--crypt-untargeted"] if untargeted else []) +
                       ["--macextract", os.path.join(BUILD, "macextract")],
                       capture_output=True)
    tail = r.stdout.decode("utf-8", "replace").strip().splitlines()[-1]
    m = re.search(r"(\d+) failures", tail)
    if not m:
        raise SystemExit("fuzz_reach: cannot read fuzz.py's tally: %s" % tail)
    return int(m.group(1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--mutants", type=int, default=30)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--kind", action="append",
                    help="only these shapes (repeatable)")
    ap.add_argument("--untargeted", action="store_true",
                    help="mutate the way this did before the ciphertext "
                         "ranges existed, which is how the 2026-09-23 "
                         "figures were taken")
    args = ap.parse_args()

    original = open(CRYPT).read()
    if "reach_f_" in original:
        raise SystemExit("fuzz_reach: src/unc_crypt.c already carries a "
                         "planted fault — a previous run was killed. "
                         "`git checkout src/unc_crypt.c` first.")
    rows = [r for r in SITES if not args.kind or r[0] in args.kind]
    results = []
    tmp = tempfile.mkdtemp()
    try:
        for kind, func in rows:
            open(CRYPT, "w").write(plant(original, func))
            build()
            control = trips(seed(kind, tmp), tmp)
            hit = mutants(kind, args.mutants, args.seed, tmp,
                          args.untargeted) if control else 0
            results.append((kind, func, control, hit))
            print("  %-11s %-22s control %s  %2d/%d"
                  % (kind, func + "()", "FIRES" if control else "BROKEN",
                     hit, args.mutants))
    finally:
        open(CRYPT, "w").write(original)
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(BUILD, ignore_errors=True)

    print()
    print("reach, %d mutants each (seed %d):" % (args.mutants, args.seed))
    for kind, func, control, hit in results:
        print("  %-11s %-22s %s"
              % (kind, func + "()",
                 "%d" % hit if control
                 else "NOT MEASURED — the planted fault never fired"))
    return 0 if all(c for _, _, c, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())

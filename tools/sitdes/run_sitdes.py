#!/usr/bin/env python3
"""run_sitdes.py — grade the engine's StuffIt classic key code against
StuffIt Deluxe 3.5.1's own, run under qemu-m68k.

The `StuffIt Engine` extension StuffIt Deluxe 3.5.1 installs carries the
archive cipher in two `CCOD` code resources: -2013 reads an encrypted
archive and -2045 writes one (docs/formats/stuffit-des-key.md, which is
what was read off them). `sitdes_run.c` calls their routines as
subroutines; `sitdes_ours.c` puts this engine's `src/unc_crypt.c` behind
the same commands. This sends both the same lines and compares answers:

  S  the key schedule, reader and writer, both directions: the zero key,
     all ones, every one of the 64 single-bit keys, and random keys
  B  one block, both directions: single-bit keys and blocks, random
  P  password -> archive key -> 'MKey' check -> file key and IV, through
     the engine's `unc_crypt_sit`; Aladdin's side is its fold, then its
     check and file-key routines. Passwords of 1..40 bytes, every byte
     value 1..255 (the high bit included), each with an 'MKey' built by
     Aladdin's own block routine as its writer builds one, and the same
     'MKey' one bit off, which both sides must refuse
  X  the fork transform, random key, IV and data
  A  the three archives StuffIt Deluxe 3.5.1 wrote (tools/vmac/sitcrypt.py,
     passwords of 8, 9 and 17 characters): Aladdin's check accepts each
     password and refuses it one character off, and both forks of each
     decrypt to the same bytes on both sides

Then it shows each comparison CAN fail: `--mutate` (run by default after
the grade) patches one instruction of Aladdin's code per class and
requires that class, and only through its own answers, to disagree.

    tools/sitdes/run_sitdes.py [--engine STUFFIT-ENGINE.bin] [--source
                               src/unc_crypt.c] [--cases N] [--seed S]

The engine is a MacBinary of `System Folder:Extensions:StuffIt Engine™`;
by default it is copied off the cached System 7.0.1 volume
`spacesaver.py` installed StuffIt Deluxe 3.5.1 on, with hfsutils. Aladdin's
code is never committed: it lives in the cache and in `.tmp/`.

What it CANNOT see:
  - an archive key whose eight bytes are all equal: Aladdin's reader and
    writer fold again from the key itself (CCOD -2013 @0x1e96, -2045
    @0x3474), the engine does not; random passwords reach it with
    probability 2^-56, so no case here does
  - a password holding a NUL byte: Aladdin's fold stops at it (a C
    string); the engine reads the length. No dialog can type one
  - the empty password, which the engine folds once as Aladdin does
    since 2026-11-09 and folded zero times before; graded on Aladdin's
    side, and against the old source only from one byte up
  - the 2.x schemes (`DES`, `NewDE`): 3.5.1 does not write them; their
    derivation is this one, graded on 2.0.1's archives by run_crypt.py

SPDX-License-Identifier: 0BSD
"""
import argparse
import hashlib
import os
import random
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TMP = os.path.join(REPO, ".tmp", "sitdes")
VMAC = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
VOLUME = os.path.join(VMAC, "spacesaver", "ssinstalled.hfv")
SPECIMENS = os.path.join(VMAC, "specimens", "sitcrypt")
ENGINE_PATH = ":System Folder:Extensions:StuffIt Engine™"

# The two resources, by the bytes they were read from.
CCODS = {
    -2013: "a8fc555e936b70c1076777752aed374ea43222fd978260b367cf5e7bbf30a28e",
    -2045: "26804847664d7eb730d22323280affa04eb382434debecd857e67d855559702c",
}
# Instructions the description cites, checked where it says they are.
WITNESS = [
    (-2013, 0x19be, "24bc0123456725 7c89abcdef"),   # the fold's starting key
    (-2013, 0x19e2, "747f"),                     # the password's 7-bit mask
    (-2013, 0x1880, "5041"),                     # schedule: nibble r+8
    (-2013, 0x1d9a, "2f3c4d4b6579"),             # GetResource('MKey', ...)
    (-2013, 0x0610, "7004"),                     # the check's trailing 4
    (-2013, 0x1f90, "e298"),                     # the feedback's rotate
    (-2045, 0x2c6e, "24bc01234567"),
    (-2045, 0x2c92, "747f"),
    (-2045, 0x2b30, "5041"),
]
# One patch per class: (class, resource, offset, old, new, what it breaks).
MUTATIONS = [
    ("S", -2013, 0x1880, "5041", "5e41", "the schedule reads nibble r+7 for r+8"),
    ("S", -2045, 0x2b30, "5041", "5e41", "the same, in the writer"),
    ("B", -2013, 0x0f70 + 4 * 37, "", "", "one S-box word, one bit flipped"),
    ("P", -2013, 0x19e2, "747f", "74ff", "the fold keeps the password's high bit"),
    ("P", -2013, 0x0610, "7004", "7005", "the check's trailing 4 becomes 5"),
    ("P", -2013, 0x06b2, "756a", "7562", "the file key XORs the archive key, not the IV"),
    ("X", -2013, 0x1f90, "e298", "e498", "the feedback rotates by two"),
]


def sh(*cmd, **kw):
    return subprocess.run(list(cmd), capture_output=True, text=True, **kw)


# ------------------------------------------------------------- Aladdin's code

def rsrc_fork(macbinary):
    dl, rl = struct.unpack(">II", macbinary[83:91])
    off = 128 + ((dl + 127) // 128) * 128
    return macbinary[off:off + rl]


def resource(fork, rtype, rid):
    """Inside Macintosh: More Macintosh Toolbox, Resource File Format."""
    doff, moff = struct.unpack(">II", fork[:8])
    m = fork[moff:]
    tl_off = struct.unpack(">H", m[24:26])[0]
    tl = m[tl_off:]
    for i in range(struct.unpack(">h", tl[:2])[0] + 1):
        t, cnt, ref = struct.unpack(">4shH", tl[2 + 8 * i:10 + 8 * i])
        if t != rtype:
            continue
        for j in range(cnt + 1):
            e = tl[ref + 12 * j:ref + 12 * j + 12]
            if struct.unpack(">h", e[:2])[0] == rid:
                at = doff + int.from_bytes(e[5:8], "big")
                n = struct.unpack(">I", fork[at:at + 4])[0]
                return fork[at + 4:at + 4 + n]
    raise SystemExit("run-sitdes: no %s %d in the engine" % (rtype, rid))


def engine_from_volume():
    if not os.path.exists(VOLUME):
        raise SystemExit("run-sitdes: %s is not here; pass --engine" % VOLUME)
    for tool in ("hmount", "hcopy", "humount"):
        if not shutil.which(tool):
            raise SystemExit("run-sitdes: needs hfsutils, or --engine")
    vol = os.path.join(TMP, "volume.hfv")
    out = os.path.join(TMP, "engine.bin")
    if os.path.exists(out):
        return out
    subprocess.run(["cp", "--sparse=always", VOLUME, vol], check=True)
    try:
        subprocess.run(["hmount", vol], check=True, capture_output=True)
        subprocess.run(["hcopy", "-m", ENGINE_PATH.encode("mac_roman"), out],
                       check=True, capture_output=True)
    finally:
        subprocess.run(["humount"], capture_output=True)
        os.remove(vol)
    return out


def lift(engine, mutation=None):
    fork = rsrc_fork(open(engine, "rb").read())
    paths = []
    for rid, digest in CCODS.items():
        code = bytearray(resource(fork, b"CCOD", rid))
        if hashlib.sha256(code).hexdigest() != digest:
            raise SystemExit("run-sitdes: CCOD %d is not the one this was "
                             "read from" % rid)
        for wrid, off, want in WITNESS:
            want = bytes.fromhex(want.replace(" ", ""))
            if wrid == rid and bytes(code[off:off + len(want)]) != want:
                raise SystemExit("run-sitdes: CCOD %d @0x%x is not %s"
                                 % (rid, off, want.hex()))
        if mutation and mutation[1] == rid:
            _, _, off, old, new, _ = mutation
            if old:
                assert code[off:off + 2] == bytes.fromhex(old)
                code[off:off + 2] = bytes.fromhex(new)
            else:
                code[off + 3] ^= 0x10
        p = os.path.join(TMP, "ccod%d%s.bin" % (rid, "-m" if mutation else ""))
        open(p, "wb").write(code)
        paths.append(p)
    return paths


# ------------------------------------------------------------- the two sides

def build(source, tag=""):
    os.makedirs(TMP, exist_ok=True)
    env = dict(os.environ, TMPDIR=TMP)
    theirs = os.path.join(TMP, "sitdes_run")
    r = sh("m68k-linux-gnu-gcc", "-std=gnu99", "-O2", "-static",
           "-fomit-frame-pointer", "-o", theirs,
           os.path.join(HERE, "sitdes_run.c"), env=env)
    if r.returncode:
        raise SystemExit("run-sitdes: building sitdes_run failed:\n" + r.stderr)
    ours = os.path.join(TMP, "sitdes_ours" + tag)
    r = sh("cc", "-std=c99", "-O1", "-Wall", "-I" + os.path.join(REPO, "src"),
           "-I" + os.path.join(REPO, "include"),
           '-DUNC_CRYPT_C="%s"' % os.path.abspath(source), "-o", ours,
           os.path.join(HERE, "sitdes_ours.c"),
           os.path.join(REPO, "src", "unc_util.c"), env=env)
    if r.returncode:
        raise SystemExit("run-sitdes: building sitdes_ours failed:\n" + r.stderr)
    return theirs, ours


def ask(cmd, lines):
    r = subprocess.run(cmd, input="\n".join(lines) + "\n",
                       capture_output=True, text=True, timeout=600)
    out = r.stdout.splitlines()
    if r.returncode or len(out) != len(lines):
        raise SystemExit("run-sitdes: %s answered %d of %d lines (exit %d) %s"
                         % (cmd[0], len(out), len(lines), r.returncode,
                            r.stderr[-300:]))
    return out


class Aladdin:
    def __init__(self, exe, ccods):
        self.cmd = ["qemu-m68k", exe] + ccods

    def __call__(self, lines):
        return ask(self.cmd, lines)


def h(b):
    return bytes(b).hex()


# ------------------------------------------------------------- the cases

def cases_s(rnd, n):
    keys = [bytes(8), b"\xff" * 8]
    keys += [(1 << (63 - i)).to_bytes(8, "big") for i in range(64)]
    keys += [rnd.randbytes(8) for _ in range(n)]
    return ["S %s %s %d" % (side, h(k), mode)
            for k in keys for side in "rw" for mode in (0, 1)]


def cases_b(rnd, n):
    out = []
    for i in range(64):
        out.append("B r %s 0 %s" % (h((1 << (63 - i)).to_bytes(8, "big")),
                                    h(bytes(8))))
        out.append("B r %s 1 %s" % (h(bytes(8)),
                                    h((1 << (63 - i)).to_bytes(8, "big"))))
    for _ in range(n):
        out.append("B r %s %d %s" % (h(rnd.randbytes(8)), rnd.randrange(2),
                                     h(rnd.randbytes(8))))
    return out


def passwords(rnd, n, empty):
    pws = [b"password", b"swordfish", b"abcdefghijklmnopq"]
    pws += [bytes([v]) for v in range(1, 256)]
    for i in range(n):
        ln = 1 + i % 40
        pws.append(bytes(rnd.randrange(1, 256) for _ in range(ln)))
    if empty:
        pws.append(b"")
    return pws


def grade_p(al, ours, rnd, n, empty):
    """Aladdin's fold, then its writer's MKey built with its own block
    routine (CCOD -2045 @0x1f76: IV = iv0 || E(iv0 || 00000004)[4..7],
    MKey = E(IV)), then its reader's check and file key, against the
    engine's unc_crypt_sit given the password."""
    pws = passwords(rnd, n, empty)
    aks = al(["F r %s" % h(p) for p in pws])
    akw = al(["F w %s" % h(p) for p in pws])
    bad = [p for p, a, b in zip(pws, aks, akw) if a != b]
    iv0 = [rnd.randbytes(4) for _ in pws]
    t = al(["B r %s 0 %s00000004" % (a, h(i)) for a, i in zip(aks, iv0)])
    ivs = [h(i) + x[8:] for i, x in zip(iv0, t)]
    mk = al(["B r %s 0 %s" % (a, v) for a, v in zip(aks, ivs)])
    ek = [h(rnd.randbytes(16)) for _ in pws]
    theirs, mine, lines = [], [], []
    for p, a, m, e in zip(pws, aks, mk, ek):
        wrong = "%02x" % (int(m[:2], 16) ^ 0x01) + m[2:]
        for mm in (m, wrong):
            theirs.append("K %s %s %s" % (a, mm, e))
            mine.append("P %s %s %s" % (h(p) or "-", mm, e))
    ta, to = al(theirs), ours(mine)
    LINES["P"] = [m for m in mine if not m.startswith("P - ")]
    ok = 0
    for i, (x, y) in enumerate(zip(ta, to)):
        xs = x.split()
        x = "1" if xs[0] != "0" else x
        want_ok = i % 2 == 0
        if x != y or (x == "1") == want_ok:
            bad.append((mine[i], x, y))
        else:
            ok += 1
    return ok, bad


def cases_x(rnd, n):
    return ["X r %s %s %s" % (h(rnd.randbytes(8)), h(rnd.randbytes(8)),
                              h(rnd.randbytes(8 * rnd.randrange(1, 64))))
            for _ in range(n)]


def specimens():
    out = []
    for tag in ("pw8", "pw9", "pw17"):
        arch = os.path.join(SPECIMENS, tag, "Secret.sit.bin")
        meta = os.path.join(SPECIMENS, tag, "made.json")
        if not (os.path.exists(arch) and os.path.exists(meta)):
            continue
        import json
        pw = json.load(open(meta))["password"].encode("mac_roman")
        b = open(arch, "rb").read()
        dl = struct.unpack(">I", b[83:87])[0]
        sit = b[128:128 + dl]
        mkey = resource(rsrc_fork(b), b"MKey", 0)
        e = sit[22:22 + 112]
        crl, cdl = struct.unpack(">II", e[92:100])
        forks = [sit[134:134 + crl], sit[134 + crl:134 + crl + cdl]]
        out.append((tag, pw, mkey, forks))
    return out


def grade_a(al, ours):
    ok, bad = 0, []
    for tag, pw, mkey, forks in specimens():
        near = pw[:-1] + bytes([pw[-1] ^ 1])
        ak, akn = al(["F r %s" % h(pw), "F r %s" % h(near)])
        c = al(["C %s %s" % (ak, h(mkey)), "C %s %s" % (akn, h(mkey))])
        if c[0].split()[0] != "0" or c[1].split()[0] == "0":
            bad.append((tag, "Aladdin's check", c))
            continue
        for fork in forks:
            body, ek = fork[:-16], fork[-16:]
            k = al(["K %s %s %s" % (ak, h(mkey), h(ek))])[0].split()
            y = ours(["P %s %s %s" % (h(pw), h(mkey), h(ek))])[0].split()
            if k != y:
                bad.append((tag, "file key", k, y))
                continue
            n = len(body) & ~7
            x1 = al(["X r %s %s %s" % (k[1], k[2], h(body[:n]))])
            x2 = ours(["X r %s %s %s" % (y[1], y[2], h(body[:n]))])
            if x1 != x2:
                bad.append((tag, "fork", x1[0][:32], x2[0][:32]))
            else:
                ok += 1
    return ok, bad


LINES = {}


def compare(al, ours, lines):
    LINES[lines[0][0]] = lines
    a, o = al(lines), ours(lines)
    bad = [(l, x, y) for l, x, y in zip(lines, a, o) if x != y]
    return len(lines) - len(bad), bad


def grade(al, ours, n, seed, empty, verbose):
    rnd = random.Random(seed)
    res = {}
    res["S"] = compare(al, ours, cases_s(rnd, n))
    res["B"] = compare(al, ours, cases_b(rnd, n * 4))
    res["P"] = grade_p(al, ours, rnd, n, empty)
    res["X"] = compare(al, ours, cases_x(rnd, n))
    res["A"] = grade_a(al, ours)
    for k, (ok, bad) in res.items():
        if verbose or bad:
            print("  %s: %d agree, %d differ%s" % (k, ok, len(bad),
                  "" if not bad else "  e.g. %.120s" % (bad[0],)))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", help="MacBinary of the StuffIt Engine")
    ap.add_argument("--source", default=os.path.join(REPO, "src", "unc_crypt.c"))
    ap.add_argument("--cases", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261109)
    ap.add_argument("--no-empty", action="store_true",
                    help="leave the empty password out (the pre-2026-11-09 "
                         "source folded it zero times)")
    ap.add_argument("--no-mutate", action="store_true")
    ap.add_argument("--old", help="a second unc_crypt.c, compared with "
                    "--source line for line on every case but the empty "
                    "password")
    a = ap.parse_args()
    for tool in ("m68k-linux-gnu-gcc", "qemu-m68k", "cc"):
        if not shutil.which(tool):
            raise SystemExit("run-sitdes: needs %s" % tool)
    os.makedirs(TMP, exist_ok=True)
    engine = a.engine or engine_from_volume()
    theirs, ours_exe = build(a.source)
    ours = lambda lines: ask([ours_exe], lines)            # noqa: E731
    print("run-sitdes: %s against StuffIt Engine 3.5.2's CCOD -2013/-2045"
          % os.path.relpath(a.source, REPO))
    res = grade(Aladdin(theirs, lift(engine)), ours, a.cases, a.seed,
                not a.no_empty, True)
    failed = any(bad for _, bad in res.values())
    if a.old:
        _, old_exe = build(a.old, "_old")
        for k, lines in LINES.items():
            x, y = ask([ours_exe], lines), ask([old_exe], lines)
            d = sum(1 for p, q in zip(x, y) if p != q)
            print("  old %s: %d identical, %d differ" % (k, len(lines) - d, d))
            failed |= d > 0
    if not res["A"][0]:
        print("run-sitdes: no 3.5.1 specimen in %s" % SPECIMENS)
        failed = True
    if not a.no_mutate:
        for m in MUTATIONS:
            r = grade(Aladdin(theirs, lift(engine, m)), ours, 200, a.seed + 1,
                      not a.no_empty, False)
            hit = [k for k, (_, bad) in r.items() if bad]
            good = m[0] in hit
            print("  mutation %s (%s): %s differ — %s" % (
                m[0], m[5], ",".join(hit) or "nothing",
                "caught" if good else "NOT CAUGHT"))
            failed |= not good
    print("run-sitdes: %s" % ("FAILED" if failed else "ok"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

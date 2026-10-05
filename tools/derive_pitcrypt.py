#!/usr/bin/env python3
"""derive_pitcrypt.py — read PackIt's two ciphers out of PackIt, and have
PackIt's own code write the archives that grade them.

`PMa5` and `PMa6` were the one part of PackIt this project could not cite
to anything but XADMaster: the published description
(`reference/notes/packit_unpackit.txt`) names all four words in its
(L)ist section and attributes both encrypted forms to PackIt III, but
describes neither CIPHER — and its appendix B table lists "PMa5" twice,
which is where the claim that the document could not name the fourth
word came from (BLOCKERS.md). deark's `packit.c` errors on both and
macutils' `pit.c` skips the block. **The reference implementation was
in the corpus the whole time.** `fixtures/packit.pit_.bin` is a PackIt
archive carrying three applications, and one of them is

    Packit III 1.3   APPL/'PIT '   "PackIt III - Version 1.3 (6/14/87)"

and PackIt III is the generation that WROTE every `PMa5` and `PMa6`
block there has ever been — the manual attributes both forms to it, so
1.0 to 1.2 exist and are not here, and every offset below is 1.3's. An
application is all resource fork, so the code is right there: `CODE` 1
holds both ciphers and `CODE` 256 is nothing but DES's nine tables. Each of those tables is FIPS 46-3's to the word, which
`--tables` checks against the standard's own PDF through
`tools/gen_crypt_tables.py`.

And the code does not only get READ. It is 68k with one Toolbox trap in
the cipher's call graph, so `tools/pitcrypt/pit_run.c` runs the original
routines as subroutines under `qemu-m68k` — no emulator, no boot. That
makes the grading the strongest kind there is: `--make` has PackIt III
1.3's own cipher encrypt the blocks of three archives, in containers
written from the published appendices (`tools/synth_pit.py`), and asks
this engine to read them back. The third one is built to punish a
reader that resyncs off the eight-byte cipher grid.

    tools/derive_pitcrypt.py --witness   check the reading against the
                                         binary, pattern by pattern
    tools/derive_pitcrypt.py --tables    CODE 256 against FIPS 46-3
    tools/derive_pitcrypt.py --make      have PackIt's code encrypt, and
                                         grade this engine on the result
    tools/derive_pitcrypt.py             all three, skipping what is absent

Not in `ci.sh`: it needs the fixture, which is copyrighted and not
committed, plus the m68k cross-compiler and `qemu-m68k`. It skips
cleanly without any of them. What IS in `ci.sh` is `tools/run_crypt.py`,
which replays the specimens `--make` leaves in
`$UNC_VMAC_HOME/specimens/pitcrypt/` whenever they are there.

License: LGPL-2.1-or-later. See LICENSE and NOTICE.
"""
import argparse
import contextlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "sdmodule"))

FIXTURE = os.path.join(ROOT, "fixtures", "packit.pit_.bin")
APP = "Packit III 1.3"
RUNNER = os.path.join(ROOT, "tools", "pitcrypt", "pit_run.c")
BUILT = os.path.join(ROOT, "build", "pit_run")
SPECIMENS = os.path.join(os.environ.get(
    "UNC_VMAC_HOME", os.path.expanduser("~/.cache/macextract/vmac")),
    "specimens", "pitcrypt")

PASSWORD = b"swordfish"          # eight characters is PackIt's own limit

# ---------------------------------------------------------------------------
# What the reading rests on: a pattern in `CODE` 1 of Packit III 1.3, what
# it is, and the offset it sits AT — checked at that offset, because 17 of
# the 32 occur more than once in the resource and an address is half of
# what identifies them (the lesson tools/derive_sqp.py's witnesses record).
# That count is printed by --witness rather than asserted here.
WITNESSES = [
    (0x109a, "the block magic starts as 'PMag'", "2d7c504d6167ff9e"),
    (0x10ae, "its fourth byte takes the encryption mode, masked to 2 bits",
     "362df77cc67c0003"),
    (0x10b6, "plus four when the entry is compressed", "4a6df77a67047404"),
    (0x10c4, "and the sum is added to '0': so 'PMa4' is compressed, 'PMa5' "
             "compressed+simple, 'PMa6' compressed+DES", "d67c00301d43ffa1"),
    (0x0c7e, "Options > Simple encryption sets mode 1 AND forces compression "
             "on", "3b7c0001f77c3b7cfffff77a"),
    (0x0c9a, "Options > DES encryption sets mode 2 and forces it too — which "
             "is why no 'PMa1' or 'PMa2' can exist",
     "3b7c0002f77c3b7cfffff77a"),
    (0x0c50, "and the compression menu item does nothing at all while the "
             "mode is nonzero, so it cannot be turned back off",
     "4a6df77c66124a6df77a6608"),
    (0x0bda, "the key dialog refuses more than eight characters", "b67c0008"),
    (0x0c1e, "and nine bytes go to the password Str255: a length and eight, "
             "zero-filled past the end", "2f3c00000009486df770"),
    (0x334e, "SetKey: the eight password bytes at A5-2191 become 64 bits",
     "486dffaa486df771"),
    (0x335c, "permuted by the 56-entry table at A5-18766, which is CODE 256 "
             "+384 = PC-1", "3f3c0038486db6b2"),
    (0x3370, "and packed into the key at A5-22", "486dffea486dffaa"),
    (0x3386, "which is SEVEN bytes long, not eight", "3b7c0007fff6"),
    (0x33a0, "the cipher dispatcher reads the mode", "302df77c"),
    (0x33ec, "one step down to the XOR, two to DES, zero does nothing",
     "534067b6534067e6"),
    (0x33bc, "the XOR is one byte against one key byte", "b712"),
    (0x33c8, "and wraps at the seventh", "45edffea2b4afff23b7c0007fff6"),
    (0x33e4, "the DES path steps eight bytes at a time", "508b5184"),
    (0x3412, "the block routine applies IP, the table at CODE 256 +0",
     "3f3c0040486db532"),
    (0x3434, "derives the key schedule through PC-1 again",
     "3f3c0038486db6b2"),
    (0x34d2, "runs sixteen rounds", "b87c0010"),
    (0x34da, "then the L/R swap at +256", "3f3c0040486db632"),
    (0x34ee, "then IP-inverse at +128 — standard DES, nothing added",
     "3f3c0040486db5b2"),
    (0x35e4, "the OTHER block routine starts its rounds at 15", "780f"),
    (0x366c, "and counts down, so it is the decryption", "5344b87c0000"),
    (0x12c0, "the four magic bytes are written in the CLEAR, before the "
             "cipher starts", "2f3c00000004486eff9e"),
    (0x12ec, "and SetKey runs once per entry, so every encrypted entry's "
             "keystream starts over: no salt, no chaining between entries",
     "4eba0542"),
    (0x1600, "one flush closes each entry", "4eba0314"),
    (0x18c2, "the writer's buffer callback ciphers with the ascending one",
     "4eba1acc"),
    (0x195a, "and so does its final flush", "4eba1a34"),
    (0x1942, "which rounds the flush up to a multiple of eight whenever the "
             "mode is nonzero", "4a6df77c670c26045e832803c8bcfffffff8"),
    (0x2a3e, "the reader is the only caller of the descending one",
     "4eba0ad8"),
]

# CODE 256, table by table: offset, name, and how many 16-bit words.
TABLES = [
    (0, "IP", 64), (128, "IP-inverse", 64), (256, "the L/R swap", 64),
    (384, "PC-1", 56), (496, "PC-2", 48), (592, "E", 48), (688, "P", 32),
    (752, "the eight S boxes", 512), (1776, "the shift schedule", 16),
]


def cli():
    for p in (os.path.join(ROOT, "build", "macextract"),
              os.path.join(ROOT, "macextract")):
        if os.path.exists(p):
            return p
    return None


def app_fork():
    """Packit III 1.3's resource fork, extracted with this project's CLI.

    The fixture is a MacBinary-wrapped `.pit`, and the CLI walks both
    layers, so this is one command and no format knowledge.
    """
    out = tempfile.mkdtemp(prefix="pit3-")
    r = subprocess.run([cli(), "x", "-o", out, FIXTURE], capture_output=True)
    fork = os.path.join(out, APP + ".rsrc")
    if r.returncode != 0 or not os.path.exists(fork):
        shutil.rmtree(out, ignore_errors=True)
        raise SystemExit("derive-pitcrypt: %s carries no %s" % (FIXTURE, APP))
    return out, fork


def code_resources():
    """`CODE` 1 and `CODE` 256 of the application, as bytes."""
    from run_sdmodule import resource_data
    out, fork = app_fork()
    try:
        res = resource_data(open(fork, "rb").read())
        got = {rid: blob for rid, _name, blob in res.get("CODE", [])}
        for rid in (1, 256):
            if rid not in got:
                raise SystemExit("derive-pitcrypt: %s has no CODE %d"
                                 % (APP, rid))
        return got[1], got[256]
    finally:
        shutil.rmtree(out, ignore_errors=True)


def witness(code1):
    """Every pattern, at the offset it is claimed to sit at.

    The occurrence count is printed rather than dropped, because it is
    what says the OFFSET is load-bearing: a pattern that appears twice
    identifies a routine only together with its address.
    """
    bad = ambiguous = 0
    for off, what, hexpat in WITNESSES:
        pat = bytes.fromhex(hexpat)
        got = code1[off:off + len(pat)]
        n = 0
        at = code1.find(pat)
        while at >= 0:
            n += 1
            at = code1.find(pat, at + 1)
        ok = got == pat
        if not ok:
            bad += 1
        if n > 1:
            ambiguous += 1
        print("  %-4s CODE 1 @0x%04x %-5s %s%s"
              % ("ok" if ok else "FAIL", off, "x%d" % n if n > 1 else "",
                 what,
                 "" if ok else " [want %s, got %s]" % (hexpat, got.hex())))
    print("derive-pitcrypt: %d of %d witnesses hold, %d of the patterns "
          "occur more than once" % (len(WITNESSES) - bad, len(WITNESSES),
                                    ambiguous))
    return 1 if bad else 0


def tables(code256):
    """CODE 256 against FIPS 46-3, table by table.

    `tools/gen_crypt_tables.py` already reads the standard's own PDF —
    that is where this engine's DES tables come from — so neither side of
    this comparison is typed in here. It prints the generated header on
    import, which is what the redirect is for.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        import gen_crypt_tables as G
    # E is the one table that module does not export: `fips_table`'s
    # uniqueness check cannot read it, because the page number that
    # follows the run is itself a legal entry. Its 48 numbers come off
    # the same text.
    E = [int(t) for t in G.fips_tokens("E  BIT-SELECTION TABLE")[:48]]
    if len(E) != 48 or sorted(set(E)) != list(range(1, 33)):
        raise SystemExit("derive-pitcrypt: E did not read out of FIPS 46-3")
    want = {
        "IP": list(G.IP), "IP-inverse": list(G.FP_PUB),
        # Not a FIPS table: the halves exchanged, which is what a DES
        # implementation does between the last round and IP-inverse.
        "the L/R swap": list(range(33, 65)) + list(range(1, 33)),
        "PC-1": list(G.PC1), "PC-2": list(G.PC2), "E": E, "P": list(G.P),
        "the eight S boxes": [v for b in range(8) for v in G.S[b]],
        "the shift schedule": list(G.SHIFTS),
    }
    bad = 0
    for off, name, n in TABLES:
        got = [struct.unpack(">H", code256[off + 2 * i:off + 2 * i + 2])[0]
               for i in range(n)]
        ok = got == want[name]
        if not ok:
            bad += 1
        print("  %-4s CODE 256 +%-4d %-20s %3d words" %
              ("ok" if ok else "FAIL", off, name, n))
    print("derive-pitcrypt: %d of %d tables are FIPS 46-3's, to the word"
          % (len(TABLES) - bad, len(TABLES)))
    return 1 if bad else 0


def build_runner():
    """Cross-compile the harness that calls into CODE 1."""
    if not (shutil.which("m68k-linux-gnu-gcc") and shutil.which("qemu-m68k")):
        return None
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    r = subprocess.run(["m68k-linux-gnu-gcc", "-std=gnu99", "-O2", "-static",
                        "-o", BUILT, RUNNER], capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode("utf-8", "replace"))
        raise SystemExit("derive-pitcrypt: the harness will not build")
    return BUILT


def packit_cipher(code1, code256, mode, key, data, direction="pack"):
    """`data`, through PackIt III 1.3's own cipher, actually executed."""
    tmp = tempfile.mkdtemp(prefix="pitrun-")
    try:
        c1 = os.path.join(tmp, "code1")
        c2 = os.path.join(tmp, "code256")
        src = os.path.join(tmp, "in")
        dst = os.path.join(tmp, "out")
        open(c1, "wb").write(code1)
        open(c2, "wb").write(code256)
        open(src, "wb").write(data)
        r = subprocess.run(["qemu-m68k", BUILT, c1, c2, str(mode),
                            key.hex(), direction, src, dst],
                           capture_output=True)
        line = r.stdout.decode("utf-8", "replace").strip()
        if r.returncode != 0 or not line.startswith("status=ok"):
            raise SystemExit("derive-pitcrypt: pit_run failed: %s %s"
                             % (line, r.stderr.decode("utf-8", "replace")))
        return open(dst, "rb").read(), line
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


SUBJECTS = [
    ("Encrypted Note", b"PackIt III encrypted this in 1987. " * 9, b""),
    ("Both forks", b"data fork" * 40, b"resource fork" * 20),
]


def is_magic(w):
    return w[:3] == b"PMa" and w[3:4] in (b"g", b"4", b"5", b"6") \
        or w == b"PEnd"


def trap_block(code1, code256, key):
    """Ciphertext carrying a false 'PMag' five bytes in.

    What grades the eight-byte resync grid is an archive that punishes a
    reader for not using it. Any 64 bytes are legal ciphertext, so this
    is a block PackIt itself could have written; the plaintext that
    produces it is found by running the wanted bytes BACK through the
    application's own keystream, and the result is checked to be the
    wanted bytes again.
    """
    want = bytearray((i * 37 + 11) & 0xFF for i in range(64))
    want[5:9] = b"PMag"                     # 5 is not a multiple of eight
    for at in range(0, 64, 8):              # ... and nothing is ON the grid
        if is_magic(bytes(want[at:at + 4])):
            raise SystemExit("derive-pitcrypt: the trap filler landed a "
                             "magic on the grid at %d" % at)
    plain, _ = packit_cipher(code1, code256, 1, key, bytes(want))
    ct, line = packit_cipher(code1, code256, 1, key, plain)
    if ct != bytes(want):
        raise SystemExit("derive-pitcrypt: the XOR did not round-trip")
    return ct, line


def make(code1, code256):
    """Three archives whose encrypted blocks PackIt's own code produced.

    The container is `tools/synth_pit.py`'s, which is written from the
    published appendices; only the cipher is the application's. A clear
    entry goes either side of the encrypted ones, so the same specimens
    grade the resync a reader without the password has to do — and the
    third one grades the GRID that resync runs on.
    """
    import synth_pit as PIT
    key = (PASSWORD + b"\0" * 8)[:8]
    os.makedirs(SPECIMENS, exist_ok=True)
    made = {"password": PASSWORD.decode(), "application": APP,
            "subjects": [{"name": n, "data": d.hex(), "rsrc": r.hex()}
                         for n, d, r in SUBJECTS],
            "clear": {"Read Me": b"not a secret\n".hex(),
                      "Trailer": b"after the secret\n".hex()},
            "archives": {}}
    for mode, magic in ((1, b"PMa5"), (2, b"PMa6")):
        parts = [PIT.stored_entry("Read Me", b"not a secret\n", b"")]
        for name, data, rsrc in SUBJECTS:
            stream = PIT.huffman_entry(name, data, rsrc)[4:]   # drop 'PMa4'
            # The writer rounds its last flush up to a whole number of
            # eight-byte blocks (CODE 1 @0x1942), so the stream it
            # ciphers is always a multiple of eight.
            stream += b"\x00" * ((-len(stream)) % 8)
            ct, line = packit_cipher(code1, code256, mode, key, stream)
            print("  %s %-16s %5d B  %s" % (magic.decode(), name,
                                            len(ct), line))
            parts.append(magic + ct)
        parts.append(PIT.stored_entry("Trailer", b"after the secret\n", b""))
        blob = b"".join(parts) + b"PEnd"
        name = "packit-%s.pit" % ("des" if mode == 2 else "xor")
        open(os.path.join(SPECIMENS, name), "wb").write(blob)
        made["archives"][name] = {"magic": magic.decode(), "mode": mode,
                                  "subjects": [n for n, _d, _r in SUBJECTS]}

    ct, line = trap_block(code1, code256, key)
    print("  PMa5 %-16s %5d B  %s" % ("false magic", len(ct), line))
    blob = (PIT.stored_entry("Read Me", b"not a secret\n", b"") +
            b"PMa5" + ct +
            PIT.stored_entry("Trailer", b"after the secret\n", b"") + b"PEnd")
    open(os.path.join(SPECIMENS, "packit-xor-trap.pit"), "wb").write(blob)
    made["archives"]["packit-xor-trap.pit"] = {
        "magic": "PMa5", "mode": 1, "subjects": [],
        "note": "the encrypted block carries 'PMag' at offset 5, off the "
                "cipher grid: a byte-wise resync parses it as an entry and "
                "loses Trailer"}
    json.dump(made, open(os.path.join(SPECIMENS, "made.json"), "w"), indent=1)
    print("derive-pitcrypt: specimens in %s" % SPECIMENS)
    return 0


def extracted(out, name):
    for root, _dirs, files in os.walk(out):
        if name in files:
            return open(os.path.join(root, name), "rb").read()
    return None


def grade():
    """This engine against each archive, with the right key and a wrong one."""
    meta = os.path.join(SPECIMENS, "made.json")
    if not os.path.exists(meta):
        print("derive-pitcrypt: no specimens yet — run --make")
        return 0
    m = json.load(open(meta))
    subjects = {s["name"]: (bytes.fromhex(s["data"]), bytes.fromhex(s["rsrc"]))
                for s in m["subjects"]}
    clear = {k: bytes.fromhex(v) for k, v in m["clear"].items()}
    total = 0
    for name in sorted(m["archives"]):
        path = os.path.join(SPECIMENS, name)
        want = {n: subjects[n] for n in m["archives"][name]["subjects"]}
        bad = 0
        forks = 0
        out = tempfile.mkdtemp(prefix="pitgrade-")
        try:
            subprocess.run([cli(), "x", "-o", out, "-p", m["password"], path],
                           capture_output=True)
            for n, (data, rsrc) in want.items():
                if extracted(out, n) != data:
                    print("  FAIL %s: %s data fork" % (name, n))
                    bad += 1
                else:
                    forks += 1
                if rsrc:
                    if extracted(out, n + ".rsrc") != rsrc:
                        print("  FAIL %s: %s resource fork" % (name, n))
                        bad += 1
                    else:
                        forks += 1
            for n, blob in clear.items():
                if extracted(out, n) != blob:
                    print("  FAIL %s: the clear entry %s" % (name, n))
                    bad += 1
                else:
                    forks += 1
        finally:
            shutil.rmtree(out, ignore_errors=True)
        # A wrong key must not take the archive down with it: the clear
        # entries either side still come out, which is the resync — and
        # for the trap specimen that is the whole point, because a
        # resync off the cipher grid parses the false magic and loses
        # the entry after it.
        out = tempfile.mkdtemp(prefix="pitwrong-")
        try:
            r = subprocess.run([cli(), "x", "-o", out, "-p", "nope", path],
                               capture_output=True)
            if r.returncode == 0:
                print("  FAIL %s: a wrong key was accepted" % name)
                bad += 1
            for n, blob in clear.items():
                if extracted(out, n) != blob:
                    print("  FAIL %s: %s lost when the key was wrong"
                          % (name, n))
                    bad += 1
        finally:
            shutil.rmtree(out, ignore_errors=True)
        print("  %-4s %-20s %5d B  %d fork(s) byte-exact"
              % ("ok" if not bad else "FAIL", name, os.path.getsize(path),
                 forks))
        total += bad
    if shutil.which("unar"):
        # Worth printing rather than grading: `unar` IS XADMaster, so it
        # says whether the reference agrees with the application, not
        # whether this engine does.
        for name in sorted(m["archives"]):
            if not m["archives"][name]["subjects"]:
                continue
            first = m["archives"][name]["subjects"][0]
            out = tempfile.mkdtemp(prefix="pitunar-")
            try:
                r = subprocess.run(["unar", "-q", "-f", "-p", m["password"],
                                    "-o", out, os.path.join(SPECIMENS, name)],
                                   capture_output=True)
                hit = extracted(out, first)
                print("  --   unar on %s: %s" % (
                    name, "byte-exact" if hit == subjects[first][0]
                    else "does NOT read it (exit %d)" % r.returncode))
            finally:
                shutil.rmtree(out, ignore_errors=True)
    print("derive-pitcrypt: %s"
          % ("every fork of every archive read back" if not total
             else "%d problem(s)" % total))
    return 1 if total else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse
                                 .RawDescriptionHelpFormatter)
    ap.add_argument("--witness", action="store_true")
    ap.add_argument("--tables", action="store_true")
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--grade", action="store_true")
    a = ap.parse_args()
    everything = not (a.witness or a.tables or a.make or a.grade)

    if not cli():
        print("derive-pitcrypt: no macextract built (make) — skipped")
        return 0
    if not os.path.exists(FIXTURE):
        print("derive-pitcrypt: no %s here (skipped)" % FIXTURE)
        return 0
    code1, code256 = code_resources()
    print("derive-pitcrypt: %s, CODE 1 is %d B and CODE 256 is %d B"
          % (APP, len(code1), len(code256)))

    rc = 0
    if a.witness or everything:
        rc |= witness(code1)
    if a.tables or everything:
        rc |= tables(code256)
    if a.make or everything:
        if not build_runner():
            print("derive-pitcrypt: needs m68k-linux-gnu-gcc and qemu-m68k "
                  "to run PackIt's own cipher — --make skipped")
        else:
            rc |= make(code1, code256)
            rc |= grade()
    elif a.grade:
        rc |= grade()
    return rc


if __name__ == "__main__":
    sys.exit(main())

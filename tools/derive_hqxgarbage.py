#!/usr/bin/env python3
"""derive_hqxgarbage.py — ask three more readers about BinHex's last
macutils rule, and record the answers.

`src/fmt_binhex.c` has one citation left to macutils' `hexbin`: the skip
of a line with intermediate garbage (`hqx.c`, *"Check line for
intermediate garbage"*), which is what lets it read a file posted in
several parts, each part carrying its own mail header. Five of that
row's six rules have gone, each to a different source, and every one of
them went because the search stopped asking the DECODERS in
`reference/` and asked a writer, an author's own program or a manual
(OPEN_ITEMS.md; DECISIONS.md 2026-10-06).

**This asks the three readers that were named and never asked, and all
three say no.** The rule stays macutils'. What the reading found instead
is below, because it is worth more than the citation would have been.

    derive_hqxgarbage.py --tables     HQXer's two tables and its error
                                      strings, at the resources they sit in
    derive_hqxgarbage.py --code       the branch itself, byte-exact at the
                                      offsets it is claimed to sit at
    derive_hqxgarbage.py --absent     UUParser 1.72: the feature is not in
                                      this binary at all
    derive_hqxgarbage.py --grade      the subject, through every reader on
                                      this machine that is not an emulator
    derive_hqxgarbage.py              all four, skipping what is absent

**HQXer 1.1** (`fixtures/hqxer-11.hqx`, John Stiles, 1994) is a BinHex
encoder and decoder whose author named his own resources. Its `8->6`
128 *"8 to 6 bit table"* is the 64-character alphabet; its `6->8` 128
*"6 to 8 bit table"* is the 256-byte inverse, and that table is
**three-way**: the 64 values, `0xFE` at exactly five characters — BS,
TAB, LF, CR and SPACE — and `0xFF` at the other 187. `CODE` 2 branches
on the sign bit, fetches the next character for `0xFE`, and for `0xFF`
sets error 11 and raises `STR# 129` strings 2, 10 and 9: *"An error has
occured: / This file / is corrupt."* So HQXer skips a CHARACTER and
never a line, and its character set is five, not sixty-four. There is
no line-level test anywhere in its decode path — `GetByte` is a plain
buffered reader.

**UUParser 1.72** (`fixtures/uu-parser-172.hqx`) cannot be asked,
measured rather than assumed: its README offers BinHex parsing as a
registered-user feature, and the binary does not contain the alphabet,
the inverse table, or any 8-character run of either. Its own help text
says why — *"Parse BinHex File ... This function is enabled when your
copy of UUParser is registered"* and *"(Version 1.8) Added binhex file
parsing"*. The shareware image carries the menu item and the prose and
no decoder.

**StuffIt Expander 4.0.2** is asked by RUNNING it, not by reading it:
it carries the alphabet twice (`DATA` 0, `Eng ` 0) and no inverse
table, so its reading is built at run time and nothing static says what
it does with a bad character. **It says no too.** Over an inserted junk
LINE it writes a `.cpt` byte-identical to this engine's, which a
line-skipper and a character-skipper would both do; over one bad
character inserted INSIDE a data line — where a line test loses the
other 64 and a character test loses nothing — it writes **zero bytes**.
Three emulator runs, in `tools/vmac/README.md`, because that is where a
harness's method lives and this one needs `--keep` to see a size at all.

Not in `ci.sh`: it needs fixtures, which are copyrighted and not
committed. What IS in `ci.sh` is `tools/run_multihqx.py`, which carries
all three resume shapes as generated cases.

**The find, which is not the citation.** HQXer carries `-- end of part `
in its `DATA` 0 and reaches it from the decoder: the value `12` is `-`,
and meeting one calls a handler that compares the REST of the line
against that literal — so the string it matches is `--- end of part `,
three dashes, which is the spelling DeHQX's documentation gives and the
one `src/fmt_binhex.c` already implements. A second implementation of a
rule this project had from one source the day before, found while
asking about a different rule.

License: LGPL-2.1-or-later. See LICENSE and NOTICE.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXDIR = os.path.join(ROOT, "fixtures")
sys.path.insert(0, os.path.join(ROOT, "tools", "sdmodule"))

# Source: reference/notes/binhex40_lewis.txt — Peter N Lewis, "BinHex 4.0
# Definition", the 64-character alphabet, index = 6-bit value.
ALPHA = (b"!\"#$%&'()*+,-012345689@ABCDEFGHIJKLMNPQRSTUVXYZ[`abcdefhijklmpqr")

# What HQXer's inverse table holds where the alphabet does not reach.
# 0xFE is "fetch another character"; 0xFF is "this file is corrupt".
HQXER_SKIP = {0x08, 0x09, 0x0A, 0x0D, 0x20}

# The branch, as bytes, at the offset in the CODE 2 resource body where it
# is claimed to sit. Nothing here is inferred from a disassembler's
# labels: each entry is (offset, bytes, what it is).
HQXER_CODE2 = [
    (0x10e8, bytes.fromhex("1e28fdec"),
     "moveb %a0@(-532),%d7   — d7 = table6to8[char], a0 = a5 + char"),
    (0x10ec, bytes.fromhex("6b24"),
     "bmis 0x1112            — the sign bit: 0xFE or 0xFF"),
    (0x10ee, bytes.fromhex("0c07000c"),
     "cmpib #12,%d7          — 12 is '-', the part separator's first byte"),
    (0x1112, bytes.fromhex("0c0700fe"),
     "cmpib #-2,%d7          — is it 0xFE?"),
    (0x1116, bytes.fromhex("67c4"),
     "beqs 0x10dc            — YES: fetch the next CHARACTER. Not a line"),
    (0x1118, bytes.fromhex("1b7c000bff56"),
     "moveb #11,%a5@(-170)   — NO: error 11"),
    (0x1122, bytes.fromhex("2f3c000a0009"),
     "movel #0x000a0009      — STR# 129 strings 10 and 9"),
    (0x112c, bytes.fromhex("4eba0720"),
     "jsr %pc@(0x184e)       — the alert"),
    (0x1b1e, bytes.fromhex("43edfbc0"),
     "lea %a5@(-1088),%a1    — the '-- end of part ' literal in DATA 0"),
    # The gap loop, which is the offset `src/fmt_binhex.c` cites. It is
    # here because the source names it: an offset in a comment that
    # nothing checks is a line number by another name.
    (0x1baa, bytes.fromhex("1e2dff56"),
     "moveb %a5@(-170),%d7   — the gap loop head (+0x1baa)"),
    (0x1bae, bytes.fromhex("4ebafe84"),
     "jsr %pc@(0x1a34)       — GetByte: the FIRST of three"),
    (0x1bb6, bytes.fromhex("0c41002d"),
     "cmpiw #45,%d1          — '-' (1 of 3)"),
    (0x1bc4, bytes.fromhex("0c41002d"),
     "cmpiw #45,%d1          — '-' (2 of 3)"),
    (0x1bd2, bytes.fromhex("0c41002d"),
     "cmpiw #45,%d1          — '-' (3 of 3): three is the whole test"),
    (0x1be0, bytes.fromhex("0c41000d"),
     "cmpiw #13,%d1          — then DISCARD the rest of the line to CR, "
     "which is why a resume line may carry anything after '---'"),
]

# The alert HQXer raises, as STR# 129 indices in the order 0x184e draws
# them. Checked against the resource rather than quoted.
HQXER_ALERT = [2, 10, 9]

# What the shareware UUParser says about the feature it does not carry.
UUPARSER_PROSE = [
    b"This function is\renabled when your copy of UUParser is registered.",
    b"(Version 1.8)  Added binhex file parsing.",
]


def cli():
    for p in (os.path.join(ROOT, "build", "rel", "macextract"),
              os.path.join(ROOT, "build", "macextract"),
              os.path.join(ROOT, "build", "san", "macextract")):
        if os.path.exists(p):
            return p
    return None


def unpack(fixture, want):
    """The resource fork of one application out of one .hqx fixture."""
    exe = cli()
    if exe is None or not os.path.exists(fixture):
        return None, None
    work = tempfile.mkdtemp(prefix="dhg-")
    try:
        subprocess.run([exe, "x", "-o", work, fixture], capture_output=True)
        rsrc = data = None
        for dirpath, _d, files in os.walk(work):
            for f in files:
                if f == want + ".rsrc":
                    rsrc = open(os.path.join(dirpath, f), "rb").read()
                elif f == want:
                    data = open(os.path.join(dirpath, f), "rb").read()
        # The documentation beside it, whatever it is called.
        docs = b""
        for dirpath, _d, files in os.walk(work):
            for f in files:
                if f.endswith(".rsrc") or f == want:
                    continue
                docs += open(os.path.join(dirpath, f), "rb").read()
        return rsrc, docs
    finally:
        shutil.rmtree(work, ignore_errors=True)


def res(fork):
    from run_sdmodule import resource_data
    return resource_data(fork)


def one(rs, rtype, rid):
    return next((b for i, _n, b in rs.get(rtype, []) if i == rid), None)


def strings(body):
    n = int.from_bytes(body[0:2], "big")
    p, out = 2, []
    for _ in range(n):
        if p >= len(body):
            break
        ln = body[p]
        out.append(body[p + 1:p + 1 + ln])
        p += 1 + ln
    return out


def tables():
    """HQXer's two tables, and the alert it raises. The finding is that
    the inverse table has THREE classes and the middle one has five
    members."""
    rsrc, _docs = unpack(os.path.join(FIXDIR, "hqxer-11.hqx"), "HQXer")
    if rsrc is None:
        print("  -- HQXer 1.1: no fixture (fixtures/hqxer-11.hqx)")
        return 0, 0
    rs = res(rsrc)
    bad = seen = 0

    enc = one(rs, "8->6", 128)
    seen += 1
    if enc == ALPHA:
        print("  ok   HQXer '8->6' 128 is the 64-character alphabet")
    else:
        print("  FAIL HQXer '8->6' 128 is not the alphabet: %r" % (enc,))
        bad += 1

    dec = one(rs, "6->8", 128)
    seen += 1
    if dec is None or len(dec) != 256:
        print("  FAIL HQXer '6->8' 128 is not a 256-byte table")
        bad += 1
    else:
        values = all(dec[c] == v for v, c in enumerate(ALPHA))
        skip = {c for c in range(256) if dec[c] == 0xFE}
        fail = {c for c in range(256) if dec[c] == 0xFF}
        other = 256 - len(skip) - len(fail) - 64
        ok = values and skip == HQXER_SKIP and len(fail) == 187 and other == 0
        print("  %s HQXer '6->8' 128: 64 values, 0xFE at %s, 0xFF at %d "
              "others%s"
              % ("ok  " if ok else "FAIL",
                 " ".join(sorted("%02X" % c for c in skip)), len(fail),
                 "" if ok else "  <- not the three-way table claimed"))
        if not ok:
            bad += 1
        # The one that decides the question: ':' is NOT a terminator in
        # this table. HQXer stops on the header's lengths instead, which
        # is why a stray ':' is corruption to it and an end to us.
        seen += 1
        if dec[0x3A] == 0xFF:
            print("  ok   HQXer treats ':' as corruption, not as the end — "
                  "its lengths come from the header")
        else:
            print("  FAIL HQXer's ':' is 0x%02X, not 0xFF" % dec[0x3A])
            bad += 1

    errs = one(rs, "STR#", 129)
    seen += 1
    if errs is None:
        print("  FAIL HQXer has no STR# 129")
        bad += 1
    else:
        got = strings(errs)
        say = b" ".join(got[i - 1] for i in HQXER_ALERT)
        want = b"An error has occured:\rThis file is corrupt."
        flat = say.replace(b" ", b"")
        if flat == want.replace(b" ", b""):
            print("  ok   HQXer's answer to a bad character: %r"
                  % say.decode("mac_roman"))
        else:
            print("  FAIL HQXer STR# 129 %s is %r" % (HQXER_ALERT, say))
            bad += 1
    return bad, seen


def code():
    """The branch, byte-exact, at the offsets it is claimed to sit at."""
    rsrc, _docs = unpack(os.path.join(FIXDIR, "hqxer-11.hqx"), "HQXer")
    if rsrc is None:
        print("  -- HQXer 1.1: no fixture")
        return 0, 0
    body = one(res(rsrc), "CODE", 2)
    if body is None:
        print("  FAIL HQXer has no CODE 2")
        return 1, 1
    bad = 0
    for off, want, what in HQXER_CODE2:
        got = body[off:off + len(want)]
        if got == want:
            print("  ok   CODE 2 +0x%04x  %s" % (off, what))
        else:
            print("  FAIL CODE 2 +0x%04x  want %s got %s  (%s)"
                  % (off, want.hex(), got.hex(), what))
            bad += 1
    # The literal the '-' handler compares against, in DATA 0.
    data0 = one(res(rsrc), "DATA", 0)
    want = b"-- end of part \x00"
    if data0 and want in data0:
        print("  ok   DATA 0 +%d  %r — reached after the '-' that "
              "triggered it, so the line matched is '--- end of part '"
              % (data0.find(want), want[:-1].decode()))
    else:
        print("  FAIL HQXer's DATA 0 does not carry %r" % want)
        bad += 1
    return bad, len(HQXER_CODE2) + 1


def absent():
    """UUParser 1.72 has no BinHex decoder, and says so itself."""
    rsrc, docs = unpack(os.path.join(FIXDIR, "uu-parser-172.hqx"),
                        "UUParser 1.72")
    if rsrc is None:
        print("  -- UUParser 1.72: no fixture (fixtures/uu-parser-172.hqx)")
        return 0, 0
    bad = seen = 0
    blob = rsrc + (docs or b"")
    seen += 1
    # **Run length is the wrong test and cost a pass to find out.** The
    # longest window of the BinHex alphabet that is also a plain ascending
    # ASCII span is `@ABCDEFGHIJKLMN`, fifteen characters, and the uu table
    # every uu program carries contains it — so "a 15-character run" is
    # evidence of nothing. What distinguishes this alphabet is its GAPS: it
    # omits n, o, s, t, u, the space and twenty more. Only a window that
    # spans one of those can have come from a BinHex table.
    def gapped(w):
        return any(w[i + 1] != w[i] + 1 for i in range(len(w) - 1))

    runs = max((n for n in range(6, 65)
                if any(gapped(ALPHA[s:s + n]) and ALPHA[s:s + n] in blob
                       for s in range(0, 65 - n))), default=0)
    if runs == 0:
        print("  ok   UUParser 1.72 carries no BinHex table: not one window "
              "of the alphabet that spans a gap appears in it")
    else:
        print("  FAIL UUParser 1.72 carries a %d-character GAPPED run of the "
              "alphabet — it may have a decoder after all" % runs)
        bad += 1
    for needle in UUPARSER_PROSE:
        seen += 1
        if needle in blob:
            print("  ok   its own words: %r"
                  % needle.decode("mac_roman").replace("\r", " "))
        else:
            print("  FAIL UUParser 1.72 does not say %r" % needle)
            bad += 1
    return bad, seen


JUNK = b"From: nobody@example.invalid  (posting, part 2 of 2)"
SUBJECT = "mac-rot13.hqx"


def build(workdir):
    """A control and the same file with one line of mail in the middle.

    The subject is `mac-rot13.hqx`, which is John Stiles's own posting of
    MacROT13 — the author of HQXer — and already carries a mail header
    BEFORE its banner. What is inserted is one after it, which is the
    shape macutils' rule exists for."""
    src = os.path.join(FIXDIR, SUBJECT)
    if not os.path.exists(src):
        return None, None
    lines = open(src, "rb").read().split(b"\n")
    mid = len(lines) // 2
    control = os.path.join(workdir, "control.hqx")
    garbage = os.path.join(workdir, "garbage.hqx")
    open(control, "wb").write(b"\n".join(lines))
    open(garbage, "wb").write(b"\n".join(lines[:mid] + [JUNK] + lines[mid:]))
    return control, garbage


def _forks(d):
    out = {}
    for dirpath, _x, files in os.walk(d):
        for f in sorted(files):
            out[f] = os.path.getsize(os.path.join(dirpath, f))
    return out


def grade():
    """Every reader on this machine that is not an emulator, over the
    pair. The point of the control is that this instrument can FAIL:
    deark decodes one and errors on the other."""
    work = tempfile.mkdtemp(prefix="dhg-")
    try:
        control, garbage = build(work)
        if control is None:
            print("  -- no %s" % SUBJECT)
            return 0, 0
        exe = cli()
        deark = os.path.join(ROOT, "build", "deark", "deark")
        bad = seen = 0
        rows = []
        # **The guard is keyed on the same string the row is named by.**
        # An earlier draft tested `name == "hexbin"` against a row called
        # "hexbin (macutils)", so the skip could never fire — which is
        # this repository's own smell, and it took a rename to notice.
        READERS = (
            ("this engine", exe is not None, lambda p, o: subprocess.run(
                [exe, "x", "-nr", "-o", o, p], capture_output=True)),
            ("hexbin (macutils)", shutil.which("hexbin") is not None,
             lambda p, o: subprocess.run(["hexbin", p], cwd=o,
                                         capture_output=True)),
            ("deark", os.path.exists(deark), lambda p, o: subprocess.run(
                [deark, "-od", o, p], capture_output=True)),
        )
        for name, have, run in READERS:
            if not have:
                print("  -- %s: not on this machine" % name)
                continue
            got = {}
            for tag, path in (("control", control), ("garbage", garbage)):
                o = os.path.join(work, "%s-%s" % (name.split()[0], tag))
                os.makedirs(o, exist_ok=True)
                run(path, o)
                got[tag] = _forks(o)
            same = got["control"] == got["garbage"] and got["control"]
            rows.append((name, same, got))
        for name, same, got in rows:
            seen += 1
            print("  %-18s control %-28s garbage %-28s  %s"
                  % (name, got["control"] or "NOTHING",
                     got["garbage"] or "NOTHING",
                     "SKIPS THE LINE" if same else "does not"))
        # The instrument has to be able to fail, and the two that bracket
        # it are the ones that say so.
        byname = dict((n, s) for n, s, _g in rows)
        for who, want in (("this engine", True), ("hexbin (macutils)", True),
                          ("deark", False)):
            if who not in byname:
                continue
            seen += 1
            if bool(byname[who]) != want:
                print("  FAIL %s was expected %s" % (who, want))
                bad += 1
        if byname.get("deark") is False and byname.get("hexbin (macutils)"):
            print("  ok   the subject separates them: the rule is what is "
                  "being measured, not the file")

        # The three resume shapes, which are about the GAP rather than
        # about garbage, and which is where the reading paid for itself:
        # taking DeHQX's "a line consisting only of '---'" literally lost
        # everything after a cut whose resume line read `--- part 2 ---`
        # or `-----`. HQXer 1.1 reads three characters and discards the
        # rest of the line (`--code`, CODE 2 +0x1baa).
        if exe is not None:
            src = os.path.join(FIXDIR, SUBJECT)
            lines = open(src, "rb").read().split(b"\n")
            mid = len(lines) // 2
            # Re-extracted rather than read off the loop above, whose
            # directories are named after the row and not after us.
            base = os.path.join(work, "cut-want")
            os.makedirs(base, exist_ok=True)
            subprocess.run([exe, "x", "-nr", "-o", base, control],
                           capture_output=True)
            want = _forks(base)
            for tag, resume in (("exact", b"---"),
                                ("decorated", b"--- part 2 ---"),
                                ("longer", b"-----")):
                cutp = os.path.join(work, "cut-%s.hqx" % tag)
                open(cutp, "wb").write(b"\n".join(
                    lines[:mid] +
                    [b"--- end of part 1 of 2 ---", JUNK, b""] +
                    [resume] + lines[mid:]))
                o = os.path.join(work, "cut-%s" % tag)
                os.makedirs(o, exist_ok=True)
                subprocess.run([exe, "x", "-nr", "-o", o, cutp],
                               capture_output=True)
                seen += 1
                if _forks(o) == want and want:
                    print("  ok   resume line %-16r read, and byte-identical "
                          "to the uncut file" % resume.decode())
                else:
                    print("  FAIL resume line %-16r lost the rest of the "
                          "posting (%s)" % (resume.decode(), _forks(o)))
                    bad += 1
        return bad, seen
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", action="store_true")
    ap.add_argument("--code", action="store_true")
    ap.add_argument("--absent", action="store_true")
    ap.add_argument("--grade", action="store_true")
    a = ap.parse_args()
    allof = not (a.tables or a.code or a.absent or a.grade)
    bad = seen = 0
    for want, fn, head in ((a.tables or allof, tables,
                            "HQXer 1.1 — its two tables and its answer"),
                           (a.code or allof, code,
                            "HQXer 1.1 — the branch itself"),
                           (a.absent or allof, absent,
                            "UUParser 1.72 — the feature is not here"),
                           (a.grade or allof, grade,
                            "the subject, through every reader here")):
        if not want:
            continue
        print("== %s" % head)
        b, s = fn()
        bad += b
        seen += s
    print("\nderive-hqxgarbage: %d checked, %d failed" % (seen, bad))
    if not bad:
        print("derive-hqxgarbage: the rule is still macutils' — "
              "no reader asked here states it (OPEN_ITEMS.md)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

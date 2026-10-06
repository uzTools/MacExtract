#!/usr/bin/env python3
"""derive_hqxgarbage.py — ask every BinHex reader within reach about
macutils' last rule, and record which were asked and how.

`src/fmt_binhex.c` has one citation left to macutils' `hexbin`: the skip
of a line with intermediate garbage (`hqx.c`, *"Check line for
intermediate garbage"*), which is what lets it read a file posted in
several parts, each part carrying its own mail header. Five of that
row's six rules have gone, each to a different source, and every one of
them went because the search stopped asking the DECODERS in
`reference/` and asked a writer, an author's own program or a manual
(OPEN_ITEMS.md; DECISIONS.md 2026-10-06).

**Thirteen readers have now been asked and none states the rule.** It
stays macutils'. What the asking found instead is below, because it is
worth more than the citation would have been.

    derive_hqxgarbage.py --tables     HQXer's two tables and its error
                                      strings, at the resources they sit in
    derive_hqxgarbage.py --code       the branch itself, byte-exact at the
                                      offsets it is claimed to sit at
    derive_hqxgarbage.py --absent     UUParser 1.72: the feature is not in
                                      this binary at all
    derive_hqxgarbage.py --author     BinHex 5.0 — Yves Lempereur's own
                                      program, the format's author
    derive_hqxgarbage.py --lewis      DeHQX 2.0.1's BINARY, not the
                                      documentation beside it
    derive_hqxgarbage.py --others     five more readers in the corpus and
                                      the specimen cache
    derive_hqxgarbage.py --length     the HALF of hexbin's rule this
                                      engine declines, against the corpus
    derive_hqxgarbage.py --grade      the subject, through every reader on
                                      this machine that is not an emulator
    derive_hqxgarbage.py              all of them, skipping what is absent

**The answer, in one line: a Macintosh reader judges a CHARACTER and
macutils judges a LINE.** Seven of the thirteen are Macintosh programs
with a BinHex decoder in them. THREE of those seven answer a character outside the alphabet by
fetching another one — BinHex 5.0, Compact Pro 1.51, Aladdin's own
translator — and FOUR give up on the file: HQXer 1.1's alert, DeHQX
2.0.1's error -7, BinHqx 1.02's error 127, StuffIt Expander 4.0.2's
zero-byte output. **Not one of the seven buffers a line in order to
judge it**, so not one can state the rule — including the two written by
the men who defined the format. The remaining six are two encoders, two
programs whose decoder is somewhere else, and the two Linux readers
asked in 2026-10-05.

**BinHex 5.0** (`fixtures/binhex-50.hqx`, Yves Lempereur, 1992) is the
author's own program and the strongest no of the twelve. `CODE` 1 builds
a **128**-byte inverse table filled with `0x80` and writes the 64
alphabet values into it (+0x0b78); its bit fetcher reads a byte, and on
a byte with the high bit set (+0x0bd2) or a table miss (+0x0bdc) branches
back and **fetches another CHARACTER**. There is no line buffer in the
decode path at all. Its one line-shaped rule is at the START: the
opening `:` must be the first character with a code of 32 or more on its
line (+0x0522), which is the Definition's rule read more strictly than
this engine reads it — `bh_find_colon` allows a space or a tab before it
because the Definition names both.

**DeHQX 2.0.1** (`fixtures/dehqx-201.hqx`, Peter N Lewis) is asked as a
BINARY here; `tools/derive_dehqx.py` asks its documentation. OPEN_ITEMS
has said since 2026-10-06 that DeHQX is not a candidate because its
answer to a cut posting is the separator rather than a line test — that
was a claim about its prose, and **the code says the same thing**, which
is a re-test that held. `INITREADHQX` (+0x35ea, the author left his
Macsbug names in) builds a **256**-byte table filled with `0xFF`; the
reader `RB` (+0x398c) skips every character of 32 or less, and on a
character above 32 that misses the table sets **error -7 and stops**
(+0x39ee, and again at +0x3bfc on the slow path). So DeHQX neither skips
the character nor the line: it refuses the file, which is deark's answer
too.

Two details of DeHQX's separator are worth having, since this engine
implements it. Its `STR#` 128 holds the marker as `--- end of partX`,
sixteen characters, and `INITREADHQX` compares the stored length MINUS
ONE (+0x3684) — so the match is a **15-character prefix**, stated by the
author in his own resource. And its resume test wants `---` followed by
a character of **32 or less** (+0x3b76): a space counts, so DeHQX reads
`--- part 2 ---` and refuses `-----`, where HQXer 1.1 reads both. This
engine reads all three and is the union of the two, which is why none of
this changes behaviour.

**Five more readers, none of them stating it either** (`--others`):

  * **BinHqx 1.02** (`fixtures/binhqx-102.hqx`), a desk accessory, keeps
    its tables as named resources like HQXer: `tabl` -15999 is the
    alphabet and `tabl` -16000 is a 256-byte inverse with **three**
    classes — `0x7F` at 188 characters, `0x7E` at exactly LF, CR and
    SPACE, and `0x7D` at `:` alone. `DRVR` 12 switches on those three
    (+0x04d6, bounds `7d 7f`) and answers `0x7F` with **error 127**. Its
    one line-shaped test — a run of data characters accepted when it is
    exactly 64 long or ends at a `:` — fires only after a document is
    complete, to decide whether another follows.
  * **Compact Pro 1.51** (`fixtures/compact-pro-151.hqx`, Bill Goodman)
    carries a **115**-entry table in `DATA` 0 (+193, read at `A5`-739),
    covering `!` through `r`. `CODE` 4 +0x0e42 fetches a byte and
    branches back for another on a character below `!` (+0x0eac), above
    `r` (+0x0eb2) or `0xFF` in the table (+0x0ec4). A CHARACTER again.
  * **StuffIt Deluxe 2's own `Binhex4 Translator`** (Aladdin, July 1992,
    out of `deluxe-2-optional.sit` in the specimen cache) names its
    routines `EncodeHqx`, `DecodeHqx`, `HQXToMac` and `MacToHQX`. It
    builds the same **115**-entry table at run time (+0x10fc) and its
    bit reader (+0x1b62) fetches another character when the byte is out
    of range (+0x1b7a) or misses (+0x1b90). Aladdin's own decoder, and
    a CHARACTER.
  * **StuffIt Commands 5.5** (`fixtures/stuffIt-commands-osax-55.hqx`)
    carries no decoder: each of its four `osax` resources uses the
    alphabet exactly ONCE, in a sniffer. That sniffer is the one place
    in all thirteen readings that is line-shaped, and it uses BOTH halves
    of macutils' rule — every character of the first data line must be
    in the alphabet (+0x2a32, ANDed over the whole line) and the line
    must be **64** characters, or shorter and ending in `:` (+0x2a60).
    It answers yes or no about one line; it never skips one.
  * **AutoBin 1.0** and **Stuff and Hex 1.0** hold the alphabet because
    they WRITE it: `SendBinHex`/`BinHexFork`/`EncodeDataChar`, seven
    copies of the alphabet and the banner literal, and no inverse table
    between them. Encoders, asked and ruled out.

**The half of the rule this engine declines, measured** (`--length`).
`hexbin` also skips any line whose length differs from the first line's,
and `src/fmt_binhex.c` does not transcribe that, on the ground that it
can discard a legitimate short final line. Two readings bear on it:
StuffIt Commands and BinHqx both implement the length test and both
resolve exactly that objection the same way — a short line is fine when
it ends at the `:`. So the reason to decline it is not the objection but
the corpus: **no line in any of the 204 `.hqx` fixtures would be skipped
by the length half and kept by the alphabet half** (measured here, and
the scan is shown to fire by injecting one). What the half would catch is
junk built only of alphabet characters, which this engine takes as data
and reports as a per-entry CRC error.

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


# ------------------------------------------------------------------
# The readers asked on 2026-10-06, each as witnesses at the offsets
# they are claimed to sit at. Nothing here is a disassembler's label:
# every row is (offset, bytes, what it is), and a row that has moved
# fails rather than being quietly re-read.
# ------------------------------------------------------------------

# BinHex 5.0, CODE 1 — Yves Lempereur's own program.
BH5_CODE1 = [
    (0x0b78, "41edfd2c", "lea %a5@(-724),%a0     — the inverse table"),
    (0x0b7c, "707f", "moveq #127,%d0         — 128 entries, not 256"),
    (0x0b7e, "10fc0080", "moveb #-128,%a0@+      — every one 'not in the "
     "alphabet'"),
    (0x0b86, "41fa0098", "lea %pc@(0xc20),%a0    — the alphabet, +0x0c20"),
    (0x0b92, "12300000", "moveb %a0@(0,%d0:w),%d1 — alphabet[i]"),
    (0x0b96, "13801000", "moveb %d0,%a1@(0,%d1:w) — table[alphabet[i]] = i"),
    (0x0bd0, "1410", "moveb %a0@,%d2         — the next byte of input"),
    (0x0bd2, "6be4", "bmis 0xbb8             — high bit set: fetch another "
     "CHARACTER"),
    (0x0bd8, "14302000", "moveb %a0@(0,%d2:w),%d2 — table[c]"),
    (0x0bdc, "6bda", "bmis 0xbb8             — a MISS: fetch another "
     "CHARACTER. Not a line"),
    (0x0522, "0c000020", "cmpib #32,%d0          — the start scan"),
    (0x0526, "65f4", "bcss 0x51c             — a control keeps the line's "
     "start"),
    (0x0528, "0c00003a", "cmpib #58,%d0          — ':' must be the FIRST "
     "character >= 32"),
]

# DeHQX 2.0.1, CODE 1 — Peter N Lewis's own program, read as a binary.
# The author left his Macsbug names in: INITREADHQX ends at +0x3694 and
# RB — the 6-bit reader — at +0x3c0c.
DEHQX_CODE1 = [
    (0x3600, "41edbad2", "lea %a5@(-17710),%a0   — INITREADHQX's table"),
    (0x3604, "11bc00ff7000", "moveb #-1,%a0@(0,%d7:w)"),
    (0x360c, "0c4700ff", "cmpiw #255,%d7         — 256 entries"),
    (0x361e, "12307000", "moveb %a0@(0,%d7:w),%d1 — alphabet[i], out of "
     "STR# 128"),
    (0x3626, "1b801000", "moveb %d0,%a5@(0,%d1:w) — table[alphabet[i]] = i"),
    (0x3680, "102dbc1c", "moveb %a5@(-17380),%d0 — the separator's stored "
     "LENGTH"),
    (0x3684, "5340", "subqw #1,%d0           — compare 15, not the 16 "
     "stored: a PREFIX"),
    (0x3686, "3b40bc5c", "movew %d0,%a5@(-17316)"),
    (0x39ca, "0c6e0020ffee", "cmpiw #32,%fp@(-18)    — the skip class is "
     "<= 32, nothing else"),
    (0x39e4, "0c6d00ffbbd4", "cmpiw #255,%a5@(-17452) — a table MISS"),
    (0x39ee, "397cfff9ffee", "movew #-7,%a4@(-18)    — an ERROR. Not the "
     "character, not the line"),
    (0x3b76, "0c430020", "cmpiw #32,%d3          — resume at '---' then a "
     "character <= 32"),
    (0x3bf4, "0c6d00ffbbd4", "cmpiw #255,...         — the slow path, same "
     "answer"),
    (0x3bfc, "397cfff9ffee", "movew #-7,%a4@(-18)"),
]

# Compact Pro 1.51, CODE 4 — Bill Goodman. 115 entries, '!' through 'r',
# so the range check is in the code and not in the table.
CPRO_CODE4 = [
    (0x0ea8, "0c070021", "cmpib #33,%d7          — '!'"),
    (0x0eac, "659a", "bcss 0xe48             — below it: fetch another "
     "CHARACTER"),
    (0x0eae, "0c070072", "cmpib #114,%d7         — 'r'"),
    (0x0eb2, "6294", "bhis 0xe48             — above it: fetch another"),
    (0x0ebc, "1e28fd1d", "moveb %a0@(-739),%d7   — table[c], DATA 0 +193"),
    (0x0ec0, "0c0700ff", "cmpib #-1,%d7"),
    (0x0ec4, "6782", "beqs 0xe48             — a MISS: fetch another. Not "
     "a line"),
]

# StuffIt Deluxe 2's own "Binhex4 Translator", Othe 0 — Aladdin, 1992.
SD2_OTHE0 = [
    (0x10fc, "117c00ff389a", "moveb #-1,%a0@(14490)  — fill the table"),
    (0x1104, "0c460073", "cmpiw #115,%d6         — 115 entries, 0..'r'"),
    (0x1114, "10283916", "moveb %a0@(14614),%d0  — alphabet[i], +0x3916"),
    (0x111c, "1146389a", "moveb %d6,%a0@(14490)  — table[alphabet[i]] = i"),
    (0x1b76, "0c470073", "cmpiw #115,%d7         — the bit reader"),
    (0x1b7a, "6cec", "bges 0x1b68            — out of range: fetch "
     "another CHARACTER"),
    (0x1b82, "1028389a", "moveb %a0@(14490),%d0  — table[c]"),
    (0x1b8a, "0c6c00ff3898", "cmpiw #255,%a4@(14488)"),
    (0x1b90, "67d6", "beqs 0x1b68            — a MISS: fetch another"),
]

# StuffIt Commands 5.5, osax 128 — a SNIFFER, and the one line-shaped
# thing in all twelve readings. It uses both halves of macutils' rule to
# answer yes or no about one line, and never skips one.
SIC_OSAX128 = [
    (0x2a14, "487900005dea", "pea 0x5dea             — the alphabet"),
    (0x2a1a, "4ebaf8a2", "jsr %pc@(0x22be)       — strchr"),
    (0x2a32, "ce00", "andb %d0,%d7           — ANDed over the WHOLE "
     "line: the alphabet half"),
    (0x2a48, "0c450040", "cmpiw #64,%d5          — stop after 64"),
    (0x2a60, "0c450040", "cmpiw #64,%d5          — the length half"),
    (0x2a66, "0c450018", "cmpiw #24,%d5"),
    (0x2a6c, "0c2a003affff", "cmpib #58,%a2@(-1)     — or shorter and "
     "ending at ':'"),
    (0x2adc, "0c030021", "cmpib #33,%d3          — '!'"),
    (0x2ae2, "0c030075", "cmpib #117,%d3         — 'u', looser than the "
     "alphabet's 'r'"),
]

# The StuffIt Deluxe 2 translator is not a fixture: it is a cached
# specimen, named here so the next reading starts from the archive and
# not from a path somebody remembered.
SD2_ARCHIVE = os.path.join(
    os.environ.get("UNC_CACHE", os.path.expanduser("~/.cache/macextract")),
    "sit2", "deluxe-2-optional.sit")
SD2_MEMBER = "Binhex4 Translator"


def witness(body, rows, label):
    """Every row of a witness table, byte-exact. Returns (bad, seen)."""
    bad = 0
    for off, hx, what in rows:
        want = bytes.fromhex(hx)
        got = body[off:off + len(want)]
        if got == want:
            print("  ok   %s +0x%04x  %s" % (label, off, what))
        else:
            print("  FAIL %s +0x%04x  want %s got %s  (%s)"
                  % (label, off, hx, got.hex(), what))
            bad += 1
    return bad, len(rows)


def author():
    """BinHex 5.0 — the format's author, and the strongest no."""
    rsrc, _docs = unpack(os.path.join(FIXDIR, "binhex-50.hqx"), "BinHex 5.0")
    if rsrc is None:
        print("  -- BinHex 5.0: no fixture (fixtures/binhex-50.hqx)")
        return 0, 0
    body = one(res(rsrc), "CODE", 1)
    if body is None:
        print("  FAIL BinHex 5.0 has no CODE 1")
        return 1, 1
    bad = seen = 0
    seen += 1
    if body.find(ALPHA) == 0x0c20:
        print("  ok   CODE 1 +0x0c20 is the 64-character alphabet")
    else:
        print("  FAIL BinHex 5.0's alphabet is at %r, not +0x0c20"
              % body.find(ALPHA))
        bad += 1
    b, s = witness(body, BH5_CODE1, "CODE 1")
    return bad + b, seen + s


def lewis():
    """DeHQX 2.0.1's BINARY. tools/derive_dehqx.py asks its prose; this
    re-tests the row's "DeHQX is not a candidate" claim against the code,
    and the code agrees."""
    rsrc, _docs = unpack(os.path.join(FIXDIR, "dehqx-201.hqx"), "DeHQX")
    if rsrc is None:
        print("  -- DeHQX 2.0.1: no fixture (fixtures/dehqx-201.hqx)")
        return 0, 0
    rs = res(rsrc)
    bad = seen = 0

    # STR# 128 is the whole of what DeHQX knows about mailed text: the
    # banner, the separator and the alphabet, and nothing else.
    body = one(rs, "STR#", 128)
    seen += 1
    got = strings(body) if body else []
    want = [b"(This file must be converted with BinHex",
            b"--- end of partX", ALPHA]
    if got == want:
        print("  ok   STR# 128 is three strings: the banner, "
              "%r (sixteen characters), the alphabet" % b"--- end of partX")
    else:
        print("  FAIL DeHQX's STR# 128 is %r" % (got,))
        bad += 1

    code1 = one(rs, "CODE", 1)
    if code1 is None:
        print("  FAIL DeHQX has no CODE 1")
        return bad + 1, seen + 1
    b, s = witness(code1, DEHQX_CODE1, "CODE 1")
    bad += b
    seen += s
    # The names are the author's, so they are checked rather than quoted.
    for name in (b"INITREADHQX", b"FINDSTART", b"READCOLON", b"READHEADER"):
        seen += 1
        if bytes([0x80 | len(name)]) + name in code1:
            print("  ok   CODE 1 carries the author's own name %r"
                  % name.decode())
        else:
            print("  FAIL DeHQX's CODE 1 has no %r record" % name.decode())
            bad += 1
    return bad, seen


def others():
    """Five more readers: two desk-accessory-and-application decoders,
    Aladdin's own translator, Aladdin's sniffer, and two encoders."""
    bad = seen = 0

    # BinHqx 1.02 — the tables are named resources, like HQXer's.
    rsrc, _d = unpack(os.path.join(FIXDIR, "binhqx-102.hqx"), "BinHqx 1.02")
    if rsrc is None:
        print("  -- BinHqx 1.02: no fixture (fixtures/binhqx-102.hqx)")
    else:
        rs = res(rsrc)
        alpha = one(rs, "tabl", -15999)
        table = one(rs, "tabl", -16000)
        seen += 1
        if alpha == ALPHA:
            print("  ok   BinHqx 'tabl' -15999 is the alphabet")
        else:
            print("  FAIL BinHqx 'tabl' -15999 is %r" % (alpha,))
            bad += 1
        seen += 1
        if table is None or len(table) != 256:
            print("  FAIL BinHqx 'tabl' -16000 is not a 256-byte table")
            bad += 1
        else:
            values = all(table[ALPHA[i]] == i for i in range(64))
            skip = {c for c in range(256) if table[c] == 0x7E}
            done = {c for c in range(256) if table[c] == 0x7D}
            fail = {c for c in range(256) if table[c] == 0x7F}
            ok = (values and skip == {0x0A, 0x0D, 0x20} and done == {0x3A}
                  and len(fail) == 188)
            print("  %s BinHqx 'tabl' -16000: 64 values, 0x7E at LF CR "
                  "SPACE, 0x7D at ':' alone, 0x7F at %d others"
                  % ("ok  " if ok else "FAIL", len(fail)))
            if not ok:
                bad += 1
        drvr = one(rs, "DRVR", 12)
        if drvr is not None:
            b, s = witness(drvr, [
                (0x04bc, "0c400040", "cmpiw #64,%d0          — a data value"),
                (0x04d6, "4ebafb66", "jsr %pc@(0x3e)         — switch on "
                 "the other three"),
                (0x04da, "007d007f", "dc.w 0x7d,0x7f         — the bounds: "
                 "exactly three classes"),
                (0x0664, "707f", "moveq #127,%d0         — 0x7F is "
                 "error 127, not a line skip"),
            ], "DRVR 12")
            bad += b
            seen += s

    # Compact Pro 1.51.
    rsrc, _d = unpack(os.path.join(FIXDIR, "compact-pro-151.hqx"),
                      "Compact Pro")
    if rsrc is None:
        print("  -- Compact Pro 1.51: no fixture "
              "(fixtures/compact-pro-151.hqx)")
    else:
        rs = res(rsrc)
        data0 = one(rs, "DATA", 0)
        seen += 1
        tb = data0[193:193 + 115] if data0 else b""
        ff = sum(1 for c in range(0x21, 0x73) if len(tb) > c and
                 tb[c] == 0xFF)
        if len(tb) == 115 and all(tb[ALPHA[i]] == i for i in range(64)) \
                and ff == 18:
            print("  ok   Compact Pro DATA 0 +193: 115 entries, 64 values, "
                  "0xFF at the 18 others between '!' and 'r'")
        else:
            print("  FAIL Compact Pro's DATA 0 +193 is not that table "
                  "(%d bytes, %d invalid)" % (len(tb), ff))
            bad += 1
        code4 = one(rs, "CODE", 4)
        if code4 is not None:
            b, s = witness(code4, CPRO_CODE4, "CODE 4")
            bad += b
            seen += s

    # StuffIt Deluxe 2's own translator, out of the specimen cache.
    rsrc, _d = unpack(SD2_ARCHIVE, SD2_MEMBER)
    if rsrc is None:
        print("  -- StuffIt Deluxe 2's Binhex4 Translator: no specimen "
              "(%s)" % SD2_ARCHIVE)
    else:
        body = one(res(rsrc), "Othe", 0)
        if body is None:
            print("  FAIL the Binhex4 Translator has no 'Othe' 0")
            bad += 1
            seen += 1
        else:
            seen += 1
            if body.find(ALPHA) == 0x3916:
                print("  ok   Binhex4 Translator 'Othe' 0 +0x3916 is the "
                      "alphabet")
            else:
                print("  FAIL its alphabet is at %r, not +0x3916"
                      % body.find(ALPHA))
                bad += 1
            for name in (b"DecodeHqx", b"HQXToMac", b"EncodeHqx"):
                seen += 1
                if bytes([0x80 | len(name)]) + name in body:
                    print("  ok   Aladdin's own name for it: %r"
                          % name.decode())
                else:
                    print("  FAIL no %r record in 'Othe' 0" % name.decode())
                    bad += 1
            b, s = witness(body, SD2_OTHE0, "Othe 0")
            bad += b
            seen += s

    # StuffIt Commands 5.5 — no decoder at all, and a line-shaped sniffer.
    rsrc, _d = unpack(os.path.join(FIXDIR, "stuffIt-commands-osax-55.hqx"),
                      "StuffIt Commands")
    if rsrc is None:
        print("  -- StuffIt Commands 5.5: no fixture")
    else:
        rs = res(rsrc)
        for rid in (128, 129, 130, 133):
            body = one(rs, "osax", rid)
            seen += 1
            if body is None:
                print("  FAIL StuffIt Commands has no osax %d" % rid)
                bad += 1
                continue
            off = body.find(ALPHA)
            # One push of the alphabet's address and no other use of it is
            # what says there is no decoder in here: a decoder needs the
            # inverse, and the inverse is the Engine's.
            pushes = body.count(b"\x48\x79" + off.to_bytes(4, "big"))
            if off >= 0 and pushes == 1:
                print("  ok   osax %d uses the alphabet exactly once, in "
                      "the sniffer" % rid)
            else:
                print("  FAIL osax %d: alphabet at %r, pushed %d time(s)"
                      % (rid, off, pushes))
                bad += 1
        body = one(rs, "osax", 128)
        if body is not None:
            b, s = witness(body, SIC_OSAX128, "osax 128")
            bad += b
            seen += s

    # Two encoders, ruled out rather than assumed.
    rsrc, _d = unpack(os.path.join(FIXDIR, "auto-bin-10.hqx"), "AutoBin 1.0")
    if rsrc is None:
        print("  -- AutoBin 1.0: no fixture")
    else:
        body = one(res(rsrc), "CODE", 2) or b""
        seen += 1
        names = [n for n in (b"SendBinHex", b"BinHexFork", b"EncodeDataChar")
                 if bytes([0x80 | len(n)]) + n in body]
        if len(names) == 3:
            print("  ok   AutoBin 1.0 is an encoder: %s"
                  % ", ".join(n.decode() for n in names))
        else:
            print("  FAIL AutoBin 1.0's own names are %r" % (names,))
            bad += 1
    rsrc, _d = unpack(os.path.join(FIXDIR, "stuff-and-hex-10.hqx"),
                      "Stuff and Hex ƒ")
    if rsrc is None:
        print("  -- Stuff and Hex 1.0: no fixture")
    else:
        body = one(res(rsrc), "CODE", 1) or b""
        seen += 1
        copies = body.count(ALPHA)
        banner = b"(This file must be converted with BinHex 4.0)" in body
        if copies == 7 and banner:
            print("  ok   Stuff and Hex 1.0 is an encoder: seven copies of "
                  "the alphabet and the banner it WRITES")
        else:
            print("  FAIL Stuff and Hex: %d alphabet copies, banner %s"
                  % (copies, banner))
            bad += 1
    return bad, seen


def length():
    """The HALF of hexbin's rule this engine declines, against the corpus.

    `hqx.c` also skips any line whose length differs from the first
    line's. `src/fmt_binhex.c` does not transcribe it. The question this
    answers is not whether the test is right but whether it is
    load-bearing HERE: a line it would skip that the alphabet half keeps.
    The scan is shown to fire by injecting one, because a scan that
    found nothing and could not fire would be no evidence at all."""
    import glob
    alpha = set(ALPHA)

    def odd_lines(raw):
        """Lines the length half skips and the alphabet half keeps."""
        lines = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
        start = next((k for k, l in enumerate(lines)
                      if l.strip().startswith(b":")), None)
        if start is None:
            return None
        norm, out = len(lines[start].rstrip(b" \t")), []
        for k in range(start, len(lines)):
            l = lines[k].rstrip(b" \t")
            if not l:
                continue
            if l.endswith(b":"):
                break                       # the terminator's own line
            if len(l) != norm and all(c in alpha for c in l):
                out.append((k, len(l)))
        return out

    files = sorted(glob.glob(os.path.join(FIXDIR, "*.hqx")))
    if not files:
        print("  -- no .hqx fixtures")
        return 0, 0
    bad = seen = 0
    hits, scanned = [], 0
    for p in files:
        got = odd_lines(open(p, "rb").read())
        if got is None:
            continue
        scanned += 1
        if got:
            hits.append((os.path.basename(p), got[:3], len(got)))
    seen += 1
    if hits:
        print("  FAIL %d of %d .hqx fixtures carry a line the length half "
              "would skip: %r" % (len(hits), scanned, hits[:2]))
        print("       that is a file this engine loses and hexbin reads — "
              "it is no longer a tolerance, it is a gap")
        bad += 1
    else:
        print("  ok   0 of %d .hqx fixtures carry a line the length half "
              "would skip and the alphabet half would keep" % scanned)

    # And the scan can fire: one injected line of hyphens, which is
    # alphabet-only and is not 64 characters long.
    seen += 1
    src = os.path.join(FIXDIR, SUBJECT)
    if not os.path.exists(src):
        print("  -- %s absent, so the scan's own control was not run"
              % SUBJECT)
    else:
        lines = open(src, "rb").read().split(b"\n")
        mid = len(lines) // 2
        probe = b"\n".join(lines[:mid] + [b"-" * 20] + lines[mid:])
        got = odd_lines(probe)
        if got:
            print("  ok   the scan fires on an injected %r line, so the 0 "
                  "above is a measurement" % ("-" * 20))
        else:
            print("  FAIL the scan did not fire on an injected line of "
                  "hyphens; the 0 above measures nothing")
            bad += 1
    return bad, seen



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
    ap.add_argument("--author", action="store_true")
    ap.add_argument("--lewis", action="store_true")
    ap.add_argument("--others", action="store_true")
    ap.add_argument("--length", action="store_true")
    ap.add_argument("--grade", action="store_true")
    a = ap.parse_args()
    allof = not (a.tables or a.code or a.absent or a.author or a.lewis
                 or a.others or a.length or a.grade)
    bad = seen = 0
    for want, fn, head in ((a.tables or allof, tables,
                            "HQXer 1.1 — its two tables and its answer"),
                           (a.code or allof, code,
                            "HQXer 1.1 — the branch itself"),
                           (a.absent or allof, absent,
                            "UUParser 1.72 — the feature is not here"),
                           (a.author or allof, author,
                            "BinHex 5.0 — the format's author"),
                           (a.lewis or allof, lewis,
                            "DeHQX 2.0.1 — the Definition's author, as a "
                            "binary"),
                           (a.others or allof, others,
                            "BinHqx, Compact Pro, Aladdin's translator and "
                            "sniffer, two encoders"),
                           (a.length or allof, length,
                            "the half of the rule this engine declines"),
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
        print("derive-hqxgarbage: the rule is still macutils' — thirteen "
              "readers asked, none states it (OPEN_ITEMS.md)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

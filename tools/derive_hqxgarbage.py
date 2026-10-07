#!/usr/bin/env python3
"""derive_hqxgarbage.py — fourteen BinHex readers asked about macutils'
last rule. The fourteenth states it, and the row closes.

`src/fmt_binhex.c` judged a whole LINE and skipped it when any character
could not be data, and cited macutils' `hexbin` for that
(`hqx.c`, *"Check line for intermediate garbage"*) because nothing else
known stated it. Five of that row's six rules had already gone, each to
a different source, and every one went because the search stopped asking
the decoders in `reference/` and asked a writer, an author's own program
or a manual (DECISIONS.md 2026-10-06).

**The sixth and last went the same way, on 2026-10-07: StuffIt's own
`HQXEngine` states the rule.** Aladdin's SDK 5.1.2, April 1999, the
decoder behind StuffIt Expander 5.x — it reads a line into an 80-byte
buffer, hands it to a predicate, and **when the predicate says no it
rewinds the buffer and reads the next line**. That is macutils' rule,
written by somebody else, and `src/fmt_binhex.c` cites it now.

    derive_hqxgarbage.py --engine     THE ANSWER: HQXEngine's line reader
                                      and its predicate, byte-exact
    derive_hqxgarbage.py --definition the Definition's own sentences,
                                      where this engine leans on them
    derive_hqxgarbage.py --tables     HQXer's two tables and its error
                                      strings, at the resources they sit in
    derive_hqxgarbage.py --code       HQXer's branch, byte-exact
    derive_hqxgarbage.py --absent     UUParser 1.72: the feature is not in
                                      this binary at all
    derive_hqxgarbage.py --author     BinHex 5.0 — Yves Lempereur's own
                                      program, the format's author
    derive_hqxgarbage.py --lewis      DeHQX 2.0.1's BINARY, not the
                                      documentation beside it
    derive_hqxgarbage.py --others     five more readers in the corpus and
                                      the specimen cache
    derive_hqxgarbage.py --length     the HALF this engine declines, and
                                      the trim it keeps, against the corpus
    derive_hqxgarbage.py --grade      the subject, through every reader on
                                      this machine that is not an emulator
    derive_hqxgarbage.py              all of them, skipping what is absent

**HQXEngine, and how it was reached.** It is not a fixture: it is four
layers inside a download this project already had, and this project's
own CLI opens every layer —

    sdk512.hqx -> "StuffIt SDK™ 5.1.2 Installer" (a .sit)
               -> the Installer's DATA FORK is itself a StuffIt archive
               -> Individual Engines/HQXEngine.rsrc, `Eng ` 10000

The resource sets its own A4 (+0x0010: base + 0x5bf8), so its two
displacements are derived here rather than guessed: the 116-byte table
at +24080 is `A4+536` and the alphabet at +24196 is `A4+652`. The decode
path is **+0x0f00 (RLE) -> +0x0dc4 (4->3) -> +0x0d78 (6-bit) -> +0x4ab0
(line reader) -> +0x4a30 (predicate)**, and the predicate's verdict
decides whether the line is served or thrown away (+0x4b1c).

Its predicate is BOTH halves of macutils' rule: a line passes when it is
**63 or 64 characters, or ends at the `:`**, AND every character is in a
71-character set. That set is not quite the alphabet — the branch chain
carves the three runs of non-alphabet characters out of `.`..`_` and
sends the rest to a plain `!`..`r` range check, so `7 : O W g n o` ride
along harmlessly (the table maps each to 0xFF). It rejects SPACE and
TAB. `--engine` simulates the chain over all 256 values rather than
describing it.

**Two things HQXEngine does NOT state, and what covers them instead.**
Neither is macutils' either, which is why that citation could go:

  * **the length half.** HQXEngine wants 63 or 64; this engine tests no
    length at all. The Definition is first-party against it — *"When
    decoding, lines of any length should be accepted"* — and the corpus
    agrees: **0 of 204 `.hqx` fixtures carry a line the length half
    would skip and the alphabet half would keep** (`--length`, whose
    scan is shown to fire by injecting one).
  * **the trailing whitespace trim.** HQXEngine does not trim, so a data
    line a mailer has put a space on is 65 characters, holds a SPACE,
    and is discarded — it loses the file. This engine trims first, and
    the Definition is why: *"`<return>` means to the decoder: Any
    sequence of `<cr>`, `<lf>`, `<tab>`, `<spc>`"*, which names the tab
    and the space outright. **That corrects "THE TAB IS OURS"**, which
    stood in `src/fmt_binhex.c` from 2026-10-06 to 2026-10-07: it is
    Lewis's, in the document this file is transcribed from.
    `--length` measures it: **`country-song-generator-101.hqx` carries a
    trailing space on all 2,600 of its data lines**, so the trim is
    load-bearing on a real corpus file and HQXEngine would read none of
    it.

**And one thing the Definition settles that neither reader does**: an
out-of-alphabet character *"indicates an error and the user should be
notified of such"*. So the line rule is a **departure** from the format
for the sake of mailed text, not an implementation of it — which is
exactly why it needed a second implementation to rest on, and now has
one.

**The twelve that say no.** Seven of the fourteen are Macintosh programs
with a decoder in them. Three answer a character outside the alphabet by
fetching another one — BinHex 5.0, Compact Pro 1.51, Aladdin's own
Deluxe 2 translator — and four give up on the file: HQXer 1.1's alert,
DeHQX 2.0.1's error -7, BinHqx 1.02's error 127, StuffIt Expander
4.0.2's zero-byte output. The remaining six are two encoders, two
programs whose decoder is somewhere else, and the two Linux readers
asked on 2026-10-05. **Aladdin is on both sides of its own answer**: the
Deluxe 2 translator of 1992 skips a character, the SDK engine of 1999
skips a line.

**BinHex 5.0** (`fixtures/binhex-50.hqx`, Yves Lempereur, 1992) is the
author's own program. `CODE` 1 builds a **128**-byte inverse table
filled with `0x80` and writes the 64 alphabet values into it (+0x0b78);
its bit fetcher reads a byte, and on a byte with the high bit set
(+0x0bd2) or a table miss (+0x0bdc) branches back and **fetches another
CHARACTER**. There is no line buffer in the decode path at all. Its one
line-shaped rule is at the START: the opening `:` must be the first
character with a code of 32 or more on its line (+0x0522), which is the
Definition's rule read more strictly than this engine reads it —
`bh_find_colon` allows a space or a tab before it because the Definition
names both.

**DeHQX 2.0.1** (`fixtures/dehqx-201.hqx`, Peter N Lewis) is asked as a
BINARY here; `tools/derive_dehqx.py` asks its documentation. OPEN_ITEMS
said since 2026-10-06 that DeHQX is not a candidate because its answer
to a cut posting is the separator rather than a line test — that was a
claim about its prose, and **the code says the same thing**, which is a
re-test that held. `INITREADHQX` (+0x35ea, the author left his Macsbug
names in) builds a **256**-byte table filled with `0xFF`; the reader
`RB` (+0x398c) skips every character of 32 or less, and on a character
above 32 that misses the table sets **error -7 and stops** (+0x39ee, and
again at +0x3bfc on the slow path). Which is what his own Definition
tells a decoder to do.

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
    in all fourteen readings besides HQXEngine's that is line-shaped,
    and it uses BOTH halves
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


# ------------------------------------------------------------------
# StuffIt's own HQXEngine — the fourteenth reader, and the one that
# says YES. SDK 5.1.2, April 1999; the decoder behind StuffIt Expander
# 5.x. Reached from the download with this project's own CLI:
#
#   sdk512.hqx -> "StuffIt SDK™ 5.1.2 Installer" (a .sit)
#              -> the Installer's DATA FORK is itself a StuffIt archive
#              -> Individual Engines/HQXEngine.rsrc, resource `Eng ` 10000
#
# The resource sets its own A4 at +0x0010: A4 = the resource's base plus
# 0x5bf8, so the 116-byte table at +24080 is A4+536 and the alphabet at
# +24196 is A4+652. Every offset below is in the `Eng ` 10000 body.
# ------------------------------------------------------------------

HQXENG_ARCHIVE = os.path.join(
    os.environ.get("UNC_CACHE", os.path.expanduser("~/.cache/macextract")),
    "sitsdk", "sdk512.hqx")
HQXENG_INSTALLER = "StuffIt SDK™ 5.1.2 Installer"
HQXENG_MEMBER = "HQXEngine.rsrc"
HQXENG_A4 = 23544               # 0x5bf8, from the witness below
HQXENG_TABLE = 24080            # A4 + 536

HQXENG_CODE = [
    # how the resource finds its own globals, so the two displacements
    # below are derived rather than guessed
    (0x0010, "41faffee", "lea %pc@(0x0000),%a0    — the resource's own base"),
    (0x0014, "d1fc00005bf8", "addal #23544,%a0        — A4 = base + 0x5bf8"),
    (0x001e, "c18c", "exg %d0,%a4"),
    # the 6-bit fetcher: it calls a LINE reader, not a byte reader
    (0x0d7e, "4eba3d30", "jsr %pc@(0x4ab0)        — the LINE reader"),
    (0x0d9e, "0c430073", "cmpiw #115,%d3          — past the table"),
    (0x0da2, "6cda", "bges 0xd7e              — fetch another character"),
    (0x0da4, "41ec0218", "lea %a4@(536),%a0       — the 116-byte table"),
    (0x0da8, "197030000abc", "moveb %a0@(0,%d3:w),%a4@(2748)"),
    (0x0dae, "0c2c00ff0abc", "cmpib #-1,%a4@(2748)"),
    (0x0db4, "67c8", "beqs 0xd7e              — a MISS: fetch another"),
    # the line reader
    (0x4abc, "4a6c0aba", "tstw %a4@(2746)         — line mode, set at +0x075e"),
    (0x4acc, "45ec045c", "lea %a4@(1116),%a2      — THE LINE BUFFER"),
    (0x4ae4, "14c3", "moveb %d3,%a2@+         — fill it"),
    (0x4aee, "0c440050", "cmpiw #80,%d4           — its cap"),
    (0x4af4, "0c43000d", "cmpiw #13,%d3           — CR ends the line"),
    (0x4afa, "0c43000a", "cmpiw #10,%d3           — LF ends the line"),
    (0x4b0e, "4ebaff20", "jsr %pc@(0x4a30)        — JUDGE THE WHOLE LINE"),
    (0x4b14, "6608", "bnes 0x4b1e             — accepted: serve it"),
    (0x4b18, "45ec045c", "lea %a4@(1116),%a2      — REJECTED: rewind"),
    (0x4b1c, "60b8", "bras 0x4ad6             — and read the NEXT LINE"),
    # the predicate, which is both halves of macutils' rule
    (0x4a3c, "0c6c003f04b2", "cmpiw #63,%a4@(1202)    — the LENGTH half"),
    (0x4a44, "0c6c004004b2", "cmpiw #64,%a4@(1202)"),
    (0x4a54, "0c30003a0000", "cmpib #58,%a0@(0,%d0:w) — or a line ending ':'"),
    (0x4a5c, "7000", "moveq #0,%d0            — wrong length: not data"),
    (0x4a68, "0440002e", "subiw #46,%d0           — the gap chain, from '.'"),
    (0x4a8a, "0c120021", "cmpib #33,%a2@          — '!'"),
    (0x4a90, "0c120072", "cmpib #114,%a2@         — 'r'"),
    (0x4a96, "7000", "moveq #0,%d0            — the ALPHABET half"),
    (0x4aa4, "7001", "moveq #1,%d0            — every character passed"),
]


def hqxeng_accepts(c):
    """HQXEngine's per-character test at +0x4a64, as the branches run.

    It is not "in the alphabet": the chain carves the three runs of
    non-alphabet characters out of '.'..'_' and sends everything else to
    a plain '!'..'r' range check, so seven strays ride along. They are
    harmless — the 116-byte table maps each to 0xFF and the character is
    skipped — but a reading that called this "the alphabet" would be
    describing our rule rather than theirs."""
    if ((c - 46) & 0xFFFF) > 49:
        return 0x21 <= c <= 0x72
    if c - 48 < 0:
        return False                        # '.' '/'
    if c - 59 < 0:
        return 0x21 <= c <= 0x72
    if c - 64 < 0:
        return False                        # ';' '<' '=' '>' '?'
    if c - 92 < 0:
        return 0x21 <= c <= 0x72
    return False                            # '\\' ']' '^' '_'


def engine():
    """The StuffIt SDK's own HQXEngine: the rule, stated by somebody
    other than macutils. Fourteen readers in, the first yes."""
    work = tempfile.mkdtemp(prefix="dhg-")
    try:
        exe = cli()
        if exe is None or not os.path.exists(HQXENG_ARCHIVE):
            print("  -- StuffIt SDK 5.1.2: no specimen (%s)"
                  % HQXENG_ARCHIVE)
            return 0, 0
        # Two steps, because the Installer is an application whose DATA
        # FORK is a StuffIt archive; nothing auto-recurses into it.
        subprocess.run([exe, "x", "-o", work, HQXENG_ARCHIVE],
                       capture_output=True)
        inst = None
        for dirpath, _d, files in os.walk(work):
            for f in files:
                if f == HQXENG_INSTALLER:
                    inst = os.path.join(dirpath, f)
        if inst is None:
            print("  FAIL the SDK archive does not hold %r"
                  % HQXENG_INSTALLER)
            return 1, 1
        out = os.path.join(work, "eng")
        os.makedirs(out, exist_ok=True)
        subprocess.run([exe, "x", "-o", out, inst], capture_output=True)
        rsrc = None
        for dirpath, _d, files in os.walk(out):
            for f in files:
                if f == HQXENG_MEMBER + ".rsrc":
                    rsrc = open(os.path.join(dirpath, f), "rb").read()
        if rsrc is None:
            print("  FAIL the Installer does not hold %r" % HQXENG_MEMBER)
            return 1, 1
        body = one(res(rsrc), "Eng ", 10000)
        if body is None:
            print("  FAIL HQXEngine has no 'Eng ' 10000")
            return 1, 1

        bad = seen = 0
        b, s = witness(body, HQXENG_CODE, "Eng  10000")
        bad += b
        seen += s

        # The table the fetcher indexes, at the displacement the A4
        # witness above derives.
        seen += 1
        t = body[HQXENG_TABLE:HQXENG_TABLE + 116]
        values = all(t[ALPHA[i]] == i for i in range(64))
        low = all(t[c] == 0xFF for c in range(0x21))
        strays = sum(1 for c in range(0x21, 0x73) if t[c] == 0xFF)
        if values and low and strays == 18:
            print("  ok   'Eng ' 10000 +%d (A4+536): 116 entries, the 64 "
                  "values, 0xFF below '!' and at the 18 strays in range"
                  % HQXENG_TABLE)
        else:
            print("  FAIL that table is not what is claimed (%s/%s/%d)"
                  % (values, low, strays))
            bad += 1
        seen += 1
        if body.find(ALPHA) == 24196:
            print("  ok   the alphabet at +24196 (A4+652)")
        else:
            print("  FAIL the alphabet is at %r" % body.find(ALPHA))
            bad += 1

        # What the predicate actually accepts, simulated from the
        # branches rather than described.
        seen += 1
        ok = {c for c in range(256) if hqxeng_accepts(c)}
        aset = set(ALPHA)
        extra = sorted(ok - aset)
        if aset <= ok and len(ok) == 71 and 0x20 not in ok and 0x09 not in ok:
            print("  ok   its line test accepts all 64 alphabet characters "
                  "and 7 strays (%s), and rejects SPACE and TAB"
                  % " ".join(chr(c) for c in extra))
        else:
            print("  FAIL the predicate accepts %d characters, extra %r"
                  % (len(ok), [chr(c) for c in extra]))
            bad += 1
        print("  ok   SO: a line that is not 63 or 64 long and does not end "
              "at ':', or that holds one character outside that set, is "
              "DISCARDED WHOLE. That is the rule (src/fmt_binhex.c)")
        return bad, seen
    finally:
        shutil.rmtree(work, ignore_errors=True)



# What the Definition itself says, where this engine relies on it.
# Checked verbatim against reference/notes/binhex40_lewis.txt rather
# than quoted, because these two sentences are now load-bearing: the
# first is why the length half is declined and the second is why the
# line rule is a DEPARTURE from the format rather than the format.
DEFINITION = [
    (b"<return> means to the decoder:",
     "the decoder's <return>"),
    (b"Any sequence of <cr>, <lf>, <tab>, <spc>.",
     "...is cr, lf, TAB and SPACE — which is the trailing trim"),
    (b"When decoding, lines of any length should be accepted",
     "lines of any length: the length half, refused first-party"),
    (b"any character other than those 64 and the <return> characters "
     b"indicates an error",
     "an out-of-alphabet character is an ERROR: the line rule is a "
     "departure from the format, not the format"),
]


def definition():
    """The Definition's own sentences, where this engine leans on them."""
    path = os.path.join(ROOT, "reference", "notes", "binhex40_lewis.txt")
    if not os.path.exists(path):
        print("  -- no reference/notes/binhex40_lewis.txt")
        return 0, 0
    text = open(path, "rb").read()
    bad = 0
    for needle, what in DEFINITION:
        if needle in text:
            print("  ok   %s" % what)
        else:
            print("  FAIL the Definition does not say %r" % needle)
            bad += 1
    return bad, len(DEFINITION)


# ------------------------------------------------------------------
# The four siblings of the engine cited above, read 2026-10-07 because
# a citation with a disagreeing sibling is worth knowing about. All
# four agree, and three of them are the same bytes.
# ------------------------------------------------------------------

EXP55_ARCHIVE = os.path.join(
    os.environ.get("UNC_CACHE", os.path.expanduser("~/.cache/macextract")),
    "exp55", "exp55.bin")
EXP55_MEMBER = "StuffIt Expander™"

# Expander 5.5 is the same module recompiled: its globals moved and its
# A4 base went from 0x5bf8 to 0x5c52, so the byte signatures do not
# match and the CONSTANTS do. These are the predicate and the line
# reader at Expander 5.5's own offsets.
EXP55_CODE = [
    (0x0014, "d1fc00005c52", "addal #23634,%a0        — A4, 90 on from 5.1"),
    (0x0d8e, "4eba3b64", "jsr %pc@(0x48f4)        — the LINE reader"),
    (0x0db4, "41ec0218", "lea %a4@(536),%a0       — the table, same offset"),
    (0x487c, "0c6c003f049c", "cmpiw #63,%a4@(1180)    — the LENGTH half"),
    (0x4884, "0c6c0040049c", "cmpiw #64,%a4@(1180)"),
    (0x4894, "0c30003a0000", "cmpib #58,%a0@(0,%d0:w) — or ending at ':'"),
    (0x48ae, "0440002e", "subiw #46,%d0           — the same gap chain"),
    (0x48b2, "0c400031", "cmpiw #49,%d0"),
    (0x48d0, "0c030021", "cmpib #33,%d3           — '!' (in a register "
     "now, not %a2@)"),
    (0x48d6, "0c030072", "cmpib #114,%d3          — 'r'"),
    (0x4928, "14c3", "moveb %d3,%a2@+         — the line buffer"),
    (0x4932, "0c440050", "cmpiw #80,%d4           — its cap"),
    (0x4952, "4ebaff1c", "jsr %pc@(0x4870)        — JUDGE THE LINE"),
    (0x495c, "45ec044c", "lea %a4@(1100),%a2      — REJECTED: rewind"),
    (0x4960, "60b8", "bras 0x491a             — and read the NEXT LINE"),
]

# The PowerPC build, as PEF. No disassembler for it on this machine, so
# what is checked is the one thing that does not need one: the opcode-11
# compares (cmpwi) at the offsets they sit at, in order, and the two
# branches that make it a loop. (code-section offset, constant).
HQXPPC_CMPWI = [
    (0x6ebc, 63, "the LENGTH half"),
    (0x6ec8, 64, ""),
    (0x6f44, 33, "'!'"),
    (0x6f4c, 114, "'r'"),
    (0x6ffc, 80, "the line buffer's cap"),
    (0x7008, 13, "CR ends the line"),
    (0x7010, 10, "LF ends the line"),
]
HQXPPC_BRANCH = [
    (0x702c, "bl", 0x6eb4, "the line reader CALLS the predicate"),
    (0x7040, "b", 0x6fc8, "and on a refusal loops back for the next line"),
]
SDK_HOME = os.path.join(
    os.environ.get("UNC_CACHE", os.path.expanduser("~/.cache/macextract")),
    "sitsdk", "u", "StuffIt SDK™ 5.1")


def pef_code(raw, base=0):
    """The code section of a PEF container at `base`, or None."""
    b = raw[base:]
    if b[:8] != b"Joy!peff":
        return None
    nsec = int.from_bytes(b[32:34], "big")
    off = 40
    for _i in range(nsec):
        hdr = b[off:off + 28]
        if len(hdr) < 28:
            return None
        packed = int.from_bytes(hdr[16:20], "big")
        cont = int.from_bytes(hdr[20:24], "big")
        kind = hdr[24]
        if kind == 0:
            return b[cont:cont + packed]
        off += 28
    return None


# PowerPlug's fourteen containers, each named by the PPC engine whose
# code section it carries byte for byte. The roll-call is here because
# it is this project's only external checklist of Macintosh archive
# formats written by somebody who shipped all of them: twelve are
# formats, one is StuffIt creation and one is a CRC helper, and the
# only format on it this engine does not read is Private File
# (OPEN_ITEMS.md).
POWERPLUG = [
    (0x00000, "UnStuffEnginePPCExt", "StuffIt, expand"),
    (0x38250, "StuffEnginePPC", "StuffIt, CREATE — out of scope here"),
    (0x6f440, "SITEnginePPC", "StuffIt"),
    (0x74e20, "ARCEnginePPC", "ARC"),
    (0x76900, "CMPEnginePPC", "Unix compress (.Z)"),
    (0x7d1f0, "CPTEnginePPC", "Compact Pro"),
    (0x87000, "HQXEnginePPC", "BinHex — the one cited"),
    (0x915f0, "LHaEnginePPC", "LHa"),
    (0x9c1b0, "MIMEEnginePPC", "MIME"),
    (0xb4910, "PFEnginePPC", "Private File — NOT READ HERE"),
    (0xbdd80, "UUEnginePPC", "uuencode"),
    (0xc59e0, "ZIPEnginePPC", "Zip"),
    (0xd16e0, "Seg_JoinEnginePPC", "StuffIt segments"),
    (0xedf30, "CRCEnginePPC", "not a format: a checksum helper"),
]


def powerplug_roll_call(plug):
    """Every container in PowerPlug, named by the engine it carries.

    Matched by the sha256 of the code section against the SDK's own
    named `.shlb` files, so the names are Aladdin's and not a guess."""
    import hashlib
    d = os.path.join(SDK_HOME, "Individual Engines", "PPC Shared Libraries")
    if not os.path.isdir(d):
        print("  -- the SDK's named PPC engines are not here")
        return 0, 0
    known = {}
    for f in sorted(os.listdir(d)):
        if not f.endswith(".shlb"):
            continue
        c = pef_code(open(os.path.join(d, f), "rb").read())
        if c:
            known[hashlib.sha256(c).hexdigest()] = f[:-len(".PPC.shlb")]
    raw = open(plug, "rb").read()
    bad = 0
    for off, name, what in POWERPLUG:
        c = pef_code(raw, off)
        got = known.get(hashlib.sha256(c).hexdigest()) if c else None
        if got == name:
            print("  ok   PowerPlug +0x%05x is %-19s — %s" % (off, name, what))
        else:
            print("  FAIL PowerPlug +0x%05x is %r, not %s" % (off, got, name))
            bad += 1
    # and nothing else is in there
    import re as _re
    n = len(_re.findall(b"Joy!peff", raw))
    if n != len(POWERPLUG):
        print("  FAIL PowerPlug holds %d PEF containers, not %d"
              % (n, len(POWERPLUG)))
        bad += 1
    else:
        print("  ok   and there are exactly %d containers, so the list is "
              "the whole of it" % n)
    return bad, len(POWERPLUG) + 1



def siblings():
    """Aladdin's other four 5.x BinHex decoders, in case one disagrees.

    None does. Two are literally the same bytes as the engine cited in
    `src/fmt_binhex.c`, one is it recompiled, and the PowerPC build is
    the same source through a different compiler."""
    bad = seen = 0

    # 1. The full StuffIt Engine ships the identical module.
    path = os.path.join(SDK_HOME, "StuffIt Engine™.rsrc")
    ours = None
    rsrc, _d = unpack(HQXENG_ARCHIVE, HQXENG_INSTALLER)   # for the control
    if os.path.exists(path):
        from run_sdmodule import resource_data
        raw = open(path, "rb").read()
        # the cache keeps these as AppleDouble; the fork is entry id 2
        if raw[:4] == b"\x00\x05\x16\x07":
            n = int.from_bytes(raw[24:26], "big")
            for i in range(n):
                e = raw[26 + i * 12:38 + i * 12]
                if int.from_bytes(e[0:4], "big") == 2:
                    raw = raw[int.from_bytes(e[4:8], "big"):]
        rs = resource_data(raw)
        ours = one(rs, "Eng ", 10000)
    # the standalone engine, out of the archive, as --engine reads it
    ref = _hqxengine_body()
    seen += 1
    if ours is None or ref is None:
        print("  -- StuffIt Engine™ 5.1: no specimen")
    elif ours == ref:
        print("  ok   StuffIt Engine™ 5.1 ships 'Eng ' 10000 BYTE-IDENTICAL "
              "to the standalone HQXEngine (%d B)" % len(ref))
    else:
        print("  FAIL StuffIt Engine™ 5.1's 'Eng ' 10000 differs from the "
              "standalone engine (%d vs %d B)"
              % (len(ours), len(ref) if ref else -1))
        bad += 1

    # 2. StuffIt Expander 5.5 — the same module recompiled.
    rsrc, _d = unpack(EXP55_ARCHIVE, EXP55_MEMBER)
    if rsrc is None:
        print("  -- StuffIt Expander 5.5: no specimen (%s)" % EXP55_ARCHIVE)
    else:
        body = one(res(rsrc), "Eng ", 0)
        if body is None:
            print("  FAIL Expander 5.5 has no 'Eng ' 0")
            bad += 1
            seen += 1
        else:
            b, s = witness(body, EXP55_CODE, "5.5 Eng  0")
            bad += b
            seen += s

    # 3 and 4. The PowerPC builds.
    shlb = os.path.join(SDK_HOME, "Individual Engines",
                        "PPC Shared Libraries", "HQXEnginePPC.PPC.shlb")
    plug = os.path.join(SDK_HOME, "StuffIt Engine™ PowerPlug")
    if not os.path.exists(shlb):
        print("  -- HQXEnginePPC: no specimen")
    else:
        code = pef_code(open(shlb, "rb").read())
        if code is None:
            print("  FAIL HQXEnginePPC is not a PEF container")
            bad += 1
            seen += 1
        else:
            for off, want, what in HQXPPC_CMPWI:
                seen += 1
                w = int.from_bytes(code[off:off + 4], "big")
                got = w & 0xFFFF
                if got >= 0x8000:
                    got -= 0x10000
                if (w >> 26) == 11 and got == want:
                    print("  ok   PPC +0x%04x  cmpwi %-4d%s"
                          % (off, want, "  — " + what if what else ""))
                else:
                    print("  FAIL PPC +0x%04x  is not cmpwi %d (word %08x)"
                          % (off, want, w))
                    bad += 1
            for off, kind, tgt, what in HQXPPC_BRANCH:
                seen += 1
                w = int.from_bytes(code[off:off + 4], "big")
                li = w & 0x03FFFFFC
                if li & 0x02000000:
                    li -= 0x04000000
                ok = ((w >> 26) == 18 and (w & 1) == (1 if kind == "bl" else 0)
                      and not (w & 2) and off + li == tgt)
                if ok:
                    print("  ok   PPC +0x%04x  %-2s 0x%04x — %s"
                          % (off, kind, tgt, what))
                else:
                    print("  FAIL PPC +0x%04x  is not %s 0x%04x (word %08x)"
                          % (off, kind, tgt, w))
                    bad += 1
        # PowerPlug is fourteen PEF containers in one file; the HQX one
        # is at 0x87000 and its code is the same bytes.
        seen += 1
        if not os.path.exists(plug):
            print("  -- StuffIt Engine™ PowerPlug: no specimen")
        else:
            other = pef_code(open(plug, "rb").read(), 0x87000)
            if code is not None and other == code:
                print("  ok   StuffIt Engine™ PowerPlug bundles that same "
                      "PowerPC code BYTE-IDENTICALLY, at +0x87000 of "
                      "fourteen concatenated PEF containers")
            else:
                print("  FAIL PowerPlug's container at +0x87000 is not the "
                      "same code")
                bad += 1
            b, s = powerplug_roll_call(plug)
            bad += b
            seen += s

    # 5. The client libraries are glue, not decoders: they hold the
    #    alphabet (they report it) and neither the table nor the rule.
    libs = os.path.join(SDK_HOME, "Libraries", "68K Libraries")
    if not os.path.isdir(libs):
        print("  -- the SDK's 68K libraries are not here")
    else:
        for name in sorted(os.listdir(libs)):
            if not name.endswith(".Lib"):
                continue
            seen += 1
            blob = open(os.path.join(libs, name), "rb").read()
            tbl = ref[HQXENG_TABLE:HQXENG_TABLE + 116] if ref else b"\xff" * 116
            if ALPHA in blob and tbl not in blob:
                print("  ok   %s holds the alphabet and no table: it is "
                      "client glue, not a decoder" % name[:44])
            else:
                print("  FAIL %s does not look like glue" % name)
                bad += 1
    return bad, seen


def _hqxengine_body():
    """`Eng ` 10000 out of the SDK archive, the way --engine reads it."""
    work = tempfile.mkdtemp(prefix="dhg-")
    try:
        exe = cli()
        if exe is None or not os.path.exists(HQXENG_ARCHIVE):
            return None
        subprocess.run([exe, "x", "-o", work, HQXENG_ARCHIVE],
                       capture_output=True)
        inst = None
        for dirpath, _d, files in os.walk(work):
            for f in files:
                if f == HQXENG_INSTALLER:
                    inst = os.path.join(dirpath, f)
        if inst is None:
            return None
        out = os.path.join(work, "eng")
        os.makedirs(out, exist_ok=True)
        subprocess.run([exe, "x", "-o", out, inst], capture_output=True)
        for dirpath, _d, files in os.walk(out):
            for f in files:
                if f == HQXENG_MEMBER + ".rsrc":
                    return one(res(open(os.path.join(dirpath, f),
                                        "rb").read()), "Eng ", 10000)
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)



def length():
    """The HALF of hexbin's rule this engine declines, and the trim it
    keeps, against the corpus.

    `hqx.c` also skips any line whose length differs from the first
    line's, and StuffIt's HQXEngine wants 63 or 64. `src/fmt_binhex.c`
    transcribes neither, and the Definition is why — "lines of any
    length should be accepted", checked above. This is the corpus half
    of the same question, and it also measures the TRIM, which is the
    other thing a line-judging reader has to get right.

    The scans are shown to fire by injecting a line, because a scan that
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

    # THE TRIM, which is the same question from the other side: a line
    # of data that a mailer has put a space on the end of. We trim it
    # and read the file; HQXEngine does not trim, so its length test
    # sees 65 and its character test sees a space, and it discards every
    # data line in such a file. This counts them.
    trimmed = []
    for p in files:
        raw = open(p, "rb").read()
        lines = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
        start = next((k for k, l in enumerate(lines)
                      if l.strip().startswith(b":")), None)
        if start is None:
            continue
        n = 0
        for k in range(start, len(lines)):
            core = lines[k].rstrip(b" \t")
            if not core:
                continue
            if all(c in alpha for c in core) and lines[k] != core:
                n += 1
            if core.endswith(b":"):
                break
        if n:
            trimmed.append((os.path.basename(p), n))
    seen += 1
    if trimmed:
        print("  ok   the trim is load-bearing: %s"
              % ", ".join("%s (%d data line(s) with trailing whitespace)" % t
                          for t in trimmed[:3]))
        print("       every one of those lines is 65 characters and holds a "
              "SPACE, so HQXEngine discards it and loses the file")
    else:
        print("  NOTE no fixture carries trailing whitespace on a data line, "
              "so the trim is unexercised by this corpus")

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
    ap.add_argument("--engine", action="store_true")
    ap.add_argument("--siblings", action="store_true")
    ap.add_argument("--definition", action="store_true")
    ap.add_argument("--length", action="store_true")
    ap.add_argument("--grade", action="store_true")
    a = ap.parse_args()
    allof = not (a.tables or a.code or a.absent or a.author or a.lewis
                 or a.others or a.engine or a.siblings
                 or a.definition or a.length or a.grade)
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
                           (a.engine or allof, engine,
                            "StuffIt's own HQXEngine — THE RULE, stated"),
                           (a.siblings or allof, siblings,
                            "the engine's four siblings — do they agree?"),
                           (a.definition or allof, definition,
                            "the Definition, where this engine leans on it"),
                           (a.length or allof, length,
                            "the half this engine declines, and the trim"),
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
        print("derive-hqxgarbage: the rule is StuffIt HQXEngine's too — "
              "fourteen readers asked, the fourteenth states it, and "
              "macutils has left src/fmt_binhex.c (NOTICE)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

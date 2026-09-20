# DiskDoubler's DD coder (method 10)

**The inventory said "documented nowhere else". It is documented.**
The Unarchiver's format wiki has a page for it, and
`tools/fetch_references.sh` fetches it since 2026-09-20:
`reference/notes/dd_dd_theunarchiver.md`. Its sibling
`dd_specs_theunarchiver.md` names what every DiskDoubler method is —
and confirms, independently of this project, that method 8 is Compact
Pro's coder "with blocksize 0xfff0 instead of 0x1fff0".

**This row is NOT closed**, and the number below is why.
`tools/derive_dd.py` is a reader written from that page alone — no
container parser, because the wiki does not document DiskDoubler's
containers ("see XADDiskDoublerParser.m for now") and this reader is
not allowed to; it finds blocks by the checksum every DD block header
carries. It reads **32 of the corpus's 34 DDn forks** byte for byte
against the oracle's sha256. Two it does not, and nobody here knows
why yet.

## The corrections

**1. The streams are in the page's stated order, not the header's.**
The block header lists the compressed sizes as run lengths, literals,
offsets. The data is **offset, literal, run length** — which the
page's prose does say, and which a reader that follows the header's
field order gets wrong.

**2. The selector table, not the formula.** The page gives 32 offset
selectors as a table AND as `((2+(selector&1))<<bits)+1`. They
disagree for selectors 0 to 3, whose bases are 1, 2, 3 and 4 with no
extra bits. The table decodes; the formula does not.

**3. "The code plus two (maybe)" is plus two.** The parenthesis can
go.

**4. The window spans blocks, so the output must too.** The page says
matches "in later blocks can reference data from earlier blocks" — so
a decoder that assembles each block into its own buffer and
concatenates is wrong wherever a fork needs more than one block. That
is not an edge case: it is every fork over about 12 KB.

**5. The page does not say how codes are derived from lengths.** Only
the lengths are transmitted. Canonical codes — shortest first,
assigned in symbol order, read most-significant-bit first — is what
decodes; three other conventions were tried and read nothing.

## What the page gets right

The 22-byte block header and every field in it, including the XOR
checksums (byte 21 over the twenty before it, which is what lets a
reader find blocks at all without a container). The Huffman header:
a big-endian `u32` packing the entry count, the byte count of the
length data, the maximum length, the bits per length and the
zero-coding flag, then the lengths, then the data at four plus that
byte count. The flags: bit 6 an uncompressed block, bit 7 Huffman
literals. The run-length stream's three cases — 0 a literal, under
128 a match, 128 or over a run of `2^(code-128)` literals — and the
observation that 0 and 128 do the same thing, which they do.

## The two forks it does not read

`derived-Terrainman_2.0__.sea`, the 19,240-byte and 16,524-byte data
forks of two pictures. Both are genuinely method 10 (a scratch build
that prints each fork's method says so), both decode to the right
LENGTH without any error, and both diverge after a few hundred bytes —
the literal stream yields a symbol the output disagrees with, while
all three of that block's code tables satisfy Kraft's equality
exactly and the first two literals come out right. No match in them
reaches back before the fork's start. The block beside them in the
same archive, same flags and same shape, reads perfectly.

It is not the XADMaster DDn defect this project has a reproduction
for: that one is an input BOUND a byte short
(`tools/xadmaster-ddn-repro/`), not a decoding rule, and this reader
does not use a bound.

**What would close it:** an explanation of those two forks. Until
there is one, `src/fmt_dd.c` keeps citing `XADDiskDoublerParser.m` for
method 10, because 94 % of a format is not a description of it.

## Not covered at all

DiskDoubler's **containers** — the wiki punts them to the source — and
the **AD** coder of methods 6 and 9, whose page
(`reference/notes/dd_ad_theunarchiver.md`) is fetched and has not been
held against anything.

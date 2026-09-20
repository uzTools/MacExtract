# DiskDoubler's DD (method 10) and AD (methods 6 and 9) coders

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
carries. It reads **32 of the corpus's 34 DDn forks** and **all 5 of its AD
forks** byte for byte against the oracle's sha256 — 37 of 39. Two it
does not, and nobody here knows why yet.

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
LENGTH without any error, and the block beside them in the same
archive — same flags, same shape — reads perfectly.

What has been established about them, so nobody starts over:

- **the structure is right.** The block header states the number of
  literals and the number of offsets, and a decode that ignores those
  fields consumes **exactly** the stated counts: 5,443 literals and
  3,380 offsets in one, 7,583 and 2,379 in the other. So the run
  stream's literal/match decisions, and the number of offsets they
  ask for, are being read correctly;
- **the output POSITIONS stay right.** Substituting the true byte for
  each literal and carrying on, the literals still land at the output
  offsets the correct file has them at, for hundreds of symbols. So
  match lengths and offsets are right too;
- **it is literal VALUES, and not all of them.** Of the first thirty
  literals, nineteen decode correctly — including a 10-bit and an
  11-bit code, which is not luck — and eleven do not;
- **and the wrong ones are not a permutation.** Two literals that
  share a code (`101000`) want different bytes, which a prefix code
  cannot do. Since a canonical code's SET of bit strings is fixed by
  the lengths alone, and those lengths satisfy Kraft exactly, either
  the length list is not what it appears to be for these blocks or
  the stream carries something between literals that this reader does
  not know about.

No match in either reaches back before the fork's start, and
descending-length code construction (the other plausible convention)
decodes nothing at all.

It is not the XADMaster DDn defect this project has a reproduction
for: that one is an input BOUND a byte short
(`tools/xadmaster-ddn-repro/`), not a decoding rule, and this reader
does not use a bound.

**What would close it:** an explanation of those two forks. Until
there is one, `src/fmt_dd.c` keeps citing `XADDiskDoublerParser.m` for
method 10, because 94 % of a format is not a description of it.

## AD, methods 6 and 9

`reference/notes/dd_ad_theunarchiver.md` describes a simpler thing: no
Huffman at all, a 12-byte block header with the same
XOR-of-the-preceding-bytes trick, and an LZSS whose dictionary is the
block rather than a sliding window — 4,096 bytes for method 9, 8,192
for method 6. The bit stream is most-significant-bit first: `0` and
eight bits is a literal; `1` then a bit choosing an eight- or
twelve-bit offset, then a length as a little prefix code (`0` two
bytes, `100` three, `101` four, `11` plus four bits that many plus
five). The page is right about all of it, and gives the length rules
twice — once as prose and once as a code table — which is how a reader
can check itself.

**One correction.** The page says "bit 0 of the flags field indicates
whether the block is compressed or not" and does not say which way
round. It is set for an **un**compressed block: the first block of
`derived-DandStoQIF2.sea` puts 2,752 bytes in and 4,096 out with that
bit clear.

All five AD forks in the corpus read.

## Not covered at all

DiskDoubler's **containers** — the wiki punts them to the source.

# DiskDoubler's DD (method 10) and AD (methods 6 and 9) coders

**The inventory said "documented nowhere else". It is documented.**
The Unarchiver's format wiki has a page for it, and
`tools/fetch_references.sh` fetches it since 2026-09-20:
`reference/notes/dd_dd_theunarchiver.md`. Its sibling
`dd_specs_theunarchiver.md` names what every DiskDoubler method is —
and confirms, independently of this project, that method 8 is Compact
Pro's coder "with blocksize 0xfff0 instead of 0x1fff0".

`tools/derive_dd.py` is a reader written from that page alone — no
container parser, because the wiki does not document DiskDoubler's
containers ("see XADDiskDoublerParser.m for now") and this reader is
not allowed to; it finds blocks by the checksum every DD block header
carries. It reads **all 34 of the corpus's DDn forks** and **all 5 of
its AD forks** byte for byte against the oracle's sha256 — **39 of
39** — once method 10's second form is added, which the page names and
does not describe. That is correction 6 below.

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

**6. Method 10 has two forms, and the page describes one.** The page
names method 10 "DD1" and "DD2" and then describes a single coder. In
the second form what the coder produces is not the fork but the fork's
**first difference**: the fork is the running sum, `out[i] =
out[i-1] + s[i]`, starting from zero. The transform is outside the
coder, not inside its literal stream — matches copy differences, so a
decoder that integrates only the literals gets the first few hundred
bytes right and then drifts (BLOCKERS.md, *"The DD reader's structure
is right; it is literal VALUES that are wrong"*).

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

## The second form, and which forks use it

Two forks of `derived-Terrainman_2.0__.sea` — the 19,240-byte and
16,524-byte data forks of two pictures — are the corpus's only ones in
the delta form, and they read with it. What identified it was a
literal-substitution trace: feeding the true byte at every literal
position and comparing the symbol the stream actually carried,
**all 5,443 literals of one fork were the difference from the previous
output byte and not the byte itself**, while only 167 of its 3,380
matches copied the right source — which is what says the transform is
over the whole stream rather than over the literals.

### Which form a fork uses

That is a container fact, and the container is not described here. But
the corpus states it twice, and the two statements agree on all **186
forks** in it:

- the fork's **method byte** — `h[16]` for the data fork and `h[17]`
  for the resource fork, where `h` is the header that follows the
  `AB CD 00 54` marker — is `0x8a` rather than `0x0a`, so **bit 0x80
  of the method byte** selects it;
- the **u16 at `h+50`** (`h+52` for the resource fork) is 1 rather
  than 0.

Both are set on exactly those two forks and on nothing else. Two
fields that agree on every specimen cannot be told apart by any
specimen here, so this note names both and claims neither.
`tools/derive_dd.py` reads no container at all: it tries the plain
form and then the delta form, and reports which read.

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

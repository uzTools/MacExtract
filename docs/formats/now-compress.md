# Now Compress — four coders, its blocks and its archive

**This is the only format left in this project's inventory with no
published description of any kind.** There is no wiki page for it, no
specification, and no second implementation: `XADNowCompressHandle.m`
is the whole of what anyone has written down. So unlike Compact Pro,
StuffIt method 13 or DiskDoubler, this one could not be fetched. It
had to be measured.

**What it was measured from.** `tools/vmac/nowcompress.py` drives Now
Compress itself under the emulator and compresses files chosen here,
keeping each input beside its output. This note is what reading those
pairs yields, and `tools/derive_now.py` re-runs the reading.

**How much of the format this is.** All four of its coders, its block
structure and its **archive container** — enough to read every
compressed specimen the harness has made, and **every block of both of
the corpus's real archives**: the 1993 `derived-Expand_Now_1.0.1.sea`,
3 blocks of 3, and the 1995 `derived-SyntheticReferences2.0.sea`, 306
of 306, whose 9.9 MB fork alone is 304 blocks of the coder an archive
uses. **Nothing in a shape-3 block is searched for any more**: the
header says where its stream starts, where it ends, and what the four
bytes after it check. What is left is named under *What this note does
NOT describe*, and the largest of it is where a shape-2 stream begins.

## A fork is a sequence of blocks

**32,768 bytes each**, and each coded its own way — the format's own
test data says Now Compress "compresses a fork at a time, in blocks",
and it means it. `mixed.bin` is one **stored** block of 32,768 bytes
followed by one **Huffman-coded** block of 16,232, in a single fork.
So "which coder does Now Compress use" has no answer: it is a
per-block choice.

**Where each block begins is a table in the fork header**, and it is
decoded here. From offset **144**, records of **eight bytes** — a u16
offset, a u16 mode, and four bytes that are zero in every specimen —
ending with a record whose offset is **the fork's own byte count**,
which is how a reader knows it has them all.

| fork | records |
|---|---|
| `runs.bin`, Faster | (162, `0x0010`), (290 = its size) |
| `runs.bin`, Smaller | (162, `0x001f`), (290) |
| `half.bin`, Smaller | (162, `0x003f`), (8,950) |
| `mixed.bin`, Stored | (170, `0x0000`), (32,942, `0x003f`), (33,430) |

The block's data begins a fixed distance after its record's offset:
**none** for a stored block, **two** bytes for shape 1, **one** for
either Huffman shape, and none for shape 3.

**The mode word is a set of layers, not a number.** The **low five
bits** say the block is LZSS-coded, **`0x20`** that a Huffman code sits
over it, **`0x40`** that the block uses the archive coder, and
**`0x100`** that it is inside an archive. That gives the five
arrangements the corpus has:

| mode | what the block is |
|---|---|
| `0x0000`, `0x0100` | stored |
| `0x0010`, `0x001f` | shape 1, LZSS alone — the low bits are the user's Faster/Smaller setting and not the coder, which is why the two `runs.bin` forks are byte-identical except for that word |
| `0x0020`, `0x0120` | **Huffman alone**: one symbol per output byte, no framing |
| `0x003f` | shape 2, Huffman over shape 1's stream |
| `0x0040`, `0x0140` | shape 3, the archive coder |

**`0x20` alone is not `0x3f` with the low bits missing**, and reading it
as one is why the 1993 archive's middle block and two members of the
`tokdist` case could not be placed until 2026-09-21: a Huffman-only
block has no flag bits and no matches at all, and its stream starts
**one byte** after its table in all three.

## Shape 1 — byte-aligned LZSS

The payload begins **164 bytes into the fork** in every specimen that
uses it, with a mode word of `0x0010` (*Faster*) or `0x003f`
(*Smaller* and *Stored*) at offset 2.

- a **flag byte**, then eight tokens, bits **most significant first**;
- a **1** is a literal: one byte, copied out;
- a **0** is a match: **`length - 2`, then the distance**, one byte
  each — **except** that a length byte of **zero is an escape**, and
  the token is then three bytes: the zero, the distance, and
  `length - 2`.

A match copies 2 to 257 bytes from at most 255 back.

## Shape 2 — the same framing, Huffman-coded

A block may instead code **every byte of shape 1's stream** —
including its flag bytes — through one Huffman code of 256 symbols.

- the code arrives as **256 lengths of four bits each**, 128 bytes,
  high nibble first, and **Kraft's equality is what identifies it**:
  exactly 1.000000 where the table is and nowhere else in the fork;
- codes are **canonical**: shortest first, assigned in symbol order,
  read most-significant-bit first;
- then the stream, which begins a few bits after the table — **what
  sits between them is not understood**, so this reader searches a
  byte or two for it;
- a **flag symbol**, then eight tokens as before, a 1 being a literal
  symbol;
- a **match is two symbols**: `length = (S & 7) + 2` and
  `distance = ((S >> 3) << 8) | D`, an 11-bit reach where shape 1 had
  8. **A length of 2 escapes**: the low three bits zero means the real
  `length - 2` is a third symbol.

**The tell that this shape is shape 1 underneath** is that in a file
of incompressible data the shortest code in the table belongs to
symbol **255** — because a flag byte of eight literals IS `0xff`, and
it occurs once per eight bytes. That is what unpicked it: a `0xff`
appearing between correct literals, every nine symbols, emitting
nothing.

### Huffman alone — the same table, no framing at all

A block whose mode is `0x20` (or `0x120` in an archive) carries the
same 128-byte table one byte into the block, and then **one symbol per
output byte**: no flag bits, no matches, nothing else. Its stream
starts **one byte after the table**, and does so in all three blocks
that use it — the 1993 archive's middle block, which is where
FORMATS.md's "Huffman-only" shape comes from, and two members of the
`tokdist` case.

This is the shape a naive reading loses: `0x3f` also has `0x20` set, so
a reader that tests that bit alone decodes a Huffman-only block as
though flag bytes were in it, and gets plausible bytes out for exactly
one symbol.

## Shape 3 — the coder an archive uses

A block whose mode has bit `0x40` codes literals, lengths and
distances through **two Huffman codes**, and it is what a `.sea`'s
members are made of. It is also the shape the corpus's two real
archives are almost entirely written in.

### The header, and the two places it says where the stream starts

- byte 0 is **`0x2f`** in every shape-3 block known;
- **byte 1 is the stream's byte offset within the block, plus 85** —
  exact on all 381 blocks read here, both corpus archives included, and
  the 85 is a constant this note cannot account for;
- byte 2 is **not identified**, and 377 blocks say what it is not: it
  is no bitmap of the lengths or distances a block uses (its eight bits
  were tested against every such predicate), no ratio of literals to
  matches, and no count of either. Over the 1995 archive its values
  cluster in `0x60..0x7f` and `0xf0..0xff`, and on one probe's members
  it climbs with the shortest match — 224, 240, 248, 252, 254, 255 for
  matches of 3 to 8 — and then stops meaning that on every other
  block;
- **byte 4 is where it BEGINS**: the bits between the end of the two
  tables and the stream come to **(16 − byte 4) mod 16** — nought when
  that byte is nought. So the header says it twice, and the two
  accounts agree on every block, which is what says either is right;
- **byte 3 is where the stream ENDS**, the same arithmetic: after the
  last token come **(16 − byte 3) mod 16** bits of flush and then the
  four-byte trailer;
- **bytes 5..12 are a code-length code**: sixteen four-bit lengths,
  one per length 0..15, and **Kraft's equality is exact on every
  specimen**. Both tables that follow are written in it;
- bytes 13..15 are **24 bits this note cannot account for**, zero in
  every specimen; the first table starts at **bit 128**.

Bytes 3 and 4 read as a bit count in a **16-bit register** — how many
of its bits were still free when the encoder flushed, nought meaning
nothing to flush. That is a guess at the why; what is measured is the
arithmetic, and it is exact on every block of both corpus archives and
every specimen.

**The `mod 16` was not free.** Derived from the 75 blocks the harness
and the 1993 archive supply, the rule read "16 − byte 4" and byte 4 was
never nought in any of them. The 1995 archive has twenty blocks where
it is, and there the stream starts at the tables' end exactly: a rule
fitted to 75 blocks was wrong on the 306 it had not seen, and the
disagreement between the header's two accounts of the same number is
what caught it.

### The main table — 290 entries, zeros and all

One code length per symbol, each written in the code-length code,
and **the count is fixed at 290**: 256 literals, then 257..289 for the
match lengths. Symbol 256 is used by nothing seen here.

**Reading it as "until the code completes" is wrong**, which is what
this note said on 2026-09-21 and what cost the reading of four
specimens: the code often completes before symbol 289 and the
remaining entries are written as **zeros**, so a reader that stops
early starts the NEXT table at the wrong bit and gets a table that
still looks plausible. What says 290 is right is that every block then
decodes byte for byte.

**A code of one symbol is written with a length of 1**, and so does not
satisfy Kraft's equality at all — 0.5, not 1. `runa.bin`, 4,000 bytes
of a single byte, is the case: its main table codes **one match symbol
and no literal whatever**, its distance table one class, and the byte
it repeats comes from the member before it. That is the window
spanning members at its starkest, and it is why a reader must not
require completeness of either table.

### The distance table, and a stored value that is not the length

Immediately after it, in the same code-length code, comes the code for
the **56 distance classes**. Two things about it:

- **the stored value is the code length PLUS TWO.** Kraft's equality
  is what says so: over the stored values it comes to 0.25 on every
  table with more than one symbol, and to exactly 1.000000 once two
  is subtracted;
- the table stops when the code is complete, and **zeros for the
  classes the block does not use follow** — as many as the encoder
  chose to write, which varies between blocks of the same file.

### Then the stream, where the header says

Every block's stream starts at a **multiple of eight bits**, and the
header gives the multiple twice: `(byte 1 − 85) × 8`, and the end of
the 290 + 56 table entries plus `16 − byte 4`. Nothing is searched for.

**Until this was read, it was a search**, and the search is what made
the arithmetic findable: reading 75 blocks with the boundary found by
trial produced a table of "how many bits past the tables", and byte 4
was 16 minus that number every time — every time in those 75, which is
not the same as every time.

### The tokens

- a symbol **below 256** is a literal byte;
- a symbol **257..289** is a match: its **length class** (below), then
  that class's extra bits, then a **distance symbol** from the second
  table, then that class's extra bits;
- **the window spans members.** A match may point back past the
  beginning of the member being decoded, into what the archive
  produced before it — which is why `nowcompress.py --case probe`
  found a defect the corpus could not (DECISIONS.md 2026-09-21, *the
  window that stopped at the fork*).

**The length classes.** 257..271 ARE the lengths 3..17; then the
classes widen. **289 spans 226..257, so 257 bytes is the longest match
this format has.**

| symbols | extra bits | lengths |
|---|---|---|
| 257..271 | 0 | 3..17, one each |
| 272, 273 | 1 | 18-19, 20-21 |
| 274..278 | 2 | 22-25, 26-29, 30-33, 34-37, 38-41 |
| 279..281 | 3 | 42-49, 50-57, 58-65 |
| 282..285 | 4 | 66-81, 82-97, 98-113, 114-129 |
| 286..289 | 5 | 130-161, 162-193, 194-225, 226-257 |

**The distance classes.** 1..7 ARE the distances 1..7; 8..27 go four
to an octave; 28..35 are eight classes of 256; above that the width
doubles every four.

| symbols | extra bits | first distance of each |
|---|---|---|
| 1..7 | 0 | 1, 2, 3, 4, 5, 6, 7 |
| 8..11 | 1 | 8, 10, 12, 14 |
| 12..15 | 2 | 16, 20, 24, 28 |
| 16..19 | 3 | 32, 40, 48, 56 |
| 20..23 | 4 | 64, 80, 96, 112 |
| 24..27 | 5 | 128, 160, 192, 224 |
| 28..35 | 8 | 256, 512, 768, 1024, 1280, 1536, 1792, 2048 |
| 36..39 | 9 | 2304, 2816, 3328, 3840 |
| 40..43 | 10 | 4352, 5376, 6400, 7424 |
| 44..47 | 11 | 8448, 10496, 12544, 14592 |
| 48..51 | 12 | 16640, 20736, 24832, 28928 |
| 52..55 | 13 | 33024, 41216, 49408, 57600 |

The last class ends at **65,791**, which is the number this project
measured off its own engine's offset table from the other side on
2026-09-21 — `0xe100` plus thirteen extra bits (DECISIONS.md, *the
window that stopped at the fork*). Nothing writes past 32,768: the
window is what bounds it, not the table.

### The trailer — a sum, not a CRC, and not shape 3's alone

**A block's last four bytes are the 32-bit sum of every byte before
them in the block**, header and tables included. Exact on all 75
shape-3 blocks the harness and the 1993 archive supply — and on the
shape-1 and shape-2 blocks of the bare forks too, where this note had
recorded the four bytes as "presumably a checksum" without saying of
what. It is the one check this reader can apply to a block whose output
nobody knows.

It is not a CRC of the OUTPUT, which is what a decoder would want and
what this note looked for first: sum, Adler-32, CRC-32 and two CRC-16s
over the decoded bytes match nothing. The encoder checks its own
compressed bytes, not its reconstruction.

### How the two tables were made legible

**Not by staring at the bits.** Each was measured against matches
planted at a length and a distance chosen here:
`nowcompress.py --case tokdist` and `--case toklen` build members out
of a **de Bruijn sequence of order 2 over 256 symbols**, in which no
pair of bytes ever repeats — so an LZ encoder can find no match in it
at all — and then append a copy of the member's own first bytes. The
one match in the member is therefore of a known length at a known
distance, and the token's bits can be read off against it. Forty
distances from 2 to 16,384 and twenty-four lengths from 2 to 255.

## The archive layer

**An archive is not a fork**, and treating one as a fork is why the
corpus's two real specimens read as nonsense for a year. What sits at
144 in them belongs to a member, not to the file.

- the file header's **word 5 is the member count**;
- **member records start at 24 and are 110 bytes each**: a Pascal
  name in the first ten bytes, the member's uncompressed size at +88,
  and the bounds of its data area at **+98** and **+102**. A record
  whose bounds do not parse is a FOLDER — the 1995 archive opens with
  one — and carries no data area;
- a member's data area opens with the same header tail a bare fork
  has — the **first block's offset** at +2 — and then its **block
  table**, the same eight-byte records.

**The table sits at one of two places and the header says which.**
The first record must repeat the first-block offset the header states.
In everything Now Compress 5.0.1 wrote the table is at **+10**, with
two words this note cannot name (`0d4c`, `0037`) in between; in the
corpus's 1993 `derived-Expand_Now_1.0.1.sea` those two words are
absent and the table starts at **+2**.

**An archive over 64 KB widens the record.** The 1995 archive
addresses 2.9 MB, which a u16 offset cannot reach, so its records are
a **u32 offset and a u16 mode** in the same eight bytes. The
terminator — a record whose offset is the member's end — is what says
which width is right.

**A record whose offset repeats the one before it is a fork
boundary**: it produces no bytes, and the next block starts the
member's other fork. That is how the 1995 archive's `SynRef2.0 INFO`
carries a 332-byte resource fork and a 574-byte data fork in one
member; the stream is the **resource fork first**.

**FORMATS.md had the 1993 archive's shape sequence already.** Its
*Now Compress* section has recorded since 2026-08-15, from
instrumenting the engine's block loop, that this archive is "three
blocks, 'new' LZSS twice and Huffman-only once" — which is `0x40`,
`0x20`, `0x40` in that order. The walk above reproduces it from the
file, and now decodes two of the three: 32,768 + 32,768 + 23,406 is
88,942, the fork's size exactly.

## What the specimens show

| mode | file | bytes | stream | read as |
|---|---|---|---|---|
| Faster | `runs.bin` | 7,400 | 290 | shape 1 |
| Faster | `prose.txt` | 6,660 | 386 | shape 1 |
| Smaller | `runs.bin` | 7,400 | 290 | shape 1, byte-identical to Faster's |
| Smaller | `prose.txt` | 6,660 | 386 | shape 1, byte-identical to Faster's |
| Smaller | `half.bin` | 16,000 | 8,950 | **shape 2**, table at 163 |
| Stored | `mixed.bin` | 49,000 | 33,430 | **two blocks**: stored 32,768, then shape 2 |
| Archive | 2 members | 49,000 + 7,500 | — | stored, then shape 3 |
| probe | 4 members | 22,000 | — | shape 3 |
| reach | 5 members | 80,000 | — | shape 3 |
| tokdist | 40 members | 82,656 | — | 38 shape 3, 2 Huffman-only |
| toklen | 24 members | 34,641 | — | shape 3 |

**Every compressed block of every one of them reads byte for byte
against the bytes that went in** — 76 of 76, the two Huffman-only
blocks in `tokdist` included.

And so do the corpus's real archives, graded against this project's
own extraction of them — which is itself adjudicated, the 1993 one by
`unar` and the 1995 one by its own self-extractor (FORMATS.md, *Now
Compress*):

| archive | blocks | read |
|---|---|---|
| `derived-Expand_Now_1.0.1.sea` (1993) | 3 — shape 3, Huffman, shape 3 | 3 |
| `derived-SyntheticReferences2.0.sea` (1995) | 306, all shape 3 | 306 |

## What this note does NOT describe

- **Where a shape-2 block's bit stream begins**, the same question one
  layer down: 23 bits after its table in one specimen and 18 in
  another, and those two are all the specimens there are. Neither the
  symbol count nor the deepest code predicts it. A Huffman-ONLY block
  has no such trouble — one byte, three times out of three — so
  whatever the gap carries belongs to the LZSS layer over it.
- **A shape-3 block's header byte 2**, the one of its four this note
  cannot read, and the 24 bits between its code-length code and its
  first table, zero in every specimen.
- **The rest of the fork header**, of which this note identifies the
  version word, the mode word, a ten-byte name field, two Mac dates, a
  `'????'`/`'UNIX'` type and creator — the harness's, not the
  format's — and the block table at 144.
- **Whether there are more shapes.** Four coders and "stored" account
  for every block in every specimen here, and that is five
  arrangements — which is what PROGRESS.md has called Now Compress's
  "five stream shapes" since M12. This note said on 2026-09-21 that
  the two counts were about different things; they are not, and the
  disagreement was this note's.

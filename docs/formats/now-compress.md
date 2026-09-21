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
uses. **Nothing in any block is searched for any more**: a shape-3
block's header says where its stream starts and ends, a shape-2 block's
stream starts a fixed distance after its table, and every block's last
four bytes check the rest of it. What is left is named under *What this
note does NOT describe*, and it is small.

## A fork is a sequence of blocks

**32,768 bytes each**, and each coded its own way — the format's own
test data says Now Compress "compresses a fork at a time, in blocks",
and it means it. `mixed.bin` is one **stored** block of 32,768 bytes
followed by one **Huffman-coded** block of 16,232, in a single fork.
So "which coder does Now Compress use" has no answer: it is a
per-block choice.

**Where each block begins is a table in the fork header**, and it is
decoded here. From offset **144**, records of **eight bytes** — a u16
offset, a u16 mode, **a u16 padding count** and a u16 that is zero in
every specimen — ending with a record whose offset is **the fork's own
byte count**, which is how a reader knows it has them all.

**The padding count is how many bytes sit between a block's stream and
its four-byte checksum.** It is 1 on four of the harness's shape-1
blocks and 0 on every other block here, and what says so is that the
shape-1 decoder stops exactly `padding + 4` bytes before the next
block's offset on all six. This note called those four bytes "zero in
every specimen" until 2026-09-21; two of them are this field, and
FORMATS.md's "zero padding" for the 1993 archive is the same number
read off the engine.

**Where this one came from**, because a note kept for a licence had
better say which facts are whose: `src/fmt_now.c` subtracts a
`padding` field when it computes a block's length, and that file is
transcribed from XADMaster. The check above is what makes it a
measurement here rather than a borrowing. **Three facts in this note
came that way** — this one, the block table's own checksum below, and
the code-length escape named at the end;
everything else was read out of the encoder's output before that file
was opened, and the commit of 2026-09-21 is the record of which came
first.

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

The block opens with the two bytes **`00 03`**, constant in every
specimen and in every shape that carries an LZSS layer, and then the
stream. (In a bare fork that puts the first token at byte **164**,
which is what this note recorded before it knew what the two bytes in
front of it were.)

- a **flag byte**, then eight tokens, bits **most significant first**;
- a **1** is a literal: one byte, copied out;
- a **0** is a match, **two bytes holding a 3-bit length and a 13-bit
  distance**: `length = (b0 & 7) + 2`, `distance = ((b0 >> 3) << 8) |
  b1`, and a length of 2 — the low three bits zero — escapes to a
  third byte carrying `length - 2`.

A match copies 2 to 257 bytes from at most 8,191 back.

**This note read that as "a length byte, then a distance byte" until
2026-09-21**, and every shape-1 specimen here obeys both readings:
they agree whenever the distance is under 256, and not one match token
in six shape-1 blocks has a first byte of 8 or more. What settles it is
the shape next door. Shape 2 is this stream Huffman-coded, its match
rule has always been read here as the 13-bit one, and **1,340 of its
2,162 match tokens are in the range where the two readings differ**,
with distances up to 7,205 — decoding byte for byte. Two rules that
agree on every specimen you have are not one rule; the counter-example
was one layer up.

## Shape 2 — the same framing, Huffman-coded

A block may instead code **every byte of shape 1's stream** —
including its flag bytes — through one Huffman code of 256 symbols.

- the code arrives as **256 lengths of four bits each**, 128 bytes,
  high nibble first, and **Kraft's equality is what identifies it**:
  exactly 1.000000 where the table is and nowhere else in the fork;
- codes are **canonical**: shortest first, assigned in symbol order,
  read most-significant-bit first;
- then **one zero byte**, whose meaning is unknown and whose value is
  0 in every block seen, in this shape and in Huffman-only. A
  hypothesis, not a measurement: it is two more four-bit entries, for
  a 258-symbol alphabet whose last two symbols no block ever uses —
  which is the shape of shape 3's main table, where symbol 256 is
  likewise always absent;
- then the LZSS stream — **starting with the `00 03` that opens a
  shape-1 block**, coded through this table like every other byte;
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

**And the same fact closed the one question left about this shape.**
Where its stream begins was recorded here as unknown — "23 bits after
the table in one specimen and 18 in another" — and both numbers are
the zero byte plus those two symbols, whose codes are as long as that
block's table makes them. The gap was the prefix, and ten blocks now
say so: the two it was measured on and the eight of
`nowcompress.py --case huffgap`, which exists because two specimens
could not tell a rule from a coincidence. What made it look
like a gap is that a reader which starts at the prefix sees a flag
byte of `0x00` — eight matches — and the first of them points 255
bytes back at output position nought, so it fails, and fails in a way
that looks like a wrong starting position rather than a wrong
assumption about what the stream opens with.

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
  the 85 is a constant this note cannot account for. Those offsets run
  from 64 to 160, so the field is within ten of overflowing a byte and
  **nothing here says what it does then**: byte 4 is the reading to
  trust if they ever disagree;
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
them in the block**, header and tables included. **385 blocks of 385**
agree, across every archive here — the 1993 one, the 1995 one and the
five the harness wrote — and so do the shape-1 and shape-2 blocks of
the bare forks, where this note had recorded the four bytes as
"presumably a checksum" without saying of what. It is the one check
this reader can apply to a block whose output nobody knows.

It is not a CRC of the OUTPUT, which is what a decoder would want and
what this note looked for first: sum, Adler-32, CRC-32 and two CRC-16s
over the decoded bytes match nothing. The encoder checks its own
compressed bytes, not its reconstruction.

### The check that came after: both tables against the only other reader

`src/fmt_now.c` carries these two tables as arrays transcribed from
XADMaster's `UnpackNewLZSS`. Compared entry for entry with the ones
derived here — **33 length classes and 55 distance classes — they
disagree nowhere**: every base, every extra-bit count, the jump from
five extra bits to eight at distance 256 included, and the last base
`0xe100`.

That is a check and not a source, and the order matters: the tables
above were committed on 2026-09-21 before this project's own engine was
opened, from the encoder's output alone. What the comparison adds is
that two lineages which share nothing — a de Bruijn probe against Now
Compress 5.0.1, and a transcription of somebody's reverse-engineering
of it — produce the same 88 numbers.

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
- **member records start at 24 and are 110 bytes each**:

  | at | field |
  |---|---|
  | +0 | a Pascal name, 1 + up to 31 bytes |
  | +38, +42 | type and creator |
  | +80 | the entries inside a FOLDER — 2 in the 1995 archive's one, 0 in every file record a 5.0.1 archive has. The 1993 archive's one record holds `0x20000` there, so this field is not read the same way across versions |
  | +86 | u32 **data fork length** |
  | +90 | u32 **resource fork length** |
  | +98, +102 | u32 start and end of the member's data area |
  | +106 | u32 **the sum of the record's first 106 bytes** |

  The two fork lengths are what let a reader split a member's stream
  without being told what went in — the stream is the resource fork
  first — and the checksum agrees on every record of every archive
  here, the folders' included. A record whose bounds do not parse is a
  folder and carries no data area;

- **a folder is followed by exactly the entries it says it holds.** The
  table is a pre-order flattening: `nowcompress.py --case tree`
  archives two folders and two loose files, and its seven records read
  `Alpha` (+80 = 2), `a1.bin`, `a2.bin`, `Beta` (+80 = 1), `b1.bin`,
  then the two root files — which is the 1995 archive's shape too, its
  one folder saying 2 with two entries behind it. That case exists
  because one specimen cannot tell a rule from a coincidence, and the
  1995 archive was the only one here with a folder in it;
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

**The header and block table end with a checksum of themselves.**
Immediately after the last record sits a **u32 equal to the sum of
every byte of the member's data area up to that point** — the same
idiom a block's four trailing bytes use, and true of all 75 members of
the five harness archives and both corpus ones. It gives a reader a
second way to find where a table stops, and it is what `src/fmt_now.c`
searches for when the reference's offsets need a constant added: that
file's delta search is where this note got the idea to look, and the
sums are the evidence.

**A repeated offset is also what the engine calls a stream restart**, and that
reconciles a count this project has carried since 2026-08-16.
FORMATS.md records **two stream-restart records** in the 1995 archive —
"the zero-length table entry that reloads the dictionary cache" — and
this walk finds one repeated offset inside `SynRef2.0 INFO`. The second
is the repeat that OPENS the big member's table: its data area states
the first block's offset and the table's first record restates it, so a
reader walking the archive as one stream sees a zero-length entry
there too. Two accounts, two records, one structure — and the bytes
come out right with the window carried across unchanged, so whatever
the reload is for, nothing here needs it.

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
| huffgap | 10 forks | 116,980 | — | 8 shape 2, 2 shape 1 |
| tree | 5 members in 2 folders | 11,150 | — | shape 3 |

**Every compressed block of every one of them reads byte for byte
against the bytes that went in** — 76 of 76 inside the archives, and
every block of the sixteen bare forks besides, each checked against its
own trailer as well.

And so do the corpus's real archives, graded against this project's
own extraction of them — which is itself adjudicated, the 1993 one by
`unar` and the 1995 one by its own self-extractor (FORMATS.md, *Now
Compress*):

| archive | blocks | read |
|---|---|---|
| `derived-Expand_Now_1.0.1.sea` (1993) | 3 — shape 3, Huffman, shape 3 | 3 |
| `derived-SyntheticReferences2.0.sea` (1995) | 306, all shape 3 | 306 |

**And both decode from the archive alone.** Given no expected output at
all, `derive_now.py` walks either file and decodes every block: the
member records say how long each fork is, the block headers say where
each stream starts and ends, and the three checksums — one per record,
one per block table, one per block — say the walk is on the rails. That
is the difference between a description that reads a file and one that
needs the answer first.

## What this note does NOT describe

- **What `00 03` means**, the two bytes every LZSS stream opens with,
  and **the zero byte** between a Huffman table and its stream.
- **A code length past 15.** The 128-byte table gives each symbol four
  bits, so 15 is as deep as it goes; `src/fmt_now.c` reads a count of
  "extra length" entries and their symbol indices after the nibbles,
  which adds 16 to those symbols' lengths. **No table here needs it** —
  the deepest code in any specimen is 12 — so this note has no evidence
  for or against, and that is the third fact in it whose lead came from
  the engine rather than the bytes.
- **The offset delta, which may not be a property of the format at
  all.** `src/fmt_now.c` corrects a block table's offsets by a constant
  it finds through the table checksum above, transcribed from the
  reference. **No file measured here needs it**: both corpus archives
  and all 75 harness members carry offsets that are already the file's
  own, and the archives that exercise the search in `ci.sh` are written
  by `tools/synth_now.py`, whose `build_table(..., delta=)` exists to
  make them. So the delta is a claim about what the reference believes,
  and this note has no evidence for or against it.
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

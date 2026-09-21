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
structure and its **container**, which a compressed file and an archive
share — enough to read every compressed specimen the harness has made,
and **every block of both of the corpus's real archives**: the 1993
`derived-Expand_Now_1.0.1.sea`, 3 blocks of 3, and the 1995
`derived-SyntheticReferences2.0.sea`, 306 of 306, whose 9.9 MB fork
alone is 304 blocks of the coder an archive uses. **Nothing in any
block is searched for any more**: a shape-3 block's header says where
its stream starts and ends, a shape-2 block's stream starts a fixed
distance after its table, and every block's last four bytes check the
rest of it.

**And where a field is written but not read, that is measured too.**
`tools/mutate_now.py` changes one field, recomputes every checksum over
it, and `tools/vmac/nowcompress.py --expand` or `--adjudicate` hands
the result back to Now Compress itself. That is what settled byte 2 of
a shape-3 header, the two bytes an LZSS stream opens with, the byte in
front of a Huffman stream and the offset delta, on 2026-09-21. What is
left is named under *What this note does NOT describe*, and it is four
short bullets.

## A compressed file is an archive of one entry

**There is no second layout.** What Now Compress writes when it
compresses a file is the same 24-byte file header and the same 110-byte
entry record an archive has, with an entry count of **1**, followed by
that entry's data area — so everything under *The archive layer* below
describes a `.now` file as well, and the only difference is the count.
Measured on 2026-09-21 across the sixteen bare forks the harness has
made: the file header's checksum at +20 agrees on every one, so does
the entry record's at +106, the record's fork lengths are the file's,
and its +98/+102 give the data area — 134, which is 24 + 110.

That is also what the engine has been reading since M12 without anybody
writing it down: `macextract x` on a compressed file walks it as a
one-entry archive, which is why "the fork header" had a block table at
**144** — 134 + 10, ten bytes into the data area.

## A fork is a sequence of blocks

**32,768 bytes each**, and each coded its own way — the format's own
test data says Now Compress "compresses a fork at a time, in blocks",
and it means it. `mixed.bin` is one **stored** block of 32,768 bytes
followed by one **Huffman-coded** block of 16,232, in a single fork.
So "which coder does Now Compress use" has no answer: it is a
per-block choice.

**Where each block begins is the data area's own table**, described
once under *The archive layer*, *A member's blocks*: a u32 saying where
the first block starts, which is also where the table ends, then one
eight-byte record per block. A record carries **a mode word, a padding
count and the offset where its block ENDS**; a block therefore runs
from the end of the one before it, and the first from the u32.

**The padding count is how many bytes sit between a block's stream and
its four-byte checksum.** It is 1 on four of the harness's shape-1
blocks and 0 on every other block here, and what says so is that the
shape-1 decoder stops exactly `padding + 4` bytes before the next
block's offset on all six. This note called those four bytes "zero in
every specimen" until 2026-09-21; two of them are this field, and
FORMATS.md's "zero padding" for the 1993 archive is the same number
read off the engine.

**Where this one came from**, because a note kept for a licence had
better say which facts are whose: the `padding` field was read out of
`src/fmt_now.c` while that file was still XADMaster's transcription,
and the check above is what makes it a measurement here rather than a
borrowing. See *What came from where*, at the end, for the tally;
everything else was read out of the encoder's output before that file
was opened, and the commits of 2026-09-21 are the record of which came
first — including the one that replaced its coders with code written
from this note.

| fork | blocks, as (start, mode) |
|---|---|
| `runs.bin`, Faster | (162, `0x0010`), ending at 290 = its size |
| `runs.bin`, Smaller | (162, `0x001f`), 290 |
| `half.bin`, Smaller | (162, `0x003f`), 8,950 |
| `mixed.bin`, Stored | (170, `0x0000`), (32,942, `0x003f`), 33,430 |

The block's data begins a fixed distance after its start: **none** for
a stored block, **two** bytes for shape 1, **one** for either Huffman
shape, and none for shape 3.

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

**They mean nothing to any reader, including the encoder's own.**
Changed to `5a a5` in a shape-1 block and to two other symbols of the
same code length in a shape-2 one — each with the block's checksum
recomputed, so a reader that looks cannot tell — both files came back
out of Now Compress's own **Decompress** byte for byte
(`tools/mutate_now.py --prefix`, `tools/vmac/nowcompress.py --expand`,
2026-09-21, with an unmutated third file as the control). So a decoder
skips two bytes here and nothing more, which is what this one and
`src/fmt_now.c` both do.

- a **flag byte**, then eight tokens, bits **most significant first**;
- a **1** is a literal: one byte, copied out;
- a **0** is a match, **two bytes holding a 3-bit length and a 13-bit
  distance**: `length = (b0 & 7) + 2`, `distance = ((b0 >> 3) << 8) |
  b1`, and a length of 2 — the low three bits zero — escapes to a
  third byte carrying `length - 2`.

A match copies 2 to 257 bytes from at most 8,191 back.

Read here as "a length byte, then a distance byte" until 2026-09-21,
which fits every shape-1 specimen and is not the format's: the two
readings agree whenever the distance is under 256. What settles it is
shape 2, where 1,340 of 2,162 match tokens carry distances past that
(BLOCKERS.md, *Withdrawn claims*).

## Shape 2 — the same framing, Huffman-coded

A block may instead code **every byte of shape 1's stream** —
including its flag bytes — through one Huffman code of 256 symbols.

- the code arrives as **256 lengths of four bits each**, 128 bytes,
  high nibble first, and **Kraft's equality is what identifies it**:
  exactly 1.000000 where the table is and nowhere else in the fork;
- codes are **canonical**: shortest first, assigned in symbol order,
  read most-significant-bit first;
- then **one zero byte**: it is the count of "extra length" entries —
  symbols whose code length gains 16, the escape past 15 — and it is 0
  in every block the encoder has written here. After those entries the
  stream starts at the next EVEN byte, which with a 1-byte header, a
  128-byte table and a 1-byte count is already where it is.
  **That byte is read**, unlike the two in front of the LZSS stream:
  set to 7 with nothing else touched, the same `half.bin` came back out
  of Decompress as 16,000 bytes of something else, and a block re-coded
  here so that the count is a true 6 came back intact (2026-09-21, *A
  code length past 15*);
- then the LZSS stream — **starting with the `00 03` that opens a
  shape-1 block**, coded through this table like every other byte;
- a **flag symbol**, then eight tokens as before, a 1 being a literal
  symbol;
- a **match is two symbols**: `length = (S & 7) + 2` and
  `distance = ((S >> 3) << 8) | D` — **the same 13-bit reach shape 1
  has**, because this IS shape 1's stream. **A length of 2 escapes**:
  the low three bits zero means the real `length - 2` is a third
  symbol.

**The tell that this shape is shape 1 underneath** is that in a file
of incompressible data the shortest code in the table belongs to
symbol **255** — because a flag byte of eight literals IS `0xff`, and
it occurs once per eight bytes. That is what unpicked it: a `0xff`
appearing between correct literals, every nine symbols, emitting
nothing.

Where the stream begins was recorded here as unknown until
2026-09-21 — "23 bits after the table in one specimen and 18 in
another". Both numbers are the count byte plus the coded prefix, whose
symbols are as long as each block's table makes them; ten blocks agree
(DECISIONS.md 2026-09-21, *the pair that never repeats*).

### Huffman alone — the same table, no framing at all

A block whose mode is `0x20` (or `0x120` in an archive) carries the
same 128-byte table one byte into the block, and then **one symbol per
output byte**: no flag bits, no matches, nothing else. Its stream
starts **one byte after the table**, and does so in all three blocks
that use it — the 1993 archive's middle block, which is where
FORMATS.md's "Huffman-only" shape comes from, and two members of the
`tokdist` case.

`0x3f` has `0x20` set too, so a reader that tests that bit alone reads
a Huffman-only block as though it had flag bytes in it.

### A code length past 15

The 128-byte table gives each symbol four bits, so 15 is as deep as a
code goes in it. **The byte after the table is the count of the symbols
that go deeper**: that many one-byte symbol indices follow it, each of
those symbols' lengths gains **16**, and the stream then starts at the
next even byte of the block.

**Measured 2026-09-21, and it took making the specimen.** Now Compress
will not write such a code: `--case deep` and `--case deeparc`
compressed and archived four files whose byte histograms are Fibonacci
— the distribution that makes a Huffman code as deep as it can be, 20
bits at 21 symbols — and all eight tables came back 10 to 13 deep with
the count zero. **The reason is the layer underneath**: every shape
puts an LZ coder below the Huffman one, and it eats precisely the skew
that would have made a deep code, because the commonest byte's
repetitions become matches. An input both skewed and match-free would
be needed, and those pull against each other.

So the code was built instead. `tools/mutate_now.py --recode 20` takes
`half.bin` as Now Compress compressed it, decodes its Huffman region to
the LZSS stream underneath, and writes that stream back under a code
that is legal but not optimal — a chain of lengths 1, 2, … 20, 20 with
the shallowest leaf split as often as there are symbols to place, which
satisfies Kraft's equality exactly and puts **six symbols at 16 to 20
bits**. Everything else about the file is what the encoder wrote.
**Decompress returned all 16,000 bytes of it**, and so did the same
file re-coded at 15 with no escape at all, which is the control.

A whole file written here from scratch is a different matter: Now
Compress calls it *"damaged and cannot be repaired"* even with a
shallow code, which is why the specimen had to be a re-coding of a real
one and not a construction (`tools/synth_now.py`'s `build_fork`, kept
for the next attempt). What is wrong with it is not known.

## Shape 3 — the coder an archive uses

A block whose mode has bit `0x40` codes literals, lengths and
distances through **two Huffman codes**, and it is what a `.sea`'s
members are made of. It is also the shape the corpus's two real
archives are almost entirely written in.

### The header, which is a size and three flush counts

- **bytes 0..1 are a u16 equal to `0x2F59` plus the length of the
  compressed header that follows.** Read as a magic byte and an offset
  — `0x2f`, then the stream's byte position plus 85 — they give the
  same answer on all **391 shape-3 blocks here**, because `4 + length`
  aligned up
  to an even byte IS `byte 1 − 85` whenever the length is even, which
  it is in every block seen. That is also why byte 1 is always odd,
  which was a puzzle while the field was read as two;
- **byte 2 is read by nothing, and it is not a property of the block.**
  Two measurements, both 2026-09-21, and between them they close it:

  **Nothing reads it.** All 38 shape-3 blocks of an archive the harness
  made were given a byte 2 of `0x5a`, each block's checksum recomputed,
  and the archive's own self-extractor run under the emulator: **80
  forks of 80 came out byte for byte** (`tools/mutate_now.py --byte2`,
  `nowcompress.py --adjudicate`). The only implementation of this
  format that exists does not look at it.

  **And it is not a function of the block.** `--case tokdist` archives
  forty near-identical members; their byte 2 runs 191, 224, 240, 248,
  252, 254, 255 and then 255 for the remaining thirty-two — each step
  halving the distance to 255. A per-block quantity cannot do that.
  Which is also why every per-block hypothesis failed on all 391:
  not the header size, the table sizes, the code depths, the flush
  counts, the ratio of a block's stream to its output, the token
  counts, the literal-to-match mix, the longest or mean match distance,
  the window's fill, nor a copy of any byte at a fixed offset in this
  block or the one before it. Whatever the encoder keeps there it
  carries ACROSS blocks: the 1995 archive's 306 sit in `0x60..0x7f`
  with occasional excursions, the harness's in `0xe0..0xff`, the 1993
  archive's are 19 and 239, and nine are zero;
- **byte 3 is the outer stream's end flush**: after the last token come
  `(16 − byte 3) mod 16` bits, and then the four-byte trailer;
- **from byte 4 comes a Huffman-coded region of the length byte 0..1
  states**, and the two code tables are inside it:

  | at | field |
  |---|---|
  | +4 | that inner stream's own end flush, same arithmetic |
  | +5..+14 | **twenty four-bit code lengths** — the code the tables are written in. Twenty, not sixteen, because the values it codes run to 19: a distance entry is stored as its length **plus two** |
  | +15 | the count of "extra length" entries, 0 in every block here |
  | +16.. | the two tables, and then a word-aligned start for the stream |

  Kraft's equality on those twenty is exact on every specimen
  (BLOCKERS.md for the sixteen-symbol reading this replaced). Nothing
  here uses a value past 15: the deepest distance entry seen is 13,
  stored as 15.

**The three flush counts are one idea**: `(16 − b) mod 16` at byte 3
for the block's stream, at byte 4 for the inner stream carrying its
tables, and at byte 0 of a shape-2 or Huffman-only block — the
encoder's 16-bit register, and how much of it was still free when it
stopped.

### The main table — 290 entries, zeros and all

One code length per symbol, each written in the code-length code,
and **the count is fixed at 290**: 256 literals, then 257..289 for the
match lengths. Symbol 256 is used by nothing seen here.

The code often completes before symbol 289 and the rest are written
as **zeros**; a reader that stops there starts the next table at the
wrong bit (BLOCKERS.md, *Withdrawn claims*).

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

Every block's stream starts on a **byte boundary**, and the header
gives it twice over: as `4 +` the header size in bytes 0..1, rounded
up to even; and as the end of the 290 + 56 table entries plus
`(16 − byte 4) mod 16` bits. Nothing is searched for.

Twenty blocks of the 1995 archive have byte 4 zero with no flush at
all, which is what `mod 16` is for (DECISIONS.md 2026-09-21).

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

**The end-flush byte has a second witness.** `src/fmt_now.c` computes
a Huffman block's bit count as `(bytes × 8) − (16 − endbits)` where
`endbits` is that block's first byte — which is `(16 − byte) mod 16`
by another name, arrived at here from the byte counts of 385 blocks
and there from the reference. The two readings of byte 0 agree.

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

`src/fmt_now.c` carried these two tables as arrays transcribed from
XADMaster's `UnpackNewLZSS` until 2026-09-21. Compared entry for entry
with the ones derived here — **33 length classes and 55 distance
classes — they disagree nowhere**: every base, every extra-bit count,
the jump from five extra bits to eight at distance 256 included, and
the last base `0xe100`. So the arrays stayed where they were when the
coders around them were rewritten, and what they cite is this note.

The same file decodes a shape-3 header into exactly **346 values, 290
then 56** — the two counts derived here, arrived at from the other
side.

The tables above were committed before that file was opened, so this
is a check and not a source: two lineages, no shared evidence, 88
numbers, no difference.

### How the two tables were made legible

Against matches planted at a chosen length and distance:
`nowcompress.py --case tokdist` and `--case toklen` build each member
out of a **de Bruijn sequence of order 2 over 256 symbols**, in which
no pair of bytes ever repeats, so the copy appended to it is the only
match an encoder can find. Forty distances from 2 to 16,384 and
twenty-four lengths from 2 to 255 (tools/vmac/README.md).

## The archive layer

**An archive is not a fork**, and treating one as a fork is why the
corpus's two real specimens read as nonsense for a year. What sits at
144 in them belongs to a member, not to the file. **A compressed file
is one of these with a count of 1**, so this section describes both.

- **the file header is 24 bytes**, and all of it reads:

  | at | field |
  |---|---|
  | +0 | u16 `0x0002` |
  | +2 | u16 **the setting**, in a block mode word's own vocabulary — `0x0010` Faster, `0x003f` Smaller, `0x0160` an archive 5.0.1 wrote, `0x0060` the 1993 one |
  | +4 | u32 **32,768** in a compressed file, **65,536** in an archive — the window a reader needs, and the block, which are `NOW_HISTORY` and `NOW_OUTBLOCK` in `src/fmt_now.c` from the other side |
  | +8 | u32 **the entry count** |
  | +20 | u32 **the sum of bytes 0..19** — the checksum idiom again, and the fourth place it turns up |
  | +24 | the first entry record |

  Twenty-four of the twenty-five files here carry that sum. The
  twenty-fifth is this project's own `synth-now-mixed.now`, which
  differs from the encoder's output in five ways nothing checks
  (TESTING.md, *what the derivation tools cannot see*).

  **+2 is the setting and not a version**, which is what this note
  called it until 2026-09-21: `runs.bin` and `prose.txt` asked for
  Smaller and came out as shape-1 blocks, and their headers still say
  `0x003f` — so the word is what the user picked, not what the coder
  did, and it is spelled in the same layer bits a block's mode uses.
  The 1993 archive is still told from a 5.0.1 one by it, on the `0x100`
  bit;
- **member records start at 24 and are 110 bytes each**:

  | at | field |
  |---|---|
  | +0 | a Pascal name, 1 + up to 31 bytes |
  | +36 | flags; **bit `0x10` marks a directory** |
  | +38, +42 | type and creator, zero on a directory |
  | +46 | u16 Finder flags |
  | +54, +58 | u32 created and modified, Mac dates |
  | +82 | u16, **how many entries a directory holds** |
  | +86 | u32 **data fork length** |
  | +90 | u32 **resource fork length** |
  | +98, +102 | u32 start and end of the member's data area |
  | +106 | u32 **the sum of the record's first 106 bytes** |

  The directory bit is the only one set in both folder records of the
  `tree` archive and clear in all five of its file records; the 1995
  archive's folder has `0x14` there, so the test is the bit and not the
  word. The dates identify themselves — 1995-10-30 and -31 for the 1995
  archive, 1993-05-25 and 1993-11-05 for the 1993 one, today for an
  archive the harness makes today. The two fork lengths let a reader
  split a member's stream without being told what went in, resource
  fork first, and the checksum agrees on every record here, folders
  included;

- **a folder is followed by exactly the entries it says it holds** —
  the table is a pre-order flattening. `nowcompress.py --case tree`
  archives two folders and two loose files: `Alpha` (+82 = 2),
  `a1.bin`, `a2.bin`, `Beta` (+82 = 1), `b1.bin`, then the root files,
  which is the 1995 archive's shape too;
### A member's blocks

A member's data area is its block table and then its blocks, and **the
table's own length is the first thing in it**:

| at | field |
|---|---|
| +0 | u32 **where the first block begins**, which is also where this table ends |
| +4 | the records, `n = (first − start − 4) / 8 − 1` of them, **eight bytes each: a u16 mode, a u16 padding count and a u32 saying where the block ENDS** |
| then | four bytes, then a u32 **equal to the sum of every byte of the data area before it** — the third place the checksum idiom turns up |
| first | the first block |

A block runs from the end of the one before it — the first from that
u32 — to its own record's end offset, less `padding + 4` for its
trailer.

**One place and one width, on all 108 members here**: the two corpus
archives, the sixteen bare forks and every archive the harness has
made, with that checksum agreeing on every one. Reading the same bytes
as `[offset][mode][padding]` records worked too, and needed two table
positions (`+2` or `+10`) and two offset widths to do it — the 1995
archive addresses 2.9 MB, which no u16 reaches — so it is the reading
that was dropped on 2026-09-21, along with the pair of words it could
not name.

**A table's offsets may all be short by a constant, and a reader is
expected to notice.** The u32 that says where the first block begins is
also where the table's checksum sits, so a walk that looks for the
running sum finds the table's true end, and the difference is the
constant. **No file the encoder wrote here needs one** — all 108
members carry the offsets their own file has — but the correction is
the format's and not a reader's invention: an archive with every stored
offset reduced by 100, that checksum recomputed, came out of **its own
self-extractor byte for byte**, 8 forks of 8, while this engine with
the correction disabled refuses all four of its members
(`tools/mutate_now.py --delta 100`, 2026-09-21).

**And the format's decoder is more tolerant than this engine.** The
same archive with only the u32 reduced — every record left correct —
also comes out of its own self-extractor byte for byte, and this engine
refuses it: it computes one constant from that u32 and adds it to every
record, so correct records become wrong ones. **Whatever Now Compress
does with a table it has to correct, it is not that.** Nothing here
turns on it — no file the encoder writes has either shape — but a
reader that must choose should know that the stored first-block offset
is the field its own decoder trusts least.

**`0d4c 0037` were the mode and padding of a record that produces no
bytes.** Now Compress 5.0.1 writes one in front of every table, whose
end offset repeats the first-block offset the u32 already gave; the
1993 archive does not. **Such a record says the next block STARTS a
stream**, and where bytes have already come out of the member it is the
boundary between its two forks: that is how the 1995 archive's
`SynRef2.0 INFO` carries a 332-byte resource fork and a 574-byte data
fork in one member, **resource fork first**.

**A stream restart is what the engine calls the same record.**
FORMATS.md's "two stream-restart records" in the 1995 archive are that
fork boundary and the leading one 5.0.1 writes in front of a table. The
window is carried across either unchanged and the bytes come out right,
so nothing here needs a reload.

FORMATS.md has recorded the 1993 archive's block sequence since
2026-08-15, from instrumenting the engine: "three blocks, 'new' LZSS
twice and Huffman-only once" — `0x40`, `0x20`, `0x40`. The walk above
reads the same three from the file, and 32,768 + 32,768 + 23,406 is
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
| deep | 4 forks, Fibonacci histograms | 55,713 | — | shape 2, codes 10–11 deep |
| deeparc | the same four, archived | 55,713 | — | shape 3, codes 10–13 deep |

**Every compressed block of every one of them reads byte for byte
against the bytes that went in** — **85 of 85** inside the archives,
and every block of the sixteen bare forks besides, each agreeing with
its own trailer as well (`tools/derive_now.py` with no arguments).

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
each stream starts and ends, and four checksums — one over the file
header, one per entry record, one per block table, one per block — say
the walk is on the rails.

**Nothing states how much a block produces, and nothing has to.** A
block's stream runs from the bit its header names to the bit its flush
count names, and what comes out is however many bytes that is — 32,768
for every full block here and 23,406 for the 1993 archive's last one,
neither written down anywhere in the file.

## What came from where

Most of this note was read off the encoder's output: the four coders,
both of shape 3's alphabets, the block and entry tables, the three
checksums, the fork boundary, the stream bounds. The de Bruijn probes
did the tables; block arithmetic did the rest; `tools/derive_now.py`
re-runs all of it, and the tables were compared with XADMaster's
afterwards and matched on all 88 entries.

**What came from reading `src/fmt_now.c`, which is XADMaster's**, and
was then checked against the bytes here:

- the `padding` count in a block-table record;
- the u32 after a member's header and table that sums the bytes before
  it — this note went looking because that file's delta search hunts
  for it;
- **nothing any more, of the escape past 15**: it was the reference's
  reading until 2026-09-21, when a block re-coded here to use it came
  back out of Decompress intact (*A code length past 15*). That it was
  worth going to make a specimen for is the reference's, though — this
  note would not have known there was a field there to test;
- the shape of a shape-3 block's header: that bytes 0..1 are one size
  field rather than a magic and an offset, that the tables ride in a
  Huffman stream of their own, and that its alphabet is twenty symbols;
- **the block table's framing** — records of `[mode][padding][end
  offset]` from +4 rather than `[offset][mode][padding]` from +2 or
  +10. Both read the same blocks out of every file here; that one needs
  no special case for the 1993 archive or for offsets past 64 KB, and
  the check that made it a measurement is the 108 members and their
  checksums above.

Each of those was verified here before being written down, and each
gives the same numbers as the reading it replaced. The distinction
matters for one reason: this note exists partly to say what the format
is without the reference, and a note that blurs the line is worth less
than one that draws it.

## What this note does NOT describe

- **What `00 03` MEANS**, the two bytes every LZSS stream opens with.
  What they are worth is settled — nothing reads them, including the
  encoder's own decoder (*Shape 1*) — but not what the encoder thinks
  it is writing.
- **What a shape-3 block's header byte 2 IS.** That nothing reads it,
  and that it is not a property of the block, are both measured (*The
  header*); what the encoder keeps there is not.
- **How the format's decoder corrects a block table it has to
  correct.** Both mutations tested read back byte for byte — every
  offset short by a constant, and the first-block u32 short on its own
  — and no single constant added to every record explains the second
  (*The archive layer*). This engine implements the first and refuses
  the second, which no file the encoder writes has.
- **Why a file written here from scratch is refused.** Now Compress
  calls one *"damaged and cannot be repaired"* even when every field
  this note describes is right and its code is one the encoder could
  have written (`tools/synth_now.py`'s `build_fork`). Something in a
  compressed file is checked that is not checked in a file the encoder
  wrote and this note has changed — which is why the specimen for the
  escape is a re-coding of a real file (*A code length past 15*).
- **Whether there are more shapes.** Four coders and "stored" account
  for every block in every specimen here, and that is five
  arrangements — which is what PROGRESS.md has called Now Compress's
  "five stream shapes" since M12. This note said on 2026-09-21 that
  the two counts were about different things; they are not, and the
  disagreement was this note's.

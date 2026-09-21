# Now Compress — two coders, its blocks and its archive

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

**How much of the format this is.** Two of its coders, its block
structure and its **archive container** — enough to read every
compressed specimen the harness has made, eight of eight, byte for
byte against the inputs they were made from, and enough to walk the
corpus's 1993 archive into the three blocks its fork needs. A third
coder, the one an archive uses, is read as far as its code table and
no further. `src/fmt_now.c` still cites XADMaster for all of it.
What follows is nevertheless the first account of any part of this
format that owes nothing to that file.

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
shape 2.

**What the mode word means, and what it does not.** `0x0000` is
stored. Beyond that, the two `runs.bin` forks are **byte-identical
except for that word** — `0x0010` from Faster and `0x001f` from
Smaller, same payload — so the low bits are the user's setting and
not the coder. **Bit `0x20` is the coder**: set for shape 2, clear
for shape 1. That is four data points, and it is a hypothesis of the
useful kind — it predicted `half.bin` (`0x3f`) and `mixed.bin`'s
second block (`0x3f`) correctly before being written down here.

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

## What the specimens show

| mode | file | bytes | stream | read as |
|---|---|---|---|---|
| Faster | `runs.bin` | 7,400 | 290 | shape 1 |
| Faster | `prose.txt` | 6,660 | 386 | shape 1 |
| Smaller | `runs.bin` | 7,400 | 290 | shape 1, byte-identical to Faster's |
| Smaller | `prose.txt` | 6,660 | 386 | shape 1, byte-identical to Faster's |
| Smaller | `half.bin` | 16,000 | 8,950 | **shape 2**, table at 163 |
| Stored | `mixed.bin` | 49,000 | 33,430 | **two blocks**: stored 32,768, then shape 2 |
| Archive | `one.txt` | 7,500 | 7,500 | stored; the `.sea` is what is compressed |
| Archive | `mixed.bin` | 49,000 | 49,000 | stored, in two blocks |

**Eight of eight**, byte for byte against the inputs the application
was given.

**Faster and Smaller produced the same bytes** for both files, so
whatever the mode word changes, it did not change these two streams.

## The archive layer

**An archive is not a fork**, and treating one as a fork is why the
corpus's two real specimens read as nonsense for a year. What sits at
144 in them belongs to a member, not to the file.

- the file header's **word 5 is the member count**;
- **member records start at 24 and are 110 bytes each**: a Pascal
  name in the first ten bytes, the member's uncompressed size at +88,
  and the bounds of its data area at **+98** and **+102**;
- a member's data area opens with the same header tail a bare fork
  has — the **first block's offset** at +2 — and then its **block
  table**, the same eight-byte records.

**The table sits at one of two places and the header says which.**
The first record must repeat the first-block offset the header states.
In everything Now Compress 5.0.1 wrote the table is at **+10**, with
two words this note cannot name (`0d4c`, `0037`) in between; in the
corpus's 1993 `derived-Expand_Now_1.0.1.sea` those two words are
absent and the table starts at **+2**.

**FORMATS.md had the answer already.** Its *Now Compress* section has
recorded since 2026-08-15, from instrumenting the engine's block
loop, that this archive is "three blocks, 'new' LZSS twice and
Huffman-only once" — which is `0x40`, `0x20`, `0x40` in that order.
The walk above reproduces it from the file.

That one distinction is the whole of what was missing. Reading the
later layout into the older file drops its FIRST block, which is why
that archive looked like two blocks of a fork that needs three. Read
correctly it is three — `(178, 0x40)`, `(19158, 0x20)`,
`(49796, 0x40)` and the end sentinel — and **32,768 + 32,768 + 23,406
is 88,942, the fork's size exactly**.

**The mode word gains a bit in an archive.** `0x20` is shape 2 and
`0x40` is shape 3, below; a stored block inside an archive is `0x100`
where a fork writes `0x0000`. The 1993 archive's middle block is
`0x20`, and a 128-byte table with Kraft exactly 1.000000 sits one byte
past its offset, where shape 2 puts one.

## Shape 3 — the archive's coder, as far as its table

The coder a `.sea` uses for its members is neither of the two above,
and this note does not decode it. What it does read is the header,
which is the same in all **eight** shape-3 blocks known — four made
to order by `nowcompress.py --case probe`, two in the harness's own
`Archive.sea`, two in the 1993 archive:

- byte 0 is **`0x2f`** in every one of them;
- bytes 1..4 are not identified;
- **bytes 5..12 are a code-length code**: sixteen four-bit lengths,
  one per length 0..15, and **Kraft's equality is exact on all eight**;
- bytes 13..15 are **24 bits this note cannot account for**, zero in
  every specimen;
- from **bit 128** comes the main table, one code length per symbol
  written in that code-length code, and it **ends where the code is
  complete** — nothing states its length and the trailing absent
  symbols are not sent;
- **symbols 0..255 are the literals.** What follows them, from 257 up,
  is the match alphabet: about 34 symbols, and not read here.

**What says the literal region is right** is not the specimens it was
derived from. In the 1993 archive's third block the table codes
**252 literals, and the 23,406 bytes that block decodes to contain
exactly those 252 distinct byte values** — none missing, none spare.
Its first block codes 256 of 256. The four made-to-order blocks agree:
a file written over `{A, B}` codes two literals at 65 and 66, one over
`{A, B, C, D}` codes four, and the 15 distinct bytes of
`one.txt` are the 15 the table codes.

**One specimen the reading does not explain.** `runa.bin`, 4,000
bytes of a single byte, produces a table with a complete code and
**no literal coded at all** — which a file that has to emit its first
byte somehow cannot be. Either that block is arranged differently or
something before the table is being read wrongly on it. It is the one
of eight that does not fit.

## What this note does NOT describe

- **Where a shape-2 block's bit stream begins.** Its code table is
  128 bytes, but the stream starts 23 bits after it in one specimen
  and 18 in another, so something variable sits between — the one
  thing `tools/derive_now.py` still searches for, within a couple of
  bytes.
- **Shape 3's stream.** The tokens after the table — how a literal,
  a length and a distance are spelled — are not derived. That is what
  stands between this note and the corpus's real archives.
- **The rest of the fork header**, of which this note identifies the
  version word, the mode word, a ten-byte name field, two Mac dates,
  a `'????'`/`'UNIX'` type and creator — the harness's, not the
  format's — and the block table at 144.
- **The trailer**, four bytes after a shape-1 payload, sometimes
  preceded by `0xff`. Presumably a checksum.
- **Whether there are more shapes.** Three coders and "stored"
  account for every block in every specimen here — shapes 1 and 2 in
  a fork, shape 3 in an archive. PROGRESS.md's "five stream shapes"
  counts something else — the container's five arrangements, not five
  coders.

# Now Compress — one shape of five

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

**How much of the format this is.** Two of its coders and its block
structure — enough to read **every specimen the harness has made**,
eight of eight, byte for byte against the inputs they were made from.
Not enough to read the corpus's real archives, whose blocks this
cannot yet locate: `src/fmt_now.c` still cites XADMaster for all of
it. What follows is nevertheless the first account of any part of this
format that owes nothing to that file.

## A fork is a sequence of blocks

**32,768 bytes each**, and each coded its own way — the format's own
test data says Now Compress "compresses a fork at a time, in blocks",
and it means it. `mixed.bin` is one **stored** block of 32,768 bytes
followed by one **Huffman-coded** block of 16,232, in a single fork.
So "which coder does Now Compress use" has no answer: it is a
per-block choice.

Where each block begins is in the fork header, which is not decoded
here — but the header plainly carries a table of records shaped
`u16 value, u16 mode, four zero bytes`, of which the last value is the
fork's own byte count (0x22f6 = 8,950 for `half.bin`, 0x8296 = 33,430
for `mixed.bin`) and an earlier one points at the second block
(0x80ae = 32,942, four bytes before that block's code table). Reading
that properly is what stands between this note and the corpus.

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

## What this note does NOT describe

- **How to find a block.** This is the gap that matters. The reader
  in `tools/derive_now.py` walks the EXPECTED output and asks of each
  block whether it was stored or Huffman-coded, searching a short
  window for its table — which is legitimate for a derivation graded
  against known bytes and useless as a decoder. The fork header's
  record table is where the answer is.
- **The corpus's real archives.** `synth-now-mixed.now` and
  `derived-Expand_Now_1.0.1.sea` are not read here. Both have
  Kraft-1 tables in them — one at 19,159 in the second — so they are
  very likely the same two shapes in blocks this reader cannot
  locate. Both have oracle hashes waiting.
- **The 164-byte fork header**, of which this note identifies the
  version word, the mode word, a ten-byte name field, two Mac dates,
  a `'????'`/`'UNIX'` type and creator — the harness's, not the
  format's — and the record table above.
- **The bits between a block's code table and its stream**: 23 of
  them in `half.bin`, unexplained.
- **The trailer**, four bytes after a shape-1 payload, sometimes
  preceded by `0xff`. Presumably a checksum.
- **Whether there are more shapes.** Two coders and "stored" account
  for every block in every specimen here. PROGRESS.md's "five stream
  shapes" counts something else — the container's five arrangements,
  not five coders.

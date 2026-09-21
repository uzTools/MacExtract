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

## What this note does NOT describe

- **Where a shape-2 block's bit stream begins.** Its code table is
  128 bytes, but the stream starts 23 bits after it in one specimen
  and 18 in another, so something variable sits between — the one
  thing `tools/derive_now.py` still searches for, within a couple of
  bytes.
- **The corpus's real archives.** `synth-now-mixed.now` and
  `derived-Expand_Now_1.0.1.sea` are not read here, and the reason is
  now known: **neither is a bare fork.** What sits at 144 in them
  belongs to an outer container — the second is self-extracting, and
  the resource fork wanted from it is an ENTRY inside the archive,
  not the archive's own fork. Finding that is the next layer, not the
  next coder.

  **What the archive layer looks like**, from the harness's own
  `Archive.sea` (two members, both inputs kept beside it): a header
  whose fifth word is the member count, then one record per member
  carrying a Pascal name at offset 24 and the same type, creator and
  date fields a fork header has — `mixed.bin` at 24, `one.txt` at
  134, so the records are about 110 bytes and NOT the 164-byte fork
  header despite the resemblance. Member data follows, and the first
  member's first block is stored: `mixed.bin`'s bytes appear verbatim
  at 280. Eight-byte records in the shape of a block table sit just
  before that data, at 262, with values that do not fit the reading
  above. That is where the next attempt starts.

  **One near-miss, recorded so nobody follows it twice.** That `.sea`
  does have eight-byte records at 144, the first of them
  `(0x4ad6, 0x20)` — and `0x4ad6` is 19,158, exactly one before the
  only offset in the whole file where 128 bytes of nibbles give
  Kraft 1.000000, which is where a shape-2 block's table would be.
  It decodes nothing, at any bit position within three bytes, with
  the table read at 19,158, 19,159 or 19,160. Either the resemblance
  is chance or that block is arranged differently; either way the
  next attempt should start by finding the entry, not by trusting
  that record.
- **The rest of the fork header**, of which this note identifies the
  version word, the mode word, a ten-byte name field, two Mac dates,
  a `'????'`/`'UNIX'` type and creator — the harness's, not the
  format's — and the block table at 144.
- **The trailer**, four bytes after a shape-1 payload, sometimes
  preceded by `0xff`. Presumably a checksum.
- **Whether there are more shapes.** Two coders and "stored" account
  for every block in every specimen here. PROGRESS.md's "five stream
  shapes" counts something else — the container's five arrangements,
  not five coders.

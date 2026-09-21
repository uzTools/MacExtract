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

**How much of the format this is: one shape, and the simplest.** Now
Compress writes several, and the corpus's real archives use ones this
note does not describe. `src/fmt_now.c` still cites XADMaster for all
of it and will until the rest are described. What follows is
nevertheless the first account of any part of this format that owes
nothing to that file.

## The shape

The payload begins **164 bytes into the fork** in every specimen —
two files, two modes, headers otherwise identical bar the name, the
dates and a mode word (`0x0010` for *Faster*, `0x003f` for *Smaller*
and *Stored*). 164 is where the data is, not a field anybody has read
out of the header.

From there:

- a **flag byte**, then eight tokens, its bits taken **most
  significant first**;
- a **1** is a literal: one byte, copied out;
- a **0** is a match: **`length - 2`, then the distance**, one byte
  each — **except** that a length byte of **zero is an escape**, and
  then the token is three bytes: the zero, the distance, and
  `length - 2`.

So a match copies 2 to 257 bytes from at most 255 back. That short
reach is presumably why the encoder picks a different shape for
anything large: both files this reads are under 8 KB, and the 16,000-
and 49,000-byte specimens are written another way.

**Nothing in the stream says when to stop.** The caller's byte count
does — as in StuffIt method 8 and ARC's squeezed members, which is
apparently just what Macintosh archivers did.

After the payload comes a **four-byte trailer**, sometimes preceded by
`0xff`. It is not decoded here and is presumably a checksum.

## What the specimens show

| mode | file | bytes | stream | |
|---|---|---|---|---|
| Faster | `runs.bin` | 7,400 | 290 | payload 164..285 |
| Faster | `prose.txt` | 6,660 | 386 | payload 164..382 |
| Smaller | `runs.bin` | 7,400 | 290 | byte-identical to Faster's |
| Smaller | `prose.txt` | 6,660 | 386 | byte-identical to Faster's |
| Archive | `one.txt` | 7,500 | 7,500 | **stored**; the `.sea` is what is compressed |
| Archive | `mixed.bin` | 49,000 | 49,000 | stored |

**Faster and Smaller produced the same bytes** for both files, so
whatever the mode word changes, it did not change these two streams.

## What this note does NOT describe

- **The other shapes.** `half.bin` (16,000 → 8,950) and `mixed.bin`
  (49,000 → 33,430) are written some other way, and so is every real
  Now Compress file in the corpus. `half.bin`'s payload is visibly
  nibble-structured, which suggests something Huffman-coded, and that
  is a guess and not a reading.
- **The header.** 164 bytes of it, of which this note identifies the
  version word, the mode word, a ten-byte name field, two Mac dates
  and a `'????'`/`'UNIX'` type and creator — the type and creator
  being the emulator harness's, not the format's.
- **The trailer**, beyond its length.
- **Blocks.** The format's own documentation inside the test data says
  Now Compress "compresses a fork at a time, in blocks", and nothing
  here has had to cross a block boundary.

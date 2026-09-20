# ARC — the member header, and three of its coders

ARC (System Enhancement Associates, 1985) is a stream of members, each
a fixed header and then the bytes of one file. PAK and ARC 7 extend it
with methods of their own; the header is the same in all three.

**Where this came from.** Derived on 2026-09-20 from the output of a
real ARC — **5.21q**, Howard Chu's UNIX port of SEA's own program,
fetched by `tools/get_arc.sh` — made to compress inputs chosen here,
with the parameters of each coder searched and scored against the
input it was given. No implementation of the format was read.
`tools/derive_arc.py --grid` re-runs the derivation against that
encoder; without `--grid` it re-reads the corpus fixture with the rules
below and checks every member against `unar`'s sha256.

## The member header

| offset | size | field |
|---|---|---|
| 0 | 1 | `0x1a`, and `0x00` in the method byte after it ends the archive |
| 1 | 1 | method |
| 2 | 13 | name, NUL-padded |
| 15 | 4 | compressed size, **little-endian** |
| 19 | 2 | date |
| 21 | 2 | time |
| 23 | 2 | CRC-16 |
| 25 | 4 | original size — **method 1 does not have this field** |

So a member's data begins 29 bytes in, or 25 for method 1, whose
compressed size is also its original size. Verified by walking three
archives end to end and landing exactly on each next header: a real
ARC 5, a real PAK, and `derived-ARCDOS.arc` — an **ARC 7** archive,
whose method 20 and 21 informational items `unar` refuses to read at
all (BLOCKERS.md, *`unar` does not read ARC 7.x*).

## The coders

**Methods 1 and 2 — stored.** The data is the file.

**Method 3 — "packed": RLE90 and nothing else.** `0x90` introduces a
run: a following `0x00` means a literal `0x90`, any other value `n`
means the byte before it repeats `n-1` more times. Every coder below
that says "then RLE90" means this filter over what it produced.

**Method 4 — "squeezed": RLE90 under a Huffman tree of node pairs.**
The member begins with a `u16` node count, then that many **pairs of
`s16`**, all little-endian. A negative value is a leaf holding symbol
`-value-1`; symbol 256 ends the stream. A non-negative value is the
index of another pair. Decoding starts at pair 0 and reads **one bit
per step, least-significant first**, the bit choosing which of the two
to follow. The symbols that come out are an RLE90 stream.

**Method 8 — "crunched": a width byte, LZW, then RLE90.** The
member's **first byte is the maximum code width** (12 in what this
encoder writes). After it, LZW read least-significant-bit first: codes
start at **9 bits** and widen as the dictionary fills, **256 clears
the table**, and the first code assigned is **257**. The output is an
RLE90 stream.

**Method 9 — "squashed": LZW to 13 bits, alone.** The same LZW, but
with no width byte in front of it and **no RLE90 behind it** — the
codes produce the file directly. PKARC introduced it and ARC 5.21
writes it for `aq`.

## What the specimens show

From ARC 5.21q itself, over inputs chosen here — one file with a
skewed byte distribution, one with long runs:

| method | what | bytes |
|---|---|---|
| 4 | squeezed | 3,000 |
| 8 | crunched | 1,536 |
| 9 | squashed | 1,536 |

And over `synth-arc-mixed.arc`, one member per method, against
`unar`'s sha256: **methods 1, 2, 3, 4, 8 and 9 all reproduced**.

## What this note does NOT establish

- **Methods 5, 6 and 7** — the older Crunch variants. ARC 5.21q will
  not write them, so nothing here can be fed to derive them; the
  corpus fixture has one member of each and they are read by
  `src/fmt_arc.c` on `XADARCCrunchHandle.m`'s authority, which is
  where that row stays.
- **Method 10 in either dialect.** PAK's **Crushed** is not an LZW of
  the shape above, and that is now measured rather than assumed: a
  grid of **288 combinations** — bytes inverted or not, codes read
  either bit order, widths from 9 to 14 with five starting points,
  with and without a clear code, two first-free codes, three leading
  skips, and RLE90 either applied or not — produces **not one correct
  byte** of `RUNS.TXT`, a 12,692-byte file that PAK itself crushed to
  261 bytes from input this project chose
  (`tools/pak.py --make`). Whatever it is, its dictionary is not
  addressed by sequence, which is consistent with the hash table
  `src/fmt_arc.c` describes — and that file still reads it on
  `XADARCCrushHandle.m` and `LZW.c`, the only implementation of
  Crushed anywhere.
- **Methods 5, 6 and 7 are the same kind of no.** The same search
  over the corpus fixture's members reads none of them. deark (MIT)
  implements 5, 6 and 8 and calls 5 and 6 "static LZW", so a
  description exists in a permissive implementation even though the
  wiki has no page for them; what does not exist is a derivation, and
  a parameter search is not going to supply one for a hash-addressed
  table. ARC 7's **Trimmed** and PAK's
  **Distilled** share the number; Distilled is deark's (MIT) already
  and needs nothing from here.
- **Anything about encryption**, ARC's `g` switch, which no specimen
  here uses.

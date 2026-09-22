# StuffIt classic method 6 — "fixed Huffman", and its framing

Method 6 is the one StuffIt method whose Huffman code book never
changes: every block of every fork is coded with the same 257 codes,
and only the BYTE each code stands for is declared per block. That is
what "fixed" means here. Underneath the Huffman layer is PackBits, and
around both is a framing — a signed block size, a stored-block escape,
and a per-block PackBits expansion — which is what this note is about.

**Why it exists.** `src/fmt_sit.c`'s method 6 was transcribed from
macutils' `macunpack` (LGPL) and was the last of that transcription in
the file; it is the row that has kept `NOTICE` copyleft. The code book
stopped being macutils' on 2026-09-21 (`src/sit6_tables.h`, 26 bytes).
This note is the rest of it.

**Where this comes from.** `reference/deark/modules/stuffit.c`
(`do_decompr_fixedhuff`, `sit_fixedhuff_init_tree`) and
`reference/deark/src/fmtutil-rle.c` (`my_packbits_codec_addbuf`), both
MIT, plus the container page `reference/notes/sit_format_theunarchiver.md`.
deark credits macunpack as documentation and uses none of its code, so
this is an independent implementation — **not an independent reading**
(TESTING.md, *A third oracle*).

`tools/derive_sit6.py` is a reader written from those and nothing else.
It reproduces **all 11 method-6 forks in the corpus** — the 34,818-byte
resource fork of `derived-INITLoader.sit`, the only real one, and the
ten of `synth-sit-fixhuf.sit` — byte for byte against the sha256 two
oracles recorded for them. It even parses the 26 bytes out of deark's
source rather than holding a copy, so it cannot agree with the engine
by sharing a typo with it.

## A fork is a sequence of blocks

Each block is independent: its own code book assignment, its own
PackBits stream, its own expansion into the fork. Nothing carries
across a block boundary.

    s32  size          counted from its own first byte
    size < 0           STORED: |size| - 4 bytes of PackBits, no Huffman
    size >= 0          u32  length of the PackBits stream this block
                            decodes to
                       s16  code count, 0..256
                       n    bytes: what leaf ordinals 1..n stand for
                       ...  the bitstream, to the block's last byte

The block ends at its first byte plus `size`, and the next block starts
there — so the bitstream may stop short of the block and what is left
is skipped without being read. A block below 10 bytes, or below 4 for a
stored one, ends the fork.

The walk is driven by the **fork's** expanded length, not by the
compressed length: it stops when the entry header's byte count has been
produced.

## The code book

Thirteen (count, length) pairs, and an assignment rule. Both are in
`src/sit6_tables.h`, which states where they come from and what they
were checked against; the exhaustive equivalence to the table they
replace is DECISIONS.md 2026-09-21, *the table that was twenty-six
bytes*. Codes are read **most-significant bit first**. Symbol 256 is
the stop code; symbols 0..255 are ordinals into the bytes the block
declared.

## PackBits, once per block

Standard Macintosh PackBits, and the caller's remaining fork length is
a maximum rather than an expectation:

- a control byte below `0x80` introduces `n + 1` literal bytes;
- `0x80` is a no-op;
- above `0x80` it repeats the next byte `0x101 - n` times.

## The three corrections

**1. The stop code is there, and reading it is right.** deark stops
Huffman decoding the moment the declared length is reached and never
reads the stop code; macunpack ignores the declared length and decodes
until the stop code. Both work, because the two agree — measured, not
assumed: across the corpus's **13 Huffman blocks, the symbol following
the declared length is the stop code in 13 of 13**, never a byte and
never the block's end. `src/fmt_sit.c` reads it and requires it, which
refuses a block the two disagree about instead of picking one.

**2. A code above the declared count stands for nothing.** deark
indexes its 256-byte translation array with the decoded symbol and
bounds it against nothing, so a block that names 12 bytes and codes a
thirteenth reads whatever the previous block left there — a wrong fork
rather than a refused one, and macunpack does the same. No block here
does it; `src/fmt_sit.c` refuses it.

**3. A short block ends the fork; it does not end the archive.** deark
treats `size < 10` as a clean stop and produces what it has.
`src/fmt_sit.c` reports the fork corrupt, because by then the fork's
declared length has not been reached and the entry is short either way
— the difference is whether the caller is told. Same for a declared
expanded length of zero, which no block here has.

## What the specimens show

| | |
|---|---|
| forks | **11**, in 2 archives |
| blocks | **27** — 13 Huffman, 14 stored |
| largest PackBits stream a block declares | **31,806 B**, which is what sizes the engine's segment buffer |
| code counts met | 1, 10, 11, 17, 129, 191, 254, 255, **256** |
| PackBits controls met | 97 distinct, `0x00` to `0xFF`: literal runs of 1 and of 128, repeats of 2 and of 128, and the `0x80` no-op |

One archive is real and one is not. `synth-sit-fixhuf.sit`
(`tools/synth_sit6.py`) exists because the real fork is two Huffman
blocks and reaches none of the stored path, the PackBits edges or a
one-byte alphabet; it is graded by the same two oracles, so it is a
fixture and not a self-test (FORMATS.md, *StuffIt classic: method 6*).

## What this note does NOT cover

The container, which is `docs/formats/stuffit-method-13.md`'s last
section and the page it cites; and every other StuffIt method, each of
which has its own source listed in `src/fmt_sit.c` and `NOTICE`.

# Compact Pro — what the published description gets wrong

Compact Pro's format **is** documented: The Unarchiver's format wiki
describes it in three pages, and `tools/fetch_references.sh` fetches
all three into `reference/notes/` since 2026-09-20 —

| page | covers |
|---|---|
| `cpt_specs_theunarchiver.md` | the archive, file and directory headers |
| `cpt_lzh_theunarchiver.md` | the LZSS + Huffman coder |
| `rle8182_theunarchiver.md` | the `0x81 0x82` run filter |

— **but it fetched only the first of them until that day**, though the
first page's last line links the other two. The project had a full
description of the coder one hop from a file already in
`reference/notes/`, and did not have it.

**What this note is.** The corrections that description needs, each
established by experiment rather than by reading an implementation.
`tools/derive_cpt.py` is a reader written from those three pages
alone; with the corrections below it reproduces **536 forks of 68
archives — every Compact Pro fork in the corpus — byte for byte**
against the sha256 an independent oracle recorded for them. Without
any one of them it does not.

## The corrections

**1. Each code list is preceded by a byte count.** The coder page says
the three codes are "of fixed size: 256 entries in the literal code,
64 entries in the length code, and 128 entries in the offset code …
encoded two to a byte as nibbles". They are not fixed. Each list is a
**count byte `n`, then `n` bytes** of two 4-bit lengths each, high
nibble first; every length after those `2n` is zero. Confirmed
independently of any implementation by **Kraft's equality**, which
comes out at exactly 1.000000 for all three codes when the count byte
is read and nowhere near 1 when it is not.

**2. `Reverse16` is not applied.** The page's code-construction
snippet adds `Reverse16(code)`. Read most-significant-bit-first — as
the same page says the stream is read — the code is simply the top
`length` bits of the accumulator. Reversing them decodes nothing at
all: not one byte of any fork.

**3. The match offset is the 13 bits exactly, and 0 is legal.** The
page says to copy "starting at one byte less than the offset value
before the previously output byte". The seven bits from the offset
code and the six read directly are the distance back from the byte
about to be written, with nothing added or subtracted. **An offset of
zero occurs** and names the byte being written, which a copy that goes
through the window one byte at a time produces naturally.

**4. The match length is the length code's symbol, with nothing
added.** No minimum-match base.

**5. The length in the file header measures the RLE's output, not the
LZSS's.** Neither page says which layer it counts. The LZSS layer has
no length of its own, so the decode has to stop when the RLE stage has
produced the header's byte count — driving the LZSS by it instead
reads past the end of short forks and stops short on forks whose
`0x81 0x82 0x00` escapes make the filter shrink its input.

**6. The file-header table lists one field twice.** "Offset to file
data" appears at `N+2` in two consecutive rows, so a reader that takes
the rows at face value is four bytes out from there on. The fields
are: `N+1` volume, `N+2` data offset, `N+6` type, `N+10` creator,
`N+14` and `N+18` the dates, `N+22` Finder flags, `N+24` CRC, `N+28`
flags, `N+30` and `N+34` the uncompressed lengths, `N+38` and `N+42`
the compressed ones, and the next header at `N+46`.

## What the pages get right, and it is most of it

The archive header, the directory-count scheme (a directory carries
the number of entries below it, sub-directories included, and that
alone rebuilds the paths — which matters, because one archive here has
**twelve pairs of files with the same name in different folders**),
the flags, the fork order within an entry, MSB-first bits, the
literal/match bit, the three code sizes, the block cost accounting
(2 per literal, 3 per match, block ends at or past `0x1fff0`), and the
flush between blocks — align, then skip three bytes if an odd number
was consumed since the block's codes began, else two. Every one of
those was exercised: the corpus has forks of half a megabyte, which
span many blocks.

## What it does not cover

Encryption (the spec says the algorithm is unknown; no fixture here
has an encrypted entry), and the segmented-archive scheme, which is
`fmt_cptseg.c` and the author's own manual
(`reference/notes/cpt_users_guide.txt`).

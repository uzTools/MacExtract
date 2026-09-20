# StuffIt method 13, and the StuffIt container

Method 13 is StuffIt's LZSS + Huffman coder: a 64 KB window, two
combined literal-and-length codes of 321 symbols, and a code for the
BIT LENGTH of each match offset. It is the method most of the corpus
uses, and the one the inventory recorded as having "no other reader
anywhere".

**It is published.** The Unarchiver's format wiki documents it in full
— the meta-code that the in-stream code lengths are themselves coded
with, the five predefined code sets, and every table, printed as C
arrays. `tools/fetch_references.sh` fetches it since 2026-09-20:

| page | covers |
|---|---|
| `sit13_theunarchiver.md` | the coder, its meta-code, and the tables |
| `sit_format_theunarchiver.md` | the archive and file headers |

**What this note is.** The corrections those pages need. A reader
written from them alone — `tools/derive_sit13.py`, which even parses
the tables out of the page rather than holding a copy — reproduces
**790 method-13 forks across 94 archives** byte for byte against the
oracle's sha256, meeting **all six code selectors**: in-stream codes
245 times and each of the five predefined sets. Without either
correction below it reproduces none.

## The corrections

**1. "In addition" means in addition.** The page lists what each
meta-code value does — 34, 35 and 36 "set the length of that many code
entries" — and then says: *"Finally, set the length of the next code
entry to be equal to the length variable, in addition to any code
entries you may have set while processing the input value."* That
final entry is written after the repeats too, not instead of them. A
reader that treats the repeat cases as complete produces lengths that
miss **Kraft's equality — 1.53 instead of 1.00** on the first fork
tried, which is how this was found with no implementation to compare
against.

**2. The match offset is one further back than the page says.** It
says the match "starts at the position of the last byte written minus
the offset value". The distance is measured from the byte ABOUT TO BE
written, so it is the offset **plus one**. (Compact Pro's page has the
same ambiguity in the other direction: there the offset is exact. Two
formats, two pages, one sentence apiece, opposite answers — the only
way to tell is to decode something.)

## What the pages get right

Everything else, and it is the hard part: the header byte's selector
(high nibble 0 for codes in the stream, 1-5 for the predefined sets;
bit 3 meaning the second code repeats the first; the low three bits
plus ten giving the offset code's size), **least-significant-bit-first
reading throughout**, the meta-code's 37 entries, the `Reverse32` in
the code construction — which really is needed here, LSB-first, unlike
Compact Pro's page where it is not — the length escapes at 318 and
319, the end marker at 320, the alternation between the two literal
codes, and the offset written as a bit length with an implied high
bit.

The container page is right as written: a 112-byte file header
whatever it describes, method 32 opening a folder and 33 closing one,
the resource fork before the data fork, and the next header after
both. Ninety-four archives walked with it, every entry matching the
name the oracle recorded.

## The tables are the page's now

`src/sit13_tables.h` was generated from `XADStuffIt13Handle.m` until
2026-09-20. All seventeen arrays were compared against the page's
copies first — **identical, element for element** — and regenerating
from the page reproduces the committed header byte for byte.
`tools/gen_sit13_tables.py` reads the page.

## What this note does NOT cover

Encryption (bit 4 of the method field; the page says the algorithm is
unknown, and this engine reads those entries by a different route —
FORMATS.md, *Encryption*), and every other StuffIt method: 0, 1, 2, 3,
5, 6 and 8 have their own sources, listed in `src/fmt_sit.c` and
`NOTICE`.

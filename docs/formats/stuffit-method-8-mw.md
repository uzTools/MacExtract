# StuffIt classic method 8 — the "MW" coder

StuffIt's method 8 is an LZ coder whose dictionary entries are the
**concatenation of two earlier entries** rather than an entry plus one
byte. That is Miller and Wegman's variation on Ziv-Lempel (1985), which
is where the two initials in XADMaster's name for it come from.

**Where this came from.** Derived on 2026-09-20 from the format's own
output, by experiment. A decoder was written against a family of
hypotheses and every parameter searched, scored by how much of the
oracle's own bytes came back; the combination kept is the one that
reproduces **whole forks**, byte for byte, against the sha256 `unar`
had already recorded for them. `tools/derive_stuffit8.py --grid`
re-runs the search; without `--grid` it re-runs the table below.

## The rule

Codes are read **least-significant bit first**, running straight
through the bytes with no padding between them.

- The dictionary starts with the 256 single bytes, codes `0`-`255`.
- A code is decoded to its string. Codes below 256 are that byte;
  above, the entry is a **pair of codes**, and its string is the first
  one's followed by the second one's — so expanding is a walk, and a
  decoder without recursion needs a stack.
- After each code but the first, a new entry is added: **(the previous
  code, this code)**. This is the whole of the dictionary rule; nothing
  is added for the first code of a stream.
- The code width starts at **9 bits** and grows by one whenever the
  next entry to be assigned would not fit in it — at 512, 1,024, 2,048
  and so on. **Thirteen bits is the widest any specimen here reaches**;
  where it stops is in the last section.
- Decoding stops when the caller has the byte count the entry header
  gave it. Nothing in the stream says how long the output is.

## What the specimens show

| specimen | entry | fork | bytes | codes | entries | widest code |
|---|---|---|---|---|---|---|
| `derived-DSKDUP.sit` | `DiskDup+` | rsrc | 17,005 | 7,348 | 7,347 | 13 bits |
| `derived-DSKDUP.sit` | `Read Me - DiskDup+` | data | 2,835 | 1,289 | 1,288 | 11 bits |
| `derived-DSKDUP.sit` | `Read Me - DiskDup+` | rsrc | 1,301 | 856 | 855 | 11 bits |
| `derived-BitMap11.sit` | `BitMapHelp.index` | data | 3,072 | 452 | 451 | 10 bits |

Four forks in two archives — **every method-8 fork the corpus has** —
each reproduced in full against `unar`'s sha256.

A fifth fork of the same family does NOT decode under this rule and is
not counter-evidence: `BitMapHelp.index`'s 286-byte resource fork is
**method 5**, which the engine reports when asked. The oracle names one
method per ENTRY and StuffIt chooses per FORK, so an entry named "MW"
can carry a fork that is not.

## A writer's restart

**Measured 2026-11-22.** StuffIt Deluxe 2.0.1's `optimal` (STR# 261's
"LZ-M (Optimal/Better)") over 200,000 bytes of word salad wrote a
method-8 fork of 26,564 bytes (`tools/vmac/sitopt.py --mw`;
`specimens/sitopt/mw-1`). It restarts its table ten times: **a code
equal to the next free one** throws the dictionary away and the next
code is read at 9 bits against 256 entries. Read that way, the fork
decodes to the 200,000 bytes it was given, byte for byte.

| table | input it coded | entries | widest code |
|---|---|---|---|
| 1-10 | 18,866 to 19,257 bytes each | 1,836 to 2,030 | 12 bits |
| 11, the last | 9,343 bytes | 1,104 | 11 bits |

The restart comes after about 19 KB of input whatever the entry count,
so **hypothesis**: 2.0.1 restarts once a table has coded about 18.8 KB.
The corpus's largest fork, 17,005 bytes, stops short of that. The fork
stops at its declared length with zero bits after the last code, and no
end code. Over 300,000 bytes of random hex digits `optimal` chose method
3 (Huffman), and over 60,000 random bytes it stored the fork.

## What Aladdin's reader does at the edge

**Measured 2026-11-22.** No writer here reaches the table's ceiling or
writes an end code, so StuffIt Expander 4.0.2 was fed streams built to a
stated rule (`tools/vmac/mwexp.py`): one data fork each, every code a
literal byte except where named, so only the code WIDTH can be in
dispute.

| stream | Expander wrote |
|---|---|
| `w14`: 16,000 literals, the table to 16,255 entries, codes 9 to 14 bits | all 16,000 bytes |
| `fullrestart`: 16,129 literals (the table to 16,384 entries), then 16,384 at 15 bits, then 871 literals from 9 bits | all 17,000 bytes |
| `grow15`: 17,000 literals, 15 bits from 16,384 entries | 16,130 bytes, then stopped |
| `stay14`: the same, 14 bits from 16,384 entries | 16,130 bytes, then stopped |
| `reset`: the same, the table restarting by itself at 16,384, 9 bits | wrong from byte 16,129 |
| `endcode`: 4,000 literals, then a code five past the next free one, then 100 literals; 4,100 declared | 4,000 bytes |

Where it stopped short it kept what it had and said *"The integrity of
the data fork of this file could not be verified."* Two controls passed
first: 300 literals, and Deluxe 2.0.1's own ten-restart fork (*A
writer's restart*) in the same container.

So:

- **The width grows to 15 bits at 16,384 entries** (`fullrestart`: a
  14-bit reader takes the restart code as a literal 0).
- **A full table restarts like any other**; it does not restart by
  itself (`reset`).
- **The table's last entry is 16,384.** The code that adds it decodes;
  the next one stops the stream (`grow15`, `stay14`: 16,130 bytes are
  codes 0 to 16,129). This is where `src/fmt_sit.c`'s 16,385-entry
  dictionary stops too.
- **A code greater than the next free one ends the stream**, and what
  follows it is not read (`endcode`).

What this cannot see: whether Expander would read on past 16,385 entries
in a stream where it had not stopped (none can be built), and anything
about a writer: Deluxe 2.0.1 restarts at about 2,000 entries and wrote
no end code (*A writer's restart*).

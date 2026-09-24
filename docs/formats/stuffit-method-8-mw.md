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

## What this note does NOT establish

Two rules in the shipped decoder are **not exercised by any specimen
here**, and this note does not claim them:

- **The table restart.** `src/fmt_sit.c` treats a code equal to the
  next free one as an instruction to throw the dictionary away and
  start again at 256 codes and 9 bits. No fork above reaches it: the
  largest, 17,005 bytes out, never fills the table.
- **The end of the stream.** The same decoder stops on a code greater
  than the next free one.
- **Where the width stops growing.** The shipped decoder caps it at 14
  bits and its dictionary at 16,385 entries. The widest code in any
  fork above is **13**, at 7,347 entries, so the cap is a number this
  note cannot confirm — the same 17,005-byte fork that fails to reach
  the restart fails to reach this.

Both came from `XADStuffItOldHandles.m` and still do; they are the part
of this row that a derivation could not take. **What would close all three:** a method-8 fork whose dictionary fills
— 16,384 entries against the 7,347 of the largest here, so something
several times larger than anything in the corpus. Synthesising one
here would only hold this project's two readings against each other,
and `unar` is not independent of the rule in question, so neither
would settle it.

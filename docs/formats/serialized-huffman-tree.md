# The bit-serialized Huffman tree

Used by **StuffIt classic method 3**, **DiskDoubler method 4** and
**PackIt**'s compressed entries. All three write the same thing: a
Huffman tree spelled out bit by bit, then the coded bytes.

**Where this came from.** Derived on 2026-09-20 from the formats' own
output, by experiment, and from nothing else. No implementation of the
format was consulted: a grid of plausible serialisations was tried at
every byte offset of a real archive, and the one combination kept is
the one whose decode reproduces **the whole fork**, byte for byte,
against the sha256 an independent oracle (`unar`, or the published
original) had already recorded for it (`fixtures/manifests/`). The
probe scripts are in the commit that added this file; re-deriving it
takes about a minute per fork.

This note exists so the decoder can be written from a description of
the FORMAT rather than transcribed from somebody else's program
(OPEN_ITEMS.md, *What is still XADMaster's*). It is in `docs/` and not
in `reference/notes/` for one reason: `reference/` is fetched material
and is not committed, and a description nobody can read is not one.

## The rule

Bits are read **most-significant first** within each byte, the stream
running forward through the bytes.

**The tree, in pre-order, one bit per node:**

| bit | means |
|---|---|
| `1` | a **leaf**, followed by **8 bits, MSB first**: the symbol |
| `0` | an **internal node**, followed by its *zero* subtree, then its *one* subtree |

The first node read is the root. Nothing states the tree's size: it
ends when every branch taken has reached a leaf.

**A symbol, per output byte:** start at the root and read one bit per
step — `0` takes the zero subtree, `1` takes the one subtree — until a
leaf; the leaf's 8-bit value is the byte.

**There is no end-of-stream symbol and no count.** The caller already
knows how many bytes it wants: StuffIt and DiskDoubler from the fork
length in the entry header, PackIt from the header it carries *inside*
the coded stream (below). Decoding stops when that many symbols have
come out, wherever in the byte the bit stream happens to be.

Symbols are 8 bits, so a tree has at most **256 leaves and 255
internal nodes**.

**PackIt codes its entry header too.** The coded stream of a PackIt
entry is `94-byte entry header || data fork || resource fork ||
CRC-16`, all of it Huffman-coded together under one tree — so a PackIt
tree is never trivial, and the first 94 bytes that come out of it are
the header whose `dlen`/`rlen` fields say how much of the rest is
which. StuffIt and DiskDoubler code the fork alone.

## What the specimens show

Every row decoded with the rule above and matched the oracle's sha256
for the whole fork. "Leaves" and "depth" are of the tree the stream
carried.

| specimen | format | fork | bytes | leaves | depth |
|---|---|---|---|---|---|
| `derived-ScrollbarPattern.sit` | StuffIt 3 | rsrc | 3,469 | 224 | 12 |
| `derived-ComIT14.sit` | StuffIt 3 | data | 6,846 | 79 | 13 |
| `derived-AdobeNumbers.sit` | StuffIt 3 | data | 2,060 | 65 | 11 |
| `derived-DDArchive.sit` | StuffIt 3 | data | 582 | 51 | 9 |
| `derived-DDT.sit` | StuffIt 3 | data | 1,473 | 58 | 10 |
| `derived-Diddle.sit` | StuffIt 3 | data | 352 | 51 | 8 |
| `derived-ExtraDAs.sit` | StuffIt 3 | data | 1,398 | 56 | 10 |
| `derived-Jump_Start_1.4.sit` | StuffIt 3 | data | 693 | 55 | 10 |
| `derived-Jump_Start_1.4.sit` | StuffIt 3 | data | 901 | 52 | 10 |
| `synth-dd-m4.dd` | DiskDoubler 4 | data | 1,145 | 256 | 11 |
| `synth-packit-2.pit` | PackIt | stream | 2,496 | 45 | 11 |
| `synth-packit-2.pit` | PackIt | stream | 1,646 | 45 | 10 |
| `synth-packit-2.pit` | PackIt | stream | 796 | 25 | 7 |

**Thirteen forks, none skipped**, and `tools/derive_huffman_tree.py`
re-runs the whole table (and `--grid` re-derives the rule from
scratch). The nine StuffIt forks come from eight archives and are graded against
`unar`. The
DiskDoubler specimen is one **Salient's own 1991 expander reads back**
(DECISIONS.md 2026-08-21, *methods 3, 4 and 5*), which is the vendor
grading this bit layout rather than a second reader agreeing with us.
The PackIt entries each decode to a header carrying their own name and
fork lengths, which is the format checking the reading from inside.

## What this note does NOT establish

- **The degenerate single-leaf tree.** No specimen here has one: PackIt
  codes a 94-byte header into the same stream, so its smallest tree is
  25 leaves, and the smallest StuffIt method-3 tree measured is 51. A
  bare leaf is well-formed under the rule and consumes **no bits per
  symbol**, so a decoder must stop on its own length and can never let
  the stream stop it. This is not a hypothetical worry: during the
  derivation a bare leaf produced a **false positive** — the nine bits
  `1` + a byte occur somewhere in almost any file, and they "decode"
  into any number of copies of that byte, so they matched a fork of
  700 identical bytes at an offset that meant nothing. Degenerate
  matches are excluded from the table above for that reason.
- **The deepest code the encoders emit.** 13 bits is the most seen. The
  rule permits 255.
- **What a malformed tree means.** More than 256 leaves, or a stream
  that ends mid-tree, is not described anywhere; this engine treats
  both as a per-entry error.
- **Where a fork's coded bytes begin.** That is each container's
  business and not this note's.

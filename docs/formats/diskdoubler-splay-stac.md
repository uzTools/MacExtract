# DiskDoubler's methods 2, 5 and 7: the splay-tree code and Stac LZS

What Salient's own decoders for these three methods do, read out of
DiskDoubler 3.1.2 and run under `qemu-m68k` (2026-11-09). Everything below
is **measured** unless it says otherwise. The algorithms themselves are
published, and are cited where they are used:

- **the splay-tree code** is Douglas W. Jones, "Application of splay trees
  to data compression", CACM 31(8), August 1988, pages 996-1007; his own
  decoder, `minunsplay.c` (1990, "may be used or copied for any purpose"),
  is `reference/notes/splay_jones_minunsplay.c`;
- **Stac LZS** is ANSI X3.241-1994, whose token grammar RFC 1974 section
  2.5.5 repeats: `reference/notes/rfc1974.txt`.

What this page adds is DiskDoubler's framing of each, which neither
describes.

**Where the code is.** `DiskDoubler™ App` 3.1.2 (type `APPL`, creator
`DDAP`, Salient Software, 1991), uncompressed on the 3.1.2 distribution
floppy (`$UNC_VMAC_HOME/ndd/dd312/`, DECISIONS.md 2026-08-21, *the Salient
disk*). `CODE` 11 holds both software decoders; `CODE` 7 @0x0070 is the
CRC-16 one of them calls. Offsets are into each resource's data. The
decoders are THINK C with their globals off A5 and reach the File Manager,
the Memory Manager and the progress callback only through the jump table,
so `tools/ddcode/dd_run.c` calls them as they are with its own stubs in
the table, and `tools/ddcode/run_ddcode.py` checks the bytes cited below
before using them.

| routine | `CODE` 11 | arguments |
|---|---|---|
| splay decoder, methods 2 and 5 | @0x221e | input stream, output stream, (unused), output length, expected sum |
| Stac decoder, method 7, in software | @0x34e2 | the same, with the expected check byte |
| Stac by the Sigma card | @0x2cc8, chosen @0x2c5c | not run here: it needs the card |

## Methods 2 and 5: the splay-tree code

Jones's code, one tree per context.

- **The tree** (@0x1e6a), 1,536 bytes: a parent byte for each of nodes
  0..511, then the left child of internal nodes 0..255 as 16-bit words,
  then the right child. It starts complete: node *n*'s parent is *n*/2 for
  *n* = 2..511 (@0x1e80, to 511 @0x1e90), internal node *j*'s children are
  2*j* and 2*j*+1 for *j* = 1..255 (@0x1ea2, to 255 @0x1ed2). The root is 1
  and leaf 256 + *b* is byte *b*. Jones's tree is the same shape over 257
  leaves (`initsplay`); DiskDoubler has no end symbol.
- **A byte** (@0x2330..0x2390): from the root, take a bit — input bytes
  most-significant bit first (@0x2374), 1 is the right child — until the
  node is a leaf (@0x238a, above 255); the byte is the leaf minus 256.
  Jones's `uncompress`.
- **After each byte, the leaf is semi-splayed** (@0x1f20, called @0x2398):
  while its parent is not the root (@0x1f58), it trades places with its
  parent's sibling, its grandparent becoming its parent, and the walk
  continues from the grandparent. That is Jones's splay loop step for step.
- **The context** (@0x1fb6..0x1fc0): the next byte is decoded with tree
  number *byte* AND (*count* − 1), *byte* being the leaf's value before the
  XOR below. Method 2 has 256 trees (@0x22c6); method 5 reads *count* from
  the fork's first byte (@0x2250), 0 meaning 256 (@0x228c), and refuses
  anything but 32, 64, 128 and 256 with -20999 (@0x1dfc). All trees start
  in the state above (@0x1ee0 builds one and copies it).
- **What is written** is the byte XORed with the word at A5−1544
  (@0x23a4) — 0x5a or 0, by the header's `info1`/`info2`
  (docs/formats/diskdoubler-container.md, *The XOR garbling*) — and the
  16-bit sum of what is written is compared with the header's when the
  header's is not zero, -20999 if they differ (@0x240e).
- **The length** is the header's: exactly that many bytes are decoded
  (@0x2402); input past them is not read. A zero-length fork reads nothing
  (@0x2236).
- **Memory**: the trees are allocated together, *count* × 1,536 bytes
  (@0x242e), halving the count down to 32 while the allocation fails; a
  fork whose count exceeds what was allocated is refused with -20998.

## Method 7: Stac LZS

- **A fork of length 1** is that byte, stored: no header, no
  complement, no check (@0x3520..0x3558). (No fork here has length 1, and
  the engine does not take this branch.)
- **Otherwise the fork starts with a chunk table** (@0x355c..0x3664): 18
  bytes, then as many 16-bit entries as the u32 at +6 says, and the CRC-16
  of everything after its first two bytes is the u16 at +0 — `CODE` 7
  @0x0070, polynomial 0x1021, most-significant bit first, from 0; -20999
  if not. On all 24 method-7 forks here (22 off the 3.1.2 floppy, the two
  THINK C libraries on the 3.7 disk), the u32 at +2 is 12,288, the entry
  count is the output length divided by 12,288 rounded up, and the
  entries sum to the length of what follows. **The decoder reads the
  table and nothing else in it**: the stream after it is one bit stream
  for every chunk.
- **Every input byte is complemented** before its bits are taken, most
  significant first (@0x3846, @0x38b6, @0x3914).
- **The tokens are RFC 1974's**: a 0 bit and eight bits is a literal
  (@0x369c); a 1 bit is a match, then 1 and seven bits or 0 and eleven
  bits of offset (@0x36bc..0x36cc), then the length — two bits plus 2
  (@0x36e4); at 5, two more bits added (@0x36f2); at 8, four bits added
  while they are 15 (@0x3706..0x3722).
- **An offset of zero, in either form, ends the stream** (@0x36de). RFC
  1974's end marker is the seven-bit one; the eleven-bit zero ends it too.
  Nothing else does: the decoder neither stops at the header's length nor
  checks that it was reached.
- **The window is 2,048 bytes** (@0x3762) and holds the decoded byte; what
  is written is its **complement** (@0x3776 for a match, @0x39bc for a
  literal). A match copies from *position* − *offset*, byte by byte, so it
  may be longer than the window and overlap itself. The window is an
  uninitialised stack buffer (@0x3506): a match reaching before the first
  byte copies whatever was there.
- **The check** (@0x37c0): an XOR over the decoded bytes, starting from
  0xff (@0x34f4), compared with the expected check byte; -20999 if not.
  Over what is WRITTEN that is the plain XOR when the length is odd and its
  complement when it is even — the parity rule `dd_fork` applies.

### What the engine does differently

None of these is reached by a fork any DiskDoubler here wrote. Each is a
case `run_ddcode.py` sends and lists in its `EXPECT_DIFFER`, but the match
before the first byte, which Salient answers with whatever its stack held:

- **a fork of length 1** is refused for want of a chunk table;
- **the chunk table's CRC is not checked**; the engine reads the entry
  count and steps over the table;
- **a match longer than 65,536 bytes**: Salient's copy counts with `dbf`
  (@0x377e), so it copies the length modulo 65,536 when its output buffer
  has room. A writer's chunk is 12,288 bytes. The engine copies the length;
- **a stream that decodes past the header's length** is written on and
  checked whole by Salient; the engine keeps the header's length and checks
  that;
- **a stream that ends short of it**: Salient answers noErr with the bytes
  it has; the engine refuses the fork as truncated;
- **a match before the first byte**, which the engine refuses rather than
  copy what an uninitialised buffer holds;
- **method 5's count** is not range-checked: 16 and smaller powers of two
  decode, where Salient refuses them; any other count is decoded with the
  mask and fails the sum, so both refuse it (measured at 3 and 100).

## How it was graded

`tools/ddcode/run_ddcode.py` (TESTING.md, *DiskDoubler methods 2, 5 and 7*)
sends the same forks to Salient's code and, in a container, to the CLI:
every method 2, 5 and 7 fork in the corpus, the specimens and the 3.1.2
floppy; splay forks from `tools/vmac/ddencode.py`'s encoder at every count;
and Stac forks from its own encoder for every length to 69, matches up to
65,537 bytes at distances 1 and 9, the longest offsets of both forms,
short offsets in the long form, either end marker, a 200-entry table and
greedy encodings of random, repetitive and word-like data up to 200 KB
in up to 17 chunks. It also checks the three chunk-table facts above on
every method-7 fork it finds.
Patching one instruction of Salient's code per rule must fail it.

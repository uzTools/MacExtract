# CURRENT_WORK.md — the four licence rows that are left

**Written 2026-09-20, rewritten 2026-09-21 when two thirds of it was
done. Delete this file when its items are done or abandoned** — a plan
file that keeps completed rows stops being readable as a list of what
is left (DECISIONS.md 2026-08-24, *PLANNED_WORK.md, closed*). Status
lives in OPEN_ITEMS.md (*What is still XADMaster's*), reasoning in
DECISIONS.md, numbers in FORMATS.md. This file holds the HOW and the
acceptance criteria, and nothing that belongs in those three.

Read CLAUDE.md first. Everything below assumes its rules: 68000
discipline, `./ci.sh` green before every commit, `dist/` rebuilt in the
same commit as any `src/` change, small focused commits pushed to
`main`, never a tag.

## What happened to the rest of it

**Part A — speed, from a 68000 profile — is done**, and so is **Part C,
the housekeeping**. BinHex −36.7 %, StuffIt method 13 −12.0 %, Arsenic
−10.1 % and smaller on both size axes; the SpaceSaver dictionary priced
and declined; the Mac timing table current; all five tiers re-run with
every figure reproduced. Numbers in FORMATS.md, reasoning in
DECISIONS.md under 2026-09-20.

**Part B was nine rows and is four**, one of which needs nothing done.
What closed them was not the plan in this file. The plan assumed these
formats were undescribed and budgeted reverse-engineering campaigns
against emulated applications; **five of them turned out to be
documented**, on a wiki whose forty-page index nobody had opened
(DECISIONS.md 2026-09-20, *forty pages nobody had listed*). So:

> **Before deriving anything, ask whether somebody wrote it down.**
> `tools/fetch_references.sh` encodes what this project believes
> exists, and it had fetched one page of forty. A list of sources is a
> claim like any other.

When nothing exists — true only of Now Compress — the answer is to
**choose an input and look at what comes back**, not to search
somebody else's archives. `tools/vmac/nowcompress.py` and
`tools/pak.py` both compress what they are given.

**The method, in the seven notes it produced** (`docs/formats/`): write
a reader from the description alone, decode WHOLE forks, grade against
the sha256 an independent oracle recorded, and write down every
correction the description needed. `tools/derive_*.py` are those
readers and TESTING.md says what they cannot see. Two tests earned
their keep repeatedly — **Kraft's equality**, which finds a code table
in a stream with no visible structure, and a **block header's own
checksum**, which finds blocks without a container parser.

## Two sessions at once — the protocol

Unchanged from the last brief, and it worked: the second session works
in a worktree and never in the main checkout:

    git worktree add /home/claude/unclassic-b main     # once
    cd /home/claude/unclassic-b                          # and stay there

Both push to `main`. Rebase before every push (`git pull --rebase`); the
conflicts are in exactly four places: `tools/build_mac.sh` (both ratchet
lines — resolve to the size of the REBASED build, measured, never to
either side's number; the check now refuses a non-numeric placeholder,
because one reached CI on 2026-09-19), `FORMATS.md`'s decode-cost
section, `DECISIONS.md`'s index and tail, and `dist/` (never merge a
binary: rebuild it with `sh tools/make_dist.sh` after the rebase and
commit that). Say in this file's item heading which session owns a row
before starting it.

**The emulator is one machine.** Wrap every `--emu mv-4M-1x` or
`mv-1M-1x` run in `flock /tmp/vmac-1x.lock ...` from both sides. All-out
runs and Linux work are fine in parallel. Do not edit the tree while
`run.py` is building.

---

## The one rule that governs all of it

**Nothing is rewritten for the licence alone, and nothing is kept unless
it is measured.** A row is taken when it is at least neutral on every
axis and better on one. "Neutral" means: Mac engine ticks within noise
(±0.5 %), peak heap not higher on any fixture the format has, `CODE` not
higher unless another axis paid for it and the ratchet comment says so.
**A row that turns out neutral and is NOT taken is a result too**: record
it in DECISIONS.md with its numbers and strike it from the inventory.

The licence rows (Part B) are under the same rule, and that is why they
are last: the engine stays LGPL until the LAST transcription is gone, so
a licence row buys nothing today unless it also buys ticks or bytes.

## The measurement protocol, per row

Five instruments. Use them in this order — the profile ranks, the tick
probe prices, and three "roughly zero" claims last week measured +468 B,
+7.8 % and +756 B when priced.

1. **Correctness**: `./ci.sh`, plus the format's own suite where it has
   one (`tools/run_crypt.py`, `run_lzh.py`, `run_arcplus.py`,
   `run_dart.py`, `run_now.py`, `run_ddforks.py`, `run_multihqx.py`).
   A per-entry CRC mismatch is a failure, never a skip. For a rewrite,
   keep the OLD engine binary and diff its output against the new one
   over every fixture of the format — the 2026-09-20 assessment did that
   over 947 fixtures and it is the check that would catch a decoder
   that is wrong where no oracle looks.
2. **The 68000 profile** (ranks, and it ranks better than callgrind —
   x86 counts missed every hot spot the last brief found):

       m68k-linux-gnu-gcc -static -std=c99 -g -Os -mcpu=68000 \
         -fno-tree-loop-distribute-patterns \
         -freorder-blocks-algorithm=simple -fipa-icf \
         -Iinclude -Ithird_party/zlib -DZ_TESTW=0 -DNO_GZIP \
         cli/main.c src/*.c third_party/zlib/*.c -o /tmp/me68k
       mkfifo /tmp/q.fifo
       python3 tools/m68kprof.py /tmp/q.fifo /tmp/me68k > /tmp/prof.txt &
       qemu-m68k -d exec,nochain,in_asm -D /tmp/q.fifo /tmp/me68k t fixtures/<f>

   Per-function counts, then the hottest basic blocks with
   `file:line`. It counts instructions, not cycles: a `mulu`, a
   `divu` or a libgcc helper costs more than its count says, and a
   memory-heavy addressing mode less. Settle a close call on the tick
   probe.
3. **Speed, Mac** (prices): `python3 tools/vmac/run.py --emu mv-4M-1x
   -D UNC_AT_TIMING --timeout <s> --poll 20 --json /tmp/t.json
   fixtures/<f>`. FAIL by construction; engine ticks = `values[3]` minus
   `values[4..6]`. `--expect` for a fixture without a manifest,
   `--out-kb 2400` for an entry over the 1,440 KB Out floppy, `--timeout
   1700` near a memory minimum. Run in the background; do not touch the
   tree until it finishes.
4. **Size**: `cp -r src include third_party mac tools /tmp/x && cd /tmp/x
   && cmake -B build -S mac -DCMAKE_TOOLCHAIN_FILE=/opt/Retro68-build/toolchain/m68k-apple-macos/cmake/retro68.toolchain.cmake
   -DCMAKE_BUILD_TYPE=Release && cmake --build build`, then
   `/opt/Retro68-build/toolchain/bin/m68k-apple-macos-size
   build/MacExtract.code.bin.gdb` for CODE and A5. Set both ratchets in
   `tools/build_mac.sh` to the measured size with a dated comment.
5. **Heap**: `build/rel/macextract t --stats fixtures/<f>`;
   `UNC_TRACE_ALLOC=1` for every request. Stack: `-fstack-usage`
   (FORMATS.md, *Stack*).

---

# Part B — the licence rows, in the order they could possibly pay

**A page is not a verified fact.** What closes a row is a reader
written from it that reproduces the corpus. These three are what is
left of nine, plus Item 12, which needs nothing.

## Item 5 — Now Compress: the blocks, not the coders (`fmt_now.c`)

**Started and mostly done 2026-09-21**, and it is the only row where
nothing could be fetched: no wiki page, no specification, no second
implementation. So it was measured off the application, which is what
the brief always said this row would need.

**Two coders and the block structure are derived**, and they read
**every specimen the harness has, eight of eight**, byte for byte
(`docs/formats/now-compress.md`, `tools/derive_now.py`):

- a fork is a sequence of **32,768-byte blocks**, each **coded its own
  way** — `mixed.bin` is a stored block followed by a Huffman one;
- **shape 1**, a byte-aligned LZSS: flag byte, eight tokens, matches
  of `length - 2` then distance with a zero escape;
- **shape 2**, the same framing with every byte of it Huffman-coded
  through a 256-symbol table of 4-bit lengths — including the flag
  bytes, which is what gives symbol 255 the shortest code in an
  incompressible file and is how the shape was recognised.

**The block table is derived too**, so the reader no longer searches
for blocks: eight-byte records from offset 144, a u16 offset and a
u16 mode, ending on a record holding the fork's own size; the data
starts 0, 2 or 1 bytes past the offset for stored, shape 1 and
shape 2. Seven of the eight specimens now read straight from it.

**What is left is a layer, not a coder.** The corpus's two archives
are not bare forks — `derived-Expand_Now_1.0.1.sea` is
self-extracting — so there is no block table at 144 to read, and
finding the fork inside the wrapper is the remaining work. Both have
oracle hashes waiting. The only thing still searched INSIDE a fork is
where a shape-2 block's bit stream starts: 23 bits after its table in
one specimen, 18 in another.

## Item 6 — DiskDoubler `ADn` (6/9), and the two `DDn` forks (`fmt_dd.c`)

**Half done, and the half that is left is small and specific.** Both
coders are documented after all — `reference/notes/dd_dd_*.md` and
`dd_ad_*.md`, fetched 2026-09-20 — and a reader written from the DD
page alone, with five corrections, reads **37 of the corpus's 39 DD and AD
forks** (`docs/formats/diskdoubler-dd.md`, `tools/derive_dd.py`).

What is left:

- **the two forks it does not read** — `derived-Terrainman_2.0__.sea`,
  19,240 B and 16,524 B, both genuinely method 10, both decoding to
  the right length and diverging after a few hundred bytes with all
  three code tables satisfying Kraft exactly. The note says what has
  been ruled out. Until they read, `fmt_dd.c` keeps citing XADMaster
  for method 10;
- ~~`ADn`~~ **done**: all five AD forks in the corpus read from its
  page, which needed one correction (flags bit 0 is set for an
  UNcompressed block; the page does not say which way round);
- **the containers**, which stay XADMaster's whatever happens to the
  coders.

## Item 8 — PackIt only (`fmt_packit.c`, macutils)

**Compact Pro left this row on 2026-09-20**: its format is published
after all, in three pages of The Unarchiver's wiki that
`fetch_references.sh` now fetches, and `docs/formats/compact-pro.md`
carries the six corrections they need — 536 forks of 68 archives read
from that description alone (DECISIONS.md, *the description that was
one link away*).

What is left is PackIt, whose container is macutils' `pit.c`. Two of
its facts already moved on 2026-09-20 with the Huffman tree: the
serialisation itself, and that a `PMa4` entry codes its 94-byte header
into the same stream as its two forks. The application is not on this
machine (inventory row: "no"), so PackIt moves only if a specimen set
written by PackIt itself turns up — the existing fixtures are the
corpus's and this project's own generator, which is enough to grade a
parser against but not to write a description from.

## Item 12 — the four container facts (`fmt_macbinary.c`, `fmt_applesingle.c`, `fmt_sitseg.c`, `fmt_stubs.c`)

The inventory's last row: three tolerances no specification supports
and two whole layouts. These are facts, not code, and the licence never
rested on them (DECISIONS.md 2026-09-19, *the facts that were somebody
else's to state*). Nothing to do unless a specification for the StuffIt
split header or the Now Compress probe turns up; leave the row.

---

## Reporting, so the work can be assessed afterwards

For each item, one commit (or a short series) whose message carries the
four-axis table, and a DECISIONS.md entry with the same table, the
reference it was written from, and what was NOT claimed. For a Part B
row, the entry names the note in `reference/notes/` and states that the
XADMaster file was not open while the decoder was written. The
assessment that follows will re-run the ticks on one fixture per item,
diff old and new outputs over the corpus, read the new file against the
note it names, and check the ratchets against a fresh build.

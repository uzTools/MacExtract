# CURRENT_WORK.md — what the 68000 profile left on the table, and the licence rows

**Written 2026-09-20 as a brief for another session. Delete this file when
its items are done or abandoned** — a plan file that keeps completed rows
stops being readable as a list of what is left (DECISIONS.md 2026-08-24,
*PLANNED_WORK.md, closed*). Status lives in OPEN_ITEMS.md (*What is still
XADMaster's*), reasoning in DECISIONS.md, numbers in FORMATS.md. This file
holds the HOW and the acceptance criteria, and nothing that belongs in
those three.

Read CLAUDE.md first. Everything below assumes its rules: 68000
discipline, `./ci.sh` green before every commit, `dist/` rebuilt in the
same commit as any `src/` change, small focused commits pushed to `main`,
never a tag.

The previous brief of this name (PLANNED_WORK.md, 2026-09-19) is done:
DES fold, Arsenic from Russotto, Compact Pro fused, LZH from lhasa, LZW
from Welch, parsers re-cited, DART specimens pinned. Its items were
chosen because Linux ranks said they were hot. **This one was chosen
from a 68000 instruction profile** (`tools/m68kprof.py`, below), run on
2026-09-20 over the five formats that had not been profiled that way:

| fixture | 68000 instructions | where they go |
|---|---|---|
| `macburger-helper.hqx` (BinHex) | 34.6 M | `bh_get_bits` 41 %, `bh_next` 29 %, `unc_bufin_next` 10 %, CRC-16 8 % — **taken 2026-09-20, 22.2 M** |
| `derived-Ultimate_Copland_1.1.sit.1` (StuffIt 13) | 40.4 M | fork body 34 %, `unc_canon_decode` 28 %, **`unc_fork_put` 14 %**, CRC-16 10 % — **taken 2026-09-20, 35.8 M** |
| `derived-MacPass390.sea` (Compact Pro) | 29.0 M | `unc_canon_decode` 34 %, `unc_cpt_lzh_fork` 34 %, two CRCs 23 % |
| `derived-MUSFMT10.ZIP` (zip) | 15.3 M | zlib `inflate_fast` 53 %, CRC-32 35 % |
| `derived-a2basic.dmg.sit` (Arsenic) | 162 M | `ars_decode` 56 %, MTF and BWT 31 %, `__mulsi3` 4 % — **taken 2026-09-20, 157.4 M** |

What that profile says is at the floor, so nobody re-opens it: the three
CRC routines are table-driven and unrolled at ~10 instructions a byte
(the 39 per block in the profile is a four-byte block), which is where
C on a 68000 stops without the 3 KB slicing table the A5 world cannot
afford; zlib is zlib; Compact Pro and every LZH family were rebuilt on
2026-09-19. **The CRC share looks large only because the decoders got
cheap.**

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

# Part A — speed, from the profile

**All three of Part A's rows are done and struck.** Method 13 flushes runs out of
its own window instead of calling `unc_fork_put` per byte — engine
4,395 → 3,867 ticks, −12.0 %, for +140 B of code and −12 B of A5
(DECISIONS.md 2026-09-20, *the window that was already the staging
buffer*); Item 4 below inherits it and now has a floor to beat.

**Item 3 (Arsenic)**: the coder's two products are two `mulu.w` and a
shift instead of `__mulsi3` — engine 18,916 → 17,002 ticks, −10.1 %,
for −20 B of code and −12 B of A5 (DECISIONS.md 2026-09-20, *what a
helper call costs that its count does not say*). **Its second half is
NOT done**: taking `k` renormalisation bits at once, named a
hypothesis in the previous brief and still never run — the count is
usually 0 to 2, so the win is small and the code grows. One tick run
settles it.

**Item 1 (BinHex)**: the line is read, judged and
converted in one pass and four characters become three bytes at once —
engine 3,771 → 2,386 ticks on a Mac Plus, −36.7 %, for +240 B of code
(DECISIONS.md 2026-09-20, *the character that was touched three
times*). **Part A is otherwise empty.**

---

# Part B — the licence rows, in the order they could possibly pay

**Item 8's Compact Pro half is done and struck**: see the row below,
which is now PackIt alone.

**Item 9 is done and struck, most of it**: ARC's member header, its
RLE90, and methods 4, 8 and 9 are derived from archives ARC 5.21q
wrote to order (`docs/formats/arc-container-and-coders.md`,
`tools/derive_arc.py`). Methods 5/6/7 stay XADMaster's because that
encoder will not write them, and PAK's Crushed stays XADMaster's
because it did not fall to an LZW parameter search — those two are
what is left of the row.

**Item 7 is done and struck, four fifths of it**: method 8 is Miller
and Wegman's dictionary rule, derived from all four method-8 forks the
corpus has (`docs/formats/stuffit-method-8-mw.md`,
`tools/derive_stuffit8.py`). Three rules no specimen reaches — the
table restart, the end-of-stream code, the 14-bit ceiling — stay
XADMaster's and say so in the file; only a much larger fork closes
them, and neither reader on this machine is independent of the rule in
question (DECISIONS.md 2026-09-20, *four forks, and the three rules
none of them reach*).

**Item 10 is done and struck**: removing `-lh2-`/`-lh3-` and their two
dispatch arms is worth **3,472 B of `CODE` and 32 B of A5**, measured
on a build without them. The number is beside the row in OPEN_ITEMS.md
with what stands against it; taking the decision is the maintainer's
and this file will not.

**Item 11 is done and struck, and it closed without a rewrite**: the
serialized Huffman tree now has a description of this project's own,
derived from thirteen forks of the three formats that write it
(`docs/formats/serialized-huffman-tree.md`,
`tools/derive_huffman_tree.py`), so `unc_huffman.c`, `fmt_sit.c`'s
method 3, `fmt_dd.c`'s method 4 and `fmt_packit.c`'s tree cite that
instead of XADMaster and macutils. The decoder is unchanged, because
the rule below says a neutral rewrite is recorded and not taken
(DECISIONS.md 2026-09-20, *the tree that could be measured instead*).

These are the rows of OPEN_ITEMS.md's inventory (*What is still
XADMaster's, and what would have to replace it*) that have **no
non-copyleft description anywhere**. Each can only be rewritten by
reverse-engineering against the original application, all of which run
under the emulator harnesses here; that is how SuperDisk! and SpaceSaver
were done (DECISIONS.md, *SuperDisk!, read out of SuperDisk!* and the
2026-08-22 SpaceSaver series; the harness scripts are
`tools/vmac/superdisk.py` and `spacesaver.py`, and the modules they
graded live in `tools/sdmodule` and `tools/ssmodule`).

**The method for every row is the same, and it is not "read the
XADMaster file and paraphrase it"**, which produces a derivative work
under the same licence. It is: write down what the FORMAT fixes (the
bit-exact facts: header layout, code lengths, window sizes, the
meaning of each symbol) as a spec in `reference/notes/<format>.md`,
sourced from the original application's behaviour on synthesized inputs
(the `tools/synth_*.py` scripts and the `tools/vmac/*.py` harnesses
already produce those), then write the decoder from that note with the
current file kept as the A/B oracle and never open while writing. The
note is the deliverable that moves the licence; the code is the part
that has to be at least neutral.

**And the rule holds:** a row whose rewrite is slower or bigger is
recorded and not taken, however much cleaner its licence. Do the cheap
half — the spec note — regardless, because it is worth having even when
the code does not move, and it is what the next attempt starts from.

## Item 5 — Now Compress (`fmt_now.c`, `XADNowCompressHandle.m`)

The whole file is XADMaster's, container and coder. Now Compress runs
here and `tools/vmac/nowcompress.py` writes and adjudicates archives
(`--case all`, `--verify`, `--adjudicate`); `tools/synth_now.py` and
`tools/run_now.py` are the suite. The 2026-09-19 slot change made it
0.3 % faster and `UNC_HOT` was declined at 0.3 %, so this row is
licence-only and will be neutral at best: the note is the deliverable,
the decoder moves only if it is not worse.

**Fixtures:** `synth-now-mixed.now`, the Now Compress rows of
FORMATS.md's table, and the specimens `nowcompress.py --case all`
writes. **Acceptance:** `run_now.py` green, ticks and CODE not higher.

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

# Part C — housekeeping the week left behind

- **The Mac timing table is stale, and three of its rows are not.**
  FORMATS.md, *Measured on a 7 MHz Mac Plus*: BinHex (107 → 83 s) and
  Arsenic's a2basic (542 → 321 s, both memory columns) were re-measured
  2026-09-20, and both yardstick rows with them (*Timed on the same Mac
  Plus*). What is left is LZH, LZW, Compact Pro and `-lh1-`/DART, each
  carrying a number from before 2026-09-18/19, plus
  `derived-Library_ISBN_Barcoder.sit`, whose pair is half an hour of
  emulator. The rows that did not change are the control and should
  reproduce within ±0.5 %.
- **The 4 MB and 512 KB tiers have not been re-run** since the
  decoder work of 2026-09-18/19/20. Both 1 MB tiers were, on
  2026-09-20 — System 6.0.8 and System 3.0, **69/69 each**, no refusal
  moved (BLOCKERS.md, the tier table) — and 1 MB is the floor the
  refusals live at, so the other two are a formality rather than a
  question. `tools/run_tiers.py` in `ci.sh` predicts; the emulator is
  the measurement.
- **The SpaceSaver dictionary** is 9,679 B of constant data
  (`src/ss_dict.h`), in the CODE resource of every build (`size` puts
  all of `fmt_spacesaver.c.obj` in text); deflated at level 9 it is
  5,182 B. Storing it deflated and inflating it into the heap for the
  one entry that needs it is a hypothesis worth pricing: zlib is already
  linked, so the cost is a ~10 KB heap transient (the inflated
  dictionary) plus inflate's state during a SpaceSaver entry, and the
  inflate's ticks once per entry, against ~4.5 KB of CODE back for
  every user. Price the ticks and the heap high-water mark on the
  largest SpaceSaver fixture before deciding; a SpaceSaver entry near
  its 1 MB minimum may not have the 10 KB.

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

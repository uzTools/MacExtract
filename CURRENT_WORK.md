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

## Item 4 — StuffIt method 13 (`fmt_sit.c`, `XADStuffIt13Handle.m`)

The one licence row that is also hot (Item 2 is its speed half; do that
first, then this rewrite inherits it). Two Huffman trees (first,
second, offset) built from code lengths that the stream carries in its
own coded form (`sit13_parse_code`, 8 % of the run), an LZ layer with
the length escapes at 0x13e/0x13f and the end marker 0x140, a 64 KB
window. StuffIt Deluxe 3.5.1 runs here (`tools/vmac/sitcrypt.py` drives
it) and writes method 13; `tools/gen_sit13_tables.py` already
regenerates the fixed tables. The spec note has to state the code-length
alphabet and how it is itself coded, which is the part with no public
description.

**Fixtures:** the method-13 fixtures above. **Acceptance:** byte-exact on
all of them and on new ones written by StuffIt Deluxe from synthesized
inputs (`tools/synth_sit6.py`'s shape, for method 13), ticks not higher
than after Item 2, CODE not higher.

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

## Item 6 — DiskDoubler `ADn` (methods 6/9) and `DDn` (method 10) (`fmt_dd.c`)

Documented nowhere else. DiskDoubler 3.7, 4.0 and Pro 4.1 run here and
graded every method (`tools/vmac/ddencode.py`, `tools/run_ddtf.py`,
`tools/run_ddforks.py`); `tools/xadmaster-ddn-repro/` holds the DDn
off-by-one this engine reads correctly and XADMaster does not — the
note must state the correct reading, which is already this engine's.
Methods 2/5 are splay, a published algorithm, and are not on this row.

**Fixtures:** the `ddtf-*` set (82 CC0 files against their originals),
the 6 harvested and 28 specimen DiskDoubler fixtures. **Acceptance:**
`run_ddtf.py` and `run_ddforks.py` green, ticks not higher on the
largest method-10 fixture in FORMATS.md's DiskDoubler table.

## Item 7 — StuffIt method 8 (`fmt_sit.c`, `XADStuffItOldHandles.m`)

Not hot on anything; one fixture family. FORMATS.md's *Floor target
verification* section records that method 8 has a real external oracle
and where it came from. Licence-only; spec note first, decoder only if
neutral.

## Item 8 — Compact Pro's container and stages, and PackIt (`fmt_cpt.c`, `fmt_packit.c`, macutils)

Compact Pro 1.51 runs here (`tools/vmac/cptcrypt.py`, `cptsegment.py`);
`tools/synth_cpt.py` and `synth_cptsplit.py` make inputs. The coder was
fused and profiled on 2026-09-19 (−31.7 %), so the rewrite has a hard
floor to meet. PackIt's format is trivial and its container is a page;
the application is not on this machine (inventory row: "no"), so PackIt
moves only if a specimen set written by PackIt itself turns up — the
existing fixtures are the corpus's, not synthesized, which is enough to
grade a parser rewrite against but not to write a note from.

## Item 9 — ARC's Squeeze, Crunch and Crush (`fmt_arc.c`)

Distilled and Trimmed are deark's (MIT) already. Squeeze is Huffman
with a published shape, Crunch 1–9 is LZW with ARC's own quirks and
Crush is PAK's LZW; ARC 5.21's source and PAK 2.51 run under DOSBox
(`tools/pak.py`, `tools/run_pak.py`, `tools/get_arc.sh`). Small on every
axis; note first.

## Item 10 — `-lh2-`/`-lh3-` (`unc_lzdyn.c`)

No corpus archive uses them and lhasa does not implement them; LHa for
UNIX does, under its own licence. Inventory says "none". The only move
that is not a rewrite for its own sake is to ask whether the two
methods should stay at all — they cost CODE on every Mac Plus for a
format nobody has a file of. Measure their CODE (`size` the `.obj`) and
put the number beside the row; the decision is the maintainer's.

## Item 11 — the bit-serialized Huffman tree parse (`unc_huffman.c`)

Used by StuffIt methods 3 and 5 and DiskDoubler method 4 ("StuffIt
Huffman"); the tree is written as a pre-order bit stream, which is a
textbook serialisation whose only public description happens to be
XADMaster's and macutils' `de_huffman.c`. A spec note stating "one bit
per node, 0 = internal, 1 = leaf followed by 8 bits" from the
application's output, and a rewrite of the ~40 lines from that note,
is the smallest licence row there is. Neutral is the expectation;
the note is the deliverable.

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
- **The tiers have not been re-run** since the same changes
  (`tools/run_tiers.py` is in `ci.sh` and predicts; the emulator tiers
  in FORMATS.md, *Floor target verification* and *System 3.0 tier*, are
  the measurement). One pass of each at 1 MB is the check that the
  heap changes of the week — the LZHUF tree at 9,000 B, the transient
  cipher tables, the pooled Arsenic models — did not move a refusal.
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

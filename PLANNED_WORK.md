# PLANNED_WORK.md — proposed, none of it done, in the order to do it

Everything in this file is a **proposal**. Nothing here has been implemented
and nothing here is a status claim: status lives in `PROGRESS.md`,
`OPEN_ITEMS.md` and `BLOCKERS.md`, and none of them changes because this file
exists. When an item lands, move the figure to `FORMATS.md`, the reasoning to
`DECISIONS.md`, and **delete the item from here** — a plan file that keeps
completed rows stops being readable as a list of what is left.

Opened 2026-08-23, from a session that measured the application's memory
layout and read the Mac shell's write and decode paths. Every claim is
labelled **measured** (run in this environment), **derived** (arithmetic over
a model this repository already documents) or **unverified** (neither).

---

## The requirement this file serves

One-pass extraction of an archive as large as an 800K Macintosh floppy —
**819,200 bytes** — on a 1 MB 68000 Macintosh, with mass storage attached for
the output. Only the bytes being decoded should be resident.

**That requirement is already met, and the cost is time rather than memory**
(measured; FORMATS.md, *Floor target verification*):

- Archive size costs **zero** heap. `fio_read` in `mac/unclassic_mac.c` reads
  straight off the file with `SetFPos` + `FSRead` into the engine's own
  buffer; the whole-archive slurp is behind `UNC_MAC_SLURP_ARCHIVE` and off by
  default.
- Output costs zero heap. `sink_begin` returns without pre-allocating unless
  `UNC_MAC_STAGE_WRITES` is defined; the default path streams.
- 62/62 sampled fixtures extract byte-exact at 1 MB with no budget refusals.
  The largest is `derived-Library_ISBN_Barcoder.sit` at 641,115 B — 78 % of a
  floppy.
- That fixture takes **1,898 s (~32 min) at 1 MB** against **768 s (~13 min)
  at 4 MB**. `derived-a2basic.dmg.sit` is 966 s against 587 s.

So the whole of this file is about that gap. It is not a memory shortage: it
is StuffIt 5's sampled inverse BWT, which trades scan time for the memory the
budget will not give it.

---

## The order, and why this order

| # | step | costs | buys (**measured 2026-08-23** unless marked derived) |
|---|---|---|---|
| 1 | ~~Profile the two slow fixtures~~ **DONE** | - | the numbers below; it re-ordered this table twice |
| 2a | Sentinel byte in the BWT scan loop | ~3 lines | **77.35 %** of the run is that ONE LINE; this removes one of its two tests per iteration |
| 2 | Shrink the Arsenic block to its fill | ~10 lines + one allocator op | the same 77 %, attacked from the other side - fewer iterations rather than cheaper ones. **Has a named trap** |
| 2b | Size five windows and tables from the entry, not the format's ceiling | small each | ~128 KB (Now Compress), up to 64 KB (SuperDisk and SpaceSaver), ~30 KB (zip/gzip), ~28 KB (ARC crunch) |
| 2c | Gate or widen the EOCD back-scan | small | **67-70 %** of four different non-zip runs, and 129 File Manager reads per archive on a Mac |
| 2d | Hoist the bound out of the LZW output copy | ~3 lines | **21 %** of a StuffIt classic run, in code four formats share |
| 2f | Give `unc_canon_decode` a peek-and-lookup table | ~40 lines + a peek on `UncBitIn` | **43-71 %** of Compact Pro, DiskDoubler and Now Compress runs. One function, four formats, and `ci.sh` can grade it |
| 2e | Build zlib's crc32.c with `-DZ_TESTW=0` | one compile flag | **5,120 B of resident A5 world**, measured, for a CRC that is never computed (see 7.5) |
| 3 | Hoist and unsign the Arsenic divides, narrow its multiplies | one function | **7.94 %** on one slow fixture, **21.26 %** on the other |
| 4 | `SetEOF` the output fork at create time | three lines | one extent allocation per fork instead of per 8 KB, and `dskFulErr` *before* the entry decodes |
| 5 | The rest of the disk-full handling | small | a full disk becomes legible instead of 100 identical errors |
| 6 | The small loop items | small each | `unc_bitin_bit` **2.15-4.07 %**, the index binary search **1.75 %**, per-file `-O2`, `-flto` |
| 7 | `kMemReserve`, then the budget sweep, then segmentation | a build; then a refactor | 32-80 KB, then ~61 KB, all of it into `target` |

Sections 2a and 2 attack the same 77 %: one makes each iteration cheaper, the
other makes there be fewer of them, and they compose. 2 and 7 both feed the
sampled index's `target`, and 2 is an order of magnitude cheaper per kilobyte
than 7 - which is why the code-size work is last despite being where this file
started.

---

## 1. The profile — measured 2026-08-23, and it re-ordered this file

`valgrind --tool=callgrind` over the Linux CLI (`-O2 -g`) at
`--budget 678392`. That budget reproduces the Mac: the run reports a
614,080 B high-water against FORMATS.md's 614,134 B measured on the Mac
itself, the same 54-byte agreement recorded there.

`derived-Library_ISBN_Barcoder.sit`, 1,195,252,541 instructions total:

| what | Ir | share |
|---|---|---|
| `do { i++; } while (i < n && block[i] != (uint8_t)c);` - **one line** | 924,478,378 | **77.35 %** |
| `ars_next_symbol` (the divides) | 94,858,991 | 7.94 % |
| `unc_bitin_bit` | 25,647,386 | 2.15 % |
| `ars_index_next`'s binary search (two lines) | ~20,944,144 | 1.75 % |
| `unc_crc32` | 11,540,070 | 0.97 % |
| `sit_arsenic_put` (the per-byte output emit) | 6,411,005 | 0.54 % |

`derived-a2basic.dmg.sit`, 487,400,612 total: the same scan line is **62.63 %**
and `ars_next_symbol` **21.26 %**.

**What it settled:**

- **The derivation was right, and by a wider margin than it claimed.** The
  sampled scan is not merely the larger term, it is three quarters of the run.
  Sections 2a and 2 are the whole game.
- **The divides are second and worth doing, not first** - 7.94 % and 21.26 %,
  and only part of that is the division itself.
- **The per-byte output emit is 0.54 %** on this format, which is what section
  6b predicted from cycle counts and why it is filed as a win for the cheap
  formats rather than this one.
- **Linux under-states the divides** (hardware divide) and represents the scan
  faithfully, so 77 % is if anything a floor for a 68000.

### 1b. The same profiler, pointed at the rest of the corpus

Run to answer "which files are worth reading", and it answered by saying the
three that had never been read are not the ones that matter (all **measured**,
`t` mode, no budget cap):

| fixture | format | where the instructions go |
|---|---|---|
| `derived-xmasbeeps.sit` | StuffIt classic, method 2 | **89.5 % in `unc_lzw.c`** (64.31 + 19.41 + 5.82), 9.28 % `unc_crc16_arc`. `fmt_sit.c`'s own code does not appear |
| `a2ps.V4.3.tar.Z` | Unix compress | **96.75 % in `unc_lzw.c`**. `fmt_exo.c`'s own code does not appear |
| `PCCTS.tar.gz` | gzip | 52.67 % zlib `inflate_fast`, **40.70 % `unc_crc32`** |
| `4acalc.zip` | zip | 149,772 Ir total - nothing is hot |
| `xmasbeeps.sit`, `empiredemo.sit`, `adobenumbers.sit`, `alpha401.cpt` | envelopes | **67-69 %** in `unc_zip_scan_eocd` - see 2c |

**So `fmt_sit.c` and `fmt_exo.c` are thin: both hand their work to
`unc_lzw.c`**, which two formats therefore share as their hot path. That is
what section 2d is about. `unc_segment.c` is still unmeasured - the corpus has
no bare segmented set to point the profiler at, since those are generated by
`tools/`.

**The zip A/B is the proof for 2c:** `unc_zip_scan_eocd` costs 456
instructions on a real zip, which finds its EOCD in the first window, and
529,727 on a StuffIt archive, which does not and walks all 64 KB.

**Recorded, not proposed:** `unc_crc32` at 40.70 % of a gzip extraction is
simply what a byte-wise table CRC costs beside zlib's fast inflate. Slicing-by-4
would cut it, and needs aligned 32-bit reads, which CLAUDE.md's 68000
discipline forbids. Left alone deliberately.

### 1c. Where the whole corpus spends its time

929 fixtures, `t` mode, no budget cap, summed by the format `sniff` reports.
**Wall clock on this machine is contaminated** - another session builds
concurrently - so read this as a distribution, not as figures:

| format | total | files |
|---|---|---|
| StuffIt classic | ~1,120 ms | 227 |
| StuffIt 5 | ~990 ms | 31 |
| Compact Pro | ~730 ms | 108 |
| BinHex 4 | ~535 ms | 204 |
| MacBinary | ~437 ms | 234 |
| Now Compress | ~138 ms | 3 |
| DiskDoubler | ~135 ms | 91 |
| everything else | <100 ms | 31 |

Two things fall out. **StuffIt 5 is 31 files and a quarter of the time** -
the tail this file opened with. And **MacBinary costs 1.9 ms per file for
what is a header parse and a fork copy**, which is section 2c: most of it is
a scan for a format it is not.

**The lesson that cost a measurement here:** wall-clock timing on this
machine is unusable while another session builds. A "gated" build measured
*slower* by 50 % on the clock and **-74.7 % on instruction count**. Use
callgrind's `Ir` for anything that matters; it is immune to CPU contention
and to whatever else is running.

**What it cannot see:** `Ir` is instruction count, not cycles, and a 68000 is
not an x86. Use it for RATIOS between engine functions, never as a predicted
runtime. The Mac numbers stay the ones in FORMATS.md.

## 2a. A sentinel byte in the BWT scan - three lines against 77 % of the run

**Claim (measured, section 1).** `ars_index_next`'s scan is

    do { i++; } while (i < n && block[i] != (uint8_t)c);

and callgrind attributes **77.35 %** of one fixture's instructions and
**62.63 %** of the other's to that single line. Two tests per iteration: the
bound and the byte.

**The bound can go.** Before the loop, write the value being searched for into
`block[n]` - `block[n] = (uint8_t)c;` - and every scan is then guaranteed to
stop at `n` at the latest, so the loop becomes
`do { i++; } while (block[i] != (uint8_t)c);`. The corrupt case is caught once
after the loop by the `return i < n ? i : 0;` that is already there. One store
per query replaces one compare-and-branch per iteration.

**It requires one extra byte of block**, which is the one place it touches
section 2: shrink the block to `n + 1`, not `n`.

**Why it is first:** it is three lines, it needs no allocator change, it has no
fragmentation trap, and it attacks the same line section 2 does. They compose -
2a makes each iteration cheaper, 2 makes there be fewer.

---

## 2. Shrink the Arsenic block to its fill before the index is built

**Claim (derived from measured figures).** The block is allocated at
`min(outlen, blocksize)` in `ars_block_reserve`, so a multi-block entry gets
the declared **512 KB** — while the largest block fill measured anywhere in
the corpus is **323,384 B** (FORMATS.md). The tail is never used and never
returned, and the memory it denies goes straight out of the sampled index's
`target`.

**The arithmetic**, from FORMATS.md's measured 1 MB peak of 614,134 B for
`derived-Library_ISBN_Barcoder.sit`: 35,840 parser + 524,288 block = 560,128,
leaving **~54 KB for the index**. Shrinking the block to its fill once the
block completes — which happens before `ars_bwt_prepare` chooses an inversion
strategy — leaves ~255 KB instead. Each halving of `target` doubles the scan
distance, so that is roughly two steps recovered: **~4x less scanning** on the
slowest fixture in the corpus.

**The trap, and it is a recorded one.** `BLOCKERS.md` and the comment in
`ars_block_reserve` record what the old doubling growth cost: a geometric
trail of freed holes, none of which could satisfy the step that followed,
stranding 125,614 B and failing a 498,548 B transform request against a
468,126 B largest run while the budget still showed 678 KB free. **Shrinking
and then re-growing for the next block in the stream re-creates exactly that
shape.** So the safe form is to shrink for the duration of the index build and
show, per block, that the block is not grown again afterwards — or to
establish first, by measurement, that a stream's blocks never grow after the
first.

**It needs an allocator operation that does not exist.** `UncAlloc` has
`alloc` and `free` and no shrink. The Mac host would implement it with
`SetPtrSize` downward, which does not move the block; the CLI with `realloc`.
That is an engine API change, so it wants a `DECISIONS.md` entry of its own.

**Measure first:** instrument `blockcap - numbytes` at `ars_bwt_prepare` over
the corpus. That one number says whether this is worth ~200 KB or ~5 KB per
fixture, and it is a single CLI run.

---

## 2b. Three more windows allocated at the format's ceiling, not the entry's size

**How this was found, because the method is repeatable and needs no
insight:** CLAUDE.md names the smell - *a constant in the peak-RAM matrix is
usually a declared ceiling nobody questioned*, because a data-driven
allocation varies with its input. Run down FORMATS.md's peak column and three
rows show one number where a range belongs: gzip **51 KB**, Now Compress
**128 KB**, and the 64 KB inside SuperDisk's range. Anyone can repeat this:
read the column, and for every row that is a constant, go find the allocation.

**The argument that covers all three (and is why section 2 exists):** a
back-reference window can never reach further back than the number of bytes
produced so far. So when an entry declares an output smaller than the format's
maximum window, the maximum is a ceiling and not a requirement - and each of
these three has the entry's size in hand before it allocates. This project has
already applied exactly this reasoning twice, to the `.Z` LZW table
(274,432 B flat, now sized from the input) and to the Arsenic block
(512 KB declared, now `min(outlen, blocksize)`) - `DECISIONS.md` 2026-08-03.

- **`src/unc_inflate.c`: `inflateInit2(&zs, -15)`** allocates a 32 KB window
  for every deflate stream whatever its size. Zip's local header carries the
  uncompressed size and gzip's trailer carries ISIZE, so
  `windowBits = max(9, ceil(log2(N)))` is provably sufficient for
  N < 32768. This is what makes gzip's peak a flat 51 KB and sets zip's 54 KB
  top end. **Check against the robustness variants:** zlib rejects a distance
  beyond the window with `Z_DATA_ERROR`, but such a distance is invalid
  anyway and already rejected, so the KIND of failure should not change.
- **`src/fmt_now.c`: `unc_alloc(c->al, NOW_INBLOCK + NOW_OUTBLOCK +
  NOW_HISTORY)`** is 131,072 B from three compile-time constants, allocated
  **once per archive, before a single entry is read**. Three 2 KB files cost
  128 KB. Awkward to fix because the buffer is per-archive: size it once from
  the largest entry in the table, not per entry - per-entry reallocation is
  how section 2's fragmentation trap gets re-created.
- **`src/fmt_superdisk.c`: `sd_need(c, &s->win, SD_WINDOW + SD_BLOCKMAX)`**
  takes 64 KB unconditionally for SlowFastB, where `min(ulen, SD_WINDOW)` is
  provably enough.

**Then run it exhaustively, not just where the matrix points.** Classifying
every `unc_alloc` call site in `src/` found two more of the same class:

- **`src/fmt_arc.c`: `ARC_CRUNCH_SIZE * 6u + ARC_STACK_SIZE`** is 28,672 B
  flat for methods 5, 6 and 7, whatever the entry's size - ARC's 32 KB top
  end. Crunch **is** LZW, so this is the identical defect `unc_lzw.c` already
  had and already fixed (the flat 274,432 B, `DECISIONS.md` 2026-08-03), and
  the bound is computed in that same file:
  `insize / 9 * 8 + insize % 9 * 8 / 9`, the most codes a stream of that
  length can define. The ARC header carries the compressed size. **The fix
  exists in this repository and never reached ARC's private copy of the
  algorithm.**
- **`src/fmt_spacesaver.c`: the window is `s->wsize`**, from the entry's width
  byte, where `min(ulen + preset dictionary, wsize)` would do - the 68 KB
  ceiling FORMATS.md notes against a 36 KB measured peak. The preset
  dictionary must still fit, which is why the bound is not simply `ulen`.

**Checked and legitimately constant, so that nobody re-checks them:** Compact
Pro's `CPT_WINDOW` is 8192 because macutils' `CIRCSIZE` is and the format
mandates it (a genuinely constant 19 KB peak); `CPT_DD_WINDOW`,
`DD_STAC_WINDOW` and `DD_AD_BLOCK` are likewise format-mandated;
`ARC_SQ_MAXNODES` is 1,028 B and the stream's own `numnodes` is validated
against it; the 4 KB `iocap`/`ocap` pairs throughout are the streaming
buffers, and the 8 KB floors in the peak column are two of them.

**This class is now exhausted** - every `unc_alloc` site in `src/` is
classified - which is a stronger statement than the section could make when
it was written from the peak column alone.

---

## 2c. Every non-zip archive pays a 64 KB backward scan to be sniffed

**Claim (measured).** Profiling a Compact Pro fixture for contrast,
`unc_zip_scan_eocd` is **529,390 of 759,272 instructions - 69.72 %** of the
whole run. Sniffing cost more than twice the decode.

**Why.** `unc_zipseg_probe` calls `zs_find_eocd` unconditionally on any file
whose size is known, with no cheap precondition first. The scan walks back
`ZS_EOCD_FIXED + 65535 = 65,557` bytes in 512-byte windows - up to **129
reads** - byte-scanning 64 KB. A zip finds its EOCD in the first window
(`end - 22` when there is no comment, which is the common case), so **the full
walk is paid precisely by the files that are NOT zips**: everything probed
after zipseg in `unc_sniff`, which is Compact Pro, ARC, tar, DiskDoubler,
SuperDisk, Now Compress, AppleSingle, LZH and DiskCopy.

**On the Mac the instruction count is the lesser half.** 129 `SetFPos` +
`FSRead` pairs and a seek to the end of the file, before extraction begins. On
a floppy that is a head move and 64 KB read per archive opened.

**Measured 2026-08-23, and it corrects what this section first proposed:**

| build | `xmasbeeps.sit` total Ir | `unc_zip_scan_eocd` | `unc_read_at` |
|---|---|---|---|
| as shipped (512 B window) | 787,183 | 529,727 | 4,420 |
| 4 KB window | 741,891 (**-5.8 %**) | 525,919 (**-0.7 %**) | 612 |
| scan skipped entirely | **198,990 (-74.7 %)** | - | - |

`alpha401.cpt` agrees: 759,272 -> **171,576**, -77.4 %.

- **Widening the window barely touches the cost.** It cuts the read-call
  overhead (129 calls to 17, visible as `unc_read_at` 4,420 -> 612) and about
  6 % of instructions - but the 67-70 % is the BYTE SCAN, and widening does
  not change how many bytes are scanned. Its real value is the 112 File
  Manager traps and the disk access it saves on a Mac, which no Linux
  measurement here can represent. **Do it, but not for the reason first
  written down.**
- **The prize is not scanning at all: three quarters of the instructions in
  opening an envelope.**

**And the root cause is ordering, not the scan.** `unc_sniff` runs
`unc_zipseg_probe` - its most expensive probe - at position 13, and
`unc_macbinary_probe` LAST, after `cpt`, `arc`, `diskcopy` and `superdisk`
have each had a go. **MacBinary is 234 of the corpus's 929 fixtures, the most
common format there is**, and it is identified by a CRC-16 over the first 124
bytes: strong, and free. Every one of those 234 files pays a 64 KB backward
scan for a format it is not, twenty probes before the cheap test that
identifies it.

**So the fix to weigh is the probe order**, and the question is which probes
can move without changing what claims what. MacBinary is last for a reason -
it has no signature, only a CRC and structural constraints, so it must not
claim a file that is really something else. But a CRC-16 match at a fixed
offset is about as selective as a two-byte magic, and MacBinary III carries
`mBIN` at offset 102. **This is a change `ci.sh` can grade**: 929 fixtures
plus 9,190 robustness variants exist precisely to catch a probe claiming
something it should not.

**Gating on a `PK` head is NOT the fix** - the measurement hack that produced
the -74.7 % figure used one, and it would break opening a spanned set by its
LAST part, which is the case `zs_find_eocd` exists for. It measured the prize;
it is not the remedy.

**What this cannot see:** the Mac's File Manager traps and disk seeks, which
are the other half of the cost and the half that matters on a floppy.

---

## 2d. The LZW output copy is the same two-condition loop as 2a

**Claim (measured).** In `unc_lzw_read`, which is the hot path for **both**
StuffIt classic method 2 and Unix compress:

    while (z->chainpos > 0 && produced < want)
        out[produced++] = z->chain[--z->chainpos];

is **13.68 %** (the test) plus **7.19 %** (the body) of a StuffIt classic
extraction - about a fifth of the run, in a loop that tests two conditions to
copy one byte.

**The fix is the shape of 2a.** Both bounds are known before the loop:
`n = chainpos < want - produced ? chainpos : want - produced;` then a counted
loop, one test per byte instead of two.

**Why it is worth more than its share suggests:** `unc_lzw.c` is shared by
four formats (`fmt_arc`, `fmt_dd`, `fmt_exo`, `fmt_sit`), so one edit reaches
StuffIt classic, `.Z`, ARC methods 8/9 and DiskDoubler method 1.

**The pattern is now this codebase's recurring hot shape** - a per-byte loop
with a bound test that could be hoisted. Section 2a is 77 % of one format,
this is 21 % of two more. Worth looking for deliberately rather than waiting
to trip over the third.

---

## 2f. The canonical Huffman decoder is bit-at-a-time, and four formats share it

**Claim (measured 2026-08-23).** `unc_canon_decode` in `unc_huffman.c` is the
single largest cost in three of the four formats that use it:

| fixture | format | `unc_canon_decode` | + bit reading | total |
|---|---|---|---|---|
| `derived-SyntheticReferences2.0.sea` | Now Compress | **57.20 %** | 13.67 % | **70.87 %** |
| `derived-Terrainman_2.0__.sea` | DiskDoubler | **49.68 %** | 9.81 % | **59.49 %** |
| `derived-XferIt_1.5b4.sea` | Compact Pro | **34.98 %** | 8.66 % | **43.64 %** |

`fmt_cpt.c`, `fmt_dd.c`, `fmt_now.c` and `fmt_sit.c` all call it, so this is
one function under four format families.

**Why it costs that much:** it walks the code one bit at a time -

    for (l = 1; l <= c->maxlen; l++) {
        int bit = unc_bitin_bit(bi);
        ...
        if (code - c->first[l] < c->count[l]) return c->sym[...];
    }

so a symbol of average length 8 costs eight calls into the bit reader plus
eight compares, and `UNC_CANON_MAX_BITS` is 31 (method-13 tables reach 18).

**The standard remedy, and zlib's:** a peek-and-lookup table. Build
`fast[1 << K]` from the code lengths, mapping the next K bits to
(symbol, length) for every code no longer than K, and fall back to the
existing loop for the rest. K = 8 costs **512 B** per table (`uint16_t`
entries) against a `UncCanon` that is already ~1.6 KB, and turns the common
case into one peek, one index and one consume.

**What it needs:** a peek on `UncBitIn` (fill to K bits, mask, do not
consume), which does not exist yet - `unc_bitin_bit` and `unc_bitin_bits`
both consume.

**Why the risk is acceptable here in a way it is not elsewhere:** the
transformation is byte-exact by construction - the same code-to-symbol
mapping, reached differently - and it sits under 919 fixtures that grade
exactly that. This is the rare change in this file that `ci.sh` can prove.

**Measure the memory before committing to K:** Compact Pro holds three tables
at once, so K = 8 is +1.5 KB there. Against a 400 KB budget that is nothing;
put the number in FORMATS.md rather than assuming it.

**The same shape, unshared:** BinHex's own reader is bit-at-a-time too -
`bh_get_bits` 36.97 % plus `bh_decode_byte` 25.68 % of `macburger-helper.hqx`.
Worth looking at after the shared one, since it benefits one format rather
than four.

---

## 3. The Arsenic symbol loop divides twice, signed, where once unsigned would do

**Claim (measured — disassembly of `sit_arsenic.o` built with the Mac
target's flags).** `ars_next_symbol`, with `ars_dec_advance` inlined into it,
calls `__divsi3` twice and `__mulsi3` twice per decoded symbol. Three separate
things are wrong with that, and none of them needs assembly:

- **The source divides three times, and the compiler merged two of them.** The
  guard in `ars_next_symbol` and the `frequency` line below it share a
  subexpression and are CSE'd; `renorm` inside `ars_dec_advance` is not,
  because gcc cannot prove `d` and `m` do not alias across the symbol-search
  loop, so it reloads `d->range` and `m->totalfrequency` and divides again.
  **Hoisting into locals is what defeats that**, and it is worth one of two
  divides — not two of three, as an earlier draft of this section said.
- **The divides are signed for no reason.** `range`, `code` and
  `totalfrequency` are `int32_t` and all are provably non-negative
  (`range <= 2^25`, `code <= range`, `totalfrequency >= 2`). `__divsi3` is a
  wrapper that handles sign and then calls `__udivsi3_internal`; casting the
  operands to `uint32_t` at the division site deletes that layer.
- **Both multiplies are 32x32 where 32x16 would do.** `renorm * symlow` and
  `symsize * renorm` each have one operand bounded by `totalfrequency <= 1032`
  (every model is initialised with `frequencylimit` 256 or 1024).
  `__mulsi3` is three `MULU.W`; a 32x16 multiply is two.

The transformation is arithmetically identical either way, so byte-exactness
holds by construction.

**What can and cannot see it:** the win does not appear on Linux — an x86 has
a hardware 32-bit divide and a 68000 does not — so `ci.sh` cannot grade it.
Measure it on the Mac, or by counting calls.

**Why assembly is not the answer here (measured).** libgcc's `__udivsi3`
(`lb1sf68.S`) already fast-paths a 16-bit divisor with two `DIVU.W`, and
`totalfrequency <= 1032` always takes that path. Hand-written division would
save the `jsr`, the `d2` save/restore and the sign wrapper — call overhead,
perhaps 15 % of the divide cost, against 50 % for the free hoist. The only
candidate worth three lines of inline asm is the 32x16 multiply above, and
only if the profile of section 1 says the multiplies matter. Against that,
an m68k assembly path is graded by the emulator harness (62 fixtures, one
boot each) while the 919-fixture suite grades its C fallback, which is this
repository's own "a test that passes may not be testing anything" trap.

Same reasoning disposes of the scan loop: what an asm
`cmp.b (a0)+,d0 / bne.s` loop would buy over
`do { i++; } while (i < n && block[i] != c)` is the bounds test, and section
2a removes that in portable C - against a line section 1 now measures at
77 % of the run. That is the strongest argument in this file for doing the
C version and re-profiling before anyone reaches for a `.s` file.

**Assembly for SIZE is not worth considering at all.** `-Os` C is already
dense and section 7.1's 94,160 B is 25 format decoders, zlib and tables, not
one hot loop; rewriting the whole of `sit_arsenic.c` (3,856 B measured) might
recover 1-1.5 KB against the ~200 KB in section 2.

---

## 4. `SetEOF` the output fork at create time

The streaming `sink_begin` creates the file and pre-allocates nothing, so
every 8 KB `FSWrite` extends the fork and HFS rewrites the extent map. One
`SetEOF` when `info->data_size` is known allocates it once.

It is also the cheapest part of section 5: `SetEOF` returns `dskFulErr`
**before the entry is decoded**, which turns "fail every remaining entry
mid-write, twenty minutes in" into "refuse this entry now" for every format
that reports a size.

---

## 5. Destination disk space: there is no pre-flight check (measured)

**Claim:** the application never asks the destination volume how much room it
has. `PBHGetVInfo` appears in `mac/unclassic_mac.c` only for volume
enumeration.

**What happens when the disk fills**, read out of the write path:

1. `FSWrite` fails mid-entry inside `sink_write`, which sets `wrErr` and
   returns −1.
2. The entry fails; `sink_end` deletes the partial file, so nothing incomplete
   is left behind.
3. The error is counted and **extraction continues** — every remaining entry
   then fails the same way, one error each.
4. The `OSErr` is discarded at the `!= noErr` test, so `dskFulErr` is
   indistinguishable from a genuine I/O error. Nothing can tell the user the
   disk is full.

**Consequence:** the failure is safe but illegible. A user who fills a volume
half way through a 200-entry archive sees 100 identical unexplained entry
errors.

**Proposed, after the `SetEOF` of section 4:**

- **Keep the `OSErr`.** Carry it in `MacSink` so the cause survives to the
  result grid.
- **Treat `dskFulErr` as terminal for the run.** Stop and report it once
  rather than failing every remaining entry against a volume that cannot
  accept them.
- **Pre-flight where the format allows it.** `ioVFrBlk × ioVAlBlkSiz` from
  `PBHGetVInfo` against a listing pass (`opt.list_only` exists) gives an exact
  answer for formats that carry sizes in a listable directory, and
  `UNC_SIZE_UNKNOWN` is a real case in the sink, so the honest behaviour is
  *warn when the total is known, fall back to the terminal-error path when it
  is not*. Any check must also count the resource fork and round each fork up
  to the volume's allocation block.

**What this cannot see:** a volume that fills from another process during a
long extraction. The mid-write path stays the backstop whatever the pre-flight
says.

---

## 6. The small items in the same loop

- **`unc_bitin_bit` is an out-of-line call in the renormalisation loop.**
  `ars_dec_advance` calls it once per renormalisation bit, several times per
  symbol. `unc_bufin_next` in `unc_internal.h` already shows the idiom — a
  `static inline` fast path over the buffer with a slow-path fallback — and
  the bit reader does not use it.
- **`ars_index_next` binary-searches 256 entries per output byte.** Eight
  compares to find which byte value owns sorted index `k`, before the sample
  scan even starts. A coarse `k >> shift` -> candidate-value table of 1-2 KB
  replaces them with one lookup and a short walk. **Measured at 1.75 %**
  (section 1) - a small item, and not to be confused with section 2a, which
  is the scan itself.
- **Per-file optimisation level.** Everything builds at `-Os`.
  `sit_arsenic.c` is 3,856 bytes of code (measured); building that one file at
  `-O2` is a one-line CMake change and costs perhaps 2 KB.

- **Try `-flto`.** It would inline exactly the cross-translation-unit calls
  named in 6b - the emit functions, `unc_bitin_bit`, `unc_crc32` - and
  typically takes a few percent off `-Os` code size as well. The unknown is
  whether Retro68's `Elf2Mac` link step survives it; that is a ten-minute
  experiment with a clear pass/fail, and nobody here has run it.
- **Measure before touching:** `ars_next_symbol` linearly scans up to
  `numsymbols - 1` entries accumulating frequencies, and `mtfmodel[6]` has
  128 symbols. High MTF ranks are rare in BWT output, so the expected
  iteration count is probably low. Section 1's profile answers this; reasoning
  does not.

**Checked and nothing there: the launch path.** Between double-click and the
file dialog the application does six Toolbox inits (`InitGraf` through
`InitDialogs`), `InitCursor`, `FlushEvents`, one trap-availability test, and
goes straight into `SFGetFile`. No resource preloading, no volume scan, no
window built before the dialog. **Every cost at launch is the Segment
Loader's 94 KB read, its relocation and the 28 KB A5 world** - which is
section 7.4 and nothing else. Recorded as a null result so the next reader
does not look again.

**Checked and not proposed:** the progress path. `prog_tick` already throttles
to ~10 Hz off `TickCount` and returns before any drawing, so
`ARS_PROGRESS_STEP` at 256 bytes costs a trap and a compare — it is already
right. Two more of the same kind: opening an archive deliberately calls
`unc_segment_describe` rather than a full `unc_sniff`, to avoid walking a
Compact Pro index twice on a 7 MHz machine (the comment in
`mac/unclassic_mac.c` says so); and the compile line is
`-O3 -DNDEBUG -mcpu=68000 -Os ...`, where the `-O3` comes from
`CMAKE_BUILD_TYPE=Release` and the `-Os` from the target options - **last
wins, so the application is built `-Os`**, whatever `flags.make` looks like at
a glance. All recorded so they are not re-derived as opportunities, along with
narrowing hot-path arithmetic to 16 bits, which would help a 68000 and which
CLAUDE.md forbids deliberately.

---

## 6a. Runtime division in per-byte paths, in three other formats

**Claim (measured — `nm` over the 68k objects for the libgcc div/mod
helpers).** Three formats call a division helper once per byte, or worse. None
of them touches the StuffIt 5 case this file opened with; all three are a few
lines, and all three are provably identical after the change.

- **`fmt_spacesaver.c`** indexes its window as
  `s->win[(s->wpos + s->wsize - dist) % s->wsize]`, **once per copied byte**.
  `wsize = 1u << wbits`, so the divisor is always a power of two - but it is a
  runtime value, so gcc emits `__umodsi3` rather than a mask. Compute
  `wmask = wsize - 1` at init and use it. The same `%` in the preset-dictionary
  load runs once per fork and matters much less.
- **`fmt_dd.c`, methods 2 and 5** (the 392 KB-peak ones) compute
  `ctx = ntrees == 256 ? byte : byte % ntrees` **once per output byte**. The
  common case is already special-cased; the other branch still calls
  `__modsi3` per byte. A 256-byte `uint8_t` table built once at init removes
  the division for every `ntrees`.
- **`fmt_binhex.c`** scans for its banner with `% 40`, including
  `(w + i) % 40` inside a 40-iteration inner loop - up to 40 helper calls per
  byte scanned before the `:` is found. The divisor is constant, but a 68000
  has no 32-bit multiply, so gcc calls the helper instead of using a magic
  number. `if (x >= 40) x -= 40` is exact, since `w < 40` and `i < 40`.

**Checked and not proposed:** `unc_lzw.c` also pulls in `__udivsi3` and
`__umodsi3`, from `insize / 9` and `insize % 9`. Those run once per stream.

## 6b. Shared code: already done where it is big

**Measured, by symbol reference across `src/`:** `unc_lzw_*` is shared by
`fmt_arc`, `fmt_dd`, `fmt_exo` and `fmt_sit`; `unc_huff_read_tree` /
`unc_huff_decode` by `fmt_dd`, `fmt_sit` and `fmt_packit`; `unc_cpt_lzh_fork`
by `fmt_cpt` and `fmt_dd`; `UncBitIn` by nine files. Every large algorithm
already has one home.

**RLE90 exists four times and should stay that way.** `sit_rle90`, `dd_rle`,
ARC's `arc_byte` and BinHex's `bh_next` are ~30 lines each - ~800 B in total,
perhaps 500 B recoverable. They differ in bounds model (output length vs input
length), in whether `count == 1` is `UNC_ERR_CORRUPT` or tolerated, in a 0x5a
XOR, and in push vs pull. Each is transcribed from its own reference with its
own `/* Source: */`, and `fmt_dd.c`'s copy documents an escape byte that is a
labelled HYPOTHESIS for that format alone. Collapsing four separately-sourced
transcriptions into one function with four flags usually costs more code than
it saves, and it puts the bit-for-bit quirk preservation at risk for 500 bytes.

**The one dedup worth doing is the output side, and it is also a speed-up.**
The same buffered-fork-output pair appears five times - `ss_flush`/`ss_emit`,
`sd_flush`/`sd_emit`, `dd_out_flush`/`dd_out_byte`,
`unc_cpt_rle_flush`/`cpt_rle_emit`, `sit_flush`/`sit_put` - all buffer, CRC,
sink write, progress tick. An `UncBufOut` mirroring the existing `UncBufIn` is
mechanical and worth perhaps 600-700 B.

**And `UncBufIn` is the point: the input side has an inline fast path and the
output side does not.** `unc_bufin_next` is a `static inline` over the buffer
with a slow-path fallback; the emit functions are ordinary calls. Measured
from relocations in the 68k objects: `sit_put` is called from 10 sites,
`dd_out_byte` from 12, both emitted as real functions, so **every output byte
costs a `bsr`, a prologue, the bounds test, the store and an `rts`** - roughly
50 cycles of overhead against maybe 10 of work. Give the shared `UncBufOut`
the same inline fast path and the dedup and the speed-up are one piece of
work.

**Sized honestly, and then measured.** ~50 cycles on 1 MB of output is ~7 s at
8 MHz, noise against StuffIt 5's 1,898 s - and section 1 measured
`sit_arsenic_put` at **0.54 %**, which is that prediction confirmed. But the
same profiler puts **`dd_out_byte` at 15.98 %** of a DiskDoubler run and
`cpt_rle_push` at 20.17 % of a Compact Pro one. So the prediction was right in
both directions: noise for the slow format, a sixth of the run for the fast
ones. (`ss_emit` is already inlined by gcc inside `fmt_spacesaver.o` and the
others are not, so today the behaviour varies by file, which is its own
argument for making it deliberate.)

---

## 7. Heap: what the application holds that a session does not need

### 7.1 Where the memory goes (measured)

Compiled with the Mac target's own flags (`-mcpu=68000 -Os
-ffunction-sections`, Retro68 gcc), section bytes summed per object:

| | code | rodata |
|---|---|---|
| engine (`src/*.c`) | 71,634 | 18,281 |
| zlib | 12,268 | 9,489 |
| Mac shell | 10,258 | 607 |
| **total** | **94,160** | **28,377** |

Two consequences, both structural:

- **Code is resident because the application is one segment.** The link line
  produces a single `unclassic.code.bin`; the Segment Loader reads all of it
  at launch and Retro68 relocates all of it before `main`.
- **rodata is resident and cannot be segmented.** `Elf2Mac/LdScript.cc` emits
  `*(.rodata*)` inside the `.data` output section — the A5 global world,
  allocated once at launch, never purgeable.

For scale: adding LZH/LHA extraction (~550 lines, OPEN_ITEMS.md) would add
about **3–4 KB of code**, derived from this repository's measured 3.7–7.8
bytes-per-line range (median 5.8; the Huffman/LZ decoders cluster at 5.5–6.5).

### 7.2 `kMemReserve` is 80 KB and nothing records why

`mac/unclassic_mac.c` keeps `kMemReserve` = 80 KB of heap back from the
engine's budget. Grepping `DECISIONS.md`, `BLOCKERS.md` and `OPEN_ITEMS.md`
finds no entry that chose that value (measured: no match). It is **larger than
the whole segmentation prize in 7.4**, and it is exactly the shape CLAUDE.md
names as worth re-testing: a constant nobody has questioned.

`UNC_AT_BUDGET` already reports whether a refusal came from the budget or from
`NewPtr`, with `MaxBlock` and `FreeMem` at the moment of refusal, so trying 48
or 64 KB is one build and one boot. It is real headroom for the Toolbox and
File Manager during output writes, so a reduction needs the full 1 MB sample
rather than one fixture.

### 7.3 What recovered heap actually buys (derived, corrected 2026-08-23)

There are **two** transitions and they behave differently. An earlier draft of
this file conflated them and concluded the recovered heap was worthless; it is
not.

**Transition one — onto the full transform vector — is out of reach:**

- The 1 MB budget is **678,392 B** — `FreeMem` less `kMemReserve`.
- `peak = ~35 KB parser + capacity + 4 × fill`, capacity from
  `ars_block_reserve`.
- `derived-Troi-ClipSave-Plug-in1.1.sit` (fill 124,637, capacity 128 KB, peak
  666,004) already fits, with ~12 KB to spare.
- Any fill above 131,072 forces capacity to 256 KB, so peak ≥ 35,840 +
  262,144 + 524,292 ≈ **822 KB**, about **144 KB** above the budget.

So no realistic amount of recovered code space flips an entry onto the fast
path: the capacity rung, not the budget, sets that cliff.

**Transition two — the density of the sampled index — is continuous, and it is
where every recovered kilobyte goes.** `ars_index_build` halves `target` until
the allocator accepts; each halving halves the index and doubles the scan
distance. Section 2 is the cheapest way to feed it, 7.2 and 7.4 the dearest.

### 7.4 Segment the CODE resource — ~61 KB, unverified

Retro68 supports it: `-Wl,--mac-segments -Wl,<file>.segmap`, with the segmap
assigning object-file patterns to segments. `libretro/MultiSegApp.c` patches
`_LoadSeg` to pull a segment in on the first jump-table call into it, and its
`PatchedUnloadSeg` ends in `HUnlock` + `HPurge`, so an explicit `UnloadSeg`
genuinely returns the memory.

A session that opens one `.sit` never executes **~61 KB** of code (measured,
summed from the objects above): zlib 12,268, `fmt_dd` 9,984, `fmt_superdisk`
6,424, `fmt_exo` 5,446, `fmt_now` 4,338, `fmt_cpt` 4,210, `fmt_arc` 3,922,
`fmt_uu` 2,664, `fmt_spacesaver` 2,478, `fmt_binhex` 2,122, `fmt_packit`
1,780, plus the wrappers and joiners.

**Startup gets cheaper, not dearer.** Each segment carries its own `RELA`
resource and is relocated on first use, the handle purged afterwards, so
launch loads and relocates segment 1 alone instead of 94 KB. The A5 world is
built at launch either way. *No launch-time baseline is measured anywhere in
this repository*, so this is a claim about work done, not a timing.

**The catch is structural.** Every format's `probe` lives in that format's
`.c` file and `unc_sniff` calls ~25 of them, so one-segment-per-format means
opening any archive touches every segment. Memory survives that (they purge)
but a floppy-only machine pays a seek per format per open. The clean version
splits the probes into one translation unit that stays in the core segment —
mechanical, but it touches ~20 files.

### 7.5 Static tables in the A5 world — ~16 KB of 28 KB, unverified

Largest items (measured): `ss_dict.h` 9,694 B, zlib's `crc32.o` table 6,272 B,
`fmt_sit` tables 4,539 B, `inflate.o` 2,675 B, `unc_util` 2,048 B.

**Measured 2026-08-23, and this one is done bar the doing.** zlib's crc32.c
compiles its "braided" tables whenever `W` is defined, and `W` defaults to 4
on anything that is not x86-64 or aarch64 - so the 68000 build carries them.
Compiling that one file with `-DZ_TESTW=0` takes it from **7,570 B to
1,864 B** (m68k, the Mac target's flags): **5,120 B of it rodata, which is
resident A5 world**. The cost is nothing at all, because the engine uses
`inflateInit2(&zs, -15)` - raw inflate - so **zlib never computes a CRC**;
the engine's own `unc_crc32` does. Verified: `PCCTS.tar.gz`, `4acalc.zip`,
`a2ps.V4.3.tar.Z` and `derived-MUSFMT10.ZIP` produce byte-identical `t --stats`
output with the flag set. One compile flag, 5 KB of permanently-resident
memory, no behaviour change - the cheapest item in this file. Moving the SpaceSaver dictionary or the StuffIt tables into purgeable
resources would cost the engine its dependency-free property — it would need a
host table-fetch callback — so that is a design decision, not an optimisation.

`unc_inflate.c` is only a bridge to zlib, which exists solely for deflate and
costs 12,268 B of code plus 9,489 B of rodata. A transcribed compact inflate
would recover most of that; zlib is what 919 fixtures currently pass against,
so it is a memory win paid for in risk, and it belongs last of everything in
this file.

---

## The tradeoff is Arsenic's alone, and that is a fact about the corpus

**Claim (measured, from FORMATS.md's peak column):** StuffIt 5 is the only
format with a memory-for-time path because it is the only format that has ever
exceeded the budget. Every other row peaks between 4 KB and 405 KB and its
*400 KB budget* column reads **full**. Two formats scale with their input —
`.Z`'s LZW table and DDn's window, sized per entry — and cap at 219 KB and
~100 KB.

**Consequence:** there is nothing for a generic mechanism to adapt today, and
a generic mechanism could not be graded against the current corpus. It becomes
real the day a format with a megabyte-class window or dictionary is added, and
the Arsenic answer will not simply port to it — `DECISIONS.md` (2026-08-03,
the LZW table) is the recorded case of that same fix failing on the second
problem. LZH/LHA is not that format: 64 KB of window worst case.

**What to do about it:** decide per format, when the format arrives, and size
the decision from the peak matrix rather than from a rule. If a future decoder
does need one, the shape to copy is the sampled occurrence index
(`DECISIONS.md`, 2026-08-07), not the allocation strategy.

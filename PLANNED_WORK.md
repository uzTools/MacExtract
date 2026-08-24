# PLANNED_WORK.md — proposed, none of it done, in the order to do it

Everything in this file is a **proposal**. Nothing here has been implemented
and nothing here is a status claim: status lives in `PROGRESS.md`,
`OPEN_ITEMS.md` and `BLOCKERS.md`, and none of them changes because this file
exists. When an item lands, move the figure to `FORMATS.md`, the reasoning to
`DECISIONS.md`, and **delete the item from here** — a plan file that keeps
completed rows stops being readable as a list of what is left.

Opened 2026-08-23 from a session that measured the application's memory
layout. Worked through on 2026-08-24; what that pass did is in `PROGRESS.md`
(M29), what it measured is in `FORMATS.md`, why is in `DECISIONS.md`
(2026-08-24), and the two proposals it **disproved** — shrinking the Arsenic
block, and segmenting the CODE resource — are in `BLOCKERS.md` under
*Withdrawn claims*, with what each would have cost.

Every claim below is labelled **measured** (run in this environment),
**derived** (arithmetic over a model this repository documents) or
**unverified** (neither). A derived one is worth an instrumented run before
it is worth an afternoon: that is what turned section 2 from 200 KB into
29 KB and deleted it.

---

## What is left, and in what order

| # | step | costs | buys |
|---|---|---|---|
| 1 | Hoist and unsign the Arsenic divides, narrow its multiplies | one function | `ars_next_symbol` is **13.1 %** of the slowest fixture's remaining instructions, and a 68000 has no divide instruction at all |
| 2 | `SetEOF` the output fork at create time | three lines | one extent allocation per fork instead of per 8 KB, and `dskFulErr` *before* the entry decodes |
| 3 | The rest of the disk-full handling | small | a full disk becomes legible instead of 100 identical errors |
| 4 | Size five windows and tables from the entry, not the format's ceiling | small each | ~128 KB (Now Compress), up to 64 KB (SuperDisk and SpaceSaver), ~30 KB (zip/gzip), ~28 KB (ARC crunch) — **memory, not time**, so it is below the two above |
| 5 | The small loop items | small each | the index binary search **1.75 %**, per-file `-O2` |
| 6 | `kMemReserve`, then the budget sweep | a build | 32-80 KB into the extraction budget |
| 7 | A transcribed inflate to replace zlib | a rewrite | ~12 KB code + 9 KB rodata, paid for in risk. Last of everything here |

---

## 1. The Arsenic symbol loop divides twice, signed, where once unsigned would do

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
only if the profile says the multiplies matter. Against that, an m68k assembly
path is graded by the emulator harness (67 fixtures, one boot each) while the
927-fixture suite grades its C fallback, which is this repository's own "a test
that passes may not be testing anything" trap.

**Assembly for SIZE is not worth considering at all.** `-Os` C is already
dense and the application's 116 KB of code is 25 format decoders, zlib and
tables, not one hot loop; rewriting the whole of `sit_arsenic.c` (4,032 B
measured) might recover 1-1.5 KB.

---

## 2. `SetEOF` the output fork at create time

The streaming `sink_begin` creates the file and pre-allocates nothing, so
every 8 KB `FSWrite` extends the fork and HFS rewrites the extent map. One
`SetEOF` when `info->data_size` is known allocates it once.

It is also the cheapest part of section 3: `SetEOF` returns `dskFulErr`
**before the entry is decoded**, which turns "fail every remaining entry
mid-write, twenty minutes in" into "refuse this entry now" for every format
that reports a size.

---

## 3. Destination disk space: there is no pre-flight check (measured)

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

**Proposed, after the `SetEOF` of section 2:**

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

## 4. Five windows allocated at the format's ceiling, not the entry's size

**This is memory, not time**, which is why it sits below the two items above:
every one of these formats already fits the 1 MB floor target with room to
spare (`FORMATS.md`'s peak column), so what it buys is headroom rather than
seconds. It is listed because the class is real and completely enumerated.

**How it was found, because the method is repeatable and needs no insight:**
CLAUDE.md names the smell — *a constant in the peak-RAM matrix is usually a
declared ceiling nobody questioned*, because a data-driven allocation varies
with its input. Run down FORMATS.md's peak column and every row that is a
constant where a range belongs is a candidate.

**The argument that covers all five:** a back-reference window can never reach
further back than the number of bytes produced so far. So when an entry
declares an output smaller than the format's maximum window, the maximum is a
ceiling and not a requirement — and each of these has the entry's size in hand
before it allocates. This project has already applied exactly this reasoning
three times: to the `.Z` LZW table (274,432 B flat, now sized from the input),
to the Arsenic block (`DECISIONS.md` 2026-08-03) and to LZH's window, which
halves down to `outlen` in `fmt_lzh.c`.

- **`src/unc_inflate.c`: `inflateInit2(&zs, -15)`** allocates a 32 KB window
  for every deflate stream whatever its size. Zip's local header carries the
  uncompressed size and gzip's trailer carries ISIZE, so
  `windowBits = max(9, ceil(log2(N)))` is provably sufficient for
  N < 32768. **Check the gzip case first:** ISIZE is in the TRAILER, so a
  stream being read forward does not have it, and a nested `.gz` may not be
  seekable. **Check against the robustness variants:** zlib rejects a distance
  beyond the window with `Z_DATA_ERROR`, but such a distance is invalid
  anyway and already rejected, so the KIND of failure should not change.
- **`src/fmt_now.c`: `unc_alloc(c->al, NOW_INBLOCK + NOW_OUTBLOCK +
  NOW_HISTORY)`** is 131,072 B from three compile-time constants, allocated
  **once per archive, before a single entry is read**. Three 2 KB files cost
  128 KB. Awkward to fix because the buffer is per-archive: size it once from
  the largest entry in the table, not per entry — per-entry reallocation is
  how the Arsenic fragmentation trail gets re-created (`BLOCKERS.md`).
- **`src/fmt_superdisk.c`: `sd_need(c, &s->win, SD_WINDOW + SD_BLOCKMAX)`**
  takes 64 KB unconditionally for SlowFastB, where `min(ulen, SD_WINDOW)` is
  provably enough.
- **`src/fmt_arc.c`: `ARC_CRUNCH_SIZE * 6u + ARC_STACK_SIZE`** is 28,672 B
  flat for methods 5, 6 and 7, whatever the entry's size — ARC's 32 KB top
  end. Crunch **is** LZW, so this is the identical defect `unc_lzw.c` already
  had and already fixed, and the bound is computed in that same file:
  `insize / 9 * 8 + insize % 9 * 8 / 9`, the most codes a stream of that
  length can define. The ARC header carries the compressed size. **The fix
  exists in this repository and never reached ARC's private copy of the
  algorithm.**
- **`src/fmt_spacesaver.c`: the window is `s->wsize`**, from the entry's width
  byte, where `min(ulen + preset dictionary, wsize)` would do — the 68 KB
  ceiling FORMATS.md notes against a 36 KB measured peak. The preset
  dictionary must still fit, which is why the bound is not simply `ulen`.

**Checked and legitimately constant, so that nobody re-checks them:** Compact
Pro's `CPT_WINDOW` is 8192 because macutils' `CIRCSIZE` is and the format
mandates it (a genuinely constant 19 KB peak); `CPT_DD_WINDOW`,
`DD_STAC_WINDOW` and `DD_AD_BLOCK` are likewise format-mandated;
`ARC_SQ_MAXNODES` is 1,028 B and the stream's own `numnodes` is validated
against it; the 4 KB `iocap`/`ocap` pairs throughout are the streaming
buffers, and the 8 KB floors in the peak column are two of them.

**Every `unc_alloc` site in `src/` is classified**, including the four files
added after this list was first written — `fmt_lzh.c` (which already sizes
its window from `outlen`), `unc_crypt.c`, `fmt_btoa.c` and `unc_lzah.c`, none
of which allocates a window at all.

---

## 5. The small items in the same loop

- **`ars_index_next` binary-searches 256 entries per output byte.** Eight
  compares to find which byte value owns sorted index `k`, before the sample
  scan even starts. A coarse `k >> shift` -> candidate-value table of 1-2 KB
  replaces them with one lookup and a short walk. **Measured at 1.75 %** — a
  small item, and not to be confused with the sentinel scan, which was 77 %
  and is done.
- **Per-file optimisation level.** Everything builds at `-Os`.
  `sit_arsenic.c` is 4,032 bytes of code (measured); building that one file at
  `-O2` is a one-line CMake change and costs perhaps 2 KB.
- **Measure before touching:** `ars_next_symbol` linearly scans up to
  `numsymbols - 1` entries accumulating frequencies, and `mtfmodel[6]` has
  128 symbols. High MTF ranks are rare in BWT output, so the expected
  iteration count is probably low.

**Checked and nothing there: the launch path.** Between double-click and the
file dialog the application does six Toolbox inits (`InitGraf` through
`InitDialogs`), `InitCursor`, `FlushEvents`, one trap-availability test, and
goes straight into `SFGetFile`. No resource preloading, no volume scan, no
window built before the dialog. And the Segment Loader's own cost is now
measured and is ≈ 0.16 s of an 8.9 s boot (`FORMATS.md`, *Launch*), so there
is nothing here at all. Recorded as a null result so the next reader does not
look again.

**Checked and not proposed:** the progress path. `prog_tick` already throttles
to ~10 Hz off `TickCount` and returns before any drawing, so
`ARS_PROGRESS_STEP` at 256 bytes costs a trap and a compare — it is already
right. Two more of the same kind: opening an archive deliberately calls
`unc_segment_describe` rather than a full `unc_sniff`, to avoid walking a
Compact Pro index twice on a 7 MHz machine (the comment in
`mac/unclassic_mac.c` says so); and the compile line is
`-O3 -DNDEBUG -mcpu=68000 -Os ...`, where the `-O3` comes from
`CMAKE_BUILD_TYPE=Release` and the `-Os` from the target options — **last
wins, so the application is built `-Os`**, whatever `flags.make` looks like at
a glance. All recorded so they are not re-derived as opportunities, along with
narrowing hot-path arithmetic to 16 bits, which would help a 68000 and which
CLAUDE.md forbids deliberately.

---

## 6. `kMemReserve` is 80 KB and nothing records why

`mac/unclassic_mac.c` keeps `kMemReserve` = 80 KB of heap back from the
engine's budget. Grepping `DECISIONS.md`, `BLOCKERS.md` and `OPEN_ITEMS.md`
finds no entry that chose that value (measured: no match). It is exactly the
shape CLAUDE.md names as worth re-testing: a constant nobody has questioned.

`UNC_AT_BUDGET` already reports whether a refusal came from the budget or from
`NewPtr`, with `MaxBlock` and `FreeMem` at the moment of refusal, so trying 48
or 64 KB is one build and one boot. It is real headroom for the Toolbox and
File Manager during output writes, so a reduction needs the full 1 MB sample
rather than one fixture.

**What recovered heap buys is continuous, not a cliff.** `ars_index_build`
halves `target` until the allocator accepts; each halving halves the index and
doubles the scan distance. It does NOT flip an entry onto the fast transform
vector: that needs `35 KB parser + capacity + 4 x fill`, and any fill above
131,072 puts the peak ~144 KB above the whole 1 MB budget. The capacity rung,
not the budget, sets that cliff.

---

## 7. zlib, and what it costs to keep

`unc_inflate.c` is only a bridge to zlib, which exists solely for deflate and
costs 7,824 B of code plus 2,675 B of rodata for `inflate.o` alone, and 12 KB
plus 3 KB across the four objects. A transcribed compact inflate would recover
most of that; zlib is what 927 fixtures currently pass against, so it is a
size win paid for in risk, and it belongs last of everything in this file.

Moving the SpaceSaver dictionary (9,694 B) or the StuffIt tables (4,475 B)
into purgeable resources would cost the engine its dependency-free property —
it would need a host table-fetch callback — so that is a design decision, not
an optimisation. And the launch measurement says what it would buy: those are
data, not pointers, so they carry no relocations and cost the Segment Loader
a read and nothing else.

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
problem. LZH is not that format: 64 KB of window worst case, and it halves.

**What to do about it:** decide per format, when the format arrives, and size
the decision from the peak matrix rather than from a rule. If a future decoder
does need one, the shape to copy is the sampled occurrence index
(`DECISIONS.md`, 2026-08-07), not the allocation strategy.

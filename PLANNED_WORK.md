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
| 1 | Size five windows and tables from the entry, not the format's ceiling | small each | ~128 KB (Now Compress), up to 64 KB (SuperDisk and SpaceSaver), ~30 KB (zip/gzip), ~28 KB (ARC crunch) — **memory, not time** |
| 2 | A transcribed inflate to replace zlib | a rewrite | ~12 KB code + 9 KB rodata, paid for in risk. Last of everything here |

**Three more are closed rather than done**, and each is in `BLOCKERS.md`
with what it cost: the **index binary search** and **per-file `-O2`** (the
first landed and is worth 7.2 % on a real Mac Plus; the second measured
1,536 B bigger and no faster, and is not in the tree), the **`SetEOF`**
and **disk-full** pair (SetEOF landed; the disk-full proposal's premise —
"every remaining entry then fails the same way" — turned out to be false
for thirteen of fourteen formats, and the real work was six lines in
`fmt_arc.c`), and:

**`kMemReserve` is closed, not done.** It was here as "32-80 KB into the
extraction budget"; measuring the budget instead of assuming it showed there
is nothing to buy. The next `target` rung for the slowest fixture needs a
650,222 B peak against a 597,036 B budget, so the reserve would have to fall
from 80 KB to under 28 KB to reach it — and that is headroom the Toolbox and
File Manager use during output writes, on the one machine nothing here can
test on real hardware. FORMATS.md, *Budget*; the 91 KB error that measurement
found is in BLOCKERS.md.

---

## 1. Five windows allocated at the format's ceiling, not the entry's size

**This is memory, not time**, and every one of these formats already fits
the 1 MB floor target with room to spare (`FORMATS.md`'s peak column), so
what it buys is headroom rather than seconds. It is listed because the class
is real and completely enumerated — and it got more interesting on
2026-08-24, when the two Huffman lookup tables put 3–6 KB back onto Compact
Pro, DiskDoubler and Now Compress. Now Compress in particular allocates
131,072 B from three compile-time constants *before a single entry is read*,
which is the largest single unearned allocation left in the engine.

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

## 2. zlib, and what it costs to keep

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

## Checked and empty — do not re-propose these

Carried forward from items that have since landed or died, because each is
a place a reader will otherwise look again.

- **The launch path.** Between double-click and the file dialog the
  application does six Toolbox inits (`InitGraf` through `InitDialogs`),
  `InitCursor`, `FlushEvents`, one trap-availability test, and goes straight
  into `SFGetFile`. No resource preloading, no volume scan, no window built
  before the dialog. And the Segment Loader's own cost is measured at
  ≈ 0.16 s of an 8.9 s boot (`FORMATS.md`, *Launch*), so there is nothing
  here at all.
- **The progress path.** `prog_tick` already throttles to ~10 Hz off
  `TickCount` and returns before any drawing, so `ARS_PROGRESS_STEP` at 256
  bytes costs a trap and a compare — it is already right.
- **Opening an archive** deliberately calls `unc_segment_describe` rather
  than a full `unc_sniff`, to avoid walking a Compact Pro index twice on a
  7 MHz machine (the comment in `mac/unclassic_mac.c` says so).
- **The compile line** is `-O3 -DNDEBUG -mcpu=68000 -Os ...`, where the
  `-O3` comes from `CMAKE_BUILD_TYPE=Release` and the `-Os` from the target
  options — **last wins, so the application is built `-Os`**, whatever
  `flags.make` looks like at a glance.
- **Narrowing hot-path arithmetic to 16 bits** would help a 68000 and
  CLAUDE.md forbids it deliberately.
- **`ars_next_symbol`'s linear symbol search** averages **10.4 iterations
  per decoded symbol** (measured), which is what kills replacing its
  division with a multiply per iteration: ten `__mulsi3` calls cost a 68000
  more than one `__udivsi3`. The search itself is 9.9 % of the slowest run
  and has no obviously cheaper shape — a running cumulative array would have
  to be updated on every `ars_model_bump`.

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

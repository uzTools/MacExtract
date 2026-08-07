# FORMATS.md — format support matrix

Status after M0–M9. "Oracle coverage" = fixtures with byte-exact
differential manifests (built from The Unarchiver's `unar`; see
TESTING.md); every one passes, plus 10 corruption variants each in the
robustness suite. "Peak RAM" = allocator high-water mark across the
whole corpus for that format (engine allocations only, via
`unclassic t --stats`).

| Format | Status | Methods | Oracle coverage | Peak RAM | 400 KB budget |
|---|---|---|---|---|---|
| MacBinary I/II/III | extract | — | 225 fixtures | 8 KB | full |
| AppleSingle/Double | extract | — | (unit tests + envelopes) | 8 KB | full |
| BinHex 4 (.hqx) | extract | RLE90 | 179 fixtures | 8 KB | full |
| PackIt (.pit) | extract | store, Huffman; encrypted detected | 4 fixtures (1 real + 3 synthetic PMa4) | 9 KB | full |
| Compact Pro (.cpt) | extract | RLE, LZH+RLE | 106 fixtures | 19 KB | full |
| StuffIt classic (.sit) | extract | 0 store, 1 RLE90*, 2 LZW, 3 Huffman, 5 LZAH, 8 MW, 13 LZSS+Huffman; 6 fixed-Huffman NOT implemented‡; encrypted detected | 211 fixtures | 8–76 KB‖ | full |
| StuffIt 5 (.sit) | extract | 0, 13, 15 Arsenic; encrypted detected | 31 fixtures | 0.15–2.53 MB† | 23 of 31 fixtures extract FULLY; the rest refuse per entry |
| Zip | extract | store, deflate; others & encrypted per-entry errors | 3 fixtures (+2 PKZIP-1.x corpus-only) | 66 KB | full |
| Gzip | extract | deflate | 3 fixtures | 51 KB | full |
| Unix compress (.Z) | extract | LZW ≤16 bit | 4 fixtures | 219 KB§ | full |
| Tar (ustar/v7) | extract | — (links reported unsupported) | 3 fixtures (2 real 1990 v7 tars) + unit tests | 8 KB | full |
| StuffIt X (.sitx) | detect only | — | — | — | — |
| DiskDoubler (DD, DDAR, DDA2) | detect only | — | 4 sniffed | — | — |
| Now Compress | detect only | — | 1 sniffed | — | — |
| LZH/LHA (-lh?-, -lz?-) | detect only | — | — | — | — |
| DiskCopy 4.2 (.image) | detect only | — | synthetic 800K GCR + real 800K image; 0 false positives in 803 fixtures | — | — |

\* **Method 1 does occur** — once, a 470-byte resource fork in
`derived-New_Python.sit` — contrary to what this footnote said until
2026-08-01. The engine extracts that whole archive cleanly, every CRC-16
verified, so method 1 *is* exercised against a real file. What it has no
ORACLE coverage for is the same fixture: `unar` fails on it ("Attempted to
read more data than was available" on `It's A Bit Runny Sir`), so
`make_manifests.py` refuses a manifest and the differential suite never sees
it. Method 1 is therefore pinned by unit tests transcribed from
XADRLE90Handle *plus* one real archive checked against its own checksums —
not by the oracle.

‡ **Method 6, "Fixed Huffman", is present in the corpus and NOT implemented.**
`derived-INITLoader.sit` carries one 34,818-byte method-6 fork; the engine
returns a clean per-entry "recognized but unsupported". The name comes from
`reference/XADMaster/XADStuffItParser.m:284`; XADMaster does not implement it
either (`//case 6: fixed huffman`, line 319), which is why that fixture has no
manifest and why the gap went unnamed here until 2026-08-01. One fixture, one
fork, in a corpus of 344 StuffIt archives.

† **Every real Arsenic block is 512 KB.** The block size is `1 << (v+9)`
with `v` read from the stream, so other sizes are legal, but across the
31-fixture StuffIt 5 corpus **all 484 Arsenic streams — one per compressed
fork — declare 512 KB** (`v` = 10, blockbits 19). Measured directly by
instrumenting the point where `sit_arsenic.c` reads `v`, not inferred.

A note here previously claimed the blocks were "128 KB (14 fixtures,
dominant), 256 KB (9), 512 KB (8)". That was **wrong**, and the way it
went wrong is worth keeping: it was inferred from peak heap via
"peak ≈ 5× block", which does not hold, because only the *block* is
allocated at its declared size —

    peak  =  ~35 KB parser state  +  512 KB block  +  4 × actual block fill

— the inverse-BWT transform vector is sized to how much of the block the
entry actually fills (`transform = numbytes * 4`, in `ars_bwt_prepare`),
which is exactly what lets a small Arsenic entry fit a small budget. A
fixture peaking at 0.64 MB is therefore a 512 KB block holding ~24 KB,
not a 128 KB block; dividing by five turned every small payload into an
imaginary small block. Peak heap can never recover the declared block
size, so the claim was not just false but unmeasurable that way.

Measured peak heap over the corpus (`unclassic t --stats`): **min
0.15 MB / median 0.59 MB / mean 0.92 MB / max 2.53 MB**, the maximum
being the entries that genuinely fill a 512 KB block (35 KB + 512 KB +
2048 KB). Those are the peaks with memory to spare, where the decoder takes
the fast inverse BWT; under a cap it takes a cheaper one and the numbers
below apply instead.

**Under a cap, since 2026-08-07: 23 of the 31 fixtures extract completely
and byte-exact under a 400 KB budget (was 11), and all 31 fit the ~700 KB a
1 MB Mac Plus has free (was 18).** The transform vector is no longer built
at all when it does not fit; a sampled occurrence index answers the same
query for a fraction of the memory and more time (DECISIONS.md 2026-08-07).
**Peak heap under a budget is not the requirement** — the decoder spends
whatever the cap allows, so the honest figure is the minimum at which a
fixture still extracts fully, bisected:

| fixture | needed before | minimum now |
|---|---|---|
| `derived-RWAsm_Folder.sit` | 160,704 | 71,996 |
| `derived-Troi-ClipSave-Plug-in1.1.sit` | 660,200 | 167,455 |
| `derived-a2basic.dmg.sit` | 1,031,463 | 245,897 |
| `derived-Library_ISBN_Barcoder.sit` | 1,682,080 | 393,028 |
| `derived-Domino_v1.4.sit` | 2,657,700 | 565,062 |
| `derived-EasyFind.dmg.sit` | 2,657,700 | 565,062 |

The unlimited-peak figures above improved on 2026-08-03, when the block
stopped being allocated
at its DECLARED size. `blockbits` says 512 KB on every real stream, but the
fill varies enormously — the fixture that peaked at 643 KB was a 512 KB
allocation holding 24 KB — so the block is now grown on demand
(`ars_block_reserve`) and peak is `~35 KB parser + capacity + 4x fill` rather
than `~35 KB + 512 KB + 4x fill`. The previous figures were min 0.63 / median
0.97 / mean 1.23 MB with **every** entry over a 400 KB budget. Nothing about
the format or the decoder changed; only what is allocated to hold it. See
DECISIONS.md.

On a **1 MB Mac Plus** Arsenic is no longer out of reach at all. It got there
in four steps. The first three were about not paying for memory the data does
not use, rather than about the decoder; only the last changed what the decoder
needs:

- **2026-08-02** — the shell stopped reading the whole archive into RAM before
  the engine was given a budget, so each archive got its own size back.
- **2026-08-03** — the Arsenic block stopped being allocated at its declared
  512 KB and is grown to what each block actually holds, which is often a
  small fraction of it.
- **2026-08-06** — the block's first allocation is sized from the entry, so
  doubling no longer leaves a trail of freed steps that nothing can reuse.
- **2026-08-07** — the 4-bytes-per-byte inverse-BWT vector is no longer built
  when it does not fit; a sampled occurrence index answers the same query for
  a fraction of the memory, at the cost of time.

All six extract byte-exact at 4 MB, and since the fourth step all six extract
byte-exact at 1 MB as well.

Until 2026-08-02 the boundary was **the size of the archive** rather
than anything about the archive's contents, because the shell read the
whole thing into RAM before the engine got a budget — so a 202 KB
archive had 202 KB less to work with. That is gone: the archive is read
from the file as the engine asks for it, and every fixture got its own
size back in budget. The effect was large. `derived-Library_ISBN_Barcoder.sit`
went from refusing all 34 entries to extracting 31 of them, and
`derived-RWAsm_Folder.sit` from 36 of 38 to all 38. See the two Mini vMac
sections below for the per-fixture outcomes, and DECISIONS.md for why the
slurp existed and why it does not any more.

§ **The `.Z` peak used to be a flat 274,432 B for every input, and is now
sized from the input.** MEASURED 2026-08-03. `compress(1)` writes
`maxbits=16` by default whatever it compressed, so a 488-byte `.Z` declared a
65,536-entry table it filled a few hundred entries of, and `unc_lzw_init`
allocated the DECLARED ceiling — the same mistake the Arsenic block had. Every
input code defines at most one new symbol and codes are at least 9 bits wide,
so `symbols <= 256 + reserved + insize * 8 / 9` bounds the table however large
`maxbits` claims:

| fixture | in | was | now |
|---|---|---|---|
| `synth-exo-Z.Z` | 488 B | 274,432 B | 15,044 B |
| `synth-exo-tar-Z.tar.Z` | 5,465 B | 274,432 B | 32,740 B |
| `a2ps.V4.3.tar.Z` | 30,255 B | 274,432 B | 120,880 B |
| `popper-1.7.tar.Z` | 59,323 B | 274,432 B | 224,232 B |

StuffIt classic method 2 is bounded the same way from the entry's compressed
size; 50 fixtures improved corpus-wide, none regressed, and the sampled
StuffIt classic peaks are unchanged because none of them is method-2 bound.
On-Mac figures agree with Linux to a constant 32 B of shell overhead. See
DECISIONS.md for why the table is sized once rather than grown.

‖ **Method 13's LZSS window is sized from the entry, not from the format.**
MEASURED 2026-08-06. The window is 64 KB by the format, but no stream can
reach further back than it has produced — an offset is `pos - moff`, and a
well-formed encoder never emits `moff > pos` because those bytes do not exist
yet. So a fork whose whole output is 6 KB can only address 6 KB of window, and
the rest was allocated, zeroed and never read. It is now rounded up to a power
of two at or above the fork's uncompressed size, capped at 64 KB, which keeps
the existing `& (win - 1)` masking computing exactly the same indices.

The assumption was checked directly rather than inferred from output: an
instrumented run over the whole corpus counted **0 back-references past
produced output**. 34 fixtures improved, none regressed; the corpus maximum
is unchanged at 76,944 B because some forks genuinely exceed 64 KB, so the
gain is at the small end — `derived-MacGzip.sit` 76,944 → 13,456 B, and
on-Mac `derived-Export.sit` 76,984 → 19,640 B.

## Envelope auto-unwrap

`unclassic x` unwraps chained envelopes by content sniffing
(never by extension): MacBinary, BinHex, AppleSingle/Double, gzip and
.Z layers that yield exactly one file are recursively extracted and
the intermediate deleted (`-nr` disables; depth ≤ 8). Verified chains:
`.sit.bin`, `.sit.hqx`, `.tar.Z` (tools/run_unwrap.py, in CI).

## Hardening

- Differential: 769 fixtures byte-exact against `unar` manifests
  (both forks + type/creator), `./ci.sh`. That is every committed
  manifest whose format the engine extracts: 774 manifests less the 5
  detect-only DiskDoubler/Now Compress ones the harness skips. (A
  headline figure of 771 stood here for a while; `run_diff.py` prints
  the number it actually ran, and it is 769.)
- Robustness: 10 truncation/bit-flip variants per fixture — no
  crashes, hangs, or sanitizer trips under
  ASan+UBSan+`-fsanitize=alignment` (`-fno-sanitize-recover=all`).
- Fuzz: seeded mutation/splice/garbage fuzzing (tools/fuzz.py);
  4,000 cases clean at M9, 150-case smoke in every CI run.
- 32-bit `-m32` build runs the full suite (68000 discipline: no
  unaligned access, no recursion, 32-bit arithmetic in hot paths).

## Measured on a 7 MHz Mac Plus (Mini vMac 1x, System 6.0.8, 4 MB)

The first absolute timings this project has ever had. `run.py --emu mv-4M-1x`
separates boot from extraction — the application paints its "alive" grid
before touching a disk — so the extract column is the archive alone. Poll
interval 5 s, so that column is quantised to 5 s; it is an upper bound at this
resolution, not a stopwatch.

| Fixture | Format | In | Boot | Extract |
|---|---|---|---|---|
| derived-Export.sit | StuffIt | 1.6 KB | 10 s | 5 s |
| synth-packit-2.pit | PackIt | 3.4 KB | 10 s | 5 s |
| derived-keyAhead.cpt | Compact Pro | 0.9 KB | 10 s | <5 s |
| export-hc.hqx | BinHex | 3.1 KB | 10 s | 5 s |
| stuffit151mstr.bin | MacBinary | 0.5 KB | 10 s | <5 s |
| synth-exo-zip-store.zip | Zip | 8.4 KB | 10 s | 5 s |
| synth-exo-tar.tar | Tar | 20 KB | 10 s | 5 s |
| synth-exo-gz.gz | Gzip | 0.1 KB | 10 s | <5 s |
| macburger-helper.hqx | BinHex | 306 KB | 30 s | **150 s** |

**StuffIt 5 / Arsenic at 1x, added 2026-08-07 — and it is in a class of its
own.** The list above samples StuffIt 5 with a 4,611 B fixture, far too small
to reach the sampled inverse BWT, so the fallback's cost on real hardware was
unmeasured until now. Measured on `derived-a2basic.dmg.sit` (153 KB in,
205 KB out), extract time only, on a purpose-built 1 MB 1x emulator
(`build_mv mv-1M-1x 1M z`; `setup.sh` had no such build):

| Machine | Inverse BWT | Peak heap | Extract |
|---|---|---|---|
| 4 MB Mac Plus | transform table (fast) | 1,031,525 B | **537 s** |
| 1 MB Mac Plus | sampled index | 560,589 B | **927 s** |

**The fallback costs 1.73x, and Arsenic was already the slow one.** Nine
minutes for a 205 KB output is what the *fast* path costs a 7 MHz 68000; the
sampled index makes it fifteen. Set against that, the 1 MB machine previously
could not extract this entry at all. The x86 ratio for the same fixture is
2.5x, so the fallback is relatively *cheaper* on the target than on the host —
most likely because the arithmetic decoder dominates more on a 68000 and the
BWT walk is a smaller share. **Do not quote the x86 ratio as a prediction of
the Mac one.**

`derived-Library_ISBN_Barcoder.sit` — the sample's worst case, 641 KB out —
has **not** been timed at 1x; extrapolation puts it near an hour, which is an
estimate and not a measurement. `a2basic` is the only Arsenic 1x figure this
project has.

**8/8, and the shape is the useful part: for small archives the BOOT dominates
and extraction is seconds.** A stripped System 6.0.8 reaches the application in
about 10 s; everything in this table then extracts in under five. The one
larger 1x measurement that exists — `derived-EmpireBuilderDemo.sit`, 278 KB in
and 417 KB out — took **~134 s**. So a few kilobytes is instant, a quarter of a
megabyte is a couple of minutes.

**The large BinHex is not an anomaly.** `macburger-helper.hqx` was written up
three times as one — it never finished inside the timeouts chosen for it — and
it simply takes 150 s. Instrumenting the engine's byte counter
(`-D UNC_AT_PROGRESS`) showed why the timeouts misled: the rate is very
non-uniform, 16% of the input in the first seven minutes and the last 205 KB
in a hundred seconds. See BLOCKERS.md.

## Relative decode cost per format (Linux, same engine)

Absolute Mac Plus timings are still missing (BLOCKERS.md says why), but the
engine's *relative* cost is a property of the code and transfers to any CPU as
a ratio. Measured with `unclassic t`, best of three, on the release build:

| Fixture | Format | In KB | Out KB | ms | in KB/s |
|---|---|---|---|---|---|
| kermitut9test.bin | MacBinary | 297 | 296 | 0.6 | 485,802 |
| derived-PCCTS.tar | Tar | 280 | 231 | 0.6 | 439,603 |
| derived-PackIt.pit | PackIt (stored) | 60 | 60 | 0.7 | 85,110 |
| macburger-helper.hqx | BinHex | 299 | 253 | 2.9 | 102,708 |
| derived-MUSFMT10.ZIP | Zip (deflate) | 168 | 498 | 3.9 | 42,704 |
| popper-1.7.tar.Z | Compress | 58 | — | 2.0 | 29,526 |
| PCCTS.tar.gz | Gzip | 62 | — | 2.0 | 31,162 |
| derived-EmpireBuilderDemo.sit | StuffIt (13) | 272 | 407 | 9.0 | 30,204 |
| derived-XferIt_1.5b4.sea | Compact Pro | 279 | 926 | 18.2 | 15,351 |
| derived-KeyGraphics.sit | StuffIt 5 (Arsenic) | 5 | 33 | 1.6 | 2,859 |

The ordering is the useful part: envelope formats (MacBinary, tar) are
essentially a copy; BinHex costs a few times that; the real compressors —
StuffIt 13 and Compact Pro's LZH — are 15-30x the cost of a copy per input
byte; and Arsenic is in a class of its own, two orders of magnitude off the
top of the table, which is consistent with its memory profile.

**This is not a Mac Plus timing.** It says a Compact Pro archive costs roughly
six times what a BinHex of the same size costs, on any CPU. The one authentic
1x measurement that exists — `derived-EmpireBuilderDemo.sit`, ~134 s for
278 KB — is in the StuffIt-13 row, so the ratios can be used to reason about
the others, cautiously and from a single anchor.

## Real-hardware verification (Mini vMac — System 6.0.8, 4 MB Mac Plus, 68000)

The Retro68 Mac shell was replayed against a 44-fixture sample spanning all
twelve formats on a **real System 6.0.8 / 4 MB Mac Plus** under Mini vMac
(a true 68000). Every extraction is verified ON THE MAC ITSELF: the app
CRC-32s both forks after reading them back through the File Manager and the
result — painted to the framebuffer, read from a screenshot — is
cross-checked against the same engine's Linux output (`tools/vmac_check.py`,
`tools/decode_grid.py`).

**44/44 byte-exact PASS** — data forks exact, resource forks exact bar the
OS-stamped reserved header (bytes 16–127). Re-run 2026-08-01 and reproduced,
with a caveat about the harness rather than the Mac: two fixtures came back
`EMUDIED` on the first pass — the emulator PROCESS exited within five seconds,
before the application could paint anything — and both passed on an immediate
re-run. That verdict now exists precisely so this is not mistaken for a
Mac-side failure again (`tools/vmac/README.md`). The sample is
`tools/vmac/sample.txt`; reproduce with

    tools/vmac/setup.sh                              # once
    tools/vmac/run.py --list tools/vmac/sample.txt   # 4 MB

An earlier record of this run reported 39/44 — four timeouts and one
unexplained failure (`derived-RWAsm_Folder.sit`, errors on all 38 entries).
Neither survives on the rebuilt harness: all four "timeouts" complete, and
RWAsm_Folder extracts its 38 entries byte-exact at the same 643.2 KB peak
the failing run reported. The old harness was not committed and no longer
exists, so what differed cannot be established; the numbers here are the
ones that reproduce.

Note that the emulator now runs **all out** rather than at Mac Plus speed,
so this harness measures correctness only — **no timing claim about a 7 MHz
68000 can be drawn from it**, including the previously recorded "185 s".

On-Mac engine peak heap (high-water mark) by format, matching the Linux
`--stats` figures:

| Format | on-Mac peak heap |
|---|---|
| MacBinary / BinHex / Tar | 8 KB |
| PackIt | 9 KB |
| Compact Pro | 19 KB |
| Zip | 12–65 KB |
| Gzip | 51 KB |
| StuffIt classic | 19–72 KB‖ |
| Unix compress (.Z) | 15–219 KB§ |
| StuffIt 5 (Arsenic) | 0.63–2.53 MB (block *fill* dependent — see †) |
| DiskDoubler / Now Compress | detect-only — no allocation, cleanly not extracted |

## System 7 tier (Mini vMac — System 7.0.1, 4 MB Mac Plus, 68000)

Until 2026-08-01 every on-Mac result in this repository came from one point of
the System 6 → Mac OS 9 range the project claims: System 6.0.8. This is the
second point.

**System 7.0.1, not 7.1.** 7.1 survives on the mirrors only as floppy disk
sets and a beta ISO, and installing from emulated floppies is hours of GUI
automation for a system that differs in nothing this project exercises. What
matters is that it is System 7 rather than 6, because two things only exist
above System 6: Standard File returns a **working-directory** reference in
`SFReply.vRefNum` rather than a plain volume refNum, and the Process Manager
is always running, so the `SIZE` partition governs the launch. Mini vMac's
Mac Plus supports up to 7.5.5, so this is the same 68000 as every other row.

**44/44 byte-exact PASS at 4 MB** — the same committed sample, the same on-Mac
CRC-32 read-back, the same twelve formats:

    tools/vmac/run.py --system Sys7.img --list tools/vmac/sample.txt

Engine peak heap is **identical to System 6.0.8 at the same memory size on
every fixture**, which is the expected result — the engine allocates through
the same callback and never asks the system for anything — but it had never
been shown. Re-measured with the final build on 2026-08-07:
`derived-RWAsm_Folder.sit` 160,766 B, `derived-KeyGraphics.sit` 181,774 B,
`derived-Troi-ClipSave-Plug-in1.1.sit` 660,262 B. (The figures this paragraph
carried before — 643.2 KB, 1810.8 KB, 710.6 KB — predate the 2026-08-03 block
sizing and were never refreshed.)

**Where this tier and the 1 MB tier disagree is the whole point of the
adaptive inverse BWT, and it is visible in one number.** Same binary, same
fixtures:

| fixture | System 7, 4 MB | System 6, 1 MB |
|---|---|---|
| `derived-a2basic.dmg.sit` | 1,031,525 B (transform table) | 560,589 B (sampled index) |
| `derived-Library_ISBN_Barcoder.sit` | 1,682,142 B (transform table) | 614,134 B (sampled index) |

Given room, the decoder takes the fast table and spends 1.0 and 1.6 MB on it.
Given a 1 MB machine, the table's allocation fails and it takes the sampled
index instead. Nothing selects this but the allocator saying no, and both
columns are byte-exact.

**This tier is 4 MB.** **The 1 MB floor target is System 6, and only
System 6**, and it is demonstrated by the 44/44 run below.

## Floor target verification (Mini vMac — System 6.0.8, **1 MB** Mac Plus, 68000)

The same 44-fixture sample was replayed on a Mini vMac built for **1 MB of
RAM** — the project's floor target — one boot per fixture, same on-Mac
CRC-32 verification (`tools/vmac/run.py --mem 1M --list tools/vmac/sample.txt`).
The engine budget is derived from `FreeMem` at startup.

**44/44 byte-exact PASS** (2026-08-07). There are no memory-budget refusals
left at the floor target: every fixture in the sample, in every format,
extracts byte-exact on a 1 MB Mac Plus. The six StuffIt 5 rows, which were the
last to arrive, with peak heap as the Mac itself reports it:

| Fixture | Format | Outcome at 1 MB | Peak heap |
|---|---|---|---|
| derived-RWAsm_Folder.sit | StuffIt 5 | **all 38 entries byte-exact** | 160,766 B |
| derived-KeyGraphics.sit | StuffIt 5 | all 1 entry byte-exact | 181,774 B |
| derived-PuzzleGetter_0.8.sit | StuffIt 5 | **all 26 entries byte-exact** | 269,084 B |
| derived-a2basic.dmg.sit | StuffIt 5 | **all 1 entry byte-exact** | 560,589 B |
| derived-Library_ISBN_Barcoder.sit | StuffIt 5 | **all 34 entries byte-exact** | 614,134 B |
| derived-Troi-ClipSave-Plug-in1.1.sit | StuffIt 5 | **all 13 entries byte-exact** | 660,262 B |

The last two rows are the ones that moved on 2026-08-07: `a2basic` was a clean
per-entry refusal of its only entry, and `Library_ISBN` delivered 33 of 34.
Both now need a *sampled* inverse BWT rather than the 4-bytes-per-byte table,
chosen automatically because the table's allocation fails first.

**The CLI's `--budget` simulation is now cross-validated against the real Mac
allocator.** `unclassic --budget 678392` on Linux predicted 560,535 B and
614,080 B for those two; the Mac measured 560,589 B and 614,134 B — 54 bytes
apart in both cases. That is worth stating because every budget figure
elsewhere in this file is a Linux number.

**This tier moved four times in six days, 39/44 → 44/44.** The first two were
about not paying for memory the data does not use: on 2026-08-02 the shell
stopped reading the whole archive into RAM before the engine got a budget
(39/44 → 40/44), and on 2026-08-03 the Arsenic block stopped being allocated at
its declared 512 KB (40/44 → 41/44). `derived-RWAsm_Folder.sit` went from
595.7 KB at the start of that to **160,766 B** for the same 38 byte-exact
entries.

The third, on 2026-08-06, was not about how MUCH was allocated but about the
SHAPE it left behind (41/44 → 42/44). Growing the block by doubling from 8 KB
left a trail of freed steps — 8+16+32+64 KB under a final 128 KB block — and a
geometric trail can never satisfy the step that follows it, so it stranded
125,614 B of heap. That is what made `derived-Troi-ClipSave-Plug-in1.1.sit`
refuse an entry whose 498,548 B request had 678 KB of budget behind it but only
a 468,126 B contiguous run in front of it. Sizing the first allocation from the
entry — `min(outlen, blocksize)`, since a block can hold neither more than the
whole output nor more than a block — removes the trail, and the entry fits.

The fourth, on 2026-08-07, was the only one that changed what the decoder
NEEDS rather than what it asks for (42/44 → 44/44). The 4-bytes-per-byte
transform vector is the dominant allocation, and it is no longer built when it
does not fit: a sampled occurrence index answers the same query from roughly
`4 * sum_c min(counts[c], target)` bytes, trading time for memory, chosen per
block by the table's allocation failing. DECISIONS.md 2026-08-07.

**How much the last two actually needed, and how that was mis-stated twice.**
An Arsenic entry needs its block plus four bytes of transform vector per byte
the block holds. Until 2026-08-03 this section said the three refused entries
each filled a 512 KB block and so needed ~2.5 MB against ~700 KB. Instrumenting
`numbytes` where the transform vector is sized says none of them does:

| fixture | largest block fill | capacity | 4x transform | peak |
|---|---|---|---|---|
| `derived-Library_ISBN_Barcoder.sit` | 323,384 B | 512 KB | 1,263 KB | 1,854,208 B |
| `derived-a2basic.dmg.sit` | 197,515 B | 256 KB | 772 KB | 1,088,588 B |
| `derived-Troi-ClipSave-Plug-in1.1.sit` | 124,637 B | 128 KB | 487 KB | 666,004 B |

`~35 KB parser + capacity + 4 x fill` reproduces all three peaks, so
`Troi-ClipSave`'s refused entry needed about **650 KB**, not 2.5 MB — which is
inside the 678,392 B budget, and is why it now passes. The 512 KB
figure was true of the CORPUS — `derived-EasyFind.dmg.sit` and
`derived-Domino_v1.4.sit` both reach 524,257 B, 31 bytes short of a full block,
and they are what sets the 2.53 MB maximum in † above — and was applied to
three fixtures it does not describe. **A true number about the worst case is
not a number about the case in front of you.** See *Withdrawn claims* in
BLOCKERS.md, and OPEN_ITEMS.md for what is actually left.

Those three peaks are what the fast path costs, and all three are now history:
under the sampled index the same entries extract fully from **245,897 B**
(`a2basic`), **393,028 B** (`Library_ISBN`) and **167,455 B**
(`Troi-ClipSave`) — bisected minima, not peaks under a cap. The per-entry
refusal machinery is unchanged and still correct; nothing in the sample
reaches it any more.


**`popper-1.7.tar.Z` and `PCCTS.tar.gz` used to fail here and no longer do.**
The Mac sink previously accumulated each whole output fork in a `NewPtr`
block and wrote it in `sink_end`, so the shell needed `archive + engine peak
+ largest output fork` — and those two fixtures have the sample's largest
output forks (174 KB and 287 KB), which a 1 MB machine could not spare. The
sink now writes each chunk straight to the File Manager as the engine
produces it, so **the shell's own RAM use no longer depends on output size
at all**. Both fixtures are byte-exact at 1 MB, with the engine's peak heap
unchanged. The old path is still buildable (`UNC_MAC_STAGE_WRITES`) and both
are byte-exact through the qemu-m68k mock in CI.

What unblocked all of this was rewriting the File Manager calls to use
explicit, fully-zeroed HFS param blocks. This was originally attributed to a
broken Retro68 `HOpen` glue; **that attribution has been withdrawn** — a
standalone minimal reproduction (`tools/retro68-hopen-repro/`) disproved it.
See DECISIONS.md and BLOCKERS.md.

## Mac OS 9 tier (QEMU PowerPC — Mac OS 9.2, `mac99`, 512 MB, 68LC040 emulation)

The third and last point of the System 6 → Mac OS 9 range the project claims,
and the only one where the 68k binary does not run on a 68k CPU: Mac OS 9.2 on
emulated PowerPC executes it through the **68LC040 emulator** built into the
system. Nothing above System 7 had ever run it.

**13/13 byte-exact** — `tools/vmac/os9sample.txt`, one fixture per format,
each in its own boot from a pristine copy of the master image:

    tools/vmac/os9.py --setup                                   # once
    tools/vmac/os9.py --list tools/vmac/os9sample.txt -o <dir> --launch

| fixture | format | files | data bytes | rsrc bytes | result |
|---|---|---|---|---|---|
| `export-hc.hqx` | BinHex | 1 | 1,615 | 0 | ✅ byte-exact |
| `derived-keyAhead.cpt` | Compact Pro | 1 | 0 | 1,233 | ✅ byte-exact |
| `synth-exo-Z.Z` | compress | 1 | 2,200 | 0 | ✅ byte-exact |
| `synth-exo-gz.gz` | gzip | 1 | 2,200 | 0 | ✅ byte-exact |
| `stuffit151mstr.bin` | MacBinary | 1 | 0 | 365 | ✅ byte-exact |
| `synth-packit-2.pit` | PackIt | 5 | 3,050 | 2,020 | ✅ byte-exact |
| `derived-Export.sit` | StuffIt | 1 | 6,944 | 0 | ✅ byte-exact |
| `derived-DDT.sit` | StuffIt with a resource fork | 2 | 1,473 | 3,504 | ✅ byte-exact |
| `derived-KeyGraphics.sit` | StuffIt 5 / Arsenic | 1 | 0 | 33,484 | ✅ byte-exact |
| `derived-XferIt_1.5b4.sea` | Compact Pro self-extracting | 10 | 679,423 | 268,752 | ✅ byte-exact |
| `derived-DandStoQIF2.sea` | DiskDoubler: must REFUSE | 0 | — | — | ✅ declined, as Linux does |
| `synth-exo-tar.tar` | tar | 4 | 7,788 | 0 | ✅ byte-exact |
| `synth-exo-zip-deflate.zip` | zip | 4 | 7,788 | 0 | ✅ byte-exact |

**13/13**, 32 files, 712,481 data bytes and 309,358 resource-fork bytes compared.

Two things differ from the Mini vMac tiers, and both make this check stronger
rather than weaker:

- **The result is read off the disk, not the screen.** The transfer volume is
  a file on the host, so after the emulator exits both forks of every
  extracted file are lifted out with hfsutils and compared **byte for byte**
  against `unclassic x -nr`. The Mini vMac tiers compare an on-screen CRC-32
  aggregate because getting a floppy back out mid-run is awkward; nothing here
  needs that.
- **Output names, folder structure and 8-bit characters are compared.** A
  summed CRC cannot carry a name, so the System 6 and 7 tiers have never
  checked one and cannot be made to fail on one. This tier does, and its first
  sweep immediately caught a real Mac-shell defect in the gzip/.Z fallback
  name — now fixed (BLOCKERS.md, DECISIONS.md). `derived-XferIt_1.5b4.sea`
  alone lands 10 files three folders deep, and PackIt's `Appé` is a MacRoman
  name that has to survive the round trip.

**The sample is small on purpose.** Each fixture costs a whole boot (~110 s on
an idle host, plus a 2 GB image copy), where Mini vMac replays a 44-fixture set
inside one boot. So this samples for breadth of format; the memory-budget
spread that `sample.txt` exists to exercise is a 1 MB question, and this
machine has 512 MB.

**The Finder is driven from the keyboard.** The pointer does not work in this
guest at all — five mouse primitives measured at exactly zero effect, cursor
pinned to screen corners. See BLOCKERS.md, and `tools/vmac/os9probe.py` for
the measurement.

### Onto HFS+ (the same machine, the boot volume instead of the transfer disk)

Everything above extracts onto the transfer volume, which is HFS. The OS 9
boot volume is HFS+, so `--hfsplus` renames it to `Out` from the keyboard and
runs the **autotest** build against it: the extraction lands on HFS+, and the
application CRC-32s both forks after reading them back through the File
Manager, exactly as the Mini vMac tiers do.

    tools/vmac/os9.py fixtures/derived-Berkeley_Packet_Monitor.sit \
                      -o <dir> --hfsplus

| fixture | files | data | rsrc | peak heap | result |
|---|---|---|---|---|---|
| `derived-Berkeley_Packet_Monitor.sit` | 31 | 372,301 B | — | 779.1 KB | ✅ CRC + length identical to Linux |
| `derived-XferIt_1.5b4.sea` | 10 | 679,423 B | 268,752 B | 18.8 KB | ✅ CRC + length identical to Linux |

Both report `ret=0` with zero per-entry errors, and every output **name** on
HFS+ is exactly what the 31-character rule predicts — including the one entry
in the Berkeley fixture whose name is 34 characters and must be truncated. A
68k application reaching HFS+ through the classic File Manager is capped at 31
characters just as it is on HFS, so HFS+ changes nothing here; that is the
result, and it was worth measuring rather than assuming.

Two things make this tier trustworthy:

- **The answer comes back as a file, not off the screen.** `at_report()` pokes
  1bpp pixels straight at the framebuffer — the right channel on a Mac Plus,
  and invisible on OS 9's 32-bit screen (confirmed by screenshot: the desktop
  is untouched after the run finishes). `at_report_file()` writes the same
  values, plus every output name, to the plain-HFS input volume. That is what
  made HFS+ reachable at all: the output volume was never the obstacle, the
  reporting channel was.
- **That the output really landed on HFS+ is measured.** The boot volume is
  HFS+ inside an HFS wrapper, and hfsutils can see only the wrapper. After the
  run the wrapper still contains exactly one file,
  `Where_have_all_my_files_gone?` — so none of those 41 files went to plain
  HFS. A signature word was considered and rejected: the classic File Manager
  reports `'BD'` for an HFS+ volume for compatibility, so a negative would
  prove nothing.

One corroboration falls out of it: the Mac's **unmasked** resource-fork CRC
equals Linux's **masked** one, so Mac OS 9 leaves the 112-byte reserved header
area alone where System 6 stamps it — the same thing the byte-level comparison
found on the HFS tier.

### The `SIZE` partition under OS 9's Process Manager

Built with a 600 KB preferred partition and run against
`derived-KeyGraphics.sit`, which needs ~656 KB: **1 entry refused, 0 files,
`ret == UNC_OK`, peak heap 35.5 KB** — the same figure System 7.0.1 gives, on
a machine with 512 MB of RAM. The partition governs, not the hardware, and
35.5 KB is parser state alone: the 512 KB Arsenic block was declined at
request time, never allocated. Method and the three-system table in
MANUAL_TESTS.md.

**Still not covered here:** names HFS+ permits that HFS does not — probably
unreachable through the classic File Manager at all, since it caps at 31
characters on either filesystem, but that is unproven either way. Real PowerPC
silicon, like real 68k silicon, remains untouched.

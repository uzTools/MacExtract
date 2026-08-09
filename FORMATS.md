# FORMATS.md — format support matrix

Status after M0–M9. "Oracle coverage" = fixtures with byte-exact
differential manifests (built from The Unarchiver's `unar`; see
TESTING.md); every one passes, plus 10 corruption variants each in the
robustness suite. "Peak RAM" = allocator high-water mark across the
whole corpus for that format (engine allocations only, via
`unclassic t --stats`).

| Format | Status | Methods | Oracle coverage | Peak RAM | 400 KB budget |
|---|---|---|---|---|---|
| MacBinary I/II/III | extract | — | 233 fixtures | 8 KB | full |
| AppleSingle/Double | extract | — | (unit tests + envelopes) | 8 KB | full |
| BinHex 4 (.hqx) | extract | RLE90 | 179 fixtures | 8 KB | full |
| PackIt (.pit) | extract | store, Huffman; encrypted detected | 4 fixtures (1 real + 3 synthetic PMa4) | 9 KB | full |
| Compact Pro (.cpt) | extract | RLE, LZH+RLE | 108 fixtures | 19 KB | full |
| StuffIt classic (.sit) | extract | 0 store, 1 RLE90*, 2 LZW, 3 Huffman, 5 LZAH, 6 fixed Huffman‡, 8 MW, 13 LZSS+Huffman; encrypted detected | 227 fixtures | 8–76 KB‖ | full |
| StuffIt 5 (.sit) | extract | 0, 13, 15 Arsenic; encrypted detected | 31 fixtures | 0.15–2.53 MB† | 23 of 31 fixtures extract FULLY; the rest refuse per entry |
| Zip | extract | store, deflate; others & encrypted per-entry errors | 5 fixtures (2 of them PKZIP 1.x, graded on names and entry counts only — Implode is out of v1 scope, and `unar` adjudicates 5 of their 7 entries) | 66 KB | full |
| Gzip | extract | deflate | 3 fixtures | 51 KB | full |
| Unix compress (.Z) | extract | LZW ≤16 bit | 4 fixtures | 219 KB§ | full |
| Tar (ustar/v7) | extract | — (links reported unsupported) | 3 fixtures (2 real 1990 v7 tars) + unit tests | 8 KB | full |
| StuffIt segment (multi-part) | extract | — (join only; the joined file is the next layer) | 7 synthetic sets, oracle-adjudicated | 8 KB | full |
| StuffIt X (.sitx) | detect only | — | — | — | — |
| DiskDoubler (DD, DDAR, DDA2) | detect only | — | 4 sniffed | — | — |
| Now Compress | detect only | — | 1 sniffed | — | — |
| LZH/LHA (-lh?-, -lz?-) | detect only | — | — | — | — |
| DiskCopy 4.2 (.image) | detect only | — | synthetic 800K GCR + real 800K image; 0 false positives in 804 fixtures | — | — |

\* **Method 1 occurs once and IS oracle-adjudicated** (since 2026-08-08).
It is the 470-byte resource fork of `I Want To Buy Some Cheese` in
`derived-New_Python.sit` (470 → 389), and `unar` decodes it byte-identically
to us — `unar` fails elsewhere in that archive, on a method-3 fork, which is
why per-entry manifests were needed to see this one at all (TESTING.md, "When
the oracle fails on an entry"). Edge cases the one real fork cannot reach — runs of `0x90`, the 255-byte
maximum token, output ending inside a run — are covered by
`synth-sit-rle90.sit` (`tools/synth_sit1.py`), also oracle-adjudicated.

‡ **Method 6, "Fixed Huffman", is implemented and oracle-adjudicated**
(since 2026-08-08). It occurs once in the corpus: the 34,818-byte resource
fork of `INITLoader` in `derived-INITLoader.sit`, two Huffman-coded segments,
which we decode byte-exact. Every segment is coded with a tree whose SHAPE is
a constant of the format, so it is generated once from the reference by
`tools/gen_sit6_tables.py` into `src/sit6_tables.h` rather than rebuilt per
fork on a 68000; only the byte each leaf stands for is declared per segment.
Peak heap 39,998 B on that fixture — the segment buffer is sized from the
segment (31,806 B here), capped at 64 KB.

The branches one real fork cannot reach — a *stored* segment, PackBits fillers,
the longest and shortest runs, a one-byte alphabet, twelve segments in a fork —
are covered by `synth-sit-fixhuf.sit` (`tools/synth_sit6.py`), also
oracle-adjudicated, 10 forks over 5 entries.

**The oracle for both is `macunpack`, not `unar`:** XADMaster recognizes the
method and refuses it (`//case 6: fixed huffman`,
`reference/XADMaster/XADStuffItParser.m`), which is where the name comes from;
macunpack has decoded it since 1991 and is the reference the decoder is
transcribed from. TESTING.md, "A second oracle", for what that does and does
not prove; BLOCKERS.md for the claim that no oracle existed.

† **Every real Arsenic block is 512 KB.** The block size is `1 << (v+9)`
with `v` read from the stream, so other sizes are legal, but across the
31-fixture StuffIt 5 corpus **all 484 Arsenic streams — one per compressed
fork — declare 512 KB** (`v` = 10, blockbits 19). Measured directly by
instrumenting the point where `sit_arsenic.c` reads `v`, not inferred.

Peak heap is modelled by

    peak  =  ~35 KB parser state  +  block capacity  +  4 × actual block fill

because only the *block* is allocated at its declared size; the inverse-BWT
transform vector is sized to how much of the block the entry actually fills
(`transform = numbytes * 4`, in `ars_bwt_prepare`). Peak heap therefore cannot
recover the declared block size — the earlier "128 KB (14 fixtures) / 256 KB
(9) / 512 KB (8)" figures were inferred by dividing peak by five and are
withdrawn (BLOCKERS.md, *Withdrawn claims*).

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

Those figures are what the corpus costs today. **Arsenic reached the 1 MB floor
in four steps, and the per-fixture outcomes are the two Mini vMac sections
below:** 2026-08-02 the shell stopped slurping the archive, 2026-08-03 the
block stopped being allocated at its declared 512 KB, 2026-08-06 its first
allocation was sized from the entry, 2026-08-07 the transform vector became
optional. Before the first, peak was min 0.63 / median 0.97 / mean 1.23 MB with
**every** entry over a 400 KB budget; nothing about the format or the decoder
changed, only what is allocated to hold it. One DECISIONS.md entry per step,
same dates.

§ **The `.Z` peak used to be a flat 274,432 B for every input, and is now
sized from the input.** MEASURED 2026-08-03. `compress(1)` writes `maxbits=16`
whatever it compressed, so a 488-byte `.Z` declared a 65,536-entry table it
filled a few hundred entries of; the table is now bounded from the input by
`symbols <= 256 + reserved + insize * 8 / 9` (DECISIONS.md 2026-08-03):

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

‖ **Method 13's LZSS window is sized from the entry, not from the format's
64 KB.** MEASURED 2026-08-06; an instrumented run over the whole corpus counted
**0 back-references past produced output**, which is what licenses it
(DECISIONS.md 2026-08-06). 34 fixtures improved, none regressed; the corpus
maximum is unchanged at 76,944 B because some forks genuinely exceed 64 KB, so
the gain is at the small end — `derived-MacGzip.sit` 76,944 → 13,456 B, and
on-Mac `derived-Export.sit` 76,984 → 19,640 B.

## Envelope auto-unwrap

`unclassic x` unwraps chained envelopes by content sniffing
(never by extension): MacBinary, BinHex, AppleSingle/Double, gzip and
.Z layers that yield exactly one file are recursively extracted and
the intermediate deleted (`-nr` disables; depth ≤ 8). Verified chains:
`.sit.bin`, `.sit.hqx`, `.tar.Z` (tools/run_unwrap.py, in CI).

A **StuffIt segment** is an envelope too, and joins that list: the
parts are joined, the file inside comes out, and if that file is an
archive the same recursion continues into it.

## Segmented archives (multi-part sets)

One logical file cut across several, one per floppy. The scheme
implemented is **StuffIt segments** (XADMaster's "StuffIt split file"),
a 100-byte header on each part: `B0 56 00`, part number, the original
file's name, and 26 fingerprint bytes at offset 68 (type, creator,
Finder flags, both dates, both fork lengths). Concatenating the parts'
payloads in order gives the original file — resource fork, then data
fork. `src/fmt_sitseg.c` has the layout and its source.

Two properties of that header decide the design, and DECISIONS.md 2026-08-08
has why they decided it: **identity is content, not name** (a part belongs to a
set if its name bytes and those 26 bytes agree — the `misnamed` case in the
suite joins correctly and `unar` cannot read it), and **the set is
self-terminating** (`rsrclen + datalen` is the exact payload total, so no part
count is stored anywhere and none is needed).

**The join is read strictly forward: 0 backward crossings**, measured
over the 3-part and 12-part cases (`unclassic x --stats` reports part
opens and how many were backward). That is what decides the cost on
removable media — a backward crossing is a disk the user has to put
back — so it is measured rather than assumed.

Peak heap for the join is 8 KB: one buffer, no part table beyond the
caller's ~1.1 KB scratch struct, one part open at a time.

### On a real emulated Mac Plus (System 6.0.8, 2026-08-08)

`derived-Cal.sit` (50,205 B) cut into three parts and put on one
floppy, the parts named `archive.sit`, `part-two` and `zzz` — names
that resemble neither each other nor the file inside:

| tier | result |
|---|---|
| Mini vMac, 4 MB | joined and written as `Cal.sit`, **byte-identical** to the original, type/creator `SIT!/SIT!` off the header |
| Mini vMac, **1 MB** (floor target) | same, byte-identical |
| 4 MB, part 2 removed | `ret = -11` (`UNC_ERR_SEGMENTED`), 1 entry error, the 20,000 B that part 1 held left on the volume; peak heap **8,208 B** |

Read back off the Out volume with hfsutils and compared to the source
file on the host, which is layer 9 of TESTING.md — not the on-screen
grid, which cannot see a filename. Re-run with:

```
python3 tools/vmac/run.py PART1 --extra-file HOST:MACNAME ... --keep-disks
```

The parts being found at all is the point of the middle column: the app
reads every file in the folder and asks the engine, so the names are
free.

### The "locate part N" dialog, driven on the same machine (2026-08-09)

Those runs use the autotest build, which has no user and does not
compile the dialog at all. The interactive application was driven
separately, with part 1 alone on the boot volume and parts 2 and 3 on a
second floppy so the folder scan has to fail:

```
python3 tools/vmac/interactive.py fixtures/derived-Cal.sit --segments -o DIR
```

| step | what the Mac showed |
|---|---|
| open part 1 | *Part 2 of "derived-Cal.sit" has not been found. Locate it, skip it, or cancel.* — Cancel / Skip / **Find...** |
| Find..., switch to the other floppy, offer part **3** | *That is part 3 of the same archive. Part 2 is the one needed.* |
| Find... again, offer part 2 | extraction resumes with no further prompt: locating one part rescans its folder, which picks up part 3 beside it |
| finish | *Extraction complete.* |

**It ends on a byte comparison, not on the screenshot**: the joined file
is read back off the volume the Mac wrote to and compared to the
fixture — 50,205 B, byte-exact. A screenshot of "Extraction complete."
is not evidence that the bytes are right, and this phase found two
harness bugs that each produced a plausible-looking wrong screenshot
(DECISIONS.md).

What is still NOT covered is a part arriving on a disk inserted
mid-run — see OPEN_ITEMS.md section 4.

## Hardening

- Differential: 797 fixtures byte-exact against `unar` manifests
  (both forks + type/creator), `./ci.sh`. `run_diff.py` prints the
  number it actually ran, plus two figures that must be read with it:
  **12 forks across 9 fixtures are oracle-unadjudicated** (both
  implementations decline every one of them, so the engine's own CRC-16
  is the only check), and **7 entries are compressed with a method the
  ORACLE names as outside v1 scope** and are graded on their names and
  entry counts alone. No fixture is skipped for anything our own engine
  says about it (TESTING.md, "When our engine declines an entry"). It was
  769 until 2026-08-08 and reached 797 that day in four steps, every one of
  them the measuring apparatus rather than new archives (BLOCKERS.md,
  DECISIONS.md).
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

**StuffIt 5 / Arsenic at 1x — and it is in a class of its own.** The list
above samples StuffIt 5 with a 4,611 B fixture, far too small to reach the
sampled inverse BWT, so the fallback's cost on real hardware went unmeasured
until 2026-08-07. Both Arsenic fixtures in the 1 MB sample, both paths,
extract time only, on a purpose-built 1 MB 1x emulator (`build_mv mv-1M-1x
1M z`; `setup.sh` had no such build until then):

| Fixture | Output | 4 MB — transform table | 1 MB — sampled index | ratio |
|---|---|---|---|---|
| `derived-a2basic.dmg.sit` | 205,019 B | **587 s** (peak 1,031,525 B) | **966 s** (peak 560,589 B) | 1.65x |
| `derived-Library_ISBN_Barcoder.sit` | 641,115 B | **768 s** (peak 1,682,142 B) | **1,898 s** (peak 614,134 B) | 2.47x |

**The fallback costs 1.65x to 2.47x, and Arsenic was already the slow one.**
Ten minutes for a 205 KB output is what the *fast* path costs a 7 MHz 68000;
before 2026-08-07 a 1 MB machine could not extract either entry at all. The
ratio widens with block fill, and neither the x86 ratio nor one fixture scaled
by output size predicts these — DECISIONS.md 2026-08-07 for both.

All four figures were measured on one build, with one emulator running at a
time. They supersede an earlier pair (537 s / 927 s) taken before the progress
rewrite; DECISIONS.md 2026-08-07 records the ~40 s between the two sets as
unexplained.

**8/8, and the shape is the useful part: for small archives the BOOT dominates
and extraction is seconds.** A stripped System 6.0.8 reaches the application in
about 10 s; everything in this table then extracts in under five. The one
larger 1x measurement that exists — `derived-EmpireBuilderDemo.sit`, 278 KB in
and 417 KB out — took **~134 s**. So a few kilobytes is instant, a quarter of a
megabyte is a couple of minutes.

**The large BinHex is not an anomaly.** `macburger-helper.hqx` simply takes
150 s; the rate is very non-uniform (16% of the input in the first seven
minutes, the last 205 KB in a hundred seconds), which is what made the
timeouts chosen for it mislead three times. BLOCKERS.md.

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

The Retro68 Mac shell was replayed against a 55-fixture sample spanning all
twelve formats on a **real System 6.0.8 / 4 MB Mac Plus** under Mini vMac
(a true 68000). Every extraction is verified ON THE MAC ITSELF: the app
CRC-32s both forks after reading them back through the File Manager and the
result — painted to the framebuffer, read from a screenshot — is
cross-checked against the same engine's Linux output (`tools/vmac_check.py`,
`tools/decode_grid.py`).

**55/55 byte-exact PASS** (2026-08-08) — data forks exact, resource forks exact
bar the OS-stamped reserved header (bytes 16–127).

**The sample was 44 fixtures until 2026-08-08**, when nine that had never had
an oracle manifest gained one and were added: seven THINK C projects holding
both `X` and a real `X.rsrc`, and two with a leading-`~` name. Two more joined
the same day for the same reason once method 6 had an oracle —
`derived-INITLoader.sit` and `synth-sit-fixhuf.sit`, measured on all three
Mini vMac tiers that day and byte-exact on each. Every `n/44`
figure elsewhere in this file refers to the smaller sample and is left as it
was measured. The nine are the only fixtures here whose shape can distinguish
a fork-naming mistake from a correct extraction, which is why the host-side
readers had to stop guessing at `<X>.rsrc` sidecars first (DECISIONS.md,
2026-08-08).

The sample is `tools/vmac/sample.txt`; reproduce with

    tools/vmac/setup.sh                              # once
    tools/vmac/run.py --list tools/vmac/sample.txt   # 4 MB

An `EMUDIED` verdict (the emulator process exits before the application paints)
is a harness event, not a Mac-side failure — `tools/vmac/README.md`. An earlier
39/44 record of this run does not survive the rebuilt harness (BLOCKERS.md,
*Withdrawn claims*).

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

**55/55 byte-exact PASS at 4 MB** (2026-08-08; 44/44 before the sample grew) —
the same committed sample, the same on-Mac CRC-32 read-back, the same twelve
formats:

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
System 6**, and it is demonstrated by the 55/55 run below.

## Floor target verification (Mini vMac — System 6.0.8, **1 MB** Mac Plus, 68000)

The same 55-fixture sample was replayed on a Mini vMac built for **1 MB of
RAM** — the project's floor target — one boot per fixture, same on-Mac
CRC-32 verification (`tools/vmac/run.py --mem 1M --list tools/vmac/sample.txt`).
The engine budget is derived from `FreeMem` at startup.

**55/55 byte-exact PASS** (2026-08-08; 44/44 on 2026-08-07, before the nine
recovered fixtures and the two method-6 fixtures joined the sample). There are no memory-budget refusals
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

**This tier moved four times in six days, 39/44 → 44/44**, one DECISIONS.md
entry per step and none of them a decoder change until the last:

| date | what changed | tier |
|---|---|---|
| 2026-08-02 | the shell stopped reading the whole archive into RAM | 39/44 → 40/44 |
| 2026-08-03 | the Arsenic block stopped being allocated at its declared 512 KB | 40/44 → 41/44 |
| 2026-08-06 | the block's first allocation sized from the entry, so growth strands no heap | 41/44 → 42/44 |
| 2026-08-07 | the transform vector is not built when it does not fit | 42/44 → 44/44 |

`derived-RWAsm_Folder.sit` went 595.7 KB → **160,766 B** across the first two,
for the same 38 byte-exact entries.

The three entries that were refused before the last step peaked at 1,854,208 B
(`Library_ISBN`), 1,088,588 B (`a2basic`) and 666,004 B (`Troi-ClipSave`) on the
fast path — `~35 KB parser + capacity + 4 × fill` reproduces all three. Under
the sampled index the same entries extract fully from **245,897 B**, **393,028 B**
and **167,455 B**, bisected minima rather than peaks under a cap. (This is where
the withdrawn "each fills a 512 KB block" claim lived; BLOCKERS.md has it and
what it cost.) The per-entry refusal machinery is unchanged and still correct;
nothing in the sample reaches it any more.

**`popper-1.7.tar.Z` and `PCCTS.tar.gz` used to fail here and no longer do** —
the Mac sink stopped accumulating whole output forks, so the shell's RAM use no
longer depends on output size at all, and these two have the sample's largest
output forks (174 KB and 287 KB). Both byte-exact at 1 MB, engine peak heap
unchanged; the old path stays buildable as `UNC_MAC_STAGE_WRITES` and both are
byte-exact through the qemu-m68k mock in CI. BLOCKERS.md, *Corrected figures*,
and DECISIONS.md for the HFS param-block rewrite that unblocked it — and for the
`HOpen` attribution that was withdrawn.

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

This tier reads its result **off the disk rather than the screen** — both forks
of every extracted file lifted out with hfsutils and compared byte for byte
against `unclassic x -nr` — so unlike the Mini vMac tiers it compares **names,
folder structure and 8-bit characters** too, which is how it caught the gzip/.Z
fallback-name defect on its first sweep (TESTING.md for what each layer can and
cannot see). `derived-XferIt_1.5b4.sea` alone lands 10 files three folders deep,
and PackIt's `Appé` is a MacRoman name that has to survive the round trip.

**The sample is small on purpose:** each fixture costs a whole boot (~110 s plus
a 2 GB image copy) against Mini vMac's ~5 s, so this tier samples for breadth of
format, and the memory-budget spread `sample.txt` exercises is a 1 MB question
on a 512 MB machine.

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

- **The answer comes back as a file, not off the screen** — `at_report_file()`
  on the plain-HFS input volume, because the framebuffer channel that works on
  a Mac Plus is invisible on OS 9's 32-bit screen. The output volume was never
  the obstacle; the reporting channel was (DECISIONS.md 2026-08-02).
- **That the output really landed on HFS+ is measured.** hfsutils sees only the
  HFS wrapper, and after the run it still contains exactly one file,
  `Where_have_all_my_files_gone?` — so none of those 41 files went to plain HFS.
  A signature word proves nothing here (BLOCKERS.md).

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
request time, never allocated.

Same binary, same fixture, three systems — the partition governs and System 6
without MultiFinder ignores `SIZE` outright, exactly as the resource's comment
always claimed and nothing had ever shown:

| System | Outcome | Engine peak heap |
|---|---|---|
| System 7.0.1 (4 MB) | **1 entry refused, 0 files** | 35.5 KB |
| Mac OS 9.2 (512 MB) | **1 entry refused, 0 files** | 35.5 KB |
| System 6.0.8 (4 MB) | 1 file, byte-exact | 656.8 KB |

The 656.8 KB row is the control — the same figure the 4 MB sweep records for
that fixture, with nothing changed but the partition. Method and commands in
`tools/vmac/README.md` ("The `SIZE` partition").

**Still not covered here:** names HFS+ permits that HFS does not — probably
unreachable through the classic File Manager at all, since it caps at 31
characters on either filesystem, but that is unproven either way. Real PowerPC
silicon, like real 68k silicon, remains untouched.

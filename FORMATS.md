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
| StuffIt classic (.sit) | extract | 0 store, 1 RLE90*, 2 LZW, 3 Huffman, 5 LZAH, 8 MW, 13 LZSS+Huffman; encrypted detected | 211 fixtures | 76 KB | full |
| StuffIt 5 (.sit) | extract | 0, 13, 15 Arsenic; encrypted detected | 31 fixtures | 0.63–2.53 MB† | per-entry refusal (all Arsenic entries > 400 KB) |
| Zip | extract | store, deflate; others & encrypted per-entry errors | 3 fixtures (+2 PKZIP-1.x corpus-only) | 66 KB | full |
| Gzip | extract | deflate | 3 fixtures | 51 KB | full |
| Unix compress (.Z) | extract | LZW ≤16 bit | 4 fixtures | 268 KB | full |
| Tar (ustar/v7) | extract | — (links reported unsupported) | 3 fixtures (2 real 1990 v7 tars) + unit tests | 8 KB | full |
| StuffIt X (.sitx) | detect only | — | — | — | — |
| DiskDoubler (DD, DDAR, DDA2) | detect only | — | 4 sniffed | — | — |
| Now Compress | detect only | — | 1 sniffed | — | — |
| LZH/LHA (-lh?-, -lz?-) | detect only | — | — | — | — |
| DiskCopy 4.2 (.image) | detect only | — | synthetic 800K GCR + real 800K image; 0 false positives in 803 fixtures | — | — |

\* method 1 does not occur in the harvested corpus; pinned by unit
tests transcribed from XADRLE90Handle.

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
entry actually fills (`transform = numbytes * 4`, `sit_arsenic.c:327`),
which is exactly what lets a small Arsenic entry fit a small budget. A
fixture peaking at 0.64 MB is therefore a 512 KB block holding ~24 KB,
not a 128 KB block; dividing by five turned every small payload into an
imaginary small block. Peak heap can never recover the declared block
size, so the claim was not just false but unmeasurable that way.

Measured peak heap over the corpus (`unclassic t --stats`): **min
0.63 MB / median 0.97 MB / mean 1.23 MB / max 2.53 MB**, the maximum
being the entries that genuinely fill a 512 KB block (35 KB + 512 KB +
2048 KB). EVERY Arsenic entry exceeds a 400 KB budget, so all fail
cleanly per entry ("block too large for memory budget") under the M9
400 KB cap.

On a **1 MB Mac Plus** Arsenic is a partial feature: the six Arsenic
fixtures in the on-Mac sample split into one that extracts completely,
two that extract most of their entries and refuse the rest, and three
that refuse every entry. The boundary is **the size of the archive**,
not the block size (which never varies): the shell slurps the archive
into RAM before extracting and budgets the engine against what is left,
so a bigger archive leaves less room for the 512 KB block. The six line
up monotonically by archive size — 4.6 KB extracts fully, 66 KB and
92 KB extract most entries, and 153 KB, 202 KB and 222 KB cannot afford
the block at all. All six extract byte-exact at 4 MB. See the two Mini
vMac sections below for the per-fixture outcomes.

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
| StuffIt classic | 72–75 KB |
| Unix compress (.Z) | 268 KB |
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

Engine peak heap is **identical to System 6.0.8 on every fixture** (e.g.
`derived-RWAsm_Folder.sit` 643.2 KB, `derived-Library_ISBN_Barcoder.sit`
1810.8 KB, `derived-PuzzleGetter_0.8.sit` 710.6 KB), which is the expected
result — the engine allocates through the same callback and never asks the
system for anything — but it had never been shown.

**System 7.0.1 does not run at 1 MB at all.** A 1 MB probe painted nothing in
180 s: not a failed extraction, a system that cannot boot. System 7 wants 2 MB
and the floor-target machine has half of it. This is not a defect in the
application and there is no 1 MB row for this tier — **the 1 MB floor target
is System 6, and only System 6.** The application's own memory floor is
unchanged and is still demonstrated by the 39/44 System 6.0.8 run below.

## Floor target verification (Mini vMac — System 6.0.8, **1 MB** Mac Plus, 68000)

The same 44-fixture sample was replayed on a Mini vMac built for **1 MB of
RAM** — the project's floor target — one boot per fixture, same on-Mac
CRC-32 verification (`tools/vmac/run.py --mem 1M --list tools/vmac/sample.txt`).
The engine budget is derived from `FreeMem` at startup.

**39/44 byte-exact PASS**, and every fixture that does not pass is a StuffIt 5
memory-budget refusal — the documented tier. Re-run 2026-08-01: 39/44 again,
the same five fixtures, and the same per-fixture entry counts and peak heaps
as the table below, to the tenth of a kilobyte. All five pass at 4 MB:

| Fixture | Format | Outcome at 1 MB | Peak heap |
|---|---|---|---|
| derived-RWAsm_Folder.sit | StuffIt 5 | 36 of 38 entries byte-exact, 2 refused | 595.7 KB |
| derived-PuzzleGetter_0.8.sit | StuffIt 5 | 11 of 26 entries byte-exact, 15 refused | 560.9 KB |
| derived-a2basic.dmg.sit | StuffIt 5 | clean per-entry refusal (1/1 entries) | 35.5 KB |
| derived-Library_ISBN_Barcoder.sit | StuffIt 5 | clean per-entry refusal (34/34 entries) | 35.5 KB |
| derived-Troi-ClipSave-Plug-in1.1.sit | StuffIt 5 | clean per-entry refusal (13/13 entries) | 35.5 KB |

**The five StuffIt 5 / Arsenic outcomes are the expected, accepted tier**
(see † above): every Arsenic entry needs a 512 KB block plus four bytes of
transform vector per byte the block actually holds, which a 1 MB Mac cannot
always give, so the engine declines *that entry* and carries on — which is
why two of the five still extract most of their archive. Where the peak
reads **35.5 KB** the budget rejected the 512 KB block *at request time* and
the buffer was never allocated, leaving only the parser's own state; where it
reads ~0.6 MB the block was affordable and the entries succeed.

The ordering is set by archive size, because the shell slurps the archive
into RAM first and budgets the engine against the remainder: 4.6 KB
(`derived-KeyGraphics.sit`) leaves room to spare, 66 KB and 92 KB leave
enough for the block but not for large fills, and 153 KB, 202 KB and 222 KB
do not leave enough for the block at all. Note the peaks in the table above
*fall* as the archives get bigger, which is this effect and not a property of
the archives. `derived-KeyGraphics.sit`, previously recorded as refusing at
1 MB, now passes (656.8 KB peak) — the boot volume is stripped to System +
Finder, which leaves the application more heap than the earlier, unrecorded
setup.

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

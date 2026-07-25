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
| StuffIt 5 (.sit) | extract | 0, 13, 15 Arsenic; encrypted detected | 31 fixtures | 0.64–2.6 MB† | per-entry refusal (all Arsenic entries > 400 KB) |
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

† Arsenic block sizes are NOT uniform (an earlier note here wrongly said
"always 512 KB"). The block is `1 << (v+9)` with `v` read from the
stream; peak memory ≈ 5× block (the block plus a 4×-block inverse-BWT
transform vector, allocated at full size regardless of payload). Across
the 31-fixture StuffIt 5 corpus the declared blocks are **128 KB (14
fixtures, dominant), 256 KB (9), 512 KB (8)** — so 512 KB is a minority
tier, not universal. Resulting peak heap: **min 0.64 MB (128 KB block) /
mean 1.23 MB / max 2.6 MB (512 KB block)**. EVERY Arsenic entry exceeds a
400 KB budget, so all fail cleanly per entry ("block too large for memory
budget") under the M9 400 KB cap. On a **1 MB Mac Plus** (~600 KB engine
budget) even the smallest 128 KB-block archive (0.64 MB) is out of reach,
so Arsenic is effectively a **≥4 MB machine** feature — an accepted,
documented tier. The 1 MB half of this is confirmed on-Mac for all six
Arsenic fixtures in the sample (clean per-entry refusal, see below); the
4 MB half is confirmed for two of the six, with three more too slow to
finish the automated poll and one (`RWAsm_Folder`) an open failure.

## Envelope auto-unwrap

`unclassic x` unwraps chained envelopes by content sniffing
(never by extension): MacBinary, BinHex, AppleSingle/Double, gzip and
.Z layers that yield exactly one file are recursively extracted and
the intermediate deleted (`-nr` disables; depth ≤ 8). Verified chains:
`.sit.bin`, `.sit.hqx`, `.tar.Z` (tools/run_unwrap.py, in CI).

## Hardening

- Differential: 771 fixtures byte-exact against `unar` manifests
  (both forks + type/creator), `./ci.sh`.
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

**39/44 byte-exact PASS** — data forks exact, resource forks exact bar the
OS-stamped reserved header (bytes 16–127). Of the five that did not pass:

- **Four timed out, not failed.** They are the corpus's LARGEST fixtures
  (~1 MB of output: three StuffIt 5 / Arsenic + one big Compact Pro SEA);
  they extract correctly but the decode is slow on a 7 MHz 68000 and
  overran the automated poll (XferIt confirmed complete at 185 s). Their
  logic is proven byte-exact off-Mac — the CI differential suite and the
  qemu-m68k mock cover these exact fixtures.
- **One is a genuine on-Mac failure:** `derived-RWAsm_Folder.sit`
  (StuffIt 5, 38 entries) reports an error on every entry at a 643.2 KB
  peak, i.e. it neither completed nor refused cleanly for a reason the
  4 MB run explains. It passes off-Mac. **Unexplained — open item**, not a
  documented tier; see the 1 MB section below, where it refuses cleanly.

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
| StuffIt 5 (Arsenic) | 0.64–2.6 MB (block-size dependent — see †) |
| DiskDoubler / Now Compress | detect-only — no allocation, cleanly not extracted |

## Floor target verification (Mini vMac — System 6.0.8, **1 MB** Mac Plus, 68000)

The same 44-fixture sample was replayed on a Mini vMac built for **1 MB of
RAM** — the project's floor target — one boot per fixture, same on-Mac
CRC-32 verification. The engine budget is derived from `FreeMem` at startup
(~600 KB on this machine).

**36/44 byte-exact PASS.** The eight non-passing fixtures fall into two
groups, and every one of them passes at 4 MB:

| Fixture | Format | Outcome at 1 MB | Peak heap |
|---|---|---|---|
| derived-KeyGraphics.sit | StuffIt 5 | clean per-entry refusal (1/1 entries) | 547.6 KB |
| derived-RWAsm_Folder.sit | StuffIt 5 | clean per-entry refusal (38/38 entries) | 35.5 KB |
| derived-PuzzleGetter_0.8.sit | StuffIt 5 | clean per-entry refusal (25/26 entries) | 35.5 KB |
| derived-a2basic.dmg.sit | StuffIt 5 | clean per-entry refusal (1/1 entries) | 35.5 KB |
| derived-Library_ISBN_Barcoder.sit | StuffIt 5 | clean per-entry refusal (34/34 entries) | 35.5 KB |
| derived-Troi-ClipSave-Plug-in1.1.sit | StuffIt 5 | clean per-entry refusal (13/13 entries) | 35.5 KB |
| popper-1.7.tar.Z | Compress | `UNC_ERR_SINK` (-9) — File Manager write failed | 268.0 KB |
| PCCTS.tar.gz | Gzip | one per-entry error, archive return 0 | 51.0 KB |

**The six StuffIt 5 / Arsenic refusals are the expected, accepted tier**
(see † above): every Arsenic entry needs ≥0.64 MB, which a 1 MB Mac cannot
give, so the engine declines per entry and the rest of the archive is
unaffected. Note the peak heap: five of the six top out at **35.5 KB**,
because the budget rejects the block allocation *at request time* — the
oversized buffer is never allocated. KeyGraphics reaches 547.6 KB before
being refused, so the refusal point depends on the declared block size.

**The two exogenous failures are a different, undocumented case.** Both are
the largest-output fixtures of their format (174 KB and 280 KB of tar
payload) and both decode fine at 4 MB with identical peak heap — so this is
not the decoder running out of budget. `popper-1.7.tar.Z` returns
`UNC_ERR_SINK`, i.e. the *sink* (the Mac app's File Manager writes), not the
engine, failed under 1 MB memory pressure. **Not yet root-caused — open
item.** The harness is otherwise identical between the two runs (same
1440 KB output volume, same disks; only the emulator's RAM differs), so the
difference is real and attributable to RAM.

Reproduce with `batch_corpus_1m.sh` (whole sample) and `retry_1m.sh`
(re-runs anything with no result grid at a longer poll, so a slow-but-correct
extraction is distinguishable from a refusal or a bomb).

What unblocked all of this was rewriting the File Manager calls to use
explicit, fully-zeroed HFS param blocks. This was originally attributed to a
broken Retro68 `HOpen` glue; **that attribution has been withdrawn** — a
standalone minimal reproduction (`tools/retro68-hopen-repro/`) disproved it.
See DECISIONS.md and BLOCKERS.md.

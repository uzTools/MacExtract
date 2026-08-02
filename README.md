# unclassic

*An open-source universal unarchiver for Classic Mac OS formats
(System 6 → Mac OS 9 era), engine-first.*

`libunclassic` is a portable, dependency-free C99 decompression engine
for the archive and encoding formats of the classic Macintosh world,
plus `unclassic`, a Linux CLI front end. Everything is developed and
validated on Linux by differential testing against The Unarchiver
(`unar`) — see [FORMATS.md](FORMATS.md) for the support matrix and
[TESTING.md](TESTING.md) for the methodology.

## Formats

Extracts: **MacBinary I/II/III**, **AppleSingle/AppleDouble**,
**BinHex 4** (.hqx), **PackIt** (.pit), **Compact Pro** (.cpt),
**StuffIt classic** (.sit, methods 0/1/2/3/5/8/13), **StuffIt 5**
(.sit, including method 15 "Arsenic"), **zip** (store/deflate),
**gzip**, **tar**, and **Unix compress** (.Z).
Detects and names (v1 does not extract): StuffIt X, DiskDoubler,
Now Compress, LZH.

Both forks are preserved (resource forks land in `<name>.rsrc`,
raw bytes), along with type/creator codes, Finder flags and dates in
listings. Nested envelopes — `.sit.hqx`, `.cpt.bin`, `.tar.Z` — are
detected by content (never by filename) and unwrapped automatically.

## Status — v0.3 (honest capability matrix)

| | Linux CLI | Mac app (System 6 → OS 9) |
|---|---|---|
| Extraction, all 12 formats | ✅ byte-exact vs `unar` (769 fixtures, both forks, in CI) | ✅ verified byte-exact on **System 6.0.8, System 7.0.1 and Mac OS 9.2**: 44/44 sampled fixtures at 4 MB on each of 6.0.8 and 7.0.1 (Mini vMac, a true 68000), 40/44 at 1 MB on 6.0.8, and 13/13 on OS 9.2 under the 68LC040 emulator — see the tier tables below |
| Both forks + type/creator/dates | ✅ | ✅ (resource fork exact bar the OS-stamped reserved header 16–127; extracted `APPL` launches by double-click) |
| Robustness (truncated/bit-flipped) | ✅ clean per-entry errors, no crash/hang/sanitizer trip | shares the same engine |
| Interactive UI | — | ✅ driven end to end on System 6: launched from the Finder → SFGetFile (Drive switches volumes) → progress dialog (Cancel / Cmd-.) → result alert; a cancel removes the partial output, and an extracted application launches by double-click |

### What runs on which machine

The 44-fixture sample in `tools/vmac/sample.txt` was replayed on-Mac
**twice**: once on a 4 MB Mac Plus and once on a **1 MB** Mac Plus, the
project's floor target. Both runs verify CRC-32 of both forks on the Mac
itself; both are reproducible with `tools/vmac/run.py`. Per format:

| Format | 4 MB | 1 MB Mac Plus | Engine peak heap |
|---|---|---|---|
| MacBinary I/II/III | ✅ 4/4 | ✅ 4/4 | 8 KB |
| BinHex 4 (.hqx) | ✅ 4/4 | ✅ 4/4 | 8 KB |
| Tar | ✅ 3/3 | ✅ 3/3 | 8 KB |
| PackIt (.pit) | ✅ 4/4 | ✅ 4/4 | 9 KB |
| Compact Pro (.cpt) | ✅ 4/4 | ✅ 4/4 | 19 KB |
| Zip | ✅ 3/3 | ✅ 3/3 | 12–65 KB |
| StuffIt classic (.sit) | ✅ 4/4 | ✅ 4/4 | 72–75 KB |
| Gzip | ✅ 3/3 | ✅ 3/3 | 51 KB |
| Unix compress (.Z) | ✅ 4/4 | ✅ 4/4 | 268 KB |
| DiskDoubler / Now Compress | ✅ detect-only | ✅ detect-only | none |
| **StuffIt 5 / Arsenic** | ✅ 6/6 | ⚠️ **2/6** | 0.6–1.8 MB |

**StuffIt 5 / Arsenic mostly wants a 4 MB machine.** Every real Arsenic
block is 512 KB, and an entry needs that block plus four bytes of
inverse-BWT transform vector for each byte the block actually holds — so
an entry costs 0.6 MB and up, rising with how much data it carries. At
1 MB the engine declines the entries it cannot afford — **per entry**,
leaving the rest of the archive alone — which is why two sampled fixtures
extract completely, three extract most of their entries, and only one
refuses everything. Where the budget rejects the block at request time
nothing is allocated at all (35.5 KB peak). This got better on 2026-08-02:
the shell used to read the whole archive into RAM before the engine was
given a budget, so a big archive starved it; now it reads from the file as
it goes and each archive gets its own size back.

**Output size does not cost the shell any RAM.** Each chunk is written
straight to the File Manager as the engine produces it, so a 1 MB machine
extracts a 287 KB file as happily as a 2 KB one — the only memory that
scales with the archive is the engine's own working set, listed above.
Everything here is byte-exact off-Mac and in CI as well.

The engine derives its memory budget from `FreeMem()` at runtime (and a
`SIZE` resource of 4 MB preferred / 400 KB minimum), so one binary adapts
from a Plus to a G3. Get the app onto a bare Mac with the bootstrap
distribution — `tools/make_dist.sh` builds an uncompressed MacBinary and an
800K disk image (a machine with no unarchiver can't open a `.sit`).

### Which systems this has actually run on

| System | What was run | Result |
|---|---|---|
| System 6.0.8, 4 MB | 44-fixture corpus + the interactive UI end to end | ✅ 44/44; UI driven from the Finder, extracted `APPL` launches |
| System 6.0.8, 1 MB | 44-fixture corpus | ✅ 40/44 — the 4 are StuffIt 5 budget refusals, and 3 of those now extract most of their entries |
| System 7.0.1, 4 MB | 44-fixture corpus | ✅ 44/44, same peak heap as 6.0.8 |
| System 7.0.1, 1 MB | boot probe | ⚠️ System 7 needs 2 MB and does not boot — not an application fault |
| Interactive UI above System 6 | — | ⚪ **out of scope by choice** — System 6 is the UI's target and it is driven end to end there; the paths the higher tiers exist for are tested directly, below |
| System 7.0.1 | the `SIZE` partition under the Process Manager | ✅ honoured — a 600 KB partition makes the engine decline an entry that needs 656 KB, cleanly; System 6 ignores `SIZE` and passes the same entry |
| System 6.0.8 + 7.0.1 | working-directory extraction (`SFReply.vRefNum` + `dirID` 0) | ✅ output lands in the working directory, nothing in the volume root |
| Mac OS 9.2, 512 MB (QEMU PowerPC, 68LC040 emulation) | 13-fixture format sample, launched from a real Finder | ✅ 13/13 byte-exact — both forks of 32 files compared **off the disk image**, names and folders included |
| Mac OS 9.2 | extraction onto an **HFS+** volume | ✅ 41 files byte-exact by CRC and length; every name as the 31-character rule predicts. That it really landed on HFS+ is measured, not inferred |
| Mac OS 9.2 | the `SIZE` partition under the Process Manager | ✅ a 600 KB partition makes the engine decline a 656 KB entry cleanly, peak heap 35.5 KB — the same as System 7.0.1, on a 512 MB machine |
| Mac OS 8 | — | ❌ **not run** (9.2 is the only system above 7 that has been) |

Everything above is **emulation**. No physical Macintosh has ever run this
binary: not a real Mac Plus at 1 MB, not an LC475 (68040), not an iMac G3.
Emulation is evidence, not proof. See [MANUAL_TESTS.md](MANUAL_TESTS.md) for
the full untested list.

**How long does it take on a real Mac Plus?** Measured at authentic 7 MHz
(Mini vMac 1x, System 6.0.8), eight fixtures across eight formats:

| Archive size | Extraction |
|---|---|
| a few KB (any format) | **under 5 s** |
| 278 KB StuffIt → 417 KB out | **~134 s** |
| 306 KB BinHex → 253 KB out | **~150 s** |

The machine itself takes ~10 s to boot into the application, so for small
archives the boot dominates and the extraction is barely noticeable. Per-format
figures and the relative decode costs are in [FORMATS.md](FORMATS.md);
Arsenic (StuffIt 5) is in a class of its own and mostly wants a 4 MB machine
anyway.

So the rule of thumb is: a few kilobytes is instant, a few hundred kilobytes is
two to three minutes. Nothing sampled behaves worse than that.

**Detect-only** (v1 names but does not extract): StuffIt X, DiskDoubler,
Now Compress, LZH, DiskCopy 4.2. **Out of scope (v1):** compression,
encrypted archives (detected → "unsupported, encrypted"), multi-segment
archives (detected), disk images.

## Building

```
make            # → build/unclassic
make test       # unit tests
./ci.sh         # the full matrix: ASan/UBSan/alignment, -m32, release
```

No dependencies beyond a C99 compiler. zlib 1.3.1 (inflate only) is
vendored in `third_party/`.

## Usage

```
unclassic l  archive.sit         # list (sizes, type/creator, names)
unclassic x  archive.sit         # extract (auto-unwraps envelopes; -nr disables)
unclassic t  archive.sit         # verify CRCs, write nothing
unclassic sniff mystery.bin      # name the format
   -o DIR         output directory
   --budget N     cap engine memory (simulate a small Mac)
   --raw-names    keep raw MacRoman bytes in filenames
   --stats        print allocator high-water mark
```

## Engine discipline

The engine targets a 68000 Mac Plus running System 6 in 1 MB of RAM
(the planned Toolbox shell wraps the same code unchanged through
Mac OS 9):

- no libc I/O or allocation — callers supply callbacks for everything;
- fully re-entrant, no global mutable state, no recursion,
  ≤ 4 KB call-chain stack depth;
- byte-wise big-endian access only (zero unaligned dereferences,
  enforced by `-fsanitize=alignment` in CI);
- single-pass streaming writes with a progress/yield callback every
  ≤ 16 KB of input;
- per-entry memory-budget failures, never per-archive;
- every size field sanity-capped before use; corrupt input produces
  clean per-entry errors (7,690 corruption variants + seeded fuzzing
  in CI).

## Provenance

Format knowledge is transcribed — never guessed — from XADMaster (The
Unarchiver's engine, LGPL), macutils, unpit, and Matthew T. Russotto's
Arsenic/SIT5 documentation, with source citations at every
transcription site. See [NOTICE](NOTICE); license:
**LGPL-2.1-or-later**.

The test corpus (hundreds of real archives from Info-Mac era mirrors)
is not committed; `fixtures/SOURCES.md` records the provenance and
SHA-256 of every fixture and `tools/harvest.py --restore` re-fetches
it. Oracle manifests (committed) pin the expected byte-exact output of
every entry. See [TESTING.md](TESTING.md).

## Repository map

```
include/unclassic.h   public API (UncIO/UncAlloc/UncSink callbacks)
src/                  engine: fmt_*.c per container, shared decoders
cli/main.c            Linux CLI
tests/, tools/        unit tests, differential/robustness/fuzz harnesses
reference/            read-only reference sources (repopulated by
                      tools/fetch_references.sh; never in the build)
third_party/zlib      vendored zlib 1.3.1 (inflate subset)
DECISIONS.md          engineering decision log
FORMATS.md            support matrix, peak memory, coverage
OPEN_ITEMS.md         what is missing, unverified, or out of scope
```

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

## Status — v0.1 (honest capability matrix)

| | Linux CLI | Mac app (System 6 → OS 9) |
|---|---|---|
| Extraction, all 12 formats | ✅ byte-exact vs `unar` (771 fixtures, both forks, in CI) | ✅ verified byte-exact **on real System 6.0.8 / 68000** (Mini vMac): 40/44 sampled fixtures across every format; the other 4 are the largest and merely slow on a 7 MHz 68000 |
| Both forks + type/creator/dates | ✅ | ✅ (resource fork exact bar the OS-stamped reserved header 16–127; extracted `APPL` launches by double-click) |
| Robustness (truncated/bit-flipped) | ✅ clean per-entry errors, no crash/hang/sanitizer trip | shares the same engine |
| Interactive UI | — | SFGetFile → progress dialog (Cancel / Cmd-.) → result alert; Cmd-. removes partial output |

On-Mac verification ran under Mini vMac configured as a **4 MB** Mac Plus.
By the measured per-fixture peak heap, it **runs on the 1 MB Mac Plus floor
target** for everything **except StuffIt 5 / Arsenic**, whose BWT blocks need
0.64–2.6 MB and so require a ~4 MB machine — they fail cleanly per entry on
1 MB rather than crashing (the M9 `--budget 400 KB` corpus run exercises that
refusal path). A real 1 MB-emulator pass is a manual test (MANUAL_TESTS.md).
The engine derives its memory budget from `FreeMem()` at runtime (and a
`SIZE` resource of 4 MB preferred / 400 KB minimum), so one binary adapts
from a Plus to a G3. Get the app onto a bare Mac with the bootstrap
distribution — `tools/make_dist.sh` builds an uncompressed MacBinary and an
800K disk image (a machine with no unarchiver can't open a `.sit`).

**Detect-only** (v1 names but does not extract): StuffIt X, DiskDoubler,
Now Compress, LZH. **Out of scope (v1):** compression, encrypted archives
(detected → "unsupported, encrypted"), multi-segment archives (detected),
disk images. DiskCopy 4.2 is named but not yet detected (no open reference).

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
  clean per-entry errors (7,710 corruption variants + seeded fuzzing
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
```

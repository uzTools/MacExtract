# OPEN_ITEMS.md — what is missing, and what is deliberately not

1. **Part 1, out of scope** — decided or impossible, recorded so nobody
   re-litigates it. Read it before starting work on a format.
2. **Part 2, open items** — what is not done or not verified, each with
   what would close it. A closed item moves out (lesson to DECISIONS.md,
   withdrawn claim to BLOCKERS.md, numbers to FORMATS.md).

Nothing here stops the engine or the CLI, which are byte-exact against the
oracle across 980 fixtures in `./ci.sh`.

**Filing something here is a decision to stop looking, so ask first.** Each
of these questions has emptied a row at least once (BLOCKERS.md, *Withdrawn
claims*):

- Is there an implementation that could be **fed** (DECISIONS.md, methods 3, 4 and 5)?
- Is *"X does not survive"* a claim about somebody's **search**?
- Does the search name the **right tool**?
- **Have you looked at all?**
- **Was the search by name?** An index of magic sees what one of names
  cannot (DECISIONS.md 2026-09-26, *the magic in somebody else's index*).
- **Is the corpus the claim was measured on the corpus that is here now?**

---

# Part 1 — Out of scope for v1

**Decided, or impossible. Not open.** "Out of scope" is today's answer, not a
refusal — the brief has grown before, on request.

## Out by the brief

| what | status | why it stays out |
|---|---|---|
| Compression | not implemented | this is an extractor |
| Get Info comments on a disk without a Desktop Manager — System 6 and 3.0 volumes (unless AppleShare's Desktop Mgr INIT is installed, DECISIONS.md 2026-10-21), floppies under System 7 | **not written; nothing says so** | the maintainer, 2026-10-17: a second write path on some Systems only (DECISIONS.md 2026-10-17, *the metadata, carried to the disk*) |
| Extracting onto an MFS disk | **out of scope, decided 2026-10-15; what happens is not documented** | a second write path (DECISIONS.md 2026-10-15, *the File Manager a 64K ROM has*) |
| Choosing which entries come out, in the Macintosh application | **not implemented; the CLI's `--only` ships** | decided 2026-09-26; branch `selective-extract` kept (DECISIONS.md 2026-09-26, *the feature that was parked, and is now out*) |
| Hardware decoding — FPU, coprocessor, NuBus card | **not implemented** | every codec is integer work; Arsenic's divides are 0.72 % of a run (DECISIONS.md 2026-09-23, *hardware decoding*) |
| The Macintosh 512K — 64 KB of ROM | **the interface runs; extraction needs HFS** | since 2026-10-16 it reaches Standard File; only a Hard Disk 20 supplies HFS, not run (FORMATS.md, *A true Macintosh 512K*; MANUAL_TESTS.md §6). A **128K** is out on the heap total (FORMATS.md, *A Macintosh 128K*) |
| StuffIt X (`.sitx`) | **not recognised** since 2026-10-18 | DECISIONS.md 2026-10-18, *the formats it only named* |
| PKWARE "strong encryption" (zip flag 0x40) | **named, refused per entry** | key material in a record nothing here parses; XADMaster refuses it too (FORMATS.md, *Encryption*) |
| Disk images (`.image`, `.img`, `.iso`, `.cdr`, `.toast`, `.dmg`, `.smi`), Disk Copy 4.2, DART | **not recognised** | a filesystem, not a codec; probes in `attic/`; DART left for MacMount 2026-09-25 (DECISIONS.md 2026-09-25, *the disk images that found another home*) |
| PMarc (`-pm0-`, `-pm1-`, `-pm2-`) and `-lhx-` | **not recognised** | another family behind an LZH-shaped header; neither reached a Macintosh |
| Self-extracting LZH | **not recognised** | nothing says where the first header is, unlike a zip (DECISIONS.md 2026-10-05, *the scan that was already being paid for*) |
| RAR, 7z, bzip2, xz, Cabinet, Zoo, ar/`.deb`, cpio, ARJ, Zstandard, lzip, lrzip, WIM, Apple Archive | **not recognised** since 2026-10-18 | not Macintosh formats (DECISIONS.md 2026-10-18, *the formats it only named*); held by `tools/run_foreign.py` (TESTING.md, *Archives this engine does not have*) |
| SuperDisk! method 13 | **not implemented, no specimen wanted** | its module refuses to decompress, so nothing could grade a decoder (FORMATS.md, *Module 13*) |
| A MIME part's `Content-MD5` | **not checked**; a `message/partial` anchor that is not a part comes out wrong with exit 0, as from munpack | priced at **+1,446 B** of `ovl_text`, declined 2026-10-11 (DECISIONS.md 2026-10-11, *the digest our own oracle could not compute*) |
| Zip64 past 4 GB | **counts and the per-entry escape read; over-4-GB fields refused** (`UNC_ERR_UNSUPPORTED` per archive, `UNC_ERR_TOOLARGE` per entry) | a format change, not a type change (DECISIONS.md 2026-08-28, *what a width costs*; FORMATS.md, *Size limits*) |

Nothing is detect-only since 2026-10-18: an unextractable file is
`UNC_FORMAT_UNKNOWN` (DECISIONS.md 2026-10-18, *the formats it only named*).

## Limits of the formats themselves

**What would change any of these: nothing in the format.**

- **An encrypted classic StuffIt archive without its resource fork cannot be
  decrypted by anything**: the password verifier is its `'MKey'` resource
  (FORMATS.md, *Encryption*). With the password, the archive IV is
  recoverable by a 2^32 search graded by the entries' CRCs (measured
  2026-10-13); not implemented.
- **A fat self-extracting StuffIt set's part 1 without its resource fork is
  refused** with *checksum mismatch*: its segment ends at the fork's `'endD'`
  (DECISIONS.md 2026-10-24, *the sum each part carries*). Two re-cuts, 128 B
  and 304 B resident, declined 2026-10-24 (DECISIONS.md, *the fork that was
  never downloaded*).
- **A fork compressed by a third-party StuffIt compressor module (method
  nibble 7) is not decodable**; none has surfaced. The engine names the
  module id and refuses the entry (FORMATS.md, *What an Optimizer did to the
  fork*).
- **A raw brotli stream cannot be identified**: RFC 7932 §9.1 has no magic.
- **A cut tar cannot be noticed**: no directory or length, and trailing zero
  blocks are not reliable (`derived-popper-1.7.tar` has none). Every other
  format notices a cut (`tools/run_truncation.py`).
- **One 46-byte window of a DiskDoubler DDA2 archive is ambiguous**: a cut
  there is a valid ending (DECISIONS.md 2026-08-29, *a cut archive*).
- **A uuencoded set missing a middle part decodes short, silently**; a
  missing last part is caught. `tools/run_uu.py` asserts this.

---

## The licence cannot move, and this is the irreducible core

**Measured and settled** (2026-09-19): five items have no permissive
statement anywhere, so LGPL-2.1 stays. **Do not re-price these.** The
per-file inventory is NOTICE's, checked by `tools/check_provenance.py`.

| what | why nothing replaces it |
|---|---|
| `unc_lzdyn.c` — `-lh2-` and `-lh3-` | lhasa implements neither; LHa for UNIX has its own licence (DECISIONS.md, *the 3,504 bytes that stay*) |
| `fmt_sit.c` — three rules of StuffIt method 8 | no specimen reaches them; deark leaves the method NULL (DECISIONS.md, *the layout Aladdin's own output settled*) |
| `unc_crypt.c` — StuffItDES's key schedule | reads all 64 key bits, so no standard schedule; graded against three StuffIt Deluxe 3.5.1 archives |
| `unc_lzah.c` — the `-lh1-`/method-5 window preload | the corpus cannot tell XADMaster's reading from lhasa's (DECISIONS.md 2026-09-28, *the preload nothing reaches*) |
| `src/sit14.c` — StuffIt 5's method 14 | libxad's `SIT_14` is the only implementation (FORMATS.md, *StuffIt 5's method 14*) |
| `fmt_arc.c` — Crunch 5/6/7 and Crush | no other implementation of 7 or Crush; **not taken, decided 2026-09-22** |
| five tolerances no specification supports — the MacBinary CRC-16/0xA001 fallback and its nonzero-date test, the byte-swapped AppleSingle header, the StuffIt split header, DiskDoubler's stored header CRC of zero | deark is a checked negative for all four; the two MacBinary ones are unexercised (933 fixtures, 9,330 variants, 2026-09-28); **kept, the maintainer's decision 2026-10-23** (DECISIONS.md 2026-10-23, *the probes next door*) |

---

# Part 2 — Open items

## A click during an extraction waits for the next progress callback

The menu bar is read only in the progress pump, so a click shorter than the
gap between callbacks is lost (DECISIONS.md 2026-10-12, *the application
nobody could leave*). **What is left is 4–6 s on a Mac Plus** for Now
Compress, Compact Pro and DiskDoubler, 2–2.5 s for StuffIt and Zip — 8 KB of
input at `UNC_PROGRESS_STEP` (FORMATS.md, *How long a click waits*).
**Halving the step is measured** (FORMATS.md, *What a 4 KB step buys*): gaps
down by a third to a half, 0 B, at most +0.4 % time. **The maintainer's to
decide** (CLAUDE.md says 8–16 KB); it needs the three stored-fork copies sized
by their own constant first. The LC 475's window was "not very reactive"
while extracting (2026-10-12, format not noted). Holding a menu down pauses
the extraction — inherent to `MenuSelect`.

## The metadata the archives hold and the readers drop

Every reader delivers what its format holds and the shell writes all of it
(DECISIONS.md 2026-10-17, *the metadata, carried to the disk*, *the archives'
own Finder info*), except what this table names. **Each needs its own source
or measurement before it is read.**

| format | stored, not read | oracle |
|---|---|---|
| MacBinary inside ZipIt and MacLHA | the Get Info comment, after both forks | none; none of 14 ZipIt payloads has one (2026-10-17); needs a second decode or a sink contract change, the maintainer's call |
| zip | ZipIt `0x2805`'s View word: one specimen, value 0 | ZipIt's own expander on a non-zero View |
| StuffIt 5 | a version-3 entry's Finder info; no version-3 entry here | Expander 5.5 on one |
| LZH | OS/2's 0x7f/0xff headers; a level 0/1 name's bytes after a NUL | `lsar`; no specimen of the second |
| tar | a pax `g` (global) header, stepped over | — |
| DiskDoubler `DDA2` records | bytes no reference assigns (folder +46..53, +62 on) | DiskDoubler Pro's own expander under emulation |
| AppleSingle entry 11 | ProDOS's access word | none; RFC 1740 gives its size, not its bits |

Closing a row: the reader delivers the field with a `Source:` and a grade,
and `tools/run_meta.py` holds it.

## Mac OS X's sidecars: what they hold and the engine does not read

`__MACOSX/…/._name` and tar `._name` sidecars are put back on their file
(DECISIONS.md, *the sidecars Mac OS X left beside the file*). Left, none with
a specimen:

- **A Spotlight comment past byte 1,024 of the sidecar**, or in a standalone
  `._name`, is dropped (DECISIONS.md 2026-10-18, *the comment Spotlight kept*).
- **A tar sidecar written after its file** comes out as itself; bsdtar never
  writes that order. A pax header between the two is stepped over, no
  specimen (hypothesis: bsdtar writes one for a non-ASCII name).

## Dates in the Macintosh's zone: what is not measured

Instants are written in the Mac's zone where it has one (DECISIONS.md
2026-10-17, *dates in the Macintosh's own zone*); gmtDelta includes summer
time, measured on Mac OS 9.2.2 and 7.6.1 on 2026-10-18 (DECISIONS.md
2026-10-18, *the format nobody reads*).

| what | status | what would close it |
|---|---|---|
| AppleSingle/AppleDouble by mpack, whose entry 8 is the writer's wall clock, not RFC 1740's GMT | **the maintainer's decision**: the RFC is followed, so such a file moves by the reader's offset | a rule to tell the writer apart, or a decision to treat entry 8 as wall clock |

## System 7.0.1 rewrites one byte of FXInfo

FXInfo +9 (`fdXFlags`) reads 0x70 on a System 7.0.1 output disk where the
shell wrote 0x00 (measured 2026-10-17, `tools/vmac/metarun.py`); 6.0.8 and 3.0
keep it. **Not `fdScript`, not the comment alone** (DECISIONS.md, *the comment
Spotlight kept*); the two that changed were both locked, so the lock is left
(hypothesis). Closes with a locked file and no comment, read back before the
Finder sees it.

## Hand-written 68000 assembly: candidates, held for one VM pass

**Not started, by decision (2026-10-09)**: collect the candidates, then
build, test and time them together in one pass. Every figure is an ESTIMATE
from the MC68000 timing table (DECISIONS.md 2026-10-09, *what GCC will not do
with an index*). The candidates are FORMATS.md's (*Hand-written 68000
assembly: the candidates, estimated*).

**Prerequisites for the pass:**

| what | why |
|---|---|
| **a `qemu-m68k` lane in `ci.sh`** running `run_crypt.py`, `run_privatefile.py`, the differential suite and a `UNC_ARS_FORCE_SAMPLED` build (build line: TESTING.md, *The 68000 profile*) | `ci.sh` runs x86, so nothing else would grade an assembly path |
| **a timing build that can open an encrypted archive**: the autotest app with a compile-time password beside `UNC_AT_TIMING` | the tick probe cannot reach any cipher today |

## Resident bytes that could leave before extraction

**Not started; each is its own change.** Sizes MEASURED 2026-10-22 at
17a025b (`nm -S` of `build/mac/MacExtract.code.bin.gdb`); every saving is a
HYPOTHESIS until read off the budget probe (FORMATS.md, *What the application
costs the engine*).

| what | resident | what would close it |
|---|---|---|
| segment joining: `unc_segment.c`, the five `fmt_*seg.c`, their shared parsers | 6,498 B of code | an image kept by the release for every set scheme; how much can move is not measured |
| the shell's set code (`SegAskUser`, `SegScanWrapped`, `SegPartOf`, …) | 3,166 B of code | needs Toolbox entries in the host vector first; not priced |
| the report window's buffers, `gRepBuf` and the row arrays | 8,730 B of bss, 1,568 B of code | a handle grown as lines arrive; `interactive.py` must still read the same box |
| the overlay shims, `mac/ovl_shim.c` | 2,462 B of code | ~25 dispatchers of one shape; a table might be a third of that |
| the relocator, `Retro68Relocate` and `Retro68ApplyRelocations` | 1,656 B of code | Elf2Mac places it at the start of `.text`; needs a layout Elf2Mac does not offer |

## Formats classic Mac programs wrote that nothing here opens — leads, not findings

From Macintosh Repository's *Compression & Archiving* category, read
2026-10-12 (`companion/harvest/macrepo-compression.tsv`). **Every row is from
a program's name and description; none has been held against a file.**

| format | programs there | here |
|---|---|---|
| ShrinkIt / NuFX (`.shk`, `.bxy`), Apple II | ShrinkIt | named nowhere |
| shell archives (`shar`) | unshar | named nowhere |
| yEnc | yEnc TZ | named nowhere |
| Apple Backup | Apple Backup Extractor | named nowhere |
| backup sets | Retrospect 1.x/2.1, Fastback, HFS Backup, MacBack, Network DiskFit, Diamond | named nowhere |
| splitters that may add a header | MacHacha, SplitIt!, SplitsVille, Split & Join, Split&Concat | plain `.001` and DiskDoubler `SPLT` only |
| unidentified | GIF Blast, MacSQZ!, The Parer, RadicalSqueeze, BKOS Compress, FileCrypt, Big Hairy Installer, MacToVax | format not known |

Closing a row: a specimen written by the program, then a second reader to
grade against.

## BinHex before 4.0: what is not graded

- **No `.hex` from any writer but BinHex 2.0.** BinHex 1.0 and the BASIC
  BinHexes wrote it too (`reference/notes/BinHex.md`); closes with a specimen.
- **`src/fmt_hecx.c` is hexbin's.** BinHex 2.0's own `CODE` (5.6 KB) is the
  writer, and reading the layout out of it is the route Packit III 1.3 gave
  PackIt's ciphers (NOTICE).

## The shell's own File Manager blocks, until multiversal's glue is inline

Switching to `HOpen`/`HOpenRF`/`HDelete` costs **+224 B** today (measured
2026-10-19; DECISIONS.md 2026-10-19, *the toolchain that inlined
PurgeSpace*), so the hand-built blocks stay. Closes when multiversal generates
File Manager glue inline (then about 0 B, hypothesis), proposed upstream
**after MacExtract's first public release** (the maintainer, 2026-10-19). The
seven glue routines linked today total 298 B (`FSRead` 58, `FSWrite` 58,
`SetFPos` 42, `GetEOF` 38, `SetEOF` 36, `FlushVol` 36, `FSClose` 30;
measured, `nm -S`).

## The double-click helpers: what is left before they ship

`companion/` works (DECISIONS.md 2026-10-12, *the stub that hands it on*) and
ships later, on MacExtract's own floppy. Left:

- **Which creators.** `companion/app-bundles.tsv` has 42; the list of stubs
  is not chosen. `TEXT` and `SITx` stay out.
- **A second double-click while MacExtract runs**, under MultiFinder and
  System 7. Not run.
- **Several archives of different creators opened together.** Not run.
- **Which of a file's two dates System 7 compares** between two applications
  of one creator. Not separated.
- **How StuffIt Expander 5.5 opens other formats through companion stubs**
  (its installer is `MacMountBench/5-Downloads/stuffit_expander_55.bin` on
  the share). Not examined.

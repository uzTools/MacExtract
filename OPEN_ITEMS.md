# OPEN_ITEMS.md — what is missing, and what is deliberately not

1. **Part 1, out of scope** — decided or impossible, recorded so nobody
   re-litigates it. Read it before starting work on a format.
2. **Part 2, open items** — what is not done or not verified, each with
   what would close it. A closed item moves out (lesson to DECISIONS.md,
   withdrawn claim to BLOCKERS.md, numbers to FORMATS.md).

Nothing here stops the engine or the CLI, which are byte-exact against the
oracle across 988 fixtures in `./ci.sh`.

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
| Invisible folders in the Open dialogs (`Move&Rename`, `TheVolumeSettingsFolder`) | **listed; invisible files are not** since v0.45.0 | Standard File's Open does not pass folders to the file filter (measured on Mac OS 9.2); only System 7's CustomGetFile does, and one dialog serves every System (DECISIONS.md 2026-11-02, *the dialogs that became the application*) |
| A split or spanned-zip part renamed on a floppy | **ejected with the wrong disks** since v0.45.0 | the maintainer's call, one drive in mind: found once copied off the floppy (DECISIONS.md 2026-10-31, *the disk Standard File took first*) |
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
| More archives opened in a quick burst while MacExtract is busy — a second double-click during a helper's stay, archives of several creators at once | **dropped silently** (two `SIT!` archives 2 s apart: both lost, 7.0.1, one run; several creators: not run) | the maintainer, 2026-11-02: a limitation of the application. One more archive at a time is queued: File > Open... on every System, a double-click under MultiFinder and System 7 (DECISIONS.md 2026-11-01, *the Open item MultiFinder looks for*) |

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

# Part 2 — Open items

## Leaving XADMaster: the original programs as the oracle, and the licence

**Reopened by the maintainer 2026-11-06**, after *the licence cannot
move* had been settled on 2026-09-19: XADMaster stops being the yardstick
and the source. Two items. The first changes what grades a fork and does
not move the licence; only the second does.

### What grades a fork

`unar` 1.10.8 grades most of the 988 fixtures' manifests; `macunpack` and
deark grade the forks it fails (TESTING.md, *The oracle*). The writers' own
readers already grade StuffIt Deluxe 2.0.1's output, SuperDisk!'s modules,
DiskDoubler's methods 3–5, Now Compress, Private File, AppleLink packages
and the Finder metadata each expander puts back (TESTING.md; FORMATS.md).

- **Not counted:** per format, how many forks only `unar` grades, and
  which format's writer has a copy on this machine. Closes with that
  inventory; it runs nothing.
- **Not decided:** which answer wins where the writer's own reader
  disagrees with the stored CRC or with another reader — StuffIt Deluxe
  7.0.3 Classic writes wrong bytes for zip's Reduce (README.md).
- **Then per format:** its manifests re-recorded with the writer's own
  reader in `oracle`, one emulator at a time, each run under two hours; a
  writer this machine has no copy of goes to MANUAL_TESTS.md.

### What still holds the licence

LGPL-2.1-or-later, through the 17 files `tools/check_provenance.py` lists
as `CARRIES`: 11 owe XADMaster, 4 owe libxad, the Amiga library
XADMaster carries them from (`unc_lzdyn.c`, `fmt_sit.c`, `sit14.c`,
`fmt_dd.c`; same licence), and `fmt_hecx.c` and `fmt_binhex_probe.c`
owe macutils' hexbin, whose README puts "some parts" under the GNU licence
(NOTICE). **A re-citation does not close a row**: the code has to be our
own, written from facts this project established — a published
description, the original program's behaviour on chosen input, or its own
code read as BinHex 2.0's and Packit III's were (NOTICE) — and the file
moves to `HISTORICAL` in the same commit.

| what | known | what would close it |
|---|---|---|
| `unc_lzdyn.c` — `-lh2-` and `-lh3-`, libxad's | lhasa implements neither; LHa for UNIX has its own licence (DECISIONS.md, *the 3,504 bytes that stay*) | a description written from what the original DOS LHA emits under DOSBox |
| `fmt_sit.c` — three rules of StuffIt method 8, libxad's | no specimen reaches them; deark leaves the method NULL (DECISIONS.md, *the layout Aladdin's own output settled*) | StuffIt made to reach them as an encoder, or shown not to and the rules deleted |
| `fmt_sit5.c` — the encrypted header's bit 5 | nothing here sets it | a StuffIt 5 archive that sets it, or the rule deleted |
| `unc_crypt.c` — StuffItDES's key schedule, StuffIt 5's hash, ARC's garble | the schedule reads all 64 key bits, so no standard one; graded against three StuffIt Deluxe 3.5.1 archives | the encryptor's own `DCMP` (512 + id) called as `tools/sdmodule/` calls SuperDisk!'s modules; the other two not looked at |
| `unc_lzah.c`, `unc_internal.h` — the `-lh1-`/method-5 window preload | the corpus cannot tell XADMaster's reading from lhasa's (DECISIONS.md 2026-09-28, *the preload nothing reaches*) | a writer's specimen that tells the two readings apart |
| `src/sit14.c` — StuffIt 5's method 14, libxad's | libxad's `SIT_14` is the only implementation (FORMATS.md, *StuffIt 5's method 14*) | a description written from StuffIt 5's own engine; the largest row, not priced |
| `fmt_arc.c` — Crunch 5/6/7, Crush, the method numbers | no other implementation of 7 or Crush; not taken 2026-09-22 | the DOS originals as encoders, and a description |
| `fmt_dd.c` — the DDAR 0x20 raw-fork shape, libxad's | — | DiskDoubler's own expander on a fork of that shape |
| `fmt_sitseg.c`, `fmt_sitseg_probe.c` — the StuffIt split header | Aladdin never published it; nothing else in `reference/` reads it (NOTICE) | its offsets measured off sets StuffIt cuts, as the B0 56 bytes were |
| `unc_sidecar.c` — which names are Mac OS X sidecars, and the pairing rule | — | not looked for |
| five tolerances no specification supports — the MacBinary CRC-16/0xA001 fallback and its nonzero-date test, the byte-swapped AppleSingle header, DiskDoubler's stored header CRC of zero (with the split header above) | deark is a checked negative for all four; the two MacBinary ones are unexercised; kept, the maintainer's decision 2026-10-23 (DECISIONS.md 2026-10-23, *the probes next door*) | the writer that made such files, or the tolerance dropped |
| `fmt_hecx.c`, `fmt_binhex_probe.c` — hexbin's | *BinHex before 4.0*, below | BinHex 2.0's own `CODE`, as that item says |

**The maintainer's, not this file's:** whether the 20 `HISTORICAL` files —
transcribed once, rewritten from descriptions since — count as clean, and
which licence follows.

## A click during an extraction waits for the next progress callback

Events are read only in the progress pump, so a click or Cmd-. waits for the
next callback, and a click on the menu bar shorter than the gap is lost
(DECISIONS.md 2026-10-12, *the application nobody could leave*). A press on
Cancel is decided by where it was released (2026-11-06, *the tap the pump
read too late*). **What is left at the 1 KB step is 6.1 s on a Mac Plus**
for Now Compress, whose 32 KB block no step reaches, and 1–2 s for Compact
Pro, DiskDoubler, StuffIt, Zip and gzip (FORMATS.md, *How long a click
waits*; *What the step costs*, 2026-11-06). The LC 475's window was "not very reactive"
while extracting (2026-10-12, format not noted). Holding a menu down pauses
the extraction — inherent to `MenuSelect`.

## A later archive's destination dialog opens where Standard File last was

After File > Open... or a part dialog answered on a floppy, the next archive
the Finder handed over extracts onto that floppy unless the user moves the
dialog (measured, System 3.0 and 6.0.8; DECISIONS.md 2026-11-05, *the dialog where Standard File last was*).
**What would close it:** pointing the dialog at the archive's folder in a way
that keeps System 3.0's first dialog where it is with a second disk
mounted; the two versions measured cost 32 and 80 B and failed that, or
fixed only half. `relaunch.py --queue` and `--first-set` show it.

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

**`-lh1-` (StuffIt method 5, LZH, ARC Trimmed), from MacMount's comparison
(2026-11-01).** All three are C, so none waits for the VM pass. Each closes
when the tick probe times it on a method-5 or `-lh1-` fixture and the
overlay images' sizes are re-taken.

| what | evidence |
|---|---|
| **the tree walk with the bit reader inside it, no call in the loop**: bits left-aligned in a register, each a test of bit 7 and a shift by one | MEASURED by MacMount on the same tree: ~150 → ~106 cycles a level read off its listing, and 6.1 → 3.9 minutes for a disk at Mini vMac 1x (macmount VERIFIED.md, *The decoders rewritten*). Ours: 230 instructions an output byte against its 178 (its harness, not our flags). An inline fast path with an out-of-line refill measured 3.1–6.6 % WORSE here (DECISIONS.md 2026-08-24); FORMATS.md, *Suggestions* (the header's "inline" helpers) |
| **the update scan on the `0xFFFF` sentinel** | FORMATS.md's row *`-lh1-`'s tree-update search* |
| **match copies in pieces that do not wrap** | FORMATS.md's row *The masked match copies* (`unc_lzah.c` named, not counted) |

**Not taken from it:** a separate output ring (+2 KB peak per entry), and
16-bit node indices (CLAUDE.md, 68000 discipline: 32-bit arithmetic in hot
paths).

## Resident bytes that could leave before extraction

**Not started; each is its own change.** Sizes MEASURED 2026-10-22 at
17a025b (`nm -S` of `build/mac/MacExtract.code.bin.gdb`); every saving is a
HYPOTHESIS until read off the budget probe (FORMATS.md, *What the application
costs the engine*).

| what | resident | what would close it |
|---|---|---|
| segment joining: `unc_segment.c`, the five `fmt_*seg.c`, their shared parsers | 6,498 B of code | an image kept by the release for every set scheme; how much can move is not measured |
| the shell's set code (`SegAskUser`, `SegPartOf`, the part dialog's scans) | 3,166 B of code on 2026-10-22, not re-measured since the setup half (`SegScanWrapped` and the rest of `mac/seg_setup.inc.c`) left as `ovl_segsetup` in v0.45.0 | the same table of function pointers the setup image is given (DECISIONS.md 2026-11-02, *the dialogs that became the application*); not priced |
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

## MAR: what is not read or not run

- **An LZ4 frame's 64 KB ring is allocated whole**, 69,816 B of heap
  whatever the payload: an LZ4 frame of anything the peek cannot name keeps
  the whole bundle and is refused on System 6.0.8 at 512 KB, 2,930 B short
  (DECISIONS.md 2026-11-04, *the frame mar 0.2.0 reads*). Closes with a ring
  that grows with the output, priced against that refusal.

## The shell's own File Manager blocks, until multiversal's glue is inline

Switching to `HOpen`/`HOpenRF`/`HDelete` costs **+224 B** today (measured
2026-10-19; DECISIONS.md 2026-10-19, *the toolchain that inlined
PurgeSpace*), so the hand-built blocks stay. Closes when multiversal generates
File Manager glue inline (then about 0 B, hypothesis), proposed upstream
**after MacExtract's first public release** (the maintainer, 2026-10-19). The
seven glue routines linked today total 298 B (`FSRead` 58, `FSWrite` 58,
`SetFPos` 42, `GetEOF` 38, `SetEOF` 36, `FlushVol` 36, `FSClose` 30;
measured, `nm -S`).

## The double-click helpers: what is left

`companion/` works (DECISIONS.md 2026-10-11, *the stub that hands it on*);
its sixteen helpers are in `dist/` and on both disk images since
2026-11-04, in no release yet (DECISIONS.md 2026-11-04, *the helpers in
dist*). Left:

- **Which of a file's two dates System 7 compares** between two applications
  of one creator. Not separated.
- **The stub's reclaim on System 7.x, 6 and 3.0.** On Mac OS 9 a helper
  opened by itself takes its creator back from StuffIt Expander
  (DECISIONS.md 2026-10-31, *the stub that sorts*); System 7.x and the
  stub's alert on Systems without a desktop database are not run.
- **MacExtract as Internet Config's post-processor — under consideration,
  the maintainer, 2026-11-03.** It is what would extract a download
  without a double-click; the helpers do not do it, Expander stays the
  post-processor. `companion/icsetup`, which set it up (and stamped
  downloads as MacExtract's) and measured working on Mac OS 9.2 only, is
  retired from the tree and kept at 9e149a5 (DECISIONS.md 2026-10-31, *the
  hand-off that arrives once*). Not run: System 7.x with an Internet Config
  extension, a real browser download, and a download finishing while
  MacExtract extracts, which the hand-off of 2026-11-01 suggests may now
  queue (DECISIONS.md 2026-11-01, *the Open item MultiFinder looks for*;
  *hypothesis*).

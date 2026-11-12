# OPEN_ITEMS.md — what is missing, and what is deliberately not

1. **Part 1, out of scope** — decided or impossible, recorded so nobody
   re-litigates it. Read it before starting work on a format.
2. **Part 2, open items** — what is not done or not verified, each with
   what would close it. A closed item moves out (lesson to DECISIONS.md,
   withdrawn claim to BLOCKERS.md, numbers to FORMATS.md).

Nothing here stops the engine or the CLI, which are byte-exact against the
oracle across 1,018 fixtures in `./ci.sh`.

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

# Part 1 — Out of scope

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
| The Macintosh 512K — 64 KB of ROM — without a Hard Disk 20 | **runs, cannot extract** | no HFS to write to (DECISIONS.md 2026-10-15); with the `Hard Disk 20` file it extracts under emulation, and a real one is MANUAL_TESTS.md §6 (FORMATS.md, *A true Macintosh 512K*). A **128K** is out on the heap total (FORMATS.md, *A Macintosh 128K*) |
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
| The report window's 6,539 B of fixed buffers (`gRepBuf` and the row arrays) | **kept** | the maintainer, 2026-11-08: until something needs the bytes; neither 512 KB refusal is within them (DECISIONS.md 2026-11-08, *the report pool that stays*) |
| A read error while the format is still being found | **"not a recognized archive"**, not "read error" (`mac_sink_test --ioerr` on `derived-MUSFMT10.ZIP`) | the maintainer, 2026-11-08: a bad sector is a corrupt archive, and either way only a good copy helps (DECISIONS.md 2026-11-07, *the read error that read as end of file*) |
| The wait before the first callback — up to 2.8 s (BinHex) and 1.0 s (Tar) on a Mac Plus, 1.0 s or less elsewhere | **accepted** since 2026-11-08 | the maintainer: initial loading time is fine where the scan is needed. It is: the zip pair's walk of a file's last 64 KB is what finds a zip behind other bytes, and the text and tar probes sit after it so they cannot take one (DECISIONS.md 2026-11-08, *the scan made twice*; FORMATS.md, *How long a click waits*) |
| MacExtract as Internet Config's post-processor, so a download is extracted without a double-click | **out of scope** since 2026-11-09; `companion/icsetup`, which set it up on Mac OS 9.2, is kept at 9e149a5 | the maintainer: Internet Config says only whether and by whom a download is post-processed, not where it goes or whether the archive is deleted, which are the post-processor's own preferences, and MacExtract has none (DECISIONS.md 2026-11-09, *the helper Internet Config would call*). A download reaching MacExtract through the `SITx` helper where Expander is absent would be welcome, not pursued (not measured) |
| A click during an extraction waiting for the next progress callback — 1–2 s on a Mac Plus for most formats at the 1 KB step; a short click on the menu bar lost; a menu held down pausing the extraction | **accepted** | the maintainer, 2026-11-06: input is queued and Cancel flashes when it is taken; the window's lack of responsiveness is known and the user is warned (DECISIONS.md 2026-11-06, *the step a click waits for*); the wait before the first callback is the row above |

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
- **An mpack AppleSingle/AppleDouble's dates land shifted by the Mac's zone
  offset**: mpack stores the wall clock in entry 8, which RFC 1740 makes GMT,
  and nothing in the file names its writer. The RFC is followed, decided
  2026-11-08 (DECISIONS.md 2026-10-17, *dates in the Macintosh's own zone*).

---

# Part 2 — Open items

## Leaving XADMaster: the original programs as the oracle, and the licence

**Reopened by the maintainer 2026-11-06**, after *the licence cannot
move* had been settled on 2026-09-19: XADMaster stops being the yardstick
and the source. Two items. The first changes what grades a fork and does
not move the licence; only the second does.

### What grades a fork

`unar` 1.10.8 grades most of the 1,018 fixtures' manifests; `macunpack` and
deark grade the forks it fails (TESTING.md, *The oracle*). The writers' own
readers already grade StuffIt Deluxe 2.0.1's output, SuperDisk!'s modules,
DiskDoubler's methods 3–5, Now Compress, Private File, AppleLink packages
and the Finder metadata each expander puts back; StuffIt Expander 4.0.2, both
forks of classic StuffIt and Compact Pro (TESTING.md; FORMATS.md).

- **Counted** 2026-11-08 (TESTING.md, *What `unar` alone vouches for, per
  format*): now 2,662 of 7,633 forks have `unar` as their sole oracle, the
  largest block StuffIt 5's 820 — with a reader on this machine (Expander
  5.5), so none goes to MANUAL_TESTS.md. No writer is missing for any format
  with committed fixtures.
- **Then per format:** its manifests re-recorded with the writer's own
  reader in `oracle`, one emulator at a time, each run under two hours; a
  writer this machine has no copy of goes to MANUAL_TESTS.md. Where that
  reader disagrees with the stored CRC or another reader, each case is
  decided on its own (DECISIONS.md 2026-11-08, *the reader that disagrees*).

### What still holds the licence

LGPL-2.1-or-later, through the four files that hold transcribed code
(`CODE` in `tools/check_provenance.py`, **code** below). The other rows are
facts read in somebody else's code, 0BSD already, and stay listed because
leaving XADMaster is about where the knowledge came from (DECISIONS.md
2026-11-08, *the code we wrote*). Of the 16 `CARRIES` files, 10 owe
XADMaster, 4 owe libxad, the Amiga library XADMaster carries them from
(`unc_lzdyn.c`, `fmt_sit.c`, `sit14.c`, `fmt_dd.c`; same licence), and
`fmt_hecx.c` and `fmt_binhex_probe.c` owe macutils' hexbin, whose README
puts "some parts" under the GNU licence (NOTICE). **A re-citation does not
close a row**: the code has to be our own, written from facts this project
established — a published description, the original program's behaviour on
chosen input, or its own code read as BinHex 2.0's and Packit III's were
(NOTICE) — and the file moves to `HISTORICAL`, and out of `CODE` with its
SPDX line, in the same commit.

| what | known | what would close it |
|---|---|---|
| `unc_lzdyn.c` — `-lh2-` and `-lh3-`, libxad's, **code** | lhasa implements neither; LHa for UNIX has its own licence (DECISIONS.md, *the 3,504 bytes that stay*) | a description written from what the original DOS LHA emits under DOSBox |
| `fmt_sit.c` — three rules of StuffIt method 8, libxad's | no specimen reaches them; deark leaves the method NULL (DECISIONS.md, *the layout Aladdin's own output settled*) | StuffIt made to reach them as an encoder, or shown not to and the rules deleted |
| `unc_lzah.c`, `unc_internal.h` — the `-lh1-`/method-5 window preload | the corpus cannot tell XADMaster's reading from lhasa's (DECISIONS.md 2026-09-28, *the preload nothing reaches*) | a writer's specimen that tells the two readings apart |
| `src/sit14.c` — StuffIt 5's method 14, libxad's, **code** | libxad's `SIT_14` is the only implementation (FORMATS.md, *StuffIt 5's method 14*) | a description written from StuffIt 5's own engine; the largest row, not priced |
| `fmt_arc.c` — Crunch 5/6/7, Crush, the method numbers, **code** | no other implementation of 7 or Crush; not taken 2026-09-22 | the DOS originals as encoders, and a description |
| `fmt_dd.c` — the per-method rules, and the DDAR 0x20 raw-fork shape, libxad's, facts | methods 2, 5 and 7's codecs left 2026-11-09 for DiskDoubler 3.1.2's own decoders (`docs/formats/diskdoubler-splay-stac.md`; DECISIONS.md 2026-11-09, *the decoders DiskDoubler shipped*) | DiskDoubler's own expander on a fork of the 0x20 shape |
| `fmt_sitseg.c`, `fmt_sitseg_probe.c` — the StuffIt split header | Aladdin never published it; nothing else in `reference/` reads it (NOTICE) | its offsets measured off sets StuffIt cuts, as the B0 56 bytes were |
| `unc_sidecar.c` — which names are Mac OS X sidecars, and the pairing rule | — | not looked for |
| `unc_segment.c` — the part names of a spanned zip (`NAME.zNN`, `NAME.zip` last) and a `.NNN` split, since 2026-11-08 | facts, not code (NOTICE) | not looked for |
| five tolerances no specification supports — the MacBinary CRC-16/0xA001 fallback and its nonzero-date test, the byte-swapped AppleSingle header, DiskDoubler's stored header CRC of zero (with the split header above) | deark is a checked negative for all four; the two MacBinary ones are unexercised; kept, the maintainer's decision 2026-10-23 (DECISIONS.md 2026-10-23, *the probes next door*) | the writer that made such files, or the tolerance dropped |
| `fmt_hecx.c` (**code**), `fmt_binhex_probe.c` — hexbin's | *BinHex before 4.0*, below | BinHex 2.0's own `CODE`, as that item says |

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
| MacBinary inside MacLHA | the Get Info comment, after both forks | none; ZipIt 1.4 writes none even for a file that has one (2026-11-06); needs a second decode or a sink contract change, the maintainer's call |
| StuffIt 5 | a version-3 entry's Finder info; no version-3 entry here | Expander 5.5 on one |
| LZH | OS/2's 0x7f/0xff headers; a level 0/1 name's bytes after a NUL | `lsar`; no specimen of the second |
| AppleSingle entry 11 | ProDOS's access word | none; RFC 1740 gives its size, not its bits |

Closing a row: the reader delivers the field with a `Source:` and a grade,
and `tools/run_meta.py` holds it.

## Mac OS X's sidecars: what they hold and the engine does not read

`__MACOSX/…/._name` and tar `._name` sidecars are put back on their file
(DECISIONS.md, *the sidecars Mac OS X left beside the file*). Left, none with
a specimen:

- **A Spotlight comment whose property list or string header starts past
  byte 1,024 of the sidecar**, or in a standalone `._name`, is dropped; one
  that starts inside and runs past is cut and reported (DECISIONS.md
  2026-11-07, *the comment the Desktop Manager cut*).
- **A tar sidecar written after its file** comes out as itself; bsdtar never
  writes that order. A pax header between the two is stepped over, no
  specimen (hypothesis: bsdtar writes one for a non-ASCII name).

## Hand-written 68000 assembly: candidates, held for one VM pass

**Not started, by decision (2026-10-09)**: collect the candidates, then
build, test and time them together in one pass. Every figure is an ESTIMATE
from the MC68000 timing table (DECISIONS.md 2026-10-09, *what GCC will not do
with an index*). The candidates are FORMATS.md's (*Hand-written 68000
assembly: the candidates, estimated*).

**Prerequisites for the pass:**

| what | why |
|---|---|
| **a `qemu-m68k` lane in `ci.sh`** running `run_crypt.py`, `run_privatefile.py`, the differential suite and a `UNC_ARS_FORCE_SAMPLED` build (build line: TESTING.md, *The 68000 profile*) | `ci.sh` runs x86, so nothing else would grade an assembly path. **The StuffIt 5 part exists since 2026-11-10** (TESTING.md, *Arsenic's divu, under qemu-m68k*), with the one instruction asked for outside the pass, Arsenic's `divu.w` (DECISIONS.md 2026-11-10, *the division libgcc was asked to do*) |
| **a timing build that can open an encrypted archive**: the autotest app with a compile-time password beside `UNC_AT_TIMING` | the tick probe cannot reach any cipher today |

**`-lh1-` (StuffIt method 5, LZH, ARC Trimmed), from MacMount's comparison
(2026-11-01).** Both are C, so neither waits for the VM pass. Each closes
when the tick probe times it on a method-5 or `-lh1-` fixture and the
overlay images' sizes are re-taken.

| what | evidence |
|---|---|
| **the tree walk with the bit reader inside it, no call in the loop**: bits left-aligned in a register, each a test of bit 7 and a shift by one | MEASURED by MacMount on the same tree: ~150 → ~106 cycles a level read off its listing, and 6.1 → 3.9 minutes for a disk at Mini vMac 1x (macmount VERIFIED.md, *The decoders rewritten*). Ours: 230 instructions an output byte against its 178 (its harness, not our flags). The CALL left the loop on 2026-11-09, `unc_bitin_bit` forced inline: method 5 −21 % of Plus engine ticks (FORMATS.md, *Inlining the shared readers*); what is left is the left-aligned register form |
| **the update scan on the `0xFFFF` sentinel** | FORMATS.md's row *`-lh1-`'s tree-update search* |

**Not taken from it:** a separate output ring (+2 KB peak per entry), and
16-bit node indices (CLAUDE.md, 68000 discipline: 32-bit arithmetic in hot
paths).

## Where a `.sit.hqx`'s time goes on a Plus: two costs not located

**Filed by the maintainer 2026-11-10.** Both MEASURED on one archive only,
`macburger-helper.hqx` (312 entries) on `mv-4M-1x`; the causes are
HYPOTHESES.

| what | evidence | what would close it |
|---|---|---|
| **`ovl_keep`'s `high_handle` on a 128K ROM: 9.6 s** | `MoveHHi` put back on today's tree: 223.6 → 213.8 s, twice (DECISIONS.md 2026-11-10, *the 12.8 seconds that were three commits*). The call runs a few times a run, so where it leaves the block is the hypothesis, about 30 ms an entry. Not measured: other archives, the 1 MB tier, the 64K ROM | an archive of few large entries and one of many small ones timed both ways, to say whether it scales per entry; a heap dump after `ovl_keep` both ways. Then either `high_handle` places the block where `MoveHHi` would (0 resident B), or the ROM test comes back (32 B off every budget) |
| **create, `SetEOF`, close, `FlushVol` and catalog: 80 s** | 4,785 of 11,772 ticks, about 15 an entry, against the engine's 6,745 (FORMATS.md, *Where `macburger-helper.hqx`'s StuffIt layer goes*). Expander does no `FlushVol` (FORMATS.md, *Our figures include a `FlushVol`*) | the tick probe splitting the five calls, then whether the `FlushVol` after every fork is what costs |

## Resident bytes that could leave before extraction

**Not started; each is its own change.** Sizes MEASURED 2026-10-22 at
17a025b, the first row's 2026-11-09 (`nm -S` of
`build/mac/MacExtract.code.bin.gdb`); every saving is a
HYPOTHESIS until read off the budget probe (FORMATS.md, *What the application
costs the engine*).

| what | resident | what would close it |
|---|---|---|
| segment joining: the joiner (`unc_segment.c`), the schemes' join hooks and readers, their parsers, the shims to `src/unc_segid.c` | 6,788 B of code on 2026-11-09, after describe and match left for `ovl_sniff` and `ovl_cptdd` (−1,584 B; DECISIONS.md 2026-11-09, *the set's identity that left*) | the joiner is read while a Compact Pro or spanned-zip set is, which keep only their readers' images, so it stays; the hooks only bundle-keeping schemes call (MIME's header walk 1,840 B, `SPLT`'s 772 B, StuffIt's emit 578 B) could go to an image, not priced |
| the shell's set code (`SegAskUser`, `SegPartOf`, the part dialog's scans) | 3,166 B of code on 2026-10-22, not re-measured since the setup half (`SegScanWrapped` and the rest of `mac/seg_setup.inc.c`) left as `ovl_segsetup` in v0.45.0 | the same table of function pointers the setup image is given (DECISIONS.md 2026-11-02, *the dialogs that became the application*); not priced |
| the relocator, `Retro68Relocate` and `Retro68ApplyRelocations` | 1,656 B of code | Elf2Mac places it at the start of `.text`; needs a layout Elf2Mac does not offer |

## One registration per format

A format's decoder is its own files and image, but registering it is a
row in each of up to seven tables: the enum (`include/macextract.h`),
`unc_formats`, the sniffer's probe order, `seg_schemes` and the match code
for a set scheme, `gRun`, the release plan, and the overlay image list,
with the budget constants moving after. Installer VISE's two commits
(700fb893, 1b6042e7) touched about 80 files; removing it, asked by the
maintainer on 2026-11-12, has to find every row by hand.
`tools/check_ovl_rows.py` already cross-checks two of the tables. What
would close it: one descriptor per format (name, probe and its place in
the sniff order, extractor, image, keep set, set scheme), from which the
build generates the rest, so a format is its files and one row; after the
resident per-format tables change lands, since it rewrites the same
tables.

## Formats classic Mac programs wrote that nothing here opens — leads, not findings

From Macintosh Repository's *Compression & Archiving* category, read
2026-10-12 (`companion/harvest/macrepo-compression.tsv`). **Every row is from
a program's name and description; none has been held against a file.**

| format | programs there | here |
|---|---|---|
| ShrinkIt / NuFX (`.shk`, `.bxy`), Apple II | ShrinkIt | named nowhere |
| shell archives (`shar`) | unshar | named nowhere |
| yEnc | yEnc TZ | named nowhere |
| backup sets | Retrospect 1.x/2.1, Fastback, HFS Backup, MacBack, Network DiskFit, Diamond | named nowhere |
| splitters that may add a header | MacHacha, SplitIt!, SplitsVille, Split & Join, Split&Concat | plain `.001` and DiskDoubler `SPLT` only |
| unidentified | GIF Blast, MacSQZ!, The Parer, RadicalSqueeze, BKOS Compress, FileCrypt, Big Hairy Installer, MacToVax | format not known |

Closing a row: a specimen written by the program, then a second reader to
grade against.

## Types MacExtract's bundle does not claim: Expander's, and real files'

Two sources, compared on 2026-11-12 with MacExtract's 51 `FREF`s (read off
`dist/MacExtract.bin`): StuffIt Expander 5.5's `'open'` 128 and its three
bundles (read off its resource fork in the cache), and MacStamp's census
(`fixtures/manifests/pair-census.csv`, 143,723 files), filtered to archive
programs' creators. **No row is established: no file's bytes were read**
(the census keeps no paths). Claiming a type costs 12 B of resource map.

| type | in Expander 5.5 | files in the census, by creator | note |
|---|---|---|---|
| `Part` | `FREF`, its `SIT!` bundle | `SIT!` 8, `SITx` 2 | unknown; beside its StuffIt archive and segment types |
| `PCFA` | `FREF`, its `crsX` bundle | none | unidentified |
| `pZIP` | `'open'` | none as a type; `pZIP` is UnZip's creator | claimed by UnZip 2.0.1, ZipIt 1.0–1.3.5, MacGzip (MacStamp's `apps.tsv`) |
| `m@rc` | `'open'` | none | claimed only by ArcMac 1.3c |
| `pBIN` | — | `pZIP` 19 (also `pGeN` 188 outside archive creators) | MacStamp's hypothesis: members UnZip wrote out, not archives |
| `SITo` | — | `SIT!` 10 | unknown |
| `bzy ` | — | `SIT!` 2 | unknown |
| `DDDA`, `DDf3`, `DDTM` | — | `DDAP` 2, 1, 1 | DiskDoubler's; `DDf3` sits beside the claimed `DDf4` |
| `Bzp2` | both lists | — | bzip2, out of scope (Part 1) |
| `SITX` | — | `SIT!` 1 | StuffIt X, out of scope (Part 1) |
| `fold`, `disk` | both lists | — | Expander's for a dropped folder or disk; MacExtract takes neither |

Also in the census under those creators and left out as not archives:
`adrp`/`SITx` 2, `pref`/`SITx` 1, `Pref`/`SIT!` 1. Creator `pZIP` is
UnZip 1.01, 1.10 and 2.0.1 (A. P. Maika), and `TEXT`/`pZIP` 26 files.

What would settle a row: a file of that type, from MacStamp's sources or
written to order by the program under the emulator (UnZip 2.0.1 on chosen
zips; StuffIt or Expander for `Part` and `SITo`; DiskDoubler for its
three), run through the CLI; a type is claimed only if it is an archive
MacExtract reads.

## BinHex before 4.0: what is not graded

- **No `.hex` from any writer but BinHex 2.0.** BinHex 1.0 and the BASIC
  BinHexes wrote it too (`reference/notes/BinHex.md`); closes with a specimen.
- **`src/fmt_hecx.c` is hexbin's.** BinHex 2.0's own `CODE` (5.6 KB) is the
  writer, and reading the layout out of it is the route Packit III 1.3 gave
  PackIt's ciphers (NOTICE).

## ZipIt archives: where the engine and ZipIt part

Measured on ZipIt 1.4 and 2.2.2 (DECISIONS.md 2026-11-06, *what ZipIt does
with a Macintosh file*). Line endings are not among them: extraction is
byte-exact by decision (DECISIONS.md 2026-11-07, *bytes as stored, never
converted*).

| what | status | what would close it |
|---|---|---|
| a segmented archive whose segments the user named freely (ZipIt asks "Save segment #%d as:") | not joined: parts are placed by `.zNN`/`.zip` (FORMATS.md, *Segments*); renamed, the set extracts byte for byte | an order read off the segments themselves, or the user's |
| a ZipIt-encrypted archive, byte for byte | **the cipher is known, the engine reads it**: ZipIt 2.2.2's `decrypt_byte`/`crypthead`/`UnzipCryptHeader` are standard PKWARE ZipCrypto, which `unc_zip_extract` already decrypts (DECISIONS.md 2026-11-06, *what ZipIt does with a Macintosh file*) | one ZipIt-made encrypted `.zip` to confirm against a real file (none here; a registered copy would write one) |

## The shell's own File Manager blocks, until multiversal's glue is inline

Switching to `HOpen`/`HOpenRF`/`HDelete` costs **+160 B** shipped today
(CODE +160, A5 0; +224 on 2026-10-19), so the hand-built blocks stay.
Inline glue alone does not make it free: the three inline cost **+32 to
+64 B** (measured with a local header, at 049d687; DECISIONS.md
2026-11-09, *the glue that was measured inline*). The seven I/O routines
are the shell's own inline code since 2026-11-11 (`mac/fm_inline.h`;
*the glue the shell expands*), so multiversal's generating them inline
would give MacExtract nothing more. Proposed upstream after MacExtract's
first public release (the maintainer, 2026-10-19), which v0.44.0 was
(2026-10-25): **not started**; posted by the maintainer.

## Apple Installer Tomes: what is not read, and what is not graded

The Tome reader is in, and the 'part' resources of an `ircp` file's or a
Tome's resource fork (FORMATS.md, *Apple Installer Tomes*). Left:

- **The per-fork checksum is unidentified** (+0x48, +0x58). Ruled out
  (measured 2026-11-11): byte, word and long sums, XOR, a rotating add,
  Adler-32, zlib's CRC-32, and every CRC-32 over eight polynomials, both bit
  orders, two initial values and two final XORs, over the decoded fork and
  over its stream with and without block headers; and in the 7.5.5
  Installer, decompressed whole, no CRC table, no reference to `idcp`, and
  no file atom of its script carrying any of 504 forks' values. So the
  Installer may never check it. Without it 1,308 of 3,704 single-byte
  changes are noticed (`tools/run_tome.py`). Closes with the routine that
  writes it: Apple's Installer SDK packer, not on this machine.
- **No `ircp` file is a fixture**: the 6 here (`~/.cache/macextract/specimens/ircp/`, off El Mac 7's
  Spanish System 7.5 Update 2.0, from MacStamp) were graded once
  (DECISIONS.md 2026-11-11, *the parts the Installer expands*), and El Mac
  7's image is not in the cache, so no SOURCES row can restore one; the
  other 10 of MacStamp's census were not kept. Closes with that image
  cached and a `derived:hfsvol` row for each.
- **19 forks graded by their exact end alone**, of `tome-wild-modemscripts`
  and `tome-wild-websharing` (81 until Mac OS 9's installed copies were
  read, 2026-11-11): deark fails them with its own errors — "Bad distance
  code" where it reads the text codec as InstaCompOne, "TODO code11" for a
  long copy it does not implement — and no installed copy of their release
  is here. Closes with an installed Mac OS 8.6.
- **deark widens InstaCompOne's long distance one output byte early** (at
  1,644; the specification and Apple's installed files say 1,645). Not
  reported upstream, and no minimal repro is written; the maintainer posts
  upstream reports.

## Installer VISE: what is not read, and what is not graded

The readers are in, the `VISE` archive of 1992-1996 and 3.5 to VISE X
with a set's segments (FORMATS.md, *Installer VISE*). Left:

- **Before 3.5, a damaged stream that keeps its length is not seen**: the
  format has no checksum, and 7 of 40 changed bytes in the smallest
  archive came out unrefused (`run_viseold.py`). Nothing closes it in the
  format; an installed copy of each file would grade it.
- **Before 3.5, where an Apple Installer script puts a `.vct`'s files** is
  not read: its 'infa' atoms may name another target; the files come out
  under the catalogue's names. Closes with the script's atoms read beside
  the `.vct`, or the Installer run under emulation.
- **Before 3.5, two files of 99 are graded by an independent copy**
  (DeltaSymbol.TT, Serial Tool). Installer VISE 3.0 (1994) is on the
  maintainer's share (MacStamp's `apps.tsv`); an archive it builds under
  emulation from known files would grade every byte, and say whether 3.0
  writes this format (not established).
- **A `.vct`'s type and creator are not known**: the eight came as data
  forks, so the bundle claims none and one is dropped on the application.
- **0x80010306** has no specimen (systemless reads it as 0x80010307's
  layout); not recognised until one is found.
- **What an installer writes is not compared.** The paths (folders by
  depth), Finder flags and dates are this engine's reading of the
  catalogue, held to `run_vise.py`'s own reading of the same layout, not
  to an installer's output; the CRC-32 grades the forks only. Closes with
  installers run under emulation (one with its resource fork: the Epson
  driver's, `fixtures/SOURCES.md`) and what they install compared.
- **A folder that holds no stored file is not created**, where the
  installer may create it empty (not measured).
- **A downloader that stores nothing** (Netscape's, QuickTime's) is refused
  with UNC_ERR_UNSUPPORTED, whose message names a compression method; it
  should say the installer holds none of its files. The wording is the
  maintainer's to choose.
- **A record whose bytes after its name hold `FVCT` or `DVCT`** would be
  taken for the next record, by this reader and by `run_vise.py` alike; no
  installer here has one.
- **Speed on a Mac Plus** is not measured: on x86 the inflater takes 42-73
  instructions an output byte to zlib's 24.
- **VISE X's segments after `Installer.data`** are not known: no set of
  them was found.
- **A later segment opened alone is not recognised**: `Segment.2` onward,
  or `Installer.data`, sniffs as unknown (only segment 1 is probed), where
  a later DiskDoubler or Apple Backup part names its format. Closes with a
  probe of a later segment and the set search started from it, priced.

## A format read only as a set, which the tick probe does not see

`tools/tick_probe` extracts through `unc_extract`, which answers
UNC_ERR_UNSUPPORTED for Apple Backup, so `run_ticks.py` grades nothing of
its progress (found 2026-11-11; Installer VISE was given a direct extract
so that it is graded, DECISIONS.md 2026-11-11, *the installer that was an
archive*). Closes with the probe driving a set through
`unc_extract_segments`.

## The double-click helpers: what is left

`companion/` works (DECISIONS.md 2026-10-11, *the stub that hands it on*);
its helpers are in `dist/` and on both disk images since
2026-11-04 (eighteen since 2026-11-10: Apple Backup's and the Installer Tome's), in no release yet (DECISIONS.md 2026-11-04, *the helpers in
dist*). Left:

- **Which of a file's two dates System 7 compares** between two applications
  of one creator. Not separated.
- **The stub's reclaim on System 7.x, 6 and 3.0.** On Mac OS 9 a helper
  opened by itself takes its creator back from StuffIt Expander
  (DECISIONS.md 2026-10-31, *the stub that sorts*); System 7.x and the
  stub's alert on Systems without a desktop database are not run.
- **An icon per document type, drawn by the maintainer.** Every helper's
  bundle points all its types at one family, MacExtract's archive icon
  (`companion/make_stub.py`); the eighteen helpers claim 51 types between
  them (`DDAP` 15, `SIT!` 8, `SITx` 5, `MARc` 4, the rest 1 or 2;
  `companion/helpers.tsv`). The Finder draws a file's icon from the
  application that owns its creator, so these show on archives that keep
  their original creators, and cost MacExtract nothing: a helper's
  resource map is in the helper's heap. MacExtract's own bundle keeps the
  one archive icon, since a family there costs 72 B of its resource map
  (FORMATS.md, *Icons*). A colour family is about 2.3 KB of the helper
  and a black-and-white one (`ICN#`, `ics#`) about 320 B; the helpers zip
  is 64,171 B today and rides on the 400K floppy.
- **The helpers in Macintosh Easy Open's lists.** Easy Open steps in only
  when no application has a document's creator, and then lists every
  application that can open its type (*Inside Macintosh: More Macintosh
  Toolbox*, Translation Manager, 7-5 to 7-6). A helper's `FREF`s make it
  one, so an orphaned `SITD` would offer MacExtract and the `StuffIt` and
  `Expander` helpers beside it (hypothesis, read off our bundles: not run).
  An `'open'` resource in an application's own fork overrides the types
  its `FREF`s list (7-44), so a helper's `'open'` with no types should drop
  it from those lists and keep its icons; whether a count of 0 is honoured
  is what one Mac OS 8 or 9 boot with Easy Open would settle. The same list
  holds at most 64 types (`TypesBlock`, `GetFileTypesThatAppCanNativelyOpen`,
  7-37); a bundle's `FREF` count has no such limit (*Macintosh Toolbox
  Essentials*, 7-64 to 7-67), and MacExtract claims 51.

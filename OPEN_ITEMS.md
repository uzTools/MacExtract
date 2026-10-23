# OPEN_ITEMS.md — what is missing, and what is deliberately not

1. **Part 1, out of scope** — decided or impossible, recorded so nobody
   re-litigates it. Read it before starting work on a format.
2. **Part 2, open items** — what is not done or not verified, each with
   what would close it. Only OPEN items live there: a closed one moves out
   (the lesson to DECISIONS.md, the withdrawn claim to BLOCKERS.md, the
   numbers to FORMATS.md).

Nothing here stops the engine or the CLI, which are byte-exact against the
oracle across 978 fixtures in `./ci.sh`. Detail lives once — status in
BLOCKERS.md, reasoning in DECISIONS.md, results in FORMATS.md, re-running in
TESTING.md or `tools/vmac/README.md`, hardware in MANUAL_TESTS.md.

**Filing something here is a decision to stop looking, so ask first.** Each
of these questions has emptied a row at least once (BLOCKERS.md, *Withdrawn
claims*, has every case):

- Is there an implementation that could be **fed** (DECISIONS.md, methods 3, 4 and 5)?
- Is *"X does not survive"* a claim about somebody's **search**?
- Does the search name the **right tool**?
- **Have you looked at all?**
- **Was the search by name?** An index of magic sees what one of names
  cannot — worth asking twice (DECISIONS.md 2026-09-26, *the magic in
  somebody else's index*).
- **Is the corpus the claim was measured on the corpus that is here now?**

---

# Part 1 — Out of scope for v1

**Decided, or impossible. Not open.** Nothing here is closed by finding a
file; "out of scope" is today's answer and not a refusal — the brief has
grown before, on request.

## Out by the brief

| what | status | why it stays out |
|---|---|---|
| Compression | not implemented | this is an extractor |
| Get Info comments on a disk without a Desktop Manager — System 6 and System 3.0 volumes (unless AppleShare's Desktop Mgr INIT is installed, DECISIONS.md 2026-10-21), and floppies under System 7 | **not written; nothing says so** | decided by the maintainer 2026-10-17: the old Finder keeps comments in its own `Desktop` file, which it may hold open, and writing it would be a second path on some Systems only (DECISIONS.md 2026-10-17, *the metadata, carried to the disk*) |
| Extracting onto an MFS disk, on any Macintosh | **out of scope, decided 2026-10-15; what happens is not documented** | MFS has no folders; supporting it means a second write path, and without HFS a check for it (DECISIONS.md 2026-10-15, *the File Manager a 64K ROM has*) |
| Choosing which entries come out, in the Macintosh application | **not implemented; the CLI's `--only` ships** | decided 2026-09-26: a tick list is paid for by every run. The engine keeps both halves a host needs (`UncOptions.list_only`, a `begin_entry` returning >0); built on the kept branch `selective-extract` (BRANCHES.md; DECISIONS.md 2026-09-26, *the feature that was parked, and is now out*) |
| Hardware decoding — an FPU, a coprocessor, a NuBus codec card | **not implemented, nothing measured for one to do** | every codec is integer work; Arsenic's two divides are 0.72 % of a run (FORMATS.md, *What is still hot*), and a second `-mcpu=68020` build is out too (DECISIONS.md 2026-09-23, *hardware decoding*) |
| The Macintosh 512K — 64 KB of ROM | **the interface runs; extraction needs HFS** | measured 2026-09-01; the download gets as far as Standard File since 2026-10-16 (`GrowApplZone`, merged from the branch `rom64k`), and only a Hard Disk 20 supplies HFS, which nobody has run (FORMATS.md, *A true Macintosh 512K*; MANUAL_TESTS.md §6). A **128K** is out on the heap TOTAL, corrected 2026-10-06 (FORMATS.md, *A Macintosh 128K*, *Overlays*) |
| StuffIt X (`.sitx`) | **not recognised** since 2026-10-18 (named until then) | out by the brief (DECISIONS.md 2026-10-18, *the formats it only named*) |
| PKWARE "strong encryption" in a zip (flag 0x40) | **named, refused per entry** | its key material is in a record nothing here parses, and XADMaster refuses it too; every other cipher these formats have is decrypted (FORMATS.md, *Encryption*) |
| Disk images (`.image`, `.img`, `.iso`, `.cdr`, `.toast`, `.dmg`, `.smi`), and Disk Copy 4.2 | **not recognised**, and not extracted | a filesystem, not a codec; the probes are kept in `attic/` (DECISIONS.md 2026-08-26, *read the volume, not the extension*). DART was in from 2026-09-09 to 2026-09-25 and left for MacMount (DECISIONS.md 2026-09-25, *the disk images that found another home*) |
| PMarc (`-pm0-`, `-pm1-`, `-pm2-`) and `-lhx-` | **not recognised** | a different family behind an LZH-shaped header; neither reached a Macintosh |
| Self-extracting LZH (an executable with an archive behind it) | **not recognised** | nothing in the file says where the first header is, unlike a zip, whose offsets are absolute — which is why a self-extracting zip is recognised since 2026-10-05 (DECISIONS.md 2026-10-05, *the scan that was already being paid for*) |
| RAR, 7z, bzip2, xz, Cabinet, Zoo, ar/`.deb`, cpio, ARJ, Zstandard, lzip, lrzip, WIM, Apple Archive | **not recognised** since 2026-10-18 (named until then) | not Macintosh formats, and each is served by a maintained extractor; the maintainer's decision 2026-10-18 that nothing is recognised that is not extracted (DECISIONS.md 2026-10-18, *the formats it only named*). `tools/run_foreign.py` holds every reader to that (TESTING.md, *Archives this engine does not have*) |
| Alysis SuperDisk! method 13 | **not implemented, and no specimen is wanted** | its module compresses and refuses to decompress, so nothing anywhere could grade a decoder (FORMATS.md, *Module 13*; DECISIONS.md 2026-08-29, *the specimen that would have settled nothing*) |
| Checking a MIME part's `Content-MD5` | **not implemented**; a `message/partial` anchor that is not a part — the set pasted into one file, or part 1 with a signature after it — comes out wrong with exit 0, as from munpack | decided 2026-10-11: built and priced at **+1,446 B** of `ovl_text` for a header mpack writes and nothing here has seen in a file this project did not make (FORMATS.md, *`message/partial`*; DECISIONS.md 2026-10-11, *the digest our own oracle could not compute*) |
| Zip64 addressing past 4 GB | **counts and the per-entry escape are read; over-4-GB fields are refused** (`UNC_ERR_UNSUPPORTED` per archive, `UNC_ERR_TOOLARGE` per entry; `unc_zipseg_describe` refuses a spanned set) | a format change, not a type change (DECISIONS.md 2026-08-28, *what a width costs*; FORMATS.md, *Size limits*); tar reaches past 4 GB today |

Nothing is detect-only since 2026-10-18: a file of a format this engine
does not extract is `UNC_FORMAT_UNKNOWN`, the CLI says *"format not
recognized"*, and the Macintosh application *"This file could not be
extracted."* without asking where to extract (DECISIONS.md 2026-10-18, *the
question after the look*, *the formats it only named*).

## Limits of the formats themselves

**What would change any of these: nothing in the format.**

- **An encrypted classic StuffIt archive that has lost its resource fork
  cannot be decrypted by anything**: the password verifier is its `'MKey'`
  resource. The engine says *"encrypted by a scheme we cannot read"*; the
  fork counts as present in a MacBinary or BinHex envelope or a sidecar
  (`load_mkey`, `cli/main.c`). It is the only one of the eight ciphers so
  affected, measured 2026-10-07 (FORMATS.md, *Encryption*). With the
  password in hand the fork's loss is not permanent after all — the
  `'MKey'` only decrypts to the archive IV, and the IV is recoverable by a
  2^32 search its own self-verifier enumerates, graded by the entries'
  CRCs (measured 2026-10-13); how to implement it is left as an exercise to
  the reader.
- **A fork compressed by a third party's StuffIt compressor module (method
  nibble 7) is not decodable.** 2.0.1's own `STR# 267` names a
  `Compressors` folder among its eight; Aladdin's two disks fill five of
  them and not that one, and none has surfaced since; the engine names the module id and refuses the entry
  (FORMATS.md, *What an Optimizer did to the fork*).
- **A raw brotli stream cannot be identified**: RFC 7932 §9.1 has no magic
  (`reference/notes/brotli_rfc7932.txt`).
- **A cut tar cannot be noticed**: no directory or length, and the trailing
  zero blocks are not reliably there (`derived-popper-1.7.tar` has none).
  Every other format notices a cut (`tools/run_truncation.py`).
- **One 46-byte window of a DiskDoubler DDA2 archive is ambiguous**: a cut
  there is byte-for-byte a valid ending (`derived-DD_Expand.sea`;
  DECISIONS.md 2026-08-29, *a cut archive*).
- **A uuencoded set missing a middle part decodes short, silently**: no
  length or checksum; a missing last part is caught. `tools/run_uu.py`
  asserts this result.

---

## The licence cannot move, and this is the irreducible core

**Measured and settled** (the 2026-09-19 shedding brief): five items have no
permissive statement anywhere, so LGPL-2.1 stays. **Do not re-price
these** — each was settled with a measurement, and prices live in
FORMATS.md (*Resident memory*). The full per-file inventory is NOTICE's,
checked by `tools/check_provenance.py`.

| what | why nothing replaces it |
|---|---|
| `unc_lzdyn.c` — `-lh2-` and `-lh3-` | lhasa implements neither and LHa for UNIX has its own licence; **kept**, settled 2026-08-25 and 2026-09-23 (DECISIONS.md, *the 3,504 bytes that stay*) |
| `fmt_sit.c` — three rules of StuffIt method 8 (table restart, end of stream, 14-bit ceiling) | no specimen reaches any of them and deark leaves the method NULL (checked 2026-09-27; DECISIONS.md, *the layout Aladdin's own output settled*) |
| `unc_crypt.c` — StuffItDES's key schedule | reads all 64 key bits, so no standard schedule; graded against three StuffIt Deluxe 3.5.1 archives every run |
| `unc_lzah.c` — the `-lh1-`/method-5 window preload | the corpus cannot tell XADMaster's reading from lhasa's, measured 2026-09-28; a stream reaching back past ~110 bytes would (DECISIONS.md 2026-09-28, *the preload nothing reaches*) |
| `src/sit14.c` — StuffIt 5's method 14 | libxad's `SIT_14` is the only implementation; deark leaves it NULL (checked 2026-10-03). Graded against `unar` and `synth-sit14.sit` (FORMATS.md, *StuffIt 5's method 14*) |
| `fmt_arc.c` — Crunch 5/6/7 and Crush | no other implementation of 7 or Crush, and nothing could grade a rewrite; **not taken, decided 2026-09-22** |
| five tolerances no specification supports — the MacBinary CRC-16/0xA001 fallback and its nonzero-date test, the byte-swapped AppleSingle header, the StuffIt split header, DiskDoubler's stored header CRC of zero (none of 91 headers here has one) | deark read for all four 2026-09-27, a checked negative (its MacBinary is CRC-16/XMODEM alone with no date test; `de_identify_applesd` takes only big-endian magics); the two MacBinary ones are also unexercised (933 fixtures, 9,330 variants, 2026-09-28), and the fallback is pinned in `tests/unit_formats.c`; **kept, the maintainer's decision 2026-10-23** (DECISIONS.md 2026-10-23, *the probes next door*) |

---

# Part 2 — Open items

## A click during an extraction waits for the next progress callback

The menu bar is read only in the progress pump, so a click shorter than
the gap between two callbacks is lost and the button has to be held
(DECISIONS.md 2026-10-12, *the application nobody could leave*). The gap
is measured per format at 1x (FORMATS.md, *How long a click waits*):
StuffIt 5 went 254 s without one until 2026-10-12 and is under 1.1 s now
(DECISIONS.md 2026-10-12, *the block nobody could cancel*). **What is
left is 4–6 s on a Mac Plus** for Now Compress, Compact Pro and
DiskDoubler, and 2–2.5 s for StuffIt and Zip — the cost of 8 KB of
input, which is where `UNC_PROGRESS_STEP` puts the tick. **Halving it
is measured** (FORMATS.md, *What a 4 KB step buys*): gaps down by a
third to a half, 0 B, at most +0.3 % on System 6 and +0.4 % on System 7
with nothing else running; Now Compress's 32 KB block does not move. It
is CLAUDE.md's "every 8–16 KB", so it is the maintainer's to decide, and
it needs the three stored-fork copies sized by their own constant
first, the step being their buffer too. MIME, which failed
`run_ticks.py` at 4 KB, passes it since 2026-10-13 (DECISIONS.md
2026-10-13, *the mail that counted itself three times*). **Seen on silicon, 2026-10-12**: the LC 475's
window "not very reactive" while it extracts, format not noted —
re-test on a StuffIt 5 archive once this is on the machine. Holding the
File menu down pauses the extraction — inherent: `MenuSelect` keeps the
machine until release, and the extraction runs in the same loop.

## The metadata the archives hold and the readers drop

Since 2026-10-17 the engine carries every field the Finder keeps
(`UncEntryInfo`: FInfo/DInfo and FXInfo/DXInfo whole, the backup date, the
lock, the Get Info comment) and the Macintosh shell writes all of it
(DECISIONS.md, *the metadata, carried to the disk*). **Readers that deliver
everything their format holds**: AppleSingle/AppleDouble, AppleLink
packages, MacBinary I/II/III (also inside ZipIt, MacLHA and MacGzip, less
the comment), uuencode, base64 and MIME `multipart/appledouble`; BinHex 4
and before 4 hold nothing more (DECISIONS.md 2026-10-17, *the envelopes'
own Finder info*); StuffIt classic, what Expander 4.0.2 restores, and
DiskDoubler's single-file header (*the window Expander puts back*); and
PackIt, StuffIt 5, Now Compress, SuperDisk!, Private File, ArcMac and ARC,
zip, tar, gzip and LZH (DECISIONS.md 2026-10-17, *the archives' own Finder
info*), less what this table still names. The leads —
**each needs its own source or measurement before it is read**:

| format | stored, not read | oracle |
|---|---|---|
| MacBinary inside ZipIt and MacLHA | the Get Info comment, after both forks in a stream decoded only after the entry is offered | none; none of 14 ZipIt payloads has one (measured 2026-10-17), MacLHA's not read; a second decode or a sink contract change, the maintainer's call |
| zip | ZipIt `0x2805`'s View word: one specimen, value 0, and which DInfo field it is no reference says | ZipIt's own expander, run on an archive with a non-zero View |
| StuffIt 5 | the Finder info of a version-3 entry, whose second block is four bytes shorter; no entry here is version 3 | Expander 5.5 on one |
| LZH | OS/2's 0x7f/0xff headers (dates, attributes); a level 0/1 name field's bytes after a NUL, which XADMaster calls a comment | `lsar`; no specimen of the second |
| tar | a pax `g` (global) header, stepped over | — |
| DiskDoubler `DDAR`/`DDA2` records | bytes no reference assigns (DDAR +100..117; DDA2 folder +46..53, +62 on); only the 84-byte single-file header is measured (DECISIONS.md 2026-10-17, *the window Expander puts back*) | DiskDoubler's own expander, under emulation |
| AppleSingle entry 11 | ProDOS's access word (no write-enable is a lock) | none; RFC 1740 gives its size and not its bits, and no reference here does |

Closing a row: the reader delivers the field with a `Source:` and a grade,
and `tools/run_meta.py` holds it.

## Mac OS X's sidecars: what they hold and the engine does not read

Since 2026-10-17 a zip's `__MACOSX/…/._name` and a tar's `._name` are put
back on their file (DECISIONS.md, *the sidecars Mac OS X left beside the
file*), their Spotlight comment since 2026-10-18. Left, none with a
specimen here:

- **A Spotlight comment past the window**: one whose property list ends
  after byte 1,024 of the sidecar is dropped, and so is one in a
  standalone `._name` read as AppleDouble (DECISIONS.md 2026-10-18, *the
  comment Spotlight kept*). No specimen has either.
- **A tar sidecar written after its file**: out as itself. bsdtar never
  writes that order; a pax header between the two is stepped over, but no
  specimen has one (hypothesis: bsdtar writes one for a non-ASCII name).

## Dates in the Macintosh's zone: what is not measured

Since 2026-10-17 a date the engine marks as an instant is written in the
Mac's zone where it can say what that is (DECISIONS.md 2026-10-17, *dates in
the Macintosh's own zone*). Measured on emulated System 3.0, 6.0.8 and 7.0.1
with the zone put into PRAM by the emulator build, not by Map.

| what | status | what would close it |
|---|---|---|
| whether gmtDelta already includes daylight saving | **hypothesis**: three non-Apple readers say it does; dlsDelta is not added | Map's daylight-saving box toggled once on 7.0.1, and the 12 bytes read back |
| AppleSingle/AppleDouble written by mpack, whose entry 8 is the writer's wall clock and not RFC 1740's GMT | **the maintainer's decision**: the RFC is followed, so such a file moves by the reader's offset | a rule to tell the writer apart, or a decision to treat entry 8 as wall clock |

## A refused PBSetCatInfo is not reported

Under GateKeeper 1.3 in its "Notify & Veto" mode, `PBSetCatInfo` on an
extracted application is vetoed — GateKeeper's `File(Other)` privilege,
which it grants StuffIt and Compact Pro by name and not this program — and
the file comes out with no type, creator, flags or dates while the run
ends in *Extraction complete.*, measured 2026-10-21 on System 6.0.8
(DECISIONS.md 2026-10-21, *the guard that vetoes the Finder info*). Both
forks are on the disk; GateKeeper's own alert names the veto. `StampCat`
ignores the call's result. Closes with a report line for the entry
(`S_REP_*`, "name: Finder info refused"), priced in resident bytes, and
the GateKeeper run repeated (`tools/vmac/README.md`, *GateKeeper*).

## System 7.0.1 rewrites one byte of FXInfo

FXInfo +9 (`fdXFlags`) reads 0x70 on a System 7.0.1 output disk where the
shell wrote the archive's 0x00, measured 2026-10-17 by
`tools/vmac/metarun.py`; System 6.0.8 and 3.0 keep it, and with no FXInfo
written it stays 0x00 on 7.0.1 too (DECISIONS.md 2026-10-17). **Not
`fdScript`**: a file with `fdScript` 0 came back 0x70 the same way, and
another with `fdScript` 0 did not (DECISIONS.md 2026-10-17, *the sidecars
Mac OS X left beside the file*). The two that changed are both locked and
both given a comment; **not the comment alone** — six files given one and
not locked kept 0x00 on the same 7.0.1 disk, measured 2026-10-18
(DECISIONS.md, *the comment Spotlight kept*), so the lock is left
(hypothesis). Closes with a locked file and no comment, FXInfo read back
by the autotest before the Finder can see the file.

## Hand-written 68000 assembly: candidates, held for one VM pass

**Not started, by decision (2026-10-09).** The engine is portable C99
and has no assembly. The maintainer's call is to collect the loops where
hand assembly beats what GCC emits, and then build, test and time them
together in one pass, rather than one at a time. Every figure is
an ESTIMATE from the MC68000 timing table and none has been timed on a
machine (DECISIONS.md 2026-10-09, *what GCC will not do with an
index*).

The candidates — twelve loops with a C and an assembly cycle estimate
each, and sixteen suggestions not yet estimated — are FORMATS.md's
(*Hand-written 68000 assembly: the candidates, estimated*).

**Prerequisites for the pass**, once for every row:

| what | why |
|---|---|
| **a `qemu-m68k` lane in `ci.sh`**: the m68k-linux CLI (TESTING.md, *The 68000 profile*, has the build line) running `run_crypt.py`, `run_privatefile.py`, the differential suite (every CRC row) and a `UNC_ARS_FORCE_SAMPLED` build (the scan) | `ci.sh` runs x86, which compiles the C path, so without this lane an assembly path is graded by nothing |
| **a timing build that can open an encrypted archive**: the autotest app with a compile-time password beside `UNC_AT_TIMING` | the tick probe (tools/vmac/README.md) is what prices a change here, and today it cannot reach any cipher |

## Resident bytes that could leave before extraction

**Not started; each is its own change.** Every resident byte comes off
every extraction's budget (FORMATS.md, *What the application costs the
engine*); these are what is still resident and runs before the release,
or only for some archives. Sizes MEASURED 2026-10-22 on `main` at
17a025b, `nm -S` of `build/mac/MacExtract.code.bin.gdb`; every saving is
a HYPOTHESIS until built and read off the budget probe on the machine,
which is how the sniffer's image (2026-10-21) and the runtime trim
(2026-10-22) were priced. On a 128K Macintosh only the last three rows
would count, since a subset build there has no bundle (FORMATS.md, *A
Macintosh 128K*).

| what | resident | what would close it |
|---|---|---|
| the encryption check before the release, `unc_archive_encrypted` | 618 B of code | it runs only inside the release, with the bundle whole, so it can join `ovl_sniff`; move it and measure |
| the MacBinary and AppleDouble readers, `unc_macbinary_extract` and `unc_appledouble_extract` | 1,880 B of code | an image of their own: an envelope keeps the whole bundle, so it costs envelopes nothing. `unc_macbinary_meta` and `unc_as_record` stay resident, because the LZH and zip images reach them through the host vector. Every call site must run with the bundle whole, the envelope peek in `SegScanWrapped` among them |
| segment joining in the engine: `unc_segment.c`, the five `fmt_*seg.c` and the parsers their probe files share | 6,498 B of code | an image kept by the release for every set scheme. Part of it is reached by images through the host vector (`unc_zip_scan_eocd`) and stays; how much can move is not measured |
| the shell's set code, `SegAskUser`, `SegScanWrapped`, `SegPartOf` and the rest | 3,166 B of code | it calls the Toolbox, and an image reaches nothing outside itself but the host vector; needs Toolbox entries in the vector first. Not priced |
| the report window's buffers, `gRepBuf` and the row arrays | 8,730 B of bss, and 1,568 B of code | the bss is resident for the whole run whatever the archive. A handle grown as lines arrive would cost most runs a few hundred bytes; `interactive.py` reads the box, so it must still show the same |
| the overlay shims, `mac/ovl_shim.c` | 2,462 B of code | about twenty-five dispatchers of one shape; a table-driven dispatch might be a third of that |
| the relocator, `Retro68Relocate` and `Retro68ApplyRelocations` | 1,656 B of code | runs once at launch and stays in `CODE` 1. Elf2Mac's linker script places it at the START of `.text`, so it cannot be trimmed off the end as the relocations are; needs a layout Elf2Mac does not offer (`--mac-keep-ldscript` shows the script) |

## MIME multipart nested past the depth cap is dropped silently

A `multipart/*` more than `MIME_MAX_DEPTH` (4) levels deep is not pushed
onto the boundary stack; its subtree is walked as one opaque leaf, emitted
by nothing, and lost without a per-entry error. Measured 2026-10-22 with
the Linux CLI, no emulator: a five-level nest whose only attachment sits at
the bottom lists nothing and exits *not a recognized archive*; four levels
extract it. The walk is iterative, so the cap is the fixed `MimeCtx` arrays,
not the 68000 no-recursion rule; mpack (the oracle where `unar` fails, and
`unar` rejects these outright) recurses unbounded and would keep it. Real
mail nests two or three deep, so the ceiling is sound — the silent loss is
the defect. Closes by making the cap loud: a report line when depth is
exceeded (`S_REP_*`) rather than a dropped subtree, priced in resident
bytes; the number may be raised (~340 B a level) or the stack grown, but
neither is required to close it.

## Formats classic Mac programs wrote that nothing here opens — leads, not findings

From the 190 entries of Macintosh Repository's *Compression & Archiving*
category, read 2026-10-12 (`companion/harvest/macrepo-compression.tsv`):
**every row below is from a program's NAME and DESCRIPTION, and none has
been held against a file.** The modern macOS programs, video compressors and
backup-to-disk tools in the category are left out, and so is what Part 1
already covers (RAR, ARJ, Zoo, cpio, disk images).

| format | programs there | here |
|---|---|---|
| SUMacC `.dl` (resource fork only, 4 bits a character) | none there; hexbin's `dl.c` reads it | named nowhere; one wild file, `mactosh/lang/xlispold.dl` on Discmaster's carousel disc, which hexbin decodes with its sum verifying |
| ShrinkIt / NuFX (`.shk`, `.bxy`), Apple II | ShrinkIt | named nowhere |
| shell archives (`shar`) | unshar | named nowhere |
| yEnc | yEnc TZ | named nowhere |
| Apple Backup (Performa-era backup disks) | Apple Backup Extractor | named nowhere |
| backup sets | Retrospect 1.x/2.1, Fastback, HFS Backup, MacBack, Network DiskFit, Diamond | named nowhere |
| splitters that may add a header | MacHacha, SplitIt!, SplitsVille, Split & Join, Split&Concat | plain `.001` and DiskDoubler `SPLT` only; whether these write either is unknown |
| unidentified | GIF Blast, MacSQZ!, The Parer, RadicalSqueeze, BKOS Compress, FileCrypt, Big Hairy Installer, MacToVax | the format is not known |

Closing a row means a specimen written by the program, then the usual
question of a second reader to grade against.

## BinHex before 4.0: what is not graded

`.hex` and `.hcx` extract since 2026-10-14 (DECISIONS.md, *the BinHex
before 4.0*). Left:

- **No `.hex` from any writer but BinHex 2.0.** BinHex 1.0 and the BASIC
  BinHexes before it wrote the format too (`reference/notes/BinHex.md`).
  Closing it is a specimen from one of them, or the program.
- **`src/fmt_hecx.c` is hexbin's.** BinHex 2.0's own `CODE` (5.6 KB) is
  the writer, and reading the layout out of it is the route Packit III
  1.3 gave PackIt's ciphers (NOTICE).

## The shell's own File Manager blocks, until multiversal's glue is inline

#322 is fixed in the toolchain here (Retro68 `afedcdc`), and the switch
decided 2026-10-15 (*the rest of the block*) was priced 2026-10-19:
`HOpen`/`HOpenRF`/`HDelete` in place of `MyOpenFork`/`MyHDelete`, shipped
CODE +216 and A5 +8, **+224 B** (`HDelete` alone +32), for the same
fields set. The blocks stay (measured; DECISIONS.md 2026-10-19, *the
toolchain that inlined PurgeSpace*).

Closes when multiversal generates its File Manager glue inline, as pull
request 20 did for register outputs: then the switch should cost about
0 B (hypothesis). Proposed upstream **after MacExtract's first public
release** (the maintainer, 2026-10-19), as pull requests one after the
other: (1) the mechanism with `HOpen`, `HOpenRF`, `HDelete`; (2) the other
opens; (3) create, delete, rename; (4) Finder info and `GetWDInfo`;
(5) read, write, position, EOF, close; (6) volumes. Measure each against a
locally patched header first. MacExtract links seven of these as glue
today, 298 B: `FSRead` 58, `FSWrite` 58, `SetFPos` 42, `GetEOF` 38,
`SetEOF` 36, `FlushVol` 36, `FSClose` 30 (measured, `nm -S`); inline at
every call site they may cost more than they save (not measured).

## The double-click helpers: what is left before they ship

`companion/` works (DECISIONS.md 2026-10-11 and 2026-10-12, *where the
stubs can live*, *the stub that hands it on*, *the stub beside StuffIt*),
and ships later, on MacExtract's own floppy. Left:

- **Which creators.** `companion/app-bundles.tsv` has 42 creators read
  off the programs themselves, with their bundles; the list of stubs is
  not chosen. Text encodings
  stay out (`TEXT` from editors), and so does `SITx`.
- **A second double-click while MacExtract runs**, under MultiFinder and
  System 7 — the stub asks to launch a running application. Not run.
- **Several archives of DIFFERENT creators opened together** — two stubs
  for one selection. Not run.
- **Which of a file's two dates System 7 compares** to choose between two
  applications of one creator. Not separated.
- **StuffIt Expander 5.5 does the same**: it opens other formats through
  companion stubs (the maintainer, 2026-10-16, from its installer,
  `MacMountBench/5-Downloads/stuffit_expander_55.bin` on the share). How
  is not examined, and its helper applications were not found on a first
  look.

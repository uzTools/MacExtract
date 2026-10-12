# OPEN_ITEMS.md — what is missing, and what is deliberately not

1. **Part 1, out of scope** — decided or impossible, recorded so nobody
   re-litigates it. Read it before starting work on a format.
2. **Part 2, open items** — what is not done or not verified, each with
   what would close it. Only OPEN items live there: a closed one moves out
   (the lesson to DECISIONS.md, the withdrawn claim to BLOCKERS.md, the
   numbers to FORMATS.md).

Nothing here stops the engine or the CLI, which are byte-exact against the
oracle across 964 fixtures in `./ci.sh`. Detail lives once — status in
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
| Choosing which entries come out, in the Macintosh application | **not implemented; the CLI's `--only` ships** | decided 2026-09-26: a tick list is paid for by every run. The engine keeps both halves a host needs (`UncOptions.list_only`, a `begin_entry` returning >0); built on the kept branch `selective-extract` (BRANCHES.md; DECISIONS.md 2026-09-26, *the feature that was parked, and is now out*) |
| Hardware decoding — an FPU, a coprocessor, a NuBus codec card | **not implemented, nothing measured for one to do** | every codec is integer work; Arsenic's two divides are 0.72 % of a run (FORMATS.md, *What is still hot*), and a second `-mcpu=68020` build is out too (DECISIONS.md 2026-09-23, *hardware decoding*) |
| The Macintosh 512K — 64 KB of ROM | **the interface runs; extraction needs HFS** | measured 2026-09-01; the branch `rom64k` gets as far as Standard File, and only a Hard Disk 20 supplies HFS, which nobody has run (FORMATS.md, *A true Macintosh 512K*; MANUAL_TESTS.md §6). A **128K** is out on the heap TOTAL, corrected 2026-10-06 (FORMATS.md, *A Macintosh 128K*, *Overlays*) |
| StuffIt X (`.sitx`) | **detect-only** | out by the brief |
| PKWARE "strong encryption" in a zip (flag 0x40) | **named, refused per entry** | its key material is in a record nothing here parses, and XADMaster refuses it too; every other cipher these formats have is decrypted (FORMATS.md, *Encryption*) |
| Disk images (`.image`, `.img`, `.iso`, `.cdr`, `.toast`, `.dmg`, `.smi`), and Disk Copy 4.2 | **not recognised**, and not extracted | a filesystem, not a codec; the probes are kept in `attic/` (DECISIONS.md 2026-08-26, *read the volume, not the extension*). DART was in from 2026-09-09 to 2026-09-25 and left for MacMount (DECISIONS.md 2026-09-25, *the disk images that found another home*) |
| PMarc (`-pm0-`, `-pm1-`, `-pm2-`) and `-lhx-` | **not recognised** | a different family behind an LZH-shaped header; neither reached a Macintosh |
| Self-extracting LZH (an executable with an archive behind it) | **not recognised** | nothing in the file says where the first header is, unlike a zip, whose offsets are absolute — which is why a self-extracting zip is recognised since 2026-10-05 (DECISIONS.md 2026-10-05, *the scan that was already being paid for*) |
| RAR, 7z, bzip2, xz, Cabinet, Zoo, ar/`.deb`, cpio, ARJ | **named, never extracted** | not Macintosh formats, and each is served by a maintained extractor (DECISIONS.md 2026-08-26, *a name is only worth something inside the frame the user came with*; FORMATS.md, *Archives named but not extracted*) |
| Alysis SuperDisk! method 13 | **not implemented, and no specimen is wanted** | its module compresses and refuses to decompress, so nothing anywhere could grade a decoder (FORMATS.md, *Module 13*; DECISIONS.md 2026-08-29, *the specimen that would have settled nothing*) |
| Checking a MIME part's `Content-MD5` | **not implemented**; a `message/partial` anchor that is not a part — the set pasted into one file, or part 1 with a signature after it — comes out wrong with exit 0, as from munpack | decided 2026-10-11: built and priced at **+1,446 B** of `ovl_text` for a header mpack writes and nothing here has seen in a file this project did not make (FORMATS.md, *`message/partial`*; DECISIONS.md 2026-10-11, *the digest our own oracle could not compute*) |
| Zip64 addressing past 4 GB | **counts and the per-entry escape are read; over-4-GB fields are refused** (`UNC_ERR_UNSUPPORTED` per archive, `UNC_ERR_TOOLARGE` per entry; `unc_zipseg_describe` refuses a spanned set) | a format change, not a type change (DECISIONS.md 2026-08-28, *what a width costs*; FORMATS.md, *Size limits*); tar reaches past 4 GB today |

Everything detect-only is **named** by `unc_sniff`, and both front ends say
the name: the CLI prints *"recognized as RAR, which v1 cannot extract"* and
the Macintosh application's alert reads *"MacExtract cannot open RAR files."*

## Limits of the formats themselves

**What would change any of these: nothing in the format.**

- **An encrypted classic StuffIt archive that has lost its resource fork
  cannot be decrypted by anything**: the password verifier is its `'MKey'`
  resource. The engine says *"encrypted by a scheme we cannot read"*; the
  fork counts as present in a MacBinary or BinHex envelope or a sidecar
  (`load_mkey`, `cli/main.c`). It is the only one of the eight ciphers so
  affected, measured 2026-10-07 (FORMATS.md, *Encryption*).
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
| four tolerances no specification supports — the MacBinary CRC-16/0xA001 fallback and its nonzero-date test, the byte-swapped AppleSingle header, the StuffIt split header | deark read for all four 2026-09-27, a checked negative (its MacBinary is CRC-16/XMODEM alone with no date test; `de_identify_applesd` takes only big-endian magics); the two MacBinary ones are also unexercised (933 fixtures, 9,330 variants, 2026-09-28), and the fallback is pinned in `tests/unit_formats.c` |

---

# Part 2 — Open items

## What the LC 475 found that is not fixed

The maintainer's first session on silicon, 2026-10-11 (MANUAL_TESTS.md
§2, §4). Each is measured on that machine and nowhere else.

- **Cmd-. does nothing on a French (AZERTY) keyboard.** The period
  needs Shift there, and the shell compares the event's character with
  `'.'` (`mac/macextract_mac.c`, the progress pump). *Hypothesis*: with
  Command down, that key does not report a period — Apple's technote on
  international canceling is about this case, and it has not been read
  here. The Cancel button works. Closing it starts with that technote,
  and is priced in bytes like any shell change.
- **The time estimate steps backwards for a tick**, on StuffIt 5 (the
  bar never does). Not looked into.

## A click during an extraction waits for the next progress callback

The menu bar is read only in the progress pump, which runs every
8–16 KB of input, so a click shorter than
that gap is lost and the button has to be held. On System 7.0.1 a 4 s hold
was enough for `derived-EmpireBuilderDemo.sit` (DECISIONS.md 2026-10-12,
*the application nobody could leave*). How long the slowest decoder makes
the user wait is not measured. Closing this means measuring the longest
gap between callbacks per method first. **Seen on silicon, 2026-10-12**:
switching to the Finder works on the LC 475, and the maintainer found
MacExtract's window "not very reactive" while it extracts. Holding the
File menu down pauses the extraction — inherent: `MenuSelect` keeps
the machine until release, and the extraction runs in the same loop.

## Hand-written 68000 assembly: candidates, held for one VM pass

**Not started, by decision (2026-10-09).** The engine is portable C99
and has no assembly. The maintainer's call is to collect the loops where
hand assembly beats what GCC emits, and then build, test and time them
together in one pass, rather than one at a time. Every figure is
an ESTIMATE from the MC68000 timing table and none has been timed on a
machine (DECISIONS.md 2026-10-09, *what GCC will not do with an
index*).

The candidates — twelve loops with a C and an assembly cycle estimate
each, and fifteen suggestions not yet estimated — are FORMATS.md's
(*Hand-written 68000 assembly: the candidates, estimated*).

**Prerequisites for the pass**, once for every row:

| what | why |
|---|---|
| **a `qemu-m68k` lane in `ci.sh`**: the m68k-linux CLI (TESTING.md, *The 68000 profile*, has the build line) running `run_crypt.py`, `run_privatefile.py`, the differential suite (every CRC row) and a `UNC_ARS_FORCE_SAMPLED` build (the scan) | `ci.sh` runs x86, which compiles the C path, so without this lane an assembly path is graded by nothing |
| **a timing build that can open an encrypted archive**: the autotest app with a compile-time password beside `UNC_AT_TIMING` | the tick probe (tools/vmac/README.md) is what prices a change here, and today it cannot reach any cipher |

## Formats classic Mac programs wrote that nothing here opens — leads, not findings

From the 190 entries of Macintosh Repository's *Compression & Archiving*
category, read 2026-10-12 (`companion/harvest/macrepo-compression.tsv`):
**every row below is from a program's NAME and DESCRIPTION, and none has
been held against a file.** The modern macOS programs, video compressors and
backup-to-disk tools in the category are left out, and so is what Part 1
already covers (RAR, ARJ, Zoo, cpio, disk images).

| format | programs there | here |
|---|---|---|
| BinHex 1.0/2.0 (`.hex`) and 3.0 (`.hcx`) | BinHex 2.0, OldHex 3.0 | only BinHex 4 is opened; the older two are named nowhere |
| ShrinkIt / NuFX (`.shk`, `.bxy`), Apple II | ShrinkIt | named nowhere |
| shell archives (`shar`) | unshar | named nowhere |
| yEnc | yEnc TZ | named nowhere |
| Apple Backup (Performa-era backup disks) | Apple Backup Extractor | named nowhere |
| backup sets | Retrospect 1.x/2.1, Fastback, HFS Backup, MacBack, Network DiskFit, Diamond | named nowhere |
| splitters that may add a header | MacHacha, SplitIt!, SplitsVille, Split & Join, Split&Concat | plain `.001` and DiskDoubler `SPLT` only; whether these write either is unknown |
| unidentified | GIF Blast, MacSQZ!, The Parer, RadicalSqueeze, BKOS Compress, FileCrypt, Big Hairy Installer, MacToVax | the format is not known |

Closing a row means a specimen written by the program, then the usual
question of a second reader to grade against.

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

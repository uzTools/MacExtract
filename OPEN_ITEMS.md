# OPEN_ITEMS.md — what is missing, and what is deliberately not

1. **Part 1, out of scope** — decided or impossible, recorded so nobody
   re-litigates it. Read it before starting work on a format.
2. **Part 2, open items** — what is not done or not verified, each with
   what would close it. Only OPEN items live there: a closed one moves out
   (the lesson to DECISIONS.md, the withdrawn claim to BLOCKERS.md, the
   numbers to FORMATS.md).

Nothing here stops the engine or the CLI, which are byte-exact against the
oracle across 959 fixtures in `./ci.sh`. Detail lives once — status in
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
| Zip Reduce (methods 2–5) | **named, refused per entry**; the CLI says it is out of scope | counted by content 2026-10-08: 13,014 files open with a Reduce entry, 5 in a Macintosh context, **0 written on a Macintosh**; deark reads Reduce, `unar` and Info-ZIP UnZip 6.00 refuse it (FORMATS.md, *Shrink*; DECISIONS.md 2026-10-08, *the method a Macintosh wrote once*) |
| PKWARE "strong encryption" in a zip (flag 0x40) | **named, refused per entry** | its key material is in a record nothing here parses, and XADMaster refuses it too; every other cipher these formats have is decrypted (FORMATS.md, *Encryption*) |
| Disk images (`.image`, `.img`, `.iso`, `.cdr`, `.toast`, `.dmg`, `.smi`), and Disk Copy 4.2 | **not recognised**, and not extracted | a filesystem, not a codec; the probes are kept in `attic/` (DECISIONS.md 2026-08-26, *read the volume, not the extension*). DART was in from 2026-09-09 to 2026-09-25 and left for MacMount (DECISIONS.md 2026-09-25, *the disk images that found another home*) |
| PMarc (`-pm0-`, `-pm1-`, `-pm2-`) and `-lhx-` | **not recognised** | a different family behind an LZH-shaped header; neither reached a Macintosh |
| Self-extracting LZH (an executable with an archive behind it) | **not recognised** | nothing in the file says where the first header is, unlike a zip, whose offsets are absolute — which is why a self-extracting zip is recognised since 2026-10-05 (DECISIONS.md 2026-10-05, *the scan that was already being paid for*) |
| RAR, 7z, bzip2, xz, Cabinet, Zoo, ar/`.deb`, cpio, ARJ | **named, never extracted** | not Macintosh formats, and each is served by a maintained extractor (DECISIONS.md 2026-08-26, *a name is only worth something inside the frame the user came with*; FORMATS.md, *Archives named but not extracted*) |
| Alysis SuperDisk! method 13 | **not implemented, and no specimen is wanted** | its module compresses and refuses to decompress, so nothing anywhere could grade a decoder (FORMATS.md, *Module 13*; DECISIONS.md 2026-08-29, *the specimen that would have settled nothing*) |
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

## The overlay loader: what no emulator here can answer

Two items, and both want the same thing: **a Macintosh with a 68020 or
better, running the shipped binary** (MANUAL_TESTS.md §2 and §6). The
Linux lane closed what it could on 2026-09-26 — it builds the fifteen
images, runs the real loaders through a mock Memory and Resource
Manager, extracts 20 fixtures byte-exact under `qemu-m68k`, and catches
six deliberate breaks every run (TESTING.md, *The overlay loader, off
the Macintosh*).

- **No tier with a CPU cache has ever run it.** The flush at both fixup
  sites is correct by documentation and unverified by measurement: Mini
  vMac is a 68000, the 68LC040 Emulator is documented to ignore the
  request, and the host lane has no cache — it proves the call is
  reached, which is a different claim. `fc=1 fn=4` on System 7.0.1 says
  the route exists and fired; whether it is NEEDED, only hardware says.
- **The shipped bytes RUN only on the emulator.** The host lane LOADS
  them since 2026-09-26 (`--shipped-only`, `ci.sh` variant 3d, all 30
  relocations across six images at the addresses they run at), but no
  host lane can EXECUTE a Retro68 image — entered from an m68k-linux
  binary it segfaults, measured.

**The maintainer has working hardware as of 2026-09-27**, so these stop
being "needs a machine nobody has" and become two runs somebody can do.
Short of them, read every tier sweep with the `-D UNC_AT_BUDGET` probe
fields (`wa`, `kf`, `rf`, `fc`, `fn`) rather than on the tally alone.

## StuffIt 2.0: the modules that are still only this project's own output

Everything StuffIt Deluxe 2.0.1 writes with what was in its box extracts,
graded against archives it wrote (FORMATS.md, *What an Optimizer did to the
fork*, *The three ways 2.0.1 encrypts*). `Text 1`, `Sound 1` and
`MacPaint 1` are graded on wild archives since 2026-10-06/07 (FORMATS.md,
*Two optimized archives nobody here made*, *Two more, and these the engine
UNDOES*).

| what is left | what would close it |
|---|---|
| **`Photoshop 1` and `JPEG Lossy` are graded only on archives this project made** | **a file from somebody who has one.** All 196,139 classic StuffIt archives Discmaster lists have been searched, the 112 early-stopped walks re-walked 2026-10-10; none carries either (TESTING.md, *Searching somebody else's index by content*) |
| **all five ciphers are graded only on archives this project made** — `DES`, `NewDE`, `NewDEx`, `DESex`, `PassLock` | **an encrypted archive and its password.** The same search found only `NewDE`, 8 forks in 3 wild archives with no password — the one read-me that speaks to it says the author mailed one on payment (DECISIONS.md 2026-10-07, *the key was what the archive CONTAINED*); `sitcrypt-wild-F7Menus.sit.bin` grades a refusal (FORMATS.md, *The one wild archive here that is encrypted*) |

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

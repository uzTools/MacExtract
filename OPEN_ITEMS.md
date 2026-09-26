# OPEN_ITEMS.md — what is missing, and what is deliberately not

Two kinds of thing live here, and they are kept apart on purpose:

1. **Out of scope** — decided or impossible, recorded so nobody re-litigates
   it, and the first section below because it is the thing a session most
   needs to know before starting work on a format.
2. **Open items** — a standing audit of the gaps: things not done, things done
   but not verified, and things this repository asserts more confidently than
   the evidence supports. Each says what would close it.

**Not** BLOCKERS.md, which records investigations that went wrong and the
claims withdrawn from them. Nothing here stops the engine or the CLI, which are
byte-exact against the oracle across 932 fixtures in `./ci.sh`.

Detail lives in one place per finding — status in BLOCKERS.md, reasoning in
DECISIONS.md, how to re-run in TESTING.md or `tools/vmac/README.md`, what needs
real hardware in MANUAL_TESTS.md, results in FORMATS.md — and is
cross-referenced from here rather than repeated.

**Filing something here is a decision to stop looking at it, so it had
better be true.**

**Only OPEN items live in part 2.** A closed one moves out rather than being
annotated: the lesson to DECISIONS.md, the withdrawn claim to BLOCKERS.md,
the numbers to FORMATS.md. A section that empties is the point of the file.

---

# Part 1 — Out of scope for v1

**Decided, or impossible. Not open.** Everything here is either a boundary
somebody chose or a property of a format that no evidence can change; nothing
here is closed by finding a file, and what is waiting for one is Part 2's
*"Waiting on a file this machine does not have"*. "Out of scope" is today's
answer and not a refusal — the brief has grown before, on request.

## Out by the brief

| what | status | why it stays out |
|---|---|---|
| Compression | not implemented | this is an extractor |
| Choosing which entries come out, in the Macintosh application | **not implemented; the CLI's `--only` ships** | decided 2026-09-26: the application extracts the whole archive, and a tick list is paid for by every run including the ones that never open it. The engine keeps both halves a host needs — `UncOptions.list_only`, and the skip a `begin_entry` returning >0 performs (`include/macextract.h`, *Sink*) — so this is a decision about the shell and not a missing capability. Built and graded on the branch `selective-extract`, which is kept only so its history can be read (BRANCHES.md; DECISIONS.md 2026-09-26, *the feature that was parked, and is now out*) |
| Hardware decoding — an FPU, a coprocessor, a NuBus codec card | **not implemented, and there is nothing measured for one to do** | every codec here is integer bit work: the only FP-shaped operation in the engine is Arsenic's two divides per symbol, **0.72 % of the run** against 9.9 % for the linear symbol search beside it (FORMATS.md, *What is still hot*). An FPU is also only available where it is not needed — a 68881 implies a 68020, which already has `DIVU.L`, while the 68000 that pays for `__udivsi3` has none — and the fastest tier reaches no FPU at all, running through the 68LC040 emulator. The formats' own answer to differing CPUs is a decompress-only twin that accepts every CPU, and all of those modules are implemented. A second `-mcpu=68020` build is the adjacent trade and is also out (DECISIONS.md 2026-09-23, *hardware decoding*) |
| The Macintosh 512K — 64 KB of ROM | **the interface runs; extraction needs HFS** | measured 2026-09-01, not assumed: `MaxApplZone` is `[Not in ROM]` there and Retro68 emits it as a trap, so the application dies on its second Toolbox call; behind that, `PBGetCatInfo` is HFS, which that ROM has never heard of. The branch `rom64k` guards the trap and its Standard File interface works; what remains is HFS, which a Hard Disk 20 supplies — and **nobody has run it on one**, so this stays out until hardware says otherwise (FORMATS.md, *A true Macintosh 512K*; MANUAL_TESTS.md §7). A Macintosh **128K** is out for a measured second reason: its largest single block is 63,744 B against 142,152 B of `CODE` |
| StuffIt X (`.sitx`) | **detect-only** | out by the brief |
| PKZIP 1.x **Implode** (zip method 6) | **named, refused per entry** | not a Macintosh method: it is PKZIP 1.x's, it predates deflate, and the two corpus archives carrying it are PC software. 7 entries across `4acalc.zip` and `4alnch11.zip`, graded on names and entry counts alone. **Half the premise is gone and the decision is the maintainer's**: an MIT implementation and a stored-CRC oracle for all 7 entries have been on this disk since 2026-09-22, so only "not a Macintosh method" still carries it (DECISIONS.md 2026-09-22, *the premise that stopped being true*). **What it would cost is still unmeasured** — a removal delta can be built and an addition cannot — but the comparable coders put it at **~1.5–2 KB of `CODE`, estimated, not measured**, against 6,952 B of headroom at the tightest tier |
| PKWARE "strong encryption" in a zip (flag 0x40) | **named, refused per entry** | its key material is in a record nothing here parses, and XADMaster refuses it too. Every OTHER encryption these formats have is decrypted, including WinZip's AES (FORMATS.md, *Encryption*) |
| Disk images (`.image`, `.img`, `.iso`, `.cdr`, `.toast`, `.dmg`, `.smi`), and Disk Copy 4.2 | **not recognised**, and not extracted | extracting one means a filesystem rather than a codec, and naming one is worth nothing either: a disk image is not an archive, so the name leaves a user exactly where "not recognized" does. The probes are complete, graded and kept in `attic/` (DECISIONS.md 2026-08-26, *read the volume, not the extension*). **DART was the one exception between 2026-09-09 and 2026-09-25** — a compressed DART expands to an uncompressed one, a codec with no volume in it — and it is out again: what reads a DART is a mounter, and that is MacMount's, so expanding disk images is not this program's job in any form (DECISIONS.md 2026-09-25, *the disk images that found another home*). NDIF and UDIF were prototyped on a branch and never merged, for the same reason |
| PMarc (`-pm0-`, `-pm1-`, `-pm2-`) and `-lhx-` | **not recognised** | a different family behind an LZH-shaped header. PMarc is a Japanese PC format with its own coders, `-lhx-` is UNLHA32's extension; neither reached a Macintosh |
| Self-extracting LZH (an executable with an archive behind it) | **not recognised** | the archive sits behind DOS, Amiga, Atari or X68000 machine code, and finding it means knowing each of those loaders. `unar` has a parser per platform; here the answer is to hand the `.lzh` itself to the extractor |
| RAR, 7z, bzip2, xz, Cabinet, Zoo, ar/`.deb`, cpio, ARJ | **named, never extracted** | none is a Macintosh archive format, none carries a resource fork or Finder metadata, and every one is served by a maintained extractor on any machine that can run one. NAMING them is in scope (DECISIONS.md 2026-08-26, *a name is only worth something inside the frame the user came with*; FORMATS.md, *Archives named but not extracted*) |
| Alysis SuperDisk! method 13 | **not implemented, and no specimen is wanted** | its module compresses and REFUSES to decompress — `_Debugger` at its own 0xd4 — so no Alysis expander in reach can read what it writes, and nor can this engine or any other module in the library. Streams can be made here at will and there is nothing whatever to grade one against. It is reachable from Alysis's own compress path (level 11 of INIT 32's table at +0xf2e), so a file COULD exist; reading one would mean inverting that compressor with no second reader anywhere, for a codec no archive in the corpus uses (FORMATS.md, *Module 13*; DECISIONS.md 2026-08-29, *the specimen that would have settled nothing*) |
| Zip64 addressing past 4 GB | **the counts and the per-ENTRY escape are read; over-4-GB fields are refused** — `UNC_ERR_UNSUPPORTED` per archive, `UNC_ERR_TOOLARGE` per entry — and `unc_zipseg_describe` still answers `UNC_ERR_UNSUPPORTED` for a spanned set | zip's own shape is what keeps it out: the directory fields are 32-bit and the Zip64 escape is read as `uint32` halves, so reading past 4 GB properly is a format change rather than a type change. The type is not the obstacle — `UncIO` carries `unc_off_t`, 64-bit in the CLI, for +0.51 % of text and 0 bytes of heap (DECISIONS.md 2026-08-28, *what a width costs*). Reading the halves is what makes a 70,000-entry archive extract, and a 3.4 GB one (FORMATS.md, *Size limits*); tar, whose positions are a running sum, reaches past 4 GB today |

Everything detect-only is **named** by `unc_sniff`, and both front ends say
the name: the CLI prints *"recognized as RAR, which v1 cannot extract"* and
the Macintosh application's alert reads *"MacExtract cannot open RAR files."*
(photographed on System 6.0.8). Extraction returns cleanly unsupported either
way.

## Limits of the formats themselves

- **A raw brotli stream cannot be identified, by this or any program.** RFC
  7932 section 9.1 is its entire stream header: one to seven bits of WBITS,
  and nothing else. No magic number, no signature, no version byte, no
  length. So `unc_sniff` will never name a `.br`, and the reason is the
  format rather than a missing reference. **What would change it:** nothing
  in the format. A host that trusts the filename could act on `.br`, which
  is a naming question and not an identifying one.
  `reference/notes/brotli_rfc7932.txt` is kept as the evidence for a
  negative.

- **A cut tar cannot be noticed, by this or any program.** A tar has no
  directory, no entry count and no length of its own, so a file that
  stops after five members reads exactly as a tar with five members. The
  two 512-byte zero blocks that POSIX ends an archive with would be the
  evidence — and they are not reliably there: `derived-popper-1.7.tar`,
  a real corpus archive, ends with **zero** trailing zero bytes, so
  requiring them would call it truncated. `unar` accepts a cut tar too.
  Every other format in the corpus notices a cut at three sampled cut
  points (`tools/run_truncation.py`, in `ci.sh`). **What would change
  it:** nothing in the format. A host that knows what the download was
  SUPPOSED to weigh could compare, which is a question about the
  transfer and not about the archive.

- **One 46-byte window of a DiskDoubler DDA2 archive is ambiguous.** A
  DDA2 archive normally ends with a 0xBBBB record, and a walk that never
  reaches one is reported truncated — except that an archive may
  legitimately end without it, leaving fewer than the 46 bytes one record
  needs after its last entry. `derived-DD_Expand.sea` ends exactly so and
  `unar` reads it, so a cut that lands in that same window is
  byte-for-byte a valid ending; `ddtf-ddpro411dd3.dd` cut to a fifth is
  the measured case, and every other cut point in the corpus is caught.
  **What would change it:** nothing in the format — the two files are
  identical there. The rule that tries is DECISIONS.md 2026-08-29, *a cut
  archive*.

- **A uuencoded set missing a MIDDLE part decodes short, and silently.** A
  document posted in several parts joins and decodes — the mail headers
  between parts are stepped over — but uuencode carries no length and no
  checksum anywhere, so nothing can notice that a part never arrived. A
  missing LAST part IS caught: the terminator and `end` live there. Asserted
  rather than described — `tools/run_uu.py` builds a gapped set and requires
  exactly this result, so the day the format turns out to have a check, the
  suite says so. **What would change it:** nothing in the format. A host that
  knows the parts were numbered `1/5` could check the count, which is a naming
  question and not a decoding one.

---

# Part 2 — Open items

---

## The overlay loader: what the host lane still cannot reach

**The Linux-side gap CLOSED on 2026-09-26.** `tests/run_overlay_host.sh`
builds the fourteen images with the m68k-linux toolchain from the same sources
and the same flags, runs the real loaders unmodified against them through a
mock Memory and Resource Manager, and extracts 17 fixtures through the images
byte-exact under `qemu-m68k` in both lifetimes — plus one fixture per image
against the resident build. Six deliberate breaks are caught every run
(TESTING.md, *The overlay loader, off the Macintosh*; DECISIONS.md 2026-09-26,
*the loader that could be run after all*). Three things are still open, and
only the first is about the mechanism:

**No tier with a CPU cache has ever run it.** The flush at both fixup sites is
correct by documentation and unverified by measurement: Mini vMac is a 68000,
the 68LC040 Emulator is documented to ignore the request, and the host lane has
no cache either — it counts the call and proves it is reached, which is a
different claim. `fc=1 fn=4` on System 7.0.1 says the route exists and fired.
MANUAL_TESTS.md §2 is the only instrument for whether it is NEEDED.

**The shipped bytes RUN only on the emulator.** Since 2026-09-26 the host
lane does load them: `--shipped-only` (`ci.sh` variant 3d) hands the Retro68
images and bundle to the real loader and checks the bundle's directory and all
30 relocations across its six images at the addresses they run at — which the
m68k-linux build cannot stand in for, since it emits 15 in one image. What no
host lane can do is EXECUTE a Retro68 image: entered from an m68k-linux binary
it segfaults (measured 2026-09-26). So the decoders' own behaviour in the
shipped bytes is the tiers' evidence and nothing else's.

**What would close those two:** a Macintosh with a 68020 or better, and a
copy of the shipped binary run on one (MANUAL_TESTS.md §2 and §7). Short of
that, read every tier sweep with the `-D UNC_AT_BUDGET` probe fields (`wa`,
`kf`, `rf`, `fc`, `fn`) rather than on the tally alone.

**`tools/run_tiers.py --shipped` predicts the shipped application at the two
tiers a machine has run it on, and at no others.** Since 2026-09-26 it models
a budget per tier PER FORMAT and per envelope layer, and reproduces the
v0.33.0 binary's 69/71 at System 3.0 / 512 KB and 71/71 at the floor target,
refusing the same fixtures by name; the resident lane is kept beside it as the
engine's regression detector (TESTING.md, *The tiers a budget predicts*). What
is still open is the evidence under the model: the per-format gains rest on
three granted budgets measured on 2026-09-24 on the branch this merged from,
which has since lost DART, and the arithmetic reproduces them only up to a
1,138 B residue nothing accounts for. **What would close it:** one Mini vMac
run of the shipped binary at `sys6-512K`, where the model predicts 66/71
against the resident build's measured 64/71 (FORMATS.md, *512 KB machines*) —
a tier it does not assert precisely because nothing has run it — and the three
granted budgets re-taken on the current tree. A machine that says anything
other than 66/71 there is the finding, and BLOCKERS.md is where it goes.

## What is still XADMaster's, and what would have to replace it

**Asked for 2026-09-19**: shed as much XADMaster-transcribed code as
possible — for the gains where they exist, and for the licence if it ever
adds up — **with no regression taken for the licence's sake**. The
-lh1- coder went first (DECISIONS.md 2026-09-19, *the tree that was
Yoshizaki's*): faster, smaller and lighter, so it would have been taken
on its merits alone. This is the inventory the rest of that work runs
against; the licence changes only when the last row is gone, and rows
carrying `macutils` have the same question (its README: "for some parts
of it the GNU software license does apply").

A file leaves this table when nothing in it is XADMaster's or macutils'
any more — the record of what that took lives in NOTICE and in
DECISIONS.md, not here (CLAUDE.md, *closing an item means moving it*).
Gone this way: `unc_huffman.c` and `unc_lzw.c`, `src/fmt_cpt.c` (the
format's three published wiki pages, `tools/derive_cpt.py`) and
`src/fmt_now.c` (this project's own measured description,
`tools/derive_now.py`) and, on 2026-09-26, `src/unc_encinfo.c`, whose
only citation was second-hand — to a comment in `fmt_cpt.c` that had
stopped saying it six days earlier.

**Membership is grepped, not remembered, since 2026-09-26**:
`grep -n 'Source:.*\(XAD\|macutils\)' src/*.c src/*.h` is what a row
is checked against. It returned 15 files and **8 had no row**; two more
(`unc_lzah.c`, `unc_encinfo.c`) do not put `Source:` and the name on one
line and needed a second spelling. The table had been the DECODER list,
so the shared primitives, the two probes and the detect-only signatures
were never in it (BLOCKERS.md, *Withdrawn claims*; DECISIONS.md 2026-09-26,
*the inventory that listed the decoders*).

| file | XADMaster code in it | other reference on this machine | gain plausible? |
|---|---|---|---|
| `unc_lzdyn.c` | `-lh2-`/`-lh3-` from `XADLZHOldHandles.m` | LHa for UNIX only (its own licence); lhasa has neither | none — no corpus archive uses them. **What they cost is measured, re-measured 2026-09-23: 3,476 B of `CODE` and 28 B of A5**, i.e. **3,504 B** of a 1 MB Mac Plus's budget, from a build with the file and its two dispatch arms removed. Not the weight of a replacement — there is none to build — but what DELETING the two formats would give back. The total is 2026-09-20's to the byte; the 4 B that moved between the columns is rodata alignment under changed text. Set that against the overlays the application now ships, which are worth 84–103 KB (FORMATS.md, *Overlays*) — and against the fact that LHa for UNIX writes `-lh2-` today and `tools/run_lzh.py` grades us against one, so dropping them refuses a file that can still be made. **Settled 2026-08-25 and confirmed 2026-09-23: kept** — and this row should not have re-asked it. LHa for UNIX writes `-lh2-` today and `tools/run_lzh.py` writes `-lh3-`, so `ci.sh` grades 21 entries of the two every run — a method this project can MAKE a file in is one a user can be handed a file in, and "no corpus archive uses them" was never the same claim. **So this row cannot close**: lhasa implements neither method and LHa for UNIX is under its own licence, so there is nothing to rewrite the file FROM (DECISIONS.md 2026-09-23, *the 3,504 bytes that stay*) |
| `fmt_lzh.c` | **none since 2026-09-22**, bar one rule with no specimen: a NUL inside a level 0/1 name field ends the name, which is `XADLZHParser.m`'s and which **0 of the 140 such fields in the 156 archives here** contains. The DECODERS left on 2026-09-19 | **the format's own published description** — `reference/lha/header.doc.euc`, Masaru Oki's `header.doc` of 2 March 1992, levels 0/1/2 field by field with the extended-header types, the OS IDs and the method IDs; **lhasa (ISC)** for the four things it does not cover | **taken, whole file, at zero cost on every axis** — the walk needed no change, only a description: a reader written from the document plus lhasa reads 191 entries of 156 archives with no disagreement (`tools/derive_lzh.py`, `docs/formats/lzh-header.md`). The decoders were taken earlier for **−17.8 to −46.4 % of the 68000's instructions for +140 B** (DECISIONS.md 2026-09-19, *the match that was walked twice*) |
| `fmt_packit.c` | **the two CRCs' polynomial, the resync rule and both ciphers, and nothing else, since 2026-09-21.** The container left this row that day, and the Huffman tree and the header-inside-the-stream fact on 2026-09-20 | **the format's own published description** — `reference/notes/packit_unpackit.txt`, appendices B and C of a 1986 freeware manual, named all along by `reference/notes/PackIt.md`, which this project fetched with its first batch of references and never read past | **taken: 38 of 38 forks** of the corpus's four archives read from the appendices plus the four corrections they need (`docs/formats/packit.md`, `tools/derive_packit.py`). "The app is not here" was the wrong question (DECISIONS.md 2026-09-21, *the manual for the other machine*) |
| `fmt_sit.c` | **none since 2026-09-22.** Method 6's framing was the last of it and left that day; the RLE90 filter and method 6's code book left on 2026-09-21, the container, method 13 and its tables, method 3's tree and method 8's coder on 2026-09-20 — bar three rules of method 8 no specimen reaches | `docs/formats/stuffit-method-6.md`, written against `reference/deark/modules/stuffit.c` (MIT); the rest is the format's own published description (The Unarchiver's wiki, fetched). StuffIt Deluxe 3.5.1 also runs here (`sitcrypt.py`) | **taken, whole file.** "No other reader anywhere" was false for method 13 — 897 forks across 103 archives read from the published description alone (DECISIONS.md 2026-09-20, *forty pages nobody had listed*) — and false for method 6, which deark implements under MIT. The code book was taken 2026-09-21 and priced: **code +408 B, A5 −1,000 B, net −592 B** (FORMATS.md, *StuffIt classic: method 6*). The **framing** followed on 2026-09-22 and cost nothing on any axis, because nothing executable had to change: a reader written from deark and the container page alone reads all 11 method-6 forks (`tools/derive_sit6.py`), and the three places this engine is stricter than both references are measured rather than transcribed (DECISIONS.md 2026-09-22, *the framing that needed no rewrite*) |
| `fmt_sit5.c` | **the ENCRYPTED archive only, since 2026-09-22** — where the password hash sits behind two optionally-present blocks, and the MD5-of-MD5 that grades a password. No corpus archive sets the bit. `sit_arsenic.c` was rewritten from Russotto's write-up on 2026-09-19, −36.7 % of a2basic's engine ticks (DECISIONS.md, *the rank that was walked a byte at a time*) | **the format's own published description** — `reference/notes/sit5_specs_theunarchiver.md`, the wiki page `reference/notes/StuffIt.md` has named in its *Sources* list all along. **Not Russotto's write-up**, which is method 15 start to finish and describes no container at all | **taken, at zero cost on every axis**: a reader written from that page alone reads all 31 StuffIt 5 fixtures, **525 entries**, agreeing with the oracle on every path and both fork lengths (`tools/derive_sit5.py`, `docs/formats/stuffit5-container.md`). The page needs one correction — its archive-header table gives offset 84 twice |
| `fmt_dd.c` | **the `DDAR` `0x20` raw-fork shape, and nothing else, since 2026-09-22** — four offsets nothing anywhere here sets. The coders, the containers and the folder records all left this row between 2026-09-20 and 2026-09-22 | **the format's own published description** for `ADn` and `DDn` — "documented nowhere else" was false. The containers have none: the wiki names three pages that do not exist on it, so the description is this project's own, measured against DiskDoubler 3.7, 4.0 and Pro 4.1, which run here | **taken twice**: 39 of 39 forks for the coders, and **643 assertions over all 91 DiskDoubler fixtures, 0 disagreements** for the containers (`docs/formats/diskdoubler-dd.md`, `docs/formats/diskdoubler-container.md`). What is left has no SPECIMEN rather than no description, and the search for one is measured: five shapes offered to 3.7 all came back with the flags word `0x0000`, and the oldest DiskDoubler reachable anywhere (ß05, Salient 1990) cannot write an archive at all. **"What would close it is a 1.x or 2.x DiskDoubler" is withdrawn** — a 2.x would not write a `DDAR` record of any flags (BLOCKERS.md, *Withdrawn claims*; DECISIONS.md 2026-09-22, *the version that could not have written it* and *the page that was never written*) |
| `fmt_arc.c` | **Crunch 5/6/7 and Crush (PAK's LZW)**; the method numbers and the CRC contract. The member header, RLE90, Squeeze (4), Crunch (8) and Squash (9) left this row 2026-09-20 for `docs/formats/arc-container-and-coders.md` | **deark (MIT)** for Distilled and Trimmed, and — unlooked-at until 2026-09-22 — for 5 and 6 as well; it leaves 7 and Crushed NULL exactly as this row does. **ARC 5.21q itself** writes methods 4, 8 and 9 to order; nothing reachable writes 5/6/7 | small, and **not taken, decided 2026-09-22**: the row would not close (7 and Crush have no implementation anywhere), so the licence would not move, and **nothing can grade a rewrite** — no corpus or reference archive uses 5/6/7. The route that would exist is an ENCODER for 5/6 from the same description, decoded by deark: two implementations agreeing on a stream neither wrote. What the two existing readings already say, and where they agree to the term: `docs/formats/arc-container-and-coders.md`, *Methods 5 and 6, read in two implementations* |
| `unc_crypt.c` | **Four XADMaster files, twelve until 2026-09-23 and five until 2026-09-26**, and none supplies a byte of `src/crypt_tables.h`: `XADStuffItDESHandle.m` (the nibble key schedule and the key derivation), `XADStuffIt5Parser.m`, `XADPackItParser.m` (keytr1) and `XADXORHandle.m` (ARC's garble). What has already left, and the document each went to, is `src/unc_crypt.c`'s own header; the withdrawn readings of this cell are in BLOCKERS.md, *Withdrawn claims* | the standards themselves, in `reference/notes/`: FIPS 46-3, RFC 1321, RFC 2104, RFC 2898, RFC 3174, APPNOTE.TXT §6.1, draft-kaukonen-cipher-arcfour-03, `winzip_aes.txt`, and **FIPS 197 since 2026-09-26**. FIPS 180 is not among them and is not wanted: SHA-1 came from RFC 3174. The AES-CTR counter's endianness and start value are stated nowhere here | **taken four times**: once at −416 B of code, and three times since at zero cost on every shipped axis (DECISIONS.md 2026-09-19 *the DES that was only wearing a disguise*; 2026-09-23 *the tables that were the standard's* and *the third statement of the same constants*; 2026-09-26 *the AES that was never Gladman's*, where the crypt `OVLY` image came out byte-identical at 9,800 B). **The row cannot close**: StuffItDES reads all 64 key bits where PC-1 drops eight, so it is no permuted-key standard schedule, and PackIt's keytr1 has no other statement — its manual names "simple encryption" and describes none |
| `unc_util.c`, `unc_internal.h` | **the three CRC tables and the bit reader, never inventoried until 2026-09-26.** `CRC.m` and macutils' `arc_updcrc` for CRC-16/XMODEM (MacBinary, BinHex 4, PackIt), CRC-32 (zip, gzip, Arsenic, Compact Pro) and CRC-16/ARC (StuffIt classic's header), called from 11 other files; `CSInputBuffer.h` and macutils' `de_huffman.c` for the MSB-first reader | **all three polynomials are published and two are on this disk**: `reference/notes/binhex40_lewis.txt` states CRC-16/XMODEM bit by bit with its initial register, `zip_appnote.txt` states CRC-32 and its `0xdebb20e3` residue, and deark (MIT) and lhasa (ISC) each BUILD the 0xA001 table from its polynomial rather than listing it | **unmeasured, and expected to be 0 B**: the tables are already described in the file as "generated mechanically from the polynomials" and all three published check values are asserted (`tests/unit_main.c`, `tests/unit_formats.c` — **not** the `tests/unit_util.c` the file named until 2026-09-26, which has never existed), so nothing executable would change — the crypt tables' case again (DECISIONS.md 2026-09-23, *the tables that were the standard's*) |
| `fmt_binhex.c`, `fmt_uu.c`, `fmt_mime.c` | **macutils' `hexbin`, five rules about text that has been mailed** rather than about an encoding: the line-ending rule and the unterminated last line (`readline.c`), `mu_convert()`, the uu terminator, the skip of a line with "intermediate garbage" and the scan for a second document in one input (`hqx.c`, `hexbin.c`) | none: RFC 1741 and `binhex40_lewis.txt` define the ENCODING, and neither says what a decoder does with a posting — the same shape as the four tolerances in the row below | none for the licence unless a second reader of mailed BinHex turns up; the rules themselves are graded by `tools/run_uu.py`'s gapped sets and the multi-part fixtures |
| `fmt_foreign.c`, `fmt_sit_probe.c`, `fmt_packit_probe.c` | **seven formats' detect-only signatures and two recognisers**, each cited to the XADMaster parser it came from: ARJ, bzip2, RAR (three signatures across two parsers), 7-Zip, xz, Cabinet and Zoo, plus `recognizeFileWithHandle` for StuffIt and for PackIt | deark for Zoo, already cited beside `XADZooParser.m`; the rest are in each format's own published description, none of which is on this disk | none — a magic number is a fact and not code, the answer the `fmt_stubs.c` row already gives; what would close it is a citation per signature, not a rewrite |
| `unc_lzah.c` | **the window preload for -lh1- and StuffIt method 5**, `resetLZSSHandle`'s pattern, quoted with XADMaster's own TODO beside it. The tree machinery left on 2026-09-19 for LZHUF.C, and **NOTICE said the preloads had left with it** — they had not (BLOCKERS.md, *Withdrawn claims*) | **none for this method.** LHa for UNIX writes the same five steps in `larc.c`'s `decode_start_lz5` — for LArc's -lz5-, not for -lh1- — and lhasa fills the -lh1- buffer with spaces instead (`lh1_decoder.c`); so the pattern is published and its APPLICATION to -lh1- and method 5 is XADMaster's, and LHa for UNIX is under its own licence anyway — the `unc_lzdyn.c` row's position exactly | none — and the pattern is load-bearing: a Trimmed member takes zeros and not the pattern, which is what tells the two dialects apart |
| `fmt_macbinary.c`, `fmt_applesingle.c`, `fmt_sitseg.c`, `fmt_stubs.c` | what the 2026-09-19 re-citation could not move (DECISIONS.md, *the facts that were somebody else's to state*): three tolerances no specification supports — the MacBinary CRC-16/0xA001 fallback, its nonzero-date test, the byte-swapped AppleSingle header — and the StuffIt split header. **Now Compress's detect-only probe left this row on 2026-09-21**: every field it tests — the 24-byte file header, the entry record and the byte-sum checksum at +106 of it — is measured in `docs/formats/now-compress.md` off nine archives | none found for any of them; `fmt_exo.c` and `fmt_zipseg.c` left this row for their own specifications, and `fmt_stubs.c`'s other two probes for deark (StuffIt X) and macutils' `dd.h` (DiskDoubler). **`fmt_binhex.c` was recorded as having left it too and had not** — two macutils citations were still in the file on 2026-09-26, and it has a row of its own below | none — the rest is facts, not code, so the licence never rested on it |

**What would close it:** one row at a time, each priced before it is kept and
graded by the suites that already cover the format — the `-lh1-` row is the
template. Of the rows once filed as having no other description, only **Now
Compress** never had a published one, and it fell to reverse-engineering
against the application on 2026-09-21.

## What WinZip's AES costs a Macintosh Plus

**2,150 B of `CODE`, measured 2026-09-23**: 1,304 for SHA-1, HMAC and
PBKDF2 and 846 for AES, out of `unc_crypt.c`'s 7,158 (FORMATS.md,
*Resident memory*). Nothing else in the engine uses any of it — the four
other hashes and ciphers are 996 B of DES, 546 of MD5 and 812 for the
five small ones — so it is the clearest single-capability price in the
file.

**And that is all this is: a price, not an open question.** WinZip AES
was settled on **2026-08-23**, in the commit that added it — *"so no
encryption a zip can carry is refused"* — and `ci.sh` has graded it
every run since at four configurations (AES-128/192/256 and a stored
AES-256), on fixtures **7-Zip writes**, with a flipped ciphertext byte
the authentication code must catch (`tools/run_crypt.py`). This section
carried "dropping a format the engine already extracts is the
maintainer's call ... nothing here will take it" until 2026-09-23, which
re-opened that decision on the byte axis and named nothing that had
changed since it was taken — the same failure as the `unc_lzdyn.c` row
above, which this text cited as its precedent (DECISIONS.md 2026-09-23,
*the 3,504 bytes that stay*). The reachability argument is in fact
WEAKER here than there: "a System 6 machine will rarely meet" a 2003 zip
feature is a claim about what is in reach, and any copy of 7-Zip or
WinZip writes one, where `-lh2-` needed a fork this project patched
itself.

## Waiting on a file this machine does not have

**Not scope decisions, and not effort.** Everything here is written or
writeable; what is missing is something to grade it against. They sit together
across formats because that is how they close — by somebody finding a file,
and the finding usually arrives from outside the format it settles. The
question to bring here is *what did I just find?*

Each says which of the two is missing, because the searches are different:

- a **reference** — a spec, an implementation, or a self-extracting specimen,
  which is one; rule #1 forbids writing a format without it;
- a **gradeable specimen** — a file written by something else, so our output
  has something to be wrong against.

None of this is impossible here: a download would do it.

**Four questions before filing anything here**, each of which has emptied this
section at least once: is there an implementation that could be **FED**
(DECISIONS.md, methods 3, 4 and 5); is *"X does not survive"* a claim about
somebody's **search** (BLOCKERS.md, SuperDisk!'s compressor); does the search
name the **right tool** (BLOCKERS.md 2026-08-25); and **have you looked at
all** (BLOCKERS.md, the ARC 7 row, filed and disproved the same day).

- **A SpaceSaver file written by SpaceSaver.** Every codec is graded against
  Aladdin's own modules (FORMATS.md, *StuffIt SpaceSaver*), so what rests on
  this is the CONTAINER: the method the application picks for its CPU, the
  data fork's length rounded up to 256 bytes, the 84-byte header, and the
  type, creator and Finder flags it moves aside — all currently read from
  containers this project builds itself. **Nothing here can make the
  application compress anything**; about twenty emulator runs are accounted
  for in BLOCKERS.md, and the request now sits in MANUAL_TESTS.md §6.
  Missing: a **gradeable specimen** — one SpaceSaver file, with the original
  beside it.

- **AppleLink `.pkg`: one file, which would settle two questions.**
  Named from Aladdin's own recogniser (FORMATS.md, *AppleLink packages*),
  and detect-only because nothing here can grade a decoder. Three measured
  things suggest there is nothing to decode — that a package is a transfer
  manifest naming files beside it rather than a container — in which case
  this closes as a property of the format (DECISIONS.md 2026-08-23,
  *AppleLink `.pkg`, named at last*). Missing: a **gradeable specimen**,
  which answers both. **Not** something to be produced here: a package
  written on this machine was offered to all three of Aladdin's own
  commands that run a translator, each in a boot where a control
  succeeded, and none of them read it — seven boots, and what PKG Expand
  asks for turns out to be a FOLDER (DECISIONS.md 2026-09-01, *the
  package that cannot be handed over*).

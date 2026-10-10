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
byte-exact against the oracle across 959 fixtures in `./ci.sh`.

Detail lives in one place per finding — status in BLOCKERS.md, reasoning in
DECISIONS.md, how to re-run in TESTING.md or `tools/vmac/README.md`, what needs
real hardware in MANUAL_TESTS.md, results in FORMATS.md — and is
cross-referenced from here rather than repeated.

**Filing something here is a decision to stop looking at it, so it had
better be true.** Five questions have each emptied a row at least once: is
there an implementation that could be **FED** (DECISIONS.md, methods 3, 4 and
5); is *"X does not survive"* a claim about somebody's **search**
(BLOCKERS.md, SuperDisk!'s compressor); does the search name the **right
tool** (BLOCKERS.md 2026-08-25); **have you looked at all** (BLOCKERS.md, the
ARC 7 row, filed and disproved the same day); and — added 2026-09-26, when
the whole *waiting on a file* section went — **was the search by NAME?** A
format that renames nothing is invisible to every index built on names and
plain to one built on magic. **That one is worth asking twice**: on
2026-10-06 it emptied a row that had been written in the same entry as
the lesson, about the one format of the two that never got the magic
search (BLOCKERS.md). A sixth, added the same day when the last StuffIt 5
row went: **is the corpus the claim was measured on the corpus that is
here now?** This one grows for unrelated reasons — installer payloads,
reference downloads, emulator output — so *"none of the 47 scanned"* was
a fact about 2026-09-27 and false eight days later (BLOCKERS.md).

**Only OPEN items live in part 2.** A closed one moves out rather than being
annotated: the lesson to DECISIONS.md, the withdrawn claim to BLOCKERS.md,
the numbers to FORMATS.md. A section that empties is the point of the file.

---

# Part 1 — Out of scope for v1

**Decided, or impossible. Not open.** Everything here is either a boundary
somebody chose or a property of a format that no evidence can change; nothing
here is closed by finding a file. **Nothing is waiting for one any more**:
that section emptied on 2026-09-26, when both files it held out for turned up
in somebody else's index (DECISIONS.md 2026-09-26, *the magic in somebody
else's index*). "Out of scope" is today's answer and not a refusal — the brief
has grown before, on request.

## Out by the brief

| what | status | why it stays out |
|---|---|---|
| Compression | not implemented | this is an extractor |
| Choosing which entries come out, in the Macintosh application | **not implemented; the CLI's `--only` ships** | decided 2026-09-26: the application extracts the whole archive, and a tick list is paid for by every run including the ones that never open it. The engine keeps both halves a host needs — `UncOptions.list_only`, and the skip a `begin_entry` returning >0 performs (`include/macextract.h`, *Sink*) — so this is a decision about the shell and not a missing capability. Built and graded on the branch `selective-extract`, which is kept only so its history can be read (BRANCHES.md; DECISIONS.md 2026-09-26, *the feature that was parked, and is now out*) |
| Hardware decoding — an FPU, a coprocessor, a NuBus codec card | **not implemented, and there is nothing measured for one to do** | every codec here is integer bit work: the only FP-shaped operation in the engine is Arsenic's two divides per symbol, **0.72 % of the run** against 9.9 % for the linear symbol search beside it (FORMATS.md, *What is still hot*). An FPU is also only available where it is not needed — a 68881 implies a 68020, which already has `DIVU.L`, while the 68000 that pays for `__udivsi3` has none — and the fastest tier reaches no FPU at all, running through the 68LC040 emulator. The formats' own answer to differing CPUs is a decompress-only twin that accepts every CPU, and all of those modules are implemented. A second `-mcpu=68020` build is the adjacent trade and is also out (DECISIONS.md 2026-09-23, *hardware decoding*) |
| The Macintosh 512K — 64 KB of ROM | **the interface runs; extraction needs HFS** | measured 2026-09-01, not assumed: `MaxApplZone` is `[Not in ROM]` there and Retro68 emits it as a trap, so the application dies on its second Toolbox call; behind that, `PBGetCatInfo` is HFS, which that ROM has never heard of. The branch `rom64k` guards the trap and its Standard File interface works; what remains is HFS, which a Hard Disk 20 supplies — and **nobody has run it on one**, so this stays out until hardware says otherwise (FORMATS.md, *A true Macintosh 512K*; MANUAL_TESTS.md §6). A Macintosh **128K** is out for a measured second reason, CORRECTED 2026-10-06: it is the heap TOTAL, not one segment. The shipped build's `CODE` resources and A5 world come to 74,940 B against `ApplLimit − ApplZone` = 78,568 B, and the eager loader then asks for the `'OVLY'` bundle as one block, whose size is FORMATS.md's and not repeated here (*Overlays*): a copy quoted here went stale twice in three days. The segment that used to be the reason — 142,152 B against a largest single block of 63,744 B — is 48,888 B since the overlays and would now be granted (FORMATS.md, *A Macintosh 128K*) |
| StuffIt X (`.sitx`) | **detect-only** | out by the brief |
| Zip Reduce (methods 2–5) | **named, refused per entry**; the CLI says it is out of scope rather than asking for a specimen | counted by content on 2026-10-08: **13,014** files in Discmaster's index open with a Reduce entry, **5** of them sit in a Macintosh context, and **all 5 are DOS archives** of DOS programs on Mac CD-ROMs — **0 written on a Macintosh**, where Shrink, counted the same way, has one (FORMATS.md, *Shrink*). deark reads Reduce; `unar` and Info-ZIP UnZip 6.00 refuse it (DECISIONS.md 2026-10-08, *the method a Macintosh wrote once*) |
| PKWARE "strong encryption" in a zip (flag 0x40) | **named, refused per entry** | its key material is in a record nothing here parses, and XADMaster refuses it too. Every OTHER encryption these formats have is decrypted, including WinZip's AES (FORMATS.md, *Encryption*) |
| Disk images (`.image`, `.img`, `.iso`, `.cdr`, `.toast`, `.dmg`, `.smi`), and Disk Copy 4.2 | **not recognised**, and not extracted | extracting one means a filesystem rather than a codec, and naming one is worth nothing either: a disk image is not an archive, so the name leaves a user exactly where "not recognized" does. The probes are complete, graded and kept in `attic/` (DECISIONS.md 2026-08-26, *read the volume, not the extension*). **DART was the one exception between 2026-09-09 and 2026-09-25** — a compressed DART expands to an uncompressed one, a codec with no volume in it — and it is out again: what reads a DART is a mounter, and that is MacMount's, so expanding disk images is not this program's job in any form (DECISIONS.md 2026-09-25, *the disk images that found another home*). NDIF and UDIF were prototyped on a branch and never merged, for the same reason |
| PMarc (`-pm0-`, `-pm1-`, `-pm2-`) and `-lhx-` | **not recognised** | a different family behind an LZH-shaped header. PMarc is a Japanese PC format with its own coders, `-lhx-` is UNLHA32's extension; neither reached a Macintosh |
| Self-extracting LZH (an executable with an archive behind it) | **not recognised** | the archive sits behind DOS, Amiga, Atari or X68000 machine code, and finding it means knowing each of those loaders. `unar` has a parser per platform; here the answer is to hand the `.lzh` itself to the extractor. **This is a fact about LZH and not about executables**, which is why a self-extracting ZIP is recognised since 2026-10-05 and this row still stands: an LZH is a chain from its first header and nothing in the file says where that header is, where every offset in a zip is absolute from the start of the file and the record that gives them is at the end (DECISIONS.md 2026-10-05, *the scan that was already being paid for*) |
| RAR, 7z, bzip2, xz, Cabinet, Zoo, ar/`.deb`, cpio, ARJ | **named, never extracted** | none is a Macintosh archive format, none carries a resource fork or Finder metadata, and every one is served by a maintained extractor on any machine that can run one. NAMING them is in scope (DECISIONS.md 2026-08-26, *a name is only worth something inside the frame the user came with*; FORMATS.md, *Archives named but not extracted*) |
| Alysis SuperDisk! method 13 | **not implemented, and no specimen is wanted** | its module compresses and REFUSES to decompress — `_Debugger` at its own 0xd4 — so no Alysis expander in reach can read what it writes, and nor can this engine or any other module in the library. Streams can be made here at will and there is nothing whatever to grade one against. It is reachable from Alysis's own compress path (level 11 of INIT 32's table at +0xf2e), so a file COULD exist; reading one would mean inverting that compressor with no second reader anywhere, for a codec no archive in the corpus uses (FORMATS.md, *Module 13*; DECISIONS.md 2026-08-29, *the specimen that would have settled nothing*) |
| Zip64 addressing past 4 GB | **the counts and the per-ENTRY escape are read; over-4-GB fields are refused** — `UNC_ERR_UNSUPPORTED` per archive, `UNC_ERR_TOOLARGE` per entry — and `unc_zipseg_describe` still answers `UNC_ERR_UNSUPPORTED` for a spanned set | zip's own shape is what keeps it out: the directory fields are 32-bit and the Zip64 escape is read as `uint32` halves, so reading past 4 GB properly is a format change rather than a type change. The type is not the obstacle — `UncIO` carries `unc_off_t`, 64-bit in the CLI, for +0.51 % of text and 0 bytes of heap (DECISIONS.md 2026-08-28, *what a width costs*). Reading the halves is what makes a 70,000-entry archive extract, and a 3.4 GB one (FORMATS.md, *Size limits*); tar, whose positions are a running sum, reaches past 4 GB today |

Everything detect-only is **named** by `unc_sniff`, and both front ends say
the name: the CLI prints *"recognized as RAR, which v1 cannot extract"* and
the Macintosh application's alert reads *"MacExtract cannot open RAR files."*
(photographed on System 6.0.8). Extraction returns cleanly unsupported either
way.

## Limits of the formats themselves

- **An encrypted classic StuffIt archive that has lost its RESOURCE
  FORK cannot be decrypted, at any password, by anything.** The block
  that verifies a password is the archive's own `'MKey'` resource — in
  its resource fork, not in the stream — so a `.sit` copied onto a
  file system without forks is missing the key material, and this
  engine says *"encrypted by a scheme we cannot read"* rather than
  asking for a password it could not use. Measured 2026-10-07 over all
  three schemes: `NewDE` and StuffIt Deluxe 3.5.1's built-in both
  refuse forkless with the right password and both decrypt byte-exact
  once the fork is beside them; `PassLock` is the exception and needs
  nothing, because it enciphers nothing (FORMATS.md, *Encryption*).
  **The fork counts as present** in a MacBinary or BinHex envelope, or
  as the `NAME.rsrc` / `._NAME` sidecar this CLI writes when it takes
  one off (`load_mkey`, `cli/main.c`). **What would change it:**
  nothing in the format. This is why `sitcrypt-wild-F7Menus.sit.bin` is
  the MacBinary copy and not the bare `.sit` on the other disc — a
  password for that one would have been useless.

  **And it is the only one of the eight ciphers that has this
  problem**, which is worth knowing before anyone generalises it.
  Measured 2026-10-07 from a bare file with no fork anywhere:
  StuffIt 5's RC4 decrypts (its verifier is MD5 of the archive key, in
  the header), and so do both of PackIt's, XOR and DES. The remaining
  three are structural rather than measured — a zip and an ARC are
  byte streams with no fork to lose, and Compact Pro *"stores NOTHING
  that verifies a password"* (`src/fmt_cpt.c`), grading a candidate by
  the entry CRC. `src/unc_crypt.c` and `src/fmt_sit.c` are the only
  files in the engine that take an `mkey` at all.

- **A fork compressed by a third party's StuffIt COMPRESSOR module
  (method nibble 7) is not decodable here, and the bar is deliberate.**
  StuffIt Deluxe 2.x could hand a fork to an external compressor the
  way it could to an Optimizer or an encryptor, and the Options menu's
  `Custom Compression…` is where one would be chosen. The slot is real
  and the application says so itself: its `STR# 267`, *"9 Magic
  Fldrs"*, lists the eight folders it searches — `Preferences, Help,
  Viewers, **Compressors**, Encryptors, Optimizers, Translators,
  Extensions`. **Aladdin filled five of them and left that one empty.**
  Their two disks carry five Optimizers, three encryptors and nine
  translators and not one compressor, so every
  shape the application writes with what was sold has been asked for
  and read (FORMATS.md, *What an Optimizer did to the fork*, *The three
  ways 2.0.1 encrypts*). A module from somebody else cannot be
  manufactured here and nothing in thirty years of corpora has shown
  one. **What would change it:** a file from whoever has one. The
  engine names the module id and refuses the entry, which is what that
  path exists for.

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

## The licence cannot move, and this is the irreducible core

**Measured, not assumed, and settled.** The 2026-09-19 brief was to shed
as much XADMaster-transcribed code as possible, for the gains where they
exist and for the licence if it ever added up. It did not add up, and
that is now a finding rather than an open question: **five items have no
permissive statement anywhere on this machine or off it**, so LGPL-2.1
stays whatever else is shed.

| what | why nothing replaces it |
|---|---|
| `unc_lzdyn.c` — `-lh2-` and `-lh3-`, the whole file | lhasa implements neither and LHa for UNIX is under its own licence, so there is nothing to rewrite it FROM. Deleting the two methods instead would give back 3,504 B on a Mac Plus (FORMATS.md) and refuse a file LHa still writes today — **settled 2026-08-25, confirmed 2026-09-23: kept** (DECISIONS.md, *the 3,504 bytes that stay*). Both halves run: 15 `-lh2-` and 6 `-lh3-` entries reach the two decoders on every `ci.sh` run, counted 2026-09-27 |
| `fmt_sit.c` — three rules of StuffIt method 8: the table restart, the end of the stream, the 14-bit ceiling | **no specimen reaches any of the three** — the largest method-8 fork in the corpus stops at 7,347 entries and 13 bits — and nothing else implements the method: deark names it "MW" and leaves the decoder NULL (checked 2026-09-27). The rest of the file's encryption item left the same day, measured against Aladdin's own archives (DECISIONS.md, *the layout Aladdin's own output settled*) |
| `unc_crypt.c` — StuffItDES's key schedule | StuffItDES reads all 64 key bits where PC-1 drops eight, so it is no permuted-key standard schedule. **It is graded** against three archives StuffIt Deluxe 3.5.1 wrote, every run. Everything else in that file went to the standards, four times (DECISIONS.md 2026-09-19, 2026-09-23 ×2, 2026-09-26) — and **PackIt's keytr1 left this row on 2026-10-05**, which it should never have been in: it is FIPS 46-3's PC-1, applied by code this corpus carries (BLOCKERS.md, *Withdrawn claims*) |
| `unc_lzah.c` — the `-lh1-`/method-5 window preload | the five steps are published, for LArc's `-lz5-`, and this file writes them byte for byte; applying them to `-lh1-` is XADMaster's, and lhasa fills the buffer with spaces instead. **Measured 2026-09-28: this corpus cannot tell the two readings apart.** One fixture of 933 touches the preload — `derived-BitMap11.sit`, 29 method-5 entries — and only its final step, the trailing spaces. All-spaces passes 933/933, zeros and 0xAA fail, and the pattern with only its tail bent fails. So the window is certainly not zero-filled and the ramps are unexercised. **What would settle it:** a stream whose first match reaches back more than ~110 bytes from the window end (DECISIONS.md 2026-09-28, *the preload nothing reaches*) |
| `src/sit14.c` — StuffIt 5's method 14, the whole file | libxad's `SIT_14` is the only implementation there is: **deark names method 14 "installer" and leaves its decompressor NULL**, and `lsar` reports *"Installer"* off the same lore (both checked 2026-10-03). Deleting the method instead would refuse 80 of the 258 entries in StuffIt Deluxe 7.0.3's own installer and 71 of 184 in 5.5's, which is what this engine did until that day. **Our use is graded**: both payloads byte-for-byte against `unar`, and `synth-sit14.sit` on every run (FORMATS.md, *StuffIt 5's method 14*) |
| `fmt_arc.c` — Crunch 5/6/7 and Crush | no implementation of 7 or Crush exists anywhere, so the row could not close even if 5 and 6 were rewritten — and **nothing can grade a rewrite**: no corpus or reference archive uses any of them. **Not taken, decided 2026-09-22** |
| four tolerances no specification supports — the MacBinary CRC-16/0xA001 fallback and its nonzero-date test, the byte-swapped AppleSingle header, the StuffIt split header | no document states any of them, and **deark was read for all four on 2026-09-27** after it disproved two other cells the same day: its MacBinary uses CRC-16/XMODEM alone and has no date test, and `de_identify_applesd` takes only the big-endian magics. A checked negative, not an unexamined one. **And the two MacBinary ones were UNEXERCISED as well, measured 2026-09-28**: the 0xA001 fallback fires zero times across 933 fixtures and 9,330 robustness variants, and removing either it or the date test changes nothing any suite grades — the `unc_lzah.c` shape, uncited and ungraded at once. The fallback is **pinned** in `tests/unit_formats.c` now, on a header built for it, so a change cannot pass silently; that makes it noticed, not right |

**Do not re-price these.** Each was settled with a measurement and the
cost of re-asking is recorded: the `unc_lzdyn.c` row re-opened its own
settled decision on the byte axis in 2026-09-23 and named nothing that
had changed. **WinZip AES is the same shape and was in Part 2 until
2026-09-28** — 2,150 B of `CODE`, settled on 2026-08-23 in the commit
that added it, graded at four configurations every run. A price is a
number, and numbers live in FORMATS.md (*Resident memory*); a gaps file
listing one invites the decision to be re-opened, which is what happened
to it once already. What is still somebody else's and still has a ROUTE is
Part 2; the full per-file inventory is NOTICE's, checked by
`tools/check_provenance.py` on every run.

---

# Part 2 — Open items

---

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

**Everything StuffIt Deluxe 2.0.1 writes with what was in its box is
extracted** as of 2026-10-02, each graded against an archive it wrote
itself: all five Optimizers, all five ciphers, every compression word,
a 1.5.1-compatible archive, a folder, and a **self-extracting archive**
(FORMATS.md, *What an Optimizer did to the fork*, *The three ways 2.0.1
encrypts*; TESTING.md, the sitopt suite's 28 archives).

**Three of the five Optimizers have stopped being ones.** `Text 1`
left on 2026-10-06 (two Giga-ROM archives, methods 8 and 3, the 255
marker — FORMATS.md, *Two optimized archives nobody here made*), and
`Sound 1` and `MacPaint 1` left on 2026-10-07, each in a fixture off a
1993 CD-ROM collection and each graded by something that is not this
engine's output (FORMATS.md, *Two more, and these the engine UNDOES*).
What is left:

| what is left | what would close it |
|---|---|
| **`Photoshop 1` and `JPEG Lossy` are graded only on archives this project made** | **a file from somebody who has one. No source in reach is left**: every archive Discmaster lists as classic StuffIt — 196,139 — has been asked by one key or the other, and none carries either bit (ids 2 and 3). Both modules accept type `8BIM` only; the 21 archives with an `8BIM` member, the 10,452 the index recorded no members for, and on 2026-10-10 the 112 of those whose walks had stopped early — re-walked to the declared end, every unread byte searched for a header whose own CRC checks — carry neither (TESTING.md, *Searching somebody else's index by content*). 24 of the 112 declare **38 MB** more than the index holds, and those bytes are not on this machine's side of the network |
| **all five ciphers are graded only on archives this project made** — `DES`, `NewDE`, `NewDEx`, `DESex`, `PassLock` | **an encrypted archive and its password, from somebody who has both. No source in reach is left**: the same 196,139 archives, the 112 re-walked on 2026-10-10 included, hold no `DES`, `DESex` or `PassLock` fork, and the only `NewDE` bits are **8 forks in 3 distinct wild archives** with no password found beside any of them — the one read-me that speaks to it says the author mailed one on payment, a negative looked for rather than proved (DECISIONS.md 2026-10-07, *the key was what the archive CONTAINED*) — so a wild encrypted archive grades a REFUSAL, which `sitcrypt-wild-F7Menus.sit.bin` does (FORMATS.md, *The one wild archive here that is encrypted*). Every other wild encrypted fork is 3.x's built-in scheme |

## Hand-written 68000 assembly: candidates, held for one VM pass

**Not started, by decision (2026-10-09).** The engine is portable C99
and has no assembly. The maintainer's call is to collect the loops where
hand assembly beats what GCC emits, and then build, test and time them
together in one pass, rather than one at a time. Every figure below is
an ESTIMATE from the MC68000 timing table and none has been timed on a
machine (DECISIONS.md 2026-10-09, *what GCC will not do with an
index*).

| candidate | C today | assembly sketch | what would close it |
|---|---|---|---|
| **RC4's keystream loop** (`unc_crypt_apply`, `UNC_CRYPT_RC4`; Private File and StuffIt 5's encrypted forks) | 19 instructions, ~178 cycles a byte | 10 instructions, ~104 cycles: index registers cleared once, so `add.b` wraps at 256 and `(d8,An,Dn.w)` addresses the table with no `andi.l #255`; `eor.b Dn,(An)+`; `dbf` | the shared prerequisites below, then the 68000 path beside the C one under `#ifdef __mc68000__`, graded and timed |
| **CRC-32** (`unc_crc32`; zip, gzip, StuffIt 5, Compact Pro, Private File — a third of Private File's instructions, FORMATS.md *What it costs*) | 8 instructions, ~111 cycles a byte | 7 instructions, ~77: the same cleared-index trick — `moveq #0` then `move.b (An)+` loads the index, `add.w` twice scales it, `(d8,An,Dn.w)` reads the table; no `andi.l #255` | as RC4's row |
| **CRC-16/XMODEM** (`unc_crc16_xmodem`; BinHex, MacBinary, PackIt) | 9 instructions, ~115 cycles a byte | 8 instructions, ~67: `rol.w #8` puts the high byte where the index wants it and the low byte where `crc << 8` wants it, so one 22-cycle rotate replaces two 22-cycle shifts; `clr.b`, then the cleared-index table read | as RC4's row |
| **CRC-16/ARC** (`unc_crc16_arc`, `UNC_HOT`; StuffIt 1.5–4 forks) | 9 instructions, ~92 cycles a byte | 7 instructions, ~63: the cleared-index table read, one `lsr.w #8` | as RC4's row |
| **Arsenic's sampled-index scan** (`ars_index_next`, the inner `do { i++; } while (block[i] != c)`; every StuffIt 5 entry on a 1 MB machine whose block outgrows the transform table — 842 s for the ISBN fixture, FORMATS.md *StuffIt 5 / Arsenic at 1x*) | 3 instructions, ~32 cycles a byte: `addq.l`, `cmp.b (d8,An,Dn.l)`, `bne` | ~16 cycles a byte: `cmp.b (An)+,Dn` with the sentinel ending the run, unrolled four times on `beq.s` not taken; `i` recovered from the pointer once per scan | as RC4's row, plus the `UNC_ARS_FORCE_SAMPLED` build in the `qemu-m68k` lane; its share of a run today is not measured (it was 77 % before the sentinel) |
| **LZW's string walk** (`lzw_emit`, `UNC_HOT`; compress, StuffIt method 2, DiskDoubler method 1, ARC) | 7 instructions, ~76 cycles a byte: `andi.l #65535` after every parent read and the `chr` base re-copied into an address register each byte | 4 instructions, ~50: the symbol register's upper word cleared once, so `move.w` leaves it clean; both bases held in address registers; `dbf` on `k` replaces `cmp.l`/`bne` | as RC4's row |
| **Compact Pro's match copy** (`cpt_rle_match`, `UNC_HOT`; DiskDoubler method 8 runs the same loop) | 8 instructions, ~64 cycles a byte | 6 instructions, ~46: `0x81` held in a register (`cmp.b Dn` 4 cycles against `cmp.b #imm` 8); the window cursor post-incremented and corrected once on the escape exit; `dbf` on `k`, which is at most 8,192 | as RC4's row |
| **The fork writer's run copy** (`unc_fork_write`; every output byte of StuffIt methods 5, 13 and 14, LZH's `-lh1-`/`-lh2-`/`-lh3-` and DART) | 12 instructions, ~154 cycles a byte: `o->buf` and `o->len` reloaded from the struct and `len` stored back on every byte, because the byte store may alias them, then `len == cap` tested | 2 instructions, ~22: `n` clipped to `cap - len` once per piece, then `move.b (An)+,(Am)+` and `dbf` (~8 a byte with `move.l` when source and destination share parity). **A C loop over the clipped piece would get most of this too**; the comment there records only its size, 100 B, not its time | as RC4's row |
| **Arsenic's renormalisation** (`ars_next_symbol`'s `while (range <= HALF)`, once per compressed bit; both Arsenic paths) | 22 instructions, ~280 cycles a bit: the inlined bit reader and the decoder's `range` and `code` all load from and store to their structs each bit | ~6 instructions, ~60: `range`, `code` and the bit buffer held in registers; `lsr.b #1` drops the next bit into X and `addx.l` shifts it into `code`. **Inference, not measured:** ~1.6 M compressed bits in the ISBN fixture puts the saving near 8 % of its 542 s | as RC4's row |
| **`-lh1-`'s tree-update search** (`lzah_update`'s `while (l + 1 <= LZAH_T && k > freq[l + 1]) l++`; DART, StuffIt method 5, LZH `-lh1-`) | 8 instructions, ~66 cycles a step | 2 instructions, ~18: `cmp.w (An)+,Dn` / `bhi.s`, stopped by the `0xFFFF` the file already writes at `freq[LZAH_T]` — which also makes the C loop's bound test redundant | as RC4's row |

**Suggestions, not yet estimated to a cycle** — candidates in the same vein whose sketch is not yet sharp enough for a figure:

- **The header's "inline" helpers are out of line in the overlays.** Compiled with `tools/overlay/mkoverlay.sh`'s flags, `-Os` and no `UNC_HOT`, the listing shows `unc_bitin_bit` emitted as a local function and CALLED in nine files (`fmt_arc`, `fmt_dd`, `fmt_exo`, `fmt_lzh`, `fmt_sit`, `fmt_spacesaver`, `unc_huffman`, `unc_lzah`, `unc_lzdyn`), `unc_bufin_next` likewise in six, `unc_bitin_fill` in two and `unc_fork_put` in `fmt_sit`. In `unc_lzah.c` that is a `jsr` per tree level of every `-lh1-` symbol, ~100 cycles of call before the bit is read. DECISIONS.md 2026-09-19 (*the tree that was Yoshizaki's*) says that coder kept "the engine's inline bit reader"; the listing says otherwise. **The listing is read, the cost is not measured.** Forcing them inline (`always_inline`) needs no assembly and costs overlay bytes; a hand-written walk is the assembly version.
- **Canonical Huffman decode as one routine with the bit state in registers** (`unc_canon_decode`; Compact Pro, DiskDoubler, Now Compress, StuffIt 13, LZH). The table-hit path GCC emits is ~45 instructions, ~630 cycles a symbol counted from the `-Os` listing, of which ~180 are the call itself: `movem.l` of six registers each way, three argument loads, `bitbuf`/`nbits` loaded from the struct and stored back. A routine that touches only `d0-d2/a0-a1` drops the `movem`; a whole decode loop in assembly drops the rest. The tree decoder (`unc_huff_decode`) has the same shape.
- **The LSB-first table hit reverses its peek every symbol** (`unc_canon_decode`'s `bi->le` path, `unc_rev_fast`; StuffIt method 13, SpaceSaver method 3, ARC): 12 instructions, ~170 cycles a symbol — two `unc_revbyte` lookups, an `andi.l #255` and three long shifts, `lsl.l #8` and `lsr.l #8` at 24 cycles each. Writing the LSB-first table at bit-reversed indices when it is built, as zlib's own tables are, removes all of it. **Needs no assembly**; the per-symbol price is the 68000's shift cost.
- **BinHex as a whole-line decoder.** The tick probe puts `macburger-helper.hqx` at 2,386 engine ticks for ~253 KB out (FORMATS.md *Decode cost*), **~1,200 cycles an output byte**. `bh_next` is a function per output byte, with a five-register `movem` each way, and `bh_fork` then makes a second pass for the CRC. A 68000 loop that turns a converted 64-character line into 48 bytes, through RLE90, with the CRC-16 step folded in and every cursor in a register, would be ~100 a byte by the timing table. It changes what a stream truncated mid-group does — the reason the C batch was not written (FORMATS.md *What is still hot*) — so the robustness variants grade it.
- **LZW's code reader shifts by a register** (`lzw_code`, inlined into `unc_lzw_read`): one `lsl.l Dn` per byte taken in, one to build the mask and one `lsr.l Dn` to consume — at 8 + 2n cycles each, ~130 cycles of shifting a code at compress's usual 12–16 bits. compress writes codes in groups of eight that fill exactly `n` bytes, so each code's position in a group is fixed for a given width: an unpacker per width, with constant shifts, takes the eight at once. Small per output byte, since one code yields several.
- **Arsenic's two divisions** (`ars_next_symbol`: `range / total`, `code / renorm`) go through libgcc's `__udivsi3`, which on a 68000 is two `divu` behind a call when the divisor fits 16 bits and, when `renorm` does not, a one-bit-at-a-time normalising loop, a `divu` and two `mulu` to correct the guess. `m68kprof` counts each `divu` as one instruction against ~140 cycles, so its 0.72 % undercounts them. **Inference, not measured:** dropping the signed wrapper alone was 1.4 % on the ISBN fixture (FORMATS.md *StuffIt 5 / Arsenic at 1x*), and the wrapper is a fraction of the routine, so the divisions are likely several times that. Inline: `total` is always < 2^16, so the first is two `divu` with no call; for the second, the shift that brings `renorm` under 2^16 can be computed once per symbol instead of looped.
- **Byte-copy loops on `dbf`.** Where GCC tests a pointer or a 32-bit count (`cmp.l` 6 + `bcs` 10), a 16-bit `dbf` is 10: ~6 cycles a byte on every plain copy loop whose count fits 16 bits. Small alone; worth taking in the same pass as the rows above.
- **Arsenic's MTF shift** (`ars_mtf_decode`, up to 15 moves within a list plus one per earlier list): `move.b -(An),-(Am)` and `dbf`, against indexed moves today. It was 34.5 % of a2basic before the two-level rewrite and is not re-profiled since.
- **The repeating-key XOR ciphers take a `%` per byte** (`unc_crypt_apply`: ARC's password, `UNC_CRYPT_XOR`, and PackIt's PMa5, `% 7u`), which is a libgcc `__umodsi3` call, ~400 cycles, for each byte. A key index that wraps by compare is ~30. **Needs no assembly**; it is here because it is the same 68000 price that C hides.
- **ZipCrypto's per-byte key update** (`unc_crypt_zip_update`) makes two calls to `unc_crc32` for one byte each, with the function's whole entry cost, and one `__mulsi3` for `k1 * 134775813`. Inline, the two CRC steps are ~70 cycles each, and the product is three `mulu.w` against the constant's halves (`0x0808`, `0x8405`, both few-bit, so each `mulu` is near its 38-cycle floor). Roughly ~800 cycles a byte → ~400, counted loosely.
- **DES's variable rotates** (`des_crypt`; StuffIt's classic fork cipher, PackIt PMa6, StuffIt 2.x `DES`/`NewDE`): `rotl32` by a computed count is `rol.l Dn`, 8 + 2n cycles, in every S-box step; a table-driven 68000 DES avoids them. Low value: StuffIt 2.x's `DES` and `NewDE` are graded only on this project's own archives (*StuffIt 2.0*, above), and an encrypted entry is rare.

- **zlib's `inflate_fast`** — 52.65 % of a gzip extraction (DECISIONS.md, *Why zlib stays*) and the vendored zlib is unmodified. A 68000 replacement for that one function would keep zlib for everything else. Hand-written 68000 inflaters exist in the Amiga world (Keir Fraser's public-domain `inflate.S` is one) — **a hypothesis: none fetched or read here**, and licence, provenance and correctness would all need checking before one is used as a source.

**Prerequisites for the pass**, once for every row:

| what | why |
|---|---|
| **a `qemu-m68k` lane in `ci.sh`**: the m68k-linux CLI (TESTING.md, *The 68000 profile*, has the build line) running `run_crypt.py`, `run_privatefile.py`, the differential suite (every CRC row) and a `UNC_ARS_FORCE_SAMPLED` build (the scan) | `ci.sh` runs x86, which compiles the C path, so without this lane an assembly path is graded by nothing |
| **a timing build that can open an encrypted archive**: the autotest app with a compile-time password beside `UNC_AT_TIMING` | the tick probe (tools/vmac/README.md) is what prices a change here, and today it cannot reach any cipher |

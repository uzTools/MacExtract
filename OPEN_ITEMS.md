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
byte-exact against the oracle across 949 fixtures in `./ci.sh`.

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
search (BLOCKERS.md).

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
| The Macintosh 512K — 64 KB of ROM | **the interface runs; extraction needs HFS** | measured 2026-09-01, not assumed: `MaxApplZone` is `[Not in ROM]` there and Retro68 emits it as a trap, so the application dies on its second Toolbox call; behind that, `PBGetCatInfo` is HFS, which that ROM has never heard of. The branch `rom64k` guards the trap and its Standard File interface works; what remains is HFS, which a Hard Disk 20 supplies — and **nobody has run it on one**, so this stays out until hardware says otherwise (FORMATS.md, *A true Macintosh 512K*; MANUAL_TESTS.md §6). A Macintosh **128K** is out for a measured second reason: its largest single block is 63,744 B against 142,152 B of `CODE` |
| StuffIt X (`.sitx`) | **detect-only** | out by the brief |
| PKZIP 1.x **Implode** (zip method 6) | **named, refused per entry** | **BOTH halves of the premise are now gone and the decision is the maintainer's.** It was out because it is PKZIP 1.x's, predates deflate, and the two corpus archives carrying it are PC software — 7 entries across `4acalc.zip` and `4alnch11.zip`, graded on names and entry counts alone. An MIT implementation and a stored-CRC oracle for all 7 have been on this disk since 2026-09-22 (DECISIONS.md 2026-09-22, *the premise that stopped being true*), and on 2026-10-04 "not a Macintosh method" fell too: `Psycho!v1.0ß1.zip` is a White Knight script set from February 1994 written BY ZipIt, three MacBinary entries with resource forks, every one Implode, saying so in its own archive comment (FORMATS.md, *ZipIt's own archives*). It is a specimen, re-fetchable, and refused cleanly per entry — the CLI's own message for it asks the user to send exactly that file. Adding the method would also want ZipIt's `0x2605` FileName (Part 2), because those three entries are the ones whose names this engine gets wrong. **What it would cost is still unmeasured** — a removal delta can be built and an addition cannot — but the comparable coders put it at **~1.5–2 KB of `CODE`, estimated, not measured**, against 12,460 B of headroom at the tightest tier |
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
| `unc_crypt.c` — StuffItDES's key schedule, and PackIt's keytr1 | StuffItDES reads all 64 key bits where PC-1 drops eight, so it is no permuted-key standard schedule; keytr1 has no other statement at all — PackIt's manual names "simple encryption" and describes none. **Both are graded**: StuffItDES against three archives StuffIt Deluxe 3.5.1 wrote, keytr1 against `unar -p`, every run. Everything else in that file went to the standards, four times (DECISIONS.md 2026-09-19, 2026-09-23 ×2, 2026-09-26) |
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

## Zip's Macintosh extra fields: what is left after reading them

**The fields are read since 2026-10-01** — type, creator, Finder flags,
dates, and both forks out of a ZipIt `0x2605` entry (FORMATS.md, *Zip's
Macintosh extra fields*, has the figures and what grades each one), and
**graded on nine archives ZipIt itself wrote since 2026-10-04**
(FORMATS.md, *ZipIt's own archives*), which closed the row that said they
were not. **A self-extracting one is recognised since 2026-10-05**, which
closed the row for that. One thing is left.

| what is left | what would close it |
|---|---|
| **ZipIt's `0x2605` FileName is not read, and it is the name the Macintosh file HAD** | **a leaf-name substitution in the zip walk.** APPNOTE.TXT 4.6.4 calls it the "full Macintosh filename"; over 20 real `0x2605` entries it agrees with the zip's own name 17 times, and with the MacBinary header's in 16 of the 17 where that header is reachable — and it is the right name in all 20. Where it disagrees, the names had been converted to MS-DOS form on their way into the zip, so `READ ME` extracts as `README` — a space lost from a Macintosh name by a Macintosh unarchiver. **It changes nothing this build can extract, re-measured 2026-10-05**: all 3 divergent fields of the 23 on this disk are Implode, refused per entry, so the fix is coupled to that decision (Part 1) and worth taking with it rather than alone; `tools/run_zipit.py` fails the day that stops being true. And the field is a leaf, not a path, so in the one archive it touches it would still leave the enclosing `PSYCHO!/` upper-cased — 3 of 4 components (FORMATS.md, *ZipIt's own archives*, has all of it). The cost is the substitution buffer — the name is built from the zip's path and the field's leaf, and `namebuf` is already 256 B of this function's stack, where CLAUDE.md's rule is measured and not assumed |

## The overlay loader: what no emulator here can answer

Two items, and both want the same thing: **a Macintosh with a 68020 or
better, running the shipped binary** (MANUAL_TESTS.md §2 and §6). The
Linux lane closed what it could on 2026-09-26 — it builds the fifteen
images, runs the real loaders through a mock Memory and Resource
Manager, extracts 17 fixtures byte-exact under `qemu-m68k`, and catches
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

## What is still somebody else's and could stop being

**The per-file inventory is NOTICE's**, in *What is still somebody
else's, in full*, and `tools/check_provenance.py` checks it on every
`ci.sh` run — a file that gains a citation fails, and so does one that
sheds its last. This section held a second copy until 2026-09-27, the
two disagreed, and that is how a live citation in `src/fmt_sit.c` came
to be recorded as shed in three documents at once (BLOCKERS.md).

**What has no route at all is Part 1**, *The licence cannot move*. The
licence does not turn on anything below — that is settled — so each is
worth taking only for its own gain: **no regression for the licence's
sake**.

**Two axes, and this table is only about the first.** Whether a fact can
be RE-CITED is not whether our use of it is GRADED, and a row that is
silent on the second gets read as doubting it. Every row below is graded
by something named in its cell. Where the two genuinely coincide — no
citation and no test either — the item is in Part 1 and says so, which
is `unc_lzah.c`'s position and, as far as anything here shows, the
MacBinary CRC-16/0xA001 fallback's (DECISIONS.md 2026-09-28, *the
preload nothing reaches*).

| what is left | what would move it |
|---|---|
| `fmt_sit5.c` — bit 5 of the encrypted archive's flag byte | **three boots nobody has done.** No archive in reach sets bit 5 (47 scanned), and the only comment UI is StuffIt Deluxe 5.0.1, which Mac OS 9.2 refuses. **The media stopped being the blocker on 2026-10-06**: the retail Mac OS 8.6 install CD is on this disk, bootable HFS, 665,600,000 B (`tools/vmac/README.md`, *Mac OS 8.6 media*; BLOCKERS.md for the withdrawal). Unmeasured, in order: does `qemu-system-ppc -M mac99` boot 8.6, does 5.0.1 run on it, does its comment UI set bit 5 — the last still a **hypothesis** (DECISIONS.md 2026-09-27, *the file system was never the problem*) |
| `fmt_binhex.c`, `fmt_uu.c`, `unc_internal.h` — macutils' four rules about mailed text | **a second reader per rule, and each is blocked differently** — which is why it will not close in one go. Checked 2026-09-27: mpack is LF-only so it cannot state the CR rule; deark errors on a stray character and mpack keeps the decoded prefix, so neither restates the whole-line garbage skip; mpack's second-document handling is a separator inside one part, not a rescan; and nothing else implements UUTool's MU layout. Two of the six left for mpack that day (TESTING.md; NOTICE). **Our use of all four is graded** — `tools/run_uu.py`'s gapped sets and the multi-part fixtures — so what is stuck is the citation, not the behaviour |
| `fmt_packit.c` — the resync strategy and both ciphers | **a second implementation of `PMa5`/`PMa6`.** deark's `packit.c` handles `PMag` and `PMa4` only and errors where this resyncs; appendix B lists "PMa5" twice and cannot name the fourth word. **Our use is graded**: `unar -p` reads both ciphers back every run (FORMATS.md, *Encryption*) |

**The template is the `-lh1-` coder** (DECISIONS.md 2026-09-19, *the
tree that was Yoshizaki's*): faster, smaller and lighter, so it would
have been taken on its merits with no licence question in sight.

## The decoder paths nothing has fuzzed

**Measured by `tools/fuzz_cover.py`** — a coverage build under
`fuzz.py`, which is the only instrument here that distinguishes a
decoder that ran from one that never did. Read the per-family counts
with its noise floor in mind: two seeds over one build have differed by
thirteen functions in a family (TESTING.md, *Fuzzing*).

Most of what this section listed on 2026-09-27 was closed the same day
and the next — `-lh2-`, `-lh3-`, DiskDoubler 3/4/5/7 and Now Compress's
coders all reach their decoders now, by seeds, by a fixture, and by a
generator that repairs the checksum it breaks — and **Now Compress is
the first family with nothing left at all**, since 2026-10-05
(TESTING.md, *Fuzzing*). **StuffIt 5's method 14 is the second**, since
the same day, by a generator that mutates a named seed inside its own
compressed streams. What is left:

| what | what it wants |
|---|---|
| `lzd_reconst` (`-lh2-`'s tree rebuild) | nothing, under fuzzing: it needs 32,768 codes, too large for a seed. The GRADED suite covers it since 2026-09-27 |
| `sit14_flush`'s window wrap (method 14) | a fork past 256 KB, where the synthetic seed's largest is 17,799 B — the window is sized to the fork, so nothing smaller can wrap it. Reached only by the two real payloads, which no committed suite can touch (TESTING.md, *Fuzzing*, for the mode's other limits) |
| ARC's Crush | nothing writes it and no implementation exists anywhere (Part 1) |

**AppleLink packages would have joined this list on 2026-10-05** — the
fuzzer measured `unc_sqp_extract` at zero lines after 400 cases, because a
`.pkg` is 6 of 949 fixtures and it draws uniformly — so the suite got a lane
that bends those six directly instead: 300 mutants, a fixed seed, 270 of
them still sniffing as a package and every one decoding without a sanitizer
report (TESTING.md, *AppleLink packages: SqueezePlay*). A draw rate is not a
property of a decoder, and the cheap answer was a targeted sweep rather than
a row here.

**Nothing here is known to be hiding a defect** — that is the point:
before this was measured, it could not be said either way.

## AppleLink `.pkg`: the packages that have not been on a Macintosh

**Every container path the format has is reached by a real package since
2026-10-06** — a resource fork, both stored bits, version 0 and folders
to four levels, over **67 forks of 8 packages**, with `gzip` reading 59
of the streams independently (FORMATS.md, *What the eight real packages
exercise*; DECISIONS.md 2026-10-06). That closed the item this section
held. One thing is left, and it is a run rather than a file:

| what is left | what would close it |
|---|---|
| **the six specimens found on 2026-10-06 have not been on a Macintosh**, and they are the ones with the folders, the stored forks and a 541,179 B member (FORMATS.md, *Run on a Macintosh*) | **`tools/vmac/run.py --mem 1M --expect` over the six** — the command the other eight were run with. It would measure the `'OVLY'` image, the real sniff path, and whether 541 KB fits a 1 MB machine's volume |

## StuffIt 2.0: the modules that are still only this project's own output

**Everything StuffIt Deluxe 2.0.1 writes with what was in its box is
extracted** as of 2026-10-02, each graded against an archive it wrote
itself: all five Optimizers, all five ciphers, every compression word,
a 1.5.1-compatible archive, a folder, and a **self-extracting archive**
(FORMATS.md, *What an Optimizer did to the fork*, *The three ways 2.0.1
encrypts*; TESTING.md, the sitopt suite's 28 archives).

**`Text 1` stopped being one of them on 2026-10-06**: two Giga-ROM CD
archives carry an entry it optimized, at methods 8 and 3, with the 255
marker and the deleted resource fork, and both are fixtures
(FORMATS.md, *Two optimized archives nobody here made*). What is left
is narrower than the row this replaces, and the search that narrowed it
is worth not repeating:

| what is left | what would close it |
|---|---|
| **the four REVERSIBLE Optimizers and all five ciphers are graded only on archives this project made** — `Sound 1`, `Photoshop 1`, `JPEG Lossy`, `MacPaint 1`, `DES`, `NewDE`, `NewDEx`, `DESex`, `PassLock` | **a wild archive carrying one.** The sweep has been run: **21,767 entry headers in 16,727 archives**, two keys, **5 Optimizer bits in 3 archives, every one `Text 1`'s**, 38 encrypted, 8 `NewDE` (TESTING.md, *Searching somebody else's index by content*). So they are rare, not absent; the widening is more archives or deeper walks by the same key. A wild ENCRYPTED archive grades a refusal rather than a decryption unless its password is published beside it |

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
better be true.** Five questions have each emptied a row at least once: is
there an implementation that could be **FED** (DECISIONS.md, methods 3, 4 and
5); is *"X does not survive"* a claim about somebody's **search**
(BLOCKERS.md, SuperDisk!'s compressor); does the search name the **right
tool** (BLOCKERS.md 2026-08-25); **have you looked at all** (BLOCKERS.md, the
ARC 7 row, filed and disproved the same day); and — added 2026-09-26, when
the whole *waiting on a file* section went — **was the search by NAME?** A
format that renames nothing is invisible to every index built on names and
plain to one built on magic.

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
| PKZIP 1.x **Implode** (zip method 6) | **named, refused per entry** | not a Macintosh method: it is PKZIP 1.x's, it predates deflate, and the two corpus archives carrying it are PC software. 7 entries across `4acalc.zip` and `4alnch11.zip`, graded on names and entry counts alone. **Half the premise is gone and the decision is the maintainer's**: an MIT implementation and a stored-CRC oracle for all 7 entries have been on this disk since 2026-09-22, so only "not a Macintosh method" still carries it (DECISIONS.md 2026-09-22, *the premise that stopped being true*). **What it would cost is still unmeasured** — a removal delta can be built and an addition cannot — but the comparable coders put it at **~1.5–2 KB of `CODE`, estimated, not measured**, against 12,460 B of headroom at the tightest tier |
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
| `unc_crypt.c` — StuffItDES's key schedule, and PackIt's keytr1 | StuffItDES reads all 64 key bits where PC-1 drops eight, so it is no permuted-key standard schedule; keytr1 has no other statement at all — PackIt's manual names "simple encryption" and describes none. Everything else in that file went to the standards, four times (DECISIONS.md 2026-09-19, 2026-09-23 ×2, 2026-09-26) |
| `unc_lzah.c` — the `-lh1-`/method-5 window preload | the five steps are published, for LArc's `-lz5-`; applying them to `-lh1-` is XADMaster's, and lhasa fills the buffer with spaces instead. Load-bearing: a Trimmed member takes zeros and not the pattern, which is what tells the dialects apart |
| `fmt_arc.c` — Crunch 5/6/7 and Crush | no implementation of 7 or Crush exists anywhere, so the row could not close even if 5 and 6 were rewritten — and **nothing can grade a rewrite**: no corpus or reference archive uses any of them. **Not taken, decided 2026-09-22** |
| four tolerances no specification supports — the MacBinary CRC-16/0xA001 fallback and its nonzero-date test, the byte-swapped AppleSingle header, the StuffIt split header | no document states any of them, and **deark was read for all four on 2026-09-27** after it disproved two other cells the same day: its MacBinary uses CRC-16/XMODEM alone and has no date test, and `de_identify_applesd` takes only the big-endian magics. A checked negative, not an unexamined one |

**Do not re-price these.** Each was settled with a measurement and the
cost of re-asking is recorded: the `unc_lzdyn.c` row re-opened its own
settled decision on the byte axis in 2026-09-23 and named nothing that
had changed. What is still somebody else's and still has a ROUTE is
Part 2; the full per-file inventory is NOTICE's, checked by
`tools/check_provenance.py` on every run.

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
copy of the shipped binary run on one (MANUAL_TESTS.md §2 and §6). Short of
that, read every tier sweep with the `-D UNC_AT_BUDGET` probe fields (`wa`,
`kf`, `rf`, `fc`, `fn`) rather than on the tally alone.

## What is still somebody else's and could stop being

**The per-file inventory is NOTICE's**, in *What is still somebody
else's, in full*, and `tools/check_provenance.py` checks it on every
`ci.sh` run: a file that gains a citation fails, and so does one that
sheds its last — which is how a row leaves here without anybody
noticing by hand. This section duplicated that list until 2026-09-27;
the two disagreed, and the disagreement is what let a live citation in
`src/fmt_sit.c` be recorded as shed in three documents at once
(BLOCKERS.md, *Withdrawn claims*).

**What has no route at all is Part 1**, *The licence cannot move*.
What is left here is the four items that could still move, and the one
thing each is waiting for. **`src/fmt_lzh.c` left on 2026-09-27**: its
last rule turned out not to be XADMaster's alone — lhasa produces the
same filename, reaching it through C-string handling rather than
stating it (DECISIONS.md, *the rule both references already
followed*). The licence does not turn on any of them —
that question is settled — so each is worth taking only for its own
gain, which is the rule the brief was given under: **no regression for
the licence's sake**.

| what is left | what would move it |
|---|---|
| `fmt_sit5.c` — bit 5 of the encrypted archive's flag byte | **most of this item went on 2026-09-27**, measured against the three archives DropStuff 5.0.1 wrote and has had in the cache since 2026-08-26: bit 7, bit 4's 14-byte shift and the MD5-of-MD5 password grade (`tools/derive_sit5crypt.py`, which needs no engine — the bytes Aladdin wrote and `hashlib`). Bit 5 shifts the hash four bytes further and **no archive in reach sets it**: all 47 StuffIt 5 archives on this machine read 0x10 or 0x90, and the StuffIt Deluxe 5.0.1 CD holds none at all (scanned 2026-09-27). That it marks a COMMENT is XADMaster's naming of the two fields and remains a **hypothesis**. **The FILE-SYSTEM route is disproved**, 2026-09-27, in all four combinations. The archive-comment UI is StuffIt Deluxe 5.0.1's, and that application raises *"an update to this software is required for compatibility with the improved Mac OS file system"* whether booted from HFS+ or from a plain-HFS volume built for the purpose (`tools/vmac/mkapmdisk.py`, a System Folder copied onto it, confirmed the startup disk), and whether run from an HFS+ volume or an HFS one. **The alert names the file system; the trigger is Mac OS 9.2 itself.** So the route is an older Mac OS — 8.x — and this machine has no Mac OS install media of any kind, only the StuffIt CD. That is a fetch or a person, not a search. DropStuff, which does run, has no comment option and its Preferences cannot be reached by the harness (`tools/vmac/README.md`, *what the pointer cannot select*) |
| `unc_internal.h` — DiskDoubler method 8's Huffman block, 0xfff0 | **half taken 2026-09-27, and the half left needs a SPECIMEN, not a citation.** That method 8 is Compact Pro's stages is measured: all 7 method-8 forks in reach decode byte for byte against the oracle's sha256 with a reader written from Compact Pro's published pages alone (`tools/derive_dd8.py`). The block size is unfalsifiable here — every size at or above 0x1000 reads every fork, the largest that FAILS anywhere is 0x400, so no stream in the corpus reaches even that much cost. **What would pin it is one method-8 fork whose coder output crosses 0xfff0 cost units** — 2 per literal, 3 per match; the biggest in reach is 44,549 B and compresses to 1,230 |
| `fmt_binhex.c`, `fmt_uu.c`, `unc_internal.h` — macutils' four remaining rules about mailed text | **two of six taken 2026-09-27, and the other four are each blocked for a DIFFERENT reason, which is why this will not close in one go.** Gone to mpack (permissive, CMU): the dispatch — any amount of preamble skipped looking for a line beginning `begin ` — and the uu terminator, `end` plus whitespace; both are `uudecode.c`'s state machine, `st_start` and `st_last`. `fmt_mime.c` carried only the terminator and has left the inventory. What is left, and what fails for each: the **CR/LF/CRLF rule and the unterminated last line** — mpack is LF-only throughout (`part_gets` breaks on `\n` alone) and deark ignores whitespace instead of reading lines, so neither states it; the **whole-line garbage skip** — deark's `binhex.c` ERRORS on a stray character and mpack's `macbhex.c` keeps the prefix it already decoded, so both differ in output rather than restating it; the **scan for a second document in one input** — mpack uses a `--- ` separator inside one part, not a rescan to EOF; and **UUTool's MU layout**, which nothing else implements. Each would need its own second reader |
| `fmt_packit.c` — the resync strategy and both ciphers | a second implementation of `PMa5`/`PMa6`. deark's `packit.c` handles `PMag` and `PMa4` only and errors out where this resyncs. Appendix B lists "PMa5" twice and cannot name the fourth word, so the document is not it |

**The template is the `-lh1-` coder** (DECISIONS.md 2026-09-19, *the
tree that was Yoshizaki's*): faster, smaller and lighter, so it would
have been taken on its merits with no licence question in sight. Of
the rows once filed as having no other description, only Now Compress
never had a published one, and it fell to reverse-engineering against
the application on 2026-09-21.

## The methods the fuzzer cannot reach

**Measured 2026-09-27, `tools/fuzz_cover.py`**, 3,000 cases at seed 11
over a coverage build: `src/unc_lzdyn.c` is **16 of 16 functions never
entered** — the whole `-lh2-`/`-lh3-` decoder — and DiskDoubler's
methods 3, 4 and 7, ARC's Crush, three of Arsenic's index helpers and
six of Now Compress's thirteen functions are never entered either.

**The cause is structural.** Three of `fuzz.py`'s four generators
mutate a corpus fixture, so the fuzzer's reach is the corpus's
coverage, and every method this project grades by GENERATING a file
rather than owning a specimen is graded for correctness and fuzzed not
at all. Now Compress is the exception that is worth its own line: its
archives are in the corpus, and a 32-bit sum over the block table
rejects every mutant before a coder runs — the gate the one decoder
heap overflow sat behind (TESTING.md, *Fuzzing*; BLOCKERS.md).

**`-lh3-` was seeded on 2026-09-27** and the family is no longer wholly
unfuzzed: `fuzz.py`'s `method_seeds()` builds a six-entry archive with
`run_lzh.py`'s pure-Python encoder, and the `-lh3-` entry point goes
from never entered to 69.7 % of its lines (TESTING.md, *Fuzzing*).

**What is left, and what each wants:**

- **`-lh3-` is done, 2026-09-27.** `lh3_lz_stream()` writes matches —
  LHa adjudicates it — and the seeds are split one archive per case, so
  a mutation has only the first entry to get past. Every `-lh3-`
  function is reached: `unc_lzst0_decode` 100 %, `lzs_decode_p` 88.9 %,
  `lzs_read_tree_p` 64.3 %. It also closed a CORRECTNESS gap: no
  `-lh3-` stream written here had ever contained a match, so the
  decoder's LZSS half was graded by nothing (BLOCKERS.md).
- **`-lh2-` is done, 2026-09-27**, by exactly that route: the bytes are
  committed at `tools/seeds/lh2.lzh` rather than generated per run.
  `src/unc_lzdyn.c` goes from 16 of 16 functions never entered to 1 —
  `lzd_reconst`, which wants 32,768 codes, too large for a seed and
  covered by the graded suite instead.
- **DiskDoubler 3, 4 and 5 are done, 2026-09-27** — and `ddencode.py
  --build` turned out to need no emulator at all, so the files were
  written locally and committed under `tools/seeds/`. DiskDoubler goes
  from 4 functions never entered to 2.
- **DiskDoubler method 7 and ARC's Crush** — nothing here writes either.
  Method 7 is the Sigma Designs card's compression, with specimens on
  the 3.1.2 and 3.7 disks but none in the corpus; Crush has no
  implementation anywhere (Part 1).
- **Now Compress's coders** — **done 2026-09-27.** `fuzz.py`'s fifth
  generator flips bits inside a block's payload and recomputes that
  block's 32-bit trailer with `mutate_now.py`'s `fix_trailer`, which is
  the only way past the gate. The family goes from 6 functions never
  entered to 1, `now_find_delta`, at two seeds. That last one wants a
  file whose block table carries a delta, which neither corpus archive
  has.

**Nothing here is known to be hiding a defect** — that is the point:
before this was measured, it could not be said either way.

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

## AppleLink `.pkg`: two packages, and a probe that names neither

**Two real AppleLink packages arrived on 2026-09-26** — `ALink.PKG` (6,900 B)
and `Read First.PKG` (1,373 B), both beside AppleLink 6.1 on fifteen Apple
Developer CDs, fetched by `tools/fetch_specimens.py` (FORMATS.md, *AppleLink
packages*). They settle what a package is and open two items:

- **A package is binary, and it is a container.** Each record holds two
  lengths, a type, a creator, Finder flags, a Pascal name and two Macintosh
  dates, with non-text data after them; `Read First.PKG` has one record and
  `ALink.PKG` at least five. The *transfer manifest* hypothesis is withdrawn
  (BLOCKERS.md). The rest of the layout is not derived: rule #1 does not let
  two specimens stand in for a reference.
- **There is no content test for one, and the probe that claimed to be it is
  gone.** Settled 2026-09-27 and it needed no boot: the `Decode … to …` token
  test read out of `PKG Expand Translator` is the translator API's COMMAND
  parser, carried verbatim by five siblings on the same disk whose formats are
  Compact Pro, zip, BinHex, uuencode and Unix compress. `unc_applelink_probe`
  is removed; a `.pkg` sniffs as *unknown*, which is what it was already doing
  on both real packages (FORMATS.md, *AppleLink packages*; DECISIONS.md
  2026-09-27, *the recogniser that was a command line*). **Closed by:** a
  reference implementation or a published layout for the binary container —
  Aladdin's translator recognises a package by its extension and reads a
  FOLDER, so it is not one.

No decoder is written, and the reader on the emulator image turns out to be a
driver: it calls `GetResource('Eng ', 2)` in `StuffIt Engine™` and jumps into
it, so whatever expands a package is in that 26,362-byte resource and not in
the translator.

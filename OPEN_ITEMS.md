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
| The Macintosh 512K — 64 KB of ROM | **the interface runs; extraction needs HFS** | measured 2026-09-01, not assumed: `MaxApplZone` is `[Not in ROM]` there (Inside Macintosh II-30) and Retro68 emits it as a trap, so the application dies on its second Toolbox call; behind that, `PBGetCatInfo` is HFS, which that ROM has no idea about. Apple's own software HFS for those machines — the `Hard Disk 20` startup disk — boots on a 128K ROM here and hangs on a 64K one, so even that route is untested (FORMATS.md, *A true Macintosh 512K*). Since 2026-09-01 the branch `rom64k` guards `MaxApplZone` with `Has128KROM()`, so its build starts there and its Standard File interface works; what remains is HFS, which a Hard Disk 20 supplies on exactly the machines where an unarchiver earns its keep. **Nobody has run it on one** — Mini vMac has no HD20, so this stays out of scope until hardware says otherwise (MANUAL_TESTS.md §7). A Macintosh **128K** is out for a second reason and that one is measured: its largest single block is 63,744 B against 142,152 B of `CODE`, so the guarded build bombs `ID = 03` on launch there (FORMATS.md, *A Macintosh 128K*) |
| StuffIt X (`.sitx`) | **detect-only** | out by the brief |
| PKZIP 1.x **Implode** (zip method 6) | **named, refused per entry** | not a Macintosh method: it is PKZIP 1.x's, it predates deflate, and the two corpus archives carrying it are PC software that arrived in the corpus for the per-entry refusal path rather than for their contents. 7 entries across `4acalc.zip` and `4alnch11.zip`, graded on their names and entry counts alone (FORMATS.md, *Hardening*). **The premise is weaker than it was and the decision is the maintainer's** — see below |
| PKWARE "strong encryption" in a zip (flag 0x40) | **named, refused per entry** | its key material is in a record nothing here parses, and XADMaster refuses it too. Every OTHER encryption these formats have is decrypted, including WinZip's AES (FORMATS.md, *Encryption*) |
| Disk images (`.image`, `.img`, `.iso`, `.cdr`, `.toast`, `.dmg`, `.smi`), and Disk Copy 4.2 | **not recognised**, and not extracted | extracting one means a filesystem rather than a codec, and naming one is worth nothing either: a disk image is not an archive, so the name leaves a user exactly where "not recognized" does. The probes are complete, graded and kept in `attic/` (DECISIONS.md 2026-08-26, *read the volume, not the extension*). **DART is the one exception, since 2026-09-09**, and it is an exception to the first clause only: a compressed DART expands to an UNCOMPRESSED DART, which is a codec with no volume anywhere in it, and no file on the disk is ever looked at. FORMATS.md, *DART* |
| PMarc (`-pm0-`, `-pm1-`, `-pm2-`) and `-lhx-` | **not recognised** | a different family behind an LZH-shaped header. PMarc is a Japanese PC format with its own coders, `-lhx-` is UNLHA32's extension; neither reached a Macintosh |
| Self-extracting LZH (an executable with an archive behind it) | **not recognised** | the archive sits behind DOS, Amiga, Atari or X68000 machine code, and finding it means knowing each of those loaders. `unar` has a parser per platform; here the answer is to hand the `.lzh` itself to the extractor |
| RAR, 7z, bzip2, xz, Cabinet, Zoo, ar/`.deb`, cpio, ARJ | **named, never extracted** | none is a Macintosh archive format, none carries a resource fork or Finder metadata, and every one is served by a maintained extractor on any machine that can run one. NAMING them is in scope (DECISIONS.md 2026-08-26, *a name is only worth something inside the frame the user came with*; FORMATS.md, *Archives named but not extracted*) |
| Alysis SuperDisk! method 13 | **not implemented, and no specimen is wanted** | its module compresses and REFUSES to decompress — `_Debugger` at its own 0xd4 — so no Alysis expander in reach can read what it writes, and nor can this engine or any other module in the library. Streams can be made here at will and there is nothing whatever to grade one against. It is reachable from Alysis's own compress path (level 11 of INIT 32's table at +0xf2e), so a file COULD exist; reading one would mean inverting that compressor with no second reader anywhere, for a codec no archive in the corpus uses (FORMATS.md, *Module 13*; DECISIONS.md 2026-08-29, *the specimen that would have settled nothing*) |
| Zip64 addressing past 4 GB | **the counts and the per-ENTRY escape are read; over-4-GB fields are refused** — `UNC_ERR_UNSUPPORTED` per archive, `UNC_ERR_TOOLARGE` per entry — and `unc_zipseg_describe` still answers `UNC_ERR_UNSUPPORTED` for a spanned set | zip's own shape is what keeps it out: the directory fields are 32-bit and the Zip64 escape is read as `uint32` halves, so reading past 4 GB properly is a format change rather than a type change. The type is not the obstacle — `UncIO` carries `unc_off_t`, 64-bit in the CLI, for +0.51 % of text and 0 bytes of heap (DECISIONS.md 2026-08-28, *what a width costs*). Reading the halves is what makes a 70,000-entry archive extract, and a 3.4 GB one (FORMATS.md, *Size limits*); tar, whose positions are a running sum, reaches past 4 GB today |

### Implode: what changed, and what has not

**Not a recommendation, and nothing has been done about it.** Recorded
because the reason for the decision is not what it was, and a scope
decision resting on a stale premise should at least be re-made
knowingly.

When Implode was declined there was no implementation here to write it
from and nothing to grade it against. Both are now on this disk and
were verified on 2026-09-22:

- **an implementation**, MIT — `reference/deark/src/fmtutil-lzh.c`,
  section *"Implode (ZIP method #6)"*, which is deark's own code and
  not one of the `foreign/` files its licence carves out;
- **an oracle that cannot be argued with** — deark decodes all **7**
  Implode entries of the two archives and every one matches the
  **CRC-32 PKZIP itself stored**: `CALC.TXT` to 5,284 B, and six more.
  A check no decoder here can influence.

What has NOT changed: Implode is still not a Macintosh method, and the
two archives are still PC software. Implementing it would cost code on
a 1 MB machine for a format a Macintosh never wrote.

**Deliberately not done, and it is one line either way.** Adding
`"Implode"` to `make_manifests.py`'s `DEARK_METHODS` would record those
7 entries' 10 forks as ground truth without implementing anything, and
`run_diff.py` would start comparing them the day a decoder lands
(TESTING.md, *When our engine declines an entry*). That is part of the
same decision and is left with it.

Everything detect-only is **named** by `unc_sniff`, and both front ends say
the name: the CLI prints *"recognized as RAR, which v1 cannot extract"* and
the Macintosh application's alert reads *"MacExtract cannot open RAR files."*
(photographed on System 6.0.8). Extraction returns cleanly unsupported either
way.

## Overlays and selective loading: built, measured, parked

**Not open, and not untried.** Loading part of the engine from a resource on
demand works and runs on a 1 MB Mac Plus. Two branches keep it —
`selective-loading` (the ciphers fetched when a format wants them) and
`overlay-eager` (the same overlay loaded at launch) — and **neither is
merged**.

Three measurements decided it: the prize is **5,988 B**, about one archive in
922 at the corpus's headroom density, and it opens nothing — since 2026-09-18
nothing in the corpus is out of a 1 MB Mac Plus's reach at all (FORMATS.md,
*The Linux budget check reads the Mac to 40 bytes*); **StuffIt can never be
one of the formats it helps**, because an
encrypted entry is discovered as the entry is read; and the disk dependency
**cannot be removed, only moved** — one branch pays a mid-run access on the
first encrypted archive, the other on the second, on a machine with one floppy
drive. What an end user would trade is a disk swap or a stall for memory that
opens nothing new. DECISIONS.md 2026-08-31, *the overlay that works and is not
worth it*.

**What would reopen it:** something needing tens of kilobytes rather than
six. The mechanism and its traps are written up in `BRANCH_NOTES.md` on either
branch, so reopening it is a merge and not a rediscovery.

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

## Selective extraction: the entries the user ticked, and no others

**Asked for 2026-09-03**: show what is in the archive, extract what is chosen.

**The engine already has both halves.** `UncOptions.list_only` walks the
containers and reports every entry through `begin_entry` while decoding
nothing, and a `begin_entry` that returns >0 skips its entry — the data is
not decoded and `end_entry` is not called (`include/macextract.h`, *Sink*).
So this is a shell and a UI item; no format and no decoder is involved.

What it costs, all of it on the Macintosh side:

- **a second walk of the archive**, at no decode. The LAST layer only: a
  chain's envelopes are unwrapped to disk either way, so `.sit.hqx` is not
  walked twice.
- **the list, on a 1 MB machine.** The end-of-run report holds 64 lines in a
  6 KB pool for this reason, and a 70,000-entry zip fits in nothing. A cap,
  and *"too many entries to choose from"* falling back to extracting
  everything, is the shape that stays honest; the choice itself is a bit per
  entry.
- **the two passes have to agree entry for entry.** An ordinal alone is
  fragile — match the name too, and extract everything rather than the wrong
  thing if they diverge.
- **the list is hand-drawn**, like the report box: the floor is System 3.0.

**What would close it:** the shell answering >0 for what was not ticked,
graded through the mock sink, plus the list driven on screen on System 3.0
and System 6 (`tools/vmac/interactive.py`).

**All of that is done on the branch `selective-extract`, and it is not
merged** — what is left is the decision, because the price is now known:
2,720 B off every 1 MB extraction's budget whether or not anybody unticks
anything, and ~10 ms an entry for the second walk. BRANCHES.md, and
`BRANCH_NOTES.md` on that branch.

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

| file | XADMaster code in it | other reference on this machine | gain plausible? |
|---|---|---|---|
| `unc_huffman.c` | **none since 2026-09-20** | the canonical codes: RFC 1951 section 3.2.2 and puff.c, since 2026-09-19. The serialized tree: `docs/formats/serialized-huffman-tree.md`, this project's own, derived from the three formats' output | **both halves taken.** The canonical codes were a re-derivation (0.00 %, −4 B of code, −20 B of A5). The tree needed no rewrite at all: what it lacked was a description, and 13 forks across StuffIt 3, DiskDoubler 4 and PackIt supplied one (DECISIONS.md 2026-09-20, *the tree that could be measured instead*) |
| `unc_lzw.c` | **none since 2026-09-19** | written from deark's `src/fmtutil-lzw.c` (MIT) and Welch's algorithm | **taken, −9.4 % on `popper-1.7.tar.Z` and −1.7 % on `derived-xmasbeeps.sit` on a Mac Plus for +140 B of code and −12 B of A5** — the walk was tight, the staging array it walked into was not (DECISIONS.md 2026-09-19, *the buffer that became a length*) |
| `unc_lzdyn.c` | `-lh2-`/`-lh3-` from `XADLZHOldHandles.m` | LHa for UNIX only (its own licence); lhasa has neither | none — no corpus archive uses them. **What they cost is measured, 2026-09-20: 3,472 B of `CODE` and 32 B of A5**, i.e. 3,504 B of a 1 MB Mac Plus's budget, from a build with the file and its two dispatch arms removed. Set that against 5,988 B for the overlay that was judged not worth taking (*Overlays*, Part 1) — and against the fact that LHa for UNIX writes `-lh2-` today and `tools/run_lzh.py` grades us against one, so dropping them refuses a file that can still be made. **The decision is the maintainer's**; nothing here will take it |
| `fmt_lzh.c` | **none since 2026-09-22**, bar one rule with no specimen: a NUL inside a level 0/1 name field ends the name, which is `XADLZHParser.m`'s and which **0 of the 140 such fields in the 156 archives here** contains. The DECODERS left on 2026-09-19 | **the format's own published description** — `reference/lha/header.doc.euc`, Masaru Oki's `header.doc` of 2 March 1992, levels 0/1/2 field by field with the extended-header types, the OS IDs and the method IDs; **lhasa (ISC)** for the four things it does not cover | **taken, whole file, at zero cost on every axis** — the walk needed no change, only a description: a reader written from the document plus lhasa reads 191 entries of 156 archives with no disagreement (`tools/derive_lzh.py`, `docs/formats/lzh-header.md`). The decoders were taken earlier for **−17.8 to −46.4 % of the 68000's instructions for +140 B** (DECISIONS.md 2026-09-19, *the match that was walked twice*) |
| `fmt_cpt.c` | **none since 2026-09-20** | `docs/formats/compact-pro.md` — the format's own published description (three wiki pages, all three fetched since that day) plus the six corrections it needs, each established by decoding whole forks | **both halves taken.** Speed: −31.7 % on a Mac Plus for +76 B, the two stages fused 2026-09-19 (DECISIONS.md, *the byte that went to two places at once*). Licence: the claim that "no non-copyleft description of the format exists" was **false** — the description was one hyperlink from a file already in `reference/notes/`, and a reader written from it alone reproduces 536 forks of 68 archives (DECISIONS.md 2026-09-20, *the description that was one link away*) |
| `fmt_packit.c` | **the two CRCs' polynomial, the resync rule and both ciphers, and nothing else, since 2026-09-21.** The container left this row that day, and the Huffman tree and the header-inside-the-stream fact on 2026-09-20 | **the format's own published description** — `reference/notes/packit_unpackit.txt`, appendices B and C of a 1986 freeware manual, named all along by `reference/notes/PackIt.md`, which this project fetched with its first batch of references and never read past | **taken: 38 of 38 forks** of the corpus's four archives read from the appendices plus the four corrections they need (`docs/formats/packit.md`, `tools/derive_packit.py`). "The app is not here" was the wrong question (DECISIONS.md 2026-09-21, *the manual for the other machine*) |
| `fmt_sit.c` | **none since 2026-09-22.** Method 6's framing was the last of it and left that day; the RLE90 filter and method 6's code book left on 2026-09-21, the container, method 13 and its tables, method 3's tree and method 8's coder on 2026-09-20 — bar three rules of method 8 no specimen reaches | `docs/formats/stuffit-method-6.md`, written against `reference/deark/modules/stuffit.c` (MIT); the rest is the format's own published description (The Unarchiver's wiki, fetched). StuffIt Deluxe 3.5.1 also runs here (`sitcrypt.py`) | **taken, whole file.** "No other reader anywhere" was false for method 13 — 897 forks across 103 archives read from the published description alone (DECISIONS.md 2026-09-20, *forty pages nobody had listed*) — and false for method 6, which deark implements under MIT. The code book was taken 2026-09-21 and priced: **code +408 B, A5 −1,000 B, net −592 B** (FORMATS.md, *StuffIt classic: method 6*). The **framing** followed on 2026-09-22 and cost nothing on any axis, because nothing executable had to change: a reader written from deark and the container page alone reads all 11 method-6 forks (`tools/derive_sit6.py`), and the three places this engine is stricter than both references are measured rather than transcribed (DECISIONS.md 2026-09-22, *the framing that needed no rewrite*) |
| `fmt_sit5.c` | **the ENCRYPTED archive only, since 2026-09-22** — where the password hash sits behind two optionally-present blocks, and the MD5-of-MD5 that grades a password. No corpus archive sets the bit. `sit_arsenic.c` was rewritten from Russotto's write-up on 2026-09-19, −36.7 % of a2basic's engine ticks (DECISIONS.md, *the rank that was walked a byte at a time*) | **the format's own published description** — `reference/notes/sit5_specs_theunarchiver.md`, the wiki page `reference/notes/StuffIt.md` has named in its *Sources* list all along. **Not Russotto's write-up**, which is method 15 start to finish and describes no container at all | **taken, at zero cost on every axis**: a reader written from that page alone reads all 31 StuffIt 5 fixtures, **525 entries**, agreeing with the oracle on every path and both fork lengths (`tools/derive_sit5.py`, `docs/formats/stuffit5-container.md`). The page needs one correction — its archive-header table gives offset 84 twice |
| `fmt_dd.c` | **the `DDAR` `0x20` raw-fork shape, and nothing else, since 2026-09-22** — four offsets nothing anywhere here sets. The folder records left this row the same day, measured against an archive DiskDoubler 3.7's own Combine command wrote. The containers left this row that day; methods 2/5 (splay) are published, 6/9 `ADn` and 10 `DDn` left on 2026-09-21, and method 4's tree on 2026-09-20 for `docs/formats/serialized-huffman-tree.md` | **the format's own published description** for `ADn` and `DDn` (`dd_ad_theunarchiver.md`, `dd_dd_theunarchiver.md`) — "documented nowhere else" was false. For the containers there is none: the wiki names `DiskDoublerSingleFormat`, `DiskDoublerArchiveFormat1` and `DiskDoublerArchiveFormat2` and **those three pages do not exist on it** (its `wikis.json` index, read 2026-09-22), so the description is this project's own, measured — DiskDoubler 3.7, 4.0 and Pro 4.1 run here | **taken twice.** The coders: **39 of 39 forks** from the pages plus six corrections (`docs/formats/diskdoubler-dd.md`, `tools/derive_dd.py`). The containers: **643 assertions against the oracle over all 91 DiskDoubler fixtures, 0 disagreements**, from `docs/formats/diskdoubler-container.md` — whose offsets `tools/derive_ddc.py --grid` re-derives by search rather than asserting. What is left has no specimen rather than no description, and the search for one is measured too: five shapes were offered to DiskDoubler 3.7 to provoke the `0x20` flag — nothing it compresses, an empty file, a forked file, an already-compressed file, plain text — and every one came back with a full file header behind its record, the flags word `0x0000` in all 44 records here. **"What would close it is a 1.x or 2.x DiskDoubler" was this row's answer until 2026-09-22 and it is withdrawn**: a 2.x DiskDoubler would not write a `DDAR` record of any flags. `DDExpand 2.03a`'s own `BNDL` declares five DiskDoubler file types and `DDAR` is not one of them, and the string does not occur anywhere in its resource fork; 3.1's declares those five and `DDAR`. So the flag can only come from a version that writes `DDAR` at all, which is the 3.x and later this project already runs — and what `--combine` measured is that 3.7 will not be provoked into it (BLOCKERS.md, *Withdrawn claims*; DECISIONS.md 2026-09-22, *the version that could not have written it*). The same search found the oldest DiskDoubler anywhere reachable, **ß05, Copyright 1990 Salient**, and it cannot write an archive either: its Finder menu is `Compress Selection;Expand Selection`, with no Combine. The same two specimens measured the folder records, and corrected the note twice: `+74` is the entry's whole SPAN, and a compressed file ends with a byte-identical copy of its own header — 63 of 66 (DECISIONS.md 2026-09-22, *the page that was never written*) |
| `fmt_now.c` | **none since 2026-09-21**, when the coders and the two block-table functions were rewritten from the note and the last two facts that rested on the reference were measured against Now Compress itself | `docs/formats/now-compress.md` — this project's own, measured off Now Compress 5.0.1 under emulation, because no published description exists anywhere. `tools/derive_now.py` reads **every block of both corpus archives** from it — the 1993 one's 3 and the 1995 one's 306, 9.9 MB — plus every specimen the harness has made | **taken.** The description came first (2026-09-21); the code followed the same day — one Huffman-region reader serving all three of its consumers, the two tables read straight out of a shape-3 header rather than staged through a 346-byte array, and the block table read in the one framing that needs no special case. **Byte-exact on all 124 Now files here and on `run_now.py`'s 42 archives, −204 B of `CODE`, −616 B of the frames its deepest chain uses (m68k `-Os -fstack-usage`, 2,264 → 1,648 B: a shape-3 block's 346-byte table staging moved into the per-archive allocation the code tables already live in), and engine 790 → 792 ticks on `derived-Expand_Now_1.0.1.sea` at 7 MHz, which is that instrument's own resolution.** The first draft of the rewrite was 21 ticks slower for reading better, and x86 instruction counts called it faster: FORMATS.md, *Decode cost*. The two rows that had pointed at the reference went with it: the **offset-delta search** is the format's (an archive rebased by 100 comes out of its own self-extractor byte for byte, and out of this engine not at all with the search disabled) and the **code-length escape past 15** is real (a block re-coded here with six symbols at 16–20 bits comes back out of Decompress intact). `tools/mutate_now.py` is the instrument for both |
| `fmt_arc.c` | **Crunch 5/6/7 and Crush (PAK's LZW)**; the method numbers and the CRC contract. The member header, RLE90, Squeeze (4), Crunch (8) and Squash (9) left this row 2026-09-20 for `docs/formats/arc-container-and-coders.md` | **deark (MIT)** for Distilled and Trimmed, already followed — **and for 5 and 6, which was not looked at until 2026-09-22**: `reference/deark/modules/arc.c`'s method table implements `crunched5 (static LZW)` and `crunched6 (RLE + static LZW)`, and leaves 7 and Crushed NULL exactly as this row does. **ARC 5.21q itself** (`tools/get_arc.sh`) writes methods 4, 8 and 9 to order, which is how the note was derived; nothing reachable writes 5/6/7, and PAK's Crushed did not fall to an LZW parameter search | small, and **not taken, decided 2026-09-22**: two of the three have an MIT implementation to be written from, but the row would not close (7 and Crush have none) so the licence would not move, and **nothing can grade a rewrite** — no corpus or reference archive uses 5/6/7. The route that would exist: write an ENCODER for 5/6 from the same description, have DEARK decode what it writes, and compare with this engine — two implementations agreeing on a stream neither wrote, which would be the first oracle these methods have ever had here. **What the two implementations already say, read side by side 2026-09-22 and not previously compared**: `reference/deark/src/fmtutil-lzw.c`'s `DE_LZWFMT_ARC5` is a **hashed** table of 4,096 entries at a fixed 12-bit code size, seeded with 256 roots under parent `0xffff`, hashing `((code + value) | 0x0800) & 0xffff` then `(h*h) >> 6`, and probing a collision by walking the chain and then `+101`, `+1`; `src/fmt_arc.c`'s non-`fast` branch is the same arithmetic, term for term, and it came from XADMaster. So the algorithm has **two independent statements that agree**, and deark's `arc5_has_stop_code` — the one parameter that would differ — is set by its LBR module and never by its ARC one, as here. That is evidence about two readers and not a stream; what an encoder would cost is the hash insertion ORDER, which it must reproduce exactly for the codes to land where either decoder looks |
| `unc_crypt.c` | `Crypto/des.c`, `md5.c`, `sha.c`, `aeskey.c` (public-domain or permissive in XADMaster's own tree); and from `XADStuffItDESHandle.m` the **nibble key schedule and the key derivation, which is all that is left**: the round folded onto standard DES's on 2026-09-19 | FIPS 46-3, RFC 1321, FIPS 180, FIPS 197, RFC 2898 | **taken, −416 B of code** (DECISIONS.md 2026-09-19, *the DES that was only wearing a disguise*). The rest cannot follow: the schedule reads all 64 key bits where PC-1 drops eight, so it is not the standard schedule of any permuted key |
| `fmt_macbinary.c`, `fmt_applesingle.c`, `fmt_sitseg.c`, `fmt_stubs.c` | what the 2026-09-19 re-citation could not move (DECISIONS.md, *the facts that were somebody else's to state*): three tolerances no specification supports — the MacBinary CRC-16/0xA001 fallback, its nonzero-date test, the byte-swapped AppleSingle header — and the StuffIt split header. **Now Compress's detect-only probe left this row on 2026-09-21**: every field it tests — the 24-byte file header, the entry record and the byte-sum checksum at +106 of it — is measured in `docs/formats/now-compress.md` off nine archives | none found for any of them; `fmt_binhex.c`, `fmt_exo.c` and `fmt_zipseg.c` left this row for their own specifications, and `fmt_stubs.c`'s other two probes for deark (StuffIt X) and macutils' `dd.h` (DiskDoubler) | none — the rest is facts, not code, so the licence never rested on it |

**What would close it:** one row at a time, each priced before it is
kept and graded by the suites that already cover the format — the
`-lh1-` row is the template. Of the rows once filed as having no other
description, only **Now Compress** never had a PUBLISHED one: StuffIt 8
and 13, DiskDoubler `ADn`/`DDn`, Compact Pro and PackIt were all
published, three of them on pages this tree had already fetched. Now
Compress could only be read against the application, which runs here —
reverse-engineering rather than transcription, the way SuperDisk! and
SpaceSaver were done — and on 2026-09-21 that description, and then the
code written from it, replaced the last of the transcription in
`fmt_now.c`.

## One volume walk that cannot see an invisible file

**Measured, not suspected.** `tools/vmac/walkprobe.py` builds one HFS
volume holding every shape that tells the walks apart and runs all eight
of them against it. Of those eight, on 2026-09-22, **seven see an
invisible file and one does not**: `superdisk.read_forks`. The table,
all four columns and how to re-run it: `tools/vmac/README.md`, *What
every walk can see*.

**It is last on purpose, and the reason is the callers rather than the
walk.** `superdisk.read_forks` has about thirty callers across nine
harnesses, and `-a` also surfaces the Finder's own invisible bookkeeping
— `Desktop`, `Desktop DB`, `Desktop DF` — on any volume a booted Mac has
touched. A caller that compares fork SETS would start failing on files
the Finder made, so this one needs the filter measured against nine
harnesses rather than one, and an emulator run for each. The four taken
on 2026-09-22 each needed a single harness re-run, and each now prints
what its filter dropped (DECISIONS.md 2026-09-22, *the folder the
application wrote and no walk could see*).

**What it has already lost**, which is the question `walkprobe.py`
cannot ask of any walk: `ndd.harvest` reads the Norton DiskDoubler Pro
floppy through this walk, and that floppy carries two invisible items —
`[DiskExpress Activity Log]`, which is invisible and locked, and
`Norton DiskDoubler Pro/Icon`. Neither is DiskDoubler output, so nothing
graded wrongly; both were unreported.

**What would close it:** the flag, a filter measured on each of the nine
harnesses' own volumes, and a re-run of each. `walkprobe.py --check` is
what says when it is done: all four of its `EXPECT_*` sets fail in both
directions.

## A DART's checksums, which this writes no fork to carry

**Not a scope decision and not a missing specimen: it is a missing
reference.** An expanded DART comes out with a data fork and nothing
else. A DART written by the application keeps its integrity check in the
RESOURCE fork — 'CKSM' 1 over the tags, 'CKSM' 2 over the data, and a
'DART' 0 string spelling both out — and this writes none of them
(FORMATS.md, *DART*).

Nothing currently reads them: MacMount parses the data fork alone, and
no other reader of the format is on this machine. And the bytes are
verified even so — `tools/run_dart.py` checks what came out against the
checksums DART recorded in 1993, which is the same assertion from the
other side.

**What would close it:** a statement of what an UNCOMPRESSED DART's
resource fork holds. DART 1.5.3 only ever wrote compressed files
(DART-notes.md: "Compression is always applied by DART v1.5"), so the
one shape this program produces is a shape no reference describes, and
writing a partial fork would be inventing the layout. An uncompressed
DART written by whatever produced them — an earlier version of the
application, per the same note — would settle it.

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

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
| PKWARE "strong encryption" in a zip (flag 0x40) | **named, refused per entry** | its key material is in a record nothing here parses, and XADMaster refuses it too. Every OTHER encryption these formats have is decrypted, including WinZip's AES (FORMATS.md, *Encryption*) |
| Disk images (`.image`, `.img`, `.iso`, `.cdr`, `.toast`, `.dmg`, `.smi`), and Disk Copy 4.2 | **not recognised**, and not extracted | extracting one means a filesystem rather than a codec, and naming one is worth nothing either: a disk image is not an archive, so the name leaves a user exactly where "not recognized" does. The probes are complete, graded and kept in `attic/` (DECISIONS.md 2026-08-26, *read the volume, not the extension*). **DART is the one exception, since 2026-09-09**, and it is an exception to the first clause only: a compressed DART expands to an UNCOMPRESSED DART, which is a codec with no volume anywhere in it, and no file on the disk is ever looked at. FORMATS.md, *DART* |
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
| `fmt_lzh.c` | the header walk and the CRC contract from `XADLZHParser.m` — the DECODERS are lhasa's since 2026-09-19 | **lhasa (ISC)** implements all of them | **taken, −17.8 to −46.4 % of the 68000's instructions for +140 B** (DECISIONS.md 2026-09-19, *the match that was walked twice*). What is left is a header walk, and lhasa's reading of it is already beside every field the two disagree about |
| `fmt_cpt.c` | container and LZH+RLE stages, with macutils `cpt.c` | Compact Pro 1.51 itself runs here (`cptcrypt.py`) | **taken, −31.7 % on a Mac Plus for +76 B** — the two stages fused, 2026-09-19 (DECISIONS.md, *the byte that went to two places at once*). The LICENCE does not move: no non-copyleft description of the format exists, so the container and the stages are still XADMaster's and macutils' |
| `fmt_packit.c` | container, with macutils `pit.c` — **less the Huffman tree and the header-inside-the-stream fact**, measured here 2026-09-20 | PackIt's own format is trivial; the app is not here | no |
| `fmt_sit.c` | parser; method **13** (`XADStuffIt13Handle.m`) — no other reader anywhere; 2, 3, 5 use the shared coders, and method 3's tree is `docs/formats/serialized-huffman-tree.md` since 2026-09-20. Method **8** is `docs/formats/stuffit-method-8-mw.md` since the same day **except for three rules no specimen reaches** — the table restart, the end-of-stream code and the 14-bit ceiling — which are still `XADStuffItOldHandles.m`'s | StuffIt Deluxe 3.5.1 runs here (`sitcrypt.py`) — an oracle, not a description | 13 is hot on `derived-Ultimate_Copland`; unknown |
| `fmt_sit5.c` | the container parser only — `sit_arsenic.c` was rewritten from Russotto's write-up on 2026-09-19, −36.7 % of a2basic's engine ticks (DECISIONS.md, *the rank that was walked a byte at a time*) | **Russotto's write-up** describes the SIT5 container too | none: a parser |
| `fmt_dd.c` | parser; methods 2/5 (splay, a published algorithm), 6/9 `ADn`, 10 `DDn` — the last two documented nowhere else. **Method 4's tree left this row 2026-09-20** for `docs/formats/serialized-huffman-tree.md` | DiskDoubler 3.7, 4.0 and Pro 4.1 run here and graded every method | 6/9/10 unknown |
| `fmt_now.c` | everything: `XADNowCompressHandle.m` is the only description of the format | Now Compress itself runs here (`nowcompress.py`) | after the slots, small |
| `fmt_arc.c` | **Crunch 5/6/7 and Crush (PAK's LZW)**; the method numbers and the CRC contract. The member header, RLE90, Squeeze (4), Crunch (8) and Squash (9) left this row 2026-09-20 for `docs/formats/arc-container-and-coders.md` | **deark (MIT)** for Distilled and Trimmed, already followed; **ARC 5.21q itself** (`tools/get_arc.sh`) writes methods 4, 8 and 9 to order, which is how the note was derived; nothing reachable writes 5/6/7, and PAK's Crushed did not fall to an LZW parameter search | small |
| `unc_crypt.c` | `Crypto/des.c`, `md5.c`, `sha.c`, `aeskey.c` (public-domain or permissive in XADMaster's own tree); and from `XADStuffItDESHandle.m` the **nibble key schedule and the key derivation, which is all that is left**: the round folded onto standard DES's on 2026-09-19 | FIPS 46-3, RFC 1321, FIPS 180, FIPS 197, RFC 2898 | **taken, −416 B of code** (DECISIONS.md 2026-09-19, *the DES that was only wearing a disguise*). The rest cannot follow: the schedule reads all 64 key bits where PC-1 drops eight, so it is not the standard schedule of any permuted key |
| `fmt_macbinary.c`, `fmt_applesingle.c`, `fmt_sitseg.c`, `fmt_stubs.c` | what the 2026-09-19 re-citation could not move (DECISIONS.md, *the facts that were somebody else's to state*): three tolerances no specification supports — the MacBinary CRC-16/0xA001 fallback, its nonzero-date test, the byte-swapped AppleSingle header — and two whole layouts, the StuffIt split header and Now Compress's detect-only probe | none found for any of them; `fmt_binhex.c`, `fmt_exo.c` and `fmt_zipseg.c` left this row for their own specifications, and `fmt_stubs.c`'s other two probes for deark (StuffIt X) and macutils' `dd.h` (DiskDoubler) | none — the rest is facts, not code, so the licence never rested on it |

**What would close it:** one row at a time, each priced with the tick
probe before it is kept and graded by the suites that already cover the
format — the `-lh1-` row is the template. Rows with no other description
(StuffIt 8 and 13, Now Compress, DiskDoubler `ADn`/`DDn`) can only be
rewritten against the original applications, which run here; that is
reverse-engineering, not transcription, and it is how SuperDisk! and
SpaceSaver were done.

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

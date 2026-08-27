# OPEN_ITEMS.md — what is missing, and what is deliberately not

Two kinds of thing live here, and they are kept apart on purpose:

1. **Out of scope** — decided, recorded so nobody re-litigates it, and the
   first section below because it is the thing a session most needs to know
   before starting work on a format.
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
here is closed by finding a file, and what is waiting for one is Part 2,
section 2. "Out of scope" is today's answer and not a refusal — the brief has
grown before, on request.

## Out by the brief

| what | status | why it stays out |
|---|---|---|
| Compression | not implemented | this is an extractor |
| StuffIt X (`.sitx`) | **detect-only** | out by the brief |
| PKWARE "strong encryption" in a zip (flag 0x40) | **named, refused per entry** | its key material is in a record nothing here parses, and XADMaster refuses it too. Every OTHER encryption these formats have — including WinZip's AES, which postdates the machines by a decade and is read anyway — is decrypted since 2026-08-23 (FORMATS.md, *Encryption*) |
| Disk images (`.image`, `.img`, `.iso`, `.cdr`, `.toast`, `.dmg`, `.smi`) | **not recognised**, since 2026-08-26, and not extracted | extracting one means a filesystem rather than a codec, and naming one is worth nothing either: a disk image is not an archive, so the name leaves a user exactly where "not recognized" does. Disk Copy 4.2 went the same day, for the same reason. The probes are complete, graded and kept in `attic/` (DECISIONS.md 2026-08-26) |
| PMarc (`-pm0-`, `-pm1-`, `-pm2-`) and `-lhx-` | **not recognised** | a different family behind an LZH-shaped header. PMarc is a Japanese PC format with its own coders, `-lhx-` is UNLHA32's extension; neither reached a Macintosh, and LZH itself only just did (2026-08-23) |
| Self-extracting LZH (an executable with an archive behind it) | **not recognised** | the archive sits behind DOS, Amiga, Atari or X68000 machine code, and finding it means knowing each of those loaders. `unar` has a parser per platform; here the answer is to hand the `.lzh` itself to the extractor |
| RAR, 7z, bzip2, xz, Cabinet, Zoo, ar/`.deb`, cpio, ARJ | **named since 2026-08-26, never extracted** | none is a Macintosh archive format, none carries a resource fork or Finder metadata, and every one is served by a maintained extractor on any machine that can run one (raised 2026-08-25, Macintosh Garden forum, *Archive formats*). NAMING them is in — the name is an instruction inside the frame the user arrived with (DECISIONS.md 2026-08-26; FORMATS.md, *Archives named but not extracted*) |
| Zip64 for files larger than 4 GB | **the counts are read since 2026-08-25 and the per-ENTRY escape since 2026-08-27; over-4-GB fields are refused, per archive or per entry**, and `unc_zipseg_describe` still answers `UNC_ERR_UNSUPPORTED` for a spanned set | the entry count, central-directory size and offset come from the Zip64 record as `uint32` halves, and so does an entry's own size and offset from extra field 0x0001 — which is what makes a 70,000-entry archive extract, and a 3.4 GB one (FORMATS.md, *Size limits*). ADDRESSING past 4 GB is the part that stays out: it would put 64-bit offsets in `UncIO` and every format would pay for them on a 68000. A field whose high half is set returns `UNC_ERR_UNSUPPORTED` for the archive or `UNC_ERR_TOOLARGE` for the entry (2026-08-14, revised 2026-08-25 and 2026-08-27) |

Everything detect-only is **named** by `unc_sniff`, and both front ends say
the name: the CLI prints *"recognized as RAR, which v1 cannot extract"* and
the Macintosh application's alert reads *"MacExtract cannot open RAR files."*
(photographed on System 6.0.8, 2026-08-26). Extraction returns cleanly
unsupported either way.

## Limits of the formats themselves

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

## 1. What is not verified

Verification gaps — things this project has and has not checked.
What it does not HAVE is section 2.

- **The Mac OS 9.2 tier has not run since M12.** Eight formats postdate
  it — ARC, uuencode, SuperDisk!, SpaceSaver, btoa, LZH, base64 and MIME —
  as do decryption and the named-only family, and its sample still
  records DiskDoubler as a refusal, which is what it was when that tier
  last ran. The other two tiers are re-run after every change
  (BLOCKERS.md). **What would close it:** an OS 9 sweep, which costs a
  full PowerPC boot per fixture — tens of minutes, against five for the
  whole System 7 tier.

- **Two things only that tier can show, and it has never been asked
  for either.** The interactive UI's cancel routes — Cmd-., the Cancel
  button, the dialog repainting afterwards — run on System 6.0.8 and,
  since 2026-08-25, on System 7.0.1 (TESTING.md, layer 10); on Mac OS 9
  the application has only ever been driven to completion. And how an
  8-bit MacRoman filename LOOKS there is unphotographed: the bytes are
  checked on every tier, the glyphs on the two Mini vMac ones.

- **The COLOUR icon members have never been displayed.** `ICN#` and `ics#`
  are photographed bound and drawn by a real Finder (DECISIONS.md
  2026-08-24, *the icon*), but Mini vMac emulates a 1-bit Mac Plus, so
  `icl4`/`ics4`/`icl8`/`ics8` have been drawn by nothing. **What would
  close it:** opening the application's folder on the Mac OS 9 tier
  (`tools/vmac/os9.py`, which has colour) and photographing it. The
  palette those members are indexed against is a separate gap, in
  section 2.

---

## 2. Waiting on a file this machine does not have

**Not scope decisions, and not effort.** Everything here is written or
writeable; what is missing is something to grade it against. They sit together across formats because that is how they
close — by somebody finding a file, and the finding usually arrives from
outside the format it settles. The question to bring here is *what did I just
find?*

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

- **Five archive formats are still unnamed for want of a reference:
  zstd, lzip, brotli, lrzip and WIM.** Missing: a **reference**. Nine
  others were named on 2026-08-26 out of `reference/XADMaster` and
  `reference/deark` (FORMATS.md, *Archives named but not extracted*); rule #1
  does not bend for a constant that is easy to look up. Extraction stays out
  of scope either way (Part 1). **What would close it:** an implementation or
  spec in `reference/` for any of them.

- **SuperDisk! method 13.** No corpus fixture uses it, and every setting of
  Alysis's own control panel produces method 1 or 6 (`sdcompress.py --sweep`).
  Its module is command-2 only, like method 20's, and its output is not shaped
  like a block here: it writes `length+8`, the word 13, then a **32-bit**
  uncompressed length, where every block this container holds has a six-byte
  header with a 16-bit one. The module itself is no longer the obstacle — it
  runs, given the 64 KB working buffer it demands and the one `_BlockMove` the
  runner now answers. **What would close it:** a file that actually contains
  one, which would say whether method 13 lives in a different container or
  whether the block header has a shape this project has not seen.

  Missing: a **gradeable specimen**. The writer was searched for on 2026-08-25
  and not found — SuperDisk! 2.x is on no archive this project can reach, the
  two surviving 1.x releases have no module loader in them at all, and of the
  later Alysis products that carry the module library, Alysis Resource
  Compressor 2.0 compresses into Apple's container and eDisk 1.2 and More Disk
  Space 1.1 carry only methods 1, 11 and a 13 named " Copy" (DECISIONS.md
  2026-08-25; `tools/vmac/rescomp.py`). One lead not followed: Disk Expander
  1.2's `INIT 32` has a compress path walking a method table.

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
  Named since 2026-08-23 from Aladdin's own recogniser (FORMATS.md,
  *AppleLink packages*), and detect-only because nothing here can grade
  a decoder. Three measured things suggest there is nothing to decode —
  that a package is a transfer manifest naming files beside it rather
  than a container — in which case this closes as a property of the
  format (DECISIONS.md 2026-08-23). **What is missing is a specimen**,
  which answers both.

- **A MIME message written by a MACINTOSH.** Every message the reader is
  graded against was built by `tools/run_mime.py` or read by munpack on
  Linux (TESTING.md, *base64 and MIME*). The independent specimen would be
  one written on the machine this is for — by mpack's own Macintosh port,
  by Eudora (1.2 is in the corpus as `eudora12qa.bin`), or by Claris
  Emailer — because what it would settle is the half no Unix tool has: how
  a real Mac laid out the `application/applefile` part, and what it put in
  the Finder-info entry. **What is missing is a gradeable specimen.**

- **A MIME part encoded `x-uuencode`, inside a multipart.** mpack decodes
  those; this does not. A uuencoded body posted to mail IS read — the
  uuencode probe runs before the MIME one and steps over the headers
  (FORMATS.md, *uuencode*) — so what is missing is only the case where one
  part of a MULTIPART message is uuencoded and another part is what the
  user wants. No specimen has been seen; the decoder is the uu one, which
  already exists.

- **`message/partial`: a message split across several FILES is not
  reassembled.** munpack does it, keyed by the `id` parameter and a
  reassembly directory. Here each file decodes on its own, and a part that
  is half an attachment yields half a file. The engine already joins
  multi-file sets four other ways (FORMATS.md, *Segmented archives*), so
  what is missing is a specimen to grade the fifth against, not a
  mechanism.

---

## 3. Untested code, named so it is not mistaken for tested

- **The Macintosh application does not read `UncEntryInfo.name_truncated`,
  and does not number a collision the way the CLI now does.** Added
  2026-08-27, when the engine started reporting a name it had to cut. The
  Mac shell shortens every name to 31 characters per component anyway, so
  it behaves exactly as it did before — which is defensible and undecided
  rather than done. Two entries whose names shorten alike still collide
  there, and a folder tree deep enough to sum past 255 bytes still puts a
  file under a name that is not the archive's, silently. **What would close
  it:** a decision about where the notice belongs on a Mac screen, `~1`
  numbering in `mac/macextract_mac.c`, and a tier run against a synthetic
  deep-tree `.sit`, which nothing in the corpus provides (FORMATS.md,
  *Name limits*).

- **Three formats report a cut name without the name.** DiskDoubler, Now
  Compress and SuperDisk! assemble their paths in a private 255-byte buffer
  — `unc_path_leaf`, which all three now share — and set
  `name_truncated = 1`; none of the three calls `unc_entry_long_name`, so
  the host is told a name was shortened and never told what it was. The
  formats that go through the shared helpers report 2 and hand the whole
  name over. The components are read out of headers the walk is still
  holding at the moment of the cut, so the limit is OURS rather than the
  format's — which is the test DECISIONS.md 2026-08-27 (*the name cap*)
  sets for this exact case. **Hypothesis:** no corpus fixture has a path
  long enough to reach it, so the degraded notice has been read rather
  than seen. **What would close it:** a synthetic deep-tree archive in one
  of the three, and the assembled path handed to `unc_entry_long_name`.

- **SuperDisk!, where a Huffman region's neighbour begins.** The two Alysis
  implementations disagree by one 32-bit refill when a coded flag bitmap ends
  exactly on a refill: this engine follows the 1991 self-extractor, the 1992
  Add-In Module has already fetched the next long (FORMATS.md, the method
  table). All 18 real blocks decode identically under both, so it is not known
  to cost anything. **What would close it:** a real block whose coded flag
  bitstream is a multiple of 32 bits — and sizing the subject does not produce
  one, because the 1991 panel codes the flags one bit each.
- **DiskDoubler's methods 3, 4 and 5 have never decoded a fork this project
  did not write.** All three are byte-exact through Salient's own 1991
  expander, which grades the reading of the format rather than the decoder
  (DECISIONS.md, methods 3, 4 and 5); what is untested is every encoding our
  own encoder does not emit. **What would change it:** one real fork of any of
  the three.
- **DiskDoubler method 5's tree-count byte is only confirmed at 0.** 0 means
  256 and expands byte-exact under both the 1991 and the 4.1.1 expander; a
  count of 16 is rejected by both, and encoder and decoder here share one
  reading, so either that shared reading of the non-zero case is wrong or
  non-zero counts do not occur. The branch is kept because it is XADMaster's
  reading and it fails as a per-entry checksum error rather than silently.
  **What would change it:** a method 5 fork with a non-zero count.



---

## 4. The same scaffolding, written once per format

**Nothing here is a defect.** Every format extracts byte-exact; what is
filed is that the code AROUND the codecs is copied rather than shared, and
what that has already cost. The codecs are not the subject — those are
different algorithms and stay that way. The reasoning, and the four
differences that are NOT duplication, are in DECISIONS.md 2026-08-27
(*the scaffolding audit*).

- **Six fork writers.** `SitFork`, `DdFork`, `LzhOut`, `CptRle`,
  `BtoaState` and `ArcTrim` are one type written six times: a staging
  buffer, a checksum, a `flush()` that guards on the options and calls
  `sink->write`, and a `put()` that flushes when the buffer is full. They
  differ on four axes and nothing else — which checksum, whether output
  stops at a declared length, one fork or two spans, and how "write or
  don't" is spelled. That last is spelled **four ways**: `!test_only`
  (StuffIt, btoa), `!test_only && !list_only` (DiskDoubler, and `UncStage`
  for SpaceSaver and SuperDisk!), a `write` flag the caller sets (LZH,
  ARC), and `!test_only && !quiet` (Compact Pro, where `quiet` grades a
  password candidate). Nothing is wrong today only because every caller
  ALSO wraps decode in `if (!opt.list_only)`: the rule is enforced twice,
  which is how it came to be written four ways without anything noticing.
  **What would close it:** one `UncForkOut` over those four axes.
  `int (*put)(void *, uint8_t)` is already the shared convention —
  `unc_lzah_decode`, `unc_lzdyn_decode` and `unc_arsenic_decode` all take
  one, and `UncStage` (`unc_util.c`) is the staging third of it already
  written. **Read to the closing brace of each before merging any two:**
  two of these look alike for eight lines and then stop (DECISIONS.md
  2026-08-27, *the scaffolding audit*).

- **Five RLE90 filters.** `sit_rle90`, `bh_next`, `dd_rle`, `arc_byte` and
  `arc_trim_put`. Two are pull-shaped, two push-shaped and one a bulk loop,
  which is why they were never shared. They have also drifted: ESC-1 is
  `UNC_ERR_CORRUPT` in StuffIt, BinHex and ARC, and a silently accepted
  no-op in `dd_rle`. That may well be right for DiskDoubler — macutils'
  `dd_rle` is its reference — but as written it cannot be told apart from
  an oversight. **What would close it:** one filter parameterised on escape
  byte and strictness, so the difference is an argument rather than an
  accident.

- **Smaller, and mechanical.** A canonical-Huffman builder written twice:
  `ss_a3_build`/`ss_a3_sym` reimplements `unc_canon_build_ext`/
  `unc_canon_decode` for one reason — the symbol order its own quicksort
  produces — and carries a weaker over-subscription check as a result
  (`code > (1u << (L + 1))` against the shared `space > (1u << l)`); a
  builder taking a pre-ordered symbol list would leave `fmt_spacesaver.c`
  holding only the sort. `sd_huff_bit` hand-rolls the MSB-first bit reading
  that `UncBitIn` over `unc_bufin_init_mem` already does, which is the
  shape `NowBits` in `fmt_now.c` uses — with one behaviour to settle first,
  that `sd_huff_bit` fails a stream ending mid-word where `UncBitIn` pads.
  Probes come in three signatures, which is why `unc_sniff` is a 120-line
  if-chain rather than a walk over an ordered table; the ordering it argues
  for is the valuable part of it and survives as table-row comments.
  `dd_fork` repeats the same `unc_alloc` / `unc_bufin_init` /
  `dd_out_start` prologue in nine branches — nine `unc_bufin_init` calls
  in that one function — where a per-method "extra bytes" table would hoist
  all three out. `unc_segment.c` dispatches on `desc->scheme` at six sites
  and both hosts do it again, though the per-scheme functions
  (`unc_ddseg_match`, `unc_cptseg_match`, `unc_ddseg_payload`, the four
  `*_describe`) already exist and would fill a vtable as they stand. And
  `4096` is a bare literal in eleven files; `fmt_spacesaver.c` is the one
  that names it.

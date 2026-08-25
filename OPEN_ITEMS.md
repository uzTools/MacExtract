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
byte-exact against the oracle across 927 fixtures in `./ci.sh`.

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
| Disk images (Disk Copy 4.2) | **detect-only**, with a real probe | out by the brief — the probe matches a synthetic 800K GCR image and a real one, 0 false positives |
| PMarc (`-pm0-`, `-pm1-`, `-pm2-`) and `-lhx-` | **not recognised** | a different family behind an LZH-shaped header. PMarc is a Japanese PC format with its own coders, `-lhx-` is UNLHA32's extension; neither reached a Macintosh, and LZH itself only just did (2026-08-23) |
| Self-extracting LZH (an executable with an archive behind it) | **not recognised** | the archive sits behind DOS, Amiga, Atari or X68000 machine code, and finding it means knowing each of those loaders. `unar` has a parser per platform; here the answer is to hand the `.lzh` itself to the extractor |
| Zip64 spanned sets | `unc_zipseg_describe` answers `UNC_ERR_UNSUPPORTED`, cleanly | an EOCD with disk number `0xFFFF` defers to a locator nothing here parses. Zip64 postdates every machine this project targets by a decade and a set that needs it is 2 GB+; refusing it cleanly is the right answer, not a missing feature (2026-08-14) |

Everything detect-only is **named** by `unc_sniff`, so a UI can tell the user
what the file is and extraction returns cleanly unsupported.

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

- **The Mac OS 9.2 tier has not run since M12.** Everything from
  DiskDoubler and Now Compress onwards postdates it — ARC, uuencode,
  SuperDisk!, SpaceSaver, decryption and btoa — and its sample still
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

---

## 2. Waiting on a file this machine does not have

**Not scope decisions, and not effort.** Every entry here is a format or a
method whose decoder is written or writeable; what is missing is something to
grade it against. They sit together across formats because that is how they
close — by somebody finding a file, and the finding usually arrives from
outside the format it settles. The question to bring here is *what did I just
find?*

Each says which of the two is missing, because the searches are different:

- a **reference** — a spec, an implementation, or a self-extracting specimen,
  which is one; rule #1 forbids writing a format without it;
- a **gradeable specimen** — a file written by something else, so our output
  has something to be wrong against.

Unlike section 3, none of this is impossible here: a download would do it.

- **ARC 0x0a/0x0b.** No corpus fixture uses either and nothing reachable
  writes them, so an implementation could not be graded — code no oracle
  can check is the same bargain LZH's `-lh2-`/`-lh3-` make. **What is missing is a
  gradeable SPECIMEN:** a `.arc` written by PKARC or PKPAK using method
  0x0a or 0x0b. DOS-side, so the likeliest source is a shareware
  collection rather than a Macintosh archive. Before filing anything else
  here, ask the two questions that have emptied this section twice:
  **is there an implementation that could be FED?** (DECISIONS.md, methods
  3, 4 and 5) and **is "X does not survive" a claim about somebody's
  search?** (BLOCKERS.md, SuperDisk!'s compressor).

- **SuperDisk! method 13.** No corpus fixture uses it, and every
  setting of Alysis's own control panel produces method 1 or 6
  (`sdcompress.py --sweep`). **Two of the three methods that used to
  sit here left on 2026-08-25**: 10 was transcribed from its module and
  graded three ways, and **20 turned out not to be a block method at
  all** — its module is an ENCODER whose output declares method 11
  (FORMATS.md, the method table). 13 is the same shape as 20 —
  command 2 only — and what leaves it open is that its output is not
  shaped like a block here: it writes `length+8`, the word 13, then a
  **32-bit** uncompressed length, where every block this container
  holds has a six-byte header with a 16-bit one. **What would close
  it:** a file that actually contains one, which would say whether
  method 13 lives in a different container (the extension's
  `compressFile` command has its own) or whether the block header has
  a shape this project has not seen. The module itself is no longer
  the obstacle: it runs, given the 64 KB working buffer it demands and
  the one `_BlockMove` the runner now answers.

  The writer of all of them was searched for on 2026-08-25 and not found.
  The vendor's own technology page names SuperDisk! **2.x** as the release
  with "faster and tighter compression algorithms"; it is not on
  Macintosh Repository, Macintosh Garden, Info-Mac's `cmp` directory or
  in archive.org's index, and the two 1.x releases that survive have no
  module loader in them at all (no `Cmpr`, no "Add-In", measured). Of
  the later Alysis products that carry the module library, **Alysis
  Resource Compressor 2.0** (1993) compresses into APPLE's container
  with `defProcID` 0 rather than a `Cmpr` codec
  (`tools/vmac/rescomp.py`), and eDisk 1.2 and More Disk Space 1.1 carry
  only methods 1, 11 and a 13 named " Copy". The one candidate left in
  hand is Disk Expander 1.2's own extension, whose `INIT 32` has a
  compress path walking a method table. One lead not followed: the panel's help offers JPEG lossy,
  lossy sound and a lossless sound/video mode that no `Cmpr` name
  accounts for — and a lossy mode is something an extractor cannot grade
  against its input by construction.

- **StuffIt SpaceSaver's methods 1, 2 and 3.** The format is read and
  implemented — container, method 0, method 4, dictionary included
  (FORMATS.md, *StuffIt SpaceSaver*). The other three are declined per
  entry: their modules are in hand, so this is transcription rather
  than research, but nothing reachable writes one — index 3 takes a
  68030 or better, and the engine's default never selects 1 or 2.
  **What is missing is a gradeable SPECIMEN:** any file that uses one.

- **A SpaceSaver file written by SpaceSaver.** Thirteen emulator runs
  have driven every trigger its control panel offers and none of them
  compressed anything. **The extension is not the reason, which is new
  on 2026-08-25**: a boot that never opens the panel writes
  `Preferences:SpaceSaver Preferences` onto an image that had none, so
  `INIT 0` runs and installs — and its every named refusal would have
  put up a Notification Manager alert, which no run has ever
  photographed (BLOCKERS.md). **Worth less than it was**: the bitstream
  a specimen would check has since been cross-read against Aladdin's own
  encoder and agrees field for field (DECISIONS.md 2026-08-23, the
  encoder agrees). **What would close it:** why the TRIGGER never fires
  — the `small` name rule is in the preferences the INIT writes, and
  renaming a file to match it still returns the file unchanged — or one
  SpaceSaver file from anywhere.

- **An encrypted StuffIt 5 archive.** StuffIt classic's half closed on
  2026-08-23 — StuffIt Deluxe 3.5.1 writes the specimens now
  (`tools/vmac/sitcrypt.py`), and they corrected the archive key —
  but nothing here writes a StuffIt **5** one: 3.5.1 predates the
  format and Deluxe 5.0.1 needs a System this machine does not run.
  So RC4-encrypted `.sit5` is still generated here and adjudicated by
  `unar -p`, which grades two readings against each other and neither
  against Aladdin. **What is missing is a gradeable SPECIMEN.** The
  classic case is the warning: there, both readings were wrong, and
  they were wrong in ways that agreed with each other for exactly the
  password lengths anybody would have tested.

- **AppleLink `.pkg`: one file, which would settle two questions.**
  Named since 2026-08-23 from Aladdin's own recogniser (FORMATS.md,
  *AppleLink packages*), and detect-only because nothing here can grade
  a decoder. Three measured things suggest there is nothing to decode —
  that a package is a transfer manifest naming files beside it rather
  than a container — in which case this closes as a property of the
  format (DECISIONS.md 2026-08-23). **What is missing is a specimen**,
  which answers both.

---

## 3. Cannot be closed in this environment

- **Real 68k hardware: never run.** No genuine floppy I/O, no real media errors
  mid-write, no real stack underneath a real ROM's own usage — 32 KB of it,
  since `kStackBump` takes 24 KB off `ApplLimit` on top of the 8 KB default
  (FORMATS.md, *Stack*, which has the deepest chain the engine reaches). The
  per-entry I/O error path has never seen an actual I/O failure. The 1 MB
  figures come from an emulated 1 MB machine with a stripped System Folder; a
  real Plus with a Chooser extension or two has less free heap than any number
  recorded here.
- **Real PowerPC hardware: never run.** Mac OS 9 is verified under QEMU only.
- **The COLOUR icon members are unverified.** `ICN#`/`ics#` are photographed
  bound and drawn by a real Finder (DECISIONS.md 2026-08-24, *the icon*),
  but Mini vMac emulates a 1-bit Mac Plus, so `icl4`/`ics4`/`icl8`/`ics8`
  have never been displayed by anything. The 256-colour indices also assume
  the Macintosh palette is a 6x6x6 cube at `36*r + 6*g + b` with black at
  255 — **reconstructed, not transcribed from a reference**, and stated as
  such in `tools/icon/make_icon.py`. What would close it: opening the
  application's folder on the Mac OS 9 tier (`tools/vmac/os9.py`, which has
  colour) and photographing the icon, or a reference for the system palette.
- **A btoa file written by a Mac.** Every stream the btoa decoder is graded
  against comes out of one encoder, btoa 5.2.1 on Linux (TESTING.md, *btoa*).
  The independent one would be Aladdin's own `btoa/atob Translator`, and it is
  reachable only through a hierarchical menu, which cannot be selected under
  Mini vMac (`tools/vmac/README.md`, *sitcrypt.py*). **`--btoa-drop` was never
  going to work**: `DropConvert™` is `APPL/SITC` and its own strings —
  `Archive.sit`, `.sit`, `Archive.sea`, `.sea`, *"Unable to convert this
  archive…"* — say it converts ARCHIVES between StuffIt and self-extracting,
  not documents between encodings (measured 2026-08-25, off the installed
  image with `hcopy`; no emulator). What would close it: a route to the
  translator that is not a submenu. One is untried and is the shape of
  `tools/sdmodule/` — a translator is a subroutine (`main(pb, selector)`,
  DECISIONS.md 2026-08-23), so it could run under `qemu-m68k` like Alysis's
  codecs do, except that it calls Toolbox traps and would need a few of them
  answered.
- **The XADMaster DDn report is not filed.** Its DDn reads one byte past a
  fork's declared compressed length; reduced to a 1,166-byte reproduction and
  written up ready to post in `tools/xadmaster-ddn-repro/`. **Deliberately
  not submitted, and no future session should submit it** — same terms as the
  Retro68 report below, and not possible from here either.
- **The Retro68 `OpenDF`/`HOpenDF` report is not filed.** The `_OpenDF` trap is
  System 7 and neither falls back to a plain open on `paramErr`, so both are
  unusable on System 6; `FSOpen` in the same file does fall back. Measured,
  cases 8 and 11 of `tools/retro68-hopen-repro/`, written up in that
  directory's `ISSUE.md`. **Deliberately not submitted, and no future session
  should submit it** — the maintainer will post it from his own account. (It is
  also not possible from here: an unauthenticated POST to the issues API
  returns 401.)

---

## 4. Known unknowns, not being chased

- **A zip's end-of-central-directory comment is read past and dropped.**
  `UncSink` has carried a comment callback since 2026-08-23 and Compact
  Pro's fills it; `fmt_exo.c` still skips zip's, which one corpus
  fixture has 495 bytes of (`derived-MUSFMT10.ZIP`). Not chased because
  a zip comment is usually the writer's boilerplate rather than
  somebody's note, and `unar` does not write one out either. **What
  would close it:** the EOCD comment length is already parsed — one
  call to the callback, and the manifest's `comment` key stops being
  excused for `Zip` in `tools/run_diff.py`.
- **Why the pointer does not work under QEMU on Mac OS 9.** Measured to
  0.0000 effect across five mouse primitives; the mechanism behind that has no
  reproduction and is labelled a guess. The keyboard route works, so this costs
  nothing.
- **Names HFS+ permits that HFS does not.** Probably unreachable from this
  binary at all — the classic File Manager caps components at 31 characters on
  either filesystem — but that is unproven either way.

---

## 5. Untested code, named so it is not mistaken for tested

- **SuperDisk!, where a Huffman region's neighbour begins.** The two
  Alysis implementations disagree with each other by one 32-bit refill
  when a coded flag bitmap ends exactly on a refill: this engine follows
  the 1991 self-extractor, the 1992 Add-In Module has already fetched the
  next long (FORMATS.md, the method table). Reachable only through
  `tools/sdmodule/`'s own encoder; all 18 real blocks — both corpus
  archives and Alysis's own compressor, including four subjects made for
  this on 2026-08-25 — decode identically under both, so it is not known
  to cost anything. **What would close it:** a real block whose coded
  flag bitstream is a multiple of 32 bits. Sizing the subject does NOT
  produce one, which is what those four established: the 1991 panel
  codes the flags one bit each, so the bit length is data-dependent and
  the byte count says nothing about it.
- **DiskDoubler's methods 3, 4 and 5 have never decoded a fork this
  project did not write.** All three are byte-exact through Salient's own 1991 expander,
  which grades the reading of the format rather than the decoder
  (DECISIONS.md, methods 3, 4 and 5) — so what is untested is every
  encoding our own encoder does not emit: run lengths it never chooses,
  Huffman tree shapes it never builds, contexts it never reaches.
  **What would change it:** one real fork of any of the three.
- **DiskDoubler method 5's tree-count byte is only confirmed at 0.** 0 means 256 and
  expands byte-exact under both the 1991 and the 4.1.1 expander; a count of
  16 is rejected by both with *Checksum failed*, and encoder and decoder
  here share one reading, so the shared reading of the non-zero case is
  what is wrong — or non-zero counts do not occur. The branch is kept
  because it is XADMaster's reading and it fails as a per-entry checksum
  error rather than silently. **What would change it:** a method 5 fork
  with a non-zero count.
- **Files larger than the HFS 2 GB cap**, and the engine's 32-bit-only
  arithmetic against them.

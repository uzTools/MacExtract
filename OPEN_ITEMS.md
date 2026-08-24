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

- **LZH's `-lh2-` and `-lh3-`.** Both are implementable — the code is in
  `reference/XADMaster/XADLZHOldHandles.m`, and it is transcription
  rather than research — but no archive that uses either is reachable:
  not in the corpus, not among the **fourteen** LHA implementations
  whose output lhasa collects, and nothing here writes one. **What is
  missing is a gradeable SPECIMEN.** XADMaster's recogniser calls the
  pair "old experimental" and every writer since emits `-lh5-` or
  better, so the likeliest source is a Japanese PC archive of the early
  1990s rather than anything Macintosh.

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

- **SuperDisk! methods 10, 13 and 20.** No corpus fixture uses any of
  them, so an implementation could not be graded. **What is missing is a
  gradeable SPECIMEN, and the compressor is in hand and cannot write
  one**: every setting of Alysis's own control panel produces method 1
  or 6 (`sdcompress.py --sweep`), and 11 needs an Add-In Module that a
  corpus archive happens to carry, so these three plausibly need modules
  too. **What would close it:** an archive that uses one, or the Add-In
  Modules. One lead not followed: the panel's help offers JPEG lossy,
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

- **A SpaceSaver file written by SpaceSaver.** Twelve emulator runs have
  driven every trigger its control panel offers and none of them
  compressed anything, because its extension does not install here;
  three causes are ruled out by measurement and five of `STR# 1001`'s
  seven refusals are untested (DECISIONS.md 2026-08-22, what will not
  compress). **Worth less than it was**: the bitstream a specimen would
  check has since been cross-read against Aladdin's own encoder and
  agrees field for field (DECISIONS.md 2026-08-23, the encoder agrees).
  **What would close it:** why `INIT 0` declines, or one file from
  anywhere.

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
- **The low-memory ALERT is unverified on screen.** That the shortfall is
  computed correctly is graded in `ci.sh` (`mac_sink --shortfall`, exact to
  the byte, on native ASan and big-endian m68k), and the CLI prints the same
  figure. What has NOT been photographed is the alert itself. Three attempts
  failed on harness shape rather than on the code: `interactive.py`'s default
  phase CANCELS both of its extractions deliberately (it is testing Cancel
  and Cmd-.), so it never reaches a result alert, and `--e2e` had moved on to
  the Finder by the time it took its `complete` frame. What would close it: a
  phase that runs one extraction to completion against a partition too small
  for the archive, and screenshots the alert before dismissing it.
- **The full-disk ALERT is unverified.** That a full destination volume
  stops the run after one error is measured (`tools/vmac/README.md`,
  *Filling the destination on purpose*); that the user is then shown "The
  disk is full" rather than the generic message is not. The choice is one
  comparison against `gLastWriteErr` in the interactive build, which the
  headless harness does not run. What would close it: a full-disk case in
  `interactive.py`, which drives the real UI and photographs each step.
- **A btoa file written by a Mac.** Every stream the btoa decoder is graded
  against comes out of one encoder, btoa 5.2.1 on Linux (TESTING.md, *btoa*).
  The independent one would be Aladdin's own `btoa/atob Translator`, and it is
  reachable only through a hierarchical menu, which cannot be selected under
  Mini vMac (`tools/vmac/README.md`, *sitcrypt.py*). What would close it: a
  route to that translator that is not a submenu — `--btoa-drop` is the attempt
  and does not write a file yet.
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

- **The interactive UI above System 6 is deliberate scope**, not a gap
  (2026-08-02). System 6 is the UI's target and it is driven end to end there.
  What that leaves unexercised: `ProgressPump()` branches on `gHasWNE`, and the
  cancel routes inside it — Cmd-., the Cancel button via `DialogSelect`, the
  dialog repainting — have only ever run on the `GetNextEvent` side. Mac OS 9
  runs the `WaitNextEvent` side, but only where nothing is cancelled. The
  engine and sink semantics of a cancel are covered separately: unit tests,
  both write paths through the qemu-m68k mock in `ci.sh`, and `UNC_AT_CANCEL`
  on-Mac at 4 MB and 1 MB.
- **SuperDisk! methods 2, 3, 4, 5, 8 and 9 have never decoded anything.**
  Both corpus archives use one method each — 7 and 11 — so most of the
  13-bit context family, two of the four wide variants and Huffman-alone
  are transcribed, compiled and never run. The unit test cannot help: it
  builds stored blocks, because writing coded ones would mean grading
  this decoder against an encoder written from the same reading. That
  the entry is worth keeping is not a guess — when 1 and 6 left it on
  2026-08-22, one of the two turned out to be broken (DECISIONS.md
  2026-08-22, last). **What would change it:** an archive that uses one,
  or the `Cmpr` modules run under emulation as a second implementation.
- **Methods 3, 4 and 5 have never decoded a fork this project did not
  write.** All three are byte-exact through Salient's own 1991 expander,
  which grades the reading of the format rather than the decoder
  (DECISIONS.md, methods 3, 4 and 5) — so what is untested is every
  encoding our own encoder does not emit: run lengths it never chooses,
  Huffman tree shapes it never builds, contexts it never reaches.
  **What would change it:** one real fork of any of the three.
- **Method 5's tree-count byte is only confirmed at 0.** 0 means 256 and
  expands byte-exact under both the 1991 and the 4.1.1 expander; a count of
  16 is rejected by both with *Checksum failed*, and encoder and decoder
  here share one reading, so the shared reading of the non-zero case is
  what is wrong — or non-zero counts do not occur. The branch is kept
  because it is XADMaster's reading and it fails as a per-entry checksum
  error rather than silently. **What would change it:** a method 5 fork
  with a non-zero count.
- **Files larger than the HFS 2 GB cap**, and the engine's 32-bit-only
  arithmetic against them.
- **MacRoman filename display and 8-bit characters above System 6.** The bytes
  are checked everywhere; how they *look* on 7 and 9 is not.

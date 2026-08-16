# OPEN_ITEMS.md — what is missing, as of 2026-08-15

A standing audit of the gaps: things not done, things done but not verified,
and things this repository asserts more confidently than the evidence supports.

**Not** BLOCKERS.md, which records investigations that went wrong and the
claims withdrawn from them. Nothing here stops the engine or the CLI, which are
byte-exact against the oracle across 809 fixtures in `./ci.sh`.

Each item says what would close it. Detail lives in one place per finding —
status in BLOCKERS.md, reasoning in DECISIONS.md, how to re-run in TESTING.md
or `tools/vmac/README.md`, what needs real hardware in MANUAL_TESTS.md,
results in FORMATS.md — and is cross-referenced from here rather than
repeated.

**Filing something here is a decision to stop looking at it, so it had better
be true.** Section 3 in particular: it held "eight fixtures are excluded as
oracle-undecidable or oracle-buggy" until 2026-08-08, when the item turned out
to be nine fixtures, closeable in an hour, and nothing to do with this
environment — it was a fork-naming flag of the oracle (DECISIONS.md,
BLOCKERS.md, 2026-08-08).

**Only open items live here.** A closed one moves out: the lesson to
DECISIONS.md, the withdrawn claim to BLOCKERS.md, the numbers to FORMATS.md.
The old section 4 used to be *Multi-segment*, and on 2026-08-14 it emptied: all
four schemes join on Linux and on the Macintosh, and the last thing in it
— taking an envelope off each part — was built the same day. A section 5
held multi-document BinHex for one day and emptied on 2026-08-15 (M2
follow-up in PROGRESS.md; DECISIONS.md for what it taught about oracles).
A section that empties is the point of the file.

---

## 1. Now Compress: one fork nobody can grade

Everything the first fixture could not reach is exercised since
2026-08-15 by generated archives graded by `unar` (TESTING.md, "Now
Compress: the archives the corpus does not have"). A **second real
archive** joined the corpus on 2026-08-16, found by creator code rather
than by name: folders, both forks, two streams and two stream-restart
records on 1995 bytes, 9.9 MB out of 2.9 MB at the same flat 128 KB.
And on the same day the **block shapes stopped being a transcription
checked against its own source**: `tools/vmac/nowcompress.py` drives Now
QuickFiler 5.0.1 under Mini vMac, so stored, LZSS-only and
Huffman-then-LZSS now exist as bytes the ORIGINAL encoder wrote, decoded
byte-exact here and by `unar` (DECISIONS.md, FORMATS.md ✧). What is left
is one thing:

- **Four forks of the 1995 fixture are adjudicated by nobody.** `unar`
  fails every one of them — 129 of the archive's 306 blocks end within
  7 bits of their buffer, which its bit reader cannot survive
  (DECISIONS.md) — and `macunpack` has never known the format. `lsar`
  still walks it, so names, type and creator are ground truth and the
  forks are marked unadjudicated, like DiskDoubler's 11 in section 2.
  Our output is defended structurally instead: `tools/run_now.py`
  requires the resource fork we produce to be a resource fork, and
  that check fails when the decoder is mutated. **What would close it:**
  a second implementation of Now Compress. None exists.

---

## 2. DiskDoubler: what M12 left

- **Methods 1, 2, 3, 4, 5 and 7 are declined per entry.** No corpus
  fixture uses any of them; the reference marks 3 and 4 unimplemented
  and 5 untested. Writing them would produce code no oracle here could
  grade — the same reason LZH extraction stays out of scope. Method 1
  is the cheapest if a fixture ever turns up: it is Unix compress, and
  `unc_lzw` already exists.
- **11 forks across 2 fixtures are adjudicated by neither oracle**
  (`derived-Terrainman_2.0__.sea`, `derived-LHA_Expander_1.0.3.sea`).
  `unar` fails on them and `macunpack` — built with its own DiskDoubler
  support — fails too. We extract them; nobody grades them.
- **The single-file container (`0xABCD0054` at offset 0) has no
  fixture.** Every DiskDoubler file in the corpus is a `DDAR` or `DDA2`
  archive. The path is covered by a unit test, including the name
  coming from the host rather than the archive, which is what the
  reference does with a `.dd` suffix.
- **Two of the four Mac tiers have not re-run since M12 or M13.** The
  System 6 tiers have (63/63 at 4 MB and at 1 MB, 2026-08-15). **System 7.0.1 and
  Mac OS 9.2 have not**: System 7 stands at 55/55 on the pre-M12 sample
  (2026-08-08), so the seven fixtures M12 added and the two M13 added have
  never run there, and
  the OS 9 sample still records DiskDoubler as a refusal, which is what
  it was when that tier last ran. FORMATS.md marks those rows pre-M12.
  **What would close it:** `run.py --system Sys7.img --list
  tools/vmac/sample.txt` (Mini vMac, cheap) and an OS 9 sweep, which
  costs a full PowerPC boot per fixture.

---

## 3. Cannot be closed in this environment

- **Real 68k hardware: never run.** No genuine floppy I/O, no real media errors
  mid-write, no real 8 KB stack underneath a real ROM's own usage. The
  per-entry I/O error path has never seen an actual I/O failure. The 1 MB
  figures come from an emulated 1 MB machine with a stripped System Folder; a
  real Plus with a Chooser extension or two has less free heap than any number
  recorded here.
- **Real PowerPC hardware: never run.** Mac OS 9 is verified under QEMU only.
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
- **Files larger than the HFS 2 GB cap**, and the engine's 32-bit-only
  arithmetic against them.
- **MacRoman filename display and 8-bit characters above System 6.** The bytes
  are checked everywhere; how they *look* on 7 and 9 is not.

---

## 6. Deliberate gaps, and remedies ruled out by measurement

- **Zip64 spanned sets, out of scope as of 2026-08-14.** An
  end-of-central-directory record whose disk number is `0xFFFF` defers to
  the zip64 locator, which nothing here parses; `unc_zipseg_describe`
  answers `UNC_ERR_UNSUPPORTED`. It was ranked as a gap until somebody
  asked the obvious question: zip64 postdates every machine this project
  targets by a decade, a set that needs it is 2 GB+, and no archive of
  the era could be one. Refusing it cleanly is the right answer, not a
  missing feature.
- **Out of scope by the brief, and still out:** compression, StuffIt X
  (`.sitx`), encrypted archives, disk-image extraction, and
  LZH *extraction* — the optional half of M8, and the evidence for
  leaving it there is that **the corpus contains no `.lzh` at all**:
  Macintosh software was not distributed that way. It would be ~550 new
  lines, since Compact Pro's LZH is a different algorithm from LHA's.
  The detect-only claim itself is now tested rather than asserted
  (DECISIONS.md 2026-08-14). **Multi-segment archives are IN scope
  since 2026-08-08** and four schemes are implemented (StuffIt segments,
  Compact Pro segments, spanned zip, plain `.NNN` splits); the rest are
  the section above.
- **The four formats StuffIt Expander 4.0.2's add-on expanded were brought
  IN scope on 2026-08-15, and two of them are done.** `.arc` (ARC and
  ArcMac) and uuencode (`.uu`, including UUTool's two-fork shape) extract —
  M13, FORMATS.md ★. The other two are open, and not for want of effort:

  - **AppleLink `.pkg` and StuffIt SpaceSaver cannot be written under
    rule #1.** Neither has a reference implementation or a published layout
    anywhere reachable. Searched 2026-08-15: the only AppleLink format with
    documented internals is the Apple II `.acu` (CiderPress2's format notes,
    magic `fZink`), which that page explicitly distinguishes from the
    Macintosh Package format; SpaceSaver has no specification, no open
    implementation, and Aladdin's own later Expanders dropped it. Neither
    can even be **sniffed** without inventing a magic number, so a user still
    gets *unknown* rather than a name. **What would close it:** a specimen
    plus the original application, derived under Mini vMac the way Compact
    Pro's segment layout was (DECISIONS.md 2026-08-14) — or one published
    description of either format.
  - **An ArcMac entry's payload is declined.** The container is walked and
    the entry reported with its real Mac name, type, creator and fork
    lengths (all documented in `reference/macutils/macunpack/arc.h`), but
    the single compressed stream holds both forks and nothing says which
    comes first. macutils' `arc.c` — the only implementation that ever read
    it — is missing from the distribution, upstream tarball included. Now
    Compress puts the resource fork first and lists it second, so the order
    is not guessable by analogy either. **What would close it:** one real
    ArcMac archive with both forks non-empty; a resource fork identifies
    itself from its own first 16 bytes, so a single specimen decides it.
  - **A uuencoded set missing a MIDDLE part decodes short, and silent.**
    Since 2026-08-15 a document posted in several parts joins and
    decodes — the mail headers between the parts are stepped over — but
    uuencode carries no length and no checksum anywhere, so nothing can
    notice that a part never arrived. A missing LAST part IS caught (the
    terminator and `end` live there). Asserted rather than described:
    `tools/run_uu.py` builds a gapped set and requires exactly this
    result, so the day the format turns out to have a check, the suite
    says so. **What would close it:** nothing in the format. A host that
    knows the parts were numbered `1/5` could check the count, which is
    a naming question and not a decoding one.
  - **ARC methods 0x0a (Crushed) and 0x0b (Distilled) are declined per
    entry.** PKARC's, and nothing reachable from here writes one, so an
    implementation could not be graded — the DiskDoubler rule.

- **Alysis SuperDisk! is the one format this corpus holds that nothing
  here names.** Two files, both inside envelopes, so a user gets the
  payload and then *unknown*: `Disk Expander .X` and `SD! Utilities.x`,
  out of `alysis-disk-expander-12.hqx` and `super-disk-utility.hqx`
  (FORMATS.md ✧✧). `unar` reads no further than the envelope either, so
  it is not on the Expander comparison's list and nothing had looked for
  it — it fell out of the innermost-format pass. **What would close the
  sniff:** a reference. There is none in `reference/` and XADMaster does
  not implement the format, so this is blocked exactly the way
  AppleLink `.pkg` and SpaceSaver are, by evidence rather than effort.
- **Compact Pro archive comments are read, CRC'd and discarded.**
  Expander 4.0.2 writes them out beside the extracted items. Deliberate:
  a comment is not a file, and the sink writes files. Noted so that the
  difference is a decision rather than an oversight.
- **Do not retry, on Mac heap pressure.** Both were measured while StuffIt 5 /
  Arsenic was still short of the 1 MB floor, and both are dead ends:
  `MaxMem()` before a retry (compaction may not move a `NewPtr`), and
  relocatable blocks moved high with `MoveHHi` (it demonstrably works,
  205,828 → 803,634, and changed `MaxBlock` at the refusal by under 500 B —
  the stranded heap was never about where the live blocks sat). Cited from
  `src/sit_arsenic.c` and `mac/unclassic_mac.c`.

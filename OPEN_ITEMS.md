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
byte-exact against the oracle across 916 fixtures in `./ci.sh`.

Detail lives in one place per finding — status in BLOCKERS.md, reasoning in
DECISIONS.md, how to re-run in TESTING.md or `tools/vmac/README.md`, what needs
real hardware in MANUAL_TESTS.md, results in FORMATS.md — and is
cross-referenced from here rather than repeated.

**Filing something here is a decision to stop looking at it, so it had
better be true.** The section that held "eight fixtures are excluded as
oracle-undecidable" was wrong about the count, the cause and the difficulty —
it was closeable in an hour and had nothing to do with this environment
(BLOCKERS.md, *Withdrawn claims*).

**Only OPEN items live in part 2.** A closed one moves out: the lesson to
DECISIONS.md, the withdrawn claim to BLOCKERS.md, the numbers to FORMATS.md.
Three sections have emptied and been removed that way — multi-segment
(2026-08-14), multi-document BinHex (2026-08-15) and Now Compress
(2026-08-16), whose last item was closed by the decoder inside the archive
itself. A section that empties is the point of the file. So is a Part 1 entry
that turns out to be a research failure rather than a boundary: Alysis
SuperDisk! sat under *"rule #1 forbids inventing a format"* until 2026-08-20,
when the reference turned up inside the corpus's own fixtures (BLOCKERS.md,
*Withdrawn claims*).

---

# Part 1 — Out of scope for v1

**Decided, not open.** Everything here is a deliberate boundary or a limit of
the evidence; none of it is work waiting to be done. The brief HAS grown three
times — multi-segment archives (M11), DiskDoubler and Now Compress (M12), and
`.arc` + uuencode (M13) were all listed as out of scope until the maintainer
asked for them — so "out of scope" means *today's* answer, not a refusal.

## Out by the brief

| what | status | why it stays out |
|---|---|---|
| Compression | not implemented | this is an extractor |
| StuffIt X (`.sitx`) | **detect-only** | out by the brief |
| Encrypted archives | **detected and reported** | out by the brief; PackIt PMa5/6 resync rather than fail |
| Disk images (Disk Copy 4.2) | **detect-only**, with a real probe | out by the brief — the probe matches a synthetic 800K GCR image and a real one, 0 false positives |
| LZH / LHA extraction | **detect-only**, tested rather than asserted (DECISIONS.md 2026-08-14) | the corpus contains **no `.lzh` at all** — Macintosh software was not distributed that way — and Compact Pro's LZH is a different algorithm from LHA's, so it is ~550 new lines for nothing the corpus can grade |
| Zip64 spanned sets | `unc_zipseg_describe` answers `UNC_ERR_UNSUPPORTED`, cleanly | an EOCD with disk number `0xFFFF` defers to a locator nothing here parses. Zip64 postdates every machine this project targets by a decade and a set that needs it is 2 GB+; refusing it cleanly is the right answer, not a missing feature (2026-08-14) |
| Compact Pro archive comments | read, CRC'd, discarded | Expander 4.0.2 writes them out beside the extracted items; a comment is not a file and the sink writes files. Recorded so the difference is a decision rather than an oversight |

Everything detect-only is **named** by `unc_sniff`, so a UI can tell the user
what the file is and extraction returns cleanly unsupported.

## Out because rule #1 forbids inventing a format

These are limits of the evidence, not of effort. Rule #1: magic numbers and
layouts come from a reference implementation or a spec, never from memory.

- **AppleLink `.pkg` and StuffIt SpaceSaver.** Neither has a reference
  implementation or a published layout anywhere reachable. Searched
  2026-08-15: the only AppleLink format with documented internals is the
  Apple II `.acu` (CiderPress2's format notes, magic `fZink`), which that page
  explicitly distinguishes from the Macintosh Package format; SpaceSaver has
  no specification, no open implementation, and Aladdin's own later Expanders
  dropped it. Neither can even be **sniffed** without inventing a magic
  number, so a user gets *unknown* rather than a name. **What would change
  it:** a specimen plus the original application, derived under Mini vMac the
  way Compact Pro's segment layout and Now Compress's block shapes were — or
  one published description. **A SELF-EXTRACTING specimen would settle it on
  its own**, which is what the SuperDisk! withdrawal cost this project four
  documents to learn (BLOCKERS.md); neither has one here, or a specimen of
  any kind.
- **DiskDoubler methods 2, 3, 4 and 5, ARC 0x0a/0x0b, and SuperDisk! methods
  10, 13 and 20.** No corpus fixture uses any of them and nothing reachable
  writes them, so an implementation could not be graded — code no oracle can
  check is the same bargain LZH refuses. **Methods 1 and 7 were in this list
  until 2026-08-20 and are now implemented**: DiskDoubler 3.7 writes method 1
  from its own menu, and its distribution disk ships two method 7 files
  (BLOCKERS.md, *Withdrawn claims*). What is left of the list is earlier
  DiskDoubler work: 3.7's menu offers two software methods and neither is one
  of them, and no copy of 1.x or 2.x is reachable from here — Macintosh Garden
  has 3.7 and 4.x only, and the 1990 shareware "DiskDoubler .05" on funet
  writes MacCompress files (its INIT carries `ZIVM`/`LZIV` and none of the
  three DiskDoubler magics), so it predates the container entirely.
  **What would close it:** a copy of DiskDoubler 1.x or 2.x, or one file
  written by one. DiskDoubler Pro 4.1.1 does not help: its five menu
  entries are AD1, AD2, DD1, DD2 and DD3, which write methods 9, 6, and
  10 three ways — nine archives' worth of them in
  `ssokolow/diskdoubler-test-files`, and not one method between 2 and 5. The three
  SuperDisk! methods are cheaper still in one sense and no cheaper in the
  other: their 68k modules sit inside the corpus, named and complete
  (FORMATS.md ✧✧), so transcribing them needs no research at all — and there
  would still be nothing to check the result against, because SuperDisk!'s
  compressor does not survive here, only its expander.

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

## 1. DiskDoubler and SuperDisk!: what M12 and M14 left

- **A method 7 fork longer than one chunk has never been decoded.** The
  fork header counts its compressed chunks and gives each a 16-bit
  length; both specimens hold exactly one, and the codec reads the
  chunks as one continuous bit stream because that is what the
  reference does. A fork over ~64 KB would settle whether that is
  right. **What would close it:** a bigger method 7 file, which needs
  the Sigma Designs card DiskDoubler 3.x wrote them with — no emulator
  here has one.
- **11 forks across 2 fixtures are adjudicated by neither oracle**
  (`derived-Terrainman_2.0__.sea`, `derived-LHA_Expander_1.0.3.sea`).
  `unar` fails on them and `macunpack` — built with its own DiskDoubler
  support — fails too. We extract them; nobody grades them.
- **No `SPLT` set has ever been joined on a Mac.** The application
  compiles with the scheme (`ci.sh` variant 4) and shares the joiner,
  the volume source and the "locate part N" dialog with the four
  schemes that HAVE run there; two pieces are its own, the filename
  rule and the joined file's name. **What would close it:**
  `tools/vmac/run.py` on a set cut from a fixture — the same shape as
  the segmented-set runs of 2026-08-09 (FORMATS.md, "Segmented sets on
  a real emulated Mac Plus").
- **The 4 bytes at `+4` of a `SPLT` header are unidentified.** Equal
  across the parts of a set, different between sets, so they serve as
  the identity and the joiner needs nothing more. Three sets are known
  and no checksum accounts for them: not of the payload, of either
  fork, or of the file (sum, rotating sum, CRC-16/ARC, CCITT and XMODEM,
  over data, resource and both, all tested 2026-08-21). Two of the three
  sets have IDENTICAL data forks and different values, so whatever it
  is, it is not a function of the data fork alone. **What would close
  it:** DiskDoubler splitting files of known size and known time under
  emulation — the same file twice would separate a content hash from a
  clock, and `tools/vmac/diskdoubler.py --probe-split` is where that
  starts.
- **A `DDA2` stored entry with a resource fork has never been seen.**
  `+87` is read as that fork's XOR checksum by position, next to the
  data fork's at `+86`, which is measured on ten forks. Both stored
  files in every set are fork-less (a JPEG and a PNG), so `+87` has only
  ever been 0 — and the record's two dates have only ever been equal, so
  which of `+54` and `+58` is the creation is assigned rather than
  measured (DECISIONS.md 2026-08-21). **What would close both:** one
  incompressible file with a resource fork, compressed by DiskDoubler
  Pro.
- **Two of the four Mac tiers have not re-run since M12, M13 or M14.** The
  System 6 tiers have (63/63 at 4 MB and at 1 MB, 2026-08-15; plus both
  SuperDisk! payloads on both, 2026-08-20). **System 7.0.1 and
  Mac OS 9.2 have not**: System 7 stands at 55/55 on the pre-M12 sample
  (2026-08-08), so the seven fixtures M12 added and the two M13 added have
  never run there, and
  the OS 9 sample still records DiskDoubler as a refusal, which is what
  it was when that tier last ran. FORMATS.md marks those rows pre-M12.
  **What would close it:** `run.py --system Sys7.img --list
  tools/vmac/sample.txt` (Mini vMac, cheap) and an OS 9 sweep, which
  costs a full PowerPC boot per fixture.
- **The SuperDisk! archives are in no `--list` file, on any tier**, because
  they are payloads inside envelopes and `run.py` graded only against a
  manifest, which the format has none of. They were replayed by hand on both
  System 6 tiers (FORMATS.md, "SuperDisk! on the Mac"), and a sweep would
  silently leave them out. The grading mode they wanted exists since
  2026-08-21 — `run.py --expect`, which takes the Linux aggregate for a file
  with no manifest, as the ArcMac specimens have also wanted since M13.
  **What would close it:** a sweep that includes them, and a `--list` file
  that names the payloads.

---

## 2. Cannot be closed in this environment

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

## 3. Known unknowns, not being chased

- **Why the pointer does not work under QEMU on Mac OS 9.** Measured to
  0.0000 effect across five mouse primitives; the mechanism behind that has no
  reproduction and is labelled a guess. The keyboard route works, so this costs
  nothing.
- **Names HFS+ permits that HFS does not.** Probably unreachable from this
  binary at all — the classic File Manager caps components at 31 characters on
  either filesystem — but that is unproven either way.

---

## 4. Untested code, named so it is not mistaken for tested

- **The interactive UI above System 6 is deliberate scope**, not a gap
  (2026-08-02). System 6 is the UI's target and it is driven end to end there.
  What that leaves unexercised: `ProgressPump()` branches on `gHasWNE`, and the
  cancel routes inside it — Cmd-., the Cancel button via `DialogSelect`, the
  dialog repainting — have only ever run on the `GetNextEvent` side. Mac OS 9
  runs the `WaitNextEvent` side, but only where nothing is cancelled. The
  engine and sink semantics of a cancel are covered separately: unit tests,
  both write paths through the qemu-m68k mock in `ci.sh`, and `UNC_AT_CANCEL`
  on-Mac at 4 MB and 1 MB.
- **SuperDisk! methods 1-6, 8 and 9 have never decoded anything.** Both corpus
  archives use one method each — 7 and 11, counted block by block — so the
  13-bit context (1-4), two of the four wide variants and Huffman-alone (9)
  are transcribed and compiled and nothing more. The Huffman decoder itself
  and the wide context ARE exercised, since method 7 is both. The unit test
  cannot help: it builds stored blocks, because writing coded ones would mean
  writing an encoder and grading this decoder against it. **What would change
  it:** an archive that uses one of them, or the `Cmpr` modules run under
  emulation as a second implementation — the same route the adjudication
  already takes, applied per method instead of per archive.
- **Files larger than the HFS 2 GB cap**, and the engine's 32-bit-only
  arithmetic against them.
- **MacRoman filename display and 8-bit characters above System 6.** The bytes
  are checked everywhere; how they *look* on 7 and 9 is not.

---

## 5. Remedies ruled out by measurement

- **Do not retry, on Mac heap pressure.** Both were measured while
  StuffIt 5 / Arsenic was still short of the 1 MB floor, and both are dead
  ends: `MaxMem()` before a retry (compaction may not move a `NewPtr`), and
  relocatable blocks moved high with `MoveHHi` — it demonstrably works,
  205,828 → 803,634, and changed `MaxBlock` at the refusal by under 500 B,
  because the stranded heap was never about where the live blocks sat. Cited
  from `src/sit_arsenic.c` and `mac/unclassic_mac.c`.

Everything else that used to sit in this section is a scope decision and is
now Part 1.

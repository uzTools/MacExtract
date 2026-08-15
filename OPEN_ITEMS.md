# OPEN_ITEMS.md — what is missing, as of 2026-08-14

A standing audit of the gaps: things not done, things done but not verified,
and things this repository asserts more confidently than the evidence supports.

**Not** BLOCKERS.md, which records investigations that went wrong and the
claims withdrawn from them. Nothing here stops the engine or the CLI, which are
byte-exact against the oracle across 797 fixtures in `./ci.sh`.

Each item says what would close it. Detail lives in one place per finding —
status in BLOCKERS.md, reasoning in DECISIONS.md, how to re-run in TESTING.md
or `tools/vmac/README.md`, what needs real hardware in MANUAL_TESTS.md,
results in FORMATS.md — and is cross-referenced from here rather than
repeated.

**Filing something here is a decision to stop looking at it, so it had better
be true.** Section 1 in particular: it held "eight fixtures are excluded as
oracle-undecidable or oracle-buggy" until 2026-08-08, when the item turned out
to be nine fixtures, closeable in an hour, and nothing to do with this
environment — it was a fork-naming flag of the oracle (DECISIONS.md,
BLOCKERS.md, 2026-08-08).

**Only open items live here.** A closed one moves out: the lesson to
DECISIONS.md, the withdrawn claim to BLOCKERS.md, the numbers to FORMATS.md.
Section 4 used to be *Multi-segment*, and on 2026-08-14 it emptied: all
four schemes join on Linux and on the Macintosh, and the last thing in it
— taking an envelope off each part — was built the same day. A section
that empties is the point of the file.

---

## 1. Cannot be closed in this environment

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

## 2. Known unknowns, not being chased

- **Why the pointer does not work under QEMU on Mac OS 9.** Measured to
  0.0000 effect across five mouse primitives; the mechanism behind that has no
  reproduction and is labelled a guess. The keyboard route works, so this costs
  nothing.
- **Names HFS+ permits that HFS does not.** Probably unreachable from this
  binary at all — the classic File Manager caps components at 31 characters on
  either filesystem — but that is unproven either way.

---

## 3. Untested code, named so it is not mistaken for tested

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

## 4. Deliberate gaps, and remedies ruled out by measurement

- **Zip64 spanned sets, out of scope as of 2026-08-14.** An
  end-of-central-directory record whose disk number is `0xFFFF` defers to
  the zip64 locator, which nothing here parses; `unc_zipseg_describe`
  answers `UNC_ERR_UNSUPPORTED`. It was ranked as a gap until somebody
  asked the obvious question: zip64 postdates every machine this project
  targets by a decade, a set that needs it is 2 GB+, and no archive of
  the era could be one. Refusing it cleanly is the right answer, not a
  missing feature.
- **Out of scope by the brief, and still out:** compression, StuffIt X
  (`.sitx`), encrypted archives, disk-image extraction, Now Compress, and
  LZH *extraction* — the optional half of M8, and the evidence for
  leaving it there is that **the corpus contains no `.lzh` at all**:
  Macintosh software was not distributed that way. It would be ~550 new
  lines, since Compact Pro's LZH is a different algorithm from LHA's.
  The detect-only claim itself is now tested rather than asserted
  (DECISIONS.md 2026-08-14). **Multi-segment archives are IN scope
  since 2026-08-08** and four schemes are implemented (StuffIt segments,
  Compact Pro segments, spanned zip, plain `.NNN` splits); the rest are
  the section above.
- **Out of scope, and added to the brief on 2026-08-15 rather than found
  in it:** `.arc`, uuencode (`.uu`), AppleLink packages (`.pkg`) and
  StuffIt SpaceSaver. They are here because the comparison with StuffIt
  Expander 4.0.2 (FORMATS.md) is what named them: each is a format its
  paid add-on expanded and we do not, and unlike the detect-only list
  above we do not sniff them either. None appears in this corpus.
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

---

## 5. Missing capability, with a reproduction

- **Multipart BinHex: several documents in one text file.** MEASURED
  2026-08-15. `cat a.hqx b.hqx > two.hqx`, and we list and extract the
  FIRST document only, exit 0 — no error, no hint that anything was left.
  `unar` does the same, so the oracle cannot see this and the differential
  suite never could have caught it (DECISIONS.md 2026-08-15). Expander
  4.0.2 claims the case outright and names comp.binaries.mac while doing
  it — FORMATS.md, "Compared with StuffIt Expander 4.0.2" — which is where
  most of this corpus came from.
  **What would close it:** on reaching a stream's end, resume scanning for
  another BinHex header and continue as further entries. Both references
  scan for that header line — `XADBinHexParser.m` and macutils
  `hexbin/hqx.c` — so the layout is transcribable rather than guessable,
  and `hexbin` is the oracle for grading it. It needs a fixture the corpus
  does not have; a synthesised one is only ground truth once `hexbin`
  adjudicates it.
- **What is NOT missing here, also measured the same day:** a single
  BinHex document CUT across files joins and extracts through to the
  archive inside, as long as the parts are named `NAME.hqx.001` /
  `.002` — the plain-split scheme takes it. A half named `NAME.hqx.1`
  reads as a whole document, lists an entry from the header's declared
  length, and then fails at extraction (`file is truncated`, exit 1)
  rather than writing a short file quietly.

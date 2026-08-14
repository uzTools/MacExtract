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

## 4. Multi-segment: what the four implemented schemes leave

StuffIt segments, spanned zip, plain `.NNN` splits and Compact Pro
segments extract end to end (M11), the last of them on the Linux CLI
only. These are the parts scoped out on purpose, ranked by what they
would cost.

- **Three of the four schemes are not wired into the Mac shell.**
  Engine and Linux CLI only, by decision on 2026-08-09, 2026-08-10 and
  2026-08-14. What each still needs:

  *Compact Pro* is the closest. Its parts are matched by header through
  `unc_segment_match`, which is what `SegPartOf` already calls, so a set
  opened at its FINAL segment would join today. What is missing is the
  other case: the count lives only in the last segment, so the shell
  needs the search the CLI does — describe each part found until one
  answers with a count. Untested on a Mac, and therefore claimed nowhere.

  *Spanned zip and `.NNN` splits* need a name-matching branch beside
  `SegPartOf`, since neither can be matched by content. This item used
  to add that the descriptor would have to carry a base filename "the
  engine deliberately has no concept of"; that was wrong, and it made
  the job look bigger than it is. The name is the HOST's already —
  `ExtractOne` is handed the name Standard File returned and passes it
  to `SegRemember` two lines after building the descriptor, which is
  the same place the Linux CLI gets its stem from (`zipfam_split`).

  *A split* needs one thing more — every part's LENGTH before extraction
  starts, since that is the only place the joined size comes from
  (DECISIONS.md 2026-08-10), which on a one-drive Mac is either a
  `PBHGetFInfo` per part on a hard disk or a decision to ask the user
  for all the disks up front. **The disk-swap cost that used to be the
  reason to wait is gone** (2026-08-09): every reader here hits the
  floor its archives allow — 6 opens with 1 backward crossing on a
  5-part zip set, 5/1 on a 4-segment Compact Pro one — so the shape a
  user would see is "insert the last disk, then disks 1 to N in order",
  which is what a PC did with these in the 1990s.

  Left over for all three: what the "locate part N" alert should say for
  a scheme where a part cannot be checked before it is used. The
  application carries the code regardless — its payload went 76,800 →
  78,208 B on 2026-08-09, 79,360 B on 2026-08-10 and 80,640 B on
  2026-08-14, which is noise against the floor target's ~700 KB of free
  heap but is the honest price of the engine being shared.
- **Parts inside envelopes: done for StuffIt, and only there**
  (2026-08-13). `Archive.sit.1.hqx` joins — the Linux CLI takes the
  envelope off each part before the join, and only when the set is
  short of one (DECISIONS.md). Two pieces of that are open. The Mac
  shell does not do it: like the two schemes above it needs the step
  added to `SegPartOf`, and unlike them it also needs somewhere to put
  a decoded part, which on the floor target is a temporary file on the
  output volume rather than the CLI's ~100 bytes of peek plus a whole
  decode. And a wrapped part of a spanned zip or a `.NNN` split is not
  looked for at all: those are placed by FILENAME, the filename of a
  wrapped part is the wrapper's, and no reference implementation says
  what that should look like — so it stays unbuilt until a real
  example says what the convention is, rather than being guessed.

---

## 5. Deliberate gaps, and remedies ruled out by measurement

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
  LZH *extraction* — LZH was the optional half of M8 and is detect-only
  (the LZH/LHA row of FORMATS.md). **Multi-segment archives are IN scope
  since 2026-08-08** and three schemes are implemented (StuffIt segments,
  spanned zip, plain `.NNN` splits); the rest are the section above.
- **Do not retry, on Mac heap pressure.** Both were measured while StuffIt 5 /
  Arsenic was still short of the 1 MB floor, and both are dead ends:
  `MaxMem()` before a retry (compaction may not move a `NewPtr`), and
  relocatable blocks moved high with `MoveHHi` (it demonstrably works,
  205,828 → 803,634, and changed `MaxBlock` at the refusal by under 500 B —
  the stranded heap was never about where the live blocks sat). Cited from
  `src/sit_arsenic.c` and `mac/unclassic_mac.c`.

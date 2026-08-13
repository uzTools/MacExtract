# OPEN_ITEMS.md — what is missing, as of 2026-08-13

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

## 4. Multi-segment: what the three implemented schemes leave

StuffIt segments, spanned zip and plain `.NNN` splits extract end to end
(M11). These are the parts scoped out on purpose, ranked by what they
would cost.

- **Spanned zip and `.NNN` splits are not wired into the Mac shell.**
  Engine and Linux CLI only, by decision on 2026-08-09 and 2026-08-10.
  One piece is missing and it serves both: the shell's part discovery
  (`SegPartOf`) matches a StuffIt header through `unc_segment_match`,
  where these two schemes can only be matched by filename. This item
  used to add that the descriptor would have to carry a base filename
  "the engine deliberately has no concept of"; that was wrong, and it
  made the job look bigger than it is. The name is the HOST's already —
  `ExtractOne` is handed the name Standard File returned and passes it
  to `SegRemember` two lines after building the descriptor, which is
  the same place the Linux CLI gets its stem from (`zipfam_split`).
  What is actually missing is a name-matching branch beside `SegPartOf`.
  A split needs one thing more — every part's LENGTH before extraction
  starts, since that is the only place the joined size comes from
  (DECISIONS.md 2026-08-10), which on a one-drive Mac is either a
  `PBHGetFInfo` per part on a hard disk or a decision to ask the user
  for all the disks up front. **The disk-swap cost that used to be the
  reason to wait is gone** (2026-08-09): the reader hits the floor its
  archives allow — 6 opens with 1 backward crossing on a 5-part set,
  14/2 on a 12-part one — so the shape a user would see is "insert the
  last disk, then disks 1 to N in order", which is what a PC did with
  these in the 1990s. What is left is the wiring above, plus deciding
  what the "locate part N" alert should say for a scheme where a part
  cannot be checked before it is used. The Mac application
  carries the code regardless — its payload went 76,800 → 78,208 B on
  2026-08-09 and 79,360 B on 2026-08-10, +2.5 KB it cannot yet reach —
  which is noise against the floor target's ~700 KB of free heap but is
  the honest price of the engine being shared.
- **Other segment schemes. Compact Pro segmented archives are the
  interesting one and the expensive one**, and what is missing is a
  SPECIMEN, not documentation. No reference implementation extracts one:
  XADMaster reads the archive volume byte and discards it
  (`/*int volume=*/`), records the per-entry one as metadata it never
  acts on, and its own format wiki marks all three of the fields
  involved — volume, cross-volume magic, per-entry volume — "meaning not
  entirely clear". `macunpack` stores its copy unused. Both sources are
  now fetched by `tools/fetch_references.sh` as
  `reference/notes/cpt_specs_theunarchiver.md` and
  `cpt_users_guide.txt`, the second being the author's own manual, which
  documents what the scheme PROMISES even though no one documents its
  bytes: at most 255 segments, each an ordinary Macintosh file; names
  and locations chosen freely, "since Compact Pro saves information
  inside the files to determine their proper ordering"; and the FINAL
  segment is the one you open. Measured here, 2026-08-13: the
  cross-volume magic is **distinct in all 68 corpus archives**, so it is
  a per-archive identifier rather than a constant — which is what a set
  identity looks like and matches what the manual says the files carry.
  On the project's own ranking rule that makes this scheme StuffIt-like
  (identity is content, not name) rather than zip-like, and it is
  therefore worth more than its position in this list suggests.
  No sample exists here — all 805 fixtures scanned for a Compact Pro
  signature with a volume byte other than 1, including files not named
  `.cpt`, since a middle segment has no index and would not sniff as one:
  zero hits — and nothing in the funet whole-index is named like a
  segment set. Generating one under Mini vMac with the copy of Compact
  Pro already in the corpus is the route, and it would answer what the
  documentation does not: whether every segment carries the 8-byte
  header, and whether an entry's offset is relative to its own segment
  or to the joined stream. The oracle would then be differential (same
  files, segmented vs not) with Compact Pro itself as a second opinion
  on the Mac.
- **Zip64 spanned sets are refused, not read.** An end-of-central-directory
  record whose disk number is `0xFFFF` defers to the zip64 locator,
  which nothing here parses; `unc_zipseg_describe` answers
  `UNC_ERR_UNSUPPORTED`. Out of reach of the floor target anyway (a
  2 GB+ archive), and no fixture exists.
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

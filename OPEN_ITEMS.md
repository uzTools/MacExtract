# OPEN_ITEMS.md — what is missing, as of 2026-08-10

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
  matches a StuffIt header, where these two schemes need a filename
  match, and the descriptor would have to carry a base filename the
  engine deliberately has no concept of (neither scheme stores one).
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
  interesting one and the expensive one**: the format documents a volume
  byte per archive and per entry, no reference implementation extracts
  them (`unar` and `macunpack` both read the byte and ignore it), and
  there is no sample in the corpus — so it needs a genuine segmented
  `.cpt` before a line of parser is written. Compact Pro itself is in
  the corpus and splits archives across floppies, so generating one
  under Mini vMac is a route; the oracle would then be differential
  (same files, segmented vs not).
- **Zip64 spanned sets are refused, not read.** An end-of-central-directory
  record whose disk number is `0xFFFF` defers to the zip64 locator,
  which nothing here parses; `unc_zipseg_describe` answers
  `UNC_ERR_UNSUPPORTED`. Out of reach of the floor target anyway (a
  2 GB+ archive), and no fixture exists.
- **Parts that are individually wrapped.** A real download is
  `Archive.sit.1.hqx`: each part BinHex- or MacBinary-encoded on its
  own, so the envelope has to come off before the join. Today the
  envelope recursion runs *after* the join, which is the other order.

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

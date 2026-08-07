# OPEN_ITEMS.md — what is missing, as of 2026-08-07

A standing audit of the gaps: things not done, things done but not verified,
and things this repository asserts more confidently than the evidence supports.

**Not** BLOCKERS.md, which records investigations that went wrong and the
claims withdrawn from them. Nothing here stops the engine or the CLI, which are
byte-exact against the oracle across 769 fixtures in `./ci.sh`.

Each item says what would close it. Detail lives in one place per finding —
status in BLOCKERS.md, reasoning in DECISIONS.md, how to re-run in
MANUAL_TESTS.md, results in FORMATS.md — and is cross-referenced from here
rather than repeated.

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
- **Eight fixtures are excluded as oracle-undecidable or oracle-buggy**
  (six StuffIt, two Compact Pro; see the M4 and M6 rows of PROGRESS.md). Not known
  failures — the oracle cannot adjudicate them.

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

## 4. Closed, kept only for the method

| was open | closed | why it is worth remembering |
|---|---|---|
| Cancel with partial output under streaming writes | 2026-08-01 | the mock's `--cancel` never called `sink_write`, so it tested only the "no fork was ever opened" path; now aborts mid-fork on both write paths |
| The `v0.1` tag was 10 commits behind | 2026-08-01 | **a tag freezes the documentation's errors along with its code**, and this repository's errors have all been in the documentation |
| Orphan emulators after a killed run | 2026-08-02 | `start_new_session=True` is deliberate, so a signal must be turned into a normal unwind; demonstrated by interrupting a live run, not assumed |
| "DECISIONS.md is truncated" | 2026-08-02 | it was not; the natural response — "restoring" the section — would have destroyed correct history. `git diff HEAD` answers it in seconds |
| A hypothesis filed under *harness lessons* | 2026-08-01 | filing a hypothesis as a lesson hides it: this one implied the shipped UI was broken and nobody looked. **This file is the place to look for others of the same shape** |
| The LZW table sized from `maxbits` rather than the input | 2026-08-03 | growth-on-demand and one-shot sizing look interchangeable and are not: copy-based growth has an `old + new` transient, so **where the buffer IS the allocation it can lose to doing nothing** (measured, 274,432 → 405,504 B). Bound it from the input instead. DECISIONS.md |
| StuffIt 5 / Arsenic incomplete at the 1 MB floor (42/44) | 2026-08-07 | the last four gains were all "allocate less of what the data does not use"; this one had to **reduce the requirement** instead, and the tell was that no placement or reserve tuning could close a 410 KB shortfall on a 760 KB machine. Also: **estimate the thing you are changing.** The prediction here was within 200 B on one fixture and 3.6% on the other because it estimated a single allocation inside one entry; the method 13 estimate a day earlier missed badly because it estimated an aggregate over a distribution. DECISIONS.md |
| "peak heap under a budget" read as a requirement | 2026-08-07 | a decoder with a time-for-memory dial spends whatever the cap allows, so its peak tracks the CAP, not its needs. Comparing such a peak against a predicted requirement compares two different quantities — **bisect the cap** for the requirement. This nearly made the sampled BWT look 2.3x worse than predicted when it was in fact accurate |

---

## 5. Capability gaps that are deliberate, but still gaps

- **StuffIt 5 / Arsenic on a 1 MB machine: CLOSED 2026-08-07, 44/44.** Kept
  here only as a pointer: all six sampled StuffIt 5 fixtures extract every
  entry byte-exact on a 1 MB Mac Plus, so this section no longer has an
  Arsenic capability gap. Results in FORMATS.md ("Floor target verification"),
  reasoning in DECISIONS.md 2026-08-07, method in the section 4 table above.

  Still **do not retry**, ruled out by measurement while this was open:
  `MaxMem()` before a retry (compaction may not move a `NewPtr`), and
  relocatable blocks moved high with `MoveHHi` (it demonstrably works,
  205,828 → 803,634, and changed `MaxBlock` at the refusal by under 500 B —
  the stranded heap was never about where the live blocks sat).

- **Timing: MEASURED 2026-08-02, and closed.** Eight
  fixtures across eight formats at authentic 1x, 8/8: boot ~10 s, every
  extraction under 5 s, plus the 278 KB StuffIt anchor at ~134 s (FORMATS.md,
  README). The earlier diagnosis that this host "cannot be trusted to run 1x"
  was wrong and is corrected — an idle machine measures fine. What remains is
  nothing outstanding: `macburger-helper.hqx`, written up three times as an
  anomaly, simply takes 150 s, and instrumenting the engine's byte counter
  (`-D UNC_AT_PROGRESS`) showed the rate is very non-uniform so every timeout
  chosen for it expired mid-run. **Timing is closed for every format sampled.**

  **Reopened for Arsenic on 2026-08-07, then measured the same day — but only
  once.** The 1x list samples StuffIt 5 with `derived-KeyGraphics.sit`,
  4,611 B, far too small to reach the sampled inverse BWT, so the fallback's
  cost on a 7 MHz 68000 was unmeasured. It now is, for one fixture:
  `derived-a2basic.dmg.sit` extracts in **537 s** on the fast path (4 MB) and
  **927 s** on the sampled path (1 MB) — 1.73x, on a 1 MB 1x emulator that had
  to be built for it (`build_mv mv-1M-1x 1M z`). FORMATS.md has the table.

  What is still open: **`derived-Library_ISBN_Barcoder.sit` has not been timed
  at 1x.** It is the sample's worst case at 641 KB of output and extrapolates
  to roughly an hour, which is an estimate. A run was started and abandoned
  rather than let it collide with a 3600 s timeout, because a timeout is a
  bound and would have been quotable as if it were a measurement. What would
  close it: `tools/vmac/run.py --emu mv-1M-1x --mem 1M --timeout 7200` on that
  fixture, one boot, and add the row to FORMATS.md. Nothing depends on it —
  correctness is already 44/44 — but the project's "do I wait one minute or
  twenty" answer currently rests on a single Arsenic data point.
- **Out of scope by the brief, and still out:** compression, StuffIt X
  (`.sitx`), encrypted archives, multi-segment archives, disk-image extraction,
  Now Compress, and LZH *extraction* — LZH was the optional half of M8 and is
  detect-only (the LZH/LHA row of FORMATS.md).

---

## 6. Loose ends

- **StuffIt method 1 (RLE90): the claim that no corpus fixture uses it was
  WRONG.** Measured 2026-08-01 by instrumenting the method byte:
  `derived-New_Python.sit` has one 470-byte method-1 resource fork, and the
  engine extracts that archive cleanly with every CRC-16 verified. It has no
  ORACLE coverage because `unar` fails on that same archive, so no manifest
  exists. Closing it properly still needs a method-1 archive `unar` can read.
- **StuffIt method 6, "fixed Huffman", is not implemented — and was never
  named.** `derived-INITLoader.sit` carries one 34,818-byte method-6 fork;
  the engine returns a clean per-entry "recognized but unsupported", which is
  correct behaviour, but no document mentioned the method existed. XADMaster
  does not implement it either (`XADStuffItParser.m:319`), so there is no
  oracle to check an implementation against and no second fixture to test one
  on. One fork in 344 StuffIt archives — worth naming, not obviously worth
  implementing.
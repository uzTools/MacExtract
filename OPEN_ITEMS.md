# OPEN_ITEMS.md — what is missing, as of 2026-08-03

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

---

## 5. Capability gaps that are deliberate, but still gaps

- **StuffIt 5 / Arsenic on a 1 MB machine: 4 of 6 sampled fixtures fully, the
  other 2 missing exactly one entry each** (2026-08-06, 42/44 on the sweep).
  The engine declines the entry it cannot afford and carries on, which is why
  `Library_ISBN` still delivers 33 of 34 files.

  **The contiguity half is CLOSED** (2026-08-06).
  `derived-Troi-ClipSave-Plug-in1.1.sit` passes. Its refused entry was never
  short of memory — it fit the budget with 12 KB to spare and failed on a
  498,548 B request against a 468,126 B largest run. The stranded ~126 KB was
  the Arsenic block's own doubling trail: growing 8K→16K→32K→64K→128K frees
  each step, and a geometric trail can never satisfy the step after it, so
  8+16+32+64 KB of holes sat under the final block (122,880 B, against 125,614 B
  measured). Sizing the first allocation from the entry —
  `min(outlen, blocksize)` — removes it. DECISIONS.md 2026-08-06.

  Ruled out along the way, by measurement, so **do not retry**: `MaxMem()`
  before a retry (compaction may not move a `NewPtr`); and relocatable blocks
  moved high — `MoveHHi` demonstrably works, 205,828 → 803,634, and changed
  `MaxBlock` at the refusal by under 500 B, because the trail was never about
  where the live blocks sat.

  **What remains is the genuine-shortage half, and only a cheaper inverse BWT
  reaches it.** Against the 678,392 B budget a 1 MB machine gives the engine:

  | fixture | fill | 4x transform | needs | vs budget |
  |---|---|---|---|---|
  | `a2basic.dmg` | 197,515 | 790,060 | 1,088,588 | +410,196 |
  | `Library_ISBN` | 323,384 | 1,293,536 | 1,854,208 | +1,175,816 |

  `a2basic` needs 1.06 MB on a machine whose entire free heap is 760,312 B, so
  no allocation placement, reserve tuning or defragmentation can reach it. Only
  reducing the REQUIREMENT can.

  **The change that would: stop building the 4-bytes-per-byte inverse-BWT
  vector.** It is the dominant term in both rows. `ars_inverse_bwt` is 17
  self-contained lines building the standard T vector; a sampled-rank walk
  keeping a checkpoint every `s` positions needs `fill/16` at `s`=64 instead of
  `fill*4`:

  | fixture | needs now | with sampled ranks (estimate) |
  |---|---|---|
  | `a2basic.dmg` | 1,088,588 | ~245,699 |
  | `Library_ISBN` | 1,854,208 | ~379,435 |

  Both land inside the budget, and both under 400 KB — which would also move
  the "11 of 31 fixtures extract fully under a 400 KB budget" figure in the †
  footnote of FORMATS.md.

  Cost, and the main risk: **time, and it is unmeasured.** Each output byte
  needs a rank query costing up to `s` steps — ~21M inner iterations for
  `Library_ISBN` at `s`=64, against the repo's existing 134 s benchmark for a
  278 KB StuffIt. `s` is the dial. It can also be made adaptive — today's fast
  path when the budget affords `fill*4`, the sampled path when it does not — so
  a 4 MB machine pays nothing. Correctness is unusually cheap to establish: it
  is engine-side and portable, so the 769-fixture suite and the 31 StuffIt 5
  fixtures adjudicate it entirely on Linux, with no emulator run needed until
  the end.

  Ruled out by the same arithmetic: trimming capacity to the exact fill leaves
  `a2basic` 345,567 B over and `Library_ISBN` 974,912 B over; shrinking the
  80 KB reserve reaches neither.

- **Timing: MEASURED 2026-08-02, and closed.** Eight
  fixtures across eight formats at authentic 1x, 8/8: boot ~10 s, every
  extraction under 5 s, plus the 278 KB StuffIt anchor at ~134 s (FORMATS.md,
  README). The earlier diagnosis that this host "cannot be trusted to run 1x"
  was wrong and is corrected — an idle machine measures fine. What remains is
  nothing outstanding: `macburger-helper.hqx`, written up three times as an
  anomaly, simply takes 150 s, and instrumenting the engine's byte counter
  (`-D UNC_AT_PROGRESS`) showed the rate is very non-uniform so every timeout
  chosen for it expired mid-run. **Timing is closed for every format sampled.**
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
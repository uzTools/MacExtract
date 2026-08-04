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

- **StuffIt 5 / Arsenic on a 1 MB machine: 3 of 6 sampled fixtures fully, the
  other 3 missing exactly one entry each.** An entry needs its block plus four
  bytes of transform vector per byte the block holds, so an entry whose block
  genuinely fills 512 KB needs ~2.5 MB and a 1 MB machine cannot give it. The
  engine declines that entry and carries on, which is the designed behaviour.

  **Closed as far as it can be** (2026-08-03). Two changes took the sample from
  39/44 to 41/44, both about not paying for memory the data does not use: the
  shell no longer reads the whole archive into RAM before the engine gets a
  budget, and the Arsenic block is grown to what it actually holds rather than
  allocated at its declared 512 KB. `derived-RWAsm_Folder.sit` went from
  595.7 KB to 163.2 KB for the same 38 byte-exact entries.

  **Not closed, and the reason it was thought closed was wrong** (corrected
  2026-08-03). This item used to say the three entries "each really do fill a
  512 KB block", needing 512 KB + 2 MB against ~700 KB, and that closing them
  would take a fundamentally different inverse BWT. Direct instrumentation says
  none of the three fills a 512 KB block — the largest holds 323,384 B and
  `derived-Troi-ClipSave-Plug-in1.1.sit` holds **124,637 B**, so its refused
  entry needs about **650 KB, not 2.5 MB**. See *Withdrawn claims* in
  BLOCKERS.md for the measurements and what the error cost.

  What is actually left, ranked by what the peak model
  (`~35 KB parser + capacity + 4 x fill`) says is dominant:

  1. **The 4x transform vector** — 487 KB, 772 KB and 1,263 KB for the three.
     The only remaining term big enough to matter, and the only one that needs
     a different inverse BWT to shrink.
  2. **Capacity is never trimmed to the fill.** Doubling stops at the first
     power of two that fits, so `derived-Library_ISBN_Barcoder.sit` holds
     323 KB in a 512 KB block — 196 KB dead, for free, no algorithm change.
  3. **Why `Troi-ClipSave` refuses at all — MEASURED 2026-08-04, and it is
     not a shortage.** `-D UNC_AT_BUDGET` reports what the shell allowed as
     well as what the engine used:

     | | bytes |
     |---|---|
     | free heap at start (`FreeMem`) | 760,312 |
     | budget given to the engine (free − 80 KB reserve) | 678,392 |
     | the refused request (transform vector, 4 × 124,637) | 498,548 |
     | **`MaxBlock()` at that moment** | **468,126** |

     The budget said yes with 678 KB to spare; **`NewPtr` itself returned
     NULL**, short of a contiguous run by ~30 KB. So this is a
     **fragmentation/contiguity failure in the shell**, not a memory shortage
     in the engine, and the thing to fix is on the Mac side rather than in the
     inverse BWT.

     **Two remedies are ruled out by measurement, not by argument**, and the
     second rules out a whole family:

     | tried | result | `MaxBlock` at the refusal |
     |---|---|---|
     | baseline (`NewPtr`) | 12/13 | 468,126 |
     | retry after `MaxMem()` | 12/13 | — |
     | `NewHandle` + `MoveHHi` + `HLock` | 12/13 | **468,008** |

     `MaxMem()` cannot help because compaction may not move a `NewPtr`. The
     obvious answer to that — make the engine's blocks relocatable and stack
     them against the top of the heap — **also changes nothing**: `MaxBlock`
     moved by 118 bytes, in the wrong direction. Implemented, tested on the
     Mac, and reverted rather than kept as an unproven behaviour change.

     So **the fragmentation is not caused by where the engine's own blocks
     sit**, which is what both remedies assumed, and the next attempt should
     establish what actually holds the middle of the heap before proposing a
     fix. Whether the ~112 KB gap between free heap and `MaxBlock` is the
     shell's own allocations, the System heap, or something else is
     unmeasured — `-D UNC_AT_BUDGET` reports `MaxBlock` at one moment only,
     and a heap walk would say more.

     Still untried, and now the only candidate that does not depend on the
     disproved assumption: trim the Arsenic capacity to the exact fill
     (item 2). That is 6,435 B here against a ~30 KB shortfall, so it cannot
     close this alone.
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
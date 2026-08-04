# CLAUDE.md — standing instructions for **unclassic**

*An open-source universal unarchiver for Classic Mac OS (System 6 → Mac OS 9).*

## Mission

1. **`libunclassic`** — a portable, dependency-free C99 extraction engine for classic Macintosh archive and encoding formats, plus a Linux CLI (`unclassic`).
2. **A Retro68 Toolbox application** wrapping the same engine. Floor target: **System 6.0.x, 68000, 1 MB RAM**; the same binary must run unchanged through Mac OS 9.

The engine is the product. The Mac app is a thin shell.

## Current state — read before working

M0–M10 are **DONE**. The engine passes a 769-fixture differential suite against `unar`, and the Mac shell extracts byte-exact on a real System 6.0.8 Mac Plus under Mini vMac (44/44 sampled fixtures at 4 MB, 41/44 at the 1 MB floor, the remainder being documented StuffIt 5 memory-budget refusals).

It runs on all three systems the project claims: **System 6.0.8 and System 7.0.1** under Mini vMac (a true 68000), and **Mac OS 9.2** under QEMU PowerPC through the 68LC040 emulator, where 13/13 of a format sample is byte-exact, extraction onto **HFS+** is verified, and the `SIZE` partition is honoured by the Process Manager.

**System 6 is the target for the interactive UI.** It is driven end to end there — SFGetFile, progress dialog, Cancel, Cmd-., partial-output cleanup, result alert, launch by double-click. Above System 6 the UI is deliberate scope, not an open item: do not spend runs on how it looks or behaves on 7 or 9. The paths those tiers exist for are tested directly instead, without a Finder.

**Do not re-plan or re-run completed milestones.** The authoritative status lives in:

- `PROGRESS.md` — milestone table
- `FORMATS.md` — format × status × peak RAM matrix, plus the per-fixture results for every tier: Mini vMac 4 MB and 1 MB, System 7, and Mac OS 9 (including HFS+)
- `BLOCKERS.md` — status first (no open blockers), then what is true and
  load-bearing, then **Withdrawn claims**: nine assertions this file used to
  make, each with what disproved it and what it cost. They are kept on
  purpose — twice a live claim has been re-tested because it sat beside an
  already-withdrawn one, and one of those was worth 39/44 → 40/44 at the
  floor target. Do not delete them.
- `DECISIONS.md` — every non-obvious engineering decision, oldest first
- `OPEN_ITEMS.md` — what is still missing, ranked, with what would close each
- `TESTING.md`, `MANUAL_TESTS.md`, `tools/vmac/README.md` — how to re-run the harnesses

Read them at the start of every session. Where these files disagree with each other, treat it as a bug to fix, not a fact to choose from.

## Where to start (handoff, 2026-08-04)

The repository is on GitHub as a **private** repo, `main`, tagged through
`v0.4`. Working tree clean, `./ci.sh` green, nothing in flight.

**The next task is StuffIt 5 / Arsenic at the 1 MB floor, and it is open
again because the reason it was closed turned out to be false.** OPEN_ITEMS.md
section 5 said the three refused entries each fill a 512 KB block and so need
~2.5 MB against ~700 KB — "a real design change". Measured on 2026-08-03: none
of them fills a 512 KB block, and `derived-Troi-ClipSave-Plug-in1.1.sit` holds
124,637 B, so its refused entry needs about **650 KB against ~700 KB free**.
Read the corrected section 5 for the ranked remainder, BLOCKERS.md
*Withdrawn claims* for the measurements, and FORMATS.md for the per-fixture
table.

Item 3 there is now measured, and it moves the whole problem: the refusal is
**`NewPtr` failing for want of a CONTIGUOUS run**, not the budget saying no.
At the 1 MB floor the shell had 678 KB of budget left and `MaxBlock()` was
468,126 B against a 498,564 B request — short by ~30 KB. **So the remaining
work is on the Mac side, not in the inverse BWT.**

Measured at the refusal instant: `FreeMem()` 593,740 against `MaxBlock()`
468,126, so **125,614 B is lost to fragmentation** and the request would fit
an unfragmented heap with ~95 KB to spare. The engine held only 167,494 B, and
that plus the free heap accounts for the whole 760,310 B — so the engine's own
blocks are the only plausible thing splitting it.

Which makes the one remedy already tried genuinely odd, and it is where to
pick up: `NewHandle` + `MoveHHi` + `HLock` should have stacked those blocks
clear and instead moved `MaxBlock` by 118 bytes. It was implemented, run on
the Mac and reverted (30a8c10 — recoverable from git). **Do not re-attempt it
blind; first check whether `MoveHHi` moves anything at all here**, with a
`MaxBlock` either side of the call. `MaxMem()` before a retry is separately
ruled out — compaction may not move a `NewPtr`. `-D UNC_AT_BUDGET` is the
probe; MANUAL_TESTS.md says how to read it.

The other lead worth having, not yet attempted: **the StuffIt method 13 LZSS
window is a 64 KB format constant, but the reachable window is bounded by the
entry's uncompressed size**, which the header already passes in as `outlen`.
175 of 225 StuffIt fixtures sit at exactly that window's peak (76,944 B —
median and p90 both equal the max), and about two thirds of them have their
largest fork under 64 KB. Note the trap: back-references past what has been
produced currently read zero-filled window bytes, so shrinking the window
changes behaviour on malformed streams. Establish that failure mode before
believing a green suite.

Everything else open is either impossible in this environment (real 68k or
PowerPC silicon), the maintainer's to do (the Retro68 report), deliberate
scope, or blocked on a fixture the oracle can read.

**The one habit that produced everything valuable this week.** Nearly every
real gain came from re-testing a claim the repository was already making,
rather than from new features:

- Two claims from the M10 "confounded period" turned out to be false and were
  each costing something concrete — one forced the whole archive into RAM
  (39/44 → 40/44 at the floor target when removed), the other forced
  verification through a channel that cannot see filenames (which is how a
  real gzip/.Z naming bug survived for weeks).
- The Arsenic block was allocated at its DECLARED 512 KB rather than what it
  holds (40/44 → 41/44, and `derived-RWAsm_Folder.sit` went 595.7 KB → 163.2 KB
  for the same output).
- The LZW table was allocated at its DECLARED `maxbits` ceiling — found on
  2026-08-03 purely by looking for the Arsenic mistake a second time, and the
  matrix pointed straight at it: `.Z` was the one peak that did not vary with
  its input at all. A flat 268 KB became 15–219 KB, 50 fixtures improved, none
  regressed.
- "The three refused Arsenic entries each fill a 512 KB block" — the stated
  reason the last capability gap was unclosable, and false. One of them holds
  124,637 B. Found the same day, by the same reflex.

So: **when something looks like a hard floor, check whether the number you are
budgeting for is a number the data actually needs.** And when a claim has no
reproduction, treat its neighbours as suspect too — that is literally how the
last two were found. A constant in the peak-RAM matrix is the tell: data-driven
allocations vary with their input, so one that does not is usually a declared
ceiling nobody questioned.

**Read the status files against each other, not just in turn.** The 512 KB
claim was disproved by a line already in this repository: DECISIONS.md said
that fixture's blocks hold "~316 KB" while OPEN_ITEMS.md said they fill 512 KB,
and the two sat a file apart for a day. The rule above — *where these files
disagree, treat it as a bug* — is not housekeeping; a contradiction between
two status files is a disproof nobody has collected yet, and it is the cheapest
finding available. The same pass turned up README.md quoting a 1.8 MB corpus
maximum where the measured figure is 2.53 MB.

And note how the false claim was built: 512 KB was **true of the corpus** —
two fixtures do reach 524,257 B — and got applied to three fixtures it did not
describe. A true number about the worst case is not a number about the case in
front of you.

**The same fix does not always work twice, though.** Growth-on-demand rescued
the Arsenic block and made the LZW table *worse* than doing nothing, because
copy-based growth has an `old + new` transient and there the table IS the whole
allocation. Two problems with the same shape can want opposite fixes; measure
the second one rather than porting the first one's answer. (DECISIONS.md,
2026-08-03.)

**Traps this environment sets, all of which cost real time here:**

- A test that passes may not be testing anything. The cursor experiment
  "passed" twice while the pointer was outside the emulator window, and again
  while the drag ran between grid rows. Establish that a test can fail before
  believing that it passed.
- `pgrep -f "some command"` matches the watching shell itself, so an
  `until ! pgrep ...` loop never exits. Use `kill -0 <captured pid>`.
- The Mac OS 9 pointer does not work at all; drive that guest from the
  keyboard. Mini vMac's mouse is fine.
- An emulator run is minutes; do not poll it every few seconds, and do not
  read a timeout as a measurement of anything.

## Rules

- **Never invent format details.** Magic numbers, header layouts and algorithm parameters come from a reference implementation or spec, with a `/* Source: ... */` comment. Never guess from memory. `reference/` is read-only and never modified; `tools/fetch_references.sh` repopulates it.
- **A root cause that has never been reduced to a minimal reproduction is a hypothesis, not a finding.** Label it as such in the docs, and build the repro before acting on it or reporting it upstream. This rule was learned the hard way — see the withdrawn `HOpen` attribution in `BLOCKERS.md`.
- **Never weaken a test to make it pass.** CRC mismatches are per-entry errors, not skips.
- **When adding a harness, write down what it CANNOT see.** The on-screen result grid carries a file count and summed CRCs, so it could never fail on a filename — and a real defect in the gzip/.Z fallback name survived in the corpus for weeks because nothing recorded that blind spot. An aggregate check cannot fail on a property it never aggregates.
- **68000 discipline** (non-negotiable — it is what made the port compile and run first try): byte-wise big-endian reads only, zero unaligned dereferences; no recursion, call depth ≤ 4 KB; 32-bit arithmetic in hot paths; no libc in the engine — all I/O, allocation and progress via caller callbacks; no global mutable state; allocation failure is a per-entry error, never per-archive; progress callback every 8–16 KB with clean abort.
- **`./ci.sh` green before every commit.** Small, focused commits. Code, comments and docs in English.
- **LGPL-2.1-or-later**, forced by transcribing XADMaster; keep `NOTICE` accurate.
- Fixture archives are copyrighted and never committed — only `fixtures/SOURCES.md` and the manifests. Same rule for the Mac ROM and System image under `tools/vmac/`.
- Work autonomously through a task list; log non-obvious decisions in `DECISIONS.md`; if something cannot be made to pass after genuine effort, write it up in `BLOCKERS.md` and move on rather than stalling.

## Writing things down

The docs were restructured on 2026-08-03 after growing to ~3,500 lines with
most findings written up three or four times. Keep them from getting back
there:

- **Status first.** Every status file opens with the current state — tallies, what works, what is open — readable in a minute. History goes below that line, never above it.
- **One home per finding.** Status → `BLOCKERS.md`. Reasoning and transferable lessons → `DECISIONS.md`. How to re-run → `MANUAL_TESTS.md`. Numbers and per-fixture tables → `FORMATS.md`. Gaps → `OPEN_ITEMS.md`. Cross-reference; do not repeat. A finding written in two files disagrees with itself within a week — which this repository treats as a bug, so do not create the opportunity.
- **A finding is claim, evidence, consequence.** Three lines. Expand only where the *reasoning* is the part worth transferring.
- **Correct figures in place.** Change the number where it lives and note the correction once. Never add a section that supersedes an earlier section: that is how one file came to state three different boot times, all of them presented as fact.
- **Withdrawn claims are collected, not interleaved**, and each records what it COST. That is what separates a claim that was merely wrong from one that displaced a capability — and the cost line is what makes the next one worth re-testing.
- **Label every claim: measured, hypothesis, or withdrawn.** An unlabelled claim is read as measured. This is the documentation half of the reproduction rule above.
- **Closed items get a table row, not an essay.** Keep the method if it transfers to the next problem; drop the narrative.
- **No plans in status docs.** "The next attempt is one run, not three" is dead weight the moment it is done. Plans belong in the conversation or a commit message.
- **Never cite `FILE.md:NN`.** Line numbers drift silently and are then wrong without anyone noticing. Cite the section or table row by name.

## Out of scope (v1)

Compression (extraction only), StuffIt X (`.sitx`), encrypted archives, multi-segment archives, disk images, DiskDoubler, Now Compress, LZH/LHA. These are **detect-only**: `unc_sniff` names them — including Disk Copy 4.2, whose probe is now real — so a UI can tell the user what the file is, and extraction returns cleanly unsupported.

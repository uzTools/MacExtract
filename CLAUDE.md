# CLAUDE.md — standing instructions for **unclassic**

*An open-source universal unarchiver for Classic Mac OS (System 6 → Mac OS 9).*

## Mission

1. **`libunclassic`** — a portable, dependency-free C99 extraction engine for classic Macintosh archive and encoding formats, plus a Linux CLI (`unclassic`).
2. **A Retro68 Toolbox application** wrapping the same engine. Floor target: **System 6.0.x, 68000, 1 MB RAM**; the same binary must run unchanged through Mac OS 9.

The engine is the product. The Mac app is a thin shell.

## Current state — read before working

M0–M10 are **DONE**. The engine passes a 769-fixture differential suite against `unar`, and the Mac shell extracts byte-exact on a real System 6.0.8 Mac Plus under Mini vMac (44/44 sampled fixtures at 4 MB, 40/44 at the 1 MB floor, the remainder being documented StuffIt 5 memory-budget refusals).

It runs on all three systems the project claims: **System 6.0.8 and System 7.0.1** under Mini vMac (a true 68000), and **Mac OS 9.2** under QEMU PowerPC through the 68LC040 emulator, where 13/13 of a format sample is byte-exact, extraction onto **HFS+** is verified, and the `SIZE` partition is honoured by the Process Manager.

**System 6 is the target for the interactive UI.** It is driven end to end there — SFGetFile, progress dialog, Cancel, Cmd-., partial-output cleanup, result alert, launch by double-click. Above System 6 the UI is deliberate scope, not an open item: do not spend runs on how it looks or behaves on 7 or 9. The paths those tiers exist for are tested directly instead, without a Finder.

**Do not re-plan or re-run completed milestones.** The authoritative status lives in:

- `PROGRESS.md` — milestone table
- `FORMATS.md` — format × status × peak RAM matrix, plus the per-fixture results for every tier: Mini vMac 4 MB and 1 MB, System 7, and Mac OS 9 (including HFS+)
- `BLOCKERS.md` — status first (no open blockers), then what is true and
  load-bearing, then **Withdrawn claims**: seven assertions this file used to
  make, each with what disproved it and what it cost. They are kept on
  purpose — twice a live claim has been re-tested because it sat beside an
  already-withdrawn one, and one of those was worth 39/44 → 40/44 at the
  floor target. Do not delete them.
- `DECISIONS.md` — every non-obvious engineering decision, oldest first
- `OPEN_ITEMS.md` — what is still missing, ranked, with what would close each
- `TESTING.md`, `MANUAL_TESTS.md`, `tools/vmac/README.md` — how to re-run the harnesses

Read them at the start of every session. Where these files disagree with each other, treat it as a bug to fix, not a fact to choose from.

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

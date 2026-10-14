# CLAUDE.md — standing instructions for **MacExtract**

*An open-source universal unarchiver for Classic Mac OS (System 6 → Mac OS 9).*

## Mission

1. **`libmacextract`** — a portable, dependency-free C99 extraction engine for classic Macintosh archive and encoding formats, plus a Linux CLI (`macextract`).
2. **A Retro68 Toolbox application** wrapping the same engine. Floor target: **System 3.0, 68000, 1 MB RAM** (a January 1986 Macintosh Plus); it also runs in **512 KB**, refusing the heaviest archives per entry, and the same binary runs unchanged through Mac OS 9. Its decoders ship as **sixteen `'OVLY'` images** read at launch and released once the archive's format is known (FORMATS.md, *Overlays*).

The engine is the product. The Mac app is a thin shell.

## Where things stand

**M0–M67 are DONE and nothing is in flight.** Every Macintosh archive family
in FORMATS.md's table extracts; the rest of that table is named-only or
detect-only by decision. The engine passes a **964-fixture** differential suite
against `unar` and, where `unar` fails, `macunpack`, plus 9,640 robustness variants. The Macintosh application extracts byte-exact on every
emulated tier from System 3.0 at 1 MB to Mac OS 9.2; the tallies are
BLOCKERS.md's (*Status*). The interactive UI is driven end to end on System
3.0 and System 6; above those it is deliberate scope, not an open item.

**Do not re-plan or re-run completed milestones.** The authoritative status is:

| file | holds | read it |
|---|---|---|
| `PROGRESS.md` | what each milestone delivered, one line each | at session start |
| `OPEN_ITEMS.md` | **what is out of scope** (part 1), then what is still missing and what would close each (part 2) | at session start |
| `BLOCKERS.md` | the tier results and what is load-bearing (its first two sections), then **every claim this project has withdrawn**, with what it cost | first two sections at session start; the archive when re-testing a claim |
| `FORMATS.md` | format × status × peak RAM, and every per-fixture table | for a number |
| `DECISIONS.md` | why anything is the way it is, oldest first, with a Contents index | via the index, for one entry |
| `TESTING.md` | how each suite works and what it cannot see | before changing a suite |
| `tools/vmac/README.md` | how to run the emulator harnesses and probes | before booting anything |
| `MANUAL_TESTS.md` | what only somebody outside this machine can do — hardware, a copy of the software, an account to post from | when something needs one of those |

That session-start reading is **~10.7k tokens** (PROGRESS 4.2k,
OPEN_ITEMS 4.4k, BLOCKERS' first two sections 2.1k); BLOCKERS'
withdrawn-claims archive is another **~75.4k** and is reference, not
orientation. All five are ESTIMATES (bytes ÷ 3.93, ±5 %, 2026-10-14; no
tokenizer is installed). `tools/check_docs.py` only fails at 25 % drift, and
every one of them has gone stale before, so **re-measure them whenever you
touch these files.** What makes them grow is table cells turning into
essays: a row states the claim, the number and the citation; the reasoning
is DECISIONS.md's.

**Scope is not stated in this file.** It is OPEN_ITEMS.md, Part 1 (out of
scope) and Part 2 (merely missing); read both before starting work on a
format. **"This machine cannot get one" is a claim to re-test before it is
filed.** Where status files disagree with each other, treat it as a bug to
fix, not a fact to choose from. **A claim you are about to rely on,
contradict or re-test is always worth opening the source for.**

## The habit that produced everything valuable here

**Re-test the claims this repository already makes.** Nearly every real gain
came from that rather than from new features: "there is no oracle for this
method" was a fact about one tool, with the second oracle already sitting in
`reference/`; "no second implementation exists" was written while a
self-extracting fixture carried one in its own resource fork.

`BLOCKERS.md` keeps every withdrawn claim with **what each one cost**, and
names the fifty-one smells that keep finding the next one. The cheapest is a
**cross-file contradiction**. Another is a constant in the peak-RAM matrix:
data-driven allocations vary with their input, so one that does not is
usually a declared ceiling nobody questioned.

- **Ask what evidence a tolerance rests on. If the answer is "our own output",
  it cannot fail.**
- **The same fix does not always work twice.** Measure the second problem
  rather than porting the first one's answer.

## Traps this environment sets

- **A test that passes may not be testing anything.** Establish that a test can
  fail before believing that it passed.
- **Kill and wait on a captured pid, never a pattern.** `pgrep -f`/`pkill -f`
  match the watching shell itself (and can kill the run before it starts);
  `pkill -x minivmac` can hit another session's emulator on this shared
  machine. Use `kill -0 <pid>` to wait.
- **Put a sentinel inside the redirect**: `{ ./ci.sh; echo "CI exit $?"; } >
  ci.log 2>&1`, or let a backgrounded command notify on exit.
- **Run `ci.sh` with no wrapper.** `stdbuf` sets `LD_PRELOAD` for every child,
  ASan refuses to start, and `ci.sh` reports a green tree as `FAILED: unit
  tests (sanitizers)`.
- **Backgrounded processes lose network access here** and stall in `poll()`
  with no error; run network work in the foreground, in chunks that fit the
  timeout.
- **Do not edit a shell script while it is running** — `sh` reads it by offset.
- **The Mac OS 9 pointer works only stepped**: ≤40 px at a time, closed loop,
  never through `usb-tablet` (`tools/vmac/os9mouse.py`); drive menus with
  Command keys. On System 7's Translate menu, submenu items cannot be
  selected (`tools/vmac/README.md`), but **a submenu is worth one attempt**
  elsewhere — a System 6 one worked.
- An emulator run is minutes; do not poll it every few seconds, and **do not
  read a timeout as a measurement of anything**.

## Rules

- **Never invent format details.** Magic numbers, header layouts and algorithm parameters come from a reference implementation or spec, with a `/* Source: ... */` comment. Never guess from memory. `reference/` is read-only and never modified; `tools/fetch_references.sh` repopulates it.
- **A root cause that has never been reduced to a minimal reproduction is a hypothesis, not a finding.** Label it as such, and build the repro before acting on it or reporting it upstream (BLOCKERS.md, the withdrawn `HOpen` attribution).
- **Never file the upstream bug reports.** `tools/xadmaster-ddn-repro/` is ready to post; the maintainer posts it from his own account (MANUAL_TESTS.md §7). The Retro68 one is filed (BLOCKERS.md). Improve a repro if you have reason to — do not submit one.
- **Never weaken a test to make it pass.** CRC mismatches are per-entry errors, not skips.
- **When adding a harness, write down what it CANNOT see.** An aggregate check cannot fail on a property it never aggregates — a wrong gzip/.Z fallback NAME survived for weeks under the file-count-and-CRC grid.
- **68000 discipline** (non-negotiable): byte-wise big-endian reads only, zero unaligned dereferences; no recursion, call depth ≤ 4 KB — **measure it, do not assume it** (it was exceeded by 66 % for months; FORMATS.md, *Stack*, has the method); 32-bit arithmetic in hot paths; no libc in the engine — all I/O, allocation and progress via caller callbacks; no global mutable state; allocation failure is a per-entry error, never per-archive; progress callback every 8–16 KB with clean abort.
- **Commit and push whenever it is appropriate — do not ask.** Small, focused commits, pushed to `main` as they are made: the maintainer reads the docs on GitHub, and a wrong commit is revertible. **A release is the exception** — see *Cutting a release*.
- **`./ci.sh` green before every commit**, except a docs-only change, where `tools/check_docs.py` is the layer that can fail. Code, comments and docs in English.
- **`dist/` is a committed binary and goes stale silently**, and it is the only download. Rebuild it with `tools/make_dist.sh` in the SAME commit as any change to `mac/` or `src/`, and re-read `dist/README.txt`.
- **LGPL-2.1-or-later**, forced by transcribing XADMaster; keep `NOTICE` accurate.
- Fixture archives are copyrighted and never committed — only `fixtures/SOURCES.md` and the manifests. Same rule for the Mac ROM and System image under `tools/vmac/`.
- Work autonomously through a task list; log non-obvious decisions in `DECISIONS.md`; if something cannot be made to pass after genuine effort, write it up in `BLOCKERS.md` and move on rather than stalling.

## Cutting a release

**Never tag one unasked** — it publishes a download under the maintainer's
name, and this machine cannot see the result. Pushing a `v*` tag publishes a
GitHub release with the application attached (`.github/workflows/release.yml`,
the runner's own `GITHUB_TOKEN`); a deploy-key push may add workflow files and
trigger them — do not re-derive either.

```sh
# bump UNC_VERSION in include/macextract.h FIRST
sh tools/make_dist.sh                    # rebuild dist/ from current source
# commit dist/ + docs, ./ci.sh green, push main FIRST
git tag -a v0.12 -m "..."                # annotated; the message is the tag's
git push origin v0.12
```

- **`UNC_VERSION` is the source of truth**; `check_docs.py` fails if
  `dist/README.txt`, `--version` and README.md disagree with it.
- **Push `main` before tagging** — Actions reads the workflow from the pushed
  ref.
- **`dist/` must be current**; the workflow publishes what is committed.
- **The release notes are `dist/README.txt`, verbatim** — a download page, not
  a changelog. Re-read it before tagging.
- **This machine cannot see the release page.** Confirm the tag with
  `git ls-remote --tags origin` and report a tag pushed, never a release
  published.
- **If the page does not show the new version, re-push the same tag**:
  `git push origin :refs/tags/vX.Y.Z && git push origin vX.Y.Z` (DECISIONS.md
  2026-08-26, *the tag that did not fire*).

## Writing things down

- **Status first.** Every status file opens with the current state, readable in a minute; history goes below.
- **One home per finding.** Status → `BLOCKERS.md`. Reasoning and lessons → `DECISIONS.md`. Re-running a suite → `TESTING.md`; an emulator harness → `tools/vmac/README.md`. Outside-this-machine work → `MANUAL_TESTS.md`. Numbers and tables → `FORMATS.md`. Gaps → `OPEN_ITEMS.md`. Cross-reference; do not repeat.
- **A finding is claim, evidence, consequence.** Three lines. Expand only where the *reasoning* is worth transferring.
- **If you are writing a paragraph that explains WHY in any file other than DECISIONS.md, stop.** State the claim, give the number, cite the entry. Re-narration by paraphrase is how these docs grow; no duplicate scan catches it.
- **Correct figures in place**, noting the correction once. Never add a section that supersedes an earlier one.
- **Withdrawn claims are collected, not interleaved**, each with what it COST.
- **Label every claim: measured, hypothesis, or withdrawn.** An unlabelled claim is read as measured.
- **Closing an item means moving it, not annotating it.** The method goes where that kind of thing lives; the item is DELETED from the file that tracked it as open.
- **No plans in status docs.** Plans belong in the conversation or a commit message.
- **Never cite `FILE.md:NN`.** Cite the section or table row by name.

### `README.md` is the exception, and has its own rules

`README.md` is written for **somebody who has a `.sit` file and an old
Macintosh** — the only document that is. Judge it by whether that person can
tell in thirty seconds what this is, whether it runs on their machine, and how
long they will be waiting.

- **Concise, and human.** A screen or two. No memory budgets, allocation strategy, per-fixture tables, milestones, methodology, history or withdrawn claims; link to the other files at the end.
- **Show the application.** Screenshots live in `docs/screens/` and come from `tools/vmac/interactive.py` — real frames, not mockups. Re-take them when the UI changes, and **look at each one before committing it**: the harness clicks fixed coordinates and will photograph the wrong window.
- **Every command in it must be run before it ships.**
- **Round the numbers.** "16 minutes", not "966 s".
- **Keep the honesty, drop the hedging.** "Nothing older has" stays; the hypotheses behind an unexplained 40 seconds do not.

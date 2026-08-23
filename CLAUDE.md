# CLAUDE.md — standing instructions for **unclassic**

*An open-source universal unarchiver for Classic Mac OS (System 6 → Mac OS 9).*

## Mission

1. **`libunclassic`** — a portable, dependency-free C99 extraction engine for classic Macintosh archive and encoding formats, plus a Linux CLI (`unclassic`).
2. **A Retro68 Toolbox application** wrapping the same engine. Floor target: **System 6.0.x, 68000, 1 MB RAM**; the same binary must run unchanged through Mac OS 9.

The engine is the product. The Mac app is a thin shell.

## Where things stand

**M0–M24 are DONE and nothing is in flight.** Every family in FORMATS.md's
table extracts — that table is the count, and this file does not keep a copy
of it — and the engine passes a **919-fixture** differential suite against
`unar` and, where `unar` fails, `macunpack`, plus 9,190 robustness variants.
The Macintosh application extracts byte-exact on **System 6.0.8 at 4 MB and at
the 1 MB floor target** (62/62 sampled fixtures each), on System 7.0.1, and on
Mac OS 9.2 under QEMU including HFS+ — that last tier predates four formats
and is the one verification gap (OPEN_ITEMS.md). System 6 is the target for
the interactive UI and is driven there end to end; above it the UI is
deliberate scope, not an open item.

**Do not re-plan or re-run completed milestones.** The authoritative status is:

| file | holds | read it |
|---|---|---|
| `PROGRESS.md` | what each milestone delivered, one line each | at session start |
| `OPEN_ITEMS.md` | **what is out of scope** (part 1), then what is still missing and what would close each (part 2) | at session start |
| `BLOCKERS.md` | the tier results, and **every claim this project has withdrawn**, with what it cost | at session start |
| `FORMATS.md` | format × status × peak RAM, and every per-fixture table | for a number |
| `DECISIONS.md` | why anything is the way it is, oldest first, with a Contents index | via the index, for one entry |
| `TESTING.md` | how each suite works and what it cannot see | before changing a suite |
| `tools/vmac/README.md` | how to run the emulator harnesses and probes | before booting anything |
| `MANUAL_TESTS.md` | only what no emulator here can settle | when something needs hardware |

Those first three are ~8k tokens together. The rest is reference — opening the
one the task touches beats reading them all. **A claim you are about to rely
on, contradict or re-test is always worth opening the source for.**

**Scope is not stated in this file.** What is in, what is detect-only and what
the formats themselves make impossible is OPEN_ITEMS.md, **Part 1 — Out of
scope for v1**; what is missing only for want of a specimen or a reference is
Part 2's *"Waiting on a file this machine does not have"*. Read them before
starting work on a format: the brief has grown three times, and each time the
answer was in that list rather than here.

Where these files disagree with each other, treat it as a bug to fix, not a
fact to choose from.

## The habit that produced everything valuable here

**Re-test the claims this repository already makes.** Nearly every real gain
came from that rather than from new features: "there is no oracle for this
method" was a fact about one tool, with the second oracle already sitting in
`reference/`; "no second implementation exists" was written while a
self-extracting fixture carried one in its own resource fork.

`BLOCKERS.md` keeps every withdrawn claim with **what each one cost**, and
names the ten smells that keep finding the next one. The cheapest is a
**cross-file contradiction**: two status files disagreeing is a disproof
nobody has collected yet. A constant in the peak-RAM matrix is another —
data-driven allocations vary with their input, so one that does not is usually
a declared ceiling nobody questioned.

Two corollaries worth keeping in mind while working:

- **Ask what evidence a tolerance rests on. If the answer is "our own output",
  it cannot fail.** Two skips that could never fire were hiding 10 adjudicated
  forks; an assertion about a rationed search observed a consequence of the
  search rather than the search.
- **The same fix does not always work twice.** Growth-on-demand rescued the
  Arsenic block and made the LZW table worse, because there the table IS the
  whole allocation. Measure the second problem rather than porting the first
  one's answer.

## Traps this environment sets

All of these cost real time here:

- **A test that passes may not be testing anything.** Establish that a test can
  fail before believing that it passed.
- `pgrep -f "some command"` matches the watching shell itself, so
  `until ! pgrep ...` never exits. Use `kill -0 <captured pid>`. **`pkill -f`
  is worse**: `pkill -f "vmac/run.py"` in the same shell command as the run
  matches that shell's own command line and kills the run before it starts.
  Match the executable (`pkill -x minivmac`) or a captured pid.
- **A sentinel echoed outside the redirect never reaches the log.**
  `./ci.sh > ci.log 2>&1; echo "CI exit $?"` puts the sentinel on the shell's
  stdout, so a companion `until grep -q "CI exit" ci.log` waits forever. Put it
  inside — `{ ./ci.sh; echo "CI exit $?"; } > ci.log 2>&1` — or let a
  backgrounded command notify on exit by itself.
- **Backgrounded processes lose network access here.** A detached download or
  probe stalls in `poll()` with no error; run anything that talks to the
  network in the foreground, in chunks that fit the timeout.
- **Do not edit a shell script while it is running.** `sh` reads the file by
  offset, so an edit shifts what it executes next.
- The Mac OS 9 pointer does not work at all; drive that guest from the
  keyboard. Mini vMac's mouse is fine — except for **hierarchical menus,
  whose submenu items never highlight and cannot be selected** however the
  pointer is moved (three ways measured, `tools/vmac/README.md`). Find a
  route that is not a submenu.
- An emulator run is minutes; do not poll it every few seconds, and **do not
  read a timeout as a measurement of anything**.

## Rules

- **Never invent format details.** Magic numbers, header layouts and algorithm parameters come from a reference implementation or spec, with a `/* Source: ... */` comment. Never guess from memory. `reference/` is read-only and never modified; `tools/fetch_references.sh` repopulates it.
- **A root cause that has never been reduced to a minimal reproduction is a hypothesis, not a finding.** Label it as such in the docs, and build the repro before acting on it or reporting it upstream. This rule was learned the hard way — see the withdrawn `HOpen` attribution in `BLOCKERS.md`.
- **Never weaken a test to make it pass.** CRC mismatches are per-entry errors, not skips.
- **When adding a harness, write down what it CANNOT see.** An aggregate check cannot fail on a property it never aggregates: the on-screen result grid carries a file count and summed CRCs, so a real defect in the gzip/.Z fallback NAME survived in the corpus for weeks.
- **68000 discipline** (non-negotiable — it is what made the port compile and run first try): byte-wise big-endian reads only, zero unaligned dereferences; no recursion, call depth ≤ 4 KB; 32-bit arithmetic in hot paths; no libc in the engine — all I/O, allocation and progress via caller callbacks; no global mutable state; allocation failure is a per-entry error, never per-archive; progress callback every 8–16 KB with clean abort.
- **`./ci.sh` green before every commit.** Small, focused commits. Code, comments and docs in English.
- **`dist/` is a committed binary and goes stale silently**, and it is the only download this project offers. Rebuild it with `tools/make_dist.sh` in the SAME commit as any change to `mac/` or `src/`, and re-read `dist/README.txt` — it once described a limitation that had been fixed the day before.
- **LGPL-2.1-or-later**, forced by transcribing XADMaster; keep `NOTICE` accurate.
- Fixture archives are copyrighted and never committed — only `fixtures/SOURCES.md` and the manifests. Same rule for the Mac ROM and System image under `tools/vmac/`.
- Work autonomously through a task list; log non-obvious decisions in `DECISIONS.md`; if something cannot be made to pass after genuine effort, write it up in `BLOCKERS.md` and move on rather than stalling.

## Cutting a release

Pushing a `v*` tag publishes a GitHub release with the application attached
(`.github/workflows/release.yml`, the runner's own `GITHUB_TOKEN`; verified end
to end on v0.5). A deploy-key push may add workflow files and a deploy-key tag
push does trigger one — both settled, do not re-litigate.

```sh
# bump UNC_VERSION in include/unclassic.h FIRST
sh tools/make_dist.sh                    # rebuild dist/ from current source
# commit dist/ + docs, ./ci.sh green, push main FIRST
git tag -a v0.12 -m "..."                # annotated; the message is the tag's
git push origin v0.12
```

Five things bite, and each cost a step once:

- **`UNC_VERSION` is the source of truth.** `make_dist.sh` writes it into
  `dist/README.txt`, `--version` prints it, README.md names it, and
  `check_docs.py` fails if they disagree. It sat at "0.4.0" through four
  releases because nothing read it.
- **Push `main` before tagging.** Actions reads the workflow from the ref that
  was pushed, so a tag on a commit predating `release.yml` publishes nothing,
  silently.
- **`dist/` must be current.** The workflow publishes what is committed; it
  does not build, and it cannot tell that a present asset is three versions old.
- **The release notes are `dist/README.txt`, verbatim** — a download page, not
  a changelog. Re-read it before tagging.
- **This machine cannot see the release page** (deploy key, no `gh`, no token,
  404 from the API). Confirm the TAG with `git ls-remote --tags origin`, report
  that, and leave the page to somebody who can load it.

## Writing things down

The docs were restructured on 2026-08-03 after growing to ~3,500 lines with
most findings written up three or four times. Keep them from getting back
there:

- **Status first.** Every status file opens with the current state — tallies, what works, what is open — readable in a minute. History goes below that line, never above it.
- **One home per finding.** Status → `BLOCKERS.md`. Reasoning and transferable lessons → `DECISIONS.md`. How to re-run an automated suite → `TESTING.md`; an emulator harness or probe → `tools/vmac/README.md`. What only real hardware can answer → `MANUAL_TESTS.md`. Numbers and per-fixture tables → `FORMATS.md`. Gaps → `OPEN_ITEMS.md`. Cross-reference; do not repeat. A finding written in two files disagrees with itself within a week — which this repository treats as a bug, so do not create the opportunity.
- **A finding is claim, evidence, consequence.** Three lines. Expand only where the *reasoning* is the part worth transferring.
- **Correct figures in place.** Change the number where it lives and note the correction once. Never add a section that supersedes an earlier section: that is how one file came to state three different boot times, all of them presented as fact.
- **Withdrawn claims are collected, not interleaved**, and each records what it COST. That is what separates a claim that was merely wrong from one that displaced a capability — and the cost line is what makes the next one worth re-testing.
- **Label every claim: measured, hypothesis, or withdrawn.** An unlabelled claim is read as measured. This is the documentation half of the reproduction rule above.
- **Closing an item means moving it, not annotating it.** Keep the method where that KIND of thing lives — the lesson in `DECISIONS.md`, a disproved assertion in `BLOCKERS.md`, a milestone in `PROGRESS.md`, a figure in `FORMATS.md` — and DELETE the item from the file that tracked it as open. A "closed, kept for the method" list inside a gaps file is the failure mode; OPEN_ITEMS.md once grew nineteen such rows and stopped being readable as a list of what is left.
- **Re-narration is how these docs actually grow, and the no-duplication rule does not catch it** — paraphrase evades it, and a verbatim-sentence scan once found one repeated sentence in nine files that were nonetheless telling three stories twice each. So: **if you are writing a paragraph that explains WHY in any file other than DECISIONS.md, stop.** State the claim, give the number, cite the entry.
- **No plans in status docs.** "The next attempt is one run, not three" is dead weight the moment it is done. Plans belong in the conversation or a commit message.
- **Never cite `FILE.md:NN`.** Line numbers drift silently and are then wrong without anyone noticing. Cite the section or table row by name.

### `README.md` is the exception, and has its own rules

Every other document in this repository is written for whoever maintains it.
`README.md` is written for **somebody who has a `.sit` file and an old
Macintosh**, and it is the only one that is. Judge it by whether that person
can tell in thirty seconds what this is, whether it runs on their machine, and
how long they will be waiting.

- **Concise, and human.** Aim for a screen or two. No memory budgets, no
  allocation strategy, no per-fixture tables, no milestones, no methodology,
  no history, no withdrawn claims. Those belong in the files above; link to
  them at the end and let the reader choose to go deeper.
- **Show the application.** Screenshots live in `docs/screens/` and come from
  `tools/vmac/interactive.py` — real frames from an emulated Mac, not mockups.
  Re-take them when the UI changes, and **look at each one before committing
  it**: that harness clicks fixed coordinates and will happily photograph the
  wrong window, which is how a wrong screenshot once shipped.
- **Every command in it must be run before it ships.** A README is the most
  copy-pasted file in a project and the least tested.
- **Round the numbers.** "16 minutes", not "966 s". Precision belongs in
  FORMATS.md; the reader here wants to know whether to make coffee.
- **Keep the honesty, drop the hedging.** "No physical Macintosh has ever run
  it" stays — it is what a user needs to weigh. The four hypotheses behind an
  unexplained 40 seconds do not.

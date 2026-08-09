# CLAUDE.md — standing instructions for **unclassic**

*An open-source universal unarchiver for Classic Mac OS (System 6 → Mac OS 9).*

## Mission

1. **`libunclassic`** — a portable, dependency-free C99 extraction engine for classic Macintosh archive and encoding formats, plus a Linux CLI (`unclassic`).
2. **A Retro68 Toolbox application** wrapping the same engine. Floor target: **System 6.0.x, 68000, 1 MB RAM**; the same binary must run unchanged through Mac OS 9.

The engine is the product. The Mac app is a thin shell.

## Current state — read before working

M0–M11 are **DONE**. M11 is multi-segment archives, in scope since
2026-08-08: StuffIt segments join end to end, on Linux and byte-exact on a
real emulated Mac Plus at 4 MB and at the 1 MB floor. **A part is identified
by its header, never by its filename** — that is the whole point, and it is
why a set whose parts are scattered or named unlike each other works here and
does not work in `unar`. Other schemes are ranked in OPEN_ITEMS.md section 6;
Compact Pro's needs a genuine sample before any parser is written, because no
reference implementation extracts one.

The engine passes a 797-fixture differential suite against `unar` and, where `unar` fails, `macunpack`; the Mac shell extracts byte-exact on a real System 6.0.8 Mac Plus under Mini vMac — **55/55 sampled fixtures at 4 MB and 55/55 at the 1 MB floor** (2026-08-08, on a sample that grew from 44 to 55 that day; there are no memory-budget refusals left).

It runs on all three systems the project claims: **System 6.0.8 and System 7.0.1** under Mini vMac (a true 68000), and **Mac OS 9.2** under QEMU PowerPC through the 68LC040 emulator, where 13/13 of a format sample is byte-exact, extraction onto **HFS+** is verified, and the `SIZE` partition is honoured by the Process Manager.

**System 6 is the target for the interactive UI.** It is driven end to end there — SFGetFile, the destination dialog, progress dialog, Cancel, Cmd-., partial-output cleanup, result alert, launch by double-click. Above System 6 the UI is deliberate scope, not an open item: do not spend runs on how it looks or behaves on 7 or 9. The paths those tiers exist for are tested directly instead, without a Finder.

**Do not re-plan or re-run completed milestones.** The authoritative status lives in:

- `PROGRESS.md` — milestone table
- `FORMATS.md` — format × status × peak RAM matrix, plus the per-fixture results for every tier: Mini vMac 4 MB and 1 MB, System 7, and Mac OS 9 (including HFS+)
- `BLOCKERS.md` — status first (no open blockers), then what is true and
  load-bearing, then **Withdrawn claims**: ten assertions this file used to
  make, each with what disproved it and what it cost. They are kept on
  purpose — twice a live claim has been re-tested because it sat beside an
  already-withdrawn one, and one of those was worth 39/44 → 40/44 at the
  floor target. Do not delete them.
- `DECISIONS.md` — every non-obvious engineering decision, oldest first
- `OPEN_ITEMS.md` — what is still missing, ranked, with what would close each
- `TESTING.md` — how the automated suites work and what each layer cannot see
- `tools/vmac/README.md` — how to re-run an emulator harness or a `-D` probe
- `MANUAL_TESTS.md` — **the to-do list for whoever has real hardware**: only what no emulator here can settle. Nothing else belongs in it

Read them at the start of every session. Where these files disagree with each other, treat it as a bug to fix, not a fact to choose from.

## Where to start (handoff, 2026-08-08)

The repository is on GitHub as a **private** repo, `main`, tagged through
`v0.6`, the release that adds StuffIt method 6 (`v0.5` was the first tag to
publish a downloadable application at all — see *Cutting a release*). Working
tree clean, `./ci.sh` green, nothing in flight. **Whether v0.6's release page
actually appeared has not been checked from here and cannot be**: this machine
has no `gh`, no token, and the Releases API answers 404 for a private repo —
re-tested 2026-08-08. `git ls-remote --tags origin` does work over SSH, so the
TAG is confirmed pushed; the release page it triggers is not.

**The differential suite is 797 fixtures, not 769** (2026-08-08), and all
three increases came from the measuring apparatus rather than from new archives.
The third: **`unar` failing on a fork is a fact about `unar`.** Every fork it
leaves unadjudicated is now offered to a SECOND oracle, macutils' `macunpack`,
built out of `reference/` by `tools/build_macunpack.sh` and recorded per fork
as `"data_oracle"` / `"rsrc_oracle"`. That settled 23 forks across 9 fixtures,
of which only ONE is the method it was built for — so the value was in the
other 22, on methods already implemented. It also closed StuffIt **method 6**
("fixed Huffman"), which four status files had called unverifiable here
because XADMaster refuses it: the oracle was in the repository the whole time
(BLOCKERS.md *Withdrawn claims*). Note the two traps that cost time: macunpack
must be built `-m32` or the STORED-segment branch is unreachable in it, and a
PREDICTED output filename becomes ground truth — a missing `.data` is an empty
fork only when the entry's `.info` proves the entry was written at all.
DECISIONS.md and TESTING.md, 2026-08-08.

And the reason the suite is 797 rather than 795: reviewing that day's harness
work for hardcoded fixture names found none, but found **two excuses that
could not fail.** One rested on our OWN error message — a fixture was skipped
whole when every entry the binary called "recognized but unsupported", so the
thing being graded decided whether it was graded, and it was quietly
discarding 10 adjudicated forks of the two PKZIP 1.x zips. The other excused a
whole ENTRY where the oracle had failed one of its forks, so an adjudicated
fork beside an unadjudicated one was never required to exist. Both now anchor
on the oracle: manifests record `oracle_methods` from `lsar`, and only a
method the ORACLE puts outside v1 scope excuses anything. **Ask what evidence
a tolerance rests on; if the answer is "our own output", it cannot fail.**
DECISIONS.md and TESTING.md, 2026-08-08.

The second: `make_manifests.py` discarded a whole manifest whenever `unar`
failed on any single entry, so 19 fixtures contributed no oracle coverage at
all — including the corpus's only StuffIt **method 1** fork, which `unar`
decodes perfectly (it fails on a different entry of that archive, using a
different method). Manifests now record per-fork `"unadjudicated"` where the
oracle failed and keep everything else. **`oracle FAILED on X` scrolling past
on every rebuild read as a fact about the fixture; it was a fact about the
builder.** DECISIONS.md and TESTING.md, 2026-08-08.

The first: nine
fixtures had been written off as ground truth the oracle could not produce —
seven "structurally undecidable", two "oracle-buggy". Both reasons were
properties of one flag: `unar -k visible` names resource forks `NAME.rsrc`,
which collides with a real entry called `X.rsrc` and which GNUstep refuses to
build for a leading `~`. Rebuilt with `-k hidden` (`._NAME`) all nine decide,
and all 774 pre-existing manifests come back entry-for-entry identical, so the
switch changed the measuring apparatus and not the ground truth. The CLI grew
`--forks hidden` because it had the same collision on its own side; the default
naming is unchanged, but the CLI now **refuses to write over an existing output
file** (per-entry error, `--overwrite` restores the old behaviour) — it used to
destroy a 7 KB resource fork on a THINK C archive and exit 0.
DECISIONS.md and BLOCKERS.md, 2026-08-08.

**The 1 MB floor is 55/55 as of 2026-08-08 (44/44 on 2026-08-07, before the
sample grew), and the StuffIt 5 / Arsenic capability gap is closed.** All six
sampled StuffIt 5 fixtures extract every
entry byte-exact on a 1 MB Mac Plus. There is no remaining "this format needs
a bigger machine" caveat anywhere in the project.

The last two — `a2basic.dmg` and `Library_ISBN` — were a genuine shortage
rather than a placement problem, so they were closed by making the decoder
NEED less rather than by finding it more memory. `ars_inverse_bwt` builds a
transform vector costing 4 bytes per block byte; when that allocation fails,
`ars_index_build` substitutes a sampled occurrence index (one sample per
`1 << shift[c]` occurrences of each byte value) and the walk scans forward
from the nearest sample. Adaptive per block, fast path tried first, and it
costs a machine that never needs it exactly 8 bytes. DECISIONS.md 2026-08-07,
FORMATS.md "Floor target verification".

Two things about that change are worth carrying forward:

- **A time-for-memory dial makes "peak heap" stop meaning "requirement".**
  The decoder halves its sampling target only until the allocator says yes, so
  under a cap it spends the cap. `Library_ISBN` peaks at 614,080 B under a
  678,392 B budget and extracts fully from 393,028 B. If you compare a
  peak-under-budget against a predicted requirement you will conclude the
  prediction was 60% out when it was accurate. **Bisect the cap.**
- **Estimate the thing you are changing.** This prediction was within 200 bytes
  on one fixture and 3.6% on the other, because it estimated one allocation
  inside one entry. The method 13 estimate a day earlier missed badly because
  it estimated an aggregate over a distribution. Same author, same week, same
  confidence — the difference was the shape of the quantity.

Several remedies in this area are ruled out BY MEASUREMENT and listed in
OPEN_ITEMS.md section 5 as do-not-retry: `MaxMem()` before a retry, and
relocatable blocks moved high with `MoveHHi`.

The method 13 LZSS window lead is DONE (2026-08-06): the window is now sized
from the entry rather than from the format's 64 KB, 34 fixtures improved, none
regressed. Note that the estimate which motivated it predicted ~115 and was
wrong for a reason worth carrying — peak heap is a per-archive MAXIMUM, so one
large fork pins an archive's peak however many small forks it has, and a
per-fork distribution cannot predict it. DECISIONS.md, 2026-08-06.

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
- "Eight fixtures the oracle cannot adjudicate" — filed under *cannot be closed
  in this environment*, and closeable in an hour. It was nine, and it was the
  fork-naming flag (769 → 778 fixtures). The remedy was quoted in TESTING.md
  one paragraph above the limitation it removes.
- "There is no oracle to check a StuffIt method 6 implementation against" — a
  fact about XADMaster, restated in four files as a fact about this
  environment. `reference/macutils` has decoded the method since 1991. Building
  it as a second oracle closed the method AND adjudicated 22 forks of other
  methods (793 → 795). **A limitation that names one tool is a limitation of
  that tool.**

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
  **`pkill -f` has the same flaw and it is worse**: put `pkill -f
  "vmac/run.py"` and the run itself in one shell command and the pattern
  matches that shell's own command line, so it kills itself before the
  work starts. It looks like the run crashed instantly. Match on the
  executable (`pkill -x minivmac`) or kill a captured pid.
- **A sentinel echoed outside the redirect never reaches the log.**
  `./ci.sh > ci.log 2>&1; echo "CI exit $?"` sends the sentinel to the
  shell's stdout, not into `ci.log`, so a companion
  `until grep -q "CI exit" ci.log; do sleep 30; done` waits for a string
  that can never appear. The watched job finishes fine and the watcher
  polls for ever; five of them accumulated in one session before anyone
  noticed. Put the sentinel inside the redirect —
  `{ ./ci.sh; echo "CI exit $?"; } > ci.log 2>&1` — or, better, do not
  hand-roll a watcher: a backgrounded command notifies on exit by itself.
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
- **`dist/` is a committed binary and goes stale silently.** It is the only download this project offers. Rebuild it with `tools/make_dist.sh` and commit the result in the SAME commit as any change to `mac/` or `src/`, and re-check that `dist/README.txt` still describes what the application does — it claimed large StuffIt 5 archives fail on a small Mac for a day after they stopped doing so.
- **LGPL-2.1-or-later**, forced by transcribing XADMaster; keep `NOTICE` accurate.
- Fixture archives are copyrighted and never committed — only `fixtures/SOURCES.md` and the manifests. Same rule for the Mac ROM and System image under `tools/vmac/`.
- Work autonomously through a task list; log non-obvious decisions in `DECISIONS.md`; if something cannot be made to pass after genuine effort, write it up in `BLOCKERS.md` and move on rather than stalling.

## Cutting a release

Pushing a `v*` tag publishes a GitHub release with the application attached.
`.github/workflows/release.yml` does it, using the runner's own
`GITHUB_TOKEN`. **Verified end to end on v0.5, 2026-08-07.**

```sh
sh tools/make_dist.sh                    # rebuild dist/ from current source
# commit dist/ + docs, ./ci.sh green, push main FIRST
git tag -a v0.6 -m "..."                 # annotated; the message is the tag's
git push origin v0.6
```

Four things will bite you, all of them cost a step on v0.5:

- **Tag the commit that contains the workflow.** Actions reads the workflow
  from the ref that was pushed, so a tag pointing at a commit predating
  `release.yml` publishes nothing, silently. Push `main` before tagging.
- **The release notes are `dist/README.txt`**, verbatim. It is a user-facing
  download page, not a changelog — check it still describes the application
  before tagging.
- **`dist/` must be current.** The workflow publishes what is committed; it
  does not build. It fails if an asset is missing or empty, but it cannot tell
  that a present asset is three versions old.
- **Confirming it worked is a human step — but confirm what you CAN.** The repo
  is private and this machine authenticates with a DEPLOY KEY, which signs git
  over SSH and cannot read the Releases or Actions API at all: re-tested
  2026-08-08 on v0.6, `gh` is not installed, no token is in the environment,
  and both `/repos/...` and `/repos/.../releases` answer 404. What *does* work
  over SSH is `git ls-remote --tags origin`, which settles that the tag reached
  GitHub — the half that used to be assumed from a `git push` exit status.
  Publishing itself is NOT a human step: the workflow does it, unattended, and
  a deploy-key tag push triggers it (v0.5, v0.6). So report the tag as pushed
  and the release page as unverified, and never collapse the two.

A deploy-key push *is* allowed to add files under `.github/workflows/`, and a
deploy-key tag push *does* trigger a workflow. Both were open questions before
v0.5 and both are now settled; do not re-litigate them.

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
- **Closed items get a table row, not an essay.** Keep the method if it transfers to the next problem; drop the narrative.
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
  `tools/vmac/interactive.py`, so they are real frames from a real emulated
  Mac rather than mockups. Re-take them whenever the UI changes, and **look at
  each one before committing it** — that harness clicks fixed coordinates and
  will happily photograph the wrong window (`tools/vmac/README.md`). One of the four
  currently in the repo was wrong for exactly that reason on 2026-08-07.
- **Every command in it must be run before it ships.** A README is the most
  copy-pasted file in a project and the least tested.
- **Round the numbers.** "16 minutes", not "966 s". Precision belongs in
  FORMATS.md; the reader here wants to know whether to make coffee.
- **Keep the honesty, drop the hedging.** "No physical Macintosh has ever run
  it" stays — it is what a user needs to weigh. The four hypotheses behind an
  unexplained 40 seconds do not.

## Out of scope (v1)

Compression (extraction only), StuffIt X (`.sitx`), encrypted archives, disk images, DiskDoubler, Now Compress, LZH/LHA. These are **detect-only**: `unc_sniff` names them — including Disk Copy 4.2, whose probe is now real — so a UI can tell the user what the file is, and extraction returns cleanly unsupported.

**Multi-segment archives are IN scope since 2026-08-08** (M11), where this
file used to list them as out. One scheme is implemented — StuffIt segments —
and the others, including Compact Pro's, are ranked in OPEN_ITEMS.md section
6 with what each would cost. The rule that decided the order: **a part must
be identifiable from its own bytes.** A `.001` split cannot be, whatever it
is named, so it buys less than it looks like it does.

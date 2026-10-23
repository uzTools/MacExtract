# BLOCKERS.md

## Status

**No open blocker.** The last one — the application bombing on Mac OS 9.2 on
every DiskDoubler archive and on SuperDisk! — was an `UncOptions` field the
shell never assigned (*Withdrawn claims*; DECISIONS.md 2026-09-04, *the
field nobody assigned*). The engine and CLI were never affected by anything
in this file.

The sample is **74 fixtures**: `shrink-wild-titanic.zip` joined 2026-10-09,
`4alnch11.zip` (Implode) 2026-10-10 and `synth-sqp-clear.pkg` (an AppleLink
package) 2026-10-11. Every tier ran on the v0.37.0 source, each 2026-10-10
sweep paired with a `-D UNC_AT_BUDGET` sweep read field by field
(`tools/vmac/README.md`, *Why an entry is refused*): no refusal, first-entry
error, late image or failed keep on any of the 238 runs.

| tier | result |
|---|---|
| System 3.0 / Finder 5.1, 4 MB Mac Plus (Mini vMac, a true 68000) | **74/74**, 2026-10-10, `synth-sqp-clear.pkg` 2026-10-11 |
| System 3.0 / Finder 5.1, **1 MB** — the oldest system, at the RAM floor | **74/74**: the 72 on 2026-10-09, `4alnch11.zip` 2026-10-10, `synth-sqp-clear.pkg` 2026-10-11 |
| System 3.0, **512 KB** Macintosh 512Ke | **72/74**, re-measured whole on 2026-10-23 after the decoder shims became one routine (`sys30.py --emu mv-512Ke`, first pass; DECISIONS.md 2026-10-23, *the shims that were one function*), the same two refused by name; **72/74**, re-measured whole on 2026-10-22 after the runtime was trimmed (`sys30.py --emu mv-512Ke`, first pass), the same two refused by name; **72/74**, re-measured whole on 2026-10-21 after the sniffer's image (`sys30.py --emu mv-512Ke`, one `NOGRID` re-run), the same two refused by name, and on 2026-10-18 after M70 (`c0be3ab`), the same two; before it the 72 on 2026-10-09, `4alnch11.zip` 2026-10-10, `synth-sqp-clear.pkg` 2026-10-11 — two per-entry memory refusals, not failures, the two `run_tiers.py --shipped` named. With every decoder resident it is 68/72, the four the resident lane names (2026-10-09; the resident build has run neither of the two): the overlays are what recovered the other two (FORMATS.md, *Overlays*) |
| System 6.0.8, 4 MB Mac Plus | **74/74**, 2026-10-10, `synth-sqp-clear.pkg` 2026-10-11 |
| System 6.0.8, 4 MB, **the stock System Folder** — every INIT and cdev loaded, AppleShare's `Desktop Mgr` among them (`run.py --keep-inits`); a tier of its own since 2026-10-21, beside the stripped one and not instead of it, the maintainer's call | **74/74**, re-measured whole on 2026-10-22 after the runtime was trimmed (`run.py --keep-inits`, first pass); **74/74**, 2026-10-21, on v0.42.0; v0.41.0 bombed its first application (*Withdrawn claims*). **At 1 MB the machine does not get as far as the application**: the System's own stop-sign alert, its text undrawn, before any grid, on the first two fixtures tried (2026-10-21) — the strip exists for that machine, and the 1 MB tier stays stripped |
| System 6.0.8, **1 MB** — the RAM floor | **74/74**, re-measured whole on 2026-10-23 after the decoder shims became one routine (`run.py --mem 1M`, first pass; DECISIONS.md 2026-10-23, *the shims that were one function*); **74/74**, re-measured whole on 2026-10-22 after the runtime was trimmed (`run.py --mem 1M`, first pass; DECISIONS.md 2026-10-22, *the runtime the application did not need*); **74/74**, re-measured whole on 2026-10-21 after the sniffer's image (`run.py --mem 1M`, one `EMUDIED` re-run; DECISIONS.md, *the probes that left with the bundle*); before it the 72 on 2026-10-09 (one fixture re-run after an `EMUDIED`, a host-side exit before any grid), `4alnch11.zip` 2026-10-10, `synth-sqp-clear.pkg` 2026-10-11; no memory-budget refusals remain |
| System 6.0.8, **512 KB** Macintosh 512Ke | **68/74**, re-measured whole on 2026-10-23 after the decoder shims became one routine (`run.py --emu mv-512Ke --system System6.hfv`, first pass), the same six refused by name; **68/74**, re-measured whole on 2026-10-22 after the runtime was trimmed (`run.py --emu mv-512Ke --system System6.hfv`, first pass), the same six refused by name; **68/74**, re-measured whole on 2026-10-21 after the sniffer's image (`run.py --emu mv-512Ke --system System6.hfv`, one `EMUDIED` re-run), the same six refused by name, and on 2026-10-18 after M70 (`c0be3ab`), the same six, as `run_tiers.py --check` predicted; before it the 72 on 2026-10-09, `4alnch11.zip` 2026-10-10, `synth-sqp-clear.pkg` 2026-10-11 — six per-entry refusals. **The model said 67/72**: `a2ps.V4.3.tar.Z`, which passed here on 2026-09-27, is refused 4,142 B short, and the model passed it on budgets 16,888 B stale (*Withdrawn claims*). With every decoder resident, 63/72, the nine the resident lane names (2026-10-09; not run on the two newest) — ten since 2026-10-11, DERIVED: `derived-DD_Expand.sea` is 436 B short after `JPEG Lossy`'s +704 B to the control; eleven since 2026-10-17, DERIVED: `derived-PuzzleGetter_0.8.sit`, after the sidecars' +4,080 B to the control |
| System 7.0.1, 4 MB | **74/74**, re-measured whole on 2026-10-22 after the runtime was trimmed (`run.py --system Sys7.img`, first pass); **74/74**, 2026-10-10, `synth-sqp-clear.pkg` 2026-10-11 — the only tier with a code-cache flush route: `_HWPriv` called on all 72 of the `UNC_AT_BUDGET` sweep, once per kept image plus the bundle fixup |
| **Macintosh LC 475, real, round 3** (2026-10-13, `main` at f4e87ac, MANUAL_TESTS.md §4–§5, in progress) | By eye: Standard File's Desktop to other volumes and back; the destination dialog (opens in the archive's folder, Cancel back, prompt whole); a two-floppy split set in one drive, the first ejected by itself, left dimmed — unmounted since, confirmed on the LC 2026-10-14 (DECISIONS.md 2026-10-14); Cancel highlights; Cmd-. cancels on a U.S. layout, and on AZERTY with the period typed as it is there, with Shift; output chosen two folders deep lands there, not at the root; MacExtract on one floppy, the archive opened from another through Standard File: no swap after Save (the preloading build; the day before's copy asked ME, C, ME, as under emulation). A `/` in names reached the disk as `/` (the share stores U+F022); the same archive twice gave `fold~1`, `fold~2`, `README~1`, nothing overwritten, per the saved reports. Two dropped archives: eleven swaps before the first dialog and one inside the second alert, the System's and the Finder's (DECISIONS.md 2026-10-14); a Calculator dragged over the progress window once crawled for two minutes, not reproduced on the LC nor under emulation; while any window is held the extraction stops and resumes on release, as every background process does under cooperative multitasking |
| **Macintosh LC 475, real, round 2** (2026-10-12, `main` at 238feef) | **24/24 archives, 188 files byte-exact in both forks**, written over AppleShare and graded from Linux: every decoder image on a CPU with a cache, no bomb (MANUAL_TESTS.md §4). A full floppy stopped with *"The disk is full"*, the entry in flight deleted. The build WITHOUT the cache flush: 6 archives, 28 files byte-exact (DECISIONS.md 2026-10-12, *the flush the LC 475 did not need*) |
| **Macintosh LC 475, real** (68LC040, System 7.6.1, 12 MB) — the first silicon | **9/11 on `dist/` v0.39.0**, 2026-10-11, by the maintainer: `.cpt`, StuffIt 1.5, methods 13 and 14, StuffIt 5 (to 45 entries, 29 s), MacBinary and BinHex, no bomb; counts and names checked by eye, not bytes. The two zips failed and were a shell defect every tier was blind to, fixed and re-run under emulation only (DECISIONS.md 2026-10-11, *the zip that was a set of one*). Truncated and non-archive files refused as designed. **At the declared 400 KB minimum partition** (set in Get Info), a StuffIt 5 archive refused one entry per entry, *"at least 136K"* short, and the rest came out, no bomb; free heap not read, one archive only |
| **Mac OS 9.2.2, real PowerPC, HFS+** (2026-10-14, MANUAL_TESTS.md §3) | By the maintainer: launch, PackIt and StuffIt 5 onto HFS+ byte-exact (data forks, read back), 8-bit names drawn right, a 32-character name cut to 31, output two folders deep. A 2.3 GB entry ended the run on *"The disk is full"*; refused as one entry since, confirmed there (DECISIONS.md 2026-10-14) |
| Mac OS 9.2 (QEMU PowerPC, 68LC040 emulation) | **22/22** on 2026-10-22 after the runtime was trimmed (`os9.py --list os9sample.txt --launch`), launch and quit to the Finder on every one: 20 in the sweep and `derived-800saywhat301j.sit` and `synth-os9-rar.rar` on re-run, the sweep having stopped when `./ci.sh` deleted the reference build it grades against; **22/22 in one sweep**, the whole of `os9sample.txt`, one boot per fixture — 2026-10-10, through the interactive application (`--launch`, byte-identical to `dist/`) and the autotest build alike |

The heaviest 4 MB allocation is the same to the byte on all three 4 MB
tiers, 44 B under the Linux engine (FORMATS.md, *System 7 tier*).

**Every other tier above boots System + Finder alone.** The stock-folder
row is what caught issue #1: `run.py --keep-inits --expect` on
`OriginalCM.sit` is NOGRID on the v0.41.0 shell and PASS on v0.42.0.

**Run off the sample**, none of it committable, each graded against this
engine's Linux output (`run.py --expect`):

- **AppleLink `.pkg`**: all eight real packages byte-exact on all seven Mini
  vMac tiers, 2026-10-10 (FORMATS.md, *Run on a Macintosh*).
- **Self-extracting zip**: the five ZipIt `.sea` specimens on all seven,
  2026-10-10 (`tools/specimens/zipit.tsv`). On System 3.0 at 1440 KB,
  `zipit-1.4.sea`'s last fork is a per-entry `UNC_ERR_SINK` because the
  Finder's `DeskTop` file fills the Out volume; it passes at 1600 KB.
- **Private File**: through the password dialog on System 6.0.8 at 4 MB
  and 1 MB (2026-10-09) and on both 512 KB machines (2026-10-10), a wrong
  password refused first each time.

Per-tier history, per-fixture tables and what each refusal costs are
FORMATS.md's (*Real-hardware verification* and the tier sections after it);
re-running is `tools/vmac/README.md`; what no emulator can settle is
MANUAL_TESTS.md.

---

## What is true, and load-bearing

**How the Mac shell is verified.** The autotest build CRC-32s both forks read
back through the real File Manager and paints the aggregate to the
framebuffer; the host decodes a screenshot and compares it with the Linux
output, and reads the Out volume for **names**. Only Mini vMac exercises the
Toolbox glue: the qemu-m68k mock calls the sink directly.

**The fix that unblocked M10 is understood: `ioMisc`.** Explicit, fully
zeroed HFS param blocks (`PBHOpenSync` and siblings) are what ships. Measured
2026-10-13 on the M10-era shell (`014ed25`), 4 fixtures per build: Retro68's
glue fails 0/4, a verbatim copy of it fails 0/4, and the same copy with
`ioMisc = NULL` alone passes 4/4 (DECISIONS.md 2026-10-13, *the bug was the
footnote*).

**Upstream: Retro68's `HOpen`/`HOpenRF`/`HOpenDF` glue leaves `ioMisc` as
stack garbage, and the File Manager writes through it** — measured 2026-10-13:
524 bytes on System 6.0.8, 12 on System 7.0.1, into memory the caller never
passed. MacExtract is unaffected (zeroed param blocks).
Filed 2026-10-13 as https://github.com/autc04/Retro68/issues/320
(`tools/retro68-hopen-repro/`); **fixed upstream 2026-10-14** with the
issue's patch verbatim (multiversal `4c78d24`, pulled in by Retro68
`afe277e`). Toolchains built before that still carry the bug.

**Upstream: four more glue fields, measured 2026-10-15 against multiversal
`4c78d24` on Systems 3.0, 6.0.8 and 7.0.1** — `GetWDInfo` (`ioWDIndex`,
`ioNamePtr` unset: `nsvErr`), `SetFInfo` (`ioFDirIndex` unset: sets the
wrong file's Finder info), `HSetFInfo` (`fnfErr` on HFS even with a zeroed stack),
`HOpen` family (`ioFVersNum` unset: `fnfErr` on MFS). MacExtract is
unaffected (own blocks). Draft and patch: `tools/retro68-hopen-repro/`
(*glue_audit*). Filed 2026-10-15 as
https://github.com/autc04/Retro68/issues/322.

**Upstream: `GetAppFiles`/`ClrAppFiles` never return for index ≥ 2**
(multiversal `glue.c`, `AppFilePtr` never decrements) — measured
2026-10-15 on Systems 3.0, 6.0.8 and 7.0.1; a one-line patch fixes all
three. MacExtract is unaffected (`DropNext` reads `AppParmHandle` itself).
Filed 2026-10-15 as https://github.com/autc04/Retro68/issues/323
(`tools/retro68-hopen-repro/ISSUE-appfiles.md`).

**`HideCursor()` before drawing the grid — confirmed by reproduction**: without
it, a pointer dragged through the grid flips one bit of the result
(`0x04000000`, reproduced twice). What must
be right before that test means anything is in `tools/vmac/README.md`.

**`unar` is wrong about ARC/PAK method 0x0b (Distilled)**, starting the window
at zero where PAK fills it with spaces, so deark is that method's oracle
(`tools/run_pak.py`). `unar` stays the oracle for 0x0a (Crushed), which deark
lacks; PAK's stored CRC-16 outranks both.

**`unar` does not read ARC 7.x at all**, stopping at the informational item
(method 0x14), so `tools/run_arcplus.py` consults deark and
`fixtures/manifests/derived-ARCDOS.arc.json` is registered by that tool
(TESTING.md).

**`src/fmt_binhex.c` owes macutils nothing since 2026-10-07**: its last rule
is cited to StuffIt's own `HQXEngine` (SDK 5.1.2, `Eng ` 10000), and
`check_provenance.py` fails if a macutils `Source:` survives (DECISIONS.md
2026-10-07, *the engine four layers down*). Taking that engine family apart
named Private File, which reads since 2026-10-09 (DECISIONS.md 2026-10-07,
*the engine list as a checklist*).

---

## Withdrawn claims

**Kept deliberately, and this is the part of the file to read first.** Twice a
live claim has been re-tested *because* it sat beside an already-withdrawn one,
and one of those was worth 39/44 → 40/44 at the floor target. **Fifty-one**
mechanisms keep finding the next one — recounted 2026-10-11; the
sentence said ten when the list had thirty, on 2026-09-26 — and three of them
need no insight at all (the third is the scan at the end of the list):

- a live claim sitting next to an already-withdrawn one;
- **two files disagreeing** — a cross-file contradiction is a disproof nobody
  has collected yet;
- a limitation written one paragraph from its own remedy;
- **a limitation stated about the environment that is true only of one tool.**
  Read every "cannot be done here" for the name of the tool it is really about;
- **an open item that describes what our OWN binary does.** Added
  2026-08-29: two MIME entries in the waiting-on-a-file section said what
  mpack does and what this engine does. Four such sentences, three of them
  false, none ever run — and each was one command away from being checked.
  A claim about a program on this disk is the cheapest in the repository to
  test and so the easiest to leave untested (below).
- **somebody else complaining about the tool you grade yourself by.** Added
  2026-08-21: a test corpus's README said `unar` was "hit-or-miss" on
  DiskDoubler Pro and that the same files unpacked fine on the Mac. That is a
  bug report against the oracle, written by someone who had already ruled out
  the files;
- **inputs from outside the corpus.** Added 2026-08-21: nine archives nobody
  here had seen, and five of them failed in the first minute (below). A suite
  that is green on the files it has says nothing about the files it has not,
  and this is the only mechanism here that needs no insight — just files.
- **what the corpus never does that the claim would allow.** Added
  2026-08-21: a rule inferred from the records it was drawn from fits every
  one of them, so counting those proves nothing. Count the records it does
  NOT cover instead — 30 `0x1000` entries fitted the claim and 45 in the same
  fifteen files contradicted it (below).
- **a limitation you inherited from the reference rather than measured.**
  Added 2026-08-23: "the algorithm for this is unknown" is a sentence in
  The Unarchiver's format notes about Compact Pro's encryption, and this
  project had been repeating it. It is a statement about what somebody
  wrote down, not about what is reachable — the algorithm was in the
  application all along, in a binary already in `fixtures/` and already
  being driven under emulation for something else.
- **a correct WORKAROUND with the wrong reason attached.** Added
  2026-09-22: `checkdisk.py` passed `hls -a` and said in a comment that
  hfsutils hides names beginning with a dot. The flag was right and the
  reason was false — `-a` is about the Finder INVISIBLE bit, and a dotted
  name with the bit clear is listed without it. Because the stated reason
  was "dotfiles", four later walks whose subjects had no dotfiles skipped
  the flag and looked safe, and one of them reported a file MISSING that
  was on the volume (below). **A wrong reason attached to a right fix
  does not fail anything, so nothing ever re-tests it — and it is what
  the next person copies instead of the fix.** Look for the explanation
  beside a flag, not just the flag.
- **a deviation from a reference, measured against OUR rendering of it.**
  Added 2026-10-05: "SqueezePlay sets the next free code to 256 after a
  clear where `compress` sets 257" is true about `src/unc_lzw.c` and false
  about `compress`, whose own decompressor sets 256 —
  `reference/macutils/macunpack/de_compress.c`, `free_ent = FIRST - 1`.
  257 is deark's rendering, and deark is what this engine was transcribed
  from. **Before calling something a deviation, open the thing it is
  supposed to deviate FROM**, not the file that implements it here. The
  cost of this one was zero only because it was checked: the item built on
  it asked for a codec parameter or a separate code path, and the measured
  answer was neither (below).
- **a reading that passes being read as a reading that is complete.**
  Added 2026-10-05: `tools/derive_sqp.py` graded 4 of 4 members of both
  real AppleLink packages byte-exact and had **five fields wrong**,
  because every one of them is zero or constant in those two files — two
  longwords filed as "read by nothing" are the resource fork's length and
  offset, the stored flag is a bit of a BYTE and not of a word, the
  resource fork has its own stored bit, and the header's count is one of
  TWO counts. What found them was reading the WRITER as well as the
  reader. **A grading that cannot fail on a field is not evidence about
  that field**, and the question to ask is which fields the corpus holds
  constant (below).
- **a sample of a dispatch table read as the whole table.** Added
  2026-10-05: two `GetResource('Eng ', N)` sites were cited as where a
  format's decoder lives. There are fourteen of them — one pair per id,
  0 through 6 — and the pair that was sampled belongs to a different
  format. **Count the call sites before believing the one you read**, and
  the cheap check is whether the ids form a complete range. This is the
  2026-09-27 lesson one step on: that one said check which QUESTION the
  cited routine answers, and this one says check whether the routine you
  cited is one of many (below).
- **a probe whose fixture carries a dimension its verdict throws away.**
  Added 2026-09-22: `walkprobe.py` built its volume with the four
  subjects at the root AND the same four inside a folder, and its
  docstring said "so a walk is tested at depth as well" — while the
  comparison reduced every result to leaf NAMES, and the folder holds
  the same four names as the root. A walk returning two entries and one
  returning eight both scored 4/4, and **four of eight never descend**.
  The fixture was right and the reading was lossy, which is the harder
  half to notice: the evidence was on the disk the whole time. Ask what
  the subject varies that the verdict cannot express.
- **a remedy aimed at a step that had already happened.** Added
  2026-09-22: a file the Macintosh had saved could not be read off the
  image, and four flush remedies were tried — a 30 s wait, Control-Q,
  SIGTERM, the shell's own `FlushVol`. All four were about getting a
  write out; the write was already out. What was missing was the
  CATALOG entry that follows it, and one reading of the raw image said
  so. **When a remedy that should work does not, check that it is
  aimed at the step that actually failed** — four failed remedies are
  evidence about the diagnosis, not about the remedies.
- **a survey built by grepping for one spelling.** Added 2026-09-22 and
  found by the same run: the inventory of "every volume walk in this
  tree" was assembled by searching for `hls`, and two walks list with
  `hdir`. So the table that scoped the work — and the count "four
  walks" in three files — was six of eight. `hdir` hides the invisible
  bit exactly as `hls` does, which DECISIONS.md already stated and no
  probe had ever asked. **An inventory is a claim like any other**, and
  the cheapest disproof is to search for the CAPABILITY rather than for
  the name one implementation gave it.
- **a check that only runs where the others are silent.** Added
  2026-09-21: the third oracle was offered a fork only when `unar` AND
  `macunpack` had both left it open, so on every method the others could
  read it was never asked — and deark had been in `reference/`, compiled
  by `ci.sh` and running for another format, for four weeks while this
  file said no second implementation of StuffIt method 6 existed. **A
  check positioned where nothing can contradict it cannot contradict
  anything.** Ask what a check is not run ON, not what it covers.
- **an oracle that never fails.** Added 2026-09-21: deark writes output
  for a truncated file by PADDING it to the length its header declares —
  286 bytes for a resource fork with 234 in the file, the last 52 zeros
  it made up. An implementation that always produces something is not
  ground truth about a file that does not contain it, and taking its
  word wrote those zeros into a manifest and then failed seven fixtures
  against them. Ask what the oracle does when the input is damaged
  before believing it where the others declined.
- **every input a suite grades against, made by one program.** Added
  2026-08-23: `run_btoa.py` grades the decoder against btoa 5.2.1 itself,
  which is the right oracle and is also a Unix program that has only ever
  written LF. Twenty-one cases therefore agreed on a property none of them
  chose. Ask what the generator never varies — for a text format read on a
  Macintosh, the line ending is the first thing to ask about (below).
- **a rule proved on one file and applied to the other forty.** Added
  2026-08-30: "everything builds at `-Os`, and that was TESTED" cited a real
  measurement — on one file, whose profile is unlike every other file's. The
  citation is what made it look settled. **Ask what the measurement's subject
  actually was**, and whether the claim is about that subject or about the
  category it belongs to (below).
- **a fix whose scope was asserted rather than grepped.** Added
  2026-09-03: a commit that repaired one call site closed with "one CLI
  per file now"; two more sites in that same file were untouched, and
  they became the next three failures (below). **A fix that says "now
  the whole file does X" is a claim about every line of it, and `grep`
  settles it in a second.**
- **a difference you read rather than ran.** Added 2026-08-27: two
  checks were called "the same test, one of them weaker" on the strength
  of how they were WRITTEN — different variable, different constant.
  They compute the same predicate. Comparing two pieces of code by
  appearance answers a question about spelling; run both over their
  inputs and compare the answers (below).
- **a grep that cannot match what the file actually says.** Added
  2026-08-23, and it is the only mechanism here that hid a stale claim
  rather than finding one: `OPEN_ITEMS.md` still said Compact Pro's
  cipher was ungraded a day after the application graded it, and a
  search for the exact sentence returned nothing — because the file
  wraps it as `no second\n  implementation has graded` and grep is
  line-based. The clean-up script that should have deleted the entry
  had aborted on a later `assert` and written none of its edits, so the
  false negative confirmed a failure. Collapse the wrapping before
  searching prose, and never take a clean grep as evidence that an edit
  landed — read the file.
- **an arithmetic model of code you did not open.** Added 2026-08-24:
  `PLANNED_WORK.md` costed a saving from a formula over what the
  allocator was documented to do, and the code had done something else
  since M9. One instrumented run — four minutes — turned ~200 KB into
  29 KB and deleted the proposal. If a number was DERIVED, the cheapest
  disproof is to print it.
- **a claim about "what the code does" that names no line.** Added
  2026-08-24: the disk-full write-up described the failure path in four
  numbered steps, and step 3 — "the error is counted and extraction
  continues" — was the one step that was never traced to a line. Thirteen
  extractors contained its refutation. **A described behaviour with no
  file:line beside it is a guess in the shape of a reading**, and the
  cheapest disproof is to make it happen: one run against a full disk.
- **a measurement taken in only the roomiest configuration.** Added
  2026-08-24: "does anything actually fail for want of this memory?" is
  the right question and was asked against a 400 KB cap and a 597,036 B
  machine budget — both of them the System 6 whole-machine case, where
  the application has the RAM to itself. A Macintosh user running
  MultiFinder sets the partition, the declared minimum is 400 KB, and the
  budget there is 130,136 B. **Ask which configuration a "nothing fails"
  result was taken in**, and whether the user can choose a worse one.
- **a cross-validation whose output is quantised.** Added 2026-08-24: the
  `--budget` simulation agreed with the real Mac allocator to 54 bytes while
  its budget was 91 KB wrong, because `target` halves and an error smaller
  than the gap between two rungs changes nothing observable. It surfaced only
  when an unrelated change moved one fixture onto a different rung. **Ask what
  resolution an agreement actually has** before reading it as confirmation of
  the inputs.
- **a limit nobody has ever measured against.** Added 2026-08-24: the
  4 KB call-depth rule was exceeded by 66 %, in code that ships and
  passes, and the only reason anyone looked was that a change was about
  to add 320 bytes to a struct. Measure a limit when something pushes at
  it; that is the one moment the measurement is free.
- **a gap you filed yourself, in the file that holds gaps.** Added
  2026-08-25, hours after the row below it: OPEN_ITEMS.md gained "what is
  missing is a gradeable SPECIMEN" for ARC 7.x's Trimmed, and nobody had
  searched for one. The writer was two minutes away and its own
  distribution was the specimen. **An OPEN_ITEMS entry is a claim and
  takes the same evidence as any other**; "I did not look" is not a
  finding, and a gaps file is the one place where an unexamined claim
  reads as a decision.
- **a search that names the wrong tool.** Added 2026-08-25: the entry
  for ARC methods 0x0a/0x0b said to look for "a `.arc` written by PKARC
  or PKPAK", and PKARC and PKPAK never wrote either — both are PAK's,
  from NoGate Consulting. A search for a file that cannot exist returns
  nothing for as long as anyone runs it, and reads as evidence of
  scarcity. **Check the attribution before hunting the artifact**; one
  search for the FORMAT settled it, and the specimens were two
  downloads away.
- **a scope decision that names a BIGGER version of the problem than the
  one you have.** Added 2026-08-25: "Zip64 is out of scope, and refusing
  it cleanly is the right answer" was written about files larger than
  4 GB, and it read as though it covered everything with Zip64 in the
  name. It did not cover the case that actually occurs — an archive of
  ordinary size with more than 65,535 entries — which was not refused at
  all, cleanly or otherwise: it was silently truncated to 65,535. **When
  a decision refuses a format, ask which of that format's uses it
  actually refuses**, and whether the cheap one hides behind the
  expensive one's name. **The same decision hid a second use two days
  later** (2026-08-27): the per-ENTRY Zip64 escape, which a writer
  reaches for at 2 GB and not at 4.
- **a limit applied by CLAMPING rather than by refusing.** Added
  2026-08-27, after it produced three findings in three days: the zip
  entry count saturating at 65,535, a Zip64 escape read as a literal
  offset, and a 457-byte name cut to 255 and written under the wrong
  filename, all three exiting 0. A clamp leaves a result that is
  internally consistent, so nothing downstream can notice. The answer is
  not always to refuse — a filesystem has always shortened a name it
  cannot take, and the CLI now does the same and numbers the collisions
  — but it is always to TELL somebody. **Where a constant meets data
  from the archive, ask what happens to the archive that exceeds it, and
  who is told.**
- **a harness that ends its runs differently from the harness beside it.**
  Added 2026-08-22: three SpaceSaver runs "measured unchanged" on a machine
  that never booted, because their image had been copied out of a KILLED
  emulator. `arcmac.py` had picked Special ▸ Shut Down for exactly that
  reason since the ARC specimens; nothing compared the two. **Again
  2026-09-27**, and this time the sibling documented the reason: `run.py`
  printed `PASS at {args.mem}`, so a `--emu mv-512Ke` sweep reported *"66/71
  PASS at 4M"*, while `sys30.py` had computed the machine from `--emu` all
  along under a comment saying *"how a 512 KB result gets filed as a 4 MB
  one"*. **Grep for the comment, not for the bug**: the comment is the proof
  somebody understood it once, and it is evidence about every file that does
  NOT have it.
- **a graded case that has never run on this machine, announcing itself
  in every CI run.** Added 2026-09-26: `run_crypt.py` prints *"no `arc`
  ... garbled ARC skipped"* on every `./ci.sh`, and ARC's garble is one
  of the eight ciphers. So that cipher's only graded cases had never
  executed here, which is how a per-entry defect in its retry condition
  survived — `unar` reads an entry this engine refused. The skip line was
  correct, prominent, and read as normal for five weeks, and
  `tools/get_arc.sh` — named in the same file — **fetched the encoder on
  the first try** when somebody finally ran it, after which those three
  cases pass — until the next `./ci.sh`, whose own `make clean` deletes
  `build/arc` again and nothing re-fetches it. **A skip is a hole in the suite that reports itself in
  every run and is never read as one**; ask of a familiar skip what it is
  the ONLY cover for, and whether its own remedy is one command away.
- **a coverage figure with a cause attached, where the cause is in the
  source.** Added 2026-09-26: *"PackIt's XOR and DES 0 in 30, because a
  flipped bit fails its header CRC before a key is derived"* was a
  measurement and an explanation of it, and the explanation was refutable
  by reading thirty lines of `src/fmt_packit.c` — PackIt encrypts the
  entry HEADER along with the payload, so the key is derived before that
  CRC can be computed at all. Re-run with the same instrument the number
  is 17 of 30 (below). **A number and a story travel together, and only
  the number ever gets re-measured** — when the story names a guard, go
  and look at which side of the guard the code is on.

- **a summary that kept the wrong half of a contradiction.** Added
  2026-09-26: a provenance cell said three ciphers had LEFT for their
  standards and, four sentences later, that the same three were *"not yet
  taken"*. Condensing the cell dropped the true half and kept the false one,
  which also destroyed the evidence that there had ever been a disagreement.
  **A cell that contradicts itself is a cross-file contradiction you can find
  without opening the second file** — and the shortening pass is exactly when
  one gets resolved by whichever half the editor read last, so re-read what a
  condensation deleted, not only what it kept.
- **a reproduction whose mechanism is a number, and which does not say to
  check the number.** Added 2026-09-26: the `UncEntryInfo` recipe said to add
  a byte *"anywhere in the struct"* while its own next paragraph said the
  effect was sensitive to the struct's SIZE — and one of the obvious
  placements lands in padding and changes nothing, so following the recipe
  exactly produces a pass that means nothing. **An unexplained effect labelled
  *reproducible* is the claim least likely to be re-run**, because the label
  is what stops anyone doubting it; this one stood ten days on a tree that had
  stopped showing it (below).
- **a source citation naming a document that is not on this machine.**
  Added 2026-09-26: `src/unc_crypt.c`'s AES read *"FIPS-197 as implemented
  in `reference/XADMaster/Crypto/aeskey.c` and `aescrypt.c`"*, and FIPS 197
  was not in `reference/`. Half of that sentence could be checked and half
  could only be believed — so the half that named the STANDARD did no work,
  and the half that named somebody's code was what the provenance table
  counted. Two shedding passes read the line and left it. The rule is
  `tools/fetch_references.sh`-shaped: a document this project cites is a
  document it should be able to open, and a citation split between one it
  has and one it does not is the shape to look for (below).
- **a citation that points at another file's comment.** Added 2026-09-26:
  `src/unc_encinfo.c` sourced Compact Pro's index layout to *"the layout
  comment in `src/fmt_cpt.c`, itself from `XADCompactProParser.m` and
  macutils' `cpt.c`"* — and `fmt_cpt.c`'s comment had said the opposite
  since 2026-09-20, naming the published pages instead. **A second-hand
  citation is the only kind that a correction somewhere else can falsify
  without touching it**, so it survives exactly the pass that should have
  caught it. **The distinction is whether it RESTATES the source**: the
  fifteen `fmt_*_probe.c` files say *"Source: unchanged from fmt_X.c,
  whose provenance comments stand"* and name nothing, so a correction
  over there reaches them for free; this one delegated and then repeated
  what it was delegating to, and only the repetition went stale.
- **two figures in one sentence, and only one of them re-measured.** Added
  2026-09-26: CLAUDE.md's session-start reading was corrected from 7.5k to
  14k tokens *with the date of the new measurement added*, and the next
  three words — the withdrawn-claims archive is *"another 15k"* — were the
  same stale month-old figure, then four times low. The correction proves
  the sentence was read. **A pass that re-measures one number in a sentence
  lends its credibility to every other number in it**, and the newly dated
  one is what stops anybody asking about the rest.
- **a claim that no specimen exists, where every search for one was by NAME.**
  Added 2026-09-26: SpaceSaver adds no extension and AppleLink packages sit in
  folders nobody indexes as archives, so both were invisible to five weeks of
  searching and both fell out of one query against the bytes — Discmaster
  indexes what `file` prints, so eight magic bytes are a search term. Ask what
  a corpus is indexed BY before concluding it does not hold the thing.
  **Extended 2026-10-04:** and when the answer is *nothing* — a zip's extra
  fields are in nobody's index — a RANGE SCAN is the cheap form of the same
  search. 3,029 candidate zips, the first 512 bytes of each, 1.5 MB against
  the 7.3 GB of downloading them, seven hits. One request per candidate,
  reading the one header that settles it.
- **a routine transcribed faithfully and asked a question it does not
  answer.** Added 2026-09-27: `PKG Expand Translator`'s @0x2952 was copied
  correctly and shipped as an AppleLink `.pkg` recogniser for 35 days. It is
  the translator API's COMMAND parser, and the five translators beside it on
  the same disk carry the same routine for Compact Pro, zip, BinHex, uuencode
  and Unix compress. Rule #1 makes you cite a reference; it does not make you
  check WHICH question the cited routine answers. **Run the sibling's copy
  against a format you can already grade** — this one rejects all 108
  Compact Pro fixtures.
- **an item that asks for a SPECIMEN when the question is about the
  FORMAT.** Added 2026-09-28: where a StuffIt archive records its add-on
  module ID was filed as closed only by an archive an emulator session
  would have to write. It was six bytes, and the program that writes
  them had been extracted onto this disk — by our own engine — an hour
  earlier. The item was right that no specimen exists and wrong that the
  header question needed one. **A missing specimen and a missing
  implementation are different gaps**: for "what does this format write
  where", the WRITER is a reference implementation under rule #1, and
  one application is easier to get than one of its archives.
- **a comparator that iterates over what it parsed.** Added 2026-10-05:
  `tools/mutate_now.py --check` decodes a file before and after a
  mutation and reports the blocks that differ. Where the decode produced
  NOTHING it reported zero differences and exited 0 — the same line and
  the same status a clean run prints — and that was every `--delta` run
  for the two weeks the option existed, because the reader had no
  offset-delta search. **Ask
  what a check prints when its subject fails to LOAD**: a pass and an
  empty subject are one output unless something counts the comparisons
  (below).
- **a classifier whose "no" branch is a SKIP.** Added 2026-10-06:
  `unc_uu_line_is_data` answers two questions at once — is this a data
  line, and is this somebody's mail header in mid-stream — so every
  false negative it gains is skipped quietly instead of reported.
  Widening such a test is cheap and narrowing it is unfalsifiable from
  outside, which is the asymmetry to check BEFORE touching one: ask
  what the old test admitted that the new one does not, and whether
  anything would say so (the row below, 2026-10-06).
- **a scan whose corpus has grown since it ran.** Added 2026-10-06:
  *"none of the 47 archives scanned sets bit 5"* was true when it was
  measured on 2026-09-27 and false eight days later, because this project
  extracts installer payloads into the cache for unrelated questions:
  `sitzip.py --payload 55` put 138 files there on 2026-10-04, one of them
  a StuffIt 5 archive with a comment in it, and the ROW'S OWN HARNESS
  indexed that directory the same day to read a `MENU` resource out of a
  file beside it. A scan is a measurement of a corpus at a date, and
  quoting it later turns it into a property. **Re-run it rather than
  re-reading it** — and re-run it first when the alternative in the row
  is an emulator, because a grep over every file on the disk is minutes
  and a boot is not (the row below, 2026-10-06).
- **negative controls derived from a POSITIVE.** Added 2026-10-06: the
  AppleLink probe's lane bends a valid package one test at a time and
  requires `unknown` for each, ten of them, all passing. Every input that
  produces is a package with one thing wrong, so the lane can only ask
  whether each test FIRES — necessity, one test at a time — and nothing
  in it can ask whether the set is sufficient. A file of zeros, which no
  bend of a package can reach, was claimed by the probe throughout.
  **Ask what input a negative lane cannot construct**, and for a
  magic-less probe start with the all-zero file of the right length (the
  row below, 2026-10-06).
- **a sum whose terms are kept current at different rates.** Added
  2026-10-09: the shipped tier model is a measured base plus `OVL_SAVED`,
  and CI re-checked `OVL_SAVED` against the builds on every run while
  nothing checked the base. Each term was right when written; the sum
  drifted 16,888 B and a refused fixture read as a pass. **For every
  derived figure, ask which of its inputs something re-takes** — the one
  nothing does is where the error is (the row below, 2026-10-09).
- **a negative taken before the subject reached the state the claim is
  about.** Added 2026-10-10: 45 memory dumps without a key were read as
  *when* an installer computes it, while the installer had never accepted
  a target and so never got that far. **Before a negative says anything
  about the subject, show the subject was in the state that would have
  produced a positive** (the row below, 2026-10-10).
- **a figure labelled "at least" read as the figure.** Added 2026-10-11:
  `run_tiers.py` reports a refused fixture "short by at least 854", the
  first allocation the budget refused, and it was read as how close the
  fixture was. It needed 401,408 B, 180 KB more. **A floor or a ceiling
  bounds the answer and is not it; binary-search the real figure before
  arguing from one** (the row below, 2026-10-11).
- **a harness that gives every input the same name.** Added 2026-10-11:
  every Macintosh tier opened its fixture as `archive.sit`, so code that
  branches on the name's extension had run on one name, and every plain
  `.zip` failed on the first real machine. **Ask which property of the
  input the harness holds constant**, and look for code that branches on
  it (the row below, 2026-10-11).

Each entry is what was claimed, what disproved it, and what it COST. The cost
line is what makes the next one worth re-testing.

| claim | disproved by | withdrawn |
|---|---|---|
| **"The engine's own ceiling"**: `JPEG Lossy` images over 8,192 pixels high refused as `UNC_ERR_TOOLARGE` — `src/sit_ccube.c`, since the decoder went in on 2026-10-02, with no reason given for the height | **StuffIt Deluxe 2.0.1 compresses and restores a 16 x 8,208 document** under Mini vMac, and this engine, the height cap lifted, matches its restore byte for byte; the width cap stays, since it alone keeps `w * h * channels` inside 32 bits. Found by asking whether "file too large (>2GB)" fit the case. **Cost: a file StuffIt itself extracts was refused as "past this engine's 32-bit reach"**, at 394 KB — a declared ceiling nobody had questioned | 2026-10-15 |
| **"Cmd-. does nothing on a French (AZERTY) keyboard"** — OPEN_ITEMS.md, *What the LC 475 found*, from 2026-10-11, with a *hypothesis* that with Command down that key reports no period | **The maintainer on the LC 475, 2026-10-14**: Cmd-Shift with the period key, which is how a period is typed on AZERTY, cancels like the Cancel button; the first try had been Command and the key without Shift, which is not a period there. **Cost: three days as an open item and a technote queued to be read for it; no code was written** | 2026-10-14 |
| **"Retro68's `OpenDF` and `HOpenDF` return `paramErr` on System 6 and do not fall back: a bug"** — ISSUE.md's headline since 2026-08-01 | **Measured, and Apple's documented contract**: Technote FL 1041 tells the caller to retry with `HOpen` on `paramErr`, and Retro68 issue #53 (closed 2018) settled it that way in `libretro/syscalls.c`. The same note requires `ioMisc` = 0, and the draft's "latent" `ioMisc` point was the real bug: its probe pointed outside a Mac Plus's RAM; one pointing into RAM is written through (DECISIONS.md 2026-10-13, *the bug was the footnote*). **Cost: two and a half months of a ready-to-post report** that would have been closed as a duplicate, with the real defect demoted to its last paragraph | 2026-10-13 |
| **"The 16-colour icons are a hard limit: nothing here can display them"** — MANUAL_TESTS.md §3 and DECISIONS.md 2026-08-24, *the icon*, "measured 2026-08-27" against QEMU's one depth and "Mini vMac is a 1-bit Mac Plus" | **Mini vMac's own `-m II -depth 2`**: a Macintosh II at 16 colours, built from the source `setup.sh` already fetched, on a ROM in the collection it already downloads. It drew `icl4` and a selected icon on 2026-10-11 (`tools/vmac/colouricon.py`). **Cost: six weeks of the item filed as needing hardware, and it took the first real machine's report to make anyone look** — the measurement was of two TOOLS, and the sentence was about the machine (DECISIONS.md 2026-10-11, *the icon that did not darken*) | 2026-10-11 |
| **"The Macintosh application opens zip archives"** — README.md's zip row and every release note since zip came in, implied by the zip fixtures passing every Mini vMac tier | **the maintainer's LC 475**, 2026-10-11: `Reduce.zip` and `Shrink.zip` both refused with *"This archive has more parts"* from a clean launch. Reduced under emulation to the NAME: the same bytes fail as `archive.zip` and pass as `archive.sit`, the only name any tier had used. **Cost: every plain `.zip` opened on a Macintosh failed from 2026-08-14 (`739c6814`) until this fix, through every release in between including v0.39.0, whose headline was a zip method** (DECISIONS.md 2026-10-11, *the zip that was a set of one*) | 2026-10-11 |
| **`run_crypt.py`'s *"sit-des by an unimplemented encryptor"* grades the refusal of an encryptor id this engine does not implement** — the case since 2026-10-02, bent to id 3 | **id 3 is `NewDEx`, implemented the same day, and the copy had no resource fork**: with no `'MKey'` every id is refused identically, so the case passed whatever the id check did. Given its fork and id 5 it fails when the check is removed. **Cost: the third-party-encryptor refusal had no test that could fail for nine days** (DECISIONS.md 2026-10-11, *the constant was a square*) | 2026-10-11 |
| **"A tile row is 7 segments = 21 MCUs = 336 pixels"**, and with it *"`src/sit_ccube.c` decodes `JPEG Lossy` byte-exactly against what 2.0.1 restores"* — FORMATS.md, *What an Optimizer did to the fork*, `src/sit_ccube.c` and `tools/ccube/decode.py`, 2026-09-30 to 2026-10-02, measured on two 256x256 documents of grey content | **33 more documents 2.0.1 optimized and restored itself** (`tools/vmac/sitcombo.py`, 2026-10-11): the engine was right on the 2 the module declined, **silently wrong on 5** — exit 0, *"rebuilt"*, a 512x128 image 134 levels off on average — and refused the other 26. The row is **(w + 39) / 40 segments**, read out of C3a+0x4366; colour is interpolated and converted at CCOD+0xd98's precision, which grey content cannot see; grey, HSL, HSB, multichannel and CMYK are several TIFFs. **Cost: every release from v0.36.0 to v0.39.0 wrote garbage under the document's name for any `JPEG Lossy` entry not 256 pixels wide or not grey, with no checksum to catch it** — the module stores `ffff`. **Why it survived:** a constant that never varied because its input never did — both subjects were the same size and both were pencil on white (DECISIONS.md 2026-10-11, *the constant was a square*) | 2026-10-11 |
| **"Height at +4, width at +6"** of the `JPEG Lossy` header — `tools/ccube/decode.py`, 2026-09-30 | **width at +4**: a 400x300 document says `0190 012c`. **Cost: nothing shipped read it until the rewrite, which got it wrong once and failed every non-square specimen** — the second time in one day a square subject hid an axis | 2026-10-11 |
| **"encrypted by StuffIt's "DES" module, which this engine does not implement — a password will not help"** — `cli/main.c`, ed6d5b5, 2026-10-02 — the same commit that implemented every encryptor it can name | **the line could fire only when the archive's `'MKey'` was missing** — a `.sit` without its resource fork, which is how one sits on a Unix disk. Measured on 2.0.1's own `DES`, `NewDEx` and `DESex` archives with the fork removed. **Cost: nine days of telling the owner of a forkless DES archive that this engine could not read it, when the answer was a copy with its fork.** It says so now (`tools/run_sitcombo.py`, *forkless*) | 2026-10-11 |
| **"`Photoshop 1`, `JPEG Lossy` and the five ciphers are graded only on archives this project made; a file from somebody who has one would close it"** — OPEN_ITEMS.md, written 2026-10-06/07, after DECISIONS.md 2026-10-02 had already said the provenance that matters is the writer's | **asking the writer**: 121 archives from 22 boots of 2.0.1 found the five silent `JPEG Lossy` failures above, where a search of all 196,139 classic StuffIt archives Discmaster lists had found none to try. **Cost: the row was a search with no possible result standing where a loop with one was** — and it contradicted the decision it should have rested on, which is the cheapest smell there is | 2026-10-11 |
| **"The window starts as zeros, which `ozur` gets from a `calloc` rather than from a comment"** — DECISIONS.md, *Reduce comes in*, and the b5c9813 commit, 2026-10-11, filed as the same lesson as ARC's Trimmed window | **APPNOTE.TXT 5.2.5 states it in words**: *"assume that all the data before the start of the output stream is filled with zeros"*. The sentence was written without reading the section the decoder implements. **Cost: none to the engine — the rule was right; a lesson was drawn from a gap that did not exist** | 2026-10-11 |
| **"A copy longer than its distance is corrupt, and the CRCs need that rule"** — `src/unc_reduce.c`, FORMATS.md and DECISIONS.md, b5c9813, 2026-10-11, after `ozur` | **the CRCs settle nothing**: no good entry has such a copy and the 3 that do fail either way, and **5.2.5 permits one** — an overlapping LZ77 copy repeats a run. The decoder now follows the specification, and deark is a reader that refuses a stream the format allows. **Cost: a refusal no real file had hit, and a unit test that asserted it** | 2026-10-11 |
| **`synth-dd-m5.dd` was 14 B from passing System 6.0.8 / 512Ke until Shrink and Reduce went into the codecs image** — reasoned in the session from `run_tiers.py`'s *"short by at least 854"* | **that figure is the first refused allocation, not the need**: the entry needs **401,408 B** against a 221 KB grant. Binary search of `--budget` settled it in one command. **Cost: none committed — caught before it reached a document, but it was the argument offered for redoing the placement, which stands on its own bytes** | 2026-10-11 |
| **"On no Macintosh: an AppleLink `.pkg`"** — this file's Status, 2026-10-09, and the brief written from it | FORMATS.md, *AppleLink packages → Run on a Macintosh*: all fourteen packages had run through the application on System 6.0.8 at 4 MB and 1 MB on 2026-10-05/06, four days before the sentence was written. **Cost: one task item spent re-establishing that a format runs on a Macintosh**, which was then extended to all seven tiers (Status). **Why it survived:** the sentence listed what is not in `sample.txt` and called that "on no Macintosh". Those are different sets, and a run off the sample changes no tally that anything checks | 2026-10-10 |
| **"The 3.5.1 application does not launch here"**, and so *"nothing in this project has ever launched a StuffIt Deluxe application"* — this file's 2026-09-28 entry on `sitcrypt.py`, DECISIONS.md the same day, `tools/vmac/README.md`, and the docstrings of `sitcrypt.py` and `sitopt.py` (*"whether 3.5.1 would use a 2.0 module … that application does not launch here"*) | **it launches by a double-click, and did the same day**: `specimens/sitopt/map351/` (2026-09-28 12:05) shows *About StuffIt Deluxe™…* in the Apple menu and an Archive menu with *Verify* and *Attach Signature*, and `sitopt.launch351`'s own comment says *"A double-click on the icon does"*. The three failures were ⌘O, which goes nowhere on that image. Driven that way on 2026-10-10 it opened Preferences and ran two scripts (`tools/vmac/sitenc351.py`), which settled the question it was blocking: 3.5.1 cannot use an Encryptor module (FORMATS.md, *Where an archive names the module*). **Cost: twelve days of "4 replaced the modules" carried as a hypothesis — load-bearing since `sit_enc_id`, the same morning — and an open "cannot see" in `sitopt.py` that one run answered.** **Why it survived:** the correction was written as a code comment 50 lines below the docstring it contradicted; nothing that reads status reads a function's comment (*a limitation written one paragraph from its own remedy*) | 2026-10-10 |
| **"The Shortcut updater's archive key is folded only when extraction starts"**, and its picker *"a folder navigator whose Open only descends"* — DECISIONS.md 2026-10-09, OPEN_ITEMS.md, `tools/sit_mkey_oracle.py`; labelled a hypothesis | the picker was the updater asking where the installed **Shortcut** is: a Standard File list filtered on `cdev`/`Cut!`, empty because no such file existed, and the code that filters it was decompressed in the same 45 dumps. A 373-byte stand-in with a `cdev` resource gets past it, and the key is then in memory **before any file is written**, from the restart alert onward (DECISIONS.md 2026-10-10, *the installer's own key*). **Cost: a day, and the next attempt aimed at the wrong thing** — timing dumps for "during extraction" when the obstacle was the installer's own target check | 2026-10-10 |
| **"No tier moves: the cost is under the narrowest margin, 16,490 B"** — this file's Status, once per change from 2026-09-26 to 2026-10-09, ten times, and `run_tiers.py --check` agreeing each time | the System 6.0.8 / 512 KB sweep of 2026-10-09: **66/72 where the model said 67**, refusing `a2ps.V4.3.tar.Z` 4,142 B short — the very layer that margin was measured on. `TIERS` had been lowered once (2,024 B, 2026-10-01) while `OVL_SAVED` rose 117,040 → 134,032 with the control build; all three bases re-taken on the machine came back **16,888 B lower**, identical on three machines, and the model then reproduces all three tiers by name. **Cost: one fixture refused on a 512 KB System 6 machine for an unknown part of two weeks with every check green**, and ten tier arguments resting on one number. `TIERS_CONTROL` now fails `--check-saved` when the control moves (DECISIONS.md 2026-10-09, *the base nobody re-took*) | 2026-10-09 |
| **"Removing the depth limit costs 376 B of resident `CODE`, nearly all of it the re-scanning pop that replaced the two fixed arrays"** — `tools/build_mac.sh`'s eager pair, FORMATS.md and a commit message, all written the same hour | a reader asking how removing a check could cost that. It could not. **202 B was `path_longbuf` being OUTLINED** the moment `pop` became a second caller — the function itself plus the inlined copies it cost two others — which caching the pointer in `unc_path_init` put back, leaving both of those SMALLER than before. The remainder was not a cost but a design fault: the walker kept the path TWICE, once as reported and once uncut, each with a per-level stack, and `UNC_PATH_MAXDEPTH` existed to size those stacks. Writing the uncut path straight into the host's `long_name` buffer leaves ONE path with ONE length, deletes `path_full_add` (152 B) outright and makes `unc_path_push` 34 B smaller than before any of this: **−68 B of CODE, −64 B resident**, and the deepest chain falls 3,386 → 3,310 B. **Cost: nothing but the hour, because the number was challenged before it was believed** — three explanations were offered for it and every one was true and none was the cause. A size figure that has an explanation is not the same as a size figure that has been attributed, and `nm --size-sort` per function is what tells them apart | 2026-10-07 |
| **"Components are pushed and popped by LENGTH, never by re-scanning for a separator"** — `src/unc_internal.h`'s description of the path walker since M0, and the reason `UncPath` carried two fixed arrays, which is the reason `UNC_PATH_MAXDEPTH` existed to size them | it was a property, never a reason. A `/` inside a component is swapped to `:` on the way in by this walker's own push and leaf, so every `/` in the buffer is one it wrote and a backward scan is EXACT. Both arrays are gone and the depth limit with them; nesting is now bounded by the path STRING, which is the only limit a Macintosh has either (`tools/vmac/depthtest/`: **250 levels, noErr**). **Cost: the sentence held for seven weeks and nothing in it was false** — what it cost is everything that was built on the constant it justified, which is a rule, a suite, a unit test, two emulator runs and a Macintosh verification, all green, none of which could see that 24 was chosen by nobody. A design note that states WHAT without WHY is a constraint nobody re-opens | 2026-10-07 |
| **"24 levels is the ENGINE's limit and not the destination's, so an entry below it must be refused rather than placed — a host that could hold the real path is why our limit is a failure and an over-long NAME is a notice"** — `include/macextract.h`'s `path_too_deep`, DECISIONS.md 2026-10-07, and the whole justification for the folder-depth rule shipped that day | the premise was right and USELESS, because it was never the question. `tools/vmac/depthtest/` on System 6.0.8: **250 levels created by dirID and read back, noErr** — the probe's own loop cap, not a limit — against 49 by full pathname, where a `Str255` runs out at 254 bytes. HFS took 89 from Linux. **Classic System software has no depth limit at all; the only limit anywhere is the path STRING, which is `UNC_NAME_MAX` already.** So 24 is not a trade-off against the destination, it is three transcriptions of somebody else's constant — and the rule refuses paths every host it has could hold. **Cost: a day's work built on a premise nobody measured**, and the measurement is one probe of 150 lines that could have been written first. It was asked for by a reader in one sentence — *"depth isn't a limitation of hfs?"* — after three suites, two emulator runs and a Macintosh verification had all gone green around it. **A number three files agree on is still not a measurement** | 2026-10-07 |
| **"`name_truncated` 2 means the WHOLE name is in `UncOptions.long_name`"** — `include/macextract.h`'s own contract, and what `cli/main.c` prints as *"the archive's name"* | an archive nested 30 deep whose folder names are 31 characters, so a path passes UNC_NAME_MAX around the eighth level and BOTH limits fire. The engine offered the FLATTENED path as the whole name: the CLI printed `.../D24.../f30.txt` as the archive's name for an entry with six more folders in it, and `name_full_len` was the length of a path that is nobody's. The promise held for every entry that was only too LONG — the pair had never been built. **Cost: none yet, and it was found by a question rather than a suite** — three suites ran over these archives green, because the claim is about what the engine SAYS and a differential suite compares what it WRITES. `name_full_len` is now 0, the documented "the format cannot say", and 2 is never reached; the CLI's cut note moved above the refusal, having said "written as" about a folder it declined to create | 2026-10-07 |
| **"`checkdisk.py` reads the Out volume back — 55/55 byte-exact, both forks, names and FOLDER STRUCTURE included"** — `tools/vmac/README.md`, and the premise of every claim this project makes about a name on a Macintosh | its volume walk returned `[]` past **eight levels**, so it read the folder structure to a depth the sample never tested it at. A correct 24-level volume came back as **32 files MISSING ON THE MAC**, which is what the first emulator run of the folder-depth rule reported about an application that had written every one of them. The claim was true of its subject — nothing in the sample nests past 6 — and the limit was silent, which is the part that matters: a truncating walk cannot say it truncated. **Cost: one misdiagnosis, caught the same hour** by listing the volume by hand, and the question of how long it would have cost somebody who trusted the harness instead. The guard is now at 26 and RAISES; `walk(dirs=True)` adds the folders, without which an assertion about a folder that must not exist is a lookup in a set of file paths and cannot fail | 2026-10-07 |
| **"`unc_path_push` refuses past `UNC_PATH_MAXDEPTH` with NOTHING changed, so a caller that would rather carry on than fail may ignore the result — landing the entries under the parent instead of refusing the archive"** — `src/unc_internal.h`'s own contract, said again in `fmt_now.c` and in `fmt_superdisk.c`, so the same claim was written in three files | a generated archive nested 30 deep (`tools/synth_deep.py`), which no fixture is — the deepest nesting on this disk is 4 (FORMATS.md, *How deep anything actually nests*). **"Under the parent" was true of ONE of the five walks.** The other four pop by a COUNT — a marker record, a level counter, a per-directory entry count — so a refusal that was not counted left the walk shallower than it went down: SuperDisk! and Now Compress misfiled **24 of 91 entries into real folders they were not in**, Now Compress reparenting a whole subtree (`D26` reported inside `D23`), and DiskDoubler's two containers returned `UNC_ERR_CORRUPT` and **threw away 43 of 91 entries**, calling an archive corrupt that was not. Only AppleLink packages, whose pops are depth-ABSOLUTE, did what the contract said. **Cost: nothing yet, because nothing here nests that deep — the price was paid in the claim's own words**, which invited exactly the `(void)` cast that misfiles, and which a reader checking one walk would have confirmed. A contract that says "ignoring this is safe" has to be true of every caller's POP, not of the push | 2026-10-07 |
| **"No archive on this machine sets bit 5 of StuffIt 5's archive flag byte — 47 scanned — so nothing here can grade it"** — OPEN_ITEMS.md's `fmt_sit5.c` row, `src/fmt_sit5.c`'s own comment and `tools/derive_sit5crypt.py`'s, all since 2026-09-27 | **`Tutorial Files/Sample Archive.sit`, which StuffIt Deluxe 5.5 ships inside its own installer**, reads `0x30` and carries a 204-byte archive comment — so bit 5 marks a COMMENT and its block is four bytes, the comment's length and its style scrap's, with 100 + 14 + 4 + 204 + 22 = 344 exactly the `firstoffs` the header declares and blocks of 0, 2, 6 and 8 bytes checked and required to miss. `lsar` prints the same text as *Archive comment*, and Aladdin's own SDK declares the comment as a text handle AND a style handle, which is the pair of lengths (FORMATS.md, *StuffIt 5's archive flag byte, and what bit 5 is*). **Cost: two days of the last StuffIt 5 item filed as needing an emulator**, and a morning's route aimed at WRITING such an archive — the scan ran on 2026-09-27, `sitzip.py --payload 55` put 138 files including that archive into the cache on 2026-10-04 for an unrelated zip question, and on 2026-10-06 the row's OWN harness opened a resource fork out of that same payload, one directory up from the archive, and concluded the row needed a guest. **Why it survived:** a scan is a measurement of a corpus at a date, and quoting it later turns it into a property of the format; this one was true when it was written. Re-run a scan rather than re-reading it, and re-run it first when the row's named route is a boot (DECISIONS.md 2026-10-06, *the archive that came with the application*) | 2026-10-06 |
| **"The only software that can set bit 5 is StuffIt Deluxe 5.0.1's comment UI, which Mac OS 9.2 refuses to run"** — OPEN_ITEMS.md's route column for `fmt_sit5.c`'s bit 5, since 2026-09-27, and the whole reason that row wanted a Mac OS 8.6 boot | **StuffIt Deluxe 5.5 and 7.0.3 Classic both have one, and both are already assembled into a Mac OS 9 System Folder on this disk.** `MENU` 131 (5.5) and `MENU` 132 (7.0.3) are `Archive` and their last items are `Edit Comment...`; 5.5's `STR# 30000` #13 describes a clickable comments AREA in the archive window, *"the comments attached to this archive"*; and both `aete`s declare `comment` AND `password` as properties of the archive, 7.0.3's `stuff` event taking a password directly. All of it is read out of the resource forks `sitzip.py` extracted on 2026-10-04 for an unrelated zip question — `sitcomment.py --read`, no emulator. **Cost: nine days of the last StuffIt 5 item filed as blocked on an operating system, and before that a file-system theory that cost ninety minutes to disprove** — both downstream of one sentence about which PROGRAMS have a feature, true when it was written and never re-read after two more boxes arrived. The menu items are a separate measurement and they are dead: neither has a Command key, and a keyless menu item is not selectable on either guest (*What the pointer cannot select*, `tools/vmac/README.md`). **And 5.5's application launches on Mac OS 9.2** — `sitcomment.py --probe`, 2026-10-06, its own menu bar with `Archive` on it — so what 9.2 refuses is 5.0.1 specifically; what stops 5.5 is `STR# 269` #30, *"has not been properly installed"*, against an installation this project assembled rather than installed, which is a wall and not a nag because dismissing it quits the application. **Why it survived:** the sentence names an application rather than a capability, so it reads as a fact about StuffIt rather than as the result of a search — this list's *route column that asserts an absence in the same sentence as the artefact it wants*, for the fourth time in eleven days (DECISIONS.md 2026-10-06, *the comment UI that was two boxes later*) | 2026-10-06 |
| **"Whether `qemu-system-ppc -M mac99` boots Mac OS 8.6 is unmeasured, and the media stopped being the blocker"** — `tools/vmac/README.md` and OPEN_ITEMS.md, 2026-10-06, the first of three steps that row listed | **It does not boot, and the blocker was never the media.** With the volume blessed (`drFndrInfo[0]` is 0 on the image; its System Folder is dir 989), Apple-partitioned with `mkapmdisk.clone_head`, and the ROM's own Forth platform test satisfied — `System Folder:Mac OS ROM`'s `<BOOT-SCRIPT>` accepts `iMac,1`, `powermac1,1` or `powerbook1,1` and QEMU's `mac99` is `PowerMac3,1` — the ROM's ELF runs and **Mac OS itself** stops: `MacOS: Boot Failure! (0xF3C481F6)`, `MacOS: "/rtas" not found!`. OpenBIOS implements no `/rtas`; Mac OS 9's ROM declares `MacRISC` and requires none, which is why 9.2 has booted here since August. **Cost: six boots, about an hour** — and the saving is larger than the cost, because "8.6 does not boot" invites fetching the 1.65 GB pre-installed image and the 8.5 CD sitting on the same host, where a firmware requirement says all three would fail the same way. **Why it survived:** nothing had tried it; the row said so and said it in the right order. What the row did not say is that step 1 had a cause worth reading whether it passed or failed (DECISIONS.md 2026-10-06, *the platform the ROM would not admit to*) | 2026-10-06 |
| **"Implode would cost ~1.5–2 KB of `CODE`, estimated, not measured, against 12,460 B of headroom at the tightest tier"** — OPEN_ITEMS.md Part 1's Implode row, the only number the decision it hands the maintainer was offered | **The estimate may stand; the wall is the wrong one, and for the second time today it is a figure from before the overlays.** 12,460 B is the *resident* margin of `derived-LHA_Expander_1.0.3.sea` — `tools/check_app_size.py` says in its own docstring that the bundle is NOT what it watches — and a DiskDoubler archive releases `ovl_exo` before it allocates anything. `src/fmt_exo.c` is excluded from resident `ENGINE_SRC` and built into that image by `mac/CMakeLists.txt`, so an Implode decoder reached from it is not resident in what ships. The second half, *"a removal delta can be built and an addition cannot"*, is false as practice: **the nearest comparable addition was measured on 2026-10-01** — zip's four Macintosh extra fields, +2,024 B into `ovl_exo` (27,252 → 29,252 B), +0 B of resident `CODE` and +0 of A5 in the shipped build, no tier tally moved in either lane — and three more additions of that order are on record with their deltas (FORMATS.md, *Three configurations, one tree*). **Cost: nothing built, because the decision was never taken** — and the error ran in the cautious direction, so the verdict *it fits* is unchanged and better supported. **Both halves settled 2026-10-07 by building it**: 1,856 B of `CODE`, which is the estimate's own range, and all of it in the resident control; the shipped build moved 0 and 0, and the image moved 1,924 B — within 100 B of the 2,024 the comparable addition cost (FORMATS.md, *Implode*). What it cost was the decision's quality: a maintainer reading that row priced a feature against a budget it does not draw on. **Why it survived:** the 12,460 B figure is real, bisected to the byte, and load-bearing for `check_app_size.py`'s threshold, so quoting it reads as rigour. The word that makes it the wrong wall is "resident", and it is in a different file's section (DECISIONS.md 2026-10-06, *the gate that had never fired*) | 2026-10-06 |
| **"A Macintosh 128K is out for a measured second reason: its largest single block is 63,744 B against 142,152 B of `CODE`"** — OPEN_ITEMS.md Part 1, MANUAL_TESTS.md §6 and this file's own 2026-09-01 row, carried verbatim from the day it was measured | **This project cut the quoted term to a third itself, on 2026-09-25, and no file that quoted it moved.** In v0.37.0's own resource map `CODE` 2 is **48,888 B** and the nine `CODE` resources total 55,888 B, so the segment the Segment Loader refused now fits inside 63,744 B with room to spare. The VERDICT is unchanged and now rests on a different number: 55,888 B of `CODE` resources plus the 19,052 B A5 world is 74,940 B against `ApplLimit − ApplZone` = 78,568 B, and the eager loader then asks for the `'OVLY'` bundle as one 155,916 B block — so the machine is short by **3,628 B**, not by the factor of about two three files claimed. **Cost: nothing on hardware, because the verdict held** — but the number was load-bearing for the one question a reader asks of it, whether a per-format build could fit, and *A Macintosh 128K* prices that on the same page at ~41 KB of fixed cost. Found by reading *Overlays* and *A Macintosh 128K* in one sitting: two sections of ONE file disagreeing by a factor of three, which is this list's second mechanism one file in (DECISIONS.md 2026-10-06, *the wall the overlays had already moved*) | 2026-10-06 |
| **"Each pushed range is the smaller half, so the depth cannot pass log2(nsyms); 16 covers 65,536 symbols against this file's 308"** — `src/sit14.c`, `sit14_sort`, written 2026-10-03 | **Both halves are true and the conclusion does not follow.** The reference RECURSES into the smaller half and returns before carrying on, so its nesting halves; the transcription DEFERS it and loops on the larger, so pending ranges accumulate one per split. A complete code whose lengths ascend — four at every length from 3 to 15 — asks for **20** of the 16, and the four that did not fit were dropped with no error: the lengths come out sorted, the ORDER does not, and two symbols get each other's code. **Cost: a VALID 112-byte entry decoded wrong from its 26th byte for three days**, found when the new wrap seed's 1,000th sanitizer case tripped UBSan on the negative shift the same unsorted tail produces — and only the entry's own CRC-16 would ever have said so, since nothing else here writes that tree shape. Fixed by deferring the larger half (7 pending ranges at nsyms=308, measured over 4,000 vectors) and by making a full stack an error; `ci.sh` variant 1d proves the guard fires. **Why it survived:** the sentence is about the SIZE of what is pushed and the bound it claims is about HOW MANY are pending, and a transcription that changes recursion into a stack changes the second without touching the first. The two real payloads — 9.3 million symbols between them — are byte-exact against `unar` on the defective build, so no amount of real data would have found this (DECISIONS.md 2026-10-06, *the sort that dropped what it could not hold*) | 2026-10-06 |
| **"`sit14_flush`'s window wrap wants a fork past 256 KB, where the synthetic seed's largest is 17,799 B — the window is sized to the fork, so nothing smaller can wrap it. Reached only by the two real payloads, which no committed suite can touch"** — OPEN_ITEMS.md, *The decoder paths nothing has fuzzed*, and TESTING.md, *Fuzzing*, written 2026-10-05 | **458 bytes of stream.** `tools/synth_sit14.py` is an encoder that takes an arbitrary symbol script, and seventeen maximum matches decode to **278,896 B** — so `synth_sit14.py --wrap` is a seed that wraps, `sit14_flush` goes 55.6 → **100 %** of its lines at seeds 11, 12 and 13 alike, and the branch runs 202–212 times per 400 stream cases (TESTING.md, *Fuzzing*). 17,799 B is the largest fork the four hand-written shapes happen to decode to; it was quoted as what the encoder can write. **Cost: the one branch that handles the full 256 KB window shipped on 2026-10-03 with nothing committed grading it, and was filed a day later as unreachable in principle** — which is the state a row is in when nobody looks at it again. **Why it survived:** the sentence runs two sizes together, the FILE and the FORK, and a compressor exists precisely because those differ — the inference is about forks and the obstacle it was read as is about seeds. It is also *a tolerance that rests on our own output*: 17,799 B came out of this project's own case list, which is four lines anyone can edit (DECISIONS.md 2026-10-06, *the fork that was cheaper than the file*) | 2026-10-06 |
| **"nothing else restates the scan for a second document in one input: deark's binhex reads ONE document and mpack's handling is a separator inside one part"** — OPEN_ITEMS.md, re-checked 2026-10-05 | **DeHQX 2.0.1 states it in its own documentation**, and DeHQX is `fixtures/dehqx-201.hqx`, in the corpus since M1, written by Peter N Lewis — the author of the BinHex 4.0 Definition this file was transcribed from: "When it comes to the end of the HQX source, if [sic] checks for the terminating colon, and then continues scanning the file for the next '(This file...'". **Cost: a per-entry failure nobody had seen.** The same two paragraphs document the part separator a cut posting resumes at — a line that is exactly `---` — and all three of those characters are in the BinHex alphabet, so this engine read them as two bytes of data and the fork's CRC objected (measured 2026-10-06; `hexbin` reads such a file). **Why it survived:** the search asked the other UNARCHIVERS, and these rules are about a convention of posted text, so the sources are the programs that posted it. The mechanism for that was already in this list too — *a reader and a writer for the same format are different gaps*, 2026-09-28 — and the row named one reader per cell (DECISIONS.md 2026-10-06, *the separator that was in the alphabet*) | 2026-10-06 |
| **"nothing else implements UUTool's MU layout"** — OPEN_ITEMS.md, *What is still somebody else's and could stop being*, re-checked 2026-10-05 at deark and mpack | **UUTool implements it, and UUTool is a corpus fixture** (`uu-tool-24.hqx`, since M13). It states the layout in its own manual, in the section headers its `DATA` 0 holds as whole literals, and in two 64-byte encode tables; UUParser 1.72, a different author and also a fixture, carries both tables too (`tools/derive_mu.py`, 21 witnesses across three versions). **Cost: the engine could not read a line of what that program writes by DEFAULT.** Its `HEXA` 129 "UNIX" table moves the low values up past 0x5f so no value encodes to a space, and the gate in front of the decoder required 0x20..0x60, so every file UUTool wrote without "use original coding" sniffed as not-a-uu-file — from M13 to 2026-10-06, green suite throughout, with the two tables sitting in a resource fork in `fixtures/` the whole time. **Why it survived:** the search for a second implementation asked only the READERS, and the mechanism that says to ask the writer was already in this list, added 2026-09-28, eight days above the row it was about. Also: the generator chose the alphabet — `binascii` writes the standard one and `hexbin`'s mask reads anything — so two independent implementations agreed byte-exact about a shape neither had ever been handed (DECISIONS.md 2026-10-06, *the alphabet nothing here had seen*) | 2026-10-06 |
| **"method 14's decoder, under `fuzz.py`: nothing, except a bigger run"** — OPEN_ITEMS.md, *The decoder paths nothing has fuzzed*, written 2026-10-03 | **Ten of its eleven functions are entered at 3,000 cases**, at seeds 11 and 12 alike: the seed is 1 of ~958 and is drawn about 2.3 times in a run that long, so the 1,500-case run the row was written from is the one that reached none of it. What was actually missing was the nested-tree reader — `sit14_lengths_coded`, 0 % at both seeds — and any reliability at all, a draw being what decided it. **Cost: small, and in the cautious direction** — the row asked for the right change and got it (TESTING.md, *Fuzzing*) — but it was filed as structure in a file whose own instrument warns, in its docstring, that a family at zero in a small run may be sampling. **Why it survived:** the claim was written without the case count it was measured at. A reach figure is a measurement OF a case count, and quoting one without it turns a sample into a property | 2026-10-05 |
| **`tools/fuzz_cover.py` "covers every decoder at once, because for a decoder 'was this entered' is what gcov reports"** — the tool's own docstring and TESTING.md, *Fuzzing*, since 2026-09-27 | **Two of its twelve rows could not report.** The BinHex row's regex named `hqx_`/`binhex_` where the functions are `bh_`, so it matched nothing — and the tool printed no line for an empty family, so twelve functions read as absent rather than as unmeasured. And `^sit\d*_` swallowed method 14's eleven into a "StuffIt classic" of 34, where a wholly unfuzzed decoder cannot show as one; that is how the row above came to be believed. **Cost: eight days of BinHex unmeasured — 12 of 12 entered once the row could print — and the whole life of the method 14 row.** **Why it survived:** a family missing from a list of families reads as a family that does not exist. It is the *check whose subject failed to load* again, in a tool rather than a comparator: an empty row now says so, and the functions in NO row are counted | 2026-10-05 |
| **"`now_find_delta` wants an archive whose block table carries a delta. Neither corpus archive has one"** — OPEN_ITEMS.md, *The decoder paths nothing has fuzzed*, written 2026-09-27 | **`tools/synth_now.py` has written two since M12** — `synth-now-delta` and `synth-now-delta-small` — and `tools/run_now.py` grades both against `unar` on every `ci.sh` run. Both halves of the claim are true and neither was the gap: the fuzzer's Now Compress pool is `corpus()`, so what was missing was one line of `fuzz.py` (DECISIONS.md 2026-10-05). **Cost: the last unfuzzed function in the family stayed unfuzzed for eight days**, with the file it asked for in the same repository and in the same suite — and the fix, once found, moved Now Compress to 13 of 13 entered at two seeds. **Why it survived:** the sentence names the CORPUS, which is where a fuzzer's seeds come from, so it reads as a statement about what exists. When an item names what it wants, grep for the name | 2026-10-05 |
| **`tools/mutate_now.py --check` "decodes the result with `tools/derive_now.py` to show that OUR reader still gets the original bytes out — which is what says the file is well formed and the question is a fair one"** — that tool's own docstring, 2026-09-21 | **On every `--delta` run it compared nothing.** `derive_now` had no offset-delta search, so a rebased table read as no table at all, and `check()` zipped two empty lists and printed `0 block(s) read the same, 0 changed` with exit 0. **Cost: nothing downstream** — the delta ladder's verdicts came from the archive's own self-extractor on an emulated Mac (DECISIONS.md 2026-09-21) and the engine's search is graded by `unar` — **but it is why the item above stayed open**: the one reader that could have said *I cannot read this* said *pass* instead. Compared-nothing is a failure now, and planting a `table_delta` that returns 0 turns the run red | 2026-10-05 |
| **ZipIt's `0x2605` premise — the field is set when and only when the data is MacBinary — "is APPNOTE.TXT 4.6.4's word and nothing this machine can check"** — OPEN_ITEMS.md, written 2026-10-01 with the three fields | **nine archives ZipIt itself wrote, and it holds in both directions**: all 16 `0x2605` entries with a reachable payload decode to a MacBinary stream, and not one of the 86 `0x2705` entries does. The field's own type and creator equal the MacBinary header's in all 16 (FORMATS.md, *ZipIt's own archives*). **Cost: three days of a field read on faith**, and a row in OPEN_ITEMS.md that named its own blind spot and was believed anyway. **Why it survived:** the sentence beside it — "ZipIt's archives are plain `.zip`, invisible to a search by name" — is TRUE, and it was read as an impossibility rather than as the one thing to route around | 2026-10-04 |
| **"ZipIt was shareware and its archives are plain `.zip`: invisible to a search by name"** — OPEN_ITEMS.md, 2026-10-01, offered as the reason no real one could be found | **true of the archives and false of the ARCHIVERS.** A ZipIt self-extractor is a code stub with the zip behind it, and the identifier Discmaster runs names that stub: `format=zipIt` returns 69 files, three of them archives other people made. And the plain ones are reachable too, just not by any index — `format=zip` over the 40 items `fetch_specimens.py` already cites gives 3,029 zips, and an HTTP `Range` request for the first 512 bytes of each found **seven carrying a ZipIt field for 1.5 MB of traffic**, against 7.3 GB to download them. **Cost: the whole item**, and it had been written the same week the *waiting on a file* section emptied for exactly this reason. **Why it survived:** the 2026-09-26 lesson was recorded as *search by magic, not by name* — and the magic here is not indexed either. **A range scan is the cheap form of searching by content when nobody has indexed the content**: one request per candidate, reading the one header that settles it | 2026-10-04 |
| **PKZIP 1.x Implode is out of scope because it is "not a Macintosh method: it is PKZIP 1.x's, and the two corpus archives carrying it are PC software"** — OPEN_ITEMS.md, Part 1, the last surviving half of that row's premise after 2026-09-22 | **`Psycho!v1.0ß1.zip`, written by ZipIt in February 1994** — three MacBinary entries with resource forks, every one Implode, and its own archive comment says which program wrote it (FORMATS.md, *ZipIt's own archives*). Found in the same sweep as the row above. **Cost: PRICED 2026-10-07, when the maintainer took the decision and the method landed — 1,856 B of `CODE` in a build nothing ships, 1,924 B of `'OVLY'` image, +0 B resident, and no tier tally moved** (FORMATS.md, *Implode*). The capability it displaced is three Macintosh entries with resource forks, extracted byte-exact, and two of the format's four parameter combinations that no committed fixture reaches. And the CLI's refusal for those three entries ended *"if you can share this file, please open an issue — a specimen is exactly what is needed to add support"*, so the program had been asking for this file for months while the file was in an index it was already searching. **Why it survived:** the claim was about the CORPUS ("the two corpus archives carrying it are PC software") and was read as being about the format. Counting the archives you have cannot tell you what a format was used for | 2026-10-04 |
| **StuffIt 2.x's `DES` and `NewDE` cannot be read here, and the report should say "which nothing implements — no password will open it"** — written 2026-10-02 when the first archives from them arrived and `src/fmt_sit.c` refused them by name | **both are decrypted, and the key derivation was never the problem.** This engine's own `'MKey'` verifier PASSED on a 2.0.1 archive with the right password — which says the archive key, the `'MKey'` and its self-check were already identical to 3.5's — so only the fork transform could differ. A sweep of 32 file-key variants against 8 transforms, scored against a known plaintext, found both on the first run that included standard DES: `DES` is standard DES in **CBC**, `NewDE` is **StuffItDES in CBC**, and 3.5's is the same cipher through the 8-byte feedback. Both primitives were already in `src/unc_crypt.c` — one for PackIt, one for StuffIt — so the work was two cipher kinds and a three-way choice on the header. `NewDEx` (3) and `DESex` (64) are those same two ciphers as plug-ins, measured the same way. **Cost: a few hours, and the message was never released** — but it is the SECOND time in one day that a refusal claimed the world could not do something when it meant that we could not, which is now a named smell | 2026-10-02 |
| **A SCRIPT cannot make an encrypted StuffIt 2.0 archive: the menu's setting does not reach a scripted `Stuff`, and STR# 257's `newde` and `des` "name no installed encryptor"** — written 2026-10-02 into `tools/vmac/README.md` and FORMATS.md, the first half measured and the second ASSUMED from the Encryptors folder holding only `PassLock` | **both words work, and they are built into the application.** A script asking for `Stuff … with fast des` and `… with fast newde` produced two encrypted archives (`sitopt.py --psdes`), each prompting for its password, with a plain control from the same boot: `DES` writes method byte 0x82 and differs from the control in 284 of 286 compressed bytes, `NewDE` writes **0x12** and differs in 285. So the menu's `NewDE™`/`DES` items are the application's own ciphers and `Custom Encryption…` is the plug-in route, which is what the menu's shape said all along. **Cost: a day of OPEN_ITEMS saying the combination needed the GUI, and a `--psencgui` phase written to drive it** — the phase is still what `PassLock` needs, so it was not wasted, but the question could have been settled by one scripted run at any point | 2026-10-02 |
| **An entry StuffIt 2.x password-protected cannot be read, and the engine should say "no password will open it"** — written 2026-10-02, in `cli/main.c`'s refusal, when the first `PassLock` archive arrived and was reported as corrupt | **the module enciphers nothing.** Two archives 2.0.1 wrote with `PassLock` armed, against the unprotected archives of the same subjects: every compressed byte of both forks is IDENTICAL — 22,097 of an optimized stored fork, 286 of an LZW text one, 473 and 86 of the resource forks — and the module appends sixteen bytes of key material and the method's padding. So the password protects nothing that is in the file, and the engine extracts such an entry without one — silently, since there is nothing a user can act on. Confirmed four ways on 2026-10-02: the byte diffs, the entry's own CRC over what comes out, and the module's own `COMP` and `DCMP`, whose data paths push the buffer pointer and never dereference it. **Cost: nothing yet — the claim was hours old** — but it was heading for a README line telling users their data was unrecoverable when it was in the clear, which is the kind of statement a project is held to. What found it was asking "what if the user HAS the password?" of a refusal that had just been written, rather than of the format | 2026-10-02 |
| **`CCOD`+0x3826 applies a round-toward-zero correction in the output stage, and the exact output mysteriously does not want it** — written 2026-10-01 from a symbolic trace of that tail, and recorded in FORMATS.md, `src/sit_ccube.c` and `tools/ccube/decode.py` as *measured and unexplained* | **a second subject, and the branch is taken thousands of times.** The first specimen was a flat drawing where the correction changed only 2,127 of 196,608 output bytes, 709 of them luma — few enough that "the image never takes that path" survived as an explanation. A dense grid drawn in Photoshop 1.0.7 (`sitopt.py --psdoc --drawing grid`) puts it on **9,645** bytes, and `decode.py --rtz` is wrong on every one while the plain decoder is **byte-exact on both subjects** — 0 of 196,608 bytes differing, twice. So the output stage does not round toward zero and the attribution of that idiom to +0x3826 was a misreading of the disassembly, not a property of the format. **Cost: two days of a decoder shipping with a comment that invited the next reader to 'fix' it to match the asm** — the comment was the defect, since the code was right throughout. What it did NOT cost is the thing worth noticing: the claim was labelled *unexplained* rather than *measured*, so nothing was built on it | 2026-10-02 |
| **`src/unc_crypt.c`'s AES is FIPS-197 as implemented in Gladman's `Crypto/aeskey.c` and `aescrypt.c`** — written when the cipher was added on 2026-08-23 and never re-read, and the reason OPEN_ITEMS.md's provenance table counted five XADMaster files in that one source file | **The code is the standard's and is nothing like Gladman's.** With FIPS 197 fetched, `aes_setkey` is section 5.2's Fig. 11 line for line, the round is section 5.1's Fig. 5, `xtime` is section 4.2.1 and the merged SubBytes/ShiftRows is the standard's own property in section 5.3.5. Gladman's is a 32-bit word machine — one function per key size, macro-unrolled, Rcon as a TABLE, the schedule as a running four-word state, four 1 KB round tables — and this file has none of those. **Cost: an attribution this engine did not owe, carried for 34 days through the two passes that re-cited everything around it — 2026-09-19 and 2026-09-23, the second of which took this file from twelve XADMaster citations to five — each reading the AES line as already sourced**; and a provenance row that priced a rewrite which did not need writing. Re-citing it moved nothing on any axis: the crypt `OVLY` image is byte-identical at 9,800 B, resident `CODE` and A5 unchanged at 53,332 B and 18,988 B (DECISIONS.md 2026-09-26, *the AES that was never Gladman's*) | 2026-09-26 |
| **Three XADMaster ciphers in `unc_crypt.c` are replaceable and not yet taken — zip crypt, the WinZip AES derivation, RC4** — OPEN_ITEMS.md's provenance table, as the one piece of shedding work still on offer there | **All three left on 2026-09-23**, in `5d14d02`, the commit that took that row from twelve XADMaster files to five: SHA-1 for RFC 3174, HMAC for RFC 2104, PBKDF2 — which IS the WinZip AES derivation — for RFC 2898 §5.2, the zip cipher for APPNOTE.TXT §6.1 and RC4 for draft-kaukonen-cipher-arcfour-03, each checked against the document before the citation moved. `src/unc_crypt.c`'s own header has said so since that commit. The cell carried both halves — *left* and *not yet taken* — from 2026-09-23, and the 2026-09-26 condensation dropped the half that was true. **Cost: the only on-machine item that table offered, kept on the list for three days after it was done** — and a second error in the same cell, which began claiming FIPS 180 and FIPS 197 were *fetched* where the text it replaced had only named them; neither is on this machine, and the AES key expansion is the one thing in the row that fetching one WOULD make takeable | 2026-09-26 |
| **Adding a field to `UncEntryInfo` makes two fixtures roughly twenty times slower on the Macintosh** — BLOCKERS.md carried it as *"unexplained, reproducible, and load-bearing for whoever edits `UncEntryInfo`"* from 2026-09-25, with a three-command reproduction and the warning that the next person to touch that struct would otherwise spend the day it cost. Labelled a hypothesis, correctly; the sensitivity was said to be to the struct's SIZE, since `uint32_t` (+4) passed where `uint8_t` and `uint16_t` (+2) hung | **The reproduction passes on v0.33.0, six runs.** With the field at the end of the struct and `sizeof(UncEntryInfo)` measured at **302** against the clean tree's 300 — the documented +2 — `derived-LHA_Expander_1.0.3.sea` and `derived-Terrainman_2.0__.sea` each extract in **5.1 s and PASS** at 1 MB and at 4 MB, and the resident control build (`UNC_OVL_RESIDENT`) does the same at 1 MB. The field was in the binary: the autotest `CODE` is 114,544 B with it against 114,428 B without. **And the recipe was defective in one measured way**: it says to add the field *"anywhere in the struct"*, but `uint8_t` placed before `method_data` lands in existing padding and `sizeof` stays **300** — two of these runs were that, and proved nothing until the size was checked. A reproduction whose whole mechanism is a size has to assert the size. What produced the original timeouts is not established and no longer happens here; the tree has since lost DART, gained the overlays and moved 8 KB of code. **Cost: a day when it was found, and a warning carried for ten days on a tree that had stopped showing it** (DECISIONS.md 2026-09-26, *the reproduction that had stopped reproducing*) | 2026-09-26 |
| **PackIt's XOR and DES are reached by 0 of 30 fuzz mutants, because a flipped bit fails its header CRC before a key is derived** — TESTING.md (*Fuzzing*) and OPEN_ITEMS.md since 2026-09-23, where it also specified the remedy: *"for PackIt a mutation that repairs the header CRC afterwards"* | **17 of 30, mutating exactly the way that measurement did** — `tools/fuzz_reach.py --untargeted`, seed 11, which reproduces the same run's `sit-des` 19 and `sit5-rc4` 21 to the case, so the instrument is not what moved. And the stated cause is impossible in this format: PackIt encrypts the entry HEADER along with the payload, so `src/fmt_packit.c` derives the key in the PMa5/PMa6 arm and checks that CRC further down the same walk — decrypt, then check. What does stand in front of the cipher is the FIRST, unencrypted entry's header CRC: in a faulted build, one flipped bit at offset 20 or at 60 stops the walk before the encrypted entries and one at 200 does not, which is 100 bytes of 890 rather than all of them. How the 0 was obtained is not recoverable from the write-up. **Cost: a remedy specified for a problem that does not exist**, carried as one of two things that would close the item, and two ciphers recorded as unreachable while they were in fact reached at nearly the rate of the two that counted as reached (DECISIONS.md 2026-09-26, *the guard that was on the other side*) | 2026-09-26 |
| **The 1 MB Mac Plus budget is 647,204 B** — FORMATS.md, *Budget*, stated as arithmetic: 648,100 B measured on 2026-08-31, less the 896 B the UTF-8 fold added to `CODE` and A5 | **The machine says 648,282 B**, so the arithmetic moved AWAY from the answer. The formula and the subtraction were both right; the base was three weeks and six rewritten formats old, and the decoder work had taken more off the application than the fold put on. The two 512 KB constants beside it had drifted **21,666 B** each, in the same direction and for the same reason, and with all three re-taken `run_tiers.py` reproduces **all three tiers fixture for fixture** — including System 6.0.8 / 512 KB, which had never matched and whose one-fixture disagreement TESTING.md had filed under fragmentation. **Cost: a stale predictor that was wrong about four fixtures on the tier it could not check**, and half a day in which the floor figure was less accurate than the one it replaced. *A constant derived from a measurement is only as current as the measurement* — and subtracting from a stale one looks like maintenance (DECISIONS.md 2026-09-22, *the fold, on a Macintosh*) | 2026-09-22 |
| **What would close the `DDAR` `0x20` row is a 1.x or 2.x DiskDoubler, neither of which is reachable from here** — OPEN_ITEMS.md's `fmt_dd.c` row and `docs/formats/diskdoubler-container.md`, *What would close it* | **A 2.x DiskDoubler could not have written a `DDAR` record of any flags, so finding one would have settled nothing.** `DDExpand 2.03a`'s `BNDL` declares the DiskDoubler file types it opens — `DD01`, `DDDA`, `DD02`, `DDTM`, `DDSP` — and `DDAR` is not among them, nor does the string occur anywhere in its 65,212-byte resource fork; DDExpand 3.1 declares those five plus `DDAR`, `DDTD`, `DDCR` and `DDF0`–`DDF5`, and holds the literal nine times. Both are on the Macintosh Garden page this project already fetches 3.7 from, and so is **DiskDoubler ß05, 1990**, the oldest DiskDoubler anywhere reachable — whose Finder menu is `Compress Selection;Expand Selection` and which cannot write an archive either. *A search that names the wrong tool*, one format over: the row named a VERSION rather than a shape, on the strength of which version XADMaster's author owned. **Cost: nothing yet, and only because no 2.x was available to spend a boot on** (DECISIONS.md 2026-09-22, *the version that could not have written it*) | 2026-09-22 |
| **The two harnesses that grade Mac output against the oracle manifests are `check_mac_sink.py` and `tools/vmac/run.py`, so a StuffIt 5 fixture with a non-ASCII name would read a correct fold as a defect in both** — TESTING.md, *The Macintosh shell's names*, written with the fold on 2026-09-22 | **`run.py` cannot see a name at all.** Its verdict is the on-screen grid — a file count, two summed CRC-32s and two summed lengths — and a summed CRC carries no name, which is the blind spot `checkdisk.py` was written for in the first place. The harness that would have failed is `checkdisk.py`, which the sentence did not name: with the fold disabled it reports three MISSING and three UNEXPECTED on `derived-800saywhat301j.sit`, and run.py passes it either way. **Cost: nothing, by one day** — the sentence would have sent whoever added the fixture to teach the harness that cannot see the problem and leave the one that can (DECISIONS.md 2026-09-22, *the fold, on a Macintosh*) | 2026-09-22 |
| **A member deark wrote at all has both forks, so a fork with no file on disk is one deark read as EMPTY** — which is the assertion `make_manifests.py` lets the third oracle make on its own, and the comment stating it (TESTING.md, *A third oracle*) | **deark writes a member's resource-fork sidecar, declines its data fork, and writes no data file.** `derived-BitMap11.sit`'s `BitMapHelp.index` is StuffIt method 8, which deark does not implement: it prints `Unsupported compression method: 8 (MW)` and the absence read as a 0-byte fork. **Cost: nothing yet, which is the only cheap time to find one** — no manifest records a false empty, because the gap-filling path had never been offered such a fork. Found 2026-09-22 by `tools/sweep_deark.py`, whose whole purpose is asking the oracle where nothing was open (DECISIONS.md 2026-09-22, *the oracle asked about everything else*) | 2026-09-22 |
| **deark's output is matched by name** — `make_manifests.py` and TESTING.md both, as the rule that replaced matching by position on 2026-09-21 | **By the name deark WRITES, which is not the name the archive holds.** deark writes each member to a real file, so a member inside a folder arrives with its separators mangled to `_`; matching raw names skipped **every entry in a folder, 500 of them**, and reported success on the subset it could match. **Cost: the third oracle's coverage, 1,641 forks where 2,075 were available** — a quarter of the cross-check, for one unmodelled sanitiser (`de_char_to_valid_fn_char`, one function in `reference/deark/src/deark-util.c`). Same shape as a check positioned where nothing can contradict it, one layer down | 2026-09-22 |
| **What is written onto the boot volume after a 300 KB extraction does not reach the image** — `interactive.py`'s `phase_report_utf8` and DECISIONS.md 2026-09-22 (*the fold, on a Macintosh*), both labelled *hypothesis, not measured*, as the reason the report is saved to a floppy | **The bytes reach the image; the CATALOG ENTRY does not.** `--utf8-to-boot` runs that phase onto the boot volume and reads the kept image twice: the report's text is there — the three `_` lines and `Extraction complete.`, in order, complete — and `hls -a` at the root does not list the file, while the extraction's own 300 KB is in BOTH, five entries deep. The File Manager writes a data fork's blocks and then records the entry, and the run ends between the two, which is why four remedies aimed at flushing changed nothing: **they were aimed at a write that had already happened.** Cost: nothing — the workaround was right and is kept — but it was the only unreduced hypothesis in the tree, and CLAUDE.md's rule says an unreduced root cause is not a finding (DECISIONS.md 2026-09-22, *the file that was on the disk and not in the catalog*) | 2026-09-22 |
| **The ArcMac header's own Finder info has bit 0x40 of the high byte set, which is `invisible`** — `arcmac.macbinary`'s docstring since M13, DECISIONS.md 2026-08-16, and quoted in OPEN_ITEMS.md and `tools/vmac/README.md` on 2026-09-22 as the reason `arcmac.read_volume` was "a known risk rather than a theoretical one" and the first of the blind walks to take | **No ArcMac header reachable here has that bit.** `macunpack/arc.h` puts `FINFO` at offset 42 of the 88-byte header — `fdFlags`, `fdLocation`, `fdFldr` — so the flags word is `h[42:44]`, and across **5 ArcMac files and 11 entries** (the two in the wild and the three this harness wrote) it is **0x2100 on the application and 0x0100 on every document**. 0x2100 is `fHasBundle | fHasBeenInited`; `fInvisible` is 0x4000 and is set nowhere. The SYMPTOM was real and is still recorded — the volume showed one item where two were written — but the code that produced it was never committed, so what it actually passed cannot be recovered. **A reason reconstructed from a symptom, written down as a property of the format.** Cost: nothing in the engine and nothing in the harness — the walk was blind independently of it and the flag costs nothing — but it is what ordered the work, and "one of the four is a known-real risk" is the sentence that made this walk first of four instead of one of five (DECISIONS.md 2026-09-22, *the column that was already on the volume*) | 2026-09-22 |
| **Eight forks in damaged nested archives cannot be adjudicated: `unar` declines them, deark PADS them, and our own output cannot grade our own output** (TESTING.md, *A third oracle*; FORMATS.md, *Hardening*) | **The container states its own layout.** All eight are MacBinary, whose forks are STORED at offsets the header gives, so what is physically present is arithmetic: all eight match what the engine writes, byte for byte, and `oracle-unadjudicated` falls **15 across 11 → 8 across 4** (7, and the eighth back the same day for an unrelated reason — the declined-fork row above). The claim was true about implementations and was read as true about evidence. **Cost: eight forks carried as ungradeable since 2026-08-08**, and the reasoning that would have settled them was the MacBinary header this project already parses (DECISIONS.md 2026-09-22, *the container is the oracle*) | 2026-09-22 |
| **What a shape-3 header's byte 2 tracks is where the encoder is in its window** — 41 of the 43 values above 200 in the 1995 archive are in blocks that start in the low half of a 65,536-byte window (`docs/formats/now-compress.md`, *The header*) | **Where a block starts in the window changes it by nothing.** `nowcompress.py --case wpos` archives four members of 65,536 bytes each, the same content to within a seed: each produces two full 32,768-byte blocks and advances the window by exactly one turn, so a 16,384-byte spacer in front of each moves its pair a quarter along. **Eight full blocks, two at each quarter of the window, byte 2 = 0 in all eight**; only the archive's first block differs, at 236. The 1995 archive's blocks alternate low/high half BECAUSE they are all full blocks in one member, so its correlation is with position in that file and not with position in the window. **Cost: none to any output — nothing reads this field — but it was the note's one surviving lead on it, and it stood for a day as the thing a probe should be built around.** The correlation was read off ONE file and labelled a correlation; what made it testable was noticing that no experiment had ever CHOSEN a block's offset, only observed one (DECISIONS.md 2026-09-21, *the quarter that changed nothing*) | 2026-09-21 |
| **`reference/macutils/macunpack/sit.c` is the only reference implementation the project has for StuffIt method 6** — XADMaster recognizes the method and refuses it, so the second oracle adjudicates a transcription against its own source (`src/fmt_sit.c`, FORMATS.md, TESTING.md) | **deark implements it, under MIT, and had been on this disk for four weeks.** `reference/deark/modules/stuffit.c` has a *"Fixed Huffman (type 6) decompression"* section; it credits macunpack as DOCUMENTATION and uses none of its code, and it agrees with this engine on **all 11 method-6 forks here** — the ten of `synth-sit-fixhuf.sit` and the 34,818-byte resource fork of `derived-INITLoader.sit`, which is the corpus's only real one. (Written "12" on the day, next to the enumeration that adds to eleven; corrected 2026-09-22 when `tools/derive_sit6.py` counted them.) It also disproves two claims made about the oracle itself: that it is a data-fork oracle only (it writes AppleDouble `.adf` sidecars, and the fork it was said not to see is the only fork method 6 occurs in) and that it reads no Zip. **Cost: four weeks of a documented blind spot** — deark arrived 2026-08-25 for ARC Distilled and is compiled by `ci.sh` on every run, and was never put to method 6 because the code path offers it only forks the others left OPEN. And a licence: method 6 and its 1,028-byte table are the reason `fmt_sit.c` still carries macutils, and deark states the same code book in 26 bytes (OPEN_ITEMS.md; DECISIONS.md 2026-09-21, *the oracle that was never asked*) | 2026-09-21 |
| **A shape-3 header's byte 2 is carried ACROSS blocks** — it climbs toward 255 by `((255 - b2) >> 1) + 1` when nothing matches and drops to 0 when everything does, which the note read as a running state the encoder keeps (`docs/formats/now-compress.md`, *The header*) | **It is computed from its own block and retraces with no lag.** `nowcompress.py --case matchv` archives 21 members of 1,200 bytes that differ only in how much of them can be MATCHED, up a ladder and back down: byte 2 runs 255, 127, 127, 63, 63, 63, 31, 31, 15, 15, 8 and then **the same eleven values in reverse**, every mirrored pair equal. A carried value updated by half the distance to a target lags; there is no hysteresis anywhere in the V, and not one of the ten transitions on the way back up takes the `((255 - b2) >> 1) + 1` step. So the 101 transitions that DO take it are a description of ladders whose parameter moved one way, not of a state machine — the same shape of error as the window correlation in the row above, found the same day and in the same field. **Cost: none to any output, and the probe cost three emulator runs — one of them wasted on a keystream, which is incompressible, so seven of eleven members came out STORED and had no header to read.** (DECISIONS.md 2026-09-21, *the ladder that was walked back down*) | 2026-09-21 |
| **Now Compress's `0d4c 0037` record is a LEADING record 5.0.1 writes in front of every block table**, and the 1993 archive's only member and the 1995 archive's first member are exceptions with none — leaving *what selects it* as the format's best open question (`docs/formats/now-compress.md`, *A member's blocks*) | **There is no leading record. There is one fork-boundary record per member, and its position is fixed by the two fork lengths**: between the forks, at the head when the resource fork is empty, at the tail when the data fork is. **153 of 153 members Now Compress wrote here.** Both "exceptions" are the rule seen from the other two positions. What hid it is in this file's own list of mechanisms — *every input a suite grades against, made by one program*: every member here came off an HFS volume built with `hcopy -r`, which writes the data fork alone, so 105 of 107 had an empty resource fork and the boundary at the head. `nowcompress.py --case forks` puts four members on the volume as MacBinary — data-only, resource-only, both-small, both-big — and each lands where the rule says. **Cost: one open question carried as the most valuable one in the format, and a version difference entertained as its cause; and `synth_now.py`'s `build_archive` still writes no boundary record at its two-fork member, which is a sixth way the archives this project grades itself on differ from the encoder's, where TESTING.md lists five.** The instrument was one emulator run, and the thing it varied was the one thing the harness had never varied (DECISIONS.md 2026-09-21, *the record that was never leading*) | 2026-09-21 |
| **The window is carried across a stream restart unchanged and the bytes come out right, so nothing here needs a reload** — `docs/formats/now-compress.md`, written 2026-09-21 | **A restart reloads the dictionary cache: the last 32,768 bytes ending where the previous stream's FIRST block ended, which is not the running window once a stream runs past one block.** `--case forks`'s `bothbig.bin` has a three-block resource fork, and its data fork's first block decodes byte-exact against the resource fork's first 32,768 bytes and comes out with **19,909 wrong bytes** against the running window. The sentence was true of every specimen that existed when it was written — `SynRef2.0 INFO`'s resource fork is 332 bytes, one block, where the cache and the window are the same bytes. **Cost: nothing to any output — `src/fmt_now.c` has always reloaded, and no file in the corpus would have broken — but the note is the description `fmt_now.c` now cites instead of XADMaster, so a reader written from it alone gets that file wrong, and `tools/derive_now.py` IS such a reader: 8 of 11 blocks before the fix.** A tolerance whose evidence is a corpus in which the two readings coincide cannot fail; ask which specimen would tell them apart, and make it | 2026-09-21 |
| **The Mac OS 9.2 tier is 20/20** — carried in BLOCKERS.md's status table and FORMATS.md since 2026-08-27 | **It is 18/20, and the two failures BOMB the application.** The tier was not run once between 2026-08-27 and 2026-09-04 while thirty-five commits touched `src/` and `mac/`, so the number described a binary nobody had run for a week. **Cost: `dist/` has shipped a build that bombs on Mac OS 9 since at least v0.29.0** — the released download, not a working copy — and the defect was found only because a tier re-run was asked for. The status table is the file read at session start, so the false number was the first thing every session saw. What the two failures were is the next row | 2026-09-04 |
| The 12 KB stack is **"verified byte-exact at exactly that size on every tier: 69/69 at 1 MB, 512 KB, System 7 and Mac OS 9"** (FORMATS.md, *Stack*, and the `kStackBump` comment in `mac/macextract_mac.c`) | **Mac OS 9 was not run at that stack size, or at any size, on the day the stack changed** — 2026-08-31 — nor for four days either side. Three tiers were verified and a fourth was named. The 12 KB stack is not the Mac OS 9 defect (the old 24 KB bump bombs there too), so this cost nothing directly; what it cost was the four hours spent today treating the stack as a suspect it had been declared innocent of by a sentence that had never been run. **A tier named in a verification list is a claim like any other** | 2026-09-04 |
| The System 6.0.8 / 512Ke tier is **"unchanged at 58/69"** after M46, because the flat reserve could not help a machine whose quarter-rule reserve was already under the 32 KB floor | **63/69.** The reasoning was sound and covered only the RESERVE; M46's other change, 20,464 B recovered from the STACK, lands on every machine and was never applied to this tier. Five fixtures had been coming back for four days with nobody looking. **Cost: nothing lost — the number was pessimistic — but a correct-sounding argument for why a tier could not have moved is exactly the shape that stops it being re-measured** | 2026-09-04 |
| **`7be1ee9` is the first bad commit for the Mac OS 9 crash**, from a `git bisect run` over 35 commits | **Withdrawn the same day, by its own retest.** Disabling any three of that commit's four sniffer probes makes the crash vanish; keeping all four in the binary but never executing them also makes it vanish; no single probe reproduces it. A defect whose symptom moves with the binary's LAYOUT makes every commit look guilty, so bisection cannot address it. **Cost: about ten emulator runs, and one report to the maintainer that had to be retracted** — the lesson is that a bisect needs its answer re-tested like any other claim, and that a clean-looking bisect over a layout-sensitive fault is a machine for producing confident wrong answers The mechanism that made every commit look guilty is now known — an uninitialised field, next row | 2026-09-04 |
| **The Mac OS 9 bomb is in code the interactive build runs and the autotest build does not** — the event loop, the dialogs, the progress bar, Standard File — and **every channel that could find the crash site perturbs it away**; carried as the one open blocker and on the v0.30.0 download page as a cause "not yet known" | **It was a field nobody assigned.** `RunExtract` filled `UncOptions` field by field and never set `long_name` or `long_name_cap`, added 2026-08-27; the engine's folder-path walker writes every component through that pointer whenever it is non-NULL, and exactly three formats walk a tree with it — DiskDoubler, SuperDisk! and Now Compress. The engine half is reproduced on the host in seconds (`tools/longname-repro/`: a 4-byte block and a 1 MB cap, ASan, those three overflow and Compact Pro and StuffIt never touch it); the Mac half is the fixed build passing the fixture that had bombed six runs out of six, then the whole sample (FORMATS.md, *Mac OS 9.2*). The crash was in code BOTH builds run, fed by a value only one build's stack left non-NULL — so "interactive-only" was a fact about stack garbage, not about the shell, and every instrument hid it because every instrument moved the garbage. **Cost: two releases shipped with it (v0.29.0, and v0.30.0 with the defect on its download page); the three Mini vMac tiers' 69/69 on the walking formats were luck rather than verification; about ten emulator runs on a bisect and its retest, a retracted first-bad-commit, two host hypotheses and a tracer build — against a one-minute `grep` of the option fields the shell assigns, which is where the search should have started: the host surface the formats consume unequally** (DECISIONS.md 2026-09-04, *the field nobody assigned*) | 2026-09-04 |
| Two folders whose shortened names collide **cannot be told apart** where the archive declares no folder entries, so a merge is what a Macintosh gets — filed under OPEN_ITEMS.md's *Limits of the formats themselves*, where nothing can change it | **Both halves were wrong, and the shell's own code held the refutation.** `RepDirMemo` records every directory a run creates, declared or not, so the second folder was distinguishable all along — the report simply never asked, being gated on `info->is_dir`. And the cost that made remembering look unaffordable was the cost of whole NAMES: the only question ever asked of a row is *is this directory this run's, and is it this name's?*, which a 32-bit hash answers in 8 bytes against 68, putting 200 folders in the 1,600 B that held 24. **Cost: for every path-only format — zip, tar, LZH, the shapes most downloads have — two archive folders became one on disk and the box said nothing whatever about the second**, while the declared case at least said *combined with*; and the entry sat in the section reserved for things no evidence can change, which is where a claim goes to stop being re-tested. One zip through a mock sink that has been in `ci.sh` since 2026-08-28 disproved it (DECISIONS.md 2026-09-03, *a folder is a name too*) | 2026-09-03 |
| A true Macintosh 512K — 64 KB of ROM — **cannot be reached at all** | **It boots.** On Apple's own 400K MFS System 1.1 floppy it reaches the Finder in ~35 s, and on an MFS volume this project builds it boots **System 3.0 and Finder 5.1**, the floor system, on the 64 KB ROM. What that ROM cannot read is HFS, and HFS was the only volume ever put in front of it — the three A/Bs behind the negative varied the ROM, the RAM and the presence of a disk, and never the FILE SYSTEM, which is the one thing the conclusion named. **Cost: a day, and it very nearly cost more** — the same entry said the machine was "out on the ROM regardless of how the disk question resolves", which is what makes nobody write the MFS writer that settles it. The application does still bomb there, so no capability was lost; what was lost was the distinction between *cannot boot* and *boots and then fails*, which is the entire content of the claim (FORMATS.md, *A true Macintosh 512K*) | 2026-08-31 |
| Two of this application's dependencies are 128K-ROM-and-later — `NGetTrapAddress` in `TrapAvailable`, and every file operation going through HFS parameter blocks | **Neither is.** `tools/vmac/traptest` paints a mark, makes one call, paints the next, and runs as the boot shell so nothing else is in the frame: on a true 512K it comes back from `NGetTrapAddress` twice and from `PBHGetVInfoSync`, and bombs at **`PBGetCatInfoSync`, `ID = 12`, unimplemented core routine**. The verdict was right and both of its reasons were wrong; the real one is the `_HFSDispatch` selector behind `PBGetCatInfo`. **Cost: it was the sentence that made the whole question look settled**, and it was written from the SHAPE of the code — two greps and an inference — in a session that had an emulator running. A minimal reproduction was ~40 lines of C and one boot (FORMATS.md, *A true Macintosh 512K*) | 2026-08-31 |
| The guarded build starts on **64K-ROM Macintoshes**, the 128K among them — OPEN_ITEMS.md listed "the 128K and the true 512K" under one status | **Only on the 512K.** One volume, one ROM, one System, two machines: the `rom64k` `dist/` opens Standard File on a 512K and bombs `ID = 03` on a 128K. `tools/vmac/memtest` says why — the largest single block a 128K will grant is **63,744 B**, against the **142,152 B** of `CODE` 2 that the Segment Loader had to place before any of the engine ran — the build of that day, and 48,888 B since the overlays, which is why the second reason is now the heap total and not this segment (the 2026-10-06 row at the top of this table). The claim was never measured on a 128K; it was one machine's result carrying a second machine's name, and RAM was the variable nobody had changed. **Cost: MANUAL_TESTS.md §6 spent a section asking somebody with the hardware to try either machine**, and half of that instruction could not have worked — the expensive kind of wrong, because it spends a stranger's afternoon rather than ours (FORMATS.md, *A Macintosh 128K*) | 2026-09-01 |
| `-fno-inline-small-functions` is 248 B that has not been taken only because nothing has timed it — the last untimed size flag, recorded here as an inconsistency because four flags beside it WERE taken untimed | **Timed 2026-08-31, and it is the worst trade in the file: −248 B for +448 ticks, +14.1 %** (3,184 → 3,632 on `derived-EmpireBuilderDemo.sit` at authentic 7 MHz, the same deterministic instrument that priced the other four, whose baseline reproduced to the tick). 53.1 s becomes 60.5 s to save a quarter of a kilobyte, against 780 B for +0.82 % from the four that were kept. **Cost: nothing — this is the entry closing, not a claim failing.** Worth recording because the inconsistency was real and the resolution went the other way from the suspicion: the flag was not being unfairly withheld, it was bad, and the four beside it were lucky rather than right. Inlining is at its size optimum here and pushing it either direction costs (FORMATS.md, *Where the bytes are*) | 2026-08-31 |
| The 32 KB stack can be cut to 20 KB for 12,272 B of budget, at a 1.9x margin over a 10,842 B watermark | **The watermark was not one.** `-D UNC_AT_STACK` painted the region between ApplLimit and the stack base and read back what was overwritten — but a frame is made by MOVING the stack pointer, and a frame holding an uninitialised buffer never writes most of itself. The same password-dialog run reported **10,842 B on a 16 KB stack and 16,266 B on a 20 KB one**, so the cut was REVERTED the same hour. Then a second instrument was built — sampling the stack POINTER in the progress pump, the sink, the allocator and inside the Dialog Manager's filter procs — and swept across four stack sizes: **5,200 B, constant**, while the paint figure ran 9,288 → 25,392 with the size of the region. The cut was RE-MADE on that evidence and then taken FURTHER by sweeping downward, which is the more useful direction: PAINT converges on SAMPLE as the room runs out (9,288 → 6,828 → 5,604 at 16, 12 and 10 KB), squeezing out whatever was helping itself to the spare room and leaving the real requirement, ~5,600 B. Final: a 12 KB stack, **20,464 B** to the engine, byte-exact on all four tiers. **Cost: about two hours of emulator time and a margin figure that stood in FORMATS.md for twenty minutes** — and the paint metric was wrong three different ways before it was abandoned (FORMATS.md, *Stack*). What caught it each time was **changing the size of the thing being measured**: a requirement does not move when its container does, and nothing in the first three measurements ever varied the container | 2026-08-31 |
| Joining a segmented set costs far more memory than the same archive whole — `derived-Troi-ClipSave-Plug-in1.1.sit` is 472,137 B straight and asks 64 KB beyond budget joined; `derived-Library_ISBN_Barcoder.sit` asks over a megabyte more | **The join was never the variable.** Driven through the same UI with NO segments at all, `Troi-ClipSave` extracts COMPLETELY on a 1 MB Mac Plus and still says *"Needs 48K more memory"*. The two figures had different instruments: 472,137 B is a peak-heap measurement from the autotest replay — what was USED — and the refusal is an alert message reporting `gShortBy` — what was ASKED for and declined. On Linux the join costs **8,192 B** and the inner extraction is then **661,173 B**, byte-identical to the whole file. The sizes even name their own source: ISBN's unconstrained peak is 1,683,101 B, and 1,683,101 − 615,348 is the "over a megabyte". **Cost: a user-facing failure filed in OPEN_ITEMS.md that did not exist, and — far worse — it concealed a real defect for as long as it stood.** `mal_alloc` records `gShortBy` on EVERY over-budget request, and StuffIt 5's inverse BWT asks for `numbytes*4` fully expecting to be refused, falling back to a sampled occurrence index that is slower and byte-identical. So every StuffIt 5 archive big enough to decline the fast path — most of them on a small Mac — reported a memory failure after extracting perfectly. The withdrawn claim pointed at joining, which almost nobody does; the defect it hid was on the main path. Gated on an errored entry since 2026-08-31 (DECISIONS.md 2026-08-31, *the message that failed a successful extraction*) | 2026-08-31 |
| Everything builds at `-Os`, and that was TESTED rather than assumed | tested on ONE file. `-O2` on `sit_arsenic.c` really is slower, and that result was applied to the other ~40 files, none of them measured. On the four a StuffIt run lives in, `-O3` is **−25.4 %** on a 7 MHz Mac Plus — 70.4 s → 52.5 s — and per-function `UNC_HOT` gets the same time for +1,024 B instead of +8,320 B. **Cost: a fifth of every StuffIt, DiskDoubler and PackIt extraction for as long as those files have existed**, and the note beside the rule said the question could not be re-asked "without a harness that resolves better than 20 s on a 22-minute run" — which was true of the screenshot clock and not of the tick probe that was one afternoon away (FORMATS.md, *What -O3 is worth, and where*) | 2026-08-30 |
| Every archive in the 922-fixture corpus fits on a 1 MB Mac Plus again (after 780 B of code came back) | Verified under a LINUX `--budget` cap, never on the machine. On the Mac two of the three still failed, and one needed **16 KB** more than the cap predicted while another needed **33 KB** more — the Mac allocator charges 16 bytes a block. Cutting the reserve later fixed two of the three; `derived-EasyFind.dmg.sit` still does not extract there. *(The 16 KB, the 33 KB and EasyFind's refusal were themselves withdrawn on 2026-09-18 — next row but one — and the claim in this row's first column is TRUE, measured on the machine.)* **Cost: a capability claim published in a commit message and in FORMATS.md on the strength of a proxy**, when the on-Mac replay that would have disproved it is one command and was used elsewhere in the same session. The proxy's error is not a constant, so no correction factor rescues it (FORMATS.md, *The Linux budget check under-reads the Mac*) | 2026-08-30 |
| The Linux `--budget` cap under-reads the Mac by 16 KB on one fixture, 33 KB and then 62 KB on another, "the gap is not a constant", and `derived-EasyFind.dmg.sit` does not extract on a 1 MB Mac Plus | Capped on the machine at **562,000 B**, 559 B above the bisected Linux minimum, both fixtures extract byte-exact with peaks **40 B** above Linux's — 561,922 against 561,882 and 561,919 against 561,879 — and the same 40 B at the shipped budget. The `gRefusedWhy = 1` the figures cited was the run's FIRST refusal, the transform vector a StuffIt 5 entry expects to have refused (the instrument error M46 found a day later, in the other message that read it). EasyFind's refusal was **`UNC_ERR_SINK` in twenty seconds**: its one entry is 1,851,907 B and the harness's Out volume has been a 1,440 KB floppy since M10, so it could never have completed there, and nobody read the `ret` slot, which said −9 and not −3. **Cost: three fixtures declared out of a 1 MB Mac Plus's reach for 18 days, a caveat printed against every `--budget` figure in FORMATS.md, and a review that ranked "close the gap" above every code change on the table.** The run that settled it was two commands, one of them `--out-kb 2400`, which the same file documents (FORMATS.md, *The Linux budget check reads the Mac to 40 bytes*; DECISIONS.md 2026-09-18, *the floppy that was full*) | 2026-09-18 |
| The compiler size flags cost no speed — "no capability lost, no speed traded" | They cost **+49 ticks, 1.55 %**, deterministic over three runs per build. Priced per flag afterwards: one of the four (`-freorder-blocks-algorithm=simple`) carried 26 of the 49 ticks, and one (`-fno-early-inlining`) was **worse on both axes** — 8 bytes bigger AND 2 ticks slower — and had been shipped. **Cost: a false claim in a pushed commit message and in `mac/CMakeLists.txt`, and a harmful flag in the shipping build for one commit.** The reasoning was available at the time and was applied selectively: `-fno-inline-small-functions` was rejected *because nothing had timed it*, while four flags reaching the same `UNC_HOT` code were taken without timing. `mac/CMakeLists.txt` had already said, of an earlier attempt, "do not re-try it without a harness that resolves better than 20 s on a 22-minute run" | 2026-08-30 |
| The application's RESIDENT SIZE — code plus data plus bss — is what costs the engine its budget, so moving big tables (`ss_dict0`, the DES S-boxes, the report pool) out of the A5 world would buy it back | Only CODE costs anything. Ballast, verified present in the binary that ran: +11,308 B of code moved FreeMem 647,096 -> 635,768, one for one; +6,132 B of `.data` moved it not at all. `CODE` resources are handles inside the heap `FreeMem()` reports and the A5 world is outside it (FORMATS.md, *What the application costs the engine*). **Cost: a whole line of proposed work aimed at the wrong bytes** — three candidate tables costing 23,887 B between them, every one of them free already — and one shipped-code change (the report pool allocated on first use) written, measured at ZERO gain, and reverted. The formula was fitted to ONE data point and generalised; the first thing that would have disproved it was the second point. **Three of the four ballast runs measured nothing**, twice because `--gc-sections` dropped the ballast and once because it was referenced only from the other `main()`, so a null result here means "check the symbol is in the binary" before it means anything about memory | 2026-08-30 |
| **Only `CODE` costs the engine; data, globals and resources are free** — measured by ballast 2026-08-30, and the reason `tools/build_mac.sh` watched code alone | **Data costs one for one.** A ballast of 16,384 B of `.data`, verified present with `nm` in the binary that ran and read from BOTH `main()`s through a volatile, takes the budget from **647,802 B to 631,384 B** — 16,418 B for 16,384 B. The A5 world sits above `ApplLimit`, so it lowers the heap's ceiling by its own size. The 2026-08-30 null result obeyed neither half of its own warning: three of its four runs had measured nothing already, and the fourth was believed. **Cost: it displaced a correct claim** — *resident size, code plus data plus bss, is what costs the budget* was withdrawn on the strength of it and was right; and it made *put material in tables rather than in C* the standing advice for two weeks, which is advice to spend budget. 32,644 B of A5 world grew unwatched in that window. An A5 ratchet now sits beside the code one (FORMATS.md, *What the application costs the engine*) | 2026-09-02 |
| An advertised capability does not work on the Mac: encrypted StuffIt extracts nothing | **Encryption works. The HARNESS was broken.** `interactive.py --password` failed because `mkboot.py` deleted the boot volume's invisible `Desktop` file under the boot-shell arrangement — one line added on 2026-08-24 (`d3907fc`, the icon commit). Bisected with BOTH endpoints verified by running them, then isolated by holding the application constant at the bad commit and reverting `mkboot.py` alone: five runs, both ways. Fixed by dropping the Desktop file only when a Finder will actually run. **Cost: a working feature was published as a broken one**, in a commit on `main` and in this file, and a `LoadMKey` hypothesis was recorded that the evidence already contradicted — two of the three entries decrypted, so the key was plainly being found, and I had read 'one entry missing' as 'nothing extracts'. **The mechanism is still not understood** and is the open question below | 2026-08-30 |
| A `git bisect` over 28 commits named `42cfda3` as the first bad commit | That commit touches only documentation and one new harness file — it cannot break an application. `git bisect start <bad> <good>` takes the GOOD end **on trust**, and mine came from a DECISIONS entry about the Mac OS 9 tier while I was testing System 6 — evidence about a different machine. The re-run with both ends measured found `d3907fc`, 108 commits earlier. **Cost: ~20 minutes of emulator time and a confident wrong answer**, which is worse than no answer because it looked authoritative | 2026-08-30 |
| The System 3.0 tier's figures were taken "with the FINDER resident", which is why that system beats System 6.0.8 on a 512 KB machine | Single-tasking Mac OS UNLOADS the Finder when an application launches. Measured on System 6.0.8 at 512 KB: a boot-shell launch leaves 122,808 B free and a double-click launch from a booted Finder leaves 122,796 B — **12 bytes**, not 56 KB. The real mechanism is the system heap, 218,208 B free under System 3.0 against 122,808 B. The RESULTS were never in doubt; the explanation for them was. **Cost: the wrong mechanism reached seven files and the v0.28.0 tag message inside one session**, because "resident" was written once and then re-narrated rather than checked, and a tag is immutable — the correction can only live here. What caught it was arithmetic that does not close: 512 KB cannot hold a 183 KB application, a ~22 KB screen, System 3.0 AND a 56 KB Finder and still leave the 218,208 B that was measured | 2026-08-30 |
| A MIME message written by a Macintosh is waiting on a gradeable specimen somebody else has to send | mpack's Macintosh PORT is in `reference/mpack` and always was — README.mac, macfile.c, the lot. `encode_applefile()` and `encode()` compile unmodified for a 68000 and run on System 6.0.8, and the message they write there passes **18/18** including both forks byte-exact through this engine (`tools/vmac/macmime.py`; FORMATS.md, *base64 and MIME*). **Cost: three days as a wait, filed one bullet below its own answer** — the entry named "mpack's own Macintosh port" as the thing that would settle it, in a tree this project had already built munpack out of | 2026-08-29 |
| A MIME part encoded `x-uuencode` inside a multipart is decoded by mpack, and not by this engine | wrong in both halves, both run. munpack's encoding enum is `enc_none, enc_qp, enc_base64`; an unknown Content-Transfer-Encoding warns and falls through, and its `handleUuencode` is reached only for a depth-0 `text/*` part with no encoding and no name — fed such a multipart it prints *"ignoring unknown content transfer encoding"* and writes the uuencoded TEXT out as the file. This engine decodes it byte-exact, and always did, because the uu probe wins the sniff. **Cost: three days in the waiting-on-a-file section, and the real defect went unnamed the whole time** — a uu part SHADOWED the rest of its multipart, a sniff-precedence bug with munpack sitting here to grade it, fixed the same day (DECISIONS.md 2026-08-29, *a part that hid its message*) | 2026-08-29 |
| `message/partial` is waiting on a specimen this machine does not have, and meanwhile each part decodes on its own into half a file | mpack writes the specimen: `mpack -m 10000 -o out.mime payload.bin` cuts 30,000 bytes into four `message/partial` files and munpack puts them back byte-exact. And no part decodes at all — part 1 sniffs as a MIME message then fails *"not a recognized archive"*, parts 2–4 are *"format not recognized"*, and `src/fmt_mime.c` does not contain the word *partial*. The stated behaviour had never been run. **Cost: three days, and a sentence about our own binary that was written from the code's shape** | 2026-08-29 |
| The engine's size limits all fail loudly, the zip entry count aside | two more were silent, found by sweeping for the shape rather than for a bug. A **457-byte zip path** listed and extracted as 255 bytes and exited 0, under a name that was not the archive's, where `unzip` showed all 457; and a container over 4 GiB was refused with *"not a recognized archive"* because `(uint32_t)st_size` wraps in the CLI — a true refusal with a false reason. **Cost: the longest name in 932 fixtures is 120 bytes**, under half the cap, so no fixture and none of the 9,320 variants could reach it, and the wrong name was the kind a user would blame on their own machine | 2026-08-27 |
| The engine reads any container up to 4 GiB, and past that it fails loudly | not for a zip written past 2 GB: a 3.4 GB archive of 23,400 entries listed every one of them and then **failed 21,352 under `t`**, each with `UNC_ERR_CORRUPT`, the first at 0x80015800 and the last one to pass at 0x7FF157D5. CPython's `zipfile` escapes a local-header offset at `ZIP64_LIMIT` (2³¹ − 1), putting the real value in extra field 0x0001, which `fmt_exo.c` did not read. **Cost: the ceiling in FORMATS.md was wrong by half for every zip any conservative writer produced between 2 and 4 GB**, and neither suite that names itself after the question could see it — `run_ziplarge.py`'s subjects are megabytes with large COUNTS, `run_sizelimits.py`'s large zip entry is the only entry and sits at offset 0. Listing was unaffected throughout, so the archive looked healthy right up to extraction | 2026-08-27 |
| A zip with more than 65,535 entries is covered by the Zip64 refusal, which returns cleanly unsupported | it was not refused at all: a 70,000-entry archive listed and extracted **65,535 entries and exited 0**, where `unzip` and CPython's `zipfile` both count 70,000. The count is 16 bits and saturates, so the truncated archive is internally consistent and nothing downstream can notice. **Cost: no fixture was ever within 65,506 entries of the boundary** — the largest zip in 932 is 29 — so neither the differential suite nor 9,320 robustness variants could have failed on it, and the scope decision that appeared to cover it was about files larger than 4 GB. The engine's other size limits all fail loudly; this one did not | 2026-08-25 |
| Retro68's `HOpen` glue is broken on System 6 | `tools/retro68-hopen-repro/`, 10 cases | 2026-07-25 |
| Three non-relocatable staging blocks bomb the Memory Manager | `UNC_AT_SEPARATE_BLOCKS` | 2026-07-25 |
| `derived-RWAsm_Folder.sit` fails on a 4 MB Mac Plus | committed harness re-run | 2026-07-25 |
| QuickDraw bombs after File Manager activity | `tools/quickdraw-repro/`, 12 configurations | 2026-08-01 |
| The OS 9 boot volume is plain HFS | `drEmbedSigWord` = `'H+'` | 2026-08-02 |
| Interleaved reads and writes on one volume return zeros | `UNC_AT_INTERLEAVE`, 3 read shapes | 2026-08-02 |
| Mini vMac's write-back is lazy and partial | `checkdisk.py`, 44/44 off the disk | 2026-08-02 |
| `pkill -9` never flushes; boot+kill corrupts the image | 11 boot+kill cycles | 2026-08-02 |
| The three 1 MB StuffIt 5 refusals each fill a 512 KB block | instrumenting `numbytes` where the transform vector is allocated | 2026-08-03 |
| Nine fixtures are ground truth the oracle cannot produce | `unar -k hidden`; all nine build, all 774 existing manifests unchanged | 2026-08-08 |
| There is no oracle for StuffIt method 6, and no second fixture to test one on | `macunpack` from `reference/`, and `tools/synth_sit6.py` | 2026-08-08 |
| Even `unar` fails on the two PKZIP 1.x zips, so they stay corpus-only | their own manifests: `unar` adjudicates 5 of the 7 entries | 2026-08-08 |
| The Macintosh application unwraps nested files (`.sit.hqx`) automatically | running it: one layer came off and it stopped | 2026-08-14 |
| No second implementation of Now Compress exists, so four forks cannot be graded | the archive is self-extracting: its own 1995 extractor agrees on every fork | 2026-08-16 |
| Nothing documents which fork an ArcMac payload starts with, and no oracle reads ArcMac | ArcMac 1.3c archiving a two-fork file under Mini vMac: data fork first | 2026-08-16 |
| Alysis SuperDisk! has no reference anywhere, so rule #1 forbids reading it | both corpus archives are self-extracting: the layout, the method table and every codec are inside them | 2026-08-20 |
| Nothing reachable writes DiskDoubler methods 1–5 or 7, so none can be graded | DiskDoubler 3.7 under Mini vMac writes method 1 from its own menu; its distribution disk ships two method 7 files | 2026-08-20 |
| The three DiskDoubler containers are read; the corpus exercises every one | nine archives from `ssokolow/diskdoubler-test-files`: five fail at their third entry, on a `DDA2` entry type neither we nor XADMaster implement | 2026-08-21 |
| The `SPLT` specimens are four parts across two sets | the same clone: six parts across three, the third with a 14 KB resource fork | 2026-08-21 |
| The Mac sample is 63 fixtures, and every tier result is 63/63 | counting the file: 63 lines, 59 distinct — four listed twice | 2026-08-21 |
| Macintosh Garden has DiskDoubler 3.7 and 4.x only | it also has 3.2 and DDExpand 2.03; 3.2's menu offers the same two software methods, and 2.03 is an expander | 2026-08-21 |
| The `0x1000` `DDA2` record is what DiskDoubler Pro writes for a file it could not shrink | the same fifteen archives hold 45 ordinary headers whose data fork is stored; all 30 `0x1000` records are the files with NO resource fork | 2026-08-21 |
| A `0x1000` record with a resource fork is waiting to be found | DiskDoubler 4.1.1 writes the form only for a fork-less file — all four cells of compressible x forked measured in one archive | 2026-08-21 |
| No DiskDoubler COMPRESSOR older than 3.2 is reachable, so methods 2-5 cannot be graded | WinWorld carries Salient's **3.1.2** distribution floppy (1991), which holds a method 2 fork | 2026-08-21 |
| DiskDoubler methods 3, 4 and 5 cannot be graded, because no specimen of them exists | the 1991 disk carries Salient's own expander: it reads forks THIS project encoded, and all three come back byte-exact | 2026-08-21 |
| 8 resource forks have no off-Mac oracle, so they cannot be ground truth | `unar`'s DDn reads ONE byte past the declared compressed length; give it one and it decodes all 33 forks byte-exact | 2026-08-22 |
| SuperDisk!'s compressor does not survive here, only its expander | Macintosh Repository has the 1991 `SuperDisk!` control panel; it installs, runs, and compresses on demand | 2026-08-22 |
| A matching name merely APPEARING does not fire SpaceSaver's rule — tested, fourteen minutes, unchanged | that run never booted: its own frames are the striped garbage screen, every one of them | 2026-08-22 |
| The `--namevol` run that did not boot was a one-off infrastructure failure | it reproduces exactly, and the cause is in the harness: the enrolled image was copied out of a KILLED emulator, so it is torn. Three runs were built on it | 2026-08-22 |
| SpaceSaver's trigger is known: rename a file to end in `small` and it compresses | four runs that booted AND flushed do it correctly and nothing compresses; the OTHER rename rule on the same page fires on the same event, turning `Forked` into a StuffIt archive | 2026-08-22 |
| SpaceSaver 3.5.1 is installed and running | its control panel runs; its EXTENSION shows no sign of it. With `~Magic Menu™` deleted the menu bar carried no icon menu at all, so the menu `STR# 1024` describes was never installed | 2026-08-22 |
| AppleLink `.pkg` has no reference implementation anywhere reachable | the SpaceSaver image has had one all along: `Extensions:Aladdin:Translators:PKG Expand Translator`, whose `Name` resource is `AppleLinkPKG` and whose `Othe` resource is 20 KB of 68k with Aladdin's usual module preamble | 2026-08-22, and **narrowed 2026-09-27**: that translator is a DRIVER — it recognises nothing and calls `GetResource('Eng ', 2)` in `StuffIt Engine™` to do the work — so the reference for the format, if it is on the image at all, is that 26,362-byte resource (*Corrected figures*) |
| AppleLink `.pkg` cannot be sniffed without inventing a magic number | true of magic numbers, false of sniffing: Aladdin's own recogniser reads three whitespace-delimited TOKENS, and `macextract sniff` now does the same at 0 false positives across 928 fixtures | 2026-08-23, and **this withdrawal is itself withdrawn** — that routine is the translator API's command parser and names no file (*Corrected figures*, 2026-09-27). **Withdrawn a third time, 2026-10-05, and for the right reason at last:** a package is sniffed by its own arithmetic — a version byte, eight zero bytes, two item counts and a directory whose forks tile the file to its last byte — at **exactly the 6 of 955 fixtures that ARE packages and no others** (measured 2026-10-05, and it is a sweep that can now fail in both directions, which the old one could not: the corpus held neither a package nor a script), and 10 bent packages refused one test at a time (`src/fmt_sqp_probe.c`) |
| SqueezePlay's LZW deviates from Unix `compress`: it sets the next free code to 256 after a clear where `compress` sets 257, so `src/unc_lzw.c` cannot be reused unchanged | **`compress` sets 256 there too** — `reference/macutils/macunpack/de_compress.c`, `free_ent = FIRST - 1`, a file this project has carried since M0. 257 is deark's rendering of the same algorithm, which is what `unc_lzw.c` follows; the two differ only in a table slot no valid stream can name. The engine reads SqueezePlay with `unc_lzw_init(..., 13, 1, ...)`, the configuration ARC method 9 already asks for, and `gzip` reads every fork of every package byte-identically through a `.Z` header. **Cost: none, because it was checked before anything was built on it** — the work it specified was a codec parameter or a second code path, measured at 0 bytes of either (DECISIONS.md 2026-10-05, *the deviation that was the reference*) | 2026-10-05 |
| Compact Pro's encryption algorithm is unknown, so an encrypted `.cpt` can only be reported | Compact Pro 1.51's own `CODE` 3: the key at 0x1892, the 64-bit CRC table at 0x408e, the seed at 0x40fe, and the encrypt and decrypt loops at 0x1152 and 0x1f08 — then graded by the application, both ways | 2026-08-23 |
| Compact Pro enables encryption only for a registration whose name ends with `*`, so no copy here can grade the cipher | registering with the code Macintosh Garden publishes (`Registered` / 35427117): the refusal goes away, the Add dialog's Encrypt checkbox appears, and the application both encrypts and decrypts. The `*` test at 0x485e is really there; it is not the only path to that flag, and reading one branch was not reading the feature | 2026-08-23 |
| StuffIt classic's archive key is XADMaster's loop, and the open question is only whether `unar` 1.10.8 or current XADMaster matches Aladdin | three archives StuffIt Deluxe 3.5.1 wrote, with passwords of 8, 9 and 17 characters: the fold count is **ceil(len/8)**, so XADMaster is wrong at 8 and at 17+ (it folds an all-zero block at 8 and never more than two) and `unar` 1.10.8 is wrong at 9+ (it folds one). Neither reference had it, and this engine had shipped XADMaster's | 2026-08-23 |
| Compact Pro corrupts every resource fork it extracts, 48 bytes in | a CORPUS archive extracted by the same copy comes back with 22 bytes changed in the same way: the Mac opens an extracted file's resource fork to draw its icon and the Resource Manager writes the map's live fields back. Nothing to do with Compact Pro, and nothing to do with the cipher — but it cost an afternoon before a real archive was tried | 2026-08-23 |
| The corpus is large enough that some of it must be encrypted, so a decryption suite has fixtures | `lsar -j` over all 903 fixtures: `XADIsEncrypted` is 0 for every entry in every one | 2026-08-23 |
| A multi-block Arsenic entry gets the declared 512 KB block, so shrinking it to its fill returns ~200 KB to the sampled index | instrumenting `blockcap - numbytes` at `ars_bwt_prepare`: the largest block in the corpus is `cap=352,160 fill=323,384`, waste **28,776 B**, and neither slow fixture ever allocates 512 KB — `ars_block_reserve` has sized the first allocation at `min(outlen, blocksize)` since M9. The index needs 225,528 B at target 512 and 346,836 B at 1024, so 29 KB does not move the dial by one step | 2026-08-24 |
| Segmenting the CODE resource keeps ~61 KB out of the launch path and makes startup cheaper | ballast, three runs each at authentic 7 MHz: 64 KB of resident data with no relocations costs **nothing measurable**, and 64 KB carrying 16,384 relocations costs **1.1 s**. The whole application has **2,376** relocations, so everything it pays at launch for its own size is ≈ 0.16 s of an 8.9 s boot | 2026-08-24 |
| Engine call depth is at most 4 KB (CLAUDE.md's own rule) | `m68k -Os -fstack-usage` over the call graph: `unc_dd_extract -> dd_fork -> dd_ddn` was **6,664 B** and Now Compress **5,632 B**. Never recorded, never tested, and it had never failed. Both formats' code tables moved to the heap; the deepest chain is now **3,290 B**. The rule was exceeded; the MACHINE never was — `kStackBump` gives the shell 32 KB of stack, not the 8 KB default, which the first write-up of this row got wrong | 2026-08-24 |
| A 1 MB Mac Plus leaves the engine 678,392 B, and `--budget 678392` reproduces it | `run.py --mem 1M -D UNC_AT_BUDGET`: `FreeMem()` is 678,956 B and the shell keeps 80 KB back, so the budget is **597,036 B** — 91 KB less. At 597,036 the CLI predicts the Mac's peak to **48 bytes on two fixtures**; at 678,392 it was out by 90,981 on one of them. **Cost: `ci.sh`'s floor-target run was 91 KB more generous than the floor target for seventeen days**, and the figure had reproduced the machine to 54 bytes when it was taken — the budget is `FreeMem()` when extraction starts, so it falls as the application grows, and nothing re-measured it | 2026-08-24 |
| When the destination disk fills, extraction continues and every remaining entry fails the same way, one error each | filling an 800 KB destination on purpose (`run.py --out-kb 800`) with a 17-entry archive: **9 files written, ONE error**, and `ret` = `UNC_ERR_SINK`. Thirteen of the fourteen extractors already end the archive on a sink failure — the line is in `fmt_sit.c` and its copies — so the behaviour the proposal wanted was already there for all but one. **Cost: a shell-side `diskFull` flag, a `Progress` coupling and a `PBHGetVInfo` call were written and then deleted**; what the case actually needed was six lines in `fmt_arc.c`, the one format that was out of step, and keeping the `OSErr` so the alert can say *which* failure it was | 2026-08-24 |
| Only StuffIt 5 ever runs out of memory, so the remaining fixed-size windows recover memory nothing is asking for | that was measured at ONE budget — 597,036 B, the System 6 whole-machine case. Under MultiFinder the application gets a PARTITION, `macextract.r` declares a 400 KB minimum, and the budget there is **130,136 B** (measured on System 7.0.1 with the preferred size built down to 400 KB). At that figure **Now Compress opened NONE of its three fixtures** — its 131,072 B per-archive allocation failed before an entry was read. **Cost: three window items were closed as pointless on 2026-08-24 and one of them reopened the same day**, when a reader asked what happens under MultiFinder. The sweep now runs at both budgets (FORMATS.md, *Budget sweep*) | 2026-08-24 |
| SpaceSaver's extension does not install on this machine, so the question is whether `INIT 0` runs at all | a boot that never opens the control panel leaves `System Folder:Preferences:SpaceSaver Preferences` (`Pref/SMKR`, 10,496 B) on an image that had none — **with the INIT patched and unpatched alike**, so its one silent gate (`_Button` and the Shift key at INIT 0 @0x2a6c, the ordinary "hold this to disable") was never closing. Every OTHER refusal it has ends in `NMInstall` with a `STR# 1001` message, which is an alert once the Finder is up, and no run has ever photographed one. **Cost: twelve emulator runs and an open item aimed at the install** — where what has never fired is the TRIGGER. It also reattributes the prefs file, which 2026-08-22 credited to OK-ing the panel | 2026-08-25 |
| ARC methods 0x0a (Crushed) and 0x0b (Distilled) are PKARC's | the format's own history: both are **PAK's**, from NoGate Consulting — 0x0b introduced in PAK v2.0, July 1989. **Cost: the search that would have closed the item was aimed at two programs that never wrote either method**, and it was written into four files, so re-reading them confirmed itself. The specimens were one HTTP fetch each from `cd.textfiles.com` | 2026-08-25 |
| SpaceSaver installs no menu of its own — `--idlenow` deleted `~Magic Menu™` to give it the bar and the menu bar came up empty | it was pressing x=283, which is where MAGIC MENU's icon had been: `SS_MENU_X` was set to that. SpaceSaver's icon is at **x=425**, measured by pressing every slot across the bar and photographing what opens, and its menu is `STR# 1024`'s *Turn Idle Time Off / Idle Now / Open Control Panel* — the toggle reading OFF, so idle-time compression was on the whole time. **Cost: an open item aimed at whether the extension installs at all**, and the run that 'proved' it was looking at a hole | 2026-08-25 |
| A coordinate in a vmac harness is right if the run completes and the frames look plausible | two of this session's runs pressed 140 px from the target and photographed a neighbouring menu, and the diagnosis took three wrong theories — window centring, then a cached origin, then Mini vMac's cursor lagging a warp. What settled it in one run was making the harness PRINT `xdotool getmouselocation` next to what it asked for; the pointer was exactly where the code said, and the code said 283 because a constant was defined twice. **Cost: four emulator runs.** A mouse harness that cannot say where it clicked cannot fail visibly | 2026-08-25 |
| The reason SpaceSaver never compresses is that no run combined a matching NAME with a menu command | `--magicname` does both in one run and the frames show the command enabled and applied to the right selection: unchanged. With a **400 KB** subject beside the 11 KB and 3 KB ones: unchanged too, so it is not the size threshold `mCompressFile` @0x5510 enforces either. **Cost: two emulator runs**, and it was a hypothesis for about twenty minutes — but it eliminated the two suspects every earlier run had been circling, and found `INIT 1`, which patches `_MenuSelect`/`_MenuKey`/`_PBEject` and NOTHING in the File Manager: a rename cannot be an event, so the name rule was never a trigger in the first place | 2026-08-25 |
| The Mac OS 9 guest has no usable pointer, so that tier is keyboard-only | it has two. The ABSOLUTE `usb-tablet` the harness makes active moves the cursor **0 px** — Mac OS 9 has no driver for it — and one huge delta to the RELATIVE mouse saturates, because an ADB packet carries ±63 px per axis, so the cursor pins to a corner. Stepped ≤40 px with a closed loop it lands within **3 px** of any target, and a click so aimed dismissed the startup alert on two boots and then drove an installer end to end. **Cost: the tier could photograph the application but not operate it** — no interactive UI run, no installer, no menu — and the claim stood in four files at once, each citing the same probe, whose five click tests had all fired with the cursor in a corner | 2026-08-26 |
| Nothing here can write an encrypted StuffIt 5 archive, because Deluxe 5.0.1 needs a System this machine does not run | Mac OS 9.2 under QEMU runs its installer, and **DropStuff 5.0.1** — installed beside it, same StuffIt Engine — writes them: three specimens at 4, 9 and 17 characters, one two-forked, all byte-exact through this engine (FORMATS.md, *StuffIt 5's RC4*). The Deluxe APPLICATION does not run there, and that part of the claim was right for a reason nobody had guessed: it predates HFS+ and quits at launch on an HFS+ boot volume | 2026-08-26 |
| SpaceSaver's methods 1, 2 and 3 cannot be graded, because nothing reachable writes one | their own `CMod` modules do: each holds a COMPRESSOR at +0x08 as well as an expander at +0x10, and `qemu-m68k` runs either — all three methods round-trip through Aladdin's code in 3 seconds, with no Macintosh in it (`tools/ssmodule/`). The claim was about the ENGINE's choice of method (CPU-gated) and was read as if it were about the codecs. **Cost: the format was declined on 2026-08-22 and the same technique landed for SuperDisk! on 2026-08-25** — three days in which the answer was a directory away, and `sdmodule` had already shown that a 68k codec module runs under qemu | 2026-08-25 |
| ARC 7.x's Trimmed is waiting on a gradeable specimen (OPEN_ITEMS.md, filed 2026-08-25) | the ArchiveTeam wiki lists ARC+Plus 7.10 and 7.12 with direct links; `ARC712.ZIP` is one HTTP GET, its installer archive holds four Trimmed members and a nested one holds three more — **including the writer**, which then generates a corpus under DOSBox. **Cost: none, because it was caught the same day** — but it was filed one paragraph below a withdrawn claim about exactly this mistake, and the entry would have read as a decision for as long as it stood | 2026-08-25 |
| Nothing reachable writes 0x0a/0x0b, so an implementation could not be graded | PAK 2.51 (1990) runs here, headless, under a DOSBox unpacked without root — and writes both on demand (`/CR`, `/O`). It also EXTRACTS, so it grades its own output. **Cost: the methods were declined for a year on the strength of it**, and two real specimens carrying 13 members between them were reachable the whole time | 2026-08-25 |
| `unar` is the oracle for every ARC method, so a transcription error cannot survive it | `unar` decodes method 0x0b **wrong**: right length, wrong bytes, on 6 of the 10 members of `derived-INTRECHO.pak` and on a 1,800-byte case generated here. XADMaster starts Distilled's 8 KB window at zero; PAK fills it with spaces. Upstream is unchanged since 2018, so transcribing the obvious reference would have shipped the bug — and a synthetic round trip would have agreed with it | 2026-08-25 |
| SuperDisk!'s block header carries a 16-bit method, and method 9's Huffman region begins after that header | Alysis's own Add-In Module for method 9, run under qemu-m68k (`tools/sdmodule/`): it reads the region AT the length word, and the reference dispatches on the low byte alone (CODE 2 @0x6ba, @0x712). A real method 9 block says 0x0809 there, so this engine answered `UNC_ERR_UNSUPPORTED` to every one of them. **Cost: method 9 could not have decoded a single real block since it was written**, and nothing said so — no fixture uses it, the unit test builds stored blocks, and "transcribed, compiled and never run" was filed in OPEN_ITEMS.md as a risk rather than tested. The second implementation was inside a corpus fixture the whole time | 2026-08-25 |
| A SuperDisk! single-file container is recognised whatever its size | the head was read as a fixed 64 bytes and a short read failed the lot, so any container under 64 B — the format's own floor is 40 — came back "archive structure is corrupt". Found by a 60-byte synthetic one; the read now asks for what is there | 2026-08-25 |
| Widening the end-of-central-directory scan window is what makes sniffing cheaper | it is worth ~6 % of the instructions and the rest is the byte scan. A POINTER walk over the same window is -30 % of an envelope open, and moving `unc_macbinary_probe` ahead of the scan is -78 % — the scan was never run for 234 of 929 fixtures' worth of work | 2026-08-24 |
| `spacesaver.py` and `sitcrypt.py` end their runs with Special ▸ Shut Down | 123 is **Restart** on System 7. Forty-three of their own `*-special-menu.png` highlight the band y=116..131, and the screenshot taken with 139 highlights Shut Down; `rescomp.py` had already been bitten by the same borrowed coordinate and says so in `tools/vmac/README.md`. **Cost: nothing measurable** — Restart ejects the volumes too, so the flush every one of those runs depends on did happen; what it cost `rescomp.py` once was a torn resource fork that read as a format finding | 2026-09-01 |
| The shortfall the Macintosh reports is "round enough to type and never short" | it is ONE request's shortfall, not the entry's demand. `synth-dd-m5.dd` at the 512 KB budget reports **928 B** and needs **203,680** — the entry takes 1,536 B per distinct context byte and is refused at the first one that crosses the line, so the figure is an artefact of granularity. Both front ends now say **at least**. **Cost: the advice sent a user to Get Info for 8K on an entry that wanted 200K**, and this is the SECOND defect in the same sentence — M46 fixed it firing after a successful extraction | 2026-09-01 |
| The eight-byte record at 144 of `derived-Expand_Now_1.0.1.sea` resembles a Now Compress block table by chance, and the next attempt should not trust it | it is a block table — the SECOND block's record, shape 2, with its 128-byte code table one byte past the offset it names, exactly where that shape puts one. Nothing was wrong with the record; two things around it were, and both were assumed rather than checked: it is not the first block, so its output starts at 32,768 and its matches reach back into a block nobody had decoded. **Cost: one day, and the advice would have cost the next attempt more** — it was written as guidance ("recorded so nobody follows it twice") and pointed away from the answer. The smell is a general one: **a structure that matches in two independent ways is evidence, and "probably coincidence" is a claim that needs its own test** | 2026-09-21 |
| **OPEN_ITEMS.md's table is the inventory of what is still XADMaster's or macutils', and the licence changes when its last row is gone** | one grep — `Source:.*\(XAD\|macutils\)` over `src/*.[ch]` — returns 15 files and **8 of them had no row**: `unc_util.c` and `unc_internal.h` (the three CRC tables and the MSB-first bit reader), `fmt_binhex.c`, `fmt_uu.c` and `fmt_mime.c` (macutils' `hexbin`), and `fmt_foreign.c` with `fmt_sit_probe.c` and `fmt_packit_probe.c` (seven formats' signatures and two recognisers). **Two more needed a second spelling** — `unc_lzah.c`'s preload and `unc_encinfo.c`'s second-hand citation do not put `Source:` and the name on one line — so ten in all, and the grep that found this would have missed two of them. The table had been the DECODER list: every file in it is a format, and the shared primitives were never in it. **Cost: the licence question was being tracked against a count that could reach zero while the code still carried XADMaster** — and two of the files were named in NOTICE as having already left, `fmt_binhex.c` for its own specification and `unc_lzah.c`'s preloads as "this project's", so the two documents that state the position disagreed with the source for a week. The rows are in OPEN_ITEMS.md now — both greps come back with every file accounted for — and membership is grepped rather than remembered. **"The 18 further files the broad one returns carry only 'no longer XADMaster's' notes" is corrected 2026-09-27**: six of them state a LIVE citation without a `Source:` line (`fmt_packit.c` and the four-file tolerance row, beside `unc_lzah.c`), so the strict grep finds 15 of the table's 21 files and the broad one has to be read | 2026-09-26 |
| **`src/unc_internal.h` cites XADStuffItHuffmanHandle.m for the bit-serialized tree and XADPrefixCode.m for the canonical codes** | both facts left on 2026-09-19 and 2026-09-20 — `docs/formats/serialized-huffman-tree.md` and RFC 1951 §3.2.2 with puff.c — and NOTICE, `unc_huffman.c`'s own header and the inventory all say so. The declarations' comments in the header were not touched. **Cost: nothing executable, and the two shedding passes that moved the file were recorded as complete** — the same fact was cited two ways in two files for six days, which is what the no-duplication rule exists to prevent | 2026-09-26 |
| **CLAUDE.md: BLOCKERS' withdrawn-claims archive "is another 15k"** | it is **~42k tokens** — 169,105 characters at the four-characters-per-token proxy that makes the same sentence's other figure read 14k, and 164,442 before the rows below it were added. 15k was right when it was taken on 2026-08-26 (64,654 characters) and the archive has since grown two and a half times. **Cost: the sentence was CORRECTED on 2026-09-26 for exactly this — 7.5k had drifted to 14k — and the second number in it was carried through the correction unmeasured**, so the pass that added "re-measured 2026-09-26" left a figure from a month earlier three words later. A reader deciding whether to open the archive was told a quarter of its size | 2026-09-26 |
| **CLAUDE.md: BLOCKERS "names the thirty-three smells that keep finding the next one"** | **the list had thirty-five**, which is what BLOCKERS.md's own sentence said: two bullets had been added on 2026-09-26 after CLAUDE.md's count was written the same day. It is thirty-eight now. **Cost: none yet — it is the third time this count has been wrong** (ten over thirty on 2026-09-26, and ten in CLAUDE.md before that), so `tools/check_docs.py` now counts the list and compares both sentences to it. A count written above a list is the cheapest claim here to check and the least likely to be checked | 2026-09-26 |
| **`src/unc_util.c`'s three CRC check values "are asserted in `tests/unit_util.c`"** | **no such file has ever existed** — `git log --all --diff-filter=A` returns nothing for it. The assertions are real and in two other files: `tests/unit_main.c`'s `test_crc` for CRC-16/XMODEM and CRC-32, `tests/unit_formats.c` for CRC-16/ARC beside an independent bitwise implementation. **Cost: none to the engine, and it was believed twice in one hour** — the sentence was quoted into an OPEN_ITEMS row and a DECISIONS entry written today, as the evidence that re-citing those tables would be free, before anybody ran `ls`. It is the same shape as the FIPS 197 citation withdrawn this morning, one directory closer: a citation to something on this machine is the cheapest in the repository to check, which is why nothing checks it | 2026-09-26 |
| **`src/unc_crypt.c`: "Seven schemes across the five formats that can encrypt an entry"** | the list under it has **eight schemes across six formats**, which is what FORMATS.md's *Encryption* and PROGRESS.md's M25 say. FORMATS.md and TESTING.md were corrected for this same count earlier on 2026-09-26; the source file the provenance table is read against was not searched. **Cost: none measured** — but it is the file whose cipher inventory the licence rows are counted from, and "eight ciphers" is the phrase BLOCKERS.md, TESTING.md, DECISIONS.md and PROGRESS.md all use | 2026-09-26 |
| **No file written by SpaceSaver itself is reachable, so the container cannot be graded; the only route left is a person with a copy of the software** | **142 of them** are on Apple Developer, MacTech, Apprentice, Info-Mac and HyperLib CD-ROMs, found by searching Discmaster's *detections* index for the eight magic bytes `SIT!DFD3`, which `file` prints verbatim — 296 hits, 142 with a parseable header, covering every method (0, 1, 2, 3, 4) and both header versions. **48 are installed as specimens and 46 of those carry the uncompressed original**, on a pressing made before that mastering machine had SpaceSaver on it; all 46 decode byte-exact. **Cost: about twenty emulator runs, a MANUAL_TESTS.md section asking somebody outside this machine to compress a file, and an open item that stood for five weeks.** The search that was never run is the one that names the format's BYTES rather than its name: no archive site lists a file as "SpaceSaver", because SpaceSaver renames nothing | 2026-09-26 |
| **AppleLink `.pkg`: no specimen has ever reached this project, and one is what the format waits on** | two shipped **beside AppleLink 6.1 on fifteen Apple Developer CDs** — `ALink.PKG` (6,900 B) and `Read First.PKG` (1,373 B). **Cost: seven boots trying to make Aladdin's own software read a package written here, and a detect-only decision taken because nothing could grade a decoder** | 2026-09-26 |
| **An AppleLink package is probably a transfer manifest naming files that sit beside it** (hypothesis, 2026-08-23, from three measured things) | both packages are **binary containers**: each record holds two lengths, a type, a creator, Finder flags, a Pascal name and two Macintosh dates at fixed offsets, with non-text data after them. `Read First.PKG` holds `TEXT/ttxt` "Antipiracy-Read Me First", a file whose uncompressed copies are on the same CDs. **Cost: the hypothesis shaped the open item for five weeks and was the reason `.pkg` was filed as *possibly nothing to decode*** | 2026-09-26 |
| **`macextract sniff` "is exactly as strong as Aladdin's" on `.pkg` — 0 false positives across 928 fixtures** | the measurement is real and the claim drawn from it is not: **neither real package passes the test**, so the probe names something that is not the format. `ALink.PKG` sniffs as *unknown*; `Read First.PKG` sniffs as **Compact Pro segment**, because `unc_cptseg_probe` takes any file with byte 0 = 1 and a zero longword at 4. **Cost: a shipped detect-only row that has never been true of a real file, and a false positive in a second format** — a false-positive rate measured over a corpus with no specimen of the format is a fact about the corpus | 2026-09-26 |
| **`tools/run_spacesaver.py` grades a specimen against the `.orig` beside it** | it looked for the decoded file under `basename[:-3]` — the specimen's name with `.ss` removed — and the CLI deliberately keeps the WHOLE basename for this format, because SpaceSaver adds no extension (`cli/main.c`). Every grade would have reported FAILED. **Cost: nothing, only because no specimen had ever existed** — the harness was written for files that had not arrived, ran green for five weeks by skipping, and the first real one failed 46 out of 46 | 2026-09-26 |
| **`src/fmt_sit.c` "owes XADStuffItParser.m, XADCompressHandle.m and `macunpack/sit.c` nothing at all" since 2026-09-22** (NOTICE, the file's own header and OPEN_ITEMS.md's inventory row, in those words) | the file carries `Source: XADStuffItParser.m decryptHandleForEntryWithDictionary` over `sit_fork_crypt` — the ENCRYPTED fork's key layout, sixteen bytes at the end of the fork and the pad count at header offset 104. The shedding of 2026-09-20 to 2026-09-22 took the plain path and was written up as the whole file. **This is the third file recorded as shed while still carrying a citation** — `unc_lzah.c`'s preloads and `fmt_binhex.c`'s two macutils rules were the others, both above — so "a file's own header says it has left" is not evidence that it has. **Cost: five days in which NOTICE, the one document whose job is the licence, named the wrong set of sources**, and an inventory row that read as closable when the item it was missing has no published description at all. Nothing executable; the fork still decrypts, graded by StuffIt Deluxe 3.5.1 on three archives it wrote (FORMATS.md, *Encryption*) | 2026-09-27 |
| **The detect-only signatures' replacements "are in each format's own published description, none of which is on this disk"** (OPEN_ITEMS.md's XADMaster inventory, the `fmt_foreign.c` row) | the cell asked about DESCRIPTIONS and was believed about implementations. **deark states eight of the ten** — ARJ with its header bounds and basic-header CRC-32 (`modules/arj.c`), RAR's three generations (`rar_get_fmtver`), Cabinet, Zoo, bzip2, 7-Zip, xz (`modules/unsupported.c`, `get_fmt`) and PackIt's recogniser — and `tools/build_deark.sh` compiles it on every `ci.sh` run. The ninth is `bzip2 -c < /dev/null`, one command here; the tenth is the StuffIt wiki table `fmt_sit.c` already cites. **Cost: five weeks of a row filed as unclosable that closed in an afternoon with no rewrite** — and it is *an oracle that was never asked* a second time, after method 6 cost four weeks of "macutils is the only reference" while deark implemented it under MIT. The question that finds this class is not "is there a description?" but "does anything here READ this format?" (DECISIONS.md 2026-09-27, *the signatures that were already on the disk*) | 2026-09-27 |
| **`src/unc_internal.h`'s XADMaster and macutils content is "the three CRC tables and the MSB-first bit reader"** (OPEN_ITEMS.md's inventory row, added 2026-09-26) | it is five things, across four subjects. Besides those two the header carries the MIME line reader's `readline.c` rule, `Source: XADDiskDoublerParser.m case 8` for DiskDoubler method 8, and a second statement of the LZAH window preload. With the CRC tables and the bit reader re-cited on 2026-09-27 the row was empty and the file was one edit from leaving the table with three live citations in it. **Cost: none yet, caught while closing the row** — but this is the second time this header has been read as belonging to whichever subject was being worked on, after the 2026-09-19/20 shedding passes left its Huffman declarations naming files that had gone (above). **A shared header collects citations from every subject that uses it**, so the mechanism is: a row naming one item of a shared file reads as naming the file (DECISIONS.md 2026-09-27, *the tables that said they were generated*) | 2026-09-27 |
| **NOTICE states what this project borrowed and from whom** — it is the licence notice, and the file that has to be right | it named neither `src/fmt_uu.c` nor `src/unc_lzdyn.c`, and both carry borrowed code: UUTool's MU layout and macutils' mailed-text rules in the first, and the whole of `-lh2-` and `-lh3-` from `XADLZHOldHandles.m` in the second. Found on 2026-09-27 by `tools/check_provenance.py` the moment it was first run, before it was wired into `ci.sh`. **Cost: unknown and possibly zero in law — but it is the one kind of staleness that matters**, and it had survived every reading of a file that has been edited dozens of times, because **prose is worst at absence**: nobody scans a paragraph for the file that is not mentioned. The inventory is a checked list now, and NOTICE is its only copy (DECISIONS.md 2026-09-27, *the inventory that was kept twice*) | 2026-09-27 |
| **`tools/check_provenance.py` fails when a file in CARRIES sheds its last citation, so a row cannot stay in the inventory after it is empty** (its own docstring, and DECISIONS.md the same day) | **it passed `src/fmt_mime.c` within the hour of being written.** That file's only live citation, the uu terminator, moved to mpack and left behind one sentence saying it had been macutils' until then — and the check tested whether a file MENTIONS either reference, which shedding properly does not stop. The single event it existed to catch was the one it could not see. Fixed by testing the `Source:` marker NOTICE already specifies rather than the mention, with a selftest asserting liveness is a STRICT subset of mention so the two can never collapse again; six carriers were normalised to the marked form on the way. **Cost: nothing, caught the same hour by using it** — and the lesson is about checks, not licences: **a check's predicate has to be the thing that CHANGES at the event** (DECISIONS.md 2026-09-27, *the check that tested the wrong thing*) | 2026-09-27 |
| **`src/fmt_sit.c`'s encrypted-fork layout needs a specimen written to order — StuffIt Deluxe 3.5.1 runs here, so the route is an emulator session** (OPEN_ITEMS.md's route column, written 2026-09-27) | **the specimens were already on this disk**, written 2026-08-23 by `tools/vmac/sitcrypt.py` under three passwords while settling the archive key's fold count, with both forks' plaintext in `made.json` — and `tools/run_crypt.py` has graded the engine against them on every run since. No emulator session was needed; the measurement was two one-line perturbations of `sit_fork_crypt`, each of which took the three archives from 0 problems to 24. **Cost: a few hours of a route being written down as harder than it was** — and it is *the magic in somebody else's index* again, with the thing one directory away rather than one index away. **Before filing a route that needs new evidence, look for the evidence a PAST question already produced** (DECISIONS.md 2026-09-27, *the layout Aladdin's own output settled*) | 2026-09-27 |
| **`src/fmt_sit5.c`'s encrypted-header reading "has no specimen either — all 31 corpus archives read 0x10 here and none is encrypted, so the only archives that exercise it are the ones `tools/run_crypt.py` synthesises, which cannot grade it"** | **three encrypted StuffIt 5 archives written by DropStuff 5.0.1 had been in `~/.cache/macextract/sit5/specimens/` since 2026-08-26**, named in FORMATS.md the whole time. They read 0x90, and they grade bit 7, bit 4's 14-byte shift (load-bearing: the shifted offset's length byte is 5, the unshifted one's is 13) and the MD5-of-MD5 password hash at 4, 9 and 17 characters — with no engine and no reference in the loop (`tools/derive_sit5crypt.py`). Only bit 5 is left. **Cost: a month of a reading filed as ungradeable while the archives that grade it sat in the cache** — the THIRD such find on 2026-09-27, after deark's signatures and StuffIt Deluxe's encrypted forks. **A claim that no specimen exists is a claim about the last search, and searches are indexed by the question that prompted them** (DECISIONS.md 2026-09-27, *the second cache nobody looked in*) | 2026-09-27 |
| **StuffIt Deluxe 5.0.1 will run on a guest whose boot volume is HFS rather than HFS+** — filed 2026-09-27 as the route for `fmt_sit5.c`'s bit 5, from the alert's own words, *"an update to this software is required for compatibility with the improved Mac OS file system"* | **it will not.** A 1 GB plain-HFS volume was built with `tools/vmac/mkapmdisk.py`, the System Folder copied onto it inside the guest (1,751 items), and QEMU relaunched with it as index 0; it became the startup disk — top of the desktop volume icons, no *"did not shut down properly"* alert, the HFS+ volume up ~500 MB as its swapfile went idle. The application raises the identical alert, and does so in **all four combinations** of boot volume and application volume. The trigger is Mac OS 9.2, not the file system. **Cost: the route was filed twice in one day — once from the alert's text, once refined after a partial test — before anything disproved it**, and the disproof took about ninety minutes. **An error message's noun is a hypothesis about the cause, not a statement of it** (DECISIONS.md 2026-09-27, *the file system was never the problem*) | 2026-09-27 |
| **`tools/fuzz.py` is a "randomized robustness pass across all formats"** (its own docstring, and TESTING.md's summary of it) | **it reaches the formats the CORPUS has, which is not the same set.** Measured 2026-09-27 with `tools/fuzz_cover.py` — a coverage build, 3,000 cases, seed 11: `src/unc_lzdyn.c` is **16 of 16 functions never entered**, the whole `-lh2-`/`-lh3-` decoder, and DiskDoubler's methods 3, 4 and 7, ARC's Crush and three of Arsenic's index helpers are never entered either. Three of the four generators mutate a corpus fixture, so **the fuzzer's reach is the corpus's coverage**, and every method this project grades by GENERATING a file rather than owning a specimen is graded for correctness and fuzzed not at all. Now Compress has a second cause: its archives are in the corpus and its coders are still unreached, because a 32-bit sum gates the block table and a random mutation destroys it — **the gate that hid the one heap overflow ever found in a decoder here**, `now_next_block` checking a length against `incap` where the buffer is `blkcap`, found by a crafted archive under ASan. **Cost: not yet known — no defect is known to be hiding in the unfuzzed set, which is exactly what could not be said before this was measured.** It is the cipher finding of 2026-09-23 in the other half of the engine, and has the same remedy: a seed per method (DECISIONS.md 2026-09-27, *the fuzzer that could only reach what the corpus had*) | 2026-09-27 |
| **Giving `fuzz.py`'s Now Compress repair generator a sixth of the cases starved the other formats** — inferred 2026-09-27 from one 3,000-case run in which the total never-entered count rose from 132 to 149 and StuffIt classic went from 0 functions to 7 | **per-family reach is that noisy between runs.** At a twentieth the total went to 163, higher than at a sixth, which is not monotonic in the weight; and an identical build at seed 12 instead of 11 gives StuffIt classic 1 where seed 11 gives 6, ARC 10 where it gives 6, and Compact Pro 1 where it gives 4. Changing a generator changes the whole RNG consumption sequence, so every run is a different sample of ~950 fixtures. **Cost: one wrong causal sentence written into `fuzz.py` and nearly into TESTING.md, and a weight chosen for a reason that was not real** — the twentieth is kept, on the ground that it reaches the coders at two seeds, which is a claim the instrument can actually support. **A measurement with no noise floor cannot support a delta**; the floor took one extra run to establish, and was put at about five functions per family — corrected to **thirteen** on 2026-10-05, *Corrected figures*, below (DECISIONS.md 2026-09-27, *the delta that was a draw*) | 2026-09-27 |
| **`-lh3-` is graded against LHa itself on six cases, so its decoder is exercised** — TESTING.md and `tools/run_lzh.py` since 2026-08, and the reason `-lh2-`/`-lh3-` were kept (OPEN_ITEMS.md, Part 1) | **the decoder's LZSS half had never run.** `lh3_stream()` Huffman-codes the 256 byte values and emits nothing above 255, so no `-lh3-` stream this project has ever written contains a MATCH — and those streams are the only `-lh3-` files anywhere here, the corpus having none. `lzs_decode_p` and the copy loop were at 0 % on the UNMUTATED seed, which is how it surfaced: a coverage run for the FUZZER found a hole in the correctness suite. LHa agreeing on six literal-only streams says nothing about match decoding. **Cost: unknown, and the decoder is one of the two this project keeps for a licence it cannot change** (Part 1) — the match path is now graded by four cases through LHa and through this engine, `-lh3-` entries 6 → 10, and every function is reached. Writing the encoder found two of its own bugs, both caught by LHa: the block size is a count of SYMBOLS, not bytes, which a literals-only stream cannot tell apart; and the longest match is 31, not the 32 the alphabet's arithmetic implies (DECISIONS.md 2026-09-27, *the encoder that only wrote literals*) | 2026-09-27 |
| **`src/fmt_lzh.c`'s NUL-ends-the-name rule is XADMaster's alone, because "the document does not mention it and lhasa takes the whole field"** — the file's own comment, `docs/formats/lzh-header.md` and OPEN_ITEMS.md, all since 2026-09-22 | **lhasa produces the same filename.** `process_level0_path()` copies the whole field and NUL-terminates it, and every consumer then handles it as a C STRING — `strrchr` in `split_header_filename`, `strdup`, and `strlen`/`sprintf` in `lha_file_header_full_path` — so anything after an embedded NUL is unreachable. "Takes the whole field" is true of the bytes it copies and false of the name it yields. The two references differ only in whether the trailing bytes surface as a COMMENT, which this engine has nowhere to put and drops, agreeing with both. **Cost: five days of a file carried in the provenance inventory that had nothing uniquely XADMaster's in it, and a decision put to the maintainer that did not exist** — the two readings were never in conflict about anything this engine emits. **A claim that two implementations disagree is a claim about their OUTPUT, not their source text**; this one was read off what lhasa stores rather than what it yields (DECISIONS.md 2026-09-27, *the rule both references already followed*) | 2026-09-27 |
| **The AppleLink `.pkg` expander is in `'Eng ' 2` of `StuffIt Engine™`** — 26,362 bytes, from `PKG Expand Translator` @0x334c doing `GetResource('Eng ', 2)` and jumping in (DECISIONS.md 2026-09-27, FORMATS.md and OPEN_ITEMS.md, all since then) | **`'Eng ' 2` is the StuffIt/PackIt unstuffer**, and no `'Eng '` resource is a package expander. Those `GetResource` sites are not two, they are **fourteen** — a complete 7 × 2 table of thunks, one pair per `'Eng '` id — reached from a seven-way if/else-if chain of recognisers, **none of which tests `.pkg`**: `'Eng ' 2`'s branch tests the file TYPE `HBSF`, and the resource itself tests node+32 against `SIT!`, `PIT ` and `HBSF`. `'Eng ' 1` is Compact Pro — `PACT`/`CPCT` is Compactor (`reference/macutils/README`), and its header parser and error numbers match `src/fmt_cpt.c` and `STR# 211` (*"it is not a Compact Pro file"*, *"this is a segmented archive"* for a zero index offset) field for field. The translator carries no AppleLink code at all: its `'Othe' 0` is *named* `CompactPro`. **The real reference implementation is 3.0.7's `AppleLink Package Translator` 3.0.3**, 33,300 bytes with 148 MacsBug symbols, and the format is SqueezePlay — read, and graded 4/4 on both packages the same day (FORMATS.md, *AppleLink packages*). **Cost: eight days of `.pkg` filed as blocked on a reference that had been in the 3.0.7 installer the whole time**, and a 26 KB resource named as the thing to disassemble next. The sample was never the table: two of fourteen call sites were read as "the engine call for this format", and the id they named belonged to another format (DECISIONS.md 2026-10-05, *the sample that was read as the table*) | 2026-10-05 |
| **Three AppleLink container paths — a resource fork, the stored mode, version 0 and folders — can only be graded against `tools/synth_sqp.py`, because no real package reaches them** — FORMATS.md and OPEN_ITEMS.md, 2026-10-05, with *"the two real packages remain the only authentic bytes anything is graded on"* | **there are 49 real packages in the same index the first two came out of, and six of them reach every path.** The two were found in 2026-09 by PATH — `AppleLink 6.1` on fifteen Apple Developer CDs — in the same entry whose stated lesson is that a format which renames nothing needs a search by MAGIC; the magic search was run on SpaceSaver that day and not on this. Discmaster's `detection=` field is also full-text over the **first 16 bytes of every file**, and a version-1 package's first 16 bytes are a hex token: 1,443 files listed, 36 packages, and 13 more including every version-0 one from `extension=.pkg&family=unknown`. 20 of the 49 are not called `.pkg`. The specimens now carry **30 members with a resource fork, both stored bits, 14 folders nested four deep, 50 clear codes and a 541,179-byte member**, and `derive_sqp.py`'s own *UNEXERCISED by these packages* line reads **nothing**. **Cost: `tools/synth_sqp.py` written to reach five paths that real packages reach, seven Mini vMac boots on 2026-09-01 spent trying to hand a package to the translator's sibling, a MANUAL_TESTS.md request, and the generator bug the generator-and-decoder agreement hid — a folder's type and creator being its window rectangle, which any of 14 real folders would have caught in one run** (DECISIONS.md 2026-10-06, *the lesson that was written down and then not applied*) | 2026-10-06 |
| **"Nobody else states the CR/LF line rule"** — `src/fmt_uu.c`'s header and OPEN_ITEMS.md's mailed-text row, reached from "mpack is LF-only" | **deark states it**, in the same file `src/unc_internal.h` already cited for the bit reader: `dbuf_find_line` ends a line at CR, at LF or at CR+LF and treats an unterminated last line as a line, and deark's own uudecode skips the blank line a CRLF leaves behind. The 2026-09-27 sweep read deark for that row's OTHER rules and never asked it about this one. **Cost: nothing but the row** — the readers did not change, and two files came off the inventory's mailed-text item. The smell is a new one: **a negative result is about a (reference, fact) pair, and this cell recorded one as if it were about the fact** (DECISIONS.md 2026-10-05, *the negative that was about one rule*) | 2026-10-05 |
| **"This machine has no Mac OS install media"** — OPEN_ITEMS.md's route column for `fmt_sit5.c`'s bit 5, since 2026-09-27, and the reason that row was filed as blocked | **the retail Mac OS 8.6 install CD is a 304 MB download from the host this project already fetches `MacOS9.img` from.** `archive.org`'s own search API answers 33 items for Mac OS 8 and 23 for 8.5/8.6; `mac-os-8.6-working-iso` extracts to a 665,600,000-byte volume `file` calls *Macintosh HFS data (bootable)*, which `hmount` opens — `System Folder`, `Install Mac OS 8.6`, `Utilities`, created 1999-04-16 — and two more routes sit beside it, a 1.65 GB pre-installed 8.6 hard-disk image and the 8.5 retail CD as a `.dmg` (`tools/vmac/README.md`, *Mac OS 8.6 media*). **Cost: nine days of the last StuffIt 5 item being filed as needing a person outside this machine, when it needed one query against a site already in `os9.py`.** The claim was never about the world: it was about a search nobody had run — the same disproof as the two rows above it, on the same day (DECISIONS.md 2026-10-06, *the media that was one download away*) | 2026-10-06 |
| **"Nothing has seen a StuffIt 2.x archive this project did not make"** — OPEN_ITEMS.md, 2026-10-02 | **two Giga-ROM CD archives carry a `Text 1`-optimized entry**, at methods 8 and **3**, id 255, resource fork deleted, and both are fixtures since 2026-10-06 (FORMATS.md, *Two optimized archives nobody here made*). The key is the Optimizer bit `0x40` on an entry's method byte — per-ENTRY, so the search is a `Range` scan of entry chains rather than an index lookup: **21,767 headers in 16,727 archives**. **Cost: none to any claim — the item was honest — but the measurement it produced is what the row could not state**: 7 Optimizer bits in 21,767 wild headers, all 7 the same module, so the four reversible Optimizers and five ciphers are rare rather than unlooked-for. Two harness defects on the way, and the dangerous one is the probe's flag bits: they were the PUBLISHED table's, where `0x10` is a folder marker, and this repository had measured on 2026-10-02 that it is `NewDE` (DECISIONS.md 2026-10-06, *the Optimizer that was in somebody else's corpus*) | 2026-10-06 |
| **"Appendix B lists 'PMa5' twice, so the document cannot name the fourth word and XADMaster is where 'PMa6' comes from"** — `src/fmt_packit.c`, `tools/derive_packit.py` and OPEN_ITEMS.md, since 2026-09-21 | **the document names it.** `reference/notes/packit_unpackit.txt`, the (L)ist command's section: *"PMa6 - compressed and DES encrypted (PACKIT III)"*, two pages before the appendix whose table duplicates `PMa5`. **Cost: nothing measurable, and the mechanism is the point** — the container was derived from appendices B and C in 2026-09-21, so the appendices are what got re-read, and a claim about THE DOCUMENT was made from the part of it the task needed. A document is not one claim. Found by opening the file to quote it while writing up the entry that supersedes it (DECISIONS.md 2026-10-05, *the reference implementation was the fixture's payload*) | 2026-10-05 |
| **PackIt's `keytr1` "has no other statement at all"** — OPEN_ITEMS.md, *The licence cannot move*, where it had been filed as irreducible, and **"`unar -p` adjudicates" both PackIt ciphers** — TESTING.md, *Decryption* | `keytr1` IS **FIPS 46-3's PC-1**, and the code that applies it is in the corpus: `Packit III 1.3`, a member of the fixture `packit.pit_.bin`, carries both ciphers in its `CODE` 1 and all nine DES tables in its `CODE` 256, and `tools/pitcrypt/pit_run.c` RUNS them under `qemu-m68k`. The second claim was worse than wrong: `unar` is XADMaster, which is where both ciphers were transcribed from, so the only test either had **could not fail on a shared mistake**. **Cost: eight days in Part 1 for one of them** — filed 2026-09-27 as having no route, while the fixture the container derivation was graded against carried the writer — and both ciphers ungraded by anything independent for the fourteen months they have been read. Three archives PackIt's own code encrypted now grade them every run (DECISIONS.md 2026-10-05, *the reference implementation was the fixture's payload*) | 2026-10-05 |
| **"The uu alphabet is UUTool's two encode tables"** — `src/fmt_uu_priv.h`, `src/fmt_uu_probe.c` and FORMATS.md's *uuencode: three alphabets* table, written 2026-10-06 from the application's own `HEXA` 128 and 129 | **the two tables are right and their union is narrower than the range they replaced.** `0x20..0x60` had been the alphabet since M13; the "PC" half was written as `0x20..0x5f`, and `0x60` is the standard alphabet's OTHER spelling of zero — every Unix `uuencode` since 4.2BSD writes ``` ` ``` for the value 0 so trailing-whitespace stripping cannot eat it, and `reference/mpack/uudecode.c` takes either. A line holding a zero AND a value under 27 then fitted neither half, and "fits neither" is the branch that SKIPS mail in mid-stream. **Cost: one day in which no file written by BSD or GNU `uuencode` was recognised at all, and `-f uuencode` listed one as 0 bytes and wrote an empty file with exit 0** — a silent decode of nothing, in the one format with no checksum anywhere to object. Nothing could fail on it: `synth_uu.py` writes the standard alphabet with `binascii.b2a_uu`, which spells zero as a space, so all four plain cases held one spelling and both wild specimens are UUTool's. The smell is new and is the asymmetry itself: **a classifier whose "no" branch is a skip cannot report a narrowing** (DECISIONS.md 2026-10-06, *the spelling the tables did not have*) | 2026-10-06 |
| **"An empty package names nothing and is indistinguishable from a file of zeros, which is why this is a test and not a tolerance"** — `src/fmt_sqp_probe.c`'s own comment on its `n < 1` test, since 2026-10-05, and the argument the whole probe's worth rested on | **`n < 1` keeps nothing out.** A 96-byte file of `01 00` and 94 zeros has a count of ONE in its first byte, and the **tiling test — the one test that makes a magic-less probe worth anything — cannot fail on it**: every compressed length is 0, so `lo` stays at `fsize`, `hi` at `start`, and `sum == fsize - start` holds with both sides zero. It sniffed as *AppleLink package* and `l` listed one 0-byte entry named `_`; so did a 198-byte version-1 file of zeros with four bytes planted. What refuses them is the **lower bound on a record's name length**, 1..31 because the name is the HFS catalog's own (`AddItems` @0x22ac/@0x22be/@0x2354), measured at 7..29 over 53 records of all 8 real packages. **Cost: one day in which any file of zeros whose length is `10 + 86n` was claimed as an archive and listed as holding a nameless entry, and ten negative controls that could not have found it** — lane 4 bends a valid package one test at a time, so every input it makes is a package with one thing wrong, and no bend can report a test that is MISSING. The smell is new and general: **negative controls derived from a positive measure each test's necessity and never the set's sufficiency.** `sum > 0` is the obvious fix and is also wrong — it refuses a package whose one member is an empty file, which is a record Aladdin's writer produces, and costs 2 B more (DECISIONS.md 2026-10-06, *the directory of empty records*) | 2026-10-06 |
| **"`EXPECT_BUNDLE` holds the `'OVLY'` bundle's size, so the bundle cannot grow unremarked"** — `tools/check_app_size.py`'s whole reason for watching it, and the sentence FORMATS.md's *Overlays* leans on when it quotes the bundle, the download and the launch read as figures that "move together" | **it was 1,924 B stale for a day and nothing went red.** `ovl_exo` grew 29,252 → 31,176 B on 2026-10-07 for zip method 6; the bundle figure in *Overlays* and the launch-read SUM beside it were both corrected that day and `EXPECT_BUNDLE` was left at 156,068, as was the launch read's stated DIFFERENCE — which then quoted 25,860 B where its own two terms gave 27,784. The check reports the bundle rather than failing on it, 1,924 B being inside a 2,048 B tolerance, so the one instrument that could have caught the other two printed the growth as information. **Cost: nothing on any machine — the bundle is not resident and no tier tally depends on it — and a day in which three of the four places that quote one number disagreed, in a repository whose cheapest disproof is two files disagreeing.** The mechanism is new and is about the tolerance rather than the constant: **a ratchet whose tolerance is wider than the change it is watching for reports instead of failing, so it is a measurement and not a check.** Found 2026-10-08 by raising the same constant for the next change to the same image (DECISIONS.md 2026-10-08, *the second attempt that had nowhere to go*) | 2026-10-08 |
| **"Per ARCHIVE and not per entry, because a zip has one writer"** — `src/fmt_exo.c`, `tools/synth_implode.py`, FORMATS.md and DECISIONS.md, all written 2026-10-08 as the REASON the minimum-match-length verdict is settled once | **the measurement is narrower than the claim, and the format is wider.** What the sweeps show is that no archive of 1,537 mixes the two readings — 29,799 bug-capable entries, each classified on its own, which is good evidence about a population. A zip is appendable and PKZIP 1.1 wrote Implode as well as fixing the bug, so an archive updated across that boundary is a shape the FORMAT allows; deark settling per archive too is one implementation's choice, which is the corroboration `UNC_PATH_MAXDEPTH` was withdrawn for. **Cost, measured on a three-entry archive the project's own encoder wrote: two entries lost where one was unavoidable, and both reported as "file is truncated" when nothing was short** — a desynchronised decode runs out of input. An inherited verdict that fails now costs the entry it was wrong about and not the rest of the archive, at one probe pass on a path that had already failed, and the report is a checksum failure (DECISIONS.md 2026-10-08, *the writer a zip is allowed to have twice*; graded by `tools/run_implode.py` lane 4) | 2026-10-08 |
| **"Rescuing that entry means either buffering a fork or a restartable sink"** — DECISIONS.md, *the writer a zip is allowed to have twice*, and the 01df57b commit message, 2026-10-08 | **there was a third route, and it was never priced:** settle the verdict once per *version made by* value. Tested the same day against PKZIP itself under DOSBox: 1.10 keeps the 0x000a stamps of records it did not write, so the key is sound. But the shipped 1.01, 1.02 and 1.10 writers never write a disagreeing combination (0 of 138 Implode entries), so there is nothing for the key to separate, and the one real 1.0x-plus-1.10 archive already extracts in full. **Cost: nothing.** The route displaced no capability, because no archive in reach needs it. The mechanism is the usual one, though: "the only ways are X or Y" was written from the shapes that had been priced, not from the space of shapes (DECISIONS.md 2026-10-08, *the key that survives and has nothing to separate*) | 2026-10-08 |
| **"The 3 entries between 2,247 and 2,244 are UNEXPLAINED: the sweep's working set was not kept, so which three the C run did not reach cannot be re-derived here"** — FORMATS.md, *Shrink*, *What grades it*, 2026-10-08 | **the working set was in `/tmp` all along, and there were no three.** The 346 files, the scripts and both per-entry tables survived; graded again entry by entry, the transcription and the engine agree on all 2,246 distinct entries. The two totals counted different entries: the C comparison listed through Python's `zipfile`, which refuses two RISC OS zips over the `0x4341` extra field (15 entries), and counted `Thief35.zip`'s 12, which the transcription never parsed — and both counted one entry twice, because the random draw re-picked a Mac-context archive. **Cost: a day of the decoder's grading reading as incomplete, and nothing it displaced.** The smell is *cannot get one* aimed at this machine's own disk, and a difference of totals read as a difference of decoders (DECISIONS.md 2026-10-09, *the three entries that were the harness's*) | 2026-10-09 |
| **"A check of the enclosed message's `Content-MD5`, which mpack writes and which disagrees here"** would close both wrong `message/partial` anchors — OPEN_ITEMS.md, 2026-10-11 | **it disagreed on the right anchor too.** Our mpack and munpack were built LP64, where `md5.h`'s `unsigned long` `UINT4` is 64 bits: `abc` hashed to `eZncdeja…` instead of RFC 1321's `kAFQmDzS…` on every message they wrote, and munpack, wrong the same way, never warned. Rebuilt with that line edited, the check catches both anchors and passes the good set — and was then declined for its size (OPEN_ITEMS.md, *Out by the brief*). **Cost: a check built against that specimen would have refused every correctly joined mpack set; and six weeks of an oracle pair that could not fail on a digest.** The smell is two oracles from one source agreeing (DECISIONS.md 2026-10-11, *the digest our own oracle could not compute*) | 2026-10-11 |

**"The DD reader's structure is right; it is literal VALUES that are wrong."**
Written 2026-09-20 about the two forks of `derived-Terrainman_2.0__.sea`
`tools/derive_dd.py` could not read, and supported by three real
measurements: the decode consumed exactly the literal and offset counts the
block header states, the literals landed at the output offsets the correct
file has them at, and two literals sharing one code wanted different bytes.
Every one of those observations holds. The conclusion drawn from them does
not: **nothing was wrong with the literals.** Method 10 has a second form in
which the coder's whole output is the fork's first difference, matches
included, and the fork is the running sum of it. Both forks read with it, so
the corpus is 39 of 39 (docs/formats/diskdoubler-dd.md, *The second form*).

**Cost: method 10's citation of `XADDiskDoublerDDnHandle.m`, for as long as
the two forks stood** — the row was explicitly held open on them ("94 % of a
format is not a description of it"), so one undescribed transform kept a
licence row open. The smell is a new one, and it is worth keeping: **a
diagnosis that explains the failures and not the successes.** The reading
under test accounted for the 11 literals that were wrong and never asked why
the other 19 were right — and under the true reading all 5,443 of them are
right, which is the kind of number a correct rule produces and a patch never
does. When the substitution trace was re-run with the match sources checked
as well, 3,213 of 3,380 matches were wrong: the defect was never in the
literals at all, and the instrument that would have said so — checking the
part of the decode that was ASSUMED good — cost one extra line.

**"A Now Compress back-reference cannot reach further back than the fork has
produced."** Written into `src/fmt_now.c` as the justification for sizing the
sliding history from the archive's LARGEST FORK rather than the format's
32 KB, which is what lets a small archive open in a 400 KB partition. The
same file says the opposite seventy lines earlier — "a block that starts a
stream reaches back into the history the PREVIOUS stream left behind. The
reference calls this absurd and does it anyway; so do we, because the bytes
require it" — so the window spans MEMBERS, and a match in the third member
can name an offset longer than any one fork in the file. Disproved by an
archive Now Compress itself wrote, four members of 4 to 6 KB: two of them
name offsets of **6,228 and 13,000 bytes against a 6,000-byte window** and
came back *archive structure is corrupt*. The bound is now the SUM of every
fork, still capped at 32 KB, and all four extract byte-exact; **no fixture's
peak heap changes**, because every Now archive in the corpus already has a
fork over 32 KB. The cap itself was then measured rather than assumed: an
archive whose fifth member is a copy of its first, 64 KB back, takes a
largest offset of **32,766** (`--case reach`), so 32,768 is the encoder's
window and the offset table's reach to 65,791 is capacity nothing writes.

**Cost: nothing yet, and only because no archive in the corpus has a match
that crosses a member.** Two of the corpus's Now archives are real, thirteen
are this project's own synthetic ones, and eight came from the encoder —
and the eight were single files or two dissimilar members, so none of them
could produce one. The smell is two this file already names, together: **a
limitation inherited as a premise rather than measured** (the sentence is
an assertion about the format, in a comment, with no specimen behind it),
and **inputs from outside the corpus** (`nowcompress.py --case probe`, four
members chosen to be similar to each other, found it on the first run). The
new one worth keeping is narrower: **an optimisation justified by a sentence
that another comment in the same file contradicts.** A cross-file
contradiction is this project's cheapest disproof; an intra-FILE one is
cheaper still, and nothing had ever read the two paragraphs together.

**DiskDoubler methods 1–5 and 7 "cannot be graded".** Declined per entry
since M12 on the grounds that no corpus fixture uses one and nothing reachable
writes one. The first half was true and the second was never tested. Running
the application says otherwise, twice over:

- **DiskDoubler 3.7's own Settings dialog offers exactly two software
  methods**, "Method A (fastest)" and "Method B (usually smaller)", and A
  writes **method 1** — Unix compress, which OPEN_ITEMS.md had already named
  as the cheapest one to add "if a fixture ever turns up". A fixture turns up
  in four minutes: `tools/vmac/diskdoubler.py --make A`.
- **Method 7 needed no emulator at all.** The 3.7 distribution disk ships two
  THINK C libraries compressed with it, because Salient built the disk on a
  machine with the Sigma Designs card fitted. They were sitting in a zip on
  Macintosh Garden the whole time, and each carries the checksum that grades
  it.

**Cost: two methods, and with method 1 the default output of DiskDoubler's own
era** — 3.7's fast setting, on a product that shipped from 1990. The smell is
the one this file already names: *a limitation stated about the environment
that is true only of one tool*. "No fixture in the corpus" was read as "no
specimen exists", and the corpus is 812 files that a URL harvester could
reach, not the set of DiskDoubler files in the world. The other half of the
same claim — that "the reference marks 3 and 4 unimplemented and 5 untested" —
was also wrong in the direction that mattered less: XADMaster implements 4 and
5 (untested) and macutils implements 3 (untested), so the references cover
three of the four methods still declined. What is missing for those is a
specimen, not code. (Method 2 was implemented on 2026-08-21, so the three
still declined are 3, 4 and 5 — and every one of them has a reference. Which
one covers which, read out of the source: OPEN_ITEMS.md.)

**`DDA2` was read as far as the corpus went, and the corpus stopped early.**
Not one of the six DiskDoubler fixtures is a `DDA2` holding a file DiskDoubler
Pro could not compress, so 809 green fixtures said nothing about the entry
type that describes one — and neither did the reference, which raises on it
too. **Cost: every DiskDoubler Pro archive containing a file that would not
compress, which is most archives that contain an image or a sound.** Five of
the nine real ones tried here. **No smell above found this one** — inputs
from outside the corpus did, which is a sixth mechanism and the only one that
needs no cleverness. What named the cause in minutes was the fifth.
DECISIONS.md 2026-08-21.

**"SuperDisk!'s compressor does not survive here, only its expander."** The
reason methods 10, 13 and 20 sat in *waiting on a file*. Macintosh Repository
carries the 1991 ` SuperDisk!` control panel — `cdev`/`AlyS`, an 89 KB
resource fork — and it is the half that compresses. It installs into
`System Folder:Control Panels`, opens under System 7 with Compress
(Off/Light/Tighter), Speed and Memory settings, and its "Make File" button
turned an 11,136-byte subject into a 2,372-byte `.x` on the first run that
reached it (`tools/vmac/sdcompress.py --compress`).

**Cost: three methods filed as ungradeable, on a sentence about what
survives that nobody had searched for.** The same site had already supplied
the Symantec DiskDoubler release earlier the same day. The smell is the
fourth again — a limitation stated about the environment — and the specific
correction is dull and repeatable: **"X does not survive" is a claim about
somebody's search, and it decays.**

What it did NOT close: the archives it writes are a container this engine has
never read — SuperDisk!'s single-file form, not the record stream the corpus
uses (DECISIONS.md 2026-08-22, later). The item moved from *waiting on a
file* to *waiting on a layout*, with the file now producible on demand.

**"These 8 forks have no second implementation."** `unar` refuses them,
macunpack has no DDn at all, and DiskDoubler's own expander only runs on a
Mac — which restamps a resource fork's bytes 16..127 as it writes it. Every
step true, and the conclusion still did not follow: **`unar`'s DDn reads one
byte past the fork's declared compressed length**, and the container is ours
to build. Declare one more, append a pad byte, and all 33 forks of the two
archives come back byte-for-byte equal to this engine and to what the Mac
produced outside the stamped window. `oracle-unadjudicated` fell from 24
forks across 12 fixtures to 16 across 10.

**Cost: eight forks carried as "not ground truth" since M12**, and an
OPEN_ITEMS entry that told three later sessions to go looking for an
implementation that was already installed. The smell is the fourth again — *a
limitation stated about the environment that is true only of one tool* — with
a twist worth naming on its own: the limitation was true OF that tool, on
that input. **An oracle that refuses one input may accept a presentation of
the same bytes.** What is fixed is the tool's bug; what was ours to choose
was what we handed it.

The bug is reduced to a 1,166-byte reproduction in
`tools/xadmaster-ddn-repro/`, because this file already records what
attributing a root cause without one costs.

**"Methods 3, 4 and 5 cannot be graded."** True of decoding, and the whole
question was pointed the wrong way. Grading a decoder needs a specimen;
grading a READING of the format needs an implementation, and Salient's own
`DiskDoubler™ App` comes off the 1991 disk uncompressed and runs. Encode a
fork, hand it to 1991, and it either expands to the bytes that went in or it
does not: all three do (`tools/vmac/ddencode.py --expand`), and 4.1.1
confirms method 5 a second time. **Cost: the last three methods of the
format, held behind a rule about oracles while the oracle was on the disk
that had just been downloaded for something else.**

The smell is the third in the list — *a limitation written one paragraph from
its own remedy*. OPEN_ITEMS.md said what was missing was "a file to grade a
decoder against" in the same entry that named two reference implementations;
what nobody asked was whether the grading had to run in that direction. The
sharper form: **an oracle you can only feed is still an oracle.**

It also found a second `#ifdef UNTESTED` that is untested in the worst way.
macutils declares method 3's escape byte as `#define ESC 0x144` — 324, which
no byte can equal — so its escape branch is unreachable and its method 3
copies input to output. Read as decimal 144 the algorithm is RLE90 exactly.
That is twice now in one file: **a reference marked untested can be untested
into a no-op, which counts as "implemented" to anyone counting references and
decodes nothing.**

**"No compressor older than 3.2 is reachable."** The reason methods 2-5 were
declined, and false. Salient's own **3.1.2** distribution floppy is on
WinWorld — 1991, 800K, SHA-1 published — and it carries **a method 2 fork**
(`XCMD.h`, 564 → 386 B), the only one anybody here has seen, plus 22 method 7
forks of up to eight chunks where the 3.7 disk's two hold one each. Method 2
is implemented and graded from it; the multi-chunk question closed with it.

**Cost: one of the eleven methods, for the life of the project**, and an open
item that read as "wait for somebody to find a file" when the file was one
page load away. The smell is the fourth in the list — *a limitation stated
about the environment that is true only of one tool* — where the tool was the
three sites somebody thought to search. All three are Macintosh archives;
WinWorld is a PC abandonware library that also carries Mac software, and
nothing had ever looked there. The sharper form, for next time: **when an
open item says what is missing is a FILE, search for the file and not for the
story.** Every search this project ran about DiskDoubler was about its
history, which is genuinely what dated methods 2-5 to the Salient era — and
which could never have returned a floppy image.

**The headerless `DDA2` record "is for a file DiskDoubler Pro could not
shrink".** True, and half a condition. The other half is that the file must
have **no resource fork**: `Test Text` is eleven bytes, stored, and gets a
full `0xABCD0054` header because it has a 332-byte one. Measured on the Mac
across all four cells of compressible x forked, and visible in the corpus the
claim was derived from all along — 30 `0x1000` records, every one fork-less,
beside 45 stored-data-fork headers that are not. **Cost: two emulator
sessions spent looking for a file that cannot exist**, and a byte at `+87`
documented as a resource fork's checksum when no `0x1000` record can carry a
resource fork at all. It also kept an entry in OPEN_ITEMS.md's *waiting on a
file* list, which is the section whose whole point is that somebody might
turn up with the file.

**No smell here found this one either, and none would have.** The claim was
inferred from real records and was merely incomplete, so it had no tell. What
found it was looking in the corpus for what the claim would ALLOW and the
corpus never does. That is the seventh mechanism, and DECISIONS.md
2026-08-21 (the Symantec release) states it as a habit: a rule inferred from
the cases it was drawn from always fits them.

**Four `SPLT` parts, two sets.** Written into FORMATS.md and OPEN_ITEMS.md
the day the scheme was derived, and the corpus it was derived from holds six
parts across three sets — the third being the DiskDoubler Pro self-extractor,
whose resource fork is 14,128 bytes. **Cost: the joiner's resource-fork path
had a 342-byte fork behind it in real specimens, and 47 times that was sitting
in the same directory**, along with the only set whose parts are 20 KB rather
than 12. All three now join byte-exact, forks included, and the CRC at `+48`
is exact on all six rather than on four. The smell is the oldest one here: a
number copied forward instead of re-counted. Nothing re-derived it because
the harness that reads the corpus grades files, and these are sets.

**"Macintosh Garden has 3.7 and 4.x only."** Written as the reason methods
2-5 cannot be graded, and false: the same site carries `DiskDoubler_App_3.2`
and `DiskDoubler2.03.sit`. Neither closes the gap — 3.2's `MENU 5019` offers
"Method A (fastest)" and "Method B", the same two 3.7 has, and the 2.03
download is DDExpand, the free EXPANDER, which compresses nothing — but the
CONCLUSION was being carried by a fact nobody had checked, and the check is
one page load. **Cost: none yet**, and that is the point of collecting it: the
next reader would have stopped at the sentence instead of at the search. The
smell is the one this file names first — a limitation stated about the
environment. OPEN_ITEMS.md now says what is on that page.

**63 sampled fixtures.** `tools/vmac/sample.txt` held 63 lines and 59 names:
`derived-MAZv143.sea`, `derived-DD_Expand.sea`, `derived-MacPass390.sea` and
`derived-Expand_Now_1.0.1.sea` were already in the list as REFUSAL cases when
M12 added them again as extractions, and nothing deduplicates a list of file
names. **Cost: four emulator runs on every sweep of every tier since
2026-08-15 — minutes each, at 1x tens of minutes — and a coverage number 7%
higher than the coverage.** It also inflated a gap: OPEN_ITEMS.md read "the
seven fixtures M12 added" have never run on System 7, and M12 added TWO new
names to this list. The smell is a cross-file contradiction that no file
carried, because both numbers were computed from the same list by hand and
neither by counting. A list of names is not a set of names until something
makes it one.

**macunpack is not a second implementation of method 7.** Built with
`-DUNTESTED` its `dd_lzss` segfaults on the first specimen: it takes the
32-bit value at offset 6 as a byte count to skip, where the field is a chunk
COUNT, and never initialises the bit pointer it then reads through. The
grading uses `unar` and the fork's own checksum instead. An `#ifdef UNTESTED`
is a claim about the code, and this one is accurate.

**"It cannot even be sniffed without inventing a magic number, so a user gets
*unknown* rather than a name."** Written on 2026-08-15 beside the search that
found no published layout, and it survived the withdrawal above by one day:
the reference had been found, and the sentence about sniffing was left
standing on its own. It rests on an assumption nobody stated — that
recognising a format means matching bytes at a fixed offset. AppleLink's does
not. `PKG Expand Translator`'s recogniser tokenizes the file as text and
checks three words, so the test was there to be copied rather than invented,
and copying it is what rule #1 asks for. **Corrected 2026-09-27: the routine
copied is that translator's COMMAND parser and recognises no file at all**, so
this withdrawal was right about the technique and wrong about the instance,
and the probe it licensed is gone (*Corrected figures*).

**Cost: a day, and it would have been the life of the project.** The smell is
the one this file calls *a limitation stated about the environment that is
true only of one tool* — here, true only of one TECHNIQUE. Read every "cannot
be done" for the assumption it is really about.

**"AppleLink `.pkg` has no reference implementation and no published layout
anywhere reachable."** Searched on 2026-08-15, written up carefully, and true
of the internet. It was not true of this machine: installing StuffIt Deluxe
3.5.1 to chase SpaceSaver put `PKG Expand Translator` in
`System Folder:Extensions:Aladdin:Translators`, one of fourteen translators
beside `UnZip`, `tar` and `Unix Compress`. Its `Name` resource is the Pascal
string `AppleLinkPKG`; its `Othe` resource is 20 KB of 68k opening with the
same `600e 0000 <type>` preamble as the `CMod` modules this project has just
finished reading; and StuffIt Deluxe's own *Translate* menu offers
**PKG Expand…**. It was found by photographing that menu while looking for a
SpaceSaver command.

**Cost: nothing yet, and that is only because nobody has needed `.pkg`.** The
smell is the one this file names first and keeps catching: **a claim that no
implementation exists, made without opening the files already in hand.** It is
the fifth of that exact shape — after StuffIt method 6, Now Compress's 1995
archive, ArcMac's fork order and SuperDisk! — and this time the file arrived
as a side effect of an investigation into something else. **What is
outstanding is a specimen**: OPEN_ITEMS.md still has none, and a decoder with
a reference but nothing to run it against is the bargain this project declines
everywhere else.

**"The trigger is a NAME RULE."** Found on the panel's *Compression and Other
Settings* page, written up as the answer to five failed attempts, and repeated
in three files. The page does say it — *"Immediately compress files, folders,
and disks whose Name begins or ends with: small"* — and the rule does not fire.
Four runs renamed a subject to match, on a machine that booted and was shut
down cleanly, and the file came back byte-identical every time. The disproof is
on the same page: its OTHER rule, *"Stuff or expand item when its name is
changed by adding the following suffixes: .SIT"*, fires on the same event —
`Forked` renamed to `Forked.SIT` came back a 228-byte StuffIt archive with the
original gone. So a rename reaches SOMETHING that acts on it and whose output
survives to the image; compression specifically does not happen.

**Cost: five runs before the flush was fixed and six after it**, and a
sentence in OPEN_ITEMS.md that made the specimen look one keystroke away for a
day. The `.SIT` rule that disproved it turned out to be Magic Menu's rather
than SpaceSaver's, which is the second half of the same lesson: the page that
offers a setting is not necessarily the software that acts on it.

**The smell is a familiar one wearing new clothes: the claim was read off
the software's own UI rather than out of its behaviour.** A settings page is
documentation, and this repository already distrusts documentation it has not
run — that is why every method table here is derived from module headers rather
than from a manual.

**Three SpaceSaver runs that "measured unchanged" never booted.** The
enrolled image every one of them started from — `--namefirst`,
`--namevol` twice — was made by `--enroll`, which drove the control
panel correctly (its own screenshot shows the startup disk added to the
Idle Time list) and was then **killed**. Mini vMac writes a guest's
sectors through buffered stdio and flushes when a volume is ejected, so
what was copied out of `/tmp` was a torn image: it does not boot, and
the runs built on it photographed the striped garbage screen and read
their subjects back unchanged. Those readbacks were written up as facts
about SpaceSaver — that a matching name appearing does not fire the
rule, that eighteen minutes of idling changes nothing.

**Cost: the specimen, for a day, and the whole of the trigger
investigation.** "A rename EVENT is required" was inferred from one of
these dead runs, and it sent five more at driving the Finder's name box.
The fix was already in this repository and had been since the ARC
specimens: `arcmac.py`'s `shutdown()` says *"killing the emulator with
the volume still mounted loses everything the guest wrote"* and picks
Special ▸ Shut Down instead. `spacesaver.py` simply never called it.
**The smell is a new one worth keeping: a harness that ends its runs
differently from the harness beside it.** Same emulator, same flush
problem, one of them solved — and nothing compared them.

**Alysis SuperDisk! "has no reference".** Filed under OPEN_ITEMS.md's
*"rule #1 forbids inventing a format"* for as long as that section has
existed, on the grounds that XADMaster does not implement it, `unar` and
`macunpack` stop at the envelope, and no layout is published. Every one of
those statements is true and the conclusion did not follow: both corpus
archives are self-extracting APPLs, so each ships an implementation — a 2,694
byte `CODE 2` that walks the container, a 982-byte `SuperDisk! Add-In Module`
in the data fork that decodes method 11, and, once that method decodes, the
Disk Expander extension whose `Cmpr` resources are the entire codec set with
their method numbers and names.

**Cost: the only format in the corpus that a user got *unknown* for, for the
whole life of the project** — two archives, five forks, four documents and an
application nobody could get at. It is the fourth withdrawal of this exact
shape, after StuffIt method 6 ("there is no oracle" — the second oracle was in
`reference/`), Now Compress's 1995 archive and ArcMac's fork order. The smell
is the same every time: **a claim that no implementation exists, made without
opening the file that needs one.** A self-extracting archive is never missing
its decoder.

**Retro68's `HOpen` glue.** Claimed to return `noErr` without writing back the
refNum, and recorded as M10's root cause. Ten cases — real vRefNum, non-zero
dirID, write permission, a poisoned stack, a cross-volume open — show `HOpen`
writing the refNum every time and agreeing with a hand-filled `PBHOpenSync`.
The same write-up also said `HOpenDF` was the odd one out "unlike the
non-hierarchical `OpenDF` beside it"; wrong, they behave identically (and as
Apple documents — corrected 2026-10-13, withdrawn above).
**Cost:** the true cause of the M10 saga stayed unknown until 2026-10-13
(`ioMisc`, the field the glue leaves unset) and every conclusion
from that period had to be re-tested — the next three entries. Twice a claim
about one source file was wrong because the file was read rather than run.

**Three non-relocatable staging blocks bomb the Memory Manager.** Re-tested
with the glue fixed: two separate `NewPtr` staging blocks plus the archive
buffer extract a two-fork file byte-exact with no crash. The shared block is
kept as marginally more heap-friendly, but its stated justification was wrong.
**Cost:** none beyond the write-up.

**`derived-RWAsm_Folder.sit` fails at 4 MB.** Does not reproduce: all 38
entries byte-exact at the same 643.2 KB peak the failing run reported. What
differed cannot be established — the harness that produced the old numbers was
never committed and its working directory is gone. Closed as
not-reproducible, not as fixed. **Cost:** it is why `tools/vmac/` is committed
and fetches its copyrighted inputs by URL.

**QuickDraw bombs after File Manager activity.** Twelve configurations of
`tools/quickdraw-repro/` — including `GetNewDialog`, eight interleaved rounds,
and a held 200 KB non-relocatable block — every call succeeding with
`MemError() == 0`, its log written by poking the framebuffer so the report
cannot depend on what is being tested. Both proposed explanations fail too.
**Cost:** as stated it meant the shipped interactive build was broken —
SFGetFile, a progress dialog, then an alert is exactly File Manager followed by
QuickDraw — and nobody noticed, because it was filed under *harness lessons*.
**Filing a hypothesis under "lessons" hides it.**

**The OS 9 boot volume is plain HFS.** A signature was read at a fixed offset
(`'BD'`) without checking `drEmbedSigWord`, which says `'H+'`. The proposal
built on it — drop the app into Startup Items with hfsutils, skip Finder
automation — is not merely untried but impossible, since nothing here writes
HFS+. **Cost:** a day's plan; and the same mistake shape (reading a field at an
offset instead of asking what qualifies it) is why the HFS+ runs now prove
their output volume by mounting the wrapper.

**Interleaved reads and writes on one volume return zeros.** This justified
reading the whole archive into RAM. `UNC_AT_INTERLEAVE` reads one file three
ways on one volume and gets an identical CRC every time, at 4 MB and 1 MB, on
two fixtures. **Cost:** the archive buffer came out of the engine's budget, so
at the floor target the archive's own size decided which StuffIt 5 entries were
affordable. Removing it took the sample 39/44 → 40/44.

**Mini vMac's write-back is lazy and partial** — "it can commit one fork of a
file but not the other". The whole sample was replayed with `--keep-disks` and
every Out volume read back: **55/55 byte-exact**, both forks, names and folder
structure included, `derived-RWAsm_Folder.sit` alone being 38 files and 73
forks. **Cost: the highest of any of these.** It forced verification through
the framebuffer grid, which carries counts and summed CRCs — and a summed CRC
cannot carry a name. That is why the System 6 and 7 tiers never checked an
output NAME, and why a real defect in the gzip/`.Z` fallback name sat in the
corpus for weeks until the Mac OS 9 harness, which reads its volume, caught it
on its first sweep.

**`pkill -9` never flushes; repeated boot+kill corrupts the boot image.**
Neither half survives: the sample was read back off its Out volumes after
exactly that kill, and 6 boot+kill cycles re-using one boot-shell image leave
it byte-identical (that configuration never writes to its boot volume), while
5 `--finder` cycles change the hash every time and still boot to a healthy
desktop. **Cost:** none — and the practice is kept for the better reason the
OS 9 master-image incident taught: the image DRIFTS, so reusing it makes two
runs months apart incomparable. That is reproducibility, not corruption.

**The three 1 MB StuffIt 5 refusals each fill a 512 KB block.** This closed the
floor target as needing "a fundamentally different inverse BWT". Instrumenting
`numbytes` says otherwise: none of the three fills a 512 KB block and one holds
under a quarter of it — the table is FORMATS.md, *Floor target verification*.
**Cost: the largest still outstanding.** The false figure made the gap look
like a 3× shortfall requiring a redesign when the worst entry needed ~650 KB
against ~700 KB free, and nobody re-derived it for a day because the item read
as closed. **Why it survived is the part worth keeping:** the disproof was
already in this repository — DECISIONS.md said that fixture's blocks "really do
hold ~316 KB", one file away from the claim it contradicts. The tier reached
44/44 on 2026-08-07 without a new algorithm (DECISIONS.md 2026-08-06 and -07).

**Nine fixtures are ground truth the oracle cannot produce.** Seven were filed
as *structurally undecidable* (an archive holding both `X` and `X.rsrc`) and
two as *oracle-buggy*. Both are properties of `unar -k visible`, the flag this
repository happened to pick. Rebuilt with `-k hidden`, all nine produce
manifests and all 774 pre-existing manifests come back entry-for-entry
identical. **Cost:** nine fixtures sat outside the differential suite from
2026-07-23 to 2026-08-08, including shapes nothing else covers; worse, the
ongoing half — `harvest.py` accepts a candidate by asking whether a manifest
can be built, so every THINK C-shaped archive the corpus might have grown by
was being dropped silently. **Why it survived:** it was filed under *cannot be
closed in this environment*, where items go to stop being re-examined, and the
remedy was quoted verbatim in TESTING.md one paragraph above the limitation.
**Check which of your limits are limits of a flag you chose.**

**There is no oracle for StuffIt method 6.** XADMaster refuses the method,
therefore nothing here can adjudicate an implementation — every step follows
except the first: `macunpack` has decoded it since 1991 and was already in
`reference/`, fetched by this repository's own script. **Cost:** one corpus
fork unextractable and 22 forks of *other* methods left unadjudicated, all
settled within an hour of building it; and the claim was restated in four
status files, which is how a fact about one tool became a fact about the
environment.

**Even `unar` fails on the two PKZIP 1.x zips.** True at M8, when a manifest
was all-or-nothing. Per-entry manifests gave both ground truth for 5 of 7
entries — and the claim survived the morning that disproved it, because
`run_diff.py` skipped those fixtures whole on the strength of our own
"recognized but unsupported" output. **Cost:** 10 adjudicated forks ungraded
for a day, and a skip that could not fail: a regression turning a supported
method into "unsupported" would have been recorded as a skip.

**The Macintosh application unwraps nested files automatically.** Claimed by
README.md, in the section describing the APPLICATION. True of the Linux CLI,
false of the application, which took exactly one layer off and stopped —
measured by running it. **Cost:** a user with a `.sit.hqx`, which is most of
what was distributed, had to open the result again by hand for as long as the
application has existed. **Why it survived:** the autotest is graded per layer
on purpose, so the harness that replays the sample could never catch it, and
nothing else read the README as a specification. **A claim in the user-facing
document had no test at all** — every other claim here is checked by something.

**No second implementation of Now Compress exists.** Written while a copy of
one sat in the corpus: the 1995 fixture is SELF-EXTRACTING, so the decoder
Now Software shipped with it is in its resource fork.
`nowcompress.py --adjudicate` runs it under the emulator; it agrees with us on
all four forks, 9.9 MB byte for byte (resource forks with bytes 16..127 masked,
the `vmac_check.py` convention). **Cost:** one day of those forks being
defended structurally instead of adjudicated — and the same shape as the
method-6 entry above, which is why this one was worth re-reading.
**Twice now the answer to "nothing can grade this" has been in the repository.**

**Nothing documents ArcMac's fork order, and no oracle reads ArcMac.** Both
halves wrong, and both fell to one wiki page (justsolve.archiveteam.org/wiki/
ArcMac, read 2026-08-16). The format HAS a published specification — *ArcMac
File Structure* in the `ARCMAC.DOC` that ships with every distribution — which
states the fork lengths are stored "using Intel 80xxx byte sex"; the decoder
had been reading them big-endian. It does not give the order, so that was
measured instead: `tools/vmac/arcmac.py` has ArcMac 1.3c archive a two-fork
file under Mini vMac, and the payload is **data fork then resource fork**,
byte-exact both ways, confirmed a second time with the `s` (stored) modifier
where the two forks are legible raw. The page also named two real archives —
neither had ever been searched for. **Cost:** every ArcMac entry's payload,
declined for a day; every ArcMac entry's fork SIZES, reported as garbage for
the same day, by a decoder and a unit test that were wrong the same way, so
the suite could not see it. **Three times now the answer to "nothing can grade
this" was one search away**, and this time the withdrawn claim above is what
made the third worth attempting.

**`src/fmt_btoa.c` accepts CR and CRLF line endings.** Its own comment said
exactly that, one line above code that SKIPPED carriage returns rather than
ending the line on them. CRLF worked by accident — the LF ended the line — and
CR alone, which is what every text file a Macintosh writes uses, ran the whole
archive together into one line that no header matched. Measured by
re-terminating the reference's own output: the CRLF copy decoded, the CR copy
did not. **Cost:** v0.15 shipped a btoa decoder that could not read a btoa file
written or re-saved on the machine this program is FOR — the one place the
format's files actually are. **Why it survived:** all 21 cases in
`tools/run_btoa.py` come out of btoa 5.2.1 on Linux, so the suite could vary
length, alphabet, framing and framing checksum but never the line ending. Four
cases now do, and they fail against the old code.

**The `btoa/atob Translator` is reachable only through a hierarchical menu.**
The submenu half is true and stands (three ways in were measured under Mini
vMac and none selects an item, `tools/vmac/README.md`). The conclusion drawn
from it was not: the menu is not the only door. StuffIt Deluxe 3.5.1's `aete`
declares a `translate` event — `SIT!`/`TRAN` — and its `SIZE` -1 has
isHighLevelEventAware set, so ONE Apple event runs the translator with no menu
tracking, no coordinate and no scripting language installed. All of that was
readable off the disk image with `hcopy` and no emulator at all. **Cost:**
three months of the btoa decoder graded against a single encoder, an
`--btoa-drop` route built and abandoned against an application that converts
archives rather than encodings, and an open item that named the wrong obstacle
("a route that is not a submenu" — it was never the menu). **Why it survived:**
the first attempt asked *how do I click this item*, and every later one
inherited the question. What the application will do is in its resources; what
a harness can click is not the same list.

- **"SpaceSaver's Huffman builder checks less than the shared one
  does"** — filed 2026-08-27 during the scaffolding audit, withdrawn the
  same day. `ss_a3_build` rejects an over-subscribed code table with
  `code > (1u << (L + 1))` and `unc_canon_build_ext` with
  `space > (1u << l)`, and the second was called the stricter of the two
  on the strength of reading them. They are one predicate: both
  accumulators start at zero, `code` updates as `2*(code + count[L])`
  and `space` as `2*space + count[l]`, so `code` is exactly twice
  `space` at every length and the two thresholds differ by the same
  factor of two. Checked as well as derived — the two loops run
  side by side over every table with maxlen <= 4 and counts <= 8, and
  over 20 million random tables up to SpaceSaver's own 24-bit ceiling:
  **zero disagreements, and 19 million of those tables were rejected**,
  so the check demonstrably fires. **Cost:** small, and it is here for
  the mechanism rather than the price — an item filed, moved between two
  sections of OPEN_ITEMS.md, and cited once. What it would have cost is
  the fix: "tighten the looser check" would have changed a line of a
  decoder graded against Aladdin's own compressor, to no effect,
  and left a comment claiming a difference that was never there.

- **"The engine calls the progress callback every 8-16 KB."** True of
  every format but one. `src/fmt_now.c` pulls each compressed block with
  `unc_read_full` — the raw `UncIO`, not the shared buffered reader that
  drives the pump — so **Now Compress never called it at all**, from the
  day the format was written (M12, 2026-08-15) until 2026-08-28. The
  claim is in `include/macextract.h` as a contract and in CLAUDE.md as a
  rule, and 946 fixtures passed for six weeks without either being
  checked once: every suite here grades bytes, and a decoder that never
  yields produces perfectly correct bytes. **Cost:** on a Mac, every Now
  Compress extraction ran with a progress dialog frozen at 0 % and both
  Cancel routes unreachable — including a 9.9 MB entry, which on a Mac
  Plus is not a short wait. Found by the Mac OS 9 cancel test, which
  read as "Cmd-. does not work here" until the second archive cancelled
  on the first chord (DECISIONS.md 2026-08-28). **Why it survived:** it
  was written down in two places and measured in none.
  `tools/run_ticks.py` measures it now, and fails on the pre-fix engine.

- **"The Mac OS 9 run launches the application, extracts and quits."**
  The last third was never true, and every screenshot after the launch
  was one step behind its label. The run sent Return, Return, Cmd-Q;
  the second Return is what accepts the DESTINATION dialog, so
  `14-result.png` photographed SFPutFile, the step printing "extraction
  reported" had timed that dialog opening, and Cmd-Q went into a modal
  dialog that never sees it — the application was still running, with
  the result alert up, when the emulator was killed. Withdrawn
  2026-08-28, when the sequence was driven to the end (DECISIONS.md;
  `tools/vmac/README.md` has the step table). **Cost:** nothing to the
  20/20, which is read off the volume and not off the screen — but for
  as long as the tier existed nothing had waited for the result alert,
  no OS 9 run had ever left the application, and the two steps that
  would have said so did not exist. **Why it survived:** every step
  reported a plausible number against a plausible name, and a
  screenshot of the wrong dialog is indistinguishable from a screenshot
  of the right one unless somebody looks. The label came from whoever
  wrote the keystroke, not from what the screen did.

- **"SuperDisk!'s up-directory record is untested."** Filed in
  OPEN_ITEMS.md beside a true statement about DiskDoubler's walks and
  withdrawn 2026-08-28, when the DiskDoubler half was closed and the
  SuperDisk! half was read properly. `super-disk-utility.hqx` holds
  `Read Me and More/Application/...` and `Read Me and More/PLEASE
  READ/...`: two folders, a pop between them, and every one of those
  paths adjudicated against the archive's OWN self-extractor on an
  emulated Mac and replayed by content in `ci.sh`
  (`tools/run_superdisk.py`). What is untested is only DEPTH — no path
  in either fixture is a fifth of the 255-byte cap. **Cost:** nothing;
  filed and disproved a week apart, and the correction narrows an open
  item rather than reopening anything. **Why it survived:** it was
  written as one bullet about two formats, and the half that was true
  carried the half that was not. An "untested" claim is a claim about
  the corpus and expires when the corpus grows — the fixture that
  disproved this one was already in the suite that the same sentence
  cited.

- **"The Macintosh application does not number a collision the way the
  CLI does."** Filed in OPEN_ITEMS.md on 2026-08-27 with the flag it was
  really about, withdrawn 2026-08-28 by the first test the shell's name
  path has ever had. `mac/macextract_mac.c` numbers `~1`..`~9` in
  `BumpName`, off the File Manager's `dupFNErr` — so two entries whose
  names are the same for 31 characters both come out, and removing the
  numbering loses one of them and stops the run (`tools/run_macnames.py`
  fails six assertions on that build). What is true is the half the
  bullet led with: the shell reads no `name_truncated` and says nothing
  on screen. **Cost:** nothing yet — but the remedy the bullet named was
  "`~1` numbering in `mac/macextract_mac.c`", which is code that has been
  there since M10 and which a reader of the file would have written
  again. **Why it survived:** the flag was new, and a front end that does
  not read a new flag was assumed not to do the thing the flag reports.
  The shell was doing it by another route, which is what the source
  comment beside it says. The half that was true — nothing on screen —
  closed on 2026-08-29, when the run report replaced the alert
  (FORMATS.md, *Name limits*).

- **"9,320 robustness variants clean"** — read, for two years of
  commits, as *damaged input is handled*. Withdrawn 2026-08-29: what
  the suite requires of a truncated archive is that the program
  "terminate quickly with a normal exit code", and **exit 0 is one**.
  A walk that reads the entries before the cut, hands them over and
  reports SUCCESS passes every variant. Two formats did: a DiskDoubler
  archive cut to three fifths extracted the entries before the cut and
  said "Extraction complete." (DDAR ends at EOF, so a header that would
  not read was its end; DDA2 has an end marker and never reaching it
  was not checked), and a StuffIt archive shorter than its own header
  says it is had that length **clamped to the file** — the step that
  keeps the walk inside the file is the step that erased the evidence.
  `unar` calls all of those files broken. **Cost:** a user extracting a
  half-downloaded archive was told the run was complete, for both of the
  formats this project exists for — DiskDoubler since M13 and StuffIt
  since M1 — and no suite here could have said otherwise. Found by a
  question about what the end-of-run box can and cannot tell the user.
  Both are fixed and `tools/run_truncation.py` now asks the oracle;
  the corpus-wide sweep is 2,796 cut archives, none silent. **Why it
  survived:** the number was the claim. 9,320 is a big number attached
  to the word "clean", and nobody asked what the suite compares — it
  compares nothing, by design, because the same suite also feeds
  bit-flips where any answer is defensible. This is the tenth smell in
  the list below, an aggregate that cannot fail on the property it never
  aggregates, in the file that names it.

- **"The Mac shell numbers a collision `~1`..`~9`, so two entries whose
  names are the same for 31 characters both come out."** Written
  2026-08-28 in the entry above, from the test that had just been added;
  withdrawn 2026-08-29. True for nine. The TENTH such name returns -1
  from `begin_entry`, which the engine reads as *abort the archive*, so
  every entry after it is silently never written and the user is told
  "This file could not be extracted." **Cost:** live from M10 until
  2026-08-29 — an archive holding ten files whose names are alike for 31
  characters lost everything after the tenth, and the run reported a
  failure about the archive rather than about the names. Measured on a
  Mac Plus: a generated archive of 26 entries produced 10 files.
  Numbering goes to `~99` now, and a name that still cannot be made
  unique fails its own entry (`tools/run_macnames.py`, the crowd case).
  **Why it survived:** the test that established the claim used exactly
  two colliding names, which is the number the claim was about. The
  abort is one line below the numbering in the same loop and cannot fire
  until the numbering runs out — so the assertion could not reach it,
  and the sentence written from that assertion described the loop's
  first nine iterations as though they were all of it.

- **"The two Alysis implementations disagree about where a Huffman
  region's neighbour begins, and only the harness's own encoder reaches
  it."** Written 2026-08-25, withdrawn 2026-08-28. They never disagreed.
  `sd_huff_bit` fetches a long only when a bit is asked for and Alysis's
  reader has already fetched it, so where a coded flag bitmap ends
  exactly on a 32-bit refill the cursor `sd_huff_end` adds 2 to was four
  bytes short — and every literal after it came back wrong. **Cost:** a
  silent decode defect in SuperDisk! methods 2, 4, 6 and 8, reachable by
  about one block in 32 of any such fork, live from the day the format
  went in (2026-08-20) until 2026-08-28. **Why it survived:** the claim
  was two mistakes propping each other up. The subjects meant to reach
  the boundary were sized `ceil(size/8) % 4 == 0`, which is a rule about
  the harness's own flat 8-bit code and about nothing the panel writes,
  so all four missed by 2 to 5 bits — and the miss was then written down
  as "a real block cannot reach it", which is how a live defect became a
  documented property of the format. Meanwhile the differential harness
  SKIPPED every synthetic block that did reach it, which is a tolerance
  resting on our own output: the one case that could have failed was the
  one case excused. Both are gone; the specimens were manufactured by
  measuring what the compressor actually writes (`tools/sdhuff.py`: the
  panel codes each flag BYTE in one bit, so the bitmap is `nflags + 5`
  bits and the size CAN be aimed), and all nine methods now agree 12/12
  with no skip.

- **"StuffIt Expander's memory partition cannot be measured here — reading
  the application's `SIZE` resource needs an HFS reader this machine does
  not have."** Written 2026-08-15, withdrawn 2026-08-29. The reader is
  `hfsutils`, which `tools/vmac/` has required since M10 and which
  `mkboot.py` uses on every boot image it builds. What hfsutils refuses is
  the size of the VOLUME, not the file: Expander's distribution image is
  400K and it declines anything "smaller than 800K". Padding a temporary
  copy to 800K mounts it — reading only ever follows the MDB's own extents,
  so the padding is never looked at — and `hcopy -m` then hands over both
  forks. 4.0.2 asks for **512 KB preferred, 384 KB minimum** (FORMATS.md,
  *Compared with StuffIt Expander 4.0.2*). **Cost:** the one row of that
  capability table a 1 MB user actually needs, blank for two weeks, and it
  is the row that says whether the free tool fits on the floor target at
  all. **Why it survived:** it is the mechanism this list already names —
  a limitation stated about the environment that was true of one tool, in
  one configuration, and was never re-read for the name of the tool.

- **"Module 13 runs now: it wanted a 64 KB working buffer and one Toolbox
  trap, `_BlockMove`, which the runner answers."** Written 2026-08-25,
  withdrawn 2026-08-29. Given exactly those two things it segfaults on
  every input — four for four, `signal=11`. The 65,536 it compares
  `workingBufferSize` against (@0xa2) is a FLOOR inside its own code; what
  it needs is the long at +0x1E of its module header, **229,618 B**, which
  is the number Alysis's own extension checks (INIT 32 @0x51a2) and
  refuses with -4 below. Sized from the header the module compresses four
  inputs cleanly. **Cost:** the method 13 item stayed filed as "waiting on
  a gradeable specimen" for four days after the tool that manufactures
  specimens was already in the tree, and the sentence three paragraphs
  above it in the same FORMATS.md section still read "13's traps on an
  A-line instruction under the runner" — one section, two accounts, both
  wrong. **Why it survived:** a requirement was read out of a guard in the
  code instead of out of the field the vendor's own loader checks. A guard
  says "not below this"; a manifest says "this much". Satisfying the guard
  satisfied the assertion and not the module — and the crash that followed
  looked like the module's problem rather than the harness's, because the
  previous sentence about this module had also blamed the module.

- **"Lenient on `ESC 1`: macutils' `dd_rle` emits nothing for it rather
  than failing."** Written with `dd_rle` and withdrawn 2026-08-29.
  Salient's own 1991 expander refuses a method 3 fork containing that
  token — at offset 0 and again 1,800 bytes in, on forks that SHRINK, so
  not the size check the `RleGrow` control measures. `fmt_dd.c` passed
  `strict = 0` to the shared RLE90 filter and was **the only one of six
  call sites that did**: `fmt_sit.c`, `fmt_arc.c` twice and
  `fmt_binhex.c` twice all pass 1. It now passes 1, and all 91
  DiskDoubler fixtures stay byte-exact — which is the evidence that no
  real fork carries one. **Cost:** this engine accepted, silently and
  with a plausible answer, a fork the format's only shipped expander
  rejects; five years of corpus never noticed because no valid file can
  contain the token. **Why it survived:** the leniency was inherited from
  a third-party reimplementation and written into a comment as its
  justification, next to five call sites that had already decided the
  other way. A comment naming its source reads as sourced; nobody asked
  whether the source was the vendor.

- **"Five archive formats are still unnamed for want of a reference: zstd,
  lzip, brotli, lrzip and WIM — no implementation or spec for them is in
  `reference/`."** Written 2026-08-26, withdrawn 2026-08-29. For lzip it was
  false the day it was written: deark's `modules/unsupported.c` tests `LZIP`
  at offset 0, and deark had been in `reference/` since 2026-08-25, cloned
  for ARC's Distilled method. The module's whole purpose — naming formats it
  will not open — is `fmt_foreign.c`'s purpose, so it is the first place to
  have looked. **Cost:** three days of a `.lz` reading as "not recognized"
  when the constant was in the tree, and the other four sitting behind a
  sentence that made all five look equally blocked. **Why it survived:** it
  is the mechanism this list already names — a limitation stated about the
  environment that is really a claim about somebody's search — and the search
  had been for "a spec for lzip" rather than for "a file in reference/ that
  names formats". The fifth, brotli, turned out not to be a search at all:
  RFC 7932 gives it no magic number, so it cannot be identified by anything
  (OPEN_ITEMS.md, part 1).

- **"Apple Archive (`.aar`) is unnamed for want of a reference — missing: an
  implementation or spec in `reference/`."** Written 2026-08-29, withdrawn
  2026-09-01. It was a claim about a search, and the search had never been
  run: `libNeoAppleArchive` is MIT-licensed, cross-platform, from-scratch
  rather than a reimplementation of Apple's closed library, and one query
  away. It carries the magics, the six-byte header prologue and the closed
  set of field subtypes; it also **builds and writes archives on this
  machine**, so what arrived was not a spec but an oracle, and the probe is
  graded against `AA01`, `pbze`, `pbzz` and `pbzb` files written and re-read
  by an implementation that is not ours. **Cost:** three days of an `.aar`
  reading as "not recognized"; small, because the format is from 2020 and
  no Macintosh in scope can meet one. **Why it survived:** the sentence was
  written the same day four other formats were joined *by fetching their
  references*, so the file already showed the remedy one paragraph away —
  the mechanism this list names as "a limitation written one paragraph from
  its own remedy". The four questions at the head of OPEN_ITEMS.md part 2's
  waiting-list exist to catch exactly this and were not asked of it.

- **"A generated SuperDisk! record stream could only be graded against the
  same transcription that wrote it."** Written 2026-08-27, withdrawn
  2026-09-01. It stood in OPEN_ITEMS.md's *Untested code* section and in
  `tools/run_names.py`'s docstring, holding open the one path-cap the engine
  had never reached through this format's own walk. **The disproof was in the
  same sentence**: it went on to name the second reader — "an archive's own
  self-extractor on an emulated Mac, which has never been handed a stream this
  project wrote" — so the file recorded both the gap and the untried route to
  closing it, and nobody took the second half as an instruction. `SD!
  Utilities.x` is an APPL whose data fork IS the archive; replacing that fork
  and keeping its resource fork gives the format's own `CODE 2` any stream you
  like. It read a 10-folder one and built all 11 files, and the uncut path
  `unc_path_leaf` reports is the path it built (FORMATS.md, *Alysis
  SuperDisk!*). **Cost:** the item stayed open five days, and the same
  sentence was carried in a second file, so the claim was reinforcing itself
  across the tree. Small in engine terms — the code was right — but it is the
  second time in a week that "there is no oracle for this" was a fact about
  what had been TRIED rather than about what exists (the first was
  SpaceSaver's modules). **Why it survived:** the mechanism this list already
  names as *a limitation written one paragraph from its own remedy*, in its
  purest form yet — the remedy was in the same paragraph, in the same
  sentence, as the limitation.

- **"Three segmented UI scenarios fail on `main`, and the split is the
  harness: the passes are found by HEADER, the failures are placed by
  NAME."** Written 2026-09-02, widened 2026-09-03, withdrawn the same day.
  `segcheck.py`'s `zip-named`, `split-named` and `wrapped` were reported
  failing across eight runs. They were: `phase_wrapped` and `phase_named`
  graded their output against `build/dev/macextract`, a path **nothing in
  this repository has ever built** — and `make clean` is `rm -rf build`, so
  `./ci.sh` deletes it and never puts it back. `R.sh` reaches it with no
  existence guard and raises `FileNotFoundError` before any comparison
  happens. With the guard and `CD.CLI` that `phase_chain` has carried since
  2026-08-27, all three pass: `zip-named` settled ~155 s, `split-named`
  ~134 s, `wrapped` MATCH with nothing left on the volume. **Cost:** a day,
  eight emulator runs at ~5 minutes each, and two commits that named the
  application as the likely culprit while FORMATS.md's *Segmented sets on a
  real emulated Mac Plus* said all three joined byte-exact — a cross-file
  contradiction that stood for the whole investigation. **Why it survived:**
  the offered explanation fit six of nine cases and was never checked
  against the other three. `wrapped` is not placed by name at all — it is a
  StuffIt set found by HEADER, staged under `Apart.sit.1.hqx`,
  `zzz-download.bin` and `Other.9.hqx`, which share no stem — and `chain`
  is driven by `interactive.py` too and passed throughout. The true
  partition was the repair: `chain` is the one phase whose reference CLI was
  fixed, and the three failures are the three that were missed. **The
  proposed close could not have worked either** — "run the parts past
  `unc_segment_describe` on Linux and it says which side is wrong" — because
  the name-based sibling search is HOST code written twice, `cli/main.c` and
  `mac/macextract_mac.c`; a Linux run exercises only the CLI's copy and can
  never see a Mac-side naming fault.

- **"Now Compress's shape-3 main table ends where the code is
  complete: nothing states its length and the trailing absent symbols
  are not sent."** Written 2026-09-21 in `docs/formats/now-compress.md`
  and withdrawn the same day. The table is a **fixed 290 entries** —
  256 literals and 33 match symbols — and the entries past the point
  where the code completes are written as **zeros**. The code often
  does complete early, which is what made the wrong rule look right:
  the reader stopped, got a table that decoded literals correctly, and
  put the NEXT table at the wrong bit. **Cost:** four of the eight
  harness specimens were recorded as having 271-, 274-, 275- or
  349-symbol alphabets — a figure written into the note as an
  observation — and the distance table read out of the wrong bits
  behind them produced distance classes reaching 131,072 in a
  16,000-byte member. That reading, and the contradiction it created
  with a 32 KB window, is most of why shape 3's stream looked
  undecodable for a day. **Why it survived:** the rule was TRUE of the
  blocks it was derived from (the first four all complete at exactly
  290) and it is the rule the format uses one layer down, for the
  DISTANCE table, which does stop where its code completes. A rule
  that holds on every specimen you have and on the neighbouring
  structure reads as the format's rule rather than as a coincidence of
  both — and what settled it was not an argument but the only test
  that can fail: decoding the block and comparing the bytes.

- **"A Now Compress shape-1 match is `length - 2` then the distance,
  one byte each, so it reaches at most 255 back."** Written 2026-09-21
  in `docs/formats/now-compress.md`, withdrawn the same day. The two
  bytes hold a **3-bit length and a 13-bit distance** — the same rule
  the shape above it uses on symbols — so a match reaches 8,191 back,
  not 255. **Cost:** nothing yet, and that is the point: every shape-1
  block in the corpus and the harness decodes under either reading,
  because the two agree whenever the distance is under 256 and not one
  match token in six blocks has a first byte of 8 or more. A reader
  written from the note would have refused the first fork that reached
  further, and nothing here would have caught it. **Why it survived:**
  it was derived from specimens that cannot tell the two apart, and
  read as measured because it decoded everything it was shown. What
  disproved it was the neighbouring shape: shape 2 is this stream
  Huffman-coded, its rule was already written the other way in this
  same note, and 1,340 of its 2,162 match tokens sit in the range where
  the readings differ. **A description that fits every specimen is not
  thereby the format's**, and two descriptions in one note that
  disagree about the same layer are a contradiction even when both
  decode — this project's cheapest smell, found this time inside a
  single file.

- **"A shape-3 block's bytes 13..15 are 24 bits this note cannot
  account for, zero in every specimen."** Written 2026-09-21 in
  `docs/formats/now-compress.md`, withdrawn the same day. They are
  **four more code lengths and a count byte** — the code-length
  alphabet is twenty symbols, not sixteen, because a distance table
  entry is stored as its length plus two — and the count is of the
  "extra length" entries that let a code run past 15. **Cost:** none
  measured; every block here has zeros there, so the short reading
  gave the right codes, and a table needing the escape would have been
  refused rather than misread. **Why it survived:** the sixteen-symbol
  reading is the obvious one (the values ARE code lengths 0..15), it
  satisfies Kraft exactly, and the leftover bits were zero — three
  reasons to stop looking. The tell was in the same header: a constant
  of 85 that nothing could source, which is `4 − 0x59` once bytes 0..1
  are read as one size field. **An unexplained gap in a header is
  usually a field you have not finished reading**, and an unexplained
  CONSTANT beside it is the pointer.

- **"The block table sits at one of two places and the header says
  which", and "an archive over 64 KB widens the record."** Both written
  2026-09-21 in `docs/formats/now-compress.md`, both withdrawn the same
  day. The eight-byte records are `[u16 mode][u16 padding][u32 END
  offset]` from +4 of a member's data area, always, with a u32 in front
  saying where the first block begins and therefore where the table
  stops; the two readings pick out the same blocks on every file here,
  and the simpler one needs no special case for the 1993 archive or for
  the 1995 one's 2.9 MB. **Cost:** none to any output — but it left
  `0d4c 0037` in the note as "two words this reader cannot name" for a
  day, and they are the mode and padding of a leading record that
  produces no bytes. **Why it survived:** reading the offset FIRST is
  natural when a table's job is to say where blocks start, it decoded
  every specimen, and each special case it needed looked like a fact
  about the file that needed it. **A reading that grows a case per
  specimen is a reading with the fields in the wrong order.**

- **"The word at +2 of a Now Compress file header is a version."**
  Written 2026-09-21, withdrawn the same day. It is the compression
  SETTING, in the same layer bits a block's mode word uses: `0x0010`
  Faster, `0x003f` Smaller, `0x0060`/`0x0160` an archive. What settles
  it is four bare forks that asked for Smaller and came out as shape-1
  blocks — `0x001f` — while their headers still say `0x003f`, so the
  word is what the user picked and not what the coder did. **Cost:**
  none; the 1993 archive is still told from a 5.0.1 one by that word,
  which is all anything here used it for. **Why it survived:** two
  values, two eras, and nothing else to compare them with until the
  compressed FILES were read as archives of one entry.

- **"The name deark uses in the errors it attaches to a fork is the
  member's REAL name, before sanitising."** Written 2026-09-22 above
  `_DEARK_ERR` in `make_manifests.py`, withdrawn the same day. deark
  prints it MAKE_PRINTABLE, so `Icon\r` — the commonest filename on a
  Macintosh volume — arrives as `Icon<\r>` and the sanitiser model
  turns that into `Icon__r_` where the file on disk is `Icon_`. **382
  declined forks across 35 fixtures were keyed to a member that does
  not exist. Cost: nothing, measured** — in every one of the 382 deark
  had written no file for that member, so nothing ever read the wrong
  key. What it would have cost with one live is a fork deark DECLINED
  recorded as a fork deark read as EMPTY, which is the exact defect the
  declined-fork rule had been written hours earlier to prevent.
  **Why it survived:** the claim is true of every printable name, which
  is every name anybody checked it against. DECISIONS.md 2026-09-22,
  *the decline that read as a naming gap*.

- **"28 entries across 5 fixtures come out of this engine with mojibake
  names."** Written 2026-09-22 when StuffIt 5's names were found to be
  UTF-8, corrected the same day. **27 across 4** is the encoding case;
  the 28th is `.typeAttributes.dict` in `derived-PuzzleGetter_0.8.sit`,
  whose forks are both empty and which deark therefore writes no file
  for at all (`do_pre_decompress_fork` leaves both `fork_exists`
  clear). **Cost:** nothing, because the fix was the same either way —
  but the figure had reached three files as though one cause explained
  all 28, which is how a shape nobody has looked at hides inside a
  number somebody has. DECISIONS.md 2026-09-22, *a name an HFS volume
  can hold*.

- **"283 entries deark names in a way no mangling of ours reproduces."**
  `sweep_deark.py`'s own printed summary of what it cannot see, written
  2026-09-22, withdrawn the same day. **225 of the 283 were entries
  deark named and DECLINED** — StuffIt method 13 and StuffIt 5's
  Arsenic, neither of which it implements — and they were invisible
  only because a member deark declines every fork of writes no output
  file. The sweep now cross-checks **4,556** graded forks rather than
  2,080, agreeing on **2,151** with `DIFFER` still 0 — 4,502 that
  morning, and 54 more once the oracle stopped being asked about
  StuffIt 5 in the wrong encoding, every one of which turned out to be
  a decline too. **Cost:**
  no wrong byte anywhere, and a real one all the same — the number was
  quoted three times as evidence that deark is a weak oracle for
  StuffIt, when it meant "deark does not implement method 13", a fact
  about the format this repository had already written down twice.
  **Why it survived:** it was printed every run, in the section headed
  *what this cannot see*, which reads as an audited number rather than
  as a claim needing evidence. **A harness that prints the wrong reason
  for its blind spot is worse than one that prints none.**

- **"`-lh2-`, `-lh3-`: declined per entry ... no archive that uses
  either is reachable here."** `src/fmt_lzh.c`'s own header comment,
  under *What is NOT here, and why*, withdrawn 2026-09-22. Both are
  decoded, twenty lines below the comment, and the reason it gave was
  answered by patching LHa for UNIX to WRITE a specimen
  (`tools/run_lzh.py`, TESTING.md, *LZH's -lh2-*). **Cost:** nothing to
  any output — but it is a source comment contradicting the code beside
  it, which is the cheapest smell this repository names, sitting in the
  one place nobody looks while working in a file: its masthead.
  **Why it survived:** it was true when it was written, and closing the
  item updated the status files rather than the file the claim lived in.

- **"The 49 Tar entries the deark sweep cannot compare are deark
  writing an AppleDouble member as a literal `._NAME` file where `unar`
  merges it."** Written 2026-09-22 in TESTING.md and repeated in two
  other places, withdrawn the same day. A tar member is stored as
  `./NAME`; `unar` reports it without the `./`, deark keeps it, and
  **deark's own filename sanitiser turns that slash into `_`** — so
  `./READ_ME` reaches the disk as `._READ_ME`. None of the 49 files
  deark writes for `derived-PCCTS.tar` carries the AppleDouble magic
  and each holds its own member's data. **Cost: 98 forks of
  cross-check**, which matching the alternative name recovers — every
  one of them agreeing, taking the sweep to 2,151 agreements of 4,502.
  **Why it survived:** `._X` is precisely the filename the AppleDouble
  convention produces, and `unar` really does merge those, so the wrong
  explanation was corroborated by the evidence every time anybody
  looked at the list. What disproved it was opening one of the files —
  four bytes of reading.

- **"Russotto's write-up describes the SIT5 container too."**
  OPEN_ITEMS.md's XADMaster inventory and `src/fmt_sit5.c`'s own source
  line, withdrawn 2026-09-22. `reference/notes/arsenic_russotto.md` is
  method 15 from its first line to its last; nothing in it mentions an
  archive, an entry or a fork. **Cost: the row sat as "none: a parser"
  — nothing to be done — while the real description was one link from
  `reference/notes/StuffIt.md`**, the page StuffIt method 13 had been
  read out of two days earlier, in a *Sources* list. Fetched, the
  container came out at zero cost: 525 entries of 31 archives read from
  it alone (DECISIONS.md 2026-09-22, *the page the sources list
  named*). **Why it survived:** a citation to a document nobody opens
  is indistinguishable from a citation to one that says what it is
  claimed to say, and this one was plausible — the write-up IS about
  StuffIt 5, just not about its container.

- **"Where a StuffIt archive records its add-on module ID is not known
  here, and a specimen from an emulator session is the route."**
  OPEN_ITEMS.md and FORMATS.md, withdrawn 2026-09-28, the same day it
  was written. It is five header bytes and one method-byte flag, read
  out of StuffIt Deluxe 2.0.1's own application — a file that had been
  extracted onto this disk, and listed by our own engine, an hour
  before the claim was filed. **Cost: the smallest possible in hours
  and the largest in behaviour.** A fork whose method byte says an
  Optimizer ran decodes fine and yields the OPTIMIZED bytes, with the
  header's CRC agreeing and exit 0, so for as long as the field went
  unread this engine would have written a silently different file
  (DECISIONS.md 2026-09-28, *the six bytes Aladdin's own Get Info pane
  reads*). **Why it survived:** the item asked for a specimen and was
  right that no specimen exists — the mistake was concluding that the
  header question needed one, when the program that WRITES the header
  is a reference implementation under rule #1 and was already in hand.

- **"2.0.1 checks its serial number, so the optimized specimen needs a
  person with a licensed copy."** Written into FORMATS.md,
  OPEN_ITEMS.md, MANUAL_TESTS.md §8, BLOCKERS.md and a commit message,
  and withdrawn **forty minutes later, by the maintainer asking one
  question**: *macintoshgarden.org/apps/stuffit-deluxe doesn't contain
  2.0, where did you get it?* It does not. The 2.0.1 downloads are on
  **`/apps/stuffit-deluxe-2`**, a different page, which states the
  scheme for this version in as many words — *"Requires a name and
  serial activation: A nnnnn (where 'n' = any number, for example: A
  12345)"* — and also offers a build that is *"already
  pre-registered"*. `A 12345` was accepted on the first try and the
  application came up in Expert menus. The six codes tried before it
  were `spacesaver.py`'s, which are 3.0.7's and 5.x's, from the page
  that does not host this file. **Cost: three emulator runs, a
  registration wall invented out of the wrong page's codes, and a
  manual-test item filed for something a shell command could do** —
  all of it published before the question was asked. **Why it
  survived:** the codes were already in the repository with a citation
  attached, so reusing them felt like reuse rather than a claim; what
  was never checked is that the citation is to the page the FILE comes
  from. **A provenance line is a claim about a URL, and the way to test
  it is to open the URL.**

- **"The route to an optimized specimen is an emulator session on the
  machine every harness here already runs — Deluxe 2.0.1 installs on a
  68000 under System 6."** FORMATS.md and OPEN_ITEMS.md, **restored**
  2026-09-28 having been withdrawn the same day. The withdrawal was the
  wrong-page error above; with the published serial the route works and
  **three optimized archives now exist** (`specimens/sitopt/make2/`).
  What it cost is recorded in the entry above, and the original claim
  was right all along.

- **"`sitcrypt.py` drives StuffIt Deluxe 3.5.1."** Its own docstring
  since 2026-08-23, and tools/vmac/README.md reads the same way,
  withdrawn 2026-09-28. **Nothing in this project has ever launched a
  StuffIt Deluxe application** (withdrawn in turn 2026-10-10, below).
  Every dialog in those successful runs is
  **Magic Menu's**, drawn over a Finder menu bar —
  `specimens/sitcrypt/pw8/04-new-dialog.png` is "Create new archive as:"
  with *File Edit View Label Archive Translate* greyed above it — and
  the 3.5.1 application does not launch here either: three attempts,
  75 s each, one of them a control with nothing added to the image
  (**that half WITHDRAWN 2026-10-10**, table above: the three were ⌘O,
  and a double-click launched it the same day).
  **Cost: nothing to the encryption work, which only ever needed the
  archives, and three runs to whoever needed the application** — this
  session, going after the Optimizers dialog, which is in the
  application and nowhere else. **Why it survived:** the harness worked.
  A description of HOW a working harness works is the least-read line in
  any file, and Magic Menu's dialogs look exactly like the
  application's; the giveaway is the menu bar above them, which no
  screenshot was ever read for.

- **"One archive from a reversible Optimizer needs a person outside this
  machine."** MANUAL_TESTS.md §8, filed and deleted on 2026-09-28, in
  the same session, **because the maintainer said it did not**: *"I
  don't see it as a manual test, you can do it in emulation."* He was
  right. The item asked for a MacPaint, Sound or Photoshop document, on
  the grounds that the 933-fixture corpus has none — true, and the
  manifests were searched to establish it. What was never asked is
  **what would have to be handed to the emulator**, and the answer is
  nothing: MacPaint 2.0 is on this machine in a `.sea.hqx` our own
  engine unwraps, it runs under Mini vMac, and three dragged strokes
  and a Save produced a `PNTG/MPNT` document in one boot. Stuffed with
  `MacPaint 1` enabled it records **4** in byte 106 — the module's own
  id, which is the half of the reading that `Text 1`'s 255 could not
  confirm. **Cost: none, by one message.** **Why it survived four
  minutes:** the search that preceded it was real and its result was
  correctly negative, and a negative search feels like a finished
  question. **"Nothing here is one" is a fact about the corpus; the
  next question is whether anything here can MAKE one.**

- **"A `DCMP` would restore the original."** FORMATS.md, OPEN_ITEMS.md,
  TESTING.md and `src/fmt_sit.c`'s own comment, written 2026-09-28 and
  withdrawn the same evening by asking the application to do it.
  StuffIt Deluxe 2.0.1 with `MacPaint 1` installed unstuffs its own
  optimized archive to a file whose artwork is byte-identical from
  offset 512 on, whose 512-byte header differs in **486 bytes**, and
  which has **no resource fork** where the original had 501. A `DCMP`
  rebuilds a valid document; it does not give the bytes back, and the
  Addendum says so in as many words — the palette and patterns *"will
  use default settings"*. **Cost: nothing, because the BEHAVIOUR was
  never derived from it** — the refusal rests on the declared lengths,
  which name the original file while the stored data is a remnant, and
  that was in the header the whole time. What the claim cost was the
  reason attached to a right answer, which this file already names as a
  mechanism of its own (*a correct WORKAROUND with the wrong reason
  attached*). **Why it survived:** Aladdin's Engine says *"Please use
  StuffIt Deluxe instead"*, and "the application can do it" was read as
  "the application can undo it".

- **"`*selector` -2 and -3 ask a module for its name and kind."**
  FORMATS.md's ABI table, written 2026-09-28 from the application's CODE
  8 and withdrawn 2026-09-29 by disassembling both halves of `MacPaint
  1`. **-2 is the FINISH call**: a `DCMP` does the whole of its work
  there — it opens the file it was named at -1, writes a new header,
  copies the remnant in, and closes and deletes its temp file — and a
  `COMP` closes and deletes its own. -3 is the only selector either
  half answers with a string. **Cost: nothing, and that is the point.**
  The probe that confirmed the calling convention used -3, which
  works, so the row next to it was never exercised; a table filled in
  from call sites rather than from handlers has one entry per selector
  whether or not anybody has read the handler. **Why it survived:** the
  application's own CODE 8 shows -2 being passed a buffer, and "it is
  handed a buffer, so it fills the buffer" is a guess that reads like
  an observation.

- **"Producing the remnant means a decode-until-input-exhausted mode in
  every method, which `UncEntryInfo` has no way to describe."**
  OPEN_ITEMS.md and FORMATS.md, written 2026-09-28 and withdrawn
  2026-09-29 **by the maintainer asking why the decoders had to be
  touched at all.** They do not. Every method here decodes to a
  requested output length and stops, so a caller may ask for FOUR bytes
  — and the remnant's first four bytes are its own length, which
  `MacPaint 1`'s `DCMP` reads out of the caller's buffer on its first
  positive-selector call. Decode four, read 2,437, decode 2,437. The
  half of the sentence that survives is the entry-size contract: there
  is still nowhere in `UncEntryInfo` to say that a stored length differs
  from a declared one. **Cost: none in code, because nothing was built
  on it — and it had already been used once to size the work as "not
  worth opening", which is the expensive kind of wrong.** **Why it
  survived:** it was true of the decoders as written, and "the loop
  condition is wrong" slid into "the loop must change" without anybody
  asking what else could supply the right number. `unar` had the same
  bytes out the whole time: run against this archive it produces the
  2,437-byte remnant, byte for byte.

- **"An entry a reversible Optimizer touched cannot be extracted, and
  refusing it is not a judgement call."** FORMATS.md, OPEN_ITEMS.md,
  TESTING.md and `src/fmt_sit.c`'s own comment, from 2026-09-28,
  withdrawn 2026-09-29 when three of the four were implemented. The
  refusal was right about `JPEG Lossy` and wrong about the other three:
  `Sound 1` and `Photoshop 1` delta-code a fork and nothing else, so
  the file comes back EXACTLY and the entry's own CRC — the original
  file's — proves it, and `MacPaint 1` comes back as the same valid
  document StuffIt Deluxe gives. **Cost: one day of the wrong module.**
  The work went to `MacPaint 1`, whose `'DCMP'` is 3,010 bytes and
  needed an emulator harness to drive, because it was the module with a
  document on this disk; `Sound 1`'s is **264 bytes** and says all of
  itself in ten minutes of disassembly. **Why it survived:** the first
  module opened was the hardest one, and "a `DCMP` rewrites the file
  through the File Manager" was then generalised to all four from a
  sample of one. Two of them never touch a file at all.

- **"A ZipIt self-extracting archive is not recognised, and a probe
  that could see past the stub is not free: the cost is a backward scan
  for every file the sniffer rejects."** OPEN_ITEMS.md's own row for
  it, carried as UNMEASURED from 2026-10-04, withdrawn 2026-10-05 when
  somebody counted the reads. **The scan was already running on every
  one of those files** — `unc_zipseg_probe` sits one line above
  `unc_zip_probe` and does exactly that scan, 50.0 % of every read a
  sniff of the corpus makes — and when the record said "disk 0" it
  threw the answer away. Measured cost of the fix on files the sniffer
  rejects: **+0 reads, +0 bytes over 7,601 of them**; one four-byte read
  on a zip. **Cost: the five specimens went a day unrecognised, which is
  nothing — but the row had been written as a price, and a price is what
  stops an item being looked at.** **Why it survived:** the row named
  the right mechanism and never asked whether it was already there. Both
  probes were in the same six lines of the sniff order and the comment
  beside them says the scan happens; the claim was about cost, and the
  cost was somebody else's already (DECISIONS.md 2026-10-05, *the scan
  that was already being paid for*).

- **"A spanned-zip part is identified by its end-of-central-directory
  record and its disk number."** `src/fmt_zipseg.c` and FORMATS.md's
  zip rows, from 2026-08-09, withdrawn 2026-10-05. Those two things were
  the whole test, and four bytes of `PK\5\6` reached by a backwards
  scan happen by chance: a sweep of **8,364 files that are not
  Macintosh archives found five being claimed as `UNC_FORMAT_ZIPSEG`** —
  four Python `.pyc` files and one of deark's object files. **Cost: a
  wrong answer on about one file in 1,700 that is not an archive, for
  fourteen months, and the CLI's message for it asks the user to go and
  find the other parts of a set that does not exist.** It was found
  while measuring something else — the sweep existed to count what the
  ZIPIT change would newly claim, and the bigger number was what the
  build already claimed. **Why it survived:** no suite feeds this engine
  anything that is not an archive, so a false positive on ordinary files
  had nowhere to show. And the open item beside it was worrying that a
  *stronger* test — four bytes, a disk number AND a corroborated
  directory — might be too weak to adopt, which is the cross-file
  contradiction smell at its cheapest: the weak claim was already
  shipping.

- **"ZipIt 1.x upper-cased the names it put in the zip and kept the
  Macintosh ones in the field."** FORMATS.md's *ZipIt's own archives*
  and OPEN_ITEMS.md's row for the `0x2605` FileName, both from
  2026-10-04, withdrawn 2026-10-05. Of the three 1.x writers here only
  one did: ZipIt 1.4's own distribution zip and the Japanese 1.x's
  carry `Read me`, `Mac SEA` and `Drop files here to zip`, spaces and
  mixed case intact. The conversion is a **user preference** — ZipIt
  1.4's resource fork holds a `DOSN` boolean, "dosify filenames", and
  the help text "Convert filenames to MS-DOS compatible format (8.3,
  uppercase)" — so the population that diverges is "whoever left that
  checkbox on", which no version number bounds. **Cost: nothing in
  code — it never reached any.** What it cost was the only estimate
  anyone had of how likely the open item is ever to matter: filed as a
  habit of writers that stopped shipping in 1995, where the real answer
  is a switch any ZipIt can still have on. **Why it survived:** both
  halves of the disproof were inside ONE archive this suite already
  extracts byte-exact on every run — the counter-example names are what
  `macextract l` prints for ZipIt 1.4's own distribution zip, and the
  switch is in the application that zip carries — so it was two
  commands from a file already on the disk, and the claim was written
  about a version because a version is what the specimen table records
  (DECISIONS.md 2026-10-05, *a leaf is not a path, and a version is not
  a preference*).

- **"Nothing in reach was written by those two versions"** — PKZIP
  1.01/1.02's minimum-match-length bug, filed 2026-10-07 in
  `src/fmt_exo.c`'s decoder header and in FORMATS.md, *Implode*, as a
  measured negative over 19,107 bug-capable entries. **Withdrawn
  2026-10-08**: `PKZ101.EXE`, PKZIP 1.01's own July 1989 distribution,
  has three entries that decode to the stored CRC-32 only under the
  dictionary-size rule, and 1,323 of its kind are in the same index the
  negative came from. deark says `MML bug detection: 1`; `unar` and
  Info-ZIP `unzip` fail the same three on CRC and so does this engine.
  **Cost: one day, and that is the whole of it** — because the negative
  was written as a result *of a named key* rather than as a fact about
  the world, so re-testing it meant adding a key and never meant
  re-opening the question. The claim it actually displaced is the
  smaller one in the same paragraph, *"a rule this corpus cannot
  grade"*: the corpus could not, and a specimen table can, and the
  difference is one `detection=` token. **Why it survived:** the key
  that was used asks which files COULD carry the bug — a flag
  combination, which is a property of the archive — and the question is
  which files WERE WRITTEN BY 1.01, which is a property of the writer.
  The writer signs a self-extractor in its stub's `MZ` header, and a
  self-extractor is invisible to every `PK\x03\x04` token there is
  (DECISIONS.md 2026-10-08, *the stub is the writer's signature*;
  FORMATS.md, *The specimen that carries the bug*).

- **"DiskDoubler 3.7 enforces its header CRC and this engine does not"**
  — DECISIONS.md 2026-10-17, *the window StuffIt kept in the name*, filed
  from reading `dd_parse_filehdr` alone. **Withdrawn the same day**:
  `unc_diskdoubler_probe` has checked +82 since M0 (macutils' `C_HDRCRC`,
  XADMaster's zero exception), and a header with one byte flipped is
  "format not recognized". **Cost: one task** — the brief asked for that
  check to be decided as missing, and the redundant extractor check it
  invited would have been bytes on a 1 MB machine for nothing. **Why it
  survived:** the claim was about a format, and was tested against the
  one function named after the format's header (DECISIONS.md 2026-10-17,
  *the window Expander puts back*).
- **"FlCrDat is the local Mac time already, and local is what the sink
  wants, so no offset of either sign enters"** — `src/fmt_exo.c` on
  `0x334d`'s dates, and *the archives' own Finder info*'s "the GMT offsets
  unused", 2026-10-17. **Withdrawn the same day**: the dates are the
  WRITER's local time, and the reader's is another zone; the offsets are
  there to move between the two, and the format's own UnZip uses them
  (`AdjustForTZmoveMac`). **Cost: every MacZip date** was written one
  writer-zone-minus-reader-zone out on any Mac but the writer's — 5 h on
  all 22 of `rexnebular_1_0_0.zip`'s for a reader in UTC. **Why it
  survived:** XADMaster and deark disagree on the sign, and that was read
  as the question being moot rather than as a question with a document
  (DECISIONS.md 2026-10-17, *dates in the Macintosh's own zone*).
- **"A System 6 or System 3.0 volume has no Desktop Manager"** — the
  shell's own comment over `StampCat`, DECISIONS.md 2026-10-17 and
  2026-10-18 (*the icon Expander registers*), and behind it "every
  emulated tier passes on System 6.0.8". **Withdrawn 2026-10-21**:
  AppleShare's 1988 `Desktop Mgr` INIT gives System 6 one, the stock
  `System6.hfv` carries it, and under it `PBDTGetPath` answers noErr and
  `DTBundle` reaches `HOpenResFile` — a System 7 trap. Every tier here
  strips the System Folder to System + Finder (`mkboot.py`), so no sweep
  ever loaded the INIT. **Cost: the first bug report on the public
  repository, two days after v0.41.0** — uzTools/MacExtract issue #1, a
  Mac Plus under Mini vMac bombing "unimplemented trap" on two StuffIt 5
  archives, both of which the stripped 6.0.8 tier extracts byte-exact.
  Reproduced on the stock System Folder with the release binary,
  bisected to that one INIT (System + Finder + the INIT bombs; the stock
  folder without it completes), fixed with a working directory and
  `OpenRFPerm`, both in the 128K ROM. **Why it survived:** the tiers'
  stripping was written down as a cost measure (RAM on the 1 MB floor)
  and never as a blind spot, and "no Desktop Manager on System 6" was
  measured on exactly the volume the strip had produced (DECISIONS.md
  2026-10-21, *the Desktop Manager System 6 can have*; `run.py
  --keep-inits` is the lane that sees it now).
- **"The whole sample under `--keep-inits`, 74/74, says the INIT breaks
  nothing else"** — v0.42.0's fix for the row above, DECISIONS.md
  2026-10-21. **Withdrawn 2026-10-22**: its `PBOpenWD` at the top of the
  output returned the working directory the Finder had handed over, and
  its `PBCloseWD` closed it. **Cost: v0.42.0, the current download, on
  System 7.0.1 and on the stock System 6.0.8 folder** — the second
  archive of a Finder list refused (*"Could not open the archive."*), and
  every entry after an application with a bundle at the top of an output
  that is not a volume's root (*"could not be created"*); measured with
  `relaunch.py`, bisected to ba8f2d2, fixed by opening no working
  directory there. **Why it survived:** `run.py` extracts into a volume's
  root by dirID and the application into a working directory with dirID
  0, so no sweep took the application's branch (DECISIONS.md 2026-10-22,
  *the working directory the bundle closed*).

### Corrected figures and superseded write-ups

- **"No zip written by PKZIP 1.01 or 1.02 is in reach, so its
  minimum-match-length bug cannot be graded"** — what the Implode row
  was about to be filed as on 2026-10-07. **Not withdrawn: not filed**,
  because the search was run first, by MAGIC, which is this file's own
  oldest lesson. The bug is a decode outcome and not a byte, so the
  token names the two flag combinations where the two readings disagree
  (`detection=504b0304????02000600*` and `...04000600*`, 8,943 files)
  and the stored CRC-32 answers. **800 archives, 19,107 bug-capable
  entries, 19,105 by the specification, 0 by the bug, 2 by neither** —
  the 2 being two copies of one truncated `synchro.zip` that `unar` and
  deark refuse as well. **Cost: nothing, which is the point of doing it
  in this order** — and what it bought is that the 8,943 figure says the
  combinations are not rare in the WORLD, only here, so what the corpus
  lacked was a committable file and not a population. **The conclusion
  drawn from it did not survive, and is withdrawn above**: the sweep was
  extended to all 3,821 deduplicated candidates on 2026-10-08 — 29,795
  by the specification, still 0 by the bug — and a key for the WRITER
  rather than for the archive found a specimen the same day (FORMATS.md,
  *Implode*; TESTING.md, *Searching somebody else's index by content*).

- **FORMATS.md's *Three configurations, one tree* table, all six
  figures, for the FOURTH time.** It read 54,340 / 19,052 (eager),
  52,916 / 19,164 (lazy) and 164,324 / 37,916 (the resident control)
  against a build that says 54,272 / 19,056, 52,848 / 19,136 and
  164,408 / 37,928 — `tools/build_mac.sh`'s ratchets, which are set at
  the size on the day, had every one of them right.
  **Found 2026-10-07** by taking the Implode deltas AGAINST them and
  getting figures that did not subtract. **Cost: nothing, and that is
  the problem** — `CODE` + A5 came to the same total either way in all
  three configurations, which is the quantity every budget is derived
  from, so nothing in `ci.sh` could fail and the error was invisible to
  the one check that would have caught a real regression. The table is
  the only place these six numbers are written as a pair; the ratchets
  hold them as a sum. **Why it keeps happening:** a re-measurement
  entry is appended under the table and the table's own cells are left,
  so the prose below it is current and the rows above it are not. The
  rows are corrected from the build, and the Implode entry says so in
  place.

- **"Nothing in the corpus is encrypted."** Written 2026-08-23 and
  re-counted twice as the corpus grew — 903 fixtures, then 961 — and the
  measurement behind it was always `lsar -j`'s `XADIsEncrypted`, 0 for
  every entry. **Withdrawn 2026-10-07**: `fixtures/sitcrypt-wild-F7Menus.sit.bin`
  is encrypted, and that flag is still 0 for every fixture including it,
  because **`unar` cannot see StuffIt 2.x's `NewDE` bit** — method byte
  `0x12` it reports as `StuffItCompressionMethod: 18`,
  `XADCompressionName: "Compress"`, no flag at all, and then fails the
  entry *"Error on decrunching"*. Measured on the fixture and on 2.0.1's
  own `NewdeT.sit.bin`, against `0x8D` on the same specimens, which does
  set the flag. The bit it is blind to is the same `0x10` the published
  table calls a folder marker, so this is the published misreading
  arriving one layer down, in the instrument rather than in a parser.
  **Cost: nothing yet — the claim was true when written and no decision
  rested on it** — but it is the shape that matters: a corpus-wide
  negative measured through somebody else's flag is a claim about the
  flag. Corrected in place in FORMATS.md (*Encryption*), TESTING.md
  (*Decryption*) and `tools/run_crypt.py`, which all three stated it
  separately.

- **`fuzz_cover.py`'s noise floor: "seeds 11 and 12 over an identical
  build differ by up to five functions in a family."** Measured
  2026-09-27, corrected 2026-10-05 to **thirteen** — ARC 0 against 13,
  StuffIt classic 8 against 1, at 3,000 cases over one build. (That pair
  was first recorded as 9 against 2, which was the row before method 14
  was split out of it; the eleventh function was at zero at both seeds,
  so one of each figure was structure.) The
  original number was right about the three families it named and was
  written as a bound over all of them. **Cost: nothing — it is the
  cautious direction, and the conclusion it guards (read whether a
  family is WHOLLY at zero, at more than one seed) is unaffected** — but
  a noise floor is quoted to decide whether a delta is real, so a floor
  that is too low is the one error that makes a non-finding look like
  one. Corrected in TESTING.md, OPEN_ITEMS.md and the tool's own
  docstring, which are the three places that cite it.

- **"The tables are not in the stream, so they are in the module;
  implementing this means recovering them from 9,176 bytes of code."**
  FORMATS.md and OPEN_ITEMS.md, written 2026-09-29 and withdrawn the
  same day by the spike it was the justification for. **Every parameter
  is in the payload**, which is a TIFF: quantisation tables at private
  tag 33606, DC and AC Huffman tables at 33607 and 33608, quality at
  33604, geometry in the ordinary IFD entries. **Cost: it was the whole
  cost estimate** — "a JPEG decoder PLUS recovering the tables from a
  disassembly" is a different piece of work from "a JPEG decoder", and
  the second was quoted to the maintainer as the first. **Why it
  survived:** two searches that were both real and both in the wrong
  place. The tables were looked for in the `COMP` and `DCMP` resources
  and never in **the module file's other resources** — which hold
  `DATA` 1000 and 1001, the tables, and a 31,952-byte `C3a` named
  *"C-Cube V1.0"* that is the actual codec. And the payload's first four
  bytes, `MM\0*`, were printed to the screen the day before while the
  question being asked was "is there an `FF D8` in here". **A structure
  announces itself in its first four bytes; a negative answer to the
  question you asked is not an answer to the question you have.**

- **"There is no oracle and no subject for `JPEG Lossy`; a genuine
  Photoshop 1.0 document would need Photoshop 1.0."** OPEN_ITEMS.md and
  FORMATS.md, 2026-09-29, withdrawn the same day **when the maintainer
  asked whether one could be made in emulation.** It could, in about an
  hour: Photoshop 1.0.7 is a 441 KB download, this project's own engine
  unwraps it, and it runs on Mini vMac's Mac Plus — which its own
  requirements page rules out, saying *"Macintosh SE or newer"*. A
  document it wrote round-trips through the module. **Cost: none yet,
  and it would have been the item's whole justification.** **Why it
  survived:** the same shape this file has already recorded twice — a
  correctly negative search of the CORPUS was read as a negative answer
  about the MACHINE. The rule was even written down after the MacPaint
  case: *"Nothing here is one" is a fact about the corpus; the next
  question is whether anything here can MAKE one.* It was not asked
  here either, and the difference was one question from somebody else.

- **"Why StuffIt Deluxe 2.0.1 refuses its own `JPEG Lossy` archive is a
  hypothesis; a real Photoshop 1.0 document would settle it."**
  FORMATS.md and OPEN_ITEMS.md, written 2026-09-29 and settled the same
  day, **by the maintainer asking whether it could be tested.** It
  could, and not on a Macintosh: that entry's method nibble is 0, so
  the 80 stored bytes ARE the module's output, and four of them are
  non-zero with no `0xFF` in the fork at all. No JPEG stream can be
  that. The archive holds an empty header, so nothing could decode it
  and no document would have changed the run. **Cost: one emulator
  boot that was not needed** — the answer was in a file already on this
  disk, and the run before it had already printed `dcomp=80` next to
  `dlen=115320`. **Why it survived:** a modal alert is a vivid result,
  and a vivid result gets explained rather than checked. The refusal
  was a fact about the ARCHIVE and was read as a fact about the module.

- **"`JPEG Lossy`'s `'DCMP'` is a 9 KB JPEG decoder"** was written into
  FORMATS.md, OPEN_ITEMS.md, `tools/run_sitopt.py` and `src/fmt_sit.c`
  on 2026-09-29 and corrected the same day, **by the maintainer asking
  what the status rested on.** It rested on the module's NAME and its
  SIZE. The code has never been read: none of the standard JPEG tables
  — the zigzag order, Annex K's Huffman bits, the luminance
  quantisation table — is in it verbatim, which settles nothing either
  way. It is 9,176 bytes and it is lossy (the application prints
  *" lossy"*, and the entry carries `ffff` where a checksum goes), and
  the refusal was always right on those grounds alone. **Cost: nothing,
  because the behaviour never depended on it** — but it is the third
  unlabelled inference this file has collected in two days, and the
  cheapest possible tell was present: every OTHER module's row cites a
  disassembly and this one cited a filename.

- **`MacPaint 1`'s data path was written as a loop over `_Read`,
  `_Write` and `_SetEOF`** (FORMATS.md, 2026-09-28). There is no
  `_SetEOF` in either half of the module. It is `_Read`, `_Write`,
  `_GetEOF` and `_SetFPos`, plus the HFS `_HOpen`/`_HCreate`/`_HDelete`
  — the $0200 variants — and `PBGetFCBInfo`, which is how it decides
  where to put its temp file. Corrected in place 2026-09-29; nothing
  depended on it, and it is listed here because a trap list is the kind
  of claim that gets copied.

- **"AppleLink `.pkg` cannot be sniffed without inventing a magic number" was
  withdrawn on the wrong grounds, and the probe that replaced it is now gone
  too.** The 2026-08-23 reading — `PKG Expand Translator`'s @0x2952
  tokenizes and accepts `Decode <thing> to|into <place>` — is an accurate
  transcription of that routine. It is not a recogniser for a FILE: the same
  routine, instruction for instruction, is in the CompactPro, UnZip, BinHex4,
  UUCode and Unix Compress translators on the same disk, each with its own
  `STR# 129` verbs and its own extension in item 3, and its input is a Handle
  the host passes at `param+4`. It parses the translator API's command
  language. So `macextract sniff` named `Decode "Payload.hqx" to "Out"` an
  AppleLink package — which is equally the CompactPro translator's command —
  and named neither real package anything. `unc_applelink_probe` was removed
  2026-09-27 and the unit test now asserts its absence. **Cost: 35 days of a
  format counted as *named* that never named a file, a supporting measurement
  ("0 false positives across 928 fixtures") that could not fail because the
  corpus held neither a package nor a script, and the seven boots of
  2026-09-01 spent trying to hand Aladdin's expander a package — a dialog
  that lists only directories was the same fact from the other side.** The
  smell is a new one and it is on the list: **a routine transcribed
  faithfully and asked a question it does not answer.** What would have caught
  it on the day: the translator beside it handles a format this project
  extracts 108 fixtures of, and that routine rejects every one of them
  (DECISIONS.md 2026-09-27, *the recogniser that was a command line*).

- **"The shipped model is pessimistic by 2,926 B, against a recorded 1,138 B
  residue"** — carried as a labelled hypothesis for one day and withdrawn
  2026-09-27, when the base and the grant were taken from one tree and one
  probe pair. Neither number was wrong and the subtraction was not a
  measurement: the base had been taken on another branch, and re-taken it was
  **652,996 B** rather than 648,250 while the residue was **−714 B** rather
  than +1,138 — **+4,746 less 1,820, the 2,926 B to the byte**. (Both moved
  again the same day when the AppleLink probe left, to 653,532 B and −666 B,
  and the ten per-format GAINS between them did not move at all.) The residue
  was never a structural constant either; it is per-build slack, and it goes
  stale exactly when a tier budget does — while the 346 B of it that nothing
  accounts for was the same either side of that 496 B change. **Cost: nothing, because it was
  labelled.** Had it been corrected on the day it was seen, the 2,926 B would
  have gone into `OVL_RESIDUE` and the model would have been wrong in both
  terms at once — the same error this file already records for the floor
  budget, where a correct 896 B sum was applied to a three-week-old base. The
  attribution offered with the hypothesis was also wrong, by 200x: "this
  tree's application is ~24 B smaller" is what the code-size table says
  v0.34.0's segment check cost, and the base had moved 4,746 B (DECISIONS.md
  2026-09-27, *the residue that was two numbers*).

- **`OVL_SAVED` = 117,056 B** — 32 B stale from 2026-09-26 to 2026-09-27,
  under a comment naming FORMATS.md's *Three configurations, one tree* as
  "the only place to correct them", which had been corrected. Every format's
  budget is that constant less the images it keeps, so it moved thirty
  budgets at once and hid inside the residue above. **Cost: part of a
  hypothesis that took two boots to settle.** It is graded against the two
  builds it is the difference of from 2026-09-27 — `run_tiers.py
  --check-saved`, in `ci.sh` after the resident control — because *a comment
  saying where a number lives is not a check.*

- **"`overlay-eager` costs one archive at 512 KB against `selective-loading`"**
  — withdrawn 2026-09-03 on the branch, recorded here on 2026-09-25 when the
  branches merged. The gap was measured at 15,748 B and attributed to the
  cipher image the eager lifetime must keep for a format that MAY encrypt,
  which was true and irrelevant: releasing the ciphers raised the budget to
  317,838 B and `derived-a2basic.dmg.sit` still failed, `gRefusedWhy` = 2 —
  `NewPtr` returning NULL for a 205 KB block against a largest free block of
  169,298 B. **The memory was there, in two pieces.** One `MoveHHi` before
  the `HLock` — the kept images are locked for the rest of the run, and
  `NewHandle` had been putting them in the middle of the heap the released
  bundle had just vacated — closed the gap entirely. **Cost: a day chasing
  the wrong cause**, and the instrument had been saying so all along:
  `gRefusedWhy` = 2 means the heap could not do what the budget said it
  could, which is fragmentation and not shortage. **A number that explains a
  gap is not the same as a cause.**

- **"One disk read at launch"** — the eager branch's whole argument, and
  untrue in the build a user would have run, for as long as the branch had a
  bundle. `ovl_preload()` was called from the AUTOTEST `main()` and not from
  the interactive one, so the shipping application never preloaded: the shim
  fetched the bundle lazily on first use, which is the precise thing the
  lifetime exists to avoid. **Found by forbidding the reload**, not by
  review: once `ovl_image()` refused to re-read the resource fork, an
  encrypted StuffIt archive stopped decrypting and the probe said `wa=128`.
  **Cost: every figure taken through `interactive.py` before 2026-09-02 was
  measured on a build that loaded nothing at launch** — the envelope row read
  705,352 B and is 689,108 B once the preload happens. The autotest columns
  were never wrong, because the autotest is the `main()` that had the call.
  **"Which `main()`?" is worth asking of every launch-time call**; a ballast
  referenced from only one of them had already cost three measurements
  (FORMATS.md, *What the application costs the engine*).

- **"`os9.py --autotest` scores `os9sample.txt` 19/22 with a healthy
  build"** — written and withdrawn the same day, 2026-09-25. It was
  measured, twice, with a control: three fixtures failed on that route
  with overlays and the same three failed without them, so the number
  was recorded as the route's own. It was a harness defect in both
  halves. `.Z` and `.gz` name their single entry after the archive and
  the route renames every input to `archive.sit`, but handed the
  REFERENCE the fixture's own path — a mismatch `verify_output()` had
  fixed on 2026-08-08 and this verifier, written later, never inherited;
  and a detect-only `.rar`'s correct refusal was failed for not being
  `UNC_OK`. Both fixed, and the same three now pass 3/3 on the build
  that failed them. **Cost: one wrong figure in four files for an
  afternoon, and very nearly a fixture sample trimmed to fit it** — the
  proposal on the table was to drop the three from `os9sample.txt`.
  **Why the control did not catch it:** it compared the overlay build
  against the resident build, and the defect was in neither — an A/B
  that agrees says the difference is not there, never that either side
  is right (`tools/vmac/README.md`, *`--autotest` scored three healthy
  fixtures*).

- **"The overlay prize is 5,988 B, it opens nothing new, and StuffIt can
  never be one of the formats it helps"** — all three superseded or
  withdrawn 2026-09-25. They were written 2026-08-31 about an overlay
  holding the ciphers and nothing else. `overlay-eager` has carried
  fourteen images since 2026-09-24 (fifteen until DART left on 2026-09-25):
  **82–105 KB** more budget at 1 MB than
  a resident build, **69/71 at System 3.0 / 512 KB against main's 67/71**
  — `derived-a2basic.dmg.sit` and `derived-Cool_Tools__.sit`, two
  archives `main` cannot open on that machine — and StuffIt gains like
  everything else, it merely cannot release the ciphers, which are
  10,702 B rather than the 15,324 B they were before the DES tables went
  transient. The download figure moved the same way: +2,304 B was the
  cipher bundle, **+25,216 B** is this one (189,312 → 214,528 B, both
  configurations built at the branch tip). **Cost: three weeks in which
  the scope file priced a mechanism at a seventeenth of its measured
  value**, and recorded "opens nothing new" of a build that opens two
  archives at 512 KB. The decision it justifies has not moved, for
  reasons that are now different ones (DECISIONS.md 2026-09-25, *the
  parked decision that outlived its numbers*). Found by the cheapest
  smell in this list — BRANCHES.md said 18,116 B, OPEN_ITEMS.md said
  5,988 B, the branch said neither — which had been readable since
  2026-09-02.

- **"walkprobe.py grades every volume walk in the tree"** — corrected
  twice, 2026-09-22 and 2026-09-23. It graded six of eight, then eight of
  nine. The missing ninth is `nowcompress.read_forks`, a different
  function sharing a name with `superdisk.read_forks`, and
  `nowcompress --adjudicate` calls it. **Cost: one harness re-run that
  proved nothing** — it was run to verify the `superdisk.read_forks`
  filter and exercised a blind walk instead, coming back green. It gave
  itself away by printing no filter line. Both errors came from searching
  for a spelling (`hls`, then the name `read_forks`); searching for the
  capability finds **thirty** volume listers in `tools/`, nine graded
  (DECISIONS.md 2026-09-23, *the ninth walk, found by the missing line*).
- **"`superdisk.read_forks` has about thirty callers, several of which
  compare fork SETS"** — corrected 2026-09-22. It has **38** call sites
  across nine harnesses, and **no** caller compares fork sets. Four
  compare ENTRY sets, which is the same hazard: `--adjudicate` in
  `superdisk.py`, `nowcompress.py` and `diskdoubler.py`, and
  `superdisk.py --nest` hold every entry on the guest volume against our
  own extraction. **Cost: nothing, and it nearly cost the opposite** —
  reading for the phrase "fork SETS" found no caller matching it, which
  looked like grounds to call the whole estimate stale and the work
  cheap. The estimate was right about the risk and wrong about its name.
  The fix was one root filter inside the walk serving all 38 sites
  (DECISIONS.md 2026-09-22, *the last walk, and the exit code nobody
  could get*).
- **`superdisk.py --adjudicate` has always exited 1**, including on runs
  where every fork was identical: its final line referenced `shots`, a
  local of another function, and raised `NameError` after the verdict had
  printed. Found 2026-09-22, by running the harness instead of
  `tools/run_superdisk.py`, which is what `ci.sh` calls and which replays
  the verdict by content. **Cost: an exit code that could never say
  success, for the life of the phase.**

- **"hfsutils hides names beginning with a dot without `-a`"** — withdrawn
  2026-09-22. It hides a file whose Finder INVISIBLE bit is set, and the
  dot is irrelevant. Measured as a 2x2, all four cells
  (`tools/vmac/walkprobe.py`): dotted and visible is listed without the
  flag, dotted and invisible is hidden, undotted and invisible is hidden.
  `.DS_Store` needed `-a` because a Macintosh writes it invisible.
  **Cost: one harness failure, one check that could not fail, and four
  walks still blind.** `os9.py` reported `Icon\r` MISSING off a volume
  that held it with 51,781 bytes of resource fork.
  `mkboot.verify_stripped` — which asserts the property every peak-heap
  figure's comparability rests on — read its listing without `-a`, so
  the files the strip cannot delete were exactly the ones it could not
  see; an invisible `Ghost INIT` planted in a stripped System Folder
  passed it. **All eight volume walks see an invisible entry since
  2026-09-22** (`tools/vmac/README.md`, *What every walk can see*).
  **The fact had been observed four separate times** — in `checkdisk.py`,
  `arcmac.py`, the yardstick's Standard File row and `mkboot.py`, the
  last of which states it correctly one function above a comment blaming
  the disk — and generalised none of them. The fix was right and the
  explanation is what got copied.
- **The OS 9 boot time** was recorded as "about four minutes", then "20-45
  minutes". An idle host settles the desktop in **~110 s**; both earlier
  figures were host load written down as a property of the guest.
- **`macburger-helper.hqx` was written up three times as an anomaly.** It
  simply takes 150 s. A decode rate this non-uniform expires every fixed
  timeout mid-run, and **a timeout expiring is not a measurement**
  (`tools/vmac/README.md`).
- **`popper-1.7.tar.Z` and `PCCTS.tar.gz` at 1 MB** were root-caused and
  fixed: the sink accumulated each whole fork in a `NewPtr` block, so the
  shell needed `archive + engine peak + largest output fork`. Streaming writes
  took the sweep 37/44 → 39/44; the old path stays buildable as
  `UNC_MAC_STAGE_WRITES`.
- **The "all-black screen crash"** chased during M10 was a harness artifact: a
  launcher that backgrounded the emulator and exited took it down by SIGHUP,
  and a dead X window reads as pure black.
- **The `mio_seek` eofErr fix** is correct and kept, but it was not the M10
  blocker either.
- **"`interactive.py`'s default phase never reaches a result alert"** was
  written into DECISIONS.md on 2026-08-24 and is wrong. That phase clicks
  Cancel at a fixed time; an extraction that FAILS before then leaves its
  result alert on screen, and the `extracting` frame photographs it. Which
  is how the low-memory alert was finally photographed, on the phase already
  declared unable to show it. **Cost:** one day, and the item it was the
  stated reason for was in OPEN_ITEMS.md the whole time.
- **The Mac OS 9 harness was damaging its own disk image** by booting the
  master in place and never hashing it. Fixed: the published SHA-1 is verified
  before every run and the master is copied to a throwaway
  (`tools/vmac/README.md`).

- **Six corpus figures the seven-sentence check could not see.**
  `check_docs.py` check 10 was written on 2026-10-06 to hold corpus-size
  figures against counts taken the way the harnesses take them, and it
  named seven sentences. It worked at all seven. **Corrected 2026-10-07
  by scanning the CLASS instead**: `FORMATS.md`'s *Verification* row and
  `OPEN_ITEMS.md`'s fuzz-draw sentence were still at 951 against 954
  manifests; `FORMATS.md`'s foreign-probe sweep was at 940 against 966
  corpus files; and three sentences in `FORMATS.md` and `TESTING.md` had
  stopped being TRUE rather than merely current — *"no corpus file"* for
  btoa and for MIME, measured today as one each, both the Mac OS 9
  tier's own unmanifested fixtures (`synth-os9-btoa.btoa`,
  `synth-os9-mime.mim`, beside the deliberate `synth-os9-rar.rar`). The
  scan takes a window per kind, so a year or a per-format count is not
  mistaken for a corpus size, and 17 historical figures are declared in
  the checker with the measurement each belongs to. **Cost: nothing
  measurable — every one was a denominator or a "none of them" — and the
  lesson is the shape:** a check that names the sentences it holds is a
  spot-check of the claims somebody remembered, and the sentences that
  rot are the ones nobody is thinking about (DECISIONS.md 2026-10-07,
  *the seven sentences that were not the class*).

- **`UncOptions.long_name`'s own documentation promised a length the
  walker had stopped keeping.** The field's comment said a NULL buffer
  *"costs nothing and loses only the text: the length is still reported
  in `name_full_len`"*, and the walker rewrite of 2026-10-07 made that
  false for a PATH — it builds the uncut path in the host's buffer, so
  without one there is nothing to measure and `name_full_len` is 0. The
  commit that changed it said so in its message and did not sweep the
  header. **Corrected 2026-10-07** at the field and at `name_full_len`,
  which had attributed 0 to one cause when there are now two. **Cost:
  the public contract was wrong for the hours between, and no host here
  reads that length — the CLI takes the text, the Mac shell takes
  neither.** Also stated there now: `long_name_cap` above 65,536 is not
  supported, because `UncPath.len` is 16-bit. Measured, not inferred: at
  a 1 MB buffer the length wraps 65,535 → 31 at the 2,048th component
  and the walk rewrites the host's buffer from its start. The CLI passes
  exactly 65,536, which is safe by one byte.

- **`UNC_PATH_MAXDEPTH` was deleted from the code and left standing in
  the prose.** Six places still described it in the present tense after
  2026-10-07 removed it: `FORMATS.md` twice, `TESTING.md`'s suite
  section and its title, `ci.sh`'s lane comment,
  `tools/measure_depth.py`'s premise, `tools/build_mac.sh`'s ceiling
  note (which also still described `path_too_deep` and
  `UNC_ERR_TOODEEP`, both deleted with it), and
  `tools/vmac/depthtest/main.c`, which PRINTED *"UNC_PATH_MAXDEPTH is
  24"* onto the Macintosh screen — the probe whose own answer deleted
  the constant. **Cost: nothing yet** — all of it was corrected the same
  day — but an instrument that reports a constant that does not exist is
  the shape that makes a future measurement unreadable.

- **The download's size, 227,968 against 227,840.** `tools/build_mac.sh`'s
  ceiling note for the minimum-match-length work put `MacExtract.bin` at
  227,968 B where the committed `dist/` and FORMATS.md's own two tables
  both said 227,840 — one 128-byte block out, in the comment that
  justifies a ratchet. **Corrected 2026-10-08** when the recovery's own
  figures were taken against it and the subtraction came out 128 B wrong.
  **Cost: nothing but the confusion of a figure that disagreed with the
  artefact it describes** — and the mechanism is worth the line: a
  ceiling's comment is prose beside a number nothing derives, so the
  number is checked on every run and the sentence beside it is not.
- **"Every figure is a lower bound with a ±3 s poll error"** — the
  Expander yardstick's own description, FORMATS.md *Timed on the same Mac
  Plus*, 2026-08-29 to 2026-10-19. **They were upper bounds**: the
  screenshot loop stamped the first poll AFTER the last change. Re-timed on
  the Mac's own `Ticks` (`tools/vmac/macclock.py`), Expander's unchanged
  code reads 0.6–2.3 s below every published cell. **Cost: the StuffIt row
  stood as "level, 1.00x" for seven weeks** on an instrument that could not
  resolve the 2 s it now shows (52.4 against 54.4 s), and nobody had derived
  the bound's direction from the sampling loop (DECISIONS.md 2026-10-19,
  *the clock inside the Mac*).

# BLOCKERS.md

## Status

**No open blocker.** The one this file carried on 2026-09-04 — the
application bombing on Mac OS 9.2 on every DiskDoubler archive and on
SuperDisk! — was a field of `UncOptions` the Mac shell never assigned, and is
withdrawn below with what it cost (*Withdrawn claims*; the reasoning is
DECISIONS.md 2026-09-04, *the field nobody assigned*). The engine and Linux
CLI were never affected by anything in this file. The Retro68 Mac shell runs
and extracts byte-exact on every system the project claims:

| tier | result |
|---|---|
| System 3.0 / Finder 5.1, 4 MB Mac Plus (Mini vMac, a true 68000) | **69/69** sampled fixtures. System 3.0 ignores the boot blocks' shell name, so the application cannot replace the Finder and is double-clicked instead — which changes how the run starts and not what it has: launching unloads the Finder, measured at 12 B (FORMATS.md, *512 KB machines*) |
| System 3.0 / Finder 5.1, **1 MB** — the oldest system, at the same RAM floor | **69/69**; the application driven end to end there too, where Cmd-. does not cancel Standard File and the Cancel button does (FORMATS.md, *System 3.0 tier*) |
| System 3.0, **512 KB** Macintosh 512Ke | **66/69**; the three shortfalls are per-entry memory refusals, not failures — the budget there is 197,728 B. The same machine under System 6.0.8, with no Finder at all, does 63/69 (re-measured 2026-09-04; 58/69 before the stack cut), and 3.0's failures are a strict subset of 6's (FORMATS.md, *512 KB machines*) |
| System 6.0.8, 4 MB Mac Plus (Mini vMac, a true 68000) | **69/69** sampled fixtures |
| System 6.0.8, **1 MB** — the RAM floor | **69/69**; no memory-budget refusals remain, and DiskDoubler method 5's 396 KB allocation succeeds here |
| System 7.0.1, 4 MB | **69/69** |
| Mac OS 9.2 (QEMU PowerPC, 68LC040 emulation) | **21/21** — re-run 2026-09-04 on the build that zeroes `UncOptions`, the sample one larger for Now Compress, the third folder-walking format; that morning it read 18/20 with the two failures bombing the application, and 20/20 when last run on 2026-08-27. Off-sample the same day, **all six DiskDoubler archives in the corpus, 6/6 byte-exact**, where the morning's binary had bombed on every one; plus HFS+, the `SIZE` partition, and — since 2026-08-28 — both cancel routes, the Cmd-. chord and the Cancel BUTTON clicked with the pointer, an 8-bit name photographed, an encrypted archive decrypted through the password dialog after a wrong password was refused, and SpaceSaver replayed by path — the format no Macintosh tier had ever run, whose first run found a name defect in the shell (FORMATS.md) |

**Every Mini vMac tier was re-run 2026-09-20**, the first time any had
been since the decoder work of 2026-09-18/19/20 changed six formats and
took 360 B net off the budget. **Five sweeps of the 69-fixture sample,
and every one reproduced its recorded figure**: System 6.0.8 at 4 MB
69/69 and at 1 MB 69/69, System 3.0 at 1 MB 69/69, and at 512 KB
System 3.0 66/69 against System 6.0.8's 63/69 — the same three and six
per-entry memory refusals as before. No refusal moved anywhere.

All three Mini vMac tiers re-run **2026-08-22**, with M15–M23's codecs in
and three fixtures added to the sample for them — DiskDoubler methods 3, 4
and 5, which nothing in the list had exercised. The two System 6 tiers were
run again on **2026-08-23** against the decryption build, which is 20 KB
larger and so leaves the 1 MB machine that much less heap: **62/62 on both**,
with the three heaviest allocations (533 KB, 471 KB and method 5's 405 KB)
unchanged. The 1 MB tier has been run again after each addition since — WinZip's
AES, the StuffIt key correction and btoa — and was 62/62 every time. All
three tiers were re-run on **2026-08-23** with LZH in and five `.lzh`
fixtures added to the sample (M28): **67/67 on each**, the new ones costing
4,112 B of heap at the small end and 41,364 B for a `-lh7-` entry. M33's two
PAK methods were run on **2026-08-25** at 4 MB and at the 1 MB floor —
`arc2pak1.pak` (0x0a, 46,546 B peak, now in the sample) and
`derived-INTRECHO.pak` (0x0b, 14,790 B, 918,631 B of output, `--out-kb 1600`)
— **1/1 at each size, four runs**; the rest of the sample was not re-run for
a 2,048 B binary growth, which FORMATS.md (*ARC*) states in full. All three
Mini vMac tiers were re-run on **2026-08-26** for M37's disk-image probe and
again the same day for M38, which changed the application as well as the
engine (the detect-only alert): **69/69 on each, both times**. The first of
those was also the first sweep to cover the whole sample —
M33 and M34 had added `arc2pak1.pak` and `derived-ARCDOS.arc` on 2026-08-25
without a full re-run, so every "67/67" above describes a sample two
fixtures smaller than `sample.txt` already held. Per-fixture tables and how
the sample grew: FORMATS.md. How to re-run any of
it: `tools/vmac/README.md`. What no emulator here can settle:
MANUAL_TESTS.md.

---

## What is true, and load-bearing

**How the Mac shell is verified.** The autotest build CRC-32s both forks after
reading them back through the real File Manager and paints the aggregate to
the framebuffer; the host decodes a screenshot and compares against the same
engine's Linux output. Since 2026-08-02 the Out volume is also read directly,
which adds the one thing an aggregate cannot carry — **names**. The off-Mac
blind spot is real: the qemu-m68k mock calls the sink directly and never
touches the Toolbox glue, so only Mini vMac exercises that layer.

**The fix that unblocked M10 — and what is still unknown about it.** Driving
the File Manager through explicit, fully-zeroed HFS param blocks
(`PBHOpenSync` / `PBHOpenRFSync` / `PBHCreateSync` / `PBHDeleteSync`)
unblocked everything at once and is what ships. **Why it worked is not
established.** The original attribution — a broken Retro68 `HOpen` — was
disproved (below). The likeliest remaining explanation is that the helpers
zero the whole param block where the pre-fix code passed partly-uninitialised
state, but that has never been reduced to a reproduction, so it is a guess and
not a finding. It is not being chased: the app is verified byte-exact as it
stands.

The one upstream finding that survived: **both `OpenDF` and `HOpenDF` return
`paramErr` on System 6**, because the `_OpenDF` trap is System 7 and neither
has a fallback — `FSOpen`, in the same glue file, does. Written up in
`tools/retro68-hopen-repro/ISSUE.md`, deliberately not filed; the maintainer
will post it.

**`HideCursor()` before drawing the grid — CONFIRMED, with a reproduction.**
Built without it and with the host pointer dragged through the grid's cell
centres, the decoded result comes back as `0x04000000` — one flipped bit, a
cell stamped over by the cursor's saved background. The stock build survives the same drag.
Reproduced twice. The two things that must be right before the test means
anything are in `tools/vmac/README.md`; both early attempts "passed" while
testing nothing.

**The oracle is wrong about one method, and the suites know it.** `unar`
decodes ARC/PAK method 0x0b (Distilled) to the right length and the wrong
bytes wherever a match reaches back past the start of the data, because
XADMaster starts the 8 KB window at zero and PAK fills it with spaces
(withdrawn claims, below; the reasoning is in DECISIONS.md). So for that
one method the oracle is **deark**, built by `tools/build_deark.sh`, and
`tools/run_pak.py` never consults `unar` about it; `make_manifests.py`
offers it the forks `unar` failed. `unar` remains the oracle for 0x0a
(Crushed), which deark does not implement at all, and for everything
else. Both are outranked by the CRC-16 PAK stored per member, which is
the only check in this format no decoder here can influence.

**`unar` does not read ARC 7.x at all.** Every archive ARC+Plus writes
opens with an informational item (method 0x14), and XADMaster's parser
stops there — `unar` and `lsar` both answer "Couldn't recognize the
archive format". It also reads method 0x0a as Crushed unconditionally,
so it could not grade Trimmed even given the container. deark reads
both, which is why `tools/run_arcplus.py` consults it and not `unar`,
and why `fixtures/manifests/derived-ARCDOS.arc.json` is registered by
that tool rather than built by `make_manifests.py` (TESTING.md).

**Detect-only gap — RESOLVED.** DiskCopy 4.2 was named in `unc_sniff` and
never detected, for want of a reference. One was obtained
(`reference/notes/DiskCopy42.md`) and the probe is real: a synthetic 800K GCR
image and a real one match, 0 false positives across the corpus. Still
detect-only — disk images are out of scope for v1.

---

## Withdrawn claims

**Kept deliberately, and this is the part of the file to read first.** Twice a
live claim has been re-tested *because* it sat beside an already-withdrawn one,
and one of those was worth 39/44 → 40/44 at the floor target. Ten mechanisms
keep finding the next one, and two of them need no insight at all:

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
  reason since the ARC specimens; nothing compared the two.

Each entry is what was claimed, what disproved it, and what it COST. The cost
line is what makes the next one worth re-testing.

| claim | disproved by | withdrawn |
|---|---|---|
| **A member deark wrote at all has both forks, so a fork with no file on disk is one deark read as EMPTY** — which is the assertion `make_manifests.py` lets the third oracle make on its own, and the comment stating it (TESTING.md, *A third oracle*) | **deark writes a member's resource-fork sidecar, declines its data fork, and writes no data file.** `derived-BitMap11.sit`'s `BitMapHelp.index` is StuffIt method 8, which deark does not implement: it prints `Unsupported compression method: 8 (MW)` and the absence read as a 0-byte fork. **Cost: nothing yet, which is the only cheap time to find one** — no manifest records a false empty, because the gap-filling path had never been offered such a fork. Found 2026-09-22 by `tools/sweep_deark.py`, whose whole purpose is asking the oracle where nothing was open (DECISIONS.md 2026-09-22, *the oracle asked about everything else*) | 2026-09-22 |
| **deark's output is matched by name** — `make_manifests.py` and TESTING.md both, as the rule that replaced matching by position on 2026-09-21 | **By the name deark WRITES, which is not the name the archive holds.** deark writes each member to a real file, so a member inside a folder arrives with its separators mangled to `_`; matching raw names skipped **every entry in a folder, 500 of them**, and reported success on the subset it could match. **Cost: the third oracle's coverage, 1,641 forks where 2,075 were available** — a quarter of the cross-check, for one unmodelled sanitiser (`de_char_to_valid_fn_char`, one function in `reference/deark/src/deark-util.c`). Same shape as a check positioned where nothing can contradict it, one layer down | 2026-09-22 |
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
| The guarded build starts on **64K-ROM Macintoshes**, the 128K among them — OPEN_ITEMS.md listed "the 128K and the true 512K" under one status | **Only on the 512K.** One volume, one ROM, one System, two machines: the `rom64k` `dist/` opens Standard File on a 512K and bombs `ID = 03` on a 128K. `tools/vmac/memtest` says why — the largest single block a 128K will grant is **63,744 B**, against the **142,152 B** of `CODE` 2 that the Segment Loader has to place before any of the engine runs. The claim was never measured on a 128K; it was one machine's result carrying a second machine's name, and RAM was the variable nobody had changed. **Cost: MANUAL_TESTS.md §7 spent a section asking somebody with the hardware to try either machine**, and half of that instruction could not have worked — the expensive kind of wrong, because it spends a stranger's afternoon rather than ours (FORMATS.md, *A Macintosh 128K*) | 2026-09-01 |
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
| AppleLink `.pkg` has no reference implementation anywhere reachable | the SpaceSaver image has had one all along: `Extensions:Aladdin:Translators:PKG Expand Translator`, whose `Name` resource is `AppleLinkPKG` and whose `Othe` resource is 20 KB of 68k with Aladdin's usual module preamble | 2026-08-22 |
| AppleLink `.pkg` cannot be sniffed without inventing a magic number | true of magic numbers, false of sniffing: Aladdin's own recogniser reads three whitespace-delimited TOKENS, and `macextract sniff` now does the same at 0 false positives across 928 fixtures | 2026-08-23 |
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
and copying it is what rule #1 asks for.

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
non-hierarchical `OpenDF` beside it"; wrong, they are broken identically.
**Cost:** the true cause of the M10 saga is still unknown and every conclusion
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

### Corrected figures and superseded write-ups

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

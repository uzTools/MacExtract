# BLOCKERS.md

## Status

**No open blocker** at v0.44.0. The last one — the application bombing on
Mac OS 9.2 on every DiskDoubler archive and on SuperDisk! — was an
`UncOptions` field the shell never assigned (DECISIONS.md 2026-09-04, *the
field nobody assigned*). The engine and CLI were never affected by anything
in this file.

The sample is **74 fixtures** (`tools/vmac/sample.txt`). Each tier's latest
whole sweep is below; the 2026-10-10 sweeps were each paired with a
`-D UNC_AT_BUDGET` sweep read field by field (`tools/vmac/README.md`, *Why
an entry is refused*): no refusal, first-entry error, late image or failed
keep on any of the 238 runs. Changes since 2026-10-23 were checked against
`run_tiers.py --check`, which moved no tally; the full sweeps were not re-run
(DECISIONS.md 2026-10-25, *the envelopes that left*).

| tier | result |
|---|---|
| System 3.0 / Finder 5.1, 4 MB Mac Plus (Mini vMac, a true 68000) | **74/74**, 2026-10-10, `synth-sqp-clear.pkg` 2026-10-11 |
| System 3.0 / Finder 5.1, **1 MB** — the oldest system, at the RAM floor | **74/74**: the 72 on 2026-10-09, `4alnch11.zip` 2026-10-10, `synth-sqp-clear.pkg` 2026-10-11 |
| System 3.0, **512 KB** Macintosh 512Ke | **72/74**, re-measured whole on 2026-10-23 (`sys30.py --emu mv-512Ke`, first pass; DECISIONS.md 2026-10-23, *the shims that were one function*), as on 2026-10-22, 2026-10-21 and 2026-10-18: two per-entry memory refusals, by name the two `run_tiers.py --shipped` names. With every decoder resident it is 68/72 (2026-10-09); the overlays recovered the other two (FORMATS.md, *Overlays*) |
| System 6.0.8, 4 MB Mac Plus | **74/74**, 2026-10-10, `synth-sqp-clear.pkg` 2026-10-11 |
| System 6.0.8, 4 MB, **the stock System Folder** — every INIT and cdev loaded, AppleShare's `Desktop Mgr` among them (`run.py --keep-inits`); beside the stripped tier, not instead of it, since 2026-10-21 | **74/74**, re-measured whole on 2026-10-22 (`run.py --keep-inits`, first pass); v0.41.0 bombed its first application (*Withdrawn claims*). **At 1 MB the machine does not reach the application**: the System's own stop-sign alert before any grid (2026-10-21), so the 1 MB tier stays stripped |
| System 6.0.8, **1 MB** — the RAM floor | **74/74**, re-measured whole on 2026-10-23 (`run.py --mem 1M`, first pass; DECISIONS.md 2026-10-23, *the shims that were one function*), as on 2026-10-22 (*the runtime the application did not need*) and 2026-10-21 (*the probes that left with the bundle*); no memory-budget refusals remain |
| System 6.0.8, **512 KB** Macintosh 512Ke | **68/74**, re-measured whole on 2026-10-23 (`run.py --emu mv-512Ke --system System6.hfv`, first pass), as on 2026-10-22, 2026-10-21 and 2026-10-18, the same six per-entry refusals by name, as `run_tiers.py --check` predicts. **The model once said 67/72** on budgets 16,888 B stale (*Withdrawn claims*). With every decoder resident, 63/72 (2026-10-09), ten since 2026-10-11 and eleven since 2026-10-17, DERIVED |
| System 7.0.1, 4 MB | **74/74**, re-measured whole on 2026-10-22 (`run.py --system Sys7.img`, first pass) — the only tier with a code-cache flush route: `_HWPriv` called on all 72 of the `UNC_AT_BUDGET` sweep, once per kept image plus the bundle fixup |
| **Macintosh LC 475, real, round 3** (2026-10-13, `main` at f4e87ac, MANUAL_TESTS.md §4–§5) | By eye: Standard File across volumes; the destination dialog; a two-floppy split set in one drive, the first ejected and dimmed, unmounted since (DECISIONS.md 2026-10-14); Cancel; Cmd-. on U.S. and AZERTY layouts; output two folders deep; MacExtract and the archive on two floppies, no swap after Save. `/` in names reached the disk as `/`; a second run gave `fold~1`, `fold~2`, `README~1`, nothing overwritten. Two dropped archives: eleven swaps before the first dialog, the System's and the Finder's (DECISIONS.md 2026-10-14). While a window is held the extraction pauses, as every background process does under cooperative multitasking |
| **Macintosh LC 475, real, round 2** (2026-10-12, `main` at 238feef) | **24/24 archives, 188 files byte-exact in both forks**, graded from Linux over AppleShare: every decoder image on a CPU with a cache, no bomb (MANUAL_TESTS.md §4). A full floppy stopped with *"The disk is full"*, the entry in flight deleted. Without the cache flush: 6 archives, 28 files byte-exact (DECISIONS.md 2026-10-12, *the flush the LC 475 did not need*) |
| **Macintosh LC 475, real** (68LC040, System 7.6.1, 12 MB) — the first silicon | **9/11 on `dist/` v0.39.0**, 2026-10-11, by eye, not bytes. The two zips were a shell defect every tier was blind to, fixed and re-run under emulation only (DECISIONS.md 2026-10-11, *the zip that was a set of one*). **At the declared 400 KB minimum partition**, a StuffIt 5 archive refused one entry *"at least 136K"* short and the rest came out, no bomb; one archive only |
| **Mac OS 9.2.2, real PowerPC, HFS+** (2026-10-14, MANUAL_TESTS.md §3) | By the maintainer: launch, PackIt and StuffIt 5 onto HFS+ byte-exact (data forks), 8-bit names right, a 32-character name cut to 31, output two folders deep. A 2.3 GB entry is refused as one entry, confirmed there (DECISIONS.md 2026-10-14) |
| Mac OS 9.2 (QEMU PowerPC, 68LC040 emulation) | **22/22** on 2026-10-22 (`os9.py --list os9sample.txt --launch`), launch and quit to the Finder on every one, 20 in the sweep and two on re-run after `./ci.sh` deleted the reference build mid-sweep; **22/22 in one sweep** on 2026-10-10, interactive and autotest builds alike |

The heaviest 4 MB allocation is the same to the byte on all three 4 MB
tiers, 44 B under the Linux engine (FORMATS.md, *System 7 tier*).

**Every other tier boots System + Finder alone.** The stock-folder row is
what caught issue #1: `run.py --keep-inits --expect` on `OriginalCM.sit` is
NOGRID on the v0.41.0 shell and PASS on v0.42.0.

**Run off the sample**, none of it committable, each graded against this
engine's Linux output (`run.py --expect`):

- **AppleLink `.pkg`**: all eight real packages byte-exact on all seven Mini
  vMac tiers, 2026-10-10 (FORMATS.md, *Run on a Macintosh*).
- **Self-extracting zip**: the five ZipIt `.sea` specimens on all seven,
  2026-10-10 (`tools/specimens/zipit.tsv`). On System 3.0 at 1440 KB,
  `zipit-1.4.sea`'s last fork is a per-entry `UNC_ERR_SINK` (the Finder's
  `DeskTop` fills the Out volume); it passes at 1600 KB.
- **Private File**: through the password dialog on System 6.0.8 at 4 MB
  and 1 MB (2026-10-09) and on both 512 KB machines (2026-10-10), a wrong
  password refused first each time.

Per-tier history and per-fixture tables are FORMATS.md's (*Real-hardware
verification* and after); re-running is `tools/vmac/README.md`; what no
emulator can settle is MANUAL_TESTS.md.

---

## What is true, and load-bearing

**How the Mac shell is verified.** The autotest build CRC-32s both forks read
back through the real File Manager and paints the aggregate to the
framebuffer; the host decodes a screenshot, compares it with the Linux
output, and reads the Out volume for **names**. Only Mini vMac exercises the
Toolbox glue: the qemu-m68k mock calls the sink directly.

**The fix that unblocked M10 is understood: `ioMisc`.** Explicit, fully
zeroed HFS param blocks (`PBHOpenSync` and siblings) are what ships. Measured
2026-10-13 on the M10-era shell (`014ed25`), 4 fixtures per build: Retro68's
glue fails 0/4, a verbatim copy fails 0/4, the copy with `ioMisc = NULL`
alone passes 4/4 (DECISIONS.md 2026-10-13, *the bug was the footnote*).

**Upstream, filed by the maintainer** (`tools/retro68-hopen-repro/`);
MacExtract is unaffected by all three (its own zeroed param blocks, and
`DropNext` reads `AppParmHandle` itself):

- Retro68's `HOpen`/`HOpenRF`/`HOpenDF` glue leaves `ioMisc` as stack
  garbage and the File Manager writes through it — 524 bytes on System
  6.0.8, 12 on System 7.0.1 (measured 2026-10-13). Filed 2026-10-13 as
  https://github.com/autc04/Retro68/issues/320; **fixed
  upstream 2026-10-14** (multiversal `4c78d24`, Retro68 `afe277e`).
  Toolchains built before that still carry it.
- Four more glue fields, measured 2026-10-15 against `4c78d24` on Systems
  3.0, 6.0.8 and 7.0.1: `GetWDInfo` (`nsvErr`), `SetFInfo` (the wrong
  file's Finder info), `HSetFInfo` (`fnfErr` on HFS), `HOpen` family
  (`ioFVersNum` unset: `fnfErr` on MFS). Filed 2026-10-15 as
  https://github.com/autc04/Retro68/issues/322 (*glue_audit*).
- `GetAppFiles`/`ClrAppFiles` never return for index ≥ 2 (`AppFilePtr`
  never decrements), measured 2026-10-15 on all three Systems; a one-line
  patch. Filed 2026-10-15 as
  https://github.com/autc04/Retro68/issues/323 (`ISSUE-appfiles.md`).

**`HideCursor()` before drawing the grid — confirmed by reproduction**:
without it a pointer dragged through the grid flips one bit of the result
(`0x04000000`, reproduced twice); preconditions in `tools/vmac/README.md`.

**`unar` is wrong about ARC/PAK method 0x0b (Distilled)** — it starts the
window at zero where PAK fills it with spaces — so deark is that method's
oracle (`tools/run_pak.py`). `unar` stays the oracle for 0x0a (Crushed),
which deark lacks; PAK's stored CRC-16 outranks both.

**`unar` does not read ARC 7.x at all**, stopping at the informational item
(method 0x14), so `tools/run_arcplus.py` consults deark and registers
`fixtures/manifests/derived-ARCDOS.arc.json` (TESTING.md).

**`src/fmt_binhex.c` owes macutils nothing since 2026-10-07**: its last rule
is cited to StuffIt's own `HQXEngine` (SDK 5.1.2, `Eng ` 10000), and
`check_provenance.py` fails if a macutils `Source:` survives (DECISIONS.md
2026-10-07, *the engine four layers down*); the same engine family named
Private File, read since 2026-10-09 (*the engine list as a checklist*).

---

## Withdrawn claims

**Kept deliberately, and this is the part of the file to read first.** Twice a
live claim has been re-tested *because* it sat beside an already-withdrawn one,
and one of those was worth 39/44 → 40/44 at the floor target. **Fifty-one**
mechanisms keep finding the next one (recounted 2026-10-11); the first two and
*inputs from outside the corpus* need no insight at all:

- a live claim sitting next to an already-withdrawn one;
- **two files disagreeing** — a cross-file contradiction is a disproof nobody
  has collected yet;
- a limitation written one paragraph from its own remedy;
- **a limitation stated about the environment that is true only of one tool.**
  Read every "cannot be done here" for the name of the tool it is really about;
- **an open item that describes what our OWN binary does.** 2026-08-29: four
  such sentences about mpack and this engine, three false, none ever run — a
  claim about a program on this disk is the cheapest to test.
- **somebody else complaining about the tool you grade yourself by.**
  2026-08-21: a corpus README called `unar` "hit-or-miss" on DiskDoubler Pro —
  a bug report against the oracle.
- **inputs from outside the corpus.** 2026-08-21: nine archives nobody here
  had seen, five failing in the first minute. Needs no insight, just files.
- **what the corpus never does that the claim would allow.** 2026-08-21: 30
  `0x1000` entries fitted a rule drawn from them and 45 in the same fifteen
  files contradicted it. Count the records a rule does NOT cover.
- **a limitation you inherited from the reference rather than measured.**
  2026-08-23: "the algorithm is unknown" was The Unarchiver's sentence about
  Compact Pro's encryption; the algorithm was in an application already in
  `fixtures/`.
- **a correct WORKAROUND with the wrong reason attached.** 2026-09-22:
  `checkdisk.py`'s `hls -a` was said to show dotfiles; it is about the
  INVISIBLE bit, so later walks without dotfiles dropped the flag and one
  reported a present file MISSING. A wrong reason beside a right fix is never
  re-tested and is what gets copied.
- **a deviation from a reference, measured against OUR rendering of it.**
  2026-10-05: "SqueezePlay sets the next free code to 256 where `compress`
  sets 257" — `compress` sets 256 (`de_compress.c`, `free_ent = FIRST - 1`);
  257 is deark's. Open the thing it deviates FROM.
- **a reading that passes being read as a reading that is complete.**
  2026-10-05: `tools/derive_sqp.py` graded 4 of 4 members byte-exact with
  **five fields wrong**, all zero or constant in those files; reading the
  WRITER found them. A grading that cannot fail on a field is not evidence
  about it.
- **a sample of a dispatch table read as the whole table.** 2026-10-05: two
  `GetResource('Eng ', N)` sites were cited; there are fourteen, ids 0–6, and
  the sampled pair was another format's. Count the call sites.
- **a probe whose fixture carries a dimension its verdict throws away.**
  2026-09-22: `walkprobe.py` put the same four names at the root and in a
  folder, then compared leaf NAMES, so **four of eight walks never descend**
  and scored 4/4. Ask what the subject varies that the verdict cannot express.
- **a remedy aimed at a step that had already happened.** 2026-09-22: four
  flush remedies for a saved file missing from the image; the write was out,
  the CATALOG entry was not. Four failed remedies are evidence about the
  diagnosis.
- **a survey built by grepping for one spelling.** 2026-09-22: "every volume
  walk" was found by grepping `hls`; two walks use `hdir`, so "four walks"
  was six of eight. Search for the capability, not one name for it.
- **a check that only runs where the others are silent.** 2026-09-21: deark
  was asked only when `unar` and `macunpack` both declined, so for four weeks
  this file said no second implementation of StuffIt method 6 existed. Ask
  what a check is not run ON.
- **an oracle that never fails.** 2026-09-21: deark PADS a truncated fork to
  its declared length (286 B for 234 present); those zeros went into a
  manifest and failed seven fixtures. Ask what the oracle does with damage.
- **every input a suite grades against, made by one program.** 2026-08-23:
  btoa 5.2.1 only ever wrote LF, so twenty-one cases agreed on a line ending
  none of them chose.
- **a rule proved on one file and applied to the other forty.** 2026-08-30:
  "everything builds at `-Os`, TESTED" was tested on one atypical file. Ask
  what the measurement's subject actually was.
- **a fix whose scope was asserted rather than grepped.** 2026-09-03: "one
  CLI per file now" fixed one site of three; the other two were the next three
  failures. `grep` settles it in a second.
- **a difference you read rather than ran.** 2026-08-27: two checks called
  "the same test, one weaker" compute the same predicate. Run both.
- **a grep that cannot match what the file actually says.** 2026-08-23: a
  stale OPEN_ITEMS sentence was wrapped across lines, so grep missed it and
  the miss hid that the clean-up script had aborted. Collapse wrapping, and
  read the file to confirm an edit landed.
- **an arithmetic model of code you did not open.** 2026-08-24: a saving
  costed from the allocator's documentation; one four-minute instrumented run
  turned ~200 KB into 29 KB. Print a DERIVED number.
- **a claim about "what the code does" that names no line.** 2026-08-24:
  "the error is counted and extraction continues" on a full disk was never
  traced; thirteen extractors refuted it. Make it happen once.
- **a measurement taken in only the roomiest configuration.** 2026-08-24:
  "nothing fails for want of memory" was asked at 597,036 B; the declared
  400 KB MultiFinder partition leaves 130,136 B. Ask which configuration the
  user can make worse.
- **a cross-validation whose output is quantised.** 2026-08-24: `--budget`
  agreed with the Mac to 54 bytes while 91 KB wrong, because `target` halves.
  Ask what resolution an agreement has.
- **a limit nobody has ever measured against.** 2026-08-24: the 4 KB
  call-depth rule was exceeded by 66 % in shipping code. Measure a limit when
  something pushes at it.
- **a gap you filed yourself, in the file that holds gaps.** 2026-08-25:
  "what is missing is a gradeable SPECIMEN" for ARC 7.x's Trimmed; the
  writer's own distribution was one. An OPEN_ITEMS entry needs evidence too.
- **a search that names the wrong tool.** 2026-08-25: specimens of ARC 0x0a/
  0x0b were sought as "written by PKARC or PKPAK", which never wrote them —
  both are PAK's. Check the attribution before hunting the artifact.
- **a scope decision that names a BIGGER version of the problem than the
  one you have.** 2026-08-25: "Zip64 is out of scope" was about >4 GB files;
  an ordinary zip of more than 65,535 entries was silently truncated, and on
  2026-08-27 the per-ENTRY escape at 2 GB was found behind the same name.
- **a limit applied by CLAMPING rather than by refusing.** 2026-08-27:
  three in three days (entry count saturating at 65,535, a Zip64 escape read
  as an offset, a 457-byte name cut to 255 under the wrong filename), all
  exiting 0. Where a constant meets archive data, ask who is told.
- **a harness that ends its runs differently from the harness beside it.**
  2026-08-22: three SpaceSaver runs "measured unchanged" off a killed
  emulator's image while `arcmac.py` shut down properly; again 2026-09-27,
  `run.py` reporting *"66/71 PASS at 4M"* for a 512Ke sweep. Grep for the
  sibling's comment, not the bug.
- **a graded case that has never run on this machine, announcing itself
  in every CI run.** 2026-09-26: `run_crypt.py`'s "garbled ARC skipped",
  read as normal for five weeks; `tools/get_arc.sh` fetched the encoder first
  try and the cases found a retry defect. `./ci.sh`'s `make clean` deletes
  `build/arc` again. Ask what a familiar skip is the ONLY cover for.
- **a coverage figure with a cause attached, where the cause is in the
  source.** 2026-09-26: "PackIt's XOR and DES 0 in 30, because a flipped bit
  fails its header CRC first" — PackIt encrypts the header, and re-run it is
  17 of 30. Only the number ever gets re-measured.
- **a summary that kept the wrong half of a contradiction.** 2026-09-26: a
  condensed provenance cell kept "not yet taken" and dropped "LEFT for their
  standards". Re-read what a condensation deleted.
- **a reproduction whose mechanism is a number, and which does not say to
  check the number.** 2026-09-26: the `UncEntryInfo` recipe's "anywhere in the
  struct" lands in padding; the label *reproducible* kept it standing ten
  days on a tree that no longer showed it.
- **a source citation naming a document that is not on this machine.**
  2026-09-26: `src/unc_crypt.c` cited FIPS-197, not in `reference/`; only
  the half naming code it had could be checked.
- **a citation that points at another file's comment.** 2026-09-26:
  `src/unc_encinfo.c` restated `src/fmt_cpt.c`'s sources, which had changed
  since 2026-09-20. Delegate without restating, as the `fmt_*_probe.c` files do.
- **two figures in one sentence, and only one of them re-measured.**
  2026-09-26: CLAUDE.md's reading went 7.5k → 14k, newly dated, beside a
  stale *"another 15k"* four times low.
- **a claim that no specimen exists, where every search for one was by NAME.**
  2026-09-26: SpaceSaver and AppleLink specimens fell out of one Discmaster
  query on bytes. Extended 2026-10-04: where nothing indexes the bytes, a
  RANGE SCAN — 3,029 zips, 512 bytes each, 1.5 MB against 7.3 GB, seven hits.
- **a routine transcribed faithfully and asked a question it does not
  answer.** 2026-09-27: `PKG Expand Translator`'s @0x2952 shipped 35 days as
  a `.pkg` recogniser; it is the translator API's COMMAND parser and rejects
  all 108 Compact Pro fixtures. Run the sibling's copy on a gradeable format.
- **an item that asks for a SPECIMEN when the question is about the
  FORMAT.** 2026-09-28: StuffIt's add-on module ID was six bytes, and the
  writer was already extracted on this disk. The WRITER is a reference.
- **a comparator that iterates over what it parsed.** 2026-10-05:
  `tools/mutate_now.py --check` printed zero differences and exited 0 on every
  `--delta` run for two weeks because nothing decoded. Ask what a check
  prints when its subject fails to LOAD.
- **a classifier whose "no" branch is a SKIP.** 2026-10-06:
  `unc_uu_line_is_data` skips its false negatives quietly; ask what an old
  test admitted that a narrower one does not.
- **a scan whose corpus has grown since it ran.** 2026-10-06: *"none of the
  47 archives scanned sets bit 5"* (2026-09-27) was false eight days later
  after `sitzip.py --payload 55` added 138 files. Re-run a scan rather than
  re-reading it, before booting an emulator.
- **negative controls derived from a POSITIVE.** 2026-10-06: ten bends of a
  valid AppleLink package all gave `unknown`, yet a file of zeros was claimed
  throughout. Ask what input a negative lane cannot construct.
- **a sum whose terms are kept current at different rates.** 2026-10-09:
  `OVL_SAVED` was re-checked every run and the base never; the sum drifted
  16,888 B and a refusal read as a pass.
- **a negative taken before the subject reached the state the claim is
  about.** 2026-10-10: 45 key-less memory dumps from an installer that had
  never accepted a target.
- **a figure labelled "at least" read as the figure.** 2026-10-11: "short by
  at least 854" — it needed 401,408 B, 180 KB more. Binary-search the figure.
- **a harness that gives every input the same name.** 2026-10-11: every tier
  opened `archive.sit`, so every plain `.zip` failed on the first real
  machine. Ask what the harness holds constant.

Each entry is what was claimed, what disproved it, and what it COST.

| claim | disproved by | withdrawn |
|---|---|---|
| **"Where its length is known, a part's payload fits in the file it is a piece of: nothing a real part can fail"** — `src/fmt_sitseg_probe.c` since 380ab9f, 2026-10-24 | **The same tree's fat-installer reading** (`src/fmt_sitseg_end.c`, db4670a): part 1's data fork also carries the PowerPC tail its 'endD' cuts off, so a set whose later disks hold less than that tail fails on Disk 1; found by reading, no such set here. **Cost: none measured; a day of `main`, no release** (DECISIONS.md 2026-10-25, *the review before the release*) | 2026-10-25 |
| **"What to do about 'Finder info refused' is said once a run"** — `mac/macextract_mac.c` and DECISIONS.md 2026-10-25, *the two that said nothing* | `RunExtract` runs once per envelope layer, so a `.sit.hqx` said it twice; and an archive of 64 entries vetoed whole dropped the advice. `tests/mac_sink_test.c` fails on the second before the fix. **Cost: `main` for an afternoon, no release** (DECISIONS.md 2026-10-25, *the review before the release*) | 2026-10-25 |
| **"`.dl` has one file and no writer: SUMacC's `dl` tools have not been found"** — OPEN_ITEMS.md and DECISIONS.md 2026-10-24, *the format before BinHex*, from one site's listing; and with it **"the sum is compared on 16 bits, as `dl.c` does"** | **4.3BSD's contributed software** (`sumacc.tar.Z` on TUHS, the first search made): `cmd/tohex.c` reproduces `xlispold.dl` byte for byte, and its own readers compare the sum on 32 bits; hexbin's 16 is `verify_crc` masking. **Cost: a 16-bit sum in `main` and its `dist/` for a day, no release; an open item filed on a search nobody had made** (DECISIONS.md 2026-10-25, *the writer that was in 4.3BSD*) | 2026-10-25 |
| **"Bytes 96-97 of a StuffIt segment are zero in every part, and 98-99 a CRC-16/ARC over the payloads of parts 1..n"** — `src/fmt_sitseg_probe.c` since 380ab9f and `src/unc_segment.c` since 7bd87da, both 2026-10-24, from 42 real parts of eight sets | **StuffIt Deluxe 2.0.1's CODE 5** and four sets it cut from files with a resource fork (`tools/vmac/sitopt.py --segment`): 96-97 is the resource fork's running CRC, 98-99 the data fork's; all 42 earlier parts had no resource fork. **Cost: every such set "format not recognized" on `main` and its `dist/` for a morning; no release** (v0.43.0 refused every real set, by `B0 56`) | 2026-10-24 |
| **"A StuffIt segment begins `B0 56 00`"** — `src/fmt_sitseg_probe.c` since M11 (2026-08-08), from XADStuffItSplitParser.m, and TESTING.md's "no `B0 56 00` header anywhere" | **The first sets StuffIt itself cut**, 2026-10-24: `41 A7`, `35 63`, `52 0C`, `93 E1`, `D3 36` — a per-set value. Every `B0 56` part here was `tools/synth_sitsplit.py`'s, graded by `unar`, which requires the same constant. **Cost: every StuffIt-written set "format not recognized" in every release since M11; the LC 475's split-set test (`Palette.sit`) ran on a synthetic one** (DECISIONS.md 2026-10-24, *the magic StuffIt never wrote*) | 2026-10-24 |
| **"A menu item without a Command key is not selectable on either guest"** — tools/vmac/README.md, *What the pointer cannot select*, from 2026-09-27 | **StuffIt Deluxe 7.0.3 on the Mac OS 9.2 guest, 2026-10-23**: a held press and one 24 px step selected `Translate ▸ Expand…`, twice (`as703.py --set boxes`). DropStuff's failure stays measured, not reduced. **Cost: `tools/aesit/` and three boots (2026-10-06) built partly for a keyless item; "the Deluxe application" in two cannot-see lists for weeks** | 2026-10-23 |
| **"The engine's own ceiling"**: `JPEG Lossy` images over 8,192 pixels high refused as `UNC_ERR_TOOLARGE` — `src/sit_ccube.c`, since 2026-10-02, no reason given | **StuffIt Deluxe 2.0.1 restores a 16 x 8,208 document** and this engine, cap lifted, matches it byte for byte; the width cap stays (it keeps `w * h * channels` in 32 bits). **Cost: a 394 KB file StuffIt extracts refused as past 32-bit reach** — a declared ceiling nobody questioned | 2026-10-15 |
| **"Cmd-. does nothing on a French (AZERTY) keyboard"** — OPEN_ITEMS.md, *What the LC 475 found*, from 2026-10-11, with a *hypothesis* | **The maintainer, 2026-10-14**: Cmd-Shift-period, a period on AZERTY, cancels; the first try had no Shift. **Cost: three days open, a technote queued; no code written** | 2026-10-14 |
| **"Retro68's `OpenDF` and `HOpenDF` return `paramErr` on System 6 and do not fall back: a bug"** — ISSUE.md's headline since 2026-08-01 | **Apple's documented contract**: Technote FL 1041 says retry with `HOpen` on `paramErr`, and Retro68 #53 (closed 2018) settled it. The same note requires `ioMisc` = 0, the real bug (DECISIONS.md 2026-10-13, *the bug was the footnote*). **Cost: two and a half months of a report that would have been closed as a duplicate, the real defect in its last paragraph** | 2026-10-13 |
| **"The 16-colour icons are a hard limit: nothing here can display them"** — MANUAL_TESTS.md §3 and DECISIONS.md 2026-08-24, *the icon*, "measured 2026-08-27" | **Mini vMac's own `-m II -depth 2`**, from the source and ROMs already here, drew `icl4` on 2026-10-11 (`tools/vmac/colouricon.py`). **Cost: six weeks filed as needing hardware** — a measurement of two tools read as one of the machine (DECISIONS.md 2026-10-11, *the icon that did not darken*) | 2026-10-11 |
| **"The Macintosh application opens zip archives"** — README.md's zip row and every release note since zip came in | **The maintainer's LC 475**, 2026-10-11: `Reduce.zip` and `Shrink.zip` refused with *"This archive has more parts"*; the same bytes fail as `archive.zip` and pass as `archive.sit`, the only name any tier used. **Cost: every plain `.zip` failed on a Macintosh from 2026-08-14 (`739c6814`) through v0.39.0** (DECISIONS.md 2026-10-11, *the zip that was a set of one*) | 2026-10-11 |
| **`run_crypt.py`'s *"sit-des by an unimplemented encryptor"* grades the refusal of an encryptor id this engine does not implement** — since 2026-10-02, bent to id 3 | **id 3 is `NewDEx`, implemented that day, and the copy had no resource fork**, so every id was refused alike; with its fork and id 5 it fails when the check is removed. **Cost: nine days with no test that could fail** (DECISIONS.md 2026-10-11, *the constant was a square*) | 2026-10-11 |
| **"A tile row is 7 segments = 21 MCUs = 336 pixels"**, and with it *"`src/sit_ccube.c` decodes `JPEG Lossy` byte-exactly against what 2.0.1 restores"* — FORMATS.md, *What an Optimizer did to the fork*, `src/sit_ccube.c`, `tools/ccube/decode.py`, 2026-09-30 to 2026-10-02, on two 256x256 grey documents | **33 more documents 2.0.1 restored** (`tools/vmac/sitcombo.py`, 2026-10-11): right on 2, **silently wrong on 5** (exit 0, a 512x128 image 134 levels off on average), 26 refused. The row is **(w + 39) / 40 segments** (C3a+0x4366); colour needs CCOD+0xd98's precision. **Cost: v0.36.0 to v0.39.0 wrote garbage for any `JPEG Lossy` entry not 256 wide or not grey, unchecked** — the module stores `ffff` (DECISIONS.md 2026-10-11, *the constant was a square*) | 2026-10-11 |
| **"Height at +4, width at +6"** of the `JPEG Lossy` header — `tools/ccube/decode.py`, 2026-09-30 | **width at +4**: a 400x300 document says `0190 012c`. **Cost: the rewrite got it wrong once and failed every non-square specimen** | 2026-10-11 |
| **"encrypted by StuffIt's "DES" module, which this engine does not implement — a password will not help"** — `cli/main.c`, ed6d5b5, 2026-10-02 | **It fired only when the `'MKey'` was missing** — a forkless `.sit`, measured on 2.0.1's `DES`, `NewDEx` and `DESex` archives. **Cost: nine days telling the owner of a forkless DES archive it was unreadable**; it says so now (`tools/run_sitcombo.py`, *forkless*) | 2026-10-11 |
| **"`Photoshop 1`, `JPEG Lossy` and the five ciphers are graded only on archives this project made; a file from somebody who has one would close it"** — OPEN_ITEMS.md, 2026-10-06/07, after DECISIONS.md 2026-10-02 said the writer's provenance is what matters | **Asking the writer**: 121 archives from 22 boots of 2.0.1 found the five silent failures above, where 196,139 Discmaster StuffIt archives had none to try. **Cost: a search with no possible result where a loop with one was, contradicting its own decision** | 2026-10-11 |
| **"The window starts as zeros, which `ozur` gets from a `calloc` rather than from a comment"** — DECISIONS.md, *Reduce comes in*, and b5c9813, 2026-10-11 | **APPNOTE.TXT 5.2.5 says it**: *"assume that all the data before the start of the output stream is filled with zeros"*. **Cost: none to the engine; a lesson drawn from a gap that did not exist** | 2026-10-11 |
| **"A copy longer than its distance is corrupt, and the CRCs need that rule"** — `src/unc_reduce.c`, FORMATS.md and DECISIONS.md, b5c9813, 2026-10-11 | **The CRCs settle nothing** (no good entry has one; the 3 that do fail either way) and **5.2.5 permits one**, an overlapping copy; the decoder follows the spec. **Cost: a refusal no real file hit, and a unit test asserting it** | 2026-10-11 |
| **`synth-dd-m5.dd` was 14 B from passing System 6.0.8 / 512Ke until Shrink and Reduce went into the codecs image** — reasoned in the session from `run_tiers.py`'s *"short by at least 854"* | **That figure is the first refused allocation, not the need**: the entry needs **401,408 B** against a 221 KB grant (one `--budget` binary search). **Cost: none committed; it was the argument offered for redoing the placement, which stands on its own bytes** | 2026-10-11 |
| **"On no Macintosh: an AppleLink `.pkg`"** — this file's Status, 2026-10-09, and the brief written from it | FORMATS.md, *AppleLink packages → Run on a Macintosh*: all fourteen packages had run on System 6.0.8 at 4 MB and 1 MB on 2026-10-05/06. The sentence read "not in `sample.txt`" as "on no Macintosh". **Cost: one task item re-establishing it**, then extended to all seven tiers (Status) | 2026-10-10 |
| **"The 3.5.1 application does not launch here"**, and so *"nothing in this project has ever launched a StuffIt Deluxe application"* — this file's 2026-09-28 entry on `sitcrypt.py`, DECISIONS.md that day, `tools/vmac/README.md`, and the docstrings of `sitcrypt.py` and `sitopt.py` | **It launches by a double-click**, and did that day (`specimens/sitopt/map351/`, `sitopt.launch351`'s own comment); the failures were ⌘O. Driven so on 2026-10-10 (`tools/vmac/sitenc351.py`): 3.5.1 cannot use an Encryptor module (FORMATS.md, *Where an archive names the module*). **Cost: twelve days of "4 replaced the modules" as a load-bearing hypothesis, and an open "cannot see" in `sitopt.py`**; the correction was a comment 50 lines below the docstring (*a limitation written one paragraph from its own remedy*) | 2026-10-10 |
| **"The Shortcut updater's archive key is folded only when extraction starts"**, and its picker *"a folder navigator whose Open only descends"* — DECISIONS.md 2026-10-09, OPEN_ITEMS.md, `tools/sit_mkey_oracle.py`; labelled a hypothesis | **The picker asked where the installed Shortcut is** (Standard File filtered on `cdev`/`Cut!`, empty); a 373-byte stand-in gets past it, and the key is in memory **before any file is written** (DECISIONS.md 2026-10-10, *the installer's own key*). **Cost: a day, and the next attempt aimed at the wrong thing** | 2026-10-10 |
| **"No tier moves: the cost is under the narrowest margin, 16,490 B"** — this file's Status, ten times from 2026-09-26 to 2026-10-09, `run_tiers.py --check` agreeing each time | **The System 6.0.8 / 512 KB sweep of 2026-10-09: 66/72 where the model said 67**, `a2ps.V4.3.tar.Z` refused 4,142 B short. `OVL_SAVED` had risen 117,040 → 134,032 while the bases were never re-taken; re-taken, all three came back **16,888 B lower** and the model reproduces every tier by name. **Cost: one fixture refused at 512 KB for up to two weeks with every check green, and ten tier arguments on one number**; `TIERS_CONTROL` now fails `--check-saved` (DECISIONS.md 2026-10-09, *the base nobody re-took*) | 2026-10-09 |
| **"Removing the depth limit costs 376 B of resident `CODE`, nearly all of it the re-scanning pop that replaced the two fixed arrays"** — `tools/build_mac.sh`'s eager pair, FORMATS.md and a commit message, the same hour | **202 B was `path_longbuf` being OUTLINED** once `pop` became a second caller; the rest was the walker keeping the path twice. One path written into `long_name` deletes `path_full_add` (152 B): **−68 B of CODE, −64 B resident**, deepest chain 3,386 → 3,310 B. **Cost: the hour; challenged before believed.** Attribute a size with `nm --size-sort`, not an explanation | 2026-10-07 |
| **"Components are pushed and popped by LENGTH, never by re-scanning for a separator"** — `src/unc_internal.h` since M0, the reason `UncPath` had two fixed arrays and `UNC_PATH_MAXDEPTH` existed | **A property, never a reason**: every `/` in the buffer is one the walker wrote, so a backward scan is exact. Arrays and depth limit gone; nesting is bounded by the path string (`tools/vmac/depthtest/`: **250 levels, noErr**). **Cost: seven weeks of a rule, a suite, a unit test, two emulator runs and a Mac verification built on a 24 nobody chose** | 2026-10-07 |
| **"24 levels is the ENGINE's limit and not the destination's, so an entry below it must be refused rather than placed — a host that could hold the real path is why our limit is a failure and an over-long NAME is a notice"** — `include/macextract.h`'s `path_too_deep`, DECISIONS.md 2026-10-07 | `tools/vmac/depthtest/` on System 6.0.8: **250 levels by dirID, noErr** (the probe's cap), 49 by full pathname (`Str255`); HFS took 89 from Linux. **Classic System software has no depth limit; the only limit is the path string, `UNC_NAME_MAX` already.** **Cost: a day's work on an unmeasured premise**, found by a reader's *"depth isn't a limitation of hfs?"* | 2026-10-07 |
| **"`name_truncated` 2 means the WHOLE name is in `UncOptions.long_name`"** — `include/macextract.h`'s contract, and what `cli/main.c` prints as *"the archive's name"* | **An archive 30 deep with 31-character folders fires both limits**, and the engine offered the FLATTENED path as the whole name. `name_full_len` is now 0 ("the format cannot say"), 2 is never reached. **Cost: none yet; found by a question — a differential suite compares what the engine WRITES, not what it SAYS** | 2026-10-07 |
| **"`checkdisk.py` reads the Out volume back — 55/55 byte-exact, both forks, names and FOLDER STRUCTURE included"** — `tools/vmac/README.md`, premise of every name claim on a Macintosh | **Its walk returned `[]` past eight levels**: a correct 24-level volume read as **32 files MISSING ON THE MAC**. The sample nests to 6. **Cost: one misdiagnosis, caught the same hour by hand.** The guard is at 26 and RAISES; `walk(dirs=True)` adds folders | 2026-10-07 |
| **"`unc_path_push` refuses past `UNC_PATH_MAXDEPTH` with NOTHING changed, so a caller that would rather carry on than fail may ignore the result — landing the entries under the parent instead of refusing the archive"** — `src/unc_internal.h`'s contract, repeated in `fmt_now.c` and `fmt_superdisk.c` | **A generated archive 30 deep** (`tools/synth_deep.py`; the corpus nests to 4, FORMATS.md, *How deep anything actually nests*): "under the parent" was true of ONE of five walks. The others pop by a count, so SuperDisk! and Now Compress misfiled **24 of 91 entries**, and DiskDoubler's two containers returned `UNC_ERR_CORRUPT` and **threw away 43 of 91**; only AppleLink's depth-absolute pops complied. **Cost: nothing yet, nothing here nests that deep; the contract invited the `(void)` cast that misfiles** | 2026-10-07 |
| **"No archive on this machine sets bit 5 of StuffIt 5's archive flag byte — 47 scanned — so nothing here can grade it"** — OPEN_ITEMS.md's `fmt_sit5.c` row, `src/fmt_sit5.c` and `tools/derive_sit5crypt.py`, since 2026-09-27 | **`Tutorial Files/Sample Archive.sit`, inside StuffIt Deluxe 5.5's installer**, reads `0x30` with a 204-byte comment: bit 5 marks a COMMENT, its block four bytes, and 100 + 14 + 4 + 204 + 22 = 344 is exactly `firstoffs` (FORMATS.md, *StuffIt 5's archive flag byte, and what bit 5 is*). It reached the cache on 2026-10-04 (`sitzip.py --payload 55`). **Cost: two days filed as needing an emulator, and a morning aimed at WRITING such an archive** (*a scan whose corpus has grown since it ran*; DECISIONS.md 2026-10-06, *the archive that came with the application*) | 2026-10-06 |
| **"The only software that can set bit 5 is StuffIt Deluxe 5.0.1's comment UI, which Mac OS 9.2 refuses to run"** — OPEN_ITEMS.md's route column for `fmt_sit5.c`'s bit 5, since 2026-09-27 | **StuffIt Deluxe 5.5 and 7.0.3 Classic both have `Edit Comment...`** (`MENU` 131 and 132), and both `aete`s declare `comment` and `password`, read by `sitcomment.py --read` with no emulator. 5.5 launches on 9.2 (`sitcomment.py --probe`) but stops at *"has not been properly installed"*. **Cost: nine days filed as blocked on an operating system, and ninety minutes disproving a file-system theory** (DECISIONS.md 2026-10-06, *the comment UI that was two boxes later*) | 2026-10-06 |
| **"Whether `qemu-system-ppc -M mac99` boots Mac OS 8.6 is unmeasured, and the media stopped being the blocker"** — `tools/vmac/README.md` and OPEN_ITEMS.md, 2026-10-06 | **It does not boot, and the media was never the blocker**: blessed, Apple-partitioned and past the ROM's platform test, Mac OS itself stops with `MacOS: "/rtas" not found!`; OpenBIOS has no `/rtas`, which 9.2's `MacRISC` ROM does not need. **Cost: six boots, about an hour**, and it saves fetching two more installs that would fail the same way (DECISIONS.md 2026-10-06, *the platform the ROM would not admit to*) | 2026-10-06 |
| **"Implode would cost ~1.5–2 KB of `CODE`, estimated, not measured, against 12,460 B of headroom at the tightest tier"** — OPEN_ITEMS.md Part 1's Implode row | **The wrong wall**: 12,460 B is a *resident* margin, and an Implode decoder in `ovl_exo` is not resident in what ships; the nearest comparable addition (zip's extra fields, 2026-10-01) cost +2,024 B of image and +0 resident (FORMATS.md, *Three configurations, one tree*). **Built 2026-10-07: 1,856 B of `CODE`**, shipped build 0 and 0, image +1,924 B (FORMATS.md, *Implode*). **Cost: nothing built on it; a decision priced against a budget it does not draw on** (DECISIONS.md 2026-10-06, *the gate that had never fired*) | 2026-10-06 |
| **"A Macintosh 128K is out for a measured second reason: its largest single block is 63,744 B against 142,152 B of `CODE`"** — OPEN_ITEMS.md Part 1, MANUAL_TESTS.md §6 and this file's 2026-09-01 row | **This project had cut the term on 2026-09-25**: v0.37.0's `CODE` 2 is **48,888 B**, nine `CODE` resources 55,888 B. The verdict holds on another number: 55,888 + 19,052 B A5 = 74,940 B against 78,568 B, then a 155,916 B bundle block — short by **3,628 B**, not a factor of two. **Cost: none on hardware; a wrong price for the per-format-build question** (DECISIONS.md 2026-10-06, *the wall the overlays had already moved*) | 2026-10-06 |
| **"Each pushed range is the smaller half, so the depth cannot pass log2(nsyms); 16 covers 65,536 symbols against this file's 308"** — `src/sit14.c`, `sit14_sort`, 2026-10-03 | **The transcription DEFERS the smaller half instead of recursing**, so pending ranges accumulate: a complete ascending code asks for **20** of 16, and the four dropped silently swap two symbols' codes. Now 7 pending at nsyms=308 over 4,000 vectors, a full stack is an error, `ci.sh` variant 1d proves it. **Cost: a VALID 112-byte entry decoded wrong from its 26th byte for three days**; the two real payloads (9.3 million symbols) never showed it (DECISIONS.md 2026-10-06, *the sort that dropped what it could not hold*) | 2026-10-06 |
| **"`sit14_flush`'s window wrap wants a fork past 256 KB, where the synthetic seed's largest is 17,799 B — the window is sized to the fork, so nothing smaller can wrap it. Reached only by the two real payloads, which no committed suite can touch"** — OPEN_ITEMS.md, *The decoder paths nothing has fuzzed*, and TESTING.md, *Fuzzing*, 2026-10-05 | **458 bytes of stream**: seventeen maximum matches decode to **278,896 B**, so `synth_sit14.py --wrap` wraps and `sit14_flush` goes 55.6 → **100 %** at seeds 11, 12 and 13 (TESTING.md, *Fuzzing*). 17,799 B was what four hand-written shapes happened to decode to. **Cost: the full-window branch shipped 2026-10-03 ungraded and was filed as unreachable** (DECISIONS.md 2026-10-06, *the fork that was cheaper than the file*) | 2026-10-06 |
| **"nothing else restates the scan for a second document in one input: deark's binhex reads ONE document and mpack's handling is a separator inside one part"** — OPEN_ITEMS.md, re-checked 2026-10-05 | **DeHQX 2.0.1 states it in its own documentation** (`fixtures/dehqx-201.hqx`, since M1, by Peter N Lewis, author of the BinHex 4.0 Definition). The same paragraphs document the `---` part separator, all three characters in the BinHex alphabet, which this engine read as data (measured 2026-10-06; `hexbin` reads it). **Cost: a per-entry failure nobody had seen**; the search asked readers, not the programs that posted (DECISIONS.md 2026-10-06, *the separator that was in the alphabet*) | 2026-10-06 |
| **"nothing else implements UUTool's MU layout"** — OPEN_ITEMS.md, *What is still somebody else's and could stop being*, re-checked 2026-10-05 | **UUTool implements it, and is a corpus fixture** (`uu-tool-24.hqx`, since M13): its manual, `DATA` 0 and two encode tables state it, and UUParser 1.72 carries the tables too (`tools/derive_mu.py`, 21 witnesses). **Cost: the engine could not read UUTool's DEFAULT output** — its `HEXA` 129 table encodes no space and the gate required 0x20..0x60 — from M13 to 2026-10-06, green throughout (DECISIONS.md 2026-10-06, *the alphabet nothing here had seen*) | 2026-10-06 |
| **"method 14's decoder, under `fuzz.py`: nothing, except a bigger run"** — OPEN_ITEMS.md, *The decoder paths nothing has fuzzed*, 2026-10-03 | **Ten of its eleven functions are entered at 3,000 cases**, at seeds 11 and 12; the 1,500-case run drew the seed (1 of ~958) too rarely. What was missing was `sit14_lengths_coded`, 0 % at both. **Cost: small, cautious direction** (TESTING.md, *Fuzzing*); a reach figure quoted without its case count | 2026-10-05 |
| **`tools/fuzz_cover.py` "covers every decoder at once, because for a decoder 'was this entered' is what gcov reports"** — its docstring and TESTING.md, *Fuzzing*, since 2026-09-27 | **Two of its twelve rows could not report**: BinHex's regex named `hqx_`/`binhex_` for `bh_` functions and an empty family printed nothing; `^sit\d*_` folded method 14 into "StuffIt classic". **Cost: eight days of BinHex unmeasured (12 of 12 once it could print), and the method 14 row's whole life.** An empty row now says so | 2026-10-05 |
| **"`now_find_delta` wants an archive whose block table carries a delta. Neither corpus archive has one"** — OPEN_ITEMS.md, *The decoder paths nothing has fuzzed*, 2026-09-27 | **`tools/synth_now.py` has written two since M12**, graded by `tools/run_now.py` every `ci.sh`; the gap was one line of `fuzz.py` (DECISIONS.md 2026-10-05). **Cost: eight days unfuzzed**; fixed, Now Compress is 13 of 13 entered at two seeds | 2026-10-05 |
| **`tools/mutate_now.py --check` "decodes the result with `tools/derive_now.py` to show that OUR reader still gets the original bytes out — which is what says the file is well formed and the question is a fair one"** — its docstring, 2026-09-21 | **On every `--delta` run it compared nothing**: `derive_now` had no offset-delta search, so it printed `0 block(s) read the same, 0 changed`, exit 0. **Cost: nothing downstream** (verdicts came from the self-extractor, DECISIONS.md 2026-09-21), **but it kept the item above open.** Compared-nothing now fails | 2026-10-05 |
| **ZipIt's `0x2605` premise — the field is set when and only when the data is MacBinary — "is APPNOTE.TXT 4.6.4's word and nothing this machine can check"** — OPEN_ITEMS.md, 2026-10-01 | **Nine archives ZipIt wrote**: all 16 `0x2605` entries decode to MacBinary, none of the 86 `0x2705` do, type and creator agree in all 16 (FORMATS.md, *ZipIt's own archives*). **Cost: three days of a field read on faith** | 2026-10-04 |
| **"ZipIt was shareware and its archives are plain `.zip`: invisible to a search by name"** — OPEN_ITEMS.md, 2026-10-01 | **True of the archives, false of the ARCHIVERS**: Discmaster's `format=zipIt` returns 69 files; and a `Range` scan of 3,029 zips found **seven carrying a ZipIt field for 1.5 MB of traffic**, against 7.3 GB. **Cost: the whole item** | 2026-10-04 |
| **PKZIP 1.x Implode is out of scope because it is "not a Macintosh method: it is PKZIP 1.x's, and the two corpus archives carrying it are PC software"** — OPEN_ITEMS.md, Part 1, after 2026-09-22 | **`Psycho!v1.0ß1.zip`, written by ZipIt in February 1994**: three MacBinary entries, every one Implode (FORMATS.md, *ZipIt's own archives*). **Cost: PRICED 2026-10-07 when the method landed — 1,856 B of `CODE` in a build nothing ships, 1,924 B of `'OVLY'` image, +0 B resident, no tier tally moved** (FORMATS.md, *Implode*); meanwhile the CLI's refusal had asked for this very file. A claim about the corpus read as one about the format | 2026-10-04 |
| **StuffIt 2.x's `DES` and `NewDE` cannot be read here, and the report should say "which nothing implements — no password will open it"** — 2026-10-02, `src/fmt_sit.c` refusing them by name | **Both are decrypted**: the `'MKey'` verifier already PASSED on 2.0.1, so only the fork transform differed; a 32 × 8 sweep found `DES` is standard DES in **CBC** and `NewDE` **StuffItDES in CBC**, both primitives already in `src/unc_crypt.c`. `NewDEx` (3) and `DESex` (64) are the same ciphers as plug-ins. **Cost: a few hours, never released** | 2026-10-02 |
| **A SCRIPT cannot make an encrypted StuffIt 2.0 archive: the menu's setting does not reach a scripted `Stuff`, and STR# 257's `newde` and `des` "name no installed encryptor"** — 2026-10-02, `tools/vmac/README.md` and FORMATS.md, the second half ASSUMED | **Both words work and are built in**: `Stuff … with fast des` / `fast newde` (`sitopt.py --psdes`) wrote method byte 0x82 and **0x12**, 284 and 285 of 286 bytes differing from a plain control. **Cost: a day of OPEN_ITEMS saying it needed the GUI, and a `--psencgui` phase** (still what `PassLock` needs) | 2026-10-02 |
| **An entry StuffIt 2.x password-protected cannot be read, and the engine should say "no password will open it"** — 2026-10-02, `cli/main.c`'s refusal of the first `PassLock` archive | **The module enciphers nothing**: every compressed byte of both forks is IDENTICAL to the unprotected archive (22,097, 286, 473 and 86 bytes), plus sixteen bytes of key material; confirmed four ways on 2026-10-02. The engine extracts it without a password. **Cost: nothing, hours old** — it was heading for a README line calling clear data unrecoverable | 2026-10-02 |
| **`CCOD`+0x3826 applies a round-toward-zero correction in the output stage, and the exact output mysteriously does not want it** — 2026-10-01, FORMATS.md, `src/sit_ccube.c` and `tools/ccube/decode.py`, as *measured and unexplained* | **A second subject** (`sitopt.py --psdoc --drawing grid`) takes the branch on **9,645** bytes: `decode.py --rtz` is wrong on every one and the plain decoder **byte-exact on both subjects**, 0 of 196,608 differing. A misreading of the disassembly. **Cost: two days of a comment inviting a wrong 'fix'**; labelled *unexplained*, so nothing was built on it | 2026-10-02 |
| **`src/unc_crypt.c`'s AES is FIPS-197 as implemented in Gladman's `Crypto/aeskey.c` and `aescrypt.c`** — 2026-08-23, and why OPEN_ITEMS.md's provenance table counted five XADMaster files there | **The code is the standard's**, section by section of FIPS 197 (5.2 Fig. 11, 5.1 Fig. 5, 4.2.1, 5.3.5), and shares none of Gladman's structure. **Cost: an unowed attribution for 34 days through two re-citing passes (2026-09-19, 2026-09-23), and a priced rewrite nobody needed**; re-citing moved nothing — the crypt image byte-identical at 9,800 B, resident `CODE` and A5 at 53,332 B and 18,988 B (DECISIONS.md 2026-09-26, *the AES that was never Gladman's*) | 2026-09-26 |
| **Three XADMaster ciphers in `unc_crypt.c` are replaceable and not yet taken — zip crypt, the WinZip AES derivation, RC4** — OPEN_ITEMS.md's provenance table | **All three left on 2026-09-23 in `5d14d02`** (RFC 3174, RFC 2104, RFC 2898 §5.2, APPNOTE.TXT §6.1, draft-kaukonen-cipher-arcfour-03); the 2026-09-26 condensation kept the false half of a cell that held both. **Cost: three days of a done item on offer, and the same cell newly claiming FIPS 180 and 197 were *fetched*** | 2026-09-26 |
| **Adding a field to `UncEntryInfo` makes two fixtures roughly twenty times slower on the Macintosh** — BLOCKERS.md carried it as *"unexplained, reproducible, and load-bearing for whoever edits `UncEntryInfo`"* from 2026-09-25; a hypothesis, said to depend on the struct's SIZE | **It passes on v0.33.0, six runs**: at `sizeof` **302** against 300, `derived-LHA_Expander_1.0.3.sea` and `derived-Terrainman_2.0__.sea` extract in **5.1 s** at 1 MB and 4 MB, resident control too; autotest `CODE` 114,544 B against 114,428 B. The recipe's *"anywhere in the struct"* can land in padding (`sizeof` stays **300**). The original cause is not established. **Cost: a day, and a warning carried ten days on a tree that no longer showed it** (DECISIONS.md 2026-09-26, *the reproduction that had stopped reproducing*) | 2026-09-26 |
| **PackIt's XOR and DES are reached by 0 of 30 fuzz mutants, because a flipped bit fails its header CRC before a key is derived** — TESTING.md (*Fuzzing*) and OPEN_ITEMS.md since 2026-09-23, with a header-CRC-repairing remedy | **17 of 30** by the same method (`tools/fuzz_reach.py --untargeted`, seed 11, which reproduces `sit-des` 19 and `sit5-rc4` 21). PackIt encrypts the header, so `src/fmt_packit.c` decrypts then checks; only the first, plain entry's CRC stands in front (100 bytes of 890). How the 0 was got is not recoverable. **Cost: a remedy for a problem that does not exist, and two ciphers recorded as unreachable** (DECISIONS.md 2026-09-26, *the guard that was on the other side*) | 2026-09-26 |
| **The 1 MB Mac Plus budget is 647,204 B** — FORMATS.md, *Budget*: 648,100 B measured 2026-08-31 less the UTF-8 fold's 896 B | **The machine says 648,282 B**; the base was three weeks old. The two 512 KB constants had drifted **21,666 B** each; re-taken, `run_tiers.py` reproduces **all three tiers fixture for fixture**. **Cost: a predictor wrong about four fixtures, and half a day with a worse floor figure** (DECISIONS.md 2026-09-22, *the fold, on a Macintosh*) | 2026-09-22 |
| **What would close the `DDAR` `0x20` row is a 1.x or 2.x DiskDoubler, neither of which is reachable from here** — OPEN_ITEMS.md's `fmt_dd.c` row and `docs/formats/diskdoubler-container.md`, *What would close it* | **A 2.x could not have written a `DDAR` record**: `DDExpand 2.03a`'s `BNDL` lists `DD01`, `DDDA`, `DD02`, `DDTM`, `DDSP` and no `DDAR` anywhere in 65,212 bytes; 3.1 adds `DDAR`. DiskDoubler ß05 (1990) writes no archive either. **Cost: nothing, only because no 2.x was available to spend a boot on** (*a search that names the wrong tool*; DECISIONS.md 2026-09-22, *the version that could not have written it*) | 2026-09-22 |
| **The two harnesses that grade Mac output against the oracle manifests are `check_mac_sink.py` and `tools/vmac/run.py`, so a StuffIt 5 fixture with a non-ASCII name would read a correct fold as a defect in both** — TESTING.md, *The Macintosh shell's names*, 2026-09-22 | **`run.py` cannot see a name** (summed CRCs); `checkdisk.py` is the one that fails — three MISSING, three UNEXPECTED on `derived-800saywhat301j.sit` with the fold disabled. **Cost: nothing, by one day** (DECISIONS.md 2026-09-22, *the fold, on a Macintosh*) | 2026-09-22 |
| **A member deark wrote at all has both forks, so a fork with no file on disk is one deark read as EMPTY** — what `make_manifests.py` let the third oracle assert (TESTING.md, *A third oracle*) | **deark writes the resource sidecar and declines the data fork**: `derived-BitMap11.sit`'s `BitMapHelp.index`, method 8, `Unsupported compression method: 8 (MW)`. **Cost: nothing yet; no manifest records a false empty.** Found by `tools/sweep_deark.py` (DECISIONS.md 2026-09-22, *the oracle asked about everything else*) | 2026-09-22 |
| **deark's output is matched by name** — `make_manifests.py` and TESTING.md, the rule that replaced matching by position on 2026-09-21 | **By the name deark WRITES**, separators mangled to `_`, so **every entry in a folder, 500 of them**, was skipped and success reported on the rest. **Cost: the third oracle's coverage, 1,641 forks where 2,075 were available**, for one unmodelled sanitiser (`de_char_to_valid_fn_char`, `reference/deark/src/deark-util.c`) | 2026-09-22 |
| **What is written onto the boot volume after a 300 KB extraction does not reach the image** — `interactive.py`'s `phase_report_utf8` and DECISIONS.md 2026-09-22 (*the fold, on a Macintosh*), labelled *hypothesis, not measured* | **The bytes reach the image; the CATALOG ENTRY does not** (`--utf8-to-boot`: the report's text is on the image, `hls -a` does not list it). Four flush remedies were aimed at a write already done. **Cost: nothing — the floppy workaround is kept** — but it was the tree's only unreduced hypothesis (DECISIONS.md 2026-09-22, *the file that was on the disk and not in the catalog*) | 2026-09-22 |
| **The ArcMac header's own Finder info has bit 0x40 of the high byte set, which is `invisible`** — `arcmac.macbinary`'s docstring since M13, DECISIONS.md 2026-08-16, OPEN_ITEMS.md and `tools/vmac/README.md` on 2026-09-22 | **No reachable ArcMac header has it**: `FINFO` at offset 42 (`macunpack/arc.h`), and across **5 ArcMac files and 11 entries** the flags are **0x2100 on the application and 0x0100 on every document**; `fInvisible` (0x4000) is set nowhere. A reason reconstructed from a symptom. **Cost: nothing in code; it ordered the walk work** (DECISIONS.md 2026-09-22, *the column that was already on the volume*) | 2026-09-22 |
| **Eight forks in damaged nested archives cannot be adjudicated: `unar` declines them, deark PADS them, and our own output cannot grade our own output** (TESTING.md, *A third oracle*; FORMATS.md, *Hardening*) | **The container states its own layout**: all eight are MacBinary, STORED at header offsets, and match byte for byte; `oracle-unadjudicated` falls **15 across 11 → 8 across 4** (7, and one back the same day — the declined-fork row above). **Cost: eight forks ungradeable since 2026-08-08** (DECISIONS.md 2026-09-22, *the container is the oracle*) | 2026-09-22 |
| **What a shape-3 header's byte 2 tracks is where the encoder is in its window** — 41 of the 43 values above 200 in the 1995 archive (`docs/formats/now-compress.md`, *The header*) | **Window position changes it by nothing**: `nowcompress.py --case wpos`, **eight full blocks, two at each quarter of the window, byte 2 = 0 in all eight**; the 1995 correlation is with position in one file. **Cost: none to output; a day as the lead a probe would be built around** (DECISIONS.md 2026-09-21, *the quarter that changed nothing*) | 2026-09-21 |
| **`reference/macutils/macunpack/sit.c` is the only reference implementation the project has for StuffIt method 6** — `src/fmt_sit.c`, FORMATS.md, TESTING.md | **deark implements it, under MIT, on this disk for four weeks** (`reference/deark/modules/stuffit.c`), and agrees on **all 11 method-6 forks here** (written "12" on the day; corrected 2026-09-22 by `tools/derive_sit6.py`). It writes `.adf` resource sidecars and reads Zip, against two claims about it. **Cost: four weeks of a documented blind spot** — deark was offered only forks the others left open — **and macutils kept in `fmt_sit.c` for a 1,028-byte table deark states in 26 bytes** (OPEN_ITEMS.md; DECISIONS.md 2026-09-21, *the oracle that was never asked*) | 2026-09-21 |
| **A shape-3 header's byte 2 is carried ACROSS blocks** — climbing by `((255 - b2) >> 1) + 1` (`docs/formats/now-compress.md`, *The header*) | **Computed from its own block, no lag**: `nowcompress.py --case matchv`, 21 members up a matchability ladder and back, byte 2 255, 127, 127, 63, 63, 63, 31, 31, 15, 15, 8 and **the same eleven in reverse**. **Cost: none to output; three emulator runs, one wasted on an incompressible keystream** (DECISIONS.md 2026-09-21, *the ladder that was walked back down*) | 2026-09-21 |
| **Now Compress's `0d4c 0037` record is a LEADING record 5.0.1 writes in front of every block table**, with two exceptions (`docs/formats/now-compress.md`, *A member's blocks*) | **One fork-boundary record per member, placed by the two fork lengths** — between the forks, at the head if the resource fork is empty, at the tail if the data fork is: **153 of 153 members**. Every member here came off `hcopy -r`, data fork only, so 105 of 107 put it at the head; `nowcompress.py --case forks` confirms all four placements. **Cost: the format's "best open question", and `synth_now.py`'s `build_archive` still writes no boundary record at its two-fork member — a sixth difference from the encoder's archives where TESTING.md lists five** (DECISIONS.md 2026-09-21, *the record that was never leading*) | 2026-09-21 |
| **The window is carried across a stream restart unchanged and the bytes come out right, so nothing here needs a reload** — `docs/formats/now-compress.md`, 2026-09-21 | **A restart reloads the dictionary cache** (the 32,768 bytes ending where the previous stream's FIRST block ended): `bothbig.bin`'s data fork decodes byte-exact that way and with **19,909 wrong bytes** on the running window. Every earlier specimen was one block. **Cost: none to output — `src/fmt_now.c` always reloaded — but `tools/derive_now.py`, written from the note, got 8 of 11 blocks before the fix** | 2026-09-21 |
| **The Mac OS 9.2 tier is 20/20** — BLOCKERS.md's status table and FORMATS.md since 2026-08-27 | **It is 18/20, and the two failures BOMB the application**; the tier was not run while thirty-five commits touched `src/` and `mac/`. **Cost: `dist/` shipped a build that bombs on Mac OS 9 since at least v0.29.0**, and the status table showed every session the false number. The cause is the next row | 2026-09-04 |
| The 12 KB stack is **"verified byte-exact at exactly that size on every tier: 69/69 at 1 MB, 512 KB, System 7 and Mac OS 9"** (FORMATS.md, *Stack*, and the `kStackBump` comment in `mac/macextract_mac.c`) | **Mac OS 9 was not run at that stack size on 2026-08-31**, nor for four days either side; three tiers were verified and a fourth named. The stack is not the OS 9 defect (24 KB bombs too). **Cost: four hours treating the stack as a suspect it had been declared innocent of** | 2026-09-04 |
| The System 6.0.8 / 512Ke tier is **"unchanged at 58/69"** after M46, because the flat reserve could not help a machine whose quarter-rule reserve was already under the 32 KB floor | **63/69**: M46's other change, 20,464 B off the STACK, lands on every machine. **Cost: nothing lost (pessimistic), but a sound argument for why a tier could not move stopped it being re-measured for four days** | 2026-09-04 |
| **`7be1ee9` is the first bad commit for the Mac OS 9 crash**, from a `git bisect run` over 35 commits | **Withdrawn the same day by its own retest**: removing any three of four probes, or never executing them, makes the crash vanish — a layout-sensitive symptom makes every commit look guilty. The mechanism was an uninitialised field (next row). **Cost: about ten emulator runs and a retracted report to the maintainer** | 2026-09-04 |
| **The Mac OS 9 bomb is in code the interactive build runs and the autotest build does not** — the event loop, the dialogs, the progress bar, Standard File — and **every channel that could find the crash site perturbs it away**; the one open blocker, and "not yet known" on the v0.30.0 download page | **A field nobody assigned**: `RunExtract` never set `long_name` or `long_name_cap` (added 2026-08-27), and the folder walker of DiskDoubler, SuperDisk! and Now Compress writes through it when non-NULL. Reproduced on the host (`tools/longname-repro/`, ASan) and fixed on the Mac (FORMATS.md, *Mac OS 9.2*). **Cost: two releases (v0.29.0, v0.30.0); the Mini vMac tiers' 69/69 on those formats was luck; ten emulator runs, a retracted bisect, two hypotheses and a tracer build — against a one-minute `grep` of the option fields the shell assigns** (DECISIONS.md 2026-09-04, *the field nobody assigned*) | 2026-09-04 |
| Two folders whose shortened names collide **cannot be told apart** where the archive declares no folder entries, so a merge is what a Macintosh gets — filed under OPEN_ITEMS.md's *Limits of the formats themselves* | **`RepDirMemo` records every directory a run creates**, declared or not; the report never asked. A 32-bit hash answers the only question in 8 bytes against 68: 200 folders in the 1,600 B that held 24. **Cost: for zip, tar and LZH, two archive folders silently became one**, filed where nothing gets re-tested; one zip through the mock sink disproved it (DECISIONS.md 2026-09-03, *a folder is a name too*) | 2026-09-03 |
| A true Macintosh 512K — 64 KB of ROM — **cannot be reached at all** | **It boots**: System 1.1 MFS in ~35 s, and **System 3.0 and Finder 5.1** on an MFS volume this project builds. The ROM cannot read HFS, the only volume tried. **Cost: a day, and nearly the MFS writer** — the entry said "out on the ROM regardless"; the application still bombs there (FORMATS.md, *A true Macintosh 512K*) | 2026-08-31 |
| Two of this application's dependencies are 128K-ROM-and-later — `NGetTrapAddress` in `TrapAvailable`, and every file operation going through HFS parameter blocks | **Neither is**: `tools/vmac/traptest` on a true 512K returns from `NGetTrapAddress` and `PBHGetVInfoSync`, and bombs at **`PBGetCatInfoSync`, `ID = 12`** — the `_HFSDispatch` selector. **Cost: the sentence that made the question look settled**, written from two greps with an emulator running (FORMATS.md, *A true Macintosh 512K*) | 2026-08-31 |
| The guarded build starts on **64K-ROM Macintoshes**, the 128K among them — OPEN_ITEMS.md listed "the 128K and the true 512K" under one status | **Only on the 512K**: the `rom64k` `dist/` bombs `ID = 03` on a 128K, whose largest block is **63,744 B** against the day's **142,152 B** `CODE` 2 (48,888 B since the overlays; the 2026-10-06 row above). **Cost: MANUAL_TESTS.md §6 asked a stranger to try a machine half of which could not work** (FORMATS.md, *A Macintosh 128K*) | 2026-09-01 |
| `-fno-inline-small-functions` is 248 B that has not been taken only because nothing has timed it — the last untimed size flag | **Timed 2026-08-31: −248 B for +448 ticks, +14.1 %** (3,184 → 3,632 on `derived-EmpireBuilderDemo.sit` at 7 MHz; 53.1 s → 60.5 s), against 780 B for +0.82 % from the four kept. **Cost: nothing — the entry closing** (FORMATS.md, *Where the bytes are*) | 2026-08-31 |
| The 32 KB stack can be cut to 20 KB for 12,272 B of budget, at a 1.9x margin over a 10,842 B watermark | **The watermark was not one**: a painted region misses frames that never write themselves — the same run read **10,842 B on a 16 KB stack and 16,266 B on a 20 KB one**, so the cut was REVERTED the same hour. Sampling the stack pointer read **5,200 B, constant**, across four sizes; sweeping down, paint converges on ~5,600 B. Final: a 12 KB stack, **20,464 B** to the engine, byte-exact on all four tiers. **Cost: about two hours of emulator time and a margin figure in FORMATS.md for twenty minutes** (FORMATS.md, *Stack*). A requirement does not move when its container does | 2026-08-31 |
| Joining a segmented set costs far more memory than the same archive whole — `derived-Troi-ClipSave-Plug-in1.1.sit` is 472,137 B straight and asks 64 KB beyond budget joined; `derived-Library_ISBN_Barcoder.sit` asks over a megabyte more | **The join was never the variable**: unsegmented, `Troi-ClipSave` extracts COMPLETELY at 1 MB and still says *"Needs 48K more memory"*; on Linux the join costs **8,192 B** and the inner extraction is **661,173 B**, as whole. The alert reported `gShortBy`, set by StuffIt 5's inverse BWT asking for `numbytes*4` expecting refusal. **Cost: a nonexistent failure in OPEN_ITEMS.md, hiding a real one — every large StuffIt 5 archive reported a memory failure after extracting perfectly** — gated on an errored entry since 2026-08-31 (DECISIONS.md 2026-08-31, *the message that failed a successful extraction*) | 2026-08-31 |
| Everything builds at `-Os`, and that was TESTED rather than assumed | **Tested on ONE file**, `sit_arsenic.c`. On the four a StuffIt run lives in, `-O3` is **−25.4 %** at 7 MHz — 70.4 s → 52.5 s — and per-function `UNC_HOT` gets it for +1,024 B instead of +8,320 B. **Cost: a fifth of every StuffIt, DiskDoubler and PackIt extraction for as long as those files existed** (FORMATS.md, *What -O3 is worth, and where*) | 2026-08-30 |
| Every archive in the 922-fixture corpus fits on a 1 MB Mac Plus again (after 780 B of code came back) | Verified under a LINUX `--budget` cap, never on the machine; on the Mac two of three failed. *(Those failures were themselves withdrawn on 2026-09-18 — next row but one — and this row's claim is TRUE, measured on the machine.)* **Cost: a capability claim published on a proxy** (FORMATS.md, *The Linux budget check under-reads the Mac*) | 2026-08-30 |
| The Linux `--budget` cap under-reads the Mac by 16 KB on one fixture, 33 KB and then 62 KB on another, "the gap is not a constant", and `derived-EasyFind.dmg.sit` does not extract on a 1 MB Mac Plus | **Capped on the machine at 562,000 B**, both fixtures extract with peaks **40 B** above Linux's (561,922 against 561,882; 561,919 against 561,879). The cited refusal was StuffIt 5's expected first refusal; EasyFind's was **`UNC_ERR_SINK`**, a 1,851,907 B entry on a 1,440 KB floppy (`ret` −9, not −3). **Cost: three fixtures declared out of reach for 18 days, a caveat on every `--budget` figure, and "close the gap" ranked above every code change** (FORMATS.md, *The Linux budget check reads the Mac to 40 bytes*; DECISIONS.md 2026-09-18, *the floppy that was full*) | 2026-09-18 |
| The compiler size flags cost no speed — "no capability lost, no speed traded" | **+49 ticks, 1.55 %**, deterministic: `-freorder-blocks-algorithm=simple` carried 26, and `-fno-early-inlining` was **worse on both axes** (8 bytes bigger, 2 ticks slower) and shipped. **Cost: a false claim in a commit message and `mac/CMakeLists.txt`, and a harmful flag for one commit** | 2026-08-30 |
| The application's RESIDENT SIZE — code plus data plus bss — is what costs the engine its budget, so moving big tables (`ss_dict0`, the DES S-boxes, the report pool) out of the A5 world would buy it back | Ballast said only CODE costs: +11,308 B of code moved FreeMem 647,096 -> 635,768, +6,132 B of `.data` nothing. *(Itself withdrawn 2026-09-02, next row: this row's claim was right.)* **Cost: 23,887 B of tables judged free, and a report-pool change measured at ZERO and reverted; three of four ballast runs measured nothing** (`--gc-sections`, an unreferenced `main()`) | 2026-08-30 |
| **Only `CODE` costs the engine; data, globals and resources are free** — measured by ballast 2026-08-30, and the reason `tools/build_mac.sh` watched code alone | **Data costs one for one**: 16,384 B of verified `.data` takes the budget **647,802 B to 631,384 B** — the A5 world lowers the heap's ceiling. **Cost: it displaced the correct claim above, made "put it in tables" standing advice for two weeks, and 32,644 B of A5 grew unwatched**; an A5 ratchet now sits beside the code one (FORMATS.md, *What the application costs the engine*) | 2026-09-02 |
| An advertised capability does not work on the Mac: encrypted StuffIt extracts nothing | **Encryption works; the HARNESS was broken**: `mkboot.py` deleted the boot volume's invisible `Desktop` file under the boot shell (`d3907fc`), bisected with both ends run and isolated in five runs. **Cost: a working feature published as broken, on `main` and here, and a `LoadMKey` hypothesis the evidence contradicted.** The mechanism was not understood when this was written | 2026-08-30 |
| A `git bisect` over 28 commits named `42cfda3` as the first bad commit | **A documentation commit**: the GOOD end was taken on trust from a Mac OS 9 entry while testing System 6. Both ends measured, it found `d3907fc`, 108 commits earlier. **Cost: ~20 minutes of emulator time and a confident wrong answer** | 2026-08-30 |
| The System 3.0 tier's figures were taken "with the FINDER resident", which is why that system beats System 6.0.8 on a 512 KB machine | **Single-tasking Mac OS UNLOADS the Finder**: 122,808 B free from the boot shell against 122,796 B from the Finder — **12 bytes**. The real mechanism is the system heap, 218,208 B free under System 3.0 against 122,808 B. **Cost: the wrong mechanism in seven files and the immutable v0.28.0 tag message** | 2026-08-30 |
| A MIME message written by a Macintosh is waiting on a gradeable specimen somebody else has to send | **mpack's Macintosh port is in `reference/mpack`**: its encoders run on System 6.0.8 and the message passes **18/18**, both forks byte-exact (`tools/vmac/macmime.py`; FORMATS.md, *base64 and MIME*). **Cost: three days as a wait, filed one bullet below its own answer** | 2026-08-29 |
| A MIME part encoded `x-uuencode` inside a multipart is decoded by mpack, and not by this engine | **Wrong in both halves**: munpack writes the uuencoded TEXT out as the file; this engine always decoded it. **Cost: three days waiting, while the real defect — a uu part SHADOWED the rest of its multipart — went unnamed**, fixed the same day (DECISIONS.md 2026-08-29, *a part that hid its message*) | 2026-08-29 |
| `message/partial` is waiting on a specimen this machine does not have, and meanwhile each part decodes on its own into half a file | **mpack writes it** (`mpack -m 10000` cuts 30,000 bytes into four parts, munpack rejoins them), and no part decoded at all — `src/fmt_mime.c` did not contain *partial*. **Cost: three days, and a sentence about our own binary written from the code's shape** | 2026-08-29 |
| The engine's size limits all fail loudly, the zip entry count aside | **Two more were silent**: a **457-byte zip path** extracted as 255 bytes under the wrong name, exit 0; a container over 4 GiB refused as *"not a recognized archive"* (`(uint32_t)st_size` wraps). **Cost: the longest name in 932 fixtures is 120 bytes, so none of the 9,320 variants could reach it** | 2026-08-27 |
| The engine reads any container up to 4 GiB, and past that it fails loudly | **Not a zip written past 2 GB**: a 3.4 GB archive of 23,400 entries **failed 21,352 under `t`** from 0x80015800 — `zipfile` escapes offsets at `ZIP64_LIMIT` (2³¹ − 1) into extra field 0x0001, unread by `fmt_exo.c`. **Cost: the ceiling in FORMATS.md wrong by half for every conservative writer between 2 and 4 GB**; neither `run_ziplarge.py` nor `run_sizelimits.py` could see it | 2026-08-27 |
| A zip with more than 65,535 entries is covered by the Zip64 refusal, which returns cleanly unsupported | **Not refused at all**: a 70,000-entry archive extracted **65,535 entries and exited 0**. **Cost: no fixture was within 65,506 entries of it** (largest zip in 932 is 29), so neither suite nor 9,320 variants could fail | 2026-08-25 |
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
| AppleLink `.pkg` has no reference implementation anywhere reachable | the SpaceSaver image has had one all along: `Extensions:Aladdin:Translators:PKG Expand Translator` (`Name` resource `AppleLinkPKG`, a 20 KB `Othe` of 68k) | 2026-08-22, and **narrowed 2026-09-27**: that translator is a DRIVER calling `GetResource('Eng ', 2)` in `StuffIt Engine™`, so the reference is that 26,362-byte resource (*Corrected figures*) |
| AppleLink `.pkg` cannot be sniffed without inventing a magic number | true of magic numbers, false of sniffing: Aladdin's recogniser reads three whitespace-delimited TOKENS, and `macextract sniff` did the same at 0 false positives across 928 fixtures | 2026-08-23; **this withdrawal itself withdrawn** 2026-09-27 — the routine is the translator API's command parser (*Corrected figures*); **withdrawn a third time, 2026-10-05**: a package is sniffed by its own arithmetic (version byte, eight zero bytes, two counts, a directory whose forks tile the file), at **exactly the 6 of 955 fixtures that ARE packages and no others**, and 10 bent packages refused one test at a time (`src/fmt_sqp_probe.c`) |
| SqueezePlay's LZW deviates from Unix `compress`: it sets the next free code to 256 after a clear where `compress` sets 257, so `src/unc_lzw.c` cannot be reused unchanged | **`compress` sets 256 too** (`reference/macutils/macunpack/de_compress.c`, `free_ent = FIRST - 1`); 257 is deark's rendering, which `unc_lzw.c` follows, differing only in a slot no valid stream names. SqueezePlay reads with `unc_lzw_init(..., 13, 1, ...)`, ARC method 9's configuration. **Cost: none, checked before anything was built — 0 bytes of codec parameter or second path** (DECISIONS.md 2026-10-05, *the deviation that was the reference*) | 2026-10-05 |
| Compact Pro's encryption algorithm is unknown, so an encrypted `.cpt` can only be reported | Compact Pro 1.51's own `CODE` 3: the key at 0x1892, the 64-bit CRC table at 0x408e, the seed at 0x40fe, and the encrypt and decrypt loops at 0x1152 and 0x1f08 — then graded by the application, both ways | 2026-08-23 |
| Compact Pro enables encryption only for a registration whose name ends with `*`, so no copy here can grade the cipher | registering with the code Macintosh Garden publishes (`Registered` / 35427117) shows the Encrypt checkbox, and the application encrypts and decrypts. The `*` test at 0x485e is real but not the only path to that flag | 2026-08-23 |
| StuffIt classic's archive key is XADMaster's loop, and the open question is only whether `unar` 1.10.8 or current XADMaster matches Aladdin | three archives StuffIt Deluxe 3.5.1 wrote, passwords of 8, 9 and 17 characters: the fold count is **ceil(len/8)**, so XADMaster is wrong at 8 and at 17+ and `unar` 1.10.8 at 9+. Neither reference had it, and this engine had shipped XADMaster's | 2026-08-23 |
| Compact Pro corrupts every resource fork it extracts, 48 bytes in | a CORPUS archive extracted by the same copy comes back with 22 bytes changed the same way: the Resource Manager writes the map's live fields back when the Finder draws the icon. Nothing to do with Compact Pro or the cipher; it cost an afternoon | 2026-08-23 |
| The corpus is large enough that some of it must be encrypted, so a decryption suite has fixtures | `lsar -j` over all 903 fixtures: `XADIsEncrypted` is 0 for every entry in every one | 2026-08-23 |
| A multi-block Arsenic entry gets the declared 512 KB block, so shrinking it to its fill returns ~200 KB to the sampled index | instrumenting `ars_bwt_prepare`: the largest block is `cap=352,160 fill=323,384`, waste **28,776 B**; `ars_block_reserve` has sized at `min(outlen, blocksize)` since M9. The index needs 225,528 B at target 512 and 346,836 B at 1024, so 29 KB moves nothing | 2026-08-24 |
| Segmenting the CODE resource keeps ~61 KB out of the launch path and makes startup cheaper | ballast at 7 MHz: 64 KB of data with no relocations costs **nothing measurable**, with 16,384 relocations **1.1 s**; the application has **2,376**, ≈ 0.16 s of an 8.9 s boot | 2026-08-24 |
| Engine call depth is at most 4 KB (CLAUDE.md's own rule) | `m68k -Os -fstack-usage`: `unc_dd_extract -> dd_fork -> dd_ddn` was **6,664 B** and Now Compress **5,632 B**, never tested. Code tables moved to the heap; the deepest chain was then **3,290 B**. The MACHINE was never exceeded — `kStackBump` gave the shell 32 KB | 2026-08-24 |
| A 1 MB Mac Plus leaves the engine 678,392 B, and `--budget 678392` reproduces it | `run.py --mem 1M -D UNC_AT_BUDGET`: `FreeMem()` is 678,956 B less the shell's 80 KB, so **597,036 B** — 91 KB less; there the CLI predicts the Mac's peak to **48 bytes on two fixtures**, at 678,392 it was out by 90,981. **Cost: `ci.sh`'s floor-target run 91 KB too generous for seventeen days** — the budget falls as the application grows, and nothing re-measured it | 2026-08-24 |
| When the destination disk fills, extraction continues and every remaining entry fails the same way, one error each | `run.py --out-kb 800` with a 17-entry archive: **9 files written, ONE error**, `ret` = `UNC_ERR_SINK`; thirteen of fourteen extractors already stop on a sink failure. **Cost: a shell-side `diskFull` flag, a `Progress` coupling and a `PBHGetVInfo` call written and deleted**; the fix was six lines in `fmt_arc.c` and keeping the `OSErr` | 2026-08-24 |
| Only StuffIt 5 ever runs out of memory, so the remaining fixed-size windows recover memory nothing is asking for | measured at ONE budget, 597,036 B. At the declared 400 KB MultiFinder minimum the budget is **130,136 B** (System 7.0.1), and **Now Compress opened NONE of its three fixtures**. **Cost: three window items closed on 2026-08-24, one reopened the same day**; the sweep runs at both budgets (FORMATS.md, *Budget sweep*) | 2026-08-24 |
| SpaceSaver's extension does not install on this machine, so the question is whether `INIT 0` runs at all | a boot that never opens the panel leaves `SpaceSaver Preferences` (`Pref/SMKR`, 10,496 B) **with the INIT patched and unpatched alike**, so its Shift-key gate at INIT 0 @0x2a6c never closed; no `STR# 1001` alert was ever photographed. **Cost: twelve emulator runs and an item aimed at the install, when what never fired is the TRIGGER** | 2026-08-25 |
| ARC methods 0x0a (Crushed) and 0x0b (Distilled) are PKARC's | both are **PAK's**, from NoGate Consulting — 0x0b in PAK v2.0, July 1989. **Cost: the search aimed at two programs that never wrote either, in four files**; the specimens were one fetch each from `cd.textfiles.com` | 2026-08-25 |
| SpaceSaver installs no menu of its own — `--idlenow` deleted `~Magic Menu™` to give it the bar and the menu bar came up empty | it was pressing x=283, Magic Menu's old slot; SpaceSaver's icon is at **x=425**, its menu `STR# 1024`'s, idle compression on throughout. **Cost: an item aimed at whether the extension installs at all** | 2026-08-25 |
| A coordinate in a vmac harness is right if the run completes and the frames look plausible | two runs pressed 140 px off target; three wrong theories, then printing `xdotool getmouselocation` showed a constant defined twice. **Cost: four emulator runs** | 2026-08-25 |
| The reason SpaceSaver never compresses is that no run combined a matching NAME with a menu command | `--magicname` does both: unchanged, with a **400 KB** subject too. It found `INIT 1` patches `_MenuSelect`/`_MenuKey`/`_PBEject` and nothing in the File Manager, so a rename was never a trigger. **Cost: two emulator runs** | 2026-08-25 |
| The Mac OS 9 guest has no usable pointer, so that tier is keyboard-only | `usb-tablet` moves the cursor **0 px** and one huge relative delta saturates at ±63 px per ADB packet; stepped ≤40 px closed-loop it lands within **3 px**, and drove an installer end to end. **Cost: the tier could not be operated, a claim in four files citing one probe whose clicks all fired from a corner** | 2026-08-26 |
| Nothing here can write an encrypted StuffIt 5 archive, because Deluxe 5.0.1 needs a System this machine does not run | **DropStuff 5.0.1** under Mac OS 9.2 writes them: three specimens at 4, 9 and 17 characters, byte-exact (FORMATS.md, *StuffIt 5's RC4*). The Deluxe application does quit at launch on an HFS+ boot volume | 2026-08-26 |
| SpaceSaver's methods 1, 2 and 3 cannot be graded, because nothing reachable writes one | their own `CMod` modules hold a COMPRESSOR at +0x08, and `qemu-m68k` round-trips all three in 3 seconds (`tools/ssmodule/`). **Cost: declined 2026-08-22 while `sdmodule` landed the same technique on 2026-08-25** | 2026-08-25 |
| ARC 7.x's Trimmed is waiting on a gradeable specimen (OPEN_ITEMS.md, filed 2026-08-25) | `ARC712.ZIP`, one GET from links on the ArchiveTeam wiki, holds seven Trimmed members **including the writer**, run under DOSBox. **Cost: none, caught the same day**, one paragraph below a withdrawn claim of the same kind | 2026-08-25 |
| Nothing reachable writes 0x0a/0x0b, so an implementation could not be graded | PAK 2.51 (1990) runs headless under DOSBox and writes both (`/CR`, `/O`), and extracts. **Cost: declined for a year, with two real specimens of 13 members reachable** | 2026-08-25 |
| `unar` is the oracle for every ARC method, so a transcription error cannot survive it | `unar` decodes 0x0b **wrong** on 6 of the 10 members of `derived-INTRECHO.pak` and a 1,800-byte case: XADMaster starts the 8 KB window at zero, PAK fills it with spaces. Transcribing it, and a synthetic round trip, would have shipped the bug | 2026-08-25 |
| SuperDisk!'s block header carries a 16-bit method, and method 9's Huffman region begins after that header | Alysis's own method 9 module under qemu-m68k (`tools/sdmodule/`) reads AT the length word and dispatches on the low byte (CODE 2 @0x6ba, @0x712); a real block says 0x0809. **Cost: method 9 could not have decoded a single real block**, filed as a risk rather than tested | 2026-08-25 |
| A SuperDisk! single-file container is recognised whatever its size | the head was read as a fixed 64 bytes, so any container under 64 B (the floor is 40) was "corrupt"; found by a 60-byte synthetic one | 2026-08-25 |
| Widening the end-of-central-directory scan window is what makes sniffing cheaper | ~6 % of instructions; a POINTER walk is -30 % of an envelope open and `unc_macbinary_probe` ahead of the scan -78 % — 234 of 929 fixtures' worth of work | 2026-08-24 |
| `spacesaver.py` and `sitcrypt.py` end their runs with Special ▸ Shut Down | 123 is **Restart** on System 7, per forty-three of their own screenshots; 139 is Shut Down (`tools/vmac/README.md`). **Cost: nothing measurable** — Restart flushes too | 2026-09-01 |
| The shortfall the Macintosh reports is "round enough to type and never short" | ONE request's shortfall: `synth-dd-m5.dd` at the 512 KB budget reports **928 B** and needs **203,680**. Both front ends now say **at least**. **Cost: a user sent to Get Info for 8K on an entry wanting 200K** — the second defect in that sentence after M46 | 2026-09-01 |
| The eight-byte record at 144 of `derived-Expand_Now_1.0.1.sea` resembles a Now Compress block table by chance, and the next attempt should not trust it | **It is a block table** — the SECOND block's, shape 2, its output starting at 32,768. **Cost: one day, and guidance pointing away from the answer**; a structure matching two independent ways is evidence | 2026-09-21 |
| **OPEN_ITEMS.md's table is the inventory of what is still XADMaster's or macutils', and the licence changes when its last row is gone** | `grep 'Source:.*\(XAD\|macutils\)'` returns 15 files and **8 had no row** (the shared primitives); two more need a second spelling, ten in all. NOTICE named two as already gone. **Cost: the licence question tracked against a count that could reach zero with XADMaster still in the code.** Corrected 2026-09-27: six more live citations lack a `Source:` line, so the strict grep finds 15 of the table's 21 files | 2026-09-26 |
| **`src/unc_internal.h` cites XADStuffItHuffmanHandle.m for the bit-serialized tree and XADPrefixCode.m for the canonical codes** | both left on 2026-09-19 and 2026-09-20 (`docs/formats/serialized-huffman-tree.md`; RFC 1951 §3.2.2 with puff.c), as NOTICE and `unc_huffman.c` say; the header's comments were not touched. **Cost: nothing executable; two passes recorded complete, one fact cited two ways for six days** | 2026-09-26 |
| **CLAUDE.md: BLOCKERS' withdrawn-claims archive "is another 15k"** | it was **~42k tokens** (169,105 characters; 64,654 when 15k was taken on 2026-08-26). **Cost: the sentence was CORRECTED on 2026-09-26 (7.5k → 14k) and its second figure carried through unmeasured**; a reader was told a quarter of the archive's size | 2026-09-26 |
| **CLAUDE.md: BLOCKERS "names the thirty-three smells that keep finding the next one"** | **the list had thirty-five**, two added after the count the same day. **Cost: none — the third time this count was wrong**, so `tools/check_docs.py` now counts the list against both sentences | 2026-09-26 |
| **`src/unc_util.c`'s three CRC check values "are asserted in `tests/unit_util.c`"** | **no such file has ever existed** (`git log --all --diff-filter=A`); the assertions are in `tests/unit_main.c`'s `test_crc` and `tests/unit_formats.c`. **Cost: none to the engine; quoted twice in one hour as evidence re-citing would be free, before anybody ran `ls`** | 2026-09-26 |
| **`src/unc_crypt.c`: "Seven schemes across the five formats that can encrypt an entry"** | the list under it has **eight schemes across six formats**, as FORMATS.md's *Encryption* and PROGRESS.md's M25 say; FORMATS.md and TESTING.md were corrected that day, the source not. **Cost: none measured; it is the file the licence rows are counted from** | 2026-09-26 |
| **No file written by SpaceSaver itself is reachable, so the container cannot be graded; the only route left is a person with a copy of the software** | **142 of them** on developer and shareware CD-ROMs, found by Discmaster's *detections* index for the magic bytes `SIT!DFD3` (296 hits), every method and both header versions; **48 are installed as specimens and 46 of those carry the uncompressed original**, all 46 byte-exact. **Cost: about twenty emulator runs, a MANUAL_TESTS.md section, and five weeks open** — SpaceSaver renames nothing, so no search by name could find one | 2026-09-26 |
| **AppleLink `.pkg`: no specimen has ever reached this project, and one is what the format waits on** | two shipped **beside AppleLink 6.1 on fifteen Apple Developer CDs** — `ALink.PKG` (6,900 B) and `Read First.PKG` (1,373 B). **Cost: seven boots trying to make Aladdin's software read a package written here, and a detect-only decision** | 2026-09-26 |
| **An AppleLink package is probably a transfer manifest naming files that sit beside it** (hypothesis, 2026-08-23, from three measured things) | both packages are **binary containers**: per record two lengths, type, creator, Finder flags, a Pascal name and two dates, then data; `Read First.PKG` holds `TEXT/ttxt` "Antipiracy-Read Me First". **Cost: five weeks of `.pkg` filed as *possibly nothing to decode*** | 2026-09-26 |
| **`macextract sniff` "is exactly as strong as Aladdin's" on `.pkg` — 0 false positives across 928 fixtures** | **neither real package passes it**: `ALink.PKG` sniffs *unknown*, `Read First.PKG` as **Compact Pro segment** (`unc_cptseg_probe` takes byte 0 = 1 and a zero longword at 4). **Cost: a detect-only row never true of a real file, and a false positive in a second format** | 2026-09-26 |
| **`tools/run_spacesaver.py` grades a specimen against the `.orig` beside it** | it looked under `basename[:-3]` while the CLI keeps the whole basename (`cli/main.c`): the first real specimens failed 46 out of 46. **Cost: nothing, only because none had existed; five weeks green by skipping** | 2026-09-26 |
| **`src/fmt_sit.c` "owes XADStuffItParser.m, XADCompressHandle.m and `macunpack/sit.c` nothing at all" since 2026-09-22** (NOTICE, the file's own header and OPEN_ITEMS.md's inventory row, in those words) | it carries `Source: XADStuffItParser.m decryptHandleForEntryWithDictionary` over `sit_fork_crypt`, the encrypted fork's key layout; the third file recorded as shed while still citing. **Cost: five days of NOTICE naming the wrong sources**; nothing executable — graded by StuffIt Deluxe 3.5.1 (FORMATS.md, *Encryption*) | 2026-09-27 |
| **The detect-only signatures' replacements "are in each format's own published description, none of which is on this disk"** (OPEN_ITEMS.md's XADMaster inventory, the `fmt_foreign.c` row) | **deark states eight of the ten** (`modules/arj.c`, `rar_get_fmtver`, `modules/unsupported.c`'s `get_fmt`, PackIt's recogniser), built by `tools/build_deark.sh` every `ci.sh`; the ninth is `bzip2 -c < /dev/null`, the tenth the StuffIt wiki. **Cost: five weeks unclosable, closed in an afternoon** — ask "does anything here READ this format?" (DECISIONS.md 2026-09-27, *the signatures that were already on the disk*) | 2026-09-27 |
| **`src/unc_internal.h`'s XADMaster and macutils content is "the three CRC tables and the MSB-first bit reader"** (OPEN_ITEMS.md's inventory row, added 2026-09-26) | **Five things, across four subjects**: also the MIME reader's `readline.c` rule, `Source: XADDiskDoublerParser.m case 8`, and the LZAH preload. With two re-cited on 2026-09-27 the file was one edit from leaving the table with three live citations. **Cost: none, caught while closing the row**; a shared header collects every subject's citations (DECISIONS.md 2026-09-27, *the tables that said they were generated*) | 2026-09-27 |
| **NOTICE states what this project borrowed and from whom** — it is the licence notice, and the file that has to be right | it named neither `src/fmt_uu.c` (UUTool's MU layout, macutils' mailed-text rules) nor `src/unc_lzdyn.c` (all of `-lh2-`/`-lh3-` from `XADLZHOldHandles.m`); found by `tools/check_provenance.py`'s first run. **Cost: unknown and possibly zero in law**; prose is worst at absence. The inventory is a checked list, NOTICE its only copy (DECISIONS.md 2026-09-27, *the inventory that was kept twice*) | 2026-09-27 |
| **`tools/check_provenance.py` fails when a file in CARRIES sheds its last citation, so a row cannot stay in the inventory after it is empty** (its own docstring, and DECISIONS.md the same day) | **It passed `src/fmt_mime.c` within the hour**: it tested a MENTION, which a shed file keeps. It now tests the `Source:` marker, with a selftest that liveness is a strict subset of mention. **Cost: nothing, caught the same hour**; a check's predicate must be what changes at the event (DECISIONS.md 2026-09-27, *the check that tested the wrong thing*) | 2026-09-27 |
| **`src/fmt_sit.c`'s encrypted-fork layout needs a specimen written to order — StuffIt Deluxe 3.5.1 runs here, so the route is an emulator session** (OPEN_ITEMS.md's route column, written 2026-09-27) | **The specimens were already here**, written 2026-08-23 by `tools/vmac/sitcrypt.py` with plaintext in `made.json`, graded by `tools/run_crypt.py` every run; two one-line perturbations of `sit_fork_crypt` took them from 0 problems to 24. **Cost: a few hours of a route written as harder than it was** (DECISIONS.md 2026-09-27, *the layout Aladdin's own output settled*) | 2026-09-27 |
| **`src/fmt_sit5.c`'s encrypted-header reading "has no specimen either — all 31 corpus archives read 0x10 here and none is encrypted, so the only archives that exercise it are the ones `tools/run_crypt.py` synthesises, which cannot grade it"** | **Three DropStuff 5.0.1 archives sat in `~/.cache/macextract/sit5/specimens/` since 2026-08-26**, named in FORMATS.md: they read 0x90 and grade bit 7, bit 4's 14-byte shift and the MD5-of-MD5 hash at 4, 9 and 17 characters (`tools/derive_sit5crypt.py`); only bit 5 was left. **Cost: a month filed as ungradeable — the third such find on 2026-09-27** (DECISIONS.md 2026-09-27, *the second cache nobody looked in*) | 2026-09-27 |
| **StuffIt Deluxe 5.0.1 will run on a guest whose boot volume is HFS rather than HFS+** — filed 2026-09-27 from the alert's words, *"an update to this software is required for compatibility with the improved Mac OS file system"* | **It will not**: booted from a 1 GB plain-HFS volume (`tools/vmac/mkapmdisk.py`), it raises the identical alert in **all four combinations** of boot and application volume; the trigger is Mac OS 9.2. **Cost: the route filed twice in a day, ninety minutes to disprove**; an error message's noun is a hypothesis (DECISIONS.md 2026-09-27, *the file system was never the problem*) | 2026-09-27 |
| **`tools/fuzz.py` is a "randomized robustness pass across all formats"** (its own docstring, and TESTING.md's summary of it) | **It reaches what the CORPUS has**: `tools/fuzz_cover.py`, 3,000 cases, seed 11 — `src/unc_lzdyn.c` **16 of 16 functions never entered**, nor DiskDoubler 3, 4 and 7, ARC's Crush, three Arsenic helpers; Now Compress's block-table sum blocks random mutation (the gate that hid `now_next_block`'s heap overflow). **Cost: not yet known**; remedy a seed per method (DECISIONS.md 2026-09-27, *the fuzzer that could only reach what the corpus had*) | 2026-09-27 |
| **Giving `fuzz.py`'s Now Compress repair generator a sixth of the cases starved the other formats** — inferred 2026-09-27 from one 3,000-case run, never-entered 132 → 149 | **Per-family reach is that noisy**: at a twentieth the total was 163, and seed 12 against 11 moves StuffIt classic 1 vs 6, ARC 10 vs 6, Compact Pro 1 vs 4. **Cost: a wrong causal sentence in `fuzz.py`, nearly TESTING.md**; the floor was put at five per family, corrected to **thirteen** on 2026-10-05 (*Corrected figures*; DECISIONS.md 2026-09-27, *the delta that was a draw*) | 2026-09-27 |
| **`-lh3-` is graded against LHa itself on six cases, so its decoder is exercised** — TESTING.md and `tools/run_lzh.py` since 2026-08, and the reason `-lh2-`/`-lh3-` were kept (OPEN_ITEMS.md, Part 1) | **The LZSS half had never run**: `lh3_stream()` emits no match, and `lzs_decode_p` was 0 % on the unmutated seed. Now four match cases through LHa, `-lh3-` entries 6 → 10; the encoder's two bugs (block size counts SYMBOLS; longest match 31, not 32) were caught by LHa. **Cost: unknown, in a decoder kept for a licence** (DECISIONS.md 2026-09-27, *the encoder that only wrote literals*) | 2026-09-27 |
| **`src/fmt_lzh.c`'s NUL-ends-the-name rule is XADMaster's alone, because "the document does not mention it and lhasa takes the whole field"** — the file's comment, `docs/formats/lzh-header.md` and OPEN_ITEMS.md, since 2026-09-22 | **lhasa yields the same filename**: it copies the field and then treats it as a C string (`strrchr`, `strdup`, `strlen`/`sprintf`). **Cost: five days of an inventory row with nothing uniquely XADMaster's, and a non-decision put to the maintainer**; compare implementations' OUTPUT (DECISIONS.md 2026-09-27, *the rule both references already followed*) | 2026-09-27 |
| **The AppleLink `.pkg` expander is in `'Eng ' 2` of `StuffIt Engine™`** — 26,362 bytes, from `PKG Expand Translator` @0x334c (DECISIONS.md 2026-09-27, FORMATS.md and OPEN_ITEMS.md) | **`'Eng ' 2` is the StuffIt/PackIt unstuffer**: the call sites are **fourteen**, a 7 × 2 thunk table, none testing `.pkg`; `'Eng ' 1` is Compact Pro. **The real reference is 3.0.7's `AppleLink Package Translator` 3.0.3**, 33,300 bytes with 148 MacsBug symbols; the format is SqueezePlay, graded 4/4 the same day (FORMATS.md, *AppleLink packages*). **Cost: eight days blocked on a reference already in the 3.0.7 installer** (DECISIONS.md 2026-10-05, *the sample that was read as the table*) | 2026-10-05 |
| **Three AppleLink container paths — a resource fork, the stored mode, version 0 and folders — can only be graded against `tools/synth_sqp.py`, because no real package reaches them** — FORMATS.md and OPEN_ITEMS.md, 2026-10-05 | **49 real packages are in the same index**, six reaching every path: Discmaster's `detection=` searches the first 16 bytes, a hex token for version 1 (36 packages), plus 13 by `extension=.pkg&family=unknown`; 20 are not called `.pkg`. They carry **30 members with a resource fork, both stored bits, 14 folders nested four deep, 50 clear codes and a 541,179-byte member**. **Cost: `tools/synth_sqp.py` written for paths real files reach, seven boots on 2026-09-01, a MANUAL_TESTS.md request, and a generator bug (folder type/creator = window rectangle) any real folder would have caught** (DECISIONS.md 2026-10-06, *the lesson that was written down and then not applied*) | 2026-10-06 |
| **"Nobody else states the CR/LF line rule"** — `src/fmt_uu.c`'s header and OPEN_ITEMS.md's mailed-text row, reached from "mpack is LF-only" | **deark states it** (`dbuf_find_line`: CR, LF or CR+LF, an unterminated last line a line), in the file `src/unc_internal.h` already cited; the 2026-09-27 sweep asked deark only the row's other rules. **Cost: nothing but the row**; a negative is about a (reference, fact) pair (DECISIONS.md 2026-10-05, *the negative that was about one rule*) | 2026-10-05 |
| **"This machine has no Mac OS install media"** — OPEN_ITEMS.md's route column for `fmt_sit5.c`'s bit 5, since 2026-09-27, the reason that row was blocked | **The retail Mac OS 8.6 CD is a 304 MB download from the host `MacOS9.img` comes from** (`mac-os-8.6-working-iso`, a bootable 665,600,000-byte HFS volume), beside a 1.65 GB pre-installed 8.6 image and the 8.5 CD (`tools/vmac/README.md`, *Mac OS 8.6 media*). **Cost: nine days filed as needing a person outside this machine, against one query** (DECISIONS.md 2026-10-06, *the media that was one download away*) | 2026-10-06 |
| **"Nothing has seen a StuffIt 2.x archive this project did not make"** — OPEN_ITEMS.md, 2026-10-02 | **Two Giga-ROM CD archives carry a `Text 1`-optimized entry**, methods 8 and **3**, fixtures since 2026-10-06 (FORMATS.md, *Two optimized archives nobody here made*), found by a `Range` scan of **21,767 headers in 16,727 archives**: 7 Optimizer bits, all one module. **Cost: none — the item was honest**; on the way, the probe's flag bits were the PUBLISHED table's, where `0x10` had been measured on 2026-10-02 to be `NewDE` (DECISIONS.md 2026-10-06, *the Optimizer that was in somebody else's corpus*) | 2026-10-06 |
| **"Appendix B lists 'PMa5' twice, so the document cannot name the fourth word and XADMaster is where 'PMa6' comes from"** — `src/fmt_packit.c`, `tools/derive_packit.py` and OPEN_ITEMS.md, since 2026-09-21 | **The document names it**: `reference/notes/packit_unpackit.txt`, the (L)ist section, *"PMa6 - compressed and DES encrypted (PACKIT III)"*, two pages before the appendix. **Cost: nothing measurable**; a document is not one claim (DECISIONS.md 2026-10-05, *the reference implementation was the fixture's payload*) | 2026-10-05 |
| **PackIt's `keytr1` "has no other statement at all"** — OPEN_ITEMS.md, *The licence cannot move*, filed as irreducible, and **"`unar -p` adjudicates" both PackIt ciphers** — TESTING.md, *Decryption* | `keytr1` IS **FIPS 46-3's PC-1**, and `Packit III 1.3`, inside the fixture `packit.pit_.bin`, carries both ciphers and all nine DES tables, run by `tools/pitcrypt/pit_run.c` under `qemu-m68k`. `unar` is XADMaster, the source both were transcribed from, so it **could not fail on a shared mistake**. **Cost: eight days in Part 1, and both ciphers ungraded independently for fourteen months**; three PackIt-encrypted archives grade them every run (DECISIONS.md 2026-10-05, *the reference implementation was the fixture's payload*) | 2026-10-05 |
| **"The uu alphabet is UUTool's two encode tables"** — `src/fmt_uu_priv.h`, `src/fmt_uu_probe.c` and FORMATS.md's *uuencode: three alphabets* table, 2026-10-06 | **Their union is narrower than the `0x20..0x60` range they replaced**: ``` ` ``` (0x60) is the standard spelling of zero since 4.2BSD, so a line with a zero and a value under 27 fitted neither half and was SKIPPED. **Cost: one day in which no BSD or GNU `uuencode` file was recognised, and `-f uuencode` wrote an empty file with exit 0**; `synth_uu.py`'s `binascii.b2a_uu` spells zero as a space (DECISIONS.md 2026-10-06, *the spelling the tables did not have*) | 2026-10-06 |
| **"An empty package names nothing and is indistinguishable from a file of zeros, which is why this is a test and not a tolerance"** — `src/fmt_sqp_probe.c`'s comment on its `n < 1` test, since 2026-10-05 | **`n < 1` keeps nothing out**: 96 bytes of `01 00` and zeros has a count of one, and the tiling test holds with both sides zero, so it sniffed as *AppleLink package* with one 0-byte entry `_`. The name-length bound 1..31 (`AddItems` @0x22ac/@0x22be/@0x2354; 7..29 over 53 real records) refuses it; `sum > 0` would refuse a real empty member. **Cost: one day in which any `10 + 86n`-byte file of zeros was claimed, and ten negative controls that could not find it** (DECISIONS.md 2026-10-06, *the directory of empty records*) | 2026-10-06 |
| **"`EXPECT_BUNDLE` holds the `'OVLY'` bundle's size, so the bundle cannot grow unremarked"** — `tools/check_app_size.py`'s reason for watching it, leaned on by FORMATS.md's *Overlays* | **1,924 B stale for a day, nothing red**: `ovl_exo` grew 29,252 → 31,176 B on 2026-10-07, `EXPECT_BUNDLE` stayed 156,068, *Overlays* quoted 25,860 B where its terms gave 27,784; 1,924 B is inside the 2,048 B tolerance. **Cost: nothing on any machine; three of four quotes of one number disagreed for a day.** A tolerance wider than the change makes a ratchet a measurement (DECISIONS.md 2026-10-08, *the second attempt that had nowhere to go*) | 2026-10-08 |
| **"Per ARCHIVE and not per entry, because a zip has one writer"** — `src/fmt_exo.c`, `tools/synth_implode.py`, FORMATS.md and DECISIONS.md, 2026-10-08, the reason the minimum-match verdict is settled once | **The format is wider than the measurement**: no archive of 1,537 (29,799 bug-capable entries) mixes the readings, but a zip is appendable across PKZIP 1.1. **Cost, on a three-entry archive our encoder wrote: two entries lost where one was unavoidable, both misreported as "file is truncated"**; a failed inherited verdict now costs only its entry (DECISIONS.md 2026-10-08, *the writer a zip is allowed to have twice*; `tools/run_implode.py` lane 4) | 2026-10-08 |
| **"Rescuing that entry means either buffering a fork or a restartable sink"** — DECISIONS.md, *the writer a zip is allowed to have twice*, and the 01df57b commit message, 2026-10-08 | **A third route, never priced**: key the verdict on *version made by*. PKZIP 1.10 under DOSBox keeps others' 0x000a stamps, so it is sound, but 1.01, 1.02 and 1.10 never write a disagreeing combination (0 of 138 Implode entries). **Cost: nothing; no archive in reach needs it** (DECISIONS.md 2026-10-08, *the key that survives and has nothing to separate*) | 2026-10-08 |
| **"The 3 entries between 2,247 and 2,244 are UNEXPLAINED: the sweep's working set was not kept, so which three the C run did not reach cannot be re-derived here"** — FORMATS.md, *Shrink*, *What grades it*, 2026-10-08 | **The working set was in `/tmp`, and there were no three**: transcription and engine agree on all 2,246 distinct entries; the totals counted different entries (two RISC OS zips `zipfile` refuses over `0x4341`, 15 entries; `Thief35.zip`'s 12; one duplicate). **Cost: a day of the grading reading as incomplete** (DECISIONS.md 2026-10-09, *the three entries that were the harness's*) | 2026-10-09 |
| **"A check of the enclosed message's `Content-MD5`, which mpack writes and which disagrees here"** would close both wrong `message/partial` anchors — OPEN_ITEMS.md, 2026-10-11 | **It disagreed on the right anchor too**: our mpack and munpack were built LP64, where `md5.h`'s `UINT4` is 64 bits, so `abc` hashed to `eZncdeja…` instead of RFC 1321's `kAFQmDzS…` and munpack never warned. Fixed, the check works and was declined for its size (OPEN_ITEMS.md, *Out by the brief*). **Cost: a check on that specimen would have refused every good mpack set; six weeks of an oracle pair that could not fail on a digest** (DECISIONS.md 2026-10-11, *the digest our own oracle could not compute*) | 2026-10-11 |

**"The DD reader's structure is right; it is literal VALUES that are wrong."**
Written 2026-09-20 about the two forks of `derived-Terrainman_2.0__.sea`
`tools/derive_dd.py` could not read, on three real measurements that all hold.
Nothing was wrong with the literals: method 10 has a second form in which the
coder's output is the fork's first difference and the fork is its running sum.
Both forks read with it; the corpus is 39 of 39 (docs/formats/diskdoubler-dd.md,
*The second form*). **Cost: method 10's citation of
`XADDiskDoublerDDnHandle.m`, for as long as the two forks stood.** The smell: a
diagnosis that explains the failures and not the successes — checking the
assumed-good matches found 3,213 of 3,380 wrong.

**"A Now Compress back-reference cannot reach further back than the fork has
produced."** Written into `src/fmt_now.c` to size the history from the largest
fork rather than 32 KB, while the same file says seventy lines earlier that the
window spans MEMBERS. Disproved by an archive Now Compress wrote, four members
of 4 to 6 KB, naming offsets of **6,228 and 13,000 bytes against a 6,000-byte
window**. The bound is now the SUM of every fork, capped at 32 KB, and **no
fixture's peak heap changes**; `--case reach` measures a largest offset of
**32,766**, so 32,768 is the encoder's window. **Cost: nothing yet, and only
because no archive in the corpus has a match that crosses a member.** The
smell: an optimisation justified by a sentence another comment in the same file
contradicts.

**DiskDoubler methods 1–5 and 7 "cannot be graded".** Declined per entry
since M12: no fixture uses one, and nothing reachable writes one — the second
half never tested.

- **DiskDoubler 3.7's own Settings dialog offers exactly two software
  methods**, and "Method A (fastest)" writes **method 1**:
  `tools/vmac/diskdoubler.py --make A`, four minutes.
- **Method 7 needed no emulator at all.** The 3.7 distribution disk ships two
  THINK C libraries compressed with it, each carrying its checksum.

**Cost: two methods, and with method 1 the default output of DiskDoubler's own
era.** "No fixture in the corpus" was read as "no specimen exists" (*a
limitation stated about the environment that is true only of one tool*); the
references also covered more than claimed (XADMaster 4 and 5, macutils 3, all
untested; OPEN_ITEMS.md).

**`DDA2` was read as far as the corpus went, and the corpus stopped early.**
None of the six DiskDoubler fixtures holds a file DiskDoubler Pro could not
compress, and the reference raises on it too. **Cost: every DiskDoubler Pro
archive containing a file that would not compress** — five of the nine real
ones tried. Found by inputs from outside the corpus (DECISIONS.md 2026-08-21).

**"SuperDisk!'s compressor does not survive here, only its expander."** The
reason methods 10, 13 and 20 waited on a file. Macintosh Repository carries the
1991 ` SuperDisk!` control panel (`cdev`/`AlyS`), which compressed an
11,136-byte subject to 2,372 bytes on the first run
(`tools/vmac/sdcompress.py --compress`). **Cost: three methods filed as
ungradeable, on a sentence about what survives that nobody had searched for.**
It wrote the single-file container, then unread (DECISIONS.md 2026-08-22,
later).

**"These 8 forks have no second implementation."** **`unar`'s DDn reads one
byte past the fork's declared compressed length**; declare one more and append
a pad byte, and all 33 forks of the two archives match this engine and the Mac
outside the stamped window. `oracle-unadjudicated` fell from 24 forks across 12
fixtures to 16 across 10. **Cost: eight forks carried as "not ground truth"
since M12**, and an OPEN_ITEMS entry sending three sessions after an
implementation already installed. An oracle that refuses one input may accept
another presentation of the same bytes; the bug is a 1,166-byte reproduction in
`tools/xadmaster-ddn-repro/`.

**"Methods 3, 4 and 5 cannot be graded."** Grading a decoder needs a
specimen; grading a reading needs an implementation, and Salient's 1991
`DiskDoubler™ App` runs: forks this project encoded all expand back
(`tools/vmac/ddencode.py --expand`), and 4.1.1 confirms method 5. **Cost: the
last three methods of the format, held behind a rule about oracles while the
oracle was on the disk** (*a limitation written one paragraph from its own
remedy*). Also found: macutils' method 3 has `#define ESC 0x144`, which no byte
equals, so its `#ifdef UNTESTED` path copies input to output.

**"No compressor older than 3.2 is reachable."** Salient's **3.1.2** floppy
is on WinWorld (1991, SHA-1 published), with **a method 2 fork** (`XCMD.h`,
564 → 386 B) and 22 method 7 forks of up to eight chunks. **Cost: one of the
eleven methods, for the life of the project**; when an item says a FILE is
missing, search for the file, not the story.

**The headerless `DDA2` record "is for a file DiskDoubler Pro could not
shrink".** Half a condition: the file must also have **no resource fork**
(`Test Text`, eleven bytes stored, gets a full `0xABCD0054` header for its
332-byte fork); in the corpus, 30 `0x1000` records all fork-less beside 45
stored-data-fork headers. **Cost: two emulator sessions looking for a file that
cannot exist**, and `+87` documented as a resource fork's checksum. Found by
*what the corpus never does that the claim would allow* (DECISIONS.md
2026-08-21, the Symantec release).

**Four `SPLT` parts, two sets.** The corpus held six parts across three, the
third the DiskDoubler Pro self-extractor with a 14,128-byte resource fork.
**Cost: the joiner's resource-fork path tested on 342 bytes with 47 times that
in the same directory**; all three join byte-exact, and the CRC at `+48` is
exact on all six. A number copied forward instead of re-counted.

**"Macintosh Garden has 3.7 and 4.x only."** It also carries
`DiskDoubler_App_3.2` (the same two methods) and `DiskDoubler2.03.sit`
(DDExpand, an expander). **Cost: none yet**; the conclusion rested on an
unchecked fact one page load away.

**63 sampled fixtures.** `tools/vmac/sample.txt` held 63 lines and 59 names,
four REFUSAL cases re-added by M12. **Cost: four emulator runs on every sweep
of every tier since 2026-08-15, and a coverage number 7% higher than the
coverage.** A list of names is not a set until something makes it one.

**macunpack is not a second implementation of method 7.** Built with
`-DUNTESTED` its `dd_lzss` segfaults on the first specimen (offset 6 is a chunk
COUNT, and the bit pointer is never initialised). The grading uses `unar` and
the fork's checksum.

**"It cannot even be sniffed without inventing a magic number, so a user gets
*unknown* rather than a name."** 2026-08-15, surviving the withdrawal above by
a day; it assumed recognition means fixed-offset bytes. **Corrected 2026-09-27:
the routine copied is that translator's COMMAND parser and recognises no file
at all** (*Corrected figures*).
**Cost: a day, and it would have been the life of the project** — a limitation
true only of one TECHNIQUE.

**"AppleLink `.pkg` has no reference implementation and no published layout
anywhere reachable."** Searched 2026-08-15 and true of the internet, not of
this machine: installing StuffIt Deluxe 3.5.1 for SpaceSaver put `PKG Expand
Translator` in `Extensions:Aladdin:Translators` (`Name` `AppleLinkPKG`, a 20 KB
`Othe` of 68k), and the *Translate* menu offers **PKG Expand…**. **Cost:
nothing, because nobody had needed `.pkg`** — the fifth claim of this shape,
after StuffIt method 6, Now Compress's 1995 archive, ArcMac's fork order and
SuperDisk!. (The translator later proved a driver, and the specimens arrived
2026-09-26: the table above and *Corrected figures*.)

**"The trigger is a NAME RULE."** Read off SpaceSaver's settings page
(*"…whose Name begins or ends with: small"*) and repeated in three files; four
clean runs renamed a subject and nothing compressed, while the page's OTHER
rule (`.SIT`, which proved Magic Menu's) fired on the same event. **Cost: five
runs before the flush was fixed and six after it**, and a day of the specimen
looking one keystroke away. A settings page is documentation, not behaviour.

**Three SpaceSaver runs that "measured unchanged" never booted.** Their
enrolled image came from a **killed** `--enroll` run; Mini vMac flushes only on
eject, so the image was torn and the runs photographed the garbage screen.
**Cost: the specimen, for a day, and the whole of the trigger investigation**;
`arcmac.py`'s `shutdown()` had solved it since the ARC specimens (*a harness
that ends its runs differently from the harness beside it*).

**Alysis SuperDisk! "has no reference".** Filed under OPEN_ITEMS.md's
*"rule #1 forbids inventing a format"*: XADMaster lacks it, `unar` and `macunpack`
stop at the envelope, no layout is published. Both corpus archives are
self-extracting, shipping a 2,694-byte `CODE 2` walker, a 982-byte method 11
module and the Disk Expander's full `Cmpr` codec set. **Cost: the only format
in the corpus that a user got *unknown* for, for the whole life of the
project.** A self-extracting archive is never missing its decoder.

**Retro68's `HOpen` glue.** Claimed to return `noErr` without writing back the
refNum, and recorded as M10's root cause; ten cases show it writing the refNum
and agreeing with a hand-filled `PBHOpenSync` (`HOpenDF` and `OpenDF` behave
alike, as Apple documents — corrected 2026-10-13, above). **Cost:** the M10
cause stayed unknown until 2026-10-13 (`ioMisc`), and every conclusion from
that period had to be re-tested — the next three entries.

**Three non-relocatable staging blocks bomb the Memory Manager.** Re-tested
with the glue fixed: two `NewPtr` blocks plus the archive buffer extract a
two-fork file byte-exact. The shared block is kept; its justification was
wrong. **Cost:** none beyond the write-up.

**`derived-RWAsm_Folder.sit` fails at 4 MB.** Does not reproduce: all 38
entries byte-exact at the same 643.2 KB peak; the old harness was never
committed. Closed as not-reproducible. **Cost:** it is why `tools/vmac/` is
committed and fetches its inputs by URL.

**QuickDraw bombs after File Manager activity.** Twelve configurations of
`tools/quickdraw-repro/` all succeed with `MemError() == 0`, logged through the
framebuffer. **Cost:** as stated it meant the shipped interactive build was
broken, and nobody noticed because it was filed under *harness lessons*.
**Filing a hypothesis under "lessons" hides it.**

**The OS 9 boot volume is plain HFS.** `'BD'` was read without checking
`drEmbedSigWord`, which says `'H+'`; the plan built on it was impossible.
**Cost:** a day's plan; the HFS+ runs now prove their volume by mounting the
wrapper.

**Interleaved reads and writes on one volume return zeros.** This justified
reading the whole archive into RAM; `UNC_AT_INTERLEAVE` reads one file three
ways and gets one CRC, at 4 MB and 1 MB. **Cost:** the buffer came out of the
engine's budget; removing it took the sample 39/44 → 40/44.

**Mini vMac's write-back is lazy and partial** — "it can commit one fork of a
file but not the other". Every Out volume read back with `--keep-disks`:
**55/55 byte-exact**, `derived-RWAsm_Folder.sit` alone 38 files and 73 forks.
**Cost: the highest of any of these** — verification was forced through the
framebuffer grid, which cannot carry a name, so a gzip/`.Z` fallback-name
defect sat for weeks until the Mac OS 9 harness read its volume.

**`pkill -9` never flushes; repeated boot+kill corrupts the boot image.**
The sample was read back after exactly that kill; 6 boot-shell cycles leave
the image byte-identical, 5 `--finder` cycles change the hash and still boot.
**Cost:** none; one-image reuse is still avoided because the image DRIFTS.

**The three 1 MB StuffIt 5 refusals each fill a 512 KB block.** This closed
the floor target as needing "a fundamentally different inverse BWT";
instrumenting `numbytes` shows none fills one (FORMATS.md, *Floor target
verification*). **Cost: the largest still outstanding** at the time — a 3×
shortfall where the worst entry needed ~650 KB against ~700 KB free, with the
disproof in DECISIONS.md one file away. The tier reached 44/44 on 2026-08-07
without a new algorithm (DECISIONS.md 2026-08-06 and -07).

**Nine fixtures are ground truth the oracle cannot produce.** Filed as
*structurally undecidable* and *oracle-buggy*, both properties of `unar -k
visible`; with `-k hidden` all nine build and all 774 manifests are unchanged.
**Cost:** nine fixtures outside the suite from 2026-07-23 to 2026-08-08, and
`harvest.py` silently dropping every THINK C-shaped candidate; the remedy was
in TESTING.md one paragraph above. **Check which of your limits are limits of
a flag you chose.**

**There is no oracle for StuffIt method 6.** `macunpack` has decoded it since
1991 and was in `reference/`. **Cost:** one fork unextractable and 22 forks of
other methods unadjudicated, settled within an hour; restated in four status
files.

**Even `unar` fails on the two PKZIP 1.x zips.** True at M8; per-entry
manifests gave 5 of 7 entries ground truth, while `run_diff.py` still skipped
the fixtures on our own "unsupported" output. **Cost:** 10 forks ungraded for a
day, and a skip that could not fail.

**The Macintosh application unwraps nested files automatically.** README.md
said so; the application took one layer off and stopped. **Cost:** every
`.sit.hqx` user opened the result again by hand for the application's whole
life; the autotest grades per layer, and nothing read the README as a
specification.

**No second implementation of Now Compress exists.** The 1995 fixture is
self-extracting; `nowcompress.py --adjudicate` runs its decoder, agreeing on
all four forks, 9.9 MB (bytes 16..127 of resource forks masked). **Cost:** a
day of structural defence. **Twice now the answer to "nothing can grade this"
has been in the repository.**

**Nothing documents ArcMac's fork order, and no oracle reads ArcMac.** One
wiki page (justsolve.archiveteam.org/wiki/ArcMac, 2026-08-16) named
`ARCMAC.DOC`'s *ArcMac File Structure* — fork lengths little-endian, read here
big-endian — and two real archives; `tools/vmac/arcmac.py` measured the order:
**data fork then resource fork**. **Cost:** every ArcMac payload declined and
its fork sizes reported as garbage for a day, by a decoder and unit test wrong
the same way.

**`src/fmt_btoa.c` accepts CR and CRLF line endings.** The code SKIPPED CR, so
a Macintosh's CR-only file ran together into one line. **Cost:** v0.15 shipped
a btoa decoder that could not read a btoa file saved on a Macintosh; all 21
`tools/run_btoa.py` cases came from btoa 5.2.1 on Linux. Four cases now vary
it.

**The `btoa/atob Translator` is reachable only through a hierarchical menu.**
The submenu half stands (`tools/vmac/README.md`); but StuffIt Deluxe 3.5.1's
`aete` declares `SIT!`/`TRAN` and its `SIZE` -1 is high-level-event aware, so
ONE Apple event runs the translator — readable with `hcopy`, no emulator.
**Cost:** three months graded against one encoder, an abandoned `--btoa-drop`
route, and an item naming the wrong obstacle.

- **"SpaceSaver's Huffman builder checks less than the shared one
  does"** — filed 2026-08-27, withdrawn the same day. `ss_a3_build`'s
  `code > (1u << (L + 1))` and `unc_canon_build_ext`'s `space > (1u << l)`
  are one predicate (`code` is exactly twice `space` at every length); run
  side by side over every small table and 20 million random ones: **zero
  disagreements, and 19 million of those tables were rejected**. **Cost:**
  small — an item filed, moved and cited once; the "fix" would have edited a
  decoder graded against Aladdin's compressor to no effect.

- **"The engine calls the progress callback every 8-16 KB."** True of every
  format but one: `src/fmt_now.c` read blocks with raw `unc_read_full`, so
  **Now Compress never called it at all** from M12 (2026-08-15) to
  2026-08-28, through 946 fixtures that grade only bytes. **Cost:** on a Mac
  every Now Compress extraction showed a dialog frozen at 0 % with both Cancel
  routes unreachable, a 9.9 MB entry among them (DECISIONS.md 2026-08-28).
  `tools/run_ticks.py` measures it now, and fails on the pre-fix engine.

- **"The Mac OS 9 run launches the application, extracts and quits."**
  The run sent Return, Return, Cmd-Q; the second Return accepted the
  DESTINATION dialog, so `14-result.png` photographed SFPutFile and Cmd-Q went
  into a modal dialog. Withdrawn 2026-08-28 (DECISIONS.md; the step table is
  `tools/vmac/README.md`'s). **Cost:** nothing to the 20/20, read off the
  volume — but no OS 9 run had ever waited for the result alert or left the
  application. The labels came from the keystrokes, not the screen.

- **"SuperDisk!'s up-directory record is untested."** Withdrawn 2026-08-28:
  `super-disk-utility.hqx` holds two folders with a pop between them, every
  path adjudicated by the archive's own self-extractor and replayed in
  `ci.sh` (`tools/run_superdisk.py`). Only DEPTH is untested. **Cost:**
  nothing; one bullet about two formats, the true half carrying the other.

- **"The Macintosh application does not number a collision the way the
  CLI does."** Filed 2026-08-27, withdrawn 2026-08-28: `BumpName` in
  `mac/macextract_mac.c` numbers `~1`..`~9` off `dupFNErr` since M10
  (`tools/run_macnames.py` fails six assertions without it). True only that
  the shell said nothing on screen, closed 2026-08-29 by the run report
  (FORMATS.md, *Name limits*). **Cost:** nothing yet; its remedy was code
  already there.

- **"9,320 robustness variants clean"** — read as *damaged input is
  handled*. Withdrawn 2026-08-29: the suite requires a truncated archive to
  "terminate quickly with a normal exit code", and **exit 0 is one**. A
  DiskDoubler archive cut to three fifths said "Extraction complete." (DDAR
  ends at EOF; DDA2's end marker was not checked), and a short StuffIt archive
  had its length **clamped to the file**; `unar` calls both broken. **Cost:**
  a user extracting a half-downloaded archive was told the run was complete,
  for both of the formats this project exists for — DiskDoubler since M13 and
  StuffIt since M1. Fixed; `tools/run_truncation.py` now asks the oracle, the
  sweep 2,796 cut archives, none silent. An aggregate that cannot fail on the
  property it never aggregates.

- **"The Mac shell numbers a collision `~1`..`~9`, so two entries whose
  names are the same for 31 characters both come out."** Written 2026-08-28,
  withdrawn 2026-08-29: true for nine; the TENTH returns -1 from
  `begin_entry`, *abort the archive*. **Cost:** live from M10 until
  2026-08-29 — a generated archive of 26 entries produced 10 files on a Mac
  Plus, reported as an archive failure. Numbering goes to `~99`, and an
  unresolvable name fails its own entry (`tools/run_macnames.py`, the crowd
  case). The test used exactly two names.

- **"The two Alysis implementations disagree about where a Huffman
  region's neighbour begins, and only the harness's own encoder reaches
  it."** Written 2026-08-25, withdrawn 2026-08-28: they never disagreed —
  where a coded flag bitmap ends on a 32-bit refill, `sd_huff_end`'s cursor
  was four bytes short. **Cost:** a silent decode defect in SuperDisk!
  methods 2, 4, 6 and 8, about one block in 32, live from 2026-08-20 to
  2026-08-28. The subjects were sized by the harness's own code and missed by
  2 to 5 bits, and the differential harness SKIPPED every synthetic block that
  reached it. `tools/sdhuff.py` now aims the size (`nflags + 5` bits); all
  nine methods agree 12/12 with no skip.

- **"StuffIt Expander's memory partition cannot be measured here — reading
  the application's `SIZE` resource needs an HFS reader this machine does
  not have."** Written 2026-08-15, withdrawn 2026-08-29: `hfsutils` refuses
  only volumes under 800K; padding a copy mounts it, and 4.0.2 asks for
  **512 KB preferred, 384 KB minimum** (FORMATS.md, *Compared with StuffIt
  Expander 4.0.2*). **Cost:** the one row a 1 MB user needs, blank for two
  weeks.

- **"Module 13 runs now: it wanted a 64 KB working buffer and one Toolbox
  trap, `_BlockMove`, which the runner answers."** Written 2026-08-25,
  withdrawn 2026-08-29: so given, it segfaults four for four. 65,536 (@0xa2)
  is a floor; it needs the header's +0x1E, **229,618 B**, which Alysis's
  extension checks (INIT 32 @0x51a2). **Cost:** method 13 "waiting on a
  gradeable specimen" for four days with the manufacturing tool in the tree,
  and two wrong accounts in one FORMATS.md section. A guard says "not below
  this"; a manifest says "this much".

- **"Lenient on `ESC 1`: macutils' `dd_rle` emits nothing for it rather
  than failing."** Withdrawn 2026-08-29: Salient's 1991 expander refuses such
  a fork, and `fmt_dd.c` was **the only one of six call sites** passing
  `strict = 0`. Now 1, all 91 DiskDoubler fixtures byte-exact. **Cost:** a
  fork the only shipped expander rejects was accepted silently; the leniency
  was inherited from a reimplementation, not the vendor.

- **"Five archive formats are still unnamed for want of a reference: zstd,
  lzip, brotli, lrzip and WIM — no implementation or spec for them is in
  `reference/`."** Written 2026-08-26, withdrawn 2026-08-29: deark's
  `modules/unsupported.c` tests `LZIP` at offset 0, in `reference/` since
  2026-08-25 — a module whose purpose is `fmt_foreign.c`'s. **Cost:** three
  days of `.lz` "not recognized" and four formats behind the same sentence.
  Brotli has no magic number (RFC 7932), so cannot be identified at all
  (OPEN_ITEMS.md, part 1).

- **"Apple Archive (`.aar`) is unnamed for want of a reference — missing: an
  implementation or spec in `reference/`."** Written 2026-08-29, withdrawn
  2026-09-01: `libNeoAppleArchive` (MIT, from scratch) is one query away and
  **builds and writes archives on this machine**, so the probe is graded on
  `AA01`, `pbze`, `pbzz` and `pbzb` files it wrote. **Cost:** three days of
  `.aar` "not recognized"; small, a 2020 format.

- **"A generated SuperDisk! record stream could only be graded against the
  same transcription that wrote it."** Written 2026-08-27, withdrawn
  2026-09-01; in OPEN_ITEMS.md and `tools/run_names.py`. The same sentence
  named the second reader: `SD! Utilities.x`'s data fork IS the archive, so
  replacing it hands its own `CODE 2` any stream — a 10-folder one built all
  11 files (FORMATS.md, *Alysis SuperDisk!*). **Cost:** five days open, in two
  files (*a limitation written one paragraph from its own remedy*, in one
  sentence).

- **"Three segmented UI scenarios fail on `main`, and the split is the
  harness: the passes are found by HEADER, the failures are placed by
  NAME."** Written 2026-09-02, widened 2026-09-03, withdrawn the same day:
  `phase_wrapped` and `phase_named` graded against `build/dev/macextract`,
  which **nothing has ever built** (and `./ci.sh`'s `make clean` deletes
  `build`), so `R.sh` raised `FileNotFoundError` before comparing. Guarded,
  all three pass (`zip-named` ~155 s, `split-named` ~134 s, `wrapped` MATCH).
  **Cost:** a day, eight emulator runs at ~5 minutes each, and two commits
  blaming the application while FORMATS.md's *Segmented sets on a real
  emulated Mac Plus* said all three joined. The proposed Linux check could not
  have worked: the sibling search is host code written twice (`cli/main.c`,
  `mac/macextract_mac.c`).

- **"Now Compress's shape-3 main table ends where the code is
  complete: nothing states its length and the trailing absent symbols
  are not sent."** Written and withdrawn 2026-09-21: a **fixed 290 entries**
  (256 literals, 33 match symbols), the tail written as **zeros**. **Cost:**
  four specimens recorded with 271-, 274-, 275- or 349-symbol alphabets, and
  distance classes reaching 131,072 in a 16,000-byte member — most of why
  shape 3 looked undecodable for a day. True of the first four blocks and of
  the DISTANCE table one layer down.

- **"A Now Compress shape-1 match is `length - 2` then the distance,
  one byte each, so it reaches at most 255 back."** Written and withdrawn
  2026-09-21: a **3-bit length and a 13-bit distance**, reaching 8,191.
  **Cost:** nothing yet — no shape-1 match token in six blocks tells the
  readings apart, so a reader from the note would refuse the first fork that
  did. Disproved by shape 2 in the same note (1,340 of 2,162 tokens).

- **"A shape-3 block's bytes 13..15 are 24 bits this note cannot
  account for, zero in every specimen."** Written and withdrawn 2026-09-21:
  **four more code lengths and a count byte** (twenty code-length symbols;
  the count of "extra length" entries past 15). **Cost:** none measured. The
  pointer was an unsourced constant of 85, `4 − 0x59` once bytes 0..1 are one
  size field.

- **"The block table sits at one of two places and the header says
  which", and "an archive over 64 KB widens the record."** Written and
  withdrawn 2026-09-21: records are `[u16 mode][u16 padding][u32 END
  offset]` from +4, always, after a u32 first-block offset. **Cost:** none to
  output; `0d4c 0037` unnamed for a day. A reading that grows a case per
  specimen has its fields in the wrong order.

- **"The word at +2 of a Now Compress file header is a version."**
  Written and withdrawn 2026-09-21: it is the compression SETTING — `0x0010`
  Faster, `0x003f` Smaller, `0x0060`/`0x0160` an archive — shown by Smaller
  forks that came out as shape-1 (`0x001f`) under a `0x003f` header.
  **Cost:** none.

- **"The name deark uses in the errors it attaches to a fork is the
  member's REAL name, before sanitising."** Written and withdrawn
  2026-09-22 (`make_manifests.py`'s `_DEARK_ERR`): deark prints it
  MAKE_PRINTABLE, so `Icon\r` became `Icon__r_` against `Icon_` on disk.
  **382 declined forks across 35 fixtures were keyed to a member that does
  not exist. Cost: nothing, measured** — deark wrote no file for any of them
  (DECISIONS.md 2026-09-22, *the decline that read as a naming gap*).

- **"28 entries across 5 fixtures come out of this engine with mojibake
  names."** Corrected 2026-09-22: **27 across 4** is the encoding case; the
  28th, `.typeAttributes.dict` in `derived-PuzzleGetter_0.8.sit`, has two
  empty forks and no deark file. **Cost:** nothing; one cause credited with 28
  in three files (DECISIONS.md 2026-09-22, *a name an HFS volume can hold*).

- **"283 entries deark names in a way no mangling of ours reproduces."**
  `sweep_deark.py`'s printed summary, written and withdrawn 2026-09-22:
  **225 of the 283 were entries deark named and DECLINED** (StuffIt method 13
  and Arsenic). The sweep now cross-checks **4,556** graded forks rather than
  2,080, agreeing on **2,151** with `DIFFER` still 0 (4,502 that morning, 54
  more once StuffIt 5 was asked in the right encoding, all declines). **Cost:**
  no wrong byte; the number was quoted three times as evidence deark is a weak
  StuffIt oracle. A harness printing the wrong reason for its blind spot is
  worse than one printing none.

- **"`-lh2-`, `-lh3-`: declined per entry ... no archive that uses
  either is reachable here."** `src/fmt_lzh.c`'s header, *What is NOT here,
  and why*, withdrawn 2026-09-22: both are decoded twenty lines below, graded
  by an LHa for UNIX patched to WRITE them (`tools/run_lzh.py`; TESTING.md,
  *LZH's -lh2-*). **Cost:** nothing to output; a masthead contradicting its
  code.

- **"The 49 Tar entries the deark sweep cannot compare are deark
  writing an AppleDouble member as a literal `._NAME` file where `unar`
  merges it."** Written in TESTING.md and two other places, withdrawn
  2026-09-22: deark keeps `./` and its sanitiser turns the slash into `_`, so
  `./READ_ME` becomes `._READ_ME`; none of the 49 carries the AppleDouble
  magic. **Cost: 98 forks of cross-check**, recovered by the alternative name,
  all agreeing — 2,151 agreements of 4,502. Opening one file disproved it.

- **"Russotto's write-up describes the SIT5 container too."**
  OPEN_ITEMS.md's inventory and `src/fmt_sit5.c`, withdrawn 2026-09-22:
  `reference/notes/arsenic_russotto.md` is method 15 only. **Cost: the row sat
  as "none: a parser" while the real description was one link from
  `reference/notes/StuffIt.md`**; fetched, 525 entries of 31 archives read from
  it alone (DECISIONS.md 2026-09-22, *the page the sources list named*).

- **"Where a StuffIt archive records its add-on module ID is not known
  here, and a specimen from an emulator session is the route."**
  OPEN_ITEMS.md and FORMATS.md, written and withdrawn 2026-09-28: five header
  bytes and a method-byte flag, read out of StuffIt Deluxe 2.0.1, already on
  this disk. **Cost: the smallest possible in hours and the largest in
  behaviour** — an Optimizer-flagged fork yields the OPTIMIZED bytes with its
  CRC agreeing and exit 0, so the engine would have written a silently
  different file (DECISIONS.md 2026-09-28, *the six bytes Aladdin's own Get
  Info pane reads*).

- **"2.0.1 checks its serial number, so the optimized specimen needs a
  person with a licensed copy."** In FORMATS.md, OPEN_ITEMS.md, MANUAL_TESTS.md
  §8, BLOCKERS.md and a commit, withdrawn **forty minutes later, by the
  maintainer asking one question**: 2.0.1 is on Macintosh Garden's
  **`/apps/stuffit-deluxe-2`**, which publishes *"A nnnnn"*; `A 12345` worked
  first try. The six codes tried were 3.0.7's and 5.x's, from another page.
  **Cost: three emulator runs, an invented registration wall and a manual-test
  item**. A provenance line is a claim about a URL; open it.

- **"The route to an optimized specimen is an emulator session on the
  machine every harness here already runs — Deluxe 2.0.1 installs on a
  68000 under System 6."** FORMATS.md and OPEN_ITEMS.md, **restored**
  2026-09-28 after the wrong-page withdrawal above: **three optimized archives
  now exist** (`specimens/sitopt/make2/`). The original claim was right.

- **"`sitcrypt.py` drives StuffIt Deluxe 3.5.1."** Its docstring since
  2026-08-23 and `tools/vmac/README.md`, withdrawn 2026-09-28: every dialog in
  its runs is **Magic Menu's** over a Finder menu bar
  (`specimens/sitcrypt/pw8/04-new-dialog.png`). The accompanying "3.5.1 does
  not launch here" was **WITHDRAWN 2026-10-10** (table above: ⌘O; a
  double-click launched it). **Cost: nothing to the encryption work, three
  runs to whoever needed the application**; the giveaway was the menu bar no
  screenshot was read for.

- **"One archive from a reversible Optimizer needs a person outside this
  machine."** MANUAL_TESTS.md §8, filed and deleted 2026-09-28 **because the
  maintainer said it did not**: MacPaint 2.0, unwrapped by this engine, ran
  under Mini vMac and saved a `PNTG/MPNT` document in one boot; stuffed with
  `MacPaint 1` it records **4** in byte 106. **Cost: none, by one message.**
  "Nothing here is one" is about the corpus; ask whether anything here can
  MAKE one.

- **"A `DCMP` would restore the original."** FORMATS.md, OPEN_ITEMS.md,
  TESTING.md and `src/fmt_sit.c`, written and withdrawn 2026-09-28: 2.0.1
  unstuffs its own optimized archive to identical artwork from offset 512,
  a header differing in **486 bytes** and **no resource fork** where the
  original had 501 — as the Addendum says. **Cost: nothing, because the
  BEHAVIOUR was never derived from it**; the refusal rests on the declared
  lengths (*a correct WORKAROUND with the wrong reason attached*).

- **"`*selector` -2 and -3 ask a module for its name and kind."**
  FORMATS.md's ABI table, from CODE 8 on 2026-09-28, withdrawn 2026-09-29 by
  disassembling both halves of `MacPaint 1`: **-2 is the FINISH call** (a
  `DCMP` writes the new header, copies the remnant, deletes its temp file;
  a `COMP` cleans up), and -3 is the only selector answering with a string.
  **Cost: nothing** — the probe used -3, so the -2 row was never exercised; a
  table filled from call sites rather than handlers.

- **"Producing the remnant means a decode-until-input-exhausted mode in
  every method, which `UncEntryInfo` has no way to describe."**
  OPEN_ITEMS.md and FORMATS.md, written 2026-09-28, withdrawn 2026-09-29
  **by the maintainer asking why the decoders had to be touched at all**:
  decode four bytes, read the remnant's own length (2,437), decode that. Still
  true: `UncEntryInfo` cannot say a stored length differs from a declared one.
  **Cost: none in code, but it had sized the work as "not worth opening"**;
  `unar` produces the 2,437-byte remnant byte for byte.

- **"An entry a reversible Optimizer touched cannot be extracted, and
  refusing it is not a judgement call."** FORMATS.md, OPEN_ITEMS.md,
  TESTING.md and `src/fmt_sit.c`, from 2026-09-28, withdrawn 2026-09-29 when
  three of four were implemented: `Sound 1` and `Photoshop 1` delta-code a
  fork and come back EXACTLY under the original CRC, `MacPaint 1` as StuffIt's
  own valid document; only `JPEG Lossy` was right. **Cost: one day of the
  wrong module** — `MacPaint 1`'s `'DCMP'` is 3,010 bytes and needed a
  harness, `Sound 1`'s is **264 bytes**; generalised from a sample of one.

- **"A ZipIt self-extracting archive is not recognised, and a probe
  that could see past the stub is not free: the cost is a backward scan
  for every file the sniffer rejects."** OPEN_ITEMS.md, UNMEASURED from
  2026-10-04, withdrawn 2026-10-05: `unc_zipseg_probe`, one line above,
  already ran that scan (50.0 % of every sniff read) and discarded the answer.
  The fix costs **+0 reads, +0 bytes over 7,601 of them**, one four-byte read
  on a zip. **Cost: five specimens unrecognised for a day**; a price stops an
  item being looked at (DECISIONS.md 2026-10-05, *the scan that was already
  being paid for*).

- **"A spanned-zip part is identified by its end-of-central-directory
  record and its disk number."** `src/fmt_zipseg.c` and FORMATS.md, from
  2026-08-09, withdrawn 2026-10-05: **8,364 files that are not Macintosh
  archives found five being claimed as `UNC_FORMAT_ZIPSEG`** (four `.pyc`, one
  deark object). **Cost: a wrong answer on about one file in 1,700 that is not
  an archive, for fourteen months**, asking the user for parts of a set that
  does not exist; no suite fed the engine non-archives, while the open item
  worried a STRONGER test was too weak.

- **"ZipIt 1.x upper-cased the names it put in the zip and kept the
  Macintosh ones in the field."** FORMATS.md's *ZipIt's own archives* and
  OPEN_ITEMS.md, 2026-10-04, withdrawn 2026-10-05: one of three 1.x writers
  did; it is a **user preference** (ZipIt 1.4's `DOSN`, "dosify filenames").
  **Cost: nothing in code; the only estimate of how likely the item is to
  matter** — both halves of the disproof inside one archive the suite extracts
  every run (DECISIONS.md 2026-10-05, *a leaf is not a path, and a version is
  not a preference*).

- **"Nothing in reach was written by those two versions"** — PKZIP
  1.01/1.02's minimum-match-length bug, filed 2026-10-07 in `src/fmt_exo.c`
  and FORMATS.md, *Implode*, as a negative over 19,107 bug-capable entries.
  **Withdrawn 2026-10-08**: `PKZ101.EXE`, PKZIP 1.01's July 1989
  distribution, has three entries that decode right only under the
  dictionary-size rule (deark `MML bug detection: 1`; `unar`, Info-ZIP
  `unzip` and this engine failed them), and 1,323 of its kind are in the same
  index. **Cost: one day, and that is the whole of it** — the negative named
  its key. The writer signs a self-extractor's `MZ` stub, invisible to every
  `PK\x03\x04` token (DECISIONS.md 2026-10-08, *the stub is the writer's
  signature*; FORMATS.md, *The specimen that carries the bug*).

- **"DiskDoubler 3.7 enforces its header CRC and this engine does not"**
  — DECISIONS.md 2026-10-17, *the window StuffIt kept in the name*, from
  `dd_parse_filehdr` alone. **Withdrawn the same day**:
  `unc_diskdoubler_probe` has checked +82 since M0, and a flipped header byte
  is "format not recognized". **Cost: one task**, and a redundant check
  avoided (DECISIONS.md 2026-10-17, *the window Expander puts back*).
- **"FlCrDat is the local Mac time already, and local is what the sink
  wants, so no offset of either sign enters"** — `src/fmt_exo.c` on
  `0x334d`'s dates, and *the archives' own Finder info*'s "the GMT offsets
  unused", 2026-10-17. **Withdrawn the same day**: the dates are the
  WRITER's local time, and MacZip's UnZip moves them (`AdjustForTZmoveMac`).
  **Cost: every MacZip date** out by writer-zone-minus-reader-zone — 5 h on
  all 22 of `rexnebular_1_0_0.zip`'s for a reader in UTC (DECISIONS.md
  2026-10-17, *dates in the Macintosh's own zone*).
- **"A System 6 or System 3.0 volume has no Desktop Manager"** — the
  shell's comment over `StampCat`, DECISIONS.md 2026-10-17 and 2026-10-18
  (*the icon Expander registers*). **Withdrawn 2026-10-21**: AppleShare's
  1988 `Desktop Mgr` INIT gives System 6 one, and `DTBundle` then reached
  `HOpenResFile`, a System 7 trap; every tier stripped the INIT
  (`mkboot.py`). **Cost: the first bug report on the public repository, two
  days after v0.41.0** — uzTools/MacExtract issue #1, "unimplemented trap" on
  two StuffIt 5 archives; bisected to that INIT, fixed with a working
  directory and `OpenRFPerm`, both in the 128K ROM (DECISIONS.md 2026-10-21,
  *the Desktop Manager System 6 can have*; `run.py --keep-inits` sees it now).
- **"The whole sample under `--keep-inits`, 74/74, says the INIT breaks
  nothing else"** — v0.42.0's fix, DECISIONS.md 2026-10-21. **Withdrawn
  2026-10-22**: its `PBOpenWD` returned the Finder's own working directory and
  `PBCloseWD` closed it. **Cost: v0.42.0, then the current download, on System
  7.0.1 and the stock System 6.0.8 folder** — the second archive of a Finder
  list refused, and entries after a bundled application *"could not be
  created"*; measured with `relaunch.py`, bisected to ba8f2d2. `run.py`
  extracts by dirID, so no sweep took that branch (DECISIONS.md 2026-10-22,
  *the working directory the bundle closed*).

### Corrected figures and superseded write-ups

- **"No zip written by PKZIP 1.01 or 1.02 is in reach, so its
  minimum-match-length bug cannot be graded"** — about to be filed
  2026-10-07. **Not withdrawn: not filed**: a search by MAGIC on the two flag
  combinations where the readings disagree (`detection=504b0304????02000600*`
  and `...04000600*`, 8,943 files) found **800 archives, 19,107 bug-capable
  entries, 19,105 by the specification, 0 by the bug, 2 by neither** (one
  truncated `synchro.zip`, twice). **Cost: nothing.** The conclusion drawn
  from it was withdrawn above: extended 2026-10-08 to all 3,821 candidates —
  29,795 by the specification, still 0 by the bug — a key for the WRITER found
  a specimen (FORMATS.md, *Implode*; TESTING.md, *Searching somebody else's
  index by content*).

- **FORMATS.md's *Three configurations, one tree* table, all six
  figures, for the FOURTH time.** It read 54,340 / 19,052 (eager),
  52,916 / 19,164 (lazy) and 164,324 / 37,916 (control) against a build of
  54,272 / 19,056, 52,848 / 19,136 and 164,408 / 37,928, which
  `tools/build_mac.sh`'s ratchets had right. **Found 2026-10-07. Cost:
  nothing, and that is the problem** — `CODE` + A5 summed the same either way,
  so no check could fail. Re-measurements were appended under the table and
  its cells left; the rows are corrected from the build.

- **"Nothing in the corpus is encrypted."** Written 2026-08-23, re-counted at
  903 and 961 fixtures, always by `lsar -j`'s `XADIsEncrypted`. **Withdrawn
  2026-10-07**: `fixtures/sitcrypt-wild-F7Menus.sit.bin` is encrypted and the
  flag is 0, because **`unar` cannot see StuffIt 2.x's `NewDE` bit** (method
  `0x12` reported as `StuffItCompressionMethod: 18`, then *"Error on
  decrunching"*; `0x8D` does set it). **Cost: nothing yet**; a negative
  measured through somebody else's flag is about the flag. Corrected in
  FORMATS.md (*Encryption*), TESTING.md (*Decryption*) and
  `tools/run_crypt.py`.

- **`fuzz_cover.py`'s noise floor: "seeds 11 and 12 over an identical
  build differ by up to five functions in a family."** Measured 2026-09-27,
  corrected 2026-10-05 to **thirteen** — ARC 0 against 13, StuffIt classic 8
  against 1, at 3,000 cases (first recorded as 9 against 2, before method 14
  was split out). **Cost: nothing — the cautious direction** — but a floor too
  low makes a non-finding look like one. Corrected in TESTING.md,
  OPEN_ITEMS.md and the tool's docstring.

- **"The tables are not in the stream, so they are in the module;
  implementing this means recovering them from 9,176 bytes of code."**
  FORMATS.md and OPEN_ITEMS.md, written and withdrawn 2026-09-29: **every
  parameter is in the payload**, a TIFF (private tags 33606, 33607, 33608,
  33604), and the module file's other resources hold `DATA` 1000 and 1001 and
  a 31,952-byte `C3a`, *"C-Cube V1.0"*, the codec. **Cost: it was the whole
  cost estimate** quoted to the maintainer; the payload's `MM\0*` had been
  printed the day before.

- **"There is no oracle and no subject for `JPEG Lossy`; a genuine
  Photoshop 1.0 document would need Photoshop 1.0."** OPEN_ITEMS.md and
  FORMATS.md, 2026-09-29, withdrawn the same day **when the maintainer asked
  whether one could be made in emulation**: Photoshop 1.0.7, a 441 KB download
  this engine unwraps, runs on Mini vMac's Mac Plus despite its *"Macintosh SE
  or newer"*. **Cost: none yet**; the MacPaint rule — ask whether anything here
  can MAKE one — was not asked.

- **"Why StuffIt Deluxe 2.0.1 refuses its own `JPEG Lossy` archive is a
  hypothesis; a real Photoshop 1.0 document would settle it."**
  FORMATS.md and OPEN_ITEMS.md, settled 2026-09-29 **by the maintainer asking
  whether it could be tested**: the entry's method nibble is 0, so its 80
  stored bytes ARE the module's output — no JPEG stream; the archive holds an
  empty header. **Cost: one emulator boot that was not needed**; the run had
  printed `dcomp=80` beside `dlen=115320`.

- **"`JPEG Lossy`'s `'DCMP'` is a 9 KB JPEG decoder"** — FORMATS.md,
  OPEN_ITEMS.md, `tools/run_sitopt.py` and `src/fmt_sit.c`, corrected
  2026-09-29 **by the maintainer asking what the status rested on**: the
  module's NAME and SIZE (9,176 bytes, lossy, `ffff` for a checksum); none of
  the standard JPEG tables is in it verbatim. **Cost: nothing**; every other
  module's row cited a disassembly and this one a filename.

- **`MacPaint 1`'s data path was written as a loop over `_Read`,
  `_Write` and `_SetEOF`** (FORMATS.md, 2026-09-28). It is `_Read`,
  `_Write`, `_GetEOF` and `_SetFPos`, plus `_HOpen`/`_HCreate`/`_HDelete` and
  `PBGetFCBInfo`; corrected in place 2026-09-29, nothing depended on it.

- **"AppleLink `.pkg` cannot be sniffed without inventing a magic number" was
  withdrawn on the wrong grounds, and the probe that replaced it is now gone
  too.** `PKG Expand Translator`'s @0x2952 is the translator API's command
  parser, the same in the CompactPro, UnZip, BinHex4, UUCode and Unix
  Compress translators; `macextract sniff` called `Decode "Payload.hqx" to
  "Out"` a package and neither real package anything. `unc_applelink_probe`
  was removed 2026-09-27; the unit test asserts its absence. **Cost: 35 days
  of a format counted as *named* that never named a file, a "0 false positives
  across 928 fixtures" that could not fail, and the seven boots of
  2026-09-01** (DECISIONS.md 2026-09-27, *the recogniser that was a command
  line*).

- **"The shipped model is pessimistic by 2,926 B, against a recorded 1,138 B
  residue"** — a labelled hypothesis for one day, withdrawn 2026-09-27: the
  base, taken on another branch, re-took at **652,996 B** rather than 648,250
  and the residue at **−714 B** rather than +1,138 — **+4,746 less 1,820, the
  2,926 B to the byte** (then 653,532 B and −666 B when the AppleLink probe
  left). **Cost: nothing, because it was labelled**; folded into
  `OVL_RESIDUE` it would have made both terms wrong (DECISIONS.md 2026-09-27,
  *the residue that was two numbers*).

- **`OVL_SAVED` = 117,056 B** — 32 B stale from 2026-09-26 to 2026-09-27,
  under a comment naming a table that had been corrected; it moved thirty
  budgets. **Cost: part of a hypothesis that took two boots to settle.**
  `run_tiers.py --check-saved` grades it in `ci.sh` since 2026-09-27.

- **"`overlay-eager` costs one archive at 512 KB against `selective-loading`"**
  — withdrawn 2026-09-03 on the branch, recorded 2026-09-25. Releasing the
  ciphers raised the budget to 317,838 B and `derived-a2basic.dmg.sit` still
  failed with `gRefusedWhy` = 2: a 205 KB `NewPtr` against a 169,298 B largest
  block. **The memory was there, in two pieces**; one `MoveHHi` before the
  `HLock` closed the gap. **Cost: a day chasing the wrong cause**, with the
  instrument saying fragmentation throughout.

- **"One disk read at launch"** — the eager branch's argument, untrue in the
  build a user would run: `ovl_preload()` was called from the AUTOTEST
  `main()` only, so the shipping application fetched the bundle lazily.
  **Found by forbidding the reload** (`wa=128`). **Cost: every figure taken
  through `interactive.py` before 2026-09-02 was measured on a build that
  loaded nothing at launch** — the envelope row read 705,352 B and is 689,108 B
  with the preload (FORMATS.md, *What the application costs the engine*). Ask
  "which `main()`?" of every launch-time call.

- **"`os9.py --autotest` scores `os9sample.txt` 19/22 with a healthy
  build"** — written and withdrawn 2026-09-25: the verifier handed the
  REFERENCE the fixture's own path while the route renames inputs to
  `archive.sit` (a mismatch `verify_output()` fixed on 2026-08-08), and failed
  a detect-only `.rar`'s correct refusal. Fixed, the three pass 3/3. **Cost:
  one wrong figure in four files for an afternoon, and very nearly three
  fixtures dropped from `os9sample.txt`**; the overlay-vs-resident control
  agreed because the defect was in neither (`tools/vmac/README.md`,
  *`--autotest` scored three healthy fixtures*).

- **"The overlay prize is 5,988 B, it opens nothing new, and StuffIt can
  never be one of the formats it helps"** — written 2026-08-31 about a
  cipher-only overlay; superseded or withdrawn 2026-09-25. `overlay-eager`'s
  fourteen images gave **82–105 KB** more budget at 1 MB and **69/71 at System
  3.0 / 512 KB against main's 67/71**; StuffIt gains too, keeping ciphers of
  10,702 B (was 15,324 B). Download **+25,216 B** (189,312 → 214,528 B).
  **Cost: three weeks of a mechanism priced at a seventeenth of its measured
  value** (DECISIONS.md 2026-09-25, *the parked decision that outlived its
  numbers*); BRANCHES.md said 18,116 B, OPEN_ITEMS.md 5,988 B.

- **"walkprobe.py grades every volume walk in the tree"** — corrected
  2026-09-22 and 2026-09-23: six of eight, then eight of nine, the ninth
  `nowcompress.read_forks`. **Cost: one harness re-run that proved nothing**;
  searching for the capability finds **thirty** volume listers in `tools/`,
  nine graded (DECISIONS.md 2026-09-23, *the ninth walk, found by the missing
  line*).
- **"`superdisk.read_forks` has about thirty callers, several of which
  compare fork SETS"** — corrected 2026-09-22: **38** call sites across nine
  harnesses, **no** caller compares fork sets, four compare ENTRY sets. **Cost:
  nothing**; one root filter in the walk serves all 38 (DECISIONS.md
  2026-09-22, *the last walk, and the exit code nobody could get*).
- **`superdisk.py --adjudicate` has always exited 1**, raising `NameError` on
  another function's `shots` after the verdict. Found 2026-09-22 by running the
  harness rather than `tools/run_superdisk.py`. **Cost: an exit code that could
  never say success, for the life of the phase.**

- **"hfsutils hides names beginning with a dot without `-a`"** — withdrawn
  2026-09-22: it hides the Finder INVISIBLE bit, measured as a 2x2
  (`tools/vmac/walkprobe.py`). **Cost: one harness failure, one check that
  could not fail, and four walks still blind** — `os9.py` reported `Icon\r`
  MISSING with 51,781 bytes of resource fork, and `mkboot.verify_stripped`
  passed a planted invisible `Ghost INIT`. **All eight volume walks see an
  invisible entry since 2026-09-22** (`tools/vmac/README.md`, *What every walk
  can see*); observed four times, generalised none.
- **The OS 9 boot time** was recorded as "about four minutes", then "20-45
  minutes". An idle host settles the desktop in **~110 s**.
- **`macburger-helper.hqx` was written up three times as an anomaly.** It
  takes 150 s; **a timeout expiring is not a measurement**
  (`tools/vmac/README.md`).
- **`popper-1.7.tar.Z` and `PCCTS.tar.gz` at 1 MB** were root-caused and
  fixed: the sink held each whole fork in a `NewPtr` block. Streaming writes
  took the sweep 37/44 → 39/44; the old path is `UNC_MAC_STAGE_WRITES`.
- **The "all-black screen crash"** chased during M10 was a harness artifact:
  the emulator died by SIGHUP, and a dead X window reads as black.
- **The `mio_seek` eofErr fix** is correct and kept, but it was not the M10
  blocker either.
- **"`interactive.py`'s default phase never reaches a result alert"** —
  DECISIONS.md, 2026-08-24, wrong: an extraction that FAILS before its fixed
  Cancel leaves the alert in the `extracting` frame, which is how the
  low-memory alert was photographed. **Cost:** one day.
- **The Mac OS 9 harness was damaging its own disk image** by booting the
  master in place. Fixed: the published SHA-1 is verified before every run and
  the master copied to a throwaway (`tools/vmac/README.md`).

- **Six corpus figures the seven-sentence check could not see.**
  `check_docs.py` check 10 (2026-10-06) named seven sentences. **Corrected
  2026-10-07 by scanning the CLASS instead**: two at 951 against 954
  manifests, a sweep at 940 against 966 corpus files, and three *"no corpus
  file"* sentences false (`synth-os9-btoa.btoa`, `synth-os9-mime.mim`); 17
  historical figures are declared in the checker. **Cost: nothing measurable**
  (DECISIONS.md 2026-10-07, *the seven sentences that were not the class*).

- **`UncOptions.long_name`'s own documentation promised a length the
  walker had stopped keeping.** After the 2026-10-07 rewrite a NULL buffer
  leaves `name_full_len` 0 for a PATH. **Corrected 2026-10-07. Cost: the public
  contract wrong for hours; no host reads that length.** Also stated there:
  `long_name_cap` above 65,536 is unsupported (`UncPath.len` is 16-bit —
  measured: it wraps 65,535 → 31 at the 2,048th component); the CLI passes
  exactly 65,536.

- **`UNC_PATH_MAXDEPTH` was deleted from the code and left standing in
  the prose.** Six places after 2026-10-07, among them
  `tools/vmac/depthtest/main.c` PRINTING *"UNC_PATH_MAXDEPTH is 24"* on the
  Macintosh. **Cost: nothing yet** — corrected the same day.

- **The download's size, 227,968 against 227,840.** `tools/build_mac.sh`'s
  ceiling note against the committed `dist/` and FORMATS.md. **Corrected
  2026-10-08. Cost: nothing but confusion**; a ceiling's comment is checked by
  nothing.
- **"Every figure is a lower bound with a ±3 s poll error"** — FORMATS.md
  *Timed on the same Mac Plus*, 2026-08-29 to 2026-10-19. **They were upper
  bounds**; re-timed on `Ticks` (`tools/vmac/macclock.py`), Expander reads
  0.6–2.3 s below every cell. **Cost: the StuffIt row stood as "level, 1.00x"
  for seven weeks** (52.4 against 54.4 s) (DECISIONS.md 2026-10-19, *the clock
  inside the Mac*).

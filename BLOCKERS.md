# BLOCKERS.md

## Status

**No open blockers.** The engine and Linux CLI were never affected by anything
in this file. The Retro68 Mac shell runs and extracts byte-exact on every
system the project claims:

| tier | result |
|---|---|
| System 6.0.8, 4 MB Mac Plus (Mini vMac, a true 68000) | **69/69** sampled fixtures |
| System 6.0.8, **1 MB** — the floor target | **69/69**; no memory-budget refusals remain, and DiskDoubler method 5's 396 KB allocation succeeds here |
| System 7.0.1, 4 MB | **69/69** |
| Mac OS 9.2 (QEMU PowerPC, 68LC040 emulation) | **20/20** sampled fixtures, re-run 2026-08-27 after standing at 13/13 since M12; plus HFS+, the `SIZE` partition, and — since 2026-08-28 — both cancel routes, the Cmd-. chord and the Cancel BUTTON clicked with the pointer, an 8-bit name photographed, an encrypted archive decrypted through the password dialog after a wrong password was refused, and SpaceSaver replayed by path — the format no Macintosh tier had ever run, whose first run found a name defect in the shell (FORMATS.md) |

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
- **every input a suite grades against, made by one program.** Added
  2026-08-23: `run_btoa.py` grades the decoder against btoa 5.2.1 itself,
  which is the right oracle and is also a Unix program that has only ever
  written LF. Twenty-one cases therefore agreed on a property none of them
  chose. Ask what the generator never varies — for a text format read on a
  Macintosh, the line ending is the first thing to ask about (below).
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

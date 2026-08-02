# OPEN_ITEMS.md — what is missing, as of 2026-08-02

A standing audit of the gaps in this project: things not done, things done but
not verified, and things the repository currently asserts more confidently than
the evidence supports.

This is **not** BLOCKERS.md. That file records milestones that could not be
completed and investigations that went wrong; it currently reports no open
blockers, and that is accurate. Everything here is either deliberate scope,
unverified-but-probably-fine, or a small hole worth closing — none of it stops
the engine or the CLI, which are byte-exact against the oracle across 769
fixtures in `./ci.sh`.

Ranked by how much it matters. Each item says what would close it.

---

## 1. Cancel with partial output was untested under streaming writes

**Status: CLOSED 2026-08-01. Kept here because the reasoning is worth
retaining, and because one narrower gap remains (see the end of this item).**

The Mac sink used to accumulate each whole fork in RAM and write it in
`sink_end`. It now writes each chunk straight through as the engine produces
it. That changes what a cancel means: under staging, an aborted entry had put
nothing on disk yet; under streaming, it has partial bytes on disk **and a fork
still open** when the user hits Cmd-. or the Cancel button.

Neither test covers that:

- `tests/mac_sink_test.c:232` (`--cancel`, run by `ci.sh` via
  `tests/run_mac_sink.sh`) calls `sink_begin` and then
  `sink_end(UNC_ERR_ABORTED)` **without ever calling `sink_write`**. Under
  staging that was the whole story. Under streaming it exercises only the
  "no fork was ever opened" path.
- The on-Mac interactive cancel test — the `derived-EmpireBuilderDemo.sit`
  partial-output check recorded at `MANUAL_TESTS.md:29` — was driven against
  the **pre-streaming** binary.

The code path looks correct: `sink_end` calls `StreamClose`
(`mac/unclassic_mac.c:679`) before `MyHDelete` (`mac/unclassic_mac.c:731`), so
the fork is closed before the partial file is deleted. But "looks correct" is
exactly what the staging-era comments claimed, and BLOCKERS.md is a record of
where that led.

**What closed it**, on both write paths and both memory sizes:

- The mock `--cancel` case now runs two scenarios — abort with no data, and
  abort after 4100 bytes to the data fork plus 64 to the resource fork, which
  is past the 4 KB write chunk so the fork is genuinely open and non-empty.
  Both write paths run it in `ci.sh` (`tests/run_mac_sink.sh`).
- A new on-Mac mode, `tools/vmac/run.py -D UNC_AT_CANCEL`, aborts the real
  application once one entry has completed — so the cancel lands inside a
  later entry — and then counts what the Out volume actually holds. Files
  present must equal entries completed. Confirmed on a real System 6.0.8 Mac
  Plus at **4 MB and 1 MB** with `derived-EmpireBuilderDemo.sit`: 1 entry
  completed, 1 file on the volume, `ret == UNC_ERR_ABORTED`.

**That narrower gap is closed too.** The interactive UI around the cancel — the
progress dialog, the Cancel button's hit-testing, the "Extraction cancelled."
alert — has now been re-driven against the streaming binary
(`tools/vmac/interactive.py`, 2026-08-01): the dialog live at 13%, both cancel
routes reaching the alert, and SFGetFile afterwards listing exactly the one
entry that had completed.

---

## 2. The `v0.1` tag was 10 commits behind and misinformed

**Status: CLOSED 2026-08-01 by tagging `v0.2`.** `v0.1` is left where it is —
it is a historical marker and moving a tag rewrites what someone else may
already have fetched. `UNC_VERSION` and the README status heading now read
0.2 to match.

The problem it had: `v0.1` points at `ba492ac` (`bd3323e v0.1: clarify 1 MB
claim ...`), and three later commits changed the headline results. The tagged
tree still says:

| Tagged at v0.1 | True on master |
|---|---|
| 39/44 on-Mac at 4 MB, four timeouts | 44/44, no timeouts |
| `derived-RWAsm_Folder.sit` an unexplained failure | does not reproduce; 38/38 byte-exact |
| 36/44 at 1 MB | 39/44 |
| shell RAM limited by largest output fork | streaming; output size costs the shell nothing |
| "185 s on a 7 MHz 68000" | struck — the 1x setup that produced it is gone |

Anyone reading `v0.1` should treat its Mac numbers as superseded and use
`v0.2` or later.

**And `v0.2` in turn is superseded by `v0.3`**, for the same reason in a
different place: it states that Arsenic block sizes are a 128/256/512 KB mix
(they are all 512 KB), that BLOCKERS.md's 1 MB tally is 37/44 (it is 39/44),
and that QuickDraw bombs after File Manager activity (it does not). All three
are corrected in `v0.3`. The pattern is now twice-observed and worth naming:
**a tag freezes the documentation's errors along with its code**, and this
repository's errors have all been in the documentation.

---

## 3. Verified in an emulator, never on hardware

**Status: documented in full at `MANUAL_TESTS.md` "Still untested"; repeated
here because it is the largest genuine unknown.**

- **Real 68k hardware: never run.** No genuine floppy I/O, no real media errors
  mid-write, no real 8 KB stack underneath a real ROM's own usage. The
  per-entry I/O error path has never seen an actual I/O failure.
- **System 7: the corpus passes, the UI is untested.** 2026-08-01: the
  44-fixture sample runs 44/44 byte-exact on System 7.0.1 at 4 MB
  (`tools/vmac/run.py --system Sys7.img`), with peak heap identical to 6.0.8.
  At 1 MB System 7 does not boot at all — it wants 2 MB — so the 1 MB floor
  target is System 6 and only System 6. **Still open on System 7:** the
  interactive UI has never been driven there, and with it the two things the
  tier exists for — `SFReply.vRefNum` as a working-directory reference, and
  the `SIZE` partition under the Process Manager.
- **`SFReply` working-directory semantics: CLOSED 2026-08-01.** The code path
  OPEN_ITEMS has carried as untested since M10 — `SFReply.vRefNum` passed to
  the File Manager with `dirID` 0, which on System 7 and later is a working
  directory rather than a volume — now has a deterministic test, and it
  passes on both systems.

  `tools/vmac/run.py -D UNC_AT_WD` makes a real working directory over a real
  subfolder with `PBOpenWD`, extracts through it exactly as `ExtractOne()`
  does, and counts what landed where. **The output must be in the folder and
  the volume root must be empty** — and the root is the whole point: every
  earlier harness here extracted into a volume root, where the working
  directory and the root are the same directory, so no amount of testing
  could have caught a mistake.

  | system | wdRefNum | entries | in the folder | in the root |
  |---|---|---|---|---|
  | System 6.0.8 | -32717 | 3 | 3 | 0 |
  | System 7.0.1 | -32701 | 3 | 3 | 0 |

  It needs no Finder, no Standard File and no screen coordinates, which is
  why it worked where two attempts at driving System 7's Finder did not.
- **The `SIZE` partition: CLOSED 2026-08-02, and it works.** 4 MB preferred /
  400 KB minimum had never governed a launch, because System 6 without
  MultiFinder ignores it and that was the only system ever tested. Rebuilt with
  a 600 KB preferred partition and run on both systems with
  `derived-KeyGraphics.sit`, which needs ~656 KB: **System 7.0.1 refused the
  entry (peak 35.5 KB — parser state only, the block rejected at request time);
  System 6.0.8 passed with 656.8 KB.** Same binary, same fixture, same 4 MB
  machine. The Process Manager honours the partition, System 6 ignores it, and
  the engine's per-entry refusal behaves correctly when it bites. Method in
  MANUAL_TESTS.md.
- **Mac OS 9: still never run — and the harness was damaging its own disk
  image.** Found 2026-08-02: `os9.py` booted the master 2 GB image in place and
  never hashed it, so every run altered the one artifact it depends on and
  nothing could tell. Both fixed (copy-before-boot, published SHA-1 verified
  before every run, `--setup --force` to re-fetch); the drifted image was
  re-downloaded. The same lesson had been in BLOCKERS.md for Mini vMac since
  M10 and was never carried across.

  **A route proposed earlier the same day has been withdrawn.** It claimed the
  OS 9 boot volume was plain HFS, so the application could be dropped into
  `System Folder:Startup Items:` with hfsutils and launched with no Finder
  automation. The volume is **HFS+ inside an HFS wrapper**
  (`drEmbedSigWord = 'H+'`; hfsutils sees only the wrapper, whose root holds
  the single placeholder file `Where_have_all_my_files_gone?`), and this
  environment has **no HFS+ writer at all** — no hfsprogs, no kernel module.
  So offline writes to that volume are impossible here and the idea is dead,
  not merely untried. See BLOCKERS.md.

  **Attempted 2026-08-02 over four boots, not achieved — but now one run
  away.** Established directly: Mac OS 9.2 boots to the Finder here (20-45
  min, not the four the old note claimed), the transfer volume mounts beside
  the boot volume, and the desktop coordinates are measured and correct. What
  failed was the pointer, not the click: `info mice` shows `mac99`'s default
  is a **relative** ADB mouse, so `mouse_move` with absolute coordinates was
  applied as a delta and slammed the pointer into a corner. Every click landed
  on bare desktop — which looks exactly like a mis-measured icon, and cost
  three boots and two wrong "fixes" (click too slow, then too fast) to
  identify. Now fixed with `-device usb-tablet` **plus** `mouse_set`, since
  QEMU leaves the relative mouse active; `Qemu.use_absolute_pointer()` checks
  `info mice` before and after and refuses to run if the active pointer is
  still relative. **The pointer mechanism is verified; the launch is not** — a
  fifth boot with the absolute pointer still opened nothing.

  The current hypothesis, labelled as one: the **Mac OS Setup Assistant**
  launches shortly after the desktop settles (every boot, because the harness
  correctly starts from a pristine copy) and takes the foreground, and in
  classic Mac OS the first click in an inactive application only activates it.
  The double-click is therefore spent activating the Finder. `os9.py` now
  clicks bare desktop first. **Untested.** Five boots, three explanations, two
  of them confirmed real defects that were not sufficient — treat the third
  the same way until a screenshot shows an open window.

  What remains is the original plan: Finder automation through QEMU
  screendumps, with `mkapmdisk.py`'s transfer volume (HFS, and it already
  mounts) carrying the application. One thing does improve — the volume really
  being HFS+ means the "HFS+ long filenames" row is reachable on this image
  once the app can be run there, blocked on the same thing rather than a
  second one. If the reporting channel ever matters: `at_report()` pokes a
  1bpp framebuffer and OS 9 runs 32-bit colour, but QEMU writes its images
  back reliably, so results could be written to a file instead of the screen.
- **Mac OS 9 detail: still never run, but no longer blocked.** The `WaitNextEvent`
  branch, `SFReply.vRefNum` as a System 7+ working-directory reference, HFS+
  names and the `SIZE` partition under a real Process Manager remain untested
  code. `tools/vmac/os9.py` gets as far as: Mac OS 9.2 boots to the Finder
  under `qemu-system-ppc -M mac99,via=pmu`, and a transfer disk carrying the
  application and an archive mounts on its desktop. **Launching the
  application and driving it is not implemented**, which is where the
  verification would actually happen — so this is a harness, not a result,
  and the row stays open.
- **The interactive application: CLOSED 2026-08-01 for System 6.**
  `tools/vmac/interactive.py` drives the real UI under an emulator built for
  authentic Mac Plus timing and photographs each step: SFGetFile, the progress
  dialog repainting (caught at 13% and 16%), the Cancel button, Cmd-., the
  partial-output cleanup visible in the file list, and the success alert.
  `--e2e` adds the two things that need a Finder at both ends — launching the
  application by double-click, and double-clicking the application it
  extracted — plus volume navigation through Standard File's Drive button. It
  is not self-checking; the screenshots are the result, and the driving is
  what is repeatable. Still unexercised above System 6 (see below).

**To close:** the OS 9 half is being attempted under QEMU PowerPC. The real
hardware half **cannot be closed here at all** — it needs physical silicon,
and no amount of emulation substitutes for it. That row should stay in this
file until someone with a Mac Plus runs the checklist.

---

## 4. Capability gaps that are deliberate, but still gaps

- **StuffIt 5 / Arsenic on a 1 MB machine: 1 of 6 sampled fixtures.** An entry
  needs 0.63–2.53 MB (a 512 KB block, plus an inverse-BWT vector of four bytes
  per byte the block actually holds), so the floor-target
  machine mostly cannot do StuffIt 5. The engine declines per entry and leaves
  the rest of the archive alone, which is the designed behaviour and is
  documented in FORMATS.md — but it is the one format the "runs on a Mac Plus"
  claim does not really cover. Closing it means a fundamentally lower-memory
  inverse BWT, not a bug fix.
- **No timing data at all — attempted 2026-08-01, and it did not work.** The
  1x emulator exists, `run.py --emu` selects it, `run.py` now splits boot from
  extraction, and `tools/vmac/timing.txt` names the set to measure. A small
  fixture came out at boot 10 s + extract 2 s. But a 306 KB BinHex did not
  finish in fifteen minutes at 1x, twice, and this environment cannot
  distinguish the two candidate explanations at the time. **It can now:**
  decode cost measured on Linux shows that fixture is one of the CHEAPEST per
  byte — 3x cheaper than one that completes in ~134 s at 1x — so the
  non-completion was an artifact of the run, not a slow code path. The
  surviving problem is purely environmental: this host cannot run Mini vMac at
  a faithful 1x while also screenshotting it. A machine with a spare core
  would produce the whole table in an hour. Relative per-format cost IS now
  published (FORMATS.md), along with the single authentic 1x anchor.
- **Out of scope by the brief, and still out:** compression, StuffIt X
  (`.sitx`), encrypted archives, multi-segment archives, disk-image extraction,
  Now Compress, and LZH *extraction* — LZH was the optional half of M8 and is
  detect-only (`FORMATS.md:26`).

---

## 5. Loose ends

- **A hypothesis filed as a fact, found and killed 2026-08-01.** BLOCKERS.md
  carried "QuickDraw drawing bombs out of memory when called after any File
  Manager activity" under *test-harness lessons (not app bugs)* — which is
  where it hid, because as stated it meant the shipped interactive build was
  broken (SFGetFile, then a progress dialog, then an alert, is File Manager
  followed by QuickDraw). It does not reproduce: `tools/quickdraw-repro/`,
  twelve configurations on a real System 6.0.8 Mac Plus, every QuickDraw call
  clean with `MemError() == 0`. Neither suggested cause (master-pointer
  fragmentation; running as the boot shell instead of under the Finder) holds
  either. The general lesson is now in BLOCKERS.md: a hypothesis filed under
  "harness lessons" gets read as settled and nobody re-examines it. **This
  file is the place to look for others of the same shape.**
- **A report that DECISIONS.md was truncated is FALSE.** Checked 2026-08-02
  after it was raised: the file is intact at 656 lines, the working tree is
  byte-identical to HEAD, and the sentence said to be cut off — "The earlier
  disk-write crash was NOT one bug but" — is line 416, the opening of a
  mid-file section, and continues normally. Recorded because the natural
  response to that report is to "restore" the section, which would destroy
  correct history; `git diff HEAD DECISIONS.md` and `tail` answer it in
  seconds.
- **The harness leaks orphan processes when a run is killed.** Both
  `tools/vmac/run.py` and `tools/vmac/os9.py` start their emulator with
  `start_new_session=True`, deliberately — a stray signal to the process group
  must not take an emulator down mid-write — but the consequence is that when
  the driver is killed by a timeout, its cleanup `finally` does not run and
  the child survives. Observed twice on 2026-08-02: an orphaned
  `qemu-system-ppc`, and two orphaned `Xvfb` displays left by earlier Mini
  vMac runs. Harmless singly, but they accumulate across a long unattended
  sweep and compete for the CPU the emulator needs. Not fixed: the right fix
  is a signal handler, and it was not attempted here.
- **The Retro68 `OpenDF`/`HOpenDF` bug is still not filed.** The `_OpenDF`
  trap is System 7, and neither `OpenDF` nor `HOpenDF` falls back to a plain
  open when it returns `paramErr`, so both are unusable on System 6; `FSOpen`
  in the same file does fall back. Measured, cases 8 and 11 of
  `tools/retro68-hopen-repro/`. Written up ready to post in that directory's
  `ISSUE.md`; **still not submitted, because this environment has no GitHub
  credentials** — the network reaches github.com but an unauthenticated POST
  to the issues API returns 401. Filing it needs a human with an account.
  (Corrected 2026-08-01: the write-up previously blamed only `HOpenDF`, on a
  misreading of which function holds the fallback.)
- **The true root cause of the original "every open fails" saga is unknown.**
  Rewriting the File Manager calls as fully-zeroed HFS param blocks fixed it;
  which field mattered was never established, and the `HOpen`-glue attribution
  was withdrawn after a minimal repro disproved it. BLOCKERS.md says so
  plainly. Not being chased — the app is verified byte-exact as it stands.
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
- **Six StuffIt and two Compact Pro fixtures are excluded** as
  oracle-undecidable or oracle-buggy (`PROGRESS.md:9`, `PROGRESS.md:11`). They
  are not known failures; the oracle cannot adjudicate them.

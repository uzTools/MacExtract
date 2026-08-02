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
  interactive UI has never been driven there. That used to carry the two
  things the tier exists for with it — `SFReply.vRefNum` as a
  working-directory reference, and the `SIZE` partition under the Process
  Manager — but both are now tested directly, without a Finder, in the two
  entries below. What remains undriven is the UI itself: SFGetFile, the
  progress dialog and the alert, on System 7 specifically.
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
- **Mac OS 9: CLOSED 2026-08-02 — the application runs there, and its output
  is byte-exact.** `tools/vmac/os9.py --launch` boots Mac OS 9.2 under
  `qemu-system-ppc -M mac99,via=pmu`, launches the 68k application from the
  transfer volume through the 68LC040 emulator, extracts, and then compares
  **both forks** of everything it wrote against the same engine's Linux
  output. Results in FORMATS.md; method in MANUAL_TESTS.md.

  Three things about how it was closed are worth keeping:

  * **It is driven from the keyboard, and the mouse does not work here at
    all.** `tools/vmac/os9probe.py` measured eleven primitives in one boot:
    all five mouse probes changed exactly 0.0000 of the screen, all five
    keyboard probes worked, and locating the cursor by diffing screenshots
    found it only ever in the extreme corners, never at any of three
    requested positions. Typing selects by name in the Finder and Cmd-Down
    opens the selection, which needs no coordinates and no double-click
    timing. It worked first try.
  * **Five boots were spent on the mouse before that probe was written.**
    Three separate real defects were found and fixed — a 0.9 s double click,
    a relative ADB pointer fed absolute coordinates, the Setup Assistant
    holding the foreground — and none of them was the answer, because all
    three were about clicking. Every one was inferred from the same
    non-observation, "the volume did not open". See BLOCKERS.md; the general
    lesson is that a non-observation names no link in the chain, and it is
    the same lesson `macburger-helper.hqx` taught three times.
  * **The check does not go through the framebuffer.** The transfer volume is
    a file on the host, so the extracted forks are lifted out with hfsutils
    after the emulator exits and compared byte for byte. That is stronger
    than the on-screen CRC grid Mini vMac needs, and it doubles as proof the
    guest flushed: an unflushed volume fails to mount rather than passing.

  **What this closed in the untested-code list:** the `WaitNextEvent` branch,
  the Standard File path, and the whole Toolbox File Manager layer now run on
  a real Process Manager on PowerPC, not just on System 6. **What it did
  not:** see the two rows below.
- **Mac OS 9 on HFS+: CLOSED 2026-08-02.** `tools/vmac/os9.py --hfsplus`
  renames the HFS+ boot volume to `Out` from the keyboard and runs the
  autotest build against it, so the extraction lands on HFS+ rather than on
  the HFS transfer volume. `derived-Berkeley_Packet_Monitor.sit`: 31 files,
  `ret=0`, `errors=0`, data CRC sum and byte count identical to the Linux
  engine, peak heap 779.1 KB — and all 31 names exactly as the 31-character
  rule predicts, including the one entry whose name is 34 characters long and
  has to be truncated.

  Two things about it are worth keeping:

  * **The report comes back as a FILE, not off the screen.** `at_report()`
    pokes 1bpp pixels straight at the framebuffer, which is the right channel
    on a Mac Plus and invisible on Mac OS 9's 32-bit screen — confirmed by
    screenshot: the desktop is untouched after the app has finished. That is
    the real reason HFS+ stayed untested long after the application ran on
    OS 9; the output volume was never the problem, the ANSWER channel was.
    `at_report_file()` writes the same values, plus every output NAME, to the
    plain-HFS input volume, which the host can read whatever the output
    volume is.
  * **That the output volume is HFS+ is measured, not assumed.** The boot
    volume is HFS+ inside an HFS wrapper, and hfsutils can see only the
    wrapper. After the run the wrapper still holds exactly one file,
    `Where_have_all_my_files_gone?` — so none of the 31 files went to plain
    HFS. Reading a signature word was considered and rejected: the classic
    File Manager reports `'BD'` for an HFS+ volume for compatibility, so a
    negative there would prove nothing, and misreading a signature at a fixed
    offset is exactly how the "the boot volume is plain HFS" claim went wrong
    in the first place.

  **Still open on HFS+:** names that HFS+ permits and HFS does not. A 68k
  application reaching HFS+ through the classic File Manager is limited to 31
  characters either way, so the interesting cases may not be reachable at all
  from this binary — which is itself worth establishing rather than assuming.
- **Mac OS 9: the `SIZE` partition — CLOSED 2026-08-02, and it bites.** Built
  with a 600 KB preferred partition and run against `derived-KeyGraphics.sit`,
  which needs ~656 KB: **1 entry refused, 0 files written, `ret == UNC_OK`,
  peak heap 35.5 KB** — the same figure System 7.0.1 produced, on a machine
  with 512 MB of RAM. The partition governs, not the hardware, and 35.5 KB is
  parser state alone, so the 512 KB block was rejected at request time rather
  than allocated and failed over. `os9.py --hfsplus --expect-refusal`, which
  passes only if the Linux engine extracts the fixture AND the Mac declines
  it — a negative test that cannot pass on an empty archive.
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
- **Timing: MEASURED 2026-08-02, and closed.** Eight
  fixtures across eight formats at authentic 1x, 8/8: boot ~10 s, every
  extraction under 5 s, plus the 278 KB StuffIt anchor at ~134 s (FORMATS.md,
  README). The earlier diagnosis that this host "cannot be trusted to run 1x"
  was wrong and is corrected — an idle machine measures fine. What remains is
  nothing outstanding: `macburger-helper.hqx`, written up three times as an
  anomaly, simply takes 150 s, and instrumenting the engine's byte counter
  (`-D UNC_AT_PROGRESS`) showed the rate is very non-uniform so every timeout
  chosen for it expired mid-run. **Timing is closed for every format sampled.**
- ~~**No timing data at all — attempted 2026-08-01, and it did not work.**~~ The
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
  sweep and compete for the CPU the emulator needs — which is the same
  contention that made the 1x timing measurement unusable. **FIXED 2026-08-02**:
  both harnesses now install a SIGTERM/SIGINT handler that raises `SystemExit`,
  so a signal unwinds normally and the existing `finally` cleanup runs.
  Demonstrated rather than assumed — a 1x run was interrupted with a live
  emulator, printed "interrupted by signal 15", and left zero `minivmac` and
  zero `Xvfb` processes behind.
- **The Retro68 `OpenDF`/`HOpenDF` bug is still not filed.** The `_OpenDF`
  trap is System 7, and neither `OpenDF` nor `HOpenDF` falls back to a plain
  open when it returns `paramErr`, so both are unusable on System 6; `FSOpen`
  in the same file does fall back. Measured, cases 8 and 11 of
  `tools/retro68-hopen-repro/`. Written up ready to post in that directory's
  `ISSUE.md`; **deliberately not submitted, and no future session should
  submit it.** The maintainer of this project will post it from his own
  account — that is a standing instruction, not a limitation to work around.
  (It is also not technically possible from here: the network reaches
  github.com but an unauthenticated POST to the issues API returns 401.)
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

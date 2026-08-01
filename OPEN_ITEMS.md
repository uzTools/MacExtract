# OPEN_ITEMS.md — what is missing, as of 2026-08-01

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
- **Mac OS 9: still never run, but no longer blocked.** The `WaitNextEvent`
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
- **No timing data at all.** The Mini vMac builds run "all out", so the harness
  measures correctness only. "Runs on a Mac Plus" is proven; "is usable on a
  Mac Plus" is not. Closing it means a third emulator build at `-speed z` and a
  small timing sweep.
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
- **The Retro68 `HOpenDF` bug was never filed.** `PBHOpenDFSync` issues a
  System 7 trap and, unlike the non-hierarchical `OpenDF` beside it, has no
  fallback, so `HOpenDF` returns `paramErr` on System 6. Written up ready to
  post in `tools/retro68-hopen-repro/ISSUE.md`; not submitted because this
  environment has no GitHub credentials (`BLOCKERS.md:43`).
- **The true root cause of the original "every open fails" saga is unknown.**
  Rewriting the File Manager calls as fully-zeroed HFS param blocks fixed it;
  which field mattered was never established, and the `HOpen`-glue attribution
  was withdrawn after a minimal repro disproved it. BLOCKERS.md says so
  plainly. Not being chased — the app is verified byte-exact as it stands.
- **StuffIt method 1 (RLE) is unit-test-only.** No corpus fixture uses it, so
  it is pinned by hand-built vectors rather than by the oracle
  (`PROGRESS.md:10`).
- **Six StuffIt and two Compact Pro fixtures are excluded** as
  oracle-undecidable or oracle-buggy (`PROGRESS.md:9`, `PROGRESS.md:11`). They
  are not known failures; the oracle cannot adjudicate them.

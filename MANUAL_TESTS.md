# MANUAL_TESTS.md — Macintosh application checklist

NOTE (2026-07-25): the shell runs under Mini vMac (System 6.0.8, Mac
Plus, a true 68000) and **extracts correctly — single-fork, two-fork,
and multi-file — with both forks verified byte-exact ON THE MAC ITSELF**
(44/44 sampled fixtures at 4 MB across all twelve formats, 39/44 at
1 MB). Data forks match exactly;
resource forks match except the 112-byte "reserved for system use" area
of the resource file header (offsets 16–127), which is masked identically
on both sides — see DECISIONS.md. For the 1 MB Mac Plus results, see the
per-fixture table in FORMATS.md.

The earlier claim that this was caused by a **broken Retro68 `HOpen`
glue** has been **withdrawn** — a standalone minimal reproduction
(`tools/retro68-hopen-repro/`) disproved it. See BLOCKERS.md.

### System 7.0.1, 2026-08-01 — a second system tier, corpus only

Every on-Mac result before this one came from System 6.0.8. This is the first
time the binary has been run anywhere else in the System 6 → Mac OS 9 range
the project claims.

**What was run:** the committed 44-fixture sample, on a stripped System 7.0.1
boot volume, 4 MB Mac Plus, same on-Mac CRC-32 read-back of both forks.

    tools/vmac/run.py --system Sys7.img --list tools/vmac/sample.txt

**Result: 44/44 byte-exact**, with engine peak heap identical to System 6.0.8
on every fixture. **1 MB: the system does not boot** — a probe painted nothing
in 180 s, which is System 7 needing 2 MB, not a fault in the application.

7.0.1 rather than 7.1 because 7.1 survives on the mirrors only as floppy sets
and a beta ISO. Both are System 7; what the tier is for is the two things
System 6 cannot reach — a working-directory `SFReply.vRefNum`, and a Process
Manager that honours the `SIZE` partition.

**NOT run on System 7, and therefore not claimed:**

- **The interactive UI.** Only the headless autotest build was replayed. The
  Finder-driven path (`--e2e`) has run on 6.0.8 only.
- **`SFReply` working-directory semantics: now TESTED, and passing.** See the
  section below — `run.py -D UNC_AT_WD` settles it without a Finder.
- **The `SIZE` partition under the Process Manager.** Still never exercised.

### Working directories, 2026-08-01 (System 6.0.8 AND System 7.0.1, 4 MB)

`tools/vmac/run.py -D UNC_AT_WD` with `derived-EmpireBuilderDemo.sit`.

The application takes `SFReply.vRefNum` from Standard File and hands it to the
File Manager with `dirID` 0. On System 7 and later that refNum is a **working
directory**, not a volume — untested code since M10, and untestable by any
harness here until now, because they all extracted into a volume ROOT where
the working directory and the root are the same directory.

This build makes a real working directory over a real subfolder with
`PBOpenWD`, extracts through it exactly as `ExtractOne()` does, and counts
what landed where. No Finder, no Standard File, no screen coordinates.

| system | wdRefNum | entries | in the folder | in the root |
|---|---|---|---|---|
| System 6.0.8 | -32717 | 3 | 3 | 0 |
| System 7.0.1 | -32701 | 3 | 3 | 0 |

The refNums are negative and outside the volume range, i.e. genuine working
directory references rather than volume refNums that happened to work. The
root column is the one that matters: nothing leaked out of the folder.

### End to end from the Finder, 2026-08-01 (System 6.0.8, 4 MB, 1x)

`tools/vmac/interactive.py --e2e` with `derived-ScrollbarPattern.sit`. Unlike
every other on-Mac run here, this one leaves the **Finder** in place instead of
installing the application as the boot shell — which is the only way to launch
the application the way a person does, and the only way to launch what it
extracted. A second volume is mounted so Standard File's Drive button has
somewhere to go. Confirmed from the screenshots, in one session:

- **Launched by double-clicking it in the Finder.** SFGetFile comes up on the
  boot volume, listing `archive.sit`, `unclassic` and the System Folder.
- **Volume navigation works.** Drive switches the listing to the second volume
  (`Second`, showing only its Desktop file) and back to `Macintosh`, with the
  archive re-selected.
- **Result alert**: "Extraction complete." after ~11 s of emulated Mac Plus
  time for this small archive.
- **Quits cleanly to the Finder on Cmd-.** in SFGetFile, and the volume window
  then shows six items — the four it started with plus the archive's two
  entries.
- **The extracted application has an application icon** in the Finder, so
  type/creator and the Finder inited flag were applied.
- **The extracted application launches by double-click** and draws its splash
  screen ("Scrollbar Pattern Editor — a simple little utility by Andrew
  McGeachie"). This is the test that exercises type/creator, the inited flag
  and resource-fork integrity together: the application *is* its resource
  fork, so it could not launch if a single byte were wrong.

### Re-driven on 2026-08-01 against the streaming sink (System 6.0.8, 4 MB, 1x)

`tools/vmac/interactive.py` drives the real application under an emulator
built for authentic 7 MHz timing and photographs every step. Confirmed from
the screenshots:

- **SFGetFile** comes up listing the archive on the boot volume.
- **Progress dialog** repaints live — caught mid-run at 13% and 16%.
- **The Cancel button** stops it: "Extraction cancelled." alert.
- **Cmd-.** does the same, by the other route (the keyDown check in
  ProgressPump rather than Dialog Manager hit-testing).
- **Partial output is removed, still.** After cancelling, SFGetFile lists
  exactly `Demo Manual V1.6` — the one entry that had finished — and no
  trace of `EB Sounds`, the entry that was being written. This is the
  behaviour the streaming rewrite put at risk, seen in the file list rather
  than inferred.
- **Extraction completes**: "Extraction complete." after ~134 s of emulated
  Mac Plus time for `derived-EmpireBuilderDemo.sit` (278 KB in, 417 KB out,
  3 entries); the machine boots in ~16 s.

### Driven end to end on 2026-07-25 (System 6.0.8, Mini vMac)

Done interactively by hand, before the sink was rewritten to stream. Each
step was captured; the items above supersede the cancel-related ones.

- Application launches from the Finder; **SFGetFile** appears and lists
  the archive.
- **Open** → **progress dialog** appears and repaints live (observed
  18% → 51% → completion on a 278 KB StuffIt archive).
- **Result alert**: "Extraction complete." on success, and
  "Extraction cancelled." after a cancel.
- **Cmd-.** during extraction cancels promptly (Mini vMac maps the host
  Alt key to Command).
- **Partial output is removed.** Cancelling part-way through
  `derived-EmpireBuilderDemo.sit` (3 entries) left exactly the one entry
  that had already completed, `Demo Manual V1.6`; the entry being written
  at the time, `EB Sounds`, was deleted rather than left truncated, and
  the third was never started.
- Cancelling SFGetFile quits cleanly back to the Finder.
- **An extracted application actually runs** (re-confirmed 2026-08-01 against
  the streaming sink, scripted — see the section above).
  `derived-ScrollbarPattern.sit`
  was extracted onto an HFS volume; the Finder showed
  `Scrollbar Pattern Editor` with an application icon (so type/creator
  and the inited flag were applied), and double-clicking it **launched
  it** — splash screen, then its working pattern-editor dialog. This is
  the one test that exercises type/creator, the Finder inited flag and
  resource-fork integrity together: the application *is* its resource
  fork, so it could not have launched if a single resource byte were
  wrong.

### Automated regression harness (Linux, no interaction)
- `sh tests/run_mac_sink.sh` (in `ci.sh`): runs the ACTUAL sink through a
  mock Toolbox against the engine, byte-exact vs. the oracle manifests,
  natively (ASan+UBSan) and under `qemu-m68k` — the file-backed IO path,
  the RAM-slurp `xio_*` path, BOTH write paths (streaming, and the older
  whole-fork staging under `UNC_MAC_STAGE_WRITES`, including its
  shared-block variant), AND the Cmd-. cancel cleanup (`--cancel`).
  Authoritative proof of the sink logic on the target word size/endian.
- **`tools/vmac/run.py` — the on-Mac replay, scripted end to end.** It
  boots a stripped System 6.0.8 straight into the `-DUNC_MAC_AUTOTEST`
  build (no Finder, no simulated double-click), which finds the HFS
  volumes "In"/"Out", extracts `In:archive.sit` onto Out, reads both forks
  back through the real File Manager, CRC-32s them, and **paints the
  result to the framebuffer** (Mini vMac's disk write-back is too
  lazy/partial to read off the Out volume). The host decodes a screenshot
  (`tools/decode_grid.py`) and cross-checks against the Linux engine
  (`tools/vmac_check.py`):

      tools/vmac/setup.sh                                       # once
      tools/vmac/run.py --list tools/vmac/sample.txt            # 4 MB
      tools/vmac/run.py --list tools/vmac/sample.txt --mem 1M   # floor target

  `-D UNC_AT_CANCEL` switches it to the cancel-cleanup check: the app aborts
  once one entry has completed — so the cancel lands inside a LATER entry,
  with that file already created and already written to — and then counts
  what the volume actually holds. Files present must equal entries
  completed, i.e. the aborted entry left nothing behind. Confirmed at 4 MB
  and 1 MB on 2026-08-01 with `derived-EmpireBuilderDemo.sit` (a flat
  3-entry archive; the walk is one level deep, and the app reports the
  root's folder count so a non-flat archive cannot be mistaken for a pass).

  It is not part of `ci.sh` (downloads, an X server, minutes per fixture).
  Read `tools/vmac/README.md` before changing it — several of its
  arrangements exist to work around emulator behaviour, not by preference.
  Note that the emulator runs **all out**, so its wall-clock times say
  nothing about a real 7 MHz 68000.

Before calling the interactive app working, run this checklist in each
environment. Do not skip the System 6 / Mac Plus column — that is the
floor target and the most likely place for stack, memory and trap
assumptions to break.

## Environments

1. **Mini vMac** (Mac Plus emulation, System 6.0.8, 1 MB then 4 MB)
2. **A real Mac Plus** (System 6.0.x, 1 MB, if available)
3. **Mac OS 9** (real hardware or SheepShaver/QEMU)

## Still untested — what is NOT known to work

Everything claimed above was observed under **Mini vMac only**. Two of
the three target environments have never been exercised at all. Nothing
below is a known failure; it is simply unverified, and should not be
described as working until someone runs it.

Three things, specifically, and none of them can be closed from here:

1. **Real 68k hardware** — any physical Mac Plus, SE or Classic.
2. **A real Mac Plus with a real 1 MB of RAM.** The 1 MB figures in
   FORMATS.md come from an emulated 1 MB machine with a stripped System
   Folder; a real one has INITs, a real ROM's own memory use, and less
   free heap than any number recorded here.
3. **Mac OS 9 on PowerPC**, where the binary runs under the 68LC040
   emulator. `tools/vmac/os9.py` boots that machine and mounts a disk with
   the application on it, and stops there.

### Real 68k hardware (Mac Plus / SE / Classic, System 6.0.x)

Never run on physical hardware. Mini vMac emulates a Mac Plus faithfully
enough for the File Manager, Memory Manager and QuickDraw paths used
here, but it is not the same as silicon. Specifically unverified:

- **Real 68000 timing and the floppy-only I/O path.** Every on-Mac test
  so far used emulated disks backed by host files; a real 800K floppy is
  orders of magnitude slower and can return media errors mid-write that
  the emulator never produces. The per-entry error path has never seen a
  genuine I/O failure.
- **Actual free memory on a stock 1 MB Plus.** The 1 MB figures in
  FORMATS.md come from an emulated 1 MB machine with a clean System
  6.0.8 and no INITs. A real machine with a Chooser extension or two has
  less, and the `FreeMem()`-derived budget will land lower than recorded.
- **The `SetApplLimit` stack bump against a real 8 KB stack**, and
  whether the engine's ≤4 KB call-chain bound holds with the real
  ROM's own stack use underneath it.
- **Address-error behaviour.** x86 and the emulator both tolerate some
  unaligned access patterns that a real 68000 traps on. CI's
  `-fsanitize=alignment` and the qemu-m68k mock are the current
  defence; neither is the actual CPU.
- Whether the app's memory use leaves the Finder able to relaunch
  afterwards (`FreeMem()` returning to its starting value is checked
  in-app, not across a real reboot cycle).

### Mac OS 9 on PowerPC

Never run above System 6. The binary is 68k-only and would execute
under the 68LC040 emulator on a PowerPC Mac; that whole layer is
untested.

`tools/vmac/os9.py` is a partial harness for closing this: Mac OS 9.2
boots to the Finder under `qemu-system-ppc -M mac99,via=pmu` (about four
minutes, headless, screenshots via QEMU's monitor), and a transfer disk
from `tools/vmac/mkapmdisk.py` carrying the application and an archive
mounts on its desktop. Launching the application and driving it is NOT
implemented, so everything below is still unverified:

- **The runtime trap checks actually taking the modern path.**
  `gHasWNE = TrapAvailable(_WaitNextEvent)` selects `WaitNextEvent` over
  `GetNextEvent`+`SystemTask`; only the System 6 branch has ever run.
  Cooperative yielding to other applications during a long extraction
  is therefore unverified.
- **`SFReply.vRefNum` as a working-directory reference.** On System 7
  and later this is a WDRefNum rather than a true volume refNum, and the
  code passes it with `dirID` 0. It behaves correctly on System 6; that
  extraction lands next to the archive on OS 9 has not been confirmed.
- **HFS+ volumes.** All testing used HFS. Long names, the 31-character
  truncation rule and the collision-suffix logic have never met an HFS+
  volume, nor names that HFS+ permits and HFS does not.
- **Files larger than the HFS 2 GB cap**, and the engine's 32-bit-only
  arithmetic against them.
- **The 'SIZE' resource under a real MultiFinder/Process Manager.** On
  System 6 without MultiFinder the SIZE partition is ignored and the app
  simply gets the free heap, which is the only case tested. The 400 KB
  minimum / 4 MB preferred pair has never actually governed a launch.
- MacRoman filename display, and 8-bit characters in names, above
  System 6.

## Setup

- Build: see mac/CMakeLists.txt header. Import `unclassic.dsk` (or the
  .bin) into the target system; copy the application to the boot disk.
- The bootstrap distribution is built by `tools/make_dist.sh`, which builds
  the application rather than picking up an old one, and checks that the
  800K image and the MacBinary carry the same resource fork byte for byte.
  **`dist/unclassic.dsk` mounts on System 6.0.8** — confirmed 2026-08-01 by
  `tools/vmac/mountcheck.py dist/unclassic.dsk`, which boots the stock system
  with the image attached and photographs the desktop; the `unclassic` volume
  appears below the boot disk. hfsutils reading an image is not evidence that
  a Mac will mount it.
- Bring test archives over as MacBinary (.bin) files — ImportFl or
  similar drops the wrapper; unclassic itself can unwrap MacBinary if
  the file arrives with a flattened fork.

## Checklist (every environment)

Launch & UI
- [ ] Application launches; SFGetFile appears immediately.
      (System 6: confirmed 2026-08-01, launched by double-click from a real
      Finder desktop — `tools/vmac/interactive.py --e2e`.)
- [ ] Cancel in SFGetFile quits cleanly to Finder.
      (System 6: confirmed 2026-08-01 by the same run, via Cmd-.)
- [ ] Standard File's Drive button switches volumes and back.
      (System 6: confirmed 2026-08-01 with a second volume mounted.)
- [ ] During extraction the progress dialog shows and repaints when
      covered/uncovered (System 6: by desk accessories).
- [ ] Cancel button stops extraction promptly (< 1 s); already-completed
      entries remain, the entry being written is deleted rather than left
      truncated, and the app returns to SFGetFile without damage.
- [ ] Cmd-. behaves exactly like the Cancel button.
      (Both re-confirmed against the streaming sink on 2026-08-01 by
      `tools/vmac/interactive.py`, at authentic Mac Plus speed — see below.)
- [ ] Under MultiFinder / System 7+ / OS 9: the app yields (other apps
      stay responsive while extracting; WaitNextEvent path).

Extraction correctness (use archives whose contents are known from the
Linux differential suite)
- [ ] A classic .sit (methods 2/13 mix): all files appear, correct
      sizes, type/creator/icons correct in Finder, dates preserved.
- [ ] A .cpt with nested folders: folder tree recreated.
- [ ] A .hqx and a .bin: single file with both forks; ResEdit (or
      Get Info) confirms the resource fork is intact.
- [ ] A file whose name contains '/': appears with '/' in Finder
      (engine ':' undone).
- [ ] Name collision: extracting the same archive twice produces
      "name~1" copies, no overwrite, no crash.
- [ ] An archive with a >31-char member name (zip/tar): truncated to
      31 chars, extraction completes.

Resource limits (Mac Plus / 1 MB, System 6)
- [ ] Small .sit extracts with ~700 KB free heap.
- [ ] A StuffIt 5 (Arsenic) archive fails **per entry** with a clean
      alert — no crash, no hang, no heap corruption on return.
- [ ] Extraction of a large archive (> free memory in output size)
      streams: memory usage stays flat (About This Mac / heap watch).
- [ ] After several consecutive extractions FreeMem() returns to the
      same value (no leaks; MacsBug `hc` clean if available).

Corrupt input
- [ ] A truncated .sit: per-entry error alert, app stays alive.
- [ ] A random file renamed .sit: "could not be extracted" alert.

Mac OS 9 specific
- [ ] Long extraction in the background while another app is frontmost.
- [ ] Filenames with 8-bit MacRoman characters display correctly.

## Known deviations to verify/fix at runtime

- SFReply.vRefNum is a working-directory reference on System 7+; the
  HOpen/HCreate calls pass dirID 0 with it. Verify extraction lands
  next to the archive on both System 6 and 9.
- The progress dialog uses DialogSelect without a filterProc; verify
  the Cancel button highlights on click.
- 'SIZE' partition is 4 MB preferred / 400 KB minimum. Arsenic (StuffIt 5
  method 15) needs 0.64–2.6 MB depending on block size, so on a small
  machine it refuses per entry rather than the app refusing to launch.
  That is the documented tier, not a bug — see FORMATS.md.

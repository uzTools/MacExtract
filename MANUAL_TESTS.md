# MANUAL_TESTS.md — Macintosh application checklist

NOTE (2026-07-23): the shell runs under Mini vMac (System 6.0.8, Mac
Plus, 4 MB) and now **extracts single-fork files correctly** — data
forks byte-exact, resource forks byte-exact except the OS-stamped
"reserved for system use" header (offsets 16–127), with type/creator/
dates set. See BLOCKERS.md for the write-path root causes that were
fixed (`mio_seek` eofErr; RAM-slurping the archive to avoid read/write
interleave on one HFS volume; and staging both forks of a two-fork file
in ONE shared block — three separate NewPtr staging blocks bomb System
6's Memory Manager, two blocks are fine). Two-fork files now extract
without crashing, both forks byte-exact (proven off-Mac via
`UNC_MAC_FORCE_SHAREBUF` in `tests/run_mac_sink.sh`). The interactive
checklist below is still the gate for the full UI (SFGetFile, progress
dialog, Cancel).

### Automated regression harness (Linux, no interaction)
- `sh tests/run_mac_sink.sh` (in `ci.sh`): runs the ACTUAL sink through a
  mock Toolbox against the engine, byte-exact vs. the oracle manifests,
  natively (ASan+UBSan) and under `qemu-m68k` — both the file-backed IO
  path and the RAM-slurp `xio_*` path (`ram` mode). This is the
  authoritative proof of the sink logic on the target word size/endian.
- A headless Mini vMac harness (build with `-DUNC_MAC_AUTOTEST`) drives
  the real System 6 File Manager: it finds a "Test" HFS volume, extracts
  `:archive.sit` into it, writes a `DONE` marker (forces the volume
  commit before the emulator is killed), and idles. The host then mounts
  the image with `hfsutils` and diffs the forks with
  `tools/verify_forks.py` / `tools/analyze_forks.py` (an all-in-16..127
  resource-fork diff counts as a pass — see above). Use a **pristine**
  boot image per run: repeated boot+kill cycles corrupt it, and a
  first-boot Desktop rebuild is slow enough to throw off UI timing.

Before calling the interactive app working, run this checklist in each
environment. Do not skip the System 6 / Mac Plus column — that is the
floor target and the most likely place for stack, memory and trap
assumptions to break.

## Environments

1. **Mini vMac** (Mac Plus emulation, System 6.0.8, 1 MB then 4 MB)
2. **A real Mac Plus** (System 6.0.x, 1 MB, if available)
3. **Mac OS 9** (real hardware or SheepShaver/QEMU)

## Setup

- Build: see mac/CMakeLists.txt header. Import `unclassic.dsk` (or the
  .bin) into the target system; copy the application to the boot disk.
- Bring test archives over as MacBinary (.bin) files — ImportFl or
  similar drops the wrapper; unclassic itself can unwrap MacBinary if
  the file arrives with a flattened fork.

## Checklist (every environment)

Launch & UI
- [ ] Application launches; SFGetFile appears immediately.
- [ ] Cancel in SFGetFile quits cleanly to Finder.
- [ ] During extraction the progress dialog shows and repaints when
      covered/uncovered (System 6: by desk accessories).
- [ ] Cancel button stops extraction promptly (< 1 s); partial output
      remains but the app returns to SFGetFile without damage.
- [ ] Cmd-. behaves exactly like the Cancel button.
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
- 'SIZE' partition (768 KB preferred / 512 KB minimum) may need tuning
  for Arsenic archives (needs ~1.1 MB for 512 KB blocks) — acceptable
  to document as "requires more memory" instead.

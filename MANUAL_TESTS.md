# MANUAL_TESTS.md — Macintosh application checklist

NOTE (2026-07-24): the shell runs under Mini vMac (System 6.0.8, 4 MB
Mac Plus, a true 68000) and **extracts correctly — single-fork,
two-fork, and multi-file — with both forks verified byte-exact ON THE
MAC ITSELF** (40/44 corpus fixtures across all twelve formats; the other
four are the largest and merely slow on the 68000). Data forks match
exactly; resource forks match except the OS-stamped "reserved for system
use" header (offsets 16–127); type/creator and the cleared inited flag
are confirmed on-Mac so an extracted `APPL` launches by double-click.
The real root cause of the long saga was a **broken Retro68 `HOpen`
glue** (returns noErr but never sets the refNum) — see BLOCKERS.md; fixed
by driving the File Manager through explicit HFS param blocks. The
interactive app was driven under Mini vMac up to **SFGetFile** (launches,
shows the picker, lists the archive — captured); the full modal
click-through (Open → progress → result; Cancel) is the checklist below.

### Automated regression harness (Linux, no interaction)
- `sh tests/run_mac_sink.sh` (in `ci.sh`): runs the ACTUAL sink through a
  mock Toolbox against the engine, byte-exact vs. the oracle manifests,
  natively (ASan+UBSan) and under `qemu-m68k` — the file-backed IO path,
  the RAM-slurp `xio_*` path, the shared-block two-fork path, AND the
  Cmd-. cancel cleanup (`--cancel`). Authoritative proof of the sink
  logic on the target word size/endian.
- The on-Mac autotest (build with `-DUNC_MAC_AUTOTEST`) drives the real
  System 6 File Manager: it finds HFS volumes "In"/"Out", extracts
  `In:archive.sit` onto Out, reads both forks back through the File
  Manager, CRC-32s them, and **paints the result to the framebuffer**
  (Mini vMac's disk write-back is too lazy/partial to read off the Out
  volume). The host decodes a screenshot (`tools/decode_grid.py`) and
  cross-checks against the Linux engine (`tools/vmac_check.py`). Use a
  **pristine** boot image per run, and boot the emulator as a child of a
  long-running process (a launcher that backgrounds it and exits takes it
  down via SIGHUP — a dead X window reads as a false "black-screen crash").

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

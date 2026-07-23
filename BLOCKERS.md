# BLOCKERS.md

## M10 Mac shell — RESOLVED (single- and two-fork extraction work)

**Status:** RESOLVED. The Mac app runs under Mini vMac (System 6.0.8,
4 MB) and extracts real Classic-Mac files correctly, including files that
carry both a data fork and a resource fork. The engine and Linux CLI
(M0–M9) were never affected. No open blockers remain; the notes below
record what the "disk-write crash" actually was and how it was fixed.

### What works on a real emulated Mac (verified in Mini vMac)
Driven headlessly through a self-extracting autotest build
(`-DUNC_MAC_AUTOTEST`, see `tools/` / `MANUAL_TESTS.md`), extracting to
an HFS volume and diffing the on-disk forks against the oracle manifests:

- **Data-fork files** come out **byte-exact** (e.g. a 40 KB HyperCard
  stack: full data fork matches the manifest SHA-256).
- **Resource-fork files** (INITs, cdevs, FKEYs, control panels) come out
  correct too: the resource data and map match byte-for-byte, and
  type/creator/Finder-flags/dates are set. The ONLY bytes that differ are
  in the resource fork's "reserved for system use" header area (offsets
  16–127), which a real Mac's Resource Manager stamps with machine/
  session-specific data (a current timestamp among them). No off-Mac tool
  can reproduce that, so a byte-exact comparison of the reserved area is
  *expected* to differ; the actual resources are intact.
- **Two-fork files** (data + resource) no longer crash — the shared-block
  fix below. On real Mini vMac the app runs to idle with no system-error
  bomb; the identical write path is proven byte-exact for both forks
  off-Mac (below).

### The three root causes that were found and fixed
1. **`mio_seek` treated `eofErr` as failure.** `SetFPos` past/at EOF
   returns `eofErr` while still positioning at EOF; the seek helper turned
   that into a hard `UNC_ERR_IO`, so extraction reported I/O failure. Fix:
   treat `eofErr` as success (it is — a following read just returns 0).
   The Linux mock never caught this because its `lseek` allows seeks past
   EOF; the mock's `SetFPos` now mimics the real Mac.
2. **Reads returned zeros when output writes interleaved.** On a real Mac,
   reading the input archive while the sink creates/extends output files
   on the SAME HFS volume corrupts the reader's file mark — input reads
   start returning zeros mid-extraction. Fix: **slurp the entire archive
   into RAM once, up front, then decode from a memory buffer** (`MemIO` /
   `xio_*`). No File Manager read is ever interleaved with a write, and
   all output writes stay at shallow depth in `sink_end` (deep writes from
   the decode callback corrupt the volume).
3. **THREE non-relocatable staging blocks crash the Memory Manager.**
   The clincher for two-fork files: staging the data fork and the resource
   fork in *two separate* `NewPtr` blocks — a third non-relocatable block
   alongside the archive buffer — reliably corrupts System 6's Memory
   Manager and kills the app with a wild-PC-jump bomb ("coprocessor not
   installed" / "illegal instruction"). A single-fork file (two blocks
   total: archive + one staging buffer) is flawless, and total memory is
   not the issue (a 63 KB resource-only file in two blocks works; a 43 KB
   two-fork file in three blocks crashes). **Fix: hold BOTH forks in ONE
   contiguous block** (data region then resource region) — block count
   stays at two, exactly like the working single-fork case. Confirmed on
   real Mini vMac (app idles, no bomb, where two blocks bombed).

### Why the fix is proven correct (not just "no crash")
The single-shared-block staging path (`mac/unclassic_mac.c`, forced on in
tests via `UNC_MAC_FORCE_SHAREBUF`) extracts **both forks byte-exact** for
four real two-fork fixtures (`3d_windows.sea`, `compact-pro-134`,
`ACInfo_Comm.sit`, `bitmap11.sit`) under ASan+UBSan *and* `qemu-m68k` —
`sh tests/run_mac_sink.sh`, in CI, covering the file-backed IO path and
the RAM-slurp `xio_*` path. So the real-Mac result (app idles, no bomb) +
the byte-exact off-Mac proof together establish that two-fork files
extract correctly.

### Ruled out during the two-fork investigation
engine logic; endianness; the RAM-slurp/`xio_*` path; buffer bounds (ASan
clean); stack overflow (call chain < 4 KB; 24 KB `SetApplLimit` bump);
`SetEOF` pre-allocation; fork write ORDER (resource-first is worse — it
corrupts the volume); `FlushVol` placement; a fully streaming
write-as-you-decode variant (deep writes corrupt the volume harder);
startup order; total memory. The distinguishing variable was the *number*
of simultaneous non-relocatable staging blocks — three vs two.

### Test-harness artifacts found along the way (not app bugs)
- **`pkill` racing Mini vMac's lazy disk write-back.** Mini vMac commits
  its disk image to the backing file on its own schedule, not per-write;
  killing the emulator can lose the just-written output. This makes
  headless output verification flaky (the crash vs. no-crash screenshot
  is the reliable real-Mac signal; byte-exactness is proven off-Mac). A
  real user quits cleanly, which flushes — a non-issue in production.
- **boot.dsk degrades over repeated boot+`pkill` cycles** (unclean
  shutdowns corrupt System 6's writes to it); a first boot of a fresh
  image is slow (Desktop DB rebuild). Both perturb click timing and made
  early results look non-deterministic. Re-copy a pristine boot image for
  reliable runs.

### Fallback still present (rare case)
If a two-fork entry's fork sizes are *unknown* up front (can't pre-size a
shared block), the Mac build keeps only the larger fork and reports the
entry partial — avoiding a two-block allocation. Every format that
produces two-fork files here reports known sizes, so the shared-block
path is what actually runs. Mock/Linux builds always use per-fork blocks
(no bug there).

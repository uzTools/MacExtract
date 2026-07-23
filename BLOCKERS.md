# BLOCKERS.md

## M10 Mac shell — single-fork extraction WORKS; two-fork files degrade

**Status:** Largely RESOLVED. The Mac app now runs under Mini vMac
(System 6.0.8, 4 MB) and extracts real Classic-Mac files correctly. One
narrow limitation remains for files that carry BOTH a data fork and a
resource fork (below). The engine and Linux CLI (M0–M9) are unaffected
and fully green.

### What works on a real emulated Mac (verified in Mini vMac)
Driven headlessly through a self-extracting autotest build
(`-DUNC_MAC_AUTOTEST`, see `tools/` / `MANUAL_TESTS.md`), extracting to
an HFS volume and diffing the on-disk forks against the oracle manifests:

- **Data-fork files** come out **byte-exact** (e.g. a 40 KB HyperCard
  stack: full data fork matches the manifest SHA-256).
- **Resource-fork files** (INITs, cdevs, FKEYs, control panels — the
  bulk of Classic-Mac software) come out correct too: the resource data
  and resource map match byte-for-byte, and type/creator/Finder-flags/
  dates are set. The ONLY bytes that differ are in the resource fork's
  "reserved for system use" header area (offsets 16–127), which a real
  Mac's Resource Manager stamps with machine/session-specific data (a
  current timestamp among them). No off-Mac tool can reproduce that, so
  a byte-exact manifest comparison of the reserved area is *expected* to
  differ; the actual resources are intact.

### The two root causes that were found and fixed
1. **`mio_seek` treated `eofErr` as failure.** `SetFPos` past/at EOF
   returns `eofErr` while still positioning at EOF; the seek helper
   turned that into a hard `UNC_ERR_IO`, so extraction reported I/O
   failure. Fix: treat `eofErr` as success (it is — a following read
   just returns 0). The Linux mock never caught this because its `lseek`
   allows seeks past EOF; the mock's `SetFPos` now mimics the real Mac.
2. **Reads returned zeros when output writes interleaved.** On a real
   Mac, reading the input archive while the sink creates/extends output
   files on the SAME HFS volume corrupts the reader's file mark — input
   reads start returning zeros mid-extraction. Fix: **slurp the entire
   archive into RAM once, up front, then decode from a memory buffer**
   (`MemIO`/`xio_*` in `mac/unclassic_mac.c`). No File Manager read is
   ever interleaved with a write. Archives targeted here are small, so
   this is cheap. (Deep writes from inside the decode callback also
   corrupt the volume, so all output writes stay at shallow depth in
   `sink_end`, from RAM staging buffers.)

### The remaining limitation: two-fork files
Writing BOTH forks of one new file — stage the data fork and the
resource fork in two RAM buffers, then open/write/close the data fork
and open/write/close the resource fork — reliably corrupts System 6's
Memory Manager: the app dies with a bad-opcode system error
("coprocessor not installed" / "illegal instruction" — a wild PC jump
from a clobbered return address / heap zone), or the HFS catalog is left
unreadable. It is the presence of **two large simultaneous `NewPtr`
staging blocks** (alongside the archive buffer) that triggers it —
writing either fork ALONE is flawless, and a resource-fork-only file up
to 31 KB extracts perfectly.

**This is NOT a logic bug.** The identical sink code — both forks, same
fixtures — is byte-exact under ASan+UBSan and under `qemu-m68k` (real
big-endian 68000), via `tests/mac_sink_test.c` (`sh
tests/run_mac_sink.sh`, in CI), covering both the file-backed IO path
and the RAM-slurp/`xio_*` path (`ram` mode). No Linux allocator, no
sanitizer, and no big-endian emulation reproduces it — only the real
System 6 Memory Manager does.

**Graceful fallback (shipped):** for a file with two non-empty forks the
Mac build keeps only the LARGER fork (the primary content — resource
fork for most applications, data fork for most documents), staging a
single buffer, and reports the entry as partial. This keeps the app
alive (no crash, no volume corruption) so the other entries in a
multi-file archive still extract. The mock/Linux builds — which have no
such bug — keep both forks (the fallback is `#ifndef UNC_SINK_TEST`).

### Ruled out by bisection (for the two-fork case)
engine logic; endianness; the RAM-slurp/`xio_*` path; two-buffer bounds
(ASan clean); stack overflow (call chain < 4 KB; a 24 KB `SetApplLimit`
bump present); `SetEOF` pre-allocation; fork write order (resource-first
is worse — it corrupts the volume); `FlushVol` placement; File-Manager
call depth (a fully streaming write-as-you-decode variant corrupts the
volume even harder); startup order; freeing the data buffer before the
resource write. Every off-Mac reproduction of the exact code is clean.

### Test-harness artifacts found along the way (not app bugs)
- **`pkill` racing Mini vMac's disk commit.** Killing the emulator right
  after the app idles can lose the just-written catalog if no further
  activity touches that volume. The autotest writes a `DONE` marker to
  the output volume after extracting, which forces the commit before the
  kill. (A real user quits cleanly, which flushes — a non-issue in
  production.)
- **boot.dsk degrades over repeated boot+`pkill` cycles** (unclean
  shutdowns corrupt System 6's writes to it); a first boot of a fresh
  image is slow (Desktop DB rebuild). Both perturb click timing and made
  early results look non-deterministic. Re-copy a pristine boot image
  for reliable runs.

### Next steps (a session with MacsBug / a 68k debugger)
- Break on the bomb for a two-fork file; inspect PC, the exception
  frame, and the application zone header at the point of corruption.
- Determine whether a File-Manager access-path/volume-buffer allocation
  collides with one of the two `NewPtr` staging blocks, and whether a
  single locked low-heap pool (instead of two mid-heap blocks) or
  private File-Manager buffers let both forks write.

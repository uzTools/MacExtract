# BLOCKERS.md

## M10 Mac shell — disk-write heap corruption (open)

**Status:** BLOCKED (needs MacsBug / a Mac debugger). Does not affect
the Linux engine or CLI (M0–M9, all green).

**Symptom:** on a real emulated Mac Plus (Mini vMac 36.04, System
6.0.8, 4 MB), extracting a `.sit` crashes when the shell writes decoded
fork data to disk. Manifests non-deterministically as a Sad Mac
(dsMemFullErr=25 despite 3.8 MB free → Memory-Manager-detected heap
corruption) or an F-line "coprocessor not installed" bomb.

**What is verified working** (same environment): app launch, full
Toolbox UI, `unc_sniff` format detection, the decompression engine
(test-only mode: full decode + in-engine CRC pass → "Extraction
complete"), file creation, and `PBSetCatInfo` type/creator/date
metadata.

**Bisection performed:**
- test-only (decode, no writes): OK → engine decodes correctly on 68000.
- write with FSWrite skipped (HOpen/HOpenRF only): OK → not HOpen.
- write with FSWrite: crashes → the write is the trigger.
- guard-byte tracking allocator over the engine's blocks: never trips,
  and the extra padding masks the crash → NOT an engine buffer overrun
  (consistent with Linux ASan/UBSan cleanliness across 769 fixtures).
- 256 KB SetApplLimit stack bump: no help → not stack overflow.
- FSWrite prototype checked against the Multiversal interfaces: matches.
- 5 MB HD image (vs 800 KB floppy): crashes identically → not floppy/
  interleaved-IO specific.
- Any NoteAlert inserted before the read, or allocator padding, masks
  it → layout-dependent memory corruption.

**Next steps (for a session with MacsBug):** break on the Sad Mac,
inspect PC/registers/A5 world and the zone header at the point of
corruption; check whether a File-Manager access-path buffer allocation
is colliding with an engine NewPtr block, and whether the engine's
callback re-entry (sink->write from deep in the decode) is the trigger.
Candidate fixes to try: pre-allocate a single locked engine pool low in
the heap (avoid fragmenting the zone with a 64 KB NewPtr mid-heap);
buffer each fork and write it after decode (shallower call depth);
raise the Retro68 stack via a linker/runtime setting rather than
SetApplLimit.

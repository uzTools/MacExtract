# BLOCKERS.md

## M10 Mac shell — disk-write crash on real Mac OS (open, environmental)

**Status:** BLOCKED on the real Toolbox environment (needs MacsBug).
The engine and the Mac glue's C logic are both PROVEN correct; the
Linux engine and CLI (M0–M9) are unaffected and fully green.

### Symptom
On a real emulated Mac Plus (Mini vMac 36.04, System 6.0.8, 4 MB),
extracting a `.sit` crashes when the shell writes the decoded fork data
to disk. Non-deterministic: Sad Mac dsMemFullErr (=25, despite 3.8 MB
free → Memory-Manager-detected heap corruption), or an F-line
"coprocessor not installed" bomb, or an "illegal instruction" bomb —
i.e. a wild PC jump / corrupted heap zone whose exact victim depends on
heap layout (any NoteAlert, allocator padding, or code change masks it).

### What is PROVEN CORRECT (deterministic, off-Mac)
- **The engine on big-endian 68000:** all 769 oracle fixtures extract
  byte-exact under `qemu-m68k` (a real big-endian m68k target). No
  endianness bug, no decode bug.
- **The Mac shell's sink/allocator/io C code on big-endian 68000:**
  `tests/mac_sink_test.c` compiles the ACTUAL `mac/unclassic_mac.c`
  sink against the real engine through a Linux-backed mock Toolbox and
  extracts a spread of fixtures (several StuffIt methods, nested CPT
  folders, Arsenic, PackIt, tar) byte-exact — both natively under
  ASan+UBSan and under `qemu-m68k` (`sh tests/run_mac_sink.sh`, in CI).
- On the real Mac, the engine DECODES correctly too: test-only mode
  (decode + in-engine CRC verification, no writes) reports "Extraction
  complete", and file creation + `PBSetCatInfo` metadata work.

### Ruled out by bisection
engine logic; endianness; uninitialized heap (NewPtrClear no help);
stack overflow (256 KB SetApplLimit bump no help); FSWrite signature;
floppy vs 5 MB HD (identical); SetEOF pre-allocation; File-Manager-call
depth (a shallow-write staging variant AND a fully trap-free deep
callback both still crash); the progress dialog (removing it entirely
still crashes). Native ASan/UBSan, `-fsanitize=alignment`, Valgrind
(`--track-origins`), the `-m32` build, and `qemu-m68k` are ALL clean.

### Conclusion
The defect is in the interaction with the real classic Mac OS runtime
(Toolbox traps / Memory Manager heap zone / Retro68 loader), which no
Linux tool, sanitizer, or mock reproduces — every off-Mac reproduction
of the actual code is byte-exact. It is not a logic bug in either the
engine or the sink.

### Next steps (a session with MacsBug / a 68k debugger)
- Break on the Sad Mac; inspect PC, the exception stack frame, and the
  application zone header at the point of corruption.
- Check whether a File-Manager access-path/volume-buffer allocation is
  colliding with an engine `NewPtr` block, and whether the crash is on
  the first output `FSWrite`/`HOpen` or a later one.
- Candidate fixes to try under the debugger: pre-allocate a single
  locked engine pool low in the zone (avoid fragmenting it with a 64 KB
  `NewPtr` mid-heap); give the File Manager private access-path buffers;
  or raise the Retro68 stack via a linker/runtime setting.

Durability fix already applied: `FlushVol` after extraction (output was
being lost on non-clean exit).

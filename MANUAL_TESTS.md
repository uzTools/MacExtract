# MANUAL_TESTS.md — what only a person with real hardware can settle

**Status: none of it has been done.** No physical Macintosh has ever run this
application. Everything the repository claims was observed under emulation —
Mini vMac for System 6.0.8 and 7.0.1, QEMU for Mac OS 9.2 — and emulation is
evidence, not proof.

This file is the to-do list for whoever has the machines. Each item says what
to do, why no emulator here can answer it, and what to record. Nothing below
is a known failure; it is unverified, which is a different thing.

Everything that *can* be automated already is, and lives elsewhere:

| you want | look in |
|---|---|
| how the automated suites work, and what each cannot see | `TESTING.md` |
| how to re-run an emulator harness or a `-D` probe | `tools/vmac/README.md` |
| what currently passes, tier by tier | `BLOCKERS.md` (status table) |
| per-fixture numbers, peak heap, timings | `FORMATS.md` |
| why something is built the way it is | `DECISIONS.md` |

---

## Before you start

- **Get the application.** `dist/` holds a built `unclassic.dsk` (an 800K
  floppy image) and a MacBinary `unclassic.bin`; both are committed so a person
  with an old Mac and no compiler can download one. `dist/unclassic.dsk` is
  confirmed to mount on System 6.0.8 (`tools/vmac/mountcheck.py`, 2026-08-01) —
  under emulation, which is exactly the kind of claim this file exists to
  re-test.
- **Bring archives over as MacBinary (`.bin`).** ImportFl or similar drops the
  wrapper; unclassic itself can unwrap MacBinary if the file arrives with a
  flattened fork.
- **Use archives whose contents you can check.** Anything in
  `fixtures/SOURCES.md` has a committed manifest, so what should come out is
  known byte for byte.
- **Write down the machine.** Model, ROM, System version, installed INITs and
  free memory at launch. Most of what makes silicon differ from an emulator is
  in that list.

---

## 1. A real Mac Plus, System 6.0.x, 1 MB — the floor target

This is the machine the project is designed around, and the one where an
emulator is least trustworthy. Do these first.

- [ ] **Free heap on a stock machine.** Record `FreeMem()` at launch (the
      application reports its budget) and compare with the ~678,392 B the
      emulated 1 MB machine leaves. The emulated figure comes from a stripped
      System Folder with no INITs; a real Plus with a Chooser extension or two
      has less, and every 1 MB number in FORMATS.md is derived from that
      budget.
- [ ] **A real 800K floppy, end to end.** Extract from a floppy onto a floppy.
      Emulated disks are host files: they never seek, never fail and never run
      out mid-write.
- [ ] **A media error during a write.** Use a marginal or deliberately damaged
      disk, or fill the volume. The engine's per-entry I/O error path has never
      seen a genuine I/O failure — only injected ones. What should happen: that
      entry fails with an alert, the partial file is removed, the application
      stays alive and continues with the next entry.
- [ ] **A full disk.** Extract something larger than the free space. Same
      expectation as above; no crash, no hang.
- [ ] **The stack against a real 8 KB.** The application bumps `SetApplLimit`
      and the engine promises a call chain under 4 KB. On silicon the ROM's own
      stack use sits underneath it. Extract a deeply nested archive (a `.cpt`
      with folders, e.g. `derived-Education7.1.cpt`) and confirm no crash.
- [ ] **Address errors.** A real 68000 traps unaligned word access; x86 and the
      emulator tolerate patterns it would not. CI's `-fsanitize=alignment` and
      the qemu-m68k mock are the current defence and neither is the CPU. Any
      bomb box with an address-error ID here is a genuine finding — record the
      fixture and the ID.
- [ ] **The Finder afterwards.** Quit and relaunch the Finder, then launch
      another application. `FreeMem()` returning to its starting value is
      checked in-app, never across a real quit.
- [ ] **Timing sanity.** Time two or three extractions with a watch and compare
      with the 1x table in FORMATS.md (e.g. `derived-EmpireBuilderDemo.sit`,
      278 KB, ~134 s). Those figures come from an emulator built for 7 MHz, not
      from a 7 MHz machine.
- [ ] **StuffIt 5 / Arsenic at 1 MB.** `derived-a2basic.dmg.sit` and
      `derived-Library_ISBN_Barcoder.sit` are the two that need the sampled
      inverse BWT, and take ~16 and ~32 minutes of Mac Plus time (FORMATS.md
      has both paths timed at 1x). They pass
      under emulation at 1 MB; on a real machine the budget will be smaller.
      A clean per-entry refusal is an acceptable result and a crash is not.

## 2. Another real 68k Mac (SE, Classic, II, LC…)

The same binary must run unchanged through the range. Different ROM, different
Toolbox revisions, sometimes a different CPU.

- [ ] **Launch and extract on a 68020/030/040 machine.** Alignment and
      instruction-timing assumptions that a 68000 hides can appear here.
- [ ] **System 7 with MultiFinder in the background.** Start a long extraction
      and switch to another application: it must stay responsive and the
      extraction must finish (the `WaitNextEvent` path).
- [ ] **The `SIZE` partition on a small machine.** 4 MB preferred / 400 KB
      minimum is in `mac/unclassic.r`. Set the application's memory low in Get
      Info and confirm a large Arsenic entry is refused per entry with an
      alert, rather than the application failing to launch.

## 3. Real PowerPC hardware, Mac OS 9

Verified under QEMU only, through the 68LC040 emulator.

- [ ] **Launch and extract on silicon.** Same checks as above.
- [ ] **Onto HFS+.** Extraction onto an HFS+ volume passes under emulation;
      confirm on a real one.
- [ ] **Names HFS+ permits and HFS does not.** Through the classic File Manager
      a 68k application is capped at 31 characters on either filesystem, so
      these may be unreachable from this binary at all. Unproven either way —
      an archive with long names would settle it.
- [ ] **Files larger than the HFS 2 GB cap**, against the engine's 32-bit-only
      arithmetic. Nothing in the corpus is that big.
- [ ] **8-bit MacRoman names on screen.** The bytes are checked everywhere; how
      they *look* above System 6 is not. `derived-Education7.1.cpt` has a
      `spinning brain ƒ` folder and PackIt's synthetic fixtures have `Appé`.

## 4. The interactive application, on any real machine

Emulation has driven all of this on System 6.0.8 end to end — launch by
double-click, SFGetFile with volume navigation, the progress dialog, Cancel,
Cmd-., partial-output cleanup, the result alert, and an extracted `APPL`
launching (`tools/vmac/interactive.py --e2e`). Re-doing it by hand is worth one
pass per machine, because a person notices what a screenshot comparison does
not.

Launch and UI
- [ ] Application launches; SFGetFile appears immediately.
- [ ] Cancel in SFGetFile quits cleanly to the Finder.
- [ ] Standard File's Drive button switches volumes and back.
- [ ] The progress dialog repaints when covered and uncovered — on System 6,
      by opening a desk accessory over it.
- [ ] The Cancel button stops extraction in under a second: completed entries
      remain, the entry being written is deleted rather than left truncated,
      and the application returns to SFGetFile undamaged.
- [ ] Cmd-. behaves exactly like the Cancel button.

Extraction correctness
- [ ] A classic `.sit` (methods 2 and 13 mixed): every file appears, sizes
      correct, type/creator and icons right in the Finder, dates preserved.
- [ ] A `.cpt` with nested folders: the folder tree is recreated.
- [ ] A `.hqx` and a `.bin`: one file with both forks; ResEdit or Get Info
      confirms the resource fork is intact.
- [ ] A file whose name contains `/`: it appears with the `/` in the Finder
      (the engine's `:` substitution undone).
- [ ] Extract the same archive twice into the same folder: `name~1` copies, no
      overwrite, no crash.
- [ ] An archive with a member name over 31 characters (zip or tar): truncated
      to 31, extraction completes.
- [ ] A truncated `.sit`: per-entry error alert, application stays alive.
- [ ] A random file renamed `.sit`: "could not be extracted" alert.

## 5. Things the resource fork and the Toolbox promise

- [ ] **`SFReply.vRefNum` on System 7 and later** is a working-directory
      reference and is passed with `dirID` 0. Confirm output lands next to the
      archive, not in the volume root, on both System 6 and Mac OS 9.
- [ ] **The progress dialog uses `DialogSelect` without a filterProc.** Confirm
      the Cancel button highlights when clicked.

---

## What a failure here would change

Worth knowing before you start, so a surprising result is recorded rather than
worked around:

- A smaller real 1 MB budget moves every figure in FORMATS.md's floor-target
  table, and could reopen the StuffIt 5 / Arsenic capability gap that closed on
  2026-08-07.
- A genuine I/O failure exercising the per-entry error path would close the
  oldest untested branch in the Mac shell.
- An address error on real silicon would invalidate the 68000 discipline claim
  in CLAUDE.md, which is currently defended by a sanitizer and an emulator.

Send anything surprising to `BLOCKERS.md` with a reproduction, and the numbers
to `FORMATS.md`. **A result from silicon outranks every emulated figure in this
repository.**

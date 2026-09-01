# MANUAL_TESTS.md — what only a person outside this machine can settle

**Status: none of it has been done.** No physical Macintosh has ever run this
application. Everything the repository claims was observed under emulation —
Mini vMac for System 3.0, 6.0.8 and 7.0.1, QEMU for Mac OS 9.2 — and emulation is
evidence, not proof.

This file is the to-do list for whoever has what this machine does not — the
hardware (§1–§5, §7), a copy of the software (§6), or an account to post
from (§8). Each item says what to do, why nothing here can answer it, and what to
record. Nothing below is a known failure; it is unverified, which is a
different thing.

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

- **Get the application.** `dist/` holds a built `MacExtract.dsk` (an 800K
  floppy image) and a MacBinary `MacExtract.bin`; both are committed so a person
  with an old Mac and no compiler can download one. `dist/MacExtract.dsk` is
  confirmed to mount on System 6.0.8 (`tools/vmac/mountcheck.py`, 2026-08-01) —
  under emulation, which is exactly the kind of claim this file exists to
  re-test.
- **Bring archives over as MacBinary (`.bin`).** ImportFl or similar drops the
  wrapper; MacExtract itself can unwrap MacBinary if the file arrives with a
  flattened fork.
- **Use archives whose contents you can check.** Anything in
  `fixtures/SOURCES.md` has a committed manifest, so what should come out is
  known byte for byte.
- **Write down the machine.** Model, ROM, System version, installed INITs and
  free memory at launch. Most of what makes silicon differ from an emulator is
  in that list.

---

## 1. A real Mac Plus, System 3.0 or 6.0.x, 1 MB — the floor target

This is the machine the project is designed around, and the one where an
emulator is least trustworthy. Do these first.

- [ ] **Free heap on a stock machine.** Record `FreeMem()` at launch and
      compare with the **678,956 B** the emulated 1 MB machine leaves
      (measured 2026-08-24, `-D UNC_AT_BUDGET`). Note which number you are
      comparing: the engine's BUDGET is that figure less the shell's 80 KB
      `kMemReserve`, i.e. **597,036 B**, and conflating the two is a mistake
      this project has already made and shipped (BLOCKERS.md). The emulated
      figure comes from a stripped System Folder with no INITs; a real Plus
      with a Chooser extension or two has less, and every 1 MB number in
      FORMATS.md is derived from that budget.
- [ ] **How much heap the Toolbox really needs while the engine is at its
      peak.** The reserve held back from the engine is a flat **20 KB**
      (`kMemReserveMin`/`Max` in `mac/macextract_mac.c`); it was 80 KB, then a
      quarter of `FreeMem()` clamped to [32 KB, 80 KB], then 32 and 24 KB, all
      within two days of measurement. **Contiguity is no longer the open
      question** — `MaxBlock()` at every dialog creation is essentially the
      whole free heap (FORMATS.md, *What the reserve is for*). What is left is
      VOLUME on iron, and specifically **a real floppy's File Manager buffers
      during writes**, which a RAM-backed emulated disk cannot produce. That is
      now the single measurement standing between this and a smaller reserve
      still. Measured under Mini vMac, the Toolbox and File
      Manager took **under 1 KB** at the tightest moment of all 67 sample
      fixtures — but that is a stripped System Folder with no INITs, a
      RAM-backed disk and no fragmentation. Do the same on iron with a
      Chooser extension loaded, extracting onto a **floppy** and onto an
      **AppleShare volume**, and watch whether anything comes close to the
      floor. If 32 KB is comfortable there, the floor can come down and
      every small-partition budget grows with it; if it is not, the floor
      needs raising and this is the only way anyone would find out.
- [ ] **MultiFinder at the declared minimum.** Set the partition to 400 KB
      in Get Info and open one archive of each format. The emulated figure
      is `FreeMem()` 211,960 B and a 158,970 B budget (FORMATS.md,
      *Budget*); a real machine has less, and this is the configuration a
      user can choose and the harness cannot default to.
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
- [ ] **The stack against a real 12 KB, and this one got much tighter on
      2026-08-31.** `kStackBump` now takes only 4 KB off `ApplLimit` on top of
      the 8 KB default, so the shell runs on **12 KB** where it used to have
      32 KB — 20,464 B went to the engine. The requirement was measured two
      ways and swept across seven stack sizes: the stack POINTER never goes
      deeper than **5,200 B** and the deepest byte ever written is
      **5,604 B** (FORMATS.md, *Stack*). **What that cannot see is silicon.**
      Every figure comes from an emulator with a stripped System Folder, no
      INITs and a RAM-backed disk; a real Macintosh runs ROM routines with a
      Chooser extension loaded, a floppy's drivers and a fragmented System
      heap underneath our frames, and one of those routines demonstrably
      sizes a stack buffer from the space available. Extract a deeply nested
      archive (a `.cpt` with folders, e.g. `derived-Education7.1.cpt`), a
      StuffIt 5 archive (the deepest decoder chain), and drive Standard File
      and the password dialog. A stack overflow here does not raise an error
      — it writes into the heap in silence — so the symptom to watch for is a
      wrong byte or a crash minutes later, not a message. If anything at all
      looks off, `UNC_STACK_BUMP_KB` rebuilds at any size and 8 KB or 12 KB
      of bump restores the old headroom.
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
      minimum is in `mac/macextract.r`. Set the application's memory low in Get
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
- [ ] **The application's icon at 16 COLOURS.** `icl4` and `ics4` are the two
      members of the icon family that nothing here can display, and it is a
      hard limit rather than a missing step (measured 2026-08-27): the QEMU
      `mac99` guest offers exactly one colour depth — its Monitors control
      panel lists "Millions" and greys out "Grays" — and booted at
      `-g 1024x768x4` it does not reach the Finder at all, stopping in
      OpenBIOS. Mini vMac is a 1-bit Mac Plus. So the 1-bit and 8-bit members
      are photographed (DECISIONS.md 2026-08-24, *the icon*) and the 4-bit
      pair needs a screen set to 16 colours on real hardware, or an emulator
      with a 4-bit video mode.

## 4. The interactive application, on any real machine

Emulation has driven all of this on System 6.0.8 end to end — launch by
double-click, SFGetFile with volume navigation, the destination dialog (both
"beside the archive" and "another volume"), the progress dialog, Cancel,
Cmd-., partial-output cleanup, the result alert, and an extracted `APPL`
launching (`tools/vmac/interactive.py --e2e`). Re-doing it by hand is worth one
pass per machine, because a person notices what a screenshot comparison does
not.

Launch and UI
- [ ] Application launches; SFGetFile appears immediately.
- [ ] Cancel in SFGetFile quits cleanly to the Finder.
- [ ] Standard File's Drive button switches volumes and back.
- [ ] The destination dialog opens in the archive's own folder, and Return
      puts the files there. Cancelling it returns to SFGetFile, not to the
      Finder.
- [ ] **A disk swap in ONE drive.** Inserting the disk holding the missing
      part answers the "part N has not been found" alert by itself, and that
      is driven under emulation (`interactive.py --diskswap`) — but Mini vMac
      inserts each image into a NEW drive, so every insertion there has a
      different drive number. A Mac Plus has one floppy drive: the user
      ejects and re-inserts, and the second disk arrives on the drive the
      first one used. The shell keys off the drive number in the event, so
      this should work; nothing here can show that it does.
- [ ] The destination dialog's prompt is not clipped by the machine's font.
      It is one fixed-width static text item and it does not wrap; the
      wording was shortened once already for exactly this (DECISIONS.md).
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

## 6. A file that SpaceSaver itself wrote

This one is not about the application at all — it is the last gap in a
FORMAT, and it needs a copy of StuffIt SpaceSaver driven by a person.

- [ ] **Compress one file with SpaceSaver and send the result**, along
      with the original. Any version, any Macintosh, real or emulated.
      A file of a few KB is enough; two, one with a resource fork, is
      better.

**Why nobody here can do it.** SpaceSaver 3.5.1 installs and runs under
Mini vMac, its control panel opens, and *SpaceSaver Info…* reports
correctly on a selected file — but every path that would WRITE a
compressed file declines in silence: the `small` keyword on a file name
or on the disk, Magic Menu's *SpaceSaver Compress*, *Idle Now* with the
volume enrolled, and DropCompress. In the same boots, StuffIt Deluxe's
own *Archive via Rename* fires every time, so the machine is healthy and
the Finder events arrive. Roughly twenty emulator runs; what is
eliminated and what is left is in `OPEN_ITEMS.md` and `BLOCKERS.md`.

**What it would settle.** Every SpaceSaver CODEC is already graded
against Aladdin's own modules, which run on Linux under `qemu-m68k`
(`tools/ssmodule/`) — methods 0, 1, 2, 3 and 4 all decode byte-exact.
What has never been checked against a real file is the CONTAINER: the
method the application picks for the machine it runs on, the data fork's
length rounded up to 256 bytes, the 84-byte header, and the type,
creator and Finder flags it moves aside. Those are read from containers
this project builds itself.

**What to record.** The file, the original, the SpaceSaver version, and
the Macintosh it ran on (a 68030 or better writes method 3, a 68000
writes method 4 — so the CPU decides what the specimen exercises).
`tools/run_spacesaver.py` grades a `.ss` against a `.orig` placed beside
it in the emulator's specimen directory.

---

## 7. A Macintosh 512K with a Hard Disk 20

**A Macintosh 128K cannot run this and is not what this section asks for.**
Measured 2026-09-01: the same volume that reaches Standard File on a 512K
bombs `ID = 03` on a 128K, whose largest single block is 63,744 B against the
142,152 B of `CODE` the engine lives in (FORMATS.md, *A Macintosh 128K*). The
machine below is a **512K**, with 512 KB of RAM behind its 64 KB ROM.

**Why nothing here can answer it: Mini vMac does not emulate the Hard Disk
20.** Apple's own *HD 20 Startup* disk boots on the emulated 512Ke and stops
on the emulated 512K at an empty dialog frame nothing dismisses, so the one
configuration that would settle this cannot be booted (FORMATS.md, *A true
Macintosh 512K*).

**Why it is worth someone's afternoon.** On a 64K-ROM machine this application
is two calls away from working, and only one of them is ours:

- `MaxApplZone` is `[Not in ROM]` (Inside Macintosh II-30) and Retro68 emits
  it as a trap. **Skip it and the application runs**: measured on the emulated
  512K under Apple's MFS System 3.0 — Standard File opens, a file is chosen,
  the destination dialog appears, a non-archive is opened, sniffed and
  correctly refused with *"This file could not be extracted."*
- Extracting a real archive then bombs `ID = 12` at an HFS call — and HFS is
  exactly what the `Hard Disk 20` file supplies on these machines.

**Take `dist/` from the branch `rom64k`**, which is what makes this askable at
all: there `Has128KROM()` guards `MaxApplZone`, so `dist/MacExtract.bin`
starts on a 64K ROM and its Standard File interface works (measured under
emulation). No toolchain needed. `main`'s download bombs on arrival on those
machines, by design — see `BRANCH_NOTES.md` on the branch.

**What is and is not already known**, because the branch starting is easy to
read as the branch working:

| configuration | status |
|---|---|
| 64K ROM, floppies only | **starts, interface works, cannot extract** — a real archive bombs `ID = 12` on an HFS call. Measured under emulation |
| 64K ROM **with an HD20 and its driver** | **unknown, and the reason this section exists.** Apple says the HFS is there: the HD20 start-up software "contains a device driver for this drive and the hierarchical (128K ROM) version of the File Manager" (Inside Macintosh IV, *The Floppy Disk Interface*) — so the call that bombs should exist on that machine |
| 64K ROM with the `Hard Disk 20` file but no drive | unknown; under emulation that file hangs the machine at an empty dialog, which is probably the driver hunting for hardware Mini vMac does not have — *hypothesis* |

So the test is: put `dist/MacExtract.bin` on an **MFS floppy** —
`tools/vmac/mkmfs.py` builds one, or copy it across on any Mac that reads
both — boot a Macintosh 512K **with a Hard Disk 20 attached**, open an
archive and extract it to the HD20. An 800K HFS floppy is fair game too on
such a machine, since the same start-up software drives an external
double-sided drive attached through the HD20. Record: does it extract; if it bombs, the
ID and what was on screen; and what the extracted files' sizes and dates look
like beside the same archive extracted anywhere else.

**A pass would not by itself move the floor.** One machine is one machine, and
what it would establish is that the HFS the `Hard Disk 20` file installs is
enough for this application — after which the tiers in BLOCKERS.md would still
have to be re-run before the claim went into README.md.

## 8. Two bug reports, written and not posted

Neither needs a Macintosh — they need an account. Both are reduced to a
reproduction and written up ready to send; what is missing is somebody to post
them, because an unauthenticated POST to either issues API returns 401 from
here. **No session working in this repository should submit them** (CLAUDE.md,
Rules): they go from the maintainer's own account.

- [ ] **XADMaster reads one byte past a DDn fork's declared compressed
      length.** Swept 0,1,2,4…64 and it flips at 1; reduced to a 1,166-byte
      reproduction. Text and repro generator: `tools/xadmaster-ddn-repro/`
      (`ISSUE.md`, `make_repro.py`). Upstream is MacPaw/XADMaster. What that
      byte is worth here is in FORMATS.md; the adjudication it unblocked was
      M21.
- [ ] **Retro68's `_OpenDF` trap is System 7 and neither wrapper falls back.**
      `OpenDF`/`HOpenDF` do not fall back to a plain open on `paramErr`, so
      both are unusable on System 6, where `FSOpen` in the same file does fall
      back. Measured as cases 8 and 11 of `tools/retro68-hopen-repro/`; text in
      that directory's `ISSUE.md`. Upstream is autc04/Retro68. **Note the
      history before writing anything further:** an earlier attribution of the
      M10 write-path failure to a broken `HOpen` was withdrawn (BLOCKERS.md),
      and this report is the narrower claim that survived it.

**What to record.** The issue URL, in `BLOCKERS.md` beside the claim it
belongs to. If either is rejected or explained upstream, that is a withdrawn
claim and goes in the same file with what it cost.

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

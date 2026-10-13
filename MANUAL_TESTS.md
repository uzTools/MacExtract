# MANUAL_TESTS.md — what only a person outside this machine can settle

**Status: one machine on silicon.** The maintainer's LC 475 (68LC040,
System 7.6.1, 12 MB) ran two sessions, 2026-10-11 and 2026-10-12; its
results are BLOCKERS.md's (*Status*), and what it found open is
OPEN_ITEMS.md's (*What the LC 475 found that is not fixed*). Nothing older
has run the application. Everything else here was observed under Mini vMac
(System 3.0, 6.0.8, 7.0.1) or QEMU (Mac OS 9.2): evidence, not proof.

Each item below says what to do and what to record. Nothing below is a
known failure; it is unverified. **Before adding an item, ask what the
emulator would have to be handed, and search for the file by its bytes** —
twice an item here turned out to need neither hardware nor a stranger
(BLOCKERS.md, *Withdrawn claims*: SpaceSaver, AppleLink).

| you want | look in |
|---|---|
| how the automated suites work, and what each cannot see | `TESTING.md` |
| how to re-run an emulator harness or a `-D` probe | `tools/vmac/README.md` |
| what passes, tier by tier, silicon included | `BLOCKERS.md` (*Status*) |
| per-fixture numbers, peak heap, timings | `FORMATS.md` |
| why something is built the way it is | `DECISIONS.md` |

---

## Before you start

- **Get the application.** `dist/` holds `MacExtract.dsk` (an 800K floppy
  image) and a MacBinary `MacExtract.bin`.
- **Bring archives over as MacBinary (`.bin`)**, or over AppleShare, which
  keeps both forks and lets the result be graded from Linux (how round 2
  was graded).
- **Use archives whose contents you can check**: anything in
  `fixtures/SOURCES.md` has a committed manifest.
- **Write down the machine**: model, ROM, System version, INITs, free
  memory at launch.

---

## 1. A real 68000 Mac (Plus, SE, Classic), System 3.0 or 6.0.x, 1 MB — the floor target

The machine the project is designed around, and the one where an emulator
is least trustworthy. Do these first. The LC 475 cannot stand in: a
68020-and-up CPU performs the misaligned accesses a 68000 bombs on.

- [ ] **Free heap at launch.** Compare `FreeMem()` with the emulated 1 MB
      System 6.0.8 machine's **655,100 B** (budget 634,620 B after the
      20 KB reserve; FORMATS.md, *Budget*). The emulated figure has no
      INITs; every 1 MB number in FORMATS.md derives from it.
- [ ] **What the Toolbox takes at the engine's peak.** The reserve is a
      flat 20 KB (`kMemReserveMin`/`Max`, `mac/macextract_mac.c`); under
      Mini vMac the Toolbox took under 1 KB at the tightest moment
      (FORMATS.md, *What the reserve is for*). Repeat with a Chooser
      extension loaded, extracting onto a **floppy** and onto an
      **AppleShare volume**. Record the lowest free heap seen.
- [ ] **Floppy to floppy.** Extract from a real 800K floppy onto another.
- [ ] **A media error during a write.** A marginal disk. Expected: that
      entry fails with an alert, the partial file is removed, extraction
      continues. Only injected errors have reached this path. (A full disk
      is done: LC 475, round 2.)
- [ ] **The 12 KB stack.** Measured need is 5,604 B deepest byte written
      (FORMATS.md, *Stack*), under emulation only. Extract
      `derived-Education7.1.cpt` and a StuffIt 5 archive, and drive
      Standard File and the password dialog. An overflow is silent: watch
      for a wrong byte or a late crash. `UNC_STACK_BUMP_KB` rebuilds at any
      size.
- [ ] **Address errors.** A bomb with an address-error ID is a finding;
      record the fixture and the ID.
- [ ] **The Finder afterwards.** Quit, relaunch the Finder, launch another
      application.
- [ ] **Timing.** Time two or three extractions against FORMATS.md's 1x
      tables (*Measured on a 7 MHz Mac Plus*), e.g.
      `derived-EmpireBuilderDemo.sit`, 61 s at 4 MB.
- [ ] **StuffIt 5 at 1 MB.** `derived-a2basic.dmg.sit` (~6 min) and
      `derived-Library_ISBN_Barcoder.sit` (~12 min), on the sampled index. A per-entry refusal is
      acceptable; a crash is not.

## 3. Real PowerPC hardware, Mac OS 9

Verified under QEMU only.

- [ ] **Launch and extract.**
- [ ] **Onto HFS+.**
- [ ] **Names HFS+ permits and HFS does not.** The classic File Manager
      caps a 68k application at 31 characters, so this may be unreachable;
      an archive with long names settles it.
- [ ] **A file over 2 GB**, against the engine's 32-bit arithmetic.
      Nothing in the corpus is that big.
- [ ] **8-bit MacRoman names on screen**: `derived-Education7.1.cpt`'s
      `spinning brain ƒ`, PackIt's synthetic `Appé`.

## 4. The interactive application, on any real machine

Driven end to end under emulation on System 3.0 and 6.0.8
(`tools/vmac/interactive.py --e2e`). Done on the LC 475: launch, Cancel
in Standard File, Cancel and File ▸ Quit mid-run, the 31-character cut,
a `.cpt` tree, `.hqx`, `.bin`, a truncated `.sit`, a non-archive, zip and
StuffIt passwords, several archives opened at once, 24 archives byte-exact
with types, creators and dates (BLOCKERS.md, *Status*). Cmd-. on AZERTY is
open (OPEN_ITEMS.md, *What the LC 475 found*).

- [ ] Standard File's Drive button switches volumes and back.
- [ ] The destination dialog opens in the archive's own folder and Return
      puts the files there; Cancel returns to Standard File.
- [ ] The destination dialog's prompt is not clipped by the machine's
      font (one fixed-width static text item; it does not wrap).
- [ ] **A disk swap in ONE drive.** Part 1 on one floppy, the rest on
      another. Expected: the first floppy comes out by itself, the alert
      says *"…is not on that disk, so it was ejected"*, and putting the
      second floppy in finishes the set with nothing clicked. Measured
      under emulation (`interactive.py --diskeject`), but Mini vMac gives
      every insertion a new drive.
- [ ] **Several archives on a one-drive machine** with the application on
      its own floppy: the second archive should ask for that floppy back.
- [ ] The progress dialog repaints when a desk accessory covers it.
- [ ] Cmd-. on a US keyboard behaves like the Cancel button.
- [ ] A name containing `/` appears with the `/` in the Finder.
- [ ] The same archive twice into one folder: `Folder~1` / `name~1`, no
      overwrite (DECISIONS.md 2026-10-11, *the folder that is already
      there*).

## 5. Things the Toolbox promises

- [ ] **`SFReply.vRefNum`** is a working-directory reference passed with
      `dirID` 0: output lands beside the archive, not at the volume root,
      on System 6 and Mac OS 9.
- [ ] **The progress dialog's Cancel button highlights** when clicked
      (`DialogSelect`, no filterProc).

## 6. A Macintosh 512K with a Hard Disk 20

**Not a 128K**: that machine is out on its heap total (FORMATS.md, *A
Macintosh 128K*). Mini vMac does not emulate the HD20, so this cannot be
booted here (FORMATS.md, *A true Macintosh 512K*).

**Take `dist/` from the branch `rom64k`**, where `Has128KROM()` guards
`MaxApplZone`; `main`'s download bombs on a 64K ROM by design
(`BRANCH_NOTES.md` on the branch).

| configuration | status |
|---|---|
| 64K ROM, floppies only | starts, interface works, a real archive bombs `ID = 12` on an HFS call — measured under emulation |
| 64K ROM **with an HD20 and its driver** | **unknown — the test.** The HD20 start-up software supplies the 128K-ROM File Manager (Inside Macintosh IV, *The Floppy Disk Interface*) |
| 64K ROM with the `Hard Disk 20` file, no drive | unknown; hangs under emulation — *hypothesis*: the driver hunting for hardware |

**The test:** put `dist/MacExtract.bin` on an MFS floppy
(`tools/vmac/mkmfs.py`), boot a 512K with an HD20 attached, extract an
archive to the HD20. Record whether it extracts; if it bombs, the ID and
the screen; the output's sizes and dates. A pass would not by itself move
the floor — BLOCKERS.md's tiers would be re-run first.

## 7. Two bug reports, written and not posted

They need an account, not a Macintosh. **No session working in this
repository submits them** (CLAUDE.md, *Rules*); the maintainer posts them.

- [ ] **XADMaster reads one byte past a DDn fork's compressed length** —
      `tools/xadmaster-ddn-repro/` (`ISSUE.md`, `make_repro.py`), for
      MacPaw/XADMaster.
- [ ] **Retro68's `HOpen`/`HOpenRF`/`HOpenDF` leave `ioMisc` uninitialised**
      — `tools/retro68-hopen-repro/ISSUE.md`, for autc04/Retro68, with
      `iomisc_repro.c` inline. Re-verified against Retro68 master 2026-10-13. The
      `paramErr` claim it replaced is withdrawn (BLOCKERS.md).

**Record** the issue URL in BLOCKERS.md beside its claim. A rejection is a
withdrawn claim, filed with what it cost.

## 8. A release

`v0.40.0` (2026-10-11) is the newest tag, and `main` has moved past it in
`mac/` and `src/`; both builds report `0.40.0`, and only size and date tell
the downloads apart. Whether to cut a release is the maintainer's call
(CLAUDE.md, *Cutting a release*); the release page is visible only from
outside this machine.

---

## What a failure here would change

- A smaller real 1 MB budget moves every floor-target figure in FORMATS.md.
- A genuine I/O failure would exercise the shell's oldest untested branch.
- An address error on silicon would break the 68000-discipline claim,
  defended today by a sanitizer and an emulator.

Send anything surprising to `BLOCKERS.md` with a reproduction, and numbers
to `FORMATS.md`. **A result from silicon outranks every emulated figure.**

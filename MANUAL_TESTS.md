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
  image), `MacExtract-1440K.img` (a 1.44 MB one, §9) and a MacBinary
  `MacExtract.bin`.
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

Done on Mac OS 9.2.2, HFS+, 2026-10-14: launch, extraction onto HFS+, the
cut to 31 characters, 8-bit names in the Finder and Standard File
(BLOCKERS.md, *Status*).

- [ ] **A file over 2 GB**: refused as one entry, *"Big.bin is over 2 GB,
      too large here"*, since 2026-10-14 — measured under emulation only;
      the build before ended the run on *"The disk is full"* there
      (DECISIONS.md 2026-10-14, *the file the disk was too full for*).

## 4. The interactive application, on any real machine

Driven end to end under emulation on System 3.0 and 6.0.8
(`tools/vmac/interactive.py --e2e`). Done on the LC 475: launch, Cancel
in Standard File, Cancel and File ▸ Quit mid-run, the 31-character cut,
a `.cpt` tree, `.hqx`, `.bin`, a truncated `.sit`, a non-archive, zip and
StuffIt passwords, several archives opened at once, 24 archives byte-exact
with types, creators and dates, the destination dialog, other volumes
through Desktop, `/` in names, `~1` on a second run, a desk accessory over
the progress window, Cmd-. on a U.S. layout (BLOCKERS.md, *Status*). Cmd-. on AZERTY is
open (OPEN_ITEMS.md, *What the LC 475 found*).


## 5. Things the Toolbox promises

- [ ] **`SFReply.vRefNum`** is a working-directory reference passed with
      `dirID` 0: output lands beside the archive, not at the volume root,
      on System 6 (passed on 7.6.1 and Mac OS 9.2.2).

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

## 7. A bug report, written and not posted

It needs an account, not a Macintosh. **No session working in this
repository submits it** (CLAUDE.md, *Rules*); the maintainer posts it.

- [ ] **XADMaster reads one byte past a DDn fork's compressed length** —
      `tools/xadmaster-ddn-repro/` (`ISSUE.md`, `make_repro.py`), for
      MacPaw/XADMaster.

**Record** the issue URL in BLOCKERS.md beside its claim. A rejection is a
withdrawn claim, filed with what it cost.

## 8. A release

`v0.40.0` (2026-10-11) is the newest tag, and `main` has moved past it in
`mac/` and `src/`; both builds report `0.40.0`, and only size and date tell
the downloads apart. Whether to cut a release is the maintainer's call
(CLAUDE.md, *Cutting a release*); the release page is visible only from
outside this machine.

## 9. The 1.44 MB image, written with a USB floppy drive

`dist/MacExtract-1440K.img` is checked here only through hfsutils, which
reads it back byte-exact (`make_dist.sh`); no Macintosh has mounted it
(DECISIONS.md 2026-10-14, *the floppy a USB drive can write*).

- [ ] **Write it raw to a high-density disk** with a USB floppy drive
      (`dd`, or a raw image writer on Windows) and insert it in a
      SuperDrive Mac — the LC 475 has one. Record whether it mounts, and
      whether MacExtract dragged off it shows its own icon and runs.
- [ ] **Optional: the same at 720K**, on a double-density disk, from an
      image `hformat` makes at 737,280 B. Whether a SuperDrive mounts an
      HFS volume on a 720K MFM disk is a *hypothesis* either way; a yes
      would make a fourth image worth shipping.

---

## What a failure here would change

- A smaller real 1 MB budget moves every floor-target figure in FORMATS.md.
- A genuine I/O failure would exercise the shell's oldest untested branch.
- An address error on silicon would break the 68000-discipline claim,
  defended today by a sanitizer and an emulator.

Send anything surprising to `BLOCKERS.md` with a reproduction, and numbers
to `FORMATS.md`. **A result from silicon outranks every emulated figure.**

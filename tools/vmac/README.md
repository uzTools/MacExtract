# tools/vmac — running the Mac shell on an emulated Mac Plus

Everything in FORMATS.md and BLOCKERS.md that claims the Macintosh shell
"runs on real System 6" was produced by this harness — on an emulator.
MANUAL_TESTS.md is the complement: what only silicon can answer. It boots the Retro68
application on Mini vMac emulating a **68000 Mac Plus under System 3.0, System
6.0.8 or System 7.0.1**, extracts one fixture per boot, and cross-checks the
result against the same engine's Linux output.

    tools/vmac/setup.sh                                  # once
    tools/vmac/run.py fixtures/adobenumbers.sit          # 4 MB machine
    tools/vmac/run.py --mem 1M fixtures/adobenumbers.sit # 1 MB RAM floor
    tools/vmac/run.py --system Sys7.img ...              # the System 7 tier
    tools/vmac/sys30.py --mem 1M ...                     # the System 3.0 tier

`--system` picks the boot system: `System6.hfv` (6.0.8) or `Sys7.img` (7.0.1).
System 7 is where `SFReply.vRefNum` becomes a working directory and the Process
Manager starts honouring the `SIZE` partition, so it is a different set of code
paths. Run the System 7 tier at 4 MB.

**512 KB machines.** `--emu mv-512Ke` on either driver boots a Macintosh
512Ke, the smallest machine this application runs on: `sys30.py --emu
mv-512Ke` is **72/74** and `run.py --emu mv-512Ke --system System6.hfv` is
**68/74** on the shipped build, the refusals per entry and by name (the
current dates are BLOCKERS.md's, *Status*; FORMATS.md, *512 KB machines*).
With every decoder resident (`-D UNC_OVL_RESIDENT`) the two are **68/72** and
**63/72** (2026-10-09). The resident budgets measured are **205,476 B** and
**110,076 B**, re-taken on the machine 2026-10-09 evening with the floor's.
`tools/run_tiers.py` reproduces both lanes on all three tiers on Linux,
fixture for fixture and by name.

**A true Macintosh 512K — `mv-512K`, a 64 KB ROM — boots, and this
application bombs on it.** It cannot read HFS, which is the whole of the
negative; nothing here drives it as a tier, and `setup.sh` builds it and
fetches both 64 KB ROMs so the frames can be re-taken rather than quoted.
Everything below wants a display and is watched by eye. `$V` is
`$UNC_VMAC_HOME`.

    $V/mv-512K/minivmac -r $V/Mac512K.ROM $V/Sys30.img    # HFS:  Sad Mac 0F0064
    $V/mv-512K/minivmac -r $V/Mac128K.ROM $V/Sys30.img    # the other 64K ROM: identical
    $V/mv-512K/minivmac -r $V/Mac512K.ROM                 # no disk: blinking floppy, healthy
    $V/mv-512K/minivmac -r $V/Mac512K.ROM $V/Sys11.img    # MFS:  boots to Finder 1.1

**A Macintosh 128K — `mv-128K` — is too small to run it**, and that is the
RAM rather than the ROM: `ID = 03` on launch (FORMATS.md, *A Macintosh
128K*). `tools/vmac/memtest` measures the machine instead — it prints the
low-memory globals, then bisects the largest single `NewPtr` the heap will
grant, which is what the Segment Loader asks and `FreeMem` does not answer
(`FreeMem` reads 4,846 B on a 128K and a 512K alike; the zone grows on
demand). Build it by hand like `traptest`, put it on as `Finder`, read the
numbers off the screen, and run it on **both** machines — a number means
nothing until the same probe has produced a different one somewhere:

    cmake -B build/memtest -S tools/vmac/memtest \
          -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
    cmake --build build/memtest
    mkmfs.py --extract System $V/Sys30MFS.img /tmp/System30mfs.bin
    mkmfs.py $V/MemTest.img --boot $V/Sys30MFS.img --name "System Software" \
             /tmp/System30mfs.bin build/memtest/MemTest.bin:Finder
    $V/mv-128K/minivmac -r $V/Mac128K.ROM $V/MemTest.img
    $V/mv-512K/minivmac -r $V/Mac128K.ROM $V/MemTest.img

**What it cannot see:** it measures a machine with nothing else resident, so
its figures are a ceiling and not a budget — the application's own globals and
stack come out of the same span. It paints its own white ground, because
digits over the desktop's 50 % grey cannot be read back off a screenshot.

**`mkmfs.py` writes the MFS volumes**, because Retro68's `.dsk` is always
800K HFS. It builds, lists and extracts:

    mkmfs.py $V/AppMFS.img --name MacExtract dist/MacExtract.bin
    mkmfs.py --list $V/AppMFS.img
    mkmfs.py --extract System $V/Sys11.img /tmp/System11.bin

**Use System 3.0, not System 1.1**, and Apple's own MFS disk: `setup.sh`
fetches `Sys30MFS.img` by unpacking Macintosh Garden's `System_3.x.sit` with
this repository's CLI, and it boots the 64K-ROM machine straight off. A volume
built from `Sys30.img`'s HFS copies boots too — `hcopy -m` lifts the files out
and the boot blocks come from the same disk:

    hmount Sys30.img; hcd "System Folder"
    hcopy -m System /tmp/System30.bin; hcopy -m Finder /tmp/Finder30.bin
    mkmfs.py $V/Sys30Boot.img --boot $V/Sys30.img --name "System Tools" \
             /tmp/System30.bin /tmp/Finder30.bin

To launch something without a Finder in the frame, put it on as `Finder`:
System 3.0 ignores the boot blocks' shell name on MFS as on HFS, so `--shell`
is for System 1.1, the one system here that reads it.

    mkmfs.py --extract System $V/Sys30MFS.img /tmp/System30mfs.bin
    mkmfs.py $V/TrapBoot30.img --boot $V/Sys30MFS.img --name "System Software" \
             /tmp/System30mfs.bin build/traptest/TrapTest.bin:Finder

A volume with no `Desktop` file makes the Finder offer "minor repairs" on
first open; click OK and it rebuilds one.

**`traptest/` is the minimal reproduction** for what the 64K ROM lacks: it
paints a mark, makes one call, paints the next, and never returns (a probe
that exits has its marks erased by the desktop repaint). Its calls are in the
application's order, so where it stops is where the application stops; marks
are eight to a row in the top 75 points, clear of the system error dialog.
`-DTRAPTEST_NO_MEM` drops the two memory calls, which is how the File Manager
rows in FORMATS.md are reached on a 64K ROM at all. Build it by hand, put it on
the volume above as `Finder`, and read the marks — **on `mv-512Ke` as well as
`mv-512K`**, because a probe that stops early says nothing until it has been
seen to finish somewhere:

    cmake -B build/traptest -S tools/vmac/traptest \
          -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
    cmake --build build/traptest

**System 3.0 has its own driver, `sys30.py`, and `run.py --system Sys30.img`
does NOT work.** That system ignores the boot blocks' shell name, so every
fixture comes back NOGRID — which reads exactly like an application that will
not start (DECISIONS.md 2026-08-30, *the shell name System 3.0 does not
read*). `sys30.py` boots to the Finder and double-clicks the application
instead; launching unloads the Finder, 12 bytes' worth (FORMATS.md, *512 KB
machines*). `interactive.py --system Sys30.img --e2e` covers the user
interface there; its Standard File row and Finder icon positions are
per-system tables, because System 3.0 leaves a different number of items in
the volume window and lists the invisible `DeskTop` file that System 6 hides.

Nothing here runs in `./ci.sh`: it needs ~80 MB of downloads, an X server and
minutes per fixture. It is a deliberate, on-demand check.

**What a full re-verification costs, as host wall clock** (measured
2026-08-07, two cores, all-out emulators — how long YOU wait, not Mac Plus
time; see the 1x note below). Scale the per-fixture figure by the list;
`sample.txt` holds 74 fixtures:

| tier | command | cost |
|---|---|---|
| System 6.0.8, 1 MB | `run.py --mem 1M --list sample.txt` | ~5.1 s per fixture, one boot each |
| System 6.0.8, 4 MB, the stock System Folder | `run.py --keep-inits --list sample.txt` | the same per fixture; a tier of its own since 2026-10-21. **Not at 1 MB**: with every INIT and cdev loaded the System's own stop-sign alert comes up, text undrawn, before the application paints anything (NOGRID, 300 s each; two fixtures, 2026-10-21) |
| System 7.0.1, 4 MB | `run.py --system Sys7.img --list sample.txt` | ~5.1 s per fixture, one boot each |
| Mac OS 9.2, 22 fixtures | `os9.py --list os9sample.txt --launch` | tens of minutes — one full PowerPC boot per fixture |

**Stagger the start by a few seconds when the application has changed.** Two
runs share one CMake build directory per define-set (`build/mac-autotest`),
and two `cmake -B` on it at the same moment ends with one exiting 1 before it
boots anything (measured 2026-08-26). Once the build exists, runs overlap
cleanly.

Run the two Mini vMac tiers in parallel if you have the cores — safe since
2026-08-15, when Xvfb began picking its own display (`-displayfd`); before,
two runs could draw on one display and grade each other's emulator
(DECISIONS.md 2026-08-15). Safe for correctness, not for the host-side
watchdogs, which are wall-clock: with two 512Ke sweeps side by side on
2026-10-21, `sys30.py` took ~19 s a fixture and one came back `NOGRID` that
passed alone. **Re-run a `NOGRID` or `EMUDIED` from a parallel sweep alone
before reading it.** Do NOT run anything else alongside these, and
**never alongside `./ci.sh`**: every harness here grades itself through
`tools/vmac_check.py`, which shells out to `build/rel/macextract`, and CI's
`make clean` takes that binary away mid-sweep — a floor sweep beside CI came
back **38/69** on 2026-09-05, every "failure" a missing oracle.

## What the pieces do

| file | role |
|---|---|
| `segcheck.py` | **replay every segmented-archive scenario in one command** |
| `setup.sh` | fetch + build the emulators, ROMs and System images into `$UNC_VMAC_HOME` (default `~/.cache/macextract/vmac/`) |
| `sys30.py` | the **System 3.0 / Finder 5.1** tier, launched by double-click |
| `mkboot.py` | strip a System image to System + Finder and boot straight into the application; `--keep-inits` leaves the System Folder as it is |
| `drive.py` | boot a Mac and take clicks, keys and screenshots from a command file, one step at a time |
| `run.py` | build the disks, boot, screenshot, decode, check. `--out-kb`/`--in-kb` size the volumes, `--rsrc` gives the fixture a resource fork. **It cannot grade more than 128 files** (`AT_MAXREC`; a 153-file set failed by count on 2026-10-16) |
| `interactive.py` | drive the real UI and photograph each step |
| `os9.py` | Mac OS 9 on emulated PowerPC, both forks checked off the disk |
| `os9probe.py` | diagnostic: which input primitives reach the Mac OS 9 guest. Not part of any suite |
| `os9sample.txt` | the fixtures replayed on Mac OS 9, one per format |
| `mountcheck.py` | boot a system image with disks attached and photograph the desktop |
| `mkapmdisk.py` | build an Apple-partitioned transfer disk Mac OS on PowerPC will mount |
| `checkdisk.py` | verify a run by READING its Out volume: both forks, and names |
| `diskdoubler.py` | DiskDoubler 3.7 writes each method its menu offers; `--adjudicate` grades the forks no oracle decodes |
| `ddpro.py` | DiskDoubler **Pro** 4.1: `DDA2` and `SPLT` |
| `ddencode.py` | **grade a method by WRITING it** for Salient's 1991 DiskDoubler |
| `ndd.py` | DiskDoubler 3.1.2, 4.0 and Norton DiskDoubler Pro 1.1 |
| `superdisk.py` | grade SuperDisk! with its own self-extractors |
| `spacesaver.py` | Aladdin's **SpaceSaver**, and much of StuffIt Deluxe 3.5.1 |
| `sdcompress.py` | the **SuperDisk! control panel**, which compresses |
| `maclha.py` | **MacLHA 2.00** writes a `.lzh` with a real resource fork: `--setup`, `--make`, `--check`. Its Type menu (`MENU` 134, read with `hcopy`) offers `-lh5-`, `-lh1-`, `-lh0-` only; `-lh2-`/`-lh3-` are graded by `tools/run_lzh.py` (TESTING.md) |
| `zipmeta.py` | what StuffIt 3.5.1 does with a MacZip archive's Finder metadata |
| `sitzip.py` | the same for StuffIt Deluxe 5.5 and 7.0.3 on Mac OS 9, placed with no installer |
| `sitcomment.py` | StuffIt 5's archive flag byte, bit 5 |
| `expander.py` | **the yardstick**: StuffIt Expander 4.0.2 against this application, timed |
| `macclock.py` | **the stopwatch** `expander.py` times with; `clockcal/` is its known duration |
| `sitmeta.py` | which header bytes become Finder info, read back with `hfscat.py`; `ddmeta.py`, `nowmeta.py`, `sdmeta.py` are its siblings |
| `hfscat.py` | every catalog record on an HFS image, whole; `patch()` plants values before a boot |
| `macmime.py` | **a MIME message written BY a Macintosh**, with mpack's own Mac port (`tools/macmime/`) |
| `mkcollide.py` | an archive whose names collide on HFS, and a check of what `BumpName` did |
| `privatefile.py` | **Aladdin Private File 2.0** writes the specimens `tools/run_privatefile.py` grades |
| `maccompress.py` | **MacCompress 3.2**: `--fetch` (Discmaster, SHA-1 checked), `--make` on System 6, `--check`. The subject `Alpha` takes the volume window's FIRST icon slot; the application the second, at (172, 105) |

`tools/quickdraw-repro/` is a sibling that reuses `mkboot.py` and this
directory's `Display`/emulator plumbing for one narrow question about
System 6's Toolbox; `mkboot.py --finder` came from it.

`tools/aetran/` is the other sibling: a Retro68 application that sends one
Apple event to another application, which is how the btoa/atob translator is
reached without its inaccessible submenu (`sitcrypt.py --btoa-send`, below).
It is built by that harness, never by `ci.sh`, and it is System 7 only.

The verification halves live one directory up: `tools/decode_grid.py`
(screenshot → eight numbers) and `tools/vmac_check.py` (those numbers vs. the
oracle).

## Why it works the way it does

**Results come off the SCREEN and off the disk.** The app paints a black/white
bit grid (three calibration squares, a sync word, eight 32-bit values;
`at_report()` in `mac/macextract_mac.c`) that `run.py` decodes; it needs
nothing of the volume and reports liveness and setup failures, but cannot
carry a NAME — `checkdisk.py` reads the disk for that (*Checking a run off the
disk*, below). **The sync word is painted LAST**, so a mid-paint screenshot
has no sync and is rejected; any `--poll` is correct (DECISIONS.md
2026-08-28, *the certificate painted first*).

**A run that drives the FINDER ends with Special > Shut Down, and must.** Mini
vMac flushes a volume's writes when it is ejected, so a killed emulator loses
what the Finder had not written, and an image COPIED out of a killed session
does not boot. Or put the subjects on a second volume and Put Away (Cmd-Y), as
`sdcompress.py` does. **Photograph the pick**: Shut Down is at **(225, 139)**
on System 7 and **(175, 123)** on System 6; 123 on System 7 is **Restart**,
which ejects too and so hid the mistake until 2026-09-01 (BLOCKERS.md,
withdrawn claims) — `rescomp.py` has the case where it tore a write.

**The app is the boot shell.** The boot blocks' shell name (offset 0x1A) is
rewritten from `Finder` to `macextract`. **Nothing mounts disks** then (the
volume walk saw one volume after 30 s), so the autotest build calls
`PBMountVol` on each drive (`MountAllDrives`); the interactive application
uses Standard File, which does its own. `mkboot.py --finder` keeps the Finder
as shell, the application at the volume root, launched by double-click.

**The System Folder is stripped to System + Finder**: on the 1 MB machine the
stock INITs and cdevs are the difference between a result and a dead machine,
and they would make peak-heap figures incomparable. **What every stripped tier
cannot see: what an INIT adds to the System** (uzTools/MacExtract issue #1;
DECISIONS.md 2026-10-21, *the Desktop Manager System 6 can have*). `run.py
--keep-inits` boots the System Folder as it is, MultiFinder included where the
Finder is kept — **74/74** over the sample at 4 MB on 2026-10-21:

    tools/vmac/run.py --keep-inits --expect ARCHIVE.sit     # NOGRID before 2026-10-21
    tools/vmac/run.py --keep-inits --list tools/vmac/sample.txt

The reporter's whole story — Finder, MultiFinder, the release binary, the
archive typed `BINA`/`SITx` as Mini vMac's ImportFl types it — is `drive.py`,
a booted Mac taking clicks and keys from a file one step at a time:

    mkboot.py $V/System6.hfv dist/MacExtract.bin boot.hfv --finder --keep-inits \
              --data ARCHIVE.sit:ARCHIVE.sit
    hmount boot.hfv; hattrib -t BINA -c SITx ARCHIVE.sit; humount
    drive.py boot.hfv mv-4M shots/ &        # then: echo 'dclick 472 45' >> shots/cmd

Menus want the button held: `down X Y`, `move X Y`, `up`. **GateKeeper**
(DECISIONS.md 2026-10-21, *the guard that vetoes the Finder info*) is the same
boot with its three files in the System Folder, `hcopy -m` from
`~/.cache/macextract/gatekeeper/specimens/`; its mode is in the Control Panel
(Apple menu, Gatekeeper Controls, Settings), and the output is read off a COPY
of the run's `boot.hfv` with `hcopy -m` — vetoed Finder info is invisible on
screen.

**Verdicts.** Before any work the app paints `ret = -1000` ("running"); a
missing `In`/`Out` volume paints `-1001`/`-1002`; `run.py` reports `NOGRID`,
`TIMEOUT` and `SETUP`, distinct from `FAIL`. **`EMUDIED` means the host
failed, not the Mac** (twice in an 88-run sweep, both passed on re-run):
**re-run it before drawing any conclusion.** `run.py` and `os9.py` turn
SIGTERM/SIGINT into a clean exit; after any interrupted sweep check `pgrep -x
minivmac`, `pgrep -f qemu-system`, `pgrep -x Xvfb` — strays cost the next
emulator CPU.

**Timing.** `run.py --emu mv-4M-1x` splits boot from extraction (the "alive"
grid marks where work starts); `timing.txt` is the set, FORMATS.md has the
tables. `UNC_AT_PROGRESS` paints the engine's byte counter into the grid, so
an unfinished run can be interrogated — decode rates are very non-uniform (a
306 KB BinHex took 150 s, 205 KB of it in the last 100 s), and a timeout says
nothing. `decode_grid.py` costs ~50 ms a call, ~5 % of a 1x core at `--poll
1`; FORMATS.md's Arsenic timings were taken at `--poll 20`.

**Wall-clock time is not Mac Plus time — except in a 1x build.** `mv-4M` and
`mv-1M` run *all out* (the sweeps); `mv-4M-1x` and `mv-1M-1x` run at
authentic 7 MHz and are the **only** builds a timing claim may come from.
`interactive.py` defaults to `mv-4M-1x`, or the progress dialog is gone before
it can be photographed. `mv-1M-1x` exists because StuffIt 5's low-memory
inverse BWT runs only when memory is tight: a claim at the intersection of two
axes needs a build at that intersection.

**This box has two cores** (`nproc`, checked 2026-09-05). At 1x the emulator
paces itself against real time, so anything else CPU-heavy — `./ci.sh`, a
sweep, a second `interactive.py`, another SESSION's emulator — inflates the
number. `interactive.py` waits fixed seconds between clicks, so a Mac below 1x
photographs the wrong moments. **Run timing, and the interactive phases, one
at a time.**

**`interactive.py` is mostly not self-checking**: same clicks, same order, a
numbered screenshot per step. Every phase but `--e2e` ends on ONE check that
can fail — `--segments` the joined bytes, `--dest` which volume, `--wd` which
folder, the default phase the names its second boot wrote — because a
screenshot of the wrong dialog looks like the right one. `--e2e` is for a
photograph: an extracted application drawing its own splash screen.

- *Press buttons with Return, not coordinates* (a measured Open hit
  **Drive**).
- *Set X input focus explicitly*: with no window manager, keys go to the root
  window while clicks still work.
- *A phase written for a new path can leave the old one less covered*:
  `--dest` passed while the DEFAULT destination was broken.

## What StuffIt does with a zip's Finder metadata — `zipmeta.py`

    tools/vmac/zipmeta.py --make /tmp/rex/rexnebular_1_0_0.zip
    tools/vmac/zipmeta.py --table        # no emulator
    tools/vmac/zipmeta.py --expander     # one boot, reads the volume back

`--make` cuts four entries out of a real MacZip archive keeping their local
headers, `0x334d` fields and compressed data BYTE FOR BYTE — only the
central-directory offsets are rewritten. **`--table` is the answer and needs
no boot**: the `UnZip Translator`'s `E2Ty` resource is nineteen rows of
extension → type/creator (2 + 19 × 16 = 306, the whole resource). The result
is in FORMATS.md, *What Aladdin's own software does with the same bytes*.

**What it cannot see.** It grades ONE StuffIt, the 3.5.1 that `spacesaver.py`
installs, which predates the field by four years (`sitzip.py` has 5.5 and
7.0.3). It cannot tell "read the field and ignored it" from "never looked";
the translator's bytes distinguish them. `checksum.md5` coming back right
proves nothing — `TEXT/ttxt` is the table's answer for anything unrecognised.
**Read the `MSWD` rows.**

## The same question, two boxes later — `sitzip.py`

    tools/vmac/zipmeta.py --make fixtures/rexnebular_1_0_0.zip
    tools/vmac/sitzip.py --payload 55     # no emulator: extract and index
    tools/vmac/sitzip.py --carbonlib      # once, for 7.0.3 only
    tools/vmac/sitzip.py --run 55
    tools/vmac/sitzip.py --run 703
    tools/vmac/sitzip.py --list -o <rundir>    # what the run left behind

This grades **5.5 and 7.0.3** on `zipmeta.py`'s four-entry subject; the
result is in FORMATS.md, *What Aladdin's own software does with the same
bytes*.

**Nothing is installed by an installer.** Both payloads extract whole with
this engine (FORMATS.md, *StuffIt 5's method 14*), and `hfsboot.img` (below)
is a plain-HFS Mac OS 9 boot volume hfsutils can write, so the engine, the
seventeen translators (5.5) or the engine shell and twenty-three plug-ins
(7.0.3) are `hcopy -m`'d into a System Folder from Linux.

**Where each piece goes is read off the software**: the 5.5 engine's `STR#
999` (`Extensions`, `Aladdin`, `Extensions:Aladdin`), `STR# 1004`
(`:Extensions`, `StuffIt Engine™`) and `fld# 999` (`Translators`, `Viewers`,
`Magic Menu Extensions`); 7.0.3's `StuffItEngineShell` carries `StuffIt
Plug-Ins`.

**Entries are selected by TYPE and CREATOR, never by name.** An
InstallerMaker payload carries zero-length `STde`/`STin` directives beside
most real files (`! Zip Translator` is one), and a name pattern picks the
directive as happily as the file. The counts are asserted (17 translators, 23
plug-ins), so a payload that changes shape fails rather than half-installs.

**`--carbonlib` is a prerequisite for 7.0.3 only.** Its Expander refuses to
launch (*"Expander requires CarbonLib 1.6.0 or later."*), and the image
carries **1.4**. Apple ships 1.6 as a self-mounting image whose data fork is
NDIF, so the Macintosh mounts it; the 40 MB `CarbonLib_160_languages.sit` is
no help. The run reads `CarbonLib`'s `vers` back **off the disk** and keeps
the volume as `hfsboot-carbon.img` only if it says 1.6.

### Four things that each cost a boot

- **Do not open with os9.py's `Cmd-Q, Return`.** That pair quits the HFS+
  master's Setup Assistant; `hfsboot.img` has none, so the Return opens the
  selected icon's name for EDITING — `HFSBoot` was renamed `sit`. **A
  keystroke harmless in one application renames a volume in another.**
- **The Expand command's Command key differs**: 5.5's `MENU` 129 is `File ▸
  Expand… / E`, 7.0.3's is `File ▸ Expand / O`. A chord the application lacks
  looks like one the guest ignored. Read the `MENU` resource, do not guess.
- **The two Expand dialogs differ.** 5.5 puts up Standard File on the
  transfer volume. 7.0.3 puts up **Navigation Services**, which opens on the
  Desktop and greys `Open` out once a FILE is highlighted — take the archive
  with `Choose`; Return opens the boot volume and looks like a healthy start.
- **Return does not reach a button that is not the default**: both licence
  agreements (Apple's disk image, the installer's *"you must agree"* alert)
  need a click. Those two clicks are the only pointer work here, at
  coordinates measured off the screenshots they are named for.

**What it cannot see.** As `zipmeta.py`: each box's **Expander** and not every
reader in it, and "ignored" vs "never looked" (FORMATS.md beside the result
reads the binaries). It relies on one primitive no other harness here uses:
**Tab selects the first icon in a Finder window by name**, which opens an
installer on a disk whose contents are unknown.

### The same boxes over the hard cases — `compat9.py`

    compat9.py --assemble 55 -o <dir>     # or 703; sitzip's installation
    compat9.py --assemble 55 --set zip -o <dir>   # the zip-method subjects instead
    compat9.py --boot -o <dir>            # detached; drive with os9mouse.Mac(attach=True)
    compat9.py --stop -o <dir>            # kills the pid --boot wrote, nothing else
    compat9.py --read -o <dir>            # every file on the transfer volume, both forks

The results are FORMATS.md's, *Run over the hard cases* and, for `--set zip`,
*Zip methods in the three boxes*. The subjects are 2.0.1's archives, an
encrypted Compact Pro archive, an mpack set and a BinHex posting, **each in a
folder of its own** (most expand to the same name) and **each with creator
`SITx`**, both Expanders' signature: the Finder opens a subject with Tab and
Cmd-Down and hands it over as an `odoc` — no Expand dialog, no pointer.

It is driven by hand, one frame at a time:

- **Close only the subject's folder window.** Typing the volume's name in the
  volume window selects `StuffIt Expander`, and Cmd-Down launches it with no
  document.
- **Look before typing a password.** 7.0.3 asks on four of the five 2.0
  ciphers and not on `NewDE`; the same keystrokes into the Finder would
  rename the selected icon.
- **A refused archive still leaves files behind** (7.0.3 an empty or
  resource-only stub per refused entry, 5.5's MIME reader an empty file). The
  verdict is the bytes `--read` reports, never the icon.

**What it cannot see.** The Deluxe APPLICATIONS (5.5's will not start on this
installation, *What `--probe` measured* below; 7.0.3's is driven by
`as703.py --set boxes`); why a reader refused, beyond its own words; and more
than one subject per question.

### AppleSingle under 7.0.3, by pair and name — `as703.py`

    as703.py --assemble -o <dir>          # 7.0.3, sitzip's installation, nine subjects
    as703.py --assemble --set tigr -o <dir>   # one BINA/TIGR copy, for the Finder's dialog
    as703.py --assemble --set claims --app dist/MacExtract.bin -o <dir>   # + a .sit typed SIT!
    as703.py --assemble --set boxes -o <dir>  # + StuffIt Deluxe 7.0.3 and Tiger 1.1
    as703.py --assemble --set icons --app build/mac/MacExtract.bin -o <dir>   # the bundle's icon, and ZIVM
    as703.py --assemble --set sdar --app dist/MacExtract.bin -o <dir>   # a SuperDisk! archive typed SDar/MExt
    as703.py --boot -o <dir>              # compat9.boot; drive with os9mouse.Mac(attach=True)
    as703.py --stop -o <dir>
    as703.py --read -o <dir>              # compat9.read

The results are FORMATS.md's, *AppleSingle and AppleDouble in 7.0.3*. The
subjects are one AppleSingle file under six pairs and names and three
AppleDouble shapes, each in its own folder; the ownerless one (`????/????`)
goes through File ▸ Expand, taken with `Choose` at
`sitzip.DIST["703"]["choose"]`, (668, 510) on 2026-10-23. Driven by hand.

- **Type-to-select needs the letters within the Finder's delay.** 0.6 s apart,
  `s`, `i`, `t` selected `SitZip`, nothing, then `Trash`; 0.3 s apart they
  select the volume. One letter is enough where it is unique.
- **A refused subject still gets a folder and a stub**; the verdict is
  `--read`'s bytes.
- **The Expander quits after an `odoc` and stays after File ▸ Expand**, so
  the Cmd-W that closes a folder window must wait for the alert's OK.
- **The boot volume has StuffIt Browser™** (`Extensions:Aladdin:TFI
  Extensions`), which opens a `.sit` inside the Finder before any owner is
  looked for. For the alternate-program dialog, `hdel` it from the run's
  `boot.img` and the Expander from `transfer.img`, both before `--boot`.
- **Escape does not cancel the alternate-program dialog**, and a typed letter
  selects a row; Cancel is a click at (612, 363).
- **`--set boxes` puts Deluxe and Tiger on the volume**, Tiger from
  `~/.cache/macextract/compat/tiger/Tiger.bin` (Info-Mac II's, through
  Discmaster, SHA-1 `878a0f50…`). Deluxe's `Open…` (⌘O) lists archive kinds
  only; its decoders are `Translate ▸ Expand…`, keyless, reached by a held
  press. That dialog reopens in the LAST folder it showed (a second Expand
  wrote `Comment Folder.1`) — ⌘↑ first.

## The archive comment, and bit 5 — `sitcomment.py`

    tools/vmac/sitcomment.py --read              no emulator
    tools/vmac/sitcomment.py --aete              no emulator
    tools/vmac/sitcomment.py --specimen          boot, drive Deluxe by Apple event
    tools/vmac/sitcomment.py --read-back <img>   re-read a finished run's volume
    tools/vmac/sitcomment.py --probe -o <dir>    boot, launch Deluxe 5.5
    tools/vmac/sitcomment.py --macos86 -o <dir>  the boot that is not the route

**Bit 5 is measured** (FORMATS.md, *StuffIt 5's archive flag byte, and what
bit 5 is*). Its meaning came from `Tutorial Files/Sample Archive.sit` inside
Deluxe 5.5's installer (`sitzip.py --payload 55`), no emulator; `--specimen`
was needed only for the ORDER of password hash and comment block, which only
an archive setting bits 5 AND 7 can say: three boots produced
`enc-comment-added.sit` and `enc-comment-stuffed.sit`, both `0xb0`.
`tools/derive_sit5crypt.py` grades all six specimens on demand.

**`--read` and `--aete` need no emulator.** `--read` prints what each box
offers for a comment; `--aete` parses both scripting dictionaries whole and
raises if a byte is left over, because a dictionary read wrongly still looks
plausible:

| box | comment UI | scripting |
|---|---|---|
| Deluxe 5.5 | `MENU` 131 *Archive* ▸ `Edit Comment...`, **no Command key**; `STR# 30000` #13, a clickable comments AREA in the archive window | `Arc ` has `comment` (`comm`) and `password` (`pass`), both settable; `SIT!`/`STUF` takes `encrypting`; the Standard Suite has `get` and `set` |
| Deluxe 7.0.3 Classic | `MENU` 132 *Archive* ▸ `Edit Comment…`, **no Command key** | `ARCH` has `comment` (`COMM`) and `password` (`PASS`), both settable; `STFF`/`stff` takes a `password` directly; `core/setd` is in its `aedt` and **not** in its `aete` |

The keyless menu item is reachable on Mac OS 9 (*What the pointer cannot
select*, below); the Apple-event route stands on its own, since it reads the
archive's byte back.

**`--specimen` sends the events.** `tools/aesit/` is the sender, a Retro68
application in aetran.c's shape: the harness drives only the Finder, by
type-to-select and Cmd-Down, and everything after happens inside the
Macintosh. It launches StuffIt Deluxe, opens an archive already on the volume
with `aevt/odoc`, `core/setd`s one property, closes, writes every reply's
`errn` to `AEResult` **after each step**, and reads the archive's flag byte
back off the disk. One phase adds a COMMENT to the encrypted
`enc-swordfish.sit`; the other adds a PASSWORD to the commented `Sample
Archive.sit` and stuffs a file into it. Both end at `0xb0`.

**What the event ladder measured, 2026-10-06, three boots:**

- **`make` fails and `open` does not.** Three shapes of *make new archive*
  answer **-1701**, `errAEDescNotFound`; an archive already on the volume
  works first time. **When an application will not CREATE the artefact, hand
  it one and ask it to CHANGE it.**
- **A reply of 0 says the term was understood and nothing more.** `set
  password of archive 1` answers 0 and leaves the archive byte for byte; the
  same event followed by a `stuff` produces `0xb0`. So `aesit` prints byte
  83, not the `errn`.
- **Deluxe 7.0.3 launches on Mac OS 9.2 from an assembled installation** and
  has no "properly installed" check; its registration nag (*Not Now* /
  *Register*) does not block Apple events.
- **`core/setd` works only on a resolved object**: with no archive open,
  `set`, `save` and `close` answer **-1708** and `stuff into` **-1728**; with
  one open, `set password` answers **0**. **`core/save` answers -1708 to an
  archive object even so**, and `core/clos` answers 0, so closing is what
  writes.
- **`FlushVol` is enough to read the volume from outside.** `UnmountVol`
  answers **-47** while Deluxe runs off that volume, and `hmount` reads it
  anyway.
- **A Pascal string literal's length byte is checked by nothing**:
  `"\017Encrypted.sit"` is fifteen for thirteen characters and read as a
  missing file. `aesit` now checks each compiled-in name against `sizeof`.

**What this cannot see.** Whether an accepted event changed anything — the
flag byte is the answer, not the `errn`. **Bit 6**, which nothing on this
machine sets. And 5.5, which still stops at `STR# 269` #30 (below).

### What `--probe` measured, 2026-10-06

It assembles 5.5 with the **application** on the transfer volume, boots,
type-selects `stu` and photographs the result.

- **Deluxe 5.5 launches on Mac OS 9.2** — splash and its own menu bar — so
  what 9.2 refuses is **5.0.1**, not Deluxe (`probe55/12-launched.png`).
- **It will not run on an ASSEMBLED installation**: *"This copy of StuffIt
  Deluxe™ has not been properly installed..."*, `STR# 269` *Alerts/Errors*
  #30.
- **The alert is a wall, not a nag.** Return reaches its OK, and dismissing
  it **quits the application** (`probe55b/14-dismissed.png`); only the menu
  bar tells a dismissed alert from a quit application.

Two routes out, neither spent because 7.0.3 needs neither: place what the
check wants — the payload also carries `Aladdin Compression™` (`APPC/ALCO`),
`Compression Extension` (`FEXT/TFI`), `True Finder Integration™`
(`cdev/TFI`), `Magic Menu™` (`TFIx/TFI`) and a `Text Encoding Converter`
(`shlb/encv`), none of which `sitzip.DIST["55"]["place"]` places — or drive
Aladdin's installer with a published 5.x code from `spacesaver.CODES`. The
disassembly got as far as `CODE` 11 at `0x3844`, `{ Alert269(30); <one more
call>; return 0; }` (`Alert269` is `CODE` 4 at `0x3b4`); nothing in `CODE` 11
calls `0x3844`, so the condition is in another segment, not found.

## Making Now Compress archives with Now Compress — `nowcompress.py`

Specimens of the Now Compress block shapes, written by the original
application.

    tools/vmac/nowcompress.py --setup     # fetch Now Utilities 5.0.1, convert
    tools/vmac/nowcompress.py --install   # install Now QuickFiler on System 7
    tools/vmac/nowcompress.py --case all  # write the specimens
    tools/vmac/nowcompress.py --case probe   # four inputs chosen to be read
    tools/vmac/nowcompress.py --case reach   # how far back a match may point
    tools/vmac/nowcompress.py --case forks   # members with a RESOURCE fork
    tools/vmac/nowcompress.py --case wpos    # block starts at each quarter of the window
    tools/vmac/nowcompress.py --case match   # members varying only in how much MATCHES
    tools/vmac/nowcompress.py --case matchv  # the same ladder up and back down
    tools/vmac/nowcompress.py --setup6    # fetch Now Utilities 6.0, build its boot image
    tools/vmac/nowcompress.py --case6 faster # the same case, the OTHER encoder
    tools/vmac/nowcompress.py --verify    # decode them, check against the input
    tools/vmac/nowcompress.py --adjudicate SEA.bin ARCHIVE   # see below
    tools/vmac/nowcompress.py --expand OUTDIR FILE.bin ...   # and below
    tools/vmac/nowcompress.py --dearchive OUTDIR FILE.bin ...  # the same, for ARCHIVES

The compressor is **Now QuickFiler** (Compress ▸ Faster/Smaller, Archive ▸
Faster/Smaller). `hcopy -r` writes the **data fork alone**, so only `--case
forks` (through `make_volume(macbinary=...)`, i.e. `hcopy -m`) has members
with a resource fork — a rule once read off data-only members was withdrawn
(BLOCKERS.md, *Withdrawn claims*). Specimens land in
`$UNC_VMAC_HOME/specimens/now/<case>/` with the inputs beside them and a
screenshot per step; `tools/run_now.py` picks them up if present and skips
with a message if not.

**A case that varies one property of a COMPRESSED block must keep the content
compressible** (a keystream made the encoder store seven of eleven members;
Now Compress refuses a file it cannot compress). The cases, each one boot:

| case | what it plants | what it settled |
|---|---|---|
| `match` | 1,000 de Bruijn bytes, then 1,000 copies of a letter of the member's own | DECISIONS.md 2026-09-21, *the ladder that was walked back down* |
| `probe` | a 4,000-byte run of one byte; 6,000 bytes over `{A, B}`; 6,000 over `{A, B, C, D}` with known frequencies; 6,000 whose second half repeats its first — a table found by what it MUST contain | docs/formats/now-compress.md, *Shape 3* |
| `reach` | five 16 KB members, the fifth a copy of the first: a perfect match 64 KB back. Largest offset taken: 32,766 against a 32,768-byte window | DECISIONS.md 2026-09-21, *the window that stopped at the fork* |
| `tokdist`, `toklen` | one match of known distance (40, 2 to 16,384) or length (24, 2 to 255) in a slice of an order-2 de Bruijn sequence over 256 symbols, then a compressible tail; ~4 minutes, 64 members, two of `tokdist`'s a Huffman-only block INSIDE an archive | `tools/derive_now.py`; DECISIONS.md 2026-09-21, *the pair that never repeats* |
| `huffgap` | ten mixed files; eight came back Huffman-over-LZSS, each starting one zero byte after the table, then `00 03`; byte 0 (4, 6, 7, 8, 10, 14) a flush count | docs/formats/now-compress.md |
| `deep`, `deeparc` | Fibonacci byte histograms, compressed and archived: every table 10 to 13 deep, escape count zero — evidence for a negative | docs/formats/now-compress.md, *What this note does NOT describe* |
| `tree` | two folders and two loose files: a pre-order flattening, a folder record then the number of entries its +80 field states | docs/formats/now-compress.md, *The archive layer* |
| `forks` | members with a resource fork (`make_volume(macbinary=...)`) | BLOCKERS.md, *Withdrawn claims* |

**QuickFiler also compresses in the background** (its balloon help; queues
`ToBeCompressedDB` and kin). **It has never fired in a run here** — the
`archive` case leaves `mixed.bin` and `one.txt` at 49,000 and 7,500 bytes
beside the `.sea` — but every case keeps the menu-pick screenshot so a
specimen is attributed to the pick it shows.

Before re-running it:

- **The application is commercial and is not committed**, like the ROM:
  `--setup` fetches Macintosh Garden's installer image by URL and checks its
  MD5. The one-week demo offered at first launch is what the script uses.
- **The installer image is NDIF**; `--setup` converts it to raw HFS with an
  ADC decoder and a block map derived from the image. A wrong conversion will
  not mount, which is the check.
- **The installer's checkbox list is read back off the screen** after every
  click; clicking blind turned QuickFiler off.

**`--setup6` and `--case6` are the SECOND encoder**, Now Utilities 6.0 (March
1996), because a field constant across one program's output is a fact about
that program (docs/formats/now-compress.md, *Two encoders*). There is no
installer: `--setup6` places the extension and its toolbox from 6.0's `.sit`
(it needs `unar`; the outer archive is StuffIt 5) into `System
Folder:Extensions` of a copy of `Sys7.img`, keeping the leading spaces in
`  Now Toolbox` and ` Now QuickFiler Extension` (the load order). 6.0's menu
sits mid-bar, so its submenus open to the RIGHT and its rows are 36 px higher
than 5.0.1's; its Demo button is at (264, 306), not (237, 306). Specimens land
in `specimens/now6/`, beside 5.0.1's. Now Utilities 3.0.2 and 4.0.2 have no
compressor.

What the encoder writes per mode is FORMATS.md ✧; why it matters is
DECISIONS.md, "Now Compress, written by Now Compress".

**`--adjudicate` grades us with the archive's own decoder** — a `.sea` carries
the extractor that shipped with it:

    tools/vmac/nowcompress.py --adjudicate \
        fixtures/SyntheticReferences2.0.sea.bin \
        fixtures/derived-SyntheticReferences2.0.sea

puts the `.sea` on a 25 MB volume, runs it under System 7, reads the volume
back and compares every fork against our extraction — resource forks with
bytes 16..127 masked, the `vmac_check.py` convention (the Resource Manager
stamps that region). It works for any `.sea` in the corpus, and settled the
1995 archive `unar` cannot decode.

**And it takes any archive, by splicing.** `tools/mutate_now.py`'s `splice`
puts a different data fork into a `.sea`'s MacBinary, which is how
`synth_now.py --ladder` asks the encoder about the thirteen synthetic
archives (TESTING.md). **The control is a length change**: `probe`'s
3,830-byte archive inside `tree`'s self-extractor (built around 1,894 bytes)
extracts all four members byte-exact.

**An extractor that refuses leaves an empty volume, and zero forks all
agree** — `--adjudicate` fails when it graded nothing since 2026-09-21. Read
the fork COUNT, not the verdict.

**`--expand` runs the DECOMPRESSING half**, which turns "nothing here reads
this field" into a statement about the format:

    tools/mutate_now.py --byte2 0x5a --splice IN.bin OUT.bin IN.dat OUT.dat
    tools/vmac/nowcompress.py --expand /tmp/out OUT.bin ...

`--expand` puts MacBinary files on a volume (the type and creator make
QuickFiler offer the item), selects them all, releases the menu on
**Decompress**, and reads the volume back into `OUTDIR`. `tools/mutate_now.py`
changes ONE field and recomputes every checksum over it (block trailer, entry
record, block table, file header), so no correct reader can tell the result
from the original (docs/formats/now-compress.md).

- **Decompress and Dearchive are plain menu items** at y 300 and 235, not
  submenus (*What the pointer cannot select*, below).
- **Put a control on the volume**: one unmutated file spliced through the same
  path, or a failure cannot be told from a harness fault.
- **QuickFiler names its output after the entry record's name**, not the
  file's, so `mutate_now.py --rename` changes both when several mutations
  share a volume. Keep the new name **as long as the one it replaces**: the
  encoder leaves 23 catalogue-shaped bytes after a short Pascal name.
- **A refused file puts up an alert and waits**, so `--expand` presses Return
  once per file and waits fifteen seconds per file. **A file it has not
  REACHED looks exactly like one it refused**; read the last screenshot — an
  icon still highlighted is still in the selection.
- **Two refusals, two alerts, and the difference is the measurement.** *"A
  part of the file X is damaged. Do you want to continue decompressing…"* is
  a BLOCK the decoder rejected; *"…is damaged and cannot be repaired"* is the
  file rejected outright. Photograph the alert.

## Making ArcMac archives with ArcMac — `arcmac.py`

    tools/vmac/arcmac.py --wild     # the two archives in the wild, fork by fork
    tools/vmac/arcmac.py --setup    # fetch ArcMac 1.2a, rebuild the application
    tools/vmac/arcmac.py --make     # boot, archive a two-fork file, read it back
    tools/vmac/arcmac.py --decide   # report which fork the payload starts with

The answer is **data fork first** (FORMATS.md ★★★; DECISIONS.md, "ArcMac's
fork order"). Specimens land in `$UNC_VMAC_HOME/specimens/arcmac/` as plain
`.arc` files, with the input forks and a screenshot per step. They are
`run.py` inputs like any archive; `--expect` grades a file with no oracle
manifest against this engine's Linux output:

    tools/vmac/run.py --expect $UNC_VMAC_HOME/specimens/arcmac/Packed.ARC

Both fork CRC-32s must equal those of `specimens/arcmac/in-data` and
`in-rsrc`, the bytes that went INTO ArcMac — encoded on a Mac, decoded on a
Mac, checked against the input. `--expect` does NOT adjudicate the Linux side;
that format's suite does (TESTING.md), and the run says so on every line.

- **The encoder comes out of the archive it is needed for.** `--setup`
  fetches `ARCMACRC.BIN` (shareware, SHA-256 checked, not committed), whose
  first entry IS the ArcMac application; our CLI decodes it and re-wraps it as
  MacBinary, so no self-extractor runs in the guest.
- **Do not copy a Mac header's Finder info into MacBinary unexamined.**
  Copied, the application did not show in the Finder ("112K in disk, 1
  item"); `arcmac.macbinary` passes 0. The flags are `fHasBundle |
  fHasBeenInited` (0x2100 application, 0x0100 documents, `macunpack/arc.h`
  `h[42:44]`), not `invisible` (BLOCKERS.md, *Withdrawn claims*).
- **ArcMac 1.3c is a command shell**, "Martian Operating System"; the verb is
  `arc a<modifiers> archive files` (*ArcMac Command Summary* in its
  `ARCMAC.DOC`). `--cmd` (repeatable) runs anything else at that prompt.
- **The run ends with Special ▸ Shut Down**, the general rule above.

## BinHex 2.0 writes `.hex` and `.hcx` — `binhex2.py`

    tools/vmac/binhex2.py --make     boot System 6.0.8, encode four times
    tools/vmac/binhex2.py --check    our CLI against the subject's forks

BinHex 2.0 (1984) is `binhex_2.0.bin` from Macintosh Repository, fetched by
hand into `$UNC_VMAC_HOME/specimens/binhex2/` and checked by SHA-1; it is
re-wrapped from its forks because `hcopy -m` refuses its MacBinary I header.
File ▸ *Application -> Upload* encodes, *Compressed* (checked at launch) picks
`.hcx` over `.hex`, and every run ends with an alert Return dismisses.
`--make` writes `XF.hcx`, `XF.hex`, `XFlf.hex` (*Send line feeds*) and
`YN.hex` (`XF.hcx` encoded again) on a fresh volume (a killed run leaves the
old one "damaged"); `tools/harvest.py --restore` lifts the four
`derived-bh2-*` fixtures from it.

Standard File is clicked by row, and the rows are the volume's files by name:
every output is named to sort after `TwoForks`, or the next encode picks up
the previous output.

## Asking DiskDoubler what it can write — `diskdoubler.py`

Running DiskDoubler 3.7 showed two of the six methods once declined as
"nothing reachable writes one" to be reachable; both are implemented
(BLOCKERS.md).

    tools/vmac/diskdoubler.py --setup      # fetch DiskDoubler 3.7, unpack its disk
    tools/vmac/diskdoubler.py --wild       # every DD container ON that disk, by method
    tools/vmac/diskdoubler.py --install    # System 7 + the DiskDoubler INIT
    tools/vmac/diskdoubler.py --probe      # photograph the menus and dialogs
    tools/vmac/diskdoubler.py --make A     # compress the subject with Method A
    tools/vmac/diskdoubler.py --verify     # decode the specimens, check against the input
    tools/vmac/diskdoubler.py --combine tree   # a DDAR archive with a FOLDER in it
    tools/vmac/diskdoubler.py --combine raw    # the shapes that might skip the file header
    tools/vmac/diskdoubler.py --verify-combine # grade those against what went in
    tools/vmac/diskdoubler.py --beta-probe     # boot the 1990 INIT, photograph its menu
    tools/vmac/diskdoubler.py --beta           # compress with DiskDoubler ß05, 1990
    tools/vmac/diskdoubler.py --beta-verify    # grade what ß05 wrote

`--make` takes `A`, `B`, `guess` or `both` — the four items of the "How To
Compress" popup. What each writes is FORMATS.md ✦; why it matters is
DECISIONS.md, "DiskDoubler methods 1 and 7". Specimens land in
`$UNC_VMAC_HOME/specimens/diskdoubler/` with the input forks (`in-data`,
`in-rsrc`) and a screenshot per step.

- **The application does not run on its own.** Launched with no INIT
  loaded, it takes the personalization, writes it into its own resource fork
  and quits without a window — which looks like a crash. `--install` puts the
  INIT in Extensions; the work is done from the Finder's **DD** menu.
- **Both halves personalize themselves on first use**, and Mini vMac boots a
  COPY of the boot image, so the INIT does it every run; the dialog has no
  default button, so Return does nothing there.
- **Method 7 is not reachable from this keyboard**: "Sigma Hardware" appears
  only with a Sigma Designs card fitted. Its specimens come from `--wild` —
  two THINK C libraries on the 3.7 distribution disk are method 7.
- **The run ends with Put Away, and must** (*Why it works the way it does*,
  above).

### The oldest DiskDoubler there is — `--beta`

**DiskDoubler ß05, Copyright 1990 Salient**, the reason the 84-byte header
is not the format's (`docs/formats/diskdoubler-container.md`, *The header
size, and the 1990 header*). It rides in `DiskDoublerExpand3.sit` on the
Macintosh Garden page `--setup` fetches from; `--beta` fetches it by URL and
sha256.

- **It is an INIT with no application**, so `install_beta()` puts it in a
  **System 6.0.8** System Folder and the work is done from the Finder's
  **DD** menu.
- **The menu's x is measured, not assumed.** `--beta-probe` photographs the
  menu bar without clicking; `BETA_MENU_X` comes from it (DD at 221–234).
  Re-measure it if the boot image changes — a miss reads as a run that
  compressed nothing.
- **There are no settings**: `Compress Selection;Expand Selection` is the
  whole menu.
- **`--beta-verify` grades it against the bytes DiskDoubler was given**
  (`unar` answers "format not recognized" for one, and no other reader
  exists), in two passes: the specimen **as it is**, and **rewritten with an
  84-byte header** and the two fork checksums DiskDoubler 3.7 stored for the
  same input. Both forks byte-exact both ways.

### The two `DDAR` record shapes no corpus fixture has — `--combine`

All 36 entries of the corpus's 7 `DDAR` archives are top-level files.
`--combine` builds a volume with a known tree and drives **Combine**,
DiskDoubler's own archive command, from the DD menu:

    Payload/Nest/One, Payload/Nest/Two     text
    Payload/Raw                            24 KB nothing compresses
    Payload/Forked                         data plus a 340-byte resource fork
    Payload/Empty                          zero bytes
    Payload/Already.dd                     a file DiskDoubler had compressed

`--verify-combine` runs offline on the saved specimens against **the bytes
DiskDoubler was given** — 7 entries, 0 disagreements.

- **Select by typing**: `p` picks `Payload`, Cmd-O opens it, Cmd-A inside it
  enables Combine.
- **`--combine raw` needs `--make A` to have run** (one subject is its `.dd`).
  Combine EXPANDS an already-compressed file and archives what was inside, so
  that entry is graded on the original's bytes.
- **It did not produce the `0x20` flag** from five shapes offered on purpose
  — a measured negative about DiskDoubler 3.7, not the format; 1.x and 2.x
  are not reachable here.

### The forks neither oracle can decode — `--adjudicate`

    tools/vmac/diskdoubler.py --adjudicate lha-expander-103.hqx --write-manifest
    tools/vmac/diskdoubler.py --adjudicate terrain-man-20.hqx  --write-manifest

Two corpus fixtures hold forks that `unar` and `macunpack` both fail on. Both
are SELF-EXTRACTING, so each carries a third implementation. Name the
ENVELOPE: the derived `.sea` in `fixtures/` is its data fork alone, without
the extractor code.

`--write-manifest` records the verdict where `ci.sh` keeps checking it: a
fork the Mac wrote goes into the fixture's manifest with `data_oracle` naming
this harness, as `make_manifests.py` records a fork the second oracle
rescued. **Only DATA forks can go in**: every resource fork the Mac wrote
agrees with ours only under the `vmac_check.py` mask (measured 2026-08-21;
DECISIONS.md), so those stay `unadjudicated` with the mask in their reason.

### DiskDoubler's own expander on a DDAR archive — `--ddar`

    tools/vmac/diskdoubler.py --ddar fixtures/im2-DD3.7.7AuxFiles.dd

DD Expand 3.7.7, Symantec's own expander, expands the archive under System 7;
every file and folder it wrote is held against ours, both forks (reserved
resource-header bytes masked) and the catalog's Finder info (`hfscat.py`)
against `macextract l --meta` — a file's FInfo, a folder's DInfo and DXInfo
whole, except `inited` (0x0100), which DD Expand clears. **9 of 9** on
`im2-DD3.7.7AuxFiles.dd`, measured 2026-10-25, and 0 of 9 with the CLI from
before that day's fix (DECISIONS.md 2026-10-25, *the archive Symantec
shipped*).

The expander is not committed: the Info-Mac II CD's `:Utility:DD Expand™:DD
Expand™`, as MacBinary at `$UNC_VMAC_HOME/specimens/diskdoubler/
ddexpand-377.bin`, SHA-256 checked. **What it cannot see**: a `DDA2`
archive, which DD Expand 3.7.7 does not write; and comments, which live in
the Desktop file the read-back drops.

## The other half of DiskDoubler — `ddpro.py`

DiskDoubler **Pro** 4.1 writes `DDA2` archives, and methods 9, 6 and 10
behind the AD1/AD2/DD1/DD2/DD3 items of its Settings dialog.

    tools/vmac/ddpro.py --setup     # fetch 4.1, unpack it
    tools/vmac/ddpro.py --install   # System 7 + its Finder-menu extension
    tools/vmac/ddpro.py --probe     # photograph the menus and dialogs
    tools/vmac/ddpro.py --experiments   # one session, both questions below

- **A `DDA2` stored entry with a resource fork does not exist** (measured
  2026-08-21): the headerless `0x1000` record is written only for a file
  whose data fork is stored AND which has no resource fork. `ndd.py --stored`
  measures all four cells; `--dates` settles which of `+54` and `+58` is the
  creation (FORMATS.md, DECISIONS.md).
- **The 4 bytes at `+4` of a `SPLT` header are the Mac's `TickCount` at the
  split** (measured 2026-08-21): three files split 72 s apart differ by 4,324
  and 4,330 ticks (FORMATS.md, DECISIONS.md).

The download is a StuffIt archive our CLI unpacks; the work is done from the
Finder's menu. Traps, each of which cost a run (DECISIONS.md 2026-08-21):

- **Never press Return at the desktop** — it opens the selected icon's name
  for editing. `select()` sends Escape first.
- **Put the application on the work volume**, or "Create Archive…" answers
  *The DiskDoubler application cannot be found.* and greys the menu out.
- **Spell the Mac name in the source**: `DiskDoubler™`; what `™` becomes in a
  Linux directory depends on the transcoding.
- **Leave room for what DiskDoubler writes**: "Split File (760K)" — a smaller
  subject comes out in one piece.

## The last two DiskDoublers — `ndd.py`

**DiskDoubler 4.0** (the first *SuperDoubler* bundle) and **Norton
DiskDoubler Pro 1.1**, Symantec's last, whose application is DiskDoubler
**4.1.1** (DECISIONS.md 2026-08-21, the Symantec release).

    tools/vmac/ndd.py --setup      fetch all three
    tools/vmac/ndd.py --specimens  decode Salient's 1991 disk; report methods
    tools/vmac/ndd.py --harvest    decode the Norton floppy; report methods
    tools/vmac/ndd.py --grade      DiskTester: ours vs the uncompressed 4.0 copy
    tools/vmac/ndd.py --install    System 7 + 4.1.1's Finder menu
    tools/vmac/ndd.py --probe      photograph the menu titles
    tools/vmac/ndd.py --submenu    Compress Using, About, Settings
    tools/vmac/ndd.py --stored     what selects the headerless 0x1000 record
    tools/vmac/ndd.py --dates      which of +54 and +58 is the creation
    tools/vmac/ndd.py --archive    seven files, one incompressible with a fork
    tools/vmac/ndd.py --dexvert    a third collector's samples, over the network

`--specimens`, `--harvest` and `--grade` need no emulator and no X server;
the rest are one boot each, about ten minutes of host wall clock.

**`--specimens`**: Salient's 3.1.2 floppy (WinWorld) holds 24 DiskDoubler
containers written in 1991 — the only method 2 fork this project has found,
and 22 method 7 forks of up to eight chunks. Each carries its own checksum,
so the mode returns non-zero on any mismatch.

- **The download is behind a one-shot token.** A plain `GET download.php?id=`
  answers "link expired"; the token comes from a 302 that needs the software
  page's session cookie, and the file is a POST of the hidden field past that
  redirect. `fetch_norton()` does the three steps. The failure mode is a
  168-byte HTML body saved as `.img`, so the SHA-1 is checked.
- **Everything on that floppy is DiskDoubler-compressed** (`DDF0`–`DDF3`,
  creator `DDAP`); `--harvest` decodes all of it and prints each container's
  methods — ten more graded specimens.
- **The boot image is built out of forks this engine decoded**: a wrong byte
  produces a System 7 that will not start.
- **Put the subjects in a folder.** `session(..., folder="Subjects")` keeps
  them apart from the application at the volume root, which Select All would
  catch. `select()` sends Escape first; the folder is opened with Cmd-O.

`--stored` grades itself against the bytes that went in, resource forks with
16..127 masked, non-zero on any mismatch.

## SuperDisk!'s compressor — `sdcompress.py`

Alysis's 1991 ` SuperDisk!` control panel (`cdev`/`AlyS`), the half that
compresses (BLOCKERS.md).

    tools/vmac/sdcompress.py --setup      fetch it (Macintosh Repository)
    tools/vmac/sdcompress.py --install    System 7 + the control panel
    tools/vmac/sdcompress.py --panel      open the panel and photograph it
    tools/vmac/sdcompress.py --makefile   what "Make File" offers
    tools/vmac/sdcompress.py --compress   compress a subject, report the file
    tools/vmac/sdcompress.py --specimens  compress all five subjects
    tools/vmac/sdcompress.py --verify     read them back, compare with the input
    tools/vmac/sdcompress.py --axes       photograph each settings axis
    tools/vmac/sdcompress.py --sweep      the same bytes once per setting
    tools/vmac/sdcompress.py --boundary   subjects sized for a refill boundary

**`--sweep`** is identical content once per setting: Speed=Fast writes method
**6** where everything else writes 1.

**`--boundary`** compresses four subjects at Speed=Fast, sized so the coded
flag bitmap ends exactly on a 32-bit refill (DECISIONS.md 2026-08-28). The
panel codes each flag BYTE in one bit (`tools/sdhuff.py` measures it), so the
bitmap is `nflags + 5` bits and `ceil(ulen/8) + 5 ≡ 0 (mod 32)` is the aim:
1240 and 2008 bytes land on 160 and 256 bits; 1248 and 2016 are one bit past,
as controls. It prints the bit count and the verdict per subject;
`tools/sdmodule/run_sdmodule.py` grades the specimens. (`ceil(ulen/8) % 4 ==
0` is the rule for `run_sdmodule.py`'s flat 8-bit code, not the panel's.)

**`--specimens`**: five subjects chosen to DISAGREE — one with a resource
fork, one stamped 1990 and 1995, one with a 20-character name (the only one
that shows the body is padded to an even offset), one over 32 KB. `--verify`
needs no emulator.

- **Close the panel with Cmd-W, not its close box**: a missed close box sent
  the next click to the settings page's **Off** button and the typed name into
  the Finder, which renamed a control panel "Coff".
- **Reopening lands on the last page shown**, so `reopen_panel` presses "Last
  Page" twice before any page-1 click.
- **The extension is the RESULT, not the trigger**: renaming a file `Alpha.x`
  changes nothing (measured); the work is the panel's "Make File" button.
- **Rebuild the boot image every run**: the panel saves its settings *and its
  current page* into the System Folder. `session()` re-copies `Sys7.img`
  unconditionally.
- **The Apple menu is not worth fighting** (two attempts gave an inverted
  title and no menu). Navigate to `System Folder:Control Panels` instead.

## Alysis Resource Compressor 2.0 — `rescomp.py`

The hunt for something that WRITES SuperDisk!'s methods 10, 13 and 20. This
1993 application carries `Cmpr` 3, 5, 19, 21, 22 (SlowFastB **and**
Tennessee end to end), 23 and 26, the same bodies as Disk Expander 1.2's.

    tools/vmac/rescomp.py --modules    list them; no emulator, no X
    tools/vmac/rescomp.py --probe      boot it, photograph its menus
    tools/vmac/rescomp.py --compress   compress a subject and read it back

**It compresses, and it is not the writer.** 8,001 bytes of `STR` became 472
in Apple's compressed-resource container (`A89F6572`, version 8, `defProcID`
**0**), not a `Cmpr` stream: none of the seven modules reproduces the subject
from that payload. The modules are there for its Decompress button.

- **Aim the Special menu at a measured coordinate.** 118, borrowed from
  another harness, hit **Restart**: new resource data with the old resource
  MAP, a torn read that looks like a format finding until the fork's length is
  checked. Shut Down is at 139.
- **The read-back is the result, not the screen**: the `Cmprssd` column said
  472 in both runs.

## SpaceSaver — `spacesaver.py`, and what it will and will not do

3.5.1 runs, its container has been read out of it (`--layout`), and **it has
never compressed anything here**. **SpaceSaver 5.0 needs System 7.5.3 and
8 MB**: forced past its two "Install anyway?" alerts on 7.0.1 it bombs with
*unimplemented trap*. **3.5.1 stops at a registration number** it will not
accept empty, and no serial was sought (the maintainer waived the licence's
reverse-engineering clause, which is not the same permission). DECISIONS.md
2026-08-22 (SpaceSaver, and SpaceSaver later) has both.

    tools/vmac/spacesaver.py --setup     fetch the CD (156 MB), lift the installer
    tools/vmac/spacesaver.py --probe     boot with it and photograph
    tools/vmac/spacesaver.py --install   walk the installer as far as it goes

    tools/vmac/spacesaver.py --setup351   fetch the 3.5.1 two-floppy set
    tools/vmac/spacesaver.py --probe351   boot with both floppies mounted
    tools/vmac/spacesaver.py --install351 run the 3.5.1 installer

    tools/vmac/spacesaver.py --setup40    fetch StuffIt Deluxe 4.0
    tools/vmac/spacesaver.py --install40  run it, trying each published code

    tools/vmac/spacesaver.py --keep-installed  lift the installed image out of /tmp
    tools/vmac/spacesaver.py --probe-installed boot it, peek the Magic Menu
    tools/vmac/spacesaver.py --idle           the panel's two settings pages
    tools/vmac/spacesaver.py --enroll         enrol the disk, then idle
    tools/vmac/spacesaver.py --namerule       rename a subject to end in "small"
    tools/vmac/spacesaver.py --suffix         both rename rules, one boot
    tools/vmac/spacesaver.py --magic          Magic Menu's SpaceSaver Compress
    tools/vmac/spacesaver.py --enrollmagic    the same, disk enrolled first
    tools/vmac/spacesaver.py --drop           launch DropCompress
    tools/vmac/spacesaver.py --dragdrop       drop a subject on DropCompress
    tools/vmac/spacesaver.py --commit         OK the settings page, then rename
    tools/vmac/spacesaver.py --idlenow        delete Magic Menu, use SpaceSaver's
    tools/vmac/spacesaver.py --parade         photograph the startup icons
    tools/vmac/spacesaver.py --twoboot        write the prefs, reboot, rename

    tools/vmac/spacesaver.py --specimen       rename, wait, SHUT DOWN, read back
    tools/vmac/spacesaver.py --patch-init     open INIT 0's install gate first
    tools/vmac/spacesaver.py --idlespec       enrol the disk, idle, shut down
    tools/vmac/spacesaver.py --layout         read the container out of the
                                              installed panel and engine
    tools/vmac/spacesaver.py --pkg            read AppleLink .pkg's recogniser
                                              out of the translator beside it
    tools/vmac/spacesaver.py --pkgexpand      write packages here and offer
                                              them to PKG Expand
    tools/vmac/spacesaver.py --pkgexpander    the same, to StuffIt Expander
    tools/vmac/spacesaver.py --pkgconvert     the same, to DropConvert

Also: `--magicname`, `--info` (*SpaceSaver Info...* answers, so the engine
is reachable), `--ssmenu`, `--enrollidle`, `--freshinstall` and `--calib`.
Every mode from `--specimen` on ends with Special > Shut Down at the right
coordinate (*Why it works the way it does*); `ssenrolled.hfv`, made before
that rule, does not boot.

**`--layout` needs no emulator.** It lifts `~StuffIt SpaceSaver™`
(`cdev/SMKR`) and `StuffIt Engine™` off `ssinstalled.hfv` with `hcopy` and
prints the compression header, the fork record, the compressor table from
each `CMod` module and the engine's MacsBug symbols, ending with **nine
witnesses** — byte patterns that must be in `SSEn 1` and `ACMP 1` — so a
different build says MISSING and exits 1 (FORMATS.md, *StuffIt SpaceSaver's
container*).

**`--pkg`** prints the AppleLink translator's `Name`, vocabulary and
recogniser (four witnesses); the recogniser parses the translator API's
command language, not a file (BLOCKERS.md). The format came from 3.0.7's
translator (*The AppleLink package expander*, below). Offering a
`tools/synth_sqp.py` package to `AppleLink Package Translator` **3.0.3** has
not been run (DECISIONS.md 2026-10-05, *the deviation that was the
reference*).

**The three `--pkg*` boot modes offer 3.5's translator a package written here,
and all three come back empty** (DECISIONS.md 2026-09-01, *the package that
cannot be handed over*). Each writes five one-line packages into `StuffIt
Deluxe™ Folder` (`Decode <item> to <destination>`, one per Finder type) plus
`Payload.hqx`, the BinHex file they name. `--pkgexpand` drives *Translate ▸
PKG Expand…* with *CPT Expand…* over a real `.cpt` as control;
`--pkgexpander` drives Expander's `⌘E`; `--pkgconvert` drives DropConvert's
`⌘C` (*type, Return to Add, then click Convert at (452, 289)*). **What they
cannot see**: *"this build will not take that input"* from *"this text is not
a package"*. **Read the control first**: `Payload.hqx` must have become
`Widget` (Expander) or `Widget.sit` (DropConvert). Its resource fork comes
back the right LENGTH with different bytes (BLOCKERS.md 2026-08-23); compare
data forks. Every field is read from the writer, not from output.

**The extension installs** (2026-08-25): any boot leaves `System
Folder:Preferences:SpaceSaver Preferences` (`Pref/SMKR`, 10,496 B), patched
or not, so `--patch-init`'s gate was never closing. Check that file after any
run; its `Opts 1` resource carries the `small` name rule. Why the rule never
fires is not explained.

**Nothing has made SpaceSaver compress anything**: the `small` name rule
(`--specimen`), enrolled and idle (`--idlespec`), Magic Menu's *SpaceSaver
Compress* (`--magic`, `--enrollmagic`), `DropCompress™` (`--drop`,
`--dragdrop`), and the modes above. `--suffix` renaming to `.SIT` returns a
StuffIt archive — Magic Menu's doing. `--idlenow` deletes `~Magic Menu™` so
SpaceSaver's own menu (`STR# 1024`: *Turn Idle-Time On*, **Idle Now**, *Open
Control Panel*) has the bar (DECISIONS.md 2026-08-22, what will not
compress). **That menu is at x=425** (`SS_MENU_X`; 283 is Magic Menu's). When
a mouse mode does nothing, suspect the coordinate: `--calib` photographs the
pointer at known positions, and the newer modes print `xdotool
getmouselocation`.

- **`ssinstalled.hfv` is flushed** (`--install351` ends with Shut Down); the
  torn one is `ssinstalled-torn.hfv`.
- **`--parade` cannot see the startup icon parade**: Mini vMac runs
  unthrottled, so its 30 frames are the settled desktop.
- **Lift the installed image out of `/tmp`** (`--keep-installed`): `run.py`
  boots a COPY, so the boot image looks untouched.
- **Do not press the installer's Restart** (its only button at the end):
  Mini vMac flushes on eject or shutdown, not a guest restart, so the image
  comes back stock and unbootable. Cmd-Q, then Shut Down in the Finder.
- **3.5.1 and 4.0 reject every code Macintosh Garden publishes** (those are
  for 3.0.7 and 5.x; 5.x needs 7.5.3 and 8000K).

Input rules for both Aladdin installers, each of which cost a run:

- **Every panel swallows its first input**: the tell is a frame IDENTICAL to
  the one before. The harness sends a click, then a Return.
- **A button is clicked ONCE**, and **walk the pointer to it** — a warp then
  an immediate click lands short (66 px short of "Yes" is "No").
  `--freshinstall` photographs the pointer on each button first.
- **The two "Install anyway?" alerts (7.5.3, 8000K) default to No**; a blind
  Return quits, and looks like a finished install.
- **Wait longer than feels necessary**: a click before its dialog lands
  behind it.
- **3.5.1's floppy opens its own window on boot and 4.0's does not.**
- **Cmd-A does not select a System 7 dialog field's text**: backspace it.

## Grading a method by writing it — `ddencode.py`

DiskDoubler methods 3, 4 and 5 have no specimen, so this **encodes** a fork,
wraps it in a `0xABCD0054` container with a correct header CRC, and hands it
to Salient's 1991 application, off the 3.1.2 disk uncompressed.

    tools/vmac/ddencode.py --build            write them; round-trip here
    tools/vmac/ddencode.py --probe            the 1991 INIT, in the Finder
    tools/vmac/ddencode.py --probe-app        the application's own menus
    tools/vmac/ddencode.py --expand           let 1991 read them
    tools/vmac/ddencode.py --expand --era 411 let 4.1.1 read them

`--build` needs no emulator and must pass before a boot is worth it; it is
encoder-vs-decoder, both ours, so it catches transcription slips and proves
nothing about the format. `--expand` is the part that grades.

- **The 1991 INIT adds no Finder menu** (that came with 3.7's "Finder Menu"
  extension). It registers the `DDF2`/`DDAP` icons, which is how a `--probe`
  frame shows it loaded; expanding is a double-click.
- **The application personalizes on first launch**; `--expand` answers it
  once and quits before touching any file.
- **Give the subjects a type nothing owns.** Expanding a `TEXT` file launches
  TeachText, and the next `Cmd-O` opens TeachText's dialog — three false "the
  expander did not take it". Click the Finder window before each file, too.
- **Use 1991, not 4.1.1, for methods 3 and 4**: 4.1.1 answers *Unknown
  compression method*. `--era 411` is a second opinion on method 5.

## A Macintosh writes a MIME message — `macmime.py`

`src/fmt_mime.c` is transcribed from mpack 1.6; mpack's Macintosh PORT is in
the same reference tree, so the specimen is made here (DECISIONS.md
2026-08-29, *a Macintosh wrote a MIME message*).

    tools/vmac/macmime.py --make     boot System 6.0.8 and write it
    tools/vmac/macmime.py --check    grade what came off the disk
    tools/vmac/macmime.py            both

`--make` boots straight into the encoder and reads `Out.mime` back off the
image. `--check` needs no emulator.

- **Retro68's newlib file I/O cannot be used on System 6.0.8**: a bare
  `open()` never returns, so every `FILE *` mpack touches is `funopen()` over
  hand-filled HFS param blocks.
- **The subject lives in the System Folder, not at the root**: `mkboot.py`'s
  shell starts in the blessed folder; a subject at the root gets −43.
- **`hcopy -m` does not carry the Finder flags onto the volume.** They are set
  on the Mac with `PBHSetFInfoSync` and the catalogue re-read afterwards.
- **The application draws its progress on screen**, one line per step; frames
  are kept in `$UNC_VMAC_HOME/specimens/macmime/shots/`.

What it cannot see: one message from one encoder, and line endings — the
specimen is LF-terminated because of the C library the port was compiled
against. FORMATS.md, *base64 and MIME*, says so where the result is.

## Grading SuperDisk! with SuperDisk! — `superdisk.py`

Nothing outside the two corpus archives reads the format, and both are
self-extracting applications — the same bargain as `nowcompress.py
--adjudicate`.

    tools/vmac/superdisk.py --list                    what the corpus holds
    tools/vmac/superdisk.py --adjudicate FIXTURE.hqx  run it, compare forks

The archive is unwrapped with our CLI, rebuilt as MacBinary, put alone on a
25 MB volume and launched under System 7; its "Save the expanded file as:"
box takes Return, and every fork it wrote is read back with `hfsutils` and
compared with `macextract x`, resource forks with bytes 16..127 masked. 5
forks across the 2 archives, all identical (2026-08-20; FORMATS.md ✧✧).
Screenshots land in `$UNC_VMAC_HOME/specimens/superdisk/`;
`tools/run_superdisk.py` replays the verdict offline.

- **The application is opened with Select All, not a coordinate**: the
  volume holds one item, so ⌘A then ⌘O. A measured double-click merely
  SELECTED the second archive (its icon drawn a few pixels higher) and the run
  "succeeded" having launched nothing.
- **The run ends with Put Away, and must** (*Why it works the way it does*).

### Handing that extractor a stream written HERE — `--nest`, `--stored`, `--rootfile`

`SD! Utilities.x` is an APPL whose data fork IS the archive, so replacing
that fork gives the format's own `CODE 2` a record stream built here
(`tools/synth_sd.py`) — the container's only second reader.

    tools/vmac/superdisk.py --nest              a 10-folder path, past the cap
    tools/vmac/superdisk.py --stored            the one block shape no fixture has
    tools/vmac/superdisk.py --rootfile          a stream that opens with a file
    tools/vmac/superdisk.py --rootfile --invented   ...with a guessed record

Measured 2026-09-01, one boot each. `--nest` builds ten folders of 31
characters, paths 43 to 331 bytes: the Macintosh made all eleven files
byte-identical, and for the three past 255 bytes **the uncut path
`unc_path_leaf` reports is the path the Macintosh built** (it creates each
component through the File Manager). `--stored` reads back byte-exact.
`tools/run_names.py` replays the `--nest` verdict offline.

What these CANNOT see: whether SuperDisk! would ever WRITE such a stream —
only what its expander reads.

**One run bombed and has not been reduced — a hypothesis.** The first
`--nest` attempt died with *"unimplemented trap"* after the Save box, writing
nothing. Its four differences from the working streams have each run fine
alone (depth, stored blocks, a file as the FIRST record, a guessed file
record); the untested combination is a root file FOLLOWED by a folder —
`synth_sd.nest()` with `control.txt` moved to the front, one boot.

### Replaying a SuperDisk! archive through OUR Mac application

This format has no oracle manifest, so the grid is read directly. Unwrap the
payloads first:

    macextract x -nr -o /tmp/sd fixtures/alysis-disk-expander-12.hqx
    tools/vmac/run.py --pngdir /tmp/p "/tmp/sd/Disk Expander .X"
    tools/decode_grid.py "/tmp/p/Disk Expander .X.png"

`run.py` reports FAIL — "no oracle manifest" — which means it cannot grade,
not a result. Compare the grid with the Linux aggregate over a `macextract x
-nr --forks hidden` of the same payload:

    python3 -c "import sys; sys.path.insert(0,'tools'); \
      from vmac_check import aggregate_dir; print(aggregate_dir('DIR'))"

Both archives matched at 4 MB and 1 MB on 2026-08-20 (FORMATS.md, "SuperDisk!
on the Mac").

## How deep a Macintosh will nest — `depthtest/`

What `UNC_PATH_MAXDEPTH` is measured against. Build it by hand like `memtest`
and `traptest`, put it on a THROWAWAY boot volume as the shell (it creates
folders on the volume it booted from), and read the numbers off the screen:

    cmake -B build/depthtest -S tools/vmac/depthtest \
          -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
    cmake --build build/depthtest
    mkboot.py $V/System6.hfv build/depthtest/DepthTest.bin /tmp/depth.hfv \
              --app-name DepthTest
    $V/mv-4M/minivmac -r $V/vMac.ROM /tmp/depth.hfv

Two numbers, for the two routes to a file: `PBDirCreateSync` with a parent
dirID per level (the shell's `EnsureDir`) reached **250 levels with noErr** —
the probe's own loop cap — and `PBGetCatInfo` given a full `Volume:a:b:...`
pathname stops at **49 levels of four characters** (a `Str255` holds 254
bytes of it). FORMATS.md, *What the DESTINATION actually allows*, has the
table.

**What it cannot see:** anything above 250, where the loop stops rather than
the Mac; and whether the FINDER can navigate what the File Manager creates,
which the shell never asks.

## The yardstick — `expander.py`

This boots StuffIt Expander 4.0.2 and this application on the same emulated
Mac Plus, at authentic 7 MHz, over the same archive on the same volume — the
comparison a user weighs.

    tools/vmac/expander.py --fetch          # download 4.0.2 and unpack the app
    tools/vmac/expander.py --sizes          # both SIZE resources; no emulator
    tools/vmac/expander.py --quiet 60 --json y.json fixtures/derived-Export.sit

Results and the ratio: FORMATS.md, *Timed on the same Mac Plus*. **One
emulator at a time, and nothing else on the box** — the 1x rule above.

`--fetch` takes Macintosh Garden's `stuffit_expander_4.0.2.sea_.bin`, checks
its SHA-256, walks MacBinary → self-extracting StuffIt → 400K disk image with
our CLI, and copies the application off that image.

- **Garden signs its download URLs and answers a bare GET with HTTP 418.** The
  page is fetched first and its cookie jar reused for the file (`arcmac.py`
  does the same two-step without the jar on the page request).
- **hfsutils refuses a volume "smaller than 800K"**, and the image is 400K;
  padding a temporary copy to 800K mounts it (reads follow the MDB's extents).
  That refusal was the whole of a withdrawn "no HFS reader" claim (BLOCKERS.md).

**The instrument is `macclock.py`** (since 2026-10-19; DECISIONS.md
2026-10-19, *the clock inside the Mac*). Both applications are driven to a
Standard File dialog with the archive selected, then timed from the keystroke
or click that starts the work to the last change of the screen buffer before
it holds still for `--quiet` seconds. The host reads the emulated `Ticks` and
the 21,888-byte screen buffer out of Mini vMac's memory at 50 Hz
(`/proc/<pid>/mem`, read-only), ~0.1 ms a read; a duration is **emulated
ticks ÷ 60.15**, host seconds beside it as a check.

    tools/vmac/expander.py --calibrate jkjk6                 # a known wait, ~3 min
    tools/vmac/expander.py --ours dist/MacExtract.bin --repeat 2 \
        --json t.json fixtures/derived-Export.sit            # the shipped app
    tools/vmac/expander.py --only ours --emu mv-1M-1x --quiet 30 ...

**Calibrated against `clockcal/`**, a 60-line application that busy-waits a
number of ticks fixed by the key pressed and draws a mark at each end
(`--calibrate`; built by the script): on `mv-4M-1x`, 2026-10-19, **+2 to +3
ticks of keystroke latency, constant**, host ÷ Mac seconds 0.9986–1.0001. A
`--quiet` shorter than the silent wait stops the stopwatch at the start mark.
**Keep ticks, not host seconds**: at 1x Mini vMac drops emulated time it is
more than 8 ticks behind (`RunEmulatedTicksToTrueTime`); every JSON row
carries `ratio` (host ÷ Mac), and far from 1.00 the host was the bottleneck.

**What `macclock.py` cannot see:** whether a Mini vMac tick holds as many
instructions as a real Mac Plus's (MANUAL_TESTS.md); disk time, which the
emulator makes free; a tick lost while interrupts are masked; work that draws
nothing for longer than `--quiet` — our progress bar sits at 0 % for over 30 s
on an Arsenic archive at 1 MB, so use `--quiet 300` there and check the run
wrote its files. The pointer is drawn into the screen buffer, so the harness
moves it BEFORE the mark.

- **The first row is not the archive**: our dialog lists the Finder's
  invisible `Desktop` file (`mkboot.py` keeps it since 2026-08-30), so a
  fixture sorting after it had `Desktop` extracted instead. The file is named
  by type-ahead (`select_by_name`), and `ours-2-selected.png` photographs the
  highlighted row before Return.
- **Expander's dialog is not the stock one** (the list ~48 px higher): the
  first row is preselected, and Expand is pressed at a coordinate measured off
  this harness's frame. Return is untested, not disproved.
- **Assign X keyboard focus** (`origin()`, not `settle()`).
- **Expander's output is not on the image until it quits.** Our sink calls
  `FlushVol` per fork; Expander's writes sit in the File Manager's cache, and
  SIGKILL loses them, so the harness sends Command-Q after the measurement.
  `live_names()` mounts a copy of the live `boot.hfv` when the screen stops,
  after the quit key and after the kill; `--json` carries
  `on_disk_before_quit`, `on_disk_after_quit`, `flush_seconds` and
  `quit_redrew` (FORMATS.md, *Timed on the same Mac Plus*).

**What the SCREEN cannot see**: Command-Q commits Expander's writes and
**repaints nothing**, so `quit` and `to_disk` in the JSON (screen figures)
read one poll interval whatever happened; the `on_disk_*` lists observe.

**What it cannot see.** Whether Expander's output is CORRECT (a run is graded
on producing files, never on their bytes). And anything outside the four
families 4.0.2 opens by itself — the rest need DropStuff with Expander
Enhancer, System 7 and not free.

## Finder info, read back — `sitmeta.py` and its three siblings

    tools/vmac/hfscat.py --check IMAGE            the reader, against hls
    tools/vmac/sitmeta.py --plan                  the classic corpus, in boots
    tools/vmac/sitmeta.py --batch N               one boot of Expander 4.0.2
    tools/vmac/sitmeta.py --synth                 the sentinel archives
    tools/vmac/sitmeta.py --run --tag T ARCHIVE...  any archives, one boot
    tools/vmac/sitmeta.py --report [--control] [--by-writer] --tag T...
    tools/vmac/sitmeta.py --writer201             StuffIt Deluxe 2.0.1 writes
    tools/vmac/sitmeta.py --writer351             StuffIt Deluxe 3.5.1 writes (System 7.0.1)
    tools/vmac/sitmeta.py --sit5 ARCHIVE [--plain|--info-only|--files-only]
    tools/vmac/ddmeta.py --writer ; ddmeta.py --reader
    tools/vmac/nowmeta.py --run
    tools/vmac/sdmeta.py

Results: FORMATS.md, *Finder info in the archive*; reasoning: DECISIONS.md
2026-10-17, *the window StuffIt kept in the name*. Results land in
`$UNC_VMAC_HOME/../sitmeta/` as JSON, one file per boot, each header beside
the catalog record it became; `--report` reads them all.

**The instrument is the catalog, not the screen.** `hfscat.py` walks the
catalog B-tree's leaf chain and returns each record whole (offsets from
libhfs's `apple.h`). Its control: every type and creator agrees with `hls`
(145 of 145 on `System6.hfv`), and `--shift 2` makes all 145 disagree.
`patch()` re-reads what it wrote, and MacMount's `fd_location` agrees.

**Two kinds of evidence.** The corpus says what real writers put in the bytes
and what Expander made of it; a SENTINEL archive says which bytes Expander
reads, because every undefined byte names its own offset (`0x01 0x27` can
only come from @38). `--report` lines every catalog field up against every
header byte and holds the measured rules against every entry; `--control`
drops each gate and mask and must disagree — 806 entries on the corpus, 500
of them file flags.

**How a boot runs.** Expander is the boot shell (`mkboot.py`), up to eight
archives sit at the root as `zq00.sit`…, each opened with ⌘E, its name typed
into Standard File, Expand pressed at `expander.py`'s coordinate; Return
after each dismisses any alert, and ⌘Q at the end commits the writes.
`--plan` puts archives whose top-level names collide in different boots. A
path found twice on the volume is reported unmatched, never guessed
(`derived-TaxTemplates1990.sit`'s `README`).

**Three things that cost a boot each:**

- **Wait for a free emulator by process NAME** (`ps -eo comm`), never by
  grepping `ps aux`, which matches another session's wait loop — two sessions
  then wait on each other for good.
- **DiskDoubler checks its header**: +82 is a CRC-16/XMODEM of bytes 0..81;
  without it a sentinel is refused (*"Corrupted file or wrong file type"*).
  `ddmeta.py` recomputes it.
- **StuffIt 5 checks its second block**: b+2 is a CRC-16/ARC over the block
  with that word zeroed; Expander 5.5 refuses a mismatch (*"a disk related
  error (-12043)"*). `--plain` on the same archive isolates the sentinels as
  the cause; `sit5_sentinel` recomputes it, and a no-op call reproduces the
  archive byte for byte.

**What none of them can see.** Get Info comments (the Finder's Desktop file);
any reader but the one each runs (Expander 4.0.2, Expander 5.5, DiskDoubler
3.7, QuickFiler 5.0.1, one SuperDisk! self-extractor); and, for the top-level
folder an expander creates, whether the expander or the Finder chose its
location.

## The downloads, and why none of them are committed

`setup.sh` fetches by URL and verifies by SHA-256, as `fixtures/` does,
because the ROMs and Systems are Apple's copyrighted property:

| file | source | why |
|---|---|---|
| `minivmac.src.tgz` 36.04 | gryphel.com | GPL-2 emulator source, built locally |
| `vMac.ROM` | Internet Archive `mac_rom_archive_-_as_of_8-19-2011`, member `4D1F8172 - MacPlus v3.ROM` | Macintosh Plus ROM — **Apple copyright** |
| `System6.hfv` | Internet Archive `system-6_202607` | System 6.0.8 — **Apple copyright** |
| `Sys7.img` | Internet Archive `AppleMacintoshSystem701` | System 7.0.1 — **Apple copyright** |
| `Sys30.img` | Internet Archive `30_20230725` | System 3.0 / Finder 5.1, 800K HFS — **Apple copyright** |
| `Sys11.img` | Internet Archive `system-1.1_apr1984` | System 1.1, 400K MFS — **Apple copyright** |
| `System_3.x.sit` → `Sys30MFS.img` | Macintosh Garden (`old.mac.gdn`) | System 3.0 on 400K MFS — **Apple copyright** |
| `Mac512K.ROM`, `Mac128K.ROM`, `MacII.ROM` | the same ROM archive, members `28BA4E50`, `28BA61CE`, `9779D2C4` | the 64K-ROM negative and the colour tier — **Apple copyright** |

If a hash ever fails to match, the upstream file changed: check it by hand
rather than editing the expected hash.

## Requirements

`Xvfb` (depth 24 — Mini vMac's X11 glue dies with `BadMatch` on an 8-bit
visual), ImageMagick (`import`, `convert`), `xdotool`, `hfsutils`
(`hformat`/`hmount`/`hcopy`, shipped with Retro68), and a Retro68 toolchain
in `$RETRO68` or `/opt/Retro68-build/toolchain`.

## Mac OS 8.6 under QEMU — booted 2026-10-06, and it does not reach Mac OS

**The retail Mac OS 8.6 install CD is on this disk** (it withdrew BLOCKERS.md's
*"this machine has no Mac OS install media"*), from the host `os9.py --setup`
uses, one 304 MB download:

    mkdir -p ~/.cache/macextract/macos86 && cd ~/.cache/macextract/macos86
    curl -L -o MacOS8.6.7z \
      "https://archive.org/download/mac-os-8.6-working-iso/MacOS%208.6.7z"
    # sha256 02699210106c8f1251be6648c0827bf4d9696628bee3dfc5d23499ecabb78215
    7z x MacOS8.6.7z            # -> MacOS8.6.iso, 665,600,000 B
    hmount MacOS8.6.iso && hdir

`hdir` lists `System Folder`, `Install Mac OS 8.6`, `Utilities` and `CD
Extras` (volume `Mac OS 8.6`, created 1999-04-16). Not committed.

**It does not boot, and the reason is the firmware** (DECISIONS.md
2026-10-06, *the platform the ROM would not admit to*). Four refusals, in the
order a boot meets them:

| gate | what it is | measured |
|---|---|---|
| no blessed folder | `drFndrInfo[0]` is **0**; the System Folder's dir ID **989** written at MDB+0x6C blesses it | prepared |
| no partition map | a bare HFS volume; `media=cdrom` and `media=disk` both fail; `mkapmdisk.clone_head` (the donor head from `MacOS9.img`, Apple_HFS entry repointed) makes OpenBIOS load the ROM | prepared |
| the ROM's own Forth | `System Folder:Mac OS ROM`'s `<BOOT-SCRIPT>` accepts `iMac,1`, `powermac1,1` or `powerbook1,1` only (*"this image is not for this platform"*); QEMU's `mac99` is `PowerMac3,1`; the one-byte edit `powermac1,1` → `powermac3,1` clears it | prepared |
| **`MacOS: "/rtas" not found!`** | the ROM's ELF runs and **Mac OS stops**: `MacOS: Boot Failure! (0xF3C481F6)`. OpenBIOS implements no `/rtas` node | **the wall** |

**`os9.Qemu.settle()` reads True from the first frame of a guest that never
left the firmware**: its `_menubar_present` is mean brightness of the top 20
rows above 0.6, and OpenBIOS's console is black on pale yellow. Every 8.6 run
was read off the frames; `--macos86` screenshots on a fixed interval.

**What tells the two ROMs apart is each file's own prologue**: Mac OS 9's
`Mac OS ROM` (2001-09-25, data fork 2,811,320 B) declares
`<COMPATIBLE>MacRISC</COMPATIBLE>`, tests for `macrisc` and asks for no
`/rtas`; 8.6's (1999-04-05, 1,945,332 B) names three 1998–99 machines and
wants RTAS. Read either without booting:

    hmount MacOS8.6.iso && hcd "System Folder" && hcopy -r ":Mac OS ROM" rom.bin
    head -c 120 rom.bin                       # the <COMPATIBLE> list
    # the <BOOT-SCRIPT> section is plain Forth; find it with
    # `grep -aob "<BOOT-SCRIPT" rom.bin`

**`sitcomment.py --prepare86` builds the three images and `--macos86` boots
the last**; `--machine` picks the machine. Beside the ISO, not committed:
`MacOS8.6-blessed.iso` (refusal 1), `MacOS8.6-apm.img` (1–2),
`MacOS8.6-apm-pm31.img` (1–3) — 2 GB in total, re-used if present.

**What would move it**: an Open Firmware providing `/rtas` (real hardware, or
an OpenBIOS implementing it) or a `Mac OS ROM` that boots 8.6 without one.
Nothing measured says a different 8.x image (the same host's 1.65 GB
`mac-os-8.6-hd.tar.gz`, the 8.5 CD `mac-os-8.5-install-cd-691-2017-a`)
carries a different ROM requirement. **It was never the route to bit 5**,
which closed on 2026-10-06 without it (`sitcomment.py`, above).

## Mac OS 9

`os9.py` boots Mac OS 9.2 under `qemu-system-ppc -M mac99,via=pmu`, headless,
screenshotting through QEMU's monitor, launches the application and checks
what it wrote:

    os9.py --setup                                       # fetch the 2 GB image
    os9.py fixtures/derived-DDT.sit -o shots/ --launch    # one fixture
    os9.py --list os9sample.txt -o shots/ --launch        # the format sample
    os9.py fixtures/foo.sit -o shots/ --hfsplus           # extract onto HFS+

An idle host reaches the Finder in ~110 s. Every fixture boots its own copy of
the master (Mac OS 9 writes to its boot volume); `--keep-boot` is off because
each copy is 2 GB. The master's published SHA-1 is verified before every run;
`--setup --force` re-fetches (BLOCKERS.md, *Corrected figures*).

**Do not point `-o` at a tmpfs** (`/tmp` is one here): the boot copy lands in
the output directory, 2 GB of RAM per fixture, and a host in swap reads as
*"never reached the Finder desktop"* (2026-09-25). `boot_copy()` warns on
`tmpfs` or `ramfs`.

**`os9.py` drives the Finder from the keyboard**: typing selects an icon by
name, Cmd-Down opens it. It types `m`, `a`, `c` (`Mail` is on that desktop
too). **A harness that selects by name depends on that name, and nothing
compiles the dependency.** The pointer works too (*Mac OS 9 with the pointer*,
below; BLOCKERS.md, *Withdrawn claims*).

**Three routes, to separate build from volume.** `--launch` runs the
INTERACTIVE build onto a plain-HFS transfer volume; `--hfsplus` runs the
AUTOTEST build onto the HFS+ boot volume; `--autotest` runs the autotest build
onto a third APM disk named `Out`, so the BUILD is its only difference from
`--launch`, and it reads both channels (the report off `In`, every fork off
`Out`). `--autotest` scores `os9sample.txt` **22/22** on a healthy build, as
`--launch` does (FORMATS.md, *Mac OS 9 tier*). Its verifier grades against the
fixture as the Mac saw it (`archive.sit`, so gzip and `.Z` names compare), and
a fixture both sides refuse passes, printing the reference's message.
Anything needing `-D` is stuck with `--autotest`. `-D UNC_AT_SAMEVOL` points
the sink at the archive's own volume; `Out` must still be mounted
(`FindVolWait` looks it up first), and the run checks it came back empty.

    os9.py fixtures/derived-DandStoQIF2.sea --autotest -o <dir>
    os9.py fixtures/derived-DandStoQIF2.sea --autotest -D UNC_AT_SAMEVOL -o <dir>

**`--hfsplus` writes to a volume the host cannot read.** The boot volume is
HFS+ inside an HFS wrapper (wrapper MDB `0x4244 'BD'`, `drEmbedSigWord`
`0x482B 'H+'`, embedded header at byte 966656 of the partition); hfsutils
mounts the WRAPPER, whose root holds only `Where_have_all_my_files_gone?`.
Renaming the boot volume `Out` in the Finder points the autotest build at it.
The result comes back through `at_report_file()`, a small file on the
plain-HFS input volume with the grid's values plus every output name (the grid
is invisible on a 32-bit screen); that the output landed on HFS+ is checked by
its ABSENCE from the wrapper.

**The reference is `macextract x`, unwrap loop ON**, for the interactive build;
`-nr` is right for the autotest build (`--hfsplus`, the Mini vMac tiers).
**When a harness changes what it drives, its oracle is part of what changed.**

**The sequence runs to the end and says what it waited for** (DECISIONS.md
2026-08-28, *the OS 9 tier's last three keystrokes*):

| shot | what it is | how it is waited for |
|---|---|---|
| `13-sfgetfile` | SFGetFile, `archive.sit` selected | one rectangle changes |
| `14-destination` | SFPutFile, "Extract into this folder:" | one rectangle changes |
| `15-progress` | the progress dialog (`--cancel` only) | one rectangle changes, polled every second |
| `16-result` | "Extraction complete." or "Extraction cancelled." | the screen goes STILL |
| `17-back` | SFGetFile repainted, with the output now listed | one rectangle changes |
| `18-finder` | the Finder, application gone | one rectangle changes |
| `19-names` | a crop of `18-finder` on the volume window | — |

The progress dialog repaints ten times a second, so the result is waited for
with `still()`, which prints how long it took. **Cmd-. quits the
application** (Standard File's Cancel ends the SFGetFile loop), sent through
`ask()` so a keycode name QEMU does not know is reported, not ignored.

**`--cancel` interrupts the extraction**:

    os9.py fixtures/derived-Library_ISBN_Barcoder.sit -o <dir> --launch --cancel

The pass condition is a **strict, non-empty subset**: every file on the volume
byte-exact, at least one entry missing, at least one there; both degenerate
outcomes fail as a broken TEST. **Pick a slow archive**
(`derived-XferIt_1.5b4.sea` extracts in under ten seconds);
`derived-Library_ISBN_Barcoder.sit` (StuffIt 5, 34 entries) is the measured
subject. **The chord is sent until the dialog goes away, and the count is the
measurement**: `ProgressPump()` runs only from `prog_tick`, so a format that
never ticks is not pumping (DECISIONS.md 2026-08-28; `tools/run_ticks.py`).
None landing prints **"Cmd-. DID NOT CANCEL"**. It waits on `PROGRESS_TITLE`
between sends, because "0%  estimating time left" is perfectly still.

**`--cancel-click` cancels through the BUTTON**, with the pointer:

    os9.py fixtures/derived-Library_ISBN_Barcoder.sit -o <dir> --launch \
           --cancel-click
    os9.py ... --cancel-click --click-at 150,168     # the control

- **Park the cursor before the dialog exists** (`goto()` costs ~40 s), while
  SFPutFile is up; `14b-parked.png` shows it (DECISIONS.md 2026-08-28,
  *clicking a dialog that does not exist yet*).
- **HOLD the button**, `Pointer.press(hold=0.9)`: the mouseDown is dequeued up
  to a tick late and `TrackControl` reads a short tap as released outside.
- **A relative `usb-mouse`** (`Qemu(pointer=True)`), never the absolute
  tablet.

`CANCEL_BUTTON` (340,168) is computed from `mac/macextract.r`: `DLOG` 128 at
global (80,80)-(400,190), not autocentred, item 1 of `DITL` 128 at local
(220,78)-(300,98). **The control** `--click-at 150,168` presses the dialog's
background: measured 2026-08-28, the button cancels at the first press (1 of
34 written), the background does not (all 34, the run FAILS as a late cancel).

**`--encrypted` answers the password dialog**, and brings its own archive:

    os9.py --encrypted --launch -o <dir>          # no fixture: it makes one

`tools/synth_crypt.py`'s StuffIt classic DES archive (three entries, password
`hushnow`), as **MacBinary** (`'MKey'` 0 is in the resource fork);
`verify_output()` gets the password for the reference. A **wrong** password
goes first and must be refused; both dialogs are keyboard work (`PassFilter`).
**Wait over the right rectangle**: the refusal changes only the MESSAGE —
0.43 % of the window in 123 s, 19 % of `PASSWORD_MSG` in 4 s (DECISIONS.md
2026-08-28, *the password dialog on Mac OS 9*).

**`19-names.png` photographs an 8-bit name**: `synth-packit-2.pit`'s `App` +
MacRoman `CC A9` draws as `AppÃ©` in the Finder and in Standard File
(`17-back.png`) — what the Linux CLI prints (`cli/main.c`, `macroman_high`).

**Names**: the Mac writes each component as `ComponentToStr63()` does (`':'`
back to `'/'`, cut at 31), so `verify_output()` maps reference names through
`mac_leaf()` first and fails outright when two map to ONE Mac name (the shell
numbers the second `~1`; `tools/run_macnames.py`). **So this tier cannot see
an over-long name**; `run_names.py` covers that.

**The result is checked off the disk image**: after the emulator exits,
`verify_output()` lifts the Apple_HFS partition out, pulls each file off with
`hcopy -m` and compares **both forks byte for byte**. A volume the guest never
flushed fails to mount.

`mkapmdisk.py` clones its partition map and drivers from a disk Mac OS 9
already mounts and repoints only the `Apple_HFS` entry; a hand-built map was
silently ignored.

## What every walk can see — `walkprobe.py`

Harnesses here grade what an application wrote by listing a Macintosh volume
with `hls` or `hdir`. This builds one volume holding every shape that tells
listings apart — a plain file, an INVISIBLE one, a dotted one with the
invisible bit CLEAR, and `Icon\r`, at the root, inside a folder and inside an
INVISIBLE folder, plus one LOCKED file — runs every walk in the tree against
it, and says which came back short. No emulator, no ROM, no X server; seconds.

    tools/vmac/walkprobe.py            # the table
    tools/vmac/walkprobe.py --check    # and assert it against the EXPECT_* sets

**Twelve** subjects and **four** columns (2026-09-23; `--check` reproduces it):

| walk | invisible file | descends | invisible folder | locked file |
|---|---|---|---|---|
| `checkdisk.walk` | 4/4 | yes | 4/4 | yes |
| `os9._walk_volume` | 4/4 | yes | 4/4 | yes |
| `arcmac.read_volume` | 4/4 | no | — | yes |
| `nowcompress.read_volume` | 4/4 | no | — | yes |
| `nowcompress.read_forks` | 4/4 | yes | 4/4 | yes |
| `diskdoubler.volume_files` | 4/4 | yes | 4/4 | yes |
| `cptsegment.read_volume` | 4/4 | no | — | yes |
| `cptcrypt.read_volume` | 4/4 | no | — | yes |
| `superdisk.read_forks` | 4/4 | yes | 4/4 | yes |
| `interactive.volume_entries` | 4/4 | no | — | yes |
| `macmime.HFS.ls` | 4/4 | no | — | yes |
| `mkboot.HFS.ls` | **4/4** | no | — | yes |

The root-only walks list ONE directory by design; their callers walk depth
themselves or read volumes built flat, which `EXPECT_FLAT` records.
`EXPECT_BLIND` and `EXPECT_NO_LOCKED` are empty and kept, because they fail in
the other direction: take `-a` out of any walk and the probe names it.
**`--check` can fail, and every column has been made to.**

**Read listings as bytes, split on `b"\n"`.** `text=True` applies universal
newlines, which cut `Icon\r` at its carriage return: `mkboot.HFS.ls` came
back 3/4 (and `verify_stripped` is built on it), and the Compact Pro walks
handed `hcopy` a file named `Icon`. `hdir` prints the CR verbatim.

**A locked file is not an `-a` question**: `hdir` prints it with a leading
`F`, so a walk keeping lines on `line.startswith("f")` throws locked files
away. One locked item exists across the cache's 84 images —
`[DiskExpress Activity Log]` on the Norton DiskDoubler Pro floppy, invisible
AND locked. **An invisible FOLDER** is its own cell: Now QuickFiler creates
`[Now QuickFiler Folder]` (invisible) holding a visible `NCdb`/`NCex`
database, on six kept `specimens/now/*` volumes.

**Four callers hold EVERY guest entry against our extraction**
(`--adjudicate` in `superdisk.py`, `nowcompress.py` and `diskdoubler.py`, and
`superdisk.py --nest`), which is why the `FINDER_OWN` filter lives inside
`superdisk.read_forks` rather than in its 38 call sites; all four were re-run
and it dropped exactly `Desktop DB` and `Desktop DF`. **Every walk prints what
its filter dropped, on every run**, so the filter is a measurement:
`cptsegment` and `cptcrypt` drop `Desktop`; `nowcompress` `Desktop` and
`[Now QuickFiler Folder]`; `diskdoubler --wild` on the 3.7 disk `Desktop`
(still 10 compressed files). The template is `arcmac.read_volume`: `-a`, a
filter measured on the harness's own volume (`hls -a -1` adds exactly
`Desktop`, FNDR/ERIK), raw bytes for `hcopy`, one Mini vMac re-run.
`FINDER_OWN` lives in `mkboot.py`, the module with no imports of its own. The
rest of `spacesaver.py` is unexercised under `-a` and selects by name or
creator — an expectation, not a measurement.

**Survey by CAPABILITY, not spelling** (grepping for `hls` missed the `hdir`
walks; grepping for `read_forks` conflated two functions of that name). An
`ast` walk finds 30 functions in `tools/` that run `hls` or `hdir`, and all 30
pass `-a` since 2026-09-23 — including the ones `walkprobe.py` cannot grade:
`interactive.read_joined`, `rescomp.report`, `sitcrypt.list_folder`,
`expander.app_from_image`, `spacesaver.lift_installer`, `os9.wrapper_names`
(a NEGATIVE, which a blind listing makes easiest to satisfy) and
`mkboot.verify_stripped` (an invisible `Ghost INIT` passed it; `ls()` takes
`-a` as a parameter because `strip_system_folder` deletes what `ls` returns
and `Desktop` is kept on purpose).

The re-survey is one command:

    python3 - <<'EOF'   # any function in tools/ that lists a volume
    import ast, os
    for r, d, fs in os.walk("tools"):
        d[:] = [x for x in d if x != "__pycache__"]
        for f in fs:
            if not f.endswith(".py"): continue
            p = os.path.join(r, f); src = open(p).read()
            for n in ast.walk(ast.parse(src)):
                if not isinstance(n, ast.FunctionDef): continue
                seg = "\n".join(src.splitlines()[n.lineno-1:n.end_lineno])
                if any(t in seg for t in ('"hls"', 'b"hls"', '"hdir"', 'b"hdir"')):
                    ok = '"-a"' in seg or 'b"-a"' in seg or "invisible=True" in seg
                    if not ok: print("BLIND", p, n.lineno, n.name)
    EOF

**What it cannot see:** whether a blind walk ever lost something — that
depends on whether the application it grades writes invisible files. The one
case called a real risk was not: no ArcMac header here sets the invisible bit
(BLOCKERS.md, *Withdrawn claims*).

## Mac OS 9 with the pointer — `os9mouse.py`

`os9.py`'s keyboard route cannot operate an application: click a checkbox,
walk an installer, answer a dialog. `os9mouse.py` does; it produced the
StuffIt 5 encryption specimens (FORMATS.md, *StuffIt 5's RC4*).

    python3 -c "import sys; sys.path.insert(0,'tools/vmac'); import os9mouse; \
                m = os9mouse.Mac(cd=True); m.settle(); m.png('desk')"

It is a module, because every session is a different dozen steps. The
positioning algorithm is `Pointer`, which takes a "send these monitor
commands" and a "give me a frame" and belongs to neither guest: `Mac` hands it
its own, and `os9.py` hands it `Qemu`'s for `--cancel-click`.

| call | does |
|---|---|
| `Mac(cd=True, xfer=True)` | boot from a qcow2 overlay on the 2 GB master, with the Deluxe CD and the transfer volume attached |
| `Mac(attach=True)` | connect to a guest already running, so successive scripts drive one boot |
| `m.goto(x, y)` / `m.click(x, y, double=)` | closed-loop positioning, then a click |
| `m.key("meta_l-s")`, `m.typestr("text")` | keystrokes; **prefer these** — see the timing note |
| `m.shot(tag)` / `m.png(tag)` | screendump straight to PPM (no ImageMagick) and a PNG to look at |
| `m.settle()` | wait until the screen stops changing, with a floor |
| `find_not_yet(frame)` | locate DropStuff's "Not Yet" button, which moves |

From the module's docstring: the absolute pointer is inert; the menu-bar clock
and a blinking caret defeat frame-differencing (hence `largest_blob`);
positioning takes ~40 s, longer than a sticky menu stays open, so use Command
keys; DropStuff's nag shuffles its buttons, so the label is matched.

**Getting a file back out**: write it to the plain-HFS transfer volume,
unmount that volume inside the guest (select it, Cmd-Y) so it flushes, and
read the Apple_HFS partition with hfsutils. The boot volume is HFS+.

### What the pointer cannot select, on either emulator

**Measured on both guests, 2026-09-27.** On Mini vMac's hierarchical
submenus (`sitcrypt.py`, *the Translate menu*), the submenu opens and the
parent stays highlighted, but the item under the pointer never highlights and
the release selects nothing (three ways in tried). On **Mac OS 9 under QEMU,
DropStuff's TOP-LEVEL `File` menu**: clicking title then item fails because
`goto()`'s ~40 s outlasts the sticky menu (`shots/c_ds_prefs.png`); holding
the button and stepping in keeps the menu open (`shots/c_ds_menu_held.png`)
but **no item highlights**.

So on Mini vMac, reach a menu item by its **Command key**; DropStuff's
`Stuff…` (⌘S) and `Quit` (⌘Q) are drivable, its keyless `Preferences…` was
not. (A System 6 submenu did work once — *A hierarchical submenu DOES open
here*, under `sitopt.py` below — so a submenu is worth one attempt.)

**On Mac OS 9 the held press DOES select, sometimes — corrected 2026-10-23**
(BLOCKERS.md, *Withdrawn claims*). StuffIt Deluxe 7.0.3's keyless `Translate ▸
Expand…` was selected twice: `goto` the title, `mouse_button 1` and a 1.2 s
wait, ONE `step(10, 24)` packet, 1.2 s, release (`as703.py --set boxes`,
`37-translate-held.png`). DropStuff's did not; the difference is not reduced
(one short packet against several, the wait, or the application). A Command
key where there is one, one attempt at a held press where there is not.

**DRAGGING works**: pressing on an application icon, stepping 882 px across
the screen and releasing over a volume copied it (`shots/h_drag_over.png`,
`shots/h_dropped.png`, 2026-09-27) — the limit is the Menu Manager, not
press-move-release. **Held moves are not 1:1** (2026-10-23, Finder): a
requested 60, 60 travelled about 47, 50, and five 25 px packets about 83, so
an open-loop drag 125 px dropped short. Step, photograph, correct, then
release. Where two icons overlap a press takes the one on top; press on the
wanted icon's NAME. There is no `drag()` helper; it is four lines:

    m.goto(sx, sy)
    m.burst(["mouse_button 1"], wait=0.6)
    m.step(dx, dy)                       # splits into <=40 px packets itself
    m.burst(["mouse_button 0"], wait=2.0)

### A plain-HFS Mac OS 9 boot volume — `hfsboot.img`

`$UNC_VMAC_HOME/../sit5/hfsboot.img` is a 1 GB **Mac OS Standard** volume
carrying a bootable System Folder, built 2026-09-27 with no install media:

    tools/vmac/mkapmdisk.py <MacOS9.img> hfsboot.img 1024 HFSBoot
    # attach as a fourth drive, drag the System Folder onto it inside the
    # guest (1,751 items, ~215 MB, about five minutes), then Cmd-Y to flush

Relaunch with it as `index=0` and it is the startup disk: it sits at the top
of the desktop volume icons, the *"did not shut down properly"* alert stops,
and the HFS+ volume gains ~500 MB as its swapfile goes idle — **that is how to
tell which volume booted**. hfsutils can write it, which is what `sitzip.py`
places software through. (*"StuffIt Deluxe 5.0.1 needs an HFS boot volume"*
is withdrawn: its alert comes up in all four combinations, so the trigger is
Mac OS 9.2; BLOCKERS.md, *Withdrawn claims*.)

## A colour Finder — `colouricon.py`

**Mini vMac is not only a Plus.** `-m II` emulates a Macintosh II, and
`-depth` fixes its colour depth at build time: `setup.sh` builds `mv-II16`
(16 colours) and `mv-II256` (256) on `MacII.ROM`. It is the one tier here
that draws `icl4`/`ics4` (BLOCKERS.md, *Withdrawn claims*) and shows an icon
SELECTED in colour.

The stock `Sys7.img` will not start it (a "Minimal" Plus install). The System
used is an installed **System 7.5.5** volume, Macintosh Repository item 73348,
*Mac OS 7.5.5 for Mini vMac*: `macosinstall755.rar`, 27,594,360 B, SHA-256
`14f511e3adf0599c36f2ca1b5d6de110b91cb4cc66374c5e328069de720a9d26`, holding a
100 MB `macosinstall755.dsk`. Its download is a form POST
(`download.php?u=0&id=65475&go=1` with its hidden `d` and `via_http=1`, and
the session cookie), so `setup.sh` does not fetch it. Copy the `.dsk` per run,
`hdel "Desktop DB" "Desktop DF"` so the Finder reads the icon afresh, and
`hcopy -m dist/MacExtract.bin :MacExtract`. Then:

    colouricon.py --emu mv-II256 run.img shot \
        c:474,355 w:40 d:598,45 w:8 s c:330,255 s c:202,200 s

dismisses the "not shut down properly" alert, opens the volume, and
photographs it plain, with MacExtract selected and with SimpleText selected.
The coordinates are that volume's, measured off its frames. What it cannot see
is in the script's docstring; the results are DECISIONS.md 2026-10-11, *the
icon that did not darken*, and `docs/screens/0c-icon-selected-256.png`,
`0d-icon-selected-16.png`.

## Checking a run off the disk instead of off the screen

`run.py`'s grid carries a file count, two summed CRC-32s and two summed
lengths — **a summed CRC cannot carry a filename** (a wrong gzip/.Z fallback
name lived in the corpus for weeks because of it). Mini vMac's write-back is
complete ("lazy and partial" is withdrawn, BLOCKERS.md), so the Out volume is
read back:

    run.py --keep-disks --list sample.txt      # keep each run's disk images
    checkdisk.py /tmp/vmacrun-*/               # read them back

**55/55 byte-exact** when it was established (2026-08-02), both forks, names
and folder structure included — `derived-RWAsm_Folder.sit` at 38 files and 73
forks, an 8-bit `spinning brain ƒ` folder, a MacRoman `Appé`, a `.DS_Store`.

`checkdisk.py` identifies each run's fixture from the `in.dsk` beside the
`out.dsk`, and feeds the reference extraction a copy named `archive.sit` (the
name the Mac saw), because gzip and .Z derive their output name from it.
**`--fixture PATH` names an archive not in `fixtures/`** (repeatable),
matched by CONTENT; without it a generated subject (`tools/synth_*.py`) skips
with "cannot identify the fixture".

**Its walk raises past depth 26** (since 2026-10-07; it silently returned
`[]` past 8, which reads as files MISSING ON THE MAC). `walk(dirs=True)` adds
the FOLDERS, which an assertion that a folder must NOT exist needs, or it
cannot fail.

**It has to know what the Mac does to a name — two rules**
(`tools/vmac_check.py`, `mac_component`): every component is fitted to 31
characters with its extension KEPT, and a StuffIt 5 name (UTF-8) is folded
into the bytes an HFS name holds, so a Japanese name arrives as a row of `_`.
The fold applies only where `macextract sniff` says the names are UTF-8.
**Fold before normalizing**: `ユーザーライセンスの購入.rtf` is DECOMPOSED in
the archive, thirteen code points where the composed spelling is twelve, so an
NFC fold predicts one `_` too few. The oracle manifests hold the composed
spelling, which `run_diff.py` normalizes away and this cannot.

Three hfsutils traps, worth knowing before writing anything similar:

- **`hls` hides a file whose Finder INVISIBLE bit is set** unless given `-a`,
  and **the leading dot has nothing to do with it** (measured as a 2x2 by
  `walkprobe.py`). `.DS_Store` needs the flag because a Macintosh writes it
  invisible; `Icon\r` (51,781 bytes of resource fork) was reported MISSING
  from a Mac OS 9 volume that held it.
- **Do not `rstrip()` `hls -1`'s output.** A carriage return is a legal HFS
  name character and the last one of `Icon\r`. Split on `\n`.
- **Every path argument must be encoded as MacRoman**, not UTF-8, or any 8-bit
  name is a file that does not exist (`os9.py`'s `_walk_volume` listed
  `Terrainman 2.0 ƒ` as empty until 2026-09-04).

All three were right in `checkdisk.py` before `os9.py` learned them: a harness
written twice learns once. *What every walk can see*, above, asks the same of
every walk.

## The Finder metadata, read off the disk — `hfscat.py`, `metarun.py`

    metarun.py --system System6.hfv          # or --sys30
    metarun.py --system Sys7.img --out-kb 8192
    metarun.py --check .tmp/vmacrun-*/       # re-grade disks a run kept
    metarun.py --expander                    # StuffIt classic, against Expander 4.0.2
    metarun.py --check-expander .tmp/vmacrun-*/
    hfscat.py out.dsk [--json] [--fcmt DeskTop]   # its control: *Finder info, read back*

`hfscat.py` walks an HFS image's catalog B-tree (libhfs's `apple.h` layout)
and prints per file the whole FInfo and FXInfo, three dates and the locked
bit, per folder the DInfo, DXInfo and dates; `--fcmt` lists a System
6-or-earlier `Desktop` file's `FCMT` comments. `metarun.py` runs
`synth-as-meta.as`, `synth-sqp-meta.pkg`, a generated `nested.pkg` (A/x,
A/B/y, A/z, folder dates held across a subfolder), `synth-macosx.zip` (Mac OS
X's sidecars) and `synth-macosx-spot.zip` (their Spotlight comments, folded
into MacRoman; on 7.0.1 the Desktop Manager gives back 199 bytes of a
255-byte comment) with `-D UNC_AT_DTCOMMENT`, keeps the disks (`sys30.py
--keep-disks` too), and grades every value against the synthesizers' input,
allowing the shell's one deliberate change (fdComment cleared; inited is kept
where the Finder info is stated). Results: DECISIONS.md 2026-10-17, *the
metadata, carried to the disk*.

**`--expander`** runs seven corpus archives covering every StuffIt classic
writer class, and the 17 sentinel archives Expander extracted whole, through
the application (`run.py --keep-disks --expect`, one boot each, about 5 s
all-out), and holds every catalog record on the output disk to the one
StuffIt Expander 4.0.2 wrote for the same entry (`sitmeta.py`'s results):
FInfo/DInfo, FXInfo/DXInfo, three dates, the lock. No difference is allowed
(DECISIONS.md 2026-10-18, *the icon Expander registers*). Its control is
built in (Expander's records, one byte shifted); a second was run once:
`origin/main`'s application, 112 of 496 values wrong (DECISIONS.md
2026-10-17, *the window Expander puts back*). It needs `build/rel/macextract`
for run.py's own verdict.

**`-D UNC_AT_DTCOMMENT`** appends a `DTCM` trailer to the autotest report:
what `PBHGetVolParms` and `PBDTGetPath` answer on the output volume, and each
file's comment via `PBDTGetComment` — the half no host tool reads off a System
7 disk. It writes the file, **ejects In**, then paints the grid; without the
eject the report never reached `in.dsk` on System 6.0.8 (three runs).

**A System 7.0.1 floppy has no Desktop Manager** (vMAttrib 0xE0), so the
comment needs `--out-kb 8192` there; on System 3.0 and 6.0.8 no volume has
one.

**What they cannot see.** The extents-overflow file (`hfscat.py` refuses a
catalog that continues there), HFS+, MFS, a partition map. `Desktop DB`. What
the Finder then does with any of it. A folder's comment: neither fixture gives
a folder one. **An output that is not a volume's root**: both extract to Out's
root, where directory 0 and the root agree (DECISIONS.md 2026-10-18, *the
comment the root kept*).

### Dates in the Macintosh's zone — `tzrun.py`

    tzrun.py                                   # the four tiers, synth-exo-tar.tar
    tzrun.py --tier sys7-tz fixtures/derived-MUSFMT10.ZIP   # wall clocks: none move
    tzrun.py --check sys7-tz .tmp/vmacrun-*/   # re-grade a kept run

Extracts one archive per tier with `--keep-disks` and holds every catalog date
to `l --meta`: a date marked `Z` moves by the tier's zone, every other one
not. **This Mini vMac keeps no PRAM between launches** — `RTC_Init` zeroes it
and writes the location record at 0xE4..0xEF from three globals, 0 on X11 —
so `setup.sh` builds `mv-4M-tz` with those globals patched (5 h west, a
non-zero location). Tiers: System 7.0.1 on `mv-4M-tz` (−18,000 s) and on
`mv-4M` (never set: 0), System 6.0.8 on `mv-4M-tz` (−18,000 s), System 3.0 on
`mv-4M-tz` (no Gestalt: 0). Results: DECISIONS.md 2026-10-17, *dates in the
Macintosh's own zone*.

**What it cannot see.** The Map control panel itself, and its daylight-saving
box. Mac OS 9. A 512 KB machine.

### What the Finder does with a restored position — `finderpos.py`

    finderpos.py -o DIR                                  # System 7.0.1
    finderpos.py -o DIR --system System6.hfv --out-at 472,108
    finderpos.py -o DIR --seeded [...]     # onto a volume with a desktop
    finderpos.py -o DIR --seeded --creator zQx7 --launch --rebuild 2 \
        -DUNC_AT_NODTREG                   # the control, launched, rebuilt

Extracts a generated package (a folder with a window rectangle, three files
placed off any automatic grid, and MacExtract itself as an application) with
the current tree's autotest build onto an 8 MB volume, opens the volume and
folder in the Finder, photographs them, chooses Shut Down and reads the
catalog back: what the Finder moved, and whether it registered the
application's bundle (`Desktop` resources on System 6, a count of the creator
in `Desktop DB` on System 7). `--seeded` first boots the blank volume once in
the Finder, so it has a desktop (`run.py --out-from IMG`). System 6 has no
type-select, so `--out-at` is the volume's desktop icon; without it the run
photographs the desktop and stops. `--creator` gives the application a
signature no desktop has seen; `--launch` opens and quits it; `--rebuild N`
boots again with Command-Option held; `--out-kb 1440` is a floppy; `-D` passes
a build switch (`UNC_AT_NODTREG`, the control without the bundle
registration). Results: DECISIONS.md 2026-10-17, *the bit that kept the
position*, and 2026-10-18, *the icon Expander registers*.

**Two traps.** Typing before `Mac.origin()` sends the keys to the X root, and
`Mac.shot()` parks the pointer, so a held menu photographed with it is
released off-screen — Shut Down never ran and the image was torn.

**What it cannot see.** System 3.0; Mac OS 9 (a one-off driver over `os9.py`,
*the icon Expander registers*); the icon after `--rebuild`, whose volume
window opens behind the folder's; how the Finder places what it relocates,
beyond the catalog and the frame; System 7's `Desktop DB` beyond a byte count.

## On-demand probes — the `-D` switches and the one-off harnesses

Every switch below rebuilds the autotest application and answers one question
the normal replay cannot. The first two change the BUILD (which overlay
lifetime, or none); the rest add a probe. None is part of any suite. **A `-D`
the CMakeLists does not know is silently ignored** — `run.py` passes it
through the environment and CMake drops what it has no rule for, so a probe
can "work" and change nothing. Check that its numbers moved before believing
them. Results are not repeated here; each line says where they live.

**`run.py --as NAME` chooses the archive's NAME on the In floppy** (default
`archive.sit`; the autotest opens the first root file called `archive.*`).
The shell dispatches on the extension before it reads a byte, so a name is an
input: `--as archive.zip` found every plain zip failing (DECISIONS.md
2026-10-11, *the zip that was a set of one*). **What it cannot see:** the
sweeps run under the default, so a path reached only by another extension
(`.NNN`, `.zNN`, the gzip/.Z fallback name) is tested only when asked for.

| switch | answers | where the result is |
|---|---|---|
| `UNC_OVL_LAZY` | the OTHER overlay lifetime: one image per format, read when a format wants it, instead of the shipped bundle-at-launch. A boolean, so every harness can pass it | FORMATS.md, *Overlays* |
| `UNC_OVL_RESIDENT` | every decoder linked in, no images (the application before 2026-09-25) — the CONTROL for any budget claim about the overlays | FORMATS.md, *Overlays* |
| `UNC_AT_BUDGET` | why an entry was refused: over budget, or `NewPtr` failed | below; DECISIONS.md 2026-08-06 |
| `UNC_AT_RESERVE` | what the shell needs of the heap kept back from the engine — a `FreeMem()` low-water mark on the completion alert; it priced `kMemReserveMax` from 80 KB down to 48 KB (13,242 B measured). **Needs a fixture that FITS and is heavy**: a small one never fires the progress pump, a big one is refused before the heap is stressed | FORMATS.md, *Budget* |
| `UNC_AT_STACK` | what `kStackBump` is worth: paints the region between ApplLimit and the stack base at launch and reads back how far down anything wrote. **Read the watermark, not the first transition** — a frame holding an uninitialised buffer leaves clean longs inside it. Autotest under-reads the shipped build, which has the dialogs | FORMATS.md, *Stack* |
| `UNC_AT_HANDLES` | does `MoveHHi` move an engine block, and does it help | below; DECISIONS.md 2026-08-06, *the Arsenic block's first allocation is sized from the entry* |
| `UNC_AT_INTERLEAVE` | do reads return zeros while output is written to the same volume | BLOCKERS.md *Withdrawn claims* |
| `UNC_AT_SAMEVOL` | does extraction onto the archive's own volume work | DECISIONS.md 2026-08-02 |
| `UNC_AT_WD` | is `SFReply.vRefNum` handled as a System 7 working directory | DECISIONS.md 2026-08-01 |
| `UNC_AT_CANCEL` | does an aborted entry leave anything behind | BLOCKERS.md, MANUAL_TESTS.md checklist |
| `UNC_OVL_NOFLUSH` | whether the overlay loader's instruction-cache flush is NEEDED: `ovl_flush_code` a bare return (2 B against 106 shipped). Only a CPU with a cache can answer: built with `tools/build_mac.sh` (`UNC_MAC_BUILD_DIR=build/mac-noflush`), renamed in its MacBinary header, run on real hardware beside the shipped build | DECISIONS.md 2026-10-12, *the flush the LC 475 did not need* |
| `UNC_AT_TWICE` | what a second extraction into the same folder makes of the first one's folders. FAILs by construction (the grid counts both runs); read the Out disk with `--keep-disks` and `hls -R` | DECISIONS.md 2026-10-11, *the folder that is already there* |
| `UNC_AT_NOHIDECURSOR` | is `HideCursor()` before painting the grid necessary — yes. The pointer must be INSIDE the emulator window (at (144,129) on the 800x600 Xvfb) and the drag must cross cell CENTRES; `UNC_VMAC_PARK` overrides the parking position | BLOCKERS.md |
| `UNC_AT_PROGRESS` | how fast the engine is going, mid-run (the byte counter in the grid) | BLOCKERS.md "Timing on a 7 MHz Mac Plus" |
| `UNC_MAC_SLURP_ARCHIVE` | rebuilds the old read-whole-archive-into-RAM path | DECISIONS.md 2026-08-02 |
| `UNC_AT_TIMING` | the extraction split into File Manager reads, writes, the rest of the File Manager and the engine, in TICKS, in grid slots 3-6, the harness read-back in slot 7 (so the CRC check FAILS by construction — read the numbers) | FORMATS.md, *What -O3 is worth, and where* |
| `UNC_AT_TICKGAP` | how long a click waits: the widest gap between two progress callbacks in TICKS (File Manager time included), the input position either side, the gaps before the first and after the last, the count, and `RunExtract`'s duration (`run=`). The grid is untouched, so the run still grades; `run.py` prints the rest from the report file. Run at `--emu mv-4M-1x`. **Cannot see:** the bar's redraw, the 10 Hz gate's up to 0.1 s, another process to switch to, what AppleShare or a slow disk adds | FORMATS.md, *How long a click waits* |
| `UNC_MAC_STAGE_WRITES` | the older whole-fork staging write path (also in `ci.sh`) | TESTING.md |
| `UNC_AT_DTCOMMENT`, `UNC_AT_NODTREG` | the Desktop Manager comment read-back; the control without bundle registration | *The Finder metadata, read off the disk*, *What the Finder does with a restored position*, above |

### Filling the destination on purpose — `--out-kb`

    run.py --mem 1M --out-kb 800 fixtures/derived-OTCFM68KGlue.sit

`hformat` refuses anything under 800 KB, so the fixture must output more:
`derived-OTCFM68KGlue.sit` (17 entries, ~1 MB out) and
`derived-XferIt_1.5b4.sea` (10 entries, 926 KB out) both do. It reports FAIL
by construction. **Read the numbers**: 9 files written, `errors` = **1**,
`ret` = −9 (`UNC_ERR_SINK`), the eight remaining entries never attempted —
every extractor ends the archive on a sink failure (the withdrawn
one-error-per-entry claim, BLOCKERS.md).

**The default is a 1,440 KB floppy, a limit in the OTHER direction too.** A
single entry larger than the volume fails at `SetEOF` about twenty seconds
in, `ret` −9, and reads like a per-entry memory refusal unless the `ret` slot
is read: `derived-EasyFind.dmg.sit`, one entry of 1,851,907 B, needs
`--out-kb 2400` (BLOCKERS.md, *Withdrawn claims*, 2026-09-18). A fixture
capped near its memory minimum walks a low rung of Arsenic's sampled index,
long even all-out — XMenu 704 s, EasyFind 1,427 s at 562,000 B — so use
`--timeout 1700`, or a timeout reads as a refusal too.

**What it cannot see:** the alert the user is shown (the interactive build;
`interactive.py`). The message is chosen from `gLastWriteErr`, and only the
choosing is untested.

### Why an entry is refused — `UNC_AT_BUDGET`

    run.py --mem 1M -D UNC_AT_BUDGET fixtures/<fixture>

The grid carries what the engine **used**, never what it was **allowed**, and
`mal_alloc` returns NULL for two unrelated reasons with opposite fixes. The
probe overwrites the slots:

| grid slot | carries |
|---|---|
| `nfiles` | address of the largest live block |
| `ret` | **`gShortBy`** — how much more budget the first refused request needed |
| `sumDataCRC` | `FreeMem()` at the start of the run, before the reserve |
| `peak heap` | **the budget** — what the engine was actually given |
| `errors` | `MaxBlock()` at the first refusal |
| `totalDataLen` | application zone bottom (`ApplicationZone()`) |
| `sumRsrcCRC` | 1 = over budget, 2 = `NewPtr` returned NULL |
| `totalRsrcLen` | `ApplLimit` |

(Corrected 2026-08-31: the free figure and the budget were overwritten before
reaching the grid.) `FreeMem()` minus `MaxBlock()`, both **at the refusal**,
is the fragmentation; free heap at the start does not give it. The refused
size, free-at-refusal and held-at-refusal of earlier revisions are in
DECISIONS.md 2026-08-06; edit the `UNC_AT_BUDGET` block to swap them back. It
reports FAIL by construction. **Read the numbers, not the verdict.**

**The completion alert's fields reach a sweep too** (since 2026-10-10): the
autotest writes `e1` (first per-entry status) and the overlay diagnostics `wa
kf rf fc fn` (`mac/ovl_load.h`) to the report FILE on `In` after the eight
grid values, and `run.py`, `sys30.py` and `os9.py --autotest` print them as
`[e1= wa= kf= rf= fc= fn= bg= short= why= free0=]`. The probe build ejects
`In` after writing it (Mini vMac flushes on eject). On a healthy run `wa`,
`kf`, `short` and `why` are 0; `rf` is the `UncFormat` the release kept for,
0 when no layer released (an envelope keeps the bundle); `fc` is the flush
route (0 none, 1 `_HWPriv`, 2 `FlushCodeCache`) and `fn` its calls. **What it
cannot see:** `rf` is the last releasing layer's only, and `bg`/`short` the
last budget's — a `.sit.hqx` re-takes one per layer.

**Pair it with `-D UNC_OVL_RESIDENT` for a budget that can be subtracted from
another.** The switch costs the eager configuration 400 B of `CODE` + A5 and
the control 304 B, so a grant compared against a base from a DIFFERENT build
carries the difference as a mystery — 2,926 B of "residue" on 2026-09-27
(FORMATS.md, *Three configurations, one tree*; DECISIONS.md 2026-09-27, *the
residue that was two numbers*).

`UNC_AT_HANDLES` swaps the engine allocator to `NewHandle` + `MoveHHi` +
`HLock` (the reverted remedy, kept buildable) and reports the block's
**address** either side of `MoveHHi` (`MaxBlock` is blind to where a block
sits, and could not fail). It instruments the first allocation of 64 KB or
more, which may be StuffIt's combined io/output buffer rather than the
Arsenic block — it proves `MoveHHi` moves *an* engine block.

### The same-volume and interleaved-read questions

    run.py -D UNC_AT_INTERLEAVE fixtures/derived-EmpireBuilderDemo.sit
    run.py -D UNC_AT_INTERLEAVE --mem 1M fixtures/derived-EmpireBuilderDemo.sit
    run.py -D UNC_AT_INTERLEAVE fixtures/derived-PCCTS.tar
    run.py -D UNC_AT_SAMEVOL --list sample.txt

The first reads one file three ways on one volume — undisturbed, in 4 KB
chunks with a file created and written between every chunk, and seeking with
`SetFPos` before each read — and compares CRC-32s. The second points the
output at the archive's own volume, which is what the interactive application
does and no other run here does.

### Working directories, without a Finder

    run.py -D UNC_AT_WD fixtures/derived-EmpireBuilderDemo.sit

Makes a real working directory over a real subfolder with `PBOpenWD` and
extracts through it as `ExtractOne()` does, counting what landed in the folder
and what leaked to the root. Every other harness extracts into a volume root,
where a working directory and the root are the same directory.

### Name collisions — `mkcollide.py`

    mkcollide.py /tmp/collide.tar
    run.py --keep-disks /tmp/collide.tar
    mkcollide.py --verify <that run's out.dsk>

`BumpName()` appends `~1`..`~9` when a sanitized name exists, and **nothing in
the corpus exercises it**: no two entries across the manifests collide under
the Mac's rules (case-insensitive HFS, 31-character components, `:` <-> `/`;
measured 2026-08-08). Five entries collide two ways, each payload distinct and
self-identifying, so the check is "the right bytes under the right name":

| archive entry | on the Mac | payload |
|---|---|---|
| `README` | `README` | upper case |
| `readme` | `readme~1` | lower case |
| `collide-me-when-truncated-to-31-alpha` | `collide-me-when-truncated-to-31` | alpha |
| `collide-me-when-truncated-to-31-beta` | `collide-me-when-truncated-to-~1` | beta |
| `collide-me-when-truncated-to-31-gamma` | `collide-me-when-truncated-to-~2` | gamma |

All five arrive, none overwrites another, and the 29-character clamp is
visible (`collide-me-when-truncated-to-` is 29, then `~1` makes 31). Archive
order decides who keeps the plain name.

### The `SIZE` partition

    sed -i 's/2048 \* 1024, 400 \* 1024/600 * 1024, 400 * 1024/' mac/macextract.r
    run.py --system Sys7.img fixtures/derived-KeyGraphics.sit
    run.py                   fixtures/derived-KeyGraphics.sit
    os9.py fixtures/derived-KeyGraphics.sit -o <dir> --hfsplus --expect-refusal
    git checkout mac/macextract.r        # the edit is temporary, on purpose

A partition big enough to launch and too small for a 512 KB Arsenic block,
against a fixture that needs ~656 KB and passes at 4 MB. `--expect-refusal`
passes only when the Linux engine DOES extract the fixture, the Mac writes
nothing, the archive returns `UNC_OK`, and an entry is counted as refused —
without the first condition it would pass on an empty archive. Three-system
table in FORMATS.md.

### Forcing a memory refusal on screen

A partition is only enforced under MultiFinder (System 7 and up), so the
`SIZE` route is two boots and a Get Info. Capping the budget in a throwaway
build is cheaper, on any system `interactive.py` drives:

    sed -i 's/a->budget = freenow - reserve;/a->budget = 150000L; (void)reserve;/' \
        mac/macextract_mac.c
    interactive.py --emu mv-4M -o /tmp/alert fixtures/derived-AuthoRize_2.0.sit
    git checkout mac/macextract_mac.c    # temporary, on purpose — wrap it in a trap

The alert is in `2-extracting.png`: the default phase clicks Cancel at a fixed
time, and a run that fails before then leaves its result alert in that frame.
Photographed 2026-08-24: *Needs 72K more memory. Give MacExtract more in Get
Info.*

### Photographing the refusal alert

Hand the application a file it cannot open:

    interactive.py --emu mv-4M -o /tmp/rarshot /tmp/Sample.rar

The alert is *"This file could not be extracted."* and comes before the
destination dialog, so it is in `1b-destination.png` (DECISIONS.md
2026-10-18, *the question after the look*); any file the engine does not
recognise does it, a RAR among them (DECISIONS.md 2026-10-18, *the formats it
only named*). **`interactive.py` exits 1 on this run and that is not a
failure**: there is no output for the CLI and the Mac to agree about. The
screenshot is the result.

The same build trick photographs the OTHER two failure alerts:

    # the disk is full — the real gLastWriteErr path, without a full disk
    sed -i 's#(Ptr)((const char \*)buf + off));#&\n        { static int nw = 0; if (++nw > 2) werr = dskFulErr; }#' \
        mac/macextract_mac.c
    # memory too fragmented — that branch fires on any run
    sed -i 's/        gShortPiece = 0;/&\n        gShortPiece = 1;/' mac/macextract_mac.c

`run.py --out-kb` measures that a full volume returns `dskFulErr` and stops
the run; these show the sentence the user gets. Photographed 2026-08-24, both
two lines.

**The alert box breaks between 32 and 36 characters** (measured off those
frames), so a message over about 60 characters draws a third line level with
the OK button. Check a new string by eye on a frame, not by counting.

**When a frame is ambiguous, make the alert say which branch drew it**:
temporarily `PStrCatNum` `ret`, `gShortBy`, `gShortPiece`, `entries` and
`errors` into the generic `ret != UNC_OK` branch (`entries = 0` once said the
archive had never been opened).

### The end-of-run report — `interactive.py --report`

    tools/vmac/interactive.py --report --emu mv-4M -o shots fixtures/anything.sit

Ignores the fixture: the archive is generated (`report_archive`) with names
too long for HFS, one that fits only once its extension goes, a duplicate, two
folders that shorten to the same name, eighteen photographs alike for 31
characters, and one entry with a one-bit checksum break — so the box lists a
rename, a numbered file, a numbered FOLDER and a per-entry failure at once,
long enough that the scroll bar is live.

Five frames: the box, the box scrolled six lines, Standard File after **Save
as Text**, the box redrawn once that is dismissed (the default ring and list
come back), and SFGetFile afterwards. **It asserts on the saved DOCUMENT**,
read back with `hcopy -t` line by line, and on the names the report CLAIMS
against the names on the volume. `--emu mv-4M`: nothing here is timed.

The box's three click targets are constants measured off `DLOG 133` in
`mac/macextract.r` (`REPORT_OK`, `REPORT_SAVE`, `REPORT_DOWN`). **Re-measure
them if that resource moves.**

#### The one line a generated archive cannot make — `interactive.py --report-utf8`

    tools/vmac/interactive.py --report-utf8 --emu mv-4M -o shots fixtures/anything.sit

*"`<name>` was named in characters this Macintosh cannot write"* needs a name
the ENGINE says is UTF-8 (only `fmt_sit5.c` does), so this phase uses
`derived-800saywhat301j.sit`, whose three Japanese names MacRoman cannot
spell. Four frames (box, Save as Text, box redrawn, SFGetFile) and
`--report`'s assertion. `ユーザーライセンスの購入` is thirteen `_`, not
twelve (`ザ` is stored decomposed); the outcome line is the CLEAN
*"Extraction complete."*.

**Why the report goes to a floppy, and the control that says so**

    tools/vmac/interactive.py --report-utf8 --utf8-to-boot --emu mv-4M \
        -o shots fixtures/derived-800saywhat301j.sit

Onto the BOOT volume, the saved report's TEXT is in the image's blocks and its
catalog record is not (`--utf8-to-boot` reads both; exit 1 is the control;
DECISIONS.md 2026-09-22, *the file that was on the disk and not in the
catalog*). **Do not search for the report's NAME**: `Extraction Report` is in
the application's resources on the same volume.

**And one level below that — `--utf8-second`, the discriminator**

    tools/vmac/interactive.py --report-utf8 --utf8-to-boot --utf8-second \
        --emu mv-4M -o shots fixtures/derived-800saywhat301j.sit

Saving a SECOND time puts both records in the catalog: the first was
**unflushed, not lost** (both live in one leaf). Exit 0 (DECISIONS.md
2026-09-22, *the entry a second write placed*).

### Driving the real UI

    interactive.py                  # progress dialog, Cancel, Cmd-., at 1x
    interactive.py --system Sys7.img  # the same, on the System 7 tier
    interactive.py --e2e            # Finder desktop: double-click launch, SFGetFile,
                                    # volume navigation, an extracted APPL launching
    interactive.py --report         # the end-of-run report box: renames,
                                    # failures, scrolling, Save as Text
    interactive.py --report-utf8    # the '_' line only a StuffIt 5 name reaches
    interactive.py --report-utf8 --utf8-to-boot
                                    # ...onto the BOOT volume: the control that
                                    # says the bytes land and the catalog entry
                                    # does not. Exits 1 by design
    interactive.py --report-utf8 --utf8-to-boot --utf8-second
                                    # ...and save it TWICE: both entries land,
                                    # so the first was unflushed, not lost
    interactive.py --segments       # the "locate part N" alert for a split archive
    interactive.py --named zip      # a spanned zip set, opened through Standard File
                                    # — needs a fixture OVER 64 KB, below
    interactive.py --named split    # a plain .NNN split, likewise
    interactive.py --chain          # .sit.hqx: do ALL the envelope layers come off?
    interactive.py --wrapped        # a set whose parts are each in an envelope
    interactive.py --wd             # output lands in the archive's folder, not at /
    interactive.py --dest           # output lands on the volume the user CHOSE
    interactive.py --diskswap       # insert the missing part's disk mid-run
                                    # — needs a fixture that is NOT an archive
    interactive.py --diskeject      # part 1 on its own floppy: is that floppy
                                    # ejected before the alert asks?
    interactive.py --drop           # drag an archive onto the application's
                                    # icon: what does the FINDER do?
    interactive.py --switch --system Sys7.img
                                    # leave an extraction for the Finder and
                                    # come back: a Finder click, then the
                                    # Application menu

Run them one at a time (*This box has two cores*, above) — and every phase
builds into the same `build/mac-interactive`, so two runs started together
fight over it and one dies in `cmake --build`.

### A one-drive Mac — `onedrive.py`

    onedrive.py [--app MacExtract.bin]     # 0 = nothing asked for after Save

`mv-4M-1d` (setup.sh) has two drives, the boot disk and one floppy, so the
System asks for disks by name and ejects the one in the drive, as a one-drive
Mac does. The walk launches MacExtract from floppy ME, ejects it in the Open
dialog, opens an archive on floppy C and saves to the boot disk, then answers
every *"Please insert the disk"* and fails if there was any. The build before
`preload` (2026-10-14) asks ME, C, ME, C and fails; after, nothing.
`onedrive.py --drop` is the drop's list of documents, given by Cmd-O on two
archives carrying MacExtract's creator; it prints every disk asked for and is
a measurement, not a check (DECISIONS.md 2026-10-14, *the swaps that are the
System's*). **What neither can see** is in the docstring: an actual drop on an
alias. Coordinates are System 7's.

**`--diskswap` needs a fixture that is not an archive**: it reads back the
joined FILE, and the application unpacks a joined archive. A few KB of random
bytes passes (DECISIONS.md 2026-10-13, *the disk that was still in the
drive*).

**`--diskeject` asserts the eject from outside the machine**: Mini vMac
`fclose`s an image when the Mac ejects it, so the phase reads the emulator's
`/proc/<pid>/fd`. Passed on `System6.hfv`, `Sys7.img` and `Sys30.img`
(2026-10-13, `derived-ScrollbarPattern.sit`); the build before fails it. On
System 7 it also checks the Finder afterwards (`DESK7_THIRD_DISK`): an ejected
but still mounted Floppy A stays as a dimmed icon, 636 px off the desktop
pattern without the unmount and 0 with it; on System 3.0 and 6 that frame
shows no dimmed icon on either build, so the check is not made. **What it
cannot see:** a real one-drive Mac — Mini vMac puts every inserted disk in a
new drive (MANUAL_TESTS.md §4).

**`--named zip` needs a fixture larger than 64 KB.** `zip -s 64k` marks an
archive split whatever its size, so a smaller payload makes one `Aset.zip` and
no `Aset.z01`, and the application correctly answers *"This archive has more
parts. Find them and try again."* — an invocation error that photographs like
a bug. Drive it with `fixtures/derived-xmasbeeps.sit`.

**On System 7 the Standard File dialog is not the same dialog.** Its first row
sits ten points higher, so `calibrate()` picks the row off `SF_ROWS` per
system and refuses a system with no entry. System 7's Process Manager also
opens the dialog inside the System Folder under the boot-shell arrangement;
`sf_to_volume_root()` presses Desktop and opens the volume (two clicks, no
menu tracking), and does nothing on System 6.

`--e2e` leaves the **Finder** as shell, the only way to launch the
application as a person does and to launch what it extracted; it uses
`derived-ScrollbarPattern.sit`, whose entry is an application drawing its own
splash screen. `docs/screens/` comes from here, except `0-icon.png`, from
`mountcheck.py --open` on `dist/MacExtract.dsk`: in the `--e2e` window the
undeletable `StuffIt Expander™ 4.0.1 Folder`'s label is painted over
`MacExtract`'s. The cancel run uses `derived-EmpireBuilderDemo.sit`: after a
cancel SFGetFile must list exactly `Demo Manual V1.6`, no `EB Sounds`.

`--segments` cuts the fixture into three, leaves part 1 alone on the boot
volume and the other two on a second floppy, so the folder scan fails and the
alert appears; it then offers the WRONG part on purpose, to see it refused by
fingerprint, and **ends on a byte comparison** of the joined file.
**Standard File opens on the last-inserted volume** — click Drive and
photograph before clicking a row — and **`Mac()` boots a private copy**: read
results from `<workdir>/boot.hfv`.

`--dest` puts the archive on the boot volume and an empty floppy beside it,
switches the DESTINATION dialog to the floppy with its own Drive button
(`SFPUT_DRIVE`; `SF_DRIVE` misses, SFPutFile's buttons sit lower), and reads
**both** volumes: every output name on the chosen one, none on the archive's.
Use `derived-Downer.sit`; it waits out `EXTRACT_QUIET`.

### What the Finder does with a dropped archive — `interactive.py --drop`

    interactive.py <fixture> --drop --system Sys30.img --emu mv-4M
    interactive.py <fixture> --drop --system System6.hfv --emu mv-4M
    interactive.py <fixture> --drop --system Sys7.img --emu mv-4M

Seven frames: the desktop, the open volume, **Get Info on the application**, a
CONTROL drag to empty space, the archive dropped on the application's icon,
the same after a launch's worth of seconds, and the extraction that follows
when the drop worked. The answer is DECISIONS.md 2026-08-31, *the drop the
Finder does not make*.

- **The control frame makes the negatives mean anything**: `drop-4` is the
  archive dragged to empty space; if it did not move, stop reading the run.
- **The phase sets the archive's TYPE with `hattrib`**, because `mkboot.py
  --data` leaves hfsutils' default and a Finder gating on the `FREF` list
  cannot match it. `--drop-type '????'` is a type nobody declared, against a
  `FREF` that claims everything.
- **Get Info is taken before the drags**, because a successful drop parks the
  archive on top of the icon the Get Info click aims at.

Icon coordinates live in `FINDER_ICONS`, per system, `archive` alongside
`app`; System 7 opens its volume window near the BOTTOM of the screen, so the
control drag moves up there.

**What it cannot see.** It photographs; it reads nothing off the volume. A
launch proves the Finder accepted the drop; `drop-7` says the application was
told WHICH file (it reads `AppParmHandle`).

### Leaving an extraction — `interactive.py --switch`

    interactive.py fixtures/derived-EmpireBuilderDemo.sit --switch --system Sys7.img

Launches from the Finder in one boot: the first opens About mid-extraction,
clicks the Finder's disk icon and comes back through the Application menu;
the second hides MacExtract from that menu and lets the extraction finish
behind the Finder; the third chooses File > Quit, which must cancel and quit.
Fifteen frames, ending on the first launch's names on the volume (DECISIONS.md
2026-10-12, *the application nobody could leave*).

- **Hold, do not click.** A press is seen only at the next progress callback,
  so `hold_and_shoot()` keeps the button down and photographs the open menu
  without `Mac.shot`, which would park the pointer and release nothing.
- **Down, then across.** A diagonal path opens every menu whose title it
  crosses; `pick()` moves straight down, then sideways.
- **What it cannot see:** how much of the processor the Finder got, and the
  second launch's output, whose names collide with the first's. The menu
  coordinates are System 7.0.1's (`APPLE_MENU`, `APP_MENU`).

### Who a double-click goes to — `deskclaim.py`

    deskclaim.py fixtures/derived-ScrollbarPattern.sit -o /tmp/c --expect refused
    deskclaim.py ... --claim --expect open                  # Desktop APPL entry
    deskclaim.py ... --app-creator 'SIT!' --expect handed   # retag the app
    deskclaim.py ... --system Sys30.img --app-creator 'SIT!' --expect handed
    deskclaim.py ... --app-creator 'SIT!' --floppy --expect handed
    deskclaim.py ... --app-creator 'SIT!' --app-folder "MacExtract Helpers" \
                     --archive-at 237,105 --claim --expect handed
    deskclaim.py ... (the same) --no-desktop --stub-bundle --expect handed
    deskclaim.py ... --stub "SIT! Helper.bin" --open 365,107 --expect handed
    deskclaim.py ... --system Sys7.img --stub ... --extra "Deluxe.bin:StuffIt Deluxe Folder:StuffIt Deluxe™" \
                     --open "StuffIt Deluxe Folder" --open "MacExtract Helpers" \
                     --archive-at archive.sit --expect handed

Double-clicks a `SIT!` archive in the Finder, after optionally: adding a
`SIT!` → MacExtract entry to the volume's `Desktop` file (`--claim`, plus a
bundle with `--bundle`); retagging the application's creator; moving it into a
folder the run never opens; giving it a bundle under its new creator
(`--stub-bundle`; `--doc-icon TYPE` adds a document icon); deleting the
`Desktop` file so the Finder rebuilds it (`--no-desktop`; on System 7 `Desktop
DB` and `Desktop DF`); or putting the archive on a second floppy. `--stub FILE`
boots a REAL stub (`companion/make_stub.py`) in `MacExtract Helpers` beside an
untouched MacExtract; `--multifinder` puts System 6's MultiFinder back.
`--extra FILE:PATH` puts another application on the volume, and `--open`
opens folders before the archive, in order, because the Finder registers what
it sees: by position, or on System 7 by NAME, type-selected (`--archive-at`
takes a name too).

**It grades the DIALOG in `claim-3-launched.png`, not the volume**: a launch
that was not handed the file shows the Open dialog, the run's Return opens the
archive from it, and the entries land anyway. The Finder's refusal alert is
identified positively (System 6's and 7's); MacExtract's dialogs by all three
rows of their frame (one row matched StuffIt Deluxe's archive window). A frame
with none of these is `nothing` — look at it. **`--app-folder` moves the
archive's icon**: read its position off `claim-2-volume.png` and pass
`--archive-at`. The expected names are `--want`, so a run needs no `build/rel`
CLI and can share the machine with `./ci.sh`. Results: DECISIONS.md
2026-10-10, *the double-click that goes by the application's creator*;
2026-10-11, *where the stubs can live* and *the stub that hands it on*;
2026-10-12, *the stub beside StuffIt*. **What it cannot see:** System 7's
`Desktop DB`, which it neither reads nor writes (which application registered
is read off the icons); and whether StuffIt OPENED an archive beyond the frame
showing its window.

### Several archives opened at once — `relaunch.py`

    relaunch.py --app build/mac-interactive/MacExtract.bin --expect both --folder-at 115,107
    relaunch.py ... --system Sys30.img --emu mv-512Ke --folder-at 174,95
    relaunch.py ... --system Sys7.img --folder-at In          # type-selected
    relaunch.py ... --multifinder
    relaunch.py ... --keep-inits --folder-at 115,107      # the stock System Folder
    relaunch.py ... --system Sys30.img --emu mv-512Ke --in-disk 1440 --disk-at 472,107 \
                    --first derived-Cool_Tools__.sit --second derived-a2basic.dmg.sit

Opens a `.cpt` and a `.sit` TOGETHER from the Finder (Select All, Open) and
grades both: the destination dialog for each, and every entry of both on the
volume. `--expect first` is the control, for a build before the reload.
`--in-disk` puts the pair on a second disk with room for its output (System
3.0's boot disk has none for `a2basic`); a `-D UNC_AT_HEAPLOG` build's `Heap
Log` is printed at the end. Results: DECISIONS.md 2026-10-12, *the reload that
the list needs*. `--keep-inits` boots the stock System Folder (`Desktop Mgr`
and MultiFinder in), where the default pair puts an application with a bundle
at the top of a folder output — the one place v0.42.0 closed the Finder's
working directory (DECISIONS.md 2026-10-22, *the working directory the bundle
closed*); `run.py` cannot see that, since it extracts into a volume's root by
dirID. **What it cannot see:** an entry refused for memory and one refused for
a full disk look the same to the volume check — read `r-6-second-done.png`.

### Making a segmented Compact Pro archive — `cptsegment.py`

    cptsegment.py --list
    cptsegment.py --map              photograph the application's menus
    cptsegment.py --case edu3        cut a specimen, and read it back
    cptsegment.py --verify           does tools/synth_cptsplit.py still
                                     reproduce the specimens byte for byte?

Compact Pro 1.51 comes out of the corpus through our CLI, goes onto the boot
volume as MacBinary beside the archive to be cut, and the driver works `Misc >
Segment` with a chosen size. The set lands in `$UNC_VMAC_HOME/specimens/<case>/`
with a `case.json` — not committed, and kept beside the emulator rather than
under `build/`, which `./ci.sh`'s `make clean` empties. Nothing documents the
segmented layout, so the specimen IS the documentation (DECISIONS.md
2026-08-14); `--verify` holds `tools/synth_cptsplit.py` to reproducing these
sets exactly.

Driving another application here:

- **A `--data` copy is invisible to it.** Another application filters Standard
  File on TYPE, so the archive arrives as MacBinary with `PACT`/`CPCT` on it —
  `mkboot.py --macbin`.
- **Its Standard File is not ours**: this one's first row is at y=88 where
  `interactive.py`'s is at 137.
- **Menu titles have to be measured, not counted** (the first map was one menu
  to the left the whole way along).
- **The number of Save boxes is not known in advance**: the driver stops when
  the screen stops changing rather than counting.

### StuffIt Deluxe 2.0.1 writes an optimized archive — `sitopt.py`

    tools/vmac/sitopt.py --setup        fetch the two 2.0.1 floppies
    tools/vmac/sitopt.py --install      build the System 6 boot volume
    tools/vmac/sitopt.py --personalize  register it, and KEEP that image
    tools/vmac/sitopt.py --make --force --no-expert   run the script
    tools/vmac/sitopt.py --unstuff      have 2.0.1 unstuff its own archive
    tools/vmac/sitopt.py --show <path>  any archive's entry headers
    tools/vmac/sitopt.py --magic        the Finder with Magic Menu loaded
    tools/vmac/sitopt.py --stuff        Magic Menu's ⌘S, read back
    tools/vmac/sitopt.py --options      the `StuffIt Options ▸` submenu
    tools/vmac/sitopt.py --add-paint    MacPaint 2.0 onto the same image
    tools/vmac/sitopt.py --paint        draw something and save it as PNTG
    tools/vmac/sitopt.py --makepaint    stuff it with `MacPaint 1` on/off
    tools/vmac/sitopt.py --add-modules  the three Optimizers --install missed
    tools/vmac/sitopt.py --makemods     Sound 1, Photoshop 1, JPEG Lossy
    tools/vmac/sitopt.py --dcmpdata     run MacPaint 1's COMP and DCMP
    tools/vmac/sitopt.py --segment small|big   cut two files with resource forks

**It installs by COPYING, not by running the installer.** Disk 1's installer
has a DATA fork that is itself a StuffIt archive; `macextract` unwraps it, so
the application, `Text 1`, `PassLock`, the Engine, Magic Menu and Aladdin's
Preferences file go onto a copy of `System6.hfv` from Linux. Where each
belongs comes from disk 2's `UnInstall Dlx Files Script`, which erases
`{system}Optimizers:Text 1` and the rest by name. Without the Preferences
file the application stops at a Standard File dialog before drawing a window.

**Registration.** 2.0.1 wants a name, a **signature drawn in a box** (no OK
without one) and a serial. The code is on the download's own page,
`macintoshgarden.org/apps/stuffit-deluxe-2`: *"A nnnnn (where 'n' = any
number)"* — **not** `/apps/stuffit-deluxe`, whose 3.0.7 and 5.x codes
`spacesaver.py` carries (BLOCKERS.md, withdrawn claims). `--personalize`
keeps the registered image, because the application writes the
personalization into its own resource fork — **do not re-run `--install`
afterwards**; it rebuilds from `System6.hfv`.

**The run is a SCRIPT, not clicks.** StuffIt Deluxe 2.0's scripting language
(vocabulary in the application's STR# 257, shapes in the payload's `Sample
Scripts`) runs from `Scripts ▸ Execute Script…` — **⌘E**; at y=20 the item
never highlights. `Write Status To` makes the application report what it did:

    Creating new archive: Macintosh:Optimized.sit
    Stuffing items matching: Macintosh:Subject
            (stuffing file: Subject)

so the control and the optimized pair come from one boot, and a syntax error
says so.

**Read the image the emulator WROTE** (a copy in the session's temp
directory); the image you handed it shows every archive missing.

**`--unstuff` is the oracle.** It boots the image `--make` wrote, deletes the
original subject, and has Magic Menu unstuff `Optimized.sit`. For `Text 1`
that gives the OPTIMIZED bytes — 594, no resource fork — which
`tools/run_sitopt.py` grades against.

**`MacPaint 1` keys on type `PNTG`**, and the corpus has no paint document,
so `--add-paint` puts **MacPaint 2.0** (a `.sea.hqx` our engine unwraps) on
the image, `--paint` drags three strokes and saves `Painting`, and
`--makepaint` stuffs it with the Optimizer off and on. **Click the icon to
launch it**: type-select and ⌘O renamed the application `Painting`.

**The last three modules' acceptance tests, read out of each `COMP`**: `Sound
1` wants type **`FSSD`** (Sound Designer II) and an `INFO` 1000 resource;
`Photoshop 1` wants **`8BIM`** (Photoshop 1.0's type, not `8BPS`) and an
`8BIM` 1000 resource of ten bytes or more whose word at +8 is a colour mode.
`--makemods` builds subjects to those tests (the Photoshop one with a genuine
PSD data fork) and all three bite, writing 1, 2 and 3 into byte 106.

- **Read the script's status file**: *"Optimizer Not Found: Sound 1"* is how
  a missed install shows.
- **Module names go through the reversible `/`→`:` swap**: the Macintosh file
  is `Photoshop/JPEG Lossy`.
- **Check a built resource fork parses** (`spacesaver.resources()` on what
  `one_resource()` writes): a map missing its attributes word made
  `Get1Resource` return NULL.

**`--unstuffapp` takes `--archive`, `--item` and `--add-archive`**, so the
application can be asked about any archive:

    tools/vmac/sitopt.py --unstuffapp --tag unjpeg1 \
      --image $VMAC/sitopt/sitopt-painted.hfv \
      --add-archive /tmp/OptJpeg.sit.bin --archive OptJpeg.sit --item Photo

That image has all five Optimizers installed. **2.0.1 refuses its own
`OptJpeg.sit`** — *"This file cannot be decoded by this version of the
Photoshop JPEG optimizer"* — in a MODAL alert, so no `UnStatus.out` comes back
and the screenshot is the finding; `OptPhoto.sit` in the same boot unstuffs
cleanly, the control. The entry is STORED, so its 80 bytes are the module's
output (FORMATS.md, *What an Optimizer did to the fork*).

**Magic Menu refuses the MacPaint archive** — *"Items that were encrypted or
compressed with an optimizer or compressor will be skipped. The Engine does
not currently support this. Please use StuffIt Deluxe instead."* — and
unstuffs the `Text 1` one; `run_sitopt.py` asserts that line as a fact about
Aladdin's Engine. This engine refuses neither.

**A hierarchical submenu DOES open here.** `--options` pulls `Magic ▸ StuffIt
Options ▸` down ten pixels at a time: the parent highlights and the submenu
draws, to the LEFT (the parent is near the right edge). That is System 6 and
Magic Menu 2.0; System 7's Translate menu failure stands (*What the pointer
cannot select*). Nothing in it was worth selecting.

What it CANNOT see:

- **whether a real Sound Designer II or Photoshop document behaves the
  same.** Two subjects are built to the modules' own acceptance tests.
- **whether the other four modules' `DCMP`s behave as `MacPaint 1`'s
  does.** That one is driven end to end by `--dcmpdata`, below; the
  rest have never been run.
- **whether 3.5.1 would use a 2.0 module.** `--install351` puts `Text 1` in
  both places 3.5 might look, and that application does not launch here.
- **the 512 KB machine.** It boots `mv-4M` throughout.

**`--segment` cuts StuffIt segments with 2.0.1's own `Segment` script
command**, two subjects with resource forks per launch, read back into
`specimens/sitopt/seg-small` or `seg-big`. `small` is one part each; `big` is
two each, at the default 793,500 payload bytes a part, and SubjC's part 1 ends
inside its resource fork. The sets in `specimens/sitseg-real/rsrc{a,b,c,d}`
came from these runs. A set's bytes 0-1 are the launch's next `_Random` (the
first file always 41 A7, the second 3A F1); a re-run repeats each part except
the name buffer past the name and the header CRC over it (DECISIONS.md
2026-10-24, *the two bytes the writer drew*). What it cannot see: any writer
but 2.0.1, and a size other than the default.

### Photoshop 1.0.7, and the document its Optimizer can read

    tools/vmac/sitopt.py --add-photoshop   fetch it and put it on the image
    tools/vmac/sitopt.py --psdoc --tag psdoc     draw and save a native 8BIM file
    tools/vmac/sitopt.py --psjpeg --tag psjpeg1  stuff it with JPEG Lossy, unstuff it

    # and the SECOND subject, two boots, 2026-10-02
    tools/vmac/sitopt.py --psdoc --drawing grid --psname PSDoc2 --tag psdoc2
    tools/vmac/sitopt.py --psjpeg --psname PSDoc2 --against psdoc2 --tag ps-jpeg2

    # what the application will actually ask for, 2026-10-02
    tools/vmac/sitopt.py --psmatrix --psname PSDoc2 --against psdoc2 --tag psmatrix1
    tools/vmac/sitopt.py --psmenus --tag psmenus1        the REGISTERED menus
    tools/vmac/sitopt.py --psopts  --tag psopts2         the two Options dialogs
    tools/vmac/sitopt.py --psjpeg --quality 50 --psname PSDoc2 \
                         --against psdoc2 --tag ps-jpeg3
    tools/vmac/sitopt.py --psenc --psname PSDoc2 --against psdoc2 --tag psenc1

**It runs on the Mac Plus** (Adobe says *"Macintosh SE or newer"*): Photoshop
1.0.7 launches in about 90 seconds, from a StuffIt archive of one DiskCopy
image this engine unwraps. Two coordinates are in `sitopt.py`: the
application's icon, and the **PENCIL** (right column, row seven; the default
marquee saves a blank page). The New dialog defaults to 512x512 RGB;
`--psdoc` types 256, Tab, 256. The file is **196,608 bytes — 256x256x3 — of
raw pixels with no header**, plus an `8BIM` 1000 resource of ten bytes
(channels, height, width, depth, mode) that the Optimizer's acceptance test
reads (FORMATS.md). `--psjpeg` is the round trip in one boot: control,
optimized archive, UnStuff.

**`--drawing grid` is the second subject, chosen for the arithmetic** (a
6-pixel comb crossed with a 12-pixel one plus two diagonals; `zigzag` is the
default): it settled that `CCOD`+0x3826 does not round toward zero
(FORMATS.md, *What an Optimizer did to the fork*; BLOCKERS.md, *Withdrawn
claims*). `--drawing` and `--psname` make a third subject two boots and no
editing.

**`--quality N` sets the module's own Q.** `--psmenus` photographs the
REGISTERED menus (`--map`'s image stops at personalization); `--psopts` opens
the two Options dialogs. Clicking a module's row in the Optimizers list opens
**the module's own dialog** (*"Please specify the JPEG quantization level to
use..."*, a Q field, *"Prompt for Q on each file"*); Q=25 is a default
(FORMATS.md, *What an Optimizer did to the fork*).

- **Neither ⌘. nor Escape cancels a 1990 modal dialog.** Click the button.
- **A module's dialog swallows everything typed after it.** Screenshot after
  every click.
- **The Q field comes up SELECTED**; `--quality` types without clicking.

**A script cannot reach `PassLock`**: `--psenc` arms it from Options ▸ Custom
Encryption… and the scripted `Stuff` still writes an unencrypted shape with no
prompt. `--psencgui` drives File ▸ New Archive… and Archive ▸ Stuff….

- **Type-select is a SYSTEM 7 feature**, so on these System 6 volumes **click
  the icon**: `--psicons` grows the window by DRAGGING its grow box (the zoom
  box does nothing here) and photographs every icon. On System 7, Escape
  clears the type-ahead buffer before each name.
- ***"No Self-UnStuffer can be found that supports this archive"* means the
  stubs are missing**: three `AUSt` files in the MAIN installer's payload
  (`Self-UnStuffers/Everything UnStuffer`, `Fast UnStuffer`, `Optimal:Better
  UnStuffer`), each supporting a set of METHODS. In a `Self-UnStuffers` folder
  in the System Folder, `Save As … Self-UnStuffing` writes a `.sea`.
  `UnStuffIt Deluxe™` is the standalone application, not a stub.

**The script's security words name built-in ciphers** (BLOCKERS.md):

    tools/vmac/sitopt.py --psdes --tag psdes1

`Stuff … with fast des` and `… with fast newde` each prompt for a password and
write a real encrypted archive, with a plain control from the same boot.
`NewDE™` and `DES` are built in; `Custom Encryption…` is the plug-in route.
The optional disk's `NewDEx` (id 3) and `DESex` (id 64) are held here as
`.rsrc` files never installed.

What `--psmatrix` CANNOT see: `Custom Compression…`, the one method in the
Options menu with no script word.

### Every combination 2.0.1 will write — `sitcombo.py`

    tools/vmac/sitcombo.py --psnew PSOdd 203x77            draw and save
    tools/vmac/sitcombo.py --psnew PSGray 256x256 --gray
    tools/vmac/sitcombo.py --psnew PSCmyk 128x128 --mode cmyk
    tools/vmac/sitcombo.py --psnew PSWide 512x128 --zoom 2
    tools/vmac/sitcombo.py --psnew PSSmall 21x13 --canvas 115,66 --margin 3
    tools/vmac/sitcombo.py --cdocs                         no boot
    tools/vmac/sitcombo.py --run b --limit 5400            one boot a set
    tools/vmac/sitcombo.py --run q --quality 1,2,3,5,10 --tag setqlow

Each `--run` copies `sitopt-ps.hfv`, puts its subjects and a script on it, and
has 2.0.1 stuff and then unstuff in one boot; the sets are in the docstring,
the grading is `tools/run_sitcombo.py` (TESTING.md). 22 boots made the 121
archives on 2026-10-11.

**It is closed-loop where `sitopt.py` types blind.** The password prompts are
recognised by one thresholded strip of the screen (`specimens/sitopt/psdes1`'s
two dialogs differ there and nowhere a typed password reaches), answered when
up, and the run ends when the Finder's menu bar is back (every script ends in
`Quit`). A screen still for a minute gets one Return and a photograph. It
asked once per ARCHIVE, never per `Stuff`.

The emulated screen, each of which cost a document:

- **The pointer lands 3 px left and 6 px up of where it is sent** (`PTR_FIX`).
- **A stroke that starts on the title bar drags the window**, and one leaving
  Photoshop's window switches MultiFinder to the Finder. Keep a margin.
- **A document wider than the screen opens at 1:2** (`--zoom 2`), and **one
  smaller than the window is centred on grey** (`--canvas`, read off the
  new-document shot).
- **The JPEG module's dialog refuses Q = 1, 2 and 3 silently**: OK does
  nothing and the next keystrokes go into the Q field. `--run q` tries a list
  and photographs which it took (5, and 255 at the top).
- **`macextract t` on a `.sit.bin` tests the MacBinary**, not the archive
  inside — `l` and `t` never unwrap. Grade with `x`.

What it CANNOT see: a coloured document Photoshop drew (`--cdocs` builds them
in its layout instead), a real Sound Designer II file, and the Stuff dialog's
own method popup.

### Running an Optimizer module — `dcmptest`, `--dcmp` and `--dcmpdata`

    cmake -B build/dcmptest -S tools/vmac/dcmptest \
          -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
    cmake --build build/dcmptest
    tools/vmac/sitopt.py --dcmp        the calling convention, on sitopt.hfv
    tools/vmac/sitopt.py --dcmpdata    the whole data path, on sitopt-paintmade.hfv

**`--dcmp` proves the calling convention and nothing else.** The probe opens
`{system}Optimizers:MacPaint 1`, takes its `'DCMP'` with `Get1IndResource`
(its id is the module's number, not 1) and jumps to `*handle`, a `bra.s` over
the sixteen-byte header. Selector **-3** makes every module copy its own name
into the caller's buffer with `_BlockMove` and write 1 back. It comes back
**"MacPaint 1"** and a 1.

**`--dcmpdata` is the round trip, and needs `Painting` on the volume**, so it
boots `sitopt-paintmade.hfv`. The `COMP` is handed a `CInfoPBRec` at -1, run
at -4, and its output read back through `*selector > 0`; that remnant goes
into the `DCMP` at -1, in 512-byte chunks, and -2. The grader checks the
rebuilt document against the original and against 2.0.1's own unstuffer output
(`specimens/sitopt/unapp3`), and the remnant against a length in front of the
document from offset 512 on. **0 problems** on 2026-09-29 (FORMATS.md, *What
the data path does*).

**It is launched AS THE FINDER**, as `traptest` is: `--dcmp` and `--dcmpdata`
replace `Finder` on a COPY and rename the real one aside, so no navigation is
needed on a volume where a type-select already renamed an application.

- **Paint the screen white first**; `DrawString` over the grey desktop is
  unreadable at 512x342.
- **One `FSRead` is not a read.** A short count is legal (2,048 of 2,437 at a
  file's first extent), and the untouched tail came out as **the right length
  with the wrong content**. Loop, as the module's own transform does.
- **`_FlushVol` returning 0 is not Shut Down**: the probe calls `ShutDwnPower`,
  and the shots are taken BEFORE it **by the clock, not by `Session.boot()`**,
  whose settle wants three identical frames — the probe never calls
  `InitCursor`, so the watch spins.
- **A `COMP` will not let go of its temp file** (`Paint Temp 0` gives -49,
  `opWrErr`; -2 deletes it). `*selector > 0` hands the bytes over.
- **`PBGetCatInfo` returns the file number in `ioDirID`**: put the three input
  fields back before handing the record to a module.

What these CANNOT see:

- **the other four modules' data paths.** `Sound 1`, `Photoshop 1` and `JPEG
  Lossy` have a `DCMP` each and none has been run; `Text 1` has none by
  design.
- **whether a real MacPaint would open the rebuilt file.** It is
  byte-identical to StuffIt Deluxe's own output from offset 512 on and its
  first 512 bytes are a stack frame.
- **the ENGINE side**, which is not driven through a module here
  (DECISIONS.md 2026-09-29, *the smallest module was the biggest gain*).

### Making an encrypted StuffIt archive — `sitcrypt.py`

    tools/vmac/sitcrypt.py --map                     photograph the menus
    tools/vmac/sitcrypt.py --password swordfish --tag pw9

StuffIt Deluxe 3.5.1 (installed by `spacesaver.py --install351`) writes
password-protected StuffIt classic archives: File ▸ New, Archive ▸ Stuff… with
**Encrypt with password** ticked, then the password twice. **Those menus are
MAGIC MENU's, in the Finder**: ⌘O does not launch the application on this
image, and a double-click does (`sitenc351.py`, below; BLOCKERS.md, withdrawn
claims, 2026-10-10). The archive comes off as MacBinary because the verifier,
`'MKey'` 0, is in its RESOURCE fork.

It settled the archive key's fold count: 8, 9 and 17 characters need 1, 2 and
3 folds, so the rule is ceil(len/8), and **neither reference has it**
(FORMATS.md). `tools/run_crypt.py` replays whatever specimens are present.

- **Shut Down can stall.** With the subject on a second volume, Shut Down
  ejected it and the Finder asked for it back, so the boot volume never
  flushed and the archive came off forty bytes short. One volume.
- **Rows are sixteen pixels apart, not fifteen.** At fifteen, row 5's click
  landed on row 4 and encrypted the 727 KB application, perfectly.
- **The invisible files count.** `Desktop DB` and `Desktop DF` are listed by
  StuffIt's own dialog and sort first, so row 0 is not your file.
- **The application renames what you type**: "Secret.sit" becomes
  `Secret.sit.sit`.

**The Translate menu's submenu items cannot be selected here** — the
harness's limit, not the application's. `--btoa-peek` photographs the menu and
its `btoa/atob ▸` submenu opening; three ways in (a diagonal jump, a sideways
entry along the submenu's row, stepped motion ten pixels at a time; tags
`btoa`, `btoa2`, `btoa3`) all leave the parent highlighted and select nothing.
*Hypothesis*, unreduced: the Menu Manager wants mouse movement the emulator's
pointer injection does not produce. That route is gone from the script: with
no picker on screen its clicks RENAMED the subject `Subject.ascii`, a
plausible-looking specimen holding the plain subject. `--btoa-drop` drove
`DropConvert™`, which converts ARCHIVES between StuffIt and self-extracting,
and never wrote a file. **`--btoa-send` is the route.**

### The translator, driven by Apple event — `--btoa-send`

    tools/vmac/sitcrypt.py --btoa-send

**No menu at all.** StuffIt Deluxe 3.5.1's `aete` declares a `translate`
event — `SIT!`/`TRAN`, direct object an alias, `trnm` the translator's name,
`encd` the direction, `dest` where to put the result — and its `SIZE` -1 is
`0xd8e8` (isHighLevelEventAware and localAndRemoteHLEvents set). The Apple
Event Manager is in System 7.0.1 without AppleScript.

`tools/aetran/` is the sender, a Retro68 application of about 400 lines the
harness cross-compiles onto the volume beside the subject. The Finder opens it
(one type-select and ⌘O, the only thing this mode drives); it finds its folder
through `GetProcessInformation`, launches StuffIt Deluxe with
`LaunchApplication`, sends the event, and writes the reply's `errn` to
`AEResult` beside itself. The specimen lands in
`$UNC_VMAC_HOME/specimens/sitcrypt/btoasend/`, graded with our CLI and diffed
against btoa 5.2.1.

- **The `aete` says what the terms MEAN, not what the handler accepts.** Of
  six shapes sent in one boot, only `dest` as an `fss ` naming the
  not-yet-existing OUTPUT FILE failed (`errn -1700`, `errAECoercionFail`);
  every shape naming an existing FOLDER, or no destination, was accepted.
- **`encd` is the direction, and its default is DECODE** (shapes omitting it
  left a zero-byte `Subject.dec`).
- **The translator wraps before it encodes**: `Subject` comes back as
  `Subject.MBin.ascii`, MacBinary then btoa. The output is found by type and
  creator (`TEXT`/`asci`), and the grading takes the two layers off
  separately.
- **It writes the OLDER framing**, `xbtoa Begin` … `xbtoa End`, not `xbtoa5`
  (FORMATS.md, *btoa*).

### The 3.5.1 APPLICATION, and its ciphers — `sitenc351.py`

    tools/vmac/sitenc351.py --install [--plain]   2.0's Encryptors added
    tools/vmac/sitenc351.py --probe --tag probe1  menus and Preferences
    tools/vmac/sitenc351.py --script --tag script2
    tools/vmac/sitenc351.py --script --variants --answers 4 --tag variants1

The image is `ssinstalled.hfv` plus `PassLock`, `NewDEx` and `DESex` in
`{system}Encryptors:` and `Extensions:Aladdin:Encryptors:`, a subject and two
scripts. `--script` launches the application, ticks *Script* in Preferences'
*Menus* box (off by default, so ⌘E does nothing until it is), runs the script
with ⌘E, types the password into every dialog, quits and shuts down, then
prints each archive's header and the status file and writes `made.json` for
`tools/run_crypt.py`. Results: FORMATS.md, *Where an archive names the
module*.

- **⌘O does not launch it; a double-click does** (`sitopt.launch351`;
  BLOCKERS.md).
- **The Script checkbox wants its LABEL clicked**, at (300, 273); a click on
  the box at (282, 272) leaves it clear and the dialog's preview menu bar
  unchanged, which is the tell.
- **Quit before Shut Down.** With the application frontmost there is no
  Special menu and the image is never flushed (`script1` came back
  unmountable).

What this CANNOT see:

- **any 3.x but 3.5.1**, or a third party's Encryptor module.
- **the Optimizers dialog.** The script answers `Enable Optimizer` with *"No
  longer supported"*, measured with no Optimizer installed.
- **the Apple-event route**, which is not driven: its `stuff` takes only the
  boolean `encryption`, so it cannot name a cipher.

### Making a Private File — `privatefile.py`

    tools/vmac/privatefile.py --fetch            download, and unpack the application
    tools/vmac/privatefile.py --probe            boot and photograph the picker
    tools/vmac/privatefile.py --make t2          encrypt the subjects, lift the results

`private_file_2.0.sit` comes off Macintosh Garden's mirror; its `Aladdin
Private File Installer` is an InstallerMaker application whose DATA FORK is a
StuffIt archive this engine opens, so **no installer is driven**. `PF
Encrypt™` is 68K with its cipher in its own `CODE` 4 — no StuffIt Engine, no
extension, pre-registered — and goes onto a copy of `Sys7.img` in `System
Folder:Startup Items`, so the Finder launches it at boot. Subjects sit at the
volume's root.

The walk, per subject: *File ▸ Encrypt…* by mouse; its own picker (not
Standard File), which opens in the APPLICATION's folder, so **Desktop** and a
double-click on the volume; the subject's row; **Add**; **Encrypt**; the
password; Return; the password again in *"Please re-enter your new
password"*; Return. Then *File ▸ Quit*, *Special ▸ Shut Down*, and every file
on the root that was not put there comes off as MacBinary into
`$UNC_VMAC_HOME/specimens/privatefile/TAG/`.

- **A Command key before any click never arrives** (no window manager gives
  the emulator focus); the first action is a menu pick by mouse.
- **Passwords under six characters are not accepted**: OK stays dimmed
  (`cmpi.b #6`, CODE 4 @0x3e76) and Return does nothing.
- **Subjects are encrypted last row first**: a finished `X.pf` lands beside
  `X` and sorts after it, so row 0 first would move every row below it.

### Asking Compact Pro about its own cipher — `cptcrypt.py`

    tools/vmac/cptcrypt.py --explore     photograph each step
    tools/vmac/cptcrypt.py               write an encrypted archive with
                                         our cipher, and have Compact Pro
                                         extract it

`ddencode.py`'s arrangement, pointed at Compact Pro's encryption, both ways:
`tools/synth_cpt.py` writes an archive with the cipher `src/unc_crypt.c` read
out of Compact Pro 1.51's `CODE` 3 and the application extracts it, and
`--make` has the application encrypt known subjects for this engine to read.
Both agree since 2026-08-23.

    tools/vmac/cptcrypt.py --register "Registered:35427117" --make --probe
    tools/vmac/cptcrypt.py --register "Registered:35427117"

**Encryption is behind the registration**, and Macintosh Garden publishes one
for 1.51 (`Registered` / 35427117). Without it Compact Pro answers Extract
with *"This version of Compact Pro cannot validate or extract encrypted
files"* and the Add dialog's Encrypt checkbox sits at a negative rect; with
it, the code at 0x4864 patches DITL 312 to bring the checkbox into view.

`--make` keeps the archive in `$UNC_VMAC_HOME/specimens/cptmade/` with a
`made.json`; `tools/run_crypt.py` replays it when present and skips loudly
when not. It is the only encrypted specimen here written by the software that
invented the format (FORMATS.md, *Compact Pro's cipher*).

`--note TEXT` types a comment into **Archive > Note...** (Compact Pro's
archive comment) before the archive is saved:

    tools/vmac/cptcrypt.py --register "Registered:35427117" --make \
        --plain --note 'First line.\nSecond line.' --outdir ...

`\n` is a line break. **Return does not press OK** in that multi-line field
(measured 2026-08-23), so OK is clicked. `--plain` writes the archive
unencrypted, so nothing asks for a password.

- **Three lengths answer a preamble question**: data forks of 96, 100 and 103
  bytes come out as 104, 108 and 111 — a constant eight, a preamble and not a
  block cipher's padding (`--probe`).
- **Every resource fork extracted on that machine comes back restamped**, a
  few dozen bytes in — the Finder opening it and the Resource Manager writing
  the map's live fields. Debug a cipher on data forks.
- **The first row of Standard File is the invisible `Desktop` file**, which
  the application reports as unreadable — what a broken archive looks like.
- **Type nothing blind before the password dialog is up.** Compact Pro asks
  when it WRITES, not at Add, so an early Return walks Standard File into a
  folder.

### Driving our own password dialog — `interactive.py --password`

    tools/vmac/interactive.py --password -o shots fixtures/anything.sit

The fixture argument is ignored: the archive is `tools/synth_crypt.py`'s
encrypted StuffIt classic one, delivered as MacBinary so the **resource
fork** with `'MKey'` 0 arrives — the only phase exercising the Mac side of
reading it. The walk answers **wrongly first**, so the retry path is driven,
and ends by comparing the extracted bytes off the volume. Verified on System
6.0.8: both asks, the second saying "That password was refused", every entry
byte-exact.

`--password-kind zip` and `--password-kind cpt` (2026-10-25) put an encrypted
zip or Compact Pro archive in its place, as a data fork: the two formats whose
ciphers the shipped build keeps only when `unc_archive_encrypted` says an
entry needs them (DECISIONS.md 2026-10-25, *the envelopes that left*). The
right password is typed first (neither has a verifier to refuse a wrong one),
and resource forks are compared with the reserved header bytes masked.
Verified on System 6.0.8: both decrypt; with the check forced to NO, the zip's
entries are lost.

### A Private File through the application — `interactive.py --privatefile`

    tools/vmac/interactive.py --privatefile -o shots fixtures/anything.bin

`--password`'s walk over the `Forked` specimen `privatefile.py --make` lifted,
so the reader's crossings into other images (key setup in `ovl_crypt`, the
reader in `ovl_stuffit`) and the envelope unwrap run in the shipped
application. Wrong password first, then `hushnow`; both forks of `Forked` read
back. Verified on System 6.0.8 on 2026-10-09 at 4 MB and, with `--emu
mv-1M-1x`, at 1 MB, and on 2026-10-10 on both 512 KB machines (`--emu
mv-512Ke`, with `--system System6.hfv` and `--system Sys30.img`): refused,
asked again, both forks byte-exact. **On `Sys30.img` the phase boots to the
Finder** and double-clicks the volume and the application, as `--e2e` does;
`pf-0-volume.png` is that window. The second Standard File row is `Forked.pf`
on both systems.

**The resource fork is compared with bytes 16..127 masked**, as every on-Mac
harness does — the Macintosh stamps the file's name into that range
(DECISIONS.md 2026-10-09, *the specimen was one search away*).

### Reading a running application's memory — the Shortcut updater probe

    # the dumper must be Mini vMac's PARENT: Yama (ptrace_scope 1) lets only
    # an ancestor read /proc/<pid>/mem, and a detached reader gets EACCES.
    # Launch the emulator from the process that will dump it, read
    # /proc/<pid>/maps for the readable regions, copy them out, then:
    tools/sit_mkey_oracle.py --mkey 4d87bcb0c49abe53 --scan dump*.bin
    tools/sit_mkey_oracle.py --mkey 4d87bcb0c49abe53 --ak <hit>  # confirm

`--scan` runs `tools/sit_akscan.c` (built on demand; ~6 s per 12 MB dump), and
`--ak` unfolds a password of up to eight characters from a key that verifies.
Used on Aladdin's *Shortcut 1.5.3 Update* (kept at
`~/.cache/macextract/specimens/shortcut-updater/`, what it installed in
`installed/`): System 7.0.1 at 4 MB, the updater in `Startup Items`, and a
stand-in `Shortcut™` (`cdev`/`Cut!`, with a non-empty `cdev` resource) in
`Control Panels` — without it the updater's Standard File list, filtered on
`cdev`/`Cut!`, goes no further. With it: Install, a restart warning (Return),
*"Install software as:"* (Return), and it extracts. The key is in every dump
from the restart warning onward (DECISIONS.md 2026-10-10, *the installer's own
key*). The System 7 Standard File popup at (172, 65) opens on a mouse-down;
drag to an item and release. **What it cannot see:** a key not computed yet (a
negative says only that the dump was early); a key kept only as an expanded
DES schedule.

### Replaying the segment work — `segcheck.py`

    tools/vmac/segcheck.py --list
    tools/vmac/segcheck.py                 # all ten, 4 MB
    tools/vmac/segcheck.py --mem 1M        # the floor target
    tools/vmac/segcheck.py --case cpt-middle

The segmented-archive checks written down as commands; its first full run
caught two stale expectations and one real defect (DECISIONS.md).

**A StuffIt set is checked off the DISK**, not against the grid: it yields the
joined archive, while the manifest describes what is inside. **A Compact Pro
set is checked against the grid**, because its reader emits the entries
directly. Same shape from outside, opposite oracles.

**`ddseg-real` is the only case whose parts were cut by the application that
defines the format.** DiskDoubler Pro 4.1.1 cut `ddtf-ddpro411ad1.dd` into
two; both are fixtures, as is the AppleDouble sidecar holding the original's
resource fork, so the case checks the joined FILE off the Out volume, both
forks, as well as the grid via `--expect`. Part 2 goes on under a name that
resembles nothing: a `SPLT` part is matched by the 26 identity bytes in its
header.

**`sit-fat` is the one case that needs a part's RESOURCE fork**: Now Utilities
6.0's two installer disks, from `$UNC_VMAC_HOME/specimens/sitseg-real/fat/`,
where part 1's `'endD'` says where its segment stops (DECISIONS.md 2026-10-24,
*the length part 1 kept in its resource fork*). `run.py --rsrc` puts part 1 on
the In volume with both forks, `--in-kb 4096` makes room, and it runs twice,
passing only if the joined file is right with the fork and wrong without it.

### The two schemes that are placed by FILENAME — `--named`

A spanned zip or a `.NNN` split cannot go through `run.py`: the names ARE the
scheme, and the autotest opens `archive.sit`. So they go through Standard
File, and the phase ends on a byte comparison of the one file the set must
produce. **Both sets' stems begin with `A`**: the phase opens the FIRST ROW,
and the invisible `Desktop` file sorts between `Blob.001` and `Set.z01`. Put
the engine's return code into the alert when a frame is ambiguous (`ret=-1
fam=0` said the application had never seen a family).

`--chain` and `--wrapped` compare NAMES on the volume against what the Linux
CLI produces, and require the application to have tidied up (the intermediate
layer for `--chain`, the decoded parts for `--wrapped`). `--chain` is what
tests README.md's envelope claim, and **the only harness that can see a
chain**: `run.py` drives the `-DUNC_MAC_AUTOTEST` build, which calls
`RunExtract` once; the unwrap loop is in the interactive application only. A
new envelope's specimen is three lines — wrap a fixture with
`tools/synth_wrapped.py`'s `macbinary()`, encode it with `reference/btoa` or
`synth_uu.plain()`, hand it to `--chain`. Pick a payload with no resource
fork: the CLI's listing has a `.rsrc` sidecar the Mac does not.

**Which reference a phase grades against follows from which build it runs.**
`run.py`, `checkdisk.py` and `os9.py --hfsplus` drive the autotest build and
compare against `macextract x -nr`; `interactive.py` and `os9.py --launch`
drive the shipped application and compare against the CLI with recursion on,
plus the `Comments` mapping checkdisk.py makes (`expected_names`;
DECISIONS.md).

### Putting a disk in while the Mac is running

`xdnd_insert.c` is a minimal XDND drag SOURCE, built on demand into
`$UNC_VMAC_HOME`. Mini vMac's X11 build accepts a disk at runtime only by a
drop: its control mode has no open-disk, it is built here with
`NeedRequestInsertDisk 0`, and `ParseOneUri` in `src/OSGLUXWN.c` turns a
dropped `file:` URI into `Sony_Insert1a`.

    cc -o xdnd_insert tools/vmac/xdnd_insert.c -lX11
    DISPLAY=:<n> ./xdnd_insert /path/to/disk.dsk

It finds the emulator window by its `XdndAware` property and exits nonzero if
there is none or the target never asks for the file list.

**Fetching the disk-inserted event is what MOUNTS the disk**: an application
that polled the volume list instead never saw a volume appear.

**`Mac.settle` answers "the screen stopped changing", not "the extraction
finished".** The progress dialog repaints once per engine callback (every
8–16 KB of input), so every settle that waits for an extraction passes
`quiet=EXTRACT_QUIET`, SECONDS the screen must hold still, longer than the
worst repaint gap (`--dest` once returned at 33 %).

**Re-measure `PROGRESS_CANCEL` in `interactive.py` whenever the dialog changes
shape.** A moved button makes the click land on the dialog background, the
extraction finish, and `3-cancelled.png` show the progress dialog instead of
the alert. The constant's comment derives it from the DLOG origin plus the
DITL rect; **check the screenshot shows the alert.**

## The AppleLink package expander — getting it out, with no emulator

The reference implementation for `.pkg` is `AppleLink Package Translator`
3.0.3, which ships **only** in the StuffIt Deluxe **3.0.7** installer (3.5
replaced it; FORMATS.md, *AppleLink packages*). The installer is two StuffIt
segments, and the join is arithmetic:

```sh
# The 3.0.7 installer, two floppies `hmount` opens, in
# ~/.cache/macextract/stuffit307/x/'Stuffit Deluxe 3.0.7'/
#   StuffIt Deluxe 3.0.7 Disk 1.dsk     the installer, segment 1
#   StuffIt Deluxe 3.0.7 Disk 2.dsk     segment 2
python3 - <<'PY'
import struct, sys
sys.path.insert(0, 'tools/vmac')
from superdisk import read_forks
B = "/home/claude/.cache/macextract/stuffit307/x/Stuffit Deluxe 3.0.7/"
seg = {}
for f in ("StuffIt Deluxe 3.0.7 Disk 1.dsk", "StuffIt Deluxe 3.0.7 Disk 2.dsk"):
    for v in read_forks(B + f).values():
        d = v[2]                       # NOT values()[0]: each floppy also
        if d[:2] == b"\xac\xd9":       # carries an `Icon\r` with an empty
            seg[d[2:4]] = d            # data fork. Select by the magic.
a, b = seg[b"\x00\x01"], seg[b"\x00\x02"]
# Each segment carries a 100-byte header, and the payloads must sum to the
# length the SIT! header declares. They do, to the byte.
assert len(a) - 100 + len(b) - 100 == struct.unpack(">I", a[0x6a:0x6e])[0]
open("/tmp/sd307.sit", "wb").write(a[100:] + b[100:])
PY
build/rel/macextract x --only "Aladdin/Translators/AppleLink Package Translator" \
    -o /tmp/sd307out /tmp/sd307.sit
```

Then pull `'Othe' 1` out of the resource fork with `spacesaver.resources()`
and write it to `$UNC_VMAC_HOME/pkgeng/alink307.bin`, where
`tools/derive_sqp.py --witness` looks for it.

- **`unar` cannot open the joined archive's translators usefully**: `lsar`
  lists the members but its `.rsrc` sidecars all start with the same 16 bytes
  and are not raw resource forks. `macextract x` writes the fork and its CRCs
  pass.
- **The hand join**: the check is the `assert` — `len(a)-100 + len(b)-100`
  equals the `0x14dd14` at offset 0x6a of segment 1, to the byte. (`macextract
  l seg1.data` once said *format not recognized*; whether today's segment
  support joins these two directly was not re-tested.)
- **The 148 MacsBug symbols are what make this readable.** A symbol FOLLOWS
  the routine it names, so a name at offset X names the routine ENDING at X;
  `tools/derive_sqp.py` cites routines by the address of their body.
  `spacesaver.macsbug_symbols()` returns the name offsets; mapping them
  backwards shifts every citation by one routine.

## Asking StuffIt Expander 4.0.2 about one rule — three runs

`src/fmt_binhex.c`'s last macutils citation is the skip of a LINE with
intermediate garbage. Expander 4.0.2 carries the alphabet twice (`DATA` 0,
`Eng ` 0) and no inverse table, so it was asked by running it, with
`expander.py --only expander` over three files built from
`fixtures/mac-rot13.hqx` (John Stiles's own posting of MacROT13; he wrote
HQXer):

| subject | what it is | Expander wrote |
|---|---|---|
| `control.hqx` | the fixture | `MacROT13.cpt`, **and** `MacROT13` — it expanded the Compact Pro archive too |
| `garbage.hqx` | one line of mail inserted mid-data | the same two: the `.cpt` is **3,309 B and md5-identical to this engine's**, and `MacROT13` is the 5,594 B application |
| `midline.hqx` | **one bad character inserted INSIDE a data line** | `MacROT13.cpt` at **0 bytes**, and no `MacROT13` |

**The third file is the experiment and the first two its controls**: only a
line test loses the other 64 characters of a line holding one bad one, and
Expander wrote nothing — so it is not macutils' rule, and `fmt_binhex.c`
keeps the citation (`tools/derive_hqxgarbage.py` has the other two readers,
no emulator).

**Reading the bytes needs `--keep`**, because this harness grades a run on
the NAMES it produced, which cannot tell a zero-byte file from a good one:

    tools/vmac/expander.py --only expander --keep <dir> -o <shots> x.hqx
    hmount <dir>/boot.hfv && hdir -a && hcopy -r ":MacROT13.cpt" out.cpt

**What this cannot see.** Why Expander stopped: no alert
(`expander-3-finished.png` is the bare desktop), and an empty file created
from the BinHex header fits both "aborted at the bad character" and "decoded
to a buffer and refused to commit". Both are a line test's opposite, which is
all the question needed.

## StuffIt Expander 4.0.2 over 2.0.1's archives — `exp402opt.py`

    tools/vmac/exp402opt.py -o <shots> --keep            # every subject
    tools/vmac/exp402opt.py -o <shots> DES MimePartial   # some

`expander.py`'s machine (System 6.0.8, Expander launched at boot) with nothing
timed, so it runs on `mv-4M`, one boot per subject:

- one 2.0.1 archive per Optimizer and per cipher;
- Compact Pro's own encrypted archive (`CptCrypt`);
- `compat9.py`'s three text subjects, the mpack set going onto the
  volume whole.

Each run selects the subject by name and presses Expand; with a password it
types it, presses Return once for whatever alert is up, quits, and reads every
new file off the image with `hcopy -m`. Results: FORMATS.md, *Run over the
hard cases*.

**Look at `-3-after-expand`, `-3b-typed` and `-3c-after-password` together.**
A refusal and a password typed into nothing leave the same empty volume; all
five ciphers here show the prompt, the masked password, then the refusal.

**What it cannot see.** The alert TEXT, which is read off the frames. 4.0.2
with DropStuff with Expander Enhancer, which this machine does not have
installed. And a wrong password, which it never types.

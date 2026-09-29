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
paths, not just a different splash screen. Run the System 7 tier at 4 MB.

**512 KB machines.** `--emu mv-512Ke` on either driver boots a Macintosh
512Ke, the smallest machine this application runs on: `sys30.py --emu
mv-512Ke` is **69/71** on the shipped build (2026-09-25; 67/71 with every
decoder resident, 66/69 before the sample grew, 65/69 before the reserve went
flat, 64/69 before the LZW bound), `run.py --emu mv-512Ke --system
System6.hfv` is **66/71** (2026-09-27, the shipped v0.34.0 build, the tier
`run_tiers.py` predicted before anything ran it; 64/71 on 2026-09-22 with
every decoder resident, 63/69 on 2026-09-04, 58/69 before the stack was cut) (FORMATS.md, *512 KB machines*). The resident budgets are **224,644 B** and
**129,244 B**, both re-taken on the machine 2026-09-27 with the floor's;
`tools/run_tiers.py` reproduces both tiers on Linux fixture for fixture, and
the one that never matched was the budget and not the model.

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
RAM rather than the ROM: same volume, same ROM, same System as the 512K above,
`ID = 03` on launch (FORMATS.md, *A Macintosh 128K*). `tools/vmac/memtest`
is what measures the machine instead — it prints the low-memory globals, then
bisects the largest single `NewPtr` the heap will grant, which is the question
the Segment Loader asks and the one `FreeMem` does not answer: `FreeMem` reads
4,846 B on a 128K and on a 512K alike, because the zone grows on demand. Build
it by hand like `traptest`, put it on as `Finder`, and read the numbers off
the screen; run it on **both** machines, because a number means nothing until
the same probe has been seen to produce a different one somewhere:

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
stack come out of the same span before the engine sees any of it. It also
paints its own white ground, because digits over the desktop's 50 % grey
cannot be read back off a screenshot.

**`mkmfs.py` writes the MFS volumes**, because Retro68's `.dsk` is always
800K HFS. It builds, lists and extracts:

    mkmfs.py $V/AppMFS.img --name MacExtract dist/MacExtract.bin
    mkmfs.py --list $V/AppMFS.img
    mkmfs.py --extract System $V/Sys11.img /tmp/System11.bin

**Use System 3.0, not System 1.1**, and use Apple's own MFS disk:
`setup.sh` fetches `Sys30MFS.img` by unpacking Macintosh Garden's
`System_3.x.sit` with this repository's CLI, and it boots the 64K-ROM machine
straight off. A volume built here from `Sys30.img`'s HFS copies boots too, if
a disk with different contents is ever wanted — `hcopy -m` lifts the files out
and the boot blocks come from the same disk:

    hmount Sys30.img; hcd "System Folder"
    hcopy -m System /tmp/System30.bin; hcopy -m Finder /tmp/Finder30.bin
    mkmfs.py $V/Sys30Boot.img --boot $V/Sys30.img --name "System Tools" \
             /tmp/System30.bin /tmp/Finder30.bin

To launch something without a Finder in the frame, put it on as `Finder`:
System 3.0 ignores the boot blocks' shell name on MFS just as it does on HFS,
so `--shell` is for System 1.1, which is the one system here that reads it.

    mkmfs.py --extract System $V/Sys30MFS.img /tmp/System30mfs.bin
    mkmfs.py $V/TrapBoot30.img --boot $V/Sys30MFS.img --name "System Software" \
             /tmp/System30mfs.bin build/traptest/TrapTest.bin:Finder

A volume with no `Desktop` file makes the Finder offer "minor repairs" on
first open; click OK and it rebuilds one.

**`traptest/` is the minimal reproduction** for what the 64K ROM actually
lacks: it paints a mark, makes one call, paints the next, and never returns —
a probe that exits has its marks erased by the desktop repaint before a
screenshot can be taken. Its calls are in the order the application makes
them, so where it stops is where the application stops; marks are eight to a
row in the top 75 points, because the system error dialog covers the middle of
the screen and a mark under it cannot be read from the screenshot that shows
the bomb. `-DTRAPTEST_NO_MEM` drops the two memory calls, which is how the
File Manager rows in FORMATS.md are reached on a 64K ROM at all. Build it by
hand, put it on the volume above as `Finder`, and read the marks — **on
`mv-512Ke` as well as `mv-512K`**, because a probe that stops early says
nothing until the same probe has been seen to finish somewhere:

    cmake -B build/traptest -S tools/vmac/traptest \
          -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
    cmake --build build/traptest

**System 3.0 has its own driver, `sys30.py`, and `run.py --system Sys30.img`
does NOT work.** That system ignores the boot blocks' shell name, so
`mkboot.py`'s usual shell replacement launches nothing and every fixture comes
back NOGRID — which reads exactly like an application that will not start
(DECISIONS.md 2026-08-30, *the shell name System 3.0 does not read*).
`sys30.py` boots to the Finder and double-clicks the application instead.
That changes how a run starts and not what it has — launching unloads the
Finder, 12 bytes' worth (FORMATS.md, *512 KB machines*). `interactive.py
--system Sys30.img --e2e` covers the user interface there; both its Standard
File row and its Finder icon positions are per-system tables, because System
3.0 leaves a different number of items in the volume window and lists the
invisible `DeskTop` file that System 6 hides.

Nothing here runs in `./ci.sh`: it needs ~80 MB of downloads, an X server and
minutes per fixture. It is a deliberate, on-demand check.

**What a full re-verification costs, as host wall clock** (measured
2026-08-07, two cores, all-out emulators — this is how long YOU wait, and says
nothing whatever about Mac Plus time; see the 1x note below). The totals were
~240 s and ~233 s when the sample held 44 fixtures; the per-fixture figure is
what every run since has reported, so scale it rather than trusting a total
measured on a different list:

| tier | command | cost |
|---|---|---|
| System 6.0.8, 1 MB, 55 fixtures | `run.py --mem 1M --list sample.txt` | ~5.1 s per fixture, one boot each |
| System 7.0.1, 4 MB, 55 fixtures | `run.py --system Sys7.img --list sample.txt` | ~5.1 s per fixture, one boot each |
| Mac OS 9.2, 22 fixtures | `os9.py --list os9sample.txt --launch` | tens of minutes — one full PowerPC boot per fixture |

**Stagger the start by a few seconds when the application has changed.** The
display race below is fixed, but the two runs still share one CMake build
directory per define-set (`build/mac-autotest`), and two `cmake -B` on it at
the same moment ends with one of them exiting 1 before it boots anything
(measured 2026-08-26). Once the build exists both runs find it up to date and
overlap cleanly, which is why parallel tiers usually work: the first run of
the day is the one that collides.

Run the two Mini vMac tiers in parallel if you have the cores — **safe since
2026-08-15**, and it was not before: `Display` looked for a free X display by
testing `/tmp/.X<n>-lock` and then starting Xvfb on it, which is check-then-act.
Two runs started together both chose `:90`, the loser's Xvfb died of the taken
lock, and its readiness probe then succeeded against the WINNER's server — so
both runs drew on one display and screenshotted each other's emulator. Three
fixtures "failed" with another run's numbers before anyone noticed the numbers
belonged to a different archive. Xvfb now picks the display itself
(`-displayfd`) and reports it back. Do NOT run
anything else alongside these, and **never alongside `./ci.sh`**: every
harness here grades itself through `tools/vmac_check.py`, which shells out
to `build/rel/macextract` as its oracle, and CI's `make clean` takes that
binary away mid-sweep. This warning named `os9.py` alone until 2026-09-05,
when a `run.py` floor sweep was started beside CI and came back **38/69** —
31 fixtures the Macintosh had extracted correctly and nothing could
compare, which reads exactly like a regression until the reason column is
read.

## What the pieces do

| file | role |
|---|---|
| `segcheck.py` | **replay every segmented-archive scenario in one command** — the six joining schemes, parts inside envelopes, and a chained file, across both harnesses |
| `setup.sh` | fetch + build the emulator, the ROM and the System 3.0, 6.0.8 and 7.0.1 images into `$UNC_VMAC_HOME` (default `~/.cache/macextract/vmac/`) |
| `sys30.py` | the **System 3.0 / Finder 5.1** tier: same disks, same grid, same grader as `run.py`, but launched by double-click because that system reads no shell name — see above |
| `mkboot.py` | strip that image to System + Finder and make it boot straight into the application |
| `run.py` | build the disks, boot, screenshot, decode, check. `--out-kb` sizes the DESTINATION volume, which is how the full-disk path is reached at all — see below |
| `interactive.py` | drive the real UI (SFGetFile, progress dialog, Cancel, Cmd-., the password dialog) and photograph each step |
| `os9.py` | boot Mac OS 9 on emulated PowerPC, launch the application from the keyboard, and check both forks of what it wrote — see below |
| `os9probe.py` | diagnostic: which input primitives actually reach the Mac OS 9 guest? Not part of any suite |
| `os9sample.txt` | the fixtures replayed on Mac OS 9 — one per format, since each costs a whole boot |
| `mountcheck.py` | boot a system image with disks attached and photograph the desktop — "does this mount?", and "does this system boot at all?" |
| `mkapmdisk.py` | build an Apple-partitioned transfer disk that Mac OS on PowerPC will mount |
| `checkdisk.py` | verify a run by READING its Out volume — both forks, and the names the on-screen grid cannot carry |
| `diskdoubler.py` | **ask DiskDoubler itself what it can write** — run the 3.7 application, compress a subject with each method its menu offers, read the method byte back; and `--adjudicate`, which runs a self-extracting fixture and grades the forks no oracle can decode |
| `ddpro.py` | the other half of the format: DiskDoubler **Pro** 4.1, which writes `DDA2` and whose Split command is the source of the `SPLT` questions still open |
| `ddencode.py` | **grade a method by WRITING it**: encode a fork, hand it to Salient's own 1991 DiskDoubler, and see whether it comes back. How methods 3, 4 and 5 were graded with no specimen |
| `ndd.py` | the releases nothing here had run: Salient's **3.1.2** (1991, the oldest reachable — it has the only method 2 fork), **DiskDoubler 4.0** and **Norton DiskDoubler Pro 1.1** (Symantec — whose application is 4.1.1). `--specimens`, `--harvest` and `--grade` need no emulator |
| `superdisk.py` | grade SuperDisk! with its own self-extractors; `--nest`/`--stored`/`--rootfile` hand that extractor a stream written here; `--on-mac` replays both payloads through our application |
| `spacesaver.py` | Aladdin's **SpaceSaver**, off the StuffIt Deluxe 5.0.1 CD. 3.5.1 runs; 5.0 does not run on 7.0.1. `--layout` reads the format out of it without booting anything — see below before spending a boot on it |
| `sdcompress.py` | the other half: Alysis's 1991 **SuperDisk! control panel**, which COMPRESSES. It wrote the five specimens the single-file container was derived from, and `--verify` re-grades them |
| `maclha.py` | **MacLHA 2.00**, out of the corpus (`derived-MacLHa_2.00.sit`), driven to write a `.lzh` holding a file with a real resource fork — the specimen no MacLHA archive in reach is. `--setup` builds the volume, `--make` drives the application (keyboard where it has a shortcut; its Header and Type menus are HIERARCHICAL and cannot be used here, and nothing needs them because `MacBinary` is already checked), `--check` grades both forks with our CLI. **The Type menu was worth reading anyway, and it is now**: `LHa`, `LHarc`, `None` — `-lh5-`, `-lh1-`, `-lh0-` — so it cannot write an `-lh2-`/`-lh3-` specimen — which `tools/run_lzh.py` grades against LHa's own encoder instead (TESTING.md) — and the inaccessible submenu costs nothing (read out of `MENU` 134 with `hcopy`, no emulator) |
| `expander.py` | **the yardstick**: StuffIt Expander 4.0.2 and this application on one Mac Plus, over one archive, timed by one instrument. `--fetch` downloads Aladdin's distribution and unpacks the application out of it; `--sizes` reads both memory partitions without booting anything |
| `macmime.py` | **a MIME message written BY a Macintosh**, with mpack's own Macintosh port: `tools/macmime/` compiles `encode_applefile()` and `encode()` out of `reference/mpack` unmodified, and this boots System 6.0.8 into them. `--make` writes the specimen, `--check` grades it (18/18) — see below before changing it, because two of its three failure modes were in the HARNESS |
| `mkcollide.py` | build an archive whose names collide on HFS, and verify what `BumpName` did with them — nothing in the corpus collides |

`tools/quickdraw-repro/` is a sibling that reuses `mkboot.py` and this
directory's `Display`/emulator plumbing to answer one narrow question about
System 6's Toolbox. It is where `mkboot.py --finder` came from.

`tools/aetran/` is the other sibling: a Retro68 application that sends one
Apple event to another application, which is how the btoa/atob translator is
reached without its inaccessible submenu (`sitcrypt.py --btoa-send`, below).
It is built by that harness, never by `ci.sh`, and it is System 7 only.

The verification halves live one directory up because they are useful on their
own: `tools/decode_grid.py` (screenshot → eight numbers) and
`tools/vmac_check.py` (those numbers vs. the oracle).

## Why it works the way it does

**Results come off the SCREEN — and, since 2026-08-02, off the disk as well.**
The app paints its results as a black/white bit grid (three calibration
squares, a sync word, eight 32-bit values) which a screenshot captures exactly;
see `at_report()` in `mac/macextract_mac.c`. That is what `run.py` decodes.

The reason it was the *only* channel used to be a claim that Mini vMac's
write-back is "lazy and partial — it will commit one fork of a file and not the
other", so extracted files could not be read back on the host. **That does not
reproduce and is withdrawn** (BLOCKERS.md): the whole sample was replayed with
`--keep-disks` and every Out volume read back byte-exact, both forks, names
included — 55/55. See "Checking a run off the disk" at the end of this file.

The grid stays: it is proven, it needs nothing of the volume, and it reports
liveness and setup failures that a disk cannot. What it cannot do is carry a
NAME, which is why `checkdisk.py` now exists beside it.

**A run that drives the FINDER ends with Special > Shut Down, and must.**
Mini vMac writes the guest's sectors through buffered stdio and flushes
when a volume is ejected, so killing the emulator with a volume still
mounted loses whatever the Finder had not written — and an image COPIED
out of a killed session is torn: it does not boot at all. `arcmac.py`
picked Shut Down for that reason in M13; `spacesaver.py` did not, and
three of its runs read their subjects back "unchanged" from a machine
whose every frame is the striped garbage screen. One of those readbacks
became a documented fact about the format (BLOCKERS.md). Either shut
down, or put the subjects on a second volume and Put Away (Cmd-Y) — what
`sdcompress.py` does.

**And photograph the pick, because the item is one row from a different
one.** Shut Down is at **(225, 139)** on System 7 and at **(175, 123)** on
System 6 — the two Special menus are not the same length, and 123 on System 7
is **Restart**, which `spacesaver.py` and `sitcrypt.py` picked in every run
either had ever made (measured 2026-09-01 off their own forty-three
`*-special-menu.png`; corrected in both; BLOCKERS.md, withdrawn claims).
Restart ejects the volumes too, which is why nothing failed and nobody
noticed — but `rescomp.py` has the case where it tore a write, below.

**The app is the boot shell.** The boot blocks' shell name (offset 0x1A) is
rewritten from `Finder` to `macextract`, so the ROM hands control straight to
the application. No Finder, no synthetic double-click, no mouse automation —
the machine boots into the test and nothing else runs.

That is a materially different environment, and it is worth naming: **nothing
mounts disks**, and no other process competes for the heap. A disk inserted
after startup never appears — the disk-inserted event is posted, but volumes
are mounted when somebody asks and normally that somebody is the Finder
(measured: the volume walk saw exactly one volume after 30 s, with both images
present and both mounting fine when the Finder was left as shell). The
autotest build calls `PBMountVol` on each drive number first
(`MountAllDrives`); the interactive application uses Standard File, which does
its own disk handling.
`mkboot.py --finder` is the other arrangement — Finder left as the shell, the
application at the volume root, launched by double-clicking it — for questions
that only make sense outside the boot-shell setup. `tools/quickdraw-repro/`
uses it.

**The System Folder is stripped to System + Finder.** The stock image ships
with a dozen INITs and cdevs; on the 1 MB floor-target machine that is the
difference between a result and a dead machine, and it would make peak-heap
figures incomparable between runs.

**The application always says whether it is alive.** Before doing any work it
paints a grid with `ret = -1000` ("running"); a missing `In`/`Out` volume paints
`-1001`/`-1002`. So the host can tell *never launched* from *still decoding*
from *bad disk set* — which a bare timeout cannot. `run.py` reports those as
`NOGRID`, `TIMEOUT` and `SETUP` respectively, distinct from a real `FAIL`.

**A killed run used to leave its emulator behind — fixed.** Both `run.py` and `os9.py` start
the emulator with `start_new_session=True` on purpose — a stray signal to the
process group must not take it down mid-write — so a driver killed by a
`timeout` never reaches its cleanup and the child survives. Seen twice:
an orphaned `qemu-system-ppc`, and two orphaned `Xvfb` displays. Check with
`pgrep -x minivmac`, `pgrep -f qemu-system`, `pgrep -x Xvfb` after any
interrupted sweep; they cost CPU the next emulator needs. Both harnesses now
turn SIGTERM and SIGINT into a `SystemExit`, so the signal unwinds and the
existing cleanup runs; verified by interrupting a 1x run with a live emulator
and finding nothing left over, and again on 2026-08-02 by interrupting an
`os9.py --list` sweep mid-boot — it printed "interrupted by signal 15" and
left zero `qemu-system-ppc` behind.

**`EMUDIED` means the host failed, not the Mac.** The emulator process
occasionally exits within a few seconds of launch — twice in an 88-run sweep
here — and both fixtures passed on an immediate re-run. That used to be
reported as `NOGRID` with the text "nothing decodable within 300s", which
reads like a Mac-side bug and is wrong on the elapsed time as well; it is now
its own verdict. **Re-run an `EMUDIED` fixture before drawing any conclusion
from it.**

**Timing is settled.** `run.py --emu mv-4M-1x` runs an authentic build and
splits boot from extraction (the app paints its "alive" grid before touching a
disk, so the harness can see where work starts), and `timing.txt` is the set
to measure. 8/8 since 2026-08-02, plus StuffIt 5 / Arsenic on 2026-08-07;
FORMATS.md has the tables. This paragraph read "attempted and not settled"
until 2026-08-07, long after the measurements existed — the 306 KB BinHex that
"did not finish in fifteen minutes" simply takes 150 s, and every timeout
chosen for it expired mid-run because its decode rate is very non-uniform.
The instrument that settled it was `UNC_AT_PROGRESS`, which paints the
engine's byte counter into the grid as it runs, so a run that has NOT finished
can still be interrogated:

    t+~7 min     49,152 / 306,651   (16%)
    t+~9 min     98,304 / 306,651   (32%)
    t+11 min    303,104 / 306,651   (99%)   <- 205 KB in the last 100 s

Still true and still the trap: **do not poll every few seconds**, because
decoding a 512x342 grid in Python steals the CPU from the emulator you are
timing.

**And on a LONG 1x run it does worse than steal CPU: it reports a bogus
FAIL.** `--poll 5` and below finish in about five seconds with `nfiles 0` and
a nonsense value in the grid's `ret` slot — four times out of four on
`derived-Library_ISBN_Barcoder.sit` at `--mem 1M --emu mv-1M-1x` (twice at
`--poll 5`, once at `--poll 2`, once at `--poll 1`), against five clean runs
at `--poll 20`. **Use `--poll 20` for the Arsenic fixtures**; the timings in
FORMATS.md were taken there. The likely cause is a poll landing while the app
is still painting its "alive" grid, so `ret` holds neither a result nor the
running sentinel and run.py takes it as final — that is a **hypothesis**, and
the failure pattern is what is measured. **FIXED 2026-08-28, and `--poll 1` now passes.** `--poll 3` was not safe
at 4 MB either — re-measuring `timing.txt`, `popper-1.7.tar.Z` and
`derived-PackIt.pit` both reported FAIL with a truncated total and
`peak heap 0 B`, 2 of 13, while passing at `--poll 20` and all out at both
memory sizes. The cause is not a race to be avoided by polling slowly:
`at_report` erases the screen to white and paints FORWARD, and it painted the
sync word FIRST, so a screenshot taken mid-paint decoded cleanly with the
unpainted tail reading as zeros. The kept frame proves it —
`derived-PackIt.pit` reported `totalRsrcLen` 0x00008000 where the truth is
0x0000DB05, which is that value with painting stopped after its 17th bit.
The sync word is now painted LAST, so it certifies completion: a mid-paint
screenshot has no sync, `decode_grid.py` rejects it, and the host looks
again. Both fixtures pass at `--poll 3` and at `--poll 1`.

**What still argues for a slower poll is CPU, not correctness.**
`decode_grid.py` costs ~50 ms a call — mostly Python parsing an ASCII PGM of
every pixel — so `--poll 1` spends ~5 % of the core the 1x emulator is
pacing against. Crop the region and emit binary `P5` and that goes away.

**Two 22-minute runs were spent finding this out**, on an A/B that then could
not be resolved: `-Os` and `-O2` builds of `sit_arsenic.c` came out exactly
one poll interval apart at `--poll 20` and both `--poll 5` re-runs failed
instantly. FORMATS.md, *Per-file `-O2`*.

**Wall-clock time is not Mac Plus time — except in a 1x build.** `setup.sh`
produces four emulators, because RAM size and speed are both compile-time
options. `mv-4M` and `mv-1M` run *all out*, as fast as the host allows, which
is what the fixture sweeps use because correctness does not depend on speed
and 55 fixtures x 2 memory sizes at Mac Plus speed would take all day.
`mv-4M-1x` and `mv-1M-1x` run at authentic 7 MHz and are the **only** builds a
timing claim may be drawn from. `interactive.py` defaults to `mv-4M-1x`,
because at all-out speed the extraction is over before the progress dialog can
be photographed and Cmd-. has nothing left to cancel.

`mv-1M-1x` was added on 2026-08-07 for one reason worth remembering: the
StuffIt 5 decoder only falls back to its low-memory inverse BWT when memory is
tight, so **the cost of that fallback is not measurable on any of the other
three** — a 4 MB machine never takes the path, and both all-out builds cannot
be quoted for time. A claim that lives at the intersection of two axes needs a
build at that intersection.

**This box has two cores** (`nproc`; the host CPU has four and the container
is limited to two — the figure here read "one core" until it was checked on
2026-09-05). At 1x the emulator paces itself against real time, so anything
else CPU-heavy — `./ci.sh`, a corpus sweep, a second `interactive.py`, or
another SESSION's emulator on the same machine — inflates the number you are
measuring. Run timing alone.

**And it is not only the number.** `interactive.py` waits fixed seconds
between clicks, so a Mac running below 1x desynchronises the whole
choreography: two phases run side by side on 2026-08-09 and every frame of one
came out a step early — `3-cancelled.png` showing the progress dialog,
`4-back.png` showing the alert that belonged in it, the Cmd-. round never
happening at all. Nothing failed; the screenshots were simply of the wrong
moments. **Run the interactive phases one at a time.**

**`interactive.py` is mostly not self-checking.** It guarantees the same clicks
in the same order and writes a numbered screenshot per step; judging them is
the reader's job. Every phase but `--e2e` does end on ONE thing that can fail
on its own — `--segments` on the joined bytes, `--dest` on which volume holds
the output, `--wd` on which folder does, the default phase on the names its
second boot wrote — and those exist because a screenshot of the wrong dialog
looks exactly like a screenshot of the right one. The default phase once
reported "settled after ~134s" for a run that spent all 134 in a "Replace
existing" alert and extracted nothing (2026-08-09). `--e2e` has no such line
on purpose: what it is for *is* a photograph, an extracted application drawing
its own splash screen.
Three lessons are baked into it, all of which produced confident-looking
nonsense first:

- *Press buttons with Return, not coordinates.* Clicking SFGetFile's Open at a
  measured point hit **Drive** one row up, switched to an empty volume, and
  made every later screenshot meaningless while still "succeeding".
- *Set X input focus explicitly.* With no window manager nothing assigns it,
  so key events go to the root window. Mouse clicks are delivered by position
  and work anyway — which makes it look like the Mac ignores one particular
  key rather than receiving none.
- *A phase written for a new path can leave the old one less covered.*
  `--dest` passed twice while the DEFAULT destination was broken, because it
  sends the output to an empty floppy and the bug needed the archive's own
  folder. Ask which case the new phase stopped exercising.

## Making Now Compress archives with Now Compress — `nowcompress.py`

Three of the five Now Compress block shapes had no real archive anywhere, so
they were graded against the implementation `fmt_now.c` was transcribed from.
`nowcompress.py` fixes that the way `cptsegment.py` fixed segmented Compact
Pro: by running the original application.

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

The compressor is **Now QuickFiler**, whose menu has Compress ▸ Faster/Smaller
and Archive ▸ Faster/Smaller. Files go on the volume with `hcopy -r`, which
writes the **data fork alone** — so until `--case forks` every member the
harness had ever made had an empty resource fork, and a rule written in terms
of the two forks looked like a rule about tables (BLOCKERS.md, *Withdrawn
claims*). That case passes its members through `make_volume(macbinary=...)`
instead, which is `hcopy -m` and carries both forks. Specimens land in
`$UNC_VMAC_HOME/specimens/now/<case>/` with the inputs beside them and a
screenshot per step; `tools/run_now.py` picks them up if they are there and
skips them with a message if they are not.

**A case that varies one property of a COMPRESSED block has to keep the
content compressible.** The first build of `--case match` used a keystream,
which is incompressible: the encoder stored seven of its eleven members, and a
stored block has no header and so no byte 2 to read. The rebuild gives each
member 1,000 de Bruijn bytes — unique substrings, so nothing matches them —
followed by 1,000 copies of a letter of its own, which compresses, matches
nothing earlier, and costs every member the same (DECISIONS.md 2026-09-21,
*the ladder that was walked back down*).

Three things to know before re-running it:

- **The application is commercial and is not committed**, exactly like the
  ROM: `--setup` fetches Macintosh Garden's installer image by URL and checks
  its MD5. Now Utilities asks for a serial number at first launch and offers a
  one-week demo; the demo is what the script uses.
- **The installer image is NDIF**, Apple's undocumented compressed format.
  `--setup` converts it to a raw HFS volume with an ADC decoder and a block
  map derived from the image itself; if the conversion is ever wrong the
  result will not mount, which is the check.
- **The installer's checkbox list is read back off the screen** after every
  click. Clicking it blind is how the first attempt turned QuickFiler off.

**`--setup6` and `--case6` are the SECOND encoder**, Now Utilities 6.0
of March 1996, and they exist because a field constant across
everything one program writes is a fact about that program
(docs/formats/now-compress.md, *Two encoders*). Four differences from
the 5.0.1 path, each of which cost a run to find:

- **there is no installer to drive.** 6.0's `.sit` holds a StuffIt
  archive of finished files, so `--setup6` places them instead: the
  extension and its toolbox into `System Folder:Extensions` of a copy
  of `Sys7.img`, the droplets at the root. It needs `unar`, the outer
  archive being StuffIt 5;
- **the leading spaces in `  Now Toolbox` and ` Now QuickFiler
  Extension` are the load order** — extensions load alphabetically and
  the Toolbox must come first — so they are kept, not stripped;
- **6.0's QuickFiler menu sits mid-bar**, not against the screen edge,
  so its submenus open to the RIGHT and its item rows are 36 px higher
  than 5.0.1's. Its Demo button is at (264, 306) rather than (237, 306);
- specimens land in `specimens/now6/` so that nothing overwrites
  5.0.1's — comparing the two directories is the experiment.

**Now Utilities 3.0.2 and 4.0.2 are not worth fetching**: they have no
compressor at all. Their two disks each are Super Boomerang, NowMenus,
WYSIWYG Menus, Startup Manager and the rest; QuickFiler arrives in 5.

**QuickFiler also compresses by itself, and both versions do.** Its
menu's *Don't Compress* and *Compress When Idle* items belong to a
background compressor: it keeps queues (`ToBeCompressedDB`,
`ToBeRecompressedDB`, `ToBeDecompressedDB`) and an exclusion list
(`DoNotCompressFileDBNV`), compresses files that have been unmodified
for a set time once the system has been idle for one, and expands them
again on open. *Don't Compress* excludes the selection — by item,
creator, type or Finder label — and the System Folder is excluded
always. Its own balloon help is the source, and 5.0.1's extension
carries the same strings as 6.0's, so this is not new in 6.
**It has never fired in a run here**: a case's volume comes back with
only the files the menu was released on changed — the `archive` case
leaves `mixed.bin` and `one.txt` at 49,000 and 7,500 bytes beside the
`.sea` — and the mis-clicked first 6.0 run came back with nothing
compressed at all. A specimen is still worth attributing to the menu
pick the screenshot shows rather than to the run, which is why every
case keeps that screenshot.

**The `probe` case exists to make a code table legible**, and it is the
technique worth reusing: its four members are a 4,000-byte run of one byte,
6,000 bytes over `{A, B}`, 6,000 over `{A, B, C, D}` with known frequencies,
and 6,000 whose second half repeats its first. A block whose literals can
only be two known bytes is found by what its table MUST contain rather than
by where the table might be — which is how the archive coder's header was
read at all, the harness's other members being prose and keystream whose
tables look like every other table (docs/formats/now-compress.md, *Shape 3*).

**`--case reach` answers a question about a bound, and that is the other
thing a made-to-order archive is good for.** Five 16 KB members whose
fifth is a byte-for-byte copy of the first put a perfect match 64 KB back;
the encoder does not take it, and the archive's largest offset is 32,766
against a 32,768-byte window. That is what says `NOW_HISTORY` is right and
the offset table's reach to 65,791 is capacity nothing writes
(DECISIONS.md 2026-09-21, *the window that stopped at the fork*).

**`--case tokdist` and `--case toklen` plant a match whose length and
distance are known**, which is what turned the archive coder's tokens from
a bit pattern into two tables. Each member is a slice of a **de Bruijn
sequence of order 2 over 256 symbols** — every pair of bytes occurs
exactly once in it, so an LZ encoder can find no match in it at all —
followed by a copy of that member's own first bytes and a compressible
tail, because Now Compress refuses a file it cannot compress. The one
match in the member is therefore at a distance this file chose (40 of
them, 2 to 16,384) or of a length this file chose (24, from 2 to 255),
and `tools/derive_now.py` reads the token's bits off against it
(DECISIONS.md 2026-09-21, *the pair that never repeats*).

Both cases are one emulator run each, ~4 minutes, and they leave 64 members
of real encoder output behind; two of `tokdist`'s came back as a Huffman-only
block INSIDE an archive, a combination no other specimen has.

**`--case huffgap` was for the gap that turned out not to exist.** Ten files
of mixed content, compressed rather than archived, to multiply the one
shape this project had two specimens of — where a Huffman-over-LZSS block's
bit stream begins was down as unknown, "23 bits after the table in one and 18
in the other". Eight of the ten came back as that shape, and all eight start
where the two did: one zero byte after the table, then the `00 03` that opens
any LZSS stream, coded through the block's own table. The case is kept
because ten blocks is what makes the rule a measurement rather than a
coincidence, and because its byte-0 values (4, 6, 7, 8, 10, 14) are what
showed that byte to be a flush count.

**`--case deep` and `--case deeparc` asked for a code past 15 bits and were
refused.** Their four files have Fibonacci byte histograms — the distribution
that makes a Huffman code as deep as it can be, 20 bits at 21 symbols — and
are compressed in one case and archived in the other, because a Huffman-only
block had only ever come out of the archive path. Every table that came back
is 10 to 13 deep with an escape count of zero: each shape puts an LZ coder
under the Huffman one, and it eats the skew that would have made the code
deep. The cases are kept as the evidence for a negative
(docs/formats/now-compress.md, *What this note does NOT describe*).

**`--case tree` puts folders in an archive**, which only the corpus's 1995
fixture had: two folders and two loose files, so that how the entry table
nests them is read off more than one specimen. It is a pre-order
flattening — a folder record, then exactly the number of entries its +80
field states (docs/formats/now-compress.md, *The archive layer*).

What the encoder writes per mode is FORMATS.md ✧; why any of it matters is
DECISIONS.md, "Now Compress, written by Now Compress".

**`--adjudicate` grades us with the archive's own decoder.** A self-extracting
archive contains the extractor that shipped with it, so it is both a specimen
and an implementation:

    tools/vmac/nowcompress.py --adjudicate \
        fixtures/SyntheticReferences2.0.sea.bin \
        fixtures/derived-SyntheticReferences2.0.sea

puts the `.sea` on a 25 MB volume, runs it under System 7, reads the volume
back and compares every fork against our own extraction — resource forks with
bytes 16..127 masked, the `vmac_check.py` convention, because the Resource
Manager stamps that region whenever it touches a file. That is what settled
the corpus's 1995 archive, which `unar` cannot decode at all. It works for any
`.sea` in the corpus, not just this one.

**And it takes any archive at all, by splicing.** `tools/mutate_now.py`'s
`splice` puts a different data fork into a `.sea`'s MacBinary, so the
extractor Now Software shipped can be pointed at an archive this project
wrote — which is how `synth_now.py --ladder` asks the encoder about the
thirteen synthetic archives (TESTING.md). **The control that route needs
is a length change**: `probe`'s 3,830-byte archive inside `tree`'s
self-extractor, which was built around one 1,894 bytes long, extracts all
four members byte-exact.

**What `--adjudicate` could not see until 2026-09-21**: an extractor that
refuses an archive leaves an empty volume, an empty volume compares zero
forks, and zero forks all agree — so it printed *"agrees with us on every
fork"* for two archives it had refused. It now fails when it graded
nothing. Read the fork COUNT, not the verdict.

**`--expand` runs the DECOMPRESSING half**, which is what turns "nothing here
reads this field" into a statement about the format:

    tools/mutate_now.py --byte2 0x5a --splice IN.bin OUT.bin IN.dat OUT.dat
    tools/vmac/nowcompress.py --expand /tmp/out OUT.bin ...

`--expand` puts MacBinary files on a volume — MacBinary because the type and
creator are what make QuickFiler offer the item at all — selects them all and
releases the menu on **Decompress**, then reads the volume back into `OUTDIR`.
`tools/mutate_now.py` is the other half: it changes ONE field, recomputes
every checksum over it (a block's four-byte trailer, an entry record's, the
block table's, the file header's) and can splice the result back into a
MacBinary or a `.sea`, so what reaches the Mac is a file no correct reader can
tell from the original. Between them they settled four fields on 2026-09-21
(docs/formats/now-compress.md).

Five things to know:

- **Decompress and Dearchive are plain menu items** at y 300 and 235, not
  submenus, which is the only reason this can be driven at all: Mini vMac
  cannot select a submenu item however the mouse is moved (*hierarchical
  menus*, above).
- **Put a control on the volume.** Every run here carries one unmutated file
  spliced through the same path; without it a failure cannot be told from a
  harness fault, and the splice rewrites the MacBinary length and CRC.
- **QuickFiler names what it expands after the entry record's name**, not the
  file's, so `--rename` changes both when several mutations of one specimen
  have to share a volume. Give a rung a name **as long as the one it
  replaces**: the encoder leaves 23 catalogue-shaped bytes after a short
  Pascal name, and a longer name walks over them.
- **A file it refuses puts up an alert and waits**, so `--expand` presses
  Return once per file on the volume rather than twice per run, and waits
  fifteen seconds per file after them. That is what makes a whole ladder
  of mutations one run instead of one run each: before 2026-09-21 the
  first refusal would have stopped every file behind it, and a ladder is
  put on one volume precisely because some rungs are expected to be
  refused. **A file it has not REACHED looks exactly like one it
  refused** — same type, same creator, same bytes — which is how a
  five-rung ladder first came back with three refusals of which only one
  was real. Read the last screenshot before believing a refusal: an icon
  still highlighted is one still in the selection, and one replaced by
  its expansion is not.
- **Two refusals, two different alerts, and the difference is the
  measurement.** *"A part of the file X is damaged. Do you want to continue
  decompressing…"* is a BLOCK the decoder could not accept — it offers
  Continue and goes on to the next file. *"…is damaged and cannot be
  repaired"* is the file being rejected outright, which is what a file
  written here from scratch gets. Photograph the alert: which one it is
  says which layer noticed.

## Making ArcMac archives with ArcMac — `arcmac.py`

An ArcMac entry's payload is one compressed stream holding both forks, and no
document anywhere states which fork comes first. `arcmac.py` measured it the
way `nowcompress.py` measured the Now Compress block shapes: by running the
original application.

    tools/vmac/arcmac.py --wild     # the two archives in the wild, fork by fork
    tools/vmac/arcmac.py --setup    # fetch ArcMac 1.2a, rebuild the application
    tools/vmac/arcmac.py --make     # boot, archive a two-fork file, read it back
    tools/vmac/arcmac.py --decide   # report which fork the payload starts with

The answer is **data fork first** (FORMATS.md ★★★; why it had to be measured
is DECISIONS.md, "ArcMac's fork order"). Specimens land in
`$UNC_VMAC_HOME/specimens/arcmac/` as plain `.arc` files, with the input forks
beside them and a screenshot per step. Nothing here runs in `ci.sh`.

The specimens are `run.py` inputs like any other archive, and since 2026-08-21
they are graded like any other archive too — `--expect` grades a file that has
no oracle manifest against this engine's own Linux output, which is what the
manifest was only ever used to locate:

    tools/vmac/run.py --expect $UNC_VMAC_HOME/specimens/arcmac/Packed.ARC

Before that it had to be done by hand, reading the grid:

    tools/vmac/run.py --pngdir /tmp/p $UNC_VMAC_HOME/specimens/arcmac/Packed.ARC
    tools/decode_grid.py /tmp/p/Packed.ARC.png

Either way both fork CRC-32s must equal those of `specimens/arcmac/in-data`
and `in-rsrc` — the bytes that went INTO ArcMac on the emulated Mac in the
first place. That closes the loop without an oracle: encoded on a Mac,
decoded on a Mac, checked against the input. What `--expect` does NOT do is
adjudicate the Linux side; the suite for that format does (TESTING.md), and
the run says so on every line it prints.

Four things to know before re-running it:

- **The encoder comes out of the archive it is needed for.** `--setup`
  fetches `ARCMACRC.BIN` — shareware, by URL, checked by SHA-256, not
  committed — whose first entry IS the ArcMac application: an APPL with an
  empty data fork. That entry is decoded with our own CLI and re-wrapped as
  MacBinary, so no self-extractor has to run inside the guest.
- **Do not copy a Mac header's Finder info into MacBinary unexamined.** The
  first attempt put the application on the volume where the Finder did not
  show it; the disk read "112K in disk, 1 item", which looks like a failed
  copy and is not. `arcmac.macbinary` passes 0. **Why is NOT
  `invisible`, which this said until 2026-09-22**: `fdFlags` is `h[42:44]`
  per `macunpack/arc.h`, and across all 5 ArcMac files and 11 entries here
  it is 0x2100 on the application and 0x0100 on every document —
  `fHasBundle | fHasBeenInited`, with `fInvisible` (0x4000) set nowhere
  (BLOCKERS.md, *Withdrawn claims*).
- **ArcMac 1.3c is a command shell, not a dialog.** It opens "Martian
  Operating System"; the verb is `arc a<modifiers> archive files`, documented
  under *ArcMac Command Summary* in the `ARCMAC.DOC` that ships with it. Pass
  `--cmd` (repeatable) to run anything else at that prompt.
- **The run ends with Special ▸ Shut Down** — the general rule above; here
  it is what the Finder showing `Test.ARC` on screen and the host's copy of
  the image not having it cost.

## Asking DiskDoubler what it can write — `diskdoubler.py`

Six of DiskDoubler's eleven methods were declined because "nothing reachable
writes one". Running the application settled that: two of the six were
reachable, and are now implemented (BLOCKERS.md).

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
Compress" popup. What each one writes is FORMATS.md ✦; why it matters is
DECISIONS.md, "DiskDoubler methods 1 and 7". Specimens land in
`$UNC_VMAC_HOME/specimens/diskdoubler/` with the input forks beside them
(`in-data`, `in-rsrc`) and a screenshot per step. Nothing here runs in
`ci.sh`.

Four things to know before re-running it:

- **The application does not run on its own.** DiskDoubler is an extension
  with an application beside it; launched with no INIT loaded, the
  application takes the personalization, writes it into its own resource fork
  and quits without ever showing a window — which on a screenshot looks
  exactly like a crash. `--install` puts the INIT in Extensions, and the work
  is then done from the Finder's own **DD** menu.
- **Both halves personalize themselves on first use**, into their own file.
  Mini vMac boots from a COPY of the boot image, so the INIT does it on every
  run; the dialog has no default button, so Return leaves it exactly where it
  was.
- **Method 7 is not reachable from this keyboard.** The popup only offers
  "Sigma Hardware" when a Sigma Designs compression card is fitted, and
  nothing here emulates one. The specimens for it come from `--wild`: the 3.7
  distribution disk was built on a machine that had the card, and two THINK C
  libraries on it are method 7.
- **The run ends with Put Away, and must**, for the reason `arcmac.py`
  documents below: Mini vMac flushes the guest's writes when the volume is
  ejected, so a run killed with it still mounted reads back an unchanged disk.

### The oldest DiskDoubler there is — `--beta`

**DiskDoubler ß05, Copyright 1990 Salient**, which is four versions older
than anything this project had run and the reason the 84-byte header
turned out not to be the format's (`docs/formats/diskdoubler-container.md`,
*The header size, and the 1990 header*). It rides in
`DiskDoublerExpand3.sit` on the same Macintosh Garden page `--setup`
already fetches from, and `--beta` fetches it by URL and sha256 like
everything else here.

Four things that are different from every other run in this file:

- **It is an INIT with no application at all**, so `--install`'s System 7
  image is no use: `install_beta()` puts it in a **System 6.0.8** System
  Folder and the work is done from the Finder's own **DD** menu, which
  that INIT adds. System 6 because the INIT is two years older than
  System 7, and because 6.0.8 is the tier every other figure here is
  quoted on.
- **The menu's x is measured, not assumed.** `--beta-probe` boots and
  photographs the menu bar without clicking anything; the Finder's own
  five titles leave **DD at 221–234**, which is where `BETA_MENU_X`
  comes from. Re-measure it if the boot image changes — an INIT's menu
  sits wherever the Finder's leave room, and a miss here reads as a run
  that compressed nothing.
- **There are no settings.** The menu is `Compress Selection;Expand
  Selection` and that is the whole application, so there is one thing to
  write and `--make`'s four-item popup has no counterpart.
- **`--beta-verify` grades it against the bytes DiskDoubler was given**,
  because `unar` answers "format not recognized" for one of these and no
  other reader exists. Two passes since 2026-09-22, when the engine
  learned the shape: the specimen **as it is**, which grades the code
  that ships, and the specimen **rewritten with an 84-byte header** and
  the two forks' checksums written where one keeps them — the stronger
  statement, because those sums are computed from the INPUT and are the
  two DiskDoubler 3.7 itself stored for the same forks. Both forks
  byte-exact both ways.

### The two `DDAR` record shapes no corpus fixture has — `--combine`

All 36 entries of the corpus's 7 `DDAR` archives are files at the top
level, so the folder records and the `0x20` raw-fork shape were read by
nothing here and `docs/formats/diskdoubler-container.md` could not
measure them. `--combine` builds a volume with a known tree on it and
drives **Combine**, DiskDoubler's own archive command, from the same DD
menu `--make` uses.

    Payload/Nest/One, Payload/Nest/Two     text
    Payload/Raw                            24 KB nothing compresses
    Payload/Forked                         data plus a 340-byte resource fork
    Payload/Empty                          zero bytes
    Payload/Already.dd                     a file DiskDoubler had compressed

`--verify-combine` runs offline, on the saved specimens, and grades this
engine's extraction against **the bytes DiskDoubler was given** — 7
entries, 0 disagreements. Three things to know:

- **the items are selected by typing, not by clicking an icon.** The
  Finder selects by name, so `p` picks `Payload` and Cmd-O opens it;
  Cmd-A inside it is what enables Combine, which is greyed out until
  something is selected.
- **`--combine raw` needs `--make A` to have run**, because one of its
  subjects is the `.dd` that produced. Combine turns out to EXPAND an
  already-compressed file and archive what was inside, so that entry is
  graded on the original's bytes.
- **It did not produce the `0x20` flag**, and five shapes were offered
  to it on purpose. That is a measured negative about DiskDoubler 3.7,
  not about the format; 1.x and 2.x are not reachable from here.

### The forks neither oracle can decode — `--adjudicate`

    tools/vmac/diskdoubler.py --adjudicate lha-expander-103.hqx --write-manifest
    tools/vmac/diskdoubler.py --adjudicate terrain-man-20.hqx  --write-manifest

Two corpus fixtures hold forks that `unar` fails on and `macunpack` — built
with its own DiskDoubler support — fails on too. Both are SELF-EXTRACTING, so
each carries a third implementation in its resource fork, the bargain
`superdisk.py` and `nowcompress.py` already make. The fixture named on the
command line is the ENVELOPE, because the derived `.sea` in `fixtures/` is its
data fork alone and a self-extractor without its code is just an archive.

`--write-manifest` records the verdict where `ci.sh` will keep checking it,
which is the point: a fork the Mac wrote goes into the fixture's manifest with
`data_oracle` naming this harness, exactly as `make_manifests.py` records a
fork the second oracle rescued.

**Only DATA forks can go in**, and re-running this will not change that:
every resource fork the Mac wrote agrees with ours only under the
`vmac_check.py` mask (measured 2026-08-21; DECISIONS.md for why). Those forks
stay `unadjudicated` with the mask noted in their reason.

## The other half of DiskDoubler — `ddpro.py`

`diskdoubler.py` runs DiskDoubler 3.7, whose two software methods are 1 and
8. DiskDoubler **Pro** 4.1 writes the other container: `DDA2` archives, and
methods 9, 6 and 10 behind the AD1/AD2/DD1/DD2/DD3 items of its Settings
dialog. Two open questions need it, and neither can be answered by reading a
file (OPEN_ITEMS.md):

    tools/vmac/ddpro.py --setup     # fetch 4.1, unpack it
    tools/vmac/ddpro.py --install   # System 7 + its Finder-menu extension
    tools/vmac/ddpro.py --probe     # photograph the menus and dialogs

- **A `DDA2` stored entry with a resource fork. ANSWERED 2026-08-21: there
  is no such thing.** DiskDoubler Pro writes the headerless `0x1000` record
  only for a file whose data fork is stored AND which has no resource fork —
  4.1's "Create Archive…" on one incompressible forked file writes an
  ordinary header with the data fork STORED, and so does 4.1.1 on seven at
  once. `ndd.py --stored` measures all four cells; `--dates` settles which of
  `+54` and `+58` is the creation (FORMATS.md, DECISIONS.md).
- **What the 4 bytes at `+4` of a `SPLT` header mean. ANSWERED 2026-08-21:
  the Mac's `TickCount` when the file was split.** Three files split 72 s
  apart differ by 4,324 and 4,330 ticks, and two of the three were
  byte-identical with different names (FORMATS.md, DECISIONS.md).

    tools/vmac/ddpro.py --experiments   # one session, both questions

Like `diskdoubler.py` this is an extension with an application beside it, so
the work is done from the Finder's own menu; unlike it, the download is a
StuffIt archive rather than a disk image, and our own CLI unpacks it.

Four things each cost a run before the fourth one worked. Why they are easy
to misread is DECISIONS.md 2026-08-21; what to do about them is:

- **Never press Return at the desktop** — it opens the selected icon's name
  for editing, and the next keystroke types into it. `select()` sends Escape
  first.
- **Put the application on the work volume.** The Finder menu is a front end;
  without it, "Create Archive…" answers *The DiskDoubler application cannot
  be found.* and greys the whole menu out behind the dialog.
- **Spell the Mac name in the source.** The application is `DiskDoubler™`,
  and what a Mac Roman `™` becomes in a Linux directory depends on the
  transcoding.
- **Leave room for what DiskDoubler writes.** A split leaves the original in
  place, and the menu says "Split File (760K)" — a subject smaller than that
  comes out in one piece and answers nothing.

## The last two DiskDoublers — `ndd.py`

`diskdoubler.py` runs Salient's 3.7 and `ddpro.py` runs Fifth Generation's
DiskDoubler Pro 4.1. This one covers the other two ends of the product's
history: **DiskDoubler 4.0**, the release that first bundled AutoDoubler and
CopyDoubler as *SuperDoubler*, and **Norton DiskDoubler Pro 1.1**, Symantec's
last one — whose application is DiskDoubler **4.1.1**, not 1.1. Why that
matters and what it settled is DECISIONS.md 2026-08-21 (the Symantec
release).

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

`--specimens`, `--harvest` and `--grade` need no emulator and no X server.
The rest are one boot each, about ten minutes of host wall clock.

**`--specimens` is the one that pays.** Salient's 3.1.2 floppy (WinWorld, a
PC abandonware library nobody here had searched — BLOCKERS.md) holds 24
DiskDoubler containers written in 1991: one method 2 fork, which is the only
one this project has ever found and what method 2 is graded on, and 22 method
7 forks of up to eight chunks. Each carries its own checksum, so the disk
grades itself and the mode returns non-zero on any mismatch.

Four things here that the other two harnesses do not have:

- **The download is behind a one-shot token.** Macintosh Repository answers a
  plain `GET download.php?id=` with an interstitial that says the link has
  expired, which reads as "the file is gone" and is not: the token is minted
  by a 302 that only appears with the software page's own session cookie
  behind it, and the file is a POST of the hidden field on the page past that
  redirect. `fetch_norton()` does the three steps. The failure mode is a
  168-byte HTML body saved as `.img` that `file(1)` cheerfully calls a floppy,
  so the SHA-1 is checked against the published one.
- **Everything on that floppy is DiskDoubler-compressed** — types `DDF0`
  through `DDF3`, creator `DDAP`. `--harvest` decodes all of it with our own
  CLI and prints each container's methods, so the installer disk is ten more
  graded specimens, the same way 3.7's distribution disk turned out to carry
  the only two method 7 forks reachable here.
- **The boot image is built out of forks this engine decoded**, because
  nothing on the disk can be installed without decompressing it first. That
  is the point rather than a shortcut: a wrong byte does not produce a
  warning, it produces a System 7 that will not start.
- **Put the subjects in a folder.** `session(..., folder="Subjects")` leaves
  the application at the volume root, because Select All in the root window
  selects the application DiskDoubler is about to launch. The Return trap
  `ddpro.py` documents applies here too — `select()` sends Escape first, and
  the folder is opened with Cmd-O.

`--stored` grades itself: it reads the archive back with our own CLI and
compares every fork with the bytes that went in, resource forks with 16..127
masked, and returns non-zero on any mismatch.

## SuperDisk!'s compressor — `sdcompress.py`

`superdisk.py` grades this engine with SuperDisk!'s own expanders, which is
all the corpus's self-extracting archives offer. This one runs the half that
compresses: Alysis's 1991 ` SuperDisk!` control panel (`cdev`/`AlyS`), which
OPEN_ITEMS.md said did not survive (BLOCKERS.md).

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

`--sweep` is the controlled experiment: identical content, one subject per
setting, so the only thing differing between outputs is the setting. It found
that Speed=Fast writes method **6** where everything else writes 1 — and
method 6 was broken until it did.

Two more traps it cost a run each to learn, on top of the two above:

- **Close the panel with Cmd-W, not its close box.** A click at the measured
  close-box coordinate did not close the window, so the next click — "Make
  File" at a page-1 coordinate — landed on the settings page's **Off** button.
  No dialog opened, and the file name meant for it was typed into the Finder,
  which renamed a control panel to "Coff".
- **Reopening lands on the last page shown**, so `reopen_panel` presses "Last
  Page" twice before anything is clicked at a page-1 coordinate.

**`--boundary` is the one that found a decode defect** — on its second
attempt, 2026-08-28. It compresses four subjects at Speed=Fast, sized so the
coded flag bitmap ends exactly on a 32-bit refill, which is where this engine
read the literals four bytes early.

The sizing is the whole of it. The first four subjects (2026-08-25) used
`ceil(ulen/8) % 4 == 0` — a rule about the flat 8-bit code
`tools/sdmodule/run_sdmodule.py` writes, and about nothing the panel writes —
missed by 2 to 5 bits, and the miss was written up as "a real block cannot
reach it". `tools/sdhuff.py` measures what the panel actually writes: it codes
each flag BYTE in one bit, so the bitmap is `nflags + 5` bits for this subject
and `ceil(ulen/8) + 5 ≡ 0 (mod 32)` is the aim. 1240 and 2008 bytes land on
160 and 256 bits; 1248 and 2016 are one bit past, as controls. All four came
back method 6; the two on the boundary were wrong from byte 0 and are
byte-exact since the fix (DECISIONS.md 2026-08-28). It prints the measured bit
count and the verdict per subject, and the specimens it leaves are graded by
`run_sdmodule.py`.

`--specimens` is the one that mattered: five subjects chosen to DISAGREE with
each other, because the first specimen alone made the header layout look
obvious and would have got it wrong — its data size, its total and its name
length were indistinguishable. One has a resource fork, one is stamped 1990
and 1995, one has a 20-character name (the only one that reveals the body is
padded to an even offset), one is over 32 KB. `--verify` needs no emulator.

Three things that cost a run each:

- **The extension is the RESULT, not the trigger.** Renaming a file to
  `Alpha.x` under a loaded SuperDisk! changes nothing — measured, the bytes
  come back identical. `.x` is what the compressor names its output; the work
  is done from the control panel's "Make File" button.
- **Rebuild the boot image every run.** The panel saves its settings *and its
  current page* into the System Folder, and Mini vMac writes back, so a
  second run opens where the first left off and a coordinate measured on page
  1 lands on page 2. One run clicked "Off" that way — turning compression off
  — and photographed a settings page believing it was a file dialog.
  `session()` re-copies `Sys7.img` unconditionally.
- **The Apple menu is not worth fighting.** Two attempts at holding it open
  produced frames with the title inverted and no menu. Navigating the boot
  volume to `System Folder:Control Panels` is slower, reliable, and proves
  the panel is installed.

## Alysis Resource Compressor 2.0 — `rescomp.py`

The hunt for something that WRITES SuperDisk!'s methods 10, 13 and 20. The
vendor's technology page names SuperDisk! 2.x as the release with the newer
codecs and no archive has it; this 1993 application does carry the whole
library — `Cmpr` 3, 5, 19, 21, 22 (SlowFastB **and** Tennessee end to end),
23 and 26, the same bodies as Disk Expander 1.2's.

    tools/vmac/rescomp.py --modules    list them; no emulator, no X
    tools/vmac/rescomp.py --probe      boot it, photograph its menus
    tools/vmac/rescomp.py --compress   compress a subject and read it back

**It compresses, and it is still not the writer.** 8,001 bytes of `STR`
became 472 — and what it wrote is Apple's compressed-resource container
(`A89F6572`, version 8, `defProcID` **0**), not a `Cmpr` stream: none of the
seven modules reproduces the subject from that payload. Its help has no codec
choice in it. The modules are there for its Decompress button.

Two things it cost, both worth copying:

- **Aim the Special menu at a measured coordinate.** The first run borrowed
  118 from another harness and hit **Restart**. The subject came back with its
  new resource data written and its old resource MAP still in place, which
  parses as garbage — a torn read that looks exactly like a format finding
  until you notice the fork is still its original length. Shut Down is at 139.
- **The read-back is the result, not the screen.** The on-screen `Cmprssd`
  column said 472 in both runs; only the flushed volume showed whether the
  file had actually been rewritten.

## SpaceSaver — `spacesaver.py`, and what it will and will not do

3.5.1 runs, its container has been read out of it (`--layout`, below), and
it has still never compressed anything here. The application is
reachable — the Deluxe 5.0.1 CD carries a standalone installer — but
**SpaceSaver 5.0 needs System 7.5.3 and 8 MB**, and forced past its own two
"Install anyway?" alerts on 7.0.1 it bombs with *unimplemented trap*.

    tools/vmac/spacesaver.py --setup     fetch the CD (156 MB), lift the installer
    tools/vmac/spacesaver.py --probe     boot with it and photograph
    tools/vmac/spacesaver.py --install   walk the installer as far as it goes

    tools/vmac/spacesaver.py --setup351   fetch the 3.5.1 two-floppy set
    tools/vmac/spacesaver.py --probe351   boot with both floppies mounted
    tools/vmac/spacesaver.py --install351 run the 3.5.1 installer

**3.5.1 stops at a registration number** it will not accept an empty value
for, and no serial was sought — the maintainer waived the licence's
reverse-engineering clause, which is not the same permission. **5.0 needs
System 7.5.3**, which is the open route. DECISIONS.md 2026-08-22
(SpaceSaver, and SpaceSaver later) has both.

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

Every mode from `--specimen` on ends with Special > Shut Down (the general
rule at the top of this file) — **at the right coordinate only since
2026-09-01**: before that they picked Restart, one item above it, which
flushes as well and so hid the mistake. `ssenrolled.hfv`, made before the
rule was followed at all, does not boot.

**`--layout` needs no emulator at all.** It lifts `~StuffIt SpaceSaver™`
(`cdev/SMKR`) and `StuffIt Engine™` off `ssinstalled.hfv` with `hcopy`,
parses their resource maps, and prints the compression header, the fork
record, and the compressor table read from each `CMod` module's own bytes —
plus the engine's MacsBug symbols, which name every routine the reading
came from. It ends with **nine witnesses**: byte patterns that must be
present in `SSEn 1` and `ACMP 1`, printed with the offset each was found
at, so a different build of SpaceSaver makes it say MISSING and exit 1
rather than silently confirm today's reading. The layout itself is in
FORMATS.md, *StuffIt SpaceSaver's container*.

**`--pkg` is in this file because the translator is on this image.** The same
installation carries fourteen of Aladdin's translators, and one of them reads
AppleLink packages — the format this project could not name until 2026-08-23.
It prints that translator's `Name`, its vocabulary and its recogniser, with
four witnesses; FORMATS.md, *AppleLink packages*, is what came of it.

**The three `--pkg*` boot modes offer that translator a package written
here, and all three come back empty.** Each writes five one-line packages
into `StuffIt Deluxe™ Folder` — `Decode <item> to <destination>`, the grammar
`--pkg` transcribed, one per Finder type so the type is a variable — plus
`Payload.hqx`, the BinHex file they name. `--pkgexpand` drives *Translate ▸
PKG Expand…* and also runs *CPT Expand…* over a real `.cpt` as its control;
`--pkgexpander` drives StuffIt Expander's `⌘E`; `--pkgconvert` drives
DropConvert's `⌘C`, whose dialog wants *type, Return to Add, then click
Convert at (452, 289)*. Every run ends in Shut Down and reads the volume back.
The result and what it means: DECISIONS.md 2026-09-01, *the package that
cannot be handed over*.

**What they cannot see.** Whether the packages are the problem. Each run
proves only that Aladdin's software did nothing with the file, and the engine
never reports anything either way, so *"this build will not take that input"*
and *"this text is not a package"* look identical from here. **Read the
control first**: `Payload.hqx` must have become `Widget` (Expander) or
`Widget.sit` (DropConvert), and the report line says which — a run whose
control did not fire says nothing about packages at all. Its resource fork
comes back the right LENGTH and different bytes, because the Finder opens an
extracted file to draw its icon and the Resource Manager rewrites the map's
live fields (BLOCKERS.md 2026-08-23); the data fork is the comparison.

What it cannot see: whether any of this describes a real compressed file.
Nothing here has produced one, so every field is read from the writer, not
from output.

**The extension installs, and finding that out needed no screenshot**
(2026-08-25). A boot that never opens the control panel leaves
`System Folder:Preferences:SpaceSaver Preferences` (`Pref/SMKR`, 10,496 B) on
an image that had none — patched and unpatched alike, so `--patch-init`'s one
silent gate was never closing. That file is the signature to check after any
run here; `hcopy` it and read its `Opts 1` resource, which carries the `small`
name rule. What it does NOT explain is why the rule never fires.

**Nothing has made SpaceSaver compress anything**, and the modes above are
the attempts. Four were added on 2026-08-25 and between them they moved the
question a long way (OPEN_ITEMS.md): `--magicname` (a matching NAME and a
menu command in one run), `--info` (ask *SpaceSaver Info...* about a file —
it answers, so the engine is reachable), `--ssmenu` (press every icon slot
across the bar and photograph what opens) and `--enrollidle` (enrol the
volume, close the panel with its close box, pick *Idle Now*, stay still,
shut down).

**SpaceSaver's own menu is at x=425, not 283.** 283 is where Magic Menu's
icon is, and `SS_MENU_X` said 283 — which is why `--idlenow` deleted Magic
Menu, pressed the hole it left, and reported no icon menu at all. When a
mouse-driven mode here does nothing, suspect the coordinate before the Mac:
`--calib` parks the pointer at known Mac positions and photographs each, and
the newer modes print `xdotool getmouselocation` beside what they asked for.

The modes below are the older attempts: the panel's `small` name rule (`--specimen`), the same with
the disk enrolled and the machine left idle (`--idlespec`), Magic Menu's
*SpaceSaver Compress* (`--magic`, `--enrollmagic`), and `DropCompress™`
both launched and dropped on (`--drop`, `--dragdrop`). One thing on that
settings page DOES fire: `--suffix` renames a subject to end in `.SIT` and
gets a StuffIt archive back — Magic Menu's doing, not SpaceSaver's.

**`--idlenow` is the one that changed the question.** It deletes
`~Magic Menu™` before booting so that SpaceSaver's own menu (`STR# 1024`:
*Turn Idle-Time On*, **Idle Now**, *Open Control Panel*) has the menu bar
to itself — and the menu bar came up with no icon menu at all. Nothing
here has ever needed SpaceSaver's EXTENSION as opposed to its control
panel, so the next thing to establish is whether `INIT 0` installs
(DECISIONS.md 2026-08-22, what will not compress).

**The installed image is now a flushed one.** `--install351` ends with
Shut Down as of 2026-08-22, and `ssinstalled.hfv` was remade with it; the
one it replaces is kept beside it as `ssinstalled-torn.hfv`. It changed
nothing about the compressor, and it removes a variable.

**`--parade` cannot answer that, and says so.** It photographs the
machine from the moment the emulator starts, 30 frames at 0.15 s, and
every one of them is the settled desktop: Mini vMac runs unthrottled, so
a Mac Plus is at the Finder before an X client can grab the first frame.
The startup icon parade is not observable through this harness.

**Lift the installed image out of `/tmp`.** `run.py` boots from a COPY, so an
installer's entire output lands in the session's temp dir and the original
boot image still looks untouched — which reads as "the installer wrote
nothing".

**Installing it, panel by panel** (measured 2026-08-25, `--freshinstall`):
Standard Install — whose text says it installs "the complete StuffIt
Deluxe™ and StuffIt SpaceSaver™ packages" — then a destination chooser,
then *"Your Macintosh needs to be restarted after installation is
complete. Do you wish to continue?"*, then the copy, then *"Installation
was successful ... needs to be restarted"* with **Restart** as its only
button.

**Do not press Restart.** Mini vMac flushes a volume on eject or
shutdown, not on a guest restart, so pressing it throws the whole
install away: the image comes back stock and unbootable, which reads as
"the installer did nothing". Quit with Cmd-Q and shut down through the
Finder instead.

Three input rules, each of which cost a run here: **a button is clicked
ONCE** (only icons are double-clicked); **walk the pointer to it** —
a warp followed immediately by a click lands short, and 66 px short of
"Yes" is "No"; and **these alerts default to No**, so Return does not
mean yes. `--freshinstall` photographs the pointer sitting on each
button before the click, which is the only way a miss is visible.

**3.5.1 and 4.0 both reject every code Macintosh Garden publishes** — those
are for 3.0.7 and 5.x, and 5.x is what cannot run here (7.5.3 and 8000K,
against a 4 MB Plus). The open route is a Mac II-class Mini vMac variant
plus a 7.5.3 image.

**Every panel in both Aladdin installers swallows its first input.** A click
on a button and a Return both leave the panel on screen; the second acts.
Three runs went into reading that as a wrong coordinate — and the
coordinates were measured off the frames and right. The tell: the frame
after the input is IDENTICAL to the one before, where a genuine miss
usually shows something else selected.

Two more, both of which produce frames that lie: **3.5.1's floppy opens its
own window on boot and 4.0's does not**, so the same installer click lands on
bare desktop and every frame after shows an empty Finder — which reads as
"the installer quit". And **Cmd-A does not select a System 7 dialog field's
text**: a run meant to try four codes typed all four in end to end and tested
none, while reporting four attempts. Backspace the field empty.

Three things that cost a run each, all about input reaching the installer:

- **Its first input is swallowed.** A click on the licence panel's Agree and
  a Return both leave it on screen; the panel only moves on the second. The
  harness sends a click and then a Return.
- **There are TWO "Install anyway?" alerts**, not one — 7.5.3 and 8000K —
  and both default to **No**, so a blind Return quits the installer. The
  frame after that looks exactly like a finished install: the Finder, with
  the volume open.
- **Wait longer than feels necessary.** A click sent before its dialog
  appears lands on whatever is behind, and the next frame shows the dialog
  still up — which reads as "the click missed the button" and is not.

## Grading a method by writing it — `ddencode.py`

Every other harness here decodes something somebody else made. This one
does the opposite, because DiskDoubler methods 3, 4 and 5 have no specimen
and never will unless a 1990 file turns up: it **encodes** a fork, wraps it
in a `0xABCD0054` container with a correct header CRC, and hands it to
Salient's own 1991 application, which comes off the 3.1.2 disk uncompressed
and runs.

    tools/vmac/ddencode.py --build            write them; round-trip here
    tools/vmac/ddencode.py --probe            the 1991 INIT, in the Finder
    tools/vmac/ddencode.py --probe-app        the application's own menus
    tools/vmac/ddencode.py --expand           let 1991 read them
    tools/vmac/ddencode.py --expand --era 411 let 4.1.1 read them

`--build` needs no emulator and must pass before a boot is worth it: it is
only encoder-vs-decoder, both ours, so it catches transcription slips and
proves nothing about the format. `--expand` is the part that grades.

Four things this one has that the others do not:

- **The 1991 INIT adds no menu to the Finder's menu bar.** That arrived with
  the separate "Finder Menu" extension of 3.7 and 4.x. It does register the
  `DDF2`/`DDAP` icons, which is how a `--probe` frame shows it loaded at
  all, and expanding is a double-click.
- **The application personalizes on first launch**, like 3.7's. `--expand`
  answers it once and quits before touching any file, so the dialog does not
  interrupt the run.
- **Give the subjects a type nothing owns.** Expanding a `TEXT` file
  launches TeachText, and the next `Cmd-O` then opens **TeachText's** Open
  dialog — which is how the first run of `--expand` expanded one file and
  typed the other three names into a standard file dialog, reporting three
  false "the expander did not take it". Click the Finder window before each
  file, too.
- **Use 1991, not 4.1.1, for methods 3 and 4.** 4.1.1 has dropped them and
  answers *Unknown compression method*. `--era 411` is worth running anyway:
  it is a second opinion on method 5.

## A Macintosh writes a MIME message — `macmime.py`

`src/fmt_mime.c` is transcribed from mpack 1.6 and had only ever been graded
against messages made on Linux. mpack's Macintosh PORT is in the same
reference tree, so the specimen is made here rather than waited for
(DECISIONS.md 2026-08-29, *a Macintosh wrote a MIME message*).

    tools/vmac/macmime.py --make     boot System 6.0.8 and write it
    tools/vmac/macmime.py --check    grade what came off the disk
    tools/vmac/macmime.py            both

`--make` boots straight into the encoder — no Finder, no mouse — and reads
`Out.mime` back off the image. `--check` needs no emulator and can be re-run
over the kept specimen at will.

Four things this one has that the others do not:

- **Retro68's newlib file I/O cannot be used on System 6.0.8.** A bare
  `open()` never returns there, so every `FILE *` mpack touches is built with
  `funopen()` over hand-filled HFS param blocks. If a future harness wants
  stdio on a Mac, this is the reason it will not get it.
- **The subject lives in the System Folder, not at the root.** `mkboot.py`
  puts a shell application in the blessed folder and that is the default
  directory it starts in; a subject at the root gets −43.
- **`hcopy -m` does not carry the Finder flags onto the volume.** They are set
  on the Mac with `PBHSetFInfoSync` and the catalogue is re-read afterwards,
  so what the applefile carries is what the volume holds.
- **The application draws its progress on screen**, one line per step, and the
  frames are kept in `$UNC_VMAC_HOME/specimens/macmime/shots/`. Every failure
  above was diagnosed from a frame rather than from a timeout.

What it cannot see: one message from one encoder, and it cannot settle line
endings — the specimen is LF-terminated because of the C library the port was
compiled against, not because of anything a Macintosh decided. FORMATS.md,
*base64 and MIME*, says so where the result is.

## Grading SuperDisk! with SuperDisk! — `superdisk.py`

Nothing outside the two corpus archives reads the format, so the only oracle
it has is the archives themselves: both are self-extracting applications.
`superdisk.py` is the same bargain `nowcompress.py --adjudicate` makes.

    tools/vmac/superdisk.py --list                    what the corpus holds
    tools/vmac/superdisk.py --adjudicate FIXTURE.hqx  run it, compare forks

The archive is unwrapped from its envelope with our own CLI, rebuilt as
MacBinary, put alone on a 25 MB volume and launched under System 7; its "Save
the expanded file as:" box is accepted with Return, and every fork it wrote is
read back off the image with `hfsutils` and compared with `macextract x`.
Resource forks are compared with bytes 16..127 masked, the `vmac_check.py`
convention. The verdict is 5 forks across the 2 archives, all identical
(2026-08-20; FORMATS.md ✧✧). Screenshots land in
`$UNC_VMAC_HOME/specimens/superdisk/`. Nothing here runs in `ci.sh` —
`tools/run_superdisk.py` replays the verdict offline.

Two things to know before re-running it:

- **The application is opened with Select All, not with a coordinate.** The
  volume holds exactly one item, so ⌘A then ⌘O needs no measurement — and a
  measurement is what broke here: a double-click on a point measured from the
  first archive's window merely SELECTED the second one, whose icon the Finder
  had drawn a few pixels higher. The run then "succeeded" having launched
  nothing, which is what a screenshot of the right window at the wrong moment
  always looks like.
- **The run ends with Put Away, and must**, for the reason `arcmac.py`
  documents above: Mini vMac flushes the guest's writes when the volume is
  ejected, so a run killed with it still mounted reads back an empty disk.

### Handing that extractor a stream written HERE — `--nest`, `--stored`, `--rootfile`

Same application, different data fork. `SD! Utilities.x` is an APPL whose data
fork IS the archive, so replacing that fork and leaving the resource fork alone
gives the format's own `CODE 2` a record stream this project built — the only
second reader this container has anywhere (`tools/synth_sd.py` writes them).

    tools/vmac/superdisk.py --nest              a 10-folder path, past the cap
    tools/vmac/superdisk.py --stored            the one block shape no fixture has
    tools/vmac/superdisk.py --rootfile          a stream that opens with a file
    tools/vmac/superdisk.py --rootfile --invented   ...with a guessed record

Measured 2026-09-01, one boot each. `--nest` builds ten folders of 31
characters, paths from 43 to 331 bytes: the Macintosh made every one of the
eleven files, all byte-identical, and for the three past 255 bytes **the uncut
path `unc_path_leaf` reports is the path the Macintosh built** — which is the
whole point, since that machine creates each component through the File
Manager and never assembles a path. `--stored` reads back byte-exact, so the
stored-block encoding is confirmed by the extractor it was disassembled out
of. `tools/run_names.py` replays the `--nest` verdict offline; nothing here
runs in `ci.sh`.

What these CANNOT see: whether SuperDisk! itself would ever WRITE such a
stream. They establish what its expander reads, which is what an extractor
needs and is not the same claim.

**One run bombed and has not been reduced — treat it as a hypothesis.** The
first `--nest` attempt died with *"unimplemented trap"* after the Save box,
having written nothing (Mini vMac flushes on eject, so a bombed run reads back
an empty volume). That stream differed from the ones that work in four ways,
and each has since been run on its own and is fine: the depth (`--nest`), the
stored blocks (`--stored`), a file as the FIRST record (`--rootfile`), and a
file record whose fields were guessed rather than copied (`--invented`). What
is left untested is the one combination — a root file FOLLOWED by a folder —
and that is one boot for whoever wants it. The archive is
`synth_sd.nest()` with `control.txt` moved to the front.

### Replaying a SuperDisk! archive through OUR Mac application

`run.py` grades against an oracle manifest and this format has none, so the
two archives are read off the grid directly, exactly as the ArcMac specimens
are. They are payloads rather than fixtures, so unwrap them first:

    macextract x -nr -o /tmp/sd fixtures/alysis-disk-expander-12.hqx
    tools/vmac/run.py --pngdir /tmp/p "/tmp/sd/Disk Expander .X"
    tools/decode_grid.py "/tmp/p/Disk Expander .X.png"

`run.py` will report FAIL — "no oracle manifest" — and that is the harness
saying it cannot grade, not a result. The grid is the result; compare it with
the same engine's Linux aggregate:

    python3 -c "import sys; sys.path.insert(0,'tools'); \
      from vmac_check import aggregate_dir; print(aggregate_dir('DIR'))"

over a `macextract x -nr --forks hidden` of the same payload. Both archives
matched at 4 MB and at 1 MB on 2026-08-20; the numbers are in FORMATS.md,
"SuperDisk! on the Mac".

## The yardstick — `expander.py`

**Every other Mac Plus figure this project publishes is absolute, and absolute
is the wrong shape.** What a user weighs is whether this is faster or slower
than the free tool they would otherwise run on that machine. This boots both
applications on the same emulated Mac Plus, at authentic 7 MHz, over the same
archive on the same volume.

    tools/vmac/expander.py --fetch          # download 4.0.2 and unpack the app
    tools/vmac/expander.py --sizes          # both SIZE resources; no emulator
    tools/vmac/expander.py --quiet 60 --json y.json fixtures/derived-Export.sit

Results and the ratio: FORMATS.md, *Timed against StuffIt Expander 4.0.2*.
**One emulator at a time, and nothing else on the box** — the 1x rule above.

`--fetch` takes Macintosh Garden's `stuffit_expander_4.0.2.sea_.bin`, checks
its SHA-256, walks MacBinary → self-extracting StuffIt → 400K disk image with
our own CLI, and copies the application off that image. Two things about that:

- **Garden signs its download URLs and answers a bare GET with HTTP 418.** The
  page is fetched first and its cookie jar reused for the file. `arcmac.py`
  does the same two-step; it does not need the jar on the page request and
  this does.
- **hfsutils refuses a volume "smaller than 800K"**, and the distribution
  image is 400K. Padding a temporary copy to 800K mounts it, and reading only
  ever follows the MDB's own extents, so the padding is never looked at. That
  refusal was the whole of "an HFS reader this machine does not have"
  (BLOCKERS.md, withdrawn claims).

**The instrument.** Both applications are driven to a Standard File dialog
with the archive selected, then timed from the keystroke or click that starts
the work to the last screenshot that differed from the one before it. Expander
cannot be asked what it took, so the only clock that is fair to both is one
outside them; ours would flatter us by exactly the interference the other one
pays. Each figure is therefore a lower bound with a one-poll error, both sides
pay the same quantisation and the same ~50 ms per poll of stolen CPU, and
**the ratio is the durable part of the result**. Do not quote the seconds as
Mac Plus times — `run.py --emu mv-4M-1x` is what those come from.

**Four things cost a run each, and not one of them failed loudly:**

- **The first row is not the archive.** Our side clicked the first row of
  Standard File and pressed Return, on the assumption that the archive is
  the only thing on the volume worth opening. `mkboot.py` stopped deleting
  the Finder's **`Desktop` file** on 2026-08-30, one day after the yardstick
  rows were published, because the password phase needs it kept — and that
  file is invisible to `hdir` and VISIBLE in our dialog, which filters
  nothing. Every fixture whose name sorts after `Desktop` therefore had
  `Desktop` extracted instead: `macburger-helper.hqx` and `unshar-111.hqx`
  both reported *"This file could not be extracted"* three seconds in,
  photographed, on builds either side of 2026-09-20.
  `derived-FirstClass_Demo.cpt` and `derived-Export.sit` sort BEFORE it
  ("der" < "Des"), which is why the published rows were taken cleanly and
  nobody saw this for three weeks. The file is named by type-ahead now
  (`select_by_name`), and `ours-2-selected.png` photographs the highlighted
  row before Return is pressed.

- **Expander's dialog is not the stock one.** Aladdin's DLOG puts the file
  list ~48 px higher, so the row `interactive.py` measured lands below the last
  item: the click selected `System Folder`, Return opened it, and the run
  reported three seconds and expanded nothing. The file list is not clicked at
  all now — the first row is preselected — and the Expand button is pressed at
  a coordinate measured off this harness's own frame. Return would probably do
  as well; it was tried, looked dead, and the volume it left empty is explained
  by the flush below rather than by the key, so it is untested and not
  disproved.
- **Nothing had assigned X keyboard focus.** `settle()` only screenshots, and
  the focus call lives in `origin()`, so Command-E went to the root window —
  the same trap the three lessons above describe, in its "the Mac ignores one
  particular key" disguise.
- **Expander's output is not on the image until it quits.** Our sink calls
  `FlushVol` after closing each fork, so its files are on the host image the
  moment the alert goes up; Expander leaves its writes in the File Manager's
  cache, and SIGKILLing the emulator throws them away. A 278 KB archive
  expanded for 56 s, with the progress window photographed mid-run, and the
  image afterwards held nothing at all. The harness sends Command-Q after the
  measurement has ended, so it costs the comparison nothing.

  **Measured rather than inferred since 2026-08-30**, by mounting a copy of
  the `boot.hfv` the emulator is writing — `live_names()`, at three points:
  when the screen stops changing, after the quit key, and after the kill. Our
  files are there at the first; Expander's appear at the second, **within a
  second of the keystroke** and with no repaint at all. `--json` carries
  `on_disk_before_quit`, `on_disk_after_quit`, `flush_seconds` and
  `quit_redrew`, and FORMATS.md (*Timed on the same Mac Plus*) has what it
  means for the ratio.

**What the SCREEN cannot see, and why the image probe exists.** Command-Q
commits Expander's writes and **repaints nothing**: the frames either side of
it are byte-identical. A screen-timed quit therefore reports one poll interval
whether the application quit, flushed 415 KB, or ignored the key entirely —
which is what the harness did report for one afternoon, until the frames were
hashed and the number turned out to be the floor rather than a measurement.
`quit` and `to_disk` in the JSON are screen figures and inherit that; the
`on_disk_*` lists are the ones that observed anything.

**What it cannot see.** Whether Expander's output is CORRECT: a run is graded
on having produced files at all, and nothing here compares its bytes with
ours. And nothing outside the four families 4.0.2 opens by itself — zip, gzip,
tar, uuencode and the rest need DropStuff with Expander Enhancer, System 7 and
not free, so timing those would be measuring a configuration a System 6 user
does not have.

## The downloads, and why none of them are committed

`setup.sh` fetches by URL and verifies by SHA-256, exactly as `fixtures/` does,
because two of the three are Apple's copyrighted property:

| file | source | why |
|---|---|---|
| `minivmac.src.tgz` 36.04 | gryphel.com | GPL-2 emulator source, built locally |
| `vMac.ROM` | Internet Archive `mac_rom_archive_-_as_of_8-19-2011`, member `4D1F8172 - MacPlus v3.ROM` | Macintosh Plus ROM — **Apple copyright** |
| `System6.hfv` | Internet Archive `system-6_202607` | System 6.0.8 — **Apple copyright** |
| `Sys7.img` | Internet Archive `AppleMacintoshSystem701` | System 7.0.1 — **Apple copyright** |

If a hash ever fails to match, the upstream file changed: check it by hand
rather than editing the expected hash.

## Requirements

`Xvfb` (depth 24 — Mini vMac's X11 glue dies with `BadMatch` on an 8-bit
visual), ImageMagick (`import`, `convert`), `xdotool`, `hfsutils`
(`hformat`/`hmount`/`hcopy`, shipped with Retro68), and a Retro68 toolchain
in `$RETRO68` or `/opt/Retro68-build/toolchain`.

## Mac OS 9

`os9.py` boots Mac OS 9.2 under `qemu-system-ppc -M mac99,via=pmu`, headless,
screenshotting through QEMU's own monitor rather than an X server, launches
the application and checks what it wrote:

    os9.py --setup                                       # fetch the 2 GB image
    os9.py fixtures/derived-DDT.sit -o shots/ --launch    # one fixture
    os9.py --list os9sample.txt -o shots/ --launch        # the format sample
    os9.py fixtures/foo.sit -o shots/ --hfsplus           # extract onto HFS+

An idle host reaches the Finder desktop in ~110 s. Every fixture boots its own
pristine copy of the master image — Mac OS 9 writes to its boot volume as it
goes — and `--keep-boot` is off by default because each copy is 2 GB. The
master's published SHA-1 is verified before every run, and `--setup --force`
re-fetches: the harness once booted the master in place and never hashed it,
so the drift was invisible until the local copy stopped matching archive.org
and the volume read back hardware-locked (BLOCKERS.md, *Corrected figures*).

**Do not point `-o` at a tmpfs.** `/tmp` is one on this machine, 16 GB of an
8 GB host's RAM, and the boot copy lands in the output directory — so a sweep
there spends 2 GB of RAM per fixture beside a running emulator. Measured
2026-09-25: a 22-fixture sweep aborted at the thirteenth with *"never reached
the Finder desktop"*, which is what a host in swap looks like from inside the
harness — the guest missed its settle timeout and nothing about the guest was
wrong. `boot_copy()` now warns when the destination is `tmpfs` or `ramfs`.
The same sweep with `-o` on disk is the one to trust.

**`os9.py` drives the Finder from the keyboard, and it does not have to.**
Typing selects an icon by name and Cmd-Down opens it — no coordinates, no
double-click threshold — which is why every fixture run goes that way and
still should: it is faster and it cannot mis-aim.

**What it CAN do is aim at a name that no longer exists.** It typed `u`, `n`,
`c` from before the project was renamed to MacExtract (2026-08-26), so the
selection landed on nothing and Cmd-Down opened whatever the Finder had
selected instead — the System Folder, photographed in `13-sfgetfile.png` of a
run that reported "application launched" and extracted nothing. The rename had
changed the volume and the application in `run_one` and left the keystrokes,
and no OS 9 run happened between the two to notice. It types `m`, `a`, `c`
now — three letters, because `Mail` is on that desktop too. **A harness that
selects by name has a dependency on that name that nothing compiles.**

But the reason it was written that way is withdrawn. `os9probe.py` measured
five mouse primitives at 0.0000 each on 2026-08-02 and concluded the pointer
was unusable; all five fired with the cursor pinned in a corner, because the
harness selects an absolute `usb-tablet` this guest has no driver for, and
because one large delta to a relative mouse saturates at ±63 px per ADB
packet. **`os9mouse.py` positions the cursor to within 3 px and clicks**
(BLOCKERS.md, *Withdrawn claims*), which is what made an installer and an
encrypted specimen possible. See *Mac OS 9 with the pointer*, below.

**`--autotest` scored three healthy fixtures as failures until 2026-09-25,
and both causes are fixed.** That route writes every input to the volume as
`ARCHIVE_ON_VOLUME` — `archive.sit` — and handed the REFERENCE the fixture's
own path, so gzip and `.Z`, which name their single entry after the archive,
came back as `archive` against Linux's `synth-exo-Z`: `ret=0`, matching CRCs
and byte counts, a name mismatch and nothing else. `verify_output()` had
copied the fixture to `as-the-mac-saw-it/archive.sit` for that exact reason
since 2026-08-08; the `--autotest` and `--hfsplus` verifiers were written
later and did not inherit it. Both do now. `synth-os9-rar.rar` failed for the
other reason: `ret=-6` with nothing written is the CORRECT refusal for a
detect-only format, and the route demanded `UNC_OK`. It now passes when both
sides refuse — the reference exiting non-zero with no files, the Mac
reporting a non-zero `ret` with no files — and prints the reference's own
message, while staying strict everywhere else, so a Macintosh that writes
nothing while the engine extracts still fails.

**So this route scores `os9sample.txt` 22/22 on a healthy build**, as
`--launch` does (FORMATS.md, *Mac OS 9 tier*); it read 19/22 before the fix,
which is in BLOCKERS.md as a harness artefact rather than a result. Anything
needing `-D` is stuck with `--autotest`, since that is the only route the
switch reaches.

**`--hfsplus` writes to a volume the host cannot read.** The boot volume is
HFS+ inside an HFS wrapper — wrapper MDB signature `0x4244 'BD'`,
`drEmbedSigWord` `0x482B 'H+'`, embedded volume header at byte 966656 of the
partition — and hfsutils mounts the WRAPPER, whose root holds exactly one
file, Apple's `Where_have_all_my_files_gone?` placeholder. Nothing here can
write HFS+ (no hfsprogs, no kernel module), which is why the application
cannot be dropped into `Startup Items` offline and the Finder has to be
automated. It also gives a free, unambiguous test: output written to that
volume is NOT visible in the wrapper, which is how the HFS+ runs prove where
their output landed rather than trusting a signature word the classic File
Manager reports as `'BD'` for compatibility anyway. The boot volume is
HFS+; renaming it to `Out` in the Finder is enough to point the *autotest*
build at it, since that build finds its volumes by name. The result comes back
through `at_report_file()` — a small file on the plain-HFS input volume
carrying the same values `at_report()` would paint, plus every output name,
because the framebuffer grid is invisible on a 32-bit screen. That the output
really landed on HFS+ is checked by mounting the volume's HFS *wrapper*: if
the files were on plain HFS they would be visible there, and they are not.

**`--autotest` is the third combination, and it exists to separate two
things `--launch` and `--hfsplus` change together.** `--launch` runs the
INTERACTIVE build onto a plain-HFS transfer volume; `--hfsplus` runs the
AUTOTEST build onto the HFS+ boot volume. When one passes and the other bombs,
the pair convicts neither the build nor the volume. `--autotest` runs the
autotest build with a plain-HFS output volume — a third APM disk named `Out`,
so no Finder rename is needed — which leaves the BUILD as the only difference
from `--launch`. It is also the only route here that reads both channels at
once: the report off `In`, and then every fork off `Out` byte for byte, which
`--hfsplus` cannot do because no host tool opens HFS+. `-D UNC_AT_SAMEVOL`
points the sink at the archive's own volume, the way the interactive
application writes beside the archive; `Out` still has to be mounted, because
`FindVolWait` looks it up before the switch redirects the sink, and the run
checks it came back empty.

    os9.py fixtures/derived-DandStoQIF2.sea --autotest -o <dir>
    os9.py fixtures/derived-DandStoQIF2.sea --autotest -D UNC_AT_SAMEVOL -o <dir>

**The reference is `macextract x`, unwrap loop ON.** This harness launches
the INTERACTIVE build, which takes envelopes off in `ExtractOne`; `-nr` is
right for the AUTOTEST build, which `--hfsplus` and the Mini vMac tiers use.
os9.py ran `-nr` until 2026-08-27 because it once launched the autotest build
too, and the tier was not re-run in between: `export-hc.hqx` came back as
"MISSING Export.sit, UNEXPECTED Export" from a Mac that had correctly opened
the BinHex, then the StuffIt inside it, and written the HyperCard stack byte
for byte. **When a harness changes what it drives, its oracle is part of what
changed.**

**Every screenshot in this tier was one step behind its label until
2026-08-28.** The sequence sent three keystrokes after the application was up:
one Return for the archive, one for what the code called "the alert", and a
Cmd-Q to quit. The second Return is in fact what accepts the DESTINATION
dialog, so `14-result.png` photographed SFPutFile under the name of the
result, the step that printed "extraction reported" had timed that dialog
opening, and Cmd-Q was typed into a modal dialog that never sees it — the
application was still running when the emulator was killed. The extraction
itself was never in question; it is read off the volume, which is why 20/20
stood. **A harness that stops before the end still reports every step it did
take.**

It now runs to the end and says what it waited for at each point:

| shot | what it is | how it is waited for |
|---|---|---|
| `13-sfgetfile` | SFGetFile, `archive.sit` selected | one rectangle changes |
| `14-destination` | SFPutFile, "Extract into this folder:" | one rectangle changes |
| `15-progress` | the progress dialog (`--cancel` only) | one rectangle changes, polled every second |
| `16-result` | "Extraction complete." or "Extraction cancelled." | the screen goes STILL |
| `17-back` | SFGetFile repainted, with the output now listed | one rectangle changes |
| `18-finder` | the Finder, application gone | one rectangle changes |
| `19-names` | a crop of `18-finder` on the volume window | — |

The result is the only one that cannot be waited for with `wait_change`: the
progress dialog repaints ten times a second, so the first change after the
destination dialog is that dialog appearing and never the alert behind it.
`still()` waits for the screen to stop instead, and prints how long it took —
`synth-packit-2.pit` finishes within 13 s of the Return that starts it, on a
machine where the whole boot takes ~130 s. **Cmd-. is what quits the
application**, not Cmd-Q: it is Standard File's Cancel, and the SFGetFile loop
in `ExtractOne`'s caller ends on `!reply.good`. It is sent through `ask()`
rather than `key()` so a keycode name QEMU does not know is reported instead
of looking like a keystroke the guest ignored.

**`--cancel` interrupts the extraction instead of waiting it out**, which is
the one thing the Mini vMac tiers have driven since M10 and this one never
had:

    os9.py fixtures/derived-Library_ISBN_Barcoder.sit -o <dir> --launch --cancel

Cmd-. reaches `ProgressPump()`'s own keyDown check, the application deletes
the entry it had in flight and puts up "Extraction cancelled.", and the pass
condition is then a **strict, non-empty subset**: every file that IS on the
volume must still be byte-exact, at least one entry must be missing, and at
least one must be there. Both degenerate outcomes fail as a broken TEST rather
than passing — a cancel that arrives after the last entry has tested nothing,
and one that arrives before the first cannot tell a working Cancel from a dead
keystroke. **Pick a slow archive**: this machine extracts
`derived-XferIt_1.5b4.sea`, the largest fixture in the format sample, in under
ten seconds. `derived-Library_ISBN_Barcoder.sit` is the subject the result
below was measured on — StuffIt 5, 34 entries, no name in it that the Mac
shortens into a collision.

**The chord is sent until the dialog goes away, and the count is the
measurement.** `ProgressPump()` runs only from `prog_tick`, which the engine
calls per 8-16 KB of input consumed — so an application decoding a format that
never ticks is not pumping at all, and a chord into it looks exactly like a
chord that does not work. **That is how Now Compress's missing progress
callback was found**: one Cmd-. did nothing, then three did nothing, on the
one format in the corpus that never called back (DECISIONS.md 2026-08-28;
`tools/run_ticks.py` now fails on it). The loop prints how many it took — 1
means the first landed, none prints **"Cmd-. DID NOT CANCEL"** rather than a
quiet pass. Waiting on `PROGRESS_TITLE` between sends is what makes the count
meaningful: a progress dialog reading "0%  estimating time left" is perfectly
still, and `still()` read that as a finished extraction 14 s into a 30 s one.

**`--cancel-click` cancels through the BUTTON**, which is the other branch of
`ProgressPump()` — the chord is its own keyDown test, the button is the
`DialogSelect` beside it — and needs the pointer:

    os9.py fixtures/derived-Library_ISBN_Barcoder.sit -o <dir> --launch \
           --cancel-click
    os9.py ... --cancel-click --click-at 150,168     # the control

Three things make it work, and each is a way it failed to:

- **The cursor is parked before the dialog exists.** `goto()` is a closed loop
  costing ~40 s and the progress dialog lasts as long as the extraction, so
  aiming at it once it is up cannot work. The parking happens while SFPutFile
  is still on screen — a modal dialog waits forever — and `14b-parked.png` is
  the photograph of the cursor sitting where the button will be. The Return
  that starts the extraction moves nothing.
- **The button is HELD down**, `Pointer.press(hold=0.9)`. An application that
  pumps events only from its progress callback dequeues the mouseDown up to a
  tick late, and `DialogSelect` then calls `TrackControl`, which asks whether
  the button is still down: a 60 ms tap that is already over reads as a click
  released outside the control and hits no item.
- **The guest gets a relative `usb-mouse`** (`Qemu(pointer=True)`), never the
  absolute tablet a fixture run leaves attached and unused.

`CANCEL_BUTTON` is computed from `mac/macextract.r` rather than eyeballed:
`DLOG` 128 sits at global (80,80)-(400,190) and does not autocentre, and item
1 of `DITL` 128 is at local (220,78)-(300,98), so the middle is (340,168) —
which is where `15-progress.png` draws it.

**The control is what makes the pass mean anything.** `--click-at 150,168`
presses the same dialog's blank background, 190 px from the button, and
everything else about the run is identical. Measured 2026-08-28, one boot
each, `derived-Library_ISBN_Barcoder.sit`: the button cancels on the first
press, 1 of 34 entries written and byte-exact; the background press does not,
all 34 entries are written, and the run FAILS as a cancel that arrived too
late. Without that second boot, "the extraction stopped early" is equally
consistent with any mouse press waking the application up.

**`--encrypted` answers the password dialog**, and brings its own archive:

    os9.py --encrypted --launch -o <dir>          # no fixture: it makes one

Nothing in the corpus is encrypted, so the subject is built by
`tools/synth_crypt.py` (StuffIt classic DES, three entries, password
`hushnow`) and put on the volume as **MacBinary** — `'MKey'` 0, which verifies
the password, is in the archive's resource fork, so a data fork alone cannot
be decrypted by anything. `verify_output()` is given the same password for the
reference side; without that every entry reads as "missing on Linux".

A **wrong** password is typed first and must be refused, because the retry is
the path a user meets and because an application that ignored what was typed
would pass a single-password run. Both dialogs are keyboard work —
`PassFilter` maps Return to OK and Escape to Cancel — so this needs no pointer.

**Wait over the right rectangle.** The refusal changes the dialog's MESSAGE and
nothing else, and the dialog is a small part of `WINDOW_RECT`: measured over
the window, one rewrapped paragraph moved 0.43 % in 123 s and printed "NO
CHANGE" about a dialog that had changed. `PASSWORD_MSG` is the message area
from `DITL` 132, and over that the same event is 19 % in 4 s.

**`19-names.png` is the photograph of an 8-bit name.** Every tier checks the
BYTES of a MacRoman filename and no tier had ever shown the GLYPHS on Mac
OS 9. `synth-packit-2.pit` carries one: `App` followed by MacRoman `CC A9`,
which the Finder and Standard File both draw as `AppÃ©` — the same two
characters the Linux CLI prints, which converts MacRoman to UTF-8 on its way
out (`cli/main.c`, `macroman_high`). Look at `17-back.png` too: Standard File
lists the extracted files, so the name is drawn twice by two different pieces
of the Toolbox.

**The two sides spell some names differently, and both are right.** The Mac
writes each component as `ComponentToStr63()` does — the engine's `':'` back to
`'/'`, cut at 31 characters — so `SD! Utilities : MacWrite` on Linux is
`SD! Utilities / MacWrite` on the volume. `verify_output()` maps the reference
names through `mac_leaf()` before comparing (the HFS+ path always did) and
fails the fixture outright when two of them map to ONE Mac name: the shell
numbers the second `~1` (`tools/run_macnames.py`, 2026-08-28), so both files
are there and the harness cannot say which reference file either one is.
**What this costs**: a name the Mac cut at 31 characters now compares equal to
the whole one, so this tier cannot see an over-long name. Nothing in the
sample has one; `run_names.py` is where that lives.

**The result is checked off the disk image, not off the screen.** Mini vMac
needs the on-screen CRC grid; QEMU does not, because the transfer volume is a
plain host file. After the emulator exits, `verify_output()` lifts the
Apple_HFS partition out, mounts it with hfsutils, pulls each extracted file
off as MacBinary (`hcopy -m`, which is the only way to get a resource fork
through hfsutils) and compares **both forks byte for byte** against
`macextract x`, unwrap loop on — the reference above, not the autotest one.
A mismatch names the file and the fork; a volume the guest never flushed fails
to mount rather than passing quietly.

`mkapmdisk.py` clones its partition map and drivers from a disk Mac OS 9
already mounts and repoints only the `Apple_HFS` entry. A map built by hand
from the format documentation — correct-looking DDR, correct-looking entries,
status word copied off a real disk — was silently ignored: no volume, no
error, nothing to debug. Cloning a known-good head worked first time.

## What every walk can see — `walkprobe.py`

Harnesses here read a Macintosh volume back — with `hls`, and two of
them with `hdir` — and grade what the application under test wrote onto
it, and they did not agree about what a listing contains. This builds
one volume holding every shape that tells them apart — a plain file, an
INVISIBLE one, a dotted one with the invisible bit CLEAR, and `Icon\r`,
at the root, inside a folder and inside an INVISIBLE folder, plus one
LOCKED file — runs every walk in the tree against it, and says which
came back short. No emulator, no ROM, no X server; seconds.

    tools/vmac/walkprobe.py            # the table
    tools/vmac/walkprobe.py --check    # and assert it against the EXPECT_* sets

As of **2026-09-23**, **twelve** subjects and **four** columns:

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

**All twelve.** The last three joined on 2026-09-23, when *"none of the
other nine listers is gradeable"* turned out to be true of four of them
and not of these — each takes an arbitrary image and returns an entry
set, so there was never a reason not to grade them. **Grading
`mkboot.HFS.ls` found a defect the reading had missed**: it came back
**3/4, missing `Icon\r`**, because it read its listing with `text=True`
and universal newlines cut the name at the carriage return — and
`mkboot.py`'s own `rmtree` says in a comment that the files surviving a
strip *are* `Icon\r`. `verify_stripped` is built on that listing. Fixed
the same way as the Compact Pro walks: bytes, split on b"\n".

`interactive.volume_entries` is itself new — the entry-set listing that
`phase_wrapped`, `phase_chain` and `phase_named` held three copies of.
Collapsing them fixed the same `splitlines()` bug once and turned three
ungradeable inline blocks into one graded function.

The three are root-only by design, not by oversight: each lists ONE
directory, and the callers that need depth walk it themselves. `EXPECT_BLIND` and `EXPECT_NO_LOCKED`
are empty sets and are kept, because they fail in the other direction:
take `-a` back out of any walk and the probe names it. The four that show
`—` never descend at all, which `EXPECT_FLAT` records as a property —
each reads a volume built flat by `make_volume`, or a boot volume whose
`System Folder` is not output.

**`superdisk.read_forks` went last, and what made it last was the
CALLERS, not the walk.** It has **38 call sites** across nine harnesses.
Thirty-four select — by leaf name, by creator (`SMKR`, `SITe`), by type,
or by a DiskDoubler header — and the flag cannot reach those. **Four do
not**: `--adjudicate` in `superdisk.py`, `nowcompress.py` and
`diskdoubler.py`, and `superdisk.py --nest`, each of which holds EVERY
entry on the guest volume against our own extraction, so an entry with
no counterpart in our output is a difference. That is why the filter
lives inside `read_forks` rather than in each caller.

**All four were re-run**, and in each the filter dropped exactly
`Desktop DB` and `Desktop DF` — the files that would otherwise have been
compared against nothing: `superdisk --adjudicate` 2/2 forks identical,
`diskdoubler --adjudicate` 10/10, `superdisk --nest` 11 files with the
Macintosh agreeing, `nowcompress --adjudicate` every fork identical
including one of 9,949,696 B. `spacesaver --layout` and `--pkg` were run
too, and select correctly on a volume where `-a` now surfaces seventeen
invisible `Icon` files. **The rest of `spacesaver.py` is still
unexercised**, and selects by name or creator — an expectation, not a
measurement.

**The inventory was wrong twice in one day, and both times because the
search was for a SPELLING.** It listed six of eight while claiming
"every walk in the tree" — built by grepping for `hls`, and two walks
use `hdir`. Then it listed eight of nine, because it was extended by
grepping for the NAME `read_forks` and every hit was credited to
`superdisk.read_forks`: `nowcompress.py` defines its own, and
`--adjudicate` calls THAT one, so the harness re-run that was supposed
to prove the filter safe passed with a blind walk and printed no filter
line at all. The missing line is what gave it away.

**The population is thirty, not nine, and all thirty pass `-a` since
2026-09-23.** Asking for the CAPABILITY — an `ast` walk over `tools/`
for any function that runs `hls` or `hdir` — finds 30. Nine are graded
in the table above (plus their nested `walk` helpers and this probe's
own measurement functions); the other nine are not gradeable by
`walkprobe.py`, because none of them takes an arbitrary image and
returns an entry set. They were taken anyway, one flag each:

| function | what it reads | what `-a` was worth |
|---|---|---|
| `interactive.phase_wrapped` / `phase_chain` / `phase_named` | the volume's entry SET, against what the application should have written | **real**: an invisible output would read as one never made. `phase_chain` already hand-filtered `Desktop`, which is the same fact spelled once |
| `macmime.HFS.ls` | a MIME phase's output volume, compared with what it wrote | **real**, and it had the `text=True` universal-newline bug too |
| `interactive.read_joined` | a diagnostic listing — *"not on the volume, which holds:"* | printed only when the file was NOT found, so a listing that hides one misleads exactly when it is read |
| `rescomp.report` | the report of what the work volume holds | same: the listing IS the finding |
| `sitcrypt.list_folder` | *"the only way to see what DropConvert called its output"* | an invisible output was not seeable at all |
| `expander.app_from_image` | the one `APPL` on a 400K image | an invisible application would read as "no application" |
| `spacesaver.lift_installer` | the installer, found by searching the listing | a name search cannot find a hidden file |

The re-survey is one command and is how this stays true:

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

**`FINDER_OWN` lives in `mkboot.py`**, the module with no imports of its
own. It was in `arcmac.py` until `interactive.py` needed it and could
not import that file — arcmac imports `Mac` from interactive, so the
arrow already pointed the other way.

**Two of the four columns are new, and both came off a real volume
rather than out of a list of things that could go wrong.** The cache in
`~/.cache/macextract/vmac` holds 84 mountable images; listing every one
twice, with `-a` and without, says what the flag is actually worth here:

- **an invisible FOLDER** is the cell where the first two columns cross,
  and passing either does not imply passing it. Now QuickFiler creates
  `[Now QuickFiler Folder]` on the volume it is compressing on and puts a
  `NCdb`/`NCex` database inside it — the FOLDER invisible, the database
  not — on six of the kept `specimens/now/*` work volumes.
  `diskdoubler.volume_files` was the walk that earned this column: it
  descends, and it used to walk straight past a folder it could not see;
- **a LOCKED file** has nothing to do with `-a` at all. `hdir` prints one
  with a leading `F`, so `cptsegment.read_volume` and
  `cptcrypt.read_volume`, which kept a listing line on
  `line.startswith("f")`, threw every locked file away along with the
  directories that test was aimed at. `mkboot.Hfs.ls` had the same
  character set and the same hole. One locked item exists across all 84
  images — `[DiskExpress Activity Log]` on the Norton DiskDoubler Pro
  floppy, invisible AND locked.

**`--check` can fail, and every column has been made to.** Taking `-a`
back out of a walk reports it newly blind; claiming a walk descends when
it does not reports that; the hidden-folder column was failed both ways
against `diskdoubler.volume_files` on the day it was written, and the
locked column named the two Compact Pro walks before they were fixed and
named them again, as gains, after.

**The table grew twice on the day it was written, and neither growth was
a new walk being added to the tree.**

- **Two walks were missing from it.** `cptsegment.read_volume` and
  `cptcrypt.read_volume` list with `hdir` rather than `hls`, so the
  survey that built this table — a grep for `hls` — did not find them.
  `hdir` hides the invisible bit exactly as `hls` does and takes the
  same `-a`: 3 lines against 5 on the probe volume, re-derived on every
  run. DECISIONS.md already said this about `hdir` and no probe had
  ever asked it.
- **The second column did not exist**, and the volume it measures has
  been there since the probe was written: the same four subjects are
  copied into `Folder`, and the verdict compared leaf NAMES. The folder
  holds the same four names as the root, so a walk that returned two
  entries and one that returned eight both scored 4/4. **Four of the
  eight never descend.** That is not automatically a defect — all four
  read volumes built flat, which `EXPECT_FLAT` records — but it was a
  property the probe's own docstring claimed to test and could not see.

**What each fix cost, and what `-a` is NOT free of.** The template is
`arcmac.read_volume`: the flag, a three-name `FINDER_OWN` filter
measured on that harness's OWN volume rather than assumed — `hls -a -1`
there adds exactly `Desktop`, FNDR/ERIK, invisible, to the four `hls -1`
gives — the raw-bytes rule for `hcopy`, and one Mini vMac run to
re-verify. Its two callers (`arcmac.make`, `maclha.make`) select by file
TYPE and extension, so neither compares fork sets. Every walk fixed
since **prints what its filter dropped, on every run**, so the filter is
a measurement rather than a constant somebody trusted:

- `cptsegment` and `cptcrypt`: `Desktop`, and nothing else.
- `nowcompress`: `Desktop` and `[Now QuickFiler Folder]`, which is the
  application's own bookkeeping and the thing this walk used to miss.
- `diskdoubler --wild` on the 3.7 disk: `Desktop`, and the figure it
  reports is unchanged at 10 compressed files.
- `superdisk` on a System 7 work volume: `Desktop DB` and `Desktop DF`.

And `-a` cost one real defect on the way in, which is why the rule is to
re-run the harness: it made `Icon\r` reachable for the first time, and
the two Compact Pro walks read their listing with `text=True`, which
applies **universal newlines** — the carriage return inside the HFS name
becomes a line break, so `hcopy` was handed `Icon` and a file that does
not exist. `hdir` prints the CR verbatim; the listing is bytes now.

**Two things outside the walks were fixed the same day.**
`os9.wrapper_names` is a NEGATIVE — the verdict is that none of the output
is on the plain-HFS wrapper — and it was reading the listing that makes a
negative EASIEST to satisfy. And `mkboot.verify_stripped`, which asserts
that the boot image's System Folder holds only System and Finder, **could
not fail on the files the strip is unable to delete**: an invisible
`Ghost INIT` copied into a freshly stripped System Folder passed it. Both
now pass `-a`; `ls()` takes it as a parameter rather than a default,
because `strip_system_folder` deletes what `ls` returns and the Finder's
`Desktop` is invisible and kept on purpose. `run.py` on one fixture, 1/1.

**What it cannot see:** whether any of the blind walks has ever actually
lost something. That depends on whether the application each one grades
writes an invisible file, which is a question about those applications
and not about the walks — and it is worth asking of each, because the
one case this file called "already known to be a real risk" turned out
not to be one. `arcmac.macbinary`'s docstring said the ArcMac header's
Finder info carries the invisible bit; measured over all 5 ArcMac files
and 11 entries here, none does (BLOCKERS.md, *Withdrawn claims*). The
walk was blind either way, and the flag cost nothing, so it was still
worth taking — but the risk that ordered the work was not there.

## Mac OS 9 with the pointer — `os9mouse.py`

What `os9.py`'s keyboard route cannot do is operate an application: click a
checkbox, walk an installer, answer a dialog. `os9mouse.py` does, and it is
what produced the StuffIt 5 encryption specimens (FORMATS.md, *StuffIt 5's
RC4*).

    python3 -c "import sys; sys.path.insert(0,'tools/vmac'); import os9mouse; \
                m = os9mouse.Mac(cd=True); m.settle(); m.png('desk')"

It is a module rather than a command because every session is a different
dozen steps. The positioning algorithm itself is `Pointer`, which takes a
"send these monitor commands" and a "give me a frame" and belongs to neither
guest: `Mac` hands it its own, and `os9.py` hands it `Qemu`'s for
`--cancel-click`. The pieces:

| call | does |
|---|---|
| `Mac(cd=True, xfer=True)` | boot from a qcow2 overlay on the 2 GB master, with the Deluxe CD and the transfer volume attached |
| `Mac(attach=True)` | connect to a guest already running, so successive scripts drive one boot |
| `m.goto(x, y)` / `m.click(x, y, double=)` | closed-loop positioning, then a click |
| `m.key("meta_l-s")`, `m.typestr("text")` | keystrokes; **prefer these** — see the timing note |
| `m.shot(tag)` / `m.png(tag)` | screendump straight to PPM (no ImageMagick) and a PNG to look at |
| `m.settle()` | wait until the screen stops changing, with a floor |
| `find_not_yet(frame)` | locate DropStuff's "Not Yet" button, which moves |

Four things it knows that cost a run each, all in the module's own docstring:
the absolute pointer is inert; the menu-bar clock and a blinking caret both
defeat frame-differencing (hence `largest_blob`); positioning takes ~40 s,
which is longer than a sticky menu stays open, so use Command keys; and
DropStuff's nag shuffles its buttons, so the label is matched, not assumed.

**Getting a file back out** is the same trick as everywhere else here: write
it to the plain-HFS transfer volume, then unmount that volume from inside the
guest (select it, Cmd-Y) so the guest flushes, and read the Apple_HFS
partition with hfsutils. The boot volume is HFS+ and the host cannot read it.

### What the pointer cannot select, on either emulator

**A menu ITEM is not reliably selectable by this harness, and as of
2026-09-27 that is measured on both guests rather than one.** Mini vMac's
hierarchical submenus were the first case (`sitcrypt.py`, *the Translate
menu*): the submenu opens, the parent stays highlighted, the item under the
pointer never does, and the release selects nothing — three ways in were
tried.

The same symptom is now recorded on **Mac OS 9 under QEMU, on a TOP-LEVEL
menu**, which is what makes it a harness limit rather than a quirk of
hierarchical tracking. Driving DropStuff's `File` menu:

- **clicking the title, then the item** fails for a different reason —
  `goto()` costs ~40 s and the sticky menu has closed by the time the second
  click lands (`shots/c_ds_prefs.png`, the menu gone and no dialog);
- **holding the button down and stepping into the item** removes the timeout
  — the menu is still open in `shots/c_ds_menu_held.png` — but **no item
  highlights**, and the release selects nothing. Same signature as the
  submenu case.

So on either guest, reach a menu item by its **Command key** or not at all.
DropStuff's `Stuff…` (⌘S) and `Quit` (⌘Q) are drivable; its `Preferences…`,
which has no Command key, is not. *Hypothesis*, unreduced and now with two
guests' worth of evidence: the Menu Manager wants mouse movement neither
emulator's pointer injection produces.

**But DRAGGING works, and that is the useful half of the same experiment.**
Holding the button down across relative `mouse_move` packets is exactly what
a Finder drag needs, and it tracks: pressing on an application icon, stepping
882 px across the screen and releasing over a volume copied it, ghost icon and
all (`shots/h_drag_over.png`, `shots/h_dropped.png`, 2026-09-27). So the limit
is the Menu Manager specifically, not held-button interaction in general —
file copies, window drags and anything else that is press-move-release are
available. There is no `drag()` helper yet; it is four lines:

    m.goto(sx, sy)
    m.burst(["mouse_button 1"], wait=0.6)
    m.step(dx, dy)                       # splits into <=40 px packets itself
    m.burst(["mouse_button 0"], wait=2.0)

### A plain-HFS Mac OS 9 boot volume — `hfsboot.img`

`$UNC_VMAC_HOME/../sit5/hfsboot.img` is a 1 GB **Mac OS Standard**
volume carrying a bootable System Folder, built 2026-09-27 with no install
media:

    tools/vmac/mkapmdisk.py <MacOS9.img> hfsboot.img 1024 HFSBoot
    # attach as a fourth drive, drag the System Folder onto it inside the
    # guest (1,751 items, ~215 MB, about five minutes), then Cmd-Y to flush

Relaunch with it as `index=0` and it is the startup disk: it sits at the top
of the desktop volume icons, the *"did not shut down properly"* alert stops
appearing, and the HFS+ volume gains ~500 MB as its virtual-memory swapfile
goes idle. **That is how to tell which volume booted**, since About This
Computer is behind the Apple menu and menu items are not selectable here.

It exists because *"StuffIt Deluxe 5.0.1 needs an HFS boot volume"* turned
out to be false — the application raises its file-system alert in all four
combinations of boot volume and application volume, so the trigger is Mac OS
9.2 (BLOCKERS.md, *Withdrawn claims*). The volume is kept anyway: the next
HFS-versus-HFS+ question costs one relaunch instead of an afternoon.

## Checking a run off the disk instead of off the screen

`run.py` reads its result from the framebuffer: the application paints a grid
of a file count, two summed CRC-32s and two summed lengths, and the host
decodes it. That works, and it is blind to one thing — **a summed CRC cannot
carry a filename**, so no run.py verdict has ever depended on an output NAME.
A real defect in the gzip/.Z fallback name lived in the corpus for weeks
because of it.

That was not a necessary limitation. BLOCKERS.md had claimed since M10 that
Mini vMac's write-back is "lazy and PARTIAL — it can commit one fork of a file
but not the other", so the Out volume could not be trusted. It does not
reproduce:

    run.py --keep-disks --list sample.txt      # keep each run's disk images
    checkdisk.py /tmp/vmacrun-*/               # read them back

**55/55 byte-exact**, both forks, names and folder structure included, over
the committed sample — including `derived-RWAsm_Folder.sit` at 38 files and 73
forks, an 8-bit `spinning brain ƒ` folder, a MacRoman `Appé`, and a
`.DS_Store`.

`checkdisk.py` identifies each run's fixture from the `in.dsk` beside the
`out.dsk`, so it needs no bookkeeping, and it feeds the reference extraction a
copy named `archive.sit` — the name the Mac saw — because gzip and .Z derive
their output name from the archive's filename.

**It has to know what the Mac does to a name, and since 2026-09-22 that is
two rules rather than one** (`tools/vmac_check.py`, `mac_component`): every
component is fitted to 31 characters with its extension KEPT, and a StuffIt
5 name — UTF-8, where every other format states MacRoman — is folded into
the bytes an HFS name holds first, so a Japanese name arrives as a row of
`_`. The fold is applied only where the engine says the names are UTF-8
(`macextract sniff`), because folding a zip name that MacRoman cannot spell
would invent an agreement the Mac does not make. **Fold before normalizing**:
the shell folds the archive's own bytes and `ユーザーライセンスの購入.rtf`
is DECOMPOSED in the archive, thirteen code points where the composed
spelling is twelve, so an NFC fold predicts one `_` too few. The oracle
manifests hold the composed spelling, which `run_diff.py` normalizes away
and this cannot.

Three hfsutils traps it hit, all worth knowing before writing anything
similar:

- **`hls` hides a file whose Finder INVISIBLE bit is set** unless given
  `-a`, and **the leading dot has nothing to do with it** — which is what
  this file and `checkdisk.py` both said until 2026-09-22. Measured as a
  2x2 by `walkprobe.py`, all four cells: a dotted name with the bit clear
  is listed without `-a`, and a name with the bit set is hidden whether it
  starts with a dot or not. `.DS_Store` needed the flag because a
  Macintosh writes it invisible. The defect that found this was on a Mac
  OS 9 volume where `hls -F -1` listed four entries and `hls -a -F -1`
  listed five; the fifth was `Icon\r`, 51,781 bytes of resource fork,
  which the application had written correctly and the harness reported
  MISSING.
- **`rstrip()` is not how you take the newline off `hls -1`'s output.** A
  carriage return is a legal HFS filename character and it is the last
  one of `Icon\r`, the name every custom folder icon on a Macintosh has.
  Splitting on `\n` has already removed everything that is not name.
- **Every path argument must be encoded as MacRoman**, not UTF-8, or any
  8-bit name is a file that does not exist.

`os9.py` had learned the third one for `hcopy`
and not for the `hls` its folder walk runs: a FILE with an 8-bit name at
the root had been checked since 2026-08-28, and the first FOLDER with one
— `Terrainman 2.0 ƒ`, on 2026-09-04 — listed as empty, so the harness
failed a run the application had completed and the volume held whole.
Fixed the same day (`_walk_volume`). It learned the first two on
**2026-09-22**, when `derived-800saywhat301j.sit` joined `os9sample.txt`
and its `Icon\r` came back MISSING from a volume that held it — so until
that day an invisible entry was invisible to this tier's COMPARISON as
well as to the Finder. All three were already right in `checkdisk.py`,
which is the shape of the lesson: a harness written twice learns once.

The same question was then asked of **every** volume walk in this tree,
because the wrong explanation above is exactly what made the flag look
like somebody else's problem — see *What every walk can see*, below.

## On-demand probes — the `-D` switches and the one-off harnesses

Every switch below rebuilds the autotest application and answers one question
the normal replay cannot. The first two change the BUILD — which overlay
lifetime, or none — and the rest add a probe. None is part of any suite; each
is run by hand when the question comes up again. **A `-D` the CMakeLists does
not know is silently ignored** — `run.py` passes it through the environment and
CMake drops what it has no rule for, so a probe can "work" and change nothing.
Check that its numbers actually moved before believing them.

Results are not repeated here; each line says where they live.

| switch | answers | where the result is |
|---|---|---|
| `UNC_OVL_LAZY` | the OTHER overlay lifetime: one image per format, read when a format turns out to want it, instead of the shipped bundle-at-launch. Changes the BUILD rather than adding a probe, and every harness can pass it because it is a boolean | FORMATS.md, *Overlays* |
| `UNC_OVL_RESIDENT` | the application as it was before 2026-09-25 — every decoder linked in, no images. The CONTROL for any budget claim about the overlays, since its budget does not move with the archive | FORMATS.md, *Overlays* |
| `UNC_AT_BUDGET` | why an entry was refused: over budget, or `NewPtr` failed | DECISIONS.md 2026-08-06, OPEN_ITEMS.md section 5 |
| `UNC_AT_RESERVE` | what the shell actually needs of the heap kept back from the engine — a `FreeMem()` low-water mark, printed on the completion alert. It priced `kMemReserveMax` from 80 KB down to 48 KB (13,242 B measured). **Needs a fixture that FITS and is heavy**: a small one never fires the progress pump, and one too big has its allocation refused before the heap is stressed | FORMATS.md, *Budget* |
| `UNC_AT_STACK` | what `kStackBump` is actually worth. Paints the whole region between ApplLimit and the stack base at launch and reads back how far down anything wrote. **Read the watermark, not the first transition**: a frame is made by moving the stack pointer, so a frame holding an uninitialised buffer leaves clean longs INSIDE the region it used, and two earlier versions of this probe — scan up for the first dirty long, scan down for the first clean one — both reported the same number for a 3 KB BinHex file and a 34-entry StuffIt 5 archive. Autotest under-reads the shipped build, which has the dialogs | FORMATS.md, *Stack* |
| `UNC_AT_HANDLES` | does `MoveHHi` move an engine block, and does it help | OPEN_ITEMS.md section 5 (do-not-retry) |
| `UNC_AT_INTERLEAVE` | do reads return zeros while output is written to the same volume | BLOCKERS.md *Withdrawn claims* |
| `UNC_AT_SAMEVOL` | does extraction onto the archive's own volume work | DECISIONS.md 2026-08-02 |
| `UNC_AT_WD` | is `SFReply.vRefNum` handled as a System 7 working directory | DECISIONS.md 2026-08-01 |
| `UNC_AT_CANCEL` | does an aborted entry leave anything behind | BLOCKERS.md, MANUAL_TESTS.md checklist |
| `UNC_AT_NOHIDECURSOR` | is `HideCursor()` before painting the grid necessary | yes — BLOCKERS.md; two things must be right before the test means anything: the pointer must be INSIDE the emulator window (at (144,129) on the 800x600 Xvfb) and the drag must cross cell CENTRES, since a path between rows disturbs nothing. `UNC_VMAC_PARK` overrides the parking position |
| `UNC_AT_PROGRESS` | how fast is the engine actually going, mid-run | BLOCKERS.md "Timing on a 7 MHz Mac Plus" |
| `UNC_MAC_SLURP_ARCHIVE` | rebuilds the old read-whole-archive-into-RAM path | DECISIONS.md 2026-08-02 |
| `UNC_AT_TIMING` | split the extraction into File Manager reads, writes, the rest of the File Manager and the engine, in TICKS, in grid slots 3-6 (so the CRC check FAILS by construction — read the numbers, not the verdict). The instrument that showed 98.5 % of a StuffIt run is the engine, and the one that resolves an optimiser change: FORMATS.md, *What -O3 is worth, and where* | FORMATS.md |
| `UNC_MAC_STAGE_WRITES` | the older whole-fork staging write path (also in `ci.sh`) | TESTING.md |

### Filling the destination on purpose — `--out-kb`

    run.py --mem 1M --out-kb 800 fixtures/derived-OTCFM68KGlue.sit

`hformat` refuses anything under 800 KB, so the smallest destination is an
800 KB volume and the fixture has to be one whose output exceeds it;
`derived-OTCFM68KGlue.sit` (17 entries, ~1 MB out) and
`derived-XferIt_1.5b4.sea` (10 entries, 926 KB out) both do.

It reports FAIL by construction — fewer files came out than the oracle
expects. **Read the numbers.** What it proves is that the run STOPS: 9 files
written, `errors` = **1**, `ret` = −9 (`UNC_ERR_SINK`), and the eight
remaining entries never attempted. That is the check behind the withdrawn
claim in BLOCKERS.md that a full disk produces one error per remaining
entry; it does not, because every extractor ends the archive on a sink
failure.

**The default is a 1,440 KB floppy, and that is a limit in the OTHER
direction too.** A single entry larger than the volume fails at `SetEOF`
about twenty seconds in, `ret` −9, and reads exactly like a per-entry memory
refusal unless the `ret` slot is read: `derived-EasyFind.dmg.sit`, one entry
of 1,851,907 B, was carried as "still refused on a 1 MB Mac Plus" for 18 days
on runs that had never had room to write it (BLOCKERS.md, *Withdrawn
claims*, 2026-09-18). `--out-kb 2400` is what that fixture needs. And a
fixture capped near its memory minimum sits on a low rung of Arsenic's
sampled index, where the walk is long even all-out — XMenu 704 s, EasyFind
1,427 s at 562,000 B — so `--timeout 1700` rather than the default, or a
timeout reads as a refusal as well.

**What it cannot see:** the alert the user is shown. That lives in the
interactive build, which this harness does not run — `interactive.py` does.
The message is chosen from `gLastWriteErr`, and only the choosing is
untested.

### Why an entry is refused — `UNC_AT_BUDGET`

    run.py --mem 1M -D UNC_AT_BUDGET fixtures/<fixture>

The grid carries what the engine **used** and never what it was **allowed**, so
a budget refusal and a genuine shortage look identical on screen — and
`mal_alloc` returns NULL for two unrelated reasons with opposite fixes. The
probe overwrites four slots:

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

**Corrected 2026-08-31.** The free figure and the budget were written into two
slots and then overwritten by the zone bounds two lines later, so the budget
never reached the grid and reading it meant editing the source. They have
their own slots now, taken from the third and fourth block addresses.

`FreeMem()` minus `MaxBlock()`, both sampled **at the refusal**, is the
fragmentation; sampling free heap at the start of the run does not give it, and
one such inference has already had to be corrected. Earlier revisions carried
the refused size, free-at-refusal and held-at-refusal instead — those figures
are in DECISIONS.md 2026-08-06; swap them back by editing the `UNC_AT_BUDGET`
block if a re-run needs them.

It reports FAIL by construction, because the overwritten slots no longer match
the oracle. **Read the numbers, not the verdict.**

**Pair it with `-D UNC_OVL_RESIDENT` to get a budget that can be subtracted
from another.** The switch is not free — it costs the eager configuration
400 B of `CODE` + A5 and the control 304 B — so a budget read here is that
much lower than the build the tallies come from, and a grant compared against
a base from a DIFFERENT build carries the difference as a mystery. That is
what 2,926 B of "residue" turned out to be on 2026-09-27 (FORMATS.md, *Three
configurations, one tree*; DECISIONS.md 2026-09-27, *the residue that was two
numbers*).

`UNC_AT_HANDLES` additionally swaps the engine allocator to `NewHandle` +
`MoveHHi` + `HLock` (the reverted remedy, kept buildable) and reports the
block's **address** either side of `MoveHHi`. Its first revision reported
`MaxBlock` there and **could not fail**: `MaxBlock` is blind to where inside a
free run a block sits, so moving one from the bottom to the top reads exactly
like not moving it. It instruments the first allocation of 64 KB or more, which
is not necessarily the Arsenic block — StuffIt's combined io/output buffer also
qualifies — so it proves `MoveHHi` moves *an* engine block, not that one.

### The same-volume and interleaved-read questions

    run.py -D UNC_AT_INTERLEAVE fixtures/derived-EmpireBuilderDemo.sit
    run.py -D UNC_AT_INTERLEAVE --mem 1M fixtures/derived-EmpireBuilderDemo.sit
    run.py -D UNC_AT_INTERLEAVE fixtures/derived-PCCTS.tar
    run.py -D UNC_AT_SAMEVOL --list sample.txt

The first reads one file three ways on one volume — undisturbed, in 4 KB chunks
with a file created and written between every chunk, and again seeking with
`SetFPos` before each read — and compares CRC-32s. The second points the output
at the volume the archive is being read from, which is what the interactive
application does and what no other run here does.

### Working directories, without a Finder

    run.py -D UNC_AT_WD fixtures/derived-EmpireBuilderDemo.sit

Makes a real working directory over a real subfolder with `PBOpenWD` and
extracts through it exactly as `ExtractOne()` does, counting what landed in the
folder and what leaked to the root. Every other harness here extracts into a
volume root, where a working directory and the root are the same directory —
which is why this code was untested until 2026-08-01.

### Name collisions — `mkcollide.py`

    mkcollide.py /tmp/collide.tar
    run.py --keep-disks /tmp/collide.tar
    mkcollide.py --verify <that run's out.dsk>

`BumpName()` appends `~1`..`~9` when a sanitized name already exists, and
**nothing in the corpus can exercise it**: across all 783 manifests no two
entries collide under the Mac's rules (case-insensitive HFS, 31-character
components, `:` <-> `/`) — measured, not assumed, and re-measured on
2026-08-08. So the archive has to be built for it. Five entries collide two
ways, and each payload is distinct and self-identifying, so the check is "the
right bytes are in the file with the right name", not "five files exist":

| archive entry | on the Mac | payload |
|---|---|---|
| `README` | `README` | upper case |
| `readme` | `readme~1` | lower case |
| `collide-me-when-truncated-to-31-alpha` | `collide-me-when-truncated-to-31` | alpha |
| `collide-me-when-truncated-to-31-beta` | `collide-me-when-truncated-to-~1` | beta |
| `collide-me-when-truncated-to-31-gamma` | `collide-me-when-truncated-to-~2` | gamma |

All five arrive, none overwrites another, each holds its own payload, and the
29-character clamp is visible: `collide-me-when-truncated-to-` is 29
characters, then `~1` makes 31. Archive order decides who keeps the plain name.

### The `SIZE` partition

    sed -i 's/4096 \* 1024, 400 \* 1024/600 * 1024, 400 * 1024/' mac/macextract.r
    run.py --system Sys7.img fixtures/derived-KeyGraphics.sit
    run.py                   fixtures/derived-KeyGraphics.sit
    os9.py fixtures/derived-KeyGraphics.sit -o <dir> --hfsplus --expect-refusal
    git checkout mac/macextract.r        # the edit is temporary, on purpose

A partition big enough to launch and too small for a 512 KB Arsenic block,
against a fixture that needs ~656 KB and passes at 4 MB. `--expect-refusal`
makes the run self-checking: it passes only when the Linux engine DOES extract
the fixture, the Mac writes nothing, the archive returns `UNC_OK`, and an entry
is counted as refused — without that first condition a negative test would pass
just as happily on an empty archive. Three-system table in FORMATS.md.

### Forcing a memory refusal on screen

The `SIZE` edit above is the wrong instrument for this one, and finding that
out cost four runs. A partition is only enforced under MultiFinder — System
7 and up — and until 2026-08-25 `interactive.py`'s Standard File clicks were
calibrated for System 6 alone; on System 7 they selected the wrong item and
the application answered `UNC_ERR_FORMAT` about a file that is not an
archive. That frame looks like a code failure and is not. The clicks are
per-system now (below), so the `SIZE` route is available again — it is still
two boots and a Get Info against one throwaway build.

Cap the budget instead, in a throwaway build, on the machine the harness can
drive (the System 7 objection below is gone since 2026-08-25 — the phase runs
there now — but this recipe is still the cheaper instrument):

    sed -i 's/ma.budget = freenow - reserve;/ma.budget = 150000L; (void)reserve;/' \
        mac/macextract_mac.c
    interactive.py --emu mv-4M -o /tmp/alert fixtures/derived-AuthoRize_2.0.sit
    git checkout mac/macextract_mac.c    # temporary, on purpose — wrap it in a trap

The alert is in `2-extracting.png`: the default phase clicks Cancel at a
fixed time, and a run that fails BEFORE then leaves its result alert up in
that frame. Photographed 2026-08-24: *Needs 72K more memory. Give MacExtract
more in Get Info.*

### Photographing the detect-only alert

No build trick and no fixture: hand the application a file it NAMES and
cannot open, and the alert is in `2-extracting.png` for the same reason the
memory one is — the run fails before the phase clicks Cancel.

    interactive.py --emu mv-4M -o /tmp/rarshot /tmp/Sample.rar

Photographed 2026-08-26 with a RAR archive out of libarchive's test suite:
**"MacExtract cannot open RAR files."**, one line, the alert's default OK
button. Any of the named-but-declined formats does it (FORMATS.md, *Archives
named but not extracted*); the sentence is built from `unc_format_name`, so
the longest of them draws 46 characters and still fits two lines.

**`interactive.py` exits 1 on this run and that is not a failure**: its
phase-2 check is that the CLI and the Mac agree on extracted output, and
there is no output to agree about. The screenshot is the result.

The same build trick photographs the OTHER two failure alerts, which no
headless harness runs:

    # the disk is full — the real gLastWriteErr path, without a full disk
    sed -i 's#(Ptr)((const char \*)buf + off));#&\n        { static int nw = 0; if (++nw > 2) werr = dskFulErr; }#' \
        mac/macextract_mac.c
    # memory too fragmented — that branch fires on any run
    sed -i 's/        gShortPiece = 0;/&\n        gShortPiece = 1;/' mac/macextract_mac.c

`run.py --out-kb` already measures that a genuinely full volume returns
`dskFulErr` here and stops the run; what these show is the sentence the user
is given afterwards. Photographed 2026-08-24, both two lines.

**The alert box is two lines wide, and the wrap is not obvious.** Measured
off those frames, it breaks between 32 and 36 characters, so a message over
about 60 characters draws a third line that sits level with the OK button
and looks broken. Three shipped strings did; they were shortened. Check a
new one by eye on a frame, not by counting.

**When a frame is ambiguous, make the alert say which branch drew it.**
Temporarily replacing the generic `ret != UNC_OK` branch with one that
`PStrCatNum`s `ret`, `gShortBy`, `gShortPiece`, `entries` and `errors` ended
three runs of guessing in one frame — `entries = 0` said the archive had
never been opened, which no amount of staring at the shipped wording could
have told anyone.

### The end-of-run report — `interactive.py --report`

    tools/vmac/interactive.py --report --emu mv-4M -o shots fixtures/anything.sit

Ignores the fixture: the archive is generated (`report_archive`), because
nothing in the corpus can make this box say anything. It holds names too long
for HFS, one that fits only once its extension goes, a duplicate, two folders
that shorten to the same name, eighteen photographs alike for 31 characters,
and one entry whose checksum is broken by a single bit — so the box lists a
rename, a numbered file, a numbered FOLDER and a per-entry failure at once,
and is long enough that the scroll bar is live.

Five frames: the box, the box scrolled six lines, Standard File over it after
**Save as Text**, the box redrawn once that is dismissed (which is what proves
the default ring and the list come back), and SFGetFile afterwards.

**It asserts, and the assertion is the saved DOCUMENT**, read back off the
volume with `hcopy -t` and checked line by line — a photograph of a box full
of text cannot fail, and a missing line in that file can. It also checks the
names the report CLAIMS against the names on the volume.

`--emu mv-4M` rather than the 1x default: nothing here is timed, and the
archive is a few hundred bytes.

The box's three click targets are constants measured off `DLOG 133` in
`mac/macextract.r` (`REPORT_OK`, `REPORT_SAVE`, `REPORT_DOWN`). **Re-measure
them if that resource moves** — this is the harness that clicks fixed
coordinates.

### The one line a generated archive cannot make — `interactive.py --report-utf8`

    tools/vmac/interactive.py --report-utf8 --emu mv-4M -o shots fixtures/anything.sit

*"`<name>` was named in characters this Macintosh cannot write"* is the
report's only line that no DiskDoubler archive can reach: the fold runs where
the ENGINE says a name is UTF-8, and `fmt_sit5.c` alone says so. So this phase
ignores the fixture the other way round — it uses one real corpus archive,
`derived-800saywhat301j.sit`, whose three Japanese names MacRoman has a byte
for none of. Four frames (the box, Standard File after **Save as Text**, the
box redrawn, SFGetFile) and the same assertion `--report` makes: the saved
DOCUMENT, plus the names on the volume. A photograph of a box full of `_`
cannot fail.

The counts in that assertion are not the ones a reader would guess —
`ユーザーライセンスの購入` is thirteen `_` and not twelve, because the
archive stores `ザ` decomposed. The outcome line is the CLEAN one,
*"Extraction complete."*: nothing failed, every entry came out, and the
box is up only because the shell has something to say about the names.

**Why the report goes to a floppy, and the control that says so**

    tools/vmac/interactive.py --report-utf8 --utf8-to-boot --emu mv-4M \
        -o shots fixtures/derived-800saywhat301j.sit

Extract this archive onto the BOOT volume instead and the saved report
cannot be read off the image afterwards, though the Macintosh plainly
has it. `--utf8-to-boot` is that run: it drops the one click that
switches volumes, keeps the image, and reads it twice —

    the extraction's output is in the catalog   : YES
    the report is in the catalog                : NO
    the report's TEXT is in the image's blocks  : YES

so **the bytes land and the directory record does not**, which is why a
30 s flush wait, Control-Q, SIGTERM and the shell's own `FlushVol` all
changed nothing: they were aimed at a write that had already happened.
The exit code is 1, because the phase's own assertion still fails —
that is the point of a control. DECISIONS.md 2026-09-22, *the file that
was on the disk and not in the catalog*.

**It does not search for the report's NAME**, and neither should
anything else here: `Extraction Report` is the name `SFPutFile` offers,
so it is in the application's resources on the same volume and a raw
search for it says YES in every run, saved or not. The blocks are
searched for a string only the saved document can hold.

**And one level below that — `--utf8-second`, the discriminator**

    tools/vmac/interactive.py --report-utf8 --utf8-to-boot --utf8-second \
        --emu mv-4M -o shots fixtures/derived-800saywhat301j.sit

Whether the missing entry is destroyed or merely unwritten is answered
by doing the save a SECOND time, under the name `Second`, so one more
catalog update follows the lost one. Both land:

    the report is in the catalog       : YES
    the SECOND report is in the catalog: YES

So the first entry was **unflushed, not lost**, and a fixed tail of
Mini vMac's buffered stdio is ruled out — both entries live in the same
catalog leaf, so a lost tail would have taken them both. This phase
exits 0. DECISIONS.md 2026-09-22, *the entry a second write placed*.

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
    interactive.py --drop           # drag an archive onto the application's
                                    # icon: what does the FINDER do?

Run them one at a time (see "This box has one core", above). **One at a
time is not only about the core**: every phase builds the application
into the same `build/mac-interactive`, so two `interactive.py` runs
started together fight over it and one dies in `cmake --build`.

**`--named zip` needs a fixture larger than 64 KB.** `zip -s 64k` marks
an archive split whatever its size, so a smaller payload makes one
`Aset.zip` and no `Aset.z01`, and the application correctly answers
*"This archive has more parts. Find them and try again."* — a harness
invocation error that photographs exactly like an application bug, which
is the shape this directory keeps meeting. Drive it with
`fixtures/derived-xmasbeeps.sit`.

**On System 7 the dialog is not the same dialog, and the clicks know it
since 2026-08-25.** System 7 draws its own Standard File — a directory
pop-up above the list, a Desktop button beside it — whose first row sits ten
points higher, so a System 6 coordinate selects the SECOND item. `calibrate()`
picks the row off `SF_ROWS` for the system being booted, and a system with no
entry there is refused rather than clicked at. The other half is WHERE the
dialog opens: System 7's Process Manager gives each application its own
default directory, so under the boot-shell arrangement it opens inside the
System Folder listing `Finder`, `System` and the application.
`sf_to_volume_root()` presses Desktop and opens the volume — two clicks, no
menu tracking — and does nothing at all on System 6, which opens at the root
already.

`--e2e` leaves the **Finder** in place instead of installing the application as
the boot shell, which is the only way to launch the application the way a
person does and the only way to launch what it extracted. Both runs photograph
every step, and `docs/screens/` comes from here.

**It cannot photograph a legible icon label**, so `docs/screens/0-icon.png`
comes from `mountcheck.py --open` instead. The `--e2e` volume window holds four
items in one row, one of them the empty `StuffIt Expander™ 4.0.1 Folder` that
`mkboot.py` cannot delete, and the Finder paints overlapping labels in HFS
catalog order — which is by name. `MacExtract` sorts before `StuffIt…`, so that
folder's label lands on top of the application's and the name is unreadable in
`e2e-2-volume.png`; the icon itself is unobstructed. `mountcheck.py --open`
opens `dist/MacExtract.dsk`, whose volume holds the application and nothing
else, so there is nothing to collide with.

What a pass looks like, and the fixtures that make it checkable: `--e2e` uses
`derived-ScrollbarPattern.sit`, whose entry is an application — so the last
step is double-clicking `Scrollbar Pattern Editor` in the Finder and seeing it
draw its own splash screen, which exercises type/creator, the Finder inited
flag and resource-fork integrity together (the application *is* its resource
fork). The cancel run uses `derived-EmpireBuilderDemo.sit`, three entries: after
a cancel, SFGetFile must list exactly `Demo Manual V1.6` — the one entry that
finished — with no trace of `EB Sounds`, the entry that was being written.
Partial-output cleanup seen in the file list rather than inferred. Status for
both is in BLOCKERS.md.

`--segments` cuts the fixture into three parts, leaves part 1 alone on the
boot volume and puts the other two on a second floppy, so the folder scan
must fail and the alert must appear. It then offers the WRONG part on
purpose, to see it refused by fingerprint and named for what it is. Unlike
the other two phases **it ends on a byte comparison** — the joined file read
back off the volume the Mac wrote to, against the fixture — and exits
nonzero if they differ, so it is not purely a look-at-it harness.

Two things it will get wrong if you copy it:

- **Standard File opens on the last-inserted volume**, which is the parts
  floppy, not the boot disk. Click Drive and photograph the result before
  clicking a row. The first version did not, opened part 2, and produced a
  screenshot of the app asking for part 1 — correct behaviour that read
  exactly like a bug.
- **`Mac()` boots from a private copy of the boot image.** Read results back
  from `<workdir>/boot.hfv`, not from the image you handed it, or a run that
  worked reports "not found".

`--dest` is the same shape for the destination dialog: the archive on the boot
volume, an empty floppy beside it, the DESTINATION dialog switched to the
floppy with its own Drive button (`SFPUT_DRIVE` — SFPutFile's buttons sit lower
than SFGetFile's, so `SF_DRIVE` misses), and then a read of **both** volumes.
Every output name must be on the chosen volume and none on the archive's. Give
it a small fixture with a folder in it, `derived-Downer.sit`; nothing here is
measuring speed and the phase waits out `EXTRACT_QUIET` at the end.

### What the Finder does with a dropped archive — `interactive.py --drop`

    interactive.py <fixture> --drop --system Sys30.img --emu mv-4M
    interactive.py <fixture> --drop --system System6.hfv --emu mv-4M
    interactive.py <fixture> --drop --system Sys7.img --emu mv-4M

Seven frames: the desktop, the open volume, **Get Info on the application**, a
CONTROL drag to empty space, the archive dropped on the application's icon,
the same after a launch's worth of seconds, and the extraction that follows
when the drop worked — the last one is what says the application was handed
the right FILE rather than merely woken up. `--emu mv-4M` because nothing here
is timed.

The answer, and what it decides, is DECISIONS.md 2026-08-31, *the drop the
Finder does not make*. Three things about running it:

- **The control frame is what makes the negatives mean anything.** Every
  refusal looks exactly like a drag that was never delivered. `drop-4` is the
  archive dragged to empty space; if it did not move, stop reading the run.
- **The phase sets the archive's TYPE with `hattrib`**, because `mkboot.py
  --data` leaves hfsutils' default and a Finder that gates on the
  application's `FREF` list cannot match a type nobody declared. The first
  System 7 run was a false negative for exactly this. `--drop-type '????'` is
  the other half of the wildcard experiment: a type nobody declared, against a
  `FREF` that claims everything.
- **Get Info is taken before the drags**, because a successful drop parks the
  archive on top of the icon the Get Info click is aimed at, and the wrong
  file's Info window looks like the right one.

Icon coordinates live in `FINDER_ICONS`, per system, `archive` alongside
`app`; System 7 opens its volume window near the BOTTOM of the screen, so the
control drag moves up there rather than down.

**What it cannot see.** It photographs; it reads nothing off the volume. A
launch proves the Finder accepted the drop, not that the application was told
WHICH file — nothing in the application reads `AppParmHandle`, so that half
cannot be tested until the receiving code exists.

### Making a segmented Compact Pro archive — `cptsegment.py`

    cptsegment.py --list
    cptsegment.py --map              photograph the application's menus
    cptsegment.py --case edu3        cut a specimen, and read it back
    cptsegment.py --verify           does tools/synth_cptsplit.py still
                                     reproduce the specimens byte for byte?

The only harness here that drives **somebody else's application**. Compact
Pro 1.51 comes out of the corpus through our own CLI, goes onto the boot
volume as MacBinary beside the archive to be cut, and the driver works
`Misc > Segment` with a chosen size. The set lands in
`$UNC_VMAC_HOME/specimens/<case>/` with a `case.json`; it is not committed,
for the reason no fixture is — and it is kept beside the emulator rather
than under `build/`, because the first two specimens were written there and
the next `./ci.sh` ran `make clean` and deleted both.

Why this exists at all is in DECISIONS.md 2026-08-14: nothing documents the
segmented layout, so the specimen IS the documentation, and the application
is the only thing that writes one. `--verify` is what keeps the description
honest: `tools/synth_cptsplit.py` writes sets from that derivation, and it
has to reproduce these ones exactly — a generator validated against nothing
is just a second copy of the reader's assumptions.

Four things it will teach you if you drive another application here:

- **A `--data` copy is invisible to it.** Our own application opens what it
  is handed by name; another one filters Standard File on TYPE, so the
  archive has to arrive as MacBinary with `PACT`/`CPCT` on it. That is what
  `mkboot.py --macbin` is for.
- **Its Standard File is not ours.** The dialog is the application's own
  resource: this one's first row is at y=88 where `interactive.py`'s is at
  137. Clicking ours selected nothing, and the shot showed a dialog with
  Open dimmed — a photograph of a working machine doing nothing.
- **Menu titles have to be measured, not counted.** The first map was one
  menu to the left the whole way along, so every shot was mislabelled and
  the "Misc" photograph was of the View menu.
- **The number of Save boxes is not known in advance** — it is what the
  segment size and the archive decide. The driver stops when the screen
  stops changing rather than counting, because a fixed count either leaves
  a dialog up or types Return into the catalog window afterwards.

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

**It installs by COPYING, not by running the installer.** The download is a
StuffIt archive of two DiskCopy images; disk 1 holds one file, an installer
whose DATA fork is itself a StuffIt archive, and `macextract` unwraps the lot
— so the application, `Text 1`, `PassLock`, the Engine, Magic Menu and
Aladdin's own Preferences file go onto a copy of `System6.hfv` from Linux.
Where each belongs is not guessed: `UnInstall Dlx Files Script`, on disk 2 of
the box, erases `{system}Optimizers:Text 1` and the rest by name. Without
the Preferences file the application stops at a Standard File dialog before
it draws a window.

**Registration, and where the code comes from.** 2.0.1 wants a name, a
**signature drawn in a box** — it will not take OK without one — and a
serial. The code is on the page the download itself is on,
`macintoshgarden.org/apps/stuffit-deluxe-2`: *"A nnnnn (where 'n' = any
number)"*. It is **not** `/apps/stuffit-deluxe`, whose codes `spacesaver.py`
carries for 3.0.7 and 5.x; six of those were tried first and refused, and a
registration wall was written into five files before the maintainer asked
which page (BLOCKERS.md, withdrawn claims). `--personalize` keeps the
registered image, because the application writes the personalization into
its own resource fork — **do not re-run `--install` afterwards**, which
rebuilds the volume from `System6.hfv` and loses it.

**The run is a SCRIPT, not a sequence of clicks.** StuffIt Deluxe 2.0 has its
own scripting language — vocabulary in the application's STR# 257, shapes in
the payload's `Sample Scripts` — and `Scripts ▸ Execute Script…` (**⌘E**, not
the menu item: at y=20 the item never highlights) runs a TEXT/`SIT!` file of
it. `Write Status To` makes the application report what it did, and that
status file comes back with the run:

    Creating new archive: Macintosh:Optimized.sit
    Stuffing items matching: Macintosh:Subject
            (stuffing file: Subject)

So the archive is written by commands whose spelling is Aladdin's, the
control and the optimized pair come from one boot, and a syntax error says
so instead of vanishing.

**Read the image the emulator WROTE.** Mini vMac boots a copy in the
session's temp directory, so mounting the image you handed it reports every
archive missing from a run that made all three.

**`--unstuff` is the oracle.** It boots the image `--make` wrote, deletes the
original subject so what comes back cannot be it, and has Magic Menu unstuff
`Optimized.sit`. For `Text 1` that gives the OPTIMIZED bytes — 594 of them,
no resource fork — which is what makes "correct" definable for a
preprocessor that undoes nothing, and what `tools/run_sitopt.py` grades
against.

**The reversible Optimizer needed a document nothing here had.** `MacPaint
1` carries a `DCMP` and keys on type `PNTG` (the literal is in its `COMP`
resource three times); the 933-fixture corpus has six `sfil` sounds and no
paint document at all. So `--add-paint` puts **MacPaint 2.0** on the same
image — it is on this machine, in a `.sea.hqx` our own engine unwraps — and
`--paint` launches it, drags three strokes across the canvas, saves
`Painting` and keeps the image. `--makepaint` then stuffs that twice,
Optimizer off and on. **Click the icon to launch it**: type-select and ⌘O
renamed the application to `Painting` on the first attempt, because nothing
had launched and the Finder took the keystrokes.

**The last three modules asked for documents, and said which.** Read out
of each `COMP`: `Sound 1` compares the file's type against **`FSSD`** —
Sound Designer II — and then wants an `INFO` 1000 resource; `Photoshop 1`
compares against **`8BIM`**, Photoshop 1.0's own type rather than the later
`8BPS`, and wants an `8BIM` 1000 resource of ten bytes or more whose word
at +8 is a colour mode. A corpus `sfil` sound suitcase and an ImageMagick
PSD were both declined, correctly, before that was read. `--makemods`
builds subjects to those tests — the Photoshop one has a genuine PSD data
fork and a resource fork made to satisfy the module — and all three then
bite, writing 1, 2 and 3 into byte 106.

**Three lessons from those runs, none of them about StuffIt.** The first
attempt installed two of the five Optimizers and the application said so
in the script's status file (*"Optimizer Not Found: Sound 1"*), which is
what `Write Status To` is for. The module names go through the reversible
`/`→`:` swap on the way out of the payload and have to go back: the
Macintosh file is `Photoshop/JPEG Lossy`. And the resource forks this
harness built were **unreadable** — the map was missing its attributes
word, so `Get1Resource` returned NULL and the module declined a subject
built for it; `spacesaver.resources()` parses what `one_resource()` writes
now, which is the check that should have been there first.

**`--unstuff` on the MacPaint archive is the other half of the answer.**
Magic Menu refuses it — *"Items that were encrypted or compressed with an
optimizer or compressor will be skipped. The Engine does not currently
support this. Please use StuffIt Deluxe instead."* — where it unstuffed the
`Text 1` one without comment. That is Aladdin's Engine drawing the same line
this engine draws, and it is why `run_sitopt.py` asserts a refusal for one
and bytes for the other.

**A hierarchical submenu DOES open here, which the note below says it does
not.** `--options` pulls `Magic ▸ StuffIt Options ▸` down ten pixels at a
time: the parent highlights and the submenu draws, to the LEFT because the
parent is near the right edge. That is System 6 and Magic Menu 2.0; the
measured failure is System 7's Translate menu and it stands. There was
nothing in this one worth selecting — compression method, Leave/Delete
Originals, no Optimizer, which is why the application had to run.

What it CANNOT see:

- **whether a real Sound Designer II or Photoshop document behaves the
  same.** Two subjects are built to the modules' own acceptance tests.
- **whether a `DCMP` restores the original.** No module has ever been
  executed here; the refusal is graded as agreement with Aladdin's Engine.
- **whether 3.5.1 would use a 2.0 module.** `--install351` puts `Text 1` in
  both places 3.5 might look, and that application does not launch here.
- **the 512 KB machine.** It boots `mv-4M` throughout.

### Calling an Optimizer module — `dcmptest`, and `sitopt.py --dcmp`

    cmake -B build/dcmptest -S tools/vmac/dcmptest \
          -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
    cmake --build build/dcmptest
    tools/vmac/sitopt.py --dcmp

**What it proves is the calling convention and nothing else.** The probe
opens `{system}Optimizers:MacPaint 1`, takes its `'DCMP'` with
`Get1IndResource` — the module file holds one, and its id is the module's
number rather than 1 — and jumps to `*handle`, which is a `bra.s` over the
sixteen-byte header. Selector **-3** is the cheapest request there is:
every module answers it by copying its own name into the caller's buffer
with `_BlockMove` and writing 1 back, so no file, no callback and no
Memory Manager are involved. It comes back with **"MacPaint 1"** and a 1.

**It is launched AS THE FINDER**, the way `traptest` is, and for a reason
this harness learned the hard way: that volume has a dozen icons by now
and a type-select on it has already renamed an application once. Booting
into the probe needs no navigation. `--dcmp` replaces `Finder` on a COPY
and renames the real one aside.

**What it cannot see:** the data path. A `DCMP` latches the file from the
record it is given at selector -1 and then reads and writes it through the
File Manager, so calling the transform needs that record's layout and a
remnant on disk — neither of which this probe touches (OPEN_ITEMS.md).

### Making an encrypted StuffIt archive — `sitcrypt.py`

    tools/vmac/sitcrypt.py --map                     photograph the menus
    tools/vmac/sitcrypt.py --password swordfish --tag pw9

StuffIt Deluxe 3.5.1 (installed by `spacesaver.py --install351`) writes
StuffIt classic archives with passwords, and this drives it: File ▸ New,
Archive ▸ Stuff… with **Encrypt with password** ticked, then the
password twice. **Those menus are MAGIC MENU's, in the Finder** — the
application itself has never launched on this machine, here or
anywhere else in this tree (BLOCKERS.md, withdrawn claims, 2026-09-28).
It changes nothing about the archives and everything about what else
this image can be asked to do. The archive comes off as MacBinary because the
verifier — `'MKey'` 0 — is in its RESOURCE fork.

It exists because the archive key's fold count was a standing
disagreement between `unar` and XADMaster that no generated file could
settle. Three runs settled it: 8, 9 and 17 characters need 1, 2 and 3
folds, so the rule is ceil(len/8) and **neither reference has it**
(FORMATS.md). `tools/run_crypt.py` replays whatever specimens are
present.

Four things it will teach you, and each cost a run:

- **Shut Down can stall.** With the subject on a second volume, Shut
  Down ejected it and the Finder asked for it back — so the boot volume
  never flushed and the archive came off forty bytes short, with a
  resource map claiming a length the file did not have. One volume.
- **Rows are sixteen pixels apart, not fifteen.** At fifteen the click
  for row 5 landed on row 4 and encrypted the 727 KB application
  instead of the subject — perfectly, which is the sort of success that
  reads as a failure.
- **The invisible files count.** A volume's `Desktop DB` and `Desktop
  DF` are listed by StuffIt's own dialog and sort before anything, so
  row 0 is not your file.
- **The application renames what you type.** "Secret.sit" typed into
  File ▸ New becomes `Secret.sit.sit`.

**The Translate menu's submenus cannot be selected here, and that is the
harness's limit, not the application's.** `--btoa-peek` photographs the
menu and its `btoa/atob ▸` submenu opens correctly; what never happens is
the submenu ITEM highlighting. Three ways in were measured — a diagonal
jump, a sideways entry along the submenu's own row, and stepped motion
ten pixels at a time (specimen tags `btoa`, `btoa2`, `btoa3`) — and in
all three the parent item stays highlighted, the item under the pointer
does not, and the release selects nothing. Plain menus and every button
in every dialog work, so this is hierarchical tracking specifically;
*hypothesis*, unreduced: the Menu Manager wants mouse movement the
emulator's pointer injection does not produce.

That route is gone from the script because of how it failed: with no
picker on screen, the clicks and Return meant for it went to the Finder
and RENAMED the subject to `Subject.ascii` — a plausible-looking
specimen containing the plain subject. `--btoa-drop`, which drove
`DropConvert™` instead, never wrote a file either and never could:
`DropConvert™` converts ARCHIVES between StuffIt and self-extracting
(OPEN_ITEMS.md, part 1). **Neither is the route.** `--btoa-send` is.

### The translator, driven by Apple event — `--btoa-send`

    tools/vmac/sitcrypt.py --btoa-send

**No menu at all.** StuffIt Deluxe 3.5.1's `aete` declares a `translate`
event — `SIT!`/`TRAN`, direct object an alias, `trnm` the translator's
name, `encd` the direction, `dest` where to put the result — and its
`SIZE` -1 is `0xd8e8`, isHighLevelEventAware and localAndRemoteHLEvents
both set. The Apple Event Manager is in System 7.0.1 whether or not
AppleScript is (it is not, on this image), so the submenu is not the only
door and never was.

`tools/aetran/` is the sender: a Retro68 application of about 400 lines
that the harness cross-compiles and copies onto the volume beside the
subject. The Finder opens it — one type-select and ⌘O, the only thing
this mode drives — and everything after that happens inside the
Macintosh, where no coordinate can miss: it finds its own folder through
`GetProcessInformation`, launches StuffIt Deluxe itself with
`LaunchApplication`, sends the event, and writes the reply's `errn` to a
text file called `AEResult` beside itself. The specimen lands in
`$UNC_VMAC_HOME/specimens/sitcrypt/btoasend/`, and the harness grades it
with our own CLI and diffs it against btoa 5.2.1.

Four things it measured, each of which cost a step:

- **The `aete` says what the terms MEAN, not what the handler accepts.**
  Six shapes of the same event were sent in one boot. `dest` as an
  `fss ` naming the not-yet-existing OUTPUT FILE is the only one that
  failed — `errn -1700`, `errAECoercionFail`. Every shape naming an
  existing FOLDER, and every shape naming no destination at all, was
  accepted. The destination is a place, not a name.
- **`encd` is the direction, and its default is DECODE.** The shapes that
  omitted it left a zero-byte `Subject.dec` beside the real output.
- **The translator wraps before it encodes.** `Subject` comes back as
  `Subject.MBin.ascii`: MacBinary first, btoa over that. So the output is
  found by its type and creator (`TEXT`/`asci`) and not by a name — the
  mistake the abandoned menu route made — and the grading takes the two
  layers off separately.
- **It writes the OLDER framing.** `xbtoa Begin` … `xbtoa End`, not
  `xbtoa5`, which is the half of the decoder the Unix reference only
  reaches with `-o` (FORMATS.md, *btoa*).

### Asking Compact Pro about its own cipher — `cptcrypt.py`

    tools/vmac/cptcrypt.py --explore     photograph each step
    tools/vmac/cptcrypt.py               write an encrypted archive with
                                         our cipher, and have Compact Pro
                                         extract it

The arrangement that graded DiskDoubler methods 3-5 (`ddencode.py`),
pointed at the one format whose encryption nothing else reads. It runs
both ways: `tools/synth_cpt.py` writes an archive with the cipher
`src/unc_crypt.c` read out of Compact Pro 1.51's `CODE` 3 and the
application is asked to extract it, and `--make` has the application
encrypt known subjects for this engine to read back. Both agree since
2026-08-23.

    tools/vmac/cptcrypt.py --register "Registered:35427117" --make --probe
    tools/vmac/cptcrypt.py --register "Registered:35427117"

**Encryption is behind the registration**, and Macintosh Garden
publishes one for 1.51 (`Registered` / 35427117). Without it Compact
Pro answers Extract with *"This version of Compact Pro cannot validate
or extract encrypted files"* and the Add dialog's Encrypt checkbox sits
at a negative rect; with it, both work — the code at 0x4864 patches
DITL 312 to bring the checkbox into view.

`--make` is the direction that matters most: the application ENCRYPTS
three known subjects and the archive is kept in
`$UNC_VMAC_HOME/specimens/cptmade/` with a `made.json` saying what went
into it. `tools/run_crypt.py` replays that archive when it is there and
skips loudly when it is not — it is the only encrypted specimen in this
project written by the software that invented the format, and it is
what turned the cipher from a reading into a measurement (FORMATS.md,
*Compact Pro's cipher*).

`--note TEXT` types a comment into **Archive > Note...**, which is what
Compact Pro calls the archive comment, before the archive is saved:

    tools/vmac/cptcrypt.py --register "Registered:35427117" --make \
        --plain --note 'First line.\nSecond line.' --outdir ...

`\n` is a line break in the note. Two things about that dialog, both
measured 2026-08-23: **Return does not press OK** — the field is
multi-line and a Return puts a CR in the text, so the first run typed
its Save, its filename and its quit into a dialog still on screen and
wrote no archive at all — and the OK button therefore has to be
clicked. `--plain` writes the archive unencrypted, which is what a
comment specimen wants: nothing is asked for a password.

Four things it will teach you, and three of them cost a run:

- **The +8 was invisible in the disassembly and obvious in the
  arithmetic.** Data forks of 96, 100 and 103 bytes come out as 104,
  108 and 111 — a constant eight, so a preamble and not a block
  cipher's padding. `--probe` exists to ask exactly that question, and
  three lengths is what it takes to answer it.
- **Every resource fork extracted on that machine comes back
  restamped**, a few dozen bytes in. Not Compact Pro: a corpus archive
  does it too. It is the Finder opening the extracted file's resource
  fork and the Resource Manager writing the map's live fields back. Do
  not debug a cipher with it — compare data forks.
- **The first row of Standard File is not your file.** The boot volume
  has an invisible `Desktop` file that sorts first, and clicking row one
  opened THAT — which the application reported as a file it could not
  read, i.e. exactly what a broken archive looks like.
- **Nothing may be typed blind before the password dialog is on
  screen.** Compact Pro asks for the password when it WRITES, not when
  you click Add, so a Return typed early lands in Standard File and
  walks into a folder — and the archive is saved somewhere you are not
  looking, or not at all.

### Driving our own password dialog — `interactive.py --password`

    tools/vmac/interactive.py --password -o shots fixtures/anything.sit

The fixture argument is ignored: the archive is generated, because
nothing in the corpus is encrypted. It is the encrypted StuffIt classic
one `tools/synth_crypt.py` writes, delivered as MacBinary so that both
forks arrive — which is the point, since that format keeps its password
verifier (`'MKey'` 0) in the archive's **resource fork** and this is the
only phase that exercises the Mac side of reading it.

The walk answers the dialog **wrongly first**, so the retry path is
driven too, and ends by reading the extracted bytes off the volume and
comparing them, so the phase fails on its own rather than on somebody
reading a screenshot. Verified on System 6.0.8: both asks, the second
one saying "That password was refused", and every entry byte-exact.

### Replaying the segment work — `segcheck.py`

    tools/vmac/segcheck.py --list
    tools/vmac/segcheck.py                 # all nine, 4 MB
    tools/vmac/segcheck.py --mem 1M        # the floor target
    tools/vmac/segcheck.py --case cpt-middle

Everything about segmented archives on the Mac was verified once, by
hand, on 2026-08-14. This is those commands written down, which is the
difference between evidence and history: it caught two stale
expectations and one real defect on its first full run (DECISIONS.md).

Two scenarios are worth knowing about because they are easy to get
backwards. **A StuffIt set is checked off the DISK**, not against the
grid: it yields the joined archive, where the fixture's manifest
describes what is inside that archive. **A Compact Pro set is checked
against the grid**, because its reader emits the archive's entries
directly — which is what the manifest lists. Same shape from outside,
opposite oracles.

**`ddseg-real` is the only case whose parts were cut by the application
that defines the format** (added 2026-08-21). DiskDoubler Pro 4.1.1 cut
`ddtf-ddpro411ad1.dd` into two, both are fixtures, and so is the
AppleDouble sidecar holding the original's resource fork — so this case
checks the joined FILE off the Out volume, both forks, against what the
corpus publishes, as well as the grid via `--expect` (a `SPLT` part has
no manifest; nothing but DiskDoubler writes the container). Part 2 goes
on the volume under a name that resembles nothing, because a `SPLT` part
is matched by the 26 identity bytes in its header and never by its
filename.

### The two schemes that are placed by FILENAME — `--named`

`run.py` can drive a StuffIt or Compact Pro set under any names at all,
because those are found by header. It cannot drive a spanned zip or a
`.NNN` split: the names ARE the scheme, and the autotest opens a file
called `archive.sit`. So those two go through Standard File, where the
name comes from the user, and the phase ends on a byte comparison — the
one file the set must produce, read back off the volume the Mac wrote to.

Both sets are built with a stem beginning `A`, and that is not
cosmetic. The phase opens the FIRST ROW of Standard File, the boot
volume's root holds an invisible `Desktop` file, and `Set.z01` sorts
after it while `Blob.001` sorts before — so the split case passed while
the zip case opened `Desktop`, which is not an archive, and the
application correctly said so. **The fourth harness bug in this
directory to photograph as an application bug.** What settled it in one
frame was putting the engine's return code into the alert: `ret=-1
fam=0` said the application had never seen a family at all.

`--chain` and `--wrapped` both compare NAMES on the volume against what
the Linux CLI produces from the same file, and both require the
application to have tidied up after itself — the intermediate layer for
`--chain`, the decoded parts for `--wrapped`. `--chain` is the phase that
found the application had no envelope unwrap at all (BLOCKERS.md), so it
is worth keeping even though it now passes: it is the only thing that
tests the claim README.md makes to users.

**It is also the only harness here that can see a chain at all.** `run.py`
drives the `-DUNC_MAC_AUTOTEST` build, which calls `RunExtract` once; the
unwrap loop is in the interactive application and nowhere else. `--chain`
takes any file, so a specimen for a new envelope is three lines — wrap a
fixture with `tools/synth_wrapped.py`'s `macbinary()`, encode that with
`reference/btoa` or `synth_uu.plain()`, and hand the result to `--chain`.
Pick a payload with no resource fork: the phase compares the Linux CLI's
directory listing, where a fork is a `.rsrc` sidecar the Mac does not have.

**Which reference a phase grades against follows from which build it runs.**
`run.py`, `checkdisk.py` and `os9.py --hfsplus` drive the autotest build and
compare against `macextract x -nr`; `interactive.py` and `os9.py --launch`
drive the shipped application and compare against the CLI with recursion left
on, plus the `Comments` mapping checkdisk.py makes. `expected_names` had the
autotest form until 2026-08-27, and so did os9.py's own reference
(DECISIONS.md).

### Putting a disk in while the Mac is running

`xdnd_insert.c` is a minimal XDND drag SOURCE, built on demand into
`$UNC_VMAC_HOME`. Mini vMac's X11 build accepts a disk at runtime through
exactly one door: its control mode (hold Control) offers magnify, full screen,
reset, interrupt, quit and speed and no open-disk, it is built here with
`NeedRequestInsertDisk 0`, and `ParseOneUri` in `src/OSGLUXWN.c` turns a
dropped `file:` URI into `Sony_Insert1a`. This display has no window manager
and no file manager, so there was nothing to drag from until this.

    cc -o xdnd_insert tools/vmac/xdnd_insert.c -lX11
    DISPLAY=:<n> ./xdnd_insert /path/to/disk.dsk

It finds the emulator window by its `XdndAware` property and exits nonzero if
there is none or the target never asks for the file list — a silent success
would be indistinguishable from a Mac that ignored the disk.

**Fetching the disk-inserted event is what MOUNTS the disk.** A version of the
application that left the queue alone and polled the volume list instead never
saw a volume appear at all. So "did the disk mount" is not a question the
harness can answer by waiting; something has to read the event.

**`Mac.settle` answers "the screen stopped changing", which is not "the
extraction finished".** The progress dialog repaints once per engine callback
— every 8–16 KB of *input* — so on a slow decode two polls land inside one gap
and a running extraction reads as a finished one. Every settle that waits for
an extraction therefore passes `quiet=EXTRACT_QUIET`, a number of SECONDS the
screen must hold still, and it has to exceed the worst repaint gap rather than
the poll interval. Without it `--dest` returned at 33%, read a half-written
floppy, and reported the application had sent the output to the wrong volume.

**Re-measure `PROGRESS_CANCEL` in `interactive.py` whenever the dialog changes
shape.** It is a hard-coded screen coordinate, so a moved button does not make
the step fail — the click lands on dialog background, the extraction finishes
normally, and `3-cancelled.png` is written anyway, showing the progress dialog
instead of the alert. That happened on 2026-08-07 when the DLOG grew 30 points
taller. The constant's comment derives it from the DLOG origin plus the DITL
rect; **check the screenshot actually shows the alert.**

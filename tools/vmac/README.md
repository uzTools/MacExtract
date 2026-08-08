# tools/vmac — running the Mac shell on an emulated Mac Plus

Everything in FORMATS.md and MANUAL_TESTS.md that claims the Macintosh shell
"runs on real System 6" was produced by this harness. It boots the Retro68
application on Mini vMac emulating a **68000 Mac Plus under System 6.0.8 or
System 7.0.1**, extracts one fixture per boot, and cross-checks the result
against the same engine's Linux output.

    tools/vmac/setup.sh                                  # once
    tools/vmac/run.py fixtures/adobenumbers.sit          # 4 MB machine
    tools/vmac/run.py --mem 1M fixtures/adobenumbers.sit # 1 MB floor target
    tools/vmac/run.py --system Sys7.img ...              # the System 7 tier

`--system` picks the boot system: `System6.hfv` (6.0.8, the floor target) or
`Sys7.img` (7.0.1). System 7 is where `SFReply.vRefNum` becomes a working
directory and the Process Manager starts honouring the `SIZE` partition, so it
is a different set of code paths, not just a different splash screen. Run the
System 7 tier at 4 MB.

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
| System 6.0.8, 1 MB, 53 fixtures | `run.py --mem 1M --list sample.txt` | ~5.1 s per fixture, one boot each |
| System 7.0.1, 4 MB, 53 fixtures | `run.py --system Sys7.img --list sample.txt` | ~5.1 s per fixture, one boot each |
| Mac OS 9.2, 13 fixtures | `os9.py --list os9sample.txt --launch` | tens of minutes — one full PowerPC boot per fixture |

Run the two Mini vMac tiers in parallel if you have the cores; do NOT run
anything else alongside `os9.py`, which uses `build/rel/unclassic` as its
oracle and will lose it to `./ci.sh`'s `make clean`.

## What the pieces do

| file | role |
|---|---|
| `setup.sh` | fetch + build the emulator, the ROM and a System 6.0.8 image into `$UNC_VMAC_HOME` (default `~/.cache/unclassic/vmac/`) |
| `mkboot.py` | strip that image to System + Finder and make it boot straight into the application |
| `run.py` | build the disks, boot, screenshot, decode, check |
| `interactive.py` | drive the real UI (SFGetFile, progress dialog, Cancel, Cmd-.) and photograph each step |
| `os9.py` | boot Mac OS 9 on emulated PowerPC, launch the application from the keyboard, and check both forks of what it wrote — see below |
| `os9probe.py` | diagnostic: which input primitives actually reach the Mac OS 9 guest? Not part of any suite |
| `os9sample.txt` | the fixtures replayed on Mac OS 9 — one per format, since each costs a whole boot |
| `mountcheck.py` | boot a system image with disks attached and photograph the desktop — "does this mount?", and "does this system boot at all?" |
| `mkapmdisk.py` | build an Apple-partitioned transfer disk that Mac OS on PowerPC will mount |
| `checkdisk.py` | verify a run by READING its Out volume — both forks, and the names the on-screen grid cannot carry |
| `mkcollide.py` | build an archive whose names collide on HFS, and verify what `BumpName` did with them — nothing in the corpus collides |

`tools/quickdraw-repro/` is a sibling that reuses `mkboot.py` and this
directory's `Display`/emulator plumbing to answer one narrow question about
System 6's Toolbox. It is where `mkboot.py --finder` came from.

The verification halves live one directory up because they are useful on their
own: `tools/decode_grid.py` (screenshot → eight numbers) and
`tools/vmac_check.py` (those numbers vs. the oracle).

## Why it works the way it does

**Results come off the SCREEN — and, since 2026-08-02, off the disk as well.**
The app paints its results as a black/white bit grid (three calibration
squares, a sync word, eight 32-bit values) which a screenshot captures exactly;
see `at_report()` in `mac/unclassic_mac.c`. That is what `run.py` decodes.

The reason it was the *only* channel used to be a claim that Mini vMac's
write-back is "lazy and partial — it will commit one fork of a file and not the
other", so extracted files could not be read back on the host. **That does not
reproduce and is withdrawn** (BLOCKERS.md): the whole sample was replayed with
`--keep-disks` and every Out volume read back byte-exact, both forks, names
included — 53/53. See "Checking a run off the disk" at the end of this file.

The grid stays: it is proven, it needs nothing of the volume, and it reports
liveness and setup failures that a disk cannot. What it cannot do is carry a
NAME, which is why `checkdisk.py` now exists beside it.

**The app is the boot shell.** The boot blocks' shell name (offset 0x1A) is
rewritten from `Finder` to `unclassic`, so the ROM hands control straight to
the application. No Finder, no synthetic double-click, no mouse automation —
the machine boots into the test and nothing else runs.

That is a materially different environment, and it is worth naming: nothing
mounts disks (see BLOCKERS.md), and no other process competes for the heap.
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
Still true and still the trap: **do not poll every few seconds**, because
decoding a 512x342 grid in Python steals the CPU from the emulator you are
timing.

**Wall-clock time is not Mac Plus time — except in a 1x build.** `setup.sh`
produces four emulators, because RAM size and speed are both compile-time
options. `mv-4M` and `mv-1M` run *all out*, as fast as the host allows, which
is what the fixture sweeps use because correctness does not depend on speed
and 53 fixtures x 2 memory sizes at Mac Plus speed would take all day.
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

**This box has one core.** At 1x the emulator paces itself against real time,
so anything else CPU-heavy — `./ci.sh`, a corpus sweep — inflates the number
you are measuring. Run timing alone.

**`interactive.py` is not self-checking, by design.** It guarantees the same
clicks in the same order and writes a numbered screenshot per step; judging
them is the reader's job. Two lessons are baked into it, both of which
produced confident-looking nonsense first:

- *Press buttons with Return, not coordinates.* Clicking SFGetFile's Open at a
  measured point hit **Drive** one row up, switched to an empty volume, and
  made every later screenshot meaningless while still "succeeding".
- *Set X input focus explicitly.* With no window manager nothing assigns it,
  so key events go to the root window. Mouse clicks are delivered by position
  and work anyway — which makes it look like the Mac ignores one particular
  key rather than receiving none.

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
goes — and `--keep-boot` is off by default because each copy is 2 GB.

**The Finder is driven from the keyboard.** The pointer does not work in this
guest: `os9probe.py` measured five mouse primitives at exactly 0.0000 effect
each, and located the cursor only ever in screen corners, never at a requested
position. Typing selects an icon by name, Cmd-Down opens it, Cmd-Q quits — no
coordinates, no double-click threshold. `os9probe.py` is kept as a diagnostic;
run it if clicking or typing ever appears to stop working, because it answers
"which link broke?" in one boot instead of inferring it from a non-event.

**`--hfsplus` writes to a volume the host cannot read.** The boot volume is
HFS+; renaming it to `Out` in the Finder is enough to point the *autotest*
build at it, since that build finds its volumes by name. The result comes back
through `at_report_file()` — a small file on the plain-HFS input volume
carrying the same values `at_report()` would paint, plus every output name,
because the framebuffer grid is invisible on a 32-bit screen. That the output
really landed on HFS+ is checked by mounting the volume's HFS *wrapper*: if
the files were on plain HFS they would be visible there, and they are not.

**The result is checked off the disk image, not off the screen.** Mini vMac
needs the on-screen CRC grid; QEMU does not, because the transfer volume is a
plain host file. After the emulator exits, `verify_output()` lifts the
Apple_HFS partition out, mounts it with hfsutils, pulls each extracted file
off as MacBinary (`hcopy -m`, which is the only way to get a resource fork
through hfsutils) and compares **both forks byte for byte** against
`unclassic x -nr`. A mismatch names the file and the fork; a volume the guest
never flushed fails to mount rather than passing quietly.

`mkapmdisk.py` clones its partition map and drivers from a disk Mac OS 9
already mounts and repoints only the `Apple_HFS` entry. A map built by hand
from the format documentation — correct-looking DDR, correct-looking entries,
status word copied off a real disk — was silently ignored: no volume, no
error, nothing to debug. Cloning a known-good head worked first time.

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

**53/53 byte-exact**, both forks, names and folder structure included, over
the committed sample — including `derived-RWAsm_Folder.sit` at 38 files and 73
forks, an 8-bit `spinning brain ƒ` folder, a MacRoman `Appé`, and a
`.DS_Store`.

`checkdisk.py` identifies each run's fixture from the `in.dsk` beside the
`out.dsk`, so it needs no bookkeeping, and it feeds the reference extraction a
copy named `archive.sit` — the name the Mac saw — because gzip and .Z derive
their output name from the archive's filename.

Two hfsutils traps it hit, both worth knowing before writing anything similar:
`hls` **hides names beginning with a dot** unless given `-a`, and every path
argument must be encoded as **MacRoman**, not UTF-8, or any 8-bit name is a
file that does not exist.

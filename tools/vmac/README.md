# tools/vmac — running the Mac shell on an emulated Mac Plus

Everything in FORMATS.md and BLOCKERS.md that claims the Macintosh shell
"runs on real System 6" was produced by this harness — on an emulator.
MANUAL_TESTS.md is the complement: what only silicon can answer. It boots the Retro68
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
| System 6.0.8, 1 MB, 55 fixtures | `run.py --mem 1M --list sample.txt` | ~5.1 s per fixture, one boot each |
| System 7.0.1, 4 MB, 55 fixtures | `run.py --system Sys7.img --list sample.txt` | ~5.1 s per fixture, one boot each |
| Mac OS 9.2, 13 fixtures | `os9.py --list os9sample.txt --launch` | tens of minutes — one full PowerPC boot per fixture |

Run the two Mini vMac tiers in parallel if you have the cores — **safe since
2026-08-15**, and it was not before: `Display` looked for a free X display by
testing `/tmp/.X<n>-lock` and then starting Xvfb on it, which is check-then-act.
Two runs started together both chose `:90`, the loser's Xvfb died of the taken
lock, and its readiness probe then succeeded against the WINNER's server — so
both runs drew on one display and screenshotted each other's emulator. Three
fixtures "failed" with another run's numbers before anyone noticed the numbers
belonged to a different archive. Xvfb now picks the display itself
(`-displayfd`) and reports it back. Do NOT run
anything else alongside `os9.py`, which uses `build/rel/unclassic` as its
oracle and will lose it to `./ci.sh`'s `make clean`.

## What the pieces do

| file | role |
|---|---|
| `segcheck.py` | **replay every segmented-archive scenario in one command** — the four joining schemes, parts inside envelopes, and a chained file, across both harnesses |
| `setup.sh` | fetch + build the emulator, the ROM and a System 6.0.8 image into `$UNC_VMAC_HOME` (default `~/.cache/unclassic/vmac/`) |
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
| `superdisk.py` | grade SuperDisk! with its own self-extractors, and `--on-mac`, which replays both payloads through our application |
| `spacesaver.py` | Aladdin's **SpaceSaver**, off the StuffIt Deluxe 5.0.1 CD. 3.5.1 runs; 5.0 does not run on 7.0.1. `--layout` reads the format out of it without booting anything — see below before spending a boot on it |
| `sdcompress.py` | the other half: Alysis's 1991 **SuperDisk! control panel**, which COMPRESSES. It wrote the five specimens the single-file container was derived from, and `--verify` re-grades them |
| `maclha.py` | **MacLHA 2.00**, out of the corpus (`derived-MacLHa_2.00.sit`), driven to write a `.lzh` holding a file with a real resource fork — the specimen no MacLHA archive in reach is. `--setup` builds the volume, `--make` drives the application (keyboard where it has a shortcut; its Header and Type menus are HIERARCHICAL and cannot be used here, and nothing needs them because `MacBinary` is already checked), `--check` grades both forks with our CLI |
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

**The app is the boot shell.** The boot blocks' shell name (offset 0x1A) is
rewritten from `Finder` to `unclassic`, so the ROM hands control straight to
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
the failure pattern is what is measured. The short 4 MB runs are a different
regime and `--poll 3` is fine for them (`timing.txt` uses it).

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

**This box has one core.** At 1x the emulator paces itself against real time,
so anything else CPU-heavy — `./ci.sh`, a corpus sweep, a second
`interactive.py` — inflates the number you are measuring. Run timing alone.

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
    tools/vmac/nowcompress.py --verify    # decode them, check against the input
    tools/vmac/nowcompress.py --adjudicate SEA.bin ARCHIVE   # see below

The compressor is **Now QuickFiler**, whose menu has Compress ▸ Faster/Smaller
and Archive ▸ Faster/Smaller. Specimens land in
`$UNC_VMAC_HOME/specimens/now/<case>/` with the inputs beside them and a
screenshot per step; `tools/run_now.py` picks them up if they are there and
skips them with a message if they are not.

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
  ArcMac header's has bit 0x40 of the high byte set — `invisible` — so the
  first attempt put the application on the volume where the Finder would not
  show it. The disk read "112K in disk, 1 item", which looks like a failed
  copy and is not.
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
    tools/vmac/spacesaver.py --idlespec       enrol the disk, idle, shut down
    tools/vmac/spacesaver.py --layout         read the container out of the
                                              installed panel and engine
    tools/vmac/spacesaver.py --pkg            read AppleLink .pkg's recogniser
                                              out of the translator beside it

Every mode from `--specimen` on ends with Special > Shut Down (the general
rule at the top of this file): `ssenrolled.hfv`, made before that rule was
followed here, does not boot.

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

What it cannot see: whether any of this describes a real compressed file.
Nothing here has produced one, so every field is read from the writer, not
from output.

**Nothing has made SpaceSaver compress anything**, and the modes above are
the attempts: the panel's `small` name rule (`--specimen`), the same with
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

## Grading SuperDisk! with SuperDisk! — `superdisk.py`

Nothing outside the two corpus archives reads the format, so the only oracle
it has is the archives themselves: both are self-extracting applications.
`superdisk.py` is the same bargain `nowcompress.py --adjudicate` makes.

    tools/vmac/superdisk.py --list                    what the corpus holds
    tools/vmac/superdisk.py --adjudicate FIXTURE.hqx  run it, compare forks

The archive is unwrapped from its envelope with our own CLI, rebuilt as
MacBinary, put alone on a 25 MB volume and launched under System 7; its "Save
the expanded file as:" box is accepted with Return, and every fork it wrote is
read back off the image with `hfsutils` and compared with `unclassic x`.
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

### Replaying a SuperDisk! archive through OUR Mac application

`run.py` grades against an oracle manifest and this format has none, so the
two archives are read off the grid directly, exactly as the ArcMac specimens
are. They are payloads rather than fixtures, so unwrap them first:

    unclassic x -nr -o /tmp/sd fixtures/alysis-disk-expander-12.hqx
    tools/vmac/run.py --pngdir /tmp/p "/tmp/sd/Disk Expander .X"
    tools/decode_grid.py "/tmp/p/Disk Expander .X.png"

`run.py` will report FAIL — "no oracle manifest" — and that is the harness
saying it cannot grade, not a result. The grid is the result; compare it with
the same engine's Linux aggregate:

    python3 -c "import sys; sys.path.insert(0,'tools'); \
      from vmac_check import aggregate_dir; print(aggregate_dir('DIR'))"

over a `unclassic x -nr --forks hidden` of the same payload. Both archives
matched at 4 MB and at 1 MB on 2026-08-20; the numbers are in FORMATS.md,
"SuperDisk! on the Mac".

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

**The Finder is driven from the keyboard.** The pointer does not work in this
guest: `os9probe.py` measured five mouse primitives at exactly 0.0000 effect
each, and located the cursor only ever in screen corners, never at a requested
position. Typing selects an icon by name, Cmd-Down opens it, Cmd-Q quits — no
coordinates, no double-click threshold. `os9probe.py` is kept as a diagnostic;
run it if clicking or typing ever appears to stop working, because it answers
"which link broke?" in one boot instead of inferring it from a non-event.

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

**55/55 byte-exact**, both forks, names and folder structure included, over
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

## On-demand probes — the `-D` switches and the one-off harnesses

Every switch below rebuilds the autotest application with an extra define and
answers one question the normal replay cannot. None is part of any suite; each
is run by hand when the question comes up again. **A `-D` the CMakeLists does
not know is silently ignored** — `run.py` passes it through the environment and
CMake drops what it has no rule for, so a probe can "work" and change nothing.
Check that its numbers actually moved before believing them.

Results are not repeated here; each line says where they live.

| switch | answers | where the result is |
|---|---|---|
| `UNC_AT_BUDGET` | why an entry was refused: over budget, or `NewPtr` failed | DECISIONS.md 2026-08-06, OPEN_ITEMS.md section 5 |
| `UNC_AT_HANDLES` | does `MoveHHi` move an engine block, and does it help | OPEN_ITEMS.md section 5 (do-not-retry) |
| `UNC_AT_INTERLEAVE` | do reads return zeros while output is written to the same volume | BLOCKERS.md *Withdrawn claims* |
| `UNC_AT_SAMEVOL` | does extraction onto the archive's own volume work | DECISIONS.md 2026-08-02 |
| `UNC_AT_WD` | is `SFReply.vRefNum` handled as a System 7 working directory | DECISIONS.md 2026-08-01 |
| `UNC_AT_CANCEL` | does an aborted entry leave anything behind | BLOCKERS.md, MANUAL_TESTS.md checklist |
| `UNC_AT_NOHIDECURSOR` | is `HideCursor()` before painting the grid necessary | yes — BLOCKERS.md; two things must be right before the test means anything: the pointer must be INSIDE the emulator window (at (144,129) on the 800x600 Xvfb) and the drag must cross cell CENTRES, since a path between rows disturbs nothing. `UNC_VMAC_PARK` overrides the parking position |
| `UNC_AT_PROGRESS` | how fast is the engine actually going, mid-run | BLOCKERS.md "Timing on a 7 MHz Mac Plus" |
| `UNC_MAC_SLURP_ARCHIVE` | rebuilds the old read-whole-archive-into-RAM path | DECISIONS.md 2026-08-02 |
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
| `nfiles`, `ret`, `sumDataCRC`, `peak heap` | addresses of the 4 largest live blocks, biggest first |
| `errors` | `MaxBlock()` at the first refusal |
| `totalDataLen` | application zone bottom (`ApplicationZone()`) |
| `sumRsrcCRC` | 1 = over budget, 2 = `NewPtr` returned NULL |
| `totalRsrcLen` | `ApplLimit` |

`FreeMem()` minus `MaxBlock()`, both sampled **at the refusal**, is the
fragmentation; sampling free heap at the start of the run does not give it, and
one such inference has already had to be corrected. Earlier revisions carried
the refused size, free-at-refusal and held-at-refusal instead — those figures
are in DECISIONS.md 2026-08-06; swap them back by editing the `UNC_AT_BUDGET`
block if a re-run needs them.

It reports FAIL by construction, because the overwritten slots no longer match
the oracle. **Read the numbers, not the verdict.**

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

    sed -i 's/4096 \* 1024, 400 \* 1024/600 * 1024, 400 * 1024/' mac/unclassic.r
    run.py --system Sys7.img fixtures/derived-KeyGraphics.sit
    run.py                   fixtures/derived-KeyGraphics.sit
    os9.py fixtures/derived-KeyGraphics.sit -o <dir> --hfsplus --expect-refusal
    git checkout mac/unclassic.r        # the edit is temporary, on purpose

A partition big enough to launch and too small for a 512 KB Arsenic block,
against a fixture that needs ~656 KB and passes at 4 MB. `--expect-refusal`
makes the run self-checking: it passes only when the Linux engine DOES extract
the fixture, the Mac writes nothing, the archive returns `UNC_OK`, and an entry
is counted as refused — without that first condition a negative test would pass
just as happily on an empty archive. Three-system table in FORMATS.md.

### Forcing a memory refusal on screen

The `SIZE` edit above is the wrong instrument for this one, and finding that
out cost four runs. A partition is only enforced under MultiFinder — System
7 and up — and `interactive.py`'s Standard File clicks are calibrated for
System 6; on System 7 they select the wrong item and the application answers
`UNC_ERR_FORMAT` about a file that is not an archive. That frame looks like
a code failure and is not.

Cap the budget instead, in a throwaway build, on the machine the harness can
drive:

    sed -i 's/ma.budget = freenow - reserve;/ma.budget = 150000L; (void)reserve;/' \
        mac/unclassic_mac.c
    interactive.py --emu mv-4M -o /tmp/alert fixtures/derived-AuthoRize_2.0.sit
    git checkout mac/unclassic_mac.c    # temporary, on purpose — wrap it in a trap

The alert is in `2-extracting.png`: the default phase clicks Cancel at a
fixed time, and a run that fails BEFORE then leaves its result alert up in
that frame. Photographed 2026-08-24: *Needs 72K more memory. Give unclassic
more in Get Info.*

**When a frame is ambiguous, make the alert say which branch drew it.**
Temporarily replacing the generic `ret != UNC_OK` branch with one that
`PStrCatNum`s `ret`, `gShortBy`, `gShortPiece`, `entries` and `errors` ended
three runs of guessing in one frame — `entries = 0` said the archive had
never been opened, which no amount of staring at the shipped wording could
have told anyone.

### Driving the real UI

    interactive.py                  # progress dialog, Cancel, Cmd-., at 1x
    interactive.py --e2e            # Finder desktop: double-click launch, SFGetFile,
                                    # volume navigation, an extracted APPL launching
    interactive.py --segments       # the "locate part N" alert for a split archive
    interactive.py --named zip      # a spanned zip set, opened through Standard File
    interactive.py --named split    # a plain .NNN split, likewise
    interactive.py --chain          # .sit.hqx: do ALL the envelope layers come off?
    interactive.py --wrapped        # a set whose parts are each in an envelope
    interactive.py --wd             # output lands in the archive's folder, not at /
    interactive.py --dest           # output lands on the volume the user CHOSE
    interactive.py --diskswap       # insert the missing part's disk mid-run

Run them one at a time (see "This box has one core", above).

`--e2e` leaves the **Finder** in place instead of installing the application as
the boot shell, which is the only way to launch the application the way a
person does and the only way to launch what it extracted. Both runs photograph
every step, and `docs/screens/` comes from here.

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

### Making an encrypted StuffIt archive — `sitcrypt.py`

    tools/vmac/sitcrypt.py --map                     photograph the menus
    tools/vmac/sitcrypt.py --password swordfish --tag pw9

StuffIt Deluxe 3.5.1 (installed by `spacesaver.py --install351`) writes
StuffIt classic archives with passwords, and this drives it: File ▸ New,
Archive ▸ Stuff… with **Encrypt with password** ticked, then the
password twice. The archive comes off as MacBinary because the
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
specimen containing the plain subject. What is left is `--btoa-drop`,
which uses `DropConvert™` from the `Drag & Drop Applications` folder
instead: its `Convert… ⌘C` needs no menu tracking, its picker takes the
subject via Add, and it is reached entirely by keystroke and button.
**It does not produce a file yet** — Convert closes the dialog and
nothing is written anywhere on the volume — so the independent btoa
specimen is still outstanding (TESTING.md, *btoa*).

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
    tools/vmac/segcheck.py                 # all seven, 4 MB
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

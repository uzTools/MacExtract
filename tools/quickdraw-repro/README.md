# Does QuickDraw bomb after File Manager activity on System 6?

**No.** Across twelve configurations on a real System 6.0.8 Mac Plus under
Mini vMac, every QuickDraw call succeeded with `MemError() == 0`, including
every call made after 64 KB of File Manager writes, a read-back and a
catalogue walk.

This directory is the reproduction that settles it.

## What was claimed

`BLOCKERS.md` carried this, filed under *real test-harness lessons (not app
bugs)*:

> **QuickDraw drawing (NewWindow/EraseRect) bombs "out of memory" when called
> after any File Manager activity**, despite megabytes free — so the result
> grid is written by poking `qd.screenBits` directly.

It was never reduced to a reproduction, and its classification hid how much it
mattered. If it were true as stated the shipped interactive application would
be broken, because its whole path is SFGetFile (File Manager) → a progress
dialog (QuickDraw) → a result alert (QuickDraw). The claim also arrived in
commit `22e806b`, whose headline root cause ("Retro68's `HOpen` glue is
broken") was later **withdrawn** as confounded — during that period every File
Manager open was silently failing, so nothing observed alongside it can be
taken at face value.

## Results

System 6.0.8, Mac Plus (68000), Mini vMac 36.04, Retro68 `335fa54f6d`, one
boot per row. `FREE` is `FreeMem()` in KB at startup; `ME` is `MemError()`
sampled immediately after each `NewWindow`.

| startup | boot shell | RAM | FREE at init | probes 1-8 | verdict |
|---|---|---|---|---|---|
| MaxApplZone + 12x MoreMasters | the application | 4 MB | 3873 K | all pass, `ME=0` | PASS |
| MaxApplZone + 12x MoreMasters | the application | 1 MB | 801 K | all pass, `ME=0` | PASS |
| MaxApplZone + 12x MoreMasters | the Finder | 4 MB | 3873 K | all pass, `ME=0` | PASS |
| MaxApplZone + 12x MoreMasters | the Finder | 1 MB | 801 K | all pass, `ME=0` | PASS |
| **no MaxApplZone, no MoreMasters** | the application | 4 MB | **2 K** | all pass, `ME=0` | PASS |
| **no MaxApplZone, no MoreMasters** | the application | 1 MB | **2 K** | all pass, `ME=0` | PASS |
| **no MaxApplZone, no MoreMasters** | the Finder | 4 MB | **2 K** | all pass, `ME=0` | PASS |
| **no MaxApplZone, no MoreMasters** | the Finder | 1 MB | **2 K** | all pass, `ME=0` | PASS |
| MaxApplZone, **no MoreMasters** | the application | 4 MB | 3876 K | all pass, `ME=0` | PASS |
| MaxApplZone, **no MoreMasters** | the application | 1 MB | 804 K | all pass, `ME=0` | PASS |
| MaxApplZone, **no MoreMasters** | the Finder | 4 MB | 3876 K | all pass, `ME=0` | PASS |
| MaxApplZone, **no MoreMasters** | the Finder | 1 MB | 804 K | all pass, `ME=0` | PASS |

The eight probes, in order, are: QuickDraw *before* any File Manager call (the
control); the File Manager work itself; **QuickDraw immediately after it — the
claim**; eight interleaved File-Manager-then-QuickDraw rounds; the same while
holding a 200 KB non-relocatable `NewPtr`, as the application does with the
slurped archive; `GetNewDialog` + `DrawDialog`, which is the route the shipped
application actually takes; `EraseRect` on the Window Manager port, named in
the claim; and a final window left on screen so the reader can see QuickDraw
output for themselves.

## What this means for the two hypotheses that were suggested

- **Master-pointer heap fragmentation** (the classic explanation for an
  allocation failing with megabytes free) is not it. `MaxApplZone` and
  `MoreMasters` were already in the application when the claim was made
  (`a707db3`), so they cannot be what was missing — and removing them does not
  produce the failure either. The `no MaxApplZone` rows are the strongest
  evidence: the heap has not been grown at all, `FreeMem()` reports **2 KB**,
  and QuickDraw still allocates every window without error, because the Memory
  Manager simply grows the zone on demand.
- **Replacing the Finder** is not it either. The autotest build runs as the
  boot shell, which does change the environment materially — nothing mounts
  disks, for one (BLOCKERS.md) — but the `the Finder` rows launch the same
  binary by double-clicking it from a normal Finder desktop and behave
  identically. On System 6 without MultiFinder that is less of a difference
  than it sounds: launching an application unloads the Finder, so the heap it
  inherits is nearly the same, and the two columns' `FreeMem()` figures agree.

So the claim does not reproduce, and neither proposed cause is the cause.
What actually happened in that session is not recoverable — the working
directory it ran in was never committed — and it is not worth chasing further.
The correct conclusion is the narrow one: **there is no reason to avoid
QuickDraw after File Manager activity on System 6.**

`at_report()` in `mac/unclassic_mac.c` still pokes the framebuffer, and still
should: it must be able to report a result even when the machine is in a state
where the Toolbox is not to be trusted, it needs no allocation and cannot
fail, and it is the only channel that survives a bomb. That is now its reason,
rather than a QuickDraw bug that does not exist.

## How the reporting works

The program cannot use QuickDraw to report on QuickDraw, so it writes its log
by poking the 1bpp framebuffer through its own 5x7 font. Two consequences
worth knowing:

- The top eight scan lines carry one **marker square** per completed probe.
  System 6's system error dialog is centred and cannot reach them, so if the
  machine bombs the marker bar still says which probe was running. A log line
  only appears once its probe *returns*; a marker goes down as soon as the
  previous one does.
- `decode_log.py` reads the log back to ASCII by matching each glyph against
  the same font table, parsed out of `qd_repro.c` so the two cannot drift.
  That makes the sweep self-checking; the screenshots remain the primary
  evidence, and a bomb or a Sad Mac is obvious in them at a glance.

## Build and run

```sh
tools/vmac/setup.sh                     # once: emulator, ROM, System 6.0.8
tools/quickdraw-repro/run.py            # all twelve configurations
tools/quickdraw-repro/run.py --variant default --shell app --mem 1M
tools/quickdraw-repro/run.py --inspect  # also photograph the Finder desktop
```

Screenshots land in `qd-repro-shots/`, 3x upscaled. `run.py` prints the
decoded log and a PASS/FAIL per configuration and exits non-zero if any fail.

To build the application alone, without the emulator:

```sh
cmake -B build -S tools/quickdraw-repro \
  -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
cmake --build build
```

Mount `build/qd_repro.dsk` in any Mini vMac with a Mac Plus ROM and a System
6.0.8 boot disk and double-click the application.

The Finder-launched mode needs `mkboot.py --finder`, which leaves the boot
blocks alone and puts the application at the volume root. `VOLUME_ICON` and
`APP_ICON` at the top of `run.py` are the double-click coordinates, measured
off `--inspect` screenshots; they are the first thing to re-measure if that
mode ever stops working.

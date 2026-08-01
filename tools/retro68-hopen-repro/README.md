# Retro68 hierarchical File Manager glue — System 6 conformance test

A standalone Retro68 application that compares Retro68's `HOpen` / `HOpenRF` /
`HOpenDF` glue against hand-filled `PBHOpenSync` param blocks, on a real
System 6.0.8 Mac Plus.

It exists because unclassic's Mac shell was, for a while, believed to be broken
by "Retro68's `HOpen` glue returns `noErr` but never writes back the refNum".
**That claim does not reproduce.** This program is the evidence for withdrawing
it — see `DECISIONS.md` in the repository root — and doubles as a regression
test for the glue.

Case 11 was added on 2026-08-01 for a second reason. The upstream write-up in
`ISSUE.md` claimed that `HOpenDF` lacks a `paramErr` fallback "unlike the
non-hierarchical `OpenDF` beside it". That was a misreading: the fallback is in
`FSOpen`, and `OpenDF` calls `PBOpenDFSync` bare exactly as `HOpenDF` does.
Rather than re-read `glue.c` a third time, case 11 runs plain `OpenDF` on the
machine — and it fails identically. **The bug is two functions, not one.**

## Results

System 6.0.8, Mac Plus (68000), Mini vMac 36.04, Retro68 `335fa54f6d`:

| # | call | result | verdict |
|---|------|--------|---------|
| 1 | `HOpen`, stack pre-dirtied | `err=0 ref=378 eof=512 got=4` | ok |
| 2 | `HOpen`, stack pre-zeroed | `err=0 ref=378 eof=512 got=4` | ok |
| 3 | `PBHOpenSync`, `ioMisc=NULL` | `err=0 ref=378 eof=512 got=4` | ok (control) |
| 4 | `PBHOpenSync`, `ioMisc=junk` | `err=0 ref=378 eof=512 got=4` | ok |
| 5 | `HOpen`, real vRefNum, read | `err=0 ref=378 eof=512 got=4` | ok |
| 6 | `HOpen`, real vRefNum, write | `err=0 ref=378 eof=512 got=4` | ok |
| 7 | `HOpenRF`, real vRefNum, write | `err=0 ref=378 eof=0 rdErr=-39` | ok (no resource fork) |
| 8 | `HOpenDF`, real vRefNum, read | `err=-50` | **bug** |
| 11 | `OpenDF`, plain, default volume | `err=-50 ref=2` | **bug** |
| 9 | `HOpen`, other volume | `err=-43` | ok, matches 10 |
| 10 | `PBHOpenSync`, other volume | `err=-43` | ok, matches 9 |

`HOpen` writes the refNum in every case and agrees with a hand-written param
block everywhere. Cases 9/10 look for `System` at the root of the boot volume,
where it does not live (it is inside the System Folder), so `fnfErr` is correct
— the point is that glue and param block return the *same* thing.

Case 11 addresses the same file, on the same default volume, that cases 1-4
open with `err=0`, so its `paramErr` is the `_OpenDF` trap being absent rather
than anything about the file. Both `OpenDF` and `HOpenDF` are unusable on
System 6.

**Run it the way this table was produced**: the application on the root of a
volume, launched by double-clicking it, so the default directory is that root.
Cases 5-10 address `fsRtDirID` explicitly and report `fnfErr` instead if the
application is installed elsewhere — as the boot shell, for instance, where the
default directory is the System Folder. Cases 1-4 and 11 use the default
directory and are unaffected.

The two real (minor) findings are described at the top of `hopen_repro.c` and
in `ISSUE.md`, which is a ready-to-post upstream issue.

## Build

```sh
cmake -B build -S . \
  -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
cmake --build build
```

Produces `build/hopen_repro.dsk` (an 800K HFS image), plus `.APPL` and `.bin`.

## Run

Mount the image in Mini vMac next to a System 6.0.8 boot disk and double-click
the application. It creates its own 512-byte test file next to itself, so it
needs nothing else on the disk, and prints one line per case.

`tools/vmac/setup.sh` puts a suitable Mini vMac, a Mac Plus ROM and a System
6.0.8 image in `build/vmac/`; any Mini vMac with a Mac Plus ROM works. Unlike
the fixture replays, this one has to be read off the screen by eye — it prints
text rather than the machine-readable grid `tools/vmac/run.py` decodes.

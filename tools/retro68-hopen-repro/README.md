# Retro68 hierarchical File Manager glue — System 6 conformance tests

Five standalone Retro68 applications.

**`iomisc_repro.c` is the one that goes upstream** (`ISSUE.md`): Retro68's
`HOpen`/`HOpenRF`/`HOpenDF` glue leaves `ioMisc` as stack garbage, and the File
Manager writes a 524-byte access path buffer through it. Measured 2026-10-13,
Mac Plus under Mini vMac:

| case | System 6.0.8 | System 7.0.1 |
|---|---|---|
| 1 `PBHOpenSync`, `ioMisc = NULL` (control) | 0 longs changed | 0 |
| 2 `PBHOpenSync`, `ioMisc = &decoy` | 131 | 3 |
| 3 `HOpen`, `&decoy` left on the stack | **131** | **3** |

**`glue.patch`** is the fix offered upstream, against multiversal's
`custom/glue.c` (`28eac84`): `ioMisc = NULL` in the three H-variants. It is
the line variant 4 of `m10-variants.patch` measured, and is not otherwise
built.

**`m10-variants.patch`** applies to commit `014ed25` and switches what the
M10-era shell opens files with (`M10VAR` in `mac/m10variant.h`). It is the
evidence that `ioMisc` is what broke M10: the verbatim glue copy fails 0/4,
the same copy with `ioMisc = NULL` passes 4/4 (DECISIONS.md, *the bug was the
footnote*). Run it with that commit's own `tools/vmac/run.py`, its CLI copied
to `build/rel/` and the fixtures linked into its `fixtures/`.

**`glue_repro.c` is the second one that goes upstream**
(`ISSUE-glue-audit.md`, filed as Retro68 #322): 122 lines calling the REAL
`GetWDInfo`, `SetFInfo`, `HSetFInfo` and `HOpen`, so it must be linked
against the glue being reported on. **`mkgluelib.sh`** builds a private
`libInterface.a` from a given `glue.c`, with multiversal's own compile line
(it reproduces the shipped `glue.o` byte for byte), and
`-DGLUE_LIB_DIR=<that dir>` links it; the shared toolchain is not touched.
Measured 2026-10-15 on Systems 3.0, 6.0.8 and 7.0.1, linked against
multiversal `4c78d24`'s glue: the failures in the issue on all three; linked
against the same glue with `glue-audit.patch`: every line correct on all
three.

```sh
./mkgluelib.sh <multiversal>/custom/glue.c ../../.tmp/retro68-glue/lib
cmake -B ../../.tmp/glue-build -S . -DGLUE_LIB_DIR=$PWD/../../.tmp/retro68-glue/lib \
  -DCMAKE_TOOLCHAIN_FILE=/opt/Retro68-build/toolchain/m68k-apple-macos/cmake/retro68.toolchain.cmake
cmake --build ../../.tmp/glue-build
./run_audit.py ../../.tmp/glue-build/GlueRepro.bin --system 6    # or 7, or 3
```

**`appfiles_repro.c` is the third** (`ISSUE-appfiles.md`, not filed):
`GetAppFiles`/`ClrAppFiles` loop forever for index ≥ 2 (`AppFilePtr`'s
`while(index)` never decrements). It writes a two-document list into
`AppParmHandle` itself, so it needs no Finder and no disk. Measured
2026-10-15 on Systems 3.0, 6.0.8 and 7.0.1: the stock glue still in
`GetAppFiles(2)` 30 s on, linked against `appfiles.patch` (`mkgluelib.sh`)
it returns "Second" at once, and a three-document variant (not kept) all three. It cannot see a real Finder launch; the list
is the layout Inside Macintosh's Segment Loader gives.

**`glue_audit.c` is the evidence behind it**, as `hopen_repro.c` was for #320:
four more fields multiversal `4c78d24`'s glue leaves unset or clobbers,
found by reading every File Manager function in `custom/glue.c` against
Inside Macintosh: Files, ch. 2. It calls verbatim, renamed copies of the
glue after `Poison()` fills the stack with zeroes (control) or a
non-zero 16-bit pattern; `-DGLUE_FIXED` (target `GlueAuditFixed`) applies
**`glue-audit.patch`** to those copies and nothing else. Measured
2026-10-15, Mac Plus 4 MB under Mini vMac, an HFS (`GlueHFS`) and an MFS
(`GlueMFS`) test disk; Systems 3.0, 6.0.8 and 7.0.1 gave the same rows:

| case | stack zero | stack non-zero | non-zero, patched (6.0.8) |
|---|---|---|---|
| `GetWDInfo`, a folder's WD (`ioWDIndex`, `ioNamePtr` unset) | `noErr` | **`nsvErr`**, garbage outputs | `noErr` |
| — the field alone: `PBGetWDInfo`, `ioNamePtr = &decoy` | 8 B written | | |
| `SetFInfo("B")`, `ioFDirIndex` unset, HFS and MFS | B set | `noErr`, **A set, name → "A"** | B set |
| `HSetFInfo`, `ioDirID` left as the file ID, root and folder | **`fnfErr`** | not run | `noErr` (zeroed stack) |
| `HOpen`, `ioFVersNum` unset, MFS | `noErr` | **`fnfErr`** | `noErr` |
| — the field alone: `PBHOpen`, `ioFVersNum = 0x41`, MFS / HFS | `fnfErr` / `noErr` | | |

```sh
cmake -B ../../.tmp/glue-build -S . \
  -DCMAKE_TOOLCHAIN_FILE=/opt/Retro68-build/toolchain/m68k-apple-macos/cmake/retro68.toolchain.cmake
cmake --build ../../.tmp/glue-build
./run_audit.py ../../.tmp/glue-build/GlueAudit.bin --system 6   # or 7, or 3
```

`run_audit.py` makes both test disks, boots, and prints the path of the last
screenshot, which is read by eye.

**What it cannot see.** The non-zero patterns are chosen, not real stack
garbage: `0x0001` for `SetFInfo`, `0x4141` for `HOpen`, and for
`GetWDInfo` the half of a decoy address `(h << 16) | h`. Through the glue,
`GetWDInfo`'s index lookup fails before any name is written, so the
write through `ioNamePtr` is shown only by the field-alone row.
`HSetFInfo` is run on HFS only. Only Mini vMac's Mac Plus ran it.

**`hopen_repro.c`** compares `HOpen`/`HOpenRF`/`HOpenDF` against hand-filled
`PBHOpenSync` blocks. It is the evidence that withdrew "`HOpen` never writes
back the refNum" (DECISIONS.md, *2026-08-01 — two claims reduced to
reproductions*). Its cases 8 and 11 (`HOpenDF`/`OpenDF` return `paramErr`) are
measured, but that is Apple's documented behaviour (Technote FL 1041) and
Retro68 issue #53, not a bug: withdrawn 2026-10-13 (BLOCKERS.md). Its case 4
poisoned `ioMisc` with an address outside a Mac Plus's RAM, which is why it
saw nothing.

## `hopen_repro` results

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
| 8 | `HOpenDF`, real vRefNum, read | `err=-50` | documented (TN1041) |
| 11 | `OpenDF`, plain, default volume | `err=-50 ref=2` | documented (TN1041) |
| 9 | `HOpen`, other volume | `err=-43` | ok, matches 10 |
| 10 | `PBHOpenSync`, other volume | `err=-43` | ok, matches 9 |

`HOpen` writes the refNum in every case and agrees with a hand-written param
block everywhere. Cases 9/10 look for `System` at the root of the boot volume,
where it does not live (it is inside the System Folder), so `fnfErr` is correct
— the point is that glue and param block return the *same* thing.

Case 11 addresses the same file, on the same default volume, that cases 1-4
open with `err=0`, so its `paramErr` is the `_OpenDF` trap being absent rather
than anything about the file — which is how a caller is meant to detect it.

**Run it the way this table was produced**: the application on the root of a
volume, launched by double-clicking it, so the default directory is that root.
Cases 5-10 address `fsRtDirID` explicitly and report `fnfErr` instead if the
application is installed elsewhere — as the boot shell, for instance, where the
default directory is the System Folder. Cases 1-4 and 11 use the default
directory and are unaffected.


## Build

```sh
cmake -B build -S . \
  -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
cmake --build build
```

Produces `build/IOMisc.dsk` and `build/hopen_repro.dsk` (800K HFS images),
plus `.APPL` and `.bin` for each.

## Run

`IOMisc` needs nothing on the disk: it creates its own file `T` and stays on
screen. To boot straight into it on this machine:

```sh
V=~/.cache/macextract/vmac
tools/vmac/mkboot.py $V/System6.hfv build/IOMisc.bin /tmp/iomisc.hfv --app-name IOMisc
$V/mv-4M/minivmac -r $V/vMac.ROM /tmp/iomisc.hfv
```

For `hopen_repro`, mount the image in Mini vMac next to a System 6.0.8 boot disk and double-click
the application. It creates its own 512-byte test file next to itself, so it
needs nothing else on the disk, and prints one line per case.

`tools/vmac/setup.sh` puts a suitable Mini vMac, a Mac Plus ROM and a System
6.0.8 image in `build/vmac/`; any Mini vMac with a Mac Plus ROM works. Unlike
the fixture replays, this one has to be read off the screen by eye — it prints
text rather than the machine-readable grid `tools/vmac/run.py` decodes.

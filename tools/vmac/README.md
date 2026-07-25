# tools/vmac — running the Mac shell on an emulated Mac Plus

Everything in FORMATS.md and MANUAL_TESTS.md that claims the Macintosh shell
"runs on real System 6" was produced by this harness. It boots the Retro68
application on Mini vMac emulating a **68000 Mac Plus under System 6.0.8**,
extracts one fixture per boot, and cross-checks the result against the same
engine's Linux output.

    tools/vmac/setup.sh                                  # once
    tools/vmac/run.py fixtures/adobenumbers.sit          # 4 MB machine
    tools/vmac/run.py --mem 1M fixtures/adobenumbers.sit # 1 MB floor target

Nothing here runs in `./ci.sh`: it needs ~80 MB of downloads, an X server and
minutes per fixture. It is a deliberate, on-demand check.

## What the pieces do

| file | role |
|---|---|
| `setup.sh` | fetch + build the emulator, the ROM and a System 6.0.8 image into `$UNC_VMAC_HOME` (default `~/.cache/unclassic/vmac/`) |
| `mkboot.py` | strip that image to System + Finder and make it boot straight into the application |
| `run.py` | build the disks, boot, screenshot, decode, check |

The verification halves live one directory up because they are useful on their
own: `tools/decode_grid.py` (screenshot → eight numbers) and
`tools/vmac_check.py` (those numbers vs. the oracle).

## Why it works the way it does

**Results come off the SCREEN, not off the disk.** Mini vMac's write-back of a
mounted image to its host file is lazy and partial — it will commit one fork of
a file and not the other — so the extracted files cannot be read back on the
host. The framebuffer, however, is captured exactly by a screenshot. So the app
paints its results as a black/white bit grid (three calibration squares, a sync
word, eight 32-bit values) and the host decodes that. See `at_report()` in
`mac/unclassic_mac.c`.

**The app is the boot shell.** The boot blocks' shell name (offset 0x1A) is
rewritten from `Finder` to `unclassic`, so the ROM hands control straight to
the application. No Finder, no synthetic double-click, no mouse automation —
the machine boots into the test and nothing else runs.

**The System Folder is stripped to System + Finder.** The stock image ships
with a dozen INITs and cdevs; on the 1 MB floor-target machine that is the
difference between a result and a dead machine, and it would make peak-heap
figures incomparable between runs.

**The application always says whether it is alive.** Before doing any work it
paints a grid with `ret = -1000` ("running"); a missing `In`/`Out` volume paints
`-1001`/`-1002`. So the host can tell *never launched* from *still decoding*
from *bad disk set* — which a bare timeout cannot. `run.py` reports those as
`NOGRID`, `TIMEOUT` and `SETUP` respectively, distinct from a real `FAIL`.

**Wall-clock time here is not Mac Plus time.** The emulator is built "all out",
i.e. as fast as the host CPU allows, so `--timeout` bounds host seconds only.
Correctness results are speed-independent; **do not derive timing claims about
a 7 MHz 68000 from this harness.**

## The downloads, and why none of them are committed

`setup.sh` fetches by URL and verifies by SHA-256, exactly as `fixtures/` does,
because two of the three are Apple's copyrighted property:

| file | source | why |
|---|---|---|
| `minivmac.src.tgz` 36.04 | gryphel.com | GPL-2 emulator source, built locally |
| `vMac.ROM` | Internet Archive `mac_rom_archive_-_as_of_8-19-2011`, member `4D1F8172 - MacPlus v3.ROM` | Macintosh Plus ROM — **Apple copyright** |
| `System6.hfv` | Internet Archive `system-6_202607` | System 6.0.8 — **Apple copyright** |

If a hash ever fails to match, the upstream file changed: check it by hand
rather than editing the expected hash.

## Requirements

`Xvfb` (depth 24 — Mini vMac's X11 glue dies with `BadMatch` on an 8-bit
visual), ImageMagick (`import`, `convert`), `xdotool`, `hfsutils`
(`hformat`/`hmount`/`hcopy`, shipped with Retro68), and a Retro68 toolchain
in `$RETRO68` or `/opt/Retro68-build/toolchain`.

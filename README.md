# unclassic

**Open old Macintosh archives — on the Macintosh they came from.**

A `.sit` file from 1995 is easy to open on a modern machine and surprisingly
hard to open on the machine it was made for. `unclassic` is an unarchiver for
Classic Mac OS that runs on everything from a 1986 Mac Plus with 1 MB of RAM
up to Mac OS 9 — one application, no extensions, no installer.

There is a Linux command-line version too, built from the same engine.

## What it looks like

Pick an archive:

![Standard File dialog listing archive.sit](docs/screens/1-open.png)

Watch it work — with a real estimate, because on a Mac Plus some archives take
half an hour:

![Progress dialog: Extracting archive.sit, 13%, about 1 minute left](docs/screens/2-extracting.png)

Change your mind at any point, with the button or Cmd-. Anything half-written
is cleaned up:

![Alert reading Extraction cancelled.](docs/screens/3-cancelled.png)

Or let it finish:

![Alert reading Extraction complete.](docs/screens/4-complete.png)

## Download

**[Latest release](https://github.com/jarreboum/unclassic/releases/latest)** —
or straight from the tree:

| | |
|---|---|
| [`dist/unclassic.bin`](dist/unclassic.bin) | the application as uncompressed MacBinary — transfer it with anything MacBinary-aware |
| [`dist/unclassic.dsk`](dist/unclassic.dsk) | an 800K HFS floppy image — write it to a real floppy, or mount it in Mini vMac, Basilisk II or SheepShaver |

Both hold the same application and neither needs an unarchiver to open, which
is the point: a bare Mac has no way to unpack a `.sit` until it already has
something that can. [`dist/README.txt`](dist/README.txt) has the transfer
notes.

## What it opens

**Extracts:** StuffIt (`.sit`, classic and 5.x), Compact Pro (`.cpt`),
BinHex (`.hqx`), MacBinary, PackIt (`.pit`), AppleSingle/AppleDouble,
zip, gzip, tar, Unix compress (`.Z`).

Nested files like `.sit.hqx` or `.tar.Z` are unwrapped automatically, by
looking inside them rather than trusting the name. Resource forks, type and
creator codes and dates all survive, so an extracted application simply runs.

**Recognises but does not extract:** StuffIt X, DiskDoubler, Now Compress,
LZH, Disk Copy 4.2. It tells you what the file is rather than failing
obscurely.

Encrypted and multi-part archives are out of scope.

## What you need

| | |
|---|---|
| Minimum | System 6.0.8, 68000, **1 MB of RAM** |
| Also runs on | System 7, Mac OS 8 and 9, PowerPC via the built-in 68k emulator |
| Disk | one 800K floppy |

The same binary adapts to whatever machine it finds itself on, so the download
above is the only one. (`tools/make_dist.sh` rebuilds it from source.)

## How long it takes

On a 1 MB Mac Plus, the slowest machine supported:

| Archive | Time |
|---|---|
| A few KB, any format | seconds |
| 300 KB StuffIt or BinHex | 2–3 minutes |
| 200 KB StuffIt 5 | 16 minutes |
| 200 KB StuffIt 5, worst case measured | 32 minutes |

StuffIt 5 is in a class of its own — its compression was designed for machines
a decade newer. Everything else is quick, and a faster Mac is proportionally
faster.

## Linux

```sh
make
build/unclassic l archive.sit           # list
build/unclassic x archive.sit -o out    # extract
build/unclassic sniff mystery.bin       # what is this?
```

## Is it any good?

It is checked against [The Unarchiver](https://theunarchiver.com/) on 797 real
archives, byte for byte, both forks. The Macintosh application is checked the
same way *while running on* an emulated Mac Plus, a System 7 machine and a
Mac OS 9 PowerPC — not only on Linux.

No physical Macintosh has ever run it. Emulation is evidence, not proof.

## Where things are written down

| | |
|---|---|
| [FORMATS.md](FORMATS.md) | every format: support, memory, speed |
| [TESTING.md](TESTING.md) | how it is verified |
| [DECISIONS.md](DECISIONS.md) | why it is built the way it is |
| [OPEN_ITEMS.md](OPEN_ITEMS.md) | what is missing |
| [BLOCKERS.md](BLOCKERS.md) | current status, and claims since disproved |
| [MANUAL_TESTS.md](MANUAL_TESTS.md) | what still needs a real Macintosh |

## License

LGPL-2.1-or-later. Format details are transcribed from
[XADMaster](https://github.com/MacPaw/XADMaster); see `NOTICE`.

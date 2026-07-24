#!/bin/sh
# make_dist.sh — assemble the "bootstrap" distribution for getting unclassic
# onto a classic Mac that has no unarchiver yet (chicken-and-egg: you can't
# ship the tool as a .sit if you need the tool to open a .sit).
#
# Produces, under dist/:
#   unclassic.bin  — the application as UNCOMPRESSED MacBinary. Drop it on any
#                    Mac with a MacBinary-aware transfer (ImportFl, most terminal
#                    programs, or a network mount); no unarchiver required.
#   unclassic.dsk  — an 800K HFS floppy image holding the application. Write it
#                    to a real 800K floppy, or mount it in Mini vMac / Basilisk /
#                    SheepShaver, then drag the app onto your startup disk.
#   README.txt     — the two paragraphs above, for the download.
#
# Run tools/build_mac.sh first (needs a Retro68 toolchain). See MANUAL_TESTS.md.
set -e
cd "$(dirname "$0")/.."

SRC=build/mac
[ -f "$SRC/unclassic.bin" ] || SRC=build-mac
if [ ! -f "$SRC/unclassic.bin" ] || [ ! -f "$SRC/unclassic.dsk" ]; then
    echo "make_dist: build the Mac app first (tools/build_mac.sh) — missing"
    echo "make_dist:   $SRC/unclassic.bin / unclassic.dsk"
    exit 1
fi

mkdir -p dist
cp "$SRC/unclassic.bin" dist/unclassic.bin
cp "$SRC/unclassic.dsk" dist/unclassic.dsk
cat > dist/README.txt <<'TXT'
unclassic — bootstrap distribution
==================================

A bare Classic Mac has no way to open a .sit/.cpt/.hqx until it HAS an
unarchiver, so unclassic ships in two forms that need no unarchiver:

  unclassic.bin  The application as uncompressed MacBinary. Transfer it to
                 the Mac with any MacBinary-aware method (ImportFl, a terminal
                 program's MacBinary receive, an AppleShare/AFP mount). The
                 wrapper unpacks to the real application on arrival.

  unclassic.dsk  An 800K HFS floppy image containing the application. Write it
                 to a physical 800K floppy (a Mac Plus reads 400K/800K GCR
                 floppies only), or mount it in an emulator (Mini vMac,
                 Basilisk II, SheepShaver), then drag unclassic onto your
                 startup disk.

Floor target: System 6.0.x on a 1 MB Mac Plus (68000). The same binary runs
unchanged through Mac OS 9. It adapts its memory use to the machine at runtime
(see the 'SIZE' resource / FreeMem-derived budget), so large StuffIt 5
(Arsenic) archives that need several MB fail cleanly per entry on a small Mac
rather than refusing to launch.

License: LGPL-2.1-or-later. See LICENSE and NOTICE in the source tree.
TXT

echo "make_dist: wrote dist/unclassic.bin ($(wc -c < dist/unclassic.bin) B),"
echo "make_dist:       dist/unclassic.dsk ($(wc -c < dist/unclassic.dsk) B), dist/README.txt"

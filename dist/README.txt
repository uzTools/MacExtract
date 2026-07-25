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

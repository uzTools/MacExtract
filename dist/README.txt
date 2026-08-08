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
unchanged through Mac OS 9 and adapts its memory use to the machine at runtime,
so there is one download for every Mac.

What it opens: StuffIt (.sit, classic and 5.x), Compact Pro (.cpt), BinHex
(.hqx), MacBinary, PackIt (.pit), AppleSingle/AppleDouble, zip, gzip, tar and
Unix compress (.Z). Nested files like .sit.hqx or .tar.Z are unwrapped
automatically, by looking inside them rather than trusting the name. Resource
forks, type and creator codes and dates all survive, so an extracted
application simply runs. StuffIt X, DiskDoubler, Now Compress, LZH and Disk
Copy 4.2 are recognised and named, not extracted; encrypted archives are out
of scope.

Archives split across floppies: a StuffIt segmented set is joined back
together. Open the first part; the rest are found beside it, and if one is
somewhere else you are asked to point at it. The parts are recognised by
what is inside them, so it does not matter what they are called or whether
they are all in one folder. Sets split by Compact Pro or PKZIP are not
handled yet.

Every archive in the test sample extracts byte-exact on a 1 MB Mac Plus,
StuffIt 5 (Arsenic) included. Arsenic is slow on a 68000 — 16 minutes for a
200 KB archive, half an hour for the largest tested — and the progress dialog
shows a time estimate for that reason. Everything else takes seconds to a few
minutes. If an entry genuinely will not fit, that entry is skipped with a
message and the rest of the archive still extracts.

Verified on emulators only: System 6.0.8 and System 7.0.1 on a Mac Plus under
Mini vMac, and Mac OS 9.2 on emulated PowerPC, where every extraction is
checked byte for byte against the same engine on Linux. No physical Macintosh
has ever run it. Worth knowing before you commit a floppy to it.

License: LGPL-2.1-or-later. See LICENSE and NOTICE in the source tree.

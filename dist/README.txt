unclassic v0.18.0 — bootstrap distribution
=========================================

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
(.hqx), MacBinary, PackIt (.pit), DiskDoubler (.dd, DDAR, DDA2), Now Compress,
StuffIt SpaceSaver, Alysis SuperDisk! (.X), ARC (.arc), LZH/LHA (.lzh, .lha,
MacLHA's included), uuencoded files (.uu), btoa (.ascii),
AppleSingle/AppleDouble, zip, gzip, tar and Unix compress (.Z).
Nested files like .sit.hqx or .tar.Z are unwrapped automatically, by looking
inside them
rather than trusting the name, and a .hqx holding several files -- one
newsgroup posting, several attachments -- gives you all of them. Resource
forks, type and creator codes and dates all survive, so an extracted
application simply runs. StuffIt X, Disk Copy 4.2 and AppleLink packages
are recognised and named, not extracted.

Password-protected archives open too -- StuffIt, StuffIt 5, Compact
Pro, PackIt, zip (the old cipher and WinZip's AES) and ARC. You are
asked for the password when an entry that needs one comes up, and
asked again if the archive refuses it. One catch, and it belongs to
the format rather than to this program: an encrypted StuffIt archive
keeps half of its key in the file's RESOURCE fork, so a copy that lost
the fork on its way here cannot be opened by anything.

StuffIt SpaceSaver files open too, and they are the ones that look like
nothing is wrong: SpaceSaver compressed in place, so the file kept its
name and icon and only that Mac could read it. On any other machine its
own application finds a compressed header where the document should be.
unclassic carries the table SpaceSaver primes its compression with -- the
part no other tool has -- so a single file on a floppy is enough, with
nothing else to install. (That table is copyright Aladdin Systems; see
the NOTICE file in the source.)

The application has its own icon -- an open carton lettered EXTRACT --
drawn for 1-bit, 16-colour and 256-colour screens. If it shows up as a plain
document or a generic diamond, the Finder is using a stale Desktop file:
restart holding Command and Option, and say yes to rebuilding it.

If you run MultiFinder or System 7, the size in the application's Get Info
window matters. It asks for 4 MB, runs in as little as 400 KB, and at about
850 KB every archive in the test sample comes out whole. Below that it still
opens everything and lists what is inside; entries too big to fit are named,
one message each, and the rest extract. If it does run short, it tells you
how much more to type into that box.

Using it: open an archive, then say which folder the files should go into.
That second dialog opens in the archive's own folder, so pressing Return
puts them next to it; click Drive to send them to another disk instead.

If a Compact Pro archive carries a note -- the comment whoever made it
typed in -- it is written into that folder as a text file called
Comments, rather than thrown away with the wrapper.

Archives split across floppies: a StuffIt segmented set is joined back
together. Open the first part; the rest are found beside it, and if one is
somewhere else you are asked for it. Putting the disk in is the whole answer
— the part is picked up as soon as the disk appears, with nothing to click —
and the question tells you how much of the archive is still to read. The
parts are recognised by what is inside them, so it does not matter what they
are called or whether they are all in one folder. Send the output to a
different disk from the parts; the disk holding the output is otherwise the
disk you have to eject.

If the parts are still in their BinHex or MacBinary wrappers
(Archive.sit.1.hqx and friends), open the first one — the wrappers come off
and the pieces are found inside the others.

Sets made by Compact Pro, or cut up by DiskDoubler's own Split command, are
joined the same way, and you can open any part of one. Archives split into
NAME.z01/.z02/.zip, or into plain NAME.001/.002 pieces, are joined by name
instead — those two schemes put nothing inside the files that says which set
they belong to, so keep the names they came with.

Every archive in the test sample extracts byte-exact on a 1 MB Mac Plus,
StuffIt 5 (Arsenic) included. Arsenic is slow on a 68000 — 13 minutes for a
200 KB archive, 21 for the largest tested — and the progress dialog
shows a time estimate for that reason. Everything else takes seconds to a few
minutes. If an entry genuinely will not fit, that entry is skipped with a
message and the rest of the archive still extracts.

Verified on emulators only: System 6.0.8 and System 7.0.1 on a Mac Plus under
Mini vMac, and Mac OS 9.2 on emulated PowerPC, where every extraction is
checked byte for byte against the same engine on Linux. No physical Macintosh
has ever run it. Worth knowing before you commit a floppy to it.

License: LGPL-2.1-or-later. See LICENSE and NOTICE in the source tree.

MacExtract v0.46.0 — bootstrap distribution
==========================================

A bare Classic Mac has no way to open a .sit/.cpt/.hqx until it HAS an
unarchiver, so MacExtract ships in forms that need none, and one for a Mac
that already has one:

  MacExtract.bin  The application as uncompressed MacBinary. Transfer it to
                  the Mac with any MacBinary-aware method (ImportFl, a terminal
                  program's MacBinary receive, an AppleShare/AFP mount). The
                  wrapper unpacks to the real application on arrival.

  MacExtract.hqx  The same application as BinHex 4.0, which is plain text.
                  It needs StuffIt Expander or BinHex on the Mac to open, so
                  it is for a Mac that already has one, over a transfer that
                  carries only text (mail, a text-mode transfer). Anything
                  that carries a .bin intact is the better route.

Each floppy comes twice. The .img is the raw disk: write it with dd or a raw
image writer, or mount it in an emulator (Mini vMac, Basilisk II,
SheepShaver). The .dsk is the same disk as a Disk Copy 4.2 image, for
Apple's Disk Copy to write to a floppy on a Mac; Disk Copy opens it once its
type is dImg and its creator dCpy. Every floppy holds MacExtract and a
short "Read Me" on using it; drag MacExtract onto your startup disk. The
floppies work locked, on every System.

  MacExtract-800K.img, .dsk  An 800K HFS floppy, with the "MacExtract
                  Helpers" folder. A Mac Plus reads 400K/800K floppies only.

  MacExtract-1440K.img, .dsk  The same disk at 1.44 MB, for a USB floppy
                  drive. Write the image itself, not a copy of the file, to
                  a high-density disk, and any Mac with a 1.44 MB SuperDrive
                  mounts it. A USB drive cannot write an 800K Mac disk, and
                  a Mac Plus, 512Ke or original SE cannot read a 1.44 MB one.
                  Copying MacExtract.bin onto a PC-formatted disk does not
                  work either: it arrives still wrapped, with nothing on the
                  Mac to unwrap it. Not yet tried on a real SuperDrive.

  MacExtract-400K.img, .dsk  A 400K MFS floppy, for a Macintosh 512K with
                  a Hard Disk 20: its 64K ROM reads no other floppy. It holds
                  MacExtract, MacExtract-Helpers.zip and the Read Me. Write
                  it to a 400K disk on a Mac with both kinds of drive. Not
                  yet tried on a real 512K; if you have one, this is the
                  test: start up from the Hard Disk 20, put the floppy in,
                  double-click MacExtract-Helpers.zip and choose the Hard
                  Disk 20. Then tell us what happened, at
                  https://github.com/uzTools/MacExtract/issues --
                  twenty-one files in a "MacExtract Helpers" folder, or
                  the ID number if it bombs.

Double-click helpers. The 800K and 1.44 MB disks also hold a "MacExtract
Helpers" folder, and MacExtract-Helpers.zip has the same twenty-one in
one file: open it with MacExtract. Each one stands in
for a program that made archives -- StuffIt, Compact Pro, DiskDoubler,
BinHex and others -- so that double-clicking one of its archives opens it in
MacExtract, on every System from 3.0 to Mac OS 9. Copy the folder to your
hard disk along with MacExtract, anywhere you like, and open it and
MacExtract's folder once so the Finder sees them. Keep only the helpers you
want. A file MacExtract cannot open goes to the program that made it, if
that program is on the Mac. On Mac OS 9, if StuffIt Expander is installed
afterwards and takes its archives back, open the "StuffIt" and "Expander"
helpers once.

No hard disk? The MacExtract floppy is ready as it comes: put it in, eject
it, put in the floppy with your archive and double-click the archive. The
Mac asks for each disk in turn -- a few swaps before MacExtract asks where
to put the files, more while it extracts. On System 7 the Finder alone asks
for the two disks about four times each before MacExtract even starts; open
MacExtract first and choose the archive in its Open dialog to avoid that.

Floor target: System 3.0 on a 1 MB Mac Plus (68000) -- the system the Plus
shipped with in January 1986. It also runs in 512 KB, on a Macintosh 512Ke.
On a true Macintosh 512K -- the 64K ROM -- it opens and lists a disk, but
extracting needs HFS, which that machine has only with a Hard Disk 20
attached. With one it extracts on an emulator; nobody has yet tried a
real one (MacExtract-400K is the disk for it). A Macintosh 128K cannot run this
at all: the program's code and data do not fit in its memory, whatever the
system.
The same binary runs unchanged through Mac OS 9 and adapts its memory use to
the machine at runtime, so there is one download for every Mac.
Extract onto an HFS disk -- an 800K floppy or a hard disk. MFS disks --
most 400K floppies -- are not supported.

Two things to know about the smallest machines. On System 3.0 the Open dialog
ignores Command-period, so close it with the Cancel button; Command-period
still stops an extraction everywhere. And in 512 KB, a StuffIt 5 archive
written with large blocks will not fit -- a block has to be in memory whole,
and its size was fixed when the archive was made. The largest method 14 files
are the same story for the same reason: that method looks back over as much as
256 KB, and the room has to be there. Those entries are skipped with a message
and the rest of the archive still comes out. Every other format fits in
512 KB, and with 1 MB the question does not arise.

v0.46.0 opens four more kinds of file: Hampa Hug's MAR archives (.mar,
.mac, and .mar.lz4); the floppies of Apple Backup, a Performa's backup,
read as one set even with disks missing; the Tomes on Apple's install
disks, System 7.5 to Mac OS 9; and the fonts and network software Apple's
Installer keeps compressed in a file's resource fork. Netscape's .xpi
installer packages, which are zips, now carry MacExtract's archive icon.

It is the first release with the double-click helpers described above.
Macintosh Easy Open and Mac OS 9's File Exchange list MacExtract, not the
helpers, for an archive whose program is missing. A file DiskDoubler
compressed in place opens through the "DiskDblr" helper, which also gives
it the archive icon.

MacExtract itself takes about 7 KB less memory, which every archive gets
instead, and on a Mac Plus StuffIt's method 5, zip's Implode and the LZH
methods decode between a fifth and a third faster, a zip stored without
compression about three times faster. In 512 KB under System 6.0.8, 72 of
the 74 test archives come out, against 68 before. On a Macintosh 512K,
v0.45.0 bombed at launch; it starts again. On a Mac Plus, an SE, a Classic
or any other Macintosh with a 68000, v0.45.0 bombed with an "address
error" as it asked where the files go; it no longer does.

Fixed: after a password was asked for, the progress bar was drawn at the
top left of the screen. A 64th character typed in the password dialog
went past its end. A disk that fills up now says "Disk full." under the
file it could not write, and a disk that cannot be read is no longer
reported as an incomplete archive. A file and a folder of the same name
no longer make everything in the folder fail: the folder is numbered. A
Get Info comment longer than the Finder keeps is cut, and the report says
so. Cancel answers sooner in the slow formats, and its button flashes. A
BinHex file with lines longer than 256 characters lost a character from
each. Six MacBinary files written without the usual padding, and tar
archives that set their dates once for every file, open as they should.
A Compact Pro set or a split zip opened without its last part beside it
said "Parts missing."; it now asks for the disk that holds the part. A
locked MacExtract floppy showed no icons, and on System 3.0 bombed when
its Helpers folder was opened; it now works locked. The icons are new.

Earlier versions' notes are in CHANGES.md:
https://github.com/uzTools/MacExtract/blob/main/CHANGES.md

What it opens: StuffIt (.sit, classic and 5.x), Compact Pro (.cpt), BinHex
(.hqx, and the older .hex and .hcx), SUMacC's .dl before them, MacBinary,
PackIt (.pit), AppleLink packages (.pkg),
Private File (.pf), DiskDoubler (.dd, DDAR, DDA2), Now Compress,
StuffIt SpaceSaver, Alysis SuperDisk! (.X), ARC (.arc), LZH/LHA (.lzh, .lha,
MacLHA's included), uuencoded files (.uu), btoa (.ascii), base64 and files
mailed as MIME attachments (.b64, .mim -- both forks, where the message
carried them), AppleSingle/AppleDouble, MAR (.mar, .mac, and .mar.lz4),
Apple Backup's floppies (a Performa's backup, even with disks missing),
the Tomes on Apple's install disks (System 7.5 to Mac OS 9) and the fonts
and network software its Installer keeps compressed, zip, gzip, tar and
Unix compress (.Z).
Nested files like .sit.hqx or .tar.Z are unwrapped automatically, by looking
inside them
rather than trusting the name, and a .hqx holding several files -- one
newsgroup posting, several attachments -- gives you all of them. A
Macintosh self-extracting archive is opened as the archive it is, zip
ones included (above). Resource
forks, type and creator codes and dates all survive, so an extracted
application simply runs. StuffIt X and the PC-side and modern
archives -- RAR, 7-Zip, xz, bzip2, Cabinet, cpio and the rest -- are
not opened: to MacExtract they are files like any other it does not
read, and it says "Unknown format." before asking
where to put anything.

Disk images are out of scope, and v0.33.0 is where that became true of
DART as well: a DART, NDIF or UDIF holds a floppy rather than files, and
what reads one is a mounting program. v0.32.0 expanded a compressed DART
into an uncompressed one; if that is what you came for, MacMount is the
project that finishes the job.

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
MacExtract carries the table SpaceSaver primes its compression with -- the
part no other tool has -- so a single file on a floppy is enough, with
nothing else to install. (That table is copyright Aladdin Systems; see
the NOTICE file in the source.)

The application has its own icon -- an open carton lettered EXTRACT --
drawn for 1-bit, 16-colour and 256-colour screens. If it shows up as a plain
document or a generic diamond, the Finder is using a stale Desktop file:
restart holding Command and Option, and say yes to rebuilding it.

If you run MultiFinder or System 7, the size in the application's Get Info
window matters. It asks for 4 MB, runs in as little as 400 KB, and at about
800 KB every archive in the test sample comes out whole. Below that it still
opens everything and lists what is inside; entries too big to fit are named,
one message each, and the rest extract. If it does run short, it tells you the
least it needs -- type at least that much into the box, since one entry can
ask for its memory in many small pieces and the message counts the first
piece that did not fit.

Using it: open an archive, then say which folder the files should go into.
That second dialog opens in the archive's own folder, so pressing Return
puts them next to it; click Drive to send them to another disk instead.

When a run ends, anything that had to change on the way is listed: a name too
long for HFS (31 characters max) and what it became, an entry that could not
be extracted and what was wrong with it. Save as Text files the whole thing as
a document. A run with nothing to report just says so, as before.

StuffIt 5 stores its names as Unicode, so they can say things a Mac cannot
write. Accented and symbol names come out as themselves -- a folder called
"Cool Tools f" with the florin sign is still that -- and anything with no
Mac spelling at all, Japanese for instance, gets an underscore per character
and a line in that list saying so.

Two files whose names are the same for the first 31 characters do not
overwrite each other -- the second gets a ~1 after its name, before the .txt
or whatever the suffix is. Two FOLDERS in that position are kept apart the
same way, so the files that were in different folders in the archive are in
different folders on your disk.

If a Compact Pro or zip archive carries a note -- the comment whoever
made it typed in -- it is written into that folder as a text file called
Comments, rather than thrown away with the wrapper.

Very occasionally a file uses a compression method MacExtract does not
know. That entry is skipped and the rest of the archive still comes out,
and the message says so rather than blaming your machine. Those files are
worth reporting -- most of the methods here were added because somebody
sent one -- and the Linux version names the method for you, which is the
part that makes a report worth sending.

One kind of StuffIt file is worth knowing about. StuffIt Deluxe 2.0, in
1990, could hand a file to an add-on called an Optimizer before
compressing it -- a separate little file you installed, which trimmed
sound, paint, Photoshop or text documents before they were squeezed. No
StuffIt since has opened those archives. MacExtract opens all five
add-ons Aladdin shipped, and tells you when what comes out is not
what went in.

A sound or a Photoshop document comes back exactly as it was. A text
one comes back tidied -- which is what StuffIt Deluxe itself hands back
too, because the add-on threw that away and nothing can put it back. A
paint document comes back with the picture intact and a blank header:
its palette and pattern settings are gone for good, and not even
StuffIt Deluxe can bring them back. A photograph the JPEG add-on
touched comes back softened in the same way, and byte for byte the
picture StuffIt Deluxe 2.0 itself hands back: the add-on threw away
part of it in 1990, and no software can return it.

Archives split across floppies: a StuffIt segmented set is joined back
together. Open the first part; the rest are found beside it, and if one is
somewhere else you are asked for it. Putting the disk in is the whole answer
— the part is picked up as soon as the disk appears, with nothing to click —
and the question tells you how much of the archive is still to read. Each
part is checked against the checksum StuffIt wrote into it as soon as it has
been read, so a damaged disk is reported before the next one is asked for,
and a part whose own header is damaged is reported as missing, not joined.
The parts are recognised by what is inside them, so it does not matter what they
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

A file that arrived as several mail messages is joined too. Mail gateways
used to cut anything large into numbered pieces (message/partial); open any
one of them and the rest are found beside it, whatever they are called, and
a Macintosh file mailed that way comes back with both its forks.

Every archive in the test sample extracts byte-exact on a 1 MB Mac Plus,
StuffIt 5 (Arsenic) included. Arsenic is slow on a 68000 — 6 minutes for a
150 KB archive, 12 for the worst tested — and the progress dialog
shows a time estimate for that reason. Everything else takes seconds to a few
minutes: a 280 KB StuffIt archive is about a minute on a 7 MHz Mac Plus, which
is what StuffIt Expander 4.0.2 takes on the same machine and the same file. If
an entry genuinely will not fit, that entry is skipped with a message and the
rest of the archive still extracts.

Verified on emulators: System 3.0, System 6.0.8 and System 7.0.1 on a Mac
Plus under Mini vMac, and Mac OS 9.2 on emulated PowerPC, where every
extraction is checked byte for byte against the same engine on Linux. One
physical Macintosh has run it: an LC 475 under System 7.6.1, which ran
v0.39.0 and found the faults above; their fixes are checked on emulators.
Nothing older than that has, so a Mac Plus is still untested on real
hardware -- worth knowing before you commit a floppy to it.

License: 0BSD, except four decoders transcribed from XADMaster, libxad or
macutils (LGPL-2.1-or-later) and zlib's inflate (the zlib licence), all
listed in NOTICE. See LICENSE and NOTICE in the source tree.

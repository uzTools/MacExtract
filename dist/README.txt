MacExtract v0.43.0 — bootstrap distribution
==========================================

A bare Classic Mac has no way to open a .sit/.cpt/.hqx until it HAS an
unarchiver, so MacExtract ships in three forms that need no unarchiver:

  MacExtract.bin  The application as uncompressed MacBinary. Transfer it to
                  the Mac with any MacBinary-aware method (ImportFl, a terminal
                  program's MacBinary receive, an AppleShare/AFP mount). The
                  wrapper unpacks to the real application on arrival.

  MacExtract.dsk  An 800K HFS floppy image containing the application. Write it
                  to a physical 800K floppy (a Mac Plus reads 400K/800K GCR
                  floppies only), or mount it in an emulator (Mini vMac,
                  Basilisk II, SheepShaver), then drag MacExtract onto your
                  startup disk.

  MacExtract-1440K.img  The same disk at 1.44 MB, for a USB floppy drive.
                  Write the image itself, not a copy of the file, to a
                  high-density disk (dd on Linux or a Mac, a raw image writer
                  on Windows), and any Mac with a 1.44 MB SuperDrive mounts
                  it. A USB drive cannot write an 800K Mac disk, and a Mac
                  Plus, 512Ke or original SE cannot read a 1.44 MB one.
                  Copying MacExtract.bin onto a PC-formatted disk does not
                  work either: it arrives still wrapped, with nothing on the
                  Mac to unwrap it. Not yet tried on a real SuperDrive.

Floor target: System 3.0 on a 1 MB Mac Plus (68000) -- the system the Plus
shipped with in January 1986. It also runs in 512 KB, on a Macintosh 512Ke.
On a true Macintosh 512K -- the 64K ROM -- it opens and lists a disk, but
extracting needs HFS, which that machine has only with a Hard Disk 20
attached; nobody has yet tried it on one. A Macintosh 128K cannot run this
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

v0.43.0 fixes what v0.42.0 broke. On System 7.0.1, and on System 6
with AppleShare's "Desktop Mgr" file in the System Folder, once an
application or anything else with its own icon had come out at the top
of a folder, nothing after it could be created there, and of several
archives opened together from the Finder only the first was extracted
-- the next one stopped at "Could not open the archive." Both are fixed;
later systems than 7.0.1 were not tried with v0.42.0. MacExtract itself
also takes about 9 KB less memory, which every archive gets instead.

v0.42.0 fixes one crash, the first reported from outside: on System 6
with AppleShare's "Desktop Mgr" file in the System Folder -- which the
System 6.0.8 disk image most Mini vMac users start from has -- any
archive holding an application, a control panel or anything else with
its own icon bombed with "unimplemented trap" as that file came out.
Nothing else changed.

v0.41.0 puts files and folders back exactly as they were before they
were archived, wherever the archive kept it: each icon's place in its
window, each folder's window -- where it opens, its size, its view and
scroll -- the Get Info comment, all three dates, the Locked box, custom
icons, and the Finder flags behind them. An application keeps its place
and its own icon, as StuffIt Expander puts it back. A zip made by the
Mac OS X Finder gives back the resource forks, types, creators and
comments it stored in its __MACOSX folder, Spotlight comments included,
and that folder is not left behind. Dates an archive kept in universal
time are shown in your Mac's own time zone. A file another system marked
read-only comes out locked. What comes out at the top lands at the next
free spot in the window or on the desktop, rather than where it sat on
the Mac it was archived on.

The Macintosh application changed in small ways, all found on real
hardware. It looks at the file first, and asks where to put anything
only if it can open it; a file it cannot read gets "Unknown format.",
and one that is damaged before its first file "Archive damaged.".
Cancel at "Extract into this folder:" quits. The password dialog says
"Enter the password for ..." and, after a wrong one -- an empty one
counts -- "Incorrect password." When a part of a split archive is
missing, Find... opens in the folder holding the parts, not the one you
are extracting into. The progress window says how long is left and no
longer flickers. And one crash is gone: opening part of a split StuffIt
archive in a folder that also held an AppleSingle file with a comment.

Formats this program could name but not open -- ARJ, RAR and the rest --
are no longer named: everything it does not extract is simply a file it
does not read.

v0.40.0 is what the first real Macintosh to run it found -- an LC 475,
in its owner's hands. The biggest: on a Macintosh, a zip whose name ends
in ".zip", which is nearly every zip, was refused with "This archive has
more parts". Every release since August had it, and every zip passed
every test, because the tests never called a file ".zip". It opens now.

Three more from the same afternoon. MacExtract now quits after an
archive: it reads its decoders from disk once, at launch, and keeps only
the ones that archive needs, so a second archive in another format could
not be opened -- and it no longer offers you one. Open it again for the
next archive, or select several archives in the Finder and open them
together: between them it reads its decoders from disk again, which on a
Mac with one floppy drive may ask for its own disk back. Extracting an
archive into a folder where you already extracted it gives you a second
folder, "Name~1", with the files inside under their own names, instead
of "~1" copies scattered through the first. And in 256 colours or more
the icon now darkens all over when you select it, as Apple's own do; it
used to darken only its white. If an earlier MacExtract was ever on that
Mac, the Finder keeps showing the old icon until you rebuild the desktop:
restart holding Command and Option.

An archive split across floppies is one step shorter on a one-drive Mac:
when the next part is not on the floppy the last one came from,
MacExtract ejects that floppy before it asks, so putting the next one in
is all there is to do.

And one from StuffIt Deluxe 2.0: a photograph its JPEG add-on had
squeezed came back as the wrong picture -- silently -- unless it was 256
pixels wide and grey. Every width and every colour mode the add-on
writes now comes back exactly as StuffIt Deluxe 2.0 itself restores it.

BinHex files from before BinHex 4 open too: the .hex and .hcx that
BinHex 2.0 wrote, which is how Macintosh software was passed around in
1984 and 1985.

v0.39.0, before it, opened the last zip method of PKZIP's first years:
Reducing, in all four of its strengths. No Macintosh program is known
to have written it, but the PC disks that Mac CD-ROMs carried by the
hundred did. The same release made Shrinking about an eighth faster on
a 68000.

v0.38.0 opened the zip archives of PKZIP's first years, and
two formats only Aladdin's own software ever read.

Old zip archives open -- the ones PKZIP 1 made in 1989 and 1990, with a
method called Imploding. Nothing has written one since, but plenty are
still on download sites and CD-ROMs, and ZipIt on the Mac could write
them too: a Macintosh zip of 1994 with both forks intact is what settled
it. Those entries used to be listed and then skipped; they come out now,
with their resource forks, types and creators. The same release gives
you the name a Macintosh file HAD inside a ZipIt archive: ZipIt could be
told to convert names to the MS-DOS shape -- eight letters, upper case,
no spaces -- and it kept the real one beside it, so "READ ME" comes out
as "READ ME" rather than "README". The folder around it keeps whatever
the archive called it, which is all the archive records for a folder.

The OLDEST of those zips open too. PKZIP 1.01 and 1.02, from 1989, had a
bug in how they wrote some files, and a zip made by one of them could be
refused here with a message saying the file's own checksum was wrong --
when there was nothing wrong with the file. PKZIP's own 1989 download is
one of them: three of the thirteen files inside it. It is read correctly
now, and so is anything else those two versions wrote. Nothing else
changed: every other zip is read exactly as before, and a zip that
really is damaged still says so.

Zips that use Shrinking, the other method of PKZIP's first years, open
too. Most such zips came from PCs, but a Macintosh made them as well --
an EndNote style from 1993 is the one that was found -- and they turn up
on Mac CD-ROMs by the hundred.

Self-extracting zip archives open. ZipIt made these -- a .sea you
double-click, which on a modern Mac of the day unpacked itself. The
application part is PowerPC code, so on a Mac Plus it was simply a file
you could not use; the zip behind it was always there, and this program
now finds it and gives you the files. Pick the .sea in MacExtract's Open
dialog and it opens like any other archive. The same is true of a
self-extracting zip from the PC side.

AppleLink packages (.pkg) open. AppleLink was Apple's own online
service, and a .pkg is the little archive its software made for sending
files over it, in 1992 -- one Aladdin wrote the code for and nobody else
ever read. Opening one used to mean having StuffIt Deluxe and the right
add-on. These are recognised by what is inside them, which not even
Aladdin's own reader did: it went by the .pkg on the end of the name.

Private File (.pf) opens. Aladdin sold Private File in 1996 and 1997 to
lock a file with a password before mailing it, and until now only
Aladdin's own software could open one. You are asked for the password,
as for any encrypted archive, and you get the original file back, both
forks, type and creator; a wrong password is refused rather than turned
into rubbish.

More uuencoded files open than before. UUTool, the Mac program most of
these were made with, had a setting that shifted the characters it used
so that mail programs could not damage them -- it was the DEFAULT
setting, and this program had never read a file written with it. It does
now. So does the other spelling, the one Unix's own uuencode uses for a
zero. If a .uu file was ever refused here as "not recognized", it is
worth another try.

A .hqx that was posted in two halves now opens. Long files were often
sent as "part 1 of 2" and "part 2 of 2", with a line of dashes where
they were cut; this program used to read the dashes as part of the file
and then say the file's own checksum was wrong. It now skips over the
join. Only the dashes were ever the trouble -- a cut marked with
ordinary words has always been read -- so if a .hqx in two parts was
refused for a bad checksum, it is worth another try.

Aladdin's Shortcut 1.5.3 updater, an installer with an encrypted archive
inside, had two of its thirteen files refused as "damaged" or "encrypted
by a scheme we cannot read" even with the right password. They were
neither: the installer leaves stray numbers where StuffIt 2.0 recorded
an encryption add-on, and this program believed them. With the password,
both now come out byte for byte as Aladdin's installer writes them.
Other installers made with the same tool may have had the same trouble;
this is the only one tested.

And one fix: a StuffIt 5 archive made with compression method 14 -- the
format v0.37.0 added, just below -- could be refused with a message
saying the file's own checksum was wrong, when there was nothing wrong
with the file. Whether it happened depended on how the archive was laid
out inside rather than on anything you did, so one .sit would open and
the next would not; the Aladdin installers v0.37.0 was tested on were
among the ones that worked. If a method 14 archive was ever refused here
as having a bad checksum, it opens now.

v0.37.0, before it, opened the last StuffIt archives this program could
not: the ones made with compression method 14, which StuffIt 5 used and
nothing else ever wrote. Aladdin's own installers are full of them -- in
StuffIt Deluxe 7.0.3's, 80 of its 258 files used it, and this program
listed them and gave up. All 258 come out now, and all 184 of StuffIt
Deluxe 5.5's. If you have ever been told a .sit was "not supported yet"
on a file this program could see the names inside, that is the release
that reads it.

v0.36.0, before it, was about one program: StuffIt Deluxe 2.0, from
1990. Everything that application could write, this one opens.

Its five add-on Optimizers, which no StuffIt since has opened, are
described further down. The other half of that release: StuffIt Deluxe
2.0 could lock an archive with a password, four different ways, and all
four open -- its own DES and NewDE, and the NewDEx and DESex plug-ins
from its optional disk. You give the password; the archive opens. A
fifth, a third-party add-on called PassLock, turns out never to have
encrypted anything at all: it writes a password into the file and
nothing else, so those archives open without one, and if you were
relying on it for privacy in 1990, you were not getting any.

The rest of what that application wrote already opened and is now
checked rather than assumed: archives that stuff a folder, archives
saved in the older 1.5.1 format, every compression setting it offered,
and the self-extracting archives it made. Twenty-eight archives written
by StuffIt Deluxe 2.0 itself, under an emulator, are tested against
this program on every build.

v0.35.0, before it, changed almost nothing you would meet, and that is
the honest summary: it is a release of tests, provenance and tooling. Two things did
change. An ARJ archive whose header is a couple of bytes shorter than this
program used to accept is now NAMED rather than passed over -- it still
cannot be opened, ARJ being one of the formats this program identifies and
does not extract. And the test that claimed to recognise an AppleLink
package turned out to be reading a menu command rather than a package, so
.pkg stopped being listed as a format at all -- until this build, where
it is read properly (above).

v0.34.0, before it, fixed two things you could meet. A password-protected
ARC archive whose scrambled data ran short was refused outright, with "file
is truncated", instead of asking you for the password; it now asks. And a
file that merely looks like one part of a split Compact Pro archive -- a
real AppleLink package does -- was taken for one and then failed as a
damaged archive.

Memory is as v0.33.0 left it: the decoders stay on disk until an archive
turns out to need one, which leaves about 85 KB more for decoding than
v0.32.0 had. On a 512 KB machine two more of the test archives come out
whole; on larger machines it changes nothing you can see.

What it opens: StuffIt (.sit, classic and 5.x), Compact Pro (.cpt), BinHex
(.hqx), MacBinary, PackIt (.pit), AppleLink packages (.pkg),
Private File (.pf), DiskDoubler (.dd, DDAR, DDA2), Now Compress,
StuffIt SpaceSaver, Alysis SuperDisk! (.X), ARC (.arc), LZH/LHA (.lzh, .lha,
MacLHA's included), uuencoded files (.uu), btoa (.ascii), base64 and files
mailed as MIME attachments (.b64, .mim -- both forks, where the message
carried them), AppleSingle/AppleDouble, zip, gzip, tar and Unix compress (.Z).
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

License: LGPL-2.1-or-later. See LICENSE and NOTICE in the source tree.

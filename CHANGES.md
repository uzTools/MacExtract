# Changes

What each version before the current one changed, newest first, as its
release notes said it. The current version's notes are in
[dist/README.txt](dist/README.txt).

## v0.45.0

v0.45.0 changes how MacExtract asks you things. Where the files go is
asked in a window with a New Folder button, on every System. A missing
part of a split archive is asked for in one window, the Open dialog with
the question under it: put the disk in and it is picked up, a disk that
does not hold the part comes straight back out, and a set that is short
of a part says "Parts missing." and names what it could not finish. The
progress window is the Finder's own shape, in the Finder's colours on a
colour Mac, and on floppies it says how long is left from the first one.
"Extraction complete." is gone when there is nothing else to say. If you
switch to the Finder while it works, MacExtract waits for you to come
back instead of opening a window behind yours that could not be used.

A set split into mail messages, opened from a later part, now ejects that
disk and needs each floppy once, and the window asking for a part no
longer takes seconds to draw in a busy folder. The Open dialog no longer
lists invisible files. MacExtract takes about 600 bytes more memory.

## v0.44.0

v0.44.0 makes split StuffIt archives work. Every set StuffIt itself
cut -- with StuffIt Lite, Deluxe, DropSegment or InstallerMaker -- was
refused as an unknown format by every earlier release: the tests had
only ever seen sets made by a program written for them. They open now,
including a file with a resource fork and the installers whose first
disk also carries PowerPC code. Each part's checksum is checked as it
is read, so a damaged disk is reported before you are asked for the
next one.

When the Finder offers to open a document with another program -- as
System 7.6 and Mac OS 9 do when its own program is missing --
MacExtract is now in the list for the archive types it reads. An
archive that names MacExtract as its creator shows an archive icon,
not the application's.

Two more formats open: the .dl files of Stanford's SUMacC, which came
before BinHex, and MacCompress 3.2's archives. An archive made by
DiskDoubler's Combine that holds a file stored as it was, such as a
self-extractor, now gives back all its files, and each file comes back
to its place in its window. A .gz made of several pieces joined end to
end comes out whole; only the first piece used to.

If virus protection such as GateKeeper stops MacExtract setting files'
types, creators and dates, the report now names those files and says
what to do; it used to end in "Extraction complete." A mail message
nested too deep to open is named too. A dozen ways a damaged archive
could crash MacExtract, hang it, or quietly drop files are fixed. And
MacExtract itself takes about 2.5 KB less memory, which every archive
gets instead.

## v0.43.0

v0.43.0 fixes what v0.42.0 broke. On System 7.0.1, and on System 6
with AppleShare's "Desktop Mgr" file in the System Folder, once an
application or anything else with its own icon had come out at the top
of a folder, nothing after it could be created there, and of several
archives opened together from the Finder only the first was extracted
-- the next one stopped at "Could not open the archive." Both are fixed;
later systems than 7.0.1 were not tried with v0.42.0. MacExtract itself
also takes about 9 KB less memory, which every archive gets instead.

## v0.42.0

v0.42.0 fixes one crash, the first reported from outside: on System 6
with AppleShare's "Desktop Mgr" file in the System Folder -- which the
System 6.0.8 disk image most Mini vMac users start from has -- any
archive holding an application, a control panel or anything else with
its own icon bombed with "unimplemented trap" as that file came out.
Nothing else changed.

## v0.41.0

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

## v0.40.0

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

## v0.39.0

v0.39.0, before it, opened the last zip method of PKZIP's first years:
Reducing, in all four of its strengths. No Macintosh program is known
to have written it, but the PC disks that Mac CD-ROMs carried by the
hundred did. The same release made Shrinking about an eighth faster on
a 68000.

## v0.38.0

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

## v0.37.0

v0.37.0, before it, opened the last StuffIt archives this program could
not: the ones made with compression method 14, which StuffIt 5 used and
nothing else ever wrote. Aladdin's own installers are full of them -- in
StuffIt Deluxe 7.0.3's, 80 of its 258 files used it, and this program
listed them and gave up. All 258 come out now, and all 184 of StuffIt
Deluxe 5.5's. If you have ever been told a .sit was "not supported yet"
on a file this program could see the names inside, that is the release
that reads it.

## v0.36.0

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

## v0.35.0

v0.35.0, before it, changed almost nothing you would meet, and that is
the honest summary: it is a release of tests, provenance and tooling. Two things did
change. An ARJ archive whose header is a couple of bytes shorter than this
program used to accept is now NAMED rather than passed over -- it still
cannot be opened, ARJ being one of the formats this program identifies and
does not extract. And the test that claimed to recognise an AppleLink
package turned out to be reading a menu command rather than a package, so
.pkg stopped being listed as a format at all -- until this build, where
it is read properly (above).

## v0.34.0

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

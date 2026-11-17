MacExtract v0.46.0
==================

Which file to download, how to get it onto your Mac and what it opens:
https://github.com/uzTools/MacExtract#readme
What earlier versions changed: CHANGES.md in the same place.

v0.46.0 opens four more kinds of file: Hampa Hug's MAR archives (.mar,
.mac, and .mar.lz4); the floppies of Apple Backup, a Performa's backup,
read as one set even with disks missing; the Tomes on Apple's install
disks, System 7.5 to Mac OS 9; and the fonts and network software Apple's
Installer keeps compressed in a file's resource fork. Netscape's .xpi
installer packages, which are zips, now carry MacExtract's archive icon.

It is the first release with the double-click helpers: the "MacExtract
Helpers" folder on the 800K and 1.44 MB floppies, and
MacExtract-Helpers.zip. Each stands in for a program that made archives
-- StuffIt, Compact Pro, DiskDoubler, BinHex and others -- so that
double-clicking one of its archives opens it in MacExtract, on every
System from 3.0 to Mac OS 9.
Macintosh Easy Open and Mac OS 9's File Exchange list MacExtract, not the
helpers, for an archive whose program is missing. A file DiskDoubler
compressed in place opens through the "DiskDblr" helper, which also gives
it the archive icon.

A helper shares its creator with the program it stands in for, and never
takes that program's icon. One limit: on System 6 and 3.0, a program
installed after the helpers shows the generic application icon instead of
its own; on System 7.6.1, the one tested, it keeps its own.

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
said "Parts missing."; it now asks for the disk that holds the part. On
a Mac with one floppy drive, the disk in the drive now comes out by
itself when the next part is not on it, and the MacExtract disk is asked
for only once, at launch. A
locked MacExtract floppy showed no icons, and on System 3.0 bombed when
its Helpers folder was opened; it now works locked. The icons are new.

Known limits. On System 6 and 3.0, a program installed after the
helpers shows the generic application icon instead of its own. On a Mac
with one floppy drive, extracting from one floppy onto another swaps the
two disks every few KB; extract onto a hard disk where there is one.
With one drive, opening MacExtract and choosing Open asks for fewer
disks than double-clicking an archive.

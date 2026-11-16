#!/bin/sh
# make_dist.sh — assemble the "bootstrap" distribution for getting MacExtract
# onto a classic Mac that has no unarchiver yet (chicken-and-egg: you can't
# ship the tool as a .sit if you need the tool to open a .sit).
#
# Produces, under dist/:
#   MacExtract.bin  — the application as UNCOMPRESSED MacBinary. Drop it on any
#                    Mac with a MacBinary-aware transfer (ImportFl, most terminal
#                    programs, or a network mount); no unarchiver required.
#   MacExtract.hqx  — the same application as BinHex 4.0, for a Mac that already
#                    has StuffIt Expander or BinHex, over a transfer that
#                    carries only text.
#   MacExtract-800K.img — an 800K HFS floppy image holding the application,
#                    the helpers folder and a TeachText "Read Me" written
#                    for the floppy (docs/floppy-read-me.txt). Write it to
#                    a real 800K floppy, or mount it in Mini vMac /
#                    Basilisk / SheepShaver.
#   MacExtract-1440K.img — the same volume at 1.44 MB, for a USB floppy drive,
#                    which writes MFM only and so cannot make an 800K GCR disk;
#                    a SuperDrive Mac mounts it (DECISIONS.md 2026-10-14,
#                    *the floppy a USB drive can write*).
#   MacExtract-400K.img — a 400K MFS floppy, MacExtract, the "Read Me" and the
#                    helpers zip, for a 64K-ROM Macintosh 512K with a Hard
#                    Disk 20.
#   MacExtract-*.dsk — each of the three as a Disk Copy 4.2 image
#                    (tools/mkdc42.py; DECISIONS.md 2026-11-07, *the floppies
#                    twice*).
#   MacExtract-Helpers.zip — the double-click helpers, one per creator
#                    (companion/helpers.tsv), in one zip MacExtract opens;
#                    also in a "MacExtract Helpers" folder on both disks.
#   README.txt     — the paragraphs above, for the download.
#
# Builds the application first (needs a Retro68 toolchain, and hfsutils for
# the 1.44 MB image and the round-trip check). Getting the result onto a real
# machine: MANUAL_TESTS.md, "Before you start".
#
# NOT REPRODUCIBLE, and that is not a bug: MacBinary carries the file's
# creation and modification dates, so two runs over identical code differ at
# offsets 93-98 and in the header CRC at 124-125. Everything from offset 128
# on — the application itself — is byte-identical. A diff in dist/ is
# therefore not evidence that the application changed; compare the payload.
set -e
cd "$(dirname "$0")/.."

# Checked before anything is built or written, so a machine without hfsutils
# stops here rather than leaving a dist/ with no 1.44 MB image in it.
for t in hformat hmount hcopy hattrib humount; do
    command -v "$t" >/dev/null 2>&1 || {
        echo "make_dist: $t not found — hfsutils is required" >&2; exit 1; }
done
command -v binhex >/dev/null 2>&1 || {
    echo "make_dist: binhex not found — macutils is required" >&2; exit 1; }

# hfsutils keeps its current-volume state in $HOME/.hcwd; each use below
# gets a scratch HOME of its own rather than the user's.
HFS_TMP=$(mktemp -d)
trap 'rm -rf "$HFS_TMP"' EXIT

# Build rather than pick up whatever is lying around. The first version of
# this script copied an existing build/, and the distribution silently went
# stale by a whole sink rewrite: the shipped .bin and .dsk still staged each
# output fork in RAM long after the tree had moved to streaming writes.
sh tools/build_mac.sh

SRC=build/mac
if [ ! -f "$SRC/MacExtract.bin" ] || [ ! -f "$SRC/MacExtract.dsk" ]; then
    echo "make_dist: no Mac build at $SRC — a Retro68 toolchain is required"
    echo "make_dist: (tools/build_mac.sh says where to get one)"
    exit 1
fi

mkdir -p dist

VERSION=$(sed -n 's/^#define UNC_VERSION "\(.*\)"/\1/p' include/macextract.h)
[ -n "$VERSION" ] || { echo "make_dist: no UNC_VERSION in include/macextract.h" >&2; exit 1; }

cat > dist/README.txt <<TXT
MacExtract v$VERSION — bootstrap distribution
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

v$VERSION opens four more kinds of file: Hampa Hug's MAR archives (.mar,
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
TXT
# Every disk's "Read Me" is its own short text, docs/floppy-read-me.txt, not
# README.txt (the maintainer, 2026-11-14: TeachText 1.2 refused README.txt
# on a Mac Plus); tools/mac_text.py converts it and refuses one over what
# TeachText opens. A MacBinary typed 'ttro'/'ttxt', TeachText's read-only
# document, as the Read Me on System 6.0.8's own disks, with a 'styl'
# resource SimpleText draws its headings from (the maintainer, 2026-11-16;
# DECISIONS.md 2026-11-16, *the Read Me in styles*).
python3 tools/mac_text.py docs/floppy-read-me.txt --markdown --disk HFS --name "Read Me" \
    -o "$HFS_TMP/readme-hfs.bin" >/dev/null
python3 tools/mac_text.py docs/floppy-read-me.txt --markdown --disk MFS --name "Read Me" \
    -o "$HFS_TMP/readme-mfs.bin" >/dev/null

cp "$SRC/MacExtract.bin" dist/MacExtract.bin
cp "$SRC/MacExtract.dsk" dist/MacExtract-800K.img
# macutils writes its own banner and LF; the spec's banner, which
# MacExtract's own sniffer looks for, and CR every 64 characters
# (reference/notes/binhex40_lewis.txt).
binhex dist/MacExtract.bin \
    | sed '1s/.*/(This file must be converted with BinHex 4.0)/' \
    | tr '\n' '\r' > dist/MacExtract.hqx

# Built from the MacBinary the way set_bundle_bit.py rebuilds the .dsk:
# `hcopy -m` carries the Finder flags, hasBundle included.
IMG=dist/MacExtract-1440K.img
rm -f "$IMG"
truncate -s 1474560 "$IMG"
HOME=$HFS_TMP hformat -l MacExtract "$IMG" >/dev/null
HOME=$HFS_TMP hmount "$IMG" >/dev/null
HOME=$HFS_TMP hcopy -m dist/MacExtract.bin ":"
HOME=$HFS_TMP humount >/dev/null
# The double-click helpers, one per creator companion/helpers.tsv lists: as
# one Finder-style zip, dist/MacExtract-Helpers.zip, which MacExtract itself
# opens, and in a "MacExtract Helpers" folder beside MacExtract on both
# disks (the maintainer, 2026-11-04; DECISIONS.md 2026-11-04, *the helpers
# in dist*). tools/check_helpers.py checks them;
# the toolchain is found as tools/build_mac.sh finds it, which has just
# succeeded.
if [ -n "$RETRO68" ] && [ -d "$RETRO68" ]; then
    TOOLCHAIN="$RETRO68"
elif command -v m68k-apple-macos-gcc >/dev/null 2>&1; then
    TOOLCHAIN="$(dirname "$(dirname "$(command -v m68k-apple-macos-gcc)")")"
else
    TOOLCHAIN=/opt/Retro68-build/toolchain
fi
cmake -B build/stub -S companion/stub \
    -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN/m68k-apple-macos/cmake/retro68.toolchain.cmake" >/dev/null
cmake --build build/stub >/dev/null
rm -rf dist/helpers
python3 companion/make_helpers.py build/stub/Stub.bin -o "$HFS_TMP/helpers" \
    --zip dist/MacExtract-Helpers.zip
for img in dist/MacExtract-800K.img "$IMG"; do
    HOME=$HFS_TMP hmount "$img" >/dev/null
    HOME=$HFS_TMP hcopy -m "$HFS_TMP/readme-hfs.bin" ":Read Me"
    HOME=$HFS_TMP hmkdir ":MacExtract Helpers"
    for h in "$HFS_TMP"/helpers/*.bin; do
        HOME=$HFS_TMP hcopy -m "$h" ":MacExtract Helpers:$(basename "$h" .bin)"
    done
    # The Desktop file listing MacExtract and the helpers, so a Mac with
    # no hard disk finds them on this floppy with it ejected (DECISIONS.md
    # 2026-11-04, *the floppy that is ready*).
    DIRID=$(HOME=$HFS_TMP hls -i -a ":" | awk '$2 == "MacExtract" && $3 == "Helpers" {print $1}')
    python3 companion/make_helpers.py build/stub/Stub.bin --desktop "$HFS_TMP/Desktop.bin" \
        --app dist/MacExtract.bin --dirid "$DIRID"
    HOME=$HFS_TMP hcopy -m "$HFS_TMP/Desktop.bin" ":Desktop"
    HOME=$HFS_TMP humount >/dev/null
    # Every icon placed and every window set (DECISIONS.md 2026-11-14, *the
    # floppy that works locked*): uninited, the Finder stacked the 18
    # helpers in one column (the maintainer's Mac Plus) and ran "MacExtract
    # Helpers" into "MacExtract" (6.0.8); an inited folder with no window
    # rectangle bombed System 3.0's Finder, ID = 04, on opening (measured).
    # Inited applications are fine: their bundles are in the Desktop file.
    python3 - "$img" <<'PY'
import struct, sys
sys.path.insert(0, "tools/vmac")
import hfscat
img = sys.argv[1]
V, H = b"MacExtract", b"MacExtract Helpers"
INITED = 0x0100
# DInfo at +22 of a cdrDirRec: frRect (top, left, bottom, right, global)
# +0, frFlags +8, frLocation (v, h) +10, frView +14; FInfo at +4 of a
# cdrFilRec: fdFlags +8, fdLocation +10 (hfscat.py). frView 0x0100 is
# icon view, as on Apple's System 6.0.8 "System Tools" disk.
def folder(path, rect, at=None):
    hfscat.patch(img, path, 22, struct.pack(">hhhh", *rect))
    hfscat.patch(img, path, 22 + 14, struct.pack(">H", 0x0100))
    if at:
        hfscat.patch(img, path, 22 + 8, struct.pack(">H", INITED))
        hfscat.patch(img, path, 22 + 10, struct.pack(">hh", *at))
def place(path, at):
    rec = [r for r in hfscat.records(open(img, "rb").read()) if r["path"] == path][0]
    hfscat.patch(img, path, 4 + 8, struct.pack(">H", rec["flags"] | INITED))
    hfscat.patch(img, path, 4 + 10, struct.pack(">hh", *at))
place((V, b"MacExtract"), (10, 20))
place((V, b"Read Me"), (10, 95))
names = sorted((r["path"][2] for r in hfscat.records(open(img, "rb").read())
                if len(r["path"]) == 3 and r["path"][1] == H), key=bytes.lower)
# Six across, alphabetical, 56 apart down: three rows showed in
# (110, 30)-(320, 428) with no scroll bars on 3.0, 6.0.8 and 7.0.1; each
# row past three moves the top up 56, the bottom kept (DECISIONS.md
# 2026-11-15, *the helpers for BinHex 4.0 and 5.0*).
rows = (len(names) + 5) // 6
folder((V, H), (110 - 56 * max(0, rows - 3), 30, 320, 428), at=(10, 175))
for i, n in enumerate(names):
    place((V, H, n), (10 + 56 * (i // 6), 20 + 62 * (i % 6)))
PY
done

# A 400K MFS floppy for a Macintosh 512K with a Hard Disk 20: a 64K ROM reads
# only MFS floppies, and MFS has no folders, so the helpers go as the zip,
# typed 'ZIP ' with MacExtract's creator to open in it (the maintainer,
# 2026-11-06; MANUAL_TESTS.md §6).
MFS=dist/MacExtract-400K.img
# Its Desktop file carries MacExtract's bundle and no 'APPL' list, as the
# Finders write one on MFS: without one, a locked 400K is refused on 3.0
# and 6.0.8 (DECISIONS.md 2026-11-14, *the floppy that works locked*;
# 7.0.1 lists a locked 400K empty with or without it).
python3 companion/make_helpers.py build/stub/Stub.bin --desktop "$HFS_TMP/DesktopMFS.bin" \
    --app dist/MacExtract.bin --mfs
python3 tools/vmac/mkmfs.py "$MFS" --name MacExtract dist/MacExtract.bin \
    "$HFS_TMP/DesktopMFS.bin:Desktop" "$HFS_TMP/readme-mfs.bin:Read Me" \
    --data dist/MacExtract-Helpers.zip MacExtract-Helpers.zip "ZIP MExt" \
    --place MacExtract 10 20 --place "Read Me" 10 95 \
    --place MacExtract-Helpers.zip 10 175 >/dev/null

# Each floppy again as a Disk Copy 4.2 image.
for k in 800K 1440K 400K; do
    python3 tools/mkdc42.py dist/MacExtract-$k.img dist/MacExtract-$k.dsk --name MacExtract
done

echo "make_dist: wrote dist/MacExtract.bin ($(wc -c < dist/MacExtract.bin) B),"
echo "make_dist:       dist/MacExtract.hqx ($(wc -c < dist/MacExtract.hqx) B),"
for k in 800K 1440K 400K; do
    echo "make_dist:       dist/MacExtract-$k.img ($(wc -c < dist/MacExtract-$k.img) B) and .dsk,"
done
echo "make_dist:       dist/MacExtract-Helpers.zip, dist/README.txt"

# Cheap proof that the three artifacts carry the same application: each
# image's copy round-trips back to a MacBinary whose resource fork — which is
# the whole of an APPL — matches the one in dist/MacExtract.bin byte for byte,
# with hasBundle still set. hfsutils does that through the catalog; it is
# checked for at the top, because a machine without it used to reach this
# point and die AFTER writing dist/, which read as "the build failed" when
# the artifacts were in fact sitting there unverified (2026-08-15).
for img in dist/MacExtract-800K.img "$IMG"; do
    HOME=$HFS_TMP hmount "$img" >/dev/null
    HOME=$HFS_TMP hcopy -m "MacExtract:MacExtract" "$HFS_TMP/roundtrip.bin"
    HOME=$HFS_TMP hcopy -m "MacExtract:Read Me" "$HFS_TMP/readme.bin"
    HOME=$HFS_TMP humount >/dev/null
    python3 - "$HFS_TMP/readme.bin" "$HFS_TMP/readme-hfs.bin" "$img" <<'PY'
import sys
r, w = open(sys.argv[1], 'rb').read(), open(sys.argv[2], 'rb').read()
# Both forks, padded as the MacBinary pads them, and their lengths.
ok = r[65:73] == b'ttrottxt' and r[83:91] == w[83:91] and r[128:] == w[128:]
print(f"make_dist: {sys.argv[3]} Read Me: {r[65:73].decode('mac_roman')!r}, "
      f"{int.from_bytes(r[83:87], 'big')} B and a {int.from_bytes(r[87:91], 'big')} B "
      f"resource fork, {'identical' if ok else 'DIFFERENT'}")
sys.exit(0 if ok else 1)
PY
    python3 tools/mac_text.py --verify "$HFS_TMP/readme.bin" >/dev/null
    python3 - "$HFS_TMP/roundtrip.bin" "$img" <<'PY'
import sys
a = open(sys.argv[1], 'rb').read()
b = open('dist/MacExtract.bin', 'rb').read()
rl = int.from_bytes(b[87:91], 'big')
same = a[128:128 + rl] == b[128:128 + rl]
flags = (a[73] << 8) | a[101]
print(f"make_dist: {sys.argv[2]} round-trip: {rl} B resource fork, "
      f"{'identical' if same else 'DIFFERENT'} to the MacBinary, "
      f"Finder flags 0x{flags:04X}")
sys.exit(0 if same and flags & 0x2000 else 1)
PY
    rm -f "$HFS_TMP/roundtrip.bin"
done
# The same for the MFS floppy, read back by mkmfs.py's own reader, and its
# zip byte for byte with its type and creator.
python3 tools/vmac/mkmfs.py "$MFS" --extract MacExtract "$HFS_TMP/roundtrip.bin" >/dev/null
python3 tools/vmac/mkmfs.py "$MFS" --extract MacExtract-Helpers.zip "$HFS_TMP/zip.bin" >/dev/null
python3 tools/vmac/mkmfs.py "$MFS" --extract "Read Me" "$HFS_TMP/readme.bin" >/dev/null
python3 - "$HFS_TMP/roundtrip.bin" "$HFS_TMP/zip.bin" "$MFS" "$HFS_TMP/readme.bin" "$HFS_TMP/readme-mfs.bin" <<'PY'
import sys
a = open(sys.argv[1], 'rb').read()
b = open('dist/MacExtract.bin', 'rb').read()
z = open(sys.argv[2], 'rb').read()
want = open('dist/MacExtract-Helpers.zip', 'rb').read()
r = open(sys.argv[4], 'rb').read()
rl = int.from_bytes(b[87:91], 'big')
same = a[128:128 + rl] == b[128:128 + rl]
flags = (a[73] << 8) | a[101]
zl = int.from_bytes(z[83:87], 'big')
zsame = z[65:73] == b'ZIP MExt' and z[128:128 + zl] == want
w = open(sys.argv[5], 'rb').read()
rsame = r[65:73] == b'ttrottxt' and r[83:91] == w[83:91] and r[128:] == w[128:]
print(f"make_dist: {sys.argv[3]} round-trip: {rl} B resource fork, "
      f"{'identical' if same else 'DIFFERENT'} to the MacBinary, "
      f"Finder flags 0x{flags:04X}; helpers zip {z[65:73].decode('mac_roman')!r}, "
      f"{'identical' if zsame else 'DIFFERENT'}; Read Me "
      f"{r[65:73].decode('mac_roman')!r}, {'identical' if rsame else 'DIFFERENT'}")
sys.exit(0 if same and flags & 0x2000 and zsame and rsame else 1)
PY
python3 tools/mac_text.py --verify "$HFS_TMP/readme.bin" >/dev/null
# And each Disk Copy image read back: its header, its checksum, and the raw
# disk it was made from.
for k in 800K 1440K 400K; do
    python3 tools/mkdc42.py --check dist/MacExtract-$k.dsk dist/MacExtract-$k.img
done

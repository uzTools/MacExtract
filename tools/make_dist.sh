#!/bin/sh
# make_dist.sh — assemble the "bootstrap" distribution for getting MacExtract
# onto a classic Mac that has no unarchiver yet (chicken-and-egg: you can't
# ship the tool as a .sit if you need the tool to open a .sit).
#
# Produces, under dist/:
#   MacExtract.bin  — the application as UNCOMPRESSED MacBinary. Drop it on any
#                    Mac with a MacBinary-aware transfer (ImportFl, most terminal
#                    programs, or a network mount); no unarchiver required.
#   MacExtract.dsk  — an 800K HFS floppy image holding the application. Write it
#                    to a real 800K floppy, or mount it in Mini vMac / Basilisk /
#                    SheepShaver, then drag the app onto your startup disk.
#   README.txt     — the two paragraphs above, for the download.
#
# Builds the application first (needs a Retro68 toolchain). Getting the result
# onto a real machine: MANUAL_TESTS.md, "Before you start".
#
# NOT REPRODUCIBLE, and that is not a bug: MacBinary carries the file's
# creation and modification dates, so two runs over identical code differ at
# offsets 93-98 and in the header CRC at 124-125. Everything from offset 128
# on — the application itself — is byte-identical. A diff in dist/ is
# therefore not evidence that the application changed; compare the payload.
set -e
cd "$(dirname "$0")/.."

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
cp "$SRC/MacExtract.bin" dist/MacExtract.bin
cp "$SRC/MacExtract.dsk" dist/MacExtract.dsk
VERSION=$(sed -n 's/^#define UNC_VERSION "\(.*\)"/\1/p' include/macextract.h)
[ -n "$VERSION" ] || { echo "make_dist: no UNC_VERSION in include/macextract.h" >&2; exit 1; }

cat > dist/README.txt <<TXT
MacExtract v$VERSION — bootstrap distribution
==========================================

A bare Classic Mac has no way to open a .sit/.cpt/.hqx until it HAS an
unarchiver, so MacExtract ships in two forms that need no unarchiver:

  MacExtract.bin  The application as uncompressed MacBinary. Transfer it to
                  the Mac with any MacBinary-aware method (ImportFl, a terminal
                  program's MacBinary receive, an AppleShare/AFP mount). The
                  wrapper unpacks to the real application on arrival.

  MacExtract.dsk  An 800K HFS floppy image containing the application. Write it
                  to a physical 800K floppy (a Mac Plus reads 400K/800K GCR
                  floppies only), or mount it in an emulator (Mini vMac,
                  Basilisk II, SheepShaver), then drag MacExtract onto your
                  startup disk.

Floor target: System 3.0 on a 1 MB Mac Plus (68000) -- the system the Plus
shipped with in January 1986. It also runs in 512 KB, on a Macintosh 512Ke.
The same binary runs unchanged through Mac OS 9 and adapts its memory use to
the machine at runtime, so there is one download for every Mac.

Two things to know about the smallest machines. On System 3.0 the Open dialog
ignores Command-period, so close it with the Cancel button; Command-period
still stops an extraction everywhere. And in 512 KB, a StuffIt 5 archive
written with large blocks will not fit -- a block has to be in memory whole,
and its size was fixed when the archive was made. Those entries are skipped
with a message and the rest of the archive still comes out. Every other format
fits in 512 KB, and with 1 MB the question does not arise.

What it opens: StuffIt (.sit, classic and 5.x), Compact Pro (.cpt), BinHex
(.hqx), MacBinary, PackIt (.pit), DiskDoubler (.dd, DDAR, DDA2), Now Compress,
StuffIt SpaceSaver, Alysis SuperDisk! (.X), ARC (.arc), LZH/LHA (.lzh, .lha,
MacLHA's included), uuencoded files (.uu), btoa (.ascii), base64 and files
mailed as MIME attachments (.b64, .mim -- both forks, where the message
carried them), AppleSingle/AppleDouble, zip, gzip, tar and Unix compress (.Z).
Nested files like .sit.hqx or .tar.Z are unwrapped automatically, by looking
inside them
rather than trusting the name, and a .hqx holding several files -- one
newsgroup posting, several attachments -- gives you all of them. Resource
forks, type and creator codes and dates all survive, so an extracted
application simply runs. StuffIt X, AppleLink packages and the PC-side
archives -- RAR, 7-Zip, xz, bzip2, Zstandard, lzip, lrzip, Cabinet, WIM,
Zoo, ARJ, cpio and ar --
are named rather than opened: you are told what the file is instead of
being left with something that looks like a damaged download.

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
850 KB every archive in the test sample comes out whole. Below that it still
opens everything and lists what is inside; entries too big to fit are named,
one message each, and the rest extract. If it does run short, it tells you
how much more to type into that box.

Using it: open an archive, then say which folder the files should go into.
That second dialog opens in the archive's own folder, so pressing Return
puts them next to it; click Drive to send them to another disk instead.

When a run ends, anything that had to change on the way is listed: a name too
long for HFS (31 characters max), two folders that ended up sharing a
shortened name, an entry that could not be extracted and what was wrong with
it. Save as Text files the whole thing as a document. A run with nothing to
report just says so, as before.

If a Compact Pro or zip archive carries a note -- the comment whoever
made it typed in -- it is written into that folder as a text file called
Comments, rather than thrown away with the wrapper.

Very occasionally a file uses a compression method this version does not
know. That entry is skipped and the rest of the archive still comes out,
and the message says so rather than blaming your machine. Those files are
worth reporting -- most of the methods here were added because somebody
sent one -- and the Linux version names the method for you, which is the
part that makes a report worth sending.

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

A file that arrived as several mail messages is joined too. Mail gateways
used to cut anything large into numbered pieces (message/partial); open any
one of them and the rest are found beside it, whatever they are called, and
a Macintosh file mailed that way comes back with both its forks.

Every archive in the test sample extracts byte-exact on a 1 MB Mac Plus,
StuffIt 5 (Arsenic) included. Arsenic is slow on a 68000 — 12 minutes for a
200 KB archive, 21 for the largest tested — and the progress dialog
shows a time estimate for that reason. Everything else takes seconds to a few
minutes: a 280 KB StuffIt archive is about a minute on a 7 MHz Mac Plus, which
is what StuffIt Expander 4.0.2 takes on the same machine and the same file. If
an entry genuinely will not fit, that entry is skipped with a message and the
rest of the archive still extracts.

Verified on emulators only: System 3.0, System 6.0.8 and System 7.0.1 on a Mac
Plus under Mini vMac, and Mac OS 9.2 on emulated PowerPC, where every
extraction is checked byte for byte against the same engine on Linux. No
physical Macintosh has ever run it. Worth knowing before you commit a floppy
to it.

License: LGPL-2.1-or-later. See LICENSE and NOTICE in the source tree.
TXT

echo "make_dist: wrote dist/MacExtract.bin ($(wc -c < dist/MacExtract.bin) B),"
echo "make_dist:       dist/MacExtract.dsk ($(wc -c < dist/MacExtract.dsk) B), dist/README.txt"

# Cheap proof that the two artifacts carry the same application: the .dsk's
# copy round-trips back to a MacBinary whose resource fork — which is the
# whole of an APPL — matches the one in dist/MacExtract.bin byte for byte.
#
# hfsutils does that properly, through the catalog. Without it the check
# still runs, weaker: the fork must appear verbatim in the image. A machine
# with no hfsutils used to reach this line and die with `hmount: not found`
# AFTER writing dist/, which read as "the build failed" when the artifacts
# were in fact sitting there unverified (2026-08-15).
if command -v hmount >/dev/null 2>&1; then
    HOME_SAVE=$HOME
    HOME=$(mktemp -d); export HOME
    hmount dist/MacExtract.dsk >/dev/null
    hcopy -m "MacExtract:MacExtract" "$HOME/roundtrip.bin"
    humount >/dev/null
    python3 - "$HOME/roundtrip.bin" <<'PY'
import sys
a = open(sys.argv[1], 'rb').read()
b = open('dist/MacExtract.bin', 'rb').read()
rl = int.from_bytes(b[87:91], 'big')
same = a[128:128 + rl] == b[128:128 + rl]
print(f"make_dist: .dsk round-trip: {rl} B resource fork, "
      f"{'identical' if same else 'DIFFERENT'} to the MacBinary")
sys.exit(0 if same else 1)
PY
    rm -rf "$HOME"
    HOME=$HOME_SAVE; export HOME
else
    python3 - <<'PY'
import sys
b = open('dist/MacExtract.bin', 'rb').read()
img = open('dist/MacExtract.dsk', 'rb').read()
rl = int.from_bytes(b[87:91], 'big')
fork = b[128:128 + rl]
found = fork in img
print(f"make_dist: no hfsutils, weaker check: {rl} B resource fork "
      f"{'found verbatim in' if found else 'NOT FOUND in'} the .dsk "
      f"(the catalog itself is unchecked)")
sys.exit(0 if found else 1)
PY
fi

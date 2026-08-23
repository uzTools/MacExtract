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
if [ ! -f "$SRC/unclassic.bin" ] || [ ! -f "$SRC/unclassic.dsk" ]; then
    echo "make_dist: no Mac build at $SRC — a Retro68 toolchain is required"
    echo "make_dist: (tools/build_mac.sh says where to get one)"
    exit 1
fi

mkdir -p dist
cp "$SRC/unclassic.bin" dist/unclassic.bin
cp "$SRC/unclassic.dsk" dist/unclassic.dsk
VERSION=$(sed -n 's/^#define UNC_VERSION "\(.*\)"/\1/p' include/unclassic.h)
[ -n "$VERSION" ] || { echo "make_dist: no UNC_VERSION in include/unclassic.h" >&2; exit 1; }

cat > dist/README.txt <<TXT
unclassic v$VERSION — bootstrap distribution
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
Alysis SuperDisk! (.X), ARC (.arc), uuencoded files (.uu),
AppleSingle/AppleDouble, zip, gzip, tar and Unix compress (.Z). Nested files
like .sit.hqx or .tar.Z are unwrapped automatically, by looking inside them
rather than trusting the name, and a .hqx holding several files -- one
newsgroup posting, several attachments -- gives you all of them. Resource
forks, type and creator codes and dates all survive, so an extracted
application simply runs. StuffIt X, LZH, Disk Copy 4.2 and AppleLink
packages are recognised and named, not extracted; encrypted archives are
out of scope.

A StuffIt SpaceSaver file is recognised and its contents named, but this
application does not expand one. SpaceSaver compresses starting from a
dictionary that lives inside SpaceSaver itself, so a Mac that has
SpaceSaver opens these files without any help, and a Mac that does not
has no dictionary to read. The Linux tool takes a copy of it with
--preset, which is the case that matters: a file that has travelled.

Using it: open an archive, then say which folder the files should go into.
That second dialog opens in the archive's own folder, so pressing Return
puts them next to it; click Drive to send them to another disk instead.

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
TXT

echo "make_dist: wrote dist/unclassic.bin ($(wc -c < dist/unclassic.bin) B),"
echo "make_dist:       dist/unclassic.dsk ($(wc -c < dist/unclassic.dsk) B), dist/README.txt"

# Cheap proof that the two artifacts carry the same application: the .dsk's
# copy round-trips back to a MacBinary whose resource fork — which is the
# whole of an APPL — matches the one in dist/unclassic.bin byte for byte.
#
# hfsutils does that properly, through the catalog. Without it the check
# still runs, weaker: the fork must appear verbatim in the image. A machine
# with no hfsutils used to reach this line and die with `hmount: not found`
# AFTER writing dist/, which read as "the build failed" when the artifacts
# were in fact sitting there unverified (2026-08-15).
if command -v hmount >/dev/null 2>&1; then
    HOME_SAVE=$HOME
    HOME=$(mktemp -d); export HOME
    hmount dist/unclassic.dsk >/dev/null
    hcopy -m "unclassic:unclassic" "$HOME/roundtrip.bin"
    humount >/dev/null
    python3 - "$HOME/roundtrip.bin" <<'PY'
import sys
a = open(sys.argv[1], 'rb').read()
b = open('dist/unclassic.bin', 'rb').read()
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
b = open('dist/unclassic.bin', 'rb').read()
img = open('dist/unclassic.dsk', 'rb').read()
rl = int.from_bytes(b[87:91], 'big')
fork = b[128:128 + rl]
found = fork in img
print(f"make_dist: no hfsutils, weaker check: {rl} B resource fork "
      f"{'found verbatim in' if found else 'NOT FOUND in'} the .dsk "
      f"(the catalog itself is unchecked)")
sys.exit(0 if found else 1)
PY
fi

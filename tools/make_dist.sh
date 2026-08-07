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
# Builds the application first (needs a Retro68 toolchain). See MANUAL_TESTS.md.
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
cat > dist/README.txt <<'TXT'
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

Every archive in the test sample extracts byte-exact on a 1 MB Mac Plus,
StuffIt 5 (Arsenic) included. Arsenic is slow on a 68000 — 16 minutes for a
200 KB archive, half an hour for the largest tested — and the progress dialog
shows a time estimate for that reason. Everything else takes seconds to a few
minutes. If an entry genuinely will not fit, that entry is skipped with a
message and the rest of the archive still extracts.

License: LGPL-2.1-or-later. See LICENSE and NOTICE in the source tree.
TXT

echo "make_dist: wrote dist/unclassic.bin ($(wc -c < dist/unclassic.bin) B),"
echo "make_dist:       dist/unclassic.dsk ($(wc -c < dist/unclassic.dsk) B), dist/README.txt"

# Cheap proof that the two artifacts carry the same application: the .dsk's
# copy round-trips back to a MacBinary whose resource fork — which is the
# whole of an APPL — matches the one in dist/unclassic.bin byte for byte.
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

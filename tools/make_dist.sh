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
MacExtract v$VERSION
==================

Which file to download, how to get it onto your Mac and what it opens: https://github.com/uzTools/MacExtract#readme. What earlier versions changed: CHANGES.md in the same place.

## New formats

- Hampa Hug's MAR archives (.mar, .mac, and .mar.lz4).
- The floppies of Apple Backup, a Performa's backup, read as one set even with disks missing.
- The Tomes on Apple's install disks, System 7.5 to Mac OS 9.
- The fonts and network software Apple's Installer keeps compressed in a file's resource fork.
- Netscape's .xpi installer packages, which are zips, now carry MacExtract's archive icon.

## The double-click helpers

- New in this release: the "MacExtract Helpers" folder on the 800K and 1.44 MB floppies, and MacExtract-Helpers.zip.
- Each stands in for a program that made archives (StuffIt, Compact Pro, DiskDoubler, BinHex and others), so that double-clicking one of its archives opens it in MacExtract, on every System from 3.0 to Mac OS 9.
- A helper shares its creator with the program it stands in for, and never takes that program's icon.
- Macintosh Easy Open and Mac OS 9's File Exchange list MacExtract, not the helpers, for an archive whose program is missing.
- A file DiskDoubler compressed in place opens through the "DiskDblr" helper, which also gives it the archive icon.

## Also new

- New icons.
- MacExtract takes about 7 KB less memory, which every archive gets instead.
- On a Mac Plus, StuffIt's method 5, zip's Implode and the LZH methods decode between a fifth and a third faster, and a zip stored without compression about three times faster.
- In 512 KB under System 6.0.8, 72 of the 74 test archives come out, against 68 before.

## Fixed

- On a Mac Plus, an SE, a Classic or any other Macintosh with a 68000, v0.45.0 bombed with an "address error" as it asked where the files go.
- On a Macintosh 512K, v0.45.0 bombed at launch; it starts again.
- After a password was asked for, the progress bar was drawn at the top left of the screen.
- A 64th character typed in the password dialog went past its end.
- A disk that fills up now says "Disk full." under the file it could not write, and a disk that cannot be read is no longer reported as an incomplete archive.
- A file and a folder of the same name no longer make everything in the folder fail: the folder is numbered.
- A Get Info comment longer than the Finder keeps is cut, and the report says so.
- Cancel answers sooner in the slow formats, and its button flashes.
- A BinHex file with lines longer than 256 characters lost a character from each.
- Six MacBinary files written without the usual padding, and tar archives that set their dates once for every file, open as they should.
- A Compact Pro set or a split zip opened without its last part beside it said "Parts missing."; it now asks for the disk that holds the part.
- On a Mac with one floppy drive, the disk in the drive now comes out by itself when the next part is not on it, and the MacExtract disk is asked for only once, at launch.
- A locked MacExtract floppy showed no icons, and on System 3.0 bombed when its Helpers folder was opened; it now works locked.

## Current limitations

- On System 6 and 3.0, a program installed after the helpers shows the generic application icon instead of its own; System 7.6.1 keeps its own.
- On a Mac with one floppy drive, extracting from one floppy onto another swaps the two disks every few KB; extract onto a hard disk if you have one.
- With one floppy drive, opening MacExtract and choosing Open asks for fewer disks than double-clicking an archive.
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

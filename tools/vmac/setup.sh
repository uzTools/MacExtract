#!/bin/sh
# setup.sh — one-time build of the Mini vMac on-Mac test harness.
#
# Everything this fetches is either GPL source (Mini vMac) or Apple
# copyrighted material (the Mac Plus ROM, System 6.0.8) that must NOT be
# committed — exactly the rule fixtures/ follows. So this script fetches by
# URL and verifies by SHA-256 instead, and drops it all in a work directory
# outside the repository tree. NOT under build/: `make clean` removes that
# whole tree, and re-downloading 80 MB because someone ran the test suite is
# not a reasonable thing to do to anybody.
#
#   $UNC_VMAC_HOME   (default: ~/.cache/macextract/vmac/)
#     vMac.ROM          128 KB Macintosh Plus ROM (checksum 4D1F8172)
#     System6.hfv       20 MB System 6.0.8 hard-disk image
#     Sys7.img          10 MB System 7.0.1 hard-disk image (the System 7 tier)
#     Sys30.img         800 KB System 3.0 / Finder 5.1 floppy (the System 3 tier)
#     mv-4M/minivmac    4 MB Mac Plus, all out
#     mv-1M/minivmac    1 MB Mac Plus, all out (the floor target)
#     mv-4M-1x/minivmac 4 MB Mac Plus, authentic 7 MHz
#     mv-1M-1x/minivmac 1 MB Mac Plus, authentic 7 MHz
#     mv-512Ke/minivmac 512 KB Macintosh 512Ke, all out (the 512 KB tier)
#     mv-512K/minivmac  512 KB Macintosh 512K, 64 KB ROM (the negative below)
#     Mac512K.ROM       64 KB Macintosh 512K ROM (checksum 28BA4E50)
#     Mac128K.ROM       64 KB Macintosh 128K ROM (checksum 28BA61CE)
#
# Six emulator builds exist because the MACHINE, its RAM size and its speed are
# all COMPILE-time options in Mini vMac, and this project makes claims along
# every one of those axes: 1 MB is the floor target, only a 1x build may be
# quoted for timing, and the two 512 KB machines differ in their ROM alone.
#
# Usage:  tools/vmac/setup.sh        (idempotent; skips what is already there)
set -e
cd "$(dirname "$0")/../.."
REPO=$(pwd)
VMAC_HOME=${UNC_VMAC_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/macextract/vmac}
mkdir -p "$VMAC_HOME"
cd "$VMAC_HOME"

# ---- sources, with the hashes this harness was validated against ----------
MV_URL=https://www.gryphel.com/d/minivmac/minivmac-36.04/minivmac-36.04.src.tgz
MV_SHA=9b7343cec87723177a203e69ad3baf20f49b4e8f03619e366c4bf2705167dfa4

# Mac Plus ROM v3 (the last Mac Plus ROM; Mini vMac wants exactly this one),
# extracted from the Internet Archive's Mac ROM collection.
ROM_URL=https://archive.org/download/mac_rom_archive_-_as_of_8-19-2011/mac_rom_archive_-_as_of_8-19-2011.zip
ROM_MEMBER='4D1F8172 - MacPlus v3.ROM'
ROM_SHA=dd908e2b65772a6b1f0c859c24e9a0d3dcde17b1c6a24f4abd8955846d7895e7

# A stock System 6.0.8 hard-disk image. mkboot.py strips it back to
# System + Finder, so the extras it ships with do not affect any result.
SYS_URL=https://archive.org/download/system-6_202607/System6.hfv
SYS_SHA=6be139b315cb61f0b482f0ef1deb35ff35a5ae2a35e04d407f5bd1d4b333d749

# A stock System 7.0.1 hard-disk image, for the System 7 tier. 7.0.1 rather
# than 7.1 because 7.1 survives only as floppy sets and a beta ISO, and
# installing from emulated floppies is hours of GUI automation for a system
# that differs in nothing this project tests. What matters is that this is
# System 7 and not 6: Standard File hands back a WORKING DIRECTORY reference
# rather than a volume refNum, and the Process Manager is always running, so
# the 'SIZE' partition governs the launch. Neither is reachable on 6.0.8.
# Mini vMac's Mac Plus supports up to 7.5.5, so this runs on the same 68000.
SYS7_URL=https://archive.org/download/AppleMacintoshSystem701/System7_0_1.img
SYS7_SHA=068cdf59dd8254546f94231cbb591cd522826083a039b4545670458017925543

check() { echo "$2  $1" | sha256sum -c - >/dev/null 2>&1; }

fetch() {   # fetch <url> <dest> <sha256>
    if [ -f "$2" ] && check "$2" "$3"; then echo "have $2"; return 0; fi
    echo "fetching $2"
    curl -fsSL -o "$2.part" "$1"
    check "$2.part" "$3" || {
        echo "setup: SHA-256 mismatch for $2 (got $(sha256sum <"$2.part" | cut -d' ' -f1))" >&2
        echo "setup: the upstream file changed; verify it by hand before trusting it" >&2
        exit 1; }
    mv "$2.part" "$2"
}

# System Tools 1.0: System 3.0 / Finder 5.1, the disk the Macintosh Plus
# shipped with in January 1986 and the oldest system a Plus can boot. An 800K
# HFS floppy, not a hard-disk image — that is what this system came on, and
# tools/vmac/sys30.py boots the application from it. System 3.0 IGNORES the
# boot blocks' shell name, so that harness launches by double-click instead
# of by mkboot.py's usual shell replacement; its header says why.
SYS30_URL=https://archive.org/download/30_20230725/30.img
SYS30_SHA=73048ab3edc772619f4fdf3e9e2c61bcb9ad55fa6c10732c980bd17da427646c

fetch "$MV_URL"  minivmac.src.tgz "$MV_SHA"
fetch "$SYS_URL"  System6.hfv     "$SYS_SHA"
fetch "$SYS7_URL" Sys7.img       "$SYS7_SHA"
fetch "$SYS30_URL" Sys30.img     "$SYS30_SHA"

# System 1.1 (April 1984) on a 400K MFS floppy: the file system a 64K ROM has.
# A true Macintosh 512K Sad Macs on every HFS volume and boots this one, which
# is what makes the 64K-ROM negative measurable rather than asserted
# (FORMATS.md, *A true Macintosh 512K*).
SYS11_URL="https://archive.org/download/system-1.1_apr1984/System%20Disk.img"
SYS11_SHA=b0a35cfb484dd91c70e5a5a16e382f1d1ec41b87b5f8ebeaddd8da643c8ce5ef

fetch "$SYS11_URL" Sys11.img     "$SYS11_SHA"

if [ -f vMac.ROM ] && check vMac.ROM "$ROM_SHA"; then
    echo "have vMac.ROM"
else
    echo "fetching vMac.ROM (from a 55 MB ROM collection — one member is used)"
    curl -fsSL -o macroms.zip.part "$ROM_URL"
    mv macroms.zip.part macroms.zip
    python3 - "$ROM_MEMBER" <<'PY'
import zipfile, sys
open("vMac.ROM", "wb").write(zipfile.ZipFile("macroms.zip").read(sys.argv[1]))
PY
    check vMac.ROM "$ROM_SHA" || { echo "setup: ROM SHA-256 mismatch" >&2; exit 1; }
    rm -f macroms.zip
fi

# The 64 KB ROM of a real Macintosh 512K. Kept because the NEGATIVE needs to be
# reproducible: that machine boots normally with no disk and Sad Macs on an HFS
# volume, which is how "512 KB is enough, 64 KB of ROM is not" was established
# (FORMATS.md, *512 KB machines*). Nothing routine uses it. Fetched as one
# member of the same collection the Plus ROM comes from, by direct URL — the
# whole 55 MB zip is not needed for it.
ROM512_URL="https://archive.org/download/mac_rom_archive_-_as_of_8-19-2011/mac_rom_archive_-_as_of_8-19-2011.zip/28BA4E50%20-%20Macintosh-512k.ROM"
ROM512_SHA=fe6a1ceff5b3eefe32f20efea967cdf8cd4cada291ede040600e7f6c9e2dfc0e

# Apple's own 64 KB ROM from the machine before it, for the A/B that rules the
# ROM REVISION out: both fail identically, so the Sad Mac is not the 512K's ROM.
ROM128_URL="https://archive.org/download/mac_rom_archive_-_as_of_8-19-2011/mac_rom_archive_-_as_of_8-19-2011.zip/28BA61CE%20-%20Macintosh-128k.ROM"
ROM128_SHA=13fe8312cf6167a2bb4351297b48cc1ee29c523b788e58270434742bfeda864c

fetch "$ROM512_URL" Mac512K.ROM "$ROM512_SHA"
fetch "$ROM128_URL" Mac128K.ROM "$ROM128_SHA"

# ---- build the emulators --------------------------------------------------
# Mini vMac's setup tool emits a shell script that writes the config headers
# and a Makefile; -speed a is "all out" (see run.py --speed for why the
# default is NOT authentic 1x).
build_mv() {    # build_mv <dir> <memsize> <speed>
    [ -x "$1/minivmac" ] && { echo "have $1/minivmac"; return 0; }
    rm -rf "$1"
    mkdir -p "$1"
    tar xzf minivmac.src.tgz -C "$1" --strip-components=1
    ( cd "$1"
      gcc -o setup_t setup/tool.c
      ./setup_t -t lx64 -m Plus -mem "$2" -speed "$3" -as 0 -bg 1 \
                -sound 0 -magnify 0 -drives 6 -n "macextract-$2" > setup.sh
      bash setup.sh >/dev/null
      make >/dev/null 2>&1 )
    [ -x "$1/minivmac" ] || { echo "setup: failed to build $1/minivmac" >&2; exit 1; }
    echo "built $1/minivmac"
}

# 'a' = all out, as fast as the host allows: what the fixture sweeps use,
# because correctness does not depend on speed and 44 fixtures x 2 memory
# sizes at Mac Plus speed would take all day.
build_mv mv-4M 4M a
build_mv mv-1M 1M a

# 'z' = 1x, authentic 7 MHz Mac Plus timing. Needed for anything that has to
# observe the machine WHILE it works — the progress dialog and Cmd-. cancel
# are invisible at all-out speed, because the extraction is over before a
# screenshot can be taken — and it is the only build any timing claim may be
# drawn from.
build_mv mv-4M-1x 4M z

# 1 MB at 1x. Added 2026-08-07: the StuffIt 5 decoder only falls back to its
# low-memory inverse BWT when memory is tight, so the cost of that fallback
# cannot be timed on a 4 MB machine — it never takes that path there — and
# cannot be timed on mv-1M either, which is all-out. Both existing 1x claims
# and both existing 1 MB claims needed this fourth combination.
build_mv mv-1M-1x 1M z

# A Macintosh 512Ke: 512 KB and the same Plus ROM, which is the smallest
# machine this application runs on at all. `-m 512Ke` is a different MODEL, not
# just a smaller memory size, so build_mv cannot make it.
if [ -x mv-512Ke/minivmac ]; then
    echo "have mv-512Ke/minivmac"
else
    rm -rf mv-512Ke
    mkdir -p mv-512Ke
    tar xzf minivmac.src.tgz -C mv-512Ke --strip-components=1
    ( cd mv-512Ke
      gcc -o setup_t setup/tool.c
      ./setup_t -t lx64 -m 512Ke -mem 512K -speed a -as 0 -bg 1 \
                -sound 0 -magnify 0 -drives 6 -n "macextract-512Ke" > setup.sh
      bash setup.sh >/dev/null
      make >/dev/null 2>&1 )
    [ -x mv-512Ke/minivmac ] || { echo "setup: failed to build mv-512Ke" >&2; exit 1; }
    echo "built mv-512Ke/minivmac"
fi

# A true Macintosh 512K: 512 KB of RAM behind a 64 KB ROM. Nothing routine
# runs on it — it never reaches the application — and it is built anyway so
# that the negative can be re-taken rather than quoted (tools/vmac/README.md,
# *512 KB machines*). Mini vMac has no plain `512K` model: `-m 128K` is the
# 64K-ROM machine and `-mem 512K` is what makes it a 512K rather than a 128K.
if [ -x mv-512K/minivmac ]; then
    echo "have mv-512K/minivmac"
else
    rm -rf mv-512K
    mkdir -p mv-512K
    tar xzf minivmac.src.tgz -C mv-512K --strip-components=1
    ( cd mv-512K
      gcc -o setup_t setup/tool.c
      ./setup_t -t lx64 -m 128K -mem 512K -speed a -as 0 -bg 1 \
                -sound 0 -magnify 0 -drives 6 -n "macextract-512K" > setup.sh
      bash setup.sh >/dev/null
      make >/dev/null 2>&1 )
    [ -x mv-512K/minivmac ] || { echo "setup: failed to build mv-512K" >&2; exit 1; }
    echo "built mv-512K/minivmac"
fi

echo "setup: ready in $VMAC_HOME"

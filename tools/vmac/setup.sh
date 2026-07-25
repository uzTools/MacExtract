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
#   $UNC_VMAC_HOME   (default: ~/.cache/unclassic/vmac/)
#     vMac.ROM          128 KB Macintosh Plus ROM (checksum 4D1F8172)
#     System6.hfv       20 MB System 6.0.8 hard-disk image
#     mv-4M/minivmac    emulator built for a 4 MB Mac Plus
#     mv-1M/minivmac    emulator built for a 1 MB Mac Plus (the floor target)
#
# Two emulator builds exist because Mini vMac's RAM size is a COMPILE-time
# option, and the 1 MB machine is the project's floor target.
#
# Usage:  tools/vmac/setup.sh        (idempotent; skips what is already there)
set -e
cd "$(dirname "$0")/../.."
REPO=$(pwd)
VMAC_HOME=${UNC_VMAC_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/unclassic/vmac}
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

fetch "$MV_URL"  minivmac.src.tgz "$MV_SHA"
fetch "$SYS_URL" System6.hfv      "$SYS_SHA"

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

# ---- build the two emulators ---------------------------------------------
# Mini vMac's setup tool emits a shell script that writes the config headers
# and a Makefile; -speed a is "all out" (see run.py --speed for why the
# default is NOT authentic 1x).
build_mv() {    # build_mv <dir> <memsize>
    [ -x "$1/minivmac" ] && { echo "have $1/minivmac"; return 0; }
    rm -rf "$1"
    mkdir -p "$1"
    tar xzf minivmac.src.tgz -C "$1" --strip-components=1
    ( cd "$1"
      gcc -o setup_t setup/tool.c
      ./setup_t -t lx64 -m Plus -mem "$2" -speed a -as 0 -bg 1 \
                -sound 0 -magnify 0 -drives 6 -n "unclassic-$2" > setup.sh
      bash setup.sh >/dev/null
      make >/dev/null 2>&1 )
    [ -x "$1/minivmac" ] || { echo "setup: failed to build $1/minivmac" >&2; exit 1; }
    echo "built $1/minivmac"
}

build_mv mv-4M 4M
build_mv mv-1M 1M

echo "setup: ready in $VMAC_HOME"

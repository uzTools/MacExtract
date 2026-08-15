#!/bin/sh
# get_arc.sh — fetch a real ARC encoder, for fixtures nothing here writes.
#
# tools/run_arc.py grades our decoder against `unar` on archives that
# tools/synth_arc.py generates. That covers methods 1-9, but every byte
# of them came out of this repository. Debian's `arc` 5.21q is an actual
# ARC implementation: it writes methods 2, 4, 8 and 9 (and 9 only with
# the `q` switch), so it contributes archives whose layout owes nothing
# to our reading of the format.
#
# Same arrangement as tools/build_macunpack.sh: an oracle assembled on
# demand, never committed. The binary lands in build/arc/, which is
# ignored; run_arc.py picks it up if it is there and says so if it is
# not.
#
# License: LGPL-2.1-or-later. See LICENSE and NOTICE.
set -e
cd "$(dirname "$0")/.."

if [ -x build/arc/usr/bin/arc ]; then
    echo "get_arc: already present at build/arc/usr/bin/arc"
    exit 0
fi

mkdir -p build/arc
cd build/arc
apt-get download arc >/dev/null 2>&1 || {
    echo "get_arc: could not download the arc package" >&2
    exit 1
}
dpkg-deb -x arc_*.deb .
echo "get_arc: build/arc/usr/bin/arc"

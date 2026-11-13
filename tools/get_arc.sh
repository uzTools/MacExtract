#!/bin/sh
# get_arc.sh — fetch a real ARC encoder, for fixtures nothing here writes.
#
# tests/harness/run_arc.py grades our decoder against `unar` on archives that
# tools/synth_arc.py generates. That covers methods 1-9, but every byte
# of them came out of this repository. Debian's `arc` 5.21q is an actual
# ARC implementation: it writes methods 2, 4, 8 and 9 (and 9 only with
# the `q` switch), so it contributes archives whose layout owes nothing
# to our reading of the format.
#
# Same arrangement as tools/build_macunpack.sh: an oracle assembled on
# demand, never committed. The binary lands in ~/.cache/macextract/arc
# ($UNC_ARC_HOME), NOT build/: ci.sh's `make clean` deletes build/, and
# the cases that need it skipped on every run while it lived there
# (DECISIONS.md 2026-11-10, *the encoder make clean deleted*).
# tools/arc_bin.py finds it for run_arc.py, run_crypt.py and
# derive_arc.py. Run it in the FOREGROUND: it downloads, and a
# backgrounded process here has no network.
#
# SPDX-License-Identifier: 0BSD
set -e
cd "$(dirname "$0")/.."

DEST=${UNC_ARC_HOME:-$HOME/.cache/macextract/arc}
if [ -x "$DEST/usr/bin/arc" ]; then
    echo "get_arc: already present at $DEST/usr/bin/arc"
    exit 0
fi

mkdir -p "$DEST"
cd "$DEST"
apt-get download arc >/dev/null 2>&1 || {
    echo "get_arc: could not download the arc package" >&2
    exit 1
}
dpkg-deb -x arc_*.deb .
echo "get_arc: $DEST/usr/bin/arc"

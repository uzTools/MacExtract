#!/bin/sh
# mkgluelib.sh — a private libInterface.a whose glue.o comes from a given
# multiversal custom/glue.c, so glue_repro.c can be linked against the glue
# being reported on without touching the shared toolchain (README.md).
#
#   mkgluelib.sh <glue.c> <outdir>      then  cmake ... -DGLUE_LIB_DIR=<outdir>
#
# The compile line is multiversal's own (cincludes.rb, "Compiling glue
# code"); with the toolchain's own glue.c it reproduces the shipped glue.o
# byte for byte (checked 2026-10-15 on Retro68 335fa54f6d).
set -e
T=${RETRO68_TOOLCHAIN:-/opt/Retro68-build/toolchain}
src=$1; out=$2
[ -f "$src" ] && [ -n "$out" ] || { echo "usage: $0 <glue.c> <outdir>" >&2; exit 2; }
mkdir -p "$out/obj"
"$T/bin/m68k-apple-macos-gcc" -c "$src" -o "$out/obj/glue.o" \
    -I "$T/multiversal/CIncludes" -O -ffunction-sections
cp "$T/multiversal/lib68k/libInterface.a" "$out/libInterface.a"
chmod u+w "$out/libInterface.a"
"$T/bin/m68k-apple-macos-ar" r "$out/libInterface.a" "$out/obj/glue.o"
echo "$out/libInterface.a"

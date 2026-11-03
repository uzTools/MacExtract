# The companion's stub: one small application per claimed creator, which
# the Finder launches for an archive of that creator and which hands the
# archive on to MacExtract (DECISIONS.md 2026-10-11, *where the stubs can
# live*). Built once, with a placeholder creator; companion/make_stub.py
# turns the build into the stub for a given creator.
#
#   cmake -B build/stub -S companion/stub \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build/stub
#
# Not part of the MacExtract build, and not built by ci.sh.
cmake_minimum_required(VERSION 3.10)
project(macextract_stub C)
add_application(Stub CREATOR "MXst" stub.c stub.r)
# One CODE segment and no MacsBug names: Retro68's multi-segment loader
# and its patches are a third of a default build (10,112 B -> 6,784 B as
# MacBinary; DECISIONS.md 2026-11-01, *the Open item MultiFinder looks for*).
# Then no Retro68 runtime at all: position-independent code (-mpcrel) has
# nothing to relocate, so stub.c's own entry (stub_start) replaces _start,
# its relocator and newlib's exit chain (7,168 -> 4,224 B; DECISIONS.md
# 2026-11-03, *the helper without a runtime*). Nothing may go in .data or
# .bss: no start-up code sets them up.
target_compile_options(Stub PRIVATE -Os -Wall -ffunction-sections -mpcrel)
target_link_options(Stub PRIVATE -Wl,-gc-sections -Wl,--mac-single
    -Wl,--mac-strip-macsbug -Wl,-e,stub_start)

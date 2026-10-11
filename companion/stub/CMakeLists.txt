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
target_compile_options(Stub PRIVATE -Os -Wall)
target_link_options(Stub PRIVATE -Wl,-gc-sections)

# Standalone reproduction for the Retro68 HOpen/HOpenDF/HOpenRF glue bug.
#
#   cmake -B build -S . \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build
#
# Produces hopen_repro.APPL / .bin / .dsk. Mount the .dsk in Mini vMac beside a
# System 6.0.8 boot disk (Mac Plus, 68000) and double-click the application.
cmake_minimum_required(VERSION 3.10)
project(hopen_repro C)

add_application(hopen_repro hopen_repro.c)

# Plain 68000, matching the floor target where the bug was found.
target_compile_options(hopen_repro PRIVATE -mcpu=68000 -Os)

# The ioMisc reproduction (ISSUE.md): the one to send upstream.
add_application(IOMisc iomisc_repro.c)
target_compile_options(IOMisc PRIVATE -mcpu=68000 -Os)

# The Desktop Manager listing probe (dtlist.c says what it reads):
#
#   cmake -B build/dtlist -S tools/dtlist \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build/dtlist
#
# Nothing in ci.sh builds it.
cmake_minimum_required(VERSION 3.10)
project(dtlist C)
add_application(dtlist CREATOR "DTls" dtlist.c)
target_compile_options(dtlist PRIVATE -mcpu=68000 -Os -Wno-multichar)

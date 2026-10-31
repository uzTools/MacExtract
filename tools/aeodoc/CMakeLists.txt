# The post-processor hand-off probe (aeodoc.c says what it measures):
#
#   cmake -B build/aeodoc -S tools/aeodoc \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build/aeodoc
#
# Nothing in ci.sh builds it: System 7 only, not part of the application.
cmake_minimum_required(VERSION 3.10)
project(aeodoc C)

add_application(aeodoc
    CREATOR "AEOd"
    aeodoc.c
    aeodoc.r
)

target_compile_options(aeodoc PRIVATE -mcpu=68000 -Os -Wno-multichar)

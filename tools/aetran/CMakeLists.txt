# Build the Apple event sender used by the btoa harness:
#
#   cmake -B build/aetran -S tools/aetran \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build/aetran
#
# tools/vmac/sitcrypt.py --btoa-send does this itself. Nothing in ci.sh
# builds it: it is System 7 only and it is not part of the application.
cmake_minimum_required(VERSION 3.10)
project(aetran C)

add_application(aetran
    CREATOR "AETr"
    aetran.c
    aetran.r
)

target_compile_options(aetran PRIVATE -mcpu=68000 -Os -Wno-multichar)

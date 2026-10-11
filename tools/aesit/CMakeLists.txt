# Build the Apple event sender that asks StuffIt Deluxe for an encrypted,
# commented StuffIt 5 archive — the one specimen that reaches bit 5 of the
# archive flag byte in src/fmt_sit5.c:
#
#   cmake -B build/aesit -S tools/aesit \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build/aesit
#
# tools/vmac/sitcomment.py --specimen does this itself. Nothing in ci.sh
# builds it: it drives another application and is not part of ours.
cmake_minimum_required(VERSION 3.10)
project(aesit C)

add_application(aesit
    CREATOR "AESt"
    aesit.c
    aesit.r
)

target_compile_options(aesit PRIVATE -mcpu=68000 -Os -Wno-multichar)
